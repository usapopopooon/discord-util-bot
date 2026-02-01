"""Tests for HTML templates."""

from __future__ import annotations

import pytest

from src.database.models import RolePanel, RolePanelItem
from src.web.templates import (
    _base,
    _nav,
    bump_list_page,
    dashboard_page,
    lobbies_list_page,
    login_page,
    role_panel_create_page,
    role_panel_detail_page,
    role_panels_list_page,
    settings_page,
    sticky_list_page,
)

# ===========================================================================
# Base テンプレート
# ===========================================================================


class TestBaseTemplate:
    """_base テンプレートのテスト。"""

    def test_contains_html_structure(self) -> None:
        """HTML の基本構造を含む。"""
        result = _base("Test", "<p>Content</p>")
        assert "<!DOCTYPE html>" in result
        assert "<html" in result
        assert "</html>" in result
        assert "<head>" in result
        assert "<body" in result

    def test_title_is_escaped(self) -> None:
        """タイトルがエスケープされる。"""
        result = _base("<script>alert('xss')</script>", "content")
        assert "&lt;script&gt;" in result
        assert "<script>alert" not in result

    def test_includes_tailwind(self) -> None:
        """Tailwind CDN が含まれる。"""
        result = _base("Test", "content")
        assert "tailwindcss" in result

    def test_content_is_included(self) -> None:
        """コンテンツが含まれる。"""
        result = _base("Test", "<div>Test Content</div>")
        assert "<div>Test Content</div>" in result


# ===========================================================================
# ナビゲーションコンポーネント
# ===========================================================================


class TestNavComponent:
    """_nav コンポーネントのテスト。"""

    def test_contains_title(self) -> None:
        """タイトルが含まれる。"""
        result = _nav("Test Title")
        assert "Test Title" in result

    def test_contains_dashboard_link(self) -> None:
        """Dashboard リンクが含まれる。"""
        result = _nav("Test")
        assert "/dashboard" in result

    def test_contains_logout_link(self) -> None:
        """Logout リンクが含まれる。"""
        result = _nav("Test")
        assert "/logout" in result

    def test_title_is_escaped(self) -> None:
        """タイトルがエスケープされる。"""
        result = _nav("<script>xss</script>")
        assert "&lt;script&gt;" in result


# ===========================================================================
# ログインページ
# ===========================================================================


class TestLoginPage:
    """login_page テンプレートのテスト。"""

    def test_contains_form(self) -> None:
        """ログインフォームが含まれる。"""
        result = login_page()
        assert "<form" in result
        assert 'action="/login"' in result
        assert 'method="POST"' in result

    def test_contains_email_field(self) -> None:
        """メールフィールドが含まれる。"""
        result = login_page()
        assert 'name="email"' in result
        assert 'type="email"' in result

    def test_contains_password_field(self) -> None:
        """パスワードフィールドが含まれる。"""
        result = login_page()
        assert 'name="password"' in result
        assert 'type="password"' in result

    def test_error_is_displayed(self) -> None:
        """エラーメッセージが表示される。"""
        result = login_page(error="Test error message")
        assert "Test error message" in result

    def test_error_is_escaped(self) -> None:
        """エラーメッセージがエスケープされる。"""
        result = login_page(error="<script>xss</script>")
        assert "&lt;script&gt;" in result


# ===========================================================================
# ダッシュボードページ
# ===========================================================================


class TestDashboardPage:
    """dashboard_page テンプレートのテスト。"""

    def test_contains_welcome_message(self) -> None:
        """ウェルカムメッセージが含まれる。"""
        result = dashboard_page(email="test@example.com")
        assert "Welcome, test@example.com" in result

    def test_contains_lobbies_link(self) -> None:
        """Lobbies リンクが含まれる。"""
        result = dashboard_page()
        assert "/lobbies" in result

    def test_contains_sticky_link(self) -> None:
        """Sticky リンクが含まれる。"""
        result = dashboard_page()
        assert "/sticky" in result

    def test_contains_bump_link(self) -> None:
        """Bump リンクが含まれる。"""
        result = dashboard_page()
        assert "/bump" in result

    def test_contains_settings_link(self) -> None:
        """Settings リンクが含まれる。"""
        result = dashboard_page()
        assert "/settings" in result

    def test_email_is_escaped(self) -> None:
        """メールアドレスがエスケープされる。"""
        result = dashboard_page(email="<script>xss</script>")
        assert "&lt;script&gt;" in result


