# -*- coding: utf-8 -*-
"""D6-8「减值准备测算」—— sheet 层薄声明（单项计提区）。

spec: d567-sync-coverage-via-row-table-engine · Task 10 · Requirements 2.4

几何（openpyxl 直读 2026-09-26）：48r × 15c(O) / 58f。
单项计提区：数据 R12-R17，小计 R18。公式列 D(=B*C) F(=D-E)。
🔴 store_item_id = "D6-8-single-rows"（不是 D6-8-rows，后者全仓零写入点）。
🔴 D6-8 有多个 section（单项/组合1/组合2），但 store 只有 `D6-8-single-rows` + `D6-8-groups`。
   本声明只覆盖 `D6-8-single-rows`（单项计提行表区），组合 section 走独立存储不在本 spec 范围。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

__all__ = ["SPEC_D608", "MANAGED_SHEET_D608", "STORE_ITEM_ID_D608"]

MANAGED_SHEET_D608: Final[str] = "减值准备测算D6-8"
TEMPLATE_ID_D608: Final[str] = "D68"
SHEET_KEY_D608: Final[str] = "d68-managed"
ROWS_TABLE_KEY_D608: Final[str] = "ecl_single_rows"
#: 🔴 实测值，不是 D6-8-rows（零写入点聚合键）！
STORE_ITEM_ID_D608: Final[str] = "D6-8-single-rows"
ROW_IDENTITY_STORE_KEY_D608: Final[str] = "rowId"

#: 单项计提区几何。
HEADER_ROW_D608: Final[int] = 11
FIRST_DATA_ROW_D608: Final[int] = 13  # R12 是公式标注行（①②③=①×②），不是数据行
LAST_DATA_ROW_D608: Final[int] = 17
FOOTER_ROW_D608: Final[int] = 18
FOOTER_MARKER_D608: Final[str] = "小计"
MANAGED_LAST_COL_D608: Final[str] = "H"
UUID_COL_D608: Final[str] = "I"

#: 8 列。D(expectedProvision=B*C formula) F(difference=D-E formula)。
FIELD_SPECS_D608: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("debtor_name", "A", "editable", "text", "debtorName", "债务人名称", ""),
    ("audited_balance", "B", "editable", "amount", "auditedBalance", "审定账面余额", ""),
    ("loss_rate", "C", "editable", "ratio", "lossRate", "预期信用损失率", ""),
    ("expected_provision", "D", "formula", "amount", "expectedProvision", "期末应计提", ""),
    ("book_balance", "E", "editable", "amount", "bookBalance", "期末账面余额", ""),
    ("difference", "F", "formula", "amount", "difference", "差异", ""),
    ("basis", "G", "editable", "text", "basis", "计提依据", ""),
    ("index_ref", "H", "editable", "text", "indexRef", "索引号", ""),
)

SPEC_D608: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D608,
    sheet_key=SHEET_KEY_D608,
    table_key=ROWS_TABLE_KEY_D608,
    template_id=TEMPLATE_ID_D608,
    table_name=f"GT_{TEMPLATE_ID_D608}_ROWS",
    uuid_col=UUID_COL_D608,
    first_data_row=FIRST_DATA_ROW_D608,
    last_data_row=LAST_DATA_ROW_D608,
    footer_row=FOOTER_ROW_D608,
    header_row=HEADER_ROW_D608,
    store_item_id=STORE_ITEM_ID_D608,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_D608,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D608,
    formula_columns=("D", "F"),
    aging_layout=None,  # 单项计提无账龄
    footer_marker=FOOTER_MARKER_D608,
    error_label="D6-8 减值准备测算（单项计提）",
)
