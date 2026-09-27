"""H7-2（**成本模式**）「生产性生物资产、累计折旧及减值准备明细表」—— sheet 层薄声明。

spec: `h3-h5-h7-variant-axis-and-dynamic-column-paradigm`

H7 是变体轴第二条（H3 是第一条）：成本模式 / 公允价值模式两张并列明细表，
各有独立持久化键（`H7-2-cost-rows` / `H7-2-fair-rows`）⇒ 两张都进受管面，必须同批交付。

═══ 🔴 映射率 5/51（10%），全 H 最低 —— 原因是前端行模型只有 11 个字段 ═══

`H7TabDetailCost.vue` 里**内联**的 `DetailRow`（不是 composable，HD-1 的
`per_tab_self_persisting` 载体族）：

    rowId · assetName · assetType · quantity · location · matureDate
    costBegin · costIncrease · costDecrease · accDep · impairment · isSubtotal?

11 个业务字段对模板 51 列。能对上的只有 **A 类别 / C 名称 / D 原值期初 /
E 本期增加金额 / G 本期减少金额** 五格 —— 那正是该 Tab「增减转换」段里用户手敲的全部格。

`useH7DetailCost.ts` **不是载体**：它只有 32 行、只导出 `getNum` / `getString`
两个读取器，没有行模型也没有 store 键（HD-1 载体族判定必须按值取证，不能按文件名推演）。

═══ 几何（openpyxl 逐格实测）═══

册 `H/H7 生产性生物资产.xlsx`（225,641 B）· **26 sheets（全 H 第二多）** ·
本 sheet `有效内容列 51（A..AY）`。

* **四级**表头 R9 / R10 / R11 / R12（与 H5 逐列同构，只差尾部布尔列数量）
* 数据区 **R13-R36（24 行）**
* footer **R37**，`A37='合计'`，**全列 SUM**
* 数据行公式列 **19 个**（映射侧 **0 个** —— 一个公式列都映不上，见下）
* UUID 列 **AZ** = 51 + 1
* footer 之后 R38-R43 是 `其中：` + 五行按类别 SUMPRODUCT 小计，
  行标签取 `=底稿目录!A9..A13`（与 H5 的字面量标签相反 ⇒ 两条不能共用判据）

═══ 结构与 H5-2 逐列同构（唯一差别在尾部）═══

* **原值 D..P**：未审 D-I（D 期初数 / E-F 增加金额·方式 / G-H 减少金额·方式 / I 期末数）
  · 期初调整 J · 账项调整 K-L · 审定 M-P
* **累计折旧 Q..AE**：未审 Q-V（Q 期初 / R-S 本期计提·其他增加 / T-U 处置·其他减少 /
  V 期末）· 期初调整 W · 账项调整 X-AA · 审定 AB-AE
* **减值准备 AF..AT**：与折旧块逐列同构
* 净值四列 AU/AV/AW/AX（`=D-Q-AF` / `=M-AB-AQ` / `=I-V-AK` / `=P-AE-AT`）
* 尾部**只有一个**布尔列 `AY 是否提足折旧`（H5 有四个：提足折耗/闲置/权属/抵押）

═══ 🔴 为什么连 `I 原值期末数` 都映不上（与 H5 的关键差别）═══

H5 的行模型有 `originalCostEnd` 字段，算式与模板 `I` 逐项相等 ⇒ 可映。
H7 **没有** `costEnd` 字段：Tab 模板里「期末原值」列是
`class-name="auto-calc-col"` 的**展示期计算**（渲染时现算，不落库）。
⇒ `I` 无 store 对端，判 template-only。本 sheet 因此 `FORMULA_TEMPLATES` 为**空**。

═══ 🔴 `accDep` / `impairment` 为什么不能映（单值 vs 期初·发生·期末三段）═══

Tab 的「计价」段列标签逐字是：`期末原值`（auto-calc）· `累计折旧` · `减值准备` ·
`净值`（auto-calc）—— 也就是说 `accDep` / `impairment` 是**用作期末余额**的单值
（净值 = 期末原值 − 累计折旧 − 减值准备）。

模板把每个备抵科目拆成 **期初数 / 本期增加（计提·其他）/ 本期减少（处置·其他）/ 期末数**，
且**期末数是公式**（`V=SUM(Q:S)-SUM(T:U)` / `AK=SUM(AF:AH)-SUM(AI:AJ)`）。

把单值映到期末数（V / AK）会被 Excel 按自己的 Q..U / AF..AJ **重算覆盖**
（那些格前端没有对端、恒空 ⇒ 重算结果为 0），回写时把 0 灌回 `accDep` —— **静默清零**。
映到期初数（Q / AF）则是语义错位（把期末余额写进期初格）。
⇒ 两块整体判 template-only，两字段判 store-only，缺口带停下报告点。

═══ 覆盖闭合 ═══

**5 映射 + 46 template-only == 51 有效列**，并集连续 A..AY 无缺口。
"""
from __future__ import annotations

