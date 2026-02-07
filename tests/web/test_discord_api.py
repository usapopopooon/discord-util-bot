"""Tests for Discord API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.database.models import (
    RolePanel,
    RolePanelItem,
    TicketPanel,
    TicketPanelCategory,
)
from src.web.discord_api import (
    _create_components_payload,
    _create_content_text,
    _create_embed_payload,
    add_reactions_to_message,
    clear_reactions_from_message,
    delete_discord_message,
    edit_role_panel_in_discord,
    post_role_panel_to_discord,
    post_ticket_panel_to_discord,
)

# ===========================================================================
# Embed ペイロード生成テスト
# ===========================================================================


class TestCreateEmbedPayload:
    """_create_embed_payload 関数のテスト。"""

    def test_basic_embed(self) -> None:
        """基本的な Embed ペイロードを生成できる。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
            description="Test description",
            color=0xFF0000,
        )
        result = _create_embed_payload(panel, [])

        assert result["title"] == "Test Panel"
        assert result["description"] == "Test description"
        assert result["color"] == 0xFF0000

    def test_embed_without_description(self) -> None:
        """説明なしの Embed ペイロードを生成できる。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
            description=None,
        )
        result = _create_embed_payload(panel, [])

        assert result["description"] == ""

    def test_embed_default_color(self) -> None:
        """色指定なしの場合はデフォルトの青を使用。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
            color=None,
        )
        result = _create_embed_payload(panel, [])

        assert result["color"] == 0x3498DB  # Blue

    def test_embed_color_zero_uses_default(self) -> None:
        """color=0 の場合はデフォルトの青を使用 (0 は黒で、意図しない可能性が高い)。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
            color=0,
        )
        result = _create_embed_payload(panel, [])

        assert result["color"] == 0x3498DB  # Blue default

    def test_embed_custom_color_preserved(self) -> None:
        """カスタムカラーが正しく保持される。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
            color=0xFF5733,  # Orange
        )
        result = _create_embed_payload(panel, [])

        assert result["color"] == 0xFF5733

    def test_embed_no_fields(self) -> None:
        """Embed にはフィールドを追加しない (タイトルと説明のみ)。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Test Panel",
        )
        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮"),
        ]
        result = _create_embed_payload(panel, items)

        assert "fields" not in result


# ===========================================================================
# テキストメッセージ生成テスト
# ===========================================================================


class TestCreateContentText:
    """_create_content_text 関数のテスト。"""

    def test_basic_content(self) -> None:
        """基本的なテキストメッセージを生成できる。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
            description="Test description",
        )
        result = _create_content_text(panel, [])

        assert "**Test Panel**" in result
        assert "Test description" in result

    def test_content_without_description(self) -> None:
        """説明なしのテキストメッセージを生成できる。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
            description=None,
        )
        result = _create_content_text(panel, [])

        assert "**Test Panel**" in result

    def test_content_no_role_list(self) -> None:
        """テキストメッセージにロール一覧は含まれない (タイトルと説明のみ)。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Test Panel",
            description="Test description",
        )
        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮"),
        ]
        result = _create_content_text(panel, items)

        assert "**Test Panel**" in result
        assert "Test description" in result
        assert "ロール一覧" not in result


# ===========================================================================
# コンポーネントペイロード生成テスト
# ===========================================================================


