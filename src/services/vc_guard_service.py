"""VCGuard の DB 操作。"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import VCGuardConfig

__all__ = [
    "delete_vc_guard_config",
    "delete_vc_guard_config_by_channel",
    "delete_vc_guard_configs_by_channel_ids",
    "get_enabled_vc_guard_channel_map",
    "get_vc_guard_configs",
    "upsert_vc_guard_config",
]


async def upsert_vc_guard_config(
    session: AsyncSession, guild_id: str, channel_id: str
) -> VCGuardConfig:
    """VCGuard 設定を作成または有効化する。"""
    stmt = select(VCGuardConfig).where(
        VCGuardConfig.guild_id == guild_id,
        VCGuardConfig.channel_id == channel_id,
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()

    if config is None:
        config = VCGuardConfig(guild_id=guild_id, channel_id=channel_id)
        session.add(config)
    else:
        config.enabled = True

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(stmt)
        config = result.scalar_one()
        config.enabled = True
        await session.commit()

    await session.refresh(config)
    return config


async def get_vc_guard_configs(
    session: AsyncSession, guild_id: str | None = None
) -> list[VCGuardConfig]:
    """VCGuard 設定を取得する。guild_id 指定で絞り込み。"""
    stmt = select(VCGuardConfig).order_by(VCGuardConfig.id)
    if guild_id is not None:
        stmt = stmt.where(VCGuardConfig.guild_id == guild_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_enabled_vc_guard_channel_map(
    session: AsyncSession,
) -> dict[str, set[str]]:
    """有効な VCGuard 設定を guild_id -> channel_id set で取得する。"""
    stmt = select(VCGuardConfig.guild_id, VCGuardConfig.channel_id).where(
        VCGuardConfig.enabled.is_(True)
    )
    result = await session.execute(stmt)
    configs: dict[str, set[str]] = {}
    for guild_id, channel_id in result.all():
        configs.setdefault(guild_id, set()).add(channel_id)
    return configs


async def delete_vc_guard_config(session: AsyncSession, config_id: int) -> bool:
    """VCGuard 設定を ID で削除する。"""
    stmt = delete(VCGuardConfig).where(VCGuardConfig.id == config_id)
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount) > 0  # type: ignore[attr-defined]


async def delete_vc_guard_config_by_channel(
    session: AsyncSession, guild_id: str, channel_id: str
) -> bool:
    """VCGuard 設定を guild_id/channel_id で削除する。"""
    stmt = delete(VCGuardConfig).where(
        VCGuardConfig.guild_id == guild_id,
        VCGuardConfig.channel_id == channel_id,
    )
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount) > 0  # type: ignore[attr-defined]


async def delete_vc_guard_configs_by_channel_ids(
    session: AsyncSession, channel_ids: set[str]
) -> int:
    """指定チャンネル ID 群に紐づく VCGuard 設定を削除する。"""
    if not channel_ids:
        return 0
    stmt = delete(VCGuardConfig).where(VCGuardConfig.channel_id.in_(channel_ids))
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]
