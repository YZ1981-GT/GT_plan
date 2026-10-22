"""公式域 7 个越权端点的端点级鉴权（spec formula-governance-coverage-closure R1.1~R1.6）。

修复前全都只校验登录：公式调试按请求体项目原样回显试算表 / 报表数据；底稿用户公式按 wp_id 读写任意项目；
公式导入任何登录用户都能改写仓库里的 seed 文件；报表「审核」读任意项目的审核金额。

做法同 test_deliverable_generation_membership_auth（memory ㉕）：请求经权限世界（tests/authz_world.py）真发，
身份是世界里的真实用户与成员行，判定由生产门禁作出，只替换当前用户与会话；业务层打桩计数 ——
被拦下的请求一次业务调用都不能有。
"""
from __future__ import annotations

import io
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.schema import CreateTable

import app.routers.formula_debug as formula_debug
import app.routers.formula_import_export as fie
import app.routers.reports as reports
import app.routers.wp_user_formulas as wuf
import app.services.formula_settings.custom_presets as custom_presets
import app.services.formula_settings.publish as fs_publish
import app.services.report_audit_checks as report_audit_checks
from app.models.base import UserRole
from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex
from app.services.formula_engine import FormulaContext
from app.services.formula_management import preset_library
from tests.authz_world import OTHER_PROJECT_ID, TARGET_PROJECT_ID, WORLD_TABLE_NAMES, sqlite_world

PID = TARGET_PROJECT_ID
WP = uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e10")
_EXTRA = (WpIndex.__table__, WorkingPaper.__table__, WpFormula.__table__)


def _create_extra_tables(session) -> None:
    conn = session.connection()
    known = WORLD_TABLE_NAMES | {t.name for t in _EXTRA}
    for table in _EXTRA:
        fks = [fk for fk in table.foreign_key_constraints
               if {e.target_fullname.split(".")[-2] for e in fk.elements} <= known]
        conn.execute(CreateTable(table, include_foreign_key_constraints=fks))


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        await w.db.run_sync(_create_extra_tables)
        idx = WpIndex(id=uuid.uuid4(), project_id=PID, wp_code="E1", wp_name="货币资金")
        w.db.add(idx)
        await w.db.flush()
        w.db.add(WorkingPaper(id=WP, project_id=PID, wp_index_id=idx.id, file_path="x.xlsx", source_type="template"))
        await w.db.flush()
        yield w


async def _send(world, router, user, method: str, path: str, **kwargs):
    async with world.client(router, user=user) as client:
        return await client.request(method.upper(), path, **kwargs)


# ── 公式调试（R1.1） ───────────────────────────────────────────────────────────

_DEBUG = {"formula": "TB('1001','期末余额')", "project_id": str(PID), "year": 2025, "scope": "report"}


@pytest.mark.parametrize(("who", "status", "calls"), [
    ("non_member", 403, 0), ("readonly_member", 200, 1), ("admin_non_member", 200, 1)])
async def test_debug_checks_body_project_and_denied_request_reads_nothing(world, who, status, calls):
    stub = world.stub(formula_debug, "_build_context", returns=FormulaContext())
    identity = await world.identity(who)
    resp = await _send(world, formula_debug.router, identity.user, "post", "/api/formula/debug", json=_DEBUG)
    assert resp.status_code == status, resp.text
    assert stub.count == calls  # 被拦下的请求一次取数都没有


# ── 底稿用户公式（R1.2 / R1.3） ────────────────────────────────────────────────
#
# 🔴 更正评估：这组端点在生产经 router_registry 统一挂 router 级 ``dedicated_wp_gate``（可见性隔离，非委派 /
# 跨项目一律 404），并非「只校验登录」。处理函数里补的 ``authorize_wp_read / authorize_wp_edit`` 是第二道
# （项目成员 + 编辑级），这里分两层测：①生产注册确实挂了可见性门；②处理函数自身的项目级判定（不挂可见性门，
# 单测这一层）。真缺口只有 validate-formula：可见性门只看路径上的底稿，预览却按**请求体**的 project_id 取数。

_UF = f"/api/workpapers/{WP}/user-formulas"


