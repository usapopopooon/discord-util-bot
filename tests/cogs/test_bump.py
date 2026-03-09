"""Tests for BumpCog (DISBOARD/ディス速報 bump reminder)."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from src.cogs.bump import (
    BUMP_NOTIFICATION_COOLDOWN_SECONDS,
    DISBOARD_BOT_ID,
    DISBOARD_SUCCESS_KEYWORD,
    DISSOKU_BOT_ID,
    DISSOKU_SUCCESS_KEYWORD,
    TARGET_ROLE_NAME,
    BumpCog,
    BumpNotificationView,
    _bump_notification_cooldown_cache,
    _cleanup_bump_notification_cooldown_cache,
    clear_bump_notification_cooldown_cache,
    is_bump_notification_on_cooldown,
)
from src.utils import clear_resource_locks


@pytest.fixture(autouse=True)
def clear_cooldown_cache() -> None:
    """Clear bump notification cooldown cache and resource locks before each test."""
    clear_bump_notification_cooldown_cache()
    clear_resource_locks()


class TestBumpStateIsolation:
    """autouse fixture によるステート分離が機能することを検証するカナリアテスト."""

    def test_cache_starts_empty(self) -> None:
        """各テスト開始時にキャッシュが空であることを検証."""
        assert len(_bump_notification_cooldown_cache) == 0

    def test_cleanup_time_is_reset(self) -> None:
        """各テスト開始時にクリーンアップ時刻がリセットされていることを検証."""
        import src.cogs.bump as bump_module

        assert bump_module._bump_last_cleanup_time <= 0


# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog() -> BumpCog:
    """Create a BumpCog with a mock bot."""
    bot = MagicMock(spec=commands.Bot)
    bot.wait_until_ready = AsyncMock()
    bot.get_channel = MagicMock(return_value=None)
    bot.add_view = MagicMock()
    return BumpCog(bot)


def _make_message(
    *,
    author_id: int,
    channel_id: int,
    guild_id: int = 12345,
    embed_description: str | None = None,
    embed_title: str | None = None,
    content: str | None = None,
    interaction_user: discord.Member | None = None,
) -> MagicMock:
    """Create a mock Discord message."""
    message = MagicMock(spec=discord.Message)
    message.author = MagicMock()
    message.author.id = author_id
    message.channel = MagicMock()
    message.channel.id = channel_id
    message.guild = MagicMock()
    message.guild.id = guild_id
    message.guild.get_member = MagicMock(return_value=interaction_user)
    message.content = content

    if embed_description is not None or embed_title is not None:
        embed = MagicMock(spec=discord.Embed)
        embed.description = embed_description
        embed.title = embed_title
        message.embeds = [embed]
    else:
        message.embeds = []

    if interaction_user:
        message.interaction = MagicMock()
        message.interaction.user = interaction_user
    else:
        message.interaction = None

    return message


def _make_member(*, has_target_role: bool = True) -> MagicMock:
    """Create a mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 99999
    member.name = "TestUser"
    member.mention = "<@99999>"

    if has_target_role:
        role = MagicMock()
        role.name = TARGET_ROLE_NAME
        member.roles = [role]
    else:
        member.roles = []

    return member


def _make_reminder(
    *,
    reminder_id: int = 1,
    guild_id: str = "12345",
    channel_id: str = "456",
    service_name: str = "DISBOARD",
    is_enabled: bool = True,
    role_id: str | None = None,
) -> MagicMock:
    """Create a mock BumpReminder."""
    reminder = MagicMock()
    reminder.id = reminder_id
    reminder.guild_id = guild_id
    reminder.channel_id = channel_id
    reminder.service_name = service_name
    reminder.is_enabled = is_enabled
    reminder.role_id = role_id
    return reminder


# ---------------------------------------------------------------------------
# _detect_bump_success テスト
# ---------------------------------------------------------------------------


class TestDetectBumpSuccess:
    """Tests for _detect_bump_success."""

    def test_detects_disboard_success(self) -> None:
        """DISBOARD の bump 成功を検知する。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            embed_description=f"サーバーの{DISBOARD_SUCCESS_KEYWORD}しました！",
        )

        result = cog._detect_bump_success(message)
        assert result == "DISBOARD"

    def test_detects_dissoku_success(self) -> None:
        """ディス速報の bump 成功を検知する (description)。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_description=f"サーバーを{DISSOKU_SUCCESS_KEYWORD}しました！",
        )

        result = cog._detect_bump_success(message)
        assert result == "ディス速報"

    def test_detects_dissoku_success_in_title(self) -> None:
        """ディス速報の bump 成功を検知する (title)。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_title=f"サーバー名 を{DISSOKU_SUCCESS_KEYWORD}したよ!",
        )

        result = cog._detect_bump_success(message)
        assert result == "ディス速報"

    def test_detects_dissoku_success_in_content(self) -> None:
        """ディス速報の bump 成功を検知する (message.content)。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            content=f"🍭CHILLカフェ を{DISSOKU_SUCCESS_KEYWORD}したよ!",
        )

        result = cog._detect_bump_success(message)
        assert result == "ディス速報"

    def test_detects_dissoku_success_in_fields(self) -> None:
        """ディス速報の bump 成功を検知する (embed.fields)。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_description="<@12345>\nコマンド: `/up`",
        )
        # fields を追加（成功パターン）
        field = MagicMock()
        field.name = f"{DISSOKU_SUCCESS_KEYWORD}しました!"
        field.value = "1時間後にまたupできます"
        message.embeds[0].fields = [field]

        result = cog._detect_bump_success(message)
        assert result == "ディス速報"

    def test_detects_dissoku_success_in_field_value(self) -> None:
        """ディス速報の bump 成功を検知する (embed.fields[].value)。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_description="<@12345>\nコマンド: `/up`",
        )
        # fields の value に「アップ」が含まれるパターン
        field = MagicMock()
        field.name = "成功!"
        field.value = f"サーバーを{DISSOKU_SUCCESS_KEYWORD}しました"
        message.embeds[0].fields = [field]

        result = cog._detect_bump_success(message)
        assert result == "ディス速報"

    def test_does_not_detect_dissoku_failure_in_fields(self) -> None:
        """ディス速報の失敗メッセージは検知しない。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_description="<@12345>\nコマンド: `/up`",
        )
        # fields を追加（失敗パターン - 「アップ」が含まれない）
        field = MagicMock()
        field.name = "失敗しました..."
        field.value = "間隔をあけてください(76分)"
        message.embeds[0].fields = [field]

        result = cog._detect_bump_success(message)
        assert result is None

    def test_returns_none_for_non_bump_message(self) -> None:
        """bump 成功ではないメッセージは None を返す。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            embed_description="This is not a bump message",
        )

        result = cog._detect_bump_success(message)
        assert result is None

    def test_returns_none_for_no_embeds(self) -> None:
        """Embed がないメッセージは None を返す。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
        )

        result = cog._detect_bump_success(message)
        assert result is None

    def test_returns_none_for_wrong_bot(self) -> None:
        """DISBOARD/ディス速報以外の Bot は None を返す。"""
        cog = _make_cog()
        message = _make_message(
            author_id=12345,  # Wrong bot
            channel_id=456,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
        )

        result = cog._detect_bump_success(message)
        assert result is None


# ---------------------------------------------------------------------------
# _get_bump_user テスト
# ---------------------------------------------------------------------------


class TestGetBumpUser:
    """Tests for _get_bump_user."""

    def test_returns_member_from_interaction(self) -> None:
        """interaction.user が Member なら返す。"""
        cog = _make_cog()
        member = _make_member()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            interaction_user=member,
        )

        result = cog._get_bump_user(message)
        assert result == member

    def test_returns_none_without_interaction(self) -> None:
        """interaction がなければ None を返す。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
        )

        result = cog._get_bump_user(message)
        assert result is None

    def test_returns_member_from_guild_when_user_is_not_member(self) -> None:
        """interaction.user が User (not Member) の場合、guild.get_member で取得。"""
        cog = _make_cog()
        message = MagicMock(spec=discord.Message)

        # interaction_metadata.user が User (not Member)
        user = MagicMock(spec=discord.User)
        user.id = 12345
        message.interaction_metadata = MagicMock()
        message.interaction_metadata.user = user

        # guild.get_member で Member を返す
        member = _make_member()
        message.guild = MagicMock()
        message.guild.get_member = MagicMock(return_value=member)

        result = cog._get_bump_user(message)

        message.guild.get_member.assert_called_once_with(12345)
        assert result == member


# ---------------------------------------------------------------------------
# _has_target_role テスト
# ---------------------------------------------------------------------------


class TestHasTargetRole:
    """Tests for _has_target_role."""

    def test_returns_true_with_role(self) -> None:
        """Server Bumper ロールを持つメンバーは True。"""
        cog = _make_cog()
        member = _make_member(has_target_role=True)

        result = cog._has_target_role(member)
        assert result is True

    def test_returns_false_without_role(self) -> None:
        """Server Bumper ロールを持たないメンバーは False。"""
        cog = _make_cog()
        member = _make_member(has_target_role=False)

        result = cog._has_target_role(member)
        assert result is False


# ---------------------------------------------------------------------------
# on_message テスト
# ---------------------------------------------------------------------------


def _make_bump_config(*, guild_id: str = "12345", channel_id: str = "456") -> MagicMock:
    """Create a mock BumpConfig."""
    config = MagicMock()
    config.guild_id = guild_id
    config.channel_id = channel_id
    return config


