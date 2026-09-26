# -*- coding: utf-8 -*-
"""D1-12「应收票据质押情况检查表」—— sheet 层薄声明（单区）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 28 · Requirements 5.1

═══ 几何（openpyxl 直读实测，2026-09-26）═══

单级表头 R11（16 列 A-P）。数据区 R12-R17（6 行）。footer R18 `合计`（[5408 8ba1]）。
🔴 数据区**无行级公式**（全 editable）。公式仅在 footer H18/J18 = SUM。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = ["SPEC_D112", "MANAGED_SHEET_D112"]

MANAGED_SHEET_D112: Final[str] = "应收票据质押检查表D1-12"
TEMPLATE_ID_D112: Final[str] = "D112"
SHEET_KEY_D112: Final[str] = f"{TEMPLATE_ID_D112.lower()}-managed"

FOOTER_MARKER_D112: Final[str] = "合计"  # [5408 8ba1]

_FIELD_SPECS_D112: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("note_type", "A", "editable", "text", "noteType", "票据类型", ""),
    ("note_no", "B", "editable", "text", "noteNo", "票据号码", ""),
    ("receive_date", "C", "editable", "text", "receiveDate", "收到票据日期", ""),
    ("predecessor", "D", "editable", "text", "predecessor", "票据前手名称", ""),
    ("issue_date", "E", "editable", "text", "issueDate", "出票日期", ""),
    ("drawer", "F", "editable", "text", "drawer", "出票人名称", ""),
    ("acceptor", "G", "editable", "text", "acceptor", "承兑人名称", ""),
    ("note_amount", "H", "editable", "amount", "noteAmount", "票据金额", ""),
    ("maturity_date", "I", "editable", "text", "maturityDate", "票据到期日", ""),
    ("pledge_amount", "J", "editable", "amount", "pledgeAmount", "质押金额", ""),
    ("pledgee", "K", "editable", "text", "pledgee", "质权人", ""),
    ("pledge_reason", "L", "editable", "text", "pledgeReason", "质押原因", ""),
    ("pledge_condition", "M", "editable", "text", "pledgeCondition", "质押条件", ""),
    ("pledge_period", "N", "editable", "text", "pledgePeriod", "质押期限", ""),
    ("pledge_agreement", "O", "editable", "text", "pledgeAgreement", "质押协议", ""),
    ("index_ref", "P", "editable", "text", "indexRef", "索引号", ""),
)

_FORMULA_COLUMNS_D112: Final[tuple[str, ...]] = ("H", "J")
_FORMULA_TEMPLATES_D112: Final[dict[str, str]] = {
    "H": "=SUM(H12:H{r})",
    "J": "=SUM(J12:J{r})",
}

SPEC_D112: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D112,
    sheet_key=SHEET_KEY_D112,
    table_key="pledge_check_rows",
    template_id=TEMPLATE_ID_D112,
    table_name=f"GT_{TEMPLATE_ID_D112}_ROWS",
    uuid_col="Q",  # max_col=P=16, 注入列 Q
    first_data_row=12,
    last_data_row=17,
    footer_row=18,
    header_row=11,
    store_item_id="D1-pledge-rows",
    empty_payload="[]",
    row_identity_key="id",  # 🔴 前端用 `id`（与 D1-11/D1-16 一致）
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_D112,
    formula_columns=_FORMULA_COLUMNS_D112,
    formula_templates=_FORMULA_TEMPLATES_D112,
    footer_marker=FOOTER_MARKER_D112,
    error_label="D1-12 质押检查",
)
