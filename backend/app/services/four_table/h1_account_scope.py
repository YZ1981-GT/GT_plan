"""H1 固定资产的语义科目定位规格（单一真源）。

**报表行**（`report_config` 实证）::

    BS-028 固定资产
      listed_standalone   : TB('1601','期末余额') - TB('1602','期末余额')
      soe_standalone      : TB('1601') - TB('1602') + TB('1606')
    IMP-011 固定资产减值准备
      soe_standalone      : TB('1603','期末余额')

**三层结构**：原值 `1601` / 累计折旧 `1602` / 减值准备 `1603`。

🔴 **H1 的「累计折旧」是裸名称**（不含「固定资产」前缀），须用否决词排除
同名的投资性房地产/使用权资产/生产性生物资产/油气累计折旧（`1525`/`1642`/`1622`/`1632`）。

🔴 **原值槽的「固定资产」会包含匹配到「固定资产清理」(`1606`)** → 否决词含「清理」。
（H6 反向用「固定资产清理」精确匹配，两条互为镜像。）

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

_GROSS_EXCLUDES = (
    "累计折旧",
    "减值准备",
    "清理",
    "减值损失",
    "折旧",
)

#: 槽键 → 前端 `tb_values` 键前缀（保持既有契约）
H1_SLOT_KEY_PREFIX = {
    "gross": "cost",
    "accum_dep": "dep",
    "impairment": "imp",
}

H1_ACCOUNT_SPEC = SemanticAccountSpec(
    row_code="BS-028",
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("固定资产",),
            exclude_names=_GROSS_EXCLUDES,
            fallback_standard_codes=("1601",),
            label="固定资产原值",
        ),
        SemanticAccountSlot(
            key="accum_dep",
            names=("累计折旧",),
            exclude_names=("投资性房地产", "使用权资产", "生产性生物资产", "油气"),
            fallback_standard_codes=("1602",),
            label="累计折旧",
            is_provision=True,
        ),
        SemanticAccountSlot(
            key="impairment",
            names=("固定资产减值准备",),
            exclude_names=("减值损失",),
            fallback_standard_codes=("1603",),
            label="减值准备",
            is_provision=True,
        ),
    ),
)

__all__ = ["H1_ACCOUNT_SPEC", "H1_SLOT_KEY_PREFIX"]
