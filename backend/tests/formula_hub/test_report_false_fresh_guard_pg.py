"""报表 false-fresh 真库守卫（spec formula-hub-integrity-closure 任务 17；需求 5.4；ADR-FHIC-24；变异 #17）。

「读取侧判未过期」= 任务 14 的 ``report_freshness`` 口径 ``is_effectively_stale``（已标过期 / 计算版本不是当前版本 / 生成时公式
与生效公式规范化后不同，三者之一即过期；生效公式经 ``load_effective_formulas``），另以 ``stale_clause`` 计数对照。
金标准 = ``gold_report_evaluator``（原始 SQL 行 + 独立词法 / 递归下降 / 叶子筛选）。判据：读取侧判未过期、且金标准生效定义里
有公式的行，生成时公式 = 金标准生效公式、金标准可算、金额与金标准差 ≤ 0.005；全部现存公式未识别语法 0 条。

- 活项目：快照库全部未删项目的未删报表行（存量行计算版本为空 ⇒ 按 D13-A 读作过期，未过期行现为 0；判据不空转靠正例）。
- 正例：``pg_tx`` 内新建【测试】项目，``INSERT … SELECT`` 复制医疗器械 2025 的 ``trial_balance`` 全部行（``1231`` 与
  ``1231-01``~``05`` 父子并存），准则与医疗器械相同（``report_config`` 按准则全局共享、``project:`` 行 0），以
  ``skip_recalc=True``、``publish_events=False`` 调生产 ``ReportEngine.generate_all_reports``：未过期行 > 0、至少 1 行引用父子
  并存科目、「宽集合全部相加」会改变其中至少 1 行的金标准（变异 #17 ``select_leaves`` 返回全部行时本守卫必红），再逐行比对。
  不重新生成真实项目的报表（X3）；``pg_tx`` 结束一律回滚。

只连快照库（库名 ``fh_snap_`` 开头）：别的库没有这份数据 —— ``GT_REQUIRE_PG=1`` 时失败，否则跳过。
计数与不符项全文经 ``user_properties`` 写进 junit（``<property>``；断言消息会被截断），供实施记录引用。
"""
from __future__ import annotations

import uuid
from collections import Counter
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from app.models.core import Project
from app.models.report_models import FinancialReport
from app.services.report_config_service import ReportConfigService
from app.services.report_engine import ReportEngine
from app.services.report_freshness import formula_for, is_effectively_stale, load_effective_formulas, stale_clause
from tests.formula_hub import gold_report_evaluator as gold
from tests.formula_hub._pg_harness import SNAPSHOT_PREFIX, TEST_PROJECT_PREFIX, pg_required

pytestmark = pytest.mark.pg_only

MED_NAME = "重庆医药集团医疗器械有限公司_2025"
YEAR = 2025
TOLERANCE = Decimal("0.005")
#: 医疗器械 2025 试算表唯一的父子并存科目（``1231`` 与 ``1231-01``~``05``，任务 9 BS-008 金标准同一份数据）
MIXED_REF = "TB('1231')"


def _record(request, **values) -> None:
    request.node.user_properties.extend((name, str(value)) for name, value in values.items())


async def _require_snapshot(db) -> None:
    name = (await db.execute(text("SELECT current_database()"))).scalar_one()
    if not name.startswith(SNAPSHOT_PREFIX):
        reason = f"false-fresh 守卫只连快照库（{SNAPSHOT_PREFIX}*），当前库 {name}"
        if pg_required():
            pytest.fail(reason, pytrace=False)
        pytest.skip(reason)


async def _report_rows(db, project_id, year) -> list[dict]:
    rows = (await db.execute(text(
        "SELECT report_type::text AS report_type, row_code, current_period_amount, formula_used, is_stale, "
        "calc_version, calc_error FROM financial_report "
        "WHERE project_id = :pid AND year = :year AND is_deleted = false"),
        {"pid": project_id, "year": year})).mappings().all()
    return [dict(r) for r in rows]


async def _clause_fresh(db, project_id, year) -> int:
    fr = FinancialReport
    return int((await db.execute(sa.select(sa.func.count()).select_from(fr).where(
        fr.project_id == project_id, fr.year == year, fr.is_deleted == sa.false(), sa.not_(stale_clause()),
    ))).scalar_one())


