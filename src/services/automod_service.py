"""AutoMod, AutoModIntroPost, BanLog の DB 操作。"""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    AutoModBanList,
    AutoModConfig,
    AutoModIntroPost,
    AutoModLog,
    AutoModRule,
    BanLog,
)

__all__ = [
    "add_to_ban_list",
    "claim_automod_log",
    "claim_ban_log",
    "create_automod_log",
    "create_automod_rule",
    "create_ban_log",
    "delete_automod_rule",
    "delete_intro_posts_by_guild",
    "get_all_automod_configs",
    "get_all_automod_logs",
    "get_all_automod_rules",
    "get_automod_config",
    "get_automod_logs_by_guild",
    "get_automod_rule",
    "get_automod_rules_by_guild",
    "get_ban_list_by_guild",
    "get_ban_logs",
    "get_enabled_automod_rules_by_guild",
    "has_intro_post",
    "is_user_in_ban_list",
    "record_intro_post",
    "remove_from_ban_list",
    "toggle_automod_rule",
    "update_automod_rule",
    "upsert_automod_config",
]


# =============================================================================
# AutoMod (自動モデレーション) 操作
# =============================================================================


async def get_all_automod_rules(
    session: AsyncSession,
) -> list[AutoModRule]:
    """全 automod ルールを取得する。"""
    result = await session.execute(
        select(AutoModRule).order_by(AutoModRule.guild_id, AutoModRule.created_at)
    )
    return list(result.scalars().all())


async def get_automod_rules_by_guild(
    session: AsyncSession, guild_id: str
) -> list[AutoModRule]:
    """サーバーの全 automod ルールを取得する。"""
    result = await session.execute(
        select(AutoModRule).where(AutoModRule.guild_id == guild_id)
    )
    return list(result.scalars().all())


async def get_enabled_automod_rules_by_guild(
    session: AsyncSession, guild_id: str
) -> list[AutoModRule]:
    """サーバーの有効な automod ルールを取得する。"""
    result = await session.execute(
        select(AutoModRule).where(
            AutoModRule.guild_id == guild_id,
            AutoModRule.is_enabled.is_(True),
        )
    )
    return list(result.scalars().all())


async def get_automod_rule(session: AsyncSession, rule_id: int) -> AutoModRule | None:
    """ルール ID から automod ルールを取得する。"""
    result = await session.execute(select(AutoModRule).where(AutoModRule.id == rule_id))
    return result.scalar_one_or_none()


