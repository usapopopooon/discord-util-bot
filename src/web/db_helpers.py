"""Database helper functions for web routes."""

import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.security as _security
from src.database.engine import async_session
from src.database.models import (
    AdminUser,
    DiscordChannel,
    DiscordGuild,
    DiscordRole,
)

logger = logging.getLogger(__name__)

_VALID_ACTIVITY_TYPES = {"playing", "listening", "watching", "competing"}


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Database session dependency."""
    async with async_session() as session:
        yield session


async def get_or_create_admin(db: AsyncSession) -> AdminUser | None:
    """Get admin user, create from env vars if not exists."""
    result = await db.execute(select(AdminUser).limit(1))
    admin = result.scalar_one_or_none()

    if admin is None and _security.INIT_ADMIN_PASSWORD:
        admin = AdminUser(
            email=_security.INIT_ADMIN_EMAIL,
            password_hash=await _security.hash_password_async(
                _security.INIT_ADMIN_PASSWORD
            ),
            email_verified=True,
            password_changed_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

    return admin


async def _get_discord_roles_by_guild(
    db: AsyncSession,
) -> dict[str, list[tuple[str, str, int]]]:
    """DBにキャッシュされているDiscordロール情報を取得する."""
    result = await db.execute(
        select(DiscordRole).order_by(DiscordRole.guild_id, DiscordRole.position.desc())
    )

    guild_roles: dict[str, list[tuple[str, str, int]]] = {}
    for role in result.scalars():
        if role.guild_id not in guild_roles:
            guild_roles[role.guild_id] = []
        guild_roles[role.guild_id].append((role.role_id, role.role_name, role.color))

    return guild_roles


async def _get_discord_guilds_and_channels(
    db: AsyncSession,
) -> tuple[dict[str, str], dict[str, list[tuple[str, str]]]]:
    """キャッシュされたギルドとチャンネル情報を取得する。"""
    guilds_result = await db.execute(
        select(DiscordGuild).order_by(DiscordGuild.guild_name)
    )
    guilds_map: dict[str, str] = {
        g.guild_id: g.guild_name for g in guilds_result.scalars()
    }

    channels_result = await db.execute(
        select(DiscordChannel)
        .where(DiscordChannel.channel_type != 4)
        .order_by(DiscordChannel.guild_id, DiscordChannel.position)
    )

    channels_map: dict[str, list[tuple[str, str]]] = {}
    for channel in channels_result.scalars():
        if channel.guild_id not in channels_map:
            channels_map[channel.guild_id] = []
        channels_map[channel.guild_id].append(
            (channel.channel_id, channel.channel_name)
        )

    return guilds_map, channels_map


async def _get_discord_categories(
    db: AsyncSession,
) -> dict[str, list[tuple[str, str]]]:
    """キャッシュされた Discord カテゴリチャンネル情報を取得する。"""
    result = await db.execute(
        select(DiscordChannel)
        .where(DiscordChannel.channel_type == 4)
        .order_by(DiscordChannel.guild_id, DiscordChannel.position)
    )

    categories_map: dict[str, list[tuple[str, str]]] = {}
    for cat in result.scalars():
        if cat.guild_id not in categories_map:
            categories_map[cat.guild_id] = []
        categories_map[cat.guild_id].append((cat.channel_id, cat.channel_name))

    return categories_map
