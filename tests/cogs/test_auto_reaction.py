"""Tests for AutoReactionCog (auto reaction feature)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from src.cogs.auto_reaction import AutoReactionCog


def _make_cog() -> AutoReactionCog:
    bot = MagicMock(spec=commands.Bot)
    bot.wait_until_ready = AsyncMock()
    return AutoReactionCog(bot)


def _make_message(
    *,
    guild_id: int = 789,
    channel_id: int = 555,
    is_bot: bool = False,
) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.id = 99999
    message.guild = MagicMock()
    message.guild.id = guild_id
    message.channel = MagicMock()
    message.channel.id = channel_id
    message.add_reaction = AsyncMock()

    author = MagicMock(spec=discord.Member)
    author.id = 12345
    author.bot = is_bot
    message.author = author
    return message


# ---------------------------------------------------------------------------
# TestOnMessage
# ---------------------------------------------------------------------------


class TestOnMessage:
    """on_message イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bot_messages(self) -> None:
        cog = _make_cog()
        cog._configs = {"555": [discord.PartialEmoji.from_str("👍")]}
        message = _make_message(is_bot=True)
        await cog.on_message(message)
        message.add_reaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_dm(self) -> None:
        cog = _make_cog()
        cog._configs = {"555": [discord.PartialEmoji.from_str("👍")]}
        message = _make_message()
        message.guild = None
        await cog.on_message(message)
        message.add_reaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_op_when_cache_uninitialized(self) -> None:
        """_configs=None (起動直後の初期化失敗時) は何もしない。"""
        cog = _make_cog()
        assert cog._configs is None
        message = _make_message()
        await cog.on_message(message)
        message.add_reaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_op_for_channel_not_in_cache(self) -> None:
        cog = _make_cog()
        cog._configs = {"999": [discord.PartialEmoji.from_str("👍")]}
        message = _make_message(channel_id=555)
        await cog.on_message(message)
        message.add_reaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_adds_unicode_emojis_in_order(self) -> None:
        cog = _make_cog()
        cog._configs = {
            "555": [discord.PartialEmoji.from_str(e) for e in ("👍", "❤️", "🎉")]
        }
        message = _make_message()
        await cog.on_message(message)

        assert message.add_reaction.await_count == 3
        called = [c.args[0] for c in message.add_reaction.await_args_list]
        assert [str(e) for e in called] == ["👍", "❤️", "🎉"]

    @pytest.mark.asyncio
    async def test_adds_custom_emoji(self) -> None:
        cog = _make_cog()
        cog._configs = {
            "555": [discord.PartialEmoji.from_str("<:custom:123456789012345678>")]
        }
        message = _make_message()
        await cog.on_message(message)

        message.add_reaction.assert_awaited_once()
        emoji = message.add_reaction.await_args.args[0]
        assert isinstance(emoji, discord.PartialEmoji)
        assert emoji.name == "custom"
        assert emoji.id == 123456789012345678
        assert emoji.animated is False

    @pytest.mark.asyncio
    async def test_adds_animated_custom_emoji(self) -> None:
        cog = _make_cog()
        cog._configs = {
            "555": [discord.PartialEmoji.from_str("<a:dance:111222333444555666>")]
        }
        message = _make_message()
        await cog.on_message(message)

        emoji = message.add_reaction.await_args.args[0]
        assert isinstance(emoji, discord.PartialEmoji)
        assert emoji.animated is True

    @pytest.mark.asyncio
    async def test_continues_after_http_error(self) -> None:
        """1つの絵文字で HTTPException が出ても残りは処理する。"""
        cog = _make_cog()
        cog._configs = {"555": [discord.PartialEmoji.from_str(e) for e in ("👍", "❤️")]}
        message = _make_message()
        message.add_reaction = AsyncMock(
            side_effect=[
                discord.HTTPException(MagicMock(), "rate limited"),
                None,
            ]
        )
        await cog.on_message(message)
        assert message.add_reaction.await_count == 2


# ---------------------------------------------------------------------------
# TestRefreshCache
# ---------------------------------------------------------------------------


class TestRefreshCache:
    """_refresh_cache バックグラウンドタスクのテスト。"""

    @pytest.mark.asyncio
    async def test_cache_is_refreshed_with_parsed_emojis(self) -> None:
        cog = _make_cog()
        with patch(
            "src.cogs.auto_reaction.get_enabled_auto_reaction_emoji_map",
            new_callable=AsyncMock,
            return_value={"555": ["👍", "❤️"], "777": ["🎉"]},
        ):
            await cog._refresh_cache()
        assert cog._configs is not None
        assert set(cog._configs.keys()) == {"555", "777"}
        assert all(
            isinstance(e, discord.PartialEmoji)
            for emojis in cog._configs.values()
            for e in emojis
        )
        assert [str(e) for e in cog._configs["555"]] == ["👍", "❤️"]

    @pytest.mark.asyncio
    async def test_before_loop_waits_until_ready(self) -> None:
        cog = _make_cog()
        await cog._before_refresh_cache()
        cog.bot.wait_until_ready.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestCogLifecycle
# ---------------------------------------------------------------------------


class TestCogLifecycle:
    @pytest.mark.asyncio
    async def test_cog_load_starts_task(self) -> None:
        cog = _make_cog()
        with patch.object(cog._refresh_cache, "start") as mock_start:
            await cog.cog_load()
            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_cancels_task(self) -> None:
        cog = _make_cog()
        with (
            patch.object(cog._refresh_cache, "is_running", return_value=True),
            patch.object(cog._refresh_cache, "cancel") as mock_cancel,
        ):
            await cog.cog_unload()
            mock_cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_not_running(self) -> None:
        cog = _make_cog()
        with (
            patch.object(cog._refresh_cache, "is_running", return_value=False),
            patch.object(cog._refresh_cache, "cancel") as mock_cancel,
        ):
            await cog.cog_unload()
            mock_cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_adds_cog_and_initializes_cache(self) -> None:
        from src.cogs.auto_reaction import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()
        with patch(
            "src.cogs.auto_reaction.get_enabled_auto_reaction_emoji_map",
            new_callable=AsyncMock,
            return_value={"555": ["👍"]},
        ):
            await setup(bot)
        bot.add_cog.assert_called_once()
        cog = bot.add_cog.call_args.args[0]
        assert cog._configs is not None
        assert [str(e) for e in cog._configs["555"]] == ["👍"]

    @pytest.mark.asyncio
    async def test_setup_swallows_cache_init_error(self) -> None:
        """初期化中の DB エラーで Bot 起動を止めない。"""
        from src.cogs.auto_reaction import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()
        with patch(
            "src.cogs.auto_reaction.get_enabled_auto_reaction_emoji_map",
            new_callable=AsyncMock,
            side_effect=RuntimeError("db down"),
        ):
            await setup(bot)
        bot.add_cog.assert_called_once()
        cog = bot.add_cog.call_args.args[0]
        assert cog._configs is None