class TestCreateComponentsPayload:
    """_create_components_payload 関数のテスト。"""

    def test_button_panel_creates_components(self) -> None:
        """ボタン式パネルでコンポーネントを生成する。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        items = [
            RolePanelItem(
                id=1,
                panel_id=1,
                role_id="111",
                emoji="🎮",
                label="Game",
                style="primary",
            ),
        ]
        result = _create_components_payload(panel, items)

        assert len(result) == 1  # 1 action row
        assert result[0]["type"] == 1  # Action Row
        assert len(result[0]["components"]) == 1  # 1 button
        button = result[0]["components"][0]
        assert button["type"] == 2  # Button
        assert button["style"] == 1  # Primary
        assert button["label"] == "Game"
        assert button["custom_id"] == "role_panel:1:1"

    def test_reaction_panel_no_components(self) -> None:
        """リアクション式パネルではコンポーネントを生成しない。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Test Panel",
        )
        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮"),
        ]
        result = _create_components_payload(panel, items)

        assert result == []

    def test_components_split_into_action_rows(self) -> None:
        """5ボタン以上で action row を分割する。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        items = [
            RolePanelItem(id=i, panel_id=1, role_id=str(i * 100), emoji=f"{i}️⃣")
            for i in range(1, 8)
        ]
        result = _create_components_payload(panel, items)

        assert len(result) == 2  # 2 action rows (5 + 2)
        assert len(result[0]["components"]) == 5
        assert len(result[1]["components"]) == 2

    def test_custom_emoji_parsing(self) -> None:
        """Discord カスタム絵文字をパースする。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="<:custom:123456789>"),
        ]
        result = _create_components_payload(panel, items)

        button = result[0]["components"][0]
        assert button["emoji"]["name"] == "custom"
        assert button["emoji"]["id"] == "123456789"
        assert button["emoji"]["animated"] is False

    def test_animated_emoji_parsing(self) -> None:
        """アニメーション絵文字をパースする。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="<a:anim:987654321>"),
        ]
        result = _create_components_payload(panel, items)

        button = result[0]["components"][0]
        assert button["emoji"]["animated"] is True

    def test_unicode_emoji_in_button(self) -> None:
        """Unicode 絵文字がボタンに設定される。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮"),
        ]
        result = _create_components_payload(panel, items)

        button = result[0]["components"][0]
        assert button["emoji"]["name"] == "🎮"

    def test_malformed_custom_emoji_no_crash(self) -> None:
        """不正なカスタム絵文字形式でもクラッシュしない。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        # パーツが3未満の不正な形式
        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="<:bad>"),
        ]
        result = _create_components_payload(panel, items)

        # クラッシュせずにボタンが作成される (emoji キーなし)
        assert len(result) == 1
        button = result[0]["components"][0]
        assert "emoji" not in button

    def test_button_without_label_or_emoji(self) -> None:
        """ラベルも絵文字もないボタンが作成できる。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji=None, label=None),
        ]
        result = _create_components_payload(panel, items)

        assert len(result) == 1
        button = result[0]["components"][0]
        assert "label" not in button
        assert "emoji" not in button


# ===========================================================================
# Discord API 投稿テスト
# ===========================================================================


