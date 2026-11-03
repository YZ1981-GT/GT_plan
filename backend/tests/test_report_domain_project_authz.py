"""报表域端点的项目级鉴权（spec consol-autotree-residual-closure R1~R3；memory ㉕：端点级真发请求）。

原状：报表页 / 报表行次映射 / 报表映射 / 报表导出 / 试算分析六个 router 共 24 个端点只挂 ``get_current_user``，
任何登录用户改路径里的项目 id 就能读写别人项目的报表与映射；``require_operation`` 只看权限矩阵、不校成员，
生成报表（项目在请求体）与建调整分录（项目在路径）同样对非成员放行；期初核对的上年项目、参照复制的来源项目
不做任何校验（参照复制按名称找不到时还会随便拿一个其他项目来复制）。

做法：请求经权限世界（``tests/authz_world.py``）真发 —— 身份是世界里的真实用户与成员行，判定由生产的
``require_project_access`` / ``assert_project_permission`` / ``require_operation`` 作出，门禁不替换，每个请求都核对
生产门禁的代码确实执行过；可替换的只有当前用户、会话、RLS 上下文与业务 service（打桩计数）。
"""
from __future__ import annotations

import io
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app import deps
from app.models.base import UserRole
from app.routers import (
    account_chart, adjustments, archive, report_export, report_line_mapping, report_mapping,
    report_related_workpapers, reports, wp_report_analysis,
)
from app.services import report_line_mapping_service as rlm_svc
from app.services.adjustment_service import AdjustmentService
from app.services.event_bus import event_bus
from app.services.prerequisite_checker import PrerequisiteChecker
from app.services.report_engine import ReportEngine
from app.services.report_excel_exporter import ReportExcelExporter
from app.services.report_mapping_service import ReportMappingService
from app.services.trial_balance_full_view_service import TrialBalanceFullViewService
from tests.authz_world import TARGET_PROJECT_ID, AuthzWorld, production_registrations, sqlite_world

PID = TARGET_PROJECT_ID
MID = uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e31")
GATE = "app.deps.assert_project_permission"
DENIED = {"detail": "权限不足"}
_PATH_VALUES = {"project_id": PID, "year": 2025, "report_type": "balance_sheet", "row_code": "BS-001", "mapping_id": MID}

# (模块, 端点函数, 级别, 请求体) —— 本 spec 改为项目级的 24 个端点（R1.1）；路径取自路由本身
_LEVELS = [
    (reports, "get_report", "readonly", None),
    (reports, "drilldown_report_row", "readonly", None),
    (reports, "export_report_excel", "readonly", None),
    (report_line_mapping, "ai_suggest", "edit", None),
    (report_line_mapping, "fix_bad_debt", "edit", None),
    (report_line_mapping, "get_mappings", "readonly", None),
    (report_line_mapping, "update_mapping", "edit", {}),
    (report_line_mapping, "confirm_mapping", "edit", None),
    (report_line_mapping, "batch_confirm", "edit", {"mapping_ids": []}),
    (report_line_mapping, "delete_mapping", "edit", None),
    (report_line_mapping, "create_manual_mapping", "edit", {}),
    (report_line_mapping, "reference_copy", "edit", {"source_company_code": "某企业"}),
    (report_line_mapping, "get_report_lines", "readonly", None),
    (report_related_workpapers, "get_related_workpapers", "readonly", None),
    (report_export, "export_excel", "readonly", {"year": 2025}),
    (report_mapping, "get_preset_mapping", "readonly", None),
    (report_mapping, "get_saved_mapping", "readonly", None),
    (report_mapping, "save_mapping", "edit", {}),
    (wp_report_analysis, "get_full_tb", "readonly", None),
    (wp_report_analysis, "check_tb_balance", "readonly", None),
    (wp_report_analysis, "get_opening_reconcile", "readonly", None),
    (wp_report_analysis, "get_bs_trend", "readonly", None),
    (wp_report_analysis, "get_pl_trend", "readonly", None),
    (wp_report_analysis, "get_financial_ratios", "readonly", None),
]
_IDS = [f"{m.__name__.rsplit('.', 1)[-1]}.{fn}" for m, fn, *_ in _LEVELS]
_MODULES = sorted({m for m, *_ in _LEVELS}, key=lambda m: m.__name__)


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


