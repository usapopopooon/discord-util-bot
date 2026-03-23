"""API v1 authentication routes (JWT-based)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.db_helpers as _db
import src.web.security as _security
from src.constants import SESSION_MAX_AGE_SECONDS
from src.web.jwt_auth import create_jwt_token, get_current_user_jwt

router = APIRouter(prefix="/api/v1/auth", tags=["api-auth"])


class _LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login", response_model=None)
async def api_login(
    body: _LoginRequest,
    request: Request,
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Authenticate via JSON body and set JWT cookie."""
    client_ip = request.client.host if request.client else "unknown"

    email = body.email.strip() if body.email else ""
    password = body.password

    if _security.is_rate_limited(client_ip):
        return JSONResponse(
            {"error": "Too many attempts. Try again later."},
            status_code=429,
        )

    admin = await _db.get_or_create_admin(db)
    if admin is None:
        return JSONResponse(
            {"error": "ADMIN_PASSWORD not configured"},
            status_code=500,
        )

    if admin.email != email or not await _security.verify_password_async(
        password, admin.password_hash
    ):
        _security.record_failed_attempt(client_ip)
        return JSONResponse(
            {"error": "Invalid email or password"},
            status_code=401,
        )

    token = create_jwt_token(email)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key="session",
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=_security.SECURE_COOKIE,
        samesite="strict",
        path="/",
    )
    return response


@router.post("/logout", response_model=None)
async def api_logout() -> JSONResponse:
    """Clear the session cookie."""
    response = JSONResponse({"ok": True})
    response.delete_cookie(key="session", path="/")
    return response


@router.get("/me", response_model=None)
async def api_me(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
) -> JSONResponse:
    """Return current user info if authenticated."""
    if not user or not user.get("sub"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return JSONResponse({"email": user["sub"]})


@router.get("/setup-status", response_model=None)
async def api_setup_status(
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Return setup status flags."""
    admin = await _db.get_or_create_admin(db)

    if admin is None:
        return JSONResponse(
            {
                "needs_setup": True,
                "needs_email_verify": False,
            }
        )

    needs_setup = admin.password_changed_at is None
    needs_email_verify = not needs_setup and not admin.email_verified

    return JSONResponse(
        {
            "needs_setup": needs_setup,
            "needs_email_verify": needs_email_verify,
        }
    )
