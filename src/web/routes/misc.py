"""Miscellaneous routes: activity, health settings, event log."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.app as _app
from src.database.models import BotActivity, EventLogConfig, HealthConfig
from src.utils import get_resource_lock
from src.web.templates import (
    activity_page,
    eventlog_page,
    health_settings_page,
)

router = APIRouter()


# =============================================================================
# Health check
# =============================================================================


@router.get("/health", response_model=None)
async def health_check() -> Response:
    """Health check endpoint for Docker/load balancer health checks.

    Returns 200 if the application is running and can connect to the database.
    Returns 503 if the database connection fails.
    """
    if await _app.check_database_connection():
        return Response(content="ok", media_type="text/plain", status_code=200)
    return Response(
        content="database unavailable", media_type="text/plain", status_code=503
    )


# =============================================================================
# Bot Activity
# =============================================================================


@router.get("/activity", response_model=None)
async def activity_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Bot Activity settings page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(BotActivity).limit(1))
    bot_act = result.scalar_one_or_none()

    return HTMLResponse(
        content=activity_page(
            activity_type=bot_act.activity_type if bot_act else "playing",
            activity_text=bot_act.activity_text
            if bot_act
            else "\u304a\u83d3\u5b50\u3092\u98df\u3079\u3066\u3044\u307e\u3059",
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/activity", response_model=None)
async def activity_post(
    request: Request,
    activity_type: Annotated[str, Form()],
    activity_text: Annotated[str, Form()],
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Update Bot Activity settings."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/activity", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/activity", status_code=302)

    activity_text = activity_text.strip()
    if not activity_text or len(activity_text) > 128:
        return RedirectResponse(url="/activity", status_code=302)

    if activity_type not in _app._VALID_ACTIVITY_TYPES:
        return RedirectResponse(url="/activity", status_code=302)

    async with get_resource_lock("bot_activity:update"):
        result = await db.execute(select(BotActivity).limit(1))
        bot_act = result.scalar_one_or_none()
        if bot_act:
            bot_act.activity_type = activity_type
            bot_act.activity_text = activity_text
            bot_act.updated_at = datetime.now(UTC)
        else:
            bot_act = BotActivity(
                activity_type=activity_type,
                activity_text=activity_text,
            )
            db.add(bot_act)
        await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/activity", status_code=302)


# =============================================================================
# Health Monitor Routes
# =============================================================================


@router.get("/health/settings", response_model=None)
async def health_settings_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Health monitor 設定ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)

    result = await db.execute(select(HealthConfig))
    configs = list(result.scalars().all())
    configs_map = {c.guild_id: c.channel_id for c in configs}

    return HTMLResponse(
        content=health_settings_page(
            guilds_map=guilds_map,
            channels_map=channels_map,
            configs_map=configs_map,
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/health/settings", response_model=None)
async def health_settings_post(
    request: Request,
    guild_id: Annotated[str, Form()],
    channel_id: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Health monitor 設定を保存する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/health/settings", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/health/settings", status_code=302)

    if not guild_id or not channel_id.strip():
        return RedirectResponse(url="/health/settings", status_code=302)

    async with get_resource_lock(f"health:settings:{guild_id}"):
        existing = await db.execute(
            select(HealthConfig).where(HealthConfig.guild_id == guild_id)
        )
        config = existing.scalar_one_or_none()

        if config:
            config.channel_id = channel_id.strip()
        else:
            config = HealthConfig(guild_id=guild_id, channel_id=channel_id.strip())
            db.add(config)

        await db.commit()
        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/health/settings", status_code=302)


@router.post("/health/settings/{guild_id}/delete", response_model=None)
async def health_settings_delete(
    request: Request,
    guild_id: str,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Health monitor 設定を削除する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/health/settings", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/health/settings", status_code=302)

    async with get_resource_lock(f"health:delete:{guild_id}"):
        result = await db.execute(
            select(HealthConfig).where(HealthConfig.guild_id == guild_id)
        )
        config = result.scalar_one_or_none()
        if config:
            await db.delete(config)
            await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/health/settings", status_code=302)


# =============================================================================
# Event Log
# =============================================================================


@router.get("/eventlog", response_model=None)
async def eventlog_list(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Event Log 設定一覧ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(EventLogConfig).order_by(EventLogConfig.id))
    configs = list(result.scalars().all())

    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=eventlog_page(
            configs,
            csrf_token=_app.generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
        )
    )


@router.post("/eventlog/new", response_model=None)
async def eventlog_create(
    request: Request,
    guild_id: Annotated[str, Form()],
    event_type: Annotated[str, Form()],
    channel_id: Annotated[str, Form()],
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Event Log 設定を作成する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/eventlog", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/eventlog", status_code=302)

    if not guild_id or not channel_id:
        return RedirectResponse(url="/eventlog", status_code=302)

    if event_type not in EventLogConfig.VALID_EVENT_TYPES:
        return RedirectResponse(url="/eventlog", status_code=302)

    async with get_resource_lock(f"eventlog:create:{guild_id}:{event_type}"):
        config = EventLogConfig(
            guild_id=guild_id,
            event_type=event_type,
            channel_id=channel_id,
        )
        db.add(config)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/eventlog", status_code=302)


@router.post("/eventlog/{config_id}/delete", response_model=None)
async def eventlog_delete(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Event Log 設定を削除する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/eventlog", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/eventlog", status_code=302)

    async with get_resource_lock(f"eventlog:delete:{config_id}"):
        result = await db.execute(
            select(EventLogConfig).where(EventLogConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config:
            await db.delete(config)
            await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/eventlog", status_code=302)


@router.post("/eventlog/{config_id}/toggle", response_model=None)
async def eventlog_toggle(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Event Log 設定の有効/無効を切り替える。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/eventlog", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/eventlog", status_code=302)

    async with get_resource_lock(f"eventlog:toggle:{config_id}"):
        result = await db.execute(
            select(EventLogConfig).where(EventLogConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config:
            config.enabled = not config.enabled
            await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/eventlog", status_code=302)
