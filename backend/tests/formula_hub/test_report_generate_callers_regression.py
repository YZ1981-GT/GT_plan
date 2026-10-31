"""需求 3.5 两个调用方回归（spec formula-hub-integrity-closure 任务 20 第一段 B-1b-2；ADR-FHIC-08）。

本任务给 ``ReportEngine.generate_all_reports`` 加的三个关键字参数（``skip_recalc`` / ``publish_events`` / ``summary_out``）只由 Draft
Refresh 报表范围传；其余两个调用方本任务未改（``git diff 00525717f`` 为空），本文件钉住它们在默认参数下的返回结构与事件行为：

- 报表路由 ``POST /api/reports/generate``（``routers/reports.py::generate_reports``）：``_draft_refresh_world`` 换挂 ``reports.router``
  真发请求；三道门禁 ``require_operation("report:edit")`` / ``check_consol_lock`` / ``PrerequisiteChecker`` 都真实运行（夹具合伙人按
  生产权限矩阵即可通过，时间线上各记一笔）。200；响应键 = message / report_types / row_counts / summary（summary 三键）；
  ``report_types`` 照原样是结果的全部键（含 coverage_stats）；``generate_all_reports`` 只收（项目, 年度, 准则）三个位置参数、不带三个
  新参数 ⇒ ``full_recalc`` 1 次；``REPORT_ROW_CHANGED`` 经 ``publish``（防抖通道）恰 1 条、由 ``generate_all_reports`` 内部发、在
  commit 之前，``changed_row_codes`` 非空、≤ 100；``REPORTS_UPDATED`` 经 ``publish_immediate`` 恰 1 条、在 commit 之后，
  ``report_types`` = 响应的；``financial_report`` 按定义写满。
- 链式编排 ``ChainOrchestrator._step_generate_reports``（无参构造）：在世界的会话里直调。返回 {applicable_standard: 项目
  ``template_type`` + ``_`` + ``report_scope``, report_types: 值为列表的键（不含 coverage_stats）, coverage: float}；
  ``generate_all_reports`` 只收（项目, 年度）+ ``applicable_standard``；``full_recalc`` 1 次；``REPORT_ROW_CHANGED`` 经 ``publish``
  1 条、不经 ``publish_immediate``；不 commit。

防抖 ``publish`` 在 TestClient 的事件循环里起 ``call_later`` 延迟任务（``event_bus._pending`` 记本项目的去重键）：两例都在世界退出前、
于同一事件循环里等到该键被 ``_dispatch`` 取走、``EventBus`` 的分发 / 持久化任务都跑完，并断言 ``_pending`` 里不再有本项目的键、总数
回到用例开始时（不跨用例泄漏）。调用参数、事件序列、返回键与这些核对材料写进 junit property。
"""
from __future__ import annotations

import asyncio
import inspect
import time
from collections import Counter
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text

import app.routers.reports as reports_module
from app.models.audit_platform_schemas import EventType
from app.services.chain_orchestrator import ChainOrchestrator
from app.services.event_bus import event_bus
from app.services.report_config_service import ReportConfigService
from app.services.report_engine import ReportEngine
from tests.formula_hub import gold_report_evaluator as gold
from tests.formula_hub._draft_refresh_world import YEAR, Key, Mark, World, draft_refresh_world, report_states, rows_json

pytestmark = pytest.mark.pg_only

GENERATE = "/api/reports/generate"
ROW_CHANGED, UPDATED = EventType.REPORT_ROW_CHANGED.value, EventType.REPORTS_UPDATED.value
ROW_CODE_LIMIT = 100
NEW_PARAMS = ("skip_recalc", "publish_events", "summary_out")
RESPONSE_KEYS = {"message", "report_types", "row_counts", "summary"}
SUMMARY_KEYS = {"total_rows", "non_zero_rows", "failed_rows"}
CHAIN_KEYS = {"applicable_standard", "report_types", "coverage"}
GATES = ("call:_resolve_project_role", "call:check_consol_lock", "call:PrerequisiteChecker.check")
TABLES = ("financial_report", "trial_balance")
DRAIN_TIMEOUT = 10.0


