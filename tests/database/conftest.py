"""Database test fixtures with factory helpers."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from faker import Faker
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.constants import DEFAULT_TEST_DATABASE_URL
from src.database.models import (
    Base,
    BumpConfig,
    BumpReminder,
    Lobby,
    StickyMessage,
    VoiceSession,
    VoiceSessionMember,
)
from src.services.db_service import (
    add_voice_session_member,
    create_lobby,
    create_sticky_message,
    create_voice_session,
    upsert_bump_config,
    upsert_bump_reminder,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

fake = Faker()

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    DEFAULT_TEST_DATABASE_URL,
)

# --- Speed optimizations ---
# NullPool: コネクションプールなし (function スコープの event loop でも安全)
_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

# スキーマ作成フラグ: DROP/CREATE は初回のみ、以降は TRUNCATE
_schema_created = False

# 全テーブル TRUNCATE 文を事前構築
_TRUNCATE_SQL = text(
    "TRUNCATE TABLE "
    + ",".join(Base.metadata.tables.keys())
    + " RESTART IDENTITY CASCADE"
)


def snowflake() -> str:
    """Discord snowflake 風の ID を生成する。"""
    return str(fake.random_number(digits=18, fix_len=True))


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """PostgreSQL テスト DB のセッションを提供する。"""
    global _schema_created
    if _schema_created:
        # 2回目以降: TRUNCATE (DROP/CREATE DDL より大幅に高速)
        async with _engine.begin() as conn:
            await conn.execute(_TRUNCATE_SQL)
    else:
        # 初回: スキーマ作成
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        _schema_created = True

    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def lobby(db_session: AsyncSession) -> Lobby:
    """テスト用ロビーを1つ作成して返す。"""
    return await create_lobby(
        db_session,
        guild_id=snowflake(),
        lobby_channel_id=snowflake(),
    )


@pytest.fixture
async def voice_session(db_session: AsyncSession, lobby: Lobby) -> VoiceSession:
    """テスト用 VoiceSession を1つ作成して返す。"""
    return await create_voice_session(
        db_session,
        lobby_id=lobby.id,
        channel_id=snowflake(),
        owner_id=snowflake(),
        name=fake.word(),
    )


@pytest.fixture
async def voice_session_member(
    db_session: AsyncSession, voice_session: VoiceSession
) -> VoiceSessionMember:
    """テスト用 VoiceSessionMember を1つ作成して返す。"""
    return await add_voice_session_member(
        db_session,
        voice_session_id=voice_session.id,
        user_id=snowflake(),
    )


@pytest.fixture
async def bump_reminder(db_session: AsyncSession) -> BumpReminder:
    """テスト用 BumpReminder を1つ作成して返す。"""
    return await upsert_bump_reminder(
        db_session,
        guild_id=snowflake(),
        channel_id=snowflake(),
        service_name=fake.random_element(elements=["DISBOARD", "ディス速報"]),
        remind_at=datetime.now(UTC) + timedelta(hours=2),
    )


@pytest.fixture
async def bump_config(db_session: AsyncSession) -> BumpConfig:
    """テスト用 BumpConfig を1つ作成して返す。"""
    return await upsert_bump_config(
        db_session,
        guild_id=snowflake(),
        channel_id=snowflake(),
    )


@pytest.fixture
async def sticky_message(db_session: AsyncSession) -> StickyMessage:
    """テスト用 StickyMessage を1つ作成して返す。"""
    return await create_sticky_message(
        db_session,
        channel_id=snowflake(),
        guild_id=snowflake(),
        title=fake.sentence(nb_words=3),
        description=fake.paragraph(),
        color=fake.random_int(min=0, max=0xFFFFFF),
        cooldown_seconds=fake.random_int(min=1, max=60),
        message_type=fake.random_element(elements=["embed", "text"]),
    )