class TestOnMessage:
    """Tests for on_message listener."""

    @pytest.fixture
    def mock_db_session(self) -> MagicMock:
        """Mock database session."""
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    async def test_skips_dm_message(self) -> None:
        """DM メッセージは無視する。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
        )
        message.guild = None  # DM

        with patch("src.cogs.bump.claim_bump_detection") as mock_claim:
            await cog.on_message(message)

        mock_claim.assert_not_called()

    async def test_skips_when_channel_not_configured(self) -> None:
        """bump 監視設定がないギルドは無視。"""
        cog = _make_cog()
        member = _make_member()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=None,  # 設定なし
            ),
            patch("src.cogs.bump.claim_bump_detection") as mock_claim,
        ):
            await cog.on_message(message)

        mock_claim.assert_not_called()

    async def test_skips_wrong_channel(self) -> None:
        """設定されたチャンネル以外は無視。"""
        cog = _make_cog()
        member = _make_member()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=999,  # 設定と異なるチャンネル
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # 設定は channel_id=456 だが、メッセージは 999
        mock_config = _make_bump_config(channel_id="456")

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch("src.cogs.bump.claim_bump_detection") as mock_claim,
        ):
            await cog.on_message(message)

        mock_claim.assert_not_called()

    async def test_skips_wrong_bot(self) -> None:
        """DISBOARD/ディス速報以外の Bot は無視。"""
        cog = _make_cog()
        member = _make_member()
        message = _make_message(
            author_id=12345,  # Wrong bot
            channel_id=456,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )

        # Bot ID が違うので get_bump_config は呼ばれない
        with patch("src.cogs.bump.claim_bump_detection") as mock_claim:
            await cog.on_message(message)

        mock_claim.assert_not_called()

    async def test_skips_user_without_role(self) -> None:
        """Server Bumper ロールを持たないユーザーは無視。"""
        cog = _make_cog()
        member = _make_member(has_target_role=False)
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_config = _make_bump_config(channel_id="456")

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch("src.cogs.bump.claim_bump_detection") as mock_claim,
        ):
            await cog.on_message(message)

        mock_claim.assert_not_called()

    async def test_creates_reminder_on_valid_bump(
        self, mock_db_session: MagicMock
    ) -> None:
        """有効な bump でリマインダーを作成し、検知 Embed と View を送信。"""
        cog = _make_cog()
        member = _make_member(has_target_role=True)
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            guild_id=12345,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )
        # チャンネルの send をモック
        message.channel.send = AsyncMock()

        # Mock config and reminder
        mock_config = _make_bump_config(guild_id="12345", channel_id="456")
        mock_reminder = _make_reminder(is_enabled=True)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_db_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.claim_bump_detection",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ) as mock_claim,
        ):
            await cog.on_message(message)

        mock_claim.assert_awaited_once()
        call_kwargs = mock_claim.call_args[1]
        assert call_kwargs["guild_id"] == "12345"
        assert call_kwargs["channel_id"] == "456"
        assert call_kwargs["service_name"] == "DISBOARD"

        # 検知 Embed と View が送信されたことを確認
        message.channel.send.assert_awaited_once()
        send_kwargs = message.channel.send.call_args[1]
        assert isinstance(send_kwargs["embed"], discord.Embed)
        assert "Bump 検知" in send_kwargs["embed"].title
        assert isinstance(send_kwargs["view"], BumpNotificationView)

    async def test_creates_reminder_shows_default_role_in_embed(
        self, mock_db_session: MagicMock
    ) -> None:
        """デフォルトロールが Embed に表示される。"""
        cog = _make_cog()
        member = _make_member(has_target_role=True)
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            guild_id=12345,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )
        message.channel.send = AsyncMock()

        mock_config = _make_bump_config(guild_id="12345", channel_id="456")
        # role_id が None = デフォルトロール
        mock_reminder = _make_reminder(is_enabled=True, role_id=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_db_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.claim_bump_detection",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ),
        ):
            await cog.on_message(message)

        send_kwargs = message.channel.send.call_args[1]
        embed = send_kwargs["embed"]
        # デフォルトロール名が表示される
        assert "現在の通知先:" in embed.description
        assert f"@{TARGET_ROLE_NAME}" in embed.description

    async def test_creates_reminder_shows_custom_role_in_embed(
        self, mock_db_session: MagicMock
    ) -> None:
        """カスタムロールが Embed に表示される。"""
        cog = _make_cog()
        member = _make_member(has_target_role=True)
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            guild_id=12345,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )
        message.channel.send = AsyncMock()

        # カスタムロールを設定
        mock_custom_role = MagicMock()
        mock_custom_role.name = "カスタムロール"
        message.guild.get_role = MagicMock(return_value=mock_custom_role)

        mock_config = _make_bump_config(guild_id="12345", channel_id="456")
        # role_id が設定されている = カスタムロール
        mock_reminder = _make_reminder(is_enabled=True, role_id="999")

        with (
            patch("src.cogs.bump.async_session", return_value=mock_db_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.claim_bump_detection",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ),
        ):
            await cog.on_message(message)

        # guild.get_role が呼ばれることを確認
        message.guild.get_role.assert_called_once_with(999)

        send_kwargs = message.channel.send.call_args[1]
        embed = send_kwargs["embed"]
        # カスタムロール名が表示される
        assert "現在の通知先:" in embed.description
        assert "@カスタムロール" in embed.description


class TestOnMessageEdit:
    """Tests for on_message_edit listener (ディス速報対応)."""

    async def test_processes_when_embed_added(self) -> None:
        """embed が後から追加された場合に検知する（ディス速報パターン）。"""
        cog = _make_cog()
        member = _make_member()

        # before: embed なし
        before = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_description=None,
            interaction_user=member,
        )
        before.embeds = []

        # after: embed あり
        after = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_description=DISSOKU_SUCCESS_KEYWORD,
            interaction_user=member,
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_config = _make_bump_config(channel_id="456")
        mock_reminder = MagicMock()
        mock_reminder.is_enabled = True
        mock_reminder.role_id = None

        after.channel.send = AsyncMock()

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.claim_bump_detection",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ) as mock_claim,
        ):
            await cog.on_message_edit(before, after)

        # リマインダーが登録される
        mock_claim.assert_called_once()
        after.channel.send.assert_called_once()

    async def test_skips_when_embed_already_exists(self) -> None:
        """before に既に embed がある場合はスキップ（重複検知防止）。"""
        cog = _make_cog()
        member = _make_member()

        # before: embed あり
        before = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_description=DISSOKU_SUCCESS_KEYWORD,
            interaction_user=member,
        )

        # after: embed あり（同じ）
        after = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_description=DISSOKU_SUCCESS_KEYWORD,
            interaction_user=member,
        )

        with patch("src.cogs.bump.claim_bump_detection") as mock_claim:
            await cog.on_message_edit(before, after)

        # 既に embed があったのでスキップ
        mock_claim.assert_not_called()

    async def test_skips_when_no_embed_added(self) -> None:
        """embed が追加されなかった場合はスキップ。"""
        cog = _make_cog()

        # before: embed なし
        before = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
        )
        before.embeds = []

        # after: embed なし（テキストのみ変更）
        after = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            content="updated text",
        )
        after.embeds = []

        with patch("src.cogs.bump.claim_bump_detection") as mock_claim:
            await cog.on_message_edit(before, after)

        # embed が追加されてないのでスキップ
        mock_claim.assert_not_called()

    async def test_detects_dissoku_success_in_fields_via_edit(self) -> None:
        """on_message_edit で fields 内の「アップ」を検知する。"""
        cog = _make_cog()
        member = _make_member()

        # before: embed なし（ディス速報の初期メッセージ）
        before = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            interaction_user=member,
        )
        before.embeds = []

        # after: embed あり（fields に「アップ」）
        after = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_description="<@12345>\nコマンド: `/up`",
            interaction_user=member,
        )
        # 成功時の fields パターン
        field = MagicMock()
        field.name = f"{DISSOKU_SUCCESS_KEYWORD}しました!"
        field.value = "1時間後にまたupできます"
        after.embeds[0].fields = [field]
        after.channel.send = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_config = _make_bump_config(channel_id="456")
        mock_reminder = MagicMock()
        mock_reminder.is_enabled = True
        mock_reminder.role_id = None

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.claim_bump_detection",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ) as mock_claim,
        ):
            await cog.on_message_edit(before, after)

        # ディス速報の bump が検知されてリマインダー登録
        mock_claim.assert_called_once()
        call_kwargs = mock_claim.call_args[1]
        assert call_kwargs["service_name"] == "ディス速報"


# ---------------------------------------------------------------------------
# _reminder_check テスト
# ---------------------------------------------------------------------------


class TestReminderCheck:
    """Tests for _reminder_check loop."""

    async def test_sends_reminder_for_due_reminders(self) -> None:
        """期限が来たリマインダーを Embed と View で送信する。"""
        cog = _make_cog()

        # Mock reminder
        reminder = _make_reminder()

        # Mock channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_channel.guild = MagicMock()
        mock_channel.guild.name = "Test Guild"
        mock_role = MagicMock()
        mock_role.mention = "@ServerVoter"

        with patch("discord.utils.get", return_value=mock_role):
            cog.bot.get_channel = MagicMock(return_value=mock_channel)

            # Mock DB session
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            with (
                patch("src.cogs.bump.async_session", return_value=mock_session),
                patch(
                    "src.cogs.bump.get_due_bump_reminders",
                    new_callable=AsyncMock,
                    return_value=[reminder],
                ),
                patch(
                    "src.cogs.bump.clear_bump_reminder", new_callable=AsyncMock
                ) as mock_clear,
            ):
                await cog._reminder_check()  # type: ignore[misc]

            mock_channel.send.assert_awaited_once()
            send_kwargs = mock_channel.send.call_args[1]
            assert send_kwargs["content"] == "@ServerVoter"
            assert isinstance(send_kwargs["embed"], discord.Embed)
            assert "Bump リマインダー" in send_kwargs["embed"].title
            assert isinstance(send_kwargs["view"], BumpNotificationView)
            mock_clear.assert_awaited_once_with(mock_session, 1)

    async def test_uses_here_when_role_not_found(self) -> None:
        """Server Bumper ロールが見つからない場合は @here を使用。"""
        cog = _make_cog()

        # Mock reminder
        reminder = _make_reminder()

        # Mock channel (no role found)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_channel.guild = MagicMock()
        mock_channel.guild.name = "Test Guild"

        with patch("discord.utils.get", return_value=None):
            cog.bot.get_channel = MagicMock(return_value=mock_channel)

            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            with (
                patch("src.cogs.bump.async_session", return_value=mock_session),
                patch(
                    "src.cogs.bump.get_due_bump_reminders",
                    new_callable=AsyncMock,
                    return_value=[reminder],
                ),
                patch("src.cogs.bump.clear_bump_reminder", new_callable=AsyncMock),
            ):
                await cog._reminder_check()  # type: ignore[misc]

            send_kwargs = mock_channel.send.call_args[1]
            assert send_kwargs["content"] == "@here"

    async def test_skips_invalid_channel(self) -> None:
        """チャンネルが見つからない場合はスキップ。"""
        cog = _make_cog()

        reminder = _make_reminder()

        # Return None for channel
        cog.bot.get_channel = MagicMock(return_value=None)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_due_bump_reminders",
                new_callable=AsyncMock,
                return_value=[reminder],
            ),
            patch(
                "src.cogs.bump.clear_bump_reminder", new_callable=AsyncMock
            ) as mock_clear,
        ):
            await cog._reminder_check()  # type: ignore[misc]

        # Should still clear the reminder
        mock_clear.assert_awaited_once()


# ---------------------------------------------------------------------------
# cog_load / cog_unload テスト
# ---------------------------------------------------------------------------


class TestCogLifecycle:
    """Tests for cog_load and cog_unload."""

    async def test_cog_load_starts_loop(self) -> None:
        """cog_load でループが開始される。"""
        cog = _make_cog()
        with patch.object(cog._reminder_check, "start") as mock_start:
            await cog.cog_load()
            mock_start.assert_called_once()

    async def test_cog_unload_cancels_loop(self) -> None:
        """cog_unload でループが停止される。"""
        cog = _make_cog()
        with (
            patch.object(cog._reminder_check, "is_running", return_value=True),
            patch.object(cog._reminder_check, "cancel") as mock_cancel,
        ):
            await cog.cog_unload()
            mock_cancel.assert_called_once()


# ---------------------------------------------------------------------------
# _before_reminder_check テスト
# ---------------------------------------------------------------------------


class TestBeforeReminderCheck:
    """Tests for _before_reminder_check."""

    async def test_waits_until_ready(self) -> None:
        """ループ開始前に wait_until_ready が呼ばれる。"""
        cog = _make_cog()
        await cog._before_reminder_check()
        cog.bot.wait_until_ready.assert_awaited_once()


# ---------------------------------------------------------------------------
# Embed 生成テスト
# ---------------------------------------------------------------------------


class TestBuildDetectionEmbed:
    """Tests for _build_detection_embed."""

    def test_detection_embed_has_correct_title(self) -> None:
        """検知 Embed のタイトルが正しい。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed("DISBOARD", member, remind_at, True)

        assert embed.title == "Bump 検知"

    def test_detection_embed_mentions_user(self) -> None:
        """検知 Embed にユーザーメンションが含まれる。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed("DISBOARD", member, remind_at, True)

        assert member.mention in (embed.description or "")

    def test_detection_embed_contains_service_name(self) -> None:
        """検知 Embed にサービス名が含まれる。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed("ディス速報", member, remind_at, True)

        assert "ディス速報" in (embed.description or "")
        assert embed.footer is not None
        assert "ディス速報" in (embed.footer.text or "")

    def test_detection_embed_shows_disabled_when_disabled(self) -> None:
        """通知無効時は「無効」と表示される。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed("DISBOARD", member, remind_at, False)

        assert "無効" in (embed.description or "")

    def test_detection_embed_shows_default_role(self) -> None:
        """デフォルトロール名が表示される。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed("DISBOARD", member, remind_at, True)

        assert "現在の通知先:" in (embed.description or "")
        assert f"@{TARGET_ROLE_NAME}" in (embed.description or "")

    def test_detection_embed_shows_custom_role(self) -> None:
        """カスタムロール名が表示される。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed(
            "DISBOARD", member, remind_at, True, role_name="カスタムロール"
        )

        assert "現在の通知先:" in (embed.description or "")
        assert "@カスタムロール" in (embed.description or "")

    def test_detection_embed_shows_custom_role_when_disabled(self) -> None:
        """通知無効時でもカスタムロール名が表示される。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        embed = cog._build_detection_embed(
            "DISBOARD", member, remind_at, False, role_name="カスタムロール"
        )

        assert "無効" in (embed.description or "")
        assert "現在の通知先:" in (embed.description or "")
        assert "@カスタムロール" in (embed.description or "")


class TestBuildReminderEmbed:
    """Tests for _build_reminder_embed."""

    def test_reminder_embed_has_correct_title(self) -> None:
        """リマインダー Embed のタイトルが正しい。"""
        cog = _make_cog()

        embed = cog._build_reminder_embed("DISBOARD")

        assert embed.title == "Bump リマインダー"

    def test_reminder_embed_contains_service_name(self) -> None:
        """リマインダー Embed にサービス名が含まれる。"""
        cog = _make_cog()

        embed = cog._build_reminder_embed("ディス速報")

        assert "ディス速報" in (embed.description or "")
        assert embed.footer is not None
        assert "ディス速報" in (embed.footer.text or "")


# ---------------------------------------------------------------------------
# BumpNotificationView テスト
# ---------------------------------------------------------------------------


