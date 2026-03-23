"""API v1 bump routes (JSON)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.db_helpers as _db
import src.web.security as _security
from src.database.models import BumpConfig, BumpReminder
from src.utils import get_resource_lock
from src.web.jwt_auth import get_current_user_jwt

router = APIRouter(prefix="/api/v1", tags=["api-bump"])


@router.get("/bump", response_model=None)
async def api_bump_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List all bump configs and reminders."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    configs_result = await db.execute(select(BumpConfig))
    configs = list(configs_result.scalars().all())

    reminders_result = await db.execute(
        select(BumpReminder).order_by(BumpReminder.guild_id)
    )
    reminders = list(reminders_result.scalars().all())

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)

    return JSONResponse(
        {
            "configs": [
                {
                    "guild_id": c.guild_id,
                    "channel_id": c.channel_id,
                }
                for c in configs
            ],
            "reminders": [
                {
                    "id": r.id,
                    "guild_id": r.guild_id,
                    "channel_id": r.channel_id,
                    "service_name": r.service_name,
                    "is_enabled": r.is_enabled,
                    "role_id": r.role_id,
                }
                for r in reminders
            ],
            "guilds": guilds_map,
            "channels": {
                gid: [{"id": cid, "name": cname} for cid, cname in clist]
                for gid, clist in channels_map.items()
            },
        }
    )


@router.delete("/bump/configs/{guild_id}", response_model=None)
async def api_bump_config_delete(
    request: Request,
    guild_id: str,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete a bump config."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"bump_config:delete:{guild_id}"):
        result = await db.execute(
            select(BumpConfig).where(BumpConfig.guild_id == guild_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return JSONResponse({"error": "Not found"}, status_code=404)

        await db.delete(config)
        await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.delete("/bump/reminders/{reminder_id}", response_model=None)
async def api_bump_reminder_delete(
    request: Request,
    reminder_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete a bump reminder."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"bump_reminder:delete:{reminder_id}"):
        result = await db.execute(
            select(BumpReminder).where(BumpReminder.id == reminder_id)
        )
        reminder = result.scalar_one_or_none()
        if not reminder:
            return JSONResponse({"error": "Not found"}, status_code=404)

        await db.delete(reminder)
        await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.patch("/bump/reminders/{reminder_id}/toggle", response_model=None)
async def api_bump_reminder_toggle(
    request: Request,
    reminder_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Toggle a bump reminder enabled state."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"bump_reminder:toggle:{reminder_id}"):
        result = await db.execute(
            select(BumpReminder).where(BumpReminder.id == reminder_id)
        )
        reminder = result.scalar_one_or_none()
        if not reminder:
            return JSONResponse({"error": "Not found"}, status_code=404)

        reminder.is_enabled = not reminder.is_enabled
        await db.commit()

        _security.record_form_submit(user_email, path)

        return JSONResponse({"ok": True, "enabled": reminder.is_enabled})
