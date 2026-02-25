"""Tests for EphemeralVCBot."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord
import pytest
from discord.ext import commands

from src.bot import EphemeralVCBot, make_activity

# ===========================================================================
# __init__ テスト
# ===========================================================================


class TestBotInit:
    """Tests for EphemeralVCBot constructor."""

    def test_activity_set_in_constructor(self) -> None:
        """アクティビティがコンストラクタで設定されている。"""
        bot = EphemeralVCBot()
        # Bot の activity プロパティは接続後に有効だが、
        # _connection.activity に初期値として設定されている
        # (pycord の実装に依存するため、より安定したテストとして
        # Bot の初期化時に渡された引数を間接的に確認する)
        assert bot.activity is not None
        assert isinstance(bot.activity, discord.Game)
        assert "お菓子" in bot.activity.name


# ===========================================================================
# setup_hook テスト
# ===========================================================================


class TestSetupHook:
    """Tests for EphemeralVCBot.setup_hook."""

    def _make_bot(self) -> EphemeralVCBot:
        """setup_hook テスト用のモック済み Bot を作成する。"""
        bot = EphemeralVCBot()
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]
        bot.add_view = MagicMock()  # type: ignore[method-assign]
        return bot

    def _mock_session_factory(self) -> MagicMock:
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        return mock_factory

    @patch("src.bot.async_session")
    async def test_loads_all_cogs(self, mock_session_factory: MagicMock) -> None:
        """5つの Cog がすべて読み込まれる。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        bot = self._make_bot()
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with (
            patch.object(
                type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
            ),
            patch(
                "src.bot.get_all_voice_sessions",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await bot.setup_hook()

        assert bot.load_extension.await_count == 9
        bot.load_extension.assert_any_await("src.cogs.voice")
        bot.load_extension.assert_any_await("src.cogs.admin")
        bot.load_extension.assert_any_await("src.cogs.health")
        bot.load_extension.assert_any_await("src.cogs.bump")
        bot.load_extension.assert_any_await("src.cogs.sticky")
        bot.load_extension.assert_any_await("src.cogs.role_panel")
        bot.load_extension.assert_any_await("src.cogs.autoban")
        bot.load_extension.assert_any_await("src.cogs.ticket")
        bot.load_extension.assert_any_await("src.cogs.join_role")

    @patch("src.bot.async_session")
    async def test_syncs_commands(self, mock_session_factory: MagicMock) -> None:
        """スラッシュコマンドが Discord に同期される。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        bot = self._make_bot()
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with (
            patch.object(
                type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
            ),
            patch(
                "src.bot.get_all_voice_sessions",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await bot.setup_hook()

        mock_tree.sync.assert_awaited_once()

    @patch("src.bot.async_session")
    async def test_restores_views(self, mock_session_factory: MagicMock) -> None:
        """DB のセッションから View が復元される。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        vs1 = MagicMock()
        vs1.id = 1
        vs1.channel_id = "100"
        vs1.is_locked = False
        vs1.is_hidden = False
        vs2 = MagicMock()
        vs2.id = 2
        vs2.channel_id = "200"
        vs2.is_locked = True
        vs2.is_hidden = True

        bot = self._make_bot()
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with (
            patch.object(
                type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
            ),
            patch(
                "src.bot.get_all_voice_sessions",
                new_callable=AsyncMock,
                return_value=[vs1, vs2],
            ),
        ):
            await bot.setup_hook()

        assert bot.add_view.call_count == 2

    @patch("src.bot.async_session")
    async def test_restores_views_with_nsfw_channel(
        self, mock_session_factory: MagicMock
    ) -> None:
        """NSFW チャンネルの場合、is_nsfw=True で View が復元される。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        vs = MagicMock()
        vs.id = 1
        vs.channel_id = "100"
        vs.is_locked = False
        vs.is_hidden = False

        # NSFW チャンネルをモック
        nsfw_channel = MagicMock(spec=discord.VoiceChannel)
        nsfw_channel.nsfw = True

        bot = self._make_bot()
        bot.get_channel = MagicMock(return_value=nsfw_channel)
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with (
            patch.object(
                type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
            ),
            patch(
                "src.bot.get_all_voice_sessions",
                new_callable=AsyncMock,
                return_value=[vs],
            ),
            patch("src.bot.ControlPanelView") as mock_view_class,
        ):
            await bot.setup_hook()

        # is_nsfw=True で View が作成されることを確認
        mock_view_class.assert_called_once_with(1, False, False, True)
        bot.get_channel.assert_called_once_with(100)

    @patch("src.bot.async_session")
    async def test_no_views_when_no_sessions(
        self, mock_session_factory: MagicMock
    ) -> None:
        """セッションがない場合、View は登録されない。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        bot = self._make_bot()
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with (
            patch.object(
                type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
            ),
            patch(
                "src.bot.get_all_voice_sessions",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await bot.setup_hook()

        bot.add_view.assert_not_called()

    @patch("src.bot.async_session")
    async def test_extension_load_error_raises(
        self, mock_session_factory: MagicMock
    ) -> None:
        """Cog 読み込みエラー時は例外が発生する。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        bot = EphemeralVCBot()
        bot.load_extension = AsyncMock(  # type: ignore[method-assign]
            side_effect=commands.ExtensionError(message="Test error", name="test_ext")
        )
        bot.add_view = MagicMock()  # type: ignore[method-assign]
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with (
            patch.object(
                type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
            ),
            patch(
                "src.bot.get_all_voice_sessions",
                new_callable=AsyncMock,
                return_value=[],
            ),
            pytest.raises(commands.ExtensionError),
        ):
            await bot.setup_hook()

    @patch("src.bot.async_session")
    async def test_non_voice_channel_logs_warning(
        self, mock_session_factory: MagicMock
    ) -> None:
        """チャンネルが VoiceChannel でない場合、警告がログに出力される。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        vs = MagicMock()
        vs.id = 1
        vs.channel_id = "100"
        vs.is_locked = False
        vs.is_hidden = False

        # TextChannel (VoiceChannel ではない)
        text_channel = MagicMock(spec=discord.TextChannel)

        bot = EphemeralVCBot()
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]
        bot.add_view = MagicMock()  # type: ignore[method-assign]
        bot.get_channel = MagicMock(return_value=text_channel)
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()

        with (
            patch.object(
                type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
            ),
            patch(
                "src.bot.get_all_voice_sessions",
                new_callable=AsyncMock,
                return_value=[vs],
            ),
            patch("src.bot.ControlPanelView") as mock_view_class,
        ):
            await bot.setup_hook()

        # is_nsfw=False (デフォルト) で View が作成される
        mock_view_class.assert_called_once_with(1, False, False, False)

    @patch("src.bot.async_session")
    async def test_tree_sync_error_raises(
        self, mock_session_factory: MagicMock
    ) -> None:
        """スラッシュコマンド同期エラー時は例外が発生する。"""
        mock_session_factory.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock()
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        bot = EphemeralVCBot()
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]
        bot.add_view = MagicMock()  # type: ignore[method-assign]
        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "Sync failed")
        )

        with (
            patch.object(
                type(bot), "tree", new_callable=PropertyMock, return_value=mock_tree
            ),
            patch(
                "src.bot.get_all_voice_sessions",
                new_callable=AsyncMock,
                return_value=[],
            ),
            pytest.raises(discord.HTTPException),
        ):
            await bot.setup_hook()


