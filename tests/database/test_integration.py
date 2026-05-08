"""Integration tests — 複数サービスにまたがる整合性テスト。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from faker import Faker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.db_service import (
    add_role_panel_item,
    clear_bump_reminder,
    create_role_panel,
    create_sticky_message,
    create_ticket,
    create_ticket_category,
    delete_bump_config,
    delete_bump_reminders_by_guild,
    delete_discord_channel,
    delete_discord_channels_by_guild,
    delete_discord_guild,
    delete_discord_role,
    delete_discord_roles_by_guild,
    delete_role_panel,
    delete_sticky_message,
    delete_sticky_messages_by_guild,
    get_all_discord_guilds,
    get_all_sticky_messages,
    get_bump_config,
    get_bump_reminder,
    get_discord_channels_by_guild,
    get_discord_roles_by_guild,
    get_due_bump_reminders,
    get_next_ticket_number,
    get_role_panel,
    get_role_panel_by_message_id,
    get_role_panel_item_by_emoji,
    get_role_panel_items,
    get_role_panels_by_channel,
    get_role_panels_by_guild,
    get_sticky_message,
    get_ticket,
    remove_role_panel_item,
    toggle_bump_reminder,
    update_role_panel,
    update_ticket_status,
    upsert_bump_config,
    upsert_bump_reminder,
    upsert_discord_channel,
    upsert_discord_guild,
    upsert_discord_role,
)
from src.utils import normalize_emoji

from .conftest import snowflake

fake = Faker()


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

    async def test_add_items_with_different_emojis(
        self, db_session: AsyncSession
    ) -> None:
        """異なる絵文字でアイテムを追加できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="アイテムテスト",
        )

        # 異なる絵文字で3つのアイテムを追加
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id=snowflake(), emoji="🎮"
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id=snowflake(), emoji="🎨"
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id=snowflake(), emoji="🎵"
        )

        items = await get_role_panel_items(db_session, panel.id)
        assert len(items) == 3
        emojis = {item.emoji for item in items}
        assert emojis == {"🎮", "🎨", "🎵"}

    async def test_duplicate_emoji_raises_integrity_error(
        self, db_session: AsyncSession
    ) -> None:
        """同じ絵文字を2回追加すると IntegrityError。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="重複テスト",
        )

        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id=snowflake(), emoji="🎮"
        )

        with pytest.raises(IntegrityError):
            await add_role_panel_item(
                db_session, panel_id=panel.id, role_id=snowflake(), emoji="🎮"
            )

    async def test_same_emoji_different_panels_allowed(
        self, db_session: AsyncSession
    ) -> None:
        """異なるパネルでは同じ絵文字を使用できる。"""
        guild_id = snowflake()

        panel1 = await create_role_panel(
            db_session,
            guild_id=guild_id,
            channel_id=snowflake(),
            panel_type="button",
            title="パネル1",
        )
        panel2 = await create_role_panel(
            db_session,
            guild_id=guild_id,
            channel_id=snowflake(),
            panel_type="button",
            title="パネル2",
        )

        # 同じ絵文字を両方のパネルに追加
        await add_role_panel_item(
            db_session, panel_id=panel1.id, role_id=snowflake(), emoji="🎮"
        )
        await add_role_panel_item(
            db_session, panel_id=panel2.id, role_id=snowflake(), emoji="🎮"
        )

        items1 = await get_role_panel_items(db_session, panel1.id)
        items2 = await get_role_panel_items(db_session, panel2.id)

        assert len(items1) == 1
        assert len(items2) == 1
        assert items1[0].emoji == "🎮"
        assert items2[0].emoji == "🎮"

    async def test_emoji_normalization_on_save(self, db_session: AsyncSession) -> None:
        """絵文字は正規化されて保存される。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="正規化テスト",
        )

        # 絵文字を正規化して保存
        emoji = "😀"
        normalized = normalize_emoji(emoji)
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id=snowflake(), emoji=normalized
        )

        items = await get_role_panel_items(db_session, panel.id)
        assert len(items) == 1
        assert items[0].emoji == normalized

    async def test_use_embed_default_true(self, db_session: AsyncSession) -> None:
        """use_embed のデフォルト値は True。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="デフォルトテスト",
        )

        fetched = await get_role_panel(db_session, panel.id)
        assert fetched is not None
        assert fetched.use_embed is True

    async def test_use_embed_false_persisted(self, db_session: AsyncSession) -> None:
        """use_embed=False が正しく保存される。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="use_embed=False テスト",
            use_embed=False,
        )

        fetched = await get_role_panel(db_session, panel.id)
        assert fetched is not None
        assert fetched.use_embed is False

    async def test_cascade_delete_items_on_panel_delete(
        self, db_session: AsyncSession
    ) -> None:
        """パネル削除時にアイテムもカスケード削除される。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="カスケードテスト",
        )

        # 複数アイテムを追加
        for emoji in ["🎮", "🎨", "🎵"]:
            await add_role_panel_item(
                db_session, panel_id=panel.id, role_id=snowflake(), emoji=emoji
            )

        items = await get_role_panel_items(db_session, panel.id)
        assert len(items) == 3

        # パネル削除
        await delete_role_panel(db_session, panel.id)

        # アイテムも削除されている
        items = await get_role_panel_items(db_session, panel.id)
        assert len(items) == 0


class TestDiscordEntityManagement:
    """Discord エンティティ（ギルド、チャンネル、ロール）の管理テスト。"""

    async def test_guild_channel_lifecycle(self, db_session: AsyncSession) -> None:
        """ギルド → チャンネル作成 → 削除のライフサイクル。"""
        guild_id = snowflake()

        # ギルド作成
        guild = await upsert_discord_guild(
            db_session, guild_id=guild_id, guild_name="Test Guild"
        )
        assert guild.guild_id == guild_id

        # チャンネル作成
        ch1, ch2 = snowflake(), snowflake()
        await upsert_discord_channel(
            db_session, guild_id=guild_id, channel_id=ch1, channel_name="channel1"
        )
        await upsert_discord_channel(
            db_session, guild_id=guild_id, channel_id=ch2, channel_name="channel2"
        )

        channels = await get_discord_channels_by_guild(db_session, guild_id)
        assert len(channels) == 2

        # 1つのチャンネルを削除
        result = await delete_discord_channel(db_session, guild_id, ch1)
        assert result is True

        channels = await get_discord_channels_by_guild(db_session, guild_id)
        assert len(channels) == 1
        assert channels[0].channel_id == ch2

    async def test_guild_role_lifecycle(self, db_session: AsyncSession) -> None:
        """ギルド → ロール作成 → 削除のライフサイクル。"""
        guild_id = snowflake()

        # ギルド作成
        await upsert_discord_guild(
            db_session, guild_id=guild_id, guild_name="Test Guild"
        )

        # ロール作成
        r1, r2, r3 = snowflake(), snowflake(), snowflake()
        await upsert_discord_role(
            db_session, guild_id=guild_id, role_id=r1, role_name="Admin"
        )
        await upsert_discord_role(
            db_session, guild_id=guild_id, role_id=r2, role_name="Mod"
        )
        await upsert_discord_role(
            db_session, guild_id=guild_id, role_id=r3, role_name="Member"
        )

        roles = await get_discord_roles_by_guild(db_session, guild_id)
        assert len(roles) == 3

        # 1つのロールを削除
        result = await delete_discord_role(db_session, guild_id, r2)
        assert result is True

        roles = await get_discord_roles_by_guild(db_session, guild_id)
        assert len(roles) == 2
        role_ids = {r.role_id for r in roles}
        assert r2 not in role_ids

    async def test_guild_deletion_clears_channels_and_roles(
        self, db_session: AsyncSession
    ) -> None:
        """ギルド削除時にチャンネルとロールも削除される。"""
        guild_id = snowflake()

        # ギルド作成
        await upsert_discord_guild(
            db_session, guild_id=guild_id, guild_name="Test Guild"
        )

        # チャンネルとロールを追加
        for i in range(3):
            await upsert_discord_channel(
                db_session,
                guild_id=guild_id,
                channel_id=snowflake(),
                channel_name=f"ch{i}",
            )
            await upsert_discord_role(
                db_session,
                guild_id=guild_id,
                role_id=snowflake(),
                role_name=f"role{i}",
            )

        assert len(await get_discord_channels_by_guild(db_session, guild_id)) == 3
        assert len(await get_discord_roles_by_guild(db_session, guild_id)) == 3

        # チャンネルとロールを一括削除
        deleted_channels = await delete_discord_channels_by_guild(db_session, guild_id)
        deleted_roles = await delete_discord_roles_by_guild(db_session, guild_id)

        assert deleted_channels == 3
        assert deleted_roles == 3

        # ギルド削除
        result = await delete_discord_guild(db_session, guild_id)
        assert result is True

        # すべて削除されている
        assert len(await get_discord_channels_by_guild(db_session, guild_id)) == 0
        assert len(await get_discord_roles_by_guild(db_session, guild_id)) == 0
        all_guilds = await get_all_discord_guilds(db_session)
        assert len([g for g in all_guilds if g.guild_id == guild_id]) == 0

    async def test_channel_upsert_updates_existing(
        self, db_session: AsyncSession
    ) -> None:
        """既存チャンネルの upsert は更新になる。"""
        guild_id = snowflake()
        channel_id = snowflake()

        await upsert_discord_guild(
            db_session, guild_id=guild_id, guild_name="Test Guild"
        )

        # 初回作成
        await upsert_discord_channel(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            channel_name="original",
        )

        # 同じ channel_id で upsert（更新）
        await upsert_discord_channel(
            db_session, guild_id=guild_id, channel_id=channel_id, channel_name="updated"
        )

        channels = await get_discord_channels_by_guild(db_session, guild_id)
        assert len(channels) == 1
        assert channels[0].channel_name == "updated"

    async def test_role_upsert_updates_existing(self, db_session: AsyncSession) -> None:
        """既存ロールの upsert は更新になる。"""
        guild_id = snowflake()
        role_id = snowflake()

        await upsert_discord_guild(
            db_session, guild_id=guild_id, guild_name="Test Guild"
        )

        # 初回作成
        await upsert_discord_role(
            db_session,
            guild_id=guild_id,
            role_id=role_id,
            role_name="original",
        )

        # 同じ role_id で upsert（更新）
        await upsert_discord_role(
            db_session, guild_id=guild_id, role_id=role_id, role_name="updated"
        )

        roles = await get_discord_roles_by_guild(db_session, guild_id)
        assert len(roles) == 1
        assert roles[0].role_name == "updated"


class TestBumpConfigReminderIntegration:
    """BumpConfig と BumpReminder の連携テスト。"""

    async def test_config_and_reminder_coexist(self, db_session: AsyncSession) -> None:
        """同じギルドで Config と Reminder が共存できる。"""
        guild_id = snowflake()
        channel_id = snowflake()

        # Config 作成
        config = await upsert_bump_config(
            db_session, guild_id=guild_id, channel_id=channel_id
        )
        assert config.guild_id == guild_id

        # Reminder 作成
        reminder = await upsert_bump_reminder(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            service_name="disboard",
            remind_at=datetime.now(UTC) + timedelta(hours=2),
        )
        assert reminder.guild_id == guild_id

        # 両方取得可能
        fetched_config = await get_bump_config(db_session, guild_id)
        fetched_reminder = await get_bump_reminder(db_session, guild_id, "disboard")

        assert fetched_config is not None
        assert fetched_reminder is not None

    async def test_config_deletion_does_not_affect_reminder(
        self, db_session: AsyncSession
    ) -> None:
        """Config 削除が Reminder に影響しない。"""
        guild_id = snowflake()
        channel_id = snowflake()

        await upsert_bump_config(db_session, guild_id=guild_id, channel_id=channel_id)
        await upsert_bump_reminder(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            service_name="disboard",
            remind_at=datetime.now(UTC) + timedelta(hours=2),
        )

        # Config 削除
        result = await delete_bump_config(db_session, guild_id)
        assert result is True

        # Reminder は残っている
        reminder = await get_bump_reminder(db_session, guild_id, "disboard")
        assert reminder is not None

    async def test_multiple_services_same_guild(self, db_session: AsyncSession) -> None:
        """同じギルドで複数サービスの Reminder が共存できる。"""
        guild_id = snowflake()
        now = datetime.now(UTC)

        # 3つのサービス
        for service in ["disboard", "dissoku", "displace"]:
            await upsert_bump_reminder(
                db_session,
                guild_id=guild_id,
                channel_id=snowflake(),
                service_name=service,
                remind_at=now + timedelta(hours=2),
            )

        # それぞれ取得可能
        for service in ["disboard", "dissoku", "displace"]:
            reminder = await get_bump_reminder(db_session, guild_id, service)
            assert reminder is not None
            assert reminder.service_name == service

    async def test_disabled_reminder_not_in_due_list(
        self, db_session: AsyncSession
    ) -> None:
        """無効化した Reminder は due リストに含まれない。"""
        guild_id = snowflake()
        past = datetime.now(UTC) - timedelta(hours=1)

        # 過去の時刻で Reminder 作成
        await upsert_bump_reminder(
            db_session,
            guild_id=guild_id,
            channel_id=snowflake(),
            service_name="disboard",
            remind_at=past,
        )

        # 有効時は due リストに含まれる
        due = await get_due_bump_reminders(db_session, datetime.now(UTC))
        assert any(r.guild_id == guild_id for r in due)

        # 無効化
        await toggle_bump_reminder(db_session, guild_id, "disboard")

        # due リストに含まれない
        due = await get_due_bump_reminders(db_session, datetime.now(UTC))
        assert not any(r.guild_id == guild_id for r in due)


class TestRolePanelAdvanced:
    """RolePanel の高度な操作テスト。"""

    async def test_get_panel_by_message_id(self, db_session: AsyncSession) -> None:
        """message_id でパネルを取得できる。"""
        guild_id = snowflake()
        message_id = snowflake()

        panel = await create_role_panel(
            db_session,
            guild_id=guild_id,
            channel_id=snowflake(),
            panel_type="button",
            title="Test Panel",
        )

        # message_id を設定
        await update_role_panel(db_session, panel, message_id=message_id)

        # message_id で取得
        fetched = await get_role_panel_by_message_id(db_session, message_id)
        assert fetched is not None
        assert fetched.id == panel.id

    async def test_get_panels_by_channel(self, db_session: AsyncSession) -> None:
        """チャンネル内の全パネルを取得できる。"""
        guild_id = snowflake()
        channel_id = snowflake()

        # 同じチャンネルに3つのパネル
        for i in range(3):
            await create_role_panel(
                db_session,
                guild_id=guild_id,
                channel_id=channel_id,
                panel_type="button",
                title=f"Panel {i}",
            )

        panels = await get_role_panels_by_channel(db_session, channel_id)
        assert len(panels) == 3

    async def test_item_lookup_by_emoji(self, db_session: AsyncSession) -> None:
        """絵文字でアイテムを検索できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id=snowflake(), emoji="🎮"
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id=snowflake(), emoji="🎨"
        )

        # 絵文字で検索
        item = await get_role_panel_item_by_emoji(db_session, panel.id, "🎮")
        assert item is not None
        assert item.emoji == "🎮"

        # 存在しない絵文字
        not_found = await get_role_panel_item_by_emoji(db_session, panel.id, "🎵")
        assert not_found is None

    async def test_remove_item_by_emoji(self, db_session: AsyncSession) -> None:
        """アイテムを絵文字で削除できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id=snowflake(), emoji="🎮"
        )
        await add_role_panel_item(
            db_session, panel_id=panel.id, role_id=snowflake(), emoji="🎨"
        )

        # 1つ削除
        result = await remove_role_panel_item(db_session, panel.id, "🎮")
        assert result is True

        # 残り1つ
        items = await get_role_panel_items(db_session, panel.id)
        assert len(items) == 1
        assert items[0].emoji == "🎨"

    async def test_update_panel_fields(self, db_session: AsyncSession) -> None:
        """パネルのフィールドを更新できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Original",
            description="Original desc",
            color=0xFF0000,
        )

        # 更新
        await update_role_panel(
            db_session,
            panel,
            title="Updated",
            description="Updated desc",
            color=0x00FF00,
        )

        # 再取得して確認
        fetched = await get_role_panel(db_session, panel.id)
        assert fetched is not None
        assert fetched.title == "Updated"
        assert fetched.description == "Updated desc"
        assert fetched.color == 0x00FF00


