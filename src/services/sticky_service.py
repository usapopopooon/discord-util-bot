"""StickyMessage の DB 操作。"""

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy import or_ as db_or
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import StickyMessage

__all__ = [
    "claim_sticky_repost",
    "create_sticky_message",
    "delete_sticky_message",
    "delete_sticky_messages_by_guild",
    "get_all_sticky_messages",
    "get_sticky_message",
    "update_sticky_message_id",
]


# =============================================================================
# StickyMessage (sticky メッセージ) 操作
# =============================================================================


async def get_sticky_message(
    session: AsyncSession,
    channel_id: str,
) -> StickyMessage | None:
    """チャンネルの sticky メッセージ設定を取得する。

    Args:
        session: DB セッション
        channel_id: Discord チャンネルの ID

    Returns:
        見つかった StickyMessage、なければ None
    """
    result = await session.execute(
        select(StickyMessage).where(StickyMessage.channel_id == channel_id)
    )
    return result.scalar_one_or_none()


async def create_sticky_message(
    session: AsyncSession,
    channel_id: str,
    guild_id: str,
    title: str,
    description: str,
    color: int | None = None,
    cooldown_seconds: int = 5,
    message_type: str = "embed",
) -> StickyMessage:
    """sticky メッセージを作成する。

    既に同じチャンネルに設定がある場合は上書きする。

    Args:
        session: DB セッション
        channel_id: Discord チャンネルの ID
        guild_id: Discord サーバーの ID
        title: embed のタイトル (text の場合は空文字)
        description: embed の説明文 / text の本文
        color: embed の色 (16進数の整数値)
        cooldown_seconds: 再投稿までの最小間隔 (秒)
        message_type: メッセージの種類 ("embed" または "text")

    Returns:
        作成または更新された StickyMessage オブジェクト
    """
    existing = await get_sticky_message(session, channel_id)

    if existing:
        existing.guild_id = guild_id
        existing.title = title
        existing.description = description
        existing.color = color
        existing.cooldown_seconds = cooldown_seconds
        existing.message_type = message_type
        existing.message_id = None  # 新規設定なのでリセット
        existing.last_posted_at = None
        await session.commit()
        return existing

    sticky = StickyMessage(
        channel_id=channel_id,
        guild_id=guild_id,
        title=title,
        description=description,
        color=color,
        cooldown_seconds=cooldown_seconds,
        message_type=message_type,
    )
    session.add(sticky)
    await session.commit()
    await session.refresh(sticky)
    return sticky


async def update_sticky_message_id(
    session: AsyncSession,
    channel_id: str,
    message_id: str | None,
    last_posted_at: datetime | None = None,
) -> bool:
    """sticky メッセージの message_id と last_posted_at を更新する。

    新しい sticky メッセージを投稿した後に呼び出す。

    Args:
        session: DB セッション
        channel_id: Discord チャンネルの ID
        message_id: 投稿したメッセージの ID (削除する場合は None)
        last_posted_at: 投稿日時 (None なら更新しない)

    Returns:
        更新できたら True、見つからなければ False
    """
    sticky = await get_sticky_message(session, channel_id)

    if sticky:
        sticky.message_id = message_id
        if last_posted_at is not None:
            sticky.last_posted_at = last_posted_at
        await session.commit()
        return True

    return False


async def claim_sticky_repost(
    session: AsyncSession,
    channel_id: str,
    now: datetime,
    cooldown_seconds: int,
) -> bool:
    """sticky 再投稿の権利をアトミックに取得する。

    複数インスタンス実行時、最初に claim したインスタンスだけが True を返す。
    last_posted_at が cooldown 以内に更新済みの場合は False を返す。

    Args:
        session: DB セッション
        channel_id: Discord チャンネルの ID
        now: 現在時刻 (UTC)
        cooldown_seconds: 再投稿の最小間隔 (秒)

    Returns:
        claim 成功なら True、既に別インスタンスが処理済みなら False
    """
    from datetime import timedelta

    threshold = now - timedelta(seconds=cooldown_seconds)
    result = await session.execute(
        update(StickyMessage)
        .where(
            StickyMessage.channel_id == channel_id,
            db_or(
                StickyMessage.last_posted_at.is_(None),
                StickyMessage.last_posted_at <= threshold,
            ),
        )
        .values(last_posted_at=now)
    )
    await session.commit()
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def delete_sticky_message(
    session: AsyncSession,
    channel_id: str,
) -> bool:
    """sticky メッセージ設定を削除する。

    Args:
        session: DB セッション
        channel_id: Discord チャンネルの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    sticky = await get_sticky_message(session, channel_id)

    if sticky:
        await session.delete(sticky)
        await session.commit()
        return True

    return False


async def delete_sticky_messages_by_guild(session: AsyncSession, guild_id: str) -> int:
    """指定ギルドの全 sticky メッセージを削除する。

    Bot がギルドから退出したときにクリーンアップとして使用。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除した sticky メッセージの数
    """
    result = await session.execute(
        delete(StickyMessage).where(StickyMessage.guild_id == guild_id)
    )
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


async def get_all_sticky_messages(
    session: AsyncSession,
) -> list[StickyMessage]:
    """全ての sticky メッセージ設定を取得する。

    Bot 起動時に既存の sticky メッセージを復元するために使用する。

    Args:
        session: DB セッション

    Returns:
        全ての StickyMessage のリスト
    """
    result = await session.execute(select(StickyMessage))
    return list(result.scalars().all())
