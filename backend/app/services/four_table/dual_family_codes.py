"""双族并存科目的单一真源（使用权资产 / 租赁负债）。

**问题**

CAS 21（2018 修订）实施过程中，平台标准科目表里出现了**两套并存的编码族**：

===================  ==============  ==============
语义                  旧族（primary）  新族（alternate）
===================  ==============  ==============
使用权资产             1641            1651
使用权资产累计折旧      1642            1652
使用权资产减值准备      1643            （无）
租赁负债               2601            2651
未确认融资费用          2602            （并入 2651.02）
===================  ==============  ==============

而 `report_config` 的 ``BS-031`` / ``BS-063`` 与
`prefill_formula_mapping.json` 的 H8/H9 公式**只写了 primary 族**。

**真实库实证（2026-08-06，9 个有 trial_balance 的项目）**

``trial_balance.unadjusted_amount`` 全库合计::

    1641 =        160,078.75   ← primary，5 个项目
    1651 =    386,272,594.21   ← alternate，5 个项目
    1642 =         68,950.60
    1652 =    246,042,927.81
    2601 =         98,176.48
    2651 =    146,970,513.03

即按 primary 取数只能取到真实金额的 **0.04%** —— 不是「恒空」而是
「取到一个极小的错数」，比恒空更隐蔽（界面有值，没人会去核）。

``tb_balance.closing_balance`` 侧同构（1651 = 872,197,195.23 /
2651 = −134,149,603.09，而 1641/2601 只有 1 个项目且为 0.00）。

**为什么是「加和」而不是「改码」**

逐项目透视实证（9 个项目 × 7 个码）：**两族在同一项目内互斥** ——
每个项目只出现一族，另一族为 NULL。唯一两族都有记录的项目
``0ec33ac9`` 双方**均为 0.00**。

⇒ ``TB('1641')+TB('1651')`` 在真实数据上**零双算风险**，
且不需要动任何现有码。

反过来，「把 1641 改成 1651」会踩到平台已实证的最贵陷阱：
`report-config-account-code-integrity` spec 的 V138 曾把一个
零命中码改成「存在的码」，导致 L3 循环从「碰巧正确」变成
「活的取数错误」（memory §踩坑铁律首条）。改码要同时核对
全部 `row_code` 消费方；加和则是纯 additive，无此风险。

**为什么改 `report_config` 对语义定位零影响**

`semantic_account_resolver` 的报表公式兜底层（层③）只在
``len(spec.slots) == 1`` 时启用（``allow_report_config_tier``）。
H8 是 3 槽、H9 是 2 槽 ⇒ 两者都**不走**层③ ⇒ 改 ``BS-031``/``BS-063``
只修正报表本身的取数，不改变底稿侧的科目定位结果。

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
      Requirements 1.1~1.7 / Property 1~4
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DualFamilyGroup:
    """一个语义槽下并存的两套标准科目码。

    :param slot_key: 语义槽键（与 `h{n}_account_scope` 的槽键一致）
    :param label: 中文标签（溯源展示用）
    :param primary: 旧族码（`report_config` 与既有预设里已写的那个）
    :param alternate: 新族码；``None`` 表示该语义只有一族
    :param is_provision: 是否备抵性质（决定加和后是加项还是减项）
    :param source_ref: 判据出处
    :param evidence: 真实库实证（金额级，供后来者复核而不必重跑）
    """

    slot_key: str
    label: str
    primary: str
    alternate: str | None
    is_provision: bool
    source_ref: str
    evidence: str

    @property
    def codes(self) -> tuple[str, ...]:
        """该语义下应当**全部并取**的码（去重、保持 primary 在前）。"""
        if self.alternate is None or self.alternate == self.primary:
            return (self.primary,)
        return (self.primary, self.alternate)


#: 使用权资产 / 租赁负债双族（H8 / H9）
#:
#: 🔴 顺序即 `codes` 顺序，公式字面量按此拼接；改顺序会让
#: `test_h_cycle_preset_account_coherence` 的逐字断言打红。
ROU_LEASE_DUAL_FAMILIES: tuple[DualFamilyGroup, ...] = (
    DualFamilyGroup(
        slot_key="gross",
        label="使用权资产原值",
        primary="1641",
        alternate="1651",
        is_provision=False,
        source_ref="report_config BS-031 四变体 / account_chart standard+client",
        evidence=(
            "trial_balance.unadjusted_amount 全库合计："
            "1641=160,078.75（5 项目） vs 1651=386,272,594.21（5 项目）；"
            "tb_balance.closing_balance：1641=0.00（1 项目） vs "
            "1651=872,197,195.23（9 项目）。两族逐项目互斥。"
        ),
    ),
    DualFamilyGroup(
        slot_key="accum_dep",
        label="使用权资产累计折旧",
        primary="1642",
        alternate="1652",
        is_provision=True,
        source_ref="report_config BS-031 减项 / account_chart standard+client",
        evidence=(
            "trial_balance：1642=68,950.60 vs 1652=246,042,927.81；"
            "tb_balance：1642=0.00 vs 1652=−192,937,269.19（贷方备抵）。"
        ),
    ),
    DualFamilyGroup(
        slot_key="impairment",
        label="使用权资产减值准备",
        primary="1643",
        alternate=None,
        is_provision=True,
        source_ref="report_config BS-031 减项",
        evidence=(
            "1643 全库 trial_balance=0.00（5 项目）、tb_balance=0.00（1 项目）；"
            "新族无对应减值准备码（客户科目表未见 1653），故 alternate=None。"
            "宁缺勿造：不为它臆造一个 1653。"
        ),
    ),
    DualFamilyGroup(
        slot_key="lease_liability",
        label="租赁负债",
        primary="2601",
        alternate="2651",
        is_provision=False,
        source_ref="report_config BS-063 四变体 / account_chart standard+client",
        evidence=(
            "trial_balance：2601=98,176.48（5 项目） vs "
            "2651=146,970,513.03（5 项目）；tb_balance：2601=0.00（1 项目） vs "
            "2651=−134,149,603.09（9 项目）。"
        ),
    ),
    DualFamilyGroup(
        slot_key="unearned_finance",
        label="未确认融资费用",
        primary="2602",
        alternate=None,
        is_provision=True,
        source_ref="report_config BS-063 减项 / account_mapping 实证",
        evidence=(
            "2602 全库 trial_balance=3,956.64（5 项目）；新族把它做成 "
            "2651.02 子科目（account_mapping 实证 "
            "`2651.02 租赁负债_未确认融资费用 → 2651` auto_exact 5 项目 / "
            "→ 2602 auto_fuzzy 2 项目）⇒ 新族下它**已含在 2651 父额内**，"
            "再减一次即双算。故 alternate=None，且加和公式里 2651 不重复减。"
        ),
    ),
)

#: 按槽键索引（供 `h{n}_account_scope` 引用，避免写字面量）
DUAL_FAMILY_BY_SLOT: dict[str, DualFamilyGroup] = {
    g.slot_key: g for g in ROU_LEASE_DUAL_FAMILIES
}

#: 🔴 `(循环, 语义槽键)` → 本表的 `slot_key`。
#:
#: 存在理由：`h{n}_account_scope` 的槽键是**循环内局部命名**，与本模块的语义键
#: 不同名 —— H9 的租赁负债槽键是 ``gross``（每个循环的主科目槽都叫 gross），
#: 而本表叫 ``lease_liability``。若两侧硬绑同名，改任一侧就静默失联
#: （`codes_for_slot('gross')` 会返回**使用权资产**的码给 H9）。
#:
#: 故按 `(cycle, slot_key)` 二元组显式映射，并由守卫断言映射覆盖
#: H8/H9 的全部槽（含 `impairment` 这类 alternate 为 None 的槽）。
CYCLE_SLOT_TO_DUAL_FAMILY: dict[tuple[str, str], str] = {
    ("H8", "gross"): "gross",
    ("H8", "accum_dep"): "accum_dep",
    ("H8", "impairment"): "impairment",
    ("H9", "gross"): "lease_liability",
    ("H9", "unearned_finance"): "unearned_finance",
}


def codes_for_cycle_slot(cycle: str, slot_key: str) -> tuple[str, ...]:
    """按 `(循环, 循环内槽键)` 取应并取的全部码。

    未登记的组合返回空元组 —— 调用方保留自己的兜底码（本函数只负责双族语义，
    不接管别的循环的科目定位）。
    """
    mapped = CYCLE_SLOT_TO_DUAL_FAMILY.get((cycle, slot_key))
    return codes_for_slot(mapped) if mapped else ()


def codes_for_slot(slot_key: str) -> tuple[str, ...]:
    """取某槽应并取的全部码；未登记的槽返回空元组（调用方自行兜底）。"""
    group = DUAL_FAMILY_BY_SLOT.get(slot_key)
    return group.codes if group else ()


def tb_expression(codes: tuple[str, ...], column: str) -> str:
    """生成 ``TB('a','col')+TB('b','col')`` 字面量。

    :raises ValueError: ``codes`` 为空时（宁可打红也不产出空表达式 —— 空串
        会被 prefill 引擎当合法公式吞掉，变成又一个静默 0）
    """
    if not codes:
        raise ValueError("tb_expression 需要至少一个科目码")
    return "+".join(f"TB('{c}','{column}')" for c in codes)


def dual_family_formula(
    groups: tuple[DualFamilyGroup, ...],
    column: str = "期末余额",
) -> str:
    """按 `is_provision` 拼出「原值加和 − 备抵加和」的完整公式。

    示例（BS-031）::

        TB('1641','期末余额')+TB('1651','期末余额')
        -TB('1642','期末余额')-TB('1652','期末余额')
        -TB('1643','期末余额')

    🔴 备抵**逐码减**而不是 ``-(a+b)``：`report_config` 既有形态就是逐码减，
    保持一致才能让 `test_report_formula_filler_mirror` 的两路径逐字比对成立。
    """
    if not groups:
        raise ValueError("dual_family_formula 需要至少一个分组")
    parts: list[str] = []
    for g in groups:
        for code in g.codes:
            sign = "-" if g.is_provision else ("+" if parts else "")
            parts.append(f"{sign}TB('{code}','{column}')")
    return "".join(parts)


#: `BS-031 使用权资产` 应有的槽（顺序即公式顺序）
BS031_GROUPS: tuple[DualFamilyGroup, ...] = tuple(
    DUAL_FAMILY_BY_SLOT[k] for k in ("gross", "accum_dep", "impairment")
)

#: `BS-063 租赁负债` 应有的槽
BS063_GROUPS: tuple[DualFamilyGroup, ...] = tuple(
    DUAL_FAMILY_BY_SLOT[k] for k in ("lease_liability", "unearned_finance")
)

#: 受双族影响的报表行 → 期望公式（供迁移 V145 与守卫共用，禁各写一份）
DUAL_FAMILY_ROW_FORMULAS: dict[str, str] = {
    "BS-031": dual_family_formula(BS031_GROUPS),
    "BS-063": dual_family_formula(BS063_GROUPS),
}

#: 全部涉及的码（供守卫做「互斥」与「零双算」断言）
ALL_DUAL_FAMILY_CODES: tuple[str, ...] = tuple(
    dict.fromkeys(c for g in ROU_LEASE_DUAL_FAMILIES for c in g.codes)
)

#: 只有 alternate 的码（守卫用它断言「预设/迁移确实补上了新族」）
ALTERNATE_CODES: tuple[str, ...] = tuple(
    g.alternate for g in ROU_LEASE_DUAL_FAMILIES if g.alternate
)

# ─────────────────────── 第二写入路径镜像判据 ───────────────────────
#
# 🔴 `report_config.formula` 有**多条写入路径**（memory 已记 5 条），只改迁移
# 等于白做 —— `ReportFormulaService.fill_all_formulas()` 挂在
# ``POST /api/report-config/seed`` 与 template_library 重建端点上，按**行名**
# 索引且 ``if cfg.formula: skip``（只填 NULL 行）。
#
# 本表与 `report_config_account_names.FORMULA_FILLER_MIRRORED_CORRECTIONS`
# **不同构**：后者是「(错码, 正码, 实证)」三元组用于**改码**；双族是
# **补码**（旧码保留，additive 加上新族）⇒ 单独一张表。

#: filler 的 `_BS_SPECIAL`（策略 1，最高优先级）里必须与 V145 逐字一致的行名。
FILLER_BS_SPECIAL_DUAL_FAMILY: dict[str, str] = {
    "使用权资产": DUAL_FAMILY_ROW_FORMULAS["BS-031"],
    "租赁负债": DUAL_FAMILY_ROW_FORMULAS["BS-063"],
}

#: filler 的 `_NAME_TO_ACCOUNT`（策略 5 fallback，**单码**表）里这两个行名的取值。
#:
#: 🔴 **有意保留 primary 单码，不改成加和** —— 该表的值被拼成
#: ``TB('{code}','{col}')`` 单码公式，塞加和字符串会产出
#: ``TB('TB('1641',...)+...','期末余额')`` 这种坏公式。
#:
#: 现状对这两行**不可达**（策略 1 的 `_BS_SPECIAL` 先命中），故是潜伏项而非活缺陷。
#: 登记它是为了钉死一条不变式：**只要 `_BS_SPECIAL` 还有对应条目，本表保留单码
#: 就是安全的**；一旦有人删掉 `_BS_SPECIAL` 条目，守卫立刻打红提醒同步处置
#: （届时正解是把该行名从本表删除让公式保持 NULL，而不是留一个只覆盖 0.04% 的单码）。
FILLER_NAME_TO_ACCOUNT_PRIMARY_ONLY: dict[str, str] = {
    "使用权资产": "1641",
    "租赁负债": "2601",
}



__all__ = [
    "DualFamilyGroup",
    "ROU_LEASE_DUAL_FAMILIES",
    "DUAL_FAMILY_BY_SLOT",
    "CYCLE_SLOT_TO_DUAL_FAMILY",
    "codes_for_slot",
    "codes_for_cycle_slot",
    "tb_expression",
    "dual_family_formula",
    "BS031_GROUPS",
    "BS063_GROUPS",
    "DUAL_FAMILY_ROW_FORMULAS",
    "ALL_DUAL_FAMILY_CODES",
    "ALTERNATE_CODES",
    "FILLER_BS_SPECIAL_DUAL_FAMILY",
    "FILLER_NAME_TO_ACCOUNT_PRIMARY_ONLY",
]
