# -*- coding: utf-8 -*-
"""F2-25 / F2-26 四个 spec 的桩文件（Task 15 填充完整声明）。

spec: f2-sync-coverage-four-entry-lanes · Task 15（桩由 Task 14 建立）
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F225_EXIST",
    "SPEC_F225_FLOOR",
    "SPEC_F226_BEFORE",
    "SPEC_F226_AFTER",
]

ROW_IDENTITY_KEY: Final[str] = "id"

# ═══════════════════════════════════════════════════════════════════════════
# F2-25 抽盘结果汇总表 —— 双区（canary）
# ═══════════════════════════════════════════════════════════════════════════
#
# 几何（Task 2 实测）：
#   区一（账→实）：表头 R14/R15，数据 R16-R26，footer A27="合计"
#   区二（实→账）：表头 R29/R30，数据 R31-R41，footer A42="合计"
#   formula_in_data: J,K,L（两区同列结构）
#   UUID 列: Q（两区共用）

_FIELD_SPECS_F225: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("location",    "A", "editable", "text",   "location",     "盘点地点",     ""),
    ("item_code",   "B", "editable", "text",   "itemCode",     "存货编号",     ""),
    ("item_name",   "C", "editable", "text",   "itemName",     "存货名称",     ""),
    ("spec",        "D", "editable", "text",   "spec",         "规格型号",     ""),
    ("unit",        "E", "editable", "text",   "unit",         "计量单位",     ""),
    ("book_qty",    "F", "editable", "amount", "bookQty",      "账面数量",     ""),
    ("book_amt",    "G", "editable", "amount", "bookAmt",      "账面金额",     ""),
    ("count_qty",   "H", "editable", "amount", "countQty",     "盘点数量",     ""),
    ("count_amt",   "I", "editable", "amount", "countAmt",     "盘点金额",     ""),
    ("diff_qty",    "J", "formula",  "amount", "diffQty",      "差异数量",     ""),
    ("diff_amt",    "K", "formula",  "amount", "diffAmt",      "差异金额",     ""),
    ("diff_rate",   "L", "formula",  "amount", "diffRate",     "差异率",       ""),
    ("reason",      "M", "editable", "text",   "reason",       "差异原因",     ""),
    ("conclusion",  "N", "editable", "text",   "conclusion",   "处理意见",     ""),
)

_FORMULA_COLUMNS_F225: Final[tuple[str, ...]] = ("J", "K", "L")
_FORMULA_TEMPLATES_F225: Final[dict[str, str]] = {
    "J": "=F{r}-H{r}",
    "K": "=G{r}-I{r}",
    "L": "=IF(G{r}=0,0,K{r}/G{r})",
}

SPEC_F225_EXIST: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet="抽盘结果汇总表F2-25",
    sheet_key="f225-managed",
    table_key="stocktake_sample_exist_rows",
    template_id="F225E",
    table_name="GT_F225_EXIST_ROWS",
    uuid_col="Q",
    first_data_row=16,
    last_data_row=26,
    footer_row=27,
    header_group_row=14,
    header_leaf_row=15,
    store_item_id="F2-25-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_F225,
    formula_columns=_FORMULA_COLUMNS_F225,
    formula_templates=_FORMULA_TEMPLATES_F225,
    footer_marker="合计",
    error_label="F2-25 区一（账→实）",
)

SPEC_F225_FLOOR: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet="抽盘结果汇总表F2-25",
    sheet_key="f225-managed",
    table_key="stocktake_sample_floor_rows",
    template_id="F225F",
    table_name="GT_F225_FLOOR_ROWS",
    uuid_col="R",
    first_data_row=31,
    last_data_row=41,
    footer_row=42,
    header_group_row=29,
    header_leaf_row=30,
    store_item_id="F2-25-floor-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_F225,
    formula_columns=_FORMULA_COLUMNS_F225,
    formula_templates=_FORMULA_TEMPLATES_F225,
    footer_marker="合计",
    error_label="F2-25 区二（实→账）",
)


# ═══════════════════════════════════════════════════════════════════════════
# F2-26 盘点倒轧表 —— 双区（无合计行）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 键名陷阱：F2-26-rows = 日前区（区二），F2-26-after-rows = 日后区（区一）
# 🔴 区一 J9 模板缺陷（J9=J2+H9-I9，J2 在标题合并区），模板覆盖层修后接入
#
# 几何（Task 2 实测）：
#   区一（日后）：表头 R7，数据 R8-R14，锚行 R15（无合计）
#   区二（日前）：表头 R16，数据 R17-R23，锚行 R24（无合计）
#   formula_in_data: J,L,M（两区同列结构）
#   UUID 列: P（两区共用）
#   footer_carries_total_formula=False（无 SUM 公式）

_FIELD_SPECS_F226: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_code",       "A", "editable", "text",   "itemCode",       "存货编号",       ""),
    ("item_name",       "B", "editable", "text",   "itemName",       "存货名称",       ""),
    ("spec",            "C", "editable", "text",   "spec",           "规格型号",       ""),
    ("unit",            "D", "editable", "text",   "unit",           "计量单位",       ""),
    ("book_qty",        "E", "editable", "amount", "bookQty",        "账面数量",       ""),
    ("book_amt",        "F", "editable", "amount", "bookAmt",        "账面金额",       ""),
    ("count_date_qty",  "G", "editable", "amount", "countDateQty",   "监盘日实存数量", ""),
    ("in_qty",          "H", "editable", "amount", "inQty",          "入库数量",       ""),
    ("out_qty",         "I", "editable", "amount", "outQty",         "出库数量",       ""),
    ("bs_date_qty",     "J", "formula",  "amount", "bsDateQty",      "资产负债表日实存数量", ""),
    ("unit_cost",       "K", "editable", "amount", "unitCost",       "单位成本",       ""),
    ("bs_date_amt",     "L", "formula",  "amount", "bsDateAmt",      "资产负债表日实存金额", ""),
    ("diff_amt",        "M", "formula",  "amount", "diffAmt",        "差异金额",       ""),
    ("reason",          "N", "editable", "text",   "reason",         "差异原因",       ""),
)

_FORMULA_COLUMNS_F226: Final[tuple[str, ...]] = ("J", "L", "M")
_FORMULA_TEMPLATES_F226: Final[dict[str, str]] = {
    "J": "=G{r}+H{r}-I{r}",
    "L": "=J{r}*K{r}",
    "M": "=L{r}-F{r}",
}

SPEC_F226_BEFORE: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet="盘点倒轧表F2-26",
    sheet_key="f226-managed",
    table_key="stocktake_rollforward_before_rows",
    template_id="F226B",
    table_name="GT_F226_BEFORE_ROWS",
    uuid_col="Q",
    first_data_row=17,
    last_data_row=23,
    footer_row=24,
    header_row=16,
    store_item_id="F2-26-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_F226,
    formula_columns=_FORMULA_COLUMNS_F226,
    formula_templates=_FORMULA_TEMPLATES_F226,
    footer_marker="审计说明：",
    footer_carries_total_formula=False,
    error_label="F2-26 区二（日前 F2-26-rows）",
)

SPEC_F226_AFTER: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet="盘点倒轧表F2-26",
    sheet_key="f226-managed",
    table_key="stocktake_rollforward_after_rows",
    template_id="F226A",
    table_name="GT_F226_AFTER_ROWS",
    uuid_col="P",
    first_data_row=8,
    last_data_row=14,
    footer_row=15,
    header_row=7,
    store_item_id="F2-26-after-rows",
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_F226,
    formula_columns=_FORMULA_COLUMNS_F226,
    formula_templates=_FORMULA_TEMPLATES_F226,
    footer_marker="（二）资产负债表日前盘点倒轧表",
    footer_carries_total_formula=False,
    error_label="F2-26 区一（日后 F2-26-after-rows）🔴 J9 模板缺陷待覆盖层修",
)
