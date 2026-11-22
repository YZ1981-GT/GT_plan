"""entry-identity 的项目级 representation pin 回归守卫。

spec: onlyoffice-sheet-open-via-published-artifact · task 3.3

同一 entry 可同时挂在多个项目。sheet 级入口先解析 binding，再读取目标项目的
published representation；如果沿用 entry 级「第一家可见底稿」查询，目标项目会被
错误地判成 representation_row_missing，canary 无法取得真实 artifact identity。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import deps
from app.routers import wp_onlyoffice_router
from app.routers import wp_sync_router as ROUTER
from app.services.workpaper_sync.projection_target_resolution import (
    current_representation_target,
)
from app.services.workpaper_sync.sheet_open_bindings import (
    SheetOpenBindingResolution,
    SheetOpenBindingResolver,
)

PROJECT = uuid.uuid4()
WP = uuid.uuid4()


def test_entry_identity_pins_artifact_reader_to_requested_workpaper(monkeypatch) -> None:
    """目标底稿的 representation pin 必须覆盖 artifact reader，且请求结束后清理。"""
    app = FastAPI()
    app.include_router(ROUTER.router)

    async def fake_db():
        yield object()

    async def fake_user():
        return SimpleNamespace(id=uuid.uuid4())

    async def fake_authorize(_db, _user, _wp_id):
        return PROJECT

    async def fake_load(_db, _wp_id):
        return SimpleNamespace(project_id=PROJECT), "D4"

    app.dependency_overrides[ROUTER.get_db] = fake_db
    app.dependency_overrides[ROUTER.get_current_user] = fake_user
    monkeypatch.setattr(deps, "authorize_wp_read", fake_authorize)
    monkeypatch.setattr(wp_onlyoffice_router, "_load_wp_or_404", fake_load)

    binding = {
        "entry_id": "xlsx/gt-d4-operating-revenue",
        "effective_entry_id": "xlsx/gt-d4-operating-revenue",
        "source_wp_code": "D4",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "target_sheet": "主营业务收入明细表D4-2",
        "mapping_kind": "provider",
        "status": "migrated",
        "binding_id": "sha256:test",
    }
    monkeypatch.setattr(
        SheetOpenBindingResolver,
        "resolve",
        lambda self, **_kwargs: SheetOpenBindingResolution("migrated", None, binding),
    )
    monkeypatch.setattr(
        ROUTER,
        "build_sync_services",
        lambda _db, _user: SimpleNamespace(artifacts=object(), registry=object()),
    )

    observed: dict[str, object] = {}
    artifact_module = __import__(
        "app.services.workpaper_sync.sheet_published_artifact",
        fromlist=["read_current_published_sheet_artifact"],
    )

    async def fake_reader(**kwargs):
        pin = current_representation_target()
        observed["wp_id"] = kwargs["wp_id"]
        observed["target_sheet"] = kwargs["target_sheet"]
        observed["pinned_wp_id"] = pin.wp_id if pin is not None else None
        raise artifact_module.PublishedSheetArtifactError(
            "current_representation_missing",
            "测试：没有可见 current representation",
        )

    monkeypatch.setattr(artifact_module, "read_current_published_sheet_artifact", fake_reader)

    response = TestClient(app).get(
        f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entry-identity",
        params={"sheet_name": "主营业务收入明细表D4-2"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["entry_id"] == "xlsx/gt-d4-operating-revenue"
    assert body["target_sheet"] == "主营业务收入明细表D4-2"
    assert body["error_code"] == "current_representation_missing"
    assert observed == {
        "wp_id": WP,
        "target_sheet": "主营业务收入明细表D4-2",
        "pinned_wp_id": WP,
    }
    assert current_representation_target() is None
