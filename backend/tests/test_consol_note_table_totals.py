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


# ─── 合计构成与单体同一判定（spec note-pull-header-formula-closure R5，note_total_terms） ───


def test_subtotal_less_deduction_total():
    """「小计 / 减：减值准备 / 合计」：合计 = 小计 − 减项（旧算法把减项也加进合计）。"""
    skeleton = [("1年以内", "data"), ("1至2年", "data"), ("小  计", "subtotal"), ("减：减值准备", "data"),
                ("合  计", "total")]
    rows, _f, _k = build_table_rows(
        skeleton, {0: {1: D("100")}, 1: {1: D("50")}, 3: {1: D("15")}}, width=2, protected=set(), existing_rows=[],
    )
    assert [r[1] for r in rows] == ["100.00", "50.00", "150.00", "15.00", "135.00"]


def test_marker_details_not_added_twice():
    """「其中：」标记行下面列的是上一行的明细：合计 = 单项 + 组合，不再加明细。"""
    skeleton = [("按单项计提", "data"), ("按组合计提", "data"), ("其中：", "data"), ("应收中央企业客户", "data"),
                ("应收海外企业客户", "data"), ("合  计", "total")]
    amounts = {0: {1: D("10")}, 1: {1: D("90")}, 3: {1: D("60")}, 4: {1: D("30")}}
    rows, _f, _k = build_table_rows(skeleton, amounts, width=2, protected=set(), existing_rows=[])
    assert rows[5][1] == "100.00"


def test_ambiguous_total_takes_source_amount_or_stays_blank():
    """判不准的合计（「其中：X」行内写法）：写来源同一行之和；没有来源金额留空（旧算法把「其中」也加进合计）。"""
    skeleton = [("交易性金融负债", "data"), ("其中：发行的交易性债券", "data"), ("其他", "data"), ("合  计", "total")]
    rows, filled, _k = build_table_rows(
        skeleton, {0: {1: D("100")}, 1: {1: D("30")}, 2: {1: D("20")}, 3: {1: D("120")}},
        width=3, protected=set(), existing_rows=[],
    )
    assert rows[3] == ["合  计", "120.00", ""] and (3, 1) in {(f["row"], f["col"]) for f in filled}
    rows, _f, _k = build_table_rows(skeleton, {0: {1: D("100")}}, width=2, protected=set(), existing_rows=[])
    assert rows[3] == ["合  计", ""]


def test_title_style_subtotals_sum_rows_below():
    """标题式小计（小计行在本组明细之上）：小计 = 下面本组明细，合计 = 各小计之和。"""
    skeleton = [("商业承兑汇票小计", "subtotal"), ("账龄1", "data"), ("银行承兑汇票小计", "subtotal"),
                ("账龄2", "data"), ("合  计", "total")]
    rows, _f, _k = build_table_rows(
        skeleton, {1: {1: D("7")}, 3: {1: D("3")}}, width=2, protected=set(), existing_rows=[],
    )
    assert [r[1] for r in rows] == ["7.00", "7.00", "3.00", "3.00", "10.00"]


def test_row_type_by_label_checks_subtotal_first():
    from app.services.consol_note_formula_service import _infer_row_type

    assert [_infer_row_type(x) for x in ("小计", "小  计", "小计：", "商业承兑汇票小计", "合 计", "合计：", "总计",
                                          "其他", "")] == [
        "subtotal", "subtotal", "subtotal", "subtotal", "total", "total", "total", "data", "data"]


def test_save_backfill_fills_only_judged_blank_totals():
    from app.services.consol_note_formula_service import backfill_total_rows

    rows = [["1年以内", "100"], ["1至2年", "50.5"], ["小  计", ""], ["减：坏账准备", "15"], ["合  计", ""]]
    assert backfill_total_rows(rows) is True
    assert [r[1] for r in rows] == ["100", "50.5", "150.5", "15", "135.5"]
    kept = [["甲", "1"], ["小计", "9"], ["合计", ""]]
    backfill_total_rows(kept)
    assert kept[1][1] == "9" and kept[2][1] == "9"  # 已有值不覆盖；合计 = 小计
    ambiguous = [["交易性金融负债", "100"], ["其中：发行的交易性债券", "30"], ["合计", ""]]
    assert backfill_total_rows(ambiguous) is False and ambiguous[2][1] == ""


