"""BS-008 真 PG 金标准：报表取数对父子并存的科目只计叶子（spec formula-hub-integrity-closure 任务 9；需求 4.1、4.3；
ADR-FHIC-03；变异 #17）。

对象：快照库里的医疗器械 2025（soe 单体）。被测值 = 生产报表取数路径 ``ReportFormulaParser.execute_with_status``
（→ ``evaluate_formula_result`` → ``_resolve_tb``：前缀宽集合 + 叶子）对 ``report_config``（soe_standalone /
balance_sheet / BS-008）现读公式的求值。金标准在测试内独立计算：原生 SQL 取本项目本年度未删的 ``trial_balance`` 行
（字面前缀 ``starts_with``；金额列 ``audited_amount`` = 生产「期末余额」口径），叶子在纯 Python 里逐行暴力判定（集合内
没有以本码为前缀且更长的其他码），再按公式的 TB 加减项求和；不调用 ``tb_leaf_codes``。父子不符告警同样按金标准比对。

夹具非空转：``1231`` 坏账准备父子并存，前缀和（父行连同下级全部相加）≠ 叶子和 ⇒ 双计会改变 BS-008 的结果。
只连快照库（库名 ``fh_snap_`` 开头）：别的库没有这份真实数据 —— ``GT_REQUIRE_PG=1`` 时失败，否则跳过（与
``_pg_harness`` 对 PG 不可用的口径一致）。``pg_tx`` 只读，结束回滚。
"""
from __future__ import annotations

import re
import uuid
from decimal import ROUND_HALF_UP, Decimal

import pytest
from sqlalchemy import text

from app.services.report_engine import ReportFormulaParser
from tests.formula_hub._pg_harness import SNAPSHOT_PREFIX, pg_required

pytestmark = pytest.mark.pg_only

PROJECT_NAME = "重庆医药集团医疗器械有限公司_2025"
PROJECT_ID = uuid.UUID("5e193c68-f53c-4e95-8d03-5d9c996c402d")
YEAR = 2025
STANDARD, REPORT_TYPE, ROW_CODE = "soe_standalone", "balance_sheet", "BS-008"
#: 父子并存的科目（F8：父行 = 下级之和，按前缀相加会把它算两遍）
DOUBLE_COUNT_CODE = "1231"
COLUMN = "期末余额"  # 生产 report_engine._COLUMN_MAP：期末余额 → audited_amount
TOLERANCE = Decimal("0.005")
_TERM = re.compile(r"\s*([+-])?\s*TB\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)\s*")
_FLAGGED = re.compile(rf"科目 ([^（\s]+)（{COLUMN}）本级金额")


def _cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _linear_tb_terms(formula: str) -> list[tuple[int, str]]:
    """公式 = ``TB('码','期末余额')`` 的加减组合 ⇒ ``[(±1, 码)]``；不是这种形状即失败（金标准只覆盖这一形状）。"""
    terms: list[tuple[int, str]] = []
    pos = 0
    while pos < len(formula):
        match = _TERM.match(formula, pos)
        assert match and (match.group(1) or not terms) and match.group(3) == COLUMN, (
            f"{ROW_CODE} 公式 {formula!r} 不是 TB(…,'{COLUMN}') 的加减组合，金标准需改写")
        terms.append((-1 if match.group(1) == "-" else 1, match.group(2)))
        pos = match.end()
    assert terms, f"{ROW_CODE} 公式为空"
    return terms


async def _tb_rows(db, code: str) -> list[tuple[str, Decimal]]:
    """本项目本年度未删、标准码以 ``code`` 开头（字面前缀）的 ``(码, 期末余额)`` 行。"""
    result = await db.execute(text(
        "SELECT standard_account_code, COALESCE(audited_amount, 0) FROM trial_balance "
        "WHERE project_id = :pid AND year = :year AND is_deleted = false "
        "AND starts_with(standard_account_code, :code)"), {"pid": PROJECT_ID, "year": YEAR, "code": code})
    return [(str(c), Decimal(a)) for c, a in result.all()]


