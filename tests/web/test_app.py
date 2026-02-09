"""Tests for web admin application routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants import BCRYPT_MAX_PASSWORD_BYTES, LOGIN_MAX_ATTEMPTS
from src.database.models import (
    AdminUser,
    AutoBanConfig,
    AutoBanLog,
    AutoBanRule,
    BanLog,
    BumpConfig,
    BumpReminder,
    DiscordChannel,
    DiscordGuild,
    DiscordRole,
    JoinRoleConfig,
    Lobby,
    RolePanel,
    RolePanelItem,
    StickyMessage,
    Ticket,
    TicketCategory,
    TicketPanel,
    TicketPanelCategory,
)
from src.utils import is_valid_emoji
from src.web.app import (
    _cleanup_form_cooldown_entries,
    _cleanup_old_rate_limit_entries,
    hash_password,
    is_form_cooldown_active,
    is_rate_limited,
    record_failed_attempt,
    record_form_submit,
    verify_password,
)

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
# ギルド・チャンネル名表示 (一覧ページ)
# ===========================================================================


class TestLobbiesListWithGuildChannelNames:
    """ロビー一覧ページのギルド・チャンネル名表示テスト。"""

    async def test_displays_guild_name_when_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにギルド名がある場合、サーバー名が表示される。"""
        # ロビーとギルド情報を作成
        lobby = Lobby(
            guild_id="123456789012345678",
            lobby_channel_id="987654321098765432",
        )
        guild = DiscordGuild(
            guild_id="123456789012345678",
            guild_name="My Test Server",
        )
        db_session.add_all([lobby, guild])
        await db_session.commit()

        response = await authenticated_client.get("/lobbies")
        assert response.status_code == 200
        assert "My Test Server" in response.text
        # ID もグレーで表示される
        assert "123456789012345678" in response.text

    async def test_displays_channel_name_when_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにチャンネル名がある場合、チャンネル名が表示される。"""
        lobby = Lobby(
            guild_id="123456789012345678",
            lobby_channel_id="987654321098765432",
        )
        channel = DiscordChannel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            channel_name="lobby-voice",
            position=0,
        )
        db_session.add_all([lobby, channel])
        await db_session.commit()

        response = await authenticated_client.get("/lobbies")
        assert response.status_code == 200
        assert "#lobby-voice" in response.text

    async def test_displays_yellow_id_when_not_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにない場合、ID が黄色で表示される。"""
        lobby = Lobby(
            guild_id="123456789012345678",
            lobby_channel_id="987654321098765432",
        )
        db_session.add(lobby)
        await db_session.commit()

        response = await authenticated_client.get("/lobbies")
        assert response.status_code == 200
        # 黄色スタイルで ID 表示
        assert "text-yellow-400" in response.text


class TestStickyListWithGuildChannelNames:
    """Sticky 一覧ページのギルド・チャンネル名表示テスト。"""

    async def test_displays_guild_name_when_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにギルド名がある場合、サーバー名が表示される。"""
        sticky = StickyMessage(
            channel_id="987654321098765432",
            guild_id="123456789012345678",
            title="Test Sticky",
            description="Test",
        )
        guild = DiscordGuild(
            guild_id="123456789012345678",
            guild_name="Sticky Server",
        )
        db_session.add_all([sticky, guild])
        await db_session.commit()

        response = await authenticated_client.get("/sticky")
        assert response.status_code == 200
        assert "Sticky Server" in response.text

    async def test_displays_channel_name_when_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにチャンネル名がある場合、チャンネル名が表示される。"""
        sticky = StickyMessage(
            channel_id="987654321098765432",
            guild_id="123456789012345678",
            title="Test Sticky",
            description="Test",
        )
        channel = DiscordChannel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            channel_name="announcements",
            position=0,
        )
        db_session.add_all([sticky, channel])
        await db_session.commit()

        response = await authenticated_client.get("/sticky")
        assert response.status_code == 200
        assert "#announcements" in response.text

    async def test_displays_yellow_id_when_not_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにない場合、ID が黄色で表示される。"""
        sticky = StickyMessage(
            channel_id="987654321098765432",
            guild_id="123456789012345678",
            title="Test Sticky",
            description="Test",
        )
        db_session.add(sticky)
        await db_session.commit()

        response = await authenticated_client.get("/sticky")
        assert response.status_code == 200
        assert "text-yellow-400" in response.text


class TestBumpListWithGuildChannelNames:
    """Bump 一覧ページのギルド・チャンネル名表示テスト。"""

    async def test_config_displays_guild_name_when_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Config でキャッシュにギルド名がある場合、サーバー名が表示される。"""
        config = BumpConfig(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
        )
        guild = DiscordGuild(
            guild_id="123456789012345678",
            guild_name="Bump Server",
        )
        db_session.add_all([config, guild])
        await db_session.commit()

        response = await authenticated_client.get("/bump")
        assert response.status_code == 200
        assert "Bump Server" in response.text

    async def test_config_displays_channel_name_when_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Config でキャッシュにチャンネル名がある場合、チャンネル名が表示される。"""
        config = BumpConfig(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
        )
        channel = DiscordChannel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            channel_name="bump-channel",
            position=0,
        )
        db_session.add_all([config, channel])
        await db_session.commit()

        response = await authenticated_client.get("/bump")
        assert response.status_code == 200
        assert "#bump-channel" in response.text

    async def test_reminder_displays_guild_name_when_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Reminder でキャッシュにギルド名がある場合、サーバー名が表示される。"""
        reminder = BumpReminder(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            service_name="DISBOARD",
        )
        guild = DiscordGuild(
            guild_id="123456789012345678",
            guild_name="Reminder Server",
        )
        db_session.add_all([reminder, guild])
        await db_session.commit()

        response = await authenticated_client.get("/bump")
        assert response.status_code == 200
        assert "Reminder Server" in response.text

    async def test_reminder_displays_channel_name_when_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Reminder でキャッシュにチャンネル名がある場合、チャンネル名が表示される。"""
        reminder = BumpReminder(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            service_name="DISBOARD",
        )
        channel = DiscordChannel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            channel_name="reminder-channel",
            position=0,
        )
        db_session.add_all([reminder, channel])
        await db_session.commit()

        response = await authenticated_client.get("/bump")
        assert response.status_code == 200
        assert "#reminder-channel" in response.text

    async def test_displays_yellow_id_when_not_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにない場合、ID が黄色で表示される。"""
        config = BumpConfig(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
        )
        db_session.add(config)
        await db_session.commit()

        response = await authenticated_client.get("/bump")
        assert response.status_code == 200
        assert "text-yellow-400" in response.text


