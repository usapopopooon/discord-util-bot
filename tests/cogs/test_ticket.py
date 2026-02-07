"""Tests for ticket cog."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord.ext import commands

# =============================================================================
# Helper factories
# =============================================================================


def _mock_async_session() -> tuple[MagicMock, AsyncMock]:
    """async_session() コンテキストマネージャのモックを返す。"""
    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_factory, mock_session


def _make_interaction(
    user_id: int = 1,
    guild_id: int = 100,
    channel_id: int = 200,
) -> MagicMock:
    """テスト用の Interaction モックを作成する。"""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.user.name = "testuser"
    interaction.user.mention = f"<@{user_id}>"
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = guild_id
    interaction.channel = MagicMock(spec=discord.TextChannel)
    interaction.channel.id = channel_id
    interaction.channel_id = channel_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _make_ticket(
    ticket_id: int = 1,
    status: str = "open",
    channel_id: str | None = "200",
    claimed_by: str | None = None,
    ticket_number: int = 1,
) -> MagicMock:
    """テスト用の Ticket モックを作成する。"""
    ticket = MagicMock()
    ticket.id = ticket_id
    ticket.status = status
    ticket.channel_id = channel_id
    ticket.claimed_by = claimed_by
    ticket.ticket_number = ticket_number
    ticket.user_id = "1"
    ticket.username = "testuser"
    ticket.category_id = 1
    return ticket


def _make_category(category_id: int = 1, name: str = "General") -> MagicMock:
    """テスト用の TicketCategory モックを作成する。"""
    category = MagicMock()
    category.id = category_id
    category.name = name
    return category


def _make_panel(panel_id: int = 1) -> MagicMock:
    """テスト用の TicketPanel モックを作成する。"""
    panel = MagicMock()
    panel.id = panel_id
    return panel


def _make_association(category_id: int = 1) -> MagicMock:
    """テスト用の TicketPanelCategory モックを作成する。"""
    assoc = MagicMock()
    assoc.category_id = category_id
    assoc.button_label = None
    assoc.button_style = "primary"
    assoc.button_emoji = None
    assoc.position = 0
    return assoc


# =============================================================================
# Cog のロード/アンロード
# =============================================================================


class TestCogLoadUnload:
    """TicketCog の cog_load/cog_unload テスト。"""

    async def test_cog_load_registers_views_and_starts_task(self) -> None:
        """cog_load で View 登録とタスク開始が行われる。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        bot.add_view = MagicMock()
        cog = TicketCog(bot)

        mock_factory, mock_session = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_all_ticket_panels",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.cogs.ticket.get_all_tickets",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await cog.cog_load()

        assert cog._sync_views_task.is_running()
        cog._sync_views_task.cancel()

    async def test_cog_unload_cancels_task(self) -> None:
        """cog_unload でタスクが停止される。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        bot.add_view = MagicMock()
        cog = TicketCog(bot)

        # cancel をモックして呼び出しを検証 (role_panel と同パターン)
        cog._sync_views_task.cancel = MagicMock()
        await cog.cog_unload()
        cog._sync_views_task.cancel.assert_called_once()


# =============================================================================
# View 登録
# =============================================================================


class TestRegisterAllViews:
    """_register_all_views のテスト。"""

    async def test_registers_panel_views(self) -> None:
        """パネルの View が登録される。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        bot.add_view = MagicMock()
        cog = TicketCog(bot)

        panel = _make_panel(panel_id=1)
        assoc = _make_association(category_id=1)
        category = _make_category(category_id=1, name="General")

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_all_ticket_panels",
                new_callable=AsyncMock,
                return_value=[panel],
            ),
            patch(
                "src.cogs.ticket.get_ticket_panel_categories",
                new_callable=AsyncMock,
                return_value=[assoc],
            ),
            patch(
                "src.cogs.ticket.get_ticket_category",
                new_callable=AsyncMock,
                return_value=category,
            ),
            patch(
                "src.cogs.ticket.get_all_tickets",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await cog._register_all_views()

        # パネル View 1 つ
        assert bot.add_view.call_count == 1

    async def test_registers_ticket_control_views(self) -> None:
        """open/claimed チケットの ControlView が登録される。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        bot.add_view = MagicMock()
        cog = TicketCog(bot)

        ticket1 = _make_ticket(ticket_id=1, status="open", channel_id="100")
        ticket2 = _make_ticket(ticket_id=2, status="claimed", channel_id="200")
        ticket3 = _make_ticket(ticket_id=3, status="closed", channel_id=None)

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_all_ticket_panels",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.cogs.ticket.get_all_tickets",
                new_callable=AsyncMock,
                return_value=[ticket1, ticket2, ticket3],
            ),
        ):
            await cog._register_all_views()

        # open + claimed = 2 views (closed は除外)
        assert bot.add_view.call_count == 2


# =============================================================================
# /ticket close コマンド
# =============================================================================


class TestTicketCloseCommand:
    """ticket_close コマンドのテスト。"""

    async def test_close_not_in_guild(self) -> None:
        """ギルド外では使用できない。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)

        interaction = _make_interaction()
        interaction.guild = None

        await cog.ticket_close.callback(cog, interaction, reason=None)
        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "サーバー内" in msg

    async def test_close_not_ticket_channel(self) -> None:
        """チケットチャンネル以外ではエラーを返す。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.ticket_close.callback(cog, interaction, reason=None)

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "チケットチャンネルではありません" in msg

    async def test_close_already_closed(self) -> None:
        """既にクローズ済みのチケットはエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        ticket = _make_ticket(status="closed")

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
        ):
            await cog.ticket_close.callback(cog, interaction, reason=None)

        msg = interaction.response.send_message.call_args[0][0]
        assert "既にクローズ" in msg

    async def test_close_success(self) -> None:
        """正常にクローズできる。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        ticket = _make_ticket(status="open")
        category = _make_category()

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
            patch(
                "src.cogs.ticket.get_ticket_category",
                new_callable=AsyncMock,
                return_value=category,
            ),
            patch(
                "src.cogs.ticket.generate_transcript",
                new_callable=AsyncMock,
                return_value="transcript text",
            ),
            patch(
                "src.cogs.ticket.update_ticket_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            await cog.ticket_close.callback(cog, interaction, reason="done")

        interaction.response.defer.assert_awaited_once()
        mock_update.assert_awaited_once()
        interaction.channel.delete.assert_awaited_once()


# =============================================================================
# /ticket claim コマンド
# =============================================================================


class TestTicketClaimCommand:
    """ticket_claim コマンドのテスト。"""

    async def test_claim_success(self) -> None:
        """正常にクレームできる。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        ticket = _make_ticket(status="open", claimed_by=None)

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
            patch(
                "src.cogs.ticket.update_ticket_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            await cog.ticket_claim.callback(cog, interaction)

        mock_update.assert_awaited_once()
        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "担当" in msg

    async def test_claim_already_claimed(self) -> None:
        """既に担当者がいる場合はエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        ticket = _make_ticket(status="claimed", claimed_by="999")

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
        ):
            await cog.ticket_claim.callback(cog, interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "既に" in msg

    async def test_claim_not_in_guild(self) -> None:
        """ギルド外ではエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        interaction.guild = None

        await cog.ticket_claim.callback(cog, interaction)
        msg = interaction.response.send_message.call_args[0][0]
        assert "サーバー内" in msg

    async def test_claim_not_ticket_channel(self) -> None:
        """チケットチャンネルでない場合はエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.ticket_claim.callback(cog, interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "チケットチャンネルではありません" in msg

    async def test_claim_closed_ticket(self) -> None:
        """既にクローズ済みのチケットはエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        ticket = _make_ticket(status="closed")

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
        ):
            await cog.ticket_claim.callback(cog, interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "クローズ" in msg


# =============================================================================
# /ticket add / remove コマンド
# =============================================================================


class TestTicketAddCommand:
    """ticket_add コマンドのテスト。"""

    async def test_add_user_success(self) -> None:
        """ユーザーをチケットに追加できる。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        ticket = _make_ticket()

        target_user = MagicMock(spec=discord.Member)
        target_user.mention = "<@2>"

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
        ):
            await cog.ticket_add.callback(cog, interaction, user=target_user)

        interaction.channel.set_permissions.assert_awaited_once()
        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "追加" in msg

    async def test_add_not_ticket_channel(self) -> None:
        """チケットチャンネルでない場合はエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        target_user = MagicMock(spec=discord.Member)

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.ticket_add.callback(cog, interaction, user=target_user)

        msg = interaction.response.send_message.call_args[0][0]
        assert "チケットチャンネルではありません" in msg

    async def test_add_not_in_guild(self) -> None:
        """ギルド外ではエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        interaction.guild = None
        target_user = MagicMock(spec=discord.Member)

        await cog.ticket_add.callback(cog, interaction, user=target_user)
        msg = interaction.response.send_message.call_args[0][0]
        assert "サーバー内" in msg

    async def test_add_channel_none(self) -> None:
        """チャンネルが None の場合はエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        interaction.channel = None
        target_user = MagicMock(spec=discord.Member)

        await cog.ticket_add.callback(cog, interaction, user=target_user)
        msg = interaction.response.send_message.call_args[0][0]
        assert "サーバー内" in msg


class TestTicketRemoveCommand:
    """ticket_remove コマンドのテスト。"""

    async def test_remove_user_success(self) -> None:
        """ユーザーをチケットから削除できる。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        ticket = _make_ticket()

        target_user = MagicMock(spec=discord.Member)
        target_user.mention = "<@2>"

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
        ):
            await cog.ticket_remove.callback(cog, interaction, user=target_user)

        interaction.channel.set_permissions.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "削除" in msg

    async def test_remove_not_in_guild(self) -> None:
        """ギルド外ではエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        interaction.guild = None
        target_user = MagicMock(spec=discord.Member)

        await cog.ticket_remove.callback(cog, interaction, user=target_user)
        msg = interaction.response.send_message.call_args[0][0]
        assert "サーバー内" in msg

    async def test_remove_not_ticket_channel(self) -> None:
        """チケットチャンネルでない場合はエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        target_user = MagicMock(spec=discord.Member)

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.ticket_remove.callback(cog, interaction, user=target_user)

        msg = interaction.response.send_message.call_args[0][0]
        assert "チケットチャンネルではありません" in msg

    async def test_remove_channel_none(self) -> None:
        """チャンネルが None の場合はエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        interaction.channel = None
        target_user = MagicMock(spec=discord.Member)

        await cog.ticket_remove.callback(cog, interaction, user=target_user)
        msg = interaction.response.send_message.call_args[0][0]
        assert "サーバー内" in msg


# =============================================================================
# イベントリスナー
# =============================================================================


class TestOnGuildChannelDelete:
    """on_guild_channel_delete リスナーのテスト。"""

    async def test_cleans_up_ticket_on_channel_delete(self) -> None:
        """チケットチャンネル削除時に DB がクリーンアップされる。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 200

        ticket = _make_ticket(status="open")

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
            patch(
                "src.cogs.ticket.update_ticket_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            await cog.on_guild_channel_delete(channel)

        mock_update.assert_awaited_once()
        assert mock_update.call_args[1]["status"] == "closed"

    async def test_no_cleanup_for_non_ticket_channel(self) -> None:
        """チケットでないチャンネル削除時はクリーンアップしない。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 999

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.cogs.ticket.update_ticket_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            await cog.on_guild_channel_delete(channel)

        mock_update.assert_not_awaited()

    async def test_no_cleanup_for_already_closed(self) -> None:
        """既にクローズ済みのチケットは再クリーンアップしない。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 200

        ticket = _make_ticket(status="closed")

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
            patch(
                "src.cogs.ticket.update_ticket_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            await cog.on_guild_channel_delete(channel)

        mock_update.assert_not_awaited()


class TestOnRawMessageDelete:
    """on_raw_message_delete リスナーのテスト。"""

    async def test_cleans_up_panel_on_message_delete(self) -> None:
        """パネルメッセージ削除時に DB がクリーンアップされる。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)

        payload = MagicMock(spec=discord.RawMessageDeleteEvent)
        payload.message_id = 500

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.delete_ticket_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_delete,
        ):
            await cog.on_raw_message_delete(payload)

        mock_delete.assert_awaited_once_with(
            mock_factory.return_value.__aenter__.return_value,
            "500",
        )

    async def test_no_cleanup_for_non_panel_message(self) -> None:
        """パネルでないメッセージ削除時はスキップ。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)

        payload = MagicMock(spec=discord.RawMessageDeleteEvent)
        payload.message_id = 999

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.delete_ticket_panel_by_message_id",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            await cog.on_raw_message_delete(payload)


# =============================================================================
# /ticket close チャンネル削除失敗
# =============================================================================


class TestTicketCloseChannelDeleteFailure:
    """ticket_close コマンドのチャンネル削除失敗テスト。"""

    async def test_close_channel_delete_http_exception(self) -> None:
        """チャンネル削除失敗時に followup メッセージを送信。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        interaction.channel.delete = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=403), "Missing Permissions"
            )
        )
        ticket = _make_ticket(status="open")
        category = _make_category()

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
            patch(
                "src.cogs.ticket.get_ticket_category",
                new_callable=AsyncMock,
                return_value=category,
            ),
            patch(
                "src.cogs.ticket.generate_transcript",
                new_callable=AsyncMock,
                return_value="transcript",
            ),
            patch(
                "src.cogs.ticket.update_ticket_status",
                new_callable=AsyncMock,
            ),
        ):
            await cog.ticket_close.callback(cog, interaction, reason=None)

        msg = interaction.followup.send.call_args[0][0]
        assert "チャンネルの削除に失敗" in msg