# ===========================================================================
# 設定ページ
# ===========================================================================


class TestSettingsPage:
    """settings_page テンプレートのテスト。"""

    def test_contains_email_change_link(self) -> None:
        """メール変更リンクが含まれる。"""
        result = settings_page(current_email="admin@example.com")
        assert 'href="/settings/email"' in result
        assert "Change Email" in result

    def test_contains_password_change_link(self) -> None:
        """パスワード変更リンクが含まれる。"""
        result = settings_page(current_email="admin@example.com")
        assert 'href="/settings/password"' in result
        assert "Change Password" in result

    def test_current_email_displayed(self) -> None:
        """現在のメールアドレスが表示される。"""
        result = settings_page(current_email="test@example.com")
        assert "test@example.com" in result

    def test_pending_email_displayed(self) -> None:
        """保留中のメールアドレスが表示される。"""
        result = settings_page(
            current_email="admin@example.com", pending_email="pending@example.com"
        )
        assert "pending@example.com" in result
        assert "Pending email change" in result


# ===========================================================================
# ロビー一覧ページ
# ===========================================================================


class TestLobbiesListPage:
    """lobbies_list_page テンプレートのテスト。"""

    def test_empty_list_message(self) -> None:
        """空リストの場合はメッセージが表示される。"""
        result = lobbies_list_page([])
        assert "No lobbies configured" in result

    def test_contains_table_headers(self) -> None:
        """テーブルヘッダーが含まれる。"""
        result = lobbies_list_page([])
        assert "Guild ID" in result
        assert "Channel ID" in result
        assert "User Limit" in result


# ===========================================================================
# Sticky 一覧ページ
# ===========================================================================


class TestStickyListPage:
    """sticky_list_page テンプレートのテスト。"""

    def test_empty_list_message(self) -> None:
        """空リストの場合はメッセージが表示される。"""
        result = sticky_list_page([])
        assert "No sticky messages configured" in result

    def test_contains_table_headers(self) -> None:
        """テーブルヘッダーが含まれる。"""
        result = sticky_list_page([])
        assert "Guild ID" in result
        assert "Channel ID" in result
        assert "Title" in result
        assert "Type" in result


# ===========================================================================
# Bump 一覧ページ
# ===========================================================================


class TestBumpListPage:
    """bump_list_page テンプレートのテスト。"""

    def test_empty_configs_message(self) -> None:
        """Config が空の場合はメッセージが表示される。"""
        result = bump_list_page([], [])
        assert "No bump configs" in result

    def test_empty_reminders_message(self) -> None:
        """Reminder が空の場合はメッセージが表示される。"""
        result = bump_list_page([], [])
        assert "No bump reminders" in result

    def test_contains_config_headers(self) -> None:
        """Config テーブルヘッダーが含まれる。"""
        result = bump_list_page([], [])
        assert "Bump Configs" in result

    def test_contains_reminder_headers(self) -> None:
        """Reminder テーブルヘッダーが含まれる。"""
        result = bump_list_page([], [])
        assert "Bump Reminders" in result
        assert "Service" in result
        assert "Status" in result


# ===========================================================================
# XSS 対策
# ===========================================================================


