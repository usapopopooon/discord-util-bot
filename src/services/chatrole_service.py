"""ChatRole の DB 操作。"""

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import ChatRoleConfig, ChatRoleProgress

__all__ = [
    "create_chat_role_config",
    "delete_chat_role_config",
    "get_chat_role_configs",
    "get_enabled_chat_role_channel_ids",
    "get_enabled_chat_role_configs_for_channel",
    "get_expired_chat_role_progress",
    "increment_chat_role_progress",
    "mark_chat_role_progress_expired",
    "mark_chat_role_progress_granted",
    "toggle_chat_role_config",
]


# =============================================================================
# ChatRoleConfig (設定) 操作
# =============================================================================


async def create_chat_role_config(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
    role_id: str,
    threshold: int,
    duration_hours: int | None,
) -> ChatRoleConfig:
    """ChatRole 設定を作成する。"""
    config = ChatRoleConfig(
        guild_id=guild_id,
        channel_id=channel_id,
        role_id=role_id,
        threshold=threshold,
        duration_hours=duration_hours,
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


async def get_chat_role_configs(
    session: AsyncSession, guild_id: str | None = None
) -> list[ChatRoleConfig]:
    """ChatRole 設定を取得する。guild_id 指定で絞り込み。"""
    stmt = select(ChatRoleConfig).order_by(ChatRoleConfig.id)
    if guild_id is not None:
        stmt = stmt.where(ChatRoleConfig.guild_id == guild_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_enabled_chat_role_configs_for_channel(
    session: AsyncSession, guild_id: str, channel_id: str
) -> list[ChatRoleConfig]:
    """指定ギルド・チャンネルの有効な ChatRole 設定を取得する。"""
    stmt = (
        select(ChatRoleConfig)
        .where(
            ChatRoleConfig.guild_id == guild_id,
            ChatRoleConfig.channel_id == channel_id,
            ChatRoleConfig.enabled.is_(True),
        )
        .order_by(ChatRoleConfig.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_enabled_chat_role_channel_ids(session: AsyncSession) -> set[str]:
    """有効な ChatRole 設定が存在するチャンネル ID 集合を取得する。

    on_message ホットパスで「この channel は ChatRole 対象か」を
    DB なしで判定するためのキャッシュ初期化用。
    """
    stmt = (
        select(ChatRoleConfig.channel_id)
        .where(ChatRoleConfig.enabled.is_(True))
        .distinct()
    )
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


async def delete_chat_role_config(session: AsyncSession, config_id: int) -> bool:
    """ChatRole 設定を削除する (関連 Progress も CASCADE 削除)。"""
    stmt = delete(ChatRoleConfig).where(ChatRoleConfig.id == config_id)
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount) > 0  # type: ignore[attr-defined]


async def toggle_chat_role_config(
    session: AsyncSession, config_id: int
) -> ChatRoleConfig | None:
    """ChatRole 設定の有効/無効を切り替える。"""
    stmt = select(ChatRoleConfig).where(ChatRoleConfig.id == config_id)
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()
    if config is None:
        return None
    config.enabled = not config.enabled
    await session.commit()
    await session.refresh(config)
    return config


# =============================================================================
# ChatRoleProgress (ユーザー進捗) 操作
# =============================================================================


async def increment_chat_role_progress(
    session: AsyncSession, config_id: int, user_id: str
) -> ChatRoleProgress | None:
    """投稿カウントを 1 増やす (granted=False のレコードのみ)。

    Postgres ON CONFLICT を使い 1 ステートメントでアトミックに upsert する:
      - 新規レコード → INSERT (count=1, granted=False)
      - granted=False の既存レコード → count を +1
      - granted=True の既存レコード → 何もせず None を返す

    granted=True のレコードを更新しないため、付与済みユーザーの投稿で
    DB 書き込みが発生しない。並列メッセージ処理でも UNIQUE 違反は起きない。
    """
    stmt = (
        pg_insert(ChatRoleProgress)
        .values(config_id=config_id, user_id=user_id, count=1, granted=False)
        .on_conflict_do_update(
            index_elements=["config_id", "user_id"],
            set_={"count": ChatRoleProgress.count + 1},
            where=ChatRoleProgress.granted.is_(False),
        )
        .returning(ChatRoleProgress)
    )
    result = await session.execute(stmt)
    progress = result.scalar()
    await session.commit()
    return progress


async def mark_chat_role_progress_granted(
    session: AsyncSession,
    progress_id: int,
    granted_at: datetime,
    expires_at: datetime | None,
) -> bool:
    """Progress を granted=True に更新する。

    アトミックに `granted=False → True` を実行し、別インスタンスが先に
    付与済みなら False を返す (UPDATE WHERE granted=False を利用)。
    """
    stmt = (
        update(ChatRoleProgress)
        .where(
            ChatRoleProgress.id == progress_id,
            ChatRoleProgress.granted.is_(False),
        )
        .values(granted=True, granted_at=granted_at, expires_at=expires_at)
    )
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount) > 0  # type: ignore[attr-defined]


async def get_expired_chat_role_progress(
    session: AsyncSession, now: datetime
) -> list[tuple[ChatRoleProgress, ChatRoleConfig]]:
    """期限切れの Progress と紐づく Config を取得する。"""
    stmt = (
        select(ChatRoleProgress, ChatRoleConfig)
        .join(ChatRoleConfig, ChatRoleProgress.config_id == ChatRoleConfig.id)
        .where(
            ChatRoleProgress.granted.is_(True),
            ChatRoleProgress.expires_at.is_not(None),
            ChatRoleProgress.expires_at <= now,
        )
        .order_by(ChatRoleProgress.expires_at)
    )
    result = await session.execute(stmt)
    return [(p, c) for p, c in result.all()]


async def mark_chat_role_progress_expired(
    session: AsyncSession, progress_id: int
) -> bool:
    """期限切れ処理: granted を False に戻し expires_at をクリアする。

    アトミックに `granted=True → False` を実行し、別インスタンスが先に
    処理済みなら False を返す。次回 threshold に達したら再付与される。
    """
    stmt = (
        update(ChatRoleProgress)
        .where(
            ChatRoleProgress.id == progress_id,
            ChatRoleProgress.granted.is_(True),
        )
        .values(granted=False, granted_at=None, expires_at=None, count=0)
    )
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount) > 0  # type: ignore[attr-defined]
