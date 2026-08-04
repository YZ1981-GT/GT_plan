"""H3 投资性房地产的语义科目定位规格（单一真源）。

**修掉的真实缺陷（2026-08-01）**

`_h3_investment_property._H3_ACCOUNT_PREFIXES` 原写::

    {"1503": 投资性房地产原值, "1504": 累计折旧}

而 `account_chart` 实证：``1503 = 可供出售金融资产``（旧准则，G6 域）、
``1504 = 债权投资``（G4 域）。投资性房地产真实科目族是::

    1521 投资性房地产
    1525 投资性房地产累计折旧
    1526 投资性房地产累计摊销      ← 土地使用权走摊销，原实现完全没有这一槽
    1527 投资性房地产减值准备      ← 同样缺失

即 H3 取数**取的是另外两个循环的科目**，且缺两个槽。

**为什么必须走语义定位而不是把码改成 1521/1525/1526/1527**

`account_mapping` 只读实证（10 个项目）—— 同一原始码在不同项目映射到**不同标准码**::

    1525 投资性房地产累计折旧 → 1521（1 个项目，**并入母科目**）
    1525 投资性房地产累计折旧 → 1525（4 个项目，独立）
    1527 投资性房地产减值准备 → 1521（1 个项目）
    1527 投资性房地产减值准备 → 1527（3 个项目）

那个把累计折旧并入 `1521` 的项目，若按标准码 `1525` 查 `trial_balance` 会**取空**；
反之按 `1521` 查会把原值与累计折旧混在一起。故只能按**科目名称**在该项目自己的科目表里定位，
再各自经 `account_mapping` 换算 —— 这正是
`semantic_account_resolver` 存在的理由。

**报表行**（`report_config` 实证，四准则公式**不同**，不可只看一条）::

    BS-027 投资性房地产
      listed_consolidated : TB('1521','期末余额')
      listed_standalone   : TB('1521') - TB('1525') - TB('1526')
      soe_consolidated    : TB('1521','期末余额')
      soe_standalone      : TB('1521') - TB('1525')
    IMP-010 九、投资性房地产减值准备
      soe_standalone      : TB('1527','期末余额')

`report_config` 在本循环**恰好是对的**，故它作为「提示 + 冲突检测」会与语义结果一致；
一旦某项目自定义了报表行公式，`SemanticAccountResult.conflicts` 会把差异暴露到溯源面板。

🔴 **`direction` 不可用于备抵判定**：实证 `1525`/`1526`/`1527` 在
`account_chart` 里 `direction` 全是 ``debit``（不是 credit）→ 只能靠科目名关键字。
`is_provision` 因此在槽里**显式声明**，不由方向推断。

spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
      Requirements 2.1~2.3 / Property 4
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

#: 原值槽的否决词 —— `投资性房地产累计折旧` **包含** `投资性房地产`，
#: 无否决词时原值会把三个备抵槽一并吃掉（虚增原值）。
_GROSS_EXCLUDES = (
    "累计折旧",
    "累计摊销",
    "减值准备",
    "减值损失",
    "公允价值变动",
    "处置",
)

#: 输出槽键 → 前端 `tb_values` 键前缀（保持既有契约：`ip_*` / `dep_*` 原样不动）
H3_SLOT_KEY_PREFIX = {
    "gross": "ip",
    "accum_dep": "dep",
    "accum_amort": "amort",
    "impairment": "impair",
}

H3_ACCOUNT_SPEC = SemanticAccountSpec(
    row_code="BS-027",
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("投资性房地产",),
            exclude_names=_GROSS_EXCLUDES,
            fallback_standard_codes=("1521",),
            label="投资性房地产原值",
        ),
        # 🔴🔴 **不得**把裸名 `累计折旧` / `累计摊销`列为兜底名（2026-08-04 真实库实证）
        #
        # `match_slot_in_chart` 按 `names` 声明顺序取第一个**精确命中**的名字。
        # DB 实证：裸名 `累计折旧` 在全库唯一对应 `1602`（**固定资产**累计折旧，
        # standard 侧 10 个项目 / client 侧 7 个项目都是这个裸名），裸名 `累计摊销`
        # 唯一对应 `1702`（无形资产累计摊销）；而 `1525 投资性房地产累计折旧` /
        # `1526 投资性房地产累计摊销` 只在 4~5 个项目的科目表里存在。
        # → 科目表缺 1525/1526 时，原实现的第二个名字会精确命中 1602/1702，
        #   把**固定资产的累计折旧 + 无形资产的累计摊销**从投资性房地产原值里扣掉，
        #   实测三个项目的投资性房地产账面金额变成负数
        #   （`4f6dbc36` −21,601,944.08 / `df5b8403` −11,322,704.22 /
        #    `f064f5e4` −21,864,702.78）。`exclude_names` 拦不住 —— 裸名里没有
        #   「固定资产」「无形资产」这些关键词。
        #
        # 删掉裸名后：科目表有 1525/1526 → 按专名精确命中（行为不变）；
        # 没有 → 槽 `found=False` → 如实按「本项目无此科目」处理、**不扣减**
        #（宁缺勿造），账面金额回归原值口径。
        SemanticAccountSlot(
            key="accum_dep",
            names=("投资性房地产累计折旧",),
            exclude_names=("固定资产", "使用权资产", "生产性生物资产"),
            fallback_standard_codes=("1525",),
            label="累计折旧",
            is_provision=True,
        ),
        SemanticAccountSlot(
            key="accum_amort",
            names=("投资性房地产累计摊销",),
            exclude_names=("无形资产", "使用权资产", "长期待摊费用"),
            fallback_standard_codes=("1526",),
            label="累计摊销",
            is_provision=True,
        ),
        SemanticAccountSlot(
            key="impairment",
            names=("投资性房地产减值准备",),
            exclude_names=("减值损失",),
            fallback_standard_codes=("1527",),
            label="减值准备",
            is_provision=True,
        ),
    ),
    # 旧准则同族科目：客户仍在用时提示人工映射，**不自动归槽**
    # （旧准则「投资性房地产」科目号本身就是 1521，故此处主要防御自建科目表的变体命名）
    legacy_standard_names=(),
)

__all__ = ["H3_ACCOUNT_SPEC", "H3_SLOT_KEY_PREFIX"]
