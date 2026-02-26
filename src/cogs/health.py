"""Health monitoring cog for sending periodic heartbeat embeds.

Bot の死活監視を行う Cog。discord.py の tasks.loop を使い、
定期的にハートビート Embed を Discord チャンネルに送信する。

仕組み:
  - 10分ごとにハートビートを送信
  - Uptime (稼働時間)、Latency (遅延)、Guilds (サーバー数) を表示
  - レイテンシに応じて Embed の色が変わる (緑/黄/赤)
  - ログにも出力されるので Heroku logs 等でも確認可能

注意:
  Bot 自身がハートビートを送る仕組みなので、Bot がフリーズすると通知も止まる。
  「通知が来ない = 死んだかもしれない」は人間が判断する必要がある。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.bot import make_activity
from src.constants import DEFAULT_EMBED_COLOR
from src.database.engine import async_session
from src.database.models import HealthConfig
from src.services.db_service import (
    claim_event,
    cleanup_expired_events,
    delete_health_config,
    get_all_health_configs,
    get_bot_activity,
    upsert_health_config,
)

# ロガーの取得。__name__ でモジュールパスがロガー名になる
# (例: "src.cogs.health")
logger = logging.getLogger(__name__)

# ハートビートの送信間隔 (分)
_HEARTBEAT_MINUTES = 10

# 日本標準時 (JST = UTC+9)。Boot 時刻の表示に使う
_JST = timezone(timedelta(hours=9))


class HealthCog(commands.Cog):
    """定期的にハートビート Embed を送信する死活監視 Cog。"""

    # コマンドグループ
    health_group = app_commands.Group(
        name="health",
        description="ヘルスチェック通知の設定",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Bot 起動時刻を記録 (Uptime 計算用)
        # time.monotonic() はシステム起動からの秒数。時計変更に影響されない。
        self._start_time = time.monotonic()
        # Boot 時刻を JST で記録 (Embed のフッターに表示)
        self._boot_jst = datetime.now(_JST)

    async def cog_load(self) -> None:
        """Cog が読み込まれたときに呼ばれる。ハートビートループを開始する。"""
        self._heartbeat.start()

    async def cog_unload(self) -> None:
        """Cog がアンロードされたときに呼ばれる。ループを停止する。"""
        self._heartbeat.cancel()

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    @health_group.command(
        name="setup", description="このチャンネルにヘルスチェック通知を設定"
    )
    async def health_setup(self, interaction: discord.Interaction) -> None:
        """現在のチャンネルをヘルスチェック通知先として設定する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)
        except (discord.HTTPException, discord.InteractionResponded):
            return

        guild_id = str(interaction.guild.id)
        channel_id = str(interaction.channel_id)

        async with async_session() as session:
            await upsert_health_config(session, guild_id, channel_id)

        embed = discord.Embed(
            title="ヘルスチェック通知を設定しました",
            description=f"通知チャンネル: <#{channel_id}>",
            color=DEFAULT_EMBED_COLOR,
        )
        await interaction.followup.send(embed=embed)

    @health_group.command(name="disable", description="ヘルスチェック通知を停止する")
    async def health_disable(self, interaction: discord.Interaction) -> None:
        """ヘルスチェック通知を停止する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)
        except (discord.HTTPException, discord.InteractionResponded):
            return

        guild_id = str(interaction.guild.id)

        async with async_session() as session:
            deleted = await delete_health_config(session, guild_id)

        if deleted:
            embed = discord.Embed(
                title="ヘルスチェック通知を停止しました",
                color=DEFAULT_EMBED_COLOR,
            )
        else:
            embed = discord.Embed(
                title="ヘルスチェック通知は設定されていません",
                color=DEFAULT_EMBED_COLOR,
            )
        await interaction.followup.send(embed=embed)

    # ------------------------------------------------------------------
    # Heartbeat loop
    # ------------------------------------------------------------------

    @tasks.loop(minutes=_HEARTBEAT_MINUTES)
    async def _heartbeat(self) -> None:
        """10分ごとに実行されるハートビート処理。"""
        # --- Uptime の計算 ---
        uptime_sec = int(time.monotonic() - self._start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        # --- Bot の状態を取得 ---
        guild_count = len(self.bot.guilds)
        latency_ms = round(self.bot.latency * 1000)

        # --- ステータスの判定 ---
        if latency_ms < 200:
            status = "Healthy"
        elif latency_ms < 500:
            status = "Degraded"
        else:
            status = "Unhealthy"

        # --- ログ出力 ---
        logger.info(
            "[Heartbeat] %s | uptime=%s latency=%dms guilds=%d",
            status,
            uptime_str,
            latency_ms,
            guild_count,
        )

        # --- Discord チャンネルに Embed を送信 (マルチインスタンス重複防止) ---
        try:
            async with async_session() as session:
                health_configs = await get_all_health_configs(session)
        except Exception:
            logger.exception("Failed to fetch health configs")
            health_configs = []

        if health_configs:
            # 10分バケットで claim — 同一バケット内では1インスタンスのみ送信
            # フェイルオープン: DB エラー時は送信する (重複より欠落の方が問題)
            claimed = True
            try:
                bucket = int(time.time()) // 600
                event_key = f"heartbeat:{bucket}"
                async with async_session() as session:
                    claimed = await claim_event(session, event_key)
            except Exception:
                logger.debug("Failed to claim heartbeat event, proceeding anyway")

            if not claimed:
                logger.debug("Heartbeat already claimed by another instance")
            else:
                embed = self._build_embed(
                    status=status,
                    uptime_str=uptime_str,
                    latency_ms=latency_ms,
                    guild_count=guild_count,
                )
                await self._send_to_channels(health_configs, embed, "heartbeat")

        # --- 重複排除テーブルのクリーンアップ ---
        try:
            async with async_session() as session:
                deleted = await cleanup_expired_events(session)
                if deleted > 0:
                    logger.info("Cleaned up %d expired event records", deleted)
        except Exception:
            logger.exception("Failed to cleanup expired events")

        # --- Bot アクティビティの同期 (Web 管理画面からの変更を反映) ---
        try:
            async with async_session() as session:
                bot_activity = await get_bot_activity(session)
            if bot_activity:
                current = self.bot.activity
                current_name = getattr(current, "name", None)
                current_type = getattr(current, "type", None)
                type_map = {
                    "playing": discord.ActivityType.playing,
                    "listening": discord.ActivityType.listening,
                    "watching": discord.ActivityType.watching,
                    "competing": discord.ActivityType.competing,
                }
                expected_type = type_map.get(
                    bot_activity.activity_type,
                    discord.ActivityType.playing,
                )
                if (
                    current_name != bot_activity.activity_text
                    or current_type != expected_type
                ):
                    activity = make_activity(
                        bot_activity.activity_type,
                        bot_activity.activity_text,
                    )
                    await self.bot.change_presence(activity=activity)
                    logger.info(
                        "Bot activity synced: type=%s, text=%s",
                        bot_activity.activity_type,
                        bot_activity.activity_text,
                    )
        except Exception:
            logger.exception("Failed to sync bot activity")

    @_heartbeat.before_loop
    async def _before_heartbeat(self) -> None:
        """ハートビートループ開始前に1回だけ呼ばれる準備用フック。

        wait_until_ready() で Bot の Discord 接続完了を待つ。
        接続完了後、デプロイ (起動) 通知を送信する。
        """
        await self.bot.wait_until_ready()

        # --- デプロイ (起動) 通知 (マルチインスタンス重複防止) ---
        try:
            async with async_session() as session:
                health_configs = await get_all_health_configs(session)
        except Exception:
            logger.exception("Failed to fetch health configs for deploy notification")
            health_configs = []

        if health_configs:
            # Boot 時刻の分単位でユニークキーを生成
            claimed = True
            try:
                boot_key = self._boot_jst.strftime("%Y%m%d%H%M")
                event_key = f"deploy:{boot_key}"
                async with async_session() as session:
                    claimed = await claim_event(session, event_key)
            except Exception:
                logger.debug("Failed to claim deploy event, proceeding anyway")

            if not claimed:
                logger.info("Deploy notification already sent by another instance")
            else:
                embed = self._build_deploy_embed()
                await self._send_to_channels(health_configs, embed, "deploy")

    # ------------------------------------------------------------------
    # Channel send helper
    # ------------------------------------------------------------------

    async def _send_to_channels(
        self,
        configs: Sequence[HealthConfig],
        embed: discord.Embed,
        label: str,
    ) -> None:
        """設定済みの全チャンネルに Embed を送信する。"""
        for config in configs:
            channel_id = int(config.channel_id)
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                logger.warning("Health channel %d not found in cache", channel_id)
            elif not isinstance(channel, discord.TextChannel):
                logger.warning(
                    "Health channel %d is not a TextChannel (type=%s)",
                    channel_id,
                    type(channel).__name__,
                )
            else:
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException as e:
                    logger.error(
                        "Failed to send %s to channel %d: %s",
                        label,
                        channel_id,
                        e,
                    )

    # ------------------------------------------------------------------
    # Embed builder
    # ------------------------------------------------------------------

    def _build_deploy_embed(self) -> discord.Embed:
        """デプロイ (起動) 通知用の Embed を組み立てる。"""
        guild_count = len(self.bot.guilds)
        embed = discord.Embed(
            title="\U0001f680 Deploy Complete",
            color=DEFAULT_EMBED_COLOR,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="Boot",
            value=f"{self._boot_jst:%Y-%m-%d %H:%M JST}",
            inline=True,
        )
        embed.add_field(name="Guilds", value=str(guild_count), inline=True)
        return embed

    def _build_embed(
        self,
        *,
        status: str,
        uptime_str: str,
        latency_ms: int,
        guild_count: int,
    ) -> discord.Embed:
        """ハートビート用の Embed を組み立てる。"""
        if latency_ms < 200:
            color = discord.Color.green()
        elif latency_ms < 500:
            color = discord.Color.yellow()
        else:
            color = discord.Color.red()

        embed = discord.Embed(
            title=f"Heartbeat — {status}",
            color=color,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Latency", value=f"{latency_ms}ms", inline=True)
        embed.add_field(name="Guilds", value=str(guild_count), inline=True)
        embed.set_footer(text=f"Boot: {self._boot_jst:%Y-%m-%d %H:%M JST}")
        return embed


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する関数。bot.load_extension() から呼ばれる。"""
    await bot.add_cog(HealthCog(bot))
