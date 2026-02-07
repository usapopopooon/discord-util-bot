"""Ticket system UI components.

チケットシステム用の UI コンポーネント。
パネルのボタン、チケット操作ボタンを提供する。

UI の構成:
  - TicketPanelView: パネルのカテゴリボタン群 (永続 View)
  - TicketCategoryButton: カテゴリ選択ボタン
  - TicketControlView: チケットチャンネル内の操作ボタン (永続 View)
"""

import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

import discord
from sqlalchemy.exc import IntegrityError

from src.config import settings
from src.database.engine import async_session
from src.database.models import Ticket, TicketCategory, TicketPanel, TicketPanelCategory
from src.services.db_service import (
    create_ticket,
    get_next_ticket_number,
    get_ticket,
    get_ticket_category,
    update_ticket_status,
)
from src.utils import format_datetime

logger = logging.getLogger(__name__)


# =============================================================================
# ヘルパー関数
# =============================================================================


def create_ticket_opening_embed(
    ticket: Ticket,
    category: TicketCategory,
) -> discord.Embed:
    """チケット開始時の Embed を作成する。

    Args:
        ticket: チケットオブジェクト
        category: チケットカテゴリ

    Returns:
        チケット開始 Embed
    """
    embed = discord.Embed(
        title=f"Ticket #{ticket.ticket_number} - {category.name}",
        description=f"<@{ticket.user_id}> がチケットを作成しました。",
        color=discord.Color.blue(),
        timestamp=ticket.created_at,
    )

    embed.set_footer(text=f"Ticket ID: {ticket.id}")
    return embed


def create_ticket_panel_embed(
    panel: TicketPanel,
    associations: list[TicketPanelCategory],  # noqa: ARG001
) -> discord.Embed:
    """チケットパネルの Embed を作成する。

    Args:
        panel: チケットパネル
        associations: パネルに関連付けられたカテゴリ

    Returns:
        パネル Embed
    """
    embed = discord.Embed(
        title=panel.title,
        description=panel.description
        or "下のボタンをクリックしてチケットを作成してください。",
        color=discord.Color.blue(),
    )
    return embed


async def generate_transcript(
    channel: discord.TextChannel,
    ticket: Ticket,
    category_name: str,
    closed_by_name: str,
) -> str:
    """チケットチャンネルのトランスクリプトを生成する。

    Args:
        channel: チケットチャンネル
        ticket: チケットオブジェクト
        category_name: カテゴリ名
        closed_by_name: クローズしたユーザー名

    Returns:
        トランスクリプト文字列
    """
    lines: list[str] = []
    lines.append(f"=== Ticket #{ticket.ticket_number} - {category_name} ===")
    lines.append(f"Created by: {ticket.username} ({ticket.user_id})")
    lines.append(
        f"Created at: {format_datetime(ticket.created_at, '%Y-%m-%d %H:%M:%S')}"
    )
    lines.append("")

    try:
        messages = [msg async for msg in channel.history(limit=500)]
        messages.reverse()  # oldest first

        for message in messages:
            if message.author.bot and message.embeds:
                # Bot の Embed メッセージはスキップ (開始 Embed など)
                continue
            timestamp = format_datetime(message.created_at, "%Y-%m-%d %H:%M:%S")
            content = message.content or ""
            if message.attachments:
                attachment_urls = ", ".join(a.url for a in message.attachments)
                if content:
                    content += f" [Attachments: {attachment_urls}]"
                else:
                    content = f"[Attachments: {attachment_urls}]"
            if message.stickers:
                sticker_names = ", ".join(s.name for s in message.stickers)
                if content:
                    content += f" [Stickers: {sticker_names}]"
                else:
                    content = f"[Stickers: {sticker_names}]"
            if content:
                lines.append(f"[{timestamp}] {message.author.name}: {content}")
    except discord.HTTPException as e:
        logger.warning("Failed to fetch messages for transcript: %s", e)
        lines.append("[Failed to fetch message history]")

    now = format_datetime(datetime.now(UTC), "%Y-%m-%d %H:%M:%S")
    lines.append("")
    lines.append(f"=== Closed by: {closed_by_name} at {now} ===")

    return "\n".join(lines)


