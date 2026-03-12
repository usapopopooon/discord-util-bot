"""Event Log cog.

特定の Discord イベントを指定チャンネルにログとして送信する。

対応イベント:
  - message_delete: メッセージ削除
  - message_edit: メッセージ編集
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
  - voice_state: ボイスチャンネル参加/退出/移動

仕組み:
  - 60 秒ごとに DB から有効な設定をキャッシュ
  - 各イベントリスナーでキャッシュを参照し、対応チャンネルに Embed 送信
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import discord
from discord.ext import commands, tasks

from src.database.engine import async_session
from src.services.db_service import get_enabled_event_log_configs

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


# イベントタイプごとの Embed カラー
_COLORS: dict[str, int] = {
    "message_delete": 0xFF0000,
    "message_edit": 0xFFA500,
    "member_join": 0x00FF00,
    "member_leave": 0xFF0000,
    "member_kick": 0xFFA500,
    "member_ban": 0xFF0000,
    "member_unban": 0x00FF00,
    "member_timeout": 0xFFFF00,
    "role_change": 0xFFA500,
    "nickname_change": 0x3498DB,
    "channel_create": 0x00FF00,
    "channel_delete": 0xFF0000,
    "voice_state": 0x3498DB,
}


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

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        """招待作成時にキャッシュを更新する。"""
        if invite.guild:
            guild_id = invite.guild.id
            if guild_id not in self._invite_cache:
                self._invite_cache[guild_id] = {}
            self._invite_cache[guild_id][invite.code] = _InviteData(
                code=invite.code,
                uses=invite.uses or 0,
                inviter_id=invite.inviter.id if invite.inviter else None,
                inviter_name=invite.inviter.name if invite.inviter else None,
            )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        """招待削除時にキャッシュを更新する。"""
        if invite.guild:
            guild_id = invite.guild.id
            self._invite_cache.get(guild_id, {}).pop(invite.code, None)

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

        content = message.content or "(empty)"
        if len(content) > 1024:
            content = content[:1021] + "..."

        # Audit log から削除した人を取得
        # 自分で削除した場合は audit log にエントリが作られないため None になる
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

        embed = discord.Embed(
            title="Message Deleted",
            color=_COLORS["message_delete"],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="Author",
            value=f"<@{message.author.id}> ({message.author.id})",
            inline=True,
        )
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
        if message.author.display_avatar:
            embed.set_thumbnail(url=message.author.display_avatar.url)

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

        before_content = before.content or "(empty)"
        after_content = after.content or "(empty)"
        if len(before_content) > 1024:
            before_content = before_content[:1021] + "..."
        if len(after_content) > 1024:
            after_content = after_content[:1021] + "..."

        embed = discord.Embed(
            title="Message Edited",
            color=_COLORS["message_edit"],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="Author",
            value=f"<@{after.author.id}> ({after.author.id})",
            inline=True,
        )
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
        if after.author.display_avatar:
            embed.set_thumbnail(url=after.author.display_avatar.url)

        await self._send_log(after.guild, "message_edit", embed)

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

        embed = discord.Embed(
            title="Member Joined",
            color=_COLORS["member_join"],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="User",
            value=f"<@{member.id}> ({member.id})",
            inline=True,
        )
        embed.add_field(
            name="Account Age",
            value=f"{days} days",
            inline=True,
        )
        embed.add_field(
            name="Account Created",
            value=member.created_at.strftime("%Y-%m-%d %H:%M UTC"),
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

        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

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
        try:
            async for entry in guild.audit_logs(
                limit=5, action=discord.AuditLogAction.kick
            ):
                if (
                    entry.target
                    and entry.target.id == member.id
                    and entry.created_at
                    and (datetime.now(UTC) - entry.created_at).total_seconds() < 5
                ):
                    mod_id = entry.user.id if entry.user else None
                    return (mod_id, entry.reason)
        except (discord.Forbidden, discord.HTTPException):
            pass
        return None

    async def _send_kick_log(
        self,
        member: discord.Member,
        kick_info: tuple[int | None, str | None],
    ) -> None:
        """Kick ログ Embed を送信する。"""
        mod_id, reason = kick_info

        embed = discord.Embed(
            title="Member Kicked",
            color=_COLORS["member_kick"],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="User",
            value=f"<@{member.id}> ({member.id})",
            inline=True,
        )
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
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        await self._send_log(member.guild, "member_kick", embed)

    async def _send_leave_log(self, member: discord.Member) -> None:
        """Leave ログ Embed を送信する。"""
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        roles_str = ", ".join(roles) if roles else "None"
        if len(roles_str) > 1024:
            roles_str = roles_str[:1021] + "..."

        embed = discord.Embed(
            title="Member Left",
            color=_COLORS["member_leave"],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="User",
            value=f"<@{member.id}> ({member.id})",
            inline=True,
        )
        if member.joined_at:
            embed.add_field(
                name="Joined At",
                value=member.joined_at.strftime("%Y-%m-%d %H:%M UTC"),
                inline=True,
            )
        embed.add_field(name="Roles", value=roles_str, inline=False)
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        await self._send_log(member.guild, "member_leave", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        """メンバー BAN イベント。"""
        if user.bot:
            return
        if not self._get_channels(guild, "member_ban"):
            return

        reason: str | None = None
        mod_id: int | None = None

        # Audit log から BAN 実行者と理由を取得
        try:
            async for entry in guild.audit_logs(
                limit=5, action=discord.AuditLogAction.ban
            ):
                if (
                    entry.target
                    and entry.target.id == user.id
                    and entry.created_at
                    and (datetime.now(UTC) - entry.created_at).total_seconds() < 5
                ):
                    mod_id = entry.user.id if entry.user else None
                    reason = entry.reason
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        # Audit log で取得できなかった場合、fetch_ban から理由だけ取得
        if reason is None:
            try:
                ban_entry = await guild.fetch_ban(user)
                reason = ban_entry.reason
            except (discord.NotFound, discord.HTTPException):
                pass

        embed = discord.Embed(
            title="Member Banned",
            color=_COLORS["member_ban"],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="User",
            value=f"<@{user.id}> ({user.id})",
            inline=True,
        )
        if mod_id:
            embed.add_field(
                name="Banned By",
                value=f"<@{mod_id}>",
                inline=True,
            )
        embed.add_field(
            name="Reason", value=reason or "No reason provided", inline=False
        )
        if user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)

        await self._send_log(guild, "member_ban", embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        """メンバー BAN 解除イベント。"""
        if user.bot:
            return
        if not self._get_channels(guild, "member_unban"):
            return

        # Audit log から解除した人を取得
        mod_id: int | None = None
        try:
            async for entry in guild.audit_logs(
                limit=5, action=discord.AuditLogAction.unban
            ):
                if (
                    entry.target
                    and entry.target.id == user.id
                    and entry.created_at
                    and (datetime.now(UTC) - entry.created_at).total_seconds() < 5
                ):
                    mod_id = entry.user.id if entry.user else None
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        embed = discord.Embed(
            title="Member Unbanned",
            color=_COLORS["member_unban"],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="User",
            value=f"<@{user.id}> ({user.id})",
            inline=True,
        )
        if mod_id:
            embed.add_field(
                name="Unbanned By",
                value=f"<@{mod_id}>",
                inline=True,
            )
        if user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)

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
        until_str = until.strftime("%Y-%m-%d %H:%M UTC") if until else "Unknown"

        # Audit log からモデレーターと理由を取得
        mod_id: int | None = None
        reason: str | None = None
        try:
            async for entry in member.guild.audit_logs(
                limit=5, action=discord.AuditLogAction.member_update
            ):
                if (
                    entry.target
                    and entry.target.id == member.id
                    and entry.created_at
                    and (datetime.now(UTC) - entry.created_at).total_seconds() < 5
                ):
                    mod_id = entry.user.id if entry.user else None
                    reason = entry.reason
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        embed = discord.Embed(
            title="Member Timed Out",
            color=_COLORS["member_timeout"],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="User",
            value=f"<@{member.id}> ({member.id})",
            inline=True,
        )
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
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

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

        embed = discord.Embed(
            title="Member Roles Updated",
            color=_COLORS["role_change"],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="User",
            value=f"<@{after.id}> ({after.id})",
            inline=True,
        )
        embed.add_field(
            name="Changes",
            value="\n".join(changes),
            inline=False,
        )
        if after.display_avatar:
            embed.set_thumbnail(url=after.display_avatar.url)

        await self._send_log(after.guild, "role_change", embed)

    async def _handle_nickname_change(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        """ニックネーム変更ログを送信する。"""
        if not self._get_channels(after.guild, "nickname_change"):
            return

        embed = discord.Embed(
            title="Nickname Changed",
            color=_COLORS["nickname_change"],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="User",
            value=f"<@{after.id}> ({after.id})",
            inline=True,
        )
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
        if after.display_avatar:
            embed.set_thumbnail(url=after.display_avatar.url)

        await self._send_log(after.guild, "nickname_change", embed)

    # =====================================================================
    # Channel Events
    # =====================================================================

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """チャンネル作成イベント。"""
        if not self._get_channels(channel.guild, "channel_create"):
            return

        embed = discord.Embed(
            title="Channel Created",
            color=_COLORS["channel_create"],
            timestamp=datetime.now(UTC),
        )
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

        embed = discord.Embed(
            title="Channel Deleted",
            color=_COLORS["channel_delete"],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Name", value=channel.name, inline=True)
        embed.add_field(
            name="Type",
            value=str(channel.type).replace("_", " ").title(),
            inline=True,
        )
        if channel.category:
            embed.add_field(name="Category", value=channel.category.name, inline=True)

        await self._send_log(channel.guild, "channel_delete", embed)

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

        embed = discord.Embed(
            title=action,
            color=_COLORS["voice_state"],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="User",
            value=f"<@{member.id}> ({member.id})",
            inline=True,
        )
        embed.add_field(name="Channel", value=detail, inline=True)
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        await self._send_log(member.guild, "voice_state", embed)


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する。"""
    await bot.add_cog(EventLogCog(bot))
    logger.info("EventLog cog loaded")
