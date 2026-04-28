"""API v1 chat role routes (JSON)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.db_helpers as _db
import src.web.security as _security
from src.database.models import ChatRoleConfig
from src.utils import get_resource_lock
from src.web.jwt_auth import get_current_user_jwt

router = APIRouter(prefix="/api/v1", tags=["api-chatrole"])


class _ChatRoleCreateRequest(BaseModel):
    guild_id: str
    channel_id: str
    role_id: str
    threshold: int
    duration_hours: int | None = None


@router.get("/chatrole", response_model=None)
async def api_chatrole_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List all chat role configs."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(select(ChatRoleConfig).order_by(ChatRoleConfig.id))
    configs = list(result.scalars().all())

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)
    roles_by_guild = await _db._get_discord_roles_by_guild(db)

    return JSONResponse(
        {
            "configs": [
                {
                    "id": c.id,
                    "guild_id": c.guild_id,
                    "channel_id": c.channel_id,
                    "role_id": c.role_id,
                    "threshold": c.threshold,
                    "duration_hours": c.duration_hours,
                    "enabled": c.enabled,
                }
                for c in configs
            ],
            "guilds": guilds_map,
            "channels": {
                gid: [{"id": cid, "name": cname} for cid, cname in clist]
                for gid, clist in channels_map.items()
            },
            "roles": {
                gid: [
                    {"id": rid, "name": rname, "color": rcolor}
                    for rid, rname, rcolor in rlist
                ]
                for gid, rlist in roles_by_guild.items()
            },
        }
    )


@router.post("/chatrole", response_model=None)
async def api_chatrole_create(
    request: Request,
    body: _ChatRoleCreateRequest,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Create a chat role config."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    if body.threshold < 1 or body.threshold > 10000:
        return JSONResponse(
            {"error": "threshold must be between 1 and 10000"},
            status_code=422,
        )

    if body.duration_hours is not None and (
        body.duration_hours < 1 or body.duration_hours > 8760
    ):
        return JSONResponse(
            {"error": "duration_hours must be between 1 and 8760"},
            status_code=422,
        )

    if not body.guild_id or not body.channel_id or not body.role_id:
        return JSONResponse(
            {"error": "guild_id, channel_id and role_id are required"},
            status_code=422,
        )

    async with get_resource_lock(
        f"chatrole:create:{body.guild_id}:{body.channel_id}:{body.role_id}"
    ):
        config = ChatRoleConfig(
            guild_id=body.guild_id,
            channel_id=body.channel_id,
            role_id=body.role_id,
            threshold=body.threshold,
            duration_hours=body.duration_hours,
        )
        db.add(config)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return JSONResponse(
                {"error": "Duplicate guild_id + channel_id + role_id combination"},
                status_code=409,
            )

        _security.record_form_submit(user_email, path)

        await db.refresh(config)
        return JSONResponse(
            {
                "ok": True,
                "config": {
                    "id": config.id,
                    "guild_id": config.guild_id,
                    "channel_id": config.channel_id,
                    "role_id": config.role_id,
                    "threshold": config.threshold,
                    "duration_hours": config.duration_hours,
                    "enabled": config.enabled,
                },
            },
            status_code=201,
        )


@router.delete("/chatrole/{config_id}", response_model=None)
async def api_chatrole_delete(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete a chat role config."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"chatrole:delete:{config_id}"):
        result = await db.execute(
            select(ChatRoleConfig).where(ChatRoleConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return JSONResponse({"error": "Not found"}, status_code=404)

        await db.delete(config)
        await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.patch("/chatrole/{config_id}/toggle", response_model=None)
async def api_chatrole_toggle(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Toggle a chat role config enabled state."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"chatrole:toggle:{config_id}"):
        result = await db.execute(
            select(ChatRoleConfig).where(ChatRoleConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return JSONResponse({"error": "Not found"}, status_code=404)

        config.enabled = not config.enabled
        await db.commit()

        _security.record_form_submit(user_email, path)

        return JSONResponse({"ok": True, "enabled": config.enabled})
