"""E 循环（货币资金）语义科目定位规格 —— **跨 E0/E1 单一真源**。

**为什么按科目名而不按标准码声明**

与 G 循环同理（详见 `semantic_account_resolver` 与 `g_cycle_specs` 模块 docstring）：
标准码在项目间并不一致，且客户科目表才是真实在用的那一套。E 循环的具体表现：

- ``report_config`` 的 ``BS-002 货币资金 = TB('1001') + TB('1002') + TB('1012')``
  四准则一致且**编码正确**（区别于 G 循环的 4 处错码）—— 但它只覆盖三个一级科目，
  拿不到「数字货币」「存放财务公司款项」这两个按准则解释 15 号**按需增设**的项目。
- ``account_chart`` 实证 ``^10(0|1)[0-9]$`` 范围内只有 ``1001``/``1002``/``1012``
  三个标准科目 —— 即平台标准表里**没有**数字货币科目，写死任何码都是错的
  （E1 公式预设原先写 ``1502``，而 ``1502`` 实为「持有至到期投资减值准备」）。

→ 故一律按名称在该项目自己的科目表里定位；本项目没有该科目时槽 ``found=False``，
调用方据此显示「本项目无此科目」而**不是取 0**（宁缺勿造）。

**数字货币与存放财务公司款项：故意不给兜底码**

准则解释 15 号（财会〔2021〕35 号）规定：

- 成员单位存入财务公司的资金，可在「货币资金」项目下增设
  「其中：存放财务公司款项」**单独列示**
- 持有中国人民银行发行的数字人民币，可增设「数字货币」**二级科目**核算

两者都是「可增设」——没有独立的一级标准科目。所以这两个槽
``fallback_standard_codes=()``：项目科目表里有同名科目才取数，没有就返空。
这比写死一个码「静默产出 0」诚实得多，也不会像 ``1502`` 那样取到别的科目族。

**受限资金不在本模块**

「受限制的货币资金」不是一级科目，而是货币资金三族里**叶子科目名**层面的分类
（客户命名千差万别）→ 见 `e1_restricted_buckets.classify_e1_restricted_leaf`。

spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/
      Requirements 2.1~2.4, 11.1 / Property 4
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

#: 货币资金报表行（**提示 + 冲突检测**用，不是定位依据）
E1_REPORT_ROW_CODE = "BS-002"

#: 一切货币资金槽的通用否决词 —— 备抵/累计类科目名不应进任何货币资金槽。
#: 货币资金本身不计提减值，但客户科目表里可能有历史遗留的准备类科目。
_PROVISION_WORDS = ("减值准备", "坏账准备", "跌价准备", "累计")

#: 三个基础槽的 key（与前端 `four_table_prefill` 的分组键、披露主表行一一对应）
E1_SLOT_CASH = "cash"
E1_SLOT_BANK = "bank"
E1_SLOT_OTHER = "other"
#: 按需增设槽（无兜底码，项目没有就返空）
E1_SLOT_FINANCE_CO = "finance_co"
E1_SLOT_DIGITAL = "digital"

#: 参与「货币资金合计」的槽 —— 🔴 只有三个基础槽。
#: `finance_co` 是 `bank` 的**其中项**（准则解释 15 号「货币资金项目之下增设」），
#: `digital` 若被客户设成一级科目则已含在其自身槽里、但不属 1001/1002/1012 三族，
#: 由调用方按 `found` 决定是否单列 —— 二者**都不得**直接加进合计，否则重复计算。
E1_TOTAL_SLOT_KEYS: tuple[str, ...] = (E1_SLOT_CASH, E1_SLOT_BANK, E1_SLOT_OTHER)

E1_MONETARY_FUND_SPEC = SemanticAccountSpec(
    row_code=E1_REPORT_ROW_CODE,
    slots=(
        SemanticAccountSlot(
            key=E1_SLOT_CASH,
            names=("库存现金", "现金"),
            # 「其他货币资金」「银行存款」不含「现金」二字，此处否决词主要防
            # 客户自设的「现金及现金等价物」「现金等价物」类汇总科目被吸进来。
            exclude_names=_PROVISION_WORDS + ("等价物", "银行", "其他货币"),
            fallback_standard_codes=("1001",),
            label="库存现金",
        ),
        SemanticAccountSlot(
            key=E1_SLOT_BANK,
            names=("银行存款",),
            # 🔴 「存放财务公司款项」是独立槽，不能被 bank 的包含匹配吸走；
            # 「存放中央银行款项」(1003) 属金融企业科目，不是货币资金 BS-002 口径。
            exclude_names=_PROVISION_WORDS + ("其他货币", "中央银行", "财务公司"),
            fallback_standard_codes=("1002",),
            label="银行存款",
        ),
        SemanticAccountSlot(
            key=E1_SLOT_OTHER,
            names=("其他货币资金",),
            exclude_names=_PROVISION_WORDS,
            fallback_standard_codes=("1012",),
            label="其他货币资金",
        ),
        # ── 以下两槽按准则解释 15 号「可增设」，故意无兜底码 ──
        SemanticAccountSlot(
            key=E1_SLOT_FINANCE_CO,
            names=("存放财务公司款项", "财务公司存款", "存放财务公司资金"),
            exclude_names=_PROVISION_WORDS,
            fallback_standard_codes=(),
            label="存放财务公司款项",
        ),
        SemanticAccountSlot(
            key=E1_SLOT_DIGITAL,
            names=("数字货币", "数字人民币"),
            exclude_names=_PROVISION_WORDS,
            fallback_standard_codes=(),
            label="数字货币",
        ),
    ),
)

__all__ = [
    "E1_MONETARY_FUND_SPEC",
    "E1_REPORT_ROW_CODE",
    "E1_SLOT_BANK",
    "E1_SLOT_CASH",
    "E1_SLOT_DIGITAL",
    "E1_SLOT_FINANCE_CO",
    "E1_SLOT_OTHER",
    "E1_TOTAL_SLOT_KEYS",
]
