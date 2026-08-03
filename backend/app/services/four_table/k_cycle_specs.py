"""K 循环（K3~K13）科目定位声明 —— **单一真源**。

各 render 只从本模块取声明，不再各写一份科目码字面量。守卫测试与 render 共读本模块，
故「声明与实现漂移」在结构上不可能发生。

科目映射真源 = ``report_config``（DB 只读实证，非 ``formula_presets_seed.json``）::

    tb_balance.account_code  →  account_mapping  →  trial_balance.standard_account_code
                                                          │ report_config.formula
                                                          ▼  （按 applicable_standard）
                                                       报表行

**实证表**（`report_config` + `account_chart` + `tb_balance` 三方交叉，2026-08-01）

=====  =============  ==================  ==========================  ==========  ===============
循环   科目名          报表行 listed/soe   formula                     真值科目    历史硬编码
=====  =============  ==================  ==========================  ==========  ===============
K3     其他应付款      BS-053 / BS-075     TB('2241','期末余额')        2241        2241  （码对）
K4     其他流动负债    BS-058 / BS-081     TB('2301','期末余额')        **无**      2245  （不存在）
K5     预计负债        BS-068 / BS-094     TB('2801','期末余额')        **2801**    2701  （长期应付款）
K6     持有待售资产    BS-015 / BS-024     None                        **无**      1481  （不存在）
K6     持有待售负债    BS-056 / BS-079     None                        **无**      2605  （不存在）
K7     递延收益        BS-069 / BS-095     TB('2401','期末余额')        2401        2401  （码对）
K8     销售费用        IS-004 / IS-022     TB('6601','本期发生额')      6601        6601  （码对）
K9     管理费用        IS-005 / IS-023     TB('6602','本期发生额')      6602        6602  （码对）
K10    其他收益        IS-010 / IS-030     TB('6117','本期发生额')      6117        6117  （码对）
K11    资产减值损失    IS-017 / IS-038     **None**                    6701        6701  （码对）
K12    营业外收入      IS-020 / IS-041     TB('6301','本期发生额')      6301        6301  （码对）
K13    营业外支出      IS-021 / IS-043     TB('6711','本期发生额')      6711        6711  （码对）
=====  =============  ==================  ==========================  ==========  ===============

🔴 **K5 是「取错整个科目族」级缺陷**：``2701`` 在全部项目的 ``account_chart`` 中一律是
**长期应付款**（L5 循环科目，且带 ``2701.01 应付融资租赁款`` / ``.02 应付长期保证金`` /
``.03 应付长期借款`` / ``.99 一年内到期`` 四个子科目）。``2801`` 才是预计负债
（``account_chart`` 5 条 / ``tb_balance`` 39 行 / ``trial_balance`` 4 条均存在）。
与已修的 K2（把 ``1231 坏账准备`` 当其他流动资产）同级。

🔴 **K4 / K6 三表零命中**：``2245`` / ``2301`` / ``1481`` / ``2605`` / ``2331`` 在
``account_chart``、``tb_balance``、``trial_balance`` **三处均零命中**（按码查与按名查
「持有待售」「其他流动负债」都是空）。这不是「本项目恰好没有」——
标准科目表里就没有这两个科目，其他流动负债与持有待售在实务中是**报表行**，
由多个明细科目按性质归集。故按平台铁律**宁缺勿造**：返回空取数结果 + `empty_reason`
留证，绝不回退到不存在的码去装作有数据。

🔴 **K11 报表公式为 None**：``IS-017``（listed）/ ``IS-038``（soe）的 formula 是
``NULL``，故 ``resolved_from`` 恒为 ``fallback``。兜底码 ``6701`` 的依据是
``account_chart`` 实证：``6701 = 资产减值损失``、``6702 = 信用减值损失``
（后者属 G14 循环，**不是** K11）。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.1~1.6 / Property 2, 3, 4
"""

from __future__ import annotations

from dataclasses import dataclass

from .pl_occurrence import AccountNature
from .report_line_accounts import ReportLineAccountSpec

# ─────────────────────────────────────────────────────────────────────────────
# 无实体科目的循环（宁缺勿造）
# ─────────────────────────────────────────────────────────────────────────────

#: 三表零命中说明文案（render 输出 `tb_source_codes.empty_reason`，前端溯源面板展示）
EMPTY_REASON_NO_ACCOUNT = (
    "三表零命中：account_chart / tb_balance / trial_balance 均无该科目 —— "
    "本科目在实务中是报表行、由多个明细科目按性质归集，四表侧无法自动取数，"
    "请在审定表手工录入（平台铁律：宁缺勿造，不臆造数据）"
)

#: K4/K6 历史硬编码过、但**在标准科目表中不存在**的码。守卫据此断言源码不得再出现。
NONEXISTENT_ACCOUNT_CODES: tuple[str, ...] = ("2245", "2301", "1481", "2605", "2331")

