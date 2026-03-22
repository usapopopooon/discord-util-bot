"""Ticket routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import src.web.app as _app
from src.database.models import (
    DiscordGuild,
    Ticket,
    TicketCategory,
    TicketPanel,
    TicketPanelCategory,
)
from src.utils import get_resource_lock
from src.web.templates import (
    ticket_detail_page,
    ticket_list_page,
    ticket_panel_create_page,
    ticket_panel_detail_page,
    ticket_panels_list_page,
)

router = APIRouter()


@router.get("/tickets", response_model=None)
async def tickets_list(
    status: str = "",
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """チケット一覧ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    query = select(Ticket).order_by(Ticket.created_at.desc()).limit(100)
    if status:
        query = query.where(Ticket.status == status)
    result = await db.execute(query)
    tickets = list(result.scalars().all())
    guilds_map, _ = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=ticket_list_page(
            tickets,
            csrf_token=_app.generate_csrf_token(),
            guilds_map=guilds_map,
            status_filter=status,
        )
    )


@router.get("/tickets/panels", response_model=None)
async def ticket_panels_list(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """チケットパネル一覧ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(TicketPanel).order_by(TicketPanel.created_at.desc())
    )
    panels = list(result.scalars().all())
    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=ticket_panels_list_page(
            panels,
            csrf_token=_app.generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
        )
    )


@router.get("/tickets/panels/new", response_model=None)
async def ticket_panel_create_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """チケットパネル作成フォーム。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)
    discord_roles = await _app._get_discord_roles_by_guild(db)
    discord_categories = await _app._get_discord_categories(db)

    roles_map: dict[str, list[tuple[str, str]]] = {}
    for gid, role_list in discord_roles.items():
        roles_map[gid] = [(rid, name) for rid, name, _ in role_list]

    return HTMLResponse(
        content=ticket_panel_create_page(
            guilds_map=guilds_map,
            channels_map=channels_map,
            roles_map=roles_map,
            discord_categories_map=discord_categories,
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/tickets/panels/new", response_model=None)
async def ticket_panel_create_post(
    request: Request,
    guild_id: Annotated[str, Form()] = "",
    channel_id: Annotated[str, Form()] = "",
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    staff_role_id: Annotated[str, Form()] = "",
    discord_category_id: Annotated[str, Form()] = "",
    channel_prefix: Annotated[str, Form()] = "ticket-",
    log_channel_id: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """チケットパネルを作成し、Discord に投稿する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/tickets/panels/new", status_code=302)

    user_email = user.get("email", "")
    path = str(request.url.path)
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/tickets/panels/new", status_code=302)
    _app.record_form_submit(user_email, path)

    if not guild_id or not channel_id or not title.strip() or not staff_role_id:
        return RedirectResponse(url="/tickets/panels/new", status_code=302)

    # カテゴリを自動作成
    category = TicketCategory(
        guild_id=guild_id,
        name=title.strip(),
        staff_role_id=staff_role_id,
        discord_category_id=discord_category_id.strip() or None,
        channel_prefix=channel_prefix.strip() or "ticket-",
        log_channel_id=log_channel_id.strip() or None,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)

    # パネルを作成
    panel = TicketPanel(
        guild_id=guild_id,
        channel_id=channel_id,
        title=title.strip(),
        description=description.strip() or None,
    )
    db.add(panel)
    await db.commit()
    await db.refresh(panel)

    # カテゴリを関連付け
    assoc = TicketPanelCategory(
        panel_id=panel.id,
        category_id=category.id,
        position=0,
    )
    db.add(assoc)
    await db.commit()
    await db.refresh(assoc)

    # Discord に投稿
    category_names: dict[int, str] = {category.id: category.name}
    success, message_id, error_msg = await _app.post_ticket_panel_to_discord(
        panel, [assoc], category_names
    )
    if success and message_id:
        panel.message_id = message_id
        await db.commit()

    return RedirectResponse(url="/tickets/panels", status_code=302)


@router.post("/tickets/panels/{panel_id}/delete", response_model=None)
async def ticket_panel_delete(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """チケットパネルを削除する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/tickets/panels", status_code=302)

    user_email = user.get("email", "")
    path = str(request.url.path)
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/tickets/panels", status_code=302)
    _app.record_form_submit(user_email, path)

    result = await db.execute(select(TicketPanel).where(TicketPanel.id == panel_id))
    panel = result.scalar_one_or_none()
    if panel:
        # Discord メッセージも削除
        if panel.message_id:
            await _app.delete_discord_message(panel.channel_id, panel.message_id)
        await db.delete(panel)
        await db.commit()

    return RedirectResponse(url="/tickets/panels", status_code=302)


@router.get("/tickets/panels/{panel_id}", response_model=None)
async def ticket_panel_detail(
    panel_id: int,
    success: str | None = None,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """チケットパネル詳細・編集ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(TicketPanel)
        .options(
            selectinload(TicketPanel.category_associations).selectinload(
                TicketPanelCategory.category
            )
        )
        .where(TicketPanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/tickets/panels", status_code=302)

    sorted_cat_assoc = sorted(panel.category_associations, key=lambda a: a.position)
    associations = [
        (a, a.category.name if a.category else "Unknown") for a in sorted_cat_assoc
    ]

    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)
    guild_name = guilds_map.get(panel.guild_id)
    guild_channels = channels_map.get(panel.guild_id, [])
    channel_name = next(
        (name for cid, name in guild_channels if cid == panel.channel_id), None
    )

    return HTMLResponse(
        content=ticket_panel_detail_page(
            panel,
            associations,
            success=success,
            guild_name=guild_name,
            channel_name=channel_name,
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/tickets/panels/{panel_id}/edit", response_model=None)
async def ticket_panel_edit(
    request: Request,
    panel_id: int,
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """チケットパネルのタイトル・説明を編集する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(
            url=f"/tickets/panels/{panel_id}?success=Invalid+security+token",
            status_code=302,
        )

    user_email = user.get("email", "")
    path = str(request.url.path)
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(
            url=f"/tickets/panels/{panel_id}?success=Please+wait+before+editing+again",
            status_code=302,
        )

    title = title.strip()
    if not title:
        return RedirectResponse(
            url=f"/tickets/panels/{panel_id}?success=Title+is+required",
            status_code=302,
        )
    if len(title) > 100:
        return RedirectResponse(
            url=f"/tickets/panels/{panel_id}?success=Title+must+be+100+characters+or+less",
            status_code=302,
        )

    description = description.strip()
    if len(description) > 2000:
        return RedirectResponse(
            url=f"/tickets/panels/{panel_id}?success=Description+must+be+2000+characters+or+less",
            status_code=302,
        )

    result = await db.execute(select(TicketPanel).where(TicketPanel.id == panel_id))
    panel = result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/tickets/panels", status_code=302)

    panel.title = title
    panel.description = description if description else None
    await db.commit()
    _app.record_form_submit(user_email, path)

    return RedirectResponse(
        url=f"/tickets/panels/{panel_id}?success=Panel+updated",
        status_code=302,
    )


@router.post("/tickets/panels/{panel_id}/buttons/{assoc_id}/edit", response_model=None)
async def ticket_panel_button_edit(
    request: Request,
    panel_id: int,
    assoc_id: int,
    button_label: Annotated[str, Form()] = "",
    button_style: Annotated[str, Form()] = "primary",
    button_emoji: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """チケットパネルのボタン設定を編集する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(
            url=f"/tickets/panels/{panel_id}?success=Invalid+security+token",
            status_code=302,
        )

    user_email = user.get("email", "")
    path = str(request.url.path)
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(
            url=f"/tickets/panels/{panel_id}?success=Please+wait",
            status_code=302,
        )

    result = await db.execute(
        select(TicketPanelCategory).where(
            TicketPanelCategory.id == assoc_id,
            TicketPanelCategory.panel_id == panel_id,
        )
    )
    assoc = result.scalar_one_or_none()
    if not assoc:
        return RedirectResponse(
            url=f"/tickets/panels/{panel_id}?success=Button+not+found",
            status_code=302,
        )

    label = button_label.strip()
    if len(label) > 80:
        label = label[:80]
    assoc.button_label = label or None

    valid_styles = ("primary", "secondary", "success", "danger")
    assoc.button_style = button_style if button_style in valid_styles else "primary"

    emoji = button_emoji.strip()
    if len(emoji) > 64:
        emoji = emoji[:64]
    assoc.button_emoji = emoji or None

    await db.commit()
    _app.record_form_submit(user_email, path)

    return RedirectResponse(
        url=f"/tickets/panels/{panel_id}?success=Button+updated",
        status_code=302,
    )


@router.post("/tickets/panels/{panel_id}/post", response_model=None)
async def ticket_panel_post_to_discord(
    request: Request,
    panel_id: int,
    csrf_token: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """チケットパネルを Discord に投稿/更新する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(
            url=f"/tickets/panels/{panel_id}?success=Invalid+security+token",
            status_code=302,
        )

    user_email = user.get("email", "")
    path = str(request.url.path)
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(
            url=f"/tickets/panels/{panel_id}?success=Please+wait",
            status_code=302,
        )

    result = await db.execute(
        select(TicketPanel)
        .options(
            selectinload(TicketPanel.category_associations).selectinload(
                TicketPanelCategory.category
            )
        )
        .where(TicketPanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/tickets/panels", status_code=302)

    sorted_cat_assoc = sorted(panel.category_associations, key=lambda a: a.position)
    category_names = {
        a.category_id: (a.category.name if a.category else "Ticket")
        for a in sorted_cat_assoc
    }

    if panel.message_id:
        ok, error = await _app.edit_ticket_panel_in_discord(
            panel, sorted_cat_assoc, category_names
        )
        if not ok:
            return RedirectResponse(
                url=f"/tickets/panels/{panel_id}?success=Error:+{error or 'Unknown'}",
                status_code=302,
            )
        _app.record_form_submit(user_email, path)
        return RedirectResponse(
            url=f"/tickets/panels/{panel_id}?success=Updated+in+Discord",
            status_code=302,
        )
    else:
        ok, message_id, error = await _app.post_ticket_panel_to_discord(
            panel, sorted_cat_assoc, category_names
        )
        if not ok:
            return RedirectResponse(
                url=f"/tickets/panels/{panel_id}?success=Error:+{error or 'Unknown'}",
                status_code=302,
            )
        if message_id:
            panel.message_id = message_id
            await db.commit()
        _app.record_form_submit(user_email, path)
        return RedirectResponse(
            url=f"/tickets/panels/{panel_id}?success=Posted+to+Discord",
            status_code=302,
        )


@router.post("/tickets/{ticket_id}/delete", response_model=None)
async def ticket_delete(
    request: Request,
    ticket_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """チケットログを削除する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/tickets", status_code=302)

    user_email = user.get("email", "")
    path = str(request.url.path)
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/tickets", status_code=302)

    async with get_resource_lock(f"ticket:delete:{ticket_id}"):
        result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if ticket:
            await db.delete(ticket)
            await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/tickets", status_code=302)


@router.get("/tickets/{ticket_id}", response_model=None)
async def ticket_detail(
    ticket_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """チケット詳細ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        return RedirectResponse(url="/tickets", status_code=302)

    # カテゴリ名を取得
    cat_result = await db.execute(
        select(TicketCategory).where(TicketCategory.id == ticket.category_id)
    )
    category = cat_result.scalar_one_or_none()
    category_name = category.name if category else "Unknown"

    # ギルド名を取得
    guild_result = await db.execute(
        select(DiscordGuild).where(DiscordGuild.guild_id == ticket.guild_id)
    )
    guild = guild_result.scalar_one_or_none()
    guild_name = guild.guild_name if guild else ""

    return HTMLResponse(
        content=ticket_detail_page(
            ticket,
            category_name=category_name,
            guild_name=guild_name,
            csrf_token=_app.generate_csrf_token(),
        )
    )