class TestBumpNotificationView:
    """Tests for BumpNotificationView."""

    async def test_view_initializes_with_enabled_state(self) -> None:
        """有効状態で初期化される。"""
        view = BumpNotificationView("12345", "DISBOARD", True)

        assert view.guild_id == "12345"
        assert view.service_name == "DISBOARD"
        assert view.toggle_button.label == "通知を無効にする"
        assert view.toggle_button.style == discord.ButtonStyle.secondary

    async def test_view_initializes_with_disabled_state(self) -> None:
        """無効状態で初期化される。"""
        view = BumpNotificationView("12345", "DISBOARD", False)

        assert view.toggle_button.label == "通知を有効にする"
        assert view.toggle_button.style == discord.ButtonStyle.success

    async def test_view_has_correct_custom_id(self) -> None:
        """custom_id が正しい形式。"""
        view = BumpNotificationView("12345", "ディス速報", True)

        assert view.toggle_button.custom_id == "bump_toggle:12345:ディス速報"

    async def test_toggle_button_toggles_state(self) -> None:
        """ボタンクリックで状態が切り替わる。"""
        view = BumpNotificationView("12345", "DISBOARD", True)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.message = MagicMock()
        mock_interaction.message.edit = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.toggle_bump_reminder",
                new_callable=AsyncMock,
                return_value=False,  # Toggled to disabled
            ) as mock_toggle,
        ):
            await view.toggle_button.callback(mock_interaction)

        mock_toggle.assert_awaited_once_with(mock_session, "12345", "DISBOARD")
        mock_interaction.message.edit.assert_awaited_once()
        mock_interaction.followup.send.assert_awaited_once()

        # Button should now show "enable"
        assert view.toggle_button.label == "通知を有効にする"
        assert view.toggle_button.style == discord.ButtonStyle.success

    async def test_view_has_role_button(self) -> None:
        """ロール変更ボタンが存在する。"""
        view = BumpNotificationView("12345", "DISBOARD", True)

        assert view.role_button.label == "通知ロールを変更"
        assert view.role_button.style == discord.ButtonStyle.primary
        assert view.role_button.custom_id == "bump_role:12345:DISBOARD"


# ---------------------------------------------------------------------------
# カスタムロール使用時のテスト
# ---------------------------------------------------------------------------


class TestReminderWithCustomRole:
    """Tests for reminder sending with custom role."""

    async def test_sends_reminder_with_custom_role(self) -> None:
        """カスタムロールが設定されている場合はそのロールにメンション。"""
        cog = _make_cog()

        # Mock reminder with custom role_id
        reminder = _make_reminder(role_id="999")

        # Mock channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_channel.guild = MagicMock()
        mock_channel.guild.name = "Test Guild"

        # Mock custom role
        mock_custom_role = MagicMock()
        mock_custom_role.mention = "@CustomRole"
        mock_channel.guild.get_role = MagicMock(return_value=mock_custom_role)

        cog.bot.get_channel = MagicMock(return_value=mock_channel)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_due_bump_reminders",
                new_callable=AsyncMock,
                return_value=[reminder],
            ),
            patch("src.cogs.bump.clear_bump_reminder", new_callable=AsyncMock),
        ):
            await cog._reminder_check()  # type: ignore[misc]

        mock_channel.guild.get_role.assert_called_once_with(999)
        send_kwargs = mock_channel.send.call_args[1]
        assert send_kwargs["content"] == "@CustomRole"

    async def test_falls_back_to_default_when_custom_role_not_found(self) -> None:
        """カスタムロールが見つからない場合はデフォルトロールにフォールバック。"""
        cog = _make_cog()

        # Mock reminder with custom role_id that doesn't exist
        reminder = _make_reminder(role_id="999")

        # Mock channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_channel.guild = MagicMock()
        mock_channel.guild.name = "Test Guild"

        # Custom role not found
        mock_channel.guild.get_role = MagicMock(return_value=None)

        # Default role found
        mock_default_role = MagicMock()
        mock_default_role.mention = "@ServerVoter"

        cog.bot.get_channel = MagicMock(return_value=mock_channel)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_due_bump_reminders",
                new_callable=AsyncMock,
                return_value=[reminder],
            ),
            patch("src.cogs.bump.clear_bump_reminder", new_callable=AsyncMock),
            patch("discord.utils.get", return_value=mock_default_role),
        ):
            await cog._reminder_check()  # type: ignore[misc]

        send_kwargs = mock_channel.send.call_args[1]
        assert send_kwargs["content"] == "@ServerVoter"


# ---------------------------------------------------------------------------
# BumpRoleSelectMenu テスト
# ---------------------------------------------------------------------------


class TestBumpRoleSelectMenu:
    """Tests for BumpRoleSelectMenu."""

    async def test_menu_initializes_without_default(self) -> None:
        """デフォルト値なしで初期化。"""
        from src.cogs.bump import BumpRoleSelectMenu

        menu = BumpRoleSelectMenu("12345", "DISBOARD")

        assert menu.guild_id == "12345"
        assert menu.service_name == "DISBOARD"
        assert menu.placeholder == "通知先ロールを選択..."
        assert menu.min_values == 1
        assert menu.max_values == 1
        assert len(menu.default_values) == 0

    async def test_menu_initializes_with_default(self) -> None:
        """デフォルト値ありで初期化。"""
        from src.cogs.bump import BumpRoleSelectMenu

        menu = BumpRoleSelectMenu("12345", "DISBOARD", current_role_id="999")

        assert len(menu.default_values) == 1
        assert menu.default_values[0].id == 999
        assert menu.default_values[0].type == discord.SelectDefaultValueType.role

    async def test_menu_callback_updates_role(self) -> None:
        """ロール選択時にDBが更新される。"""
        from src.cogs.bump import BumpRoleSelectMenu

        menu = BumpRoleSelectMenu("12345", "DISBOARD")

        mock_role = MagicMock()
        mock_role.id = 999
        mock_role.name = "CustomRole"
        menu._values = [mock_role]

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.edit_message = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.update_bump_reminder_role",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            await menu.callback(mock_interaction)

        mock_update.assert_awaited_once_with(mock_session, "12345", "DISBOARD", "999")
        mock_interaction.response.edit_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.edit_message.call_args[1]
        assert "CustomRole" in call_kwargs["content"]
        assert call_kwargs["view"] is None

    async def test_menu_callback_does_nothing_without_values(self) -> None:
        """選択値がない場合は何もしない。"""
        from src.cogs.bump import BumpRoleSelectMenu

        menu = BumpRoleSelectMenu("12345", "DISBOARD")
        menu._values = []

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.edit_message = AsyncMock()

        await menu.callback(mock_interaction)

        mock_interaction.response.edit_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# BumpRoleSelectView テスト
# ---------------------------------------------------------------------------


class TestBumpRoleSelectView:
    """Tests for BumpRoleSelectView."""

    async def test_view_initializes_with_menu(self) -> None:
        """ロール選択メニューを含む。"""
        from src.cogs.bump import BumpRoleSelectMenu, BumpRoleSelectView

        view = BumpRoleSelectView("12345", "DISBOARD")

        assert view.timeout == 60
        # メニューを探す (順序は実装依存なので型で探す)
        menu = None
        for child in view.children:
            if isinstance(child, BumpRoleSelectMenu):
                menu = child
                break
        assert menu is not None
        assert menu.guild_id == "12345"
        assert menu.service_name == "DISBOARD"

    async def test_view_passes_current_role_to_menu(self) -> None:
        """現在のロールIDをメニューに渡す。"""
        from src.cogs.bump import BumpRoleSelectMenu, BumpRoleSelectView

        view = BumpRoleSelectView("12345", "DISBOARD", current_role_id="999")

        # メニューを探す
        menu = None
        for child in view.children:
            if isinstance(child, BumpRoleSelectMenu):
                menu = child
                break
        assert menu is not None
        assert len(menu.default_values) == 1
        assert menu.default_values[0].id == 999

    async def test_reset_button_resets_role(self) -> None:
        """デフォルトに戻すボタンがロールをリセット。"""
        from src.cogs.bump import BumpRoleSelectMenu, BumpRoleSelectView

        view = BumpRoleSelectView("12345", "DISBOARD")

        # メニューを見つけて service_name を確認するためのモック
        menu = None
        for child in view.children:
            if isinstance(child, BumpRoleSelectMenu):
                menu = child
                break
        assert menu is not None

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild_id = 12345  # int型
        mock_interaction.response = MagicMock()
        mock_interaction.response.edit_message = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.update_bump_reminder_role",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            await view.reset_button.callback(mock_interaction)

        # role_id=None でリセット (guild_id は str に変換される)
        mock_update.assert_awaited_once_with(mock_session, "12345", "DISBOARD", None)
        mock_interaction.response.edit_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.edit_message.call_args[1]
        assert "Server Bumper" in call_kwargs["content"]
        assert "デフォルト" in call_kwargs["content"]


# ---------------------------------------------------------------------------
# role_button callback テスト
# ---------------------------------------------------------------------------


class TestRoleButtonCallback:
    """Tests for role_button callback in BumpNotificationView."""

    async def test_role_button_shows_select_view(self) -> None:
        """ロール変更ボタンがロール選択Viewを表示。"""
        view = BumpNotificationView("12345", "DISBOARD", True)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_reminder = MagicMock()
        mock_reminder.role_id = None

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_reminder",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ),
        ):
            await view.role_button.callback(mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        assert call_kwargs["ephemeral"] is True
        assert "DISBOARD" in mock_interaction.response.send_message.call_args[0][0]

    async def test_role_button_passes_current_role(self) -> None:
        """現在のロールIDをViewに渡す。"""
        from src.cogs.bump import BumpRoleSelectMenu, BumpRoleSelectView

        view = BumpNotificationView("12345", "DISBOARD", True)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_reminder = MagicMock()
        mock_reminder.role_id = "999"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_reminder",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ),
        ):
            await view.role_button.callback(mock_interaction)

        # 送信されたViewを確認
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        sent_view = call_kwargs["view"]
        assert isinstance(sent_view, BumpRoleSelectView)

        # メニューにデフォルト値が設定されている (順序は実装依存なので型で探す)
        menu = None
        for child in sent_view.children:
            if isinstance(child, BumpRoleSelectMenu):
                menu = child
                break
        assert menu is not None
        assert len(menu.default_values) == 1
        assert menu.default_values[0].id == 999

    async def test_role_button_handles_no_reminder(self) -> None:
        """リマインダーが存在しない場合もViewを表示。"""
        view = BumpNotificationView("12345", "DISBOARD", True)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_reminder",
                new_callable=AsyncMock,
                return_value=None,  # リマインダーなし
            ),
        ):
            await view.role_button.callback(mock_interaction)

        # エラーなく実行される
        mock_interaction.response.send_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# 検知Embed の追加テスト
# ---------------------------------------------------------------------------


class TestBuildDetectionEmbedTimestamp:
    """Tests for detection embed timestamp formatting."""

    async def test_embed_contains_absolute_time(self) -> None:
        """Embedに絶対時刻が含まれる。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        member = MagicMock(spec=discord.Member)
        member.mention = "<@123>"

        embed = cog._build_detection_embed("DISBOARD", member, remind_at, True)

        # タイムスタンプ形式 <t:...:t> が含まれる
        assert "<t:" in (embed.description or "")
        assert ":t>" in (embed.description or "")

    async def test_embed_contains_time_format(self) -> None:
        """Embedに時刻が含まれる。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        member = MagicMock(spec=discord.Member)
        member.mention = "<@123>"

        embed = cog._build_detection_embed("DISBOARD", member, remind_at, True)

        # タイムスタンプ形式 <t:...:t> が含まれる
        assert ":t>" in (embed.description or "")


# ---------------------------------------------------------------------------
# _find_recent_bump テスト
# ---------------------------------------------------------------------------


