# -*- coding: utf-8 -*-
"""G9-2「其他非流动金融资产明细表」—— sheet 层薄声明（**三区三段**）。

spec: `g-cycle-single-region-detail-lanes` · Task 8 / C-5
　　　设计依据 `evidence/task8-template-design-logic.md`（模板编制思路）

═══ 几何（openpyxl 逐格实测，禁推演）═══

`明细表G9-2`：`max_row=47` / `max_column=28`（A..AB）/ 20 个合并区 / **0 个 definedName**。

* **两级**表头 **R9（组）/ R10（叶子）** —— 合并区逐字：
  `A9:A10` 类别 · `B9:B10` 投资项目 · `C9:E9` 期初余额 · `F9:G9` 期初账项调整 ·
  `H9:J9` 期初审定数 · `K9:K10` 期初重分类数 · `L9:L10` 期初报表数 ·
  `M9:O9` 本期变动（借方发生填正数）· `P9:R9` 期末余额 · `S9:T9` 账项调整 ·
  `U9:W9` 期末审定数 · `X9:X10` 期末重分类数 · `Y9:Y10` 期末报表数 ·
  `Z9:Z10` 期末应收利息 · `AA9:AA10` 变现是否存在限制 · `AB9:AB10` 发函情况
* **三个受管区**（区之间夹着小计行，区标题行不受管）：
  | 区 | 标题行（不受管） | 数据区 | 小计行（不受管） |
  |---|---|---|---|
  | 区① `main` | R11 `其他非流动金融资产` | **R12-16** | R17 |
  | 区② `mandatory_fvtpl` | R18 `划分为以公允价值计量且其变动计入当期损益的金融资产` | **R19-23** | R24 |
  | 区③ `designated_fvtpl` | R25 `指定为以公允价值计量且其变动计入当期损益的金融资产` | **R26-28** | R29 |
* 合计 **R30** `=SUM(C17,C24,C29)`（**枚举相加**，非 SUM 区间）—— 三区小计相加
* 公式列 **12 个**（三区逐行同型，实测 13 行 ×12 = 156 个公式格）：
  `E=C+D` `H=C+F` `I=D+G` `J=H+I` `L=E+K` `P=C+M` `Q=D+N` `R=P+Q` `U=P+S` `V=Q+T` `W=U+V` `Y=R+X`
  🔴 `P=C+M` / `Q=D+N` 走**未审线**（期初未审 + 本期变动），**不是**从审定数推。
  🔴 `O`（计入投资收益的股息）是损益项，**不参与**任何余额公式。
* 🔴 **无 `T` 跨表列** —— 与几何近同构的 `明细表G1-2` 区① 多一个引 `公允价值测试表G1-6` 的 T 列，
  两条**不得共用** `formula_columns`（P6 断言两者不等）。

═══ 三段共用一个 store 键（引擎 `row_section_field` 过滤）═══

前端把三区的行存在**同一个** `G9-detail-rows` 数组里、用 `section` 字段标记区归属
（`useG9Detail.G9_SECTIONS`）。平台既有多区范式（`phase5_d3_04_analysis` 双区）是
「一区一个 `store_item_id`」—— 那要求前端拆键，而 `G9-detail-rows` 已有真库载荷（605 B）、
被 8 个跨表消费方读取、且是 BP-10 登记的键。
⇒ 改为在引擎声明 `row_section_field="section"` + 各段 `row_section_value`，
`iter_store_rows` 按它过滤、`merge_projection_into_store_rows` 给新增行补它（成对）。

═══ 字段键逐字取自前端行接口 ═══

`useG9Detail.G9DetailRow`（28 字段，与模板列序 A..AB 逐列对应）。
`rowId` 是行身份（`generated_prefixed_opaque_string`，`genId()` 带随机后缀）、
`seq` 是显示序号 —— 两者都**不是**受管列。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G902_R1",
    "SPEC_G902_R2",
    "SPEC_G902_R3",
    "ALL_SPECS_G902",
    "MANAGED_SHEET_G902",
    "STORE_ITEM_ID_G902",
    "FORMULA_TEMPLATES_G902",
    "FORMULA_COLUMNS_G902",
    "SECTION_TITLE_ROWS_G902",
    "SUBTOTAL_ROWS_G902",
    "GRAND_TOTAL_ROW_G902",
]

MANAGED_SHEET_G902: Final[str] = "明细表G9-2"
TEMPLATE_ID_G902: Final[str] = "G92"
#: 🔴 单一共享 `sheet_key`（照 `phase5_d3_04_analysis` 的先例：契约层 `managed_sheet` 映射到
#: 两个不同 sheet_key 会在装配时产生「同 excel_name 两个 sheet 条目」）。
SHEET_KEY_G902: Final[str] = "g902-managed"

#: 🔴 按值取自 `useG9Detail.ts` 的 `ITEM_ID_ROWS`，**不按 sheet 号推演**。
STORE_ITEM_ID_G902: Final[str] = "G9-detail-rows"
ROW_IDENTITY_STORE_KEY_G902: Final[str] = "rowId"
#: 行的区归属字段（前端 `G9DetailRow.section`）—— 引擎据此把同一数组的行分到三个受管区。
ROW_SECTION_FIELD_G902: Final[str] = "section"

HEADER_GROUP_ROW_G902: Final[int] = 9
HEADER_LEAF_ROW_G902: Final[int] = 10

#: 区标题行（**不受管**：整行只有 A 列有分类文本、无公式）
SECTION_TITLE_ROWS_G902: Final[tuple[int, int, int]] = (11, 18, 25)
#: 小计行（**不受管**：逐列 `=SUM(x{first}:x{last})`）
SUBTOTAL_ROWS_G902: Final[tuple[int, int, int]] = (17, 24, 29)
#: 合计行（**不受管**：`=SUM(C17,C24,C29)` 枚举相加）
GRAND_TOTAL_ROW_G902: Final[int] = 30

FOOTER_MARKER_G902: Final[str] = "小计"


#: 12 个公式列（逐格实测；三区逐行同型）。🔴 **无 `T`** —— 见模块 docstring 的 G1 对照。
FORMULA_COLUMNS_G902: Final[tuple[str, ...]] = (
    "E", "H", "I", "J", "L", "P", "Q", "R", "U", "V", "W", "Y",
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R12（区①首行）。
FORMULA_TEMPLATES_G902: Final[dict[str, str]] = {
    "E": "=C{r}+D{r}",        # 期初公允价值 = 成本 + 累计公允价值变动
    "H": "=C{r}+F{r}",        # 期初审定成本
    "I": "=D{r}+G{r}",        # 期初审定累计公允价值变动
    "J": "=H{r}+I{r}",        # 期初审定公允价值（三分量恒等式）
    "L": "=E{r}+K{r}",        # 期初报表数
    "P": "=C{r}+M{r}",        # 🔴 期末成本（未审线：期初未审 + 本期）
    "Q": "=D{r}+N{r}",        # 🔴 期末累计公允价值变动（未审线）
    "R": "=P{r}+Q{r}",        # 期末公允价值（三分量恒等式）
    "U": "=P{r}+S{r}",        # 期末审定成本
    "V": "=Q{r}+T{r}",        # 期末审定累计公允价值变动
    "W": "=U{r}+V{r}",        # 期末审定公允价值（三分量恒等式）
    "Y": "=R{r}+X{r}",        # 期末报表数
}

#: 28 个受管字段（7 元组 `(column_key, column, mode, value_type, json_key, header_text, group_header_cell)`）。
#:
#: 顺序即 Excel 列序 A→AB；`header_text` 逐字取模板（**两级表头取叶子行 R10**，跨两行合并的
#: 单列取 R9）；`json_key` 逐字取 `useG9Detail.G9DetailRow`；`group_header_cell` 指向该列所属
#: 一级分组的合并区起始格（跨两行的单列为 `""`）。
FIELD_SPECS_G902: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("category", "A", "editable", "text", "category", "类别", ""),
    (
        "invest_target", "B", "editable", "text", "investTarget",
        "投资项目【按明细项目列示，如证券名称或被投资单位名称】", "",
    ),
    # ── C9:E9 期初余额（三分量）────────────────────────────────────────
    ("opening_cost", "C", "editable", "amount", "openingCost", "成本", "C9"),
    ("opening_cumulative_fv", "D", "editable", "amount", "openingCumulativeFv", "累计公允价值变动", "C9"),
    ("opening_fair_value", "E", "formula", "amount", "openingFairValue", "公允价值", "C9"),
    # ── F9:G9 期初账项调整（二分量，无独立公允价值列）──────────────────
    ("opening_adj_cost", "F", "editable", "amount", "openingAdjCost", "成本", "F9"),
    ("opening_adj_fv_change", "G", "editable", "amount", "openingAdjFvChange", "公允价值变动", "F9"),
    # ── H9:J9 期初审定数（三分量）──────────────────────────────────────
    ("opening_audited_cost", "H", "formula", "amount", "openingAuditedCost", "成本", "H9"),
    (
        "opening_audited_cumulative_fv", "I", "formula", "amount",
        "openingAuditedCumulativeFv", "累计公允价值变动", "H9",
    ),
    (
        "opening_audited_fair_value", "J", "formula", "amount",
        "openingAuditedFairValue", "公允价值", "H9",
    ),
    ("opening_reclass", "K", "editable", "amount", "openingReclass", "期初重分类数", ""),
    ("opening_reported", "L", "formula", "amount", "openingReported", "期初报表数", ""),
    # ── M9:O9 本期变动（借方发生填正数）────────────────────────────────
    ("period_cost", "M", "editable", "amount", "periodCost", "成本", "M9"),
    ("period_fv_change", "N", "editable", "amount", "periodFvChange", "本期公允价值变动", "M9"),
    (
        "period_dividend_income", "O", "editable", "amount",
        "periodDividendIncome", "计入投资收益的股息", "M9",
    ),
    # ── P9:R9 期末余额（三分量，未审线）───────────────────────────────
    ("closing_cost", "P", "formula", "amount", "closingCost", "成本", "P9"),
    ("closing_cumulative_fv", "Q", "formula", "amount", "closingCumulativeFv", "累计公允价值变动", "P9"),
    ("closing_fair_value", "R", "formula", "amount", "closingFairValue", "公允价值", "P9"),
    # ── S9:T9 账项调整（二分量）────────────────────────────────────────
    ("closing_adj_cost", "S", "editable", "amount", "closingAdjCost", "成本", "S9"),
    ("closing_adj_fv_change", "T", "editable", "amount", "closingAdjFvChange", "公允价值变动", "S9"),
    # ── U9:W9 期末审定数（三分量）──────────────────────────────────────
    ("closing_audited_cost", "U", "formula", "amount", "closingAuditedCost", "成本", "U9"),
    (
        "closing_audited_cumulative_fv", "V", "formula", "amount",
        "closingAuditedCumulativeFv", "累计公允价值变动", "U9",
    ),
    (
        "closing_audited_fair_value", "W", "formula", "amount",
        "closingAuditedFairValue", "公允价值", "U9",
    ),
    ("closing_reclass", "X", "editable", "amount", "closingReclass", "期末重分类数", ""),
    ("closing_reported", "Y", "formula", "amount", "closingReported", "期末报表数", ""),
    ("closing_interest_receivable", "Z", "editable", "amount", "closingInterestReceivable", "期末应收利息", ""),
    ("realization_restricted", "AA", "editable", "text", "realizationRestricted", "变现是否存在限制", ""),
    ("confirmation_status", "AB", "editable", "text", "confirmationStatus", "发函情况", ""),
)


def _section_spec(
    *,
    table_key: str,
    template_suffix: str,
    uuid_col: str,
    first_data_row: int,
    last_data_row: int,
    footer_row: int,
    section_value: str,
    error_label: str,
) -> RowTableSheetSpec:
    """三区共用的声明工厂（照 `phase5_d3_04_analysis._base_spec` 的先例）。

    三区**只在**行号区间、`uuid_col`、`table_key`、`template_id` 后缀、
    `row_section_value` 上不同；表头 / 字段集 / 公式列 / store 键完全相同 —— 抄三份必漂移。

    🔴 `template_id` 必须**逐区不同**（`G92R1/R2/R3`）：instrumentation 的 definedName
    是按它命名的（`GT_MANAGED_REGION_{template_id}` / `GT_FOOTER_ANCHOR_{template_id}`
    / `GT_UUID_COL_{template_id}`），三区共用一个 id 会让三个受管区争同一个 definedName。
    `build_instrumentation_payload_for_sheets` 对此有显式门（实测抛
    「多 sheet instrumentation 的 template_id 必须唯一，实得 ['G92','G92','G92']」）。
    先例是 `phase5_d3_04_analysis`（同一张 sheet 两区，`template_id=D34DEBIT/D34CREDIT`）。
    `sheet_key` 反过来必须**共享**（否则契约层产出两个同 `excel_name` 的 sheet 条目）。
    """
    return RowTableSheetSpec(
        managed_sheet=MANAGED_SHEET_G902,
        sheet_key=SHEET_KEY_G902,
        table_key=table_key,
        template_id=f"{TEMPLATE_ID_G902}{template_suffix}",
        table_name=f"GT_{TEMPLATE_ID_G902}_{table_key.upper()}",
        uuid_col=uuid_col,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        footer_row=footer_row,
        header_group_row=HEADER_GROUP_ROW_G902,
        header_leaf_row=HEADER_LEAF_ROW_G902,
        store_item_id=STORE_ITEM_ID_G902,
        empty_payload="[]",
        row_identity_key=ROW_IDENTITY_STORE_KEY_G902,
        store_kind=StoreKind.rows,
        field_specs=FIELD_SPECS_G902,
        formula_columns=FORMULA_COLUMNS_G902,
        formula_templates=FORMULA_TEMPLATES_G902,
        footer_marker=FOOTER_MARKER_G902,
        error_label=error_label,
        row_section_field=ROW_SECTION_FIELD_G902,
        row_section_value=section_value,
        # 🔴 幽灵行锚点必须指向 **B 列「投资项目」**（真正的业务名称），不是默认的 `[0]`。
        #    `[0]` 是 A 列「类别」—— 它是**枚举**（债务工具投资 / 权益工具投资 / …）且模板
        #    R12/R19 本就有预填值，用它当锚点会让「只填了类别的空行」通不过幽灵行防护、
        #    而「OO 侧只填了投资项目的真行」被当幽灵行剔除。
        #    与 `phase5_row_table_sheet.ghost_row_anchor_index` 注释里的 D5 例外同型
        #    （D5 的 `[0]` 也是枚举 `category`，原实现同样改用 `[1]`）。
        #    判据：`test_merge_stamps_section_on_newly_inserted_rows` 实测踩到过 —— 新行只给
        #    `invest_target` 时被判幽灵行，`touched` 为空。
        ghost_row_anchor_index=1,
    )


#: 区① 其他非流动金融资产（模板区标题 R11）
SPEC_G902_R1: Final[RowTableSheetSpec] = _section_spec(
    table_key="g9_detail_rows_r1",
    template_suffix="R1",
    uuid_col="AC",
    first_data_row=12,
    last_data_row=16,
    footer_row=17,
    section_value="main",
    error_label="G9-2 其他非流动金融资产明细表（其他非流动金融资产）",
)

#: 区② 划分为以公允价值计量且其变动计入当期损益的金融资产（模板区标题 R18；**强制** FVTPL）
SPEC_G902_R2: Final[RowTableSheetSpec] = _section_spec(
    table_key="g9_detail_rows_r2",
    template_suffix="R2",
    uuid_col="AD",
    first_data_row=19,
    last_data_row=23,
    footer_row=24,
    section_value="mandatory_fvtpl",
    error_label="G9-2 其他非流动金融资产明细表（划分为FVTPL）",
)

#: 区③ 指定为以公允价值计量且其变动计入当期损益的金融资产（模板区标题 R25；**指定** FVTPL）
SPEC_G902_R3: Final[RowTableSheetSpec] = _section_spec(
    table_key="g9_detail_rows_r3",
    template_suffix="R3",
    uuid_col="AE",
    first_data_row=26,
    last_data_row=28,
    footer_row=29,
    section_value="designated_fvtpl",
    error_label="G9-2 其他非流动金融资产明细表（指定为FVTPL）",
)

ALL_SPECS_G902: Final[tuple[RowTableSheetSpec, ...]] = (
    SPEC_G902_R1,
    SPEC_G902_R2,
    SPEC_G902_R3,
)