def _pending_keys(project_id: UUID) -> list[str]:
    """``event_bus._pending``（防抖缓冲）里属于本项目的去重键（``<事件>:<项目>:<年度>``）。"""
    return sorted(key for key in list(event_bus._pending) if f":{project_id}:" in key)


def _bus_tasks() -> list[str]:
    """当前事件循环里还没结束的 ``EventBus`` 协程任务（防抖到期的分发、Redis 持久化）。"""
    current = asyncio.current_task()
    names = (getattr(task.get_coro(), "__qualname__", "") for task in asyncio.all_tasks()
             if task is not current and not task.done())
    return sorted(name for name in names if name.startswith("EventBus."))


async def _pending_now(_session, project_id: UUID) -> dict[str, Any]:
    return {"keys": _pending_keys(project_id), "total": len(event_bus._pending), "at": time.perf_counter()}


async def _drain(_session, project_id: UUID) -> dict[str, Any]:
    """在 TestClient 的事件循环里等本项目的防抖延迟任务被 ``_dispatch`` 取走、``EventBus`` 任务都跑完（≤ 10 秒）。超时则取消本项目
    剩下的延迟任务（不泄漏到后面的用例）并如实返回，由用例断言为空。"""
    loop = asyncio.get_running_loop()
    started, seen = loop.time(), set()
    while loop.time() - started < DRAIN_TIMEOUT:
        pending, tasks = _pending_keys(project_id), _bus_tasks()
        seen.update(tasks)
        if not pending and not tasks:
            break
        await asyncio.sleep(0.05)
    left_pending, left_tasks = _pending_keys(project_id), _bus_tasks()
    for key in left_pending:
        entry = event_bus._pending.pop(key, None)
        if entry is not None:
            entry["handle"].cancel()
    return {"seconds": round(loop.time() - started, 3), "left_pending": left_pending, "left_tasks": left_tasks,
            "seen_tasks": sorted(seen), "total": len(event_bus._pending)}


async def _definition_keys(session, project_id: UUID) -> set[Key]:
    standard = await gold.resolve_standard(session, project_id)
    return {(c.report_type, c.row_code) for c in await gold.load_config_rows(session, project_id, standard)}


async def _standard(session, project_id: UUID) -> str:
    return await ReportConfigService.resolve_applicable_standard(session, project_id)


async def _project_fields(session, project_id: UUID) -> tuple[Any, Any]:
    row = (await session.execute(text("SELECT template_type, report_scope FROM projects WHERE id = :pid"),
                                 {"pid": project_id})).one()
    return row[0], row[1]


async def _chain_step(session, project_id: UUID) -> dict[str, Any]:
    return await ChainOrchestrator()._step_generate_reports(session, project_id, YEAR)


def _handler_counts() -> dict[str, int]:
    return {name: len(event_bus._handlers.get(EventType(name), [])) for name in (ROW_CHANGED, UPDATED)}


def _only(marks: list[Mark], kind: str) -> int:
    found = [i for i, mark in enumerate(marks) if mark.kind == kind]
    assert len(found) == 1, f"{kind} 应恰 1 笔，实际 {len(found)}：{[m.kind for m in marks]}"
    return found[0]


def _events(marks: list[Mark], kind: str) -> list[tuple[int, Mark]]:
    return [(i, mark) for i, mark in enumerate(marks) if mark.kind == kind]


def _operation_gates(world: World) -> list[Any]:
    """生成端点依赖树里 ``require_operation(...)`` 闭包所带的操作码（按生产注册挂上的真实依赖，未被 override）。"""
    routes = [r for r in world.api.routes if getattr(r, "path", None) == GENERATE and "POST" in getattr(r, "methods", ())]
    assert len(routes) == 1, f"{GENERATE} 路由 {len(routes)} 条"
    found, stack = [], list(routes[0].dependant.dependencies)
    while stack:
        dep = stack.pop()
        if getattr(dep.call, "__qualname__", "") == "require_operation.<locals>.dependency":
            found.append(inspect.getclosurevars(dep.call).nonlocals.get("operation"))
        stack.extend(dep.dependencies)
    return found


