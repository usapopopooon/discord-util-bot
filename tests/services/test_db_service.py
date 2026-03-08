"""Tests for database service."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.constants import DEFAULT_TEST_DATABASE_URL
from src.database.models import Base
from src.services.db_service import (
    add_role_panel_item,
    add_voice_session_member,
    claim_autoban_log,
    claim_ban_log,
    claim_event,
    claim_join_role_assignment,
    cleanup_expired_events,
    clear_bump_reminder,
    create_autoban_log,
    create_autoban_rule,
    create_ban_log,
    create_join_role_assignment,
    create_join_role_config,
    create_lobby,
    create_role_panel,
    create_sticky_message,
    create_voice_session,
    delete_autoban_rule,
    delete_bump_config,
    delete_bump_reminders_by_guild,
    delete_discord_channel,
    delete_discord_channels_by_guild,
    delete_discord_guild,
    delete_discord_role,
    delete_discord_roles_by_guild,
    delete_intro_posts_by_guild,
    delete_join_role_assignment,
    delete_join_role_config,
    delete_lobbies_by_guild,
    delete_lobby,
    delete_role_panel,
    delete_role_panel_by_message_id,
    delete_role_panels_by_channel,
    delete_role_panels_by_guild,
    delete_sticky_message,
    delete_sticky_messages_by_guild,
    delete_voice_session,
    delete_voice_sessions_by_guild,
    get_all_autoban_configs,
    get_all_autoban_logs,
    get_all_autoban_rules,
    get_all_bump_configs,
    get_all_discord_guilds,
    get_all_lobbies,
    get_all_role_panels,
    get_all_sticky_messages,
    get_all_voice_sessions,
    get_autoban_config,
    get_autoban_logs_by_guild,
    get_autoban_rule,
    get_autoban_rules_by_guild,
    get_ban_logs,
    get_bot_activity,
    get_bump_config,
    get_bump_reminder,
    get_discord_channels_by_guild,
    get_discord_roles_by_guild,
    get_due_bump_reminders,
    get_enabled_autoban_rules_by_guild,
    get_enabled_join_role_configs,
    get_expired_join_role_assignments,
    get_join_role_configs,
    get_lobbies_by_guild,
    get_lobby_by_channel_id,
    get_role_panel,
    get_role_panel_by_message_id,
    get_role_panel_item_by_emoji,
    get_role_panel_items,
    get_role_panels_by_channel,
    get_role_panels_by_guild,
    get_sticky_message,
    get_voice_session,
    get_voice_session_members_ordered,
    has_intro_post,
    record_intro_post,
    remove_role_panel_item,
    remove_voice_session_member,
    toggle_autoban_rule,
    toggle_bump_reminder,
    toggle_join_role_config,
    update_autoban_rule,
    update_bump_reminder_role,
    update_role_panel,
    update_sticky_message_id,
    update_voice_session,
    upsert_autoban_config,
    upsert_bot_activity,
    upsert_bump_config,
    upsert_bump_reminder,
    upsert_discord_channel,
    upsert_discord_guild,
    upsert_discord_role,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    DEFAULT_TEST_DATABASE_URL,
)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """PostgreSQL テスト DB のセッションを提供する。"""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


class TestLobbyOperations:
    """Tests for lobby database operations."""

    async def test_create_lobby(self, db_session: AsyncSession) -> None:
        """Test creating a lobby."""
        lobby = await create_lobby(
            db_session,
            guild_id="123",
            lobby_channel_id="456",
            category_id="789",
            default_user_limit=10,
        )
        assert lobby.id is not None
        assert lobby.guild_id == "123"
        assert lobby.lobby_channel_id == "456"
        assert lobby.category_id == "789"
        assert lobby.default_user_limit == 10

    async def test_get_lobby_by_channel_id(self, db_session: AsyncSession) -> None:
        """Test getting a lobby by channel ID."""
        await create_lobby(db_session, guild_id="123", lobby_channel_id="456")

        lobby = await get_lobby_by_channel_id(db_session, "456")
        assert lobby is not None
        assert lobby.guild_id == "123"

    async def test_get_lobby_by_channel_id_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting a non-existent lobby."""
        lobby = await get_lobby_by_channel_id(db_session, "nonexistent")
        assert lobby is None

    async def test_get_lobbies_by_guild(self, db_session: AsyncSession) -> None:
        """Test getting all lobbies for a guild."""
        await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        await create_lobby(db_session, guild_id="123", lobby_channel_id="789")
        await create_lobby(db_session, guild_id="999", lobby_channel_id="111")

        lobbies = await get_lobbies_by_guild(db_session, "123")
        assert len(lobbies) == 2

    async def test_delete_lobby(self, db_session: AsyncSession) -> None:
        """Test deleting a lobby."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")

        result = await delete_lobby(db_session, lobby.id)
        assert result is True

        found = await get_lobby_by_channel_id(db_session, "456")
        assert found is None

    async def test_delete_lobby_not_found(self, db_session: AsyncSession) -> None:
        """Test deleting a non-existent lobby."""
        result = await delete_lobby(db_session, 99999)
        assert result is False


class TestVoiceSessionOperations:
    """Tests for voice session database operations."""

    async def test_create_voice_session(self, db_session: AsyncSession) -> None:
        """Test creating a voice session."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")

        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
            user_limit=5,
        )

        assert session.id is not None
        assert session.channel_id == "789"
        assert session.owner_id == "111"
        assert session.name == "Test Channel"
        assert session.user_limit == 5

    async def test_get_voice_session(self, db_session: AsyncSession) -> None:
        """Test getting a voice session."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        found = await get_voice_session(db_session, "789")
        assert found is not None
        assert found.owner_id == "111"

    async def test_get_voice_session_not_found(self, db_session: AsyncSession) -> None:
        """Test getting a non-existent voice session."""
        found = await get_voice_session(db_session, "nonexistent")
        assert found is None

    async def test_get_all_voice_sessions(self, db_session: AsyncSession) -> None:
        """Test getting all voice sessions."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Channel 1",
        )
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="790",
            owner_id="222",
            name="Channel 2",
        )

        sessions = await get_all_voice_sessions(db_session)
        assert len(sessions) == 2

    async def test_update_voice_session(self, db_session: AsyncSession) -> None:
        """Test updating a voice session."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        updated = await update_voice_session(
            db_session,
            session,
            name="New Name",
            user_limit=10,
            is_locked=True,
            is_hidden=True,
            owner_id="222",
        )

        assert updated.name == "New Name"
        assert updated.user_limit == 10
        assert updated.is_locked is True
        assert updated.is_hidden is True
        assert updated.owner_id == "222"

    async def test_update_voice_session_name_only(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating only the name leaves other fields unchanged."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Original",
            user_limit=5,
        )

        updated = await update_voice_session(db_session, session, name="Renamed")

        assert updated.name == "Renamed"
        assert updated.user_limit == 5
        assert updated.is_locked is False
        assert updated.is_hidden is False
        assert updated.owner_id == "111"

    async def test_update_voice_session_no_params(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating with no parameters changes nothing."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Unchanged",
        )

        updated = await update_voice_session(db_session, session)

        assert updated.name == "Unchanged"
        assert updated.owner_id == "111"
        assert updated.is_locked is False
        assert updated.is_hidden is False

    async def test_delete_voice_session(self, db_session: AsyncSession) -> None:
        """Test deleting a voice session."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        result = await delete_voice_session(db_session, "789")
        assert result is True

        found = await get_voice_session(db_session, "789")
        assert found is None

    async def test_delete_voice_session_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting a non-existent voice session."""
        result = await delete_voice_session(db_session, "nonexistent")
        assert result is False

    async def test_voice_session_default_values(self, db_session: AsyncSession) -> None:
        """Test that default values are set correctly."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        assert session.is_locked is False
        assert session.is_hidden is False
        assert session.user_limit == 0


