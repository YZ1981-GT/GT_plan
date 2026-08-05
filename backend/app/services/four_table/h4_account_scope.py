"""H4 工程物资的语义科目定位规格（单一真源）。

H4 工程物资底稿关注 `1605 工程物资` 本体，另需 `1604 在建工程` 供 H4-1 审定表
与报表核对（H4 推附注 §五、23/八、23 的「工程物资」子表，与 H2 推的「在建工程」
子表共存于同一章节）。

**无独立报表行** — `1605` 含于 `BS-029`。
**无减值准备独立行** — 工程物资减值准备在标准科目表中**不存在独立编码**。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

#: 槽键 → 前端 `tb_values` 键前缀
H4_SLOT_KEY_PREFIX = {
    "gross": "eng_mat",
    "cip": "cip",
}

H4_ACCOUNT_SPEC = SemanticAccountSpec(
    row_code="BS-029",
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("工程物资",),
            exclude_names=("减值准备", "减值损失"),
            fallback_standard_codes=("1605",),
            label="工程物资",
        ),
        SemanticAccountSlot(
            key="cip",
            names=("在建工程",),
            exclude_names=("减值准备", "物资", "减值损失"),
            fallback_standard_codes=("1604",),
            label="在建工程（核对用）",
        ),
    ),
)

__all__ = ["H4_ACCOUNT_SPEC", "H4_SLOT_KEY_PREFIX"]
