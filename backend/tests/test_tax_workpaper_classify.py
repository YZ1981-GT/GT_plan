"""spec citar-audited-balance-and-workpaper-coverage R3 / R4：样表没有取数规则区的表按行标签分类取数、
税收金额默认等于账载。分类口径用生成后的计算模型（``classify_groups``），科目名取自两个案例与辽宁项目的真实账套。"""

from __future__ import annotations

from decimal import Decimal as D
from types import SimpleNamespace as R

import pytest

from app.services.tax_workbook import load_workbook, parse_a1
from app.services.tax_workpaper_fetch import build_account_book
from app.services.tax_workpaper_rule_runner import RuleRunner

WB = load_workbook()
GROUPS = WB.model["classify_groups"]


def _row(code, name, debit=0, credit=0, closing=0):
    side = "credit" if closing < 0 else "debit"
    return R(account_code=code, account_name=name, opening_balance=D(0), opening_direction="debit",
             debit_amount=D(str(debit)), credit_amount=D(str(credit)),
             closing_balance=D(str(abs(closing))), closing_direction=side)


def _runner(rows, mapping):
    return RuleRunner(build_account_book(rows, mapping), WB.model["lists"], lambda s, r: None, WB.model["rules"], GROUPS)


def _rule(sheet, ref):
    return WB.rules[(sheet, *parse_a1(ref))]


def _value(runner, sheet, ref):
    return runner.run(_rule(sheet, ref)).value


# 案例 1（企业会计制度）营业费用：父 5501、部分二级再分三级；已结转（借贷相等、期末 0）
ABC_SALES = [
    ("5501", "营业费用", 0), ("550101", "工资", 7250730.74), ("550103", "办公费", 22704.14),
    ("550104", "通讯费", 44484.37), ("550105", "差旅费", 1211.92), ("550106", "修理费", 0),
    ("55010601", "日常修理费", 124523.84), ("55010602", "装修改造款摊销", 4220853.12), ("550107", "运杂费", 0),
    ("55010701", "外卖运杂费", 18161.09), ("55010702", "其他运杂费", 15309.13), ("550108", "交通费", 4218.99),
    ("550110", "折旧费", 535093.97), ("550111", "租赁费", 0), ("55011101", "房屋租赁费", 2589835.47),
    ("55011102", "其他租赁费", 74135.62), ("550113", "保险费", 26268.78), ("550114", "福利费", 213725.36),
    ("550118", "员工住宿费", 569118.92), ("550120", "职工教育经费", 1600), ("550121", "低值易耗品摊销", 160617.32),
    ("550122", "其他", 1014841.29), ("550124", "宣传推广费", 0), ("55012402", "其他宣传推广费", 124570.82),
    ("550125", "网络平台佣金服务费", 0), ("55012501", "美团外卖服务费", 5075.57), ("55012504", "微信服务费", 31236.52),
    ("550126", "人力资源服务费", 218405.99), ("550127", "劳动保险费", 0), ("55012701", "养老保险", 975682.08),
    ("55012702", "医疗生育保险", 597605.88), ("55012703", "失业保险", 30491.53), ("55012704", "工伤保险", 27486.94),
    ("550128", "住房公积金", 47796),
]


_CODES = [c for c, _, _ in ABC_SALES]
_LEAVES = {c: D(str(a)) for c, _, a in ABC_SALES if not any(o != c and o.startswith(c) for o in _CODES)}


def _abc_rows():
    """上级行的发生额 = 下级末级合计（导入后的余额表就是这样）。"""
    out = []
    for code, name, _ in ABC_SALES:
        v = sum((a for c, a in _LEAVES.items() if c.startswith(code)), D(0))
        out.append(_row(code, name, debit=v, credit=v))
    return out


def test_sales_expense_rows_match_case_1_auditor():
    r = _runner(_abc_rows(), {"5501": "6601"})
    expected = {
        "C9": "7250730.74",     # 工资
        "C10": "782844.28",     # 福利费 + 员工住宿费（审计员同样归入福利费）
        "C11": "1600",          # 职工教育经费
        "C13": "47796",         # 住房公积金
        "C15": "975682.08", "C16": "30491.53", "C17": "597605.88", "C19": "27486.94",
        "C27": "124570.82",     # 宣传推广费
        "C29": "4755947.09",    # 折旧费 + 装修改造款摊销（低值易耗品摊销不进）
        "C31": "67188.51",      # 办公费 + 通讯费
        "C33": "2663971.09",    # 租赁费
        "C35": "1211.92", "C36": "26268.78", "C37": "33470.22", "C38": "124523.84",
    }
    for ref, want in expected.items():
        assert _value(r, "2-08", ref) == D(want), ref
    assert _value(r, "2-08", "C28") is None  # 网络平台佣金服务费：审计员列在其他，不进佣金和手续费
    names = [_value(r, "2-08", f"B{i}") for i in range(45, 66)]
    assert "网络平台佣金服务费" in names and "低值易耗品摊销" in names and "人力资源服务费" in names
    # 各行 + 其他 = 末级合计
    total = sum((_value(r, "2-08", f"C{i}") or D(0)) for i in list(range(9, 14)) + list(range(15, 20)) + list(range(21, 44)))
    total += sum((_value(r, "2-08", f"C{i}") or D(0)) for i in range(45, 66))
    assert total == sum(_LEAVES.values())


