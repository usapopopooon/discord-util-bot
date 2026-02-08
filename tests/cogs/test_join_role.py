"""Tests for JoinRoleCog (join role feature)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from src.cogs.join_role import JoinRoleCog

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog() -> JoinRoleCog:
    """Create a JoinRoleCog with a mock bot."""
    bot = MagicMock(spec=commands.Bot)
    bot.wait_until_ready = AsyncMock()
    return JoinRoleCog(bot)


def _make_member(
    *,
    user_id: int = 12345,
    guild_id: int = 789,
    is_bot: bool = False,
) -> MagicMock:
    """Create a mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.bot = is_bot
    member.guild = MagicMock()
    member.guild.id = guild_id
    member.guild.get_role = MagicMock()
    member.add_roles = AsyncMock()
    return member


def _make_config(
    *,
    config_id: int = 1,
    guild_id: str = "789",
    role_id: str = "111",
    duration_hours: int = 24,
    enabled: bool = True,
) -> MagicMock:
    """Create a mock JoinRoleConfig."""
    config = MagicMock()
    config.id = config_id
    config.guild_id = guild_id
    config.role_id = role_id
    config.duration_hours = duration_hours
    config.enabled = enabled
    return config


def _make_assignment(
    *,
    assignment_id: int = 1,
    guild_id: str = "789",
    user_id: str = "12345",
    role_id: str = "111",
    expires_at: datetime | None = None,
) -> MagicMock:
    """Create a mock JoinRoleAssignment."""
    assignment = MagicMock()
    assignment.id = assignment_id
    assignment.guild_id = guild_id
    assignment.user_id = user_id
    assignment.role_id = role_id
    assignment.expires_at = expires_at or datetime.now(UTC) - timedelta(minutes=1)
    return assignment


# ---------------------------------------------------------------------------
# TestOnMemberJoin
# ---------------------------------------------------------------------------


