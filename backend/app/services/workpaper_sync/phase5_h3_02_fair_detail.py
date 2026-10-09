"""H3-2（**公允价值模式**）「投资性房地产明细表」—— sheet 层薄声明。

spec: `h3-h5-h7-variant-axis-and-dynamic-column-paradigm`

变体轴的另一半（成本模式见 `phase5_h3_02_cost_detail`）。两张 sheet **各有独立
持久化键**（`H3-2-cost-rows` / `H3-2-fair-rows`），故各自一个 `RowTableSheetSpec`。

🔴 `H3-2-fair-rows` 在 **HC-8 冻结键**清册上：被 **G 循环**消费
（`g13SourceDetailPull.ts` 的 `{ wpCode: 'H3', itemId: 'H3-2-fair-rows' }` 与
`gCycleSourceFv.ts` 的 `H3: 'H3-2-fair-rows'`）⇒ 本轮**只补契约不动键名**。

═══ 几何（openpyxl 逐格实测）═══

`max_row=53` / `max_column=31`，**有效内容列 27（A..AA）**。
* **三级**表头 R9 / R10 / R11
* 数据区 **R12-R26（15 行）** —— 🔴 起始行比成本模式**早一行**（成本是 R13）
* footer **R27**，`A27='合计'`，全部列 SUM（无行内派生格）
* 数据行公式列 **11 个**（映射侧 2 个进 `FORMULA_TEMPLATES`）
* UUID 列 **AB** = 27 + 1
* footer 之后 R28-R32 是 `其中：` + 四行按类别 SUMPRODUCT 小计 ⇒ 不受管

═══ 两区块 × 四段 ═══

* **投资性房地产原值 C..O**（`C9`）：未审 C-H / 期初调整 I / 账项调整 J-K / 审定 L-O
  —— 与成本模式那张**逐列同构**
* **公允价值变动 P..W**（`P9`）：
  - 未审数 `P10`：P 期初余额 / Q 本年变动 / R 期末余额
  - 期初调整 `S10`（单列）
  - 本期变动调整 `T10`（单列）
  - 审定数 `U10`：U 期初余额 / V 本年变动 / W 期末余额
* 尾部：`X 期初净值`（`=L+U`）· `Y 期末净值`（`=O+W`）· `Z 是否有权属证明` ·
  `AA 是否抵押受限`

═══ 🔴 模板真实缺陷（走覆盖层，不改模板字节）═══

**`R` 列（公允价值变动·未审数·期末余额）只有首行 `R12` 有 `=P12+Q12`，
R13-R26 共 14 行缺公式。** 对照组：H7 公允价值模式的同位列 `S` 满格 25/25 有 `=Q+R`
⇒ 这是 H3 独有的漏填，不是设计意图。

后果：用户在第 2 行起填 P（期初）与 Q（本年变动）后，R（期末）不自动算 ⇒ 未审期末
累计公允变动漏算。审定侧 U/V/W 满格有公式，于是**同一张表里审定段算得出期末、
未审段算不出**（模板内部自相矛盾）。

处置沿用既有规则（F2-26!J9 / F5-7!G31 两例确立）：`backend/wp_templates/` 运行时
只读 + sha 冻结 ⇒ 缺陷走**覆盖层**，不改字节。本文件把它登记在
`TEMPLATE_DEFECTS_H302_FAIR`，`R` 列同时判 template-only（它本就无前端对端）。

═══ 🔴 前端 `fairValueBegin/End` 是「含公允变动的公允价值总额」，不是模板的「原值」 ═══

`useH3FormulaEngine.calcFairEndBalance(begin, increase, decrease, transfer, change)`
= `begin + increase - decrease + transfer + change` —— **把本年公允变动加了进去**。
而模板把「原值 C..O」与「公允价值变动 P..W」**分成两块**，净值才是两者之和
（`X=L+U` / `Y=O+W`）。

⇒ `fairValueBegin` / `fairValueEnd` **不能**映到 `C` / `H`（那是原值列）：映过去会把
公允价值总额写进原值格，`X=L+U` 立刻把公允变动**重复计一次**。两者判 store-only，
原值整块（C..O）判 template-only。

能对上的只有四点（逐条按语义核，不按名字近似）：
  · `Q 本年变动`（未审）↔ `fairValueChange`
  · `V 审定·本年变动`（`=Q+T`）↔ `fvChangeAudited`
    —— 前端 `fvChangeAudited = fvChangeUnadj + fvChangeAje + fvChangeRje`，
       而 `fvChangeUnadj` 默认取 `change`（**本年**变动）⇒ 对的是 V 不是 W。
       🔴 映到 `W`（审定期末**累计**）会把「本年变动」当成「累计余额」，差一个期初。
  · `Y 期末净值`（`=O+W`）↔ `fairAudited`
    —— 前端 `fairAudited = fairUnadj + fairAje + fairRje`，`fairUnadj` 默认取
       `fairValueEnd`（含变动的期末公允总额）⇒ 语义正是「审定后的期末公允价值总额」。
  · `AA 是否抵押受限` ↔ `mortgaged`

═══ 覆盖闭合 ═══

**6 映射 + 21 template-only == 27 有效列**，并集连续 A..AA 无缺口。
"""
from __future__ import annotations