class TestPostRolePanelToDiscord:
    """post_role_panel_to_discord 関数のテスト。"""

    @pytest.fixture
    def panel(self) -> RolePanel:
        """テスト用パネル。"""
        return RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
            description="Test",
            use_embed=True,
        )

    @pytest.fixture
    def items(self) -> list[RolePanelItem]:
        """テスト用アイテム。"""
        return [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮"),
        ]

    async def test_returns_error_without_token(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """トークンがない場合はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "")

        success, message_id, error = await post_role_panel_to_discord(panel, items)

        assert success is False
        assert message_id is None
        assert "token" in error.lower()

    async def test_successful_post(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """投稿成功時はメッセージ ID を返す。"""
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "999888777"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            success, message_id, error = await post_role_panel_to_discord(panel, items)

        assert success is True
        assert message_id == "999888777"
        assert error is None

    async def test_successful_post_with_201(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """投稿成功時 (201 Created) もメッセージ ID を返す。"""
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "888777666"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            success, message_id, error = await post_role_panel_to_discord(panel, items)

        assert success is True
        assert message_id == "888777666"
        assert error is None

    async def test_forbidden_error(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """403 エラー時は権限エラーメッセージを返す。"""
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.content = b'{"message": "Missing Access"}'
        mock_response.json.return_value = {"message": "Missing Access"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            success, message_id, error = await post_role_panel_to_discord(panel, items)

        assert success is False
        assert message_id is None
        assert "権限" in error

    async def test_not_found_error(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """404 エラー時はチャンネル見つからないエラーを返す。"""
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.content = b'{"message": "Unknown Channel"}'
        mock_response.json.return_value = {"message": "Unknown Channel"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            success, message_id, error = await post_role_panel_to_discord(panel, items)

        assert success is False
        assert "チャンネル" in error or "見つかり" in error

    async def test_timeout_error(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """タイムアウト時はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = (
                httpx.TimeoutException("timeout")
            )

            success, message_id, error = await post_role_panel_to_discord(panel, items)

        assert success is False
        assert "タイムアウト" in error

    async def test_unauthorized_error(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """401 エラー時はトークン無効エラーを返す。"""
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.content = b'{"message": "Unauthorized"}'
        mock_response.json.return_value = {"message": "Unauthorized"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            success, message_id, error = await post_role_panel_to_discord(panel, items)

        assert success is False
        assert "トークン" in error

    async def test_request_error(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """RequestError 時は接続エラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = (
                httpx.RequestError("Connection failed")
            )

            success, message_id, error = await post_role_panel_to_discord(panel, items)

        assert success is False
        assert "接続" in error

    async def test_post_without_embed(
        self,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """use_embed=False でテキストメッセージを投稿できる。"""
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
            description="Test",
            use_embed=False,  # Embed を使わない
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "999888777"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            success, message_id, error = await post_role_panel_to_discord(panel, items)

        assert success is True
        assert message_id == "999888777"
        # content がペイロードに含まれることを確認
        call_args = mock_post.call_args
        payload = call_args.kwargs.get("json", {})
        assert "content" in payload
        assert "embeds" not in payload


# ===========================================================================
# リアクション追加テスト
# ===========================================================================


class TestAddReactionsToMessage:
    """add_reactions_to_message 関数のテスト。"""

    async def test_returns_error_without_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """トークンがない場合はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "")

        items = [RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮")]
        success, error = await add_reactions_to_message("123", "456", items)

        assert success is False
        assert "token" in error.lower()

    async def test_empty_items_returns_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """アイテムが空の場合は成功を返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        success, error = await add_reactions_to_message("123", "456", [])

        assert success is True
        assert error is None

    async def test_successful_reaction_add(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """リアクション追加成功時は成功を返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = AsyncMock()
        mock_response.status_code = 204

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.put.return_value = (
                mock_response
            )

            items = [RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮")]
            success, error = await add_reactions_to_message("123", "456", items)

        assert success is True
        assert error is None

    async def test_custom_emoji_reaction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """カスタム絵文字のリアクションを追加できる。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = AsyncMock()
        mock_response.status_code = 204

        with patch("httpx.AsyncClient") as mock_client:
            mock_put = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.put = mock_put

            items = [
                RolePanelItem(id=1, panel_id=1, role_id="111", emoji="<:custom:123456>")
            ]
            success, error = await add_reactions_to_message("123", "456", items)

        assert success is True
        # URL にカスタム絵文字がエンコードされていることを確認
        call_args = mock_put.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        assert "custom:123456" in url

    async def test_reaction_error_continues(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """リアクション追加エラーが発生しても他のリアクションは続行する。"""
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        # 最初は失敗、次は成功
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.content = b'{"message": "Bad emoji"}'
        error_response.json.return_value = {"message": "Bad emoji"}

        success_response = MagicMock()
        success_response.status_code = 204

        with patch("httpx.AsyncClient") as mock_client:
            mock_put = AsyncMock(side_effect=[error_response, success_response])
            mock_client.return_value.__aenter__.return_value.put = mock_put

            items = [
                RolePanelItem(id=1, panel_id=1, role_id="111", emoji="bad"),
                RolePanelItem(id=2, panel_id=1, role_id="222", emoji="🎮"),
            ]
            success, error = await add_reactions_to_message("123", "456", items)

        # 部分的な失敗でも全体としては成功
        assert success is True
        assert error is None
        # 2回呼ばれた
        assert mock_put.call_count == 2

    async def test_reaction_timeout_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """リアクション追加時のタイムアウトエラー。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.put.side_effect = (
                httpx.TimeoutException("timeout")
            )

            items = [RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮")]
            success, error = await add_reactions_to_message("123", "456", items)

        assert success is False
        assert "タイムアウト" in error

    async def test_reaction_request_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """リアクション追加時の接続エラー。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.put.side_effect = (
                httpx.RequestError("Connection failed")
            )

            items = [RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮")]
            success, error = await add_reactions_to_message("123", "456", items)

        assert success is False
        assert "接続" in error

    async def test_multiple_reactions_added_with_delay(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """複数リアクション追加時にレート制限対策のディレイが入る。"""
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        success_response = MagicMock()
        success_response.status_code = 204

        call_times: list[float] = []
        import time

        async def mock_put(*_args, **_kwargs):
            call_times.append(time.monotonic())
            return success_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.put = mock_put

            # 3つのリアクションを追加
            items = [
                RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮", position=0),
                RolePanelItem(id=2, panel_id=1, role_id="222", emoji="🎯", position=1),
                RolePanelItem(id=3, panel_id=1, role_id="333", emoji="🎲", position=2),
            ]
            success, error = await add_reactions_to_message("123", "456", items)

        assert success is True
        assert error is None
        # 3回呼ばれた
        assert len(call_times) == 3
        # ディレイが入っていることを確認 (各呼び出しの間隔が 0.2 秒以上)
        for i in range(1, len(call_times)):
            assert call_times[i] - call_times[i - 1] >= 0.2


# ===========================================================================
# メッセージ編集テスト
# ===========================================================================


class TestEditRolePanelInDiscord:
    """edit_role_panel_in_discord 関数のテスト。"""

    @pytest.fixture
    def panel(self) -> RolePanel:
        """テスト用パネル (message_id 付き)。"""
        return RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            message_id="789",
            panel_type="button",
            title="Test Panel",
            description="Test",
            use_embed=True,
        )

    @pytest.fixture
    def items(self) -> list[RolePanelItem]:
        """テスト用アイテム。"""
        return [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮"),
        ]

    async def test_returns_error_without_token(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """トークンがない場合はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "")

        success, error = await edit_role_panel_in_discord(panel, items)

        assert success is False
        assert "token" in error.lower()

    async def test_returns_error_without_message_id(
        self,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """message_id がない場合はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            message_id=None,  # message_id なし
            panel_type="button",
            title="Test Panel",
        )

        success, error = await edit_role_panel_in_discord(panel, items)

        assert success is False
        assert "message_id" in error.lower()

    async def test_successful_edit(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """編集成功時は True を返す。"""
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.patch = AsyncMock(
                return_value=mock_response
            )

            success, error = await edit_role_panel_in_discord(panel, items)

        assert success is True
        assert error is None

    async def test_forbidden_error(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """403 エラー時は権限エラーメッセージを返す。"""
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.content = b'{"message": "Missing Access"}'
        mock_response.json.return_value = {"message": "Missing Access"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.patch = AsyncMock(
                return_value=mock_response
            )

            success, error = await edit_role_panel_in_discord(panel, items)

        assert success is False
        assert "権限" in error

    async def test_not_found_error(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """404 エラー時はメッセージ見つからないエラーを返す。"""
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.content = b'{"message": "Unknown Message"}'
        mock_response.json.return_value = {"message": "Unknown Message"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.patch = AsyncMock(
                return_value=mock_response
            )

            success, error = await edit_role_panel_in_discord(panel, items)

        assert success is False
        assert "メッセージ" in error or "見つかり" in error

    async def test_timeout_error(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """タイムアウト時はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.patch.side_effect = (
                httpx.TimeoutException("timeout")
            )

            success, error = await edit_role_panel_in_discord(panel, items)

        assert success is False
        assert "タイムアウト" in error

    async def test_request_error(
        self,
        panel: RolePanel,
        items: list[RolePanelItem],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """RequestError 時は接続エラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.patch.side_effect = (
                httpx.RequestError("Connection failed")
            )

            success, error = await edit_role_panel_in_discord(panel, items)

        assert success is False
        assert "接続" in error


# ===========================================================================
# リアクションクリアテスト
# ===========================================================================


class TestClearReactionsFromMessage:
    """clear_reactions_from_message 関数のテスト。"""

    async def test_returns_error_without_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """トークンがない場合はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "")

        success, error = await clear_reactions_from_message("123", "456")

        assert success is False
        assert "token" in error.lower()

    async def test_successful_clear(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """リアクションクリア成功時は成功を返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = AsyncMock()
        mock_response.status_code = 204

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.delete.return_value = (
                mock_response
            )

            success, error = await clear_reactions_from_message("123", "456")

        assert success is True
        assert error is None

    async def test_clear_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """リアクションクリアエラー時はエラーを返す。"""
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.content = b'{"message": "Missing Permissions"}'
        mock_response.json.return_value = {"message": "Missing Permissions"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.delete.return_value = (
                mock_response
            )

            success, error = await clear_reactions_from_message("123", "456")

        assert success is False
        assert "Missing Permissions" in error

    async def test_timeout_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """タイムアウト時はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.delete.side_effect = (
                httpx.TimeoutException("timeout")
            )

            success, error = await clear_reactions_from_message("123", "456")

        assert success is False
        assert "タイムアウト" in error

    async def test_request_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """RequestError 時は接続エラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.delete.side_effect = (
                httpx.RequestError("Connection failed")
            )

            success, error = await clear_reactions_from_message("123", "456")

        assert success is False
        assert "接続" in error


class TestAddReactionsWithClear:
    """add_reactions_to_message の clear_existing パラメータテスト。"""

    async def test_clear_existing_calls_clear(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """clear_existing=True で clear_reactions_from_message が呼ばれる。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_put_response = AsyncMock()
        mock_put_response.status_code = 204

        mock_delete_response = AsyncMock()
        mock_delete_response.status_code = 204

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.put.return_value = mock_put_response
            mock_instance.delete.return_value = mock_delete_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            items = [RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮")]
            success, error = await add_reactions_to_message(
                "123", "456", items, clear_existing=True
            )

        assert success is True
        # delete (clear) が呼ばれた
        assert mock_instance.delete.called

    async def test_no_clear_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """clear_existing=False (デフォルト) では clear は呼ばれない。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_put_response = AsyncMock()
        mock_put_response.status_code = 204

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.put.return_value = mock_put_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            items = [RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮")]
            success, error = await add_reactions_to_message("123", "456", items)

        assert success is True
        # delete (clear) は呼ばれない
        assert not mock_instance.delete.called

    async def test_delay_after_clear_before_add(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """clear_existing=True でクリア後にディレイが入る。"""
        import time
        from unittest.mock import MagicMock

        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_delete_response = MagicMock()
        mock_delete_response.status_code = 204

        mock_put_response = MagicMock()
        mock_put_response.status_code = 204

        call_times: list[tuple[str, float]] = []

        async def mock_delete(*_args, **_kwargs):
            call_times.append(("delete", time.monotonic()))
            return mock_delete_response

        async def mock_put(*_args, **_kwargs):
            call_times.append(("put", time.monotonic()))
            return mock_put_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.delete = mock_delete
            mock_instance.put = mock_put
            mock_client.return_value.__aenter__.return_value = mock_instance

            items = [RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮")]
            success, error = await add_reactions_to_message(
                "123", "456", items, clear_existing=True
            )

        assert success is True
        assert error is None
        # delete -> put の順序で呼ばれた
        assert len(call_times) == 2
        assert call_times[0][0] == "delete"
        assert call_times[1][0] == "put"
        # delete と put の間にディレイがある (0.4 秒以上)
        assert call_times[1][1] - call_times[0][1] >= 0.4


# ===========================================================================
# Discord メッセージ削除テスト
# ===========================================================================


class TestDeleteDiscordMessage:
    """delete_discord_message 関数のテスト。"""

    async def test_returns_error_without_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """トークンがない場合はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "")

        success, error = await delete_discord_message("456", "789")

        assert success is False
        assert error is not None
        assert "token" in error.lower()

    async def test_successful_delete(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """メッセージ削除成功 (204)。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = AsyncMock()
        mock_response.status_code = 204

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.delete.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            success, error = await delete_discord_message("456", "789")

        assert success is True
        assert error is None
        mock_instance.delete.assert_called_once()

    async def test_already_deleted_returns_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """メッセージが既に削除済み (404) の場合は成功扱い。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = AsyncMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.delete.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            success, error = await delete_discord_message("456", "789")

        assert success is True
        assert error is None

    async def test_permission_denied(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """権限不足 (403) の場合はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.content = b'{"message": "Missing Permissions"}'
        mock_response.json.return_value = {"message": "Missing Permissions"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.delete.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            success, error = await delete_discord_message("456", "789")

        assert success is False
        assert error is not None
        assert "権限" in error

    async def test_invalid_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """無効なトークン (401) の場合はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "invalid_token")

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.content = b'{"message": "401: Unauthorized"}'
        mock_response.json.return_value = {"message": "401: Unauthorized"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.delete.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            success, error = await delete_discord_message("456", "789")

        assert success is False
        assert error is not None
        assert "トークン" in error

    async def test_timeout_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """タイムアウトの場合はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.delete.side_effect = httpx.TimeoutException("timeout")
            mock_client.return_value.__aenter__.return_value = mock_instance

            success, error = await delete_discord_message("456", "789")

        assert success is False
        assert error is not None
        assert "タイムアウト" in error

    async def test_request_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """リクエストエラーの場合はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.delete.side_effect = httpx.RequestError("connection failed")
            mock_client.return_value.__aenter__.return_value = mock_instance

            success, error = await delete_discord_message("456", "789")

        assert success is False
        assert error is not None
        assert "接続に失敗" in error


# ===========================================================================
# チケットパネル Discord 投稿テスト
# ===========================================================================


class TestPostTicketPanelToDiscord:
    """post_ticket_panel_to_discord 関数のテスト。"""

    @pytest.fixture
    def panel(self) -> TicketPanel:
        """テスト用パネル。"""
        return TicketPanel(
            id=1,
            guild_id="123",
            channel_id="456",
            title="Support Panel",
            description="Click to create a ticket",
        )

    @pytest.fixture
    def associations(self) -> list[TicketPanelCategory]:
        """テスト用関連付け。"""
        return [
            TicketPanelCategory(
                id=1,
                panel_id=1,
                category_id=10,
                button_label="General",
                button_style="primary",
                position=0,
            ),
        ]

    @pytest.fixture
    def category_names(self) -> dict[int, str]:
        """テスト用カテゴリ名マッピング。"""
        return {10: "General Support"}

    async def test_returns_error_without_token(
        self,
        panel: TicketPanel,
        associations: list[TicketPanelCategory],
        category_names: dict[int, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """トークンがない場合はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "")

        success, message_id, error = await post_ticket_panel_to_discord(
            panel, associations, category_names
        )

        assert success is False
        assert message_id is None
        assert "token" in (error or "").lower()

    async def test_successful_post(
        self,
        panel: TicketPanel,
        associations: list[TicketPanelCategory],
        category_names: dict[int, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """投稿成功時はメッセージ ID を返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "111222333"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            success, message_id, error = await post_ticket_panel_to_discord(
                panel, associations, category_names
            )

        assert success is True
        assert message_id == "111222333"
        assert error is None

        # ペイロードにボタンが含まれることを確認
        call_args = mock_post.call_args
        payload = call_args.kwargs.get("json", {})
        assert "components" in payload
        assert "embeds" in payload

    async def test_successful_post_201(
        self,
        panel: TicketPanel,
        associations: list[TicketPanelCategory],
        category_names: dict[int, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """201 Created でもメッセージ ID を返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "444555666"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            success, message_id, error = await post_ticket_panel_to_discord(
                panel, associations, category_names
            )

        assert success is True
        assert message_id == "444555666"

    async def test_post_without_associations(
        self,
        panel: TicketPanel,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """関連付けなしでもパネルを投稿できる (ボタンなし)。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "777888999"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            success, message_id, error = await post_ticket_panel_to_discord(
                panel, [], {}
            )

        assert success is True
        payload = mock_post.call_args.kwargs.get("json", {})
        assert "components" not in payload

    async def test_forbidden_error(
        self,
        panel: TicketPanel,
        associations: list[TicketPanelCategory],
        category_names: dict[int, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """403 エラー時は権限エラーメッセージを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.content = b'{"message": "Missing Access"}'
        mock_response.json.return_value = {"message": "Missing Access"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            success, message_id, error = await post_ticket_panel_to_discord(
                panel, associations, category_names
            )

        assert success is False
        assert message_id is None
        assert "権限" in (error or "")

    async def test_not_found_error(
        self,
        panel: TicketPanel,
        associations: list[TicketPanelCategory],
        category_names: dict[int, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """404 エラー時はチャンネル見つからないエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.content = b'{"message": "Unknown Channel"}'
        mock_response.json.return_value = {"message": "Unknown Channel"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            success, message_id, error = await post_ticket_panel_to_discord(
                panel, associations, category_names
            )

        assert success is False
        assert "チャンネル" in (error or "")

    async def test_unauthorized_error(
        self,
        panel: TicketPanel,
        associations: list[TicketPanelCategory],
        category_names: dict[int, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """401 エラー時はトークン無効エラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.content = b'{"message": "Unauthorized"}'
        mock_response.json.return_value = {"message": "Unauthorized"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            success, message_id, error = await post_ticket_panel_to_discord(
                panel, associations, category_names
            )

        assert success is False
        assert "トークン" in (error or "")

    async def test_timeout_error(
        self,
        panel: TicketPanel,
        associations: list[TicketPanelCategory],
        category_names: dict[int, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """タイムアウト時はエラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = (
                httpx.TimeoutException("timeout")
            )

            success, message_id, error = await post_ticket_panel_to_discord(
                panel, associations, category_names
            )

        assert success is False
        assert "タイムアウト" in (error or "")

    async def test_request_error(
        self,
        panel: TicketPanel,
        associations: list[TicketPanelCategory],
        category_names: dict[int, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """RequestError 時は接続エラーを返す。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = (
                httpx.RequestError("Connection failed")
            )

            success, message_id, error = await post_ticket_panel_to_discord(
                panel, associations, category_names
            )

        assert success is False
        assert "接続" in (error or "")

    async def test_custom_emoji_in_button(
        self,
        panel: TicketPanel,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """カスタム絵文字がボタンペイロードに含まれる。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        associations = [
            TicketPanelCategory(
                id=1,
                panel_id=1,
                category_id=10,
                button_emoji="<:custom:123456789>",
                button_style="primary",
                position=0,
            ),
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "999"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await post_ticket_panel_to_discord(panel, associations, {10: "Test"})

        payload = mock_post.call_args.kwargs.get("json", {})
        button = payload["components"][0]["components"][0]
        assert button["emoji"]["name"] == "custom"
        assert button["emoji"]["id"] == "123456789"
        assert button["emoji"]["animated"] is False

    async def test_animated_emoji_in_button(
        self,
        panel: TicketPanel,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """アニメーション絵文字がボタンペイロードに含まれる。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        associations = [
            TicketPanelCategory(
                id=1,
                panel_id=1,
                category_id=10,
                button_emoji="<a:anim:987654321>",
                button_style="primary",
                position=0,
            ),
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "999"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await post_ticket_panel_to_discord(panel, associations, {10: "Test"})

        payload = mock_post.call_args.kwargs.get("json", {})
        button = payload["components"][0]["components"][0]
        assert button["emoji"]["animated"] is True

    async def test_unicode_emoji_in_button(
        self,
        panel: TicketPanel,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Unicode 絵文字がボタンペイロードに含まれる。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        associations = [
            TicketPanelCategory(
                id=1,
                panel_id=1,
                category_id=10,
                button_emoji="🎫",
                button_style="primary",
                position=0,
            ),
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "999"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await post_ticket_panel_to_discord(panel, associations, {10: "Test"})

        payload = mock_post.call_args.kwargs.get("json", {})
        button = payload["components"][0]["components"][0]
        assert button["emoji"]["name"] == "🎫"

    async def test_buttons_split_into_action_rows(
        self,
        panel: TicketPanel,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """6 ボタン以上で action row を分割する。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        associations = [
            TicketPanelCategory(
                id=i,
                panel_id=1,
                category_id=i * 10,
                button_style="primary",
                position=i,
            )
            for i in range(1, 8)
        ]
        category_names = {i * 10: f"Cat {i}" for i in range(1, 8)}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "999"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await post_ticket_panel_to_discord(panel, associations, category_names)

        payload = mock_post.call_args.kwargs.get("json", {})
        assert len(payload["components"]) == 2  # 5 + 2
        assert len(payload["components"][0]["components"]) == 5
        assert len(payload["components"][1]["components"]) == 2

    async def test_default_description_when_none(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """description が None の場合はデフォルトメッセージを使用。"""
        from src.config import settings

        monkeypatch.setattr(settings, "discord_token", "test_token")

        panel = TicketPanel(
            id=1,
            guild_id="123",
            channel_id="456",
            title="Support",
            description=None,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "999"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await post_ticket_panel_to_discord(panel, [], {})

        payload = mock_post.call_args.kwargs.get("json", {})
        embed = payload["embeds"][0]
        assert "ボタンをクリック" in embed["description"]
