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
    is_bot: bool = False,
) -> MagicMock:
    """Create a mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.name = name
    member.id = user_id
    member.bot = is_bot
    member.avatar = avatar
    member.created_at = created_at or datetime.now(UTC) - timedelta(days=30)
    member.guild = MagicMock()
    member.guild.id = guild_id
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
