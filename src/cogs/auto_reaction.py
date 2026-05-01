"""Auto Reaction cog.

指定チャンネルに新規投稿された (Bot 以外の) メッセージへ、設定済みの絵文字を
自動でリアクションとして付与する。

仕組み:
    - on_message イベントで投稿を検知
    - 設定済みチャンネルなら、事前パース済みの絵文字リストでリアクション
    - 1分ごとのバックグラウンドタスクでキャッシュを再構築する
      (Web 管理画面での変更は最大 60 秒で反映される)

ホットパス最適化: on_message は per-message に呼ばれるため DB アクセス・
JSON デコード・絵文字パースを全て事前計算してキャッシュする。
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from src.database.engine import async_session
from src.services.db_service import get_enabled_auto_reaction_emoji_map

logger = logging.getLogger(__name__)


def _parse_emojis(raws: list[str]) -> list[discord.PartialEmoji]:
    """絵文字文字列を PartialEmoji にパースする (キャッシュ更新時に1回)。"""
    return [discord.PartialEmoji.from_str(r) for r in raws]


class AutoReactionCog(commands.Cog):
    """AutoReaction 機能を提供する Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # channel_id → 事前パース済み PartialEmoji リスト。
        # None は「未初期化」を意味し on_message は何もしない (DB フォールバックなし:
        # 起動直後の超短時間だけ。次の cog_load/refresh で必ず初期化される)。
        self._configs: dict[str, list[discord.PartialEmoji]] | None = None

    async def cog_load(self) -> None:
        self._refresh_cache.start()
        logger.info("AutoReaction cog loaded, cache refresh loop started")

    async def cog_unload(self) -> None:
        if self._refresh_cache.is_running():
            self._refresh_cache.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or not message.author:
            return
        if message.author.bot:
            return
        if self._configs is None:
            return

        emojis = self._configs.get(str(message.channel.id))
        if not emojis:
            return

        for emoji in emojis:
            try:
                await message.add_reaction(emoji)
            except discord.HTTPException:
                logger.warning(
                    "AutoReaction: Failed to add %r to message %s in channel %s",
                    emoji,
                    message.id,
                    message.channel.id,
                )

    @tasks.loop(minutes=1)
    async def _refresh_cache(self) -> None:
        async with async_session() as session:
            raw_map = await get_enabled_auto_reaction_emoji_map(session)
        self._configs = {cid: _parse_emojis(raws) for cid, raws in raw_map.items()}

    @_refresh_cache.before_loop
    async def _before_refresh_cache(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録し、絵文字キャッシュを初期化する。"""
    cog = AutoReactionCog(bot)
    await bot.add_cog(cog)

    try:
        async with async_session() as session:
            raw_map = await get_enabled_auto_reaction_emoji_map(session)
        cog._configs = {cid: _parse_emojis(raws) for cid, raws in raw_map.items()}
    except Exception:
        logger.exception("Failed to load auto_reaction cache")
