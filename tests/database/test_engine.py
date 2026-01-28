"""Tests for database engine module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.database.models import Base

from .conftest import TEST_DATABASE_URL

# ===========================================================================
# init_db テスト
# ===========================================================================


class TestInitDb:
    """Tests for init_db()."""

    @patch("src.database.engine.engine")
    async def test_creates_all_tables(self, mock_engine: MagicMock) -> None:
        """Base.metadata.create_all が呼ばれる。"""
        from src.database.engine import init_db

        mock_conn = AsyncMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(
            return_value=mock_conn
        )
        mock_engine.begin.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        await init_db()

        mock_conn.run_sync.assert_awaited_once()

    async def test_idempotent(self) -> None:
        """init_db を2回呼んでもエラーにならない (冪等性)。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)

            # 1回目: テーブル作成
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # 2回目: 既存テーブルがあっても問題なし
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    async def test_tables_exist_after_init(self) -> None:
        """init_db 後にテーブルが実際に存在する。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)

            from sqlalchemy import inspect as sa_inspect

            async with engine.connect() as conn:
                tables = await conn.run_sync(
                    lambda sync_conn: sa_inspect(sync_conn).get_table_names()
                )

            assert "lobbies" in tables
            assert "voice_sessions" in tables
        finally:
            await engine.dispose()


# ===========================================================================
# get_session テスト
# ===========================================================================


class TestGetSession:
    """Tests for get_session()."""

    @patch("src.database.engine.async_session")
    async def test_returns_session(
        self, mock_factory: MagicMock
    ) -> None:
        """AsyncSession が返される。"""
        from src.database.engine import get_session

        mock_session = AsyncMock(spec=AsyncSession)
        mock_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_factory.return_value.__aexit__ = AsyncMock(
            return_value=False
        )

        result = await get_session()

        assert result is mock_session