async def send_close_log(
    guild: discord.Guild,
    ticket: Ticket,
    category: TicketCategory | None,
    closed_by_name: str,
    app_url: str,
) -> None:
    """クローズログをログチャンネルに送信する。

    Args:
        guild: Discord ギルド
        ticket: クローズされたチケット
        category: チケットカテゴリ (None の場合はスキップ)
        closed_by_name: クローズしたユーザー名
        app_url: Web 管理画面のベース URL
    """
    if category is None or not category.log_channel_id:
        return

    try:
        channel = guild.get_channel(int(category.log_channel_id))
    except (ValueError, TypeError):
        logger.warning("Invalid log_channel_id: %r", category.log_channel_id)
        return
    if not isinstance(channel, discord.TextChannel):
        return

    category_name = category.name
    web_url = f"{app_url.rstrip('/')}/tickets/{ticket.id}"

    embed = discord.Embed(
        title=f"Ticket #{ticket.ticket_number} Closed",
        color=discord.Color.red(),
        timestamp=datetime.now(UTC),
    )
    embed.add_field(name="Category", value=category_name, inline=True)
    embed.add_field(name="Created by", value=ticket.username, inline=True)
    embed.add_field(name="Closed by", value=closed_by_name, inline=True)
    if ticket.close_reason:
        embed.add_field(name="Reason", value=ticket.close_reason, inline=False)
    embed.add_field(name="Transcript", value=f"[View on Web]({web_url})", inline=False)

    try:
        await channel.send(embed=embed)
    except discord.HTTPException as e:
        logger.warning("Failed to send close log to channel %s: %s", channel.id, e)


# =============================================================================
# TicketPanelView (パネルボタン)
# =============================================================================


class TicketCategoryButton(discord.ui.Button[Any]):
    """チケットカテゴリ選択ボタン。

    custom_id 形式: ticket_panel:{panel_id}:{category_id}
    """

    def __init__(
        self,
        panel_id: int,
        association: TicketPanelCategory,
        category_name: str,
    ) -> None:
        style_map = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger,
        }
        style = style_map.get(association.button_style, discord.ButtonStyle.primary)

        label = association.button_label or category_name

        super().__init__(
            label=label,
            emoji=association.button_emoji or None,
            style=style,
            custom_id=f"ticket_panel:{panel_id}:{association.category_id}",
        )
        self.panel_id = panel_id
        self.category_id = association.category_id

    async def callback(self, interaction: discord.Interaction) -> None:
        """ボタンクリック時の処理。フォーム表示またはチケット直接作成。"""
        if interaction.guild is None:
            await interaction.response.send_message(
                "サーバー内でのみ使用できます。", ephemeral=True
            )
            return

        try:
            await self._handle_interaction(interaction)
        except Exception:
            logger.exception(
                "Error in TicketCategoryButton callback (panel=%d, category=%d)",
                self.panel_id,
                self.category_id,
            )
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "エラーが発生しました。しばらくしてからもう一度お試しください。",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        "エラーが発生しました。しばらくしてからもう一度お試しください。",
                        ephemeral=True,
                    )
            except discord.HTTPException:
                pass

    async def _handle_interaction(self, interaction: discord.Interaction) -> None:
        """ボタンクリックの実処理。"""
        assert interaction.guild is not None  # noqa: S101

        async with async_session() as db_session:
            category = await get_ticket_category(db_session, self.category_id)
            if category is None or not category.is_enabled:
                await interaction.response.send_message(
                    "このカテゴリは現在利用できません。", ephemeral=True
                )
                return

            # 同ユーザーの open チケットを確認
            from sqlalchemy import select

            from src.database.models import Ticket as TicketModel

            result = await db_session.execute(
                select(TicketModel).where(
                    TicketModel.guild_id == str(interaction.guild.id),
                    TicketModel.user_id == str(interaction.user.id),
                    TicketModel.status.in_(["open", "claimed"]),
                )
            )
            existing = result.scalars().first()
            if existing:
                await interaction.response.send_message(
                    f"既にオープン中のチケットがあります: <#{existing.channel_id}>",
                    ephemeral=True,
                )
                return

            # チケット作成
            await interaction.response.defer(ephemeral=True)
            # パネルのチャンネルのカテゴリをフォールバックとして使用
            panel_category: discord.CategoryChannel | None = None
            if isinstance(interaction.channel, discord.TextChannel):
                panel_category = interaction.channel.category
            channel = await _create_ticket_channel(
                interaction.guild,
                interaction.user,
                category,
                db_session,
                fallback_category=panel_category,
            )
            if channel:
                await interaction.followup.send(
                    f"チケットを作成しました: {channel.mention}",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "チケットの作成に失敗しました。Bot の権限を確認してください。",
                    ephemeral=True,
                )