async def _tb_snapshot(db, project_id) -> list[tuple[str, ...]]:
    rows = (await db.execute(text(
        "SELECT standard_account_code, company_code, audited_amount, opening_balance, unadjusted_amount, is_deleted "
        "FROM trial_balance WHERE project_id = :pid AND year = :year"), {"pid": project_id, "year": YEAR})).all()
    return sorted(tuple(str(v) for v in row) for row in rows)


def _key(row: dict) -> tuple[str, str]:
    return (row["report_type"], row["row_code"])


def _has_formula(result: gold.GoldResult, row: dict) -> bool:
    return bool((result.formulas.get(_key(row)) or "").strip())


def _fresh(rows: list[dict], effective, result: gold.GoldResult) -> list[dict]:
    """读取侧判未过期、且金标准生效定义里该行有公式的行。"""
    return [r for r in rows if not is_effectively_stale(r, formula_for(effective, r)) and _has_formula(result, r)]


def _compare(label: str, rows: list[dict], result: gold.GoldResult) -> tuple[list[str], Decimal]:
    problems, max_diff = [], Decimal("0")
    for r in rows:
        formula, expected = result.formulas[_key(r)], result.values[_key(r)]
        if (r["formula_used"] or "").strip() != (formula or "").strip():
            problems.append(f"{label} {_key(r)}：生成时公式 {r['formula_used']!r} ≠ 金标准生效公式 {formula!r}")
        elif expected.value is None:
            problems.append(f"{label} {_key(r)}：读取侧判未过期，金标准不可算（{expected.reason}）")
        elif r["current_period_amount"] is None:
            problems.append(f"{label} {_key(r)}：读取侧判未过期，金额为空；金标准 {expected.value}")
        else:
            diff = abs(Decimal(r["current_period_amount"]) - expected.value)
            max_diff = max(max_diff, diff)
            if diff > TOLERANCE:
                problems.append(f"{label} {_key(r)}：报表 {r['current_period_amount']} ≠ 金标准 {expected.value}（差 {diff}）")
    return problems, max_diff


async def test_live_project_fresh_rows_equal_gold(pg_tx, request):
    await _require_snapshot(pg_tx)
    parsed, issues = await gold.scan_all_formulas(pg_tx)
    scopes = (await pg_tx.execute(text(
        "SELECT DISTINCT fr.project_id, fr.year FROM financial_report fr JOIN projects p ON p.id = fr.project_id "
        "WHERE p.is_deleted = false AND fr.is_deleted = false ORDER BY fr.project_id, fr.year"))).all()
    counts: Counter = Counter()
    problems: list[str] = []
    unrecognized: list[str] = []
    max_diff = Decimal("0")
    for project_id, year in scopes:
        rows = await _report_rows(pg_tx, project_id, year)
        effective = await load_effective_formulas(pg_tx, project_id)
        result = await gold.evaluate_project(pg_tx, project_id, year)
        unrecognized += result.unrecognized
        standard = await ReportConfigService.resolve_applicable_standard(pg_tx, project_id)
        if standard != result.standard:
            problems.append(f"{project_id}：生产准则 {standard} ≠ 金标准准则 {result.standard}")
        fresh = _fresh(rows, effective, result)
        found, diff = _compare(f"{project_id}/{year}", fresh, result)
        problems += found
        max_diff = max(max_diff, diff)
        with_formula = [r for r in rows if _has_formula(result, r)]
        stale = [r for r in with_formula if r not in fresh]
        counts.update(
            rows=len(rows), with_formula=len(with_formula), fresh=len(fresh),
            clause_fresh=await _clause_fresh(pg_tx, project_id, year),
            gold_uncomputable=sum(1 for r in with_formula if result.values[_key(r)].value is None),
            stale_differ=sum(1 for r in stale if result.values[_key(r)].value is not None
                             and r["current_period_amount"] is not None
                             and abs(Decimal(r["current_period_amount"]) - result.values[_key(r)].value) > TOLERANCE),
        )
    _record(request, live_formulas_parsed=parsed, live_scopes=len(scopes), live_rows=counts["rows"],
            live_rows_with_formula=counts["with_formula"], live_fresh_rows=counts["fresh"],
            live_clause_fresh_rows=counts["clause_fresh"], live_gold_uncomputable=counts["gold_uncomputable"],
            live_stale_rows_differ_gold=counts["stale_differ"], live_max_diff=max_diff, live_problems=problems)
    assert parsed > 0 and issues == [], issues
    assert scopes, "快照库没有活项目的报表行：守卫没有对象"
    assert unrecognized == [], unrecognized
    assert problems == [], problems


