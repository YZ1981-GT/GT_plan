# -*- coding: utf-8 -*-
"""D1-2「原值明细表（按类别）」—— sheet 层薄声明（批次 1 第一张）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 25 · Requirements 5.1 / 5.2 / 11.7
几何证据: docs/operations/evidence/row-table-engine-d1-coverage/d1-02-category-geometry.json

═══ 为什么它排批次 1 第一张 ═══

它与已接的 D1-3 在**同一册**模板（21 张 sheet 里第 6 张，D1-3 是第 7 张）、同一套双期审定列、
同一个宿主组件。接通它即证明「一个 entry 多受管 sheet」在 D1 上成立，且失败面最小
（若挂，挂的是 D1-2 那一个 binding，且灰度开关可立即关掉）。

═══ 🔴 实测推翻 spec 首版的形态假设 ═══

requirements 批次表写 D1-2 是「固定 2 + 动态行」混合身份。**openpyxl 逐格实测**（2026-09-26）：
模板只画了 **3 个固定票据种类行**（R11 银行承兑 / R12 财务公司承兑 / R13 商业承兑），
footer R14「合计」紧接其后，**零动态行区域**。

⇒ 按 D4-6 范式判「**稳定 key 固定行**」：`row_identity_key='key'`（不是 `rowId`）、行不增删，
   但**仍是 `excel_table` binding 且仍注入 UUID 列** —— 判据是「有没有行维度」而不是
   「行会不会变」（spec design §附表二）。

═══ 几何（逐格实测，禁推演）═══

单级表头 R10（11 列 A..K）· 数据区 R11-13（3 固定行）· footer R14「合计」（纯两字无空格，
与 D1-4 的「合计  」带两个全角空格不同）· 公式列 E/H/K：
`=B+C+D`（期初审定）· `=B+F-G`（期末未审）· `=H+I+J`（期末审定）· 注入 UUID 列 L。

🔴 H 列 xlsx 公式用 **B（期初未审）** 而非 E（期初审定）作被加数。前端若用 priorAudited
   则与 xlsx 公式文本不同 —— 按 D1-3 已立纪律**以 xlsx 为准**，H 声明 formula、
   materialize 不覆盖公式格、由 OO 重算。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_D102",
    "MANAGED_SHEET_D102",
    "STORE_ITEM_ID_D102",
    "ROW_IDENTITY_STORE_KEY_D102",
    "FIXED_ROW_KEYS_D102",
]

MANAGED_SHEET_D102: Final[str] = "原值明细表（按类别）D1-2"
TEMPLATE_ID_D102: Final[str] = "D12"
SHEET_KEY_D102: Final[str] = f"{TEMPLATE_ID_D102.lower()}-managed"
ROWS_TABLE_KEY_D102: Final[str] = "category_detail_rows"
STORE_ITEM_ID_D102: Final[str] = "D1-cat-rows"

#: 🔴 稳定 key 固定行（D4-6 范式 `ROW_IDENTITY_KEY_D46="key"`）—— 不是 UUID 动态行。
ROW_IDENTITY_STORE_KEY_D102: Final[str] = "key"

#: 三个固定票据种类行的稳定 key（顺序即 Excel 行序 R11→R13，与模板 A 列标签一一对应）。
FIXED_ROW_KEYS_D102: Final[tuple[tuple[str, int, str], ...]] = (
    ("fixed-bank", 11, "银行承兑汇票"),
    ("fixed-finance", 12, "财务公司承兑汇票"),
    ("fixed-commercial", 13, "商业承兑汇票"),
)

HEADER_ROW_D102: Final[int] = 10
FIRST_DATA_ROW_D102: Final[int] = 11
LAST_DATA_ROW_D102: Final[int] = 13
FOOTER_ROW_D102: Final[int] = 14
#: footer marker 实测为纯「合计」两字（**无空格**）—— 不要照搬 D1-4 的「合计  」。
FOOTER_MARKER_D102: Final[str] = "合计"
MANAGED_LAST_COL_D102: Final[str] = "K"
UUID_COL_D102: Final[str] = "L"

#: 11 个受管字段（7 元组，末位 group_header_cell 为 "" —— 单级表头无分组）。
#: 顺序即 Excel 列序 A→K；表头文本与 R10 逐字相等（实测）。
#: E/H/K 三列模板内逐行有真公式 ⇒ formula；其余 8 列无公式 ⇒ editable。
FIELD_SPECS_D102: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("note_type", "A", "editable", "text", "noteType", "票据种类", ""),
    ("prior_unadjusted", "B", "editable", "amount", "priorUnadjusted", "期初未审数", ""),
    ("prior_aje", "C", "editable", "amount", "priorAje", "账项调整", ""),
    ("prior_rje", "D", "editable", "amount", "priorRje", "重分类调整", ""),
    ("prior_audited", "E", "formula", "amount", "priorAudited", "期初审定数", ""),
    ("current_increase", "F", "editable", "amount", "currentIncrease", "本期增加", ""),
    ("current_decrease", "G", "editable", "amount", "currentDecrease", "本期减少", ""),
    ("current_unadjusted", "H", "formula", "amount", "currentUnadjusted", "期末未审数", ""),
    ("current_aje", "I", "editable", "amount", "currentAje", "账项调整", ""),
    ("current_rje", "J", "editable", "amount", "currentRje", "重分类调整", ""),
    ("current_audited", "K", "formula", "amount", "currentAudited", "期末审定数", ""),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐格实测，守卫可逐行与模板比对。
FORMULA_TEMPLATES_D102: Final[dict[str, str]] = {
    "E": "=B{r}+C{r}+D{r}",
    "H": "=B{r}+F{r}-G{r}",
    "K": "=H{r}+I{r}+J{r}",
}

SPEC_D102: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D102,
    sheet_key=SHEET_KEY_D102,
    table_key=ROWS_TABLE_KEY_D102,
    template_id=TEMPLATE_ID_D102,
    table_name=f"GT_{TEMPLATE_ID_D102}_ROWS",
    uuid_col=UUID_COL_D102,
    first_data_row=FIRST_DATA_ROW_D102,
    last_data_row=LAST_DATA_ROW_D102,
    footer_row=FOOTER_ROW_D102,
    header_row=HEADER_ROW_D102,
    store_item_id=STORE_ITEM_ID_D102,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_D102,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D102,
    formula_columns=("E", "H", "K"),
    formula_templates=FORMULA_TEMPLATES_D102,
    footer_marker=FOOTER_MARKER_D102,
    error_label="D1-2 原值明细表（按类别）",
)
