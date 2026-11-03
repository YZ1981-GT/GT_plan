"""Draft Refresh 路由状态与幂等（spec formula-hub-integrity-closure 任务 20 第一段 B-2；需求 3.3；ADR-FHIC-08）。

真 PG、经路由 ``POST /api/workpapers/draft-refresh``：世界 = ``_draft_refresh_world``（按生产注册挂路由，只替换当前用户与会话；
门禁、编排器、报表范围执行与事件总线都是生产对象，时间线只记录、照常调用原实现）。每个用例一个世界：

1. ``no_effect`` 照实报告（变异 #26「路由恢复 ``no_effect→success``」必红）：只勾 ``workpaper:D``，wp_index 只有预设库里没有预设的
   ``D0-1``、不建 ``wp_formula`` ⇒ 200，响应 ``status`` / ``outcome`` 与编排器结果对象的 ``status`` / ``outcome`` 都是 ``no_effect``
   （路由原样透传），四个计数 0，审计 +1。
2. 带请求键的幂等命中：勾 ``["report", "workpaper:D"]``（``D0`` 有预设）、同一个显式 ``idempotency_key`` 连发两次。第 1 次
   ``success`` / ``applied``：审计 ``detail.scopes`` 保序、``idempotency_key`` 列 = ``detail.idempotency_base`` = 请求键，
   ``preset_application`` = 测试内独立算出的那份（纯映射 ``build_preset_draft_units``：report 的 7 个预设页面 + ``workpaper:D0``），
   Draft 标记数 = 本次新增的 ``draft_marker`` 行数 = 预设条数。第 2 次 ``idempotent_hit``：``idempotent`` 为真、``run_id`` = 第 1 次的
   审计 id、outcome 与四个计数同第 1 次，``full_recalc`` / ``generate_all_reports`` 0 次（判定在任何范围执行之前，report 范围也不执行），
   四张表逐字节不变、0 事件、恰 1 次 commit（无写入），``preset_application`` 回放第 1 次存的那份，报表执行过 ⇒ 不可回滚 + 说明。
   判据不空转：第 1 次的 ``full_recalc`` 改了复制来的试算表（报表四项进计划指纹 ⇒ 不带键时第 2 次会重新执行），命中只能来自请求键；
   两次之间另加一张有预设的底稿 ``D1``（不在四张表里），本次重算的预设套用因此与首次不同，回放的仍是首次存的那份。
3. 同键 ``executing`` ⇒ 409，``detail`` = ``DRAFT_REFRESH_IN_PROGRESS`` + 中文 ``message`` + ``run_id``（那条审计）；0 次 commit、
   两个执行函数 0 次、0 事件、四张表逐字节不变（判定在取锁之后、任何范围执行与写入之前）。
   用例 2、3 另在编排器 ``_acquire_project_lock`` 上记一笔（只记录、调用原实现）：恰 1 次取锁，且在执行函数与 commit 之前。
4. 同键 ``rolled_back`` ⇒ 照常执行（``success`` / ``applied``）：新审计的 ``idempotency_key`` 列 = ``write_key(K, 1)`` ≠ K（K 已被
   占用），``detail.idempotency_base`` = K；那条 rolled_back 审计逐字节不变。
5. 未知范围：勾 ``["report", "bogus_scope", "report"]`` ⇒ 报表范围执行一次，``detail.scopes == ["report"]``（经发现集合过滤、保序
   去重），``preset_application`` = 只按 report 独立算出的那份。🔴 照实：未知范围只经编排器 ``logger.warning`` 落日志（恰 1 条、含
   ``'bogus_scope'``），**不进**响应 ``warnings``；响应 ``scopes`` 原样回显请求（含未知键与重复，只记 junit、不断言）。

各次的 HTTP / status / outcome / 计数 / 事件数 / commit 数 / 执行函数调用数经 ``user_properties`` 写进 junit；断言消息以
「用例名 第 n 次」开头。
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest import mock
from uuid import UUID

import pytest
from sqlalchemy import text

from app.services.draft_refresh_service import DraftRefreshService
from app.services.formula_management.draft_refresh_orchestrator import DraftRefreshOrchestrator
from app.services.formula_management.preset_library import build_preset_index, find_presets_for_page
from app.services.formula_management.refresh_idempotency import write_key
from tests.formula_hub._draft_refresh_world import (
    JSON_TABLES,
    RESULT_KIND,
    YEAR,
    AuditRow,
    Mark,
    Prepare,
    World,
    add_workpaper,
    assert_production_path,
    audit_rows,
    draft_refresh_world,
    rows_json,
    trial_balance_rows,
)
from tests.formula_hub.test_draft_refresh_truthful import (
    BARE_WP,
    CJK,
    COUNT_FIELDS,
    MARKER_SCOPE,
    PRESET_WP,
    ROLLBACK_WARNING,
)

pytestmark = pytest.mark.pg_only

#: 显式请求键（固定字符串；每个用例一个新项目，审计的部分唯一索引按项目年度，用例之间不互相撞）
REQUEST_KEY = "fh_t20_b2_router_status"
IN_PROGRESS = "DRAFT_REFRESH_IN_PROGRESS"
UNKNOWN_SCOPE = "bogus_scope"
ORCHESTRATOR_LOGGER = "app.services.formula_management.draft_refresh_orchestrator"
HEX64 = re.compile(r"[0-9a-f]{64}")
EXECUTORS = ("full_recalc", "generate_all_reports")
#: 时间线上「取项目锁」那一笔（:func:`_lock_spy` 记）
LOCK_KIND = "call:_acquire_project_lock"
#: 用例 2 两次请求之间另加的底稿（预设库里有预设 ⇒ 本次重算的预设套用与首次存的不同，回放判据不空转）
EXTRA_WP = "D1"
#: 预设库里 ``report:`` 键的个数（B-1b-1 现查 7 个）；只作夹具自证
REPORT_PAGES = 7
Tables = dict[str, list[tuple[str, str]]]


@dataclass
class Shot:
    """一次请求：响应、本次时间线（首尾是 ``request:start`` / ``request:end``）、请求前后四张表全行与审计行。"""

    case: str
    n: int
    status_code: int
    body: dict[str, Any]
    marks: list[Mark]
    before: Tables
    after: Tables
    audits_before: list[AuditRow]
    audits_after: list[AuditRow]

    @property
    def tag(self) -> str:
        return f"{self.case} 第 {self.n} 次"

    @property
    def kinds(self) -> list[str]:
        return [mark.kind for mark in self.marks]

    def at(self, kind: str) -> list[int]:
        return [i for i, mark in enumerate(self.marks) if mark.kind == kind]

    @property
    def events(self) -> list[tuple[int, Mark]]:
        return [(i, mark) for i, mark in enumerate(self.marks) if mark.kind in ("publish", "publish_immediate")]

    @property
    def result(self) -> dict[str, Any]:
        """编排器结果对象的 outcome / status / failures（时间线上 :data:`RESULT_KIND` 那一笔；``generate`` 抛错时没有、为空 dict）。"""
        found = [mark.extra for mark in self.marks if mark.kind == RESULT_KIND]
        return dict(found[-1] or {}) if found else {}

    @property
    def new_audits(self) -> list[AuditRow]:
        known = {audit.id for audit in self.audits_before}
        return [audit for audit in self.audits_after if audit.id not in known]

    @property
    def changed_tables(self) -> list[str]:
        """请求前后不是逐字节相同的表（:data:`JSON_TABLES` 之内）。"""
        return [table for table in JSON_TABLES if self.before[table] != self.after[table]]

    def new_rows(self, table: str) -> int:
        return len({row_id for row_id, _ in self.after[table]} - {row_id for row_id, _ in self.before[table]})


async def _tables(session, project_id: UUID) -> Tables:
    return {table: await rows_json(session, project_id, table) for table in JSON_TABLES}


def _send(world: World, body: dict[str, Any], n: int, case: str) -> Shot:
    """真发一次请求；请求前后各读一次四张表（:data:`JSON_TABLES`）与审计行。"""
    pid = world.project_id
    before, audits_before = world.run(_tables, pid), world.run(audit_rows, pid)
    response, marks = world.post(body)
    return Shot(case, n, response.status_code, response.json(), marks, before, world.run(_tables, pid),
                audits_before, world.run(audit_rows, pid))


def _record(request, s: Shot, **extra: Any) -> None:
    """本次的 HTTP / status / outcome / 计数 / 事件 / commit / 执行函数调用数等写进 junit（``round<n>_<名称>``）。"""
    ok = s.status_code == 200
    body = s.body if ok else {}
    values = {
        "http": s.status_code,
        **{key: body.get(key) for key in ("status", "outcome", "idempotent", "run_id", *COUNT_FIELDS, "failed_count",
                                          "rollback_available", "warnings", "failures", "preset_application", "scopes")},
        "error_detail": None if ok else s.body.get("detail"),
        "result": s.result,
        "event_count": len(s.events),
        "events": [(mark.kind, mark.event_type) for _, mark in s.events],
        "commits": len(s.at("commit")),
        "rollbacks": len(s.at("rollback")),
        "lock_calls": len(s.at(LOCK_KIND)),
        **{f"{name}_calls": len(s.at(f"call:{name}")) for name in (*EXECUTORS, "trigger_recalc")},
        "tables_before": {table: len(rows) for table, rows in s.before.items()},
        "tables_after": {table: len(rows) for table, rows in s.after.items()},
        "changed_tables": s.changed_tables,
        "new_audits": [{"id": str(a.id), "result_status": a.result_status, "idempotency_key": a.idempotency_key,
                        **{k: a.detail.get(k) for k in ("outcome", "scopes", "idempotency_base", "plan_fp")}}
                       for a in s.new_audits],
        "seconds": round(s.marks[-1].at - s.marks[0].at, 3),
        **extra,
    }
    request.node.user_properties.extend((f"round{s.n}_{name}", str(value)) for name, value in values.items())


@contextmanager
def _lock_spy(world: World) -> Iterator[None]:
    """在编排器类上包 ``_acquire_project_lock``：调用前在世界时间线上记 :data:`LOCK_KIND`，再调用原实现（只记录，退出时还原）。"""
    original = DraftRefreshOrchestrator._acquire_project_lock

    async def spy(self, project_id):
        world.recorder.timeline.append(Mark(LOCK_KIND))
        return await original(self, project_id)

    with mock.patch.object(DraftRefreshOrchestrator, "_acquire_project_lock", spy):
        yield


def _assert_timeline(s: Shot, *, committed: bool, executed: bool, events: int, locked: bool = False) -> None:
    """``committed``：路由恰 1 次 commit、0 次 rollback（否则 0 次 commit）；``executed``：报表范围执行过 ⇒ ``full_recalc`` /
    ``generate_all_reports`` 各 1 次、都在 commit 之前（否则都 0 次）；``events``：事件数（只经 ``publish_immediate``、都在 commit 之后）；
    ``locked``：本次装了 :func:`_lock_spy` ⇒ 恰 1 次取项目锁，且在两个执行函数与 commit 之前。"""
    commits, rollbacks = s.at("commit"), s.at("rollback")
    if locked:
        locks, later = s.at(LOCK_KIND), [*s.at("call:full_recalc"), *s.at("call:generate_all_reports"), *commits]
        assert len(locks) == 1 and all(locks[0] < i for i in later), (
            f"{s.tag} 应恰 1 次取项目锁、在执行函数与 commit 之前，时间线 {s.kinds}")
    if committed:
        assert len(commits) == 1 and rollbacks == [], f"{s.tag} 应恰 1 次 commit、0 次 rollback，时间线 {s.kinds}"
    else:
        assert commits == [], f"{s.tag} 应 0 次 commit，时间线 {s.kinds}"
    end = commits[0] if commits else len(s.marks)
    for name in EXECUTORS:
        calls = s.at(f"call:{name}")
        assert len(calls) == int(executed) and all(i < end for i in calls), (
            f"{s.tag} {name} 调用 {len(calls)} 次（应 {int(executed)} 次、都在 commit 之前），时间线 {s.kinds}")
    assert s.at("publish") == [] and len(s.events) == events and all(i > end for i, _ in s.events), (
        f"{s.tag} 事件应恰 {events} 条、只经 publish_immediate、都在 commit 之后：{[(m.kind, m.event_type) for _, m in s.events]}")


def _assert_executed_audit(s: Shot, *, outcome: str, scopes: list[str], base: str | None = None,
                           column: str | None = None) -> AuditRow:
    """本次执行写了恰 1 条审计：id = run_id，``detail`` 的 outcome / 四个计数 = 响应，``detail.scopes`` = ``scopes``，``plan_fp`` 为
    64 位十六进制；有效键 ``detail.idempotency_base`` = ``base``（不带请求键 ⇒ ``plan_fp``），``idempotency_key`` 列 = ``column``
    （默认 = 有效键）。"""
    assert len(s.new_audits) == 1 and len(s.audits_after) == len(s.audits_before) + 1, (
        f"{s.tag} 审计应 +1：{len(s.audits_before)} → {len(s.audits_after)}")
    audit = s.new_audits[0]
    detail = audit.detail
    assert str(audit.id) == s.body["run_id"], f"{s.tag} run_id {s.body['run_id']} ≠ 新审计 {audit.id}"
    assert {key: detail.get(key) for key in ("outcome", *COUNT_FIELDS)} == {
        "outcome": outcome, **{key: s.body[key] for key in COUNT_FIELDS}}, f"{s.tag} 审计 detail 的 outcome / 计数：{detail}"
    assert detail.get("scopes") == scopes, f"{s.tag} 审计 detail.scopes {detail.get('scopes')}（应 {scopes}）"
    fp = detail.get("plan_fp")
    assert isinstance(fp, str) and HEX64.fullmatch(fp), f"{s.tag} 审计 detail.plan_fp：{fp!r}"
    base = fp if base is None else base
    column = base if column is None else column
    assert (detail.get("idempotency_base"), audit.idempotency_key) == (base, column), (
        f"{s.tag} 有效键 {detail.get('idempotency_base')!r} / 列 {audit.idempotency_key!r}，应为 {base!r} / {column!r}")
    return audit


def _assert_applied(s: Shot, *, locked: bool = False) -> None:
    """报表范围执行且成功：200 ``success`` / ``applied``、applied > 0、``affected = applied + recomputed``、无失败、不可回滚 + 说明；
    恰 1 次 commit、两个执行函数各 1 次、2 条提交后事件（同 B-1a 第 1 次）；``locked`` 透传 :func:`_assert_timeline`。"""
    assert s.status_code == 200, f"{s.tag} HTTP {s.status_code}：{s.body}"
    assert (s.body["status"], s.body["outcome"], s.body["idempotent"]) == ("success", "applied", False), (
        f"{s.tag} status / outcome / idempotent：{s.body}")
    assert s.body["applied_count"] > 0 and s.body["affected_count"] == s.body["applied_count"] + s.body["recomputed_count"], (
        f"{s.tag} 计数：{[s.body[key] for key in COUNT_FIELDS]}")
    assert (s.body["failures"], s.body["failed_count"]) == ([], 0), f"{s.tag} failures：{s.body['failures'][:5]}"
    assert s.body["rollback_available"] is False and ROLLBACK_WARNING in s.body["warnings"], (
        f"{s.tag} rollback_available {s.body['rollback_available']}、warnings {s.body['warnings']}")
    _assert_timeline(s, committed=True, executed=True, events=2, locked=locked)


async def _wp_codes(session, project_id: UUID) -> list[str]:
    """本项目 wp_index 现存编码（未删、去重、排序；只读）。"""
    rows = (await session.execute(text(
        "SELECT DISTINCT wp_code FROM wp_index WHERE project_id = :pid AND is_deleted = false"), {"pid": project_id})).scalars()
    return sorted(str(code) for code in rows if code)


async def _wp_formula_count(session, project_id: UUID) -> int:
    return int((await session.execute(text("SELECT count(*) FROM wp_formula WHERE project_id = :pid"),
                                      {"pid": project_id})).scalar_one())


def _expected_application(selected: list[str], wp_codes: list[str]) -> tuple[dict[str, Any], list[str]]:
    """测试内独立算预设套用：本次实际执行的勾选范围（按勾选顺序）的 page_keys —— ``report`` = 预设库 ``build_preset_index()`` 里
    全部 ``report:`` 键（排序）、``workpaper:<循环>`` = ``workpaper:<本项目 wp_index 里该循环的编码>`` —— 交纯映射
    ``DraftRefreshService().build_preset_draft_units`` 取 ``to_dict()``。返回（预设套用, page_keys）。"""
    index = build_preset_index()
    page_keys: list[str] = []
    for scope in selected:
        if scope == "report":
            page_keys += sorted(key for key in index if key.startswith("report:"))
        elif scope.startswith("workpaper:"):
            cycle = scope.split(":", 1)[1].upper()
            page_keys += [f"workpaper:{code}" for code in wp_codes if code[:1].upper() == cycle]
    return DraftRefreshService().build_preset_draft_units(page_keys, preset_index=index).to_dict(), page_keys


def _with_workpaper(code: str) -> Prepare:
    """夹具（照 truthful）：wp_index ``code`` 一行 + 底稿一张；不建 wp_formula ⇒ coordinator 0 个 mutation、不冻结。"""
    async def prepare(session, project_id: UUID) -> None:
        await add_workpaper(session, project_id, code)
    return prepare


def _prior_audit(result_status: str) -> Prepare:
    """夹具：本项目年度一条同键（:data:`REQUEST_KEY`）的审计 —— 照模型必填列（操作者 = 夹具里的合伙人、角色 partner、scope
    ``report``、快照指纹 64 位 0 占位）+ 给定 ``result_status`` + 空 ``detail``，其余列取库默认。先 flush（成员行还在会话里待写）。"""
    async def prepare(session, project_id: UUID) -> None:
        await session.flush()
        user_id = (await session.execute(text("SELECT user_id FROM project_users WHERE project_id = :pid"),
                                         {"pid": project_id})).scalar_one()
        await session.execute(text(
            "INSERT INTO draft_refresh_audit (id, project_id, year, operator_id, operator_role, scope, tb_snapshot_hash, "
            "result_status, detail, idempotency_key) VALUES (gen_random_uuid(), :pid, :year, :uid, 'partner', 'report', "
            ":snapshot, :status, CAST(:detail AS jsonb), :key)"),
            {"pid": project_id, "year": YEAR, "uid": user_id, "snapshot": "0" * 64, "status": result_status,
             "detail": "{}", "key": REQUEST_KEY})
    return prepare


def _priors(s: Shot) -> list[tuple[str, str | None, dict[str, Any]]]:
    """请求前本项目的审计行（result_status, idempotency_key 列, detail）。"""
    return [(audit.result_status, audit.idempotency_key, audit.detail) for audit in s.audits_before]


def test_no_effect_is_reported_as_no_effect(request):
    """需求 3.3：金额变化 = 仅重算 = Draft 标记 = 0、无失败 ⇒ 路由照实报 ``no_effect``（与编排器结果对象相同），不再改报 ``success``。"""
    assert_production_path()
    case = request.node.name
    with draft_refresh_world("rs_noeff", prepare=_with_workpaper(BARE_WP)) as world:
        pid = world.project_id
        wp_formulas, wp_codes = world.run(_wp_formula_count, pid), world.run(_wp_codes, pid)
        s = _send(world, world.body([MARKER_SCOPE]), 1, case)
    presets = find_presets_for_page(f"workpaper:{BARE_WP}", index=build_preset_index())
    expected, _ = _expected_application([MARKER_SCOPE], wp_codes)
    _record(request, s, wp_formulas=wp_formulas, wp_codes=wp_codes, presets=len(presets), expected_application=expected)
    assert (wp_formulas, wp_codes, len(presets)) == (0, [BARE_WP], 0), (
        f"{case} 夹具：wp_formula {wp_formulas} 行、wp_index {wp_codes}、workpaper:{BARE_WP} 预设 {len(presets)} 条")
    assert s.status_code == 200, f"{s.tag} HTTP {s.status_code}：{s.body}"
    assert (s.body["status"], s.body["outcome"]) == ("no_effect", "no_effect"), f"{s.tag} 响应 status / outcome：{s.body}"
    assert (s.result.get("status"), s.result.get("outcome")) == ("no_effect", "no_effect"), (
        f"{s.tag} 编排器结果对象 status / outcome：{s.result}")
    assert {key: s.body[key] for key in COUNT_FIELDS} == dict.fromkeys(COUNT_FIELDS, 0), (
        f"{s.tag} 计数：{[s.body[key] for key in COUNT_FIELDS]}")
    assert (s.body["idempotent"], s.body["failures"], s.body["failed_count"]) == (False, [], 0), f"{s.tag} {s.body}"
    assert s.body["preset_application"] == expected, f"{s.tag} preset_application {s.body['preset_application']}（应 {expected}）"
    _assert_timeline(s, committed=True, executed=False, events=0)
    _assert_executed_audit(s, outcome="no_effect", scopes=[MARKER_SCOPE])


def test_idempotent_hit_with_request_key_skips_report_scope(request):
    """ADR-FHIC-08：同一请求键第 2 次命中 ⇒ 不执行任何范围（含 report）、不写入、不发事件，回放首次运行的结果与预设套用。

    两次请求之间另加一张预设库里有预设的底稿 :data:`EXTRA_WP`（不在四张表里）：本次若重算预设套用会多出它，命中仍回放首次存的
    那份（判据不空转）；另装 :func:`_lock_spy` 钉住「先取项目锁、再判定」。"""
    assert_production_path()
    case, scopes = request.node.name, ["report", MARKER_SCOPE]
    with draft_refresh_world("rs_hit", prepare=_with_workpaper(PRESET_WP)) as world, _lock_spy(world):
        pid = world.project_id
        body = world.body(scopes, idempotency_key=REQUEST_KEY)
        wp_codes, tb_start = world.run(_wp_codes, pid), world.run(trial_balance_rows, pid)
        s1 = _send(world, body, 1, case)
        tb_after_first = world.run(trial_balance_rows, pid)
        world.run(add_workpaper, pid, EXTRA_WP)
        wp_codes_later = world.run(_wp_codes, pid)
        s2 = _send(world, body, 2, case)
    expected, page_keys = _expected_application(scopes, wp_codes)
    expected_later, _ = _expected_application(scopes, wp_codes_later)
    report_pages = [key for key in page_keys if key.startswith("report:")]
    for s in (s1, s2):
        _record(request, s)
    request.node.user_properties.extend((name, str(value)) for name, value in {
        "wp_codes": wp_codes, "page_keys": page_keys, "expected_application": expected, "wp_codes_later": wp_codes_later,
        "expected_application_later": expected_later, "tb_changed_by_round1": tb_start != tb_after_first}.items())

    # ── 夹具自证：页面 = report 的 7 个预设页面 + workpaper:D0（都有预设）；第 1 次改了试算表 ⇒ 计划指纹输入已变；
    #    加了 EXTRA_WP 后重算的预设套用与首次不同 ⇒ 回放判据不空转 ──
    assert wp_codes == [PRESET_WP] and len(report_pages) == REPORT_PAGES, f"{case} 夹具：wp_index {wp_codes}、页面 {page_keys}"
    assert page_keys == [*report_pages, f"workpaper:{PRESET_WP}"] == expected["presetted_pages"], f"{case} 夹具：{expected}"
    assert expected["pending_pages"] == [] and expected["preset_count"] > 0, f"{case} 夹具：预设套用 {expected}"
    assert tb_start != tb_after_first, f"{case} 夹具：第 1 次 full_recalc 没改动复制来的试算表（命中不能证明来自请求键）"
    assert wp_codes_later == sorted([PRESET_WP, EXTRA_WP]) and expected_later["preset_count"] > expected["preset_count"], (
        f"{case} 夹具：加 {EXTRA_WP} 后 wp_index {wp_codes_later}、重算的预设套用 {expected_later}")

    # ── 第 1 次：执行（success / applied），有效键与写入键都是请求键 ──
    _assert_applied(s1, locked=True)
    new_markers = s1.new_rows("draft_marker")
    assert s1.body["draft_marked_count"] == new_markers == expected["preset_count"], (
        f"{s1.tag} draft_marked_count {s1.body['draft_marked_count']}，draft_marker 新增 {new_markers}，"
        f"预设 {expected['preset_count']}")
    assert s1.body["preset_application"] == expected, f"{s1.tag} preset_application：{s1.body['preset_application']}"
    audit1 = _assert_executed_audit(s1, outcome="applied", scopes=scopes, base=REQUEST_KEY)
    assert audit1.detail.get("preset_application") == expected, (
        f"{s1.tag} 审计存的预设套用：{audit1.detail.get('preset_application')}")

    # ── 第 2 次：命中 ──
    assert s2.status_code == 200, f"{s2.tag} HTTP {s2.status_code}：{s2.body}"
    assert (s2.body["status"], s2.body["idempotent"], s2.result.get("status")) == ("idempotent_hit", True, "idempotent_hit"), (
        f"{s2.tag} status / idempotent：{s2.body}；结果对象 {s2.result}")
    assert s2.body["run_id"] == str(audit1.id), f"{s2.tag} run_id {s2.body['run_id']} ≠ 第 1 次审计 {audit1.id}"
    replayed = ("outcome", *COUNT_FIELDS)
    assert {key: s2.body[key] for key in replayed} == {key: s1.body[key] for key in replayed}, (
        f"{s2.tag} outcome / 计数 {[s2.body[key] for key in replayed]} ≠ 第 1 次 {[s1.body[key] for key in replayed]}")
    assert (s2.body["failures"], s2.body["failed_count"]) == ([], 0), f"{s2.tag} failures：{s2.body['failures']}"
    assert s2.body["preset_application"] == s1.body["preset_application"] != expected_later, (
        f"{s2.tag} preset_application {s2.body['preset_application']} 应 = 第 1 次存的 {s1.body['preset_application']}"
        f"（≠ 本次重算 {expected_later}）")
    assert s2.body["rollback_available"] is False and ROLLBACK_WARNING in s2.body["warnings"], (
        f"{s2.tag} rollback_available {s2.body['rollback_available']}、warnings {s2.body['warnings']}")
    _assert_timeline(s2, committed=True, executed=False, events=0, locked=True)
    assert s2.changed_tables == [] and s2.new_audits == [], f"{s2.tag} 命中却改动了表：{s2.changed_tables}"


def test_executing_record_with_same_key_is_409(request):
    """ADR-FHIC-08：同一有效键的首次运行仍在执行（``executing``）⇒ 409，判定在取锁之后、任何范围执行与写入之前，不 commit。"""
    assert_production_path()
    case = request.node.name
    with draft_refresh_world("rs_busy", prepare=_prior_audit("executing")) as world, _lock_spy(world):
        s = _send(world, world.body(["report"], idempotency_key=REQUEST_KEY), 1, case)
    raw = s.body.get("detail")
    detail = raw if isinstance(raw, dict) else {}
    _record(request, s, priors=_priors(s))
    assert _priors(s) == [("executing", REQUEST_KEY, {})], f"{case} 夹具：请求前的审计 {_priors(s)}"
    assert s.status_code == 409, f"{s.tag} HTTP {s.status_code}：{s.body}"
    assert (detail.get("error_code"), detail.get("run_id")) == (IN_PROGRESS, str(s.audits_before[0].id)), (
        f"{s.tag} 409 detail：{s.body}（run_id 应为那条 executing 审计 {s.audits_before[0].id}）")
    assert isinstance(detail.get("message"), str) and CJK.search(detail["message"]), f"{s.tag} message 不是中文：{detail}"
    _assert_timeline(s, committed=False, executed=False, events=0, locked=True)
    assert s.result == {}, f"{s.tag} 409 却有编排器结果对象：{s.result}"
    assert s.changed_tables == [], f"{s.tag} 409 却改动了表：{s.changed_tables}"


def test_rolled_back_record_with_same_key_executes(request):
    """ADR-FHIC-08：同键最近一条是 ``rolled_back`` ⇒ 照常执行；K 已被占用 ⇒ 写入键 = ``write_key(K, 1)``，有效键仍记 K。"""
    assert_production_path()
    case, occupied_key = request.node.name, write_key(REQUEST_KEY, 1)
    with draft_refresh_world("rs_rolled", prepare=_prior_audit("rolled_back")) as world:
        s = _send(world, world.body(["report"], idempotency_key=REQUEST_KEY), 1, case)
    _record(request, s, priors=_priors(s), write_key_1=occupied_key)
    assert _priors(s) == [("rolled_back", REQUEST_KEY, {})], f"{case} 夹具：请求前的审计 {_priors(s)}"
    _assert_applied(s)
    audit = _assert_executed_audit(s, outcome="applied", scopes=["report"], base=REQUEST_KEY, column=occupied_key)
    assert audit.idempotency_key != REQUEST_KEY, f"{s.tag} 写入键 {audit.idempotency_key!r} 与已占用的请求键相同"
    prior = s.audits_before[0]
    assert [a.raw for a in s.audits_after if a.id == prior.id] == [prior.raw], f"{s.tag} 那条 rolled_back 审计被改动"


def test_scope_trace_ignores_unknown_scope(request, caplog):
    """需求 3.3 scope 留痕：未知范围忽略、重复去重 ⇒ ``detail.scopes == ["report"]``、报表范围只执行一次，预设套用只按 report 算。
    🔴 照实：未知范围只落编排器日志（``_plan`` 里 ``logger.warning``，恰 1 条、含 ``'bogus_scope'``），不进响应 ``warnings``；
    响应 ``scopes`` 原样回显请求（只记 junit）。"""
    assert_production_path()
    case, requested = request.node.name, ["report", UNKNOWN_SCOPE, "report"]
    with caplog.at_level(logging.WARNING, logger=ORCHESTRATOR_LOGGER):
        with draft_refresh_world("rs_scope") as world:
            wp_codes = world.run(_wp_codes, world.project_id)
            s = _send(world, world.body(requested), 1, case)
    logged = [record.getMessage() for record in caplog.records
              if record.name == ORCHESTRATOR_LOGGER and UNKNOWN_SCOPE in record.getMessage()]
    expected, page_keys = _expected_application(["report"], wp_codes)
    _record(request, s, requested=requested, unknown_scope_logs=logged, expected_application=expected)
    assert wp_codes == [] and len(page_keys) == REPORT_PAGES, f"{case} 夹具：wp_index {wp_codes}、页面 {page_keys}"
    _assert_applied(s)
    _assert_executed_audit(s, outcome="applied", scopes=["report"])
    assert s.body["preset_application"] == expected, f"{s.tag} preset_application {s.body['preset_application']}（应 {expected}）"
    assert not any(UNKNOWN_SCOPE in warning for warning in s.body["warnings"]), (
        f"{s.tag} warnings 提到了未知范围（与现状不符：改本用例 docstring 与断言）：{s.body['warnings']}")
    assert len(logged) == 1 and f"'{UNKNOWN_SCOPE}'" in logged[0], f"{s.tag} 编排器关于未知范围的日志：{logged}"
