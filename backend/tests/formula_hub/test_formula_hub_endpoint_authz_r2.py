"""端点权限配方表·第 2 轮补齐（spec formula-hub-integrity-closure 任务 40 / 需求 17.2；design §10.3 其余各行）。

原文件 ``test_formula_hub_endpoint_authz.py`` 只有 5 条配方，design §10.3 表里其余 19 条路由在 ``_UNCHANGED_ROUTES``
里写着「待移入」。本文件按同一套机制补齐（复用原文件的身份、``seed_world``、``_endpoint`` / ``_send``、表状态摘要）：
每个（配方, 身份）一个用例、一个回滚事务里的世界；只替换 ``get_current_user`` / ``get_db``，门禁真实运行；
放行 ⇒ 2xx + 结果断言；拒绝 ⇒ 401 / 403 + 列出的表（行数, 内容摘要）不变（拒绝前表非空）+ 下游桩没被调用。

design 写「既有判定」的路由按现读代码逐身份写入（每条配方的 ``basis`` 写明判定链）。与 design 的出入：
- 删除底稿公式、恢复全局（DELETE overrides）：design 只列拒绝 anon / non_member / ro；现读两处都是项目 ``edit`` 级，
  qc / eqcr（review 级）同样 403 —— 比 design 更严，按现状写入（不是越权）。
- 删除底稿公式另有生产注册时挂上的 router 级 ``dedicated_wp_gate``（含 ``{wp_id}`` 的 router 一律挂，底稿可见性）：
  先于端点判定，看不见该底稿 ⇒ 统一 404（不泄露存在性），拒绝原因记安全审计 outbox。可见的条件是主管委派
  （合伙人 / 经理 / 质控 / EQCR 在本项目的 ``project_assignments``，看全部循环）或本人是编制人（``assigned_to``，
  且底稿循环在团队分配勾选的循环里）。夹具按团队分配的生产形态补齐委派行与编制人；non_member / ro 404，
  qc / eqcr 过了可见性、被 edit 级拒 403。outbox 写入走全局引擎（看不见本用例未提交的用户），桩成记录原因。
- 一键刷新：合伙人角色门（``PARTNER_ROLES`` = partner / signing_partner / admin）+ 项目 edit ⇒ manager 403。
- 导出包：交付件 ``_guard_action(export)`` = 项目 review 级 + 角色矩阵（AUDITOR_PLUS 含 qc；EQCR 委派只读）。
- 回滚、一键刷新、自定义函数：拒绝来自签名上的 ``require_role``（先于项目门禁）⇒ 拒绝时项目门禁不执行（``role_first``）。
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import APIRouter
from httpx import Response
from sqlalchemy import text

from app.models.core import Project
from tests.formula_hub.test_formula_hub_endpoint_authz import (
    A_EDITORS,
    A_MEMBERS,
    IDENTITIES,
    LOGGED_IN,
    Ctx,
    Req,
    World,
    _endpoint,
    _send,
    _tables_state,
    seed_world,
    stub,
)

YEAR = 2025
_PERM = "app.deps.assert_project_permission"
_ACCESS = "app.deps.require_project_access.<locals>.dependency"
_GUARD = "app.routers.deliverable._guard_action"
A_REVIEWERS = frozenset({"auditor", "manager", "qc", "eqcr", "partner"})  # 本项目 review 级及以上成员
_RO_DENIED = {"anon": 401, "non_member": 403}


@dataclass(frozen=True)
class RecipeR2:
    key: str
    method: str
    route: str
    routers: tuple[APIRouter, ...]
    allowed: frozenset[str]
    denied: Mapping[str, int]
    prepare: Callable[[Any, World], Awaitable[Req]]
    basis: str  # 现读判定链（逐身份写入的依据）
    tables: tuple[str, ...] = ()
    check: Callable[[Ctx, str, Response], None] | None = None
    gate: str | None = None
    role_first: bool = False  # 403 来自签名上的角色门（先于项目门禁）
    stub_factory: Callable[[pytest.MonkeyPatch, World], None] | None = None
    state: Callable[[Ctx], Any] | None = None  # 表以外的状态（拒绝时不变）


def _routers(*names: str) -> tuple[APIRouter, ...]:
    import importlib

    out = []
    for name in names:
        module, _, attr = name.partition(":")
        out.append(getattr(importlib.import_module(f"app.routers.{module}"), attr or "router"))
    return tuple(out)


async def _with_year(session, world: World) -> uuid.UUID:
    """目标项目 A 设审计年度 2025（按年度取数 / 年度门的端点需要）。"""
    pid = world.projects["A"]
    await session.execute(sa.update(Project).where(Project.id == pid).values(audit_year=YEAR))
    await session.commit()
    return pid


def _ok_json(_ctx: Ctx, _identity: str, response: Response) -> None:
    response.json()  # 合法 JSON


# ─── 中央公式 API（需求 12） ──────────────────────────────────────────────────


def _tb_request(pid) -> dict:
    return {"project_id": str(pid), "year": YEAR, "formula_type": "TB", "params": {"formula": "TB('1001','期末余额')"}}


async def _prep_execute(session, world: World) -> Req:
    return Req("POST", "/api/formula/execute", json=_tb_request(await _with_year(session, world)))


async def _prep_batch(session, world: World) -> Req:
    pid = await _with_year(session, world)
    return Req("POST", "/api/formula/batch-execute", json=[_tb_request(pid), _tb_request(pid)])


async def _prep_debug(session, world: World) -> Req:
    pid = await _with_year(session, world)
    return Req("POST", "/api/formula/debug", json={"formula": "1+1", "project_id": str(pid), "year": YEAR,
                                                  "scope": "report"})


_CUSTOM_FN = "FHR2AUTHZFN"


async def _prep_custom_fn(_session, _world: World) -> Req:
    return Req("POST", "/api/formula/custom-functions", json={"name": _CUSTOM_FN, "expression": "1+1"})


def _custom_fn_state(_ctx: Ctx) -> tuple[bool, bool]:
    from app.services import formula_engine
    from app.services.formula_custom_functions import get_custom_registry

    return _CUSTOM_FN in get_custom_registry(), formula_engine._REGISTRY.get(_CUSTOM_FN) is not None


def _check_custom_fn(ctx: Ctx, _identity: str, response: Response) -> None:
    from app.services.formula_custom_functions import unregister_custom_function

    try:
        assert response.json() == {"registered": True, "name": _CUSTOM_FN}, response.text
        assert _custom_fn_state(ctx) == (True, True)
    finally:
        unregister_custom_function(_CUSTOM_FN)  # 进程内全局注册表：放行用例结束即注销
    assert _custom_fn_state(ctx) == (False, False)


async def _prep_report_execute(session, world: World) -> Req:
    pid = await _with_year(session, world)
    return Req("POST", "/api/report-config/execute-formula", json={"project_id": str(pid), "year": YEAR,
                                                                   "formula": "1+1"})


def _check_report_execute(_ctx: Ctx, _identity: str, response: Response) -> None:
    assert float(response.json()["value"]) == 2.0, response.text


async def _prep_report_batch(session, world: World) -> Req:
    pid = await _with_year(session, world)
    return Req("POST", "/api/report-config/execute-formulas-batch", json={
        "project_id": str(pid), "year": YEAR, "formulas": [{"row_code": "BS-001", "formula": "1+1"}]})


def _check_report_batch(_ctx: Ctx, _identity: str, response: Response) -> None:
    assert response.json()["results"][0]["value"] == 2, response.text


# ─── 溯源 / 时间轴 / 审计日志（需求 10、11、15） ─────────────────────────────


async def _prep_lineage(session, world: World) -> Req:
    pid = await _with_year(session, world)
    return Req("GET", f"/api/projects/{pid}/lineage", params={"object_type": "report_row", "object_id": "BS-001",
                                                             "year": YEAR})


async def _prep_timeline(session, world: World) -> Req:
    pid = await _with_year(session, world)
    return Req("GET", f"/api/formula-timeline/{pid}/{YEAR}")


async def _prep_audit_get(session, world: World) -> Req:
    pid = await _with_year(session, world)
    return Req("GET", f"/api/formula-audit-log/{pid}/{YEAR}")


async def _prep_audit_post(session, world: World) -> Req:
    pid = await _with_year(session, world)
    return Req("POST", f"/api/formula-audit-log/{pid}/{YEAR}", json={"note": "【测试】第 2 轮配方表人工补记"})


def _check_audit_post(_ctx: Ctx, _identity: str, response: Response) -> None:
    assert response.json()["ok"] is True, response.text


_TB_OLD = {"formula": "TB('1001','审定数')", "formula_category": "auto_calc"}
_TB_NEW = {"formula": "TB('1001','期末余额')", "formula_category": "auto_calc"}


async def _two_versions(session, pid, slot: str) -> int:
    """tb_detail 本项目适配写两版（生产 save_overrides，各留一条 formula.changed）；返回当前版本号。"""
    from app.services.formula_settings import project_ops

    first = await project_ops.save_overrides(session, domain="tb_detail", project_id=pid, user_id=None,
                                             items=[{"slot_key": slot, "definition": dict(_TB_OLD), "label": "库存现金"}])
    v1 = first["saved"][0]["version"]
    second = await project_ops.save_overrides(session, domain="tb_detail", project_id=pid, user_id=None, items=[
        {"slot_key": slot, "definition": dict(_TB_NEW), "expected_version": v1, "label": "库存现金"}])
    await session.commit()
    return second["saved"][0]["version"]


async def _prep_rollback(session, world: World) -> Req:
    pid = await _with_year(session, world)
    slot = f"FH-R2-RB-{uuid.uuid4().hex[:6]}"
    version = await _two_versions(session, pid, slot)
    row = (await session.execute(text(
        "SELECT id, payload->>'row_code' FROM audit_log_entries WHERE action_type = 'formula.changed' "
        "AND payload->>'project_id' = :p AND payload->>'slot_key' = :s ORDER BY ts DESC LIMIT 1"),
        {"p": str(pid), "s": slot})).one()
    world.extra.update(rb_slot=slot, rb_version=version)
    return Req("POST", f"/api/formula-audit-log/{pid}/{YEAR}/rollback", json={
        "row_code": row[1] or slot, "module": "tb_detail", "source_log_id": str(row[0]), "expected_version": version})


async def _tb_local(session, pid, slot: str) -> tuple[str, int]:
    row = (await session.execute(text(
        "SELECT definition->>'formula', version FROM formula_setting WHERE domain = 'tb_detail' AND layer = 'project' "
        "AND project_id = :p AND slot_key = :s AND NOT is_deleted"), {"p": pid, "s": slot})).one()
    return row[0], int(row[1])


def _check_rollback(ctx: Ctx, _identity: str, response: Response) -> None:
    assert response.json()["restored_formula"] == _TB_OLD["formula"], response.text
    formula, version = ctx.call(_tb_local, ctx.world.projects["A"], ctx.world.extra["rb_slot"])
    assert (formula, version) == (_TB_OLD["formula"], ctx.world.extra["rb_version"] + 1)


def _stub_setting_events(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    """变更事件经事件总线另开会话做传播（不在本用例回滚事务里）：桩成计数。"""
    from app.services.formula_settings import propagation

    world.extra["events"] = stub(monkeypatch, propagation, "publish_events", returns=0)


# ─── 三个删除（需求 9，ADR-FHIC-11 强制 CAS） ─────────────────────────────────


_WP_CYCLE = "F"
# 团队分配写的委派角色（assignment_service.ROLE_MAP 的键）；EQCR 的委派 seed_world 已建
_TEAM_ROLES = {"auditor": "auditor", "manager": "manager", "qc": "qc", "partner": "partner"}


async def _prep_wp_formula_delete(session, world: World) -> Req:
    """一份 F 循环底稿 + 一条公式；按团队分配的生产形态补委派行（审计员勾选 F 循环、是该底稿编制人）。"""
    from datetime import datetime, timezone

    from app.models.staff_models import ProjectAssignment, StaffMember
    from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex, WpSourceType

    pid = world.projects["A"]
    for identity, role in _TEAM_ROLES.items():
        staff = StaffMember(user_id=world.users[identity].id, name=f"fh_authz_r2_{identity}")
        session.add(staff)
        await session.flush()
        session.add(ProjectAssignment(project_id=pid, staff_id=staff.id, role=role,
                                      assigned_cycles=[_WP_CYCLE] if identity == "auditor" else None,
                                      assigned_at=datetime.now(timezone.utc)))
    idx = WpIndex(project_id=pid, wp_code="FHR2", wp_name="【测试】配方表底稿", audit_cycle=_WP_CYCLE)
    session.add(idx)
    await session.flush()
    wp = WorkingPaper(project_id=pid, wp_index_id=idx.id, file_path="fhr2.xlsx", source_type=WpSourceType.template,
                      assigned_to=world.users["auditor"].id)
    session.add(wp)
    await session.flush()
    formula = WpFormula(project_id=pid, wp_id=wp.id, sheet_name="审定表", target_cell="B5", expression="=1+1",
                        definition_version=1)
    session.add(formula)
    await session.commit()
    world.extra["wp_formula"] = formula.id
    return Req("DELETE", f"/api/workpapers/{wp.id}/formulas/{formula.id}", params={"expected_version": 1})


def _check_wp_formula_deleted(ctx: Ctx, _identity: str, _response: Response) -> None:
    async def _gone(session, fid):
        return (await session.execute(text("SELECT count(*) FROM wp_formula WHERE id = :i"), {"i": fid})).scalar_one()

    assert ctx.call(_gone, ctx.world.extra["wp_formula"]) == 0


def _stub_wp_gate_outbox(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    """底稿可见性门拒绝时写安全审计 outbox（判定之后、走全局引擎另开连接）：换成记录拒绝原因。"""
    from app.services.wp_visibility.denial import DenialResponder

    reasons: list[str | None] = []

    async def _capture(_self, **fields) -> None:
        reasons.append(fields.get("reason"))

    monkeypatch.setattr(DenialResponder, "_write_outbox", _capture)
    world.extra["denials"] = reasons


async def _prep_template_delete(session, world: World) -> Req:
    from app.models.formula_setting_models import FormulaTemplate

    tpl = FormulaTemplate(name="【测试】第 2 轮配方表模板", share_scope="firm", owner_user_id=world.users["partner"].id,
                          domains=["report"], version=1, status="active")
    session.add(tpl)
    await session.commit()
    world.extra["template"] = tpl.id
    return Req("DELETE", f"/api/formula-templates/{tpl.id}", params={"expected_version": 1})


def _check_template_deleted(_ctx: Ctx, _identity: str, response: Response) -> None:
    assert response.json()["deleted"] is True, response.text


async def _prep_overrides_delete(session, world: World) -> Req:
    pid = world.projects["A"]
    slot = f"FH-R2-RG-{uuid.uuid4().hex[:6]}"
    version = await _two_versions(session, pid, slot)
    world.extra["rg_slot"] = slot
    return Req("DELETE", f"/api/projects/{pid}/formula-settings/tb_detail/overrides",
               params={"slot_key": [slot], "expected_version": [version]})


def _check_overrides_deleted(ctx: Ctx, _identity: str, _response: Response) -> None:
    async def _left(session, pid, slot):
        return (await session.execute(text(
            "SELECT count(*) FROM formula_setting WHERE domain = 'tb_detail' AND layer = 'project' AND project_id = :p "
            "AND slot_key = :s AND NOT is_deleted"), {"p": pid, "s": slot})).scalar_one()

    assert ctx.call(_left, ctx.world.projects["A"], ctx.world.extra["rg_slot"]) == 0


# ─── 一键刷新（需求 3） ──────────────────────────────────────────────────────


async def _prep_draft_refresh(session, world: World) -> Req:
    pid = await _with_year(session, world)
    return Req("POST", "/api/workpapers/draft-refresh", json={"project_id": str(pid), "year": YEAR,
                                                              "scopes": ["report"]})


def _stub_draft_refresh(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    """前置校验与生成编排换成计数桩（业务写入在它们里面；门禁在它们之前）。"""
    from app.routers import draft_refresh as module

    calls: list[str] = []
    run_id = str(uuid.uuid4())

    class _Service:
        async def precheck(self, db, *, project_id, year):
            calls.append("precheck")
            return SimpleNamespace(can_refresh=True, to_dict=lambda: {})

    class _Orchestrator:
        def __init__(self, db):
            pass

        async def generate(self, **_kw):
            calls.append("generate")
            return SimpleNamespace(to_dict=lambda: {"status": "no_effect", "outcome": "no_effect", "run_id": run_id},
                                   post_commit_events=[]), {}

    monkeypatch.setattr(module, "DraftRefreshService", _Service)
    monkeypatch.setattr(module, "DraftRefreshOrchestrator", _Orchestrator)
    world.extra.update(downstream_calls=calls, dr_run_id=run_id)


def _check_draft_refresh(ctx: Ctx, _identity: str, response: Response) -> None:
    body = response.json()
    assert (body["status"], body["run_id"]) == ("no_effect", ctx.world.extra["dr_run_id"]), response.text
    assert ctx.world.extra["downstream_calls"] == ["precheck", "generate"]


# ─── 门禁展示与消费方（需求 16） ──────────────────────────────────────────────


async def _prep_heatmap(session, world: World) -> Req:
    return Req("GET", f"/api/projects/{await _with_year(session, world)}/qc/vr-heatmap")


async def _prep_consistency(session, world: World) -> Req:
    pid = await _with_year(session, world)
    return Req("GET", f"/api/projects/{pid}/workflow/consistency-check", params={"year": YEAR})


def _check_consistency(_ctx: Ctx, _identity: str, response: Response) -> None:
    assert "checks" in response.json() and "not_executed_count" in response.json(), response.text[:300]


async def _prep_export(session, world: World) -> Req:
    pid = await _with_year(session, world)
    return Req("POST", f"/api/projects/{pid}/workflow/export-package", json={"year": YEAR})


def _stub_exporters(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    from app.services.note_word_exporter import NoteWordExporter
    from app.services.report_excel_exporter import ReportExcelExporter

    calls: list[str] = []

    async def _excel(self, **_kw):
        calls.append("excel")
        return BytesIO(b"xlsx")

    async def _word(self, **_kw):
        calls.append("word")
        return BytesIO(b"docx")

    monkeypatch.setattr(ReportExcelExporter, "export", _excel)
    monkeypatch.setattr(NoteWordExporter, "export", _word)
    world.extra["downstream_calls"] = calls


def _check_export(ctx: Ctx, _identity: str, response: Response) -> None:
    assert response.headers["content-type"].startswith("application/zip"), response.headers
    assert ctx.world.extra["downstream_calls"] == ["excel", "word"]


async def _prep_sign_readiness(session, world: World) -> Req:
    return Req("GET", f"/api/projects/{await _with_year(session, world)}/sign-readiness")


def _check_readiness(_ctx: Ctx, _identity: str, response: Response) -> None:
    body = response.json()
    assert {"ready", "groups", "gate_eval_id"} <= set(body), sorted(body)


# ─── 配方表 ──────────────────────────────────────────────────────────────────

_RO_PLUS = A_MEMBERS | {"admin"}
_EDIT_PLUS = A_EDITORS | {"admin"}
_EDIT_DENIED = {"anon": 401, "non_member": 403, "ro": 403, "qc": 403, "eqcr": 403}
_LOGGED_IN_DENIED = {i: 403 for i in LOGGED_IN} | {"anon": 401}

RECIPES_R2: tuple[RecipeR2, ...] = (
    RecipeR2("execute", "POST", "/api/formula/execute", _routers("formula"), _RO_PLUS, _RO_DENIED, _prep_execute,
             "get_current_user + 体内 assert_project_permission(readonly)", check=_ok_json, gate=_PERM),
    RecipeR2("batch-execute", "POST", "/api/formula/batch-execute", _routers("formula"), _RO_PLUS, _RO_DENIED,
             _prep_batch, "get_current_user + 体内 assert_project_permission(readonly)", check=_ok_json, gate=_PERM),
    RecipeR2("debug", "POST", "/api/formula/debug", _routers("formula_debug"), _RO_PLUS, _RO_DENIED, _prep_debug,
             "get_current_user + 体内 assert_project_permission(readonly)", check=_ok_json, gate=_PERM),
    RecipeR2("custom-function", "POST", "/api/formula/custom-functions", _routers("formula"), frozenset({"admin"}),
             {i: c for i, c in _LOGGED_IN_DENIED.items() if i != "admin"}, _prep_custom_fn,
             "require_role(['admin'])（全局能力，无项目维度）", check=_check_custom_fn, role_first=True,
             state=_custom_fn_state),
    RecipeR2("report-execute", "POST", "/api/report-config/execute-formula", _routers("report_config"), _RO_PLUS,
             _RO_DENIED, _prep_report_execute, "get_current_user + 体内 assert_project_permission(readonly)",
             check=_check_report_execute, gate=_PERM),
    RecipeR2("report-batch", "POST", "/api/report-config/execute-formulas-batch", _routers("report_config"), _RO_PLUS,
             _RO_DENIED, _prep_report_batch, "get_current_user + 体内 assert_project_permission(readonly)",
             tables=("audit_log_entries",), check=_check_report_batch, gate=_PERM),
    RecipeR2("lineage", "GET", "/api/projects/{project_id}/lineage", _routers("lineage"), _RO_PLUS, _RO_DENIED,
             _prep_lineage, "require_project_access('readonly')", check=_ok_json, gate=_ACCESS),
    RecipeR2("timeline", "GET", "/api/formula-timeline/{project_id}/{year}", _routers("formula_timeline"), _RO_PLUS,
             _RO_DENIED, _prep_timeline, "require_project_access('readonly')", check=_ok_json, gate=_ACCESS),
    RecipeR2("audit-log-get", "GET", "/api/formula-audit-log/{project_id}/{year}", _routers("formula_audit_log"),
             _RO_PLUS, _RO_DENIED, _prep_audit_get, "require_project_access('readonly')", check=_ok_json,
             gate=_ACCESS),
    RecipeR2("audit-log-post", "POST", "/api/formula-audit-log/{project_id}/{year}", _routers("formula_audit_log"),
             _EDIT_PLUS, _EDIT_DENIED, _prep_audit_post, "require_project_access('edit')",
             tables=("audit_log_entries",), check=_check_audit_post, gate=_ACCESS),
    RecipeR2("rollback", "POST", "/api/formula-audit-log/{project_id}/{year}/rollback", _routers("formula_audit_log"),
             frozenset({"manager", "partner", "admin"}),
             {"anon": 401, "non_member": 403, "ro": 403, "auditor": 403, "qc": 403, "eqcr": 403}, _prep_rollback,
             "require_role(['admin','partner','manager']) + 体内 assert_project_permission(review)",
             tables=("formula_setting", "audit_log_entries"), check=_check_rollback, gate=_PERM, role_first=True,
             stub_factory=_stub_setting_events),
    RecipeR2("wp-formula-delete", "DELETE", "/api/workpapers/{wp_id}/formulas/{formula_id}", _routers("wp_formula"),
             _EDIT_PLUS, {"anon": 401, "non_member": 404, "ro": 404, "qc": 403, "eqcr": 403},
             _prep_wp_formula_delete,
             "router 级 dedicated_wp_gate（底稿可见性：主管委派 / 编制人；看不见统一 404）"
             " + 体内经 wp.project_id 反查后 assert_project_permission(edit)",
             tables=("wp_formula",), check=_check_wp_formula_deleted, gate=_PERM, stub_factory=_stub_wp_gate_outbox),
    RecipeR2("template-delete", "DELETE", "/api/formula-templates/{template_id}", _routers("formula_templates"),
             frozenset({"partner", "admin"}), {i: c for i, c in _LOGGED_IN_DENIED.items() if i not in ("partner", "admin")},
             _prep_template_delete,
             "get_current_user + get_managed（事务所模板对全员可见；只有所有者（partner）与管理员可管理，余者 403）",
             tables=("formula_template",), check=_check_template_deleted, role_first=True),
    RecipeR2("overrides-delete", "DELETE", "/api/projects/{project_id}/formula-settings/{domain}/overrides",
             _routers("formula_settings:project_router"), _EDIT_PLUS, _EDIT_DENIED, _prep_overrides_delete,
             "require_project_access('edit')", tables=("formula_setting",), check=_check_overrides_deleted,
             gate=_ACCESS, stub_factory=_stub_setting_events),
    RecipeR2("draft-refresh", "POST", "/api/workpapers/draft-refresh", _routers("draft_refresh"),
             frozenset({"partner", "admin"}),
             {"anon": 401, "non_member": 403, "ro": 403, "auditor": 403, "manager": 403, "qc": 403, "eqcr": 403},
             _prep_draft_refresh, "require_role(PARTNER_ROLES) + 体内 assert_project_permission(edit)",
             tables=("draft_refresh_audit",), check=_check_draft_refresh, gate=_PERM, role_first=True,
             stub_factory=_stub_draft_refresh),
    RecipeR2("vr-heatmap", "GET", "/api/projects/{project_id}/qc/vr-heatmap", _routers("qc_vr_heatmap"), _RO_PLUS,
             _RO_DENIED, _prep_heatmap, "require_project_access('readonly') + 项目审计年度", check=_ok_json,
             gate=_ACCESS),
    RecipeR2("consistency-check", "GET", "/api/projects/{project_id}/workflow/consistency-check",
             _routers("chain_workflow"), _RO_PLUS, _RO_DENIED, _prep_consistency, "require_project_access('readonly')",
             check=_check_consistency, gate=_ACCESS),
    RecipeR2("export-package", "POST", "/api/projects/{project_id}/workflow/export-package",
             _routers("chain_workflow"), frozenset({"auditor", "manager", "qc", "partner", "admin"}),
             {"anon": 401, "non_member": 403, "ro": 403, "eqcr": 403}, _prep_export,
             "get_current_user + _guard_action(export)：项目 review 级 + 角色矩阵 AUDITOR_PLUS；EQCR 委派只读",
             tables=("gate_decisions", "audit_log_entries"), check=_check_export, gate=_GUARD,
             stub_factory=_stub_exporters),
    RecipeR2("sign-readiness", "GET", "/api/projects/{project_id}/sign-readiness", _routers("partner_dashboard"),
             A_REVIEWERS | {"admin"}, {"anon": 401, "non_member": 403, "ro": 403}, _prep_sign_readiness,
             "require_project_access('review')", tables=("gate_decisions",), check=_check_readiness, gate=_ACCESS),
)


def _assert_denied_r2(recipe: RecipeR2, identity: str, response: Response, gate_runs: Mapping[str, int],
                      before: Mapping[str, tuple[int, str]], after: Mapping[str, tuple[int, str]],
                      state_before: Any, state_after: Any, downstream: list[str] | None,
                      denials: list[str | None] | None) -> None:
    expected = recipe.denied[identity]
    assert response.status_code == expected, (recipe.key, identity, response.status_code, response.text[:800])
    assert all(count > 0 for count, _ in before.values()), (recipe.key, "拒绝前表为空，内容不变的判据会空转", before)
    assert after == before, (recipe.key, identity, "拒绝后表内容变了", before, after)
    assert state_after == state_before, (recipe.key, identity, "拒绝后状态变了", state_before, state_after)
    assert not downstream, (recipe.key, identity, "拒绝的请求调到了下游", downstream)
    if denials is not None:  # 底稿可见性门：404 恰记一条「未委派」，其余拒绝不经它拒
        assert denials == (["not_delegated"] if expected == 404 else []), (recipe.key, identity, denials)
    if recipe.gate is not None:
        runs = gate_runs[recipe.gate]
        if expected in (401, 404) or recipe.role_first:
            assert runs == 0, (recipe.key, identity, "门禁之前就该被拒", recipe.gate, runs)
        else:
            assert runs >= 1, (recipe.key, identity, "403 应来自生产门禁", recipe.gate, runs)


_CASES = [(recipe, identity) for recipe in RECIPES_R2 for identity in IDENTITIES]


@pytest.mark.pg_only
@pytest.mark.parametrize(("recipe", "identity"), _CASES, ids=[f"{r.key}-{i}" for r, i in _CASES])
def test_recipe_r2(recipe: RecipeR2, identity: str, monkeypatch: pytest.MonkeyPatch) -> None:
    with _endpoint(*recipe.routers) as ctx:
        ctx.world = ctx.call(seed_world)
        req = ctx.call(recipe.prepare, ctx.world)
        if recipe.stub_factory is not None:
            recipe.stub_factory(monkeypatch, ctx.world)
        before = ctx.call(_tables_state, recipe.tables)
        state_before = recipe.state(ctx) if recipe.state else None
        response, gate_runs = _send(ctx, identity, req)
        after = ctx.call(_tables_state, recipe.tables)
        state_after = recipe.state(ctx) if recipe.state else None
        denials = ctx.world.extra.get("denials")
        if identity in recipe.allowed:
            assert 200 <= response.status_code < 300, (recipe.key, identity, response.status_code,
                                                       response.text[:800])
            assert not denials, (recipe.key, identity, "放行的请求记了可见性拒绝", denials)
            if recipe.gate is not None:
                assert gate_runs[recipe.gate] >= 1, (recipe.key, identity, "放行的请求没有经过生产门禁", recipe.gate)
            if recipe.check is not None:
                recipe.check(ctx, identity, response)
        else:
            downstream = ctx.world.extra.get("downstream_calls")
            events = ctx.world.extra.get("events")
            _assert_denied_r2(recipe, identity, response, gate_runs, before, after, state_before, state_after,
                              list(downstream or []) + (["publish_events"] * events.count if events else []),
                              denials)


def test_recipes_r2_partition_identities_and_cover_design_rows() -> None:
    """九种身份每条配方恰好分一次；与原文件配方不重叠；design §10.3 的其余 19 行全部在本表。"""
    from tests.formula_hub.test_formula_hub_endpoint_authz import RECIPES

    assert len(RECIPES_R2) == 19 and len({r.key for r in RECIPES_R2}) == 19
    keys = {(r.method, r.route) for r in RECIPES_R2}
    assert keys.isdisjoint({(r.method, r.route) for r in RECIPES})
    for recipe in RECIPES_R2:
        assert recipe.allowed.isdisjoint(recipe.denied) and recipe.allowed | set(recipe.denied) == set(IDENTITIES), \
            recipe.key
        assert recipe.basis.strip(), recipe.key
        if 404 in recipe.denied.values():  # 只有底稿绑定路由有可见性门；404 的拒绝原因必须被核对
            assert "{wp_id}" in recipe.route and recipe.stub_factory is _stub_wp_gate_outbox, recipe.key
