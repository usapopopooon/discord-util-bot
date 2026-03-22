"""Lobby routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import src.web.app as _app
from src.database.models import Lobby
from src.utils import get_resource_lock
from src.web.templates import lobbies_list_page

router = APIRouter()


@router.get("/lobbies", response_model=None)
async def lobbies_list(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """List all lobbies."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(Lobby).options(selectinload(Lobby.sessions)).order_by(Lobby.id)
    )
    lobbies = list(result.scalars().all())

    # ギルド・チャンネル名のルックアップを取得
    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=lobbies_list_page(
            lobbies,
            csrf_token=_app.generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
        )
    )


@router.post("/lobbies/{lobby_id}/delete", response_model=None)
async def lobbies_delete(
    request: Request,
    lobby_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Delete a lobby."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/lobbies", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/lobbies", status_code=302)

    # 二重ロック: 同じリソースへの同時操作を防止
    async with get_resource_lock(f"lobby:delete:{lobby_id}"):
        result = await db.execute(select(Lobby).where(Lobby.id == lobby_id))
        lobby = result.scalar_one_or_none()
        if lobby:
            await db.delete(lobby)
            await db.commit()

        # クールタイム記録
        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/lobbies", status_code=302)
