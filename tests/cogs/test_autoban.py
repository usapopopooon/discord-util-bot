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
    required_channel_id: str | None = None,
    created_at: datetime | None = None,
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
    rule.required_channel_id = required_channel_id
    rule.created_at = created_at or datetime.now(UTC) - timedelta(days=1)
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

    def test_skips_role_acquired(self) -> None:
        """role_acquired は on_member_update でチェック。_check_rule では対象外。"""
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC) - timedelta(seconds=5))
        rule = _make_rule(
            rule_type="role_acquired",
            pattern=None,
            threshold_seconds=10,
        )
        matched, _ = cog._check_rule(rule, member)
        assert not matched

    def test_skips_vc_join(self) -> None:
        """vc_join は on_voice_state_update でチェック。_check_rule では対象外。"""
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC) - timedelta(seconds=3))
        rule = _make_rule(rule_type="vc_join", pattern=None, threshold_seconds=60)
        matched, _ = cog._check_rule(rule, member)
        assert not matched

    def test_skips_message_post(self) -> None:
        """message_post は on_message でチェック。_check_rule では対象外。"""
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC) - timedelta(seconds=1))
        rule = _make_rule(rule_type="message_post", pattern=None, threshold_seconds=30)
        matched, _ = cog._check_rule(rule, member)
        assert not matched


class TestCheckJoinTiming:
    """_check_join_timing のテスト。"""

    def test_within_threshold_matches(self) -> None:
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC) - timedelta(seconds=5))
        rule = _make_rule(rule_type="role_acquired", pattern=None, threshold_seconds=60)
        matched, reason = cog._check_join_timing(rule, member)
        assert matched
        assert "threshold" in reason.lower()

    def test_outside_threshold_no_match(self) -> None:
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC) - timedelta(hours=1))
        rule = _make_rule(rule_type="vc_join", pattern=None, threshold_seconds=60)
        matched, _ = cog._check_join_timing(rule, member)
        assert not matched

    def test_no_threshold_returns_false(self) -> None:
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC))
        rule = _make_rule(rule_type="vc_join", pattern=None, threshold_seconds=None)
        matched, _ = cog._check_join_timing(rule, member)
        assert not matched

    def test_no_joined_at_returns_false(self) -> None:
        cog = _make_cog()
        member = _make_member(joined_at=None)
        rule = _make_rule(rule_type="vc_join", pattern=None, threshold_seconds=60)
        matched, _ = cog._check_join_timing(rule, member)
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
            patch("src.cogs.autoban.claim_autoban_log", new_callable=AsyncMock),
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
            patch("src.cogs.autoban.claim_autoban_log", new_callable=AsyncMock),
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
            patch("src.cogs.autoban.claim_autoban_log", new_callable=AsyncMock),
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
    async def test_timing_rules_ignored_on_join(self) -> None:
        """タイミング系ルールは on_member_join では無視。"""
        cog = _make_cog()
        member = _make_member(
            name="gooduser",
            joined_at=datetime.now(UTC),  # 今参加した
        )
        rules = [
            _make_rule(
                rule_id=1,
                rule_type="role_acquired",
                pattern=None,
                threshold_seconds=60,
            ),
            _make_rule(
                rule_id=2,
                rule_type="vc_join",
                pattern=None,
                threshold_seconds=90,
            ),
            _make_rule(
                rule_id=3,
                rule_type="message_post",
                pattern=None,
                threshold_seconds=30,
            ),
        ]
        with patch(
            "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
            return_value=rules,
        ):
            await cog.on_member_join(member)
            member.guild.ban.assert_not_called()
            member.guild.kick.assert_not_called()

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
                "src.cogs.autoban.claim_autoban_log",
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
        """BAN が Forbidden でも claim 済み — エラーログのみ出力。"""
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
                "src.cogs.autoban.claim_autoban_log",
                new_callable=AsyncMock,
            ) as mock_log,
            patch(
                "src.cogs.autoban.get_autoban_config",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.on_member_join(member)
            # claim は ban の前に呼ばれる
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_exception_handled(self) -> None:
        """BAN が HTTPException でも claim 済み — エラーログのみ出力。"""
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
                "src.cogs.autoban.claim_autoban_log",
                new_callable=AsyncMock,
            ) as mock_log,
            patch(
                "src.cogs.autoban.get_autoban_config",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await cog.on_member_join(member)
            # claim は ban の前に呼ばれる
            mock_log.assert_called_once()


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
            patch("src.cogs.autoban.claim_autoban_log", new_callable=AsyncMock),
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
            patch("src.cogs.autoban.claim_autoban_log", new_callable=AsyncMock),
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
    async def test_log_creation_failure_propagates_no_ban(self) -> None:
        """claim 失敗時は BAN も実行されずエラーが伝播する。"""
        cog = _make_cog()
        member = _make_member(name="spammer")
        rule = _make_rule(action="ban", pattern="spammer")
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                return_value=[rule],
            ),
            patch(
                "src.cogs.autoban.claim_autoban_log",
                new_callable=AsyncMock,
                side_effect=Exception("DB error"),
            ),
        ):
            with pytest.raises(Exception, match="DB error"):
                await cog.on_member_join(member)
            # claim が先なので BAN は実行されない
            member.guild.ban.assert_not_called()


