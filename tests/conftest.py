"""Shared pytest fixtures."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database.models import Base, Lobby


@pytest.fixture
def db_session() -> Session:
    """Create an in-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        # Create a test lobby
        lobby = Lobby(guild_id="123456789", lobby_channel_id="987654321")
        session.add(lobby)
        session.commit()
        yield session