def _routers(module) -> list:
    return [v for v in vars(module).values() if type(v).__name__ == "APIRouter"]


def _route(module, fn: str):
    found = [(r, route) for r in _routers(module) for route in r.routes if route.endpoint.__name__ == fn]
    assert len(found) == 1, f"{module.__name__}.{fn} 找到 {len(found)} 个路由"
    return found[0]


def _project_levels(dependant) -> list[str]:
    """依赖树里 ``require_project_access`` 闭包的级别（从闭包变量 ``min_permission`` 取）。"""
    out: list[str] = []
    for sub in dependant.dependencies:
        code = getattr(sub.call, "__code__", None)
        if code is not None and sub.call.__qualname__ == "require_project_access.<locals>.dependency":
            cells = dict(zip(code.co_freevars, (c.cell_contents for c in sub.call.__closure__)))
            out.append(cells["min_permission"])
        out.extend(_project_levels(sub))
    return out


def _request(module, fn: str):
    router, route = _route(module, fn)
    (method,) = route.methods
    return router, method, route.path.format(**{k: v for k, v in _PATH_VALUES.items() if "{" + k + "}" in route.path})


async def _send(world: AuthzWorld, router, user, method: str, path: str, body=None, **kwargs):
    async with world.client(router, user=user) as client:
        response = await client.request(method, path, **({"json": body} if body is not None else {}), **kwargs)
    return response, client


# ── 定级表（静态，钉住每个端点的级别） ─────────────────────────────────────────

@pytest.mark.parametrize(("module", "fn", "level", "_body"), _LEVELS, ids=_IDS)
def test_endpoint_level_matches_table(module, fn, level, _body) -> None:
    _router, route = _route(module, fn)
    assert _project_levels(route.dependant) == [level], f"{fn} 的项目级门禁与定级表不符"


def test_every_route_in_report_domain_is_project_level() -> None:
    """六个模块里不留「仅登录」的端点：每个路由都挂 require_project_access；生成报表（项目在请求体）在函数体里校验。"""
    loose = []
    for module in _MODULES:
        for router in _routers(module):
            for route in router.routes:
                if not _project_levels(route.dependant) and route.endpoint is not reports.generate_reports:
                    loose.append(f"{module.__name__}.{route.endpoint.__name__}")
    assert not loose, f"仍只校验登录：{loose}"


def test_routers_registered_without_extra_dependencies() -> None:
    """前提：本文件挂的 router 生产注册不附加依赖（附加门禁会先于端点门禁执行，改变本文件的结论）。"""
    mounted = {id(r) for m in [*_MODULES, account_chart, adjustments, archive] for r in _routers(m)}
    extra = [(r.prefix, kw.get("dependencies")) for r, kw in production_registrations()
             if id(r) in mounted and kw.get("dependencies")]
    assert not extra, extra


# ── 非成员 / 只读成员（真发请求，生产门禁作出判定） ─────────────────────────────

@pytest.mark.parametrize(("module", "fn", "level", "body"), _LEVELS, ids=_IDS)
async def test_non_member_is_denied(world, module, fn, level, body) -> None:
    identity = await world.non_member()
    router, method, path = _request(module, fn)
    resp, client = await _send(world, router, identity.user, method, path, body)
    assert (resp.status_code, resp.json()) == (403, DENIED), f"{fn}：非成员未被拦 {resp.status_code} {resp.text[:200]}"
    client.assert_passed(GATE, times=1)


@pytest.mark.parametrize(("module", "fn", "level", "body"), [c for c in _LEVELS if c[2] == "edit"],
                         ids=[i for i, c in zip(_IDS, _LEVELS) if c[2] == "edit"])
