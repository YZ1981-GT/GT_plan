"""Draft Refresh 如实报告（spec formula-hub-integrity-closure 任务 20 第一段 B-1a / B-1b-1 / B-1b-2；需求 3.1~3.4；ADR-FHIC-08）。

B-1a（报表范围三态）：同一请求（只勾 ``report``、不带请求键、默认 ``all_or_nothing``）连发三次，逐次钉住：

1. 第 1 次 ``success`` / ``applied``：``applied_count`` = 本次 before → after 金额变化的成功行数、``recomputed_count`` = 金额未变的
   成功行数（两次 ``financial_report`` 快照独立数出，金额规范到分），``affected_count = applied + recomputed``；有公式的行 after =
   金标准（``gold_report_evaluator``：生成时公式 = 金标准生效公式、差 ≤ 0.005）；事件恰 2 条（``REPORT_ROW_CHANGED`` /
   ``REPORTS_UPDATED`` 各一）、都经 ``publish_immediate`` 且在路由 commit 之后，``changed_row_codes`` = 金额变化行的行次（按生成
   顺序去重、前 100 个），``report_types`` = 本次生成的报表类型（不含 coverage_stats / debug_info）；审计 +1，``detail`` 带
   outcome、四个计数、``scopes == ["report"]``，``idempotency_base`` = ``plan_fp`` = 审计 ``idempotency_key`` 列。
2. 第 2 次 ``recomputed``：金额变化 0、仅重算 > 0（独立数出），报表金额列与第 1 次后相同，0 事件，审计 +1，有效键 = 新的
   ``plan_fp``（第 1 次的指纹按运行前状态取，``full_recalc`` 重算了复制来的试算表 ⇒ 第 2 次输入已变；编排方决定 ①），试算表不变。
3. 第 3 次 ``idempotent_hit``：``run_id`` = 第 2 次的审计 id、outcome 与计数 = 第 2 次；``full_recalc`` / ``generate_all_reports``
   0 次调用，``financial_report`` 全行与审计行逐字节不变，试算表不变，0 事件。
三次都是 200、恰 1 次 commit、0 次 rollback、``rollback_available`` 为 false 且 warnings 含「报表可重新生成，不支持一键回滚」；第 1、2
次两个执行函数各调用 1 次、都在 commit 之前。

夹具自证（判据不空转）：项目准则 = 医疗器械的准则，且其余三个准则的定义都与之不同（报表行集合 = 本准则定义行集合即钉住「按项目
真实准则」）；试算表 ``1002`` 带一笔已发布底稿调整（``wp_adjustment``，``full_recalc`` 保留它），至少一行公式在审定 / 未审口径下
金标准不同（钉住「审定模式」）；金标准非零的行 > 0；每张报表的行号不重复（「前 100 个」的生成顺序可独立复原）；第 1 次的
``full_recalc`` 确实改了复制来的试算表（第 2 次因此执行而不是命中）。三次的状态、计数、事件数、耗时经 ``user_properties`` 写进
junit。世界与时间线见 ``_draft_refresh_world``。

B-1b-1（状态表其余四态，每态一个世界）：

- ``draft_marked`` / ``no_effect``：只勾 ``workpaper:D``（``RefreshScopeDiscovery`` 按循环常量必发现）；夹具建 wp_index 一行（``D0``：
  预设库有预设 / ``D0-1``：没有）+ 一张 prefill_stale=False 的底稿、不建 ``wp_formula`` ⇒ coordinator 0 个 mutation（不冻结），走
  marker-only 路径。前者 Draft 标记数 = 本次新增的 ``draft_marker`` 行数（表里独立数出）= 预设条数 > 0，后者三个数都为 0；两者都
  不调 ``trigger_recalc``、``prefill_stale`` 为真的底稿数不变（需求 3.4）、0 事件、审计 +1。用例末尾真调一次 ``trigger_recalc``：
  同一张底稿被标过时（判据不空转）。
- ``partial`` / ``failed``：经项目层适配把「资产总计」（本准则有公式、不被任何行引用）换成悬空引用 ``ROW('ZZ-999')``（保存不校验，
  报表计算时失败），只勾 ``report``。``partial_success`` 模式 ⇒ 提交，failures 恰为这一行（``stage=report_row``、报表类型、行次、
  中文原因 = 写库的 ``calc_error``），失败行不写 0（新行为空、标过期），其余行 = 金标准，2 条事件在 commit 之后；默认模式 ⇒
  回滚，四张表与请求前逐字节相同、0 事件、200 + 同一条 failures、四个计数如实为 0（B-1b-2 编排方决定：整体回滚后这些写入不存在，
  与服务层 all_or_nothing 失败同口径）；同一世界再按 ``partial_success`` 发一次，四张表都变了、计数照旧非 0（判据不空转）。

B-1b-2（需求 3.1「试算表重算失败 ⇒ 本范围失败、试算表不变」）：故障注在 ``full_recalc`` 的下一层 —— 第三步 ``recalc_audited`` 抛错
（前两步已 flush 写入），``full_recalc`` 仍是生产函数（解包记录包装后是开工前类上的同一个函数、注入点的调用方帧即其代码）。同一世界
依次：``partial_success`` ⇒ partial（报表预设的 Draft 标记使有效 > 0）、failures 恰一条 ``stage=trial_balance_recalc``、不生成报表、
试算表逐字节不变（注入时刻与请求前不同 ⇒ 保存点撤销了前两步）、0 事件、提交；默认模式 ⇒ failed、计数全 0、回滚、四张表逐字节不变；
撤掉注入再发 ``partial_success`` ⇒ 试算表被改动、报表按定义写满（判据不空转）。
"""
from __future__ import annotations

import inspect
import re
import sys
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal
from functools import partial
from pathlib import Path
from typing import Any
from unittest import mock
from uuid import UUID

import pytest
from sqlalchemy import text

from app.models.audit_platform_schemas import EventType
from app.services.draft_refresh_service import DraftRefreshService
from app.services.event_bus import event_bus
from app.services.formula_management.preset_library import build_preset_index, find_presets_for_page
from app.services.report_config_service import ReportConfigService
from app.services.report_freshness import CALC_VERSION
from app.services.trial_balance_service import TrialBalanceService
from tests.formula_hub import gold_report_evaluator as gold
from tests.formula_hub._draft_refresh_world import (
    JSON_TABLES,
    RESULT_KIND,
    YEAR,
    AuditRow,
    Key,
    Mark,
    ReportRow,
    World,
    add_workpaper,
    assert_production_path,
    audit_rows,
    draft_markers,
    draft_refresh_world,
    override_report_formula,
    prefill_stale_count,
    report_rows_json,
    report_states,
    rows_json,
    trial_balance_rows,
)

pytestmark = pytest.mark.pg_only

