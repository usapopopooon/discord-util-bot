"""API v1 miscellaneous routes: health, activity, health settings (JSON)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.db_helpers as _db
import src.web.security as _security
from src.database.engine import check_database_connection
from src.database.models import BotActivity, HealthConfig
from src.utils import get_resource_lock
from src.web.jwt_auth import get_current_user_jwt

router = APIRouter(prefix="/api/v1", tags=["api-misc"])


# =============================================================================
# Health check
# =============================================================================


@router.get("/health", response_model=None)
async def api_health_check() -> JSONResponse:
    """Health check endpoint."""
    if await check_database_connection():
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "database unavailable"}, status_code=503)


# =============================================================================
# Bot Activity
# =============================================================================


@router.get("/activity", response_model=None)
async def api_activity_get(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Return current bot activity setting."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(select(BotActivity).limit(1))
    bot_act = result.scalar_one_or_none()

    return JSONResponse(
        {
            "activity_type": bot_act.activity_type if bot_act else "playing",
            "activity_text": bot_act.activity_text
            if bot_act
            else "\u304a\u83d3\u5b50\u3092\u98df\u3079\u3066\u3044\u307e\u3059",
        }
    )


class _ActivityUpdateRequest(BaseModel):
    activity_type: str
    activity_text: str


@router.put("/activity", response_model=None)
async def api_activity_put(
    request: Request,
    body: _ActivityUpdateRequest,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Update bot activity settings."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    activity_text = body.activity_text.strip()
    if not activity_text or len(activity_text) > 128:
        return JSONResponse(
            {"error": "activity_text must be 1-128 characters"},
            status_code=422,
        )

    if body.activity_type not in _db._VALID_ACTIVITY_TYPES:
        return JSONResponse(
            {"error": f"Invalid activity_type: {body.activity_type}"},
            status_code=422,
        )

    async with get_resource_lock("bot_activity:update"):
        result = await db.execute(select(BotActivity).limit(1))
        bot_act = result.scalar_one_or_none()
        if bot_act:
            bot_act.activity_type = body.activity_type
            bot_act.activity_text = activity_text
            bot_act.updated_at = datetime.now(UTC)
        else:
            bot_act = BotActivity(
                activity_type=body.activity_type,
                activity_text=activity_text,
            )
            db.add(bot_act)
        await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse(
        {
            "ok": True,
            "activity_type": body.activity_type,
            "activity_text": activity_text,
        }
    )


# =============================================================================
# Health Monitor Settings
# =============================================================================


@router.get("/health/settings", response_model=None)
async def api_health_settings_get(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Return health monitor configs."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)

    result = await db.execute(select(HealthConfig))
    configs = list(result.scalars().all())

    return JSONResponse(
        {
            "configs": [
                {
                    "guild_id": c.guild_id,
                    "channel_id": c.channel_id,
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


class _HealthSettingsUpdateRequest(BaseModel):
    guild_id: str
    channel_id: str


@router.put("/health/settings", response_model=None)
async def api_health_settings_put(
    request: Request,
    body: _HealthSettingsUpdateRequest,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Create or update a health monitor config."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    if not body.guild_id or not body.channel_id.strip():
        return JSONResponse(
            {"error": "guild_id and channel_id are required"},
            status_code=422,
        )

    async with get_resource_lock(f"health:settings:{body.guild_id}"):
        existing = await db.execute(
            select(HealthConfig).where(HealthConfig.guild_id == body.guild_id)
        )
        config = existing.scalar_one_or_none()

        if config:
            config.channel_id = body.channel_id.strip()
        else:
            config = HealthConfig(
                guild_id=body.guild_id, channel_id=body.channel_id.strip()
            )
            db.add(config)

        await db.commit()
        _security.record_form_submit(user_email, path)

    return JSONResponse(
        {
            "ok": True,
            "guild_id": body.guild_id,
            "channel_id": body.channel_id.strip(),
        }
    )


@router.delete("/health/settings/{guild_id}", response_model=None)
async def api_health_settings_delete(
    request: Request,
    guild_id: str,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete a health monitor config."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"health:delete:{guild_id}"):
        result = await db.execute(
            select(HealthConfig).where(HealthConfig.guild_id == guild_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return JSONResponse({"error": "Not found"}, status_code=404)

        await db.delete(config)
        await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})
