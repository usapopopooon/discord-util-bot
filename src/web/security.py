"""Security utilities: password, CSRF, session, rate limiting, form cooldown."""

import asyncio
import logging
import os
import re
import secrets
import time
from typing import Annotated, Any, cast

import bcrypt
from fastapi import Cookie, Request
from fastapi.responses import Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings
from src.constants import (
    BCRYPT_MAX_PASSWORD_BYTES,
    FORM_COOLDOWN_CLEANUP_INTERVAL_SECONDS,
    FORM_SUBMIT_COOLDOWN_SECONDS,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_WINDOW_SECONDS,
    RATE_LIMIT_CLEANUP_INTERVAL_SECONDS,
    SESSION_MAX_AGE_SECONDS,
    TOKEN_BYTE_LENGTH,
)

logger = logging.getLogger(__name__)

# =============================================================================
# セキュリティヘッダーミドルウェア
# =============================================================================

_CSP_HEADER = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
    "img-src 'self' data: https:; "
    "font-src 'self' https:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """レスポンスにセキュリティヘッダーを追加するミドルウェア."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """リクエストを処理し、セキュリティヘッダーを追加."""
        response: Response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = _CSP_HEADER
        if request.url.path not in ["/health", "/favicon.ico"]:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response


# =============================================================================
# モジュールレベル設定
# =============================================================================

_session_secret_from_env = os.environ.get("SESSION_SECRET_KEY", "").strip()
if not _session_secret_from_env:
    logger.warning(
        "SESSION_SECRET_KEY is not set. Using a random key. "
        "Sessions will be invalidated on restart. "
        "Set SESSION_SECRET_KEY environment variable for persistent sessions."
    )
    SECRET_KEY = secrets.token_hex(TOKEN_BYTE_LENGTH)
else:
    SECRET_KEY = _session_secret_from_env

INIT_ADMIN_EMAIL = settings.admin_email.strip()
INIT_ADMIN_PASSWORD = settings.admin_password.strip() if settings.admin_password else ""
SECURE_COOKIE = os.environ.get("SECURE_COOKIE", "false").lower() == "true"

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

serializer = URLSafeTimedSerializer(SECRET_KEY)
csrf_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="csrf-token")
CSRF_TOKEN_MAX_AGE_SECONDS = 86400

# =============================================================================
# CSRF 保護
# =============================================================================


def generate_csrf_token() -> str:
    """CSRF トークンを生成する."""
    return csrf_serializer.dumps(secrets.token_hex(16))


def validate_csrf_token(token: str | None) -> bool:
    """CSRF トークンを検証する."""
    if not token:
        return False
    try:
        csrf_serializer.loads(token, max_age=CSRF_TOKEN_MAX_AGE_SECONDS)
        return True
    except BadSignature:
        return False


# =============================================================================
# パスワードユーティリティ
# =============================================================================


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        logger.warning(
            "Password exceeds %d bytes, truncating",
            BCRYPT_MAX_PASSWORD_BYTES,
        )
        password_bytes = password_bytes[:BCRYPT_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a hash."""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


async def hash_password_async(password: str) -> str:
    """bcrypt をスレッドプールで実行してイベントループをブロックしない。"""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    """bcrypt 検証をスレッドプールで実行してイベントループをブロックしない。"""
    return await asyncio.to_thread(verify_password, password, password_hash)


# =============================================================================
# レート制限
# =============================================================================

LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_last_cleanup_time: float = 0.0


def _cleanup_old_rate_limit_entries() -> None:
    """古いレート制限エントリをクリーンアップする。"""
    global _last_cleanup_time
    now = time.time()
    if (
        _last_cleanup_time > 0
        and now - _last_cleanup_time < RATE_LIMIT_CLEANUP_INTERVAL_SECONDS
    ):
        return
    _last_cleanup_time = now
    for ip in list(LOGIN_ATTEMPTS):
        valid = [t for t in LOGIN_ATTEMPTS[ip] if now - t < LOGIN_WINDOW_SECONDS]
        if valid:
            LOGIN_ATTEMPTS[ip] = valid
        else:
            del LOGIN_ATTEMPTS[ip]


def is_rate_limited(ip: str) -> bool:
    """Check if IP is rate limited."""
    _cleanup_old_rate_limit_entries()
    attempts = LOGIN_ATTEMPTS.get(ip)
    if not attempts:
        return False
    now = time.time()
    valid = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
    if len(valid) != len(attempts):
        if valid:
            LOGIN_ATTEMPTS[ip] = valid
        else:
            del LOGIN_ATTEMPTS[ip]
    return len(valid) >= LOGIN_MAX_ATTEMPTS


def record_failed_attempt(ip: str) -> None:
    """Record a failed login attempt."""
    if not ip:
        return
    now = time.time()
    if ip not in LOGIN_ATTEMPTS:
        LOGIN_ATTEMPTS[ip] = []
    LOGIN_ATTEMPTS[ip].append(now)


# =============================================================================
# フォーム送信クールタイム
# =============================================================================

FORM_SUBMIT_TIMES: dict[str, float] = {}
_form_cooldown_last_cleanup_time: float = 0.0


def _cleanup_form_cooldown_entries() -> None:
    """古いフォームクールタイムエントリをクリーンアップする。"""
    global _form_cooldown_last_cleanup_time
    now = time.time()
    if (
        _form_cooldown_last_cleanup_time > 0
        and now - _form_cooldown_last_cleanup_time
        < FORM_COOLDOWN_CLEANUP_INTERVAL_SECONDS
    ):
        return
    _form_cooldown_last_cleanup_time = now
    threshold = FORM_SUBMIT_COOLDOWN_SECONDS * 5
    for key in list(FORM_SUBMIT_TIMES):
        if now - FORM_SUBMIT_TIMES[key] > threshold:
            del FORM_SUBMIT_TIMES[key]


def is_form_cooldown_active(user_email: str, path: str) -> bool:
    """フォーム送信がクールタイム中かチェックする."""
    _cleanup_form_cooldown_entries()
    key = f"{user_email}:{path}"
    now = time.time()
    last_submit = FORM_SUBMIT_TIMES.get(key)
    if last_submit is None:
        return False
    return now - last_submit < FORM_SUBMIT_COOLDOWN_SECONDS


def record_form_submit(user_email: str, path: str) -> None:
    """フォーム送信を記録する."""
    if not user_email:
        return
    key = f"{user_email}:{path}"
    FORM_SUBMIT_TIMES[key] = time.time()


# =============================================================================
# セッションユーティリティ
# =============================================================================


def create_session_token(email: str) -> str:
    """Create a signed session token."""
    return serializer.dumps({"authenticated": True, "email": email})


def verify_session_token(token: str) -> dict[str, Any] | None:
    """Verify a session token and return data."""
    if not token or not token.strip():
        return None
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        if data.get("authenticated"):
            return cast(dict[str, Any], data)
        return None
    except (BadSignature, TypeError, ValueError):
        return None


def get_current_user(
    session: Annotated[str | None, Cookie(alias="session")] = None,
) -> dict[str, Any] | None:
    """Check if user is authenticated, return session data."""
    if not session:
        return None
    return verify_session_token(session)
