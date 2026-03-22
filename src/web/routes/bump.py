"""Bump routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.app as _app
from src.database.models import BumpConfig, BumpReminder
from src.utils import get_resource_lock
from src.web.templates import bump_list_page

router = APIRouter()


@router.get("/bump", response_model=None)
async def bump_list(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """List all bump configs and reminders."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    configs_result = await db.execute(select(BumpConfig))
    configs = list(configs_result.scalars().all())

    reminders_result = await db.execute(
        select(BumpReminder).order_by(BumpReminder.guild_id)
    )
    reminders = list(reminders_result.scalars().all())

    # ギルド・チャンネル名のルックアップを取得
    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=bump_list_page(
            configs,
            reminders,
            csrf_token=_app.generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
        )
    )


@router.post("/bump/config/{guild_id}/delete", response_model=None)
async def bump_config_delete(
    request: Request,
    guild_id: str,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Delete a bump config."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/bump", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/bump", status_code=302)

    # 二重ロック: 同じリソースへの同時操作を防止
    async with get_resource_lock(f"bump_config:delete:{guild_id}"):
        result = await db.execute(
            select(BumpConfig).where(BumpConfig.guild_id == guild_id)
        )
        config = result.scalar_one_or_none()
        if config:
            await db.delete(config)
            await db.commit()

        # クールタイム記録
        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/bump", status_code=302)


@router.post("/bump/reminder/{reminder_id}/delete", response_model=None)
async def bump_reminder_delete(
    request: Request,
    reminder_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Delete a bump reminder."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/bump", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/bump", status_code=302)

    # 二重ロック: 同じリソースへの同時操作を防止
    async with get_resource_lock(f"bump_reminder:delete:{reminder_id}"):
        result = await db.execute(
            select(BumpReminder).where(BumpReminder.id == reminder_id)
        )
        reminder = result.scalar_one_or_none()
        if reminder:
            await db.delete(reminder)
            await db.commit()

        # クールタイム記録
        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/bump", status_code=302)


@router.post("/bump/reminder/{reminder_id}/toggle", response_model=None)
async def bump_reminder_toggle(
    request: Request,
    reminder_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Toggle a bump reminder enabled state."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/bump", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/bump", status_code=302)

    # 二重ロック: 同じリソースへの同時操作を防止
    async with get_resource_lock(f"bump_reminder:toggle:{reminder_id}"):
        result = await db.execute(
            select(BumpReminder).where(BumpReminder.id == reminder_id)
        )
        reminder = result.scalar_one_or_none()
        if reminder:
            reminder.is_enabled = not reminder.is_enabled
            await db.commit()

        # クールタイム記録
        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/bump", status_code=302)
