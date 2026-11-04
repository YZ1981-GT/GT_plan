"""四套报表模板（国企 / 上市 × 单体 / 合并）合计行与少数明细行的正确公式（单一来源）。

为什么要单独列出来：
- 合计行公式原先由 ``fill_all_formulas`` 按行名套 CAS 模板公式（``multi_standard_report_formats.json``），
  但 CAS 公式里的 ``ROW('BS-009')`` 是 **CAS 模板自己的行号**（在 CAS 里是流动资产合计），套到国企模板上
  指向「应收款项融资」⇒ 资产总计 = 应收款项融资 + 应收资金集中管理款。四套模板全部中招。
- 兜底的 ``SUM_ROW('起','止')`` 按行号区间求和，会把「其中：」子项与父项一起加（流动负债合计多加应付股利等）。

这里每个合计行写成「逐行相加 / 相减」，只列本层项目、跳过「其中：」子项与标题行；明细行只收「原公式取错科目」的几行。
消费方：``scripts/fix/fix_report_total_formulas.py``（全局发布到现有库）与
``report_formula_service.fill_all_formulas``（新库首次填公式时最先查这里）。

行名只做前缀核对（``row_name.startswith``）：行名里有全角括号 / 引号 / ▲△ 等，前缀足以防止行号漂移时改错行。
"""

from __future__ import annotations


def _rows(*codes: str, minus: tuple[str, ...] = ()) -> str:
    plus = " + ".join(f"ROW('{c}')" for c in codes)
    return plus + "".join(f" - ROW('{c}')" for c in minus)


def _bs(codes: str) -> list[str]:
    return [f"BS-{c}" for c in codes.split()]


def _is(codes: str) -> list[str]:
    return [f"IS-{c}" for c in codes.split()]


#: 存货 = 各存货科目 − 贷方性质的存货备抵（试算表存自然正数，区间求和会把备抵当正数加上）
INVENTORY_FORMULA = (
    "TB('1401','期末余额')+TB('1402','期末余额')+TB('1403','期末余额')+TB('1404','期末余额')"
    "+TB('1405','期末余额')+TB('1406','期末余额')-TB('1407','期末余额')+TB('1408','期末余额')"
    "+TB('1411','期末余额')+TB('1421','期末余额')+TB('1431','期末余额')+TB('1441','期末余额')"
    "+TB('1451','期末余额')-TB('1461','期末余额')+TB('1471','期末余额')+TB('1472','期末余额')"
)
#: 现行报表格式：应收利息 / 应收股利并入其他应收款（报表上的「其中」是它的子集）
_OTHER_RECEIVABLES = "TB('1221','期末余额')+TB('1131','期末余额')+TB('1132','期末余额')"
_OTHER_PAYABLES = "TB('2241','期末余额')+TB('2231','期末余额')+TB('2232','期末余额')"

#: 本层不填数的明细行（取不到正确科目：利息收入 / 利息费用是财务费用的子项，平台科目表没有拆分科目；
#: 每股收益不是试算表数；「以摊余成本计量的金融资产终止确认收益」是投资收益的子项，原取 6111 与投资收益重复）
_EMPTY = None

#: 权益类按平台标准科目表（backend/data/standard_account_chart.json）的实际编码取数：3001 实收资本 / 3002 资本公积 /
#: 3003 其他权益工具 / 3101 盈余公积 / 3102 其他综合收益 / 3104 本年利润 / 3201 利润分配；4xxx 在这张表里是成本类
#: （4001 生产成本 / 4101 制造费用 / 4301 研发支出），原公式按 4001 / 4002 / 4101 / 4104 / 4301 取数 ⇒ 实收资本取到生产成本。
#: 库存股 / 专项储备 / 一般风险准备在科目表里没有对应科目 ⇒ 置空（用户 2026-11-02 裁定：企业有此业务时须新增科目）。
_PAID_IN = "TB('3001','期末余额')"
_CAPITAL_RESERVE = "TB('3002','期末余额')"
_OTHER_EQUITY_INSTRUMENTS = "TB('3003','期末余额')"
_SURPLUS_RESERVE = "TB('3101','期末余额')"
#: 未分配利润 = 本年利润 + 利润分配（未结账时本年利润挂在 3104，结账后转入 3201，两者相加不重复）
_RETAINED_EARNINGS = "TB('3104','期末余额')+TB('3201','期末余额')"
#: 单体报表另加未结转损益（spec citar-audited-balance-and-workpaper-coverage R1）：SAP 等年末不结转的账套损益留在
#: 损益科目、3104 没有数；已批准的损益类审计调整也只改损益科目 ⇒ 不加这一项资产负债表差的正是本年利润 / 调整对利润的影响。
#: 合并报表走合并试算表 resolver，没有这个口径，仍用上面的公式。
_RETAINED_EARNINGS_STANDALONE = _RETAINED_EARNINGS + "+PL_UNCLOSED()"
_NO_ACCOUNT = "平台标准科目表没有对应科目（企业有此业务时须新增科目）"

