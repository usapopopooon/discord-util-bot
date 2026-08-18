"""Event Log cog.

特定の Discord イベントを指定チャンネルにログとして送信する。

対応イベント:
  - message_delete: メッセージ削除
  - message_edit: メッセージ編集
  - message_purge: メッセージ一括削除
  - member_join: メンバー参加
  - member_leave: メンバー脱退
  - member_kick: メンバー KICK
  - member_ban: メンバー BAN
  - member_unban: メンバー BAN 解除
  - member_timeout: メンバータイムアウト
  - role_change: ロール変更
  - nickname_change: ニックネーム変更
  - channel_create: チャンネル作成
  - channel_delete: チャンネル削除
  - channel_update: チャンネル更新
  - role_create: ロール作成
  - role_delete: ロール削除
  - role_update: ロール更新
  - voice_state: ボイスチャンネル参加/退出/移動
  - invite_create: 招待作成
  - invite_delete: 招待削除
  - thread_create: スレッド作成
  - thread_delete: スレッド削除
  - thread_update: スレッド更新
  - server_update: サーバー設定変更
  - emoji_update: 絵文字追加/削除/変更

仕組み:
  - 60 秒ごとに DB から有効な設定をキャッシュ
  - 各イベントリスナーでキャッシュを参照し、対応チャンネルに Embed 送信
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

import discord
from discord.ext import commands, tasks

from src.cogs._eventlog_helpers import (
    add_user_field,
    create_event_embed,
    find_audit_entry,
    format_datetime_with_relative,
    format_permission_changes,
    set_user_thumbnail,
    truncate_content,
)
from src.database.engine import async_session
from src.services.common_service import get_enabled_event_log_configs

logger = logging.getLogger(__name__)
_URL_PATTERN = re.compile(r"https?://\S+")


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    """Return True when the attachment is likely an image."""
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True

    filename = attachment.filename.lower()
    return filename.endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg")
    )


def _format_attachment_line(attachment: discord.Attachment) -> str:
    """Format one attachment line for embed field."""
    label = attachment.filename or "attachment"
    return f"[{label}]({attachment.url})"


def _format_permission_label(permission_name: str) -> str:
    """Convert permission key into a human-readable label."""
    return permission_name.replace("_", " ").title()


def _build_channel_overwrite_lines(
    channel: discord.abc.GuildChannel,
) -> list[str]:
    """Build display lines for channel permission overwrites."""
    overwrites = getattr(channel, "overwrites", {})
    if not isinstance(overwrites, dict) or not overwrites:
        return []

    def _sort_key(
        item: tuple[discord.abc.Snowflake, discord.PermissionOverwrite],
    ) -> tuple[int, str]:
        target = item[0]
        if isinstance(target, discord.Role):
            return (0, getattr(target, "name", "").lower())
        if isinstance(target, discord.Member):
            return (1, getattr(target, "name", "").lower())
        return (2, getattr(target, "name", "").lower())

    lines: list[str] = []
    for target, overwrite in sorted(overwrites.items(), key=_sort_key):
        allow, deny = overwrite.pair()
        allow_perms = [name for name, value in allow if value]
        deny_perms = [name for name, value in deny if value]
        if not allow_perms and not deny_perms:
            continue

        if isinstance(target, discord.Role):
            lines.append(f"Role override for {target.name}")
        elif isinstance(target, discord.Member):
            lines.append(f"Member override for {target.name}")
        else:
            target_name = getattr(target, "name", f"ID {target.id}")
            lines.append(f"Override for {target_name}")

        for permission_name in sorted(allow_perms):
            lines.append(f"{_format_permission_label(permission_name)}: ✅")
        for permission_name in sorted(deny_perms):
            lines.append(f"{_format_permission_label(permission_name)}: ❌")

    return lines


def _add_long_field(embed: discord.Embed, name: str, lines: list[str]) -> None:
    """Add one or more embed fields while respecting field length limits."""
    if not lines:
        return

    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > 1024:
            if current:
                chunks.append(current)
            current = line[:1024]
        else:
            current = candidate
    if current:
        chunks.append(current)

    for index, chunk in enumerate(chunks):
        field_name = name if index == 0 else f"{name} (cont.)"
        embed.add_field(name=field_name, value=chunk, inline=False)


def _format_channel_snapshot(channel: object) -> str:
    """Format channel mention with a name snapshot."""
    channel_id = getattr(channel, "id", "?")
    channel_name = getattr(channel, "name", "unknown")
    return f"<#{channel_id}> ({channel_name})"


def _extract_urls(content: str) -> set[str]:
    """Extract URL-like substrings from message content."""
    return set(_URL_PATTERN.findall(content))


def _extract_user_mentions(content: str) -> set[str]:
    """Extract user mentions from message content."""
    return set(re.findall(r"<@!?\d+>", content))


def _format_permission_list(diff: set[str]) -> str:
    """Format permission names for human-readable output."""
    if not diff:
        return "(none)"
    return ", ".join(_format_permission_label(name) for name in sorted(diff))


def _add_audit_fields(
    embed: discord.Embed,
    actor_id: int | None,
    reason: str | None,
    *,
    actor_label: str,
) -> None:
    """Add consistent actor and reason details when an audit entry exists."""
    if actor_id:
        embed.add_field(
            name=actor_label,
            value=f"<@{actor_id}>\nID: `{actor_id}`",
            inline=True,
        )
    if reason:
        embed.add_field(
            name="Reason",
            value=truncate_content(reason, max_len=900),
            inline=False,
        )


async def _find_invite_audit_entry(
    guild: discord.Guild,
    invite_code: str,
) -> tuple[int | None, str | None]:
    """Find a recent invite deletion entry, whose target has no snowflake ID."""
    try:
        async for entry in guild.audit_logs(
            limit=8,
            action=discord.AuditLogAction.invite_delete,
        ):
            if (
                getattr(entry.target, "code", None) == invite_code
                and entry.created_at
                and (datetime.now(UTC) - entry.created_at).total_seconds() < 10
            ):
                return (entry.user.id if entry.user else None, entry.reason)
    except (discord.Forbidden, discord.HTTPException):
        pass
    return None, None


def _build_overwrite_diff_lines(
    before: discord.abc.GuildChannel,
    after: discord.abc.GuildChannel,
) -> list[str]:
    """Build diff lines for channel permission overwrites."""
    before_overwrites = getattr(before, "overwrites", {}) or {}
    after_overwrites = getattr(after, "overwrites", {}) or {}
    if not isinstance(before_overwrites, dict):
        before_overwrites = {}
    if not isinstance(after_overwrites, dict):
        after_overwrites = {}
    all_targets = set(before_overwrites.keys()) | set(after_overwrites.keys())
    lines: list[str] = []

    def _target_name(target: object) -> str:
        if isinstance(target, discord.Role):
            return f"Role {target.name}"
        if isinstance(target, discord.Member):
            return f"Member {target.name}"
        return f"Target {getattr(target, 'id', '?')}"

    for target in sorted(all_targets, key=lambda t: getattr(t, "name", "")):
        before_ow = before_overwrites.get(target, discord.PermissionOverwrite())
        after_ow = after_overwrites.get(target, discord.PermissionOverwrite())
        b_allow, b_deny = before_ow.pair()
        a_allow, a_deny = after_ow.pair()
        b_allow_set = {n for n, v in b_allow if v}
        b_deny_set = {n for n, v in b_deny if v}
        a_allow_set = {n for n, v in a_allow if v}
        a_deny_set = {n for n, v in a_deny if v}
        if b_allow_set == a_allow_set and b_deny_set == a_deny_set:
            continue

        lines.append(_target_name(target))
        allow_added = a_allow_set - b_allow_set
        allow_removed = b_allow_set - a_allow_set
        deny_added = a_deny_set - b_deny_set
        deny_removed = b_deny_set - a_deny_set
        if allow_added:
            lines.append(f"  +Allow: {_format_permission_list(allow_added)}")
        if allow_removed:
            lines.append(f"  -Allow: {_format_permission_list(allow_removed)}")
        if deny_added:
            lines.append(f"  +Deny: {_format_permission_list(deny_added)}")
        if deny_removed:
            lines.append(f"  -Deny: {_format_permission_list(deny_removed)}")
    return lines


class _InviteData:
    """招待キャッシュ用の軽量データクラス。"""

    __slots__ = ("code", "uses", "inviter_id", "inviter_name")

    def __init__(
        self,
        code: str,
        uses: int,
        inviter_id: int | None,
        inviter_name: str | None,
    ) -> None:
        self.code = code
        self.uses = uses
        self.inviter_id = inviter_id
        self.inviter_name = inviter_name


class EventLogCog(commands.Cog):
    """イベントログ機能を提供する Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # キャッシュ: (guild_id, event_type) -> [channel_id, ...]
        self._cache: dict[tuple[str, str], list[str]] = {}
        # 招待キャッシュ: guild_id -> {invite_code: uses}
        self._invite_cache: dict[int, dict[str, _InviteData]] = {}
        # ボイス在室トラッキング: user_id -> (channel_id, joined_at)
        self._voice_sessions: dict[int, tuple[int, datetime]] = {}
        # 直近重複抑制: (guild_id, event_type, fingerprint) -> seen_at
        self._recent_event_fingerprints: dict[tuple[int, str, str], datetime] = {}

    async def cog_load(self) -> None:
        """Cog 読み込み時にキャッシュ同期タスクを開始する。"""
        self._sync_cache_task.start()

    async def cog_unload(self) -> None:
        """Cog アンロード時にタスクを停止する。"""
        self._sync_cache_task.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Bot 起動完了時に招待キャッシュを構築する。"""
        await self._refresh_invite_cache()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Bot が新しいギルドへ参加した時点で招待を追跡する。"""
        await self._cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """退出済みギルドの招待キャッシュを破棄する。"""
        self._invite_cache.pop(guild.id, None)

    async def _refresh_invite_cache(self) -> None:
        """全ギルドの招待情報をキャッシュする。"""
        for guild in self.bot.guilds:
            await self._cache_guild_invites(guild)

    async def _cache_guild_invites(self, guild: discord.Guild) -> None:
        """指定ギルドの招待一覧をキャッシュする。"""
        try:
            invites = await guild.invites()
            self._invite_cache[guild.id] = {
                inv.code: _InviteData(
                    code=inv.code,
                    uses=inv.uses or 0,
                    inviter_id=inv.inviter.id if inv.inviter else None,
                    inviter_name=inv.inviter.name if inv.inviter else None,
                )
                for inv in invites
            }
        except (discord.Forbidden, discord.HTTPException):
            logger.debug(
                "Cannot fetch invites for guild %s (missing permissions)",
                guild.id,
            )

    @tasks.loop(seconds=60)
    async def _sync_cache_task(self) -> None:
        """DB から有効な EventLog 設定を定期的にキャッシュする。"""
        try:
            await self._refresh_cache()
        except Exception:
            logger.exception("Failed to refresh event log cache")

    async def _refresh_cache(self) -> None:
        """キャッシュを DB から再構築する。"""
        new_cache: dict[tuple[str, str], list[str]] = {}
        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            async with async_session() as session:
                configs = await get_enabled_event_log_configs(session, guild_id)
            for config in configs:
                key = (guild_id, config.event_type)
                new_cache.setdefault(key, []).append(config.channel_id)
        self._cache = new_cache

    def _get_channels(self, guild: discord.Guild, event_type: str) -> list[str]:
        """キャッシュからチャンネル ID リストを取得する。"""
        return self._cache.get((str(guild.id), event_type), [])

    async def _send_log(
        self, guild: discord.Guild, event_type: str, embed: discord.Embed
    ) -> None:
        """指定イベントタイプの全チャンネルに Embed を送信する。"""
        fingerprint = (
            f"{embed.title}|{','.join(f'{f.name}:{f.value}' for f in embed.fields)}"
        )
        key = (guild.id, event_type, fingerprint)
        now = datetime.now(UTC)
        seen_at = self._recent_event_fingerprints.get(key)
        if seen_at and now - seen_at < timedelta(seconds=2):
            return
        self._recent_event_fingerprints[key] = now

        # 古いキーを軽量掃除
        expired = [
            k
            for k, t in self._recent_event_fingerprints.items()
            if now - t > timedelta(minutes=5)
        ]
        for k in expired:
            self._recent_event_fingerprints.pop(k, None)

        channel_ids = self._get_channels(guild, event_type)
        for channel_id in channel_ids:
            cached_channel = guild.get_channel(int(channel_id))
            channel = (
                cached_channel
                if isinstance(cached_channel, discord.TextChannel)
                else None
            )
            if channel is None:
                try:
                    fetched = await guild.fetch_channel(int(channel_id))
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    fetched = None
                if isinstance(fetched, discord.TextChannel):
                    channel = fetched
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    logger.warning(
                        "Missing permissions for event log channel %s",
                        channel_id,
                    )
                except discord.HTTPException as e:
                    logger.warning(
                        "Failed to send event log to channel %s: %s",
                        channel_id,
                        e,
                    )

    # =====================================================================
    # Message Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """メッセージ削除イベント。"""
        if not message.guild or message.author.bot:
            return
        if not self._get_channels(message.guild, "message_delete"):
            return

        content = truncate_content(message.content or "(empty)")

        # Audit log から削除した人を取得
        # 自分で削除した場合は audit log にエントリが作られないため None になる
        # message_delete は extra.channel のチェックが必要なため汎用ヘルパー不可
        deleted_by_id: int | None = None
        deletion_reason: str | None = None
        try:
            async for entry in message.guild.audit_logs(
                limit=8, action=discord.AuditLogAction.message_delete
            ):
                extra_channel = getattr(entry.extra, "channel", None)
                if (
                    entry.target
                    and entry.target.id == message.author.id
                    and extra_channel
                    and extra_channel.id == message.channel.id
                    and entry.created_at
                    and (datetime.now(UTC) - entry.created_at).total_seconds() < 10
                ):
                    deleted_by_id = entry.user.id if entry.user else None
                    deletion_reason = entry.reason
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        embed = create_event_embed("Message Deleted", "message_delete")
        add_user_field(embed, message.author, label="Author")
        embed.add_field(
            name="Channel",
            value=_format_channel_snapshot(message.channel),
            inline=True,
        )
        embed.add_field(name="Message ID", value=f"`{message.id}`", inline=True)
        if isinstance(message.created_at, datetime):
            embed.add_field(
                name="Posted At",
                value=format_datetime_with_relative(message.created_at),
                inline=True,
            )
        if deleted_by_id and deleted_by_id != message.author.id:
            embed.add_field(
                name="Deleted By",
                value=f"<@{deleted_by_id}>\nID: `{deleted_by_id}`",
                inline=True,
            )
        if message.reference and getattr(message.reference, "message_id", None):
            ref_id = message.reference.message_id
            embed.add_field(
                name="Reply To",
                value=f"`{ref_id}`",
                inline=True,
            )
        embed.add_field(name="Content", value=content, inline=False)
        if deletion_reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(deletion_reason, max_len=900),
                inline=False,
            )

        attachments = list(message.attachments)
        if attachments:
            attachment_lines = [_format_attachment_line(a) for a in attachments]
            embed.add_field(
                name="Attachments",
                value=truncate_content("\n".join(attachment_lines), max_len=1024),
                inline=False,
            )
            metadata_lines = [
                (f"{a.filename}: type={a.content_type or 'unknown'}, size={a.size}B")
                for a in attachments
            ]
            embed.add_field(
                name="Attachment Metadata",
                value=truncate_content("\n".join(metadata_lines), max_len=1024),
                inline=False,
            )
            first_image = next(
                (a for a in attachments if _is_image_attachment(a)),
                None,
            )
            if first_image:
                embed.set_image(url=first_image.url)
        set_user_thumbnail(embed, message.author)

        await self._send_log(message.guild, "message_delete", embed)

    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        """メッセージ編集イベント。"""
        if not after.guild or after.author.bot:
            return
        before_attachment_urls = {a.url for a in before.attachments}
        after_attachment_urls = {a.url for a in after.attachments}
        if (
            before.content == after.content
            and before_attachment_urls == after_attachment_urls
        ):
            return
        if not self._get_channels(after.guild, "message_edit"):
            return

        before_content = truncate_content(before.content or "(empty)")
        after_content = truncate_content(after.content or "(empty)")

        embed = create_event_embed("Message Edited", "message_edit")
        add_user_field(embed, after.author, label="Author")
        embed.add_field(
            name="Channel",
            value=_format_channel_snapshot(after.channel),
            inline=True,
        )
        embed.add_field(name="Before", value=before_content, inline=False)
        embed.add_field(name="After", value=after_content, inline=False)
        embed.add_field(name="Message ID", value=f"`{after.id}`", inline=True)
        if isinstance(after.created_at, datetime):
            embed.add_field(
                name="Posted At",
                value=format_datetime_with_relative(after.created_at),
                inline=True,
            )
        if isinstance(after.edited_at, datetime):
            embed.add_field(
                name="Edited At",
                value=format_datetime_with_relative(after.edited_at),
                inline=True,
            )
        added_urls = _extract_urls(after.content or "") - _extract_urls(
            before.content or ""
        )
        removed_urls = _extract_urls(before.content or "") - _extract_urls(
            after.content or ""
        )
        if added_urls or removed_urls:
            url_changes = []
            if added_urls:
                url_changes.append(
                    "Added: "
                    f"{truncate_content(', '.join(sorted(added_urls)), max_len=900)}"
                )
            if removed_urls:
                url_changes.append(
                    "Removed: "
                    f"{truncate_content(', '.join(sorted(removed_urls)), max_len=900)}"
                )
            embed.add_field(
                name="URL Changes", value="\n".join(url_changes), inline=False
            )

        added_mentions = _extract_user_mentions(
            after.content or ""
        ) - _extract_user_mentions(before.content or "")
        removed_mentions = _extract_user_mentions(
            before.content or ""
        ) - _extract_user_mentions(after.content or "")
        if added_mentions or removed_mentions:
            mention_changes = []
            if added_mentions:
                mention_changes.append(f"Added: {', '.join(sorted(added_mentions))}")
            if removed_mentions:
                mention_changes.append(
                    f"Removed: {', '.join(sorted(removed_mentions))}"
                )
            embed.add_field(
                name="Mention Changes",
                value=truncate_content("\n".join(mention_changes), max_len=1024),
                inline=False,
            )

        if before_attachment_urls != after_attachment_urls:
            added_files = after_attachment_urls - before_attachment_urls
            removed_files = before_attachment_urls - after_attachment_urls
            file_changes = []
            if added_files:
                file_changes.append(
                    "Added: "
                    f"{truncate_content(', '.join(sorted(added_files)), max_len=900)}"
                )
            if removed_files:
                file_changes.append(
                    "Removed: "
                    f"{truncate_content(', '.join(sorted(removed_files)), max_len=900)}"
                )
            embed.add_field(
                name="Attachment Changes",
                value="\n".join(file_changes),
                inline=False,
            )
        if after.jump_url:
            embed.add_field(
                name="Jump",
                value=f"[Go to message]({after.jump_url})",
                inline=False,
            )
        set_user_thumbnail(embed, after.author)

        await self._send_log(after.guild, "message_edit", embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        """メッセージ一括削除イベント。"""
        if not messages:
            return
        guild = messages[0].guild
        if not guild:
            return
        if not self._get_channels(guild, "message_purge"):
            return

        channel = messages[0].channel
        count = len(messages)
        authors = {m.author.name for m in messages if not m.author.bot}
        authors_str = ", ".join(sorted(authors)[:10])
        if len(authors) > 10:
            authors_str += f" (+{len(authors) - 10} more)"

        embed = create_event_embed("Messages Purged", "message_purge")
        embed.add_field(
            name="Channel",
            value=_format_channel_snapshot(channel),
            inline=True,
        )
        embed.add_field(name="Count", value=str(count), inline=True)
        if authors_str:
            embed.add_field(name="Authors", value=authors_str, inline=False)

        message_ids = [f"`{message.id}`" for message in messages]
        embed.add_field(
            name="Message IDs",
            value=truncate_content(", ".join(message_ids)),
            inline=False,
        )
        created_at_values = [
            message.created_at
            for message in messages
            if isinstance(message.created_at, datetime)
        ]
        if created_at_values:
            embed.add_field(
                name="Posted At Range",
                value=(
                    f"{format_datetime_with_relative(min(created_at_values))} - "
                    f"{format_datetime_with_relative(max(created_at_values))}"
                ),
                inline=False,
            )

        deleted_by_id: int | None = None
        deletion_reason: str | None = None
        try:
            async for entry in guild.audit_logs(
                limit=8,
                action=discord.AuditLogAction.message_bulk_delete,
            ):
                extra_channel = getattr(entry.extra, "channel", None)
                target_id = getattr(entry.target, "id", None)
                if (
                    (
                        target_id == channel.id
                        or getattr(extra_channel, "id", None) == channel.id
                    )
                    and entry.created_at
                    and (datetime.now(UTC) - entry.created_at).total_seconds() < 10
                ):
                    deleted_by_id = entry.user.id if entry.user else None
                    deletion_reason = entry.reason
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        if deleted_by_id:
            embed.add_field(
                name="Deleted By",
                value=f"<@{deleted_by_id}>\nID: `{deleted_by_id}`",
                inline=True,
            )
        if deletion_reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(deletion_reason, max_len=900),
                inline=False,
            )

        await self._send_log(guild, "message_purge", embed)

    # =====================================================================
    # Member Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """メンバー参加イベント。"""
        if member.bot:
            return
        if not self._get_channels(member.guild, "member_join"):
            return

        account_age = datetime.now(UTC) - member.created_at
        days = account_age.days

        embed = create_event_embed("Member Joined", "member_join")
        add_user_field(embed, member)
        embed.add_field(
            name="Account Age",
            value=f"{days} days",
            inline=True,
        )
        embed.add_field(
            name="Account Created",
            value=format_datetime_with_relative(member.created_at),
            inline=True,
        )
        if member.joined_at:
            embed.add_field(
                name="Joined At",
                value=format_datetime_with_relative(member.joined_at),
                inline=True,
            )
        embed.add_field(
            name="Member Count",
            value=str(member.guild.member_count),
            inline=True,
        )

        # 招待キャッシュの差分から招待方法・招待者を特定
        invite_info = await self._detect_used_invite(member.guild)
        if invite_info:
            embed.add_field(
                name="Invited By",
                value=invite_info,
                inline=False,
            )

        set_user_thumbnail(embed, member)

        await self._send_log(member.guild, "member_join", embed)

    async def _detect_used_invite(self, guild: discord.Guild) -> str | None:
        """招待キャッシュと最新の招待を比較し、使用された招待を特定する。"""
        old_cache = self._invite_cache.get(guild.id, {})

        try:
            new_invites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return None

        # 新しいキャッシュを構築
        new_cache: dict[str, _InviteData] = {}
        used_invite: _InviteData | None = None
        largest_increase = 0

        for inv in new_invites:
            new_data = _InviteData(
                code=inv.code,
                uses=inv.uses or 0,
                inviter_id=inv.inviter.id if inv.inviter else None,
                inviter_name=inv.inviter.name if inv.inviter else None,
            )
            new_cache[inv.code] = new_data

            # uses が増えた招待を検出
            old_data = old_cache.get(inv.code)
            increase = new_data.uses - old_data.uses if old_data else 0
            if increase > largest_increase:
                used_invite = new_data
                largest_increase = increase

        # キャッシュから消えた招待 (max_uses に達して削除) をチェック
        if used_invite is None:
            for code, old_data in old_cache.items():
                if code not in new_cache:
                    used_invite = old_data
                    break

        # キャッシュを更新
        self._invite_cache[guild.id] = new_cache

        if used_invite is None:
            # Vanity URL の可能性
            try:
                vanity = await guild.vanity_invite()
                if vanity:
                    details = f"Vanity URL (`{vanity.code}`)"
                    if isinstance(vanity.uses, int):
                        details += f" / Uses: {vanity.uses}"
                    return details
            except (discord.Forbidden, discord.HTTPException):
                pass
            return None

        if used_invite.inviter_id:
            # 同じ招待者の全招待の使用回数を合計
            total_uses = sum(
                d.uses
                for d in new_cache.values()
                if d.inviter_id == used_invite.inviter_id
            )
            # 期限切れ招待 (new_cache に含まれない) の uses も加算
            if used_invite.code not in new_cache:
                total_uses += used_invite.uses
            return (
                f"<@{used_invite.inviter_id}>"
                f" (Invite: `{used_invite.code}` / Total: {total_uses})"
            )
        return f"Invite: `{used_invite.code}`"

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """メンバー脱退イベント (leave / kick を audit log で判別)。"""
        if member.bot:
            return

        has_leave = bool(self._get_channels(member.guild, "member_leave"))
        has_kick = bool(self._get_channels(member.guild, "member_kick"))
        if not has_leave and not has_kick:
            return

        # Audit log で kick かどうか判定
        kick_info: tuple[int | None, str | None] | None = None
        if has_kick:
            kick_info = await self._check_kick_audit(member.guild, member)

        if kick_info and has_kick:
            await self._send_kick_log(member, kick_info)
        elif has_leave:
            await self._send_leave_log(member)

    async def _check_kick_audit(
        self, guild: discord.Guild, member: discord.Member
    ) -> tuple[int | None, str | None] | None:
        """Audit log から kick を検出する。(moderator_id, reason) or None."""
        mod_id, reason = await find_audit_entry(
            guild, discord.AuditLogAction.kick, member.id
        )
        if mod_id is not None or reason is not None:
            return (mod_id, reason)
        return None

    async def _send_kick_log(
        self,
        member: discord.Member,
        kick_info: tuple[int | None, str | None],
    ) -> None:
        """Kick ログ Embed を送信する。"""
        mod_id, reason = kick_info

        embed = create_event_embed("Member Kicked", "member_kick")
        add_user_field(embed, member)
        if mod_id:
            embed.add_field(
                name="Kicked By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        embed.add_field(
            name="Reason",
            value=truncate_content(reason or "No reason provided", max_len=900),
            inline=False,
        )
        set_user_thumbnail(embed, member)

        await self._send_log(member.guild, "member_kick", embed)

    async def _send_leave_log(self, member: discord.Member) -> None:
        """Leave ログ Embed を送信する。"""
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        roles_str = ", ".join(roles) if roles else "None"
        roles_str = truncate_content(roles_str)

        embed = create_event_embed("Member Left", "member_leave")
        add_user_field(embed, member)
        if member.joined_at:
            embed.add_field(
                name="Joined At",
                value=format_datetime_with_relative(member.joined_at),
                inline=True,
            )
        embed.add_field(name="Roles", value=roles_str, inline=False)
        set_user_thumbnail(embed, member)

        await self._send_log(member.guild, "member_leave", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        """メンバー BAN イベント。"""
        if user.bot:
            return
        if not self._get_channels(guild, "member_ban"):
            return

        # Audit log から BAN 実行者と理由を取得
        mod_id, reason = await find_audit_entry(
            guild, discord.AuditLogAction.ban, user.id
        )

        # Audit log で取得できなかった場合、fetch_ban から理由だけ取得
        if reason is None:
            try:
                ban_entry = await guild.fetch_ban(user)
                reason = ban_entry.reason
            except (discord.NotFound, discord.HTTPException):
                pass

        embed = create_event_embed("Member Banned", "member_ban")
        add_user_field(embed, user)
        if mod_id:
            embed.add_field(
                name="Banned By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        reason_text = reason or "No reason provided"
        # BAN 理由が長すぎると他フィールドが見づらくなるため短縮表示する。
        reason_text = truncate_content(reason_text, max_len=300)
        embed.add_field(name="Reason", value=reason_text, inline=False)
        set_user_thumbnail(embed, user)

        await self._send_log(guild, "member_ban", embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        """メンバー BAN 解除イベント。"""
        if user.bot:
            return
        if not self._get_channels(guild, "member_unban"):
            return

        # Audit log から解除した人を取得
        mod_id, reason = await find_audit_entry(
            guild,
            discord.AuditLogAction.unban,
            user.id,
        )

        embed = create_event_embed("Member Unbanned", "member_unban")
        add_user_field(embed, user)
        if mod_id:
            embed.add_field(
                name="Unbanned By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )
        set_user_thumbnail(embed, user)

        await self._send_log(guild, "member_unban", embed)

    # =====================================================================
    # Member Update Events (roles / nickname)
    # =====================================================================

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        """メンバー更新イベント (ロール変更 / ニックネーム変更 / タイムアウト)。"""
        if after.bot:
            return

        # タイムアウト (timed_out_until が None → 値 に変化)
        if not before.timed_out_until and after.timed_out_until:
            await self._handle_timeout(after)
        # タイムアウト解除
        if before.timed_out_until and not after.timed_out_until:
            await self._handle_timeout_removed(after)

        # ロール変更
        if before.roles != after.roles:
            await self._handle_role_change(before, after)

        # ニックネーム変更
        if before.nick != after.nick:
            await self._handle_nickname_change(before, after)

        # 表示名やアバター変更
        if before.display_name != after.display_name or before.avatar != after.avatar:
            await self._handle_profile_change(before, after)

    async def _handle_timeout(self, member: discord.Member) -> None:
        """タイムアウトログを送信する。"""
        if not self._get_channels(member.guild, "member_timeout"):
            return

        until = member.timed_out_until
        until_str = format_datetime_with_relative(until)

        # Audit log からモデレーターと理由を取得
        mod_id, reason = await find_audit_entry(
            member.guild, discord.AuditLogAction.member_update, member.id
        )

        embed = create_event_embed("Member Timed Out", "member_timeout")
        add_user_field(embed, member)
        if mod_id:
            embed.add_field(
                name="Timed Out By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        embed.add_field(name="Until", value=until_str, inline=True)
        embed.add_field(
            name="Reason",
            value=truncate_content(reason or "No reason provided", max_len=900),
            inline=False,
        )
        set_user_thumbnail(embed, member)

        await self._send_log(member.guild, "member_timeout", embed)

    async def _handle_role_change(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        """ロール変更ログを送信する。"""
        if not self._get_channels(after.guild, "role_change"):
            return

        added = set(after.roles) - set(before.roles)
        removed = set(before.roles) - set(after.roles)

        changes: list[str] = []
        for role in added:
            changes.append(f"+ {role.mention}")
        for role in removed:
            changes.append(f"× {role.mention}")

        if not changes:
            return

        embed = create_event_embed("Member Roles Updated", "role_change")
        add_user_field(embed, after)
        embed.add_field(
            name="Changes",
            value="\n".join(changes),
            inline=False,
        )
        mod_id, reason = await find_audit_entry(
            after.guild, discord.AuditLogAction.member_role_update, after.id
        )
        if mod_id:
            embed.add_field(
                name="Updated By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )
        set_user_thumbnail(embed, after)

        await self._send_log(after.guild, "role_change", embed)

    async def _handle_nickname_change(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        """ニックネーム変更ログを送信する。"""
        if not self._get_channels(after.guild, "nickname_change"):
            return

        embed = create_event_embed("Nickname Changed", "nickname_change")
        add_user_field(embed, after)
        embed.add_field(
            name="Before",
            value=before.nick or "(none)",
            inline=True,
        )
        embed.add_field(
            name="After",
            value=after.nick or "(none)",
            inline=True,
        )
        mod_id, reason = await find_audit_entry(
            after.guild, discord.AuditLogAction.member_update, after.id
        )
        if mod_id:
            embed.add_field(
                name="Updated By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )
        set_user_thumbnail(embed, after)

        await self._send_log(after.guild, "nickname_change", embed)

    async def _handle_timeout_removed(self, member: discord.Member) -> None:
        """タイムアウト解除ログを送信する。"""
        if not self._get_channels(member.guild, "member_timeout"):
            return
        mod_id, reason = await find_audit_entry(
            member.guild, discord.AuditLogAction.member_update, member.id
        )
        embed = create_event_embed("Member Timeout Removed", "member_timeout")
        add_user_field(embed, member)
        if mod_id:
            embed.add_field(
                name="Updated By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        embed.add_field(name="Status", value="timeout removed", inline=True)
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )
        set_user_thumbnail(embed, member)
        await self._send_log(member.guild, "member_timeout", embed)

    async def _handle_profile_change(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        """表示名・アバター変更ログを送信する。"""
        if not self._get_channels(after.guild, "nickname_change"):
            return

        # ニックネーム変更は専用ログで送信するため重複を避ける。
        if before.nick != after.nick:
            return

        changes: list[str] = []
        if before.display_name != after.display_name:
            changes.append(
                f"Display Name: {before.display_name} → {after.display_name}"
            )
        if before.avatar != after.avatar:
            changes.append("Avatar: changed")
        if not changes:
            return
        embed = create_event_embed("Member Profile Updated", "nickname_change")
        add_user_field(embed, after)
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        set_user_thumbnail(embed, after)
        await self._send_log(after.guild, "nickname_change", embed)

    # =====================================================================
    # Channel Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """チャンネル作成イベント。"""
        if not self._get_channels(channel.guild, "channel_create"):
            return

        embed = create_event_embed("Channel Created", "channel_create")
        embed.add_field(name="Name", value=channel.name, inline=True)
        embed.add_field(
            name="Type",
            value=str(channel.type).replace("_", " ").title(),
            inline=True,
        )
        if channel.category:
            embed.add_field(name="Category", value=channel.category.name, inline=True)
        embed.add_field(name="Channel ID", value=f"`{channel.id}`", inline=True)
        if isinstance(channel.created_at, datetime):
            embed.add_field(
                name="Created At",
                value=format_datetime_with_relative(channel.created_at),
                inline=True,
            )
        topic = getattr(channel, "topic", None)
        if isinstance(topic, str) and topic:
            embed.add_field(
                name="Topic",
                value=truncate_content(topic),
                inline=False,
            )

        overwrite_lines = _build_channel_overwrite_lines(channel)
        _add_long_field(embed, "Permission Overwrites", overwrite_lines)
        mod_id, reason = await find_audit_entry(
            channel.guild, discord.AuditLogAction.channel_create, channel.id
        )
        if mod_id:
            embed.add_field(
                name="Created By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )

        await self._send_log(channel.guild, "channel_create", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """チャンネル削除イベント。"""
        if not self._get_channels(channel.guild, "channel_delete"):
            return

        embed = create_event_embed("Channel Deleted", "channel_delete")
        embed.add_field(name="Name", value=channel.name, inline=True)
        embed.add_field(
            name="Type",
            value=str(channel.type).replace("_", " ").title(),
            inline=True,
        )
        if channel.category:
            embed.add_field(name="Category", value=channel.category.name, inline=True)
        embed.add_field(name="Channel ID", value=f"`{channel.id}`", inline=True)
        if isinstance(channel.created_at, datetime):
            embed.add_field(
                name="Created At",
                value=format_datetime_with_relative(channel.created_at),
                inline=True,
            )
        mod_id, reason = await find_audit_entry(
            channel.guild, discord.AuditLogAction.channel_delete, channel.id
        )
        if mod_id:
            embed.add_field(
                name="Deleted By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )

        await self._send_log(channel.guild, "channel_delete", embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        """チャンネル更新イベント。"""
        if not self._get_channels(after.guild, "channel_update"):
            return

        changes: list[str] = []
        if before.name != after.name:
            changes.append(f"**Name:** {before.name} → {after.name}")
        if hasattr(before, "topic") and hasattr(after, "topic"):
            before_topic = getattr(before, "topic", None) or ""
            after_topic = getattr(after, "topic", None) or ""
            if before_topic != after_topic:
                changes.append(
                    f"**Topic:** {truncate_content(before_topic or '(none)', 200)}"
                    f" → {truncate_content(after_topic or '(none)', 200)}"
                )
        if hasattr(before, "slowmode_delay") and hasattr(after, "slowmode_delay"):
            b_slow = getattr(before, "slowmode_delay", 0)
            a_slow = getattr(after, "slowmode_delay", 0)
            if b_slow != a_slow:
                changes.append(f"**Slowmode:** {b_slow}s → {a_slow}s")
        if hasattr(before, "nsfw") and hasattr(after, "nsfw"):
            b_nsfw = getattr(before, "nsfw", False)
            a_nsfw = getattr(after, "nsfw", False)
            if b_nsfw != a_nsfw:
                changes.append(f"**NSFW:** {b_nsfw} → {a_nsfw}")
        if before.category != after.category:
            changes.append(
                f"**Category:** "
                f"{before.category.name if before.category else '(none)'}"
                f" → {after.category.name if after.category else '(none)'}"
            )
        if hasattr(before, "bitrate") and hasattr(after, "bitrate"):
            b_bitrate = getattr(before, "bitrate", None)
            a_bitrate = getattr(after, "bitrate", None)
            if b_bitrate != a_bitrate:
                changes.append(f"**Bitrate:** {b_bitrate} → {a_bitrate}")
        if hasattr(before, "user_limit") and hasattr(after, "user_limit"):
            b_user_limit = getattr(before, "user_limit", None)
            a_user_limit = getattr(after, "user_limit", None)
            if b_user_limit != a_user_limit:
                changes.append(f"**User Limit:** {b_user_limit} → {a_user_limit}")

        overwrite_changes = _build_overwrite_diff_lines(before, after)
        if not changes and not overwrite_changes:
            return

        embed = create_event_embed("Channel Updated", "channel_update")
        embed.add_field(
            name="Channel", value=f"<#{after.id}> ({after.name})", inline=True
        )
        if changes:
            embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        if overwrite_changes:
            _add_long_field(embed, "Overwrite Changes", overwrite_changes)

        mod_id, reason = await find_audit_entry(
            after.guild, discord.AuditLogAction.channel_update, after.id
        )
        if mod_id:
            embed.add_field(
                name="Updated By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )

        await self._send_log(after.guild, "channel_update", embed)

    # =====================================================================
    # Role Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        """ロール作成イベント。"""
        if not self._get_channels(role.guild, "role_create"):
            return

        embed = create_event_embed("Role Created", "role_create")
        embed.add_field(name="Role", value=f"{role.mention} ({role.name})", inline=True)
        embed.add_field(name="Role ID", value=f"`{role.id}`", inline=True)
        if role.color.value:
            embed.add_field(name="Color", value=f"#{role.color.value:06X}", inline=True)
        if isinstance(role.created_at, datetime):
            embed.add_field(
                name="Created At",
                value=format_datetime_with_relative(role.created_at),
                inline=True,
            )
        if isinstance(role.permissions, discord.Permissions):
            permission_names = {name for name, enabled in role.permissions if enabled}
            embed.add_field(
                name="Permissions",
                value=truncate_content(_format_permission_list(permission_names)),
                inline=False,
            )
        mod_id, reason = await find_audit_entry(
            role.guild, discord.AuditLogAction.role_create, role.id
        )
        if mod_id:
            embed.add_field(
                name="Created By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )

        await self._send_log(role.guild, "role_create", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """ロール削除イベント。"""
        if not self._get_channels(role.guild, "role_delete"):
            return

        embed = create_event_embed("Role Deleted", "role_delete")
        embed.add_field(name="Role", value=role.name, inline=True)
        embed.add_field(name="Role ID", value=f"`{role.id}`", inline=True)
        if role.color.value:
            embed.add_field(name="Color", value=f"#{role.color.value:06X}", inline=True)
        embed.add_field(name="Members", value=str(len(role.members)), inline=True)
        if isinstance(role.created_at, datetime):
            embed.add_field(
                name="Created At",
                value=format_datetime_with_relative(role.created_at),
                inline=True,
            )
        if isinstance(role.permissions, discord.Permissions):
            permission_names = {name for name, enabled in role.permissions if enabled}
            embed.add_field(
                name="Permissions",
                value=truncate_content(_format_permission_list(permission_names)),
                inline=False,
            )
        mod_id, reason = await find_audit_entry(
            role.guild, discord.AuditLogAction.role_delete, role.id
        )
        if mod_id:
            embed.add_field(
                name="Deleted By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )

        await self._send_log(role.guild, "role_delete", embed)

    @commands.Cog.listener()
    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> None:
        """ロール更新イベント。"""
        if not self._get_channels(after.guild, "role_update"):
            return

        changes: list[str] = []
        if before.name != after.name:
            changes.append(f"**Name:** {before.name} → {after.name}")
        if before.color != after.color:
            changes.append(
                f"**Color:** #{before.color.value:06X} → #{after.color.value:06X}"
            )
        if before.hoist != after.hoist:
            changes.append(f"**Hoisted:** {before.hoist} → {after.hoist}")
        if before.mentionable != after.mentionable:
            changes.append(
                f"**Mentionable:** {before.mentionable} → {after.mentionable}"
            )
        if before.permissions != after.permissions:
            if isinstance(before.permissions, discord.Permissions) and isinstance(
                after.permissions, discord.Permissions
            ):
                permission_lines = format_permission_changes(
                    before.permissions,
                    after.permissions,
                )
                changes.append(
                    "**Permissions:**\n" + ("\n".join(permission_lines) or "changed")
                )
            else:
                changes.append("**Permissions:** changed")

        if not changes:
            return

        embed = create_event_embed("Role Updated", "role_update")
        embed.add_field(
            name="Role", value=f"{after.mention} ({after.name})", inline=True
        )
        embed.add_field(name="Role ID", value=f"`{after.id}`", inline=True)
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        mod_id, reason = await find_audit_entry(
            after.guild, discord.AuditLogAction.role_update, after.id
        )
        if mod_id:
            embed.add_field(
                name="Updated By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )

        await self._send_log(after.guild, "role_update", embed)

    # =====================================================================
    # Voice State Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """ボイスチャンネル状態変更イベント。"""
        if member.bot:
            return
        if not self._get_channels(member.guild, "voice_state"):
            return

        # Join
        if before.channel is None and after.channel is not None:
            action = "Joined Voice Channel"
            detail = _format_channel_snapshot(after.channel)
            self._voice_sessions[member.id] = (after.channel.id, datetime.now(UTC))
            member_count = len(getattr(after.channel, "members", []))
            extra_detail = f"Members now: {member_count}"
        # Leave
        elif before.channel is not None and after.channel is None:
            action = "Left Voice Channel"
            detail = _format_channel_snapshot(before.channel)
            started = self._voice_sessions.pop(member.id, None)
            if started and started[0] == before.channel.id:
                stayed = datetime.now(UTC) - started[1]
                extra_detail = f"Stayed: {int(stayed.total_seconds())}s"
            else:
                extra_detail = None
        # Move
        elif (
            before.channel is not None
            and after.channel is not None
            and before.channel != after.channel
        ):
            action = "Moved Voice Channel"
            detail = (
                f"{_format_channel_snapshot(before.channel)}"
                f" → {_format_channel_snapshot(after.channel)}"
            )
            self._voice_sessions[member.id] = (after.channel.id, datetime.now(UTC))
            extra_detail = f"Members now: {len(getattr(after.channel, 'members', []))}"
        else:
            state_changes: list[str] = []
            tracked = [
                ("Self Mute", before.self_mute, after.self_mute),
                ("Self Deaf", before.self_deaf, after.self_deaf),
                ("Server Mute", before.mute, after.mute),
                ("Server Deaf", before.deaf, after.deaf),
                ("Streaming", before.self_stream, after.self_stream),
                ("Video", before.self_video, after.self_video),
            ]
            for label, b_val, a_val in tracked:
                if b_val != a_val:
                    state_changes.append(f"{label}: {b_val} → {a_val}")
            if not state_changes:
                return
            action = "Voice State Updated"
            current_channel = after.channel or before.channel
            detail = (
                _format_channel_snapshot(current_channel)
                if current_channel is not None
                else "(none)"
            )
            extra_detail = "\n".join(state_changes)

        embed = create_event_embed(action, "voice_state")
        add_user_field(embed, member)
        embed.add_field(name="Channel", value=detail, inline=True)
        if extra_detail:
            embed.add_field(name="Details", value=extra_detail, inline=False)
        set_user_thumbnail(embed, member)

        await self._send_log(member.guild, "voice_state", embed)

    # =====================================================================
    # Invite Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        """招待作成イベント。"""
        if not invite.guild:
            return

        # 招待キャッシュの更新 (既存ロジック)
        guild_id = invite.guild.id
        if guild_id not in self._invite_cache:
            self._invite_cache[guild_id] = {}
        self._invite_cache[guild_id][invite.code] = _InviteData(
            code=invite.code,
            uses=invite.uses or 0,
            inviter_id=invite.inviter.id if invite.inviter else None,
            inviter_name=invite.inviter.name if invite.inviter else None,
        )

        # ログ送信
        guild = self.bot.get_guild(guild_id)
        if not guild or not self._get_channels(guild, "invite_create"):
            return

        embed = create_event_embed("Invite Created", "invite_create")
        embed.add_field(name="Code", value=f"`{invite.code}`", inline=True)
        embed.add_field(name="URL", value=str(invite.url), inline=False)
        if invite.inviter:
            add_user_field(embed, invite.inviter, label="Created By")
        if invite.channel:
            embed.add_field(
                name="Channel",
                value=_format_channel_snapshot(invite.channel),
                inline=True,
            )
        if isinstance(invite.created_at, datetime):
            embed.add_field(
                name="Created At",
                value=format_datetime_with_relative(invite.created_at),
                inline=True,
            )
        if isinstance(invite.expires_at, datetime):
            embed.add_field(
                name="Expires",
                value=format_datetime_with_relative(invite.expires_at),
                inline=True,
            )
        else:
            embed.add_field(name="Expires", value="Never", inline=True)
        if invite.max_uses:
            embed.add_field(name="Max Uses", value=str(invite.max_uses), inline=True)
        else:
            embed.add_field(name="Max Uses", value="Unlimited", inline=True)
        if isinstance(invite.uses, int):
            embed.add_field(name="Current Uses", value=str(invite.uses), inline=True)
        embed.add_field(
            name="Temporary",
            value="Yes" if invite.temporary else "No",
            inline=True,
        )

        await self._send_log(guild, "invite_create", embed)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        """招待削除イベント。"""
        if not invite.guild:
            return

        # 招待キャッシュの更新 (既存ロジック)
        guild_id = invite.guild.id
        self._invite_cache.get(guild_id, {}).pop(invite.code, None)

        # ログ送信
        guild = self.bot.get_guild(guild_id)
        if not guild or not self._get_channels(guild, "invite_delete"):
            return

        embed = create_event_embed("Invite Deleted", "invite_delete")
        embed.add_field(name="Code", value=f"`{invite.code}`", inline=True)
        embed.add_field(name="URL", value=str(invite.url), inline=False)
        if invite.channel:
            embed.add_field(
                name="Channel",
                value=_format_channel_snapshot(invite.channel),
                inline=True,
            )
        mod_id, reason = await _find_invite_audit_entry(guild, invite.code)
        _add_audit_fields(
            embed,
            mod_id,
            reason,
            actor_label="Deleted By",
        )

        await self._send_log(guild, "invite_delete", embed)

    # =====================================================================
    # Thread Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        """スレッド作成イベント。"""
        if not self._get_channels(thread.guild, "thread_create"):
            return

        embed = create_event_embed("Thread Created", "thread_create")
        embed.add_field(name="Name", value=thread.name, inline=True)
        embed.add_field(name="Thread ID", value=f"`{thread.id}`", inline=True)
        if thread.parent:
            embed.add_field(
                name="Parent",
                value=_format_channel_snapshot(thread.parent),
                inline=True,
            )
        if thread.owner:
            add_user_field(embed, thread.owner, label="Owner")
        if isinstance(thread.created_at, datetime):
            embed.add_field(
                name="Created At",
                value=format_datetime_with_relative(thread.created_at),
                inline=True,
            )
        embed.add_field(
            name="State",
            value=(
                f"Archived: {'Yes' if thread.archived else 'No'} / "
                f"Locked: {'Yes' if thread.locked else 'No'}"
            ),
            inline=False,
        )
        auto_archive_minutes = getattr(thread, "auto_archive_duration", None)
        if isinstance(auto_archive_minutes, int):
            embed.add_field(
                name="Auto Archive",
                value=f"{auto_archive_minutes}m",
                inline=True,
            )

        mod_id, reason = await find_audit_entry(
            thread.guild, discord.AuditLogAction.thread_create, thread.id
        )
        if mod_id is not None:
            embed.add_field(
                name="Created By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )

        await self._send_log(thread.guild, "thread_create", embed)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        """スレッド削除イベント。"""
        if not self._get_channels(thread.guild, "thread_delete"):
            return

        embed = create_event_embed("Thread Deleted", "thread_delete")
        embed.add_field(name="Name", value=thread.name, inline=True)
        embed.add_field(name="Thread ID", value=f"`{thread.id}`", inline=True)
        if thread.parent:
            embed.add_field(
                name="Parent",
                value=_format_channel_snapshot(thread.parent),
                inline=True,
            )
        if isinstance(thread.created_at, datetime):
            embed.add_field(
                name="Created At",
                value=format_datetime_with_relative(thread.created_at),
                inline=True,
            )
        mod_id, reason = await find_audit_entry(
            thread.guild, discord.AuditLogAction.thread_delete, thread.id
        )
        if mod_id is not None:
            embed.add_field(
                name="Deleted By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )

        await self._send_log(thread.guild, "thread_delete", embed)

    @commands.Cog.listener()
    async def on_thread_update(
        self, before: discord.Thread, after: discord.Thread
    ) -> None:
        """スレッド更新イベント。"""
        if not self._get_channels(after.guild, "thread_update"):
            return

        changes: list[str] = []
        if before.name != after.name:
            changes.append(f"**Name:** {before.name} → {after.name}")
        if before.archived != after.archived:
            changes.append(f"**Archived:** {before.archived} → {after.archived}")
        if before.locked != after.locked:
            changes.append(f"**Locked:** {before.locked} → {after.locked}")
        if before.slowmode_delay != after.slowmode_delay:
            changes.append(
                f"**Slowmode:** {before.slowmode_delay}s → {after.slowmode_delay}s"
            )
        before_auto_archive = getattr(before, "auto_archive_duration", None)
        after_auto_archive = getattr(after, "auto_archive_duration", None)
        if before_auto_archive != after_auto_archive:
            changes.append(
                f"**Auto Archive:** {before_auto_archive}m → {after_auto_archive}m"
            )

        if not changes:
            return

        embed = create_event_embed("Thread Updated", "thread_update")
        embed.add_field(
            name="Thread",
            value=_format_channel_snapshot(after),
            inline=True,
        )
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        mod_id, reason = await find_audit_entry(
            after.guild, discord.AuditLogAction.thread_update, after.id
        )
        if mod_id is not None:
            embed.add_field(
                name="Updated By",
                value=f"<@{mod_id}>\nID: `{mod_id}`",
                inline=True,
            )
        if reason:
            embed.add_field(
                name="Reason",
                value=truncate_content(reason, max_len=900),
                inline=False,
            )

        await self._send_log(after.guild, "thread_update", embed)

    # =====================================================================
    # Server Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_guild_update(
        self, before: discord.Guild, after: discord.Guild
    ) -> None:
        """サーバー設定変更イベント。"""
        if not self._get_channels(after, "server_update"):
            return

        changes: list[str] = []
        if before.name != after.name:
            changes.append(f"**Name:** {before.name} → {after.name}")
        if before.icon != after.icon:
            changes.append("**Icon:** changed")
        if before.banner != after.banner:
            changes.append("**Banner:** changed")
        if before.description != after.description:
            changes.append(
                f"**Description:** "
                f"{truncate_content(before.description or '(none)', 200)}"
                f" → "
                f"{truncate_content(after.description or '(none)', 200)}"
            )
        if before.verification_level != after.verification_level:
            changes.append(
                f"**Verification Level:** "
                f"{before.verification_level.name} → "
                f"{after.verification_level.name}"
            )
        if before.default_notifications != after.default_notifications:
            changes.append(
                f"**Notifications:** "
                f"{before.default_notifications.name} → "
                f"{after.default_notifications.name}"
            )
        if before.afk_channel != after.afk_channel:
            b_afk = (
                _format_channel_snapshot(before.afk_channel)
                if before.afk_channel
                else "(none)"
            )
            a_afk = (
                _format_channel_snapshot(after.afk_channel)
                if after.afk_channel
                else "(none)"
            )
            changes.append(f"**AFK Channel:** {b_afk} → {a_afk}")
        if before.system_channel != after.system_channel:
            b_sys = (
                _format_channel_snapshot(before.system_channel)
                if before.system_channel
                else "(none)"
            )
            a_sys = (
                _format_channel_snapshot(after.system_channel)
                if after.system_channel
                else "(none)"
            )
            changes.append(f"**System Channel:** {b_sys} → {a_sys}")
        if before.rules_channel != after.rules_channel:
            b_rules = (
                _format_channel_snapshot(before.rules_channel)
                if before.rules_channel
                else "(none)"
            )
            a_rules = (
                _format_channel_snapshot(after.rules_channel)
                if after.rules_channel
                else "(none)"
            )
            changes.append(f"**Rules Channel:** {b_rules} → {a_rules}")
        if before.public_updates_channel != after.public_updates_channel:
            b_updates = (
                _format_channel_snapshot(before.public_updates_channel)
                if before.public_updates_channel
                else "(none)"
            )
            a_updates = (
                _format_channel_snapshot(after.public_updates_channel)
                if after.public_updates_channel
                else "(none)"
            )
            changes.append(f"**Updates Channel:** {b_updates} → {a_updates}")
        if before.explicit_content_filter != after.explicit_content_filter:
            changes.append(
                f"**Explicit Content Filter:** "
                f"{before.explicit_content_filter.name} → "
                f"{after.explicit_content_filter.name}"
            )
        if before.mfa_level != after.mfa_level:
            changes.append(
                f"**MFA Level:** {before.mfa_level.name} → {after.mfa_level.name}"
            )
        if before.preferred_locale != after.preferred_locale:
            changes.append(
                "**Preferred Locale:** "
                f"{before.preferred_locale} → {after.preferred_locale}"
            )

        if not changes:
            return

        embed = create_event_embed("Server Updated", "server_update")
        embed.add_field(
            name="Server",
            value=f"{after.name}\nID: `{after.id}`",
            inline=True,
        )
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        mod_id, reason = await find_audit_entry(
            after,
            discord.AuditLogAction.guild_update,
            after.id,
            limit=8,
            window_seconds=10,
        )
        _add_audit_fields(embed, mod_id, reason, actor_label="Updated By")

        await self._send_log(after, "server_update", embed)

    # =====================================================================
    # Emoji Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self,
        guild: discord.Guild,
        before: tuple[discord.Emoji, ...],
        after: tuple[discord.Emoji, ...],
    ) -> None:
        """絵文字更新イベント。"""
        if not self._get_channels(guild, "emoji_update"):
            return

        before_set = {e.id: e for e in before}
        after_set = {e.id: e for e in after}

        changed_emojis: list[
            tuple[
                str,
                discord.Emoji,
                discord.AuditLogAction,
                str | None,
            ]
        ] = []
        changed_emojis.extend(
            ("Emoji Created", emoji, discord.AuditLogAction.emoji_create, None)
            for eid, emoji in after_set.items()
            if eid not in before_set
        )
        changed_emojis.extend(
            ("Emoji Deleted", emoji, discord.AuditLogAction.emoji_delete, None)
            for eid, emoji in before_set.items()
            if eid not in after_set
        )
        changed_emojis.extend(
            (
                "Emoji Updated",
                after_set[eid],
                discord.AuditLogAction.emoji_update,
                f"**Name:** {before_set[eid].name} → {after_set[eid].name}",
            )
            for eid in before_set
            if eid in after_set and before_set[eid].name != after_set[eid].name
        )

        for title, emoji, audit_action, details in changed_emojis:
            embed = create_event_embed(title, "emoji_update")
            embed.add_field(
                name="Emoji",
                value=f"{emoji} (`:{emoji.name}:`)\nID: `{emoji.id}`",
                inline=True,
            )
            embed.add_field(
                name="Settings",
                value=(
                    f"Animated: {'Yes' if emoji.animated else 'No'} / "
                    f"Managed: {'Yes' if emoji.managed else 'No'}"
                ),
                inline=False,
            )
            if details:
                embed.add_field(name="Changes", value=details, inline=False)

            mod_id, reason = await find_audit_entry(
                guild,
                audit_action,
                emoji.id,
                limit=8,
                window_seconds=10,
            )
            _add_audit_fields(embed, mod_id, reason, actor_label="Updated By")
            emoji_url = str(emoji.url)
            if emoji_url.startswith(("https://", "http://")):
                embed.set_thumbnail(url=emoji_url)

            await self._send_log(guild, "emoji_update", embed)


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する。"""
    await bot.add_cog(EventLogCog(bot))
    logger.info("EventLog cog loaded")
