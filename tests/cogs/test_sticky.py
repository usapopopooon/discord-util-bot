"""Tests for StickyCog (sticky message feature)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands
from faker import Faker

from src.cogs.sticky import (
    StickyCog,
    StickyEmbedModal,
    StickySetModal,
    StickyTextModal,
    StickyTypeSelect,
    StickyTypeView,
)
from src.utils import clear_resource_locks

fake = Faker("ja_JP")


@pytest.fixture(autouse=True)
def _clear_locks() -> None:
    """Clear resource locks before each test."""
    clear_resource_locks()


# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog(bot_user_id: int = 99999) -> StickyCog:
    """Create a StickyCog with a mock bot."""
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock()
    bot.user.id = bot_user_id
    return StickyCog(bot)


def _make_message(
    *,
    author_id: int = 12345,
    channel_id: int = 456,
    guild_id: int = 789,
    is_bot: bool = False,
) -> MagicMock:
    """Create a mock Discord message."""
    message = MagicMock(spec=discord.Message)
    message.author = MagicMock()
    message.author.id = author_id
    message.author.bot = is_bot
    message.channel = MagicMock()
    message.channel.id = channel_id
    message.channel.send = AsyncMock()
    message.channel.fetch_message = AsyncMock()
    message.guild = MagicMock()
    message.guild.id = guild_id
    return message


def _make_sticky(
    *,
    channel_id: str = "456",
    guild_id: str = "789",
    message_id: str | None = "999",
    title: str = "Test Title",
    description: str = "Test Description",
    color: int | None = 0xFF0000,
    cooldown_seconds: int = 5,
    last_posted_at: datetime | None = None,
    message_type: str = "embed",
) -> MagicMock:
    """Create a mock StickyMessage."""
    sticky = MagicMock()
    sticky.channel_id = channel_id
    sticky.guild_id = guild_id
    sticky.message_id = message_id
    sticky.title = title
    sticky.description = description
    sticky.color = color
    sticky.cooldown_seconds = cooldown_seconds
    sticky.last_posted_at = last_posted_at
    sticky.message_type = message_type
    return sticky


def _make_interaction(
    *,
    guild_id: int = 789,
    channel_id: int = 456,
) -> MagicMock:
    """Create a mock Discord interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock()
    interaction.guild.id = guild_id
    interaction.channel = MagicMock()
    interaction.channel.id = channel_id
    interaction.channel.send = AsyncMock()
    interaction.channel_id = channel_id
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    return interaction


# ---------------------------------------------------------------------------
# _build_embed テスト
# ---------------------------------------------------------------------------


class TestBuildEmbed:
    """Tests for _build_embed method."""

    def test_builds_embed_with_all_params(self) -> None:
        """全てのパラメータを指定して embed を作成する。"""
        cog = _make_cog()
        embed = cog._build_embed("Title", "Description", 0xFF0000)

        assert embed.title == "Title"
        assert embed.description == "Description"
        assert embed.color == discord.Color(0xFF0000)

    def test_uses_default_color_when_none(self) -> None:
        """色が None の場合はデフォルト色を使用する。"""
        cog = _make_cog()
        embed = cog._build_embed("Title", "Description", None)

        assert embed.color == discord.Color(0x85E7AD)


# ---------------------------------------------------------------------------
# on_message テスト
# ---------------------------------------------------------------------------


class TestOnMessage:
    """Tests for on_message listener."""

    async def test_ignores_own_bot_messages(self) -> None:
        """自分自身の Bot メッセージは無視する（無限ループ防止）。"""
        bot_user_id = 99999
        cog = _make_cog(bot_user_id=bot_user_id)
        # メッセージの author.id を bot.user.id と同じにする
        message = _make_message(author_id=bot_user_id, is_bot=True)

        with patch("src.cogs.sticky.get_sticky_message") as mock_get:
            await cog.on_message(message)

        mock_get.assert_not_called()

    async def test_triggers_on_other_bot_messages(self) -> None:
        """他の Bot のメッセージでも sticky を再投稿する。"""
        cog = _make_cog(bot_user_id=99999)
        # 別の bot からのメッセージ
        message = _make_message(author_id=88888, is_bot=True)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        sticky = _make_sticky()

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch("src.cogs.sticky.get_sticky_message", return_value=sticky),
        ):
            await cog.on_message(message)

        # タスクがスケジュールされていることを確認
        channel_id = str(message.channel.id)
        assert channel_id in cog._pending_tasks

    async def test_triggers_on_bot_embed_messages(self) -> None:
        """他の Bot の embed メッセージでも sticky を再投稿する。"""
        cog = _make_cog(bot_user_id=99999)
        # 別の bot からの embed 付きメッセージ
        message = _make_message(author_id=88888, is_bot=True)
        message.embeds = [MagicMock()]  # embed が含まれている

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        sticky = _make_sticky()

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch("src.cogs.sticky.get_sticky_message", return_value=sticky),
        ):
            await cog.on_message(message)

        # タスクがスケジュールされていることを確認
        channel_id = str(message.channel.id)
        assert channel_id in cog._pending_tasks

    async def test_handles_bot_user_none(self) -> None:
        """bot.user が None の場合でもエラーにならない。"""
        cog = _make_cog()
        cog.bot.user = None  # bot.user を None に設定
        message = _make_message(is_bot=True)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        sticky = _make_sticky()

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch("src.cogs.sticky.get_sticky_message", return_value=sticky),
        ):
            # エラーなく実行される
            await cog.on_message(message)

        # bot.user が None の場合、全てのメッセージが処理される
        channel_id = str(message.channel.id)
        assert channel_id in cog._pending_tasks

    async def test_ignores_dm_messages(self) -> None:
        """DM メッセージは無視する。"""
        cog = _make_cog()
        message = _make_message()
        message.guild = None

        with patch("src.cogs.sticky.get_sticky_message") as mock_get:
            await cog.on_message(message)

        mock_get.assert_not_called()

    async def test_ignores_when_no_sticky_configured(self) -> None:
        """sticky 設定がない場合は無視する。"""
        cog = _make_cog()
        message = _make_message()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.on_message(message)

        # タスクがスケジュールされていない
        assert len(cog._pending_tasks) == 0

    async def test_schedules_delayed_repost(self) -> None:
        """メッセージが来たら遅延再投稿をスケジュールする。"""
        cog = _make_cog()
        message = _make_message()

        sticky = _make_sticky(cooldown_seconds=5)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
        ):
            await cog.on_message(message)

        # タスクがスケジュールされている
        assert "456" in cog._pending_tasks
        # クリーンアップ
        cog._pending_tasks["456"].cancel()

    async def test_cancels_existing_task_on_new_message(self) -> None:
        """新しいメッセージが来たら既存のタスクをキャンセルする（デバウンス）。"""
        cog = _make_cog()
        message = _make_message()

        sticky = _make_sticky(cooldown_seconds=5)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
        ):
            # 1回目のメッセージ
            await cog.on_message(message)
            first_task = cog._pending_tasks["456"]

            # 2回目のメッセージ
            await cog.on_message(message)
            second_task = cog._pending_tasks["456"]

        # 1回目のタスクはキャンセルされている
        assert first_task.cancelled()
        # 2回目のタスクが新しく設定されている
        assert first_task is not second_task
        # クリーンアップ
        second_task.cancel()


