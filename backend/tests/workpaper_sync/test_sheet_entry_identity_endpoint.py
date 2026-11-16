"""Sheet entry identity 端点的真实 HTTP 线守卫。"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import deps
from app.routers import wp_onlyoffice_router
from app.routers import wp_sync_router as ROUTER

PROJECT = uuid.uuid4()
WP = uuid.uuid4()


def test_pending_sheet_does_not_fabricate_xlsx_sheet_entry(monkeypatch) -> None:
    """当前 K11 provider mapping 未有 exact target 时，端点必须返回 pending。

    这条用例直接防住原实现：原实现会无条件调用 `sheet_entry_id()`，返回
    `xlsx-sheet/K11/...`，再把不存在的 entry 送给 readiness，导致表面上有身份、
    实际永远 404。新语义是「binding 未完成 = pending」，不伪造 room entry。
    """
    app = FastAPI()
    app.include_router(ROUTER.router)

    async def fake_db():
        yield object()

    async def fake_user():
        return SimpleNamespace(id=uuid.uuid4())

    async def fake_authorize(_db, _user, _wp_id):
        return PROJECT

    async def fake_load(_db, _wp_id):
        return SimpleNamespace(project_id=PROJECT), "K11"

    app.dependency_overrides[ROUTER.get_db] = fake_db
    app.dependency_overrides[ROUTER.get_current_user] = fake_user
    monkeypatch.setattr(deps, "authorize_wp_read", fake_authorize)
    monkeypatch.setattr(wp_onlyoffice_router, "_load_wp_or_404", fake_load)

    client = TestClient(app)
    response = client.get(
        f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entry-identity",
        params={"sheet_name": "资产减值损失检查表K11"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["reason"] == "sheet_binding_provider_review_required"
    assert body["entry_id"] is None
    assert not str(body.get("entry_id") or "").startswith("xlsx-sheet/")
