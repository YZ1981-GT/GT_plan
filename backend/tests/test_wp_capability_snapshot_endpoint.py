# -*- coding: utf-8 -*-
"""`GET /api/workpapers/{wp_id}/capability-snapshot` 端点集成守卫。

代替浏览器实测「前端 formula shell 挂载能拉到快照」的后端半：用 ASGITransport 打真实
注册的路由，断言 200 + 前端 parser 需要的 wire 形状（snapshotVersion/ownerEpoch/
subjectDigest/expiresAt + 9 键 decision）。角色不同 → 判定不同（fail-closed）。

Spec: d4-adjustment-and-analysis-gap-closure Task 5
Requirements: 3.1
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.models.base import UserRole
from app.routers.wp_capability_snapshot import router as capability_router

_FRONTEND_KEYS = (
    "formulaView", "formulaEditUser", "formulaHistory", "aiReviewPage",
    "aiReviewBatch", "aiAssistChat", "humanReviewRead", "humanReviewWrite", "guidanceRead",
)


class _FakeUser:
    def __init__(self, role: UserRole) -> None:
        self.id = uuid.uuid4()
        self.role = role


def _make_client(role: UserRole) -> AsyncClient:
    app = FastAPI()
    app.include_router(capability_router)
    app.dependency_overrides[get_current_user] = lambda: _FakeUser(role)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_snapshot_endpoint_returns_full_wire_shape() -> None:
    async with _make_client(UserRole.auditor) as client:
        resp = await client.get(
            "/api/workpapers/wp-D4-4/capability-snapshot",
            params={"project_id": "p1", "ownerEpoch": 3, "sheetUid": "sh1"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["snapshotVersion"] == "1.0"
    assert body["ownerEpoch"] == 3
    assert body["wpId"] == "wp-D4-4"
    assert len(body["subjectDigest"]) == 64
    assert body["expiresAt"]
    for key in _FRONTEND_KEYS:
        assert key in body
        assert isinstance(body[key]["allowed"], bool)


@pytest.mark.asyncio
async def test_snapshot_endpoint_role_differentiates_capabilities() -> None:
    async with _make_client(UserRole.readonly) as client:
        resp = await client.get(
            "/api/workpapers/wp-D4-4/capability-snapshot",
            params={"project_id": "p1", "ownerEpoch": 1},
        )
    body = resp.json()
    assert body["formulaView"]["allowed"] is True
    assert body["formulaEditUser"]["allowed"] is False  # viewer 只读


@pytest.mark.asyncio
async def test_capability_assert_endpoint_allows_permitted_and_rejects_unknown() -> None:
    async with _make_client(UserRole.manager) as client:
        ok = await client.get(
            "/api/workpapers/wp-D4-4/capability-assert",
            params={"project_id": "p1", "capability": "formulaEditUser", "ownerEpoch": 5},
        )
        unknown = await client.get(
            "/api/workpapers/wp-D4-4/capability-assert",
            params={"project_id": "p1", "capability": "unknownCap", "ownerEpoch": 5},
        )
    # reviewer(manager) 可编辑用户公式；assert 端点主体 epoch 恒等于查询 epoch（自洽）。
    assert ok.json()["status"] == "allowed"
    assert unknown.json()["reasonCode"] == "unknown_capability"


@pytest.mark.asyncio
async def test_capability_assert_blocks_viewer_edit() -> None:
    async with _make_client(UserRole.readonly) as client:
        blocked = await client.get(
            "/api/workpapers/wp-D4-4/capability-assert",
            params={"project_id": "p1", "capability": "formulaEditUser", "ownerEpoch": 2},
        )
    verdict = blocked.json()
    assert verdict["status"] == "blocked"
    assert verdict["reasonCode"] in {"viewer_read_only", "role_denied"}