from typing import Any, Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_H702_COST",
    "MANAGED_SHEET_H702_COST",
    "SHEET_KEY_H702_COST",
    "STORE_ITEM_ID_H702_COST",
    "ROW_IDENTITY_STORE_KEY_H702_COST",
    "FORMULA_TEMPLATES_H702_COST",
    "STORE_ONLY_FIELDS_H702_COST",
    "TEMPLATE_ONLY_COLUMNS_H702_COST",
    "DECLARED_COVERAGE_GAPS_H702_COST",
    "DERIVED_TOTAL_KEYS_H702_COST",
    "UNMANAGED_REGIONS_H702_COST",
    "EFFECTIVE_COLUMNS_H702_COST",
    "UUID_COL_H702_COST",
]

MANAGED_SHEET_H702_COST: Final[str] = "明细表（成本模式）H7-2"
TEMPLATE_ID_H702_COST: Final[str] = "H72C"
SHEET_KEY_H702_COST: Final[str] = "h702cost-managed"
ROWS_TABLE_KEY_H702_COST: Final[str] = "biological_assets_cost_detail_rows"

#: 按值取自 `H7TabDetailCost.vue#L257/#L275`（键**内联在 Tab 里**，不在 composable ——
#: HD-1 的 `per_tab_self_persisting` 载体族）。
STORE_ITEM_ID_H702_COST: Final[str] = "H7-2-cost-rows"

#: 行身份：`rowId`（Tab 内联 `DetailRow` 的字段）。
ROW_IDENTITY_STORE_KEY_H702_COST: Final[str] = "rowId"

HEADER_TOP_ROW_H702_COST: Final[int] = 9
HEADER_GROUP_ROW_H702_COST: Final[int] = 10
HEADER_SUB_ROW_H702_COST: Final[int] = 11
HEADER_LEAF_ROW_H702_COST: Final[int] = 12
FIRST_DATA_ROW_H702_COST: Final[int] = 13
LAST_DATA_ROW_H702_COST: Final[int] = 36
FOOTER_ROW_H702_COST: Final[int] = 37
FOOTER_MARKER_H702_COST: Final[str] = "合计"
EFFECTIVE_COLUMNS_H702_COST: Final[int] = 51
UUID_COL_H702_COST: Final[str] = "AZ"

UNMANAGED_REGIONS_H702_COST: Final[tuple[dict[str, object], ...]] = (
    {
        "first_row": 38,
        "last_row": 43,
        "kind": "category_subtotal_block",
        "note": (
            "A38='其中：'；R39-R43 为 "
            "=SUMPRODUCT(($A$13:$A$36=$A39)*(D$13:D$36)) 形态的按类别小计，"
            "行标签取 =底稿目录!A9..A13（**五行**；H5 的同族区是字面量标签 ⇒ 判据不共用）。"
            "不受管、不比对、不覆盖。"
        ),
    },
)

#: 🔴 H7 的小计行**在 rows 里**（`DetailRow.isSubtotal?`）而不是 computed ——
#:    与 H5 的 `subtotalRow` computed 相反。合计行由模板 footer R37 承担，
#:    store 侧那条 isSubtotal 行**不得**被当数据行写进 R13-R36。
DERIVED_TOTAL_KEYS_H702_COST: Final[tuple[str, ...]] = (
    "H7-2-cost-total",
)