# =============================================================================
# /ticket add/remove 非テキストチャンネル
# =============================================================================


class TestTicketAddRemoveNonTextChannel:
    """ticket_add / ticket_remove の非テキストチャンネルテスト。"""

    async def test_add_non_text_channel(self) -> None:
        """テキストチャンネルでない場合はエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        # VoiceChannel にする
        interaction.channel = MagicMock(spec=discord.VoiceChannel)
        interaction.channel.id = 200
        interaction.channel_id = 200

        ticket = _make_ticket(status="open")
        target_user = MagicMock(spec=discord.Member)

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
        ):
            await cog.ticket_add.callback(cog, interaction, user=target_user)

        msg = interaction.response.send_message.call_args[0][0]
        assert "この操作を実行できません" in msg

    async def test_remove_non_text_channel(self) -> None:
        """テキストチャンネルでない場合はエラー。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        interaction.channel = MagicMock(spec=discord.VoiceChannel)
        interaction.channel.id = 200
        interaction.channel_id = 200

        ticket = _make_ticket(status="open")
        target_user = MagicMock(spec=discord.Member)

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
        ):
            await cog.ticket_remove.callback(cog, interaction, user=target_user)

        msg = interaction.response.send_message.call_args[0][0]
        assert "この操作を実行できません" in msg