# ---------------------------------------------------------------------------
# TestDuplicateGuard: 重複インスタンス防止のテスト
# ---------------------------------------------------------------------------


class TestDuplicateGuard:
    """claim が None (別インスタンスが先に処理) ならスキップ。"""

    @pytest.mark.asyncio
    async def test_execute_action_skips_all_on_duplicate(self) -> None:
        """claim_autoban_log が None → ban/kick も embed も実行しない。"""
        cog = _make_cog()
        member = _make_member(name="spammer")
        rule = _make_rule(action="ban", pattern="spammer")

        with (
            patch(
                "src.cogs.autoban.claim_autoban_log",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.cogs.autoban.get_autoban_config",
                new_callable=AsyncMock,
            ) as mock_cfg,
            patch.object(cog, "_send_log_embed", new_callable=AsyncMock) as mock_send,
        ):
            await cog._execute_action(member, rule, "test reason")
            member.guild.ban.assert_not_called()
            mock_cfg.assert_not_called()
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_member_ban_skips_on_duplicate(self) -> None:
        """claim_ban_log が None → 重複ログを作成しない。"""
        cog = _make_cog()
        guild, user = _make_guild_and_user()
        ban_entry = MagicMock()
        ban_entry.reason = "Spam"
        guild.fetch_ban.return_value = ban_entry
        mock_session = _make_mock_session()

        with (
            patch(
                "src.cogs.autoban.async_session",
                return_value=mock_session,
            ),
            patch(
                "src.cogs.autoban.claim_ban_log",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_claim,
        ):
            await cog.on_member_ban(guild, user)
            mock_claim.assert_called_once()


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
    @pytest.mark.parametrize(
        ("action", "expected_title", "expected_color"),
        [
            ("banned", "[AutoBan] User Banned", 0xFF0000),
            ("kicked", "[AutoBan] User Kicked", 0xFFA500),
        ],
    )
    async def test_embed_title_and_color(
        self,
        action: str,
        expected_title: str,
        expected_color: int,
    ) -> None:
        """アクションに応じた Embed タイトルと色が設定される。"""
        cog = _make_cog()
        ch = self._make_text_channel()
        guild = self._make_guild(channel_return=ch)
        now = datetime.now(UTC)

        await self._call(
            cog,
            guild,
            action_taken=action,
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
        assert embed.title == expected_title
        assert embed.color.value == expected_color

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
    @pytest.mark.parametrize(
        "exc",
        [
            discord.Forbidden(MagicMock(), "forbidden"),
            discord.HTTPException(MagicMock(), "error"),
        ],
        ids=["forbidden", "http_exception"],
    )
    async def test_send_exception_handled(self, exc: Exception) -> None:
        """送信時の例外が伝播しない。"""
        cog = _make_cog()
        ch = self._make_text_channel(side_effect=exc)
        guild = self._make_guild(channel_return=ch)
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
                "src.cogs.autoban.claim_autoban_log",
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


# ---------------------------------------------------------------------------
# TestOnMemberBan: on_member_ban イベントのテスト
# ---------------------------------------------------------------------------


def _make_mock_session() -> MagicMock:
    """Create a mock async session context manager."""
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    return mock_session


def _make_guild_and_user(
    *,
    guild_id: int = 789,
    user_id: int = 12345,
    user_name: str = "testuser",
) -> tuple[MagicMock, MagicMock]:
    """Create mock guild and user for on_member_ban tests."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    guild.name = "Test Server"
    guild.fetch_ban = AsyncMock()
    user = MagicMock(spec=discord.User)
    user.id = user_id
    user.name = user_name
    return guild, user


class TestOnMemberBan:
    """on_member_ban イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_creates_log(self) -> None:
        """BAN イベントで BanLog が作成される。"""
        cog = _make_cog()
        guild, user = _make_guild_and_user()
        ban_entry = MagicMock()
        ban_entry.reason = "Spam behavior"
        guild.fetch_ban.return_value = ban_entry
        mock_session = _make_mock_session()

        with (
            patch(
                "src.cogs.autoban.async_session",
                return_value=mock_session,
            ),
            patch(
                "src.cogs.autoban.claim_ban_log",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await cog.on_member_ban(guild, user)
            mock_create.assert_called_once_with(
                mock_session,
                guild_id="789",
                user_id="12345",
                username="testuser",
                reason="Spam behavior",
                is_autoban=False,
            )

    @pytest.mark.asyncio
    async def test_autoban_detected(self) -> None:
        """理由が [Autoban] で始まる場合 is_autoban=True。"""
        cog = _make_cog()
        guild, user = _make_guild_and_user()
        ban_entry = MagicMock()
        ban_entry.reason = "[Autoban] Username match"
        guild.fetch_ban.return_value = ban_entry
        mock_session = _make_mock_session()

        with (
            patch(
                "src.cogs.autoban.async_session",
                return_value=mock_session,
            ),
            patch(
                "src.cogs.autoban.claim_ban_log",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await cog.on_member_ban(guild, user)
            mock_create.assert_called_once_with(
                mock_session,
                guild_id="789",
                user_id="12345",
                username="testuser",
                reason="[Autoban] Username match",
                is_autoban=True,
            )

    @pytest.mark.asyncio
    async def test_manual_ban(self) -> None:
        """通常の理由では is_autoban=False。"""
        cog = _make_cog()
        guild, user = _make_guild_and_user()
        ban_entry = MagicMock()
        ban_entry.reason = "Manual ban by admin"
        guild.fetch_ban.return_value = ban_entry
        mock_session = _make_mock_session()

        with (
            patch(
                "src.cogs.autoban.async_session",
                return_value=mock_session,
            ),
            patch(
                "src.cogs.autoban.claim_ban_log",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await cog.on_member_ban(guild, user)
            call_kwargs = mock_create.call_args
            assert call_kwargs.kwargs["is_autoban"] is False
            assert call_kwargs.kwargs["reason"] == "Manual ban by admin"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exc",
        [
            discord.HTTPException(MagicMock(), "error"),
            discord.NotFound(MagicMock(), "not found"),
        ],
        ids=["http_exception", "not_found"],
    )
    async def test_fetch_ban_exception(self, exc: Exception) -> None:
        """fetch_ban が例外を返してもログは作成される。"""
        cog = _make_cog()
        guild, user = _make_guild_and_user()
        guild.fetch_ban = AsyncMock(side_effect=exc)
        mock_session = _make_mock_session()

        with (
            patch(
                "src.cogs.autoban.async_session",
                return_value=mock_session,
            ),
            patch(
                "src.cogs.autoban.claim_ban_log",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await cog.on_member_ban(guild, user)
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args
            assert call_kwargs.kwargs["reason"] is None
            assert call_kwargs.kwargs["is_autoban"] is False

    @pytest.mark.asyncio
    async def test_claim_ban_log_exception_handled(self) -> None:
        """claim_ban_log が例外を出しても伝播しない。"""
        cog = _make_cog()
        guild, user = _make_guild_and_user()
        ban_entry = MagicMock()
        ban_entry.reason = "Spam"
        guild.fetch_ban.return_value = ban_entry
        mock_session = _make_mock_session()

        with (
            patch(
                "src.cogs.autoban.async_session",
                return_value=mock_session,
            ),
            patch(
                "src.cogs.autoban.claim_ban_log",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB error"),
            ),
        ):
            # 例外は伝播しない
            await cog.on_member_ban(guild, user)

    @pytest.mark.asyncio
    async def test_reason_none_from_ban_entry(self) -> None:
        """ban_entry.reason が None の場合も正しく処理される。"""
        cog = _make_cog()
        guild, user = _make_guild_and_user()
        ban_entry = MagicMock()
        ban_entry.reason = None
        guild.fetch_ban.return_value = ban_entry
        mock_session = _make_mock_session()

        with (
            patch(
                "src.cogs.autoban.async_session",
                return_value=mock_session,
            ),
            patch(
                "src.cogs.autoban.claim_ban_log",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await cog.on_member_ban(guild, user)
            call_kwargs = mock_create.call_args
            assert call_kwargs.kwargs["reason"] is None
            assert call_kwargs.kwargs["is_autoban"] is False


# ---------------------------------------------------------------------------
# TestOnMemberUpdate: on_member_update (role_acquired) のテスト
# ---------------------------------------------------------------------------


class TestOnMemberUpdate:
    """on_member_update イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        cog = _make_cog()
        before = _make_member(is_bot=True)
        after = _make_member(is_bot=True)
        with patch("src.cogs.autoban.get_enabled_autoban_rules_by_guild") as mock_get:
            await cog.on_member_update(before, after)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_role_change_skips(self) -> None:
        cog = _make_cog()
        role = MagicMock(spec=discord.Role)
        before = _make_member()
        before.roles = [role]
        after = _make_member()
        after.roles = [role]
        with patch("src.cogs.autoban.get_enabled_autoban_rules_by_guild") as mock_get:
            await cog.on_member_update(before, after)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_role_removed_skips(self) -> None:
        """ロール削除は検知しない (追加のみ)。"""
        cog = _make_cog()
        role = MagicMock(spec=discord.Role)
        before = _make_member()
        before.roles = [role]
        after = _make_member()
        after.roles = []
        with patch("src.cogs.autoban.get_enabled_autoban_rules_by_guild") as mock_get:
            await cog.on_member_update(before, after)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_rules_no_action(self) -> None:
        cog = _make_cog()
        role = MagicMock(spec=discord.Role)
        before = _make_member()
        before.roles = []
        after = _make_member()
        after.roles = [role]
        with patch(
            "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await cog.on_member_update(before, after)
            after.guild.ban.assert_not_called()

    @pytest.mark.asyncio
    async def test_matching_role_acquired_bans(self) -> None:
        cog = _make_cog()
        role = MagicMock(spec=discord.Role)
        before = _make_member()
        before.roles = []
        after = _make_member(joined_at=datetime.now(UTC) - timedelta(seconds=5))
        after.roles = [role]
        rule = _make_rule(
            rule_type="role_acquired",
            pattern=None,
            threshold_seconds=60,
        )
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                new_callable=AsyncMock,
                return_value=[rule],
            ),
            patch.object(cog, "_execute_action", new_callable=AsyncMock) as mock,
        ):
            await cog.on_member_update(before, after)
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_role_acquired_rule_skipped(self) -> None:
        """role_acquired 以外のルールはスキップ。"""
        cog = _make_cog()
        role = MagicMock(spec=discord.Role)
        before = _make_member()
        before.roles = []
        after = _make_member(joined_at=datetime.now(UTC) - timedelta(seconds=5))
        after.roles = [role]
        rule = _make_rule(rule_type="username_match", pattern="test")
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                new_callable=AsyncMock,
                return_value=[rule],
            ),
            patch.object(cog, "_execute_action", new_callable=AsyncMock) as mock,
        ):
            await cog.on_member_update(before, after)
            mock.assert_not_called()


# ---------------------------------------------------------------------------
# TestOnVoiceStateUpdate: on_voice_state_update (vc_join) のテスト
# ---------------------------------------------------------------------------


class TestOnVoiceStateUpdate:
    """on_voice_state_update イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        cog = _make_cog()
        member = _make_member(is_bot=True)
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock()
        with patch("src.cogs.autoban.get_enabled_autoban_rules_by_guild") as mock_get:
            await cog.on_voice_state_update(member, before, after)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_channel_move_skips(self) -> None:
        """チャンネル移動は無視 (新規参加のみ)。"""
        cog = _make_cog()
        member = _make_member()
        before = MagicMock(spec=discord.VoiceState)
        before.channel = MagicMock()
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock()
        with patch("src.cogs.autoban.get_enabled_autoban_rules_by_guild") as mock_get:
            await cog.on_voice_state_update(member, before, after)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_vc_leave_skips(self) -> None:
        """VC退出は無視。"""
        cog = _make_cog()
        member = _make_member()
        before = MagicMock(spec=discord.VoiceState)
        before.channel = MagicMock()
        after = MagicMock(spec=discord.VoiceState)
        after.channel = None
        with patch("src.cogs.autoban.get_enabled_autoban_rules_by_guild") as mock_get:
            await cog.on_voice_state_update(member, before, after)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_rules_no_action(self) -> None:
        cog = _make_cog()
        member = _make_member()
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock()
        with patch(
            "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await cog.on_voice_state_update(member, before, after)
            member.guild.ban.assert_not_called()

    @pytest.mark.asyncio
    async def test_matching_vc_join_bans(self) -> None:
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC) - timedelta(seconds=3))
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock()
        rule = _make_rule(rule_type="vc_join", pattern=None, threshold_seconds=60)
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                new_callable=AsyncMock,
                return_value=[rule],
            ),
            patch.object(cog, "_execute_action", new_callable=AsyncMock) as mock,
        ):
            await cog.on_voice_state_update(member, before, after)
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_vc_join_rule_skipped(self) -> None:
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC) - timedelta(seconds=3))
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock()
        rule = _make_rule(rule_type="no_avatar", pattern=None)
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                new_callable=AsyncMock,
                return_value=[rule],
            ),
            patch.object(cog, "_execute_action", new_callable=AsyncMock) as mock,
        ):
            await cog.on_voice_state_update(member, before, after)
            mock.assert_not_called()


# ---------------------------------------------------------------------------
# TestOnMessage: on_message (message_post) のテスト
# ---------------------------------------------------------------------------


class TestOnMessage:
    """on_message イベントのテスト。"""

    def _make_message(
        self,
        *,
        is_bot: bool = False,
        is_member: bool = True,
        has_guild: bool = True,
        joined_at: datetime | None = None,
        message_type: discord.MessageType = discord.MessageType.default,
    ) -> MagicMock:
        msg = MagicMock(spec=discord.Message)
        msg.type = message_type
        if has_guild:
            msg.guild = MagicMock()
            msg.guild.id = 789
        else:
            msg.guild = None

        if is_member:
            member = _make_member(is_bot=is_bot, joined_at=joined_at)
            msg.author = member
            msg.author.__class__ = discord.Member
            # isinstance check needs special handling
        else:
            msg.author = MagicMock(spec=discord.User)
            msg.author.bot = is_bot
        return msg

    @pytest.mark.asyncio
    async def test_no_guild_skips(self) -> None:
        cog = _make_cog()
        msg = self._make_message(has_guild=False)
        with patch("src.cogs.autoban.get_enabled_autoban_rules_by_guild") as mock_get:
            await cog.on_message(msg)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_bot_message_skips(self) -> None:
        cog = _make_cog()
        msg = self._make_message(is_bot=True)
        with patch("src.cogs.autoban.get_enabled_autoban_rules_by_guild") as mock_get:
            await cog.on_message(msg)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_system_message_skips(self) -> None:
        """システムメッセージ (参加通知など) はスキップ。"""
        cog = _make_cog()
        msg = self._make_message(message_type=discord.MessageType.new_member)
        with patch("src.cogs.autoban.get_enabled_autoban_rules_by_guild") as mock_get:
            await cog.on_message(msg)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_member_author_skips(self) -> None:
        """author が Member でない場合はスキップ。"""
        cog = _make_cog()
        msg = MagicMock(spec=discord.Message)
        msg.type = discord.MessageType.default
        msg.guild = MagicMock()
        msg.guild.id = 789
        msg.author = MagicMock(spec=discord.User)  # Not a Member
        msg.author.bot = False
        with patch("src.cogs.autoban.get_enabled_autoban_rules_by_guild") as mock_get:
            await cog.on_message(msg)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_rules_no_action(self) -> None:
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC) - timedelta(seconds=5))
        msg = MagicMock(spec=discord.Message)
        msg.type = discord.MessageType.default
        msg.guild = MagicMock()
        msg.guild.id = 789
        msg.author = member
        with patch(
            "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await cog.on_message(msg)

    @pytest.mark.asyncio
    async def test_matching_message_post_bans(self) -> None:
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC) - timedelta(seconds=2))
        msg = MagicMock(spec=discord.Message)
        msg.type = discord.MessageType.default
        msg.guild = MagicMock()
        msg.guild.id = 789
        msg.author = member
        rule = _make_rule(rule_type="message_post", pattern=None, threshold_seconds=60)
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                new_callable=AsyncMock,
                return_value=[rule],
            ),
            patch.object(cog, "_execute_action", new_callable=AsyncMock) as mock,
        ):
            await cog.on_message(msg)
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_message_post_rule_skipped(self) -> None:
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC) - timedelta(seconds=2))
        msg = MagicMock(spec=discord.Message)
        msg.type = discord.MessageType.default
        msg.guild = MagicMock()
        msg.guild.id = 789
        msg.author = member
        rule = _make_rule(rule_type="account_age", pattern=None, threshold_hours=24)
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                new_callable=AsyncMock,
                return_value=[rule],
            ),
            patch.object(cog, "_execute_action", new_callable=AsyncMock) as mock,
        ):
            await cog.on_message(msg)
            mock.assert_not_called()