#: 🔴 模板有列但 HTML 无对端 ⇒ 不进 `field_specs`。**46 列**。
TEMPLATE_ONLY_COLUMNS_H702_COST: Final[tuple[tuple[str, str], ...]] = (
    ("B", "生产性生物资产编号"),
    ("F", "增加方式"),
    ("H", "减少方式"),
    ("I", "期末数"),
    ("J", "期初调整"),
    ("K", "本期增加"),
    ("L", "本期减少"),
    ("M", "期初数"),
    ("N", "本期增加"),
    ("O", "本期减少"),
    ("P", "期末数"),
    # ── 累计折旧整块（前端只有一个用作期末余额的 accDep 单值）────────────────
    ("Q", "期初数"),
    ("R", "本期计提"),
    ("S", "其他增加"),
    ("T", "处置"),
    ("U", "其他减少"),
    ("V", "期末数"),
    ("W", "期初调整"),
    ("X", "本期计提"),
    ("Y", "其他增加"),
    ("Z", "处置"),
    ("AA", "其他减少"),
    ("AB", "期初数"),
    ("AC", "本期增加"),
    ("AD", "本期减少"),
    ("AE", "期末数"),
    # ── 减值准备整块（同上，前端只有一个 impairment 单值）─────────────────────
    ("AF", "期初数"),
    ("AG", "本期计提"),
    ("AH", "其他增加"),
    ("AI", "处置"),
    ("AJ", "其他减少"),
    ("AK", "期末数"),
    ("AL", "期初调整"),
    ("AM", "本期计提"),
    ("AN", "其他增加"),
    ("AO", "处置"),
    ("AP", "其他减少"),
    ("AQ", "期初数"),
    ("AR", "本期增加"),
    ("AS", "本期减少"),
    ("AT", "期末数"),
    # ── 净值四列（前端「净值」是展示期 auto-calc，不落库）─────────────────────
    ("AU", "未审净值"),
    ("AV", "审定净值"),
    ("AW", "未审净值"),
    ("AX", "审定净值"),
    ("AY", "是否提足折旧"),
)

#: HTML 有字段但模板无列（或不可安全映）⇒ store-only。
STORE_ONLY_FIELDS_H702_COST: Final[tuple[str, ...]] = (
    # 模板本 sheet 无这三列（B 是资产编号，与数量/所在地/成熟日期都不是一回事）
    "quantity",
    "location",
    "matureDate",
    # 单值 vs 期初·发生·期末三段 ⇒ 映期末会被 Excel 重算清零、映期初是语义错位
    "accDep",
    "impairment",
    # 小计标记：合计行由模板 footer R37 承担，这条不得当数据行写入
    "isSubtotal",
)