def test_production_registration_attaches_visibility_gate_to_user_formula_router():
    from app.routers._wp_gate import dedicated_wp_gate
    from tests.authz_world import production_registrations

    regs = [kw for router, kw in production_registrations() if router is wuf.router]
    assert regs, "wp_user_formulas 路由未注册"
    deps = [getattr(d, "dependency", None) for kw in regs for d in (kw.get("dependencies") or [])]
    assert dedicated_wp_gate in deps, "底稿用户公式路由须挂 router 级可见性门 dedicated_wp_gate"


def _handler_app():
    from fastapi import FastAPI

    api = FastAPI()
    api.include_router(wuf.router)  # 只测处理函数这一层（不挂可见性门）
    return api


async def _send_handler(world, user, method: str, path: str, **kwargs):
    async with world.client_for_app(_handler_app(), user=user) as client:
        return await client.request(method.upper(), path, **kwargs)


@pytest.mark.parametrize(("who", "status", "calls"), [
    ("non_member", 403, 0), ("readonly_member", 200, 1), ("admin_non_member", 200, 1)])
async def test_user_formula_list_handler_checks_membership(world, who, status, calls):
    stub = world.stub(wuf.wp_formula_service, "list_by_wp", returns=[])
    identity = await world.identity(who)
    resp = await _send_handler(world, identity.user, "get", _UF)
    assert resp.status_code == status, resp.text
    assert stub.count == calls


@pytest.mark.parametrize(("who", "status"), [
    ("non_member", 403), ("readonly_member", 403), ("edit_member", 200), ("admin_non_member", 200)])
async def test_user_formula_write_handlers_require_edit(world, who, status):
    identity = await world.identity(who)
    put = await _send_handler(world, identity.user, "put", _UF, json={"formulas": {}})
    delete = await _send_handler(world, identity.user, "delete", f"{_UF}/Sheet1!A1")
    assert (put.status_code, delete.status_code) == (status, status), (put.text, delete.text)


async def test_validate_formula_rejects_foreign_project_in_body(world):
    member = await world.readonly_member()
    path = f"/api/workpapers/{WP}/validate-formula"
    own = await _send_handler(world, member.user, "post", path, json={"formula": "=TB('1001','期末余额')"})
    foreign = await _send_handler(world, member.user, "post", path, json={
        "formula": "=TB('1001','期末余额')", "project_id": str(OTHER_PROJECT_ID), "year": 2025, "preview": True})
    outsider = await world.non_member()
    denied = await _send_handler(world, outsider.user, "post", path, json={"formula": "=TB('1001','期末余额')"})
    assert own.status_code == 200 and own.json()["valid"] is True, own.text
    assert foreign.status_code == 403, "拿本项目底稿配别的项目 id 预览，必须拒绝"
    assert denied.status_code == 403


async def test_validate_formula_preview_uses_workpaper_project(world, monkeypatch):
    seen: list[uuid.UUID] = []

    async def _resolve(_db, project_id, _year, _ftype, _args):
        seen.append(project_id)
        return 1

    monkeypatch.setattr(wuf, "resolve_extended_formula", _resolve)
    member = await world.readonly_member()
    resp = await _send_handler(world, member.user, "post", f"/api/workpapers/{WP}/validate-formula",
                               json={"formula": "=WP('E1','审定表E1-1','B5')", "year": 2025, "preview": True})
    assert resp.status_code == 200, resp.text
    assert seen == [PID], f"预览取数一律按底稿所属项目：{resp.json()}"


# ── 公式导入（R1.4 / R1.5） ───────────────────────────────────────────────────

_IMPORT = "/api/formula-management/import-export/import-data"
_ENTRY = preset_library.PresetEntry(page_key="report:balance_sheet", target_cell="BS-002",
                                    expression="TB('1001','期末余额')", formula_type="auto_calc", refs=[],
                                    source="seed", description="测试", variant=None)


def _xlsx():
    return {"file": ("公式.xlsx", io.BytesIO(b"PK\x03\x04 fake"), "application/octet-stream")}


