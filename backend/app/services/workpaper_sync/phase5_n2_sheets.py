# -*- coding: utf-8 -*-
"""N2 应交税费 — 受管 sheet 层声明。

受管 sheet = `应交税费明细表N2-2`：两级表头 R8/R9、17列 A-Q、
数据区 R10-R24（15行固定税种），R25 合计=SUM。
5个公式列 F/M/N/O/P 逐行。Q 列备注 editable。
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

PHASE5_WAVE: Final[str] = "n_cycle_taxes_payable"
ENTRY_ID: Final[str] = "xlsx/gt-n2-taxes-payable"
ADAPTER_ID: Final[str] = "n2.taxes_payable"
WP_CODES: Final[frozenset[str]] = frozenset({"N2T"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "N/N2 应交税费.xlsx"
TEMPLATE_SHA256: Final[str] = "fbc0e220073adbe2b74a9e36a628e6c4e8790662c55eda74f367e9a740ad11be"
MANAGED_SHEET: Final[str] = "应交税费明细表N2-2"
DERIVED_SHEET: Final[str] = "应交税费审定表N2-1"
TEMPLATE_ID: Final[str] = "N22"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "taxes_payable_detail_rows"
HEADER_ROW: Final[int] = 8
HEADER_LEAF_ROW: Final[int] = 9
FIRST_DATA_ROW: Final[int] = 10
LAST_DATA_ROW: Final[int] = 24
FOOTER_ROW: Final[int] = 25
MANAGED_LAST_COL: Final[str] = "Q"
UUID_COL: Final[str] = "R"
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
FOOTER_MARKER: Final[str] = "合计"
FOOTER_SEARCH_COLUMN: Final[str] = "A"
STORE_ITEM_ID: Final[str] = "N2-2-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "id"
HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = ()

MANAGED_FIELD_SPECS_7: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("tax_name", "A", "editable", "text", "taxName", "项目", ""),
    ("tax_rate", "B", "editable", "text", "taxRate", "税率或税收优惠", ""),
    ("prior_opening", "C", "editable", "amount", "priorOpening", "期初数", "C8"),
    ("prior_accrued", "D", "editable", "amount", "priorAccrued", "本期应交数", "C8"),
    ("prior_paid", "E", "editable", "amount", "priorPaid", "本期已交数", "C8"),
    ("prior_closing", "F", "formula", "amount", "priorClosing", "期末数", "C8"),
    ("adj_aje", "G", "editable", "amount", "adjAje", "账项调整", "G8"),
    ("adj_rje", "H", "editable", "amount", "adjRje", "重分类调整", "G8"),
    ("aje_accrued", "I", "editable", "amount", "ajeAccrued", "本期应交", "I8"),
    ("aje_paid", "J", "editable", "amount", "ajePaid", "本期已交", "I8"),
    ("rje_accrued", "K", "editable", "amount", "rjeAccrued", "本期应交", "K8"),
    ("rje_paid", "L", "editable", "amount", "rjePaid", "本期已交", "K8"),
    ("audited_opening", "M", "formula", "amount", "auditedOpening", "期初数", "M8"),
    ("audited_accrued", "N", "formula", "amount", "auditedAccrued", "本期应交数", "M8"),
    ("audited_paid", "O", "formula", "amount", "auditedPaid", "本期已交数", "M8"),
    ("audited_closing", "P", "formula", "amount", "auditedClosing", "期末数", "M8"),
    ("remark", "Q", "editable", "text", "remark", "备注", ""),
)
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "F": "=C{row}+D{row}-E{row}",
    "M": "=C{row}+G{row}+H{row}",
    "N": "=D{row}+I{row}+K{row}",
    "O": "=E{row}+J{row}+L{row}",
    "P": "=M{row}+N{row}-O{row}",
}
FORMULA_COLUMNS: Final[tuple[str, ...]] = tuple(FORMULA_TEMPLATES)

SPEC_N22: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET, sheet_key=SHEET_KEY, table_key=ROWS_TABLE_KEY,
    template_id=TEMPLATE_ID, table_name=TABLE_NAME, uuid_col=UUID_COL,
    first_data_row=FIRST_DATA_ROW, last_data_row=LAST_DATA_ROW, footer_row=FOOTER_ROW,
    header_row=HEADER_ROW, header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID, empty_payload=EMPTY_STORE_PAYLOAD,
    row_identity_key=ROW_IDENTITY_STORE_KEY, store_kind=StoreKind.rows,
    field_specs=MANAGED_FIELD_SPECS_7, formula_columns=FORMULA_COLUMNS,
    formula_templates=FORMULA_TEMPLATES,
    footer_marker=FOOTER_MARKER, footer_carries_total_formula=True,
    footer_search_column=FOOTER_SEARCH_COLUMN,
    error_label="N2-2 应交税费明细表", ghost_row_anchor_index=0,
)
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _engine_managed_field_specs(SPEC_N22))
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_N22.formula_mask
_HTML_STORE_NOTE: Final[str] = "N2-2 明细表存成 N2-2-rows 的 conclusion（JSON 数组）。15行固定税种。"
_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 N2 应交税费.xlsx 的 应交税费明细表N2-2：两级表头 R8/R9，"
    "17列 A-Q，数据区 R10-R24（15行），5公式列 F/M/N/O/P。R25 合计 SUM。"
    "审定表 N2-1 全公式。"
)