class TestVoiceSessionMemberOperations:
    """Tests for voice session member database operations."""

    async def test_add_voice_session_member(self, db_session: AsyncSession) -> None:
        """Test adding a member to a voice session."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        member = await add_voice_session_member(db_session, voice_session.id, "222")

        assert member.id is not None
        assert member.voice_session_id == voice_session.id
        assert member.user_id == "222"
        assert member.joined_at is not None

    async def test_add_voice_session_member_existing(
        self, db_session: AsyncSession
    ) -> None:
        """Test adding an existing member returns the existing record."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        # Add member first time
        member1 = await add_voice_session_member(db_session, voice_session.id, "222")

        # Add same member again
        member2 = await add_voice_session_member(db_session, voice_session.id, "222")

        # Should return same record (idempotent)
        assert member1.id == member2.id
        assert member1.joined_at == member2.joined_at

    async def test_remove_voice_session_member(self, db_session: AsyncSession) -> None:
        """Test removing a member from a voice session."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        await add_voice_session_member(db_session, voice_session.id, "222")

        result = await remove_voice_session_member(db_session, voice_session.id, "222")
        assert result is True

        # Verify member is gone
        members = await get_voice_session_members_ordered(db_session, voice_session.id)
        assert len(members) == 0

    async def test_remove_voice_session_member_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test removing a non-existent member returns False."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        result = await remove_voice_session_member(
            db_session, voice_session.id, "nonexistent"
        )
        assert result is False

    async def test_get_voice_session_members_ordered(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting members ordered by join time."""
        import asyncio

        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        # Add members with slight delays to ensure different join times
        await add_voice_session_member(db_session, voice_session.id, "first")
        await asyncio.sleep(0.01)
        await add_voice_session_member(db_session, voice_session.id, "second")
        await asyncio.sleep(0.01)
        await add_voice_session_member(db_session, voice_session.id, "third")

        members = await get_voice_session_members_ordered(db_session, voice_session.id)

        assert len(members) == 3
        assert members[0].user_id == "first"
        assert members[1].user_id == "second"
        assert members[2].user_id == "third"

    async def test_get_voice_session_members_ordered_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting members from empty session returns empty list."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        members = await get_voice_session_members_ordered(db_session, voice_session.id)

        assert members == []

    async def test_voice_session_members_cascade_delete(
        self, db_session: AsyncSession
    ) -> None:
        """Test that members are deleted when voice session is deleted."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        await add_voice_session_member(db_session, voice_session.id, "222")
        await add_voice_session_member(db_session, voice_session.id, "333")

        # Delete the voice session
        await delete_voice_session(db_session, "789")

        # Members should be automatically deleted via CASCADE
        # We can't query directly since voice_session is gone,
        # but we verify no errors occurred during cascade delete


class TestBumpReminderOperations:
    """Tests for bump reminder database operations."""

    async def test_upsert_bump_reminder_create(self, db_session: AsyncSession) -> None:
        """Test creating a new bump reminder."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        reminder = await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        assert reminder.id is not None
        assert reminder.guild_id == "123"
        assert reminder.channel_id == "456"
        assert reminder.service_name == "DISBOARD"
        assert reminder.remind_at == remind_at

    async def test_upsert_bump_reminder_update(self, db_session: AsyncSession) -> None:
        """Test updating an existing bump reminder for same guild+service."""
        from datetime import UTC, datetime, timedelta

        remind_at_1 = datetime.now(UTC) + timedelta(hours=2)
        remind_at_2 = datetime.now(UTC) + timedelta(hours=4)

        # Create first reminder
        reminder1 = await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at_1,
        )

        # Upsert with new time (same guild+service should update)
        reminder2 = await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="789",  # Different channel
            service_name="DISBOARD",
            remind_at=remind_at_2,
        )

        # Should be same record (updated)
        assert reminder1.id == reminder2.id
        assert reminder2.channel_id == "789"
        assert reminder2.remind_at == remind_at_2

    async def test_upsert_bump_reminder_different_services(
        self, db_session: AsyncSession
    ) -> None:
        """Test that different services create separate reminders."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        reminder1 = await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        reminder2 = await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="ディス速報",
            remind_at=remind_at,
        )

        # Should be different records
        assert reminder1.id != reminder2.id

    async def test_get_due_bump_reminders(self, db_session: AsyncSession) -> None:
        """Test getting reminders that are due."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)

        # Past reminder (should be returned)
        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=now - timedelta(minutes=5),
        )

        # Future reminder (should not be returned)
        await upsert_bump_reminder(
            db_session,
            guild_id="456",
            channel_id="789",
            service_name="ディス速報",
            remind_at=now + timedelta(hours=1),
        )

        due = await get_due_bump_reminders(db_session, now)

        assert len(due) == 1
        assert due[0].guild_id == "123"
        assert due[0].service_name == "DISBOARD"

    async def test_get_due_bump_reminders_empty(self, db_session: AsyncSession) -> None:
        """Test getting due reminders when none are due."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)

        # Only future reminders
        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=now + timedelta(hours=2),
        )

        due = await get_due_bump_reminders(db_session, now)

        assert due == []

    async def test_clear_bump_reminder(self, db_session: AsyncSession) -> None:
        """Test clearing a bump reminder (sets remind_at to None)."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        reminder = await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        result = await clear_bump_reminder(db_session, reminder.id)
        assert result is True

        # Verify remind_at is cleared (no due reminders)
        due = await get_due_bump_reminders(
            db_session, datetime.now(UTC) + timedelta(hours=3)
        )
        assert due == []

    async def test_clear_bump_reminder_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test clearing a non-existent bump reminder."""
        result = await clear_bump_reminder(db_session, 99999)
        assert result is False

    async def test_toggle_bump_reminder(self, db_session: AsyncSession) -> None:
        """Test toggling bump reminder enabled state."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        # Create reminder (default is_enabled=True)
        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        # Toggle to disabled
        new_state = await toggle_bump_reminder(db_session, "123", "DISBOARD")
        assert new_state is False

        # Toggle back to enabled
        new_state = await toggle_bump_reminder(db_session, "123", "DISBOARD")
        assert new_state is True

    async def test_toggle_bump_reminder_creates_if_not_exists(
        self, db_session: AsyncSession
    ) -> None:
        """Test toggle creates disabled reminder if not exists."""
        # Toggle non-existent reminder
        new_state = await toggle_bump_reminder(db_session, "999", "DISBOARD")
        assert new_state is False

    async def test_get_due_bump_reminders_ignores_disabled(
        self, db_session: AsyncSession
    ) -> None:
        """Test that disabled reminders are not returned as due."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)

        # Create reminder
        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=now - timedelta(minutes=5),
        )

        # Disable it
        await toggle_bump_reminder(db_session, "123", "DISBOARD")

        # Should not be returned
        due = await get_due_bump_reminders(db_session, now)
        assert due == []

    async def test_get_bump_reminder(self, db_session: AsyncSession) -> None:
        """Test getting a bump reminder by guild_id and service_name."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        reminder = await get_bump_reminder(db_session, "123", "DISBOARD")

        assert reminder is not None
        assert reminder.guild_id == "123"
        assert reminder.service_name == "DISBOARD"

    async def test_get_bump_reminder_not_found(self, db_session: AsyncSession) -> None:
        """Test getting a non-existent bump reminder."""
        reminder = await get_bump_reminder(db_session, "nonexistent", "DISBOARD")
        assert reminder is None

    async def test_update_bump_reminder_role(self, db_session: AsyncSession) -> None:
        """Test updating the notification role for a bump reminder."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        # Update role
        result = await update_bump_reminder_role(db_session, "123", "DISBOARD", "999")
        assert result is True

        # Verify role was updated
        reminder = await get_bump_reminder(db_session, "123", "DISBOARD")
        assert reminder is not None
        assert reminder.role_id == "999"

    async def test_update_bump_reminder_role_reset_to_default(
        self, db_session: AsyncSession
    ) -> None:
        """Test resetting the notification role to default (None)."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        # Set a custom role first
        await update_bump_reminder_role(db_session, "123", "DISBOARD", "999")

        # Reset to default
        result = await update_bump_reminder_role(db_session, "123", "DISBOARD", None)
        assert result is True

        # Verify role was reset
        reminder = await get_bump_reminder(db_session, "123", "DISBOARD")
        assert reminder is not None
        assert reminder.role_id is None

    async def test_update_bump_reminder_role_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating role for a non-existent reminder."""
        result = await update_bump_reminder_role(
            db_session, "nonexistent", "DISBOARD", "999"
        )
        assert result is False


class TestBumpConfigOperations:
    """Tests for bump config database operations."""

    async def test_upsert_bump_config_create(self, db_session: AsyncSession) -> None:
        """Test creating a new bump config."""
        config = await upsert_bump_config(
            db_session,
            guild_id="123",
            channel_id="456",
        )

        assert config.guild_id == "123"
        assert config.channel_id == "456"
        assert config.created_at is not None

    async def test_upsert_bump_config_update(self, db_session: AsyncSession) -> None:
        """Test updating an existing bump config."""
        # Create first config
        config1 = await upsert_bump_config(
            db_session,
            guild_id="123",
            channel_id="456",
        )
        original_created_at = config1.created_at

        # Upsert with new channel (same guild should update)
        config2 = await upsert_bump_config(
            db_session,
            guild_id="123",
            channel_id="789",
        )

        # Should be same record (updated channel, same guild_id)
        assert config2.guild_id == "123"
        assert config2.channel_id == "789"
        # created_at should remain the same
        assert config2.created_at == original_created_at

    async def test_upsert_bump_config_different_guilds(
        self, db_session: AsyncSession
    ) -> None:
        """Test that different guilds create separate configs."""
        config1 = await upsert_bump_config(
            db_session,
            guild_id="123",
            channel_id="456",
        )

        config2 = await upsert_bump_config(
            db_session,
            guild_id="999",
            channel_id="789",
        )

        # Should be different records (different guilds)
        assert config1.guild_id != config2.guild_id

    async def test_get_bump_config(self, db_session: AsyncSession) -> None:
        """Test getting a bump config by guild_id."""
        await upsert_bump_config(
            db_session,
            guild_id="123",
            channel_id="456",
        )

        config = await get_bump_config(db_session, "123")

        assert config is not None
        assert config.guild_id == "123"
        assert config.channel_id == "456"

    async def test_get_bump_config_not_found(self, db_session: AsyncSession) -> None:
        """Test getting a non-existent bump config."""
        config = await get_bump_config(db_session, "nonexistent")
        assert config is None

    async def test_delete_bump_config(self, db_session: AsyncSession) -> None:
        """Test deleting a bump config."""
        await upsert_bump_config(
            db_session,
            guild_id="123",
            channel_id="456",
        )

        result = await delete_bump_config(db_session, "123")
        assert result is True

        # Verify config is deleted
        config = await get_bump_config(db_session, "123")
        assert config is None

    async def test_delete_bump_config_not_found(self, db_session: AsyncSession) -> None:
        """Test deleting a non-existent bump config."""
        result = await delete_bump_config(db_session, "nonexistent")
        assert result is False


class TestStickyMessageOperations:
    """Tests for sticky message database operations."""

    async def test_create_sticky_message(self, db_session: AsyncSession) -> None:
        """Test creating a new sticky message."""
        sticky = await create_sticky_message(
            db_session,
            channel_id="456",
            guild_id="123",
            title="Test Title",
            description="Test Description",
            color=0xFF0000,
            cooldown_seconds=10,
        )

        assert sticky.channel_id == "456"
        assert sticky.guild_id == "123"
        assert sticky.title == "Test Title"
        assert sticky.description == "Test Description"
        assert sticky.color == 0xFF0000
        assert sticky.cooldown_seconds == 10
        assert sticky.message_id is None
        assert sticky.last_posted_at is None
        assert sticky.created_at is not None

    async def test_create_sticky_message_updates_existing(
        self, db_session: AsyncSession
    ) -> None:
        """Test that creating a sticky message updates existing one."""
        await create_sticky_message(
            db_session,
            channel_id="456",
            guild_id="123",
            title="Original Title",
            description="Original Description",
        )

        sticky = await create_sticky_message(
            db_session,
            channel_id="456",
            guild_id="123",
            title="Updated Title",
            description="Updated Description",
            color=0x00FF00,
        )

        assert sticky.title == "Updated Title"
        assert sticky.description == "Updated Description"
        assert sticky.color == 0x00FF00

    async def test_get_sticky_message(self, db_session: AsyncSession) -> None:
        """Test getting a sticky message by channel_id."""
        await create_sticky_message(
            db_session,
            channel_id="456",
            guild_id="123",
            title="Test Title",
            description="Test Description",
        )

        sticky = await get_sticky_message(db_session, "456")

        assert sticky is not None
        assert sticky.channel_id == "456"
        assert sticky.title == "Test Title"

    async def test_get_sticky_message_not_found(self, db_session: AsyncSession) -> None:
        """Test getting a non-existent sticky message."""
        sticky = await get_sticky_message(db_session, "nonexistent")
        assert sticky is None

    async def test_update_sticky_message_id(self, db_session: AsyncSession) -> None:
        """Test updating the message_id and last_posted_at."""
        from datetime import UTC, datetime

        await create_sticky_message(
            db_session,
            channel_id="456",
            guild_id="123",
            title="Test Title",
            description="Test Description",
        )

        now = datetime.now(UTC)
        result = await update_sticky_message_id(
            db_session, "456", "999", last_posted_at=now
        )
        assert result is True

        sticky = await get_sticky_message(db_session, "456")
        assert sticky is not None
        assert sticky.message_id == "999"
        assert sticky.last_posted_at is not None

    async def test_update_sticky_message_id_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating message_id for a non-existent sticky."""
        result = await update_sticky_message_id(db_session, "nonexistent", "999")
        assert result is False

    async def test_delete_sticky_message(self, db_session: AsyncSession) -> None:
        """Test deleting a sticky message."""
        await create_sticky_message(
            db_session,
            channel_id="456",
            guild_id="123",
            title="Test Title",
            description="Test Description",
        )

        result = await delete_sticky_message(db_session, "456")
        assert result is True

        sticky = await get_sticky_message(db_session, "456")
        assert sticky is None

    async def test_delete_sticky_message_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting a non-existent sticky message."""
        result = await delete_sticky_message(db_session, "nonexistent")
        assert result is False

    async def test_get_all_sticky_messages(self, db_session: AsyncSession) -> None:
        """Test getting all sticky messages."""
        await create_sticky_message(
            db_session,
            channel_id="456",
            guild_id="123",
            title="Title 1",
            description="Description 1",
        )

        await create_sticky_message(
            db_session,
            channel_id="789",
            guild_id="123",
            title="Title 2",
            description="Description 2",
        )

        stickies = await get_all_sticky_messages(db_session)
        assert len(stickies) == 2

    async def test_get_all_sticky_messages_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting all sticky messages when there are none."""
        stickies = await get_all_sticky_messages(db_session)
        assert len(stickies) == 0

    async def test_create_sticky_message_with_embed_type(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a sticky message with embed type."""
        sticky = await create_sticky_message(
            db_session,
            channel_id="456",
            guild_id="123",
            title="Test Title",
            description="Test Description",
            message_type="embed",
        )

        assert sticky.message_type == "embed"

    async def test_create_sticky_message_with_text_type(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a sticky message with text type."""
        sticky = await create_sticky_message(
            db_session,
            channel_id="456",
            guild_id="123",
            title="",
            description="Just plain text",
            message_type="text",
        )

        assert sticky.message_type == "text"
        assert sticky.title == ""
        assert sticky.description == "Just plain text"

    async def test_create_sticky_message_default_type_is_embed(
        self, db_session: AsyncSession
    ) -> None:
        """Test that default message_type is embed."""
        sticky = await create_sticky_message(
            db_session,
            channel_id="456",
            guild_id="123",
            title="Test Title",
            description="Test Description",
        )

        assert sticky.message_type == "embed"

    async def test_update_sticky_message_type(self, db_session: AsyncSession) -> None:
        """Test that updating a sticky message preserves and can change type."""
        # 最初に embed タイプで作成
        await create_sticky_message(
            db_session,
            channel_id="456",
            guild_id="123",
            title="Original Title",
            description="Original Description",
            message_type="embed",
        )

        # text タイプで更新
        sticky = await create_sticky_message(
            db_session,
            channel_id="456",
            guild_id="123",
            title="",
            description="Updated text content",
            message_type="text",
        )

        assert sticky.message_type == "text"
        assert sticky.description == "Updated text content"


class TestDiscordRoleOperations:
    """Tests for Discord role cache database operations."""

    async def test_upsert_discord_role_create(self, db_session: AsyncSession) -> None:
        """Test creating a new Discord role."""
        role = await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name="Test Role",
            color=0xFF0000,
            position=5,
        )

        assert role.id is not None
        assert role.guild_id == "123"
        assert role.role_id == "456"
        assert role.role_name == "Test Role"
        assert role.color == 0xFF0000
        assert role.position == 5

    async def test_upsert_discord_role_update(self, db_session: AsyncSession) -> None:
        """Test updating an existing Discord role."""
        # Create first
        await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name="Original Name",
            color=0xFF0000,
            position=5,
        )

        # Update
        role = await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name="Updated Name",
            color=0x00FF00,
            position=10,
        )

        assert role.role_name == "Updated Name"
        assert role.color == 0x00FF00
        assert role.position == 10

    async def test_upsert_discord_role_different_guilds(
        self, db_session: AsyncSession
    ) -> None:
        """Test that same role_id in different guilds are separate records."""
        role1 = await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name="Role in Guild 1",
        )

        role2 = await upsert_discord_role(
            db_session,
            guild_id="789",
            role_id="456",
            role_name="Role in Guild 2",
        )

        assert role1.id != role2.id
        assert role1.guild_id != role2.guild_id

    async def test_delete_discord_role(self, db_session: AsyncSession) -> None:
        """Test deleting a Discord role."""
        await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name="Test Role",
        )

        result = await delete_discord_role(db_session, "123", "456")
        assert result is True

        # Verify role is deleted
        roles = await get_discord_roles_by_guild(db_session, "123")
        assert len(roles) == 0

    async def test_delete_discord_role_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting a non-existent Discord role."""
        result = await delete_discord_role(db_session, "nonexistent", "456")
        assert result is False

    async def test_delete_discord_roles_by_guild(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting all roles for a guild."""
        # Create multiple roles for a guild
        await upsert_discord_role(
            db_session, guild_id="123", role_id="1", role_name="Role 1"
        )
        await upsert_discord_role(
            db_session, guild_id="123", role_id="2", role_name="Role 2"
        )
        await upsert_discord_role(
            db_session, guild_id="123", role_id="3", role_name="Role 3"
        )
        # Create a role in a different guild
        await upsert_discord_role(
            db_session, guild_id="999", role_id="4", role_name="Other Guild Role"
        )

        count = await delete_discord_roles_by_guild(db_session, "123")
        assert count == 3

        # Verify all roles for guild 123 are deleted
        roles = await get_discord_roles_by_guild(db_session, "123")
        assert len(roles) == 0

        # Verify role in other guild still exists
        other_roles = await get_discord_roles_by_guild(db_session, "999")
        assert len(other_roles) == 1

    async def test_delete_discord_roles_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting roles for a guild with no roles."""
        count = await delete_discord_roles_by_guild(db_session, "nonexistent")
        assert count == 0

    async def test_get_discord_roles_by_guild(self, db_session: AsyncSession) -> None:
        """Test getting all roles for a guild sorted by position."""
        # Create roles with different positions
        await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="1",
            role_name="Low Role",
            position=1,
        )
        await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="2",
            role_name="High Role",
            position=10,
        )
        await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="3",
            role_name="Medium Role",
            position=5,
        )

        roles = await get_discord_roles_by_guild(db_session, "123")

        assert len(roles) == 3
        # Should be sorted by position descending (highest first)
        assert roles[0].role_name == "High Role"
        assert roles[1].role_name == "Medium Role"
        assert roles[2].role_name == "Low Role"

    async def test_get_discord_roles_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting roles for a guild with no roles."""
        roles = await get_discord_roles_by_guild(db_session, "nonexistent")
        assert roles == []

    async def test_upsert_discord_role_with_default_values(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a role with default color and position."""
        role = await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name="Default Role",
            # color と position は省略（デフォルト値 0）
        )

        assert role.color == 0
        assert role.position == 0

    async def test_upsert_discord_role_preserves_id_on_update(
        self, db_session: AsyncSession
    ) -> None:
        """Test that updating a role preserves the same ID."""
        role1 = await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name="Original",
        )
        original_id = role1.id

        role2 = await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name="Updated",
        )

        assert role2.id == original_id

    async def test_delete_discord_role_wrong_guild(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting a role with wrong guild_id returns False."""
        await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name="Test Role",
        )

        # 異なるギルド ID で削除を試みる
        result = await delete_discord_role(db_session, "999", "456")
        assert result is False

        # 元のロールはまだ存在する
        roles = await get_discord_roles_by_guild(db_session, "123")
        assert len(roles) == 1

    async def test_get_discord_roles_by_guild_with_same_position(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting roles with same position (deterministic ordering)."""
        await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="1",
            role_name="Role A",
            position=5,
        )
        await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="2",
            role_name="Role B",
            position=5,
        )

        roles = await get_discord_roles_by_guild(db_session, "123")
        assert len(roles) == 2
        # position が同じ場合でも両方取得できる

    async def test_upsert_discord_role_with_zero_color(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a role with color=0 (black/default)."""
        role = await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name="No Color Role",
            color=0,
            position=5,
        )

        assert role.color == 0

    async def test_upsert_discord_role_with_max_color(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a role with maximum color value."""
        role = await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name="White Role",
            color=0xFFFFFF,
            position=5,
        )

        assert role.color == 0xFFFFFF

    async def test_upsert_discord_role_with_unicode_name(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a role with unicode characters in name."""
        role = await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name="日本語ロール 🎮",
        )

        assert role.role_name == "日本語ロール 🎮"

    async def test_upsert_discord_role_with_long_name(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a role with a long name."""
        long_name = "A" * 100  # Discord allows up to 100 chars
        role = await upsert_discord_role(
            db_session,
            guild_id="123",
            role_id="456",
            role_name=long_name,
        )

        assert role.role_name == long_name
        assert len(role.role_name) == 100


class TestDiscordGuildOperations:
    """Tests for Discord guild cache database operations."""

    async def test_upsert_discord_guild_create(self, db_session: AsyncSession) -> None:
        """Test creating a new Discord guild."""
        guild = await upsert_discord_guild(
            db_session,
            guild_id="123456789",
            guild_name="Test Server",
            icon_hash="abc123",
            member_count=100,
        )

        assert guild.guild_id == "123456789"
        assert guild.guild_name == "Test Server"
        assert guild.icon_hash == "abc123"
        assert guild.member_count == 100
        assert guild.updated_at is not None

    async def test_upsert_discord_guild_update(self, db_session: AsyncSession) -> None:
        """Test updating an existing Discord guild."""
        await upsert_discord_guild(
            db_session,
            guild_id="123456789",
            guild_name="Original Name",
            member_count=50,
        )

        guild = await upsert_discord_guild(
            db_session,
            guild_id="123456789",
            guild_name="Updated Name",
            icon_hash="new_hash",
            member_count=200,
        )

        assert guild.guild_name == "Updated Name"
        assert guild.icon_hash == "new_hash"
        assert guild.member_count == 200

    async def test_upsert_discord_guild_with_defaults(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a guild with default values."""
        guild = await upsert_discord_guild(
            db_session,
            guild_id="123456789",
            guild_name="Test Server",
        )

        assert guild.icon_hash is None
        assert guild.member_count == 0

    async def test_delete_discord_guild(self, db_session: AsyncSession) -> None:
        """Test deleting a Discord guild."""
        await upsert_discord_guild(
            db_session,
            guild_id="123456789",
            guild_name="Test Server",
        )

        result = await delete_discord_guild(db_session, "123456789")
        assert result is True

        guilds = await get_all_discord_guilds(db_session)
        assert len(guilds) == 0

    async def test_delete_discord_guild_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting a non-existent Discord guild."""
        result = await delete_discord_guild(db_session, "nonexistent")
        assert result is False

    async def test_get_all_discord_guilds(self, db_session: AsyncSession) -> None:
        """Test getting all Discord guilds."""
        await upsert_discord_guild(
            db_session,
            guild_id="111",
            guild_name="Server A",
        )
        await upsert_discord_guild(
            db_session,
            guild_id="222",
            guild_name="Server B",
        )
        await upsert_discord_guild(
            db_session,
            guild_id="333",
            guild_name="Server C",
        )

        guilds = await get_all_discord_guilds(db_session)
        assert len(guilds) == 3

    async def test_get_all_discord_guilds_empty(self, db_session: AsyncSession) -> None:
        """Test getting all guilds when there are none."""
        guilds = await get_all_discord_guilds(db_session)
        assert guilds == []

    async def test_upsert_discord_guild_with_unicode_name(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a guild with unicode characters in name."""
        guild = await upsert_discord_guild(
            db_session,
            guild_id="123456789",
            guild_name="日本語サーバー 🎮",
        )

        assert guild.guild_name == "日本語サーバー 🎮"


class TestDiscordChannelOperations:
    """Tests for Discord channel cache database operations."""

    async def test_upsert_channel_create(self, db_session: AsyncSession) -> None:
        """Test creating a new Discord channel."""
        channel = await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="456",
            channel_name="general",
            channel_type=0,
            position=1,
            category_id="789",
        )

        assert channel.id is not None
        assert channel.guild_id == "123"
        assert channel.channel_id == "456"
        assert channel.channel_name == "general"
        assert channel.channel_type == 0
        assert channel.position == 1
        assert channel.category_id == "789"
        assert channel.updated_at is not None

    async def test_upsert_channel_update(self, db_session: AsyncSession) -> None:
        """Test updating an existing Discord channel."""
        await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="456",
            channel_name="original-channel",
            channel_type=0,
            position=1,
        )

        channel = await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="456",
            channel_name="renamed-channel",
            channel_type=0,
            position=5,
            category_id="999",
        )

        assert channel.channel_name == "renamed-channel"
        assert channel.position == 5
        assert channel.category_id == "999"

    async def test_upsert_discord_channel_with_defaults(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a channel with default values."""
        channel = await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="456",
            channel_name="test-channel",
        )

        assert channel.channel_type == 0
        assert channel.position == 0
        assert channel.category_id is None

    async def test_upsert_discord_channel_different_guilds(
        self, db_session: AsyncSession
    ) -> None:
        """Test that same channel_id in different guilds are separate records."""
        channel1 = await upsert_discord_channel(
            db_session,
            guild_id="111",
            channel_id="456",
            channel_name="channel-in-guild-1",
        )

        channel2 = await upsert_discord_channel(
            db_session,
            guild_id="222",
            channel_id="456",
            channel_name="channel-in-guild-2",
        )

        assert channel1.id != channel2.id
        assert channel1.guild_id != channel2.guild_id

    async def test_delete_discord_channel(self, db_session: AsyncSession) -> None:
        """Test deleting a Discord channel."""
        await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="456",
            channel_name="test-channel",
        )

        result = await delete_discord_channel(db_session, "123", "456")
        assert result is True

        channels = await get_discord_channels_by_guild(db_session, "123")
        assert len(channels) == 0

    async def test_delete_discord_channel_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting a non-existent Discord channel."""
        result = await delete_discord_channel(db_session, "nonexistent", "456")
        assert result is False

    async def test_delete_discord_channels_by_guild(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting all channels for a guild."""
        await upsert_discord_channel(
            db_session, guild_id="123", channel_id="1", channel_name="channel-1"
        )
        await upsert_discord_channel(
            db_session, guild_id="123", channel_id="2", channel_name="channel-2"
        )
        await upsert_discord_channel(
            db_session, guild_id="123", channel_id="3", channel_name="channel-3"
        )
        await upsert_discord_channel(
            db_session,
            guild_id="999",
            channel_id="4",
            channel_name="other-guild-channel",
        )

        count = await delete_discord_channels_by_guild(db_session, "123")
        assert count == 3

        channels = await get_discord_channels_by_guild(db_session, "123")
        assert len(channels) == 0

        other_channels = await get_discord_channels_by_guild(db_session, "999")
        assert len(other_channels) == 1

    async def test_delete_discord_channels_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting channels for a guild with no channels."""
        count = await delete_discord_channels_by_guild(db_session, "nonexistent")
        assert count == 0

    async def test_get_discord_channels_by_guild(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting all channels for a guild sorted by position."""
        await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="1",
            channel_name="last-channel",
            position=10,
        )
        await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="2",
            channel_name="first-channel",
            position=1,
        )
        await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="3",
            channel_name="middle-channel",
            position=5,
        )

        channels = await get_discord_channels_by_guild(db_session, "123")

        assert len(channels) == 3
        # Should be sorted by position ascending
        assert channels[0].channel_name == "first-channel"
        assert channels[1].channel_name == "middle-channel"
        assert channels[2].channel_name == "last-channel"

    async def test_get_discord_channels_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting channels for a guild with no channels."""
        channels = await get_discord_channels_by_guild(db_session, "nonexistent")
        assert channels == []

    async def test_upsert_discord_channel_various_types(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating channels with various types."""
        # Text channel
        text_ch = await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="1",
            channel_name="text-channel",
            channel_type=0,
        )
        assert text_ch.channel_type == 0

        # Voice channel (for lobbies)
        voice_ch = await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="2",
            channel_name="voice-lobby",
            channel_type=2,
        )
        assert voice_ch.channel_type == 2

        # News/Announcement channel
        news_ch = await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="3",
            channel_name="announcement",
            channel_type=5,
        )
        assert news_ch.channel_type == 5

        # Forum channel
        forum_ch = await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="4",
            channel_name="forum",
            channel_type=15,
        )
        assert forum_ch.channel_type == 15

    async def test_upsert_discord_channel_with_unicode_name(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a channel with unicode characters in name."""
        channel = await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="456",
            channel_name="日本語チャンネル",
        )

        assert channel.channel_name == "日本語チャンネル"

    async def test_upsert_discord_channel_preserves_id_on_update(
        self, db_session: AsyncSession
    ) -> None:
        """Test that updating a channel preserves the same ID."""
        channel1 = await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="456",
            channel_name="original",
        )
        original_id = channel1.id

        channel2 = await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="456",
            channel_name="updated",
        )

        assert channel2.id == original_id

    async def test_delete_discord_channel_wrong_guild(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting a channel with wrong guild_id returns False."""
        await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="456",
            channel_name="test-channel",
        )

        result = await delete_discord_channel(db_session, "999", "456")
        assert result is False

        channels = await get_discord_channels_by_guild(db_session, "123")
        assert len(channels) == 1


class TestDiscordGuildSortingAndTimestamps:
    """Tests for Discord guild sorting and timestamp behavior."""

    async def test_get_all_discord_guilds_sorted_by_name(
        self, db_session: AsyncSession
    ) -> None:
        """Test that guilds are returned sorted by guild_name."""
        # Create guilds in non-alphabetical order
        await upsert_discord_guild(db_session, guild_id="1", guild_name="Zebra Server")
        await upsert_discord_guild(db_session, guild_id="2", guild_name="Alpha Server")
        await upsert_discord_guild(db_session, guild_id="3", guild_name="Middle Server")

        guilds = await get_all_discord_guilds(db_session)

        assert len(guilds) == 3
        assert guilds[0].guild_name == "Alpha Server"
        assert guilds[1].guild_name == "Middle Server"
        assert guilds[2].guild_name == "Zebra Server"

    async def test_upsert_discord_guild_updates_timestamp(
        self, db_session: AsyncSession
    ) -> None:
        """Test that updated_at is updated when guild is updated."""
        import asyncio

        guild1 = await upsert_discord_guild(
            db_session, guild_id="123", guild_name="Original"
        )
        original_timestamp = guild1.updated_at

        # Wait a bit to ensure timestamp difference
        await asyncio.sleep(0.01)

        guild2 = await upsert_discord_guild(
            db_session, guild_id="123", guild_name="Updated"
        )

        assert guild2.updated_at >= original_timestamp

    async def test_upsert_discord_channel_updates_timestamp(
        self, db_session: AsyncSession
    ) -> None:
        """Test that updated_at is updated when channel is updated."""
        import asyncio

        channel1 = await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="456",
            channel_name="original-channel",
        )
        original_timestamp = channel1.updated_at

        # Wait a bit to ensure timestamp difference
        await asyncio.sleep(0.01)

        channel2 = await upsert_discord_channel(
            db_session,
            guild_id="123",
            channel_id="456",
            channel_name="updated-channel",
        )

        assert channel2.updated_at >= original_timestamp


class TestRolePanelOperations:
    """Tests for role panel database operations."""

    async def test_create_role_panel_with_defaults(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a role panel with default values."""
        panel = await create_role_panel(
            db_session,
            guild_id="123456789",
            channel_id="987654321",
            panel_type="button",
            title="Test Panel",
        )

        assert panel.id is not None
        assert panel.guild_id == "123456789"
        assert panel.channel_id == "987654321"
        assert panel.panel_type == "button"
        assert panel.title == "Test Panel"
        assert panel.description is None
        assert panel.color is None
        assert panel.remove_reaction is False
        assert panel.use_embed is True  # Default value
        assert panel.message_id is None
        assert panel.created_at is not None

    async def test_create_role_panel_with_use_embed_true(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a role panel with use_embed=True."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Embed Panel",
            use_embed=True,
        )

        assert panel.use_embed is True

    async def test_create_role_panel_with_use_embed_false(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a role panel with use_embed=False."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Text Panel",
            use_embed=False,
        )

        assert panel.use_embed is False

    async def test_create_role_panel_reaction_type(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a reaction type role panel."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Reaction Panel",
            remove_reaction=True,
        )

        assert panel.panel_type == "reaction"
        assert panel.remove_reaction is True

    async def test_create_role_panel_with_all_fields(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a role panel with all fields specified."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Full Panel",
            description="This is a test panel",
            color=0x5865F2,
            remove_reaction=False,
            use_embed=False,
        )

        assert panel.title == "Full Panel"
        assert panel.description == "This is a test panel"
        assert panel.color == 0x5865F2
        assert panel.remove_reaction is False
        assert panel.use_embed is False

    async def test_get_role_panel(self, db_session: AsyncSession) -> None:
        """Test getting a role panel by ID."""
        created = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        panel = await get_role_panel(db_session, created.id)

        assert panel is not None
        assert panel.id == created.id
        assert panel.title == "Test Panel"

    async def test_get_role_panel_not_found(self, db_session: AsyncSession) -> None:
        """Test getting a non-existent role panel."""
        panel = await get_role_panel(db_session, 99999)
        assert panel is None

    async def test_get_role_panel_by_message_id(self, db_session: AsyncSession) -> None:
        """Test getting a role panel by message ID."""
        created = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        await update_role_panel(db_session, created, message_id="111222333")

        panel = await get_role_panel_by_message_id(db_session, "111222333")

        assert panel is not None
        assert panel.id == created.id
        assert panel.message_id == "111222333"

    async def test_get_role_panel_by_message_id_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting a role panel by non-existent message ID."""
        panel = await get_role_panel_by_message_id(db_session, "nonexistent")
        assert panel is None

    async def test_get_role_panels_by_guild(self, db_session: AsyncSession) -> None:
        """Test getting all role panels for a guild."""
        await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Panel 1",
        )
        await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="789",
            panel_type="reaction",
            title="Panel 2",
        )
        await create_role_panel(
            db_session,
            guild_id="999",
            channel_id="111",
            panel_type="button",
            title="Other Guild Panel",
        )

        panels = await get_role_panels_by_guild(db_session, "123")

        assert len(panels) == 2
        titles = [p.title for p in panels]
        assert "Panel 1" in titles
        assert "Panel 2" in titles

    async def test_get_role_panels_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting panels for a guild with no panels."""
        panels = await get_role_panels_by_guild(db_session, "nonexistent")
        assert panels == []

    async def test_get_role_panels_by_channel(self, db_session: AsyncSession) -> None:
        """Test getting all role panels for a channel."""
        await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Panel 1",
        )
        await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Panel 2",
        )
        await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="789",
            panel_type="button",
            title="Other Channel Panel",
        )

        panels = await get_role_panels_by_channel(db_session, "456")

        assert len(panels) == 2
        for panel in panels:
            assert panel.channel_id == "456"

    async def test_get_role_panels_by_channel_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting panels for a channel with no panels."""
        panels = await get_role_panels_by_channel(db_session, "nonexistent")
        assert panels == []

    async def test_get_all_role_panels(self, db_session: AsyncSession) -> None:
        """Test getting all role panels."""
        await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Panel 1",
        )
        await create_role_panel(
            db_session,
            guild_id="789",
            channel_id="012",
            panel_type="reaction",
            title="Panel 2",
        )

        panels = await get_all_role_panels(db_session)

        assert len(panels) == 2

    async def test_get_all_role_panels_empty(self, db_session: AsyncSession) -> None:
        """Test getting all panels when there are none."""
        panels = await get_all_role_panels(db_session)
        assert panels == []

    async def test_update_role_panel_message_id(self, db_session: AsyncSession) -> None:
        """Test updating a role panel's message ID."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        updated = await update_role_panel(db_session, panel, message_id="999888777")

        assert updated.message_id == "999888777"

    async def test_update_role_panel_title(self, db_session: AsyncSession) -> None:
        """Test updating a role panel's title."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Original Title",
        )

        updated = await update_role_panel(db_session, panel, title="New Title")

        assert updated.title == "New Title"

    async def test_update_role_panel_description(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating a role panel's description."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        updated = await update_role_panel(
            db_session, panel, description="New description"
        )

        assert updated.description == "New description"

    async def test_update_role_panel_color(self, db_session: AsyncSession) -> None:
        """Test updating a role panel's color."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        updated = await update_role_panel(db_session, panel, color=0xFF0000)

        assert updated.color == 0xFF0000

    async def test_update_role_panel_multiple_fields(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating multiple fields at once."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        updated = await update_role_panel(
            db_session,
            panel,
            message_id="123",
            title="Updated Title",
            description="Updated description",
            color=0x00FF00,
        )

        assert updated.message_id == "123"
        assert updated.title == "Updated Title"
        assert updated.description == "Updated description"
        assert updated.color == 0x00FF00

    async def test_update_role_panel_remove_reaction(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating a role panel's remove_reaction flag."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Reaction Panel",
            remove_reaction=False,
        )

        assert panel.remove_reaction is False

        updated = await update_role_panel(db_session, panel, remove_reaction=True)

        assert updated.remove_reaction is True

        # Toggle back
        updated2 = await update_role_panel(db_session, panel, remove_reaction=False)

        assert updated2.remove_reaction is False

    async def test_delete_role_panel(self, db_session: AsyncSession) -> None:
        """Test deleting a role panel."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        panel_id = panel.id

        result = await delete_role_panel(db_session, panel_id)

        assert result is True
        deleted = await get_role_panel(db_session, panel_id)
        assert deleted is None

    async def test_delete_role_panel_not_found(self, db_session: AsyncSession) -> None:
        """Test deleting a non-existent role panel."""
        result = await delete_role_panel(db_session, 99999)
        assert result is False

    async def test_create_role_panel_with_unicode_title(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a role panel with unicode characters in title."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="ロール選択 🎮",
            description="お好きなロールを選んでください",
        )

        assert panel.title == "ロール選択 🎮"
        assert panel.description == "お好きなロールを選んでください"


class TestRolePanelItemOperations:
    """Tests for role panel item database operations."""

    async def test_add_role_panel_item(self, db_session: AsyncSession) -> None:
        """Test adding an item to a role panel."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        item = await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id="111222333",
            emoji="🎮",
            label="Gamer",
            style="primary",
        )

        assert item.id is not None
        assert item.panel_id == panel.id
        assert item.role_id == "111222333"
        assert item.emoji == "🎮"
        assert item.label == "Gamer"
        assert item.style == "primary"
        assert item.position == 0

    async def test_add_role_panel_item_minimal(self, db_session: AsyncSession) -> None:
        """Test adding an item with minimal fields."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="reaction",
            title="Test Panel",
        )

        item = await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id="111222333",
            emoji="👍",
        )

        assert item.emoji == "👍"
        assert item.label is None
        assert item.style == "secondary"

    async def test_add_role_panel_item_auto_position(
        self, db_session: AsyncSession
    ) -> None:
        """Test that items get auto-incrementing positions."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        item1 = await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id="111",
            emoji="🎮",
        )
        item2 = await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id="222",
            emoji="🎵",
        )

        assert item1.position == 0
        assert item2.position == 1

    async def test_add_multiple_items(self, db_session: AsyncSession) -> None:
        """Test adding multiple items to a panel."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id="111", emoji="🎮"
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id="222", emoji="🎵"
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id="333", emoji="🎨"
        )

        items = await get_role_panel_items(db_session, panel.id)

        assert len(items) == 3
        # Items are added in order, sorted by position
        assert items[0].emoji == "🎮"
        assert items[1].emoji == "🎵"
        assert items[2].emoji == "🎨"

    async def test_get_role_panel_items(self, db_session: AsyncSession) -> None:
        """Test getting all items for a panel sorted by position."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        # Add items - they get auto-incrementing positions
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id="111", emoji="🎮"
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id="222", emoji="🎵"
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id="333", emoji="🎨"
        )

        items = await get_role_panel_items(db_session, panel.id)

        assert len(items) == 3
        # Should be sorted by position (auto-assigned 0, 1, 2)
        assert items[0].position == 0
        assert items[0].emoji == "🎮"
        assert items[1].position == 1
        assert items[1].emoji == "🎵"
        assert items[2].position == 2
        assert items[2].emoji == "🎨"

    async def test_get_role_panel_items_empty(self, db_session: AsyncSession) -> None:
        """Test getting items for a panel with no items."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        items = await get_role_panel_items(db_session, panel.id)

        assert items == []

    async def test_get_role_panel_item_by_emoji(self, db_session: AsyncSession) -> None:
        """Test getting an item by emoji."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id="111", emoji="🎮"
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id="222", emoji="🎵"
        )

        item = await get_role_panel_item_by_emoji(db_session, panel.id, "🎮")

        assert item is not None
        assert item.emoji == "🎮"
        assert item.role_id == "111"

    async def test_get_role_panel_item_by_emoji_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting an item by non-existent emoji."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        item = await get_role_panel_item_by_emoji(db_session, panel.id, "🎮")

        assert item is None

    async def test_remove_role_panel_item(self, db_session: AsyncSession) -> None:
        """Test removing an item from a panel."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id="111", emoji="🎮"
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id="222", emoji="🎵"
        )

        result = await remove_role_panel_item(db_session, panel.id, "🎮")

        assert result is True
        items = await get_role_panel_items(db_session, panel.id)
        assert len(items) == 1
        assert items[0].emoji == "🎵"

    async def test_remove_role_panel_item_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test removing a non-existent item."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        result = await remove_role_panel_item(db_session, panel.id, "🎮")

        assert result is False

    async def test_delete_panel_cascades_items(self, db_session: AsyncSession) -> None:
        """Test that deleting a panel also deletes its items."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id="111", emoji="🎮"
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id="222", emoji="🎵"
        )
        panel_id = panel.id

        await delete_role_panel(db_session, panel_id)

        # Items should be deleted with the panel
        items = await get_role_panel_items(db_session, panel_id)
        assert items == []

    async def test_add_role_panel_item_with_unicode_label(
        self, db_session: AsyncSession
    ) -> None:
        """Test adding an item with unicode characters in label."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        item = await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id="111",
            emoji="🎮",
            label="ゲーマー",
        )

        assert item.label == "ゲーマー"

    async def test_add_role_panel_item_with_all_styles(
        self, db_session: AsyncSession
    ) -> None:
        """Test adding items with all valid button styles."""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test Panel",
        )

        styles = ["primary", "secondary", "success", "danger"]
        emojis = ["🔵", "⚪", "🟢", "🔴"]

        for style, emoji in zip(styles, emojis, strict=False):
            item = await add_role_panel_item(
                db_session,
                panel_id=panel.id,
                role_id=f"111{style}",
                emoji=emoji,
                style=style,
            )
            assert item.style == style

        # Verify all items are saved
        items = await get_role_panel_items(db_session, panel.id)
        assert len(items) == 4
        assert {item.style for item in items} == set(styles)


# =============================================================================
# Guild-level cleanup functions
# =============================================================================


class TestDeleteLobbiesByGuild:
    """delete_lobbies_by_guild のテスト。"""

    async def test_delete_lobbies_by_guild(self, db_session: AsyncSession) -> None:
        """指定ギルドのロビーを全て削除できる。"""
        # 対象ギルドにロビーを作成
        await create_lobby(
            db_session, guild_id="123", lobby_channel_id="200000000000000001"
        )
        await create_lobby(
            db_session, guild_id="123", lobby_channel_id="200000000000000002"
        )
        # 別ギルドにもロビーを作成
        await create_lobby(
            db_session, guild_id="999", lobby_channel_id="200000000000000003"
        )

        count = await delete_lobbies_by_guild(db_session, "123")
        assert count == 2

        # 対象ギルドのロビーは削除されている
        lobbies = await get_lobbies_by_guild(db_session, "123")
        assert len(lobbies) == 0

        # 別ギルドのロビーは残っている
        other_lobbies = await get_lobbies_by_guild(db_session, "999")
        assert len(other_lobbies) == 1

    async def test_delete_lobbies_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドを指定しても 0 が返る。"""
        count = await delete_lobbies_by_guild(db_session, "nonexistent")
        assert count == 0


