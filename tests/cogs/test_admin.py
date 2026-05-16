"""Tests for AdminCog."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord import app_commands
from discord.ext import commands

from src.cogs.admin import AdminCog


def _make_cog() -> AdminCog:
    bot = MagicMock(spec=commands.Bot)
    bot.guilds = []
    bot.change_presence = AsyncMock()
    return AdminCog(bot)


def _make_interaction(guild_id: int = 12345) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock()
    interaction.guild.id = guild_id
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _make_mock_guild(guild_id: int, channel_ids: list[int] | None = None) -> MagicMock:
    guild = MagicMock()
    guild.id = guild_id
    if channel_ids is None:
        channel_ids = [100, 200]
    channels = []
    for ch_id in channel_ids:
        ch = MagicMock()
        ch.id = ch_id
        channels.append(ch)
    guild.channels = channels
    return guild


def _make_mock_session() -> MagicMock:
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
    return mock_session_ctx


def _make_sticky_message(guild_id: str, channel_id: str = "100") -> MagicMock:
    sticky = MagicMock()
    sticky.guild_id = guild_id
    sticky.channel_id = channel_id
    return sticky


def _make_role_panel(guild_id: str, channel_id: str = "100") -> MagicMock:
    panel = MagicMock()
    panel.guild_id = guild_id
    panel.channel_id = channel_id
    return panel


class TestSetup:
    async def test_setup_adds_cog(self) -> None:
        from src.cogs.admin import setup

        bot = MagicMock(spec=discord.ext.commands.Bot)
        bot.add_cog = AsyncMock()

        await setup(bot)

        bot.add_cog.assert_awaited_once()
        cog = bot.add_cog.call_args[0][0]
        assert isinstance(cog, AdminCog)


class TestCleanupCommand:
    @patch("src.cogs.admin.async_session")
    @patch("src.cogs.admin.get_all_sticky_messages")
    @patch("src.cogs.admin.get_all_role_panels")
    @patch("src.cogs.admin.delete_sticky_messages_by_guild")
    @patch("src.cogs.admin.delete_role_panels_by_guild")
    async def test_cleanup_no_orphaned_data(
        self,
        mock_delete_panels: AsyncMock,
        mock_delete_stickies: AsyncMock,
        mock_get_panels: AsyncMock,
        mock_get_stickies: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        cog = _make_cog()
        cog.bot.guilds = [_make_mock_guild(12345)]

        mock_get_stickies.return_value = [_make_sticky_message("12345")]
        mock_get_panels.return_value = [_make_role_panel("12345")]
        mock_session.return_value = _make_mock_session()

        interaction = _make_interaction()
        await cog.cleanup.callback(cog, interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once()
        msg = interaction.followup.send.call_args[0][0]
        assert "ありませんでした" in msg
        mock_delete_stickies.assert_not_awaited()
        mock_delete_panels.assert_not_awaited()


class TestStatsCommand:
    @patch("src.cogs.admin.async_session")
    @patch("src.cogs.admin.get_all_sticky_messages")
    @patch("src.cogs.admin.get_all_role_panels")
    async def test_stats_embed(
        self,
        mock_get_panels: AsyncMock,
        mock_get_stickies: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        cog = _make_cog()
        cog.bot.guilds = [_make_mock_guild(12345), _make_mock_guild(67890)]

        mock_get_stickies.return_value = [
            _make_sticky_message("12345"),
            _make_sticky_message("99999"),
        ]
        mock_get_panels.return_value = [
            _make_role_panel("12345"),
            _make_role_panel("67890"),
            _make_role_panel("99999"),
        ]
        mock_session.return_value = _make_mock_session()

        interaction = _make_interaction()
        await cog.stats.callback(cog, interaction)

        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.call_args.kwargs
        embed = kwargs["embed"]
        assert embed.title == "DB統計情報"


class TestActivityCommand:
    @patch("src.cogs.admin.upsert_bot_activity")
    @patch("src.cogs.admin.async_session")
    async def test_activity_updates_presence(
        self,
        mock_session: MagicMock,
        mock_upsert: AsyncMock,
    ) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        mock_session.return_value = _make_mock_session()

        choice = app_commands.Choice(name="プレイ中", value="playing")
        await cog.activity.callback(cog, interaction, choice, "Hello")

        mock_upsert.assert_awaited_once()
        cog.bot.change_presence.assert_awaited_once()
        interaction.followup.send.assert_awaited_once()
