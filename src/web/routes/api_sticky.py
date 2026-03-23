"""API v1 sticky message routes (JSON)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.db_helpers as _db
import src.web.security as _security
from src.database.models import StickyMessage
from src.utils import get_resource_lock
from src.web.jwt_auth import get_current_user_jwt

router = APIRouter(prefix="/api/v1", tags=["api-sticky"])


@router.get("/sticky", response_model=None)
async def api_sticky_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List all sticky messages."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(select(StickyMessage).order_by(StickyMessage.created_at))
    stickies = list(result.scalars().all())

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)

    return JSONResponse(
        {
            "stickies": [
                {
                    "id": idx,
                    "channel_id": s.channel_id,
                    "guild_id": s.guild_id,
                    "message_type": s.message_type,
                    "title": s.title,
                    "description": s.description,
                    "color": s.color,
                    "cooldown_seconds": s.cooldown_seconds,
                }
                for idx, s in enumerate(stickies, 1)
            ],
            "guilds": guilds_map,
            "channels": {
                gid: [{"id": cid, "name": cname} for cid, cname in clist]
                for gid, clist in channels_map.items()
            },
        }
    )


@router.delete("/sticky/{channel_id}", response_model=None)
async def api_sticky_delete(
    request: Request,
    channel_id: str,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete a sticky message by channel_id."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"sticky:delete:{channel_id}"):
        result = await db.execute(
            select(StickyMessage).where(StickyMessage.channel_id == channel_id)
        )
        sticky = result.scalar_one_or_none()
        if not sticky:
            return JSONResponse({"error": "Not found"}, status_code=404)

        await db.delete(sticky)
        await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})
