"""Tests for excluded_role_ids in role panel API routes."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import RolePanel
from src.web.jwt_auth import create_jwt_token

if TYPE_CHECKING:
    pass


@pytest.fixture
def auth_cookie(admin_user: object) -> dict[str, str]:  # noqa: ARG001
    """認証済み Cookie を生成する。"""
    token = create_jwt_token("test@example.com")
    return {"session": token}


class TestRolePanelExcludedRoleIdsAPI:
    """excluded_role_ids の API テスト。"""

    async def test_create_panel_with_excluded_role_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_cookie: dict[str, str],
    ) -> None:
        """excluded_role_ids 付きでパネルを作成できる。"""
        body = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321012345678",
            "panel_type": "button",
            "title": "Test Panel",
            "excluded_role_ids": ["111", "222"],
            "items": [],
        }
        response = await client.post(
            "/api/v1/rolepanels",
            json=body,
            cookies=auth_cookie,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["ok"] is True

        # DB で確認
        from sqlalchemy import select

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.id == data["panel_id"])
        )
        panel = result.scalar_one()
        assert json.loads(panel.excluded_role_ids) == ["111", "222"]

    async def test_create_panel_without_excluded_role_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_cookie: dict[str, str],
    ) -> None:
        """excluded_role_ids なしでパネルを作成するとデフォルト空リストになる。"""
        body = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321012345678",
            "panel_type": "button",
            "title": "Test Panel",
            "items": [],
        }
        response = await client.post(
            "/api/v1/rolepanels",
            json=body,
            cookies=auth_cookie,
        )
        assert response.status_code == 201
        data = response.json()

        from sqlalchemy import select

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.id == data["panel_id"])
        )
        panel = result.scalar_one()
        assert json.loads(panel.excluded_role_ids) == []

    async def test_detail_returns_excluded_role_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_cookie: dict[str, str],
    ) -> None:
        """詳細 API が excluded_role_ids を返す。"""
        panel = RolePanel(
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test",
            excluded_role_ids=json.dumps(["111", "222"]),
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await client.get(
            f"/api/v1/rolepanels/{panel.id}",
            cookies=auth_cookie,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["panel"]["excluded_role_ids"] == ["111", "222"]

    async def test_list_returns_excluded_role_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_cookie: dict[str, str],
    ) -> None:
        """一覧 API が excluded_role_ids を返す。"""
        panel = RolePanel(
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test",
            excluded_role_ids=json.dumps(["333"]),
        )
        db_session.add(panel)
        await db_session.commit()

        response = await client.get(
            "/api/v1/rolepanels",
            cookies=auth_cookie,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["panels"]) == 1
        assert data["panels"][0]["excluded_role_ids"] == ["333"]

    async def test_update_panel_excluded_role_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_cookie: dict[str, str],
    ) -> None:
        """パネル更新で excluded_role_ids を変更できる。"""
        panel = RolePanel(
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test",
            excluded_role_ids="[]",
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await client.put(
            f"/api/v1/rolepanels/{panel.id}",
            json={
                "title": "Updated",
                "excluded_role_ids": ["444", "555"],
            },
            cookies=auth_cookie,
        )
        assert response.status_code == 200

        await db_session.refresh(panel)
        assert json.loads(panel.excluded_role_ids) == ["444", "555"]

    async def test_update_panel_clear_excluded_role_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_cookie: dict[str, str],
    ) -> None:
        """パネル更新で excluded_role_ids をクリアできる。"""
        panel = RolePanel(
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Test",
            excluded_role_ids=json.dumps(["111"]),
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await client.put(
            f"/api/v1/rolepanels/{panel.id}",
            json={
                "title": "Updated",
                "excluded_role_ids": [],
            },
            cookies=auth_cookie,
        )
        assert response.status_code == 200

        await db_session.refresh(panel)
        assert json.loads(panel.excluded_role_ids) == []

    async def test_copy_panel_preserves_excluded_role_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_cookie: dict[str, str],
    ) -> None:
        """パネルコピーで excluded_role_ids が引き継がれる。"""
        panel = RolePanel(
            guild_id="123",
            channel_id="456",
            panel_type="button",
            title="Original",
            excluded_role_ids=json.dumps(["666", "777"]),
        )
        db_session.add(panel)
        await db_session.commit()
        await db_session.refresh(panel)

        response = await client.post(
            f"/api/v1/rolepanels/{panel.id}/copy",
            cookies=auth_cookie,
        )
        assert response.status_code == 201
        data = response.json()

        from sqlalchemy import select

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.id == data["new_panel_id"])
        )
        copied = result.scalar_one()
        assert json.loads(copied.excluded_role_ids) == ["666", "777"]

    async def test_create_invalid_excluded_role_ids_ignored(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_cookie: dict[str, str],
    ) -> None:
        """不正な excluded_role_ids は空リストとして扱われる。"""
        body = {
            "guild_id": "123456789012345678",
            "channel_id": "987654321012345678",
            "panel_type": "button",
            "title": "Test Panel",
            "excluded_role_ids": "invalid",
            "items": [],
        }
        response = await client.post(
            "/api/v1/rolepanels",
            json=body,
            cookies=auth_cookie,
        )
        assert response.status_code == 201
        data = response.json()

        from sqlalchemy import select

        result = await db_session.execute(
            select(RolePanel).where(RolePanel.id == data["panel_id"])
        )
        panel = result.scalar_one()
        assert json.loads(panel.excluded_role_ids) == []
