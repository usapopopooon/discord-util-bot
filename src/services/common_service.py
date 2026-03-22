"""ProcessedEvent, BotActivity, SiteSettings, HealthConfig, EventLogConfig。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    BotActivity,
    EventLogConfig,
    HealthConfig,
    ProcessedEvent,
    SiteSettings,
)

__all__ = [
    "claim_event",
    "cleanup_expired_events",
    "delete_health_config",
    "get_all_health_configs",
    "get_bot_activity",
    "get_enabled_event_log_configs",
    "get_event_log_configs",
    "get_health_config",
    "get_site_settings",
    "upsert_bot_activity",
    "upsert_health_config",
    "upsert_site_settings",
]


# =============================================================================
# ProcessedEvent (重複排除テーブル) 操作
# =============================================================================


async def claim_event(session: AsyncSession, event_key: str) -> bool:
    """イベントをアトミックに claim する。

    UNIQUE 制約 (event_key) を利用し、INSERT の IntegrityError で
    「既に別インスタンスが処理済み」をアトミックに判定する。

    Args:
        session: DB セッション。
        event_key: イベントを一意に識別するキー。

    Returns:
        True: このインスタンスが claim に成功 (処理を続行すべき)。
        False: 別インスタンスが既に claim 済み (処理をスキップすべき)。
    """
    try:
        session.add(ProcessedEvent(event_key=event_key))
        await session.flush()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def cleanup_expired_events(
    session: AsyncSession, max_age_seconds: int = 3600
) -> int:
    """期限切れの重複排除レコードを削除する。

    Args:
        session: DB セッション。
        max_age_seconds: レコードの最大保持期間 (秒)。デフォルト 3600 (1時間)。

    Returns:
        削除されたレコード数。
    """
    cutoff = datetime.now(tz=UTC) - timedelta(seconds=max_age_seconds)
    stmt = delete(ProcessedEvent).where(ProcessedEvent.created_at < cutoff)
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


# =============================================================================
# BotActivity (Bot アクティビティ) 操作
# =============================================================================


async def get_bot_activity(session: AsyncSession) -> BotActivity | None:
    """Bot アクティビティ設定を取得する。

    シングルレコードを想定。レコードが無い場合は None を返す。

    Args:
        session: DB セッション。

    Returns:
        BotActivity レコード、または None。
    """
    result = await session.execute(select(BotActivity).limit(1))
    return result.scalar_one_or_none()


async def upsert_bot_activity(
    session: AsyncSession, activity_type: str, activity_text: str
) -> BotActivity:
    """Bot アクティビティ設定を作成または更新する。

    Args:
        session: DB セッション。
        activity_type: アクティビティの種類
            (playing / listening / watching / competing)。
        activity_text: 表示テキスト。

    Returns:
        作成または更新された BotActivity レコード。
    """
    existing = await get_bot_activity(session)
    if existing:
        existing.activity_type = activity_type
        existing.activity_text = activity_text
        existing.updated_at = datetime.now(UTC)
    else:
        existing = BotActivity(
            activity_type=activity_type,
            activity_text=activity_text,
        )
        session.add(existing)
    await session.commit()
    return existing


# =============================================================================
# SiteSettings (サイト全体設定) 操作
# =============================================================================


async def get_site_settings(session: AsyncSession) -> SiteSettings | None:
    """サイト設定を取得する。"""
    result = await session.execute(select(SiteSettings).limit(1))
    return result.scalar_one_or_none()


async def upsert_site_settings(
    session: AsyncSession, *, timezone_offset: int
) -> SiteSettings:
    """サイト設定を作成または更新する。"""
    existing = await get_site_settings(session)
    if existing:
        existing.timezone_offset = timezone_offset
        existing.updated_at = datetime.now(UTC)
    else:
        existing = SiteSettings(timezone_offset=timezone_offset)
        session.add(existing)
    await session.commit()
    return existing


# =============================================================================
# HealthConfig (ヘルスチェック設定) 操作
# =============================================================================


async def get_health_config(
    session: AsyncSession, guild_id: str
) -> HealthConfig | None:
    """ギルドのヘルスチェック設定を取得する。"""
    result = await session.execute(
        select(HealthConfig).where(HealthConfig.guild_id == guild_id)
    )
    return result.scalar_one_or_none()


async def get_all_health_configs(
    session: AsyncSession,
) -> list[HealthConfig]:
    """全ヘルスチェック設定を取得する。"""
    result = await session.execute(select(HealthConfig))
    return list(result.scalars().all())


async def upsert_health_config(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
) -> HealthConfig:
    """ヘルスチェック設定を作成または更新する。"""
    existing = await get_health_config(session, guild_id)
    if existing:
        existing.channel_id = channel_id
        await session.commit()
        return existing
    config = HealthConfig(guild_id=guild_id, channel_id=channel_id)
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


async def delete_health_config(session: AsyncSession, guild_id: str) -> bool:
    """ヘルスチェック設定を削除する。"""
    existing = await get_health_config(session, guild_id)
    if existing:
        await session.delete(existing)
        await session.commit()
        return True
    return False


# =============================================================================
# EventLogConfig (イベントログ) 操作
# =============================================================================


async def get_event_log_configs(
    session: AsyncSession, guild_id: str | None = None
) -> list[EventLogConfig]:
    """EventLog 設定を取得する。guild_id 指定で絞り込み。"""
    stmt = select(EventLogConfig).order_by(EventLogConfig.id)
    if guild_id is not None:
        stmt = stmt.where(EventLogConfig.guild_id == guild_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_enabled_event_log_configs(
    session: AsyncSession, guild_id: str
) -> list[EventLogConfig]:
    """指定ギルドの有効な EventLog 設定を取得する。"""
    stmt = (
        select(EventLogConfig)
        .where(
            EventLogConfig.guild_id == guild_id,
            EventLogConfig.enabled.is_(True),
        )
        .order_by(EventLogConfig.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
