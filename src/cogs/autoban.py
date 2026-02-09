"""Autoban cog.

新規メンバー参加時にルールに基づき自動 BAN/KICK する。

ルールタイプ:
  - username_match: ユーザー名マッチング (大文字小文字無視、ワイルドカード対応)
  - account_age: アカウント年齢 (作成からの時間が閾値未満なら該当)
  - no_avatar: アバター未設定
  - role_acquired: サーバーJOIN後 X秒以内にロール取得
  - vc_join: サーバーJOIN後 X秒以内にVC参加
  - message_post: サーバーJOIN後 X秒以内にメッセージ投稿
  - vc_without_intro: 指定チャンネル未投稿でVC参加
  - msg_without_intro: 指定チャンネル未投稿で別チャンネルに投稿

仕組み:
  - on_member_join イベントで新規メンバーを検知
  - on_member_update イベントでロール変更を検知
  - on_voice_state_update イベントでVC参加を検知
  - on_message イベントでメッセージ投稿を検知
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
    create_ban_log,
    delete_autoban_rule,
    get_autoban_config,
    get_autoban_logs_by_guild,
    get_autoban_rules_by_guild,
    get_enabled_autoban_rules_by_guild,
    has_intro_post,
    record_intro_post,
)

logger = logging.getLogger(__name__)

MAX_THRESHOLD_HOURS = 336
MAX_THRESHOLD_SECONDS = 3600


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

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        """メンバー更新時にロール取得の autoban ルールをチェックする。"""
        if after.bot:
            return

        # ロール変更がない場合はスキップ
        if before.roles == after.roles:
            return

        # ロールが追加されたかチェック
        added_roles = set(after.roles) - set(before.roles)
        if not added_roles:
            return

        guild_id = str(after.guild.id)

        async with async_session() as session:
            rules = await get_enabled_autoban_rules_by_guild(session, guild_id)

        if not rules:
            return

        for rule in rules:
            if rule.rule_type != "role_acquired":
                continue
            matched, reason = self._check_join_timing(rule, after)
            if matched:
                await self._execute_action(after, rule, reason)
                break

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """VC参加時の autoban ルールをチェックする。"""
        if member.bot:
            return

        # VC に新規参加した場合のみ (チャンネル移動は対象外)
        if before.channel is not None or after.channel is None:
            return

        guild_id = str(member.guild.id)

        async with async_session() as session:
            rules = await get_enabled_autoban_rules_by_guild(session, guild_id)

        if not rules:
            return

        for rule in rules:
            if rule.rule_type == "vc_join":
                matched, reason = self._check_join_timing(rule, member)
                if matched:
                    await self._execute_action(member, rule, reason)
                    return
            elif rule.rule_type == "vc_without_intro":
                matched, reason = await self._check_intro_missing(rule, member)
                if matched:
                    await self._execute_action(member, rule, reason)
                    return

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """メッセージ投稿時の autoban ルールをチェックする。"""
        if not message.guild or not message.author:
            return

        # Bot やシステムメッセージは無視
        if message.author.bot:
            return

        # Member オブジェクトが必要 (joined_at を参照するため)
        member = message.author
        if not isinstance(member, discord.Member):
            return

        guild_id = str(message.guild.id)

        async with async_session() as session:
            rules = await get_enabled_autoban_rules_by_guild(session, guild_id)

        if not rules:
            return

        channel_id_str = str(message.channel.id)

        # 指定チャンネルへの投稿を記録 (vc_without_intro / msg_without_intro 用)
        intro_rule_types = ("vc_without_intro", "msg_without_intro")
        required_channels = {
            r.required_channel_id
            for r in rules
            if r.rule_type in intro_rule_types and r.required_channel_id
        }
        if channel_id_str in required_channels:
            async with async_session() as session:
                await record_intro_post(
                    session, guild_id, str(member.id), channel_id_str
                )

        for rule in rules:
            if rule.rule_type == "message_post":
                matched, reason = self._check_join_timing(rule, member)
                if matched:
                    await self._execute_action(member, rule, reason)
                    return
            elif rule.rule_type == "msg_without_intro":
                # 指定チャンネル自体への投稿は対象外
                if channel_id_str == rule.required_channel_id:
                    continue
                matched, reason = await self._check_intro_missing(rule, member)
                if matched:
                    await self._execute_action(member, rule, reason)
                    return

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        """BAN イベントを検知して BAN ログを記録する。"""
        reason: str | None = None
        is_autoban = False
        try:
            ban_entry = await guild.fetch_ban(user)
            reason = ban_entry.reason
            if reason and reason.startswith("[Autoban]"):
                is_autoban = True
        except discord.NotFound:
            pass
        except discord.HTTPException as e:
            logger.warning("Failed to fetch ban info: %s", e)

        try:
            async with async_session() as session:
                await create_ban_log(
                    session,
                    guild_id=str(guild.id),
                    user_id=str(user.id),
                    username=user.name,
                    reason=reason,
                    is_autoban=is_autoban,
                )
        except Exception:
            logger.exception("Failed to create ban log for user %s", user.id)

    # ==========================================================================
    # ルールチェック
    # ==========================================================================

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
        if rule.rule_type in ("role_acquired", "vc_join", "message_post"):
            return self._check_join_timing(rule, member)
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

    def _check_join_timing(
        self, rule: AutoBanRule, member: discord.Member
    ) -> tuple[bool, str]:
        """サーバーJOIN後の経過時間をチェック (role_acquired / vc_join 共通)。"""
        if not rule.threshold_seconds or not member.joined_at:
            return False, ""

        elapsed = (datetime.now(UTC) - member.joined_at).total_seconds()
        if elapsed < rule.threshold_seconds:
            return True, (
                f"Action within {elapsed:.1f}s of join "
                f"(threshold: {rule.threshold_seconds}s)"
            )
        return False, ""

    async def _check_intro_missing(
        self, rule: AutoBanRule, member: discord.Member
    ) -> tuple[bool, str]:
        """指定チャンネルに投稿していないかチェック。"""
        if not rule.required_channel_id or not member.joined_at:
            return False, ""

        # ルール作成前に参加したメンバーは対象外
        if member.joined_at < rule.created_at:
            return False, ""

        async with async_session() as session:
            posted = await has_intro_post(
                session,
                str(member.guild.id),
                str(member.id),
                rule.required_channel_id,
            )

        if not posted:
            return True, (f"No post in required channel ({rule.required_channel_id})")
        return False, ""

    # ==========================================================================
    # アクション実行
    # ==========================================================================

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

        # ログ送信用にメンバー情報を事前に保存 (BAN後はアクセス不可)
        member_name = member.name
        member_id = member.id
        member_display_name = member.display_name
        member_avatar_url = member.display_avatar.url if member.display_avatar else None
        member_created_at = member.created_at
        member_joined_at = member.joined_at

        try:
            if rule.action == "ban":
                await guild.ban(member, reason=full_reason)
            else:
                await guild.kick(member, reason=full_reason)

            logger.info(
                "Autoban %s user %s (%s) in guild %s: %s",
                action_taken,
                member_name,
                member_id,
                guild.id,
                reason,
            )
        except discord.Forbidden:
            logger.warning(
                "Missing permissions to %s user %s (%s) in guild %s",
                rule.action,
                member_name,
                member_id,
                guild.id,
            )
            return
        except discord.HTTPException as e:
            logger.error(
                "Failed to %s user %s (%s) in guild %s: %s",
                rule.action,
                member_name,
                member_id,
                guild.id,
                e,
            )
            return

        async with async_session() as session:
            await create_autoban_log(
                session,
                guild_id=str(guild.id),
                user_id=str(member_id),
                username=member_name,
                rule_id=rule.id,
                action_taken=action_taken,
                reason=reason,
            )

            # ログチャンネルに通知を送信
            config = await get_autoban_config(session, str(guild.id))

        if config and config.log_channel_id:
            await self._send_log_embed(
                guild=guild,
                channel_id=config.log_channel_id,
                action_taken=action_taken,
                rule=rule,
                reason=reason,
                member_name=member_name,
                member_id=member_id,
                member_display_name=member_display_name,
                member_avatar_url=member_avatar_url,
                member_created_at=member_created_at,
                member_joined_at=member_joined_at,
            )

    async def _send_log_embed(
        self,
        *,
        guild: discord.Guild,
        channel_id: str,
        action_taken: str,
        rule: AutoBanRule,
        reason: str,
        member_name: str,
        member_id: int,
        member_display_name: str,
        member_avatar_url: str | None,
        member_created_at: datetime,
        member_joined_at: datetime | None,
    ) -> None:
        """ログチャンネルに BAN/KICK の通知 Embed を送信する。"""
        channel = guild.get_channel(int(channel_id))
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning("Log channel %s not found in guild %s", channel_id, guild.id)
            return

        color = 0xFF0000 if action_taken == "banned" else 0xFFA500
        title = f"[AutoBan] User {action_taken.capitalize()}"

        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=datetime.now(UTC),
        )

        if member_avatar_url:
            embed.set_thumbnail(url=member_avatar_url)

        embed.add_field(
            name="User",
            value=f"{member_display_name} (`{member_name}`)",
            inline=True,
        )
        embed.add_field(
            name="User ID",
            value=str(member_id),
            inline=True,
        )
        embed.add_field(
            name="Action",
            value=action_taken.upper(),
            inline=True,
        )
        embed.add_field(
            name="Rule",
            value=f"#{rule.id} ({rule.rule_type})",
            inline=True,
        )
        embed.add_field(
            name="Reason",
            value=reason,
            inline=False,
        )

        created_str = member_created_at.strftime("%Y-%m-%d %H:%M UTC")
        embed.add_field(
            name="Account Created",
            value=created_str,
            inline=True,
        )

        if member_joined_at:
            joined_str = member_joined_at.strftime("%Y-%m-%d %H:%M UTC")
            elapsed = (datetime.now(UTC) - member_joined_at).total_seconds()
            embed.add_field(
                name="Joined Server",
                value=f"{joined_str} ({elapsed:.0f}s ago)",
                inline=True,
            )

        embed.set_footer(text=f"Server: {guild.name}")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning(
                "Missing permissions to send log to channel %s in guild %s",
                channel_id,
                guild.id,
            )
        except discord.HTTPException as e:
            logger.error(
                "Failed to send log to channel %s in guild %s: %s",
                channel_id,
                guild.id,
                e,
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
        threshold_seconds="JOIN後の閾値 (秒、role_acquired/vc_join のみ、最大 3600)",
    )
    @app_commands.choices(
        rule_type=[
            app_commands.Choice(name="Username Match", value="username_match"),
            app_commands.Choice(name="Account Age", value="account_age"),
            app_commands.Choice(name="No Avatar", value="no_avatar"),
            app_commands.Choice(
                name="Role Acquired (after join)", value="role_acquired"
            ),
            app_commands.Choice(name="VC Join (after join)", value="vc_join"),
            app_commands.Choice(name="Message Post (after join)", value="message_post"),
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
        threshold_seconds: int | None = None,
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

        if rule_type in ("role_acquired", "vc_join", "message_post"):
            if not threshold_seconds or threshold_seconds < 1:
                await interaction.response.send_message(
                    f"{rule_type} ルールには 1 以上の threshold_seconds が必要です。",
                    ephemeral=True,
                )
                return
            if threshold_seconds > MAX_THRESHOLD_SECONDS:
                await interaction.response.send_message(
                    f"threshold_seconds は最大 {MAX_THRESHOLD_SECONDS} (1時間) です。",
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
                threshold_seconds=threshold_seconds,
            )

        desc_parts = [f"Type: {rule_type}", f"Action: {action}"]
        if pattern:
            desc_parts.append(f"Pattern: {pattern}")
            if use_wildcard:
                desc_parts.append("Wildcard: Yes")
        if threshold_hours:
            desc_parts.append(f"Threshold: {threshold_hours}h")
        if threshold_seconds:
            desc_parts.append(f"Threshold: {threshold_seconds}s")

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
            elif rule.rule_type in ("role_acquired", "vc_join", "message_post"):
                desc += f"\nThreshold: {rule.threshold_seconds}s after join"
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