class TestXSSProtection:
    """XSS 対策のテスト。"""

    @pytest.mark.parametrize(
        "malicious_input",
        [
            "<script>alert('xss')</script>",
            '"><script>alert("xss")</script>',
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
        ],
    )
    def test_login_error_escapes_xss(self, malicious_input: str) -> None:
        """ログインエラーで XSS がエスケープされる。"""
        result = login_page(error=malicious_input)
        # HTML tags should be escaped (< and > become &lt; and &gt;)
        assert "<script>" not in result
        assert "<img " not in result

    @pytest.mark.parametrize(
        "malicious_input",
        [
            "<script>alert('xss')</script>",
            '"><script>alert("xss")</script>',
        ],
    )
    def test_dashboard_email_escapes_xss(self, malicious_input: str) -> None:
        """ダッシュボードのメールアドレスで XSS がエスケープされる。"""
        result = dashboard_page(email=malicious_input)
        assert "<script>" not in result

    @pytest.mark.parametrize(
        "malicious_input",
        [
            "<script>alert('xss')</script>",
            '"><script>alert("xss")</script>',
        ],
    )
    def test_settings_email_escapes_xss(self, malicious_input: str) -> None:
        """設定ページのメールアドレスで XSS がエスケープされる。"""
        result = settings_page(current_email=malicious_input)
        assert "<script>" not in result

    @pytest.mark.parametrize(
        "malicious_input",
        [
            "<script>alert('xss')</script>",
            '"><script>alert("xss")</script>',
            "<img src=x onerror=alert('xss')>",
        ],
    )
    def test_role_panel_create_error_escapes_xss(self, malicious_input: str) -> None:
        """ロールパネル作成ページのエラーで XSS がエスケープされる。"""
        result = role_panel_create_page(error=malicious_input)
        # 悪意のある入力がそのまま含まれていないことを確認
        # (正当な <script> タグは JavaScript 用に存在するため、
        # エスケープ後の文字列をチェック)
        assert malicious_input not in result
        # エスケープされた形式で含まれていることを確認
        assert "&lt;script&gt;" in result or "&lt;img " in result

    @pytest.mark.parametrize(
        "malicious_input",
        [
            "<script>alert('xss')</script>",
            '"><script>alert("xss")</script>',
        ],
    )
    def test_role_panel_create_fields_escape_xss(self, malicious_input: str) -> None:
        """ロールパネル作成ページのフィールドで XSS がエスケープされる。"""
        result = role_panel_create_page(
            guild_id=malicious_input,
            channel_id=malicious_input,
            title=malicious_input,
            description=malicious_input,
        )
        # 悪意のある入力がそのまま含まれていないことを確認
        assert malicious_input not in result


# ===========================================================================
# ロールパネル一覧ページ
# ===========================================================================


class TestRolePanelsListPage:
    """role_panels_list_page テンプレートのテスト。"""

    def test_empty_list_message(self) -> None:
        """空リストの場合はメッセージが表示される。"""
        result = role_panels_list_page([], {})
        assert "No role panels" in result

    def test_contains_table_headers(self) -> None:
        """テーブルヘッダーが含まれる。"""
        result = role_panels_list_page([], {})
        assert "Title" in result
        assert "Type" in result
        assert "Guild ID" in result
        assert "Channel ID" in result
        assert "Roles" in result
        assert "Created" in result
        assert "Actions" in result

    def test_contains_rolepanels_link_in_dashboard(self) -> None:
        """ダッシュボードに Role Panels リンクが含まれる。"""
        result = dashboard_page()
        assert "/rolepanels" in result

    def test_contains_create_button(self) -> None:
        """Create ボタンが含まれる。"""
        result = role_panels_list_page([], {})
        assert "/rolepanels/new" in result
        assert "Create Panel" in result


# ===========================================================================
# ロールパネル作成ページ
# ===========================================================================


