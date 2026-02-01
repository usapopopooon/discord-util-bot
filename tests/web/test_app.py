"""Tests for web admin application routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from src.web.app import hash_password

from .conftest import TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD

# ===========================================================================
# ヘルスチェックルート
# ===========================================================================


class TestHealthCheckRoute:
    """/health ルートのテスト。"""

    async def test_health_check_returns_ok(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """正常時は 200 OK を返す。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        # check_database_connection を True を返すようにモック
        monkeypatch.setattr(
            web_app_module,
            "check_database_connection",
            AsyncMock(return_value=True),
        )

        response = await client.get("/health")
        assert response.status_code == 200
        assert response.text == "ok"

    async def test_health_check_returns_503_on_db_failure(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DB 接続失敗時は 503 を返す。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        # check_database_connection を False を返すようにモック
        monkeypatch.setattr(
            web_app_module,
            "check_database_connection",
            AsyncMock(return_value=False),
        )

        response = await client.get("/health")
        assert response.status_code == 503
        assert response.text == "database unavailable"

    async def test_health_check_no_auth_required(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """認証なしでアクセスできる (ログイン不要)。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        # check_database_connection を True を返すようにモック
        monkeypatch.setattr(
            web_app_module,
            "check_database_connection",
            AsyncMock(return_value=True),
        )

        # 認証なしのクライアントでアクセス
        response = await client.get("/health")
        assert response.status_code == 200
        # リダイレクトではなく直接レスポンスを返す
        assert "session" not in response.request.headers


# ===========================================================================
# インデックスルート
# ===========================================================================


class TestIndexRoute:
    """/ ルートのテスト。"""

    async def test_redirect_to_login_when_not_authenticated(
        self, client: AsyncClient
    ) -> None:
        """未認証時は /login にリダイレクトされる。"""
        response = await client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_redirect_to_dashboard_when_authenticated(
        self, authenticated_client: AsyncClient
    ) -> None:
        """認証済みの場合は /dashboard にリダイレクトされる。"""
        response = await authenticated_client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"


# ===========================================================================
# ログインルート
# ===========================================================================


class TestLoginRoutes:
    """ログイン関連ルートのテスト。"""

    async def test_login_page_renders(self, client: AsyncClient) -> None:
        """ログインページが表示される。"""
        response = await client.get("/login")
        assert response.status_code == 200
        assert "Bot Admin" in response.text
        assert "Email" in response.text
        assert "Password" in response.text

    async def test_login_redirects_when_authenticated(
        self, authenticated_client: AsyncClient
    ) -> None:
        """認証済みの場合は /dashboard にリダイレクトされる。"""
        response = await authenticated_client.get("/login", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"

    async def test_login_success(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """正しい認証情報でログインできる。"""
        response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"
        assert "session" in response.cookies

    async def test_login_failure_wrong_password(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """間違ったパスワードでログインに失敗する。"""
        response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": "wrongpassword",
            },
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.text

    async def test_login_failure_wrong_email(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """間違ったユーザー名でログインに失敗する。"""
        response = await client.post(
            "/login",
            data={
                "email": "wronguser",
                "password": TEST_ADMIN_PASSWORD,
            },
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.text

    async def test_login_with_default_admin(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """デフォルトの AdminUser 認証情報でログインできる。"""
        import src.web.app as web_app_module

        # 既知のテスト認証情報を使用
        monkeypatch.setattr(web_app_module, "INIT_ADMIN_EMAIL", "default@example.com")
        monkeypatch.setattr(web_app_module, "INIT_ADMIN_PASSWORD", "defaultpassword")

        response = await client.post(
            "/login",
            data={
                "email": "default@example.com",
                "password": "defaultpassword",
            },
            follow_redirects=False,
        )
        # 認証済み状態で作成されるため、ダッシュボードへ直接リダイレクト
        assert response.status_code == 302
        assert response.headers.get("location") == "/dashboard"

    async def test_login_auto_creates_admin_from_env(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """INIT_ADMIN_PASSWORD が設定されていれば AdminUser が自動作成される。"""
        import src.web.app as web_app_module

        monkeypatch.setattr(web_app_module, "INIT_ADMIN_EMAIL", "env@example.com")
        monkeypatch.setattr(web_app_module, "INIT_ADMIN_PASSWORD", "envpassword123")

        # 正しい認証情報でログイン
        response = await client.post(
            "/login",
            data={
                "email": "env@example.com",
                "password": "envpassword123",
            },
            follow_redirects=False,
        )
        # 認証済み状態で作成されるため、ダッシュボードへ直接リダイレクト
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"
        assert "session" in response.cookies


# ===========================================================================
# ログアウトルート
# ===========================================================================


class TestLogoutRoute:
    """/logout ルートのテスト。"""

    async def test_logout_clears_session(
        self, authenticated_client: AsyncClient
    ) -> None:
        """ログアウトするとセッションがクリアされる。"""
        response = await authenticated_client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"


# ===========================================================================
# ダッシュボードルート
# ===========================================================================


class TestDashboardRoute:
    """/dashboard ルートのテスト。"""

    async def test_dashboard_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_dashboard_renders(self, authenticated_client: AsyncClient) -> None:
        """認証済みの場合はダッシュボードが表示される。"""
        response = await authenticated_client.get("/dashboard")
        assert response.status_code == 200
        assert "Dashboard" in response.text
        assert "Lobbies" in response.text
        assert "Sticky Messages" in response.text
        assert "Bump Reminders" in response.text


# ===========================================================================
# 設定ルート
# ===========================================================================


class TestSettingsRoutes:
    """/settings ルートのテスト。"""

    async def test_settings_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/settings", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_page_renders(
        self, authenticated_client: AsyncClient
    ) -> None:
        """設定ハブページが表示される。"""
        response = await authenticated_client.get("/settings")
        assert response.status_code == 200
        assert "Settings" in response.text
        assert "Change Email" in response.text
        assert "Change Password" in response.text


# ===========================================================================
# ロビールート
# ===========================================================================


class TestLobbiesRoutes:
    """/lobbies ルートのテスト。"""

    async def test_lobbies_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/lobbies", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_lobbies_list_empty(self, authenticated_client: AsyncClient) -> None:
        """ロビーがない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/lobbies")
        assert response.status_code == 200
        assert "No lobbies configured" in response.text

    async def test_lobbies_list_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロビーがある場合は一覧が表示される。"""
        lobby = Lobby(
            guild_id="123456789012345678",
            lobby_channel_id="987654321098765432",
        )
        db_session.add(lobby)
        await db_session.commit()

        response = await authenticated_client.get("/lobbies")
        assert response.status_code == 200
        assert "123456789012345678" in response.text
        assert "987654321098765432" in response.text

    async def test_delete_lobby(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロビーを削除できる。"""
        lobby = Lobby(
            guild_id="123456789012345678",
            lobby_channel_id="987654321098765432",
        )
        db_session.add(lobby)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/lobbies/{lobby.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/lobbies"


# ===========================================================================
# Sticky ルート
# ===========================================================================


class TestStickyRoutes:
    """/sticky ルートのテスト。"""

    async def test_sticky_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/sticky", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_sticky_list_empty(self, authenticated_client: AsyncClient) -> None:
        """Sticky がない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/sticky")
        assert response.status_code == 200
        assert "No sticky messages configured" in response.text

    async def test_sticky_list_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Sticky がある場合は一覧が表示される。"""
        sticky = StickyMessage(
            channel_id="123456789012345678",
            guild_id="987654321098765432",
            title="Test Title",
            description="Test Description",
        )
        db_session.add(sticky)
        await db_session.commit()

        response = await authenticated_client.get("/sticky")
        assert response.status_code == 200
        assert "Test Title" in response.text

    async def test_delete_sticky(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Sticky を削除できる。"""
        sticky = StickyMessage(
            channel_id="123456789012345678",
            guild_id="987654321098765432",
            title="Test",
            description="Test",
        )
        db_session.add(sticky)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/sticky/{sticky.channel_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/sticky"


# ===========================================================================
# Bump ルート
# ===========================================================================


class TestBumpRoutes:
    """/bump ルートのテスト。"""

    async def test_bump_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/bump", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_bump_list_empty(self, authenticated_client: AsyncClient) -> None:
        """Bump 設定がない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/bump")
        assert response.status_code == 200
        assert "No bump configs" in response.text
        assert "No bump reminders" in response.text

    async def test_bump_list_with_config(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Bump Config がある場合は一覧に表示される。"""
        config = BumpConfig(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
        )
        db_session.add(config)
        await db_session.commit()

        response = await authenticated_client.get("/bump")
        assert response.status_code == 200
        assert "123456789012345678" in response.text

    async def test_bump_list_with_reminder(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Bump Reminder がある場合は一覧に表示される。"""
        reminder = BumpReminder(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            service_name="DISBOARD",
        )
        db_session.add(reminder)
        await db_session.commit()

        response = await authenticated_client.get("/bump")
        assert response.status_code == 200
        assert "DISBOARD" in response.text

    async def test_toggle_reminder(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Reminder の有効/無効を切り替えられる。"""
        reminder = BumpReminder(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            service_name="DISBOARD",
            is_enabled=True,
        )
        db_session.add(reminder)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/bump/reminder/{reminder.id}/toggle",
            follow_redirects=False,
        )
        assert response.status_code == 302

    async def test_delete_config(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Config を削除できる。"""
        config = BumpConfig(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
        )
        db_session.add(config)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/bump/config/{config.guild_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    async def test_delete_reminder(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Reminder を削除できる。"""
        reminder = BumpReminder(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            service_name="DISBOARD",
        )
        db_session.add(reminder)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/bump/reminder/{reminder.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302


# ===========================================================================
# レート制限
# ===========================================================================


class TestRateLimiting:
    """レート制限のテスト。"""

    async def test_rate_limit_after_max_attempts(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """最大試行回数を超えるとレート制限がかかる。"""
        # 5回失敗
        for _ in range(5):
            await client.post(
                "/login",
                data={
                    "email": "wrong",
                    "password": "wrong",
                },
            )

        # 6回目はレート制限
        response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
        )
        assert response.status_code == 429
        assert "Too many attempts" in response.text


# ===========================================================================
# パスワードハッシュ
# ===========================================================================


class TestPasswordHashing:
    """パスワードハッシュのテスト。"""

    def test_hash_password_creates_hash(self) -> None:
        """hash_password がハッシュを生成する。"""
        password = "testpassword123"
        hashed = hash_password(password)
        assert hashed != password
        assert hashed.startswith("$2b$")

    def test_different_passwords_different_hashes(self) -> None:
        """異なるパスワードは異なるハッシュになる。"""
        hash1 = hash_password("password1")
        hash2 = hash_password("password2")
        assert hash1 != hash2

    def test_same_password_different_hashes(self) -> None:
        """同じパスワードでも毎回異なるハッシュ (salt)。"""
        password = "testpassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2


# ===========================================================================
# パスワード検証
# ===========================================================================


class TestPasswordVerification:
    """verify_password 関数のテスト。"""

    def test_verify_password_correct(self) -> None:
        """正しいパスワードで True を返す。"""
        from src.web.app import verify_password

        password = "testpassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """間違ったパスワードで False を返す。"""
        from src.web.app import verify_password

        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False


# ===========================================================================
# 設定 (変更なし)
# ===========================================================================


# ===========================================================================
# 存在しないアイテムの削除
# ===========================================================================


class TestDeleteNonExistent:
    """存在しないアイテムの削除テスト。"""

    async def test_delete_nonexistent_lobby(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないロビーの削除はリダイレクトで返る。"""
        response = await authenticated_client.post(
            "/lobbies/99999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/lobbies"

    async def test_delete_nonexistent_sticky(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しない Sticky の削除はリダイレクトで返る。"""
        response = await authenticated_client.post(
            "/sticky/999999999999999999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/sticky"

    async def test_delete_nonexistent_bump_config(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しない BumpConfig の削除はリダイレクトで返る。"""
        response = await authenticated_client.post(
            "/bump/config/999999999999999999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/bump"

    async def test_delete_nonexistent_bump_reminder(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しない BumpReminder の削除はリダイレクトで返る。"""
        response = await authenticated_client.post(
            "/bump/reminder/99999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/bump"

    async def test_toggle_nonexistent_bump_reminder(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しない BumpReminder のトグルはリダイレクトで返る。"""
        response = await authenticated_client.post(
            "/bump/reminder/99999/toggle",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/bump"


# ===========================================================================
# セッションユーティリティ
# ===========================================================================


# ===========================================================================
# 未認証の POST リクエスト
# ===========================================================================


class TestUnauthenticatedGetRequests:
    """認証なしの GET リクエストのテスト。"""

    async def test_initial_setup_get_requires_auth(self, client: AsyncClient) -> None:
        """認証なしで初回セットアップGETは /login にリダイレクトされる。"""
        response = await client.get("/initial-setup", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_email_get_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでメール変更GETは /login にリダイレクトされる。"""
        response = await client.get("/settings/email", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_password_get_requires_auth(
        self, client: AsyncClient
    ) -> None:
        """認証なしでパスワード変更GETは /login にリダイレクトされる。"""
        response = await client.get("/settings/password", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"


class TestUnauthenticatedPostRequests:
    """認証なしの POST リクエストのテスト。"""

    async def test_initial_setup_post_requires_auth(self, client: AsyncClient) -> None:
        """認証なしで初回セットアップは /login にリダイレクトされる。"""
        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "test@example.com",
                "new_password": "password123",
                "confirm_password": "password123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_email_post_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでメール変更は /login にリダイレクトされる。"""
        response = await client.post(
            "/settings/email",
            data={"new_email": "test@example.com"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_password_post_requires_auth(
        self, client: AsyncClient
    ) -> None:
        """認証なしでパスワード変更は /login にリダイレクトされる。"""
        response = await client.post(
            "/settings/password",
            data={"new_password": "password123", "confirm_password": "password123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_resend_verification_requires_auth(self, client: AsyncClient) -> None:
        """認証なしで確認メール再送は /login にリダイレクトされる。"""
        response = await client.post("/resend-verification", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_lobbies_delete_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでロビー削除は /login にリダイレクトされる。"""
        response = await client.post("/lobbies/1/delete", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_sticky_delete_requires_auth(self, client: AsyncClient) -> None:
        """認証なしで Sticky 削除は /login にリダイレクトされる。"""
        response = await client.post("/sticky/123/delete", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_bump_config_delete_requires_auth(self, client: AsyncClient) -> None:
        """認証なしで BumpConfig 削除は /login にリダイレクトされる。"""
        response = await client.post("/bump/config/123/delete", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_bump_reminder_delete_requires_auth(
        self, client: AsyncClient
    ) -> None:
        """認証なしで BumpReminder 削除は /login にリダイレクトされる。"""
        response = await client.post("/bump/reminder/1/delete", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_bump_reminder_toggle_requires_auth(
        self, client: AsyncClient
    ) -> None:
        """認証なしで BumpReminder トグルは /login にリダイレクトされる。"""
        response = await client.post("/bump/reminder/1/toggle", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"


# ===========================================================================
# 初回セットアップフロー
# ===========================================================================


class TestInitialSetupFlow:
    """初回セットアップフローのテスト。"""

    async def test_login_redirects_to_initial_setup(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回ログイン時は /initial-setup にリダイレクトされる。"""
        response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/initial-setup"

    async def test_dashboard_redirects_to_initial_setup(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回セットアップ時は /dashboard から /initial-setup にリダイレクトされる。"""
        # まずログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # ダッシュボードにアクセス
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/initial-setup"

    async def test_initial_setup_page_renders(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回セットアップページが表示される。"""
        # まずログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # 初回セットアップページにアクセス
        response = await client.get("/initial-setup")
        assert response.status_code == 200
        assert "Initial Setup" in response.text
        assert "Email Address" in response.text
        assert "New Password" in response.text

    async def test_initial_setup_success(
        self,
        client: AsyncClient,
        initial_admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """初回セットアップが成功する。"""
        # まずログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # 初回セットアップを実行
        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "newadmin@example.com",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
            follow_redirects=False,
        )
        # SMTP 未設定のため、ダッシュボードへ直接リダイレクト
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"

        # DBが更新されていることを確認
        await db_session.refresh(initial_admin_user)
        # メールアドレスが直接更新される（pending_email ではなく）
        assert initial_admin_user.email == "newadmin@example.com"
        assert initial_admin_user.pending_email is None
        assert initial_admin_user.password_changed_at is not None
        assert initial_admin_user.email_verified is True

    async def test_initial_setup_invalid_email(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回セットアップで無効なメールアドレスはエラー。"""
        # まずログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # 無効なメールアドレスで初回セットアップ
        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "invalid-email",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )
        assert response.status_code == 200
        assert "Invalid email format" in response.text

    async def test_initial_setup_password_mismatch(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回セットアップでパスワード不一致はエラー。"""
        # まずログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # パスワード不一致で初回セットアップ
        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "newadmin@example.com",
                "new_password": "newpassword123",
                "confirm_password": "differentpassword",
            },
        )
        assert response.status_code == 200
        assert "Passwords do not match" in response.text

    async def test_initial_setup_password_too_short(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回セットアップでパスワードが短すぎる場合はエラー。"""
        # まずログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # 短すぎるパスワードで初回セットアップ
        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "newadmin@example.com",
                "new_password": "short",
                "confirm_password": "short",
            },
        )
        assert response.status_code == 200
        assert "at least 8 characters" in response.text


class TestSessionUtilities:
    """セッションユーティリティのテスト。"""

    def test_create_session_token(self) -> None:
        """create_session_token がトークンを生成する。"""
        from src.web.app import create_session_token

        token = create_session_token("test@example.com")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_session_token_valid(self) -> None:
        """有効なトークンを検証できる。"""
        from src.web.app import create_session_token, verify_session_token

        token = create_session_token("test@example.com")
        data = verify_session_token(token)
        assert data is not None
        assert data["authenticated"] is True
        assert data["email"] == "test@example.com"

    def test_verify_session_token_invalid(self) -> None:
        """無効なトークンは None を返す。"""
        from src.web.app import verify_session_token

        data = verify_session_token("invalid_token")
        assert data is None

    def test_get_current_user_no_session(self) -> None:
        """セッションがない場合は None を返す。"""
        from src.web.app import get_current_user

        user = get_current_user(None)
        assert user is None

    def test_get_current_user_invalid_session(self) -> None:
        """無効なセッションは None を返す。"""
        from src.web.app import get_current_user

        user = get_current_user("invalid_token")
        assert user is None

    def test_get_current_user_valid_session(self) -> None:
        """有効なセッションでユーザー情報を取得できる。"""
        from src.web.app import create_session_token, get_current_user

        token = create_session_token("test@example.com")
        user = get_current_user(token)
        assert user is not None
        assert user["email"] == "test@example.com"

    def test_verify_session_token_not_authenticated(self) -> None:
        """authenticated=False のトークンは None を返す。"""
        from src.web.app import serializer, verify_session_token

        # authenticated=False のトークンを作成
        token = serializer.dumps({"authenticated": False, "email": "test@example.com"})
        data = verify_session_token(token)
        assert data is None


# ===========================================================================
# レート制限ユーティリティ
# ===========================================================================


class TestRateLimitingUtilities:
    """レート制限ユーティリティのテスト。"""

    def test_is_rate_limited_new_ip(self) -> None:
        """新規IPはレート制限されていない。"""
        from src.web.app import is_rate_limited

        result = is_rate_limited("192.168.1.100")
        assert result is False

    def test_record_failed_attempt_new_ip(self) -> None:
        """新規IPの失敗を記録できる。"""
        from src.web.app import LOGIN_ATTEMPTS, record_failed_attempt

        record_failed_attempt("192.168.1.101")
        assert "192.168.1.101" in LOGIN_ATTEMPTS
        assert len(LOGIN_ATTEMPTS["192.168.1.101"]) == 1

    def test_is_rate_limited_after_max_attempts(self) -> None:
        """最大試行回数後はレート制限される。"""
        from src.web.app import is_rate_limited, record_failed_attempt

        ip = "192.168.1.102"
        for _ in range(5):
            record_failed_attempt(ip)

        result = is_rate_limited(ip)
        assert result is True


# ===========================================================================
# パスワードリセットルート
# ===========================================================================


class TestForgotPasswordRoutes:
    """パスワードリセット（forgot-password）ルートのテスト。"""

    async def test_forgot_password_page_renders(self, client: AsyncClient) -> None:
        """パスワードリセットページが表示される。"""
        response = await client.get("/forgot-password")
        assert response.status_code == 200
        assert "Reset Password" in response.text
        assert "Email" in response.text

    async def test_forgot_password_with_valid_email(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """SMTP 未設定のため、パスワードリセットは利用不可。"""
        response = await client.post(
            "/forgot-password",
            data={"email": TEST_ADMIN_EMAIL},
        )
        assert response.status_code == 200
        assert "SMTP is not configured" in response.text

    async def test_forgot_password_with_invalid_email(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """SMTP 未設定のため、どのメールアドレスでも同じエラーが表示される。"""
        response = await client.post(
            "/forgot-password",
            data={"email": "nonexistent@example.com"},
        )
        assert response.status_code == 200
        assert "SMTP is not configured" in response.text

    async def test_forgot_password_sets_reset_token(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """SMTP 未設定のため、リセットトークンは生成されない。"""
        await client.post(
            "/forgot-password",
            data={"email": TEST_ADMIN_EMAIL},
        )
        await db_session.refresh(admin_user)
        # SMTP 未設定のためトークンは設定されない
        assert admin_user.reset_token is None
        assert admin_user.reset_token_expires_at is None


class TestResetPasswordRoutes:
    """パスワードリセット（reset-password）ルートのテスト。"""

    async def test_reset_password_page_without_token(self, client: AsyncClient) -> None:
        """トークンなしでアクセスするとエラー。"""
        response = await client.get("/reset-password")
        assert response.status_code == 200
        assert "Invalid or missing reset token" in response.text

    async def test_reset_password_page_with_invalid_token(
        self, client: AsyncClient
    ) -> None:
        """無効なトークンでアクセスするとエラー。"""
        response = await client.get("/reset-password?token=invalid_token")
        assert response.status_code == 200
        assert "Invalid or expired reset token" in response.text

    async def test_reset_password_page_with_valid_token(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """有効なトークンでパスワードリセットページが表示される。"""
        # トークンを設定
        admin_user.reset_token = "valid_test_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        await db_session.commit()

        response = await client.get("/reset-password?token=valid_test_token")
        assert response.status_code == 200
        assert "New Password" in response.text

    async def test_reset_password_with_expired_token(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """期限切れのトークンでアクセスするとエラー。"""
        # 期限切れトークンを設定
        admin_user.reset_token = "expired_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) - timedelta(hours=1)
        await db_session.commit()

        response = await client.get("/reset-password?token=expired_token")
        assert response.status_code == 200
        assert "expired" in response.text

    async def test_reset_password_success(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """パスワードリセットが成功する。"""
        # トークンを設定
        admin_user.reset_token = "reset_test_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        await db_session.commit()

        response = await client.post(
            "/reset-password",
            data={
                "token": "reset_test_token",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )
        assert response.status_code == 200
        # ログインページに戻る
        assert "Bot Admin" in response.text

        # トークンがクリアされている
        await db_session.refresh(admin_user)
        assert admin_user.reset_token is None
        assert admin_user.reset_token_expires_at is None

    async def test_reset_password_mismatch(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """パスワードが一致しない場合はエラー。"""
        admin_user.reset_token = "mismatch_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        await db_session.commit()

        response = await client.post(
            "/reset-password",
            data={
                "token": "mismatch_token",
                "new_password": "password123",
                "confirm_password": "different123",
            },
        )
        assert response.status_code == 200
        assert "Passwords do not match" in response.text

    async def test_reset_password_too_short(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """パスワードが短すぎる場合はエラー。"""
        admin_user.reset_token = "short_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        await db_session.commit()

        response = await client.post(
            "/reset-password",
            data={
                "token": "short_token",
                "new_password": "short",
                "confirm_password": "short",
            },
        )
        assert response.status_code == 200
        assert "at least 8 characters" in response.text

    async def test_reset_password_with_expired_token_post(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """期限切れトークンでPOSTするとエラー。"""
        admin_user.reset_token = "expired_post_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) - timedelta(hours=1)
        await db_session.commit()

        response = await client.post(
            "/reset-password",
            data={
                "token": "expired_post_token",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )
        assert response.status_code == 200
        assert "expired" in response.text


# ===========================================================================
# メールアドレス変更検証ルート
# ===========================================================================


class TestEmailChangeVerification:
    """メールアドレス変更検証のテスト。"""

    async def test_settings_email_page_renders(
        self, authenticated_client: AsyncClient
    ) -> None:
        """メールアドレス変更ページが表示される。"""
        response = await authenticated_client.get("/settings/email")
        assert response.status_code == 200
        assert "Change Email" in response.text

    async def test_settings_email_change_sends_verification(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """SMTP 未設定のため、メールアドレスは直接変更される。"""
        response = await authenticated_client.post(
            "/settings/email",
            data={"new_email": "newemail@example.com"},
            follow_redirects=False,
        )
        # リダイレクトで設定ページに戻る
        assert response.status_code == 302
        assert response.headers["location"] == "/settings"

    async def test_settings_email_same_email_error(
        self, authenticated_client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """同じメールアドレスを入力するとエラー。"""
        response = await authenticated_client.post(
            "/settings/email",
            data={"new_email": admin_user.email},
        )
        assert response.status_code == 200
        assert "different from current" in response.text

    async def test_settings_shows_pending_email(
        self,
        authenticated_client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """保留中のメールアドレス変更が表示される。"""
        # 保留中のメールを設定
        admin_user.pending_email = "pending@example.com"
        admin_user.email_change_token = "test_token"
        admin_user.email_change_token_expires_at = datetime.now(UTC) + timedelta(
            hours=1
        )
        await db_session.commit()

        response = await authenticated_client.get("/settings")
        assert response.status_code == 200
        assert "pending@example.com" in response.text

    async def test_confirm_email_without_token(self, client: AsyncClient) -> None:
        """トークンなしでアクセスするとエラー。"""
        response = await client.get("/confirm-email")
        assert response.status_code == 200
        assert "Invalid or missing confirmation token" in response.text

    async def test_confirm_email_with_invalid_token(self, client: AsyncClient) -> None:
        """無効なトークンでアクセスするとエラー。"""
        response = await client.get("/confirm-email?token=invalid_token")
        assert response.status_code == 200
        assert "Invalid or expired confirmation token" in response.text

    async def test_confirm_email_with_valid_token(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """有効なトークンでメールアドレスが変更される。"""
        # トークンを設定
        admin_user.pending_email = "confirmed@example.com"
        admin_user.email_change_token = "valid_confirm_token"
        admin_user.email_change_token_expires_at = datetime.now(UTC) + timedelta(
            hours=1
        )
        await db_session.commit()

        response = await client.get("/confirm-email?token=valid_confirm_token")
        assert response.status_code == 200

        # メールアドレスが変更され、email_verified が True になっている
        await db_session.refresh(admin_user)
        assert admin_user.email == "confirmed@example.com"
        assert admin_user.email_verified is True
        assert admin_user.pending_email is None
        assert admin_user.email_change_token is None

    async def test_confirm_email_with_expired_token(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """期限切れトークンでアクセスするとエラー。"""
        # 期限切れトークンを設定
        admin_user.pending_email = "expired@example.com"
        admin_user.email_change_token = "expired_confirm_token"
        admin_user.email_change_token_expires_at = datetime.now(UTC) - timedelta(
            hours=1
        )
        await db_session.commit()

        response = await client.get("/confirm-email?token=expired_confirm_token")
        assert response.status_code == 200
        assert "expired" in response.text


class TestEmailVerificationPendingRoutes:
    """メール認証待ちルートのテスト。"""

    async def test_verify_email_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/verify-email", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_verify_email_page_renders(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """メール認証待ちページが表示される。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # メール認証待ちページにアクセス
        response = await client.get("/verify-email")
        assert response.status_code == 200
        assert "Verify Your Email" in response.text
        assert "pending@example.com" in response.text

    async def test_login_redirects_to_verify_email_when_unverified(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """メール未認証の場合は /verify-email にリダイレクトされる。"""
        response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"

    async def test_dashboard_redirects_to_verify_email_when_unverified(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """メール未認証の場合は /dashboard から /verify-email にリダイレクトされる。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # ダッシュボードにアクセス
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"

    async def test_resend_verification_success(
        self,
        client: AsyncClient,
        unverified_admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """確認メール再送が成功する。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # 元のトークンを記録
        original_token = unverified_admin_user.email_change_token

        # 確認メール再送
        response = await client.post("/resend-verification")
        assert response.status_code == 200
        assert "Verification email sent" in response.text

        # 新しいトークンが生成されている
        await db_session.refresh(unverified_admin_user)
        assert unverified_admin_user.email_change_token != original_token

    async def test_verify_email_redirects_to_dashboard_when_verified(
        self, authenticated_client: AsyncClient
    ) -> None:
        """既に認証済みの場合は /dashboard にリダイレクトされる。"""
        response = await authenticated_client.get(
            "/verify-email", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"


class TestPasswordChangeRoutes:
    """パスワード変更ルートのテスト。"""

    async def test_password_change_page_renders(
        self, authenticated_client: AsyncClient
    ) -> None:
        """パスワード変更ページが表示される。"""
        response = await authenticated_client.get("/settings/password")
        assert response.status_code == 200
        assert "Change Password" in response.text

    async def test_password_change_success(
        self, authenticated_client: AsyncClient
    ) -> None:
        """パスワード変更が成功する。"""
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_password_change_mismatch(
        self, authenticated_client: AsyncClient
    ) -> None:
        """パスワードが一致しない場合はエラー。"""
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": "password123",
                "confirm_password": "different123",
            },
        )
        assert response.status_code == 200
        assert "Passwords do not match" in response.text

    async def test_password_change_too_short(
        self, authenticated_client: AsyncClient
    ) -> None:
        """パスワードが短すぎる場合はエラー。"""
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": "short",
                "confirm_password": "short",
            },
        )
        assert response.status_code == 200
        assert "at least 8 characters" in response.text


# ===========================================================================
# Faker を使ったテスト
# ===========================================================================

from faker import Faker  # noqa: E402

fake = Faker()


class TestWebAdminWithFaker:
    """Faker を使ったランダムデータでのテスト。"""

    async def test_login_with_random_credentials_fails(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """ランダムな認証情報ではログインに失敗する。"""
        response = await client.post(
            "/login",
            data={
                "email": fake.email(),
                "password": fake.password(),
            },
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.text

    async def test_change_to_random_email(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Faker で生成したメールアドレスに変更できる（SMTP 未設定のため直接変更）。"""
        new_email = fake.email()
        response = await authenticated_client.post(
            "/settings/email",
            data={"new_email": new_email},
            follow_redirects=False,
        )
        # SMTP 未設定のため、リダイレクトで設定ページに戻る
        assert response.status_code == 302
        assert response.headers["location"] == "/settings"

    async def test_change_to_random_password(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Faker で生成したパスワードに変更できる。"""
        new_password = fake.password(length=12)
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": new_password,
                "confirm_password": new_password,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_invalid_random_email_format_rejected(
        self, authenticated_client: AsyncClient
    ) -> None:
        """不正な形式のメールアドレスは拒否される。"""
        invalid_email = fake.user_name()  # @ がないので不正
        response = await authenticated_client.post(
            "/settings/email",
            data={"new_email": invalid_email},
        )
        assert response.status_code == 200
        assert "Invalid email format" in response.text

    async def test_short_random_password_rejected(
        self, authenticated_client: AsyncClient
    ) -> None:
        """短すぎるパスワードは拒否される。"""
        short_password = fake.password(length=5)
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": short_password,
                "confirm_password": short_password,
            },
        )
        assert response.status_code == 200
        assert "at least 8 characters" in response.text

    async def test_rate_limiting_with_random_ips(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """ランダムIPでのレート制限テスト。"""
        from src.web.app import LOGIN_ATTEMPTS, is_rate_limited, record_failed_attempt

        random_ip = fake.ipv4()
        assert is_rate_limited(random_ip) is False

        for _ in range(5):
            record_failed_attempt(random_ip)

        assert is_rate_limited(random_ip) is True

        # クリーンアップ
        LOGIN_ATTEMPTS.pop(random_ip, None)


# ===========================================================================
# 初回セットアップのエッジケース
# ===========================================================================


class TestInitialSetupEdgeCases:
    """初回セットアップのエッジケーステスト。"""

    async def test_initial_setup_get_redirects_to_dashboard_when_completed(
        self, authenticated_client: AsyncClient
    ) -> None:
        """セットアップ完了済みの場合は /dashboard にリダイレクトされる。"""
        response = await authenticated_client.get(
            "/initial-setup", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"

    async def test_initial_setup_get_redirects_to_verify_email_when_unverified(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """セットアップ完了済みでメール未認証の場合は /verify-email にリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/initial-setup", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"

    async def test_initial_setup_post_empty_email(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """空のメールアドレスはエラー。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "",
                "new_password": "password123",
                "confirm_password": "password123",
            },
        )
        assert response.status_code == 200
        assert "Email address is required" in response.text

    async def test_initial_setup_post_empty_password(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """空のパスワードはエラー。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "valid@example.com",
                "new_password": "",
                "confirm_password": "",
            },
        )
        assert response.status_code == 200
        assert "Password is required" in response.text


# ===========================================================================
# メール認証待ちのエッジケース
# ===========================================================================


class TestVerifyEmailEdgeCases:
    """メール認証待ちのエッジケーステスト。"""

    async def test_verify_email_no_pending_redirects_to_dashboard(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """pending_email がない場合は /dashboard にリダイレクト。"""
        # email_verified を False にしつつ pending_email を None に
        admin_user.email_verified = False
        admin_user.pending_email = None
        await db_session.commit()

        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/verify-email", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"


# ===========================================================================
# 確認メール再送のエッジケース
# ===========================================================================


class TestResendVerificationEdgeCases:
    """確認メール再送のエッジケーステスト。"""

    async def test_resend_verification_no_pending_redirects_to_dashboard(
        self,
        authenticated_client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """pending_email がない場合は /dashboard にリダイレクト。"""
        # pending_email を None に
        admin_user.pending_email = None
        await db_session.commit()

        response = await authenticated_client.post(
            "/resend-verification", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"


# ===========================================================================
# 初回セットアップが必要な設定ルート
# ===========================================================================


class TestSettingsRequiresInitialSetup:
    """設定ルートで初回セットアップが必要なケースのテスト。"""

    async def test_settings_redirects_to_initial_setup(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """/settings は初回セットアップにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/settings", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/initial-setup"

    async def test_settings_redirects_to_verify_email_when_unverified(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """/settings はメール認証待ちにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/settings", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"

    async def test_settings_email_get_redirects_to_initial_setup(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """/settings/email は初回セットアップにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/settings/email", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/initial-setup"

    async def test_settings_email_get_redirects_to_verify_email_when_unverified(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """/settings/email はメール認証待ちにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/settings/email", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"

    async def test_settings_password_get_redirects_to_initial_setup(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """/settings/password は初回セットアップにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/settings/password", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/initial-setup"

    async def test_settings_password_get_redirects_to_verify_email_when_unverified(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """/settings/password はメール認証待ちにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.get("/settings/password", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"

    async def test_settings_password_post_redirects_to_initial_setup(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """POST /settings/password は初回セットアップにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.post(
            "/settings/password",
            data={
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/initial-setup"

    async def test_settings_password_post_redirects_to_verify_email(
        self, client: AsyncClient, unverified_admin_user: AdminUser
    ) -> None:
        """POST /settings/password はメール認証待ちにリダイレクト。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.post(
            "/settings/password",
            data={
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/verify-email"


# ===========================================================================
# メール変更 POST のエッジケース
# ===========================================================================


class TestSettingsEmailPostEdgeCases:
    """メール変更POSTのエッジケーステスト。"""

    async def test_settings_email_post_empty_email(
        self, authenticated_client: AsyncClient
    ) -> None:
        """空のメールアドレスはエラー。"""
        response = await authenticated_client.post(
            "/settings/email",
            data={"new_email": ""},
        )
        assert response.status_code == 200
        assert "Email address is required" in response.text


# ===========================================================================
# パスワード変更 POST のエッジケース
# ===========================================================================


class TestSettingsPasswordPostEdgeCases:
    """パスワード変更POSTのエッジケーステスト。"""

    async def test_settings_password_post_empty_password(
        self, authenticated_client: AsyncClient
    ) -> None:
        """空のパスワードはエラー。"""
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": "",
                "confirm_password": "",
            },
        )
        assert response.status_code == 200
        assert "Password is required" in response.text


# ===========================================================================
# パスワードリセット POST のエッジケース
# ===========================================================================


class TestResetPasswordPostEdgeCases:
    """パスワードリセットPOSTのエッジケーステスト。"""

    async def test_reset_password_post_invalid_token(self, client: AsyncClient) -> None:
        """無効なトークンでPOSTするとエラー。"""
        response = await client.post(
            "/reset-password",
            data={
                "token": "invalid_token_for_post",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
        )
        assert response.status_code == 200
        assert "Invalid or expired reset token" in response.text

    async def test_reset_password_post_password_too_long(
        self, client: AsyncClient, admin_user: AdminUser, db_session: AsyncSession
    ) -> None:
        """パスワードが長すぎる場合（72バイト超）はエラー。"""
        admin_user.reset_token = "long_pw_token"
        admin_user.reset_token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        await db_session.commit()

        # 72バイトを超えるパスワード
        long_password = "a" * 80
        response = await client.post(
            "/reset-password",
            data={
                "token": "long_pw_token",
                "new_password": long_password,
                "confirm_password": long_password,
            },
        )
        assert response.status_code == 200
        assert "at most 72 bytes" in response.text


# ===========================================================================
# パスワードが長すぎる場合のテスト
# ===========================================================================


class TestPasswordTooLong:
    """パスワードが72バイトを超える場合のテスト。"""

    async def test_initial_setup_password_too_long(
        self, client: AsyncClient, initial_admin_user: AdminUser
    ) -> None:
        """初回セットアップでパスワードが72バイトを超えるとエラー。"""
        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        # 72バイトを超えるパスワード
        long_password = "a" * 80
        response = await client.post(
            "/initial-setup",
            data={
                "new_email": "newadmin@example.com",
                "new_password": long_password,
                "confirm_password": long_password,
            },
        )
        assert response.status_code == 200
        assert "at most 72 bytes" in response.text

    async def test_settings_password_change_password_too_long(
        self, authenticated_client: AsyncClient
    ) -> None:
        """パスワード変更で72バイトを超えるパスワードはエラー。"""
        long_password = "a" * 80
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": long_password,
                "confirm_password": long_password,
            },
        )
        assert response.status_code == 200
        assert "at most 72 bytes" in response.text


# ===========================================================================
# hash_password の長いパスワードテスト
# ===========================================================================


class TestHashPasswordLong:
    """hash_password で長いパスワードのテスト。"""

    def test_hash_password_truncates_long_password(self) -> None:
        """72バイトを超えるパスワードは切り詰められてハッシュ化される。"""
        from src.web.app import hash_password

        long_password = "a" * 100
        hashed = hash_password(long_password)
        # ハッシュが生成される
        assert hashed.startswith("$2b$")


# ===========================================================================
# verify_password のエッジケース
# ===========================================================================


class TestVerifyPasswordEdgeCases:
    """verify_password のエッジケーステスト。"""

    def test_verify_password_empty_password(self) -> None:
        """空のパスワードは False を返す。"""
        from src.web.app import verify_password

        assert verify_password("", "some_hash") is False

    def test_verify_password_empty_hash(self) -> None:
        """空のハッシュは False を返す。"""
        from src.web.app import verify_password

        assert verify_password("password", "") is False

    def test_verify_password_invalid_hash_format(self) -> None:
        """無効なハッシュ形式は False を返す。"""
        from src.web.app import verify_password

        assert verify_password("password", "not_a_valid_bcrypt_hash") is False


# ===========================================================================
# verify_session_token のエッジケース
# ===========================================================================


class TestVerifySessionTokenEdgeCases:
    """verify_session_token のエッジケーステスト。"""

    def test_verify_session_token_empty_string(self) -> None:
        """空文字列は None を返す。"""
        from src.web.app import verify_session_token

        assert verify_session_token("") is None

    def test_verify_session_token_whitespace(self) -> None:
        """空白のみのトークンは None を返す。"""
        from src.web.app import verify_session_token

        assert verify_session_token("   ") is None


# ===========================================================================
# レート制限クリーンアップのテスト
# ===========================================================================


class TestRateLimitCleanup:
    """レート制限クリーンアップのテスト。"""

    def test_cleanup_removes_old_entries(self) -> None:
        """古いエントリがクリーンアップされる。"""
        import time

        import src.web.app as web_app_module
        from src.web.app import (
            LOGIN_ATTEMPTS,
            _cleanup_old_rate_limit_entries,
        )

        # 古いタイムスタンプを設定（5分以上前）
        old_time = time.time() - 400
        test_ip = "10.0.0.1"
        LOGIN_ATTEMPTS[test_ip] = [old_time]

        # 強制的にクリーンアップを実行
        web_app_module._last_cleanup_time = 0
        _cleanup_old_rate_limit_entries()

        # 古いIPが削除されている
        assert test_ip not in LOGIN_ATTEMPTS

    def test_cleanup_keeps_valid_entries(self) -> None:
        """有効なエントリは保持される。"""
        import time

        import src.web.app as web_app_module
        from src.web.app import (
            LOGIN_ATTEMPTS,
            _cleanup_old_rate_limit_entries,
        )

        # 新しいタイムスタンプを設定
        test_ip = "10.0.0.2"
        LOGIN_ATTEMPTS[test_ip] = [time.time()]

        # 強制的にクリーンアップを実行
        web_app_module._last_cleanup_time = 0
        _cleanup_old_rate_limit_entries()

        # 新しいIPは保持される
        assert test_ip in LOGIN_ATTEMPTS

        # クリーンアップ
        LOGIN_ATTEMPTS.pop(test_ip, None)


# ===========================================================================
# record_failed_attempt のエッジケース
# ===========================================================================


class TestRecordFailedAttemptEdgeCases:
    """record_failed_attempt のエッジケーステスト。"""

    def test_record_failed_attempt_empty_ip(self) -> None:
        """空のIPは記録されない。"""
        from src.web.app import LOGIN_ATTEMPTS, record_failed_attempt

        initial_count = len(LOGIN_ATTEMPTS)
        record_failed_attempt("")
        assert len(LOGIN_ATTEMPTS) == initial_count


# ===========================================================================
# admin が None の場合のテスト
# ===========================================================================


class TestAdminNoneScenarios:
    """admin が None の場合のテスト。"""

    async def test_login_admin_none(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ログイン時に admin が None の場合はエラー。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        # get_or_create_admin を None を返すようにモック
        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await client.post(
            "/login",
            data={
                "email": "test@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 500
        assert "ADMIN_PASSWORD not configured" in response.text

    async def test_initial_setup_get_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """初回セットアップGETで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        # get_or_create_admin を None を返すようにモック
        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.get(
            "/initial-setup", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_initial_setup_post_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """初回セットアップPOSTで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.post(
            "/initial-setup",
            data={
                "new_email": "new@example.com",
                "new_password": "password123",
                "confirm_password": "password123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_verify_email_get_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """verify-email GETで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.get(
            "/verify-email", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_resend_verification_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resend-verification で admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.post(
            "/resend-verification", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_get_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings GETで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.get("/settings", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_email_get_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings/email GETで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.get(
            "/settings/email", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_email_post_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings/email POSTで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.post(
            "/settings/email",
            data={"new_email": "new@example.com"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_password_get_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings/password GETで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.get(
            "/settings/password", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_settings_password_post_admin_none(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings/password POSTで admin が None の場合はリダイレクト。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"


# ===========================================================================
# resend_verification でメール送信失敗のテスト
# ===========================================================================


class TestDashboardAdminNone:
    """dashboard で admin が None の場合のテスト。"""

    async def test_dashboard_admin_none_shows_page(
        self, authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ダッシュボードで admin が None の場合でもページが表示される。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        # get_or_create_admin を None を返すようにモック
        monkeypatch.setattr(
            web_app_module, "get_or_create_admin", AsyncMock(return_value=None)
        )

        response = await authenticated_client.get("/dashboard")
        assert response.status_code == 200
        assert "Dashboard" in response.text


class TestResendVerificationEmailFailure:
    """確認メール再送でメール送信失敗のテスト。"""

    async def test_resend_verification_email_send_fails(
        self,
        client: AsyncClient,
        unverified_admin_user: AdminUser,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """メール送信が失敗した場合はエラーメッセージが表示される。"""
        import src.web.app as web_app_module

        # メール送信を失敗させる
        monkeypatch.setattr(
            web_app_module,
            "send_email_change_verification",
            lambda _email, _token: False,
        )

        # ログイン
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        session_cookie = login_response.cookies.get("session")
        if session_cookie:
            client.cookies.set("session", session_cookie)

        response = await client.post("/resend-verification")
        assert response.status_code == 200
        assert "Failed to send verification email" in response.text


# ===========================================================================
# ロールパネルルート
# ===========================================================================


class TestRolePanelsRoutes:
    """/rolepanels ルートのテスト。"""

    async def test_rolepanels_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/rolepanels", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_rolepanels_list_empty(
        self, authenticated_client: AsyncClient
    ) -> None:
        """ロールパネルがない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "No role panels" in response.text

    async def test_rolepanels_list_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロールパネルがある場合は一覧が表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Role Panel",
        )
        db_session.add(panel)
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "Test Role Panel" in response.text
        assert "123456789012345678" in response.text

    async def test_rolepanels_list_with_items(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロールパネルにアイテムがある場合は表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Panel with Items",
        )
        db_session.add(panel)
        await db_session.flush()

        item = RolePanelItem(
            panel_id=panel.id,
            role_id="111111111111111111",
            emoji="🎮",
            label="Gamer",
            style="primary",
        )
        db_session.add(item)
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "Panel with Items" in response.text
        assert "🎮" in response.text
        assert "Gamer" in response.text

    async def test_delete_rolepanel(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロールパネルを削除できる。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="To Delete",
        )
        db_session.add(panel)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/rolepanels"

    async def test_delete_nonexistent_rolepanel(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないロールパネルの削除はリダイレクトで返る。"""
        response = await authenticated_client.post(
            "/rolepanels/99999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/rolepanels"

    async def test_rolepanels_delete_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでロールパネル削除は /login にリダイレクトされる。"""
        response = await client.post("/rolepanels/1/delete", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_rolepanels_shows_reaction_type(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """リアクション式パネルのバッジが表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Reaction Panel",
        )
        db_session.add(panel)
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "Reaction Panel" in response.text
        assert "Reaction" in response.text

    async def test_rolepanels_shows_auto_remove_badge(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """リアクション自動削除バッジが表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Auto Remove Panel",
            remove_reaction=True,
        )
        db_session.add(panel)
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "Auto-remove" in response.text

    async def test_rolepanels_list_contains_create_button(
        self, authenticated_client: AsyncClient
    ) -> None:
        """一覧ページに Create ボタンが含まれる。"""
        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "/rolepanels/new" in response.text
        assert "Create Panel" in response.text


# ===========================================================================
# Role Panel Create ルート
# ===========================================================================


class TestRolePanelCreateRoutes:
    """/rolepanels/new ルートのテスト。"""

    async def test_create_page_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/rolepanels/new", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_create_page_shows_form(
        self, authenticated_client: AsyncClient
    ) -> None:
        """認証済みでフォームが表示される。"""
        response = await authenticated_client.get("/rolepanels/new")
        assert response.status_code == 200
        assert 'action="/rolepanels/new"' in response.text
        assert 'name="guild_id"' in response.text
        assert 'name="channel_id"' in response.text
        assert 'name="panel_type"' in response.text
        assert 'name="title"' in response.text

    async def test_create_post_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123",
                "channel_id": "456",
                "panel_type": "button",
                "title": "Test",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_create_success(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """パネルを正常に作成できる。"""
        # Form data with array fields
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "New Test Panel",
            "description": "Test description",
            "item_emoji[]": "🎮",
            "item_role_id[]": "111222333444555666",
            "item_label[]": "Gamer",
            "item_position[]": "0",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/rolepanels/" in response.headers["location"]

        # DB にパネルが作成されていることを確認
        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "New Test Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.guild_id == "123456789012345678"
        assert panel.channel_id == "987654321098765432"
        assert panel.panel_type == "button"
        assert panel.description == "Test description"
        assert panel.use_embed is True  # Default value

        # ロールアイテムも作成されていることを確認
        items_result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        items = list(items_result.scalars().all())
        assert len(items) == 1
        assert items[0].emoji == "🎮"
        assert items[0].role_id == "111222333444555666"
        assert items[0].label == "Gamer"

    async def test_create_reaction_type(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """リアクション式パネルを作成できる。"""
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "reaction",
            "title": "Reaction Panel",
            "item_emoji[]": "⭐",
            "item_role_id[]": "222333444555666777",
            "item_label[]": "",
            "item_position[]": "0",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Reaction Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.panel_type == "reaction"

    async def test_create_with_use_embed_true(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """use_embed=1 でパネルを作成するとuse_embed=Trueになる。"""
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "Embed Panel",
            "use_embed": "1",
            "item_emoji[]": "🎮",
            "item_role_id[]": "111222333444555666",
            "item_label[]": "Test",
            "item_position[]": "0",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Embed Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.use_embed is True

    async def test_create_with_use_embed_false(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """use_embed=0 でパネルを作成するとuse_embed=Falseになる。"""
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "Text Panel",
            "use_embed": "0",
            "item_emoji[]": "🎵",
            "item_role_id[]": "222333444555666777",
            "item_label[]": "Music",
            "item_position[]": "0",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Text Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.use_embed is False

    async def test_create_missing_guild_id(
        self, authenticated_client: AsyncClient
    ) -> None:
        """guild_id が空の場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
            },
        )
        assert response.status_code == 200
        assert "Guild ID is required" in response.text

    async def test_create_invalid_guild_id(
        self, authenticated_client: AsyncClient
    ) -> None:
        """guild_id が数字でない場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "not_a_number",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
            },
        )
        assert response.status_code == 200
        assert "Guild ID must be a number" in response.text

    async def test_create_missing_channel_id(
        self, authenticated_client: AsyncClient
    ) -> None:
        """channel_id が空の場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "",
                "panel_type": "button",
                "title": "Test",
            },
        )
        assert response.status_code == 200
        assert "Channel ID is required" in response.text

    async def test_create_invalid_channel_id(
        self, authenticated_client: AsyncClient
    ) -> None:
        """channel_id が数字でない場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "not_a_number",
                "panel_type": "button",
                "title": "Test",
            },
        )
        assert response.status_code == 200
        assert "Channel ID must be a number" in response.text

    async def test_create_invalid_panel_type(
        self, authenticated_client: AsyncClient
    ) -> None:
        """panel_type が不正な場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "invalid",
                "title": "Test",
            },
        )
        assert response.status_code == 200
        assert "Invalid panel type" in response.text

    async def test_create_missing_title(
        self, authenticated_client: AsyncClient
    ) -> None:
        """title が空の場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "",
            },
        )
        assert response.status_code == 200
        assert "Title is required" in response.text

    async def test_create_title_too_long(
        self, authenticated_client: AsyncClient
    ) -> None:
        """title が長すぎる場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "x" * 257,
            },
        )
        assert response.status_code == 200
        assert "Title must be 256 characters or less" in response.text

    async def test_create_description_too_long(
        self, authenticated_client: AsyncClient
    ) -> None:
        """description が長すぎる場合はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
                "description": "x" * 4097,
            },
        )
        assert response.status_code == 200
        assert "Description must be 4096 characters or less" in response.text

    async def test_create_preserves_input_on_error(
        self, authenticated_client: AsyncClient
    ) -> None:
        """エラー時に入力値が保持される。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "reaction",
                "title": "",  # Empty title causes error
                "description": "Test desc",
            },
        )
        assert response.status_code == 200
        assert "123456789012345678" in response.text
        assert "987654321098765432" in response.text
        assert "Test desc" in response.text

    async def test_create_without_description(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """description なしでパネルを作成できる。"""
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "No Description Panel",
            "description": "",
            "item_emoji[]": "🎉",
            "item_role_id[]": "333444555666777888",
            "item_label[]": "",
            "item_position[]": "0",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "No Description Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.description is None


# ===========================================================================
# Discord ロールキャッシュ関連
# ===========================================================================


class TestGetDiscordRolesByGuild:
    """_get_discord_roles_by_guild ヘルパー関数のテスト。"""

    async def test_returns_empty_dict_when_no_roles(
        self, db_session: AsyncSession
    ) -> None:
        """ロールがない場合は空の辞書を返す。"""
        from src.web.app import _get_discord_roles_by_guild

        result = await _get_discord_roles_by_guild(db_session)
        assert result == {}

    async def test_returns_roles_grouped_by_guild(
        self, db_session: AsyncSession
    ) -> None:
        """ロールがギルドごとにグループ化される。"""
        from src.web.app import _get_discord_roles_by_guild

        # ギルド1のロール
        db_session.add(
            DiscordRole(
                guild_id="111",
                role_id="1",
                role_name="Role A",
                color=0xFF0000,
                position=10,
            )
        )
        db_session.add(
            DiscordRole(
                guild_id="111",
                role_id="2",
                role_name="Role B",
                color=0x00FF00,
                position=5,
            )
        )
        # ギルド2のロール
        db_session.add(
            DiscordRole(
                guild_id="222",
                role_id="3",
                role_name="Role C",
                color=0x0000FF,
                position=1,
            )
        )
        await db_session.commit()

        result = await _get_discord_roles_by_guild(db_session)

        assert "111" in result
        assert "222" in result
        assert len(result["111"]) == 2
        assert len(result["222"]) == 1

    async def test_roles_sorted_by_position_descending(
        self, db_session: AsyncSession
    ) -> None:
        """ロールが position 降順でソートされる。"""
        from src.web.app import _get_discord_roles_by_guild

        # 位置順序がバラバラなロールを追加
        db_session.add(
            DiscordRole(
                guild_id="123",
                role_id="1",
                role_name="Low",
                position=1,
            )
        )
        db_session.add(
            DiscordRole(
                guild_id="123",
                role_id="2",
                role_name="High",
                position=10,
            )
        )
        db_session.add(
            DiscordRole(
                guild_id="123",
                role_id="3",
                role_name="Medium",
                position=5,
            )
        )
        await db_session.commit()

        result = await _get_discord_roles_by_guild(db_session)

        roles = result["123"]
        # position 降順 (High > Medium > Low)
        assert roles[0][1] == "High"
        assert roles[1][1] == "Medium"
        assert roles[2][1] == "Low"

    async def test_returns_correct_tuple_format(self, db_session: AsyncSession) -> None:
        """(role_id, role_name, color) のタプル形式で返される。"""
        from src.web.app import _get_discord_roles_by_guild

        db_session.add(
            DiscordRole(
                guild_id="123",
                role_id="456",
                role_name="Gamer",
                color=0xFF00FF,
                position=5,
            )
        )
        await db_session.commit()

        result = await _get_discord_roles_by_guild(db_session)

        role_tuple = result["123"][0]
        assert role_tuple == ("456", "Gamer", 0xFF00FF)


class TestRolePanelCreatePageWithDiscordRoles:
    """Discord ロールを含むパネル作成ページのテスト。"""

    async def test_create_page_includes_discord_roles(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """パネル作成ページに Discord ロール情報が含まれる。"""
        # ロールを追加
        db_session.add(
            DiscordRole(
                guild_id="123456789012345678",
                role_id="111222333444555666",
                role_name="Test Role",
                color=0xFF0000,
                position=5,
            )
        )
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels/new")
        assert response.status_code == 200
        # JavaScript 用 JSON にロール情報が含まれる
        assert '"name": "Test Role"' in response.text


class TestRolePanelDetailPageWithDiscordRoles:
    """Discord ロールを含むパネル詳細ページのテスト。"""

    async def test_detail_page_shows_role_names(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """パネル詳細ページでロール名が表示される。"""
        # パネルを作成
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # ロールアイテムを追加
        item = RolePanelItem(
            panel_id=panel.id,
            role_id="111222333444555666",
            emoji="🎮",
            label="Gamer",
            position=0,
        )
        db_session.add(item)

        # ロールキャッシュを追加
        role = DiscordRole(
            guild_id="123456789012345678",
            role_id="111222333444555666",
            role_name="Gamer Role",
            color=0x00FF00,
            position=5,
        )
        db_session.add(role)
        await db_session.commit()

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        # ロール名が表示される
        assert "@Gamer Role" in response.text

    async def test_detail_page_shows_role_select(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """パネル詳細ページでロール選択セレクトボックスが表示される。"""
        # パネルを作成
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)

        # ロールキャッシュを追加
        role = DiscordRole(
            guild_id="123456789012345678",
            role_id="111222333444555666",
            role_name="Available Role",
            color=0xFF0000,
            position=5,
        )
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        # セレクトボックスにロールが表示される
        assert "@Available Role" in response.text
        assert 'id="role_select"' in response.text

    async def test_detail_page_disables_add_button_when_no_roles(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """ロールがない場合は Add Role Item ボタンが非活性。"""
        # パネルのみ作成 (ロールキャッシュなし)
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        # ボタンが非活性
        assert "disabled" in response.text
        assert "No roles found for this guild" in response.text

    async def test_detail_page_shows_role_id_when_not_in_cache(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにないロールはロール ID のみ表示される。"""
        # パネルを作成
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # キャッシュにないロール ID でアイテムを追加
        item = RolePanelItem(
            panel_id=panel.id,
            role_id="999888777666555444",  # キャッシュにない ID
            emoji="🎮",
            label="Unknown Role",
            position=0,
        )
        db_session.add(item)
        await db_session.commit()

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        # ロール ID がそのまま表示される（ロール名ではなく）
        assert "999888777666555444" in response.text

    async def test_detail_page_shows_role_with_zero_color(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """color=0 のロールが正しく表示される。"""
        # パネルを作成
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)

        # color=0 のロール
        role = DiscordRole(
            guild_id="123456789012345678",
            role_id="111222333444555666",
            role_name="Default Color Role",
            color=0,  # デフォルト色
            position=5,
        )
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        assert "@Default Color Role" in response.text


class TestGetDiscordRolesByGuildEdgeCases:
    """_get_discord_roles_by_guild のエッジケーステスト。"""

    async def test_returns_roles_with_zero_color(
        self, db_session: AsyncSession
    ) -> None:
        """color=0 のロールが正しく取得される。"""
        from src.web.app import _get_discord_roles_by_guild

        db_session.add(
            DiscordRole(
                guild_id="123",
                role_id="456",
                role_name="No Color",
                color=0,
                position=5,
            )
        )
        await db_session.commit()

        result = await _get_discord_roles_by_guild(db_session)

        role_tuple = result["123"][0]
        assert role_tuple == ("456", "No Color", 0)

    async def test_returns_multiple_guilds_independently(
        self, db_session: AsyncSession
    ) -> None:
        """複数ギルドのロールが独立して取得される。"""
        from src.web.app import _get_discord_roles_by_guild

        # ギルド1
        db_session.add(
            DiscordRole(
                guild_id="111",
                role_id="1",
                role_name="Guild1 Role",
                position=10,
            )
        )
        # ギルド2
        db_session.add(
            DiscordRole(
                guild_id="222",
                role_id="2",
                role_name="Guild2 Role",
                position=5,
            )
        )
        await db_session.commit()

        result = await _get_discord_roles_by_guild(db_session)

        assert len(result) == 2
        assert len(result["111"]) == 1
        assert len(result["222"]) == 1
        assert result["111"][0][1] == "Guild1 Role"
        assert result["222"][0][1] == "Guild2 Role"

    async def test_handles_unicode_role_names(self, db_session: AsyncSession) -> None:
        """Unicode 文字を含むロール名が正しく取得される。"""
        from src.web.app import _get_discord_roles_by_guild

        db_session.add(
            DiscordRole(
                guild_id="123",
                role_id="456",
                role_name="日本語ロール 🎮",
                position=5,
            )
        )
        await db_session.commit()

        result = await _get_discord_roles_by_guild(db_session)

        assert result["123"][0][1] == "日本語ロール 🎮"


class TestGetDiscordGuildsAndChannels:
    """_get_discord_guilds_and_channels のテスト。"""

    async def test_returns_guilds_sorted_by_name(self, db_session: AsyncSession) -> None:
        """ギルドが名前順でソートされて返される。"""
        from src.web.app import _get_discord_guilds_and_channels

        # 順不同で追加
        db_session.add(DiscordGuild(guild_id="3", guild_name="Zebra Server"))
        db_session.add(DiscordGuild(guild_id="1", guild_name="Alpha Server"))
        db_session.add(DiscordGuild(guild_id="2", guild_name="Middle Server"))
        await db_session.commit()

        guilds_map, _ = await _get_discord_guilds_and_channels(db_session)

        # dict なので順序は保証されないが、値が正しいことを確認
        assert len(guilds_map) == 3
        assert guilds_map["1"] == "Alpha Server"
        assert guilds_map["2"] == "Middle Server"
        assert guilds_map["3"] == "Zebra Server"

    async def test_returns_channels_grouped_by_guild(
        self, db_session: AsyncSession
    ) -> None:
        """チャンネルがギルドごとにグループ化されて返される。"""
        from src.web.app import _get_discord_guilds_and_channels

        db_session.add(DiscordGuild(guild_id="111", guild_name="Guild A"))
        db_session.add(DiscordGuild(guild_id="222", guild_name="Guild B"))
        db_session.add(
            DiscordChannel(
                guild_id="111", channel_id="1", channel_name="general", position=0
            )
        )
        db_session.add(
            DiscordChannel(
                guild_id="111", channel_id="2", channel_name="random", position=1
            )
        )
        db_session.add(
            DiscordChannel(
                guild_id="222", channel_id="3", channel_name="announcements", position=0
            )
        )
        await db_session.commit()

        _, channels_map = await _get_discord_guilds_and_channels(db_session)

        assert len(channels_map) == 2
        assert len(channels_map["111"]) == 2
        assert len(channels_map["222"]) == 1

    async def test_returns_channels_sorted_by_position(
        self, db_session: AsyncSession
    ) -> None:
        """チャンネルが position 順でソートされて返される。"""
        from src.web.app import _get_discord_guilds_and_channels

        db_session.add(DiscordGuild(guild_id="123", guild_name="Test Guild"))
        # 順不同で追加
        db_session.add(
            DiscordChannel(
                guild_id="123", channel_id="3", channel_name="last-channel", position=10
            )
        )
        db_session.add(
            DiscordChannel(
                guild_id="123", channel_id="1", channel_name="first-channel", position=0
            )
        )
        db_session.add(
            DiscordChannel(
                guild_id="123", channel_id="2", channel_name="middle-channel", position=5
            )
        )
        await db_session.commit()

        _, channels_map = await _get_discord_guilds_and_channels(db_session)

        channels = channels_map["123"]
        assert channels[0][1] == "first-channel"
        assert channels[1][1] == "middle-channel"
        assert channels[2][1] == "last-channel"

    async def test_returns_empty_when_no_data(self, db_session: AsyncSession) -> None:
        """データがない場合は空の辞書を返す。"""
        from src.web.app import _get_discord_guilds_and_channels

        guilds_map, channels_map = await _get_discord_guilds_and_channels(db_session)

        assert guilds_map == {}
        assert channels_map == {}


class TestRolePanelCreatePageWithGuildChannelNames:
    """ギルド・チャンネル名を含むパネル作成ページのテスト。"""

    async def test_create_page_shows_guild_names(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """パネル作成ページにギルド名が表示される。"""
        db_session.add(
            DiscordGuild(guild_id="123456789012345678", guild_name="My Test Server")
        )
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels/new")
        assert response.status_code == 200
        # セレクトボックスにギルド名が含まれる
        assert "My Test Server" in response.text

    async def test_create_page_shows_channel_names(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """パネル作成ページにチャンネル名が表示される。"""
        db_session.add(
            DiscordGuild(guild_id="123456789012345678", guild_name="My Test Server")
        )
        db_session.add(
            DiscordChannel(
                guild_id="123456789012345678",
                channel_id="987654321098765432",
                channel_name="general-chat",
                position=0,
            )
        )
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels/new")
        assert response.status_code == 200
        # JavaScript 用 JSON にチャンネル名が含まれる
        assert "general-chat" in response.text


class TestRolePanelDetailPageWithGuildChannelNames:
    """ギルド・チャンネル名を含むパネル詳細ページのテスト。"""

    async def test_detail_page_shows_guild_name(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """パネル詳細ページにギルド名が表示される。"""
        # パネルを作成
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        # ギルドキャッシュを追加
        db_session.add(
            DiscordGuild(guild_id="123456789012345678", guild_name="Cached Server Name")
        )
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        # ギルド名が表示される
        assert "Cached Server Name" in response.text

    async def test_detail_page_shows_channel_name(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """パネル詳細ページにチャンネル名が表示される。"""
        # パネルを作成
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        # チャンネルキャッシュを追加
        db_session.add(
            DiscordGuild(guild_id="123456789012345678", guild_name="Test Server")
        )
        db_session.add(
            DiscordChannel(
                guild_id="123456789012345678",
                channel_id="987654321098765432",
                channel_name="cached-channel",
                position=0,
            )
        )
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        # チャンネル名が表示される (#付き)
        assert "#cached-channel" in response.text

    async def test_detail_page_shows_guild_id_when_not_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにないギルドはギルド ID のみ表示される。"""
        # パネルを作成 (ギルドキャッシュなし)
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        # ギルド ID がそのまま表示される
        assert "123456789012345678" in response.text

    async def test_detail_page_shows_channel_id_when_not_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにないチャンネルはチャンネル ID のみ表示される。"""
        # パネルを作成 (チャンネルキャッシュなし)
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        # ギルドだけキャッシュ
        db_session.add(
            DiscordGuild(guild_id="123456789012345678", guild_name="Test Server")
        )
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        # チャンネル ID がそのまま表示される
        assert "987654321098765432" in response.text


class TestRolePanelReactionTypeEdgeCases:
    """リアクション式パネルのエッジケーステスト。"""

    async def test_reaction_panel_hides_label_column(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """リアクション式パネルでは Label カラムが表示されない。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",  # リアクション式
            title="Reaction Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        item = RolePanelItem(
            panel_id=panel.id,
            role_id="111222333444555666",
            emoji="🎮",
            label="This should not show",
            position=0,
        )
        db_session.add(item)
        await db_session.commit()

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        # Label カラムヘッダーがない
        assert '<th class="py-3 px-4 text-left">Label</th>' not in response.text
        # Add Role フォームにも Label フィールドがない
        assert 'for="label"' not in response.text

    async def test_reaction_panel_shows_purple_badge(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """リアクション式パネルには紫色のバッジが表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Reaction Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        assert "bg-purple-600" in response.text
        assert "Reaction" in response.text

    async def test_button_panel_shows_blue_badge(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """ボタン式パネルには青色のバッジが表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Button Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        assert "bg-blue-600" in response.text
        assert "Button" in response.text


# ===========================================================================
# Role Panel Item Add ルート 結合テスト
# ===========================================================================


class TestRolePanelItemAddRoutes:
    """/rolepanels/{panel_id}/items/add ルートの結合テスト。"""

    async def test_add_item_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.post(
            "/rolepanels/1/items/add",
            data={"emoji": "🎮", "role_id": "123", "label": "Test"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_add_item_to_nonexistent_panel(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないパネルへのアイテム追加はリダイレクト。"""
        response = await authenticated_client.post(
            "/rolepanels/99999/items/add",
            data={"emoji": "🎮", "role_id": "123", "label": "Test"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/rolepanels"

    async def test_add_item_success(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロールアイテムを正常に追加できる。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={
                "emoji": "🎮",
                "role_id": "111222333444555666",
                "label": "Gamer",
                "position": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/rolepanels/{panel.id}" in response.headers["location"]
        assert "success=Role+item+added" in response.headers["location"]

        # DB にアイテムが追加されていることを確認
        result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        items = list(result.scalars().all())
        assert len(items) == 1
        assert items[0].emoji == "🎮"
        assert items[0].role_id == "111222333444555666"
        assert items[0].label == "Gamer"

    async def test_add_item_missing_emoji(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Emoji が空の場合はエラー。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={"emoji": "", "role_id": "123", "label": "Test"},
        )
        assert response.status_code == 200
        assert "Emoji is required" in response.text

    async def test_add_item_invalid_emoji(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """不正な Emoji の場合はエラー。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={"emoji": "invalid", "role_id": "123", "label": "Test"},
        )
        assert response.status_code == 200
        assert "Invalid emoji" in response.text

    async def test_add_item_missing_role_id(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Role ID が空の場合はエラー。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={"emoji": "🎮", "role_id": "", "label": "Test"},
        )
        assert response.status_code == 200
        assert "Role ID is required" in response.text

    async def test_add_item_invalid_role_id(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Role ID が数字でない場合はエラー。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={"emoji": "🎮", "role_id": "not_a_number", "label": "Test"},
        )
        assert response.status_code == 200
        assert "Role ID must be a number" in response.text

    async def test_add_item_duplicate_emoji(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """重複する Emoji の場合はエラー。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # 既存のアイテムを追加
        existing_item = RolePanelItem(
            panel_id=panel.id,
            role_id="111222333444555666",
            emoji="🎮",
            label="Existing",
            position=0,
        )
        db_session.add(existing_item)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={"emoji": "🎮", "role_id": "999888777", "label": "New"},
        )
        assert response.status_code == 200
        assert "already used" in response.text

    async def test_add_item_emoji_too_long(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Emoji が長すぎる場合はエラー。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={"emoji": "x" * 65, "role_id": "123", "label": "Test"},
        )
        assert response.status_code == 200
        assert "64 characters or less" in response.text

    async def test_add_item_label_too_long(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Label が長すぎる場合はエラー。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={"emoji": "🎮", "role_id": "123", "label": "x" * 81},
        )
        assert response.status_code == 200
        assert "80 characters or less" in response.text

    async def test_add_item_without_label(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Label なしでアイテムを追加できる。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Reaction Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={
                "emoji": "⭐",
                "role_id": "111222333444555666",
                "label": "",
                "position": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        item = result.scalar_one()
        assert item.label is None


# ===========================================================================
# Role Panel Item Delete ルート 結合テスト
# ===========================================================================


class TestRolePanelItemDeleteRoutes:
    """/rolepanels/{panel_id}/items/{item_id}/delete ルートの結合テスト。"""

    async def test_delete_item_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.post(
            "/rolepanels/1/items/1/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_delete_item_from_nonexistent_panel(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないパネルからの削除はリダイレクト。"""
        response = await authenticated_client.post(
            "/rolepanels/99999/items/1/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/rolepanels"

    async def test_delete_nonexistent_item(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """存在しないアイテムの削除はリダイレクト (エラーなし)。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/99999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/rolepanels/{panel.id}" in response.headers["location"]

    async def test_delete_item_success(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロールアイテムを正常に削除できる。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        item = RolePanelItem(
            panel_id=panel.id,
            role_id="111222333444555666",
            emoji="🎮",
            label="Gamer",
            position=0,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)
        item_id = item.id

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/{item_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/rolepanels/{panel.id}" in response.headers["location"]
        assert "success=Role+item+deleted" in response.headers["location"]

        # DB からアイテムが削除されていることを確認
        result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.id == item_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_item_from_wrong_panel(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """異なるパネルのアイテム削除は無視される。"""
        # パネル1を作成
        panel1 = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Panel 1",
        )
        db_session.add(panel1)
        # パネル2を作成
        panel2 = RolePanel(
            guild_id="123456789012345678",
            channel_id="111222333444555666",
            panel_type="button",
            title="Panel 2",
        )
        db_session.add(panel2)
        await db_session.commit()
        await db_session.refresh(panel1)
        await db_session.refresh(panel2)

        # パネル1にアイテムを追加
        item = RolePanelItem(
            panel_id=panel1.id,
            role_id="111222333444555666",
            emoji="🎮",
            label="Gamer",
            position=0,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)
        item_id = item.id

        # パネル2のURLでパネル1のアイテムを削除しようとする
        response = await authenticated_client.post(
            f"/rolepanels/{panel2.id}/items/{item_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

        # アイテムは削除されていないことを確認
        result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.id == item_id)
        )
        assert result.scalar_one_or_none() is not None


# ===========================================================================
# Role Panel エンドツーエンド 結合テスト
# ===========================================================================


class TestRolePanelEndToEnd:
    """ロールパネルのエンドツーエンド結合テスト。"""

    async def test_create_panel_then_add_item(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """パネル作成後にアイテムを追加できる。"""
        # パネルを作成 (最低1つのアイテムが必要)
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "Test Panel",
            "item_emoji[]": "⭐",
            "item_role_id[]": "000111222333444555",
            "item_label[]": "Initial",
            "item_position[]": "0",
        }
        create_response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert create_response.status_code == 302

        # 作成されたパネルを取得
        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Test Panel")
        )
        panel = result.scalar_one()

        # アイテムを追加
        add_response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={
                "emoji": "🎮",
                "role_id": "111222333444555666",
                "label": "Gamer",
                "position": "1",
            },
            follow_redirects=False,
        )
        assert add_response.status_code == 302

        # アイテムが追加されたことを確認 (作成時の1つ + 追加の1つ = 2つ)
        items_result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        items = list(items_result.scalars().all())
        assert len(items) == 2
        assert any(item.emoji == "🎮" for item in items)

    async def test_add_then_delete_item(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """アイテムを追加してから削除できる。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # アイテムを追加
        add_response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={
                "emoji": "🎮",
                "role_id": "111222333444555666",
                "label": "Gamer",
                "position": "0",
            },
            follow_redirects=False,
        )
        assert add_response.status_code == 302

        # 追加されたアイテムを取得
        items_result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        item = items_result.scalar_one()

        # アイテムを削除
        delete_response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/{item.id}/delete",
            follow_redirects=False,
        )
        assert delete_response.status_code == 302

        # アイテムが削除されたことを確認
        items_result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        items = list(items_result.scalars().all())
        assert len(items) == 0

    async def test_create_panel_with_multiple_items_delete_one(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """複数アイテム付きパネル作成後、1つだけ削除できる。"""
        # パネルを直接 DB に作成
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Multi-item Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # 3つのアイテムを追加
        items_data = [
            ("🎮", "111222333444555666", "Gamer", 0),
            ("⭐", "222333444555666777", "Star", 1),
            ("🎵", "333444555666777888", "Music", 2),
        ]
        for emoji, role_id, label, pos in items_data:
            item = RolePanelItem(
                panel_id=panel.id,
                role_id=role_id,
                emoji=emoji,
                label=label,
                position=pos,
            )
            db_session.add(item)
        await db_session.commit()

        # 3つのアイテムがあることを確認
        items_result = await db_session.execute(
            select(RolePanelItem)
            .where(RolePanelItem.panel_id == panel.id)
            .order_by(RolePanelItem.position)
        )
        items = list(items_result.scalars().all())
        assert len(items) == 3

        # 真ん中のアイテム (Star) を削除
        star_item = next(i for i in items if i.emoji == "⭐")
        delete_response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/{star_item.id}/delete",
            follow_redirects=False,
        )
        assert delete_response.status_code == 302

        # 2つのアイテムが残っていることを確認
        items_result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        remaining_items = list(items_result.scalars().all())
        assert len(remaining_items) == 2
        remaining_emojis = {i.emoji for i in remaining_items}
        assert remaining_emojis == {"🎮", "🎵"}

    async def test_delete_panel_cascades_items(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """パネル削除時にアイテムもカスケード削除される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Cascade Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # アイテムを追加
        item1 = RolePanelItem(panel_id=panel.id, role_id="111", emoji="🎮", position=0)
        item2 = RolePanelItem(panel_id=panel.id, role_id="222", emoji="⭐", position=1)
        db_session.add(item1)
        db_session.add(item2)
        await db_session.commit()

        panel_id = panel.id

        # パネルを削除
        delete_response = await authenticated_client.post(
            f"/rolepanels/{panel_id}/delete",
            follow_redirects=False,
        )
        assert delete_response.status_code == 302

        # アイテムも削除されていることを確認
        items_result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel_id)
        )
        items = list(items_result.scalars().all())
        assert len(items) == 0

    async def test_detail_page_shows_added_item(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """詳細ページに追加したアイテムが表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # アイテムを追加
        add_response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={
                "emoji": "🎮",
                "role_id": "111222333444555666",
                "label": "Gamer",
                "position": "0",
            },
            follow_redirects=False,
        )
        assert add_response.status_code == 302

        # 詳細ページを取得
        detail_response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert detail_response.status_code == 200
        assert "🎮" in detail_response.text
        assert "Gamer" in detail_response.text

    async def test_list_page_shows_item_count(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """一覧ページにアイテム数が表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Itemized Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # アイテムを3つ追加
        for i, emoji in enumerate(["🎮", "⭐", "🎵"]):
            item = RolePanelItem(
                panel_id=panel.id,
                role_id=f"11122233344455566{i}",
                emoji=emoji,
                position=i,
            )
            db_session.add(item)
        await db_session.commit()

        # 一覧ページを取得
        list_response = await authenticated_client.get("/rolepanels")
        assert list_response.status_code == 200
        assert "Itemized Panel" in list_response.text
        # アイテム数 (絵文字) が表示される
        assert "🎮" in list_response.text

    async def test_add_custom_discord_emoji(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Discord カスタム絵文字でアイテムを追加できる。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        custom_emoji = "<:custom:123456789012345678>"
        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={
                "emoji": custom_emoji,
                "role_id": "111222333444555666",
                "label": "Custom Role",
                "position": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        # アイテムが追加されたことを確認
        result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        item = result.scalar_one()
        assert item.emoji == custom_emoji
