"""Chat Role cog.

指定チャンネルに累計 N 回投稿したメンバーにロールを自動付与する。
duration_hours が指定されていれば付与から N 時間後にロールを自動削除する
(再度 threshold まで投稿すれば再付与)。

仕組み:
  - on_message イベントで投稿を検知
  - 設定された (guild_id, channel_id) に該当する有効な ChatRoleConfig を取得
  - ChatRoleProgress を increment、threshold 到達でロール付与 + granted=True
  - 毎分バックグラウンドタスクで期限切れチェック → ロール削除 + granted=False
  - config.created_at より前の投稿はカウント対象外
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import discord
from discord.ext import commands, tasks

from src.database.engine import async_session
from src.services.db_service import (
    get_enabled_chat_role_channel_ids,
    get_enabled_chat_role_configs_for_channel,
    get_expired_chat_role_progress,
    increment_chat_role_progress,
    mark_chat_role_progress_expired,
    mark_chat_role_progress_granted,
)

logger = logging.getLogger(__name__)


class ChatRoleCog(commands.Cog):
    """Chat Role 機能を提供する Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # 有効な ChatRoleConfig を持つチャンネル ID のキャッシュ。
        # on_message ホットパスで DB 問い合わせを回避する用途。None は
        # 「未初期化なので DB にフォールバック」を意味する。
        # 1分ごとのバックグラウンドタスクで再構築するため、Web 管理画面での
        # 変更は最大 60 秒で反映される。
        self._chatrole_channels: set[str] | None = None

    async def cog_load(self) -> None:
        """Cog 読み込み時にバックグラウンドタスクを開始する。"""
        self._check_expired_roles.start()
        logger.info("ChatRole cog loaded, expiry check loop started")

    async def cog_unload(self) -> None:
        """Cog アンロード時にバックグラウンドタスクを停止する。"""
        if self._check_expired_roles.is_running():
            self._check_expired_roles.cancel()

    # ==========================================================================
    # イベントリスナー
    # ==========================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """メッセージ投稿時に ChatRole の進捗を更新する。"""
        if not message.guild or not message.author:
            return
        if message.author.bot:
            return
        if message.type != discord.MessageType.default:
            return

        member = message.author
        if not isinstance(member, discord.Member):
            return

        channel_id = str(message.channel.id)

        # ホットパス短絡: ChatRole 対象チャンネルでない場合は DB 問い合わせなし。
        if (
            self._chatrole_channels is not None
            and channel_id not in self._chatrole_channels
        ):
            return

        guild_id = str(message.guild.id)

        async with async_session() as session:
            configs = await get_enabled_chat_role_configs_for_channel(
                session, guild_id, channel_id
            )
        if not configs:
            return

        for config in configs:
            if message.created_at < config.created_at:
                continue

            async with async_session() as session:
                progress = await increment_chat_role_progress(
                    session, config.id, str(member.id)
                )

            if progress is None:
                continue  # 既に granted=True (DB 上で更新スキップ)
            if progress.count < config.threshold:
                continue

            role = message.guild.get_role(int(config.role_id))
            if role is None:
                logger.warning(
                    "ChatRole: Role %s not found in guild %s",
                    config.role_id,
                    guild_id,
                )
                continue

            now = datetime.now(UTC)
            expires_at: datetime | None = (
                now + timedelta(hours=config.duration_hours)
                if config.duration_hours is not None
                else None
            )

            async with async_session() as session:
                claimed = await mark_chat_role_progress_granted(
                    session,
                    progress.id,
                    granted_at=now,
                    expires_at=expires_at,
                )
            if not claimed:
                continue

            try:
                await member.add_roles(role, reason="ChatRole: 投稿ロール付与")
            except discord.HTTPException:
                logger.exception(
                    "ChatRole: Failed to add role %s to member %s in guild %s",
                    config.role_id,
                    member.id,
                    guild_id,
                )

    # ==========================================================================
    # バックグラウンドタスク
    # ==========================================================================

    @tasks.loop(minutes=1)
    async def _check_expired_roles(self) -> None:
        """毎分実行: 期限切れロールの削除 + チャンネルキャッシュの更新。

        Web 管理画面での設定変更はこのタスクの周期 (最大 60 秒) で反映される。
        """
        now = datetime.now(UTC)

        async with async_session() as session:
            self._chatrole_channels = await get_enabled_chat_role_channel_ids(session)
            expired = await get_expired_chat_role_progress(session, now)

        for progress, config in expired:
            guild = self.bot.get_guild(int(config.guild_id))
            if guild is None:
                async with async_session() as session:
                    await mark_chat_role_progress_expired(session, progress.id)
                continue

            member = guild.get_member(int(progress.user_id))
            if member is None:
                async with async_session() as session:
                    await mark_chat_role_progress_expired(session, progress.id)
                continue

            role = guild.get_role(int(config.role_id))
            if role is None:
                async with async_session() as session:
                    await mark_chat_role_progress_expired(session, progress.id)
                continue

            async with async_session() as session:
                claimed = await mark_chat_role_progress_expired(session, progress.id)
            if not claimed:
                continue

            try:
                await member.remove_roles(role, reason="ChatRole: 期限切れロール削除")
            except discord.HTTPException:
                logger.exception(
                    "ChatRole: Failed to remove role %s from member %s in guild %s",
                    config.role_id,
                    progress.user_id,
                    config.guild_id,
                )

    @_check_expired_roles.before_loop
    async def _before_check_expired_roles(self) -> None:
        """Bot の接続完了を待つ。"""
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録し、チャンネルキャッシュを初期化する。"""
    cog = ChatRoleCog(bot)
    await bot.add_cog(cog)

    try:
        async with async_session() as session:
            cog._chatrole_channels = await get_enabled_chat_role_channel_ids(session)
    except Exception:
        logger.exception("Failed to load chatrole channel cache")
