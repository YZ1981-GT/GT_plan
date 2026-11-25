"""Sheet entry identity 端点的真实 HTTP 线守卫。"""
from __future__ import annotations

import uuid

import pytest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import deps
from app.routers import wp_onlyoffice_router
from app.routers import wp_sync_router as ROUTER

PROJECT = uuid.uuid4()
WP = uuid.uuid4()


@pytest.fixture(autouse=True)
def _gate_calls(monkeypatch) -> list[dict]:
    """本文件测端点的业务分支，鉴权全部替身（authorize_wp_read 已替换）。

    2026-11-25 端点补接了平台 wp 可见性门 ``enforce_wp_gate``；这里同样替身并记录调用，
    门本身的判定由 wp_visibility 自己的测试覆盖。接线与拒绝路径见文件末两条用例。
    """
    from app.routers import _wp_gate

    calls: list[dict] = []

    async def fake_gate(_db, _user, **kw):
        calls.append(kw)
        return SimpleNamespace(readonly=False)

    monkeypatch.setattr(_wp_gate, "enforce_wp_gate", fake_gate)
    return calls


def test_pending_sheet_does_not_fabricate_xlsx_sheet_entry(monkeypatch) -> None:
    """K11 的 provider binding 未审核 ⇒ 端点必须返回 pending，且不伪造 room 身份。

    这条用例防住两种相反的错误：

    * **原实现**会无条件调用 `sheet_entry_id()`，返回 `xlsx-sheet/K11/...` —— 那个
      entry 在 manifest 里根本不存在，表面上有身份、实际永远 404；
    * **反过来**把 provider 解析成功当成「可迁移」也不行 —— `status` 必须完全取自
      生成物（未审核就是 `pending`），解析出 binding ≠ 允许开门。

    🔴 2026-11-17 语义更新：批 2 给 resolver 补上 provider 型解析后，provider binding
    现在**能解析出真实 manifest entry**（`xlsx/gt-k11-asset-impairment-loss`），
    而不再是「拿不到 entry」。所以判据从「entry_id 必须为 None」升级为
    「entry_id 必须是真实 manifest entry、且状态仍是 pending」—— 前者在解析能力
    到位后本就该消失，后者才是本 spec 真正要守的东西（Requirement 3）。
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
    # ① 状态取自生成物：未审核 ⇒ pending（不因为解析成功就晋级）
    assert body["status"] == "pending"
    # ② 原因必须是 binding 自己的**封闭原因码**，不是 readiness 的技术异常名。
    #    这条同时钉住「pending 不跑 readiness」——跑 readiness 会把它覆盖成
    #    `该底稿尚未接入统一在线编辑（AttributeError）`（本用例的测试替身没有真库）。
    assert body["reason"] == "runtime_sheet_name_requires_provider_binding"
    # ③ 身份必须是真实 manifest entry，且**永远**不是 `xlsx-sheet/*` 虚构命名空间
    assert body["entry_id"] == "xlsx/gt-k11-asset-impairment-loss"
    assert not str(body.get("entry_id") or "").startswith("xlsx-sheet/")
    # ④ pending 不得声明 room 可用（否则前端/其它消费方会绕过审核开门）
    assert body["room_ready"] is False
    assert body["allowed_modes"] == ["html"]


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
    # `error_code` 是机器可读的封闭域；`reason` 是可直接展示的中文原因（task 2.5）。
    assert body["error_code"] == "current_representation_missing"
    assert "保存一次以发布首版" in body["reason"], body["reason"]
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


# ─────────────────────────────────────────────────────────────────────────────
# 2026-11-17：`allows_room_readiness` 是「pending 不跑 readiness」的唯一判据
#
# 为什么必须单独钉：那个门住在 service（router 已到行数门上限，判据不能写在那儿），
# 所以「router 真的问了它」与「它真的对每种状态给对答案」是两个必须分别证明的事。
# 前者由上面 3 例覆盖（pending 不装配 sync services / ready 会读 artifact），
# 这里补后者 —— 少任何一半，把门改成恒真或恒假都会有一条路径静默放行。
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        # 只有这三种能走 room readiness：room 是它们的正路。
        ("ready", True),
        ("migrated", True),
        ("draining", True),
        # pending：未审核不得判成 room 可用（Requirement 3）。
        ("pending", False),
        # retired：已下线，room 不再服务它。
        ("retired", False),
        # out_of_scope：本就不适用本迁移（Word / custom）。
        ("out_of_scope", False),
        # 未知状态 fail-closed —— 服务端加新状态时不许默认放行。
        ("brand_new_state", False),
    ],
)
def test_allows_room_readiness_is_closed_and_fail_closed(status: str, expected: bool) -> None:
    from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolution

    resolution = SheetOpenBindingResolution(status, None, {"entry_id": "xlsx/x"})
    assert resolution.allows_room_readiness is expected, (
        f"status={status} 的 allows_room_readiness 应为 {expected} —— "
        "它决定「要不要跑 room readiness」，改错方向要么绕过审核、要么让已迁移入口打不开"
    )


def test_pending_reason_survives_the_whole_endpoint(monkeypatch) -> None:
    """pending 的封闭原因码必须原样到达响应，不得被 readiness 的技术异常名盖掉。

    这是 2026-11-17 实测到的真缺陷的回归栅栏：`pending` 也去跑 readiness 时，
    端点 `except Exception` 会把它压成 `该底稿尚未接入统一在线编辑（AttributeError）`
    —— 用户与前端从此看不到「为什么没迁」。上一条用例只证明 service 的属性对，
    这一条证明**端点真的按它分支**（属性对了但没人问，同样不会有正确响应）。
    """
    app = _endpoint_app(monkeypatch)
    binding = {
        "entry_id": "xlsx/gt-k11-asset-impairment-loss",
        "effective_entry_id": "xlsx/gt-k11-asset-impairment-loss",
        "source_wp_code": "K11",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "target_sheet": None,
        "mapping_kind": "provider",
        "status": "pending",
        "reason": "runtime_sheet_name_requires_provider_binding",
        "binding_id": "sha256:test",
    }
    from app.services.workpaper_sync import sheet_open_bindings as MODULE

    monkeypatch.setattr(
        MODULE.SheetOpenBindingResolver,
        "resolve",
        lambda self, **_kw: MODULE.SheetOpenBindingResolution(
            "pending", binding["reason"], binding
        ),
    )

    # readiness 一旦被调用就留下痕迹：它会把 reason 覆盖成技术异常名。
    async def forbidden_readiness(**_kwargs):
        raise AttributeError("pending 不得跑 room readiness")

    monkeypatch.setattr(ROUTER, "evaluate_entry_readiness", forbidden_readiness, raising=False)

    body = TestClient(app).get(
        f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entry-identity",
        params={"sheet_name": "资产减值损失检查表K11"},
    ).json()
    assert body["reason"] == "runtime_sheet_name_requires_provider_binding", body["reason"]
    assert "AttributeError" not in str(body.get("reason") or "")
    assert body["status"] == "pending"
    assert body["room_ready"] is False


def test_draining_binding_still_reads_artifact(monkeypatch) -> None:
    """draining 必须能读 artifact —— 否则这个状态是入口死路。

    🔴 这条是删掉内层门（`if resolution.allows_room_readiness:` 的第二次判断）后补的。
    删之前 `draining` 走不到 artifact reader，落到 `build_production_registry()` 那条
    兜底 —— 而 legacy gate 对 draining 是 **409 拒**（`DRAINING_MESSAGE`：
    「旧的编辑会话已进入收尾期…之后改用协同编辑入口打开」）⇒ 旧路被拒、新路又拿不到
    representation ⇒ **draining 期间该入口整个打不开**，与「收尾期还能继续用 room」矛盾。

    变异证明：把 `allows_room_readiness` 里的 `"draining"` 去掉，本用例打红。
    """
    app = _endpoint_app(monkeypatch)
    binding = {
        "entry_id": "xlsx/gt-d4-operating-revenue",
        "effective_entry_id": "xlsx/gt-d4-operating-revenue",
        "source_wp_code": "D4",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "target_sheet": "主营业务收入明细表D4-2",
        "mapping_kind": "provider",
        "status": "draining",
        "binding_id": "sha256:test",
    }
    _patch_binding(monkeypatch, status="draining", binding=binding)

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

    body = TestClient(app).get(
        f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entry-identity",
        params={"sheet_name": "主营业务收入明细表D4-2"},
    ).json()
    # ① 真的去读了 artifact（不是落到 production registry 的兜底）
    assert len(calls) == 1, f"draining 未读 artifact ⇒ 入口死路；calls={calls}"
    assert calls[0]["entry_id"] == "xlsx/gt-d4-operating-revenue"
    assert calls[0]["target_sheet"] == "主营业务收入明细表D4-2"
    # ② 读取失败仍降级成 typed pending（不抛 500）
    assert body["status"] == "pending"
    assert body["error_code"] == "current_representation_missing"


def _identity_app(monkeypatch) -> TestClient:
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
    return TestClient(app)


def test_entry_identity_passes_the_platform_wp_visibility_gate(monkeypatch, _gate_calls) -> None:
    """项目成员级校验之外，必须过 wp 可见性门（委派 / 复核人白名单 / History_Only）。"""
    response = _identity_app(monkeypatch).get(
        f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entry-identity",
        params={"sheet_name": "资产减值损失检查表K11"},
    )
    assert response.status_code == 200
    assert len(_gate_calls) == 1, _gate_calls
    call = _gate_calls[0]
    assert call["wp_id"] == WP and call["project_id"] == PROJECT
    assert call["entrypoint"] == ROUTER._VISIBILITY_ENTRYPOINT
    assert call["action"] == ROUTER._VISIBILITY_READ_ACTION and call["method"] == "GET"


def test_entry_identity_gate_denial_is_404_before_any_binding_work(monkeypatch) -> None:
    """门拒绝 ⇒ 404，且不得走到 binding 解析 / 已发布 artifact 读取（不泄露 entry 事实）。"""
    from app.routers import _wp_gate
    from app.services.wp_visibility.denial import ExternalNotFound

    async def deny(_db, _user, **_kw):
        raise ExternalNotFound()

    touched: list[str] = []

    def boom(*_a, **_k):
        touched.append("resolver")
        raise AssertionError("gate denial must stop before binding resolution")

    monkeypatch.setattr(_wp_gate, "enforce_wp_gate", deny)
    from app.services.workpaper_sync import sheet_open_bindings

    monkeypatch.setattr(sheet_open_bindings.SheetOpenBindingResolver, "resolve", boom)
    response = _identity_app(monkeypatch).get(
        f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entry-identity",
        params={"sheet_name": "资产减值损失检查表K11"},
    )
    assert response.status_code == 404
    assert touched == []
