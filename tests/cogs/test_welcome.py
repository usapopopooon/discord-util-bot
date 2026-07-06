"""Tests for WelcomeCog."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from src.cogs.welcome import WELCOME_EMBED_COLOR, WelcomeCog


def _make_cog() -> WelcomeCog:
    bot = MagicMock(spec=commands.Bot)
    banner_service = MagicMock()
    banner_service.create.return_value = b"pngdata"
    return WelcomeCog(bot, banner_service=banner_service)


def _make_member() -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = 12345
    member.name = "chill"
    member.display_name = "ちるちる"
    member.mention = "<@12345>"
    member.display_avatar = MagicMock()

    guild = MagicMock(spec=discord.Guild)
    guild.id = 789
    guild.name = "CHILLカフェ"
    guild.member_count = 128
    guild.get_channel_or_thread = MagicMock()
    guild.fetch_channel = AsyncMock()
    member.guild = guild
    return member


def _patch_session() -> MagicMock:
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return session_factory


class TestSendWelcome:
    @pytest.mark.asyncio
    async def test_no_config_returns_false(self) -> None:
        cog = _make_cog()
        member = _make_member()

        with (
            patch("src.cogs.welcome.async_session", _patch_session()),
            patch(
                "src.cogs.welcome.get_welcome_config",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            sent = await cog.send_welcome(member)

        assert sent is False
        member.guild.get_channel_or_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_config_returns_false(self) -> None:
        cog = _make_cog()
        member = _make_member()
        config = SimpleNamespace(enabled=False, channel_id="555")

        with (
            patch("src.cogs.welcome.async_session", _patch_session()),
            patch(
                "src.cogs.welcome.get_welcome_config",
                new_callable=AsyncMock,
                return_value=config,
            ),
        ):
            sent = await cog.send_welcome(member)

        assert sent is False
        member.guild.get_channel_or_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_welcome_embed_with_attachment(self) -> None:
        cog = _make_cog()
        member = _make_member()
        channel = MagicMock()
        channel.id = 555
        channel.send = AsyncMock()
        member.guild.get_channel_or_thread.return_value = channel
        config = SimpleNamespace(
            enabled=True,
            channel_id="555",
            message_content="いらっしゃいませ、{mention}!",
            banner_message_template="{displayName} さんが入店しました",
        )

        with (
            patch("src.cogs.welcome.async_session", _patch_session()),
            patch(
                "src.cogs.welcome.get_welcome_config",
                new_callable=AsyncMock,
                return_value=config,
            ),
            patch(
                "src.cogs.welcome._read_member_avatar",
                new_callable=AsyncMock,
                return_value=b"avatar",
            ),
        ):
            sent = await cog.send_welcome(member)

        assert sent is True
        channel.send.assert_awaited_once()
        kwargs = channel.send.await_args.kwargs
        assert isinstance(kwargs["embed"], discord.Embed)
        assert kwargs["embed"].description == "いらっしゃいませ、<@12345>!"
        assert kwargs["embed"].color == discord.Color(WELCOME_EMBED_COLOR)
        assert isinstance(kwargs["file"], discord.File)
        assert kwargs["file"].filename == "welcome-12345.png"
        cog.banner_service.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_channel_missing(self) -> None:
        cog = _make_cog()
        member = _make_member()
        member.guild.get_channel_or_thread.return_value = None
        member.guild.fetch_channel.side_effect = discord.HTTPException(
            MagicMock(), "missing"
        )
        config = SimpleNamespace(enabled=True, channel_id="555")

        with (
            patch("src.cogs.welcome.async_session", _patch_session()),
            patch(
                "src.cogs.welcome.get_welcome_config",
                new_callable=AsyncMock,
                return_value=config,
            ),
        ):
            sent = await cog.send_welcome(member)

        assert sent is False