async def test_readonly_member_is_denied_on_edit_endpoints(world, module, fn, level, body) -> None:
    identity = await world.readonly_member()
    router, method, path = _request(module, fn)
    resp, client = await _send(world, router, identity.user, method, path, body)
    assert (resp.status_code, resp.json()) == (403, DENIED), f"{fn}：只读成员未被拦 {resp.status_code}"
    client.assert_passed(GATE, times=1)


# 每个模块挑代表端点：放行的人能用，业务恰执行 1 次（桩名 → 所属对象、属性、返回值）
_ALLOWED = [
    ("drilldown", reports, "drilldown_report_row", "readonly", None, (ReportEngine, "drilldown", {"row_code": "BS-001"}),
     {"row_code": "BS-001"}),
    ("mappings", report_line_mapping, "get_mappings", "readonly", None, (rlm_svc, "get_mappings", []), []),
    ("batch_confirm", report_line_mapping, "batch_confirm", "edit", {"mapping_ids": []},
     (rlm_svc, "batch_confirm", 0), {"confirmed_count": 0}),
    ("saved_mapping", report_mapping, "get_saved_mapping", "readonly", None,
     (ReportMappingService, "get_saved_mapping", {"rules": [1]}), {"rules": [1]}),
    ("save_mapping", report_mapping, "save_mapping", "edit", {"rules": []},
     (ReportMappingService, "save_mapping", {"saved": True}), {"saved": True}),
    ("full_tb", wp_report_analysis, "get_full_tb", "readonly", None, (TrialBalanceFullViewService, "get_full_view", []), []),
]


@pytest.mark.parametrize(("name", "module", "fn", "level", "body", "stub", "expected"), _ALLOWED, ids=[c[0] for c in _ALLOWED])
async def test_allowed_member_reaches_business(world, name, module, fn, level, body, stub, expected) -> None:
    owner, attr, value = stub
    business = world.stub(owner, attr, returns=value)
    identity = await (world.readonly_member() if level == "readonly" else world.edit_member())
    router, method, path = _request(module, fn)
    resp, client = await _send(world, router, identity.user, method, path, body)
    assert (resp.status_code, resp.json()) == (200, expected), resp.text[:300]
    assert business.count == 1
    client.assert_passed(GATE, times=1)


async def test_report_excel_export_reaches_exporter_for_readonly_member(world) -> None:
    exporter = world.stub(ReportExcelExporter, "export", returns=io.BytesIO(b"xlsx"))
    identity = await world.readonly_member()
    router, method, path = _request(report_export, "export_excel")
    resp, client = await _send(world, router, identity.user, method, path, {"year": 2025})
    assert resp.status_code == 200 and resp.content == b"xlsx"
    assert exporter.count == 1
    client.assert_passed(GATE, times=1)


# ── 生成报表：项目在请求体（R1.2） ──────────────────────────────────────────────

def _stub_generate(world: AuthzWorld):
    world.stub(PrerequisiteChecker, "check", returns={"ok": True})
    world.stub(reports, "_resolve_applicable_standard", returns="soe_standalone")
    world.stub(event_bus, "publish_immediate", returns=None)
    return world.stub(ReportEngine, "generate_all_reports", returns={"balance_sheet": []})


@pytest.mark.parametrize("member_level", [None, "readonly", "review"])
async def test_generate_requires_edit_member_of_body_project(world, member_level) -> None:
    """系统角色 partner（矩阵有 report:edit）：不是请求体项目的 edit 级成员 ⇒ 403，不生成。"""
    generate = _stub_generate(world)
    if member_level is None:
        identity = await world.non_member_with_other_project(global_role=UserRole.partner)
    else:
        identity = await world.member(member_level, "partner", global_role=UserRole.partner)
    resp, client = await _send(world, reports.router, identity.user, "POST", "/api/reports/generate",
                               {"project_id": str(PID), "year": 2025})
    assert (resp.status_code, resp.json()) == (403, DENIED)
    assert generate.count == 0
    client.assert_passed(GATE, times=1)


