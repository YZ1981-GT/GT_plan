# -*- coding: utf-8 -*-
"""F5-5「与上年度比较分析表」—— sheet 层薄声明。

spec: f5-sync-coverage-and-first-canary · Task 13 · Requirements 4.1, 4.4
几何证据: openpyxl 逐格实测（2026-10-07）

═══ 几何 ═══

两级表头 **R9（组）/ R10（叶子）**：
    A(A9:A10) 产品  |  B~D(B9:D9) 本期数  |  E~G(E9:G9) 上期数  |
    H~J(H9:J9) 变动额  |  K~M(K9:M9) 变动率  |  N~O(N9:O9) 差异原因分析

叶子行 R10：B 数量 / C 平均单位成本 / D 总成本 / E 数量 / F 平均单位成本 / G 总成本 /
             H 数量 / I 平均单位成本 / J 总成本 / K 数量 / L 平均单位成本 / M 总成本 /
             N 变动原因 / O 索引号

数据区 **R11~R16**（6 行）· footer **R17** 合计。
R8 「二、审计过程：」是节标题，非表头。

═══ 公式列（8 列，逐行同构）═══

    D{r} = B{r}*C{r}             本期总成本
    G{r} = E{r}*F{r}             上期总成本
    H{r} = B{r}-E{r}             数量变动额
    I{r} = C{r}-F{r}             单价变动额
    J{r} = D{r}-G{r}             总成本变动额
    K{r} = H{r}/E{r}             数量变动率（🔴 上期=0 ⇒ #DIV/0!）
    L{r} = I{r}/F{r}             单价变动率（🔴 上期=0 ⇒ #DIV/0!）
    M{r} = J{r}/G{r}             总成本变动率（🔴 上期=0 ⇒ #DIV/0!）

前端 `calcF5ComparisonChangeRate` 返回 `'N/A'`（对应 Excel #DIV/0!）。

═══ footer ═══

R17「合计」，SUM 列 D/G/J/M（四列有 SUM 公式，其余列空）。
footer_carries_total_formula=True。

═══ UUID 列 ═══

max_col=Q(17)，P 列 non_null=0 ⇒ 取 **P**。

═══ 字段 ═══

行身份 **`id`**（F5 系列统一用 `id`，与 D 类的 `rowId` 不同）。
前端 `STORAGE_KEY = 'F5-5-comparison-rows'`。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F505",
    "MANAGED_SHEET_F505",
    "STORE_ITEM_ID_F505",
]

MANAGED_SHEET_F505: Final[str] = "与上年度比较分析表F5-5"
TEMPLATE_ID_F505: Final[str] = "F55"
SHEET_KEY_F505: Final[str] = "f55-managed"
ROWS_TABLE_KEY_F505: Final[str] = "comparison_rows"
STORE_ITEM_ID_F505: Final[str] = "F5-5-comparison-rows"

ROW_IDENTITY_STORE_KEY_F505: Final[str] = "id"

HEADER_GROUP_ROW_F505: Final[int] = 9
HEADER_LEAF_ROW_F505: Final[int] = 10
FIRST_DATA_ROW_F505: Final[int] = 11
LAST_DATA_ROW_F505: Final[int] = 16
FOOTER_ROW_F505: Final[int] = 17
FOOTER_MARKER_F505: Final[str] = "合计"
MANAGED_LAST_COL_F505: Final[str] = "O"
UUID_COL_F505: Final[str] = "P"

#: 7 个受管 editable 字段。公式列（D,G,H,I,J,K,L,M）不进 field_specs。
FIELD_SPECS_F505: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("product", "A", "editable", "text", "product", "产品", ""),
    ("current_qty", "B", "editable", "amount", "currentQty", "数量", "B9"),
    ("current_unit_cost", "C", "editable", "amount", "currentUnitCost", "平均单位成本", "B9"),
    ("prior_qty", "E", "editable", "amount", "priorQty", "数量", "E9"),
    ("prior_unit_cost", "F", "editable", "amount", "priorUnitCost", "平均单位成本", "E9"),
    ("change_reason", "N", "editable", "text", "changeReason", "变动原因", "N9"),
    ("index_ref", "O", "editable", "text", "indexRef", "索引号", "N9"),
)

SPEC_F505: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F505,
    sheet_key=SHEET_KEY_F505,
    table_key=ROWS_TABLE_KEY_F505,
    template_id=TEMPLATE_ID_F505,
    table_name=f"GT_{TEMPLATE_ID_F505}_ROWS",
    uuid_col=UUID_COL_F505,
    first_data_row=FIRST_DATA_ROW_F505,
    last_data_row=LAST_DATA_ROW_F505,
    footer_row=FOOTER_ROW_F505,
    header_group_row=HEADER_GROUP_ROW_F505,
    header_leaf_row=HEADER_LEAF_ROW_F505,
    store_item_id=STORE_ITEM_ID_F505,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F505,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F505,
    formula_columns=("D", "G", "H", "I", "J", "K", "L", "M"),
    formula_templates={
        "D": "=B{r}*C{r}",
        "G": "=E{r}*F{r}",
        "H": "=B{r}-E{r}",
        "I": "=C{r}-F{r}",
        "J": "=D{r}-G{r}",
        "K": "=H{r}/E{r}",
        "L": "=I{r}/F{r}",
        "M": "=J{r}/G{r}",
    },
    footer_marker=FOOTER_MARKER_F505,
    footer_carries_total_formula=True,
    error_label="F5-5 与上年度比较分析表",
)
