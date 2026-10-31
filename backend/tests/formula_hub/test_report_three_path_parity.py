"""报表三路统一逐行计算与依赖缓存（spec formula-hub-integrity-closure 任务 16；需求 5.2、5.3、6.4；ADR-FHIC-01 / 05）。

夹具见 ``_report_compute_world``（SQLite 真 ORM，每路一份独立库）。三路 = 全量 ``generate_all_reports`` / affected
``regenerate_affected`` / stale ``recalculate_stale_rows``，对同一组初始数据逐行比较库中终态（金额、``is_stale``、
``calc_error``、``calc_version``）与逐行计算结果（经 ``report_engine.compute_row`` 的记录器取得，记录器原样调用
``report_row_compute.compute_row``）：

- 行形态：``1/0``、缺科目 ⇒ 0（trace 注明）、合法 0（科目有余额也不替换、只告警；变异 #19）、父子不符 ⇒ 按叶子 + 告警、
  首次失败新行金额 NULL（只有全量路径建行）、组成行无公式告警（需求 6.4）；
- 「A 失败 ⇒ 合计 T 失败且过期」：本轮失败（A 与 T 都重算）与上一轮已失败（affected 只重算 T）两种，三路一致（变异 #23）；
- affected：``1231-02`` 命中 ``TB('1231')``，不传准则时按项目真实准则（需求 5.3）；
- ``generate_all_reports`` 的 ``skip_recalc`` / ``publish_events`` / ``summary_out``（返回 dict 的键不变）。
"""
from __future__ import annotations

from decimal import Decimal

import pytest

import app.services.report_engine as report_engine
from app.models.audit_platform_schemas import EventType
from app.services import report_row_compute
from app.services.event_bus import event_bus
from app.services.report_freshness import CALC_VERSION
from app.services.report_row_compute import GenerateSummary, RowOutcome
from app.services.trial_balance_service import TrialBalanceService
from tests.formula_hub._report_compute_world import (
    COMPONENTS, DIV0, LEAF, LEGAL_ZERO, MISSING, NEW, PATHS, YEAR, A, B, S, T, run_path, set_tb, snapshot,
    sqlite_world,
)

NOT_READY = f"引用行未就绪：{A}（过期或计算失败）"
FORMULA_LESS = ("IS-048", "IS-054")
#: 三路共同的库中终态期望：(金额, is_stale, calc_error 应含的文字 / None, calc_version)
EXPECTED = {
    DIV0: (Decimal(33), True, "除数为 0", None),
    MISSING: (Decimal(0), False, None, CALC_VERSION),
    LEGAL_ZERO: (Decimal(0), False, None, CALC_VERSION),
    LEAF: (Decimal(90), False, None, CALC_VERSION),
    A: (Decimal(11), True, "除数为 0", None),
    B: (Decimal(200), False, None, CALC_VERSION),
    T: (Decimal(77), True, NOT_READY, None),
    S: (Decimal(88), True, NOT_READY, None),
    **{code: (Decimal(0), False, None, CALC_VERSION) for code in FORMULA_LESS},
    COMPONENTS: (Decimal(600), False, None, CALC_VERSION),
}


class _Recorder:
    """``report_engine.compute_row`` 的记录器：原样调用 ``report_row_compute.compute_row``，按路径记下每行结果。"""

    def __init__(self) -> None:
        self.path = ""
        self.outcomes: dict[str, dict[str, RowOutcome]] = {}

    async def __call__(self, parser, config, row_cache, **kwargs):
        outcome = await report_row_compute.compute_row(parser, config, row_cache, **kwargs)
        self.outcomes.setdefault(self.path, {})[config.row_code] = outcome
        return outcome


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(report_engine, "compute_row", rec)
    return rec


def _matches(state, expected) -> bool:
    amount, stale, error, version = state
    want_amount, want_stale, want_error, want_version = expected
    amount_ok = amount is None if want_amount is None else amount == want_amount
    error_ok = error is None if want_error is None else (error is not None and want_error in error)
    return amount_ok and bool(stale) == want_stale and error_ok and version == want_version


def _view(outcome: RowOutcome):
    return outcome.state, outcome.value, outcome.calc_error, tuple(outcome.warnings), tuple(outcome.trace)


