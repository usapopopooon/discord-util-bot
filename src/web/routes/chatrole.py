"""Chat Role routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.app as _app
from src.database.models import ChatRoleConfig
from src.utils import get_resource_lock
from src.web.templates import chatrole_page

router = APIRouter()


@router.get("/chatrole", response_model=None)
async def chatrole_list(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Chat Role 設定一覧ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(ChatRoleConfig).order_by(ChatRoleConfig.id))
    configs = list(result.scalars().all())

    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)
    roles_by_guild = await _app._get_discord_roles_by_guild(db)

    return HTMLResponse(
        content=chatrole_page(
            configs,
            csrf_token=_app.generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
            roles_by_guild=roles_by_guild,
        )
    )


@router.post("/chatrole/new", response_model=None)
async def chatrole_create(
    request: Request,
    guild_id: Annotated[str, Form()],
    channel_id: Annotated[str, Form()],
    role_id: Annotated[str, Form()],
    threshold: Annotated[str, Form()],
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    duration_hours: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Chat Role 設定を作成する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/chatrole", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/chatrole", status_code=302)

    try:
        threshold_int = int(threshold)
    except ValueError:
        return RedirectResponse(url="/chatrole", status_code=302)

    if threshold_int < 1 or threshold_int > 10000:
        return RedirectResponse(url="/chatrole", status_code=302)

    duration_hours_int: int | None
    if duration_hours.strip():
        try:
            duration_hours_int = int(duration_hours)
        except ValueError:
            return RedirectResponse(url="/chatrole", status_code=302)
        if duration_hours_int < 1 or duration_hours_int > 8760:
            return RedirectResponse(url="/chatrole", status_code=302)
    else:
        duration_hours_int = None

    if not guild_id or not channel_id or not role_id:
        return RedirectResponse(url="/chatrole", status_code=302)

    async with get_resource_lock(f"chatrole:create:{guild_id}:{channel_id}:{role_id}"):
        config = ChatRoleConfig(
            guild_id=guild_id,
            channel_id=channel_id,
            role_id=role_id,
            threshold=threshold_int,
            duration_hours=duration_hours_int,
        )
        db.add(config)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/chatrole", status_code=302)


@router.post("/chatrole/{config_id}/delete", response_model=None)
async def chatrole_delete(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Chat Role 設定を削除する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/chatrole", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/chatrole", status_code=302)

    async with get_resource_lock(f"chatrole:delete:{config_id}"):
        result = await db.execute(
            select(ChatRoleConfig).where(ChatRoleConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config:
            await db.delete(config)
            await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/chatrole", status_code=302)


@router.post("/chatrole/{config_id}/toggle", response_model=None)
async def chatrole_toggle(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Chat Role 設定の有効/無効を切り替える。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/chatrole", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/chatrole", status_code=302)

    async with get_resource_lock(f"chatrole:toggle:{config_id}"):
        result = await db.execute(
            select(ChatRoleConfig).where(ChatRoleConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config:
            config.enabled = not config.enabled
            await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/chatrole", status_code=302)
