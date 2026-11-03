"""粗裁判定规则 4：实质性循环的科目母码跟随下级程序行（spec trim-generation-plan-linkage R4）。

背景：标准程序目录里 D2 / D4 / E1 / F2 四张审定表没有自己的程序行，只有区间 / 普通的下级程序行
（``D2-1至D2-4`` / ``D2-5`` / ``D2-6至D2-13``）。改前「一直找不到程序行 ⇒ 保留」，于是科目程序全部
裁掉之后审定表照样生成。
"""
from __future__ import annotations

import pytest

from app.services.procedure_scope_retention import SUBSTANTIVE_CYCLES, TrimmedScope

NA = "not_applicable"
EX = "execute"

# 标准程序目录里 D2 的三条下级程序行
D2_ROWS = ("D2-1至D2-4", "D2-5", "D2-6至D2-13")


def _scope(*rows: tuple[str, str]) -> TrimmedScope:
    return TrimmedScope.from_rows(rows)


def test_substantive_cycles_are_d_to_n():
    assert SUBSTANTIVE_CYCLES == frozenset("DEFGHIJKLMN")


def test_all_children_trimmed_trims_parent_and_reports_first_child():
    scope = _scope(*((c, NA) for c in D2_ROWS))
    assert scope.is_trimmed("D2")
    assert scope.follows_children("D2")
    # 决定者 = 按编码升序的第一条下级行（Python 与 Java 实现同一结果）
    assert scope.decided_by("D2") == ("D2-1至D2-4", True)
    assert scope.trim_owner("D2") == "D2-1至D2-4"
    assert scope.deciders("D2") == ("D2-1至D2-4", "D2-5", "D2-6至D2-13")
    assert scope.decide("d2 ") == {"wp_code": "d2 ", "decided_by": "D2-1至D2-4", "trimmed": True}


def test_any_child_executing_keeps_parent_and_reports_executing_child():
    scope = _scope(("D2-1至D2-4", NA), ("D2-5", NA), ("D2-6至D2-13", EX))
    assert not scope.is_trimmed("D2")
    assert scope.decided_by("D2") == ("D2-6至D2-13", False), "保留时回报第一条执行的下级行"
    assert scope.follows_children("D2")
    assert scope.trim_owner("D2") is None


def test_deeper_descendants_count_and_execute_wins():
    scope = _scope(("F2-1至F2-14", NA), ("F2-16", NA), ("F2-16-1", EX))
    assert not scope.is_trimmed("F2"), "更深一级的下级行执行 ⇒ 母码保留"
    all_cut = _scope(("F2-1至F2-14", NA), ("F2-16", NA), ("F2-16-1", NA))
    assert all_cut.is_trimmed("F2")
    assert all_cut.deciders("F2") == ("F2-16", "F2-16-1", "F2-1至F2-14")


def test_rule_applies_only_to_parent_itself():
    """没有程序行的同级 / 子码不受影响：只看自己与母码链（规则 1~3），母码跟随下级不往下传。"""
    scope = _scope(*((c, NA) for c in D2_ROWS))
    assert not scope.is_trimmed("D2-14"), "D2-14 自己与母码链都没有程序行 ⇒ 保留（不跟着 D2 的推论走）"
    assert scope.decided_by("D2-14") is None
    assert not scope.is_trimmed("D2A") and scope.decided_by("D2A") is None


def test_own_row_or_lineage_wins_over_children():
    scope = _scope(("D2", EX), *((c, NA) for c in D2_ROWS))
    assert not scope.is_trimmed("D2") and scope.decided_by("D2") == ("D2", False)
    assert not scope.follows_children("D2")
    assert scope.deciders("D2") == ("D2",)
    # 母码链上有行（G4 被裁）⇒ G4-7 跟随 G4，不看 G4-7 自己的下级
    chain = _scope(("G4", NA), ("G4-7-1", EX))
    assert chain.is_trimmed("G4-7") and chain.decided_by("G4-7") == ("G4", True)


@pytest.mark.parametrize("cycle", ["A", "B", "C", "S"])
def test_non_substantive_cycles_do_not_follow_children(cycle):
    scope = _scope((f"{cycle}5-1", NA), (f"{cycle}5-2", NA))
    assert not scope.is_trimmed(f"{cycle}5")
    assert scope.decided_by(f"{cycle}5") is None
    assert not scope.follows_children(f"{cycle}5")


def test_invalid_range_row_is_not_anyones_child():
    """不合法区间按普通编码判定（契约用例），但它的谱系是字符串切出来的，不算 F1-5 / F1 的下级。"""
    scope = _scope(("F1-5至F2-9", NA), ("K3-9至K3-2", NA))
    assert scope.is_trimmed("F1-5至F2-9")
    assert scope.decided_by("F1-5") is None and scope.decided_by("F1") is None
    assert scope.decided_by("K3") is None and not scope.is_trimmed("K3-9")


def test_overlapping_ranges_report_a_matching_representative_and_all_deciders():
    """重叠区间采用 execute-wins；展示决定者必须与结论一致，联动必须认两条来源。"""
    scope = _scope(("D2-1至D2-3", NA), ("D2-2至D2-4", EX))
    assert scope.decided_by("D2-2") == ("D2-2至D2-4", False), "不能回报一条已裁区间却给出保留结论"
    assert scope.deciders("D2-2") == ("D2-1至D2-3", "D2-2至D2-4")
    assert scope.deciders("D2-2至D2-3") == ("D2-1至D2-3", "D2-2至D2-4")

    all_cut = _scope(("D2-1至D2-3", NA), ("D2-2至D2-4", NA))
    assert all_cut.decided_by("D2-2") == ("D2-1至D2-3", True)
    assert all_cut.deciders("D2-2") == ("D2-1至D2-3", "D2-2至D2-4")


def test_range_member_registers_parent_of_member():
    scope = _scope(("E1-1至E1-11", NA), ("E1-14至E1-15", NA), ("E1-18至E1-23", NA), ("E1-26至E1-32", NA))
    assert scope.is_trimmed("E1"), "E1 货币资金只有区间下级行，全部裁掉 ⇒ 不生成"
    restored = _scope(("E1-1至E1-11", EX), ("E1-14至E1-15", NA))
    assert not restored.is_trimmed("E1")


def test_split_and_payload_unchanged_by_children_index():
    scope = _scope(*((c, NA) for c in D2_ROWS))
    assert scope.split(["D2", "D2-14", "D2-3"]) == (["D2-14"], ["D2", "D2-3"])
    # 快照规范形不含派生的下级索引（契约 trimmed-scope.schema.json 不变）
    assert scope.to_payload() == {"exact": {"D2-5": True}, "ranges": {"D2-1至D2-4": True, "D2-6至D2-13": True}}


def test_children_index_ignores_soft_input_noise():
    scope = _scope((" d2-5 ", " NOT_APPLICABLE "), ("", NA), (None, NA))
    assert scope.is_trimmed("D2") and scope.children["D2"] == ("D2-5",)
