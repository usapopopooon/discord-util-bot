"""welcome feature の Discord 表示用 helper。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import discord

from src.services.welcome_banner_service import WelcomeBannerInput
from src.services.welcome_service import (
    DEFAULT_WELCOME_BANNER_MESSAGE_TEMPLATE,
    DEFAULT_WELCOME_MESSAGE_CONTENT,
    WelcomeMessageInput,
    limit_welcome_message_content,
    render_welcome_message,
)

WELCOME_EMBED_COLOR = 0xE0A2EB
WELCOME_PLACEHOLDERS = (
    "{mention}, {username}, {displayName}, {guildName}, {memberCount}"
)


class WelcomeConfigStatus(Protocol):
    """status 表示に必要な welcome 設定の最小 surface。"""

    enabled: bool
    channel_id: str
    message_content: str
    banner_message_template: str


@dataclass(frozen=True, slots=True)
class WelcomeRenderInputs:
    """welcome 本文用と画像内文言用の placeholder 入力。"""

    message: WelcomeMessageInput
    banner: WelcomeMessageInput


def format_message_content(content: str) -> str:
    """設定確認メッセージ内で長すぎる本文を短く表示する。"""
    return f"{content[:137]}..." if len(content) > 140 else content


def build_welcome_status_message(config: WelcomeConfigStatus | None) -> str:
    """``/welcome status`` で返す人間向けメッセージを組み立てる。"""
    if config is None or not config.enabled:
        return "\n".join(
            [
                "welcome投稿は無効です。",
                "デフォルト本文: "
                f"{format_message_content(DEFAULT_WELCOME_MESSAGE_CONTENT)}",
                "デフォルト画像内メッセージ: "
                f"{format_message_content(DEFAULT_WELCOME_BANNER_MESSAGE_TEMPLATE)}",
                f"使用可能なプレースホルダー: {WELCOME_PLACEHOLDERS}",
            ]
        )

    return "\n".join(
        [
            f"welcome投稿は有効です。送信先: <#{config.channel_id}>",
            f"本文: {format_message_content(config.message_content)}",
            "画像内メッセージ: "
            f"{format_message_content(config.banner_message_template)}",
            f"使用可能なプレースホルダー: {WELCOME_PLACEHOLDERS}",
        ]
    )


def build_welcome_render_inputs(
    *,
    username: str,
    display_name: str,
    guild_name: str,
    member_count: int,
    mention: str,
) -> WelcomeRenderInputs:
    """Discord member 情報から welcome 描画用 input を作る。"""
    return WelcomeRenderInputs(
        message=WelcomeMessageInput(
            username=username,
            display_name=display_name,
            guild_name=guild_name,
            member_count=member_count,
            mention=mention,
        ),
        banner=WelcomeMessageInput(
            username=username,
            display_name=display_name,
            guild_name=guild_name,
            member_count=member_count,
            mention=f"@{display_name}",
        ),
    )


def build_welcome_banner_input(
    *,
    display_name: str,
    username: str,
    guild_name: str,
    member_count: int,
    banner_message_template: str,
    inputs: WelcomeRenderInputs,
    avatar_bytes: bytes | None,
) -> WelcomeBannerInput:
    """welcome バナー生成 service に渡す input を組み立てる。"""
    return WelcomeBannerInput(
        display_name=display_name,
        username=username,
        guild_name=guild_name,
        headline_text=render_welcome_message(banner_message_template, inputs.banner),
        member_count=member_count,
        avatar_bytes=avatar_bytes,
    )


def build_welcome_embed(
    *,
    message_template: str,
    inputs: WelcomeRenderInputs,
    attachment_name: str,
) -> discord.Embed:
    """welcome 投稿用の embed を作る。"""
    embed = discord.Embed(
        description=limit_welcome_message_content(
            render_welcome_message(message_template, inputs.message)
        ),
        color=WELCOME_EMBED_COLOR,
    )
    embed.set_image(url=f"attachment://{attachment_name}")
    return embed
