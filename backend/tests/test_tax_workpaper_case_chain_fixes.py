"""spec citar-case-chain-fetch-fixes 底稿取数：「其他」余项、平铺科目、无下级回退、工会经费回退、
未结转损益取净额、事业单位 / 民非专用表只对相应账套取数。合成科目树，不连库。"""

from __future__ import annotations

from decimal import Decimal as D
from types import SimpleNamespace as R

from app.services.tax_workpaper_fetch import build_account_book
from app.services.tax_workpaper_rule_runner import RuleRunner


def _row(code, name, opening=0, debit=0, credit=0, closing=0):
    """余额行：opening / closing 借正贷负（方向随符号），与导入后 tb_balance 同口径。"""
    def side(v):
        return "credit" if v < 0 else "debit"
    return R(account_code=code, account_name=name, opening_balance=D(str(abs(opening))), opening_direction=side(opening),
             debit_amount=D(str(debit)), credit_amount=D(str(credit)),
             closing_balance=D(str(abs(closing))), closing_direction=side(closing))


def item(op, sheet="S", **kw):
    return {"sheet": sheet, "ref": "D1", "rule": "原文", "status": kw.pop("status", "auto"), "op": op, **kw}


def _runner(rows, mapping, rules=(), lists=None, monthly=None):
    return RuleRunner(build_account_book(rows, mapping, monthly), lists or {}, lambda s, r: None, list(rules))


# ── R6：「其他」= 不属于任何具名类别的明细 ──
CATEGORY_RULES = [
    {"sheet": "2-01", "path": ["主营业务收入", "商品销售收入"]},
    {"sheet": "2-01", "path": ["主营业务收入", "提供劳务收入"]},
    {"sheet": "2-01", "path": ["主营业务收入", "其他"]},
]


def test_others_category_is_remainder_of_named_categories():
    rows = [
        _row("5101", "主营业务收入", debit=100, credit=100),
        _row("510101", "宴会收入", debit=60, credit=60),
        _row("510102", "商品销售收入", debit=30, credit=30),
        _row("510103", "外卖收入", debit=10, credit=10),
    ]
    r = _runner(rows, {"5101": "6001"}, CATEGORY_RULES)
    other = r.run(item("amount", sheet="2-01", path=["主营业务收入", "其他"], measure="credit"))
    goods = r.run(item("amount", sheet="2-01", path=["主营业务收入", "商品销售收入"], measure="credit"))
    assert other.value == D(70) and goods.value == D(30)  # 各类别 + 其他 = 一级科目合计
    assert sorted(n.code for n in other.nodes) == ["510101", "510103"]


def test_others_category_without_detail_is_the_account_itself():
    rows = [_row("5401", "主营业务成本", debit=80, credit=80)]
    r = _runner(rows, {"5401": "6401"}, [{"sheet": "2-04", "path": ["主营业务成本", "销售商品"]},
                                          {"sheet": "2-04", "path": ["主营业务成本", "其他"]}])
    res = r.run(item("amount", sheet="2-04", path=["主营业务成本", "其他"], measure="debit"))
    assert res.value == D(80) and res.issue is None


# ── R7：平铺科目表（SAP：无上级行，名称「一级-明细」） ──
FLAT = [
    _row("2211010010", "应付职工薪酬-应付工会经费", opening=-40762.10, closing=-40762.10),
    _row("2211010012", "应付职工薪酬-应付福利费", debit=-6890, credit=-6890),
    _row("2211010007", "应付职工薪酬-应付住房公积金", debit=330683, credit=330683),
    _row("1601010000", "固定资产-机器设备", opening=3466776.64, closing=3466776.64),
    _row("1601060000", "固定资产-其他设备", opening=1091218.12, closing=1091218.12),
    _row("1602010000", "累计折旧-机器设备", credit=318219.84, closing=-1627956.64),
    _row("1602060000", "累计折旧-其他设备", credit=177161.22, closing=-984412.79),
]
FLAT_MAP = {"2211010010": "2211", "2211010012": "2211", "2211010007": "2211",
            "1601010000": "1601", "1601060000": "1601", "1602010000": "1602", "1602060000": "1602"}


def test_flat_chart_detail_found_by_name_after_first_level():
    r = _runner(FLAT, FLAT_MAP)
    assert r.run(item("amount", path=["应付职工薪酬", "工会经费"], measure="opening")).value == D("40762.10")
    assert r.run(item("amount", path=["应付职工薪酬", "应付福利费"], measure="debit")).value == D(-6890)
    assert r.run(item("amount", path=["应付职工薪酬", "住房公积金"], measure="credit")).value == D(330683)


def test_flat_chart_fixed_asset_categories_and_others():
    lists = {
        "M": {"sheet": "S", "path": ["固定资产", "飞机、火车、轮船、机器、机械和其他生产设备"], "mode": "children", "exclude": [], "refs": ["C16"]},
        "O": {"sheet": "S", "path": ["固定资产"], "mode": "others",
              "exclude": ["房屋建筑物", "飞机、火车、轮船、机器、机械和其他生产设备", "电子设备"], "refs": ["C36"]},
    }
    r = _runner(FLAT, FLAT_MAP, lists=lists)
    assert r.run(item("list_name", list="M", index=0)).value == "机器设备"
    assert r.run(item("list_amount", list="M", index=0, path=["累计折旧", "飞机、火车、轮船、机器、机械和其他生产设备"],
                      measure="credit")).value == D("318219.84")
    assert r.run(item("list_name", list="O", index=0)).value == "其他设备"
    assert r.run(item("list_amount", list="O", index=0, path=["累计折旧"], measure="closing_credit")).value == D("984412.79")