async def test_generate_passes_for_edit_member(world) -> None:
    generate = _stub_generate(world)
    identity = await world.member("edit", "partner", global_role=UserRole.partner)
    resp, client = await _send(world, reports.router, identity.user, "POST", "/api/reports/generate",
                               {"project_id": str(PID), "year": 2025})
    assert resp.status_code == 200 and resp.json()["report_types"] == ["balance_sheet"], resp.text[:300]
    assert generate.count == 1
    client.assert_passed(GATE, times=1)


# ── 期初核对的上年项目（R2.2） ──────────────────────────────────────────────────

async def test_opening_reconcile_checks_prior_project(world) -> None:
    reconcile = world.stub(TrialBalanceFullViewService, "reconcile_opening_balance", returns={"reconciled": True})
    identity = await world.readonly_member()
    prior = await world.project(name="【测试】上年项目")
    path = f"/api/workpapers/{PID}/2025/opening-reconcile"

    resp, client = await _send(world, wp_report_analysis.router, identity.user, "GET", path,
                               params={"prior_project_id": str(prior.id)})
    assert (resp.status_code, resp.json()) == (403, DENIED), "上年项目不是成员也能读"
    assert reconcile.count == 0
    client.assert_passed(GATE, times=2)

    await world.member("readonly", "readonly", project=prior, user=identity.user)
    world.rls_calls.clear()
    resp, client = await _send(world, wp_report_analysis.router, identity.user, "GET", path,
                               params={"prior_project_id": str(prior.id)})
    assert (resp.status_code, resp.json()) == (200, {"reconciled": True})
    assert reconcile.calls[-1][0] == (PID, 2025, prior.id)
    assert world.rls_calls == [str(PID), str(prior.id), str(PID)], "读完上年项目后 RLS 上下文没设回本项目"


# ── 参照复制的来源项目（R2.3 / R2.4） ───────────────────────────────────────────

_RLM_COPY = f"/api/projects/{PID}/report-line-mapping/reference-copy"


async def test_reference_copy_by_project_requires_readable_source(world) -> None:
    copy = world.stub(rlm_svc, "reference_copy_from_project", returns={"copied_count": 3, "source_found": True})
    identity = await world.edit_member()
    source = await world.project(name="【测试】来源项目")

    resp, client = await _send(world, report_line_mapping.router, identity.user, "POST", _RLM_COPY,
                               {"source_project_id": str(source.id)})
    assert (resp.status_code, resp.json()) == (403, DENIED)
    assert copy.count == 0
    client.assert_passed(GATE, times=2)

    await world.member("readonly", "readonly", project=source, user=identity.user)
    world.rls_calls.clear()
    resp, _client = await _send(world, report_line_mapping.router, identity.user, "POST", _RLM_COPY,
                                {"source_project_id": str(source.id)})
    assert resp.status_code == 200 and resp.json()["copied_count"] == 3
    assert copy.calls[-1][0][:2] == (source.id, PID)
    assert world.rls_calls[-1] == str(PID), "复制写本项目前 RLS 上下文没设回本项目"


@pytest.mark.parametrize(("body", "status"), [
    ({"source_project_id": str(PID)}, 400),
    ({}, 422),
    ({"source_project_id": str(uuid.uuid4()), "source_company_code": "某企业"}, 422),
], ids=["self", "neither", "both"])
async def test_reference_copy_rejects_bad_source(world, body, status) -> None:
    identity = await world.edit_member()
    resp, _client = await _send(world, report_line_mapping.router, identity.user, "POST", _RLM_COPY, body)
    assert resp.status_code == status, resp.text[:200]