class TestDeleteVoiceSessionsByGuild:
    """delete_voice_sessions_by_guild のテスト。"""

    async def test_delete_voice_sessions_by_guild(
        self, db_session: AsyncSession
    ) -> None:
        """指定ギルドのボイスセッションを全て削除できる。"""
        # ロビーを作成
        lobby1 = await create_lobby(
            db_session, guild_id="123", lobby_channel_id="200000000000000001"
        )
        lobby2 = await create_lobby(
            db_session, guild_id="999", lobby_channel_id="200000000000000002"
        )

        # 対象ギルドにボイスセッションを作成
        await create_voice_session(
            db_session,
            lobby_id=lobby1.id,
            channel_id="300000000000000001",
            owner_id="400000000000000001",
            name="VC 1",
        )
        await create_voice_session(
            db_session,
            lobby_id=lobby1.id,
            channel_id="300000000000000002",
            owner_id="400000000000000002",
            name="VC 2",
        )
        # 別ギルドにもボイスセッションを作成
        await create_voice_session(
            db_session,
            lobby_id=lobby2.id,
            channel_id="300000000000000003",
            owner_id="400000000000000003",
            name="VC 3",
        )

        count = await delete_voice_sessions_by_guild(db_session, "123")
        assert count == 2

        # 対象ギルドのボイスセッションは削除されている
        all_sessions = await get_all_voice_sessions(db_session)
        target_sessions = [s for s in all_sessions if s.lobby.guild_id == "123"]
        assert len(target_sessions) == 0

        # 別ギルドのボイスセッションは残っている
        other_sessions = [s for s in all_sessions if s.lobby.guild_id == "999"]
        assert len(other_sessions) == 1

    async def test_delete_voice_sessions_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドを指定しても 0 が返る。"""
        count = await delete_voice_sessions_by_guild(db_session, "nonexistent")
        assert count == 0


class TestDeleteBumpRemindersByGuild:
    """delete_bump_reminders_by_guild のテスト。"""

    async def test_delete_bump_reminders_by_guild(
        self, db_session: AsyncSession
    ) -> None:
        """指定ギルドの bump リマインダーを全て削除できる。"""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        # 対象ギルドにリマインダーを作成
        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="ch1",
            service_name="DISBOARD",
            remind_at=remind_at,
        )
        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="ch1",
            service_name="ディス速報",
            remind_at=remind_at,
        )
        # 別ギルドにもリマインダーを作成
        await upsert_bump_reminder(
            db_session,
            guild_id="999",
            channel_id="ch2",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        count = await delete_bump_reminders_by_guild(db_session, "123")
        assert count == 2

        # 対象ギルドのリマインダーは削除されている
        disboard = await get_bump_reminder(db_session, "123", "DISBOARD")
        dissoku = await get_bump_reminder(db_session, "123", "ディス速報")
        assert disboard is None
        assert dissoku is None

        # 別ギルドのリマインダーは残っている
        other = await get_bump_reminder(db_session, "999", "DISBOARD")
        assert other is not None

    async def test_delete_bump_reminders_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドを指定しても 0 が返る。"""
        count = await delete_bump_reminders_by_guild(db_session, "nonexistent")
        assert count == 0