class TestDelayedRepost:
    """Tests for _delayed_repost method."""

    async def test_reposts_after_delay(self) -> None:
        """遅延後に再投稿する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock(return_value=MagicMock(id=1234567890))
        channel.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        sticky = _make_sticky()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await cog._delayed_repost(channel, "456", 5)

        mock_sleep.assert_called_once_with(5)
        channel.send.assert_called_once()

    async def test_deletes_old_message_before_repost(self) -> None:
        """再投稿前に古いメッセージを削除する。"""
        cog = _make_cog()
        channel = MagicMock()
        new_msg = MagicMock(id=1234567890)
        channel.send = AsyncMock(return_value=new_msg)

        old_msg = MagicMock()
        old_msg.delete = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=old_msg)

        sticky = _make_sticky(message_id="999")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        old_msg.delete.assert_called_once()
        channel.send.assert_called_once()

    async def test_does_nothing_if_cancelled(self) -> None:
        """キャンセルされた場合は何もしない。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock()

        with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
            await cog._delayed_repost(channel, "456", 5)

        channel.send.assert_not_called()

    async def test_does_nothing_if_sticky_deleted(self) -> None:
        """sticky が削除されていた場合は何もしない。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        channel.send.assert_not_called()

    async def test_skips_repost_when_message_not_found(self) -> None:
        """メッセージが既に削除されていた場合は再投稿せず、DB から削除する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock()
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        sticky = _make_sticky(message_id="999")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.delete_sticky_message",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # NotFound の場合、再投稿しない
        channel.send.assert_not_called()
        # DB から削除される
        mock_delete.assert_called_once()

    async def test_skips_repost_when_no_message_id(self) -> None:
        """message_id がない場合は再投稿せず、DB から削除する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock()

        sticky = _make_sticky(message_id=None)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.delete_sticky_message",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # message_id がない場合、再投稿しない
        channel.send.assert_not_called()
        # DB から削除される
        mock_delete.assert_called_once()

    async def test_skips_repost_on_http_exception(self) -> None:
        """HTTP エラーが発生した場合は再投稿せず、DB から削除する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock()
        channel.fetch_message = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "")
        )

        sticky = _make_sticky(message_id="999")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.delete_sticky_message",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # HTTPException の場合も再投稿しない
        channel.send.assert_not_called()
        # DB から削除される
        mock_delete.assert_called_once()

    async def test_updates_db_after_successful_repost(self) -> None:
        """再投稿成功後に DB を更新する。"""
        cog = _make_cog()
        channel = MagicMock()
        new_msg = MagicMock(id=1234567890)
        channel.send = AsyncMock(return_value=new_msg)

        old_msg = MagicMock()
        old_msg.delete = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=old_msg)

        sticky = _make_sticky(message_id="999")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ) as mock_update,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # DB が新しいメッセージ ID で更新される
        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][1] == "456"  # channel_id
        assert call_args[0][2] == "1234567890"  # new message_id

    async def test_handles_send_failure(self) -> None:
        """メッセージ送信に失敗しても例外を投げない。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))

        old_msg = MagicMock()
        old_msg.delete = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=old_msg)

        sticky = _make_sticky(message_id="999")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ) as mock_update,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            # 例外が発生しないことを確認
            await cog._delayed_repost(channel, "456", 5)

        # 送信失敗時は DB 更新されない
        mock_update.assert_not_called()

    async def test_removes_task_from_pending_after_completion(self) -> None:
        """完了後に _pending_tasks からタスクが削除される。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock(return_value=MagicMock(id=123))
        channel.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        sticky = _make_sticky()

        # タスクを事前に登録
        cog._pending_tasks["456"] = MagicMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # タスクが削除されている
        assert "456" not in cog._pending_tasks

    async def test_removes_task_from_pending_on_cancel(self) -> None:
        """キャンセル時にも _pending_tasks からタスクが削除される。"""
        cog = _make_cog()
        channel = MagicMock()

        # タスクを事前に登録
        cog._pending_tasks["456"] = MagicMock()

        with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
            await cog._delayed_repost(channel, "456", 5)

        # タスクが削除されている
        assert "456" not in cog._pending_tasks


class TestCogUnload:
    """Tests for cog_unload method."""

    async def test_cancels_pending_tasks(self) -> None:
        """アンロード時に保留中のタスクをキャンセルする。"""
        cog = _make_cog()

        # ダミーのタスクを追加
        async def dummy() -> None:
            await asyncio.sleep(100)

        task = asyncio.create_task(dummy())
        cog._pending_tasks["456"] = task

        await cog.cog_unload()

        # タスクがキャンセル中または完了していることを確認
        assert task.cancelling() > 0 or task.cancelled()
        assert len(cog._pending_tasks) == 0


# ---------------------------------------------------------------------------
# スラッシュコマンドテスト
# ---------------------------------------------------------------------------


