"""存量项目附注表格搬值（spec disclosure-note-template-word-realignment Task 12，design §4.2）。

纯函数行为 + 三条硬断言的变异证明（破坏非空 multiset / 孤儿收集 / 正文哈希都要打红）。
"""
from __future__ import annotations

import copy
from typing import Any

import pytest

from app.services.note_project_table_realign import (
    TableRealignError,
    _cell_value_multiset,
    plan_section,
    realign_section_tables,
    section_needs_write,
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


# ── 写库判据：只差种子元数据不写（2026-10-31 真库：预演 5 节、写入 104 节，已按备份恢复）──────────


def _seed_money_with_meta() -> dict:
    """种子表带生成链元数据（科目码 / 明细标记 / 表后文字）—— 库内表没有这些键。"""
    seed = copy.deepcopy(SEED_MONEY)
    seed["rows"][0]["account_codes"] = ["1001"]
    seed["rows"][1].update(account_codes=["1002"], is_detail=True)
    seed["text_after_table"] = "注：……"
    return seed


def test_metadata_only_difference_is_not_a_write() -> None:
    # 库内表与种子表名 / 表头 / 行标签 / 值都一致，只差元数据（is_total:false、空边车、无 columns）
    db = {"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
          "rows": [{"label": "库存现金", "values": [100, 200], "is_total": False, "_cell_modes": {}},
                   {"label": "银行存款", "values": [300, 400], "_cell_meta": {}},
                   {"label": "合计", "values": [400, 600], "is_total": True}]}
    td = {"name": db["name"], "headers": db["headers"], "rows": copy.deepcopy(db["rows"]), "_tables": [db]}
    new_td = realign_section_tables(td, [_seed_money_with_meta()])
    assert new_td != td  # 搬值结果确实带了种子元数据
    assert section_needs_write(td, new_td) is False
    assert plan_section("八、1", td, [_seed_money_with_meta()])["changed"] is False


def test_trailing_empty_cells_are_not_a_write() -> None:
    # 库内值数组比表头短（尾部空格没存）⇒ 搬值补成 [100, None]，用户看到的内容不变
    db = {"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
          "rows": [{"label": "库存现金", "values": [100]}, {"label": "银行存款", "values": [300, 400]},
                   {"label": "合计", "values": [400, 600]}]}
    new_td = realign_section_tables({"_tables": [db]}, [SEED_MONEY])
    assert new_td["_tables"][0]["rows"][0]["values"] == [100, None]
    assert section_needs_write({"_tables": [db]}, new_td) is False


@pytest.mark.parametrize("change", ["header", "label", "label_text", "value", "name", "table_count"])
def test_visible_changes_are_writes(change: str) -> None:
    db = _db_money()
    if change == "header":
        db["headers"] = ["项目", "期末数", "期初余额"]  # key 一致，值照搬，表头文字换成种子的
    elif change == "label":
        db["rows"].insert(2, {"label": "", "values": [None, None]})  # 占位空行，种子没有
    elif change == "label_text":
        db["rows"][2]["label"] = "合 计"  # 规范化后同一行，原文不同 ⇒ 写成种子原文
    elif change == "value":
        # 表头文字相同、列 key 指明两列互换 ⇒ 按 key 搬，值换位（只有值变）
        db["columns"] = [{"key": "label", "is_label": True}, {"key": "begin"}, {"key": "end"}]
    elif change == "name":
        db["name"] = "货币资金情况"  # 改名配对，无值可搬时允许
        for r in db["rows"]:
            r["values"] = [None, None]
    td = {"_tables": [db, {"name": "多余", "rows": []}]} if change == "table_count" else {"_tables": [db]}
    new_td = realign_section_tables(td, [SEED_MONEY])
    assert section_needs_write(td, new_td) is True


def test_existing_orphans_alone_are_not_a_write() -> None:
    # 已搬过一次：孤儿区固化在库里，结构已是种子 ⇒ 再搬不写（二次预演为 0 的前提）
    first = realign_section_tables({"_tables": [_db_money(rows=[
        {"label": "库存现金", "values": [100, 200]}, {"label": "鬼魂行", "values": [5]}])]}, [SEED_MONEY])
    assert first["_realign_orphans"]
    second = realign_section_tables(first, [SEED_MONEY])
    assert second["_realign_orphans"] == first["_realign_orphans"]
    assert section_needs_write(first, second) is False


# ── 顶层首表镜像 ─────────────────────────────────────────────────────


def test_top_level_mirror_rebuilt_from_new_first_table() -> None:
    db = _db_money(headers=["项目", "期初余额", "期末余额"],
                   columns=[{"key": "label", "is_label": True}, {"key": "begin"}, {"key": "end"}],
                   rows=[{"label": "库存现金", "values": [200, 100]}])
    td = {"name": db["name"], "headers": db["headers"], "rows": copy.deepcopy(db["rows"]), "_tables": [db],
          "_source": "workpaper"}
    out = realign_section_tables(td, [SEED_MONEY])
    first = out["_tables"][0]
    assert (out["name"], out["headers"], out["rows"]) == (first["name"], first["headers"], first["rows"])
    assert out["rows"][0]["values"] == [100, 200]
    assert out["_source"] == "workpaper"  # 其他顶层键原样保留
    # 镜像不是第二份值：multiset 只算 _tables + 孤儿区
    assert _cell_value_multiset(out) == _cell_value_multiset(td)


def test_no_top_level_mirror_added_when_input_had_none() -> None:
    out = realign_section_tables({"_tables": [_db_money()]}, [SEED_MONEY])
    assert "rows" not in out and "headers" not in out and "name" not in out


# ── 表配对：先按表名，表名配不上的才按剩余表序 ─────────────────────────


def _aging(name: str, end: Any = None, begin: Any = None, both_periods: bool = False) -> dict:
    headers = ["账龄", "应收账款", "坏账准备"] + (["应收账款", "坏账准备"] if both_periods else [])
    width = len(headers) - 1
    total = [end, None] + ([begin, None] if both_periods else [])
    return {"name": name, "headers": headers,
            "rows": [{"label": "1年以内", "values": [None] * width}, {"label": "合计", "values": total[:width]}]}


def test_tables_paired_by_name_when_db_order_differs() -> None:
    """和平 八、5 形态：库内续表排在最后，结构相同的兄弟表按表序配会互相串值。"""
    db = [_aging("组合：中央企业", end=11), _aging("组合：海外企业", end=22),
          _aging("组合：中央企业（续：期初数）", end=33), _aging("组合：海外企业（续：期初数）", end=44)]
    seed = [{**_aging(n), "rows": [{"label": "1年以内"}, {"label": "合计"}]} for n in
            ("组合：中央企业", "组合：中央企业（续：期初数）", "组合：海外企业", "组合：海外企业（续：期初数）")]
    out = realign_section_tables({"_tables": db}, seed)
    got = {t["name"]: t["rows"][1]["values"][0] for t in out["_tables"]}
    assert got == {"组合：中央企业": 11, "组合：中央企业（续：期初数）": 33,
                   "组合：海外企业": 22, "组合：海外企业（续：期初数）": 44}
    assert "_realign_orphans" not in out


def test_unpaired_db_table_values_become_orphans_even_if_same_name_exists() -> None:
    # 库内同名两张（重复生成）：第一张配种子，第二张没得配 ⇒ 值进孤儿，不并进第一张
    db = [_aging("计划资产", end=1), _aging("计划资产", end=2)]
    out = realign_section_tables({"_tables": db}, [{**_aging("计划资产"), "rows": [{"label": "合计"}]}])
    assert out["_tables"][0]["rows"][0]["values"][0] == 1
    assert [o["values"] for o in out["_realign_orphans"]] == [[2]]
    assert "整张表" in out["_realign_orphans"][0]["reason"]


def test_renamed_pair_carrying_values_is_refused() -> None:
    """种子改了表名、库内只能按剩余表序配上：要搬非空值 ⇒ 不猜，整节拒绝（plan 报不安全）。"""
    db = [_aging("组合：中央企业", end=11), _aging("旧表名", end=99)]
    seed = [{**_aging(n), "rows": [{"label": "合计"}]} for n in ("组合：中央企业", "新表名")]
    with pytest.raises(TableRealignError, match="表名不同"):
        realign_section_tables({"_tables": db}, seed)
    rep = plan_section("八、5", {"_tables": db}, seed)
    assert rep["safe"] is False and "旧表名" in rep["error"]


def test_renamed_pair_without_values_follows_seed() -> None:
    db = [_aging("组合：中央企业", end=11), _aging("旧表名")]
    seed = [{**_aging(n), "rows": [{"label": "合计"}]} for n in ("组合：中央企业", "新表名")]
    out = realign_section_tables({"_tables": db}, seed)
    assert [t["name"] for t in out["_tables"]] == ["组合：中央企业", "新表名"]
    assert out["_tables"][0]["rows"][0]["values"][0] == 11


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