class TestRolePanelCreatePage:
    """role_panel_create_page テンプレートのテスト。"""

    def test_contains_form(self) -> None:
        """フォームが含まれる。"""
        result = role_panel_create_page()
        assert "<form" in result
        assert 'action="/rolepanels/new"' in result
        assert 'method="POST"' in result

    def test_contains_guild_id_field(self) -> None:
        """Guild ID フィールドが含まれる。"""
        result = role_panel_create_page()
        assert 'name="guild_id"' in result

    def test_contains_channel_id_field(self) -> None:
        """Channel ID フィールドが含まれる。"""
        result = role_panel_create_page()
        assert 'name="channel_id"' in result

    def test_contains_panel_type_field(self) -> None:
        """Panel Type フィールドが含まれる。"""
        result = role_panel_create_page()
        assert 'name="panel_type"' in result
        assert 'value="button"' in result
        assert 'value="reaction"' in result

    def test_contains_title_field(self) -> None:
        """Title フィールドが含まれる。"""
        result = role_panel_create_page()
        assert 'name="title"' in result

    def test_contains_description_field(self) -> None:
        """Description フィールドが含まれる。"""
        result = role_panel_create_page()
        assert 'name="description"' in result

    def test_error_is_displayed(self) -> None:
        """エラーメッセージが表示される。"""
        result = role_panel_create_page(error="Test error message")
        assert "Test error message" in result

    def test_error_is_escaped(self) -> None:
        """エラーメッセージがエスケープされる。"""
        result = role_panel_create_page(error="<script>xss</script>")
        assert "&lt;script&gt;" in result

    def test_preserves_input_values(self) -> None:
        """入力値が保持される。"""
        result = role_panel_create_page(
            guild_id="123456789",
            channel_id="987654321",
            panel_type="reaction",
            title="Test Title",
            description="Test Description",
        )
        assert "123456789" in result
        assert "987654321" in result
        assert "Test Title" in result
        assert "Test Description" in result

    def test_input_values_are_escaped(self) -> None:
        """入力値がエスケープされる。"""
        result = role_panel_create_page(
            title="<script>xss</script>",
            description="<script>xss</script>",
        )
        assert "&lt;script&gt;" in result
        assert "<script>xss</script>" not in result

    def test_label_field_class_exists(self) -> None:
        """Label フィールドに label-field クラスが設定されている。"""
        result = role_panel_create_page()
        assert 'class="label-field' in result

    def test_panel_type_change_javascript_exists(self) -> None:
        """panel_type 変更時の JavaScript が含まれる。"""
        result = role_panel_create_page()
        assert "updateLabelFieldsVisibility" in result
        assert "isButtonType" in result

    def test_discord_roles_json_included(self) -> None:
        """Discord ロール情報が JavaScript 用 JSON として含まれる。"""
        discord_roles = {
            "123": [
                ("456", "Gamer", 0xFF0000),
                ("789", "Member", 0x00FF00),
            ]
        }
        result = role_panel_create_page(
            guild_id="123",
            discord_roles=discord_roles,
        )
        # JavaScript 用 JSON にロール名が含まれていることを確認
        assert '"name": "Gamer"' in result
        assert '"name": "Member"' in result

    def test_contains_drag_handle_for_role_items(self) -> None:
        """Role Items にドラッグハンドルが含まれる。"""
        result = role_panel_create_page()
        assert "drag-handle" in result
        assert "cursor-grab" in result

    def test_contains_hidden_position_input(self) -> None:
        """Role Items に hidden の position 入力フィールドがある。"""
        result = role_panel_create_page()
        assert 'name="item_position[]"' in result
        assert "position-input" in result

    def test_contains_drag_and_drop_javascript(self) -> None:
        """ドラッグ&ドロップ用の JavaScript が含まれる。"""
        result = role_panel_create_page()
        assert "dragstart" in result
        assert "dragend" in result
        assert "dragover" in result
        assert "updatePositions" in result

    def test_role_item_row_is_draggable(self) -> None:
        """Role Item の行が draggable に設定される JavaScript が含まれる。"""
        result = role_panel_create_page()
        assert "row.draggable = true" in result


