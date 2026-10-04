# -*- coding: utf-8 -*-
"""F2 main 册明细表族（F2-3/4/6/8/9）—— 五个 RowTableSheetSpec 常量。

spec: f2-sync-coverage-four-entry-lanes · Task 8 · Requirements 2.1~2.7
裁决 F2-H4：一个声明文件、五个显式 spec 常量 + 共享字段元组常量。

═══ 五表共享 useF2DetailSheet（config 驱动）═══

前端 F2_DETAIL_SHEET_CONFIGS 按 sheetCode 区分：只差 hasQuantity / identityMode /
hasPostPeriod / hasSalesOrderCols / noteProfile。本文件取**公共子集**声明 field_specs，
差异列各自追加。禁 `def`/`class`（E1 Task 13 判据 + Property 5）。

═══ canary = F2-6 ═══

四、自制半成品明细表（30r×U / 两级表头 R6/R7 / 数据 R9-24 / footer A25="合计"）。
与 F2-3 的唯一差异：footer 标记列——F2-6 在 A 列，F2-3 在 B 列。
F2-3 暂不受管（需求 2.4：框架层 search_column 硬编码 "A"，F2-3 的"合计"在 B 列）。

═══ 几何（openpyxl 逐格实测，2026-09-26）═══

| sheet | dims | data | footer | formula_in_data | UUID | 特殊 |
|---|---|---|---|---|---|---|
| F2-6 | 30r×U | R9-24 | A25 | F,I,L,N,O,P | V | canary |
| F2-3 | 31r×U | R9-24 | **B25** | F,I,L,N,O,P | V | 🔴 footer B 列暂缓 |
| F2-4 | 30r×W | R9-24 | A25 | E,H,K,M,N,O,Q | X | identityMode=inTransit |
| F2-8 | 36r×X | R9-24 | A25 | F,I,L,N,O,P | Y | +在手订单 V/W/X |
| F2-9 | 36r×W | R9-24 | A25 | E,H,K,M,N,O,Q | X | identityMode=dispatched |
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F206",
    "SPEC_F203",
    "SPEC_F204",
    "SPEC_F208",
    "SPEC_F209",
]

# ═══════════════════════════════════════════════════════════════════════════
# 共享常量
# ═══════════════════════════════════════════════════════════════════════════

ROW_IDENTITY_KEY: Final[str] = "id"
HEADER_GROUP_ROW: Final[int] = 6
HEADER_LEAF_ROW: Final[int] = 7
FIRST_DATA_ROW: Final[int] = 9
LAST_DATA_ROW: Final[int] = 24
FOOTER_ROW: Final[int] = 25


# ═══════════════════════════════════════════════════════════════════════════
# 字段元组（共享部分：标准存货明细 A~P + 品质 U，16 列）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 F2-6 的 R6 组表头：
#   A=存货编码 | B=自制半成品名称 | C=规格 | D=单位
#   E:G=期初库存 | H:J=本期购进 | K:M=本期发出 | N:P=期末结存
#   Q:T=库龄（4 段，THREE_YEAR 口径，nested aging 仅受管时启用，本阶段不接）
#   U=品质状况
#
# 公式逐格实测（F2-6 R9）：
#   F = IF(E9=0,0,G9/E9)     期初单价
#   I = IF(H9=0,0,J9/H9)     购进单价
#   L = IF(K9=0,0,M9/K9)     发出单价
#   N = E9+H9-K9              期末数量
#   O = IF(N9=0,0,P9/N9)     期末单价
#   P = G9+J9-M9              期末金额

_FIELD_SPECS_STANDARD: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_code",     "A", "editable", "text",   "itemCode",     "存货编码",   ""),
    ("item_name",     "B", "editable", "text",   "itemName",     "存货名称",   ""),
    ("spec",          "C", "editable", "text",   "spec",         "规格",       ""),
    ("unit",          "D", "editable", "text",   "unit",         "单位",       ""),
    ("opening_qty",   "E", "editable", "amount", "openingQty",   "数量",       f"E{HEADER_GROUP_ROW}"),
    ("opening_price", "F", "formula",  "amount", "openingUnitPrice", "单价",   f"E{HEADER_GROUP_ROW}"),
    ("opening_amt",   "G", "editable", "amount", "openingAmt",   "金额",       f"E{HEADER_GROUP_ROW}"),
    ("increase_qty",  "H", "editable", "amount", "increaseQty",  "数量",       f"H{HEADER_GROUP_ROW}"),
    ("increase_price","I", "formula",  "amount", "increaseUnitPrice","单价",    f"H{HEADER_GROUP_ROW}"),
    ("increase_amt",  "J", "editable", "amount", "increaseAmt",  "金额",       f"H{HEADER_GROUP_ROW}"),
    ("decrease_qty",  "K", "editable", "amount", "decreaseQty",  "数量",       f"K{HEADER_GROUP_ROW}"),
    ("decrease_price","L", "formula",  "amount", "decreaseUnitPrice","单价",    f"K{HEADER_GROUP_ROW}"),
    ("decrease_amt",  "M", "editable", "amount", "decreaseAmt",  "金额",       f"K{HEADER_GROUP_ROW}"),
    ("closing_qty",   "N", "formula",  "amount", "closingQty",   "数量",       f"N{HEADER_GROUP_ROW}"),
    ("closing_price", "O", "formula",  "amount", "unitPrice",    "单价",       f"N{HEADER_GROUP_ROW}"),
    ("closing_amt",   "P", "formula",  "amount", "closingAmt",   "金额",       f"N{HEADER_GROUP_ROW}"),
    ("quality_status","U", "editable", "text",   "qualityStatus","品质状况",   ""),
)

#: 账龄列 Q-T（4 段 THREE_YEAR 口径）—— 需求 2.6 明确仅 THREE_YEAR 启用受管。
#: 本阶段 canary 不接账龄（nested aging 需 AgingGroupSpec，后续灰度开启）。
#: 登记在此以备 Task 10 扩容时接入。

_FORMULA_COLUMNS_STANDARD: Final[tuple[str, ...]] = ("F", "I", "L", "N", "O", "P")

_FORMULA_TEMPLATES_STANDARD: Final[dict[str, str]] = {
    "F": "=IF(E{r}=0,0,G{r}/E{r})",
    "I": "=IF(H{r}=0,0,J{r}/H{r})",
    "L": "=IF(K{r}=0,0,M{r}/K{r})",
    "N": "=E{r}+H{r}-K{r}",
    "O": "=IF(N{r}=0,0,P{r}/N{r})",
    "P": "=G{r}+J{r}-M{r}",
}

#: F2-8 额外在手订单列（V/W/X），append 在 standard 之后。
_FIELD_SPECS_F208_EXTRA: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("has_open_order",  "V", "editable", "text",   "hasOpenOrder",    "是否有在手订单", ""),
    ("order_no",        "W", "editable", "text",   "orderNo",         "订单编号",       ""),
    ("sales_unit_price","X", "editable", "amount", "salesUnitPrice",  "销售单价",       ""),
)


# ═══════════════════════════════════════════════════════════════════════════
# canary：F2-6 四、自制半成品明细表
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_F206: Final[str] = "四、自制半成品明细表F2-6"
TEMPLATE_ID_F206: Final[str] = "F26"
SHEET_KEY_F206: Final[str] = "f26-managed"
STORE_ITEM_ID_F206: Final[str] = "F2-6-rows"

SPEC_F206: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F206,
    sheet_key=SHEET_KEY_F206,
    table_key="detail_f26_rows",
    template_id=TEMPLATE_ID_F206,
    table_name=f"GT_{TEMPLATE_ID_F206}_ROWS",
    uuid_col="V",
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    header_group_row=HEADER_GROUP_ROW,
    header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID_F206,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_STANDARD,
    formula_columns=_FORMULA_COLUMNS_STANDARD,
    formula_templates=_FORMULA_TEMPLATES_STANDARD,
    footer_marker="合计",
    error_label="F2-6 自制半成品明细表",
)


# ═══════════════════════════════════════════════════════════════════════════
# F2-3 一、原材料明细表（灰度默认关——footer B 列问题待框架层 footer_search_column 支持）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 与 F2-6 唯一差异：footer "合计" 在 B25 而非 A25。框架层 search_column 硬编码 "A"
# （phase5_row_table_sheet.py:309），直接受管会定位失败。需求 2.4 裁决：
# 暂不受管，登记原因，待框架层新增 footer_search_column 后开启。

MANAGED_SHEET_F203: Final[str] = "一、原材料明细表F2-3"
TEMPLATE_ID_F203: Final[str] = "F23"
SHEET_KEY_F203: Final[str] = "f23-managed"
STORE_ITEM_ID_F203: Final[str] = "F2-3-rows"

SPEC_F203: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F203,
    sheet_key=SHEET_KEY_F203,
    table_key="detail_f23_rows",
    template_id=TEMPLATE_ID_F203,
    table_name=f"GT_{TEMPLATE_ID_F203}_ROWS",
    uuid_col="V",
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    header_group_row=HEADER_GROUP_ROW,
    header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID_F203,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_STANDARD,
    formula_columns=_FORMULA_COLUMNS_STANDARD,
    formula_templates=_FORMULA_TEMPLATES_STANDARD,
    footer_marker="合计",
    error_label="F2-3 原材料明细表（🔴 footer B 列——暂不受管）",
)


# ═══════════════════════════════════════════════════════════════════════════
# F2-4 二、材料采购、在途物资明细表（灰度默认关——列偏移，另立 field_specs）
# ═══════════════════════════════════════════════════════════════════════════
#
# identityMode=inTransit：A 列=供货单位（非存货编码），B 列=采购物资名称及规格
# hasPostPeriod=true：增加期后结转三列
# dims 30r×W，UUID X
# 🔴 列号偏移：三联结构起点不同（无 spec 列→E 起于 D 列 qty），需独立 field_specs。
# 本阶段登记，Task 10 实测确认列映射后接入。

MANAGED_SHEET_F204: Final[str] = "二、材料采购、在途物资明细表F2-4"
TEMPLATE_ID_F204: Final[str] = "F24"
SHEET_KEY_F204: Final[str] = "f24-managed"
STORE_ITEM_ID_F204: Final[str] = "F2-4-rows"

SPEC_F204: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F204,
    sheet_key=SHEET_KEY_F204,
    table_key="detail_f24_rows",
    template_id=TEMPLATE_ID_F204,
    table_name=f"GT_{TEMPLATE_ID_F204}_ROWS",
    uuid_col="X",
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    header_group_row=HEADER_GROUP_ROW,
    header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID_F204,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_STANDARD,  # 🔴 暂用 standard，Task 10 替换为偏移版
    formula_columns=_FORMULA_COLUMNS_STANDARD,
    formula_templates=_FORMULA_TEMPLATES_STANDARD,
    footer_marker="合计",
    error_label="F2-4 材料采购在途明细表",
)


# ═══════════════════════════════════════════════════════════════════════════
# F2-8 六、库存商品明细表（灰度默认关——+在手订单 V/W/X）
# ═══════════════════════════════════════════════════════════════════════════
#
# A~U 结构与 F2-6 完全相同，V/W/X 是额外的在手订单列。
# dims 36r×X，UUID Y

MANAGED_SHEET_F208: Final[str] = "六、库存商品明细表F2-8"
TEMPLATE_ID_F208: Final[str] = "F28"
SHEET_KEY_F208: Final[str] = "f28-managed"
STORE_ITEM_ID_F208: Final[str] = "F2-8-rows"

SPEC_F208: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F208,
    sheet_key=SHEET_KEY_F208,
    table_key="detail_f28_rows",
    template_id=TEMPLATE_ID_F208,
    table_name=f"GT_{TEMPLATE_ID_F208}_ROWS",
    uuid_col="Y",
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    header_group_row=HEADER_GROUP_ROW,
    header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID_F208,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_STANDARD + _FIELD_SPECS_F208_EXTRA,
    formula_columns=_FORMULA_COLUMNS_STANDARD,
    formula_templates=_FORMULA_TEMPLATES_STANDARD,
    footer_marker="合计",
    error_label="F2-8 库存商品明细表",
)


# ═══════════════════════════════════════════════════════════════════════════
# F2-9 七、发出商品（灰度默认关——列偏移同 F2-4）
# ═══════════════════════════════════════════════════════════════════════════
#
# identityMode=dispatched：A=购货单位，B=发出商品名称及规格
# hasPostPeriod=true，dims 36r×W，UUID X
# 列偏移同 F2-4，Task 10 替换 field_specs。

MANAGED_SHEET_F209: Final[str] = "七、发出商品F2-9"
TEMPLATE_ID_F209: Final[str] = "F29"
SHEET_KEY_F209: Final[str] = "f29-managed"
STORE_ITEM_ID_F209: Final[str] = "F2-9-rows"

SPEC_F209: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F209,
    sheet_key=SHEET_KEY_F209,
    table_key="detail_f29_rows",
    template_id=TEMPLATE_ID_F209,
    table_name=f"GT_{TEMPLATE_ID_F209}_ROWS",
    uuid_col="X",
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    header_group_row=HEADER_GROUP_ROW,
    header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID_F209,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_STANDARD,  # 🔴 暂用 standard，Task 10 替换为偏移版
    formula_columns=_FORMULA_COLUMNS_STANDARD,
    formula_templates=_FORMULA_TEMPLATES_STANDARD,
    footer_marker="合计",
    error_label="F2-9 发出商品明细表",
)
