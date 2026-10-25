# -*- coding: utf-8 -*-
"""D6-9「减值准备转回、核销检查表」—— 双区声明（区①转回 / 区②核销）。

spec: d567-sync-coverage-via-row-table-engine · Task 15 · Requirements 2.5

几何（openpyxl 直读 2026-09-26）：30r × 8c(H) / 10f。
区①（转回检查）：表头 R13，数据 R14-R16，footer R17「合  计」。
区②（核销检查）：表头 R19，数据 R20-R22，footer R23「合  计」。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

__all__ = ["SPEC_D609_REVERSAL", "SPEC_D609_WRITEOFF", "MANAGED_SHEET_D609"]

MANAGED_SHEET_D609: Final[str] = "减值准备转回、核销检查表D6-9"

# ─── 区① 转回检查 ────────────────────────────────────────────────────────

TEMPLATE_ID_D609_REV: Final[str] = "D69REV"
SHEET_KEY_D609: Final[str] = "d69-managed"
STORE_ITEM_ID_D609_REVERSAL: Final[str] = "D6-9-reversal-rows"

FIELD_SPECS_D609_REV: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "客户名称", ""),
    ("reason", "B", "editable", "text", "reason", "转回原因", ""),
    ("recovery_method", "C", "editable", "text", "recoveryMethod", "收回方式", ""),
    ("original_basis", "D", "editable", "text", "originalBasis", "原计提依据", ""),
    ("reversal_amount", "E", "editable", "amount", "reversalAmount", "转回金额", ""),
    ("prior_provision", "F", "editable", "amount", "priorProvisionAmount", "原计提金额", ""),
    ("reasonability", "G", "editable", "text", "reasonabilityAnalysis", "合理性分析", ""),
    ("index_ref", "H", "editable", "text", "indexRef", "索引号", ""),
)

SPEC_D609_REVERSAL: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D609,
    sheet_key=SHEET_KEY_D609,
    table_key="reversal_rows",
    template_id=TEMPLATE_ID_D609_REV,
    table_name=f"GT_{TEMPLATE_ID_D609_REV}_ROWS",
    uuid_col="I",
    first_data_row=14,
    last_data_row=16,
    footer_row=17,
    header_row=13,
    store_item_id=STORE_ITEM_ID_D609_REVERSAL,
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D609_REV,
    formula_columns=(),
    aging_layout=None,
    footer_marker="合  计",  # 🔴 模板「合  计」含两空格
    error_label="D6-9 转回检查 区①",
)

# ─── 区② 核销检查 ────────────────────────────────────────────────────────

TEMPLATE_ID_D609_WO: Final[str] = "D69WO"
STORE_ITEM_ID_D609_WRITEOFF: Final[str] = "D6-9-writeoff-rows"

FIELD_SPECS_D609_WO: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "客户名称", ""),
    ("writeoff_amount", "B", "editable", "amount", "writeoffAmount", "核销金额", ""),
    ("writeoff_reason", "C", "editable", "text", "writeoffReason", "核销原因", ""),
    ("writeoff_procedure", "D", "editable", "text", "writeoffProcedure", "核销程序", ""),
    ("is_related_party", "E", "editable", "text", "isRelatedParty", "是否关联方", ""),
    ("reasonability", "F", "editable", "text", "reasonabilityAnalysis", "合理性分析", ""),
    ("index_ref", "G", "editable", "text", "indexRef", "索引号", ""),
    ("remark", "H", "editable", "text", "remark", "备注", ""),
)

SPEC_D609_WRITEOFF: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D609,
    sheet_key=SHEET_KEY_D609,
    table_key="writeoff_rows",
    template_id=TEMPLATE_ID_D609_WO,
    table_name=f"GT_{TEMPLATE_ID_D609_WO}_ROWS",
    uuid_col="J",  # 🔴 不同区不同 UUID 列
    first_data_row=20,
    last_data_row=22,
    footer_row=23,
    header_row=19,
    store_item_id=STORE_ITEM_ID_D609_WRITEOFF,
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D609_WO,
    formula_columns=(),
    aging_layout=None,
    footer_marker="合  计",
    error_label="D6-9 核销检查 区②",
)
