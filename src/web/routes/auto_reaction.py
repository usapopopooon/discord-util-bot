"""Auto Reaction routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.app as _app
from src.database.models import AutoReactionConfig
from src.services.auto_reaction_service import (
    MAX_AUTO_REACTION_EMOJIS,
    encode_auto_reaction_emojis,
    normalize_auto_reaction_emojis,
)
from src.utils import get_resource_lock
from src.web.templates import auto_reaction_page

router = APIRouter()


@router.get("/auto-reaction", response_model=None)
async def auto_reaction_list(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoReaction 設定一覧ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(AutoReactionConfig).order_by(AutoReactionConfig.id)
    )
    configs = list(result.scalars().all())

    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=auto_reaction_page(
            configs,
            csrf_token=_app.generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
        )
    )


@router.post("/auto-reaction/new", response_model=None)
async def auto_reaction_create(
    request: Request,
    guild_id: Annotated[str, Form()],
    channel_id: Annotated[str, Form()],
    emojis: Annotated[str, Form()],
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoReaction 設定を作成する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/auto-reaction", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/auto-reaction", status_code=302)

    if not guild_id or not channel_id:
        return RedirectResponse(url="/auto-reaction", status_code=302)

    emoji_list = normalize_auto_reaction_emojis(emojis.split())
    if not emoji_list or len(emoji_list) > MAX_AUTO_REACTION_EMOJIS:
        return RedirectResponse(url="/auto-reaction", status_code=302)

    async with get_resource_lock(f"auto_reaction:create:{guild_id}:{channel_id}"):
        config = AutoReactionConfig(
            guild_id=guild_id,
            channel_id=channel_id,
            emojis=encode_auto_reaction_emojis(emoji_list),
        )
        db.add(config)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/auto-reaction", status_code=302)


@router.post("/auto-reaction/{config_id}/delete", response_model=None)
async def auto_reaction_delete(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoReaction 設定を削除する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/auto-reaction", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/auto-reaction", status_code=302)

    async with get_resource_lock(f"auto_reaction:delete:{config_id}"):
        result = await db.execute(
            select(AutoReactionConfig).where(AutoReactionConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config:
            await db.delete(config)
            await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/auto-reaction", status_code=302)


@router.post("/auto-reaction/{config_id}/toggle", response_model=None)
async def auto_reaction_toggle(
    request: Request,
    config_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoReaction 設定の有効/無効を切り替える。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/auto-reaction", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/auto-reaction", status_code=302)

    async with get_resource_lock(f"auto_reaction:toggle:{config_id}"):
        result = await db.execute(
            select(AutoReactionConfig).where(AutoReactionConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config:
            config.enabled = not config.enabled
            await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/auto-reaction", status_code=302)
