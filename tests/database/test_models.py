"""Tests for database models — edge cases and constraints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from faker import Faker
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import Lobby, VoiceSession

from .conftest import snowflake

fake = Faker()


# ===========================================================================
# Lobby — ユニーク制約・リレーション
# ===========================================================================


class TestLobbyConstraints:
    """Lobby モデルの制約テスト。"""

    async def test_duplicate_channel_id_rejected(
        self, db_session: AsyncSession
    ) -> None:
        """同じ lobby_channel_id は重複登録できない。"""
        channel_id = snowflake()
        db_session.add(
            Lobby(guild_id=snowflake(), lobby_channel_id=channel_id)
        )
        await db_session.commit()

        db_session.add(
            Lobby(guild_id=snowflake(), lobby_channel_id=channel_id)
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_multiple_lobbies_per_guild(
        self, db_session: AsyncSession
    ) -> None:
        """1つのギルドに複数のロビーを作成できる。"""
        guild_id = snowflake()
        for _ in range(3):
            db_session.add(
                Lobby(guild_id=guild_id, lobby_channel_id=snowflake())
            )
        await db_session.commit()

        result = await db_session.execute(
            select(Lobby).where(Lobby.guild_id == guild_id)
        )
        assert len(list(result.scalars().all())) == 3

    async def test_sessions_relationship(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """Lobby.sessions リレーションで子セッションを取得できる。"""
        for _ in range(2):
            db_session.add(
                VoiceSession(
                    lobby_id=lobby.id,
                    channel_id=snowflake(),
                    owner_id=snowflake(),
                    name=fake.word(),
                )
            )
        await db_session.commit()

        result = await db_session.execute(
            select(Lobby)
            .where(Lobby.id == lobby.id)
            .options(selectinload(Lobby.sessions))
        )
        loaded = result.scalar_one()
        assert len(loaded.sessions) == 2

    async def test_cascade_deletes_sessions(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """Lobby を削除すると子 VoiceSession もカスケード削除される。"""
        ch_id = snowflake()
        db_session.add(
            VoiceSession(
                lobby_id=lobby.id,
                channel_id=ch_id,
                owner_id=snowflake(),
                name=fake.word(),
            )
        )
        await db_session.commit()

        await db_session.delete(lobby)
        await db_session.commit()

        result = await db_session.execute(
            select(VoiceSession).where(VoiceSession.channel_id == ch_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_cascade_deletes_multiple_sessions(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """複数のセッションがあるロビーを削除しても全て消える。"""
        ids = []
        for _ in range(5):
            ch = snowflake()
            ids.append(ch)
            db_session.add(
                VoiceSession(
                    lobby_id=lobby.id,
                    channel_id=ch,
                    owner_id=snowflake(),
                    name=fake.word(),
                )
            )
        await db_session.commit()

        await db_session.delete(lobby)
        await db_session.commit()

        result = await db_session.execute(select(VoiceSession))
        assert list(result.scalars().all()) == []


class TestLobbyFields:
    """Lobby フィールドの境界値・型テスト。"""

    async def test_default_user_limit_zero(
        self, db_session: AsyncSession
    ) -> None:
        """default_user_limit のデフォルトは 0。"""
        lobby = Lobby(guild_id=snowflake(), lobby_channel_id=snowflake())
        db_session.add(lobby)
        await db_session.commit()
        assert lobby.default_user_limit == 0

    async def test_category_id_nullable(
        self, db_session: AsyncSession
    ) -> None:
        """category_id は None を許容する。"""
        lobby = Lobby(guild_id=snowflake(), lobby_channel_id=snowflake())
        db_session.add(lobby)
        await db_session.commit()
        assert lobby.category_id is None

    async def test_category_id_set(
        self, db_session: AsyncSession
    ) -> None:
        """category_id に値をセットできる。"""
        cat = snowflake()
        lobby = Lobby(
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
            category_id=cat,
        )
        db_session.add(lobby)
        await db_session.commit()
        assert lobby.category_id == cat

    async def test_large_user_limit(
        self, db_session: AsyncSession
    ) -> None:
        """大きな user_limit 値を保存できる。"""
        lobby = Lobby(
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
            default_user_limit=99999,
        )
        db_session.add(lobby)
        await db_session.commit()
        assert lobby.default_user_limit == 99999

    async def test_unicode_guild_id(
        self, db_session: AsyncSession
    ) -> None:
        """guild_id に数値文字列以外が入っても DB は受け入れる。"""
        lobby = Lobby(
            guild_id="unicode-テスト",
            lobby_channel_id=snowflake(),
        )
        db_session.add(lobby)
        await db_session.commit()
        assert lobby.guild_id == "unicode-テスト"

    async def test_repr_format(
        self, db_session: AsyncSession
    ) -> None:
        """__repr__ に guild_id と channel_id が含まれる。"""
        gid = snowflake()
        cid = snowflake()
        lobby = Lobby(guild_id=gid, lobby_channel_id=cid)
        db_session.add(lobby)
        await db_session.commit()
        text = repr(lobby)
        assert gid in text
        assert cid in text

    async def test_id_auto_increment(
        self, db_session: AsyncSession
    ) -> None:
        """id は自動採番される。"""
        l1 = Lobby(guild_id=snowflake(), lobby_channel_id=snowflake())
        l2 = Lobby(guild_id=snowflake(), lobby_channel_id=snowflake())
        db_session.add_all([l1, l2])
        await db_session.commit()
        assert l1.id is not None
        assert l2.id is not None
        assert l1.id != l2.id


# ===========================================================================
# VoiceSession — ユニーク制約・FK・タイムスタンプ
# ===========================================================================


class TestVoiceSessionConstraints:
    """VoiceSession モデルの制約テスト。"""

    async def test_duplicate_channel_id_rejected(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """同じ channel_id は重複登録できない。"""
        ch_id = snowflake()
        db_session.add(
            VoiceSession(
                lobby_id=lobby.id,
                channel_id=ch_id,
                owner_id=snowflake(),
                name=fake.word(),
            )
        )
        await db_session.commit()

        db_session.add(
            VoiceSession(
                lobby_id=lobby.id,
                channel_id=ch_id,
                owner_id=snowflake(),
                name=fake.word(),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_lobby_relationship(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """VoiceSession.lobby リレーションで親 Lobby を取得できる。"""
        await db_session.refresh(voice_session)
        assert voice_session.lobby is not None
        assert voice_session.lobby.id == voice_session.lobby_id

    async def test_default_values(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """デフォルト値が正しく設定される。"""
        vs = VoiceSession(
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name="Test",
        )
        db_session.add(vs)
        await db_session.commit()

        assert vs.user_limit == 0
        assert vs.is_locked is False
        assert vs.is_hidden is False

    async def test_foreign_key_violation(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない lobby_id は FK 違反。"""
        db_session.add(
            VoiceSession(
                lobby_id=999999,
                channel_id=snowflake(),
                owner_id=snowflake(),
                name="orphan",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_multiple_sessions_per_lobby(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """1つのロビーから複数セッションを作成できる。"""
        for _ in range(5):
            db_session.add(
                VoiceSession(
                    lobby_id=lobby.id,
                    channel_id=snowflake(),
                    owner_id=snowflake(),
                    name=fake.word(),
                )
            )
        await db_session.commit()

        result = await db_session.execute(
            select(VoiceSession).where(
                VoiceSession.lobby_id == lobby.id
            )
        )
        assert len(list(result.scalars().all())) == 5

    async def test_same_owner_multiple_sessions(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """同じオーナーが複数セッションを持てる。"""
        owner = snowflake()
        for _ in range(3):
            db_session.add(
                VoiceSession(
                    lobby_id=lobby.id,
                    channel_id=snowflake(),
                    owner_id=owner,
                    name=fake.word(),
                )
            )
        await db_session.commit()

        result = await db_session.execute(
            select(VoiceSession).where(VoiceSession.owner_id == owner)
        )
        assert len(list(result.scalars().all())) == 3


class TestVoiceSessionFields:
    """VoiceSession フィールドの境界値テスト。"""

    async def test_created_at_auto_set(
        self, voice_session: VoiceSession
    ) -> None:
        """created_at が自動設定される。"""
        assert voice_session.created_at is not None

    async def test_created_at_is_recent(
        self, voice_session: VoiceSession
    ) -> None:
        """created_at がテスト実行時刻と近い。"""
        now = datetime.now(UTC)
        # タイムゾーン無しの場合も考慮
        ts = voice_session.created_at
        if ts.tzinfo is None:
            diff = abs(now.replace(tzinfo=None) - ts)
        else:
            diff = abs(now - ts)
        assert diff < timedelta(seconds=10)

    async def test_repr_contains_ids(
        self, voice_session: VoiceSession
    ) -> None:
        """__repr__ に channel_id と owner_id が含まれる。"""
        text = repr(voice_session)
        assert voice_session.channel_id in text
        assert voice_session.owner_id in text

    async def test_unicode_name(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """チャンネル名に Unicode (日本語・絵文字) を使える。"""
        name = "🎮 テストチャンネル"
        vs = VoiceSession(
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name=name,
        )
        db_session.add(vs)
        await db_session.commit()
        await db_session.refresh(vs)
        assert vs.name == name

    async def test_long_name(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """長いチャンネル名も保存できる。"""
        name = "A" * 200
        vs = VoiceSession(
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name=name,
        )
        db_session.add(vs)
        await db_session.commit()
        await db_session.refresh(vs)
        assert vs.name == name

    async def test_user_limit_boundary(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """user_limit に 0 と大きい値を設定できる。"""
        vs0 = VoiceSession(
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name="zero",
            user_limit=0,
        )
        vs_big = VoiceSession(
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name="big",
            user_limit=99,
        )
        db_session.add_all([vs0, vs_big])
        await db_session.commit()
        assert vs0.user_limit == 0
        assert vs_big.user_limit == 99

    async def test_boolean_fields_toggle(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """is_locked / is_hidden を True に設定して保存・再読み込みできる。"""
        vs = VoiceSession(
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name="toggle",
            is_locked=True,
            is_hidden=True,
        )
        db_session.add(vs)
        await db_session.commit()
        await db_session.refresh(vs)
        assert vs.is_locked is True
        assert vs.is_hidden is True

    async def test_id_auto_increment(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """id は自動採番され、ユニーク。"""
        sessions = []
        for _ in range(3):
            vs = VoiceSession(
                lobby_id=lobby.id,
                channel_id=snowflake(),
                owner_id=snowflake(),
                name=fake.word(),
            )
            db_session.add(vs)
            sessions.append(vs)
        await db_session.commit()
        ids = [s.id for s in sessions]
        assert len(set(ids)) == 3
