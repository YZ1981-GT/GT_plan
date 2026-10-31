"""报表行引用的计算顺序守卫（= 0 冻结；spec formula-hub-integrity-closure 任务 18 第一段 B；需求 6.3；F37、N8）。

计算顺序 =（报表类型序, 行号, 行次）：金标准求值器 ``gold_report_evaluator.evaluate`` 的排序键。报表类型序与生产
``report_engine._TYPE_ORDER``（全量 / affected / stale 三路共用）逐项相同（本文件断言）；生产在表内按行号排序
（``sorted(config_rows, key=row_number)``），两者在表内行号不重复时等价 —— 行号不重复作为结构前提一并断言。

判据（种子、快照库未删 ``report_config`` 各算一次，每套定义单独算，全部为 0）：

- ``ROW('x')``：悬空 = x 不是本套定义的行次；跨表 = x 只在他表；前向 = x 的计算位置不早于本行（含自引用），不论 x 有无公式 ——
  比 ``report_row_compute._not_ready`` 严：现行实现里引用后算的无公式行读 0、不报未就绪，这里也算前向；
- ``SUM_ROW('a','b')``（区间按字符串比较）：端点不是本套行次、``a > b`` 或本表无行落入 ⇒ 悬空；端点在他表或区间含他表行 ⇒ 跨表；
  区间含计算位置不早于本行的本表行（含本行）⇒ 前向；
- 未识别写法：公式里 ``ROW(``（含 ``SUM_ROW(`` 里的）出现次数 ≠ 上两种写法认出的次数（双引号、缺实参……）⇒ 记一条；
- 结构前提：行次在本套定义里唯一（含跨表同码）、表内行号唯一、报表类型在计算顺序里。
"""
from __future__ import annotations

import re
from collections import Counter

import pytest
from sqlalchemy import text

from app.services.report_engine import _TYPE_ORDER
from tests.formula_hub._report_definition_rows import DefRow, db_definitions, require_snapshot, seed_definitions
from tests.formula_hub.gold_report_evaluator import TYPE_ORDER

ROW_REF = re.compile(r"(?<![A-Za-z0-9_])ROW\([ \t]*'([^']*)'[ \t]*\)")
SUM_ROW_REF = re.compile(r"(?<![A-Za-z0-9_])SUM_ROW\([ \t]*'([^']*)'[ \t]*,[ \t]*'([^']*)'[ \t]*\)")
ROW_OPEN = re.compile(r"ROW\(")
BS, IS = "balance_sheet", "income_statement"
#: (类别, 准则, 报表类型, 行次, 说明)
Problem = tuple[str, str, str, str, str]


def _structure(std: str, rows: list[DefRow]) -> list[Problem]:
    problems: list[Problem] = []
    codes = Counter(r.row_code for r in rows)
    numbers = Counter((r.report_type, r.row_number) for r in rows)
    for r in rows:
        if r.report_type not in TYPE_ORDER:
            problems.append(("结构", std, r.report_type, r.row_code, "报表类型不在计算顺序里"))
        if codes[r.row_code] > 1:
            problems.append(("结构", std, r.report_type, r.row_code, "行次在本套定义里重复（含跨表同码）"))
        if numbers[(r.report_type, r.row_number)] > 1:
            problems.append(("结构", std, r.report_type, r.row_code, f"表内行号 {r.row_number} 重复"))
    return problems


