"""Tests for database service."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.database.models import Base, Lobby, VoiceSession


@pytest.fixture
def db_session() -> Session:
    """Create an in-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        lobby = Lobby(guild_id="123", lobby_channel_id="456")
        session.add(lobby)
        session.commit()
        yield session


class TestLobbyOperations:
    """Tests for lobby database operations."""

    def test_create_lobby(self, db_session: Session) -> None:
        """Test creating a lobby."""
        lobby = Lobby(guild_id="999", lobby_channel_id="888")
        db_session.add(lobby)
        db_session.commit()

        result = db_session.execute(
            select(Lobby).where(Lobby.lobby_channel_id == "888")
        )
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.guild_id == "999"

    def test_get_lobby_by_channel_id(self, db_session: Session) -> None:
        """Test getting a lobby by channel ID."""
        result = db_session.execute(
            select(Lobby).where(Lobby.lobby_channel_id == "456")
        )
        lobby = result.scalar_one_or_none()
        assert lobby is not None
        assert lobby.guild_id == "123"

    def test_get_lobby_not_found(self, db_session: Session) -> None:
        """Test getting a non-existent lobby."""
        result = db_session.execute(
            select(Lobby).where(Lobby.lobby_channel_id == "nonexistent")
        )
        lobby = result.scalar_one_or_none()
        assert lobby is None


class TestVoiceSessionOperations:
    """Tests for voice session database operations."""

    def test_create_voice_session(self, db_session: Session) -> None:
        """Test creating a voice session."""
        result = db_session.execute(
            select(Lobby).where(Lobby.lobby_channel_id == "456")
        )
        lobby = result.scalar_one()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )
        db_session.add(session)
        db_session.commit()

        assert session.id is not None
        assert session.channel_id == "789"
        assert session.owner_id == "111"

    def test_get_voice_session(self, db_session: Session) -> None:
        """Test getting a voice session."""
        result = db_session.execute(
            select(Lobby).where(Lobby.lobby_channel_id == "456")
        )
        lobby = result.scalar_one()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )
        db_session.add(session)
        db_session.commit()

        result = db_session.execute(
            select(VoiceSession).where(VoiceSession.channel_id == "789")
        )
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.owner_id == "111"

    def test_delete_voice_session(self, db_session: Session) -> None:
        """Test deleting a voice session."""
        result = db_session.execute(
            select(Lobby).where(Lobby.lobby_channel_id == "456")
        )
        lobby = result.scalar_one()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )
        db_session.add(session)
        db_session.commit()

        db_session.delete(session)
        db_session.commit()

        result = db_session.execute(
            select(VoiceSession).where(VoiceSession.channel_id == "789")
        )
        found = result.scalar_one_or_none()
        assert found is None

    def test_voice_session_default_is_locked(self, db_session: Session) -> None:
        """Test that is_locked defaults to False."""
        result = db_session.execute(
            select(Lobby).where(Lobby.lobby_channel_id == "456")
        )
        lobby = result.scalar_one()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )
        db_session.add(session)
        db_session.commit()

        assert session.is_locked is False

    def test_voice_session_default_is_hidden(self, db_session: Session) -> None:
        """Test that is_hidden defaults to False."""
        result = db_session.execute(
            select(Lobby).where(Lobby.lobby_channel_id == "456")
        )
        lobby = result.scalar_one()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )
        db_session.add(session)
        db_session.commit()

        assert session.is_hidden is False

    def test_voice_session_update_is_hidden(self, db_session: Session) -> None:
        """Test updating is_hidden field."""
        result = db_session.execute(
            select(Lobby).where(Lobby.lobby_channel_id == "456")
        )
        lobby = result.scalar_one()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )
        db_session.add(session)
        db_session.commit()

        session.is_hidden = True
        db_session.commit()

        result = db_session.execute(
            select(VoiceSession).where(VoiceSession.channel_id == "789")
        )
        found = result.scalar_one()
        assert found.is_hidden is True

    def test_voice_session_update_is_locked(self, db_session: Session) -> None:
        """Test updating is_locked field."""
        result = db_session.execute(
            select(Lobby).where(Lobby.lobby_channel_id == "456")
        )
        lobby = result.scalar_one()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )
        db_session.add(session)
        db_session.commit()

        session.is_locked = True
        db_session.commit()

        result = db_session.execute(
            select(VoiceSession).where(VoiceSession.channel_id == "789")
        )
        found = result.scalar_one()
        assert found.is_locked is True