def _stub_import(world):
    parsed = SimpleNamespace(imported=[_ENTRY], skipped=[], to_dict=lambda: {"imported_count": 1, "skipped_count": 0})
    return {
        "parse": world.stub(fie, "parse_import_rows", returns=parsed),
        "upsert": world.stub(custom_presets, "upsert", returns={"inserted": 1, "updated": 0, "total": 1}),
        "refresh": world.stub(custom_presets, "refresh_cache", returns=1),
        "candidate": world.stub(custom_presets, "submit_candidate", returns=SimpleNamespace(id=uuid.uuid4())),
        "publish_to_dict": world.stub(fs_publish, "publish_to_dict", returns={"id": "c"}, awaitable=False),
    }


def _seed_mtime() -> int:
    return preset_library.SEED_PATH.stat().st_mtime_ns if preset_library.SEED_PATH.exists() else -1


async def test_import_persist_needs_preset_writer_role_and_never_touches_repo_seed(world):
    stubs = _stub_import(world)
    before = _seed_mtime()
    auditor = await world.user(UserRole.auditor)
    denied = await _send(world, fie.router, auditor, "post", _IMPORT, files=_xlsx())
    assert denied.status_code == 403, denied.text
    assert stubs["parse"].count == 0, "无权入库的请求连文件都不解析"

    partner = await world.user(UserRole.partner)
    cand = await _send(world, fie.router, partner, "post", _IMPORT, files=_xlsx())
    assert cand.status_code == 200 and cand.json()["pending_review"] is True, cand.text
    assert (stubs["candidate"].count, stubs["upsert"].count) == (1, 0), "合伙人入库 = 提交全局候选"

    admin = await world.user(UserRole.admin)
    done = await _send(world, fie.router, admin, "post", _IMPORT, files=_xlsx())
    assert done.status_code == 200 and done.json()["pending_review"] is False, done.text
    assert (stubs["upsert"].count, stubs["refresh"].count) == (1, 1), "管理员入库 = 写数据库自定义预设"
    assert _seed_mtime() == before, "在线导入不得改写仓库里的 seed 文件"


async def test_import_with_project_context_requires_membership(world):
    stubs = _stub_import(world)
    outsider = await world.non_member()
    url = f"{_IMPORT}?persist=false&project_id={PID}"
    denied = await _send(world, fie.router, outsider.user, "post", url, files=_xlsx())
    member = await world.readonly_member()
    ok = await _send(world, fie.router, member.user, "post", url, files=_xlsx())
    assert (denied.status_code, ok.status_code) == (403, 200), (denied.text, ok.text)
    assert stubs["parse"].count == 1 and stubs["upsert"].count == 0 and stubs["candidate"].count == 0


# ── 报表「审核」（R1.6） ──────────────────────────────────────────────────────

_AUDIT = f"/api/reports/{PID}/2025/consistency-check"


@pytest.mark.parametrize(("who", "status", "calls"), [
    ("non_member", 403, 0), ("readonly_member", 200, 1), ("admin_non_member", 200, 1)])
async def test_report_audit_requires_membership(world, who, status, calls):
    world.stub(reports, "_resolve_applicable_standard", returns="soe_standalone")
    stub = world.stub(report_audit_checks, "run_report_audit", returns=[])
    identity = await world.identity(who)
    resp = await _send(world, reports.router, identity.user, "get", _AUDIT)
    assert resp.status_code == status, resp.text
    assert stub.count == calls


async def test_report_audit_with_nothing_to_check_is_no_result_not_all_passed(world):
    world.stub(reports, "_resolve_applicable_standard", returns="soe_standalone")
    world.stub(report_audit_checks, "run_report_audit", returns=[])
    member = await world.readonly_member()
    body = (await _send(world, reports.router, member.user, "get", _AUDIT)).json()
    assert (body["no_result"], body["consistent"], body["total"]) == (True, None, 0), body


# ── 第三维：项目在请求体 / 查询参数里的公式端点（R1.7） ──────────────────────────
#
# 角色门（require_role）只保证「是合伙人」，不含项目维度：修复前任一合伙人都能刷新 / 回滚 / 枚举任意项目，
# 新增自定义预设时也能拿任意项目做引用解析。