from typing import Any, Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_H302_FAIR",
    "MANAGED_SHEET_H302_FAIR",
    "SHEET_KEY_H302_FAIR",
    "STORE_ITEM_ID_H302_FAIR",
    "ROW_IDENTITY_STORE_KEY_H302_FAIR",
    "FORMULA_TEMPLATES_H302_FAIR",
    "STORE_ONLY_FIELDS_H302_FAIR",
    "TEMPLATE_ONLY_COLUMNS_H302_FAIR",
    "DECLARED_COVERAGE_GAPS_H302_FAIR",
    "TEMPLATE_DEFECTS_H302_FAIR",
    "DERIVED_TOTAL_KEYS_H302_FAIR",
    "UNMANAGED_REGIONS_H302_FAIR",
    "EFFECTIVE_COLUMNS_H302_FAIR",
    "UUID_COL_H302_FAIR",
]

MANAGED_SHEET_H302_FAIR: Final[str] = "明细表（公允价值模式）H3-2"
TEMPLATE_ID_H302_FAIR: Final[str] = "H32F"
SHEET_KEY_H302_FAIR: Final[str] = "h302fair-managed"
ROWS_TABLE_KEY_H302_FAIR: Final[str] = "investment_property_fair_detail_rows"

#: 按值取自 `useH3DetailFair.ts#L60` 的 `ITEM_ID`。🔴 HC-8 冻结键（G 循环消费）。
STORE_ITEM_ID_H302_FAIR: Final[str] = "H3-2-fair-rows"

#: 行身份：`df-${Math.random().toString(36).slice(2, 8)}` / `df-${Date.now()}`。
#: 与成本模式同族弱点（载入回填不稳定 + addRow 同毫秒可撞），已登记不在本文件修。
ROW_IDENTITY_STORE_KEY_H302_FAIR: Final[str] = "rowId"

HEADER_TOP_ROW_H302_FAIR: Final[int] = 9
HEADER_GROUP_ROW_H302_FAIR: Final[int] = 10
HEADER_LEAF_ROW_H302_FAIR: Final[int] = 11
#: 🔴 比成本模式早一行（成本 R13 / 公允 R12）—— 照抄会让 merge 越界写进表头。
FIRST_DATA_ROW_H302_FAIR: Final[int] = 12
LAST_DATA_ROW_H302_FAIR: Final[int] = 26
FOOTER_ROW_H302_FAIR: Final[int] = 27
FOOTER_MARKER_H302_FAIR: Final[str] = "合计"
EFFECTIVE_COLUMNS_H302_FAIR: Final[int] = 27
UUID_COL_H302_FAIR: Final[str] = "AB"

UNMANAGED_REGIONS_H302_FAIR: Final[tuple[dict[str, object], ...]] = (
    {
        "first_row": 28,
        "last_row": 32,
        "kind": "category_subtotal_block",
        "note": (
            "A28='其中：'；R29-R32 为 "
            "=SUMPRODUCT(($A$12:$A$26=$A29)*(C$12:C$26)) 形态的按类别小计，"
            "行标签取 =底稿目录!A9..A12。不受管、不比对、不覆盖。"
        ),
    },
)

#: 🔴 模板真实缺陷登记（走覆盖层，**不改** `backend/wp_templates/` 字节）。
TEMPLATE_DEFECTS_H302_FAIR: Final[tuple[dict[str, Any], ...]] = (
    {
        "defect_id": "H3F-TPL-1",
        "cells": "R13:R26",
        "kind": "missing_formula",
        "expected": "=P{r}+Q{r}",
        "measured": (
            "仅 R12 有 `=P12+Q12`；R13-R26 共 14 行为空（无公式）。"
            "对照组：H7 公允价值模式同位列 S 满格 25/25 有 `=Q+R`。"
        ),
        "consequence": (
            "第 2 行起填 P（期初累计公允变动）与 Q（本年变动）后 R（期末）不自动算 ⇒ "
            "未审期末累计公允变动漏算。审定侧 U/V/W 满格有公式，于是同一张表里"
            "审定段算得出期末、未审段算不出（模板内部自相矛盾）。"
        ),
        "disposition": (
            "走覆盖层补公式，不改模板字节（同 F2-26!J9 / F5-7!G31 两例）。"
            "R 本身无前端对端 ⇒ 同时判 template-only，回写不碰它。"
        ),
    },
)

