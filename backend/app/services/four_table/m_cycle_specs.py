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

.. note::
   **兜底码已逐项 DB 实证**（2026-08-03，双向对账 `account_chart`：① 该码实际叫什么名
   ② 该名实际挂在哪个码）。曾修正的错码见各槽行内注释。

.. warning::
   🔴 **`account_chart` 并存两套编码体系** —— 同一码在 ``source='client'`` 与
   ``source='standard'`` 下可能是**完全不同的科目**（实证 10 个项目）::

       码     client 表（8 项目）    standard 表（5 项目）
       4001   实收资本               生产成本
       4101   盈余公积               制造费用
       4401   其他权益工具           工程施工
       4301   专项储备               研发支出

   故 :func:`resolve_semantic_accounts` 的「**client chart 优先**按名定位」不是优化
   而是**正确性前提**：硬编码码值 + 走 standard 表会在那 5 个项目取到成本类科目。
   同族已知现象见 memory「存货科目编码语义在项目间冲突」。

   另：本文件的兜底码只在「按名定位失败」时生效，且要求该码**在本项目科目表里确实存在**
   （见 `semantic_account_resolver` 定位链路第 ④ 层），故一码两义不会因兜底而取错。
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
    slots=(_equity("gross", ("利润分配", "未分配利润"), ("4104",), "利润分配"),),
)

M7_SPEC = SemanticAccountSpec(
    row_code="BS-075",
    slots=(_equity("gross", ("专项储备",), ("4301",), "专项储备"),),
)

M8_SPEC = SemanticAccountSpec(
    row_code="BS-076",
    slots=(_equity("gross", ("一般风险准备",), (), "一般风险准备"),),
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