# ── R8：一级科目没有下级时列它本身，对应的金额路径同样取本身 ──
def test_account_without_detail_lists_itself_and_pairs_amount():
    rows = [_row("1501", "固定资产", closing=2812506.57), _row("1502", "累计折旧", credit=518626.49, closing=-1062037.94),
            _row("5303", "其他收益", credit=40513.06, debit=40513.06)]
    lists = {
        "O": {"sheet": "S", "path": ["固定资产"], "mode": "others", "exclude": ["房屋建筑物"], "refs": ["C36"]},
        "G": {"sheet": "S", "path": ["其他收益"], "mode": "children", "exclude": [], "refs": ["B8"]},
    }
    r = _runner(rows, {"1501": "1601", "1502": "1602", "5303": "6117"}, lists=lists)
    assert r.run(item("list_amount", list="O", index=0, path=["固定资产"], measure="closing_debit")).value == D("2812506.57")
    assert r.run(item("list_amount", list="O", index=0, path=["累计折旧"], measure="credit")).value == D("518626.49")
    assert r.run(item("list_name", list="G", index=0)).value == "其他收益"
    assert r.run(item("list_amount", list="G", index=0, path=["其他收益"], measure="credit")).value == D("40513.06")


# ── R9 / R10：工会经费挂其他应付款；字序不同的同义词 ──
def test_union_fee_falls_back_to_other_payables_and_housing_fund_does_not():
    rows = [_row("2151", "应付工资", closing=-100), _row("215101", "工资", closing=-100),
            _row("2181", "其他应付款", closing=-200), _row("218101", "工会经费", opening=-49494.99, debit=189928.20,
                                                         credit=183583.95, closing=-43150.74),
            _row("218103", "住房公积金", closing=8690)]
    r = _runner(rows, {"2151": "2211", "2181": "2241"})
    assert r.run(item("amount", path=["应付职工薪酬", "工会经费"], measure="debit")).value == D("189928.20")
    housing = r.run(item("amount", path=["应付职工薪酬", "住房公积金"], measure="credit"))
    assert housing.value is None and "住房公积金" in housing.issue


def test_reordered_disposal_loss_synonym():
    rows = [_row("5601", "营业外支出", debit=8778.73, credit=8778.73), _row("560103", "处置非流动资产损失", debit=8778.73, credit=8778.73)]
    r = _runner(rows, {"5601": "6711"})
    assert r.run(item("amount", path=["营业外支出", "非流动资产处置损失"], measure="debit")).value == D("8778.73")


# ── R12：没结转的损益科目，对方发生额是冲减 ──
def test_unclosed_pl_account_takes_net_and_closed_takes_gross():
    rows = [_row("6401010000", "主营业务成本-内部", debit=14502719.31, credit=2109933.76, closing=12392785.55),
            _row("5401", "主营业务成本", debit=80, credit=80)]
    monthly = {"6401010000": {9: (D(1000), D(300))}}
    unclosed = _runner(rows[:1], {"6401010000": "6401"}, monthly=monthly)
    assert unclosed.run(item("amount", path=["主营业务成本"], measure="debit")).value == D("12392785.55")
    assert unclosed.run(item("month", path=["主营业务成本"], measure="debit", month=9)).value == D(700)
    closed = _runner(rows[1:], {"5401": "6401"})
    assert closed.run(item("amount", path=["主营业务成本"], measure="debit")).value == D(80)


def test_balance_sheet_debit_not_netted():
    rows = [_row("2211010010", "应付职工薪酬-应付工会经费", debit=10, credit=30, closing=-20)]
    r = _runner(rows, {"2211010010": "2211"})
    assert r.run(item("amount", path=["应付职工薪酬", "工会经费"], measure="debit")).value == D(10)


# ── R13：事业单位 / 民非专用表只对相应账套取数 ──
def test_entity_sheet_skipped_for_enterprise_book():
    rules = [{"sheet": "2-01（3)-1", "path": ["事业收入"]}, {"sheet": "2-01（3)-1", "path": ["投资收益"]}]
    rows = [_row("6111010000", "投资收益", credit=161.63, closing=-161.63)]
    enterprise = _runner(rows, {"6111010000": "6111"}, rules)
    res = enterprise.run(item("month", sheet="2-01（3)-1", path=["投资收益"], measure="credit", month=1))
    assert res.value is None and res.issue is None
    # 普通企业表照取
    assert enterprise.run(item("amount", path=["投资收益"], measure="credit")).value == D("161.63")
    institution = _runner(rows + [_row("4101", "事业收入", credit=5, closing=-5)], {"6111010000": "6111"}, rules)
    assert institution.entity_sheet_applies("2-01（3)-1")