#: 🔴 模板有列但 HTML 无对端 ⇒ 不进 `field_specs`。
#: **原值整块 C..O 全部在列**：前端 `fairValueBegin/End` 是含公允变动的总额，
#: 不是原值 ⇒ 映过去会让 `X=L+U` 把变动重复计一次（见 docstring）。
TEMPLATE_ONLY_COLUMNS_H302_FAIR: Final[tuple[tuple[str, str], ...]] = (
    ("C", "期初余额"),
    ("D", "本年增加"),
    ("E", "增加方式"),
    ("F", "本年减少"),
    ("G", "减少方式"),
    ("H", "期末余额"),
    ("I", "期初调整"),
    ("J", "本期增加"),
    ("K", "本期减少"),
    ("L", "期初余额"),
    ("M", "本年增加"),
    ("N", "本年减少"),
    ("O", "期末余额"),
    ("P", "期初余额"),
    ("R", "期末余额"),
    ("S", "期初调整"),
    ("T", "本期变动调整"),
    ("U", "期初余额"),
    ("W", "期末余额"),
    ("X", "期初净值"),
    ("Z", "是否有权属证明"),
)

#: HTML 有字段但无模板对端（或语义不可映）⇒ store-only。
STORE_ONLY_FIELDS_H302_FAIR: Final[tuple[str, ...]] = (
    "seq",
    "location",
    "area",
    "acquireDate",
    "changeDate",
    "voucherNo",
    "counterAccount",
    # 🔴 含公允变动的公允价值总额，**不是**模板的「原值」（见 docstring）
    "fairValueBegin",
    "fairValueEnd",
    # 1 格对 2 字段 + 混装双向（与成本模式同族，见 DECLARED_COVERAGE_GAPS）
    "fairIncrease",
    "fairDecrease",
    "transferIn",
    "transferOut",
    "changeType",
    # 四段 ↔ 四分正交：未审/AJE/RJE 三档无模板对端
    "fairUnadj",
    "fairAje",
    "fairRje",
    "fvChangeUnadj",
    "fvChangeAje",
    "fvChangeRje",
    # 模板本 sheet 无「公允价值来源 / 评估依据」列（那两项在公允价值复核表H3-8）
    "fairValueSource",
    "appraisalBasis",
    # 语义 ≠ Z「是否有权属证明」
    "ownershipRestricted",
    "remark",
)

DERIVED_TOTAL_KEYS_H302_FAIR: Final[tuple[str, ...]] = (
    "H3-2-fair-begin-total",
    "H3-2-fair-increase-total",
    "H3-2-fair-decrease-total",
)

