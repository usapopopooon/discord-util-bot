"""DiscordRole, DiscordGuild, DiscordChannel の DB 操作。"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import DiscordChannel, DiscordGuild, DiscordRole

__all__ = [
    "delete_discord_channel",
    "delete_discord_channels_by_guild",
    "delete_discord_guild",
    "delete_discord_role",
    "delete_discord_roles_by_guild",
    "get_all_discord_guilds",
    "get_discord_channels_by_guild",
    "get_discord_roles_by_guild",
    "upsert_discord_channel",
    "upsert_discord_guild",
    "upsert_discord_role",
]


# =============================================================================
# DiscordRole (Discord ロールキャッシュ) 操作
# =============================================================================


async def upsert_discord_role(
    session: AsyncSession,
    guild_id: str,
    role_id: str,
    role_name: str,
    color: int = 0,
    position: int = 0,
) -> DiscordRole:
    """Discord ロール情報を作成または更新する。

    同じ guild_id + role_id の組み合わせが既に存在する場合は上書きする。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        role_id: Discord ロールの ID
        role_name: ロール名
        color: ロールの色 (16進数の整数値)
        position: ロールの表示順序

    Returns:
        作成または更新された DiscordRole オブジェクト
    """
    result = await session.execute(
        select(DiscordRole).where(
            DiscordRole.guild_id == guild_id,
            DiscordRole.role_id == role_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.role_name = role_name
        existing.color = color
        existing.position = position
        await session.commit()
        return existing

    role = DiscordRole(
        guild_id=guild_id,
        role_id=role_id,
        role_name=role_name,
        color=color,
        position=position,
    )
    session.add(role)
    await session.commit()
    await session.refresh(role)
    return role


async def delete_discord_role(
    session: AsyncSession,
    guild_id: str,
    role_id: str,
) -> bool:
    """Discord ロール情報を削除する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        role_id: Discord ロールの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(
        select(DiscordRole).where(
            DiscordRole.guild_id == guild_id,
            DiscordRole.role_id == role_id,
        )
    )
    role = result.scalar_one_or_none()
    if role:
        await session.delete(role)
        await session.commit()
        return True
    return False


async def delete_discord_roles_by_guild(
    session: AsyncSession,
    guild_id: str,
) -> int:
    """サーバーの全ロール情報を削除する。

    Bot がサーバーから退出したときに呼ばれる。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除したレコード数
    """
    result = await session.execute(
        delete(DiscordRole).where(DiscordRole.guild_id == guild_id)
    )
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


async def get_discord_roles_by_guild(
    session: AsyncSession,
    guild_id: str,
) -> list[DiscordRole]:
    """サーバーの全ロール情報を取得する。

    position の降順 (上位ロールから) でソートして返す。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        DiscordRole のリスト (position 降順)
    """
    result = await session.execute(
        select(DiscordRole)
        .where(DiscordRole.guild_id == guild_id)
        .order_by(DiscordRole.position.desc())
    )
    return list(result.scalars().all())


# =============================================================================
# DiscordGuild (Discord ギルドキャッシュ) 操作
# =============================================================================


async def upsert_discord_guild(
    session: AsyncSession,
    guild_id: str,
    guild_name: str,
    icon_hash: str | None = None,
    member_count: int = 0,
) -> DiscordGuild:
    """Discord ギルド情報を作成または更新する。

    同じ guild_id が既に存在する場合は上書きする。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        guild_name: サーバー名
        icon_hash: サーバーアイコンのハッシュ
        member_count: メンバー数 (概算)

    Returns:
        作成または更新された DiscordGuild オブジェクト
    """
    result = await session.execute(
        select(DiscordGuild).where(DiscordGuild.guild_id == guild_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.guild_name = guild_name
        existing.icon_hash = icon_hash
        existing.member_count = member_count
        await session.commit()
        return existing

    guild = DiscordGuild(
        guild_id=guild_id,
        guild_name=guild_name,
        icon_hash=icon_hash,
        member_count=member_count,
    )
    session.add(guild)
    await session.commit()
    await session.refresh(guild)
    return guild


async def delete_discord_guild(
    session: AsyncSession,
    guild_id: str,
) -> bool:
    """Discord ギルド情報を削除する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(
        select(DiscordGuild).where(DiscordGuild.guild_id == guild_id)
    )
    guild = result.scalar_one_or_none()
    if guild:
        await session.delete(guild)
        await session.commit()
        return True
    return False


async def get_all_discord_guilds(
    session: AsyncSession,
) -> list[DiscordGuild]:
    """全てのキャッシュ済みギルド情報を取得する。

    ギルド名でソートして返す。

    Args:
        session: DB セッション

    Returns:
        DiscordGuild のリスト (ギルド名順)
    """
    result = await session.execute(
        select(DiscordGuild).order_by(DiscordGuild.guild_name)
    )
    return list(result.scalars().all())


# =============================================================================
# DiscordChannel (Discord チャンネルキャッシュ) 操作
# =============================================================================


async def upsert_discord_channel(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
    channel_name: str,
    channel_type: int = 0,
    position: int = 0,
    category_id: str | None = None,
) -> DiscordChannel:
    """Discord チャンネル情報を作成または更新する。

    同じ guild_id + channel_id の組み合わせが既に存在する場合は上書きする。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        channel_id: Discord チャンネルの ID
        channel_name: チャンネル名
        channel_type: チャンネルタイプ (0=text, 5=news, etc.)
        position: チャンネルの表示順序
        category_id: 親カテゴリの ID

    Returns:
        作成または更新された DiscordChannel オブジェクト
    """
    result = await session.execute(
        select(DiscordChannel).where(
            DiscordChannel.guild_id == guild_id,
            DiscordChannel.channel_id == channel_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.channel_name = channel_name
        existing.channel_type = channel_type
        existing.position = position
        existing.category_id = category_id
        await session.commit()
        return existing

    channel = DiscordChannel(
        guild_id=guild_id,
        channel_id=channel_id,
        channel_name=channel_name,
        channel_type=channel_type,
        position=position,
        category_id=category_id,
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel


async def delete_discord_channel(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
) -> bool:
    """Discord チャンネル情報を削除する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        channel_id: Discord チャンネルの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(
        select(DiscordChannel).where(
            DiscordChannel.guild_id == guild_id,
            DiscordChannel.channel_id == channel_id,
        )
    )
    channel = result.scalar_one_or_none()
    if channel:
        await session.delete(channel)
        await session.commit()
        return True
    return False


async def delete_discord_channels_by_guild(
    session: AsyncSession,
    guild_id: str,
) -> int:
    """サーバーの全チャンネル情報を削除する。

    Bot がサーバーから退出したときに呼ばれる。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除したレコード数
    """
    result = await session.execute(
        delete(DiscordChannel).where(DiscordChannel.guild_id == guild_id)
    )
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


async def get_discord_channels_by_guild(
    session: AsyncSession,
    guild_id: str,
) -> list[DiscordChannel]:
    """サーバーの全チャンネル情報を取得する。

    position 順でソートして返す。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        DiscordChannel のリスト (position 順)
    """
    result = await session.execute(
        select(DiscordChannel)
        .where(DiscordChannel.guild_id == guild_id)
        .order_by(DiscordChannel.position)
    )
    return list(result.scalars().all())
