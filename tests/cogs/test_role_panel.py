"""Tests for role panel cog and related functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import DiscordRole, RolePanel, RolePanelItem

# =============================================================================
# Database Model Tests
# =============================================================================


class TestRolePanelModel:
    """RolePanel モデルのテスト。"""

    def test_role_panel_repr(self) -> None:
        """__repr__ が正しくフォーマットされる。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        assert "RolePanel" in repr(panel)
        assert "id=1" in repr(panel)
        assert "title=Test Panel" in repr(panel)

    def test_role_panel_use_embed_field_exists(self) -> None:
        """use_embed フィールドが存在し、値を設定できる。"""
        # use_embed を明示的に設定して動作を確認
        # DB デフォルト値は tests/services/test_db_service.py でテスト済み
        panel = RolePanel(
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
            use_embed=True,
        )
        assert panel.use_embed is True

    def test_role_panel_use_embed_false(self) -> None:
        """use_embed=False を設定できる。"""
        panel = RolePanel(
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Text Panel",
            use_embed=False,
        )
        assert panel.use_embed is False

    def test_role_panel_use_embed_true(self) -> None:
        """use_embed=True を設定できる。"""
        panel = RolePanel(
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Embed Panel",
            use_embed=True,
        )
        assert panel.use_embed is True


class TestRolePanelItemModel:
    """RolePanelItem モデルのテスト。"""

    def test_role_panel_item_repr(self) -> None:
        """__repr__ が正しくフォーマットされる。"""
        item = RolePanelItem(
            id=1,
            panel_id=1,
            role_id="789",
            emoji="🎮",
        )
        assert "RolePanelItem" in repr(item)
        assert "id=1" in repr(item)
        assert "emoji=🎮" in repr(item)


class TestDiscordRoleModel:
    """DiscordRole モデルのテスト。"""

    def test_discord_role_repr(self) -> None:
        """__repr__ が正しくフォーマットされる。"""
        role = DiscordRole(
            id=1,
            guild_id="123456789",
            role_id="987654321",
            role_name="Gamer",
            color=0xFF0000,
            position=5,
        )
        assert "DiscordRole" in repr(role)
        assert "id=1" in repr(role)
        assert "guild_id=123456789" in repr(role)
        assert "role_id=987654321" in repr(role)
        assert "name=Gamer" in repr(role)

    def test_discord_role_accepts_optional_fields(self) -> None:
        """オプションフィールドなしでもインスタンス化できる。"""
        # color と position を省略してインスタンス化
        role = DiscordRole(
            guild_id="123",
            role_id="456",
            role_name="Test",
        )
        # インスタンス化できることを確認
        # (デフォルト値は DB 挿入時に適用される)
        assert role.guild_id == "123"
        assert role.role_id == "456"
        assert role.role_name == "Test"


# =============================================================================
# CRUD Function Tests
# =============================================================================


class TestRolePanelCRUD:
    """RolePanel CRUD 関数のテスト。"""

    @pytest.fixture
    def db_session(self) -> AsyncMock:
        """Mock database session."""
        return AsyncMock(spec=AsyncSession)

    async def test_create_role_panel(self, db_session: AsyncMock) -> None:
        """create_role_panel がパネルを作成する。"""
        from src.services.db_service import create_role_panel

        db_session.commit = AsyncMock()
        db_session.refresh = AsyncMock()
        db_session.add = MagicMock()

        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test",
        )

        db_session.add.assert_called_once()
        db_session.commit.assert_awaited_once()
        assert panel.guild_id == "123"
        assert panel.title == "Test"

    async def test_get_role_panel(self, db_session: AsyncMock) -> None:
        """get_role_panel がパネルを取得する。"""
        from src.services.db_service import get_role_panel

        mock_panel = RolePanel(
            id=1, guild_id="123", channel_id="456", panel_type="button", title="Test"
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_panel
        db_session.execute = AsyncMock(return_value=mock_result)

        panel = await get_role_panel(db_session, 1)

        assert panel is not None
        assert panel.id == 1

    async def test_get_role_panel_not_found(self, db_session: AsyncMock) -> None:
        """get_role_panel がパネルが見つからない場合 None を返す。"""
        from src.services.db_service import get_role_panel

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        panel = await get_role_panel(db_session, 999)

        assert panel is None

    async def test_get_role_panel_by_message_id(self, db_session: AsyncMock) -> None:
        """get_role_panel_by_message_id がメッセージ ID からパネルを取得する。"""
        from src.services.db_service import get_role_panel_by_message_id

        mock_panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            message_id="789",
            panel_type="reaction",
            title="Test",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_panel
        db_session.execute = AsyncMock(return_value=mock_result)

        panel = await get_role_panel_by_message_id(db_session, "789")

        assert panel is not None
        assert panel.message_id == "789"

    async def test_get_role_panels_by_guild(self, db_session: AsyncMock) -> None:
        """get_role_panels_by_guild がサーバー内の全パネルを取得する。"""
        from src.services.db_service import get_role_panels_by_guild

        mock_panels = [
            RolePanel(
                id=1,
                guild_id="123",
                channel_id="456",
                panel_type="button",
                title="Test1",
            ),
            RolePanel(
                id=2,
                guild_id="123",
                channel_id="789",
                panel_type="reaction",
                title="Test2",
            ),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_panels
        db_session.execute = AsyncMock(return_value=mock_result)

        panels = await get_role_panels_by_guild(db_session, "123")

        assert len(panels) == 2

    async def test_delete_role_panel(self, db_session: AsyncMock) -> None:
        """delete_role_panel がパネルを削除する。"""
        from src.services.db_service import delete_role_panel

        mock_panel = RolePanel(
            id=1, guild_id="123", channel_id="456", panel_type="button", title="Test"
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_panel
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.delete = AsyncMock()
        db_session.commit = AsyncMock()

        result = await delete_role_panel(db_session, 1)

        assert result is True
        db_session.delete.assert_awaited_once_with(mock_panel)
        db_session.commit.assert_awaited_once()

    async def test_delete_role_panel_not_found(self, db_session: AsyncMock) -> None:
        """delete_role_panel がパネルが見つからない場合 False を返す。"""
        from src.services.db_service import delete_role_panel

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        result = await delete_role_panel(db_session, 999)

        assert result is False


class TestRolePanelItemCRUD:
    """RolePanelItem CRUD 関数のテスト。"""

    @pytest.fixture
    def db_session(self) -> AsyncMock:
        """Mock database session."""
        return AsyncMock(spec=AsyncSession)

    async def test_add_role_panel_item(self, db_session: AsyncMock) -> None:
        """add_role_panel_item がアイテムを追加する。"""
        from src.services.db_service import add_role_panel_item

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.add = MagicMock()
        db_session.commit = AsyncMock()
        db_session.refresh = AsyncMock()

        item = await add_role_panel_item(
            db_session,
            panel_id=1,
            role_id="123",
            emoji="🎮",
            label="Gamer",
        )

        db_session.add.assert_called_once()
        assert item.emoji == "🎮"

    async def test_get_role_panel_items(self, db_session: AsyncMock) -> None:
        """get_role_panel_items がアイテムを取得する。"""
        from src.services.db_service import get_role_panel_items

        mock_items = [
            RolePanelItem(id=1, panel_id=1, role_id="123", emoji="🎮", position=0),
            RolePanelItem(id=2, panel_id=1, role_id="456", emoji="🎨", position=1),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_items
        db_session.execute = AsyncMock(return_value=mock_result)

        items = await get_role_panel_items(db_session, 1)

        assert len(items) == 2

    async def test_remove_role_panel_item(self, db_session: AsyncMock) -> None:
        """remove_role_panel_item がアイテムを削除する。"""
        from src.services.db_service import remove_role_panel_item

        mock_item = RolePanelItem(
            id=1, panel_id=1, role_id="123", emoji="🎮", position=0
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_item
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.delete = AsyncMock()
        db_session.commit = AsyncMock()

        result = await remove_role_panel_item(db_session, 1, "🎮")

        assert result is True
        db_session.delete.assert_awaited_once_with(mock_item)


# =============================================================================
# UI Component Tests
# =============================================================================


class TestRolePanelEmbed:
    """create_role_panel_embed のテスト。"""

    def test_create_embed_button_type(self) -> None:
        """ボタン式パネルの Embed が正しく作成される。"""
        from src.ui.role_panel_view import create_role_panel_embed

        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
            description="Test Description",
            color=0x00FF00,
        )
        items: list[RolePanelItem] = []

        embed = create_role_panel_embed(panel, items)

        assert embed.title == "Test Panel"
        assert embed.description == "Test Description"
        assert embed.color is not None
        assert embed.color.value == 0x00FF00

    def test_create_embed_reaction_type(self) -> None:
        """リアクション式パネルの Embed にロール一覧が含まれる。"""
        from src.ui.role_panel_view import create_role_panel_embed

        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Test Panel",
        )
        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮", position=0),
            RolePanelItem(id=2, panel_id=1, role_id="222", emoji="🎨", position=1),
        ]

        embed = create_role_panel_embed(panel, items)

        assert len(embed.fields) == 1
        assert embed.fields[0].name == "ロール一覧"
        assert "🎮" in embed.fields[0].value
        assert "🎨" in embed.fields[0].value


class TestRoleButton:
    """RoleButton のテスト。"""

    async def test_button_initialization(self) -> None:
        """ボタンが正しく初期化される。"""
        from src.ui.role_panel_view import RoleButton

        item = RolePanelItem(
            id=1,
            panel_id=1,
            role_id="123",
            emoji="🎮",
            label="Gamer",
            style="primary",
            position=0,
        )

        button = RoleButton(panel_id=1, item=item)

        assert button.label == "Gamer"
        assert button.custom_id == "role_panel:1:1"
        assert button.style == discord.ButtonStyle.primary


class TestRolePanelView:
    """RolePanelView のテスト。"""

    async def test_view_initialization(self) -> None:
        """View が正しく初期化される。"""
        from src.ui.role_panel_view import RolePanelView

        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮", position=0),
            RolePanelItem(id=2, panel_id=1, role_id="222", emoji="🎨", position=1),
        ]

        view = RolePanelView(panel_id=1, items=items)

        assert view.timeout is None  # 永続
        assert len(view.children) == 2

    async def test_view_max_items_limit(self) -> None:
        """25 個以上のアイテムは切り捨てられる。"""
        from src.ui.role_panel_view import RolePanelView

        items = [
            RolePanelItem(id=i, panel_id=1, role_id=str(i), emoji="🔢", position=i)
            for i in range(30)
        ]

        view = RolePanelView(panel_id=1, items=items)

        assert len(view.children) == 25


# =============================================================================
# Cog Tests
# =============================================================================


class TestRolePanelCog:
    """RolePanelCog のテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        bot = MagicMock(spec=commands.Bot)
        bot.add_view = MagicMock()
        return bot

    async def test_cog_load_registers_views(self, mock_bot: MagicMock) -> None:
        """cog_load が永続 View を登録する。"""
        from src.cogs.role_panel import RolePanelCog

        mock_panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test",
            message_id="999",
        )
        mock_items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮", position=0),
        ]

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.get_all_role_panels") as mock_get_panels:
                mock_get_panels.return_value = [mock_panel]

                with patch(
                    "src.cogs.role_panel.get_role_panel_items"
                ) as mock_get_items:
                    mock_get_items.return_value = mock_items

                    cog = RolePanelCog(mock_bot)
                    cog._sync_views_task.start = MagicMock()
                    await cog.cog_load()

        mock_bot.add_view.assert_called()

    async def test_cog_load_starts_sync_task(self, mock_bot: MagicMock) -> None:
        """cog_load が定期同期タスクを開始する。"""
        from src.cogs.role_panel import RolePanelCog

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.get_all_role_panels") as mock_get_panels:
                mock_get_panels.return_value = []

                cog = RolePanelCog(mock_bot)
                cog._sync_views_task.start = MagicMock()
                await cog.cog_load()

        cog._sync_views_task.start.assert_called_once()

    async def test_cog_unload_cancels_sync_task(self, mock_bot: MagicMock) -> None:
        """cog_unload が定期同期タスクを停止する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        cog._sync_views_task.cancel = MagicMock()
        await cog.cog_unload()

        cog._sync_views_task.cancel.assert_called_once()

    async def test_cog_load_skips_reaction_panels(self, mock_bot: MagicMock) -> None:
        """cog_load がリアクション式パネルをスキップする。"""
        from src.cogs.role_panel import RolePanelCog

        mock_panel = RolePanel(
            id=1, guild_id="123", channel_id="456", panel_type="reaction", title="Test"
        )

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.get_all_role_panels") as mock_get_panels:
                mock_get_panels.return_value = [mock_panel]

                cog = RolePanelCog(mock_bot)
                cog._sync_views_task.start = MagicMock()
                await cog.cog_load()

        # リアクション式は add_view が呼ばれない
        mock_bot.add_view.assert_not_called()

    async def test_sync_views_task_calls_register(self, mock_bot: MagicMock) -> None:
        """_sync_views_task が _register_all_views を呼ぶ。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        with patch.object(
            cog, "_register_all_views", new_callable=AsyncMock
        ) as mock_register:
            await cog._sync_views_task()
            mock_register.assert_called_once()

    async def test_sync_views_task_handles_error(self, mock_bot: MagicMock) -> None:
        """_sync_views_task が例外発生時にクラッシュしない。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        with patch.object(
            cog, "_register_all_views", side_effect=Exception("DB error")
        ):
            # 例外が飛ばずに正常終了する
            await cog._sync_views_task()

    async def test_register_views_mixed_panels(self, mock_bot: MagicMock) -> None:
        """ボタン式とリアクション式が混在する場合、ボタン式のみ登録される。"""
        from src.cogs.role_panel import RolePanelCog

        button_panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="B",
            message_id="999",
        )
        reaction_panel = RolePanel(
            id=2,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="R",
            message_id="888",
        )
        mock_items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮", position=0),
        ]

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.get_all_role_panels") as mock_get_panels:
                mock_get_panels.return_value = [button_panel, reaction_panel]

                with patch(
                    "src.cogs.role_panel.get_role_panel_items"
                ) as mock_get_items:
                    mock_get_items.return_value = mock_items

                    cog = RolePanelCog(mock_bot)
                    await cog._register_all_views()

        # ボタン式の1パネルのみ add_view される
        assert mock_bot.add_view.call_count == 1
        # get_role_panel_items はボタン式の1パネル分のみ呼ばれる
        mock_get_items.assert_called_once_with(mock_db, 1)

    async def test_register_views_multiple_button_panels(
        self, mock_bot: MagicMock
    ) -> None:
        """複数のボタン式パネルが全て登録される。"""
        from src.cogs.role_panel import RolePanelCog

        panels = [
            RolePanel(
                id=i,
                guild_id="123",
                channel_id="456",
                panel_type="button",
                title=f"P{i}",
                message_id=str(900 + i),
            )
            for i in range(1, 4)
        ]

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.get_all_role_panels") as mock_get_panels:
                mock_get_panels.return_value = panels

                with patch(
                    "src.cogs.role_panel.get_role_panel_items"
                ) as mock_get_items:
                    mock_get_items.return_value = []

                    cog = RolePanelCog(mock_bot)
                    await cog._register_all_views()

        # 3 パネル全て add_view される
        assert mock_bot.add_view.call_count == 3


