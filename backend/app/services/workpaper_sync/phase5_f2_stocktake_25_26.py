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
#   UUID 列: Q / R（区一 / 区二）

#: 🔴 字段键逐字取前端 `f2StocktakeConfigs.StocktakeSampleRow`（spec oo-writeback-template-parity-closure R3）。
#: 原声明照另一种版式写（A 盘点地点 / H 盘点数量 / I 盘点金额 / J~L 差异数量·金额·率 / N 处理意见），
#: 与模板 R14/R15 表头整体错位，OO 填的存货编码会写进前端没有的 `location`、抽盘数量写进 `countAmt`。
#: 公式列 J/K/L 由前端 `f2StocktakeRowCalc.enrichStocktakeSampleRow` 现算、不落库（formula 字段只读）。
#: 品质状况右侧（N 起）模板无列；前端的差异原因 / 备注只在 HTML 侧。
_FIELD_SPECS_F225: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_code",        "A", "editable", "text",   "itemCode",       "存货编码",         ""),
    ("item_name",        "B", "editable", "text",   "itemName",       "存货名称/类别",    ""),
    ("spec",             "C", "editable", "text",   "spec",           "规格",             ""),
    ("unit",             "D", "editable", "text",   "unit",           "单位",             ""),
    ("unit_price",       "E", "editable", "amount", "unitPrice",      "单价",             ""),
    ("book_qty",         "F", "editable", "amount", "bookQty",        "数量",             ""),
    ("book_amount",      "G", "editable", "amount", "bookAmount",     "金额",             ""),
    ("client_count_qty", "H", "editable", "amount", "clientCountQty", "企业盘点记录数量", ""),
    ("sample_qty",       "I", "editable", "amount", "sampleQty",      "抽盘数量",         ""),
    ("sample_vs_book",   "J", "formula",  "amount", "sampleVsBook",   "抽盘与账面差异（+盈-亏）", ""),
    ("sample_vs_client", "K", "formula",  "amount", "sampleVsClient", "抽盘与企业盘点差异", ""),
    ("client_vs_book",   "L", "formula",  "amount", "clientVsBook",   "企业盘点与账面差异", ""),
    ("quality_status",   "M", "editable", "text",   "qualityStatus",  "品质状况（正常/残次/毁损/滞销等）", ""),
)

_FORMULA_COLUMNS_F225: Final[tuple[str, ...]] = ("J", "K", "L")
#: 模板 R16 逐格：J=I−F、K=I−H、L=H−F（两区同式）
_FORMULA_TEMPLATES_F225: Final[dict[str, str]] = {
    "J": "=I{r}-F{r}",
    "K": "=I{r}-H{r}",
    "L": "=H{r}-F{r}",
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
#
# 几何（openpyxl 实测）：
#   区一（日后）：表头 R7，数据 R8-R14，锚行 R15「（二）资产负债表日前盘点倒轧表」（无合计）
#   区二（日前）：表头 R16，数据 R17-R23，锚行 R24「审计说明：」（无合计）
#   formula_in_data: J=G+H−I、L=J−K、M=L×E（两区同式；区一 J9 旧缺陷已随模板修正）
#   UUID 列: P / Q
#   footer_carries_total_formula=False（无 SUM 公式）
#
# 🔴 H / I 两列的业务含义两区相反（spec oo-writeback-template-parity-closure R3）：
#   日后表 H「加：资产负债表日至监盘日发出数量」I「减：…入库数量」；
#   日前表 H「加：监盘日至资产负债表日入库数量」I「减：…发出数量」。
#   前端 `StocktakeRollforwardRow` 两张表都存 inboundQty / outboundQty（实物入库 / 发出量），
#   所以两区的 H / I 接到不同字段。原声明两区共用一份、且列名照另一种版式写
#   （A 存货编号 / E 账面数量 / F 账面金额 / K 单位成本 …），与模板 R7 / R16 表头整体错位。
#   C 列模板是「品名及规格」一列，接前端 itemName；前端单独的 spec 只在 HTML 侧。


def _f226_fields(*, h: tuple[str, str, str], i: tuple[str, str, str]) -> tuple[tuple[str, str, str, str, str, str, str], ...]:
    """两区共用的字段声明；`h` / `i` = (column_key, json_key, 表头) 按区给。"""
    return (
        ("category",        "A", "editable", "text",   "category",       "存货类别",           ""),
        ("item_code",       "B", "editable", "text",   "itemCode",       "存货编码",           ""),
        ("item_name",       "C", "editable", "text",   "itemName",       "品名及规格",         ""),
        ("unit",            "D", "editable", "text",   "unit",           "单位",               ""),
        ("unit_price",      "E", "editable", "amount", "unitPrice",      "单价",               ""),
        ("warehouse",       "F", "editable", "text",   "warehouse",      "仓库",               ""),
        ("count_day_qty",   "G", "editable", "amount", "countDayQty",    "监盘日实存数量",     ""),
        (h[0],              "H", "editable", "amount", h[1],             h[2],                 ""),
        (i[0],              "I", "editable", "amount", i[1],             i[2],                 ""),
        ("calc_bs_qty",     "J", "formula",  "amount", "calcBsQty",      "资产负债表日实存数量", ""),
        ("book_qty",        "K", "editable", "amount", "bookQty",        "资产负债表日账面数量", ""),
        ("qty_diff",        "L", "formula",  "amount", "qtyDiff",        "数量差异",           ""),
        ("amt_diff",        "M", "formula",  "amount", "amtDiff",        "金额差异",           ""),
        ("variance_reason", "N", "editable", "text",   "varianceReason", "差异原因",           ""),
        ("need_adjust",     "O", "editable", "text",   "needAdjust",     "是否调整",           ""),
    )


_FIELD_SPECS_F226_AFTER: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = _f226_fields(
    h=("outbound_qty", "outboundQty", "加：资产负债表日至监盘日发出数量（经核对调节后）"),
    i=("inbound_qty", "inboundQty", "减：资产负债表日至监盘日入库数量（经核对调节后）"),
)
_FIELD_SPECS_F226_BEFORE: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = _f226_fields(
    h=("inbound_qty", "inboundQty", "加：监盘日至资产负债表日入库数量"),
    i=("outbound_qty", "outboundQty", "减：监盘日至资产负债表日发出数量"),
)

_FORMULA_COLUMNS_F226: Final[tuple[str, ...]] = ("J", "L", "M")
_FORMULA_TEMPLATES_F226: Final[dict[str, str]] = {
    "J": "=G{r}+H{r}-I{r}",
    "L": "=J{r}-K{r}",
    "M": "=L{r}*E{r}",
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
    field_specs=_FIELD_SPECS_F226_BEFORE,
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
    field_specs=_FIELD_SPECS_F226_AFTER,
    formula_columns=_FORMULA_COLUMNS_F226,
    formula_templates=_FORMULA_TEMPLATES_F226,
    footer_marker="（二）资产负债表日前盘点倒轧表",
    footer_carries_total_formula=False,
    error_label="F2-26 区一（日后 F2-26-after-rows）",
)