def test_flat_sap_names_and_negative_detail():
    """案例 2：平铺科目「人工费用-工资津贴补贴」、股份支付负数、福利费-宿舍费用。"""
    rows = [
        _row("6601030000", "人工费用-工资津贴补贴", debit=7018978.46, closing=7018978.46),
        _row("6601030001", "人工费用-奖金", debit=3719999.32, closing=3719999.32),
        _row("6601030012", "人工费用-股份支付", debit=-100696, closing=-100696),
        _row("6601030007", "人工费用-住房公积金", debit=330683, closing=330683),
        _row("6601030008", "人工费用-补充医疗保险", debit=167.11, closing=167.11),
        _row("6601030011", "人工费用-辞退福利", debit=142364, closing=142364),
        _row("6601040000", "福利费-宿舍费用", debit=-6890, closing=-6890),
        _row("6601050000", "折旧摊销-固定资产折旧", debit=495381.06, closing=495381.06),
        _row("6601130000", "中介机构服务费-咨询服务费", debit=96956.84, closing=96956.84),
    ]
    r = _runner(rows, {c.account_code: "6601" for c in rows})
    assert _value(r, "2-08", "C9") == D("10638281.78")  # 工资 + 奖金 + 股份支付
    assert _value(r, "2-08", "C10") == D(-6890)
    assert _value(r, "2-08", "C13") == D(330683)
    assert _value(r, "2-08", "C22") == D("167.11")
    assert _value(r, "2-08", "C23") == D(142364)
    assert _value(r, "2-08", "C25") == D("96956.84")
    assert _value(r, "2-08", "C29") == D("495381.06")
    assert _value(r, "2-08", "B45") is None  # 全部归进了各行
    # 没有管理费用科目 ⇒ 2-09 第一行给原因，其余行不重复报
    first = r.run(_rule("2-09", "C9"))
    assert first.value is None and "管理费用" in (first.issue or "")
    assert r.run(_rule("2-09", "C10")).issue is None


def test_dotted_long_names_take_last_segment():
    """辽宁：编码 6601.01.07.01、名称「销售费用_职工薪酬_社会保险_基本医疗保险」（无上级行）。"""
    rows = [
        _row("6602.01.07.01", "管理费用_职工薪酬_社会保险_基本医疗保险", debit=225342.66, credit=225342.66),
        _row("6602.01.12.02", "管理费用_职工薪酬_设定提存计划_企业年金", debit=500, credit=500),
        _row("6602.01.06.02", "管理费用_职工薪酬_工资、奖金、津贴和补贴_奖金", debit=2117724.92, credit=2117724.92),
        _row("6602.08.01", "管理费用_摊销费用_低值易耗品摊销", debit=1962.83, credit=1962.83),
        _row("6602.08.02", "管理费用_摊销费用_长期待摊费用摊销", debit=300, credit=300),
        _row("6602.20.01", "管理费用_咨询服务费_年度决算审计费用", debit=1000, credit=1000),
        _row("6602.16.02", "管理费用_办公费_邮电费", debit=75297.37, credit=75297.37),
        _row("6602.99", "管理费用_其他管理费用", debit=10, credit=10),
    ]
    r = _runner(rows, {c.account_code: "6602" for c in rows})
    assert _value(r, "2-09", "C17") == D("225342.66")
    assert _value(r, "2-09", "C21") == D(500)
    assert _value(r, "2-09", "C9") == D("2117724.92")
    assert _value(r, "2-09", "C29") == D(300)          # 长期待摊费用摊销进折旧摊销，低值易耗品摊销不进
    assert _value(r, "2-09", "C25") == D(1000)
    assert _value(r, "2-09", "C31") == D("75297.37")
    rest = {_value(r, "2-09", f"B{i}"): _value(r, "2-09", f"C{i}") for i in range(45, 50)}
    assert rest.get("摊销费用-低值易耗品摊销") == D("1962.83") and rest.get("其他管理费用") == D(10)