def ref_problems(defs: dict[str, list[DefRow]]) -> list[Problem]:
    problems: list[Problem] = []
    for std, rows in sorted(defs.items()):
        problems += _structure(std, rows)
        known = [r for r in rows if r.report_type in TYPE_ORDER]
        order = sorted(known, key=lambda r: (TYPE_ORDER.index(r.report_type), r.row_number, r.row_code))
        pos = {(r.report_type, r.row_code): i for i, r in enumerate(order)}
        types_of: dict[str, set[str]] = {}
        for r in known:
            types_of.setdefault(r.row_code, set()).add(r.report_type)
        for row in known:
            formula = row.formula or ""
            if not formula.strip():
                continue
            me, where = pos[(row.report_type, row.row_code)], (std, row.report_type, row.row_code)
            refs, ranges = ROW_REF.findall(formula), SUM_ROW_REF.findall(formula)
            if len(ROW_OPEN.findall(formula)) != len(refs) + len(ranges):
                problems.append(("未识别", *where, formula))
            for code in refs:
                found = types_of.get(code, set())
                if not found:
                    problems.append(("悬空", *where, f"ROW('{code}')"))
                elif row.report_type not in found:
                    problems.append(("跨表", *where, f"ROW('{code}') 在 {sorted(found)}"))
                elif pos[(row.report_type, code)] >= me:
                    problems.append(("前向", *where, f"ROW('{code}')"))
            for start, end in ranges:
                label = f"SUM_ROW('{start}','{end}')"
                members = [r for r in known if start <= r.row_code <= end]
                same = [r for r in members if r.report_type == row.report_type]
                if start not in types_of or end not in types_of or start > end or not same:
                    problems.append(("悬空", *where, f"{label} 端点不存在或区间为空"))
                if any(r.report_type != row.report_type for r in members) or any(
                        e in types_of and row.report_type not in types_of[e] for e in (start, end)):
                    problems.append(("跨表", *where, f"{label} 端点或区间含他表行"))
                later = [r.row_code for r in same if pos[(r.report_type, r.row_code)] >= me]
                if later:
                    problems.append(("前向", *where, f"{label} 含 {later}"))
    return problems


def ref_counts(defs: dict[str, list[DefRow]]) -> dict[str, int]:
    formulas = [r.formula or "" for rows in defs.values() for r in rows]
    return {"row_refs": sum(len(ROW_REF.findall(f)) for f in formulas),
            "sum_row_refs": sum(len(SUM_ROW_REF.findall(f)) for f in formulas)}


def _defs(*rows: tuple) -> dict[str, list[DefRow]]:
    """(报表类型, 行次, 行号, 公式[, 合计行]) → 一套名为 s 的定义。"""
    return {"s": [DefRow(rt, code, num, code, bool(rest and rest[0]), f) for rt, code, num, f, *rest in rows]}


def test_type_order_matches_production():
    assert TYPE_ORDER == tuple(t.value for t in _TYPE_ORDER)


@pytest.mark.parametrize(("defs", "expected"), [
    (_defs((BS, "A-001", 1, "ROW('A-002')"), (BS, "A-002", 2, None)), [("前向", "s", BS, "A-001", "ROW('A-002')")]),
    (_defs((BS, "A-001", 1, "ROW('A-001')")), [("前向", "s", BS, "A-001", "ROW('A-001')")]),
    (_defs((BS, "A-001", 1, "ROW('A-009')")), [("悬空", "s", BS, "A-001", "ROW('A-009')")]),
    (_defs((BS, "A-001", 1, None), (IS, "I-001", 1, "ROW('A-001')")),
     [("跨表", "s", IS, "I-001", "ROW('A-001') 在 ['balance_sheet']")]),
    (_defs((BS, "A-001", 1, None), (BS, "A-002", 2, "SUM_ROW('A-001','A-003')", True), (BS, "A-003", 3, None)),
     [("前向", "s", BS, "A-002", "SUM_ROW('A-001','A-003') 含 ['A-002', 'A-003']")]),
    (_defs((BS, "A-001", 1, None), (BS, "A-002", 2, "SUM_ROW('A-000','A-001')", True)),
     [("悬空", "s", BS, "A-002", "SUM_ROW('A-000','A-001') 端点不存在或区间为空")]),
    (_defs((BS, "A-001", 1, None), (IS, "I-001", 1, None), (IS, "I-002", 2, "SUM_ROW('A-001','I-001')", True)),
     [("跨表", "s", IS, "I-002", "SUM_ROW('A-001','I-001') 端点或区间含他表行")]),
    (_defs((BS, "A-001", 1, None), (BS, "A-002", 2, 'ROW("A-001")')), [("未识别", "s", BS, "A-002", 'ROW("A-001")')]),
    (_defs((BS, "A-001", 1, None), (IS, "A-001", 1, None)),
     [("结构", "s", BS, "A-001", "行次在本套定义里重复（含跨表同码）"),
      ("结构", "s", IS, "A-001", "行次在本套定义里重复（含跨表同码）")]),
    (_defs((BS, "A-001", 1, None), (BS, "A-002", 1, None)),
     [("结构", "s", BS, "A-001", "表内行号 1 重复"), ("结构", "s", BS, "A-002", "表内行号 1 重复")]),
    (_defs(("weird_type", "W-001", 1, None)), [("结构", "s", "weird_type", "W-001", "报表类型不在计算顺序里")]),
], ids=["row_forward", "row_self", "row_dangling", "row_cross", "sum_forward", "sum_dangling", "sum_cross",
        "unrecognized", "dup_code", "dup_number", "unknown_type"])
