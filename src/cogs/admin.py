"""Admin slash commands.

管理者用コマンドの Cog。
- /admin cleanup: 孤立したDBレコードをクリーンアップ
- /admin activity: Bot のアクティビティ（プレゼンス）を変更
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.bot import make_activity
from src.constants import DEFAULT_EMBED_COLOR
from src.database.engine import async_session
from src.services.db_service import (
    delete_bump_config,
    delete_bump_reminders_by_guild,
    delete_lobbies_by_guild,
    delete_role_panels_by_guild,
    delete_sticky_messages_by_guild,
    get_all_bump_configs,
    get_all_lobbies,
    get_all_role_panels,
    get_all_sticky_messages,
    upsert_bot_activity,
)

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    """管理者用コマンドの Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    admin_group = app_commands.Group(
        name="admin",
        description="管理者用コマンド",
        default_permissions=discord.Permissions(administrator=True),
    )

    @admin_group.command(name="cleanup", description="孤立したDBレコードを削除")
    async def cleanup(self, interaction: discord.Interaction) -> None:
        """孤立したDBレコードをクリーンアップする。

        以下のデータを削除します:
        - Bot が参加していないギルドのデータ
        - 存在しないチャンネルに紐づくデータ
        """
        await interaction.response.defer(ephemeral=True)

        # 現在 Bot が参加しているギルド ID のセット
        current_guild_ids = {str(guild.id) for guild in self.bot.guilds}

        # 各ギルドのチャンネル ID マップを構築
        channel_ids_by_guild: dict[str, set[str]] = {}
        for guild in self.bot.guilds:
            channel_ids = set()
            for channel in guild.channels:
                channel_ids.add(str(channel.id))
            channel_ids_by_guild[str(guild.id)] = channel_ids

        results: list[str] = []

        async with async_session() as session:
            # 1. ロビーのクリーンアップ (VoiceSession もカスケード削除される)
            lobbies = await get_all_lobbies(session)
            orphaned_lobby_guilds: set[str] = set()

            for lobby in lobbies:
                if lobby.guild_id not in current_guild_ids:
                    orphaned_lobby_guilds.add(lobby.guild_id)

            # ギルド単位で削除
            for guild_id in orphaned_lobby_guilds:
                count = await delete_lobbies_by_guild(session, guild_id)
                if count > 0:
                    results.append(f"ロビー: ギルド {guild_id} から {count} 件削除")

            # 2. Bump 設定のクリーンアップ
            bump_configs = await get_all_bump_configs(session)
            for config in bump_configs:
                if config.guild_id not in current_guild_ids:
                    await delete_bump_config(session, config.guild_id)
                    await delete_bump_reminders_by_guild(session, config.guild_id)
                    results.append(f"Bump: ギルド {config.guild_id} から削除")
                elif config.channel_id not in channel_ids_by_guild.get(
                    config.guild_id, set()
                ):
                    await delete_bump_config(session, config.guild_id)
                    await delete_bump_reminders_by_guild(session, config.guild_id)
                    results.append(f"Bump: CH削除のため {config.guild_id} から削除")

            # 3. Sticky メッセージのクリーンアップ
            stickies = await get_all_sticky_messages(session)
            orphaned_sticky_guilds: set[str] = set()

            for sticky in stickies:
                if sticky.guild_id not in current_guild_ids:
                    orphaned_sticky_guilds.add(sticky.guild_id)

            for guild_id in orphaned_sticky_guilds:
                count = await delete_sticky_messages_by_guild(session, guild_id)
                if count > 0:
                    results.append(f"Sticky: ギルド {guild_id} から {count} 件削除")

            # 4. ロールパネルのクリーンアップ
            role_panels = await get_all_role_panels(session)
            orphaned_panel_guilds: set[str] = set()

            for panel in role_panels:
                if panel.guild_id not in current_guild_ids:
                    orphaned_panel_guilds.add(panel.guild_id)

            for guild_id in orphaned_panel_guilds:
                count = await delete_role_panels_by_guild(session, guild_id)
                if count > 0:
                    results.append(f"パネル: ギルド {guild_id} から {count} 件削除")

        if results:
            message = "**クリーンアップ完了:**\n" + "\n".join(f"- {r}" for r in results)
            logger.info("Admin cleanup executed: %s", results)
        else:
            message = "クリーンアップ対象のデータはありませんでした。"
            logger.info("Admin cleanup executed: no orphaned data found")

        await interaction.followup.send(message, ephemeral=True)

    @admin_group.command(name="stats", description="DB統計情報を表示")
    async def stats(self, interaction: discord.Interaction) -> None:
        """現在のDB統計情報を表示する。"""
        await interaction.response.defer(ephemeral=True)

        current_guild_ids = {str(guild.id) for guild in self.bot.guilds}

        async with async_session() as session:
            lobbies = await get_all_lobbies(session)
            bump_configs = await get_all_bump_configs(session)
            stickies = await get_all_sticky_messages(session)
            role_panels = await get_all_role_panels(session)

            # 孤立データのカウント
            orphaned_lobbies = sum(
                1 for lobby in lobbies if lobby.guild_id not in current_guild_ids
            )
            orphaned_bumps = sum(
                1 for c in bump_configs if c.guild_id not in current_guild_ids
            )
            orphaned_stickies = sum(
                1 for s in stickies if s.guild_id not in current_guild_ids
            )
            orphaned_panels = sum(
                1 for p in role_panels if p.guild_id not in current_guild_ids
            )

        embed = discord.Embed(title="DB統計情報", color=DEFAULT_EMBED_COLOR)
        embed.add_field(
            name="ロビー",
            value=f"総数: {len(lobbies)}\n孤立: {orphaned_lobbies}",
            inline=True,
        )
        embed.add_field(
            name="Bump設定",
            value=f"総数: {len(bump_configs)}\n孤立: {orphaned_bumps}",
            inline=True,
        )
        embed.add_field(
            name="Sticky",
            value=f"総数: {len(stickies)}\n孤立: {orphaned_stickies}",
            inline=True,
        )
        embed.add_field(
            name="ロールパネル",
            value=f"総数: {len(role_panels)}\n孤立: {orphaned_panels}",
            inline=True,
        )
        embed.add_field(
            name="参加ギルド数",
            value=str(len(self.bot.guilds)),
            inline=True,
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @admin_group.command(
        name="activity", description="Bot のアクティビティ（プレゼンス）を変更"
    )
    @app_commands.describe(
        activity_type="アクティビティの種類",
        text="表示テキスト",
    )
    @app_commands.choices(
        activity_type=[
            app_commands.Choice(name="プレイ中", value="playing"),
            app_commands.Choice(name="再生中", value="listening"),
            app_commands.Choice(name="視聴中", value="watching"),
            app_commands.Choice(name="参戦中", value="competing"),
        ]
    )
    async def activity(
        self,
        interaction: discord.Interaction,
        activity_type: app_commands.Choice[str],
        text: str,
    ) -> None:
        """Bot のアクティビティを変更する。

        DB に保存し、即座に反映する。
        """
        try:
            await interaction.response.defer(ephemeral=True)
        except (discord.HTTPException, discord.InteractionResponded):
            return

        text = text.strip()
        if not text:
            await interaction.followup.send(
                "テキストを入力してください。", ephemeral=True
            )
            return

        if len(text) > 128:
            await interaction.followup.send(
                "テキストは128文字以内にしてください。", ephemeral=True
            )
            return

        async with async_session() as session:
            await upsert_bot_activity(session, activity_type.value, text)

        new_activity = make_activity(activity_type.value, text)
        await self.bot.change_presence(activity=new_activity)

        type_labels = {
            "playing": "プレイ中",
            "listening": "再生中",
            "watching": "視聴中",
            "competing": "参戦中",
        }
        label = type_labels.get(activity_type.value, activity_type.value)
        await interaction.followup.send(
            f"アクティビティを変更しました: **{label}** {text}",
            ephemeral=True,
        )
        logger.info(
            "Bot activity changed: type=%s, text=%s",
            activity_type.value,
            text,
        )


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する関数。bot.load_extension() から呼ばれる。"""
    await bot.add_cog(AdminCog(bot))