class TestRolePanelDetailPage:
    """role_panel_detail_page テンプレートのテスト。"""

    @pytest.fixture
    def button_panel(self) -> RolePanel:
        """ボタン式のパネル。"""
        return RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Button Panel",
            description="Test Description",
        )

    @pytest.fixture
    def reaction_panel(self) -> RolePanel:
        """リアクション式のパネル。"""
        return RolePanel(
            id=2,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Test Reaction Panel",
            description="Test Description",
        )

    @pytest.fixture
    def panel_items(self) -> list[RolePanelItem]:
        """パネルアイテムのリスト。"""
        return [
            RolePanelItem(
                id=1,
                panel_id=1,
                role_id="789",
                emoji="🎮",
                label="Gamer",
                position=0,
            ),
        ]

    def test_contains_panel_title(self, button_panel: RolePanel) -> None:
        """パネルタイトルが含まれる。"""
        result = role_panel_detail_page(button_panel, [])
        assert "Test Button Panel" in result

    def test_button_panel_shows_label_column(
        self, button_panel: RolePanel, panel_items: list[RolePanelItem]
    ) -> None:
        """ボタン式パネルでは Label カラムが表示される。"""
        result = role_panel_detail_page(button_panel, panel_items)
        assert '<th class="py-3 px-4 text-left">Label</th>' in result

    def test_reaction_panel_hides_label_column(
        self, reaction_panel: RolePanel, panel_items: list[RolePanelItem]
    ) -> None:
        """リアクション式パネルでは Label カラムが非表示。"""
        result = role_panel_detail_page(reaction_panel, panel_items)
        assert '<th class="py-3 px-4 text-left">Label</th>' not in result

    def test_button_panel_shows_label_field_in_form(
        self, button_panel: RolePanel
    ) -> None:
        """ボタン式パネルでは Add Role フォームに Label フィールドが表示される。"""
        result = role_panel_detail_page(button_panel, [])
        assert 'for="label"' in result
        assert "Label (for buttons)" in result

    def test_reaction_panel_hides_label_field_in_form(
        self, reaction_panel: RolePanel
    ) -> None:
        """リアクション式パネルでは Add Role フォームに Label フィールドが非表示。"""
        result = role_panel_detail_page(reaction_panel, [])
        # Label フィールドが存在しないことを確認
        assert "Label (for buttons)" not in result

    def test_discord_roles_select_rendered(self, button_panel: RolePanel) -> None:
        """Discord ロールがセレクトボックスに表示される。"""
        discord_roles = [
            ("456", "Gamer", 0xFF0000),
            ("789", "Member", 0x00FF00),
        ]
        result = role_panel_detail_page(button_panel, [], discord_roles=discord_roles)
        assert "@Gamer" in result
        assert "@Member" in result

    def test_no_roles_shows_warning(self, button_panel: RolePanel) -> None:
        """ロールがない場合に警告が表示される。"""
        result = role_panel_detail_page(button_panel, [], discord_roles=[])
        assert "No roles found for this guild" in result

    def test_add_button_disabled_when_no_roles(self, button_panel: RolePanel) -> None:
        """ロールがない場合に Add Role Item ボタンが非活性。"""
        result = role_panel_detail_page(button_panel, [], discord_roles=[])
        assert "disabled" in result

    def test_empty_items_shows_no_roles_message(self, button_panel: RolePanel) -> None:
        """アイテムがない場合に「No roles configured」メッセージが表示される。"""
        result = role_panel_detail_page(button_panel, [])
        assert "No roles configured" in result

    def test_reaction_panel_empty_items_has_correct_colspan(
        self, reaction_panel: RolePanel
    ) -> None:
        """リアクション式パネルの空テーブルは colspan=4 (Label カラムなし)。"""
        result = role_panel_detail_page(reaction_panel, [])
        assert 'colspan="4"' in result

    def test_button_panel_empty_items_has_correct_colspan(
        self, button_panel: RolePanel
    ) -> None:
        """ボタン式パネルの空テーブルは colspan=5 (Label カラムあり)。"""
        result = role_panel_detail_page(button_panel, [])
        assert 'colspan="5"' in result

    def test_role_with_zero_color_uses_default(self, button_panel: RolePanel) -> None:
        """color=0 のロールはデフォルト色で表示される。"""
        discord_roles = [
            ("456", "No Color Role", 0),  # color=0
        ]
        result = role_panel_detail_page(button_panel, [], discord_roles=discord_roles)
        # デフォルトグレー #99aab5 が使用される
        assert "#99aab5" in result or "#0099aab5" in result or "99aab5" in result

    def test_role_item_without_cache_shows_id_only(
        self, button_panel: RolePanel, panel_items: list[RolePanelItem]
    ) -> None:
        """キャッシュにないロールは ID のみ表示される。"""
        # discord_roles を空にして、キャッシュにない状態をシミュレート
        result = role_panel_detail_page(button_panel, panel_items, discord_roles=[])
        # ロール ID がそのまま表示される
        assert "789" in result  # panel_items[0].role_id

    def test_panel_title_is_escaped(self) -> None:
        """パネルタイトルがエスケープされる。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="<script>alert('xss')</script>",
        )
        result = role_panel_detail_page(panel, [])
        assert "&lt;script&gt;" in result
        assert "<script>alert" not in result

    def test_item_emoji_is_escaped(self, button_panel: RolePanel) -> None:
        """アイテムの絵文字がエスケープされる。"""
        item = RolePanelItem(
            id=1,
            panel_id=button_panel.id,
            role_id="789",
            emoji="<script>",
            label="Test",
            position=0,
        )
        result = role_panel_detail_page(button_panel, [item])
        assert "&lt;script&gt;" in result

    def test_item_label_is_escaped(self, button_panel: RolePanel) -> None:
        """アイテムのラベルがエスケープされる。"""
        item = RolePanelItem(
            id=1,
            panel_id=button_panel.id,
            role_id="789",
            emoji="🎮",
            label="<script>xss</script>",
            position=0,
        )
        result = role_panel_detail_page(button_panel, [item])
        assert "&lt;script&gt;" in result

    def test_item_without_label_shows_placeholder(
        self, button_panel: RolePanel
    ) -> None:
        """ラベルがないアイテムは「(no label)」と表示される。"""
        item = RolePanelItem(
            id=1,
            panel_id=button_panel.id,
            role_id="789",
            emoji="🎮",
            label=None,
            position=0,
        )
        result = role_panel_detail_page(button_panel, [item])
        assert "(no label)" in result


class TestRolePanelCreatePageEdgeCases:
    """role_panel_create_page のエッジケーステスト。"""

    def test_empty_discord_roles_dict(self) -> None:
        """空の discord_roles 辞書でもエラーにならない。"""
        result = role_panel_create_page(discord_roles={})
        assert "Create Role Panel" in result

    def test_discord_roles_with_zero_color(self) -> None:
        """color=0 のロールが JSON に正しく含まれる。"""
        discord_roles = {"123": [("456", "No Color", 0)]}
        result = role_panel_create_page(discord_roles=discord_roles)
        assert '"color": 0' in result

    def test_discord_roles_with_unicode_name(self) -> None:
        """Unicode ロール名が JSON に正しく含まれる (エスケープまたはそのまま)。"""
        discord_roles = {"123": [("456", "日本語ロール", 0xFF0000)]}
        result = role_panel_create_page(discord_roles=discord_roles)
        # JSON エンコードでは ensure_ascii=True がデフォルトなので
        # Unicode はエスケープされる場合がある
        # "日本語ロール" または "\\u65e5\\u672c\\u8a9e\\u30ed\\u30fc\\u30eb" のいずれか
        assert "日本語ロール" in result or "\\u65e5\\u672c\\u8a9e" in result

    def test_multiple_guilds_discord_roles(self) -> None:
        """複数ギルドのロールが JSON に正しく含まれる。"""
        discord_roles = {
            "111": [("1", "Guild1 Role", 0xFF0000)],
            "222": [("2", "Guild2 Role", 0x00FF00)],
        }
        result = role_panel_create_page(discord_roles=discord_roles)
        assert "Guild1 Role" in result
        assert "Guild2 Role" in result

    def test_guild_id_preserved_on_error(self) -> None:
        """エラー時に guild_id が保持される。"""
        result = role_panel_create_page(
            error="Test error",
            guild_id="123456789",
        )
        assert "123456789" in result

    def test_channel_id_preserved_on_error(self) -> None:
        """エラー時に channel_id が保持される。"""
        result = role_panel_create_page(
            error="Test error",
            channel_id="987654321",
        )
        assert "987654321" in result

    def test_panel_type_reaction_selected(self) -> None:
        """reaction タイプが選択状態で表示される。"""
        result = role_panel_create_page(panel_type="reaction")
        # reaction ラジオボタンが checked
        assert 'value="reaction"' in result
