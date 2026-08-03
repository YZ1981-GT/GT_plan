"""M 循环（权益类：实收资本/资本公积/盈余公积/未分配利润/专项储备/一般风险/OCI/其他权益）语义科目定位规格。

🔴 M 循环**全部为权益类**（`is_liability=True`）—— 原值贷方，不做备抵拆分。

科目映射真源 = **平台 DB 实证值**（取自各 render 策略里 `m-cycle-…` spec Wave 1
已做真实 DB 核对并 push 的 `_MX_ACCOUNT_CODE` 常量）：
  M1  应付股利 `BS-048` = `TB('2232')`（负债类）
  M2  实收资本 `BS-070` = `TB('4001')`
  M3  库存股   `BS-071` = `TB('4002')`（借方，唯一例外）
  M4  资本公积 `BS-072` = `TB('4101')`
  M5  盈余公积 `BS-074` = `TB('4102')`
  M6  未分配利润 `BS-088` = `TB('4104')`
  M7  专项储备 `BS-075` = `TB('4103')`
  M8  一般风险准备 `BS-076` = `TB('4201')`
  M9  其他综合收益 `BS-073` = `TB('4401')`
  M10 其他权益工具 `BS-077` = `TB('4301')`

spec: .kiro/specs/semantic-account-resolver-full-rollout/

.. warning::
   🔴 **本文件的兜底码尚未逐项 DB 实证**（未核 `report_config` / `account_chart` /
   `tb_balance` 三方）。当前**没有任何 render 策略用它驱动取数**，故不影响运行。
   接线前必须逐个循环按平台铁律核对真源，否则会重演「取错整个科目族」级缺陷
   （已实证教训：本文件 M 循环 7/7 兜底码曾与平台实证值全不符，已按 DB 值修正）。
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec


def _equity(key, names, fallback, label):
    """权益类槽。"""
    return SemanticAccountSlot(
        key=key, names=names, exclude_names=(),
        fallback_standard_codes=fallback, label=label,
    )


M1_SPEC = SemanticAccountSpec(
    row_code="BS-048",
    slots=(_equity("gross", ("应付股利",), ("2232",), "应付股利"),),
)

M2_SPEC = SemanticAccountSpec(
    row_code="BS-070",
    slots=(_equity("gross", ("实收资本", "股本"), ("4001",), "实收资本"),),
)

M3_SPEC = SemanticAccountSpec(
    row_code="BS-071",
    slots=(_equity("gross", ("库存股",), ("4201",), "库存股"),),
)

M4_SPEC = SemanticAccountSpec(
    row_code="BS-072",
    slots=(_equity("gross", ("资本公积",), ("4002",), "资本公积"),),
)

M5_SPEC = SemanticAccountSpec(
    row_code="BS-074",
    slots=(_equity("gross", ("盈余公积",), ("4101",), "盈余公积"),),
)

M6_SPEC = SemanticAccountSpec(
    row_code="BS-088",
    slots=(_equity("gross", ("未分配利润", "利润分配"), ("4104",), "未分配利润"),),
)

M7_SPEC = SemanticAccountSpec(
    row_code="BS-075",
    slots=(_equity("gross", ("专项储备",), ("4301",), "专项储备"),),
)

M8_SPEC = SemanticAccountSpec(
    row_code="BS-076",
    slots=(_equity("gross", ("一般风险准备",), ("4302",), "一般风险准备"),),
)

M9_SPEC = SemanticAccountSpec(
    row_code="BS-073",
    slots=(_equity("gross", ("其他综合收益",), ("4003",), "其他综合收益"),),
)

M10_SPEC = SemanticAccountSpec(
    row_code="BS-077",
    slots=(_equity("gross", ("其他权益工具",), ("4401",), "其他权益工具"),),
)


M_CYCLE_SPECS: dict[str, SemanticAccountSpec] = {
    "M1": M1_SPEC, "M2": M2_SPEC, "M3": M3_SPEC, "M4": M4_SPEC,
    "M5": M5_SPEC, "M6": M6_SPEC, "M7": M7_SPEC, "M8": M8_SPEC,
    "M9": M9_SPEC, "M10": M10_SPEC,
}

M_PL_CYCLES: frozenset = frozenset()
M_PL_POSITIVE_SIDE: dict[str, str] = {}


def spec_of(wp_code: str) -> SemanticAccountSpec | None:
    return M_CYCLE_SPECS.get(str(wp_code or "").strip().upper())


__all__ = [
    "M1_SPEC", "M2_SPEC", "M3_SPEC", "M4_SPEC", "M5_SPEC",
    "M6_SPEC", "M7_SPEC", "M8_SPEC", "M9_SPEC", "M10_SPEC",
    "M_CYCLE_SPECS", "M_PL_CYCLES", "M_PL_POSITIVE_SIDE", "spec_of",
]
