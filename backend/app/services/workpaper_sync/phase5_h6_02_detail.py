"""H6-2「固定资产清理明细表」—— sheet 层薄声明（H 循环第二张接入，发布链首例 entry）。

spec: `h2-h6-h10-pilot-cross-reference-lanes`

═══ 为什么 H6 是 canary 之后的第一条 ═══

`h-cycle-sync-foundation-and-first-canary` 选 H9-2 作 canary 时把 H6 否掉的理由是
**真库零载荷**（`H6-2-rows` 在 `checklist_responses` 无行）——那条理由只影响「能否做
roundtrip 真实证」，不影响接线本身。反过来 H6 有两项全循环最优：

* 🔴 **TB 发布门最干净**，是 H 循环**发布链首例**：H6 的审定数经
  `H6TabAdjudication → useH6Adjudication.publishToTb` 走显式发布门（POST 科目 1606），
  H8/H9 两条**完全没有**发布门（`publishToTb` 全链路 0 处）。
* **裸 `IF(` 最少（12 格，全 H 最低）** ⇒ OO 加载崩溃面最小。

第三项也重要：**H6 的 HTML 字段与模板的四块调整模型天然同构**。H3/H5/H7 三条 lane 的
HTML 侧用 `costUnadj / costAje / costRje / costAudited` 命名，与模板的
「未审数 / 期初调整 / 账项调整 / 审定数」四块**不是同一套切分**，逐列映射需审计域裁决；
H6 的 `beginUnadjusted / beginAdjustment / ajeIncrease / beginAudited` 与模板逐块对齐
（前端注释自己写明「区块3: 余额变动（对齐 Excel H6-2 B–L）」）⇒ 无需裁决即可映射。

═══ 几何（openpyxl 逐格实测，禁推演）═══

册 `H/H6 固定资产清理.xlsx`（48,865 B）· 8 sheets · **无 `GT_Custom` hidden sheet**
（与 H9/H10 两册不同）· 本 sheet `max_row=36` / `max_column=25`，
**有效内容列 16（A..P）** —— `max_column=25` 是空列尾巴，不是内容。

* **两级**表头 **R9 / R10**（`header_rows = 10 - 9 + 1 = 2`）
* 数据区 **R11-R15**（5 行）
* footer **R16**，A16 = `'　合计'`（🔴 **前导全角空格 U+3000**，不是 `'合计'`），
  `B16..L16` 各为 `=SUM(x11:x15)`
* 公式列 **E / I / J / K / L**（逐行实测 R11-R15）：
  - `E{r} = SUM(B{r}:C{r})-D{r}`　未审期末
  - `I{r} = B{r}+F{r}`　审定期初
  - `J{r} = C{r}+G{r}`　审定本期增加
  - `K{r} = D{r}+H{r}`　审定本期减少
  - `L{r} = I{r}+J{r}-K{r}`　审定期末
    🔴 **资产口径（期初 + 增加 − 减少）**，与 H9-2 的负债口径 `=I-J+K` **相反**。
    抄 H9 的模板会让审定期末反号 —— 这是两表唯一形似而实异的地方。
* UUID 列 **Q** = 有效内容列（16）+ 1（HC-13）

表头合并实测：`A9:A10` / `F9:F10` / `M9:M10` / `N9:N10` / `O9:O10` / `P9:P10` 六列是
**纵向**合并（无横向分组 ⇒ `group_header_cell` 留空）；`B9:E9`（未审数）、`G9:H9`
（账项调整）、`I9:L9`（审定数）三处是**横向**分组。

═══ 字段键逐字取自前端 `_persist()` 落盘列表 ═══

`useH6Detail.ts` 的 `_persist()`（L531-570）是唯一权威。**模板列 ↔ store 字段**：

| 列 | 模板标题（叶子/纵合并取 R9） | store 字段 | mode |
|---|---|---|---|
| A | 项目 | `assetName` | editable |
| B | 期初数（未审数） | `beginUnadjusted` | editable |
| C | 本期增加（未审数） | `periodIncrease` | editable |
| D | 本期减少（未审数） | `periodDecrease` | editable |
| E | 期末数（未审数） | `endUnadjusted` | **formula** |
| F | 期初调整 | `beginAdjustment` | editable |
| G | 本期增加（账项调整） | `ajeIncrease` | editable |
| H | 本期减少（账项调整） | `ajeDecrease` | editable |
| I | 期初数（审定数） | `beginAudited` | **formula** |
| J | 本期增加（审定数） | `increaseAudited` | **formula** |
| K | 本期减少（审定数） | `decreaseAudited` | **formula** |
| L | 期末数（审定数） | `endAudited` | **formula** |
| M | 转入清理的原因 | `disposalReason` | editable |
| N | 转入清理的时间 | `startDate` | editable |
| O | 转入固定资产清理起始时间已超过1年的固定资产清理进展情况 | `overOneYearProgress` | editable |
| P | 备注 | `remarks` | editable |

🔴 **`increaseAudited` / `decreaseAudited` 不在 `_persist()` 里**（`beginAudited` /
`endAudited` 在）。即 J/K 两列的 json_key **不落库**，客户端 load 时由
`applyH62BalanceFormulas` 重算。这与 H9 的「公式列 json_key 不落库」同族，但 H6 是
**部分落库**（E/I/L 落、J/K 不落）⇒ 回写比对不得假设公式列一律不落库。

模板列全部有 store 字段 ⇒ `TEMPLATE_ONLY_COLUMNS` 为空（与 H9 的 U/V 两列不同）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_H602",
    "MANAGED_SHEET_H602",
    "SHEET_KEY_H602",
    "STORE_ITEM_ID_H602",
    "ROW_IDENTITY_STORE_KEY_H602",
    "FORMULA_TEMPLATES_H602",
    "CHINESE_ENUM_FIELDS_H602",
    "DERIVED_STORE_ONLY_FIELDS_H602",
    "STORE_ONLY_FIELDS_H602",
    "TEMPLATE_ONLY_COLUMNS_H602",
    "NON_PERSISTED_FORMULA_KEYS_H602",
    "DERIVED_TOTAL_KEYS_H602",
    "CROSS_ENTRY_CONSUMERS_H602",
    "EFFECTIVE_COLUMNS_H602",
    "UUID_COL_H602",
]

MANAGED_SHEET_H602: Final[str] = "明细表H6-2"
TEMPLATE_ID_H602: Final[str] = "H62"
SHEET_KEY_H602: Final[str] = "h602-managed"
ROWS_TABLE_KEY_H602: Final[str] = "asset_disposal_clearing_detail_rows"

#: 🔴 按值取自 `useH6Detail.ts#L119` 的 `ROWS_KEY`，**不按 sheet 号推演**。
#: HC-8 冻结键：被三处跨 entry 消费（见 `CROSS_ENTRY_CONSUMERS_H602`）⇒ 本轮不得改名。
STORE_ITEM_ID_H602: Final[str] = "H6-2-rows"

#: 行身份键与生成式（slice `row_identity_generator_form` 逐字）：
#: `` `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}` ``
#: ⇒ HC-7 族 A（时间戳 + 随机，非下标）⇒ 本表**不含身份改造**。
#: 同一行还有 `seq: raw.seq ?? idx + 1`，那是**展示序号不是身份**（slice 已登记该判据只取
#: `rowId:` 自己的值表达式）—— 不得因为 `seq` 是序数就判本表位置身份。
ROW_IDENTITY_STORE_KEY_H602: Final[str] = "rowId"

HEADER_GROUP_ROW_H602: Final[int] = 9
HEADER_LEAF_ROW_H602: Final[int] = 10
FIRST_DATA_ROW_H602: Final[int] = 11
LAST_DATA_ROW_H602: Final[int] = 15
FOOTER_ROW_H602: Final[int] = 16
#: 🔴 前导**全角空格 U+3000**，逐字取 A16。写成 `"合计"` 会让 footer 定位失配。
FOOTER_MARKER_H602: Final[str] = "\u3000合计"
EFFECTIVE_COLUMNS_H602: Final[int] = 16
UUID_COL_H602: Final[str] = "Q"

#: 模板有列但 HTML 无字段 ⇒ 本表**为空**（16 列全部有 store 字段）。
TEMPLATE_ONLY_COLUMNS_H602: Final[tuple[tuple[str, str], ...]] = ()

#: HTML 有字段但模板无列 ⇒ store-only，不映射任何格（merge 只动受管列，这些原样保留）。
#: 逐字取 `_persist()`；其中 4 对是**跨 entry 读别名**（同值双键，见 note）。
STORE_ONLY_FIELDS_H602: Final[tuple[str, ...]] = (
    "seq",
    "originalCost",
    "accumulatedDepreciation",
    "accDepreciation",          # 别名：兼容旧导入键（导出以规范名为准）
    "impairmentProvision",
    "netBookValue",
    "disposalIncome",
    "disposalExpenses",
    "taxAmount",
    "tax",                      # 别名
    "gainLoss",
    "netGainLoss",              # 别名
    "transferAccount",
    "completionDate",
    "status",
    "refH1Code",
    "h1Reference",              # 别名
    "refH10Code",
    "h10Reference",             # 别名
    "endAdjustment",
)

#: 🔴 派生 store-only：`endAdjustment` 由 `calcH62EndAdjustment(beginAdjustment,
#: ajeIncrease, ajeDecrease)` 算出（前端注释：「供 H6-1 期末账项列：期初调整+账项增加−账项减少」）。
#: 模板**无此列** ⇒ OO 侧无处可编辑；即便 store 里有值也不得回写成某一格。
DERIVED_STORE_ONLY_FIELDS_H602: Final[tuple[str, ...]] = ("endAdjustment",)

#: 🔴 HC-11：中文枚举域字段（值域是中文字面量，**不得**声明为 boolean）。
#: 逐字取 `H6DetailRow.status: '清理中' | '已完成' | '已结转'`。
#: 该字段是 store-only（模板无列）⇒ 登记它是为了让回写侧不把它当自由文本覆盖。
CHINESE_ENUM_FIELDS_H602: Final[dict[str, tuple[str, ...]]] = {
    "status": ("清理中", "已完成", "已结转"),
}

#: 🔴 公式列里 json_key **不落库**的两个（客户端 load 时 `applyH62BalanceFormulas` 重算）。
#: 回写比对必须排除它们 —— 否则会把「store 里本来就没有」误报成「回写丢字段」。
NON_PERSISTED_FORMULA_KEYS_H602: Final[tuple[str, ...]] = (
    "increaseAudited",
    "decreaseAudited",
)

#: 🔴 HC-6 派生合计副本：6 个独立 checklist 键，由 `_persist()` 与主表**同批**写出。
#: 它们是主表的合计投影，不参与 roundtrip 比对；重算责任方 = 前端 `subtotalRow` computed。
DERIVED_TOTAL_KEYS_H602: Final[tuple[str, ...]] = (
    "H6-2-subtotal-gain-loss",
    "H6-2-subtotal-net-book-value",
    "H6-2-subtotal-begin-unadjusted",
    "H6-2-subtotal-end-unadjusted",
    "H6-2-subtotal-begin-audited",
    "H6-2-subtotal-end-audited",
)

#: 🔴 HC-8 键名冻结的依据：`H6-2-rows` 的跨 entry 消费方（按值 grep 实测）。
CROSS_ENTRY_CONSUMERS_H602: Final[tuple[str, ...]] = (
    "h10RelatedH6Pull.ts",      # H10 侧拉 H6 清理净损益
    "h1SoeClearingH6Pull.ts",   # H1 国企附注拉清理明细
    "h6DisclosureModel.ts",     # H6 自身附注模型
)

#: 16 个受管字段（7 元组，第 7 位 `group_header_cell`）。
#: 顺序即 Excel 列序 A→P；`header_text` 逐字取模板（横向分组列取 R10 叶子，
#: 纵向合并列取 R9）；`json_key` 逐字取 `useH6Detail._persist()`。
FIELD_SPECS_H602: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("asset_name", "A", "editable", "text", "assetName", "项目", ""),
    ("begin_unadjusted", "B", "editable", "amount", "beginUnadjusted", "期初数", "B9"),
    ("period_increase", "C", "editable", "amount", "periodIncrease", "本期增加", "B9"),
    ("period_decrease", "D", "editable", "amount", "periodDecrease", "本期减少", "B9"),
    ("end_unadjusted", "E", "formula", "amount", "endUnadjusted", "期末数", "B9"),
    ("begin_adjustment", "F", "editable", "amount", "beginAdjustment", "期初调整", ""),
    ("aje_increase", "G", "editable", "amount", "ajeIncrease", "本期增加", "G9"),
    ("aje_decrease", "H", "editable", "amount", "ajeDecrease", "本期减少", "G9"),
    ("begin_audited", "I", "formula", "amount", "beginAudited", "期初数", "I9"),
    ("increase_audited", "J", "formula", "amount", "increaseAudited", "本期增加", "I9"),
    ("decrease_audited", "K", "formula", "amount", "decreaseAudited", "本期减少", "I9"),
    ("end_audited", "L", "formula", "amount", "endAudited", "期末数", "I9"),
    ("disposal_reason", "M", "editable", "text", "disposalReason", "转入清理的原因", ""),
    ("start_date", "N", "editable", "text", "startDate", "转入清理的时间", ""),
    (
        "over_one_year_progress",
        "O",
        "editable",
        "text",
        "overOneYearProgress",
        "转入固定资产清理起始时间已超过1年的固定资产清理进展情况",
        "",
    ),
    ("remarks", "P", "editable", "text", "remarks", "备注", ""),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R11-R15。
#: 🔴 `L` 是**资产口径**（期初 + 增加 − 减少）。H9-2 的同位列是 `=I-J+K`（负债口径），
#: 两者形似而实异 —— 直接复制 H9 会让 H6 审定期末反号。
FORMULA_TEMPLATES_H602: Final[dict[str, str]] = {
    "E": "=SUM(B{r}:C{r})-D{r}",
    "I": "=B{r}+F{r}",
    "J": "=C{r}+G{r}",
    "K": "=D{r}+H{r}",
    "L": "=I{r}+J{r}-K{r}",
}

SPEC_H602: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_H602,
    sheet_key=SHEET_KEY_H602,
    table_key=ROWS_TABLE_KEY_H602,
    template_id=TEMPLATE_ID_H602,
    table_name=f"GT_{TEMPLATE_ID_H602}_ROWS",
    uuid_col=UUID_COL_H602,
    first_data_row=FIRST_DATA_ROW_H602,
    last_data_row=LAST_DATA_ROW_H602,
    footer_row=FOOTER_ROW_H602,
    header_group_row=HEADER_GROUP_ROW_H602,
    header_leaf_row=HEADER_LEAF_ROW_H602,
    store_item_id=STORE_ITEM_ID_H602,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_H602,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_H602,
    formula_columns=("E", "I", "J", "K", "L"),
    formula_templates=FORMULA_TEMPLATES_H602,
    footer_marker=FOOTER_MARKER_H602,
    error_label="H6-2 固定资产清理明细表",
)