class TicketPanelView(discord.ui.View):
    """チケットパネルのボタン View (永続)。

    timeout=None で Bot 再起動後もボタンが動作する。
    """

    def __init__(
        self,
        panel_id: int,
        associations: list[TicketPanelCategory],
        category_names: dict[int, str] | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self.panel_id = panel_id

        if category_names is None:
            category_names = {}

        for assoc in associations[:25]:
            name = category_names.get(assoc.category_id, "Ticket")
            self.add_item(TicketCategoryButton(panel_id, assoc, name))


# =============================================================================
# TicketFormModal
# =============================================================================


# =============================================================================
# TicketControlView (チケット内操作ボタン)
# =============================================================================


class TicketControlView(discord.ui.View):
    """チケットチャンネル内の操作ボタン View (永続)。

    Close と Claim ボタンを提供する。
    """

    def __init__(self, ticket_id: int) -> None:
        super().__init__(timeout=None)
        self.ticket_id = ticket_id

        self.add_item(
            TicketCloseButton(ticket_id),
        )
        self.add_item(
            TicketClaimButton(ticket_id),
        )


class TicketCloseButton(discord.ui.Button[Any]):
    """チケットクローズボタン。

    custom_id 形式: ticket_ctrl:{ticket_id}:close
    """

    def __init__(self, ticket_id: int) -> None:
        super().__init__(
            label="Close",
            emoji="\U0001f512",
            style=discord.ButtonStyle.danger,
            custom_id=f"ticket_ctrl:{ticket_id}:close",
        )
        self.ticket_id = ticket_id

    async def callback(self, interaction: discord.Interaction) -> None:
        """クローズボタンの処理。"""
        if interaction.guild is None or interaction.channel is None:
            return

        await interaction.response.defer()

        try:
            async with async_session() as db_session:
                ticket = await get_ticket(db_session, self.ticket_id)
                if ticket is None or ticket.status == "closed":
                    await interaction.followup.send(
                        "このチケットは既にクローズされています。", ephemeral=True
                    )
                    return

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

                # チケットステータス更新
                await update_ticket_status(
                    db_session,
                    ticket,
                    status="closed",
                    closed_by=interaction.user.name,
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
        except Exception:
            logger.exception(
                "Error in TicketCloseButton callback (ticket_id=%d)",
                self.ticket_id,
            )
            with contextlib.suppress(discord.HTTPException):
                await interaction.followup.send(
                    "エラーが発生しました。しばらくしてからもう一度お試しください。",
                    ephemeral=True,
                )


class TicketClaimButton(discord.ui.Button[Any]):
    """チケット担当ボタン。

    custom_id 形式: ticket_ctrl:{ticket_id}:claim
    """

    def __init__(self, ticket_id: int) -> None:
        super().__init__(
            label="Claim",
            emoji="\u2705",
            style=discord.ButtonStyle.success,
            custom_id=f"ticket_ctrl:{ticket_id}:claim",
        )
        self.ticket_id = ticket_id

    async def callback(self, interaction: discord.Interaction) -> None:
        """担当ボタンの処理。"""
        if interaction.guild is None:
            return

        try:
            async with async_session() as db_session:
                ticket = await get_ticket(db_session, self.ticket_id)
                if ticket is None:
                    await interaction.response.send_message(
                        "チケットが見つかりません。", ephemeral=True
                    )
                    return

                if ticket.status == "closed":
                    await interaction.response.send_message(
                        "このチケットは既にクローズされています。", ephemeral=True
                    )
                    return

                if ticket.claimed_by:
                    await interaction.response.send_message(
                        f"このチケットは既に {ticket.claimed_by} が担当しています。",
                        ephemeral=True,
                    )
                    return

                await update_ticket_status(
                    db_session,
                    ticket,
                    status="claimed",
                    claimed_by=interaction.user.name,
                )

            await interaction.response.send_message(
                f"{interaction.user.mention} がこのチケットを担当します。",
            )
        except Exception:
            logger.exception(
                "Error in TicketClaimButton callback (ticket_id=%d)",
                self.ticket_id,
            )
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "エラーが発生しました。しばらくしてからもう一度お試しください。",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        "エラーが発生しました。しばらくしてからもう一度お試しください。",
                        ephemeral=True,
                    )
            except discord.HTTPException:
                pass


# =============================================================================
# チケットチャンネル作成ヘルパー
# =============================================================================


_TICKET_NUMBER_MAX_RETRIES = 3


async def _create_ticket_channel(
    guild: discord.Guild,
    user: discord.User | discord.Member,
    category: TicketCategory,
    db_session: Any,
    *,
    fallback_category: discord.CategoryChannel | None = None,
) -> discord.TextChannel | None:
    """チケットチャンネルを作成する。

    Args:
        guild: Discord ギルド
        user: チケット作成ユーザー
        category: チケットカテゴリ
        db_session: DB セッション
        fallback_category: discord_category_id 未設定時のフォールバックカテゴリ

    Returns:
        作成されたチャンネル、または失敗時に None
    """
    # パーミッションオーバーライト
    try:
        staff_role = guild.get_role(int(category.staff_role_id))
    except (ValueError, TypeError):
        logger.error(
            "Invalid staff_role_id: %r for category %d",
            category.staff_role_id,
            category.id,
        )
        return None

    overwrites: dict[discord.Member | discord.Role, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            manage_messages=True,
            attach_files=True,
            read_message_history=True,
        ),
    }

    if isinstance(user, discord.Member):
        overwrites[user] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            read_message_history=True,
        )

    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            read_message_history=True,
            manage_messages=True,
        )

    # Discord カテゴリ (明示設定 > パネルのカテゴリ > なし)
    discord_category: discord.CategoryChannel | None = None
    if category.discord_category_id:
        try:
            ch = guild.get_channel(int(category.discord_category_id))
        except (ValueError, TypeError):
            logger.warning(
                "Invalid discord_category_id: %r", category.discord_category_id
            )
            ch = None
        if isinstance(ch, discord.CategoryChannel):
            discord_category = ch
    if discord_category is None:
        discord_category = fallback_category

    # チャンネル作成 + DB 保存 (ticket_number 競合時はリトライ)
    channel: discord.TextChannel | None = None
    ticket: Ticket | None = None

    for attempt in range(_TICKET_NUMBER_MAX_RETRIES):
        ticket_number = await get_next_ticket_number(db_session, str(guild.id))

        try:
            channel = await guild.create_text_channel(
                name=f"{category.channel_prefix}{ticket_number}",
                category=discord_category,
                overwrites=overwrites,  # type: ignore[arg-type]
                reason=f"Ticket #{ticket_number} by {user.name}",
            )
        except discord.HTTPException as e:
            logger.error("Failed to create ticket channel: %s", e)
            return None

        try:
            ticket = await create_ticket(
                db_session,
                guild_id=str(guild.id),
                user_id=str(user.id),
                username=user.name,
                category_id=category.id,
                channel_id=str(channel.id),
                ticket_number=ticket_number,
            )
            break
        except IntegrityError:
            logger.warning(
                "Ticket number %d collision (attempt %d/%d), retrying...",
                ticket_number,
                attempt + 1,
                _TICKET_NUMBER_MAX_RETRIES,
            )
            await db_session.rollback()
            # 孤立チャンネルを削除
            with contextlib.suppress(discord.HTTPException):
                await channel.delete(reason="Ticket creation failed (number collision)")
            channel = None

    if channel is None or ticket is None:
        logger.error(
            "Failed to create ticket after %d attempts", _TICKET_NUMBER_MAX_RETRIES
        )
        return None

    # 開始 Embed + スタッフメンション (スポイラーで非表示) を送信
    embed = create_ticket_opening_embed(ticket, category)
    view = TicketControlView(ticket.id)
    staff_mention = f"||<@&{category.staff_role_id}>||"
    try:
        await channel.send(content=staff_mention, embed=embed, view=view)
    except discord.HTTPException as e:
        logger.error("Failed to send opening message to ticket channel: %s", e)

    return channel