@pytest.mark.parametrize("who", ["edit_member", "admin_non_member"])
async def test_reference_copy_by_name_limits_candidates_to_readable(world, who) -> None:
    copy = world.stub(rlm_svc, "reference_copy", returns={"copied_count": 0, "source_found": False})
    identity = await world.identity(who)
    resp, _client = await _send(world, report_line_mapping.router, identity.user, "POST", _RLM_COPY,
                                {"source_company_code": "某企业"})
    assert resp.status_code == 200 and resp.json()["source_found"] is False
    expected = None if who == "admin_non_member" else {PID}
    assert copy.calls[-1][1] == {"readable_project_ids": expected}


async def _with_column_mappings(world: AuthzWorld, name: str):
    project = await world.project(name=name)
    project.wizard_state = {"column_mappings": {"balance": {"A": "account_code"}}}
    await world.db.flush()
    return project


async def test_column_mapping_reference_projects_lists_only_readable(world) -> None:
    identity = await world.edit_member()
    mine = await _with_column_mappings(world, "【测试】可读来源")
    await world.member("readonly", "readonly", project=mine, user=identity.user)
    others = await _with_column_mappings(world, "【测试】不可读来源")
    path = f"/api/projects/{PID}/column-mappings/reference-projects"

    resp, client = await _send(world, account_chart.router, identity.user, "GET", path)
    assert resp.status_code == 200 and [p["id"] for p in resp.json()] == [str(mine.id)]
    client.assert_passed(GATE, times=1)

    admin = await world.admin_non_member()
    resp, _client = await _send(world, account_chart.router, admin.user, "GET", path)
    assert {p["id"] for p in resp.json()} == {str(mine.id), str(others.id)}


async def _target_with_wizard_state(world: AuthzWorld) -> None:
    """目标项目带一份向导状态（向导建的项目都有）：原地改 JSONB 不落库的缺陷只在这种项目上显出来。"""
    world.target.wizard_state = {"steps": {"basic_info": {"data": {"client_name": "权限世界"}}}}
    await world.db.commit()


async def test_column_mapping_reference_copy_requires_readable_source(world) -> None:
    await _target_with_wizard_state(world)
    identity = await world.edit_member()
    source = await _with_column_mappings(world, "【测试】列映射来源")
    path = f"/api/projects/{PID}/column-mappings/reference-copy"

    resp, client = await _send(world, account_chart.router, identity.user, "POST", path, {"source_project_id": str(source.id)})
    assert (resp.status_code, resp.json()) == (403, DENIED)
    client.assert_passed(GATE, times=2)
    await world.db.refresh(world.target)
    assert "column_mappings" not in world.target.wizard_state

    await world.member("readonly", "readonly", project=source, user=identity.user)
    world.rls_calls.clear()
    resp, _client = await _send(world, account_chart.router, identity.user, "POST", path, {"source_project_id": str(source.id)})
    assert resp.status_code == 200 and resp.json()["mapping_count"] == 1
    assert world.rls_calls[-1] == str(PID), "复制写本项目前 RLS 上下文没设回本项目"
    await world.db.refresh(world.target)
    assert world.target.wizard_state["column_mappings"] == {"balance": {"A": "account_code"}}, "复制结果没落库"
    assert world.target.wizard_state["steps"] == {"basic_info": {"data": {"client_name": "权限世界"}}}

    for bad, status in ((str(PID), 400), ("不是 id", 422)):
        resp, _client = await _send(world, account_chart.router, identity.user, "POST", path, {"source_project_id": bad})
        assert resp.status_code == status, bad


async def test_save_column_mapping_persists_on_project_with_wizard_state(world) -> None:
    """同文件同型缺陷：保存列映射原地改 JSONB 再赋回同一对象 ⇒ 不发 UPDATE，读回仍是旧的。"""
    await _target_with_wizard_state(world)
    identity = await world.edit_member()
    body = {"file_type": "balance", "sheet_name": "Sheet1", "mapping": {"A": "account_code"}}
    resp, _client = await _send(world, account_chart.router, identity.user, "POST",
                                f"/api/projects/{PID}/column-mappings", body)
    assert resp.status_code == 200 and resp.json()["key"] == "balance:Sheet1"
    await world.db.refresh(world.target)
    assert world.target.wizard_state["column_mappings"] == {"balance:Sheet1": {"A": "account_code"}}, "保存结果没落库"


