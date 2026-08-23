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

from src.cogs._eventlog_embeds import (
    InviteDetails,
    channel_embed,
    channel_updated_embed,
    emoji_embed,
    guild_updated_embed,
    invite_created_embed,
    invite_deleted_embed,
    member_joined_embed,
    member_left_embed,
    member_roles_changed_embed,
    message_deleted_embed,
    message_edited_embed,
    messages_purged_embed,
    moderated_member_embed,
    nickname_changed_embed,
    role_embed,
    role_updated_embed,
    thread_embed,
    thread_updated_embed,
    voice_state_embed,
)
from src.cogs._eventlog_helpers import find_audit_entry
from src.database.engine import async_session
from src.services.common_service import get_enabled_event_log_configs

logger = logging.getLogger(__name__)


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
        actor_id, reason = await find_audit_entry(
            message.guild,
            discord.AuditLogAction.message_delete,
            message.author.id,
        )
        await self._send_log(
            message.guild,
            "message_delete",
            message_deleted_embed(message, actor_id, reason),
        )

    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        """メッセージ編集イベント。"""
        if not after.guild or after.author.bot:
            return
        if not self._get_channels(after.guild, "message_edit"):
            return
        embed = message_edited_embed(before, after)
        if embed is not None:
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
        await self._send_log(
            guild,
            "message_purge",
            messages_purged_embed(messages, deleted_by_id, deletion_reason),
        )

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
        invite_info = await self._detect_used_invite(member.guild)
        await self._send_log(
            member.guild,
            "member_join",
            member_joined_embed(member, invite_info),
        )

    async def _detect_used_invite(self, guild: discord.Guild) -> InviteDetails | None:
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
                    return InviteDetails(
                        kind="vanity",
                        code=vanity.code,
                        uses=vanity.uses,
                    )
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
            return InviteDetails(
                kind="invite",
                code=used_invite.code,
                inviter_id=used_invite.inviter_id,
                inviter_total_uses=total_uses,
            )
        return InviteDetails(kind="invite", code=used_invite.code)

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
        await self._send_log(
            member.guild,
            "member_kick",
            moderated_member_embed(
                "メンバーKick",
                "member_kick",
                member,
                mod_id,
                reason,
            ),
        )

    async def _send_leave_log(self, member: discord.Member) -> None:
        """Leave ログ Embed を送信する。"""
        await self._send_log(
            member.guild,
            "member_leave",
            member_left_embed(member),
        )

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

        await self._send_log(
            guild,
            "member_ban",
            moderated_member_embed(
                "メンバーBAN",
                "member_ban",
                user,
                mod_id,
                reason,
            ),
        )

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

        await self._send_log(
            guild,
            "member_unban",
            moderated_member_embed(
                "BAN解除",
                "member_unban",
                user,
                mod_id,
                reason,
            ),
        )

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

    async def _handle_timeout(self, member: discord.Member) -> None:
        """タイムアウトログを送信する。"""
        if not self._get_channels(member.guild, "member_timeout"):
            return

        until = member.timed_out_until
        mod_id, reason = await find_audit_entry(
            member.guild, discord.AuditLogAction.member_update, member.id
        )
        await self._send_log(
            member.guild,
            "member_timeout",
            moderated_member_embed(
                "メンバータイムアウト",
                "member_timeout",
                member,
                mod_id,
                reason,
                until=until,
            ),
        )

    async def _handle_role_change(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        """ロール変更ログを送信する。"""
        if not self._get_channels(after.guild, "role_change"):
            return

        mod_id, reason = await find_audit_entry(
            after.guild, discord.AuditLogAction.member_role_update, after.id
        )
        embed = member_roles_changed_embed(before, after, mod_id, reason)
        if embed is not None:
            await self._send_log(after.guild, "role_change", embed)

    async def _handle_nickname_change(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        """ニックネーム変更ログを送信する。"""
        if not self._get_channels(after.guild, "nickname_change"):
            return

        mod_id, reason = await find_audit_entry(
            after.guild, discord.AuditLogAction.member_update, after.id
        )
        embed = nickname_changed_embed(before, after, mod_id, reason)
        if embed is not None:
            await self._send_log(after.guild, "nickname_change", embed)

    async def _handle_timeout_removed(self, member: discord.Member) -> None:
        """タイムアウト解除ログを送信する。"""
        if not self._get_channels(member.guild, "member_timeout"):
            return
        mod_id, reason = await find_audit_entry(
            member.guild, discord.AuditLogAction.member_update, member.id
        )
        await self._send_log(
            member.guild,
            "member_timeout",
            moderated_member_embed(
                "タイムアウト解除",
                "member_timeout",
                member,
                mod_id,
                reason,
            ),
        )

    # =====================================================================
    # Channel Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """チャンネル作成イベント。"""
        if not self._get_channels(channel.guild, "channel_create"):
            return
        mod_id, reason = await find_audit_entry(
            channel.guild, discord.AuditLogAction.channel_create, channel.id
        )
        await self._send_log(
            channel.guild,
            "channel_create",
            channel_embed(
                "チャンネル作成",
                "channel_create",
                channel,
                mod_id,
                reason,
            ),
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """チャンネル削除イベント。"""
        if not self._get_channels(channel.guild, "channel_delete"):
            return

        mod_id, reason = await find_audit_entry(
            channel.guild, discord.AuditLogAction.channel_delete, channel.id
        )
        await self._send_log(
            channel.guild,
            "channel_delete",
            channel_embed(
                "チャンネル削除",
                "channel_delete",
                channel,
                mod_id,
                reason,
            ),
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        """チャンネル更新イベント。"""
        if not self._get_channels(after.guild, "channel_update"):
            return
        mod_id, reason = await find_audit_entry(
            after.guild, discord.AuditLogAction.channel_update, after.id
        )
        embed = channel_updated_embed(before, after, mod_id, reason)
        if embed is not None:
            await self._send_log(after.guild, "channel_update", embed)

    # =====================================================================
    # Role Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        """ロール作成イベント。"""
        if not self._get_channels(role.guild, "role_create"):
            return
        mod_id, reason = await find_audit_entry(
            role.guild, discord.AuditLogAction.role_create, role.id
        )
        await self._send_log(
            role.guild,
            "role_create",
            role_embed("ロール作成", "role_create", role, mod_id, reason),
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """ロール削除イベント。"""
        if not self._get_channels(role.guild, "role_delete"):
            return

        mod_id, reason = await find_audit_entry(
            role.guild, discord.AuditLogAction.role_delete, role.id
        )
        await self._send_log(
            role.guild,
            "role_delete",
            role_embed("ロール削除", "role_delete", role, mod_id, reason),
        )

    @commands.Cog.listener()
    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> None:
        """ロール更新イベント。"""
        if not self._get_channels(after.guild, "role_update"):
            return
        mod_id, reason = await find_audit_entry(
            after.guild, discord.AuditLogAction.role_update, after.id
        )
        embed = role_updated_embed(before, after, mod_id, reason)
        if embed is not None:
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
        embed = voice_state_embed(member, before, after)
        if embed is not None:
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
        await self._send_log(guild, "invite_create", invite_created_embed(invite))

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

        mod_id, reason = await _find_invite_audit_entry(guild, invite.code)
        await self._send_log(
            guild,
            "invite_delete",
            invite_deleted_embed(invite, mod_id, reason),
        )

    # =====================================================================
    # Thread Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        """スレッド作成イベント。"""
        if not self._get_channels(thread.guild, "thread_create"):
            return
        mod_id, reason = await find_audit_entry(
            thread.guild, discord.AuditLogAction.thread_create, thread.id
        )
        await self._send_log(
            thread.guild,
            "thread_create",
            thread_embed(
                "スレッド作成",
                "thread_create",
                thread,
                mod_id,
                reason,
            ),
        )

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        """スレッド削除イベント。"""
        if not self._get_channels(thread.guild, "thread_delete"):
            return

        mod_id, reason = await find_audit_entry(
            thread.guild, discord.AuditLogAction.thread_delete, thread.id
        )
        await self._send_log(
            thread.guild,
            "thread_delete",
            thread_embed(
                "スレッド削除",
                "thread_delete",
                thread,
                mod_id,
                reason,
            ),
        )

    @commands.Cog.listener()
    async def on_thread_update(
        self, before: discord.Thread, after: discord.Thread
    ) -> None:
        """スレッド更新イベント。"""
        if not self._get_channels(after.guild, "thread_update"):
            return

        mod_id, reason = await find_audit_entry(
            after.guild, discord.AuditLogAction.thread_update, after.id
        )
        embed = thread_updated_embed(before, after, mod_id, reason)
        if embed is not None:
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
        mod_id, reason = await find_audit_entry(
            after,
            discord.AuditLogAction.guild_update,
            after.id,
            limit=8,
            window_seconds=10,
        )
        embed = guild_updated_embed(before, after, mod_id, reason)
        if embed is not None:
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
            ("絵文字作成", emoji, discord.AuditLogAction.emoji_create, None)
            for eid, emoji in after_set.items()
            if eid not in before_set
        )
        changed_emojis.extend(
            ("絵文字削除", emoji, discord.AuditLogAction.emoji_delete, None)
            for eid, emoji in before_set.items()
            if eid not in after_set
        )
        changed_emojis.extend(
            (
                "絵文字更新",
                after_set[eid],
                discord.AuditLogAction.emoji_update,
                f"**名前:** {before_set[eid].name} -> {after_set[eid].name}",
            )
            for eid in before_set
            if eid in after_set and before_set[eid].name != after_set[eid].name
        )

        for title, emoji, audit_action, details in changed_emojis:
            mod_id, reason = await find_audit_entry(
                guild,
                audit_action,
                emoji.id,
                limit=8,
                window_seconds=10,
            )
            await self._send_log(
                guild,
                "emoji_update",
                emoji_embed(title, emoji, details, mod_id, reason),
            )


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する。"""
    await bot.add_cog(EventLogCog(bot))
    logger.info("EventLog cog loaded")
