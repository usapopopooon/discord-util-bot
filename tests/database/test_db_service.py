"""Tests for db_service using factory fixtures and faker."""

from __future__ import annotations

from datetime import UTC

import pytest
from faker import Faker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Lobby, VoiceSession
from src.services.db_service import (
    add_role_panel_item,
    add_voice_session_member,
    clear_bump_reminder,
    create_lobby,
    create_role_panel,
    create_sticky_message,
    create_voice_session,
    delete_bump_config,
    delete_lobby,
    delete_role_panel,
    delete_sticky_message,
    delete_voice_session,
    get_all_role_panels,
    get_all_sticky_messages,
    get_all_voice_sessions,
    get_bump_config,
    get_bump_reminder,
    get_due_bump_reminders,
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
    remove_role_panel_item,
    remove_voice_session_member,
    toggle_bump_reminder,
    update_bump_reminder_role,
    update_role_panel,
    update_sticky_message_id,
    update_voice_session,
    upsert_bump_config,
    upsert_bump_reminder,
)

from .conftest import snowflake

fake = Faker()


# ===========================================================================
# Lobby CRUD — faker 利用
# ===========================================================================


class TestLobbyWithFaker:
    """faker で生成したデータでの Lobby テスト。"""

    async def test_create_with_all_options(self, db_session: AsyncSession) -> None:
        """全オプション指定で Lobby を作成できる。"""
        gid = snowflake()
        cid = snowflake()
        cat = snowflake()
        limit = fake.random_int(min=1, max=99)

        lobby = await create_lobby(
            db_session,
            guild_id=gid,
            lobby_channel_id=cid,
            category_id=cat,
            default_user_limit=limit,
        )

        assert lobby.guild_id == gid
        assert lobby.lobby_channel_id == cid
        assert lobby.category_id == cat
        assert lobby.default_user_limit == limit
        assert lobby.id is not None

    async def test_get_by_channel_returns_correct_lobby(
        self, db_session: AsyncSession
    ) -> None:
        """複数ロビー存在時に正しいロビーが返る。"""
        target_cid = snowflake()
        await create_lobby(
            db_session, guild_id=snowflake(), lobby_channel_id=snowflake()
        )
        await create_lobby(
            db_session, guild_id=snowflake(), lobby_channel_id=target_cid
        )

        found = await get_lobby_by_channel_id(db_session, target_cid)
        assert found is not None
        assert found.lobby_channel_id == target_cid

    async def test_get_lobbies_filters_by_guild(self, db_session: AsyncSession) -> None:
        """guild_id でフィルタされる。"""
        guild_a = snowflake()
        guild_b = snowflake()
        for _ in range(3):
            await create_lobby(
                db_session,
                guild_id=guild_a,
                lobby_channel_id=snowflake(),
            )
        for _ in range(2):
            await create_lobby(
                db_session,
                guild_id=guild_b,
                lobby_channel_id=snowflake(),
            )

        assert len(await get_lobbies_by_guild(db_session, guild_a)) == 3
        assert len(await get_lobbies_by_guild(db_session, guild_b)) == 2

    async def test_get_lobbies_empty_guild(self, db_session: AsyncSession) -> None:
        """存在しないギルドは空リスト。"""
        result = await get_lobbies_by_guild(db_session, snowflake())
        assert result == []

    async def test_delete_lobby_cascades(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """ロビー削除でセッションもカスケード削除される。"""
        ch_id = snowflake()
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=ch_id,
            owner_id=snowflake(),
            name=fake.word(),
        )

        result = await delete_lobby(db_session, lobby.id)
        assert result is True

        assert await get_voice_session(db_session, ch_id) is None

    async def test_delete_nonexistent_lobby(self, db_session: AsyncSession) -> None:
        """存在しない ID の削除は False。"""
        assert await delete_lobby(db_session, 999999) is False


# ===========================================================================
# VoiceSession CRUD — faker + fixture 利用
# ===========================================================================


class TestVoiceSessionWithFaker:
    """faker/fixture で生成したデータでの VoiceSession テスト。"""

    async def test_create_with_user_limit(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """user_limit 指定で作成できる。"""
        limit = fake.random_int(min=1, max=99)
        vs = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name=fake.word(),
            user_limit=limit,
        )
        assert vs.user_limit == limit

    async def test_get_session_returns_correct_one(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """複数セッション存在時に正しいものが返る。"""
        target_cid = snowflake()
        for _ in range(3):
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=snowflake(),
                owner_id=snowflake(),
                name=fake.word(),
            )
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=target_cid,
            owner_id=snowflake(),
            name="target",
        )

        found = await get_voice_session(db_session, target_cid)
        assert found is not None
        assert found.name == "target"

    async def test_get_all_sessions(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """get_all_voice_sessions が全件返す。"""
        count = fake.random_int(min=2, max=5)
        for _ in range(count):
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=snowflake(),
                owner_id=snowflake(),
                name=fake.word(),
            )

        sessions = await get_all_voice_sessions(db_session)
        assert len(sessions) == count

    async def test_get_all_sessions_empty(self, db_session: AsyncSession) -> None:
        """セッションがなければ空リスト。"""
        assert await get_all_voice_sessions(db_session) == []


