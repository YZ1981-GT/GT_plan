"""I 循环语义科目规格 —— **从 :mod:`.i_cycle_accounts` 单向派生**（无独立真源）。

.. warning::
   🔴 **本模块不再自己声明 row_code 与兜底码**（2026-08-09 Task 5 收敛）。

   改造前它与 `i_cycle_accounts.I_CYCLE_ROW_CODES` 是**双真源**：两处各写一份 I 类
   报表行编码，而只有 `i_cycle_accounts` 那份被 6 个 render 消费。后果是
   `i_cycle_accounts` 侧 12 个取值里 **11 个错**（listed 侧整体错位一个循环、soe 侧
   落在负债段）却长期无人察觉 —— 本模块这份是对的，但**零 render 消费方**，
   改对一处另一处不动。

   现在 row_code 取自 :data:`.i_cycle_accounts.I_CYCLE_ROW_CODES`、
   兜底码取自 :data:`.i_cycle_accounts.I_CYCLE_SEGMENTS` 的段声明，
   本模块只做**形态转换**（段化 → `SemanticAccountSpec` 的 gross/provision 二分），
   供平台级守卫（跨循环兜底码互斥 / row_code 实证对账 / 语义解析覆盖率）消费。

**为什么保留本模块而不是删掉**

`I_CYCLE_SPECS` 有 6 个跨 spec 消费方（`test_cycle_specs_row_code_evidence` /
`test_cycle_specs_account_evidence` / `test_semantic_resolver_coverage` /
`test_render_fetch_smoke` / `diagnose_semantic_migration_candidates` /
`_wip_conflict_scope`），它们按 `SemanticAccountSpec` 形态迭代 `slots[].
fallback_standard_codes` 做**跨循环兜底码互斥**判定。删文件会让 I 类整体退出那张
认领表 —— 那正是当年漏掉「L7 与 K5 都认领 2801」的成因。

**形态转换的两条约定**

1. **段 → 槽**：`cost` / `expense` 段 → ``gross`` 槽；`amortization` /
   `impairment` 段 → ``provision`` 槽（按 `ISegmentSpec.absolute` 判定，
   不按段名硬编码）。I1 有两个备抵段（累计摊销 + 减值准备），二分形态下
   合并进同一个 ``provision`` 槽 —— **这正是 `i_cycle_accounts` 改用段化声明的原因**
   （见其模块 docstring「二分装不下 I1 的三段」），本模块的二分投影只供守卫用，
   **不得反向用于取数**。
2. **`trust_report_config`**：I6 保持 ``False``。实证 ``6604`` 在
   `account_chart` 的 standard 侧 6 个项目叫「研发费用」，但 **client 侧有 1 个项目
   叫「勘探费用」** → 对那个项目按 6604 取数会拿到勘探费用，故只靠按科目名定位。

spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ Requirement 1.3
"""
from __future__ import annotations

from .i_cycle_accounts import (
    I_CYCLE_ROW_CODES,
    I_CYCLE_SEGMENTS,
    resolve_row_code,
)
from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

_PROVISION_WORDS = ("减值准备", "坏账准备", "跌价准备", "累计折旧", "累计摊销", "减值损失")

#: 不信 `report_config` 兜底层的循环（连带理由见模块 docstring 第 2 条）
_DISTRUST_REPORT_CONFIG = frozenset({"I6"})


def _slots_for(wp_code: str) -> tuple[SemanticAccountSlot, ...]:
    """把 :data:`.i_cycle_accounts.I_CYCLE_SEGMENTS` 的段声明投影成 gross/provision 二分。

    Args:
        wp_code: ``'I1'`` ~ ``'I6'``。

    Returns:
        至多两个槽（``gross`` 恒有；有备抵段时追加 ``provision``）。
        兜底码与否决词全部取自段声明，**本函数不写任何科目码字面量**。
    """
    segments = I_CYCLE_SEGMENTS.get(wp_code, ())

    gross_names: list[str] = []
    gross_codes: list[str] = []
    gross_excludes: list[str] = []
    prov_names: list[str] = []
    prov_codes: list[str] = []
    gross_label = ""
    prov_label = ""

    for seg in segments:
        if seg.absolute:  # 备抵段（累计摊销 / 减值准备）
            prov_names.extend(k for k in seg.name_keywords if k not in prov_names)
            prov_codes.extend(c for c in seg.fallback if c not in prov_codes)
            prov_label = prov_label or seg.label
        else:  # 原值段 / 损益段
            gross_names.extend(k for k in seg.name_keywords if k not in gross_names)
            gross_codes.extend(c for c in seg.fallback if c not in gross_codes)
            gross_excludes.extend(
                k for k in seg.exclude_keywords if k not in gross_excludes
            )
            gross_label = gross_label or seg.label

    slots = [
        SemanticAccountSlot(
            key="gross",
            names=tuple(gross_names),
            # 原值槽必须否决全部备抵词（否则「无形资产减值准备」会被当原值）
            exclude_names=tuple(dict.fromkeys(_PROVISION_WORDS + tuple(gross_excludes))),
            fallback_standard_codes=tuple(gross_codes),
            label=gross_label,
        )
    ]
    if prov_names or prov_codes:
        slots.append(
            SemanticAccountSlot(
                key="provision",
                names=tuple(prov_names),
                exclude_names=("减值损失",),
                fallback_standard_codes=tuple(prov_codes),
                label=prov_label,
                is_provision=True,
            )
        )
    return tuple(slots)


def _spec_for(wp_code: str) -> SemanticAccountSpec:
    """构造某 I 循环的 `SemanticAccountSpec`（row_code 与兜底码全部派生）。"""
    return SemanticAccountSpec(
        row_code=resolve_row_code(wp_code, ()),  # 空 standards → listed 侧（两侧同码）
        slots=_slots_for(wp_code),
        trust_report_config=wp_code not in _DISTRUST_REPORT_CONFIG,
    )


#: {wp_code: SemanticAccountSpec}。**派生自 `i_cycle_accounts`，无独立字面量。**
I_CYCLE_SPECS: dict[str, SemanticAccountSpec] = {
    wp: _spec_for(wp) for wp in sorted(I_CYCLE_ROW_CODES)
}

I1_SPEC = I_CYCLE_SPECS["I1"]
I2_SPEC = I_CYCLE_SPECS["I2"]
I3_SPEC = I_CYCLE_SPECS["I3"]
I4_SPEC = I_CYCLE_SPECS["I4"]
I5_SPEC = I_CYCLE_SPECS["I5"]
I6_SPEC = I_CYCLE_SPECS["I6"]

#: 损益类循环（取本期发生额而非期末余额）
I_PL_CYCLES = frozenset({"I6"})
#: 损益类的正方向（借方 = 费用增加）
I_PL_POSITIVE_SIDE: dict[str, str] = {"I6": "debit"}


def spec_of(wp_code: str) -> SemanticAccountSpec | None:
    """按 wp_code 取语义规格（大小写与空白不敏感）。"""
    return I_CYCLE_SPECS.get(str(wp_code or "").strip().upper())


__all__ = [
    "I1_SPEC", "I2_SPEC", "I3_SPEC", "I4_SPEC", "I5_SPEC", "I6_SPEC",
    "I_CYCLE_SPECS", "I_PL_CYCLES", "I_PL_POSITIVE_SIDE", "spec_of",
]