#: K5 历史误用的码 → 它真正的科目名（守卫的反向自检用）
MISUSED_ACCOUNT_CODES: dict[str, str] = {"2701": "长期应付款"}


@dataclass(frozen=True)
class KCycleSpec:
    """单个 K 循环的科目定位声明。

    Attributes:
        wp_code: 循环编码（``K3`` ~ ``K13``）。
        account_name: 科目中文名（展示与守卫比对用）。
        row_code_listed: 上市准则下的报表行编码。
        row_code_soe: 国企准则下的报表行编码。
        fallback_standard: 兜底**标准码**（报表映射解析失败时用）；无实体科目时为空。
        nature: 损益类科目的增加方向；资产负债类为 ``None``（走余额口径）。
        has_account: ``False`` 表示三表零命中，走宁缺勿造分支。
        note: 该循环的实证结论（写进 `tb_source_codes` 供溯源，也是守卫的判据来源）。
    """

    wp_code: str
    account_name: str
    row_code_listed: str
    row_code_soe: str
    fallback_standard: str = ""
    nature: AccountNature | None = None
    has_account: bool = True
    note: str = ""

    @property
    def is_pl(self) -> bool:
        """是否损益类（取发生额而非余额）。"""
        return self.nature is not None

    def spec_for(self, applicable_standards) -> ReportLineAccountSpec:
        """按适用准则选报表行，产出共享件所需的 :class:`ReportLineAccountSpec`。

        `resolve_report_line_accounts` 内部会再按 ``applicable_standards`` 挑公式，
        但 **row_code 本身在两套准则下就不同**（如 K5 是 ``BS-068`` vs ``BS-094``），
        必须在这一层先选对行号，否则解析必然落空。

        无法判定准则时用国企行号 —— 在册项目绝大多数是 soe（memory 实测 8/8），
        且解析失败会 fail-open 回退 ``fallback_standard``，不会取到错科目。
        """
        stds = [str(s or "") for s in (applicable_standards or [])]
        is_listed = any("listed" in s for s in stds)
        row_code = self.row_code_listed if is_listed else self.row_code_soe
        return ReportLineAccountSpec(
            row_code=row_code,
            fallback_gross=(self.fallback_standard,) if self.fallback_standard else (),
            fallback_provision=(),
            provision_name_filter=None,
            extra_standard_codes=(),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 声明表（唯一真源）
# ─────────────────────────────────────────────────────────────────────────────

K_CYCLE_SPECS: dict[str, KCycleSpec] = {
    "K3": KCycleSpec(
        wp_code="K3",
        account_name="其他应付款",
        row_code_listed="BS-053",
        row_code_soe="BS-075",
        fallback_standard="2241",
        note="report_config 四准则一致 TB('2241','期末余额')；科目码原本正确，"
        "本次修的是父子双计与缺点号边界的叶子判定",
    ),
    "K4": KCycleSpec(
        wp_code="K4",
        account_name="其他流动负债",
        row_code_listed="BS-058",
        row_code_soe="BS-081",
        fallback_standard="",
        has_account=False,
        note="report_config 写 TB('2301')，但 2301 与历史硬编码的 2245 在三表均零命中 "
        "→ 宁缺勿造",
    ),
    "K5": KCycleSpec(
        wp_code="K5",
        account_name="预计负债",
        row_code_listed="BS-068",
        row_code_soe="BS-094",
        fallback_standard="2801",
        note="🔴 历史硬编码 2701 = 长期应付款（L5 科目，含 4 个子科目）；"
        "真值 2801 预计负债（account_chart / tb_balance / trial_balance 三处均有）",
    ),
    "K6": KCycleSpec(
        wp_code="K6",
        account_name="持有待售资产和负债",
        row_code_listed="BS-015",
        row_code_soe="BS-024",
        fallback_standard="",
        has_account=False,
        note="四条报表行（BS-015/BS-024 资产 + BS-056/BS-079 负债）formula 全为 None，"
        "历史硬编码 1481/2605/2331 在三表零命中 → 宁缺勿造",
    ),
    "K7": KCycleSpec(
        wp_code="K7",
        account_name="递延收益",
        row_code_listed="BS-069",
        row_code_soe="BS-095",
        fallback_standard="2401",
        note="report_config 四准则一致 TB('2401','期末余额')；科目码原本正确",
    ),
    "K8": KCycleSpec(
        wp_code="K8",
        account_name="销售费用",
        row_code_listed="IS-004",
        row_code_soe="IS-022",
        fallback_standard="6601",
        nature=AccountNature.EXPENSE,
        note="损益类借方；原实现 debit - credit 恒 0（活体 6601 逐行 debit==credit），"
        "改 trial_balance 权威（实证 505,080,400.27）",
    ),
    "K9": KCycleSpec(
        wp_code="K9",
        account_name="管理费用",
        row_code_listed="IS-005",
        row_code_soe="IS-023",
        fallback_standard="6602",
        nature=AccountNature.EXPENSE,
        note="损益类借方；同 K8（实证 trial_balance 6602 = 72,957,201.11）",
    ),
    "K10": KCycleSpec(
        wp_code="K10",
        account_name="其他收益",
        row_code_listed="IS-010",
        row_code_soe="IS-030",
        fallback_standard="6117",
        nature=AccountNature.INCOME,
        note="损益类贷方；trial_balance 符号在项目间不统一（-146,477.91 与 +15,712.56 并存）"
        "→ 按报表口径取绝对值并留 raw_sign",
    ),
    "K11": KCycleSpec(
        wp_code="K11",
        account_name="资产减值损失",
        row_code_listed="IS-017",
        row_code_soe="IS-038",
        fallback_standard="6701",
        nature=AccountNature.EXPENSE,
        note="🔴 两版 formula 均为 None → resolved_from 恒 fallback；"
        "兜底码依据 account_chart 实证 6701=资产减值损失（6702=信用减值损失属 G14）",
    ),
    "K12": KCycleSpec(
        wp_code="K12",
        account_name="营业外收入",
        row_code_listed="IS-020",
        row_code_soe="IS-041",
        fallback_standard="6301",
        nature=AccountNature.INCOME,
        note="损益类贷方；同 K10 的符号处理",
    ),
    "K13": KCycleSpec(
        wp_code="K13",
        account_name="营业外支出",
        row_code_listed="IS-021",
        row_code_soe="IS-043",
        fallback_standard="6711",
        nature=AccountNature.EXPENSE,
        note="损益类借方；同 K8",
    ),
}

#: K6 负债侧报表行（K6 一个循环管资产与负债两侧，资产侧行号在 `K_CYCLE_SPECS`）
K6_LIABILITY_ROW_CODE_LISTED = "BS-056"
K6_LIABILITY_ROW_CODE_SOE = "BS-079"


def get_k_cycle_spec(wp_code: str) -> KCycleSpec | None:
    """按 wp_code 取声明（大小写不敏感）。未登记返 ``None``。"""
    return K_CYCLE_SPECS.get(str(wp_code or "").strip().upper())


def pl_cycle_codes() -> list[str]:
    """损益类循环的 wp_code 列表（K8~K13）。"""
    return [c for c, s in K_CYCLE_SPECS.items() if s.is_pl]


def balance_cycle_codes() -> list[str]:
    """资产负债类循环的 wp_code 列表（K3/K4/K5/K6/K7）。"""
    return [c for c, s in K_CYCLE_SPECS.items() if not s.is_pl]


def no_account_cycle_codes() -> list[str]:
    """三表零命中、走宁缺勿造的循环（K4/K6）。"""
    return [c for c, s in K_CYCLE_SPECS.items() if not s.has_account]


# ─────────────────────────────────────────────────────────────────────────────
# SemanticAccountSpec 转换（供 resolve_semantic_accounts 调用方使用）
# ─────────────────────────────────────────────────────────────────────────────

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

_PROVISION_WORDS = ("减值准备", "坏账准备", "跌价准备")


def to_semantic_spec(kspec: KCycleSpec) -> SemanticAccountSpec:
    """将 KCycleSpec → SemanticAccountSpec（用于 resolve_semantic_accounts）。"""
    return SemanticAccountSpec(
        row_code=kspec.row_code_soe,  # 默认用国企行号（在册项目绝大多数是 soe）
        slots=(
            SemanticAccountSlot(
                key="gross",
                names=(kspec.account_name,),
                exclude_names=_PROVISION_WORDS,
                fallback_standard_codes=(kspec.fallback_standard,) if kspec.fallback_standard else (),
                label=kspec.account_name,
            ),
        ),
    )


def semantic_spec_of(wp_code: str) -> SemanticAccountSpec | None:
    """按 wp_code 取 SemanticAccountSpec（K3~K13）。未登记返 None。"""
    kspec = get_k_cycle_spec(wp_code)
    if kspec is None:
        return None
    return to_semantic_spec(kspec)


__all__ = [
    "EMPTY_REASON_NO_ACCOUNT",
    "K6_LIABILITY_ROW_CODE_LISTED",
    "K6_LIABILITY_ROW_CODE_SOE",
    "K_CYCLE_SPECS",
    "MISUSED_ACCOUNT_CODES",
    "NONEXISTENT_ACCOUNT_CODES",
    "KCycleSpec",
    "balance_cycle_codes",
    "get_k_cycle_spec",
    "no_account_cycle_codes",
    "pl_cycle_codes",
    "semantic_spec_of",
    "to_semantic_spec",
]