class TestDeleteStickyMessagesByGuild:
    """delete_sticky_messages_by_guild のテスト。"""

    async def test_delete_sticky_messages_by_guild(
        self, db_session: AsyncSession
    ) -> None:
        """指定ギルドの sticky メッセージを全て削除できる。"""
        # 対象ギルドに sticky メッセージを作成
        await create_sticky_message(
            db_session,
            channel_id="ch1",
            guild_id="123",
            title="Sticky 1",
            description="Description 1",
            color=0xFF0000,
            cooldown_seconds=5,
        )
        await create_sticky_message(
            db_session,
            channel_id="ch2",
            guild_id="123",
            title="Sticky 2",
            description="Description 2",
            color=0x00FF00,
            cooldown_seconds=10,
        )
        # 別ギルドにも sticky メッセージを作成
        await create_sticky_message(
            db_session,
            channel_id="ch3",
            guild_id="999",
            title="Other Sticky",
            description="Other Description",
            color=0x0000FF,
            cooldown_seconds=5,
        )

        count = await delete_sticky_messages_by_guild(db_session, "123")
        assert count == 2

        # 対象ギルドの sticky メッセージは削除されている
        all_stickies = await get_all_sticky_messages(db_session)
        target_stickies = [s for s in all_stickies if s.guild_id == "123"]
        assert len(target_stickies) == 0

        # 別ギルドの sticky メッセージは残っている
        other_stickies = [s for s in all_stickies if s.guild_id == "999"]
        assert len(other_stickies) == 1

    async def test_delete_sticky_messages_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドを指定しても 0 が返る。"""
        count = await delete_sticky_messages_by_guild(db_session, "nonexistent")
        assert count == 0


class TestGetAllLobbies:
    """get_all_lobbies のテスト。"""

    async def test_get_all_lobbies(self, db_session: AsyncSession) -> None:
        """全てのロビーを取得できる。"""
        # 複数ギルドにロビーを作成
        await create_lobby(
            db_session,
            guild_id="100000000000000001",
            lobby_channel_id="200000000000000001",
        )
        await create_lobby(
            db_session,
            guild_id="100000000000000001",
            lobby_channel_id="200000000000000002",
        )
        await create_lobby(
            db_session,
            guild_id="100000000000000002",
            lobby_channel_id="200000000000000003",
        )

        lobbies = await get_all_lobbies(db_session)
        assert len(lobbies) == 3

        channel_ids = {lobby.lobby_channel_id for lobby in lobbies}
        assert channel_ids == {
            "200000000000000001",
            "200000000000000002",
            "200000000000000003",
        }

    async def test_get_all_lobbies_empty(self, db_session: AsyncSession) -> None:
        """ロビーが存在しない場合は空リストを返す。"""
        lobbies = await get_all_lobbies(db_session)
        assert lobbies == []

    async def test_get_all_lobbies_after_deletion(
        self, db_session: AsyncSession
    ) -> None:
        """削除後にロビーが正しく取得される。"""
        lobby1 = await create_lobby(
            db_session,
            guild_id="100000000000000001",
            lobby_channel_id="200000000000000001",
        )
        await create_lobby(
            db_session,
            guild_id="100000000000000001",
            lobby_channel_id="200000000000000002",
        )

        # 1つ削除（IDで削除）
        await delete_lobby(db_session, lobby1.id)

        lobbies = await get_all_lobbies(db_session)
        assert len(lobbies) == 1
        assert lobbies[0].lobby_channel_id == "200000000000000002"


class TestGetAllBumpConfigs:
    """get_all_bump_configs のテスト。"""

    async def test_get_all_bump_configs(self, db_session: AsyncSession) -> None:
        """全ての bump 設定を取得できる。"""
        # 複数ギルドに bump 設定を作成
        await upsert_bump_config(
            db_session,
            guild_id="guild1",
            channel_id="ch1",
        )
        await upsert_bump_config(
            db_session,
            guild_id="guild2",
            channel_id="ch2",
        )
        await upsert_bump_config(
            db_session,
            guild_id="guild3",
            channel_id="ch3",
        )

        configs = await get_all_bump_configs(db_session)
        assert len(configs) == 3

        guild_ids = {config.guild_id for config in configs}
        assert guild_ids == {"guild1", "guild2", "guild3"}

    async def test_get_all_bump_configs_empty(self, db_session: AsyncSession) -> None:
        """bump 設定が存在しない場合は空リストを返す。"""
        configs = await get_all_bump_configs(db_session)
        assert configs == []

    async def test_get_all_bump_configs_after_deletion(
        self, db_session: AsyncSession
    ) -> None:
        """削除後に bump 設定が正しく取得される。"""
        await upsert_bump_config(
            db_session,
            guild_id="guild1",
            channel_id="ch1",
        )
        await upsert_bump_config(
            db_session,
            guild_id="guild2",
            channel_id="ch2",
        )

        # 1つ削除
        await delete_bump_config(db_session, "guild1")

        configs = await get_all_bump_configs(db_session)
        assert len(configs) == 1
        assert configs[0].guild_id == "guild2"

    async def test_get_all_bump_configs_with_updated_data(
        self, db_session: AsyncSession
    ) -> None:
        """更新後のデータが正しく取得される。"""
        await upsert_bump_config(
            db_session,
            guild_id="guild1",
            channel_id="ch1",
        )

        # 同じギルドの設定を更新
        await upsert_bump_config(
            db_session,
            guild_id="guild1",
            channel_id="ch1_updated",
        )

        configs = await get_all_bump_configs(db_session)
        assert len(configs) == 1
        assert configs[0].channel_id == "ch1_updated"


class TestDeleteRolePanelsByGuild:
    """delete_role_panels_by_guild のテスト。"""

    async def test_delete_role_panels_by_guild(self, db_session: AsyncSession) -> None:
        """指定ギルドの全ロールパネルを削除できる。"""
        # 対象ギルドにロールパネルを作成
        panel1 = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="ch1",
            panel_type="button",
            title="Panel 1",
        )
        panel2 = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="ch2",
            panel_type="button",
            title="Panel 2",
        )
        # 別ギルドにもロールパネルを作成
        await create_role_panel(
            db_session,
            guild_id="999",
            channel_id="ch3",
            panel_type="button",
            title="Other Panel",
        )

        # パネルにアイテムを追加
        await add_role_panel_item(
            db_session,
            panel_id=panel1.id,
            role_id="role1",
            emoji="game",
        )
        await add_role_panel_item(
            db_session,
            panel_id=panel2.id,
            role_id="role2",
            emoji="music",
        )

        count = await delete_role_panels_by_guild(db_session, "123")
        assert count == 2

        # 対象ギルドのロールパネルは削除されている
        all_panels = await get_all_role_panels(db_session)
        target_panels = [p for p in all_panels if p.guild_id == "123"]
        assert len(target_panels) == 0

        # カスケード削除によりアイテムも削除されている
        items1 = await get_role_panel_items(db_session, panel1.id)
        items2 = await get_role_panel_items(db_session, panel2.id)
        assert len(items1) == 0
        assert len(items2) == 0

        # 別ギルドのロールパネルは残っている
        other_panels = [p for p in all_panels if p.guild_id == "999"]
        assert len(other_panels) == 1

    async def test_delete_role_panels_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドを指定しても 0 が返る。"""
        count = await delete_role_panels_by_guild(db_session, "nonexistent")
        assert count == 0

    async def test_delete_role_panels_by_guild_with_multiple_items(
        self, db_session: AsyncSession
    ) -> None:
        """複数アイテムを持つパネルが正しくカスケード削除される。"""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="ch1",
            panel_type="button",
            title="Panel with many items",
        )

        # 複数アイテムを追加
        for i in range(5):
            await add_role_panel_item(
                db_session,
                panel_id=panel.id,
                role_id=f"role{i}",
                emoji=f"emoji{i}",
            )

        items_before = await get_role_panel_items(db_session, panel.id)
        assert len(items_before) == 5

        count = await delete_role_panels_by_guild(db_session, "123")
        assert count == 1

        # カスケード削除によりアイテムも全て削除されている
        items_after = await get_role_panel_items(db_session, panel.id)
        assert len(items_after) == 0


