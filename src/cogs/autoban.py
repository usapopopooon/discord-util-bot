"""Autoban cog.

新規メンバー参加時にルールに基づき自動 BAN/KICK する。

ルールタイプ:
  - username_match: ユーザー名マッチング (大文字小文字無視、ワイルドカード対応)
  - account_age: アカウント年齢 (作成からの時間が閾値未満なら該当)
  - no_avatar: アバター未設定

仕組み:
  - on_member_join イベントで新規メンバーを検知
  - DB から有効ルールを取得し、順にチェック
  - マッチしたら ban/kick + DB にログ記録
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from src.database.engine import async_session
from src.database.models import AutoBanRule
from src.services.db_service import (
    create_autoban_log,
    create_autoban_rule,
    delete_autoban_rule,
    get_autoban_logs_by_guild,
    get_autoban_rules_by_guild,
    get_enabled_autoban_rules_by_guild,
)

logger = logging.getLogger(__name__)

MAX_THRESHOLD_HOURS = 336


class AutoBanCog(commands.Cog):
    """Autoban 機能を提供する Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ==========================================================================
    # イベントリスナー
    # ==========================================================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """新規メンバー参加時に autoban ルールをチェックする。"""
        if member.bot:
            return

        guild_id = str(member.guild.id)

        async with async_session() as session:
            rules = await get_enabled_autoban_rules_by_guild(session, guild_id)

        if not rules:
            return

        for rule in rules:
            matched, reason = self._check_rule(rule, member)
            if matched:
                await self._execute_action(member, rule, reason)
                break

    def _check_rule(
        self, rule: AutoBanRule, member: discord.Member
    ) -> tuple[bool, str]:
        """ルールに対してメンバーがマッチするかチェックする。"""
        if rule.rule_type == "username_match":
            return self._check_username_match(rule, member)
        if rule.rule_type == "account_age":
            return self._check_account_age(rule, member)
        if rule.rule_type == "no_avatar":
            return self._check_no_avatar(member)
        return False, ""

    def _check_username_match(
        self, rule: AutoBanRule, member: discord.Member
    ) -> tuple[bool, str]:
        """ユーザー名マッチングをチェック。"""
        if not rule.pattern:
            return False, ""

        username_lower = member.name.lower()
        pattern_lower = rule.pattern.lower()

        if rule.use_wildcard:
            if pattern_lower in username_lower:
                return True, f"Username contains '{rule.pattern}' (wildcard match)"
        elif username_lower == pattern_lower:
            return True, f"Username matches '{rule.pattern}' (exact match)"

        return False, ""

    def _check_account_age(
        self, rule: AutoBanRule, member: discord.Member
    ) -> tuple[bool, str]:
        """アカウント年齢をチェック。"""
        if not rule.threshold_hours:
            return False, ""

        now = datetime.now(UTC)
        account_age_hours = (now - member.created_at).total_seconds() / 3600

        if account_age_hours < rule.threshold_hours:
            return True, (
                f"Account age ({account_age_hours:.1f}h) "
                f"is less than threshold ({rule.threshold_hours}h)"
            )
        return False, ""

    def _check_no_avatar(self, member: discord.Member) -> tuple[bool, str]:
        """アバター未設定をチェック。"""
        if member.avatar is None:
            return True, "No avatar set"
        return False, ""

    async def _execute_action(
        self,
        member: discord.Member,
        rule: AutoBanRule,
        reason: str,
    ) -> None:
        """マッチしたルールに基づきアクションを実行する。"""
        guild = member.guild
        action_taken = "banned" if rule.action == "ban" else "kicked"
        full_reason = f"[Autoban] {reason}"

        try:
            if rule.action == "ban":
                await guild.ban(member, reason=full_reason)
            else:
                await guild.kick(member, reason=full_reason)

            logger.info(
                "Autoban %s user %s (%s) in guild %s: %s",
                action_taken,
                member.name,
                member.id,
                guild.id,
                reason,
            )
        except discord.Forbidden:
            logger.warning(
                "Missing permissions to %s user %s (%s) in guild %s",
                rule.action,
                member.name,
                member.id,
                guild.id,
            )
            return
        except discord.HTTPException as e:
            logger.error(
                "Failed to %s user %s (%s) in guild %s: %s",
                rule.action,
                member.name,
                member.id,
                guild.id,
                e,
            )
            return

        async with async_session() as session:
            await create_autoban_log(
                session,
                guild_id=str(guild.id),
                user_id=str(member.id),
                username=member.name,
                rule_id=rule.id,
                action_taken=action_taken,
                reason=reason,
            )

    # ==========================================================================
    # スラッシュコマンド
    # ==========================================================================

    autoban_group = app_commands.Group(
        name="autoban",
        description="Autoban ルールの管理",
        default_permissions=discord.Permissions(administrator=True),
    )

    @autoban_group.command(name="add", description="Autoban ルールを追加")
    @app_commands.describe(
        rule_type="ルールの種類",
        action="アクション (ban または kick)",
        pattern="ユーザー名パターン (username_match のみ)",
        use_wildcard="ワイルドカード: パターンがユーザー名に含まれていればマッチ",
        threshold_hours="アカウント年齢の閾値 (時間、account_age のみ、最大 336)",
    )
    @app_commands.choices(
        rule_type=[
            app_commands.Choice(name="Username Match", value="username_match"),
            app_commands.Choice(name="Account Age", value="account_age"),
            app_commands.Choice(name="No Avatar", value="no_avatar"),
        ],
        action=[
            app_commands.Choice(name="Ban", value="ban"),
            app_commands.Choice(name="Kick", value="kick"),
        ],
    )
    async def autoban_add(
        self,
        interaction: discord.Interaction,
        rule_type: str,
        action: str = "ban",
        pattern: str | None = None,
        use_wildcard: bool = False,
        threshold_hours: int | None = None,
    ) -> None:
        """Autoban ルールを追加する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        if rule_type == "username_match" and not pattern:
            await interaction.response.send_message(
                "username_match ルールには pattern が必要です。", ephemeral=True
            )
            return

        if rule_type == "account_age":
            if not threshold_hours or threshold_hours < 1:
                await interaction.response.send_message(
                    "account_age ルールには 1 以上の threshold_hours が必要です。",
                    ephemeral=True,
                )
                return
            if threshold_hours > MAX_THRESHOLD_HOURS:
                await interaction.response.send_message(
                    f"threshold_hours は最大 {MAX_THRESHOLD_HOURS} (14日) です。",
                    ephemeral=True,
                )
                return

        guild_id = str(interaction.guild.id)

        async with async_session() as session:
            rule = await create_autoban_rule(
                session,
                guild_id=guild_id,
                rule_type=rule_type,
                action=action,
                pattern=pattern,
                use_wildcard=use_wildcard,
                threshold_hours=threshold_hours,
            )

        desc_parts = [f"Type: {rule_type}", f"Action: {action}"]
        if pattern:
            desc_parts.append(f"Pattern: {pattern}")
            if use_wildcard:
                desc_parts.append("Wildcard: Yes")
        if threshold_hours:
            desc_parts.append(f"Threshold: {threshold_hours}h")

        await interaction.response.send_message(
            f"Autoban rule #{rule.id} added.\n" + "\n".join(desc_parts),
            ephemeral=True,
        )

    @autoban_group.command(name="remove", description="Autoban ルールを削除")
    @app_commands.describe(rule_id="削除するルールの ID")
    async def autoban_remove(
        self, interaction: discord.Interaction, rule_id: int
    ) -> None:
        """Autoban ルールを削除する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        async with async_session() as session:
            deleted = await delete_autoban_rule(session, rule_id)

        if deleted:
            await interaction.response.send_message(
                f"Autoban rule #{rule_id} deleted.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Rule #{rule_id} not found.", ephemeral=True
            )

    @autoban_group.command(name="list", description="Autoban ルール一覧")
    async def autoban_list(self, interaction: discord.Interaction) -> None:
        """Autoban ルール一覧を表示する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)
        async with async_session() as session:
            rules = await get_autoban_rules_by_guild(session, guild_id)

        if not rules:
            await interaction.response.send_message(
                "No autoban rules configured.", ephemeral=True
            )
            return

        embed = discord.Embed(title="Autoban Rules", color=0xFF4444)
        for rule in rules:
            status = "Enabled" if rule.is_enabled else "Disabled"
            desc = f"Action: {rule.action} | Status: {status}"
            if rule.rule_type == "username_match":
                wildcard = " (wildcard)" if rule.use_wildcard else ""
                desc += f"\nPattern: {rule.pattern}{wildcard}"
            elif rule.rule_type == "account_age":
                desc += f"\nThreshold: {rule.threshold_hours}h"
            embed.add_field(
                name=f"#{rule.id} - {rule.rule_type}",
                value=desc,
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @autoban_group.command(name="logs", description="Autoban ログを表示")
    async def autoban_logs(self, interaction: discord.Interaction) -> None:
        """直近の autoban ログを表示する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)
        async with async_session() as session:
            logs = await get_autoban_logs_by_guild(session, guild_id, limit=10)

        if not logs:
            await interaction.response.send_message(
                "No autoban logs found.", ephemeral=True
            )
            return

        embed = discord.Embed(title="Autoban Logs (Last 10)", color=0xFF4444)
        for log_entry in logs:
            embed.add_field(
                name=f"{log_entry.username} ({log_entry.user_id})",
                value=(
                    f"Action: {log_entry.action_taken}\n"
                    f"Reason: {log_entry.reason}\n"
                    f"Rule: #{log_entry.rule_id}\n"
                    f"Date: {log_entry.created_at.strftime('%Y-%m-%d %H:%M')}"
                ),
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する。"""
    await bot.add_cog(AutoBanCog(bot))
    logger.info("AutoBan cog loaded")