# ---------------------------------------------------------------------------
# TestAutobanAddTimingRules: slash command for timing-based rules
# ---------------------------------------------------------------------------


class TestAutobanAddTimingRules:
    """autoban_add タイミングベースルール テスト。"""

    @pytest.mark.asyncio
    async def test_role_acquired_without_threshold(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        await cog.autoban_add.callback(
            cog, interaction, rule_type="role_acquired", threshold_seconds=None
        )
        call_args = interaction.response.send_message.call_args
        assert "threshold_seconds" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_vc_join_threshold_zero(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        await cog.autoban_add.callback(
            cog, interaction, rule_type="vc_join", threshold_seconds=0
        )
        call_args = interaction.response.send_message.call_args
        assert "threshold_seconds" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_message_post_exceeds_max(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        await cog.autoban_add.callback(
            cog, interaction, rule_type="message_post", threshold_seconds=5000
        )
        call_args = interaction.response.send_message.call_args
        assert "3600" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_successful_add_with_threshold_seconds(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        mock_rule = _make_rule(rule_id=10, rule_type="vc_join", threshold_seconds=30)
        with patch(
            "src.cogs.autoban.create_autoban_rule",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            await cog.autoban_add.callback(
                cog,
                interaction,
                rule_type="vc_join",
                threshold_seconds=30,
            )
            call_args = interaction.response.send_message.call_args
            assert "#10" in call_args.args[0]
            assert "30s" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_successful_add_with_wildcard(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        mock_rule = _make_rule(rule_id=11, use_wildcard=True)
        with patch(
            "src.cogs.autoban.create_autoban_rule",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            await cog.autoban_add.callback(
                cog,
                interaction,
                rule_type="username_match",
                pattern="spam",
                use_wildcard=True,
            )
            call_args = interaction.response.send_message.call_args
            assert "Wildcard: Yes" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_successful_add_with_threshold_hours(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        mock_rule = _make_rule(rule_id=12, rule_type="account_age", threshold_hours=48)
        with patch(
            "src.cogs.autoban.create_autoban_rule",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            await cog.autoban_add.callback(
                cog,
                interaction,
                rule_type="account_age",
                threshold_hours=48,
            )
            call_args = interaction.response.send_message.call_args
            assert "48h" in call_args.args[0]


# ---------------------------------------------------------------------------
# TestAutobanListTimingRules: list command for timing-based rules
# ---------------------------------------------------------------------------


class TestAutobanListTimingRules:
    """autoban_list のタイミングベースルール表示テスト。"""

    @pytest.mark.asyncio
    async def test_shows_account_age_threshold(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        rule = _make_rule(rule_type="account_age", threshold_hours=24, pattern=None)
        with patch(
            "src.cogs.autoban.get_autoban_rules_by_guild",
            new_callable=AsyncMock,
            return_value=[rule],
        ):
            await cog.autoban_list.callback(cog, interaction)
            call_kwargs = interaction.response.send_message.call_args
            embed = call_kwargs.kwargs["embed"]
            assert "24h" in embed.fields[0].value

    @pytest.mark.asyncio
    async def test_shows_timing_rule_threshold(self) -> None:
        cog = _make_cog()
        interaction = _make_interaction()
        rule = _make_rule(rule_type="vc_join", threshold_seconds=120, pattern=None)
        with patch(
            "src.cogs.autoban.get_autoban_rules_by_guild",
            new_callable=AsyncMock,
            return_value=[rule],
        ):
            await cog.autoban_list.callback(cog, interaction)
            call_kwargs = interaction.response.send_message.call_args
            embed = call_kwargs.kwargs["embed"]
            assert "120s" in embed.fields[0].value


# ---------------------------------------------------------------------------
# TestCheckIntroMissing: _check_intro_missing のテスト
# ---------------------------------------------------------------------------


class TestCheckIntroMissing:
    """_check_intro_missing のテスト。"""

    @pytest.mark.asyncio
    async def test_no_required_channel_returns_false(self) -> None:
        """required_channel_id が None なら False。"""
        cog = _make_cog()
        rule = _make_rule(
            rule_type="vc_without_intro",
            required_channel_id=None,
            pattern=None,
        )
        member = _make_member(joined_at=datetime.now(UTC))
        matched, _ = await cog._check_intro_missing(rule, member)
        assert matched is False

    @pytest.mark.asyncio
    async def test_no_joined_at_returns_false(self) -> None:
        """joined_at が None なら False。"""
        cog = _make_cog()
        rule = _make_rule(
            rule_type="vc_without_intro",
            required_channel_id="555",
            pattern=None,
        )
        member = _make_member(joined_at=None)
        matched, _ = await cog._check_intro_missing(rule, member)
        assert matched is False

    @pytest.mark.asyncio
    async def test_old_member_skipped(self) -> None:
        """ルール作成前に参加したメンバーは対象外。"""
        cog = _make_cog()
        rule = _make_rule(
            rule_type="vc_without_intro",
            required_channel_id="555",
            created_at=datetime.now(UTC),
            pattern=None,
        )
        member = _make_member(
            joined_at=datetime.now(UTC) - timedelta(days=7),
        )
        matched, _ = await cog._check_intro_missing(rule, member)
        assert matched is False

    @pytest.mark.asyncio
    async def test_not_posted_returns_true(self) -> None:
        """指定チャンネルに未投稿なら True。"""
        cog = _make_cog()
        rule = _make_rule(
            rule_type="vc_without_intro",
            required_channel_id="555",
            created_at=datetime.now(UTC) - timedelta(days=7),
            pattern=None,
        )
        member = _make_member(joined_at=datetime.now(UTC))
        with patch(
            "src.cogs.autoban.has_intro_post",
            new_callable=AsyncMock,
            return_value=False,
        ):
            matched, reason = await cog._check_intro_missing(rule, member)
        assert matched is True
        assert "555" in reason

    @pytest.mark.asyncio
    async def test_posted_returns_false(self) -> None:
        """指定チャンネルに投稿済みなら False。"""
        cog = _make_cog()
        rule = _make_rule(
            rule_type="vc_without_intro",
            required_channel_id="555",
            created_at=datetime.now(UTC) - timedelta(days=7),
            pattern=None,
        )
        member = _make_member(joined_at=datetime.now(UTC))
        with patch(
            "src.cogs.autoban.has_intro_post",
            new_callable=AsyncMock,
            return_value=True,
        ):
            matched, _ = await cog._check_intro_missing(rule, member)
        assert matched is False


# ---------------------------------------------------------------------------
# TestVcWithoutIntro: VC参加時の intro チェック
# ---------------------------------------------------------------------------


class TestVcWithoutIntro:
    """VC参加 + intro未投稿のテスト。"""

    @pytest.mark.asyncio
    async def test_vc_without_intro_bans(self) -> None:
        """指定チャンネル未投稿で VC 参加 → BAN。"""
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC))
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock()
        rule = _make_rule(
            rule_type="vc_without_intro",
            required_channel_id="555",
            pattern=None,
        )
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                new_callable=AsyncMock,
                return_value=[rule],
            ),
            patch.object(
                cog,
                "_check_intro_missing",
                new_callable=AsyncMock,
                return_value=(True, "No post"),
            ),
            patch.object(cog, "_execute_action", new_callable=AsyncMock) as mock_exec,
        ):
            await cog.on_voice_state_update(member, before, after)
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_vc_without_intro_posted(self) -> None:
        """指定チャンネル投稿済みで VC 参加 → 無視。"""
        cog = _make_cog()
        member = _make_member(joined_at=datetime.now(UTC))
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock()
        rule = _make_rule(
            rule_type="vc_without_intro",
            required_channel_id="555",
            pattern=None,
        )
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                new_callable=AsyncMock,
                return_value=[rule],
            ),
            patch.object(
                cog,
                "_check_intro_missing",
                new_callable=AsyncMock,
                return_value=(False, ""),
            ),
            patch.object(cog, "_execute_action", new_callable=AsyncMock) as mock_exec,
        ):
            await cog.on_voice_state_update(member, before, after)
            mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# TestMsgWithoutIntro: テキストチャンネル投稿時の intro チェック
# ---------------------------------------------------------------------------


class TestMsgWithoutIntro:
    """テキストチャンネル投稿 + intro未投稿のテスト。"""

    def _make_message(
        self,
        *,
        joined_at: datetime | None = None,
        channel_id: int = 999,
    ) -> MagicMock:
        msg = MagicMock(spec=discord.Message)
        msg.type = discord.MessageType.default
        msg.guild = MagicMock()
        msg.guild.id = 789
        member = _make_member(joined_at=joined_at)
        msg.author = member
        msg.channel = MagicMock()
        msg.channel.id = channel_id
        return msg

    @pytest.mark.asyncio
    async def test_msg_without_intro_bans(self) -> None:
        """指定チャンネル未投稿で別チャンネルに投稿 → BAN。"""
        cog = _make_cog()
        msg = self._make_message(
            joined_at=datetime.now(UTC),
            channel_id=999,
        )
        rule = _make_rule(
            rule_type="msg_without_intro",
            required_channel_id="555",
            pattern=None,
        )
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                new_callable=AsyncMock,
                return_value=[rule],
            ),
            patch.object(
                cog,
                "_check_intro_missing",
                new_callable=AsyncMock,
                return_value=(True, "No post"),
            ),
            patch.object(cog, "_execute_action", new_callable=AsyncMock) as mock_exec,
        ):
            await cog.on_message(msg)
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_msg_without_intro_posted(self) -> None:
        """指定チャンネル投稿済みで別チャンネルに投稿 → 無視。"""
        cog = _make_cog()
        msg = self._make_message(
            joined_at=datetime.now(UTC),
            channel_id=999,
        )
        rule = _make_rule(
            rule_type="msg_without_intro",
            required_channel_id="555",
            pattern=None,
        )
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                new_callable=AsyncMock,
                return_value=[rule],
            ),
            patch.object(
                cog,
                "_check_intro_missing",
                new_callable=AsyncMock,
                return_value=(False, ""),
            ),
            patch.object(cog, "_execute_action", new_callable=AsyncMock) as mock_exec,
        ):
            await cog.on_message(msg)
            mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_msg_in_required_channel_records(self) -> None:
        """指定チャンネルへの投稿 → DB記録、BAN なし。"""
        cog = _make_cog()
        msg = self._make_message(
            joined_at=datetime.now(UTC),
            channel_id=555,
        )
        rule = _make_rule(
            rule_type="msg_without_intro",
            required_channel_id="555",
            pattern=None,
        )
        with (
            patch(
                "src.cogs.autoban.get_enabled_autoban_rules_by_guild",
                new_callable=AsyncMock,
                return_value=[rule],
            ),
            patch(
                "src.cogs.autoban.record_intro_post",
                new_callable=AsyncMock,
            ) as mock_record,
            patch.object(cog, "_execute_action", new_callable=AsyncMock) as mock_exec,
        ):
            await cog.on_message(msg)
            mock_record.assert_called_once()
            mock_exec.assert_not_called()
