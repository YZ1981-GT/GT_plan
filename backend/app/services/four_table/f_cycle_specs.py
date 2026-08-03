"""F 循环（存货/应付/成本）语义科目定位规格 — 跨 F1~F5 单一真源。

科目映射真源 = `report_config` DB 实证：
  F1 `BS-008` = `TB('1123','期末余额')`（预付账款）
  F2 `BS-010` = `SUM_TB('1401~1499','期末余额')`（存货，区间口径）
  F3 `BS-044` = `TB('2201','期末余额')`（应付票据，负债类）
  F4 `BS-045` = `TB('2202','期末余额')`（应付账款，负债类）
  F5 营业成本（IS 行，损益类）

🔴 F3/F4 为负债类（`is_liability=True`）—— 2201/2202 方向均为贷方。
🔴 F2 区间口径 `1401~1499` 含 14 个科目族（材料采购/原材料/库存商品/…/存货跌价准备），
   归类由独立 `f2_extraction/category_rules.py` 处理，本文件只做科目定位不做分类。

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

_PROVISION_WORDS = ("减值准备", "坏账准备", "跌价准备", "累计折旧", "累计摊销", "减值损失")


def _gross(key, names, fallback, label, extra_excludes=()):
    return SemanticAccountSlot(
        key=key, names=names, exclude_names=_PROVISION_WORDS + extra_excludes,
        fallback_standard_codes=fallback, label=label,
    )


# ─────────────────────────────────── F1~F5 ───────────────────────────────────

F1_SPEC = SemanticAccountSpec(
    row_code="BS-008",
    slots=(_gross("gross", ("预付账款", "预付款项"), ("1123",), "预付账款"),),
)

F2_SPEC = SemanticAccountSpec(
    row_code="BS-010",
    slots=(
        # 区间口径：1401~1499 含 14+ 个存货科目族，兜底用首码 1401
        SemanticAccountSlot(
            key="gross",
            names=("存货", "材料采购", "原材料", "库存商品"),
            exclude_names=("跌价准备", "减值准备"),
            fallback_standard_codes=("1401",),
            label="存货",
        ),
    ),
)

F3_SPEC = SemanticAccountSpec(
    row_code="BS-044",
    slots=(
        SemanticAccountSlot(
            key="gross", names=("应付票据",),
            exclude_names=_PROVISION_WORDS,
            fallback_standard_codes=("2201",), label="应付票据",
        ),
    ),
)

F4_SPEC = SemanticAccountSpec(
    row_code="BS-045",
    slots=(
        SemanticAccountSlot(
            key="gross", names=("应付账款",),
            exclude_names=_PROVISION_WORDS,
            fallback_standard_codes=("2202",), label="应付账款",
        ),
    ),
)

F5_SPEC = SemanticAccountSpec(
    row_code="IS-002",
    slots=(
        SemanticAccountSlot(
            key="gross", names=("营业成本", "主营业务成本"),
            exclude_names=(),
            fallback_standard_codes=("6401",), label="营业成本",
        ),
    ),
)


F_CYCLE_SPECS: dict[str, SemanticAccountSpec] = {
    "F1": F1_SPEC,
    "F2": F2_SPEC,
    "F3": F3_SPEC,
    "F4": F4_SPEC,
    "F5": F5_SPEC,
}

#: 损益类 F 循环
F_PL_CYCLES = frozenset({"F5"})

F_PL_POSITIVE_SIDE: dict[str, str] = {
    "F5": "debit",  # 成本类借方正方向
}


def spec_of(wp_code: str) -> SemanticAccountSpec | None:
    return F_CYCLE_SPECS.get(str(wp_code or "").strip().upper())


__all__ = [
    "F1_SPEC", "F2_SPEC", "F3_SPEC", "F4_SPEC", "F5_SPEC",
    "F_CYCLE_SPECS", "F_PL_CYCLES", "F_PL_POSITIVE_SIDE", "spec_of",
]