def _diff(left: dict, right: dict) -> dict:
    return {code: (left.get(code), right.get(code)) for code in sorted(set(left) | set(right))
            if left.get(code) != right.get(code)}


@pytest.mark.asyncio
async def test_row_cases_agree_across_three_paths(recorder):
    """有公式行都是已标过期的存量行：三路库中终态逐行一致且等于期望，逐行计算结果（状态 / 值 / 原因 / 告警 / trace）三路相同。"""
    finals = {}
    for path in PATHS:
        recorder.path = path
        async with sqlite_world(tag=f"fh_t16_{path}") as world:
            await run_path(world, path)
            finals[path] = await snapshot(world)
    for path, final in finals.items():
        got = {code: state for code, state in final.items() if code != NEW}
        assert set(got) == set(EXPECTED), (path, sorted(got))
        bad = {code: got[code] for code in EXPECTED if not _matches(got[code], EXPECTED[code])}
        assert not bad, (path, bad)
    full_existing = {code: state for code, state in finals["full"].items() if code != NEW}
    assert not _diff(full_existing, finals["affected"]) and not _diff(full_existing, finals["stale"])
    # 首次生成即失败的新行只有全量路径会建：金额 NULL、过期、写失败原因、无计算版本
    assert _matches(finals["full"][NEW], (None, True, "除数为 0", None)), finals["full"][NEW]
    assert NEW not in finals["affected"] and NEW not in finals["stale"]

    for code in (c for c in EXPECTED if c not in FORMULA_LESS):  # 无公式行 affected / stale 不重算
        views = {path: _view(recorder.outcomes[path][code]) for path in PATHS}
        assert views["full"] == views["affected"] == views["stale"], (code, views)
    full = recorder.outcomes["full"]
    assert [w for w in full[LEGAL_ZERO].warnings if "1001" in w and "100" in w], full[LEGAL_ZERO].warnings
    assert [w for w in full[LEAF].warnings if "1231" in w and "10.00" in w], full[LEAF].warnings
    assert (full[MISSING].state, full[MISSING].errors, full[MISSING].warnings) == ("ok", [], [])
    assert [t for t in full[MISSING].trace if "TB('9999')" in t and "按 0" in t], full[MISSING].trace


@pytest.mark.asyncio
async def test_failed_input_keeps_total_failed_and_stale(recorder):
    """「A 失败 ⇒ 合计 T 失败且过期」：上一轮全量生成里 A 已失败、T / S 随之失败；本轮三路 —— 全量、stale（A、T、S 都重算）、
    affected（只变更 B 的科目 ⇒ 只重算 B、T、S，A 保持上一轮的失败状态）—— T 与 S 都失败「引用行未就绪」、保留旧值并保持过期，
    整表终态与上一轮相同（变异 #23：依赖缓存收入过期 / 失败行 ⇒ affected 的 T、S 用 A 的旧值算成功）。"""
    for path in PATHS:
        async with sqlite_world(tag=f"fh_t16_dep_{path}") as world:
            recorder.path = f"baseline:{path}"
            await run_path(world, "full")
            baseline = await snapshot(world)
            assert all(_matches(baseline[code], EXPECTED[code]) for code in (A, T, S)), baseline
            recorder.path = path
            await run_path(world, path, changed=["1002"])
            final = await snapshot(world)
        assert not _diff(baseline, final), (path, _diff(baseline, final))
        outcomes = recorder.outcomes[path]
        if path == "affected":
            assert A not in outcomes and {B, T, S} <= set(outcomes), sorted(outcomes)
        for code in (T, S):
            assert (outcomes[code].state, outcomes[code].calc_error) == ("not_ready", NOT_READY), (path, code)