import app.routers.draft_refresh as draft_refresh  # noqa: E402
import app.routers.refresh_scopes as refresh_scopes  # noqa: E402
from app.models.workpaper_models import DraftRefreshAudit  # noqa: E402

_RUN = uuid.UUID("5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e20")


async def _partner(world, level: str | None):
    """全局角色合伙人；``level`` 给出时在目标项目建一条（partner, level）成员行。"""
    if level is None:
        return await world.user(UserRole.partner)
    return (await world.member(level, "partner", global_role=UserRole.partner)).user


def _blocked_refresh_service():
    """四表库不完整的刷新服务桩：门禁放行后端点停在 precheck 422，不进编排（零写入）。"""
    blocked = SimpleNamespace(can_refresh=False, to_dict=lambda: {"can_refresh": False, "blocking": [], "warnings": []})

    async def _precheck(_db, *, project_id, year):
        return blocked

    return SimpleNamespace(precheck=_precheck)


@pytest.mark.parametrize(("who", "status", "calls"), [
    ("non_member", 403, 0), ("readonly", 403, 0), ("edit", 422, 1)])
async def test_draft_refresh_requires_edit_membership_of_body_project(world, who, status, calls):
    stub = world.stub(draft_refresh, "DraftRefreshService", returns=_blocked_refresh_service(), awaitable=False)
    user = await _partner(world, None if who == "non_member" else who)
    resp = await _send(world, draft_refresh.router, user, "post", "/api/workpapers/draft-refresh",
                       json={"project_id": str(PID), "year": 2025, "scopes": ["report"]})
    assert resp.status_code == status, resp.text
    assert stub.count == calls  # 被拦下的请求连刷新服务都不构造


async def test_draft_refresh_admin_needs_no_membership(world):
    world.stub(draft_refresh, "DraftRefreshService", returns=_blocked_refresh_service(), awaitable=False)
    admin = await world.admin_non_member()
    resp = await _send(world, draft_refresh.router, admin.user, "post", "/api/workpapers/draft-refresh",
                       json={"project_id": str(PID), "year": 2025, "scopes": ["report"]})
    assert resp.status_code == 422, resp.text


def _create_refresh_audit_table(session) -> None:
    session.connection().execute(CreateTable(DraftRefreshAudit.__table__))


@pytest.mark.parametrize(("who", "status"), [("non_member", 403), ("readonly", 403), ("edit", 409)])
async def test_draft_refresh_rollback_checks_project_of_the_run(world, monkeypatch, who, status):
    from app.services.formula_runtime.contracts import ExecutionResult
    from app.services.formula_runtime.coordinator import FormulaRuntimeCoordinator

    await world.db.run_sync(_create_refresh_audit_table)
    world.db.add(DraftRefreshAudit(id=_RUN, project_id=PID, year=2025, operator_id=uuid.uuid4(),
                                   operator_role="partner", scope="report", tb_snapshot_hash="h",
                                   result_status="success", detail={}))
    await world.db.flush()

    async def _rollback(_db, *, run_id, adapters, operator):
        return ExecutionResult(run_id=run_id, status="conflict", conflicts=[{"target": "report:BS-1"}])

    service = world.stub(draft_refresh, "DraftRefreshService", returns=SimpleNamespace(rollback_refresh=_rollback),
                         awaitable=False)
    monkeypatch.setattr(FormulaRuntimeCoordinator, "build_adapter_map", lambda self, domains: {})
    user = await _partner(world, None if who == "non_member" else who)
    missing = await _send(world, draft_refresh.router, user, "post",
                          f"/api/workpapers/draft-refresh/{uuid.uuid4()}/rollback")
    assert missing.status_code == 404, missing.text

    # 放在最后：冲突分支会回滚请求会话（即本世界的会话）
    resp = await _send(world, draft_refresh.router, user, "post", f"/api/workpapers/draft-refresh/{_RUN}/rollback")
    assert resp.status_code == status, resp.text
    assert service.count == (1 if status == 409 else 0), "门禁按运行记录反查的项目判 edit，先于回滚"