class TestStickySetCommand:
    """Tests for /sticky set command."""

    async def test_requires_guild(self) -> None:
        """ギルド外では使用できない。"""
        cog = _make_cog()
        interaction = _make_interaction()
        interaction.guild = None

        await cog.sticky_set.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ" in call_args[0][0]

    async def test_shows_type_selector(self) -> None:
        """ギルド内でタイプセレクターを表示する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        await cog.sticky_set.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        call_kwargs = interaction.response.send_message.call_args[1]
        assert "view" in call_kwargs
        assert call_kwargs["ephemeral"] is True


class TestStickySetModal:
    """Tests for StickySetModal."""

    def _make_modal(self) -> StickySetModal:
        """Create a StickySetModal with a mock cog."""
        cog = _make_cog()
        modal = StickySetModal(cog)
        return modal

    async def test_requires_guild(self) -> None:
        """ギルド外では使用できない。"""
        modal = self._make_modal()
        interaction = _make_interaction()
        interaction.guild = None

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "5"

        await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ" in call_args[0][0]

    async def test_creates_sticky_message(self) -> None:
        """sticky メッセージを作成する。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        mock_create.assert_called_once()
        interaction.response.send_message.assert_called_once()

    async def test_parses_hex_color(self) -> None:
        """16進数の色をパースする。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = "FF0000"
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["color"] == 0xFF0000

    async def test_rejects_invalid_color(self) -> None:
        """無効な色形式はエラーを返す。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = "invalid"
        modal.delay._value = "5"

        await modal.on_submit(interaction)

        call_args = interaction.response.send_message.call_args
        assert "無効な色形式" in call_args[0][0]

    async def test_uses_delay_parameter(self) -> None:
        """delay パラメータを使用する。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "10"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 10

    async def test_rejects_invalid_delay(self) -> None:
        """無効な遅延値はエラーを返す。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "abc"

        await modal.on_submit(interaction)

        call_args = interaction.response.send_message.call_args
        assert "無効な遅延値" in call_args[0][0]

    async def test_multiline_description(self) -> None:
        """改行を含む説明文を処理できる。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with multiline description
        modal.sticky_title._value = "Title"
        modal.description._value = "Line 1\nLine 2\nLine 3"
        modal.color._value = ""
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["description"] == "Line 1\nLine 2\nLine 3"

    async def test_delay_minimum_boundary(self) -> None:
        """遅延の最小値は1秒に制限される。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with delay below minimum
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "0"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 1

    async def test_delay_maximum_boundary(self) -> None:
        """遅延の最大値は3600秒に制限される。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with delay above maximum
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "9999"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 3600

    async def test_color_with_hash_prefix(self) -> None:
        """# プレフィックス付きの色をパースする。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = "#00FF00"
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["color"] == 0x00FF00

    async def test_handles_send_failure(self) -> None:
        """メッセージ送信に失敗しても例外を投げない。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # send が例外を投げる
        interaction.channel.send = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "")
        )

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            # 例外が発生しないことを確認
            await modal.on_submit(interaction)

        # 送信失敗時は DB 更新されない
        mock_update.assert_not_called()

    async def test_empty_delay_defaults_to_five(self) -> None:
        """空の遅延値はデフォルト5秒になる。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with empty delay
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = ""

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 5


class TestStickyRemoveCommand:
    """Tests for /sticky remove command."""

    async def test_requires_guild(self) -> None:
        """ギルド外では使用できない。"""
        cog = _make_cog()
        interaction = _make_interaction()
        interaction.guild = None

        await cog.sticky_remove.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ" in call_args[0][0]

    async def test_shows_error_when_not_configured(self) -> None:
        """設定がない場合はエラーを表示する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.sticky_remove.callback(cog, interaction)

        call_args = interaction.response.send_message.call_args
        assert "設定されていません" in call_args[0][0]

    async def test_removes_sticky_message(self) -> None:
        """sticky メッセージを削除する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        sticky = _make_sticky()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        old_message = MagicMock()
        old_message.delete = AsyncMock()
        interaction.channel.fetch_message = AsyncMock(return_value=old_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.delete_sticky_message",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            await cog.sticky_remove.callback(cog, interaction)

        mock_delete.assert_called_once()
        old_message.delete.assert_called_once()

    async def test_cancels_pending_task(self) -> None:
        """保留中のタスクをキャンセルする。"""
        cog = _make_cog()
        interaction = _make_interaction()

        # ダミーのタスクを追加
        async def dummy() -> None:
            await asyncio.sleep(100)

        task = asyncio.create_task(dummy())
        cog._pending_tasks["456"] = task

        sticky = _make_sticky()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        old_message = MagicMock()
        old_message.delete = AsyncMock()
        interaction.channel.fetch_message = AsyncMock(return_value=old_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.delete_sticky_message",
                new_callable=AsyncMock,
            ),
        ):
            await cog.sticky_remove.callback(cog, interaction)

        # タスクがキャンセル中または完了していることを確認
        assert task.cancelling() > 0 or task.cancelled()
        assert "456" not in cog._pending_tasks


class TestStickyStatusCommand:
    """Tests for /sticky status command."""

    async def test_requires_guild(self) -> None:
        """ギルド外では使用できない。"""
        cog = _make_cog()
        interaction = _make_interaction()
        interaction.guild = None

        await cog.sticky_status.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ" in call_args[0][0]

    async def test_shows_not_configured(self) -> None:
        """設定がない場合は未設定と表示する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.sticky_status.callback(cog, interaction)

        call_args = interaction.response.send_message.call_args
        assert "設定されていません" in call_args[0][0]

    async def test_shows_configuration(self) -> None:
        """設定がある場合は詳細を表示する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        sticky = _make_sticky()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
        ):
            await cog.sticky_status.callback(cog, interaction)

        call_kwargs = interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        assert embed.title == "📌 Sticky メッセージ設定"

    async def test_shows_text_type(self) -> None:
        """テキストタイプの設定を表示する。"""
        cog = _make_cog()
        interaction = _make_interaction()

        sticky = _make_sticky(message_type="text", title="", color=None)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
        ):
            await cog.sticky_status.callback(cog, interaction)

        call_kwargs = interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        # 種類フィールドがテキストになっている
        type_field = next(f for f in embed.fields if f.name == "種類")
        assert type_field.value == "テキスト"


# ---------------------------------------------------------------------------
# StickyTextModal テスト
# ---------------------------------------------------------------------------


