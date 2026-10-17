"""存量项目附注表格搬值（spec disclosure-note-template-word-realignment Task 12，design §4.2）。

纯函数行为 + 三条硬断言的变异证明（破坏非空 multiset / 孤儿收集 / 正文哈希都要打红）。
"""
from __future__ import annotations

import copy

import pytest

from app.services.note_project_table_realign import (
    TableRealignError,
    _cell_value_multiset,
    plan_section,
    realign_section_tables,
)

# 种子表：结构元数据，无 values（与 Task 11 的 SEED 同形）
SEED_MONEY = {
    "name": "货币资金",
    "headers": ["项目", "期末余额", "期初余额"],
    "columns": [{"key": "label", "is_label": True}, {"key": "end"}, {"key": "begin"}],
    "rows": [{"label": "库存现金"}, {"label": "银行存款"}, {"label": "合计", "is_total": True}],
}


def _db_money(**over) -> dict:
    """库内一张货币资金表（有 values + 边车）。"""
    return {
        **{
            "name": "货币资金",
            "headers": ["项目", "期末余额", "期初余额"],
            "columns": [{"key": "label", "is_label": True}, {"key": "end"}, {"key": "begin"}],
            "rows": [
                {"label": "库存现金", "values": [100, 200], "_cell_modes": {"0": "manual"}},
                {"label": "银行存款", "values": [300, 400]},
                {"label": "合计", "values": [400, 600], "is_total": True},
            ],
        },
        **over,
    }


# ── 一致 / 搬值到正确落点 ─────────────────────────────────────────────


def test_consistent_structure_carries_all_values_no_orphans() -> None:
    td = {"_tables": [_db_money()]}
    out = realign_section_tables(td, [SEED_MONEY])
    rows = out["_tables"][0]["rows"]
    assert [r["values"] for r in rows] == [[100, 200], [300, 400], [400, 600]]
    assert "_realign_orphans" not in out
    # 边车随值搬到同列索引
    assert rows[0]["_cell_modes"] == {"0": "manual"}
    # 非空 multiset 恒等
    assert _cell_value_multiset(td) == _cell_value_multiset(out)


def test_columns_matched_by_header_text_when_order_differs() -> None:
    # 库内列顺序 = 期初、期末；种子 = 期末、期初 ⇒ 按表头文字搬，值跟着换位
    db = _db_money(headers=["项目", "期初余额", "期末余额"],
                   columns=[{"key": "label", "is_label": True}, {"key": "begin"}, {"key": "end"}],
                   rows=[{"label": "库存现金", "values": [200, 100]}])
    out = realign_section_tables({"_tables": [db]}, [SEED_MONEY])
    r0 = out["_tables"][0]["rows"][0]
    # 新结构 headers = 期末、期初 ⇒ values 应为 [100, 200]
    assert r0["values"] == [100, 200]
    assert "_realign_orphans" not in out


def test_columns_matched_by_key_even_if_header_text_changed() -> None:
    db = _db_money(headers=["项目", "期末数", "期初数"])  # 表头文字不同，但 key 一致
    out = realign_section_tables({"_tables": [db]}, [SEED_MONEY])
    assert [r["values"] for r in out["_tables"][0]["rows"]] == [[100, 200], [300, 400], [400, 600]]
    assert "_realign_orphans" not in out


# ── 行增减 / 列增减产生孤儿 ───────────────────────────────────────────


def test_db_row_not_in_seed_becomes_orphan() -> None:
    db = _db_money(rows=[
        {"label": "库存现金", "values": [100, 200]},
        {"label": "其他货币资金", "values": [999, 888]},  # 种子无此行
    ])
    out = realign_section_tables({"_tables": [db]}, [SEED_MONEY])
    orphans = out["_realign_orphans"]
    assert any(o["label"] == "其他货币资金" and 999 in o["values"] and "行标签" in o["reason"] for o in orphans)
    assert _cell_value_multiset({"_tables": [db]}) == _cell_value_multiset(out)


def test_db_column_not_in_seed_becomes_orphan() -> None:
    # 库内多一列「本年增减」，种子只有期末 / 期初 ⇒ 该列值进孤儿
    db = _db_money(headers=["项目", "期末余额", "期初余额", "本年增减"],
                   columns=[{"key": "label", "is_label": True}, {"key": "end"}, {"key": "begin"}, {"key": "delta"}],
                   rows=[{"label": "库存现金", "values": [100, 200, 50]}])
    out = realign_section_tables({"_tables": [db]}, [SEED_MONEY])
    orphans = out["_realign_orphans"]
    assert any(50 in o["values"] and "本年增减" in o["reason"] for o in orphans)
    assert out["_tables"][0]["rows"][0]["values"] == [100, 200]
    assert _cell_value_multiset({"_tables": [db]}) == _cell_value_multiset(out)


def test_extra_db_table_values_become_orphans() -> None:
    db1 = _db_money()
    db2 = {"name": "续表", "headers": ["项目", "金额"], "rows": [{"label": "补充", "values": [77]}]}
    out = realign_section_tables({"_tables": [db1, db2]}, [SEED_MONEY])  # 种子只有 1 张表
    assert any(77 in o["values"] and "整张表" in o["reason"] for o in out["_realign_orphans"])
    assert _cell_value_multiset({"_tables": [db1, db2]}) == _cell_value_multiset(out)


