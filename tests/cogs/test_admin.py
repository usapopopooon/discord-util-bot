"""Tests for AdminCog."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord.ext import commands

from src.cogs.admin import AdminCog

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog() -> AdminCog:
    """Create an AdminCog with a mock bot."""
    bot = MagicMock(spec=commands.Bot)
    bot.guilds = []
    return AdminCog(bot)


def _make_interaction(guild_id: int = 12345) -> MagicMock:
    """Create a mock Discord interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock()
    interaction.guild.id = guild_id
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _make_mock_guild(
    guild_id: int,
    channel_ids: list[int] | None = None,
) -> MagicMock:
    """Create a mock Discord guild."""
    guild = MagicMock()
    guild.id = guild_id
    if channel_ids is None:
        channel_ids = [100, 200, 300]
    channels = []
    for ch_id in channel_ids:
        ch = MagicMock()
        ch.id = ch_id
        channels.append(ch)
    guild.channels = channels
    return guild


def _make_mock_session() -> MagicMock:
    """Create a mock async_session context manager."""
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
    return mock_session_ctx


def _make_lobby(guild_id: str, channel_id: str = "100") -> MagicMock:
    """Create a mock Lobby."""
    lobby = MagicMock()
    lobby.guild_id = guild_id
    lobby.channel_id = channel_id
    return lobby


def _make_bump_config(guild_id: str, channel_id: str = "100") -> MagicMock:
    """Create a mock BumpConfig."""
    config = MagicMock()
    config.guild_id = guild_id
    config.channel_id = channel_id
    return config


def _make_sticky_message(guild_id: str, channel_id: str = "100") -> MagicMock:
    """Create a mock StickyMessage."""
    sticky = MagicMock()
    sticky.guild_id = guild_id
    sticky.channel_id = channel_id
    return sticky


def _make_role_panel(guild_id: str, channel_id: str = "100") -> MagicMock:
    """Create a mock RolePanel."""
    panel = MagicMock()
    panel.guild_id = guild_id
    panel.channel_id = channel_id
    return panel


# ---------------------------------------------------------------------------
# setup 関数テスト
# ---------------------------------------------------------------------------


class TestSetup:
    """Tests for setup function."""

    async def test_setup_adds_cog(self) -> None:
        """setup() が Bot に AdminCog を追加する。"""
        from src.cogs.admin import setup

        bot = MagicMock(spec=discord.ext.commands.Bot)
        bot.add_cog = AsyncMock()

        await setup(bot)

        bot.add_cog.assert_awaited_once()
        cog = bot.add_cog.call_args[0][0]
        assert isinstance(cog, AdminCog)


# ---------------------------------------------------------------------------
# /admin cleanup テスト
# ---------------------------------------------------------------------------