class TestStickyTextModal:
    """Tests for StickyTextModal."""

    def _make_modal(self) -> StickyTextModal:
        """Create a StickyTextModal with a mock cog."""
        cog = _make_cog()
        modal = StickyTextModal(cog)
        return modal

    async def test_requires_guild(self) -> None:
        """ギルド外では使用できない。"""
        modal = self._make_modal()
        interaction = _make_interaction()
        interaction.guild = None

        # Set modal values
        modal.content._value = "Test content"
        modal.delay._value = "5"

        await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内でのみ" in call_args[0][0]

    async def test_creates_sticky_message(self) -> None:
        """テキスト sticky メッセージを作成する。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.content._value = "Test content"
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["message_type"] == "text"
        assert call_kwargs["title"] == ""
        assert call_kwargs["description"] == "Test content"
        interaction.response.send_message.assert_called_once()

    async def test_uses_delay_parameter(self) -> None:
        """delay パラメータを使用する。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.content._value = "Test content"
        modal.delay._value = "10"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 10

    async def test_rejects_invalid_delay(self) -> None:
        """無効な遅延値はエラーを返す。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.content._value = "Test content"
        modal.delay._value = "abc"

        await modal.on_submit(interaction)

        call_args = interaction.response.send_message.call_args
        assert "無効な遅延値" in call_args[0][0]

    async def test_multiline_content(self) -> None:
        """改行を含むコンテンツを処理できる。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with multiline content
        modal.content._value = "Line 1\nLine 2\nLine 3"
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["description"] == "Line 1\nLine 2\nLine 3"

    async def test_delay_minimum_boundary(self) -> None:
        """遅延の最小値は1秒に制限される。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with delay below minimum
        modal.content._value = "Test content"
        modal.delay._value = "0"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 1

    async def test_delay_maximum_boundary(self) -> None:
        """遅延の最大値は3600秒に制限される。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with delay above maximum
        modal.content._value = "Test content"
        modal.delay._value = "9999"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 3600

    async def test_handles_send_failure(self) -> None:
        """メッセージ送信に失敗しても例外を投げない。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.content._value = "Test content"
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # send が例外を投げる
        interaction.channel.send = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "")
        )

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            # 例外が発生しないことを確認
            await modal.on_submit(interaction)

        # 送信失敗時は DB 更新されない
        mock_update.assert_not_called()

    async def test_empty_delay_defaults_to_five(self) -> None:
        """空の遅延値はデフォルト5秒になる。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values with empty delay
        modal.content._value = "Test content"
        modal.delay._value = ""

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == 5


# ---------------------------------------------------------------------------
# StickyTypeSelect テスト
# ---------------------------------------------------------------------------


class TestStickyTypeSelect:
    """Tests for StickyTypeSelect."""

    async def test_select_embed_opens_embed_modal(self) -> None:
        """Embed を選択すると StickyEmbedModal が開く。"""
        cog = _make_cog()
        select = StickyTypeSelect(cog)
        interaction = _make_interaction()
        interaction.response.send_modal = AsyncMock()

        select._values = ["embed"]

        await select.callback(interaction)

        interaction.response.send_modal.assert_called_once()
        modal = interaction.response.send_modal.call_args[0][0]
        assert isinstance(modal, StickyEmbedModal)

    async def test_select_text_opens_text_modal(self) -> None:
        """テキストを選択すると StickyTextModal が開く。"""
        cog = _make_cog()
        select = StickyTypeSelect(cog)
        interaction = _make_interaction()
        interaction.response.send_modal = AsyncMock()

        select._values = ["text"]

        await select.callback(interaction)

        interaction.response.send_modal.assert_called_once()
        modal = interaction.response.send_modal.call_args[0][0]
        assert isinstance(modal, StickyTextModal)


# ---------------------------------------------------------------------------
# StickyTypeView テスト
# ---------------------------------------------------------------------------


class TestStickyTypeView:
    """Tests for StickyTypeView."""

    async def test_view_has_select_item(self) -> None:
        """View に StickyTypeSelect が含まれている。"""
        cog = _make_cog()
        view = StickyTypeView(cog)

        assert len(view.children) == 1
        assert isinstance(view.children[0], StickyTypeSelect)

    async def test_view_timeout(self) -> None:
        """View のタイムアウトが60秒である。"""
        cog = _make_cog()
        view = StickyTypeView(cog)

        assert view.timeout == 60


# ---------------------------------------------------------------------------
# _delayed_repost テキストタイプ テスト
# ---------------------------------------------------------------------------


class TestDelayedRepostTextType:
    """Tests for _delayed_repost with text message type."""

    async def test_reposts_text_message(self) -> None:
        """テキストタイプの場合、テキストメッセージを再投稿する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock(return_value=MagicMock(id=1234567890))
        channel.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        sticky = _make_sticky(message_type="text", description="Test text content")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # テキストとして送信されている（embed ではない）
        channel.send.assert_called_once_with("Test text content")

    async def test_reposts_embed_message(self) -> None:
        """Embed タイプの場合、embed メッセージを再投稿する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock(return_value=MagicMock(id=1234567890))
        channel.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        sticky = _make_sticky(
            message_type="embed",
            title="Test Title",
            description="Test Description",
            color=0xFF0000,
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # embed として送信されている
        channel.send.assert_called_once()
        call_kwargs = channel.send.call_args[1]
        assert "embed" in call_kwargs
        assert call_kwargs["embed"].title == "Test Title"
        assert call_kwargs["embed"].description == "Test Description"


# ---------------------------------------------------------------------------
# StickyEmbedModal message_type テスト
# ---------------------------------------------------------------------------


class TestStickyEmbedModalMessageType:
    """Tests for StickyEmbedModal message_type parameter."""

    def _make_modal(self) -> StickyEmbedModal:
        """Create a StickyEmbedModal with a mock cog."""
        cog = _make_cog()
        modal = StickyEmbedModal(cog)
        return modal

    async def test_creates_sticky_with_embed_type(self) -> None:
        """message_type が embed として保存される。"""
        modal = self._make_modal()
        interaction = _make_interaction()

        # Set modal values
        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        new_message = MagicMock()
        new_message.id = 1234567890
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["message_type"] == "embed"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cog() -> StickyCog:
    """StickyCog フィクスチャ。"""
    return _make_cog()


@pytest.fixture
def interaction() -> MagicMock:
    """Interaction フィクスチャ。"""
    return _make_interaction()


@pytest.fixture
def mock_session() -> MagicMock:
    """Mock session フィクスチャ。"""
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


# ---------------------------------------------------------------------------
# Faker を使ったテスト
# ---------------------------------------------------------------------------


class TestStickyWithFaker:
    """Faker を使ったランダムデータでのテスト。"""

    async def test_embed_modal_with_random_data(
        self, cog: StickyCog, interaction: MagicMock, mock_session: MagicMock
    ) -> None:
        """ランダムなデータで embed sticky を作成する。"""
        modal = StickyEmbedModal(cog)

        # Faker でランダムデータ生成
        title = fake.sentence(nb_words=3)
        description = fake.paragraph(nb_sentences=3)
        delay = str(fake.random_int(min=1, max=60))

        modal.sticky_title._value = title
        modal.description._value = description
        modal.color._value = ""
        modal.delay._value = delay

        new_message = MagicMock()
        new_message.id = fake.random_int(min=100000, max=999999)
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["title"] == title
        assert call_kwargs["description"] == description
        assert call_kwargs["cooldown_seconds"] == int(delay)

    async def test_text_modal_with_random_content(
        self, cog: StickyCog, interaction: MagicMock, mock_session: MagicMock
    ) -> None:
        """ランダムなコンテンツでテキスト sticky を作成する。"""
        modal = StickyTextModal(cog)

        # Faker でランダムデータ生成
        content = fake.text(max_nb_chars=500)
        delay = str(fake.random_int(min=1, max=60))

        modal.content._value = content
        modal.delay._value = delay

        new_message = MagicMock()
        new_message.id = fake.random_int(min=100000, max=999999)
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["description"] == content
        assert call_kwargs["message_type"] == "text"

    async def test_delayed_repost_with_random_sticky(
        self, cog: StickyCog, mock_session: MagicMock
    ) -> None:
        """ランダムな sticky データで再投稿をテストする。"""
        channel = MagicMock()
        channel.send = AsyncMock(return_value=MagicMock(id=fake.random_int()))
        channel.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        # ランダムなタイプを選択
        message_type = fake.random_element(elements=("embed", "text"))
        sticky = _make_sticky(
            message_type=message_type,
            title=fake.sentence() if message_type == "embed" else "",
            description=fake.paragraph(),
            color=(
                fake.random_int(min=0, max=0xFFFFFF)
                if message_type == "embed"
                else None
            ),
            cooldown_seconds=fake.random_int(min=1, max=60),
        )

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, str(fake.random_int()), 5)

        channel.send.assert_called_once()

    @pytest.mark.parametrize("message_type", ["embed", "text"])
    async def test_status_shows_correct_type(
        self,
        cog: StickyCog,
        interaction: MagicMock,
        mock_session: MagicMock,
        message_type: str,
    ) -> None:
        """各メッセージタイプのステータス表示をテストする。"""
        sticky = _make_sticky(
            message_type=message_type,
            title=fake.sentence() if message_type == "embed" else "",
            description=fake.paragraph(),
        )

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
        ):
            await cog.sticky_status.callback(cog, interaction)

        call_kwargs = interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        type_field = next(f for f in embed.fields if f.name == "種類")
        expected = "Embed" if message_type == "embed" else "テキスト"
        assert type_field.value == expected


