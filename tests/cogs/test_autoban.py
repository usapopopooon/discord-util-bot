"""Tests for AutoBanCog (autoban feature)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from src.cogs.autoban import AutoBanCog

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog() -> AutoBanCog:
    """Create an AutoBanCog with a mock bot."""
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock()
    bot.user.id = 99999
    return AutoBanCog(bot)


def _make_member(
    *,
    name: str = "testuser",
    user_id: int = 12345,
    guild_id: int = 789,
    avatar: object | None = MagicMock(),
    created_at: datetime | None = None,
    joined_at: datetime | None = None,
    is_bot: bool = False,
) -> MagicMock:
    """Create a mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.name = name
    member.id = user_id
    member.bot = is_bot
    member.avatar = avatar
    member.created_at = created_at or datetime.now(UTC) - timedelta(days=30)
    member.joined_at = joined_at
    member.display_name = name
    member.display_avatar = MagicMock()
    member.display_avatar.url = "https://cdn.example.com/avatar.png"
    member.guild = MagicMock()
    member.guild.id = guild_id
    member.guild.name = "Test Server"
    member.guild.ban = AsyncMock()
    member.guild.kick = AsyncMock()
    return member


def _make_rule(
    *,
    rule_id: int = 1,
    guild_id: str = "789",
    rule_type: str = "username_match",
    is_enabled: bool = True,
    action: str = "ban",
    pattern: str | None = "spammer",
    use_wildcard: bool = False,
    threshold_hours: int | None = None,
    threshold_seconds: int | None = None,
) -> MagicMock:
    """Create a mock AutoBanRule."""
    rule = MagicMock()
    rule.id = rule_id
    rule.guild_id = guild_id
    rule.rule_type = rule_type
    rule.is_enabled = is_enabled
    rule.action = action
    rule.pattern = pattern
    rule.use_wildcard = use_wildcard
    rule.threshold_hours = threshold_hours
    rule.threshold_seconds = threshold_seconds
    return rule


