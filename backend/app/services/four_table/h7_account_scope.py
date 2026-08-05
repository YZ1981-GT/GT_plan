"""H7 生产性生物资产的语义科目定位规格（单一真源）。

**报表行**（`report_config` 实证）::

    BS-030 生产性生物资产
      soe_standalone : TB('1621','期末余额')
    IMP-013 生产性生物资产减值准备
      formula = NULL → 兜底 (无独立编码)

**三层结构**：原值 `1621` / 累计折旧 `1622` / 减值准备（无独立编码）。

🔴 旧 render 的 `_H7_ACCOUNT_PREFIXES` 只有 `1621` 一个码（缺累计折旧 `1622`），
且公式预设块的 `1621`/`1622` 实际写的是正确码但旧 render 不消费它。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

_GROSS_EXCLUDES = (
    "累计折旧",
    "减值准备",
    "折旧",
    "减值损失",
)

#: 槽键 → 前端 `tb_values` 键前缀
H7_SLOT_KEY_PREFIX = {
    "gross": "cost",
    "accum_dep": "dep",
    "impairment": "imp",
}

H7_ACCOUNT_SPEC = SemanticAccountSpec(
    row_code="BS-030",
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("生产性生物资产",),
            exclude_names=_GROSS_EXCLUDES,
            fallback_standard_codes=("1621",),
            label="生产性生物资产原值",
        ),
        SemanticAccountSlot(
            key="accum_dep",
            names=("生产性生物资产累计折旧",),
            exclude_names=("固定资产", "投资性房地产", "使用权资产"),
            fallback_standard_codes=("1622",),
            label="累计折旧",
            is_provision=True,
        ),
        SemanticAccountSlot(
            key="impairment",
            names=("生产性生物资产减值准备",),
            exclude_names=("减值损失",),
            fallback_standard_codes=(),
            label="减值准备",
            is_provision=True,
        ),
    ),
)

__all__ = ["H7_ACCOUNT_SPEC", "H7_SLOT_KEY_PREFIX"]