DECLARED_COVERAGE_GAPS_H302_FAIR: Final[tuple[dict[str, Any], ...]] = (
    {
        "gap_id": "H3F-GAP-1",
        "title": "前端公允价值口径（含变动的总额）与模板「原值 + 公允价值变动」两块拆分不同源",
        "template_columns": ["C", "D", "F", "H", "I", "J", "K", "L", "M", "N", "O"],
        "store_fields": [
            "fairValueBegin", "fairValueEnd",
            "fairIncrease", "fairDecrease", "transferIn", "transferOut",
        ],
        "why_not_mapped": (
            "calcFairEndBalance(begin, inc, dec, transfer, change) = "
            "begin + inc - dec + transfer + change —— 前端把本年公允变动加进了"
            "「期末公允价值」，即 fairValueBegin/End 是**含累计变动的公允价值总额**。"
            "模板把「原值 C..O」与「公允价值变动 P..W」分成两块，净值才是两者之和"
            "（X=L+U / Y=O+W）。把总额映进原值列会让 X 把公允变动**重复计一次**。"
        ),
        "what_still_syncs": (
            "Q ↔ fairValueChange（未审本年变动）、V ↔ fvChangeAudited（审定本年变动）、"
            "Y ↔ fairAudited（审定期末公允价值总额）。"
        ),
        "stop_and_report": (
            "要把前端总额口径拆回「原值 + 累计公允变动」两个独立字段，属前端模型变更 + "
            "存量数据迁移（且拆分基准年的累计变动无从追溯）⇒ 属审计域与数据治理裁决。"
        ),
        "owner": "审计业务方 / spec h3-h5-h7-variant-axis-and-dynamic-column-paradigm 后续任务",
    },
    {
        "gap_id": "H3F-GAP-2",
        "title": "模板四段（按作用位置）与前端四分（按调整来源）正交",
        "template_columns": ["S", "T", "U", "W"],
        "store_fields": [
            "fairUnadj", "fairAje", "fairRje",
            "fvChangeUnadj", "fvChangeAje", "fvChangeRje",
        ],
        "why_not_mapped": (
            "同成本模式 H3C-GAP-1：模板按作用位置分段（期初调整 / 本期变动调整），"
            "前端按来源分档（AJE / RJE）。`T 本期变动调整` 是**一列**对 "
            "fvChangeAje + fvChangeRje **两字段** ⇒ 映任一档都会吞掉另一档。"
        ),
        "what_still_syncs": "V（审定本年变动，=Q+T）↔ fvChangeAudited。",
        "stop_and_report": "AJE/RJE 的摊分属审计域裁决。",
        "owner": "审计业务方",
    },
    {
        "gap_id": "H3F-GAP-3",
        "title": "`E 增加方式` / `G 减少方式` 两列对一个混装双向的字段",
        "template_columns": ["E", "G"],
        "store_fields": ["changeType"],
        "why_not_mapped": (
            "FAIR_CHANGE_TYPE_OPTIONS 混装双向（购入 / 自建完工转入 / 自用转投资 / "
            "在建转投资 / 处置 / 转为自用 / 转出 / 公允价值变动），与成本模式同族。"
        ),
        "stop_and_report": "拆成 increaseType / decreaseType 属前端模型变更。",
        "owner": "spec h3-h5-h7-variant-axis-and-dynamic-column-paradigm 后续任务",
    },
    {
        "gap_id": "H3F-GAP-4",
        "title": "`Z 是否有权属证明` 与 `ownershipRestricted`「是否权属受限」不是同一事实",
        "template_columns": ["Z"],
        "store_fields": ["ownershipRestricted"],
        "why_not_mapped": "同成本模式 H3C-GAP-4（权属核对另有 产权核对表H3-12）。",
        "stop_and_report": "Z 的数据源应取 H3-12。",
        "owner": "spec h3-h5-h7-variant-axis-and-dynamic-column-paradigm 后续任务",
    },
)

#: 6 个受管字段。
FIELD_SPECS_H302_FAIR: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("asset_type", "A", "editable", "text", "assetType", "投资性房地产类别", ""),
    ("asset_name", "B", "editable", "text", "assetName", "投资性房地产名称", ""),
    ("fv_change_current", "Q", "editable", "amount", "fairValueChange", "本年变动", "P10"),
    # 🔴 V 不是 W：前端 fvChangeUnadj 默认取 change（**本年**变动）⇒ 对审定「本年变动」
    ("fv_change_audited", "V", "formula", "amount", "fvChangeAudited", "本年变动", "U10"),
    # Y 期末净值 = O + W = 审定后的期末公允价值总额 ↔ fairAudited
    ("fair_audited", "Y", "formula", "amount", "fairAudited", "期末净值", ""),
    ("mortgaged", "AA", "editable", "text", "mortgaged", "是否抵押受限", ""),
)

#: 🔴 只登记进了 `field_specs` 的公式列。template-only 的公式列
#:    （H/L/M/N/O · R · U/W · X）由 Excel 自行重算 —— 其中 `R` 本身缺 14 行公式
#:    （见 `TEMPLATE_DEFECTS_H302_FAIR`）。
FORMULA_TEMPLATES_H302_FAIR: Final[dict[str, str]] = {
    "V": "=Q{r}+T{r}",
    "Y": "=O{r}+W{r}",
}

SPEC_H302_FAIR: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_H302_FAIR,
    sheet_key=SHEET_KEY_H302_FAIR,
    table_key=ROWS_TABLE_KEY_H302_FAIR,
    template_id=TEMPLATE_ID_H302_FAIR,
    table_name=f"GT_{TEMPLATE_ID_H302_FAIR}_ROWS",
    uuid_col=UUID_COL_H302_FAIR,
    first_data_row=FIRST_DATA_ROW_H302_FAIR,
    last_data_row=LAST_DATA_ROW_H302_FAIR,
    footer_row=FOOTER_ROW_H302_FAIR,
    header_group_row=HEADER_TOP_ROW_H302_FAIR,
    header_leaf_row=HEADER_LEAF_ROW_H302_FAIR,
    store_item_id=STORE_ITEM_ID_H302_FAIR,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_H302_FAIR,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_H302_FAIR,
    formula_columns=tuple(FORMULA_TEMPLATES_H302_FAIR),
    formula_templates=FORMULA_TEMPLATES_H302_FAIR,
    footer_marker=FOOTER_MARKER_H302_FAIR,
    error_label="H3-2（公允价值模式）投资性房地产明细表",
)