async def create_automod_rule(
    session: AsyncSession,
    guild_id: str,
    rule_type: str,
    action: str = "ban",
    pattern: str | None = None,
    use_wildcard: bool = False,
    threshold_seconds: int | None = None,
    timeout_duration_seconds: int | None = None,
) -> AutoModRule:
    """新しい automod ルールを作成する。"""
    rule = AutoModRule(
        guild_id=guild_id,
        rule_type=rule_type,
        action=action,
        pattern=pattern,
        use_wildcard=use_wildcard,
        threshold_seconds=threshold_seconds,
        timeout_duration_seconds=timeout_duration_seconds,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


async def delete_automod_rule(session: AsyncSession, rule_id: int) -> bool:
    """automod ルールを削除する。"""
    rule = await get_automod_rule(session, rule_id)
    if rule:
        await session.delete(rule)
        await session.commit()
        return True
    return False


async def toggle_automod_rule(session: AsyncSession, rule_id: int) -> bool | None:
    """automod ルールの有効/無効を切り替える。新しい状態を返す。"""
    rule = await get_automod_rule(session, rule_id)
    if rule:
        rule.is_enabled = not rule.is_enabled
        await session.commit()
        return rule.is_enabled
    return None


async def update_automod_rule(
    session: AsyncSession,
    rule: AutoModRule,
    *,
    action: str | None = None,
    pattern: str | None = None,
    use_wildcard: bool | None = None,
    threshold_seconds: int | None = None,
    timeout_duration_seconds: int | None = None,
) -> AutoModRule:
    """automod ルールを更新する。None のフィールドは変更しない。"""
    if action is not None:
        rule.action = action
    if pattern is not None:
        rule.pattern = pattern
    if use_wildcard is not None:
        rule.use_wildcard = use_wildcard
    if threshold_seconds is not None:
        rule.threshold_seconds = threshold_seconds
    if timeout_duration_seconds is not None:
        rule.timeout_duration_seconds = timeout_duration_seconds
    await session.commit()
    return rule


async def create_automod_log(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    username: str,
    rule_id: int,
    action_taken: str,
    reason: str,
) -> AutoModLog:
    """automod 実行ログを作成する。"""
    log = AutoModLog(
        guild_id=guild_id,
        user_id=user_id,
        username=username,
        rule_id=rule_id,
        action_taken=action_taken,
        reason=reason,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def claim_automod_log(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    username: str,
    rule_id: int,
    action_taken: str,
    reason: str,
) -> AutoModLog | None:
    """automod 実行ログをアトミックに作成する。

    同一 (guild_id, user_id, rule_id) のログが直近 10 秒以内に存在する場合は
    重複と見なし None を返す (別インスタンスが先に処理済み)。
    ルール行を FOR UPDATE でロックし並行書き込みを直列化する。
    """
    from datetime import timedelta

    # ルール行をロックして並行書き込みを直列化
    rule_result = await session.execute(
        select(AutoModRule).where(AutoModRule.id == rule_id).with_for_update()
    )
    if not rule_result.scalar_one_or_none():
        return None  # ルールが削除済み

    threshold = datetime.now(UTC) - timedelta(seconds=10)
    dup = await session.execute(
        select(AutoModLog.id).where(
            AutoModLog.guild_id == guild_id,
            AutoModLog.user_id == user_id,
            AutoModLog.rule_id == rule_id,
            AutoModLog.created_at >= threshold,
        )
    )
    if dup.scalar_one_or_none() is not None:
        return None  # 別インスタンスが先に処理済み

    log = AutoModLog(
        guild_id=guild_id,
        user_id=user_id,
        username=username,
        rule_id=rule_id,
        action_taken=action_taken,
        reason=reason,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def get_automod_logs_by_guild(
    session: AsyncSession, guild_id: str, limit: int = 50
) -> list[AutoModLog]:
    """サーバーの automod ログを取得する (新しい順)。"""
    result = await session.execute(
        select(AutoModLog)
        .where(AutoModLog.guild_id == guild_id)
        .order_by(AutoModLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_all_automod_logs(
    session: AsyncSession, limit: int = 100
) -> list[AutoModLog]:
    """全 automod ログを取得する (新しい順)。"""
    result = await session.execute(
        select(AutoModLog).order_by(AutoModLog.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_automod_config(
    session: AsyncSession, guild_id: str
) -> AutoModConfig | None:
    """ギルドの automod 設定を取得する。"""
    result = await session.execute(
        select(AutoModConfig).where(AutoModConfig.guild_id == guild_id)
    )
    return result.scalar_one_or_none()


async def upsert_automod_config(
    session: AsyncSession,
    guild_id: str,
    log_channel_id: str | None,
) -> AutoModConfig:
    """automod 設定を作成または更新する。"""
    existing = await get_automod_config(session, guild_id)

    if existing:
        existing.log_channel_id = log_channel_id
        await session.commit()
        return existing

    config = AutoModConfig(guild_id=guild_id, log_channel_id=log_channel_id)
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


async def get_all_automod_configs(session: AsyncSession) -> list[AutoModConfig]:
    """全 automod 設定を取得する。"""
    result = await session.execute(select(AutoModConfig))
    return list(result.scalars().all())


# =============================================================================
# AutoModIntroPost (投稿追跡) 操作
# =============================================================================


async def record_intro_post(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    channel_id: str,
) -> None:
    """指定チャンネルへの投稿を記録する (重複は無視)。"""
    post = AutoModIntroPost(
        guild_id=guild_id,
        user_id=user_id,
        channel_id=channel_id,
    )
    session.add(post)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()


async def has_intro_post(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    channel_id: str,
) -> bool:
    """指定チャンネルへの投稿があるか確認する。"""
    result = await session.execute(
        select(AutoModIntroPost.id)
        .where(
            AutoModIntroPost.guild_id == guild_id,
            AutoModIntroPost.user_id == user_id,
            AutoModIntroPost.channel_id == channel_id,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def delete_intro_posts_by_guild(
    session: AsyncSession,
    guild_id: str,
) -> int:
    """ギルドの全投稿追跡レコードを削除する。"""
    result = await session.execute(
        delete(AutoModIntroPost).where(AutoModIntroPost.guild_id == guild_id)
    )
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


# =============================================================================
# BanLog (BAN ログ) 操作
# =============================================================================


async def create_ban_log(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    username: str,
    reason: str | None = None,
    is_automod: bool = False,
) -> BanLog:
    """BAN ログを作成する。"""
    log = BanLog(
        guild_id=guild_id,
        user_id=user_id,
        username=username,
        reason=reason,
        is_automod=is_automod,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def claim_ban_log(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    username: str,
    reason: str | None = None,
    is_automod: bool = False,
) -> BanLog | None:
    """BAN ログをアトミックに作成する。

    同一 (guild_id, user_id) のログが直近 10 秒以内に存在する場合は
    重複と見なし None を返す (別インスタンスが先に処理済み)。
    """
    from datetime import timedelta

    threshold = datetime.now(UTC) - timedelta(seconds=10)
    dup = await session.execute(
        select(BanLog.id).where(
            BanLog.guild_id == guild_id,
            BanLog.user_id == user_id,
            BanLog.created_at >= threshold,
        )
    )
    if dup.scalar_one_or_none() is not None:
        return None  # 別インスタンスが先に処理済み

    log = BanLog(
        guild_id=guild_id,
        user_id=user_id,
        username=username,
        reason=reason,
        is_automod=is_automod,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def get_ban_logs(session: AsyncSession, limit: int = 100) -> list[BanLog]:
    """全 BAN ログを取得する (新しい順)。"""
    result = await session.execute(
        select(BanLog).order_by(BanLog.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


# =============================================================================
# AutoModBanList (ユーザーID BANリスト) 操作
# =============================================================================


async def get_ban_list_by_guild(
    session: AsyncSession, guild_id: str
) -> list[AutoModBanList]:
    """ギルドの BANリストを取得する (新しい順)。"""
    result = await session.execute(
        select(AutoModBanList)
        .where(AutoModBanList.guild_id == guild_id)
        .order_by(AutoModBanList.created_at.desc())
    )
    return list(result.scalars().all())


async def add_to_ban_list(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    reason: str | None = None,
) -> AutoModBanList | None:
    """BANリストにユーザーIDを追加する。重複時は None を返す。"""
    entry = AutoModBanList(
        guild_id=guild_id,
        user_id=user_id,
        reason=reason,
    )
    session.add(entry)
    try:
        await session.commit()
        await session.refresh(entry)
        return entry
    except IntegrityError:
        await session.rollback()
        return None


async def remove_from_ban_list(session: AsyncSession, entry_id: int) -> bool:
    """BANリストからエントリを削除する。"""
    result = await session.execute(
        select(AutoModBanList).where(AutoModBanList.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if entry:
        await session.delete(entry)
        await session.commit()
        return True
    return False


async def is_user_in_ban_list(
    session: AsyncSession, guild_id: str, user_id: str
) -> str | None:
    """ユーザーが BANリストに存在するか確認する。

    存在する場合は reason を返す (reason が None なら空文字列)。
    存在しない場合は None を返す。
    """
    result = await session.execute(
        select(AutoModBanList.reason)
        .where(
            AutoModBanList.guild_id == guild_id,
            AutoModBanList.user_id == user_id,
        )
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        # scalar_one_or_none returns None when no row found
        # But also returns None if reason column is None
        # So we need to check if the row exists
        exists = await session.execute(
            select(AutoModBanList.id)
            .where(
                AutoModBanList.guild_id == guild_id,
                AutoModBanList.user_id == user_id,
            )
            .limit(1)
        )
        if exists.scalar_one_or_none() is not None:
            return ""
        return None
    return row