class TestSetupFunction:
    """setup 関数のテスト。"""

    async def test_setup_adds_cog(self) -> None:
        """setup が Cog を追加する。"""
        from src.cogs.role_panel import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()

        await setup(bot)

        bot.add_cog.assert_awaited_once()


class TestCogLoad:
    """cog_load のエラーハンドリングテスト。"""

    async def test_cog_load_does_not_raise_on_db_error(self) -> None:
        """DB エラーでも cog_load が例外を出さずに完了する."""
        from src.cogs.role_panel import RolePanelCog

        bot = MagicMock(spec=commands.Bot)
        cog = RolePanelCog(bot)

        # _register_all_views が例外を投げても cog_load は失敗しない
        with patch.object(
            cog, "_register_all_views", side_effect=Exception("DB error")
        ):
            cog._sync_views_task = MagicMock()
            await cog.cog_load()

        # _sync_views_task は開始される
        cog._sync_views_task.start.assert_called_once()


# =============================================================================
# Remove Reaction Feature Tests
# =============================================================================


class TestRemoveReactionFeature:
    """リアクション自動削除機能のテスト。"""

    def test_role_panel_with_remove_reaction_false(self) -> None:
        """RolePanel を remove_reaction=False で作成できる。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Test",
            remove_reaction=False,
        )
        assert panel.remove_reaction is False

    def test_role_panel_with_remove_reaction_true(self) -> None:
        """RolePanel を remove_reaction=True で作成できる。"""
        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Test",
            remove_reaction=True,
        )
        assert panel.remove_reaction is True

    @pytest.fixture
    def db_session(self) -> AsyncMock:
        """Mock database session."""
        return AsyncMock(spec=AsyncSession)

    async def test_create_role_panel_with_remove_reaction(
        self, db_session: AsyncMock
    ) -> None:
        """create_role_panel が remove_reaction を設定できる。"""
        from src.services.db_service import create_role_panel

        db_session.commit = AsyncMock()
        db_session.refresh = AsyncMock()
        db_session.add = MagicMock()

        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Test",
            remove_reaction=True,
        )

        assert panel.remove_reaction is True

    async def test_modal_initialization_with_remove_reaction(self) -> None:
        """RolePanelCreateModal が remove_reaction を受け取れる。"""
        from src.ui.role_panel_view import RolePanelCreateModal

        modal = RolePanelCreateModal("reaction", 123, remove_reaction=True)

        assert modal.panel_type == "reaction"
        assert modal.channel_id == 123
        assert modal.remove_reaction is True

    async def test_modal_initialization_default_remove_reaction(self) -> None:
        """RolePanelCreateModal のデフォルト remove_reaction は False。"""
        from src.ui.role_panel_view import RolePanelCreateModal

        modal = RolePanelCreateModal("reaction", 123)

        assert modal.remove_reaction is False


# =============================================================================
# Command Handler Tests
# =============================================================================


class TestCreateCommand:
    """create コマンドのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        bot = MagicMock(spec=commands.Bot)
        bot.add_view = MagicMock()
        return bot

    async def test_create_non_text_channel_error(self, mock_bot: MagicMock) -> None:
        """テキストチャンネル以外でエラーを返す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.VoiceChannel)
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await cog.create.callback(cog, interaction, "button", None, False)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "テキストチャンネル" in call_args.args[0]
        assert call_args.kwargs.get("ephemeral") is True

    async def test_create_sends_modal(self, mock_bot: MagicMock) -> None:
        """create コマンドがモーダルを送信する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123
        interaction.channel = mock_channel
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await cog.create.callback(cog, interaction, "button", None, False)

        interaction.response.send_modal.assert_awaited_once()


class TestAddCommand:
    """add コマンドのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        bot = MagicMock(spec=commands.Bot)
        return bot

    async def test_add_no_channel_error(self, mock_bot: MagicMock) -> None:
        """チャンネルがない場合エラーを返す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = None
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        await cog.add.callback(cog, interaction, mock_role, "🎮", None, "secondary")

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "チャンネルが見つかりません" in call_args.args[0]

    async def test_add_no_panel_error(self, mock_bot: MagicMock) -> None:
        """パネルがない場合エラーを返す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panels_by_channel"
            ) as mock_get_panels:
                mock_get_panels.return_value = []

                await cog.add.callback(
                    cog, interaction, mock_role, "🎮", None, "secondary"
                )

        interaction.followup.send.assert_awaited_once()
        call_args = interaction.followup.send.call_args
        assert "ロールパネルがありません" in call_args.args[0]

    async def test_add_duplicate_emoji_error(self, mock_bot: MagicMock) -> None:
        """同じ絵文字が既に使われている場合エラーを返す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)
        mock_panel = RolePanel(
            id=1, guild_id="123", channel_id="123", panel_type="button", title="Test"
        )

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panels_by_channel"
            ) as mock_get_panels:
                mock_get_panels.return_value = [mock_panel]

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = RolePanelItem(
                        id=1, panel_id=1, role_id="111", emoji="🎮", position=0
                    )

                    await cog.add.callback(
                        cog, interaction, mock_role, "🎮", None, "secondary"
                    )

        interaction.followup.send.assert_awaited_once()
        call_args = interaction.followup.send.call_args
        assert "既に使用されています" in call_args.args[0]

    async def test_add_invalid_emoji_error(self, mock_bot: MagicMock) -> None:
        """無効な絵文字の場合エラーを返す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        # 無効な絵文字 (通常のテキスト) でコマンドを呼び出す
        await cog.add.callback(
            cog, interaction, mock_role, "invalid", None, "secondary"
        )

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "無効な絵文字" in call_args.args[0]
        assert call_args.kwargs.get("ephemeral") is True

    async def test_add_whitespace_emoji_error(self, mock_bot: MagicMock) -> None:
        """空白のみの絵文字は無効。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        await cog.add.callback(cog, interaction, mock_role, "   ", None, "secondary")

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "無効な絵文字" in call_args.args[0]

    async def test_add_zwj_emoji_valid(self, mock_bot: MagicMock) -> None:
        """ZWJ 絵文字 (🧑‍💻等) は有効。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.guild = MagicMock()
        interaction.guild.get_channel.return_value = None

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 111
        mock_role.mention = "@Test"
        mock_panel = RolePanel(
            id=1, guild_id="123", channel_id="123", panel_type="button", title="Test"
        )

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panels_by_channel"
            ) as mock_get_panels:
                mock_get_panels.return_value = [mock_panel]

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = None  # 絵文字は未使用

                    with (
                        patch(
                            "src.cogs.role_panel.add_role_panel_item"
                        ) as mock_add_item,
                        patch(
                            "src.cogs.role_panel.get_role_panel_items"
                        ) as mock_get_items,
                    ):
                        mock_get_items.return_value = []

                        # ZWJ 絵文字でコマンドを呼び出す
                        await cog.add.callback(
                            cog, interaction, mock_role, "🧑‍💻", None, "secondary"
                        )

                    # add_role_panel_item が呼び出されたことを確認
                    mock_add_item.assert_awaited_once()

        # エラーメッセージではなく成功メッセージ
        call_args = interaction.followup.send.call_args
        assert "追加しました" in call_args.args[0]

    async def test_add_keycap_emoji_valid(self, mock_bot: MagicMock) -> None:
        """Keycap 絵文字 (1️⃣等) は有効。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.guild = MagicMock()
        interaction.guild.get_channel.return_value = None

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 111
        mock_role.mention = "@Test"
        mock_panel = RolePanel(
            id=1, guild_id="123", channel_id="123", panel_type="button", title="Test"
        )

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panels_by_channel"
            ) as mock_get_panels:
                mock_get_panels.return_value = [mock_panel]

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = None

                    with (
                        patch(
                            "src.cogs.role_panel.add_role_panel_item"
                        ) as mock_add_item,
                        patch(
                            "src.cogs.role_panel.get_role_panel_items"
                        ) as mock_get_items,
                    ):
                        mock_get_items.return_value = []

                        # Keycap 絵文字でコマンドを呼び出す
                        await cog.add.callback(
                            cog, interaction, mock_role, "1️⃣", None, "secondary"
                        )

                    mock_add_item.assert_awaited_once()

        call_args = interaction.followup.send.call_args
        assert "追加しました" in call_args.args[0]

    async def test_add_integrity_error_race_condition(
        self, mock_bot: MagicMock
    ) -> None:
        """IntegrityError (レースコンディション) で適切なエラーを返す。"""
        from sqlalchemy.exc import IntegrityError

        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 111
        mock_panel = RolePanel(
            id=1, guild_id="123", channel_id="123", panel_type="button", title="Test"
        )

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panels_by_channel"
            ) as mock_get_panels:
                mock_get_panels.return_value = [mock_panel]

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = None  # チェック時は未使用

                    with patch(
                        "src.cogs.role_panel.add_role_panel_item"
                    ) as mock_add_item:
                        # add_role_panel_item が IntegrityError をスロー
                        mock_add_item.side_effect = IntegrityError(
                            statement="INSERT",
                            params={},
                            orig=Exception("duplicate key"),
                        )

                        await cog.add.callback(
                            cog, interaction, mock_role, "🎮", None, "secondary"
                        )

        interaction.followup.send.assert_awaited_once()
        call_args = interaction.followup.send.call_args
        assert "既に使用されています" in call_args.args[0]
        assert call_args.kwargs.get("ephemeral") is True