class TestFindRecentBump:
    """Tests for _find_recent_bump method."""

    async def test_finds_disboard_bump(self) -> None:
        """DISBOARD の bump を検出する。"""
        from datetime import UTC, datetime
        from typing import Any

        cog = _make_cog()

        # Mock message with DISBOARD bump
        mock_message = MagicMock()
        mock_message.author = MagicMock()
        mock_message.author.id = DISBOARD_BOT_ID
        mock_embed = MagicMock()
        mock_embed.description = DISBOARD_SUCCESS_KEYWORD
        mock_message.embeds = [mock_embed]
        mock_message.created_at = datetime.now(UTC)

        # Mock channel history (discord.py uses keyword argument)
        async def mock_history(**_kwargs: Any) -> Any:
            yield mock_message

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.history = mock_history

        result = await cog._find_recent_bump(mock_channel)

        assert result is not None
        assert result[0] == "DISBOARD"
        assert result[1] == mock_message.created_at

    async def test_finds_dissoku_bump(self) -> None:
        """ディス速報の bump を検出する。"""
        from datetime import UTC, datetime
        from typing import Any

        cog = _make_cog()

        # Mock message with ディス速報 bump
        mock_message = MagicMock()
        mock_message.author = MagicMock()
        mock_message.author.id = DISSOKU_BOT_ID
        mock_embed = MagicMock()
        mock_embed.description = DISSOKU_SUCCESS_KEYWORD
        mock_message.embeds = [mock_embed]
        mock_message.created_at = datetime.now(UTC)

        async def mock_history(**_kwargs: Any) -> Any:
            yield mock_message

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.history = mock_history

        result = await cog._find_recent_bump(mock_channel)

        assert result is not None
        assert result[0] == "ディス速報"
        assert result[1] == mock_message.created_at

    async def test_returns_none_when_no_bump_found(self) -> None:
        """bump が見つからない場合は None を返す。"""
        from typing import Any

        cog = _make_cog()

        # Mock message without bump
        mock_message = MagicMock()
        mock_message.author = MagicMock()
        mock_message.author.id = 12345  # 他の Bot
        mock_message.embeds = []

        async def mock_history(**_kwargs: Any) -> Any:
            yield mock_message

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.history = mock_history

        result = await cog._find_recent_bump(mock_channel)

        assert result is None

    async def test_returns_none_on_http_exception(self) -> None:
        """HTTP エラー時は None を返す。"""
        from typing import Any

        cog = _make_cog()

        async def mock_history(**_kwargs: Any) -> Any:
            raise discord.HTTPException(MagicMock(), "Test error")
            yield  # Make it a generator

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.history = mock_history

        result = await cog._find_recent_bump(mock_channel)

        assert result is None

    async def test_returns_none_on_empty_history(self) -> None:
        """履歴が空の場合は None を返す。"""
        from typing import Any

        cog = _make_cog()

        async def mock_history(**_kwargs: Any) -> Any:
            # 何も yield しない (空のジェネレータ)
            return
            yield  # Make it a generator

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.history = mock_history

        result = await cog._find_recent_bump(mock_channel)

        assert result is None

    async def test_returns_first_bump_found(self) -> None:
        """複数の bump がある場合は最新 (最初に見つかった) ものを返す。"""
        from datetime import UTC, datetime, timedelta
        from typing import Any

        cog = _make_cog()

        # 新しい bump (1時間前)
        newer_message = MagicMock()
        newer_message.author = MagicMock()
        newer_message.author.id = DISBOARD_BOT_ID
        newer_embed = MagicMock()
        newer_embed.description = DISBOARD_SUCCESS_KEYWORD
        newer_message.embeds = [newer_embed]
        newer_message.created_at = datetime.now(UTC) - timedelta(hours=1)

        # 古い bump (5時間前)
        older_message = MagicMock()
        older_message.author = MagicMock()
        older_message.author.id = DISSOKU_BOT_ID
        older_embed = MagicMock()
        older_embed.description = DISSOKU_SUCCESS_KEYWORD
        older_message.embeds = [older_embed]
        older_message.created_at = datetime.now(UTC) - timedelta(hours=5)

        async def mock_history(**_kwargs: Any) -> Any:
            # history は新しい順に返す
            yield newer_message
            yield older_message

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.history = mock_history

        result = await cog._find_recent_bump(mock_channel)

        assert result is not None
        # 最初に見つかった (より新しい) DISBOARD の bump が返される
        assert result[0] == "DISBOARD"
        assert result[1] == newer_message.created_at


# ---------------------------------------------------------------------------
# Cog setup テスト
# ---------------------------------------------------------------------------


class TestBumpCogSetup:
    """Tests for bump cog setup function."""

    async def test_setup_registers_persistent_views(self) -> None:
        """setup が永続 View を登録する。"""
        from src.cogs.bump import setup

        mock_bot = MagicMock(spec=commands.Bot)
        mock_bot.add_view = MagicMock()
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        # 2つの永続 View が登録される (DISBOARD と ディス速報)
        assert mock_bot.add_view.call_count == 2
        mock_bot.add_cog.assert_awaited_once()

    async def test_setup_does_not_raise_without_db(self) -> None:
        """DB未接続でも setup が例外を出さずに完了する."""
        from src.cogs.bump import setup

        mock_bot = MagicMock(spec=commands.Bot)
        mock_bot.add_view = MagicMock()
        mock_bot.add_cog = AsyncMock()

        # DB モック無しで呼び出しても例外が発生しないことを検証
        await setup(mock_bot)

        assert mock_bot.add_view.call_count == 2
        mock_bot.add_cog.assert_awaited_once()


# ---------------------------------------------------------------------------
# スラッシュコマンド テスト
# ---------------------------------------------------------------------------


class TestBumpSetupCommand:
    """Tests for /bump setup command."""

    async def test_setup_creates_config(self) -> None:
        """設定を作成してメッセージを送信する。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.upsert_bump_config", new_callable=AsyncMock
            ) as mock_upsert,
        ):
            # app_commands のコマンドは .callback でコールバック関数を取得
            await cog.bump_setup.callback(cog, mock_interaction)

        mock_upsert.assert_awaited_once_with(mock_session, "12345", "456")
        mock_interaction.followup.send.assert_awaited()

    async def test_setup_requires_guild(self) -> None:
        """ギルド外では実行できない。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = None
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        await cog.bump_setup.callback(cog, mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "サーバー内" in call_args[0][0]

    async def test_setup_detects_recent_bump_and_creates_reminder(self) -> None:
        """直近の bump を検出してリマインダーを自動作成し、具体的な時刻を表示する。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()

        # 1時間前の bump
        bump_time = datetime.now(UTC) - timedelta(hours=1)
        expected_remind_at = bump_time + timedelta(hours=2)  # 2時間後にリマインド
        expected_ts = int(expected_remind_at.timestamp())

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        # TextChannel をモック
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_interaction.channel = mock_channel

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch("src.cogs.bump.upsert_bump_config", new_callable=AsyncMock),
            patch(
                "src.cogs.bump.upsert_bump_reminder", new_callable=AsyncMock
            ) as mock_upsert_reminder,
            patch.object(cog, "_find_recent_bump", new_callable=AsyncMock) as mock_find,
        ):
            mock_find.return_value = ("DISBOARD", bump_time)
            await cog.bump_setup.callback(cog, mock_interaction)

        # リマインダーが作成されることを確認
        mock_upsert_reminder.assert_awaited_once()
        call_kwargs = mock_upsert_reminder.call_args[1]
        assert call_kwargs["service_name"] == "DISBOARD"

        # Embed に直近の bump 情報が含まれる
        send_kwargs = mock_interaction.followup.send.call_args[1]
        embed = send_kwargs["embed"]
        assert "直近の bump を検出" in embed.description
        assert "リマインダーを自動設定しました" in embed.description

        # 具体的な時刻が Discord タイムスタンプ形式で表示される
        assert f"<t:{expected_ts}:t>" in embed.description  # 絶対時刻 (例: 21:30)

        # 相対時刻 (:R>) は含まれない（絶対時刻のみ表示）
        assert ":R>" not in embed.description

        # base_description にも時刻が含まれる
        assert f"<t:{expected_ts}:t> にリマインドを送信します" in embed.description

    async def test_setup_detects_bump_already_available(self) -> None:
        """既に bump 可能な場合はその旨を表示する。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()

        # 3時間前の bump (既に bump 可能)
        bump_time = datetime.now(UTC) - timedelta(hours=3)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        # TextChannel をモック
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_interaction.channel = mock_channel

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch("src.cogs.bump.upsert_bump_config", new_callable=AsyncMock),
            patch(
                "src.cogs.bump.upsert_bump_reminder", new_callable=AsyncMock
            ) as mock_upsert_reminder,
            patch.object(cog, "_find_recent_bump", new_callable=AsyncMock) as mock_find,
        ):
            mock_find.return_value = ("DISBOARD", bump_time)
            await cog.bump_setup.callback(cog, mock_interaction)

        # リマインダーは作成されない (既に bump 可能なので)
        mock_upsert_reminder.assert_not_awaited()

        # Embed に bump 可能であることが含まれる
        send_kwargs = mock_interaction.followup.send.call_args[1]
        embed = send_kwargs["embed"]
        assert "直近の bump を検出" in embed.description
        assert "現在 bump 可能です" in embed.description

    async def test_setup_no_recent_bump_found(self) -> None:
        """直近の bump がない場合は bump 情報なしで設定のみ表示する。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        # TextChannel をモック
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_interaction.channel = mock_channel

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch("src.cogs.bump.upsert_bump_config", new_callable=AsyncMock),
            patch(
                "src.cogs.bump.upsert_bump_reminder", new_callable=AsyncMock
            ) as mock_upsert_reminder,
            patch.object(cog, "_find_recent_bump", new_callable=AsyncMock) as mock_find,
        ):
            mock_find.return_value = None  # bump が見つからない
            await cog.bump_setup.callback(cog, mock_interaction)

        # リマインダーは作成されない
        mock_upsert_reminder.assert_not_awaited()

        # Embed に bump 情報が含まれない — followup.send の最初の呼び出しを検査
        send_kwargs = mock_interaction.followup.send.call_args_list[0][1]
        embed = send_kwargs["embed"]
        assert "直近の bump を検出" not in embed.description
        assert "Bump 監視を開始しました" in embed.title

        # followup: main embed + 2 notification views = 3
        assert mock_interaction.followup.send.await_count == 3

    async def test_setup_skips_history_for_non_text_channel(self) -> None:
        """TextChannel 以外ではチャンネル履歴をスキップする。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        # VoiceChannel をモック (TextChannel ではない)
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_interaction.channel = mock_channel

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.upsert_bump_config", new_callable=AsyncMock
            ) as mock_upsert,
            patch.object(cog, "_find_recent_bump", new_callable=AsyncMock) as mock_find,
        ):
            await cog.bump_setup.callback(cog, mock_interaction)

        # 設定は作成される
        mock_upsert.assert_awaited_once_with(mock_session, "12345", "456")

        # _find_recent_bump は呼ばれない
        mock_find.assert_not_awaited()

        # Embed に bump 情報が含まれない
        send_kwargs = mock_interaction.followup.send.call_args_list[0][1]
        embed = send_kwargs["embed"]
        assert "直近の bump を検出" not in embed.description

    async def test_setup_shows_notification_role(self) -> None:
        """セットアップ時に通知先ロールが表示される。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        # VoiceChannel をモック (TextChannel ではない -> 履歴検索なし)
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_interaction.channel = mock_channel

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch("src.cogs.bump.upsert_bump_config", new_callable=AsyncMock),
        ):
            await cog.bump_setup.callback(cog, mock_interaction)

        # Embed に通知先ロールが表示される
        send_kwargs = mock_interaction.followup.send.call_args_list[0][1]
        embed = send_kwargs["embed"]
        assert "現在の通知先:" in embed.description
        assert f"@{TARGET_ROLE_NAME}" in embed.description

    async def test_setup_shows_custom_notification_role(self) -> None:
        """セットアップ時にカスタム通知先ロールが表示される。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()

        # 1時間前の bump
        bump_time = datetime.now(UTC) - timedelta(hours=1)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.channel_id = 456
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        # カスタムロールを設定
        mock_custom_role = MagicMock()
        mock_custom_role.name = "カスタムロール"
        mock_interaction.guild.get_role = MagicMock(return_value=mock_custom_role)

        # TextChannel をモック
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_interaction.channel = mock_channel

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # リマインダーにカスタムロールが設定されている
        mock_reminder = _make_reminder(role_id="999")

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch("src.cogs.bump.upsert_bump_config", new_callable=AsyncMock),
            patch(
                "src.cogs.bump.upsert_bump_reminder",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ),
            patch.object(cog, "_find_recent_bump", new_callable=AsyncMock) as mock_find,
        ):
            mock_find.return_value = ("DISBOARD", bump_time)
            await cog.bump_setup.callback(cog, mock_interaction)

        # Embed にカスタムロール名が表示される
        send_kwargs = mock_interaction.followup.send.call_args[1]
        embed = send_kwargs["embed"]
        assert "現在の通知先:" in embed.description
        assert "@カスタムロール" in embed.description