# ── require_operation：项目在路径时校验成员、已归档只读（R3） ──────────────────────

_ADJ_BODY = {"adjustment_type": "aje", "year": 2025, "line_items": [
    {"standard_account_code": "1001", "debit_amount": "100"},
    {"standard_account_code": "6001", "credit_amount": "100"}]}
_OPERATION_ENDPOINTS = [
    ("建调整分录", adjustments.router, f"/api/projects/{PID}/adjustments", _ADJ_BODY),
    ("底稿分录同步", adjustments.router, f"/api/projects/{PID}/adjustments/sync-from-workpaper", {}),
    ("归档编排", archive.router, f"/api/projects/{PID}/archive/orchestrate", {"scope": "final"}),
]


@pytest.mark.parametrize(("name", "router", "path", "body"), _OPERATION_ENDPOINTS, ids=[c[0] for c in _OPERATION_ENDPOINTS])
async def test_operation_endpoint_denies_non_member_partner(world, name, router, path, body) -> None:
    """系统角色 partner 的矩阵是全集：原先对任何项目放行，现在不是本项目成员即 403。"""
    identity = await world.non_member_with_other_project(global_role=UserRole.partner)
    resp, client = await _send(world, router, identity.user, "POST", path, body)
    assert (resp.status_code, resp.json()) == (403, DENIED), f"{name}：{resp.status_code} {resp.text[:200]}"
    client.assert_passed(GATE, times=1)


async def test_operation_endpoint_passes_member_and_locks_archived(world) -> None:
    create = world.stub(AdjustmentService, "create_entry", returns=SimpleNamespace(model_dump=lambda: {"created": True}))
    member = await world.member("edit", "manager", global_role=UserRole.manager)
    path = f"/api/projects/{PID}/adjustments"
    resp, client = await _send(world, adjustments.router, member.user, "POST", path, _ADJ_BODY)
    assert (resp.status_code, resp.json()) == (200, {"created": True}), resp.text[:300]
    assert create.count == 1
    client.assert_passed(GATE, times=1)

    await world.archived_edit_member()  # 目标项目置为已归档
    resp, client = await _send(world, adjustments.router, member.user, "POST", path, _ADJ_BODY)
    assert resp.status_code == 423 and resp.json()["detail"]["error_code"] == "PROJECT_ARCHIVED"
    assert create.count == 1
    client.assert_passed(GATE, times=0)  # 归档守卫先于矩阵与成员判定


# ── 候选口径与门禁同一（R2.3） ──────────────────────────────────────────────────

@pytest.mark.parametrize("who", [
    "edit_member", "review_member", "readonly_member", "non_member", "admin_non_member", "partner_non_member"])
async def test_readable_project_ids_agrees_with_readonly_gate(world, who) -> None:
    """含系统角色 partner 的非成员：``get_visible_project_ids`` 给 partner 全部项目，门禁不给 —— 候选须跟门禁走。"""
    if who == "partner_non_member":
        identity = await world.non_member_with_other_project(global_role=UserRole.partner)
    else:
        identity = await world.identity(who)
    readable = await deps.readable_project_ids(world.db, identity.user)
    try:
        await deps.assert_project_permission(world.db, identity.user, PID, "readonly")
        gate_allows = True
    except Exception:  # noqa: BLE001 —— 门禁拒绝即 HTTPException(403)
        gate_allows = False
    assert (readable is None or PID in readable) is gate_allows
    assert (readable is None) is (who == "admin_non_member")


async def test_readable_project_ids_skips_deleted_membership(world) -> None:
    identity = await world.readonly_member()
    identity.member.is_deleted = True
    await world.db.flush()
    assert PID not in await deps.readable_project_ids(world.db, identity.user)
