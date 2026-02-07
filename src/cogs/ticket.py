"""Ticket system cog for support ticket management.

チケットシステム機能を提供する Cog。
パネルボタンからチケット作成、スタッフ対応、クローズ/トランスクリプト保存。

機能:
  - パネルボタン → フォーム回答 → プライベートチャンネル作成
  - /ticket close: チケットクローズ + トランスクリプト保存
  - /ticket claim: スタッフがチケットを担当
  - /ticket add: ユーザーをチケットに追加
  - /ticket remove: ユーザーをチケットから削除
"""

import logging
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.config import settings
from src.database.engine import async_session
from src.services.db_service import (
    delete_ticket_panel_by_message_id,
    get_all_ticket_panels,
    get_all_tickets,
    get_ticket_by_channel_id,
    get_ticket_category,
    get_ticket_panel_categories,
    update_ticket_status,
)
from src.ui.ticket_view import (
    TicketControlView,
    TicketPanelView,
    generate_transcript,
    send_close_log,
)

logger = logging.getLogger(__name__)


class TicketCog(commands.Cog):
    """チケットシステム機能を提供する Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Cog 読み込み時に永続 View を登録し、定期同期タスクを開始する。"""
        try:
            await self._register_all_views()
        except Exception:
            logger.exception("Failed to register ticket views on cog_load")
        self._sync_views_task.start()

    async def cog_unload(self) -> None:
        """Cog アンロード時に定期同期タスクを停止する。"""
        self._sync_views_task.cancel()

    async def _register_all_views(self) -> None:
        """DB から全パネルと open/claimed チケットの永続 View を登録する。"""
        async with async_session() as db_session:
            # パネルの View を登録
            panels = await get_all_ticket_panels(db_session)
            panel_count = 0
            for panel in panels:
                try:
                    associations = await get_ticket_panel_categories(
                        db_session, panel.id
                    )
                    if associations:
                        # カテゴリ名を取得
                        category_names: dict[int, str] = {}
                        for assoc in associations:
                            cat = await get_ticket_category(
                                db_session, assoc.category_id
                            )
                            if cat:
                                category_names[cat.id] = cat.name
                        view = TicketPanelView(panel.id, associations, category_names)
                        self.bot.add_view(view)
                        panel_count += 1
                except Exception:
                    logger.exception("Failed to register view for panel %d", panel.id)

            # open/claimed チケットの ControlView を登録
            tickets = await get_all_tickets(db_session, limit=500)
            ticket_count = 0
            for ticket in tickets:
                if ticket.status in ("open", "claimed") and ticket.channel_id:
                    try:
                        ctrl_view = TicketControlView(ticket.id)
                        self.bot.add_view(ctrl_view)
                        ticket_count += 1
                    except Exception:
                        logger.exception(
                            "Failed to register control view for ticket %d", ticket.id
                        )

        logger.info(
            "Registered %d ticket panel views and %d ticket control views",
            panel_count,
            ticket_count,
        )

    @tasks.loop(seconds=60)
    async def _sync_views_task(self) -> None:
        """Web 管理画面で追加されたパネルの永続 View を定期的に同期する。"""
        try:
            await self._register_all_views()
        except Exception:
            logger.exception("Failed to sync ticket views")

    # -------------------------------------------------------------------------
    # スラッシュコマンド
    # -------------------------------------------------------------------------

    ticket_group = app_commands.Group(
        name="ticket",
        description="チケットシステムの管理コマンド",
        default_permissions=discord.Permissions(manage_channels=True),
    )

    @ticket_group.command(name="close", description="チケットをクローズする")
    @app_commands.describe(reason="クローズ理由")
    async def ticket_close(
        self,
        interaction: discord.Interaction,
        reason: str | None = None,
    ) -> None:
        """チケットチャンネル内でチケットをクローズする。"""
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "サーバー内でのみ使用できます。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            ticket = await get_ticket_by_channel_id(
                db_session, str(interaction.channel_id)
            )
            if ticket is None:
                await interaction.response.send_message(
                    "このチャンネルはチケットチャンネルではありません。",
                    ephemeral=True,
                )
                return

            if ticket.status == "closed":
                await interaction.response.send_message(
                    "このチケットは既にクローズされています。", ephemeral=True
                )
                return

            await interaction.response.defer()

            category = await get_ticket_category(db_session, ticket.category_id)
            category_name = category.name if category else "Unknown"

            # トランスクリプト生成
            transcript_text = ""
            if isinstance(interaction.channel, discord.TextChannel):
                transcript_text = await generate_transcript(
                    interaction.channel,
                    ticket,
                    category_name,
                    interaction.user.name,
                )

            # DB 更新
            await update_ticket_status(
                db_session,
                ticket,
                status="closed",
                closed_by=str(interaction.user.id),
                close_reason=reason,
                transcript=transcript_text,
                closed_at=datetime.now(UTC),
                channel_id=None,
            )

        # ログチャンネルに通知
        await send_close_log(
            interaction.guild,
            ticket,
            category,
            interaction.user.name,
            settings.app_url,
        )

        # チャンネル削除
        try:
            if isinstance(interaction.channel, discord.TextChannel):
                closer = interaction.user.name
                await interaction.channel.delete(
                    reason=f"Ticket #{ticket.ticket_number} closed by {closer}"
                )
        except discord.HTTPException as e:
            logger.error("Failed to delete ticket channel: %s", e)
            await interaction.followup.send(
                "チケットをクローズしましたが、チャンネルの削除に失敗しました。",
            )

    @ticket_group.command(name="claim", description="チケットを担当する")
    async def ticket_claim(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """チケットを担当する。"""
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "サーバー内でのみ使用できます。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            ticket = await get_ticket_by_channel_id(
                db_session, str(interaction.channel_id)
            )
            if ticket is None:
                await interaction.response.send_message(
                    "このチャンネルはチケットチャンネルではありません。",
                    ephemeral=True,
                )
                return

            if ticket.status == "closed":
                await interaction.response.send_message(
                    "このチケットは既にクローズされています。", ephemeral=True
                )
                return

            if ticket.claimed_by:
                await interaction.response.send_message(
                    f"このチケットは既に <@{ticket.claimed_by}> が担当しています。",
                    ephemeral=True,
                )
                return

            await update_ticket_status(
                db_session,
                ticket,
                status="claimed",
                claimed_by=str(interaction.user.id),
            )

        await interaction.response.send_message(
            f"{interaction.user.mention} がこのチケットを担当します。",
        )

    @ticket_group.command(
        name="add", description="ユーザーをチケットチャンネルに追加する"
    )
    @app_commands.describe(user="追加するユーザー")
    async def ticket_add(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        """ユーザーをチケットチャンネルに追加する。"""
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "サーバー内でのみ使用できます。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            ticket = await get_ticket_by_channel_id(
                db_session, str(interaction.channel_id)
            )
            if ticket is None:
                await interaction.response.send_message(
                    "このチャンネルはチケットチャンネルではありません。",
                    ephemeral=True,
                )
                return

        if isinstance(interaction.channel, discord.TextChannel):
            await interaction.channel.set_permissions(
                user,
                view_channel=True,
                send_messages=True,
                attach_files=True,
                read_message_history=True,
                reason=f"Added to ticket #{ticket.ticket_number}",
            )
            await interaction.response.send_message(
                f"{user.mention} をこのチケットに追加しました。",
            )
        else:
            await interaction.response.send_message(
                "このチャンネルではこの操作を実行できません。", ephemeral=True
            )

    @ticket_group.command(
        name="remove", description="ユーザーをチケットチャンネルから削除する"
    )
    @app_commands.describe(user="削除するユーザー")
    async def ticket_remove(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        """ユーザーをチケットチャンネルから削除する。"""
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "サーバー内でのみ使用できます。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            ticket = await get_ticket_by_channel_id(
                db_session, str(interaction.channel_id)
            )
            if ticket is None:
                await interaction.response.send_message(
                    "このチャンネルはチケットチャンネルではありません。",
                    ephemeral=True,
                )
                return

        if isinstance(interaction.channel, discord.TextChannel):
            await interaction.channel.set_permissions(
                user,
                overwrite=None,
                reason=f"Removed from ticket #{ticket.ticket_number}",
            )
            await interaction.response.send_message(
                f"{user.mention} をこのチケットから削除しました。",
            )
        else:
            await interaction.response.send_message(
                "このチャンネルではこの操作を実行できません。", ephemeral=True
            )

    # -------------------------------------------------------------------------
    # イベントリスナー
    # -------------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """チケットチャンネルが外部削除された場合の DB クリーンアップ。"""
        async with async_session() as db_session:
            ticket = await get_ticket_by_channel_id(db_session, str(channel.id))
            if ticket and ticket.status != "closed":
                await update_ticket_status(
                    db_session,
                    ticket,
                    status="closed",
                    closed_at=datetime.now(UTC),
                    channel_id=None,
                )
                logger.info(
                    "Cleaned up ticket %d after channel %s was deleted",
                    ticket.id,
                    channel.id,
                )

    @commands.Cog.listener()
    async def on_raw_message_delete(
        self, payload: discord.RawMessageDeleteEvent
    ) -> None:
        """パネルメッセージが削除された場合の DB クリーンアップ。"""
        async with async_session() as db_session:
            deleted = await delete_ticket_panel_by_message_id(
                db_session, str(payload.message_id)
            )
            if deleted:
                logger.info(
                    "Cleaned up ticket panel after message %d was deleted",
                    payload.message_id,
                )


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に追加する。"""
    await bot.add_cog(TicketCog(bot))