def test_embedded_header_row_is_structure_not_detail():
    """表内子表头（汇总时标 header）不参与合计构成：首行是子表头的标题式小计表仍按标题式算。"""
    skeleton = [("项目", "header"), ("商业承兑汇票小计", "subtotal"), ("账龄1", "data"), ("银行承兑汇票小计", "subtotal"),
                ("账龄2", "data"), ("合  计", "total")]
    rows, _f, _k = build_table_rows(
        skeleton, {2: {1: D("7")}, 4: {1: D("3")}}, width=2, protected=set(), existing_rows=[],
    )
    assert [r[1] for r in rows] == ["", "7.00", "7.00", "3.00", "3.00", "10.00"]


# ─── 「……」占位行不写、手工 / 锁定格按行名对行（spec note-pull-followup-closure R15） ───


def test_placeholder_row_dropped_and_manual_cell_follows_its_row():
    """修复前建的模板把「……」标成固定行：拉数不写这一行；它后面的手工格跟着行名走，不落到上一行。"""
    from app.services.consol_note_table_totals import build_note_rows, remap_cells

    skeleton = [("工资", "data"), ("……", "data"), ("办公费", "data"), ("合计", "total")]
    existing = [["工资", "1.00", ""], ["……", "", ""], ["办公费", "999.00", ""], ["合计", "", ""]]
    built = build_note_rows(skeleton, {0: {1: D("10")}, 2: {1: D("20")}}, width=3, protected={(2, 1)},
                            existing_rows=existing, placeholders=[1])
    assert [r[0] for r in built.rows] == ["工资", "办公费", "合计"]
    assert built.rows[1] == ["办公费", "999.00", ""] and built.rows[2][1] == "1009.00"
    assert built.kept == [{"row": 1, "col": 1, "kept_value": "999.00"}]
    assert built.dropped_placeholders == ["……"] and built.kept_index == {0: 0, 2: 1, 3: 2}
    assert remap_cells({(2, 1), (1, 2)}, built.old_to_new) == ([(1, 1)], [(1, 2)])


def test_placeholder_kept_when_it_got_amounts_or_a_manual_value():
    from app.services.consol_note_table_totals import build_note_rows

    skeleton = [("甲", "data"), ("……", "data"), ("合计", "total")]
    with_amount = build_note_rows(skeleton, {1: {1: D("5")}}, width=2, protected=set(), existing_rows=[],
                                  placeholders=[1])
    assert [r[0] for r in with_amount.rows] == ["甲", "……", "合计"] and not with_amount.dropped_placeholders
    typed = build_note_rows(skeleton, {}, width=2, protected={(1, 1)},
                            existing_rows=[["甲", ""], ["……", "7"], ["合计", ""]], placeholders=[1])
    assert typed.rows[1] == ["……", "7"]
    blank = build_note_rows(skeleton, {}, width=2, protected={(1, 1)},
                            existing_rows=[["甲", ""], ["……", ""], ["合计", ""]], placeholders=[1])
    assert [r[0] for r in blank.rows] == ["甲", "合计"]


def test_row_correspondence_by_name_then_position():
    """按（行名, 同名序号）对；行名改过（同号没被别的行认领）按位置对；插行后不按位置错配。"""
    from app.services.consol_note_table_totals import row_correspondence

    assert row_correspondence(["甲", "乙", "甲"], [["甲"], ["甲"], ["乙"]]) == {0: 0, 1: 2, 2: 1}
    assert row_correspondence(["甲", "新名"], [["甲"], ["旧名"]]) == {0: 0, 1: 1}
    assert row_correspondence(["甲", "插入", "乙"], [["甲"], ["乙"]]) == {0: 0, 2: 1}
    # 旧实现按行号读已保存值：插入一行后「乙」的手工值会落到「插入」上
    rows, _f, kept = build_table_rows([("甲", "data"), ("插入", "data"), ("乙", "data")], {}, width=2,
                                      protected={(1, 1)}, existing_rows=[["甲", ""], ["乙", "8"]])
    assert [r[1] for r in rows] == ["", "", "8"] and kept == []
