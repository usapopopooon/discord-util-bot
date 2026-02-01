"""Integration tests — 複数サービスにまたがる整合性テスト。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.db_service import (
    add_voice_session_member,
    clear_bump_reminder,
    create_lobby,
    create_role_panel,
    create_sticky_message,
    create_voice_session,
    delete_lobby,
    delete_role_panel,
    delete_sticky_message,
    delete_voice_session,
    get_all_sticky_messages,
    get_all_voice_sessions,
    get_bump_reminder,
    get_due_bump_reminders,
    get_lobbies_by_guild,
    get_lobby_by_channel_id,
    get_role_panel,
    get_role_panels_by_guild,
    get_sticky_message,
    get_voice_session,
    get_voice_session_members_ordered,
    remove_voice_session_member,
    toggle_bump_reminder,
    update_voice_session,
    upsert_bump_reminder,
)

from .conftest import snowflake

fake = Faker()


class TestLobbySessionLifecycle:
    """ロビー → セッション作成 → 更新 → 削除の一連フローテスト。"""

    async def test_full_lifecycle(self, db_session: AsyncSession) -> None:
        """ロビー作成 → セッション作成 → 更新 → セッション削除 → ロビー削除。"""
        # ロビー作成
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
            default_user_limit=10,
        )
        assert lobby.id is not None

        # セッション作成
        ch_id = snowflake()
        vs = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=ch_id,
            owner_id=snowflake(),
            name="initial",
        )
        assert vs.id is not None
        assert vs.name == "initial"

        # セッション更新
        updated = await update_voice_session(
            db_session, vs, name="renamed", is_locked=True
        )
        assert updated.name == "renamed"
        assert updated.is_locked is True

        # セッション削除
        assert await delete_voice_session(db_session, ch_id) is True
        assert await get_voice_session(db_session, ch_id) is None

        # ロビー削除
        assert await delete_lobby(db_session, lobby.id) is True

    async def test_multiple_lobbies_multiple_sessions(
        self, db_session: AsyncSession
    ) -> None:
        """複数ロビーにそれぞれセッションを作成し、独立して管理できる。"""
        guild_id = snowflake()
        lobbies = []
        for _ in range(3):
            lobby = await create_lobby(
                db_session,
                guild_id=guild_id,
                lobby_channel_id=snowflake(),
            )
            lobbies.append(lobby)

        # 各ロビーに2セッションずつ作成
        all_channels: dict[int, list[str]] = {}
        for lobby in lobbies:
            channels = []
            for _ in range(2):
                cid = snowflake()
                channels.append(cid)
                await create_voice_session(
                    db_session,
                    lobby_id=lobby.id,
                    channel_id=cid,
                    owner_id=snowflake(),
                    name=fake.word(),
                )
            all_channels[lobby.id] = channels

        # 全6セッション存在
        all_sessions = await get_all_voice_sessions(db_session)
        assert len(all_sessions) == 6

        # ロビー1つ削除 → そのセッションのみ消える
        deleted_lobby = lobbies[0]
        await delete_lobby(db_session, deleted_lobby.id)

        remaining = await get_all_voice_sessions(db_session)
        assert len(remaining) == 4

        # 削除されたロビーのセッションは存在しない
        for cid in all_channels[deleted_lobby.id]:
            assert await get_voice_session(db_session, cid) is None

        # 残りのロビーのセッションは存在する
        for lobby in lobbies[1:]:
            for cid in all_channels[lobby.id]:
                assert await get_voice_session(db_session, cid) is not None

    async def test_owner_transfer_and_verify(self, db_session: AsyncSession) -> None:
        """オーナー譲渡後にセッションを再取得して反映を確認。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )
        original_owner = snowflake()
        ch_id = snowflake()
        vs = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=ch_id,
            owner_id=original_owner,
            name="test",
        )

        new_owner = snowflake()
        await update_voice_session(db_session, vs, owner_id=new_owner)

        # DB から再取得して確認
        reloaded = await get_voice_session(db_session, ch_id)
        assert reloaded is not None
        assert reloaded.owner_id == new_owner
        assert reloaded.owner_id != original_owner


