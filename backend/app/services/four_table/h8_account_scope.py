"""H8 使用权资产的语义科目定位规格（单一真源）。

**修掉的真实缺陷**

`_h8_right_of_use_assets._H8_ACCOUNT_PREFIXES = {"1901","190101"}` ——
`1901` 实为**待处理财产损溢**（`BS-014 其他流动资产` 亦引用 `1901`），
`190101` 是无点号平铺形态且非真实科目。使用权资产真实族::

    1641 使用权资产
    1642 使用权资产累计折旧
    1643 使用权资产减值准备

`_h8` 的 `is_contra = len(code) > 4 and code.startswith("1901")` 把任何子科目都当
累计折旧 → 逻辑完全错误（真实累计折旧是 `1642`，三个码互相独立）。

**报表行**（`report_config` 实证）::

    BS-031 使用权资产
      listed_standalone   : TB('1641','期末余额') - TB('1642','期末余额') - TB('1643','期末余额')
      soe_standalone      : TB('1641') - TB('1642') - TB('1643')
    IMP-015 使用权资产减值准备
      soe_standalone      : TB('1643','期末余额')

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

from .dual_family_codes import codes_for_cycle_slot
from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

_GROSS_EXCLUDES = (
    "累计折旧",
    "减值准备",
    "折旧",
    "减值损失",
)

#: 槽键 → 前端 `tb_values` 键前缀（保持既有契约：`rou_asset`/`rou_dep` 不变，新增 `rou_imp`）
H8_SLOT_KEY_PREFIX = {
    "gross": "rou_asset",
    "accum_dep": "rou_dep",
    "impairment": "rou_imp",
}

# 🔴 兜底码走**双族真源** `dual_family_codes`（spec h-cycle-… 裁决 1 / Task 6）：
# 使用权资产在真实库里**两套编码族并存且逐项目互斥** ——
#   trial_balance: 1641=160,078.75（5 项目） vs 1651=386,272,594.21（5 项目）
#   tb_balance:    1641=0.00（1 项目）      vs 1651=872,197,195.23（9 项目）
# 只写 `("1641",)` 时，在用新族的 9 个项目上**只取到 0.04%**（比恒空更隐蔽）。
# 两族在同一项目内互斥（唯一并存的 0ec33ac9 双方均 0.00）⇒ 并取零双算风险。
# 这里**不写字面量** —— 引常量才能让「改一处漏一处」在守卫里立刻暴露。
_GROSS_CODES = codes_for_cycle_slot("H8", "gross")
_ACCUM_DEP_CODES = codes_for_cycle_slot("H8", "accum_dep")
_IMPAIRMENT_CODES = codes_for_cycle_slot("H8", "impairment")

H8_ACCOUNT_SPEC = SemanticAccountSpec(
    row_code="BS-031",
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("使用权资产",),
            exclude_names=_GROSS_EXCLUDES,
            fallback_standard_codes=_GROSS_CODES,
            label="使用权资产原值",
        ),
        SemanticAccountSlot(
            key="accum_dep",
            # 🔴 不列裸名 `累计折旧`：DB 实证它全库唯一对应 `1602`（**固定资产**累计折旧，
            # standard 10 / client 7 个项目都是裸名），而 `match_slot_in_chart` 按 names
            # 顺序取第一个精确命中 → 科目表缺使用权资产累计折旧时会把固定资产的折旧扣进来
            # （H3 同款写法已实测让投资性房地产账面金额变负，见 h3_account_scope 注释）。
            # 本循环当前是**潜伏态**（1642/1652 在各项目科目表里都在，专名先命中），
            # 删裸名后行为逐字不变，只关掉这条隐患。
            names=("使用权资产累计折旧",),
            exclude_names=("固定资产", "投资性房地产", "生产性生物资产", "油气"),
            fallback_standard_codes=_ACCUM_DEP_CODES,
            label="累计折旧",
            is_provision=True,
        ),
        SemanticAccountSlot(
            key="impairment",
            names=("使用权资产减值准备",),
            exclude_names=("减值损失",),
            # 🔴 该槽 `alternate=None`（新族无对应减值准备码，客户科目表未见 1653）
            # ⇒ 双族真源只返 `('1643',)`。**宁缺勿造**：不为它臆造一个 1653。
            fallback_standard_codes=_IMPAIRMENT_CODES,
            label="减值准备",
            is_provision=True,
        ),
    ),
    legacy_standard_names=("融资租赁资产",),
)

__all__ = ["H8_ACCOUNT_SPEC", "H8_SLOT_KEY_PREFIX"]
