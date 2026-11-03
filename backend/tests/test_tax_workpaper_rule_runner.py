"""税审底稿取数规则执行：科目树、名称匹配、口径、按月、列表溢出、找不到留空（spec tax-workpaper-data-fetch R2 / R3）。

用合成科目树（不连库）驱动 ``RuleRunner``，覆盖生成脚本产出的各类 op。
"""

from __future__ import annotations

from decimal import Decimal as D

from app.services.tax_workpaper_fetch import AccountBook, Node, name_key
from app.services.tax_workpaper_rule_runner import RuleRunner


def _book(monthly=None) -> AccountBook:
    def node(code, name, std, direction, parent=None, **amounts):
        return Node(code=code, name=name, standard=std, direction=direction, parent=parent,
                    **{k: D(str(v)) for k, v in amounts.items()})
    nodes = [
        node("6051", "其他业务收入", "6051", "credit", credit=300, debit=300),
        node("605101", "出租固定资产收入", "6051", "credit", "6051", credit=100, debit=100),
        node("605102", "其他", "6051", "credit", "6051", credit=50, debit=50),
        node("605103", "租金收入", "6051", "credit", "6051", credit=150, debit=150),
        node("6401", "主营业务成本", "6401", "debit", debit=80, credit=80),
        node("1122", "应收账款", "1122", "debit", closing=60, opening=10),
        node("112201", "\\应收账款\\甲公司", "1122", "debit", "1122", closing=40),
        node("112202", "乙公司", "1122", "debit", "1122", closing=20),
        node("112203", "丙公司（零余额）", "1122", "debit", "1122"),
        node("2211", "应付职工薪酬", "2211", "credit", closing=-30),
        node("221102", "职工福利费", "2211", "credit", "2211", opening=-5, debit=7, credit=9, closing=-7),
        node("1601", "固定资产", "1601", "debit", closing=500),
        node("160101", "房屋及建筑物", "1601", "debit", "1601", closing=300),
        node("160199", "其他设备", "1601", "debit", "1601", closing=200),
        node("1602", "累计折旧", "1602", "credit", closing=-90),
        node("160201", "房屋及建筑物", "1602", "credit", "1602", closing=-60, credit=12),
    ]
    tree = {n.code: n for n in nodes}
    for n in nodes:
        if n.parent:
            tree[n.parent].children.append(n.code)
    return AccountBook(tree, monthly)


def _runner(book=None, lists=None, labels=None):
    labels = labels or {}
    return RuleRunner(book or _book(), lists or {}, lambda sheet, ref: labels.get(ref))


def item(op, **kw):
    return {"sheet": "S", "ref": "D1", "rule": "原文", "status": kw.pop("status", "auto"), "op": op, **kw}


def test_name_key_normalizes_path_prefix_and_brackets():
    assert name_key("\\其他应付款\\北京（某）公司") == name_key("北京(某)公司")
    assert name_key("其中：非货币性资产交换收入") == name_key("非货币性资产交换收入")


def test_amount_by_detail_name_and_synonym():
    r = _runner()
    assert r.run(item("amount", path=["其他业务收入", "出租固定资产收入"], measure="credit")).value == D(100)
    # 应付福利费 ≈ 职工福利费；期初贷方 5 → 自然正数 5
    res = r.run(item("amount", path=["应付职工薪酬", "应付福利费"], measure="opening"))
    assert res.value == D(5) and res.issue is None


def test_missing_detail_is_blank_with_reason():
    res = _runner().run(item("amount", path=["其他业务收入", "出租无形资产收入"], measure="credit"))
    assert res.value is None
    assert "未找到明细科目「出租无形资产收入」" in res.issue


def test_closing_direction_measures():
    r = _runner()
    assert r.run(item("amount", path=["累计折旧", "房屋建筑物"], measure="closing_credit")).value == D(60)
    assert r.run(item("amount", path=["累计折旧", "房屋建筑物"], measure="closing_debit")).value == D(0)


def test_label_from_row_cell():
    r = _runner(labels={"B8": "租金收入"})
    res = r.run(item("amount", path=["其他业务收入"], label="B8", measure="credit"))
    assert res.value == D(150)
    # 本行没写科目名：空行，不报问题
    assert _runner().run(item("amount", path=["其他业务收入"], label="B9", measure="credit")).value is None


def test_month_from_ledger_and_missing_ledger():
    monthly = {"6401": {1: (D(30), D(0)), 2: (D(50), D(0))}}
    r = _runner(_book(monthly))
    assert r.run(item("month", path=["主营业务成本"], measure="debit", month=2)).value == D(50)
    res = _runner().run(item("month", path=["主营业务成本"], measure="debit", month=2))
    assert res.value is None and "序时账" in res.issue


def test_manual_rule_never_fetches():
    res = _runner().run(item("amount", status="manual", path=["其他业务收入", "出租固定资产收入"], measure="credit"))
    assert res.value is None and res.status == "manual"


def _list(path, mode, refs, exclude=()):
    return {"sheet": "S", "path": path, "mode": mode, "exclude": list(exclude), "refs": refs}


def test_leaves_list_skips_zero_rows_and_amounts_follow():
    lists = {"L": _list(["应收账款"], "leaves", ["A7", "A8", "A9"])}
    r = _runner(lists=lists)
    names = [r.run(item("list_name", list="L", index=i)).value for i in range(3)]
    assert names == ["甲公司", "乙公司", None]
    amount = r.run(item("list_amount", list="L", index=1, path=["应收账款"], measure="closing"))
    assert amount.value == D(20)


def test_list_overflow_bundles_into_last_row():
    lists = {"L": _list(["应收账款"], "leaves", ["A7"])}
    r = _runner(lists=lists)
    assert r.run(item("list_name", list="L", index=0)).value == "其他（共 2 个科目）"
    assert r.run(item("list_amount", list="L", index=0, path=["应收账款"], measure="closing")).value == D(60)


def test_children_list_excludes_listed_names_but_keeps_qita():
    lists = {"L": _list(["其他业务收入"], "children", ["C14", "C15", "C16"], exclude=["出租固定资产收入", "其   他", "其中："])}
    r = _runner(lists=lists)
    names = [r.run(item("list_name", list="L", index=i)).value for i in range(3)]
    assert names == ["其他", "租金收入", None]


def test_list_amount_across_trees_matches_by_name():
    # 名称列来自「固定资产-房屋建筑物」，金额取「累计折旧-房屋建筑物」下同名明细
    lists = {"L": _list(["固定资产", "房屋建筑物"], "children", ["C11"])}
    r = _runner(lists=lists)
    assert r.run(item("list_name", list="L", index=0)).value == "房屋及建筑物"
    res = r.run(item("list_amount", list="L", index=0, path=["累计折旧", "房屋建筑物"], measure="credit"))
    assert res.value == D(12)


def test_user_overridden_label_is_used_for_amount():
    lists = {"L": _list(["应收账款"], "leaves", ["A7", "A8"])}
    r = _runner(lists=lists, labels={"A7": "乙公司"})
    assert r.run(item("list_amount", list="L", index=0, path=["应收账款"], measure="closing")).value == D(20)


def test_others_sum_excludes_named_categories():
    res = _runner().run(item("others_sum", path=["固定资产"], exclude=["房屋建筑物"], measure="closing_debit"))
    assert res.value == D(200)


def test_empty_book_reports_not_imported():
    res = _runner(AccountBook({})).run(item("amount", path=["其他业务收入"], measure="credit"))
    assert res.value is None and "科目余额表" in res.issue
