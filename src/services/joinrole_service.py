"""JoinRole の DB 操作。"""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import JoinRoleAssignment, JoinRoleConfig

__all__ = [
    "claim_join_role_assignment",
    "create_join_role_assignment",
    "create_join_role_config",
    "delete_join_role_assignment",
    "delete_join_role_config",
    "get_enabled_join_role_configs",
    "get_expired_join_role_assignments",
    "get_join_role_configs",
    "toggle_join_role_config",
]


# =============================================================================
# JoinRole (自動ロール付与) 操作
# =============================================================================


async def create_join_role_config(
    session: AsyncSession,
    guild_id: str,
    role_id: str,
    duration_hours: int,
) -> JoinRoleConfig:
    """JoinRole 設定を作成する。"""
    config = JoinRoleConfig(
        guild_id=guild_id,
        role_id=role_id,
        duration_hours=duration_hours,
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


async def get_join_role_configs(
    session: AsyncSession, guild_id: str | None = None
) -> list[JoinRoleConfig]:
    """JoinRole 設定を取得する。guild_id 指定で絞り込み。"""
    stmt = select(JoinRoleConfig).order_by(JoinRoleConfig.id)
    if guild_id is not None:
        stmt = stmt.where(JoinRoleConfig.guild_id == guild_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_enabled_join_role_configs(
    session: AsyncSession, guild_id: str
) -> list[JoinRoleConfig]:
    """指定ギルドの有効な JoinRole 設定を取得する。"""
    stmt = (
        select(JoinRoleConfig)
        .where(JoinRoleConfig.guild_id == guild_id, JoinRoleConfig.enabled.is_(True))
        .order_by(JoinRoleConfig.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_join_role_config(session: AsyncSession, config_id: int) -> bool:
    """JoinRole 設定を削除する。"""
    stmt = delete(JoinRoleConfig).where(JoinRoleConfig.id == config_id)
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount) > 0  # type: ignore[attr-defined]


async def toggle_join_role_config(
    session: AsyncSession, config_id: int
) -> JoinRoleConfig | None:
    """JoinRole 設定の有効/無効を切り替える。"""
    stmt = select(JoinRoleConfig).where(JoinRoleConfig.id == config_id)
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()
    if config is None:
        return None
    config.enabled = not config.enabled
    await session.commit()
    await session.refresh(config)
    return config


async def create_join_role_assignment(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    role_id: str,
    assigned_at: datetime,
    expires_at: datetime,
) -> JoinRoleAssignment:
    """JoinRole 付与レコードを作成する。"""
    assignment = JoinRoleAssignment(
        guild_id=guild_id,
        user_id=user_id,
        role_id=role_id,
        assigned_at=assigned_at,
        expires_at=expires_at,
    )
    session.add(assignment)
    await session.commit()
    await session.refresh(assignment)
    return assignment


async def claim_join_role_assignment(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    role_id: str,
    assigned_at: datetime,
    expires_at: datetime,
) -> JoinRoleAssignment | None:
    """JoinRole 付与レコードをアトミックに作成する。

    同一 (guild_id, user_id, role_id) のレコードが直近 10 秒以内に存在する場合は
    重複と見なし None を返す (別インスタンスが先に処理済み)。
    """
    from datetime import timedelta

    threshold = assigned_at - timedelta(seconds=10)
    dup = await session.execute(
        select(JoinRoleAssignment.id).where(
            JoinRoleAssignment.guild_id == guild_id,
            JoinRoleAssignment.user_id == user_id,
            JoinRoleAssignment.role_id == role_id,
            JoinRoleAssignment.assigned_at >= threshold,
        )
    )
    if dup.scalar_one_or_none() is not None:
        return None  # 別インスタンスが先に処理済み

    assignment = JoinRoleAssignment(
        guild_id=guild_id,
        user_id=user_id,
        role_id=role_id,
        assigned_at=assigned_at,
        expires_at=expires_at,
    )
    session.add(assignment)
    await session.commit()
    await session.refresh(assignment)
    return assignment


async def get_expired_join_role_assignments(
    session: AsyncSession, now: datetime
) -> list[JoinRoleAssignment]:
    """期限切れの JoinRole 付与レコードを取得する。"""
    stmt = (
        select(JoinRoleAssignment)
        .where(JoinRoleAssignment.expires_at <= now)
        .order_by(JoinRoleAssignment.expires_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_join_role_assignment(
    session: AsyncSession, assignment_id: int
) -> bool:
    """JoinRole 付与レコードを削除する。"""
    stmt = delete(JoinRoleAssignment).where(JoinRoleAssignment.id == assignment_id)
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount) > 0  # type: ignore[attr-defined]
