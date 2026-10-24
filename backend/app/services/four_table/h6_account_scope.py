"""H6 固定资产清理的语义科目定位规格（单一真源）。

**报表行**：固定资产清理 `1606` 含于 `BS-028`（四个准则：`TB('1601')-TB('1602')-TB('1603')+TB('1606')`）。
无独立报表行，`row_code` 设为 `BS-028` 供溯源面板展示。

**单层结构**：只有原值 `1606`，无备抵。

🔴 **层③（报表公式给的码）必须关闭**：`BS-028` 是固定资产行，不是 H6 自己的行 —— 公式里
`1601 / 1602 / 1603 / 1606` 都在（2026-10-24 起四个准则一致），单槽规格允许层③时，客户科目表里
没有叫「固定资产清理」的科目就会把固定资产原值、累计折旧、减值准备一并当成清理科目
（spec formula-fetch-followup-defect-closure R6.4）。`row_code` 仍如实填，供溯源展示与冲突检测。

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
    trust_report_config=False,  # 见模块说明：BS-028 不是本科目自己的行
)

__all__ = ["H6_ACCOUNT_SPEC", "H6_SLOT_KEY_PREFIX"]
