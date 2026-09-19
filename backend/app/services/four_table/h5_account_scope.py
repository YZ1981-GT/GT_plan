"""H5 油气资产的语义科目定位规格（单一真源）。

**报表行**：`report_config` 中**无 BS 报表行**（仅有 `CFSS-005` 提折耗、
`IMP-014` formula=NULL）→ `row_code=None`，溯源面板须明示「该科目无报表行映射」。

**三层结构**：原值 `1631` / 累计折耗 `1632` / 减值准备（无独立编码，兜底空）。

🔴 旧 render 写 `_H5_ACCOUNT_PREFIXES = {"1611"}` —— `1611` 实为**融资租赁资产**。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

_GROSS_EXCLUDES = (
    "累计折耗",
    "减值准备",
    "折耗",
    "减值损失",
)

#: 槽键 → 前端 `tb_values` 键前缀
H5_SLOT_KEY_PREFIX = {
    "gross": "cost",
    "accum_depletion": "dep",
    "impairment": "imp",
}

H5_ACCOUNT_SPEC = SemanticAccountSpec(
    row_code=None,  # 油气资产在 report_config 无 BS 行
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("油气资产",),
            exclude_names=_GROSS_EXCLUDES,
            fallback_standard_codes=("1631",),
            label="油气资产原值",
        ),
        SemanticAccountSlot(
            key="accum_depletion",
            names=("油气资产累计折耗", "累计折耗"),
            exclude_names=("固定资产", "投资性房地产"),
            fallback_standard_codes=("1632",),
            label="累计折耗",
            is_provision=True,
        ),
        SemanticAccountSlot(
            key="impairment",
            names=("油气资产减值准备",),
            exclude_names=("减值损失",),
            fallback_standard_codes=(),
            label="减值准备",
            is_provision=True,
        ),
    ),
    legacy_standard_names=("矿区权益",),
)

__all__ = ["H5_ACCOUNT_SPEC", "H5_SLOT_KEY_PREFIX"]
