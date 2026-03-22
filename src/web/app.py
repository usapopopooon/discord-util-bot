"""FastAPI web admin application."""

import asyncio
import logging
import os
import re
import secrets
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any, cast

import bcrypt
from fastapi import Cookie, FastAPI, Request
from fastapi.responses import Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
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
from src.database.engine import (
    async_session,
)
from src.database.engine import (
    check_database_connection as check_database_connection,  # noqa: F401
)
from src.database.models import (
    AdminUser,
    DiscordChannel,
    DiscordGuild,
    DiscordRole,
    SiteSettings,
)
from src.web.discord_api import (  # noqa: F401  # re-exported for route modules / test patches
    add_reactions_to_message as add_reactions_to_message,
)
from src.web.discord_api import (
    delete_discord_message as delete_discord_message,
)
from src.web.discord_api import (
    edit_role_panel_in_discord as edit_role_panel_in_discord,
)
from src.web.discord_api import (
    edit_ticket_panel_in_discord as edit_ticket_panel_in_discord,
)
from src.web.discord_api import (
    post_role_panel_to_discord as post_role_panel_to_discord,
)
from src.web.discord_api import (
    post_ticket_panel_to_discord as post_ticket_panel_to_discord,
)
from src.web.email_service import (
    send_email_change_verification as send_email_change_verification,  # noqa: F401
    # send_password_reset_email,  # SMTP 未設定のため未使用
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
        # DB からタイムゾーン設定を読み込み
        try:
            async with async_session() as session:
                result = await session.execute(select(SiteSettings).limit(1))
                site = result.scalar_one_or_none()
                if site:
                    from src.utils import set_timezone_offset

                    set_timezone_offset(site.timezone_offset)
                    logger.info("Timezone offset loaded: UTC%+d", site.timezone_offset)
        except Exception:
            logger.warning("Failed to load site settings from DB")
    yield
    # シャットダウン
    logger.info("Shutting down web admin application...")


app = FastAPI(title="Bot Admin", docs_url=None, redoc_url=None, lifespan=lifespan)


# =============================================================================
# セキュリティヘッダーミドルウェア
# =============================================================================

# Content Security Policy (モジュール定数: リクエストごとの文字列構築を回避)
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
        response.headers["Content-Security-Policy"] = _CSP_HEADER

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


async def hash_password_async(password: str) -> str:
    """bcrypt をスレッドプールで実行してイベントループをブロックしない。"""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    """bcrypt 検証をスレッドプールで実行してイベントループをブロックしない。"""
    return await asyncio.to_thread(verify_password, password, password_hash)


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
            password_hash=await hash_password_async(INIT_ADMIN_PASSWORD),
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

    if (
        _last_cleanup_time > 0
        and now - _last_cleanup_time < RATE_LIMIT_CLEANUP_INTERVAL_SECONDS
    ):
        return

    _last_cleanup_time = now
    # 1パス削除: キーのスナップショットからフィルタリング + 期限切れ削除
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

    # IP のエントリがない or 空リスト → レート制限なし (dict 書き込み不要)
    if not attempts:
        return False

    now = time.time()
    valid = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]

    # フィルタ後のリストが元と異なる場合のみ dict 更新
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

    # 1パス削除: キーのスナップショットから期限切れをその場で削除
    threshold = FORM_SUBMIT_COOLDOWN_SECONDS * 5
    for key in list(FORM_SUBMIT_TIMES):
        if now - FORM_SUBMIT_TIMES[key] > threshold:
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
# データベースヘルパー関数 (ルートモジュールから使用される)
# =============================================================================


async def _get_known_guilds_and_channels(
    db: AsyncSession,
) -> dict[str, list[str]]:
    """データベースから既知のギルドとチャンネルを取得する.

    Returns:
        ギルドID -> チャンネルIDリストのマッピング
    """
    from src.database.models import (
        BumpConfig,
        Lobby,
        RolePanel,
        StickyMessage,
    )

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
    from src.database.models import RolePanel, RolePanelItem

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

    # チャンネル情報を取得 (カテゴリ type=4 は除外)
    channels_result = await db.execute(
        select(DiscordChannel)
        .where(DiscordChannel.channel_type != 4)
        .order_by(DiscordChannel.guild_id, DiscordChannel.position)
    )

    channels_map: dict[str, list[tuple[str, str]]] = {}
    for channel in channels_result.scalars():
        if channel.guild_id not in channels_map:
            channels_map[channel.guild_id] = []
        channels_map[channel.guild_id].append(
            (channel.channel_id, channel.channel_name)
        )

    return guilds_map, channels_map


async def _get_discord_categories(
    db: AsyncSession,
) -> dict[str, list[tuple[str, str]]]:
    """キャッシュされた Discord カテゴリチャンネル情報を取得する。

    Returns:
        ギルドID -> [(カテゴリID, カテゴリ名), ...] のマッピング
    """
    result = await db.execute(
        select(DiscordChannel)
        .where(DiscordChannel.channel_type == 4)
        .order_by(DiscordChannel.guild_id, DiscordChannel.position)
    )

    categories_map: dict[str, list[tuple[str, str]]] = {}
    for cat in result.scalars():
        if cat.guild_id not in categories_map:
            categories_map[cat.guild_id] = []
        categories_map[cat.guild_id].append((cat.channel_id, cat.channel_name))

    return categories_map


# =============================================================================
# Activity 定数
# =============================================================================

_VALID_ACTIVITY_TYPES = {"playing", "listening", "watching", "competing"}


# =============================================================================
# ルーター登録
# =============================================================================

from src.web.routes.auth import router as auth_router  # noqa: E402
from src.web.routes.automod import router as automod_router  # noqa: E402
from src.web.routes.bump import router as bump_router  # noqa: E402
from src.web.routes.joinrole import router as joinrole_router  # noqa: E402
from src.web.routes.lobby import router as lobby_router  # noqa: E402
from src.web.routes.misc import router as misc_router  # noqa: E402
from src.web.routes.rolepanel import router as rolepanel_router  # noqa: E402
from src.web.routes.settings import router as settings_router  # noqa: E402
from src.web.routes.sticky import router as sticky_router  # noqa: E402
from src.web.routes.ticket import router as ticket_router  # noqa: E402

app.include_router(misc_router)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(lobby_router)
app.include_router(sticky_router)
app.include_router(bump_router)
app.include_router(rolepanel_router)
app.include_router(automod_router)
app.include_router(ticket_router)
app.include_router(joinrole_router)
