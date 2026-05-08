"""Tests for db_service using factory fixtures and faker."""

from __future__ import annotations

from datetime import UTC

import pytest
from faker import Faker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.db_service import (
    add_role_panel_item,
    clear_bump_reminder,
    create_role_panel,
    create_sticky_message,
    delete_bump_config,
    delete_role_panel,
    delete_sticky_message,
    get_all_role_panels,
    get_all_sticky_messages,
    get_bump_config,
    get_bump_reminder,
    get_due_bump_reminders,
    get_role_panel,
    get_role_panel_by_message_id,
    get_role_panel_item_by_emoji,
    get_role_panel_items,
    get_role_panels_by_channel,
    get_role_panels_by_guild,
    get_sticky_message,
    remove_role_panel_item,
    toggle_bump_reminder,
    update_bump_reminder_role,
    update_role_panel,
    update_sticky_message_id,
    upsert_bump_config,
    upsert_bump_reminder,
)

from .conftest import snowflake

fake = Faker()


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
