"""Shared pytest fixtures."""

import os

# Set DISCORD_TOKEN before any src imports to avoid validation error
os.environ.setdefault("DISCORD_TOKEN", "test-token-for-testing")

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src.constants import DEFAULT_TEST_DATABASE_URL_SYNC
from src.database.models import Base, Lobby

TEST_DATABASE_URL_SYNC = os.environ.get(
    "TEST_DATABASE_URL_SYNC",
    DEFAULT_TEST_DATABASE_URL_SYNC,
)

# --- Speed optimizations ---
_sync_engine = create_engine(TEST_DATABASE_URL_SYNC)

# スキーマ作成フラグ: DROP/CREATE は初回のみ、以降は TRUNCATE
_schema_created = False

# 全テーブル TRUNCATE 文を事前構築
_TRUNCATE_SQL = text(
    "TRUNCATE TABLE "
    + ",".join(Base.metadata.tables.keys())
    + " RESTART IDENTITY CASCADE"
)


@pytest.fixture
def db_session() -> Session:
    """Create a PostgreSQL session for testing."""
    global _schema_created
    if _schema_created:
        with _sync_engine.begin() as conn:
            conn.execute(_TRUNCATE_SQL)
    else:
        Base.metadata.drop_all(_sync_engine)
        Base.metadata.create_all(_sync_engine)
        _schema_created = True

    with Session(_sync_engine) as session:
        # テスト用ロビーを作成
        lobby = Lobby(guild_id="123456789", lobby_channel_id="987654321")
        session.add(lobby)
        session.commit()
        yield session