class TestStickyWithParameterize:
    """pytest.mark.parametrize を使ったテスト。"""

    @pytest.mark.parametrize(
        "delay_input,expected_delay",
        [
            ("1", 1),
            ("5", 5),
            ("60", 60),
            ("3600", 3600),
            ("0", 1),  # 最小値に補正
            ("-5", 1),  # 負の値は最小値に補正
            ("9999", 3600),  # 最大値に補正
        ],
    )
    async def test_embed_modal_delay_boundaries(
        self,
        cog: StickyCog,
        interaction: MagicMock,
        mock_session: MagicMock,
        delay_input: str,
        expected_delay: int,
    ) -> None:
        """遅延値の境界値テスト。"""
        modal = StickyEmbedModal(cog)

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = delay_input

        new_message = MagicMock()
        new_message.id = 12345
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["cooldown_seconds"] == expected_delay

    @pytest.mark.parametrize(
        "color_input,expected_color",
        [
            ("FF0000", 0xFF0000),
            ("00FF00", 0x00FF00),
            ("0000FF", 0x0000FF),
            ("#FF0000", 0xFF0000),
            ("#00ff00", 0x00FF00),
            ("FFFFFF", 0xFFFFFF),
            ("123456", 0x123456),
            ("#ABCDEF", 0xABCDEF),
        ],
    )
    async def test_embed_modal_color_parsing(
        self,
        cog: StickyCog,
        interaction: MagicMock,
        mock_session: MagicMock,
        color_input: str,
        expected_color: int,
    ) -> None:
        """色のパーステスト。"""
        modal = StickyEmbedModal(cog)

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = color_input
        modal.delay._value = "5"

        new_message = MagicMock()
        new_message.id = 12345
        interaction.channel.send = AsyncMock(return_value=new_message)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ) as mock_create,
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["color"] == expected_color


# ---------------------------------------------------------------------------
# 追加テスト: 未カバー行のテスト
# ---------------------------------------------------------------------------


class TestStickyModalChannelBranches:
    """Modal 送信時のチャンネル分岐テスト。"""

    async def test_embed_modal_channel_no_send_method(
        self,
        cog: StickyCog,
        interaction: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """チャンネルに send メソッドがない場合でも正常終了。"""
        modal = StickyEmbedModal(cog)

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "5"

        # send メソッドがないチャンネル
        channel_mock = MagicMock()
        del channel_mock.send  # send メソッドを削除
        interaction.channel = channel_mock

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()

    async def test_text_modal_channel_no_send_method(
        self,
        cog: StickyCog,
        interaction: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """テキストモーダル: チャンネルに send メソッドがない場合でも正常終了。"""
        from src.cogs.sticky import StickyTextModal

        modal = StickyTextModal(cog)

        modal.content._value = "Test content"
        modal.delay._value = "5"

        # send メソッドがないチャンネル
        channel_mock = MagicMock()
        del channel_mock.send
        interaction.channel = channel_mock

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                new_callable=AsyncMock,
            ),
        ):
            await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()


class TestRemoveStickyBranches:
    """sticky_remove の分岐テスト。"""

    @patch("src.cogs.sticky.async_session")
    @patch("src.cogs.sticky.get_sticky_message")
    @patch("src.cogs.sticky.delete_sticky_message")
    async def test_remove_with_not_found_exception(
        self,
        mock_delete: AsyncMock,
        mock_get: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """メッセージが見つからない場合の NotFound 例外処理。"""
        bot = MagicMock(spec=commands.Bot)
        bot.add_view = MagicMock()
        cog = StickyCog(bot)

        sticky = MagicMock()
        sticky.message_id = "456"
        mock_get.return_value = sticky

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock()
        interaction.guild.id = 12345
        interaction.channel = MagicMock()
        interaction.channel_id = 123
        interaction.channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        await cog.sticky_remove.callback(cog, interaction)

        # 削除成功メッセージが送信される
        interaction.response.send_message.assert_called()

    @patch("src.cogs.sticky.async_session")
    @patch("src.cogs.sticky.get_sticky_message")
    @patch("src.cogs.sticky.delete_sticky_message")
    async def test_remove_with_http_exception(
        self,
        mock_delete: AsyncMock,
        mock_get: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """メッセージ削除時の HTTPException 処理。"""
        bot = MagicMock(spec=commands.Bot)
        bot.add_view = MagicMock()
        cog = StickyCog(bot)

        sticky = MagicMock()
        sticky.message_id = "456"
        mock_get.return_value = sticky

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock()
        interaction.guild.id = 12345
        interaction.channel = MagicMock()
        interaction.channel_id = 123
        interaction.channel.fetch_message = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "Error")
        )
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        await cog.sticky_remove.callback(cog, interaction)

        # 削除成功メッセージが送信される
        interaction.response.send_message.assert_called()