class TestDataIsolation:
    """データ分離・整合性テスト。"""

    async def test_guild_lobby_isolation(self, db_session: AsyncSession) -> None:
        """異なるギルドのロビーは完全に分離されている。"""
        g1, g2 = snowflake(), snowflake()
        l1 = await create_lobby(db_session, guild_id=g1, lobby_channel_id=snowflake())
        l2 = await create_lobby(db_session, guild_id=g2, lobby_channel_id=snowflake())

        g1_lobbies = await get_lobbies_by_guild(db_session, g1)
        g2_lobbies = await get_lobbies_by_guild(db_session, g2)

        assert len(g1_lobbies) == 1
        assert g1_lobbies[0].id == l1.id
        assert len(g2_lobbies) == 1
        assert g2_lobbies[0].id == l2.id

    async def test_session_deletion_isolation(self, db_session: AsyncSession) -> None:
        """セッション削除は同じロビーの他セッションに影響しない。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )
        ch1, ch2, ch3 = snowflake(), snowflake(), snowflake()
        for cid in [ch1, ch2, ch3]:
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=cid,
                owner_id=snowflake(),
                name=fake.word(),
            )

        # ch2 だけ削除
        await delete_voice_session(db_session, ch2)

        assert await get_voice_session(db_session, ch1) is not None
        assert await get_voice_session(db_session, ch2) is None
        assert await get_voice_session(db_session, ch3) is not None

    async def test_lobby_lookup_by_channel_id(self, db_session: AsyncSession) -> None:
        """channel_id でロビーを正しく取得できる。"""
        target_cid = snowflake()
        # ダミーロビーを先に作成
        for _ in range(5):
            await create_lobby(
                db_session,
                guild_id=snowflake(),
                lobby_channel_id=snowflake(),
            )
        # ターゲットロビー
        target = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=target_cid,
        )

        found = await get_lobby_by_channel_id(db_session, target_cid)
        assert found is not None
        assert found.id == target.id

    async def test_session_count_after_bulk_operations(
        self, db_session: AsyncSession
    ) -> None:
        """大量の作成・削除後にカウントが正確。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )

        # 10セッション作成
        channels = []
        for _ in range(10):
            cid = snowflake()
            channels.append(cid)
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=cid,
                owner_id=snowflake(),
                name=fake.word(),
            )
        assert len(await get_all_voice_sessions(db_session)) == 10

        # 偶数インデックスの5件削除
        for i in range(0, 10, 2):
            await delete_voice_session(db_session, channels[i])

        remaining = await get_all_voice_sessions(db_session)
        assert len(remaining) == 5

    async def test_update_does_not_create_duplicate(
        self, db_session: AsyncSession
    ) -> None:
        """update はレコードを増やさない。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )
        vs = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name="original",
        )

        assert len(await get_all_voice_sessions(db_session)) == 1

        await update_voice_session(db_session, vs, name="updated")
        assert len(await get_all_voice_sessions(db_session)) == 1

    async def test_lobby_with_category_id(self, db_session: AsyncSession) -> None:
        """category_id 付きロビーの作成と取得。"""
        cat_id = snowflake()
        cid = snowflake()
        await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=cid,
            category_id=cat_id,
            default_user_limit=25,
        )

        found = await get_lobby_by_channel_id(db_session, cid)
        assert found is not None
        assert found.category_id == cat_id
        assert found.default_user_limit == 25


class TestStickyMessageLifecycle:
    """Sticky メッセージのライフサイクルテスト。"""

    async def test_create_update_delete(self, db_session: AsyncSession) -> None:
        """Sticky メッセージの作成→更新→削除。"""
        guild_id = snowflake()
        channel_id = snowflake()

        # 作成
        sticky = await create_sticky_message(
            db_session,
            channel_id=channel_id,
            guild_id=guild_id,
            title="初期タイトル",
            description="初期内容",
        )
        assert sticky.channel_id == channel_id
        assert sticky.title == "初期タイトル"

        # 同じチャンネルに再作成 → 更新される
        updated = await create_sticky_message(
            db_session,
            channel_id=channel_id,
            guild_id=guild_id,
            title="更新タイトル",
            description="更新内容",
        )
        assert updated.channel_id == sticky.channel_id
        assert updated.title == "更新タイトル"

        # 削除
        result = await delete_sticky_message(db_session, channel_id)
        assert result is True
        assert await get_sticky_message(db_session, channel_id) is None

    async def test_multiple_channels(self, db_session: AsyncSession) -> None:
        """異なるチャンネルに複数の Sticky を作成。"""
        guild_id = snowflake()
        channels = [snowflake() for _ in range(5)]

        for i, ch in enumerate(channels):
            await create_sticky_message(
                db_session,
                channel_id=ch,
                guild_id=guild_id,
                title=f"Sticky {i}",
                description=f"Content {i}",
            )

        all_stickies = await get_all_sticky_messages(db_session)
        assert len(all_stickies) == 5

        # 2件削除
        await delete_sticky_message(db_session, channels[0])
        await delete_sticky_message(db_session, channels[2])

        remaining = await get_all_sticky_messages(db_session)
        assert len(remaining) == 3


class TestBumpReminderWorkflow:
    """Bump リマインダーのワークフローテスト。"""

    async def test_upsert_and_toggle(self, db_session: AsyncSession) -> None:
        """Bump リマインダーの upsert と toggle。"""
        guild_id = snowflake()
        channel_id = snowflake()

        # 初回作成
        reminder = await upsert_bump_reminder(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            service_name="disboard",
            remind_at=datetime.now(UTC) + timedelta(hours=2),
        )
        assert reminder.is_enabled is True
        original_id = reminder.id

        # toggle で無効化 (returns new is_enabled value)
        toggled = await toggle_bump_reminder(db_session, guild_id, "disboard")
        assert toggled is False  # True → False

        # 確認 (get_bump_reminder は channel_id を取らない)
        updated = await get_bump_reminder(db_session, guild_id, "disboard")
        assert updated is not None
        assert updated.is_enabled is False
        assert updated.id == original_id

        # 再度 toggle で有効化
        toggled2 = await toggle_bump_reminder(db_session, guild_id, "disboard")
        assert toggled2 is True  # False → True

        updated2 = await get_bump_reminder(db_session, guild_id, "disboard")
        assert updated2 is not None
        assert updated2.is_enabled is True

    async def test_due_reminders_filtering(self, db_session: AsyncSession) -> None:
        """期限切れリマインダーのフィルタリング。"""
        now = datetime.now(UTC)
        g1 = snowflake()
        g2 = snowflake()

        # 過去 (due) - ギルド1
        await upsert_bump_reminder(
            db_session,
            guild_id=g1,
            channel_id=snowflake(),
            service_name="disboard",
            remind_at=now - timedelta(hours=1),
        )
        # 未来 (not due) - ギルド2
        await upsert_bump_reminder(
            db_session,
            guild_id=g2,
            channel_id=snowflake(),
            service_name="dissoku",
            remind_at=now + timedelta(hours=1),
        )

        due = await get_due_bump_reminders(db_session, now)
        assert len(due) == 1  # 過去かつ enabled のみ
        assert due[0].guild_id == g1

    async def test_clear_reminder(self, db_session: AsyncSession) -> None:
        """リマインダーのクリア（remind_at を None に）。"""
        guild_id = snowflake()
        channel_id = snowflake()

        reminder = await upsert_bump_reminder(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            service_name="disboard",
            remind_at=datetime.now(UTC) + timedelta(hours=2),
        )

        cleared = await clear_bump_reminder(db_session, reminder.id)
        assert cleared is True

        updated = await get_bump_reminder(db_session, guild_id, "disboard")
        assert updated is not None
        assert updated.remind_at is None


class TestRolePanelCRUD:
    """Role Panel の CRUD テスト。"""

    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        """Role Panel の作成と取得。"""
        guild_id = snowflake()
        channel_id = snowflake()

        panel = await create_role_panel(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            panel_type="button",
            title="ロール選択",
            description="好きなロールを選んでください",
        )
        assert panel.id is not None
        assert panel.title == "ロール選択"
        assert panel.panel_type == "button"

        # ID で取得
        fetched = await get_role_panel(db_session, panel.id)
        assert fetched is not None
        assert fetched.title == "ロール選択"

    async def test_guild_isolation(self, db_session: AsyncSession) -> None:
        """異なるギルドのパネルは分離される。"""
        g1, g2 = snowflake(), snowflake()

        for _ in range(3):
            await create_role_panel(
                db_session,
                guild_id=g1,
                channel_id=snowflake(),
                panel_type="button",
                title=fake.word(),
            )
        for _ in range(2):
            await create_role_panel(
                db_session,
                guild_id=g2,
                channel_id=snowflake(),
                panel_type="reaction",
                title=fake.word(),
            )

        g1_panels = await get_role_panels_by_guild(db_session, g1)
        g2_panels = await get_role_panels_by_guild(db_session, g2)

        assert len(g1_panels) == 3
        assert len(g2_panels) == 2
        assert all(p.panel_type == "button" for p in g1_panels)
        assert all(p.panel_type == "reaction" for p in g2_panels)

    async def test_delete(self, db_session: AsyncSession) -> None:
        """Role Panel の削除。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="削除テスト",
        )
        panel_id = panel.id

        result = await delete_role_panel(db_session, panel_id)
        assert result is True

        assert await get_role_panel(db_session, panel_id) is None