def _has_longer(code: str, codes: set[str]) -> bool:
    return any(len(other) > len(code) and other.startswith(code) for other in codes)


def _leaf_sum(rows: list[tuple[str, Decimal]]) -> Decimal:
    codes = {c for c, _ in rows}
    return sum((a for c, a in rows if not _has_longer(c, codes)), Decimal("0"))


def _mismatched_parents(rows: list[tuple[str, Decimal]]) -> set[str]:
    """父行（同码合计）与其下叶子合计差 > 0.005 的父码 —— 生产应恰对这些码告警。"""
    codes = {c for c, _ in rows}
    out = set()
    for parent in (c for c in codes if _has_longer(c, codes)):
        own = sum((a for c, a in rows if c == parent), Decimal("0"))
        if abs(own - _leaf_sum([(c, a) for c, a in rows if c.startswith(parent)])) > TOLERANCE:
            out.add(parent)
    return out


async def _require_snapshot(db) -> None:
    name = (await db.execute(text("SELECT current_database()"))).scalar_one()
    if not name.startswith(SNAPSHOT_PREFIX):
        reason = f"BS-008 金标准只连快照库（{SNAPSHOT_PREFIX}*），当前库 {name}"
        if pg_required():
            pytest.fail(reason, pytrace=False)
        pytest.skip(reason)


async def test_bs008_equals_leaf_gold(pg_tx):
    await _require_snapshot(pg_tx)
    located = (await pg_tx.execute(text(
        "SELECT id, template_type, report_scope FROM projects "
        "WHERE name = :name AND is_deleted = false AND audit_year = :year"),
        {"name": PROJECT_NAME, "year": YEAR})).all()
    assert [(uuid.UUID(str(i)), t, s) for i, t, s in located] == [(PROJECT_ID, "soe", "standalone")], located

    formulas = (await pg_tx.execute(text(
        "SELECT formula FROM report_config WHERE applicable_standard = :std AND report_type::text = :rt "
        "AND row_code = :row AND is_deleted = false"),
        {"std": STANDARD, "rt": REPORT_TYPE, "row": ROW_CODE})).scalars().all()
    assert len(formulas) == 1, formulas
    terms = _linear_tb_terms(formulas[0])
    assert DOUBLE_COUNT_CODE in {code for _, code in terms}, formulas[0]

    rows = {code: await _tb_rows(pg_tx, code) for _, code in terms}
    family = rows[DOUBLE_COUNT_CODE]
    codes = {c for c, _ in family}
    children = sorted(c for c in codes if len(c) > len(DOUBLE_COUNT_CODE) and c.startswith(DOUBLE_COUNT_CODE))
    assert DOUBLE_COUNT_CODE in codes and children, f"夹具空转：{DOUBLE_COUNT_CODE} 父子不并存（{sorted(codes)}）"
    prefix_sum = sum((a for _, a in family), Decimal("0"))
    assert prefix_sum != _leaf_sum(family), f"夹具空转：{DOUBLE_COUNT_CODE} 前缀和 = 叶子和 = {prefix_sum}"
    gold = _cents(sum((sign * _leaf_sum(rows[code]) for sign, code in terms), Decimal("0")))
    doubled = _cents(sum((sign * sum((a for _, a in rows[code]), Decimal("0")) for sign, code in terms), Decimal("0")))
    assert doubled != gold, "夹具空转：按前缀相加与叶子金标准相同"

    result = await ReportFormulaParser(pg_tx, PROJECT_ID, YEAR).execute_with_status(formulas[0], {})
    assert result.ok, result.errors
    assert _cents(result.value) == gold, f"{ROW_CODE} = {result.value}；叶子金标准 {gold}；按前缀相加 {doubled}"
    expected = set().union(*(_mismatched_parents(items) for items in rows.values()))
    assert {m.group(1) for w in result.warnings for m in _FLAGGED.finditer(w)} == expected, result.warnings
