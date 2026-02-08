"""Web test fixtures."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.constants import DEFAULT_TEST_DATABASE_URL
from src.database.models import AdminUser, Base
from src.web import app as web_app_module
from src.web.app import app, generate_csrf_token, get_db, hash_password

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    DEFAULT_TEST_DATABASE_URL,
)

# テスト用管理者認証情報
TEST_ADMIN_EMAIL = "test@example.com"
TEST_ADMIN_PASSWORD = "testpassword123"

# --- Speed optimizations ---
# bcrypt hash をモジュールレベルでキャッシュ (bcrypt は意図的に低速 ~0.2-0.3s)
_CACHED_PASSWORD_HASH = hash_password(TEST_ADMIN_PASSWORD)

# NullPool: コネクションプールなし (function スコープの event loop でも安全)
_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

# スキーマ作成フラグ: DROP/CREATE は初回のみ、以降は TRUNCATE
_schema_created = False

# 全テーブル TRUNCATE 文を事前構築
_TRUNCATE_SQL = text(
    "TRUNCATE TABLE "
    + ",".join(Base.metadata.tables.keys())
    + " RESTART IDENTITY CASCADE"
)


@pytest.fixture(autouse=True)
def clear_rate_limit() -> None:
    """各テスト前にレート制限とフォームクールタイムをクリアする。"""
    web_app_module.LOGIN_ATTEMPTS.clear()
    web_app_module.FORM_SUBMIT_TIMES.clear()
    web_app_module._last_cleanup_time = 0.0
    web_app_module._form_cooldown_last_cleanup_time = 0.0


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """PostgreSQL テスト DB のセッションを提供する。"""
    global _schema_created
    if _schema_created:
        # 2回目以降: TRUNCATE (DROP/CREATE DDL より大幅に高速)
        async with _engine.begin() as conn:
            await conn.execute(_TRUNCATE_SQL)
    else:
        # 初回: スキーマ作成
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        _schema_created = True

    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> AdminUser:
    """テスト用の AdminUser を作成する (パスワード変更済み、メール認証済み)。"""
    admin = AdminUser(
        email=TEST_ADMIN_EMAIL,
        password_hash=_CACHED_PASSWORD_HASH,
        password_changed_at=datetime.now(UTC),
        email_verified=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.fixture
async def initial_admin_user(db_session: AsyncSession) -> AdminUser:
    """テスト用の AdminUser を作成する (初回セットアップ状態)。"""
    admin = AdminUser(
        email=TEST_ADMIN_EMAIL,
        password_hash=_CACHED_PASSWORD_HASH,
        password_changed_at=None,
        email_verified=False,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.fixture
async def unverified_admin_user(db_session: AsyncSession) -> AdminUser:
    """テスト用の AdminUser を作成する (パスワード変更済み、メール未認証)。"""
    admin = AdminUser(
        email=TEST_ADMIN_EMAIL,
        password_hash=_CACHED_PASSWORD_HASH,
        password_changed_at=datetime.now(UTC),
        email_verified=False,
        pending_email="pending@example.com",
        email_change_token="test_verify_token",
        email_change_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI テストクライアントを提供する。"""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_client(
    client: AsyncClient,
    admin_user: AdminUser,
) -> AsyncClient:
    """認証済みのテストクライアントを提供する。"""
    csrf_token = generate_csrf_token()

    response = await client.post(
        "/login",
        data={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_ADMIN_PASSWORD,
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    session_cookie = response.cookies.get("session")
    if session_cookie:
        client.cookies.set("session", session_cookie)
    return client


@pytest.fixture(autouse=True)
def mock_email_sending() -> Generator[None, None, None]:
    """全てのテストでメール送信をモックする (常に成功)。"""
    with (
        patch(
            "src.web.app.send_email_change_verification",
            return_value=True,
        ),
    ):
        yield


@pytest.fixture
def csrf_token() -> str:
    """テスト用の CSRF トークンを生成する。"""
    return generate_csrf_token()


@pytest.fixture(autouse=True)
def disable_csrf_validation(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """CSRF 検証をデフォルトで無効化する (CSRFProtection テスト以外)。

    TestCSRFProtection クラスのテストでは CSRF 検証を有効にする。
    """
    if request.node.parent and "TestCSRFProtection" in request.node.parent.name:
        yield
        return

    with patch(
        "src.web.app.validate_csrf_token",
        return_value=True,
    ):
        yield