#: {准则家族: {公式位: (行名前缀, 公式, 说明)}}；家族：soe = 国企单体 / 合并，listed = 上市单体 / 合并
FIXES: dict[str, dict[str, tuple[str, str | None, str]]] = {
    "soe": {
        # ── 资产负债表 ──
        "balance_sheet:BS-015": ("其他应收款", _OTHER_RECEIVABLES, "其他应收款 + 应收股利 + 应收利息（现行报表格式并入）"),
        "balance_sheet:BS-018": ("存货", INVENTORY_FORMULA, "各存货科目 − 商品进销差价 − 存货跌价准备"),
        "balance_sheet:BS-027": ("流动资产合计", _rows(*_bs("002 003 004 005 006 007 008 009 010 011 012 013 014 015 017 018 021 022 023 024 025 026")),
                                 "流动资产各项目之和（不含「其中」子项）"),
        "balance_sheet:BS-052": ("非流动资产合计", _rows(*_bs("029 030 031 032 033 034 035 036 037 041 042 043 044 045 046 047 048 049 050")),
                                 "非流动资产各项目之和（不含「其中」子项）"),
        "balance_sheet:BS-053": ("资产总计", _rows("BS-027", "BS-052"), "流动资产合计 + 非流动资产合计"),
        "balance_sheet:BS-075": ("其他应付款", _OTHER_PAYABLES, "其他应付款 + 应付股利 + 应付利息（现行报表格式并入）"),
        "balance_sheet:BS-082": ("流动负债合计", _rows(*_bs("055 056 057 058 059 060 061 062 063 064 065 066 067 068 069 073 075 077 078 079 080 081")),
                                 "流动负债各项目之和（不含「其中」子项）"),
        "balance_sheet:BS-097": ("其他非流动负债", _EMPTY, "原取 2901 递延所得税负债，与上一行重复；没有对应的标准科目"),
        "balance_sheet:BS-099": ("非流动负债合计", _rows(*_bs("084 085 086 089 090 091 092 093 094 095 096 097")),
                                 "非流动负债各项目之和（不含「其中」子项）"),
        "balance_sheet:BS-100": ("负债合计", _rows("BS-082", "BS-099"), "流动负债合计 + 非流动负债合计"),
        "balance_sheet:BS-102": ("实收资本", _PAID_IN, "3001 实收资本"),
        "balance_sheet:BS-110": ("其他权益工具", _OTHER_EQUITY_INSTRUMENTS, "3003 其他权益工具"),
        "balance_sheet:BS-113": ("资本公积", _CAPITAL_RESERVE, "3002 资本公积"),
        "balance_sheet:BS-114": ("减：库存股", _EMPTY, _NO_ACCOUNT),
        "balance_sheet:BS-117": ("专项储备", _EMPTY, _NO_ACCOUNT),
        "balance_sheet:BS-118": ("盈余公积", _SURPLUS_RESERVE, "3101 盈余公积"),
        "balance_sheet:BS-124": ("△一般风险准备", _EMPTY, _NO_ACCOUNT),
        "balance_sheet:BS-125": ("未分配利润", _RETAINED_EARNINGS, "3104 本年利润 + 3201 利润分配"),
        "balance_sheet:BS-126": ("归属于母公司所有者权益合计",
                                 _rows(*_bs("102 110 113 115 117 118 124 125"), minus=("BS-114",)),
                                 "实收资本 + 其他权益工具 + 资本公积 − 库存股 + 其他综合收益 + 专项储备 + 盈余公积 + 一般风险准备 + 未分配利润"),
        # ── 利润表 ──
        "income_statement:IS-001": ("一、营业总收入", _rows(*_is("002 003 004 005 006")), "营业收入 + 金融 / 保险类收入"),
        "income_statement:IS-003": ("△利息收入", _EMPTY, "金融企业利息收入，原取 6603 财务费用"),
        "income_statement:IS-007": ("二、营业总成本",
                                    _rows(*_is("008 009 010 011 012 014 016 017 018 019 020 021 022 023 024 025"), minus=("IS-013", "IS-015")),
                                    "营业成本 + 各项费用（摊回 / 分出再保险收益为减项）"),
        "income_statement:IS-026": ("其中：利息费用", _EMPTY, "财务费用的子项，原取整个 6603"),
        "income_statement:IS-027": ("利息收入", _EMPTY, "财务费用的子项，原取整个 6603"),
        "income_statement:IS-031": ("投资收益", "TB('6111','本期发生额')", "投资收益"),
        "income_statement:IS-033": ("以摊余成本计量的金融资产终止确认收益", _EMPTY, "投资收益的子项，原取 6111 与投资收益重复"),
        "income_statement:IS-040": ("三、营业利润", _rows(*_is("001 030 031 034 035 036 037 038 039"), minus=("IS-007",)),
                                    "营业总收入 − 营业总成本 + 其他收益、投资收益等（损失以负数列示）"),
        "income_statement:IS-044": ("四、利润总额", _rows("IS-040", "IS-041", minus=("IS-043",)), "营业利润 + 营业外收入 − 营业外支出"),
        "income_statement:IS-046": ("五、净利润", _rows("IS-044", minus=("IS-045",)), "利润总额 − 所得税费用"),
        "income_statement:IS-073": ("七、综合收益总额", _rows("IS-046", "IS-053"), "净利润 + 其他综合收益的税后净额"),
        "income_statement:IS-077": ("基本每股收益", _EMPTY, "不是试算表数，原取 6901 以前年度损益调整"),
        "income_statement:IS-078": ("稀释每股收益", _EMPTY, "不是试算表数，原取不存在的 6902"),
    },
    "listed": {
        # ── 资产负债表 ──
        "balance_sheet:BS-009": ("其他应收款", _OTHER_RECEIVABLES, "其他应收款 + 应收利息 + 应收股利（现行报表格式并入）"),
        "balance_sheet:BS-012": ("存货", INVENTORY_FORMULA, "各存货科目 − 商品进销差价 − 存货跌价准备"),
        "balance_sheet:BS-018": ("流动资产合计", _rows(*_bs("002 003 004 005 006 007 008 009 012 014 015 016 017")),
                                 "流动资产各项目之和（不含「其中」子项）"),
        "balance_sheet:BS-041": ("非流动资产合计", _rows(*_bs("020 021 022 023 024 025 026 027 028 029 030 031 032 033 035 037 038 039 040")),
                                 "非流动资产各项目之和（不含「其中」子项）"),
        "balance_sheet:BS-042": ("资产总计", _rows("BS-018", "BS-041"), "流动资产合计 + 非流动资产合计"),
        "balance_sheet:BS-053": ("其他应付款", _OTHER_PAYABLES, "其他应付款 + 应付利息 + 应付股利（现行报表格式并入）"),
        "balance_sheet:BS-059": ("流动负债合计", _rows(*_bs("044 045 046 047 048 049 050 051 052 053 056 057 058")),
                                 "流动负债各项目之和（不含「其中」子项）"),
        "balance_sheet:BS-071": ("其他非流动负债", _EMPTY, "原取 2901 递延所得税负债，与上一行重复；没有对应的标准科目"),
        "balance_sheet:BS-072": ("非流动负债合计", _rows(*_bs("061 062 065 066 067 068 069 070 071")),
                                 "非流动负债各项目之和（不含「其中」子项）"),
        "balance_sheet:BS-073": ("负债合计", _rows("BS-059", "BS-072"), "流动负债合计 + 非流动负债合计"),
        "balance_sheet:BS-075": ("股本", _PAID_IN, "3001 实收资本"),
        "balance_sheet:BS-076": ("其他权益工具", _OTHER_EQUITY_INSTRUMENTS, "3003 其他权益工具"),
        "balance_sheet:BS-079": ("资本公积", _CAPITAL_RESERVE, "3002 资本公积"),
        "balance_sheet:BS-080": ("减：库存股", _EMPTY, _NO_ACCOUNT),
        "balance_sheet:BS-082": ("专项储备", _EMPTY, _NO_ACCOUNT),
        "balance_sheet:BS-083": ("盈余公积", _SURPLUS_RESERVE, "3101 盈余公积"),
        "balance_sheet:BS-084": ("未分配利润", _RETAINED_EARNINGS, "3104 本年利润 + 3201 利润分配"),
        "balance_sheet:BS-085": ("归属于母公司股东权益合计", _rows(*_bs("075 076 079 081 082 083 084"), minus=("BS-080",)),
                                 "股本 + 其他权益工具 + 资本公积 − 库存股 + 其他综合收益 + 专项储备 + 盈余公积 + 未分配利润"),
        "balance_sheet:BS-087": ("股东（或所有者）权益合计", _rows("BS-085", "BS-086"), "归属于母公司股东权益合计 + 少数股东权益"),
        "balance_sheet:BS-088": ("负债和股东（或所有者）权益总计", _rows("BS-073", "BS-087"), "负债合计 + 股东权益合计"),
        # ── 利润表 ──
        "income_statement:IS-008": ("其中：利息费用", _EMPTY, "财务费用的子项，原取整个 6603"),
        "income_statement:IS-009": ("利息收入", _EMPTY, "财务费用的子项，原取整个 6603"),
        "income_statement:IS-011": ("投资收益", "TB('6111','本期发生额')", "投资收益"),
        "income_statement:IS-013": ("以摊余成本计量的金融资产终止确认收益", _EMPTY, "投资收益的子项，原取 6111 与投资收益重复"),
        "income_statement:IS-019": ("二、营业利润",
                                    _rows(*_is("001 010 011 014 015 016 017 018"), minus=("IS-002", "IS-003", "IS-004", "IS-005", "IS-006", "IS-007")),
                                    "营业收入 − 营业成本 − 税金及附加 − 期间费用 + 其他收益、投资收益等（损失以负数列示）"),
        "income_statement:IS-022": ("三、利润总额", _rows("IS-019", "IS-020", minus=("IS-021",)), "营业利润 + 营业外收入 − 营业外支出"),
        "income_statement:IS-024": ("四、净利润", _rows("IS-022", minus=("IS-023",)), "利润总额 − 所得税费用"),
        "income_statement:IS-050": ("六、综合收益总额", _rows("IS-024", "IS-031"), "净利润 + 其他综合收益的税后净额"),
    },
}

