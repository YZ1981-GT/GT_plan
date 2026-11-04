"""鉴证报告纯函数（spec citar-assurance-report-menus）：TEXT 函数、审核说明显示规则、单体报表行计算、年度文字。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.tax_assurance.common import year_text
from app.services.tax_assurance.fs_rows import account_total, compute_statement, load_config, statement_def
from app.services.tax_assurance.review_notes import Rule, layout, number_text
from app.services.tax_formula_engine import evaluate, parse_formula

D = Decimal


class _Ctx:
    current = None

    def cell(self, sheet, row, col):
        return None


@pytest.mark.parametrize("formula, expected", [
    ('=TEXT(3183610.234,"#,##0.00")', "3,183,610.23"),
    ('=TEXT(0,"#,##0.00")&"元"', "0.00元"),
    ('=TEXT(-1234.5,"#,##0.00")', "-1,234.50"),
    ('=TEXT(0.25,"0%")', "25%"),
    ('=TEXT(12.345,"0.0")', "12.3"),
    ('=TEXT("文字","#,##0.00")', "文字"),
    ('=TEXT(-0.0004,"#,##0.00")', "0.00"),
])
def test_text_function(formula, expected):
    assert evaluate(parse_formula(formula, "S"), _Ctx()) == expected


def test_year_text_only_replaces_fiscal_year():
    s = "被审核单位2025年度…国家税务总局公告2025年第1号… 日期：2026年  月  日"
    assert year_text(s, 2024) == "被审核单位2024年度…国家税务总局公告2025年第1号… 日期：2025年  月  日"


@pytest.mark.parametrize("fmt, n, text", [(1, 1, "一、"), (1, 11, "十一、"), (2, 3, "（三）"), (3, 2, "2、"),
                                          (4, 1, "（1）"), (5, 2, "②"), (6, 4, "IV."), (7, 3, "iii.")])
def test_number_text(fmt, n, text):
    assert number_text(fmt, n) == text


def R(row, template, fmt="文本1", mark="", values=(), number_fmt=None):
    return Rule(row=row, mark=mark, template=template, fmt=fmt, number_fmt=number_fmt, values=list(values))


def texts(rules):
    return [p["text"] for p in layout(rules)]


def test_hidden_section_when_first_body_has_no_amount():
    rules = [
        R(1, "第二部分", fmt="3", mark="※"),
        R(2, "纳税调整", fmt="4", mark="※", number_fmt=1),
        R(3, "收入类", fmt="6", mark="﹟", number_fmt=3),
        R(4, "收入类增加{0}元，减少{1}元。具体调整数据如下：", values=[D(0), D(0)]),
        R(5, "视同销售", fmt="7", mark="﹟", number_fmt=4),
        R(6, "视同销售{0}元", values=[D(0)]),
        R(7, "扣除类", fmt="6", mark="﹟", number_fmt=3),
        R(8, "扣除类增加{0}元。具体调整数据如下：", values=[D(10)]),
        R(9, "招待费", fmt="7", mark="﹟", number_fmt=4),
        R(10, "招待费{0}元，审核确认{1}元；", values=[D(5), D(3)]),
    ]
    # 收入类整节无数据隐藏；扣除类显示，编号从 1 起；招待费是本节最后一项，「；」改「。」
    assert texts(rules) == [
        "第二部分", "一、纳税调整", "1、扣除类", "扣除类增加10.00元。具体调整数据如下：",
        "（1）招待费", "招待费5.00元，审核确认3.00元。",
    ]


def test_always_mark_shows_zero_and_strips_lead_out():
    rules = [
        R(1, "调整", fmt="5", mark="﹟", number_fmt=2),
        R(2, "合计增加{0}元。", values=[D(1)]),
        R(3, "收入类", fmt="6", mark="※", number_fmt=3),
        R(4, "收入类增加{0}元，减少{1}元。具体调整数据如下：", mark="※", values=[D(0), D(0)]),
        R(5, "视同销售", fmt="7", mark="﹟", number_fmt=4),
        R(6, "视同销售{0}元", values=[D(0)]),
    ]
    # ※ 行为 0 也显示；其下内容全隐藏 ⇒ 「具体调整数据如下：」去掉
    assert texts(rules)[-1] == "收入类增加0.00元，减少0.00元。"


def test_dead_rows_and_none_placeholder():
    rules = [
        R(1, "重大事项", fmt="4", mark="※", number_fmt=1),
        R(2, "{0}", values=["0"]),
        R(3, "{0}", values=[None]),
        R(4, "被审核单位名称：{0}；", fmt="文本2", mark="※", values=["甲公司"]),
    ]
    paras = texts(rules)
    assert "0" not in paras
    assert paras[1] == "被审核单位名称：甲公司。"


def test_none_text_for_always_heading_without_visible_body():
    rules = [
        R(1, "重大事项", fmt="4", mark="※", number_fmt=1),
        R(2, "{0}", values=["0"]),
        R(3, "附件1", fmt="4", mark="※"),
    ]
    assert texts(rules) == ["一、重大事项", "无。", "附件1"]


def test_zero_calculation_is_cut():
    rules = [
        R(1, "应纳税额", fmt="5", mark="※", number_fmt=2),
        R(2, "经审核，应纳税额{0}，计算过程如下：应纳所得税额{1}－减免{2}={3}。", mark="※",
          values=["0.00元", "0.00元", "0.00元", "0.00元"]),
        R(3, "应纳税所得额", fmt="5", mark="※", number_fmt=2),
        R(4, "经审核，应纳税所得额{0}，计算过程如下：", mark="※", values=["5.00元"]),
        R(5, "应纳税所得额{0}=利润{1}", mark="※", values=["5.00元", "5.00元"]),
    ]
    assert texts(rules) == [
        "（一）应纳税额", "经审核，应纳税额0.00元。",
        "（二）应纳税所得额", "经审核，应纳税所得额5.00元，计算过程如下：", "应纳税所得额5.00元=利润5.00元",
    ]


def test_list_numbering_only_for_two_or_more():
    rules = [
        R(1, "亏损", fmt="5", mark="﹟", number_fmt=2),
        R(2, "实际弥补{0}元，具体计算过程如下：", values=[D(9)]),
        R(3, "前二年度弥补{0}元；", fmt="文本2", number_fmt=3, values=[D(4)]),
        R(4, "前一年度弥补{0}元；", fmt="文本2", number_fmt=3, values=[D(5)]),
        R(5, "单项", fmt="5", mark="﹟", number_fmt=2),
        R(6, "单项{0}元", values=[D(1)]),
        R(7, "明细{0}元；", number_fmt=5, values=[D(1)]),
    ]
    assert texts(rules) == [
        "（一）亏损", "实际弥补9.00元，具体计算过程如下：", "1、前二年度弥补4.00元；", "2、前一年度弥补5.00元。",
        "（二）单项", "单项1.00元", "明细1.00元。",
    ]


def _list_rules():
    return [
        R(1, "亏损", fmt="5", mark="﹟", number_fmt=2),
        R(2, "实际弥补{0}元，具体计算过程如下：", values=[D(9)]),
        R(3, "前二年度弥补{0}元；", fmt="文本2", number_fmt=3, values=[D(4)]),
        R(4, "前一年度弥补{0}元；", fmt="文本2", number_fmt=3, values=[D(5)]),
        R(5, "本年度弥补{0}元；", fmt="文本2", number_fmt=3, values=[D(6)]),
    ]


def test_edit_replaces_body_and_keeps_auto_number():
    """改过的段用人工正文、编号照旧自动（spec citar-table-manual-edit R8）。"""
    paras = layout(_list_rules(), {"r3": {"text": "前二年度弥补 4 元（已核对）；", "auto": "前二年度弥补4.00元；"}})
    p3 = next(p for p in paras if p["key"] == "r3")
    assert p3["text"] == "1、前二年度弥补 4 元（已核对）；"
    assert p3["number"] == "1、" and p3["edited"] is True and p3["auto_changed"] is False
    assert p3["auto_body"] == "前二年度弥补4.00元；"


def test_deleted_paragraph_renumbers_and_fixes_list_end():
    paras = layout(_list_rules(), {"r4": {"text": None, "auto": "前一年度弥补5.00元；"}})
    assert [p["text"] for p in paras] == [
        "（一）亏损", "实际弥补9.00元，具体计算过程如下：", "1、前二年度弥补4.00元；", "2、本年度弥补6.00元。",
    ]


def test_auto_changed_and_orphan_and_deleted_lists():
    from app.services.tax_assurance.review_notes import layout_with_edits

    edits = {
        "r3": {"text": "改过的", "auto": "前二年度弥补3.00元；"},   # 改后数据变了
        "r5": {"text": None, "auto": "本年度弥补6.00元。"},
        "r99": {"text": "不再显示的段", "auto": "旧文字"},
    }
    out = layout_with_edits(_list_rules(), edits)
    p3 = next(p for p in out["paragraphs"] if p["key"] == "r3")
    assert p3["auto_changed"] is True
    assert [d["key"] for d in out["deleted"]] == ["r5"]
    assert out["deleted"][0]["auto_text"] == "3、本年度弥补6.00元。"
    assert [o["key"] for o in out["orphans"]] == ["r99"]


def test_none_placeholder_has_own_key():
    rules = [R(1, "重大事项", fmt="4", mark="※", number_fmt=1), R(2, "{0}", values=["0"])]
    paras = layout(rules, {"r1-none": {"text": "本期无重大事项。", "auto": "无。"}})
    assert [(p["key"], p["text"]) for p in paras] == [("r1", "一、重大事项"), ("r1-none", "本期无重大事项。")]


def test_money_only_counts_yuan_slots():
    # 人数、万元不算金额：小微企业减免 0 元 ⇒ 不显示
    rules = [
        R(1, "减免", fmt="5", mark="※", number_fmt=2),
        R(2, "减免{0}元（从业人数{1}人，资产总额{2}万元）；", values=[D(0), D(69), D("4360.6")]),
        R(3, "高新{0}元；", values=[D(7)]),
    ]
    assert texts(rules) == ["（一）减免", "高新7.00元。"]


def test_blank_reference_text_slot_stays_empty():
    from app.services.tax_assurance.review_notes import RULES_SHEET, VALUE_COL, blank_text_slots
    rule = R(7, "统一社会信用代码：{0}；账载金额{1}元", values=[D(0), D(0)])
    blank_text_slots([rule], {(RULES_SHEET, 7, VALUE_COL), (RULES_SHEET, 7, VALUE_COL + 1)})
    assert rule.render() == "统一社会信用代码：；账载金额0.00元"


def test_people_count_renders_as_integer():
    rule = R(1, "从业人数{0}人，资产总额{1}万元", values=[D(69), D("4360.6")])
    assert rule.render() == "从业人数69人，资产总额4,360.60万元"


# ── 单体财务报表 ──
def test_account_total_prefix_and_exclude():
    bal = {"2211": D(-100), "221101": D(-60), "221102": D(-30), "22110201": D(-5), "2221": D(-7)}
    assert account_total(bal, "2211!221102") == D(-160)
    assert account_total(bal, "221102") == D(-35)
    assert account_total(bal, "22") == D(-202)


def test_enterprise_system_balance_sheet_balances():
    bs = statement_def("balance_sheet")
    liab = statement_def("balance_sheet_liabilities")
    pl = statement_def("income_statement")
    # 借正贷负：现金 100、应收 50 减坏账 5、固定资产 80 减折旧 20；应付 30、应付工资 10、福利费 2；实收资本 150；
    # 本年损益未结转：收入 −60、成本 +23 ⇒ 未分配利润 = −(−3104…) + 37
    bal = {"1001": D(100), "1122": D(50), "1231": D(-5), "1601": D(80), "1602": D(-20),
           "2202": D(-30), "221101": D(-10), "221102": D(-2), "3001": D(-150), "3201": D(24),
           "6001": D(-60), "6401": D(23)}
    pl_close = D(-60) + D(23)
    a = compute_statement(bs, bal, pl_close)
    b = compute_statement(liab, bal, pl_close)
    assert a[7] == D(100) and a[12] == D(45)
    assert a[29] == D(20) and a[30] == D(60)
    assert a[47] == D(205)
    assert b[9] == D(30) and b[11] == D(10) and b[12] == D(2)
    assert b[43] == D(13)  # 未分配利润：-(24 − 37)
    assert b[46] == a[47]
    p = compute_statement(pl, bal)
    assert p[6] == D(60) and p[7] == D(23) and p[25] == D(37)


def test_cash_flow_by_platform_row_name():
    cf = statement_def("cash_flow_statement")
    vals = {"销售商品、提供劳务收到的现金": D(10), "支付给职工及为职工支付的现金": D(4)}
    out = compute_statement(cf, None, cf_values=vals)
    assert out[6] == D(10) and out[11] == D(4) and out[15] == D(6)
    assert compute_statement(cf, None, cf_values=None)[6] is None


def test_config_formulas_reference_existing_rows():
    import re
    for stmt in load_config()["statements"]:
        rows = {r["r"] for r in stmt["rows"]}
        for r in stmt["rows"]:
            for lo, hi in re.findall(r"SUM\((\d+):(\d+)\)", r.get("formula", "")):
                assert int(lo) in rows and int(hi) in rows, (stmt["key"], r["r"])
            for n in re.findall(r"(?<![:(\d])(\d+)(?![:\d])", re.sub(r"SUM\(\d+:\d+\)", "", r.get("formula", ""))):
                assert int(n) in rows, (stmt["key"], r["r"], n)


def test_manual_override_drives_totals_and_headings_stay_blank():
    """单体报表手工值（spec citar-table-manual-edit R7）：明细改后合计重算；合计行改后不再按公式算。"""
    from app.services.tax_assurance.fs_rows import editable_rows

    cf = statement_def("cash_flow_statement")
    vals = {"销售商品、提供劳务收到的现金": D(10), "支付给职工及为职工支付的现金": D(4)}
    out = compute_statement(cf, None, cf_values=vals, overrides={6: D(30)})
    assert out[6] == D(30) and out[15] == D(26)
    out = compute_statement(cf, None, cf_values=vals, overrides={15: D(1)})
    assert out[15] == D(1)
    headings = {r["r"] for r in cf["rows"] if r.get("heading") or r.get("note")}
    assert headings and not (headings & editable_rows(cf))
    assert all(compute_statement(cf, None, cf_values=vals, overrides={h: D(9) for h in headings})[h] is None for h in headings)
