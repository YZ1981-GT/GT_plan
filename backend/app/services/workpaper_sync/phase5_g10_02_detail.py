# -*- coding: utf-8 -*-
"""G10-2「交易性金融负债明细表」—— sheet 层薄声明（单区）。

spec: `g-cycle-single-region-detail-lanes` · Task 9 / C-7
　　　列模型依据 `evidence/task8-c6-remaining-eight-template-logic.md` §2

═══ 几何（openpyxl 逐格实测，禁推演）═══

`明细表G10-2`：`max_row=38` / `max_column=24` / **0 个 definedName**。

* **两级**表头 **R9（组）/ R10（叶子）** —— 合并区逐字：
  `A9:A10` 类别 · `B9:B10` 项目【按明细项目列示，如债券名称】 · `C9:E9` 期初余额 ·
  `H9:J9` 本期变动（增加"+"/减少"—"）· `K9:O9` 期末余额 · `P9:P10` 到期日 ·
  `Q9:Q10` 票面利率 · `R9:R10` 期末应付利息 · `S9:S10` 发行文件索引
  🔴 `F`（期初调整数）与 `G`（期初审定数）**只在 R10 有文本、R9 无合并区** ——
  负债侧的调整与审定都是单列，不像 G9 那样拆成本与公允价值变动两分量。
* **单个受管区** R11-R20（10 行），footer **R21** 合计（逐列 `=SUM(x11:x20)`，
  其中 `O21` 例外是 `=M21+N21`）。
* 有效内容列 **19**（A..S），`T`/`U`/`V`/`W`/`X` 全空 ⇒ UUID 列取 `T`。
* 公式列 **6 个**（逐格实测，R11-R20 同型）：
  `E=C+D` `G=E+F` `K=C+H` `L=D+I+J` `M=K+L` `O=M+N`

🔴 **`L = D+I+J` 含利息 J**：交易性金融负债的利息计入财务费用**同时增加负债账面价值**，
所以「计入财务费用的利息」必须进期末累计公允价值变动。改造前前端算 `D+I`（漏 J）。

🔴 **`K = C+H` 走未审线**（期初未审 + 本期变动），不从审定数 `G` 推 —— 同 G9 的
`P=C+M`。改造前前端有个走审定线的 legacy `closingBalance`（`=期初审定+变动−减少`），
口径与模板不符，已随 C-7 移除。

🔴 **本期变动是净额列**：表头逐字「增加"+"/减少"—"」⇒ 模板**没有**「本期减少」列。
改造前的自研 `currentDecrease` 已移除。

═══ 字段键逐字取自前端行接口 ═══

`useG10Detail.G10DetailRow`（19 字段，与模板列序 A..S 逐列对应）。
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
    "SPEC_G1002",
    "MANAGED_SHEET_G1002",
    "STORE_ITEM_ID_G1002",
    "FORMULA_TEMPLATES_G1002",
    "FORMULA_COLUMNS_G1002",
    "FIELD_SPECS_G1002",
    "FOOTER_ROW_G1002",
]

MANAGED_SHEET_G1002: Final[str] = "明细表G10-2"
TEMPLATE_ID_G1002: Final[str] = "G102"
SHEET_KEY_G1002: Final[str] = "g1002-managed"

#: 🔴 按值取自 `useG10Detail.ts` 的 `ITEM_ID_ROWS`，**不按 sheet 号推演**。
STORE_ITEM_ID_G1002: Final[str] = "G10-detail-rows"
ROW_IDENTITY_STORE_KEY_G1002: Final[str] = "rowId"

HEADER_GROUP_ROW_G1002: Final[int] = 9
HEADER_LEAF_ROW_G1002: Final[int] = 10
FIRST_DATA_ROW_G1002: Final[int] = 11
LAST_DATA_ROW_G1002: Final[int] = 20
#: footer 合计行（**不受管**）：逐列 `=SUM(x11:x20)`，`O21` 例外为 `=M21+N21`
FOOTER_ROW_G1002: Final[int] = 21
FOOTER_MARKER_G1002: Final[str] = "合计"

#: 6 个公式列（逐格实测；R11-R20 同型）
FORMULA_COLUMNS_G1002: Final[tuple[str, ...]] = ("E", "G", "K", "L", "M", "O")

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R11。
FORMULA_TEMPLATES_G1002: Final[dict[str, str]] = {
    "E": "=C{r}+D{r}",              # 期初公允价值 = 初始确认金额 + 累计公允价值变动
    "G": "=E{r}+F{r}",              # 期初审定数（🔴 调整是单列 F，不拆分量）
    "K": "=C{r}+H{r}",              # 🔴 期末初始确认金额（未审线）
    "L": "=D{r}+I{r}+J{r}",         # 🔴 期末累计公允价值变动（**含利息 J**）
    "M": "=K{r}+L{r}",              # 期末公允价值
    "O": "=M{r}+N{r}",              # 期末审定数（🔴 调整是单列 N）
}

#: 19 个受管字段（7 元组 `(column_key, column, mode, value_type, json_key, header_text, group_header_cell)`）。
#:
#: 顺序即 Excel 列序 A→S；`header_text` 逐字取模板（两级表头取叶子行 R10，跨两行合并的
#: 单列取 R9）；`json_key` 逐字取 `useG10Detail.G10DetailRow`；`group_header_cell` 指向
#: 该列所属一级分组的合并区起始格（跨两行的单列、以及 F/G 两个无 R9 分组的列为 `""`）。
FIELD_SPECS_G1002: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("liability_category", "A", "editable", "text", "liabilityCategory", "类别", ""),
    (
        "liability_name", "B", "editable", "text", "liabilityName",
        "项目【按明细项目列示，如债券名称】", "",
    ),
    # ── C9:E9 期初余额（三分量）────────────────────────────────────────
    ("opening_initial_amount", "C", "editable", "amount", "openingInitialAmount", "初始确认金额", "C9"),
    ("opening_fv_accum", "D", "editable", "amount", "openingFvAccum", "累计公允价值变动", "C9"),
    ("opening_fair_value", "E", "formula", "amount", "openingFairValue", "公允价值", "C9"),
    # ── F / G 单列（🔴 R9 无分组：负债侧调整与审定都不拆分量）──────────
    ("opening_adjustment", "F", "editable", "amount", "openingAdjustment", "期初调整数", ""),
    ("opening_adjusted", "G", "formula", "amount", "openingAdjusted", "期初审定数", ""),
    # ── H9:J9 本期变动（增加"+"/减少"—" ⇒ **净额列**）──────────────────
    (
        "movement_initial_amount", "H", "editable", "amount",
        "movementInitialAmount", "初始确认金额", "H9",
    ),
    ("movement_fv_change", "I", "editable", "amount", "movementFvChange", "本期公允价值变动", "H9"),
    ("interest_expense", "J", "editable", "amount", "interestExpense", "计入财务费用的利息", "H9"),
    # ── K9:O9 期末余额（三分量 + 单列调整/审定）────────────────────────
    ("closing_initial_amount", "K", "formula", "amount", "closingInitialAmount", "初始确认金额", "K9"),
    ("closing_fv_accum", "L", "formula", "amount", "closingFvAccum", "累计公允价值变动", "K9"),
    ("closing_fair_value", "M", "formula", "amount", "closingFairValue", "公允价值", "K9"),
    ("closing_adjustment", "N", "editable", "amount", "closingAdjustment", "调整数", "K9"),
    ("closing_adjusted", "O", "formula", "amount", "closingAdjusted", "审定数", "K9"),
    # ── 单列补充（P..S，均跨 R9:R10 合并）──────────────────────────────
    ("maturity_date", "P", "editable", "text", "maturityDate", "到期日", ""),
    ("coupon_rate", "Q", "editable", "text", "couponRate", "票面利率", ""),
    ("accrued_interest", "R", "editable", "amount", "accruedInterest", "期末应付利息", ""),
    ("issuance_doc_index", "S", "editable", "text", "issuanceDocIndex", "发行文件索引", ""),
)

SPEC_G1002: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_G1002,
    sheet_key=SHEET_KEY_G1002,
    table_key="g10_detail_rows",
    template_id=TEMPLATE_ID_G1002,
    table_name=f"GT_{TEMPLATE_ID_G1002}_DETAIL_ROWS",
    #: 🔴 有效内容列 19（A..S），T..X 全空 ⇒ UUID 列取 T（不是 max_column+1=Y：
    #:   `max_column=24` 含空列，按**有效**列右移一列才是判据 GC-3 的口径）
    uuid_col="T",
    first_data_row=FIRST_DATA_ROW_G1002,
    last_data_row=LAST_DATA_ROW_G1002,
    footer_row=FOOTER_ROW_G1002,
    header_group_row=HEADER_GROUP_ROW_G1002,
    header_leaf_row=HEADER_LEAF_ROW_G1002,
    store_item_id=STORE_ITEM_ID_G1002,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_G1002,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_G1002,
    formula_columns=FORMULA_COLUMNS_G1002,
    formula_templates=FORMULA_TEMPLATES_G1002,
    footer_marker=FOOTER_MARKER_G1002,
    error_label="G10-2 交易性金融负债明细表",
    #: 🔴 幽灵行锚点指 **B 列「项目」**（真正的业务名称），不是默认的 `[0]`（A 列「类别」）。
    #:   A 列是枚举（指定类 / 交易类）且模板 R11 本就有预填值「指定类」，用它当锚点会让
    #:   「只填了类别的空行」通不过幽灵行防护、而「OO 侧只填了项目名的真行」被当幽灵行剔除。
    #:   与 G9 / D5 的同型例外一致。
    ghost_row_anchor_index=1,
)
