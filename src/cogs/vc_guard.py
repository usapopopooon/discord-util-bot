"""VC limit guard cog.

監視対象 VC の人数制限を、Move Members などで超えて入室したメンバーを
自動で切断する。
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.constants import DEFAULT_EMBED_COLOR
from src.database.engine import async_session
from src.services.vc_guard_service import (
    delete_vc_guard_config_by_channel,
    delete_vc_guard_configs_by_channel_ids,
    get_enabled_vc_guard_channel_map,
    get_vc_guard_configs,
    upsert_vc_guard_config,
)

logger = logging.getLogger(__name__)


async def _ensure_can_manage_vcguard(interaction: discord.Interaction) -> bool:
    """VCGuard コマンド実行権限を実行時にも確認する。"""
    user = interaction.user
    if isinstance(user, discord.Member) and user.guild_permissions.move_members:
        return True

    await interaction.response.send_message(
        "このコマンドを使うには「メンバーを移動」権限が必要です。",
        ephemeral=True,
    )
    return False


class VCGuardCog(commands.Cog):
    """VCGuard 機能を提供する Cog。"""

    vcguard_group = app_commands.Group(
        name="vcguard",
        description="VC 人数制限ガードの設定",
        default_permissions=discord.Permissions(move_members=True),
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._configs: dict[str, set[str]] | None = None
        self._startup_cleanup_task: asyncio.Task[None] | None = None

    async def cog_load(self) -> None:
        """Cog 読み込み時にキャッシュ更新と孤立設定掃除を開始する。"""
        self._refresh_cache.start()
        self._cleanup_missing_channels.start()
        self._startup_cleanup_task = asyncio.create_task(
            self._startup_cleanup_missing_channels()
        )
        logger.info("VCGuard cog loaded")

    async def cog_unload(self) -> None:
        """Cog アンロード時にバックグラウンドタスクを停止する。"""
        if self._refresh_cache.is_running():
            self._refresh_cache.cancel()
        if self._cleanup_missing_channels.is_running():
            self._cleanup_missing_channels.cancel()
        if self._startup_cleanup_task and not self._startup_cleanup_task.done():
            self._startup_cleanup_task.cancel()

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    @vcguard_group.command(name="set", description="監視対象 VC を設定する")
    @app_commands.describe(channel="監視するボイスチャンネル")
    async def vcguard_set(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
    ) -> None:
        """指定 VC を監視対象に追加する。"""
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return
        if not await _ensure_can_manage_vcguard(interaction):
            return

        try:
            await interaction.response.defer(ephemeral=True)
        except (discord.HTTPException, discord.InteractionResponded):
            return

        if channel.guild.id != interaction.guild.id:
            await interaction.followup.send(
                "同じサーバー内の VC を指定してください。", ephemeral=True
            )
            return

        async with async_session() as session:
            await upsert_vc_guard_config(
                session,
                guild_id=str(interaction.guild.id),
                channel_id=str(channel.id),
            )
        await self._load_cache()

        await interaction.followup.send(
            f"VCGuard を設定しました: {channel.mention}", ephemeral=True
        )

    @vcguard_group.command(name="unset", description="監視対象 VC の設定を解除する")
    @app_commands.describe(channel="解除するボイスチャンネル")
    async def vcguard_unset(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
    ) -> None:
        """指定 VC の監視設定を削除する。"""
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return
        if not await _ensure_can_manage_vcguard(interaction):
            return

        try:
            await interaction.response.defer(ephemeral=True)
        except (discord.HTTPException, discord.InteractionResponded):
            return

        async with async_session() as session:
            deleted = await delete_vc_guard_config_by_channel(
                session,
                guild_id=str(interaction.guild.id),
                channel_id=str(channel.id),
            )
        await self._load_cache()

        if deleted:
            message = f"VCGuard 設定を解除しました: {channel.mention}"
        else:
            message = f"VCGuard は設定されていません: {channel.mention}"
        await interaction.followup.send(message, ephemeral=True)

    @vcguard_group.command(name="list", description="監視対象 VC の一覧を表示する")
    async def vcguard_list(self, interaction: discord.Interaction) -> None:
        """現在のサーバーの VCGuard 設定一覧を表示する。"""
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return
        if not await _ensure_can_manage_vcguard(interaction):
            return

        try:
            await interaction.response.defer(ephemeral=True)
        except (discord.HTTPException, discord.InteractionResponded):
            return

        async with async_session() as session:
            configs = await get_vc_guard_configs(session, str(interaction.guild.id))

        if not configs:
            await interaction.followup.send(
                "VCGuard は設定されていません。", ephemeral=True
            )
            return

        lines = []
        for config in configs:
            channel = interaction.guild.get_channel(int(config.channel_id))
            label = channel.mention if channel else f"`{config.channel_id}` (削除済み)"
            status = "有効" if config.enabled else "無効"
            lines.append(f"- {label}: {status}")

        embed = discord.Embed(
            title="VCGuard 設定一覧",
            description="\n".join(lines),
            color=DEFAULT_EMBED_COLOR,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # Event listeners
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """監視対象 VC への入室時に、人数制限超過なら入室者を切断する。"""
        if member.bot or after.channel is None:
            return
        if before.channel and before.channel.id == after.channel.id:
            return
        if not isinstance(after.channel, discord.VoiceChannel):
            return
        if self._configs is None:
            return

        guild_id = str(member.guild.id)
        channel_id = str(after.channel.id)
        if channel_id not in self._configs.get(guild_id, set()):
            return

        user_limit = after.channel.user_limit
        if user_limit <= 0 or len(after.channel.members) <= user_limit:
            return

        try:
            await member.move_to(
                None,
                reason="VCGuard: VC の人数制限を超過したため切断",
            )
            logger.info(
                "VCGuard disconnected member=%s from channel=%s guild=%s "
                "members=%s limit=%s",
                member.id,
                after.channel.id,
                member.guild.id,
                len(after.channel.members),
                user_limit,
            )
        except discord.HTTPException:
            logger.exception(
                "VCGuard failed to disconnect member=%s from channel=%s guild=%s",
                member.id,
                after.channel.id,
                member.guild.id,
            )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """監視対象 VC が削除されたら設定も削除する。"""
        if not isinstance(channel, discord.VoiceChannel):
            return

        async with async_session() as session:
            deleted = await delete_vc_guard_config_by_channel(
                session,
                guild_id=str(channel.guild.id),
                channel_id=str(channel.id),
            )
        if deleted:
            await self._load_cache()
            logger.info(
                "VCGuard config cleaned up for deleted channel=%s guild=%s",
                channel.id,
                channel.guild.id,
            )

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    @tasks.loop(minutes=1)
    async def _refresh_cache(self) -> None:
        await self._load_cache()

    @_refresh_cache.before_loop
    async def _before_refresh_cache(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def _cleanup_missing_channels(self) -> None:
        """Bot 起動中に見えない孤立 VCGuard 設定を定期的に削除する。"""
        await self._cleanup_missing_channel_configs()

    @_cleanup_missing_channels.before_loop
    async def _before_cleanup_missing_channels(self) -> None:
        await self.bot.wait_until_ready()

    async def _startup_cleanup_missing_channels(self) -> None:
        await self.bot.wait_until_ready()
        await self._cleanup_missing_channel_configs()

    async def _cleanup_missing_channel_configs(self) -> None:
        """Bot から見えない孤立 VCGuard 設定を削除する。"""
        if self._configs is None:
            await self._load_cache()

        missing: set[str] = set()
        for guild_id, channel_ids in (self._configs or {}).items():
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                missing.update(channel_ids)
                continue
            for channel_id in channel_ids:
                channel = guild.get_channel(int(channel_id))
                if not isinstance(channel, discord.VoiceChannel):
                    missing.add(channel_id)

        if not missing:
            return

        async with async_session() as session:
            deleted = await delete_vc_guard_configs_by_channel_ids(session, missing)
        if deleted:
            await self._load_cache()
            logger.info("VCGuard cleaned up %s missing channel configs", deleted)

    async def _load_cache(self) -> None:
        async with async_session() as session:
            self._configs = await get_enabled_vc_guard_channel_map(session)


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録し、設定キャッシュを初期化する。"""
    cog = VCGuardCog(bot)
    await bot.add_cog(cog)

    try:
        await cog._load_cache()
    except Exception:
        logger.exception("Failed to load VCGuard cache")