async def test_copied_medical_regeneration_fresh_rows_equal_gold(pg_tx, request):
    await _require_snapshot(pg_tx)
    located = (await pg_tx.execute(text(
        "SELECT id, template_type, report_scope FROM projects "
        "WHERE name = :name AND is_deleted = false AND audit_year = :year"), {"name": MED_NAME, "year": YEAR})).all()
    assert len(located) == 1, located
    source_id, template_type, report_scope = located[0]
    project = Project(name=f"{TEST_PROJECT_PREFIX}fh_t17_false_fresh_{uuid.uuid4().hex[:10]}",
                      client_name=f"{TEST_PROJECT_PREFIX}公式中枢 false-fresh 守卫",
                      template_type=template_type, report_scope=report_scope, audit_year=YEAR)
    pg_tx.add(project)
    await pg_tx.flush()
    project_id = project.id

    columns = (await pg_tx.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
        "AND table_name = 'trial_balance' AND column_name NOT IN ('id', 'project_id') "
        "ORDER BY ordinal_position"))).scalars().all()
    quoted = ", ".join('"' + name.replace('"', '""') + '"' for name in columns)
    source_tb = await _tb_snapshot(pg_tx, source_id)
    copied = await pg_tx.execute(text(
        f"INSERT INTO trial_balance (id, project_id, {quoted}) SELECT gen_random_uuid(), :dst, {quoted} "
        "FROM trial_balance WHERE project_id = :src AND year = :year"),
        {"dst": project_id, "src": source_id, "year": YEAR})
    assert copied.rowcount == len(source_tb) > 0, (copied.rowcount, len(source_tb))
    assert await _tb_snapshot(pg_tx, project_id) == source_tb

    standard = await ReportConfigService.resolve_applicable_standard(pg_tx, project_id)
    assert standard == await ReportConfigService.resolve_applicable_standard(pg_tx, source_id)
    assert standard == await gold.resolve_standard(pg_tx, project_id)
    await ReportEngine(pg_tx).generate_all_reports(
        project_id, YEAR, applicable_standard=standard, skip_recalc=True, publish_events=False)
    await pg_tx.flush()
    assert await _tb_snapshot(pg_tx, project_id) == source_tb, "skip_recalc=True 仍改动了复制来的试算表"

    rows = await _report_rows(pg_tx, project_id, YEAR)
    effective = await load_effective_formulas(pg_tx, project_id)
    result = await gold.evaluate_project(pg_tx, project_id, YEAR)
    doubled = await gold.evaluate_project(pg_tx, project_id, YEAR, leaves_only=False)
    tb = await gold.load_tb_rows(pg_tx, project_id, YEAR)
    fresh = _fresh(rows, effective, result)
    keys = [_key(r) for r in fresh]
    mixed = {key: refs for key in keys if (refs := gold.mixed_family_refs(result.formulas[key], tb))}
    sensitive = sorted(key for key in keys if doubled.values[key].value != result.values[key].value)
    problems, max_diff = _compare("正例", fresh, result)
    with_formula = [r for r in rows if _has_formula(result, r)]
    _record(request, positive_tb_rows=len(source_tb), positive_rows=len(rows),
            positive_rows_with_formula=len(with_formula), positive_fresh_rows=len(fresh),
            positive_clause_fresh_rows=await _clause_fresh(pg_tx, project_id, YEAR),
            positive_stale_rows=sorted((_key(r), r["calc_error"]) for r in with_formula if r not in fresh),
            positive_mixed_rows=sorted(mixed.items()), positive_double_count_sensitive_rows=sensitive,
            positive_max_diff=max_diff, positive_problems=problems)
    assert result.unrecognized == [], result.unrecognized
    assert fresh, "夹具空转：重新生成后没有读取侧判未过期的有公式行"
    assert any(MIXED_REF in refs for refs in mixed.values()), f"夹具空转：未过期行都没引用 {MIXED_REF}（{mixed}）"
    assert sensitive, "夹具空转：宽集合全部相加不改变任何未过期行的金标准"
    assert problems == [], problems