class TestRemoveCommand:
    """remove コマンドのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        return MagicMock(spec=commands.Bot)

    async def test_remove_no_channel_error(self, mock_bot: MagicMock) -> None:
        """チャンネルがない場合エラーを返す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = None
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await cog.remove.callback(cog, interaction, "🎮")

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "チャンネルが見つかりません" in call_args.args[0]

    async def test_remove_no_panel_error(self, mock_bot: MagicMock) -> None:
        """パネルがない場合エラーを返す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panels_by_channel"
            ) as mock_get_panels:
                mock_get_panels.return_value = []

                await cog.remove.callback(cog, interaction, "🎮")

        interaction.followup.send.assert_awaited_once()
        call_args = interaction.followup.send.call_args
        assert "ロールパネルがありません" in call_args.args[0]

    async def test_remove_emoji_not_found_error(self, mock_bot: MagicMock) -> None:
        """絵文字が見つからない場合エラーを返す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_panel = RolePanel(
            id=1, guild_id="123", channel_id="123", panel_type="button", title="Test"
        )

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panels_by_channel"
            ) as mock_get_panels:
                mock_get_panels.return_value = [mock_panel]

                with patch("src.cogs.role_panel.remove_role_panel_item") as mock_remove:
                    mock_remove.return_value = False

                    await cog.remove.callback(cog, interaction, "🎮")

        interaction.followup.send.assert_awaited_once()
        call_args = interaction.followup.send.call_args
        assert "見つかりません" in call_args.args[0]


class TestDeleteCommand:
    """delete コマンドのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        return MagicMock(spec=commands.Bot)

    async def test_delete_no_channel_error(self, mock_bot: MagicMock) -> None:
        """チャンネルがない場合エラーを返す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = None
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await cog.delete.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "チャンネルが見つかりません" in call_args.args[0]

    async def test_delete_no_panel_error(self, mock_bot: MagicMock) -> None:
        """パネルがない場合エラーを返す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panels_by_channel"
            ) as mock_get_panels:
                mock_get_panels.return_value = []

                await cog.delete.callback(cog, interaction)

        interaction.followup.send.assert_awaited_once()
        call_args = interaction.followup.send.call_args
        assert "ロールパネルがありません" in call_args.args[0]


class TestListCommand:
    """list コマンドのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        return MagicMock(spec=commands.Bot)

    async def test_list_no_guild_error(self, mock_bot: MagicMock) -> None:
        """ギルド外で実行した場合エラーを返す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await cog.list_panels.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ使用できます" in call_args.args[0]

    async def test_list_no_panels_message(self, mock_bot: MagicMock) -> None:
        """パネルがない場合のメッセージを表示する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.services.db_service.get_role_panels_by_guild"
            ) as mock_get_panels:
                mock_get_panels.return_value = []

                await cog.list_panels.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "ロールパネルはありません" in call_args.args[0]


# =============================================================================
# Reaction Handler Tests
# =============================================================================


