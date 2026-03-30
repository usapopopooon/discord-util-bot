"""API v1 role panel routes (JSON)."""

from __future__ import annotations

import json
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import src.web.db_helpers as _db
import src.web.security as _security
from src.database.models import RolePanel, RolePanelItem
from src.utils import get_resource_lock, is_valid_emoji, normalize_emoji
from src.web.discord_api import (
    add_reactions_to_message,
    delete_discord_message,
    edit_role_panel_in_discord,
    post_role_panel_to_discord,
)
from src.web.jwt_auth import get_current_user_jwt

router = APIRouter(prefix="/api/v1", tags=["api-rolepanels"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_panel(panel: RolePanel, *, item_count: int = 0) -> dict[str, Any]:
    """Serialize a RolePanel to a JSON-safe dict (list view)."""
    try:
        excluded = json.loads(panel.excluded_role_ids)
    except (json.JSONDecodeError, TypeError):
        excluded = []

    return {
        "id": panel.id,
        "guild_id": panel.guild_id,
        "channel_id": panel.channel_id,
        "message_id": panel.message_id,
        "panel_type": panel.panel_type,
        "title": panel.title,
        "description": panel.description,
        "color": panel.color,
        "remove_reaction": panel.remove_reaction,
        "excluded_role_ids": excluded,
        "item_count": item_count,
    }


def _serialize_item(item: RolePanelItem) -> dict[str, Any]:
    """Serialize a RolePanelItem to a JSON-safe dict."""
    return {
        "id": item.id,
        "role_id": item.role_id,
        "emoji": item.emoji,
        "label": item.label,
        "style": item.style,
        "position": item.position,
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


_VALID_STYLES = {"primary", "secondary", "success", "danger"}


# ---------------------------------------------------------------------------
# Form data
# ---------------------------------------------------------------------------


@router.get("/rolepanels/form-data", response_model=None)
async def api_rolepanels_form_data(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Return guilds, channels and roles for panel creation forms."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)
    discord_roles = await _db._get_discord_roles_by_guild(db)

    return JSONResponse(
        {
            "guilds": guilds_map,
            "channels": _channels_payload(channels_map),
            "roles": _roles_payload(discord_roles),
        }
    )


# ---------------------------------------------------------------------------
# Panel CRUD
# ---------------------------------------------------------------------------


@router.get("/rolepanels", response_model=None)
async def api_rolepanels_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List all role panels."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .order_by(RolePanel.created_at.desc())
    )
    panels = list(result.scalars().all())

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)

    return JSONResponse(
        {
            "panels": [_serialize_panel(p, item_count=len(p.items)) for p in panels],
            "guilds": guilds_map,
            "channels": _channels_payload(channels_map),
        }
    )


@router.get("/rolepanels/{panel_id}", response_model=None)
async def api_rolepanels_detail(
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Return a single panel with its items."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .where(RolePanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return JSONResponse({"error": "Not found"}, status_code=404)

    items = sorted(panel.items, key=lambda x: x.position)

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)
    discord_roles = await _db._get_discord_roles_by_guild(db)

    return JSONResponse(
        {
            "panel": {
                **_serialize_panel(panel, item_count=len(items)),
                "use_embed": panel.use_embed,
                "items": [_serialize_item(it) for it in items],
            },
            "guilds": guilds_map,
            "channels": _channels_payload(channels_map),
            "roles": _roles_payload(discord_roles),
        }
    )


@router.post("/rolepanels", response_model=None)
async def api_rolepanels_create(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Create a new role panel with items."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    body: dict[str, Any] = await request.json()

    guild_id = str(body.get("guild_id", "")).strip()
    channel_id = str(body.get("channel_id", "")).strip()
    panel_type = str(body.get("panel_type", "button")).strip()
    title = str(body.get("title", "")).strip()
    description = str(body.get("description", "")).strip()
    color_raw = body.get("color")
    items_raw: list[dict[str, Any]] = body.get("items", [])

    # --- Validation ---
    if not guild_id or not guild_id.isdigit():
        return JSONResponse({"error": "Valid guild_id is required"}, status_code=400)
    if not channel_id or not channel_id.isdigit():
        return JSONResponse({"error": "Valid channel_id is required"}, status_code=400)
    if panel_type not in ("button", "reaction"):
        return JSONResponse({"error": "Invalid panel_type"}, status_code=400)
    if not title:
        return JSONResponse({"error": "Title is required"}, status_code=400)
    if len(title) > 256:
        return JSONResponse(
            {"error": "Title must be 256 characters or less"}, status_code=400
        )
    if len(description) > 4096:
        return JSONResponse(
            {"error": "Description must be 4096 characters or less"}, status_code=400
        )

    color_int: int | None = None
    if color_raw is not None:
        if isinstance(color_raw, int):
            color_int = color_raw if 0 <= color_raw <= 0xFFFFFF else None
        elif isinstance(color_raw, str):
            color_hex = color_raw.strip().lstrip("#")
            if len(color_hex) == 6:
                with suppress(ValueError):
                    color_int = int(color_hex, 16)

    # Validate items
    role_items_data: list[dict[str, Any]] = []
    seen_emojis: set[str] = set()
    for i, raw_item in enumerate(items_raw):
        emoji = str(raw_item.get("emoji", "")).strip()
        role_id = str(raw_item.get("role_id", "")).strip()
        label = str(raw_item.get("label", "")).strip()
        style = str(raw_item.get("style", "secondary")).strip()

        if not emoji:
            return JSONResponse(
                {"error": f"Item {i + 1}: emoji is required"}, status_code=400
            )
        if len(emoji) > 64:
            return JSONResponse(
                {"error": f"Item {i + 1}: emoji must be 64 chars or less"},
                status_code=400,
            )
        if not is_valid_emoji(emoji):
            return JSONResponse(
                {"error": f"Item {i + 1}: invalid emoji"}, status_code=400
            )
        if emoji in seen_emojis:
            return JSONResponse(
                {"error": f"Item {i + 1}: duplicate emoji '{emoji}'"}, status_code=400
            )
        seen_emojis.add(emoji)

        if not role_id or not role_id.isdigit():
            return JSONResponse(
                {"error": f"Item {i + 1}: valid role_id is required"}, status_code=400
            )
        if label and len(label) > 80:
            return JSONResponse(
                {"error": f"Item {i + 1}: label must be 80 chars or less"},
                status_code=400,
            )
        if style not in _VALID_STYLES:
            style = "secondary"

        role_items_data.append(
            {
                "emoji": normalize_emoji(emoji),
                "role_id": role_id,
                "label": label or None,
                "style": style,
                "position": i,
            }
        )

    # Validate excluded_role_ids
    excluded_raw = body.get("excluded_role_ids", [])
    if not isinstance(excluded_raw, list) or not all(
        isinstance(r, str) and r.isdigit() for r in excluded_raw
    ):
        excluded_raw = []
    excluded_json = json.dumps(excluded_raw)

    async with get_resource_lock(f"rolepanel:create:{user_email}"):
        panel = RolePanel(
            guild_id=guild_id,
            channel_id=channel_id,
            panel_type=panel_type,
            title=title,
            description=description or None,
            color=color_int,
            remove_reaction=panel_type == "reaction"
            and bool(body.get("remove_reaction")),
            excluded_role_ids=excluded_json,
        )
        db.add(panel)
        await db.flush()

        for item_data in role_items_data:
            db.add(
                RolePanelItem(
                    panel_id=panel.id,
                    role_id=str(item_data["role_id"]),
                    emoji=str(item_data["emoji"]),
                    label=item_data["label"],
                    style=str(item_data["style"]),
                    position=int(item_data["position"]),
                )
            )

        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            if "uq_panel_emoji" in str(e.orig):
                return JSONResponse(
                    {"error": "Duplicate emoji in role items"}, status_code=400
                )
            raise

        await db.refresh(panel)
        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True, "panel_id": panel.id}, status_code=201)


@router.put("/rolepanels/{panel_id}", response_model=None)
async def api_rolepanels_update(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Update panel metadata (title, description, color)."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    body: dict[str, Any] = await request.json()
    title = str(body.get("title", "")).strip()
    description = str(body.get("description", "")).strip()
    color_raw = body.get("color")

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

    result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
    panel = result.scalar_one_or_none()
    if not panel:
        return JSONResponse({"error": "Not found"}, status_code=404)

    panel.title = title
    panel.description = description or None

    # Update excluded_role_ids
    excluded_raw = body.get("excluded_role_ids")
    if excluded_raw is not None:
        if isinstance(excluded_raw, list) and all(
            isinstance(r, str) and r.isdigit() for r in excluded_raw
        ):
            panel.excluded_role_ids = json.dumps(excluded_raw)
        else:
            panel.excluded_role_ids = "[]"

    if panel.use_embed and color_raw is not None:
        if isinstance(color_raw, int):
            if 0 <= color_raw <= 0xFFFFFF:
                panel.color = color_raw
        elif isinstance(color_raw, str):
            color_hex = color_raw.strip().lstrip("#")
            if len(color_hex) == 6:
                with suppress(ValueError):
                    panel.color = int(color_hex, 16)

    await db.commit()
    _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.delete("/rolepanels/{panel_id}", response_model=None)
async def api_rolepanels_delete(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete a role panel (and its Discord message if posted)."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"rolepanel:delete:{panel_id}"):
        result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
        panel = result.scalar_one_or_none()
        if not panel:
            return JSONResponse({"error": "Not found"}, status_code=404)

        if panel.message_id:
            await delete_discord_message(panel.channel_id, panel.message_id)

        await db.delete(panel)
        await db.commit()
        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.post("/rolepanels/{panel_id}/copy", response_model=None)
async def api_rolepanels_copy(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Duplicate a role panel with all its items."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .where(RolePanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return JSONResponse({"error": "Not found"}, status_code=404)

    async with get_resource_lock(f"rolepanel:copy:{panel_id}"):
        new_panel = RolePanel(
            guild_id=panel.guild_id,
            channel_id=panel.channel_id,
            panel_type=panel.panel_type,
            title=f"{panel.title} (Copy)",
            description=panel.description,
            color=panel.color,
            use_embed=panel.use_embed,
            remove_reaction=panel.remove_reaction,
            excluded_role_ids=panel.excluded_role_ids,
        )
        db.add(new_panel)
        await db.flush()

        for item in sorted(panel.items, key=lambda x: x.position):
            db.add(
                RolePanelItem(
                    panel_id=new_panel.id,
                    role_id=item.role_id,
                    emoji=item.emoji,
                    label=item.label,
                    style=item.style,
                    position=item.position,
                )
            )

        await db.commit()
        await db.refresh(new_panel)
        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True, "new_panel_id": new_panel.id}, status_code=201)


@router.patch("/rolepanels/{panel_id}/toggle-remove-reaction", response_model=None)
async def api_rolepanels_toggle_remove_reaction(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Toggle the remove_reaction flag for a reaction panel."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"rolepanel:toggle:{panel_id}"):
        result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
        panel = result.scalar_one_or_none()
        if not panel:
            return JSONResponse({"error": "Not found"}, status_code=404)

        if panel.panel_type != "reaction":
            return JSONResponse(
                {"error": "Only reaction panels support remove_reaction"},
                status_code=400,
            )

        panel.remove_reaction = not panel.remove_reaction
        await db.commit()
        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True, "remove_reaction": panel.remove_reaction})


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


@router.post("/rolepanels/{panel_id}/items", response_model=None)
async def api_rolepanels_add_item(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Add a role item to a panel."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .where(RolePanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return JSONResponse({"error": "Panel not found"}, status_code=404)

    body: dict[str, Any] = await request.json()
    emoji = str(body.get("emoji", "")).strip()
    role_id = str(body.get("role_id", "")).strip()
    label = str(body.get("label", "")).strip()
    style = str(body.get("style", "secondary")).strip()

    if not emoji:
        return JSONResponse({"error": "Emoji is required"}, status_code=400)
    if len(emoji) > 64:
        return JSONResponse(
            {"error": "Emoji must be 64 characters or less"}, status_code=400
        )
    if not is_valid_emoji(emoji):
        return JSONResponse({"error": "Invalid emoji"}, status_code=400)
    if not role_id or not role_id.isdigit():
        return JSONResponse({"error": "Valid role_id is required"}, status_code=400)
    if label and len(label) > 80:
        return JSONResponse(
            {"error": "Label must be 80 characters or less"}, status_code=400
        )
    if style not in _VALID_STYLES:
        style = "secondary"

    normalized = normalize_emoji(emoji)
    items = sorted(panel.items, key=lambda x: x.position)
    for it in items:
        if it.emoji == normalized:
            return JSONResponse(
                {"error": f"Emoji '{emoji}' is already used in this panel"},
                status_code=400,
            )

    next_position = max((it.position for it in items), default=-1) + 1

    async with get_resource_lock(f"rolepanel:add_item:{panel_id}"):
        item = RolePanelItem(
            panel_id=panel_id,
            role_id=role_id,
            emoji=normalized,
            label=label or None,
            style=style,
            position=next_position,
        )
        db.add(item)

        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            if "uq_panel_emoji" in str(e.orig):
                return JSONResponse(
                    {"error": f"Emoji '{emoji}' is already used in this panel"},
                    status_code=400,
                )
            raise

        await db.refresh(item)
        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True, "item": _serialize_item(item)}, status_code=201)