STANDARD_FAMILY = {
    "soe_standalone": "soe",
    "soe_consolidated": "soe",
    "listed_standalone": "listed",
    "listed_consolidated": "listed",
}

#: 只用于单体准则的公式位（覆盖 FIXES 里同家族的同一位）
STANDALONE_OVERRIDES: dict[str, dict[str, tuple[str, str | None, str]]] = {
    "soe": {"balance_sheet:BS-125": ("未分配利润", _RETAINED_EARNINGS_STANDALONE, "3104 本年利润 + 3201 利润分配 + 未结转损益")},
    "listed": {"balance_sheet:BS-084": ("未分配利润", _RETAINED_EARNINGS_STANDALONE, "3104 本年利润 + 3201 利润分配 + 未结转损益")},
}


def fixes_for(standard: str) -> dict[str, tuple[str, str | None, str]]:
    """某个准则的全部公式位（家族公式 + 单体覆盖）；未知准则为空。"""
    family = STANDARD_FAMILY.get(standard)
    if family is None:
        return {}
    out = dict(FIXES[family])
    if standard.endswith("_standalone"):
        out.update(STANDALONE_OVERRIDES.get(family, {}))
    return out


def fix_for(standard: str, report_type: str, row_code: str, row_name: str) -> tuple[bool, str | None]:
    """新库填公式用：(是否命中, 公式)。行名前缀不符视为未命中（行号体系不同的模板不套用）。"""
    entry = fixes_for(standard).get(f"{report_type}:{row_code}")
    if entry is None:
        return False, None
    prefix, formula, _desc = entry
    if not (row_name or "").strip().startswith(prefix):
        return False, None
    return True, formula
