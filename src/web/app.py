"""FastAPI web admin application."""

import logging
import os
import re
import secrets
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

import bcrypt
from fastapi import Cookie, Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings
from src.constants import (
    BCRYPT_MAX_PASSWORD_BYTES,
    EMAIL_CHANGE_TOKEN_EXPIRY_SECONDS,
    FORM_COOLDOWN_CLEANUP_INTERVAL_SECONDS,
    FORM_SUBMIT_COOLDOWN_SECONDS,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_WINDOW_SECONDS,
    PASSWORD_MIN_LENGTH,
    RATE_LIMIT_CLEANUP_INTERVAL_SECONDS,
    # RESET_TOKEN_EXPIRY_SECONDS,  # SMTP 未設定のため未使用
    SESSION_MAX_AGE_SECONDS,
    TOKEN_BYTE_LENGTH,
)
from src.database.engine import async_session, check_database_connection
from src.database.models import (
    AdminUser,
    BumpConfig,
    BumpReminder,
    DiscordChannel,
    DiscordGuild,
    DiscordRole,
    Lobby,
    RolePanel,
    RolePanelItem,
    StickyMessage,
)
from src.utils import get_resource_lock, is_valid_emoji, normalize_emoji
from src.web.discord_api import (
    add_reactions_to_message,
    edit_role_panel_in_discord,
    post_role_panel_to_discord,
)
from src.web.email_service import (
    send_email_change_verification,  # noqa: F401  # SMTP 設定時に使用
    # send_password_reset_email,  # SMTP 未設定のため未使用
)
from src.web.templates import (
    bump_list_page,
    dashboard_page,
    email_change_page,
    email_verification_pending_page,
    forgot_password_page,
    initial_setup_page,
    lobbies_list_page,
    login_page,
    maintenance_page,
    password_change_page,
    reset_password_page,
    role_panel_create_page,
    role_panel_detail_page,
    role_panels_list_page,
    settings_page,
    sticky_list_page,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan handler for startup/shutdown events."""
    # Startup: データベース接続をチェック
    logger.info("Starting web admin application...")
    if not await check_database_connection():
        logger.error(
            "Database connection failed. "
            "Check DATABASE_URL and ensure the database is running."
        )
        # Web アプリはデータベースがなくても起動を許可する (ヘルスチェック用)
        # ただし、機能は制限される
    else:
        logger.info("Database connection successful")
    yield
    # シャットダウン
    logger.info("Shutting down web admin application...")


app = FastAPI(title="Bot Admin", docs_url=None, redoc_url=None, lifespan=lifespan)


# =============================================================================
# セキュリティヘッダーミドルウェア
# =============================================================================


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """レスポンスにセキュリティヘッダーを追加するミドルウェア."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """リクエストを処理し、セキュリティヘッダーを追加."""
        response: Response = await call_next(request)

        # クリックジャッキング防止
        response.headers["X-Frame-Options"] = "DENY"

        # MIME スニッフィング防止
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS 防止 (レガシーブラウザ向け)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # リファラーポリシー
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy
        # Tailwind CSS CDN と inline styles/scripts を許可
        response.headers["Content-Security-Policy"] = (
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

        # キャッシュ制御 (機密データを含むページ)
        if request.url.path not in ["/health", "/favicon.ico"]:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"

        return response


app.add_middleware(SecurityHeadersMiddleware)


# セッション設定
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

# config.py の設定を使用して一貫性を保つ
# 空白のみのパスワードは空として扱う
INIT_ADMIN_EMAIL = settings.admin_email.strip()
INIT_ADMIN_PASSWORD = settings.admin_password.strip() if settings.admin_password else ""
SECURE_COOKIE = os.environ.get("SECURE_COOKIE", "false").lower() == "true"

# レート制限 (インメモリ、再起動時にリセット)
LOGIN_ATTEMPTS: dict[str, list[float]] = {}

# フォーム送信クールタイム (インメモリ、再起動時にリセット)
# key: "user_email:path", value: 最終送信時刻
FORM_SUBMIT_TIMES: dict[str, float] = {}
_form_cooldown_last_cleanup_time: float = 0.0

# メールアドレス検証パターン
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


serializer = URLSafeTimedSerializer(SECRET_KEY)

# CSRF トークン用シリアライザ (セッションとは別のソルトを使用)
csrf_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="csrf-token")

# CSRF トークンの有効期限 (24時間)
CSRF_TOKEN_MAX_AGE_SECONDS = 86400


# =============================================================================
# CSRF 保護
# =============================================================================


def generate_csrf_token() -> str:
    """CSRF トークンを生成する."""
    return csrf_serializer.dumps(secrets.token_hex(16))


def validate_csrf_token(token: str | None) -> bool:
    """CSRF トークンを検証する.

    Args:
        token: 検証するトークン

    Returns:
        トークンが有効な場合 True
    """
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
    """Hash a password using bcrypt.

    Note: bcrypt 4.x は72バイトを超えるパスワードで ValueError を発生させる。
    入力検証で長いパスワードを事前に拒否することを推奨。
    """
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        # bcrypt 4.x は72バイトを超えるパスワードでエラーを発生させる
        # 手動で切り詰めてハッシュ化 (セキュリティ上の考慮が必要)
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
        # 無効なハッシュ形式の場合
        return False


# =============================================================================
# データベースユーティリティ
# =============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Database session dependency."""
    async with async_session() as session:
        yield session


async def get_or_create_admin(db: AsyncSession) -> AdminUser | None:
    """Get admin user, create from env vars if not exists."""
    result = await db.execute(select(AdminUser).limit(1))
    admin = result.scalar_one_or_none()

    if admin is None and INIT_ADMIN_PASSWORD:
        # 環境変数から初期管理者を作成（認証済みとして設定）
        admin = AdminUser(
            email=INIT_ADMIN_EMAIL,
            password_hash=hash_password(INIT_ADMIN_PASSWORD),
            email_verified=True,
            password_changed_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

    return admin


# =============================================================================
# レート制限
# =============================================================================

# メモリリーク防止: 古いエントリを定期的にクリーンアップ
_last_cleanup_time: float = 0.0


def _cleanup_old_rate_limit_entries() -> None:
    """古いレート制限エントリをクリーンアップする。"""
    global _last_cleanup_time
    now = time.time()

    if now - _last_cleanup_time < RATE_LIMIT_CLEANUP_INTERVAL_SECONDS:
        return

    _last_cleanup_time = now
    # 期限切れのIPアドレスを削除
    ips_to_remove = []
    for ip, attempts in LOGIN_ATTEMPTS.items():
        valid_attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
        if not valid_attempts:
            ips_to_remove.append(ip)
        else:
            LOGIN_ATTEMPTS[ip] = valid_attempts

    for ip in ips_to_remove:
        del LOGIN_ATTEMPTS[ip]


def is_rate_limited(ip: str) -> bool:
    """Check if IP is rate limited."""
    _cleanup_old_rate_limit_entries()

    now = time.time()
    attempts = LOGIN_ATTEMPTS.get(ip, [])
    attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
    LOGIN_ATTEMPTS[ip] = attempts
    return len(attempts) >= LOGIN_MAX_ATTEMPTS


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


def _cleanup_form_cooldown_entries() -> None:
    """古いフォームクールタイムエントリをクリーンアップする。"""
    global _form_cooldown_last_cleanup_time
    now = time.time()

    if now - _form_cooldown_last_cleanup_time < FORM_COOLDOWN_CLEANUP_INTERVAL_SECONDS:
        return

    _form_cooldown_last_cleanup_time = now

    # 古いエントリを削除 (クールタイムの5倍以上経過したもの)
    threshold = FORM_SUBMIT_COOLDOWN_SECONDS * 5
    keys_to_remove = [
        key
        for key, submit_time in FORM_SUBMIT_TIMES.items()
        if now - submit_time > threshold
    ]
    for key in keys_to_remove:
        del FORM_SUBMIT_TIMES[key]


def is_form_cooldown_active(user_email: str, path: str) -> bool:
    """フォーム送信がクールタイム中かチェックする.

    Args:
        user_email: ユーザーのメールアドレス
        path: リクエストパス

    Returns:
        クールタイム中の場合 True
    """
    _cleanup_form_cooldown_entries()

    key = f"{user_email}:{path}"
    now = time.time()

    last_submit = FORM_SUBMIT_TIMES.get(key)
    if last_submit is None:
        return False

    return now - last_submit < FORM_SUBMIT_COOLDOWN_SECONDS


def record_form_submit(user_email: str, path: str) -> None:
    """フォーム送信を記録する.

    Args:
        user_email: ユーザーのメールアドレス
        path: リクエストパス
    """
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
        # BadSignature: 無効な署名またはトークンの改ざん
        # TypeError: トークンのデシリアライズ失敗
        # ValueError: 不正なトークン形式
        return None


def get_current_user(
    session: Annotated[str | None, Cookie(alias="session")] = None,
) -> dict[str, Any] | None:
    """Check if user is authenticated, return session data."""
    if not session:
        return None
    return verify_session_token(session)


# =============================================================================
# 認証ルート
# =============================================================================


@app.get("/health", response_model=None)
async def health_check() -> Response:
    """Health check endpoint for Docker/load balancer health checks.

    Returns 200 if the application is running and can connect to the database.
    Returns 503 if the database connection fails.
    """
    if await check_database_connection():
        return Response(content="ok", media_type="text/plain", status_code=200)
    return Response(
        content="database unavailable", media_type="text/plain", status_code=503
    )


@app.get("/", response_model=None)
async def index(
    user: dict[str, Any] | None = Depends(get_current_user),
) -> Response:
    """Redirect to dashboard or login."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_model=None)
async def login_get(
    user: dict[str, Any] | None = Depends(get_current_user),
) -> Response:
    """Show login page."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return HTMLResponse(content=login_page(csrf_token=generate_csrf_token()))


@app.post("/login", response_model=None)
async def login_post(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Process login form."""
    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=login_page(
                error="Invalid security token. Please try again.",
                csrf_token=generate_csrf_token(),
            ),
            status_code=403,
        )

    client_ip = request.client.host if request.client else "unknown"

    # メールアドレスは前後の空白をトリムする (パスワードはトリムしない)
    email = email.strip() if email else ""

    if is_rate_limited(client_ip):
        return HTMLResponse(
            content=login_page(
                error="Too many attempts. Try again later.",
                csrf_token=generate_csrf_token(),
            ),
            status_code=429,
        )

    # 管理者ユーザーを取得または作成
    admin = await get_or_create_admin(db)
    if admin is None:
        return HTMLResponse(
            content=login_page(
                error="ADMIN_PASSWORD not configured",
                csrf_token=generate_csrf_token(),
            ),
            status_code=500,
        )

    # 認証情報を検証 (メールアドレスは大文字小文字を区別)
    if admin.email != email or not verify_password(password, admin.password_hash):
        record_failed_attempt(client_ip)
        return HTMLResponse(
            content=login_page(
                error="Invalid email or password",
                csrf_token=generate_csrf_token(),
            ),
            status_code=401,
        )

    # セットアップ状況に応じてリダイレクト先を決定
    if admin.password_changed_at is None:
        # 初期セットアップが必要 (メールアドレス + パスワード)
        redirect_url = "/initial-setup"
    elif not admin.email_verified:
        # メールアドレス認証が必要
        redirect_url = "/verify-email"
    else:
        redirect_url = "/dashboard"

    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(
        key="session",
        value=create_session_token(email),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=SECURE_COOKIE,
        samesite="lax",
    )
    return response


@app.get("/logout")
async def logout() -> RedirectResponse:
    """Logout and clear session."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="session")
    return response


# =============================================================================
# 初期セットアップルート
# =============================================================================


@app.get("/initial-setup", response_model=None)
async def initial_setup_get(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show initial setup page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # セットアップ済み
    if admin.password_changed_at is not None:
        if not admin.email_verified:
            return RedirectResponse(url="/verify-email", status_code=302)
        return RedirectResponse(url="/dashboard", status_code=302)

    return HTMLResponse(
        content=initial_setup_page(
            current_email=admin.email, csrf_token=generate_csrf_token()
        )
    )


@app.post("/initial-setup", response_model=None)
async def initial_setup_post(
    user: dict[str, Any] | None = Depends(get_current_user),
    new_email: Annotated[str, Form()] = "",
    new_password: Annotated[str, Form()] = "",
    confirm_password: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Process initial setup form."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Invalid security token. Please try again.",
                csrf_token=generate_csrf_token(),
            ),
            status_code=403,
        )

    # 入力値のトリム (パスワードはトリムしない)
    new_email = new_email.strip() if new_email else ""

    # メールアドレスのバリデーション
    if not new_email:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Email address is required",
                csrf_token=generate_csrf_token(),
            )
        )

    if not EMAIL_PATTERN.match(new_email):
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Invalid email format",
                csrf_token=generate_csrf_token(),
            )
        )

    # パスワードのバリデーション
    if not new_password:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Password is required",
                csrf_token=generate_csrf_token(),
            )
        )

    if new_password != confirm_password:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Passwords do not match",
                csrf_token=generate_csrf_token(),
            )
        )

    if len(new_password) < PASSWORD_MIN_LENGTH:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error=f"Password must be at least {PASSWORD_MIN_LENGTH} characters",
                csrf_token=generate_csrf_token(),
            )
        )

    # bcrypt の制限を超えるパスワードは警告を表示
    if len(new_password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error=f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes",
                csrf_token=generate_csrf_token(),
            )
        )

    # パスワードを更新
    admin.password_hash = hash_password(new_password)
    admin.password_changed_at = datetime.now(UTC)

    # メールアドレスを直接更新（SMTP 未設定のため認証スキップ）
    admin.email = new_email
    admin.email_verified = True
    admin.pending_email = None
    admin.email_change_token = None
    admin.email_change_token_expires_at = None

    # # 保留中のメールアドレスを設定し、認証トークンを生成
    # token = secrets.token_urlsafe(TOKEN_BYTE_LENGTH)
    # admin.pending_email = new_email
    # admin.email_change_token = token
    # admin.email_change_token_expires_at = datetime.now(UTC) + timedelta(
    #     seconds=EMAIL_CHANGE_TOKEN_EXPIRY_SECONDS
    # )

    await db.commit()

    # # 認証メールを送信
    # email_sent = send_email_change_verification(new_email, token)
    #
    # # メール送信失敗時は警告付きで認証待ちページにリダイレクト
    # if not email_sent:
    #     return HTMLResponse(
    #         content=email_verification_pending_page(
    #             pending_email=new_email,
    #             error="Failed to send verification email. Check SMTP configuration.",
    #         )
    #     )
    #
    # return RedirectResponse(url="/verify-email", status_code=302)

    # セッションを更新してダッシュボードにリダイレクト
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="session",
        value=create_session_token(new_email),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=SECURE_COOKIE,
        samesite="lax",
    )
    return response


