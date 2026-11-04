"""税审底稿公式引擎：Excel 语义 + 整本计算模型可解析、函数全部受支持、无环（spec tax-workpaper-data-fetch R4）。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services import tax_formula_engine as fe
from app.services.tax_workbook import TaxWorkbook, load_workbook, parse_a1


class _Ctx:
    def __init__(self, cells: dict[str, object], sheet: str = "S") -> None:
        self.cells = {(sheet, *parse_a1(k)): v for k, v in cells.items()}
        self.current = None

    def cell(self, sheet, row, col):
        return self.cells.get((sheet, row, col))


def ev(formula: str, cells: dict[str, object] | None = None, current: str | None = None):
    ctx = _Ctx({k: (Decimal(str(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
                for k, v in (cells or {}).items()})
    if current:
        ctx.current = parse_a1(current)
    return fe.evaluate(fe.parse_formula(formula, "S"), ctx)


@pytest.mark.parametrize("formula, cells, expected", [
    ("=1+2*3", {}, Decimal(7)),
    ("=-2^2", {}, Decimal(4)),            # Excel：取负先于乘方
    ("=10%", {}, Decimal("0.1")),
    ("=A1+B1", {"A1": 1}, Decimal(1)),     # 空格算 0
    ('=A1&"元"', {"A1": 5}, "5元"),
    ("=SUM(A1:A3)", {"A1": 1, "A2": "文字", "A3": 2}, Decimal(3)),  # 引用里的文字忽略
    ('=SUM(1,"2")', {}, Decimal(3)),       # 直接参数按数值转换
    ("=IF(A1>0,1,2)", {"A1": None}, Decimal(2)),
    ('=IF(A1="",1,2)', {}, Decimal(1)),     # 空格 = 空串
    ("=IFERROR(1/0,9)", {}, Decimal(9)),
    ("=MIN(A1:A2)", {}, Decimal(0)),
    ("=MAX(A1,5,3)", {"A1": 7}, Decimal(7)),
    ("=ROUND(2.345,2)", {}, Decimal("2.35")),
    ("=ROUND(-2.5,0)", {}, Decimal(-3)),   # 四舍五入远离零
    ("=ABS(-3)", {}, Decimal(3)),
    ('=LEFT("税审底稿",2)', {}, "税审"),
    ("=AND(1>0,A1)", {"A1": True}, True),
    ("=OR(A1:A2)", {"A1": False, "A2": None}, False),
    ("=ISNUMBER(A1)", {"A1": "1"}, False),
    ('=SUMIF(A1:A3,"资本化",B1:B3)', {"A1": "资本化", "A2": "费用化", "A3": "资本化", "B1": 1, "B2": 2, "B3": 4}, Decimal(5)),
    ('=SUMIF(A1:A2,">1")', {"A1": 1, "A2": 3}, Decimal(3)),
])
def test_excel_semantics(formula, cells, expected):
    assert ev(formula, cells) == expected


def test_errors_propagate():
    assert ev("=1/0") == fe.DIV0
    assert ev('="a"+1') == fe.VALUE
    assert ev("=NOSUCH(1)") == fe.NAME
    assert ev("=A1+1", {"A1": fe.DIV0}) == fe.DIV0


def test_implicit_intersection_by_formula_column():
    # ='1-12'!F3:G3 写在 F 列：取 F3（样表 A000000!F3 即此写法）
    assert ev("=A1:B1", {"A1": 1, "B1": 2}, current="B5") == Decimal(2)
    assert ev("=A1:B2", {"A1": 1}, current="A1") == fe.VALUE


def test_cross_sheet_and_external_prefix():
    node = fe.parse_formula("='[1]2-01（2）-1'!H23+'2-02'!G18", "X")
    sheets = [r[1] for r in fe.iter_refs(node)]
    assert sheets == ["2-01（2）-1", "2-02"]


def test_whole_model_parses_and_is_acyclic():
    wb = load_workbook()
    assert wb.parse_errors == {}
    assert wb.cyclic == set()
    used = set(wb.model["functions"])
    assert used <= set(fe.FUNCTIONS), f"模型用到未支持的函数：{used - set(fe.FUNCTIONS)}"


def test_workbook_evaluates_in_dependency_order():
    model = {
        "codes": {"T": ["S"]},
        "params_sheet": "P", "params": [], "lists": {}, "rules": [],
        "sheets": {"S": {"print": [1, 1, 3, 3], "cells": {
            "A1": 2, "A2": {"f": "=A1*3"}, "A3": {"f": "=A2+B1"},
        }}},
    }
    wb = TaxWorkbook(model)
    keys = wb.closure(wb.print_keys("S"))
    res = wb.evaluate(keys, {("S", 1, 2): Decimal(1)}, {})
    assert res[("S", 3, 1)] == Decimal(7)


def _override_model() -> TaxWorkbook:
    return TaxWorkbook({
        "codes": {"T": ["S"]}, "params_sheet": "P", "params": [], "lists": {}, "rules": [],
        "sheets": {"S": {"print": None, "cells": {
            "A1": 10, "A2": {"f": "=A1*2"}, "A3": {"f": "=A2+1"}, "A4": {"f": "=MIN(A2,7)"}, "A5": 0.25,
            "A6": {"f": "=A3*A5"},
        }}},
    })


def test_manual_value_overrides_formula_and_flows_downstream():
    """公式格的手工值盖过公式，下游公式按手工值算，原公式值进 auto（spec citar-table-manual-edit R1）。"""
    wb = _override_model()
    keys = wb.closure(wb.print_keys("S"))
    inputs = {("S", 2, 1): Decimal(100)}
    res = wb.evaluate(keys, inputs, {})
    assert res[("S", 2, 1)] == Decimal(100)
    assert res.auto[("S", 2, 1)] == Decimal(20)
    assert res[("S", 3, 1)] == Decimal(101)
    assert wb.cell_value(("S", 2, 1), inputs, {}, res) == Decimal(100)
    assert ("S", 3, 1) not in res.auto  # 没改的格不记原值


def test_manual_blank_formula_is_empty_for_downstream():
    """手工清空（null）：显示空白，下游按空格算（MIN 忽略空格，与 Excel 一致）。"""
    wb = _override_model()
    inputs = {("S", 2, 1): None}
    res = wb.evaluate(wb.closure(wb.print_keys("S")), inputs, {})
    assert wb.cell_value(("S", 2, 1), inputs, {}, res) is None
    assert res[("S", 4, 1)] == Decimal(7)
    assert res[("S", 3, 1)] == Decimal(1)


def test_preset_constant_override_and_auto_value():
    """样表预置数字（税率）可改：手工值参与计算。"""
    wb = _override_model()
    inputs = {("S", 5, 1): Decimal("0.2")}
    res = wb.evaluate(wb.closure(wb.print_keys("S")), inputs, {})
    assert res[("S", 6, 1)] == Decimal("4.2")
    assert wb.cell_value(("S", 5, 1), inputs, {}, res) == Decimal("0.2")


def test_manual_value_breaks_cycle():
    model = {
        "codes": {"T": ["S"]}, "params_sheet": "P", "params": [], "lists": {}, "rules": [],
        "sheets": {"S": {"print": None, "cells": {"A1": {"f": "=A2"}, "A2": {"f": "=A1"}, "A3": {"f": "=A1+1"}}}},
    }
    wb = TaxWorkbook(model)
    res = wb.evaluate(wb.closure(wb.print_keys("S")), {("S", 1, 1): Decimal(5)}, {})
    assert res[("S", 1, 1)] == Decimal(5)
    assert res.auto[("S", 1, 1)] == fe.CIRC


def test_workbook_cycle_is_reported():
    model = {
        "codes": {"T": ["S"]}, "params_sheet": "P", "params": [], "lists": {}, "rules": [],
        "sheets": {"S": {"print": None, "cells": {"A1": {"f": "=A2"}, "A2": {"f": "=A1"}}}},
    }
    wb = TaxWorkbook(model)
    assert wb.cyclic == {("S", 1, 1), ("S", 2, 1)}
    res = wb.evaluate(wb.closure(wb.print_keys("S")), {}, {})
    assert res[("S", 1, 1)] == fe.CIRC