class TestDeleteRolePanelsByChannel:
    """delete_role_panels_by_channel のテスト。"""

    async def test_delete_role_panels_by_channel(
        self, db_session: AsyncSession
    ) -> None:
        """指定チャンネルの全ロールパネルを削除できる。"""
        # 対象チャンネルにロールパネルを作成
        panel1 = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="ch1",
            panel_type="button",
            title="Panel 1",
        )
        panel2 = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="ch1",
            panel_type="reaction",
            title="Panel 2",
        )
        # 別チャンネルにもロールパネルを作成
        await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="ch2",
            panel_type="button",
            title="Other Panel",
        )

        # パネルにアイテムを追加
        await add_role_panel_item(
            db_session,
            panel_id=panel1.id,
            role_id="role1",
            emoji="👍",
        )
        await add_role_panel_item(
            db_session,
            panel_id=panel2.id,
            role_id="role2",
            emoji="👎",
        )

        count = await delete_role_panels_by_channel(db_session, "ch1")
        assert count == 2

        # 対象チャンネルのロールパネルは削除されている
        all_panels = await get_all_role_panels(db_session)
        target_panels = [p for p in all_panels if p.channel_id == "ch1"]
        assert len(target_panels) == 0

        # カスケード削除によりアイテムも削除されている
        items1 = await get_role_panel_items(db_session, panel1.id)
        items2 = await get_role_panel_items(db_session, panel2.id)
        assert len(items1) == 0
        assert len(items2) == 0

        # 別チャンネルのロールパネルは残っている
        other_panels = [p for p in all_panels if p.channel_id == "ch2"]
        assert len(other_panels) == 1

    async def test_delete_role_panels_by_channel_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないチャンネルを指定しても 0 が返る。"""
        count = await delete_role_panels_by_channel(db_session, "nonexistent")
        assert count == 0


class TestDeleteRolePanelByMessageId:
    """delete_role_panel_by_message_id のテスト。"""

    async def test_delete_role_panel_by_message_id(
        self, db_session: AsyncSession
    ) -> None:
        """指定メッセージIDのロールパネルを削除できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="ch1",
            panel_type="button",
            title="Test Panel",
        )
        # message_id を設定
        await update_role_panel(db_session, panel, message_id="msg123")
        # パネルにアイテムを追加
        await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id="role1",
            emoji="👍",
        )

        result = await delete_role_panel_by_message_id(db_session, "msg123")
        assert result is True

        # ロールパネルは削除されている
        deleted_panel = await get_role_panel(db_session, panel.id)
        assert deleted_panel is None

        # カスケード削除によりアイテムも削除されている
        items = await get_role_panel_items(db_session, panel.id)
        assert len(items) == 0

    async def test_delete_role_panel_by_message_id_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないメッセージIDを指定すると False が返る。"""
        result = await delete_role_panel_by_message_id(db_session, "nonexistent")
        assert result is False

    async def test_delete_role_panel_by_message_id_none(
        self, db_session: AsyncSession
    ) -> None:
        """message_id が None のパネルは削除されない。"""
        # message_id が None のパネルを作成 (デフォルトで message_id は None)
        await create_role_panel(
            db_session,
            guild_id="123",
            channel_id="ch1",
            panel_type="button",
            title="Unposted Panel",
        )

        # None を指定しても False が返る（マッチしない）
        result = await delete_role_panel_by_message_id(db_session, "")
        assert result is False


# ===========================================================================
# チケットカテゴリ操作
# ===========================================================================


class TestTicketCategoryOperations:
    """Tests for ticket category database operations."""

    async def test_create_ticket_category(self, db_session: AsyncSession) -> None:
        """チケットカテゴリを作成できる。"""
        from src.services.db_service import create_ticket_category

        category = await create_ticket_category(
            db_session,
            guild_id="123",
            name="General Support",
            staff_role_id="999",
        )
        assert category.id is not None
        assert category.guild_id == "123"
        assert category.name == "General Support"
        assert category.staff_role_id == "999"
        assert category.channel_prefix == "ticket-"
        assert category.is_enabled is True

    async def test_create_ticket_category_with_options(
        self, db_session: AsyncSession
    ) -> None:
        """オプション付きでチケットカテゴリを作成できる。"""
        from src.services.db_service import create_ticket_category

        category = await create_ticket_category(
            db_session,
            guild_id="123",
            name="Bug Report",
            staff_role_id="999",
            discord_category_id="555",
            channel_prefix="bug-",
            form_questions='["お名前","内容"]',
        )
        assert category.discord_category_id == "555"
        assert category.channel_prefix == "bug-"
        assert category.form_questions == '["お名前","内容"]'

    async def test_create_ticket_category_with_log_channel(
        self, db_session: AsyncSession
    ) -> None:
        """log_channel_id 付きでチケットカテゴリを作成できる。"""
        from src.services.db_service import create_ticket_category

        category = await create_ticket_category(
            db_session,
            guild_id="123",
            name="Support",
            staff_role_id="999",
            log_channel_id="888",
        )
        assert category.log_channel_id == "888"

    async def test_get_ticket_category(self, db_session: AsyncSession) -> None:
        """チケットカテゴリを ID で取得できる。"""
        from src.services.db_service import create_ticket_category, get_ticket_category

        created = await create_ticket_category(
            db_session, guild_id="123", name="Test", staff_role_id="999"
        )
        found = await get_ticket_category(db_session, created.id)
        assert found is not None
        assert found.name == "Test"

    async def test_get_ticket_category_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないカテゴリは None を返す。"""
        from src.services.db_service import get_ticket_category

        found = await get_ticket_category(db_session, 99999)
        assert found is None

    async def test_get_ticket_categories_by_guild(
        self, db_session: AsyncSession
    ) -> None:
        """ギルドごとのカテゴリ一覧を取得できる。"""
        from src.services.db_service import (
            create_ticket_category,
            get_ticket_categories_by_guild,
        )

        await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        await create_ticket_category(
            db_session, guild_id="123", name="Cat2", staff_role_id="999"
        )
        await create_ticket_category(
            db_session, guild_id="999", name="Other", staff_role_id="999"
        )

        cats = await get_ticket_categories_by_guild(db_session, "123")
        assert len(cats) == 2

    async def test_get_enabled_ticket_categories_by_guild(
        self, db_session: AsyncSession
    ) -> None:
        """有効なカテゴリのみ取得できる。"""
        from src.services.db_service import (
            create_ticket_category,
            get_enabled_ticket_categories_by_guild,
        )

        await create_ticket_category(
            db_session, guild_id="123", name="Enabled", staff_role_id="999"
        )
        cat2 = await create_ticket_category(
            db_session, guild_id="123", name="Disabled", staff_role_id="999"
        )
        cat2.is_enabled = False
        await db_session.commit()

        cats = await get_enabled_ticket_categories_by_guild(db_session, "123")
        assert len(cats) == 1
        assert cats[0].name == "Enabled"

    async def test_delete_ticket_category(self, db_session: AsyncSession) -> None:
        """チケットカテゴリを削除できる。"""
        from src.services.db_service import (
            create_ticket_category,
            delete_ticket_category,
            get_ticket_category,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="ToDelete", staff_role_id="999"
        )
        result = await delete_ticket_category(db_session, cat.id)
        assert result is True

        found = await get_ticket_category(db_session, cat.id)
        assert found is None

    async def test_delete_ticket_category_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないカテゴリの削除は False。"""
        from src.services.db_service import delete_ticket_category

        result = await delete_ticket_category(db_session, 99999)
        assert result is False

    async def test_delete_ticket_category_cascades_tickets(
        self, db_session: AsyncSession
    ) -> None:
        """カテゴリ削除時に関連チケットも CASCADE 削除される。"""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            delete_ticket_category,
            get_ticket,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="CascadeTest", staff_role_id="999"
        )
        ticket = await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )

        result = await delete_ticket_category(db_session, cat.id)
        assert result is True

        found = await get_ticket(db_session, ticket.id)
        assert found is None

    async def test_delete_ticket_category_cascades_panel_categories(
        self, db_session: AsyncSession
    ) -> None:
        """カテゴリ削除時に関連 panel_category も CASCADE 削除される。"""
        from src.services.db_service import (
            add_ticket_panel_category,
            create_ticket_category,
            create_ticket_panel,
            delete_ticket_category,
            get_ticket_panel_categories,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="CascadeTest", staff_role_id="999"
        )
        panel = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="Panel"
        )
        await add_ticket_panel_category(
            db_session, panel_id=panel.id, category_id=cat.id
        )

        result = await delete_ticket_category(db_session, cat.id)
        assert result is True

        associations = await get_ticket_panel_categories(db_session, panel.id)
        assert len(associations) == 0


# ===========================================================================
# チケットパネル操作
# ===========================================================================


class TestTicketPanelOperations:
    """Tests for ticket panel database operations."""

    async def test_create_ticket_panel(self, db_session: AsyncSession) -> None:
        """チケットパネルを作成できる。"""
        from src.services.db_service import create_ticket_panel

        panel = await create_ticket_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            title="Support",
        )
        assert panel.id is not None
        assert panel.guild_id == "123"
        assert panel.title == "Support"
        assert panel.message_id is None

    async def test_get_ticket_panel(self, db_session: AsyncSession) -> None:
        """パネルを ID で取得できる。"""
        from src.services.db_service import create_ticket_panel, get_ticket_panel

        created = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="Test"
        )
        found = await get_ticket_panel(db_session, created.id)
        assert found is not None
        assert found.title == "Test"

    async def test_get_ticket_panel_by_message_id(
        self, db_session: AsyncSession
    ) -> None:
        """message_id でパネルを取得できる。"""
        from src.services.db_service import (
            create_ticket_panel,
            get_ticket_panel_by_message_id,
            update_ticket_panel,
        )

        panel = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="Test"
        )
        await update_ticket_panel(db_session, panel, message_id="msg123")

        found = await get_ticket_panel_by_message_id(db_session, "msg123")
        assert found is not None
        assert found.id == panel.id

    async def test_get_all_ticket_panels(self, db_session: AsyncSession) -> None:
        """全パネルを取得できる。"""
        from src.services.db_service import create_ticket_panel, get_all_ticket_panels

        await create_ticket_panel(
            db_session, guild_id="123", channel_id="ch1", title="P1"
        )
        await create_ticket_panel(
            db_session, guild_id="456", channel_id="ch2", title="P2"
        )

        panels = await get_all_ticket_panels(db_session)
        assert len(panels) == 2

    async def test_update_ticket_panel(self, db_session: AsyncSession) -> None:
        """パネルを更新できる。"""
        from src.services.db_service import create_ticket_panel, update_ticket_panel

        panel = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="Old"
        )
        updated = await update_ticket_panel(
            db_session, panel, title="New", message_id="msg1"
        )
        assert updated.title == "New"
        assert updated.message_id == "msg1"

    async def test_delete_ticket_panel(self, db_session: AsyncSession) -> None:
        """パネルを削除できる。"""
        from src.services.db_service import (
            create_ticket_panel,
            delete_ticket_panel,
            get_ticket_panel,
        )

        panel = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="ToDelete"
        )
        result = await delete_ticket_panel(db_session, panel.id)
        assert result is True

        found = await get_ticket_panel(db_session, panel.id)
        assert found is None

    async def test_delete_ticket_panel_by_message_id(
        self, db_session: AsyncSession
    ) -> None:
        """message_id でパネルを削除できる。"""
        from src.services.db_service import (
            create_ticket_panel,
            delete_ticket_panel_by_message_id,
            update_ticket_panel,
        )

        panel = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="Test"
        )
        await update_ticket_panel(db_session, panel, message_id="msg123")

        result = await delete_ticket_panel_by_message_id(db_session, "msg123")
        assert result is True

    async def test_get_ticket_panel_not_found(self, db_session: AsyncSession) -> None:
        """存在しないパネルは None を返す。"""
        from src.services.db_service import get_ticket_panel

        found = await get_ticket_panel(db_session, 99999)
        assert found is None

    async def test_get_ticket_panel_by_message_id_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない message_id は None を返す。"""
        from src.services.db_service import get_ticket_panel_by_message_id

        found = await get_ticket_panel_by_message_id(db_session, "nonexistent")
        assert found is None

    async def test_delete_ticket_panel_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないパネルの削除は False。"""
        from src.services.db_service import delete_ticket_panel

        result = await delete_ticket_panel(db_session, 99999)
        assert result is False

    async def test_delete_ticket_panel_by_message_id_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない message_id の削除は False。"""
        from src.services.db_service import delete_ticket_panel_by_message_id

        result = await delete_ticket_panel_by_message_id(db_session, "nonexistent")
        assert result is False

    async def test_get_ticket_panels_by_guild(self, db_session: AsyncSession) -> None:
        """ギルドごとのパネル一覧を取得できる。"""
        from src.services.db_service import (
            create_ticket_panel,
            get_ticket_panels_by_guild,
        )

        await create_ticket_panel(
            db_session, guild_id="123", channel_id="ch1", title="P1"
        )
        await create_ticket_panel(
            db_session, guild_id="123", channel_id="ch2", title="P2"
        )
        await create_ticket_panel(
            db_session, guild_id="999", channel_id="ch3", title="Other"
        )

        panels = await get_ticket_panels_by_guild(db_session, "123")
        assert len(panels) == 2

        panels_999 = await get_ticket_panels_by_guild(db_session, "999")
        assert len(panels_999) == 1

    async def test_update_ticket_panel_description_only(
        self, db_session: AsyncSession
    ) -> None:
        """description のみを更新できる。"""
        from src.services.db_service import create_ticket_panel, update_ticket_panel

        panel = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="Title"
        )
        updated = await update_ticket_panel(
            db_session, panel, description="New description"
        )
        assert updated.description == "New description"
        assert updated.title == "Title"  # 変更されていない

    async def test_create_ticket_panel_with_description(
        self, db_session: AsyncSession
    ) -> None:
        """description 付きでパネルを作成できる。"""
        from src.services.db_service import create_ticket_panel

        panel = await create_ticket_panel(
            db_session,
            guild_id="123",
            channel_id="456",
            title="Support",
            description="Click below to create a ticket",
        )
        assert panel.description == "Click below to create a ticket"

    async def test_delete_ticket_panel_cascades_associations(
        self, db_session: AsyncSession
    ) -> None:
        """パネル削除で関連する panel_category も CASCADE 削除される。"""
        from src.services.db_service import (
            add_ticket_panel_category,
            create_ticket_category,
            create_ticket_panel,
            delete_ticket_panel,
            get_ticket_panel_categories,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        panel = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="Panel"
        )
        await add_ticket_panel_category(
            db_session, panel_id=panel.id, category_id=cat.id
        )

        # パネル削除
        result = await delete_ticket_panel(db_session, panel.id)
        assert result is True

        # 関連も消えている
        associations = await get_ticket_panel_categories(db_session, panel.id)
        assert len(associations) == 0


# ===========================================================================
# チケットパネルカテゴリ関連操作
# ===========================================================================


class TestTicketPanelCategoryOperations:
    """Tests for ticket panel-category association operations."""

    async def test_add_ticket_panel_category(self, db_session: AsyncSession) -> None:
        """パネルにカテゴリを関連付けできる。"""
        from src.services.db_service import (
            add_ticket_panel_category,
            create_ticket_category,
            create_ticket_panel,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        panel = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="Panel"
        )
        assoc = await add_ticket_panel_category(
            db_session, panel_id=panel.id, category_id=cat.id
        )
        assert assoc is not None
        assert assoc.panel_id == panel.id
        assert assoc.category_id == cat.id

    async def test_get_ticket_panel_categories(self, db_session: AsyncSession) -> None:
        """パネルのカテゴリ関連を取得できる。"""
        from src.services.db_service import (
            add_ticket_panel_category,
            create_ticket_category,
            create_ticket_panel,
            get_ticket_panel_categories,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        panel = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="Panel"
        )
        await add_ticket_panel_category(
            db_session, panel_id=panel.id, category_id=cat.id
        )

        associations = await get_ticket_panel_categories(db_session, panel.id)
        assert len(associations) == 1

    async def test_remove_ticket_panel_category(self, db_session: AsyncSession) -> None:
        """パネルのカテゴリ関連を削除できる。"""
        from src.services.db_service import (
            add_ticket_panel_category,
            create_ticket_category,
            create_ticket_panel,
            get_ticket_panel_categories,
            remove_ticket_panel_category,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        panel = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="Panel"
        )
        await add_ticket_panel_category(
            db_session, panel_id=panel.id, category_id=cat.id
        )

        result = await remove_ticket_panel_category(
            db_session, panel_id=panel.id, category_id=cat.id
        )
        assert result is True

        associations = await get_ticket_panel_categories(db_session, panel.id)
        assert len(associations) == 0

    async def test_remove_ticket_panel_category_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない関連の削除は False。"""
        from src.services.db_service import remove_ticket_panel_category

        result = await remove_ticket_panel_category(db_session, 99999, 99999)
        assert result is False

    async def test_add_ticket_panel_category_with_options(
        self, db_session: AsyncSession
    ) -> None:
        """オプション付きで関連を追加できる。"""
        from src.services.db_service import (
            add_ticket_panel_category,
            create_ticket_category,
            create_ticket_panel,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        panel = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="Panel"
        )
        assoc = await add_ticket_panel_category(
            db_session,
            panel_id=panel.id,
            category_id=cat.id,
            button_label="Support",
            button_style="success",
            button_emoji="\U0001f4e9",
        )
        assert assoc.button_label == "Support"
        assert assoc.button_style == "success"
        assert assoc.button_emoji == "\U0001f4e9"

    async def test_add_ticket_panel_category_auto_position(
        self, db_session: AsyncSession
    ) -> None:
        """複数カテゴリ追加時に position が自動増加する。"""
        from src.services.db_service import (
            add_ticket_panel_category,
            create_ticket_category,
            create_ticket_panel,
            get_ticket_panel_categories,
        )

        cat1 = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        cat2 = await create_ticket_category(
            db_session, guild_id="123", name="Cat2", staff_role_id="999"
        )
        panel = await create_ticket_panel(
            db_session, guild_id="123", channel_id="456", title="Panel"
        )
        await add_ticket_panel_category(
            db_session, panel_id=panel.id, category_id=cat1.id
        )
        await add_ticket_panel_category(
            db_session, panel_id=panel.id, category_id=cat2.id
        )

        associations = await get_ticket_panel_categories(db_session, panel.id)
        assert len(associations) == 2
        assert associations[0].position == 0
        assert associations[1].position == 1


# ===========================================================================
# チケット操作
# ===========================================================================


class TestTicketOperations:
    """Tests for ticket database operations."""

    async def test_create_ticket(self, db_session: AsyncSession) -> None:
        """チケットを作成できる。"""
        from src.services.db_service import create_ticket, create_ticket_category

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        ticket = await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User One",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )
        assert ticket.id is not None
        assert ticket.guild_id == "123"
        assert ticket.user_id == "user1"
        assert ticket.status == "open"
        assert ticket.ticket_number == 1

    async def test_get_ticket(self, db_session: AsyncSession) -> None:
        """チケットを ID で取得できる。"""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            get_ticket,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        created = await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )
        found = await get_ticket(db_session, created.id)
        assert found is not None
        assert found.user_id == "user1"

    async def test_get_ticket_by_channel_id(self, db_session: AsyncSession) -> None:
        """channel_id でチケットを取得できる。"""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            get_ticket_by_channel_id,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )
        found = await get_ticket_by_channel_id(db_session, "ch1")
        assert found is not None

    async def test_get_ticket_by_channel_id_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない channel_id は None を返す。"""
        from src.services.db_service import get_ticket_by_channel_id

        found = await get_ticket_by_channel_id(db_session, "nonexistent")
        assert found is None

    async def test_get_next_ticket_number(self, db_session: AsyncSession) -> None:
        """次のチケット番号が正しく返される。"""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            get_next_ticket_number,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )

        # 最初のチケット番号は 1
        num = await get_next_ticket_number(db_session, "123")
        assert num == 1

        await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )

        # 次は 2
        num = await get_next_ticket_number(db_session, "123")
        assert num == 2

    async def test_update_ticket_status(self, db_session: AsyncSession) -> None:
        """チケットステータスを更新できる。"""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            update_ticket_status,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        ticket = await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )

        updated = await update_ticket_status(
            db_session,
            ticket,
            status="claimed",
            claimed_by="staff1",
        )
        assert updated.status == "claimed"
        assert updated.claimed_by == "staff1"

    async def test_update_ticket_status_close_with_channel_none(
        self, db_session: AsyncSession
    ) -> None:
        """チケットクローズ時に channel_id を None に設定できる。"""
        from datetime import UTC, datetime

        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            update_ticket_status,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        ticket = await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )

        now = datetime.now(UTC)
        updated = await update_ticket_status(
            db_session,
            ticket,
            status="closed",
            closed_by="staff1",
            close_reason="resolved",
            transcript="transcript text",
            closed_at=now,
            channel_id=None,
        )
        assert updated.status == "closed"
        assert updated.closed_by == "staff1"
        assert updated.channel_id is None
        assert updated.transcript == "transcript text"

    async def test_get_all_tickets(self, db_session: AsyncSession) -> None:
        """全チケットを取得できる。"""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            get_all_tickets,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User1",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )
        await create_ticket(
            db_session,
            guild_id="123",
            user_id="user2",
            username="User2",
            category_id=cat.id,
            channel_id="ch2",
            ticket_number=2,
        )

        tickets = await get_all_tickets(db_session)
        assert len(tickets) == 2

    async def test_get_tickets_by_guild_with_status(
        self, db_session: AsyncSession
    ) -> None:
        """ステータスフィルタ付きでギルドのチケットを取得できる。"""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            get_tickets_by_guild,
            update_ticket_status,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        t1 = await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User1",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )
        await create_ticket(
            db_session,
            guild_id="123",
            user_id="user2",
            username="User2",
            category_id=cat.id,
            channel_id="ch2",
            ticket_number=2,
        )
        await update_ticket_status(db_session, t1, status="closed")

        open_tickets = await get_tickets_by_guild(db_session, "123", status="open")
        assert len(open_tickets) == 1

        closed_tickets = await get_tickets_by_guild(db_session, "123", status="closed")
        assert len(closed_tickets) == 1

    async def test_get_ticket_not_found(self, db_session: AsyncSession) -> None:
        """存在しないチケットは None を返す。"""
        from src.services.db_service import get_ticket

        found = await get_ticket(db_session, 99999)
        assert found is None

    async def test_create_ticket_with_form_answers(
        self, db_session: AsyncSession
    ) -> None:
        """フォーム回答付きでチケットを作成できる。"""
        from src.services.db_service import create_ticket, create_ticket_category

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        ticket = await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User One",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
            form_answers='["answer1","answer2"]',
        )
        assert ticket.form_answers == '["answer1","answer2"]'

    async def test_get_all_tickets_with_status_filter(
        self, db_session: AsyncSession
    ) -> None:
        """ステータスフィルタ付きで全チケットを取得できる。"""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            get_all_tickets,
            update_ticket_status,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        t1 = await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User1",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )
        await create_ticket(
            db_session,
            guild_id="456",
            user_id="user2",
            username="User2",
            category_id=cat.id,
            channel_id="ch2",
            ticket_number=1,
        )
        await update_ticket_status(db_session, t1, status="closed")

        open_tickets = await get_all_tickets(db_session, status="open")
        assert len(open_tickets) == 1

        closed_tickets = await get_all_tickets(db_session, status="closed")
        assert len(closed_tickets) == 1

    async def test_get_all_tickets_with_limit(self, db_session: AsyncSession) -> None:
        """limit 付きで全チケットを取得できる。"""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            get_all_tickets,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        for i in range(5):
            await create_ticket(
                db_session,
                guild_id="123",
                user_id=f"user{i}",
                username=f"User{i}",
                category_id=cat.id,
                channel_id=f"ch{i}",
                ticket_number=i + 1,
            )

        tickets = await get_all_tickets(db_session, limit=3)
        assert len(tickets) == 3

    async def test_get_tickets_by_guild_without_status(
        self, db_session: AsyncSession
    ) -> None:
        """ステータスフィルタなしでギルドのチケットを取得できる。"""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            get_tickets_by_guild,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User1",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )
        await create_ticket(
            db_session,
            guild_id="123",
            user_id="user2",
            username="User2",
            category_id=cat.id,
            channel_id="ch2",
            ticket_number=2,
        )
        await create_ticket(
            db_session,
            guild_id="999",
            user_id="user3",
            username="User3",
            category_id=cat.id,
            channel_id="ch3",
            ticket_number=1,
        )

        tickets = await get_tickets_by_guild(db_session, "123")
        assert len(tickets) == 2

    async def test_get_next_ticket_number_cross_guild(
        self, db_session: AsyncSession
    ) -> None:
        """異なるギルドのチケット番号は独立している。"""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            get_next_ticket_number,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=5,
        )

        # guild 123 は次が 6
        num_123 = await get_next_ticket_number(db_session, "123")
        assert num_123 == 6

        # guild 999 はチケットなしなので 1
        num_999 = await get_next_ticket_number(db_session, "999")
        assert num_999 == 1

    async def test_update_ticket_status_without_channel_id(
        self, db_session: AsyncSession
    ) -> None:
        """channel_id を渡さない場合は変更しない (_UNSET sentinel)。"""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            update_ticket_status,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        ticket = await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )

        # channel_id を渡さず status のみ更新
        updated = await update_ticket_status(
            db_session, ticket, status="claimed", claimed_by="staff1"
        )
        assert updated.channel_id == "ch1"  # 変更されていない