class TestCleanupCommand:
    """Tests for /admin cleanup command."""

    @patch("src.cogs.admin.async_session")
    @patch("src.cogs.admin.get_all_lobbies")
    @patch("src.cogs.admin.get_all_bump_configs")
    @patch("src.cogs.admin.get_all_sticky_messages")
    @patch("src.cogs.admin.get_all_role_panels")
    @patch("src.cogs.admin.delete_lobbies_by_guild")
    @patch("src.cogs.admin.delete_bump_config")
    @patch("src.cogs.admin.delete_bump_reminders_by_guild")
    @patch("src.cogs.admin.delete_sticky_messages_by_guild")
    @patch("src.cogs.admin.delete_role_panels_by_guild")
    async def test_cleanup_no_orphaned_data(
        self,
        mock_delete_panels: AsyncMock,
        mock_delete_stickies: AsyncMock,
        mock_delete_reminders: AsyncMock,
        mock_delete_bump: AsyncMock,
        mock_delete_lobbies: AsyncMock,
        mock_get_panels: AsyncMock,
        mock_get_stickies: AsyncMock,
        mock_get_bumps: AsyncMock,
        mock_get_lobbies: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """孤立データがない場合のクリーンアップ。"""
        cog = _make_cog()
        cog.bot.guilds = [_make_mock_guild(12345)]

        # 全データが現在のギルドに属している
        mock_get_lobbies.return_value = [_make_lobby("12345")]
        mock_get_bumps.return_value = [_make_bump_config("12345", "100")]
        mock_get_stickies.return_value = [_make_sticky_message("12345")]
        mock_get_panels.return_value = [_make_role_panel("12345")]

        mock_session.return_value = _make_mock_session()

        interaction = _make_interaction()
        await cog.cleanup.callback(cog, interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once()
        msg = interaction.followup.send.call_args[0][0]
        assert "ありませんでした" in msg

        # 削除関数が呼ばれていない
        mock_delete_lobbies.assert_not_awaited()
        mock_delete_bump.assert_not_awaited()
        mock_delete_stickies.assert_not_awaited()
        mock_delete_panels.assert_not_awaited()

    @patch("src.cogs.admin.async_session")
    @patch("src.cogs.admin.get_all_lobbies")
    @patch("src.cogs.admin.get_all_bump_configs")
    @patch("src.cogs.admin.get_all_sticky_messages")
    @patch("src.cogs.admin.get_all_role_panels")
    @patch("src.cogs.admin.delete_lobbies_by_guild")
    @patch("src.cogs.admin.delete_bump_config")
    @patch("src.cogs.admin.delete_bump_reminders_by_guild")
    @patch("src.cogs.admin.delete_sticky_messages_by_guild")
    @patch("src.cogs.admin.delete_role_panels_by_guild")
    async def test_cleanup_orphaned_lobbies(
        self,
        mock_delete_panels: AsyncMock,
        mock_delete_stickies: AsyncMock,
        mock_delete_reminders: AsyncMock,
        mock_delete_bump: AsyncMock,
        mock_delete_lobbies: AsyncMock,
        mock_get_panels: AsyncMock,
        mock_get_stickies: AsyncMock,
        mock_get_bumps: AsyncMock,
        mock_get_lobbies: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """孤立したロビーを削除する。"""
        cog = _make_cog()
        cog.bot.guilds = [_make_mock_guild(12345)]

        # 存在しないギルドのデータ
        mock_get_lobbies.return_value = [
            _make_lobby("12345"),
            _make_lobby("99999"),  # orphaned
        ]
        mock_get_bumps.return_value = []
        mock_get_stickies.return_value = []
        mock_get_panels.return_value = []

        mock_delete_lobbies.return_value = 2

        mock_session.return_value = _make_mock_session()

        interaction = _make_interaction()
        await cog.cleanup.callback(cog, interaction)

        mock_delete_lobbies.assert_awaited_once()
        msg = interaction.followup.send.call_args[0][0]
        assert "ロビー" in msg
        assert "99999" in msg

    @patch("src.cogs.admin.async_session")
    @patch("src.cogs.admin.get_all_lobbies")
    @patch("src.cogs.admin.get_all_bump_configs")
    @patch("src.cogs.admin.get_all_sticky_messages")
    @patch("src.cogs.admin.get_all_role_panels")
    @patch("src.cogs.admin.delete_lobbies_by_guild")
    @patch("src.cogs.admin.delete_bump_config")
    @patch("src.cogs.admin.delete_bump_reminders_by_guild")
    @patch("src.cogs.admin.delete_sticky_messages_by_guild")
    @patch("src.cogs.admin.delete_role_panels_by_guild")
    async def test_cleanup_orphaned_bump_by_guild(
        self,
        mock_delete_panels: AsyncMock,
        mock_delete_stickies: AsyncMock,
        mock_delete_reminders: AsyncMock,
        mock_delete_bump: AsyncMock,
        mock_delete_lobbies: AsyncMock,
        mock_get_panels: AsyncMock,
        mock_get_stickies: AsyncMock,
        mock_get_bumps: AsyncMock,
        mock_get_lobbies: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """存在しないギルドのBump設定を削除する。"""
        cog = _make_cog()
        cog.bot.guilds = [_make_mock_guild(12345)]

        mock_get_lobbies.return_value = []
        mock_get_bumps.return_value = [
            _make_bump_config("99999", "100"),  # orphaned guild
        ]
        mock_get_stickies.return_value = []
        mock_get_panels.return_value = []

        mock_session.return_value = _make_mock_session()

        interaction = _make_interaction()
        await cog.cleanup.callback(cog, interaction)

        mock_delete_bump.assert_awaited_once()
        mock_delete_reminders.assert_awaited_once()
        msg = interaction.followup.send.call_args[0][0]
        assert "Bump" in msg
        assert "99999" in msg

    @patch("src.cogs.admin.async_session")
    @patch("src.cogs.admin.get_all_lobbies")
    @patch("src.cogs.admin.get_all_bump_configs")
    @patch("src.cogs.admin.get_all_sticky_messages")
    @patch("src.cogs.admin.get_all_role_panels")
    @patch("src.cogs.admin.delete_lobbies_by_guild")
    @patch("src.cogs.admin.delete_bump_config")
    @patch("src.cogs.admin.delete_bump_reminders_by_guild")
    @patch("src.cogs.admin.delete_sticky_messages_by_guild")
    @patch("src.cogs.admin.delete_role_panels_by_guild")
    async def test_cleanup_orphaned_bump_by_channel(
        self,
        mock_delete_panels: AsyncMock,
        mock_delete_stickies: AsyncMock,
        mock_delete_reminders: AsyncMock,
        mock_delete_bump: AsyncMock,
        mock_delete_lobbies: AsyncMock,
        mock_get_panels: AsyncMock,
        mock_get_stickies: AsyncMock,
        mock_get_bumps: AsyncMock,
        mock_get_lobbies: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """削除されたチャンネルのBump設定を削除する。"""
        cog = _make_cog()
        cog.bot.guilds = [_make_mock_guild(12345, channel_ids=[100, 200])]

        mock_get_lobbies.return_value = []
        mock_get_bumps.return_value = [
            _make_bump_config("12345", "999"),  # deleted channel
        ]
        mock_get_stickies.return_value = []
        mock_get_panels.return_value = []

        mock_session.return_value = _make_mock_session()

        interaction = _make_interaction()
        await cog.cleanup.callback(cog, interaction)

        mock_delete_bump.assert_awaited_once()
        mock_delete_reminders.assert_awaited_once()
        msg = interaction.followup.send.call_args[0][0]
        assert "Bump" in msg
        assert "CH削除" in msg

    @patch("src.cogs.admin.async_session")
    @patch("src.cogs.admin.get_all_lobbies")
    @patch("src.cogs.admin.get_all_bump_configs")
    @patch("src.cogs.admin.get_all_sticky_messages")
    @patch("src.cogs.admin.get_all_role_panels")
    @patch("src.cogs.admin.delete_lobbies_by_guild")
    @patch("src.cogs.admin.delete_bump_config")
    @patch("src.cogs.admin.delete_bump_reminders_by_guild")
    @patch("src.cogs.admin.delete_sticky_messages_by_guild")
    @patch("src.cogs.admin.delete_role_panels_by_guild")
    async def test_cleanup_orphaned_stickies(
        self,
        mock_delete_panels: AsyncMock,
        mock_delete_stickies: AsyncMock,
        mock_delete_reminders: AsyncMock,
        mock_delete_bump: AsyncMock,
        mock_delete_lobbies: AsyncMock,
        mock_get_panels: AsyncMock,
        mock_get_stickies: AsyncMock,
        mock_get_bumps: AsyncMock,
        mock_get_lobbies: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """孤立したStickyメッセージを削除する。"""
        cog = _make_cog()
        cog.bot.guilds = [_make_mock_guild(12345)]

        mock_get_lobbies.return_value = []
        mock_get_bumps.return_value = []
        mock_get_stickies.return_value = [
            _make_sticky_message("99999"),  # orphaned
        ]
        mock_get_panels.return_value = []

        mock_delete_stickies.return_value = 3

        mock_session.return_value = _make_mock_session()

        interaction = _make_interaction()
        await cog.cleanup.callback(cog, interaction)

        mock_delete_stickies.assert_awaited_once()
        msg = interaction.followup.send.call_args[0][0]
        assert "Sticky" in msg

    @patch("src.cogs.admin.async_session")
    @patch("src.cogs.admin.get_all_lobbies")
    @patch("src.cogs.admin.get_all_bump_configs")
    @patch("src.cogs.admin.get_all_sticky_messages")
    @patch("src.cogs.admin.get_all_role_panels")
    @patch("src.cogs.admin.delete_lobbies_by_guild")
    @patch("src.cogs.admin.delete_bump_config")
    @patch("src.cogs.admin.delete_bump_reminders_by_guild")
    @patch("src.cogs.admin.delete_sticky_messages_by_guild")
    @patch("src.cogs.admin.delete_role_panels_by_guild")
    async def test_cleanup_orphaned_role_panels(
        self,
        mock_delete_panels: AsyncMock,
        mock_delete_stickies: AsyncMock,
        mock_delete_reminders: AsyncMock,
        mock_delete_bump: AsyncMock,
        mock_delete_lobbies: AsyncMock,
        mock_get_panels: AsyncMock,
        mock_get_stickies: AsyncMock,
        mock_get_bumps: AsyncMock,
        mock_get_lobbies: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """孤立したロールパネルを削除する。"""
        cog = _make_cog()
        cog.bot.guilds = [_make_mock_guild(12345)]

        mock_get_lobbies.return_value = []
        mock_get_bumps.return_value = []
        mock_get_stickies.return_value = []
        mock_get_panels.return_value = [
            _make_role_panel("99999"),  # orphaned
        ]

        mock_delete_panels.return_value = 1

        mock_session.return_value = _make_mock_session()

        interaction = _make_interaction()
        await cog.cleanup.callback(cog, interaction)

        mock_delete_panels.assert_awaited_once()
        msg = interaction.followup.send.call_args[0][0]
        assert "パネル" in msg

    @patch("src.cogs.admin.async_session")
    @patch("src.cogs.admin.get_all_lobbies")
    @patch("src.cogs.admin.get_all_bump_configs")
    @patch("src.cogs.admin.get_all_sticky_messages")
    @patch("src.cogs.admin.get_all_role_panels")
    @patch("src.cogs.admin.delete_lobbies_by_guild")
    @patch("src.cogs.admin.delete_bump_config")
    @patch("src.cogs.admin.delete_bump_reminders_by_guild")
    @patch("src.cogs.admin.delete_sticky_messages_by_guild")
    @patch("src.cogs.admin.delete_role_panels_by_guild")
    async def test_cleanup_multiple_orphaned_data(
        self,
        mock_delete_panels: AsyncMock,
        mock_delete_stickies: AsyncMock,
        mock_delete_reminders: AsyncMock,
        mock_delete_bump: AsyncMock,
        mock_delete_lobbies: AsyncMock,
        mock_get_panels: AsyncMock,
        mock_get_stickies: AsyncMock,
        mock_get_bumps: AsyncMock,
        mock_get_lobbies: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """複数種類の孤立データを一度に削除する。"""
        cog = _make_cog()
        cog.bot.guilds = [_make_mock_guild(12345)]

        mock_get_lobbies.return_value = [_make_lobby("99998")]
        mock_get_bumps.return_value = [_make_bump_config("99999", "100")]
        mock_get_stickies.return_value = [_make_sticky_message("88888")]
        mock_get_panels.return_value = [_make_role_panel("77777")]

        mock_delete_lobbies.return_value = 1
        mock_delete_stickies.return_value = 1
        mock_delete_panels.return_value = 1

        mock_session.return_value = _make_mock_session()

        interaction = _make_interaction()
        await cog.cleanup.callback(cog, interaction)

        # 全ての削除関数が呼ばれる
        mock_delete_lobbies.assert_awaited()
        mock_delete_bump.assert_awaited()
        mock_delete_stickies.assert_awaited()
        mock_delete_panels.assert_awaited()

        msg = interaction.followup.send.call_args[0][0]
        assert "クリーンアップ完了" in msg


# ---------------------------------------------------------------------------
# /admin stats テスト
# ---------------------------------------------------------------------------


class TestStatsCommand:
    """Tests for /admin stats command."""

    @patch("src.cogs.admin.async_session")
    @patch("src.cogs.admin.get_all_lobbies")
    @patch("src.cogs.admin.get_all_bump_configs")
    @patch("src.cogs.admin.get_all_sticky_messages")
    @patch("src.cogs.admin.get_all_role_panels")
    async def test_stats_no_data(
        self,
        mock_get_panels: AsyncMock,
        mock_get_stickies: AsyncMock,
        mock_get_bumps: AsyncMock,
        mock_get_lobbies: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """データがない場合の統計表示。"""
        cog = _make_cog()
        cog.bot.guilds = []

        mock_get_lobbies.return_value = []
        mock_get_bumps.return_value = []
        mock_get_stickies.return_value = []
        mock_get_panels.return_value = []

        mock_session.return_value = _make_mock_session()

        interaction = _make_interaction()
        await cog.stats.callback(cog, interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once()

        # Embed が送信されていることを確認
        call_kwargs = interaction.followup.send.call_args[1]
        assert "embed" in call_kwargs
        embed = call_kwargs["embed"]
        assert embed.title == "DB統計情報"

    @patch("src.cogs.admin.async_session")
    @patch("src.cogs.admin.get_all_lobbies")
    @patch("src.cogs.admin.get_all_bump_configs")
    @patch("src.cogs.admin.get_all_sticky_messages")
    @patch("src.cogs.admin.get_all_role_panels")
    async def test_stats_with_data(
        self,
        mock_get_panels: AsyncMock,
        mock_get_stickies: AsyncMock,
        mock_get_bumps: AsyncMock,
        mock_get_lobbies: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """データがある場合の統計表示。"""
        cog = _make_cog()
        cog.bot.guilds = [_make_mock_guild(12345), _make_mock_guild(67890)]

        mock_get_lobbies.return_value = [
            _make_lobby("12345"),
            _make_lobby("12345"),
        ]
        mock_get_bumps.return_value = [
            _make_bump_config("12345", "100"),
            _make_bump_config("67890", "200"),
        ]
        mock_get_stickies.return_value = [
            _make_sticky_message("12345"),
        ]
        mock_get_panels.return_value = [
            _make_role_panel("12345"),
            _make_role_panel("67890"),
            _make_role_panel("67890"),
        ]

        mock_session.return_value = _make_mock_session()

        interaction = _make_interaction()
        await cog.stats.callback(cog, interaction)

        call_kwargs = interaction.followup.send.call_args[1]
        embed = call_kwargs["embed"]

        # フィールドが正しく設定されていることを確認
        assert len(embed.fields) == 5
        field_names = [f.name for f in embed.fields]
        assert "ロビー" in field_names
        assert "Bump設定" in field_names
        assert "Sticky" in field_names
        assert "ロールパネル" in field_names
        assert "参加ギルド数" in field_names

    @patch("src.cogs.admin.async_session")
    @patch("src.cogs.admin.get_all_lobbies")
    @patch("src.cogs.admin.get_all_bump_configs")
    @patch("src.cogs.admin.get_all_sticky_messages")
    @patch("src.cogs.admin.get_all_role_panels")
    async def test_stats_with_orphaned_data(
        self,
        mock_get_panels: AsyncMock,
        mock_get_stickies: AsyncMock,
        mock_get_bumps: AsyncMock,
        mock_get_lobbies: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """孤立データがある場合の統計表示。"""
        cog = _make_cog()
        cog.bot.guilds = [_make_mock_guild(12345)]

        mock_get_lobbies.return_value = [
            _make_lobby("12345"),
            _make_lobby("99999"),  # orphaned
        ]
        mock_get_bumps.return_value = [
            _make_bump_config("12345", "100"),
            _make_bump_config("99999", "100"),  # orphaned
        ]
        mock_get_stickies.return_value = [
            _make_sticky_message("99999"),  # orphaned
        ]
        mock_get_panels.return_value = [
            _make_role_panel("12345"),
            _make_role_panel("88888"),  # orphaned
            _make_role_panel("88888"),  # orphaned
        ]

        mock_session.return_value = _make_mock_session()

        interaction = _make_interaction()
        await cog.stats.callback(cog, interaction)

        call_kwargs = interaction.followup.send.call_args[1]
        embed = call_kwargs["embed"]

        # 孤立データの数が正しく表示されている
        lobby_field = next(f for f in embed.fields if f.name == "ロビー")
        assert "総数: 2" in lobby_field.value
        assert "孤立: 1" in lobby_field.value

        bump_field = next(f for f in embed.fields if f.name == "Bump設定")
        assert "総数: 2" in bump_field.value
        assert "孤立: 1" in bump_field.value

        sticky_field = next(f for f in embed.fields if f.name == "Sticky")
        assert "総数: 1" in sticky_field.value
        assert "孤立: 1" in sticky_field.value

        panel_field = next(f for f in embed.fields if f.name == "ロールパネル")
        assert "総数: 3" in panel_field.value
        assert "孤立: 2" in panel_field.value
