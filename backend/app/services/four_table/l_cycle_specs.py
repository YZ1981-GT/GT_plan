"""L 循环（借款/应付债券/长期应付/专项应付/其他非流动负债/财务费用）语义科目定位规格。

🔴 L 循环**全部为负债类**（`is_liability=True`）—— 原值贷方，不做备抵拆分。
L8 财务费用为损益类。

科目映射真源 = `report_config` DB 实证：
  L1 `BS-041` = `TB('2001','期末余额')`（短期借款）
  L2 `BS-062` 应付利息（新准则不单列，并入 K3，`row_code=None`）
  L3 `BS-060` = `TB('2501','期末余额')`（长期借款）
  L4 `BS-061` = `TB('2502','期末余额')`（应付债券）
  L5 `BS-064` = `TB('2701','期末余额')`（长期应付款）
  L6 `BS-065` = `TB('2711','期末余额')`（专项应付款）
  L7 `BS-066` = `TB('2801','期末余额')`（其他非流动负债）
  L8 财务费用（IS 行，损益类）

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

_LIABILITY_EXCLUDES = ("减值准备", "坏账准备")


def _liability(key, names, fallback, label):
    """负债类槽：不拆备抵。"""
    return SemanticAccountSlot(
        key=key, names=names, exclude_names=_LIABILITY_EXCLUDES,
        fallback_standard_codes=fallback, label=label,
    )


L1_SPEC = SemanticAccountSpec(
    row_code="BS-041",
    slots=(_liability("gross", ("短期借款",), ("2001",), "短期借款"),),
)

L2_SPEC = SemanticAccountSpec(
    row_code=None,  # 新准则不单列应付利息
    slots=(_liability("gross", ("应付利息",), ("2231",), "应付利息"),),
)

L3_SPEC = SemanticAccountSpec(
    row_code="BS-060",
    slots=(_liability("gross", ("长期借款",), ("2501",), "长期借款"),),
)

L4_SPEC = SemanticAccountSpec(
    row_code="BS-061",
    slots=(_liability("gross", ("应付债券",), ("2502",), "应付债券"),),
)

L5_SPEC = SemanticAccountSpec(
    row_code="BS-064",
    slots=(_liability("gross", ("长期应付款",), ("2701",), "长期应付款"),),
)

L6_SPEC = SemanticAccountSpec(
    row_code="BS-065",
    slots=(_liability("gross", ("专项应付款",), ("2711",), "专项应付款"),),
)

L7_SPEC = SemanticAccountSpec(
    row_code="BS-066",
    slots=(
        # 🔴 2801 已被 K5 预计负债认领（DB 实证：account_chart 5 条 / tb_balance 39 行）
        #    其他非流动负债在实务中是**报表行**、由多个明细科目归集 → 宁缺勿造不给兜底码
        _liability("gross", ("其他非流动负债",), (), "其他非流动负债"),
    ),
)

L8_SPEC = SemanticAccountSpec(
    row_code="IS-009",
    slots=(
        SemanticAccountSlot(
            key="gross", names=("财务费用",),
            exclude_names=(), fallback_standard_codes=("6603",), label="财务费用",
        ),
    ),
)


L_CYCLE_SPECS: dict[str, SemanticAccountSpec] = {
    "L1": L1_SPEC, "L2": L2_SPEC, "L3": L3_SPEC, "L4": L4_SPEC,
    "L5": L5_SPEC, "L6": L6_SPEC, "L7": L7_SPEC, "L8": L8_SPEC,
}

L_PL_CYCLES = frozenset({"L8"})
L_PL_POSITIVE_SIDE: dict[str, str] = {"L8": "debit"}


def spec_of(wp_code: str) -> SemanticAccountSpec | None:
    return L_CYCLE_SPECS.get(str(wp_code or "").strip().upper())


__all__ = [
    "L1_SPEC", "L2_SPEC", "L3_SPEC", "L4_SPEC",
    "L5_SPEC", "L6_SPEC", "L7_SPEC", "L8_SPEC",
    "L_CYCLE_SPECS", "L_PL_CYCLES", "L_PL_POSITIVE_SIDE", "spec_of",
]
