"""Common API routes for shared data (guilds, channels, roles)."""

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.db_helpers as _db
from src.web.jwt_auth import get_current_user_jwt

router = APIRouter(prefix="/api/v1", tags=["common"])


@router.get("/guilds", response_model=None)
async def get_guilds(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """ギルド一覧を返す。"""
    if not user:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    guilds_map, _ = await _db._get_discord_guilds_and_channels(db)
    return JSONResponse(guilds_map)


@router.get("/channels", response_model=None)
async def get_channels(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """チャンネル一覧を返す。"""
    if not user:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    _, channels_map = await _db._get_discord_guilds_and_channels(db)
    channels = {
        gid: [{"id": cid, "name": cname} for cid, cname in clist]
        for gid, clist in channels_map.items()
    }
    return JSONResponse(channels)


@router.get("/roles", response_model=None)
async def get_roles(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """ロール一覧を返す。"""
    if not user:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    roles_map = await _db._get_discord_roles_by_guild(db)
    roles = {
        gid: [
            {"id": rid, "name": rname, "color": rcolor} for rid, rname, rcolor in rlist
        ]
        for gid, rlist in roles_map.items()
    }
    return JSONResponse(roles)
