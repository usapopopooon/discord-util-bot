"""Tests for WatchdogCog (gateway silence detection)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from discord.ext import commands

from src.cogs.watchdog import _STALE_THRESHOLD_SECONDS, WatchdogCog


def _make_cog() -> WatchdogCog:
    bot = MagicMock(spec=commands.Bot)
    bot.wait_until_ready = AsyncMock()
    return WatchdogCog(bot)


class TestOnSocketEventType:
    """Gateway イベント受信時の最終時刻更新。"""

    async def test_updates_last_event_at(self) -> None:
        cog = _make_cog()
        with patch("src.cogs.watchdog.time.monotonic", return_value=1234.5):
            await cog.on_socket_event_type("MESSAGE_CREATE")
        assert cog._last_event_at == 1234.5


class TestCheckGateway:
    """無音検知ロジック。"""

    async def test_does_not_exit_when_recent_event(self) -> None:
        cog = _make_cog()
        # 直近にイベントを受信した状態
        cog._last_event_at = 1000.0
        with (
            patch("src.cogs.watchdog.time.monotonic", return_value=1010.0),
            patch("src.cogs.watchdog.os._exit") as mock_exit,
        ):
            await cog._check_gateway()
        mock_exit.assert_not_called()

    async def test_does_not_exit_at_threshold_boundary(self) -> None:
        cog = _make_cog()
        cog._last_event_at = 1000.0
        # ちょうど閾値の場合は exit しない (> で比較しているため)
        with (
            patch(
                "src.cogs.watchdog.time.monotonic",
                return_value=1000.0 + _STALE_THRESHOLD_SECONDS,
            ),
            patch("src.cogs.watchdog.os._exit") as mock_exit,
        ):
            await cog._check_gateway()
        mock_exit.assert_not_called()

    async def test_exits_when_stale(self) -> None:
        cog = _make_cog()
        cog._last_event_at = 1000.0
        # 閾値を 1 秒超えた状態
        with (
            patch(
                "src.cogs.watchdog.time.monotonic",
                return_value=1000.0 + _STALE_THRESHOLD_SECONDS + 1,
            ),
            patch("src.cogs.watchdog.os._exit") as mock_exit,
        ):
            await cog._check_gateway()
        mock_exit.assert_called_once_with(1)


class TestBeforeCheck:
    """before_loop での初期化。"""

    async def test_waits_until_ready_and_resets_timer(self) -> None:
        cog = _make_cog()
        with patch("src.cogs.watchdog.time.monotonic", return_value=9999.0):
            await cog._before_check()
        cog.bot.wait_until_ready.assert_awaited_once()
        assert cog._last_event_at == 9999.0


class TestCogLifecycle:
    async def test_cog_load_starts_check_loop(self) -> None:
        cog = _make_cog()
        with patch.object(cog._check_gateway, "start") as mock_start:
            await cog.cog_load()
        mock_start.assert_called_once()

    async def test_cog_unload_cancels_check_loop(self) -> None:
        cog = _make_cog()
        with patch.object(cog._check_gateway, "cancel") as mock_cancel:
            await cog.cog_unload()
        mock_cancel.assert_called_once()
