"""合计行 ``SUM_ROW`` 区间不含其他合计行（棘轮；spec formula-hub-integrity-closure 任务 18 第一段 B；需求 6.3；ADR-FHIC-23）。

判据：``is_total_row`` 行的公式里每个 ``SUM_ROW('起','止')``，区间 = 与本行同表、起 ≤ 行次 ≤ 止（字符串比较，与
``report_row_compute._not_ready`` 同口径）的行，本行以外不得有 ``is_total_row`` 行。现存违规按（准则, 报表类型, 行次）冻结成
精确集合：现值 ⊆ 基线（新增即红），且基线 ⊆ 现值（基线不虚高）。

数据源各算一次：种子（非 PG；现有 ``SUM_ROW`` 0 条 ⇒ 基线为空，判据现为结构性零）与快照库未删 ``report_config``（真 PG；基线 =
国企两套 IS-074 / IS-075、上市两套 IS-051 / IS-052 共 8 行，任务 18 第一段 A 判定为首版生成器写入）。

基线下调：违规修好后（如任务 19 升级工具对快照库执行、决策项 X2），把对应键从 ``DB_BASELINE`` / ``SEED_BASELINE`` 删除 ——
只许删、不许加；本守卫在「已修好却仍在基线里」时同样变红，提示删哪几条。
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy import text

from tests.formula_hub._report_definition_rows import DefRow, db_definitions, require_snapshot, seed_definitions

SUM_ROW_REF = re.compile(r"(?<![A-Za-z0-9_])SUM_ROW\([ \t]*'([^']*)'[ \t]*,[ \t]*'([^']*)'[ \t]*\)")
IS = "income_statement"
SEED_BASELINE: frozenset[tuple[str, str, str]] = frozenset()
DB_BASELINE: frozenset[tuple[str, str, str]] = frozenset({
    ("listed_consolidated", IS, "IS-051"), ("listed_consolidated", IS, "IS-052"),
    ("listed_standalone", IS, "IS-051"), ("listed_standalone", IS, "IS-052"),
    ("soe_consolidated", IS, "IS-074"), ("soe_consolidated", IS, "IS-075"),
    ("soe_standalone", IS, "IS-074"), ("soe_standalone", IS, "IS-075"),
})


def range_violations(defs: dict[str, list[DefRow]]) -> dict[tuple[str, str, str], tuple[str, ...]]:
    """（准则, 报表类型, 行次）→ 区间里的其他合计行（升序）。只看 ``is_total_row`` 行公式里的 ``SUM_ROW``。"""
    out: dict[tuple[str, str, str], tuple[str, ...]] = {}
    for std, rows in defs.items():
        by_type: dict[str, list[DefRow]] = {}
        for r in rows:
            by_type.setdefault(r.report_type, []).append(r)
        for row in rows:
            if not row.is_total_row:
                continue
            crossed = {r.row_code for start, end in SUM_ROW_REF.findall(row.formula or "")
                       for r in by_type[row.report_type]
                       if start <= r.row_code <= end and r.row_code != row.row_code and r.is_total_row}
            if crossed:
                out[(std, row.report_type, row.row_code)] = tuple(sorted(crossed))
    return out


def scanned(defs: dict[str, list[DefRow]]) -> dict[str, int]:
    rows = [r for items in defs.values() for r in items]
    return {"rows": len(rows), "total_rows": sum(r.is_total_row for r in rows),
            "total_rows_with_sum_row": sum(bool(r.is_total_row and SUM_ROW_REF.search(r.formula or "")) for r in rows)}


def ratchet_problems(current: dict, baseline: frozenset, name: str) -> list[str]:
    added = sorted(set(current) - baseline)
    fixed = sorted(baseline - set(current))
    problems = [f"新增跨合计行 SUM_ROW：{key} 区间含合计行 {current[key]}" for key in added]
    problems += [f"基线虚高：{key} 已不再违规 —— 从 {name} 删除这一条（只许删、不许加）" for key in fixed]
    return problems


def _rows(*specs) -> dict[str, list[DefRow]]:
    return {"std": [DefRow(rt, code, i, code, total, formula) for i, (rt, code, total, formula) in enumerate(specs, 1)]}


# ─── 扫描器自检（合成样本）──────────────────────────────────────────────────────────


def test_scanner_reports_violations_and_ignores_clean_samples():
    bad = _rows((IS, "X-001", False, None), (IS, "X-002", True, "ROW('X-001')"), (IS, "X-003", False, None),
                (IS, "X-004", True, "SUM_ROW('X-001','X-003')"),
                (IS, "X-005", True, "SUM_ROW( 'X-001' , 'X-004' )+ROW('X-003')"))
    assert range_violations(bad) == {("std", IS, "X-004"): ("X-002",), ("std", IS, "X-005"): ("X-002", "X-004")}
    clean = _rows(
        (IS, "X-001", False, None), (IS, "X-002", False, None),
        (IS, "X-003", True, "SUM_ROW('X-001','X-002')"),            # 区间里没有合计行
        (IS, "X-004", True, "SUM_ROW('X-004','X-004')"),            # 只含本行（不算「另一合计行」）
        (IS, "X-005", False, "SUM_ROW('X-001','X-004')"),           # 非合计行不在本判据范围
        (IS, "X-006", True, "ROW('X-003')+ROW('X-004')"),           # 显式 ROW 相加不是区间
        ("balance_sheet", "X-007", True, None),                     # 他表的合计行不在本表区间里
        (IS, "X-008", True, "SUM_ROW('X-005','X-005')"))
    assert range_violations(clean) == {}
    assert scanned(clean)["total_rows_with_sum_row"] == 3, "自检样本空转：合计行的 SUM_ROW 没被扫到"


def test_ratchet_reports_new_and_stale_baseline_entries():
    current = {("a", IS, "X-1"): ("X-0",), ("a", IS, "X-2"): ("X-1",)}
    assert ratchet_problems(current, frozenset(current), "B") == []
    problems = ratchet_problems(current, frozenset({("a", IS, "X-1"), ("a", IS, "X-9")}), "B")
    assert len(problems) == 2 and "新增" in problems[0] and "X-2" in problems[0]
    assert "基线虚高" in problems[1] and "X-9" in problems[1] and "从 B 删除" in problems[1]


# ─── 种子（非 PG）────────────────────────────────────────────────────────────────


def test_seed_total_row_ranges_within_baseline(request):
    defs = seed_definitions()
    current = range_violations(defs)
    counts = scanned(defs)
    request.node.user_properties.extend([("seed_scanned", str(counts)), ("seed_violations", str(sorted(current)))])
    assert sorted(defs) == ["listed_consolidated", "listed_standalone", "soe_consolidated", "soe_standalone"]
    assert counts["total_rows"] > 0, f"种子没有合计行：守卫没有对象（{counts}）"
    assert ratchet_problems(current, SEED_BASELINE, "SEED_BASELINE") == []


# ─── 快照库（真 PG）──────────────────────────────────────────────────────────────

PURPOSE = "合计行区间守卫的基线按快照库冻结，"


@pytest.mark.pg_only
async def test_snapshot_total_row_ranges_within_baseline(pg_tx, request):
    await require_snapshot(pg_tx, PURPOSE)
    defs = await db_definitions(pg_tx)
    current = range_violations(defs)
    counts = scanned(defs)
    request.node.user_properties.extend([("db_scanned", str(counts)), ("db_violations", str(sorted(current.items())))])
    assert counts["total_rows_with_sum_row"] > 0, f"快照库合计行没有 SUM_ROW：守卫空转（{counts}）"
    assert ratchet_problems(current, DB_BASELINE, "DB_BASELINE") == []


@pytest.mark.pg_only
async def test_snapshot_scan_detects_injected_violation(pg_tx):
    """回滚事务内把国企单体 IS-073「七、综合收益总额」（合计行，现为 ``SUM_ROW('IS-054','IS-072')``、不在基线）改成
    ``SUM_ROW('IS-001','IS-072')``（区间含合计行 IS-044）：库内读取 + 判据必报出这一条、且只多这一条（读取路径不空转）。"""
    await require_snapshot(pg_tx, PURPOSE)
    target = (await pg_tx.execute(text(
        "SELECT id, is_total_row FROM report_config WHERE is_deleted = false AND applicable_standard = 'soe_standalone' "
        "AND report_type = 'income_statement' AND row_code = 'IS-073'"))).one()
    key = ("soe_standalone", IS, "IS-073")
    assert target.is_total_row is True and key not in DB_BASELINE
    await pg_tx.execute(text("UPDATE report_config SET formula = :f WHERE id = :id"),
                        {"f": "SUM_ROW('IS-001','IS-072')", "id": target.id})
    current = range_violations(await db_definitions(pg_tx))
    assert "IS-044" in current.get(key, ()), current.get(key)
    assert ratchet_problems(current, DB_BASELINE, "DB_BASELINE") == [
        f"新增跨合计行 SUM_ROW：{key} 区间含合计行 {current[key]}"]
