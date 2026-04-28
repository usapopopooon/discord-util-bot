"""Tests for ChatRoleCog (chat role feature)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from src.cogs.chatrole import ChatRoleCog

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog() -> ChatRoleCog:
    bot = MagicMock(spec=commands.Bot)
    bot.wait_until_ready = AsyncMock()
    return ChatRoleCog(bot)


def _make_message(
    *,
    user_id: int = 12345,
    guild_id: int = 789,
    channel_id: int = 555,
    is_bot: bool = False,
    msg_type: discord.MessageType = discord.MessageType.default,
    created_at: datetime | None = None,
) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.guild = MagicMock()
    message.guild.id = guild_id
    message.guild.get_role = MagicMock()
    message.channel = MagicMock()
    message.channel.id = channel_id
    message.type = msg_type
    message.created_at = created_at or datetime.now(UTC)

    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.bot = is_bot
    member.add_roles = AsyncMock()
    message.author = member
    return message


def _make_config(
    *,
    config_id: int = 1,
    guild_id: str = "789",
    channel_id: str = "555",
    role_id: str = "111",
    threshold: int = 3,
    duration_hours: int | None = 24,
    enabled: bool = True,
    created_at: datetime | None = None,
) -> MagicMock:
    config = MagicMock()
    config.id = config_id
    config.guild_id = guild_id
    config.channel_id = channel_id
    config.role_id = role_id
    config.threshold = threshold
    config.duration_hours = duration_hours
    config.enabled = enabled
    config.created_at = created_at or (datetime.now(UTC) - timedelta(days=1))
    return config


def _make_progress(
    *,
    progress_id: int = 1,
    config_id: int = 1,
    user_id: str = "12345",
    count: int = 1,
    granted: bool = False,
    expires_at: datetime | None = None,
) -> MagicMock:
    progress = MagicMock()
    progress.id = progress_id
    progress.config_id = config_id
    progress.user_id = user_id
    progress.count = count
    progress.granted = granted
    progress.expires_at = expires_at
    return progress


# ---------------------------------------------------------------------------
# TestOnMessage
# ---------------------------------------------------------------------------


class TestOnMessage:
    """on_message イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bot_messages(self) -> None:
        cog = _make_cog()
        message = _make_message(is_bot=True)
        with patch(
            "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel"
        ) as mock_get:
            await cog.on_message(message)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_non_default_messages(self) -> None:
        cog = _make_cog()
        message = _make_message(msg_type=discord.MessageType.thread_created)
        with patch(
            "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel"
        ) as mock_get:
            await cog.on_message(message)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_dm(self) -> None:
        cog = _make_cog()
        message = _make_message()
        message.guild = None
        with patch(
            "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel"
        ) as mock_get:
            await cog.on_message(message)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_config_no_action(self) -> None:
        cog = _make_cog()
        message = _make_message()
        with patch(
            "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel",
            return_value=[],
        ):
            await cog.on_message(message)
            message.author.add_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_short_circuits_db_query(self) -> None:
        """キャッシュに channel_id がなければ DB クエリを発行しない。"""
        cog = _make_cog()
        cog._chatrole_channels = {"999"}  # 別チャンネルのみキャッシュ
        message = _make_message(channel_id=555)
        with patch(
            "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel"
        ) as mock_get:
            await cog.on_message(message)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_proceeds_to_db_query(self) -> None:
        """キャッシュに channel_id があれば DB クエリを実行する。"""
        cog = _make_cog()
        cog._chatrole_channels = {"555"}
        message = _make_message(channel_id=555)
        with patch(
            "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel",
            return_value=[],
        ) as mock_get:
            await cog.on_message(message)
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_increment_below_threshold_no_grant(self) -> None:
        """threshold 未達ではロール付与しない。"""
        cog = _make_cog()
        message = _make_message()
        config = _make_config(threshold=5)
        progress = _make_progress(count=2, granted=False)

        with (
            patch(
                "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel",
                return_value=[config],
            ),
            patch(
                "src.cogs.chatrole.increment_chat_role_progress",
                new_callable=AsyncMock,
                return_value=progress,
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_granted",
                new_callable=AsyncMock,
            ) as mock_grant,
        ):
            await cog.on_message(message)
            mock_grant.assert_not_called()
            message.author.add_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_grants_role_when_threshold_reached(self) -> None:
        cog = _make_cog()
        message = _make_message()
        role = MagicMock(spec=discord.Role)
        message.guild.get_role.return_value = role
        config = _make_config(threshold=3, duration_hours=24)
        progress = _make_progress(count=3, granted=False)

        with (
            patch(
                "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel",
                return_value=[config],
            ),
            patch(
                "src.cogs.chatrole.increment_chat_role_progress",
                new_callable=AsyncMock,
                return_value=progress,
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_granted",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_grant,
        ):
            await cog.on_message(message)
            mock_grant.assert_called_once()
            message.author.add_roles.assert_called_once_with(
                role, reason="ChatRole: 投稿ロール付与"
            )

    @pytest.mark.asyncio
    async def test_skips_when_already_granted(self) -> None:
        """increment が None を返した場合 (granted=True) は付与処理スキップ。"""
        cog = _make_cog()
        message = _make_message()
        config = _make_config(threshold=3)

        with (
            patch(
                "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel",
                return_value=[config],
            ),
            patch(
                "src.cogs.chatrole.increment_chat_role_progress",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_granted",
                new_callable=AsyncMock,
            ) as mock_grant,
        ):
            await cog.on_message(message)
            mock_grant.assert_not_called()
            message.author.add_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_messages_before_config_created(self) -> None:
        """config.created_at より前の投稿はカウントしない。"""
        cog = _make_cog()
        config_created = datetime.now(UTC)
        message = _make_message(created_at=config_created - timedelta(hours=1))
        config = _make_config(created_at=config_created)

        with (
            patch(
                "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel",
                return_value=[config],
            ),
            patch(
                "src.cogs.chatrole.increment_chat_role_progress",
                new_callable=AsyncMock,
            ) as mock_inc,
        ):
            await cog.on_message(message)
            mock_inc.assert_not_called()

    @pytest.mark.asyncio
    async def test_role_not_found(self) -> None:
        cog = _make_cog()
        message = _make_message()
        message.guild.get_role.return_value = None
        config = _make_config(threshold=1)
        progress = _make_progress(count=1, granted=False)

        with (
            patch(
                "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel",
                return_value=[config],
            ),
            patch(
                "src.cogs.chatrole.increment_chat_role_progress",
                new_callable=AsyncMock,
                return_value=progress,
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_granted",
                new_callable=AsyncMock,
            ) as mock_grant,
        ):
            await cog.on_message(message)
            mock_grant.assert_not_called()
            message.author.add_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_claim_skipped(self) -> None:
        """別インスタンスが先に granted にした場合、add_roles は呼ばない。"""
        cog = _make_cog()
        message = _make_message()
        role = MagicMock(spec=discord.Role)
        message.guild.get_role.return_value = role
        config = _make_config(threshold=1)
        progress = _make_progress(count=1, granted=False)

        with (
            patch(
                "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel",
                return_value=[config],
            ),
            patch(
                "src.cogs.chatrole.increment_chat_role_progress",
                new_callable=AsyncMock,
                return_value=progress,
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_granted",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            await cog.on_message(message)
            message.author.add_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_permanent_grant_no_expires_at(self) -> None:
        """duration_hours が None の場合、expires_at は None で付与する。"""
        cog = _make_cog()
        message = _make_message()
        role = MagicMock(spec=discord.Role)
        message.guild.get_role.return_value = role
        config = _make_config(threshold=1, duration_hours=None)
        progress = _make_progress(count=1, granted=False)

        with (
            patch(
                "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel",
                return_value=[config],
            ),
            patch(
                "src.cogs.chatrole.increment_chat_role_progress",
                new_callable=AsyncMock,
                return_value=progress,
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_granted",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_grant,
        ):
            await cog.on_message(message)
            assert mock_grant.call_args.kwargs["expires_at"] is None

    @pytest.mark.asyncio
    async def test_add_roles_http_error(self) -> None:
        cog = _make_cog()
        message = _make_message()
        role = MagicMock(spec=discord.Role)
        message.guild.get_role.return_value = role
        message.author.add_roles = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "error")
        )
        config = _make_config(threshold=1)
        progress = _make_progress(count=1, granted=False)

        with (
            patch(
                "src.cogs.chatrole.get_enabled_chat_role_configs_for_channel",
                return_value=[config],
            ),
            patch(
                "src.cogs.chatrole.increment_chat_role_progress",
                new_callable=AsyncMock,
                return_value=progress,
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_granted",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            # 例外を握りつぶす (logger.exception で記録) ことを確認
            await cog.on_message(message)


# ---------------------------------------------------------------------------
# TestCheckExpiredRoles
# ---------------------------------------------------------------------------


class TestCheckExpiredRoles:
    """_check_expired_roles バックグラウンドタスクのテスト。"""

    @pytest.fixture(autouse=True)
    def _patch_channel_cache(self) -> AsyncMock:
        """全テストで get_enabled_chat_role_channel_ids を空集合にスタブする。"""
        with patch(
            "src.cogs.chatrole.get_enabled_chat_role_channel_ids",
            new_callable=AsyncMock,
            return_value=set(),
        ) as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_removes_expired_role(self) -> None:
        cog = _make_cog()
        member = MagicMock(spec=discord.Member)
        member.remove_roles = AsyncMock()
        role = MagicMock(spec=discord.Role)
        guild = MagicMock(spec=discord.Guild)
        guild.get_member.return_value = member
        guild.get_role.return_value = role
        cog.bot.get_guild.return_value = guild

        progress = _make_progress(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        config = _make_config()

        with (
            patch(
                "src.cogs.chatrole.get_expired_chat_role_progress",
                new_callable=AsyncMock,
                return_value=[(progress, config)],
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_expired",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_expire,
        ):
            await cog._check_expired_roles()
            member.remove_roles.assert_called_once_with(
                role, reason="ChatRole: 期限切れロール削除"
            )
            mock_expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_guild_not_found(self) -> None:
        cog = _make_cog()
        cog.bot.get_guild.return_value = None
        progress = _make_progress()
        config = _make_config()

        with (
            patch(
                "src.cogs.chatrole.get_expired_chat_role_progress",
                new_callable=AsyncMock,
                return_value=[(progress, config)],
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_expired",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_expire,
        ):
            await cog._check_expired_roles()
            mock_expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_member_left(self) -> None:
        cog = _make_cog()
        guild = MagicMock(spec=discord.Guild)
        guild.get_member.return_value = None
        cog.bot.get_guild.return_value = guild
        progress = _make_progress()
        config = _make_config()

        with (
            patch(
                "src.cogs.chatrole.get_expired_chat_role_progress",
                new_callable=AsyncMock,
                return_value=[(progress, config)],
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_expired",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_expire,
        ):
            await cog._check_expired_roles()
            mock_expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_role_not_found_only_clears_record(self) -> None:
        cog = _make_cog()
        member = MagicMock(spec=discord.Member)
        guild = MagicMock(spec=discord.Guild)
        guild.get_member.return_value = member
        guild.get_role.return_value = None
        cog.bot.get_guild.return_value = guild
        progress = _make_progress()
        config = _make_config()

        with (
            patch(
                "src.cogs.chatrole.get_expired_chat_role_progress",
                new_callable=AsyncMock,
                return_value=[(progress, config)],
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_expired",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_expire,
        ):
            await cog._check_expired_roles()
            mock_expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_is_refreshed(self, _patch_channel_cache: AsyncMock) -> None:
        """バックグラウンドタスク実行時にチャンネルキャッシュが更新される。"""
        cog = _make_cog()
        _patch_channel_cache.return_value = {"555", "777"}
        with patch(
            "src.cogs.chatrole.get_expired_chat_role_progress",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await cog._check_expired_roles()
        assert cog._chatrole_channels == {"555", "777"}

    @pytest.mark.asyncio
    async def test_no_expired_progress(self) -> None:
        cog = _make_cog()
        with (
            patch(
                "src.cogs.chatrole.get_expired_chat_role_progress",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_expired",
                new_callable=AsyncMock,
            ) as mock_expire,
        ):
            await cog._check_expired_roles()
            mock_expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_expire_skipped(self) -> None:
        cog = _make_cog()
        member = MagicMock(spec=discord.Member)
        member.remove_roles = AsyncMock()
        role = MagicMock(spec=discord.Role)
        guild = MagicMock(spec=discord.Guild)
        guild.get_member.return_value = member
        guild.get_role.return_value = role
        cog.bot.get_guild.return_value = guild
        progress = _make_progress()
        config = _make_config()

        with (
            patch(
                "src.cogs.chatrole.get_expired_chat_role_progress",
                new_callable=AsyncMock,
                return_value=[(progress, config)],
            ),
            patch(
                "src.cogs.chatrole.mark_chat_role_progress_expired",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            await cog._check_expired_roles()
            member.remove_roles.assert_not_called()


# ---------------------------------------------------------------------------
# TestCogLifecycle
# ---------------------------------------------------------------------------


class TestCogLifecycle:
    @pytest.mark.asyncio
    async def test_cog_load_starts_task(self) -> None:
        cog = _make_cog()
        with patch.object(cog._check_expired_roles, "start") as mock_start:
            await cog.cog_load()
            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_cancels_task(self) -> None:
        cog = _make_cog()
        with (
            patch.object(cog._check_expired_roles, "is_running", return_value=True),
            patch.object(cog._check_expired_roles, "cancel") as mock_cancel,
        ):
            await cog.cog_unload()
            mock_cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_not_running(self) -> None:
        cog = _make_cog()
        with (
            patch.object(cog._check_expired_roles, "is_running", return_value=False),
            patch.object(cog._check_expired_roles, "cancel") as mock_cancel,
        ):
            await cog.cog_unload()
            mock_cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_adds_cog(self) -> None:
        from src.cogs.chatrole import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()
        with patch(
            "src.cogs.chatrole.get_enabled_chat_role_channel_ids",
            new_callable=AsyncMock,
            return_value={"555"},
        ):
            await setup(bot)
        bot.add_cog.assert_called_once()
        cog = bot.add_cog.call_args.args[0]
        assert cog._chatrole_channels == {"555"}

    @pytest.mark.asyncio
    async def test_before_loop_waits_until_ready(self) -> None:
        cog = _make_cog()
        cog.bot.wait_until_ready = AsyncMock()
        await cog._before_check_expired_roles()
        cog.bot.wait_until_ready.assert_awaited_once()
