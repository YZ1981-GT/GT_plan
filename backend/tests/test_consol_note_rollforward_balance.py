"""变动表逐行勾稽 ``rollforward_balance``：「审核」与勾稽规则列平衡共用（R7.5）。

列平衡原在种子里手写期初 / 增加 / 减少 / 期末四个列号（16 条与表头不符：只认分组的第一列、拿「本期增加」当期末…），
改为标题行库 ``rollforward_columns`` 按表头认，逐行判定与「审核」规则 2 同一个函数。
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.consol_note_table_totals import rollforward_balance
from app.services.note_check_rules import CheckRule, _check_column_balance, rollforward_for
from app.services.note_table_header_library import RollForward

FLOW = RollForward(opening=1, closing=6, increase=(2, 3), decrease=(4,), unknown=(5,))


@pytest.mark.parametrize("row,expected", [
    (["甲", "100", "20", "5", "10", "", "115"], (Decimal("115"), Decimal("115"))),       # 多个增加列都算
    (["乙", "1,000.50", "—", "0.5", "", "", "1,001"], (Decimal("1001.00"), Decimal("1001"))),  # 千分位 / 占位符
    (["丙", "", "50", "", "", "", "50"], (Decimal("50"), Decimal("50"))),                 # 期初空按零
    (["壬", "—", "30", "", "", "", "30"], (Decimal("30"), Decimal("30"))),                # 期初占位符按零
    (["丁", "100", "", "", "", "", "120"], None),                                        # 只填了余额
    (["戊", "100", "20", "", "", "3", "123"], None),                                     # 方向不定的列有数
    (["己", "abc", "20", "", "", "", "120"], None),                                      # 期初有字但不是数
    (["庚", "", "", "", "", "", ""], None),                                              # 全空
    (["辛", "100", "20"], (Decimal("120"), Decimal("0"))),                               # 越界格按零（行比表头短）
])
def test_rollforward_balance_rows(row, expected):
    got = rollforward_balance(FLOW, row)
    if expected is None or got is None:
        assert got == expected
    else:
        assert got == expected and str(got[0]) == str(expected[0])


def _rule(label: str = "*") -> CheckRule:
    return CheckRule(check_id="MV", peer_section_id="", peer_row_label="", peer_col_index=0, self_row_label=label,
                     self_col_index=0, relation="column_balance", tolerance=0.01, description="平衡", mode="column_balance")


def test_column_balance_uses_header_library_columns_and_reports_each_row():
    rows = [["甲", "100", "20", "5", "10", "", "115"], ["乙", "100", "20", "5", "10", "", "120"],
            ["只余额", "100", "", "", "", "", "100"], ["合  计", "200", "40", "10", "20", "", "235"]]
    out = {r.check_id: (r.status, r.expected, r.actual) for r in _check_column_balance(_rule(), rows, FLOW)}
    # 「只余额」一行与「审核」同口径不勾稽；其余逐行报（合计行也按本行的期初 / 增减 / 期末算）
    assert out == {"MV[甲]": ("pass", "115", "115"), "MV[乙]": ("fail", "115", "120"), "MV[合  计]": ("fail", "230", "235")}


def test_column_balance_skips_with_reasons():
    assert [r.reason for r in _check_column_balance(_rule(), [["甲", "1"]], None)] == [
        "标题行库认不出这张表的期初 / 期末 / 增减列（不是变动表）"]
    assert [r.reason for r in _check_column_balance(_rule("合计"), [["甲", "1"]], FLOW)] == ["找不到行「合计」"]
    assert [r.reason for r in _check_column_balance(_rule(), [["甲", "100", "", "", "", "", "100"]], FLOW)] == [
        "本表没有可勾稽的行（期初 / 期末 / 增减都没填，或方向不定的变动列有数）"]
    one = _check_column_balance(_rule("合  计"), [["合  计", "100", "20", "", "", "", "120"]], FLOW)
    assert [(r.check_id, r.status) for r in one] == [("MV", "pass")]


@pytest.mark.parametrize("std,sid,flow", [
    # 国企 投资性房地产（以公允价值计量）：本期增加三列、本期减少两列（原手写列号把「本期增加/公允价值变动损益」当期末）
    ("soe", "五-21-2", RollForward(1, 7, (2, 3, 4), (5, 6), ())),
    # 上市 存货跌价准备：增加 / 减少各两列（原手写只认分组第一列）
    ("listed", "五-9-2", RollForward(1, 6, (2, 3), (4, 5), ())),
])
def test_real_movement_tables_get_every_leaf_column(std, sid, flow):
    assert rollforward_for(std, sid) == flow