# ===========================================================================
# on_ready テスト
# ===========================================================================


class TestOnReady:
    """Tests for EphemeralVCBot.on_ready."""

    async def test_sets_activity(self) -> None:
        """ステータスが設定される。"""
        bot = EphemeralVCBot()
        bot.change_presence = AsyncMock()  # type: ignore[method-assign]

        mock_user = MagicMock()
        mock_user.id = 12345

        with patch.object(
            type(bot), "user", new_callable=PropertyMock, return_value=mock_user
        ):
            await bot.on_ready()

        bot.change_presence.assert_awaited_once()
        activity = bot.change_presence.call_args[1]["activity"]
        assert isinstance(activity, discord.Game)
        assert "お菓子" in activity.name

    async def test_handles_no_user(self) -> None:
        """self.user が None でもエラーにならない。"""
        bot = EphemeralVCBot()
        bot.change_presence = AsyncMock()  # type: ignore[method-assign]

        with patch.object(
            type(bot), "user", new_callable=PropertyMock, return_value=None
        ):
            await bot.on_ready()

        bot.change_presence.assert_awaited_once()

    async def test_loads_activity_from_db(self) -> None:
        """DB にアクティビティが保存されている場合、それを使用する。"""
        bot = EphemeralVCBot()
        bot.change_presence = AsyncMock()  # type: ignore[method-assign]

        mock_user = MagicMock()
        mock_user.id = 12345

        mock_bot_activity = MagicMock()
        mock_bot_activity.activity_type = "listening"
        mock_bot_activity.activity_text = "音楽"

        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(
                type(bot), "user", new_callable=PropertyMock, return_value=mock_user
            ),
            patch("src.bot.async_session", mock_factory),
            patch(
                "src.bot.get_bot_activity",
                new_callable=AsyncMock,
                return_value=mock_bot_activity,
            ),
        ):
            await bot.on_ready()

        bot.change_presence.assert_awaited_once()
        activity = bot.change_presence.call_args[1]["activity"]
        assert isinstance(activity, discord.Activity)
        assert activity.type == discord.ActivityType.listening
        assert activity.name == "音楽"

    async def test_uses_default_when_db_has_no_record(self) -> None:
        """DB にレコードがない場合はデフォルトのアクティビティを使用する。"""
        bot = EphemeralVCBot()
        bot.change_presence = AsyncMock()  # type: ignore[method-assign]

        mock_user = MagicMock()
        mock_user.id = 12345

        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(
                type(bot), "user", new_callable=PropertyMock, return_value=mock_user
            ),
            patch("src.bot.async_session", mock_factory),
            patch(
                "src.bot.get_bot_activity",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await bot.on_ready()

        bot.change_presence.assert_awaited_once()
        activity = bot.change_presence.call_args[1]["activity"]
        assert isinstance(activity, discord.Game)
        assert "お菓子" in activity.name

    async def test_handles_db_error_in_on_ready(self) -> None:
        """DB エラーが発生してもデフォルトのアクティビティが使用される。"""
        bot = EphemeralVCBot()
        bot.change_presence = AsyncMock()  # type: ignore[method-assign]

        mock_user = MagicMock()
        mock_user.id = 12345

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("DB error")
        )
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(
                type(bot), "user", new_callable=PropertyMock, return_value=mock_user
            ),
            patch("src.bot.async_session", mock_factory),
        ):
            await bot.on_ready()

        bot.change_presence.assert_awaited_once()
        activity = bot.change_presence.call_args[1]["activity"]
        assert isinstance(activity, discord.Game)
        assert "お菓子" in activity.name


