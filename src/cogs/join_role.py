"""Join Role cog.

新規メンバー参加時に設定されたロールを自動付与し、
指定期間後に自動削除する。

仕組み:
  - on_member_join イベントで新規メンバーを検知
  - DB から有効な JoinRoleConfig を取得し、各ロールを付与
  - JoinRoleAssignment レコードを作成して追跡
  - 毎分バックグラウンドタスクで期限切れチェック → ロール削除
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import discord
from discord.ext import commands, tasks

from src.database.engine import async_session
from src.services.db_service import (
    claim_join_role_assignment,
    delete_join_role_assignment,
    get_enabled_join_role_configs,
    get_expired_join_role_assignments,
)

logger = logging.getLogger(__name__)


class JoinRoleCog(commands.Cog):
    """Join Role 機能を提供する Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Cog 読み込み時にバックグラウンドタスクを開始する。"""
        self._check_expired_roles.start()
        logger.info("JoinRole cog loaded, expiry check loop started")

    async def cog_unload(self) -> None:
        """Cog アンロード時にバックグラウンドタスクを停止する。"""
        if self._check_expired_roles.is_running():
            self._check_expired_roles.cancel()

    # ==========================================================================
    # イベントリスナー
    # ==========================================================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """新規メンバー参加時にロールを自動付与する。"""
        if member.bot:
            return

        guild_id = str(member.guild.id)

        async with async_session() as session:
            configs = await get_enabled_join_role_configs(session, guild_id)

        if not configs:
            return

        now = datetime.now(UTC)

        for config in configs:
            role = member.guild.get_role(int(config.role_id))
            if role is None:
                logger.warning(
                    "JoinRole: Role %s not found in guild %s",
                    config.role_id,
                    guild_id,
                )
                continue

            # DB レコードを先に作成 (claim) — 成功インスタンスのみ add_roles
            expires_at = now + timedelta(hours=config.duration_hours)
            try:
                async with async_session() as session:
                    assignment = await claim_join_role_assignment(
                        session,
                        guild_id=guild_id,
                        user_id=str(member.id),
                        role_id=config.role_id,
                        assigned_at=now,
                        expires_at=expires_at,
                    )
            except Exception:
                logger.exception(
                    "JoinRole: Failed to create assignment record for "
                    "member %s role %s in guild %s",
                    member.id,
                    config.role_id,
                    guild_id,
                )
                continue

            if not assignment:
                logger.info(
                    "JoinRole: Already processed by another instance: "
                    "member=%s role=%s guild=%s",
                    member.id,
                    config.role_id,
                    guild_id,
                )
                continue

            try:
                await member.add_roles(role, reason="JoinRole: 自動ロール付与")
            except discord.HTTPException:
                logger.exception(
                    "JoinRole: Failed to add role %s to member %s in guild %s",
                    config.role_id,
                    member.id,
                    guild_id,
                )

    # ==========================================================================
    # バックグラウンドタスク
    # ==========================================================================

    @tasks.loop(minutes=1)
    async def _check_expired_roles(self) -> None:
        """毎分実行: 期限切れロールを削除する。"""
        now = datetime.now(UTC)

        async with async_session() as session:
            expired = await get_expired_join_role_assignments(session, now)

        for assignment in expired:
            guild = self.bot.get_guild(int(assignment.guild_id))
            if guild is None:
                async with async_session() as session:
                    await delete_join_role_assignment(session, assignment.id)
                continue

            member = guild.get_member(int(assignment.user_id))
            if member is None:
                async with async_session() as session:
                    await delete_join_role_assignment(session, assignment.id)
                continue

            role = guild.get_role(int(assignment.role_id))
            if role is None:
                async with async_session() as session:
                    await delete_join_role_assignment(session, assignment.id)
                continue

            # DB レコードを先に削除 (アトミック) — 成功インスタンスのみ remove_roles
            async with async_session() as session:
                deleted = await delete_join_role_assignment(session, assignment.id)
            if not deleted:
                continue  # 別インスタンスが先に処理済み

            try:
                await member.remove_roles(role, reason="JoinRole: 期限切れロール削除")
            except discord.HTTPException:
                logger.exception(
                    "JoinRole: Failed to remove role %s from member %s in guild %s",
                    assignment.role_id,
                    assignment.user_id,
                    assignment.guild_id,
                )

    @_check_expired_roles.before_loop
    async def _before_check_expired_roles(self) -> None:
        """Bot の接続完了を待つ。"""
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する。"""
    await bot.add_cog(JoinRoleCog(bot))
