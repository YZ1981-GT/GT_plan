"""H10 资产处置损益的语义科目定位规格（单一真源）。

**报表行**（`report_config` 实证）::

    IS-018 资产处置收益（损失以"-"号填列）
      soe_standalone : TB('6115','本期发生额')

**单层、损益类**：只有 `gross` = `6115`，无备抵。

🔴 **损益口径**：取**本期发生额**，不是期末余额。
- `trial_balance` 优先（`unadjusted_amount` 即发生额）
- 兜底 `tb_balance`：按正方向取（`6115` direction 多为 credit，取 `credit_amount`）
- 禁用 `debit - credit`（含年末结转损益的全年账上结构性恒为 0）

🔴 `6115` 在 `account_chart` 里有三种名称：
- `资产处置损益`（debit）
- `资产处置损益`（credit）
- `资产处置收益`（credit）
→ `names` 须含两个别名。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

#: 槽键 → 前端 `tb_values` 键前缀
H10_SLOT_KEY_PREFIX = {
    "gross": "disposal_income",
}

H10_ACCOUNT_SPEC = SemanticAccountSpec(
    row_code="IS-018",
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("资产处置损益", "资产处置收益"),
            exclude_names=(),
            fallback_standard_codes=("6115",),
            label="资产处置损益",
        ),
    ),
)

#: H10 是损益类：取本期发生额，不取期末余额
H10_IS_OCCURRENCE = True

__all__ = ["H10_ACCOUNT_SPEC", "H10_SLOT_KEY_PREFIX", "H10_IS_OCCURRENCE"]
