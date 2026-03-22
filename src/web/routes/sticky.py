"""Sticky message routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.app as _app
from src.database.models import StickyMessage
from src.utils import get_resource_lock
from src.web.templates import sticky_list_page

router = APIRouter()


@router.get("/sticky", response_model=None)
async def sticky_list(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """List all sticky messages."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(StickyMessage).order_by(StickyMessage.created_at))
    stickies = list(result.scalars().all())

    # ギルド・チャンネル名のルックアップを取得
    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=sticky_list_page(
            stickies,
            csrf_token=_app.generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
        )
    )


@router.post("/sticky/{channel_id}/delete", response_model=None)
async def sticky_delete(
    request: Request,
    channel_id: str,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Delete a sticky message."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/sticky", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/sticky", status_code=302)

    # 二重ロック: 同じリソースへの同時操作を防止
    async with get_resource_lock(f"sticky:delete:{channel_id}"):
        result = await db.execute(
            select(StickyMessage).where(StickyMessage.channel_id == channel_id)
        )
        sticky = result.scalar_one_or_none()
        if sticky:
            await db.delete(sticky)
            await db.commit()

        # クールタイム記録
        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/sticky", status_code=302)