class TestCrossEntityIntegrity:
    """異なるエンティティ間の整合性テスト。"""

    async def test_same_channel_different_resources(
        self, db_session: AsyncSession
    ) -> None:
        """同じチャンネルに異なるリソースが共存できる。"""
        guild_id = snowflake()
        channel_id = snowflake()

        # StickyMessage
        await create_sticky_message(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            title="Sticky",
            description="Test sticky",
            color=0xFF0000,
            cooldown_seconds=10,
            message_type="embed",
        )

        # RolePanel
        await create_role_panel(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            panel_type="button",
            title="Role Panel",
        )

        # BumpConfig
        await upsert_bump_config(db_session, guild_id=guild_id, channel_id=channel_id)

        # すべて取得可能
        assert await get_sticky_message(db_session, channel_id) is not None
        panels = await get_role_panels_by_channel(db_session, channel_id)
        assert len(panels) == 1
        assert await get_bump_config(db_session, guild_id) is not None

    async def test_independent_deletion(self, db_session: AsyncSession) -> None:
        """各リソースの削除が他に影響しない。"""
        guild_id = snowflake()
        channel_id = snowflake()

        # 3つのリソースを作成
        await create_sticky_message(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            title="Sticky",
            description="Test",
            color=0,
            cooldown_seconds=10,
            message_type="text",
        )
        panel = await create_role_panel(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            panel_type="button",
            title="Panel",
        )
        await upsert_bump_config(db_session, guild_id=guild_id, channel_id=channel_id)

        # RolePanel だけ削除
        await delete_role_panel(db_session, panel.id)

        # 他は残っている
        assert await get_sticky_message(db_session, channel_id) is not None
        assert await get_bump_config(db_session, guild_id) is not None
        assert len(await get_role_panels_by_channel(db_session, channel_id)) == 0

    async def test_guild_data_isolation(self, db_session: AsyncSession) -> None:
        """異なるギルドのデータが完全に分離されている。"""
        g1, g2 = snowflake(), snowflake()

        # 各ギルドにリソースを作成
        panels_by_guild: dict[str, int] = {}
        for gid in [g1, g2]:
            panel = await create_role_panel(
                db_session,
                guild_id=gid,
                channel_id=snowflake(),
                panel_type="button",
                title=f"Panel for {gid}",
            )
            panels_by_guild[gid] = panel.id
            await upsert_bump_config(db_session, guild_id=gid, channel_id=snowflake())

        # 各ギルドのデータが分離されている
        assert len(await get_role_panels_by_guild(db_session, g1)) == 1
        assert len(await get_role_panels_by_guild(db_session, g2)) == 1

        # g1 のリソースを削除しても g2 に影響しない
        await delete_role_panel(db_session, panels_by_guild[g1])

        assert len(await get_role_panels_by_guild(db_session, g1)) == 0
        assert len(await get_role_panels_by_guild(db_session, g2)) == 1