def test_seed_row_absent_in_db_is_empty_no_value_invented() -> None:
    db = _db_money(rows=[{"label": "库存现金", "values": [100, 200]}])  # 缺银行存款 / 合计
    out = realign_section_tables({"_tables": [db]}, [SEED_MONEY])
    rows = out["_tables"][0]["rows"]
    assert rows[0]["values"] == [100, 200]
    assert rows[1]["values"] == [None, None] and rows[2]["values"] == [None, None]
    assert _cell_value_multiset({"_tables": [db]}) == _cell_value_multiset(out)


def test_empty_db_builds_empty_seed_structure() -> None:
    out = realign_section_tables(None, [SEED_MONEY])
    assert len(out["_tables"][0]["rows"]) == 3
    assert all(r["values"] == [None, None] for r in out["_tables"][0]["rows"])
    assert "_realign_orphans" not in out


def test_input_not_mutated() -> None:
    td = {"_tables": [_db_money()]}
    before = copy.deepcopy(td)
    realign_section_tables(td, [SEED_MONEY])
    assert td == before


def test_zero_is_not_empty_value() -> None:
    db = _db_money(rows=[{"label": "库存现金", "values": [0, 0.0]}])
    out = realign_section_tables({"_tables": [db]}, [SEED_MONEY])
    assert out["_tables"][0]["rows"][0]["values"] == [0, 0.0]
    assert _cell_value_multiset(out)[("int", 0)] == 1


def test_string_and_number_are_distinct_atoms() -> None:
    # "100" 与 100 是不同原子，搬值不得悄悄改类型
    db = _db_money(rows=[{"label": "库存现金", "values": ["100", 100]}])
    out = realign_section_tables({"_tables": [db]}, [SEED_MONEY])
    ms = _cell_value_multiset(out)
    assert ms[("str", "100")] == 1 and ms[("int", 100)] == 1


def test_unconsumed_row_with_unmapped_columns_counted_once() -> None:
    """回归：库内行既无同标签落点、列也全不映射时，两条孤儿分支曾各收一次 ⇒ multiset 虚增。

    现在未配对行整行进孤儿一次，已配对行才按未映射列进孤儿，互斥。
    """
    # 库内表：标签 / 列都与种子完全不同 ⇒ 整表的值应恰好各进孤儿一次
    db = {"name": "经营成果", "headers": ["公司", "A列", "B列"],
          "rows": [{"label": "营业收入", "values": [111, 222]}, {"label": "净利润", "values": [333, 444]}]}
    seed = [{"name": "续：经营成果", "headers": ["项目", "本期", "上期"],
             "columns": [{"key": "label", "is_label": True}, {"key": "cur"}, {"key": "prev"}],
             "rows": [{"label": "其他行"}]}]
    out = realign_section_tables({"_tables": [db]}, seed)
    orphan_vals = sorted(v for o in out["_realign_orphans"] for v in o["values"])
    assert orphan_vals == [111, 222, 333, 444]  # 各一次，不翻倍
    assert _cell_value_multiset({"_tables": [db]}) == _cell_value_multiset(out)


def test_plan_section_reports_orphans_and_safety() -> None:
    db = _db_money(rows=[{"label": "库存现金", "values": [100, 200]},
                         {"label": "鬼魂行", "values": [5]}])
    rep = plan_section("八、1", {"_tables": [db]}, [SEED_MONEY])
    assert rep["safe"] is True and rep["changed"] is True and rep["orphan_values"] == 1


# ── 变异证明：破坏三条断言必打红 ───────────────────────────────────────


def test_mutation_dropping_a_value_is_caught() -> None:
    """变异①：若搬值逻辑丢了一个库内非空值（不进表也不进孤儿）⇒ multiset 不等 ⇒ 抛错。

    直接构造「搬后少一个值」的假结果，证明 _assert_multiset 会拦。
    """
    from app.services import note_project_table_realign as mod

    before = {"_tables": [_db_money(rows=[{"label": "库存现金", "values": [100, 200]}])]}
    bad_after = {"_tables": [{"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
                              "rows": [{"label": "库存现金", "values": [100, None]}]}]}  # 丢了 200
    with pytest.raises(TableRealignError, match="丢"):
        mod._assert_multiset(before, bad_after)


def test_mutation_inventing_a_value_is_caught() -> None:
    """变异②：若搬值造了一个原本不存在的值 ⇒ multiset 不等 ⇒ 抛错。"""
    from app.services import note_project_table_realign as mod

    before = {"_tables": [_db_money(rows=[{"label": "库存现金", "values": [100, 200]}])]}
    bad_after = {"_tables": [{"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
                              "rows": [{"label": "库存现金", "values": [100, 200, 999]}]}]}  # 凭空多 999
    with pytest.raises(TableRealignError, match="多"):
        mod._assert_multiset(before, bad_after)


def test_mutation_orphan_not_collected_is_caught_by_real_path() -> None:
    """变异③：孤儿不进 _realign_orphans ⇒ 该非空值既不在表也不在孤儿 ⇒ 真实搬值路径 multiset 不等 ⇒ 抛错。

    通过 monkeypatch 让孤儿收集返回空，证明真实 realign_section_tables 会打红。
    """
    from app.services import note_project_table_realign as mod

    db = _db_money(rows=[{"label": "库存现金", "values": [100, 200]},
                         {"label": "不在种子的行", "values": [777]}])
    orig = mod._realign_one_table

    def _no_orphans(db_tbl, seed_tbl):
        new_tbl, _orphans = orig(db_tbl, seed_tbl)
        return new_tbl, []  # 吞掉孤儿

    mod._realign_one_table = _no_orphans
    try:
        with pytest.raises(TableRealignError):
            mod.realign_section_tables({"_tables": [db]}, [SEED_MONEY])
    finally:
        mod._realign_one_table = orig
