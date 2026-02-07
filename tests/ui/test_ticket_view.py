"""Tests for ticket UI components."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.database.models import Ticket, TicketCategory, TicketPanel, TicketPanelCategory
from src.ui.ticket_view import (
    TicketCategoryButton,
    TicketClaimButton,
    TicketCloseButton,
    TicketControlView,
    TicketPanelView,
    _create_ticket_channel,
    create_ticket_opening_embed,
    create_ticket_panel_embed,
    generate_transcript,
    send_close_log,
)

# =============================================================================
# Helper factories
# =============================================================================


def _make_ticket(**kwargs: object) -> MagicMock:
    """テスト用の Ticket モックを作成する。"""
    ticket = MagicMock(spec=Ticket)
    ticket.id = kwargs.get("id", 1)
    ticket.ticket_number = kwargs.get("ticket_number", 42)
    ticket.user_id = kwargs.get("user_id", "123456789")
    ticket.username = kwargs.get("username", "testuser")
    ticket.status = kwargs.get("status", "open")
    ticket.created_at = kwargs.get(
        "created_at", datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC)
    )
    ticket.category_id = kwargs.get("category_id", 1)
    ticket.channel_id = kwargs.get("channel_id", "200")
    ticket.claimed_by = kwargs.get("claimed_by")
    ticket.close_reason = kwargs.get("close_reason")
    return ticket


def _make_category(**kwargs: object) -> MagicMock:
    """テスト用の TicketCategory モックを作成する。"""
    category = MagicMock(spec=TicketCategory)
    category.id = kwargs.get("id", 1)
    category.name = kwargs.get("name", "General Support")
    category.staff_role_id = kwargs.get("staff_role_id", "999")
    category.discord_category_id = kwargs.get("discord_category_id")
    category.channel_prefix = kwargs.get("channel_prefix", "ticket-")
    category.form_questions = kwargs.get("form_questions")
    category.log_channel_id = kwargs.get("log_channel_id")
    category.is_enabled = kwargs.get("is_enabled", True)
    return category


def _make_panel(**kwargs: object) -> MagicMock:
    """テスト用の TicketPanel モックを作成する。"""
    panel = MagicMock(spec=TicketPanel)
    panel.id = kwargs.get("id", 1)
    panel.title = kwargs.get("title", "Support")
    panel.description = kwargs.get("description", "Click to create a ticket")
    return panel


def _make_association(**kwargs: object) -> MagicMock:
    """テスト用の TicketPanelCategory モックを作成する。"""
    assoc = MagicMock(spec=TicketPanelCategory)
    assoc.category_id = kwargs.get("category_id", 1)
    assoc.button_label = kwargs.get("button_label")
    assoc.button_style = kwargs.get("button_style", "primary")
    assoc.button_emoji = kwargs.get("button_emoji")
    assoc.position = kwargs.get("position", 0)
    return assoc


# =============================================================================
# create_ticket_opening_embed テスト
# =============================================================================


class TestCreateTicketOpeningEmbed:
    """create_ticket_opening_embed のテスト。"""

    def test_basic_embed(self) -> None:
        """基本的な Embed が作成される。"""
        ticket = _make_ticket(ticket_number=42)
        category = _make_category(name="General Support")

        embed = create_ticket_opening_embed(ticket, category)

        assert "Ticket #42" in embed.title
        assert "General Support" in embed.title
        assert f"<@{ticket.user_id}>" in (embed.description or "")
        assert embed.color == discord.Color.blue()

    def test_embed_no_fields(self) -> None:
        """Embed にフィールドがない。"""
        ticket = _make_ticket()
        category = _make_category()

        embed = create_ticket_opening_embed(ticket, category)

        assert len(embed.fields) == 0

    def test_embed_footer(self) -> None:
        """フッターにチケット ID が含まれる。"""
        ticket = _make_ticket(id=5)
        category = _make_category()

        embed = create_ticket_opening_embed(ticket, category)

        assert embed.footer.text == "Ticket ID: 5"


# =============================================================================
# create_ticket_panel_embed テスト
# =============================================================================


class TestCreateTicketPanelEmbed:
    """create_ticket_panel_embed のテスト。"""

    def test_panel_embed_with_description(self) -> None:
        """description 付きパネル Embed。"""
        panel = _make_panel(title="Support", description="Click here")
        associations = [_make_association()]

        embed = create_ticket_panel_embed(panel, associations)

        assert embed.title == "Support"
        assert embed.description == "Click here"

    def test_panel_embed_without_description(self) -> None:
        """description なしのパネル Embed はデフォルトメッセージ。"""
        panel = _make_panel(title="Support", description=None)
        associations = [_make_association()]

        embed = create_ticket_panel_embed(panel, associations)

        assert embed.title == "Support"
        assert "ボタンをクリック" in (embed.description or "")


# =============================================================================
# generate_transcript テスト
# =============================================================================


class TestGenerateTranscript:
    """generate_transcript のテスト。"""

    async def test_transcript_header(self) -> None:
        """トランスクリプトヘッダーが正しい形式。"""
        ticket = _make_ticket(ticket_number=42, username="testuser", user_id="123")
        channel = MagicMock(spec=discord.TextChannel)

        # メッセージ履歴を空にする
        async def empty_history(*_args: object, **_kwargs: object):
            return
            yield  # make this an async generator

        channel.history = MagicMock(return_value=empty_history())

        result = await generate_transcript(channel, ticket, "General", "staff_user")

        assert "=== Ticket #42 - General ===" in result
        assert "Created by: testuser (123)" in result
        assert "Closed by: staff_user" in result

    async def test_transcript_with_messages(self) -> None:
        """メッセージ付きトランスクリプト。"""
        ticket = _make_ticket(ticket_number=1, username="user1", user_id="1")
        channel = MagicMock(spec=discord.TextChannel)

        msg1 = MagicMock()
        msg1.author = MagicMock()
        msg1.author.bot = False
        msg1.author.name = "user1"
        msg1.embeds = []
        msg1.content = "Hello"
        msg1.attachments = []
        msg1.created_at = datetime(2026, 2, 7, 10, 0, 5, tzinfo=UTC)

        msg2 = MagicMock()
        msg2.author = MagicMock()
        msg2.author.bot = False
        msg2.author.name = "staff"
        msg2.embeds = []
        msg2.content = "How can I help?"
        msg2.attachments = []
        msg2.created_at = datetime(2026, 2, 7, 10, 0, 10, tzinfo=UTC)

        async def message_history(*_args: object, **_kwargs: object):
            for m in [msg1, msg2]:
                yield m

        channel.history = MagicMock(return_value=message_history())

        result = await generate_transcript(channel, ticket, "General", "staff")

        assert "[2026-02-07 10:00:05] user1: Hello" in result
        assert "[2026-02-07 10:00:10] staff: How can I help?" in result

    async def test_transcript_skips_bot_embeds(self) -> None:
        """Bot の Embed メッセージはスキップされる。"""
        ticket = _make_ticket()
        channel = MagicMock(spec=discord.TextChannel)

        bot_msg = MagicMock()
        bot_msg.author = MagicMock()
        bot_msg.author.bot = True
        bot_msg.embeds = [MagicMock()]  # Bot の Embed
        bot_msg.content = ""
        bot_msg.attachments = []
        bot_msg.created_at = datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC)

        async def message_history(*_args: object, **_kwargs: object):
            yield bot_msg

        channel.history = MagicMock(return_value=message_history())

        result = await generate_transcript(channel, ticket, "General", "staff")

        # Bot Embed はスキップされるので、ヘッダーとフッターのみ
        lines = [line for line in result.split("\n") if line.startswith("[")]
        assert len(lines) == 0

    async def test_transcript_with_attachments(self) -> None:
        """添付ファイル付きメッセージ。"""
        ticket = _make_ticket()
        channel = MagicMock(spec=discord.TextChannel)

        msg = MagicMock()
        msg.author = MagicMock()
        msg.author.bot = False
        msg.author.name = "user1"
        msg.embeds = []
        msg.content = "See attached"
        attachment = MagicMock()
        attachment.url = "https://example.com/file.png"
        msg.attachments = [attachment]
        msg.created_at = datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC)

        async def message_history(*_args: object, **_kwargs: object):
            yield msg

        channel.history = MagicMock(return_value=message_history())

        result = await generate_transcript(channel, ticket, "General", "staff")

        assert "[Attachments: https://example.com/file.png]" in result


# =============================================================================
# TicketPanelView テスト
# =============================================================================


class TestTicketPanelView:
    """TicketPanelView のテスト。"""

    async def test_creates_buttons_from_associations(self) -> None:
        """カテゴリ数分のボタンが作成される。"""
        assoc1 = _make_association(category_id=1)
        assoc2 = _make_association(category_id=2)
        names = {1: "General", 2: "Bug Report"}

        view = TicketPanelView(
            panel_id=1, associations=[assoc1, assoc2], category_names=names
        )

        assert len(view.children) == 2

    async def test_timeout_is_none(self) -> None:
        """永続 View なので timeout は None。"""
        view = TicketPanelView(panel_id=1, associations=[], category_names={})
        assert view.timeout is None

    async def test_max_25_buttons(self) -> None:
        """最大 25 ボタンまで。"""
        associations = [_make_association(category_id=i) for i in range(30)]
        names = {i: f"Cat {i}" for i in range(30)}

        view = TicketPanelView(
            panel_id=1, associations=associations, category_names=names
        )

        assert len(view.children) == 25


# =============================================================================
# TicketCategoryButton テスト
# =============================================================================


class TestTicketCategoryButton:
    """TicketCategoryButton のテスト。"""

    def test_custom_id_format(self) -> None:
        """custom_id が正しい形式。"""
        assoc = _make_association(category_id=5)
        button = TicketCategoryButton(
            panel_id=3, association=assoc, category_name="Test"
        )

        assert button.custom_id == "ticket_panel:3:5"

    def test_button_label_from_association(self) -> None:
        """button_label が設定されている場合はそれを使用。"""
        assoc = _make_association(button_label="Custom Label")
        button = TicketCategoryButton(
            panel_id=1, association=assoc, category_name="Default"
        )

        assert button.label == "Custom Label"

    def test_button_label_from_category_name(self) -> None:
        """button_label がない場合はカテゴリ名を使用。"""
        assoc = _make_association(button_label=None)
        button = TicketCategoryButton(
            panel_id=1, association=assoc, category_name="General"
        )

        assert button.label == "General"

    def test_button_style_mapping(self) -> None:
        """ボタンスタイルが正しくマッピングされる。"""
        styles = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger,
        }
        for style_name, expected_style in styles.items():
            assoc = _make_association(button_style=style_name)
            button = TicketCategoryButton(
                panel_id=1, association=assoc, category_name="Test"
            )
            assert button.style == expected_style


# =============================================================================
# TicketControlView テスト
# =============================================================================


class TestTicketControlView:
    """TicketControlView のテスト。"""

    async def test_has_close_and_claim_buttons(self) -> None:
        """Close と Claim ボタンが含まれる。"""
        view = TicketControlView(ticket_id=1)

        assert len(view.children) == 2
        button_types = [type(child) for child in view.children]
        assert TicketCloseButton in button_types
        assert TicketClaimButton in button_types

    async def test_timeout_is_none(self) -> None:
        """永続 View なので timeout は None。"""
        view = TicketControlView(ticket_id=1)
        assert view.timeout is None


# =============================================================================
# TicketCloseButton テスト
# =============================================================================


class TestTicketCloseButton:
    """TicketCloseButton のテスト。"""

    def test_custom_id_format(self) -> None:
        """custom_id が正しい形式。"""
        button = TicketCloseButton(ticket_id=42)
        assert button.custom_id == "ticket_ctrl:42:close"

    def test_button_style_is_danger(self) -> None:
        """ボタンスタイルが danger。"""
        button = TicketCloseButton(ticket_id=1)
        assert button.style == discord.ButtonStyle.danger

    def test_button_label(self) -> None:
        """ラベルが Close。"""
        button = TicketCloseButton(ticket_id=1)
        assert button.label == "Close"


# =============================================================================
# TicketClaimButton テスト
# =============================================================================


class TestTicketClaimButton:
    """TicketClaimButton のテスト。"""

    def test_custom_id_format(self) -> None:
        """custom_id が正しい形式。"""
        button = TicketClaimButton(ticket_id=42)
        assert button.custom_id == "ticket_ctrl:42:claim"

    def test_button_style_is_success(self) -> None:
        """ボタンスタイルが success。"""
        button = TicketClaimButton(ticket_id=1)
        assert button.style == discord.ButtonStyle.success

    def test_button_label(self) -> None:
        """ラベルが Claim。"""
        button = TicketClaimButton(ticket_id=1)
        assert button.label == "Claim"


# =============================================================================
# _create_ticket_channel テスト
# =============================================================================


def _mock_async_session() -> tuple[MagicMock, AsyncMock]:
    """async_session() コンテキストマネージャのモックを返す。"""
    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_factory, mock_session


class TestCreateTicketChannel:
    """_create_ticket_channel のテスト。"""

    async def test_creates_channel_successfully(self) -> None:
        """正常にチャンネルを作成できる。"""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 100
        guild.default_role = MagicMock(spec=discord.Role)
        guild.me = MagicMock(spec=discord.Member)
        guild.get_role = MagicMock(return_value=MagicMock(spec=discord.Role))
        guild.get_channel = MagicMock(return_value=None)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 999
        mock_channel.mention = "<#999>"
        mock_channel.send = AsyncMock()
        guild.create_text_channel = AsyncMock(return_value=mock_channel)

        user = MagicMock(spec=discord.Member)
        user.id = 1
        user.name = "testuser"

        category = _make_category(channel_prefix="ticket-", staff_role_id="999")
        db_session = AsyncMock()

        mock_ticket = _make_ticket(id=1, ticket_number=42)

        with (
            patch(
                "src.ui.ticket_view.get_next_ticket_number",
                new_callable=AsyncMock,
                return_value=42,
            ),
            patch(
                "src.ui.ticket_view.create_ticket",
                new_callable=AsyncMock,
                return_value=mock_ticket,
            ),
            patch(
                "src.ui.ticket_view.TicketControlView",
                return_value=MagicMock(),
            ),
        ):
            result = await _create_ticket_channel(guild, user, category, db_session)

        assert result == mock_channel
        guild.create_text_channel.assert_awaited_once()
        mock_channel.send.assert_awaited_once()

    async def test_returns_none_on_http_exception(self) -> None:
        """HTTPException 発生時は None を返す。"""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 100
        guild.default_role = MagicMock(spec=discord.Role)
        guild.me = MagicMock(spec=discord.Member)
        guild.get_role = MagicMock(return_value=None)
        guild.get_channel = MagicMock(return_value=None)
        guild.create_text_channel = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=403), "Missing Permissions"
            )
        )

        user = MagicMock(spec=discord.Member)
        user.id = 1
        user.name = "testuser"

        category = _make_category(channel_prefix="ticket-", staff_role_id="999")
        db_session = AsyncMock()

        with patch(
            "src.ui.ticket_view.get_next_ticket_number",
            new_callable=AsyncMock,
            return_value=1,
        ):
            result = await _create_ticket_channel(guild, user, category, db_session)

        assert result is None

    async def test_uses_discord_category_when_set(self) -> None:
        """discord_category_id が設定されている場合に Discord カテゴリを使用。"""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 100
        guild.default_role = MagicMock(spec=discord.Role)
        guild.me = MagicMock(spec=discord.Member)
        guild.get_role = MagicMock(return_value=None)

        discord_cat = MagicMock(spec=discord.CategoryChannel)
        guild.get_channel = MagicMock(return_value=discord_cat)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        guild.create_text_channel = AsyncMock(return_value=mock_channel)

        user = MagicMock(spec=discord.Member)
        user.id = 1
        user.name = "testuser"

        category = _make_category(
            channel_prefix="ticket-",
            staff_role_id="999",
            discord_category_id="500",
        )
        db_session = AsyncMock()
        mock_ticket = _make_ticket()

        with (
            patch(
                "src.ui.ticket_view.get_next_ticket_number",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "src.ui.ticket_view.create_ticket",
                new_callable=AsyncMock,
                return_value=mock_ticket,
            ),
            patch(
                "src.ui.ticket_view.TicketControlView",
                return_value=MagicMock(),
            ),
        ):
            await _create_ticket_channel(guild, user, category, db_session)

        call_kwargs = guild.create_text_channel.call_args[1]
        assert call_kwargs["category"] == discord_cat

    async def test_no_user_overwrite_for_non_member(self) -> None:
        """User (非 Member) の場合はユーザーの overwrite を追加しない。"""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 100
        guild.default_role = MagicMock(spec=discord.Role)
        guild.me = MagicMock(spec=discord.Member)
        guild.get_role = MagicMock(return_value=None)
        guild.get_channel = MagicMock(return_value=None)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        guild.create_text_channel = AsyncMock(return_value=mock_channel)

        user = MagicMock(spec=discord.User)
        user.id = 1
        user.name = "testuser"

        category = _make_category(channel_prefix="ticket-", staff_role_id="999")
        db_session = AsyncMock()
        mock_ticket = _make_ticket()

        with (
            patch(
                "src.ui.ticket_view.get_next_ticket_number",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "src.ui.ticket_view.create_ticket",
                new_callable=AsyncMock,
                return_value=mock_ticket,
            ),
            patch(
                "src.ui.ticket_view.TicketControlView",
                return_value=MagicMock(),
            ),
        ):
            await _create_ticket_channel(guild, user, category, db_session)

        call_kwargs = guild.create_text_channel.call_args[1]
        overwrites = call_kwargs["overwrites"]
        # default_role + guild.me のみ (ユーザーは含まれない)
        assert user not in overwrites

    async def test_sends_spoiler_staff_mention(self) -> None:
        """チャンネルにスポイラー付きスタッフメンションが送信される。"""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 100
        guild.default_role = MagicMock(spec=discord.Role)
        guild.me = MagicMock(spec=discord.Member)
        guild.get_role = MagicMock(return_value=MagicMock(spec=discord.Role))
        guild.get_channel = MagicMock(return_value=None)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        guild.create_text_channel = AsyncMock(return_value=mock_channel)

        user = MagicMock(spec=discord.Member)
        user.id = 1
        user.name = "testuser"

        category = _make_category(channel_prefix="ticket-", staff_role_id="999")
        db_session = AsyncMock()
        mock_ticket = _make_ticket()

        with (
            patch(
                "src.ui.ticket_view.get_next_ticket_number",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "src.ui.ticket_view.create_ticket",
                new_callable=AsyncMock,
                return_value=mock_ticket,
            ),
            patch(
                "src.ui.ticket_view.TicketControlView",
                return_value=MagicMock(),
            ),
        ):
            await _create_ticket_channel(guild, user, category, db_session)

        call_kwargs = mock_channel.send.call_args[1]
        assert call_kwargs["content"] == "||<@&999>||"


# =============================================================================
# TicketCloseButton callback テスト
# =============================================================================


class TestTicketCloseButtonCallback:
    """TicketCloseButton.callback のテスト。"""

    async def test_close_button_guild_none_returns(self) -> None:
        """guild が None の場合は何もしない。"""
        button = TicketCloseButton(ticket_id=1)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None
        interaction.channel = None
        interaction.response = AsyncMock()

        await button.callback(interaction)
        interaction.response.defer.assert_not_awaited()

    async def test_close_button_ticket_none(self) -> None:
        """チケットが None の場合はエラーメッセージ。"""
        button = TicketCloseButton(ticket_id=1)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.id = 1
        interaction.user.name = "closer"

        _, mock_session = _mock_async_session()
        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        interaction.followup.send.assert_awaited_once()
        msg = interaction.followup.send.call_args[0][0]
        assert "クローズ" in msg

    async def test_close_button_already_closed(self) -> None:
        """既にクローズ済みのチケットはエラー。"""
        button = TicketCloseButton(ticket_id=1)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.user = MagicMock()

        ticket = _make_ticket(status="closed")
        _, mock_session = _mock_async_session()
        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        msg = interaction.followup.send.call_args[0][0]
        assert "クローズ" in msg

    async def test_close_button_success(self) -> None:
        """正常にクローズできる。"""
        button = TicketCloseButton(ticket_id=1)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.delete = AsyncMock()
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.id = 1
        interaction.user.name = "closer"

        ticket = _make_ticket(status="open", ticket_number=42)
        category = _make_category(name="General")
        _, mock_session = _mock_async_session()
        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
            patch(
                "src.ui.ticket_view.get_ticket_category",
                new_callable=AsyncMock,
                return_value=category,
            ),
            patch(
                "src.ui.ticket_view.generate_transcript",
                new_callable=AsyncMock,
                return_value="transcript",
            ),
            patch(
                "src.ui.ticket_view.update_ticket_status",
                new_callable=AsyncMock,
            ) as mock_update,
            patch(
                "src.ui.ticket_view.send_close_log",
                new_callable=AsyncMock,
            ) as mock_log,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        mock_update.assert_awaited_once()
        mock_log.assert_awaited_once()
        interaction.channel.delete.assert_awaited_once()


# =============================================================================
# TicketClaimButton callback テスト
# =============================================================================


class TestTicketClaimButtonCallback:
    """TicketClaimButton.callback のテスト。"""

    async def test_claim_button_guild_none_returns(self) -> None:
        """guild が None の場合は何もしない。"""
        button = TicketClaimButton(ticket_id=1)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None
        interaction.response = AsyncMock()

        await button.callback(interaction)
        interaction.response.send_message.assert_not_awaited()

    async def test_claim_button_ticket_none(self) -> None:
        """チケットが None の場合はエラー。"""
        button = TicketClaimButton(ticket_id=1)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.response = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.id = 1
        interaction.user.mention = "<@1>"

        _, mock_session = _mock_async_session()
        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "見つかりません" in msg

    async def test_claim_button_ticket_closed(self) -> None:
        """クローズ済みのチケットはエラー。"""
        button = TicketClaimButton(ticket_id=1)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.response = AsyncMock()
        interaction.user = MagicMock()

        ticket = _make_ticket(status="closed")
        _, mock_session = _mock_async_session()
        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "クローズ" in msg

    async def test_claim_button_already_claimed(self) -> None:
        """既に担当者がいる場合はエラー。"""
        button = TicketClaimButton(ticket_id=1)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.response = AsyncMock()
        interaction.user = MagicMock()

        ticket = _make_ticket(status="claimed", claimed_by="999")
        _, mock_session = _mock_async_session()
        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "既に" in msg

    async def test_claim_button_success(self) -> None:
        """正常に担当できる。"""
        button = TicketClaimButton(ticket_id=1)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.response = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.id = 1
        interaction.user.mention = "<@1>"

        ticket = _make_ticket(status="open", claimed_by=None)
        _, mock_session = _mock_async_session()
        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
            patch(
                "src.ui.ticket_view.update_ticket_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        mock_update.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert "担当" in msg


# =============================================================================
# TicketCategoryButton callback テスト
# =============================================================================


class TestTicketCategoryButtonCallback:
    """TicketCategoryButton.callback のテスト。"""

    async def test_callback_guild_none(self) -> None:
        """guild が None の場合はエラーメッセージ。"""
        assoc = _make_association(category_id=1)
        button = TicketCategoryButton(
            panel_id=1, association=assoc, category_name="Test"
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None
        interaction.response = AsyncMock()

        await button.callback(interaction)
        msg = interaction.response.send_message.call_args[0][0]
        assert "サーバー内" in msg

    async def test_callback_category_disabled(self) -> None:
        """カテゴリが無効の場合はエラー。"""
        assoc = _make_association(category_id=1)
        button = TicketCategoryButton(
            panel_id=1, association=assoc, category_name="Test"
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 100
        interaction.user = MagicMock()
        interaction.user.id = 1
        interaction.response = AsyncMock()

        category = _make_category(is_enabled=False)
        _, mock_session = _mock_async_session()
        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket_category",
                new_callable=AsyncMock,
                return_value=category,
            ),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "利用できません" in msg

    async def test_callback_category_none(self) -> None:
        """カテゴリが None の場合はエラー。"""
        assoc = _make_association(category_id=1)
        button = TicketCategoryButton(
            panel_id=1, association=assoc, category_name="Test"
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 100
        interaction.user = MagicMock()
        interaction.user.id = 1
        interaction.response = AsyncMock()

        _, mock_session = _mock_async_session()
        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket_category",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "利用できません" in msg


# =============================================================================
# generate_transcript エッジケーステスト
# =============================================================================


class TestGenerateTranscriptEdgeCases:
    """generate_transcript のエッジケーステスト。"""

    async def test_transcript_http_exception_handling(self) -> None:
        """HTTPException 発生時はエラーメッセージが含まれる。"""
        ticket = _make_ticket(ticket_number=1, username="user1", user_id="1")
        channel = MagicMock(spec=discord.TextChannel)

        channel.history = MagicMock(
            side_effect=discord.HTTPException(MagicMock(status=403), "Missing Access")
        )

        result = await generate_transcript(channel, ticket, "General", "staff")

        assert "Failed to fetch message history" in result

    async def test_transcript_with_multiple_attachments(self) -> None:
        """複数の添付ファイルがカンマ区切りで出力される。"""
        ticket = _make_ticket()
        channel = MagicMock(spec=discord.TextChannel)

        msg = MagicMock()
        msg.author = MagicMock()
        msg.author.bot = False
        msg.author.name = "user1"
        msg.embeds = []
        msg.content = "Files"
        a1 = MagicMock()
        a1.url = "https://example.com/a.png"
        a2 = MagicMock()
        a2.url = "https://example.com/b.pdf"
        msg.attachments = [a1, a2]
        msg.created_at = datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC)

        async def message_history(*_args: object, **_kwargs: object):
            yield msg

        channel.history = MagicMock(return_value=message_history())

        result = await generate_transcript(channel, ticket, "General", "staff")

        assert "https://example.com/a.png" in result
        assert "https://example.com/b.pdf" in result

    async def test_transcript_empty_content_with_attachment(self) -> None:
        """content が空でも添付ファイルだけで行が出力される。"""
        ticket = _make_ticket()
        channel = MagicMock(spec=discord.TextChannel)

        msg = MagicMock()
        msg.author = MagicMock()
        msg.author.bot = False
        msg.author.name = "user1"
        msg.embeds = []
        msg.content = ""
        attachment = MagicMock()
        attachment.url = "https://example.com/file.png"
        msg.attachments = [attachment]
        msg.created_at = datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC)

        async def message_history(*_args: object, **_kwargs: object):
            yield msg

        channel.history = MagicMock(return_value=message_history())

        result = await generate_transcript(channel, ticket, "General", "staff")

        assert "[Attachments: https://example.com/file.png]" in result

    async def test_transcript_bot_text_message_included(self) -> None:
        """Bot のテキストメッセージ (Embed なし) は含まれる。"""
        ticket = _make_ticket()
        channel = MagicMock(spec=discord.TextChannel)

        msg = MagicMock()
        msg.author = MagicMock()
        msg.author.bot = True
        msg.embeds = []  # Embed なし
        msg.content = "Bot message"
        msg.attachments = []
        msg.created_at = datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC)

        async def message_history(*_args: object, **_kwargs: object):
            yield msg

        channel.history = MagicMock(return_value=message_history())

        result = await generate_transcript(channel, ticket, "General", "staff")

        assert "Bot message" in result

    async def test_transcript_respects_timezone_offset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """タイムゾーンオフセットがトランスクリプトに反映される。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 9)

        ticket = _make_ticket(
            ticket_number=1,
            username="user1",
            user_id="1",
            created_at=datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC),
        )
        channel = MagicMock(spec=discord.TextChannel)

        msg = MagicMock()
        msg.author = MagicMock()
        msg.author.bot = False
        msg.author.name = "user1"
        msg.embeds = []
        msg.content = "Hello"
        msg.attachments = []
        msg.created_at = datetime(2026, 2, 7, 10, 0, 5, tzinfo=UTC)

        async def message_history(*_args: object, **_kwargs: object):
            yield msg

        channel.history = MagicMock(return_value=message_history())

        result = await generate_transcript(channel, ticket, "General", "staff")

        # UTC 10:00 + 9h = 19:00 JST
        assert "Created at: 2026-02-07 19:00:00" in result
        assert "[2026-02-07 19:00:05] user1: Hello" in result

    async def test_transcript_with_sticker_only(self) -> None:
        """スタンプのみのメッセージがトランスクリプトに含まれる。"""
        ticket = _make_ticket()
        channel = MagicMock(spec=discord.TextChannel)

        msg = MagicMock()
        msg.author = MagicMock()
        msg.author.bot = False
        msg.author.name = "user1"
        msg.embeds = []
        msg.content = ""
        msg.attachments = []
        sticker = MagicMock()
        sticker.name = "cool_sticker"
        msg.stickers = [sticker]
        msg.created_at = datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC)

        async def message_history(*_args: object, **_kwargs: object):
            yield msg

        channel.history = MagicMock(return_value=message_history())

        result = await generate_transcript(channel, ticket, "General", "staff")

        assert "[Stickers: cool_sticker]" in result
        assert "user1" in result

    async def test_transcript_with_text_and_sticker(self) -> None:
        """テキスト＋スタンプのメッセージが両方含まれる。"""
        ticket = _make_ticket()
        channel = MagicMock(spec=discord.TextChannel)

        msg = MagicMock()
        msg.author = MagicMock()
        msg.author.bot = False
        msg.author.name = "user1"
        msg.embeds = []
        msg.content = "Check this out"
        msg.attachments = []
        sticker = MagicMock()
        sticker.name = "like_sticker"
        msg.stickers = [sticker]
        msg.created_at = datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC)

        async def message_history(*_args: object, **_kwargs: object):
            yield msg

        channel.history = MagicMock(return_value=message_history())

        result = await generate_transcript(channel, ticket, "General", "staff")

        assert "Check this out" in result
        assert "[Stickers: like_sticker]" in result

    async def test_transcript_messages_in_chronological_order(self) -> None:
        """メッセージが時系列順に並ぶ。"""
        ticket = _make_ticket()
        channel = MagicMock(spec=discord.TextChannel)

        msg1 = MagicMock()
        msg1.author = MagicMock()
        msg1.author.bot = False
        msg1.author.name = "user1"
        msg1.embeds = []
        msg1.content = "First"
        msg1.attachments = []
        msg1.stickers = []
        msg1.created_at = datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC)

        msg2 = MagicMock()
        msg2.author = MagicMock()
        msg2.author.bot = False
        msg2.author.name = "user1"
        msg2.embeds = []
        msg2.content = "Second"
        msg2.attachments = []
        msg2.stickers = []
        msg2.created_at = datetime(2026, 2, 7, 10, 5, 0, tzinfo=UTC)

        # channel.history() はデフォルトで新しい順 (msg2, msg1) で返す
        async def message_history(*_args: object, **_kwargs: object):
            for m in [msg2, msg1]:
                yield m

        channel.history = MagicMock(return_value=message_history())

        result = await generate_transcript(channel, ticket, "General", "staff")

        # reverse() により古い順に並ぶ
        first_pos = result.index("First")
        second_pos = result.index("Second")
        assert first_pos < second_pos

    async def test_transcript_attachment_only_no_content(self) -> None:
        """テキストなし・添付ファイルのみのメッセージが含まれる。"""
        ticket = _make_ticket()
        channel = MagicMock(spec=discord.TextChannel)

        msg = MagicMock()
        msg.author = MagicMock()
        msg.author.bot = False
        msg.author.name = "user1"
        msg.embeds = []
        msg.content = ""
        attachment = MagicMock()
        attachment.url = "https://cdn.discord.com/img.png"
        msg.attachments = [attachment]
        msg.stickers = []
        msg.created_at = datetime(2026, 2, 7, 10, 0, 0, tzinfo=UTC)

        async def message_history(*_args: object, **_kwargs: object):
            yield msg

        channel.history = MagicMock(return_value=message_history())

        result = await generate_transcript(channel, ticket, "General", "staff")

        assert "user1: [Attachments: https://cdn.discord.com/img.png]" in result