ROLLBACK_WARNING = "报表可重新生成，不支持一键回滚"
ROW_CODE_LIMIT = 100  # REPORT_ROW_CHANGED 只带前 100 个行次
TOLERANCE = Decimal("0.005")
ADJUSTED_CODE = "1002"
WP_ADJUSTMENT = Decimal("12345.67")
NON_REPORT_KEYS = {"coverage_stats", "debug_info"}
COUNT_FIELDS = ("affected_count", "applied_count", "recomputed_count", "draft_marked_count")
ROW_CHANGED, UPDATED = EventType.REPORT_ROW_CHANGED.value, EventType.REPORTS_UPDATED.value
#: B-1b-1 marker-only 范围：底稿·循环 D（循环常量里有 D ⇒ 必被发现）；PRESET_WP 在预设库里有预设、BARE_WP 没有
MARKER_SCOPE, PRESET_WP, BARE_WP = "workpaper:D", "D0", "D0-1"
#: B-1b-1 失败行：本准则有公式、不被任何 ROW / SUM_ROW 引用（改坏它只失败这一行），换成悬空行次引用
BROKEN: Key = ("balance_sheet", "BS-053")
BROKEN_NAME, BROKEN_FORMULA, DANGLING = "资产总计", "ROW('ZZ-999')", "ZZ-999"
CJK = re.compile(r"[\u4e00-\u9fff]")
FAILURE_FIELDS = ("scope", "stage", "report_type", "row_code", "error")
Reader = Callable[[Any, UUID], Awaitable[Any]]
MARKER_READERS: dict[str, Reader] = {"markers": draft_markers, "prefill_stale": prefill_stale_count}
JSON_READERS: dict[str, Reader] = {table: partial(rows_json, table=table) for table in JSON_TABLES}


@dataclass
class Round:
    n: int
    status_code: int
    body: dict[str, Any]
    marks: list[Mark]
    before: dict[Key, ReportRow]
    after: dict[Key, ReportRow]
    after_json: list[tuple[str, str]]
    audits_before: list[AuditRow]
    audits_after: list[AuditRow]
    tb_before: list[tuple[str, ...]]
    tb_after: list[tuple[str, ...]]
    #: ``_send(extra=…)`` 额外读数（名称 → 请求前 / 后的值）；B-1a 不传
    extra_before: dict[str, Any] = field(default_factory=dict)
    extra_after: dict[str, Any] = field(default_factory=dict)
    #: 断言消息前缀里的状态名（B-1b-1 每态一个世界）；B-1a 不传
    label: str = ""

    @property
    def tag(self) -> str:
        return f"{self.label} 第 {self.n} 次".strip()

    @property
    def result(self) -> dict[str, Any]:
        """编排器结果对象的 outcome / status / failures（时间线上 :data:`RESULT_KIND` 那一笔；没有则为空 dict）。"""
        found = [mark.extra for mark in self.marks if mark.kind == RESULT_KIND]
        return dict(found[-1] or {}) if found else {}

    def at(self, kind: str) -> list[int]:
        return [i for i, mark in enumerate(self.marks) if mark.kind == kind]

    @property
    def events(self) -> list[tuple[int, Mark]]:
        return [(i, mark) for i, mark in enumerate(self.marks) if mark.kind in ("publish", "publish_immediate")]

    @property
    def new_audits(self) -> list[AuditRow]:
        known = {audit.id for audit in self.audits_before}
        return [audit for audit in self.audits_after if audit.id not in known]

    def seconds(self, start: str) -> float:
        """从首个 ``start`` 标记到 ``request:end`` 的秒数（没有该标记为 -1）。"""
        first = [mark.at for mark in self.marks if mark.kind == start]
        last = [mark.at for mark in self.marks if mark.kind == "request:end"]
        return round(last[-1] - first[0], 3) if first and last else -1.0


@dataclass
class GoldCheck:
    standard: str
    production_standard: str
    source_standard: str
    same_as_other_standards: list[str]
    result: gold.GoldResult
    mode_sensitive: list[Key]
    duplicate_row_numbers: list[tuple[str, int]]
    row_numbers: dict[Key, int]
    tb_rows: int
    tb_nonzero: int


async def _publish_wp_adjustment(session, project_id: UUID) -> None:
    """一笔已发布的底稿调整（审定数 = 未审数 + 调整，``full_recalc`` 保留 ``wp_adjustment``）：审定 / 未审口径可分辨。"""
    result = await session.execute(text(
        "UPDATE trial_balance SET wp_adjustment = :adjustment WHERE project_id = :pid AND year = :year "
        "AND standard_account_code = :code AND is_deleted = false"),
        {"adjustment": WP_ADJUSTMENT, "pid": project_id, "year": YEAR, "code": ADJUSTED_CODE})
    assert result.rowcount == 1, f"夹具：复制来的试算表里 {ADJUSTED_CODE} 应恰 1 行，实际 {result.rowcount}"


async def _gold_check(session, project_id: UUID, source_id: UUID) -> GoldCheck:
    """金标准（审定口径，另算一份未审口径作对照）与准则 / 行号的自证材料；只读。"""
    standard = await gold.resolve_standard(session, project_id)
    configs = await gold.load_config_rows(session, project_id, standard)
    tb = await gold.load_tb_rows(session, project_id, YEAR)
    audited = gold.evaluate(configs, tb, standard=standard)
    unadjusted_tb = [gold.TbRow(str(code), unadjusted, opening) for code, unadjusted, opening in (await session.execute(
        text("SELECT standard_account_code, unadjusted_amount, opening_balance FROM trial_balance "
             "WHERE project_id = :pid AND year = :year AND is_deleted = false"),
        {"pid": project_id, "year": YEAR})).all()]
    unadjusted = gold.evaluate(configs, unadjusted_tb, standard=standard)
    mine = {(c.report_type, c.row_code): c.formula for c in configs}
    same = []
    for other in gold.STANDARDS:
        if other != standard and {(c.report_type, c.row_code): c.formula
                                  for c in await gold.load_config_rows(session, project_id, other)} == mine:
            same.append(other)
    with_formula = [key for key, formula in audited.formulas.items() if (formula or "").strip()]
    numbers = Counter((c.report_type, c.row_number) for c in configs)
    return GoldCheck(
        standard=standard,
        production_standard=await ReportConfigService.resolve_applicable_standard(session, project_id),
        source_standard=await ReportConfigService.resolve_applicable_standard(session, source_id),
        same_as_other_standards=same, result=audited,
        mode_sensitive=[key for key in with_formula if audited.values[key].value != unadjusted.values[key].value],
        duplicate_row_numbers=sorted(key for key, count in numbers.items() if count > 1),
        row_numbers={(c.report_type, c.row_code): c.row_number for c in configs},
        tb_rows=len(tb), tb_nonzero=sum(1 for row in tb if row.audited_amount))


def _send(world: World, body: dict[str, Any], n: int, extra: dict[str, Reader] | None = None,
          label: str = "") -> Round:
    """真发一次请求；请求前后各读一次报表行 / 审计行 / 试算表，``extra`` 的读数也各读一次（B-1a 不传 extra / label）。"""
    pid, readers = world.project_id, extra or {}
    before, audits_before, tb_before = (world.run(fn, pid) for fn in (report_states, audit_rows, trial_balance_rows))
    extra_before = {name: world.run(fn, pid) for name, fn in readers.items()}
    response, marks = world.post(body)
    return Round(n, response.status_code, response.json(), marks, before, world.run(report_states, pid),
                 world.run(report_rows_json, pid), audits_before, world.run(audit_rows, pid), tb_before,
                 world.run(trial_balance_rows, pid), extra_before,
                 {name: world.run(fn, pid) for name, fn in readers.items()}, label)


