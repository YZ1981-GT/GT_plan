"""合并附注表格行组装与合计重算（明细映射拉数与节点子树汇总共用，纯函数）。

spec: consol-note-header-library-and-node-reaggregate Task 9
"""
from __future__ import annotations

from decimal import Decimal

from app.services.consol_note_table_totals import build_table_rows, existing_cell, to_decimal

D = Decimal
SKELETON = [("甲", "data"), ("乙", "data"), ("小计", "subtotal"), ("丙", "data"), ("合计", "total"), ("其中：丁", "data")]


def test_totals_are_table_sums_and_blank_columns_stay_blank():
    rows, filled, kept = build_table_rows(
        SKELETON, {0: {1: D("1.005")}, 1: {1: D("2")}, 3: {1: D("10"), 2: D("0")}, 5: {1: D("7")}},
        width=3, protected=set(), existing_rows=[],
    )
    assert rows[0] == ["甲", "1.01", ""]          # ROUND_HALF_UP
    assert rows[2] == ["小计", "3.01", ""]
    assert rows[4] == ["合计", "13.01", "0.00"]    # 合计加全部数据行（不含小计），整列没数保持空白
    assert rows[5] == ["其中：丁", "7.00", ""]      # 合计行之后的「其中」不进合计
    assert {(f["row"], f["col"]) for f in filled} == {(0, 1), (1, 1), (3, 1), (3, 2), (5, 1)}
    assert kept == []


def test_subtotal_only_sums_its_own_segment():
    skeleton = [("甲", "data"), ("小计", "subtotal"), ("乙", "data"), ("丙", "data"), ("小计", "subtotal"),
                ("合计", "total")]
    rows, _filled, _kept = build_table_rows(
        skeleton, {0: {1: D("1")}, 2: {1: D("2")}, 3: {1: D("4")}}, width=2, protected=set(), existing_rows=[],
    )
    assert [r[1] for r in rows] == ["1.00", "1.00", "2.00", "4.00", "6.00", "7.00"]


def test_manual_cells_kept_even_when_source_has_no_amount_and_feed_totals():
    """手工 / 锁定格一律保留：来源这一格有数 ⇒ 回报「保留了手工值」；没数也不清空（旧实现会清空）。"""
    existing = [["甲", "999.00", "5.00"], ["乙", "", ""], ["小计", "", ""], ["丙", "", ""], ["合计", "1.00", ""]]
    rows, _filled, kept = build_table_rows(
        SKELETON, {0: {1: D("1")}, 3: {1: D("10")}},
        width=3, protected={(0, 1), (0, 2), (4, 1)}, existing_rows=existing,
    )
    assert rows[0] == ["甲", "999.00", "5.00"]
    assert kept == [{"row": 0, "col": 1, "kept_value": "999.00"}]
    assert rows[2] == ["小计", "999.00", "5.00"]   # 保留的手工数参与小计
    assert rows[4] == ["合计", "1.00", "5.00"]     # 合计格本身被保护 ⇒ 不重算


def test_value_parsing_and_existing_cell_shapes():
    assert to_decimal("1,234.50") == D("1234.50") and to_decimal("—") is None and to_decimal(True) is None
    assert to_decimal(float("nan")) is None and to_decimal({"value": "3"}) == D("3") and to_decimal("x") is None
    assert existing_cell([{"values": {"1": "8"}}], 0, 1) == "8" and existing_cell([["a"]], 0, 2) == ""