@pytest.mark.asyncio
async def test_affected_prefix_hits_parent_and_uses_real_standard():
    """``changed_accounts=['1231-02']`` 命中引用 ``TB('1231')`` 的行；不传准则时按项目真实准则（soe_standalone）取定义。"""
    engine = report_engine.ReportEngine.__new__(report_engine.ReportEngine)
    assert engine._is_affected("TB('1231','期末余额')", ["1231-02"])
    assert engine._is_affected("TB('1231','期末余额')", ["1231"])
    assert not engine._is_affected("TB('1231','期末余额')", ["1232"])
    assert not engine._is_affected("TB('1231-02','期末余额')", ["1231"])  # 上级变更不命中只取下级的引用
    assert engine._is_affected("SUM_TB('1400~1499','期末余额')", ["1499-01"])
    assert not engine._is_affected("SUM_TB('1400~1499','期末余额')", ["1500"])
    async with sqlite_world(tag="fh_t16_prefix") as world:
        await run_path(world, "full")
        before = await snapshot(world)
        await set_tb(world, "1231-02", 60)
        count = await run_path(world, "affected", changed=["1231-02"])
        after = await snapshot(world)
    assert count == 1
    assert after[LEAF] == (Decimal(100), False, None, CALC_VERSION)
    assert not _diff({c: s for c, s in before.items() if c != LEAF}, {c: s for c, s in after.items() if c != LEAF})


@pytest.mark.asyncio
async def test_formula_less_component_warning():
    """合计行的组成行无公式（``ROW`` 直接引用）⇒ 行结果带「组成行 IS-048、IS-054 未定义公式」，值照常（无公式行按 0）。"""
    async with sqlite_world(tag="fh_t16_components") as world:
        result = await run_path(world, "full")
    row = next(r for r in result["income_statement"] if r["row_code"] == COMPONENTS)
    assert (Decimal(row["current_period_amount"]), row["formula_error"], row["is_stale"]) == (Decimal(600), None, False)
    assert row["warnings"] == ["组成行 IS-048、IS-054 未定义公式"]
    coverage = result["coverage_stats"]["by_type"]["income_statement"].get("warnings", [])
    assert [w["message"] for w in coverage if w["row_code"] == COMPONENTS] == ["组成行 IS-048、IS-054 未定义公式"]


@pytest.mark.asyncio
async def test_generate_switches_and_summary(monkeypatch):
    """``skip_recalc`` / ``publish_events`` / ``summary_out``：默认照旧（先重算试算表、发 ``REPORT_ROW_CHANGED``），返回 dict 的键
    不变；关掉后两者都不发生；摘要按「值变化 / 成功未变 / 失败」逐行分类（金额规范化到分后比较）。"""
    recalcs, published = [], []

    async def fake_full_recalc(self, project_id, year, company_code="001"):  # 夹具没有四表数据，不跑真重算
        recalcs.append((project_id, year))

    async def fake_publish(payload):
        published.append(payload)

    monkeypatch.setattr(TrialBalanceService, "full_recalc", fake_full_recalc)
    # 在实例上替换：同进程先跑的 tests/formula_settings/test_propagation.py 用 monkeypatch 在实例上换过 publish，
    # 撤销时把原方法写成实例属性，之后的类级替换被它挡住（2026-10-30 整合到分支 HEAD 后按目录顺序复现：0 条事件）
    monkeypatch.setattr(event_bus, "publish", fake_publish)
    first, second = GenerateSummary(), GenerateSummary()
    async with sqlite_world(tag="fh_t16_switch") as world:
        out = await run_path(world, "full", skip_recalc=False, publish_events=True, summary_out=first)
        events = [p for p in published if p.event_type == EventType.REPORT_ROW_CHANGED]
        assert set(out) == {"balance_sheet", "income_statement", "coverage_stats"}
        assert recalcs == [(world.project_id, YEAR)]
        assert len(events) == 1 and events[0].extra["changed_row_codes"], events
        await run_path(world, "full", summary_out=second)  # run_path 默认 skip_recalc=True、publish_events=False
    assert len(recalcs) == 1
    assert len([p for p in published if p.event_type == EventType.REPORT_ROW_CHANGED]) == 1

    def codes(rows):
        return sorted(r["row_code"] for r in rows)

    changed, failed = sorted([MISSING, LEGAL_ZERO, LEAF, B, COMPONENTS]), sorted([DIV0, A, T, S, NEW])
    assert (codes(first.changed_rows), codes(first.recomputed_rows), codes(first.failed_rows)) == (
        changed, list(FORMULA_LESS), failed)
    assert (codes(second.changed_rows), codes(second.recomputed_rows), codes(second.failed_rows)) == (
        [], sorted([*changed, *FORMULA_LESS]), failed)
    assert {r["row_code"]: (r["state"], r["error"]) for r in first.failed_rows}[T] == ("not_ready", NOT_READY)
