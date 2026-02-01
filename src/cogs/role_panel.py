"""Role panel cog for role assignment via buttons/reactions.

ボタンまたはリアクションでロールを付与/解除するパネル機能を提供する Cog。

機能:
  - /rolepanel create: パネル作成
  - /rolepanel add: ロール追加
  - /rolepanel remove: ロール削除
  - /rolepanel delete: パネル削除
  - /rolepanel list: パネル一覧

対応形式:
  - button: ボタン式 (推奨)
  - reaction: リアクション式
"""

import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from src.database.engine import async_session
from src.services.db_service import (
    add_role_panel_item,
    delete_discord_channel,
    delete_discord_channels_by_guild,
    delete_discord_guild,
    delete_discord_role,
    delete_discord_roles_by_guild,
    delete_role_panel,
    get_all_role_panels,
    get_role_panel_by_message_id,
    get_role_panel_item_by_emoji,
    get_role_panel_items,
    get_role_panels_by_channel,
    remove_role_panel_item,
    upsert_discord_channel,
    upsert_discord_guild,
    upsert_discord_role,
)
from src.ui.role_panel_view import (
    RolePanelCreateModal,
    RolePanelView,
    refresh_role_panel,
)

logger = logging.getLogger(__name__)


class RolePanelCog(commands.Cog):
    """ロールパネル機能を提供する Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Cog 読み込み時に永続 View を登録する。"""
        async with async_session() as db_session:
            panels = await get_all_role_panels(db_session)
            for panel in panels:
                if panel.panel_type == "button":
                    items = await get_role_panel_items(db_session, panel.id)
                    view = RolePanelView(panel.id, items)
                    self.bot.add_view(view)
                    logger.debug("Registered role panel view for panel %d", panel.id)

        logger.info(
            "Loaded %d role panel views",
            len([p for p in panels if p.panel_type == "button"]),
        )

    # -------------------------------------------------------------------------
    # コマンドグループ
    # -------------------------------------------------------------------------

    rolepanel = app_commands.Group(
        name="rolepanel",
        description="ロールパネルの作成・管理",
        default_permissions=discord.Permissions(manage_roles=True),
    )

    @rolepanel.command(name="create", description="ロールパネルを作成する")
    @app_commands.describe(
        panel_type="パネルの種類 (button: ボタン式, reaction: リアクション式)",
        channel="パネルを送信するチャンネル (省略時: 現在のチャンネル)",
        remove_reaction="リアクション自動削除 (カウントを常に 1 に保つ)",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        panel_type: Literal["button", "reaction"],
        channel: discord.TextChannel | None = None,
        remove_reaction: bool = False,
    ) -> None:
        """ロールパネルを作成する。"""
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "テキストチャンネルを指定してください。", ephemeral=True
            )
            return

        modal = RolePanelCreateModal(panel_type, target_channel.id, remove_reaction)
        await interaction.response.send_modal(modal)

    @rolepanel.command(name="add", description="ロールパネルにロールを追加する")
    @app_commands.describe(
        role="追加するロール",
        emoji="ボタン/リアクションに使う絵文字",
        label="ボタンのラベル (ボタン式のみ)",
        style="ボタンのスタイル (ボタン式のみ)",
    )
    async def add(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        emoji: str,
        label: str | None = None,
        style: Literal["primary", "secondary", "success", "danger"] = "secondary",
    ) -> None:
        """ロールパネルにロールを追加する。"""
        if interaction.channel is None:
            await interaction.response.send_message(
                "チャンネルが見つかりません。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            # チャンネル内のパネルを取得
            panels = await get_role_panels_by_channel(
                db_session, str(interaction.channel.id)
            )
            if not panels:
                await interaction.response.send_message(
                    "このチャンネルにロールパネルがありません。\n"
                    "先に `/rolepanel create` でパネルを作成してください。",
                    ephemeral=True,
                )
                return

            # 最新のパネルを使用
            panel = panels[-1]

            # 既に同じ絵文字が使われていないか確認
            existing = await get_role_panel_item_by_emoji(db_session, panel.id, emoji)
            if existing:
                await interaction.response.send_message(
                    f"絵文字 {emoji} は既に使用されています。", ephemeral=True
                )
                return

            # ロールを追加
            await add_role_panel_item(
                db_session,
                panel_id=panel.id,
                role_id=str(role.id),
                emoji=emoji,
                label=label,
                style=style,
            )

            # パネルを更新
            items = await get_role_panel_items(db_session, panel.id)
            channel = (
                interaction.guild.get_channel(int(panel.channel_id))
                if interaction.guild
                else None
            )
            if isinstance(channel, discord.TextChannel):
                await refresh_role_panel(channel, panel, items, self.bot)

        await interaction.response.send_message(
            f"ロール {role.mention} ({emoji}) を追加しました。",
            ephemeral=True,
        )

    @rolepanel.command(name="remove", description="ロールパネルからロールを削除する")
    @app_commands.describe(emoji="削除するロールの絵文字")
    async def remove(
        self,
        interaction: discord.Interaction,
        emoji: str,
    ) -> None:
        """ロールパネルからロールを削除する。"""
        if interaction.channel is None:
            await interaction.response.send_message(
                "チャンネルが見つかりません。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            panels = await get_role_panels_by_channel(
                db_session, str(interaction.channel.id)
            )
            if not panels:
                await interaction.response.send_message(
                    "このチャンネルにロールパネルがありません。", ephemeral=True
                )
                return

            panel = panels[-1]

            # ロールを削除
            success = await remove_role_panel_item(db_session, panel.id, emoji)
            if not success:
                await interaction.response.send_message(
                    f"絵文字 {emoji} のロールが見つかりません。", ephemeral=True
                )
                return

            # パネルを更新
            items = await get_role_panel_items(db_session, panel.id)
            channel = (
                interaction.guild.get_channel(int(panel.channel_id))
                if interaction.guild
                else None
            )
            if isinstance(channel, discord.TextChannel):
                await refresh_role_panel(channel, panel, items, self.bot)

        await interaction.response.send_message(
            f"ロール ({emoji}) を削除しました。", ephemeral=True
        )

    @rolepanel.command(name="delete", description="ロールパネルを削除する")
    async def delete(self, interaction: discord.Interaction) -> None:
        """ロールパネルを削除する。"""
        if interaction.channel is None:
            await interaction.response.send_message(
                "チャンネルが見つかりません。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            panels = await get_role_panels_by_channel(
                db_session, str(interaction.channel.id)
            )
            if not panels:
                await interaction.response.send_message(
                    "このチャンネルにロールパネルがありません。", ephemeral=True
                )
                return

            panel = panels[-1]

            # Discord 上のメッセージを削除
            if panel.message_id and interaction.guild:
                channel = interaction.guild.get_channel(int(panel.channel_id))
                if isinstance(channel, discord.TextChannel):
                    try:
                        msg = await channel.fetch_message(int(panel.message_id))
                        await msg.delete()
                    except discord.HTTPException:
                        pass  # メッセージが既に削除されている場合は無視

            # DB からパネルを削除
            await delete_role_panel(db_session, panel.id)

        await interaction.response.send_message(
            "ロールパネルを削除しました。", ephemeral=True
        )

    @rolepanel.command(name="list", description="ロールパネルの一覧を表示する")
    async def list_panels(self, interaction: discord.Interaction) -> None:
        """ロールパネルの一覧を表示する。"""
        if interaction.guild is None:
            await interaction.response.send_message(
                "サーバー内でのみ使用できます。", ephemeral=True
            )
            return

        from src.services.db_service import get_role_panels_by_guild

        async with async_session() as db_session:
            panels = await get_role_panels_by_guild(
                db_session, str(interaction.guild.id)
            )
            if not panels:
                await interaction.response.send_message(
                    "このサーバーにロールパネルはありません。", ephemeral=True
                )
                return

            embed = discord.Embed(
                title="ロールパネル一覧",
                color=discord.Color.blue(),
            )

            for panel in panels:
                items = await get_role_panel_items(db_session, panel.id)
                channel = interaction.guild.get_channel(int(panel.channel_id))
                channel_mention = (
                    channel.mention if channel else f"(不明: {panel.channel_id})"
                )

                role_count = len(items)
                embed.add_field(
                    name=f"{panel.title} ({panel.panel_type})",
                    value=f"チャンネル: {channel_mention}\nロール数: {role_count}",
                    inline=False,
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------------------------------------------------------------------------
    # リアクションイベント
    # -------------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        """リアクション追加イベント。リアクション式ロールパネル用。"""
        await self._handle_reaction(payload, "add")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        """リアクション削除イベント。リアクション式ロールパネル用。"""
        await self._handle_reaction(payload, "remove")

    async def _handle_reaction(
        self, payload: discord.RawReactionActionEvent, action: str
    ) -> None:
        """リアクションイベントを処理する。"""
        # Bot 自身のリアクションは無視
        if payload.user_id == self.bot.user.id:  # type: ignore[union-attr]
            return

        async with async_session() as db_session:
            # パネルを取得
            panel = await get_role_panel_by_message_id(
                db_session, str(payload.message_id)
            )
            if panel is None or panel.panel_type != "reaction":
                return

            # 絵文字からロールを取得
            emoji_str = str(payload.emoji)
            item = await get_role_panel_item_by_emoji(db_session, panel.id, emoji_str)
            if item is None:
                return

            # remove_reaction モードの情報を保持
            remove_reaction_mode = panel.remove_reaction

        # ギルドとメンバーを取得
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if guild is None:
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.HTTPException:
                return

        if member.bot:
            return

        role = guild.get_role(int(item.role_id))
        if role is None:
            logger.warning("Role %s not found for panel %d", item.role_id, panel.id)
            return

        try:
            if remove_reaction_mode:
                # リアクション自動削除モード: 追加時のみトグル動作
                if action == "add":
                    # ユーザーのリアクションを削除してカウントを 1 に保つ
                    channel = guild.get_channel(payload.channel_id)
                    if isinstance(channel, discord.TextChannel):
                        try:
                            msg = await channel.fetch_message(payload.message_id)
                            await msg.remove_reaction(payload.emoji, member)
                        except discord.HTTPException:
                            pass  # 削除失敗は無視

                    # ロールをトグル
                    if role in member.roles:
                        await member.remove_roles(
                            role, reason="ロールパネル (リアクション) から解除"
                        )
                        logger.debug(
                            "Removed role %s from user %s via reaction (toggle)",
                            role.name,
                            member.display_name,
                        )
                    else:
                        await member.add_roles(
                            role, reason="ロールパネル (リアクション) から付与"
                        )
                        logger.debug(
                            "Added role %s to user %s via reaction (toggle)",
                            role.name,
                            member.display_name,
                        )
                # remove イベントは無視 (Bot がリアクションを削除しただけ)
            else:
                # 通常モード: リアクション追加で付与、削除で解除
                if action == "add":
                    if role not in member.roles:
                        await member.add_roles(
                            role, reason="ロールパネル (リアクション) から付与"
                        )
                        logger.debug(
                            "Added role %s to user %s via reaction",
                            role.name,
                            member.display_name,
                        )
                else:  # remove
                    if role in member.roles:
                        await member.remove_roles(
                            role, reason="ロールパネル (リアクション) から解除"
                        )
                        logger.debug(
                            "Removed role %s from user %s via reaction",
                            role.name,
                            member.display_name,
                        )
        except discord.Forbidden:
            logger.warning("No permission to modify role %s", role.name)
        except discord.HTTPException as e:
            logger.error("Failed to modify role: %s", e)

    # -------------------------------------------------------------------------
    # 同期イベント (ギルド、チャンネル、ロール)
    # -------------------------------------------------------------------------

    # 同期対象のチャンネルタイプ (テキスト系のみ)
    SYNC_CHANNEL_TYPES = {
        discord.ChannelType.text,  # 0
        discord.ChannelType.news,  # 5 (announcement)
        discord.ChannelType.forum,  # 15
    }

    async def _sync_guild_info(self, guild: discord.Guild) -> None:
        """ギルド情報を DB に同期する。

        Args:
            guild: Discord ギルド
        """
        async with async_session() as db_session:
            await upsert_discord_guild(
                db_session,
                guild_id=str(guild.id),
                guild_name=guild.name,
                icon_hash=guild.icon.key if guild.icon else None,
                member_count=guild.member_count or 0,
            )

    async def _sync_guild_channels(self, guild: discord.Guild) -> int:
        """ギルドのチャンネル情報を DB に同期する。

        Args:
            guild: Discord ギルド

        Returns:
            同期したチャンネル数
        """
        count = 0
        async with async_session() as db_session:
            for channel in guild.channels:
                # テキスト系チャンネルのみ同期
                if channel.type not in self.SYNC_CHANNEL_TYPES:
                    continue
                # Bot が見えるチャンネルのみ
                if not channel.permissions_for(guild.me).view_channel:
                    continue

                await upsert_discord_channel(
                    db_session,
                    guild_id=str(guild.id),
                    channel_id=str(channel.id),
                    channel_name=channel.name,
                    channel_type=channel.type.value,
                    position=channel.position,
                    category_id=str(channel.category_id) if channel.category_id else None,
                )
                count += 1
        return count

    async def _sync_guild_roles(self, guild: discord.Guild) -> int:
        """ギルドのロール情報を DB に同期する。

        Args:
            guild: Discord ギルド

        Returns:
            同期したロール数
        """
        count = 0
        async with async_session() as db_session:
            for role in guild.roles:
                # @everyone ロールとマネージドロール (Bot ロール等) は除外
                if role.is_default() or role.managed:
                    continue
                await upsert_discord_role(
                    db_session,
                    guild_id=str(guild.id),
                    role_id=str(role.id),
                    role_name=role.name,
                    color=role.color.value,
                    position=role.position,
                )
                count += 1
        return count

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Bot 起動時に全ギルドの情報を同期する。"""
        total_roles = 0
        total_channels = 0
        for guild in self.bot.guilds:
            # ギルド情報を同期
            await self._sync_guild_info(guild)
            # ロールを同期
            role_count = await self._sync_guild_roles(guild)
            total_roles += role_count
            # チャンネルを同期
            channel_count = await self._sync_guild_channels(guild)
            total_channels += channel_count
            logger.debug(
                "Synced %d roles, %d channels for guild %s",
                role_count,
                channel_count,
                guild.name,
            )
        logger.info(
            "Synced %d guilds, %d roles, %d channels",
            len(self.bot.guilds),
            total_roles,
            total_channels,
        )

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """新しいギルドに参加したときに情報を同期する。"""
        await self._sync_guild_info(guild)
        role_count = await self._sync_guild_roles(guild)
        channel_count = await self._sync_guild_channels(guild)
        logger.info(
            "Synced %d roles, %d channels for new guild %s",
            role_count,
            channel_count,
            guild.name,
        )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """ギルドから退出したときにキャッシュを削除する。"""
        async with async_session() as db_session:
            role_count = await delete_discord_roles_by_guild(db_session, str(guild.id))
            channel_count = await delete_discord_channels_by_guild(
                db_session, str(guild.id)
            )
            await delete_discord_guild(db_session, str(guild.id))
            logger.info(
                "Deleted guild info, %d roles, %d channels for guild %s",
                role_count,
                channel_count,
                guild.name,
            )

    @commands.Cog.listener()
    async def on_guild_update(
        self, before: discord.Guild, after: discord.Guild
    ) -> None:
        """ギルド情報が更新されたときに DB を更新する。"""
        # 名前やアイコンが変わった場合のみ更新
        if before.name != after.name or before.icon != after.icon:
            await self._sync_guild_info(after)
            logger.debug("Updated guild info for %s", after.name)

    # -------------------------------------------------------------------------
    # ロールイベント
    # -------------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        """ロールが作成されたときに DB に追加する。"""
        if role.is_default() or role.managed:
            return
        async with async_session() as db_session:
            await upsert_discord_role(
                db_session,
                guild_id=str(role.guild.id),
                role_id=str(role.id),
                role_name=role.name,
                color=role.color.value,
                position=role.position,
            )
            logger.debug("Added role %s to cache", role.name)

    @commands.Cog.listener()
    async def on_guild_role_update(
        self, _before: discord.Role, after: discord.Role
    ) -> None:
        """ロールが更新されたときに DB を更新する。"""
        if after.is_default() or after.managed:
            return
        async with async_session() as db_session:
            await upsert_discord_role(
                db_session,
                guild_id=str(after.guild.id),
                role_id=str(after.id),
                role_name=after.name,
                color=after.color.value,
                position=after.position,
            )
            logger.debug("Updated role %s in cache", after.name)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """ロールが削除されたときに DB から削除する。"""
        async with async_session() as db_session:
            await delete_discord_role(db_session, str(role.guild.id), str(role.id))
            logger.debug("Deleted role %s from cache", role.name)

    # -------------------------------------------------------------------------
    # チャンネルイベント
    # -------------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_channel_create(
        self, channel: discord.abc.GuildChannel
    ) -> None:
        """チャンネルが作成されたときに DB に追加する。"""
        if channel.type not in self.SYNC_CHANNEL_TYPES:
            return
        if not channel.permissions_for(channel.guild.me).view_channel:
            return

        async with async_session() as db_session:
            await upsert_discord_channel(
                db_session,
                guild_id=str(channel.guild.id),
                channel_id=str(channel.id),
                channel_name=channel.name,
                channel_type=channel.type.value,
                position=channel.position,
                category_id=str(channel.category_id) if channel.category_id else None,
            )
            logger.debug("Added channel %s to cache", channel.name)

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        """チャンネルが更新されたときに DB を更新する。"""
        if after.type not in self.SYNC_CHANNEL_TYPES:
            # タイプが変わって対象外になった場合は削除
            async with async_session() as db_session:
                await delete_discord_channel(
                    db_session, str(after.guild.id), str(after.id)
                )
            return

        if not after.permissions_for(after.guild.me).view_channel:
            # 権限がなくなった場合も削除
            async with async_session() as db_session:
                await delete_discord_channel(
                    db_session, str(after.guild.id), str(after.id)
                )
            return

        async with async_session() as db_session:
            await upsert_discord_channel(
                db_session,
                guild_id=str(after.guild.id),
                channel_id=str(after.id),
                channel_name=after.name,
                channel_type=after.type.value,
                position=after.position,
                category_id=str(after.category_id) if after.category_id else None,
            )
            logger.debug("Updated channel %s in cache", after.name)

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self, channel: discord.abc.GuildChannel
    ) -> None:
        """チャンネルが削除されたときに DB から削除する。"""
        async with async_session() as db_session:
            await delete_discord_channel(
                db_session, str(channel.guild.id), str(channel.id)
            )
            logger.debug("Deleted channel %s from cache", channel.name)


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する。"""
    await bot.add_cog(RolePanelCog(bot))