def _new_param_defaults() -> dict[str, Any]:
    parameters = inspect.signature(inspect.unwrap(ReportEngine.generate_all_reports)).parameters
    return {name: parameters[name].default for name in NEW_PARAMS}


def _assert_debounce(tag: str, marks: list[Mark], publish_at: int, pid: UUID, pending: dict[str, Any],
                     drained: dict[str, Any], total_before: int) -> None:
    """防抖延迟任务：发出后到期前 ``_pending`` 里有本项目的键（查得晚于防抖窗口则不要求）；退出前已被取走、任务跑完、总数复原。"""
    key = f"{ROW_CHANGED}:{pid}:{YEAR}"
    elapsed = pending["at"] - marks[publish_at].at
    assert key in pending["keys"] or elapsed >= event_bus._debounce_ms / 1000, (
        f"{tag} 防抖 publish 之后 {elapsed:.3f} 秒 _pending 里没有 {key}：{pending}")
    assert drained["left_pending"] == [] and drained["left_tasks"] == [], f"{tag} 防抖 / 分发任务没跑完：{drained}"
    assert drained["total"] == total_before, f"{tag} _pending 总数 {total_before} → {drained['total']}（泄漏）"


def _record(request, prefix: str, values: dict[str, Any]) -> None:
    request.node.user_properties.extend((f"{prefix}_{name}", str(value)) for name, value in values.items())


