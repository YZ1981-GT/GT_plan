"""附注比例 / 损失率派生列（spec note-table-structure-formula-pull-closure R2）。

判据：①按真模板 D2 两版逐表认列（账面余额组的比例 = 本行 ÷ 合计行；损失率 / 计提比例 = 准备 ÷ 账面余额，同期间）②分母不在
本表的占比（前五名）不派生、回原因 ③单体预设类型 ``ratio``、带 ``requires``（分子空不算）④合并汇总后合计只加金额列、比例 /
损失率按本表派生（手工格不动、分子空留空）。
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.consol_note_table_totals import build_note_rows
from app.services.note_formula_ratios import derive_ratio, ratio_plans
from app.services.note_formula_tables import table_preset_formulas

DATA = Path(__file__).resolve().parents[1] / "data"


def _table(std: str, section: str, name: str) -> dict:
    doc = json.loads((DATA / f"note_template_{std}.json").read_text(encoding="utf-8"))
    sec = next(s for s in doc["sections"] if s["section_number"] == section)
    return next(t for t in sec["tables"] if t["name"] == name)


def _plans(table: dict) -> list[tuple]:
    plans, _notes = ratio_plans(table)
    return [(p.column, p.kind, p.numerator, p.denominator, p.total_row) for p in plans]


@pytest.mark.parametrize("std, section, name, expected", [
    # 分类表：账面余额组「比例」= 本行金额 ÷ 合计；坏账准备组「预期信用损失率」= 坏账 ÷ 余额
    ("soe", "八、5", "（2）按坏账准备计提方法分类披露应收账款", [(1, "share", 0, None, 5), (3, "rate", 2, 0, None)]),
    ("listed", "五、5", "按坏账计提方法分类披露", [(1, "share", 0, None, 8), (3, "rate", 2, 0, None)]),
    # 国企组合计提分表：账面余额组下「应收账款 / 比例（%）」
    ("soe", "八、5", "组合计提项目：应收中央企业客户", [(1, "share", 0, None, 6)]),
    # 国企其他组合方法：期末 / 期初两组「计提比例」
    ("soe", "八、5", "采用余额百分比或其他组合方法计提坏账准备的应收账款", [(1, "rate", 2, 0, None), (4, "rate", 5, 3, None)]),
    # 上市组合计提：期末 / 期初各一组「预期信用损失率」
    ("listed", "五、5", "组合计提项目：应收中央企业客户", [(2, "rate", 1, 0, None), (5, "rate", 4, 3, None)]),
    # 单项计提：「账龄」是说明列（R1.4），损失率 = 坏账 ÷ 余额
    ("soe", "八、5", "期末单项计提坏账准备的应收账款", [(3, "rate", 1, 0, None)]),
    ("listed", "五、5", "按单项计提坏账准备的应收账款", [(2, "rate", 1, 0, None)]),
])
def test_d2_ratio_columns_from_real_templates(std, section, name, expected):
    assert _plans(_table(std, section, name)) == expected


def test_share_with_denominator_outside_the_table_is_not_derived():
    table = _table("soe", "八、5", "（5）按欠款方归集的期末余额前五名的应收账款")
    plans, notes = ratio_plans(table)
    assert plans == [] and any("分母不在本表" in n for n in notes)


def test_presets_are_ratio_typed_and_require_the_numerator():
    table = _table("soe", "八、5", "（2）按坏账准备计提方法分类披露应收账款")
    formulas, _notes = table_preset_formulas(table, 1)
    share, rate = formulas["t1:0:1"], formulas["t1:0:3"]
    assert share["type"] == rate["type"] == "ratio" and share["category"] == "auto_calc"
    assert share["expression"] == "cell(0,0) / cell(5,0) * 100" and share["requires"] == [[0, 0]]
    assert rate["expression"] == "cell(0,2) / cell(0,0) * 100" and rate["requires"] == [[0, 2]]
    assert "t1:2:1" not in formulas, "「其中：」标记行没有比例"


def test_derive_ratio_skips_blank_numerator_and_zero_denominator():
    table = _table("soe", "八、5", "（2）按坏账准备计提方法分类披露应收账款")
    (share, rate), _ = ratio_plans(table)
    cells = {(0, 0): Decimal(100), (0, 2): Decimal(20), (5, 0): Decimal(1000), (1, 0): Decimal(0)}

    def read(r, c):
        return cells.get((r, c))

    assert derive_ratio(share, 0, read) == Decimal(10)
    assert derive_ratio(rate, 0, read) == Decimal(20)
    assert derive_ratio(share, 3, read) is None, "分子为空不算"
    assert derive_ratio(rate, 1, read) is None, "分母为 0 不写"


def _consol_bad_debt() -> dict:
    """合并模板表经 ``find_table`` 补齐后的形态（叶子表头 + 分组），与上市 五-5-2 同构。"""
    return {
        "headers": ["类别", "金额", "比例(%)", "金额", "预期信用损失率(%)", "账面价值"],
        "_column_groups": [{"group": "账面余额", "start": 1, "span": 2}, {"group": "坏账准备", "start": 3, "span": 2}],
        "rows": [["按单项计提坏账准备"], ["按组合计提坏账准备"], ["合计"]],
    }


@pytest.mark.parametrize("std, sid, kinds", [
    ("listed", "五-5-2", ["share", "rate"]), ("soe", "五-5-2", ["share", "rate", "share", "rate"]),
    ("soe", "五-5-4", ["share", "share"]), ("listed", "五-5-6", ["rate", "rate"]),
])
def test_consolidated_templates_get_the_same_plans(std, sid, kinds):
    from app.services.consol_note_formula_service import find_table

    table = find_table(std, sid)
    shaped = [{"label": r[0] if isinstance(r, list) and r else "", "row_type": rt}
              for r, rt in zip(table["rows"], table["_row_types"])]
    plans, _notes = ratio_plans(table, shaped)
    assert [p.kind for p in plans] == kinds


def test_consolidated_build_derives_ratios_and_sums_only_amount_columns():
    skeleton = [("按单项计提坏账准备", "data"), ("按组合计提坏账准备", "data"), ("合计", "total")]
    amounts = {0: {1: Decimal(200), 2: Decimal(55), 3: Decimal(20)},  # 来源比例 55 混进来也不加总
               1: {1: Decimal(800), 2: Decimal(45), 3: Decimal(40)}}
    built = build_note_rows(skeleton, amounts, width=6, protected=set(), existing_rows=[], table=_consol_bad_debt())
    rows = built.rows
    assert rows[2][1] == "1000.00" and rows[2][3] == "60.00", "合计只加金额列"
    assert [r[2] for r in rows] == ["20.00", "80.00", "100.00"], "比例 = 本行 ÷ 合计 × 100（不是来源比例之和）"
    assert [r[4] for r in rows] == ["10.00", "5.00", "6.00"], "损失率 = 坏账 ÷ 余额 × 100"


def test_consolidated_build_keeps_manual_ratio_and_blank_numerator():
    skeleton = [("按单项计提坏账准备", "data"), ("按组合计提坏账准备", "data"), ("合计", "total")]
    existing = [["按单项计提坏账准备", "", "33.33", "", "", ""], ["按组合计提坏账准备"], ["合计"]]
    built = build_note_rows(skeleton, {1: {1: Decimal(800), 3: Decimal(40)}}, width=6, protected={(0, 2)},
                            existing_rows=existing, table=_consol_bad_debt())
    assert built.rows[0][2] == "33.33", "手工格不动"
    assert built.rows[0][4] == "", "分子为空不写 0"
    assert built.rows[1][2] == "100.00"


def test_consolidated_total_uses_source_sum_when_components_are_blank():
    """判得准的合计行这一列明细全空（单体只给了合计）⇒ 用来源同一行之和（R6.5）。"""
    skeleton = [("1年以内", "data"), ("1至2年", "data"), ("合计", "total")]
    built = build_note_rows(skeleton, {0: {1: Decimal(70)}, 1: {1: Decimal(30)}, 2: {1: Decimal(999), 2: Decimal(12)}},
                            width=3, protected=set(), existing_rows=[])
    assert built.rows[2][1] == "100.00", "明细有数：按明细之和"
    assert built.rows[2][2] == "12.00", "明细全空：来源合计之和"