@app.get("/verify-email", response_model=None)
async def verify_email_get(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show email verification pending page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # 認証済み
    if admin.email_verified:
        return RedirectResponse(url="/dashboard", status_code=302)

    # 保留中のメールがない (通常は発生しないが、念のため処理)
    if not admin.pending_email:
        return RedirectResponse(url="/dashboard", status_code=302)

    return HTMLResponse(
        content=email_verification_pending_page(
            pending_email=admin.pending_email, csrf_token=generate_csrf_token()
        )
    )


@app.post("/resend-verification", response_model=None)
async def resend_verification(
    user: dict[str, Any] | None = Depends(get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Resend verification email."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=email_verification_pending_page(
                pending_email=admin.pending_email or "",
                error="Invalid security token. Please try again.",
                csrf_token=generate_csrf_token(),
            ),
            status_code=403,
        )

    if not admin.pending_email:
        return RedirectResponse(url="/dashboard", status_code=302)

    # 新しいトークンを生成
    token = secrets.token_urlsafe(TOKEN_BYTE_LENGTH)
    admin.email_change_token = token
    admin.email_change_token_expires_at = datetime.now(UTC) + timedelta(
        seconds=EMAIL_CHANGE_TOKEN_EXPIRY_SECONDS
    )
    await db.commit()

    # 認証メールを送信
    email_sent = send_email_change_verification(admin.pending_email, token)

    if email_sent:
        return HTMLResponse(
            content=email_verification_pending_page(
                pending_email=admin.pending_email,
                success="Verification email sent.",
                csrf_token=generate_csrf_token(),
            )
        )
    else:
        return HTMLResponse(
            content=email_verification_pending_page(
                pending_email=admin.pending_email,
                error="Failed to send verification email. Check SMTP configuration.",
                csrf_token=generate_csrf_token(),
            )
        )


# =============================================================================
# パスワードリセットルート
# =============================================================================


@app.get("/forgot-password", response_model=None)
async def forgot_password_get() -> Response:
    """Show forgot password page."""
    return HTMLResponse(content=forgot_password_page(csrf_token=generate_csrf_token()))


@app.post("/forgot-password", response_model=None)
async def forgot_password_post(
    email: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Process forgot password form."""
    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=forgot_password_page(
                error="Invalid security token. Please try again.",
                csrf_token=generate_csrf_token(),
            ),
            status_code=403,
        )

    # 入力値のトリム
    email = email.strip() if email else ""

    # # メールアドレスの存在を推測されないよう、常に成功メッセージを表示
    # success_message = (
    #     "If an account exists with that email, a reset link has been sent."
    # )
    #
    # # メールアドレスで管理者を検索
    # result = await db.execute(select(AdminUser).where(AdminUser.email == email))
    # admin = result.scalar_one_or_none()
    #
    # if admin:
    #     # リセットトークンを生成
    #     token = secrets.token_urlsafe(TOKEN_BYTE_LENGTH)
    #     admin.reset_token = token
    #     admin.reset_token_expires_at = datetime.now(UTC) + timedelta(
    #         seconds=RESET_TOKEN_EXPIRY_SECONDS
    #     )
    #     await db.commit()
    #
    #     # メールを送信
    #     send_password_reset_email(admin.email, token)
    #
    # return HTMLResponse(content=forgot_password_page(success=success_message))

    # SMTP 未設定のエラーメッセージを表示
    _ = email, db  # unused variable warning 回避
    return HTMLResponse(
        content=forgot_password_page(
            error="Password reset is not available. SMTP is not configured.",
            csrf_token=generate_csrf_token(),
        )
    )


@app.get("/reset-password", response_model=None)
async def reset_password_get(
    token: str = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show reset password page."""
    # トークンのトリム
    token = token.strip() if token else ""

    if not token:
        return HTMLResponse(
            content=forgot_password_page(error="Invalid or missing reset token.")
        )

    # トークンが存在し、有効期限内であることを確認
    result = await db.execute(select(AdminUser).where(AdminUser.reset_token == token))
    admin = result.scalar_one_or_none()

    if not admin or not admin.reset_token_expires_at:
        return HTMLResponse(
            content=forgot_password_page(error="Invalid or expired reset token.")
        )

    if admin.reset_token_expires_at < datetime.now(UTC):
        return HTMLResponse(
            content=forgot_password_page(error="Reset token has expired.")
        )

    return HTMLResponse(
        content=reset_password_page(token=token, csrf_token=generate_csrf_token())
    )


@app.post("/reset-password", response_model=None)
async def reset_password_post(
    token: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Process reset password form."""
    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=reset_password_page(
                token=token,
                error="Invalid security token. Please try again.",
                csrf_token=generate_csrf_token(),
            ),
            status_code=403,
        )

    # パスワードの一致を検証
    if new_password != confirm_password:
        return HTMLResponse(
            content=reset_password_page(
                token=token,
                error="Passwords do not match",
                csrf_token=generate_csrf_token(),
            )
        )

    # パスワードの長さを検証
    if len(new_password) < PASSWORD_MIN_LENGTH:
        return HTMLResponse(
            content=reset_password_page(
                token=token,
                error=f"Password must be at least {PASSWORD_MIN_LENGTH} characters",
                csrf_token=generate_csrf_token(),
            )
        )

    # bcrypt の制限を超えるパスワードは拒否
    if len(new_password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        error_msg = f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes"
        return HTMLResponse(
            content=reset_password_page(
                token=token, error=error_msg, csrf_token=generate_csrf_token()
            )
        )

    # トークンで管理者を検索
    result = await db.execute(select(AdminUser).where(AdminUser.reset_token == token))
    admin = result.scalar_one_or_none()

    if not admin or not admin.reset_token_expires_at:
        return HTMLResponse(
            content=forgot_password_page(error="Invalid or expired reset token.")
        )

    if admin.reset_token_expires_at < datetime.now(UTC):
        return HTMLResponse(
            content=forgot_password_page(error="Reset token has expired.")
        )

    # パスワードを更新し、リセットトークンをクリア
    admin.password_hash = hash_password(new_password)
    admin.password_changed_at = datetime.now(UTC)
    admin.reset_token = None
    admin.reset_token_expires_at = None
    await db.commit()

    return HTMLResponse(
        content=login_page(error=None),
    )


@app.get("/dashboard", response_model=None)
async def dashboard(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show dashboard."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin:
        # パスワードが一度も変更されていない場合は初期セットアップにリダイレクト
        if admin.password_changed_at is None:
            return RedirectResponse(url="/initial-setup", status_code=302)
        # メールアドレス未認証の場合は認証ページにリダイレクト
        if not admin.email_verified:
            return RedirectResponse(url="/verify-email", status_code=302)

    return HTMLResponse(content=dashboard_page(email=user.get("email", "Admin")))


# =============================================================================
# 設定ルート
# =============================================================================


@app.get("/settings", response_model=None)
async def settings_get(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show settings hub page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # パスワードが一度も変更されていない場合は初期セットアップにリダイレクト
    if admin.password_changed_at is None:
        return RedirectResponse(url="/initial-setup", status_code=302)

    # メールアドレス未認証の場合は認証ページにリダイレクト
    if not admin.email_verified:
        return RedirectResponse(url="/verify-email", status_code=302)

    return HTMLResponse(
        content=settings_page(
            current_email=admin.email,
            pending_email=admin.pending_email,
        )
    )


@app.get("/settings/email", response_model=None)
async def settings_email_get(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show email change page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # 初期セットアップが先に必要
    if admin.password_changed_at is None:
        return RedirectResponse(url="/initial-setup", status_code=302)

    # メールアドレス認証が先に必要
    if not admin.email_verified:
        return RedirectResponse(url="/verify-email", status_code=302)

    return HTMLResponse(
        content=email_change_page(
            current_email=admin.email,
            pending_email=admin.pending_email,
            csrf_token=generate_csrf_token(),
        )
    )


@app.post("/settings/email", response_model=None)
async def settings_email_post(
    user: dict[str, Any] | None = Depends(get_current_user),
    new_email: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Update email address."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=email_change_page(
                current_email=admin.email,
                pending_email=admin.pending_email,
                error="Invalid security token. Please try again.",
                csrf_token=generate_csrf_token(),
            ),
            status_code=403,
        )

    # 入力値のトリム
    new_email = new_email.strip() if new_email else ""

    # バリデーション
    if not new_email:
        return HTMLResponse(
            content=email_change_page(
                current_email=admin.email,
                pending_email=admin.pending_email,
                error="Email address is required",
                csrf_token=generate_csrf_token(),
            )
        )

    if not EMAIL_PATTERN.match(new_email):
        return HTMLResponse(
            content=email_change_page(
                current_email=admin.email,
                pending_email=admin.pending_email,
                error="Invalid email format",
                csrf_token=generate_csrf_token(),
            )
        )

    if new_email == admin.email:
        return HTMLResponse(
            content=email_change_page(
                current_email=admin.email,
                pending_email=admin.pending_email,
                error="New email must be different from current email",
                csrf_token=generate_csrf_token(),
            )
        )

    # メールアドレスを直接更新（SMTP 未設定のため認証スキップ）
    admin.email = new_email
    admin.pending_email = None
    admin.email_change_token = None
    admin.email_change_token_expires_at = None

    # # 認証トークンを生成し、保留中のメールアドレスを保存
    # token = secrets.token_urlsafe(TOKEN_BYTE_LENGTH)
    # admin.pending_email = new_email
    # admin.email_change_token = token
    # admin.email_change_token_expires_at = datetime.now(UTC) + timedelta(
    #     seconds=EMAIL_CHANGE_TOKEN_EXPIRY_SECONDS
    # )

    await db.commit()

    # # 新しいメールアドレスに認証メールを送信
    # email_sent = send_email_change_verification(new_email, token)
    #
    # if email_sent:
    #     return HTMLResponse(
    #         content=email_change_page(
    #             current_email=admin.email,
    #             pending_email=admin.pending_email,
    #             success="Verification email sent. Please check your inbox.",
    #         )
    #     )
    # else:
    #     return HTMLResponse(
    #         content=email_change_page(
    #             current_email=admin.email,
    #             pending_email=admin.pending_email,
    #             error="Failed to send verification email. Check SMTP configuration.",
    #         )
    #     )

    # セッションを更新してリダイレクト
    response = RedirectResponse(url="/settings", status_code=302)
    response.set_cookie(
        key="session",
        value=create_session_token(new_email),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=SECURE_COOKIE,
        samesite="lax",
    )
    return response


@app.get("/settings/password", response_model=None)
async def settings_password_get(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show password change page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # 初期セットアップが先に必要
    if admin.password_changed_at is None:
        return RedirectResponse(url="/initial-setup", status_code=302)

    # メールアドレス認証が先に必要
    if not admin.email_verified:
        return RedirectResponse(url="/verify-email", status_code=302)

    return HTMLResponse(content=password_change_page(csrf_token=generate_csrf_token()))


@app.post("/settings/password", response_model=None)
async def settings_password_post(
    user: dict[str, Any] | None = Depends(get_current_user),
    new_password: Annotated[str, Form()] = "",
    confirm_password: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Update password."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # 初期セットアップが先に必要
    if admin.password_changed_at is None:
        return RedirectResponse(url="/initial-setup", status_code=302)

    # メールアドレス認証が先に必要
    if not admin.email_verified:
        return RedirectResponse(url="/verify-email", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=password_change_page(
                error="Invalid security token. Please try again.",
                csrf_token=generate_csrf_token(),
            ),
            status_code=403,
        )

    # バリデーション
    if not new_password:
        return HTMLResponse(
            content=password_change_page(
                error="Password is required", csrf_token=generate_csrf_token()
            )
        )

    if new_password != confirm_password:
        return HTMLResponse(
            content=password_change_page(
                error="Passwords do not match", csrf_token=generate_csrf_token()
            )
        )

    if len(new_password) < PASSWORD_MIN_LENGTH:
        return HTMLResponse(
            content=password_change_page(
                error=f"Password must be at least {PASSWORD_MIN_LENGTH} characters",
                csrf_token=generate_csrf_token(),
            )
        )

    # bcrypt の制限を超えるパスワードは拒否
    if len(new_password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        return HTMLResponse(
            content=password_change_page(
                error=f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes",
                csrf_token=generate_csrf_token(),
            )
        )

    # パスワードを更新
    admin.password_hash = hash_password(new_password)
    admin.password_changed_at = datetime.now(UTC)
    await db.commit()

    # パスワード変更後はログアウト
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="session")
    return response


# =============================================================================
# メンテナンスルート
# =============================================================================


@app.get("/settings/maintenance", response_model=None)
async def settings_maintenance(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Database maintenance page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # メールアドレス未認証の場合は認証ページにリダイレクト
    result = await db.execute(select(AdminUser).where(AdminUser.email == user["email"]))
    admin = result.scalar_one_or_none()
    if admin and not admin.email_verified:
        return RedirectResponse(url="/verify-email", status_code=302)

    # Get success message from query params
    success = request.query_params.get("success")

    # Get active guild IDs from the DiscordGuild cache table
    guild_result = await db.execute(select(DiscordGuild.guild_id))
    active_guild_ids = {row[0] for row in guild_result.fetchall()}

    # Get all lobbies and count orphaned
    lobby_result = await db.execute(select(Lobby))
    lobbies = list(lobby_result.scalars().all())
    lobby_orphaned = sum(
        1 for lobby in lobbies if lobby.guild_id not in active_guild_ids
    )

    # Get all bump configs and count orphaned
    bump_result = await db.execute(select(BumpConfig))
    bump_configs = list(bump_result.scalars().all())
    bump_orphaned = sum(1 for c in bump_configs if c.guild_id not in active_guild_ids)

    # Get all stickies and count orphaned
    sticky_result = await db.execute(select(StickyMessage))
    stickies = list(sticky_result.scalars().all())
    sticky_orphaned = sum(1 for s in stickies if s.guild_id not in active_guild_ids)

    # Get all role panels and count orphaned
    panel_result = await db.execute(select(RolePanel))
    panels = list(panel_result.scalars().all())
    panel_orphaned = sum(1 for p in panels if p.guild_id not in active_guild_ids)

    return HTMLResponse(
        content=maintenance_page(
            lobby_total=len(lobbies),
            lobby_orphaned=lobby_orphaned,
            bump_total=len(bump_configs),
            bump_orphaned=bump_orphaned,
            sticky_total=len(stickies),
            sticky_orphaned=sticky_orphaned,
            panel_total=len(panels),
            panel_orphaned=panel_orphaned,
            guild_count=len(active_guild_ids),
            success=success,
            csrf_token=generate_csrf_token(),
        )
    )


@app.post("/settings/maintenance/refresh", response_model=None)
async def settings_maintenance_refresh(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user),
    csrf_token: Annotated[str, Form()] = "",
) -> Response:
    """Refresh maintenance page statistics."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF token validation
    if not validate_csrf_token(csrf_token):
        return RedirectResponse(url="/settings/maintenance", status_code=302)

    # Rate limit check
    path = str(request.url.path)
    user_email = user.get("email", "")
    if is_form_cooldown_active(user_email, path):
        return RedirectResponse(
            url="/settings/maintenance?success=Please+wait+before+refreshing",
            status_code=302,
        )

    # Record form submit for rate limiting
    record_form_submit(user_email, path)

    return RedirectResponse(
        url="/settings/maintenance?success=Stats+refreshed",
        status_code=302,
    )


@app.post("/settings/maintenance/cleanup", response_model=None)
async def settings_maintenance_cleanup(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Cleanup orphaned database records."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF token validation
    if not validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=maintenance_page(
                lobby_total=0,
                lobby_orphaned=0,
                bump_total=0,
                bump_orphaned=0,
                sticky_total=0,
                sticky_orphaned=0,
                panel_total=0,
                panel_orphaned=0,
                guild_count=0,
                csrf_token=generate_csrf_token(),
            ),
            status_code=400,
        )

    # Rate limit check
    path = str(request.url.path)
    user_email = user.get("email", "")
    if is_form_cooldown_active(user_email, path):
        return RedirectResponse(
            url="/settings/maintenance?success=Please+wait+before+trying+again",
            status_code=302,
        )

    # Get active guild IDs from the DiscordGuild cache table
    guild_result = await db.execute(select(DiscordGuild.guild_id))
    active_guild_ids = {row[0] for row in guild_result.fetchall()}

    deleted_counts: list[str] = []

    # Delete orphaned lobbies
    lobby_result = await db.execute(select(Lobby))
    lobbies = list(lobby_result.scalars().all())
    lobby_deleted = 0
    for lobby in lobbies:
        if lobby.guild_id not in active_guild_ids:
            await db.delete(lobby)
            lobby_deleted += 1
    if lobby_deleted > 0:
        deleted_counts.append(f"{lobby_deleted} lobbies")

    # Delete orphaned bump configs and their reminders
    bump_result = await db.execute(select(BumpConfig))
    bump_configs = list(bump_result.scalars().all())
    bump_deleted = 0
    for config in bump_configs:
        if config.guild_id not in active_guild_ids:
            # Also delete associated reminders
            reminder_result = await db.execute(
                select(BumpReminder).where(BumpReminder.guild_id == config.guild_id)
            )
            for reminder in reminder_result.scalars().all():
                await db.delete(reminder)
            await db.delete(config)
            bump_deleted += 1
    if bump_deleted > 0:
        deleted_counts.append(f"{bump_deleted} bump configs")

    # Delete orphaned stickies
    sticky_result = await db.execute(select(StickyMessage))
    stickies = list(sticky_result.scalars().all())
    sticky_deleted = 0
    for sticky in stickies:
        if sticky.guild_id not in active_guild_ids:
            await db.delete(sticky)
            sticky_deleted += 1
    if sticky_deleted > 0:
        deleted_counts.append(f"{sticky_deleted} stickies")

    # Delete orphaned role panels
    panel_result = await db.execute(select(RolePanel))
    panels = list(panel_result.scalars().all())
    panel_deleted = 0
    for panel in panels:
        if panel.guild_id not in active_guild_ids:
            await db.delete(panel)
            panel_deleted += 1
    if panel_deleted > 0:
        deleted_counts.append(f"{panel_deleted} role panels")

    await db.commit()

    # Record form submit for rate limiting
    record_form_submit(user_email, path)

    if deleted_counts:
        success_msg = "Cleaned up: " + ", ".join(deleted_counts)
    else:
        success_msg = "No orphaned data found"

    return RedirectResponse(
        url=f"/settings/maintenance?success={success_msg.replace(' ', '+')}",
        status_code=302,
    )


# =============================================================================
# メールアドレス変更確認ルート
# =============================================================================


@app.get("/confirm-email", response_model=None)
async def confirm_email(
    token: str = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Confirm email change."""
    # トークンのトリム
    token = token.strip() if token else ""

    if not token:
        return HTMLResponse(
            content=login_page(error="Invalid or missing confirmation token.")
        )

    # トークンで管理者を検索
    result = await db.execute(
        select(AdminUser).where(AdminUser.email_change_token == token)
    )
    admin = result.scalar_one_or_none()

    if not admin or not admin.email_change_token_expires_at or not admin.pending_email:
        return HTMLResponse(
            content=login_page(error="Invalid or expired confirmation token.")
        )

    if admin.email_change_token_expires_at < datetime.now(UTC):
        return HTMLResponse(content=login_page(error="Confirmation token has expired."))

    # メールアドレスを更新し、認証済みに設定し、保留中フィールドをクリア
    admin.email = admin.pending_email
    admin.email_verified = True
    admin.pending_email = None
    admin.email_change_token = None
    admin.email_change_token_expires_at = None
    await db.commit()

    return HTMLResponse(
        content=login_page(error=None),
    )


# =============================================================================
# ロビールート
# =============================================================================


@app.get("/lobbies", response_model=None)
async def lobbies_list(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """List all lobbies."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(Lobby).options(selectinload(Lobby.sessions)).order_by(Lobby.id)
    )
    lobbies = list(result.scalars().all())

    # ギルド・チャンネル名のルックアップを取得
    guilds_map, channels_map = await _get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=lobbies_list_page(
            lobbies,
            csrf_token=generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
        )
    )


@app.post("/lobbies/{lobby_id}/delete", response_model=None)
async def lobbies_delete(
    request: Request,
    lobby_id: int,
    user: dict[str, Any] | None = Depends(get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a lobby."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return RedirectResponse(url="/lobbies", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/lobbies", status_code=302)

    # 二重ロック: 同じリソースへの同時操作を防止
    async with get_resource_lock(f"lobby:delete:{lobby_id}"):
        result = await db.execute(select(Lobby).where(Lobby.id == lobby_id))
        lobby = result.scalar_one_or_none()
        if lobby:
            await db.delete(lobby)
            await db.commit()

        # クールタイム記録
        record_form_submit(user_email, path)

    return RedirectResponse(url="/lobbies", status_code=302)


# =============================================================================
# Sticky メッセージルート
# =============================================================================


@app.get("/sticky", response_model=None)
async def sticky_list(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """List all sticky messages."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(StickyMessage).order_by(StickyMessage.created_at))
    stickies = list(result.scalars().all())

    # ギルド・チャンネル名のルックアップを取得
    guilds_map, channels_map = await _get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=sticky_list_page(
            stickies,
            csrf_token=generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
        )
    )


@app.post("/sticky/{channel_id}/delete", response_model=None)
async def sticky_delete(
    request: Request,
    channel_id: str,
    user: dict[str, Any] | None = Depends(get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a sticky message."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return RedirectResponse(url="/sticky", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if is_form_cooldown_active(user_email, path):
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
        record_form_submit(user_email, path)

    return RedirectResponse(url="/sticky", status_code=302)


# =============================================================================
# Bump ルート
# =============================================================================


@app.get("/bump", response_model=None)
async def bump_list(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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
    guilds_map, channels_map = await _get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=bump_list_page(
            configs,
            reminders,
            csrf_token=generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
        )
    )


@app.post("/bump/config/{guild_id}/delete", response_model=None)
async def bump_config_delete(
    request: Request,
    guild_id: str,
    user: dict[str, Any] | None = Depends(get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a bump config."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return RedirectResponse(url="/bump", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if is_form_cooldown_active(user_email, path):
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
        record_form_submit(user_email, path)

    return RedirectResponse(url="/bump", status_code=302)


@app.post("/bump/reminder/{reminder_id}/delete", response_model=None)
async def bump_reminder_delete(
    request: Request,
    reminder_id: int,
    user: dict[str, Any] | None = Depends(get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a bump reminder."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return RedirectResponse(url="/bump", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if is_form_cooldown_active(user_email, path):
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
        record_form_submit(user_email, path)

    return RedirectResponse(url="/bump", status_code=302)


@app.post("/bump/reminder/{reminder_id}/toggle", response_model=None)
async def bump_reminder_toggle(
    request: Request,
    reminder_id: int,
    user: dict[str, Any] | None = Depends(get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Toggle a bump reminder enabled state."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return RedirectResponse(url="/bump", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if is_form_cooldown_active(user_email, path):
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
        record_form_submit(user_email, path)

    return RedirectResponse(url="/bump", status_code=302)


# -----------------------------------------------------------------------------
# Role Panels 管理
# -----------------------------------------------------------------------------


@app.get("/rolepanels", response_model=None)
async def rolepanels_list(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """List all role panels."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # パネル一覧を取得 (アイテムも一緒に取得)
    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .order_by(RolePanel.created_at.desc())
    )
    panels = list(result.scalars().all())

    # パネルID -> アイテムリストのマップを作成
    items_by_panel: dict[int, list[RolePanelItem]] = {}
    for panel in panels:
        items_by_panel[panel.id] = sorted(panel.items, key=lambda x: x.position)

    # ギルド・チャンネル名のルックアップを取得
    guilds_map, channels_map = await _get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=role_panels_list_page(
            panels,
            items_by_panel,
            csrf_token=generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
        )
    )


@app.post("/rolepanels/{panel_id}/delete", response_model=None)
async def rolepanel_delete(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a role panel."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return RedirectResponse(url="/rolepanels", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/rolepanels", status_code=302)

    # 二重ロック: 同じリソースへの同時操作を防止
    async with get_resource_lock(f"rolepanel:delete:{panel_id}"):
        result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
        panel = result.scalar_one_or_none()
        if panel:
            await db.delete(panel)
            await db.commit()

        # クールタイム記録
        record_form_submit(user_email, path)

    return RedirectResponse(url="/rolepanels", status_code=302)


@app.post("/rolepanels/{panel_id}/toggle-remove-reaction", response_model=None)
async def rolepanel_toggle_remove_reaction(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Toggle the remove_reaction flag for a role panel."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return RedirectResponse(url=f"/rolepanels/{panel_id}", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if is_form_cooldown_active(user_email, path):
        return RedirectResponse(url=f"/rolepanels/{panel_id}", status_code=302)

    # 二重ロック: 同じリソースへの同時操作を防止
    async with get_resource_lock(f"rolepanel:toggle:{panel_id}"):
        result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
        panel = result.scalar_one_or_none()
        if panel and panel.panel_type == "reaction":
            panel.remove_reaction = not panel.remove_reaction
            await db.commit()

        # クールタイム記録
        record_form_submit(user_email, path)

    return RedirectResponse(url=f"/rolepanels/{panel_id}", status_code=302)


async def _get_known_guilds_and_channels(
    db: AsyncSession,
) -> dict[str, list[str]]:
    """データベースから既知のギルドとチャンネルを取得する.

    Returns:
        ギルドID -> チャンネルIDリストのマッピング
    """
    guild_channels: dict[str, set[str]] = {}

    # Lobby からチャンネルを取得
    lobbies = await db.execute(select(Lobby))
    for lobby in lobbies.scalars():
        if lobby.guild_id not in guild_channels:
            guild_channels[lobby.guild_id] = set()
        guild_channels[lobby.guild_id].add(lobby.lobby_channel_id)

    # BumpConfig からチャンネルを取得
    bump_configs = await db.execute(select(BumpConfig))
    for config in bump_configs.scalars():
        if config.guild_id not in guild_channels:
            guild_channels[config.guild_id] = set()
        guild_channels[config.guild_id].add(config.channel_id)

    # StickyMessage からチャンネルを取得
    stickies = await db.execute(select(StickyMessage))
    for sticky in stickies.scalars():
        if sticky.guild_id not in guild_channels:
            guild_channels[sticky.guild_id] = set()
        guild_channels[sticky.guild_id].add(sticky.channel_id)

    # RolePanel からチャンネルを取得
    panels = await db.execute(select(RolePanel))
    for panel in panels.scalars():
        if panel.guild_id not in guild_channels:
            guild_channels[panel.guild_id] = set()
        guild_channels[panel.guild_id].add(panel.channel_id)

    # set を list に変換してソート
    return {
        guild_id: sorted(channels)
        for guild_id, channels in sorted(guild_channels.items())
    }


async def _get_known_roles_by_guild(
    db: AsyncSession,
) -> dict[str, list[str]]:
    """既存のRolePanelItemからギルドごとのロールIDを取得する.

    Returns:
        ギルドID -> ロールIDリストのマッピング
    """
    guild_roles: dict[str, set[str]] = {}

    # RolePanelItem と RolePanel を結合してギルドごとのロールを取得
    result = await db.execute(
        select(RolePanel.guild_id, RolePanelItem.role_id).join(
            RolePanelItem, RolePanel.id == RolePanelItem.panel_id
        )
    )

    for guild_id, role_id in result:
        if guild_id not in guild_roles:
            guild_roles[guild_id] = set()
        guild_roles[guild_id].add(role_id)

    # set を list に変換してソート
    return {guild_id: sorted(roles) for guild_id, roles in sorted(guild_roles.items())}


async def _get_discord_roles_by_guild(
    db: AsyncSession,
) -> dict[str, list[tuple[str, str, int]]]:
    """DBにキャッシュされているDiscordロール情報を取得する.

    Returns:
        ギルドID -> [(role_id, role_name, color), ...] のマッピング
        ロールは position 降順（上位ロールから）でソート
    """
    result = await db.execute(
        select(DiscordRole).order_by(DiscordRole.guild_id, DiscordRole.position.desc())
    )

    guild_roles: dict[str, list[tuple[str, str, int]]] = {}
    for role in result.scalars():
        if role.guild_id not in guild_roles:
            guild_roles[role.guild_id] = []
        guild_roles[role.guild_id].append((role.role_id, role.role_name, role.color))

    return guild_roles


async def _get_discord_guilds_and_channels(
    db: AsyncSession,
) -> tuple[dict[str, str], dict[str, list[tuple[str, str]]]]:
    """キャッシュされたギルドとチャンネル情報を取得する。

    Returns:
        (guilds_map, channels_map) のタプル
        - guilds_map: ギルドID -> ギルド名 のマッピング
        - channels_map: ギルドID -> [(チャンネルID, チャンネル名), ...] のマッピング
    """
    # ギルド情報を取得
    guilds_result = await db.execute(
        select(DiscordGuild).order_by(DiscordGuild.guild_name)
    )
    guilds_map: dict[str, str] = {
        g.guild_id: g.guild_name for g in guilds_result.scalars()
    }

    # チャンネル情報を取得
    channels_result = await db.execute(
        select(DiscordChannel).order_by(
            DiscordChannel.guild_id, DiscordChannel.position
        )
    )

    channels_map: dict[str, list[tuple[str, str]]] = {}
    for channel in channels_result.scalars():
        if channel.guild_id not in channels_map:
            channels_map[channel.guild_id] = []
        channels_map[channel.guild_id].append(
            (channel.channel_id, channel.channel_name)
        )

    return guilds_map, channels_map


@app.get("/rolepanels/new", response_model=None)
async def rolepanel_create_get(
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show role panel create form."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    guilds_map, channels_map = await _get_discord_guilds_and_channels(db)
    discord_roles = await _get_discord_roles_by_guild(db)
    return HTMLResponse(
        content=role_panel_create_page(
            guilds_map=guilds_map,
            channels_map=channels_map,
            discord_roles=discord_roles,
            csrf_token=generate_csrf_token(),
        )
    )


@app.post("/rolepanels/new", response_model=None)
async def rolepanel_create_post(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user),
    guild_id: Annotated[str, Form()] = "",
    channel_id: Annotated[str, Form()] = "",
    panel_type: Annotated[str, Form()] = "button",
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    use_embed: Annotated[str, Form()] = "1",
    color: Annotated[str, Form()] = "",
    remove_reaction: Annotated[str, Form()] = "",
    action: Annotated[str, Form()] = "create",
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Create a new role panel with role items."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # エラー時にも選択肢を表示するためにギルド/チャンネル/ロール情報を取得
    guilds_map, channels_map = await _get_discord_guilds_and_channels(db)
    discord_roles = await _get_discord_roles_by_guild(db)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=role_panel_create_page(
                error="Invalid security token. Please try again.",
                guilds_map=guilds_map,
                channels_map=channels_map,
                discord_roles=discord_roles,
                csrf_token=generate_csrf_token(),
            ),
            status_code=403,
        )

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if is_form_cooldown_active(user_email, path):
        return HTMLResponse(
            content=role_panel_create_page(
                error="Please wait before submitting again.",
                guilds_map=guilds_map,
                channels_map=channels_map,
                discord_roles=discord_roles,
                csrf_token=generate_csrf_token(),
            ),
            status_code=429,
        )

    # Trim input values
    guild_id = guild_id.strip()
    channel_id = channel_id.strip()
    panel_type = panel_type.strip()
    title = title.strip()
    description = description.strip()

    # Convert use_embed to boolean
    use_embed_bool = use_embed == "1"

    # Convert color to integer (hex string -> int)
    color_int: int | None = None
    color = color.strip()
    if color and use_embed_bool:
        # Remove # prefix if present
        color_hex = color.lstrip("#")
        if len(color_hex) == 6:
            with suppress(ValueError):
                color_int = int(color_hex, 16)

    # Convert remove_reaction to boolean (only effective for reaction panels)
    remove_reaction_bool = remove_reaction == "1" and panel_type == "reaction"

    # Parse role items from form data (バリデーションエラー時に保持するため先に解析)
    form_data = await request.form()
    item_emojis = form_data.getlist("item_emoji[]")
    item_role_ids = form_data.getlist("item_role_id[]")
    item_labels = form_data.getlist("item_label[]")
    item_styles = form_data.getlist("item_style[]")
    item_positions = form_data.getlist("item_position[]")

    # フォームから送信されたアイテムを保持用に収集
    submitted_items: list[dict[str, str | int | None]] = []
    for i in range(len(item_emojis)):
        submitted_items.append(
            {
                "emoji": str(item_emojis[i]).strip() if i < len(item_emojis) else "",
                "role_id": str(item_role_ids[i]).strip()
                if i < len(item_role_ids)
                else "",
                "label": str(item_labels[i]).strip() if i < len(item_labels) else "",
                "style": str(item_styles[i]).strip()
                if i < len(item_styles)
                else "secondary",
                "position": i,
            }
        )

    # Validation helper
    def error_response(error: str) -> HTMLResponse:
        return HTMLResponse(
            content=role_panel_create_page(
                error=error,
                guild_id=guild_id,
                channel_id=channel_id,
                panel_type=panel_type,
                title=title,
                description=description,
                use_embed=use_embed_bool,
                color=color,
                remove_reaction=remove_reaction_bool,
                guilds_map=guilds_map,
                channels_map=channels_map,
                discord_roles=discord_roles,
                csrf_token=generate_csrf_token(),
                existing_items=submitted_items,
            )
        )

    # Validation
    if not guild_id:
        return error_response("Guild ID is required")

    if not guild_id.isdigit():
        return error_response("Guild ID must be a number")

    if not channel_id:
        return error_response("Channel ID is required")

    if not channel_id.isdigit():
        return error_response("Channel ID must be a number")

    if panel_type not in ("button", "reaction"):
        return error_response("Invalid panel type")

    if not title:
        return error_response("Title is required")

    if len(title) > 256:
        return error_response("Title must be 256 characters or less")

    if len(description) > 4096:
        return error_response("Description must be 4096 characters or less")

    # Validate at least one role item (only for "create" action)
    is_draft = action == "save_draft"
    if not is_draft and not item_emojis:
        return error_response("At least one role item is required")

    # Validate and collect role items
    role_items_data: list[dict[str, str | int | None]] = []
    seen_emojis: set[str] = set()

    # Pad item_styles to match the length of other lists
    while len(item_styles) < len(item_emojis):
        item_styles.append("secondary")

    valid_styles = {"primary", "secondary", "success", "danger"}

    items_zip = zip(
        item_emojis,
        item_role_ids,
        item_labels,
        item_styles,
        item_positions,
        strict=False,
    )
    for i, (emoji, role_id, label, style, position) in enumerate(items_zip):
        # Trim values
        emoji = str(emoji).strip()
        role_id = str(role_id).strip()
        label = str(label).strip()
        style = str(style).strip()
        position_str = str(position).strip()

        # Validate emoji
        if not emoji:
            return error_response(f"Role item {i + 1}: Emoji is required")
        if len(emoji) > 64:
            return error_response(f"Role item {i + 1}: Emoji must be 64 chars or less")
        if not is_valid_emoji(emoji):
            return error_response(
                f"Role item {i + 1}: Invalid emoji. Use a Unicode emoji (🎮) "
                "or Discord custom emoji (<:name:id>)"
            )
        if emoji in seen_emojis:
            return error_response(f"Role item {i + 1}: Duplicate emoji '{emoji}'")
        seen_emojis.add(emoji)

        # Validate role_id
        if not role_id:
            return error_response(f"Role item {i + 1}: Role ID is required")
        if not role_id.isdigit():
            return error_response(f"Role item {i + 1}: Role ID must be a number")

        # Validate label
        if label and len(label) > 80:
            return error_response(f"Role item {i + 1}: Label must be 80 chars or less")

        # Validate style
        if style not in valid_styles:
            style = "secondary"

        # Parse position
        try:
            pos = int(position_str) if position_str else i
        except ValueError:
            pos = i

        role_items_data.append(
            {
                "emoji": emoji,
                "role_id": role_id,
                "label": label if label else None,
                "style": style,
                "position": pos,
            }
        )

    # 二重ロック: 同じユーザーによる同時パネル作成を防止
    async with get_resource_lock(f"rolepanel:create:{user_email}"):
        # Create the role panel
        panel = RolePanel(
            guild_id=guild_id,
            channel_id=channel_id,
            panel_type=panel_type,
            title=title,
            description=description if description else None,
            color=color_int,
            use_embed=use_embed_bool,
            remove_reaction=remove_reaction_bool,
        )
        db.add(panel)
        await db.flush()  # Get the panel ID without committing

        # Create role items
        for item_data in role_items_data:
            item = RolePanelItem(
                panel_id=panel.id,
                role_id=str(item_data["role_id"]),
                emoji=normalize_emoji(str(item_data["emoji"])),
                label=item_data["label"] if item_data["label"] else None,
                style=str(item_data.get("style") or "secondary"),
                position=int(item_data["position"]) if item_data["position"] else 0,
            )
            db.add(item)

        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            # UniqueConstraint 違反 (panel_id, emoji) の場合
            if "uq_panel_emoji" in str(e.orig):
                return error_response("Duplicate emoji in role items")
            raise

        await db.refresh(panel)

        # クールタイム記録
        record_form_submit(user_email, path)

    # 作成後は詳細ページにリダイレクト
    return RedirectResponse(url=f"/rolepanels/{panel.id}", status_code=302)


@app.get("/rolepanels/{panel_id}", response_model=None)
async def rolepanel_detail(
    panel_id: int,
    success: str | None = None,
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Show role panel detail page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .where(RolePanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/rolepanels", status_code=302)

    items = sorted(panel.items, key=lambda x: x.position)

    # ギルド・チャンネル名を取得
    guilds_map, channels_map = await _get_discord_guilds_and_channels(db)
    guild_name = guilds_map.get(panel.guild_id)
    # チャンネル名を取得
    guild_channels = channels_map.get(panel.guild_id, [])
    channel_name = next(
        (name for cid, name in guild_channels if cid == panel.channel_id), None
    )

    # このギルドのDiscordロール情報を取得
    discord_roles = await _get_discord_roles_by_guild(db)
    guild_discord_roles = discord_roles.get(panel.guild_id, [])

    return HTMLResponse(
        content=role_panel_detail_page(
            panel,
            items,
            success=success,
            discord_roles=guild_discord_roles,
            guild_name=guild_name,
            channel_name=channel_name,
            csrf_token=generate_csrf_token(),
        )
    )


@app.post("/rolepanels/{panel_id}/edit", response_model=None)
async def rolepanel_edit(
    request: Request,
    panel_id: int,
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    color: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Edit role panel title, description, and color."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Invalid+security+token",
            status_code=302,
        )

    # クールタイムチェック
    user_email = user.get("email", "")
    path = str(request.url.path)
    if is_form_cooldown_active(user_email, path):
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Please+wait+before+editing+again",
            status_code=302,
        )

    # バリデーション
    title = title.strip()
    if not title:
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Title+is+required",
            status_code=302,
        )
    if len(title) > 100:
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Title+must+be+100+characters+or+less",
            status_code=302,
        )

    description = description.strip()
    if len(description) > 2000:
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Description+must+be+2000+characters+or+less",
            status_code=302,
        )

    # パネルを取得して更新
    result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
    panel = result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/rolepanels", status_code=302)

    panel.title = title
    panel.description = description if description else None

    # Update color if panel uses embed
    if panel.use_embed:
        color = color.strip()
        color_hex = color.lstrip("#")
        if len(color_hex) == 6:
            with suppress(ValueError):
                panel.color = int(color_hex, 16)

    await db.commit()

    # クールタイム記録
    record_form_submit(user_email, path)

    return RedirectResponse(
        url=f"/rolepanels/{panel_id}?success=Panel+updated",
        status_code=302,
    )


@app.post("/rolepanels/{panel_id}/post", response_model=None)
async def rolepanel_post_to_discord(
    request: Request,
    panel_id: int,
    csrf_token: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Post role panel to Discord channel."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Invalid+security+token",
            status_code=302,
        )

    # クールタイムチェック
    user_email = user.get("email", "")
    path = str(request.url.path)
    if is_form_cooldown_active(user_email, path):
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Please+wait+before+posting+again",
            status_code=302,
        )

    # パネルを取得
    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .where(RolePanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/rolepanels", status_code=302)

    items = sorted(panel.items, key=lambda x: x.position)

    # 既存メッセージがある場合は編集、なければ新規投稿
    if panel.message_id:
        # 既存メッセージを編集
        success, error_msg = await edit_role_panel_in_discord(panel, items)
        message_id = panel.message_id if success else None
        action_text = "Updated"
    else:
        # 新規投稿
        success, message_id, error_msg = await post_role_panel_to_discord(panel, items)
        action_text = "Posted"

    if not success:
        error_encoded = (error_msg or "Unknown error").replace(" ", "+")
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Failed:+{error_encoded}",
            status_code=302,
        )

    # 新規投稿の場合はメッセージ ID を保存
    if message_id and message_id != panel.message_id:
        panel.message_id = message_id
        await db.commit()

    # リアクション式の場合はリアクションを追加/更新
    target_message_id = message_id or panel.message_id
    if panel.panel_type == "reaction" and items and target_message_id:
        # 編集時は既存リアクションをクリア
        is_edit = action_text == "Updated"
        react_success, react_error = await add_reactions_to_message(
            panel.channel_id,
            target_message_id,
            items,
            clear_existing=is_edit,
        )
        if not react_success:
            return RedirectResponse(
                url=f"/rolepanels/{panel_id}?success={action_text}+but+reactions+failed:+{react_error}",
                status_code=302,
            )

    # クールタイム記録
    record_form_submit(user_email, path)

    return RedirectResponse(
        url=f"/rolepanels/{panel_id}?success={action_text}+to+Discord",
        status_code=302,
    )