class TestEdgeCasesAndBoundaries:
    """エッジケースと境界値のテスト。"""

    async def test_empty_string_handling(self, db_session: AsyncSession) -> None:
        """空文字列の扱い。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
            description="",  # 空文字列
        )

        fetched = await get_role_panel(db_session, panel.id)
        assert fetched is not None
        # 空文字列は None ではなく空文字列として保存される
        assert fetched.description == ""

    async def test_none_optional_fields(self, db_session: AsyncSession) -> None:
        """None のオプションフィールド。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
            description=None,
            color=None,
        )

        fetched = await get_role_panel(db_session, panel.id)
        assert fetched is not None
        assert fetched.description is None
        assert fetched.color is None

    async def test_delete_nonexistent_returns_false(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないリソースの削除は False を返す。"""
        result = await delete_role_panel(db_session, 999999)
        assert result is False

    async def test_get_nonexistent_returns_none(self, db_session: AsyncSession) -> None:
        """存在しないリソースの取得は None を返す。"""
        assert await get_role_panel(db_session, 999999) is None
        assert await get_role_panel_by_message_id(db_session, "nonexistent") is None

    async def test_maximum_items_per_panel(self, db_session: AsyncSession) -> None:
        """パネルに多数のアイテムを追加できる。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Many Items",
        )

        # 25個のアイテムを追加（Discord の制限に近い数）
        # 実際には異なる絵文字を使う必要があるが、テスト用にカスタム絵文字形式を使用
        for i in range(25):
            await add_role_panel_item(
                db_session,
                panel_id=panel.id,
                role_id=snowflake(),
                emoji=f"<:emoji{i}:{snowflake()}>",  # カスタム絵文字形式
            )

        items = await get_role_panel_items(db_session, panel.id)
        assert len(items) == 25


