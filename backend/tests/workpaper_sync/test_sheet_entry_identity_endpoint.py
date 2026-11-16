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


# ─────────────────────────────────────────────────────────────────────────────
# task 2.3：artifact reader 只在 ready / migrated binding 上运行
#
# 这两个用例是「接线」的判据，不是 reader 自身的判据（reader 有自己的 4 例）。
# 它们防住两种相反的错误：
#   * pending binding 也去读 artifact ⇒ 未审核入口被当成可开（Requirement 3 违反）；
#   * ready binding 不去读 artifact ⇒ 接线是假的，room 仍从模板/旧 config 出发。
# ─────────────────────────────────────────────────────────────────────────────


def _endpoint_app(monkeypatch):
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
    return app


def _patch_binding(monkeypatch, *, status: str, binding: dict | None):
    from app.services.workpaper_sync import sheet_open_bindings as MODULE

    def fake_resolve(self, **_kwargs):
        return MODULE.SheetOpenBindingResolution(status, None, binding)

    monkeypatch.setattr(MODULE.SheetOpenBindingResolver, "resolve", fake_resolve)


def _patch_artifact_reader(monkeypatch, *, calls: list):
    from app.services.workpaper_sync import sheet_published_artifact as MODULE

    async def fake_read(**kwargs):
        calls.append(kwargs)
        raise MODULE.PublishedSheetArtifactError(
            "current_representation_missing", "测试用：没有可见 current representation"
        )

    monkeypatch.setattr(MODULE, "read_current_published_sheet_artifact", fake_read)


def test_pending_binding_never_reads_published_artifact(monkeypatch) -> None:
    """pending binding ⇒ 不实例化 sync services、不读 artifact。

    🔴 断言必须落在 `calls` 上而不是「抛异常」上：端点有 `except Exception` 兜底，
    抛出的断言会被吞成 `status=pending`，若只看响应就与「正常 pending」不可区分
    （实测变异 M2 即因此存活）。所以这里**记录调用**并断言为空。
    """
    app = _endpoint_app(monkeypatch)
    _patch_binding(monkeypatch, status="pending", binding=None)

    calls: list = []

    def forbidden(*_args, **_kwargs):
        calls.append("build_sync_services")
        raise AssertionError("pending binding 不得装配 sync services（会读 artifact）")

    monkeypatch.setattr(ROUTER, "build_sync_services", forbidden)
    _patch_artifact_reader(monkeypatch, calls=calls)

    response = TestClient(app).get(
        f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entry-identity",
        params={"sheet_name": "资产减值损失检查表K11"},
    )
    assert response.status_code == 200
    assert calls == []


def test_ready_binding_reads_published_artifact_and_reports_typed_reason(monkeypatch) -> None:
    """ready binding ⇒ 读 artifact；reader 失败必须降级成 pending + 机器可读原因。"""
    app = _endpoint_app(monkeypatch)
    binding = {
        "entry_id": "xlsx/gt-k11-asset-impairment-loss",
        "effective_entry_id": "xlsx/gt-k11-asset-impairment-loss",
        "source_wp_code": "K11",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "target_sheet": "K11-1",
        "mapping_kind": "exact",
        "status": "ready",
        "binding_id": "sha256:test",
    }
    _patch_binding(monkeypatch, status="ready", binding=binding)

    class _Artifacts:
        pass

    class _Registry:
        pass

    monkeypatch.setattr(
        ROUTER,
        "build_sync_services",
        lambda _db, _user: SimpleNamespace(artifacts=_Artifacts(), registry=_Registry()),
    )

    calls: list = []
    _patch_artifact_reader(monkeypatch, calls=calls)

    response = TestClient(app).get(
        f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entry-identity",
        params={"sheet_name": "资产减值损失检查表K11"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(calls) == 1
    assert calls[0]["entry_id"] == "xlsx/gt-k11-asset-impairment-loss"
    assert calls[0]["target_sheet"] == "K11-1"
    assert calls[0]["whole_workbook"] is False
    assert body["status"] == "pending"
    assert body["reason"] == "current_representation_missing"
    assert body["room_ready"] is False
    assert body["allowed_modes"] == ["html"]
    # 失败路径不得留下半截 representation 字段
    assert "representation" not in body


def test_pending_binding_with_entry_id_still_skips_artifact_read(monkeypatch) -> None:
    """pending 但 binding 非空（真实形态：`sheet_binding_entry_not_in_manifest`）。

    🔴 这条用例是上面那条的**必要补充**，不是重复：`binding=None` 时 `entry_id is None`
    在更早的分支就 return 了，根本没走到 `status` 门控 ⇒ 单靠那条用例时把门控改成
    恒真仍然全绿（实测变异存活）。真实业务里 pending 与「有 binding」同时成立的形态
    至少有 `sheet_binding_entry_not_in_manifest` / `sheet_binding_status_invalid` 两种，
    它们都必须不读 artifact。
    """
    app = _endpoint_app(monkeypatch)
    binding = {
        "entry_id": "xlsx/gt-k11-asset-impairment-loss",
        "effective_entry_id": "xlsx/gt-k11-asset-impairment-loss",
        "source_wp_code": "K11",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "target_sheet": "K11-1",
        "mapping_kind": "exact",
        "status": "pending",
        "binding_id": "sha256:test",
    }
    _patch_binding(monkeypatch, status="pending", binding=binding)

    calls: list = []

    def forbidden(*_args, **_kwargs):
        calls.append("build_sync_services")
        raise AssertionError("pending binding（即使带 entry_id）不得装配 sync services")

    monkeypatch.setattr(ROUTER, "build_sync_services", forbidden)
    _patch_artifact_reader(monkeypatch, calls=calls)

    response = TestClient(app).get(
        f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entry-identity",
        params={"sheet_name": "资产减值损失检查表K11"},
    )
    assert response.status_code == 200
    assert calls == []
    assert response.json()["status"] == "pending"
