# -*- coding: utf-8 -*-
"""D1-9「应收票据贴息检查表」—— sheet 层薄声明（单区）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 28 · Requirements 5.1

═══ 几何（openpyxl 直读实测，2026-09-26）═══

单级表头 R10（13 列 A-M）。数据区 R11-R17（7 行）。footer R18 `合计`（[5408 8ba1]）。
🔴 **数据区有行级公式**：H=E-G（贴息天数）/ J=I/365*H*B（应计利息）/ L=J-K（差异）——
引擎把这些列声明为 `formula`，materialize 不覆盖公式格、由 OO 重算。
前端 `useD1InterestCheck.ts` 的 `discountDays`/`calculatedInterest`/`difference` 标注为
"自动计算，只读派生"，与 `formula` mode 语义一致。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = ["SPEC_D109", "MANAGED_SHEET_D109"]

MANAGED_SHEET_D109: Final[str] = "应收票据贴息检查表D1-9"
TEMPLATE_ID_D109: Final[str] = "D19"
SHEET_KEY_D109: Final[str] = f"{TEMPLATE_ID_D109.lower()}-managed"

FOOTER_MARKER_D109: Final[str] = "合计"  # [5408 8ba1]

_FIELD_SPECS_D109: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("note_type", "A", "editable", "text", "noteType", "票据类型", ""),
    ("face_value", "B", "editable", "amount", "faceValue", "票面金额", ""),
    ("face_rate", "C", "editable", "amount", "faceRate", "票面利率", ""),
    ("issue_date", "D", "editable", "text", "issueDate", "出票日期", ""),
    ("maturity_date", "E", "editable", "text", "maturityDate", "票据到期日", ""),
    ("maturity_value", "F", "editable", "amount", "maturityValue", "到期日票据价值", ""),
    ("discount_date", "G", "editable", "text", "discountDate", "贴现日期", ""),
    ("discount_days", "H", "formula", "amount", "discountDays", "贴息天数", ""),
    ("discount_rate", "I", "editable", "amount", "discountRate", "贴现率", ""),
    ("calculated_interest", "J", "formula", "amount", "calculatedInterest", "应计贴现利息", ""),
    ("booked_interest", "K", "editable", "amount", "bookedInterest", "账面贴现利息", ""),
    ("difference", "L", "formula", "amount", "difference", "差异", ""),
    ("remark", "M", "editable", "text", "remark", "备注", ""),
)

_FORMULA_COLUMNS_D109: Final[tuple[str, ...]] = ("H", "J", "L")
_FORMULA_TEMPLATES_D109: Final[dict[str, str]] = {
    "H": "=E{r}-G{r}",
    "J": "=I{r}/365*H{r}*B{r}",
    "L": "=J{r}-K{r}",
}

SPEC_D109: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D109,
    sheet_key=SHEET_KEY_D109,
    table_key="interest_check_rows",
    template_id=TEMPLATE_ID_D109,
    table_name=f"GT_{TEMPLATE_ID_D109}_ROWS",
    uuid_col="N",  # max_col=M=13, 注入列 N
    first_data_row=11,
    last_data_row=17,
    footer_row=18,
    header_row=10,
    store_item_id="D1-interest-rows",
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_D109,
    formula_columns=_FORMULA_COLUMNS_D109,
    formula_templates=_FORMULA_TEMPLATES_D109,
    footer_marker=FOOTER_MARKER_D109,
    error_label="D1-9 贴息检查",
)