@pytest.mark.parametrize(("who", "status", "calls"), [("non_member", 403, 0), ("readonly", 200, 1)])
async def test_refresh_scopes_require_membership_of_query_project(world, who, status, calls):
    async def _discover(*, project_id, year):
        return []

    stub = world.stub(refresh_scopes, "RefreshScopeDiscovery", returns=SimpleNamespace(discover=_discover),
                      awaitable=False)
    user = await _partner(world, None if who == "non_member" else who)
    resp = await _send(world, refresh_scopes.router, user, "get",
                       f"/api/workpapers/refresh-scopes?project_id={PID}&year=2025")
    assert resp.status_code == status, resp.text
    assert stub.count == calls


_CUSTOM = "/api/formula-management/presets/custom"
_PRESET = {"page_key": "report:balance_sheet", "target_cell": "BS-002",
           "expression": "TB('1001','期末余额')", "formula_type": "auto_calc"}


async def test_custom_preset_project_context_requires_membership(world):
    refs = world.stub(fie, "validate_single_formula_refs", returns=([], []))
    world.stub(custom_presets, "submit_candidate", returns=SimpleNamespace(id=uuid.uuid4()))
    world.stub(fs_publish, "publish_to_dict", returns={"id": "c"}, awaitable=False)
    outsider = await _partner(world, None)
    denied = await _send(world, fie.router, outsider, "post", f"{_CUSTOM}?project_id={PID}", json=_PRESET)
    bad = await _send(world, fie.router, outsider, "post", f"{_CUSTOM}?project_id=not-a-uuid", json=_PRESET)
    assert (denied.status_code, bad.status_code) == (403, 400), (denied.text, bad.text)
    assert refs.count == 0, "被拦下的请求不做引用解析"

    member = await _partner(world, "readonly")
    ok = await _send(world, fie.router, member, "post", f"{_CUSTOM}?project_id={PID}", json=_PRESET)
    no_ctx = await _send(world, fie.router, outsider, "post", _CUSTOM, json=_PRESET)
    assert (ok.status_code, no_ctx.status_code) == (200, 200), (ok.text, no_ctx.text)
    assert ok.json()["pending_review"] is True and refs.count == 2


@pytest.mark.parametrize(("who", "status", "calls"), [
    ("non_member", 403, 0), ("readonly_member", 403, 0), ("edit_member", 200, 1), ("admin_non_member", 200, 1)])
async def test_batch_refresh_requires_edit_membership_of_body_project(world, who, status, calls):
    """批量刷新底稿取数：路径没有 wp_id（router 级可见性门是 no-op），按请求体项目判 edit。"""
    import app.routers.row_name_alignment_router as row_alignment
    import app.services.workpaper_refresh_service as refresh_service

    stub = world.stub(refresh_service, "batch_refresh_workpapers", returns=[])
    identity = await world.identity(who)
    resp = await _send(world, row_alignment.router, identity.user, "post", "/api/workpapers/batch-refresh",
                       json={"project_id": str(PID), "wp_ids": [str(WP)]})
    assert resp.status_code == status, resp.text
    assert stub.count == calls  # 被拦下的请求一次刷新都没有


@pytest.mark.parametrize(("who", "status"), [
    ("manager_non_member", 403), ("manager_readonly", 403), ("manager_edit", 200), ("admin", 200)])
async def test_note_formula_gray_switch_requires_edit_membership(world, who, status):
    """附注公式灰度开关：角色门只保证「经理及以上」，须再是本项目 edit 级成员（admin 放行）。"""
    import app.routers.disclosure_notes as disclosure_notes

    if who == "admin":
        user = (await world.admin_non_member()).user
    elif who == "manager_non_member":
        user = await world.user(UserRole.manager)
    else:
        level = who.removeprefix("manager_")
        user = (await world.member(level, "manager", global_role=UserRole.manager)).user
    resp = await _send(world, disclosure_notes.router, user, "put", f"/api/disclosure-notes/{PID}/formula-gray",
                       json={"enabled": True})
    assert resp.status_code == status, resp.text
    await world.db.refresh(world.target)
    flag = (world.target.wizard_state or {}).get("disclosure_note_formula_enabled")
    assert flag is (True if status == 200 else None), "被拦下的请求不得改开关"