@router.delete("/rolepanels/{panel_id}/items/{item_id}", response_model=None)
async def api_rolepanels_delete_item(
    request: Request,
    panel_id: int,
    item_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete a role item from a panel."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    panel_result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
    if not panel_result.scalar_one_or_none():
        return JSONResponse({"error": "Panel not found"}, status_code=404)

    async with get_resource_lock(f"rolepanel:delete_item:{panel_id}:{item_id}"):
        result = await db.execute(
            select(RolePanelItem).where(
                RolePanelItem.id == item_id, RolePanelItem.panel_id == panel_id
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            return JSONResponse({"error": "Item not found"}, status_code=404)

        await db.delete(item)
        await db.commit()
        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.put("/rolepanels/{panel_id}/items/reorder", response_model=None)
async def api_rolepanels_reorder_items(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Reorder role items."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    body: dict[str, Any] = await request.json()
    item_ids = body.get("item_ids", [])
    if not isinstance(item_ids, list):
        return JSONResponse({"error": "Invalid item_ids"}, status_code=400)

    panel_result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
    if not panel_result.scalar_one_or_none():
        return JSONResponse({"error": "Panel not found"}, status_code=404)

    async with get_resource_lock(f"rolepanel:reorder:{panel_id}"):
        for position, iid in enumerate(item_ids):
            await db.execute(
                update(RolePanelItem)
                .where(
                    RolePanelItem.id == int(iid),
                    RolePanelItem.panel_id == panel_id,
                )
                .values(position=position)
            )
        await db.commit()

    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Post to Discord
# ---------------------------------------------------------------------------


@router.post("/rolepanels/{panel_id}/post", response_model=None)
async def api_rolepanels_post_to_discord(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Post or update a role panel in Discord."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path
    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .where(RolePanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return JSONResponse({"error": "Not found"}, status_code=404)

    items = sorted(panel.items, key=lambda x: x.position)

    if panel.message_id:
        success, error_msg = await edit_role_panel_in_discord(panel, items)
        message_id = panel.message_id if success else None
        action_text = "Updated"
    else:
        success, message_id, error_msg = await post_role_panel_to_discord(panel, items)
        action_text = "Posted"

    if not success:
        return JSONResponse({"error": error_msg or "Unknown error"}, status_code=502)

    if message_id and message_id != panel.message_id:
        panel.message_id = message_id
        await db.commit()

    target_message_id = message_id or panel.message_id
    if panel.panel_type == "reaction" and items and target_message_id:
        is_edit = action_text == "Updated"
        react_ok, react_error = await add_reactions_to_message(
            panel.channel_id,
            target_message_id,
            items,
            clear_existing=is_edit,
        )
        if not react_ok:
            _security.record_form_submit(user_email, path)
            return JSONResponse(
                {
                    "ok": True,
                    "message": f"{action_text} but reactions failed: {react_error}",
                }
            )

    _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True, "message": f"{action_text} to Discord"})