@app.post("/rolepanels/{panel_id}/items/add", response_model=None)
async def rolepanel_add_item(
    request: Request,
    panel_id: int,
    emoji: Annotated[str, Form()] = "",
    role_id: Annotated[str, Form()] = "",
    label: Annotated[str, Form()] = "",
    style: Annotated[str, Form()] = "secondary",
    csrf_token: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Add a role item to a panel."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Get the panel
    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .where(RolePanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/rolepanels", status_code=302)

    # Trim inputs
    emoji = emoji.strip()
    role_id = role_id.strip()
    label = label.strip()

    items = sorted(panel.items, key=lambda x: x.position)

    # ギルド・チャンネル名を取得
    guilds_map, channels_map = await _get_discord_guilds_and_channels(db)
    guild_name = guilds_map.get(panel.guild_id)
    guild_channels = channels_map.get(panel.guild_id, [])
    channel_name = next(
        (name for cid, name in guild_channels if cid == panel.channel_id), None
    )

    # このギルドのDiscordロール情報を取得
    discord_roles = await _get_discord_roles_by_guild(db)
    guild_discord_roles = discord_roles.get(panel.guild_id, [])

    # Validation helper
    def error_response(error: str) -> HTMLResponse:
        return HTMLResponse(
            content=role_panel_detail_page(
                panel,
                items,
                error=error,
                discord_roles=guild_discord_roles,
                guild_name=guild_name,
                channel_name=channel_name,
                csrf_token=generate_csrf_token(),
            )
        )

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=role_panel_detail_page(
                panel,
                items,
                error="Invalid security token. Please try again.",
                discord_roles=guild_discord_roles,
                guild_name=guild_name,
                channel_name=channel_name,
                csrf_token=generate_csrf_token(),
            ),
            status_code=403,
        )

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if is_form_cooldown_active(user_email, path):
        return HTMLResponse(
            content=role_panel_detail_page(
                panel,
                items,
                error="Please wait before submitting again.",
                discord_roles=guild_discord_roles,
                guild_name=guild_name,
                channel_name=channel_name,
                csrf_token=generate_csrf_token(),
            ),
            status_code=429,
        )

    # Validation
    if not emoji:
        return error_response("Emoji is required")

    if len(emoji) > 64:
        return error_response("Emoji must be 64 characters or less")

    if not is_valid_emoji(emoji):
        return error_response(
            "Invalid emoji. Use a Unicode emoji (🎮) "
            "or Discord custom emoji (<:name:id>)"
        )

    if not role_id:
        return error_response("Role ID is required")

    if not role_id.isdigit():
        return error_response("Role ID must be a number")

    if label and len(label) > 80:
        return error_response("Label must be 80 characters or less")

    # Check for duplicate emoji
    # Normalize emoji for consistent comparison and storage
    normalized_emoji = normalize_emoji(emoji)

    for item in items:
        if item.emoji == normalized_emoji:
            return error_response(f"Emoji '{emoji}' is already used in this panel")

    # Validate style
    valid_styles = {"primary", "secondary", "success", "danger"}
    if style not in valid_styles:
        style = "secondary"

    # Auto-calculate position from existing items
    next_position = max((it.position for it in items), default=-1) + 1

    # 二重ロック: 同じパネルへの同時アイテム追加を防止
    async with get_resource_lock(f"rolepanel:add_item:{panel_id}"):
        # Create the item
        item = RolePanelItem(
            panel_id=panel_id,
            role_id=role_id,
            emoji=normalized_emoji,
            label=label if label else None,
            style=style,
            position=next_position,
        )
        db.add(item)

        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            if "uq_panel_emoji" in str(e.orig):
                return error_response(f"Emoji '{emoji}' is already used in this panel")
            raise

        # クールタイム記録
        record_form_submit(user_email, path)

    return RedirectResponse(
        url=f"/rolepanels/{panel_id}?success=Role+item+added", status_code=302
    )


@app.post("/rolepanels/{panel_id}/items/{item_id}/delete", response_model=None)
async def rolepanel_delete_item(
    request: Request,
    panel_id: int,
    item_id: int,
    user: dict[str, Any] | None = Depends(get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a role item from a panel."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not validate_csrf_token(csrf_token):
        return RedirectResponse(url=f"/rolepanels/{panel_id}", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if is_form_cooldown_active(user_email, path):
        return RedirectResponse(url=f"/rolepanels/{panel_id}", status_code=302)

    # Check panel exists
    panel_result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
    panel = panel_result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/rolepanels", status_code=302)

    # 二重ロック: 同じアイテムへの同時削除を防止
    async with get_resource_lock(f"rolepanel:delete_item:{panel_id}:{item_id}"):
        # Get and delete the item
        result = await db.execute(
            select(RolePanelItem).where(
                RolePanelItem.id == item_id, RolePanelItem.panel_id == panel_id
            )
        )
        item = result.scalar_one_or_none()
        if item:
            await db.delete(item)
            await db.commit()

        # クールタイム記録
        record_form_submit(user_email, path)

    return RedirectResponse(
        url=f"/rolepanels/{panel_id}?success=Role+item+deleted", status_code=302
    )


@app.post("/rolepanels/{panel_id}/items/reorder", response_model=None)
async def rolepanel_reorder_items(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Reorder role items via drag-and-drop."""
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await request.json()
    csrf_token = body.get("csrf_token", "")
    if not validate_csrf_token(csrf_token):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    item_ids = body.get("item_ids", [])
    if not isinstance(item_ids, list):
        return JSONResponse({"error": "Invalid item_ids"}, status_code=400)

    # Check panel exists
    panel_result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
    panel = panel_result.scalar_one_or_none()
    if not panel:
        return JSONResponse({"error": "Panel not found"}, status_code=404)

    async with get_resource_lock(f"rolepanel:reorder:{panel_id}"):
        for position, item_id in enumerate(item_ids):
            await db.execute(
                update(RolePanelItem)
                .where(
                    RolePanelItem.id == int(item_id),
                    RolePanelItem.panel_id == panel_id,
                )
                .values(position=position)
            )
        await db.commit()

    return JSONResponse({"ok": True})
