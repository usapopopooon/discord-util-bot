"""API v1 event log routes (JSON)."""

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
from src.database.models import EventLogConfig
from src.utils import get_resource_lock
from src.web.jwt_auth import get_current_user_jwt

router = APIRouter(prefix="/api/v1", tags=["api-eventlog"])


class _EventLogCreateRequest(BaseModel):
    guild_id: str
    event_type: str
    channel_id: str


@router.get("/eventlog", response_model=None)
async def api_eventlog_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List all event log configs."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(select(EventLogConfig).order_by(EventLogConfig.id))
    configs = list(result.scalars().all())

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)

    return JSONResponse(
        {
            "configs": [
                {
                    "id": c.id,
                    "guild_id": c.guild_id,
                    "event_type": c.event_type,
                    "channel_id": c.channel_id,
                    "enabled": c.enabled,
                }
                for c in configs
            ],
            "guilds": guilds_map,
            "channels": {
                gid: [{"id": cid, "name": cname} for cid, cname in clist]
                for gid, clist in channels_map.items()
            },
        }
    )


@router.post("/eventlog", response_model=None)
async def api_eventlog_create(
    request: Request,
    body: _EventLogCreateRequest,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Create an event log config."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    if not body.guild_id or not body.channel_id:
        return JSONResponse(
            {"error": "guild_id and channel_id are required"},
            status_code=422,
        )

    if body.event_type not in EventLogConfig.VALID_EVENT_TYPES:
        return JSONResponse(
            {"error": f"Invalid event_type: {body.event_type}"},
            status_code=422,
        )

    async with get_resource_lock(f"eventlog:create:{body.guild_id}:{body.event_type}"):
        config = EventLogConfig(
            guild_id=body.guild_id,
            event_type=body.event_type,
            channel_id=body.channel_id,
        )
        db.add(config)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return JSONResponse(
                {"error": "Duplicate guild_id + event_type combination"},
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
                    "event_type": config.event_type,
                    "channel_id": config.channel_id,
                    "enabled": config.enabled,
                },
            },
            status_code=201,
        )


@router.delete("/eventlog/{config_id}", response_model=None)
async def api_eventlog_delete(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete an event log config."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"eventlog:delete:{config_id}"):
        result = await db.execute(
            select(EventLogConfig).where(EventLogConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return JSONResponse({"error": "Not found"}, status_code=404)

        await db.delete(config)
        await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.patch("/eventlog/{config_id}/toggle", response_model=None)
async def api_eventlog_toggle(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Toggle an event log config enabled state."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"eventlog:toggle:{config_id}"):
        result = await db.execute(
            select(EventLogConfig).where(EventLogConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return JSONResponse({"error": "Not found"}, status_code=404)

        config.enabled = not config.enabled
        await db.commit()

        _security.record_form_submit(user_email, path)

        return JSONResponse({"ok": True, "enabled": config.enabled})
