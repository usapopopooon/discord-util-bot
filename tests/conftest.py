"""Shared pytest fixtures."""

import os

# Set DISCORD_TOKEN before any src imports to avoid validation error
os.environ.setdefault("DISCORD_TOKEN", "test-token-for-testing")

# =============================================================================
# xdist: ワーカーごとに専用 DB を作成して並列テストを安全に実行する
# =============================================================================
# pytest-xdist のワーカープロセスでは PYTEST_XDIST_WORKER 環境変数が設定される。
# 各ワーカーに専用の PostgreSQL データベースを作成し、環境変数を上書きする。
# これにより tests/database/conftest.py, tests/web/conftest.py 等が
# ワーカー専用の DB URL を参照するようになる。
#
# フレーク対策:
# - pg_terminate_backend: 前回クラッシュで残った接続を強制切断
# - リトライ: 一時的な接続エラーに対して最大3回リトライ (指数バックオフ)
# - atexit クリーンアップ: テスト終了後にワーカー DB を削除
_xdist_worker = os.environ.get("PYTEST_XDIST_WORKER")
if _xdist_worker:
    import atexit
    import time
    from urllib.parse import urlparse, urlunparse

    import psycopg2

    from src.constants import (
        DEFAULT_TEST_DATABASE_URL,
        DEFAULT_TEST_DATABASE_URL_SYNC,
    )

    _worker_db = f"discord_util_bot_test_{_xdist_worker}"

    _base_sync = os.environ.get(
        "TEST_DATABASE_URL_SYNC", DEFAULT_TEST_DATABASE_URL_SYNC
    )
    _base_async = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)

    # ワーカー専用の DB URL を生成
    _p = urlparse(_base_sync)
    os.environ["TEST_DATABASE_URL_SYNC"] = urlunparse(
        _p._replace(path=f"/{_worker_db}")
    )
    _admin_url = urlunparse(_p._replace(path="/postgres"))

    _p = urlparse(_base_async)
    os.environ["TEST_DATABASE_URL"] = urlunparse(_p._replace(path=f"/{_worker_db}"))

    # ワーカー専用データベースを作成 (リトライ付き)
    _last_error: Exception | None = None
    for _attempt in range(3):
        try:
            _conn = psycopg2.connect(_admin_url)
            _conn.autocommit = True
            with _conn.cursor() as _cur:
                # 前回クラッシュで残った接続を強制切断
                _cur.execute(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (_worker_db,),
                )
                _cur.execute(f'DROP DATABASE IF EXISTS "{_worker_db}"')
                _cur.execute(f'CREATE DATABASE "{_worker_db}"')
            _conn.close()
            _last_error = None
            break
        except psycopg2.Error as _e:
            _last_error = _e
            if _attempt < 2:
                time.sleep(0.5 * (_attempt + 1))
    if _last_error is not None:
        _msg = f"Failed to create worker DB '{_worker_db}' after 3 attempts"
        raise RuntimeError(_msg) from _last_error

    def _cleanup_worker_db() -> None:
        """ワーカー DB を削除する (ベストエフォート)。"""
        try:
            conn = psycopg2.connect(_admin_url)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (_worker_db,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{_worker_db}"')
            conn.close()
        except Exception:
            pass  # ベストエフォート: 次回実行時に DROP される

    atexit.register(_cleanup_worker_db)

import logging

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from src.constants import DEFAULT_TEST_DATABASE_URL_SYNC
from src.database.models import Base, Lobby

logger = logging.getLogger(__name__)

TEST_DATABASE_URL_SYNC = os.environ.get(
    "TEST_DATABASE_URL_SYNC",
    DEFAULT_TEST_DATABASE_URL_SYNC,
)

# --- Speed optimizations ---
# NullPool: コネクションプールなし — 接続の残留を防止し xdist ワーカー間の
# 分離を保証する。デフォルトの QueuePool では、ワーカー DB 削除後に
# プール内の接続が無効化されてエラーになる可能性がある。
_sync_engine = create_engine(TEST_DATABASE_URL_SYNC, poolclass=NullPool)

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
        try:
            with _sync_engine.begin() as conn:
                conn.execute(_TRUNCATE_SQL)
        except Exception:
            # TRUNCATE 失敗時はスキーマを再作成してリカバリ
            logger.warning("TRUNCATE failed, recreating schema", exc_info=True)
            _schema_created = False

    if not _schema_created:
        Base.metadata.drop_all(_sync_engine)
        Base.metadata.create_all(_sync_engine)
        _schema_created = True

    with Session(_sync_engine) as session:
        # テスト用ロビーを作成
        lobby = Lobby(guild_id="123456789", lobby_channel_id="987654321")
        session.add(lobby)
        session.commit()
        yield session
