"""TicketCategory, TicketPanel, TicketPanelCategory, Ticket の DB 操作。"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    Ticket,
    TicketCategory,
    TicketPanel,
    TicketPanelCategory,
)

__all__ = [
    "add_ticket_panel_category",
    "create_ticket",
    "create_ticket_category",
    "create_ticket_panel",
    "delete_ticket_category",
    "delete_ticket_panel",
    "delete_ticket_panel_by_message_id",
    "get_all_ticket_panels",
    "get_all_tickets",
    "get_enabled_ticket_categories_by_guild",
    "get_next_ticket_number",
    "get_ticket",
    "get_ticket_by_channel_id",
    "get_ticket_categories_by_guild",
    "get_ticket_category",
    "get_ticket_panel",
    "get_ticket_panel_by_message_id",
    "get_ticket_panel_categories",
    "get_ticket_panels_by_guild",
    "get_tickets_by_guild",
    "remove_ticket_panel_category",
    "update_ticket_panel",
    "update_ticket_status",
]

# Sentinel for update_ticket_status channel_id parameter
_UNSET: object = object()


# =============================================================================
# TicketCategory (チケットカテゴリ) 操作
# =============================================================================


async def create_ticket_category(
    session: AsyncSession,
    guild_id: str,
    name: str,
    staff_role_id: str,
    discord_category_id: str | None = None,
    channel_prefix: str = "ticket-",
    form_questions: str | None = None,
    log_channel_id: str | None = None,
) -> TicketCategory:
    """チケットカテゴリを作成する。"""
    category = TicketCategory(
        guild_id=guild_id,
        name=name,
        staff_role_id=staff_role_id,
        discord_category_id=discord_category_id,
        channel_prefix=channel_prefix,
        form_questions=form_questions,
        log_channel_id=log_channel_id,
    )
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def get_ticket_category(
    session: AsyncSession, category_id: int
) -> TicketCategory | None:
    """カテゴリ ID からチケットカテゴリを取得する。"""
    result = await session.execute(
        select(TicketCategory).where(TicketCategory.id == category_id)
    )
    return result.scalar_one_or_none()


async def get_ticket_categories_by_guild(
    session: AsyncSession, guild_id: str
) -> list[TicketCategory]:
    """サーバーの全チケットカテゴリを取得する。"""
    result = await session.execute(
        select(TicketCategory).where(TicketCategory.guild_id == guild_id)
    )
    return list(result.scalars().all())


async def get_enabled_ticket_categories_by_guild(
    session: AsyncSession, guild_id: str
) -> list[TicketCategory]:
    """サーバーの有効なチケットカテゴリを取得する。"""
    result = await session.execute(
        select(TicketCategory).where(
            TicketCategory.guild_id == guild_id,
            TicketCategory.is_enabled.is_(True),
        )
    )
    return list(result.scalars().all())


async def delete_ticket_category(session: AsyncSession, category_id: int) -> bool:
    """チケットカテゴリを削除する。関連レコードも CASCADE で削除。"""
    category = await get_ticket_category(session, category_id)
    if category:
        await session.delete(category)
        await session.commit()
        return True
    return False


# =============================================================================
# TicketPanel (チケットパネル) 操作
# =============================================================================


async def create_ticket_panel(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
    title: str,
    description: str | None = None,
) -> TicketPanel:
    """チケットパネルを作成する。"""
    panel = TicketPanel(
        guild_id=guild_id,
        channel_id=channel_id,
        title=title,
        description=description,
    )
    session.add(panel)
    await session.commit()
    await session.refresh(panel)
    return panel


async def get_ticket_panel(session: AsyncSession, panel_id: int) -> TicketPanel | None:
    """パネル ID からチケットパネルを取得する。"""
    result = await session.execute(
        select(TicketPanel).where(TicketPanel.id == panel_id)
    )
    return result.scalar_one_or_none()


async def get_ticket_panel_by_message_id(
    session: AsyncSession, message_id: str
) -> TicketPanel | None:
    """メッセージ ID からチケットパネルを取得する。"""
    result = await session.execute(
        select(TicketPanel).where(TicketPanel.message_id == message_id)
    )
    return result.scalar_one_or_none()


async def get_all_ticket_panels(session: AsyncSession) -> list[TicketPanel]:
    """全チケットパネルを取得する。"""
    result = await session.execute(select(TicketPanel))
    return list(result.scalars().all())


async def get_ticket_panels_by_guild(
    session: AsyncSession, guild_id: str
) -> list[TicketPanel]:
    """サーバーの全チケットパネルを取得する。"""
    result = await session.execute(
        select(TicketPanel).where(TicketPanel.guild_id == guild_id)
    )
    return list(result.scalars().all())


async def update_ticket_panel(
    session: AsyncSession,
    panel: TicketPanel,
    *,
    message_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> TicketPanel:
    """チケットパネルを更新する。None のフィールドは変更しない。"""
    if message_id is not None:
        panel.message_id = message_id
    if title is not None:
        panel.title = title
    if description is not None:
        panel.description = description
    await session.commit()
    return panel


async def delete_ticket_panel(session: AsyncSession, panel_id: int) -> bool:
    """チケットパネルを削除する。関連レコードも CASCADE で削除。"""
    panel = await get_ticket_panel(session, panel_id)
    if panel:
        await session.delete(panel)
        await session.commit()
        return True
    return False


async def delete_ticket_panel_by_message_id(
    session: AsyncSession, message_id: str
) -> bool:
    """メッセージ ID からチケットパネルを削除する。"""
    panel = await get_ticket_panel_by_message_id(session, message_id)
    if panel:
        await session.delete(panel)
        await session.commit()
        return True
    return False


# =============================================================================
# TicketPanelCategory (パネル-カテゴリ結合) 操作
# =============================================================================


async def add_ticket_panel_category(
    session: AsyncSession,
    panel_id: int,
    category_id: int,
    button_label: str | None = None,
    button_style: str = "primary",
    button_emoji: str | None = None,
) -> TicketPanelCategory:
    """パネルにカテゴリを関連付ける。"""
    # 現在の最大 position を取得
    result = await session.execute(
        select(func.coalesce(func.max(TicketPanelCategory.position), -1)).where(
            TicketPanelCategory.panel_id == panel_id
        )
    )
    next_position = result.scalar_one() + 1

    assoc = TicketPanelCategory(
        panel_id=panel_id,
        category_id=category_id,
        button_label=button_label,
        button_style=button_style,
        button_emoji=button_emoji,
        position=next_position,
    )
    session.add(assoc)
    await session.commit()
    await session.refresh(assoc)
    return assoc


async def get_ticket_panel_categories(
    session: AsyncSession, panel_id: int
) -> list[TicketPanelCategory]:
    """パネルに関連付けられたカテゴリを position 順で取得する。"""
    result = await session.execute(
        select(TicketPanelCategory)
        .where(TicketPanelCategory.panel_id == panel_id)
        .order_by(TicketPanelCategory.position)
    )
    return list(result.scalars().all())


async def remove_ticket_panel_category(
    session: AsyncSession, panel_id: int, category_id: int
) -> bool:
    """パネルからカテゴリの関連付けを削除する。"""
    result = await session.execute(
        select(TicketPanelCategory).where(
            TicketPanelCategory.panel_id == panel_id,
            TicketPanelCategory.category_id == category_id,
        )
    )
    assoc = result.scalar_one_or_none()
    if assoc:
        await session.delete(assoc)
        await session.commit()
        return True
    return False


# =============================================================================
# Ticket (チケット) 操作
# =============================================================================


async def create_ticket(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    username: str,
    category_id: int,
    channel_id: str,
    ticket_number: int,
    form_answers: str | None = None,
) -> Ticket:
    """チケットを作成する。"""
    ticket = Ticket(
        guild_id=guild_id,
        user_id=user_id,
        username=username,
        category_id=category_id,
        channel_id=channel_id,
        ticket_number=ticket_number,
        form_answers=form_answers,
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def get_ticket(session: AsyncSession, ticket_id: int) -> Ticket | None:
    """チケット ID からチケットを取得する。"""
    result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
    return result.scalar_one_or_none()


async def get_ticket_by_channel_id(
    session: AsyncSession, channel_id: str
) -> Ticket | None:
    """チャンネル ID からチケットを取得する。"""
    result = await session.execute(
        select(Ticket).where(Ticket.channel_id == channel_id)
    )
    return result.scalar_one_or_none()


async def get_tickets_by_guild(
    session: AsyncSession,
    guild_id: str,
    status: str | None = None,
    limit: int = 100,
) -> list[Ticket]:
    """サーバーのチケットを取得する (新しい順)。"""
    query = select(Ticket).where(Ticket.guild_id == guild_id)
    if status is not None:
        query = query.where(Ticket.status == status)
    query = query.order_by(Ticket.created_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_all_tickets(
    session: AsyncSession,
    status: str | None = None,
    limit: int = 100,
) -> list[Ticket]:
    """全チケットを取得する (新しい順)。"""
    query = select(Ticket)
    if status is not None:
        query = query.where(Ticket.status == status)
    query = query.order_by(Ticket.created_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_next_ticket_number(session: AsyncSession, guild_id: str) -> int:
    """ギルドの次のチケット番号を取得する。"""
    result = await session.execute(
        select(func.max(Ticket.ticket_number)).where(Ticket.guild_id == guild_id)
    )
    max_number = result.scalar_one_or_none()
    return (max_number or 0) + 1


async def update_ticket_status(
    session: AsyncSession,
    ticket: Ticket,
    *,
    status: str | None = None,
    claimed_by: str | None = None,
    closed_by: str | None = None,
    close_reason: str | None = None,
    transcript: str | None = None,
    closed_at: datetime | None = None,
    channel_id: str | None | object = _UNSET,
) -> Ticket:
    """チケットのステータスを更新する。None のフィールドは変更しない。

    channel_id はデフォルト値 _UNSET (sentinel) を使い、
    明示的に None を渡した場合のみ None に設定する。
    """
    if status is not None:
        ticket.status = status
    if claimed_by is not None:
        ticket.claimed_by = claimed_by
    if closed_by is not None:
        ticket.closed_by = closed_by
    if close_reason is not None:
        ticket.close_reason = close_reason
    if transcript is not None:
        ticket.transcript = transcript
    if closed_at is not None:
        ticket.closed_at = closed_at
    if channel_id is not _UNSET:
        ticket.channel_id = channel_id  # type: ignore[assignment]
    await session.commit()
    return ticket
