"""跨 sheet 主表去重：「科目余额表」sheet 与「辅助余额表」sheet 各自 convert 后合并。

回归：辅助余额表 sheet 会为同科目再聚合出一条 _aggregated_from_aux 虚拟行，
分 sheet 直接写 tb_balance 会让同科目出现两行（科目余额表重复、下游 SUM 翻倍）。
"""
from __future__ import annotations

from decimal import Decimal

from app.services.ledger_import.converter import (
    convert_balance_rows,
    dedupe_balance_rows_across_sheets,
)


def _summary_sheet() -> list[dict]:
    return [{"account_code": "1002.01", "account_name": "银行存款_活期存款", "company_code": "6601",
             "opening_debit": Decimal("100"), "closing_debit": Decimal("150")}]


def _aux_sheet() -> list[dict]:
    # 同科目、两个辅助维度，只有明细行 → 本 sheet 内会聚合出虚拟汇总行
    return [
        {"account_code": "1002.01", "account_name": "银行存款_活期存款", "company_code": "6601",
         "aux_dimensions": "银行账号:A 账户一",
         "opening_debit": Decimal("40"), "closing_debit": Decimal("60")},
        {"account_code": "1002.01", "account_name": "银行存款_活期存款", "company_code": "6601",
         "aux_dimensions": "银行账号:B 账户二",
         "opening_debit": Decimal("60"), "closing_debit": Decimal("90")},
        {"account_code": "1122.01", "account_name": "应收账款_统驭", "company_code": "6601",
         "aux_dimensions": "客户:C 客户",
         "opening_debit": Decimal("5"), "closing_debit": Decimal("7")},
    ]


def _convert(rows):
    bal, _aux = convert_balance_rows(rows)
    return bal


def test_real_summary_wins_regardless_of_sheet_order():
    real, virt = _convert(_summary_sheet()), _convert(_aux_sheet())
    for combined in (real + virt, virt + real):
        merged = dedupe_balance_rows_across_sheets(combined)
        codes = [r["account_code"] for r in merged]
        assert sorted(codes) == ["1002.01", "1122.01"]
        r1002 = next(r for r in merged if r["account_code"] == "1002.01")
        assert not (r1002.get("raw_extra") or {}).get("_aggregated_from_aux")
        assert r1002["closing_balance"] == Decimal("150")


def test_virtual_only_account_is_kept():
    merged = dedupe_balance_rows_across_sheets(_convert(_summary_sheet()) + _convert(_aux_sheet()))
    r1122 = next(r for r in merged if r["account_code"] == "1122.01")
    assert r1122["raw_extra"]["_aggregated_from_aux"] is True


def _aux_rows(spec):
    """spec: [(维度串, 期初借, 期末借)]；同科目 2202.01，无汇总行。"""
    return [
        {"account_code": "2202.01", "account_name": "应付账款_统驭", "company_code": "6601",
         "aux_dimensions": dims, "opening_debit": Decimal(o), "closing_debit": Decimal(c)}
        for dims, o, c in spec
    ]


def test_same_balance_listed_once_per_dimension_type_is_not_double_counted():
    """源文件把同一笔余额按「客户」和「部门」各列一遍：两个类型汇总相等 ⇒ 只取一个类型。"""
    rows = _aux_rows([
        ("客户:C1 甲", "60", "70"), ("客户:C2 乙", "40", "30"),   # 客户视图：100 / 100
        ("部门:D1 销售", "100", "100"),                             # 部门视图：100 / 100
    ])
    bal, aux = convert_balance_rows(rows)
    assert len(bal) == 1 and len(aux) == 3
    assert bal[0]["closing_balance"] == Decimal("100")      # 不是 200
    assert bal[0]["opening_balance"] == Decimal("100")
    assert bal[0]["raw_extra"]["_aggregated_from_aux"] is True
    assert bal[0]["raw_extra"]["_aux_view_type"] == "客户"   # 行数最多的类型
    assert bal[0]["raw_extra"]["_aux_row_count"] == 2


def test_different_type_totals_are_treated_as_a_partition_and_summed():
    """各类型汇总不同 ⇒ 互不重叠的划分（部分行挂客户、部分挂部门），照旧全部相加。"""
    rows = _aux_rows([("客户:C1 甲", "60", "70"), ("部门:D1 销售", "40", "30")])
    bal, _ = convert_balance_rows(rows)
    assert bal[0]["closing_balance"] == Decimal("100")
    assert "_aux_view_type" not in bal[0]["raw_extra"]


def test_one_row_with_several_dimensions_counted_once():
    rows = _aux_rows([("客户:C1 甲,部门:D1 销售", "60", "70"), ("客户:C2 乙,部门:D2 财务", "40", "30")])
    bal, aux = convert_balance_rows(rows)
    assert len(aux) == 4
    assert bal[0]["closing_balance"] == Decimal("100")   # 每个源行只计一次


def test_single_type_unchanged():
    rows = _aux_rows([("客户:C1 甲", "60", "70"), ("客户:C2 乙", "40", "30")])
    bal, _ = convert_balance_rows(rows)
    assert bal[0]["closing_balance"] == Decimal("100")
    assert "_aux_view_type" not in bal[0]["raw_extra"]


def test_different_company_not_merged():
    a = {"company_code": "A", "account_code": "1002", "raw_extra": None}
    b = {"company_code": "B", "account_code": "1002", "raw_extra": None}
    assert len(dedupe_balance_rows_across_sheets([a, b])) == 2


def test_no_duplicates_returns_same_rows_in_order():
    rows = [{"company_code": "A", "account_code": c} for c in ("1001", "1002", "1003")]
    assert dedupe_balance_rows_across_sheets(rows) == rows


def test_same_priority_keeps_first():
    first = {"company_code": "A", "account_code": "1002", "closing_balance": 1}
    second = {"company_code": "A", "account_code": "1002", "closing_balance": 2}
    assert dedupe_balance_rows_across_sheets([first, second]) == [first]
