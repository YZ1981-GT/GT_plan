# -*- coding: utf-8 -*-
"""N1 递延所得税资产 — 受管 sheet 层声明。

受管 sheet = `递延所得税资产明细表N1-2`：两级表头 R9/R10、14列 A-N、
数据区 R11-R29（19行固定项）、无 footer 标签行（R30+ 是说明区）。
公式列 E=ROUND(C*D,2) / H=F+E / K=ROUND(I*J,2) / N=L+K。
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

PHASE5_WAVE: Final[str] = "n_cycle_deferred_tax_assets"
ENTRY_ID: Final[str] = "xlsx/gt-n1-deferred-tax-assets"
ADAPTER_ID: Final[str] = "n1.deferred_tax_assets"
WP_CODES: Final[frozenset[str]] = frozenset({"N1D"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "N/N1 递延所得税资产.xlsx"
TEMPLATE_SHA256: Final[str] = "25cefe2f4e1d8cbb47b6b54b4ac5cd50f9f34016962aa2f8ec0dad16d449dea3"
MANAGED_SHEET: Final[str] = "递延所得税资产明细表N1-2"
DERIVED_SHEET: Final[str] = "递延所得税资产审定表N1-1"
TEMPLATE_ID: Final[str] = "N12"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "deferred_tax_asset_detail_rows"
HEADER_ROW: Final[int] = 9
HEADER_LEAF_ROW: Final[int] = 10
FIRST_DATA_ROW: Final[int] = 11
LAST_DATA_ROW: Final[int] = 29
FOOTER_ROW: Final[int] = 31
MANAGED_LAST_COL: Final[str] = "N"
UUID_COL: Final[str] = "O"
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
FOOTER_MARKER: Final[str] = ""
FOOTER_SEARCH_COLUMN: Final[str] = "A"
STORE_ITEM_ID: Final[str] = "N1-2-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "id"
HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = ("index", "deductibleDiff", "endDta", "isReversed",)

MANAGED_FIELD_SPECS_7: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项  目", ""),
    ("category", "B", "editable", "text", "category", "类别", ""),
    ("prior_temp_diff", "C", "editable", "amount", "priorTempDiff", "暂时性差异", "C9"),
    ("prior_tax_rate", "D", "editable", "rate", "taxRate", "适用税率", "C9"),
    ("prior_dta_balance", "E", "formula", "amount", "priorDtaBalance", "递延所得税资产期初余额", "C9"),
    ("prior_aje", "F", "editable", "amount", "priorAje", "账项调整", "C9"),
    ("prior_rje", "G", "editable", "amount", "priorRje", "重分类调整", "C9"),
    ("prior_audited", "H", "formula", "amount", "priorAudited", "递延所得税资产期初审定数", "C9"),
    ("current_temp_diff", "I", "editable", "amount", "currentTempDiff", "暂时性差异", "I9"),
    ("current_tax_rate", "J", "editable", "rate", "currentTaxRate", "适用税率", "I9"),
    ("current_dta_balance", "K", "formula", "amount", "currentDtaBalance", "递延所得税资产期末余额", "I9"),
    ("current_aje", "L", "editable", "amount", "currentAje", "账项调整", "I9"),
    ("current_rje", "M", "editable", "amount", "currentRje", "重分类调整", "I9"),
    ("current_audited", "N", "formula", "amount", "currentAudited", "递延所得税资产期末审定数", "I9"),
)
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "E": "=ROUND(C{row}*D{row},2)",
    "H": "=F{row}+E{row}",
    "K": "=ROUND(I{row}*J{row},2)",
    "N": "=L{row}+K{row}",
}
FORMULA_COLUMNS: Final[tuple[str, ...]] = tuple(FORMULA_TEMPLATES)

SPEC_N12: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET, sheet_key=SHEET_KEY, table_key=ROWS_TABLE_KEY,
    template_id=TEMPLATE_ID, table_name=TABLE_NAME, uuid_col=UUID_COL,
    first_data_row=FIRST_DATA_ROW, last_data_row=LAST_DATA_ROW, footer_row=FOOTER_ROW,
    header_row=HEADER_ROW, header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID, empty_payload=EMPTY_STORE_PAYLOAD,
    row_identity_key=ROW_IDENTITY_STORE_KEY, store_kind=StoreKind.rows,
    field_specs=MANAGED_FIELD_SPECS_7, formula_columns=FORMULA_COLUMNS,
    formula_templates=FORMULA_TEMPLATES, footer_marker="",
    footer_carries_total_formula=False, footer_search_column=FOOTER_SEARCH_COLUMN,
    error_label="N1-2 递延所得税资产明细表", ghost_row_anchor_index=0,
)
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _engine_managed_field_specs(SPEC_N12))
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_N12.formula_mask
_HTML_STORE_NOTE: Final[str] = "N1-2 明细表存成 N1-2-rows 的 conclusion（JSON 数组）。"
_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 N1 递延所得税资产.xlsx 的 递延所得税资产明细表N1-2：两级表头 R9/R10，"
    "14列 A-N，数据区 R11-R29（19行），四公式列 E/H/K/N。审定表 N1-1 全公式一格不写。"
)