# =============================================================================
# ギルド削除時のクリーンアップ統合テスト
# =============================================================================


class TestGuildRemovalCleanup:
    """ギルドからBot削除時のデータクリーンアップ統合テスト。

    on_guild_remove イベントで呼ばれる削除関数の整合性をテスト。
    """

    async def test_bump_cleanup_with_multiple_services(
        self, db_session: AsyncSession
    ) -> None:
        """複数サービスのbumpリマインダーを持つギルドのクリーンアップ。"""
        guild_id = snowflake()
        channel_id = snowflake()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        # bump設定を作成
        await upsert_bump_config(db_session, guild_id, channel_id)

        # 複数サービスのリマインダーを作成
        await upsert_bump_reminder(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            service_name="DISBOARD",
            remind_at=remind_at,
        )
        await upsert_bump_reminder(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            service_name="ディス速報",
            remind_at=remind_at,
        )

        # ギルドのクリーンアップを実行
        await delete_bump_config(db_session, guild_id)
        reminder_count = await delete_bump_reminders_by_guild(db_session, guild_id)

        assert reminder_count == 2

        # 全て削除されていることを確認
        assert await get_bump_config(db_session, guild_id) is None
        assert await get_bump_reminder(db_session, guild_id, "DISBOARD") is None
        assert await get_bump_reminder(db_session, guild_id, "ディス速報") is None

    async def test_sticky_cleanup_multiple_channels(
        self, db_session: AsyncSession
    ) -> None:
        """複数チャンネルのstickyメッセージを持つギルドのクリーンアップ。"""
        guild_id = snowflake()

        # 複数チャンネルにstickyを作成
        await create_sticky_message(
            db_session,
            channel_id=snowflake(),
            guild_id=guild_id,
            title="Sticky 1",
            description="Description 1",
            color=0xFF0000,
            cooldown_seconds=5,
        )
        await create_sticky_message(
            db_session,
            channel_id=snowflake(),
            guild_id=guild_id,
            title="Sticky 2",
            description="Description 2",
            color=0x00FF00,
            cooldown_seconds=10,
        )
        await create_sticky_message(
            db_session,
            channel_id=snowflake(),
            guild_id=guild_id,
            title="Sticky 3",
            description="Description 3",
            color=0x0000FF,
            cooldown_seconds=15,
        )

        # ギルドのクリーンアップを実行
        sticky_count = await delete_sticky_messages_by_guild(db_session, guild_id)

        assert sticky_count == 3

        # 全て削除されていることを確認
        all_stickies = await get_all_sticky_messages(db_session)
        guild_stickies = [s for s in all_stickies if s.guild_id == guild_id]
        assert len(guild_stickies) == 0

    async def test_full_guild_cleanup(self, db_session: AsyncSession) -> None:
        """ギルドの全データを一括クリーンアップする統合テスト。

        実際の on_guild_remove イベントで行われる操作をシミュレート。
        """
        guild_id = snowflake()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        # --- セットアップ: ギルドに様々なデータを作成 ---

        # Bump関連
        bump_channel = snowflake()
        await upsert_bump_config(db_session, guild_id, bump_channel)
        await upsert_bump_reminder(
            db_session,
            guild_id=guild_id,
            channel_id=bump_channel,
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        # Sticky関連
        await create_sticky_message(
            db_session,
            channel_id=snowflake(),
            guild_id=guild_id,
            title="Test Sticky",
            description="Test",
            color=0xFF0000,
            cooldown_seconds=5,
        )

        # --- クリーンアップ実行 (on_guild_remove の処理をシミュレート) ---

        # Bump
        await delete_bump_config(db_session, guild_id)
        bump_count = await delete_bump_reminders_by_guild(db_session, guild_id)

        # Sticky
        sticky_count = await delete_sticky_messages_by_guild(db_session, guild_id)

        # --- 検証 ---
        assert bump_count == 1
        assert sticky_count == 1

        # 全て削除されていることを確認
        assert await get_bump_config(db_session, guild_id) is None
        all_stickies = await get_all_sticky_messages(db_session)
        assert all(s.guild_id != guild_id for s in all_stickies)

    async def test_cleanup_isolation_between_guilds(
        self, db_session: AsyncSession
    ) -> None:
        """ギルドAのクリーンアップがギルドBに影響しないことを確認。"""
        guild_a = snowflake()
        guild_b = snowflake()
        remind_at = datetime.now(UTC) + timedelta(hours=2)

        # ギルドAにデータを作成
        await upsert_bump_config(db_session, guild_a, snowflake())
        await upsert_bump_reminder(
            db_session,
            guild_id=guild_a,
            channel_id=snowflake(),
            service_name="DISBOARD",
            remind_at=remind_at,
        )
        await create_sticky_message(
            db_session,
            channel_id=snowflake(),
            guild_id=guild_a,
            title="A Sticky",
            description="A",
            color=0xFF0000,
            cooldown_seconds=5,
        )

        # ギルドBにデータを作成
        await upsert_bump_config(db_session, guild_b, snowflake())
        await upsert_bump_reminder(
            db_session,
            guild_id=guild_b,
            channel_id=snowflake(),
            service_name="DISBOARD",
            remind_at=remind_at,
        )
        await create_sticky_message(
            db_session,
            channel_id=snowflake(),
            guild_id=guild_b,
            title="B Sticky",
            description="B",
            color=0x00FF00,
            cooldown_seconds=5,
        )

        # ギルドAのみクリーンアップ
        await delete_bump_config(db_session, guild_a)
        await delete_bump_reminders_by_guild(db_session, guild_a)
        await delete_sticky_messages_by_guild(db_session, guild_a)

        # ギルドAは空
        assert await get_bump_config(db_session, guild_a) is None

        # ギルドBは残っている
        assert await get_bump_config(db_session, guild_b) is not None
        assert await get_bump_reminder(db_session, guild_b, "DISBOARD") is not None
        all_stickies = await get_all_sticky_messages(db_session)
        guild_b_stickies = [s for s in all_stickies if s.guild_id == guild_b]
        assert len(guild_b_stickies) == 1


class TestTicketLifecycle:
    """チケットの作成→クレーム→クローズのライフサイクルテスト。"""

    async def test_create_claim_close_lifecycle(self, db_session: AsyncSession) -> None:
        """チケット作成→担当者割り当て→クローズの一連フローを検証する。"""
        guild_id = snowflake()

        # カテゴリ作成
        category = await create_ticket_category(
            db_session,
            guild_id=guild_id,
            name="General Support",
            staff_role_id=snowflake(),
        )

        # チケット作成
        channel_id = snowflake()
        ticket = await create_ticket(
            db_session,
            guild_id=guild_id,
            user_id=snowflake(),
            username="testuser",
            category_id=category.id,
            channel_id=channel_id,
            ticket_number=1,
        )
        assert ticket.status == "open"
        assert ticket.channel_id == channel_id
        assert ticket.claimed_by is None
        assert ticket.closed_by is None
        assert ticket.transcript is None
        assert ticket.closed_at is None

        # 担当者割り当て (claimed)
        staff_name = "staff_user"
        ticket = await update_ticket_status(
            db_session,
            ticket,
            status="claimed",
            claimed_by=staff_name,
        )
        assert ticket.status == "claimed"
        assert ticket.claimed_by == staff_name
        assert ticket.channel_id == channel_id  # channel_id は変わらない

        # クローズ
        closed_at = datetime.now(UTC)
        transcript_text = "User: Hello\nStaff: How can I help?"
        ticket = await update_ticket_status(
            db_session,
            ticket,
            status="closed",
            closed_by=staff_name,
            transcript=transcript_text,
            closed_at=closed_at,
            channel_id=None,
        )
        assert ticket.status == "closed"
        assert ticket.closed_by == staff_name
        assert ticket.transcript == transcript_text
        assert ticket.closed_at is not None
        assert ticket.channel_id is None

    async def test_ticket_number_auto_increment(self, db_session: AsyncSession) -> None:
        """同一ギルドで3件のチケット作成後、次の番号が4になる。"""
        guild_id = snowflake()

        category = await create_ticket_category(
            db_session,
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )

        # 3件のチケットを作成
        for i in range(1, 4):
            await create_ticket(
                db_session,
                guild_id=guild_id,
                user_id=snowflake(),
                username=f"user{i}",
                category_id=category.id,
                channel_id=snowflake(),
                ticket_number=i,
            )

        next_num = await get_next_ticket_number(db_session, guild_id)
        assert next_num == 4

    async def test_ticket_number_empty_guild_returns_1(
        self, db_session: AsyncSession
    ) -> None:
        """チケットが存在しないギルドでは次の番号が1になる。"""
        guild_id = snowflake()
        next_num = await get_next_ticket_number(db_session, guild_id)
        assert next_num == 1

    async def test_update_ticket_channel_id_to_none(
        self, db_session: AsyncSession
    ) -> None:
        """channel_id を明示的に None に更新できる。"""
        guild_id = snowflake()
        channel_id = snowflake()

        category = await create_ticket_category(
            db_session,
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )

        ticket = await create_ticket(
            db_session,
            guild_id=guild_id,
            user_id=snowflake(),
            username="testuser",
            category_id=category.id,
            channel_id=channel_id,
            ticket_number=1,
        )
        assert ticket.channel_id == channel_id

        # channel_id を None に更新
        ticket = await update_ticket_status(
            db_session,
            ticket,
            channel_id=None,
        )
        assert ticket.channel_id is None

        # DB から再取得して確認
        reloaded = await get_ticket(db_session, ticket.id)
        assert reloaded is not None
        assert reloaded.channel_id is None

    async def test_update_ticket_preserves_unset_fields(
        self, db_session: AsyncSession
    ) -> None:
        """status のみ更新した場合、channel_id は変更されない。"""
        guild_id = snowflake()
        channel_id = snowflake()

        category = await create_ticket_category(
            db_session,
            guild_id=guild_id,
            name="Support",
            staff_role_id=snowflake(),
        )

        ticket = await create_ticket(
            db_session,
            guild_id=guild_id,
            user_id=snowflake(),
            username="testuser",
            category_id=category.id,
            channel_id=channel_id,
            ticket_number=1,
        )

        # status のみ更新（channel_id は _UNSET のまま）
        ticket = await update_ticket_status(
            db_session,
            ticket,
            status="claimed",
            claimed_by="staff",
        )

        # channel_id は元の値のまま
        assert ticket.status == "claimed"
        assert ticket.channel_id == channel_id

        # DB から再取得して確認
        reloaded = await get_ticket(db_session, ticket.id)
        assert reloaded is not None
        assert reloaded.channel_id == channel_id


# =============================================================================
# エッジケーステスト（追加）
# =============================================================================


class TestTicketNumberEdgeCases:
    """チケット番号のエッジケーステスト。"""

    async def test_same_ticket_number_different_guilds(
        self, db_session: AsyncSession
    ) -> None:
        """異なるギルドで同じチケット番号を使用できる。"""
        g1, g2 = snowflake(), snowflake()

        cat1 = await create_ticket_category(
            db_session, guild_id=g1, name="Support", staff_role_id=snowflake()
        )
        cat2 = await create_ticket_category(
            db_session, guild_id=g2, name="Support", staff_role_id=snowflake()
        )

        # 両ギルドで ticket_number=1
        t1 = await create_ticket(
            db_session,
            guild_id=g1,
            user_id=snowflake(),
            username="user1",
            category_id=cat1.id,
            channel_id=snowflake(),
            ticket_number=1,
        )
        t2 = await create_ticket(
            db_session,
            guild_id=g2,
            user_id=snowflake(),
            username="user2",
            category_id=cat2.id,
            channel_id=snowflake(),
            ticket_number=1,
        )

        assert t1.ticket_number == 1
        assert t2.ticket_number == 1
        assert t1.guild_id != t2.guild_id

    async def test_ticket_number_after_closed_tickets(
        self, db_session: AsyncSession
    ) -> None:
        """クローズ済みチケットがあっても次の番号は最大値+1。"""
        guild_id = snowflake()
        cat = await create_ticket_category(
            db_session, guild_id=guild_id, name="Support", staff_role_id=snowflake()
        )

        # 3件作成して全部クローズ
        for i in range(1, 4):
            ticket = await create_ticket(
                db_session,
                guild_id=guild_id,
                user_id=snowflake(),
                username=f"user{i}",
                category_id=cat.id,
                channel_id=snowflake(),
                ticket_number=i,
            )
            await update_ticket_status(
                db_session,
                ticket,
                status="closed",
                closed_by="staff",
                closed_at=datetime.now(UTC),
                channel_id=None,
            )

        next_num = await get_next_ticket_number(db_session, guild_id)
        assert next_num == 4


class TestBumpReminderEdgeCases:
    """Bump リマインダーのエッジケーステスト。"""

    async def test_upsert_updates_remind_at(self, db_session: AsyncSession) -> None:
        """同じギルド・サービスの upsert は remind_at を更新する。"""
        guild_id = snowflake()
        channel_id = snowflake()
        original_time = datetime.now(UTC) + timedelta(hours=1)
        new_time = datetime.now(UTC) + timedelta(hours=3)

        r1 = await upsert_bump_reminder(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            service_name="disboard",
            remind_at=original_time,
        )

        r2 = await upsert_bump_reminder(
            db_session,
            guild_id=guild_id,
            channel_id=channel_id,
            service_name="disboard",
            remind_at=new_time,
        )

        assert r1.id == r2.id  # 同じレコード
        fetched = await get_bump_reminder(db_session, guild_id, "disboard")
        assert fetched is not None
        # remind_at が更新されている
        assert abs((fetched.remind_at - new_time).total_seconds()) < 1

    async def test_clear_already_cleared_reminder(
        self, db_session: AsyncSession
    ) -> None:
        """既に cleared のリマインダーを再度 clear すると False を返す。"""
        guild_id = snowflake()
        reminder = await upsert_bump_reminder(
            db_session,
            guild_id=guild_id,
            channel_id=snowflake(),
            service_name="disboard",
            remind_at=datetime.now(UTC) + timedelta(hours=1),
        )

        # 1回目のクリア
        assert await clear_bump_reminder(db_session, reminder.id) is True
        fetched = await get_bump_reminder(db_session, guild_id, "disboard")
        assert fetched is not None
        assert fetched.remind_at is None

        # 2回目のクリア（既に None → アトミックに False）
        assert await clear_bump_reminder(db_session, reminder.id) is False

    async def test_toggle_nonexistent_reminder_creates_disabled(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないリマインダーの toggle は無効状態で新規作成する。"""
        guild_id = snowflake()
        result = await toggle_bump_reminder(db_session, guild_id, "newservice")
        assert result is False  # 新規作成時は無効 (is_enabled=False)

        # 確認: レコードが作成されている
        reminder = await get_bump_reminder(db_session, guild_id, "newservice")
        assert reminder is not None
        assert reminder.is_enabled is False

    async def test_due_reminders_excludes_cleared(
        self, db_session: AsyncSession
    ) -> None:
        """remind_at が None のリマインダーは due リストに含まれない。"""
        guild_id = snowflake()
        reminder = await upsert_bump_reminder(
            db_session,
            guild_id=guild_id,
            channel_id=snowflake(),
            service_name="disboard",
            remind_at=datetime.now(UTC) - timedelta(hours=1),
        )

        # クリア前は due に含まれる
        due = await get_due_bump_reminders(db_session, datetime.now(UTC))
        assert any(r.id == reminder.id for r in due)

        # クリア後は due に含まれない
        await clear_bump_reminder(db_session, reminder.id)
        due = await get_due_bump_reminders(db_session, datetime.now(UTC))
        assert not any(r.id == reminder.id for r in due)


class TestRolePanelItemEdgeCases:
    """RolePanel アイテムのエッジケーステスト。"""

    async def test_remove_nonexistent_emoji_returns_false(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない絵文字の削除は False を返す。"""
        panel = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Test",
        )

        result = await remove_role_panel_item(db_session, panel.id, "🎵")
        assert result is False

    async def test_get_items_from_nonexistent_panel(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないパネルのアイテム取得は空リスト。"""
        items = await get_role_panel_items(db_session, 999999)
        assert items == []

    async def test_item_emoji_lookup_wrong_panel(
        self, db_session: AsyncSession
    ) -> None:
        """別のパネルの絵文字は見つからない。"""
        panel1 = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Panel 1",
        )
        panel2 = await create_role_panel(
            db_session,
            guild_id=snowflake(),
            channel_id=snowflake(),
            panel_type="button",
            title="Panel 2",
        )

        await add_role_panel_item(
            db_session, panel_id=panel1.id, role_id=snowflake(), emoji="🎮"
        )

        # panel2 から panel1 の絵文字を検索 → None
        result = await get_role_panel_item_by_emoji(db_session, panel2.id, "🎮")
        assert result is None


class TestStickyMessageEdgeCases:
    """Sticky メッセージのエッジケーステスト。"""

    async def test_delete_nonexistent_returns_false(
        self, db_session: AsyncSession
    ) -> None:
        """存在しないチャンネルの Sticky 削除は False を返す。"""
        result = await delete_sticky_message(db_session, snowflake())
        assert result is False

    async def test_upsert_preserves_channel_across_guilds(
        self, db_session: AsyncSession
    ) -> None:
        """異なるギルドで同じチャンネルID の Sticky は上書きされる。"""
        channel_id = snowflake()
        g1 = snowflake()
        g2 = snowflake()

        await create_sticky_message(
            db_session,
            channel_id=channel_id,
            guild_id=g1,
            title="Guild 1 Sticky",
            description="First",
        )

        # 同じ channel_id で別ギルドから upsert
        await create_sticky_message(
            db_session,
            channel_id=channel_id,
            guild_id=g2,
            title="Guild 2 Sticky",
            description="Second",
        )

        # 最後の upsert が反映される
        fetched = await get_sticky_message(db_session, channel_id)
        assert fetched is not None
        assert fetched.title == "Guild 2 Sticky"
        assert fetched.guild_id == g2


class TestBulkDeletionEdgeCases:
    """一括削除のエッジケーステスト。"""

    async def test_bulk_delete_empty_guild_returns_zero(
        self, db_session: AsyncSession
    ) -> None:
        """データのないギルドの一括削除は 0 を返す。"""
        empty_guild = snowflake()

        assert await delete_bump_reminders_by_guild(db_session, empty_guild) == 0
        assert await delete_sticky_messages_by_guild(db_session, empty_guild) == 0

    async def test_delete_config_nonexistent_returns_false(
        self, db_session: AsyncSession
    ) -> None:
        """存在しない BumpConfig の削除は False を返す。"""
        result = await delete_bump_config(db_session, snowflake())
        assert result is False

    async def test_bulk_delete_does_not_affect_other_guilds(
        self, db_session: AsyncSession
    ) -> None:
        """一括削除は他のギルドに影響しない。"""
        g1, g2 = snowflake(), snowflake()

        # 両ギルドに sticky メッセージを作成
        for gid in [g1, g2]:
            await create_sticky_message(
                db_session,
                channel_id=snowflake(),
                guild_id=gid,
                title=f"Sticky {gid}",
                description="test",
                color=0,
                cooldown_seconds=5,
            )

        # g1 の sticky のみ削除
        count = await delete_sticky_messages_by_guild(db_session, g1)
        assert count == 1

        # g2 の sticky は残っている
        all_stickies = await get_all_sticky_messages(db_session)
        g2_stickies = [s for s in all_stickies if s.guild_id == g2]
        assert len(g2_stickies) == 1


class TestUpsertIdempotency:
    """Upsert の冪等性テスト。"""

    async def test_bump_config_upsert_updates_channel(
        self, db_session: AsyncSession
    ) -> None:
        """BumpConfig の upsert は channel_id を更新する。"""
        guild_id = snowflake()
        ch1 = snowflake()
        ch2 = snowflake()

        await upsert_bump_config(db_session, guild_id=guild_id, channel_id=ch1)
        config1 = await get_bump_config(db_session, guild_id)
        assert config1 is not None
        assert config1.channel_id == ch1

        # 同じ guild_id で upsert
        await upsert_bump_config(db_session, guild_id=guild_id, channel_id=ch2)
        config2 = await get_bump_config(db_session, guild_id)
        assert config2 is not None
        assert config2.channel_id == ch2

    async def test_discord_guild_upsert_updates_name(
        self, db_session: AsyncSession
    ) -> None:
        """DiscordGuild の upsert はギルド名を更新する。"""
        guild_id = snowflake()

        await upsert_discord_guild(db_session, guild_id=guild_id, guild_name="Original")
        await upsert_discord_guild(db_session, guild_id=guild_id, guild_name="Renamed")

        guilds = await get_all_discord_guilds(db_session)
        matching = [g for g in guilds if g.guild_id == guild_id]
        assert len(matching) == 1
        assert matching[0].guild_name == "Renamed"

    async def test_discord_guild_upsert_updates_icon_hash(
        self, db_session: AsyncSession
    ) -> None:
        """DiscordGuild の upsert は icon_hash を更新する。"""
        guild_id = snowflake()

        await upsert_discord_guild(
            db_session, guild_id=guild_id, guild_name="Test", icon_hash=None
        )
        await upsert_discord_guild(
            db_session,
            guild_id=guild_id,
            guild_name="Test",
            icon_hash="abc123def456",
        )

        guilds = await get_all_discord_guilds(db_session)
        matching = [g for g in guilds if g.guild_id == guild_id]
        assert len(matching) == 1
        assert matching[0].icon_hash == "abc123def456"
