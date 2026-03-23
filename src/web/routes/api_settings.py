"""API v1 settings / maintenance routes (JSON, JWT auth)."""

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
from src.constants import BCRYPT_MAX_PASSWORD_BYTES, PASSWORD_MIN_LENGTH
from src.database.models import (
    BumpConfig,
    BumpReminder,
    DiscordGuild,
    Lobby,
    RolePanel,
    SiteSettings,
    StickyMessage,
)
from src.utils import get_resource_lock, set_timezone_offset
from src.web.jwt_auth import get_current_user_jwt

router = APIRouter(prefix="/api/v1", tags=["api-settings"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class _TimezoneRequest(BaseModel):
    timezone_offset: int


class _EmailRequest(BaseModel):
    new_email: str


class _PasswordRequest(BaseModel):
    new_password: str
    confirm_password: str


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=None)
async def api_dashboard(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
) -> JSONResponse:
    """Return current user info for the dashboard."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    return JSONResponse({"email": user.get("sub", "")})


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@router.get("/settings", response_model=None)
async def api_settings_get(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Return current settings (email, pending email, timezone)."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    admin = await _db.get_or_create_admin(db)
    if admin is None:
        return JSONResponse({"error": "Admin not configured"}, status_code=500)

    result = await db.execute(select(SiteSettings).limit(1))
    site = result.scalar_one_or_none()

    return JSONResponse(
        {
            "email": admin.email,
            "pending_email": admin.pending_email,
            "timezone_offset": site.timezone_offset if site else 9,
        }
    )


@router.put("/settings/timezone", response_model=None)
async def api_settings_timezone(
    request: Request,
    body: _TimezoneRequest,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Update timezone offset."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    if body.timezone_offset < -12 or body.timezone_offset > 14:
        return JSONResponse(
            {"error": "timezone_offset must be between -12 and 14"},
            status_code=400,
        )

    async with get_resource_lock("site_settings:update"):
        result = await db.execute(select(SiteSettings).limit(1))
        site = result.scalar_one_or_none()
        if site:
            site.timezone_offset = body.timezone_offset
            site.updated_at = datetime.now(UTC)
        else:
            site = SiteSettings(timezone_offset=body.timezone_offset)
            db.add(site)
        await db.commit()

        set_timezone_offset(body.timezone_offset)
        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.put("/settings/email", response_model=None)
async def api_settings_email(
    request: Request,
    body: _EmailRequest,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Update email address."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    admin = await _db.get_or_create_admin(db)
    if admin is None:
        return JSONResponse({"error": "Admin not configured"}, status_code=500)

    new_email = body.new_email.strip() if body.new_email else ""

    if not new_email:
        return JSONResponse({"error": "Email address is required"}, status_code=400)

    if not _security.EMAIL_PATTERN.match(new_email):
        return JSONResponse({"error": "Invalid email format"}, status_code=400)

    if new_email == admin.email:
        return JSONResponse(
            {"error": "New email must be different from current email"},
            status_code=400,
        )

    # Update email directly (same behavior as HTML route when SMTP is not configured)
    admin.email = new_email
    admin.pending_email = None
    admin.email_change_token = None
    admin.email_change_token_expires_at = None
    await db.commit()

    _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.put("/settings/password", response_model=None)
async def api_settings_password(
    request: Request,
    body: _PasswordRequest,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Update password."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    admin = await _db.get_or_create_admin(db)
    if admin is None:
        return JSONResponse({"error": "Admin not configured"}, status_code=500)

    if not body.new_password:
        return JSONResponse({"error": "Password is required"}, status_code=400)

    if body.new_password != body.confirm_password:
        return JSONResponse({"error": "Passwords do not match"}, status_code=400)

    if len(body.new_password) < PASSWORD_MIN_LENGTH:
        return JSONResponse(
            {"error": f"Password must be at least {PASSWORD_MIN_LENGTH} characters"},
            status_code=400,
        )

    if len(body.new_password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        return JSONResponse(
            {"error": f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes"},
            status_code=400,
        )

    admin.password_hash = await _security.hash_password_async(body.new_password)
    admin.password_changed_at = datetime.now(UTC)
    await db.commit()

    _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


@router.get("/maintenance", response_model=None)
async def api_maintenance(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Return maintenance statistics."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    # Active guild IDs from the DiscordGuild cache table
    guild_result = await db.execute(select(DiscordGuild.guild_id))
    active_guild_ids = {row[0] for row in guild_result.fetchall()}

    lobby_result = await db.execute(select(Lobby))
    lobbies = list(lobby_result.scalars().all())
    lobby_orphaned = sum(
        1 for lobby in lobbies if lobby.guild_id not in active_guild_ids
    )

    bump_result = await db.execute(select(BumpConfig))
    bump_configs = list(bump_result.scalars().all())
    bump_orphaned = sum(1 for c in bump_configs if c.guild_id not in active_guild_ids)

    sticky_result = await db.execute(select(StickyMessage))
    stickies = list(sticky_result.scalars().all())
    sticky_orphaned = sum(1 for s in stickies if s.guild_id not in active_guild_ids)

    panel_result = await db.execute(select(RolePanel))
    panels = list(panel_result.scalars().all())
    panel_orphaned = sum(1 for p in panels if p.guild_id not in active_guild_ids)

    return JSONResponse(
        {
            "guild_count": len(active_guild_ids),
            "lobbies": {
                "total": len(lobbies),
                "orphaned": lobby_orphaned,
            },
            "bump_configs": {
                "total": len(bump_configs),
                "orphaned": bump_orphaned,
            },
            "stickies": {
                "total": len(stickies),
                "orphaned": sticky_orphaned,
            },
            "role_panels": {
                "total": len(panels),
                "orphaned": panel_orphaned,
            },
        }
    )


@router.post("/maintenance/cleanup", response_model=None)
async def api_maintenance_cleanup(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Cleanup orphaned database records."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock("maintenance:cleanup"):
        guild_result = await db.execute(select(DiscordGuild.guild_id))
        active_guild_ids = {row[0] for row in guild_result.fetchall()}

        # Delete orphaned lobbies
        lobby_result = await db.execute(select(Lobby))
        lobbies = list(lobby_result.scalars().all())
        lobby_deleted = 0
        for lobby in lobbies:
            if lobby.guild_id not in active_guild_ids:
                await db.delete(lobby)
                lobby_deleted += 1

        # Delete orphaned bump configs and their reminders
        bump_result = await db.execute(select(BumpConfig))
        bump_configs = list(bump_result.scalars().all())
        bump_deleted = 0
        for config in bump_configs:
            if config.guild_id not in active_guild_ids:
                reminder_result = await db.execute(
                    select(BumpReminder).where(BumpReminder.guild_id == config.guild_id)
                )
                for reminder in reminder_result.scalars().all():
                    await db.delete(reminder)
                await db.delete(config)
                bump_deleted += 1

        # Delete orphaned stickies
        sticky_result = await db.execute(select(StickyMessage))
        stickies = list(sticky_result.scalars().all())
        sticky_deleted = 0
        for sticky in stickies:
            if sticky.guild_id not in active_guild_ids:
                await db.delete(sticky)
                sticky_deleted += 1

        # Delete orphaned role panels
        panel_result = await db.execute(select(RolePanel))
        panels = list(panel_result.scalars().all())
        panel_deleted = 0
        for panel in panels:
            if panel.guild_id not in active_guild_ids:
                await db.delete(panel)
                panel_deleted += 1

        await db.commit()
        _security.record_form_submit(user_email, path)

    return JSONResponse(
        {
            "ok": True,
            "deleted": {
                "lobbies": lobby_deleted,
                "bump_configs": bump_deleted,
                "stickies": sticky_deleted,
                "role_panels": panel_deleted,
            },
        }
    )