# =============================================================================
# TicketCategoryButton callback 追加テスト
# =============================================================================


class TestTicketCategoryButtonCallbackExtra:
    """TicketCategoryButton.callback の追加テスト。"""

    async def test_callback_existing_open_ticket(self) -> None:
        """既にオープンチケットがある場合はエラーメッセージ。"""
        assoc = _make_association(category_id=1)
        button = TicketCategoryButton(
            panel_id=1, association=assoc, category_name="Test"
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 100
        interaction.user = MagicMock()
        interaction.user.id = 1
        interaction.response = AsyncMock()

        category = _make_category(is_enabled=True, form_questions=None)

        # 既存チケットのモック
        existing_ticket = MagicMock()
        existing_ticket.channel_id = "300"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = existing_ticket

        _, mock_session = _mock_async_session()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket_category",
                new_callable=AsyncMock,
                return_value=category,
            ),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "既にオープン中" in msg

    async def test_callback_direct_creation_success(self) -> None:
        """フォームなしで直接チケット作成に成功。"""
        assoc = _make_association(category_id=1)
        button = TicketCategoryButton(
            panel_id=1, association=assoc, category_name="Test"
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 100
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 1
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        category = _make_category(is_enabled=True, form_questions=None)

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        _, mock_session = _mock_async_session()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.mention = "<#999>"

        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket_category",
                new_callable=AsyncMock,
                return_value=category,
            ),
            patch(
                "src.ui.ticket_view._create_ticket_channel",
                new_callable=AsyncMock,
                return_value=mock_channel,
            ),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        msg = interaction.followup.send.call_args[0][0]
        assert "チケットを作成しました" in msg

    async def test_callback_direct_creation_failure(self) -> None:
        """チャンネル作成失敗時はエラーメッセージ。"""
        assoc = _make_association(category_id=1)
        button = TicketCategoryButton(
            panel_id=1, association=assoc, category_name="Test"
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 100
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 1
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        category = _make_category(is_enabled=True, form_questions=None)

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        _, mock_session = _mock_async_session()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket_category",
                new_callable=AsyncMock,
                return_value=category,
            ),
            patch(
                "src.ui.ticket_view._create_ticket_channel",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        msg = interaction.followup.send.call_args[0][0]
        assert "失敗" in msg


# =============================================================================
# TicketCloseButton channel delete failure テスト
# =============================================================================


class TestTicketCloseButtonChannelDeleteFailure:
    """TicketCloseButton でチャンネル削除失敗時のテスト。"""

    async def test_close_button_channel_delete_http_exception(self) -> None:
        """チャンネル削除失敗時に followup メッセージを送信。"""
        button = TicketCloseButton(ticket_id=1)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel.delete = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=403), "Missing Permissions"
            )
        )
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.id = 1
        interaction.user.name = "closer"

        ticket = _make_ticket(status="open", ticket_number=42)
        category = _make_category(name="General")
        _, mock_session = _mock_async_session()
        with (
            patch("src.ui.ticket_view.async_session") as mock_factory,
            patch(
                "src.ui.ticket_view.get_ticket",
                new_callable=AsyncMock,
                return_value=ticket,
            ),
            patch(
                "src.ui.ticket_view.get_ticket_category",
                new_callable=AsyncMock,
                return_value=category,
            ),
            patch(
                "src.ui.ticket_view.generate_transcript",
                new_callable=AsyncMock,
                return_value="transcript",
            ),
            patch(
                "src.ui.ticket_view.update_ticket_status",
                new_callable=AsyncMock,
            ),
            patch(
                "src.ui.ticket_view.send_close_log",
                new_callable=AsyncMock,
            ),
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await button.callback(interaction)

        msg = interaction.followup.send.call_args[0][0]
        assert "チャンネルの削除に失敗" in msg


# =============================================================================
# send_close_log テスト
# =============================================================================


class TestSendCloseLog:
    """send_close_log のテスト。"""

    async def test_sends_embed_to_log_channel(self) -> None:
        """ログチャンネルにEmbedを送信する。"""
        guild = MagicMock(spec=discord.Guild)
        log_channel = MagicMock(spec=discord.TextChannel)
        log_channel.send = AsyncMock()
        guild.get_channel.return_value = log_channel

        ticket = _make_ticket(ticket_number=42, close_reason="resolved")
        category = _make_category(log_channel_id="888")

        await send_close_log(guild, ticket, category, "closer", "http://localhost:8000")

        guild.get_channel.assert_called_once_with(888)
        log_channel.send.assert_awaited_once()
        embed = log_channel.send.call_args[1]["embed"]
        assert "Ticket #42" in embed.title
        assert "Closed" in embed.title

    async def test_skips_when_no_log_channel_id(self) -> None:
        """log_channel_id が None の場合はスキップ。"""
        guild = MagicMock(spec=discord.Guild)
        ticket = _make_ticket()
        category = _make_category(log_channel_id=None)

        await send_close_log(guild, ticket, category, "closer", "http://localhost:8000")

        guild.get_channel.assert_not_called()

    async def test_skips_when_category_is_none(self) -> None:
        """カテゴリが None の場合はスキップ。"""
        guild = MagicMock(spec=discord.Guild)
        ticket = _make_ticket()

        await send_close_log(guild, ticket, None, "closer", "http://localhost:8000")

        guild.get_channel.assert_not_called()

    async def test_skips_when_channel_not_text(self) -> None:
        """ログチャンネルが TextChannel でない場合はスキップ。"""
        guild = MagicMock(spec=discord.Guild)
        guild.get_channel.return_value = MagicMock(spec=discord.VoiceChannel)

        ticket = _make_ticket()
        category = _make_category(log_channel_id="888")

        await send_close_log(guild, ticket, category, "closer", "http://localhost:8000")

        guild.get_channel.assert_called_once_with(888)

    async def test_handles_http_exception(self) -> None:
        """送信失敗時はログのみで例外を投げない。"""
        guild = MagicMock(spec=discord.Guild)
        log_channel = MagicMock(spec=discord.TextChannel)
        log_channel.send = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "error")
        )
        guild.get_channel.return_value = log_channel

        ticket = _make_ticket()
        category = _make_category(log_channel_id="888")

        # Should not raise
        await send_close_log(guild, ticket, category, "closer", "http://localhost:8000")

    async def test_embed_contains_web_link(self) -> None:
        """Embed にWeb管理画面へのリンクが含まれる。"""
        guild = MagicMock(spec=discord.Guild)
        log_channel = MagicMock(spec=discord.TextChannel)
        log_channel.send = AsyncMock()
        guild.get_channel.return_value = log_channel

        ticket = _make_ticket(id=42)
        category = _make_category(log_channel_id="888")

        await send_close_log(guild, ticket, category, "closer", "http://localhost:8000")

        embed = log_channel.send.call_args[1]["embed"]
        # Find the Transcript field
        transcript_field = next(f for f in embed.fields if f.name == "Transcript")
        assert "http://localhost:8000/tickets/42" in transcript_field.value

    async def test_embed_includes_close_reason(self) -> None:
        """close_reason がある場合はEmbedに含まれる。"""
        guild = MagicMock(spec=discord.Guild)
        log_channel = MagicMock(spec=discord.TextChannel)
        log_channel.send = AsyncMock()
        guild.get_channel.return_value = log_channel

        ticket = _make_ticket(close_reason="spam")
        category = _make_category(log_channel_id="888")

        await send_close_log(guild, ticket, category, "closer", "http://localhost:8000")

        embed = log_channel.send.call_args[1]["embed"]
        reason_field = next(f for f in embed.fields if f.name == "Reason")
        assert reason_field.value == "spam"

    async def test_embed_no_reason_field_when_none(self) -> None:
        """close_reason が None の場合は Reason フィールドなし。"""
        guild = MagicMock(spec=discord.Guild)
        log_channel = MagicMock(spec=discord.TextChannel)
        log_channel.send = AsyncMock()
        guild.get_channel.return_value = log_channel

        ticket = _make_ticket(close_reason=None)
        category = _make_category(log_channel_id="888")

        await send_close_log(guild, ticket, category, "closer", "http://localhost:8000")

        embed = log_channel.send.call_args[1]["embed"]
        field_names = [f.name for f in embed.fields]
        assert "Reason" not in field_names
