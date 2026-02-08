"""Tests for database models — edge cases and constraints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from faker import Faker
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import (
    AdminUser,
    AutoBanConfig,
    AutoBanLog,
    AutoBanRule,
    BumpConfig,
    BumpReminder,
    DiscordChannel,
    DiscordGuild,
    DiscordRole,
    Lobby,
    RolePanel,
    RolePanelItem,
    StickyMessage,
    Ticket,
    TicketCategory,
    TicketPanel,
    TicketPanelCategory,
    VoiceSession,
    VoiceSessionMember,
)

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
        db_session.add(Lobby(guild_id=snowflake(), lobby_channel_id=channel_id))
        await db_session.commit()

        db_session.add(Lobby(guild_id=snowflake(), lobby_channel_id=channel_id))
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_multiple_lobbies_per_guild(self, db_session: AsyncSession) -> None:
        """1つのギルドに複数のロビーを作成できる。"""
        guild_id = snowflake()
        for _ in range(3):
            db_session.add(Lobby(guild_id=guild_id, lobby_channel_id=snowflake()))
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

    async def test_default_user_limit_zero(self, db_session: AsyncSession) -> None:
        """default_user_limit のデフォルトは 0。"""
        lobby = Lobby(guild_id=snowflake(), lobby_channel_id=snowflake())
        db_session.add(lobby)
        await db_session.commit()
        assert lobby.default_user_limit == 0

    async def test_category_id_nullable(self, db_session: AsyncSession) -> None:
        """category_id は None を許容する。"""
        lobby = Lobby(guild_id=snowflake(), lobby_channel_id=snowflake())
        db_session.add(lobby)
        await db_session.commit()
        assert lobby.category_id is None

    async def test_category_id_set(self, db_session: AsyncSession) -> None:
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

    async def test_large_user_limit(self, db_session: AsyncSession) -> None:
        """大きな user_limit 値を保存できる。"""
        lobby = Lobby(
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
            default_user_limit=99999,
        )
        db_session.add(lobby)
        await db_session.commit()
        assert lobby.default_user_limit == 99999

    async def test_unicode_guild_id_rejected(self, db_session: AsyncSession) -> None:
        """guild_id に数値文字列以外は ValueError で拒否される。"""
        with pytest.raises(ValueError, match="guild_id"):
            Lobby(
                guild_id="unicode-テスト",
                lobby_channel_id=snowflake(),
            )

    async def test_repr_format(self, db_session: AsyncSession) -> None:
        """__repr__ に guild_id と channel_id が含まれる。"""
        gid = snowflake()
        cid = snowflake()
        lobby = Lobby(guild_id=gid, lobby_channel_id=cid)
        db_session.add(lobby)
        await db_session.commit()
        text = repr(lobby)
        assert gid in text
        assert cid in text

    async def test_id_auto_increment(self, db_session: AsyncSession) -> None:
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

    async def test_default_values(self, db_session: AsyncSession, lobby: Lobby) -> None:
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

    async def test_foreign_key_violation(self, db_session: AsyncSession) -> None:
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
            select(VoiceSession).where(VoiceSession.lobby_id == lobby.id)
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

    async def test_created_at_auto_set(self, voice_session: VoiceSession) -> None:
        """created_at が自動設定される。"""
        assert voice_session.created_at is not None

    async def test_created_at_is_recent(self, voice_session: VoiceSession) -> None:
        """created_at がテスト実行時刻と近い。"""
        now = datetime.now(UTC)
        # タイムゾーン無しの場合も考慮
        ts = voice_session.created_at
        if ts.tzinfo is None:
            diff = abs(now.replace(tzinfo=None) - ts)
        else:
            diff = abs(now - ts)
        assert diff < timedelta(seconds=10)

    async def test_repr_contains_ids(self, voice_session: VoiceSession) -> None:
        """__repr__ に channel_id と owner_id が含まれる。"""
        text = repr(voice_session)
        assert voice_session.channel_id in text
        assert voice_session.owner_id in text

    async def test_unicode_name(self, db_session: AsyncSession, lobby: Lobby) -> None:
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

    async def test_long_name(self, db_session: AsyncSession, lobby: Lobby) -> None:
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


# ===========================================================================
# VoiceSessionMember — ユニーク制約・FK・タイムスタンプ
# ===========================================================================


class TestVoiceSessionMemberConstraints:
    """VoiceSessionMember モデルの制約テスト。"""

    async def test_unique_session_user(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """同じセッション+ユーザーの組み合わせは重複登録できない。"""
        user_id = snowflake()
        db_session.add(
            VoiceSessionMember(
                voice_session_id=voice_session.id,
                user_id=user_id,
            )
        )
        await db_session.commit()

        db_session.add(
            VoiceSessionMember(
                voice_session_id=voice_session.id,
                user_id=user_id,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_same_user_different_sessions(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """同じユーザーが異なるセッションには参加できる。"""
        user_id = snowflake()
        for _ in range(3):
            vs = VoiceSession(
                lobby_id=lobby.id,
                channel_id=snowflake(),
                owner_id=snowflake(),
                name=fake.word(),
            )
            db_session.add(vs)
            await db_session.flush()
            db_session.add(
                VoiceSessionMember(
                    voice_session_id=vs.id,
                    user_id=user_id,
                )
            )
        await db_session.commit()

        result = await db_session.execute(
            select(VoiceSessionMember).where(VoiceSessionMember.user_id == user_id)
        )
        assert len(list(result.scalars().all())) == 3

    async def test_cascade_delete_on_session_delete(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """VoiceSession を削除すると関連メンバーもカスケード削除される。"""
        for _ in range(3):
            db_session.add(
                VoiceSessionMember(
                    voice_session_id=voice_session.id,
                    user_id=snowflake(),
                )
            )
        await db_session.commit()

        await db_session.delete(voice_session)
        await db_session.commit()

        result = await db_session.execute(select(VoiceSessionMember))
        assert list(result.scalars().all()) == []

    async def test_foreign_key_violation(self, db_session: AsyncSession) -> None:
        """存在しない voice_session_id は FK 違反。"""
        db_session.add(
            VoiceSessionMember(
                voice_session_id=999999,
                user_id=snowflake(),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestVoiceSessionMemberFields:
    """VoiceSessionMember フィールドのテスト。"""

    async def test_joined_at_auto_set(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """joined_at が自動設定される。"""
        member = VoiceSessionMember(
            voice_session_id=voice_session.id,
            user_id=snowflake(),
        )
        db_session.add(member)
        await db_session.commit()
        assert member.joined_at is not None

    async def test_joined_at_is_recent(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """joined_at がテスト実行時刻と近い。"""
        member = VoiceSessionMember(
            voice_session_id=voice_session.id,
            user_id=snowflake(),
        )
        db_session.add(member)
        await db_session.commit()

        now = datetime.now(UTC)
        ts = member.joined_at
        if ts.tzinfo is None:
            diff = abs(now.replace(tzinfo=None) - ts)
        else:
            diff = abs(now - ts)
        assert diff < timedelta(seconds=10)

    async def test_repr_contains_ids(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """__repr__ に session_id と user_id が含まれる。"""
        user_id = snowflake()
        member = VoiceSessionMember(
            voice_session_id=voice_session.id,
            user_id=user_id,
        )
        db_session.add(member)
        await db_session.commit()

        text = repr(member)
        assert user_id in text
        assert str(voice_session.id) in text


# ===========================================================================
# BumpReminder — ユニーク制約・フィールド
# ===========================================================================


class TestBumpReminderConstraints:
    """BumpReminder モデルの制約テスト。"""

    async def test_unique_guild_service(self, db_session: AsyncSession) -> None:
        """同じ guild + service の組み合わせは重複登録できない。"""
        guild_id = snowflake()
        service = "DISBOARD"

        db_session.add(
            BumpReminder(
                guild_id=guild_id,
                channel_id=snowflake(),
                service_name=service,
            )
        )
        await db_session.commit()

        db_session.add(
            BumpReminder(
                guild_id=guild_id,
                channel_id=snowflake(),
                service_name=service,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_same_guild_different_services(
        self, db_session: AsyncSession
    ) -> None:
        """同じギルドでも異なるサービスなら登録できる。"""
        guild_id = snowflake()
        for service in ["DISBOARD", "ディス速報"]:
            db_session.add(
                BumpReminder(
                    guild_id=guild_id,
                    channel_id=snowflake(),
                    service_name=service,
                )
            )
        await db_session.commit()

        result = await db_session.execute(
            select(BumpReminder).where(BumpReminder.guild_id == guild_id)
        )
        assert len(list(result.scalars().all())) == 2

    async def test_multiple_guilds_same_service(self, db_session: AsyncSession) -> None:
        """異なるギルドで同じサービスを登録できる。"""
        service = "DISBOARD"
        for _ in range(3):
            db_session.add(
                BumpReminder(
                    guild_id=snowflake(),
                    channel_id=snowflake(),
                    service_name=service,
                )
            )
        await db_session.commit()

        result = await db_session.execute(
            select(BumpReminder).where(BumpReminder.service_name == service)
        )
        assert len(list(result.scalars().all())) == 3


class TestBumpReminderFields:
    """BumpReminder フィールドのテスト。"""

    async def test_default_is_enabled(self, db_session: AsyncSession) -> None:
        """is_enabled のデフォルトは True。"""
        reminder = BumpReminder(
            guild_id=snowflake(),
            channel_id=snowflake(),
            service_name="DISBOARD",
        )
        db_session.add(reminder)
        await db_session.commit()
        assert reminder.is_enabled is True

    async def test_remind_at_nullable(self, db_session: AsyncSession) -> None:
        """remind_at は None を許容する。"""
        reminder = BumpReminder(
            guild_id=snowflake(),
            channel_id=snowflake(),
            service_name="DISBOARD",
        )
        db_session.add(reminder)
        await db_session.commit()
        assert reminder.remind_at is None

    async def test_remind_at_set(self, db_session: AsyncSession) -> None:
        """remind_at に値をセットできる。"""
        remind_time = datetime.now(UTC) + timedelta(hours=2)
        reminder = BumpReminder(
            guild_id=snowflake(),
            channel_id=snowflake(),
            service_name="DISBOARD",
            remind_at=remind_time,
        )
        db_session.add(reminder)
        await db_session.commit()
        assert reminder.remind_at is not None

    async def test_role_id_nullable(self, db_session: AsyncSession) -> None:
        """role_id は None を許容する。"""
        reminder = BumpReminder(
            guild_id=snowflake(),
            channel_id=snowflake(),
            service_name="DISBOARD",
        )
        db_session.add(reminder)
        await db_session.commit()
        assert reminder.role_id is None

    async def test_role_id_set(self, db_session: AsyncSession) -> None:
        """role_id に値をセットできる。"""
        role_id = snowflake()
        reminder = BumpReminder(
            guild_id=snowflake(),
            channel_id=snowflake(),
            service_name="DISBOARD",
            role_id=role_id,
        )
        db_session.add(reminder)
        await db_session.commit()
        assert reminder.role_id == role_id

    async def test_is_enabled_toggle(self, db_session: AsyncSession) -> None:
        """is_enabled を False に設定して保存できる。"""
        reminder = BumpReminder(
            guild_id=snowflake(),
            channel_id=snowflake(),
            service_name="DISBOARD",
            is_enabled=False,
        )
        db_session.add(reminder)
        await db_session.commit()
        assert reminder.is_enabled is False

    async def test_repr_contains_fields(self, db_session: AsyncSession) -> None:
        """__repr__ に主要フィールドが含まれる。"""
        guild_id = snowflake()
        reminder = BumpReminder(
            guild_id=guild_id,
            channel_id=snowflake(),
            service_name="DISBOARD",
        )
        db_session.add(reminder)
        await db_session.commit()

        text = repr(reminder)
        assert guild_id in text
        assert "DISBOARD" in text


# ===========================================================================
# BumpConfig — フィールド・デフォルト値
# ===========================================================================


class TestBumpConfigConstraints:
    """BumpConfig モデルの制約テスト。"""

    async def test_guild_id_primary_key(self, db_session: AsyncSession) -> None:
        """guild_id が主キーなので重複登録できない。"""
        guild_id = snowflake()

        db_session.add(
            BumpConfig(
                guild_id=guild_id,
                channel_id=snowflake(),
            )
        )
        await db_session.commit()

        db_session.add(
            BumpConfig(
                guild_id=guild_id,
                channel_id=snowflake(),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestBumpConfigFields:
    """BumpConfig フィールドのテスト。"""

    async def test_created_at_auto_set(self, db_session: AsyncSession) -> None:
        """created_at が自動設定される。"""
        config = BumpConfig(
            guild_id=snowflake(),
            channel_id=snowflake(),
        )
        db_session.add(config)
        await db_session.commit()
        assert config.created_at is not None

    async def test_created_at_is_recent(self, db_session: AsyncSession) -> None:
        """created_at がテスト実行時刻と近い。"""
        config = BumpConfig(
            guild_id=snowflake(),
            channel_id=snowflake(),
        )
        db_session.add(config)
        await db_session.commit()

        now = datetime.now(UTC)
        ts = config.created_at
        if ts.tzinfo is None:
            diff = abs(now.replace(tzinfo=None) - ts)
        else:
            diff = abs(now - ts)
        assert diff < timedelta(seconds=10)

    async def test_repr_contains_ids(self, db_session: AsyncSession) -> None:
        """__repr__ に guild_id と channel_id が含まれる。"""
        guild_id = snowflake()
        channel_id = snowflake()
        config = BumpConfig(
            guild_id=guild_id,
            channel_id=channel_id,
        )
        db_session.add(config)
        await db_session.commit()

        text = repr(config)
        assert guild_id in text
        assert channel_id in text


# ===========================================================================
# StickyMessage — フィールド・デフォルト値
# ===========================================================================


class TestStickyMessageConstraints:
    """StickyMessage モデルの制約テスト。"""

    async def test_channel_id_primary_key(self, db_session: AsyncSession) -> None:
        """channel_id が主キーなので重複登録できない。"""
        channel_id = snowflake()

        db_session.add(
            StickyMessage(
                channel_id=channel_id,
                guild_id=snowflake(),
                title="Title",
                description="Description",
            )
        )
        await db_session.commit()

        db_session.add(
            StickyMessage(
                channel_id=channel_id,
                guild_id=snowflake(),
                title="Another",
                description="Another",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_multiple_channels_same_guild(self, db_session: AsyncSession) -> None:
        """同じギルドで複数チャンネルに sticky を設定できる。"""
        guild_id = snowflake()
        for _ in range(3):
            db_session.add(
                StickyMessage(
                    channel_id=snowflake(),
                    guild_id=guild_id,
                    title=fake.sentence(nb_words=3),
                    description=fake.paragraph(),
                )
            )
        await db_session.commit()

        result = await db_session.execute(
            select(StickyMessage).where(StickyMessage.guild_id == guild_id)
        )
        assert len(list(result.scalars().all())) == 3


class TestStickyMessageFields:
    """StickyMessage フィールドのテスト。"""

    async def test_default_message_type(self, db_session: AsyncSession) -> None:
        """message_type のデフォルトは 'embed'。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.message_type == "embed"

    async def test_message_type_text(self, db_session: AsyncSession) -> None:
        """message_type を 'text' に設定できる。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="",
            description="Plain text message",
            message_type="text",
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.message_type == "text"

    async def test_empty_title_allowed(self, db_session: AsyncSession) -> None:
        """embed でも title を空文字で保存できる（タイトルなし embed）。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="",
            description="Description only embed",
            message_type="embed",
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.title == ""
        assert sticky.description == "Description only embed"
        assert sticky.message_type == "embed"

    async def test_default_cooldown_seconds(self, db_session: AsyncSession) -> None:
        """cooldown_seconds のデフォルトは 5。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.cooldown_seconds == 5

    async def test_cooldown_seconds_custom(self, db_session: AsyncSession) -> None:
        """cooldown_seconds をカスタム値に設定できる。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
            cooldown_seconds=60,
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.cooldown_seconds == 60

    async def test_message_id_nullable(self, db_session: AsyncSession) -> None:
        """message_id は None を許容する。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.message_id is None

    async def test_message_id_set(self, db_session: AsyncSession) -> None:
        """message_id に値をセットできる。"""
        msg_id = snowflake()
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
            message_id=msg_id,
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.message_id == msg_id

    async def test_color_nullable(self, db_session: AsyncSession) -> None:
        """color は None を許容する。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.color is None

    async def test_color_set(self, db_session: AsyncSession) -> None:
        """color に値をセットできる。"""
        color = 0xFF5733
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
            color=color,
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.color == color

    async def test_last_posted_at_nullable(self, db_session: AsyncSession) -> None:
        """last_posted_at は None を許容する。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.last_posted_at is None

    async def test_last_posted_at_set(self, db_session: AsyncSession) -> None:
        """last_posted_at に値をセットできる。"""
        posted_time = datetime.now(UTC)
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
            last_posted_at=posted_time,
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.last_posted_at is not None

    async def test_created_at_auto_set(self, db_session: AsyncSession) -> None:
        """created_at が自動設定される。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.created_at is not None

    async def test_unicode_content(self, db_session: AsyncSession) -> None:
        """title と description に Unicode (日本語・絵文字) を使える。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="🎉 お知らせ",
            description="これは日本語のテスト説明文です。絵文字も使えます！🚀",
        )
        db_session.add(sticky)
        await db_session.commit()
        await db_session.refresh(sticky)
        assert "お知らせ" in sticky.title
        assert "日本語" in sticky.description

    async def test_long_description(self, db_session: AsyncSession) -> None:
        """長い description も保存できる。"""
        long_desc = "A" * 4000  # Embed description limit is 4096
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description=long_desc,
        )
        db_session.add(sticky)
        await db_session.commit()
        await db_session.refresh(sticky)
        assert len(sticky.description) == 4000

    async def test_repr_contains_ids(self, db_session: AsyncSession) -> None:
        """__repr__ に channel_id と guild_id が含まれる。"""
        channel_id = snowflake()
        guild_id = snowflake()
        sticky = StickyMessage(
            channel_id=channel_id,
            guild_id=guild_id,
            title="Title",
            description="Description",
        )
        db_session.add(sticky)
        await db_session.commit()

        text = repr(sticky)
        assert channel_id in text
        assert guild_id in text


# ===========================================================================
# RolePanel — カスケード削除・ユニーク制約・デフォルト値
# ===========================================================================


class TestRolePanelConstraints:
    """RolePanel モデルの制約テスト。"""

    async def test_items_cascade_on_panel_delete(
        self, db_session: AsyncSession
    ) -> None:
        """パネル削除時に子アイテムもカスケード削除される。"""
        panel = RolePanel(
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test Panel",
        )
        db_session.add(panel)
        await db_session.flush()

        for i, emoji in enumerate(["🎮", "🎵", "📚"]):
            db_session.add(
                RolePanelItem(
                    panel_id=panel.id,
                    role_id=snowflake(),
                    emoji=emoji,
                    position=i,
                )
            )
        await db_session.commit()

        await db_session.delete(panel)
        await db_session.commit()

        result = await db_session.execute(select(RolePanelItem))
        assert list(result.scalars().all()) == []

    async def test_panel_default_values(self, db_session: AsyncSession) -> None:
        """デフォルト値が正しく設定される。"""
        panel = RolePanel(
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )
        db_session.add(panel)
        await db_session.commit()

        assert panel.remove_reaction is False
        assert panel.use_embed is True
        assert panel.created_at is not None

    async def test_duplicate_panel_emoji_rejected(
        self, db_session: AsyncSession
    ) -> None:
        """同じパネルに同じ絵文字は重複登録できない。"""
        panel = RolePanel(
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )
        db_session.add(panel)
        await db_session.flush()

        db_session.add(
            RolePanelItem(
                panel_id=panel.id, role_id=snowflake(), emoji="🎮", position=0
            )
        )
        await db_session.commit()

        db_session.add(
            RolePanelItem(
                panel_id=panel.id, role_id=snowflake(), emoji="🎮", position=1
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_same_emoji_different_panels_allowed(
        self, db_session: AsyncSession
    ) -> None:
        """異なるパネルには同じ絵文字を登録できる。"""
        panels = []
        for _ in range(2):
            p = RolePanel(
                guild_id=snowflake(),
                channel_id=snowflake(),
                panel_type="button",
                title="Test",
            )
            db_session.add(p)
            panels.append(p)
        await db_session.flush()

        for p in panels:
            db_session.add(
                RolePanelItem(
                    panel_id=p.id, role_id=snowflake(), emoji="🎮", position=0
                )
            )
        await db_session.commit()

        result = await db_session.execute(
            select(RolePanelItem).where(RolePanelItem.emoji == "🎮")
        )
        assert len(list(result.scalars().all())) == 2


class TestRolePanelItemConstraints:
    """RolePanelItem モデルの制約テスト。"""

    async def test_fk_violation_invalid_panel_id(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない panel_id は FK 違反。"""
        db_session.add(
            RolePanelItem(
                panel_id=999999,
                role_id=snowflake(),
                emoji="🎮",
                position=0,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_default_position_and_style(self, db_session: AsyncSession) -> None:
        """position と style のデフォルト値が正しい。"""
        panel = RolePanel(
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )
        db_session.add(panel)
        await db_session.flush()

        item = RolePanelItem(
            panel_id=panel.id,
            role_id=snowflake(),
            emoji="🎮",
        )
        db_session.add(item)
        await db_session.commit()

        assert item.position == 0
        assert item.style == "secondary"


# ===========================================================================
# DiscordRole / DiscordChannel / DiscordGuild — ユニーク制約・デフォルト値
# ===========================================================================


class TestDiscordEntityConstraints:
    """Discord エンティティモデルの制約テスト。"""

    async def test_duplicate_guild_role_rejected(
        self, db_session: AsyncSession
    ) -> None:
        """同じ (guild_id, role_id) の組み合わせは重複登録できない。"""
        guild_id = snowflake()
        role_id = snowflake()

        db_session.add(
            DiscordRole(
                guild_id=guild_id,
                role_id=role_id,
                role_name="Role1",
            )
        )
        await db_session.commit()

        db_session.add(
            DiscordRole(
                guild_id=guild_id,
                role_id=role_id,
                role_name="Role2",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_duplicate_guild_channel_rejected(
        self, db_session: AsyncSession
    ) -> None:
        """同じ (guild_id, channel_id) の組み合わせは重複登録できない。"""
        guild_id = snowflake()
        channel_id = snowflake()

        db_session.add(
            DiscordChannel(
                guild_id=guild_id,
                channel_id=channel_id,
                channel_name="general",
            )
        )
        await db_session.commit()

        db_session.add(
            DiscordChannel(
                guild_id=guild_id,
                channel_id=channel_id,
                channel_name="general2",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_duplicate_guild_id_rejected(self, db_session: AsyncSession) -> None:
        """DiscordGuild の guild_id PK 重複は拒否される。"""
        guild_id = snowflake()

        db_session.add(DiscordGuild(guild_id=guild_id, guild_name="Server1"))
        await db_session.commit()

        db_session.add(DiscordGuild(guild_id=guild_id, guild_name="Server2"))
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_default_values(self, db_session: AsyncSession) -> None:
        """DiscordRole, DiscordChannel, DiscordGuild のデフォルト値が正しい。"""
        role = DiscordRole(
            guild_id=snowflake(),
            role_id=snowflake(),
            role_name="Test",
        )
        channel = DiscordChannel(
            guild_id=snowflake(),
            channel_id=snowflake(),
            channel_name="test",
        )
        guild = DiscordGuild(
            guild_id=snowflake(),
            guild_name="Test Server",
        )
        db_session.add_all([role, channel, guild])
        await db_session.commit()

        assert role.color == 0
        assert role.position == 0
        assert channel.channel_type == 0
        assert channel.position == 0
        assert guild.member_count == 0


# ===========================================================================
# AutoBanRule / AutoBanLog — カスケード削除・デフォルト値・FK
# ===========================================================================


class TestAutoBanConfigModel:
    """AutoBanConfig モデルのテスト。"""

    async def test_create_config(self, db_session: AsyncSession) -> None:
        """AutoBanConfig を作成できる。"""
        config = AutoBanConfig(
            guild_id=snowflake(),
            log_channel_id=snowflake(),
        )
        db_session.add(config)
        await db_session.commit()

        result = await db_session.execute(
            select(AutoBanConfig).where(AutoBanConfig.guild_id == config.guild_id)
        )
        found = result.scalar_one()
        assert found.guild_id == config.guild_id
        assert found.log_channel_id == config.log_channel_id

    async def test_create_config_without_log_channel(
        self, db_session: AsyncSession
    ) -> None:
        """log_channel_id なしで AutoBanConfig を作成できる。"""
        config = AutoBanConfig(guild_id=snowflake())
        db_session.add(config)
        await db_session.commit()

        result = await db_session.execute(
            select(AutoBanConfig).where(AutoBanConfig.guild_id == config.guild_id)
        )
        found = result.scalar_one()
        assert found.log_channel_id is None

    async def test_guild_id_primary_key(self, db_session: AsyncSession) -> None:
        """同じ guild_id で2つ目の AutoBanConfig は IntegrityError。"""
        gid = snowflake()
        config1 = AutoBanConfig(guild_id=gid, log_channel_id=snowflake())
        db_session.add(config1)
        await db_session.commit()

        config2 = AutoBanConfig(guild_id=gid, log_channel_id=snowflake())
        db_session.add(config2)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_repr(self) -> None:
        """__repr__ にギルド ID とチャンネル ID が含まれる。"""
        config = AutoBanConfig(guild_id="111", log_channel_id="222")
        r = repr(config)
        assert "111" in r
        assert "222" in r

    async def test_update_log_channel(self, db_session: AsyncSession) -> None:
        """log_channel_id を更新できる。"""
        gid = snowflake()
        new_channel = snowflake()
        config = AutoBanConfig(guild_id=gid, log_channel_id=snowflake())
        db_session.add(config)
        await db_session.commit()

        config.log_channel_id = new_channel
        await db_session.commit()

        result = await db_session.execute(
            select(AutoBanConfig).where(AutoBanConfig.guild_id == gid)
        )
        found = result.scalar_one()
        assert found.log_channel_id == new_channel

    async def test_set_log_channel_to_none(self, db_session: AsyncSession) -> None:
        """log_channel_id を None に設定できる。"""
        gid = snowflake()
        config = AutoBanConfig(guild_id=gid, log_channel_id=snowflake())
        db_session.add(config)
        await db_session.commit()

        config.log_channel_id = None
        await db_session.commit()

        result = await db_session.execute(
            select(AutoBanConfig).where(AutoBanConfig.guild_id == gid)
        )
        found = result.scalar_one()
        assert found.log_channel_id is None


class TestAutoBanConstraints:
    """AutoBan モデルの制約テスト。"""

    async def test_logs_cascade_on_rule_delete(self, db_session: AsyncSession) -> None:
        """ルール削除時にログもカスケード削除される。"""
        rule = AutoBanRule(
            guild_id=snowflake(),
            rule_type="username_match",
            action="ban",
            pattern="spam*",
        )
        db_session.add(rule)
        await db_session.flush()

        for _ in range(3):
            db_session.add(
                AutoBanLog(
                    guild_id=rule.guild_id,
                    user_id=snowflake(),
                    username=fake.user_name(),
                    rule_id=rule.id,
                    action_taken="banned",
                    reason="Username matched",
                )
            )
        await db_session.commit()

        await db_session.delete(rule)
        await db_session.commit()

        result = await db_session.execute(select(AutoBanLog))
        assert list(result.scalars().all()) == []

    async def test_default_values(self, db_session: AsyncSession) -> None:
        """AutoBanRule のデフォルト値が正しい。"""
        rule = AutoBanRule(
            guild_id=snowflake(),
            rule_type="no_avatar",
        )
        db_session.add(rule)
        await db_session.commit()

        assert rule.is_enabled is True
        assert rule.action == "ban"

    async def test_log_fk_violation_invalid_rule_id(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない rule_id は FK 違反。"""
        db_session.add(
            AutoBanLog(
                guild_id=snowflake(),
                user_id=snowflake(),
                username="test",
                rule_id=999999,
                action_taken="banned",
                reason="test",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()


# ===========================================================================
# Ticket — ユニーク制約・カスケード削除・Nullable
# ===========================================================================


class TestTicketConstraints:
    """Ticket モデルの制約テスト。"""

    async def test_duplicate_guild_ticket_number_rejected(
        self, db_session: AsyncSession
    ) -> None:
        """同じ (guild_id, ticket_number) は重複登録できない。"""
        guild_id = snowflake()
        category = TicketCategory(
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )
        db_session.add(category)
        await db_session.flush()

        db_session.add(
            Ticket(
                guild_id=guild_id,
                channel_id=snowflake(),
                user_id=snowflake(),
                username="user1",
                category_id=category.id,
                ticket_number=1,
            )
        )
        await db_session.commit()

        db_session.add(
            Ticket(
                guild_id=guild_id,
                channel_id=snowflake(),
                user_id=snowflake(),
                username="user2",
                category_id=category.id,
                ticket_number=1,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_same_ticket_number_different_guilds_allowed(
        self, db_session: AsyncSession
    ) -> None:
        """異なるギルドでは同じ ticket_number を使える。"""
        categories = []
        for _ in range(2):
            cat = TicketCategory(
                guild_id=snowflake(),
                name="Support",
                staff_role_id=snowflake(),
            )
            db_session.add(cat)
            categories.append(cat)
        await db_session.flush()

        for cat in categories:
            db_session.add(
                Ticket(
                    guild_id=cat.guild_id,
                    channel_id=snowflake(),
                    user_id=snowflake(),
                    username="user",
                    category_id=cat.id,
                    ticket_number=1,
                )
            )
        await db_session.commit()

        result = await db_session.execute(
            select(Ticket).where(Ticket.ticket_number == 1)
        )
        assert len(list(result.scalars().all())) == 2

    async def test_channel_id_nullable(self, db_session: AsyncSession) -> None:
        """channel_id は None を許容する (クローズ後)。"""
        guild_id = snowflake()
        category = TicketCategory(
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )
        db_session.add(category)
        await db_session.flush()

        ticket = Ticket(
            guild_id=guild_id,
            channel_id=None,
            user_id=snowflake(),
            username="user",
            category_id=category.id,
            ticket_number=1,
        )
        db_session.add(ticket)
        await db_session.commit()

        assert ticket.channel_id is None

    async def test_panel_category_associations_cascade_on_panel_delete(
        self, db_session: AsyncSession
    ) -> None:
        """パネル削除時に TicketPanelCategory もカスケード削除される。"""
        guild_id = snowflake()
        panel = TicketPanel(
            guild_id=guild_id,
            channel_id=snowflake(),
            title="Support Panel",
        )
        category = TicketCategory(
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )
        db_session.add_all([panel, category])
        await db_session.flush()

        db_session.add(
            TicketPanelCategory(
                panel_id=panel.id,
                category_id=category.id,
            )
        )
        await db_session.commit()

        await db_session.delete(panel)
        await db_session.commit()

        result = await db_session.execute(select(TicketPanelCategory))
        assert list(result.scalars().all()) == []

    async def test_duplicate_panel_category_rejected(
        self, db_session: AsyncSession
    ) -> None:
        """同じ (panel_id, category_id) は重複登録できない。"""
        guild_id = snowflake()
        panel = TicketPanel(
            guild_id=guild_id,
            channel_id=snowflake(),
            title="Panel",
        )
        category = TicketCategory(
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )
        db_session.add_all([panel, category])
        await db_session.flush()

        db_session.add(TicketPanelCategory(panel_id=panel.id, category_id=category.id))
        await db_session.commit()

        db_session.add(TicketPanelCategory(panel_id=panel.id, category_id=category.id))
        with pytest.raises(IntegrityError):
            await db_session.commit()


# ===========================================================================
# Model Validators — @validates デコレータのテスト
# ===========================================================================


class TestModelValidators:
    """各モデルの @validates デコレータのテスト。"""

    async def test_lobby_invalid_guild_id_rejected(self) -> None:
        """Lobby の guild_id に空文字・非数字は ValueError。"""
        with pytest.raises(ValueError, match="guild_id"):
            Lobby(guild_id="", lobby_channel_id=snowflake(), panel_type="button")

        with pytest.raises(ValueError, match="guild_id"):
            Lobby(guild_id="abc", lobby_channel_id=snowflake())

    async def test_lobby_valid_ids_accepted(self) -> None:
        """Lobby の guild_id / lobby_channel_id に数字文字列は受け入れられる。"""
        lobby = Lobby(guild_id=snowflake(), lobby_channel_id=snowflake())
        assert lobby.guild_id.isdigit()
        assert lobby.lobby_channel_id.isdigit()

    async def test_voice_session_negative_user_limit_rejected(self) -> None:
        """VoiceSession の user_limit に負の値は ValueError。"""
        with pytest.raises(ValueError, match="user_limit"):
            VoiceSession(
                lobby_id=1,
                channel_id=snowflake(),
                owner_id=snowflake(),
                name="test",
                user_limit=-1,
            )

    async def test_voice_session_zero_user_limit_accepted(self) -> None:
        """VoiceSession の user_limit に 0 は受け入れられる。"""
        vs = VoiceSession(
            lobby_id=1,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name="test",
            user_limit=0,
        )
        assert vs.user_limit == 0

    async def test_sticky_color_out_of_range_rejected(self) -> None:
        """StickyMessage の color に範囲外の値は ValueError。"""
        with pytest.raises(ValueError, match="color"):
            StickyMessage(
                channel_id=snowflake(),
                guild_id=snowflake(),
                title="T",
                description="D",
                color=-1,
            )

        with pytest.raises(ValueError, match="color"):
            StickyMessage(
                channel_id=snowflake(),
                guild_id=snowflake(),
                title="T",
                description="D",
                color=0x1000000,
            )

    async def test_sticky_color_none_accepted(self) -> None:
        """StickyMessage の color に None は受け入れられる。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="T",
            description="D",
            color=None,
        )
        assert sticky.color is None

    async def test_sticky_negative_cooldown_rejected(self) -> None:
        """StickyMessage の cooldown_seconds に負の値は ValueError。"""
        with pytest.raises(ValueError, match="cooldown_seconds"):
            StickyMessage(
                channel_id=snowflake(),
                guild_id=snowflake(),
                title="T",
                description="D",
                cooldown_seconds=-1,
            )

    async def test_role_panel_invalid_type_rejected(self) -> None:
        """RolePanel の panel_type に不正な値は ValueError。"""
        with pytest.raises(ValueError, match="panel_type"):
            RolePanel(
                guild_id=snowflake(),
                channel_id=snowflake(),
                panel_type="dropdown",
                title="Test",
            )

    async def test_role_panel_item_invalid_style_rejected(self) -> None:
        """RolePanelItem の style に不正な値は ValueError。"""
        with pytest.raises(ValueError, match="style"):
            RolePanelItem(
                panel_id=1,
                role_id=snowflake(),
                emoji="🎮",
                style="primary2",
            )

    async def test_autoban_invalid_rule_type_rejected(self) -> None:
        """AutoBanRule の rule_type に不正な値は ValueError。"""
        with pytest.raises(ValueError, match="rule_type"):
            AutoBanRule(
                guild_id=snowflake(),
                rule_type="unknown",
            )

    async def test_autoban_invalid_action_rejected(self) -> None:
        """AutoBanRule の action に不正な値は ValueError。"""
        with pytest.raises(ValueError, match="action"):
            AutoBanRule(
                guild_id=snowflake(),
                rule_type="no_avatar",
                action="warn",
            )

    async def test_ticket_invalid_status_rejected(self) -> None:
        """Ticket の status に不正な値は ValueError。"""
        with pytest.raises(ValueError, match="status"):
            Ticket(
                guild_id=snowflake(),
                channel_id=snowflake(),
                user_id=snowflake(),
                username="test",
                category_id=1,
                ticket_number=1,
                status="pending",
            )


# ===========================================================================
# パラメタライズテスト
# ===========================================================================


class TestModelsParametrized:
    """各モデルのパラメタライズテスト。"""

    @pytest.mark.parametrize(
        "user_limit",
        [0, 1, 10, 50, 99],
    )
    async def test_voice_session_user_limit_values(
        self, db_session: AsyncSession, lobby: Lobby, user_limit: int
    ) -> None:
        """様々な user_limit 値を保存できる。"""
        vs = VoiceSession(
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name=fake.word(),
            user_limit=user_limit,
        )
        db_session.add(vs)
        await db_session.commit()
        assert vs.user_limit == user_limit

    @pytest.mark.parametrize(
        "is_locked,is_hidden",
        [
            (False, False),
            (True, False),
            (False, True),
            (True, True),
        ],
    )
    async def test_voice_session_boolean_combinations(
        self,
        db_session: AsyncSession,
        lobby: Lobby,
        is_locked: bool,
        is_hidden: bool,
    ) -> None:
        """is_locked と is_hidden の全組み合わせを保存できる。"""
        vs = VoiceSession(
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name=fake.word(),
            is_locked=is_locked,
            is_hidden=is_hidden,
        )
        db_session.add(vs)
        await db_session.commit()
        assert vs.is_locked == is_locked
        assert vs.is_hidden == is_hidden

    @pytest.mark.parametrize(
        "service_name",
        ["DISBOARD", "ディス速報"],
    )
    async def test_bump_reminder_service_names(
        self, db_session: AsyncSession, service_name: str
    ) -> None:
        """各サービス名を保存できる。"""
        reminder = BumpReminder(
            guild_id=snowflake(),
            channel_id=snowflake(),
            service_name=service_name,
        )
        db_session.add(reminder)
        await db_session.commit()
        assert reminder.service_name == service_name

    @pytest.mark.parametrize(
        "message_type",
        ["embed", "text"],
    )
    async def test_sticky_message_types(
        self, db_session: AsyncSession, message_type: str
    ) -> None:
        """各メッセージタイプを保存できる。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
            message_type=message_type,
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.message_type == message_type

    @pytest.mark.parametrize(
        "cooldown_seconds",
        [1, 5, 10, 30, 60, 300],
    )
    async def test_sticky_cooldown_values(
        self, db_session: AsyncSession, cooldown_seconds: int
    ) -> None:
        """様々な cooldown_seconds 値を保存できる。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
            cooldown_seconds=cooldown_seconds,
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.cooldown_seconds == cooldown_seconds

    @pytest.mark.parametrize(
        "color",
        [0x000000, 0xFF0000, 0x00FF00, 0x0000FF, 0xFFFFFF, 0x5865F2],
    )
    async def test_sticky_color_values(
        self, db_session: AsyncSession, color: int
    ) -> None:
        """様々な color 値を保存できる。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="Title",
            description="Description",
            color=color,
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.color == color

    @pytest.mark.parametrize(
        "title",
        ["", "Short", "A" * 256, "🎉 お知らせ"],
    )
    async def test_sticky_title_variations(
        self, db_session: AsyncSession, title: str
    ) -> None:
        """様々な title 値を保存できる（空文字含む）。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title=title,
            description="Description",
        )
        db_session.add(sticky)
        await db_session.commit()
        assert sticky.title == title


# ===========================================================================
# AdminUser — ユニーク制約・タイムスタンプ
# ===========================================================================


class TestAdminUserConstraints:
    """AdminUser モデルの制約テスト。"""

    async def test_unique_email(self, db_session: AsyncSession) -> None:
        """同じ email は重複登録できない。"""
        email = "admin@example.com"
        db_session.add(
            AdminUser(
                email=email,
                password_hash="hash1",
            )
        )
        await db_session.commit()

        db_session.add(
            AdminUser(
                email=email,
                password_hash="hash2",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_different_emails_allowed(self, db_session: AsyncSession) -> None:
        """異なる email は複数登録できる。"""
        for i in range(3):
            db_session.add(
                AdminUser(
                    email=f"admin{i}",
                    password_hash=f"hash{i}",
                )
            )
        await db_session.commit()

        result = await db_session.execute(select(AdminUser))
        assert len(list(result.scalars().all())) == 3


class TestAdminUserFields:
    """AdminUser フィールドのテスト。"""

    async def test_created_at_auto_set(self, db_session: AsyncSession) -> None:
        """created_at が自動設定される。"""
        admin = AdminUser(
            email="admin",
            password_hash="hash",
        )
        db_session.add(admin)
        await db_session.commit()
        assert admin.created_at is not None

    async def test_created_at_is_recent(self, db_session: AsyncSession) -> None:
        """created_at がテスト実行時刻と近い。"""
        admin = AdminUser(
            email="admin",
            password_hash="hash",
        )
        db_session.add(admin)
        await db_session.commit()

        now = datetime.now(UTC)
        ts = admin.created_at
        if ts.tzinfo is None:
            diff = abs(now.replace(tzinfo=None) - ts)
        else:
            diff = abs(now - ts)
        assert diff < timedelta(seconds=10)

    async def test_updated_at_auto_set(self, db_session: AsyncSession) -> None:
        """updated_at が自動設定される。"""
        admin = AdminUser(
            email="admin",
            password_hash="hash",
        )
        db_session.add(admin)
        await db_session.commit()
        assert admin.updated_at is not None

    async def test_password_hash_stored(self, db_session: AsyncSession) -> None:
        """password_hash が保存される。"""
        password_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4"
        admin = AdminUser(
            email="admin",
            password_hash=password_hash,
        )
        db_session.add(admin)
        await db_session.commit()
        await db_session.refresh(admin)
        assert admin.password_hash == password_hash

    async def test_repr_contains_email(self, db_session: AsyncSession) -> None:
        """__repr__ に email が含まれる。"""
        admin = AdminUser(
            email="test@example.com",
            password_hash="hash",
        )
        db_session.add(admin)
        await db_session.commit()

        text = repr(admin)
        assert "test@example.com" in text
        assert str(admin.id) in text

    async def test_nullable_fields_default_none(self, db_session: AsyncSession) -> None:
        """nullable フィールドはデフォルト None。"""
        admin = AdminUser(
            email="nulltest@example.com",
            password_hash="hash",
        )
        db_session.add(admin)
        await db_session.commit()

        assert admin.password_changed_at is None
        assert admin.reset_token is None
        assert admin.reset_token_expires_at is None
        assert admin.pending_email is None
        assert admin.email_change_token is None
        assert admin.email_change_token_expires_at is None
        assert admin.email_verified is False

    async def test_email_verified_toggle(self, db_session: AsyncSession) -> None:
        """email_verified を True に設定して保存できる。"""
        admin = AdminUser(
            email="verified@example.com",
            password_hash="hash",
            email_verified=True,
        )
        db_session.add(admin)
        await db_session.commit()
        assert admin.email_verified is True


# ===========================================================================
# Additional Edge Case Tests — Validators
# ===========================================================================


class TestModelValidatorsEdgeCases:
    """@validates デコレータの追加エッジケーステスト。"""

    async def test_lobby_empty_string_guild_id_rejected(self) -> None:
        """Lobby の guild_id に空文字は ValueError。"""
        with pytest.raises(ValueError, match="guild_id"):
            Lobby(guild_id="", lobby_channel_id=snowflake())

    async def test_lobby_whitespace_guild_id_rejected(self) -> None:
        """Lobby の guild_id にスペースは ValueError。"""
        with pytest.raises(ValueError, match="guild_id"):
            Lobby(guild_id=" ", lobby_channel_id=snowflake())

    async def test_lobby_negative_number_string_rejected(self) -> None:
        """Lobby の guild_id に負数文字列は ValueError。"""
        with pytest.raises(ValueError, match="guild_id"):
            Lobby(guild_id="-123", lobby_channel_id=snowflake())

    async def test_lobby_decimal_number_string_rejected(self) -> None:
        """Lobby の guild_id に小数文字列は ValueError。"""
        with pytest.raises(ValueError, match="guild_id"):
            Lobby(guild_id="123.456", lobby_channel_id=snowflake())

    async def test_lobby_large_snowflake_accepted(self) -> None:
        """Lobby の guild_id に18桁の大きな snowflake は受け入れられる。"""
        large_id = "999999999999999999"
        lobby = Lobby(guild_id=large_id, lobby_channel_id=snowflake())
        assert lobby.guild_id == large_id

    async def test_voice_session_invalid_channel_id_rejected(self) -> None:
        """VoiceSession の channel_id に非数字は ValueError。"""
        with pytest.raises(ValueError, match="channel_id"):
            VoiceSession(
                lobby_id=1,
                channel_id="abc",
                owner_id=snowflake(),
                name="test",
            )

    async def test_voice_session_invalid_owner_id_rejected(self) -> None:
        """VoiceSession の owner_id に非数字は ValueError。"""
        with pytest.raises(ValueError, match="owner_id"):
            VoiceSession(
                lobby_id=1,
                channel_id=snowflake(),
                owner_id="not-a-number",
                name="test",
            )

    async def test_voice_session_user_limit_large_value(self) -> None:
        """VoiceSession の user_limit に大きな正の値は受け入れられる。"""
        vs = VoiceSession(
            lobby_id=1,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name="test",
            user_limit=9999,
        )
        assert vs.user_limit == 9999

    async def test_sticky_color_boundary_zero_accepted(self) -> None:
        """StickyMessage の color = 0 (黒) は受け入れられる。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="T",
            description="D",
            color=0,
        )
        assert sticky.color == 0

    async def test_sticky_color_boundary_max_accepted(self) -> None:
        """StickyMessage の color = 0xFFFFFF (白) は受け入れられる。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="T",
            description="D",
            color=0xFFFFFF,
        )
        assert sticky.color == 0xFFFFFF

    async def test_sticky_cooldown_zero_accepted(self) -> None:
        """StickyMessage の cooldown_seconds = 0 は受け入れられる。"""
        sticky = StickyMessage(
            channel_id=snowflake(),
            guild_id=snowflake(),
            title="T",
            description="D",
            cooldown_seconds=0,
        )
        assert sticky.cooldown_seconds == 0

    async def test_role_panel_button_type_accepted(self) -> None:
        """RolePanel の panel_type = 'button' は受け入れられる。"""
        panel = RolePanel(
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )
        assert panel.panel_type == "button"

    async def test_role_panel_reaction_type_accepted(self) -> None:
        """RolePanel の panel_type = 'reaction' は受け入れられる。"""
        panel = RolePanel(
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="reaction",
            title="Test",
        )
        assert panel.panel_type == "reaction"

    async def test_role_panel_color_out_of_range_rejected(self) -> None:
        """RolePanel の color に範囲外の値は ValueError。"""
        with pytest.raises(ValueError, match="color"):
            RolePanel(
                guild_id=snowflake(),
                channel_id=snowflake(),
                panel_type="button",
                title="Test",
                color=-1,
            )

        with pytest.raises(ValueError, match="color"):
            RolePanel(
                guild_id=snowflake(),
                channel_id=snowflake(),
                panel_type="button",
                title="Test",
                color=0x1000000,
            )

    @pytest.mark.parametrize("style", ["primary", "secondary", "success", "danger"])
    async def test_role_panel_item_all_valid_styles(self, style: str) -> None:
        """RolePanelItem の全ての有効な style が受け入れられる。"""
        item = RolePanelItem(
            panel_id=1,
            role_id=snowflake(),
            emoji="🎮",
            style=style,
        )
        assert item.style == style

    @pytest.mark.parametrize(
        "rule_type", ["username_match", "account_age", "no_avatar"]
    )
    async def test_autoban_all_valid_rule_types(self, rule_type: str) -> None:
        """AutoBanRule の全ての有効な rule_type が受け入れられる。"""
        rule = AutoBanRule(
            guild_id=snowflake(),
            rule_type=rule_type,
        )
        assert rule.rule_type == rule_type

    @pytest.mark.parametrize("status", ["open", "claimed", "closed"])
    async def test_ticket_all_valid_statuses(self, status: str) -> None:
        """Ticket の全ての有効な status が受け入れられる。"""
        ticket = Ticket(
            guild_id=snowflake(),
            channel_id=snowflake(),
            user_id=snowflake(),
            username="test",
            category_id=1,
            ticket_number=1,
            status=status,
        )
        assert ticket.status == status


# ===========================================================================
# Cascade Delete Deep Chain Tests
# ===========================================================================


class TestCascadeDeleteDeepChain:
    """カスケード削除の深いチェーンテスト。"""

    async def test_lobby_delete_cascades_to_session_members(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """Lobby 削除 → VoiceSession → VoiceSessionMember まで全てカスケード削除。"""
        vs = VoiceSession(
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name="test",
        )
        db_session.add(vs)
        await db_session.flush()

        member = VoiceSessionMember(
            voice_session_id=vs.id,
            user_id=snowflake(),
        )
        db_session.add(member)
        await db_session.commit()

        # ロビーを削除
        await db_session.delete(lobby)
        await db_session.commit()

        # VoiceSession も VoiceSessionMember も削除される
        from sqlalchemy import select

        result_vs = await db_session.execute(select(VoiceSession))
        assert list(result_vs.scalars().all()) == []

        result_m = await db_session.execute(select(VoiceSessionMember))
        assert list(result_m.scalars().all()) == []

    async def test_lobby_delete_with_no_children(
        self, db_session: AsyncSession
    ) -> None:
        """子セッションなしのロビー削除は正常動作する。"""
        lobby = Lobby(guild_id=snowflake(), lobby_channel_id=snowflake())
        db_session.add(lobby)
        await db_session.commit()

        await db_session.delete(lobby)
        await db_session.commit()

        from sqlalchemy import select

        result = await db_session.execute(select(Lobby))
        assert list(result.scalars().all()) == []

    async def test_ticket_category_delete_cascades_to_tickets(
        self, db_session: AsyncSession
    ) -> None:
        """TicketCategory 削除で Ticket もカスケード削除。"""
        guild_id = snowflake()
        category = TicketCategory(
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )
        db_session.add(category)
        await db_session.flush()

        ticket = Ticket(
            guild_id=guild_id,
            channel_id=snowflake(),
            user_id=snowflake(),
            username="user",
            category_id=category.id,
            ticket_number=1,
        )
        db_session.add(ticket)
        await db_session.commit()

        await db_session.delete(category)
        await db_session.commit()

        from sqlalchemy import select

        result = await db_session.execute(select(Ticket))
        assert list(result.scalars().all()) == []

    async def test_ticket_category_delete_cascades_to_panel_associations(
        self, db_session: AsyncSession
    ) -> None:
        """TicketCategory 削除で TicketPanelCategory もカスケード削除。"""
        guild_id = snowflake()
        category = TicketCategory(
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )
        panel = TicketPanel(
            guild_id=guild_id,
            channel_id=snowflake(),
            title="Panel",
        )
        db_session.add_all([category, panel])
        await db_session.flush()

        assoc = TicketPanelCategory(
            panel_id=panel.id,
            category_id=category.id,
        )
        db_session.add(assoc)
        await db_session.commit()

        await db_session.delete(category)
        await db_session.commit()

        from sqlalchemy import select

        result = await db_session.execute(select(TicketPanelCategory))
        assert list(result.scalars().all()) == []


# ===========================================================================
# Ticket Model Edge Cases
# ===========================================================================


class TestTicketFieldEdgeCases:
    """Ticket モデルのフィールドエッジケーステスト。"""

    async def test_closed_ticket_with_all_fields(
        self, db_session: AsyncSession
    ) -> None:
        """クローズ済みチケットの全フィールドが保存される。"""
        guild_id = snowflake()
        category = TicketCategory(
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )
        db_session.add(category)
        await db_session.flush()

        ticket = Ticket(
            guild_id=guild_id,
            channel_id=None,
            user_id=snowflake(),
            username="user",
            category_id=category.id,
            ticket_number=1,
            status="closed",
            claimed_by="staff_user",
            closed_by="admin_user",
            close_reason="Resolved",
            transcript="Some transcript text",
            closed_at=datetime.now(UTC),
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)

        assert ticket.status == "closed"
        assert ticket.channel_id is None
        assert ticket.claimed_by == "staff_user"
        assert ticket.closed_by == "admin_user"
        assert ticket.close_reason == "Resolved"
        assert ticket.transcript == "Some transcript text"
        assert ticket.closed_at is not None

    async def test_ticket_form_answers_stored(self, db_session: AsyncSession) -> None:
        """form_answers の JSON 文字列が保存される。"""
        guild_id = snowflake()
        category = TicketCategory(
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )
        db_session.add(category)
        await db_session.flush()

        import json

        answers = json.dumps(["Answer 1", "Answer 2"])
        ticket = Ticket(
            guild_id=guild_id,
            channel_id=snowflake(),
            user_id=snowflake(),
            username="user",
            category_id=category.id,
            ticket_number=1,
            form_answers=answers,
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)

        assert json.loads(ticket.form_answers) == ["Answer 1", "Answer 2"]

    async def test_ticket_long_transcript(self, db_session: AsyncSession) -> None:
        """長いトランスクリプトが保存される (Text カラム)。"""
        guild_id = snowflake()
        category = TicketCategory(
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )
        db_session.add(category)
        await db_session.flush()

        long_transcript = "A" * 50000
        ticket = Ticket(
            guild_id=guild_id,
            channel_id=snowflake(),
            user_id=snowflake(),
            username="user",
            category_id=category.id,
            ticket_number=1,
            transcript=long_transcript,
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)

        assert len(ticket.transcript) == 50000

    async def test_ticket_repr(self, db_session: AsyncSession) -> None:
        """Ticket の __repr__ にフィールドが含まれる。"""
        guild_id = snowflake()
        category = TicketCategory(
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )
        db_session.add(category)
        await db_session.flush()

        ticket = Ticket(
            guild_id=guild_id,
            channel_id=snowflake(),
            user_id=snowflake(),
            username="user",
            category_id=category.id,
            ticket_number=42,
        )
        db_session.add(ticket)
        await db_session.commit()

        text = repr(ticket)
        assert "42" in text
        assert guild_id in text


# ===========================================================================
# DiscordEntity Edge Cases
# ===========================================================================


class TestDiscordEntityEdgeCases:
    """Discord エンティティモデルの追加エッジケーステスト。"""

    async def test_discord_role_unicode_name(self, db_session: AsyncSession) -> None:
        """DiscordRole に Unicode ロール名を保存できる。"""
        role = DiscordRole(
            guild_id=snowflake(),
            role_id=snowflake(),
            role_name="🎮 ゲーマー",
            color=0xFF0000,
            position=5,
        )
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)
        assert "ゲーマー" in role.role_name

    async def test_discord_channel_all_types(self, db_session: AsyncSession) -> None:
        """各種チャンネルタイプが保存できる。"""
        guild_id = snowflake()
        for ch_type in [0, 2, 4, 5, 15]:
            ch = DiscordChannel(
                guild_id=guild_id,
                channel_id=snowflake(),
                channel_name=f"channel_type_{ch_type}",
                channel_type=ch_type,
            )
            db_session.add(ch)
        await db_session.commit()

        from sqlalchemy import select

        result = await db_session.execute(
            select(DiscordChannel).where(DiscordChannel.guild_id == guild_id)
        )
        assert len(list(result.scalars().all())) == 5

    async def test_discord_guild_with_icon_hash(self, db_session: AsyncSession) -> None:
        """DiscordGuild に icon_hash を設定できる。"""
        guild = DiscordGuild(
            guild_id=snowflake(),
            guild_name="Test Server",
            icon_hash="a_1234567890abcdef",
            member_count=500,
        )
        db_session.add(guild)
        await db_session.commit()
        await db_session.refresh(guild)
        assert guild.icon_hash == "a_1234567890abcdef"
        assert guild.member_count == 500

    async def test_discord_channel_repr(self, db_session: AsyncSession) -> None:
        """DiscordChannel の __repr__ にフィールドが含まれる。"""
        channel_id = snowflake()
        ch = DiscordChannel(
            guild_id=snowflake(),
            channel_id=channel_id,
            channel_name="test-channel",
        )
        db_session.add(ch)
        await db_session.commit()

        text = repr(ch)
        assert channel_id in text
        assert "test-channel" in text

    async def test_discord_role_repr(self, db_session: AsyncSession) -> None:
        """DiscordRole の __repr__ にフィールドが含まれる。"""
        role_id = snowflake()
        role = DiscordRole(
            guild_id=snowflake(),
            role_id=role_id,
            role_name="Moderator",
        )
        db_session.add(role)
        await db_session.commit()

        text = repr(role)
        assert role_id in text
        assert "Moderator" in text

    async def test_discord_guild_repr(self, db_session: AsyncSession) -> None:
        """DiscordGuild の __repr__ にフィールドが含まれる。"""
        guild_id = snowflake()
        guild = DiscordGuild(
            guild_id=guild_id,
            guild_name="My Server",
        )
        db_session.add(guild)
        await db_session.commit()

        text = repr(guild)
        assert guild_id in text
        assert "My Server" in text
