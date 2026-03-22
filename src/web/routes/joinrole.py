"""Join Role routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.app as _app
from src.database.models import JoinRoleConfig
from src.utils import get_resource_lock
from src.web.templates import joinrole_page

router = APIRouter()


@router.get("/joinrole", response_model=None)
async def joinrole_list(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Join Role 設定一覧ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(JoinRoleConfig).order_by(JoinRoleConfig.id))
    configs = list(result.scalars().all())

    guilds_map, _ = await _app._get_discord_guilds_and_channels(db)
    roles_by_guild = await _app._get_discord_roles_by_guild(db)

    return HTMLResponse(
        content=joinrole_page(
            configs,
            csrf_token=_app.generate_csrf_token(),
            guilds_map=guilds_map,
            roles_by_guild=roles_by_guild,
        )
    )


@router.post("/joinrole/new", response_model=None)
async def joinrole_create(
    request: Request,
    guild_id: Annotated[str, Form()],
    role_id: Annotated[str, Form()],
    duration_hours: Annotated[str, Form()],
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Join Role 設定を作成する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/joinrole", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/joinrole", status_code=302)

    # バリデーション
    try:
        hours = int(duration_hours)
    except ValueError:
        return RedirectResponse(url="/joinrole", status_code=302)

    if hours < 1 or hours > 720:
        return RedirectResponse(url="/joinrole", status_code=302)

    if not guild_id or not role_id:
        return RedirectResponse(url="/joinrole", status_code=302)

    async with get_resource_lock(f"joinrole:create:{guild_id}:{role_id}"):
        config = JoinRoleConfig(
            guild_id=guild_id,
            role_id=role_id,
            duration_hours=hours,
        )
        db.add(config)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/joinrole", status_code=302)


@router.post("/joinrole/{config_id}/delete", response_model=None)
async def joinrole_delete(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Join Role 設定を削除する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/joinrole", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/joinrole", status_code=302)

    async with get_resource_lock(f"joinrole:delete:{config_id}"):
        result = await db.execute(
            select(JoinRoleConfig).where(JoinRoleConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config:
            await db.delete(config)
            await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/joinrole", status_code=302)


@router.post("/joinrole/{config_id}/toggle", response_model=None)
async def joinrole_toggle(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Join Role 設定の有効/無効を切り替える。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/joinrole", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/joinrole", status_code=302)

    async with get_resource_lock(f"joinrole:toggle:{config_id}"):
        result = await db.execute(
            select(JoinRoleConfig).where(JoinRoleConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config:
            config.enabled = not config.enabled
            await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/joinrole", status_code=302)