class TestAutobanDbService:
    """Tests for autoban CRUD database operations."""

    async def test_create_autoban_rule(self, db_session: AsyncSession) -> None:
        """Test creating an autoban rule with all fields."""
        rule = await create_autoban_rule(
            db_session,
            guild_id="123",
            rule_type="username_match",
            action="ban",
            pattern="spam*",
            use_wildcard=True,
            threshold_minutes=None,
        )
        assert rule.id is not None
        assert rule.guild_id == "123"
        assert rule.rule_type == "username_match"
        assert rule.action == "ban"
        assert rule.pattern == "spam*"
        assert rule.use_wildcard is True
        assert rule.threshold_minutes is None
        assert rule.is_enabled is True

    async def test_create_autoban_rule_defaults(self, db_session: AsyncSession) -> None:
        """Test creating an autoban rule with default values."""
        rule = await create_autoban_rule(
            db_session,
            guild_id="123",
            rule_type="no_avatar",
        )
        assert rule.action == "ban"
        assert rule.pattern is None
        assert rule.use_wildcard is False
        assert rule.threshold_minutes is None

    async def test_get_autoban_rule(self, db_session: AsyncSession) -> None:
        """Test getting a specific autoban rule by ID."""
        rule = await create_autoban_rule(
            db_session,
            guild_id="123",
            rule_type="username_match",
            pattern="test",
        )
        found = await get_autoban_rule(db_session, rule.id)
        assert found is not None
        assert found.id == rule.id
        assert found.guild_id == "123"

    async def test_get_autoban_rule_not_found(self, db_session: AsyncSession) -> None:
        """Test getting a non-existent autoban rule returns None."""
        found = await get_autoban_rule(db_session, 99999)
        assert found is None

    async def test_get_all_autoban_rules(self, db_session: AsyncSession) -> None:
        """Test getting all autoban rules across guilds."""
        await create_autoban_rule(
            db_session, guild_id="123", rule_type="username_match", pattern="a"
        )
        await create_autoban_rule(db_session, guild_id="456", rule_type="no_avatar")
        await create_autoban_rule(
            db_session, guild_id="123", rule_type="account_age", threshold_minutes=1440
        )

        rules = await get_all_autoban_rules(db_session)
        assert len(rules) == 3

    async def test_get_all_autoban_rules_empty(self, db_session: AsyncSession) -> None:
        """Test getting all autoban rules when none exist."""
        rules = await get_all_autoban_rules(db_session)
        assert rules == []

    async def test_get_autoban_rules_by_guild(self, db_session: AsyncSession) -> None:
        """Test getting autoban rules filtered by guild."""
        await create_autoban_rule(
            db_session, guild_id="123", rule_type="username_match", pattern="a"
        )
        await create_autoban_rule(db_session, guild_id="123", rule_type="no_avatar")
        await create_autoban_rule(
            db_session, guild_id="456", rule_type="account_age", threshold_minutes=2880
        )

        rules_123 = await get_autoban_rules_by_guild(db_session, "123")
        assert len(rules_123) == 2

        rules_456 = await get_autoban_rules_by_guild(db_session, "456")
        assert len(rules_456) == 1

    async def test_get_autoban_rules_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting autoban rules for a guild with no rules."""
        rules = await get_autoban_rules_by_guild(db_session, "nonexistent")
        assert rules == []

    async def test_get_enabled_autoban_rules_by_guild(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting only enabled autoban rules for a guild."""
        rule1 = await create_autoban_rule(
            db_session, guild_id="123", rule_type="username_match", pattern="a"
        )
        await create_autoban_rule(db_session, guild_id="123", rule_type="no_avatar")

        # Disable rule1
        await toggle_autoban_rule(db_session, rule1.id)

        enabled = await get_enabled_autoban_rules_by_guild(db_session, "123")
        assert len(enabled) == 1
        assert enabled[0].rule_type == "no_avatar"

    async def test_get_enabled_autoban_rules_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting enabled rules when all are disabled."""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="no_avatar"
        )
        await toggle_autoban_rule(db_session, rule.id)

        enabled = await get_enabled_autoban_rules_by_guild(db_session, "123")
        assert enabled == []

    async def test_delete_autoban_rule(self, db_session: AsyncSession) -> None:
        """Test deleting an autoban rule."""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="no_avatar"
        )
        result = await delete_autoban_rule(db_session, rule.id)
        assert result is True

        found = await get_autoban_rule(db_session, rule.id)
        assert found is None

    async def test_delete_autoban_rule_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting a non-existent autoban rule returns False."""
        result = await delete_autoban_rule(db_session, 99999)
        assert result is False

    async def test_toggle_autoban_rule(self, db_session: AsyncSession) -> None:
        """Test toggling an autoban rule enabled/disabled."""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="no_avatar"
        )
        assert rule.is_enabled is True

        # Toggle off
        new_state = await toggle_autoban_rule(db_session, rule.id)
        assert new_state is False

        # Toggle back on
        new_state = await toggle_autoban_rule(db_session, rule.id)
        assert new_state is True

    async def test_toggle_autoban_rule_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test toggling a non-existent autoban rule returns None."""
        result = await toggle_autoban_rule(db_session, 99999)
        assert result is None

    async def test_create_autoban_log(self, db_session: AsyncSession) -> None:
        """Test creating an autoban log entry."""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="username_match", pattern="spam"
        )
        log = await create_autoban_log(
            db_session,
            guild_id="123",
            user_id="user1",
            username="spammer",
            rule_id=rule.id,
            action_taken="banned",
            reason="Username matched pattern: spam",
        )
        assert log.id is not None
        assert log.guild_id == "123"
        assert log.user_id == "user1"
        assert log.username == "spammer"
        assert log.rule_id == rule.id
        assert log.action_taken == "banned"
        assert log.reason == "Username matched pattern: spam"

    async def test_get_autoban_logs_by_guild(self, db_session: AsyncSession) -> None:
        """Test getting autoban logs filtered by guild."""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="no_avatar"
        )
        await create_autoban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="user1",
            rule_id=rule.id,
            action_taken="banned",
            reason="No avatar",
        )
        await create_autoban_log(
            db_session,
            guild_id="123",
            user_id="u2",
            username="user2",
            rule_id=rule.id,
            action_taken="banned",
            reason="No avatar",
        )

        rule2 = await create_autoban_rule(
            db_session, guild_id="456", rule_type="no_avatar"
        )
        await create_autoban_log(
            db_session,
            guild_id="456",
            user_id="u3",
            username="user3",
            rule_id=rule2.id,
            action_taken="kicked",
            reason="No avatar",
        )

        logs_123 = await get_autoban_logs_by_guild(db_session, "123")
        assert len(logs_123) == 2

        logs_456 = await get_autoban_logs_by_guild(db_session, "456")
        assert len(logs_456) == 1

    async def test_get_autoban_logs_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting autoban logs for a guild with no logs."""
        logs = await get_autoban_logs_by_guild(db_session, "nonexistent")
        assert logs == []

    async def test_get_autoban_logs_by_guild_limit(
        self, db_session: AsyncSession
    ) -> None:
        """Test that get_autoban_logs_by_guild respects the limit parameter."""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="no_avatar"
        )
        for i in range(5):
            await create_autoban_log(
                db_session,
                guild_id="123",
                user_id=f"u{i}",
                username=f"user{i}",
                rule_id=rule.id,
                action_taken="banned",
                reason="No avatar",
            )

        logs = await get_autoban_logs_by_guild(db_session, "123", limit=3)
        assert len(logs) == 3

    async def test_get_all_autoban_logs(self, db_session: AsyncSession) -> None:
        """Test getting all autoban logs across guilds."""
        rule1 = await create_autoban_rule(
            db_session, guild_id="123", rule_type="no_avatar"
        )
        rule2 = await create_autoban_rule(
            db_session, guild_id="456", rule_type="no_avatar"
        )
        await create_autoban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="user1",
            rule_id=rule1.id,
            action_taken="banned",
            reason="No avatar",
        )
        await create_autoban_log(
            db_session,
            guild_id="456",
            user_id="u2",
            username="user2",
            rule_id=rule2.id,
            action_taken="kicked",
            reason="No avatar",
        )

        logs = await get_all_autoban_logs(db_session)
        assert len(logs) == 2

    async def test_get_all_autoban_logs_empty(self, db_session: AsyncSession) -> None:
        """Test getting all autoban logs when none exist."""
        logs = await get_all_autoban_logs(db_session)
        assert logs == []

    async def test_get_all_autoban_logs_limit(self, db_session: AsyncSession) -> None:
        """Test that get_all_autoban_logs respects the limit parameter."""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="no_avatar"
        )
        for i in range(5):
            await create_autoban_log(
                db_session,
                guild_id="123",
                user_id=f"u{i}",
                username=f"user{i}",
                rule_id=rule.id,
                action_taken="banned",
                reason="No avatar",
            )

        logs = await get_all_autoban_logs(db_session, limit=2)
        assert len(logs) == 2

    async def test_delete_autoban_rule_cascades_logs(
        self, db_session: AsyncSession
    ) -> None:
        """Test that deleting a rule cascades to delete its logs."""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="no_avatar"
        )
        await create_autoban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="user1",
            rule_id=rule.id,
            action_taken="banned",
            reason="No avatar",
        )

        await delete_autoban_rule(db_session, rule.id)
        logs = await get_all_autoban_logs(db_session)
        assert logs == []


class TestClaimAutobanLog:
    """claim_autoban_log のアトミック重複防止テスト。"""

    async def test_first_claim_creates_log(self, db_session: AsyncSession) -> None:
        """初回 claim はログを作成する。"""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="username_match", pattern="spam"
        )
        log = await claim_autoban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="spammer",
            rule_id=rule.id,
            action_taken="banned",
            reason="test",
        )
        assert log is not None
        assert log.guild_id == "123"
        assert log.user_id == "u1"
        assert log.action_taken == "banned"

    async def test_duplicate_claim_returns_none(self, db_session: AsyncSession) -> None:
        """10 秒以内の同一 claim は None を返す。"""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="username_match", pattern="spam"
        )
        log1 = await claim_autoban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="spammer",
            rule_id=rule.id,
            action_taken="banned",
            reason="test",
        )
        assert log1 is not None

        log2 = await claim_autoban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="spammer",
            rule_id=rule.id,
            action_taken="banned",
            reason="test",
        )
        assert log2 is None

    async def test_different_user_not_duplicate(self, db_session: AsyncSession) -> None:
        """異なるユーザーなら重複にならない。"""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="username_match", pattern="spam"
        )
        log1 = await claim_autoban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="spammer1",
            rule_id=rule.id,
            action_taken="banned",
            reason="test",
        )
        log2 = await claim_autoban_log(
            db_session,
            guild_id="123",
            user_id="u2",
            username="spammer2",
            rule_id=rule.id,
            action_taken="banned",
            reason="test",
        )
        assert log1 is not None
        assert log2 is not None

    async def test_deleted_rule_returns_none(self, db_session: AsyncSession) -> None:
        """削除済みルールの claim は None を返す。"""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="username_match", pattern="spam"
        )
        rule_id = rule.id
        await delete_autoban_rule(db_session, rule_id)
        log = await claim_autoban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="spammer",
            rule_id=rule_id,
            action_taken="banned",
            reason="test",
        )
        assert log is None


class TestClaimBanLog:
    """claim_ban_log のアトミック重複防止テスト。"""

    async def test_first_claim_creates_log(self, db_session: AsyncSession) -> None:
        """初回 claim はログを作成する。"""
        log = await claim_ban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="spammer",
            reason="test",
            is_autoban=False,
        )
        assert log is not None
        assert log.guild_id == "123"
        assert log.user_id == "u1"

    async def test_duplicate_claim_returns_none(self, db_session: AsyncSession) -> None:
        """10 秒以内の同一 claim は None を返す。"""
        log1 = await claim_ban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="spammer",
            reason="test",
        )
        assert log1 is not None

        log2 = await claim_ban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="spammer",
            reason="test",
        )
        assert log2 is None

    async def test_different_user_not_duplicate(self, db_session: AsyncSession) -> None:
        """異なるユーザーなら重複にならない。"""
        log1 = await claim_ban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="spammer1",
        )
        log2 = await claim_ban_log(
            db_session,
            guild_id="123",
            user_id="u2",
            username="spammer2",
        )
        assert log1 is not None
        assert log2 is not None