def test_scanner_reports_each_violation_kind(defs, expected):
    assert ref_problems(defs) == expected


def test_scanner_passes_clean_sample():
    clean = _defs((BS, "A-001", 1, None), (BS, "A-002", 2, "TB('1001','期末余额')"),
                  (BS, "A-003", 3, "ROW('A-001')+ROW('A-002')", True), (BS, "A-004", 4, "SUM_ROW('A-001','A-003')", True),
                  (BS, "A-005", 5, "ROW( 'A-004' ) + ROW('A-003')"), (IS, "I-001", 1, "TB('6001','本期发生额')"),
                  (IS, "I-002", 2, "SUM_ROW('I-001','I-001')", True))
    assert ref_problems(clean) == []
    assert ref_counts(clean) == {"row_refs": 4, "sum_row_refs": 2}, "自检样本空转：引用没被扫到"


def test_seed_row_refs_in_order(request):
    defs = seed_definitions()
    counts = ref_counts(defs)
    request.node.user_properties.append(("seed_counts", str(counts)))
    assert counts["row_refs"] > 0, f"种子没有 ROW 引用：守卫空转（{counts}）"
    assert ref_problems(defs) == []


PURPOSE = "行引用顺序守卫"


@pytest.mark.pg_only
async def test_snapshot_row_refs_in_order(pg_tx, request):
    await require_snapshot(pg_tx, PURPOSE)
    defs = await db_definitions(pg_tx)
    counts = ref_counts(defs)
    request.node.user_properties.extend([("db_counts", str(counts)), ("db_standards", str(sorted(defs)))])
    assert counts["row_refs"] > 0 and counts["sum_row_refs"] > 0, f"快照库没有行引用：守卫空转（{counts}）"
    assert ref_problems(defs) == []


@pytest.mark.pg_only
async def test_snapshot_scan_detects_injected_forward_ref(pg_tx):
    """回滚事务内给国企单体 BS-001「流动资产：」（无公式）写 ``ROW('BS-002')``：库内读取 + 判据必报出这一条前向、且只此一条。"""
    await require_snapshot(pg_tx, PURPOSE)
    updated = await pg_tx.execute(text(
        "UPDATE report_config SET formula = :f WHERE is_deleted = false AND applicable_standard = 'soe_standalone' "
        "AND report_type = 'balance_sheet' AND row_code = 'BS-001' AND coalesce(btrim(formula), '') = ''"),
        {"f": "ROW('BS-002')"})
    assert updated.rowcount == 1
    assert ref_problems(await db_definitions(pg_tx)) == [("前向", "soe_standalone", BS, "BS-001", "ROW('BS-002')")]