def test_taxes_and_finance_rows():
    rows = [
        _row("5402", "税金及附加", debit=1987.47, credit=1987.47),
        _row("540203", "地方教育费附加", debit=10, credit=10),
        _row("540204", "印花税", debit=1977.47, credit=1977.47),
        _row("5503", "财务费用", debit=24895.51, credit=24895.51),
        _row("550301", "利息", debit=-4544.29, credit=-4544.29),
        _row("55030101", "利息收入", debit=-4544.29, credit=-4544.29),
        _row("550302", "手续费", debit=29439.80, credit=29439.80),
        _row("55030201", "网银付款手续费", debit=830.38, credit=830.38),
        _row("55030202", "银行POS手续费", debit=28609.42, credit=28609.42),
    ]
    r = _runner(rows, {"5402": "6403", "5503": "6603"})
    assert _value(r, "2-07", "D12") == D(10) and _value(r, "2-07", "D11") is None  # 地方教育费附加不进教育费附加
    assert _value(r, "2-07", "D15") == D("1977.47")
    assert _value(r, "2-10", "D8") == D("29439.80") and _value(r, "2-10", "D9") == D("-4544.29")


def test_mismatched_parent_total_is_reported():
    """一级科目发生额与末级合计不等 ⇒ 第一行给出原因（各行按末级取数）。"""
    rows = [_row("6602", "管理费用", debit=120), _row("660201", "办公费", debit=100)]
    r = _runner(rows, {"6602": "6602"})
    res = r.run(_rule("2-09", "C9"))
    assert "相差 20" in (res.issue or "")
    assert _value(r, "2-09", "C31") == D(100)


def test_deferred_expense_categories_and_tax_default():
    rows = [_row("1910", "长期待摊费用", debit=74221.02, credit=4218662.88, closing=25408063.77),
            _row("191001", "前期装修工程款", debit=74221.02, credit=4218662.88, closing=25408063.77)]
    r = _runner(rows, {"1910": "1801"})
    assert _value(r, "3-03-04", "B12") == "前期装修工程款"
    assert _value(r, "3-03-04", "E12") == D("4218662.88")
    assert _value(r, "3-03-04", "I12") == D("4218662.88")  # 税收本年摊销默认 = 账载
    assert _value(r, "3-03-04", "B9") is None and _value(r, "3-03-04", "B21") is None


@pytest.mark.parametrize(("sheet", "copies"), [
    ("3-03-01", {"J11": "E11", "M11": "H11", "N11": "H11", "P11": "I11", "J36": "E36"}),
    ("3-03-03", {"H9": "D9", "J9": "F9", "L9": "G9", "H16": "D16"}),
])
def test_tax_columns_default_to_book_columns(sheet, copies):
    for target, source in copies.items():
        t, s = _rule(sheet, target), _rule(sheet, source)
        assert t["status"] == "confirm" and t["op"] == s["op"]
        assert {k: v for k, v in t.items() if k not in ("ref", "rule", "status")} == \
               {k: v for k, v in s.items() if k not in ("ref", "rule", "status")}


def test_every_group_category_row_has_a_rule_and_label():
    for group_id, g in GROUPS.items():
        assert g["categories"], group_id
        for c in g["categories"]:
            assert c["label"].strip(), (group_id, c)
    assert set(WB.model["sheet_notes"]) >= {"3-03-08", "5-01-06", "2-08", "2-09"}


# ── 职工薪酬类审核表：实际发放 / 支出取应付科目 + 默认公式（账载补上后不能把整笔薪酬当未支付全额调增） ──
def _bal(code, name, opening=0, debit=0, credit=0, closing=0):
    """余额行：opening / closing 借正贷负。"""
    def side(v):
        return "credit" if v < 0 else "debit"
    return R(account_code=code, account_name=name, opening_balance=D(str(abs(opening))), opening_direction=side(opening),
             debit_amount=D(str(debit)), credit_amount=D(str(credit)),
             closing_balance=D(str(abs(closing))), closing_direction=side(closing))


