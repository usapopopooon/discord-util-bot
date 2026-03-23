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
from datetime import UTC, datetime

import discord
from discord.ext import commands, tasks

from src.cogs._eventlog_helpers import (
    add_user_field,
    create_event_embed,
    find_audit_entry,
    set_user_thumbnail,
    truncate_content,
)
from src.database.engine import async_session
from src.services.db_service import get_enabled_event_log_configs
from src.utils import format_datetime

logger = logging.getLogger(__name__)


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
        channel_ids = self._get_channels(guild, event_type)
        for channel_id in channel_ids:
            channel = guild.get_channel(int(channel_id))
            if channel and isinstance(channel, discord.TextChannel):
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
        try:
            async for entry in message.guild.audit_logs(
                limit=5, action=discord.AuditLogAction.message_delete
            ):
                extra_channel = getattr(entry.extra, "channel", None)
                if (
                    entry.target
                    and entry.target.id == message.author.id
                    and extra_channel
                    and extra_channel.id == message.channel.id
                    and entry.created_at
                    and (datetime.now(UTC) - entry.created_at).total_seconds() < 5
                ):
                    deleted_by_id = entry.user.id if entry.user else None
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        embed = create_event_embed("Message Deleted", "message_delete")
        add_user_field(embed, message.author, label="Author")
        embed.add_field(
            name="Channel",
            value=f"<#{message.channel.id}>",
            inline=True,
        )
        if deleted_by_id and deleted_by_id != message.author.id:
            embed.add_field(
                name="Deleted By",
                value=f"<@{deleted_by_id}>",
                inline=True,
            )
        embed.add_field(name="Content", value=content, inline=False)
        set_user_thumbnail(embed, message.author)

        await self._send_log(message.guild, "message_delete", embed)

    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        """メッセージ編集イベント。"""
        if not after.guild or after.author.bot:
            return
        if before.content == after.content:
            return
        if not self._get_channels(after.guild, "message_edit"):
            return

        before_content = truncate_content(before.content or "(empty)")
        after_content = truncate_content(after.content or "(empty)")

        embed = create_event_embed("Message Edited", "message_edit")
        add_user_field(embed, after.author, label="Author")
        embed.add_field(
            name="Channel",
            value=f"<#{after.channel.id}>",
            inline=True,
        )
        embed.add_field(name="Before", value=before_content, inline=False)
        embed.add_field(name="After", value=after_content, inline=False)
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
        embed.add_field(name="Channel", value=f"<#{channel.id}>", inline=True)
        embed.add_field(name="Count", value=str(count), inline=True)
        if authors_str:
            embed.add_field(name="Authors", value=authors_str, inline=False)

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
            value=format_datetime(member.created_at),
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
            if old_data and new_data.uses > old_data.uses:
                used_invite = new_data

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
                    return "Vanity URL"
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
                value=f"<@{mod_id}>",
                inline=True,
            )
        embed.add_field(
            name="Reason",
            value=reason or "No reason provided",
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
                value=format_datetime(member.joined_at),
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
                value=f"<@{mod_id}>",
                inline=True,
            )
        embed.add_field(
            name="Reason", value=reason or "No reason provided", inline=False
        )
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
        mod_id, _ = await find_audit_entry(guild, discord.AuditLogAction.unban, user.id)

        embed = create_event_embed("Member Unbanned", "member_unban")
        add_user_field(embed, user)
        if mod_id:
            embed.add_field(
                name="Unbanned By",
                value=f"<@{mod_id}>",
                inline=True,
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

        # ロール変更
        if before.roles != after.roles:
            await self._handle_role_change(before, after)

        # ニックネーム変更
        if before.nick != after.nick:
            await self._handle_nickname_change(before, after)

    async def _handle_timeout(self, member: discord.Member) -> None:
        """タイムアウトログを送信する。"""
        if not self._get_channels(member.guild, "member_timeout"):
            return

        until = member.timed_out_until
        until_str = format_datetime(until, fallback="Unknown")

        # Audit log からモデレーターと理由を取得
        mod_id, reason = await find_audit_entry(
            member.guild, discord.AuditLogAction.member_update, member.id
        )

        embed = create_event_embed("Member Timed Out", "member_timeout")
        add_user_field(embed, member)
        if mod_id:
            embed.add_field(
                name="Timed Out By",
                value=f"<@{mod_id}>",
                inline=True,
            )
        embed.add_field(name="Until", value=until_str, inline=True)
        embed.add_field(
            name="Reason",
            value=reason or "No reason provided",
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

        if not changes:
            return

        embed = create_event_embed("Channel Updated", "channel_update")
        embed.add_field(
            name="Channel", value=f"<#{after.id}> ({after.name})", inline=True
        )
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)

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
        if role.color.value:
            embed.add_field(name="Color", value=f"#{role.color.value:06X}", inline=True)

        await self._send_log(role.guild, "role_create", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """ロール削除イベント。"""
        if not self._get_channels(role.guild, "role_delete"):
            return

        embed = create_event_embed("Role Deleted", "role_delete")
        embed.add_field(name="Role", value=role.name, inline=True)
        if role.color.value:
            embed.add_field(name="Color", value=f"#{role.color.value:06X}", inline=True)
        embed.add_field(name="Members", value=str(len(role.members)), inline=True)

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
            changes.append("**Permissions:** changed")

        if not changes:
            return

        embed = create_event_embed("Role Updated", "role_update")
        embed.add_field(
            name="Role", value=f"{after.mention} ({after.name})", inline=True
        )
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)

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
            detail = f"<#{after.channel.id}>"
        # Leave
        elif before.channel is not None and after.channel is None:
            action = "Left Voice Channel"
            detail = f"<#{before.channel.id}>"
        # Move
        elif (
            before.channel is not None
            and after.channel is not None
            and before.channel != after.channel
        ):
            action = "Moved Voice Channel"
            detail = f"<#{before.channel.id}> → <#{after.channel.id}>"
        else:
            # mute/deaf 等の状態変更はスキップ
            return

        embed = create_event_embed(action, "voice_state")
        add_user_field(embed, member)
        embed.add_field(name="Channel", value=detail, inline=True)
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
        if invite.inviter:
            add_user_field(embed, invite.inviter, label="Created By")
        if invite.channel:
            embed.add_field(
                name="Channel",
                value=f"<#{invite.channel.id}>",
                inline=True,
            )
        if invite.max_age:
            if invite.max_age >= 3600:
                age_str = f"{invite.max_age // 3600}h"
            elif invite.max_age >= 60:
                age_str = f"{invite.max_age // 60}m"
            else:
                age_str = f"{invite.max_age}s"
            embed.add_field(name="Expires", value=age_str, inline=True)
        else:
            embed.add_field(name="Expires", value="Never", inline=True)
        if invite.max_uses:
            embed.add_field(name="Max Uses", value=str(invite.max_uses), inline=True)

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
        if invite.channel:
            embed.add_field(
                name="Channel",
                value=f"<#{invite.channel.id}>",
                inline=True,
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
        if thread.parent:
            embed.add_field(
                name="Parent",
                value=f"<#{thread.parent.id}>",
                inline=True,
            )
        if thread.owner:
            add_user_field(embed, thread.owner, label="Created By")

        await self._send_log(thread.guild, "thread_create", embed)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        """スレッド削除イベント。"""
        if not self._get_channels(thread.guild, "thread_delete"):
            return

        embed = create_event_embed("Thread Deleted", "thread_delete")
        embed.add_field(name="Name", value=thread.name, inline=True)
        if thread.parent:
            embed.add_field(
                name="Parent",
                value=f"<#{thread.parent.id}>",
                inline=True,
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

        if not changes:
            return

        embed = create_event_embed("Thread Updated", "thread_update")
        embed.add_field(name="Thread", value=f"<#{after.id}>", inline=True)
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)

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
            b_afk = f"<#{before.afk_channel.id}>" if before.afk_channel else "(none)"
            a_afk = f"<#{after.afk_channel.id}>" if after.afk_channel else "(none)"
            changes.append(f"**AFK Channel:** {b_afk} → {a_afk}")
        if before.system_channel != after.system_channel:
            b_sys = (
                f"<#{before.system_channel.id}>" if before.system_channel else "(none)"
            )
            a_sys = (
                f"<#{after.system_channel.id}>" if after.system_channel else "(none)"
            )
            changes.append(f"**System Channel:** {b_sys} → {a_sys}")

        if not changes:
            return

        embed = create_event_embed("Server Updated", "server_update")
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)

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

        changes: list[str] = []

        # Added
        for eid, emoji in after_set.items():
            if eid not in before_set:
                changes.append(f"+ {emoji} (`:{emoji.name}:`)")

        # Removed
        for eid, emoji in before_set.items():
            if eid not in after_set:
                changes.append(f"× `:{emoji.name}:`")

        # Renamed
        for eid in before_set:
            if eid in after_set and before_set[eid].name != after_set[eid].name:
                changes.append(
                    f"**Renamed:** `:{before_set[eid].name}:` → "
                    f"`:{after_set[eid].name}:`"
                )

        if not changes:
            return

        embed = create_event_embed("Emojis Updated", "emoji_update")
        embed.add_field(
            name="Changes",
            value=truncate_content("\n".join(changes)),
            inline=False,
        )

        await self._send_log(guild, "emoji_update", embed)


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する。"""
    await bot.add_cog(EventLogCog(bot))
    logger.info("EventLog cog loaded")