DECLARED_COVERAGE_GAPS_H702_COST: Final[tuple[dict[str, Any], ...]] = (
    {
        "gap_id": "H7C-GAP-1",
        "title": "前端行模型只有 11 个字段，模板 51 列 —— 无审定口径、无增减方式、无期末原值",
        "template_columns": [
            "F", "H", "I", "J", "K", "L", "M", "N", "O", "P",
            "W", "X", "Y", "Z", "AA", "AB", "AC", "AD", "AE",
            "AL", "AM", "AN", "AO", "AP", "AQ", "AR", "AS", "AT",
            "AU", "AV", "AW", "AX", "AY",
        ],
        "store_fields": [],
        "why_not_mapped": (
            "`H7TabDetailCost.vue` 内联的 `DetailRow` 只有 11 个业务字段"
            "（assetName / assetType / quantity / location / matureDate / costBegin / "
            "costIncrease / costDecrease / accDep / impairment + rowId）。"
            "模板的增减**方式**两列、原值**期末数**、三个区块的期初调整/账项调整/审定数、"
            "净值四列、是否提足折旧 —— 前端一个字段都没有。"
            "🔴 `I 期末数` 特别说明：Tab 里「期末原值」列是 `class-name=\"auto-calc-col\"` 的"
            "**展示期计算**（渲染时现算，不落库）⇒ 无 store 对端。这也是本 sheet "
            "`FORMULA_TEMPLATES` 为**空**的原因（H5 有 `originalCostEnd` 字段所以能映 I）。"
        ),
        "stop_and_report": (
            "要接通这 33 列需要给 Tab 内联的行模型补约 20 个字段 + 改表格 UI，"
            "并先决定 H7 的审定数究竟在明细表逐资产列示还是只在 H7-1 审定表汇总"
            "（编制口径问题）⇒ 属前端模型扩张 + 审计域确认。"
        ),
        "owner": "审计业务方 / spec h3-h5-h7-variant-axis-and-dynamic-column-paradigm 后续任务",
    },
    {
        "gap_id": "H7C-GAP-2",
        "title": "`accDep` / `impairment` 是**单值期末余额**，模板是期初·发生·期末三段",
        "template_columns": [
            "Q", "R", "S", "T", "U", "V",
            "AF", "AG", "AH", "AI", "AJ", "AK",
        ],
        "store_fields": ["accDep", "impairment"],
        "why_not_mapped": (
            "Tab 的「计价」段列标签逐字是 `期末原值`(auto-calc) / `累计折旧` / `减值准备` / "
            "`净值`(auto-calc) ⇒ 两字段是**用作期末余额**的单值。模板把每个备抵科目拆成"
            "期初数 / 本期增加（计提·其他）/ 本期减少（处置·其他）/ 期末数，**且期末数是公式**"
            "（V=SUM(Q:S)-SUM(T:U) / AK=SUM(AF:AH)-SUM(AI:AJ)）。"
            "映到期末数会被 Excel 按自己的 Q..U / AF..AJ 重算覆盖（那些格恒空 ⇒ 结果 0），"
            "回写时把 0 灌回 accDep —— **静默清零**。映到期初数则是语义错位。"
        ),
        "stop_and_report": (
            "要接通需把单值拆成「期初 + 本期计提 + 本期减少」三个字段（并决定减少额落"
            "处置还是其他减少）⇒ 前端模型变更 + 审计口径裁决，与 H5-GAP-2 同族。"
        ),
        "owner": "审计业务方",
    },
)

#: 5 个受管字段 —— 该 Tab「增减转换」段里用户手敲的全部格。
FIELD_SPECS_H702_COST: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("asset_type", "A", "editable", "text", "assetType", "生产性生物资产类别", ""),
    ("asset_name", "C", "editable", "text", "assetName", "生产性生物资产名称", ""),
    ("cost_begin", "D", "editable", "amount", "costBegin", "期初数", "D10"),
    ("cost_increase", "E", "editable", "amount", "costIncrease", "金额", "E11"),
    ("cost_decrease", "G", "editable", "amount", "costDecrease", "金额", "G11"),
)

#: 🔴 **空** —— 本 sheet 的 19 个公式列一个都没进 `field_specs`（理由见 docstring 与
#:    H7C-GAP-1/2）。全部由 Excel 自行重算，回写不碰它们。
FORMULA_TEMPLATES_H702_COST: Final[dict[str, str]] = {}

SPEC_H702_COST: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_H702_COST,
    sheet_key=SHEET_KEY_H702_COST,
    table_key=ROWS_TABLE_KEY_H702_COST,
    template_id=TEMPLATE_ID_H702_COST,
    table_name=f"GT_{TEMPLATE_ID_H702_COST}_ROWS",
    uuid_col=UUID_COL_H702_COST,
    first_data_row=FIRST_DATA_ROW_H702_COST,
    last_data_row=LAST_DATA_ROW_H702_COST,
    footer_row=FOOTER_ROW_H702_COST,
    header_group_row=HEADER_TOP_ROW_H702_COST,
    header_leaf_row=HEADER_LEAF_ROW_H702_COST,
    store_item_id=STORE_ITEM_ID_H702_COST,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_H702_COST,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_H702_COST,
    formula_columns=tuple(FORMULA_TEMPLATES_H702_COST),
    formula_templates=FORMULA_TEMPLATES_H702_COST,
    footer_marker=FOOTER_MARKER_H702_COST,
    error_label="H7-2（成本模式）生产性生物资产明细表",
)
