"""附注主表单元格定位 / 读写（note_writer 纯函数）。

spec: chain-closure-phase2-formula-push-engine · 任务 10 · design §五 附注单元格

读写口径必须与附注渲染的投影器 ``note_sub_table_projector`` 一致，否则写了也看不见：
- 只认 ``_source ∈ {workpaper, workpaper_html}`` 的 ``sub_table_data``（F1 模板取数章节不推）；
- 标签列 = 首个 ``is_label``，否则首列；数值列按列序；
- 行里已有业务键优先于 ``values[i]``（投影器逆投影「已存在的业务键不被覆盖」）。
形态样本取自真库（2026-09-29 现查：宜宾 八、1 F2 旧标签「现金」、重药 五、1 F2、陕西华氏 八、1 F3）。
"""
from __future__ import annotations

import copy

import pytest

from app.services.formula_push import note_writer as nw
from app.services.note_sub_table_projector import project_sub_tables

COLS = [
    {"key": "label", "flat": True, "label": "项目", "is_label": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "期初余额", "format": "amount"},
]


def f2(**over) -> dict:
    td = {
        "_source": "workpaper",
        "_sub_table_columns": {"货币资金": copy.deepcopy(COLS)},
        "sub_table_data": {"货币资金": [
            {"label": "现金", "end_amount": 0, "prior_amount": 0},
            {"label": "银行存款", "end_amount": 10, "prior_amount": 5},
            {"label": "合计", "is_total": True, "end_amount": 10, "prior_amount": 5},
            {"label": "其中：存放在境外的款项总额", "end_amount": 3, "prior_amount": 0},
        ]},
    }
    td.update(over)
    return td


def f3() -> dict:
    return {
        "_source": "workpaper",
        "_sub_table_columns": {"货币资金": copy.deepcopy(COLS)},
        "sub_table_data": {"货币资金": [
            {"label": "库存现金", "values": [1.0, 2.0], "row_type": "data", "_cell_modes": {"0": "auto"}},
            {"label": "数字货币", "values": [None, None], "_cell_modes": {"0": "manual", "1": "locked"}},
            {"label": "合计", "values": [1.0, 2.0], "is_total": True, "row_type": "total"},
        ]},
    }


# ── 定位 ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("td, fragment", [
    (None, "尚无表格"),
    ({}, "尚无表格"),
    # sub_table_data 在但来源明确非底稿：投影器不渲染 sub_table_data，写了用户也看不见
    ({"_source": "template", "sub_table_data": {"货币资金": []}}, "模板取数维护"),
    ({"_source": "workpaper", "sub_table_data": {"受限制的货币资金明细": []}}, "没有「货币资金」表"),
])
def test_locate_table_refuses_what_the_projector_would_not_render(td, fragment):
    table, reason = nw.locate_table(td, "货币资金")
    assert table is None and fragment in reason


def test_locate_table_source_null_old_format_rows_accepted():
    """_source=None + 顶层 rows（旧格式）→ 旧格式兜底返回 NoteTable（需求 1.2）。
    真库和平药房 / 首汽此前被一刀切拦截，现在放行。"""
    td = {"rows": [{"label": "库存现金", "values": [1, 2]}], "headers": ["项目"]}
    table, reason = nw.locate_table(td, "货币资金")
    assert reason is None and table is not None
    assert table.rows == [{"label": "库存现金", "values": [1, 2]}]


def test_locate_table_source_null_sub_table_accepted():
    """_source=None + sub_table_data 存在 → 放行（需求 1.1）。
    仅 _source 明确为非底稿值（template/import/migration）时才拦截。"""
    td = {"sub_table_data": {"货币资金": []}}
    table, reason = nw.locate_table(td, "货币资金")
    assert reason is None and table is not None


@pytest.mark.parametrize("source", ["workpaper", "workpaper_html"])
def test_locate_table_accepts_projector_sources(source):
    table, reason = nw.locate_table(f2(_source=source), "货币资金")
    assert reason is None and table.value_keys == ["end_amount", "prior_amount"]
    assert table.section_locked is False
    # 与投影器同源：投影器对这两种来源确实渲染 sub_table_data
    assert project_sub_tables(f2(_source=source))


def test_value_keys_label_column_falls_back_to_first_column():
    """无 is_label 声明时投影器取首列为标签列（_pick_label_def）—— 数值列序必须同口径。"""
    td = f2(_sub_table_columns={"货币资金": [{"key": "label"}, {"key": "end_amount"}, {"key": "prior_amount"}]})
    table, _ = nw.locate_table(td, "货币资金")
    assert table.value_keys == ["end_amount", "prior_amount"]


@pytest.mark.parametrize("where", ["top", "sub"])
def test_manual_override_locks_whole_section(where):
    td = f2()
    (td if where == "top" else td["sub_table_data"])["_manual_override"] = True
    table, _ = nw.locate_table(td, "货币资金")
    assert table.section_locked is True
    assert nw.external_mode(table.section_locked, None) == "locked"