def test_reports_generate_route_default_contract(request):
    """报表路由（默认参数）：返回结构；三道门禁真实运行；full_recalc 1 次；REPORT_ROW_CHANGED 经防抖 publish（commit 前）、
    REPORTS_UPDATED 经 publish_immediate（commit 后）各 1 条；报表按定义写满。"""
    with draft_refresh_world("rptgen", routers=(reports_module.router,)) as world:
        pid, user_id = world.project_id, world.seeded.user.id
        gates, handlers = _operation_gates(world), _handler_counts()
        total_before = world.run(_pending_now, pid)["total"]
        before = {table: world.run(rows_json, pid, table) for table in TABLES}
        response, marks = world.post({"project_id": str(pid), "year": YEAR}, endpoint=GENERATE)
        pending = world.run(_pending_now, pid)
        drained = world.run(_drain, pid)
        after = {table: world.run(rows_json, pid, table) for table in TABLES}
        states, definitions = world.run(report_states, pid), world.run(_definition_keys, pid)
        standard = world.run(_standard, pid)
    body = response.json()
    calls = {m.kind: m.extra for m in marks if m.kind.startswith("call:")}  # 只断言恰 1 笔的那几种（见 _only）
    published, immediate = _events(marks, "publish"), _events(marks, "publish_immediate")
    produced = sorted({report_type for report_type, _ in states})
    non_zero = sum(1 for row in states.values() if row.amount is not None and row.amount != 0)
    _record(request, "route", {
        "http": response.status_code, "response_keys": sorted(body), "summary": body.get("summary"),
        "report_types": body.get("report_types"), "row_counts": body.get("row_counts"), "call_args": calls,
        "events": [(i, m.kind, m.event_type, len((m.extra or {}).get("changed_row_codes") or [])) for i, m in
                   (*published, *immediate)],
        "timeline": [m.kind for m in marks], "operation_gates": gates, "new_param_defaults": _new_param_defaults(),
        "event_handlers": handlers, "pending_after_request": pending, "drained": drained, "standard": standard,
        "fr_rows": (len(before["financial_report"]), len(after["financial_report"])), "definition_rows": len(definitions),
        "non_zero_rows_db": non_zero, "tb_changed": after["trial_balance"] != before["trial_balance"],
        "row_changed_codes_head": ((published[0][1].extra or {}).get("changed_row_codes") or [])[:5] if published else []})

    # ── 返回结构 ──
    assert response.status_code == 200, body
    assert set(body) == RESPONSE_KEYS and set(body["summary"]) == SUMMARY_KEYS, f"响应键 {sorted(body)}"
    assert body["message"] == "报表生成成功", body["message"]
    report_types = body["report_types"]
    assert "coverage_stats" in report_types and "debug_info" not in report_types, report_types
    assert sorted(set(report_types) - {"coverage_stats"}) == produced, f"report_types {report_types} / 写库 {produced}"
    assert list(body["row_counts"]) == report_types, body["row_counts"]
    assert {rt: body["row_counts"][rt] for rt in produced} == Counter(rt for rt, _ in states), body["row_counts"]
    assert body["summary"] == {"total_rows": sum(body["row_counts"].values()), "non_zero_rows": non_zero,
                               "failed_rows": 0}, f"summary {body['summary']}（写库非零 {non_zero}）"

    # ── 门禁真实运行（依赖未被 override、时间线各一笔，在生成之前）──
    gen, recalc, commit = _only(marks, "call:generate_all_reports"), _only(marks, "call:full_recalc"), _only(marks, "commit")
    assert gates == ["report:edit"], f"生成端点的操作门禁：{gates}"
    order = [_only(marks, kind) for kind in GATES]
    assert order == sorted(order) and order[-1] < gen, f"门禁顺序：{[m.kind for m in marks]}"
    assert calls["call:_resolve_project_role"] == {"args": ["AsyncSession", str(user_id), None], "kwargs": {}}, calls
    assert calls["call:check_consol_lock"] == {"args": [], "kwargs": {"project_id": str(pid), "db": "AsyncSession"}}, calls
    assert calls["call:PrerequisiteChecker.check"]["args"] == [
        "PrerequisiteChecker", "AsyncSession", str(pid), YEAR, "generate_reports"], calls

    # ── 调用参数：默认参数（不带三个新参数）⇒ 生成前重算试算表 ──
    assert _new_param_defaults() == {"skip_recalc": False, "publish_events": True, "summary_out": None}
    assert calls["call:generate_all_reports"] == {"args": ["ReportEngine", str(pid), YEAR, standard], "kwargs": {}}, calls
    assert calls["call:full_recalc"] == {"args": ["TrialBalanceService", str(pid), YEAR], "kwargs": {}}, calls
    assert gen < recalc and after["trial_balance"] != before["trial_balance"], "full_recalc 不在生成里 / 没有改动试算表"

    # ── 事件：REPORT_ROW_CHANGED 防抖 publish 在 commit 前；REPORTS_UPDATED publish_immediate 在 commit 后 ──
    assert [m.event_type for _, m in published] == [ROW_CHANGED], f"publish：{[m.event_type for _, m in published]}"
    assert [m.event_type for _, m in immediate] == [UPDATED], f"publish_immediate：{[m.event_type for _, m in immediate]}"
    (at_changed, changed), (at_updated, updated) = published[0], immediate[0]
    assert recalc < at_changed < commit < at_updated and _events(marks, "rollback") == [], [m.kind for m in marks]
    assert {(m.project_id, m.year) for m in (changed, updated)} == {(str(pid), YEAR)}, (changed, updated)
    codes = (changed.extra or {}).get("changed_row_codes") or []
    assert 0 < len(codes) <= ROW_CODE_LIMIT and set(codes) <= {code for _, code in states}, f"changed_row_codes {codes[:5]}"
    assert (updated.extra or {}).get("report_types") == report_types, f"REPORTS_UPDATED {updated.extra}"
    _assert_debounce("报表路由", marks, at_changed, pid, pending, drained, total_before)

    # ── 写库 ──
    assert before["financial_report"] == [] and set(states) == definitions, f"报表行 {len(states)} / 定义 {len(definitions)}"
    assert len(after["financial_report"]) == len(definitions) > 0, f"financial_report 写入 {len(after['financial_report'])} 行"


