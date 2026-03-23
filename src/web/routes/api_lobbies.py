"""API v1 lobby routes (JSON)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import src.web.db_helpers as _db
import src.web.security as _security
from src.database.models import Lobby
from src.utils import get_resource_lock
from src.web.jwt_auth import get_current_user_jwt

router = APIRouter(prefix="/api/v1", tags=["api-lobbies"])


@router.get("/lobbies", response_model=None)
async def api_lobbies_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List all lobbies."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(
        select(Lobby).options(selectinload(Lobby.sessions)).order_by(Lobby.id)
    )
    lobbies = list(result.scalars().all())

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)

    return JSONResponse(
        {
            "lobbies": [
                {
                    "id": lobby.id,
                    "guild_id": lobby.guild_id,
                    "lobby_channel_id": lobby.lobby_channel_id,
                    "default_user_limit": lobby.default_user_limit,
                }
                for lobby in lobbies
            ],
            "guilds": guilds_map,
            "channels": {
                gid: [{"id": cid, "name": cname} for cid, cname in clist]
                for gid, clist in channels_map.items()
            },
        }
    )


@router.delete("/lobbies/{lobby_id}", response_model=None)
async def api_lobbies_delete(
    request: Request,
    lobby_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete a lobby."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"lobby:delete:{lobby_id}"):
        result = await db.execute(select(Lobby).where(Lobby.id == lobby_id))
        lobby = result.scalar_one_or_none()
        if not lobby:
            return JSONResponse({"error": "Not found"}, status_code=404)

        await db.delete(lobby)
        await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})