def _evaluate(rows, mapping, refs):
    from app.services.tax_workpaper_service import _make_runner

    book = build_account_book(rows, mapping)
    runner = _make_runner(WB, book, {})
    seeds = [(s, *parse_a1(r)) for s, r in refs]
    needed = WB.closure(seeds)
    values = {}
    for key in sorted((k for k in needed if k in WB.rules), key=lambda k: 0 if WB.rules[k]["op"] == "list_name" else 1):
        values[key] = runner.run(WB.rules[key]).value
    computed = WB.evaluate(needed, {}, values)
    return {(s, r): WB.cell_value((s, *parse_a1(r)), {}, values, computed) for s, r in refs}


def test_payroll_actual_payment_case_1():
    """案例 1：工资实际发放 = 年初 + 借方 − 以前年度 + 汇算清缴期（默认年末余额）= 账载，纳税调整 0；
    工会经费回退其他应付款、实际支付 183,583.95、调整 0。与审计员底稿一致。"""
    rows = _abc_rows() + [
        _bal("5502", "管理费用", debit=2112050.73, credit=2112050.73),
        _bal("550201", "工资", debit=1928466.78, credit=1928466.78),
        _bal("550225", "工会经费", debit=183583.95, credit=183583.95),
        _bal("2151", "应付工资", opening=-801686.90, debit=9311758.09, credit=9179197.52, closing=-669126.33),
        _bal("215101", "工资", opening=-801686.90, debit=9311758.09, credit=9179197.52, closing=-669126.33),
        _bal("2181", "其他应付款", opening=-49494.99, debit=189928.20, credit=183583.95, closing=-43150.74),
        _bal("218101", "工会经费", opening=-49494.99, debit=189928.20, credit=183583.95, closing=-43150.74),
    ]
    got = _evaluate(rows, {"5501": "6601", "5502": "6602", "2151": "2211", "2181": "2241"}, [
        ("3-02-01-01", "D16"), ("3-02-01-01", "D22"), ("3-02-01-01", "D27"), ("3-02-01-01", "D34"),
        ("3-02-01-01", "D52"), ("3-02-01-01", "D54"),
        ("3-02-01-04", "D16"), ("3-02-01-04", "D21"), ("3-02-01-04", "D33"), ("3-02-01-04", "D41"),
        ("3-02-01-02", "D16"), ("3-02-01-02", "D32"), ("3-02-01-02", "D42"),
        ("3-02-01-05", "G14"),
    ])
    assert got[("3-02-01-01", "D16")] == D("9179197.52")
    assert got[("3-02-01-01", "D22")] == D("801686.90") and got[("3-02-01-01", "D27")] == D("669126.33")
    assert got[("3-02-01-01", "D34")] == got[("3-02-01-01", "D52")] == D("9179197.52")
    assert got[("3-02-01-01", "D54")] == 0
    assert got[("3-02-01-04", "D16")] == D("183583.95") and got[("3-02-01-04", "D21")] == D("49494.99")
    assert got[("3-02-01-04", "D33")] == D("183583.95") and got[("3-02-01-04", "D41")] == 0
    # 福利费没有应付福利费科目（直接列支）⇒ 未通过应付科目部分默认 = 审核确认额，不调整（14% 限额内）
    assert got[("3-02-01-02", "D32")] == got[("3-02-01-02", "D16")] == D("782844.28")
    assert got[("3-02-01-02", "D42")] == 0
    assert got[("3-02-01-05", "G14")] == 0


def test_payroll_flat_sap_wage_accounts_include_bonus_and_share_based():
    """SAP 平铺：应付工资津贴补贴 + 应付奖金 + 股份支付都算工资（「工资」同义词）；奖金年末未付 ⇒ 汇算清缴期默认按年末余额。"""
    rows = [
        _bal("2211010000", "应付职工薪酬-应付工资津贴补贴", opening=-741421.37, debit=7306964.17, credit=7018978.46, closing=-453435.66),
        _bal("2211010001", "应付职工薪酬-应付奖金", opening=-188552.00, debit=1726224.85, credit=3719999.32, closing=-2182326.47),
        _bal("2211010013", "应付职工薪酬-股份支付", debit=-100696, credit=-100696),
        _bal("2211010012", "应付职工薪酬-应付福利费", debit=-6890, credit=-6890),
    ]
    got = _evaluate(rows, {r.account_code: "2211" for r in rows}, [
        ("3-02-01-01", "D20"), ("3-02-01-01", "D21"), ("3-02-01-01", "D25"), ("3-02-01-02", "D20"),
    ])
    assert got[("3-02-01-01", "D20")] == D("929973.37")
    assert got[("3-02-01-01", "D21")] == D("8932493.02")
    assert got[("3-02-01-01", "D25")] == D("10638281.78")
    assert got[("3-02-01-02", "D20")] == D(-6890)  # 福利费不被工资同义词吞掉
