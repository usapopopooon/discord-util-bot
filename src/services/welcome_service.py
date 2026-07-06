"""Welcome 設定とメッセージ描画用のサービス関数。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import WelcomeConfig

__all__ = [
    "DEFAULT_WELCOME_BANNER_MESSAGE_TEMPLATE",
    "DEFAULT_WELCOME_MESSAGE_CONTENT",
    "MAX_WELCOME_BANNER_MESSAGE_LENGTH",
    "MAX_WELCOME_MESSAGE_LENGTH",
    "WelcomeMessageInput",
    "disable_welcome_config",
    "get_welcome_config",
    "limit_welcome_message_content",
    "render_welcome_message",
    "set_welcome_banner_message",
    "set_welcome_channel",
    "set_welcome_message",
]

DEFAULT_WELCOME_MESSAGE_CONTENT = "いらっしゃいませ、{mention}!"
DEFAULT_WELCOME_BANNER_MESSAGE_TEMPLATE = "{displayName} さんが入店しました"
MAX_WELCOME_MESSAGE_LENGTH = 1_500
MAX_WELCOME_BANNER_MESSAGE_LENGTH = 160
DISCORD_MESSAGE_MAX_LENGTH = 2_000
_TRUNCATION_SUFFIX = "..."


@dataclass(frozen=True, slots=True)
class WelcomeMessageInput:
    """welcome 本文と画像内テキストのプレースホルダー入力。"""

    mention: str
    username: str
    display_name: str
    guild_name: str
    member_count: int


async def get_welcome_config(
    session: AsyncSession, guild_id: str
) -> WelcomeConfig | None:
    """ギルドの welcome 設定を取得する。"""
    result = await session.execute(
        select(WelcomeConfig).where(WelcomeConfig.guild_id == guild_id)
    )
    return result.scalar_one_or_none()


async def set_welcome_channel(
    session: AsyncSession, guild_id: str, channel_id: str
) -> WelcomeConfig:
    """welcome 送信先を設定し、有効化する。"""
    config = await get_welcome_config(session, guild_id)

    if config is None:
        config = WelcomeConfig(
            guild_id=guild_id,
            channel_id=channel_id,
            enabled=True,
            message_content=DEFAULT_WELCOME_MESSAGE_CONTENT,
            banner_message_template=DEFAULT_WELCOME_BANNER_MESSAGE_TEMPLATE,
        )
        session.add(config)
    else:
        config.channel_id = channel_id
        config.enabled = True

    await session.commit()
    await session.refresh(config)
    return config


async def set_welcome_message(
    session: AsyncSession, guild_id: str, message_content: str
) -> WelcomeConfig | None:
    """welcome embed の本文テンプレートを更新する。"""
    config = await get_welcome_config(session, guild_id)
    if config is None:
        return None

    config.message_content = message_content
    await session.commit()
    await session.refresh(config)
    return config


async def set_welcome_banner_message(
    session: AsyncSession, guild_id: str, banner_message_template: str
) -> WelcomeConfig | None:
    """welcome 画像内に描画するメッセージテンプレートを更新する。"""
    config = await get_welcome_config(session, guild_id)
    if config is None:
        return None

    config.banner_message_template = banner_message_template
    await session.commit()
    await session.refresh(config)
    return config


async def disable_welcome_config(
    session: AsyncSession, guild_id: str
) -> WelcomeConfig | None:
    """welcome 投稿を無効化する。設定がない場合は None を返す。"""
    config = await get_welcome_config(session, guild_id)
    if config is None:
        return None

    config.enabled = False
    await session.commit()
    await session.refresh(config)
    return config


def render_welcome_message(template: str, input_data: WelcomeMessageInput) -> str:
    """welcome テンプレート内の既知プレースホルダーを置換する。

    kakuzato-bot と同じ camelCase 形式を主に使い、Python 側から扱いやすい
    snake_case 形式も同じ値として受け付ける。
    """
    replacements = {
        "mention": input_data.mention,
        "username": input_data.username,
        "displayName": input_data.display_name,
        "display_name": input_data.display_name,
        "guildName": input_data.guild_name,
        "guild_name": input_data.guild_name,
        "memberCount": str(input_data.member_count),
        "member_count": str(input_data.member_count),
    }

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return replacements.get(key, match.group(0))

    return re.sub(r"\{([A-Za-z_]+)\}", replace, template)


def limit_welcome_message_content(content: str) -> str:
    """Discord の通常メッセージ上限に収まるよう本文を切り詰める。"""
    if len(content) <= DISCORD_MESSAGE_MAX_LENGTH:
        return content

    max_body_length = DISCORD_MESSAGE_MAX_LENGTH - len(_TRUNCATION_SUFFIX)
    return f"{content[:max_body_length]}{_TRUNCATION_SUFFIX}"