class TestSetupWithStickies:
    """setup 関数で sticky が存在する場合のテスト。"""

    @patch("src.cogs.sticky.async_session")
    @patch("src.cogs.sticky.get_all_sticky_messages")
    async def test_setup_logs_existing_stickies(
        self,
        mock_get_all: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """既存の sticky 設定がある場合にログ出力される。"""
        from src.cogs.sticky import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()

        # sticky が存在する場合
        mock_get_all.return_value = [MagicMock(), MagicMock()]

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        await setup(bot)

        bot.add_cog.assert_called_once()
        mock_get_all.assert_called_once()

    async def test_setup_does_not_raise_without_db(self) -> None:
        """DB未接続でも setup が例外を出さずに完了する."""
        from src.cogs.sticky import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()

        # DB モック無しで呼び出しても例外が発生しないことを検証
        await setup(bot)

        bot.add_cog.assert_called_once()


# =============================================================================
# クリーンアップリスナーのテスト
# =============================================================================


class TestOnGuildChannelDelete:
    """on_guild_channel_delete リスナーのテスト。"""

    @patch("src.cogs.sticky.async_session")
    @patch("src.cogs.sticky.delete_sticky_message")
    async def test_deletes_sticky_and_cancels_task(
        self,
        mock_delete: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """チャンネル削除時に sticky を削除し、保留タスクをキャンセルする。"""
        cog = _make_cog()

        # 保留タスクを作成
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()
        cog._pending_tasks["456"] = mock_task

        mock_delete.return_value = True

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 456
        channel.guild = MagicMock()
        channel.guild.id = 789

        await cog.on_guild_channel_delete(channel)

        mock_task.cancel.assert_called_once()
        assert "456" not in cog._pending_tasks
        mock_delete.assert_called_once()

    @patch("src.cogs.sticky.async_session")
    @patch("src.cogs.sticky.delete_sticky_message")
    async def test_handles_no_pending_task(
        self,
        mock_delete: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """保留タスクがない場合も正常に動作する。"""
        cog = _make_cog()

        mock_delete.return_value = True

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 456
        channel.guild = MagicMock()
        channel.guild.id = 789

        await cog.on_guild_channel_delete(channel)

        mock_delete.assert_called_once()

    @patch("src.cogs.sticky.async_session")
    @patch("src.cogs.sticky.delete_sticky_message")
    async def test_handles_no_sticky(
        self,
        mock_delete: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """sticky が存在しない場合も正常に動作する。"""
        cog = _make_cog()

        mock_delete.return_value = False

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 456
        channel.guild = MagicMock()
        channel.guild.id = 789

        await cog.on_guild_channel_delete(channel)

        mock_delete.assert_called_once()


class TestOnGuildRemove:
    """on_guild_remove リスナーのテスト。"""

    @patch("src.cogs.sticky.async_session")
    @patch("src.cogs.sticky.delete_sticky_messages_by_guild")
    async def test_deletes_all_stickies(
        self,
        mock_delete_by_guild: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """ギルド削除時に全ての sticky を削除する。"""
        cog = _make_cog()

        mock_delete_by_guild.return_value = 3

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        guild = MagicMock(spec=discord.Guild)
        guild.id = 789

        await cog.on_guild_remove(guild)

        mock_delete_by_guild.assert_called_once()

    @patch("src.cogs.sticky.async_session")
    @patch("src.cogs.sticky.delete_sticky_messages_by_guild")
    async def test_handles_no_stickies(
        self,
        mock_delete_by_guild: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """sticky がない場合も正常に動作する。"""
        cog = _make_cog()

        mock_delete_by_guild.return_value = 0

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        guild = MagicMock(spec=discord.Guild)
        guild.id = 789

        await cog.on_guild_remove(guild)

        mock_delete_by_guild.assert_called_once()


# ---------------------------------------------------------------------------
# エッジケーステスト: _delayed_repost
# ---------------------------------------------------------------------------


class TestDelayedRepostEdgeCases:
    """_delayed_repost のエッジケーステスト。"""

    async def test_repost_text_type_sends_plain_text(self) -> None:
        """テキストタイプの場合は content= でプレーンテキストを送信する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock(return_value=MagicMock(id=1234567890))
        channel.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        sticky = _make_sticky(message_type="text", description="Hello")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # content="Hello" で送信されている（embed ではない）
        channel.send.assert_called_once_with("Hello")

    async def test_repost_embed_type_sends_embed(self) -> None:
        """Embed タイプの場合は embed= で送信する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock(return_value=MagicMock(id=1234567890))
        channel.fetch_message = AsyncMock(return_value=MagicMock(delete=AsyncMock()))

        sticky = _make_sticky(
            message_type="embed",
            title="T",
            description="D",
            color=0xFF0000,
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # embed= キーワード引数で送信されている
        channel.send.assert_called_once()
        call_kwargs = channel.send.call_args[1]
        assert "embed" in call_kwargs
        embed = call_kwargs["embed"]
        assert embed.title == "T"
        assert embed.description == "D"

    async def test_repost_old_message_not_found_deletes_sticky(self) -> None:
        """古いメッセージが NotFound の場合、DB から sticky を削除し再投稿しない。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock()
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        sticky = _make_sticky(message_id="999")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.delete_sticky_message",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # DB から削除される
        mock_delete.assert_called_once()
        # 再投稿はされない
        channel.send.assert_not_called()


# ---------------------------------------------------------------------------
# エッジケーステスト: on_message デバウンス
# ---------------------------------------------------------------------------


class TestOnMessageDebounce:
    """on_message のデバウンス関連エッジケーステスト。"""

    async def test_rapid_messages_cancel_old_tasks(self) -> None:
        """3 連続メッセージで前のタスクがキャンセルされ、最後の 1 つだけ残る。"""
        cog = _make_cog()
        message = _make_message()

        sticky = _make_sticky(cooldown_seconds=5)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
        ):
            await cog.on_message(message)
            task1 = cog._pending_tasks["456"]

            await cog.on_message(message)
            task2 = cog._pending_tasks["456"]

            await cog.on_message(message)
            task3 = cog._pending_tasks["456"]

        # 前の 2 つはキャンセルされている
        assert task1.cancelled()
        assert task2.cancelled()
        # 最後の 1 つだけが残っている
        assert "456" in cog._pending_tasks
        assert cog._pending_tasks["456"] is task3
        # クリーンアップ
        task3.cancel()

    async def test_http_exception_on_fetch_removes_sticky(self) -> None:
        """fetch_message で HTTPException が発生した場合、DB から sticky を削除する。"""
        cog = _make_cog()
        channel = MagicMock()
        channel.send = AsyncMock()
        channel.fetch_message = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "")
        )

        sticky = _make_sticky(message_id="999")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.get_sticky_message",
                new_callable=AsyncMock,
                return_value=sticky,
            ),
            patch(
                "src.cogs.sticky.delete_sticky_message",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await cog._delayed_repost(channel, "456", 5)

        # DB から削除される
        mock_delete.assert_called_once()
        # 再投稿はされない
        channel.send.assert_not_called()


# ---------------------------------------------------------------------------
# エッジケーステスト: StickyEmbedModal カラーパース
# ---------------------------------------------------------------------------


class TestColorParsingEdgeCases:
    """StickyEmbedModal の色パースのエッジケーステスト。"""

    async def test_color_black_000000_lstrip_edge(self) -> None:
        """'000000' は lstrip('#').lstrip('0x') で空文字になり ValueError になる。

        lstrip('0x') は文字集合 {'0', 'x'} の各文字を先頭から除去するため、
        '000000' の全ての '0' が除去されて空文字 '' になり、
        int('', 16) が ValueError を発生させる。これは既知の挙動を文書化する。
        """
        cog = _make_cog()
        modal = StickyEmbedModal(cog)
        interaction = _make_interaction()

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = "000000"
        modal.delay._value = "5"

        await modal.on_submit(interaction)

        # ValueError がキャッチされてエラーメッセージが送信される
        call_args = interaction.response.send_message.call_args
        assert "無効な色形式" in call_args[0][0]

    async def test_invalid_hex_rejected(self) -> None:
        """'gg0000' のような無効な 16 進数はエラーメッセージを返す。"""
        cog = _make_cog()
        modal = StickyEmbedModal(cog)
        interaction = _make_interaction()

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = "gg0000"
        modal.delay._value = "5"

        await modal.on_submit(interaction)

        # ValueError がキャッチされてエラーメッセージが送信される
        call_args = interaction.response.send_message.call_args
        assert "無効な色形式" in call_args[0][0]


# ---------------------------------------------------------------------------
# Additional Edge Case Tests
# ---------------------------------------------------------------------------


class TestStickyEmbedModalEdgeCases:
    """StickyEmbedModal の追加エッジケーステスト。"""

    async def test_delay_zero_clamped_to_one(self) -> None:
        """delay = 0 は 1 にクランプされる。"""
        cog = _make_cog()
        modal = StickyEmbedModal(cog)
        interaction = _make_interaction()

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "0"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch("src.cogs.sticky.create_sticky_message", new_callable=AsyncMock),
            patch("src.cogs.sticky.update_sticky_message_id", new_callable=AsyncMock),
        ):
            await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        # エラーメッセージではないことを確認
        assert "無効" not in str(call_args)

    async def test_delay_exceeds_max_clamped_to_3600(self) -> None:
        """delay > 3600 は 3600 にクランプされる。"""
        cog = _make_cog()
        modal = StickyEmbedModal(cog)
        interaction = _make_interaction()

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "9999"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch("src.cogs.sticky.create_sticky_message", new_callable=AsyncMock),
            patch("src.cogs.sticky.update_sticky_message_id", new_callable=AsyncMock),
        ):
            await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "無効" not in str(call_args)

    async def test_delay_float_rejected(self) -> None:
        """delay に小数値はエラー。"""
        cog = _make_cog()
        modal = StickyEmbedModal(cog)
        interaction = _make_interaction()

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "5.5"

        await modal.on_submit(interaction)

        call_args = interaction.response.send_message.call_args
        assert "無効な遅延値" in call_args[0][0]

    async def test_no_guild_returns_error(self) -> None:
        """guild なしの interaction はエラーメッセージを返す。"""
        cog = _make_cog()
        modal = StickyEmbedModal(cog)
        interaction = _make_interaction()
        interaction.guild = None

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = ""
        modal.delay._value = "5"

        await modal.on_submit(interaction)

        call_args = interaction.response.send_message.call_args
        assert "サーバー内" in call_args[0][0]

    async def test_color_with_hash_prefix(self) -> None:
        """色に # プレフィックスを付けても正常にパースされる。"""
        cog = _make_cog()
        modal = StickyEmbedModal(cog)
        interaction = _make_interaction()

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = "#FF0000"
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch("src.cogs.sticky.create_sticky_message", new_callable=AsyncMock),
            patch("src.cogs.sticky.update_sticky_message_id", new_callable=AsyncMock),
        ):
            await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "無効な色形式" not in str(call_args)

    async def test_color_with_0x_prefix(self) -> None:
        """色に 0x プレフィックスを付けても正常にパースされる。"""
        cog = _make_cog()
        modal = StickyEmbedModal(cog)
        interaction = _make_interaction()

        modal.sticky_title._value = "Title"
        modal.description._value = "Description"
        modal.color._value = "0xFF0000"
        modal.delay._value = "5"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch("src.cogs.sticky.create_sticky_message", new_callable=AsyncMock),
            patch("src.cogs.sticky.update_sticky_message_id", new_callable=AsyncMock),
        ):
            await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "無効な色形式" not in str(call_args)


class TestOnMessageEdgeCases:
    """on_message リスナーの追加エッジケーステスト。"""

    async def test_no_sticky_config_no_repost(self) -> None:
        """sticky 設定がないチャンネルでは再投稿しない。"""
        cog = _make_cog()
        message = _make_message(author_id=12345)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch("src.cogs.sticky.get_sticky_message", return_value=None),
        ):
            await cog.on_message(message)

        channel_id = str(message.channel.id)
        assert channel_id not in cog._pending_tasks

    async def test_no_guild_no_repost(self) -> None:
        """DM メッセージでは sticky 処理をスキップ。"""
        cog = _make_cog()
        message = _make_message(author_id=12345)
        message.guild = None

        with patch("src.cogs.sticky.get_sticky_message") as mock_get:
            await cog.on_message(message)

        mock_get.assert_not_called()

    async def test_pending_task_cancelled_on_new_message(self) -> None:
        """新しいメッセージで既存のペンディングタスクがキャンセルされる。"""
        cog = _make_cog()
        message = _make_message(author_id=12345)
        channel_id = str(message.channel.id)

        # 既存のタスクを作成
        existing_task = asyncio.create_task(asyncio.sleep(100))
        cog._pending_tasks[channel_id] = existing_task

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        sticky = _make_sticky()

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch("src.cogs.sticky.get_sticky_message", return_value=sticky),
        ):
            await cog.on_message(message)

        # 既存のタスクがキャンセルされた
        assert existing_task.cancelled()
        # 新しいタスクが作成された
        assert channel_id in cog._pending_tasks
        assert cog._pending_tasks[channel_id] is not existing_task


class TestBuildEmbedEdgeCases:
    """_build_embed メソッドの追加エッジケーステスト。"""

    def test_empty_title_allowed(self) -> None:
        """空タイトルの embed が作成できる。"""
        cog = _make_cog()
        embed = cog._build_embed("", "Description", None)
        assert embed.title == ""
        assert embed.description == "Description"

    def test_long_description(self) -> None:
        """長い description の embed が作成できる。"""
        cog = _make_cog()
        long_desc = "A" * 4000
        embed = cog._build_embed("Title", long_desc, None)
        assert len(embed.description) == 4000

    def test_color_zero_falls_back_to_default(self) -> None:
        """color = 0 は falsy なのでデフォルト色が使われる。"""
        cog = _make_cog()
        embed = cog._build_embed("Title", "Description", 0)
        # 0 is falsy → `color or DEFAULT_EMBED_COLOR` → DEFAULT_EMBED_COLOR
        assert embed.color == discord.Color(0x85E7AD)


class TestStickySetupCacheVerification:
    """setup() がキャッシュを正しく構築することを検証。"""

    @patch("src.cogs.sticky.async_session")
    @patch("src.cogs.sticky.get_all_sticky_messages")
    async def test_setup_builds_channel_cache(
        self,
        mock_get_all: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """setup が _sticky_channels キャッシュを構築する."""
        from src.cogs.sticky import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()

        mock_sticky1 = MagicMock()
        mock_sticky1.channel_id = 111
        mock_sticky2 = MagicMock()
        mock_sticky2.channel_id = 222
        mock_get_all.return_value = [mock_sticky1, mock_sticky2]

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        await setup(bot)

        cog = bot.add_cog.call_args[0][0]
        assert hasattr(cog, "_sticky_channels")
        assert cog._sticky_channels == {111, 222}

    @patch("src.cogs.sticky.async_session")
    @patch("src.cogs.sticky.get_all_sticky_messages")
    async def test_setup_empty_stickies_builds_empty_cache(
        self,
        mock_get_all: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """sticky が 0 件の場合に空キャッシュが構築される."""
        from src.cogs.sticky import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()

        mock_get_all.return_value = []

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        await setup(bot)

        cog = bot.add_cog.call_args[0][0]
        assert hasattr(cog, "_sticky_channels")
        assert len(cog._sticky_channels) == 0


# ---------------------------------------------------------------------------
# _sticky_channels キャッシュ統合テスト
# ---------------------------------------------------------------------------


class TestStickyChannelsCache:
    """_sticky_channels キャッシュが初期化されている場合のテスト。"""

    @patch("src.cogs.sticky.async_session")
    @patch("src.cogs.sticky.delete_sticky_message")
    async def test_channel_delete_discards_from_cache(
        self,
        mock_delete: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """チャンネル削除時にキャッシュから channel_id を削除する (line 343)。"""
        cog = _make_cog()
        cog._sticky_channels = {"456", "789"}

        mock_delete.return_value = True
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 456
        channel.guild = MagicMock()
        channel.guild.id = 789

        await cog.on_guild_channel_delete(channel)

        assert "456" not in cog._sticky_channels
        assert "789" in cog._sticky_channels

    async def test_on_message_cache_miss_returns_early(self) -> None:
        """キャッシュ未登録チャンネルは DB アクセスなしで無視する。"""
        cog = _make_cog()
        cog._sticky_channels = {"999"}  # channel 456 は含まない

        message = _make_message(channel_id=456)

        with patch("src.cogs.sticky.async_session") as mock_session:
            await cog.on_message(message)

        # DB にアクセスしていないことを確認
        mock_session.assert_not_called()


# ---------------------------------------------------------------------------
# ロックによる同時実行制御テスト
# ---------------------------------------------------------------------------


class TestStickySetConcurrency:
    """Sticky set のロックによる同時実行制御テスト。"""

    async def test_concurrent_embed_set_serialized(self) -> None:
        """同チャンネルで同時に Embed 設定しても、ロックでシリアライズされる。"""
        cog = _make_cog()
        cog._sticky_channels = set()

        execution_order: list[str] = []

        async def tracking_create(*_args: object, **_kwargs: object) -> None:
            execution_order.append("create_start")
            await asyncio.sleep(0.01)
            execution_order.append("create_end")

        modal1 = StickySetModal(cog)
        modal1.sticky_title._value = "Title1"
        modal1.description._value = "Desc1"
        modal1.color._value = ""
        modal1.delay._value = "5"

        modal2 = StickySetModal(cog)
        modal2.sticky_title._value = "Title2"
        modal2.description._value = "Desc2"
        modal2.color._value = ""
        modal2.delay._value = "5"

        # 同じチャンネル ID
        interaction1 = _make_interaction(channel_id=456)
        interaction2 = _make_interaction(channel_id=456)

        new_msg = MagicMock()
        new_msg.id = 111
        interaction1.channel.send = AsyncMock(return_value=new_msg)
        interaction2.channel.send = AsyncMock(return_value=new_msg)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.sticky.async_session", return_value=mock_session),
            patch(
                "src.cogs.sticky.create_sticky_message",
                side_effect=tracking_create,
            ),
            patch(
                "src.cogs.sticky.update_sticky_message_id",
                new_callable=AsyncMock,
            ),
        ):
            await asyncio.gather(
                modal1.on_submit(interaction1),
                modal2.on_submit(interaction2),
            )

        # シリアライズされている: create_start → create_end が連続
        assert execution_order == [
            "create_start",
            "create_end",
            "create_start",
            "create_end",
        ]
