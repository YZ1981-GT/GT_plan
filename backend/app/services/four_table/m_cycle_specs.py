"""M 循环（权益类：实收资本/资本公积/盈余公积/未分配利润/专项储备/一般风险/OCI/其他权益）语义科目定位规格。

🔴 M 循环**全部为权益类**（`is_liability=True`）—— 原值贷方，不做备抵拆分。

**科目码真源 = `account_chart` 的 `source='client'` 侧**（2026-08-03 全量实证，
10 个项目双向对账）::

    码     client 名（权威）    项目数
    2232   应付股利             —
    4001   实收资本             8
    4002   资本公积             7
    4003   其他综合收益         8
    4101   盈余公积             8
    4104   利润分配（=未分配利润口径）  8
    4201   库存股               5
    4301   专项储备             4
    4401   其他权益工具         5

**报表行次（`row_code`）已按 `report_config` 逐行对账改正**（2026-08-03）——
上一版 9/10 个都指向了完全无关的行（如 M8 声明 `BS-076` 实为「其他权益工具 /
其中：应付股利」、M2 声明 `BS-070` 实为「负债合计」），且其中 M1 指的 `BS-048`
**带公式 `TB('2211')`（应付职工薪酬）** → 层③会静默把应付股利解析成应付职工薪酬::

    循环  概念            row_code   report_config 公式        层③可信？
    M1   应付股利         BS-055     None（仅 listed）          —
    M2   实收资本（或股本） BS-081     TB('4001')  ✅ 与实证一致   是
    M3   库存股           BS-084     TB('4201')  ✅ V138 已修     是
    M4   资本公积         BS-083     TB('4002')  ✅              是
    M5   盈余公积         BS-087     TB('4101')  ✅              是
    M6   未分配利润        BS-088     TB('4104')  ✅              是
    M7   专项储备         BS-086     TB('4301')  ✅ V138 已修     是
    M8   一般风险准备      BS-124     None（仅 soe）             —
    M9   其他综合收益      BS-085     TB('4003')  ✅ V138 已修     是
    M10  其他权益工具      BS-082     TB('4401')  ✅ V138 已修     是

**2026-08-05 更新**：M3/M7/M9/M10 曾因上表那四行是错码而声明
`trust_report_config=False`（关闭层③）。迁移 **V138**（spec
``.kiro/specs/report-config-account-code-integrity/``）已把 `report_config` 改对，
修正值与本文件兜底码逐一相同 ⇒ 四个 flag 全部移除、层③恢复启用。

🔴 那批 flag 是**针对错码的临时防护**，不是长期设计：数据改对后继续关着层③，
会让「客户科目表里缺该科目」的项目白白取不到数（层③本来能救）。
两侧一致性由 ``test_cycle_specs_row_code_evidence`` 与
``report_config_account_names.CODE_CORRECTIONS`` 交叉锁死 ——
往 `_WRONG_FORMULA_ROWS` 里留下 V138 已修的行会打红。

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


def _equity(key, names, fallback, label):
    """权益类槽。"""
    return SemanticAccountSlot(
        key=key, names=names, exclude_names=(),
        fallback_standard_codes=fallback, label=label,
    )


#: `BS-055 应付股利` 只在 listed 两个准则下存在且 formula 为 None；soe 侧对应
#: `BS-076 其中：应付股利`（同样 None）。层③本就无从生效，如实填 listed 侧行号。
M1_SPEC = SemanticAccountSpec(
    row_code="BS-055",
    slots=(_equity("gross", ("应付股利",), ("2232",), "应付股利"),),
)

M2_SPEC = SemanticAccountSpec(
    row_code="BS-081",  # 实收资本（或股本）= TB('4001') ✅ 与 client 表实证一致
    slots=(_equity("gross", ("实收资本", "股本"), ("4001",), "实收资本"),),
)

M3_SPEC = SemanticAccountSpec(
    # 减：库存股。原 `TB('4005')` ❌（4005 全库两张表都不存在）→ **V138 已改为 4201**，
    # 与本 spec 兜底码一致 ⇒ 层③恢复启用（`trust_report_config` 回默认 True）。
    # 那个 flag 是针对错码的临时防护，数据改对后继续关着会让「客户科目表缺该科目」的
    # 项目白白取不到数（层③本来能救）。
    row_code="BS-084",
    slots=(_equity("gross", ("库存股",), ("4201",), "库存股"),),
)

M4_SPEC = SemanticAccountSpec(
    row_code="BS-083",  # 资本公积 = TB('4002') ✅
    slots=(_equity("gross", ("资本公积",), ("4002",), "资本公积"),),
)

M5_SPEC = SemanticAccountSpec(
    row_code="BS-087",  # 盈余公积 = TB('4101') ✅
    slots=(_equity("gross", ("盈余公积",), ("4101",), "盈余公积"),),
)

M6_SPEC = SemanticAccountSpec(
    row_code="BS-088",  # 未分配利润 = TB('4104') ✅（4104 client 名为「利润分配」）
    slots=(_equity("gross", ("利润分配", "未分配利润"), ("4104",), "利润分配"),),
)

M7_SPEC = SemanticAccountSpec(
    # 专项储备。原 `TB('4103')` ❌ —— 4103 client/standard 双侧都是「本年利润」且**确实存在**，
    # 层③「码必须存在」那道闸拦不住 → 曾必须显式关闭层③。
    # **V138 已改为 4301**，与本 spec 兜底码一致 ⇒ 层③恢复启用。
    row_code="BS-086",
    slots=(_equity("gross", ("专项储备",), ("4301",), "专项储备"),),
)

M8_SPEC = SemanticAccountSpec(
    # `BS-124 △一般风险准备`（仅 soe，formula None）。全库两张科目表都**没有**
    # 名为「一般风险准备」的科目 → 兜底码留空，取不到就 `found=False`（宁缺勿造）。
    # 生产代码曾硬编码 `4302`（全库不存在）与 docstring 写的 `4104`（未分配利润），
    # 两者都错，已于 2026-08-03 改走本 spec。
    row_code="BS-124",
    slots=(_equity("gross", ("一般风险准备",), (), "一般风险准备"),),
)

M9_SPEC = SemanticAccountSpec(
    # 其他综合收益。原 `TB('4102')` ❌（4102 全库不存在）→ **V138 已改为 4003**，
    # 与本 spec 兜底码一致 ⇒ 层③恢复启用。
    row_code="BS-085",
    slots=(_equity("gross", ("其他综合收益",), ("4003",), "其他综合收益"),),
)

M10_SPEC = SemanticAccountSpec(
    # 其他权益工具。原 `TB('4003')` ❌（4003 实为「其他综合收益」）→ **V138 已改为 4401**，
    # 与本 spec 兜底码一致 ⇒ 层③恢复启用。
    row_code="BS-082",
    slots=(_equity("gross", ("其他权益工具",), ("4401",), "其他权益工具"),),
)


M_CYCLE_SPECS: dict[str, SemanticAccountSpec] = {
    "M1": M1_SPEC, "M2": M2_SPEC, "M3": M3_SPEC, "M4": M4_SPEC,
    "M5": M5_SPEC, "M6": M6_SPEC, "M7": M7_SPEC, "M8": M8_SPEC,
    "M9": M9_SPEC, "M10": M10_SPEC,
}

M_PL_CYCLES: frozenset = frozenset()
M_PL_POSITIVE_SIDE: dict[str, str] = {}


def spec_of(wp_code: str) -> SemanticAccountSpec | None:
    return M_CYCLE_SPECS.get(str(wp_code or "").strip().upper())


__all__ = [
    "M1_SPEC", "M2_SPEC", "M3_SPEC", "M4_SPEC", "M5_SPEC",
    "M6_SPEC", "M7_SPEC", "M8_SPEC", "M9_SPEC", "M10_SPEC",
    "M_CYCLE_SPECS", "M_PL_CYCLES", "M_PL_POSITIVE_SIDE", "spec_of",
]