class TestAutobanConfigDbService:
    """Tests for autoban config CRUD database operations."""

    async def test_get_autoban_config(self, db_session: AsyncSession) -> None:
        """Test getting an existing autoban config."""
        config = await upsert_autoban_config(db_session, "123", "456")
        found = await get_autoban_config(db_session, "123")
        assert found is not None
        assert found.guild_id == config.guild_id
        assert found.log_channel_id == "456"

    async def test_get_autoban_config_not_found(self, db_session: AsyncSession) -> None:
        """Test getting a non-existent autoban config returns None."""
        found = await get_autoban_config(db_session, "nonexistent")
        assert found is None

    async def test_upsert_autoban_config_create(self, db_session: AsyncSession) -> None:
        """Test creating a new autoban config via upsert."""
        config = await upsert_autoban_config(db_session, "123", "789")
        assert config.guild_id == "123"
        assert config.log_channel_id == "789"

    async def test_upsert_autoban_config_update(self, db_session: AsyncSession) -> None:
        """Test updating an existing autoban config via upsert."""
        await upsert_autoban_config(db_session, "123", "789")
        updated = await upsert_autoban_config(db_session, "123", "999")
        assert updated.guild_id == "123"
        assert updated.log_channel_id == "999"

        # 確認: 重複作成されていない
        configs = await get_all_autoban_configs(db_session)
        assert len(configs) == 1

    async def test_upsert_autoban_config_set_none(
        self, db_session: AsyncSession
    ) -> None:
        """Test setting log_channel_id to None via upsert."""
        await upsert_autoban_config(db_session, "123", "789")
        updated = await upsert_autoban_config(db_session, "123", None)
        assert updated.log_channel_id is None

    async def test_get_all_autoban_configs(self, db_session: AsyncSession) -> None:
        """Test getting all autoban configs."""
        await upsert_autoban_config(db_session, "111", "aaa")
        await upsert_autoban_config(db_session, "222", "bbb")
        await upsert_autoban_config(db_session, "333", None)

        configs = await get_all_autoban_configs(db_session)
        assert len(configs) == 3

    async def test_get_all_autoban_configs_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting all autoban configs when none exist."""
        configs = await get_all_autoban_configs(db_session)
        assert configs == []


class TestUpdateAutobanRule:
    """Tests for update_autoban_rule database operation."""

    async def test_update_action(self, db_session: AsyncSession) -> None:
        """action を更新できる。"""
        rule = await create_autoban_rule(
            db_session, guild_id="123", rule_type="no_avatar", action="ban"
        )
        updated = await update_autoban_rule(db_session, rule, action="kick")
        assert updated.action == "kick"

    async def test_update_pattern(self, db_session: AsyncSession) -> None:
        """pattern と use_wildcard を更新できる。"""
        rule = await create_autoban_rule(
            db_session,
            guild_id="123",
            rule_type="username_match",
            action="ban",
            pattern="spam",
        )
        updated = await update_autoban_rule(
            db_session, rule, pattern="new_pattern", use_wildcard=True
        )
        assert updated.pattern == "new_pattern"
        assert updated.use_wildcard is True

    async def test_update_threshold_minutes(self, db_session: AsyncSession) -> None:
        """threshold_minutes を更新できる。"""
        rule = await create_autoban_rule(
            db_session,
            guild_id="123",
            rule_type="account_age",
            action="ban",
            threshold_minutes=1440,
        )
        updated = await update_autoban_rule(db_session, rule, threshold_minutes=2880)
        assert updated.threshold_minutes == 2880

    async def test_update_threshold_seconds(self, db_session: AsyncSession) -> None:
        """threshold_seconds を更新できる。"""
        rule = await create_autoban_rule(
            db_session,
            guild_id="123",
            rule_type="role_acquired",
            action="ban",
            threshold_seconds=60,
        )
        updated = await update_autoban_rule(db_session, rule, threshold_seconds=300)
        assert updated.threshold_seconds == 300

    async def test_none_fields_not_changed(self, db_session: AsyncSession) -> None:
        """None のフィールドは変更しない。"""
        rule = await create_autoban_rule(
            db_session,
            guild_id="123",
            rule_type="username_match",
            action="ban",
            pattern="original",
        )
        updated = await update_autoban_rule(db_session, rule, action="kick")
        assert updated.action == "kick"
        assert updated.pattern == "original"

    async def test_update_multiple_fields(self, db_session: AsyncSession) -> None:
        """複数フィールドを同時に更新できる。"""
        rule = await create_autoban_rule(
            db_session,
            guild_id="123",
            rule_type="username_match",
            action="ban",
            pattern="old",
        )
        updated = await update_autoban_rule(
            db_session,
            rule,
            action="kick",
            pattern="new",
            use_wildcard=True,
        )
        assert updated.action == "kick"
        assert updated.pattern == "new"
        assert updated.use_wildcard is True

    async def test_update_no_fields_noop(self, db_session: AsyncSession) -> None:
        """全てのフィールドが None の場合は何も変更しない。"""
        rule = await create_autoban_rule(
            db_session,
            guild_id="123",
            rule_type="no_avatar",
            action="ban",
        )
        updated = await update_autoban_rule(db_session, rule)
        assert updated.action == "ban"
        assert updated.id == rule.id

    async def test_update_returns_same_object(self, db_session: AsyncSession) -> None:
        """更新後のオブジェクトは同一インスタンスを返す。"""
        rule = await create_autoban_rule(
            db_session,
            guild_id="123",
            rule_type="no_avatar",
            action="ban",
        )
        updated = await update_autoban_rule(db_session, rule, action="kick")
        assert updated is rule

    async def test_update_persists_after_refresh(
        self, db_session: AsyncSession
    ) -> None:
        """更新後に refresh しても値が保持されている。"""
        rule = await create_autoban_rule(
            db_session,
            guild_id="123",
            rule_type="account_age",
            action="ban",
            threshold_minutes=1440,
        )
        await update_autoban_rule(db_session, rule, threshold_minutes=6000)
        await db_session.refresh(rule)
        assert rule.threshold_minutes == 6000

    async def test_update_use_wildcard_to_false(self, db_session: AsyncSession) -> None:
        """use_wildcard を True から False に更新できる。"""
        rule = await create_autoban_rule(
            db_session,
            guild_id="123",
            rule_type="username_match",
            action="ban",
            pattern="test",
            use_wildcard=True,
        )
        updated = await update_autoban_rule(db_session, rule, use_wildcard=False)
        assert updated.use_wildcard is False


class TestTicketNumberEdgeCases:
    """Edge case tests for ticket number generation."""

    async def test_next_number_non_sequential(self, db_session: AsyncSession) -> None:
        """Non-sequential ticket numbers still return max+1, not gap-filling."""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            get_next_ticket_number,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )

        for num in (1, 3, 5):
            await create_ticket(
                db_session,
                guild_id="123",
                user_id="user1",
                username="User",
                category_id=cat.id,
                channel_id=f"ch{num}",
                ticket_number=num,
            )

        result = await get_next_ticket_number(db_session, "123")
        assert result == 6

    async def test_next_number_empty_guild(self, db_session: AsyncSession) -> None:
        """Empty guild returns 1 as the first ticket number."""
        from src.services.db_service import get_next_ticket_number

        result = await get_next_ticket_number(db_session, "999999")
        assert result == 1


class TestBumpConfigUpsertEdgeCases:
    """Edge case tests for bump config upsert."""

    async def test_upsert_insert_path(self, db_session: AsyncSession) -> None:
        """Upserting a new guild creates a fresh BumpConfig."""
        config = await upsert_bump_config(db_session, guild_id="111", channel_id="222")
        assert config.guild_id == "111"
        assert config.channel_id == "222"

    async def test_upsert_update_path(self, db_session: AsyncSession) -> None:
        """Upserting same guild_id twice updates channel_id."""
        await upsert_bump_config(db_session, guild_id="111", channel_id="222")
        updated = await upsert_bump_config(db_session, guild_id="111", channel_id="333")
        assert updated.guild_id == "111"
        assert updated.channel_id == "333"


class TestUpdateTicketSentinelEdgeCases:
    """Edge case tests for update_ticket_status sentinel behavior."""

    async def test_status_only_preserves_other_fields(
        self, db_session: AsyncSession
    ) -> None:
        """Updating status only preserves previously-set claimed_by."""
        from src.services.db_service import (
            create_ticket,
            create_ticket_category,
            update_ticket_status,
        )

        cat = await create_ticket_category(
            db_session, guild_id="123", name="Cat1", staff_role_id="999"
        )
        ticket = await create_ticket(
            db_session,
            guild_id="123",
            user_id="user1",
            username="User",
            category_id=cat.id,
            channel_id="ch1",
            ticket_number=1,
        )

        # First set claimed_by
        await update_ticket_status(
            db_session, ticket, status="claimed", claimed_by="staff1"
        )

        # Then update status only — claimed_by should be preserved
        updated = await update_ticket_status(db_session, ticket, status="closed")
        assert updated.status == "closed"
        assert updated.claimed_by == "staff1"


class TestDeleteVoiceSessionEdgeCases:
    """Edge case tests for voice session deletion."""

    async def test_delete_non_existent_returns_false(
        self, db_session: AsyncSession
    ) -> None:
        """Deleting a non-existent voice session returns False."""
        result = await delete_voice_session(db_session, "999999999999999999")
        assert result is False


# =============================================================================
# Additional Edge Case Tests
# =============================================================================


class TestGetOperationsEdgeCases:
    """get_* 系関数のエッジケーステスト。"""

    async def test_get_lobby_by_nonexistent_channel(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない channel_id で get_lobby_by_channel_id は None を返す。"""
        result = await get_lobby_by_channel_id(db_session, "999999999999999999")
        assert result is None

    async def test_get_voice_session_nonexistent(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない channel_id で get_voice_session は None を返す。"""
        result = await get_voice_session(db_session, "999999999999999999")
        assert result is None

    async def test_get_sticky_message_nonexistent(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない channel_id で get_sticky_message は None を返す。"""
        result = await get_sticky_message(db_session, "999999999999999999")
        assert result is None

    async def test_get_bump_config_nonexistent(self, db_session: AsyncSession) -> None:
        """存在しない guild_id で get_bump_config は None を返す。"""
        result = await get_bump_config(db_session, "999999999999999999")
        assert result is None

    async def test_get_bump_reminder_nonexistent(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない guild + service で get_bump_reminder は None を返す。"""
        result = await get_bump_reminder(db_session, "999999999999999999", "DISBOARD")
        assert result is None

    async def test_get_role_panel_nonexistent(self, db_session: AsyncSession) -> None:
        """存在しない id で get_role_panel は None を返す。"""
        result = await get_role_panel(db_session, 999999)
        assert result is None

    async def test_get_role_panel_by_message_id_nonexistent(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない message_id で get_role_panel_by_message_id は None を返す。"""
        result = await get_role_panel_by_message_id(db_session, "999999999999999999")
        assert result is None

    async def test_get_autoban_rule_nonexistent(self, db_session: AsyncSession) -> None:
        """存在しない id で get_autoban_rule は None を返す。"""
        result = await get_autoban_rule(db_session, 999999)
        assert result is None


class TestDeleteOperationsEdgeCases:
    """delete_* 系関数のエッジケーステスト。"""

    async def test_delete_lobby_nonexistent(self, db_session: AsyncSession) -> None:
        """存在しないロビーの削除は False を返す。"""
        result = await delete_lobby(db_session, 999999)
        assert result is False

    async def test_delete_sticky_nonexistent(self, db_session: AsyncSession) -> None:
        """存在しない sticky の削除は False を返す。"""
        result = await delete_sticky_message(db_session, "999999999999999999")
        assert result is False

    async def test_delete_bump_config_nonexistent(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない bump config の削除は False を返す。"""
        result = await delete_bump_config(db_session, "999999999999999999")
        assert result is False

    async def test_delete_role_panel_nonexistent(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないロールパネルの削除は False を返す。"""
        result = await delete_role_panel(db_session, 999999)
        assert result is False

    async def test_delete_autoban_rule_nonexistent(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない autoban ルールの削除は False を返す。"""
        result = await delete_autoban_rule(db_session, 999999)
        assert result is False


class TestBulkDeleteEdgeCases:
    """一括削除関数のエッジケーステスト。"""

    async def test_delete_lobbies_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドのロビー一括削除は 0 を返す。"""
        result = await delete_lobbies_by_guild(db_session, "999999999999999999")
        assert result == 0

    async def test_delete_voice_sessions_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドの VC セッション一括削除は 0 を返す。"""
        result = await delete_voice_sessions_by_guild(db_session, "999999999999999999")
        assert result == 0

    async def test_delete_sticky_messages_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドの sticky 一括削除は 0 を返す。"""
        result = await delete_sticky_messages_by_guild(db_session, "999999999999999999")
        assert result == 0

    async def test_delete_bump_reminders_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドの bump リマインダー一括削除は 0 を返す。"""
        result = await delete_bump_reminders_by_guild(db_session, "999999999999999999")
        assert result == 0

    async def test_delete_role_panels_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドのロールパネル一括削除は 0 を返す。"""
        result = await delete_role_panels_by_guild(db_session, "999999999999999999")
        assert result == 0

    async def test_delete_discord_roles_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドの discord ロール一括削除は 0 を返す。"""
        result = await delete_discord_roles_by_guild(db_session, "999999999999999999")
        assert result == 0

    async def test_delete_discord_channels_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドの discord チャンネル一括削除は 0 を返す。"""
        result = await delete_discord_channels_by_guild(
            db_session, "999999999999999999"
        )
        assert result == 0


class TestListOperationsEdgeCases:
    """リスト取得関数のエッジケーステスト。"""

    async def test_get_all_lobbies_empty(self, db_session: AsyncSession) -> None:
        """ロビーがない場合は空リストを返す。"""
        result = await get_all_lobbies(db_session)
        assert result == []

    async def test_get_all_voice_sessions_empty(self, db_session: AsyncSession) -> None:
        """VC セッションがない場合は空リストを返す。"""
        result = await get_all_voice_sessions(db_session)
        assert result == []

    async def test_get_all_sticky_messages_empty(
        self, db_session: AsyncSession
    ) -> None:
        """sticky がない場合は空リストを返す。"""
        result = await get_all_sticky_messages(db_session)
        assert result == []

    async def test_get_all_bump_configs_empty(self, db_session: AsyncSession) -> None:
        """bump config がない場合は空リストを返す。"""
        result = await get_all_bump_configs(db_session)
        assert result == []

    async def test_get_all_discord_guilds_empty(self, db_session: AsyncSession) -> None:
        """discord guild がない場合は空リストを返す。"""
        result = await get_all_discord_guilds(db_session)
        assert result == []

    async def test_get_all_autoban_rules_empty(self, db_session: AsyncSession) -> None:
        """autoban ルールがない場合は空リストを返す。"""
        result = await get_all_autoban_rules(db_session)
        assert result == []

    async def test_get_all_autoban_logs_empty(self, db_session: AsyncSession) -> None:
        """autoban ログがない場合は空リストを返す。"""
        result = await get_all_autoban_logs(db_session)
        assert result == []

    async def test_get_lobbies_by_guild_empty(self, db_session: AsyncSession) -> None:
        """ギルドにロビーがない場合は空リストを返す。"""
        result = await get_lobbies_by_guild(db_session, "999999999999999999")
        assert result == []

    async def test_get_role_panels_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """ギルドにロールパネルがない場合は空リストを返す。"""
        result = await get_role_panels_by_guild(db_session, "999999999999999999")
        assert result == []

    async def test_get_discord_roles_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """ギルドに discord ロールがない場合は空リストを返す。"""
        result = await get_discord_roles_by_guild(db_session, "999999999999999999")
        assert result == []

    async def test_get_discord_channels_by_guild_empty(
        self, db_session: AsyncSession
    ) -> None:
        """ギルドに discord チャンネルがない場合は空リストを返す。"""
        result = await get_discord_channels_by_guild(db_session, "999999999999999999")
        assert result == []


class TestToggleOperationsEdgeCases:
    """トグル操作のエッジケーステスト。"""

    async def test_toggle_nonexistent_autoban_rule(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない autoban ルールのトグルは None を返す。"""
        result = await toggle_autoban_rule(db_session, 999999)
        assert result is None

    async def test_toggle_nonexistent_bump_reminder_creates_disabled(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない bump リマインダーのトグルは無効状態で新規作成する。"""
        result = await toggle_bump_reminder(db_session, "999999", "nonexistent")
        assert result is False


class TestDueBumpRemindersEdgeCases:
    """get_due_bump_reminders のエッジケーステスト。"""

    async def test_no_due_reminders(self, db_session: AsyncSession) -> None:
        """期限切れのリマインダーがない場合は空リストを返す。"""
        from datetime import UTC, datetime, timedelta

        # 未来のリマインダーを作成
        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=datetime.now(UTC) + timedelta(hours=2),
        )
        result = await get_due_bump_reminders(db_session, datetime.now(UTC))
        assert result == []

    async def test_due_reminder_returned(self, db_session: AsyncSession) -> None:
        """期限切れのリマインダーが返される。"""
        from datetime import UTC, datetime, timedelta

        # 過去のリマインダーを作成
        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        result = await get_due_bump_reminders(db_session, datetime.now(UTC))
        assert len(result) == 1


class TestBanLogOperations:
    """Tests for ban log database operations."""

    @pytest.mark.parametrize(
        ("reason", "is_autoban", "expected_reason"),
        [
            ("Spamming", False, "Spamming"),
            ("[Autoban] No avatar set", True, "[Autoban] No avatar set"),
            (None, False, None),
        ],
        ids=["manual", "autoban", "no_reason"],
    )
    async def test_create_ban_log(
        self,
        db_session: AsyncSession,
        reason: str | None,
        is_autoban: bool,
        expected_reason: str | None,
    ) -> None:
        """BAN ログを作成できる。"""
        log = await create_ban_log(
            db_session,
            guild_id="123",
            user_id="456",
            username="banneduser",
            reason=reason,
            is_autoban=is_autoban,
        )
        assert log.id is not None
        assert log.guild_id == "123"
        assert log.reason == expected_reason
        assert log.is_autoban is is_autoban
        assert log.created_at is not None

    async def test_get_ban_logs(self, db_session: AsyncSession) -> None:
        """Test retrieving ban logs ordered by created_at desc."""
        import asyncio

        log1 = await create_ban_log(
            db_session,
            guild_id="123",
            user_id="u1",
            username="user1",
            reason="First ban",
        )
        # Small delay to ensure different created_at timestamps
        await asyncio.sleep(0.05)
        log2 = await create_ban_log(
            db_session,
            guild_id="456",
            user_id="u2",
            username="user2",
            reason="Second ban",
        )

        logs = await get_ban_logs(db_session)
        assert len(logs) == 2
        # Most recent first
        assert logs[0].id == log2.id
        assert logs[1].id == log1.id

    async def test_get_ban_logs_respects_limit(self, db_session: AsyncSession) -> None:
        """Test that get_ban_logs respects the limit parameter."""
        for i in range(5):
            await create_ban_log(
                db_session,
                guild_id="123",
                user_id=f"u{i}",
                username=f"user{i}",
            )

        logs = await get_ban_logs(db_session, limit=3)
        assert len(logs) == 3

    async def test_get_ban_logs_empty(self, db_session: AsyncSession) -> None:
        """Test retrieving ban logs when none exist."""
        logs = await get_ban_logs(db_session)
        assert logs == []


class TestJoinRoleDbService:
    """Tests for join role CRUD database operations."""

    async def test_create_join_role_config(self, db_session: AsyncSession) -> None:
        """Test creating a join role config."""
        config = await create_join_role_config(
            db_session,
            guild_id="123",
            role_id="456",
            duration_hours=24,
        )
        assert config.id is not None
        assert config.guild_id == "123"
        assert config.role_id == "456"
        assert config.duration_hours == 24
        assert config.enabled is True

    async def test_get_join_role_configs(self, db_session: AsyncSession) -> None:
        """Test getting all join role configs."""
        await create_join_role_config(db_session, "g1", "r1", 24)
        await create_join_role_config(db_session, "g2", "r2", 48)

        configs = await get_join_role_configs(db_session)
        assert len(configs) == 2

    async def test_get_join_role_configs_by_guild(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting join role configs filtered by guild."""
        await create_join_role_config(db_session, "g1", "r1", 24)
        await create_join_role_config(db_session, "g2", "r2", 48)

        configs = await get_join_role_configs(db_session, guild_id="g1")
        assert len(configs) == 1
        assert configs[0].guild_id == "g1"

    async def test_get_enabled_join_role_configs(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting only enabled configs."""
        c1 = await create_join_role_config(db_session, "g1", "r1", 24)
        await create_join_role_config(db_session, "g1", "r2", 48)

        # Disable one
        await toggle_join_role_config(db_session, c1.id)

        enabled = await get_enabled_join_role_configs(db_session, "g1")
        assert len(enabled) == 1
        assert enabled[0].role_id == "r2"

    async def test_delete_join_role_config(self, db_session: AsyncSession) -> None:
        """Test deleting a join role config."""
        config = await create_join_role_config(db_session, "g1", "r1", 24)
        result = await delete_join_role_config(db_session, config.id)
        assert result is True

        configs = await get_join_role_configs(db_session)
        assert len(configs) == 0

    async def test_delete_join_role_config_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting a non-existent join role config."""
        result = await delete_join_role_config(db_session, 999)
        assert result is False

    async def test_toggle_join_role_config(self, db_session: AsyncSession) -> None:
        """Test toggling a join role config."""
        config = await create_join_role_config(db_session, "g1", "r1", 24)
        assert config.enabled is True

        toggled = await toggle_join_role_config(db_session, config.id)
        assert toggled is not None
        assert toggled.enabled is False

        toggled2 = await toggle_join_role_config(db_session, config.id)
        assert toggled2 is not None
        assert toggled2.enabled is True

    async def test_toggle_join_role_config_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test toggling a non-existent join role config."""
        result = await toggle_join_role_config(db_session, 999)
        assert result is None

    async def test_create_join_role_assignment(self, db_session: AsyncSession) -> None:
        """Test creating a join role assignment."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        assignment = await create_join_role_assignment(
            db_session,
            guild_id="g1",
            user_id="u1",
            role_id="r1",
            assigned_at=now,
            expires_at=now + timedelta(hours=24),
        )
        assert assignment.id is not None
        assert assignment.guild_id == "g1"
        assert assignment.user_id == "u1"
        assert assignment.role_id == "r1"

    async def test_get_expired_join_role_assignments(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting expired assignments."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        # Expired
        await create_join_role_assignment(
            db_session,
            "g1",
            "u1",
            "r1",
            now - timedelta(hours=25),
            now - timedelta(hours=1),
        )
        # Not yet expired
        await create_join_role_assignment(
            db_session, "g1", "u2", "r1", now, now + timedelta(hours=23)
        )

        expired = await get_expired_join_role_assignments(db_session, now)
        assert len(expired) == 1
        assert expired[0].user_id == "u1"

    async def test_delete_join_role_assignment(self, db_session: AsyncSession) -> None:
        """Test deleting a join role assignment."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        assignment = await create_join_role_assignment(
            db_session, "g1", "u1", "r1", now, now + timedelta(hours=24)
        )
        result = await delete_join_role_assignment(db_session, assignment.id)
        assert result is True

    async def test_delete_join_role_assignment_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting a non-existent assignment."""
        result = await delete_join_role_assignment(db_session, 999)
        assert result is False

    async def test_get_expired_exact_boundary(self, db_session: AsyncSession) -> None:
        """expires_at == now のレコードは期限切れとして取得される。"""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        await create_join_role_assignment(
            db_session, "g1", "u1", "r1", now - timedelta(hours=24), now
        )
        expired = await get_expired_join_role_assignments(db_session, now)
        assert len(expired) == 1

    async def test_get_expired_just_before_boundary(
        self, db_session: AsyncSession
    ) -> None:
        """expires_at が now の1秒後のレコードは期限切れにならない。"""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        await create_join_role_assignment(
            db_session,
            "g1",
            "u1",
            "r1",
            now - timedelta(hours=24),
            now + timedelta(seconds=1),
        )
        expired = await get_expired_join_role_assignments(db_session, now)
        assert len(expired) == 0

    async def test_get_enabled_all_disabled(self, db_session: AsyncSession) -> None:
        """全て無効の場合、空リストが返る。"""
        c1 = await create_join_role_config(db_session, "g1", "r1", 24)
        c2 = await create_join_role_config(db_session, "g1", "r2", 48)
        await toggle_join_role_config(db_session, c1.id)
        await toggle_join_role_config(db_session, c2.id)

        enabled = await get_enabled_join_role_configs(db_session, "g1")
        assert len(enabled) == 0

    async def test_create_duplicate_guild_role_raises(
        self, db_session: AsyncSession
    ) -> None:
        """同じ guild_id + role_id の二重登録は IntegrityError。"""
        from sqlalchemy.exc import IntegrityError

        await create_join_role_config(db_session, "g1", "r1", 24)
        with pytest.raises(IntegrityError):
            await create_join_role_config(db_session, "g1", "r1", 48)

    async def test_multiple_assignments_same_user(
        self, db_session: AsyncSession
    ) -> None:
        """同一ユーザーの複数ロール割り当てが共存できる。"""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        a1 = await create_join_role_assignment(
            db_session, "g1", "u1", "r1", now, now + timedelta(hours=24)
        )
        a2 = await create_join_role_assignment(
            db_session, "g1", "u1", "r2", now, now + timedelta(hours=48)
        )
        assert a1.id != a2.id
        assert a1.role_id == "r1"
        assert a2.role_id == "r2"


class TestClaimJoinRoleAssignment:
    """claim_join_role_assignment のアトミック重複防止テスト。"""

    async def test_first_claim_creates_assignment(
        self, db_session: AsyncSession
    ) -> None:
        """初回 claim はレコードを作成する。"""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        a = await claim_join_role_assignment(
            db_session,
            guild_id="123",
            user_id="u1",
            role_id="r1",
            assigned_at=now,
            expires_at=now + timedelta(hours=24),
        )
        assert a is not None
        assert a.guild_id == "123"
        assert a.user_id == "u1"

    async def test_duplicate_claim_returns_none(self, db_session: AsyncSession) -> None:
        """10 秒以内の同一 claim は None を返す。"""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        a1 = await claim_join_role_assignment(
            db_session,
            guild_id="123",
            user_id="u1",
            role_id="r1",
            assigned_at=now,
            expires_at=now + timedelta(hours=24),
        )
        assert a1 is not None

        a2 = await claim_join_role_assignment(
            db_session,
            guild_id="123",
            user_id="u1",
            role_id="r1",
            assigned_at=now,
            expires_at=now + timedelta(hours=24),
        )
        assert a2 is None

    async def test_different_role_not_duplicate(self, db_session: AsyncSession) -> None:
        """異なるロールなら重複にならない。"""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        a1 = await claim_join_role_assignment(
            db_session,
            guild_id="123",
            user_id="u1",
            role_id="r1",
            assigned_at=now,
            expires_at=now + timedelta(hours=24),
        )
        a2 = await claim_join_role_assignment(
            db_session,
            guild_id="123",
            user_id="u1",
            role_id="r2",
            assigned_at=now,
            expires_at=now + timedelta(hours=24),
        )
        assert a1 is not None
        assert a2 is not None


# ===========================================================================
# IntroPost CRUD
# ===========================================================================


class TestIntroPostCRUD:
    """record_intro_post / has_intro_post / delete_intro_posts_by_guild のテスト。"""

    @pytest.mark.asyncio
    async def test_record_intro_post(self, db_session: AsyncSession) -> None:
        """投稿を記録できる。"""
        await record_intro_post(db_session, "g1", "u1", "c1")
        result = await has_intro_post(db_session, "g1", "u1", "c1")
        assert result is True

    @pytest.mark.asyncio
    async def test_record_intro_post_duplicate(self, db_session: AsyncSession) -> None:
        """重複記録はエラーなし。"""
        await record_intro_post(db_session, "g1", "u1", "c1")
        await record_intro_post(db_session, "g1", "u1", "c1")
        result = await has_intro_post(db_session, "g1", "u1", "c1")
        assert result is True

    @pytest.mark.asyncio
    async def test_has_intro_post_not_found(self, db_session: AsyncSession) -> None:
        """投稿がなければ False。"""
        result = await has_intro_post(db_session, "g1", "u1", "c1")
        assert result is False

    @pytest.mark.asyncio
    async def test_has_intro_post_different_channel(
        self, db_session: AsyncSession
    ) -> None:
        """異なるチャンネルでは False。"""
        await record_intro_post(db_session, "g1", "u1", "c1")
        result = await has_intro_post(db_session, "g1", "u1", "c2")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_intro_posts_by_guild(self, db_session: AsyncSession) -> None:
        """ギルド単位で削除できる。"""
        await record_intro_post(db_session, "g1", "u1", "c1")
        await record_intro_post(db_session, "g1", "u2", "c1")
        await record_intro_post(db_session, "g2", "u1", "c1")

        count = await delete_intro_posts_by_guild(db_session, "g1")
        assert count == 2

        assert await has_intro_post(db_session, "g1", "u1", "c1") is False
        assert await has_intro_post(db_session, "g2", "u1", "c1") is True

    @pytest.mark.asyncio
    async def test_delete_intro_posts_empty_guild(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないギルドの削除は 0。"""
        count = await delete_intro_posts_by_guild(db_session, "nonexistent")
        assert count == 0


# ===========================================================================
# ProcessedEvent (重複排除テーブル) 操作
# ===========================================================================


class TestClaimEvent:
    """claim_event のアトミック重複防止テスト。"""

    @pytest.mark.asyncio
    async def test_first_claim_succeeds(self, db_session: AsyncSession) -> None:
        """初回 claim は True を返す。"""
        result = await claim_event(db_session, "test:event:1")
        assert result is True

    @pytest.mark.asyncio
    async def test_duplicate_claim_returns_false(
        self, db_session: AsyncSession
    ) -> None:
        """同一 event_key の2回目の claim は False を返す。"""
        result1 = await claim_event(db_session, "test:event:dup")
        assert result1 is True

        result2 = await claim_event(db_session, "test:event:dup")
        assert result2 is False

    @pytest.mark.asyncio
    async def test_different_keys_both_succeed(self, db_session: AsyncSession) -> None:
        """異なる event_key なら両方 claim 成功。"""
        r1 = await claim_event(db_session, "test:event:a")
        r2 = await claim_event(db_session, "test:event:b")
        assert r1 is True
        assert r2 is True

    @pytest.mark.asyncio
    async def test_claim_after_duplicate_still_works(
        self, db_session: AsyncSession
    ) -> None:
        """重複 claim (rollback) 後でも別キーの claim が成功する。"""
        await claim_event(db_session, "test:event:first")
        await claim_event(db_session, "test:event:first")  # False + rollback

        result = await claim_event(db_session, "test:event:second")
        assert result is True


class TestCleanupExpiredEvents:
    """cleanup_expired_events のテスト。"""

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_records(self, db_session: AsyncSession) -> None:
        """古いレコードが削除される。"""
        from datetime import UTC, datetime, timedelta

        from src.database.models import ProcessedEvent

        # 2時間前のレコードを直接挿入
        old_event = ProcessedEvent(
            event_key="old:event",
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )
        db_session.add(old_event)
        await db_session.commit()

        deleted = await cleanup_expired_events(db_session, max_age_seconds=3600)
        assert deleted == 1

    @pytest.mark.asyncio
    async def test_cleanup_keeps_recent_records(self, db_session: AsyncSession) -> None:
        """新しいレコードは削除されない。"""
        await claim_event(db_session, "recent:event")

        deleted = await cleanup_expired_events(db_session, max_age_seconds=3600)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cleanup_returns_zero_when_empty(
        self, db_session: AsyncSession
    ) -> None:
        """テーブルが空なら 0。"""
        deleted = await cleanup_expired_events(db_session)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cleanup_mixed_old_and_recent(self, db_session: AsyncSession) -> None:
        """古いレコードのみ削除し、新しいレコードは残す。"""
        from datetime import UTC, datetime, timedelta

        from src.database.models import ProcessedEvent

        # 古いレコード 3 件
        for i in range(3):
            db_session.add(
                ProcessedEvent(
                    event_key=f"old:{i}",
                    created_at=datetime.now(UTC) - timedelta(hours=2),
                )
            )
        await db_session.commit()

        # 新しいレコード 2 件
        for i in range(2):
            await claim_event(db_session, f"recent:{i}")

        deleted = await cleanup_expired_events(db_session, max_age_seconds=3600)
        assert deleted == 3

    @pytest.mark.asyncio
    async def test_cleanup_respects_custom_max_age(
        self, db_session: AsyncSession
    ) -> None:
        """カスタム max_age_seconds が正しく適用される。"""
        from datetime import UTC, datetime, timedelta

        from src.database.models import ProcessedEvent

        # 45分前 (30分以上、1時間未満)
        db_session.add(
            ProcessedEvent(
                event_key="mid:age",
                created_at=datetime.now(UTC) - timedelta(minutes=45),
            )
        )
        await db_session.commit()

        # デフォルト (1時間) では削除されない
        deleted = await cleanup_expired_events(db_session, max_age_seconds=3600)
        assert deleted == 0

        # 30分指定なら削除される
        deleted = await cleanup_expired_events(db_session, max_age_seconds=1800)
        assert deleted == 1

    @pytest.mark.asyncio
    async def test_cleanup_boundary_not_deleted(self, db_session: AsyncSession) -> None:
        """ちょうどカットオフ時刻のレコードは削除されない (< 条件)。"""
        from datetime import UTC, datetime, timedelta

        from src.database.models import ProcessedEvent

        # ちょうど 1秒前 (max_age=3600 → カットオフより新しい)
        db_session.add(
            ProcessedEvent(
                event_key="boundary:event",
                created_at=datetime.now(UTC) - timedelta(seconds=3599),
            )
        )
        await db_session.commit()

        deleted = await cleanup_expired_events(db_session, max_age_seconds=3600)
        assert deleted == 0


class TestClaimEventSessionRecovery:
    """claim_event の IntegrityError 後のセッション復旧テスト。"""

    @pytest.mark.asyncio
    async def test_session_usable_after_duplicate_claim(
        self, db_session: AsyncSession
    ) -> None:
        """重複 claim (rollback) 後も他の DB 操作が可能。"""
        await claim_event(db_session, "key:recovery:1")
        result = await claim_event(db_session, "key:recovery:1")  # False + rollback
        assert result is False

        # rollback 後にロビー作成が成功することを確認
        lobby = await create_lobby(db_session, guild_id="111", lobby_channel_id="222")
        assert lobby.id is not None

    @pytest.mark.asyncio
    async def test_different_operations_after_rollback(
        self, db_session: AsyncSession
    ) -> None:
        """重複 claim の rollback 後に異なる DB 操作が連続で成功する。"""
        await claim_event(db_session, "ops:after:rollback")
        await claim_event(db_session, "ops:after:rollback")  # False + rollback

        # rollback 後にロビー作成 → 更にイベント claim → 両方成功
        lobby = await create_lobby(db_session, guild_id="333", lobby_channel_id="444")
        assert lobby.id is not None

        result = await claim_event(db_session, "ops:after:rollback:2")
        assert result is True


class TestGetBotActivity:
    """Tests for get_bot_activity."""

    async def test_returns_none_when_no_record(self, db_session: AsyncSession) -> None:
        """レコードがない場合は None を返す。"""
        result = await get_bot_activity(db_session)
        assert result is None

    async def test_returns_existing_record(self, db_session: AsyncSession) -> None:
        """レコードが存在する場合はそれを返す。"""
        await upsert_bot_activity(db_session, "watching", "配信中")
        result = await get_bot_activity(db_session)
        assert result is not None
        assert result.activity_type == "watching"
        assert result.activity_text == "配信中"


class TestUpsertBotActivity:
    """Tests for upsert_bot_activity."""

    async def test_create_new_record(self, db_session: AsyncSession) -> None:
        """レコードがない場合は新規作成する。"""
        result = await upsert_bot_activity(db_session, "playing", "テストゲーム")
        assert result.id is not None
        assert result.activity_type == "playing"
        assert result.activity_text == "テストゲーム"

    async def test_update_existing_record(self, db_session: AsyncSession) -> None:
        """レコードが既に存在する場合は更新する。"""
        first = await upsert_bot_activity(db_session, "playing", "最初のテキスト")
        first_id = first.id
        first_updated_at = first.updated_at

        second = await upsert_bot_activity(db_session, "listening", "音楽")
        assert second.id == first_id
        assert second.activity_type == "listening"
        assert second.activity_text == "音楽"
        assert second.updated_at >= first_updated_at

    async def test_upsert_returns_bot_activity(self, db_session: AsyncSession) -> None:
        """upsert の戻り値が BotActivity インスタンスである。"""
        from src.database.models import BotActivity

        result = await upsert_bot_activity(db_session, "competing", "大会参加中")
        assert isinstance(result, BotActivity)

    async def test_upsert_persists_to_db(self, db_session: AsyncSession) -> None:
        """upsert した結果が DB に永続化されている。"""
        await upsert_bot_activity(db_session, "watching", "動画")

        # 別途取得して確認
        fetched = await get_bot_activity(db_session)
        assert fetched is not None
        assert fetched.activity_type == "watching"
        assert fetched.activity_text == "動画"
