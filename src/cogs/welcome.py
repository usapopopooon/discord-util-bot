"""Welcome cog.

メンバー参加時に CHILL カフェ風の welcome 画像を送信する。
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any, Protocol, TypeGuard

import discord
from discord import app_commands
from discord.ext import commands

from src.database.engine import async_session
from src.services.welcome_banner_service import (
    WelcomeBannerInput,
    WelcomeBannerService,
)
from src.services.welcome_service import (
    DEFAULT_WELCOME_BANNER_MESSAGE_TEMPLATE,
    DEFAULT_WELCOME_MESSAGE_CONTENT,
    MAX_WELCOME_BANNER_MESSAGE_LENGTH,
    MAX_WELCOME_MESSAGE_LENGTH,
    WelcomeMessageInput,
    disable_welcome_config,
    get_welcome_config,
    limit_welcome_message_content,
    render_welcome_message,
    set_welcome_banner_message,
    set_welcome_channel,
    set_welcome_message,
)

logger = logging.getLogger(__name__)

WELCOME_EMBED_COLOR = 0xE0A2EB
WELCOME_PLACEHOLDERS = (
    "{mention}, {username}, {displayName}, {guildName}, {memberCount}"
)


class WelcomeSendableChannel(Protocol):
    id: int

    async def send(self, *args: Any, **kwargs: Any) -> Any: ...


class WelcomeCog(commands.Cog):
    """Welcome 画像投稿機能を提供する Cog。"""

    welcome = app_commands.Group(
        name="welcome",
        description="参加時のwelcome画像投稿を設定します",
        guild_only=True,
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(
        self,
        bot: commands.Bot,
        banner_service: WelcomeBannerService | None = None,
    ) -> None:
        self.bot = bot
        self.banner_service = banner_service or WelcomeBannerService()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """新規メンバー参加時に welcome 投稿を送信する。"""
        await self.send_welcome(member)

    @welcome.command(
        name="set", description="welcome画像の送信先チャンネルを設定します"
    )
    @app_commands.describe(channel="welcome画像を送信するチャンネル")
    async def welcome_set(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if not await self._ensure_admin(interaction):
            return
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return
        if not _can_bot_send_welcome(channel, interaction.guild):
            await interaction.response.send_message(
                "そのチャンネルに送信、ファイル添付、"
                "埋め込みリンク送信する権限が Bot にありません。",
                ephemeral=True,
            )
            return

        async with async_session() as session:
            await set_welcome_channel(
                session,
                guild_id=str(interaction.guild.id),
                channel_id=str(channel.id),
            )

        await interaction.response.send_message(
            f"welcome画像の送信先を {channel.mention} に設定しました。",
            ephemeral=True,
        )

    @welcome.command(
        name="message", description="welcome画像と一緒に送る本文を設定します"
    )
    @app_commands.describe(content=f"本文。使用可能: {WELCOME_PLACEHOLDERS}")
    async def welcome_message(
        self, interaction: discord.Interaction, content: str
    ) -> None:
        if not await self._ensure_admin(interaction):
            return
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        content = content.strip()
        if not content:
            await interaction.response.send_message(
                "本文は空にできません。", ephemeral=True
            )
            return
        if len(content) > MAX_WELCOME_MESSAGE_LENGTH:
            await interaction.response.send_message(
                f"本文は{MAX_WELCOME_MESSAGE_LENGTH}文字以内にしてください。",
                ephemeral=True,
            )
            return

        async with async_session() as session:
            config = await set_welcome_message(
                session, str(interaction.guild.id), content
            )

        if config is None:
            await interaction.response.send_message(
                "先に `/welcome set` で送信先チャンネルを設定してください。",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"welcome本文を設定しました。\n{_format_message_content(config.message_content)}",
            ephemeral=True,
        )

    @welcome.command(
        name="banner-message",
        description="welcome画像内に表示するメッセージを設定します",
    )
    @app_commands.describe(
        content=f"画像内メッセージ。使用可能: {WELCOME_PLACEHOLDERS}"
    )
    async def welcome_banner_message(
        self, interaction: discord.Interaction, content: str
    ) -> None:
        if not await self._ensure_admin(interaction):
            return
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        content = content.strip()
        if not content:
            await interaction.response.send_message(
                "画像内メッセージは空にできません。", ephemeral=True
            )
            return
        if len(content) > MAX_WELCOME_BANNER_MESSAGE_LENGTH:
            await interaction.response.send_message(
                f"画像内メッセージは{MAX_WELCOME_BANNER_MESSAGE_LENGTH}文字以内にしてください。",
                ephemeral=True,
            )
            return

        async with async_session() as session:
            config = await set_welcome_banner_message(
                session, str(interaction.guild.id), content
            )

        if config is None:
            await interaction.response.send_message(
                "先に `/welcome set` で送信先チャンネルを設定してください。",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "welcome画像内メッセージを設定しました。\n"
            f"{_format_message_content(config.banner_message_template)}",
            ephemeral=True,
        )

    @welcome.command(name="disable", description="welcome投稿を無効にします")
    async def welcome_disable(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_admin(interaction):
            return
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        async with async_session() as session:
            await disable_welcome_config(session, str(interaction.guild.id))

        await interaction.response.send_message(
            "welcome投稿を無効にしました。", ephemeral=True
        )

    @welcome.command(name="status", description="welcome設定を表示します")
    async def welcome_status(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_admin(interaction):
            return
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        async with async_session() as session:
            config = await get_welcome_config(session, str(interaction.guild.id))

        if config is None or not config.enabled:
            await interaction.response.send_message(
                "\n".join(
                    [
                        "welcome投稿は無効です。",
                        "デフォルト本文: "
                        f"{_format_message_content(DEFAULT_WELCOME_MESSAGE_CONTENT)}",
                        "デフォルト画像内メッセージ: "
                        f"{_format_message_content(DEFAULT_WELCOME_BANNER_MESSAGE_TEMPLATE)}",
                        f"使用可能なプレースホルダー: {WELCOME_PLACEHOLDERS}",
                    ]
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "\n".join(
                [
                    f"welcome投稿は有効です。送信先: <#{config.channel_id}>",
                    f"本文: {_format_message_content(config.message_content)}",
                    "画像内メッセージ: "
                    f"{_format_message_content(config.banner_message_template)}",
                    f"使用可能なプレースホルダー: {WELCOME_PLACEHOLDERS}",
                ]
            ),
            ephemeral=True,
        )

    @welcome.command(name="test", description="設定済みチャンネルにテスト投稿します")
    async def welcome_test(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_admin(interaction):
            return
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        sent = await self.send_welcome(interaction.user)
        await interaction.followup.send(
            "welcomeのテスト投稿を送信しました。"
            if sent
            else (
                "welcomeのテスト投稿を送信できませんでした。"
                "設定と Bot の送信権限を確認してください。"
            ),
            ephemeral=True,
        )

    async def send_welcome(self, member: discord.Member) -> bool:
        """設定済みチャンネルに welcome 画像を送信する。"""
        async with async_session() as session:
            config = await get_welcome_config(session, str(member.guild.id))

        if config is None or not config.enabled:
            return False

        channel = await self._fetch_sendable_channel(member.guild, config.channel_id)
        if channel is None:
            logger.warning(
                "Welcome channel is not sendable: guild=%s channel=%s",
                member.guild.id,
                config.channel_id,
            )
            return False

        try:
            member_count = member.guild.member_count or 0
            template_input = WelcomeMessageInput(
                username=member.name,
                display_name=member.display_name,
                guild_name=member.guild.name,
                member_count=member_count,
                mention=member.mention,
            )
            banner_input = WelcomeMessageInput(
                username=member.name,
                display_name=member.display_name,
                guild_name=member.guild.name,
                member_count=member_count,
                mention=f"@{member.display_name}",
            )
            avatar_bytes = await _read_member_avatar(member)
            image_bytes = self.banner_service.create(
                WelcomeBannerInput(
                    display_name=member.display_name,
                    username=member.name,
                    guild_name=member.guild.name,
                    headline_text=render_welcome_message(
                        config.banner_message_template, banner_input
                    ),
                    member_count=member_count,
                    avatar_bytes=avatar_bytes,
                )
            )
            attachment_name = f"welcome-{member.id}.png"
            file = discord.File(BytesIO(image_bytes), filename=attachment_name)
            embed = discord.Embed(
                description=limit_welcome_message_content(
                    render_welcome_message(config.message_content, template_input)
                ),
                color=WELCOME_EMBED_COLOR,
            )
            embed.set_image(url=f"attachment://{attachment_name}")

            await channel.send(
                embed=embed,
                file=file,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            logger.info(
                "Sent welcome banner: guild=%s user=%s", member.guild.id, member.id
            )
            return True
        except Exception:
            logger.exception(
                "Failed to send welcome banner: guild=%s channel=%s user=%s",
                member.guild.id,
                config.channel_id,
                member.id,
            )
            return False

    async def _fetch_sendable_channel(
        self, guild: discord.Guild, channel_id: str
    ) -> WelcomeSendableChannel | None:
        numeric_channel_id = int(channel_id)
        cached = guild.get_channel_or_thread(numeric_channel_id)
        if _is_sendable_channel(cached):
            return cached

        try:
            fetched = await guild.fetch_channel(numeric_channel_id)
        except discord.HTTPException:
            return None
        return fetched if _is_sendable_channel(fetched) else None

    async def _ensure_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return False
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return False
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "このコマンドは管理者のみ実行できます。", ephemeral=True
            )
            return False
        return True


def _is_sendable_channel(channel: object) -> TypeGuard[WelcomeSendableChannel]:
    return (
        hasattr(channel, "send") and callable(channel.send) and hasattr(channel, "id")
    )


def _can_bot_send_welcome(channel: object, guild: discord.Guild) -> bool:
    me = guild.me
    if me is None:
        return True

    permissions_for = getattr(channel, "permissions_for", None)
    if not callable(permissions_for):
        return True

    permissions = permissions_for(me)
    return bool(
        permissions
        and permissions.view_channel
        and permissions.send_messages
        and permissions.attach_files
        and permissions.embed_links
    )


async def _read_member_avatar(member: discord.Member) -> bytes | None:
    try:
        return await member.display_avatar.replace(size=512, static_format="png").read()
    except (discord.HTTPException, ValueError):
        logger.warning(
            "Failed to read avatar: guild=%s user=%s", member.guild.id, member.id
        )
        return None


def _format_message_content(content: str) -> str:
    return f"{content[:137]}..." if len(content) > 140 else content


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する。"""
    await bot.add_cog(WelcomeCog(bot))