class TestRolePanelsListWithGuildChannelNames:
    """ロールパネル一覧ページのギルド・チャンネル名表示テスト。"""

    async def test_displays_guild_name_when_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにギルド名がある場合、サーバー名が表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        guild = DiscordGuild(
            guild_id="123456789012345678",
            guild_name="Panel Server",
        )
        db_session.add_all([panel, guild])
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "Panel Server" in response.text

    async def test_displays_channel_name_when_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにチャンネル名がある場合、チャンネル名が表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        channel = DiscordChannel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            channel_name="roles-channel",
            position=0,
        )
        db_session.add_all([panel, channel])
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "#roles-channel" in response.text

    async def test_displays_yellow_id_when_not_cached(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュにない場合、ID が黄色で表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "text-yellow-400" in response.text

    async def test_displays_both_guild_and_channel_names(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """ギルド名とチャンネル名の両方がある場合、両方表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        guild = DiscordGuild(
            guild_id="123456789012345678",
            guild_name="Full Server",
        )
        channel = DiscordChannel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            channel_name="full-channel",
            position=0,
        )
        db_session.add_all([panel, guild, channel])
        await db_session.commit()

        response = await authenticated_client.get("/rolepanels")
        assert response.status_code == 200
        assert "Full Server" in response.text
        assert "#full-channel" in response.text
        # ID はグレーで表示
        assert "text-gray-500" in response.text


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
# 絵文字検証
# ===========================================================================


class TestEmojiValidation:
    """is_valid_emoji 関数のテスト。"""

    def test_simple_emoji_valid(self) -> None:
        """シンプルな絵文字は有効。"""
        assert is_valid_emoji("😀") is True
        assert is_valid_emoji("🎮") is True
        assert is_valid_emoji("❤️") is True
        assert is_valid_emoji("⭐") is True

    def test_zwj_family_emoji_valid(self) -> None:
        """ZWJ シーケンスの家族絵文字は有効。"""
        assert is_valid_emoji("🧑‍🧑‍🧒") is True  # family
        assert is_valid_emoji("👨‍👩‍👧") is True  # man woman girl
        assert is_valid_emoji("👩‍👩‍👦‍👦") is True  # woman woman boy boy

    def test_zwj_profession_emoji_valid(self) -> None:
        """ZWJ シーケンスの職業絵文字は有効。"""
        assert is_valid_emoji("👨‍💻") is True  # man technologist
        assert is_valid_emoji("👩‍🎨") is True  # woman artist
        assert is_valid_emoji("🧑‍🚀") is True  # astronaut

    def test_keycap_emoji_valid(self) -> None:
        """Keycap 絵文字は有効。"""
        assert is_valid_emoji("1️⃣") is True
        assert is_valid_emoji("2️⃣") is True
        assert is_valid_emoji("3️⃣") is True
        assert is_valid_emoji("0️⃣") is True
        assert is_valid_emoji("#️⃣") is True
        assert is_valid_emoji("*️⃣") is True

    def test_flag_emoji_valid(self) -> None:
        """国旗絵文字は有効。"""
        assert is_valid_emoji("🇯🇵") is True
        assert is_valid_emoji("🇺🇸") is True
        assert is_valid_emoji("🇬🇧") is True

    def test_skin_tone_emoji_valid(self) -> None:
        """肌の色修飾子付き絵文字は有効。"""
        assert is_valid_emoji("👋🏻") is True  # light skin tone
        assert is_valid_emoji("👋🏿") is True  # dark skin tone
        assert is_valid_emoji("🧑🏽‍💻") is True  # medium skin technologist

    def test_discord_custom_emoji_valid(self) -> None:
        """Discord カスタム絵文字は有効。"""
        assert is_valid_emoji("<:custom:123456789>") is True
        assert is_valid_emoji("<a:animated:987654321>") is True

    def test_empty_string_invalid(self) -> None:
        """空文字は無効。"""
        assert is_valid_emoji("") is False

    def test_regular_text_invalid(self) -> None:
        """通常テキストは無効。"""
        assert is_valid_emoji("hello") is False
        assert is_valid_emoji("abc123") is False
        assert is_valid_emoji("!@#") is False

    def test_multiple_emojis_invalid(self) -> None:
        """複数絵文字は無効 (単一絵文字のみ許可)。"""
        assert is_valid_emoji("😀😀") is False
        assert is_valid_emoji("🎮🎵") is False

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_none_input_invalid(self) -> None:
        """None 入力は無効。"""
        assert is_valid_emoji(None) is False  # type: ignore[arg-type]

    def test_whitespace_only_invalid(self) -> None:
        """空白のみは無効。"""
        assert is_valid_emoji("   ") is False
        assert is_valid_emoji("\t") is False
        assert is_valid_emoji("\n") is False

    def test_emoji_with_whitespace_invalid(self) -> None:
        """絵文字＋空白は無効。"""
        assert is_valid_emoji(" 😀") is False  # leading space
        assert is_valid_emoji("😀 ") is False  # trailing space
        assert is_valid_emoji(" 😀 ") is False  # both

    def test_emoji_with_text_invalid(self) -> None:
        """絵文字＋テキストは無効。"""
        assert is_valid_emoji("😀hello") is False
        assert is_valid_emoji("hello😀") is False
        assert is_valid_emoji("a😀b") is False

    def test_discord_custom_emoji_invalid_formats(self) -> None:
        """Discord カスタム絵文字の不正フォーマットは無効。"""
        assert is_valid_emoji("<:custom>") is False  # missing id
        assert is_valid_emoji("<:name:>") is False  # empty id
        assert is_valid_emoji("<::123>") is False  # empty name
        assert is_valid_emoji("<custom:123>") is False  # missing colon prefix
        assert is_valid_emoji(":custom:123") is False  # missing angle brackets

    def test_partial_flag_invalid(self) -> None:
        """不完全な国旗 (regional indicator 単体) は無効。"""
        assert is_valid_emoji("🇯") is False  # Just J, not JP

    def test_text_vs_emoji_style(self) -> None:
        """テキストスタイルと絵文字スタイル両方有効。"""
        assert is_valid_emoji("☺") is True  # text style (no variation selector)
        assert is_valid_emoji("☺️") is True  # emoji style (with variation selector)

    def test_component_emojis_valid(self) -> None:
        """コンポーネント絵文字 (Discord でリアクションとして使用可)。"""
        # These are component emojis but Discord accepts them
        assert is_valid_emoji("🏻") is True  # skin tone modifier (light)
        assert is_valid_emoji("🦰") is True  # red hair component

    def test_special_unicode_invalid(self) -> None:
        """特殊 Unicode 文字 (絵文字ではない) は無効。"""
        assert is_valid_emoji("\u200d") is False  # ZWJ alone
        assert is_valid_emoji("\ufe0f") is False  # variation selector alone
        assert is_valid_emoji("\u20e3") is False  # combining enclosing keycap alone

    def test_control_characters_invalid(self) -> None:
        """制御文字を含む文字列は無効。"""
        assert is_valid_emoji("😀\n") is False  # emoji with newline
        assert is_valid_emoji("\n😀") is False  # newline before emoji
        assert is_valid_emoji("😀\r") is False  # emoji with carriage return
        assert is_valid_emoji("😀\t") is False  # emoji with tab
        assert is_valid_emoji("\x00😀") is False  # null character
        assert is_valid_emoji("😀\x1f") is False  # unit separator

    def test_lone_surrogate_invalid(self) -> None:
        """壊れたサロゲートペアは無効。"""
        # Note: Python 3 は通常壊れたサロゲートを許可しないが、
        # surrogateescape エラーハンドラで作られた文字列等で発生する可能性
        # ここでは正常な文字列のみテスト
        # 実際の壊れたサロゲートは _has_lone_surrogate でテスト
        pass  # 正常な Python 文字列では壊れたサロゲートを作成できない

    def test_emoji_family_zwj_sequence(self) -> None:
        """家族の ZWJ シーケンスが正しく処理される。"""
        # 🧑‍🧑‍🧒 = 🧑 + ZWJ + 🧑 + ZWJ + 🧒
        assert is_valid_emoji("🧑‍🧑‍🧒") is True


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


class TestWebStateIsolation:
    """autouse fixture によるステート分離が機能することを検証するカナリアテスト."""

    def test_login_attempts_starts_empty(self) -> None:
        """各テスト開始時に LOGIN_ATTEMPTS が空であることを検証."""
        from src.web.app import LOGIN_ATTEMPTS

        assert len(LOGIN_ATTEMPTS) == 0

    def test_form_submit_times_starts_empty(self) -> None:
        """各テスト開始時に FORM_SUBMIT_TIMES が空であることを検証."""
        from src.web.app import FORM_SUBMIT_TIMES

        assert len(FORM_SUBMIT_TIMES) == 0

    def test_cleanup_times_are_reset(self) -> None:
        """各テスト開始時にクリーンアップ時刻がリセットされていることを検証."""
        import src.web.app as web_app_module

        assert web_app_module._last_cleanup_time == 0.0
        assert web_app_module._form_cooldown_last_cleanup_time == 0.0


class TestRateLimitCleanup:
    """レート制限クリーンアップのテスト。"""

    def test_cleanup_removes_old_entries(self) -> None:
        """古いエントリがクリーンアップされる。"""
        import time

        import src.web.app as web_app_module
        from src.web.app import (
            LOGIN_ATTEMPTS,
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

    def test_cleanup_guard_allows_zero_last_time(self) -> None:
        """_last_cleanup_time=0 でもクリーンアップが実行される.

        0 は「未実行」として扱われクリーンアップがスキップされないことを検証。
        """
        import time

        import src.web.app as web_app_module
        from src.web.app import LOGIN_ATTEMPTS

        test_ip = "10.0.0.99"
        LOGIN_ATTEMPTS[test_ip] = [time.time() - 400]

        web_app_module._last_cleanup_time = 0
        _cleanup_old_rate_limit_entries()

        assert test_ip not in LOGIN_ATTEMPTS
        assert web_app_module._last_cleanup_time > 0

    def test_cleanup_interval_respected(self) -> None:
        """クリーンアップ間隔が未経過ならスキップされる."""
        import time

        import src.web.app as web_app_module
        from src.web.app import LOGIN_ATTEMPTS

        test_ip = "10.0.0.88"
        LOGIN_ATTEMPTS[test_ip] = [time.time() - 400]

        # 最終クリーンアップを最近に設定 (間隔未経過)
        web_app_module._last_cleanup_time = time.time() - 1
        _cleanup_old_rate_limit_entries()

        # 間隔未経過なのでエントリはまだ残る
        assert test_ip in LOGIN_ATTEMPTS
        LOGIN_ATTEMPTS.pop(test_ip, None)

    def test_cleanup_keeps_active_removes_expired(self) -> None:
        """期限切れエントリは削除、アクティブは保持."""
        import time

        import src.web.app as web_app_module
        from src.web.app import LOGIN_ATTEMPTS

        expired_ip = "10.0.0.77"
        active_ip = "10.0.0.66"
        LOGIN_ATTEMPTS[expired_ip] = [time.time() - 400]
        LOGIN_ATTEMPTS[active_ip] = [time.time()]

        web_app_module._last_cleanup_time = 0
        _cleanup_old_rate_limit_entries()

        assert expired_ip not in LOGIN_ATTEMPTS
        assert active_ip in LOGIN_ATTEMPTS
        LOGIN_ATTEMPTS.pop(active_ip, None)


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
        # アイテム数のみ表示される（個別の絵文字やラベルは非表示）
        assert "1 role(s)" in response.text

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
        panel_id = panel.id

        response = await authenticated_client.post(
            f"/rolepanels/{panel_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/rolepanels"

        # パネルがデータベースから削除されていることを確認
        result = await db_session.execute(
            select(RolePanel).where(RolePanel.id == panel_id)
        )
        deleted_panel = result.scalar_one_or_none()
        assert deleted_panel is None

    async def test_delete_rolepanel_with_message_deletes_discord_message(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """投稿済みパネル削除時に Discord メッセージも削除される。"""
        from unittest.mock import patch

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Posted Panel",
            message_id="111111111111111111",
        )
        db_session.add(panel)
        await db_session.commit()
        panel_id = panel.id

        with patch(
            "src.web.app.delete_discord_message", return_value=(True, None)
        ) as mock_delete:
            response = await authenticated_client.post(
                f"/rolepanels/{panel_id}/delete",
                follow_redirects=False,
            )

        assert response.status_code == 302
        mock_delete.assert_called_once_with("987654321098765432", "111111111111111111")

        # DB からも削除されている
        result = await db_session.execute(
            select(RolePanel).where(RolePanel.id == panel_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_rolepanel_without_message_skips_discord(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """未投稿パネル削除時は Discord API を呼ばない。"""
        from unittest.mock import patch

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Draft Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        panel_id = panel.id

        with patch(
            "src.web.app.delete_discord_message", return_value=(True, None)
        ) as mock_delete:
            response = await authenticated_client.post(
                f"/rolepanels/{panel_id}/delete",
                follow_redirects=False,
            )

        assert response.status_code == 302
        mock_delete.assert_not_called()

    async def test_delete_rolepanel_discord_failure_still_deletes_db(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Discord メッセージ削除が失敗しても DB からは削除される。"""
        from unittest.mock import patch

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Posted Panel",
            message_id="111111111111111111",
        )
        db_session.add(panel)
        await db_session.commit()
        panel_id = panel.id

        with patch(
            "src.web.app.delete_discord_message",
            return_value=(False, "Missing Permissions"),
        ):
            response = await authenticated_client.post(
                f"/rolepanels/{panel_id}/delete",
                follow_redirects=False,
            )

        assert response.status_code == 302

        # Discord 削除が失敗しても DB からは削除される
        result = await db_session.execute(
            select(RolePanel).where(RolePanel.id == panel_id)
        )
        assert result.scalar_one_or_none() is None

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

    async def test_create_with_color(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """color を指定してパネルを作成できる。"""
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "Colored Panel",
            "use_embed": "1",
            "color": "#FF5733",
            "item_emoji[]": "🎨",
            "item_role_id[]": "111222333444555666",
            "item_label[]": "Artist",
            "item_position[]": "0",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Colored Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.color == 0xFF5733  # 16724787 in decimal

    async def test_create_with_color_without_hash(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """color を # なしで指定しても正しく保存される。"""
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "Colored Panel No Hash",
            "use_embed": "1",
            "color": "00FF00",
            "item_emoji[]": "🌿",
            "item_role_id[]": "111222333444555666",
            "item_label[]": "Nature",
            "item_position[]": "0",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Colored Panel No Hash")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.color == 0x00FF00

    async def test_create_with_color_ignored_when_text_format(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """use_embed=0 の場合、color は無視される (None になる)。"""
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "Text Panel With Color",
            "use_embed": "0",
            "color": "#FF0000",
            "item_emoji[]": "📝",
            "item_role_id[]": "111222333444555666",
            "item_label[]": "Writer",
            "item_position[]": "0",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Text Panel With Color")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.color is None

    async def test_create_with_invalid_color_uses_none(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """無効な color はNoneになる。"""
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "Invalid Color Panel",
            "use_embed": "1",
            "color": "invalid",
            "item_emoji[]": "❓",
            "item_role_id[]": "111222333444555666",
            "item_label[]": "Unknown",
            "item_position[]": "0",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Invalid Color Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.color is None

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

    async def test_create_preserves_role_items_on_error(
        self, authenticated_client: AsyncClient
    ) -> None:
        """バリデーションエラー時にロールアイテムが保持される。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "reaction",
                "title": "",  # Empty title causes error
                "item_emoji[]": "🎮",
                "item_role_id[]": "111222333444555666",
                "item_label[]": "Gamer",
                "item_style[]": "primary",
                "item_position[]": "0",
            },
        )
        assert response.status_code == 200
        assert "Title is required" in response.text
        # ロールアイテムが existingItems JSON に保持される
        assert '"role_id": "111222333444555666"' in response.text
        assert '"label": "Gamer"' in response.text

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

    async def test_create_with_multiple_role_items(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """複数のロールアイテムを同時に作成できる。"""
        form_data = [
            ("guild_id", "123456789012345678"),
            ("channel_id", "987654321098765432"),
            ("panel_type", "button"),
            ("title", "Multi Role Panel"),
            ("item_emoji[]", "🎮"),
            ("item_role_id[]", "111222333444555666"),
            ("item_label[]", "Gamer"),
            ("item_position[]", "0"),
            ("item_emoji[]", "🎵"),
            ("item_role_id[]", "222333444555666777"),
            ("item_label[]", "Music"),
            ("item_position[]", "1"),
            ("item_emoji[]", "🎨"),
            ("item_role_id[]", "333444555666777888"),
            ("item_label[]", "Artist"),
            ("item_position[]", "2"),
        ]
        response = await authenticated_client.post(
            "/rolepanels/new",
            content=urlencode(form_data),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Multi Role Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None

        items_result = await db_session.execute(
            select(RolePanelItem)
            .where(RolePanelItem.panel_id == panel.id)
            .order_by(RolePanelItem.position)
        )
        items = list(items_result.scalars().all())
        assert len(items) == 3

        assert items[0].emoji == "🎮"
        assert items[0].label == "Gamer"
        assert items[0].position == 0

        assert items[1].emoji == "🎵"
        assert items[1].label == "Music"
        assert items[1].position == 1

        assert items[2].emoji == "🎨"
        assert items[2].label == "Artist"
        assert items[2].position == 2

    async def test_create_with_duplicate_emoji_error(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """同じ絵文字を複数のアイテムに使用するとエラー。"""
        form_data = [
            ("guild_id", "123456789012345678"),
            ("channel_id", "987654321098765432"),
            ("panel_type", "button"),
            ("title", "Duplicate Emoji Panel"),
            ("item_emoji[]", "🎮"),
            ("item_role_id[]", "111222333444555666"),
            ("item_label[]", "First"),
            ("item_position[]", "0"),
            ("item_emoji[]", "🎮"),  # 同じ絵文字
            ("item_role_id[]", "222333444555666777"),
            ("item_label[]", "Second"),
            ("item_position[]", "1"),
        ]
        response = await authenticated_client.post(
            "/rolepanels/new",
            content=urlencode(form_data),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Duplicate emoji" in response.text

        # パネルが作成されていないことを確認
        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Duplicate Emoji Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is None

    async def test_create_with_custom_item_positions(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロールアイテムのposition順序が保持される。"""
        # 意図的に順番を変えて送信 (position: 2, 0, 1 の順で送る)
        form_data = [
            ("guild_id", "123456789012345678"),
            ("channel_id", "987654321098765432"),
            ("panel_type", "button"),
            ("title", "Custom Order Panel"),
            ("item_emoji[]", "🔴"),
            ("item_role_id[]", "333333333333333333"),
            ("item_label[]", "Third"),
            ("item_position[]", "2"),
            ("item_emoji[]", "🟢"),
            ("item_role_id[]", "111111111111111111"),
            ("item_label[]", "First"),
            ("item_position[]", "0"),
            ("item_emoji[]", "🔵"),
            ("item_role_id[]", "222222222222222222"),
            ("item_label[]", "Second"),
            ("item_position[]", "1"),
        ]
        response = await authenticated_client.post(
            "/rolepanels/new",
            content=urlencode(form_data),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Custom Order Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None

        items_result = await db_session.execute(
            select(RolePanelItem)
            .where(RolePanelItem.panel_id == panel.id)
            .order_by(RolePanelItem.position)
        )
        items = list(items_result.scalars().all())
        assert len(items) == 3

        # position順でソートされた順序を確認
        assert items[0].label == "First"
        assert items[0].position == 0
        assert items[1].label == "Second"
        assert items[1].position == 1
        assert items[2].label == "Third"
        assert items[2].position == 2

    async def test_create_with_empty_label_for_reaction_type(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """リアクションタイプではラベルなしでも作成できる。"""
        form_data = [
            ("guild_id", "123456789012345678"),
            ("channel_id", "987654321098765432"),
            ("panel_type", "reaction"),
            ("title", "Reaction No Label"),
            ("item_emoji[]", "⭐"),
            ("item_role_id[]", "111111111111111111"),
            ("item_label[]", ""),
            ("item_position[]", "0"),
            ("item_emoji[]", "🌟"),
            ("item_role_id[]", "222222222222222222"),
            ("item_label[]", ""),
            ("item_position[]", "1"),
        ]
        response = await authenticated_client.post(
            "/rolepanels/new",
            content=urlencode(form_data),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Reaction No Label")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None

        items_result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        items = list(items_result.scalars().all())
        assert len(items) == 2
        assert all(item.label is None or item.label == "" for item in items)


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

    async def test_detail_page_shows_role_autocomplete(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """パネル詳細ページでロール選択オートコンプリートが表示される。"""
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
        # オートコンプリート用 JSON 配列にロールが含まれる
        assert '"name": "Available Role"' in response.text
        assert 'id="role_input"' in response.text
        assert "role-autocomplete" in response.text

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
        # オートコンプリート用 JSON 配列にロールが含まれる
        assert '"name": "Default Color Role"' in response.text
        # color=0 も正しく含まれる
        assert '"color": 0' in response.text


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

    async def test_guilds_sorted_by_name(self, db_session: AsyncSession) -> None:
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
                guild_id="123",
                channel_id="2",
                channel_name="middle-channel",
                position=5,
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

    async def test_includes_voice_channels(self, db_session: AsyncSession) -> None:
        """ボイスチャンネルも含まれる (ロビー用)。"""
        from src.web.app import _get_discord_guilds_and_channels

        db_session.add(DiscordGuild(guild_id="123", guild_name="Test Guild"))
        # テキストチャンネル
        db_session.add(
            DiscordChannel(
                guild_id="123",
                channel_id="1",
                channel_name="general",
                channel_type=0,
                position=0,
            )
        )
        # ボイスチャンネル (ロビー)
        db_session.add(
            DiscordChannel(
                guild_id="123",
                channel_id="2",
                channel_name="voice-lobby",
                channel_type=2,
                position=1,
            )
        )
        await db_session.commit()

        _, channels_map = await _get_discord_guilds_and_channels(db_session)

        assert len(channels_map["123"]) == 2
        channel_names = [ch[1] for ch in channels_map["123"]]
        assert "general" in channel_names
        assert "voice-lobby" in channel_names

    async def test_excludes_category_channels(self, db_session: AsyncSession) -> None:
        """カテゴリチャンネル (type=4) は除外される。"""
        from src.web.app import _get_discord_guilds_and_channels

        db_session.add(DiscordGuild(guild_id="123", guild_name="Test Guild"))
        db_session.add(
            DiscordChannel(
                guild_id="123",
                channel_id="1",
                channel_name="general",
                channel_type=0,
                position=0,
            )
        )
        db_session.add(
            DiscordChannel(
                guild_id="123",
                channel_id="2",
                channel_name="Support",
                channel_type=4,
                position=1,
            )
        )
        await db_session.commit()

        _, channels_map = await _get_discord_guilds_and_channels(db_session)

        assert len(channels_map["123"]) == 1
        assert channels_map["123"][0] == ("1", "general")


class TestGetDiscordCategories:
    """_get_discord_categories のテスト。"""

    async def test_returns_only_categories(self, db_session: AsyncSession) -> None:
        """カテゴリチャンネル (type=4) のみ返される。"""
        from src.web.app import _get_discord_categories

        db_session.add(DiscordGuild(guild_id="123", guild_name="Test Guild"))
        db_session.add(
            DiscordChannel(
                guild_id="123",
                channel_id="1",
                channel_name="general",
                channel_type=0,
                position=0,
            )
        )
        db_session.add(
            DiscordChannel(
                guild_id="123",
                channel_id="2",
                channel_name="Support",
                channel_type=4,
                position=1,
            )
        )
        db_session.add(
            DiscordChannel(
                guild_id="123",
                channel_id="3",
                channel_name="Development",
                channel_type=4,
                position=2,
            )
        )
        await db_session.commit()

        categories_map = await _get_discord_categories(db_session)

        assert len(categories_map["123"]) == 2
        names = [c[1] for c in categories_map["123"]]
        assert "Support" in names
        assert "Development" in names
        assert "general" not in names

    async def test_returns_empty_when_no_categories(
        self, db_session: AsyncSession
    ) -> None:
        """カテゴリがない場合は空の辞書を返す。"""
        from src.web.app import _get_discord_categories

        categories_map = await _get_discord_categories(db_session)
        assert categories_map == {}

    async def test_grouped_by_guild(self, db_session: AsyncSession) -> None:
        """ギルドごとにグループ化される。"""
        from src.web.app import _get_discord_categories

        db_session.add(DiscordGuild(guild_id="111", guild_name="Guild A"))
        db_session.add(DiscordGuild(guild_id="222", guild_name="Guild B"))
        db_session.add(
            DiscordChannel(
                guild_id="111",
                channel_id="1",
                channel_name="Cat A",
                channel_type=4,
                position=0,
            )
        )
        db_session.add(
            DiscordChannel(
                guild_id="222",
                channel_id="2",
                channel_name="Cat B",
                channel_type=4,
                position=0,
            )
        )
        await db_session.commit()

        categories_map = await _get_discord_categories(db_session)

        assert len(categories_map) == 2
        assert categories_map["111"] == [("1", "Cat A")]
        assert categories_map["222"] == [("2", "Cat B")]


class TestGetKnownGuildsAndChannels:
    """_get_known_guilds_and_channels のテスト。"""

    async def test_collects_lobby_channels(self, db_session: AsyncSession) -> None:
        """Lobby からチャンネルIDを収集する。"""
        from src.web.app import _get_known_guilds_and_channels

        db_session.add(
            Lobby(guild_id="123", lobby_channel_id="456", default_user_limit=10)
        )
        db_session.add(
            Lobby(guild_id="123", lobby_channel_id="789", default_user_limit=5)
        )
        await db_session.commit()

        result = await _get_known_guilds_and_channels(db_session)

        assert "123" in result
        assert "456" in result["123"]
        assert "789" in result["123"]

    async def test_collects_bump_config_channels(
        self, db_session: AsyncSession
    ) -> None:
        """BumpConfig からチャンネルIDを収集する。"""
        from src.web.app import _get_known_guilds_and_channels

        db_session.add(BumpConfig(guild_id="111", channel_id="222"))
        await db_session.commit()

        result = await _get_known_guilds_and_channels(db_session)

        assert "111" in result
        assert "222" in result["111"]

    async def test_collects_sticky_channels(self, db_session: AsyncSession) -> None:
        """StickyMessage からチャンネルIDを収集する。"""
        from src.web.app import _get_known_guilds_and_channels

        db_session.add(
            StickyMessage(
                guild_id="333",
                channel_id="444",
                message_type="text",
                title="",
                description="Test sticky",
            )
        )
        await db_session.commit()

        result = await _get_known_guilds_and_channels(db_session)

        assert "333" in result
        assert "444" in result["333"]

    async def test_collects_role_panel_channels(self, db_session: AsyncSession) -> None:
        """RolePanel からチャンネルIDを収集する。"""
        from src.web.app import _get_known_guilds_and_channels

        db_session.add(
            RolePanel(
                guild_id="555",
                channel_id="666",
                message_id="777",
                panel_type="button",
                title="Test Panel",
            )
        )
        await db_session.commit()

        result = await _get_known_guilds_and_channels(db_session)

        assert "555" in result
        assert "666" in result["555"]

    async def test_returns_empty_when_no_data(self, db_session: AsyncSession) -> None:
        """データがない場合は空の辞書を返す。"""
        from src.web.app import _get_known_guilds_and_channels

        result = await _get_known_guilds_and_channels(db_session)

        assert result == {}

    async def test_collects_from_multiple_sources(
        self, db_session: AsyncSession
    ) -> None:
        """複数のソースからチャンネルIDを収集する。"""
        from src.web.app import _get_known_guilds_and_channels

        # 同じギルドに複数のソースからチャンネルを追加
        db_session.add(
            Lobby(guild_id="100", lobby_channel_id="1", default_user_limit=10)
        )
        db_session.add(BumpConfig(guild_id="100", channel_id="2"))
        db_session.add(
            StickyMessage(
                guild_id="100",
                channel_id="3",
                message_type="text",
                title="",
                description="Test",
            )
        )
        db_session.add(
            RolePanel(
                guild_id="100",
                channel_id="4",
                message_id="999",
                panel_type="button",
                title="Test",
            )
        )
        await db_session.commit()

        result = await _get_known_guilds_and_channels(db_session)

        assert "100" in result
        assert len(result["100"]) == 4
        assert set(result["100"]) == {"1", "2", "3", "4"}


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
# Role Panel Remove Reaction Toggle ルート
# ===========================================================================


class TestRolePanelToggleRemoveReaction:
    """toggle-remove-reaction エンドポイントのテスト。"""

    async def test_toggle_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.post(
            "/rolepanels/1/toggle-remove-reaction",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_toggle_enables_remove_reaction(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """False -> True にトグルできる。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Reaction Panel",
            remove_reaction=False,
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/toggle-remove-reaction",
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(panel)
        assert panel.remove_reaction is True

    async def test_toggle_disables_remove_reaction(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """True -> False にトグルできる。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Reaction Panel",
            remove_reaction=True,
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/toggle-remove-reaction",
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(panel)
        assert panel.remove_reaction is False

    async def test_toggle_only_affects_reaction_panels(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """ボタン式パネルでは toggle は効果なし。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",  # ボタン式
            title="Button Panel",
            remove_reaction=False,
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/toggle-remove-reaction",
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(panel)
        # ボタン式なので変化なし
        assert panel.remove_reaction is False

    async def test_toggle_shows_in_detail_page(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """詳細ページに Auto-remove トグルボタンが表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Reaction Panel",
            remove_reaction=True,
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        assert "Auto-remove:" in response.text
        assert "Enabled" in response.text
        assert "toggle-remove-reaction" in response.text


# ===========================================================================
# Role Panel Item Style テスト
# ===========================================================================


class TestRolePanelItemStyle:
    """アイテムのスタイル (ボタン色) のテスト。"""

    async def test_add_item_with_style(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """アイテム追加時にスタイルを指定できる。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Button Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={
                "emoji": "🎮",
                "role_id": "111222333444555666",
                "label": "Game",
                "style": "success",
                "position": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        # アイテムが追加されたことを確認
        from sqlalchemy import select

        result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        item = result.scalar_one()
        assert item.style == "success"

    async def test_add_item_invalid_style_defaults_to_secondary(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """無効なスタイルは secondary にフォールバック。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Button Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={
                "emoji": "🎮",
                "role_id": "111222333444555666",
                "label": "Game",
                "style": "invalid_style",
                "position": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        from sqlalchemy import select

        result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        item = result.scalar_one()
        assert item.style == "secondary"

    async def test_detail_page_shows_style(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """詳細ページにスタイルが表示される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Button Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        item = RolePanelItem(
            panel_id=panel.id,
            role_id="111222333444555666",
            emoji="🎮",
            label="Game",
            style="danger",
            position=0,
        )
        db_session.add(item)
        await db_session.commit()

        response = await authenticated_client.get(f"/rolepanels/{panel.id}")
        assert response.status_code == 200
        # danger スタイルは Red で表示される
        assert "Red" in response.text

    async def test_create_panel_with_item_style(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """パネル作成時にアイテムのスタイルを指定できる。"""
        # DiscordGuild を追加 (チャンネル検証用)
        from src.database.models import DiscordChannel, DiscordGuild, DiscordRole

        guild = DiscordGuild(guild_id="123456789012345678", guild_name="Test Guild")
        db_session.add(guild)
        await db_session.commit()

        channel = DiscordChannel(
            channel_id="987654321098765432",
            guild_id="123456789012345678",
            channel_name="test-channel",
            channel_type=0,
        )
        db_session.add(channel)

        role = DiscordRole(
            role_id="111222333444555666",
            guild_id="123456789012345678",
            role_name="Test Role",
            color=0xFF0000,
        )
        db_session.add(role)
        await db_session.commit()

        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test Panel",
                "description": "",
                "use_embed": "1",
                "remove_reaction": "",
                "item_emoji[]": "🎮",
                "item_role_id[]": "111222333444555666",
                "item_label[]": "Test",
                "item_style[]": "primary",
                "item_position[]": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        # アイテムのスタイルが primary であることを確認
        from sqlalchemy import select

        result = await db_session.execute(select(RolePanelItem))
        item = result.scalar_one()
        assert item.style == "primary"


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
        # アイテム数が表示される
        assert "3 role(s)" in list_response.text

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


# ===========================================================================
# セキュリティヘッダーテスト
# ===========================================================================


class TestSecurityHeaders:
    """セキュリティヘッダーミドルウェアのテスト。"""

    async def test_x_frame_options_header(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """X-Frame-Options ヘッダーが設定される。"""
        response = await client.get("/login")
        assert response.headers.get("X-Frame-Options") == "DENY"

    async def test_x_content_type_options_header(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """X-Content-Type-Options ヘッダーが設定される。"""
        response = await client.get("/login")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    async def test_x_xss_protection_header(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """X-XSS-Protection ヘッダーが設定される。"""
        response = await client.get("/login")
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    async def test_referrer_policy_header(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """Referrer-Policy ヘッダーが設定される。"""
        response = await client.get("/login")
        assert (
            response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        )

    async def test_content_security_policy_header(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """Content-Security-Policy ヘッダーが設定される。"""
        response = await client.get("/login")
        csp = response.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    async def test_cache_control_header_on_login(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """認証ページにはキャッシュ制御ヘッダーが設定される。"""
        response = await client.get("/login")
        assert "no-store" in response.headers.get("Cache-Control", "")

    async def test_cache_control_not_on_health(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ヘルスチェックにはキャッシュ制御ヘッダーが設定されない。"""
        from unittest.mock import AsyncMock

        import src.web.app as web_app_module

        monkeypatch.setattr(
            web_app_module,
            "check_database_connection",
            AsyncMock(return_value=True),
        )

        response = await client.get("/health")
        # health エンドポイントはキャッシュ制御なし
        assert "no-store" not in response.headers.get("Cache-Control", "")


# ===========================================================================
# CSRF 保護テスト
# ===========================================================================


class TestCSRFProtection:
    """CSRF 保護のテスト。"""

    async def test_login_without_csrf_token_fails(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """CSRF トークンなしでログインすると 403 エラーになる。"""
        response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
                # csrf_token なし
            },
            follow_redirects=False,
        )
        assert response.status_code == 403
        assert "Invalid security token" in response.text

    async def test_login_with_invalid_csrf_token_fails(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """無効な CSRF トークンでログインすると 403 エラーになる。"""
        response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
                "csrf_token": "invalid-token",
            },
            follow_redirects=False,
        )
        assert response.status_code == 403
        assert "Invalid security token" in response.text

    async def test_login_with_valid_csrf_token_succeeds(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """有効な CSRF トークンでログインすると成功する。"""
        from src.web.app import generate_csrf_token

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
        # ログイン成功 → ダッシュボードにリダイレクト
        assert response.status_code == 302
        assert response.headers.get("location") == "/dashboard"

    async def test_password_change_without_csrf_fails(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """CSRF トークンなしでパスワード変更すると 403 エラーになる。"""
        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
                # csrf_token なし
            },
            follow_redirects=False,
        )
        assert response.status_code == 403
        assert "Invalid security token" in response.text

    async def test_password_change_with_valid_csrf_succeeds(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """有効な CSRF トークンでパスワード変更すると成功する。"""
        from src.web.app import generate_csrf_token

        csrf_token = generate_csrf_token()

        response = await authenticated_client.post(
            "/settings/password",
            data={
                "new_password": "newpassword123",
                "confirm_password": "newpassword123",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        # 成功 → ログインページにリダイレクト
        assert response.status_code == 302
        assert response.headers.get("location") == "/login"

    async def test_delete_lobby_without_csrf_is_ignored(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """CSRF トークンなしで削除リクエストは無視される (リダイレクト)。"""
        lobby = Lobby(
            guild_id="123456789012345678",
            lobby_channel_id="987654321098765432",
        )
        db_session.add(lobby)
        await db_session.commit()
        await db_session.refresh(lobby)

        response = await authenticated_client.post(
            f"/lobbies/{lobby.id}/delete",
            data={},  # csrf_token なし
            follow_redirects=False,
        )
        # CSRF 検証失敗 → リダイレクト
        assert response.status_code == 302

        # ロビーは削除されていない
        result = await db_session.execute(select(Lobby).where(Lobby.id == lobby.id))
        assert result.scalar_one_or_none() is not None

    async def test_delete_lobby_with_valid_csrf_succeeds(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """有効な CSRF トークンで削除すると成功する。"""
        from src.web.app import generate_csrf_token

        lobby = Lobby(
            guild_id="123456789012345678",
            lobby_channel_id="987654321098765432",
        )
        db_session.add(lobby)
        await db_session.commit()
        await db_session.refresh(lobby)
        lobby_id = lobby.id

        csrf_token = generate_csrf_token()
        response = await authenticated_client.post(
            f"/lobbies/{lobby_id}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302

        # ロビーが削除されている
        db_session.expire_all()
        result = await db_session.execute(select(Lobby).where(Lobby.id == lobby_id))
        assert result.scalar_one_or_none() is None

    async def test_csrf_token_generation_and_validation(self) -> None:
        """CSRF トークンの生成と検証が正しく動作する。"""
        from src.web.app import generate_csrf_token, validate_csrf_token

        # 生成したトークンは有効
        token = generate_csrf_token()
        assert validate_csrf_token(token) is True

        # 空のトークンは無効
        assert validate_csrf_token("") is False
        assert validate_csrf_token(None) is False  # type: ignore[arg-type]

        # 不正なトークンは無効
        assert validate_csrf_token("invalid-token") is False
        assert validate_csrf_token("some.random.string") is False


# ===========================================================================
# フォームクールタイムのテスト
# ===========================================================================


class TestFormCooldown:
    """フォーム送信クールタイムのテスト。"""

    def test_cooldown_not_active_for_new_user(self) -> None:
        """新規ユーザーはクールタイム中ではない。"""
        from src.web.app import is_form_cooldown_active

        result = is_form_cooldown_active("newuser@example.com", "/test/path")
        assert result is False

    def test_cooldown_active_after_submission(self) -> None:
        """フォーム送信後はクールタイム中になる。"""
        from src.web.app import (
            FORM_SUBMIT_TIMES,
            is_form_cooldown_active,
            record_form_submit,
        )

        user_email = "cooldown_test@example.com"
        path = "/test/cooldown"

        record_form_submit(user_email, path)
        result = is_form_cooldown_active(user_email, path)
        assert result is True

        # クリーンアップ
        FORM_SUBMIT_TIMES.pop(f"{user_email}:{path}", None)

    def test_cooldown_not_active_for_different_path(self) -> None:
        """異なるパスはクールタイムが独立している。"""
        from src.web.app import (
            FORM_SUBMIT_TIMES,
            is_form_cooldown_active,
            record_form_submit,
        )

        user_email = "cooldown_path_test@example.com"
        path1 = "/test/path1"
        path2 = "/test/path2"

        record_form_submit(user_email, path1)
        assert is_form_cooldown_active(user_email, path1) is True
        assert is_form_cooldown_active(user_email, path2) is False

        # クリーンアップ
        FORM_SUBMIT_TIMES.pop(f"{user_email}:{path1}", None)

    def test_cooldown_not_active_for_different_user(self) -> None:
        """異なるユーザーはクールタイムが独立している。"""
        from src.web.app import (
            FORM_SUBMIT_TIMES,
            is_form_cooldown_active,
            record_form_submit,
        )

        user1 = "user1@example.com"
        user2 = "user2@example.com"
        path = "/test/path"

        record_form_submit(user1, path)
        assert is_form_cooldown_active(user1, path) is True
        assert is_form_cooldown_active(user2, path) is False

        # クリーンアップ
        FORM_SUBMIT_TIMES.pop(f"{user1}:{path}", None)

    def test_record_form_submit_empty_email(self) -> None:
        """空のメールアドレスは記録されない。"""
        from src.web.app import FORM_SUBMIT_TIMES, record_form_submit

        initial_count = len(FORM_SUBMIT_TIMES)
        record_form_submit("", "/test/path")
        assert len(FORM_SUBMIT_TIMES) == initial_count

    def test_cooldown_cleanup(self) -> None:
        """クールタイムエントリのクリーンアップ。"""
        import time

        import src.web.app as web_app_module
        from src.web.app import (
            FORM_SUBMIT_TIMES,
            _cleanup_form_cooldown_entries,
        )

        # 古いタイムスタンプを設定（クールタイムの5倍以上前）
        old_time = time.time() - 10  # 10秒前
        test_key = "cleanup_test@example.com:/test/cleanup"
        FORM_SUBMIT_TIMES[test_key] = old_time

        # 強制的にクリーンアップを実行
        web_app_module._form_cooldown_last_cleanup_time = 0
        _cleanup_form_cooldown_entries()

        # 古いエントリが削除されている
        assert test_key not in FORM_SUBMIT_TIMES

    def test_cooldown_cleanup_guard_allows_zero_last_time(self) -> None:
        """_form_cooldown_last_cleanup_time=0 でもクリーンアップが実行される.

        0 は「未実行」として扱われクリーンアップがスキップされないことを検証。
        """
        import time

        import src.web.app as web_app_module
        from src.web.app import (
            FORM_SUBMIT_TIMES,
            _cleanup_form_cooldown_entries,
        )

        test_key = "guard_test@example.com:/test/guard"
        FORM_SUBMIT_TIMES[test_key] = time.time() - 100

        web_app_module._form_cooldown_last_cleanup_time = 0
        _cleanup_form_cooldown_entries()

        assert test_key not in FORM_SUBMIT_TIMES
        assert web_app_module._form_cooldown_last_cleanup_time > 0

    def test_cooldown_cleanup_interval_respected(self) -> None:
        """クリーンアップ間隔が未経過ならスキップされる."""
        import time

        import src.web.app as web_app_module
        from src.web.app import (
            FORM_SUBMIT_TIMES,
            _cleanup_form_cooldown_entries,
        )

        test_key = "interval_test@example.com:/test/interval"
        FORM_SUBMIT_TIMES[test_key] = time.time() - 100

        # 最終クリーンアップを最近に設定 (間隔未経過)
        web_app_module._form_cooldown_last_cleanup_time = time.time() - 1
        _cleanup_form_cooldown_entries()

        # 間隔未経過なのでエントリはまだ残る
        assert test_key in FORM_SUBMIT_TIMES
        FORM_SUBMIT_TIMES.pop(test_key, None)

    def test_cooldown_cleanup_keeps_active_removes_expired(self) -> None:
        """期限切れエントリは削除、アクティブは保持."""
        import time

        import src.web.app as web_app_module
        from src.web.app import (
            FORM_SUBMIT_TIMES,
            _cleanup_form_cooldown_entries,
        )

        expired_key = "expired@example.com:/test/expired"
        active_key = "active@example.com:/test/active"
        FORM_SUBMIT_TIMES[expired_key] = time.time() - 100
        FORM_SUBMIT_TIMES[active_key] = time.time()

        web_app_module._form_cooldown_last_cleanup_time = 0
        _cleanup_form_cooldown_entries()

        assert expired_key not in FORM_SUBMIT_TIMES
        assert active_key in FORM_SUBMIT_TIMES
        FORM_SUBMIT_TIMES.pop(active_key, None)


class TestFormCooldownRoutes:
    """フォームクールタイムのルートテスト。"""

    async def test_lobby_delete_cooldown(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロビー削除にクールタイムが適用される。"""
        lobby = Lobby(
            guild_id="123456789012345678",
            lobby_channel_id="987654321098765432",
        )
        db_session.add(lobby)
        await db_session.commit()
        await db_session.refresh(lobby)

        # 最初の削除は成功
        response = await authenticated_client.post(
            f"/lobbies/{lobby.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

    async def test_rolepanel_create_cooldown(
        self, authenticated_client: AsyncClient
    ) -> None:
        """ロールパネル作成でクールタイムが適用される。"""
        import time

        from src.web.app import FORM_SUBMIT_TIMES

        # 直前にフォーム送信を記録してクールタイム状態にする
        key = "test@example.com:/rolepanels/new"
        FORM_SUBMIT_TIMES[key] = time.time()

        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "Cooldown Test Panel",
            "item_emoji[]": "🎮",
            "item_role_id[]": "111222333444555666",
            "item_label[]": "Test",
            "item_position[]": "0",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
        )
        # クールタイム中なので 429 を返す
        assert response.status_code == 429
        assert "Please wait" in response.text

        # クリーンアップ
        FORM_SUBMIT_TIMES.pop(key, None)


# ===========================================================================
# 二重ロック（リソースロック）のテスト
# ===========================================================================


class TestResourceLock:
    """リソースロックのテスト。"""

    def test_get_resource_lock_returns_lock(self) -> None:
        """get_resource_lock がロックを返す。"""
        import asyncio

        from src.utils import get_resource_lock

        lock = get_resource_lock("test:lock:1")
        assert isinstance(lock, asyncio.Lock)

    def test_get_resource_lock_same_key_returns_same_lock(self) -> None:
        """同じキーでは同じロックが返される。"""
        from src.utils import get_resource_lock

        lock1 = get_resource_lock("test:lock:same")
        lock2 = get_resource_lock("test:lock:same")
        assert lock1 is lock2

    def test_get_resource_lock_different_key_returns_different_lock(self) -> None:
        """異なるキーでは異なるロックが返される。"""
        from src.utils import get_resource_lock

        lock1 = get_resource_lock("test:lock:a")
        lock2 = get_resource_lock("test:lock:b")
        assert lock1 is not lock2

    async def test_resource_lock_prevents_concurrent_access(self) -> None:
        """リソースロックが同時アクセスを防止する。"""
        import asyncio

        from src.utils import get_resource_lock

        results: list[int] = []
        lock_key = "test:concurrent:lock"

        async def task1() -> None:
            async with get_resource_lock(lock_key):
                results.append(1)
                await asyncio.sleep(0.1)
                results.append(2)

        async def task2() -> None:
            await asyncio.sleep(0.05)  # task1 がロックを取得してから
            async with get_resource_lock(lock_key):
                results.append(3)
                results.append(4)

        await asyncio.gather(task1(), task2())

        # task1 が完了してから task2 が実行されるはず
        assert results == [1, 2, 3, 4]


class TestResourceLockIntegration:
    """リソースロックの統合テスト。"""

    async def test_concurrent_lobby_delete_requests(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """同時ロビー削除リクエストが順序正しく処理される。"""
        lobby = Lobby(
            guild_id="123456789012345678",
            lobby_channel_id="987654321098765432",
        )
        db_session.add(lobby)
        await db_session.commit()
        await db_session.refresh(lobby)
        lobby_id = lobby.id

        # 削除リクエスト
        response = await authenticated_client.post(
            f"/lobbies/{lobby_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

        # 2回目は既に削除済みなのでリダイレクトのみ
        response2 = await authenticated_client.post(
            f"/lobbies/{lobby_id}/delete",
            follow_redirects=False,
        )
        assert response2.status_code == 302

    async def test_concurrent_rolepanel_item_add(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """同時ロールパネルアイテム追加が順序正しく処理される。"""
        # パネルを作成
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Lock Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # アイテム追加リクエスト
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
        assert "success" in response.headers["location"]


# ===========================================================================
# メンテナンスルート
# ===========================================================================


class TestMaintenanceRoutes:
    """/settings/maintenance ルートのテスト。"""

    async def test_maintenance_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/settings/maintenance", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_maintenance_page_renders(
        self, authenticated_client: AsyncClient
    ) -> None:
        """メンテナンスページが表示される。"""
        response = await authenticated_client.get("/settings/maintenance")
        assert response.status_code == 200
        assert "Database Maintenance" in response.text
        assert "Database Statistics" in response.text
        assert "Actions" in response.text
        assert "Refresh Stats" in response.text

    async def test_maintenance_shows_stats(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """統計情報が表示される。"""
        # ギルドを追加
        guild = DiscordGuild(
            guild_id="123456789012345678",
            guild_name="Test Guild",
            member_count=100,
        )
        db_session.add(guild)

        # アクティブなギルドに属するデータを追加
        lobby = Lobby(
            guild_id="123456789012345678",
            lobby_channel_id="987654321098765432",
        )
        db_session.add(lobby)
        await db_session.commit()

        response = await authenticated_client.get("/settings/maintenance")
        assert response.status_code == 200
        # ロビー数が表示される
        assert "Lobbies" in response.text

    async def test_maintenance_shows_orphaned_count(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """孤立データの数が表示される。"""
        # アクティブなギルド (DiscordGuild にある)
        active_guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Active Guild",
            member_count=100,
        )
        db_session.add(active_guild)

        # アクティブなギルドのロビー
        active_lobby = Lobby(
            guild_id="111111111111111111",
            lobby_channel_id="222222222222222222",
        )
        db_session.add(active_lobby)

        # 孤立したロビー (DiscordGuild にない)
        orphaned_lobby = Lobby(
            guild_id="999999999999999999",
            lobby_channel_id="888888888888888888",
        )
        db_session.add(orphaned_lobby)
        await db_session.commit()

        response = await authenticated_client.get("/settings/maintenance")
        assert response.status_code == 200
        # 孤立数: 1 が表示される
        assert "Orphaned: 1" in response.text

    async def test_maintenance_cleanup_requires_auth(self, client: AsyncClient) -> None:
        """クリーンアップは認証が必要。"""
        response = await client.post(
            "/settings/maintenance/cleanup",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_maintenance_cleanup_deletes_orphaned_lobbies(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """孤立したロビーがクリーンアップで削除される。"""
        # アクティブなギルド
        active_guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Active Guild",
            member_count=100,
        )
        db_session.add(active_guild)

        # アクティブなギルドのロビー
        active_lobby = Lobby(
            guild_id="111111111111111111",
            lobby_channel_id="222222222222222222",
        )
        db_session.add(active_lobby)

        # 孤立したロビー
        orphaned_lobby = Lobby(
            guild_id="999999999999999999",
            lobby_channel_id="888888888888888888",
        )
        db_session.add(orphaned_lobby)
        await db_session.commit()

        # クリーンアップを実行
        response = await authenticated_client.post(
            "/settings/maintenance/cleanup",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "success" in response.headers["location"].lower()

        # 孤立したロビーが削除されていることを確認
        db_session.expire_all()
        result = await db_session.execute(select(Lobby))
        lobbies = list(result.scalars().all())
        assert len(lobbies) == 1
        assert lobbies[0].guild_id == "111111111111111111"

    async def test_maintenance_cleanup_deletes_orphaned_bump_configs(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """孤立した Bump 設定がクリーンアップで削除される。"""
        # アクティブなギルド
        active_guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Active Guild",
            member_count=100,
        )
        db_session.add(active_guild)

        # アクティブなギルドの Bump 設定
        active_bump = BumpConfig(
            guild_id="111111111111111111",
            channel_id="222222222222222222",
        )
        db_session.add(active_bump)

        # 孤立した Bump 設定
        orphaned_bump = BumpConfig(
            guild_id="999999999999999999",
            channel_id="888888888888888888",
        )
        db_session.add(orphaned_bump)

        # 孤立した Bump 設定のリマインダー
        orphaned_reminder = BumpReminder(
            guild_id="999999999999999999",
            channel_id="888888888888888888",
            service_name="DISBOARD",
        )
        db_session.add(orphaned_reminder)
        await db_session.commit()

        # クリーンアップを実行
        response = await authenticated_client.post(
            "/settings/maintenance/cleanup",
            follow_redirects=False,
        )
        assert response.status_code == 302

        # 孤立した Bump 設定とリマインダーが削除されていることを確認
        db_session.expire_all()
        bump_result = await db_session.execute(select(BumpConfig))
        bump_configs = list(bump_result.scalars().all())
        assert len(bump_configs) == 1
        assert bump_configs[0].guild_id == "111111111111111111"

        reminder_result = await db_session.execute(select(BumpReminder))
        reminders = list(reminder_result.scalars().all())
        assert len(reminders) == 0

    async def test_maintenance_cleanup_deletes_orphaned_stickies(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """孤立した Sticky メッセージがクリーンアップで削除される。"""
        # アクティブなギルド
        active_guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Active Guild",
            member_count=100,
        )
        db_session.add(active_guild)

        # アクティブなギルドの Sticky
        active_sticky = StickyMessage(
            guild_id="111111111111111111",
            channel_id="222222222222222222",
            title="Active sticky",
            description="Active sticky message",
        )
        db_session.add(active_sticky)

        # 孤立した Sticky
        orphaned_sticky = StickyMessage(
            guild_id="999999999999999999",
            channel_id="888888888888888888",
            title="Orphaned sticky",
            description="Orphaned sticky message",
        )
        db_session.add(orphaned_sticky)
        await db_session.commit()

        # クリーンアップを実行
        response = await authenticated_client.post(
            "/settings/maintenance/cleanup",
            follow_redirects=False,
        )
        assert response.status_code == 302

        # 孤立した Sticky が削除されていることを確認
        db_session.expire_all()
        result = await db_session.execute(select(StickyMessage))
        stickies = list(result.scalars().all())
        assert len(stickies) == 1
        assert stickies[0].guild_id == "111111111111111111"

    async def test_maintenance_cleanup_deletes_orphaned_role_panels(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """孤立したロールパネルがクリーンアップで削除される。"""
        # アクティブなギルド
        active_guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Active Guild",
            member_count=100,
        )
        db_session.add(active_guild)

        # アクティブなギルドのパネル
        active_panel = RolePanel(
            guild_id="111111111111111111",
            channel_id="222222222222222222",
            panel_type="button",
            title="Active Panel",
        )
        db_session.add(active_panel)

        # 孤立したパネル
        orphaned_panel = RolePanel(
            guild_id="999999999999999999",
            channel_id="888888888888888888",
            panel_type="button",
            title="Orphaned Panel",
        )
        db_session.add(orphaned_panel)
        await db_session.commit()

        # クリーンアップを実行
        response = await authenticated_client.post(
            "/settings/maintenance/cleanup",
            follow_redirects=False,
        )
        assert response.status_code == 302

        # 孤立したパネルが削除されていることを確認
        db_session.expire_all()
        result = await db_session.execute(select(RolePanel))
        panels = list(result.scalars().all())
        assert len(panels) == 1
        assert panels[0].guild_id == "111111111111111111"

    async def test_maintenance_cleanup_no_orphaned_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """孤立データがない場合のクリーンアップ。"""
        # アクティブなギルドのみ
        active_guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Active Guild",
            member_count=100,
        )
        db_session.add(active_guild)

        # アクティブなギルドのロビーのみ
        active_lobby = Lobby(
            guild_id="111111111111111111",
            lobby_channel_id="222222222222222222",
        )
        db_session.add(active_lobby)
        await db_session.commit()

        # クリーンアップを実行
        response = await authenticated_client.post(
            "/settings/maintenance/cleanup",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "No+orphaned+data+found" in response.headers["location"]

        # ロビーは削除されていない
        db_session.expire_all()
        result = await db_session.execute(select(Lobby))
        lobbies = list(result.scalars().all())
        assert len(lobbies) == 1

    async def test_maintenance_refresh_requires_auth(self, client: AsyncClient) -> None:
        """リフレッシュは認証が必要。"""
        response = await client.post(
            "/settings/maintenance/refresh",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_maintenance_refresh_redirects_with_success(
        self, authenticated_client: AsyncClient
    ) -> None:
        """リフレッシュ成功時はメンテナンスページにリダイレクトされる。"""
        response = await authenticated_client.post(
            "/settings/maintenance/refresh",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "success=Stats+refreshed" in response.headers["location"]

    async def test_maintenance_refresh_rate_limited(
        self,
        authenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """リフレッシュはレート制限される。"""
        import src.web.app as web_app_module

        # クールダウンをアクティブにモック
        monkeypatch.setattr(
            web_app_module,
            "is_form_cooldown_active",
            lambda *_args: True,
        )

        response = await authenticated_client.post(
            "/settings/maintenance/refresh",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "Please+wait" in response.headers["location"]

    async def test_maintenance_cleanup_rate_limited(
        self,
        authenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """クリーンアップはレート制限される。"""
        import src.web.app as web_app_module

        # クールダウンをアクティブにモック
        monkeypatch.setattr(
            web_app_module,
            "is_form_cooldown_active",
            lambda *_args: True,
        )

        response = await authenticated_client.post(
            "/settings/maintenance/cleanup",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "Please+wait" in response.headers["location"]

    async def test_maintenance_page_contains_cleanup_modal(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """メンテナンスページに確認モーダルが含まれる。"""
        # 孤立データを作成
        orphaned_lobby = Lobby(
            guild_id="999999999999999999",
            lobby_channel_id="888888888888888888",
        )
        db_session.add(orphaned_lobby)
        await db_session.commit()

        response = await authenticated_client.get("/settings/maintenance")
        assert response.status_code == 200
        # モーダルの要素が含まれる
        assert "cleanup-modal" in response.text
        assert "Confirm Cleanup" in response.text
        assert "permanently deleted" in response.text
        assert "This action cannot be undone" in response.text

    async def test_cleanup_modal_shows_breakdown(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """確認モーダルに削除対象の内訳が表示される。"""
        # 複数種類の孤立データを作成
        orphaned_lobby = Lobby(
            guild_id="999999999999999999",
            lobby_channel_id="888888888888888888",
        )
        orphaned_bump = BumpConfig(
            guild_id="999999999999999999",
            channel_id="777777777777777777",
        )
        orphaned_sticky = StickyMessage(
            channel_id="666666666666666666",
            guild_id="999999999999999999",
            title="Orphaned Sticky",
            description="Test",
        )
        orphaned_panel = RolePanel(
            guild_id="999999999999999999",
            channel_id="555555555555555555",
            panel_type="button",
            title="Orphaned Panel",
        )
        db_session.add_all(
            [orphaned_lobby, orphaned_bump, orphaned_sticky, orphaned_panel]
        )
        await db_session.commit()

        response = await authenticated_client.get("/settings/maintenance")
        assert response.status_code == 200
        # 内訳が表示される
        assert "Lobbies:" in response.text
        assert "Bump Configs:" in response.text
        assert "Stickies:" in response.text
        assert "Role Panels:" in response.text
        # 合計が表示される
        assert "Total:" in response.text
        # 確認ボタンにレコード数が表示される
        assert "Delete 4 Records" in response.text

    async def test_cleanup_modal_has_cancel_button(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """確認モーダルにキャンセルボタンがある。"""
        orphaned_lobby = Lobby(
            guild_id="999999999999999999",
            lobby_channel_id="888888888888888888",
        )
        db_session.add(orphaned_lobby)
        await db_session.commit()

        response = await authenticated_client.get("/settings/maintenance")
        assert response.status_code == 200
        # キャンセルボタン
        assert "Cancel" in response.text
        assert "hideCleanupModal" in response.text

    async def test_cleanup_button_triggers_modal(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """クリーンアップボタンがモーダルを表示する。"""
        orphaned_lobby = Lobby(
            guild_id="999999999999999999",
            lobby_channel_id="888888888888888888",
        )
        db_session.add(orphaned_lobby)
        await db_session.commit()

        response = await authenticated_client.get("/settings/maintenance")
        assert response.status_code == 200
        # ボタンがモーダルを表示する JavaScript を呼び出す
        assert "showCleanupModal()" in response.text


# ===========================================================================
# クリーンアップモーダル エッジケーステスト
# ===========================================================================


class TestCleanupModalEdgeCases:
    """クリーンアップモーダルのエッジケーステスト。"""

    async def test_cleanup_button_disabled_when_no_orphaned_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """孤立データがない場合、クリーンアップボタンが非活性。"""
        # アクティブなギルドを作成
        active_guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Active Guild",
            member_count=100,
        )
        db_session.add(active_guild)

        # アクティブなギルドのデータのみ
        active_lobby = Lobby(
            guild_id="111111111111111111",
            lobby_channel_id="222222222222222222",
        )
        db_session.add(active_lobby)
        await db_session.commit()

        response = await authenticated_client.get("/settings/maintenance")
        assert response.status_code == 200
        # 孤立データなしのボタンが表示される
        assert "No Orphaned Data" in response.text
        # disabled 属性がボタンに付いている
        assert "disabled" in response.text

    async def test_cleanup_modal_with_only_lobbies_orphaned(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロビーだけが孤立している場合の表示。"""
        # 孤立したロビーのみ
        orphaned_lobby1 = Lobby(
            guild_id="999999999999999999",
            lobby_channel_id="888888888888888888",
        )
        orphaned_lobby2 = Lobby(
            guild_id="999999999999999999",
            lobby_channel_id="777777777777777777",
        )
        db_session.add_all([orphaned_lobby1, orphaned_lobby2])
        await db_session.commit()

        response = await authenticated_client.get("/settings/maintenance")
        assert response.status_code == 200
        # Lobbies の数が表示される
        assert "Delete 2 Records" in response.text
        # モーダル内のLobbies行
        assert "Lobbies:" in response.text

    async def test_cleanup_modal_with_only_panels_orphaned(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロールパネルだけが孤立している場合の表示。"""
        orphaned_panel = RolePanel(
            guild_id="999999999999999999",
            channel_id="888888888888888888",
            panel_type="button",
            title="Orphaned Panel",
        )
        db_session.add(orphaned_panel)
        await db_session.commit()

        response = await authenticated_client.get("/settings/maintenance")
        assert response.status_code == 200
        assert "Delete 1 Records" in response.text
        assert "Role Panels:" in response.text

    async def test_cleanup_modal_shows_mixed_orphaned_types(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """複数種類の孤立データが混在する場合の表示。"""
        # アクティブなギルド
        active_guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Active Guild",
        )
        db_session.add(active_guild)

        # アクティブなデータ (カウントされない)
        active_lobby = Lobby(
            guild_id="111111111111111111",
            lobby_channel_id="222222222222222222",
        )
        active_bump = BumpConfig(
            guild_id="111111111111111111",
            channel_id="222222222222222222",
        )
        db_session.add_all([active_lobby, active_bump])

        # 孤立データ
        orphaned_lobbies = [
            Lobby(guild_id="999999999999999999", lobby_channel_id=f"8888{i}")
            for i in range(3)
        ]
        orphaned_stickies = [
            StickyMessage(
                channel_id=f"7777{i}",
                guild_id="999999999999999999",
                title=f"Sticky {i}",
                description="Test",
            )
            for i in range(2)
        ]
        db_session.add_all(orphaned_lobbies + orphaned_stickies)
        await db_session.commit()

        response = await authenticated_client.get("/settings/maintenance")
        assert response.status_code == 200
        # 合計: 3 (lobbies) + 2 (stickies) = 5
        assert "Delete 5 Records" in response.text
        assert "Lobbies:" in response.text
        assert "Stickies:" in response.text

    async def test_refresh_stats_updates_counts(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """統計更新ボタンが正しく動作する。"""
        response = await authenticated_client.post(
            "/settings/maintenance/refresh",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/settings/maintenance" in response.headers["location"]

    async def test_cleanup_with_large_number_of_orphaned_records(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """大量の孤立レコードがある場合のクリーンアップ。"""
        # 50件の孤立ロビーを作成
        orphaned_lobbies = [
            Lobby(
                guild_id="999999999999999999",
                lobby_channel_id=f"10000000000000000{i:02d}",
            )
            for i in range(50)
        ]
        db_session.add_all(orphaned_lobbies)
        await db_session.commit()

        response = await authenticated_client.get("/settings/maintenance")
        assert response.status_code == 200
        assert "Delete 50 Records" in response.text

        # クリーンアップ実行
        cleanup_response = await authenticated_client.post(
            "/settings/maintenance/cleanup",
            follow_redirects=False,
        )
        assert cleanup_response.status_code == 302

        # 全て削除されたことを確認
        db_session.expire_all()
        result = await db_session.execute(select(Lobby))
        remaining_lobbies = list(result.scalars().all())
        assert len(remaining_lobbies) == 0

    async def test_cleanup_preserves_active_guild_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """クリーンアップがアクティブギルドのデータを保持する。"""
        # 複数のアクティブギルド
        active_guild1 = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Active Guild 1",
        )
        active_guild2 = DiscordGuild(
            guild_id="222222222222222222",
            guild_name="Active Guild 2",
        )
        db_session.add_all([active_guild1, active_guild2])

        # 各アクティブギルドのデータ
        active_lobby1 = Lobby(
            guild_id="111111111111111111",
            lobby_channel_id="100000000000000001",
        )
        active_lobby2 = Lobby(
            guild_id="222222222222222222",
            lobby_channel_id="200000000000000001",
        )
        active_bump = BumpConfig(
            guild_id="111111111111111111",
            channel_id="100000000000000001",
        )
        db_session.add_all([active_lobby1, active_lobby2, active_bump])

        # 孤立データ
        orphaned_lobby = Lobby(
            guild_id="999999999999999999",
            lobby_channel_id="900000000000000001",
        )
        db_session.add(orphaned_lobby)
        await db_session.commit()

        # クリーンアップ実行
        await authenticated_client.post(
            "/settings/maintenance/cleanup",
            follow_redirects=False,
        )

        # アクティブギルドのデータが保持されていることを確認
        db_session.expire_all()
        lobby_result = await db_session.execute(select(Lobby))
        lobbies = list(lobby_result.scalars().all())
        assert len(lobbies) == 2
        guild_ids = {lobby.guild_id for lobby in lobbies}
        assert "111111111111111111" in guild_ids
        assert "222222222222222222" in guild_ids
        assert "999999999999999999" not in guild_ids

        bump_result = await db_session.execute(select(BumpConfig))
        bumps = list(bump_result.scalars().all())
        assert len(bumps) == 1
        assert bumps[0].guild_id == "111111111111111111"


# ===========================================================================
# ギルド・チャンネル名表示 統合テスト
# ===========================================================================


class TestGuildChannelNameDisplayIntegration:
    """ギルド・チャンネル名表示の統合テスト。"""

    async def test_all_list_pages_display_cached_names(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """全ての一覧ページでキャッシュされた名前が表示される。"""
        # 共通のギルド・チャンネルキャッシュを作成
        guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Integration Test Server",
        )
        channel = DiscordChannel(
            guild_id="111111111111111111",
            channel_id="222222222222222222",
            channel_name="test-channel",
            position=0,
        )
        db_session.add_all([guild, channel])

        # 各機能のデータを作成
        lobby = Lobby(
            guild_id="111111111111111111",
            lobby_channel_id="222222222222222222",
        )
        sticky = StickyMessage(
            channel_id="222222222222222222",
            guild_id="111111111111111111",
            title="Test Sticky",
            description="Test",
        )
        bump_config = BumpConfig(
            guild_id="111111111111111111",
            channel_id="222222222222222222",
        )
        role_panel = RolePanel(
            guild_id="111111111111111111",
            channel_id="222222222222222222",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add_all([lobby, sticky, bump_config, role_panel])
        await db_session.commit()

        # 全ページで名前が表示されることを確認
        lobbies_response = await authenticated_client.get("/lobbies")
        assert lobbies_response.status_code == 200
        assert "Integration Test Server" in lobbies_response.text
        assert "#test-channel" in lobbies_response.text

        sticky_response = await authenticated_client.get("/sticky")
        assert sticky_response.status_code == 200
        assert "Integration Test Server" in sticky_response.text
        assert "#test-channel" in sticky_response.text

        bump_response = await authenticated_client.get("/bump")
        assert bump_response.status_code == 200
        assert "Integration Test Server" in bump_response.text
        assert "#test-channel" in bump_response.text

        rolepanels_response = await authenticated_client.get("/rolepanels")
        assert rolepanels_response.status_code == 200
        assert "Integration Test Server" in rolepanels_response.text
        assert "#test-channel" in rolepanels_response.text

    async def test_mixed_cached_and_uncached_guilds(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュ済みとキャッシュなしのギルドが混在する場合の表示。"""
        # キャッシュ済みギルド
        cached_guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Cached Server",
        )
        db_session.add(cached_guild)

        # キャッシュ済みギルドのロビー
        cached_lobby = Lobby(
            guild_id="111111111111111111",
            lobby_channel_id="222222222222222222",
        )
        # キャッシュなしギルドのロビー
        uncached_lobby = Lobby(
            guild_id="999999999999999999",
            lobby_channel_id="888888888888888888",
        )
        db_session.add_all([cached_lobby, uncached_lobby])
        await db_session.commit()

        response = await authenticated_client.get("/lobbies")
        assert response.status_code == 200

        # キャッシュ済みはサーバー名が表示
        assert "Cached Server" in response.text
        # キャッシュなしは黄色 ID 表示
        assert "text-yellow-400" in response.text
        # キャッシュなしの ID が表示
        assert "999999999999999999" in response.text

    async def test_multiple_channels_same_guild(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """同一ギルドの複数チャンネルが正しく表示される。"""
        guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Multi Channel Server",
        )
        channel1 = DiscordChannel(
            guild_id="111111111111111111",
            channel_id="222222222222222222",
            channel_name="channel-one",
            position=0,
        )
        channel2 = DiscordChannel(
            guild_id="111111111111111111",
            channel_id="333333333333333333",
            channel_name="channel-two",
            position=1,
        )
        db_session.add_all([guild, channel1, channel2])

        # 異なるチャンネルのスティッキー
        sticky1 = StickyMessage(
            channel_id="222222222222222222",
            guild_id="111111111111111111",
            title="Sticky One",
            description="Test",
        )
        sticky2 = StickyMessage(
            channel_id="333333333333333333",
            guild_id="111111111111111111",
            title="Sticky Two",
            description="Test",
        )
        db_session.add_all([sticky1, sticky2])
        await db_session.commit()

        response = await authenticated_client.get("/sticky")
        assert response.status_code == 200
        assert "Multi Channel Server" in response.text
        assert "#channel-one" in response.text
        assert "#channel-two" in response.text

    async def test_guild_name_with_special_characters(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """特殊文字を含むサーバー名が正しくエスケープされる。"""
        guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Test <Server> & 'Guild'",
        )
        channel = DiscordChannel(
            guild_id="111111111111111111",
            channel_id="222222222222222222",
            channel_name="general",
            position=0,
        )
        lobby = Lobby(
            guild_id="111111111111111111",
            lobby_channel_id="222222222222222222",
        )
        db_session.add_all([guild, channel, lobby])
        await db_session.commit()

        response = await authenticated_client.get("/lobbies")
        assert response.status_code == 200
        # HTML エスケープされた形で表示
        assert "&lt;Server&gt;" in response.text
        assert "&amp;" in response.text
        # 生の特殊文字は含まれない
        assert "<Server>" not in response.text

    async def test_japanese_guild_and_channel_names(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """日本語のサーバー名・チャンネル名が正しく表示される。"""
        guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="日本語サーバー",
        )
        channel = DiscordChannel(
            guild_id="111111111111111111",
            channel_id="222222222222222222",
            channel_name="一般チャット",
            position=0,
        )
        bump_config = BumpConfig(
            guild_id="111111111111111111",
            channel_id="222222222222222222",
        )
        db_session.add_all([guild, channel, bump_config])
        await db_session.commit()

        response = await authenticated_client.get("/bump")
        assert response.status_code == 200
        assert "日本語サーバー" in response.text
        assert "#一般チャット" in response.text

    async def test_display_after_cache_update(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """キャッシュ更新後に新しい名前が反映される。"""
        # 初期のキャッシュ
        guild = DiscordGuild(
            guild_id="111111111111111111",
            guild_name="Old Server Name",
        )
        lobby = Lobby(
            guild_id="111111111111111111",
            lobby_channel_id="222222222222222222",
        )
        db_session.add_all([guild, lobby])
        await db_session.commit()

        # 初回リクエスト
        response1 = await authenticated_client.get("/lobbies")
        assert "Old Server Name" in response1.text

        # キャッシュを更新
        guild.guild_name = "New Server Name"
        await db_session.commit()

        # 更新後のリクエスト
        response2 = await authenticated_client.get("/lobbies")
        assert "New Server Name" in response2.text
        assert "Old Server Name" not in response2.text


# ===========================================================================
# パスワードユーティリティのテスト
# ===========================================================================


class TestPasswordUtilities:
    """hash_password / verify_password のテスト。"""

    def test_hash_password_normal(self) -> None:
        """通常のパスワードがハッシュ化される。"""
        password = "testpassword123"
        hashed = hash_password(password)
        assert hashed != password
        assert hashed.startswith("$2")  # bcrypt プレフィックス

    def test_verify_password_correct(self) -> None:
        """正しいパスワードで検証が成功する。"""
        password = "testpassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """間違ったパスワードで検証が失敗する。"""
        password = "testpassword123"
        hashed = hash_password(password)
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty_password(self) -> None:
        """空のパスワードで検証が失敗する。"""
        hashed = hash_password("testpassword123")
        assert verify_password("", hashed) is False

    def test_verify_password_empty_hash(self) -> None:
        """空のハッシュで検証が失敗する。"""
        assert verify_password("testpassword123", "") is False

    def test_verify_password_invalid_hash(self) -> None:
        """無効なハッシュ形式で検証が失敗する。"""
        assert verify_password("testpassword123", "invalid_hash") is False

    def test_verify_password_corrupted_hash(self) -> None:
        """破損したハッシュで検証が失敗する。"""
        # bcrypt っぽいが無効なハッシュ
        corrupted = "$2b$12$invalid_hash_data_here"
        assert verify_password("testpassword123", corrupted) is False

    def test_hash_password_long_password_truncation(self) -> None:
        """72バイトを超えるパスワードが切り詰められる。"""
        # 73バイト以上のパスワード (ASCII文字で73文字)
        long_password = "a" * 100
        hashed = hash_password(long_password)
        # 切り詰められた72バイトで検証
        truncated = "a" * 72
        assert verify_password(truncated, hashed) is True

    def test_hash_password_exactly_72_bytes(self) -> None:
        """ちょうど72バイトのパスワードは切り詰められない。"""
        password = "a" * BCRYPT_MAX_PASSWORD_BYTES
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_hash_password_utf8_truncation(self) -> None:
        """UTF-8 マルチバイト文字を含むパスワードの切り詰め。"""
        # 日本語1文字は3バイト (UTF-8)
        # 72バイト / 3バイト = 24文字で72バイト
        password_24_chars = "あ" * 24  # 72バイト
        password_25_chars = "あ" * 25  # 75バイト (切り詰められる)

        hashed_24 = hash_password(password_24_chars)
        hashed_25 = hash_password(password_25_chars)

        # 24文字は切り詰めなしで検証成功
        assert verify_password(password_24_chars, hashed_24) is True
        # 25文字は切り詰められて24文字と同じハッシュになる
        assert verify_password(password_24_chars, hashed_25) is True

    def test_hash_password_unicode(self) -> None:
        """Unicode 文字を含むパスワードがハッシュ化される。"""
        password = "パスワード123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True


# ===========================================================================
# レート制限ユーティリティのテスト
# ===========================================================================


class TestRateLimitingFunctions:
    """is_rate_limited / record_failed_attempt のテスト。"""

    def test_is_rate_limited_new_ip(self) -> None:
        """新しい IP はレート制限されない。"""
        assert is_rate_limited("192.168.1.1") is False

    def test_is_rate_limited_under_limit(self) -> None:
        """試行回数が上限未満ならレート制限されない。"""
        ip = "192.168.1.1"
        for _ in range(LOGIN_MAX_ATTEMPTS - 1):
            record_failed_attempt(ip)
        assert is_rate_limited(ip) is False

    def test_is_rate_limited_at_limit(self) -> None:
        """試行回数が上限に達するとレート制限される。"""
        ip = "192.168.1.1"
        for _ in range(LOGIN_MAX_ATTEMPTS):
            record_failed_attempt(ip)
        assert is_rate_limited(ip) is True

    def test_is_rate_limited_over_limit(self) -> None:
        """試行回数が上限を超えてもレート制限が維持される。"""
        ip = "192.168.1.1"
        for _ in range(LOGIN_MAX_ATTEMPTS + 5):
            record_failed_attempt(ip)
        assert is_rate_limited(ip) is True

    def test_rate_limit_per_ip(self) -> None:
        """IP ごとに独立してレート制限される。"""
        ip1 = "192.168.1.1"
        ip2 = "192.168.1.2"

        for _ in range(LOGIN_MAX_ATTEMPTS):
            record_failed_attempt(ip1)

        assert is_rate_limited(ip1) is True
        assert is_rate_limited(ip2) is False

    def test_record_failed_attempt_empty_ip(self) -> None:
        """空の IP では記録されない。"""
        record_failed_attempt("")
        # エラーが発生しないことを確認
        assert True

    def test_cleanup_old_rate_limit_entries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """古いレート制限エントリがクリーンアップされる。"""
        import time

        import src.web.app as app_module

        ip = "192.168.1.1"
        # 古い試行を記録
        old_time = time.time() - 400  # 5分以上前
        app_module.LOGIN_ATTEMPTS[ip] = [old_time]

        # クリーンアップ間隔を超えた状態にする
        app_module._last_cleanup_time = time.time() - 4000

        # is_rate_limited 呼び出しでクリーンアップがトリガーされる
        is_rate_limited(ip)

        # 古いエントリは削除される (空になるか、有効なものだけ残る)
        assert (
            ip not in app_module.LOGIN_ATTEMPTS
            or len(app_module.LOGIN_ATTEMPTS[ip]) == 0
        )


# ===========================================================================
# フォーム送信クールタイムユーティリティのテスト
# ===========================================================================


class TestFormCooldownFunctions:
    """is_form_cooldown_active / record_form_submit のテスト。"""

    def test_form_cooldown_not_active_initially(self) -> None:
        """初回送信時はクールタイムがアクティブでない。"""
        assert is_form_cooldown_active("user@example.com", "/settings") is False

    def test_form_cooldown_active_after_submission(self) -> None:
        """送信後はクールタイムがアクティブになる。"""
        email = "user@example.com"
        path = "/settings"
        record_form_submit(email, path)
        assert is_form_cooldown_active(email, path) is True

    def test_form_cooldown_per_path(self) -> None:
        """パスごとに独立してクールタイムが適用される。"""
        email = "user@example.com"
        record_form_submit(email, "/settings")

        assert is_form_cooldown_active(email, "/settings") is True
        assert is_form_cooldown_active(email, "/password") is False

    def test_form_cooldown_per_user(self) -> None:
        """ユーザーごとに独立してクールタイムが適用される。"""
        path = "/settings"
        record_form_submit("user1@example.com", path)

        assert is_form_cooldown_active("user1@example.com", path) is True
        assert is_form_cooldown_active("user2@example.com", path) is False

    def test_cleanup_form_cooldown_entries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """古いフォームクールタイムエントリがクリーンアップされる。"""
        import time

        import src.web.app as app_module

        key = "user@example.com:/settings"
        # 古いエントリを記録 (クールタイムの5倍以上前)
        old_time = time.time() - 100  # 十分古い時間
        app_module.FORM_SUBMIT_TIMES[key] = old_time

        # クリーンアップ間隔を超えた状態にする
        app_module._form_cooldown_last_cleanup_time = time.time() - 4000

        # クリーンアップを実行
        _cleanup_form_cooldown_entries()

        # 古いエントリは削除される
        assert key not in app_module.FORM_SUBMIT_TIMES


class TestRateLimitCleanupEmptyCache:
    """空キャッシュに対するレート制限クリーンアップが安全に動作することを検証。"""

    def test_cleanup_on_empty_cache_does_not_crash(self) -> None:
        """LOGIN_ATTEMPTS が空でもクリーンアップがクラッシュしない."""
        import src.web.app as web_app_module
        from src.web.app import LOGIN_ATTEMPTS

        assert len(LOGIN_ATTEMPTS) == 0
        web_app_module._last_cleanup_time = 0
        _cleanup_old_rate_limit_entries()
        assert len(LOGIN_ATTEMPTS) == 0
        assert web_app_module._last_cleanup_time > 0

    def test_is_rate_limited_on_empty_returns_false(self) -> None:
        """空状態で is_rate_limited が False を返す."""
        from src.web.app import LOGIN_ATTEMPTS

        assert len(LOGIN_ATTEMPTS) == 0
        result = is_rate_limited("10.0.0.1")
        assert result is False


class TestRateLimitCleanupAllExpired:
    """全エントリが期限切れの場合にキャッシュが空になることを検証。"""

    def test_all_expired_entries_removed(self) -> None:
        """全エントリが期限切れなら全て削除されキャッシュが空になる."""
        import time

        import src.web.app as web_app_module
        from src.web.app import LOGIN_ATTEMPTS

        old_time = time.time() - 400
        LOGIN_ATTEMPTS["10.0.0.1"] = [old_time]
        LOGIN_ATTEMPTS["10.0.0.2"] = [old_time - 100]
        LOGIN_ATTEMPTS["10.0.0.3"] = [old_time - 200]

        web_app_module._last_cleanup_time = 0
        _cleanup_old_rate_limit_entries()

        assert len(LOGIN_ATTEMPTS) == 0


class TestRateLimitCleanupTriggerViaPublicAPI:
    """is_rate_limited がクリーンアップを内部的にトリガーすることを検証。"""

    def test_is_rate_limited_triggers_cleanup(self) -> None:
        """is_rate_limited がクリーンアップをトリガーする."""
        import time

        import src.web.app as web_app_module
        from src.web.app import LOGIN_ATTEMPTS

        old_ip = "10.0.0.50"
        LOGIN_ATTEMPTS[old_ip] = [time.time() - 400]

        web_app_module._last_cleanup_time = 0
        is_rate_limited("10.0.0.51")

        assert old_ip not in LOGIN_ATTEMPTS

    def test_cleanup_updates_last_cleanup_time(self) -> None:
        """クリーンアップ実行後に _last_cleanup_time が更新される."""
        import src.web.app as web_app_module

        web_app_module._last_cleanup_time = 0
        is_rate_limited("10.0.0.52")

        assert web_app_module._last_cleanup_time > 0


class TestFormCooldownCleanupEmptyCache:
    """空キャッシュに対するフォームクールダウンクリーンアップが安全に動作することを検証。"""

    def test_cleanup_on_empty_cache_does_not_crash(self) -> None:
        """FORM_SUBMIT_TIMES が空でもクリーンアップがクラッシュしない."""
        import src.web.app as app_module
        from src.web.app import FORM_SUBMIT_TIMES

        assert len(FORM_SUBMIT_TIMES) == 0
        app_module._form_cooldown_last_cleanup_time = 0
        _cleanup_form_cooldown_entries()
        assert len(FORM_SUBMIT_TIMES) == 0
        assert app_module._form_cooldown_last_cleanup_time > 0

    def test_is_form_cooldown_on_empty_returns_false(self) -> None:
        """空状態で is_form_cooldown_active が False を返す."""
        from src.web.app import FORM_SUBMIT_TIMES

        assert len(FORM_SUBMIT_TIMES) == 0
        result = is_form_cooldown_active("user@example.com", "/test")
        assert result is False


class TestFormCooldownCleanupAllExpired:
    """全エントリが期限切れの場合にキャッシュが空になることを検証。"""

    def test_all_expired_entries_removed(self) -> None:
        """全エントリが期限切れなら全て削除されキャッシュが空になる."""
        import time

        import src.web.app as app_module
        from src.web.app import FORM_SUBMIT_TIMES

        old_time = time.time() - 100
        FORM_SUBMIT_TIMES["user1@example.com:/path1"] = old_time
        FORM_SUBMIT_TIMES["user2@example.com:/path2"] = old_time - 100
        FORM_SUBMIT_TIMES["user3@example.com:/path3"] = old_time - 200

        app_module._form_cooldown_last_cleanup_time = 0
        _cleanup_form_cooldown_entries()

        assert len(FORM_SUBMIT_TIMES) == 0


class TestFormCooldownCleanupTriggerViaPublicAPI:
    """is_form_cooldown_active がクリーンアップを内部的にトリガーすることを検証。"""

    def test_is_form_cooldown_triggers_cleanup(self) -> None:
        """is_form_cooldown_active がクリーンアップをトリガーする."""
        import time

        import src.web.app as app_module
        from src.web.app import FORM_SUBMIT_TIMES

        old_key = "old@example.com:/old"
        FORM_SUBMIT_TIMES[old_key] = time.time() - 100

        app_module._form_cooldown_last_cleanup_time = 0
        is_form_cooldown_active("new@example.com", "/new")

        assert old_key not in FORM_SUBMIT_TIMES

    def test_cleanup_updates_last_cleanup_time(self) -> None:
        """クリーンアップ実行後に _form_cooldown_last_cleanup_time が更新される."""
        import src.web.app as app_module

        app_module._form_cooldown_last_cleanup_time = 0
        is_form_cooldown_active("new@example.com", "/new")

        assert app_module._form_cooldown_last_cleanup_time > 0

    def test_form_cooldown_guard_allows_zero(self) -> None:
        """_form_cooldown_last_cleanup_time=0 でもクリーンアップが実行される."""
        import time

        import src.web.app as app_module
        from src.web.app import FORM_SUBMIT_TIMES

        old_key = "guard@example.com:/guard"
        FORM_SUBMIT_TIMES[old_key] = time.time() - 100

        app_module._form_cooldown_last_cleanup_time = 0
        _cleanup_form_cooldown_entries()

        assert old_key not in FORM_SUBMIT_TIMES
        assert app_module._form_cooldown_last_cleanup_time > 0

    def test_form_cooldown_interval_respected(self) -> None:
        """フォームクールダウンクリーンアップ間隔が未経過ならスキップされる."""
        import time

        import src.web.app as app_module
        from src.web.app import FORM_SUBMIT_TIMES

        old_key = "interval@example.com:/interval"
        FORM_SUBMIT_TIMES[old_key] = time.time() - 100

        app_module._form_cooldown_last_cleanup_time = time.time() - 1
        _cleanup_form_cooldown_entries()

        # 間隔未経過なのでエントリはまだ残る
        assert old_key in FORM_SUBMIT_TIMES
        FORM_SUBMIT_TIMES.pop(old_key, None)

    def test_form_cooldown_keeps_active_removes_expired(self) -> None:
        """期限切れエントリは削除、アクティブは保持."""
        import time

        import src.web.app as app_module
        from src.web.app import FORM_SUBMIT_TIMES

        expired_key = "expired@example.com:/expired"
        active_key = "active@example.com:/active"
        FORM_SUBMIT_TIMES[expired_key] = time.time() - 100
        FORM_SUBMIT_TIMES[active_key] = time.time()

        app_module._form_cooldown_last_cleanup_time = 0
        _cleanup_form_cooldown_entries()

        assert expired_key not in FORM_SUBMIT_TIMES
        assert active_key in FORM_SUBMIT_TIMES
        FORM_SUBMIT_TIMES.pop(active_key, None)


# ===========================================================================
# Role Panel Post to Discord ルート 結合テスト
# ===========================================================================


class TestRolePanelPostToDiscord:
    """ロールパネルをDiscordに投稿するエンドポイントのテスト。"""

    async def test_post_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.post(
            "/rolepanels/1/post",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_post_nonexistent_panel(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないパネルへの投稿は一覧にリダイレクト。"""
        response = await authenticated_client.post(
            "/rolepanels/99999/post",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/rolepanels"

    async def test_edit_already_posted_panel(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """既に投稿済みのパネルは編集される。"""
        from unittest.mock import AsyncMock

        import src.web.app as app_module

        # Discord API をモック (edit)
        monkeypatch.setattr(
            app_module,
            "edit_role_panel_in_discord",
            AsyncMock(return_value=(True, None)),
        )

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Already Posted",
            message_id="111111111111111111",  # 投稿済み
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/post",
            follow_redirects=False,
        )
        assert response.status_code == 302
        # 編集成功
        assert "updated+to+discord" in response.headers["location"].lower()

        # message_id は変わらない (編集)
        await db_session.refresh(panel)
        assert panel.message_id == "111111111111111111"

    async def test_post_success(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Discord への投稿成功時はメッセージIDが保存される。"""
        from unittest.mock import AsyncMock

        import src.web.app as app_module

        # Discord API をモック
        monkeypatch.setattr(
            app_module,
            "post_role_panel_to_discord",
            AsyncMock(return_value=(True, "222222222222222222", None)),
        )

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
            f"/rolepanels/{panel.id}/post",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "success=Posted" in response.headers["location"]

        # メッセージIDが保存されていることを確認
        await db_session.refresh(panel)
        assert panel.message_id == "222222222222222222"

    async def test_post_failure(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Discord API エラー時はエラーメッセージを表示。"""
        from unittest.mock import AsyncMock

        import src.web.app as app_module

        # Discord API をモック (失敗)
        monkeypatch.setattr(
            app_module,
            "post_role_panel_to_discord",
            AsyncMock(return_value=(False, None, "Bot lacks permissions")),
        )

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
            f"/rolepanels/{panel.id}/post",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "Failed" in response.headers["location"]

    async def test_post_reaction_panel_with_reactions(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """リアクション式パネル投稿後にリアクションが追加される。"""
        from unittest.mock import AsyncMock

        import src.web.app as app_module

        # Discord API をモック
        monkeypatch.setattr(
            app_module,
            "post_role_panel_to_discord",
            AsyncMock(return_value=(True, "333333333333333333", None)),
        )
        monkeypatch.setattr(
            app_module,
            "add_reactions_to_message",
            AsyncMock(return_value=(True, None)),
        )

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",  # リアクション式
            title="Test Reaction Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # アイテムを追加
        item = RolePanelItem(
            panel_id=panel.id,
            role_id="444444444444444444",
            emoji="⭐",
            position=0,
        )
        db_session.add(item)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/post",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "success=Posted" in response.headers["location"]

        # add_reactions_to_message が呼ばれたことを確認
        app_module.add_reactions_to_message.assert_called_once()

    async def test_post_reaction_panel_with_reaction_failure(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """リアクション追加失敗時は警告メッセージを表示。"""
        from unittest.mock import AsyncMock

        import src.web.app as app_module

        # Discord API をモック
        monkeypatch.setattr(
            app_module,
            "post_role_panel_to_discord",
            AsyncMock(return_value=(True, "333333333333333333", None)),
        )
        monkeypatch.setattr(
            app_module,
            "add_reactions_to_message",
            AsyncMock(return_value=(False, "Rate limited")),
        )

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Test Reaction Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        item = RolePanelItem(
            panel_id=panel.id,
            role_id="444444444444444444",
            emoji="⭐",
            position=0,
        )
        db_session.add(item)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/post",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "reactions+failed" in response.headers["location"].lower()

    async def test_edit_reaction_panel_clears_existing_reactions(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """既存のリアクションパネルを編集すると clear_existing=True で呼ばれる。"""
        from unittest.mock import AsyncMock

        import src.web.app as app_module

        # Discord API をモック (edit)
        monkeypatch.setattr(
            app_module,
            "edit_role_panel_in_discord",
            AsyncMock(return_value=(True, None)),
        )
        mock_add_reactions = AsyncMock(return_value=(True, None))
        monkeypatch.setattr(
            app_module,
            "add_reactions_to_message",
            mock_add_reactions,
        )

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",  # リアクション式
            title="Existing Reaction Panel",
            message_id="111111111111111111",  # 投稿済み
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # アイテムを追加
        item = RolePanelItem(
            panel_id=panel.id,
            role_id="444444444444444444",
            emoji="⭐",
            position=0,
        )
        db_session.add(item)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/post",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "updated" in response.headers["location"].lower()

        # add_reactions_to_message が clear_existing=True で呼ばれたことを確認
        mock_add_reactions.assert_called_once()
        call_kwargs = mock_add_reactions.call_args.kwargs
        assert call_kwargs.get("clear_existing") is True

    async def test_post_cooldown_active(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """クールタイム中は投稿できない。"""
        from src.web.app import record_form_submit

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # クールタイムを記録
        record_form_submit("test@example.com", f"/rolepanels/{panel.id}/post")

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/post",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "wait" in response.headers["location"].lower()


# ===========================================================================
# Role Panel Edit テスト
# ===========================================================================


class TestRolePanelEdit:
    """ロールパネルの編集機能のテスト。"""

    async def test_edit_requires_auth(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """未認証時はログインページにリダイレクト。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await client.post(
            f"/rolepanels/{panel.id}/edit",
            data={"title": "New Title"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    async def test_edit_nonexistent_panel(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """存在しないパネルの編集は一覧にリダイレクト。"""
        response = await authenticated_client.post(
            "/rolepanels/99999/edit",
            data={"title": "New Title"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/rolepanels" in response.headers["location"]

    async def test_edit_success(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """正常系: タイトルと説明を更新。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Old Title",
            description="Old Description",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/edit",
            data={"title": "New Title", "description": "New Description"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "updated" in response.headers["location"].lower()

        await db_session.refresh(panel)
        assert panel.title == "New Title"
        assert panel.description == "New Description"

    async def test_edit_clears_description(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """空の説明を送信すると説明がクリアされる。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Test Panel",
            description="Old Description",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/edit",
            data={"title": "Test Panel", "description": ""},
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(panel)
        assert panel.description is None

    async def test_edit_empty_title_rejected(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """空のタイトルはエラー。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/edit",
            data={"title": "", "description": "Test"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "required" in response.headers["location"].lower()

    async def test_edit_title_too_long(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """タイトルが長すぎるとエラー。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/edit",
            data={"title": "x" * 101, "description": ""},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "100" in response.headers["location"]

    async def test_edit_description_too_long(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """説明が長すぎるとエラー。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/edit",
            data={"title": "Test", "description": "x" * 2001},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "2000" in response.headers["location"]


# ===========================================================================
# Role Panel Item CSRF / Cooldown テスト
# ===========================================================================


class TestRolePanelItemCsrfAndCooldown:
    """ロールアイテム操作の CSRF とクールダウンのテスト。"""

    async def test_add_item_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """CSRF トークン検証失敗時はエラーを返す。"""
        # CSRF 検証をモックしない (テストで有効化)
        from unittest.mock import patch

        from src.web.app import generate_csrf_token

        # ログイン
        csrf_token = generate_csrf_token()
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        client.cookies.set("session", login_response.cookies.get("session") or "")

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/rolepanels/{panel.id}/items/add",
                data={
                    "emoji": "⭐",
                    "role_id": "111222333444555666",
                    "csrf_token": "invalid_token",
                },
                follow_redirects=False,
            )
        assert response.status_code == 403
        assert "Invalid security token" in response.text

    async def test_add_item_cooldown_active(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """クールタイム中はアイテム追加できない。"""
        from src.web.app import record_form_submit

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # クールタイムを記録
        record_form_submit("test@example.com", f"/rolepanels/{panel.id}/items/add")

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={
                "emoji": "⭐",
                "role_id": "111222333444555666",
            },
            follow_redirects=False,
        )
        assert response.status_code == 429
        assert "Please wait" in response.text

    async def test_delete_item_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """CSRF トークン検証失敗時はリダイレクト。"""
        from unittest.mock import patch

        from src.web.app import generate_csrf_token

        # ログイン
        csrf_token = generate_csrf_token()
        login_response = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        client.cookies.set("session", login_response.cookies.get("session") or "")

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
            emoji="⭐",
            position=0,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/rolepanels/{panel.id}/items/{item.id}/delete",
                data={"csrf_token": "invalid_token"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert f"/rolepanels/{panel.id}" in response.headers["location"]

        # アイテムが削除されていないことを確認
        result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.id == item.id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_delete_item_cooldown_active(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """クールタイム中はアイテム削除がスキップされる。"""
        from src.web.app import record_form_submit

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
            emoji="⭐",
            position=0,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        # クールタイムを記録
        record_form_submit(
            "test@example.com", f"/rolepanels/{panel.id}/items/{item.id}/delete"
        )

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/{item.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302

        # アイテムが削除されていないことを確認
        result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.id == item.id)
        )
        assert result.scalar_one_or_none() is not None


# ===========================================================================
# Role Panel Item Duplicate Emoji テスト
# ===========================================================================


class TestRolePanelItemDuplicateEmoji:
    """同じ絵文字のアイテム追加時のエラーハンドリングテスト。"""

    async def test_add_duplicate_emoji_returns_error(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """同じ絵文字は追加できない (IntegrityError)。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        # 最初のアイテムを追加
        item = RolePanelItem(
            panel_id=panel.id,
            role_id="111222333444555666",
            emoji="⭐",
            position=0,
        )
        db_session.add(item)
        await db_session.commit()

        # 同じ絵文字で2つ目のアイテムを追加しようとする
        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={
                "emoji": "⭐",
                "role_id": "222333444555666777",
                "position": "1",
            },
            follow_redirects=False,
        )
        # IntegrityError がキャッチされエラーレスポンスが返される
        assert response.status_code == 200
        assert "already used" in response.text


# ===========================================================================
# Role Panel Get Known Roles by Guild テスト
# ===========================================================================


class TestGetKnownRolesByGuild:
    """_get_known_roles_by_guild 関数のテスト。"""

    async def test_returns_role_ids_grouped_by_guild(
        self,
        db_session: AsyncSession,
    ) -> None:
        """ギルドごとにロールIDがグループ化される。"""
        from src.web.app import _get_known_roles_by_guild

        # 2つのギルドに属するパネルとアイテムを作成
        panel1 = RolePanel(
            guild_id="111111111111111111",
            channel_id="123456789012345678",
            panel_type="button",
            title="Guild 1 Panel",
        )
        panel2 = RolePanel(
            guild_id="222222222222222222",
            channel_id="987654321098765432",
            panel_type="button",
            title="Guild 2 Panel",
        )
        db_session.add_all([panel1, panel2])
        await db_session.commit()
        await db_session.refresh(panel1)
        await db_session.refresh(panel2)

        # アイテムを追加
        items = [
            RolePanelItem(
                panel_id=panel1.id,
                role_id="role_a",
                emoji="⭐",
                position=0,
            ),
            RolePanelItem(
                panel_id=panel1.id,
                role_id="role_b",
                emoji="🎮",
                position=1,
            ),
            RolePanelItem(
                panel_id=panel2.id,
                role_id="role_c",
                emoji="🎵",
                position=0,
            ),
        ]
        db_session.add_all(items)
        await db_session.commit()

        result = await _get_known_roles_by_guild(db_session)

        assert "111111111111111111" in result
        assert "222222222222222222" in result
        assert sorted(result["111111111111111111"]) == ["role_a", "role_b"]
        assert result["222222222222222222"] == ["role_c"]

    async def test_returns_empty_dict_when_no_items(
        self,
        db_session: AsyncSession,
    ) -> None:
        """アイテムがない場合は空の辞書を返す。"""
        from src.web.app import _get_known_roles_by_guild

        result = await _get_known_roles_by_guild(db_session)
        assert result == {}


# ===========================================================================
# Role Panel Copy (Duplicate) テスト
# ===========================================================================


class TestRolePanelCopy:
    """ロールパネルのコピー機能のテスト。"""

    async def test_copy_requires_auth(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """未認証時はログインページにリダイレクト。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await client.post(
            f"/rolepanels/{panel.id}/copy",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    async def test_copy_nonexistent_panel(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """存在しないパネルのコピーは一覧にリダイレクト。"""
        response = await authenticated_client.post(
            "/rolepanels/99999/copy",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/rolepanels" in response.headers["location"]

    async def test_copy_success(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """パネルが正常にコピーされる。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Original Panel",
            description="Original Desc",
            color=0x3498DB,
            use_embed=True,
            message_id="111111111111111111",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        item = RolePanelItem(
            panel_id=panel.id,
            role_id="111222333444555666",
            emoji="🎮",
            label="Gamer",
            style="primary",
            position=0,
        )
        db_session.add(item)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/copy",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "duplicated" in response.headers["location"].lower()

        # コピーされたパネルを確認
        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Original Panel (Copy)")
        )
        copied = result.scalar_one_or_none()
        assert copied is not None
        assert copied.guild_id == "123456789012345678"
        assert copied.description == "Original Desc"
        assert copied.color == 0x3498DB
        assert copied.message_id is None  # 未投稿
        assert copied.id != panel.id

        # アイテムもコピーされていることを確認
        items_result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == copied.id)
        )
        copied_items = list(items_result.scalars().all())
        assert len(copied_items) == 1
        assert copied_items[0].emoji == "🎮"
        assert copied_items[0].role_id == "111222333444555666"
        assert copied_items[0].label == "Gamer"
        assert copied_items[0].style == "primary"

    async def test_copy_preserves_panel_type(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """コピーがパネルタイプ (reaction) を保持する。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Reaction Panel",
            remove_reaction=True,
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/copy",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Reaction Panel (Copy)")
        )
        copied = result.scalar_one_or_none()
        assert copied is not None
        assert copied.panel_type == "reaction"
        assert copied.remove_reaction is True


# ===========================================================================
# Role Panel Save Draft テスト
# ===========================================================================


class TestRolePanelSaveDraft:
    """パネル途中保存のテスト。"""

    async def test_save_draft_without_items(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """アイテムなしでも途中保存できる。"""
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "Draft Panel",
            "description": "Draft Desc",
            "action": "save_draft",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/rolepanels/" in response.headers["location"]

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Draft Panel")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None
        assert panel.description == "Draft Desc"

    async def test_save_draft_with_items(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """アイテム付きで途中保存できる。"""
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "Draft With Items",
            "action": "save_draft",
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

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.title == "Draft With Items")
        )
        panel = result.scalar_one_or_none()
        assert panel is not None

        items_result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        items = list(items_result.scalars().all())
        assert len(items) == 1

    async def test_create_action_requires_items(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """action=create ではアイテムが必須。"""
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "Test Panel",
            "action": "create",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "At least one role item is required" in response.text

    async def test_save_draft_still_validates_title(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """途中保存でもタイトルは必須。"""
        form_data = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321098765432",
            "panel_type": "button",
            "title": "",
            "action": "save_draft",
        }
        response = await authenticated_client.post(
            "/rolepanels/new",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Title is required" in response.text


# ===========================================================================
# Role Panel Reorder テスト
# ===========================================================================


class TestRolePanelReorder:
    """ロールパネルアイテムの並べ替えテスト。"""

    async def test_reorder_requires_auth(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """未認証時は 401 を返す。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await client.post(
            f"/rolepanels/{panel.id}/items/reorder",
            json={"item_ids": [], "csrf_token": ""},
        )
        assert response.status_code == 401

    async def test_reorder_nonexistent_panel(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """存在しないパネルは 404 を返す。"""
        response = await authenticated_client.post(
            "/rolepanels/99999/items/reorder",
            json={"item_ids": [], "csrf_token": "test"},
        )
        assert response.status_code == 404

    async def test_reorder_success(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """アイテムの順番が正しく更新される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        item1 = RolePanelItem(
            panel_id=panel.id,
            role_id="111",
            emoji="🎮",
            position=0,
        )
        item2 = RolePanelItem(
            panel_id=panel.id,
            role_id="222",
            emoji="🎯",
            position=1,
        )
        item3 = RolePanelItem(
            panel_id=panel.id,
            role_id="333",
            emoji="🎲",
            position=2,
        )
        db_session.add_all([item1, item2, item3])
        await db_session.commit()
        await db_session.refresh(item1)
        await db_session.refresh(item2)
        await db_session.refresh(item3)

        # 逆順に並べ替え: item3, item1, item2
        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/reorder",
            json={
                "item_ids": [item3.id, item1.id, item2.id],
                "csrf_token": "test",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

        # DB で position が更新されていることを確認
        await db_session.refresh(item1)
        await db_session.refresh(item2)
        await db_session.refresh(item3)
        assert item3.position == 0
        assert item1.position == 1
        assert item2.position == 2


# ===========================================================================
# Role Panel Edit Color テスト
# ===========================================================================


class TestRolePanelEditColor:
    """パネル編集時のカラー更新テスト。"""

    async def test_edit_updates_color(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Embed パネルの色が更新される。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
            use_embed=True,
            color=0x3498DB,
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/edit",
            data={
                "title": "Test Panel",
                "description": "",
                "color": "#FF0000",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(panel)
        assert panel.color == 0xFF0000

    async def test_edit_color_ignored_for_text_panel(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """テキストパネルではカラーが更新されない。"""
        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
            use_embed=False,
            color=None,
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/edit",
            data={
                "title": "Test Panel",
                "description": "",
                "color": "#FF0000",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(panel)
        assert panel.color is None


# ===========================================================================
# Role Panel Add Item Position Auto-Calc テスト
# ===========================================================================


class TestRolePanelAddItemAutoPosition:
    """アイテム追加時の position 自動算出テスト。"""

    async def test_auto_position_first_item(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """最初のアイテムは position=0 になる。"""
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
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        items_result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.panel_id == panel.id)
        )
        items = list(items_result.scalars().all())
        assert len(items) == 1
        assert items[0].position == 0

    async def test_auto_position_increments(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """既存アイテムの max(position) + 1 になる。"""
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
            role_id="111",
            emoji="🎮",
            position=5,
        )
        db_session.add(item)
        await db_session.commit()

        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/items/add",
            data={
                "emoji": "🎯",
                "role_id": "222333444555666777",
                "label": "Target",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        items_result = await db_session.execute(
            select(RolePanelItem)
            .where(RolePanelItem.panel_id == panel.id)
            .order_by(RolePanelItem.position)
        )
        items = list(items_result.scalars().all())
        assert len(items) == 2
        assert items[1].position == 6


# ===========================================================================
# CSRF 検証失敗テスト (各エンドポイント)
# ===========================================================================


class TestCsrfValidationFailures:
    """CSRF トークン検証失敗時のテスト。"""

    async def _login_client(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> AsyncClient:
        """ログイン済みクライアントを返す (CSRF モックなし)。"""
        from src.web.app import generate_csrf_token

        csrf_token = generate_csrf_token()
        resp = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        client.cookies.set("session", resp.cookies.get("session") or "")
        return client

    async def test_sticky_delete_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """sticky_delete の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        sticky = StickyMessage(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            title="Test",
            description="Test desc",
        )
        db_session.add(sticky)
        await db_session.commit()

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/sticky/{sticky.channel_id}/delete",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/sticky" in response.headers["location"]

    async def test_bump_config_delete_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """bump_config_delete の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        bump = BumpConfig(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
        )
        db_session.add(bump)
        await db_session.commit()

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/bump/config/{bump.guild_id}/delete",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/bump" in response.headers["location"]

    async def test_bump_reminder_delete_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """bump_reminder_delete の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        reminder = BumpReminder(
            guild_id="123456789012345678",
            channel_id="111111111111111111",
            service_name="DISBOARD",
        )
        db_session.add(reminder)
        await db_session.commit()
        await db_session.refresh(reminder)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/bump/reminder/{reminder.id}/delete",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/bump" in response.headers["location"]

    async def test_bump_reminder_toggle_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """bump_reminder_toggle の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        reminder = BumpReminder(
            guild_id="123456789012345678",
            channel_id="111111111111111111",
            service_name="DISBOARD",
        )
        db_session.add(reminder)
        await db_session.commit()
        await db_session.refresh(reminder)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/bump/reminder/{reminder.id}/toggle",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/bump" in response.headers["location"]

    async def test_rolepanel_create_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
    ) -> None:
        """rolepanel_create_post の CSRF 失敗は 403。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                "/rolepanels/new",
                data={
                    "guild_id": "123456789012345678",
                    "channel_id": "987654321098765432",
                    "panel_type": "button",
                    "title": "Test",
                    "csrf_token": "bad",
                },
                follow_redirects=False,
            )
        assert response.status_code == 403
        assert "Invalid security token" in response.text

    async def test_rolepanel_copy_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """rolepanel_copy の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/rolepanels/{panel.id}/copy",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert f"/rolepanels/{panel.id}" in response.headers["location"]

    async def test_rolepanel_toggle_remove_reaction_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """rolepanel_toggle_remove_reaction の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/rolepanels/{panel.id}/toggle-remove-reaction",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert f"/rolepanels/{panel.id}" in response.headers["location"]

    async def test_rolepanel_post_to_discord_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """rolepanel_post_to_discord の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/rolepanels/{panel.id}/post",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302

    async def test_reorder_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """rolepanel_reorder_items の CSRF 失敗は 403。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/rolepanels/{panel.id}/items/reorder",
                json={"item_ids": [], "csrf_token": "bad"},
            )
        assert response.status_code == 403

    async def test_autoban_create_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
    ) -> None:
        """autoban_create_post の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                "/autoban/new",
                data={
                    "guild_id": "123",
                    "rule_type": "no_avatar",
                    "action": "ban",
                    "csrf_token": "bad",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/autoban/new" in response.headers["location"]

    async def test_autoban_delete_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """autoban_delete の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="no_avatar",
            action="ban",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/autoban/{rule.id}/delete",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/autoban" in response.headers["location"]

    async def test_autoban_toggle_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """autoban_toggle の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="no_avatar",
            action="ban",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/autoban/{rule.id}/toggle",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/autoban" in response.headers["location"]

    async def test_autoban_settings_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
    ) -> None:
        """autoban_settings の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                "/autoban/settings",
                data={
                    "guild_id": "123",
                    "log_channel_id": "456",
                    "csrf_token": "bad",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/autoban/settings" in response.headers["location"]

    async def test_autoban_edit_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
        db_session: AsyncSession,
    ) -> None:
        """autoban_edit の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="no_avatar",
            action="ban",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                f"/autoban/{rule.id}/edit",
                data={"action": "kick", "csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert f"/autoban/{rule.id}/edit" in response.headers["location"]

    async def test_joinrole_create_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
    ) -> None:
        """joinrole_create の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                "/joinrole/new",
                data={
                    "guild_id": "123",
                    "role_id": "456",
                    "duration_hours": "24",
                    "csrf_token": "bad",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/joinrole" in response.headers["location"]

    async def test_joinrole_delete_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
    ) -> None:
        """joinrole_delete の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                "/joinrole/1/delete",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/joinrole" in response.headers["location"]

    async def test_joinrole_toggle_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
    ) -> None:
        """joinrole_toggle の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        await self._login_client(client, admin_user)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                "/joinrole/1/toggle",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/joinrole" in response.headers["location"]


# ===========================================================================
# クールダウンテスト (各エンドポイント)
# ===========================================================================


class TestCooldownEnforcement:
    """各エンドポイントのクールダウンテスト。"""

    async def test_sticky_delete_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """sticky_delete のクールダウン。"""
        from src.web.app import record_form_submit

        sticky = StickyMessage(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            title="Test",
            description="Test desc",
        )
        db_session.add(sticky)
        await db_session.commit()

        record_form_submit("test@example.com", f"/sticky/{sticky.channel_id}/delete")
        response = await authenticated_client.post(
            f"/sticky/{sticky.channel_id}/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/sticky" in response.headers["location"]

    async def test_bump_config_delete_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """bump_config_delete のクールダウン。"""
        from src.web.app import record_form_submit

        bump = BumpConfig(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
        )
        db_session.add(bump)
        await db_session.commit()

        record_form_submit("test@example.com", f"/bump/config/{bump.guild_id}/delete")
        response = await authenticated_client.post(
            f"/bump/config/{bump.guild_id}/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/bump" in response.headers["location"]

    async def test_bump_reminder_delete_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """bump_reminder_delete のクールダウン。"""
        from src.web.app import record_form_submit

        reminder = BumpReminder(
            guild_id="123456789012345678",
            channel_id="111111111111111111",
            service_name="DISBOARD",
        )
        db_session.add(reminder)
        await db_session.commit()
        await db_session.refresh(reminder)

        record_form_submit("test@example.com", f"/bump/reminder/{reminder.id}/delete")
        response = await authenticated_client.post(
            f"/bump/reminder/{reminder.id}/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/bump" in response.headers["location"]

    async def test_bump_reminder_toggle_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """bump_reminder_toggle のクールダウン。"""
        from src.web.app import record_form_submit

        reminder = BumpReminder(
            guild_id="123456789012345678",
            channel_id="111111111111111111",
            service_name="DISBOARD",
        )
        db_session.add(reminder)
        await db_session.commit()
        await db_session.refresh(reminder)

        record_form_submit("test@example.com", f"/bump/reminder/{reminder.id}/toggle")
        response = await authenticated_client.post(
            f"/bump/reminder/{reminder.id}/toggle",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/bump" in response.headers["location"]

    async def test_rolepanel_delete_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """rolepanel_delete のクールダウン。"""
        from src.web.app import record_form_submit

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        record_form_submit("test@example.com", f"/rolepanels/{panel.id}/delete")
        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/rolepanels" in response.headers["location"]

    async def test_rolepanel_copy_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """rolepanel_copy のクールダウン。"""
        from src.web.app import record_form_submit

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        record_form_submit("test@example.com", f"/rolepanels/{panel.id}/copy")
        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/copy",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/rolepanels" in response.headers["location"]

    async def test_rolepanel_toggle_remove_reaction_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """rolepanel_toggle_remove_reaction のクールダウン。"""
        from src.web.app import record_form_submit

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="reaction",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        record_form_submit(
            "test@example.com",
            f"/rolepanels/{panel.id}/toggle-remove-reaction",
        )
        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/toggle-remove-reaction",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302

    async def test_rolepanel_edit_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """rolepanel_edit のクールダウン。"""
        from src.web.app import record_form_submit

        panel = RolePanel(
            guild_id="123456789012345678",
            channel_id="987654321098765432",
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        record_form_submit("test@example.com", f"/rolepanels/{panel.id}/edit")
        response = await authenticated_client.post(
            f"/rolepanels/{panel.id}/edit",
            data={"title": "New Title"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "wait" in response.headers["location"].lower()

    async def test_rolepanel_create_cooldown(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """rolepanel_create_post のクールダウン。"""
        from src.web.app import record_form_submit

        record_form_submit("test@example.com", "/rolepanels/new")
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
                "item_emoji[]": "🎮",
                "item_role_id[]": "111",
                "item_label[]": "",
                "item_position[]": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 429
        assert "Please wait" in response.text

    async def test_autoban_create_cooldown(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """autoban_create_post のクールダウン。"""
        from src.web.app import record_form_submit

        record_form_submit("test@example.com", "/autoban/new")
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123",
                "rule_type": "no_avatar",
                "action": "ban",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/autoban" in response.headers["location"]

    async def test_autoban_delete_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """autoban_delete のクールダウン。"""
        from src.web.app import record_form_submit

        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="no_avatar",
            action="ban",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        record_form_submit("test@example.com", f"/autoban/{rule.id}/delete")
        response = await authenticated_client.post(
            f"/autoban/{rule.id}/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/autoban" in response.headers["location"]

    async def test_autoban_toggle_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """autoban_toggle のクールダウン。"""
        from src.web.app import record_form_submit

        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="no_avatar",
            action="ban",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        record_form_submit("test@example.com", f"/autoban/{rule.id}/toggle")
        response = await authenticated_client.post(
            f"/autoban/{rule.id}/toggle",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/autoban" in response.headers["location"]

    async def test_autoban_settings_cooldown(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """autoban_settings のクールダウン。"""
        from src.web.app import record_form_submit

        record_form_submit("test@example.com", "/autoban/settings")
        response = await authenticated_client.post(
            "/autoban/settings",
            data={
                "guild_id": "123",
                "log_channel_id": "456",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/autoban/settings" in response.headers["location"]

    async def test_autoban_edit_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """autoban_edit のクールダウン。"""
        from src.web.app import record_form_submit

        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="no_avatar",
            action="ban",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        record_form_submit("test@example.com", f"/autoban/{rule.id}/edit")
        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "kick"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/autoban/{rule.id}/edit" in response.headers["location"]

    async def test_joinrole_create_cooldown(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """joinrole_create のクールダウン。"""
        from src.web.app import record_form_submit

        record_form_submit("test@example.com", "/joinrole/new")
        response = await authenticated_client.post(
            "/joinrole/new",
            data={
                "guild_id": "123",
                "role_id": "456",
                "duration_hours": "24",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/joinrole" in response.headers["location"]

    async def test_joinrole_delete_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """joinrole_delete のクールダウン。"""
        from src.web.app import record_form_submit

        config = JoinRoleConfig(
            guild_id="123",
            role_id="456",
            duration_hours=24,
        )
        db_session.add(config)
        await db_session.commit()
        await db_session.refresh(config)

        record_form_submit("test@example.com", f"/joinrole/{config.id}/delete")
        response = await authenticated_client.post(
            f"/joinrole/{config.id}/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/joinrole" in response.headers["location"]

    async def test_joinrole_toggle_cooldown(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """joinrole_toggle のクールダウン。"""
        from src.web.app import record_form_submit

        config = JoinRoleConfig(
            guild_id="123",
            role_id="456",
            duration_hours=24,
        )
        db_session.add(config)
        await db_session.commit()
        await db_session.refresh(config)

        record_form_submit("test@example.com", f"/joinrole/{config.id}/toggle")
        response = await authenticated_client.post(
            f"/joinrole/{config.id}/toggle",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/joinrole" in response.headers["location"]

        # Config should not be toggled
        await db_session.refresh(config)
        assert config.enabled is True


# ===========================================================================
# Create ページ アイテムバリデーション エッジケーステスト
# ===========================================================================


class TestRolePanelCreateItemValidation:
    """パネル作成時のアイテムバリデーションのエッジケース。"""

    async def test_item_empty_emoji(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """空の絵文字はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
                "item_emoji[]": "",
                "item_role_id[]": "111",
                "item_label[]": "",
                "item_position[]": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Emoji is required" in response.text

    async def test_item_emoji_too_long(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """絵文字が65文字以上はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
                "item_emoji[]": "x" * 65,
                "item_role_id[]": "111",
                "item_label[]": "",
                "item_position[]": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "64 chars or less" in response.text

    async def test_item_invalid_emoji(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """不正な絵文字フォーマットはエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
                "item_emoji[]": "not_an_emoji",
                "item_role_id[]": "111",
                "item_label[]": "",
                "item_position[]": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Invalid emoji" in response.text

    async def test_item_empty_role_id(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """空のロール ID はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
                "item_emoji[]": "🎮",
                "item_role_id[]": "",
                "item_label[]": "",
                "item_position[]": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Role ID is required" in response.text

    async def test_item_invalid_role_id(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """非数値のロール ID はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
                "item_emoji[]": "🎮",
                "item_role_id[]": "not_a_number",
                "item_label[]": "",
                "item_position[]": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Role ID must be a number" in response.text

    async def test_item_label_too_long(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """ラベルが81文字以上はエラー。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
                "item_emoji[]": "🎮",
                "item_role_id[]": "111222333444555666",
                "item_label[]": "x" * 81,
                "item_position[]": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "80 chars or less" in response.text

    async def test_item_invalid_style_defaults(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """不正なスタイルはデフォルト (secondary) に置換される。"""
        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456789012345678",
                "channel_id": "987654321098765432",
                "panel_type": "button",
                "title": "Test",
                "item_emoji[]": "🎮",
                "item_role_id[]": "111222333444555666",
                "item_label[]": "Test",
                "item_style[]": "invalid_style",
                "item_position[]": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.emoji == "🎮")
        )
        item = result.scalar_one()
        assert item.style == "secondary"


# ===========================================================================
# Reorder 入力検証テスト
# ===========================================================================


class TestRolePanelReorderValidation:
    """reorder エンドポイントの入力検証テスト。"""

    async def test_reorder_invalid_item_ids_type(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """item_ids がリストでない場合は 400。"""
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
            f"/rolepanels/{panel.id}/items/reorder",
            json={"item_ids": "not_a_list", "csrf_token": "test"},
        )
        assert response.status_code == 400
        assert "Invalid item_ids" in response.json()["error"]


# ===========================================================================
# IntegrityError ハンドリングテスト (create 内)
# ===========================================================================


class TestRolePanelCreateIntegrityError:
    """パネル作成時の重複絵文字テスト。"""

    async def test_create_duplicate_emoji_in_items(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """同じ絵文字が2つ含まれている場合はエラー。"""
        from urllib.parse import urlencode

        form_body = urlencode(
            [
                ("guild_id", "123456789012345678"),
                ("channel_id", "987654321098765432"),
                ("panel_type", "button"),
                ("title", "Test"),
                ("item_emoji[]", "🎮"),
                ("item_role_id[]", "111"),
                ("item_label[]", ""),
                ("item_style[]", "secondary"),
                ("item_position[]", "0"),
                ("item_emoji[]", "🎮"),
                ("item_role_id[]", "222"),
                ("item_label[]", ""),
                ("item_style[]", "secondary"),
                ("item_position[]", "1"),
            ]
        )
        response = await authenticated_client.post(
            "/rolepanels/new",
            content=form_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Duplicate emoji" in response.text


# ===========================================================================
# Autoban ルート
# ===========================================================================


class TestAutobanRoutes:
    """/autoban ルートのテスト。"""

    async def test_autoban_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/autoban", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_autoban_list_empty(self, authenticated_client: AsyncClient) -> None:
        """ルールがない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/autoban")
        assert response.status_code == 200
        assert "No autoban rules configured" in response.text

    async def test_autoban_list_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ルールがある場合は一覧が表示される。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="username_match",
            action="ban",
            pattern="spammer",
        )
        db_session.add(rule)
        await db_session.commit()

        response = await authenticated_client.get("/autoban")
        assert response.status_code == 200
        assert "username_match" in response.text

    async def test_autoban_create_page(self, authenticated_client: AsyncClient) -> None:
        """作成フォームが表示される。"""
        response = await authenticated_client.get("/autoban/new")
        assert response.status_code == 200
        assert "Create Autoban Rule" in response.text

    async def test_autoban_create_page_requires_auth(self, client: AsyncClient) -> None:
        """作成フォームは認証が必要。"""
        response = await client.get("/autoban/new", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_autoban_create_username_match(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """username_match ルールを作成できる。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123456789012345678",
                "rule_type": "username_match",
                "action": "ban",
                "pattern": "spammer",
                "use_wildcard": "on",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

        result = await db_session.execute(select(AutoBanRule))
        rules = list(result.scalars().all())
        assert len(rules) == 1
        assert rules[0].pattern == "spammer"
        assert rules[0].use_wildcard is True

    async def test_autoban_create_account_age(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """account_age ルールを作成できる。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123456789012345678",
                "rule_type": "account_age",
                "action": "kick",
                "threshold_hours": "48",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(select(AutoBanRule))
        rules = list(result.scalars().all())
        assert len(rules) == 1
        assert rules[0].threshold_hours == 48
        assert rules[0].action == "kick"

    async def test_autoban_create_no_avatar(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """no_avatar ルールを作成できる。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123456789012345678",
                "rule_type": "no_avatar",
                "action": "ban",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(select(AutoBanRule))
        rules = list(result.scalars().all())
        assert len(rules) == 1
        assert rules[0].rule_type == "no_avatar"

    async def test_autoban_create_invalid_rule_type(
        self, authenticated_client: AsyncClient
    ) -> None:
        """無効な rule_type はリダイレクトされる。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123",
                "rule_type": "invalid_type",
                "action": "ban",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/autoban/new" in response.headers["location"]

    async def test_autoban_create_invalid_action(
        self, authenticated_client: AsyncClient
    ) -> None:
        """無効な action はリダイレクトされる。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123",
                "rule_type": "no_avatar",
                "action": "delete",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/autoban/new" in response.headers["location"]

    async def test_autoban_create_username_without_pattern(
        self, authenticated_client: AsyncClient
    ) -> None:
        """username_match で pattern なしはリダイレクトされる。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123",
                "rule_type": "username_match",
                "action": "ban",
                "pattern": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/autoban/new" in response.headers["location"]

    async def test_autoban_create_account_age_invalid_threshold(
        self, authenticated_client: AsyncClient
    ) -> None:
        """account_age で invalid threshold はリダイレクトされる。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123",
                "rule_type": "account_age",
                "action": "ban",
                "threshold_hours": "abc",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/autoban/new" in response.headers["location"]

    async def test_autoban_create_account_age_exceeds_max(
        self, authenticated_client: AsyncClient
    ) -> None:
        """account_age で 336 超はリダイレクトされる。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123",
                "rule_type": "account_age",
                "action": "ban",
                "threshold_hours": "500",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/autoban/new" in response.headers["location"]

    async def test_autoban_delete(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ルールを削除できる。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="no_avatar",
            action="ban",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

        result = await db_session.execute(
            select(AutoBanRule).where(AutoBanRule.id == rule.id)
        )
        assert result.scalar_one_or_none() is None

    async def test_autoban_delete_requires_auth(self, client: AsyncClient) -> None:
        """削除は認証が必要。"""
        response = await client.post("/autoban/1/delete", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_autoban_toggle(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ルールの有効/無効を切り替えられる。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="no_avatar",
            action="ban",
            is_enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/toggle",
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(rule)
        assert rule.is_enabled is False

    async def test_autoban_toggle_requires_auth(self, client: AsyncClient) -> None:
        """トグルは認証が必要。"""
        response = await client.post("/autoban/1/toggle", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_autoban_logs_requires_auth(self, client: AsyncClient) -> None:
        """ログは認証が必要。"""
        response = await client.get("/autoban/logs", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_autoban_logs_empty(self, authenticated_client: AsyncClient) -> None:
        """ログがない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/autoban/logs")
        assert response.status_code == 200
        assert "No autoban logs" in response.text

    async def test_autoban_logs_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ログがある場合は一覧が表示される。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="no_avatar",
            action="ban",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        log = AutoBanLog(
            guild_id="123456789012345678",
            user_id="999888777",
            username="baduser",
            rule_id=rule.id,
            action_taken="banned",
            reason="No avatar set",
        )
        db_session.add(log)
        await db_session.commit()

        response = await authenticated_client.get("/autoban/logs")
        assert response.status_code == 200
        assert "baduser" in response.text
        assert "banned" in response.text

    async def test_autoban_settings_requires_auth(self, client: AsyncClient) -> None:
        """設定ページは認証が必要。"""
        response = await client.get("/autoban/settings", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_autoban_settings_post_requires_auth(
        self, client: AsyncClient
    ) -> None:
        """設定の POST は認証が必要。"""
        response = await client.post(
            "/autoban/settings",
            data={"guild_id": "123", "log_channel_id": "456"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_autoban_settings_get(
        self, authenticated_client: AsyncClient
    ) -> None:
        """設定ページが表示される。"""
        response = await authenticated_client.get("/autoban/settings")
        assert response.status_code == 200
        assert "Autoban Settings" in response.text

    async def test_autoban_settings_post_saves_config(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """設定を保存できる。"""
        response = await authenticated_client.post(
            "/autoban/settings",
            data={
                "guild_id": "123456789012345678",
                "log_channel_id": "987654321098765432",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/autoban/settings" in response.headers["location"]

        result = await db_session.execute(select(AutoBanConfig))
        configs = list(result.scalars().all())
        assert len(configs) == 1
        assert configs[0].guild_id == "123456789012345678"
        assert configs[0].log_channel_id == "987654321098765432"

    async def test_autoban_settings_post_updates_config(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """既存の設定を更新できる。"""
        config = AutoBanConfig(
            guild_id="123456789012345678",
            log_channel_id="111111111111111111",
        )
        db_session.add(config)
        await db_session.commit()

        response = await authenticated_client.post(
            "/autoban/settings",
            data={
                "guild_id": "123456789012345678",
                "log_channel_id": "222222222222222222",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(config)
        assert config.log_channel_id == "222222222222222222"

    async def test_autoban_settings_post_clears_channel(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """ログチャンネルを空にできる (None に設定)。"""
        config = AutoBanConfig(
            guild_id="123456789012345678",
            log_channel_id="111111111111111111",
        )
        db_session.add(config)
        await db_session.commit()

        response = await authenticated_client.post(
            "/autoban/settings",
            data={
                "guild_id": "123456789012345678",
                "log_channel_id": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(config)
        assert config.log_channel_id is None

    async def test_autoban_settings_post_empty_guild_id(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """guild_id が空の場合は拒否される (422 or 302)。"""
        response = await authenticated_client.post(
            "/autoban/settings",
            data={
                "guild_id": "",
                "log_channel_id": "123",
            },
            follow_redirects=False,
        )
        assert response.status_code in (302, 422)

        result = await db_session.execute(select(AutoBanConfig))
        assert list(result.scalars().all()) == []

    # --- Edit ---

    async def test_autoban_edit_get_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/autoban/1/edit", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_autoban_edit_get_page(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """編集ページが表示される。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="username_match",
            action="ban",
            pattern="spammer",
            use_wildcard=True,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.get(f"/autoban/{rule.id}/edit")
        assert response.status_code == 200
        assert "Edit Autoban Rule" in response.text
        assert "spammer" in response.text

    async def test_autoban_edit_get_not_found(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないルールは /autoban にリダイレクト。"""
        response = await authenticated_client.get(
            "/autoban/99999/edit", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

    async def test_autoban_edit_post_username_match(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """username_match ルールを更新できる。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="username_match",
            action="ban",
            pattern="old",
            use_wildcard=False,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={
                "action": "kick",
                "pattern": "new_pattern",
                "use_wildcard": "on",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

        await db_session.refresh(rule)
        assert rule.action == "kick"
        assert rule.pattern == "new_pattern"
        assert rule.use_wildcard is True

    async def test_autoban_edit_post_account_age(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """account_age ルールを更新できる。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="account_age",
            action="ban",
            threshold_hours=24,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "kick", "threshold_hours": "48"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(rule)
        assert rule.action == "kick"
        assert rule.threshold_hours == 48

    async def test_autoban_edit_post_threshold_seconds(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """role_acquired ルールを更新できる。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="role_acquired",
            action="ban",
            threshold_seconds=30,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "kick", "threshold_seconds": "60"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(rule)
        assert rule.action == "kick"
        assert rule.threshold_seconds == 60

    async def test_autoban_edit_post_not_found(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないルールは /autoban にリダイレクト。"""
        response = await authenticated_client.post(
            "/autoban/99999/edit",
            data={"action": "ban"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

    async def test_autoban_edit_post_invalid_action(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """不正な action はリダイレクト。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="no_avatar",
            action="ban",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "invalid"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/edit" in response.headers["location"]

    @pytest.mark.parametrize("pattern", ["", "   "])
    async def test_autoban_edit_post_invalid_pattern(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        pattern: str,
    ) -> None:
        """username_match で空/空白パターンはリダイレクト。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="username_match",
            action="ban",
            pattern="old",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "ban", "pattern": pattern},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/edit" in response.headers["location"]

        await db_session.refresh(rule)
        assert rule.pattern == "old"

    @pytest.mark.parametrize("value", ["abc", "0", "337", "-1", ""])
    async def test_autoban_edit_post_threshold_hours_invalid(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        value: str,
    ) -> None:
        """account_age で不正な threshold_hours はリダイレクト。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="account_age",
            action="ban",
            threshold_hours=24,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "ban", "threshold_hours": value},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/edit" in response.headers["location"]

        await db_session.refresh(rule)
        assert rule.threshold_hours == 24

    @pytest.mark.parametrize("value", ["xyz", "0", "3601", "-5", ""])
    async def test_autoban_edit_post_threshold_seconds_invalid(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        value: str,
    ) -> None:
        """threshold_seconds で不正な値はリダイレクト。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="role_acquired",
            action="ban",
            threshold_seconds=60,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "ban", "threshold_seconds": value},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/edit" in response.headers["location"]

        await db_session.refresh(rule)
        assert rule.threshold_seconds == 60

    async def test_autoban_edit_post_threshold_hours_max_valid(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """account_age で 336 は有効な最大値。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="account_age",
            action="ban",
            threshold_hours=24,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "ban", "threshold_hours": "336"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

        await db_session.refresh(rule)
        assert rule.threshold_hours == 336

    async def test_autoban_edit_post_threshold_seconds_max_valid(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """threshold_seconds で 3600 は有効な最大値。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="vc_join",
            action="ban",
            threshold_seconds=60,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "ban", "threshold_seconds": "3600"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

        await db_session.refresh(rule)
        assert rule.threshold_seconds == 3600

    async def test_autoban_edit_post_no_avatar_only_action(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """no_avatar ルールは action のみ更新可能。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="no_avatar",
            action="ban",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "kick"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

        await db_session.refresh(rule)
        assert rule.action == "kick"

    async def test_autoban_edit_post_use_wildcard_unchecked(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """use_wildcard のチェックを外すと False になる。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="username_match",
            action="ban",
            pattern="spam",
            use_wildcard=True,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "ban", "pattern": "spam"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

        await db_session.refresh(rule)
        assert rule.use_wildcard is False

    async def test_autoban_edit_post_disabled_rule(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """無効なルールも編集できる。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="no_avatar",
            action="ban",
            is_enabled=False,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "kick"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

        await db_session.refresh(rule)
        assert rule.action == "kick"
        assert rule.is_enabled is False

    @pytest.mark.parametrize(
        ("rule_type", "seconds", "new_action", "new_seconds"),
        [
            ("message_post", 30, "kick", "120"),
            ("vc_join", 600, "ban", "1800"),
        ],
    )
    async def test_autoban_edit_post_threshold_seconds_rule(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        rule_type: str,
        seconds: int,
        new_action: str,
        new_seconds: str,
    ) -> None:
        """threshold_seconds 系ルールを更新できる。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type=rule_type,
            action="ban",
            threshold_seconds=seconds,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={
                "action": new_action,
                "threshold_seconds": new_seconds,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(rule)
        assert rule.action == new_action
        assert rule.threshold_seconds == int(new_seconds)

    async def test_autoban_edit_post_pattern_stripped(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """pattern の前後の空白はストリップされる。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="username_match",
            action="ban",
            pattern="old",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={"action": "ban", "pattern": "  spammer  "},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

        await db_session.refresh(rule)
        assert rule.pattern == "spammer"

    async def test_autoban_edit_get_displays_current_values(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """GET 編集ページに現在の値がプリフィルされる。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="account_age",
            action="kick",
            threshold_hours=72,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.get(f"/autoban/{rule.id}/edit")
        assert response.status_code == 200
        assert "72" in response.text
        assert "kick" in response.text

    async def test_autoban_edit_post_requires_auth(self, client: AsyncClient) -> None:
        """POST 認証なしでは /login にリダイレクト。"""
        response = await client.post(
            "/autoban/1/edit",
            data={"action": "ban"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    # --- vc_without_intro / msg_without_intro ---

    async def test_autoban_create_vc_without_intro(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """vc_without_intro ルールを作成できる。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123456789012345678",
                "rule_type": "vc_without_intro",
                "action": "ban",
                "required_channel_id": "987654321",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

        result = await db_session.execute(select(AutoBanRule))
        rules = list(result.scalars().all())
        assert len(rules) == 1
        assert rules[0].rule_type == "vc_without_intro"
        assert rules[0].required_channel_id == "987654321"

    async def test_autoban_create_msg_without_intro(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """msg_without_intro ルールを作成できる。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123456789012345678",
                "rule_type": "msg_without_intro",
                "action": "kick",
                "required_channel_id": "111222333",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(select(AutoBanRule))
        rules = list(result.scalars().all())
        assert len(rules) == 1
        assert rules[0].rule_type == "msg_without_intro"
        assert rules[0].action == "kick"

    async def test_autoban_create_intro_rule_no_channel(
        self, authenticated_client: AsyncClient
    ) -> None:
        """required_channel_id 未指定 → リダイレクト。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123456789012345678",
                "rule_type": "vc_without_intro",
                "action": "ban",
                "required_channel_id": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/autoban/new" in response.headers["location"]

    async def test_autoban_create_intro_rule_non_digit(
        self, authenticated_client: AsyncClient
    ) -> None:
        """required_channel_id が数字でない → リダイレクト。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123456789012345678",
                "rule_type": "msg_without_intro",
                "action": "ban",
                "required_channel_id": "abc",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/autoban/new" in response.headers["location"]

    async def test_autoban_edit_intro_rule(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """intro ルールの required_channel_id を編集できる。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="vc_without_intro",
            action="ban",
            required_channel_id="111",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={
                "action": "kick",
                "required_channel_id": "222",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(rule)
        assert rule.action == "kick"
        assert rule.required_channel_id == "222"

    async def test_autoban_edit_intro_rule_empty_channel(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """intro ルール編集で channel 未指定 → リダイレクト。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="msg_without_intro",
            action="ban",
            required_channel_id="111",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={
                "action": "ban",
                "required_channel_id": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/autoban/{rule.id}/edit" in response.headers["location"]

    async def test_autoban_edit_intro_rule_non_digit(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """intro ルール編集で非数字の channel → リダイレクト。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="vc_without_intro",
            action="ban",
            required_channel_id="111",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.post(
            f"/autoban/{rule.id}/edit",
            data={
                "action": "ban",
                "required_channel_id": "not-a-number",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/autoban/{rule.id}/edit" in response.headers["location"]

    async def test_autoban_edit_get_intro_rule(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """intro ルールの編集ページが表示される。"""
        rule = AutoBanRule(
            guild_id="123456789012345678",
            rule_type="vc_without_intro",
            action="ban",
            required_channel_id="555",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await authenticated_client.get(f"/autoban/{rule.id}/edit")
        assert response.status_code == 200
        assert "VC Join without Intro Post" in response.text


# ===========================================================================
# BAN ログルート
# ===========================================================================


class TestBanLogRoutes:
    """/banlogs ルートのテスト。"""

    async def test_banlogs_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/banlogs", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_banlogs_page(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """データがある場合は一覧が表示される。"""
        log = BanLog(
            guild_id="123456789012345678",
            user_id="999888777",
            username="banneduser",
            reason="Spamming",
            is_autoban=False,
        )
        db_session.add(log)
        await db_session.commit()

        response = await authenticated_client.get("/banlogs")
        assert response.status_code == 200
        assert "banneduser" in response.text
        assert "Spamming" in response.text

    async def test_banlogs_empty(self, authenticated_client: AsyncClient) -> None:
        """ログがない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/banlogs")
        assert response.status_code == 200
        assert "No ban logs" in response.text

    async def test_dashboard_shows_ban_logs_link(
        self, authenticated_client: AsyncClient
    ) -> None:
        """ダッシュボードに Ban Logs リンクが表示される。"""
        response = await authenticated_client.get("/dashboard")
        assert response.status_code == 200
        assert "/banlogs" in response.text
        assert "Ban Logs" in response.text


# ===========================================================================
# チケットルート
# ===========================================================================


class TestTicketRoutes:
    """/tickets ルートのテスト。"""

    async def test_tickets_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/tickets", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_tickets_list_empty(self, authenticated_client: AsyncClient) -> None:
        """チケットがない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/tickets")
        assert response.status_code == 200
        assert "No tickets" in response.text

    async def test_tickets_list_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """チケットがある場合は一覧が表示される。"""
        cat = TicketCategory(guild_id="123", name="General", staff_role_id="999")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        ticket = Ticket(
            guild_id="123",
            user_id="456",
            username="testuser",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
            status="open",
        )
        db_session.add(ticket)
        await db_session.commit()

        response = await authenticated_client.get("/tickets")
        assert response.status_code == 200
        assert "testuser" in response.text

    async def test_tickets_list_with_status_filter(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ステータスフィルタ付きでチケットを取得できる。"""
        cat = TicketCategory(guild_id="123", name="General", staff_role_id="999")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        ticket = Ticket(
            guild_id="123",
            user_id="456",
            username="testuser",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
            status="open",
        )
        db_session.add(ticket)
        await db_session.commit()

        response = await authenticated_client.get("/tickets?status=closed")
        assert response.status_code == 200

    async def test_ticket_detail_requires_auth(self, client: AsyncClient) -> None:
        """チケット詳細は認証が必要。"""
        response = await client.get("/tickets/1", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_ticket_detail_not_found(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないチケットは /tickets にリダイレクトされる。"""
        response = await authenticated_client.get(
            "/tickets/99999", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/tickets"

    async def test_ticket_detail_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """チケット詳細が表示される。"""
        cat = TicketCategory(guild_id="123", name="General", staff_role_id="999")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        ticket = Ticket(
            guild_id="123",
            user_id="456",
            username="testuser",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=42,
            status="open",
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)

        response = await authenticated_client.get(f"/tickets/{ticket.id}")
        assert response.status_code == 200
        assert "Ticket #42" in response.text

    async def test_ticket_delete_requires_auth(self, client: AsyncClient) -> None:
        """チケット削除は認証が必要。"""
        response = await client.post(
            "/tickets/1/delete", data={}, follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_ticket_delete_success(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """チケットを削除できる。"""
        cat = TicketCategory(guild_id="123", name="General", staff_role_id="999")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        ticket = Ticket(
            guild_id="123",
            user_id="456",
            username="testuser",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
            status="closed",
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)

        response = await authenticated_client.post(
            f"/tickets/{ticket.id}/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/tickets"

        result = await db_session.execute(select(Ticket).where(Ticket.id == ticket.id))
        assert result.scalar_one_or_none() is None

    async def test_ticket_delete_not_found(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないチケットの削除はリダイレクトされる。"""
        response = await authenticated_client.post(
            "/tickets/99999/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/tickets"

    async def test_ticket_delete_csrf_failure(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """チケット削除の CSRF 失敗はリダイレクトされる。"""
        from unittest.mock import patch

        cat = TicketCategory(guild_id="123", name="General", staff_role_id="999")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        ticket = Ticket(
            guild_id="123",
            user_id="456",
            username="testuser",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
            status="closed",
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await authenticated_client.post(
                f"/tickets/{ticket.id}/delete",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302

        # チケットはまだ存在する
        result = await db_session.execute(select(Ticket).where(Ticket.id == ticket.id))
        assert result.scalar_one_or_none() is not None

    async def test_ticket_delete_cooldown(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """チケット削除のクールタイム中はリダイレクトされる。"""
        from src.web.app import record_form_submit

        cat = TicketCategory(guild_id="123", name="General", staff_role_id="999")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        ticket = Ticket(
            guild_id="123",
            user_id="456",
            username="testuser",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
            status="closed",
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)

        record_form_submit("test@example.com", f"/tickets/{ticket.id}/delete")
        response = await authenticated_client.post(
            f"/tickets/{ticket.id}/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestTicketPanelRoutes:
    """/tickets/panels ルートのテスト。"""

    async def test_panels_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/tickets/panels", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_panels_list_empty(self, authenticated_client: AsyncClient) -> None:
        """パネルがない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/tickets/panels")
        assert response.status_code == 200
        assert "No ticket panels" in response.text

    async def test_panels_list_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """パネルがある場合は一覧が表示される。"""
        panel = TicketPanel(
            guild_id="123",
            channel_id="456",
            title="Support Panel",
        )
        db_session.add(panel)
        await db_session.commit()

        response = await authenticated_client.get("/tickets/panels")
        assert response.status_code == 200
        assert "Support Panel" in response.text

    async def test_panel_create_page(self, authenticated_client: AsyncClient) -> None:
        """作成フォームが表示される。"""
        response = await authenticated_client.get("/tickets/panels/new")
        assert response.status_code == 200
        assert "Create" in response.text

    async def test_panel_create_page_requires_auth(self, client: AsyncClient) -> None:
        """作成フォームは認証が必要。"""
        response = await client.get("/tickets/panels/new", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_panel_create(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """パネルを作成できる。"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "src.web.app.post_ticket_panel_to_discord",
            new_callable=AsyncMock,
            return_value=(True, "msg123", None),
        ):
            response = await authenticated_client.post(
                "/tickets/panels/new",
                data={
                    "guild_id": "123456789012345678",
                    "channel_id": "999888777",
                    "title": "New Panel",
                    "description": "Click to create ticket",
                    "staff_role_id": "111222333",
                },
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert response.headers["location"] == "/tickets/panels"

        result = await db_session.execute(select(TicketPanel))
        panels = list(result.scalars().all())
        assert len(panels) == 1
        assert panels[0].title == "New Panel"

        # カテゴリも自動作成される
        result = await db_session.execute(select(TicketCategory))
        cats = list(result.scalars().all())
        assert len(cats) == 1
        assert cats[0].staff_role_id == "111222333"

    async def test_panel_create_missing_fields(
        self, authenticated_client: AsyncClient
    ) -> None:
        """必須フィールドが欠けている場合はリダイレクトされる。"""
        response = await authenticated_client.post(
            "/tickets/panels/new",
            data={
                "guild_id": "",
                "channel_id": "",
                "title": "",
                "staff_role_id": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/tickets/panels/new" in response.headers["location"]

    async def test_panel_delete(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """パネルを削除できる。"""
        from unittest.mock import AsyncMock, patch

        panel = TicketPanel(
            guild_id="123",
            channel_id="456",
            title="ToDelete",
            message_id="msg123",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch(
            "src.web.app.delete_discord_message",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            response = await authenticated_client.post(
                f"/tickets/panels/{panel.id}/delete",
                data={},
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert response.headers["location"] == "/tickets/panels"

        result = await db_session.execute(
            select(TicketPanel).where(TicketPanel.id == panel.id)
        )
        assert result.scalar_one_or_none() is None

    async def test_panel_delete_requires_auth(self, client: AsyncClient) -> None:
        """パネル削除は認証が必要。"""
        response = await client.post(
            "/tickets/panels/1/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_panel_create_csrf_failure(
        self, authenticated_client: AsyncClient
    ) -> None:
        """CSRF トークンが無効な場合はリダイレクトされる。"""
        from unittest.mock import patch

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await authenticated_client.post(
                "/tickets/panels/new",
                data={
                    "guild_id": "123",
                    "channel_id": "456",
                    "title": "Test",
                    "csrf_token": "invalid",
                },
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/tickets/panels/new" in response.headers["location"]

    async def test_panel_create_discord_api_failure(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Discord API 投稿失敗時もパネルは作成される (message_id は None)。"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "src.web.app.post_ticket_panel_to_discord",
            new_callable=AsyncMock,
            return_value=(False, None, "Bot にこのチャンネルへの送信権限がありません"),
        ):
            response = await authenticated_client.post(
                "/tickets/panels/new",
                data={
                    "guild_id": "123",
                    "channel_id": "456",
                    "title": "Failed Panel",
                    "staff_role_id": "999",
                },
                follow_redirects=False,
            )

        assert response.status_code == 302
        result = await db_session.execute(select(TicketPanel))
        panels = list(result.scalars().all())
        assert len(panels) == 1
        assert panels[0].message_id is None

    async def test_panel_delete_not_found(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないパネルの削除は 302 リダイレクト。"""
        response = await authenticated_client.post(
            "/tickets/panels/99999/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/tickets/panels"

    async def test_panel_create_with_category_fields(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """カテゴリフィールド付きでパネルを作成できる。"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "src.web.app.post_ticket_panel_to_discord",
            new_callable=AsyncMock,
            return_value=(True, "msg456", None),
        ):
            response = await authenticated_client.post(
                "/tickets/panels/new",
                data={
                    "guild_id": "123",
                    "channel_id": "456",
                    "title": "Panel with settings",
                    "staff_role_id": "999",
                    "discord_category_id": "888",
                    "channel_prefix": "help-",
                    "log_channel_id": "777",
                },
                follow_redirects=False,
            )

        assert response.status_code == 302

        result = await db_session.execute(select(TicketPanel))
        panels = list(result.scalars().all())
        assert len(panels) == 1
        assert panels[0].message_id == "msg456"

        result = await db_session.execute(select(TicketCategory))
        cats = list(result.scalars().all())
        assert len(cats) == 1
        assert cats[0].staff_role_id == "999"
        assert cats[0].discord_category_id == "888"
        assert cats[0].channel_prefix == "help-"
        assert cats[0].log_channel_id == "777"

        result = await db_session.execute(select(TicketPanelCategory))
        associations = list(result.scalars().all())
        assert len(associations) == 1
        assert associations[0].category_id == cats[0].id

    async def test_panel_create_cooldown(
        self, authenticated_client: AsyncClient
    ) -> None:
        """クールタイム中はリダイレクトされる。"""
        from src.web.app import record_form_submit

        record_form_submit("test@example.com", "/tickets/panels/new")
        response = await authenticated_client.post(
            "/tickets/panels/new",
            data={
                "guild_id": "123",
                "channel_id": "456",
                "title": "Test",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/tickets/panels/new" in response.headers["location"]

    async def test_panel_delete_csrf_failure(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """パネル削除の CSRF 失敗はリダイレクトされる。"""
        from unittest.mock import patch

        panel = TicketPanel(guild_id="123", channel_id="456", title="Test")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await authenticated_client.post(
                f"/tickets/panels/{panel.id}/delete",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/tickets/panels" in response.headers["location"]

        # パネルはまだ存在する
        result = await db_session.execute(
            select(TicketPanel).where(TicketPanel.id == panel.id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_panel_delete_cooldown(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """パネル削除のクールタイム中はリダイレクトされる。"""
        from src.web.app import record_form_submit

        panel = TicketPanel(guild_id="123", channel_id="456", title="Test")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        record_form_submit("test@example.com", f"/tickets/panels/{panel.id}/delete")
        response = await authenticated_client.post(
            f"/tickets/panels/{panel.id}/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302

    async def test_panel_delete_without_message_id(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """message_id がないパネルの削除は Discord 削除をスキップする。"""
        panel = TicketPanel(guild_id="123", channel_id="456", title="NoMessage")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/tickets/panels/{panel.id}/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/tickets/panels"

        result = await db_session.execute(
            select(TicketPanel).where(TicketPanel.id == panel.id)
        )
        assert result.scalar_one_or_none() is None


class TestTicketDetailExtra:
    """チケット詳細ページの追加テスト。"""

    async def test_ticket_detail_with_transcript(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """トランスクリプト付きチケットの詳細が表示される。"""
        cat = TicketCategory(guild_id="123", name="General", staff_role_id="999")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        ticket = Ticket(
            guild_id="123",
            user_id="456",
            username="testuser",
            category_id=cat.id,
            ticket_number=10,
            status="closed",
            transcript="=== Ticket #10 ===\n[2025-01-01 10:00:00] user: Hello",
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)

        response = await authenticated_client.get(f"/tickets/{ticket.id}")
        assert response.status_code == 200
        assert "Ticket #10" in response.text
        assert "Hello" in response.text

    async def test_ticket_detail_with_form_answers(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """フォーム回答付きチケットの詳細が表示される。"""
        cat = TicketCategory(
            guild_id="123",
            name="General",
            staff_role_id="999",
            form_questions='["お名前","内容"]',
        )
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        ticket = Ticket(
            guild_id="123",
            user_id="456",
            username="testuser",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=11,
            status="open",
            form_answers=(
                '[{"question":"お名前","answer":"Taro"},'
                '{"question":"内容","answer":"Bug report"}]'
            ),
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)

        response = await authenticated_client.get(f"/tickets/{ticket.id}")
        assert response.status_code == 200
        assert "Ticket #11" in response.text

    async def test_ticket_detail_closed_ticket(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """クローズ済みチケットの詳細が表示される。"""
        cat = TicketCategory(guild_id="123", name="General", staff_role_id="999")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        ticket = Ticket(
            guild_id="123",
            user_id="456",
            username="testuser",
            category_id=cat.id,
            ticket_number=12,
            status="closed",
            closed_by="staff1",
            close_reason="resolved",
            closed_at=datetime(2026, 2, 7, 10, 0, tzinfo=UTC),
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)

        response = await authenticated_client.get(f"/tickets/{ticket.id}")
        assert response.status_code == 200
        assert "Ticket #12" in response.text
        assert "closed" in response.text.lower()

    async def test_ticket_detail_missing_category(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """カテゴリが削除された場合は 'Unknown' が表示される。"""
        cat = TicketCategory(guild_id="123", name="Temp", staff_role_id="999")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        ticket = Ticket(
            guild_id="123",
            user_id="456",
            username="testuser",
            category_id=cat.id,
            channel_id="ch_miss",
            ticket_number=50,
            status="open",
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)

        # FK 制約を一時無効化してカテゴリを削除
        from sqlalchemy import text

        await db_session.execute(text("SET session_replication_role = 'replica'"))
        await db_session.execute(
            text("DELETE FROM ticket_categories WHERE id = :cid"),
            {"cid": cat.id},
        )
        await db_session.commit()
        await db_session.execute(text("SET session_replication_role = 'origin'"))

        response = await authenticated_client.get(f"/tickets/{ticket.id}")
        assert response.status_code == 200
        assert "Ticket #50" in response.text
        assert "Unknown" in response.text

    async def test_ticket_detail_missing_guild(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ギルドが見つからない場合もエラーなく表示される。"""
        cat = TicketCategory(guild_id="999999", name="Test", staff_role_id="1")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        ticket = Ticket(
            guild_id="999999",
            user_id="456",
            username="testuser",
            category_id=cat.id,
            channel_id="ch2",
            ticket_number=51,
            status="open",
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)

        response = await authenticated_client.get(f"/tickets/{ticket.id}")
        assert response.status_code == 200
        assert "Ticket #51" in response.text


class TestTicketPanelDetailRoutes:
    """チケットパネル詳細・編集ルートのテスト。"""

    async def test_detail_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/tickets/panels/1", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_detail_not_found(self, authenticated_client: AsyncClient) -> None:
        """存在しないパネルは /tickets/panels にリダイレクトされる。"""
        response = await authenticated_client.get(
            "/tickets/panels/99999", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/tickets/panels"

    async def test_detail_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """パネル詳細が表示される。"""
        panel = TicketPanel(guild_id="123", channel_id="456", title="Detail Test Panel")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.get(f"/tickets/panels/{panel.id}")
        assert response.status_code == 200
        assert "Detail Test Panel" in response.text

    async def test_detail_with_associations(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """カテゴリ関連付きパネル詳細が表示される。"""
        cat = TicketCategory(guild_id="123", name="Support", staff_role_id="999")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        panel = TicketPanel(guild_id="123", channel_id="456", title="With Cats")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        assoc = TicketPanelCategory(
            panel_id=panel.id,
            category_id=cat.id,
            button_style="primary",
            position=0,
        )
        db_session.add(assoc)
        await db_session.commit()

        response = await authenticated_client.get(f"/tickets/panels/{panel.id}")
        assert response.status_code == 200
        assert "Support" in response.text
        assert "Category Buttons" in response.text

    async def test_edit_title(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """タイトル・説明を更新できる。"""
        panel = TicketPanel(guild_id="123", channel_id="456", title="Old Title")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/tickets/panels/{panel.id}/edit",
            data={"title": "New Title", "description": "New Desc"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "success=Panel+updated" in response.headers["location"]

        await db_session.refresh(panel)
        assert panel.title == "New Title"
        assert panel.description == "New Desc"

    async def test_edit_requires_auth(self, client: AsyncClient) -> None:
        """編集は認証が必要。"""
        response = await client.post(
            "/tickets/panels/1/edit",
            data={"title": "Test"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_edit_csrf_failure(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """CSRF 失敗時はリダイレクトされる。"""
        from unittest.mock import patch

        panel = TicketPanel(guild_id="123", channel_id="456", title="Original")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await authenticated_client.post(
                f"/tickets/panels/{panel.id}/edit",
                data={"title": "Hacked", "csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "Invalid+security+token" in response.headers["location"]

        await db_session.refresh(panel)
        assert panel.title == "Original"

    async def test_edit_empty_title(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """空タイトルはエラーになる。"""
        panel = TicketPanel(guild_id="123", channel_id="456", title="Keep")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/tickets/panels/{panel.id}/edit",
            data={"title": "", "description": ""},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "Title+is+required" in response.headers["location"]

        await db_session.refresh(panel)
        assert panel.title == "Keep"

    async def test_edit_not_found(self, authenticated_client: AsyncClient) -> None:
        """存在しないパネルの編集は /tickets/panels にリダイレクト。"""
        response = await authenticated_client.post(
            "/tickets/panels/99999/edit",
            data={"title": "Test"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/tickets/panels"

    async def test_edit_cooldown(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """クールタイム中は編集できない。"""
        from src.web.app import record_form_submit

        panel = TicketPanel(guild_id="123", channel_id="456", title="Test")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        record_form_submit("test@example.com", f"/tickets/panels/{panel.id}/edit")
        response = await authenticated_client.post(
            f"/tickets/panels/{panel.id}/edit",
            data={"title": "Updated"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "Please+wait" in response.headers["location"]

    async def test_button_edit(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ボタン設定を更新できる。"""
        cat = TicketCategory(guild_id="123", name="Bug", staff_role_id="999")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        panel = TicketPanel(guild_id="123", channel_id="456", title="Panel")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        assoc = TicketPanelCategory(
            panel_id=panel.id,
            category_id=cat.id,
            button_style="primary",
            position=0,
        )
        db_session.add(assoc)
        await db_session.commit()
        await db_session.refresh(assoc)

        response = await authenticated_client.post(
            f"/tickets/panels/{panel.id}/buttons/{assoc.id}/edit",
            data={
                "button_label": "Report Bug",
                "button_style": "danger",
                "button_emoji": "🐛",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "success=Button+updated" in response.headers["location"]

        await db_session.refresh(assoc)
        assert assoc.button_label == "Report Bug"
        assert assoc.button_style == "danger"
        assert assoc.button_emoji == "🐛"

    async def test_button_edit_not_found(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """存在しないボタンの編集はリダイレクト。"""
        panel = TicketPanel(guild_id="123", channel_id="456", title="Panel")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/tickets/panels/{panel.id}/buttons/99999/edit",
            data={"button_label": "Test", "button_style": "primary"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "Button+not+found" in response.headers["location"]

    async def test_button_edit_requires_auth(self, client: AsyncClient) -> None:
        """ボタン編集は認証が必要。"""
        response = await client.post(
            "/tickets/panels/1/buttons/1/edit",
            data={"button_label": "Test"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_button_edit_csrf_failure(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ボタン編集 CSRF 失敗。"""
        from unittest.mock import patch

        cat = TicketCategory(guild_id="123", name="Test", staff_role_id="999")
        db_session.add(cat)
        await db_session.commit()
        await db_session.refresh(cat)

        panel = TicketPanel(guild_id="123", channel_id="456", title="Panel")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        assoc = TicketPanelCategory(
            panel_id=panel.id,
            category_id=cat.id,
            button_style="primary",
            position=0,
        )
        db_session.add(assoc)
        await db_session.commit()
        await db_session.refresh(assoc)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await authenticated_client.post(
                f"/tickets/panels/{panel.id}/buttons/{assoc.id}/edit",
                data={"button_label": "Hacked", "csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "Invalid+security+token" in response.headers["location"]

        await db_session.refresh(assoc)
        assert assoc.button_label is None  # unchanged

    async def test_post_to_discord_new(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """新規 Discord 投稿。"""
        from unittest.mock import AsyncMock, patch

        panel = TicketPanel(guild_id="123", channel_id="456", title="Post Test")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch(
            "src.web.app.post_ticket_panel_to_discord",
            new_callable=AsyncMock,
            return_value=(True, "msg_posted_123", None),
        ):
            response = await authenticated_client.post(
                f"/tickets/panels/{panel.id}/post",
                data={},
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert "success=Posted+to+Discord" in response.headers["location"]

        await db_session.refresh(panel)
        assert panel.message_id == "msg_posted_123"

    async def test_update_in_discord(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """既存メッセージの Discord 更新。"""
        from unittest.mock import AsyncMock, patch

        panel = TicketPanel(
            guild_id="123",
            channel_id="456",
            title="Update Test",
            message_id="existing123",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch(
            "src.web.app.edit_ticket_panel_in_discord",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            response = await authenticated_client.post(
                f"/tickets/panels/{panel.id}/post",
                data={},
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert "success=Updated+in+Discord" in response.headers["location"]

    async def test_post_requires_auth(self, client: AsyncClient) -> None:
        """Discord 投稿は認証が必要。"""
        response = await client.post(
            "/tickets/panels/1/post",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_post_not_found(self, authenticated_client: AsyncClient) -> None:
        """存在しないパネルの投稿は /tickets/panels にリダイレクト。"""
        response = await authenticated_client.post(
            "/tickets/panels/99999/post",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/tickets/panels"

    async def test_post_discord_api_failure(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Discord API 失敗時はエラーメッセージ付きリダイレクト。"""
        from unittest.mock import AsyncMock, patch

        panel = TicketPanel(guild_id="123", channel_id="456", title="Fail Test")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch(
            "src.web.app.post_ticket_panel_to_discord",
            new_callable=AsyncMock,
            return_value=(False, None, "Bot permission denied"),
        ):
            response = await authenticated_client.post(
                f"/tickets/panels/{panel.id}/post",
                data={},
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert "Error" in response.headers["location"]

    async def test_update_discord_api_failure(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Discord PATCH API 失敗時はエラーメッセージ付きリダイレクト。"""
        from unittest.mock import AsyncMock, patch

        panel = TicketPanel(
            guild_id="123",
            channel_id="456",
            title="Fail Update",
            message_id="existing456",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch(
            "src.web.app.edit_ticket_panel_in_discord",
            new_callable=AsyncMock,
            return_value=(False, "Message not found"),
        ):
            response = await authenticated_client.post(
                f"/tickets/panels/{panel.id}/post",
                data={},
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert "Error" in response.headers["location"]


class TestJoinRoleRoutes:
    """/joinrole ルートのテスト。"""

    async def test_joinrole_requires_auth(self, client: AsyncClient) -> None:
        """認証なしでは /login にリダイレクトされる。"""
        response = await client.get("/joinrole", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_joinrole_list_empty(self, authenticated_client: AsyncClient) -> None:
        """設定がない場合は空メッセージが表示される。"""
        response = await authenticated_client.get("/joinrole")
        assert response.status_code == 200
        assert "No join role configs configured" in response.text

    async def test_joinrole_list_with_data(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """設定がある場合は一覧が表示される。"""
        config = JoinRoleConfig(
            guild_id="123456789012345678",
            role_id="987654321012345678",
            duration_hours=24,
        )
        db_session.add(config)
        await db_session.commit()

        response = await authenticated_client.get("/joinrole")
        assert response.status_code == 200
        assert "24h" in response.text

    async def test_joinrole_create(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """JoinRole 設定を作成できる。"""
        response = await authenticated_client.post(
            "/joinrole/new",
            data={
                "guild_id": "123456789012345678",
                "role_id": "987654321012345678",
                "duration_hours": "48",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/joinrole"

        result = await db_session.execute(select(JoinRoleConfig))
        configs = list(result.scalars().all())
        assert len(configs) == 1
        assert configs[0].duration_hours == 48

    async def test_joinrole_create_invalid_hours(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """無効な時間はリダイレクトで拒否される。"""
        response = await authenticated_client.post(
            "/joinrole/new",
            data={
                "guild_id": "123",
                "role_id": "456",
                "duration_hours": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(select(JoinRoleConfig))
        assert len(list(result.scalars().all())) == 0

    async def test_joinrole_create_too_many_hours(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """720時間超はリダイレクトで拒否される。"""
        response = await authenticated_client.post(
            "/joinrole/new",
            data={
                "guild_id": "123",
                "role_id": "456",
                "duration_hours": "721",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(select(JoinRoleConfig))
        assert len(list(result.scalars().all())) == 0

    async def test_joinrole_delete(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """JoinRole 設定を削除できる。"""
        config = JoinRoleConfig(
            guild_id="123",
            role_id="456",
            duration_hours=24,
        )
        db_session.add(config)
        await db_session.commit()
        await db_session.refresh(config)

        response = await authenticated_client.post(
            f"/joinrole/{config.id}/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(select(JoinRoleConfig))
        assert len(list(result.scalars().all())) == 0

    async def test_joinrole_toggle(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """JoinRole 設定の有効/無効を切り替えできる。"""
        config = JoinRoleConfig(
            guild_id="123",
            role_id="456",
            duration_hours=24,
        )
        db_session.add(config)
        await db_session.commit()
        await db_session.refresh(config)
        assert config.enabled is True

        response = await authenticated_client.post(
            f"/joinrole/{config.id}/toggle",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(config)
        assert config.enabled is False

    async def test_joinrole_create_requires_auth(self, client: AsyncClient) -> None:
        """作成は認証が必要。"""
        response = await client.post(
            "/joinrole/new",
            data={
                "guild_id": "123",
                "role_id": "456",
                "duration_hours": "24",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_joinrole_delete_requires_auth(self, client: AsyncClient) -> None:
        """削除は認証が必要。"""
        response = await client.post(
            "/joinrole/1/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_joinrole_toggle_requires_auth(self, client: AsyncClient) -> None:
        """トグルは認証が必要。"""
        response = await client.post(
            "/joinrole/1/toggle",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    async def test_joinrole_create_non_integer_hours(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """duration_hours が数値でない場合はリダイレクト。"""
        response = await authenticated_client.post(
            "/joinrole/new",
            data={
                "guild_id": "123",
                "role_id": "456",
                "duration_hours": "abc",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(select(JoinRoleConfig))
        assert len(list(result.scalars().all())) == 0

    async def test_joinrole_create_negative_hours(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """負の時間はリダイレクトで拒否。"""
        response = await authenticated_client.post(
            "/joinrole/new",
            data={
                "guild_id": "123",
                "role_id": "456",
                "duration_hours": "-1",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(select(JoinRoleConfig))
        assert len(list(result.scalars().all())) == 0

    async def test_joinrole_create_boundary_min(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """最小値 1 時間で作成可能。"""
        response = await authenticated_client.post(
            "/joinrole/new",
            data={
                "guild_id": "123",
                "role_id": "456",
                "duration_hours": "1",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(select(JoinRoleConfig))
        configs = list(result.scalars().all())
        assert len(configs) == 1
        assert configs[0].duration_hours == 1

    async def test_joinrole_create_boundary_max(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """最大値 720 時間で作成可能。"""
        response = await authenticated_client.post(
            "/joinrole/new",
            data={
                "guild_id": "123",
                "role_id": "456",
                "duration_hours": "720",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(select(JoinRoleConfig))
        configs = list(result.scalars().all())
        assert len(configs) == 1
        assert configs[0].duration_hours == 720

    async def test_joinrole_create_duplicate(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """同じ guild_id + role_id で重複作成はエラーにならない。"""
        config = JoinRoleConfig(
            guild_id="123",
            role_id="456",
            duration_hours=24,
        )
        db_session.add(config)
        await db_session.commit()

        response = await authenticated_client.post(
            "/joinrole/new",
            data={
                "guild_id": "123",
                "role_id": "456",
                "duration_hours": "48",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        result = await db_session.execute(select(JoinRoleConfig))
        assert len(list(result.scalars().all())) == 1

    async def test_joinrole_delete_nonexistent(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しない設定の削除はエラーにならない。"""
        response = await authenticated_client.post(
            "/joinrole/99999/delete",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/joinrole" in response.headers["location"]

    async def test_joinrole_toggle_nonexistent(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しない設定のトグルはエラーにならない。"""
        response = await authenticated_client.post(
            "/joinrole/99999/toggle",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/joinrole" in response.headers["location"]


# ===========================================================================
# 追加 CSRF / バリデーション テスト (カバレッジ向上)
# ===========================================================================


class TestAdditionalCsrfFailures:
    """追加の CSRF 検証失敗テスト (app.py 未カバー行用)。"""

    @pytest.mark.asyncio
    async def test_forgot_password_csrf_failure(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """forgot-password の CSRF 失敗は 403。"""
        from unittest.mock import patch

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                "/forgot-password",
                data={"email": "test@example.com", "csrf_token": "bad"},
            )
        assert response.status_code == 403
        assert "Invalid security token" in response.text

    @pytest.mark.asyncio
    async def test_reset_password_csrf_failure(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """reset-password の CSRF 失敗は 403。"""
        from unittest.mock import patch

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                "/reset-password",
                data={
                    "token": "tok",
                    "new_password": "pass",
                    "confirm_password": "pass",
                    "csrf_token": "bad",
                },
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_initial_setup_csrf_failure(
        self,
        client: AsyncClient,
        initial_admin_user: AdminUser,
    ) -> None:
        """initial-setup の CSRF 失敗は 403。"""
        from unittest.mock import patch

        from src.web.app import generate_csrf_token

        # 初回セットアップ状態でログイン
        csrf = generate_csrf_token()
        resp = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        client.cookies.set("session", resp.cookies.get("session") or "")

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                "/initial-setup",
                data={
                    "new_email": "new@test.com",
                    "new_password": "newpassword123",
                    "confirm_password": "newpassword123",
                    "csrf_token": "bad",
                },
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_email_change_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
    ) -> None:
        """email-change の CSRF 失敗は 403。"""
        from unittest.mock import patch

        from src.web.app import generate_csrf_token

        csrf = generate_csrf_token()
        resp = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        client.cookies.set("session", resp.cookies.get("session") or "")

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                "/settings/email",
                data={"new_email": "new@test.com", "csrf_token": "bad"},
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_settings_email_csrf_failure(
        self,
        client: AsyncClient,
        admin_user: AdminUser,
    ) -> None:
        """settings/email POST の CSRF 失敗は 403。"""
        from unittest.mock import patch

        from src.web.app import generate_csrf_token

        csrf = generate_csrf_token()
        resp = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        client.cookies.set("session", resp.cookies.get("session") or "")

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                "/settings/email",
                data={"new_email": "new@test.com", "csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 403


class TestAdditionalAutobanValidation:
    """autoban 追加バリデーション (threshold_seconds)。"""

    @pytest.mark.asyncio
    async def test_vc_join_invalid_threshold(
        self, authenticated_client: AsyncClient
    ) -> None:
        """vc_join の threshold_seconds が無効な場合リダイレクト。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123456",
                "rule_type": "vc_join",
                "action": "ban",
                "threshold_seconds": "abc",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    @pytest.mark.asyncio
    async def test_role_acquired_threshold_too_high(
        self, authenticated_client: AsyncClient
    ) -> None:
        """role_acquired の threshold_seconds が上限超え。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123456",
                "rule_type": "role_acquired",
                "action": "ban",
                "threshold_seconds": "5000",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    @pytest.mark.asyncio
    async def test_message_post_threshold_zero(
        self, authenticated_client: AsyncClient
    ) -> None:
        """message_post の threshold_seconds=0 はリダイレクト。"""
        response = await authenticated_client.post(
            "/autoban/new",
            data={
                "guild_id": "123456",
                "rule_type": "message_post",
                "action": "kick",
                "threshold_seconds": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestJoinRoleEmptyGuildRole:
    """Join role の guild_id/role_id 空バリデーション。"""

    @pytest.mark.asyncio
    async def test_empty_guild_id(self, authenticated_client: AsyncClient) -> None:
        response = await authenticated_client.post(
            "/joinrole/new",
            data={"guild_id": "", "role_id": "123", "duration_hours": "24"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/joinrole" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_empty_role_id(self, authenticated_client: AsyncClient) -> None:
        response = await authenticated_client.post(
            "/joinrole/new",
            data={"guild_id": "123", "role_id": "", "duration_hours": "24"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/joinrole" in response.headers["location"]


class TestAppCoverageGaps:
    """app.py の未カバー行を埋めるテスト群。"""

    # --- Line 1346: dashboard redirects unverified admin to verify-email ---

    @pytest.mark.asyncio
    async def test_dashboard_unverified_admin_redirects(
        self,
        client: AsyncClient,
        unverified_admin_user: AdminUser,
    ) -> None:
        """未認証の admin は dashboard から verify-email にリダイレクト。"""
        from src.web.app import generate_csrf_token

        csrf = generate_csrf_token()
        resp = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        client.cookies.set("session", resp.cookies.get("session") or "")
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert "/verify-email" in response.headers["location"]

    # --- Line 818: resend-verification CSRF failure ---

    @pytest.mark.asyncio
    async def test_resend_verification_csrf_failure(
        self,
        client: AsyncClient,
        unverified_admin_user: AdminUser,
    ) -> None:
        """resend-verification の CSRF 失敗は 403。"""
        from unittest.mock import patch

        from src.web.app import generate_csrf_token

        csrf = generate_csrf_token()
        resp = await client.post(
            "/login",
            data={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        client.cookies.set("session", resp.cookies.get("session") or "")

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await client.post(
                "/resend-verification",
                data={"csrf_token": "bad"},
            )
        assert response.status_code == 403

    # --- Line 1406: refresh maintenance CSRF failure ---

    @pytest.mark.asyncio
    async def test_refresh_maintenance_csrf_failure(
        self, authenticated_client: AsyncClient
    ) -> None:
        """maintenance refresh の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await authenticated_client.post(
                "/settings/maintenance/refresh",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/settings/maintenance" in response.headers["location"]

    # --- Line 1439: cleanup orphaned CSRF failure ---

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_csrf_failure(
        self, authenticated_client: AsyncClient
    ) -> None:
        """cleanup orphaned の CSRF 失敗は 400。"""
        from unittest.mock import patch

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await authenticated_client.post(
                "/settings/maintenance/cleanup",
                data={"csrf_token": "bad"},
            )
        assert response.status_code == 400

    # --- Line 1928: delete role panel CSRF failure ---

    @pytest.mark.asyncio
    async def test_delete_role_panel_csrf_failure(
        self, authenticated_client: AsyncClient
    ) -> None:
        """ロールパネル削除の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await authenticated_client.post(
                "/rolepanels/1/delete",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "/rolepanels" in response.headers["location"]

    # --- Line 2515: role panel detail requires auth ---

    @pytest.mark.asyncio
    async def test_role_panel_detail_requires_auth(self, client: AsyncClient) -> None:
        """ロールパネル詳細は認証必須。"""
        response = await client.get("/rolepanels/1", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    # --- Line 2524: role panel detail not found ---

    @pytest.mark.asyncio
    async def test_role_panel_detail_not_found(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないロールパネルはリダイレクト。"""
        response = await authenticated_client.get(
            "/rolepanels/99999", follow_redirects=False
        )
        assert response.status_code == 302
        assert "/rolepanels" in response.headers["location"]

    # --- Line 2571: edit role panel CSRF failure ---

    @pytest.mark.asyncio
    async def test_edit_role_panel_csrf_failure(
        self, authenticated_client: AsyncClient
    ) -> None:
        """ロールパネル編集の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await authenticated_client.post(
                "/rolepanels/1/edit",
                data={"title": "t", "csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "rolepanels/1" in response.headers["location"]

    # --- Lines 3224->3228: autoban delete with nonexistent rule ---

    @pytest.mark.asyncio
    async def test_autoban_delete_nonexistent_rule(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないルールの削除は正常にリダイレクト。"""
        response = await authenticated_client.post(
            "/autoban/99999/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

    # --- Lines 3257->3261: autoban toggle with nonexistent rule ---

    @pytest.mark.asyncio
    async def test_autoban_toggle_nonexistent_rule(
        self, authenticated_client: AsyncClient
    ) -> None:
        """存在しないルールのトグルは正常にリダイレクト。"""
        response = await authenticated_client.post(
            "/autoban/99999/toggle",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/autoban"

    # --- Line 3037: autoban create requires auth ---

    @pytest.mark.asyncio
    async def test_autoban_create_requires_auth(self, client: AsyncClient) -> None:
        """autoban ルール作成は認証必須。"""
        response = await client.post(
            "/autoban/new",
            data={"guild_id": "1", "rule_type": "no_avatar"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    # --- Line 3485: ticket panel create POST requires auth ---

    @pytest.mark.asyncio
    async def test_ticket_panel_create_post_requires_auth(
        self, client: AsyncClient
    ) -> None:
        """チケットパネル作成 POST は認証必須。"""
        response = await client.post(
            "/tickets/panels/new",
            data={"guild_id": "1", "title": "t"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    # --- Line 3661: ticket panel title too long ---

    @pytest.mark.asyncio
    async def test_ticket_panel_edit_title_too_long(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """チケットパネルのタイトルが100文字超はリダイレクト。"""
        panel = TicketPanel(guild_id="123456", channel_id="789", title="Test")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/tickets/panels/{panel.id}/edit",
            data={"title": "x" * 101, "description": "ok"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "100+characters" in response.headers["location"]

    # --- Line 3668: ticket panel description too long ---

    @pytest.mark.asyncio
    async def test_ticket_panel_edit_description_too_long(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """チケットパネルの説明が2000文字超はリダイレクト。"""
        panel = TicketPanel(guild_id="123456", channel_id="789", title="Test")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await authenticated_client.post(
            f"/tickets/panels/{panel.id}/edit",
            data={"title": "Valid Title", "description": "x" * 2001},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "2000+characters" in response.headers["location"]

    # --- Lines 3714, 3734, 3742: ticket panel button edit ---

    @pytest.mark.asyncio
    async def test_ticket_panel_button_edit_cooldown(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ボタン編集のクールダウン中はリダイレクト。"""
        panel = TicketPanel(guild_id="123456", channel_id="789", title="Test")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        record_form_submit(
            "test@example.com",
            f"/tickets/panels/{panel.id}/buttons/1/edit",
        )
        response = await authenticated_client.post(
            f"/tickets/panels/{panel.id}/buttons/1/edit",
            data={
                "button_label": "Click",
                "button_style": "primary",
                "button_emoji": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "Please+wait" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_ticket_panel_button_edit_label_truncation(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ボタンラベルが80文字超は切り詰められる。"""
        cat = TicketCategory(
            guild_id="123456",
            name="TestCat",
            staff_role_id="111",
        )
        db_session.add(cat)
        await db_session.flush()

        panel = TicketPanel(guild_id="123456", channel_id="789", title="Test")
        db_session.add(panel)
        await db_session.flush()

        assoc = TicketPanelCategory(
            panel_id=panel.id,
            category_id=cat.id,
            position=0,
        )
        db_session.add(assoc)
        await db_session.commit()
        await db_session.refresh(assoc)

        response = await authenticated_client.post(
            f"/tickets/panels/{panel.id}/buttons/{assoc.id}/edit",
            data={
                "button_label": "L" * 100,
                "button_style": "primary",
                "button_emoji": "E" * 100,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        await db_session.refresh(assoc)
        assert len(assoc.button_label) <= 80
        assert len(assoc.button_emoji) <= 64

    # --- Lines 3767, 3775: ticket panel post-to-discord ---

    @pytest.mark.asyncio
    async def test_ticket_panel_post_to_discord_csrf_failure(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """post-to-discord の CSRF 失敗はリダイレクト。"""
        from unittest.mock import patch

        panel = TicketPanel(guild_id="123456", channel_id="789", title="Test")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch("src.web.app.validate_csrf_token", return_value=False):
            response = await authenticated_client.post(
                f"/tickets/panels/{panel.id}/post",
                data={"csrf_token": "bad"},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "Invalid+security+token" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_ticket_panel_post_to_discord_cooldown(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """post-to-discord のクールダウン中はリダイレクト。"""
        panel = TicketPanel(guild_id="123456", channel_id="789", title="Test")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        record_form_submit("test@example.com", f"/tickets/panels/{panel.id}/post")
        response = await authenticated_client.post(
            f"/tickets/panels/{panel.id}/post",
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "Please+wait" in response.headers["location"]

    # --- Lines 3822-3825: post-to-discord success with message_id ---

    @pytest.mark.asyncio
    async def test_ticket_panel_post_to_discord_success(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """post-to-discord 成功で message_id が保存される。"""
        from unittest.mock import AsyncMock, patch

        panel = TicketPanel(guild_id="123456", channel_id="789", title="Test")
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        with patch(
            "src.web.app.post_ticket_panel_to_discord",
            new_callable=AsyncMock,
            return_value=(True, "msg_id_123", None),
        ):
            response = await authenticated_client.post(
                f"/tickets/panels/{panel.id}/post",
                data={},
                follow_redirects=False,
            )
        assert response.status_code == 302
        assert "Posted+to+Discord" in response.headers["location"]

        await db_session.refresh(panel)
        assert panel.message_id == "msg_id_123"

    # --- Lines 2447-2448: role panel create with bad position ---

    @pytest.mark.asyncio
    async def test_role_panel_create_bad_position(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """ロールパネル作成時の position が不正な場合はデフォルト値。"""
        guild = DiscordGuild(guild_id="123456", guild_name="Test")
        db_session.add(guild)
        channel = DiscordChannel(channel_id="789", guild_id="123456", channel_name="ch")
        db_session.add(channel)
        await db_session.commit()

        response = await authenticated_client.post(
            "/rolepanels/new",
            data={
                "guild_id": "123456",
                "channel_id": "789",
                "title": "Test Panel",
                "panel_type": "button",
                "use_embed": "1",
                "item_emoji[]": "😀",
                "item_role_id[]": "999",
                "item_label[]": "Role1",
                "item_style[]": "primary",
                "item_position[]": "abc",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/rolepanels/" in response.headers["location"]

        # Check the item was created with position=0 (fallback)
        result = await db_session.execute(select(RolePanelItem))
        item = result.scalar_one_or_none()
        assert item is not None
        assert item.position == 0

    # --- Lines 367-370: login rate limit cleanup via HTTP ---

    @pytest.mark.asyncio
    async def test_login_rate_limit_cleanup_expired(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """期限切れのレート制限エントリがログインリクエスト時に削除される。"""
        import time

        from src.web import app as web_app_module

        test_ip = "127.0.0.1"
        web_app_module.LOGIN_ATTEMPTS.clear()
        old_time = time.time() - web_app_module.LOGIN_WINDOW_SECONDS - 10
        web_app_module.LOGIN_ATTEMPTS[test_ip] = [old_time]

        await client.post(
            "/login",
            data={
                "email": "test@example.com",
                "password": "wrong",
                "csrf_token": "token",
            },
        )
        # 古いエントリはクリーンアップされ、新しい失敗のみ残る
        remaining = web_app_module.LOGIN_ATTEMPTS.get(test_ip, [])
        assert all(
            time.time() - t < web_app_module.LOGIN_WINDOW_SECONDS for t in remaining
        )

    @pytest.mark.asyncio
    async def test_login_rate_limit_cleanup_partial(
        self, client: AsyncClient, admin_user: AdminUser
    ) -> None:
        """一部だけ期限切れのエントリがログインリクエスト時に更新される。"""
        import time

        from src.web import app as web_app_module

        test_ip = "127.0.0.1"
        web_app_module.LOGIN_ATTEMPTS.clear()
        old_time = time.time() - web_app_module.LOGIN_WINDOW_SECONDS - 10
        recent_time = time.time()
        web_app_module.LOGIN_ATTEMPTS[test_ip] = [old_time, recent_time]

        await client.post(
            "/login",
            data={
                "email": "test@example.com",
                "password": "wrong",
                "csrf_token": "token",
            },
        )
        # 古いエントリが削除され、新しいものが残る
        assert test_ip in web_app_module.LOGIN_ATTEMPTS
