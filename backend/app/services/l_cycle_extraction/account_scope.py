"""L 类（债务循环）科目定位与叶子分类 —— 单一真源。

**为什么必须有这个模块**

改造前 L1~L8 的 render 各自硬编码一个科目码字面量（`_l1→'2001'` … `_l8→'6603'`），
其中两处**取错整个科目族**，一处**结构性恒为 0**，DB 只读实证如下：

======  ================  ==========================  ====================================
循环    render 硬编码     report_config 报表行         account_chart / tb_balance 实证
======  ================  ==========================  ====================================
L1      ``2001``          BS-044/BS-055 TB('2001')    2001 短期借款 ✔
L2      ``2231``          BS-054 仅 listed 且 None    2231 应付利息 ✔（兜底正确）
L3      ``2501``          BS-061/BS-085 TB('2501')    2501 长期借款 ✔
L4      ``2502``          BS-062/BS-086 TB('2502')    2502 应付债券 ✔
L5      ``2701``          BS-066/BS-092 TB('2701')    2701 长期应付款 ✔
L6      ``2601`` 🔴       无该报表行                   **2601 = 租赁负债**（H 循环）；
                                                     专项应付款真值 = **2711**；
                                                     ``tb_balance`` 中 ``2601%`` **0 行**
L7      ``2801`` 🔴       BS-071/BS-097 TB('2901')    **2801 = 预计负债**；
                                                     **2901 = 递延所得税负债**（且已被
                                                     BS-070/BS-096 占用 → 报表行撞码）；
                                                     客户科目表**无**「其他非流动负债」科目
L8      ``6603`` ✔        IS-007/IS-025 本期发生额     6603 财务费用 ✔ 但取数口径错（见下）
======  ================  ==========================  ====================================

**根因**：`prefill_formula_mapping.json` 的 L 类公式预设**整块错位一位**
（L4 块写「租赁负债审定表」+``2601``、L7 块写「预计负债审定表」+``2801``），
render 的科目码正是照抄该错位预设而来 → 两处必须一起修，否则会互相抄回。

**L8 恒为 0**：原 `fetch_tb_for_income` 用 ``debit - credit``，而含年末结转损益的全年账
上 ``6603`` 及**每一个**子科目都满足 ``debit == credit``（实证 543,020,073.49 双侧相等）
→ 差额恒 0。平台权威口径 = ``trial_balance`` 本期发生额，兜底 ``tb_balance.debit_amount``。

**L7 宁缺勿造**：其他非流动负债在 CAS 无专属科目，report_config 该行公式引用的 ``2901``
语义是递延所得税负债 → 不设兜底码、不预填，并在 ``tb_source_codes`` 记录依据。
report_config 该缺陷属平台级 data-hygiene 待办，本模块只报告不擅改（同 G14 范式）。

**客户子科目天然对应披露分项**（同 G7 ``1511.03``→变动列 / F1 ``1123``→五性质桶）：
``2231.01~.04`` → 附注应付利息分项；``2501.01/.02`` → 长期借款 + 一年内到期；
``2502.01~.03`` → 应付债券（续）变动列；``2701.01~.03/.99`` → 按款项性质 + 一年内到期；
``6603.01~.99`` → 财务费用按费用性质 12 行。故分类一律**按名称**，禁按编码写死。

spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/
      Requirements 1.1~1.3, 2.1~2.5, 3.2~3.4 / Property 1, 2, 6
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from app.services.four_table.report_line_accounts import (
    RESOLVED_FROM_FALLBACK,
    RESOLVED_FROM_REPORT,
    ReportLineAccountSpec,
    ReportLineAccounts,
    normalize_standard_prefix,
    resolve_report_line_accounts,
)

logger = logging.getLogger(__name__)

#: 「一年内到期」重分类识别词。
#:
#: 🔴 判定必须**前置于**任何业务桶：``2701.99 长期应付款_一年内到期的长期应付款`` 同时含
#: 「长期应付款」，若先过业务桶会被吞掉，导致「减一年内到期」列恒 0。
CURRENT_PORTION_KEYWORDS: tuple[str, ...] = ("一年内到期", "1年内到期")

#: 桶键：一年内到期部分
BUCKET_CURRENT_PORTION = "current_portion"
#: 桶键：未命中任何业务桶（金额不丢弃）
BUCKET_OTHER = "other"


@dataclass(frozen=True)
class LBucket:
    """叶子科目分类桶（声明式，纯数据）。

    Attributes:
        key: 桶键（snake_case，前端消费）。
        label: 中文标签（UI 展示，单一真源在此，前端不抄第二份）。
        keywords: 命中词，按 ``account_name`` 子串匹配。
        exclude_keywords: 否决词 —— 命中任一则**不**归入本桶。
            🔴 必要性实证：``6603.02 利息收入`` 与 ``6603.01 利息支出`` 都含「利息」，
            ``现金折扣收取`` 与 ``现金折扣支出`` 都含「现金折扣」。
        source_ref: 实证依据（``tb_balance`` 科目码或源 xlsx 单元格），供反查。
    """

    key: str
    label: str
    keywords: tuple[str, ...]
    exclude_keywords: tuple[str, ...] = ()
    source_ref: str = ""


@dataclass(frozen=True)
class LCycleSpec:
    """某 L 循环的科目定位规格。

    Attributes:
        wp_code: 循环编码（``L1``…``L8``）。
        account_label: 科目中文名（溯源展示）。
        row_code_listed: 上市准则下的报表行编码；``None`` = 该准则无此行。
        row_code_soe: 国企准则下的报表行编码。
        fallback_codes: 报表行解析落空时的兜底**标准码**。
            空元组 = 宁缺勿造（L7），此时不预填。
        kind: ``balance`` 取期初/期末余额；``income`` 取本期发生额。
        buckets: 叶子分类桶（按顺序即优先级）。空 = 该科目无子科目（单行口径）。
        split_current_portion: 是否需拆分「一年内到期」部分。
        source_ref: 本规格的实证依据。
    """

    wp_code: str
    account_label: str
    row_code_listed: str | None
    row_code_soe: str | None
    fallback_codes: tuple[str, ...]
    kind: Literal["balance", "income"] = "balance"
    buckets: tuple[LBucket, ...] = ()
    split_current_portion: bool = False
    source_ref: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# L1~L8 单一真源
# ─────────────────────────────────────────────────────────────────────────────

_L2_BUCKETS: tuple[LBucket, ...] = (
    LBucket(
        key="long_term_loan_interest",
        label="分期付息到期还本的长期借款利息",
        keywords=("分期付息",),
        source_ref="tb_balance 2231.01",
    ),
    LBucket(
        key="bond_interest",
        label="企业债券利息",
        keywords=("企业债券利息", "债券利息"),
        source_ref="tb_balance 2231.02",
    ),
    LBucket(
        key="short_term_loan_interest",
        label="短期借款应付利息",
        keywords=("短期借款",),
        source_ref="tb_balance 2231.03",
    ),
    LBucket(
        key="ar_derecognition_interest",
        label="应收账款出表利息",
        keywords=("应收账款出表", "出表利息"),
        source_ref="tb_balance 2231.04",
    ),
)

_L3_BUCKETS: tuple[LBucket, ...] = (
    LBucket(
        key="non_current",
        label="长期借款",
        keywords=("长期借款",),
        exclude_keywords=CURRENT_PORTION_KEYWORDS,
        source_ref="tb_balance 2501.01",
    ),
)

_L4_BUCKETS: tuple[LBucket, ...] = (
    LBucket(
        key="face_value",
        label="面值",
        keywords=("面值",),
        source_ref="tb_balance 2502.01",
    ),
    LBucket(
        key="interest_adjustment",
        label="利息调整",
        keywords=("利息调整",),
        source_ref="tb_balance 2502.02",
    ),
    LBucket(
        key="accrued_interest",
        label="应计利息",
        keywords=("应计利息",),
        source_ref="tb_balance 2502.03",
    ),
)

_L5_BUCKETS: tuple[LBucket, ...] = (
    LBucket(
        key="finance_lease",
        label="应付融资租赁款",
        keywords=("融资租赁",),
        exclude_keywords=CURRENT_PORTION_KEYWORDS,
        source_ref="tb_balance 2701.01",
    ),
    LBucket(
        key="long_term_deposit",
        label="应付长期保证金",
        keywords=("保证金", "押金"),
        exclude_keywords=CURRENT_PORTION_KEYWORDS,
        source_ref="tb_balance 2701.02",
    ),
    LBucket(
        key="long_term_loan",
        label="应付长期借款",
        keywords=("长期借款",),
        exclude_keywords=CURRENT_PORTION_KEYWORDS,
        source_ref="tb_balance 2701.03",
    ),
)

#: L8 财务费用按费用性质分桶。
#:
#: 🔴 顺序即优先级，且**否决词是必需的**：`利息支出` / `利息收入` 都含「利息」；
#: `现金折扣支出` / `现金折扣收取` 都含「现金折扣」。打乱顺序或去掉否决词会让
#: 收入类金额被并进支出类（守卫含反向自检）。
_L8_BUCKETS: tuple[LBucket, ...] = (
    LBucket(
        key="interest_expense",
        label="利息支出",
        keywords=("利息支出",),
        source_ref="tb_balance 6603.01",
    ),
    LBucket(
        key="interest_income",
        label="减：利息收入",
        keywords=("利息收入",),
        source_ref="tb_balance 6603.02",
    ),
    LBucket(
        key="handling_fee",
        label="手续费支出",
        keywords=("手续费",),
        # 🔴 否决词必需：`6603.07.01 金融工具转移_保理利息及手续费` /
        #    `.02 ABS支出及手续费` / `.03 ABN支出及手续费` 都含「手续费」，
        #    无否决词会被本桶提前吞掉（守卫 test_classify_l_leaf_real_account_names 已钉死）。
        exclude_keywords=("金融工具转移", "保理", "ABS", "ABN"),
        source_ref="tb_balance 6603.03",
    ),
    LBucket(
        key="exchange_gain_loss",
        label="汇兑损益",
        keywords=("汇兑",),
        source_ref="tb_balance 6603.04",
    ),
    LBucket(
        key="cash_discount_received",
        label="减：现金折扣收取",
        keywords=("现金折扣收取",),
        source_ref="tb_balance 6603.15",
    ),
    LBucket(
        key="cash_discount_expense",
        label="现金折扣支出",
        keywords=("现金折扣",),
        exclude_keywords=("收取",),
        source_ref="tb_balance 6603.05",
    ),
    LBucket(
        key="guarantee_fee",
        label="担保费",
        keywords=("担保费",),
        source_ref="tb_balance 6603.06",
    ),
    LBucket(
        key="financial_instrument_transfer",
        label="金融工具转移",
        keywords=("金融工具转移", "保理", "ABS", "ABN"),
        source_ref="tb_balance 6603.07",
    ),
)

# 🔴 2026-08-05 修正：本文件的 `row_code` 与 `four_table/l_cycle_specs.py`（2026-08-03 已按
# `report_config` 对账改正）**长期分叉** —— 本文件才是 render 消费的那一份，却一直没跟上。
# 逐行 DB 实证（`report_config`，四准则 listed_standalone / listed_consolidated /
# soe_standalone / soe_consolidated 全查，`is_deleted=false`）::
#     BS-041 短期借款      TB('2001','期末余额')   四准则一致   ← L1 正解
#     BS-044 应付票据      TB('2201','期末余额')   四准则一致   ← L1 原值，取的是 F3 的科目
#     BS-055 短期借款      formula NULL（仅 soe）               ← L1 soe，名对但无公式→走兜底
#     BS-061 长期借款      TB('2501','期末余额')   四准则一致   ← L3 正解
#     BS-062 应付债券      TB('2502','期末余额')   四准则一致   ← L4 正解
#     BS-064 长期应付款    TB('2701','期末余额')   四准则一致   ← L5 正解
#     BS-066 递延收益      TB('2811','期末余额')   四准则一致   ← L5 原值（K7 的行）
#     BS-085 其他综合收益  TB('4003','期末余额')   四准则一致   ← L3 原值（M9 的行）
#     BS-086 专项储备      TB('4301','期末余额')   四准则一致   ← L4 原值（M7 的行）
# `account_chart` 双向对账：2001 短期借款（standard 9 / client 6）· 2501 长期借款（8/5）·
# 2502 应付债券（8/5）· 2701 长期应付款（8/5）· 2201 应付票据（10/7）·
# 4003 其他综合收益（5/8）· 4301 专项储备（8/4）；**2811 全库两张科目表零命中**。
L_CYCLE_SPECS: dict[str, LCycleSpec] = {
    "L1": LCycleSpec(
        wp_code="L1",
        account_label="短期借款",
        # 🔴 原写 `BS-044` = **应付票据** `TB('2201')`（四准则一致）→ listed 项目的短期借款
        #    审定表取到应付票据余额（`resolve_report_line_accounts` 解析成功即 break，
        #    兜底 2001 永远用不上）。正解 `BS-041 短期借款 = TB('2001','期末余额')`。
        row_code_listed="BS-041",
        row_code_soe="BS-055",
        fallback_codes=("2001",),
        source_ref="report_config BS-041 = TB('2001','期末余额')（四准则一致）；"
        "BS-055（仅 soe）row_name 亦为短期借款但 formula NULL → 该分支回退兜底；"
        "tb_balance 2001 无子科目",
    ),
    "L2": LCycleSpec(
        wp_code="L2",
        account_label="应付利息",
        # BS-054「其中：应付利息」**只有 listed 两条且 formula 均为 None** → 必然回退兜底
        row_code_listed="BS-054",
        row_code_soe=None,
        fallback_codes=("2231",),
        buckets=_L2_BUCKETS,
        source_ref="report_config BS-054 仅 listed 且 formula=None；account_chart 2231 应付利息",
    ),
    "L3": LCycleSpec(
        wp_code="L3",
        account_label="长期借款",
        row_code_listed="BS-061",
        # 🔴 原写 `BS-085` = **其他综合收益** `TB('4003')`（M9 的行）。这是 **V138 造成的
        #    活跃回归**：V138 之前 BS-085 的公式是 `TB('4102')`（该码全库零命中）→ 虽解析
        #    成功但取不到数，错误被掩盖；V138 把它改对成 `TB('4003')`（4003 确实存在）后，
        #    soe 项目的长期借款审定表开始取到**其他综合收益**的余额。
        #    正解 = 与 listed 同一行 `BS-061 长期借款 = TB('2501','期末余额')`（四准则一致，
        #    长期借款在 soe 侧没有独立行号）。
        row_code_soe="BS-061",
        fallback_codes=("2501",),
        buckets=_L3_BUCKETS,
        split_current_portion=True,
        source_ref="report_config BS-061 = TB('2501','期末余额')（四准则一致）；"
        "tb_balance 2501.01/.02",
    ),
    "L4": LCycleSpec(
        wp_code="L4",
        account_label="应付债券",
        row_code_listed="BS-062",
        # 🔴 原写 `BS-086` = **专项储备** `TB('4301')`（M7 的行）。同 L3，属 **V138 造成的
        #    活跃回归**：V138 前 BS-086 写 `TB('4103')`（实为「本年利润」，确实存在）→ 早已
        #    取错；V138 改对成 `TB('4301')` 后改为取到**专项储备**。两种情形都不是应付债券。
        #    正解 = 与 listed 同一行 `BS-062 应付债券 = TB('2502','期末余额')`（四准则一致）。
        row_code_soe="BS-062",
        fallback_codes=("2502",),
        buckets=_L4_BUCKETS,
        split_current_portion=True,
        source_ref="report_config BS-062 = TB('2502','期末余额')（四准则一致）；"
        "tb_balance 2502.01~.03",
    ),
    "L5": LCycleSpec(
        wp_code="L5",
        account_label="长期应付款",
        # 🔴 原写 `BS-066` = **递延收益** `TB('2811')`（K7 的行）→ listed 项目的长期应付款
        #    取到递延收益的报表口径；2811 全库两张科目表零命中，故表现为「恒空」而非错数
        #    （比 L3/L4 隐蔽）。正解 `BS-064 长期应付款 = TB('2701','期末余额')`（四准则一致）。
        row_code_listed="BS-064",
        row_code_soe="BS-092",
        fallback_codes=("2701",),
        buckets=_L5_BUCKETS,
        split_current_portion=True,
        source_ref="report_config BS-064 = TB('2701','期末余额')（四准则一致）；"
        "BS-092（仅 soe）row_name 亦为长期应付款但 formula NULL → 该分支回退兜底；"
        "tb_balance 2701.01~.03/.99",
    ),
    "L6": LCycleSpec(
        wp_code="L6",
        account_label="专项应付款",
        # report_config 无「专项应付款」报表行（并入长期应付款披露）→ 只有兜底码
        row_code_listed=None,
        row_code_soe=None,
        fallback_codes=("2711",),
        source_ref=(
            "account_chart 2711 专项应付款（3 项目）；"
            "改造前硬编码 2601 实为租赁负债，tb_balance 该前缀 0 行 → 取数恒空"
        ),
    ),
    "L7": LCycleSpec(
        wp_code="L7",
        account_label="其他非流动负债",
        row_code_listed="BS-071",
        row_code_soe="BS-097",
        # 🔴 故意留空 = 宁缺勿造：BS-071/BS-097 的 TB('2901') 与 BS-070/BS-096
        #    递延所得税负债撞码；2801 是预计负债；客户科目表无「其他非流动负债」科目。
        #
        # 🔴 双真源标注（spec l-cycle-…completion R9.4）：
        #    另一份 = `four_table/l_cycle_specs.py` 的 `L7_SPEC`（row_code="BS-068"）。
        #    那份是 `semantic_account_resolver` 的定位链路消费——走 BS-068 的 TB('2911')
        #    可让语义解析在本项目科目表有 2911 时正常工作。
        #    本文件保留 BS-071/BS-097 是因为 render 下发 `tb_source_codes` 需要展示
        #    「report_config 引用了什么公式」这个审计追溯信息（哪怕该公式不被采纳）。
        #    两者不同是有意设计、不是分叉 —— 因 fallback_codes 为空，改 row_code 不影响取数。
        fallback_codes=(),
        source_ref=(
            "account_chart 实证 2901=递延所得税负债、2801=预计负债；"
            "无名称含「其他非流动负债」的科目 → 不预填，report_config 缺陷另报"
        ),
    ),
    "L8": LCycleSpec(
        wp_code="L8",
        account_label="财务费用",
        row_code_listed="IS-007",
        row_code_soe="IS-025",
        fallback_codes=("6603",),
        kind="income",
        buckets=_L8_BUCKETS,
        source_ref="report_config IS-007/IS-025 = TB('6603','本期发生额')；tb_balance 6603.01~.99",
    ),
}


@dataclass(frozen=True)
class ResolvedScope:
    """科目定位结果（render 输出 `tb_source_codes` 的数据源）。

    Attributes:
        wp_code: 循环编码。
        account_label: 科目中文名。
        report_row_code: 实际用于解析的报表行编码（``''`` = 无报表行）。
        gross_standard: 标准码集。
        gross_query: 反解后的客户原始码前缀集（用于 `tb_balance` 前缀匹配）。
        resolved_from: ``report_config`` 或 ``fallback``。
        formula: 命中的报表公式原文（溯源展示）。
        prefill_supported: 是否支持预填（L7 为 ``False``）。
        note: 无法预填 / 回退兜底的依据说明（UI 溯源面板展示）。
    """

    wp_code: str
    account_label: str
    report_row_code: str = ""
    gross_standard: list[str] = field(default_factory=list)
    gross_query: list[str] = field(default_factory=list)
    resolved_from: str = RESOLVED_FROM_FALLBACK
    formula: str | None = None
    prefill_supported: bool = True
    note: str = ""

    def as_dict(self) -> dict:
        """供 render 输出（前端 `WpFourTableSourcePanel` 消费）。"""
        return {
            "wp_code": self.wp_code,
            "account_label": self.account_label,
            "report_row_code": self.report_row_code,
            "gross_standard": list(self.gross_standard),
            "gross_query": list(self.gross_query),
            "resolved_from": self.resolved_from,
            "formula": self.formula,
            "prefill_supported": self.prefill_supported,
            "note": self.note,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（无 DB，可独立单测）
# ─────────────────────────────────────────────────────────────────────────────


def is_current_portion(account_name: str) -> bool:
    """该叶子是否属「一年内到期」重分类部分。

    仅按**名称**判定 —— 客户把一年内到期部分编在 ``2501.02`` / ``2701.99`` 等不同
    编码上（实证两者后缀完全不同），按编码写死必漏。
    """
    name = (account_name or "").strip()
    if not name:
        return False
    return any(kw in name for kw in CURRENT_PORTION_KEYWORDS)


def classify_l_leaf(wp_code: str, account_name: str) -> str:
    """叶子科目 → 桶键。名称优先 + 否决词，未命中归 :data:`BUCKET_OTHER`。

    🔴 「一年内到期」判定**前置**于业务桶（见 :data:`CURRENT_PORTION_KEYWORDS`）。

    Args:
        wp_code: 循环编码。
        account_name: ``tb_balance.account_name``（可能带父级前缀，如
            ``财务费用_利息支出_借款利息（金融机构）``，故用子串匹配）。

    Returns:
        桶键；该循环无桶定义时恒返 :data:`BUCKET_OTHER`。
    """
    spec = L_CYCLE_SPECS.get(wp_code)
    if spec is None:
        return BUCKET_OTHER
    name = (account_name or "").strip()
    if not name:
        return BUCKET_OTHER

    if spec.split_current_portion and is_current_portion(name):
        return BUCKET_CURRENT_PORTION

    for bucket in spec.buckets:
        if any(x in name for x in bucket.exclude_keywords):
            continue
        if any(kw in name for kw in bucket.keywords):
            return bucket.key
    return BUCKET_OTHER


def bucket_defs_payload(wp_code: str) -> list[dict]:
    """下发前端的桶定义（中文标签只此一份，前端不抄第二份）。"""
    spec = L_CYCLE_SPECS.get(wp_code)
    if spec is None:
        return []
    out = [
        {"key": b.key, "label": b.label, "source_ref": b.source_ref}
        for b in spec.buckets
    ]
    if spec.split_current_portion:
        out.append(
            {
                "key": BUCKET_CURRENT_PORTION,
                "label": "减：一年内到期的部分",
                "source_ref": "源模板「减一年内到期」列",
            }
        )
    return out


def pick_row_codes(wp_code: str, applicable_standards) -> list[str]:
    """按适用准则挑报表行编码，返回**尝试顺序**（首选在前）。

    同一科目在两套准则下报表行编码可能不同（短期借款 listed ``BS-041`` / soe ``BS-055``），
    故不能只传一个。准则未知时两个都试（顺序 soe 优先 —— 平台在册项目以国企为主）。

    🔴 长期借款 / 应付债券**两套准则共用同一行号**（``BS-061`` / ``BS-062``，
    见 :data:`L_CYCLE_SPECS` 上方的 2026-08-05 修正说明）—— soe 侧没有独立行号，
    别因为「listed 与 soe 取值相同」就以为是漏填。
    """
    spec = L_CYCLE_SPECS.get(wp_code)
    if spec is None:
        return []
    stds = [str(s or "").strip().lower() for s in (applicable_standards or [])]
    listed = spec.row_code_listed
    soe = spec.row_code_soe

    if any(s.startswith("listed") for s in stds):
        ordered = [listed, soe]
    elif any(s.startswith("soe") for s in stds):
        ordered = [soe, listed]
    else:
        ordered = [soe, listed]
    return [c for c in ordered if c]


# ─────────────────────────────────────────────────────────────────────────────
# DB 访问（fail-open）
# ─────────────────────────────────────────────────────────────────────────────


async def resolve_l_scope(ctx, wp_code: str) -> ResolvedScope:
    """解析该循环的取数科目（报表行驱动 + 兜底，全程 fail-open）。

    Args:
        ctx: `RenderContext`（需 ``db`` / ``project_id``）。
        wp_code: ``L1``…``L8``。

    Returns:
        :class:`ResolvedScope`。``prefill_supported=False`` 时 ``gross_*`` 为空
        （L7 宁缺勿造），调用方应跳过预填。
    """
    spec = L_CYCLE_SPECS.get(wp_code)
    if spec is None:
        return ResolvedScope(
            wp_code=wp_code,
            account_label="",
            prefill_supported=False,
            note=f"未登记的循环 {wp_code}",
        )

    # 宁缺勿造：无兜底码且报表行公式不可信 → 直接不预填（不去猜科目）
    if not spec.fallback_codes and not (spec.row_code_listed or spec.row_code_soe):
        return ResolvedScope(
            wp_code=wp_code,
            account_label=spec.account_label,
            prefill_supported=False,
            note=spec.source_ref,
        )

    from app.services.four_table.report_line_accounts import fetch_applicable_standards

    try:
        standards = await fetch_applicable_standards(ctx)
    except Exception as e:  # noqa: BLE001 — 准则未知则两个报表行都试
        logger.debug("L 科目解析: 准则派生失败 %s: %s", wp_code, e)
        standards = []

    resolved: ReportLineAccounts | None = None
    used_row_code = ""
    for row_code in pick_row_codes(wp_code, standards):
        try:
            candidate = await resolve_report_line_accounts(
                ctx,
                ReportLineAccountSpec(
                    row_code=row_code,
                    fallback_gross=spec.fallback_codes,
                ),
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("L 科目解析: 报表行 %s 解析失败: %s", row_code, e)
            continue
        used_row_code = row_code
        resolved = candidate
        if candidate.resolved_from == RESOLVED_FROM_REPORT:
            break

    if resolved is None:
        # 全部报表行解析失败 → 纯兜底（L6 无报表行时走这里）
        if not spec.fallback_codes:
            return ResolvedScope(
                wp_code=wp_code,
                account_label=spec.account_label,
                prefill_supported=False,
                note=spec.source_ref,
            )
        return ResolvedScope(
            wp_code=wp_code,
            account_label=spec.account_label,
            report_row_code=used_row_code,
            gross_standard=list(spec.fallback_codes),
            gross_query=[normalize_standard_prefix(c) for c in spec.fallback_codes],
            resolved_from=RESOLVED_FROM_FALLBACK,
            note=spec.source_ref,
        )

    # 🔴 L7 专属：报表公式解析成功也不采用 —— BS-071/BS-097 引用的 2901 语义是
    #    递延所得税负债（已被 BS-070/BS-096 占用），采用即把别的科目的钱算进来。
    if not spec.fallback_codes:
        return ResolvedScope(
            wp_code=wp_code,
            account_label=spec.account_label,
            report_row_code=used_row_code,
            resolved_from=RESOLVED_FROM_FALLBACK,
            formula=resolved.formula,
            prefill_supported=False,
            note=spec.source_ref,
        )

    return ResolvedScope(
        wp_code=wp_code,
        account_label=spec.account_label,
        report_row_code=used_row_code,
        gross_standard=list(resolved.gross_standard),
        gross_query=list(resolved.gross),
        resolved_from=resolved.resolved_from,
        formula=resolved.formula,
        note="" if resolved.resolved_from == RESOLVED_FROM_REPORT else spec.source_ref,
    )


__all__ = [
    "BUCKET_CURRENT_PORTION",
    "BUCKET_OTHER",
    "CURRENT_PORTION_KEYWORDS",
    "L_CYCLE_SPECS",
    "LBucket",
    "LCycleSpec",
    "ResolvedScope",
    "bucket_defs_payload",
    "classify_l_leaf",
    "is_current_portion",
    "pick_row_codes",
    "resolve_l_scope",
]
