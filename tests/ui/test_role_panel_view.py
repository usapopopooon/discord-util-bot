"""Tests for role panel UI components."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.ui.role_panel_view import (
    ROLE_PANEL_COOLDOWN_SECONDS,
    RoleButton,
    RolePanelCreateModal,
    RolePanelView,
    _cleanup_cooldown_cache,
    _cooldown_cache,
    clear_cooldown_cache,
    create_role_panel_content,
    create_role_panel_embed,
    handle_role_reaction,
    is_on_cooldown,
    refresh_role_panel,
)


@pytest.fixture(autouse=True)
def _clear_role_panel_cooldown() -> None:
    """Clear role panel cooldown cache before each test."""
    clear_cooldown_cache()


class TestRolePanelStateIsolation:
    """autouse fixture によるステート分離が機能することを検証するカナリアテスト."""

    def test_cache_starts_empty(self) -> None:
        """各テスト開始時にキャッシュが空であることを検証."""
        assert len(_cooldown_cache) == 0

    def test_cleanup_time_is_reset(self) -> None:
        """各テスト開始時にクリーンアップ時刻がリセットされていることを検証."""
        import src.ui.role_panel_view as rpv_module

        assert rpv_module._last_cleanup_time == 0.0


# ===========================================================================
# Helper Functions
# ===========================================================================


def _make_role_panel(
    *,
    panel_id: int = 1,
    guild_id: str = "123456789",
    channel_id: str = "987654321",
    panel_type: str = "button",
    title: str = "Test Panel",
    description: str | None = None,
    color: int | None = None,
    message_id: str | None = None,
    use_embed: bool = True,
    excluded_role_ids: str = "[]",
) -> MagicMock:
    """Create a mock RolePanel object."""
    panel = MagicMock()
    panel.id = panel_id
    panel.guild_id = guild_id
    panel.channel_id = channel_id
    panel.panel_type = panel_type
    panel.title = title
    panel.description = description
    panel.color = color
    panel.message_id = message_id
    panel.use_embed = use_embed
    panel.excluded_role_ids = excluded_role_ids
    return panel


def _make_role_panel_item(
    *,
    item_id: int = 1,
    panel_id: int = 1,
    role_id: str = "111222333",
    emoji: str = "🎮",
    label: str | None = "Gamer",
    style: str = "secondary",
    position: int = 0,
) -> MagicMock:
    """Create a mock RolePanelItem object."""
    item = MagicMock()
    item.id = item_id
    item.panel_id = panel_id
    item.role_id = role_id
    item.emoji = emoji
    item.label = label
    item.style = style
    item.position = position
    return item


# ===========================================================================
# RolePanelCreateModal - クラス属性テスト
# ===========================================================================


class TestRolePanelCreateModalClassAttributes:
    """RolePanelCreateModal のクラス属性テスト。

    Modal のインスタンス化はイベントループを必要とするため、
    クラス属性レベルでテストする。
    """

    def test_title_max_length_within_discord_limit(self) -> None:
        """タイトルの max_length が Discord の制限内 (4000)。"""
        # クラス属性として定義された TextInput を取得
        title_input = RolePanelCreateModal.panel_title
        assert title_input.max_length is not None
        assert title_input.max_length <= 4000

    def test_description_max_length_within_discord_limit(self) -> None:
        """説明文の max_length が Discord Modal の制限内 (4000)。

        Discord Modal TextInput の max_length 上限は 4000。
        Embed description の上限 (4096) とは異なる。
        """
        description_input = RolePanelCreateModal.description
        assert description_input.max_length is not None
        assert description_input.max_length <= 4000

    def test_panel_title_is_required(self) -> None:
        """タイトルフィールドは必須。"""
        title_input = RolePanelCreateModal.panel_title
        # TextInput のデフォルトは required=True
        # required が明示的に False でないことを確認
        assert title_input.required is not False
        assert title_input.min_length == 1

    def test_description_is_optional(self) -> None:
        """説明文フィールドは任意。"""
        description_input = RolePanelCreateModal.description
        assert description_input.required is False


# ===========================================================================
# RolePanelView
# ===========================================================================


class TestRolePanelView:
    """RolePanelView のテスト。"""

    @pytest.mark.asyncio
    async def test_view_instantiation(self) -> None:
        """View をインスタンス化できる。"""
        items: list[MagicMock] = []
        view = RolePanelView(panel_id=1, items=items)
        assert view.panel_id == 1
        assert view.timeout is None  # 永続 View

    @pytest.mark.asyncio
    async def test_view_is_persistent(self) -> None:
        """View は永続 (timeout=None)。"""
        view = RolePanelView(panel_id=999, items=[])
        assert view.timeout is None

    @pytest.mark.asyncio
    async def test_view_adds_buttons_for_items(self) -> None:
        """items に対応するボタンが追加される。"""
        items = [
            _make_role_panel_item(item_id=1, emoji="🎮", label="Gamer"),
            _make_role_panel_item(item_id=2, emoji="🎨", label="Artist"),
        ]
        view = RolePanelView(panel_id=1, items=items)
        assert len(view.children) == 2

    @pytest.mark.asyncio
    async def test_view_with_empty_items(self) -> None:
        """items が空でも View を作成できる。"""
        view = RolePanelView(panel_id=1, items=[])
        assert len(view.children) == 0


# ===========================================================================
# RoleButton
# ===========================================================================


class TestRoleButton:
    """RoleButton のテスト。"""

    @pytest.mark.asyncio
    async def test_button_instantiation(self) -> None:
        """ボタンをインスタンス化できる。"""
        item = _make_role_panel_item(
            item_id=2,
            role_id="123456789",
            emoji="🎮",
            label="Test",
            style="success",
        )
        button = RoleButton(panel_id=1, item=item)
        assert button.panel_id == 1
        assert button.role_id == "123456789"
        assert button.label == "Test"

    @pytest.mark.asyncio
    async def test_button_custom_id_format(self) -> None:
        """custom_id のフォーマットが正しい。"""
        item = _make_role_panel_item(item_id=50)
        button = RoleButton(panel_id=100, item=item)
        assert button.custom_id == "role_panel:100:50"

    @pytest.mark.asyncio
    async def test_button_style_mapping(self) -> None:
        """style 文字列が ButtonStyle に変換される。"""
        # primary
        item = _make_role_panel_item(style="primary")
        button = RoleButton(panel_id=1, item=item)
        assert button.style == discord.ButtonStyle.primary

        # success
        item = _make_role_panel_item(style="success")
        button = RoleButton(panel_id=1, item=item)
        assert button.style == discord.ButtonStyle.success

        # danger
        item = _make_role_panel_item(style="danger")
        button = RoleButton(panel_id=1, item=item)
        assert button.style == discord.ButtonStyle.danger

    @pytest.mark.asyncio
    async def test_button_default_style(self) -> None:
        """不明な style は secondary になる。"""
        item = _make_role_panel_item(style="unknown")
        button = RoleButton(panel_id=1, item=item)
        assert button.style == discord.ButtonStyle.secondary


# ===========================================================================
# create_role_panel_embed
# ===========================================================================


class TestCreateRolePanelEmbed:
    """create_role_panel_embed のテスト。"""

    def test_creates_embed_with_title(self) -> None:
        """タイトル付きの Embed を作成できる。"""
        panel = _make_role_panel(title="Test Panel")
        embed = create_role_panel_embed(panel, [])
        assert embed.title == "Test Panel"

    def test_creates_embed_with_description(self) -> None:
        """説明文付きの Embed を作成できる。"""
        panel = _make_role_panel(description="This is a description")
        embed = create_role_panel_embed(panel, [])
        assert embed.description == "This is a description"

    def test_creates_embed_with_custom_color(self) -> None:
        """カスタム色の Embed を作成できる。"""
        panel = _make_role_panel(color=0xFF5733)
        embed = create_role_panel_embed(panel, [])
        assert embed.color is not None
        assert embed.color.value == 0xFF5733

    def test_creates_embed_with_default_color(self) -> None:
        """色未指定時はデフォルト色になる。"""
        panel = _make_role_panel(color=None)
        embed = create_role_panel_embed(panel, [])
        assert embed.color == discord.Color(0x85E7AD)

    def test_creates_embed_without_description(self) -> None:
        """説明文なしの Embed を作成できる。"""
        panel = _make_role_panel(description=None)
        embed = create_role_panel_embed(panel, [])
        # description が None の場合は空文字列になる
        assert embed.description == ""

    def test_reaction_panel_shows_role_list(self) -> None:
        """リアクション式パネルはロール一覧を表示する。"""
        panel = _make_role_panel(panel_type="reaction")
        items = [
            _make_role_panel_item(emoji="🎮", role_id="111"),
            _make_role_panel_item(emoji="🎨", role_id="222"),
        ]
        embed = create_role_panel_embed(panel, items)
        # フィールドが追加されている
        assert len(embed.fields) == 1
        assert embed.fields[0].name == "ロール一覧"
        assert "🎮" in embed.fields[0].value
        assert "🎨" in embed.fields[0].value

    def test_button_panel_no_role_list(self) -> None:
        """ボタン式パネルはロール一覧を表示しない。"""
        panel = _make_role_panel(panel_type="button")
        items = [
            _make_role_panel_item(emoji="🎮", role_id="111"),
        ]
        embed = create_role_panel_embed(panel, items)
        # フィールドなし
        assert len(embed.fields) == 0


# ===========================================================================
# create_role_panel_content
# ===========================================================================


class TestCreateRolePanelContent:
    """create_role_panel_content のテスト。"""

    def test_creates_content_with_title(self) -> None:
        """タイトル付きのテキストコンテンツを作成できる。"""
        panel = _make_role_panel(title="Test Panel", use_embed=False)
        content = create_role_panel_content(panel, [])
        assert "**Test Panel**" in content

    def test_creates_content_with_description(self) -> None:
        """説明文付きのテキストコンテンツを作成できる。"""
        panel = _make_role_panel(description="This is a description", use_embed=False)
        content = create_role_panel_content(panel, [])
        assert "This is a description" in content

    def test_creates_content_without_description(self) -> None:
        """説明文なしのテキストコンテンツを作成できる。"""
        panel = _make_role_panel(title="Title Only", description=None, use_embed=False)
        content = create_role_panel_content(panel, [])
        assert "**Title Only**" in content
        # 説明文がない場合は余分な改行がないはず
        assert content.strip().startswith("**Title Only**")

    def test_reaction_panel_shows_role_list(self) -> None:
        """リアクション式パネルはロール一覧を表示する。"""
        panel = _make_role_panel(panel_type="reaction", use_embed=False)
        items = [
            _make_role_panel_item(emoji="🎮", role_id="111"),
            _make_role_panel_item(emoji="🎨", role_id="222"),
        ]
        content = create_role_panel_content(panel, items)
        assert "**ロール一覧**" in content
        assert "🎮 → <@&111>" in content
        assert "🎨 → <@&222>" in content

    def test_button_panel_no_role_list(self) -> None:
        """ボタン式パネルはロール一覧を表示しない。"""
        panel = _make_role_panel(panel_type="button", use_embed=False)
        items = [
            _make_role_panel_item(emoji="🎮", role_id="111"),
        ]
        content = create_role_panel_content(panel, items)
        # ロール一覧は表示されない
        assert "ロール一覧" not in content

    def test_returns_string(self) -> None:
        """戻り値が文字列であることを確認。"""
        panel = _make_role_panel(use_embed=False)
        content = create_role_panel_content(panel, [])
        assert isinstance(content, str)


# ===========================================================================
# refresh_role_panel
# ===========================================================================


class TestRefreshRolePanel:
    """refresh_role_panel のテスト。"""

    @pytest.mark.asyncio
    async def test_returns_false_if_no_message_id(self) -> None:
        """message_id が None の場合 False を返す。"""
        channel = MagicMock(spec=discord.TextChannel)
        panel = _make_role_panel(message_id=None)
        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, [], bot)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_if_message_not_found(self) -> None:
        """メッセージが見つからない場合 False を返す。"""
        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        panel = _make_role_panel(message_id="123456")
        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, [], bot)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_http_exception(self) -> None:
        """HTTPException 発生時は False を返す。"""
        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "error")
        )
        panel = _make_role_panel(message_id="123456")
        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, [], bot)
        assert result is False

    @pytest.mark.asyncio
    async def test_updates_button_panel(self) -> None:
        """ボタン式パネルを更新できる。"""
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock()

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=msg)

        panel = _make_role_panel(panel_type="button", message_id="123456")
        items = [_make_role_panel_item(emoji="🎮", label="Test")]

        bot = MagicMock(spec=discord.Client)
        bot.add_view = MagicMock()

        result = await refresh_role_panel(channel, panel, items, bot)

        assert result is True
        msg.edit.assert_called_once()
        bot.add_view.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_reaction_panel(self) -> None:
        """リアクション式パネルを更新できる。"""
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock()
        msg.clear_reactions = AsyncMock()
        msg.add_reaction = AsyncMock()

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=msg)

        panel = _make_role_panel(panel_type="reaction", message_id="123456")
        items = [
            _make_role_panel_item(emoji="🎮"),
            _make_role_panel_item(emoji="🎨"),
        ]

        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, items, bot)

        assert result is True
        msg.edit.assert_called_once()
        msg.clear_reactions.assert_called_once()
        assert msg.add_reaction.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_reaction_add_error(self) -> None:
        """リアクション追加失敗時もパネル更新は成功扱い。"""
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock()
        msg.clear_reactions = AsyncMock()
        msg.add_reaction = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "error")
        )

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=msg)

        panel = _make_role_panel(panel_type="reaction", message_id="123456")
        items = [_make_role_panel_item(emoji="🎮")]

        bot = MagicMock(spec=discord.Client)

        # リアクション追加失敗しても True が返る
        result = await refresh_role_panel(channel, panel, items, bot)
        assert result is True


# ===========================================================================
# handle_role_reaction
# ===========================================================================


class TestHandleRoleReaction:
    """handle_role_reaction のテスト。"""

    @pytest.mark.asyncio
    async def test_returns_early_if_member_is_none_on_add(self) -> None:
        """add 時に member が None なら早期リターン。"""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = None

        # 早期リターンするためエラーにならない
        await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_returns_if_panel_not_found(self) -> None:
        """パネルが見つからない場合は何もしない。"""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = MagicMock()
        payload.message_id = 123456
        payload.emoji = MagicMock()

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch("src.ui.role_panel_view.get_role_panel_item_by_emoji"),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=None,
            ):
                await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_returns_if_panel_is_not_reaction_type(self) -> None:
        """パネルがリアクション式でない場合は何もしない。"""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = MagicMock()
        payload.message_id = 123456
        payload.emoji = MagicMock()

        panel = _make_role_panel(panel_type="button")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch("src.ui.role_panel_view.get_role_panel_item_by_emoji"),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_returns_if_item_not_found(self) -> None:
        """アイテムが見つからない場合は何もしない。"""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = MagicMock()
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_returns_early_on_remove_action(self) -> None:
        """remove アクション時は guild 取得できず早期リターン。"""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = None  # remove 時は member が None
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                # remove action で member が取得できないので早期リターン
                await handle_role_reaction(payload, "remove")

    @pytest.mark.asyncio
    async def test_ignores_bot_member(self) -> None:
        """Bot ユーザーのリアクションは無視する。"""
        member = MagicMock(spec=discord.Member)
        member.bot = True

        guild = MagicMock(spec=discord.Guild)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = member
        payload.member.guild = guild
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                # Bot なので処理されない
                await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_adds_role_on_add_action(self) -> None:
        """add アクションでロールを付与する。"""
        role = MagicMock(spec=discord.Role)

        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.roles = []  # ロールを持っていない
        member.add_roles = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=role)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = member
        payload.member.guild = guild
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                await handle_role_reaction(payload, "add")

        member.add_roles.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_add_if_already_has_role(self) -> None:
        """既にロールを持っている場合は追加しない。"""
        role = MagicMock(spec=discord.Role)

        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.roles = [role]  # 既にロールを持っている
        member.add_roles = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=role)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = member
        payload.member.guild = guild
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                await handle_role_reaction(payload, "add")

        member.add_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_role_not_found(self) -> None:
        """ロールが見つからない場合は何もしない。"""
        member = MagicMock(spec=discord.Member)
        member.bot = False

        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=None)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = member
        payload.member.guild = guild
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                # エラーにならずに処理される
                await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_handles_forbidden_error(self) -> None:
        """権限不足エラーをハンドルする。"""
        role = MagicMock(spec=discord.Role)
        role.name = "Test Role"

        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.roles = []
        member.add_roles = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "no permission")
        )

        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=role)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = member
        payload.member.guild = guild
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                # エラーにならずに処理される
                await handle_role_reaction(payload, "add")

    @pytest.mark.asyncio
    async def test_handles_http_exception(self) -> None:
        """HTTP エラーをハンドルする。"""
        role = MagicMock(spec=discord.Role)
        role.name = "Test Role"

        member = MagicMock(spec=discord.Member)
        member.bot = False
        member.roles = []
        member.add_roles = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "error")
        )

        guild = MagicMock(spec=discord.Guild)
        guild.get_role = MagicMock(return_value=role)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = member
        payload.member.guild = guild
        payload.message_id = 123456
        payload.emoji = "🎮"

        panel = _make_role_panel(panel_type="reaction")
        item = _make_role_panel_item(emoji="🎮", role_id="111")

        with (
            patch("src.ui.role_panel_view.async_session") as mock_session,
            patch(
                "src.ui.role_panel_view.get_role_panel_item_by_emoji",
                new_callable=AsyncMock,
                return_value=item,
            ),
        ):
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock()

            with patch(
                "src.services.db_service.get_role_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=panel,
            ):
                # エラーにならずに処理される
                await handle_role_reaction(payload, "add")


# ===========================================================================
# use_embed Feature Regression Tests
# ===========================================================================


class TestUseEmbedFeature:
    """use_embed 機能のデグレ防止テスト。

    Embed/Text 形式の切り替えが正しく動作することを確認する。
    """

    @pytest.mark.asyncio
    async def test_refresh_panel_uses_embed_when_use_embed_true(self) -> None:
        """use_embed=True の場合、Embed 形式でメッセージを編集する。"""
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock()

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=msg)

        # use_embed=True (Embed モード)
        panel = _make_role_panel(
            panel_type="button",
            message_id="123456",
            use_embed=True,
        )
        items = [_make_role_panel_item(emoji="🎮", label="Test")]

        bot = MagicMock(spec=discord.Client)
        bot.add_view = MagicMock()

        result = await refresh_role_panel(channel, panel, items, bot)

        assert result is True
        msg.edit.assert_called_once()
        # embed が設定され、content が None であることを確認
        call_kwargs = msg.edit.call_args.kwargs
        assert "embed" in call_kwargs
        assert call_kwargs["embed"] is not None
        assert call_kwargs.get("content") is None

    @pytest.mark.asyncio
    async def test_refresh_panel_uses_content_when_use_embed_false(self) -> None:
        """use_embed=False の場合、テキスト形式でメッセージを編集する。"""
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock()

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=msg)

        # use_embed=False (テキストモード)
        panel = _make_role_panel(
            panel_type="button",
            message_id="123456",
            use_embed=False,
            title="Test Panel",
        )
        items = [_make_role_panel_item(emoji="🎮", label="Test")]

        bot = MagicMock(spec=discord.Client)
        bot.add_view = MagicMock()

        result = await refresh_role_panel(channel, panel, items, bot)

        assert result is True
        msg.edit.assert_called_once()
        # content が設定され、embed が None であることを確認
        call_kwargs = msg.edit.call_args.kwargs
        assert "content" in call_kwargs
        assert call_kwargs["content"] is not None
        assert "**Test Panel**" in call_kwargs["content"]
        assert call_kwargs.get("embed") is None

    @pytest.mark.asyncio
    async def test_refresh_reaction_panel_uses_embed_when_use_embed_true(self) -> None:
        """リアクション式パネルでも use_embed=True なら Embed を使う。"""
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock()
        msg.clear_reactions = AsyncMock()
        msg.add_reaction = AsyncMock()

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=msg)

        panel = _make_role_panel(
            panel_type="reaction",
            message_id="123456",
            use_embed=True,
        )
        items = [_make_role_panel_item(emoji="🎮")]

        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, items, bot)

        assert result is True
        call_kwargs = msg.edit.call_args.kwargs
        assert call_kwargs.get("embed") is not None
        assert call_kwargs.get("content") is None

    @pytest.mark.asyncio
    async def test_refresh_reaction_panel_uses_content_when_use_embed_false(
        self,
    ) -> None:
        """リアクション式パネルでも use_embed=False ならテキストを使う。"""
        msg = MagicMock(spec=discord.Message)
        msg.edit = AsyncMock()
        msg.clear_reactions = AsyncMock()
        msg.add_reaction = AsyncMock()

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=msg)

        panel = _make_role_panel(
            panel_type="reaction",
            message_id="123456",
            use_embed=False,
            title="Reaction Panel",
        )
        items = [_make_role_panel_item(emoji="🎮", role_id="111")]

        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, items, bot)

        assert result is True
        call_kwargs = msg.edit.call_args.kwargs
        assert call_kwargs.get("content") is not None
        assert "**Reaction Panel**" in call_kwargs["content"]
        assert "🎮 → <@&111>" in call_kwargs["content"]  # ロール一覧も表示
        assert call_kwargs.get("embed") is None

    @pytest.mark.asyncio
    async def test_create_modal_stores_use_embed_true(self) -> None:
        """RolePanelCreateModal が use_embed=True を保持する。"""
        modal = RolePanelCreateModal(
            panel_type="button",
            channel_id=123456789,
            remove_reaction=False,
            use_embed=True,
        )
        assert modal.use_embed is True

    @pytest.mark.asyncio
    async def test_create_modal_stores_use_embed_false(self) -> None:
        """RolePanelCreateModal が use_embed=False を保持する。"""
        modal = RolePanelCreateModal(
            panel_type="button",
            channel_id=123456789,
            remove_reaction=False,
            use_embed=False,
        )
        assert modal.use_embed is False

    @pytest.mark.asyncio
    async def test_create_modal_default_use_embed_is_true(self) -> None:
        """RolePanelCreateModal のデフォルト use_embed は True。"""
        modal = RolePanelCreateModal(
            panel_type="button",
            channel_id=123456789,
        )
        assert modal.use_embed is True

    def test_embed_format_includes_fields_for_reaction_panel(self) -> None:
        """Embed 形式ではリアクション式パネルにフィールドが含まれる。"""
        panel = _make_role_panel(
            panel_type="reaction",
            title="Reaction Test",
            use_embed=True,
        )
        items = [
            _make_role_panel_item(emoji="🎮", role_id="111"),
            _make_role_panel_item(emoji="🎨", role_id="222"),
        ]
        embed = create_role_panel_embed(panel, items)

        assert len(embed.fields) == 1
        assert embed.fields[0].name == "ロール一覧"

    def test_text_format_includes_role_list_for_reaction_panel(self) -> None:
        """テキスト形式でもリアクション式パネルにロール一覧が含まれる。"""
        panel = _make_role_panel(
            panel_type="reaction",
            title="Reaction Test",
            use_embed=False,
        )
        items = [
            _make_role_panel_item(emoji="🎮", role_id="111"),
            _make_role_panel_item(emoji="🎨", role_id="222"),
        ]
        content = create_role_panel_content(panel, items)

        assert "**ロール一覧**" in content
        assert "🎮 → <@&111>" in content
        assert "🎨 → <@&222>" in content

    def test_embed_and_text_both_show_title(self) -> None:
        """Embed とテキスト両方でタイトルが表示される。"""
        panel = _make_role_panel(title="My Panel Title", use_embed=True)

        embed = create_role_panel_embed(panel, [])
        assert embed.title == "My Panel Title"

        panel_text = _make_role_panel(title="My Panel Title", use_embed=False)
        content = create_role_panel_content(panel_text, [])
        assert "**My Panel Title**" in content

    def test_embed_and_text_both_show_description(self) -> None:
        """Embed とテキスト両方で説明文が表示される。"""
        panel = _make_role_panel(
            title="Test",
            description="This is a description",
            use_embed=True,
        )

        embed = create_role_panel_embed(panel, [])
        assert embed.description == "This is a description"

        panel_text = _make_role_panel(
            title="Test",
            description="This is a description",
            use_embed=False,
        )
        content = create_role_panel_content(panel_text, [])
        assert "This is a description" in content


# ===========================================================================
# Cooldown Feature Tests
# ===========================================================================


class TestCooldownFeature:
    """クールダウン機能のテスト.

    連打対策のクールダウンが正しく動作することを確認する。
    """

    def setup_method(self) -> None:
        """各テスト前にクールダウンキャッシュをクリア."""
        clear_cooldown_cache()

    def test_first_action_not_on_cooldown(self) -> None:
        """最初の操作はクールダウンされない."""
        user_id = 12345
        panel_id = 1

        result = is_on_cooldown(user_id, panel_id)

        assert result is False

    def test_immediate_second_action_on_cooldown(self) -> None:
        """直後の操作はクールダウンされる."""
        user_id = 12345
        panel_id = 1

        # 1回目
        is_on_cooldown(user_id, panel_id)

        # 即座に2回目
        result = is_on_cooldown(user_id, panel_id)

        assert result is True

    def test_different_user_not_affected(self) -> None:
        """異なるユーザーはクールダウンの影響を受けない."""
        user_id_1 = 12345
        user_id_2 = 67890
        panel_id = 1

        # ユーザー1が操作
        is_on_cooldown(user_id_1, panel_id)

        # ユーザー2は影響を受けない
        result = is_on_cooldown(user_id_2, panel_id)

        assert result is False

    def test_different_panel_not_affected(self) -> None:
        """異なるパネルはクールダウンの影響を受けない."""
        user_id = 12345
        panel_id_1 = 1
        panel_id_2 = 2

        # パネル1で操作
        is_on_cooldown(user_id, panel_id_1)

        # パネル2は影響を受けない
        result = is_on_cooldown(user_id, panel_id_2)

        assert result is False

    def test_cooldown_expires(self) -> None:
        """クールダウン時間経過後は再度操作できる."""
        import time
        from unittest.mock import patch

        user_id = 12345
        panel_id = 1

        # 1回目
        is_on_cooldown(user_id, panel_id)

        # time.monotonic をモックしてクールダウン時間経過をシミュレート
        original_time = time.monotonic()
        with patch(
            "src.ui.role_panel_view.time.monotonic",
            return_value=original_time + ROLE_PANEL_COOLDOWN_SECONDS + 0.1,
        ):
            result = is_on_cooldown(user_id, panel_id)

        assert result is False

    def test_clear_cooldown_cache(self) -> None:
        """クールダウンキャッシュをクリアできる."""
        user_id = 12345
        panel_id = 1

        # クールダウンを設定
        is_on_cooldown(user_id, panel_id)
        assert is_on_cooldown(user_id, panel_id) is True

        # キャッシュをクリア
        clear_cooldown_cache()

        # クリア後はクールダウンされない
        assert is_on_cooldown(user_id, panel_id) is False

    def test_cooldown_constant_value(self) -> None:
        """クールダウン時間が適切に設定されている."""
        assert ROLE_PANEL_COOLDOWN_SECONDS == 1.0

    @pytest.mark.asyncio
    async def test_button_callback_rejects_when_on_cooldown(self) -> None:
        """ボタンコールバックはクールダウン中にエラーメッセージを返す."""
        clear_cooldown_cache()

        item = _make_role_panel_item(emoji="🎮", role_id="111")
        button = RoleButton(panel_id=1, item=item)

        # モック interaction
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock()
        interaction.user = MagicMock()
        interaction.user.id = 12345
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        # 1回目のクールダウンを記録
        is_on_cooldown(12345, 1)

        # 2回目の操作 (クールダウン中)
        await button.callback(interaction)

        # エラーメッセージが送信されることを確認
        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "操作が早すぎます" in call_args.args[0]
        assert call_args.kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_reaction_handler_ignores_when_on_cooldown(self) -> None:
        """リアクションハンドラはクールダウン中に処理をスキップする."""
        clear_cooldown_cache()

        # モック payload
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 12345
        payload.message_id = 999
        payload.member = MagicMock()
        payload.member.bot = False
        payload.emoji = MagicMock()

        # 1回目のクールダウンを記録
        is_on_cooldown(12345, 999)

        # 2回目の操作 (クールダウン中)
        # DB クエリが呼ばれないことを確認
        with patch("src.ui.role_panel_view.async_session") as mock_session:
            await handle_role_reaction(payload, "add")
            # セッションが開始されないことを確認 (クールダウンで早期リターン)
            mock_session.assert_not_called()


class TestRoleButtonExcludedRoles:
    """RoleButton の除外ロールチェックのテスト。"""

    @pytest.mark.asyncio
    async def test_button_callback_blocks_excluded_role(self) -> None:
        """除外ロールを持つユーザーはパネルを使用できない。"""
        import json

        clear_cooldown_cache()

        item = _make_role_panel_item(emoji="🎮", role_id="111")
        button = RoleButton(panel_id=1, item=item)

        # 除外ロール "555" を持つメンバー
        excluded_role = MagicMock(spec=discord.Role)
        excluded_role.id = 555

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 12345
        interaction.user.roles = [excluded_role]
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        mock_panel = _make_role_panel(
            panel_id=1,
            excluded_role_ids=json.dumps(["555"]),
        )

        with patch("src.ui.role_panel_view.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.ui.role_panel_view.get_role_panel") as mock_get:
                mock_get.return_value = mock_panel

                await button.callback(interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "あなたのロールではこのパネルを使用できません" in call_args.args[0]
        assert call_args.kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_button_callback_allows_non_excluded_role(self) -> None:
        """除外ロールを持たないユーザーはパネルを使用できる。"""
        import json

        clear_cooldown_cache()

        item = _make_role_panel_item(emoji="🎮", role_id="111")
        button = RoleButton(panel_id=1, item=item)

        # 除外対象ではないロール "999" を持つメンバー
        other_role = MagicMock(spec=discord.Role)
        other_role.id = 999

        target_role = MagicMock(spec=discord.Role)
        target_role.id = 111
        target_role.name = "TestRole"

        bot_role = MagicMock(spec=discord.Role)
        bot_role.id = 888

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.get_role.return_value = target_role
        interaction.guild.me = MagicMock()
        interaction.guild.me.top_role = bot_role
        # target_role < bot_role
        target_role.__ge__ = MagicMock(return_value=False)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 12345
        interaction.user.roles = [other_role]
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        mock_panel = _make_role_panel(
            panel_id=1,
            excluded_role_ids=json.dumps(["555"]),
        )

        with patch("src.ui.role_panel_view.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.ui.role_panel_view.get_role_panel") as mock_get:
                mock_get.return_value = mock_panel

                await button.callback(interaction)

        # ロール付与メッセージが返される (ブロックされない)
        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "あなたのロールではこのパネルを使用できません" not in call_args.args[0]

    @pytest.mark.asyncio
    async def test_button_callback_allows_empty_excluded_list(self) -> None:
        """除外ロールが空の場合は全員使用できる。"""
        clear_cooldown_cache()

        item = _make_role_panel_item(emoji="🎮", role_id="111")
        button = RoleButton(panel_id=1, item=item)

        some_role = MagicMock(spec=discord.Role)
        some_role.id = 999

        target_role = MagicMock(spec=discord.Role)
        target_role.id = 111
        target_role.name = "TestRole"

        bot_role = MagicMock(spec=discord.Role)
        bot_role.id = 888

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.get_role.return_value = target_role
        interaction.guild.me = MagicMock()
        interaction.guild.me.top_role = bot_role
        target_role.__ge__ = MagicMock(return_value=False)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 12345
        interaction.user.roles = [some_role]
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        mock_panel = _make_role_panel(panel_id=1, excluded_role_ids="[]")

        with patch("src.ui.role_panel_view.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.ui.role_panel_view.get_role_panel") as mock_get:
                mock_get.return_value = mock_panel

                await button.callback(interaction)

        # ブロックされない
        call_args = interaction.response.send_message.call_args
        assert "あなたのロールではこのパネルを使用できません" not in call_args.args[0]


class TestRolePanelCleanupGuard:
    """ロールパネルクリーンアップのガード条件テスト。"""

    def test_cleanup_guard_allows_zero_last_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_last_cleanup_time=0 でもクリーンアップが実行される.

        time.monotonic() が小さい環境 (CI等) でも
        0 は「未実行」として扱われクリーンアップがスキップされないことを検証。
        """
        import time

        import src.ui.role_panel_view as rpv_module

        key = (99999, 88888)
        _cooldown_cache[key] = time.monotonic() - 400

        monkeypatch.setattr(rpv_module, "_last_cleanup_time", 0)
        _cleanup_cooldown_cache()

        assert key not in _cooldown_cache
        assert rpv_module._last_cleanup_time > 0

    def test_cleanup_removes_old_entries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """古いエントリがクリーンアップされる."""
        import time

        import src.ui.role_panel_view as rpv_module

        key = (11111, 22222)
        _cooldown_cache[key] = time.monotonic() - 400

        monkeypatch.setattr(rpv_module, "_last_cleanup_time", time.monotonic() - 700)
        _cleanup_cooldown_cache()

        assert key not in _cooldown_cache

    def test_cleanup_preserves_recent_entries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """最近のエントリはクリーンアップされない."""
        import time

        import src.ui.role_panel_view as rpv_module

        key = (33333, 44444)
        _cooldown_cache[key] = time.monotonic() - 10

        monkeypatch.setattr(rpv_module, "_last_cleanup_time", time.monotonic() - 700)
        _cleanup_cooldown_cache()

        assert key in _cooldown_cache

    def test_cleanup_interval_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """クリーンアップ間隔が未経過ならスキップされる."""
        import time

        import src.ui.role_panel_view as rpv_module

        key = (55555, 66666)
        _cooldown_cache[key] = time.monotonic() - 400

        monkeypatch.setattr(rpv_module, "_last_cleanup_time", time.monotonic() - 1)
        _cleanup_cooldown_cache()

        assert key in _cooldown_cache

    def test_cleanup_keeps_active_removes_expired(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """期限切れエントリは削除、アクティブは保持."""
        import time

        import src.ui.role_panel_view as rpv_module

        expired_key = (77777, 88888)
        active_key = (99990, 99991)
        _cooldown_cache[expired_key] = time.monotonic() - 400
        _cooldown_cache[active_key] = time.monotonic()

        monkeypatch.setattr(rpv_module, "_last_cleanup_time", 0)
        _cleanup_cooldown_cache()

        assert expired_key not in _cooldown_cache
        assert active_key in _cooldown_cache


class TestRolePanelCleanupEmptyCache:
    """空キャッシュに対するクリーンアップが安全に動作することを検証。"""

    def test_cleanup_on_empty_cache_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """キャッシュが空でもクリーンアップがクラッシュしない."""
        import src.ui.role_panel_view as rpv_module

        assert len(_cooldown_cache) == 0
        monkeypatch.setattr(rpv_module, "_last_cleanup_time", 0)
        _cleanup_cooldown_cache()
        assert len(_cooldown_cache) == 0
        assert rpv_module._last_cleanup_time > 0

    def test_is_cooldown_on_empty_cache_returns_false(self) -> None:
        """空キャッシュで is_on_cooldown が False を返す."""
        assert len(_cooldown_cache) == 0
        result = is_on_cooldown(99999, 88888)
        assert result is False


class TestRolePanelCleanupAllExpired:
    """全エントリが期限切れの場合にキャッシュが空になることを検証。"""

    def test_all_expired_entries_removed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """全エントリが期限切れなら全て削除されキャッシュが空になる."""
        import time

        import src.ui.role_panel_view as rpv_module

        now = time.monotonic()
        _cooldown_cache[(1, 10)] = now - 400
        _cooldown_cache[(2, 20)] = now - 500
        _cooldown_cache[(3, 30)] = now - 600

        monkeypatch.setattr(rpv_module, "_last_cleanup_time", 0)
        _cleanup_cooldown_cache()

        assert len(_cooldown_cache) == 0


class TestRolePanelCleanupTriggerViaPublicAPI:
    """公開 API 関数がクリーンアップを内部的にトリガーすることを検証。"""

    def test_is_cooldown_triggers_cleanup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """is_on_cooldown がクリーンアップをトリガーする."""
        import time

        import src.ui.role_panel_view as rpv_module

        old_key = (11111, 22222)
        _cooldown_cache[old_key] = time.monotonic() - 400

        monkeypatch.setattr(rpv_module, "_last_cleanup_time", 0)
        is_on_cooldown(99999, 88888)

        assert old_key not in _cooldown_cache

    def test_cleanup_updates_last_cleanup_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """クリーンアップ実行後に _last_cleanup_time が更新される."""
        import src.ui.role_panel_view as rpv_module

        monkeypatch.setattr(rpv_module, "_last_cleanup_time", 0)
        is_on_cooldown(99999, 88888)

        assert rpv_module._last_cleanup_time > 0