def test_chain_step_generate_reports_default_contract(request):
    """链式编排（默认参数）：返回 {applicable_standard, report_types, coverage}；full_recalc 1 次；REPORT_ROW_CHANGED 经 publish 1 条、
    不经 publish_immediate；不 commit。"""
    with draft_refresh_world("chainrpt") as world:
        pid = world.project_id
        handlers = _handler_counts()
        total_before = world.run(_pending_now, pid)["total"]
        before = {table: world.run(rows_json, pid, table) for table in TABLES}
        start = len(world.recorder.timeline)
        result = world.run(_chain_step, pid)
        marks = world.recorder.since(start)
        pending = world.run(_pending_now, pid)
        drained = world.run(_drain, pid)
        after = {table: world.run(rows_json, pid, table) for table in TABLES}
        states, definitions = world.run(report_states, pid), world.run(_definition_keys, pid)
        fields, resolved = world.run(_project_fields, pid), world.run(_standard, pid)
    calls = {m.kind: m.extra for m in marks if m.kind.startswith("call:")}
    published, immediate = _events(marks, "publish"), _events(marks, "publish_immediate")
    produced = sorted({report_type for report_type, _ in states})
    _record(request, "chain", {
        "result": result, "result_types": {k: type(v).__name__ for k, v in result.items()}, "call_args": calls,
        "events": [(i, m.kind, m.event_type, len((m.extra or {}).get("changed_row_codes") or [])) for i, m in
                   (*published, *immediate)],
        "timeline": [m.kind for m in marks], "event_handlers": handlers, "pending_after_step": pending,
        "drained": drained, "project_fields": fields, "resolved_standard": resolved,
        "fr_rows": (len(before["financial_report"]), len(after["financial_report"])), "definition_rows": len(definitions),
        "tb_changed": after["trial_balance"] != before["trial_balance"]})

    # ── 返回结构（按源码现状）──
    assert set(result) == CHAIN_KEYS, f"返回键 {sorted(result)}"
    assert result["applicable_standard"] == f"{fields[0]}_{fields[1]}" and all(fields), (result, fields)
    assert isinstance(result["report_types"], list) and all(isinstance(rt, str) for rt in result["report_types"])
    assert sorted(result["report_types"]) == produced and "coverage_stats" not in result["report_types"], result
    assert isinstance(result["coverage"], float) and 0 <= result["coverage"] <= 100, result["coverage"]

    # ── 调用参数与事件 ──
    gen, recalc = _only(marks, "call:generate_all_reports"), _only(marks, "call:full_recalc")
    assert calls["call:generate_all_reports"] == {
        "args": ["ReportEngine", str(pid), YEAR], "kwargs": {"applicable_standard": result["applicable_standard"]}}, calls
    assert calls["call:full_recalc"] == {"args": ["TrialBalanceService", str(pid), YEAR], "kwargs": {}}, calls
    assert [m.event_type for _, m in published] == [ROW_CHANGED] and immediate == [], [m.kind for m in marks]
    assert gen < recalc < published[0][0], [m.kind for m in marks]
    assert _events(marks, "commit") == _events(marks, "rollback") == [], [m.kind for m in marks]
    codes = (published[0][1].extra or {}).get("changed_row_codes") or []
    assert 0 < len(codes) <= ROW_CODE_LIMIT and (published[0][1].project_id, published[0][1].year) == (str(pid), YEAR)
    assert after["trial_balance"] != before["trial_balance"], "full_recalc 没有改动试算表"
    _assert_debounce("链式编排", marks, published[0][0], pid, pending, drained, total_before)

    # ── 写库（会话内、未提交）──
    assert before["financial_report"] == [] and set(states) == definitions, f"报表行 {len(states)} / 定义 {len(definitions)}"
