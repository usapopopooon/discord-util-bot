"""API v1 ticket routes (JSON)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import src.web.db_helpers as _db
import src.web.security as _security
from src.database.models import (
    Ticket,
    TicketCategory,
    TicketPanel,
    TicketPanelCategory,
)
from src.utils import get_resource_lock
from src.web.discord_api import (
    delete_discord_message,
    edit_ticket_panel_in_discord,
    post_ticket_panel_to_discord,
)
from src.web.jwt_auth import get_current_user_jwt

router = APIRouter(prefix="/api/v1", tags=["api-tickets"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_ticket(ticket: Ticket) -> dict[str, Any]:
    return {
        "id": ticket.id,
        "guild_id": ticket.guild_id,
        "channel_id": ticket.channel_id,
        "ticket_number": ticket.ticket_number,
        "user_id": ticket.user_id,
        "username": ticket.username,
        "status": ticket.status,
        "claimed_by": ticket.claimed_by,
        "closed_by": ticket.closed_by,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
    }


def _serialize_panel(panel: TicketPanel) -> dict[str, Any]:
    return {
        "id": panel.id,
        "guild_id": panel.guild_id,
        "channel_id": panel.channel_id,
        "message_id": panel.message_id,
        "title": panel.title,
        "description": panel.description,
        "created_at": panel.created_at.isoformat() if panel.created_at else None,
    }


def _serialize_category(cat: TicketCategory) -> dict[str, Any]:
    return {
        "id": cat.id,
        "guild_id": cat.guild_id,
        "name": cat.name,
        "staff_role_id": cat.staff_role_id,
        "discord_category_id": cat.discord_category_id,
        "channel_prefix": cat.channel_prefix,
        "log_channel_id": cat.log_channel_id,
        "is_enabled": cat.is_enabled,
    }


def _channels_payload(
    channels_map: dict[str, list[tuple[str, str]]],
) -> dict[str, list[dict[str, str]]]:
    return {
        gid: [{"id": cid, "name": cname} for cid, cname in clist]
        for gid, clist in channels_map.items()
    }


def _roles_payload(
    roles_map: dict[str, list[tuple[str, str, int]]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        gid: [{"id": rid, "name": name, "color": color} for rid, name, color in rlist]
        for gid, rlist in roles_map.items()
    }


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


@router.get("/tickets", response_model=None)
async def api_tickets_list(
    status: str = "",
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List tickets with optional status filter."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    query = select(Ticket).order_by(Ticket.created_at.desc()).limit(100)
    if status:
        query = query.where(Ticket.status == status)
    result = await db.execute(query)
    tickets = list(result.scalars().all())

    guilds_map, _ = await _db._get_discord_guilds_and_channels(db)

    return JSONResponse(
        {
            "tickets": [_serialize_ticket(t) for t in tickets],
            "guilds": guilds_map,
        }
    )


@router.get("/tickets/{ticket_id}", response_model=None)
async def api_tickets_detail(
    ticket_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Get a single ticket with transcript."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        return JSONResponse({"error": "Not found"}, status_code=404)

    cat_result = await db.execute(
        select(TicketCategory).where(TicketCategory.id == ticket.category_id)
    )
    category = cat_result.scalar_one_or_none()

    return JSONResponse(
        {
            "ticket": {
                **_serialize_ticket(ticket),
                "transcript": ticket.transcript,
                "form_answers": ticket.form_answers,
                "category_id": ticket.category_id,
                "category_name": category.name if category else "Unknown",
            }
        }
    )


@router.delete("/tickets/{ticket_id}", response_model=None)
async def api_tickets_delete(
    request: Request,
    ticket_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete a ticket."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"ticket:delete:{ticket_id}"):
        result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if not ticket:
            return JSONResponse({"error": "Not found"}, status_code=404)

        await db.delete(ticket)
        await db.commit()
        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@router.get("/tickets/categories", response_model=None)
async def api_ticket_categories_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List all ticket categories."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(
        select(TicketCategory).order_by(TicketCategory.created_at.desc())
    )
    categories = list(result.scalars().all())

    return JSONResponse({"categories": [_serialize_category(c) for c in categories]})


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------


@router.get("/tickets/panels", response_model=None)
async def api_ticket_panels_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List all ticket panels."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(
        select(TicketPanel).order_by(TicketPanel.created_at.desc())
    )
    panels = list(result.scalars().all())

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)

    return JSONResponse(
        {
            "panels": [_serialize_panel(p) for p in panels],
            "guilds": guilds_map,
            "channels": _channels_payload(channels_map),
        }
    )


@router.get("/tickets/panels/form-data", response_model=None)
async def api_ticket_panels_form_data(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Return form data for panel creation."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)
    discord_roles = await _db._get_discord_roles_by_guild(db)
    discord_categories = await _db._get_discord_categories(db)

    cat_result = await db.execute(
        select(TicketCategory).order_by(TicketCategory.created_at.desc())
    )
    categories = list(cat_result.scalars().all())

    return JSONResponse(
        {
            "guilds": guilds_map,
            "channels": _channels_payload(channels_map),
            "roles": _roles_payload(discord_roles),
            "categories": [_serialize_category(c) for c in categories],
            "discord_categories": {
                gid: [{"id": cid, "name": cname} for cid, cname in clist]
                for gid, clist in discord_categories.items()
            },
        }
    )


@router.get("/tickets/panels/{panel_id}", response_model=None)
async def api_ticket_panels_detail(
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Get a single ticket panel with category associations."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

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
        return JSONResponse({"error": "Not found"}, status_code=404)

    sorted_assoc = sorted(panel.category_associations, key=lambda a: a.position)

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)

    return JSONResponse(
        {
            "panel": {
                **_serialize_panel(panel),
                "categories": [
                    {
                        "assoc_id": a.id,
                        "category_id": a.category_id,
                        "category_name": a.category.name if a.category else "Unknown",
                        "button_label": a.button_label,
                        "button_style": a.button_style,
                        "button_emoji": a.button_emoji,
                        "position": a.position,
                    }
                    for a in sorted_assoc
                ],
            },
            "guilds": guilds_map,
            "channels": _channels_payload(channels_map),
        }
    )


@router.post("/tickets/panels", response_model=None)
async def api_ticket_panels_create(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Create a ticket panel with an auto-created category."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    body: dict[str, Any] = await request.json()

    guild_id = str(body.get("guild_id", "")).strip()
    channel_id = str(body.get("channel_id", "")).strip()
    title = str(body.get("title", "")).strip()
    description = str(body.get("description", "")).strip()
    staff_role_id = str(body.get("staff_role_id", "")).strip()
    discord_category_id = str(body.get("discord_category_id", "")).strip()
    channel_prefix = str(body.get("channel_prefix", "ticket-")).strip()
    log_channel_id = str(body.get("log_channel_id", "")).strip()
    category_ids: list[int] = body.get("categories", [])

    if not guild_id or not guild_id.isdigit():
        return JSONResponse({"error": "Valid guild_id is required"}, status_code=400)
    if not channel_id or not channel_id.isdigit():
        return JSONResponse({"error": "Valid channel_id is required"}, status_code=400)
    if not title:
        return JSONResponse({"error": "Title is required"}, status_code=400)
    if not staff_role_id:
        return JSONResponse({"error": "staff_role_id is required"}, status_code=400)

    async with get_resource_lock(f"ticket_panel:create:{user_email}"):
        # Auto-create category (matching HTML route behavior)
        category = TicketCategory(
            guild_id=guild_id,
            name=title,
            staff_role_id=staff_role_id,
            discord_category_id=discord_category_id or None,
            channel_prefix=channel_prefix or "ticket-",
            log_channel_id=log_channel_id or None,
        )
        db.add(category)
        await db.commit()
        await db.refresh(category)

        panel = TicketPanel(
            guild_id=guild_id,
            channel_id=channel_id,
            title=title,
            description=description or None,
        )
        db.add(panel)
        await db.commit()
        await db.refresh(panel)

        # Link auto-created category
        assoc = TicketPanelCategory(
            panel_id=panel.id,
            category_id=category.id,
            position=0,
        )
        db.add(assoc)

        # Link additional categories if provided
        for i, cat_id in enumerate(category_ids):
            existing = await db.execute(
                select(TicketCategory).where(TicketCategory.id == int(cat_id))
            )
            if existing.scalar_one_or_none():
                db.add(
                    TicketPanelCategory(
                        panel_id=panel.id,
                        category_id=int(cat_id),
                        position=i + 1,
                    )
                )

        await db.commit()
        await db.refresh(assoc)

        # Post to Discord
        category_names: dict[int, str] = {category.id: category.name}
        for cat_id in category_ids:
            cat_r = await db.execute(
                select(TicketCategory).where(TicketCategory.id == int(cat_id))
            )
            cat_obj = cat_r.scalar_one_or_none()
            if cat_obj:
                category_names[cat_obj.id] = cat_obj.name

        # Reload associations
        assoc_result = await db.execute(
            select(TicketPanelCategory)
            .where(TicketPanelCategory.panel_id == panel.id)
            .order_by(TicketPanelCategory.position)
        )
        all_assocs = list(assoc_result.scalars().all())

        success, message_id, _error = await post_ticket_panel_to_discord(
            panel, all_assocs, category_names
        )
        if success and message_id:
            panel.message_id = message_id
            await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True, "panel_id": panel.id}, status_code=201)


@router.put("/tickets/panels/{panel_id}", response_model=None)
async def api_ticket_panels_update(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Update ticket panel title and description."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    body: dict[str, Any] = await request.json()
    title = str(body.get("title", "")).strip()
    description = str(body.get("description", "")).strip()

    if not title:
        return JSONResponse({"error": "Title is required"}, status_code=400)
    if len(title) > 100:
        return JSONResponse(
            {"error": "Title must be 100 characters or less"}, status_code=400
        )
    if len(description) > 2000:
        return JSONResponse(
            {"error": "Description must be 2000 characters or less"}, status_code=400
        )

    result = await db.execute(select(TicketPanel).where(TicketPanel.id == panel_id))
    panel = result.scalar_one_or_none()
    if not panel:
        return JSONResponse({"error": "Not found"}, status_code=404)

    panel.title = title
    panel.description = description or None
    await db.commit()
    _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.delete("/tickets/panels/{panel_id}", response_model=None)
async def api_ticket_panels_delete(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete a ticket panel (and its Discord message if posted)."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"ticket_panel:delete:{panel_id}"):
        result = await db.execute(select(TicketPanel).where(TicketPanel.id == panel_id))
        panel = result.scalar_one_or_none()
        if not panel:
            return JSONResponse({"error": "Not found"}, status_code=404)

        if panel.message_id:
            await delete_discord_message(panel.channel_id, panel.message_id)

        await db.delete(panel)
        await db.commit()
        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.post("/tickets/panels/{panel_id}/post", response_model=None)
async def api_ticket_panels_post_to_discord(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Post or update a ticket panel in Discord."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

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
        return JSONResponse({"error": "Not found"}, status_code=404)

    sorted_cat_assoc = sorted(panel.category_associations, key=lambda a: a.position)
    category_names = {
        a.category_id: (a.category.name if a.category else "Ticket")
        for a in sorted_cat_assoc
    }

    if panel.message_id:
        ok, error = await edit_ticket_panel_in_discord(
            panel, sorted_cat_assoc, category_names
        )
        if not ok:
            return JSONResponse({"error": error or "Unknown error"}, status_code=502)
        _security.record_form_submit(user_email, path)
        return JSONResponse({"ok": True, "message": "Updated in Discord"})
    else:
        ok, message_id, error = await post_ticket_panel_to_discord(
            panel, sorted_cat_assoc, category_names
        )
        if not ok:
            return JSONResponse({"error": error or "Unknown error"}, status_code=502)
        if message_id:
            panel.message_id = message_id
            await db.commit()
        _security.record_form_submit(user_email, path)
        return JSONResponse({"ok": True, "message": "Posted to Discord"})


@router.put("/tickets/panels/{panel_id}/buttons/{assoc_id}", response_model=None)
async def api_ticket_panels_update_button(
    request: Request,
    panel_id: int,
    assoc_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Update button appearance for a panel category association."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    result = await db.execute(
        select(TicketPanelCategory).where(
            TicketPanelCategory.id == assoc_id,
            TicketPanelCategory.panel_id == panel_id,
        )
    )
    assoc = result.scalar_one_or_none()
    if not assoc:
        return JSONResponse({"error": "Button not found"}, status_code=404)

    body: dict[str, Any] = await request.json()

    label = str(body.get("label", "")).strip()
    if len(label) > 80:
        label = label[:80]
    assoc.button_label = label or None

    valid_styles = ("primary", "secondary", "success", "danger")
    style = str(body.get("style", "primary")).strip()
    assoc.button_style = style if style in valid_styles else "primary"

    emoji = str(body.get("emoji", "")).strip()
    if len(emoji) > 64:
        emoji = emoji[:64]
    assoc.button_emoji = emoji or None

    await db.commit()
    _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})
