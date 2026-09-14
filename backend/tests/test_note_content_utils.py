"""note_content_utils 单元/契约测试（spec: disclosure-notes-selective-generation）。

覆盖 Property 6（has_data 与 _has_content 同口径）、Property 11（not_applicable → false）。
纯函数测试，无需 DB。
"""
from types import SimpleNamespace

from app.services.note_content_utils import effective_table_data, note_has_data
from app.services.note_word_exporter import NoteWordExporter


def _note(**kw):
    kw.setdefault("is_empty", False)
    kw.setdefault("text_content", None)
    kw.setdefault("table_data", None)
    return SimpleNamespace(**kw)


# ── note_has_data 分支 ─────────────────────────────────────────────

def test_is_empty_short_circuits_to_false():
    # Property 11：not_applicable(is_empty) 即使有 text_content 也 False（提前短路）
    assert note_has_data(_note(is_empty=True, text_content="有内容")) is False
    assert note_has_data(_note(is_empty=True, table_data={"rows": [{"values": [100]}]})) is False


def test_text_content_non_empty_true():
    assert note_has_data(_note(text_content="本期发生")) is True


def test_text_content_whitespace_only_falls_through_false():
    assert note_has_data(_note(text_content="   \n\t  ")) is False


def test_table_data_none_or_empty_false():
    assert note_has_data(_note(table_data=None)) is False
    assert note_has_data(_note(table_data={})) is False
    assert note_has_data(_note(table_data={"rows": []})) is False


def test_table_data_has_nonzero_value_true():
    assert note_has_data(_note(table_data={"rows": [{"values": [0, 100]}]})) is True


def test_table_data_all_zero_dash_false():
    # 全 0 / "0" / "-" / 空 → 视为无数据
    td = {"rows": [{"values": [0, "0", "-", "", None]}]}
    assert note_has_data(_note(table_data=td)) is False


def test_table_data_cells_dict_value_and_manual_value():
    # cell 为 dict：优先 value，回退 manual_value
    assert note_has_data(_note(table_data={"rows": [{"cells": [{"value": 5}]}]})) is True
    assert note_has_data(_note(table_data={"rows": [{"cells": [{"manual_value": 7}]}]})) is True
    assert note_has_data(_note(table_data={"rows": [{"cells": [{"value": 0, "manual_value": 0}]}]})) is False


def test_table_data_multi_tables():
    # _tables 多表：任一表有数据即 True
    td = {"_tables": [{"rows": [{"values": [0]}]}, {"rows": [{"values": [42]}]}]}
    assert note_has_data(_note(table_data=td)) is True
    td_empty = {"_tables": [{"rows": [{"values": [0]}]}, {"rows": [{"values": ["-"]}]}]}
    assert note_has_data(_note(table_data=td_empty)) is False


def test_note_has_data_fail_open_on_malformed():
    # 遍历异常 → fail-open 返回 False，不抛
    class Bad:
        is_empty = False
        text_content = None
        table_data = {"rows": "not-a-list"}  # 触发遍历异常路径

    assert note_has_data(Bad()) is False


# ── effective_table_data ───────────────────────────────────────────

def test_effective_table_data_non_dict_returns_as_is():
    assert effective_table_data(None) is None
    assert effective_table_data("x") == "x"


def test_effective_table_data_plain_dict_no_projection():
    # 非 workpaper 来源（无 sub_table_data）→ project_sub_tables 空 → 原样返回
    td = {"rows": [{"values": [1]}]}
    assert effective_table_data(td) == td


# ── Property 6：与 NoteWordExporter._has_content 同口径（同一 helper） ──

def test_has_content_delegates_to_note_has_data():
    # _has_content 委托 note_has_data，不使用 self.db → __new__ 免 __init__ 构造
    exporter = NoteWordExporter.__new__(NoteWordExporter)
    for td in (
        None,
        {},
        {"rows": [{"values": [0]}]},
        {"rows": [{"values": [123]}]},
        {"rows": [{"cells": [{"value": "-"}]}]},
        {"_tables": [{"rows": [{"values": [5]}]}]},
    ):
        n = _note(table_data=td)
        assert exporter._has_content(n) == note_has_data(n)
    # text_content 分支
    n2 = _note(text_content="x")
    assert exporter._has_content(n2) == note_has_data(n2) is True
