"""AutoReaction の DB 操作。"""

from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import AutoReactionConfig

__all__ = [
    "MAX_AUTO_REACTION_EMOJIS",
    "create_auto_reaction_config",
    "decode_auto_reaction_emojis",
    "delete_auto_reaction_config",
    "encode_auto_reaction_emojis",
    "get_auto_reaction_configs",
    "get_enabled_auto_reaction_config_for_channel",
    "get_enabled_auto_reaction_emoji_map",
    "normalize_auto_reaction_emojis",
    "toggle_auto_reaction_config",
    "update_auto_reaction_emojis",
]

MAX_AUTO_REACTION_EMOJIS = 20


def normalize_auto_reaction_emojis(emojis: list[str]) -> list[str]:
    """ユーザー入力を絵文字リストに正規化する (前後空白除去、空要素除外)。"""
    return [e.strip() for e in emojis if isinstance(e, str) and e.strip()]


def encode_auto_reaction_emojis(emojis: list[str]) -> str:
    """絵文字リストを JSON 文字列にエンコードする。"""
    return json.dumps(emojis, ensure_ascii=False)


def decode_auto_reaction_emojis(encoded: str) -> list[str]:
    """DB に保存された JSON 文字列を絵文字リストに戻す。

    壊れた JSON や型不一致の場合は空リストを返し、Cog 側でスキップさせる。
    """
    try:
        value = json.loads(encoded)
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [s for s in value if isinstance(s, str) and s]


async def create_auto_reaction_config(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
    emojis: list[str],
) -> AutoReactionConfig:
    """AutoReaction 設定を作成する。"""
    config = AutoReactionConfig(
        guild_id=guild_id,
        channel_id=channel_id,
        emojis=encode_auto_reaction_emojis(emojis),
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


async def get_auto_reaction_configs(
    session: AsyncSession, guild_id: str | None = None
) -> list[AutoReactionConfig]:
    """AutoReaction 設定を取得する。guild_id 指定で絞り込み。"""
    stmt = select(AutoReactionConfig).order_by(AutoReactionConfig.id)
    if guild_id is not None:
        stmt = stmt.where(AutoReactionConfig.guild_id == guild_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_enabled_auto_reaction_config_for_channel(
    session: AsyncSession, guild_id: str, channel_id: str
) -> AutoReactionConfig | None:
    """指定チャンネルの有効な AutoReaction 設定を取得する。"""
    stmt = select(AutoReactionConfig).where(
        AutoReactionConfig.guild_id == guild_id,
        AutoReactionConfig.channel_id == channel_id,
        AutoReactionConfig.enabled.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_enabled_auto_reaction_emoji_map(
    session: AsyncSession,
) -> dict[str, list[str]]:
    """有効な AutoReaction 設定の channel_id → 絵文字リストの辞書を取得する。

    Cog の on_message ホットパスでこの辞書をキャッシュすることで、
    DB 問い合わせと JSON デコードを毎メッセージで行わずに済ませる。
    """
    stmt = select(AutoReactionConfig.channel_id, AutoReactionConfig.emojis).where(
        AutoReactionConfig.enabled.is_(True)
    )
    result = await session.execute(stmt)
    return {
        channel_id: decode_auto_reaction_emojis(emojis)
        for channel_id, emojis in result.all()
    }


async def update_auto_reaction_emojis(
    session: AsyncSession, config_id: int, emojis: list[str]
) -> AutoReactionConfig | None:
    """AutoReaction 設定の絵文字リストを更新する。"""
    stmt = select(AutoReactionConfig).where(AutoReactionConfig.id == config_id)
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()
    if config is None:
        return None
    config.emojis = encode_auto_reaction_emojis(emojis)
    await session.commit()
    await session.refresh(config)
    return config


async def toggle_auto_reaction_config(
    session: AsyncSession, config_id: int
) -> AutoReactionConfig | None:
    """AutoReaction 設定の有効/無効を切り替える。"""
    stmt = select(AutoReactionConfig).where(AutoReactionConfig.id == config_id)
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()
    if config is None:
        return None
    config.enabled = not config.enabled
    await session.commit()
    await session.refresh(config)
    return config


async def delete_auto_reaction_config(session: AsyncSession, config_id: int) -> bool:
    """AutoReaction 設定を削除する。"""
    stmt = delete(AutoReactionConfig).where(AutoReactionConfig.id == config_id)
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount) > 0  # type: ignore[attr-defined]