class TestHandleReaction:
    """リアクションハンドラのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        bot = MagicMock(spec=commands.Bot)
        bot.user = MagicMock()
        bot.user.id = 999  # Bot の ID
        return bot

    async def test_ignore_bot_reaction(self, mock_bot: MagicMock) -> None:
        """Bot 自身のリアクションは無視する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 999  # Bot の ID と同じ

        # _handle_reaction は何もせず終了するはず
        await cog._handle_reaction(payload, "add")

    async def test_ignore_non_panel_message(self, mock_bot: MagicMock) -> None:
        """パネル以外のメッセージは無視する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123  # 別のユーザー
        payload.message_id = 456

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = None

                await cog._handle_reaction(payload, "add")

    async def test_ignore_button_panel_reaction(self, mock_bot: MagicMock) -> None:
        """ボタン式パネルのリアクションは無視する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456

        mock_panel = RolePanel(
            id=1, guild_id="123", channel_id="456", panel_type="button", title="Test"
        )

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                await cog._handle_reaction(payload, "add")

    async def test_ignore_unknown_emoji(self, mock_bot: MagicMock) -> None:
        """パネルに設定されていない絵文字は無視する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="❓")

        mock_panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Test",
            remove_reaction=False,
        )

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = None

                    await cog._handle_reaction(payload, "add")


# =============================================================================
# RoleButton Callback Tests
# =============================================================================


class TestRoleButtonCallback:
    """RoleButton.callback のテスト。"""

    async def test_callback_no_guild_error(self) -> None:
        """ギルド外でエラーを返す。"""
        from src.ui.role_panel_view import RoleButton

        item = RolePanelItem(
            id=1, panel_id=1, role_id="123", emoji="🎮", position=0, style="primary"
        )
        button = RoleButton(panel_id=1, item=item)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ使用できます" in call_args.args[0]

    async def test_callback_non_member_error(self) -> None:
        """メンバーでないユーザーでエラーを返す。"""
        from src.ui.role_panel_view import RoleButton

        item = RolePanelItem(
            id=1, panel_id=1, role_id="123", emoji="🎮", position=0, style="primary"
        )
        button = RoleButton(panel_id=1, item=item)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.user = MagicMock(spec=discord.User)  # Member ではない
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "メンバー情報を取得できませんでした" in call_args.args[0]

    async def test_callback_role_not_found_error(self) -> None:
        """ロールが見つからない場合エラーを返す。"""
        from src.ui.role_panel_view import RoleButton

        item = RolePanelItem(
            id=1, panel_id=1, role_id="999", emoji="🎮", position=0, style="primary"
        )
        button = RoleButton(panel_id=1, item=item)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.get_role.return_value = None
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "ロールが見つかりませんでした" in call_args.args[0]

    async def test_callback_role_too_high_error(self) -> None:
        """Bot のロールより上のロールはエラーを返す。"""
        from src.ui.role_panel_view import RoleButton

        item = RolePanelItem(
            id=1, panel_id=1, role_id="123", emoji="🎮", position=0, style="primary"
        )
        button = RoleButton(panel_id=1, item=item)

        mock_role = MagicMock(spec=discord.Role)
        mock_role.position = 10

        mock_bot_top_role = MagicMock(spec=discord.Role)
        mock_bot_top_role.position = 5

        # Role の比較を設定
        mock_role.__ge__ = MagicMock(return_value=True)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.get_role.return_value = mock_role
        interaction.guild.me = MagicMock(spec=discord.Member)
        interaction.guild.me.top_role = mock_bot_top_role
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "Bot の権限ではこのロールを付与できません" in call_args.args[0]

    async def test_callback_add_role_success(self) -> None:
        """ロール付与が成功する。"""
        from src.ui.role_panel_view import RoleButton

        item = RolePanelItem(
            id=1, panel_id=1, role_id="123", emoji="🎮", position=0, style="primary"
        )
        button = RoleButton(panel_id=1, item=item)

        mock_role = MagicMock(spec=discord.Role)
        mock_role.position = 5
        mock_role.mention = "@Gamer"

        mock_bot_top_role = MagicMock(spec=discord.Role)
        mock_bot_top_role.position = 10

        # Role の比較を設定
        mock_role.__ge__ = MagicMock(return_value=False)

        mock_member = MagicMock(spec=discord.Member)
        mock_member.roles = []  # ロールを持っていない
        mock_member.add_roles = AsyncMock()

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.get_role.return_value = mock_role
        interaction.guild.me = MagicMock(spec=discord.Member)
        interaction.guild.me.top_role = mock_bot_top_role
        interaction.user = mock_member
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await button.callback(interaction)

        mock_member.add_roles.assert_awaited_once_with(
            mock_role, reason="ロールパネルから付与"
        )
        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "付与しました" in call_args.args[0]

    async def test_callback_remove_role_success(self) -> None:
        """ロール解除が成功する。"""
        from src.ui.role_panel_view import RoleButton

        item = RolePanelItem(
            id=1, panel_id=1, role_id="123", emoji="🎮", position=0, style="primary"
        )
        button = RoleButton(panel_id=1, item=item)

        mock_role = MagicMock(spec=discord.Role)
        mock_role.position = 5
        mock_role.mention = "@Gamer"

        mock_bot_top_role = MagicMock(spec=discord.Role)
        mock_bot_top_role.position = 10

        # Role の比較を設定
        mock_role.__ge__ = MagicMock(return_value=False)

        mock_member = MagicMock(spec=discord.Member)
        mock_member.roles = [mock_role]  # ロールを持っている
        mock_member.remove_roles = AsyncMock()

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.get_role.return_value = mock_role
        interaction.guild.me = MagicMock(spec=discord.Member)
        interaction.guild.me.top_role = mock_bot_top_role
        interaction.user = mock_member
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await button.callback(interaction)

        mock_member.remove_roles.assert_awaited_once_with(
            mock_role, reason="ロールパネルから解除"
        )
        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "解除しました" in call_args.args[0]

    async def test_callback_forbidden_error(self) -> None:
        """権限不足でエラーを返す。"""
        from src.ui.role_panel_view import RoleButton

        item = RolePanelItem(
            id=1, panel_id=1, role_id="123", emoji="🎮", position=0, style="primary"
        )
        button = RoleButton(panel_id=1, item=item)

        mock_role = MagicMock(spec=discord.Role)
        mock_role.position = 5

        mock_bot_top_role = MagicMock(spec=discord.Role)
        mock_bot_top_role.position = 10

        mock_role.__ge__ = MagicMock(return_value=False)

        # Forbidden 例外用のモック response を作成
        mock_response = MagicMock()
        mock_response.status = 403

        mock_member = MagicMock(spec=discord.Member)
        mock_member.roles = []
        mock_member.add_roles = AsyncMock(
            side_effect=discord.Forbidden(mock_response, "No permission")
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.get_role.return_value = mock_role
        interaction.guild.me = MagicMock(spec=discord.Member)
        interaction.guild.me.top_role = mock_bot_top_role
        interaction.user = mock_member
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "権限不足" in call_args.args[0]


# =============================================================================
# refresh_role_panel Tests
# =============================================================================


class TestRefreshRolePanel:
    """refresh_role_panel のテスト。"""

    async def test_no_message_id_returns_false(self) -> None:
        """message_id がない場合 False を返す。"""
        from src.ui.role_panel_view import refresh_role_panel

        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test",
            message_id=None,
        )
        channel = MagicMock(spec=discord.TextChannel)
        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, [], bot)

        assert result is False

    async def test_message_not_found_returns_false(self) -> None:
        """メッセージが見つからない場合 False を返す。"""
        from src.ui.role_panel_view import refresh_role_panel

        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test",
            message_id="789",
        )
        # NotFound 例外用のモック response を作成
        mock_response = MagicMock()
        mock_response.status = 404

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(mock_response, "Not found")
        )
        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, [], bot)

        assert result is False

    async def test_button_panel_updates_view(self) -> None:
        """ボタン式パネルが View を更新する。"""
        from src.ui.role_panel_view import refresh_role_panel

        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test",
            message_id="789",
        )
        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮", position=0),
        ]

        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.edit = AsyncMock()

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=mock_msg)

        bot = MagicMock(spec=discord.Client)
        bot.add_view = MagicMock()

        result = await refresh_role_panel(channel, panel, items, bot)

        assert result is True
        bot.add_view.assert_called_once()
        mock_msg.edit.assert_awaited_once()

    async def test_reaction_panel_updates_reactions(self) -> None:
        """リアクション式パネルがリアクションを更新する。"""
        from src.ui.role_panel_view import refresh_role_panel

        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Test",
            message_id="789",
        )
        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮", position=0),
            RolePanelItem(id=2, panel_id=1, role_id="222", emoji="🎨", position=1),
        ]

        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.edit = AsyncMock()
        mock_msg.clear_reactions = AsyncMock()
        mock_msg.add_reaction = AsyncMock()

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=mock_msg)

        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, items, bot)

        assert result is True
        mock_msg.edit.assert_awaited_once()
        mock_msg.clear_reactions.assert_awaited_once()
        assert mock_msg.add_reaction.await_count == 2

    async def test_http_exception_returns_false(self) -> None:
        """HTTPException が発生した場合 False を返す。"""
        from src.ui.role_panel_view import refresh_role_panel

        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test",
            message_id="789",
        )
        mock_response = MagicMock()
        mock_response.status = 500

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(
            side_effect=discord.HTTPException(mock_response, "Server error")
        )
        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, [], bot)

        assert result is False

    async def test_reaction_add_failure_continues(self) -> None:
        """リアクション追加失敗時も続行する。"""
        from src.ui.role_panel_view import refresh_role_panel

        panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Test",
            message_id="789",
        )
        items = [
            RolePanelItem(id=1, panel_id=1, role_id="111", emoji="🎮", position=0),
            RolePanelItem(id=2, panel_id=1, role_id="222", emoji="🎨", position=1),
        ]

        mock_response = MagicMock()
        mock_response.status = 400

        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.edit = AsyncMock()
        mock_msg.clear_reactions = AsyncMock()
        # 1回目は失敗、2回目は成功
        mock_msg.add_reaction = AsyncMock(
            side_effect=[
                discord.HTTPException(mock_response, "Invalid emoji"),
                None,
            ]
        )

        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=mock_msg)

        bot = MagicMock(spec=discord.Client)

        result = await refresh_role_panel(channel, panel, items, bot)

        assert result is True
        assert mock_msg.add_reaction.await_count == 2


# =============================================================================
# Command Success Path Tests
# =============================================================================


class TestAddCommandSuccess:
    """add コマンドの成功パスのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        bot = MagicMock(spec=commands.Bot)
        bot.add_view = MagicMock()
        return bot

    async def test_add_role_success(self, mock_bot: MagicMock) -> None:
        """ロール追加が成功する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123

        interaction.channel = mock_channel
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.get_channel.return_value = mock_channel
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 456
        mock_role.mention = "@TestRole"

        mock_panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="123",
            panel_type="button",
            title="Test",
            message_id="789",
        )

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panels_by_channel"
            ) as mock_get_panels:
                mock_get_panels.return_value = [mock_panel]

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = None

                    with patch(
                        "src.cogs.role_panel.add_role_panel_item"
                    ) as mock_add_item:
                        mock_add_item.return_value = RolePanelItem(
                            id=1,
                            panel_id=1,
                            role_id="456",
                            emoji="🎮",
                            position=0,
                        )

                        with patch(
                            "src.cogs.role_panel.get_role_panel_items"
                        ) as mock_get_items:
                            mock_get_items.return_value = []

                            with patch(
                                "src.cogs.role_panel.refresh_role_panel"
                            ) as mock_refresh:
                                mock_refresh.return_value = True

                                await cog.add.callback(
                                    cog,
                                    interaction,
                                    mock_role,
                                    "🎮",
                                    "Gamer",
                                    "primary",
                                )

        interaction.followup.send.assert_awaited_once()
        call_args = interaction.followup.send.call_args
        assert "追加しました" in call_args.args[0]


class TestRemoveCommandSuccess:
    """remove コマンドの成功パスのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        bot = MagicMock(spec=commands.Bot)
        bot.add_view = MagicMock()
        return bot

    async def test_remove_role_success(self, mock_bot: MagicMock) -> None:
        """ロール削除が成功する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123

        interaction.channel = mock_channel
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.get_channel.return_value = mock_channel
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="123",
            panel_type="button",
            title="Test",
            message_id="789",
        )

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panels_by_channel"
            ) as mock_get_panels:
                mock_get_panels.return_value = [mock_panel]

                with patch("src.cogs.role_panel.remove_role_panel_item") as mock_remove:
                    mock_remove.return_value = True

                    with patch(
                        "src.cogs.role_panel.get_role_panel_items"
                    ) as mock_get_items:
                        mock_get_items.return_value = []

                        with patch(
                            "src.cogs.role_panel.refresh_role_panel"
                        ) as mock_refresh:
                            mock_refresh.return_value = True

                            await cog.remove.callback(cog, interaction, "🎮")

        interaction.followup.send.assert_awaited_once()
        call_args = interaction.followup.send.call_args
        assert "削除しました" in call_args.args[0]


class TestDeleteCommandSuccess:
    """delete コマンドの成功パスのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        return MagicMock(spec=commands.Bot)

    async def test_delete_panel_success(self, mock_bot: MagicMock) -> None:
        """パネル削除が成功する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123
        mock_channel.fetch_message = AsyncMock(return_value=MagicMock())

        interaction.channel = mock_channel
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.get_channel.return_value = mock_channel
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="123",
            panel_type="button",
            title="Test",
            message_id="789",
        )

        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.delete = AsyncMock()

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panels_by_channel"
            ) as mock_get_panels:
                mock_get_panels.return_value = [mock_panel]

                with patch.object(mock_channel, "fetch_message") as mock_fetch:
                    mock_fetch.return_value = mock_msg

                    with patch("src.cogs.role_panel.delete_role_panel") as mock_delete:
                        mock_delete.return_value = True

                        await cog.delete.callback(cog, interaction)

        interaction.followup.send.assert_awaited_once()
        call_args = interaction.followup.send.call_args
        assert "削除しました" in call_args.args[0]


class TestListCommandSuccess:
    """list コマンドの成功パスのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        return MagicMock(spec=commands.Bot)

    async def test_list_panels_with_results(self, mock_bot: MagicMock) -> None:
        """パネル一覧を表示する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.mention = "#test-channel"

        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.guild.get_channel.return_value = mock_channel
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_panels = [
            RolePanel(
                id=1,
                guild_id="123",
                channel_id="456",
                panel_type="button",
                title="Test Panel",
            ),
        ]

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.services.db_service.get_role_panels_by_guild"
            ) as mock_get_panels:
                mock_get_panels.return_value = mock_panels

                with patch(
                    "src.cogs.role_panel.get_role_panel_items"
                ) as mock_get_items:
                    mock_get_items.return_value = []

                    await cog.list_panels.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "embed" in call_args.kwargs


# =============================================================================
# Reaction Handler Success Path Tests
# =============================================================================


class TestHandleReactionSuccess:
    """リアクションハンドラの成功パスのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        bot = MagicMock(spec=commands.Bot)
        bot.user = MagicMock()
        bot.user.id = 999
        return bot

    async def test_normal_mode_add_role(self, mock_bot: MagicMock) -> None:
        """通常モードでロール付与が成功する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456
        payload.guild_id = 789
        payload.channel_id = 111
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="🎮")

        mock_panel = RolePanel(
            id=1,
            guild_id="789",
            channel_id="111",
            panel_type="reaction",
            title="Test",
            remove_reaction=False,
        )
        mock_item = RolePanelItem(
            id=1, panel_id=1, role_id="222", emoji="🎮", position=0
        )

        mock_role = MagicMock(spec=discord.Role)
        mock_role.name = "TestRole"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.bot = False
        mock_member.roles = []
        mock_member.add_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role

        mock_bot.get_guild.return_value = mock_guild

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = mock_item

                    await cog._handle_reaction(payload, "add")

        mock_member.add_roles.assert_awaited_once()

    async def test_normal_mode_remove_role(self, mock_bot: MagicMock) -> None:
        """通常モードでロール解除が成功する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456
        payload.guild_id = 789
        payload.channel_id = 111
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="🎮")

        mock_panel = RolePanel(
            id=1,
            guild_id="789",
            channel_id="111",
            panel_type="reaction",
            title="Test",
            remove_reaction=False,
        )
        mock_item = RolePanelItem(
            id=1, panel_id=1, role_id="222", emoji="🎮", position=0
        )

        mock_role = MagicMock(spec=discord.Role)
        mock_role.name = "TestRole"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.bot = False
        mock_member.roles = [mock_role]  # ロールを持っている
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role

        mock_bot.get_guild.return_value = mock_guild

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = mock_item

                    await cog._handle_reaction(payload, "remove")

        mock_member.remove_roles.assert_awaited_once()

    async def test_remove_reaction_mode_toggle_add(self, mock_bot: MagicMock) -> None:
        """リアクション自動削除モードでロール付与 (トグル) が成功する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456
        payload.guild_id = 789
        payload.channel_id = 111
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="🎮")

        mock_panel = RolePanel(
            id=1,
            guild_id="789",
            channel_id="111",
            panel_type="reaction",
            title="Test",
            remove_reaction=True,  # 自動削除モード
        )
        mock_item = RolePanelItem(
            id=1, panel_id=1, role_id="222", emoji="🎮", position=0
        )

        mock_role = MagicMock(spec=discord.Role)
        mock_role.name = "TestRole"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.bot = False
        mock_member.roles = []  # ロールを持っていない
        mock_member.add_roles = AsyncMock()

        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.remove_reaction = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_msg)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role
        mock_guild.get_channel.return_value = mock_channel

        mock_bot.get_guild.return_value = mock_guild

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = mock_item

                    await cog._handle_reaction(payload, "add")

        # リアクションが削除されたことを確認
        mock_msg.remove_reaction.assert_awaited_once()
        # ロールが付与されたことを確認
        mock_member.add_roles.assert_awaited_once()

    async def test_remove_reaction_mode_toggle_remove(
        self, mock_bot: MagicMock
    ) -> None:
        """リアクション自動削除モードでロール解除 (トグル) が成功する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456
        payload.guild_id = 789
        payload.channel_id = 111
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="🎮")

        mock_panel = RolePanel(
            id=1,
            guild_id="789",
            channel_id="111",
            panel_type="reaction",
            title="Test",
            remove_reaction=True,  # 自動削除モード
        )
        mock_item = RolePanelItem(
            id=1, panel_id=1, role_id="222", emoji="🎮", position=0
        )

        mock_role = MagicMock(spec=discord.Role)
        mock_role.name = "TestRole"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.bot = False
        mock_member.roles = [mock_role]  # ロールを持っている
        mock_member.remove_roles = AsyncMock()

        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.remove_reaction = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_msg)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role
        mock_guild.get_channel.return_value = mock_channel

        mock_bot.get_guild.return_value = mock_guild

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = mock_item

                    await cog._handle_reaction(payload, "add")

        # リアクションが削除されたことを確認
        mock_msg.remove_reaction.assert_awaited_once()
        # ロールが解除されたことを確認
        mock_member.remove_roles.assert_awaited_once()

    async def test_remove_reaction_mode_ignores_remove_action(
        self, mock_bot: MagicMock
    ) -> None:
        """リアクション自動削除モードで remove アクションは無視する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456
        payload.guild_id = 789
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="🎮")

        mock_panel = RolePanel(
            id=1,
            guild_id="789",
            channel_id="111",
            panel_type="reaction",
            title="Test",
            remove_reaction=True,  # 自動削除モード
        )
        mock_item = RolePanelItem(
            id=1, panel_id=1, role_id="222", emoji="🎮", position=0
        )

        mock_role = MagicMock(spec=discord.Role)
        mock_member = MagicMock(spec=discord.Member)
        mock_member.bot = False
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role

        mock_bot.get_guild.return_value = mock_guild

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = mock_item

                    # remove アクションで呼び出し
                    await cog._handle_reaction(payload, "remove")

        # どちらのロール操作も呼ばれない
        mock_member.add_roles.assert_not_awaited()
        mock_member.remove_roles.assert_not_awaited()

    async def test_no_guild_returns_early(self, mock_bot: MagicMock) -> None:
        """ギルドが取得できない場合は早期終了する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456
        payload.guild_id = 789
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="🎮")

        mock_panel = RolePanel(
            id=1,
            guild_id="789",
            channel_id="111",
            panel_type="reaction",
            title="Test",
            remove_reaction=False,
        )
        mock_item = RolePanelItem(
            id=1, panel_id=1, role_id="222", emoji="🎮", position=0
        )

        mock_bot.get_guild.return_value = None

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = mock_item

                    await cog._handle_reaction(payload, "add")

    async def test_member_fetch_failure_returns_early(
        self, mock_bot: MagicMock
    ) -> None:
        """メンバー取得失敗時は早期終了する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456
        payload.guild_id = 789
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="🎮")

        mock_panel = RolePanel(
            id=1,
            guild_id="789",
            channel_id="111",
            panel_type="reaction",
            title="Test",
            remove_reaction=False,
        )
        mock_item = RolePanelItem(
            id=1, panel_id=1, role_id="222", emoji="🎮", position=0
        )

        mock_response = MagicMock()
        mock_response.status = 404

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_member.return_value = None
        mock_guild.fetch_member = AsyncMock(
            side_effect=discord.HTTPException(mock_response, "Not found")
        )

        mock_bot.get_guild.return_value = mock_guild

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = mock_item

                    await cog._handle_reaction(payload, "add")

    async def test_bot_member_ignored(self, mock_bot: MagicMock) -> None:
        """Bot メンバーは無視する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456
        payload.guild_id = 789
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="🎮")

        mock_panel = RolePanel(
            id=1,
            guild_id="789",
            channel_id="111",
            panel_type="reaction",
            title="Test",
            remove_reaction=False,
        )
        mock_item = RolePanelItem(
            id=1, panel_id=1, role_id="222", emoji="🎮", position=0
        )

        mock_member = MagicMock(spec=discord.Member)
        mock_member.bot = True  # Bot

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_member.return_value = mock_member

        mock_bot.get_guild.return_value = mock_guild

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = mock_item

                    await cog._handle_reaction(payload, "add")

    async def test_role_not_found_logs_warning(self, mock_bot: MagicMock) -> None:
        """ロールが見つからない場合は警告ログを出力する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456
        payload.guild_id = 789
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="🎮")

        mock_panel = RolePanel(
            id=1,
            guild_id="789",
            channel_id="111",
            panel_type="reaction",
            title="Test",
            remove_reaction=False,
        )
        mock_item = RolePanelItem(
            id=1, panel_id=1, role_id="222", emoji="🎮", position=0
        )

        mock_member = MagicMock(spec=discord.Member)
        mock_member.bot = False

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = None  # ロールなし

        mock_bot.get_guild.return_value = mock_guild

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = mock_item

                    await cog._handle_reaction(payload, "add")

    async def test_role_forbidden_logs_warning(self, mock_bot: MagicMock) -> None:
        """権限不足の場合は警告ログを出力する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456
        payload.guild_id = 789
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="🎮")

        mock_panel = RolePanel(
            id=1,
            guild_id="789",
            channel_id="111",
            panel_type="reaction",
            title="Test",
            remove_reaction=False,
        )
        mock_item = RolePanelItem(
            id=1, panel_id=1, role_id="222", emoji="🎮", position=0
        )

        mock_role = MagicMock(spec=discord.Role)
        mock_role.name = "TestRole"

        mock_response = MagicMock()
        mock_response.status = 403

        mock_member = MagicMock(spec=discord.Member)
        mock_member.bot = False
        mock_member.roles = []
        mock_member.add_roles = AsyncMock(
            side_effect=discord.Forbidden(mock_response, "Forbidden")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role

        mock_bot.get_guild.return_value = mock_guild

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = mock_item

                    # 例外は無視される
                    await cog._handle_reaction(payload, "add")

    async def test_role_http_exception_logs_error(self, mock_bot: MagicMock) -> None:
        """HTTPException の場合はエラーログを出力する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 123
        payload.message_id = 456
        payload.guild_id = 789
        payload.emoji = MagicMock()
        payload.emoji.__str__ = MagicMock(return_value="🎮")

        mock_panel = RolePanel(
            id=1,
            guild_id="789",
            channel_id="111",
            panel_type="reaction",
            title="Test",
            remove_reaction=False,
        )
        mock_item = RolePanelItem(
            id=1, panel_id=1, role_id="222", emoji="🎮", position=0
        )

        mock_role = MagicMock(spec=discord.Role)
        mock_role.name = "TestRole"

        mock_response = MagicMock()
        mock_response.status = 500

        mock_member = MagicMock(spec=discord.Member)
        mock_member.bot = False
        mock_member.roles = []
        mock_member.add_roles = AsyncMock(
            side_effect=discord.HTTPException(mock_response, "Server error")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role

        mock_bot.get_guild.return_value = mock_guild

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panel_by_message_id"
            ) as mock_get_panel:
                mock_get_panel.return_value = mock_panel

                with patch(
                    "src.cogs.role_panel.get_role_panel_item_by_emoji"
                ) as mock_get_item:
                    mock_get_item.return_value = mock_item

                    # 例外は無視される
                    await cog._handle_reaction(payload, "add")


# =============================================================================
# RoleButton HTTPException Test
# =============================================================================


class TestRoleButtonHTTPException:
    """RoleButton の HTTPException テスト。"""

    async def test_callback_http_exception_error(self) -> None:
        """HTTPException でエラーを返す。"""
        from src.ui.role_panel_view import RoleButton

        item = RolePanelItem(
            id=1, panel_id=1, role_id="123", emoji="🎮", position=0, style="primary"
        )
        button = RoleButton(panel_id=1, item=item)

        mock_role = MagicMock(spec=discord.Role)
        mock_role.position = 5

        mock_bot_top_role = MagicMock(spec=discord.Role)
        mock_bot_top_role.position = 10

        mock_role.__ge__ = MagicMock(return_value=False)

        mock_response = MagicMock()
        mock_response.status = 500

        mock_member = MagicMock(spec=discord.Member)
        mock_member.roles = []
        mock_member.add_roles = AsyncMock(
            side_effect=discord.HTTPException(mock_response, "Server error")
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.get_role.return_value = mock_role
        interaction.guild.me = MagicMock(spec=discord.Member)
        interaction.guild.me.top_role = mock_bot_top_role
        interaction.user = mock_member
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "失敗しました" in call_args.args[0]


# =============================================================================
# Delete Command Message Delete Exception Test
# =============================================================================


class TestDeferFailure:
    """defer() 失敗時（別インスタンスが先に応答）のテスト。"""

    async def test_add_defer_failure_aborts(self) -> None:
        """add: defer() 失敗時、DB 書き込みもパネル更新もしない。"""
        from src.cogs.role_panel import RolePanelCog

        bot = MagicMock(spec=commands.Bot)
        cog = RolePanelCog(bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=400), "already acknowledged"
            )
        )
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_role = MagicMock(spec=discord.Role)

        with patch(
            "src.cogs.role_panel.add_role_panel_item", new_callable=AsyncMock
        ) as mock_add:
            await cog.add.callback(cog, interaction, mock_role, "🎮", None, "secondary")
            mock_add.assert_not_awaited()
            interaction.followup.send.assert_not_awaited()

    async def test_remove_defer_failure_aborts(self) -> None:
        """remove: defer() 失敗時、DB 削除もパネル更新もしない。"""
        from src.cogs.role_panel import RolePanelCog

        bot = MagicMock(spec=commands.Bot)
        cog = RolePanelCog(bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=400), "already acknowledged"
            )
        )
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        with patch(
            "src.cogs.role_panel.remove_role_panel_item", new_callable=AsyncMock
        ) as mock_remove:
            await cog.remove.callback(cog, interaction, "🎮")
            mock_remove.assert_not_awaited()
            interaction.followup.send.assert_not_awaited()

    async def test_delete_defer_failure_aborts(self) -> None:
        """delete: defer() 失敗時、メッセージ削除も DB 削除もしない。"""
        from src.cogs.role_panel import RolePanelCog

        bot = MagicMock(spec=commands.Bot)
        cog = RolePanelCog(bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.id = 123
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=400), "already acknowledged"
            )
        )
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        with patch(
            "src.cogs.role_panel.delete_role_panel", new_callable=AsyncMock
        ) as mock_delete:
            await cog.delete.callback(cog, interaction)
            mock_delete.assert_not_awaited()
            interaction.followup.send.assert_not_awaited()


class TestDeleteCommandException:
    """delete コマンドの例外処理テスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        return MagicMock(spec=commands.Bot)

    async def test_delete_message_not_found_continues(
        self, mock_bot: MagicMock
    ) -> None:
        """メッセージ削除失敗時も続行する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123

        mock_response = MagicMock()
        mock_response.status = 404
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.HTTPException(mock_response, "Not found")
        )

        interaction.channel = mock_channel
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.get_channel.return_value = mock_channel
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_panel = RolePanel(
            id=1,
            guild_id="123",
            channel_id="123",
            panel_type="button",
            title="Test",
            message_id="789",
        )

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.get_role_panels_by_channel"
            ) as mock_get_panels:
                mock_get_panels.return_value = [mock_panel]

                with patch("src.cogs.role_panel.delete_role_panel") as mock_delete:
                    mock_delete.return_value = True

                    await cog.delete.callback(cog, interaction)

        interaction.followup.send.assert_awaited_once()
        call_args = interaction.followup.send.call_args
        assert "削除しました" in call_args.args[0]


# =============================================================================
# Reaction Event Listener Tests
# =============================================================================


class TestReactionEventListeners:
    """リアクションイベントリスナーのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        bot = MagicMock(spec=commands.Bot)
        bot.user = MagicMock()
        bot.user.id = 999
        return bot

    async def test_on_raw_reaction_add(self, mock_bot: MagicMock) -> None:
        """on_raw_reaction_add がハンドラを呼び出す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 999  # Bot の ID

        # Bot 自身のリアクションは無視されるので、_handle_reaction は実質何もしない
        await cog.on_raw_reaction_add(payload)

    async def test_on_raw_reaction_remove(self, mock_bot: MagicMock) -> None:
        """on_raw_reaction_remove がハンドラを呼び出す。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.user_id = 999  # Bot の ID

        # Bot 自身のリアクションは無視されるので、_handle_reaction は実質何もしない
        await cog.on_raw_reaction_remove(payload)


# =============================================================================
# Role Sync Event Listener Tests
# =============================================================================


class TestRoleSyncEventListeners:
    """ロール同期イベントリスナーのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        bot = MagicMock(spec=commands.Bot)
        bot.user = MagicMock()
        bot.user.id = 999
        bot.guilds = []
        return bot

    @pytest.fixture
    def mock_role(self) -> MagicMock:
        """Mock Discord Role."""
        role = MagicMock(spec=discord.Role)
        role.id = 123
        role.name = "Test Role"
        role.color = MagicMock()
        role.color.value = 0xFF0000
        role.position = 5
        role.is_default.return_value = False
        role.managed = False
        role.guild = MagicMock(spec=discord.Guild)
        role.guild.id = 456
        return role

    @pytest.fixture
    def mock_guild(self, mock_role: MagicMock) -> MagicMock:
        """Mock Discord Guild with roles."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 456
        guild.name = "Test Guild"

        # @everyone ロール (is_default=True)
        everyone_role = MagicMock(spec=discord.Role)
        everyone_role.is_default.return_value = True
        everyone_role.managed = False

        # Bot ロール (managed=True)
        bot_role = MagicMock(spec=discord.Role)
        bot_role.is_default.return_value = False
        bot_role.managed = True

        # 通常のロール
        mock_role.guild = guild

        guild.roles = [everyone_role, bot_role, mock_role]
        return guild

    async def test_sync_guild_roles_excludes_default_and_managed(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """_sync_guild_roles が @everyone とマネージドロールを除外する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_role") as mock_upsert:
                count = await cog._sync_guild_roles(mock_guild)

        # 通常のロールのみ (1件) が同期される
        assert count == 1
        mock_upsert.assert_called_once()

    async def test_on_ready_syncs_all_guilds(self, mock_bot: MagicMock) -> None:
        """on_ready が全ギルドの情報を同期する。"""
        from src.cogs.role_panel import RolePanelCog

        # 複数のギルドを設定
        guild1 = MagicMock(spec=discord.Guild)
        guild1.name = "Guild 1"
        guild1.roles = []

        guild2 = MagicMock(spec=discord.Guild)
        guild2.name = "Guild 2"
        guild2.roles = []

        mock_bot.guilds = [guild1, guild2]

        cog = RolePanelCog(mock_bot)

        with (
            patch.object(
                cog, "_sync_guild_info", new_callable=AsyncMock
            ) as mock_sync_info,
            patch.object(
                cog, "_sync_guild_roles", new_callable=AsyncMock
            ) as mock_sync_roles,
            patch.object(
                cog, "_sync_guild_channels", new_callable=AsyncMock
            ) as mock_sync_channels,
        ):
            mock_sync_roles.return_value = 5
            mock_sync_channels.return_value = 3

            await cog.on_ready()

        assert mock_sync_info.call_count == 2
        assert mock_sync_roles.call_count == 2
        assert mock_sync_channels.call_count == 2

    async def test_on_guild_join_syncs_roles(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """on_guild_join が新しいギルドの情報を同期する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        with (
            patch.object(
                cog, "_sync_guild_info", new_callable=AsyncMock
            ) as mock_sync_info,
            patch.object(
                cog, "_sync_guild_roles", new_callable=AsyncMock
            ) as mock_sync_roles,
            patch.object(
                cog, "_sync_guild_channels", new_callable=AsyncMock
            ) as mock_sync_channels,
        ):
            mock_sync_roles.return_value = 3
            mock_sync_channels.return_value = 5

            await cog.on_guild_join(mock_guild)

        mock_sync_info.assert_called_once_with(mock_guild)
        mock_sync_roles.assert_called_once_with(mock_guild)
        mock_sync_channels.assert_called_once_with(mock_guild)

    async def test_on_guild_remove_deletes_cached_roles(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """on_guild_remove がキャッシュされたロールとギルド情報を削除する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with (
                patch(
                    "src.cogs.role_panel.delete_discord_roles_by_guild"
                ) as mock_delete_roles,
                patch(
                    "src.cogs.role_panel.delete_discord_channels_by_guild"
                ) as mock_delete_channels,
                patch("src.cogs.role_panel.delete_discord_guild") as mock_delete_guild,
            ):
                mock_delete_roles.return_value = 5
                mock_delete_channels.return_value = 3
                mock_delete_guild.return_value = True

                await cog.on_guild_remove(mock_guild)

        mock_delete_roles.assert_called_once_with(mock_db, str(mock_guild.id))
        mock_delete_channels.assert_called_once_with(mock_db, str(mock_guild.id))
        mock_delete_guild.assert_called_once_with(mock_db, str(mock_guild.id))

    async def test_on_guild_role_create_adds_role(
        self, mock_bot: MagicMock, mock_role: MagicMock
    ) -> None:
        """on_guild_role_create がロールをキャッシュに追加する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_role") as mock_upsert:
                await cog.on_guild_role_create(mock_role)

        mock_upsert.assert_called_once_with(
            mock_db,
            guild_id=str(mock_role.guild.id),
            role_id=str(mock_role.id),
            role_name=mock_role.name,
            color=mock_role.color.value,
            position=mock_role.position,
        )

    async def test_on_guild_role_create_skips_default_role(
        self, mock_bot: MagicMock, mock_role: MagicMock
    ) -> None:
        """on_guild_role_create が @everyone ロールをスキップする。"""
        from src.cogs.role_panel import RolePanelCog

        mock_role.is_default.return_value = True

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.upsert_discord_role") as mock_upsert:
            await cog.on_guild_role_create(mock_role)

        mock_upsert.assert_not_called()

    async def test_on_guild_role_create_skips_managed_role(
        self, mock_bot: MagicMock, mock_role: MagicMock
    ) -> None:
        """on_guild_role_create がマネージドロールをスキップする。"""
        from src.cogs.role_panel import RolePanelCog

        mock_role.managed = True

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.upsert_discord_role") as mock_upsert:
            await cog.on_guild_role_create(mock_role)

        mock_upsert.assert_not_called()

    async def test_on_guild_role_update_updates_role(
        self, mock_bot: MagicMock, mock_role: MagicMock
    ) -> None:
        """on_guild_role_update がロールを更新する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        before_role = MagicMock(spec=discord.Role)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_role") as mock_upsert:
                await cog.on_guild_role_update(before_role, mock_role)

        mock_upsert.assert_called_once()

    async def test_on_guild_role_update_skips_default_role(
        self, mock_bot: MagicMock, mock_role: MagicMock
    ) -> None:
        """on_guild_role_update が @everyone ロールをスキップする。"""
        from src.cogs.role_panel import RolePanelCog

        mock_role.is_default.return_value = True

        cog = RolePanelCog(mock_bot)
        before_role = MagicMock(spec=discord.Role)

        with patch("src.cogs.role_panel.upsert_discord_role") as mock_upsert:
            await cog.on_guild_role_update(before_role, mock_role)

        mock_upsert.assert_not_called()

    async def test_on_guild_role_delete_removes_role(
        self, mock_bot: MagicMock, mock_role: MagicMock
    ) -> None:
        """on_guild_role_delete がロールをキャッシュから削除する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.delete_discord_role") as mock_delete:
                await cog.on_guild_role_delete(mock_role)

        mock_delete.assert_called_once_with(
            mock_db, str(mock_role.guild.id), str(mock_role.id)
        )

    async def test_sync_guild_roles_with_empty_guild(self, mock_bot: MagicMock) -> None:
        """_sync_guild_roles が空のギルドで 0 を返す。"""
        from src.cogs.role_panel import RolePanelCog

        empty_guild = MagicMock(spec=discord.Guild)
        empty_guild.id = 123
        empty_guild.roles = []

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            count = await cog._sync_guild_roles(empty_guild)

        assert count == 0

    async def test_sync_guild_roles_skips_all_special_roles(
        self, mock_bot: MagicMock
    ) -> None:
        """_sync_guild_roles が @everyone と Bot ロールのみの場合 0 を返す。"""
        from src.cogs.role_panel import RolePanelCog

        # @everyone ロール
        everyone = MagicMock(spec=discord.Role)
        everyone.is_default.return_value = True
        everyone.managed = False

        # Bot ロール
        bot_role = MagicMock(spec=discord.Role)
        bot_role.is_default.return_value = False
        bot_role.managed = True

        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.roles = [everyone, bot_role]

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_role") as mock_upsert:
                count = await cog._sync_guild_roles(guild)

        assert count == 0
        mock_upsert.assert_not_called()

    async def test_on_guild_role_update_with_managed_role(
        self, mock_bot: MagicMock
    ) -> None:
        """on_guild_role_update がマネージドロールをスキップする。"""
        from src.cogs.role_panel import RolePanelCog

        before = MagicMock(spec=discord.Role)
        after = MagicMock(spec=discord.Role)
        after.is_default.return_value = False
        after.managed = True  # Bot ロールなど

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.upsert_discord_role") as mock_upsert:
            await cog.on_guild_role_update(before, after)

        mock_upsert.assert_not_called()

    async def test_on_guild_role_delete_for_any_role(
        self, mock_bot: MagicMock, mock_role: MagicMock
    ) -> None:
        """on_guild_role_delete は managed ロールでも削除を試みる。"""
        from src.cogs.role_panel import RolePanelCog

        # managed ロールでもキャッシュからは削除する
        mock_role.managed = True

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.delete_discord_role") as mock_delete:
                await cog.on_guild_role_delete(mock_role)

        # managed ロールでも削除は呼ばれる（キャッシュにあれば削除）
        mock_delete.assert_called_once()

    async def test_sync_guild_roles_with_multiple_normal_roles(
        self, mock_bot: MagicMock
    ) -> None:
        """_sync_guild_roles が複数の通常ロールを同期する。"""
        from src.cogs.role_panel import RolePanelCog

        # 通常のロール 3 つ
        roles = []
        for i in range(3):
            role = MagicMock(spec=discord.Role)
            role.id = 100 + i
            role.name = f"Role {i}"
            role.color = MagicMock()
            role.color.value = 0xFF0000
            role.position = i
            role.is_default.return_value = False
            role.managed = False
            roles.append(role)

        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.roles = roles

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_role") as mock_upsert:
                count = await cog._sync_guild_roles(guild)

        assert count == 3
        assert mock_upsert.call_count == 3


# =============================================================================
# Guild Info and Channel Sync Event Listener Tests
# =============================================================================


class TestGuildInfoAndChannelSyncEventListeners:
    """ギルド情報・チャンネル同期イベントリスナーのテスト。"""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Mock Bot."""
        bot = MagicMock(spec=commands.Bot)
        bot.user = MagicMock()
        bot.user.id = 999
        bot.guilds = []
        return bot

    @pytest.fixture
    def mock_guild(self) -> MagicMock:
        """Mock Discord Guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 456
        guild.name = "Test Guild"
        guild.icon = MagicMock()
        guild.icon.key = "abc123"
        guild.member_count = 100
        guild.me = MagicMock()  # Bot 自身
        guild.channels = []
        return guild

    @pytest.fixture
    def mock_text_channel(self, mock_guild: MagicMock) -> MagicMock:
        """Mock Discord Text Channel."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 123
        channel.name = "general"
        channel.type = discord.ChannelType.text
        channel.position = 0
        channel.category_id = None
        channel.guild = mock_guild
        # permissions_for を設定
        perms = MagicMock()
        perms.view_channel = True
        channel.permissions_for.return_value = perms
        return channel

    # -------------------------------------------------------------------------
    # _sync_guild_info テスト
    # -------------------------------------------------------------------------

    async def test_sync_guild_info_upserts_guild(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """_sync_guild_info がギルド情報を upsert する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_guild") as mock_upsert:
                await cog._sync_guild_info(mock_guild)

        mock_upsert.assert_called_once_with(
            mock_db,
            guild_id=str(mock_guild.id),
            guild_name=mock_guild.name,
            icon_hash=mock_guild.icon.key,
            member_count=mock_guild.member_count,
        )

    async def test_sync_guild_info_with_no_icon(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """_sync_guild_info がアイコンなしのギルドを処理する。"""
        from src.cogs.role_panel import RolePanelCog

        mock_guild.icon = None  # アイコンなし

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_guild") as mock_upsert:
                await cog._sync_guild_info(mock_guild)

        mock_upsert.assert_called_once_with(
            mock_db,
            guild_id=str(mock_guild.id),
            guild_name=mock_guild.name,
            icon_hash=None,
            member_count=mock_guild.member_count,
        )

    async def test_sync_guild_info_with_zero_member_count(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """_sync_guild_info が member_count が None の場合 0 を使用する。"""
        from src.cogs.role_panel import RolePanelCog

        mock_guild.member_count = None

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_guild") as mock_upsert:
                await cog._sync_guild_info(mock_guild)

        mock_upsert.assert_called_once_with(
            mock_db,
            guild_id=str(mock_guild.id),
            guild_name=mock_guild.name,
            icon_hash=mock_guild.icon.key,
            member_count=0,
        )

    # -------------------------------------------------------------------------
    # _sync_guild_channels テスト
    # -------------------------------------------------------------------------

    async def test_sync_guild_channels_syncs_text_channel(
        self, mock_bot: MagicMock, mock_guild: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """_sync_guild_channels がテキストチャンネルを同期する。"""
        from src.cogs.role_panel import RolePanelCog

        mock_guild.channels = [mock_text_channel]

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_channel") as mock_upsert:
                count = await cog._sync_guild_channels(mock_guild)

        assert count == 1
        mock_upsert.assert_called_once_with(
            mock_db,
            guild_id=str(mock_guild.id),
            channel_id=str(mock_text_channel.id),
            channel_name=mock_text_channel.name,
            channel_type=mock_text_channel.type.value,
            position=mock_text_channel.position,
            category_id=None,
        )

    async def test_sync_guild_channels_syncs_news_channel(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """_sync_guild_channels がニュース (アナウンス) チャンネルを同期する。"""
        from src.cogs.role_panel import RolePanelCog

        news_channel = MagicMock()
        news_channel.id = 456
        news_channel.name = "announcements"
        news_channel.type = discord.ChannelType.news
        news_channel.position = 1
        news_channel.category_id = 789
        news_channel.guild = mock_guild
        perms = MagicMock()
        perms.view_channel = True
        news_channel.permissions_for.return_value = perms

        mock_guild.channels = [news_channel]

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_channel") as mock_upsert:
                count = await cog._sync_guild_channels(mock_guild)

        assert count == 1
        mock_upsert.assert_called_once()
        call_args = mock_upsert.call_args
        assert call_args.kwargs["channel_type"] == discord.ChannelType.news.value
        assert call_args.kwargs["category_id"] == "789"

    async def test_sync_guild_channels_syncs_forum_channel(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """_sync_guild_channels がフォーラムチャンネルを同期する。"""
        from src.cogs.role_panel import RolePanelCog

        forum_channel = MagicMock()
        forum_channel.id = 789
        forum_channel.name = "help-forum"
        forum_channel.type = discord.ChannelType.forum
        forum_channel.position = 2
        forum_channel.category_id = None
        forum_channel.guild = mock_guild
        perms = MagicMock()
        perms.view_channel = True
        forum_channel.permissions_for.return_value = perms

        mock_guild.channels = [forum_channel]

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_channel") as mock_upsert:
                count = await cog._sync_guild_channels(mock_guild)

        assert count == 1
        mock_upsert.assert_called_once()
        call_args = mock_upsert.call_args
        assert call_args.kwargs["channel_type"] == discord.ChannelType.forum.value

    async def test_sync_guild_channels_syncs_voice_channel(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """_sync_guild_channels がボイスチャンネルを同期する。"""
        from src.cogs.role_panel import RolePanelCog

        voice_channel = MagicMock()
        voice_channel.id = 111
        voice_channel.name = "Voice"
        voice_channel.type = discord.ChannelType.voice
        voice_channel.guild = mock_guild
        voice_channel.position = 0
        voice_channel.category_id = None
        perms = MagicMock()
        perms.view_channel = True
        voice_channel.permissions_for.return_value = perms

        mock_guild.channels = [voice_channel]

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_channel") as mock_upsert:
                count = await cog._sync_guild_channels(mock_guild)

        assert count == 1
        mock_upsert.assert_called_once()

    async def test_sync_guild_channels_includes_category(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """_sync_guild_channels がカテゴリチャンネルを同期する。"""
        from src.cogs.role_panel import RolePanelCog

        category = MagicMock()
        category.id = 222
        category.name = "Category"
        category.type = discord.ChannelType.category
        category.category_id = None
        category.position = 0
        category.guild = mock_guild
        perms = MagicMock()
        perms.view_channel = True
        category.permissions_for.return_value = perms

        mock_guild.channels = [category]

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_channel") as mock_upsert:
                count = await cog._sync_guild_channels(mock_guild)

        assert count == 1
        mock_upsert.assert_called_once()

    async def test_sync_guild_channels_skips_no_view_permission(
        self, mock_bot: MagicMock, mock_guild: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """_sync_guild_channels が Bot に閲覧権限のないチャンネルをスキップする。"""
        from src.cogs.role_panel import RolePanelCog

        # Bot に view_channel 権限がない
        perms = MagicMock()
        perms.view_channel = False
        mock_text_channel.permissions_for.return_value = perms

        mock_guild.channels = [mock_text_channel]

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_channel") as mock_upsert:
                count = await cog._sync_guild_channels(mock_guild)

        assert count == 0
        mock_upsert.assert_not_called()

    async def test_sync_guild_channels_with_multiple_channels(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """_sync_guild_channels が複数の対象チャンネルを同期する。"""
        from src.cogs.role_panel import RolePanelCog

        channels = []
        for i, (name, ch_type) in enumerate(
            [
                ("general", discord.ChannelType.text),
                ("announcements", discord.ChannelType.news),
                ("voice", discord.ChannelType.voice),
                ("help", discord.ChannelType.forum),
            ]
        ):
            ch = MagicMock()
            ch.id = 100 + i
            ch.name = name
            ch.type = ch_type
            ch.position = i
            ch.category_id = None
            ch.guild = mock_guild
            perms = MagicMock()
            perms.view_channel = True
            ch.permissions_for.return_value = perms
            channels.append(ch)

        mock_guild.channels = channels

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_channel") as mock_upsert:
                count = await cog._sync_guild_channels(mock_guild)

        # text, voice, news, forum の 4 つ
        assert count == 4
        assert mock_upsert.call_count == 4

    async def test_sync_guild_channels_with_empty_guild(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """_sync_guild_channels が空のギルドで 0 を返す。"""
        from src.cogs.role_panel import RolePanelCog

        mock_guild.channels = []

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            count = await cog._sync_guild_channels(mock_guild)

        assert count == 0

    # -------------------------------------------------------------------------
    # on_guild_update テスト
    # -------------------------------------------------------------------------

    async def test_on_guild_update_syncs_when_name_changes(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """on_guild_update がギルド名変更時に同期する。"""
        from src.cogs.role_panel import RolePanelCog

        before = MagicMock(spec=discord.Guild)
        before.name = "Old Name"
        before.icon = mock_guild.icon

        mock_guild.name = "New Name"

        cog = RolePanelCog(mock_bot)

        with patch.object(cog, "_sync_guild_info", new_callable=AsyncMock) as mock_sync:
            await cog.on_guild_update(before, mock_guild)

        mock_sync.assert_called_once_with(mock_guild)

    async def test_on_guild_update_syncs_when_icon_changes(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """on_guild_update がアイコン変更時に同期する。"""
        from src.cogs.role_panel import RolePanelCog

        before = MagicMock(spec=discord.Guild)
        before.name = mock_guild.name
        before.icon = MagicMock()
        before.icon.key = "old_icon"

        # 新しいアイコン
        mock_guild.icon.key = "new_icon"

        cog = RolePanelCog(mock_bot)

        with patch.object(cog, "_sync_guild_info", new_callable=AsyncMock) as mock_sync:
            await cog.on_guild_update(before, mock_guild)

        mock_sync.assert_called_once_with(mock_guild)

    async def test_on_guild_update_skips_when_no_change(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """on_guild_update が名前もアイコンも変更なしの場合スキップする。"""
        from src.cogs.role_panel import RolePanelCog

        before = MagicMock(spec=discord.Guild)
        before.name = mock_guild.name
        before.icon = mock_guild.icon  # 同じアイコン

        cog = RolePanelCog(mock_bot)

        with patch.object(cog, "_sync_guild_info", new_callable=AsyncMock) as mock_sync:
            await cog.on_guild_update(before, mock_guild)

        mock_sync.assert_not_called()

    # -------------------------------------------------------------------------
    # on_guild_channel_create テスト
    # -------------------------------------------------------------------------

    async def test_on_guild_channel_create_adds_text_channel(
        self, mock_bot: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """on_guild_channel_create がテキストチャンネルを追加する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_channel") as mock_upsert:
                await cog.on_guild_channel_create(mock_text_channel)

        mock_upsert.assert_called_once_with(
            mock_db,
            guild_id=str(mock_text_channel.guild.id),
            channel_id=str(mock_text_channel.id),
            channel_name=mock_text_channel.name,
            channel_type=mock_text_channel.type.value,
            position=mock_text_channel.position,
            category_id=None,
        )

    async def test_on_guild_channel_create_syncs_voice_channel(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """on_guild_channel_create がボイスチャンネルを同期する。"""
        from src.cogs.role_panel import RolePanelCog

        voice_channel = MagicMock()
        voice_channel.id = 111
        voice_channel.name = "voice-lobby"
        voice_channel.type = discord.ChannelType.voice
        voice_channel.position = 0
        voice_channel.category_id = None
        voice_channel.guild = mock_guild
        perms = MagicMock()
        perms.view_channel = True
        voice_channel.permissions_for.return_value = perms

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_channel") as mock_upsert:
                await cog.on_guild_channel_create(voice_channel)

            mock_upsert.assert_called_once()

    async def test_on_guild_channel_create_skips_no_view_permission(
        self, mock_bot: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """on_guild_channel_create が閲覧権限なしチャンネルをスキップする。"""
        from src.cogs.role_panel import RolePanelCog

        perms = MagicMock()
        perms.view_channel = False
        mock_text_channel.permissions_for.return_value = perms

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.upsert_discord_channel") as mock_upsert:
            await cog.on_guild_channel_create(mock_text_channel)

        mock_upsert.assert_not_called()

    async def test_on_guild_channel_create_with_category(
        self, mock_bot: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """on_guild_channel_create がカテゴリー ID を保存する。"""
        from src.cogs.role_panel import RolePanelCog

        mock_text_channel.category_id = 999

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_channel") as mock_upsert:
                await cog.on_guild_channel_create(mock_text_channel)

        call_args = mock_upsert.call_args
        assert call_args.kwargs["category_id"] == "999"

    # -------------------------------------------------------------------------
    # on_guild_channel_update テスト
    # -------------------------------------------------------------------------

    async def test_on_guild_channel_update_updates_channel(
        self, mock_bot: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """on_guild_channel_update がチャンネルを更新する。"""
        from src.cogs.role_panel import RolePanelCog

        before = MagicMock()
        before.name = "old-name"

        mock_text_channel.name = "new-name"

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.upsert_discord_channel") as mock_upsert:
                await cog.on_guild_channel_update(before, mock_text_channel)

        mock_upsert.assert_called_once()
        call_args = mock_upsert.call_args
        assert call_args.kwargs["channel_name"] == "new-name"

    async def test_on_guild_channel_update_deletes_when_type_changes_to_category(
        self, mock_bot: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """on_guild_channel_update がタイプが非対象に変わった場合削除する。"""
        from src.cogs.role_panel import RolePanelCog

        before = MagicMock()
        before.type = discord.ChannelType.text

        # タイプがステージに変更 (非対象)
        after = MagicMock()
        after.type = discord.ChannelType.stage_voice
        after.guild = mock_text_channel.guild
        after.id = mock_text_channel.id

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.delete_discord_channel") as mock_delete:
                await cog.on_guild_channel_update(before, after)

        mock_delete.assert_called_once_with(mock_db, str(after.guild.id), str(after.id))

    async def test_on_guild_channel_update_deletes_when_view_permission_lost(
        self, mock_bot: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """on_guild_channel_update が閲覧権限がなくなった場合削除する。"""
        from src.cogs.role_panel import RolePanelCog

        before = MagicMock()

        # 権限がなくなった
        perms = MagicMock()
        perms.view_channel = False
        mock_text_channel.permissions_for.return_value = perms

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch("src.cogs.role_panel.delete_discord_channel") as mock_delete:
                await cog.on_guild_channel_update(before, mock_text_channel)

        mock_delete.assert_called_once_with(
            mock_db, str(mock_text_channel.guild.id), str(mock_text_channel.id)
        )

    # -------------------------------------------------------------------------
    # on_guild_channel_delete テスト
    # -------------------------------------------------------------------------

    async def test_on_guild_channel_delete_removes_channel(
        self, mock_bot: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """on_guild_channel_delete がチャンネルを削除する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with (
                patch(
                    "src.cogs.role_panel.delete_discord_channel"
                ) as mock_delete_channel,
                patch(
                    "src.cogs.role_panel.delete_role_panels_by_channel",
                    return_value=0,
                ) as mock_delete_panels,
            ):
                await cog.on_guild_channel_delete(mock_text_channel)

        mock_delete_channel.assert_called_once_with(
            mock_db, str(mock_text_channel.guild.id), str(mock_text_channel.id)
        )
        mock_delete_panels.assert_called_once_with(mock_db, str(mock_text_channel.id))

    async def test_on_guild_channel_delete_removes_role_panels(
        self, mock_bot: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """on_guild_channel_delete がロールパネルも削除する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with (
                patch("src.cogs.role_panel.delete_discord_channel"),
                patch(
                    "src.cogs.role_panel.delete_role_panels_by_channel",
                    return_value=2,
                ) as mock_delete_panels,
            ):
                await cog.on_guild_channel_delete(mock_text_channel)

        # ロールパネル削除が呼ばれる
        mock_delete_panels.assert_called_once_with(mock_db, str(mock_text_channel.id))

    async def test_on_guild_channel_delete_works_for_any_channel_type(
        self, mock_bot: MagicMock, mock_guild: MagicMock
    ) -> None:
        """on_guild_channel_delete が全てのチャンネルタイプで削除を試みる。"""
        from src.cogs.role_panel import RolePanelCog

        # ボイスチャンネルでも削除は試みる（キャッシュにあれば削除）
        voice_channel = MagicMock()
        voice_channel.id = 333
        voice_channel.type = discord.ChannelType.voice
        voice_channel.guild = mock_guild

        cog = RolePanelCog(mock_bot)

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with (
                patch(
                    "src.cogs.role_panel.delete_discord_channel"
                ) as mock_delete_channel,
                patch(
                    "src.cogs.role_panel.delete_role_panels_by_channel",
                    return_value=0,
                ),
            ):
                await cog.on_guild_channel_delete(voice_channel)

        # on_guild_channel_delete は常に削除を試みる
        mock_delete_channel.assert_called_once()

    # -------------------------------------------------------------------------
    # on_raw_message_delete テスト
    # -------------------------------------------------------------------------

    async def test_on_raw_message_delete_removes_role_panel(
        self, mock_bot: MagicMock
    ) -> None:
        """on_raw_message_delete がロールパネルを削除する。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        payload = MagicMock(spec=discord.RawMessageDeleteEvent)
        payload.message_id = 12345
        payload.channel_id = 67890

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.delete_role_panel_by_message_id",
                return_value=True,
            ) as mock_delete:
                await cog.on_raw_message_delete(payload)

        mock_delete.assert_called_once_with(mock_db, "12345")

    async def test_on_raw_message_delete_no_panel_found(
        self, mock_bot: MagicMock
    ) -> None:
        """on_raw_message_delete でパネルが見つからない場合も正常終了。"""
        from src.cogs.role_panel import RolePanelCog

        cog = RolePanelCog(mock_bot)

        payload = MagicMock(spec=discord.RawMessageDeleteEvent)
        payload.message_id = 99999
        payload.channel_id = 67890

        with patch("src.cogs.role_panel.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.cogs.role_panel.delete_role_panel_by_message_id",
                return_value=False,
            ) as mock_delete:
                await cog.on_raw_message_delete(payload)

        mock_delete.assert_called_once_with(mock_db, "99999")


# =============================================================================
# RolePanelCreateModal Tests
# =============================================================================


class TestRolePanelCreateModal:
    """RolePanelCreateModal のテスト。"""

    async def test_on_submit_no_guild_error(self) -> None:
        """ギルド外でエラーを返す。"""
        from src.ui.role_panel_view import RolePanelCreateModal

        modal = RolePanelCreateModal(
            panel_type="button", channel_id=123, remove_reaction=False
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await modal.on_submit(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ使用できます" in call_args.args[0]

    async def test_on_submit_no_channel_error(self) -> None:
        """チャンネルが見つからない場合エラーを返す。"""
        from src.ui.role_panel_view import RolePanelCreateModal

        modal = RolePanelCreateModal(
            panel_type="button", channel_id=123, remove_reaction=False
        )
        # TextInput の値をセット
        modal.panel_title._value = "Test Panel"
        modal.description._value = "Test Description"

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 456
        interaction.guild.get_channel.return_value = None  # チャンネルなし
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_panel = RolePanel(
            id=1, guild_id="456", channel_id="123", panel_type="button", title="Test"
        )

        with patch("src.ui.role_panel_view.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.services.db_service.create_role_panel"
            ) as mock_create_panel:
                mock_create_panel.return_value = mock_panel

                await modal.on_submit(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "チャンネルが見つかりませんでした" in call_args.args[0]

    async def test_on_submit_button_panel_success(self) -> None:
        """ボタン式パネル作成が成功する。"""
        from src.ui.role_panel_view import RolePanelCreateModal

        modal = RolePanelCreateModal(
            panel_type="button", channel_id=123, remove_reaction=False
        )
        # TextInput の値をセット
        modal.panel_title._value = "Test Panel"
        modal.description._value = "Test Description"

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123
        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.id = 789
        mock_channel.send = AsyncMock(return_value=mock_msg)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 456
        interaction.guild.get_channel.return_value = mock_channel
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_panel = RolePanel(
            id=1, guild_id="456", channel_id="123", panel_type="button", title="Test"
        )

        with patch("src.ui.role_panel_view.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.services.db_service.create_role_panel"
            ) as mock_create_panel:
                mock_create_panel.return_value = mock_panel

                with patch(
                    "src.services.db_service.update_role_panel"
                ) as mock_update_panel:
                    mock_update_panel.return_value = mock_panel

                    await modal.on_submit(interaction)

        # チャンネルにメッセージが送信されたことを確認
        mock_channel.send.assert_awaited_once()
        # 成功メッセージが返されたことを確認
        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "作成しました" in call_args.args[0]

    async def test_on_submit_reaction_panel_success(self) -> None:
        """リアクション式パネル作成が成功する。"""
        from src.ui.role_panel_view import RolePanelCreateModal

        modal = RolePanelCreateModal(
            panel_type="reaction", channel_id=123, remove_reaction=True
        )
        # TextInput の値をセット
        modal.panel_title._value = "Test Panel"
        modal.description._value = ""  # 説明なし

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123
        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.id = 789
        mock_channel.send = AsyncMock(return_value=mock_msg)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 456
        interaction.guild.get_channel.return_value = mock_channel
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.response = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_panel = RolePanel(
            id=1,
            guild_id="456",
            channel_id="123",
            panel_type="reaction",
            title="Test",
            remove_reaction=True,
        )

        with patch("src.ui.role_panel_view.async_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.services.db_service.create_role_panel"
            ) as mock_create_panel:
                mock_create_panel.return_value = mock_panel

                with patch(
                    "src.services.db_service.update_role_panel"
                ) as mock_update_panel:
                    mock_update_panel.return_value = mock_panel

                    await modal.on_submit(interaction)

        # チャンネルにメッセージが送信されたことを確認
        mock_channel.send.assert_awaited_once()
        # 成功メッセージが返されたことを確認
        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        assert "作成しました" in call_args.args[0]
        # created_panel がセットされたことを確認
        assert modal.created_panel == mock_panel


# ===========================================================================
# 重複排除テーブルによる重複防止テスト
# ===========================================================================
