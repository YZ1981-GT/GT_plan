# -*- coding: utf-8 -*-
"""D6-3「合同资产减值准备明细表」—— sheet 层薄声明。

spec: d567-sync-coverage-via-row-table-engine · Task 9 · Requirements 2.1

几何（openpyxl 直读 2026-09-26）：29r × 14c(N) / 63f。
双分类行：按单项评估(R12-R16 data, R17 小计) + 信用风险组合(R18-R21 data, R22 合计)。
🔴 store_item_id = D6-3-rows（全库单条 JSON 数组，含 category 字段区分 single/group）。
aging_layout=flat（D6 全家 flat 键）。
"""
from __future__ import annotations
from typing import Final
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

__all__ = ["SPEC_D603", "MANAGED_SHEET_D603", "STORE_ITEM_ID_D603"]

MANAGED_SHEET_D603: Final[str] = "合同资产减值准备明细表D6-3"
TEMPLATE_ID_D603: Final[str] = "D63"
SHEET_KEY_D603: Final[str] = "d63-managed"
ROWS_TABLE_KEY_D603: Final[str] = "impairment_detail_rows"
STORE_ITEM_ID_D603: Final[str] = "D6-3-rows"
ROW_IDENTITY_STORE_KEY_D603: Final[str] = "rowId"

HEADER_ROW_D603: Final[int] = 11
FIRST_DATA_ROW_D603: Final[int] = 13  # R12 是小计行（SUM 公式），数据区从 R13 开始
LAST_DATA_ROW_D603: Final[int] = 16  # R17 是组合评估小计行（SUM），R18-R21 是组合评估数据区——当前只覆盖个别评估（R13-R16），组合评估待双区改造
FOOTER_ROW_D603: Final[int] = 22
FOOTER_MARKER_D603: Final[str] = "合计"
MANAGED_LAST_COL_D603: Final[str] = "N"
UUID_COL_D603: Final[str] = "O"

#: 14 列受管字段。E(priorAudited)=C+D formula / K(endUnadjusted)=F+G+H-I-J formula / N(endAudited)=K+L+M formula。
FIELD_SPECS_D603: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("category", "B", "editable", "text", "category", "分类", ""),
    ("prior_unadjusted", "C", "editable", "amount", "priorUnadjusted", "未审数", ""),
    ("prior_aje", "D", "editable", "amount", "priorAje", "账项调整", ""),
    ("prior_audited", "E", "formula", "amount", "priorAudited", "审定数", ""),
    ("provision", "F", "editable", "amount", "provision", "计提", ""),
    ("other_increase", "G", "editable", "amount", "otherIncrease", "其他增加", ""),
    ("reversal", "H", "editable", "amount", "reversal", "转回", ""),
    ("write_off", "I", "editable", "amount", "writeOff", "核销", ""),
    ("other_decrease", "J", "editable", "amount", "otherDecrease", "其他减少", ""),
    ("end_unadjusted", "K", "formula", "amount", "endUnadjusted", "期末未审数", ""),
    ("end_aje", "L", "editable", "amount", "endAje", "账项调整", ""),
    ("end_rje", "M", "editable", "amount", "endRje", "重分类调整", ""),
    ("end_audited", "N", "formula", "amount", "endAudited", "审定数", ""),
)

SPEC_D603: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D603,
    sheet_key=SHEET_KEY_D603,
    table_key=ROWS_TABLE_KEY_D603,
    template_id=TEMPLATE_ID_D603,
    table_name=f"GT_{TEMPLATE_ID_D603}_ROWS",
    uuid_col=UUID_COL_D603,
    first_data_row=FIRST_DATA_ROW_D603,
    last_data_row=LAST_DATA_ROW_D603,
    footer_row=FOOTER_ROW_D603,
    header_row=HEADER_ROW_D603,
    store_item_id=STORE_ITEM_ID_D603,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_D603,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D603,
    formula_columns=("E", "K", "N"),
    aging_layout=None,  # D6-3 本身无账龄组（明细表级别，不同于 D6-2）
    footer_marker=FOOTER_MARKER_D603,
    error_label="D6-3 减值准备明细表",
)
