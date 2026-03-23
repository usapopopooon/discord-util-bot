"""JWT authentication utilities for API endpoints."""

from __future__ import annotations

import time
from typing import Annotated, Any

import jwt
from fastapi import Cookie

from src.constants import SESSION_MAX_AGE_SECONDS
from src.web.security import SECRET_KEY

_ALGORITHM = "HS256"


def create_jwt_token(email: str) -> str:
    """Create a JWT token with the given email as subject."""
    now = int(time.time())
    payload = {
        "sub": email,
        "iat": now,
        "exp": now + SESSION_MAX_AGE_SECONDS,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=_ALGORITHM)


def verify_jwt_token(token: str) -> dict[str, Any] | None:
    """Verify and decode a JWT token. Returns payload or None on any error."""
    if not token or not token.strip():
        return None
    try:
        payload: dict[str, Any] = jwt.decode(token, SECRET_KEY, algorithms=[_ALGORITHM])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception):
        return None


def get_current_user_jwt(
    session: Annotated[str | None, Cookie(alias="session")] = None,
) -> dict[str, Any] | None:
    """FastAPI dependency: extract JWT payload from session cookie."""
    if not session:
        return None
    return verify_jwt_token(session)
