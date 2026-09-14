"""H6 固定资产清理的语义科目定位规格（单一真源）。

**报表行**：固定资产清理 `1606` 含于 `BS-028`（公式 soe: `TB('1601')-TB('1602')+TB('1606')`）。
无独立报表行，`row_code` 设为 `BS-028` 供溯源面板展示。

**单层结构**：只有原值 `1606`，无备抵。

🔴 **H6 的「固定资产清理」与 H1 的「固定资产」互为镜像约束**：
- H1 的原值槽否决词含「清理」（否则 `1606 固定资产清理` 被 H1 吃掉）
- H6 用完整名称「固定资产清理」精确匹配（否则被 H1 的「固定资产」包含匹配吃掉）
守卫须双向断言。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

#: 槽键 → 前端 `tb_values` 键前缀
H6_SLOT_KEY_PREFIX = {
    "gross": "disposal",
}

H6_ACCOUNT_SPEC = SemanticAccountSpec(
    row_code="BS-028",  # 含于固定资产行
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("固定资产清理",),
            exclude_names=("减值准备",),
            fallback_standard_codes=("1606",),
            label="固定资产清理",
        ),
    ),
)

__all__ = ["H6_ACCOUNT_SPEC", "H6_SLOT_KEY_PREFIX"]
