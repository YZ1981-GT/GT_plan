"""存量附注表格结构分类（spec disclosure-note-template-word-realignment Task 11，design §4.2）。"""
from __future__ import annotations

from app.services.note_project_table_diff import classify_table, compare_section, db_tables, enriched, summarize

SEED = {"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
        "rows": [{"label": "库存现金"}, {"label": "银行存款"}, {"label": "合计"}]}


def _db(**over) -> dict:
    return {**{"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
               "rows": [{"label": "库存现金", "values": [1, 2]}, {"label": "银行存款", "values": [3, 4]},
                        {"label": "合计", "values": [4, 6]}]}, **over}


def test_db_tables_shapes() -> None:
    assert db_tables(None) == [] and db_tables({}) == []
    assert db_tables({"rows": []}) == [{"rows": []}]  # 旧单表格式
    assert db_tables({"_tables": [_db(), "坏数据"], "rows": []}) == [_db()]


def test_classes_take_the_heaviest_difference() -> None:
    assert classify_table(_db(), SEED)[0] == "一致"
    cls, d = classify_table(_db(name="货币资金明细"), SEED)
    assert (cls, d["whitespace_only"]) == ("仅表头文字不同", False)
    assert classify_table(_db(headers=["项 目", "期末余额", "期初余额"]), SEED)[1]["whitespace_only"] is True
    assert classify_table(_db(rows=[{"label": "库存现金"}, {"label": "合计"}]), SEED)[0] == "行增减"
    # 列数与行都不同 ⇒ 只算列增减（一张表只归一类）
    assert classify_table(_db(headers=["项目", "期末余额"], rows=[]), SEED)[0] == "列增减"


def test_section_count_mismatch_and_summary() -> None:
    a = compare_section({"_tables": [_db()]}, [SEED, SEED])
    b = compare_section(None, [SEED])
    c = compare_section({"_tables": [_db(name="x")]}, [SEED])
    assert (a["count_mismatch"], len(a["tables"]), b["db"], b["tables"]) == (True, 1, 0, [])
    assert summarize([a, b, c]) == {"一致": 1, "仅表头文字不同": 1, "列增减": 0, "行增减": 0, "表数不同（节）": 2,
                                    "比对节数": 3, "其中仅空白差异": 0}


def test_enriched_does_not_mutate_input() -> None:
    td = {"_tables": [_db()]}
    before = repr(td)
    enriched(td, "soe", "八、1")
    assert repr(td) == before