class TestUpdateVoiceSession:
    """update_voice_session の各フィールド個別テスト。"""

    async def test_update_name(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """名前だけ更新できる。"""
        new_name = fake.word()
        updated = await update_voice_session(db_session, voice_session, name=new_name)
        assert updated.name == new_name

    async def test_update_user_limit(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """user_limit だけ更新できる。"""
        new_limit = fake.random_int(min=1, max=99)
        updated = await update_voice_session(
            db_session, voice_session, user_limit=new_limit
        )
        assert updated.user_limit == new_limit

    async def test_update_is_locked(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """is_locked だけ更新できる。"""
        updated = await update_voice_session(db_session, voice_session, is_locked=True)
        assert updated.is_locked is True

    async def test_update_is_locked_toggle(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """is_locked をトグルできる (True → False)。"""
        # まずロック
        locked = await update_voice_session(db_session, voice_session, is_locked=True)
        assert locked.is_locked is True
        # 次にアンロック
        unlocked = await update_voice_session(db_session, locked, is_locked=False)
        assert unlocked.is_locked is False

    async def test_update_is_hidden(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """is_hidden だけ更新できる。"""
        updated = await update_voice_session(db_session, voice_session, is_hidden=True)
        assert updated.is_hidden is True

    async def test_update_is_hidden_toggle(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """is_hidden をトグルできる (True → False)。"""
        # まず非表示
        hidden = await update_voice_session(db_session, voice_session, is_hidden=True)
        assert hidden.is_hidden is True
        # 次に表示
        visible = await update_voice_session(db_session, hidden, is_hidden=False)
        assert visible.is_hidden is False

    async def test_update_owner_id(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """owner_id だけ更新（譲渡）できる。"""
        new_owner = snowflake()
        updated = await update_voice_session(
            db_session, voice_session, owner_id=new_owner
        )
        assert updated.owner_id == new_owner

    async def test_update_multiple_fields(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """複数フィールド同時更新。"""
        new_name = fake.word()
        new_owner = snowflake()
        updated = await update_voice_session(
            db_session,
            voice_session,
            name=new_name,
            is_locked=True,
            is_hidden=True,
            owner_id=new_owner,
        )
        assert updated.name == new_name
        assert updated.is_locked is True
        assert updated.is_hidden is True
        assert updated.owner_id == new_owner

    async def test_update_no_params_unchanged(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """パラメータなしなら変更なし。"""
        original_name = voice_session.name
        original_owner = voice_session.owner_id
        updated = await update_voice_session(db_session, voice_session)
        assert updated.name == original_name
        assert updated.owner_id == original_owner


class TestUpdateVoiceSessionEdgeCases:
    """update_voice_session のエッジケーステスト。"""

    async def test_update_is_locked_same_value_no_op(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """同じ値で更新しても問題ない (is_locked=False → False)。"""
        assert voice_session.is_locked is False
        updated = await update_voice_session(db_session, voice_session, is_locked=False)
        assert updated.is_locked is False

    async def test_update_is_locked_rapid_toggle(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """連続してトグルしても正しく動作する。"""
        # False → True
        s1 = await update_voice_session(db_session, voice_session, is_locked=True)
        assert s1.is_locked is True
        # True → False
        s2 = await update_voice_session(db_session, s1, is_locked=False)
        assert s2.is_locked is False
        # False → True
        s3 = await update_voice_session(db_session, s2, is_locked=True)
        assert s3.is_locked is True
        # True → False
        s4 = await update_voice_session(db_session, s3, is_locked=False)
        assert s4.is_locked is False

    async def test_update_both_locked_and_hidden(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """ロックと非表示を同時に設定できる。"""
        updated = await update_voice_session(
            db_session, voice_session, is_locked=True, is_hidden=True
        )
        assert updated.is_locked is True
        assert updated.is_hidden is True

    async def test_update_unlock_while_hidden(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """非表示のままロック解除できる。"""
        # まず両方設定
        locked_hidden = await update_voice_session(
            db_session, voice_session, is_locked=True, is_hidden=True
        )
        # ロックだけ解除
        unlocked = await update_voice_session(
            db_session, locked_hidden, is_locked=False
        )
        assert unlocked.is_locked is False
        assert unlocked.is_hidden is True  # 非表示は維持

    async def test_update_lock_with_name_change(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """ロックと同時に名前変更できる。"""
        new_name = "🔒ロック済みチャンネル"
        updated = await update_voice_session(
            db_session, voice_session, name=new_name, is_locked=True
        )
        assert updated.name == new_name
        assert updated.is_locked is True

    async def test_update_preserves_other_fields_when_locking(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """ロック時に他のフィールドは変更されない。"""
        original_name = voice_session.name
        original_owner = voice_session.owner_id
        original_user_limit = voice_session.user_limit

        updated = await update_voice_session(db_session, voice_session, is_locked=True)

        assert updated.is_locked is True
        assert updated.name == original_name
        assert updated.owner_id == original_owner
        assert updated.user_limit == original_user_limit

    async def test_update_lock_state_persists_after_refresh(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """ロック状態がDB再取得後も維持される。"""
        channel_id = voice_session.channel_id

        # ロック
        await update_voice_session(db_session, voice_session, is_locked=True)

        # 再取得して確認
        refreshed = await get_voice_session(db_session, channel_id)
        assert refreshed is not None
        assert refreshed.is_locked is True

    async def test_update_empty_name_with_lock(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """空の名前でもロックできる。"""
        updated = await update_voice_session(
            db_session, voice_session, name="", is_locked=True
        )
        assert updated.name == ""
        assert updated.is_locked is True

    async def test_update_unicode_name_with_lock(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """Unicode文字を含む名前でロックできる。"""
        unicode_name = "🔒日本語チャンネル🎵"
        updated = await update_voice_session(
            db_session, voice_session, name=unicode_name, is_locked=True
        )
        assert updated.name == unicode_name
        assert updated.is_locked is True


class TestDeleteVoiceSession:
    """delete_voice_session のテスト。"""

    async def test_delete_existing(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """存在するセッションを削除できる。"""
        ch_id = voice_session.channel_id
        assert await delete_voice_session(db_session, ch_id) is True
        assert await get_voice_session(db_session, ch_id) is None

    async def test_delete_nonexistent(self, db_session: AsyncSession) -> None:
        """存在しない channel_id の削除は False。"""
        assert await delete_voice_session(db_session, snowflake()) is False

    async def test_delete_does_not_affect_others(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """1つ削除しても他のセッションに影響しない。"""
        ch_keep = snowflake()
        ch_delete = snowflake()
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=ch_keep,
            owner_id=snowflake(),
            name="keep",
        )
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=ch_delete,
            owner_id=snowflake(),
            name="delete",
        )

        await delete_voice_session(db_session, ch_delete)

        kept = await get_voice_session(db_session, ch_keep)
        assert kept is not None
        assert kept.name == "keep"


# ===========================================================================
# エッジケース — FK 違反・重複・ロールバック
# ===========================================================================


class TestServiceEdgeCases:
    """サービス関数のエッジケーステスト。"""

    async def test_create_lobby_duplicate_channel_id(
        self, db_session: AsyncSession
    ) -> None:
        """同じ lobby_channel_id で create_lobby を2回呼ぶと IntegrityError。"""
        cid = snowflake()
        await create_lobby(db_session, guild_id=snowflake(), lobby_channel_id=cid)
        with pytest.raises(IntegrityError):
            await create_lobby(db_session, guild_id=snowflake(), lobby_channel_id=cid)

    async def test_create_voice_session_duplicate_channel_id(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """同じ channel_id で create_voice_session を2回呼ぶと IntegrityError。"""
        cid = snowflake()
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=cid,
            owner_id=snowflake(),
            name=fake.word(),
        )
        with pytest.raises(IntegrityError):
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=cid,
                owner_id=snowflake(),
                name=fake.word(),
            )

    async def test_create_voice_session_invalid_lobby_id(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない lobby_id で create_voice_session は IntegrityError。"""
        with pytest.raises(IntegrityError):
            await create_voice_session(
                db_session,
                lobby_id=999999,
                channel_id=snowflake(),
                owner_id=snowflake(),
                name="orphan",
            )

    async def test_get_lobby_by_channel_id_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない channel_id は None を返す。"""
        result = await get_lobby_by_channel_id(db_session, snowflake())
        assert result is None

    async def test_get_voice_session_not_found(self, db_session: AsyncSession) -> None:
        """存在しない channel_id は None を返す。"""
        result = await get_voice_session(db_session, snowflake())
        assert result is None

    async def test_delete_lobby_returns_false_for_missing(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない lobby_id の delete_lobby は False。"""
        assert await delete_lobby(db_session, 0) is False

    async def test_update_voice_session_preserves_unmodified(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """name だけ更新すると他のフィールドは変わらない。"""
        original_owner = voice_session.owner_id
        original_limit = voice_session.user_limit
        original_locked = voice_session.is_locked
        original_hidden = voice_session.is_hidden

        await update_voice_session(db_session, voice_session, name="changed")

        assert voice_session.name == "changed"
        assert voice_session.owner_id == original_owner
        assert voice_session.user_limit == original_limit
        assert voice_session.is_locked == original_locked
        assert voice_session.is_hidden == original_hidden

    async def test_create_and_immediately_delete_lobby(
        self, db_session: AsyncSession
    ) -> None:
        """作成直後に削除できる。"""
        lobby = await create_lobby(
            db_session, guild_id=snowflake(), lobby_channel_id=snowflake()
        )
        assert await delete_lobby(db_session, lobby.id) is True
        assert await delete_lobby(db_session, lobby.id) is False

    async def test_create_and_immediately_delete_session(
        self, db_session: AsyncSession, lobby: Lobby
    ) -> None:
        """作成直後にセッション削除できる。"""
        cid = snowflake()
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=cid,
            owner_id=snowflake(),
            name=fake.word(),
        )
        assert await delete_voice_session(db_session, cid) is True
        assert await delete_voice_session(db_session, cid) is False

    async def test_get_lobbies_by_guild_isolation(
        self, db_session: AsyncSession
    ) -> None:
        """異なるギルドのロビーは混在しない。"""
        g1, g2 = snowflake(), snowflake()
        await create_lobby(db_session, guild_id=g1, lobby_channel_id=snowflake())
        await create_lobby(db_session, guild_id=g1, lobby_channel_id=snowflake())
        await create_lobby(db_session, guild_id=g2, lobby_channel_id=snowflake())

        assert len(await get_lobbies_by_guild(db_session, g1)) == 2
        assert len(await get_lobbies_by_guild(db_session, g2)) == 1
        assert len(await get_lobbies_by_guild(db_session, snowflake())) == 0

    async def test_delete_lobby_cascades_multiple_sessions(
        self, db_session: AsyncSession
    ) -> None:
        """複数セッションを持つロビーを削除するとすべてカスケード削除。"""
        lobby = await create_lobby(
            db_session, guild_id=snowflake(), lobby_channel_id=snowflake()
        )
        channels = []
        for _ in range(5):
            cid = snowflake()
            channels.append(cid)
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=cid,
                owner_id=snowflake(),
                name=fake.word(),
            )

        assert await delete_lobby(db_session, lobby.id) is True

        for cid in channels:
            assert await get_voice_session(db_session, cid) is None

    async def test_update_session_back_to_defaults(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """フィールドを変更後、デフォルト値に戻せる。"""
        await update_voice_session(
            db_session,
            voice_session,
            is_locked=True,
            is_hidden=True,
            user_limit=50,
        )
        assert voice_session.is_locked is True

        await update_voice_session(
            db_session,
            voice_session,
            is_locked=False,
            is_hidden=False,
            user_limit=0,
        )
        assert voice_session.is_locked is False
        assert voice_session.is_hidden is False
        assert voice_session.user_limit == 0


# ===========================================================================
# RolePanel CRUD — faker 利用
# ===========================================================================


class TestRolePanelWithFaker:
    """faker で生成したデータでの RolePanel テスト。"""

    async def test_create_button_panel(self, db_session: AsyncSession) -> None:
        """ボタン式パネルを作成できる。"""
        gid = snowflake()
        cid = snowflake()
        title = fake.sentence(nb_words=3)

        panel = await create_role_panel(
            db_session,
            guild_id=gid,
            channel_id=cid,
            panel_type="button",
            title=title,
        )

        assert panel.guild_id == gid
        assert panel.channel_id == cid
        assert panel.panel_type == "button"
        assert panel.title == title
        assert panel.id is not None

    async def test_create_reaction_panel(self, db_session: AsyncSession) -> None:
        """リアクション式パネルを作成できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="reaction",
            title="Reaction Panel",
        )

        assert panel.panel_type == "reaction"

    async def test_create_panel_with_all_options(
        self, db_session: AsyncSession
    ) -> None:
        """全オプション指定でパネルを作成できる。"""
        gid = snowflake()
        cid = snowflake()
        title = fake.sentence(nb_words=3)
        desc = fake.paragraph()
        color = fake.random_int(min=0, max=0xFFFFFF)

        panel = await create_role_panel(
            db_session,
            guild_id=gid,
            channel_id=cid,
            panel_type="button",
            title=title,
            description=desc,
            color=color,
            remove_reaction=True,
        )

        assert panel.description == desc
        assert panel.color == color
        assert panel.remove_reaction is True

    async def test_get_panel_by_id(self, db_session: AsyncSession) -> None:
        """ID でパネルを取得できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        found = await get_role_panel(db_session, panel.id)
        assert found is not None
        assert found.id == panel.id

    async def test_get_panel_by_id_not_found(self, db_session: AsyncSession) -> None:
        """存在しない ID は None を返す。"""
        result = await get_role_panel(db_session, 999999)
        assert result is None

    async def test_get_panel_by_message_id(self, db_session: AsyncSession) -> None:
        """message_id でパネルを取得できる。"""
        mid = snowflake()
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )
        await update_role_panel(db_session, panel, message_id=mid)

        found = await get_role_panel_by_message_id(db_session, mid)
        assert found is not None
        assert found.message_id == mid

    async def test_get_panel_by_message_id_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない message_id は None を返す。"""
        result = await get_role_panel_by_message_id(db_session, snowflake())
        assert result is None

    async def test_get_panels_by_guild(self, db_session: AsyncSession) -> None:
        """guild_id でパネル一覧を取得できる。"""
        guild_a = snowflake()
        guild_b = snowflake()
        for _ in range(3):
            await create_role_panel(
                db_session,
                guild_id=guild_a,
                channel_id=snowflake(),
                panel_type="button",
                title=fake.word(),
            )
        for _ in range(2):
            await create_role_panel(
                db_session,
                guild_id=guild_b,
                channel_id=snowflake(),
                panel_type="reaction",
                title=fake.word(),
            )

        assert len(await get_role_panels_by_guild(db_session, guild_a)) == 3
        assert len(await get_role_panels_by_guild(db_session, guild_b)) == 2

    async def test_get_panels_by_guild_empty(self, db_session: AsyncSession) -> None:
        """存在しないギルドは空リスト。"""
        result = await get_role_panels_by_guild(db_session, snowflake())
        assert result == []

    async def test_get_panels_by_channel(self, db_session: AsyncSession) -> None:
        """channel_id でパネル一覧を取得できる。"""
        gid = snowflake()
        cid = snowflake()
        await create_role_panel(
            db_session,
            guild_id=gid,
            channel_id=cid,
            panel_type="button",
            title="Panel 1",
        )
        await create_role_panel(
            db_session,
            guild_id=gid,
            channel_id=cid,
            panel_type="reaction",
            title="Panel 2",
        )

        panels = await get_role_panels_by_channel(db_session, cid)
        assert len(panels) == 2

    async def test_get_all_panels(self, db_session: AsyncSession) -> None:
        """全パネルを取得できる。"""
        count = fake.random_int(min=2, max=5)
        for _ in range(count):
            await create_role_panel(
                db_session,
                guild_id=snowflake(),
                channel_id=snowflake(),
                panel_type="button",
                title=fake.word(),
            )

        panels = await get_all_role_panels(db_session)
        assert len(panels) == count

    async def test_get_all_panels_empty(self, db_session: AsyncSession) -> None:
        """パネルがなければ空リスト。"""
        result = await get_all_role_panels(db_session)
        assert result == []

    async def test_update_panel_title(self, db_session: AsyncSession) -> None:
        """タイトルを更新できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Original",
        )

        updated = await update_role_panel(db_session, panel, title="Updated")
        assert updated.title == "Updated"

    async def test_update_panel_description(self, db_session: AsyncSession) -> None:
        """説明を更新できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        desc = fake.paragraph()
        updated = await update_role_panel(db_session, panel, description=desc)
        assert updated.description == desc

    async def test_update_panel_message_id(self, db_session: AsyncSession) -> None:
        """message_id を更新できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        mid = snowflake()
        updated = await update_role_panel(db_session, panel, message_id=mid)
        assert updated.message_id == mid

    async def test_update_panel_no_change(self, db_session: AsyncSession) -> None:
        """パラメータなしなら変更なし。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Original",
        )
        original_title = panel.title

        updated = await update_role_panel(db_session, panel)
        assert updated.title == original_title

    async def test_update_panel_description_none_preserves(
        self, db_session: AsyncSession
    ) -> None:
        """description=None は変更なしを意味する。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
            description="Original description",
        )
        assert panel.description == "Original description"

        # None は「変更なし」なので元の値が保持される
        updated = await update_role_panel(db_session, panel, description=None)
        assert updated.description == "Original description"

    async def test_update_panel_title_and_description(
        self, db_session: AsyncSession
    ) -> None:
        """タイトルと説明を同時に更新できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Original Title",
            description="Original Description",
        )

        updated = await update_role_panel(
            db_session,
            panel,
            title="New Title",
            description="New Description",
        )
        assert updated.title == "New Title"
        assert updated.description == "New Description"

    async def test_delete_panel(self, db_session: AsyncSession) -> None:
        """パネルを削除できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        result = await delete_role_panel(db_session, panel.id)
        assert result is True
        assert await get_role_panel(db_session, panel.id) is None

    async def test_delete_panel_not_found(self, db_session: AsyncSession) -> None:
        """存在しないパネルの削除は False。"""
        result = await delete_role_panel(db_session, 999999)
        assert result is False


# ===========================================================================
# RolePanelItem CRUD — faker 利用
# ===========================================================================


class TestRolePanelItemWithFaker:
    """faker で生成したデータでの RolePanelItem テスト。"""

    async def test_add_item(self, db_session: AsyncSession) -> None:
        """アイテムを追加できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        item = await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id=snowflake(),
            emoji="🎮",
            label="Gamer",
        )

        assert item.panel_id == panel.id
        assert item.emoji == "🎮"
        assert item.label == "Gamer"
        assert item.position == 0

    async def test_add_item_position_increment(self, db_session: AsyncSession) -> None:
        """アイテム追加時に position が自動インクリメント。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        item1 = await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id=snowflake(),
            emoji="🎮",
        )
        item2 = await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id=snowflake(),
            emoji="🎨",
        )
        item3 = await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id=snowflake(),
            emoji="🎵",
        )

        assert item1.position == 0
        assert item2.position == 1
        assert item3.position == 2

    async def test_add_item_with_style(self, db_session: AsyncSession) -> None:
        """スタイル付きでアイテムを追加できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        item = await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id=snowflake(),
            emoji="🎮",
            style="success",
        )

        assert item.style == "success"

    async def test_get_items(self, db_session: AsyncSession) -> None:
        """パネルのアイテム一覧を取得できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        for emoji in ["🎮", "🎨", "🎵"]:
            await add_role_panel_item(
                db_session,
                panel_id=panel.id,
                role_id=snowflake(),
                emoji=emoji,
            )

        items = await get_role_panel_items(db_session, panel.id)
        assert len(items) == 3
        assert items[0].position == 0
        assert items[1].position == 1
        assert items[2].position == 2

    async def test_get_items_empty(self, db_session: AsyncSession) -> None:
        """アイテムがなければ空リスト。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        items = await get_role_panel_items(db_session, panel.id)
        assert items == []

    async def test_get_item_by_emoji(self, db_session: AsyncSession) -> None:
        """絵文字でアイテムを取得できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="reaction",
            title="Test",
        )

        await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id=snowflake(),
            emoji="🎮",
        )
        await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id=snowflake(),
            emoji="🎨",
        )

        item = await get_role_panel_item_by_emoji(db_session, panel.id, "🎨")
        assert item is not None
        assert item.emoji == "🎨"

    async def test_get_item_by_emoji_not_found(self, db_session: AsyncSession) -> None:
        """存在しない絵文字は None を返す。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="reaction",
            title="Test",
        )

        result = await get_role_panel_item_by_emoji(db_session, panel.id, "🎮")
        assert result is None

    async def test_remove_item(self, db_session: AsyncSession) -> None:
        """アイテムを削除できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id=snowflake(),
            emoji="🎮",
        )

        result = await remove_role_panel_item(db_session, panel.id, "🎮")
        assert result is True

        items = await get_role_panel_items(db_session, panel.id)
        assert len(items) == 0

    async def test_remove_item_not_found(self, db_session: AsyncSession) -> None:
        """存在しないアイテムの削除は False。"""
        result = await remove_role_panel_item(db_session, 999999, "🎮")
        assert result is False

    async def test_cascade_delete_items(self, db_session: AsyncSession) -> None:
        """パネル削除でアイテムもカスケード削除される。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        for emoji in ["🎮", "🎨", "🎵"]:
            await add_role_panel_item(
                db_session,
                panel_id=panel.id,
                role_id=snowflake(),
                emoji=emoji,
            )

        await delete_role_panel(db_session, panel.id)

        items = await get_role_panel_items(db_session, panel.id)
        assert items == []

    async def test_add_item_invalid_panel_id(self, db_session: AsyncSession) -> None:
        """存在しない panel_id でアイテム追加は IntegrityError。"""
        with pytest.raises(IntegrityError):
            await add_role_panel_item(
                db_session,
                panel_id=999999,
                role_id=snowflake(),
                emoji="🎮",
            )

    async def test_add_item_duplicate_emoji(self, db_session: AsyncSession) -> None:
        """同じパネルに同じ絵文字のアイテムを追加すると IntegrityError。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        # 最初のアイテムは成功
        await add_role_panel_item(
            db_session,
            panel_id=panel.id,
            role_id=snowflake(),
            emoji="🎮",
        )

        # 同じ絵文字で2つ目を追加しようとすると IntegrityError
        with pytest.raises(IntegrityError):
            await add_role_panel_item(
                db_session,
                panel_id=panel.id,
                role_id=snowflake(),
                emoji="🎮",
            )


# ===========================================================================
# VoiceSessionMember CRUD — faker 利用
# ===========================================================================


class TestVoiceSessionMemberWithFaker:
    """faker で生成したデータでの VoiceSessionMember テスト。"""

    async def test_add_member(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """メンバーを追加できる。"""
        user_id = snowflake()
        member = await add_voice_session_member(db_session, voice_session.id, user_id)

        assert member.voice_session_id == voice_session.id
        assert member.user_id == user_id
        assert member.joined_at is not None

    async def test_add_member_idempotent(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """同じメンバーを2回追加しても既存を返す。"""
        user_id = snowflake()
        member1 = await add_voice_session_member(db_session, voice_session.id, user_id)
        member2 = await add_voice_session_member(db_session, voice_session.id, user_id)

        assert member1.id == member2.id
        assert member1.joined_at == member2.joined_at

    async def test_remove_member(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """メンバーを削除できる。"""
        user_id = snowflake()
        await add_voice_session_member(db_session, voice_session.id, user_id)

        result = await remove_voice_session_member(
            db_session, voice_session.id, user_id
        )
        assert result is True

    async def test_remove_member_not_found(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """存在しないメンバーの削除は False。"""
        result = await remove_voice_session_member(
            db_session, voice_session.id, snowflake()
        )
        assert result is False

    async def test_get_members_ordered(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """メンバー一覧を参加順で取得できる。"""
        users = [snowflake() for _ in range(3)]
        for uid in users:
            await add_voice_session_member(db_session, voice_session.id, uid)

        members = await get_voice_session_members_ordered(db_session, voice_session.id)
        assert len(members) == 3
        # 参加順でソートされている (古い順)
        assert members[0].user_id == users[0]
        assert members[1].user_id == users[1]
        assert members[2].user_id == users[2]

    async def test_get_members_ordered_empty(
        self, db_session: AsyncSession, voice_session: VoiceSession
    ) -> None:
        """メンバーがいなければ空リスト。"""
        members = await get_voice_session_members_ordered(db_session, voice_session.id)
        assert members == []


# ===========================================================================
# BumpReminder CRUD — faker 利用
# ===========================================================================


class TestBumpReminderWithFaker:
    """faker で生成したデータでの BumpReminder テスト。"""

    async def test_upsert_creates_new(self, db_session: AsyncSession) -> None:
        """新規リマインダーを作成できる。"""
        from datetime import datetime

        gid = snowflake()
        cid = snowflake()
        remind_at = datetime.now(UTC)

        reminder = await upsert_bump_reminder(
            db_session, gid, cid, "DISBOARD", remind_at
        )

        assert reminder.guild_id == gid
        assert reminder.channel_id == cid
        assert reminder.service_name == "DISBOARD"
        assert reminder.is_enabled is True

    async def test_upsert_updates_existing(self, db_session: AsyncSession) -> None:
        """既存リマインダーを更新できる。"""
        from datetime import datetime

        gid = snowflake()
        cid1 = snowflake()
        cid2 = snowflake()
        remind_at = datetime.now(UTC)

        await upsert_bump_reminder(db_session, gid, cid1, "DISBOARD", remind_at)
        reminder2 = await upsert_bump_reminder(
            db_session, gid, cid2, "DISBOARD", remind_at
        )

        assert reminder2.channel_id == cid2

    async def test_get_bump_reminder(self, db_session: AsyncSession) -> None:
        """リマインダーを取得できる。"""
        from datetime import datetime

        gid = snowflake()
        remind_at = datetime.now(UTC)
        await upsert_bump_reminder(db_session, gid, snowflake(), "DISBOARD", remind_at)

        found = await get_bump_reminder(db_session, gid, "DISBOARD")
        assert found is not None
        assert found.guild_id == gid

    async def test_get_bump_reminder_not_found(self, db_session: AsyncSession) -> None:
        """存在しないリマインダーは None。"""
        result = await get_bump_reminder(db_session, snowflake(), "DISBOARD")
        assert result is None

    async def test_get_due_bump_reminders(self, db_session: AsyncSession) -> None:
        """送信予定時刻を過ぎたリマインダーを取得できる。"""
        from datetime import datetime, timedelta

        now = datetime.now(UTC)
        past = now - timedelta(hours=1)
        future = now + timedelta(hours=1)

        gid1 = snowflake()
        gid2 = snowflake()
        await upsert_bump_reminder(db_session, gid1, snowflake(), "DISBOARD", past)
        await upsert_bump_reminder(db_session, gid2, snowflake(), "DISBOARD", future)

        due = await get_due_bump_reminders(db_session, now)
        assert len(due) == 1
        assert due[0].guild_id == gid1

    async def test_clear_bump_reminder(self, db_session: AsyncSession) -> None:
        """リマインダーの remind_at をクリアできる。"""
        from datetime import datetime

        gid = snowflake()
        remind_at = datetime.now(UTC)
        reminder = await upsert_bump_reminder(
            db_session, gid, snowflake(), "DISBOARD", remind_at
        )

        result = await clear_bump_reminder(db_session, reminder.id)
        assert result is True

        found = await get_bump_reminder(db_session, gid, "DISBOARD")
        assert found is not None
        assert found.remind_at is None

    async def test_clear_bump_reminder_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないリマインダーのクリアは False。"""
        result = await clear_bump_reminder(db_session, 999999)
        assert result is False

    async def test_toggle_bump_reminder(self, db_session: AsyncSession) -> None:
        """リマインダーの有効/無効を切り替えられる。"""
        from datetime import datetime

        gid = snowflake()
        remind_at = datetime.now(UTC)
        await upsert_bump_reminder(db_session, gid, snowflake(), "DISBOARD", remind_at)

        # 有効 -> 無効
        is_enabled = await toggle_bump_reminder(db_session, gid, "DISBOARD")
        assert is_enabled is False

        # 無効 -> 有効
        is_enabled = await toggle_bump_reminder(db_session, gid, "DISBOARD")
        assert is_enabled is True

    async def test_toggle_bump_reminder_creates_new(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないリマインダーをトグルすると無効状態で作成される。"""
        gid = snowflake()
        is_enabled = await toggle_bump_reminder(db_session, gid, "DISBOARD")
        assert is_enabled is False

        found = await get_bump_reminder(db_session, gid, "DISBOARD")
        assert found is not None
        assert found.is_enabled is False

    async def test_update_bump_reminder_role(self, db_session: AsyncSession) -> None:
        """リマインダーの通知ロールを更新できる。"""
        from datetime import datetime

        gid = snowflake()
        role_id = snowflake()
        remind_at = datetime.now(UTC)
        await upsert_bump_reminder(db_session, gid, snowflake(), "DISBOARD", remind_at)

        result = await update_bump_reminder_role(db_session, gid, "DISBOARD", role_id)
        assert result is True

        found = await get_bump_reminder(db_session, gid, "DISBOARD")
        assert found is not None
        assert found.role_id == role_id

    async def test_update_bump_reminder_role_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないリマインダーのロール更新は False。"""
        result = await update_bump_reminder_role(
            db_session, snowflake(), "DISBOARD", snowflake()
        )
        assert result is False


# ===========================================================================
# BumpConfig CRUD — faker 利用
# ===========================================================================


class TestBumpConfigWithFaker:
    """faker で生成したデータでの BumpConfig テスト。"""

    async def test_upsert_creates_new(self, db_session: AsyncSession) -> None:
        """新規設定を作成できる。"""
        gid = snowflake()
        cid = snowflake()

        config = await upsert_bump_config(db_session, gid, cid)

        assert config.guild_id == gid
        assert config.channel_id == cid

    async def test_upsert_updates_existing(self, db_session: AsyncSession) -> None:
        """既存設定を更新できる。"""
        gid = snowflake()
        cid1 = snowflake()
        cid2 = snowflake()

        await upsert_bump_config(db_session, gid, cid1)
        config2 = await upsert_bump_config(db_session, gid, cid2)

        assert config2.channel_id == cid2

    async def test_get_bump_config(self, db_session: AsyncSession) -> None:
        """設定を取得できる。"""
        gid = snowflake()
        cid = snowflake()
        await upsert_bump_config(db_session, gid, cid)

        found = await get_bump_config(db_session, gid)
        assert found is not None
        assert found.guild_id == gid

    async def test_get_bump_config_not_found(self, db_session: AsyncSession) -> None:
        """存在しない設定は None。"""
        result = await get_bump_config(db_session, snowflake())
        assert result is None

    async def test_delete_bump_config(self, db_session: AsyncSession) -> None:
        """設定を削除できる。"""
        gid = snowflake()
        await upsert_bump_config(db_session, gid, snowflake())

        result = await delete_bump_config(db_session, gid)
        assert result is True
        assert await get_bump_config(db_session, gid) is None

    async def test_delete_bump_config_not_found(self, db_session: AsyncSession) -> None:
        """存在しない設定の削除は False。"""
        result = await delete_bump_config(db_session, snowflake())
        assert result is False


# ===========================================================================
# StickyMessage CRUD — faker 利用
# ===========================================================================


class TestStickyMessageWithFaker:
    """faker で生成したデータでの StickyMessage テスト。"""

    async def test_create_sticky_message(self, db_session: AsyncSession) -> None:
        """sticky メッセージを作成できる。"""
        gid = snowflake()
        cid = snowflake()
        title = fake.sentence(nb_words=3)
        desc = fake.paragraph()

        sticky = await create_sticky_message(
            db_session,
            channel_id=cid,
            guild_id=gid,
            title=title,
            description=desc,
        )

        assert sticky.channel_id == cid
        assert sticky.guild_id == gid
        assert sticky.title == title
        assert sticky.description == desc
        assert sticky.message_type == "embed"

    async def test_create_sticky_message_with_all_options(
        self, db_session: AsyncSession
    ) -> None:
        """全オプション指定で sticky メッセージを作成できる。"""
        gid = snowflake()
        cid = snowflake()
        color = fake.random_int(min=0, max=0xFFFFFF)

        sticky = await create_sticky_message(
            db_session,
            channel_id=cid,
            guild_id=gid,
            title="Test",
            description="Desc",
            color=color,
            cooldown_seconds=10,
            message_type="text",
        )

        assert sticky.color == color
        assert sticky.cooldown_seconds == 10
        assert sticky.message_type == "text"

    async def test_create_sticky_message_upsert(self, db_session: AsyncSession) -> None:
        """同じチャンネルに作成すると上書きされる。"""
        gid = snowflake()
        cid = snowflake()

        await create_sticky_message(
            db_session,
            channel_id=cid,
            guild_id=gid,
            title="Original",
            description="Desc",
        )
        sticky2 = await create_sticky_message(
            db_session,
            channel_id=cid,
            guild_id=gid,
            title="Updated",
            description="New Desc",
        )

        assert sticky2.title == "Updated"
        found = await get_sticky_message(db_session, cid)
        assert found is not None
        assert found.title == "Updated"

    async def test_get_sticky_message(self, db_session: AsyncSession) -> None:
        """sticky メッセージを取得できる。"""
        cid = snowflake()
        await create_sticky_message(
            db_session,
            channel_id=cid,
            guild_id=snowflake(),
            title="Test",
            description="Desc",
        )

        found = await get_sticky_message(db_session, cid)
        assert found is not None
        assert found.channel_id == cid

    async def test_get_sticky_message_not_found(self, db_session: AsyncSession) -> None:
        """存在しない sticky メッセージは None。"""
        result = await get_sticky_message(db_session, snowflake())
        assert result is None

    async def test_update_sticky_message_id(self, db_session: AsyncSession) -> None:
        """sticky メッセージの message_id を更新できる。"""
        from datetime import datetime

        cid = snowflake()
        mid = snowflake()
        await create_sticky_message(
            db_session,
            channel_id=cid,
            guild_id=snowflake(),
            title="Test",
            description="Desc",
        )

        now = datetime.now(UTC)
        result = await update_sticky_message_id(db_session, cid, mid, now)
        assert result is True

        found = await get_sticky_message(db_session, cid)
        assert found is not None
        assert found.message_id == mid

    async def test_update_sticky_message_id_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない sticky メッセージの更新は False。"""
        result = await update_sticky_message_id(db_session, snowflake(), snowflake())
        assert result is False

    async def test_delete_sticky_message(self, db_session: AsyncSession) -> None:
        """sticky メッセージを削除できる。"""
        cid = snowflake()
        await create_sticky_message(
            db_session,
            channel_id=cid,
            guild_id=snowflake(),
            title="Test",
            description="Desc",
        )

        result = await delete_sticky_message(db_session, cid)
        assert result is True
        assert await get_sticky_message(db_session, cid) is None

    async def test_delete_sticky_message_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない sticky メッセージの削除は False。"""
        result = await delete_sticky_message(db_session, snowflake())
        assert result is False

    async def test_get_all_sticky_messages(self, db_session: AsyncSession) -> None:
        """全 sticky メッセージを取得できる。"""
        count = fake.random_int(min=2, max=5)
        for _ in range(count):
            await create_sticky_message(
                db_session,
                channel_id=snowflake(),
                guild_id=snowflake(),
                title=fake.word(),
                description=fake.sentence(),
            )

        stickies = await get_all_sticky_messages(db_session)
        assert len(stickies) == count

    async def test_get_all_sticky_messages_empty(
        self, db_session: AsyncSession
    ) -> None:
        """sticky メッセージがなければ空リスト。"""
        result = await get_all_sticky_messages(db_session)
        assert result == []