# =============================================================================
# _sync_views_task 例外ハンドリング
# =============================================================================


class TestSyncViewsTaskException:
    """_sync_views_task の例外ハンドリングテスト。"""

    async def test_sync_task_catches_exception(self) -> None:
        """_sync_views_task は例外をキャッチしてクラッシュしない。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)

        with patch.object(
            cog,
            "_register_all_views",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection failed"),
        ):
            # 例外がキャッチされ、外に漏れないことを確認
            await cog._sync_views_task.coro(cog)


# =============================================================================
# /ticket close カテゴリなし
# =============================================================================


class TestTicketCloseNoCategoryCommand:
    """ticket_close でカテゴリが見つからないケースのテスト。"""

    async def test_close_with_missing_category(self) -> None:
        """カテゴリが None でも 'Unknown' でクローズできる。"""
        from src.cogs.ticket import TicketCog

        bot = MagicMock(spec=commands.Bot)
        cog = TicketCog(bot)
        interaction = _make_interaction()
        ticket = _make_ticket(status="open")

        mock_factory, _ = _mock_async_session()
        with (
            patch("src.cogs.ticket.async_session", mock_factory),
            patch(
                "src.cogs.ticket.get_ticket_by_channel_id",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
            patch(
                "src.cogs.ticket.get_ticket_category",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.cogs.ticket.generate_transcript",
                new_callable=AsyncMock,
                return_value="transcript",
            ) as mock_transcript,
            patch(
                "src.cogs.ticket.update_ticket_status",
                new_callable=AsyncMock,
            ),
        ):
            await cog.ticket_close.callback(cog, interaction, reason=None)

        # generate_transcript に "Unknown" が渡されることを確認
        assert mock_transcript.call_args[0][2] == "Unknown"


# =============================================================================
# setup 関数
# =============================================================================


class TestSetup:
    """setup 関数のテスト。"""

    async def test_setup_adds_cog(self) -> None:
        """setup() が Bot に Cog を追加する。"""
        from src.cogs.ticket import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()

        await setup(bot)
        bot.add_cog.assert_awaited_once()