def _make_interaction(*, guild_id: int = 789) -> MagicMock:
    """Create a mock Discord interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock()
    interaction.guild.id = guild_id
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    return interaction


# ---------------------------------------------------------------------------
# TestCheckRule: ルールチェックの単体テスト
# ---------------------------------------------------------------------------


class TestCheckUsernameMatch:
    """_check_username_match のテスト。"""

    def test_exact_match(self) -> None:
        cog = _make_cog()
        rule = _make_rule(pattern="spammer")
        member = _make_member(name="spammer")
        matched, reason = cog._check_username_match(rule, member)
        assert matched
        assert "exact match" in reason

    def test_exact_match_case_insensitive(self) -> None:
        cog = _make_cog()
        rule = _make_rule(pattern="SPAMMER")
        member = _make_member(name="spammer")
        matched, reason = cog._check_username_match(rule, member)
        assert matched

    def test_exact_no_match(self) -> None:
        cog = _make_cog()
        rule = _make_rule(pattern="spammer")
        member = _make_member(name="gooduser")
        matched, _ = cog._check_username_match(rule, member)
        assert not matched

    def test_exact_no_partial_match(self) -> None:
        """Without wildcard, partial matches should NOT match."""
        cog = _make_cog()
        rule = _make_rule(pattern="spam")
        member = _make_member(name="spammer123")
        matched, _ = cog._check_username_match(rule, member)
        assert not matched

    def test_wildcard_match(self) -> None:
        cog = _make_cog()
        rule = _make_rule(pattern="spam", use_wildcard=True)
        member = _make_member(name="totalspammer")
        matched, reason = cog._check_username_match(rule, member)
        assert matched
        assert "wildcard match" in reason

    def test_wildcard_case_insensitive(self) -> None:
        cog = _make_cog()
        rule = _make_rule(pattern="SPAM", use_wildcard=True)
        member = _make_member(name="totalspammer")
        matched, _ = cog._check_username_match(rule, member)
        assert matched

    def test_wildcard_no_match(self) -> None:
        cog = _make_cog()
        rule = _make_rule(pattern="badword", use_wildcard=True)
        member = _make_member(name="gooduser")
        matched, _ = cog._check_username_match(rule, member)
        assert not matched

    def test_no_pattern_returns_false(self) -> None:
        cog = _make_cog()
        rule = _make_rule(pattern=None)
        member = _make_member(name="testuser")
        matched, _ = cog._check_username_match(rule, member)
        assert not matched


class TestCheckAccountAge:
    """_check_account_age のテスト。"""

    def test_new_account_matches(self) -> None:
        cog = _make_cog()
        rule = _make_rule(
            rule_type="account_age",
            threshold_hours=24,
            pattern=None,
        )
        member = _make_member(created_at=datetime.now(UTC) - timedelta(hours=1))
        matched, reason = cog._check_account_age(rule, member)
        assert matched
        assert "less than threshold" in reason

    def test_old_account_no_match(self) -> None:
        cog = _make_cog()
        rule = _make_rule(
            rule_type="account_age",
            threshold_hours=24,
            pattern=None,
        )
        member = _make_member(created_at=datetime.now(UTC) - timedelta(days=30))
        matched, _ = cog._check_account_age(rule, member)
        assert not matched

    def test_no_threshold_returns_false(self) -> None:
        cog = _make_cog()
        rule = _make_rule(
            rule_type="account_age",
            threshold_hours=None,
            pattern=None,
        )
        member = _make_member()
        matched, _ = cog._check_account_age(rule, member)
        assert not matched


class TestCheckNoAvatar:
    """_check_no_avatar のテスト。"""

    def test_no_avatar_matches(self) -> None:
        cog = _make_cog()
        member = _make_member(avatar=None)
        matched, reason = cog._check_no_avatar(member)
        assert matched
        assert "No avatar" in reason

    def test_has_avatar_no_match(self) -> None:
        cog = _make_cog()
        member = _make_member(avatar=MagicMock())
        matched, _ = cog._check_no_avatar(member)
        assert not matched


class TestCheckRule:
    """_check_rule のテスト。"""

    def test_dispatches_username_match(self) -> None:
        cog = _make_cog()
        rule = _make_rule(rule_type="username_match", pattern="baduser")
        member = _make_member(name="baduser")
        matched, _ = cog._check_rule(rule, member)
        assert matched

    def test_dispatches_account_age(self) -> None:
        cog = _make_cog()
        rule = _make_rule(
            rule_type="account_age",
            threshold_hours=24,
            pattern=None,
        )
        member = _make_member(created_at=datetime.now(UTC) - timedelta(hours=1))
        matched, _ = cog._check_rule(rule, member)
        assert matched

    def test_dispatches_no_avatar(self) -> None:
        cog = _make_cog()
        rule = _make_rule(rule_type="no_avatar", pattern=None)
        member = _make_member(avatar=None)
        matched, _ = cog._check_rule(rule, member)
        assert matched

    def test_unknown_type_returns_false(self) -> None:
        cog = _make_cog()
        rule = _make_rule(rule_type="unknown_type", pattern=None)
        member = _make_member()
        matched, _ = cog._check_rule(rule, member)
        assert not matched


# ---------------------------------------------------------------------------
# TestOnMemberJoin: on_member_join の統合テスト
# ---------------------------------------------------------------------------


class TestOnMemberJoin:
    """on_member_join イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        cog = _make_cog()
        member = _make_member(is_bot=True)
        with patch("src.cogs.autoban.get_enabled_autoban_rules_by_guild") as mock_get:
            await cog.on_member_join(member)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_rules_no_action(self) -> None:
        cog = _make_cog()
        member = _make_member()
        with patch(
            "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
            return_value=[],
        ):
            await cog.on_member_join(member)
            member.guild.ban.assert_not_called()
            member.guild.kick.assert_not_called()

    @pytest.mark.asyncio
    async def test_matching_rule_bans(self) -> None:
        cog = _make_cog()
        member = _make_member(name="spammer")
        rule = _make_rule(action="ban", pattern="spammer")
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                return_value=[rule],
            ),
            patch("src.cogs.autoban.create_autoban_log", new_callable=AsyncMock),
            patch(
                "src.cogs.autoban.get_autoban_config",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.on_member_join(member)
            member.guild.ban.assert_called_once()

    @pytest.mark.asyncio
    async def test_matching_rule_kicks(self) -> None:
        cog = _make_cog()
        member = _make_member(name="spammer")
        rule = _make_rule(action="kick", pattern="spammer")
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                return_value=[rule],
            ),
            patch("src.cogs.autoban.create_autoban_log", new_callable=AsyncMock),
            patch(
                "src.cogs.autoban.get_autoban_config",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.on_member_join(member)
            member.guild.kick.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_match_no_action(self) -> None:
        cog = _make_cog()
        member = _make_member(name="gooduser")
        rule = _make_rule(pattern="baduser")
        with patch(
            "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
            return_value=[rule],
        ):
            await cog.on_member_join(member)
            member.guild.ban.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_matching_rule_wins(self) -> None:
        cog = _make_cog()
        member = _make_member(name="spammer", avatar=None)
        rule1 = _make_rule(rule_id=1, action="kick", pattern="spammer")
        rule2 = _make_rule(rule_id=2, rule_type="no_avatar", pattern=None, action="ban")
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                return_value=[rule1, rule2],
            ),
            patch("src.cogs.autoban.create_autoban_log", new_callable=AsyncMock),
            patch(
                "src.cogs.autoban.get_autoban_config",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.on_member_join(member)
            member.guild.kick.assert_called_once()
            member.guild.ban.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_log_on_action(self) -> None:
        cog = _make_cog()
        member = _make_member(name="spammer")
        rule = _make_rule(action="ban", pattern="spammer")
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                return_value=[rule],
            ),
            patch(
                "src.cogs.autoban.create_autoban_log",
                new_callable=AsyncMock,
            ) as mock_log,
            patch(
                "src.cogs.autoban.get_autoban_config",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.on_member_join(member)
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_forbidden_error_handled(self) -> None:
        cog = _make_cog()
        member = _make_member(name="spammer")
        member.guild.ban = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "forbidden")
        )
        rule = _make_rule(action="ban", pattern="spammer")
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                return_value=[rule],
            ),
            patch(
                "src.cogs.autoban.create_autoban_log",
                new_callable=AsyncMock,
            ) as mock_log,
        ):
            await cog.on_member_join(member)
            mock_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_http_exception_handled(self) -> None:
        cog = _make_cog()
        member = _make_member(name="spammer")
        member.guild.ban = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "error")
        )
        rule = _make_rule(action="ban", pattern="spammer")
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                return_value=[rule],
            ),
            patch(
                "src.cogs.autoban.create_autoban_log",
                new_callable=AsyncMock,
            ) as mock_log,
        ):
            await cog.on_member_join(member)
            mock_log.assert_not_called()