class TestBumpStatusCommand:
    """Tests for /bump status command."""

    async def test_status_shows_config(self) -> None:
        """設定がある場合は表示する。"""
        from datetime import UTC, datetime

        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.guild.get_role = MagicMock(return_value=None)
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_config = MagicMock()
        mock_config.channel_id = "456"
        mock_config.created_at = datetime.now(UTC)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.get_bump_reminder",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.bump_status.callback(cog, mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        assert "<#456>" in embed.description

    async def test_status_shows_not_configured(self) -> None:
        """設定がない場合はその旨を表示する。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.cogs.bump.get_bump_reminder",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.bump_status.callback(cog, mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        assert "設定されていません" in embed.description

    async def test_status_shows_notification_roles(self) -> None:
        """通知先ロールが表示される。"""
        from datetime import UTC, datetime

        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        # カスタムロールを設定
        mock_custom_role = MagicMock()
        mock_custom_role.name = "カスタムロール"
        mock_interaction.guild.get_role = MagicMock(return_value=mock_custom_role)

        mock_config = MagicMock()
        mock_config.channel_id = "456"
        mock_config.created_at = datetime.now(UTC)

        # DISBOARD はカスタムロール, ディス速報はデフォルト
        mock_disboard_reminder = _make_reminder(service_name="DISBOARD", role_id="999")
        mock_dissoku_reminder = None  # ディス速報はリマインダーなし

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        async def mock_get_reminder(
            _session: MagicMock, _guild_id: str, service_name: str
        ) -> MagicMock | None:
            if service_name == "DISBOARD":
                return mock_disboard_reminder
            return mock_dissoku_reminder

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.get_bump_reminder",
                new=AsyncMock(side_effect=mock_get_reminder),
            ),
        ):
            await cog.bump_status.callback(cog, mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]

        # 通知先ロールが表示される
        assert "通知先ロール" in embed.description
        assert "DISBOARD" in embed.description
        assert "ディス速報" in embed.description
        # カスタムロール名が表示される
        assert "カスタムロール" in embed.description
        # デフォルトロールも表示される
        assert "Server Bumper" in embed.description


class TestBumpDisableCommand:
    """Tests for /bump disable command."""

    async def test_disable_deletes_config(self) -> None:
        """設定を削除する。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.delete_bump_config",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_delete,
        ):
            await cog.bump_disable.callback(cog, mock_interaction)

        mock_delete.assert_awaited_once_with(mock_session, "12345")
        mock_interaction.response.send_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        assert "停止しました" in embed.title

    async def test_disable_shows_already_disabled(self) -> None:
        """既に無効の場合はその旨を表示する。"""
        cog = _make_cog()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild = MagicMock()
        mock_interaction.guild.id = 12345
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.delete_bump_config",
                new_callable=AsyncMock,
                return_value=False,  # 既に無効
            ),
        ):
            await cog.bump_disable.callback(cog, mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        embed = call_kwargs["embed"]
        assert "既に無効" in embed.description


# ---------------------------------------------------------------------------
# Faker を使ったテスト
# ---------------------------------------------------------------------------

from faker import Faker  # noqa: E402

fake = Faker("ja_JP")


def _snowflake() -> str:
    """Discord snowflake 風の ID を生成する。"""
    return str(fake.random_number(digits=18, fix_len=True))


class TestBumpWithFaker:
    """Faker を使ったランダムデータでのテスト。"""

    async def test_on_message_with_random_ids(self) -> None:
        """ランダムなIDでon_messageをテスト。"""
        cog = _make_cog()
        guild_id = int(_snowflake())
        channel_id = int(_snowflake())

        member = _make_member(has_target_role=True)
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=channel_id,
            guild_id=guild_id,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )
        message.channel.send = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_config = _make_bump_config(
            guild_id=str(guild_id), channel_id=str(channel_id)
        )
        mock_reminder = _make_reminder(is_enabled=True)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.claim_bump_detection",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ) as mock_claim,
        ):
            await cog.on_message(message)

        mock_claim.assert_awaited_once()
        call_kwargs = mock_claim.call_args[1]
        assert call_kwargs["guild_id"] == str(guild_id)
        assert call_kwargs["channel_id"] == str(channel_id)

    async def test_reminder_with_random_service(self) -> None:
        """ランダムなサービス名でリマインダーをテスト。"""
        service = fake.random_element(elements=["DISBOARD", "ディス速報"])
        cog = _make_cog()

        embed = cog._build_reminder_embed(service)

        assert service in (embed.description or "")
        assert embed.footer is not None
        assert service in (embed.footer.text or "")

    async def test_detection_embed_with_random_data(self) -> None:
        """ランダムなデータで検知Embedをテスト。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()

        member = MagicMock(spec=discord.Member)
        member.id = int(_snowflake())
        member.name = fake.user_name()
        member.mention = f"<@{member.id}>"

        service = fake.random_element(elements=["DISBOARD", "ディス速報"])
        remind_at = datetime.now(UTC) + timedelta(hours=fake.random_int(min=1, max=2))
        is_enabled = fake.boolean()

        embed = cog._build_detection_embed(service, member, remind_at, is_enabled)

        assert member.mention in (embed.description or "")
        assert service in (embed.description or "")
        if not is_enabled:
            assert "無効" in (embed.description or "")


class TestBumpWithParameterize:
    """pytest.mark.parametrize を使ったテスト。"""

    @pytest.mark.parametrize(
        "service_name,bot_id,keyword",
        [
            ("DISBOARD", DISBOARD_BOT_ID, DISBOARD_SUCCESS_KEYWORD),
            ("ディス速報", DISSOKU_BOT_ID, DISSOKU_SUCCESS_KEYWORD),
        ],
    )
    def test_detect_bump_success_for_each_service(
        self, service_name: str, bot_id: int, keyword: str
    ) -> None:
        """各サービスのbump成功検知をテスト。"""
        cog = _make_cog()
        message = _make_message(
            author_id=bot_id,
            channel_id=456,
            embed_description=f"サーバーを{keyword}しました！",
        )

        result = cog._detect_bump_success(message)
        assert result == service_name

    @pytest.mark.parametrize(
        "is_enabled,expected_label",
        [
            (True, "通知を無効にする"),
            (False, "通知を有効にする"),
        ],
    )
    async def test_notification_view_button_label(
        self, is_enabled: bool, expected_label: str
    ) -> None:
        """通知状態に応じたボタンラベルをテスト。"""
        view = BumpNotificationView("12345", "DISBOARD", is_enabled)
        assert view.toggle_button.label == expected_label

    @pytest.mark.parametrize(
        "has_role,should_process",
        [
            (True, True),
            (False, False),
        ],
    )
    def test_has_target_role_check(self, has_role: bool, should_process: bool) -> None:
        """ロール有無によるフィルタリングをテスト。"""
        cog = _make_cog()
        member = _make_member(has_target_role=has_role)

        result = cog._has_target_role(member)
        assert result == should_process

    @pytest.mark.parametrize("service_name", ["DISBOARD", "ディス速報"])
    def test_reminder_embed_for_each_service(self, service_name: str) -> None:
        """各サービスのリマインダーEmbedをテスト。"""
        cog = _make_cog()

        embed = cog._build_reminder_embed(service_name)

        assert embed.title == "Bump リマインダー"
        assert service_name in (embed.description or "")

    @pytest.mark.parametrize(
        "role_id,expected_in_embed",
        [
            (None, TARGET_ROLE_NAME),
            ("999", "カスタム"),
        ],
    )
    async def test_reminder_role_display(
        self, role_id: str | None, expected_in_embed: str
    ) -> None:
        """リマインダーのロール表示をテスト。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()
        member = _make_member()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        role_name = "カスタムロール" if role_id else None
        embed = cog._build_detection_embed(
            "DISBOARD", member, remind_at, True, role_name=role_name
        )

        assert expected_in_embed in (embed.description or "")


# ---------------------------------------------------------------------------
# 追加テスト: 未カバー行のテスト
# ---------------------------------------------------------------------------


class TestBumpRoleSelectViewResetButton:
    """BumpRoleSelectView のリセットボタンテスト。"""

    async def test_reset_button_returns_when_no_menu_found(self) -> None:
        """メニューが見つからない場合は早期リターン。"""
        from src.cogs.bump import BumpRoleSelectView

        view = BumpRoleSelectView("12345", "DISBOARD", None)
        # メニューを強制的に削除
        view.clear_items()

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild_id = 12345
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()

        # エラーが発生しないことを確認
        await view.reset_button.callback(interaction)

        # edit_message は呼ばれない (早期リターン)
        interaction.response.edit_message.assert_not_called()


class TestCogUnloadWhenNotRunning:
    """cog_unload でループが実行中でない場合のテスト。"""

    async def test_cog_unload_when_loop_not_running(self) -> None:
        """ループが実行中でない場合、cancel は呼ばれない。"""
        cog = _make_cog()
        cog._reminder_check.is_running = MagicMock(return_value=False)
        cog._reminder_check.cancel = MagicMock()

        await cog.cog_unload()

        cog._reminder_check.cancel.assert_not_called()


class TestProcessBumpMessageNoEmbeds:
    """_process_bump_message で embed もコンテンツもない場合のテスト。"""

    @patch("src.cogs.bump.async_session")
    async def test_returns_early_when_no_embeds_and_no_content(
        self, mock_session: MagicMock
    ) -> None:
        """embed もコンテンツもない場合は早期リターン。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            guild_id=12345,
        )
        message.embeds = []
        message.content = None

        await cog._process_bump_message(message)

        # DB アクセスは発生しない
        mock_session.assert_not_called()


class TestProcessBumpMessageNoUser:
    """_process_bump_message で bump ユーザーを取得できない場合のテスト。"""

    @patch("src.cogs.bump.async_session")
    @patch("src.cogs.bump.get_bump_config")
    async def test_returns_early_when_no_bump_user(
        self, mock_get_config: MagicMock, mock_session: MagicMock
    ) -> None:
        """bump ユーザーを取得できない場合は早期リターン。"""
        cog = _make_cog()

        # bump 成功のメッセージを作成 (interaction_metadata なし)
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            guild_id=12345,
            embed_description=f"サーバーの{DISBOARD_SUCCESS_KEYWORD}しました！",
        )
        message.interaction_metadata = None

        # 設定あり
        config = MagicMock()
        config.channel_id = "456"
        mock_get_config.return_value = config

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        await cog._process_bump_message(message)


class TestProcessBumpMessageHttpException:
    """_process_bump_message で HTTPException が発生する場合のテスト。"""

    @patch("src.cogs.bump.async_session")
    @patch("src.cogs.bump.get_bump_config")
    @patch("src.cogs.bump.claim_bump_detection")
    async def test_handles_http_exception_when_sending(
        self,
        mock_claim: MagicMock,
        mock_get_config: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Embed 送信時の HTTPException を処理。"""
        cog = _make_cog()

        member = _make_member()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            guild_id=12345,
            embed_description=f"サーバーの{DISBOARD_SUCCESS_KEYWORD}しました！",
            interaction_user=member,
        )
        message.interaction_metadata = MagicMock()
        message.interaction_metadata.user = member
        message.channel.send = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "Error")
        )

        config = MagicMock()
        config.channel_id = "456"
        mock_get_config.return_value = config

        reminder = MagicMock()
        reminder.is_enabled = True
        reminder.role_id = None
        mock_claim.return_value = reminder

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        # エラーが発生してもクラッシュしない
        await cog._process_bump_message(message)


class TestGetBumpUserNotMember:
    """_get_bump_user で interaction_metadata.user が Member でない場合のテスト。"""

    def test_returns_none_when_get_member_returns_none(self) -> None:
        """guild.get_member が None を返す場合は None。"""
        cog = _make_cog()

        # discord.User を返す (Member ではない)
        user = MagicMock(spec=discord.User)
        user.id = 12345

        message = MagicMock(spec=discord.Message)
        message.interaction_metadata = MagicMock()
        message.interaction_metadata.user = user
        message.guild = MagicMock()
        message.guild.get_member = MagicMock(return_value=None)

        result = cog._get_bump_user(message)
        assert result is None


class TestSendReminderHttpException:
    """_send_reminder で HTTPException が発生する場合のテスト。"""

    async def test_handles_http_exception(self) -> None:
        """リマインダー送信時の HTTPException を処理。"""
        cog = _make_cog()

        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = MagicMock()
        channel.guild.get_role = MagicMock(return_value=None)
        channel.guild.roles = []
        channel.send = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "Error")
        )

        cog.bot.get_channel = MagicMock(return_value=channel)

        reminder = _make_reminder()

        # エラーが発生してもクラッシュしない
        await cog._send_reminder(reminder)


class TestBumpStatusNoGuild:
    """bump_status で guild がない場合のテスト。"""

    async def test_returns_error_when_no_guild(self) -> None:
        """guild がない場合はエラーメッセージ。"""
        cog = _make_cog()

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await cog.bump_status.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        call_kwargs = interaction.response.send_message.call_args[1]
        assert "サーバー内でのみ" in call_kwargs.get("content", "") or any(
            "サーバー内でのみ" in str(arg)
            for arg in interaction.response.send_message.call_args[0]
        )


class TestBumpDisableNoGuild:
    """bump_disable で guild がない場合のテスト。"""

    async def test_returns_error_when_no_guild(self) -> None:
        """guild がない場合はエラーメッセージ。"""
        cog = _make_cog()

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await cog.bump_disable.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()