def test_find_row_prefers_note_label_then_workpaper_label_and_skips_total():
    rows = f2()["sub_table_data"]["货币资金"]
    # 宜宾历史同步把国企首行写成底稿字面「现金」：附注字面「库存现金」找不到时退回底稿字面
    assert nw.find_row(rows, ["库存现金", "现金"]) == 0
    assert nw.find_row(rows, ["银行存款"]) == 1
    assert nw.find_row(rows, ["合计"]) is None, "合计行只能经 find_total_row 定位"
    assert nw.find_row(rows, ["数字货币"]) is None
    assert nw.find_total_row(rows) == 2
    assert nw.find_total_row([{"label": "合计", "row_type": "total", "values": []}]) == 0


# ── 读写 ──────────────────────────────────────────────────────────────────


def test_f2_read_write_business_keys_and_projection_shows_written_value():
    td = f2()
    table, _ = nw.locate_table(td, "货币资金")
    assert nw.read_cell(table.rows[1], "end_amount", table.value_keys) == (True, 10, None)
    nw.write_cell(table.rows[1], "end_amount", 1234.5, table.value_keys)
    nw.write_cell(table.rows[1], "prior_amount", 100.0, table.value_keys)
    assert table.rows[1] == {"label": "银行存款", "end_amount": 1234.5, "prior_amount": 100}
    assert isinstance(table.rows[1]["prior_amount"], int), "整数值须落 int（与前端 JSON.stringify 一致）"
    projected = project_sub_tables(td)[0]["rows"][1]
    assert projected["values"] == [1234.5, 100]


def test_f3_read_write_positional_values_and_cell_modes():
    td = f3()
    table, _ = nw.locate_table(td, "货币资金")
    assert nw.read_cell(table.rows[0], "end_amount", table.value_keys) == (True, 1.0, "auto")
    assert nw.read_cell(table.rows[1], "end_amount", table.value_keys) == (True, None, "manual")
    assert nw.read_cell(table.rows[1], "prior_amount", table.value_keys) == (True, None, "locked")
    nw.write_cell(table.rows[0], "prior_amount", 9.0, table.value_keys)
    assert table.rows[0]["values"] == [1.0, 9]
    assert "prior_amount" not in table.rows[0], "F3 行不得新增业务键（否则遮住 values 形态）"
    assert project_sub_tables(td)[0]["rows"][0]["values"] == [1.0, 9]


def test_f3_short_values_are_padded_and_unknown_column_is_unlocatable():
    row = {"label": "库存现金", "values": [5.0]}
    assert nw.read_cell(row, "prior_amount", ["end_amount", "prior_amount"]) == (True, None, None)
    nw.write_cell(row, "prior_amount", 7.0, ["end_amount", "prior_amount"])
    assert row["values"] == [5.0, 7]
    assert nw.read_cell(row, "prior_amount", ["end_amount"]) == (False, None, None)


def test_business_key_wins_over_values_like_the_projector():
    """两种形态并存时投影器显示业务键 ⇒ 读写都必须落在业务键上，写 values 用户看不见。"""
    td = f3()
    row = td["sub_table_data"]["货币资金"][0]
    row["end_amount"] = 50.0
    table, _ = nw.locate_table(td, "货币资金")
    assert nw.read_cell(table.rows[0], "end_amount", table.value_keys)[1] == 50.0
    nw.write_cell(table.rows[0], "end_amount", 60.0, table.value_keys)
    assert table.rows[0]["end_amount"] == 60 and table.rows[0]["values"][0] == 1.0
    assert project_sub_tables(td)[0]["rows"][0]["values"][0] == 60


@pytest.mark.parametrize("locked, mode, expected", [
    (False, None, None), (False, "auto", None), (False, "manual", "manual"),
    (False, "locked", "locked"), (True, None, "locked"), (True, "manual", "locked"),
])
def test_external_mode(locked, mode, expected):
    assert nw.external_mode(locked, mode) == expected


def test_total_formula_sums_rows_before_total_only():
    rows = f2()["sub_table_data"]["货币资金"]
    rows[0]["end_amount"] = 1.25
    rows[1]["end_amount"] = "2.5"          # 字符串数值按 JS Number 读
    rows.insert(1, {"label": "空行", "end_amount": None})
    total = nw.find_total_row(rows)
    # 「其中：」在合计之后 ⇒ 不计入；None 按 0
    assert nw.total_formula(rows, total, "end_amount", []) == 3.75
    f3_rows = f3()["sub_table_data"]["货币资金"]
    assert nw.total_formula(f3_rows, 2, "end_amount", ["end_amount", "prior_amount"]) == 1.0