def _cents(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _classify(r: Round) -> tuple[list[Key], list[Key], list[Key]]:
    """独立分类本次的 after 行：（金额变化, 金额未变, 失败）；成功 = 无错误、未过期、计算版本为当前版本、有金额。"""
    changed: list[Key] = []
    recomputed: list[Key] = []
    failed: list[Key] = []
    for key, row in sorted(r.after.items()):
        prior = r.before.get(key)
        if row.calc_error is not None or row.is_stale or row.calc_version != CALC_VERSION or row.amount is None:
            failed.append(key)
        elif prior is None or prior.amount is None or _cents(prior.amount) != _cents(row.amount):
            changed.append(key)
        else:
            recomputed.append(key)
    return changed, recomputed, failed


def _gold_problems(result: gold.GoldResult, after: dict[Key, ReportRow],
                   exclude: frozenset[Key] = frozenset()) -> tuple[int, int, list[str]]:
    """有公式的行逐行对金标准（``exclude`` 里的行不比）：返回（比对行数, 其中金标准非零行数, 问题清单）。"""
    compared = nonzero = 0
    problems: list[str] = []
    for key, formula in sorted(result.formulas.items()):
        if not (formula or "").strip() or key in exclude:
            continue
        expected, row = result.values[key], after.get(key)
        if expected.value is None:
            problems.append(f"{key}：金标准不可算（{expected.reason}）")
        elif row is None:
            problems.append(f"{key}：报表没有这一行")
        elif (row.formula_used or "").strip() != formula.strip():
            problems.append(f"{key}：生成时公式 {row.formula_used!r} ≠ 金标准生效公式 {formula!r}")
        elif row.amount is None or abs(Decimal(row.amount) - expected.value) > TOLERANCE:
            problems.append(f"{key}：报表 {row.amount} ≠ 金标准 {expected.value}")
        else:
            compared += 1
            nonzero += expected.value != 0
    return compared, nonzero, problems


def _expected_codes(changed: list[Key], row_numbers: dict[Key, int]) -> list[str]:
    """生成顺序（报表类型序、行号）下金额变化行的行次，去重后前 100 个。"""
    ordered = sorted(changed, key=lambda key: (gold.TYPE_ORDER.index(key[0]), row_numbers[key]))
    return list(dict.fromkeys(code for _, code in ordered))[:ROW_CODE_LIMIT]


def _record(request, r: Round, **extra: Any) -> None:
    values = {"http": r.status_code, **{k: r.body.get(k) for k in ("status", "outcome", "run_id", *COUNT_FIELDS,
                                                                    "failed_count", "idempotent")},
              "event_count": len(r.events), "events": [(m.kind, m.event_type) for _, m in r.events],
              "commits": len(r.at("commit")), "rollbacks": len(r.at("rollback")),
              "seconds": r.seconds("request:start"), "after_commit_seconds": r.seconds("commit"),
              "changed_row_codes": sum(len(m.extra.get("changed_row_codes") or []) for _, m in r.events),
              "report_types": [m.extra.get("report_types") for _, m in r.events if m.event_type == UPDATED],
              "tb_changed": r.tb_before != r.tb_after,
              "full_recalc_calls": len(r.at("call:full_recalc")),
              "generate_all_reports_calls": len(r.at("call:generate_all_reports")),
              "trigger_recalc_calls": len(r.at("call:trigger_recalc")),
              "rollback_available": r.body.get("rollback_available"), "warnings": r.body.get("warnings"),
              "failures": r.body.get("failures"), "preset_application": r.body.get("preset_application"),
              "report_rows": len(r.after), "audits": len(r.audits_after), **extra}
    request.node.user_properties.extend((f"round{r.n}_{name}", str(value)) for name, value in values.items())


def _assert_common(r: Round, *, executed: bool, report: bool = True, committed: bool = True,
                   failures: bool = False, generate: bool = True) -> None:
    """``report``：本次勾选了报表范围（两个执行函数各调 1 次、不可回滚说明）；``committed``：路由恰 1 次 commit（否则恰 1 次
    rollback）；``failures``：响应应带失败（否则为空）；``generate``：走到了报表生成（试算表重算失败时为假 ⇒
    ``generate_all_reports`` 0 次）。默认值即 B-1a 报表范围三态的判据。"""
    assert r.status_code == 200, f"{r.tag} HTTP {r.status_code}：{r.body}"
    commits, rollbacks, kinds = r.at("commit"), r.at("rollback"), [m.kind for m in r.marks]
    if committed:
        assert len(commits) == 1 and rollbacks == [], f"{r.tag} 应恰 1 次 commit、0 次 rollback，时间线 {kinds}"
    else:
        assert commits == [] and len(rollbacks) == 1, f"{r.tag} 应 0 次 commit、恰 1 次 rollback，时间线 {kinds}"
    settled, settle = (commits[0], "commit") if committed else (rollbacks[0], "rollback")
    for name in ("full_recalc", "generate_all_reports"):
        calls = r.at(f"call:{name}")
        expected = 1 if executed and report and (generate or name == "full_recalc") else 0
        assert len(calls) == expected, f"{r.tag} {name} 调用 {len(calls)} 次（应 {expected}），时间线 {kinds}"
        assert all(i < settled for i in calls), f"{r.tag} {name} 在 {settle} 之后才调用，时间线 {kinds}"
    assert r.at("publish") == [], f"{r.tag} 有事件经 publish（防抖）投递，时间线 {kinds}"
    assert all(i > settled for i, _ in r.events), f"{r.tag} 有事件在 {settle} 之前投递，时间线 {kinds}"
    if failures:
        assert r.body["failures"] and r.body["failed_count"] == len(r.body["failures"]), (
            f"{r.tag} 应带失败：failures {r.body['failures'][:5]}、failed_count {r.body['failed_count']}")
    else:
        assert r.body["failures"] == [] and r.body["failed_count"] == 0, f"{r.tag} failures：{r.body['failures'][:5]}"
    assert r.body["rollback_available"] is (not report), f"{r.tag} rollback_available：{r.body['rollback_available']}"
    assert (ROLLBACK_WARNING in r.body["warnings"]) is report, f"{r.tag} warnings：{r.body['warnings']}"


def _assert_executed_audit(r: Round, outcome: str, scopes: tuple[str, ...] = ("report",)) -> AuditRow:
    assert len(r.audits_after) == len(r.audits_before) + 1 and len(r.new_audits) == 1, (
        f"{r.tag} 审计应 +1：{len(r.audits_before)} → {len(r.audits_after)}")
    audit = r.new_audits[0]
    assert str(audit.id) == r.body["run_id"], f"{r.tag} run_id {r.body['run_id']} ≠ 新审计 {audit.id}"
    detail = audit.detail
    assert {k: detail.get(k) for k in ("outcome", *COUNT_FIELDS)} == {"outcome": outcome, **{
        k: r.body[k] for k in COUNT_FIELDS}}, f"{r.tag} 审计 detail 的 outcome / 计数：{detail}"
    assert detail.get("scopes") == list(scopes), f"{r.tag} 审计 detail.scopes：{detail.get('scopes')}"
    fp = detail.get("plan_fp")
    assert isinstance(fp, str) and len(fp) == 64, f"{r.tag} 审计 detail.plan_fp：{fp!r}"
    assert detail.get("idempotency_base") == fp == audit.idempotency_key, (
        f"{r.tag} 有效键 {detail.get('idempotency_base')!r} / plan_fp {fp!r} / 列 {audit.idempotency_key!r} 应相同")
    assert audit.affected_count == r.body["affected_count"], f"{r.tag} 审计 affected_count 列 {audit.affected_count}"
    return audit


def test_report_scope_applied_then_recomputed_then_idempotent_hit(request):
    assert_production_path()
    started = time.perf_counter()
    with draft_refresh_world("truthful", prepare=_publish_wp_adjustment) as world:
        seed_seconds = time.perf_counter() - started
        body = world.body(["report"])
        r1 = _send(world, body, 1)
        gold_started = time.perf_counter()
        check = world.run(_gold_check, world.project_id, world.seeded.source_id)
        gold_seconds = time.perf_counter() - gold_started
        r2 = _send(world, body, 2)
        r3 = _send(world, body, 3)
        copied = world.seeded.copied
        handlers = {name: len(event_bus._handlers.get(EventType(name), [])) for name in (ROW_CHANGED, UPDATED)}
    rounds = (r1, r2, r3)
    split = {r.n: _classify(r) for r in rounds[:2]}
    compared, nonzero, problems = _gold_problems(check.result, r1.after)
    for r in rounds:
        rows = dict(zip(("changed_rows", "unchanged_rows", "failed_rows"), map(len, split[r.n]))) if r.n in split else {}
        _record(request, r, **rows)
    request.node.user_properties.extend((name, str(value)) for name, value in {
        "seed_seconds": round(seed_seconds, 3), "gold_seconds": round(gold_seconds, 3), "event_handlers": handlers,
        "copied": copied, "standard": check.standard, "tb_rows": check.tb_rows, "tb_nonzero_audited": check.tb_nonzero,
        "gold_compared": compared, "gold_nonzero": nonzero, "gold_mode_sensitive": len(check.mode_sensitive),
        "gold_problems": problems[:20]}.items())

    # ── 夹具自证 ──
    assert check.standard == check.production_standard == check.source_standard, (
        f"准则：金标准 {check.standard} / 生产 {check.production_standard} / 医疗器械 {check.source_standard}")
    assert check.same_as_other_standards == [], f"夹具空转：准则 {check.standard} 与 {check.same_as_other_standards} 定义相同"
    assert check.result.unrecognized == [], check.result.unrecognized
    assert check.duplicate_row_numbers == [], f"同一张报表有重复行号：{check.duplicate_row_numbers}"
    assert check.mode_sensitive, "夹具空转：审定 / 未审口径下金标准没有一行不同"
    assert r1.tb_after != r1.tb_before, "夹具：第 1 次 full_recalc 没有改动复制来的试算表（第 2 次的计划指纹输入将不变）"

    # ── 第 1 次：applied ──
    changed, recomputed, failed = split[1]
    _assert_common(r1, executed=True)
    assert (r1.body["status"], r1.body["outcome"]) == ("success", "applied"), f"第 1 次 status / outcome：{r1.body}"
    assert failed == [], f"第 1 次有失败 / 过期行：{failed[:10]}"
    assert (r1.body["applied_count"], r1.body["recomputed_count"]) == (len(changed), len(recomputed)) and changed, (
        f"第 1 次 applied / recomputed {r1.body['applied_count']} / {r1.body['recomputed_count']}，独立数出 "
        f"{len(changed)} / {len(recomputed)}")
    assert r1.body["affected_count"] == r1.body["applied_count"] + r1.body["recomputed_count"], r1.body
    assert r1.body["idempotent"] is False, r1.body
    assert set(r1.after) == set(check.result.formulas), (
        f"第 1 次报表行集合 ≠ 本准则定义：多 {sorted(set(r1.after) - set(check.result.formulas))[:5]} "
        f"少 {sorted(set(check.result.formulas) - set(r1.after))[:5]}")
    assert problems == [] and compared > 0 and nonzero > 0, f"第 1 次金标准：比对 {compared} 非零 {nonzero}，{problems[:10]}"
    assert len(r1.events) == 2 and Counter(m.event_type for _, m in r1.events) == Counter([ROW_CHANGED, UPDATED]), (
        f"第 1 次事件：{[(m.kind, m.event_type) for _, m in r1.events]}")
    events = {m.event_type: m for _, m in r1.events}
    assert all((m.project_id, m.year) == (str(world.project_id), YEAR) for m in events.values()), events
    codes = events[ROW_CHANGED].extra.get("changed_row_codes")
    assert codes == _expected_codes(changed, check.row_numbers), (
        f"第 1 次 changed_row_codes（{len(codes or [])} 个）：{(codes or [])[:5]}…，应为 "
        f"{_expected_codes(changed, check.row_numbers)[:5]}…")
    report_types = events[UPDATED].extra.get("report_types") or []
    assert sorted(report_types) == sorted({rt for rt, _ in r1.after}) and not NON_REPORT_KEYS & set(report_types), (
        f"第 1 次 report_types：{report_types}")
    audit1 = _assert_executed_audit(r1, "applied")

    # ── 第 2 次：recomputed ──
    changed, recomputed, failed = split[2]
    _assert_common(r2, executed=True)
    assert (r2.body["status"], r2.body["outcome"]) == ("recomputed", "recomputed"), f"第 2 次 status / outcome：{r2.body}"
    assert failed == [] and changed == [], f"第 2 次失败 {failed[:5]} / 金额变化 {changed[:5]}"
    assert r2.body["applied_count"] == 0 and r2.body["recomputed_count"] == len(recomputed) > 0, (
        f"第 2 次 applied / recomputed {r2.body['applied_count']} / {r2.body['recomputed_count']}，独立数出未变 "
        f"{len(recomputed)}")
    assert r2.body["affected_count"] == r2.body["recomputed_count"] and r2.body["idempotent"] is False, r2.body
    amounts = {r.n: {key: (row.amount, row.prior) for key, row in r.after.items()} for r in (r1, r2)}
    assert amounts[2] == amounts[1], "第 2 次报表金额列与第 1 次后不同"
    assert r2.tb_before == r2.tb_after == r1.tb_after, "第 2 次 full_recalc 又改动了试算表（重算不幂等）"
    assert r2.events == [], f"第 2 次事件：{[(m.kind, m.event_type) for _, m in r2.events]}"
    audit2 = _assert_executed_audit(r2, "recomputed")
    assert audit2.detail["plan_fp"] != audit1.detail["plan_fp"], "第 2 次 plan_fp 与第 1 次相同（应按新输入重算）"

    # ── 第 3 次：idempotent_hit ──
    _assert_common(r3, executed=False)
    assert (r3.body["status"], r3.body["outcome"], r3.body["idempotent"]) == ("idempotent_hit", "recomputed", True), (
        f"第 3 次 status / outcome / idempotent：{r3.body}")
    assert r3.body["run_id"] == str(audit2.id), f"第 3 次 run_id {r3.body['run_id']} ≠ 第 2 次审计 {audit2.id}"
    assert {k: r3.body[k] for k in COUNT_FIELDS} == {k: r2.body[k] for k in COUNT_FIELDS}, (
        f"第 3 次计数 {[r3.body[k] for k in COUNT_FIELDS]} ≠ 第 2 次 {[r2.body[k] for k in COUNT_FIELDS]}")
    assert r3.after_json == r2.after_json, "第 3 次后 financial_report 与第 2 次后不是逐字节相同"
    assert r3.tb_before == r3.tb_after == r2.tb_after, "第 3 次（命中）改动了试算表"
    assert [a.raw for a in r3.audits_after] == [a.raw for a in r2.audits_after], "第 3 次改动了审计行"
    assert r3.events == [], f"第 3 次事件：{[(m.kind, m.event_type) for _, m in r3.events]}"


# ═══════════════════════════════════════════════════════════════════════
# B-1b-1：状态表其余四态（draft_marked / no_effect / partial / failed），每态一个世界
# ═══════════════════════════════════════════════════════════════════════
def _with_workpaper(code: str):
    """夹具：wp_index ``code`` 一行 + prefill_stale=False 的底稿一张；不建 wp_formula ⇒ coordinator 0 个 mutation、不冻结。"""
    async def prepare(session, project_id: UUID) -> None:
        await add_workpaper(session, project_id, code)
    return prepare


async def _break_row(session, project_id: UUID) -> None:
    """夹具：经项目层适配把失败行的公式换成悬空行次引用（只写本项目行，准则行不动）。"""
    await override_report_formula(session, project_id, *BROKEN, BROKEN_FORMULA, BROKEN_NAME)


async def _wp_formula_count(session, project_id: UUID) -> int:
    return int((await session.execute(text("SELECT count(*) FROM wp_formula WHERE project_id = :pid"),
                                      {"pid": project_id})).scalar_one())


async def _trigger_recalc(session, project_id: UUID) -> int:
    return await DraftRefreshService().trigger_recalc(session, project_id=project_id)


def _new_markers(r: Round) -> list[tuple[str, str, str | None]]:
    known = set(r.extra_before["markers"])
    return [marker for marker in r.extra_after["markers"] if marker not in known]


def _marker_only(request, purpose: str, wp_code: str, label: str) -> tuple[Round, dict[str, Any]]:
    """只勾 MARKER_SCOPE 发一次请求，末尾在同一世界真调一次 ``trigger_recalc``；断言 marker-only 共同判据（需求 3.4）。"""
    assert_production_path()
    presets = find_presets_for_page(f"workpaper:{wp_code}", index=build_preset_index())
    with draft_refresh_world(purpose, prepare=_with_workpaper(wp_code)) as world:
        pid = world.project_id
        wp_formulas = world.run(_wp_formula_count, pid)
        r = _send(world, world.body([MARKER_SCOPE]), 1, extra=MARKER_READERS, label=label)
        start = len(world.recorder.timeline)
        triggered = world.run(_trigger_recalc, pid)
        facts = {"presets": presets, "wp_formulas": wp_formulas, "triggered": triggered,
                 "trigger_marks": [mark.kind for mark in world.recorder.since(start)],
                 "stale_after_trigger": world.run(prefill_stale_count, pid)}
    _record(request, r, markers_before=len(r.extra_before["markers"]), markers_new=len(_new_markers(r)),
            prefill_stale_before=r.extra_before["prefill_stale"], prefill_stale_after=r.extra_after["prefill_stale"],
            presets=len(presets), wp_formulas=wp_formulas, trigger_recalc_direct=triggered,
            trigger_marks=facts["trigger_marks"], prefill_stale_after_trigger=facts["stale_after_trigger"],
            result=r.result)
    assert wp_formulas == 0, f"{r.tag} 夹具：本项目 wp_formula {wp_formulas} 行（计划会含 Runtime mutation、被冻结）"
    _assert_common(r, executed=True, report=False)
    assert r.at("call:trigger_recalc") == [], f"{r.tag} marker-only 调了 trigger_recalc：{[m.kind for m in r.marks]}"
    assert r.extra_before["prefill_stale"] == r.extra_after["prefill_stale"] == 0, (
        f"{r.tag} prefill_stale 为真的底稿 {r.extra_before['prefill_stale']} → {r.extra_after['prefill_stale']}")
    assert r.events == [], f"{r.tag} 事件：{[(m.kind, m.event_type) for _, m in r.events]}"
    assert r.result.get("outcome") == r.body["outcome"], f"{r.tag} 结果对象 outcome {r.result} ≠ 响应 {r.body['outcome']}"
    # 判据不空转：同一张底稿真调 trigger_recalc 会被标过时，包装也确实记到了这次调用
    assert (triggered, facts["stale_after_trigger"], facts["trigger_marks"]) == (1, 1, ["call:trigger_recalc"]), (
        f"{r.tag} 夹具空转：真调 trigger_recalc 标过时 {triggered} 张、之后 prefill_stale 为真 "
        f"{facts['stale_after_trigger']} 张、时间线 {facts['trigger_marks']}")
    return r, facts


def test_marker_only_scope_draft_marked_without_stale(request):
    """需求 3.2「draft_marked」+ 3.4：金额变化 = 仅重算 = 0、Draft 标记 > 0 ⇒ draft_marked；不调 trigger_recalc、不标过时。"""
    r, facts = _marker_only(request, "marked", PRESET_WP, "draft_marked")
    new, presets = _new_markers(r), facts["presets"]
    assert presets, f"{r.tag} 夹具空转：预设库里 workpaper:{PRESET_WP} 没有预设"
    assert (r.body["status"], r.body["outcome"]) == ("draft_marked", "draft_marked"), f"{r.tag} status / outcome：{r.body}"
    assert [r.body[k] for k in ("affected_count", "applied_count", "recomputed_count")] == [0, 0, 0], (
        f"{r.tag} affected / applied / recomputed：{[r.body[k] for k in COUNT_FIELDS]}")
    assert r.body["draft_marked_count"] == len(new) == len(presets) > 0, (
        f"{r.tag} draft_marked_count {r.body['draft_marked_count']}，draft_marker 新增 {len(new)}，预设 {len(presets)}")
    assert {scope for scope, _, _ in new} == {f"workpaper:{PRESET_WP}:{p.target_cell}" for p in presets}, (
        f"{r.tag} 新增标记的单元：{sorted(scope for scope, _, _ in new)[:5]}")
    assert all((state, refresh) == ("draft", r.body["run_id"]) for _, state, refresh in new), f"{r.tag} 标记：{new[:3]}"
    assert r.body["preset_application"] == {"preset_count": len(presets), "presetted_pages": [f"workpaper:{PRESET_WP}"],
                                            "pending_pages": []}, f"{r.tag} preset_application：{r.body['preset_application']}"
    audit = _assert_executed_audit(r, "draft_marked", scopes=(MARKER_SCOPE,))
    assert audit.detail.get("stale_marked_count") == 0, f"{r.tag} 审计 stale_marked_count：{audit.detail}"


def test_marker_only_scope_without_presets_is_no_effect(request):
    """需求 3.2「no_effect」：三者都为 0、无失败 ⇒ status / outcome 都是 no_effect（路由不再报成 success）。"""
    r, facts = _marker_only(request, "noeffect", BARE_WP, "no_effect")
    assert facts["presets"] == [], f"{r.tag} 夹具：预设库里 workpaper:{BARE_WP} 有预设 {len(facts['presets'])} 条"
    assert (r.body["status"], r.body["outcome"]) == ("no_effect", "no_effect"), f"{r.tag} status / outcome：{r.body}"
    assert {k: r.body[k] for k in COUNT_FIELDS} == dict.fromkeys(COUNT_FIELDS, 0), (
        f"{r.tag} 计数：{[r.body[k] for k in COUNT_FIELDS]}")
    assert _new_markers(r) == [] and r.extra_after["markers"] == r.extra_before["markers"], f"{r.tag} 打了 Draft 标记"
    assert r.body["preset_application"] == {"preset_count": 0, "presetted_pages": [],
                                            "pending_pages": [f"workpaper:{BARE_WP}"]}, (
        f"{r.tag} preset_application：{r.body['preset_application']}")
    audit = _assert_executed_audit(r, "no_effect", scopes=(MARKER_SCOPE,))
    assert audit.detail.get("stale_marked_count") == 0, f"{r.tag} 审计 stale_marked_count：{audit.detail}"


@dataclass
class BrokenFacts:
    """失败行夹具的自证材料（请求后读、只读）。"""

    standard: str
    standard_rows: list[tuple[str | None, str | None]]  # 准则行（未删）的（公式, 行名）
    project_formulas: list[str | None]  # 本项目行（project:<项目>）的公式
    effective: gold.GoldResult  # 生效定义（含本项目行）× 请求后试算表
    restored: gold.GoldResult  # 同上，失败行换回准则公式（自证「本来能算」）
    row_numbers: dict[Key, int]

    @property
    def uncomputable(self) -> list[Key]:
        return sorted(key for key, formula in self.effective.formulas.items()
                      if (formula or "").strip() and self.effective.values[key].value is None)


async def _broken_facts(session, project_id: UUID) -> BrokenFacts:
    standard = await gold.resolve_standard(session, project_id)
    configs = await gold.load_config_rows(session, project_id, standard)
    tb = await gold.load_tb_rows(session, project_id, YEAR)
    rows: dict[str, list[tuple[Any, ...]]] = {}
    for name, applicable in (("standard", standard), ("project", f"project:{project_id}")):
        rows[name] = [tuple(row) for row in (await session.execute(text(
            "SELECT formula, row_name FROM report_config WHERE applicable_standard = :std AND report_type::text = :rt "
            "AND row_code = :rc AND is_deleted = false"), {"std": applicable, "rt": BROKEN[0], "rc": BROKEN[1]})).all()]
    original = rows["standard"][0][0] if rows["standard"] else None
    restored = [replace(c, formula=original) if (c.report_type, c.row_code) == BROKEN else c for c in configs]
    return BrokenFacts(standard, rows["standard"], [formula for formula, _ in rows["project"]],
                       gold.evaluate(configs, tb, standard=standard), gold.evaluate(restored, tb, standard=standard),
                       {(c.report_type, c.row_code): c.row_number for c in configs})


def _assert_broken_fixture(facts: BrokenFacts, tag: str) -> None:
    """失败行：准则行有公式、行名对得上且未被改动；本项目行恰为悬空引用；换回准则公式能算；金标准独立得出只有这一行算不出。"""
    standard_formula = (facts.standard_rows[0][0] or "").strip() if len(facts.standard_rows) == 1 else ""
    assert standard_formula not in ("", BROKEN_FORMULA) and facts.standard_rows[0][1] == BROKEN_NAME, (
        f"{tag} 夹具：准则 {facts.standard} 的 {BROKEN} 行：{facts.standard_rows}")
    assert facts.project_formulas == [BROKEN_FORMULA], f"{tag} 夹具：本项目行公式 {facts.project_formulas}"
    assert facts.restored.values[BROKEN].value is not None, (
        f"{tag} 夹具：换回准则公式后金标准仍算不出（{facts.restored.values[BROKEN].reason}）")
    assert facts.uncomputable == [BROKEN] and DANGLING in (facts.effective.values[BROKEN].reason or ""), (
        f"{tag} 夹具：金标准算不出的行 {facts.uncomputable[:5]}（{facts.effective.values[BROKEN].reason}）")


def _assert_broken_failure(r: Round, calc_error: str | None) -> None:
    """failures 恰为失败行：结果对象带 stage=report_row / 报表类型 / 行次 / 中文原因，响应字符串 = 结果对象的 error。"""
    expected = f"报表 {BROKEN[0]} 行 {BROKEN[1]} 计算失败：{calc_error}"
    got = [{k: f.get(k) for k in FAILURE_FIELDS} for f in r.result.get("failures") or []]
    assert got == [{"scope": "report", "stage": "report_row", "report_type": BROKEN[0], "row_code": BROKEN[1],
                    "error": expected}], f"{r.tag} 结果对象 failures：{r.result.get('failures')}"
    assert r.body["failures"] == [expected] and r.body["failed_count"] == 1, f"{r.tag} 响应 failures：{r.body['failures']}"
    assert calc_error and CJK.search(calc_error) and DANGLING in calc_error, f"{r.tag} 失败原因不可读：{calc_error!r}"


def test_report_scope_partial_success_keeps_failed_row_and_commits_rest(request):
    """需求 3.2「partial」：partial_success 模式、有失败且有效 > 0 ⇒ 提交；失败行不写 0、原因可读，其余行照常写入、事件照发。"""
    assert_production_path()
    with draft_refresh_world("partial", prepare=_break_row) as world:
        r = _send(world, world.body(["report"], transaction_mode="partial_success"), 1,
                  extra={"markers": draft_markers}, label="partial")
        facts = world.run(_broken_facts, world.project_id)
    changed, recomputed, failed = _classify(r)
    row, new = r.after.get(BROKEN), _new_markers(r)
    compared, nonzero, problems = _gold_problems(facts.effective, r.after, exclude=frozenset({BROKEN}))
    _record(request, r, changed_rows=len(changed), unchanged_rows=len(recomputed), failed_rows=len(failed),
            failed_keys=failed, broken_row=row, result=r.result, markers_new=len(new), gold_compared=compared,
            gold_nonzero=nonzero, gold_problems=problems[:20], gold_uncomputable=facts.uncomputable)
    _assert_broken_fixture(facts, r.tag)
    _assert_common(r, executed=True, failures=True)
    assert (r.body["status"], r.body["outcome"], r.result.get("outcome")) == ("partial_success", "partial", "partial"), (
        f"{r.tag} status / outcome：{r.body} / 结果对象 {r.result}")
    assert failed == [BROKEN], f"{r.tag} 失败 / 过期行（两次快照独立分类）：{failed[:10]}"
    assert row is not None and row.amount is None and row.is_stale and row.formula_used is None, (
        f"{r.tag} 失败行写库：{row}（新行应为空、标过期，不写 0）")
    _assert_broken_failure(r, row.calc_error)
    assert (r.body["applied_count"], r.body["recomputed_count"]) == (len(changed), len(recomputed)) and changed, (
        f"{r.tag} applied / recomputed {r.body['applied_count']} / {r.body['recomputed_count']}，独立数出 "
        f"{len(changed)} / {len(recomputed)}")
    assert r.body["affected_count"] == r.body["applied_count"] + r.body["recomputed_count"], r.body
    assert set(r.after) == set(facts.effective.formulas), f"{r.tag} 报表行集合 ≠ 生效定义"
    assert problems == [] and compared > 0 and nonzero > 0, f"{r.tag} 其余行对金标准：比对 {compared} 非零 {nonzero}，{problems[:10]}"
    assert r.body["draft_marked_count"] == len(new) > 0, (
        f"{r.tag} draft_marked_count {r.body['draft_marked_count']}，draft_marker 新增 {len(new)}")
    assert len(r.events) == 2 and Counter(m.event_type for _, m in r.events) == Counter([ROW_CHANGED, UPDATED]), (
        f"{r.tag} 事件：{[(m.kind, m.event_type) for _, m in r.events]}")
    codes = next(m for _, m in r.events if m.event_type == ROW_CHANGED).extra.get("changed_row_codes") or []
    assert codes == _expected_codes(changed, facts.row_numbers) and BROKEN[1] not in codes, (
        f"{r.tag} changed_row_codes（{len(codes)} 个）：{codes[:5]}…")
    _assert_executed_audit(r, "partial")


def test_report_scope_all_or_nothing_failure_rolls_back_everything(request):
    """需求 3.2「failed」/ 3.3：默认 all_or_nothing、同一个失败行 ⇒ 路由回滚，四张表与请求前逐字节相同、0 事件、200 + failures、
    四个计数如实为 0。"""
    assert_production_path()
    with draft_refresh_world("failed", prepare=_break_row) as world:
        r1 = _send(world, world.body(["report"]), 1, extra=JSON_READERS, label="failed")
        # 判据不空转：同一世界、同一失败行，改 partial_success 再发一次 ⇒ 提交，四张表都有写入
        r2 = _send(world, world.body(["report"], transaction_mode="partial_success"), 2, extra=JSON_READERS,
                   label="failed 自证（partial_success）")
        facts = world.run(_broken_facts, world.project_id)
    row = r2.after.get(BROKEN)
    calc_error = row.calc_error if row is not None else None
    identical = {table: r1.extra_before[table] == r1.extra_after[table] for table in JSON_TABLES}
    written = {table: r2.extra_after[table] != r1.extra_before[table] for table in JSON_TABLES}
    _record(request, r1, tables_before={t: len(r1.extra_before[t]) for t in JSON_TABLES},
            tables_after={t: len(r1.extra_after[t]) for t in JSON_TABLES}, identical=identical, result=r1.result)
    _record(request, r2, tables_after={t: len(r2.extra_after[t]) for t in JSON_TABLES}, written=written,
            broken_row=row, result=r2.result)
    _assert_broken_fixture(facts, r1.tag)
    _assert_common(r1, executed=True, committed=False, failures=True)
    assert (r1.body["status"], r1.body["outcome"], r1.result.get("outcome")) == ("failed", "failed", "failed"), (
        f"{r1.tag} status / outcome：{r1.body} / 结果对象 {r1.result}")
    _assert_broken_failure(r1, calc_error)
    assert {k: r1.body[k] for k in COUNT_FIELDS} == dict.fromkeys(COUNT_FIELDS, 0), (
        f"{r1.tag} 整体回滚后计数应如实为 0：{[r1.body[k] for k in COUNT_FIELDS]}")
    assert all(identical.values()), f"{r1.tag} 回滚后与请求前不是逐字节相同的表：{[t for t, ok in identical.items() if not ok]}"
    assert r1.events == [], f"{r1.tag} 事件：{[(m.kind, m.event_type) for _, m in r1.events]}"
    _assert_common(r2, executed=True, failures=True)
    assert (r2.body["status"], r2.body["outcome"]) == ("partial_success", "partial"), f"{r2.tag} status / outcome：{r2.body}"
    _assert_broken_failure(r2, calc_error)
    changed, recomputed, _ = _classify(r2)
    assert (r2.body["applied_count"], r2.body["recomputed_count"]) == (len(changed), len(recomputed)) and changed, (
        f"{r2.tag} applied / recomputed {r2.body['applied_count']} / {r2.body['recomputed_count']}，独立数出 "
        f"{len(changed)} / {len(recomputed)}")
    assert r2.body["draft_marked_count"] > 0 and r2.body["affected_count"] == len(changed) + len(recomputed), (
        f"{r2.tag} 计数应照旧非 0：{[r2.body[k] for k in COUNT_FIELDS]}")
    assert all(written.values()), f"{r2.tag} 判据空转：提交后仍与第 1 次请求前相同的表：{[t for t, ok in written.items() if not ok]}"


# ═══════════════════════════════════════════════════════════════════════
# B-1b-2：试算表重算失败（需求 3.1），故障注在 full_recalc 的下一层
# ═══════════════════════════════════════════════════════════════════════
INJECTED = "注入故障：审定数重算失败"
INJECT_KIND = "inject:recalc_audited"
TB_FAILURE = {"scope": "report", "stage": "trial_balance_recalc", "error": f"试算表重算失败：RuntimeError: {INJECTED}"}
TB_READERS: dict[str, Reader] = {**JSON_READERS, "markers": draft_markers}


def _is_production(fn: Any, qualname: str) -> bool:
    """``fn`` 是生产模块 ``app/services/trial_balance_service.py`` 里定义的 ``qualname`` 本身（不是任何包装 / 替身）。"""
    filename = Path(getattr(getattr(fn, "__code__", None), "co_filename", "")).as_posix()
    return (getattr(fn, "__module__", None) == TrialBalanceService.__module__ and getattr(fn, "__qualname__", None) == qualname
            and not hasattr(fn, "__wrapped__") and filename.endswith("app/services/trial_balance_service.py"))


@contextmanager
def _failing_recalc_audited(world: World, seen: list[dict[str, Any]]) -> Iterator[None]:
    """把 ``TrialBalanceService.recalc_audited``（``full_recalc`` 的第三步）换成抛错（中文消息）的函数，退出时还原；``full_recalc``
    本身不动。抛错前记下调用方帧的代码对象与此刻本项目试算表全行（前两步已 flush 的写入），并在时间线上记 :data:`INJECT_KIND`。"""
    async def failing(self, project_id, year, *args, **kwargs):
        caller = sys._getframe(1).f_code  # 第一次执行到这里时的调用方 = 正在 await 本协程的 full_recalc
        seen.append({"caller": caller, "tb": await rows_json(self.db, project_id, "trial_balance")})
        world.recorder.timeline.append(Mark(INJECT_KIND))
        raise RuntimeError(INJECTED)

    with mock.patch.object(TrialBalanceService, "recalc_audited", failing):
        yield


async def _definition_keys(session, project_id: UUID) -> set[Key]:
    standard = await gold.resolve_standard(session, project_id)
    return {(c.report_type, c.row_code) for c in await gold.load_config_rows(session, project_id, standard)}


def _assert_tb_failure(r: Round) -> None:
    """failures 恰一条 ``stage=trial_balance_recalc``（结果对象逐字段、响应 = 其 error），原因是中文且含注入消息；不生成报表、0 事件；
    注入点在 ``full_recalc`` 之后、提交 / 回滚之前。"""
    assert r.result.get("failures") == [TB_FAILURE], f"{r.tag} 结果对象 failures：{r.result.get('failures')}"
    assert r.body["failures"] == [TB_FAILURE["error"]] and r.body["failed_count"] == 1, f"{r.tag} 响应 failures：{r.body}"
    assert CJK.search(r.body["failures"][0]) and INJECTED in r.body["failures"][0], f"{r.tag} 原因：{r.body['failures']}"
    injected, recalc = r.at(INJECT_KIND), r.at("call:full_recalc")
    settled = (r.at("commit") or r.at("rollback") or [len(r.marks)])[0]
    assert len(injected) == 1 and recalc[0] < injected[0] < settled, f"{r.tag} 时间线：{[m.kind for m in r.marks]}"
    assert r.events == [], f"{r.tag} 事件：{[(m.kind, m.event_type) for _, m in r.events]}"
    assert r.extra_before["financial_report"] == r.extra_after["financial_report"] == [], (
        f"{r.tag} 报表行 {len(r.extra_before['financial_report'])} → {len(r.extra_after['financial_report'])}（应不生成）")


def test_report_scope_trial_balance_recalc_failure(request):
    """需求 3.1：试算表重算失败 ⇒ 报表范围失败、试算表不变、不生成报表；partial_success 下提交其余（Draft 标记），默认模式整体回滚。"""
    assert_production_path()
    production = vars(TrialBalanceService)["full_recalc"]
    production_audited = vars(TrialBalanceService)["recalc_audited"]
    assert _is_production(production, "TrialBalanceService.full_recalc"), f"开工前 full_recalc 不是生产函数：{production!r}"
    assert _is_production(production_audited, "TrialBalanceService.recalc_audited"), repr(production_audited)
    seen: list[dict[str, Any]] = []
    with draft_refresh_world("tbfail") as world:
        with _failing_recalc_audited(world, seen):
            in_effect = inspect.unwrap(TrialBalanceService.full_recalc)
            injected_fn = vars(TrialBalanceService)["recalc_audited"]
            ra = _send(world, world.body(["report"], transaction_mode="partial_success"), 1, extra=TB_READERS,
                       label="tbfail partial")
            rb = _send(world, world.body(["report"]), 2, extra=TB_READERS, label="tbfail failed")
        restored = vars(TrialBalanceService)["recalc_audited"]
        hits_before_c = len(seen)
        rc = _send(world, world.body(["report"], transaction_mode="partial_success"), 3, extra=TB_READERS,
                   label="tbfail 自证（撤掉注入）")
        definitions = world.run(_definition_keys, world.project_id)
    mid_differs = [item["tb"] != r.extra_before["trial_balance"] for item, r in zip(seen, (ra, rb))]
    for r in (ra, rb, rc):
        _record(request, r, injected_calls=len(r.at(INJECT_KIND)), result=r.result, markers_new=len(_new_markers(r)),
                tables_before={t: len(r.extra_before[t]) for t in JSON_TABLES},
                tables_after={t: len(r.extra_after[t]) for t in JSON_TABLES},
                identical={t: r.extra_before[t] == r.extra_after[t] for t in JSON_TABLES})
    request.node.user_properties.extend((name, str(value)) for name, value in {
        "inject_hits": len(seen), "inject_callers": [item["caller"].co_qualname for item in seen],
        "tb_mid_differs_from_before": mid_differs, "definition_rows": len(definitions)}.items())

    # ── 注入点：在 full_recalc 的下一层，full_recalc 本身是生产函数 ──
    assert in_effect is production, f"注入期间生效的 full_recalc 解包后 {in_effect!r} 不是生产函数"
    assert injected_fn is not production_audited and restored is production_audited, "recalc_audited 注入 / 还原不对"
    assert len(seen) == hits_before_c == 2 and all(item["caller"] is production.__code__ for item in seen), (
        f"注入点调用方：{[item['caller'].co_qualname for item in seen]}（应是生产 full_recalc、(a)(b) 各一次）")
    assert all(mid_differs), f"夹具空转：注入时刻试算表与请求前相同（前两步没有写入）{mid_differs}"

    # ── (a) partial_success：partial，提交 Draft 标记，试算表不变 ──
    _assert_common(ra, executed=True, failures=True, generate=False)
    assert (ra.body["status"], ra.body["outcome"], ra.result.get("outcome")) == ("partial_success", "partial", "partial"), (
        f"{ra.tag} status / outcome：{ra.body} / 结果对象 {ra.result}")
    _assert_tb_failure(ra)
    assert [ra.body[k] for k in ("affected_count", "applied_count", "recomputed_count")] == [0, 0, 0], (
        f"{ra.tag} 计数：{[ra.body[k] for k in COUNT_FIELDS]}")
    assert ra.body["draft_marked_count"] == len(_new_markers(ra)) > 0, (
        f"{ra.tag} draft_marked_count {ra.body['draft_marked_count']}，draft_marker 新增 {len(_new_markers(ra))}")
    assert ra.extra_after["trial_balance"] == ra.extra_before["trial_balance"], f"{ra.tag} 试算表与请求前不是逐字节相同"
    _assert_executed_audit(ra, "partial")

    # ── (b) 默认 all_or_nothing：failed，计数全 0，整体回滚 ──
    _assert_common(rb, executed=True, committed=False, failures=True, generate=False)
    assert (rb.body["status"], rb.body["outcome"], rb.result.get("outcome")) == ("failed", "failed", "failed"), (
        f"{rb.tag} status / outcome：{rb.body} / 结果对象 {rb.result}")
    _assert_tb_failure(rb)
    assert {k: rb.body[k] for k in COUNT_FIELDS} == dict.fromkeys(COUNT_FIELDS, 0), (
        f"{rb.tag} 计数：{[rb.body[k] for k in COUNT_FIELDS]}")
    changed = [t for t in JSON_TABLES if rb.extra_before[t] != rb.extra_after[t]]
    assert changed == [], f"{rb.tag} 回滚后与请求前不是逐字节相同的表：{changed}"

    # ── (c) 撤掉注入再发 partial_success：试算表确实被改动、报表按定义写满（判据不空转）──
    _assert_common(rc, executed=True)
    assert (rc.body["status"], rc.body["outcome"]) == ("success", "applied"), f"{rc.tag} status / outcome：{rc.body}"
    assert rc.at(INJECT_KIND) == [] and len(rc.events) == 2, f"{rc.tag} 时间线：{[m.kind for m in rc.marks]}"
    assert rc.extra_after["trial_balance"] != rc.extra_before["trial_balance"], f"{rc.tag} 判据空转：试算表没有被改动"
    assert set(rc.after) == definitions and len(rc.extra_after["financial_report"]) == len(definitions) > 0, (
        f"{rc.tag} 报表写入 {len(rc.extra_after['financial_report'])} 行，定义 {len(definitions)} 行")