class TestBumpSetupWithRecentBump:
    """bump_setup で直近の bump を検出した場合のテスト。"""

    @patch("src.cogs.bump.async_session")
    @patch("src.cogs.bump.upsert_bump_config")
    @patch("src.cogs.bump.upsert_bump_reminder")
    async def test_detects_recent_bump_with_custom_role(
        self,
        mock_upsert_reminder: MagicMock,
        mock_upsert_config: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """直近の bump 検出時にカスタムロールがある場合のテスト。"""
        from datetime import UTC, datetime, timedelta

        cog = _make_cog()

        # カスタムロールがあるリマインダー
        reminder = MagicMock()
        reminder.is_enabled = True
        reminder.role_id = "999"
        mock_upsert_reminder.return_value = reminder

        # ロールを取得できる
        custom_role = MagicMock()
        custom_role.name = "カスタムBumper"

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock()
        interaction.guild.id = 12345
        interaction.guild.get_role = MagicMock(return_value=custom_role)
        interaction.channel = MagicMock(spec=discord.TextChannel)
        interaction.channel_id = 456
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        # _find_recent_bump のモック (bump 検出)
        bump_time = datetime.now(UTC) - timedelta(hours=1)
        cog._find_recent_bump = AsyncMock(return_value=("DISBOARD", bump_time))

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        await cog.bump_setup.callback(cog, interaction)

        interaction.followup.send.assert_called_once()


# ---------------------------------------------------------------------------
# Bump 通知設定クールダウンテスト
# ---------------------------------------------------------------------------


class TestBumpNotificationCooldown:
    """Bump 通知設定クールダウンの単体テスト。"""

    def test_first_action_not_on_cooldown(self) -> None:
        """最初の操作はクールダウンされない."""
        user_id = 12345
        guild_id = "67890"
        service_name = "DISBOARD"

        result = is_bump_notification_on_cooldown(user_id, guild_id, service_name)

        assert result is False

    def test_immediate_second_action_on_cooldown(self) -> None:
        """直後の操作はクールダウンされる."""
        user_id = 12345
        guild_id = "67890"
        service_name = "DISBOARD"

        # 1回目 (クールダウンを記録)
        is_bump_notification_on_cooldown(user_id, guild_id, service_name)

        # 即座に2回目
        result = is_bump_notification_on_cooldown(user_id, guild_id, service_name)

        assert result is True

    def test_different_user_not_affected(self) -> None:
        """異なるユーザーはクールダウンの影響を受けない."""
        user_id_1 = 12345
        user_id_2 = 67890
        guild_id = "11111"
        service_name = "DISBOARD"

        # ユーザー1が操作
        is_bump_notification_on_cooldown(user_id_1, guild_id, service_name)

        # ユーザー2は影響を受けない
        result = is_bump_notification_on_cooldown(user_id_2, guild_id, service_name)

        assert result is False

    def test_different_guild_not_affected(self) -> None:
        """異なるギルドはクールダウンの影響を受けない."""
        user_id = 12345
        guild_id_1 = "11111"
        guild_id_2 = "22222"
        service_name = "DISBOARD"

        # ギルド1で操作
        is_bump_notification_on_cooldown(user_id, guild_id_1, service_name)

        # ギルド2は影響を受けない
        result = is_bump_notification_on_cooldown(user_id, guild_id_2, service_name)

        assert result is False

    def test_different_service_not_affected(self) -> None:
        """異なるサービスはクールダウンの影響を受けない."""
        user_id = 12345
        guild_id = "11111"
        service_name_1 = "DISBOARD"
        service_name_2 = "ディス速報"

        # DISBOARD で操作
        is_bump_notification_on_cooldown(user_id, guild_id, service_name_1)

        # ディス速報は影響を受けない
        result = is_bump_notification_on_cooldown(user_id, guild_id, service_name_2)

        assert result is False

    def test_cooldown_expires(self) -> None:
        """クールダウン時間経過後は再度操作できる."""
        import time
        from unittest.mock import patch as mock_patch

        user_id = 12345
        guild_id = "67890"
        service_name = "DISBOARD"

        # 1回目
        is_bump_notification_on_cooldown(user_id, guild_id, service_name)

        # time.monotonic をモックしてクールダウン時間経過をシミュレート
        original_time = time.monotonic()
        with mock_patch(
            "src.cogs.bump.time.monotonic",
            return_value=original_time + BUMP_NOTIFICATION_COOLDOWN_SECONDS + 0.1,
        ):
            result = is_bump_notification_on_cooldown(user_id, guild_id, service_name)

        assert result is False

    def test_clear_cooldown_cache(self) -> None:
        """クールダウンキャッシュをクリアできる."""
        user_id = 12345
        guild_id = "67890"
        service_name = "DISBOARD"

        # クールダウンを設定
        is_bump_notification_on_cooldown(user_id, guild_id, service_name)
        assert is_bump_notification_on_cooldown(user_id, guild_id, service_name) is True

        # キャッシュをクリア
        clear_bump_notification_cooldown_cache()

        # クリア後はクールダウンされない
        assert (
            is_bump_notification_on_cooldown(user_id, guild_id, service_name) is False
        )

    def test_cooldown_constant_value(self) -> None:
        """クールダウン時間が適切に設定されている."""
        assert BUMP_NOTIFICATION_COOLDOWN_SECONDS == 3


class TestBumpNotificationCooldownIntegration:
    """Bump 通知設定クールダウンの統合テスト (BumpNotificationView との連携)."""

    async def test_toggle_button_rejects_when_on_cooldown(self) -> None:
        """クールダウン中にトグルボタンを押すとエラーメッセージが返される."""
        view = BumpNotificationView("12345", "DISBOARD", True)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.user = MagicMock()
        mock_interaction.user.id = 99999
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        # 1回目のクールダウンを記録
        is_bump_notification_on_cooldown(99999, "12345", "DISBOARD")

        # 2回目の操作 (クールダウン中)
        await view.toggle_button.callback(mock_interaction)

        # エラーメッセージが送信される
        mock_interaction.response.send_message.assert_awaited_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "操作が早すぎます" in call_args.args[0]
        assert call_args.kwargs.get("ephemeral") is True

    async def test_role_button_rejects_when_on_cooldown(self) -> None:
        """クールダウン中にロールボタンを押すとエラーメッセージが返される."""
        view = BumpNotificationView("12345", "DISBOARD", True)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.user = MagicMock()
        mock_interaction.user.id = 99999
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        # 1回目のクールダウンを記録
        is_bump_notification_on_cooldown(99999, "12345", "DISBOARD")

        # 2回目の操作 (クールダウン中)
        await view.role_button.callback(mock_interaction)

        # エラーメッセージが送信される
        mock_interaction.response.send_message.assert_awaited_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "操作が早すぎます" in call_args.args[0]
        assert call_args.kwargs.get("ephemeral") is True

    async def test_toggle_button_allows_first_action(self) -> None:
        """最初のトグル操作は許可される."""
        view = BumpNotificationView("12345", "DISBOARD", True)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.user = MagicMock()
        mock_interaction.user.id = 88888
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.message = MagicMock()
        mock_interaction.message.edit = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.toggle_bump_reminder",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            await view.toggle_button.callback(mock_interaction)

        # 正常にトグル操作が行われる
        mock_interaction.message.edit.assert_awaited_once()
        mock_interaction.followup.send.assert_awaited_once()

    async def test_different_users_can_operate_simultaneously(self) -> None:
        """異なるユーザーは同時に操作できる."""
        view = BumpNotificationView("12345", "DISBOARD", True)

        # ユーザー1がクールダウン状態になる
        is_bump_notification_on_cooldown(11111, "12345", "DISBOARD")

        # ユーザー2の interaction
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.user = MagicMock()
        mock_interaction.user.id = 22222
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.message = MagicMock()
        mock_interaction.message.edit = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.toggle_bump_reminder",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            await view.toggle_button.callback(mock_interaction)

        # ユーザー2は操作可能
        mock_interaction.message.edit.assert_awaited_once()


# ---------------------------------------------------------------------------
# ロック + クールダウン二重保護統合テスト
# ---------------------------------------------------------------------------


class TestBumpNotificationLockCooldownIntegration:
    """Bump 通知のロック + クールダウン二重保護の統合テスト."""

    async def test_lock_serializes_same_guild_service_operations(self) -> None:
        """同じギルド・サービスの操作はロックによりシリアライズされる."""
        from src.utils import get_resource_lock

        execution_order: list[str] = []

        async def mock_toggle_operation(name: str, guild_id: str, service: str) -> None:
            async with get_resource_lock(f"bump_notification:{guild_id}:{service}"):
                execution_order.append(f"start_{name}")
                await asyncio.sleep(0.01)
                execution_order.append(f"end_{name}")

        # 同じギルド・サービスで並行操作
        await asyncio.gather(
            mock_toggle_operation("A", "12345", "DISBOARD"),
            mock_toggle_operation("B", "12345", "DISBOARD"),
        )

        # シリアライズされているため、start-end が連続
        assert len(execution_order) == 4
        assert execution_order[0].startswith("start_")
        assert execution_order[1].startswith("end_")
        assert execution_order[0][6:] == execution_order[1][4:]

    async def test_lock_allows_parallel_for_different_services(self) -> None:
        """異なるサービスの操作は並列実行可能."""
        from src.utils import get_resource_lock

        execution_order: list[str] = []

        async def mock_toggle_operation(name: str, guild_id: str, service: str) -> None:
            async with get_resource_lock(f"bump_notification:{guild_id}:{service}"):
                execution_order.append(f"start_{name}_{service}")
                await asyncio.sleep(0.01)
                execution_order.append(f"end_{name}_{service}")

        # 同じギルドだが異なるサービスで並行操作
        await asyncio.gather(
            mock_toggle_operation("A", "12345", "DISBOARD"),
            mock_toggle_operation("B", "12345", "ディス速報"),
        )

        # 両方とも完了
        assert len(execution_order) == 4

    async def test_lock_allows_parallel_for_different_guilds(self) -> None:
        """異なるギルドの操作は並列実行可能."""
        from src.utils import get_resource_lock

        execution_order: list[str] = []

        async def mock_toggle_operation(name: str, guild_id: str, service: str) -> None:
            async with get_resource_lock(f"bump_notification:{guild_id}:{service}"):
                execution_order.append(f"start_{name}_{guild_id}")
                await asyncio.sleep(0.01)
                execution_order.append(f"end_{name}_{guild_id}")

        # 異なるギルドで並行操作
        await asyncio.gather(
            mock_toggle_operation("A", "111", "DISBOARD"),
            mock_toggle_operation("B", "222", "DISBOARD"),
        )

        # 両方とも完了
        assert len(execution_order) == 4

    async def test_lock_key_format_matches_implementation(self) -> None:
        """ロックキーの形式が実装と一致することを確認."""
        from src.utils import get_resource_lock

        guild_id = "12345"
        service_name = "DISBOARD"
        expected_key = f"bump_notification:{guild_id}:{service_name}"

        # 同じキーで2回ロックを取得すると同じロックインスタンス
        lock1 = get_resource_lock(expected_key)
        lock2 = get_resource_lock(expected_key)
        assert lock1 is lock2


# =============================================================================
# クリーンアップリスナーのテスト
# =============================================================================


class TestOnGuildChannelDelete:
    """on_guild_channel_delete リスナーのテスト。"""

    @patch("src.cogs.bump.async_session")
    @patch("src.cogs.bump.get_bump_config")
    @patch("src.cogs.bump.delete_bump_config")
    @patch("src.cogs.bump.delete_bump_reminders_by_guild")
    async def test_deletes_config_when_channel_matches(
        self,
        mock_delete_reminders: AsyncMock,
        mock_delete_config: AsyncMock,
        mock_get_config: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """監視チャンネルが削除された場合、設定を削除する。"""
        cog = _make_cog()

        # モックセットアップ
        mock_config = MagicMock()
        mock_config.channel_id = "456"
        mock_get_config.return_value = mock_config
        mock_delete_reminders.return_value = 2

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        # チャンネル削除イベント
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 456
        channel.guild = MagicMock()
        channel.guild.id = 789

        await cog.on_guild_channel_delete(channel)

        mock_get_config.assert_called_once()
        mock_delete_config.assert_called_once()
        mock_delete_reminders.assert_called_once()

    @patch("src.cogs.bump.async_session")
    @patch("src.cogs.bump.get_bump_config")
    @patch("src.cogs.bump.delete_bump_config")
    async def test_does_not_delete_when_channel_does_not_match(
        self,
        mock_delete_config: AsyncMock,
        mock_get_config: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """監視チャンネル以外が削除された場合、設定を削除しない。"""
        cog = _make_cog()

        # モックセットアップ - 異なるチャンネル ID
        mock_config = MagicMock()
        mock_config.channel_id = "999"  # 削除されたチャンネルとは異なる
        mock_get_config.return_value = mock_config

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 456
        channel.guild = MagicMock()
        channel.guild.id = 789

        await cog.on_guild_channel_delete(channel)

        mock_get_config.assert_called_once()
        mock_delete_config.assert_not_called()

    @patch("src.cogs.bump.async_session")
    @patch("src.cogs.bump.get_bump_config")
    @patch("src.cogs.bump.delete_bump_config")
    async def test_does_not_delete_when_no_config(
        self,
        mock_delete_config: AsyncMock,
        mock_get_config: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """設定が存在しない場合、何もしない。"""
        cog = _make_cog()

        mock_get_config.return_value = None

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 456
        channel.guild = MagicMock()
        channel.guild.id = 789

        await cog.on_guild_channel_delete(channel)

        mock_get_config.assert_called_once()
        mock_delete_config.assert_not_called()


class TestOnGuildRemove:
    """on_guild_remove リスナーのテスト。"""

    @patch("src.cogs.bump.async_session")
    @patch("src.cogs.bump.delete_bump_config")
    @patch("src.cogs.bump.delete_bump_reminders_by_guild")
    async def test_deletes_all_bump_data(
        self,
        mock_delete_reminders: AsyncMock,
        mock_delete_config: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """ギルド削除時に全ての bump データを削除する。"""
        cog = _make_cog()

        mock_delete_reminders.return_value = 3

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        guild = MagicMock(spec=discord.Guild)
        guild.id = 789

        await cog.on_guild_remove(guild)

        mock_delete_config.assert_called_once()
        mock_delete_reminders.assert_called_once()

    @patch("src.cogs.bump.async_session")
    @patch("src.cogs.bump.delete_bump_config")
    @patch("src.cogs.bump.delete_bump_reminders_by_guild")
    async def test_handles_no_reminders(
        self,
        mock_delete_reminders: AsyncMock,
        mock_delete_config: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """リマインダーがない場合も正常に動作する。"""
        cog = _make_cog()

        mock_delete_reminders.return_value = 0

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        guild = MagicMock(spec=discord.Guild)
        guild.id = 789

        await cog.on_guild_remove(guild)

        mock_delete_config.assert_called_once()
        mock_delete_reminders.assert_called_once()


# ---------------------------------------------------------------------------
# クールダウンキャッシュの自動クリーンアップテスト
# ---------------------------------------------------------------------------


class TestBumpNotificationCooldownAutoCleanup:
    """Bump 通知クールダウンキャッシュの自動クリーンアップテスト."""

    def test_cleanup_removes_old_entries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """古いエントリがクリーンアップされる."""
        import time

        import src.cogs.bump as bump_module

        # 古いエントリを追加
        old_time = time.monotonic() - 400  # 5分以上前
        _bump_notification_cooldown_cache[(12345, "67890", "DISBOARD")] = old_time

        # 最終クリーンアップ時刻を古くする (クリーンアップ間隔より前に設定)
        monkeypatch.setattr(
            bump_module, "_bump_last_cleanup_time", time.monotonic() - 700
        )

        # クリーンアップをトリガー (新しいクールダウンチェック)
        is_bump_notification_on_cooldown(99999, "11111", "DISBOARD")

        # 古いエントリは削除される
        assert (12345, "67890", "DISBOARD") not in _bump_notification_cooldown_cache

    def test_cleanup_preserves_recent_entries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """最近のエントリはクリーンアップされない."""
        import time

        import src.cogs.bump as bump_module

        # 最近のエントリを追加
        recent_time = time.monotonic() - 10  # 10秒前
        _bump_notification_cooldown_cache[(12345, "67890", "DISBOARD")] = recent_time

        # 最終クリーンアップ時刻を古くする (クリーンアップ間隔より前に設定)
        monkeypatch.setattr(
            bump_module, "_bump_last_cleanup_time", time.monotonic() - 700
        )

        # クリーンアップをトリガー
        _cleanup_bump_notification_cooldown_cache()

        # 最近のエントリは残る
        assert (12345, "67890", "DISBOARD") in _bump_notification_cooldown_cache

    def test_cleanup_interval_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """クリーンアップ間隔が尊重される."""
        import time

        import src.cogs.bump as bump_module

        # 古いエントリを追加
        old_time = time.monotonic() - 400
        _bump_notification_cooldown_cache[(12345, "67890", "DISBOARD")] = old_time

        # 最終クリーンアップ時刻を最近に設定 (間隔未経過)
        monkeypatch.setattr(
            bump_module, "_bump_last_cleanup_time", time.monotonic() - 1
        )

        # クリーンアップは実行されない
        _cleanup_bump_notification_cooldown_cache()

        # エントリはまだ残っている
        assert (12345, "67890", "DISBOARD") in _bump_notification_cooldown_cache


# ---------------------------------------------------------------------------
# Cooldown 境界値テスト
# ---------------------------------------------------------------------------


class TestBumpCooldownBoundary:
    """Bump 通知クールダウンの境界値テスト."""

    def test_cooldown_exact_boundary_still_active(self) -> None:
        """クールダウン期間のちょうど手前 (0.001秒残り) はまだクールダウン中."""
        import time

        user_id = 11111
        guild_id = "22222"
        svc = "DISBOARD"

        # クールダウン期間の0.001秒手前に設定
        _bump_notification_cooldown_cache[(user_id, guild_id, svc)] = (
            time.monotonic() - BUMP_NOTIFICATION_COOLDOWN_SECONDS + 0.001
        )

        result = is_bump_notification_on_cooldown(user_id, guild_id, svc)
        assert result is True

    def test_cooldown_just_expired(self) -> None:
        """クールダウン期間を0.001秒超過したらクールダウン解除."""
        import time

        user_id = 11111
        guild_id = "22222"
        svc = "DISBOARD"

        # クールダウン期間の0.001秒超過に設定
        _bump_notification_cooldown_cache[(user_id, guild_id, svc)] = (
            time.monotonic() - BUMP_NOTIFICATION_COOLDOWN_SECONDS - 0.001
        )

        result = is_bump_notification_on_cooldown(user_id, guild_id, svc)
        assert result is False

        # キャッシュが再記録されていることを確認
        key = (user_id, guild_id, svc)
        assert key in _bump_notification_cooldown_cache
        # 再記録された値は現在時刻に近い (1秒以内)
        assert time.monotonic() - _bump_notification_cooldown_cache[key] < 1.0

    def test_cleanup_keeps_active_removes_expired(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """クリーンアップで期限切れエントリは削除、アクティブは保持."""
        import time

        import src.cogs.bump as bump_module

        # 期限切れエントリ (400秒前 > _BUMP_CLEANUP_INTERVAL=300秒)
        expired_key = (11111, "22222", "DISBOARD")
        _bump_notification_cooldown_cache[expired_key] = time.monotonic() - 400

        # アクティブなエントリ (今)
        active_key = (33333, "44444", "ディス速報")
        _bump_notification_cooldown_cache[active_key] = time.monotonic()

        # 最終クリーンアップ時刻を 0 にしてクリーンアップを強制
        monkeypatch.setattr(bump_module, "_bump_last_cleanup_time", 0)

        _cleanup_bump_notification_cooldown_cache()

        # 期限切れエントリは削除される
        assert expired_key not in _bump_notification_cooldown_cache
        # アクティブなエントリは残る
        assert active_key in _bump_notification_cooldown_cache

    def test_cleanup_guard_allows_zero_last_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_bump_last_cleanup_time=0 でもクリーンアップが実行される.

        time.monotonic() が小さい環境 (CI等) でも
        0 は「未実行」として扱われクリーンアップがスキップされないことを検証。
        """
        import time

        import src.cogs.bump as bump_module

        key = (99999, "guard_test", "DISBOARD")
        _bump_notification_cooldown_cache[key] = time.monotonic() - 400

        monkeypatch.setattr(bump_module, "_bump_last_cleanup_time", 0)
        _cleanup_bump_notification_cooldown_cache()

        # クリーンアップが実行されたことを検証
        assert key not in _bump_notification_cooldown_cache
        # _bump_last_cleanup_time が更新されている (0 より大きい)
        assert bump_module._bump_last_cleanup_time > 0


# ---------------------------------------------------------------------------
# Bump 検知エッジケーステスト
# ---------------------------------------------------------------------------


class TestBumpDetectionEdgeCases:
    """Bump 検知のエッジケーステスト."""

    def test_keyword_in_title_not_description_ignored(self) -> None:
        """DISBOARD: title にキーワードがあっても description になければ検知しない."""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            embed_title=f"サーバーの{DISBOARD_SUCCESS_KEYWORD}しました！",
            embed_description="",
        )

        result = cog._detect_bump_success(message)
        assert result is None

    def test_empty_embed_returns_none(self) -> None:
        """DISBOARD: description も title も空の embed は検知しない."""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            embed_title="",
            embed_description="",
        )

        result = cog._detect_bump_success(message)
        assert result is None


# ---------------------------------------------------------------------------
# _send_reminder エッジケーステスト
# ---------------------------------------------------------------------------


class TestSendReminderEdgeCases:
    """_send_reminder のエッジケーステスト."""

    async def test_no_role_falls_back_to_here(self) -> None:
        """ロールが見つからない場合は @here にフォールバック."""
        cog = _make_cog()

        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = MagicMock()
        # カスタムロールなし、デフォルトロールもなし
        channel.guild.get_role = MagicMock(return_value=None)
        channel.guild.roles = []  # discord.utils.get は空リストから None を返す
        channel.send = AsyncMock()

        cog.bot.get_channel = MagicMock(return_value=channel)

        # role_id=None でリマインダーを作成
        reminder = _make_reminder(role_id=None)

        await cog._send_reminder(reminder)

        # send が呼ばれたことを確認
        channel.send.assert_called_once()
        call_kwargs = channel.send.call_args[1]
        assert call_kwargs["content"] == "@here"

    async def test_custom_role_mentioned(self) -> None:
        """カスタムロールが設定されている場合はそのロールをメンション."""
        cog = _make_cog()

        # カスタムロールを作成
        custom_role = MagicMock(spec=discord.Role)
        custom_role.mention = "<@&999>"

        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = MagicMock()
        channel.guild.get_role = MagicMock(return_value=custom_role)
        channel.send = AsyncMock()

        cog.bot.get_channel = MagicMock(return_value=channel)

        # role_id を設定
        reminder = _make_reminder(role_id="999")

        await cog._send_reminder(reminder)

        # get_role がカスタムロール ID で呼ばれた
        channel.guild.get_role.assert_called_once_with(999)
        # send が呼ばれ、カスタムロールの mention が content に含まれる
        channel.send.assert_called_once()
        call_kwargs = channel.send.call_args[1]
        assert call_kwargs["content"] == "<@&999>"

    async def test_non_text_channel_skipped(self) -> None:
        """TextChannel 以外のチャンネルの場合は送信しない."""
        cog = _make_cog()

        # VoiceChannel を返す
        voice_channel = MagicMock(spec=discord.VoiceChannel)
        voice_channel.send = AsyncMock()

        cog.bot.get_channel = MagicMock(return_value=voice_channel)

        reminder = _make_reminder()

        await cog._send_reminder(reminder)

        # send は呼ばれない
        voice_channel.send.assert_not_called()


# ---------------------------------------------------------------------------
# Additional Edge Case Tests
# ---------------------------------------------------------------------------


class TestBumpCooldownEdgeCases:
    """Bump通知クールダウンの追加エッジケーステスト。"""

    def test_first_call_returns_false(self) -> None:
        """最初の呼び出しはクールダウン中ではない。"""
        result = is_bump_notification_on_cooldown(1, "guild1", "DISBOARD")
        assert result is False

    def test_immediate_second_call_returns_true(self) -> None:
        """連続呼び出しはクールダウン中。"""
        is_bump_notification_on_cooldown(1, "guild1", "DISBOARD")
        result = is_bump_notification_on_cooldown(1, "guild1", "DISBOARD")
        assert result is True

    def test_different_user_not_on_cooldown(self) -> None:
        """別ユーザーはクールダウンに影響されない。"""
        is_bump_notification_on_cooldown(1, "guild1", "DISBOARD")
        result = is_bump_notification_on_cooldown(2, "guild1", "DISBOARD")
        assert result is False

    def test_different_guild_not_on_cooldown(self) -> None:
        """別ギルドはクールダウンに影響されない。"""
        is_bump_notification_on_cooldown(1, "guild1", "DISBOARD")
        result = is_bump_notification_on_cooldown(1, "guild2", "DISBOARD")
        assert result is False

    def test_different_service_not_on_cooldown(self) -> None:
        """別サービスはクールダウンに影響されない。"""
        is_bump_notification_on_cooldown(1, "guild1", "DISBOARD")
        result = is_bump_notification_on_cooldown(1, "guild1", "ディス速報")
        assert result is False

    def test_cache_cleared_resets_cooldown(self) -> None:
        """キャッシュクリア後はクールダウンリセット。"""
        is_bump_notification_on_cooldown(1, "guild1", "DISBOARD")
        clear_bump_notification_cooldown_cache()
        result = is_bump_notification_on_cooldown(1, "guild1", "DISBOARD")
        assert result is False

    def test_cleanup_removes_old_entries(self) -> None:
        """クリーンアップが古いエントリを削除する。"""
        import src.cogs.bump as bump_module

        # エントリを作成
        is_bump_notification_on_cooldown(1, "guild1", "DISBOARD")

        # タイムスタンプを古くする
        key = (1, "guild1", "DISBOARD")
        _bump_notification_cooldown_cache[key] = time.monotonic() - 400

        # クリーンアップを強制実行
        bump_module._bump_last_cleanup_time = 0.0
        _cleanup_bump_notification_cooldown_cache()

        assert key not in _bump_notification_cooldown_cache


class TestDetectBumpSuccessEdgeCases:
    """_detect_bump_success の追加エッジケーステスト。"""

    def test_empty_embeds_no_detection(self) -> None:
        """embed がない場合は検知しない。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
        )
        message.embeds = []
        message.content = None
        result = cog._detect_bump_success(message)
        assert result is None

    def test_disboard_without_success_keyword(self) -> None:
        """DISBOARD のメッセージだが成功キーワードなしは検知しない。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            embed_description="別のメッセージです。",
        )
        result = cog._detect_bump_success(message)
        assert result is None

    def test_non_bot_message_not_detected(self) -> None:
        """DISBOARD/ディス速報以外の Bot のメッセージは検知しない。"""
        cog = _make_cog()
        message = _make_message(
            author_id=99999,  # 別の Bot
            channel_id=456,
            embed_description=f"サーバーの{DISBOARD_SUCCESS_KEYWORD}しました！",
        )
        result = cog._detect_bump_success(message)
        assert result is None

    def test_dissoku_none_description_no_crash(self) -> None:
        """ディス速報の embed.description が None でもクラッシュしない。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
        )
        embed = MagicMock(spec=discord.Embed)
        embed.description = None
        embed.title = None
        embed.fields = []
        message.embeds = [embed]
        message.content = None
        result = cog._detect_bump_success(message)
        assert result is None

    def test_dissoku_empty_fields_no_crash(self) -> None:
        """ディス速報の embed.fields が空リストでもクラッシュしない。"""
        cog = _make_cog()
        message = _make_message(
            author_id=DISSOKU_BOT_ID,
            channel_id=456,
            embed_description="Some text without keyword",
        )
        message.embeds[0].title = None
        message.embeds[0].fields = []
        message.content = None
        result = cog._detect_bump_success(message)
        assert result is None


class TestBumpNotificationViewEdgeCases:
    """BumpNotificationView の追加エッジケーステスト。"""

    async def test_view_timeout_is_none(self) -> None:
        """BumpNotificationView の timeout は None (永続 View)。"""
        view = BumpNotificationView("guild1", "DISBOARD", is_enabled=True)
        assert view.timeout is None


class TestBumpCleanupEmptyCache:
    """空キャッシュに対するクリーンアップが安全に動作することを検証。"""

    def test_cleanup_on_empty_cache_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """キャッシュが空でもクリーンアップがクラッシュしない."""
        import src.cogs.bump as bump_module

        assert len(_bump_notification_cooldown_cache) == 0
        monkeypatch.setattr(bump_module, "_bump_last_cleanup_time", 0)
        _cleanup_bump_notification_cooldown_cache()
        assert len(_bump_notification_cooldown_cache) == 0
        assert bump_module._bump_last_cleanup_time > 0

    def test_is_cooldown_on_empty_cache_returns_false(self) -> None:
        """空キャッシュで is_bump_notification_on_cooldown が False を返す."""
        assert len(_bump_notification_cooldown_cache) == 0
        result = is_bump_notification_on_cooldown(99999, "99999", "DISBOARD")
        assert result is False


class TestBumpCleanupAllExpired:
    """全エントリが期限切れの場合にキャッシュが空になることを検証。"""

    def test_all_expired_entries_removed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """全エントリが期限切れなら全て削除されキャッシュが空になる."""
        import src.cogs.bump as bump_module

        now = time.monotonic()
        _bump_notification_cooldown_cache[(1, "1", "DISBOARD")] = now - 400
        _bump_notification_cooldown_cache[(2, "2", "ディス速報")] = now - 500
        _bump_notification_cooldown_cache[(3, "3", "DISBOARD")] = now - 600

        monkeypatch.setattr(bump_module, "_bump_last_cleanup_time", 0)
        _cleanup_bump_notification_cooldown_cache()

        assert len(_bump_notification_cooldown_cache) == 0


class TestBumpCleanupTriggerViaPublicAPI:
    """公開 API 関数がクリーンアップを内部的にトリガーすることを検証。"""

    def test_is_cooldown_triggers_cleanup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """is_bump_notification_on_cooldown がクリーンアップをトリガーする."""
        import src.cogs.bump as bump_module

        old_key = (11111, "22222", "DISBOARD")
        _bump_notification_cooldown_cache[old_key] = time.monotonic() - 400

        monkeypatch.setattr(bump_module, "_bump_last_cleanup_time", 0)
        is_bump_notification_on_cooldown(99999, "99999", "DISBOARD")

        assert old_key not in _bump_notification_cooldown_cache

    def test_cleanup_updates_last_cleanup_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """クリーンアップ実行後に _bump_last_cleanup_time が更新される."""
        import src.cogs.bump as bump_module

        monkeypatch.setattr(bump_module, "_bump_last_cleanup_time", 0)
        is_bump_notification_on_cooldown(99999, "99999", "DISBOARD")

        assert bump_module._bump_last_cleanup_time > 0


class TestBumpCogSetupCacheVerification:
    """setup() がキャッシュを正しく構築することを検証。"""

    async def test_setup_builds_guild_cache(self) -> None:
        """setup が _bump_guild_ids キャッシュを構築する."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.cogs.bump import setup

        mock_bot = MagicMock(spec=commands.Bot)
        mock_bot.add_view = MagicMock()
        mock_bot.add_cog = AsyncMock()

        mock_config1 = MagicMock()
        mock_config1.guild_id = "guild1"
        mock_config2 = MagicMock()
        mock_config2.guild_id = "guild2"

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.services.db_service.get_all_bump_configs",
                new_callable=AsyncMock,
                return_value=[mock_config1, mock_config2],
            ),
        ):
            await setup(mock_bot)

        cog = mock_bot.add_cog.call_args[0][0]
        assert hasattr(cog, "_bump_guild_ids")
        assert cog._bump_guild_ids == {"guild1", "guild2"}


# ---------------------------------------------------------------------------
# ロックによる同時実行制御テスト
# ---------------------------------------------------------------------------


class TestBumpSetupConcurrency:
    """Bump setup のロックによる同時実行制御テスト。"""

    async def test_concurrent_setup_serialized(self) -> None:
        """同ギルドで同時に /bump setup を実行してもシリアライズされる。"""
        cog = _make_cog()
        cog._bump_guild_ids = set()

        execution_order: list[str] = []

        async def tracking_upsert(*_args: object, **_kwargs: object) -> None:
            execution_order.append("upsert_start")
            await asyncio.sleep(0.01)
            execution_order.append("upsert_end")

        def make_setup_interaction(guild_id: int = 12345) -> MagicMock:
            interaction = MagicMock(spec=discord.Interaction)
            interaction.guild = MagicMock()
            interaction.guild.id = guild_id
            interaction.channel_id = 456
            interaction.channel = MagicMock(spec=discord.TextChannel)
            interaction.response = MagicMock()
            interaction.response.defer = AsyncMock()
            interaction.followup = MagicMock()
            interaction.followup.send = AsyncMock()
            return interaction

        interaction1 = make_setup_interaction()
        interaction2 = make_setup_interaction()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.upsert_bump_config",
                side_effect=tracking_upsert,
            ),
            patch.object(cog, "_find_recent_bump", return_value=None),
        ):
            await asyncio.gather(
                cog.bump_setup.callback(cog, interaction1),
                cog.bump_setup.callback(cog, interaction2),
            )

        # シリアライズされている: upsert_start → upsert_end が連続
        assert execution_order == [
            "upsert_start",
            "upsert_end",
            "upsert_start",
            "upsert_end",
        ]


class TestBumpDeferFailure:
    """defer() 失敗時（別インスタンスが先に応答）のテスト。"""

    async def test_setup_defer_failure_aborts(self) -> None:
        """bump_setup で defer 失敗時、DB 書き込みせず終了する。"""
        cog = _make_cog()

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock()
        interaction.guild.id = 12345
        interaction.channel_id = 456
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=400), "already acknowledged"
            )
        )
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        with patch(
            "src.cogs.bump.upsert_bump_config",
            new_callable=AsyncMock,
        ) as mock_upsert:
            await cog.bump_setup.callback(cog, interaction)
            mock_upsert.assert_not_awaited()
            interaction.followup.send.assert_not_awaited()

    async def test_toggle_defer_failure_aborts(self) -> None:
        """toggle_button で defer 失敗時、DB 変更せず終了する。"""
        view = BumpNotificationView("12345", "DISBOARD", True)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock(
            side_effect=discord.HTTPException(
                MagicMock(status=400), "already acknowledged"
            )
        )
        interaction.message = MagicMock()
        interaction.message.edit = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        with patch(
            "src.cogs.bump.toggle_bump_reminder",
            new_callable=AsyncMock,
        ) as mock_toggle:
            await view.toggle_button.callback(interaction)
            mock_toggle.assert_not_awaited()
            interaction.message.edit.assert_not_awaited()
            interaction.followup.send.assert_not_awaited()


class TestBumpDetectionDuplicateGuard:
    """別インスタンスが同じ bump を既に処理済みの場合のテスト。"""

    async def test_skips_when_claim_returns_none(self) -> None:
        """claim が None (別インスタンスが先に処理) ならスキップ。"""
        cog = _make_cog()
        member = _make_member(has_target_role=True)
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            guild_id=12345,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )
        message.channel.send = AsyncMock()

        mock_config = _make_bump_config(guild_id="12345", channel_id="456")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.claim_bump_detection",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.on_message(message)

        # claim 失敗 → メッセージ送信されない
        message.channel.send.assert_not_awaited()

    async def test_processes_when_claim_succeeds(self) -> None:
        """claim_bump_detection がリマインダーを返す場合は処理する。"""
        cog = _make_cog()
        member = _make_member(has_target_role=True)
        message = _make_message(
            author_id=DISBOARD_BOT_ID,
            channel_id=456,
            guild_id=12345,
            embed_description=DISBOARD_SUCCESS_KEYWORD,
            interaction_user=member,
        )
        message.channel.send = AsyncMock()

        mock_config = _make_bump_config(guild_id="12345", channel_id="456")
        mock_reminder = _make_reminder(is_enabled=True)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.cogs.bump.async_session", return_value=mock_session),
            patch(
                "src.cogs.bump.get_bump_config",
                new_callable=AsyncMock,
                return_value=mock_config,
            ),
            patch(
                "src.cogs.bump.claim_bump_detection",
                new_callable=AsyncMock,
                return_value=mock_reminder,
            ) as mock_claim,
        ):
            await cog.on_message(message)

        # claim 成功 → メッセージ送信される
        mock_claim.assert_awaited_once()
        message.channel.send.assert_awaited_once()


# ---------------------------------------------------------------------------
# キャッシュ連携テスト
# ---------------------------------------------------------------------------


class TestBumpCacheIntegration:
    """_bump_guild_ids キャッシュの連携テスト。"""

    @patch("src.cogs.bump.async_session")
    @patch("src.cogs.bump.get_bump_config")
    @patch("src.cogs.bump.delete_bump_config")
    @patch("src.cogs.bump.delete_bump_reminders_by_guild")
    async def test_channel_delete_discards_from_cache(
        self,
        mock_delete_reminders: AsyncMock,
        mock_delete_config: AsyncMock,
        mock_get_config: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """チャンネル削除時にキャッシュからも削除される。"""
        cog = _make_cog()
        cog._bump_guild_ids = {"789", "999"}

        mock_config = MagicMock()
        mock_config.channel_id = "456"
        mock_get_config.return_value = mock_config
        mock_delete_reminders.return_value = 0

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 456
        channel.guild = MagicMock()
        channel.guild.id = 789

        await cog.on_guild_channel_delete(channel)

        assert "789" not in cog._bump_guild_ids
        assert "999" in cog._bump_guild_ids

    @patch("src.cogs.bump.async_session")
    @patch("src.cogs.bump.delete_bump_config")
    @patch("src.cogs.bump.delete_bump_reminders_by_guild")
    async def test_guild_remove_discards_from_cache(
        self,
        mock_delete_reminders: AsyncMock,
        mock_delete_config: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """ギルド削除時にキャッシュからも削除される。"""
        cog = _make_cog()
        cog._bump_guild_ids = {"789"}

        mock_delete_reminders.return_value = 0

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        guild = MagicMock(spec=discord.Guild)
        guild.id = 789

        await cog.on_guild_remove(guild)

        assert "789" not in cog._bump_guild_ids

    async def test_on_message_skips_not_configured_guild(self) -> None:
        """キャッシュに含まれないギルドのメッセージはスキップ。"""
        cog = _make_cog()
        cog._bump_guild_ids = {"999"}  # 789 は含まない

        message = MagicMock(spec=discord.Message)
        message.guild = MagicMock()
        message.guild.id = 789
        message.author = MagicMock()
        message.author.id = 302050872383242240  # DISBOARD

        await cog.on_message(message)
        # DB にアクセスしないことを暗黙的に検証 (例外が出ない)

    @patch("src.cogs.bump.async_session")
    @patch("src.cogs.bump.delete_bump_config")
    async def test_disable_discards_from_cache(
        self,
        mock_delete: AsyncMock,
        mock_session: MagicMock,
    ) -> None:
        """bump disable でキャッシュからも削除される。"""
        cog = _make_cog()
        cog._bump_guild_ids = {"789"}

        mock_delete.return_value = True

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_ctx

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock()
        interaction.guild.id = 789
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await cog.bump_disable.callback(cog, interaction)

        assert "789" not in cog._bump_guild_ids
