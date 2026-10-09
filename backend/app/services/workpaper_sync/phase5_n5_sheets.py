# -*- coding: utf-8 -*-
"""N5 所得税费用 — 受管 sheet 层声明。

受管 sheet = `所得税费用明细表N5-2`：单级表头 R8、6列 A-F、
数据区 R9-R20（12行固定项）、R21 合计=SUM、R22 未审数、R23 审计调整=审定-未审。
🔴 只有 B10/D10 两格有公式（=B9*25%/=D9*25%），其余全 editable。
但 R10 是数据区内的行——公式模板声明为引擎不覆盖该行已有公式。
🔴 R21 合计在 A21，footer_marker="所得税费用审定数"。
"""
from __future__ import annotations
from typing import Any, Final, Mapping
from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec, StoreKind,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (
    managed_field_specs as _engine_managed_field_specs,
)

PHASE5_WAVE: Final[str] = "n_cycle_income_tax_expense"
ENTRY_ID: Final[str] = "xlsx/gt-n5-income-tax-expense"
ADAPTER_ID: Final[str] = "n5.income_tax_expense"
WP_CODES: Final[frozenset[str]] = frozenset({"N5I"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "N/N5 所得税费用.xlsx"
TEMPLATE_SHA256: Final[str] = "d5dd5b29ac649dbbd2959496bcdad4c984f0210996bdaba2407072758c4e89b3"
MANAGED_SHEET: Final[str] = "所得税费用明细表N5-2"
DERIVED_SHEET: Final[str] = "所得税费用审定表N5-1"
TEMPLATE_ID: Final[str] = "N52"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "income_tax_expense_detail_rows"
HEADER_ROW: Final[int] = 8
FIRST_DATA_ROW: Final[int] = 9
LAST_DATA_ROW: Final[int] = 20
FOOTER_ROW: Final[int] = 21
MANAGED_LAST_COL: Final[str] = "F"
UUID_COL: Final[str] = "G"
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
FOOTER_MARKER: Final[str] = "所得税费用审定数"
FOOTER_SEARCH_COLUMN: Final[str] = "A"
STORE_ITEM_ID: Final[str] = "N5-2-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "id"
HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = ()

MANAGED_FIELD_SPECS_7: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("current_amount", "B", "editable", "amount", "currentAmount", "本期数", ""),
    ("current_index", "C", "editable", "text", "currentIndex", "索引号", ""),
    ("prior_amount", "D", "editable", "amount", "priorAmount", "上期数", ""),
    ("prior_index", "E", "editable", "text", "priorIndex", "索引号", ""),
    ("remark", "F", "editable", "text", "remark", "备注", ""),
)
# N5-2 数据区无逐行公式（B10=B9*25% 是特殊单格公式，不是行模板）
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {}
FORMULA_COLUMNS: Final[tuple[str, ...]] = ()

SPEC_N52: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET, sheet_key=SHEET_KEY, table_key=ROWS_TABLE_KEY,
    template_id=TEMPLATE_ID, table_name=TABLE_NAME, uuid_col=UUID_COL,
    first_data_row=FIRST_DATA_ROW, last_data_row=LAST_DATA_ROW, footer_row=FOOTER_ROW,
    header_row=HEADER_ROW,
    store_item_id=STORE_ITEM_ID, empty_payload=EMPTY_STORE_PAYLOAD,
    row_identity_key=ROW_IDENTITY_STORE_KEY, store_kind=StoreKind.rows,
    field_specs=MANAGED_FIELD_SPECS_7, formula_columns=FORMULA_COLUMNS,
    formula_templates=FORMULA_TEMPLATES,
    footer_marker=FOOTER_MARKER, footer_carries_total_formula=True,
    footer_search_column=FOOTER_SEARCH_COLUMN,
    error_label="N5-2 所得税费用明细表", ghost_row_anchor_index=0,
)
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _engine_managed_field_specs(SPEC_N52))
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_N52.formula_mask
_HTML_STORE_NOTE: Final[str] = "N5-2 明细表存成 N5-2-rows 的 conclusion（JSON 数组）。"
_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 N5 所得税费用.xlsx 的 所得税费用明细表N5-2：单级表头 R8，"
    "6列 A-F，数据区 R9-R20（12行），零逐行公式列（B10=B9*25%是单格特殊公式不是行模板）。"
    "R21 合计 SUM。审定表 N5-1 全公式。"
)