class TestOnMemberJoin:
    """on_member_join イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        """Bot 参加時はスキップ。"""
        cog = _make_cog()
        member = _make_member(is_bot=True)
        with patch("src.cogs.join_role.get_enabled_join_role_configs") as mock_get:
            await cog.on_member_join(member)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_config_no_action(self) -> None:
        """設定なしの場合はスキップ。"""
        cog = _make_cog()
        member = _make_member()
        with patch(
            "src.cogs.join_role.get_enabled_join_role_configs",
            return_value=[],
        ):
            await cog.on_member_join(member)
            member.add_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_assigns_role(self) -> None:
        """有効な設定がある場合はロールを付与する。"""
        cog = _make_cog()
        member = _make_member()
        role = MagicMock(spec=discord.Role)
        member.guild.get_role.return_value = role
        config = _make_config()

        with (
            patch(
                "src.cogs.join_role.get_enabled_join_role_configs",
                return_value=[config],
            ),
            patch(
                "src.cogs.join_role.create_join_role_assignment",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await cog.on_member_join(member)
            member.add_roles.assert_called_once_with(
                role, reason="JoinRole: 自動ロール付与"
            )
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_role_not_found(self) -> None:
        """ロールが見つからない場合はスキップ。"""
        cog = _make_cog()
        member = _make_member()
        member.guild.get_role.return_value = None
        config = _make_config()

        with (
            patch(
                "src.cogs.join_role.get_enabled_join_role_configs",
                return_value=[config],
            ),
            patch(
                "src.cogs.join_role.create_join_role_assignment",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await cog.on_member_join(member)
            member.add_roles.assert_not_called()
            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_roles_http_error(self) -> None:
        """ロール付与失敗時はスキップしてログ出力。"""
        cog = _make_cog()
        member = _make_member()
        role = MagicMock(spec=discord.Role)
        member.guild.get_role.return_value = role
        member.add_roles.side_effect = discord.HTTPException(MagicMock(), "error")
        config = _make_config()

        with (
            patch(
                "src.cogs.join_role.get_enabled_join_role_configs",
                return_value=[config],
            ),
            patch(
                "src.cogs.join_role.create_join_role_assignment",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await cog.on_member_join(member)
            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_configs(self) -> None:
        """複数の設定がある場合は全て付与する。"""
        cog = _make_cog()
        member = _make_member()
        role1 = MagicMock(spec=discord.Role)
        role2 = MagicMock(spec=discord.Role)
        member.guild.get_role.side_effect = [role1, role2]
        config1 = _make_config(config_id=1, role_id="111")
        config2 = _make_config(config_id=2, role_id="222")

        with (
            patch(
                "src.cogs.join_role.get_enabled_join_role_configs",
                return_value=[config1, config2],
            ),
            patch(
                "src.cogs.join_role.create_join_role_assignment",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await cog.on_member_join(member)
            assert member.add_roles.call_count == 2
            assert mock_create.call_count == 2


# ---------------------------------------------------------------------------
# TestCheckExpiredRoles
# ---------------------------------------------------------------------------


class TestCheckExpiredRoles:
    """_check_expired_roles バックグラウンドタスクのテスト。"""

    @pytest.mark.asyncio
    async def test_removes_expired_role(self) -> None:
        """期限切れロールを削除する。"""
        cog = _make_cog()
        member = MagicMock(spec=discord.Member)
        member.remove_roles = AsyncMock()
        role = MagicMock(spec=discord.Role)
        guild = MagicMock(spec=discord.Guild)
        guild.get_member.return_value = member
        guild.get_role.return_value = role
        cog.bot.get_guild.return_value = guild

        assignment = _make_assignment()

        with (
            patch(
                "src.cogs.join_role.get_expired_join_role_assignments",
                new_callable=AsyncMock,
                return_value=[assignment],
            ),
            patch(
                "src.cogs.join_role.delete_join_role_assignment",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_delete,
        ):
            await cog._check_expired_roles()
            member.remove_roles.assert_called_once_with(
                role, reason="JoinRole: 期限切れロール削除"
            )
            mock_delete.assert_called_once_with(
                mock_delete.call_args[0][0], assignment.id
            )

    @pytest.mark.asyncio
    async def test_guild_not_found(self) -> None:
        """ギルドが見つからない場合はレコードのみ削除。"""
        cog = _make_cog()
        cog.bot.get_guild.return_value = None

        assignment = _make_assignment()

        with (
            patch(
                "src.cogs.join_role.get_expired_join_role_assignments",
                new_callable=AsyncMock,
                return_value=[assignment],
            ),
            patch(
                "src.cogs.join_role.delete_join_role_assignment",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_delete,
        ):
            await cog._check_expired_roles()
            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_member_left(self) -> None:
        """メンバーが退出済みの場合はレコードのみ削除。"""
        cog = _make_cog()
        guild = MagicMock(spec=discord.Guild)
        guild.get_member.return_value = None
        cog.bot.get_guild.return_value = guild

        assignment = _make_assignment()

        with (
            patch(
                "src.cogs.join_role.get_expired_join_role_assignments",
                new_callable=AsyncMock,
                return_value=[assignment],
            ),
            patch(
                "src.cogs.join_role.delete_join_role_assignment",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_delete,
        ):
            await cog._check_expired_roles()
            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_role_already_removed(self) -> None:
        """ロールが既に削除されている場合はレコードのみ削除。"""
        cog = _make_cog()
        member = MagicMock(spec=discord.Member)
        guild = MagicMock(spec=discord.Guild)
        guild.get_member.return_value = member
        guild.get_role.return_value = None
        cog.bot.get_guild.return_value = guild

        assignment = _make_assignment()

        with (
            patch(
                "src.cogs.join_role.get_expired_join_role_assignments",
                new_callable=AsyncMock,
                return_value=[assignment],
            ),
            patch(
                "src.cogs.join_role.delete_join_role_assignment",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_delete,
        ):
            await cog._check_expired_roles()
            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_expired_assignments(self) -> None:
        """期限切れなしの場合は何もしない。"""
        cog = _make_cog()

        with (
            patch(
                "src.cogs.join_role.get_expired_join_role_assignments",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.cogs.join_role.delete_join_role_assignment",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            await cog._check_expired_roles()
            mock_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_roles_http_error(self) -> None:
        """ロール削除失敗時もレコードは削除する。"""
        cog = _make_cog()
        member = MagicMock(spec=discord.Member)
        member.remove_roles = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "error")
        )
        role = MagicMock(spec=discord.Role)
        guild = MagicMock(spec=discord.Guild)
        guild.get_member.return_value = member
        guild.get_role.return_value = role
        cog.bot.get_guild.return_value = guild

        assignment = _make_assignment()

        with (
            patch(
                "src.cogs.join_role.get_expired_join_role_assignments",
                new_callable=AsyncMock,
                return_value=[assignment],
            ),
            patch(
                "src.cogs.join_role.delete_join_role_assignment",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_delete,
        ):
            await cog._check_expired_roles()
            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_expired_same_member(self) -> None:
        """同一メンバーの複数ロールが期限切れの場合、全て削除。"""
        cog = _make_cog()
        member = MagicMock(spec=discord.Member)
        member.remove_roles = AsyncMock()
        role1 = MagicMock(spec=discord.Role)
        role2 = MagicMock(spec=discord.Role)
        guild = MagicMock(spec=discord.Guild)
        guild.get_member.return_value = member
        guild.get_role.side_effect = [role1, role2]
        cog.bot.get_guild.return_value = guild

        a1 = _make_assignment(assignment_id=1, role_id="111")
        a2 = _make_assignment(assignment_id=2, role_id="222")

        with (
            patch(
                "src.cogs.join_role.get_expired_join_role_assignments",
                new_callable=AsyncMock,
                return_value=[a1, a2],
            ),
            patch(
                "src.cogs.join_role.delete_join_role_assignment",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_delete,
        ):
            await cog._check_expired_roles()
            assert member.remove_roles.call_count == 2
            assert mock_delete.call_count == 2


# ---------------------------------------------------------------------------
# TestCogLifecycle
# ---------------------------------------------------------------------------


class TestCogLifecycle:
    """Cog のライフサイクルテスト。"""

    @pytest.mark.asyncio
    async def test_cog_load_starts_task(self) -> None:
        """cog_load でバックグラウンドタスクが開始される。"""
        cog = _make_cog()
        with patch.object(cog._check_expired_roles, "start") as mock_start:
            await cog.cog_load()
            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_cancels_task(self) -> None:
        """cog_unload でバックグラウンドタスクが停止される。"""
        cog = _make_cog()
        with (
            patch.object(cog._check_expired_roles, "is_running", return_value=True),
            patch.object(cog._check_expired_roles, "cancel") as mock_cancel,
        ):
            await cog.cog_unload()
            mock_cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_not_running(self) -> None:
        """タスク未実行時の cog_unload は cancel しない。"""
        cog = _make_cog()
        with (
            patch.object(cog._check_expired_roles, "is_running", return_value=False),
            patch.object(cog._check_expired_roles, "cancel") as mock_cancel,
        ):
            await cog.cog_unload()
            mock_cancel.assert_not_called()


# ---------------------------------------------------------------------------
# TestOnMemberJoinEdgeCases
# ---------------------------------------------------------------------------


class TestOnMemberJoinEdgeCases:
    """on_member_join の追加エッジケーステスト。"""

    @pytest.mark.asyncio
    async def test_assignment_creation_failure(self) -> None:
        """DB レコード作成失敗時もロール付与は完了している。"""
        cog = _make_cog()
        member = _make_member()
        role = MagicMock(spec=discord.Role)
        member.guild.get_role.return_value = role
        config = _make_config()

        with (
            patch(
                "src.cogs.join_role.get_enabled_join_role_configs",
                return_value=[config],
            ),
            patch(
                "src.cogs.join_role.create_join_role_assignment",
                new_callable=AsyncMock,
                side_effect=Exception("DB error"),
            ),
        ):
            await cog.on_member_join(member)
            # ロールは付与済み
            member.add_roles.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_configs_one_role_fails(self) -> None:
        """複数設定で一つのロール付与失敗時も他は成功する。"""
        cog = _make_cog()
        member = _make_member()
        role1 = MagicMock(spec=discord.Role)
        role2 = MagicMock(spec=discord.Role)
        member.guild.get_role.side_effect = [role1, role2]
        # 最初のロール付与は失敗
        member.add_roles = AsyncMock(
            side_effect=[discord.HTTPException(MagicMock(), "error"), None]
        )
        config1 = _make_config(config_id=1, role_id="111")
        config2 = _make_config(config_id=2, role_id="222")

        with (
            patch(
                "src.cogs.join_role.get_enabled_join_role_configs",
                return_value=[config1, config2],
            ),
            patch(
                "src.cogs.join_role.create_join_role_assignment",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await cog.on_member_join(member)
            # 2回目のロール付与は成功 → assignment も 1 件作成
            assert mock_create.call_count == 1
