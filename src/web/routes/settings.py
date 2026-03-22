"""Settings routes."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.app as _app
from src.constants import (
    BCRYPT_MAX_PASSWORD_BYTES,
    PASSWORD_MIN_LENGTH,
    SESSION_MAX_AGE_SECONDS,
)
from src.database.models import (
    AdminUser,
    BumpConfig,
    BumpReminder,
    DiscordGuild,
    Lobby,
    RolePanel,
    SiteSettings,
    StickyMessage,
)
from src.utils import get_resource_lock
from src.web.templates import (
    dashboard_page,
    email_change_page,
    maintenance_page,
    password_change_page,
    settings_page,
)

router = APIRouter()


@router.get("/dashboard", response_model=None)
async def dashboard(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Show dashboard."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await _app.get_or_create_admin(db)
    if admin:
        # パスワードが一度も変更されていない場合は初期セットアップにリダイレクト
        if admin.password_changed_at is None:
            return RedirectResponse(url="/initial-setup", status_code=302)
        # メールアドレス未認証の場合は認証ページにリダイレクト
        if not admin.email_verified:
            return RedirectResponse(url="/verify-email", status_code=302)

    return HTMLResponse(content=dashboard_page(email=user.get("email", "Admin")))


@router.get("/settings", response_model=None)
async def settings_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Show settings hub page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await _app.get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # パスワードが一度も変更されていない場合は初期セットアップにリダイレクト
    if admin.password_changed_at is None:
        return RedirectResponse(url="/initial-setup", status_code=302)

    # メールアドレス未認証の場合は認証ページにリダイレクト
    if not admin.email_verified:
        return RedirectResponse(url="/verify-email", status_code=302)

    result = await db.execute(select(SiteSettings).limit(1))
    site = result.scalar_one_or_none()

    return HTMLResponse(
        content=settings_page(
            current_email=admin.email,
            pending_email=admin.pending_email,
            timezone_offset=site.timezone_offset if site else 9,
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/settings/timezone", response_model=None)
async def settings_timezone_post(
    request: Request,
    timezone_offset: Annotated[int, Form()],
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Update timezone offset setting."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/settings", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/settings", status_code=302)

    if timezone_offset < -12 or timezone_offset > 14:
        return RedirectResponse(url="/settings", status_code=302)

    async with get_resource_lock("site_settings:update"):
        result = await db.execute(select(SiteSettings).limit(1))
        site = result.scalar_one_or_none()
        if site:
            site.timezone_offset = timezone_offset
            site.updated_at = datetime.now(UTC)
        else:
            site = SiteSettings(timezone_offset=timezone_offset)
            db.add(site)
        await db.commit()

        # ランタイムのタイムゾーンオフセットを更新
        from src.utils import set_timezone_offset

        set_timezone_offset(timezone_offset)

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/settings", status_code=302)


@router.get("/settings/email", response_model=None)
async def settings_email_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Show email change page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await _app.get_or_create_admin(db)
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
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/settings/email", response_model=None)
async def settings_email_post(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    new_email: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Update email address."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await _app.get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=email_change_page(
                current_email=admin.email,
                pending_email=admin.pending_email,
                error="Invalid security token. Please try again.",
                csrf_token=_app.generate_csrf_token(),
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
                csrf_token=_app.generate_csrf_token(),
            )
        )

    if not _app.EMAIL_PATTERN.match(new_email):
        return HTMLResponse(
            content=email_change_page(
                current_email=admin.email,
                pending_email=admin.pending_email,
                error="Invalid email format",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    if new_email == admin.email:
        return HTMLResponse(
            content=email_change_page(
                current_email=admin.email,
                pending_email=admin.pending_email,
                error="New email must be different from current email",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    # メールアドレスを直接更新（SMTP 未設定のため認証スキップ）
    admin.email = new_email
    admin.pending_email = None
    admin.email_change_token = None
    admin.email_change_token_expires_at = None

    await db.commit()

    # セッションを更新してリダイレクト
    response = RedirectResponse(url="/settings", status_code=302)
    response.set_cookie(
        key="session",
        value=_app.create_session_token(new_email),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=_app.SECURE_COOKIE,
        samesite="lax",
    )
    return response


@router.get("/settings/password", response_model=None)
async def settings_password_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Show password change page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await _app.get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # 初期セットアップが先に必要
    if admin.password_changed_at is None:
        return RedirectResponse(url="/initial-setup", status_code=302)

    # メールアドレス認証が先に必要
    if not admin.email_verified:
        return RedirectResponse(url="/verify-email", status_code=302)

    return HTMLResponse(
        content=password_change_page(csrf_token=_app.generate_csrf_token())
    )


@router.post("/settings/password", response_model=None)
async def settings_password_post(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    new_password: Annotated[str, Form()] = "",
    confirm_password: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Update password."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    admin = await _app.get_or_create_admin(db)
    if admin is None:
        return RedirectResponse(url="/login", status_code=302)

    # 初期セットアップが先に必要
    if admin.password_changed_at is None:
        return RedirectResponse(url="/initial-setup", status_code=302)

    # メールアドレス認証が先に必要
    if not admin.email_verified:
        return RedirectResponse(url="/verify-email", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=password_change_page(
                error="Invalid security token. Please try again.",
                csrf_token=_app.generate_csrf_token(),
            ),
            status_code=403,
        )

    # バリデーション
    if not new_password:
        return HTMLResponse(
            content=password_change_page(
                error="Password is required",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    if new_password != confirm_password:
        return HTMLResponse(
            content=password_change_page(
                error="Passwords do not match",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    if len(new_password) < PASSWORD_MIN_LENGTH:
        return HTMLResponse(
            content=password_change_page(
                error=f"Password must be at least {PASSWORD_MIN_LENGTH} characters",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    # bcrypt の制限を超えるパスワードは拒否
    if len(new_password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        return HTMLResponse(
            content=password_change_page(
                error=f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes",
                csrf_token=_app.generate_csrf_token(),
            )
        )

    # パスワードを更新
    admin.password_hash = await _app.hash_password_async(new_password)
    admin.password_changed_at = datetime.now(UTC)
    await db.commit()

    # パスワード変更後はログアウト
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="session")
    return response


# =============================================================================
# メンテナンスルート
# =============================================================================


@router.get("/settings/maintenance", response_model=None)
async def settings_maintenance(
    request: Request,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
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
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/settings/maintenance/refresh", response_model=None)
async def settings_maintenance_refresh(
    request: Request,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
) -> Response:
    """Refresh maintenance page statistics."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF token validation
    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/settings/maintenance", status_code=302)

    # Rate limit check
    path = str(request.url.path)
    user_email = user.get("email", "")
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(
            url="/settings/maintenance?success=Please+wait+before+refreshing",
            status_code=302,
        )

    # Record form submit for rate limiting
    _app.record_form_submit(user_email, path)

    return RedirectResponse(
        url="/settings/maintenance?success=Stats+refreshed",
        status_code=302,
    )


@router.post("/settings/maintenance/cleanup", response_model=None)
async def settings_maintenance_cleanup(
    request: Request,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Cleanup orphaned database records."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF token validation
    if not _app.validate_csrf_token(csrf_token):
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
                csrf_token=_app.generate_csrf_token(),
            ),
            status_code=400,
        )

    # Rate limit check
    path = str(request.url.path)
    user_email = user.get("email", "")
    if _app.is_form_cooldown_active(user_email, path):
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
    _app.record_form_submit(user_email, path)

    if deleted_counts:
        success_msg = "Cleaned up: " + ", ".join(deleted_counts)
    else:
        success_msg = "No orphaned data found"

    return RedirectResponse(
        url=f"/settings/maintenance?success={success_msg.replace(' ', '+')}",
        status_code=302,
    )