# ---------------------------------------------------------------------------
# TestSlashCommands: スラッシュコマンドのテスト
# ---------------------------------------------------------------------------


class TestAutobanAdd:
    """autoban_add コマンドのテスト。"""

    @pytest.mark.asyncio
    async def test_no_guild_returns_error(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        interaction.guild = None
        await cog.autoban_add.callback(cog, interaction, rule_type="username_match")
        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert "サーバー内" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_username_match_without_pattern(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        await cog.autoban_add.callback(
            cog, interaction, rule_type="username_match", pattern=None
        )
        call_args = interaction.response.send_message.call_args
        assert "pattern" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_account_age_without_threshold(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        await cog.autoban_add.callback(
            cog, interaction, rule_type="account_age", threshold_hours=None
        )
        call_args = interaction.response.send_message.call_args
        assert "threshold_hours" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_account_age_exceeds_max(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        await cog.autoban_add.callback(
            cog, interaction, rule_type="account_age", threshold_hours=500
        )
        call_args = interaction.response.send_message.call_args
        assert "336" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_successful_add(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        mock_rule = _make_rule(rule_id=42)
        with patch(
            "src.cogs.autoban.create_autoban_rule",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            await cog.autoban_add.callback(
                cog,
                interaction,
                rule_type="username_match",
                pattern="baduser",
            )
            call_args = interaction.response.send_message.call_args
            assert "#42" in call_args.args[0]


class TestAutobanRemove:
    """autoban_remove コマンドのテスト。"""

    @pytest.mark.asyncio
    async def test_no_guild_returns_error(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        interaction.guild = None
        await cog.autoban_remove.callback(cog, interaction, rule_id=1)
        call_args = interaction.response.send_message.call_args
        assert "サーバー内" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_successful_delete(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        with patch(
            "src.cogs.autoban.delete_autoban_rule",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await cog.autoban_remove.callback(cog, interaction, rule_id=1)
            call_args = interaction.response.send_message.call_args
            assert "deleted" in call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        with patch(
            "src.cogs.autoban.delete_autoban_rule",
            new_callable=AsyncMock,
            return_value=False,
        ):
            await cog.autoban_remove.callback(cog, interaction, rule_id=999)
            call_args = interaction.response.send_message.call_args
            assert "not found" in call_args.args[0].lower()


class TestAutobanList:
    """autoban_list コマンドのテスト。"""

    @pytest.mark.asyncio
    async def test_no_guild_returns_error(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        interaction.guild = None
        await cog.autoban_list.callback(cog, interaction)
        call_args = interaction.response.send_message.call_args
        assert "サーバー内" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        with patch(
            "src.cogs.autoban.get_autoban_rules_by_guild",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await cog.autoban_list.callback(cog, interaction)
            call_args = interaction.response.send_message.call_args
            assert "no autoban rules" in call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_shows_rules(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        rules = [
            _make_rule(rule_id=1, rule_type="username_match", pattern="bad"),
            _make_rule(
                rule_id=2,
                rule_type="account_age",
                threshold_hours=24,
                pattern=None,
            ),
        ]
        with patch(
            "src.cogs.autoban.get_autoban_rules_by_guild",
            new_callable=AsyncMock,
            return_value=rules,
        ):
            await cog.autoban_list.callback(cog, interaction)
            call_kwargs = interaction.response.send_message.call_args.kwargs
            assert "embed" in call_kwargs


class TestAutobanLogs:
    """autoban_logs コマンドのテスト。"""

    @pytest.mark.asyncio
    async def test_no_guild_returns_error(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        interaction.guild = None
        await cog.autoban_logs.callback(cog, interaction)
        call_args = interaction.response.send_message.call_args
        assert "サーバー内" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_empty_logs(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        with patch(
            "src.cogs.autoban.get_autoban_logs_by_guild",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await cog.autoban_logs.callback(cog, interaction)
            call_args = interaction.response.send_message.call_args
            assert "no autoban logs" in call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_shows_logs(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        log_entry = MagicMock()
        log_entry.username = "baduser"
        log_entry.user_id = "123"
        log_entry.action_taken = "banned"
        log_entry.reason = "Username match"
        log_entry.rule_id = 1
        log_entry.created_at = datetime.now(UTC)
        with patch(
            "src.cogs.autoban.get_autoban_logs_by_guild",
            new_callable=AsyncMock,
            return_value=[log_entry],
        ):
            await cog.autoban_logs.callback(cog, interaction)
            call_kwargs = interaction.response.send_message.call_args.kwargs
            assert "embed" in call_kwargs


# ---------------------------------------------------------------------------
# TestSetup: setup 関数のテスト
# ---------------------------------------------------------------------------


class TestSetup:
    """setup 関数のテスト。"""

    @pytest.mark.asyncio
    async def test_setup_adds_cog(self) -> None:
        from src.cogs.autoban import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()
        await setup(bot)
        bot.add_cog.assert_called_once()


# ---------------------------------------------------------------------------
# Edge Case Tests: Account Age Boundary
# ---------------------------------------------------------------------------


class TestAccountAgeBoundary:
    """Account age boundary condition tests (strict < comparison)."""

    def test_account_exactly_at_threshold_no_match(self) -> None:
        """Account age == threshold should NOT match (strict <)."""
        cog = _make_cog()
        rule = _make_rule(
            rule_type="account_age",
            threshold_hours=24,
            pattern=None,
        )
        member = _make_member(created_at=datetime.now(UTC) - timedelta(hours=24))
        matched, reason = cog._check_account_age(rule, member)
        assert matched is False
        assert reason == ""

    def test_account_one_second_under_threshold_matches(self) -> None:
        """Account age just under threshold should match."""
        cog = _make_cog()
        rule = _make_rule(
            rule_type="account_age",
            threshold_hours=24,
            pattern=None,
        )
        member = _make_member(
            created_at=datetime.now(UTC) - timedelta(hours=24) + timedelta(seconds=1)
        )
        matched, reason = cog._check_account_age(rule, member)
        assert matched is True
        assert "less than threshold" in reason


# ---------------------------------------------------------------------------
# Edge Case Tests: Username Match with Special Characters
# ---------------------------------------------------------------------------


class TestUsernameMatchSpecialChars:
    """Username matching treats patterns as literal strings, not regex."""

    def test_pattern_with_regex_special_chars_literal(self) -> None:
        """Regex special chars like [ ] are treated as literal substring."""
        cog = _make_cog()
        rule = _make_rule(pattern="user[bot]", use_wildcard=True)
        member = _make_member(name="user[bot]test")
        matched, reason = cog._check_username_match(rule, member)
        assert matched is True
        assert "wildcard match" in reason

    def test_pattern_with_dots_literal(self) -> None:
        """Dot is NOT treated as regex wildcard; it must match literally."""
        cog = _make_cog()
        rule = _make_rule(pattern="spam.bot", use_wildcard=True)
        member = _make_member(name="spamXbot")
        matched, reason = cog._check_username_match(rule, member)
        assert matched is False
        assert reason == ""


# ---------------------------------------------------------------------------
# Edge Case Tests: First Match Wins (break behavior)
# ---------------------------------------------------------------------------


class TestFirstMatchWins:
    """Verify the loop breaks on first match and disabled rules are filtered."""

    @pytest.mark.asyncio
    async def test_disabled_rule_not_returned_by_db(self) -> None:
        """DB function returns only enabled rules; disabled rules never reach cog."""
        cog = _make_cog()
        member = _make_member(name="spammer")
        enabled_rule = _make_rule(
            rule_id=1, action="ban", pattern="spammer", is_enabled=True
        )
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                return_value=[enabled_rule],
            ),
            patch("src.cogs.autoban.create_autoban_log", new_callable=AsyncMock),
            patch(
                "src.cogs.autoban.get_autoban_config",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.on_member_join(member)
            member.guild.ban.assert_called_once()

    @pytest.mark.asyncio
    async def test_first_match_breaks_no_second_action(self) -> None:
        """When member matches two rules, only the first rule's action runs."""
        cog = _make_cog()
        member = _make_member(name="spammer", avatar=None)
        rule1 = _make_rule(
            rule_id=1,
            rule_type="username_match",
            action="kick",
            pattern="spammer",
        )
        rule2 = _make_rule(
            rule_id=2,
            rule_type="no_avatar",
            action="ban",
            pattern=None,
        )
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                return_value=[rule1, rule2],
            ),
            patch("src.cogs.autoban.create_autoban_log", new_callable=AsyncMock),
            patch(
                "src.cogs.autoban.get_autoban_config",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.on_member_join(member)
            member.guild.kick.assert_called_once()
            member.guild.ban.assert_not_called()


# ---------------------------------------------------------------------------
# Additional Edge Case Tests
# ---------------------------------------------------------------------------


class TestUsernameMatchEdgeCases:
    """ユーザー名マッチングの追加エッジケーステスト。"""

    def test_empty_pattern_no_match(self) -> None:
        """空文字パターンはマッチしない。"""
        cog = _make_cog()
        rule = _make_rule(pattern="")
        member = _make_member(name="testuser")
        matched, _ = cog._check_username_match(rule, member)
        assert not matched

    def test_unicode_pattern_exact_match(self) -> None:
        """日本語パターンの完全一致。"""
        cog = _make_cog()
        rule = _make_rule(pattern="スパマー")
        member = _make_member(name="スパマー")
        matched, reason = cog._check_username_match(rule, member)
        assert matched is True
        assert "exact match" in reason

    def test_unicode_pattern_wildcard_match(self) -> None:
        """日本語パターンのワイルドカード一致。"""
        cog = _make_cog()
        rule = _make_rule(pattern="スパム", use_wildcard=True)
        member = _make_member(name="テストスパム送信者123")
        matched, reason = cog._check_username_match(rule, member)
        assert matched is True
        assert "wildcard match" in reason

    def test_unicode_pattern_no_match(self) -> None:
        """日本語パターンが一致しない場合。"""
        cog = _make_cog()
        rule = _make_rule(pattern="スパム", use_wildcard=True)
        member = _make_member(name="正常ユーザー")
        matched, _ = cog._check_username_match(rule, member)
        assert matched is False

    def test_whitespace_pattern_no_match_without_wildcard(self) -> None:
        """スペースパターンは完全一致でのみマッチ。"""
        cog = _make_cog()
        rule = _make_rule(pattern="  ", use_wildcard=False)
        member = _make_member(name="user  name")
        matched, _ = cog._check_username_match(rule, member)
        assert matched is False

    def test_identical_name_case_variants(self) -> None:
        """大文字小文字の異なる複数のバリエーション。"""
        cog = _make_cog()
        rule = _make_rule(pattern="SpAmMeR")
        for name in ["spammer", "SPAMMER", "Spammer", "sPaMMeR"]:
            member = _make_member(name=name)
            matched, _ = cog._check_username_match(rule, member)
            assert matched is True


class TestAccountAgeEdgeCases:
    """アカウント年齢チェックの追加エッジケーステスト。"""

    def test_account_created_just_now(self) -> None:
        """作成されたばかりのアカウント (0秒) は閾値があればマッチ。"""
        cog = _make_cog()
        rule = _make_rule(
            rule_type="account_age",
            threshold_hours=1,
            pattern=None,
        )
        member = _make_member(created_at=datetime.now(UTC))
        matched, reason = cog._check_account_age(rule, member)
        assert matched is True
        assert "less than threshold" in reason

    def test_threshold_hours_zero_returns_false(self) -> None:
        """threshold_hours = 0 は falsy なのでマッチしない。"""
        cog = _make_cog()
        rule = _make_rule(
            rule_type="account_age",
            threshold_hours=0,
            pattern=None,
        )
        member = _make_member(created_at=datetime.now(UTC))
        matched, _ = cog._check_account_age(rule, member)
        assert matched is False

    def test_max_threshold_hours(self) -> None:
        """最大閾値 (336時間 = 14日) で新しいアカウントにマッチ。"""
        cog = _make_cog()
        rule = _make_rule(
            rule_type="account_age",
            threshold_hours=336,
            pattern=None,
        )
        member = _make_member(created_at=datetime.now(UTC) - timedelta(days=13))
        matched, _ = cog._check_account_age(rule, member)
        assert matched is True


class TestOnMemberJoinEdgeCases:
    """on_member_join の追加エッジケーステスト。"""

    @pytest.mark.asyncio
    async def test_multiple_non_matching_rules(self) -> None:
        """複数のルール全てマッチしない場合はアクションなし。"""
        cog = _make_cog()
        member = _make_member(
            name="gooduser",
            created_at=datetime.now(UTC) - timedelta(days=365),
        )
        rule1 = _make_rule(rule_id=1, pattern="baduser")
        rule2 = _make_rule(
            rule_id=2, rule_type="account_age", threshold_hours=24, pattern=None
        )
        rule3 = _make_rule(rule_id=3, rule_type="no_avatar", pattern=None)
        with patch(
            "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
            return_value=[rule1, rule2, rule3],
        ):
            await cog.on_member_join(member)
            member.guild.ban.assert_not_called()
            member.guild.kick.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_creation_failure_propagates_after_ban(self) -> None:
        """ログ作成失敗時、BAN は実行されるがエラーが伝播する。"""
        cog = _make_cog()
        member = _make_member(name="spammer")
        rule = _make_rule(action="ban", pattern="spammer")
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                return_value=[rule],
            ),
            patch(
                "src.cogs.autoban.create_autoban_log",
                new_callable=AsyncMock,
                side_effect=Exception("DB error"),
            ),
        ):
            with pytest.raises(Exception, match="DB error"):
                await cog.on_member_join(member)
            # BAN は実行されている
            member.guild.ban.assert_called_once()


# ---------------------------------------------------------------------------
# TestSendLogEmbed: _send_log_embed のテスト
# ---------------------------------------------------------------------------


class TestSendLogEmbed:
    """_send_log_embed メソッドのテスト。"""

    @staticmethod
    def _make_guild(*, channel_return: object | None = None) -> MagicMock:
        guild = MagicMock(spec=discord.Guild)
        guild.id = 789
        guild.name = "Test Server"
        guild.get_channel.return_value = channel_return
        return guild

    @staticmethod
    def _make_text_channel(*, side_effect: Exception | None = None) -> MagicMock:
        ch = MagicMock(spec=discord.TextChannel)
        ch.send = AsyncMock(side_effect=side_effect)
        return ch

    @staticmethod
    async def _call(
        cog: AutoBanCog,
        guild: MagicMock,
        *,
        channel_id: str = "100",
        action_taken: str = "banned",
        rule: MagicMock | None = None,
        reason: str = "test",
        member_name: str = "user",
        member_id: int = 1,
        member_display_name: str = "user",
        member_avatar_url: str | None = None,
        member_created_at: datetime | None = None,
        member_joined_at: datetime | None = None,
    ) -> None:
        now = datetime.now(UTC)
        await cog._send_log_embed(
            guild=guild,
            channel_id=channel_id,
            action_taken=action_taken,
            rule=rule or _make_rule(),
            reason=reason,
            member_name=member_name,
            member_id=member_id,
            member_display_name=member_display_name,
            member_avatar_url=member_avatar_url,
            member_created_at=member_created_at or now,
            member_joined_at=member_joined_at,
        )

    @pytest.mark.asyncio
    async def test_sends_embed_to_channel(self) -> None:
        """有効なチャンネルに Embed が送信される。"""
        cog = _make_cog()
        ch = self._make_text_channel()
        guild = self._make_guild(channel_return=ch)
        now = datetime.now(UTC)

        await self._call(
            cog,
            guild,
            action_taken="banned",
            rule=_make_rule(rule_type="no_avatar"),
            reason="No avatar set",
            member_name="baduser",
            member_id=12345,
            member_display_name="Bad User",
            member_avatar_url="https://cdn.example.com/avatar.png",
            member_created_at=now - timedelta(days=30),
            member_joined_at=now - timedelta(seconds=5),
        )

        guild.get_channel.assert_called_once_with(100)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "User Banned"
        assert embed.color.value == 0xFF0000

    @pytest.mark.asyncio
    async def test_kick_embed_color(self) -> None:
        """KICK の場合はオレンジ色の Embed が送信される。"""
        cog = _make_cog()
        ch = self._make_text_channel()
        guild = self._make_guild(channel_return=ch)

        await self._call(
            cog,
            guild,
            action_taken="kicked",
            rule=_make_rule(rule_type="no_avatar", action="kick"),
        )

        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "User Kicked"
        assert embed.color.value == 0xFFA500

    @pytest.mark.asyncio
    async def test_channel_not_found(self) -> None:
        """チャンネルが見つからない場合は何も送信しない。"""
        cog = _make_cog()
        guild = self._make_guild(channel_return=None)
        # 例外は発生しない
        await self._call(cog, guild, channel_id="999")

    @pytest.mark.asyncio
    async def test_channel_not_text_channel(self) -> None:
        """TextChannel でないチャンネルの場合は何も送信しない。"""
        cog = _make_cog()
        guild = self._make_guild(channel_return=MagicMock(spec=discord.VoiceChannel))
        await self._call(cog, guild)

    @pytest.mark.asyncio
    async def test_forbidden_error_handled(self) -> None:
        """権限不足の場合は例外が伝播しない。"""
        cog = _make_cog()
        ch = self._make_text_channel(
            side_effect=discord.Forbidden(MagicMock(), "forbidden")
        )
        guild = self._make_guild(channel_return=ch)
        # 例外は発生しない
        await self._call(cog, guild)

    @pytest.mark.asyncio
    async def test_http_exception_handled(self) -> None:
        """HTTPException の場合は例外が伝播しない。"""
        cog = _make_cog()
        ch = self._make_text_channel(
            side_effect=discord.HTTPException(MagicMock(), "error")
        )
        guild = self._make_guild(channel_return=ch)
        # 例外は発生しない
        await self._call(cog, guild)

    @pytest.mark.asyncio
    async def test_embed_fields(self) -> None:
        """Embed に正しいフィールドが含まれる。"""
        cog = _make_cog()
        ch = self._make_text_channel()
        guild = self._make_guild(channel_return=ch)
        now = datetime.now(UTC)

        await self._call(
            cog,
            guild,
            rule=_make_rule(rule_id=42, rule_type="username_match"),
            reason="Username match",
            member_name="baduser",
            member_id=12345,
            member_display_name="Bad User",
            member_avatar_url="https://cdn.example.com/av.png",
            member_created_at=now - timedelta(days=30),
            member_joined_at=now - timedelta(seconds=5),
        )

        embed = ch.send.call_args.kwargs["embed"]
        field_names = [f.name for f in embed.fields]
        assert "User" in field_names
        assert "User ID" in field_names
        assert "Action" in field_names
        assert "Rule" in field_names
        assert "Reason" in field_names
        assert "Account Created" in field_names
        assert "Joined Server" in field_names

        # User ID フィールドの値
        uid_field = next(f for f in embed.fields if f.name == "User ID")
        assert uid_field.value == "12345"

        # Rule フィールドの値
        rule_field = next(f for f in embed.fields if f.name == "Rule")
        assert "#42" in rule_field.value
        assert "username_match" in rule_field.value

    @pytest.mark.asyncio
    async def test_embed_no_joined_at(self) -> None:
        """joined_at が None の場合は Joined Server フィールドがない。"""
        cog = _make_cog()
        ch = self._make_text_channel()
        guild = self._make_guild(channel_return=ch)

        await self._call(cog, guild, member_joined_at=None)

        embed = ch.send.call_args.kwargs["embed"]
        field_names = [f.name for f in embed.fields]
        assert "Joined Server" not in field_names


# ---------------------------------------------------------------------------
# TestExecuteActionWithLogChannel: ログチャンネル連携のテスト
# ---------------------------------------------------------------------------


class TestExecuteActionWithLogChannel:
    """_execute_action でログチャンネルに通知されるテスト。"""

    @staticmethod
    def _patches(
        config_return: MagicMock | None,
    ) -> tuple[patch, patch]:  # type: ignore[type-arg]
        """共通 patch オブジェクトを返す。"""
        return (
            patch(
                "src.cogs.autoban.create_autoban_log",
                new_callable=AsyncMock,
            ),
            patch(
                "src.cogs.autoban.get_autoban_config",
                new_callable=AsyncMock,
                return_value=config_return,
            ),
        )

    @pytest.mark.asyncio
    async def test_sends_log_when_config_exists(self) -> None:
        """ログチャンネル設定がある場合は _send_log_embed が呼ばれる。"""
        cog = _make_cog()
        mock_config = MagicMock()
        mock_config.log_channel_id = "100"
        p_log, p_cfg = self._patches(mock_config)

        with (
            p_log,
            p_cfg,
            patch.object(cog, "_send_log_embed", new_callable=AsyncMock) as mock_send,
        ):
            await cog._execute_action(
                _make_member(name="spammer"),
                _make_rule(action="ban", pattern="spammer"),
                "test reason",
            )
            mock_send.assert_called_once()
            assert mock_send.call_args.kwargs["channel_id"] == "100"
            assert mock_send.call_args.kwargs["action_taken"] == "banned"

    @pytest.mark.asyncio
    async def test_no_log_when_config_none(self) -> None:
        """ログチャンネル設定がない場合は _send_log_embed が呼ばれない。"""
        cog = _make_cog()
        p_log, p_cfg = self._patches(None)

        with (
            p_log,
            p_cfg,
            patch.object(cog, "_send_log_embed", new_callable=AsyncMock) as mock_send,
        ):
            await cog._execute_action(
                _make_member(name="spammer"),
                _make_rule(action="ban", pattern="spammer"),
                "test reason",
            )
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_log_when_channel_id_none(self) -> None:
        """log_channel_id が None の場合は _send_log_embed が呼ばれない。"""
        cog = _make_cog()
        mock_config = MagicMock()
        mock_config.log_channel_id = None
        p_log, p_cfg = self._patches(mock_config)

        with (
            p_log,
            p_cfg,
            patch.object(cog, "_send_log_embed", new_callable=AsyncMock) as mock_send,
        ):
            await cog._execute_action(
                _make_member(name="spammer"),
                _make_rule(action="ban", pattern="spammer"),
                "test reason",
            )
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_kick_action_with_log(self) -> None:
        """KICK アクションでもログが送信される。"""
        cog = _make_cog()
        mock_config = MagicMock()
        mock_config.log_channel_id = "200"
        p_log, p_cfg = self._patches(mock_config)

        with (
            p_log,
            p_cfg,
            patch.object(cog, "_send_log_embed", new_callable=AsyncMock) as mock_send,
        ):
            await cog._execute_action(
                _make_member(name="spammer"),
                _make_rule(action="kick", pattern="spammer"),
                "test reason",
            )
            mock_send.assert_called_once()
            assert mock_send.call_args.kwargs["action_taken"] == "kicked"
