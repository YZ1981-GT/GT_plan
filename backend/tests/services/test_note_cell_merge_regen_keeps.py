"""重生成三态合并：old 独有字段保留；明细保留了手工值时，合计按合并后的明细重算。

2026-11-04 真库（【测试】公式同步甲）：调整分录审批 → REPORTS_UPDATED → ``DisclosureEngine.update_note_values`` 重并
119 节。五、5「组合计提项目：应收中央企业客户」的手工明细 100 / 80 还在，合计却被清空（new 的合计按模板明细算，
不含手工值）；119 节的 ``_validation_rules`` 被删（合并从 new 起步，old 独有字段丢掉）。回滚事务复现：
``tmp_note_pull_doc/repro_55.py``。
"""
from __future__ import annotations

import copy

from app.services.note_cell_merge import merge_table_data_preserving_cell_modes

HEADERS = ["账龄", "应收账款", "坏账准备", "预期信用损失率(%)", "应收账款", "坏账准备", "预期信用损失率(%)"]
LABELS = ["1年以内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上"]
RULES = ["余额", "纵向", "账龄衔接"]
EMPTY = [None] * 6


def _table(first, total, *, manual=False):
    rows = [{"label": label, "values": list(first) if i == 0 else list(EMPTY), "is_total": False, "row_type": "data",
             "_cell_modes": {"0": "manual", "3": "manual"} if manual and i == 0 else {}}
            for i, label in enumerate(LABELS)]
    rows.append({"label": "合  计", "values": list(total), "is_total": True, "row_type": "total", "_cell_modes": {}})
    return {"name": "组合计提项目：应收中央企业客户", "headers": list(HEADERS), "rows": rows}


def _old_new():
    """五、5 原样：第一行手工 100 / 80、合计 100 / 80；模板重算这张表没有取数 ⇒ 明细与合计全空。"""
    old = _table([100, None, None, 80, None, None], [100, None, None, 80, None, None], manual=True)
    return old, _table(EMPTY, EMPTY)


def test_multi_table_keeps_old_only_keys_and_recomputes_total_from_preserved_details():
    old_tbl, new_tbl = _old_new()
    first = {"name": "表1", "headers": ["项目", "期末"], "rows": [{"label": "A", "values": [None]}]}
    old = {"_tables": [copy.deepcopy(first), old_tbl], "_validation_rules": RULES,
           "_user_formulas": [{"target": "t1:6:0", "formula": "SUM(0:5, 0)"}],
           "headers": first["headers"], "rows": copy.deepcopy(first["rows"]), "name": "表1"}
    new = {"_tables": [copy.deepcopy(first), new_tbl], "headers": first["headers"], "rows": copy.deepcopy(first["rows"]),
           "name": "表1"}
    merged = merge_table_data_preserving_cell_modes(old, new)
    table = merged["_tables"][1]
    assert table["rows"][0]["values"] == [100, None, None, 80, None, None], "手工明细保留"
    assert table["rows"][-1]["values"] == [100.0, None, None, 80.0, None, None], "合计按合并后的明细重算，不是被清空"
    assert merged["_validation_rules"] == RULES, "old 独有字段保留"
    assert merged["_user_formulas"] == old["_user_formulas"]


def test_single_table_follows_the_same_rules():
    old_tbl, new_tbl = _old_new()
    merged = merge_table_data_preserving_cell_modes({**old_tbl, "_validation_rules": RULES}, new_tbl)
    assert merged["rows"][-1]["values"] == [100.0, None, None, 80.0, None, None]
    assert merged["_validation_rules"] == RULES


def test_totals_follow_new_when_no_detail_was_preserved():
    """明细没有手工 / 锁定格 ⇒ 合计照 new（模板可能另有取数来源），只在合并真改了明细时才重算。"""
    old = _table([100, None, None, 80, None, None], [100, None, None, 80, None, None])  # 都是自动格
    new = _table([5, None, None, 6, None, None], [7, None, None, 8, None, None])
    merged = merge_table_data_preserving_cell_modes(old, new)
    assert merged["rows"][0]["values"] == [5, None, None, 6, None, None]
    assert merged["rows"][-1]["values"] == [7, None, None, 8, None, None]


def test_new_keys_win_and_old_tables_are_not_carried_into_a_single_table():
    """new 有的字段以 new 为准；旧多表、新单表时不带旧 ``_tables``（编辑器优先读它，会显示旧表）。"""
    old_tbl, new_tbl = _old_new()
    old = {"_tables": [old_tbl], "_validation_rules": ["旧"], "rows": copy.deepcopy(old_tbl["rows"]),
           "headers": list(HEADERS)}
    merged = merge_table_data_preserving_cell_modes(old, {**new_tbl, "_validation_rules": ["新"]})
    assert "_tables" not in merged
    assert merged["_validation_rules"] == ["新"]
