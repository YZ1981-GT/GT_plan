# -*- coding: utf-8 -*-
"""N3 递延所得税负债 —— 受管 sheet 层声明。

受管 sheet = `递延所得税负债明细表N3-2`（openpyxl 逐格实测，净化后复算）：**两级表头** R9/R10、
14 列 A-N、数据区 R11-R21（11 行固定项）、footer R23（R22 空行）。

四个公式列逐行：E=ROUND(C*D,2) / H=F+O{n}（引用隐藏列） / K=ROUND(I*J,2) / N=L+K。
🔴 H 列引用隐藏列 O（外部链接关联），N 列只取 L+K（缺 M），均为模板既知缺陷，记录型锁定。
🔴 Footer E23=SUM(E3:O22) 越界，记录型锁定。

模板已净化（删 3 外链部件，留 `.preclean.bak`）。
"""
from __future__ import annotations

from typing import Any, Final, Mapping

from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (
    managed_field_specs as _engine_managed_field_specs,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "n_cycle_deferred_tax_liabilities"
ENTRY_ID: Final[str] = "xlsx/gt-n3-deferred-tax-liabilities"
ADAPTER_ID: Final[str] = "n3.deferred_tax_liabilities"
WP_CODES: Final[frozenset[str]] = frozenset({"N3D"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "N/N3 递延所得税负债.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "672addf15523e92b91bc8f9e581f313f8757d3fa3310ff8f02cc888803fa5633"
)
MANAGED_SHEET: Final[str] = "递延所得税负债明细表N3-2"
DERIVED_SHEET: Final[str] = "递延所得税负债审定表N3-1"
TEMPLATE_ID: Final[str] = "N32"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "deferred_tax_liability_detail_rows"

HEADER_ROW: Final[int] = 9
HEADER_LEAF_ROW: Final[int] = 10

FIRST_DATA_ROW: Final[int] = 11
LAST_DATA_ROW: Final[int] = 20  # R21 是「…………」占位行不是业务行
FOOTER_ROW: Final[int] = 23  # R22 空行，R23 合计

MANAGED_LAST_COL: Final[str] = "N"
UUID_COL: Final[str] = "O"

TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
FOOTER_MARKER: Final[str] = ""  # R23 A 列为空，无标签
FOOTER_SEARCH_COLUMN: Final[str] = "A"

STORE_ITEM_ID: Final[str] = "N3-2-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "id"

HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = (
    "index",
    "taxableDiff",
    "endDtl",
    "isSpecialNonRecognition",
    "isReversed",
)

# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管字段（14 列 7 元组）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_FIELD_SPECS_7: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("item_name", "A", "editable", "text", "itemName", "项  目", ""),
    ("category", "B", "editable", "text", "category", "分类", ""),
    ("prior_temp_diff", "C", "editable", "amount", "priorTempDiff", "暂时性差异", "C9"),
    ("prior_tax_rate", "D", "editable", "rate", "taxRate", "适用税率", "C9"),
    ("prior_dtl_balance", "E", "formula", "amount", "priorDtlBalance", "递延所得税负债期初余额", "C9"),
    ("prior_aje", "F", "editable", "amount", "priorAje", "账项调整", "C9"),
    ("prior_rje", "G", "editable", "amount", "priorRje", "重分类调整", "C9"),
    ("prior_audited", "H", "formula", "amount", "priorAudited", "递延所得税资产期初审定数", "C9"),
    ("current_temp_diff", "I", "editable", "amount", "currentTempDiff", "暂时性差异", "I9"),
    ("current_tax_rate", "J", "editable", "rate", "currentTaxRate", "适用税率", "I9"),
    ("current_dtl_balance", "K", "formula", "amount", "currentDtlBalance", "递延所得税负债期末余额", "I9"),
    ("current_aje", "L", "editable", "amount", "currentAje", "账项调整", "I9"),
    ("current_rje", "M", "editable", "amount", "currentRje", "重分类调整", "I9"),
    ("current_audited", "N", "formula", "amount", "currentAudited", "递延所得税负债期末审定数", "I9"),
)

FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "E": "=ROUND(C{row}*D{row},2)",
    "H": "=F{row}+E{row}+G{row}",  # 🔴 模板真实公式 =F+O{n}（引用隐藏列），这里用正确形态
    "K": "=ROUND(I{row}*J{row},2)",
    "N": "=L{row}+K{row}+M{row}",  # 🔴 模板真实公式 =L+K（缺 M），这里用正确形态
}
FORMULA_COLUMNS: Final[tuple[str, ...]] = tuple(FORMULA_TEMPLATES)

# ═══════════════════════════════════════════════════════════════════════════
# 3. 单一权威声明
# ═══════════════════════════════════════════════════════════════════════════

SPEC_N32: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET,
    sheet_key=SHEET_KEY,
    table_key=ROWS_TABLE_KEY,
    template_id=TEMPLATE_ID,
    table_name=TABLE_NAME,
    uuid_col=UUID_COL,
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    header_row=HEADER_ROW,
    header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID,
    empty_payload=EMPTY_STORE_PAYLOAD,
    row_identity_key=ROW_IDENTITY_STORE_KEY,
    store_kind=StoreKind.rows,
    field_specs=MANAGED_FIELD_SPECS_7,
    formula_columns=FORMULA_COLUMNS,
    formula_templates=FORMULA_TEMPLATES,
    footer_marker="",  # R23 A 列无标签
    footer_carries_total_formula=True,  # R23 有 SUM 公式但无标签
    footer_search_column=FOOTER_SEARCH_COLUMN,
    error_label="N3-2 递延所得税负债明细表",
    ghost_row_anchor_index=0,
)

MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _engine_managed_field_specs(SPEC_N32)
)
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_N32.formula_mask

_HTML_STORE_NOTE: Final[str] = (
    "N3-2 明细表存成 `N3-2-rows` 的 conclusion（JSON 数组，useN3Detail 的 rows）。"
    "行身份是熵键 id（`row-${Date.now()}-${random}`）。前端 N3DetailRow 的 "
    "taxableDiff/endDtl/isSpecialNonRecognition/isReversed/index 是 computed，不入契约。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测权威模板 N/N3 递延所得税负债.xlsx（6 sheet，净化后 sha256 abd34241）"
    "的受管 sheet 递延所得税负债明细表N3-2：两级表头 R9/R10，14 列 A-N，数据区 R11-R21"
    "（11 行固定项），R22 空行，R23 合计=SUM。四个公式列 E=ROUND(C*D,2) / H=F+O "
    "/ K=ROUND(I*J,2) / N=L+K。Editable 10 列 A/B/C/D/F/G/I/J/L/M。"
    "🔴 H 列引用隐藏列 O（外链），N 列缺 M，E23 SUM 越界——均为模板既知缺陷，记录型锁定。"
    "审定表 N3-1 r7-r13 全公式（SUMIF 引明细表），一格不写。"
)
