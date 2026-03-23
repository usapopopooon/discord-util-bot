"""API v1 join role routes (JSON)."""

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
from src.database.models import JoinRoleConfig
from src.utils import get_resource_lock
from src.web.jwt_auth import get_current_user_jwt

router = APIRouter(prefix="/api/v1", tags=["api-joinrole"])


class _JoinRoleCreateRequest(BaseModel):
    guild_id: str
    role_id: str
    duration_hours: int


@router.get("/joinrole", response_model=None)
async def api_joinrole_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List all join role configs."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(select(JoinRoleConfig).order_by(JoinRoleConfig.id))
    configs = list(result.scalars().all())

    guilds_map, _ = await _db._get_discord_guilds_and_channels(db)
    roles_by_guild = await _db._get_discord_roles_by_guild(db)

    return JSONResponse(
        {
            "configs": [
                {
                    "id": c.id,
                    "guild_id": c.guild_id,
                    "role_id": c.role_id,
                    "duration_hours": c.duration_hours,
                    "enabled": c.enabled,
                }
                for c in configs
            ],
            "guilds": guilds_map,
            "roles": {
                gid: [
                    {"id": rid, "name": rname, "color": rcolor}
                    for rid, rname, rcolor in rlist
                ]
                for gid, rlist in roles_by_guild.items()
            },
        }
    )


@router.post("/joinrole", response_model=None)
async def api_joinrole_create(
    request: Request,
    body: _JoinRoleCreateRequest,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Create a join role config."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    if body.duration_hours < 1 or body.duration_hours > 720:
        return JSONResponse(
            {"error": "duration_hours must be between 1 and 720"},
            status_code=422,
        )

    if not body.guild_id or not body.role_id:
        return JSONResponse(
            {"error": "guild_id and role_id are required"},
            status_code=422,
        )

    async with get_resource_lock(f"joinrole:create:{body.guild_id}:{body.role_id}"):
        config = JoinRoleConfig(
            guild_id=body.guild_id,
            role_id=body.role_id,
            duration_hours=body.duration_hours,
        )
        db.add(config)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return JSONResponse(
                {"error": "Duplicate guild_id + role_id combination"},
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
                    "role_id": config.role_id,
                    "duration_hours": config.duration_hours,
                    "enabled": config.enabled,
                },
            },
            status_code=201,
        )


@router.delete("/joinrole/{config_id}", response_model=None)
async def api_joinrole_delete(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete a join role config."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"joinrole:delete:{config_id}"):
        result = await db.execute(
            select(JoinRoleConfig).where(JoinRoleConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return JSONResponse({"error": "Not found"}, status_code=404)

        await db.delete(config)
        await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.patch("/joinrole/{config_id}/toggle", response_model=None)
async def api_joinrole_toggle(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Toggle a join role config enabled state."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"joinrole:toggle:{config_id}"):
        result = await db.execute(
            select(JoinRoleConfig).where(JoinRoleConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return JSONResponse({"error": "Not found"}, status_code=404)

        config.enabled = not config.enabled
        await db.commit()

        _security.record_form_submit(user_email, path)

        return JSONResponse({"ok": True, "enabled": config.enabled})
