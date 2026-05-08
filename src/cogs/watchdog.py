"""Gateway watchdog cog.

Discord Gateway からのイベント受信が長時間途絶した場合にプロセスを終了させる。
Railway の再起動ポリシーに依存して、新しいコンテナで egress 経路を引き直す
ことを期待する。

仕組み:
  - Gateway から何らかのイベントを受信するたびに最終受信時刻を更新する。
    Discord は idle な Bot にも約 41 秒ごとに HEARTBEAT_ACK を送ってくるため、
    正常時は常に更新され続ける。
  - 30 秒ごとに「最終受信からの経過時間」をチェックし、閾値を超えたら
    os._exit(1) で即終了する。

注意:
  - Railway の restart policy が ALWAYS / ON_FAILURE になっていることが前提。
  - os._exit() は asyncio のクリーンアップを行わないが、Gateway が死んでいる
    状況で graceful close を試みても無駄なため、即時終了を選択している。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Final

from discord.ext import commands, tasks

logger = logging.getLogger(__name__)

# Gateway 無音許容時間 (秒)。
# 内訳の目安: 60s (ws_connect timeout) + 128s (新バックオフ上限) = 188s 1サイクル。
# Railway の restartPolicyMaxRetries=10 と組み合わせて約 100 分間の自動回復試行
# を確保するため、過剰な再起動を抑える方向で 600s (10 分) に設定。
_STALE_THRESHOLD_SECONDS: Final[int] = 600

# 監視タスクの実行間隔 (秒)。
_CHECK_INTERVAL_SECONDS: Final[int] = 30


class WatchdogCog(commands.Cog):
    """Gateway 接続が長時間途絶した場合にプロセスを終了させる Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # 最後に Gateway からイベントを受信した時刻 (monotonic 秒)。
        # 起動直後はまだ受信していないので現在時刻で初期化し、
        # _before_check() で wait_until_ready() 後に再初期化する。
        self._last_event_at: float = time.monotonic()

    async def cog_load(self) -> None:
        self._check_gateway.start()

    async def cog_unload(self) -> None:
        self._check_gateway.cancel()

    @commands.Cog.listener()
    async def on_socket_event_type(self, event_type: str) -> None:
        """Gateway から何らかのイベントを受信するたびに呼ばれる。"""
        self._last_event_at = time.monotonic()
        logger.debug("Gateway event received: %s", event_type)

    @tasks.loop(seconds=_CHECK_INTERVAL_SECONDS)
    async def _check_gateway(self) -> None:
        elapsed = time.monotonic() - self._last_event_at
        if elapsed > _STALE_THRESHOLD_SECONDS:
            logger.critical(
                "Gateway has been silent for %.0fs (threshold=%ds). "
                "Exiting to trigger Railway restart.",
                elapsed,
                _STALE_THRESHOLD_SECONDS,
            )
            # asyncio クリーンアップを待たずに即時終了。
            # Gateway が死んでいる状況で bot.close() は応答しない可能性が高い。
            os._exit(1)

    @_check_gateway.before_loop
    async def _before_check(self) -> None:
        # Gateway 接続完了 (READY 受信) まで待ち、そこから計測を開始する。
        await self.bot.wait_until_ready()
        self._last_event_at = time.monotonic()
        logger.info(
            "Watchdog started: stale_threshold=%ds, check_interval=%ds",
            _STALE_THRESHOLD_SECONDS,
            _CHECK_INTERVAL_SECONDS,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WatchdogCog(bot))