# ===========================================================================
# make_activity テスト
# ===========================================================================


class TestMakeActivity:
    """Tests for make_activity helper."""

    def test_playing_returns_game(self) -> None:
        """playing タイプは discord.Game を返す。"""
        result = make_activity("playing", "テストゲーム")
        assert isinstance(result, discord.Game)
        assert result.name == "テストゲーム"

    def test_listening_returns_activity(self) -> None:
        """listening タイプは discord.Activity を返す。"""
        result = make_activity("listening", "音楽")
        assert isinstance(result, discord.Activity)
        assert result.type == discord.ActivityType.listening
        assert result.name == "音楽"

    def test_watching_returns_activity(self) -> None:
        """watching タイプは discord.Activity を返す。"""
        result = make_activity("watching", "動画")
        assert isinstance(result, discord.Activity)
        assert result.type == discord.ActivityType.watching
        assert result.name == "動画"

    def test_competing_returns_activity(self) -> None:
        """competing タイプは discord.Activity を返す。"""
        result = make_activity("competing", "大会")
        assert isinstance(result, discord.Activity)
        assert result.type == discord.ActivityType.competing
        assert result.name == "大会"

    def test_unknown_type_defaults_to_game(self) -> None:
        """不明なタイプは discord.Game (playing) にフォールバックする。"""
        result = make_activity("unknown", "テスト")
        assert isinstance(result, discord.Game)
        assert result.name == "テスト"