class TestVoiceSessionMemberManagement:
    """VoiceSession メンバー管理テスト。"""

    async def test_add_remove_members(self, db_session: AsyncSession) -> None:
        """メンバーの追加と削除。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )
        ch_id = snowflake()
        owner_id = snowflake()

        vs = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=ch_id,
            owner_id=owner_id,
            name="test",
        )

        # メンバー追加
        m1, m2, m3 = snowflake(), snowflake(), snowflake()
        await add_voice_session_member(db_session, vs.id, m1)
        await add_voice_session_member(db_session, vs.id, m2)
        await add_voice_session_member(db_session, vs.id, m3)

        members = await get_voice_session_members_ordered(db_session, vs.id)
        assert len(members) == 3

        # メンバー削除
        await remove_voice_session_member(db_session, vs.id, m2)
        members = await get_voice_session_members_ordered(db_session, vs.id)
        assert len(members) == 2
        member_ids = [m.user_id for m in members]
        assert m2 not in member_ids
        assert m1 in member_ids
        assert m3 in member_ids

    async def test_member_join_order(self, db_session: AsyncSession) -> None:
        """メンバーの参加順序が保持される。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )
        vs = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=snowflake(),
            owner_id=snowflake(),
            name="order-test",
        )

        # 順番に追加
        member_ids = [snowflake() for _ in range(5)]
        for mid in member_ids:
            await add_voice_session_member(db_session, vs.id, mid)
            await asyncio.sleep(0.01)  # 順序を保証するための微小な待機

        members = await get_voice_session_members_ordered(db_session, vs.id)
        result_ids = [m.user_id for m in members]
        assert result_ids == member_ids

    async def test_cascade_delete_on_session_delete(
        self, db_session: AsyncSession
    ) -> None:
        """セッション削除時にメンバーもカスケード削除。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )
        ch_id = snowflake()
        vs = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id=ch_id,
            owner_id=snowflake(),
            name="cascade-test",
        )

        for _ in range(3):
            await add_voice_session_member(db_session, vs.id, snowflake())

        # セッション削除
        await delete_voice_session(db_session, ch_id)

        # メンバーも削除されている（セッションがないので空）
        members = await get_voice_session_members_ordered(db_session, vs.id)
        assert len(members) == 0


class TestBulkOperations:
    """一括操作テスト。"""

    async def test_sequential_session_creation(self, db_session: AsyncSession) -> None:
        """複数セッションの連続作成。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )

        channel_ids = []
        for i in range(10):
            ch_id = snowflake()
            channel_ids.append(ch_id)
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=ch_id,
                owner_id=snowflake(),
                name=f"sequential-{i}",
            )

        all_sessions = await get_all_voice_sessions(db_session)
        assert len(all_sessions) == 10

        # 全て取得可能
        for ch_id in channel_ids:
            assert await get_voice_session(db_session, ch_id) is not None

    async def test_bulk_delete(self, db_session: AsyncSession) -> None:
        """複数セッションの一括削除。"""
        lobby = await create_lobby(
            db_session,
            guild_id=snowflake(),
            lobby_channel_id=snowflake(),
        )

        channel_ids = []
        for i in range(20):
            ch_id = snowflake()
            channel_ids.append(ch_id)
            await create_voice_session(
                db_session,
                lobby_id=lobby.id,
                channel_id=ch_id,
                owner_id=snowflake(),
                name=f"bulk-{i}",
            )

        assert len(await get_all_voice_sessions(db_session)) == 20

        # 全て削除
        for ch_id in channel_ids:
            await delete_voice_session(db_session, ch_id)

        assert len(await get_all_voice_sessions(db_session)) == 0
