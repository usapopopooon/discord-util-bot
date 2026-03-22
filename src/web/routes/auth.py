"""Authentication routes."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.app as _app
from src.constants import (
    BCRYPT_MAX_PASSWORD_BYTES,
    EMAIL_CHANGE_TOKEN_EXPIRY_SECONDS,
    PASSWORD_MIN_LENGTH,
    SESSION_MAX_AGE_SECONDS,
    TOKEN_BYTE_LENGTH,
)
from src.database.models import AdminUser
from src.web.templates import (
    email_verification_pending_page,
    forgot_password_page,
    initial_setup_page,
    login_page,
    reset_password_page,
)

router = APIRouter()


@router.get("/", response_model=None)
async def index(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
) -> Response:
    """Redirect to dashboard or login."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@router.get("/login", response_model=None)
async def login_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
) -> Response:
    """Show login page."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return HTMLResponse(content=login_page(csrf_token=_app.generate_csrf_token()))


@router.post("/login", response_model=None)
async def login_post(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Process login form."""
    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=login_page(
                error="Invalid security token. Please try again.",
                csrf_token=_app.generate_csrf_token(),
            ),
            status_code=403,
        )

    client_ip = request.client.host if request.client else "unknown"

    # メールアドレスは前後の空白をトリムする (パスワードはトリムしない)
    email = email.strip() if email else ""

    if _app.is_rate_limited(client_ip):
        return HTMLResponse(
            content=login_page(
                error="Too many attempts. Try again later.",
                csrf_token=_app.generate_csrf_token(),
            ),
            status_code=429,
        )

    # 管理者ユーザーを取得または作成
    admin = await _app.get_or_create_admin(db)
    if admin is None:
        return HTMLResponse(
            content=login_page(
                error="ADMIN_PASSWORD not configured",
                csrf_token=_app.generate_csrf_token(),
            ),
            status_code=500,
        )

    # 認証情報を検証 (メールアドレスは大文字小文字を区別)
    if admin.email != email or not await _app.verify_password_async(
        password, admin.password_hash
    ):
        _app.record_failed_attempt(client_ip)
        return HTMLResponse(
            content=login_page(
                error="Invalid email or password",
                csrf_token=_app.generate_csrf_token(),
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
        value=_app.create_session_token(email),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=_app.SECURE_COOKIE,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout() -> RedirectResponse:
    """Logout and clear session."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="session")
    return response


# =============================================================================
# 初期セットアップルート
# =============================================================================


@router.get("/initial-setup", response_model=None)
async def initial_setup_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Show initial setup page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await _app.get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # セットアップ済み
    if admin.password_changed_at is not None:
        if not admin.email_verified:
            return RedirectResponse(url="/verify-email", status_code=302)
        return RedirectResponse(url="/dashboard", status_code=302)

    return HTMLResponse(
        content=initial_setup_page(
            current_email=admin.email, csrf_token=_app.generate_csrf_token()
        )
    )


@router.post("/initial-setup", response_model=None)
async def initial_setup_post(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    new_email: Annotated[str, Form()] = "",
    new_password: Annotated[str, Form()] = "",
    confirm_password: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Process initial setup form."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await _app.get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Invalid security token. Please try again.",
                csrf_token=_app.generate_csrf_token(),
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
                csrf_token=_app.generate_csrf_token(),
            )
        )

    if not _app.EMAIL_PATTERN.match(new_email):
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Invalid email format",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    # パスワードのバリデーション
    if not new_password:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Password is required",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    if new_password != confirm_password:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error="Passwords do not match",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    if len(new_password) < PASSWORD_MIN_LENGTH:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error=f"Password must be at least {PASSWORD_MIN_LENGTH} characters",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    # bcrypt の制限を超えるパスワードは警告を表示
    if len(new_password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        return HTMLResponse(
            content=initial_setup_page(
                current_email=admin.email,
                error=f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    # パスワードを更新
    admin.password_hash = await _app.hash_password_async(new_password)
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
        value=_app.create_session_token(new_email),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=_app.SECURE_COOKIE,
        samesite="lax",
    )
    return response


@router.get("/verify-email", response_model=None)
async def verify_email_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Show email verification pending page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await _app.get_or_create_admin(db)
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
            pending_email=admin.pending_email,
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/resend-verification", response_model=None)
async def resend_verification(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Resend verification email."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await _app.get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=email_verification_pending_page(
                pending_email=admin.pending_email or "",
                error="Invalid security token. Please try again.",
                csrf_token=_app.generate_csrf_token(),
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
    email_sent = _app.send_email_change_verification(admin.pending_email, token)

    if email_sent:
        return HTMLResponse(
            content=email_verification_pending_page(
                pending_email=admin.pending_email,
                success="Verification email sent.",
                csrf_token=_app.generate_csrf_token(),
            )
        )
    else:
        return HTMLResponse(
            content=email_verification_pending_page(
                pending_email=admin.pending_email,
                error="Failed to send verification email. Check SMTP configuration.",
                csrf_token=_app.generate_csrf_token(),
            )
        )


# =============================================================================
# パスワードリセットルート
# =============================================================================


@router.get("/forgot-password", response_model=None)
async def forgot_password_get() -> Response:
    """Show forgot password page."""
    return HTMLResponse(
        content=forgot_password_page(csrf_token=_app.generate_csrf_token())
    )


@router.post("/forgot-password", response_model=None)
async def forgot_password_post(
    email: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Process forgot password form."""
    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=forgot_password_page(
                error="Invalid security token. Please try again.",
                csrf_token=_app.generate_csrf_token(),
            ),
            status_code=403,
        )

    # 入力値のトリム
    email = email.strip() if email else ""

    # SMTP 未設定のエラーメッセージを表示
    _ = email, db  # unused variable warning 回避
    return HTMLResponse(
        content=forgot_password_page(
            error="Password reset is not available. SMTP is not configured.",
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.get("/reset-password", response_model=None)
async def reset_password_get(
    token: str = "",
    db: AsyncSession = Depends(_app.get_db),
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
        content=reset_password_page(token=token, csrf_token=_app.generate_csrf_token())
    )


@router.post("/reset-password", response_model=None)
async def reset_password_post(
    token: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Process reset password form."""
    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=reset_password_page(
                token=token,
                error="Invalid security token. Please try again.",
                csrf_token=_app.generate_csrf_token(),
            ),
            status_code=403,
        )

    # パスワードの一致を検証
    if new_password != confirm_password:
        return HTMLResponse(
            content=reset_password_page(
                token=token,
                error="Passwords do not match",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    # パスワードの長さを検証
    if len(new_password) < PASSWORD_MIN_LENGTH:
        return HTMLResponse(
            content=reset_password_page(
                token=token,
                error=f"Password must be at least {PASSWORD_MIN_LENGTH} characters",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    # bcrypt の制限を超えるパスワードは拒否
    if len(new_password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        error_msg = f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes"
        return HTMLResponse(
            content=reset_password_page(
                token=token, error=error_msg, csrf_token=_app.generate_csrf_token()
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
    admin.password_hash = await _app.hash_password_async(new_password)
    admin.password_changed_at = datetime.now(UTC)
    admin.reset_token = None
    admin.reset_token_expires_at = None
    await db.commit()

    return HTMLResponse(
        content=login_page(error=None),
    )


@router.get("/confirm-email", response_model=None)
async def confirm_email(
    token: str = "",
    db: AsyncSession = Depends(_app.get_db),
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
