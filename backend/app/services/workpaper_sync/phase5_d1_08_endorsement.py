# -*- coding: utf-8 -*-
"""D1-8「应收票据贴现、票据已背书未到期明细表」—— sheet 层薄声明（**双区**）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 27 · Requirements 5.1 / 5.4

═══ 几何（openpyxl 直读实测，2026-09-26）═══

| 区 | 标题 | 表头 | 数据行 | footer | 公式列 | store 键 | UUID 列 |
|---|---|---|---|---|---|---|---|
| 贴现 | R11（一） | R12-13（两级，合并） | R14-R21 (8行) | R22 `合计` | E/F/L/M SUM | `D1-endorse-discount-rows` | Q |
| 背书 | R23（二） | R24-25（两级，合并） | R26-R33 (8行) | R34 `合计` | E SUM | `D1-endorse-transfer-rows` | R |

两区共 managed_sheet 与 sheet_key（同 D1-4 / D4-9 先例），各自独立 UUID 列（Q/R，max_col=P=16
故注入列从 Q 起不冲突）。四区 footer marker 逐字相同 `合计`（codepoints 5408 8ba1）。

两区列集不完全相同：区一有贴现银行/贴现金额/贴现息（K/L/M），区二替换为背书转让单位/
背书转让日期/说明（K/L/M）——列字母相同但语义不同。前端 `EndorsementRow` 接口把两套字段
合并进一个 union（贴现行的 `discountBank`/`discountAmount`/`discountInterest` 与背书行的
`endorsedTo`/`endorsedDate`/`description` 各用各的字段名，不冲突），但 store 是分开的
两个键，materialize 按各自的 field_specs 独立处理。

🔴 数据区内零公式（全 editable），公式只在 footer 的 SUM。
🔴 两区 `row_identity_key = "rowId"`（与 D1-3/D1-4 相同，非 D1-16 的 `"id"`）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_D108_DISCOUNT",
    "SPEC_D108_TRANSFER",
    "SPECS_D108",
    "MANAGED_SHEET_D108",
]

MANAGED_SHEET_D108: Final[str] = "应收票据贴现、票据已背书未到期明细表D1-8"
TEMPLATE_ID_D108: Final[str] = "D18"
SHEET_KEY_D108: Final[str] = f"{TEMPLATE_ID_D108.lower()}-managed"

#: 两级表头（区一 R12 组/R13 叶，区二 R24 组/R25 叶；区二 group_header_cell 对齐区二表头行）。
HEADER_GROUP_ROW_DISCOUNT: Final[int] = 12
HEADER_LEAF_ROW_DISCOUNT: Final[int] = 13
HEADER_GROUP_ROW_TRANSFER: Final[int] = 24
HEADER_LEAF_ROW_TRANSFER: Final[int] = 25

FOOTER_ROW_DISCOUNT: Final[int] = 22
FOOTER_ROW_TRANSFER: Final[int] = 34
FOOTER_MARKER_D108: Final[str] = "合计"  # [5408 8ba1]

MANAGED_LAST_COL_D108: Final[str] = "P"

#: ──── 区一（贴现）field_specs（16 列 A-P，7 元组）────
#: 所有列均 editable/text 或 editable/amount，无数据区内公式。
_FIELD_SPECS_DISCOUNT: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("note_type", "A", "editable", "text", "noteType", "票据种类", ""),
    ("received_date", "B", "editable", "text", "receivedDate", "收到日期", ""),
    ("issuer", "C", "editable", "text", "issuer", "出票人全称", ""),
    ("note_number", "D", "editable", "text", "noteNumber", "票据号", ""),
    ("bill_amount", "E", "editable", "amount", "billAmount", "汇票金额", ""),
    ("accrued_interest", "F", "editable", "amount", "accruedInterest", "已计利息", ""),
    ("issue_date", "G", "editable", "text", "issueDate", "出票日期", ""),
    ("maturity_date", "H", "editable", "text", "maturityDate", "到期日", ""),
    ("acceptor_bank", "I", "editable", "text", "acceptorBank", "承兑银行", ""),
    ("credit_rating", "J", "editable", "text", "creditRating", "承兑单位信用等级", ""),
    ("discount_bank", "K", "editable", "text", "discountBank", "贴现银行", ""),
    ("discount_amount", "L", "editable", "amount", "discountAmount", "贴现金额", ""),
    ("discount_interest", "M", "editable", "amount", "discountInterest", "贴现息", ""),
    ("is_derecognized", "N", "editable", "text", "isDerecognized", "是否终止确认", ""),
    ("is_correct", "O", "editable", "text", "isCorrect", "会计处理是否正确", ""),
    ("index_ref", "P", "editable", "text", "indexRef", "索引号", ""),
)

#: ──── 区二（背书）field_specs（16 列 A-P）────
#: K/L/M 三列语义不同于区一（背书转让单位/日期/说明 vs 贴现银行/金额/息）。
_FIELD_SPECS_TRANSFER: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("note_type", "A", "editable", "text", "noteType", "票据种类", ""),
    ("received_date", "B", "editable", "text", "receivedDate", "收到日期", ""),
    ("issuer", "C", "editable", "text", "issuer", "出票人全称", ""),
    ("note_number", "D", "editable", "text", "noteNumber", "票据号", ""),
    ("bill_amount", "E", "editable", "amount", "billAmount", "汇票金额", ""),
    ("endorser", "F", "editable", "text", "endorser", "前手", ""),
    ("issue_date", "G", "editable", "text", "issueDate", "出票日期", ""),
    ("maturity_date", "H", "editable", "text", "maturityDate", "到期日", ""),
    ("acceptor_bank", "I", "editable", "text", "acceptorBank", "承兑银行", ""),
    ("credit_rating", "J", "editable", "text", "creditRating", "承兑单位信用等级", ""),
    ("endorsed_to", "K", "editable", "text", "endorsedTo", "背书转让单位", ""),
    ("endorsed_date", "L", "editable", "text", "endorsedDate", "背书转让日期", ""),
    ("description", "M", "editable", "text", "description", "说明", ""),
    ("is_derecognized", "N", "editable", "text", "isDerecognized", "是否终止确认", ""),
    ("is_correct", "O", "editable", "text", "isCorrect", "会计处理是否正确", ""),
    ("index_ref", "P", "editable", "text", "indexRef", "索引号", ""),
)

#: footer SUM 公式列（只在 footer 行，数据区内无公式 ⇒ formula_columns 仅供 formula_mask）。
_FORMULA_COLUMNS_DISCOUNT: Final[tuple[str, ...]] = ("E", "F", "L", "M")
_FORMULA_TEMPLATES_DISCOUNT: Final[dict[str, str]] = {
    "E": "=SUM(E14:E{r})", "F": "=SUM(F14:F{r})",
    "L": "=SUM(L14:L{r})", "M": "=SUM(M14:M{r})",
}

_FORMULA_COLUMNS_TRANSFER: Final[tuple[str, ...]] = ("E",)
_FORMULA_TEMPLATES_TRANSFER: Final[dict[str, str]] = {"E": "=SUM(E26:E{r})"}


SPEC_D108_DISCOUNT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D108,
    sheet_key=SHEET_KEY_D108,
    table_key="endorse_discount_rows",
    template_id=f"{TEMPLATE_ID_D108}DISCOUNT",
    table_name=f"GT_{TEMPLATE_ID_D108}_DISCOUNT_ROWS",
    uuid_col="Q",
    first_data_row=14,
    last_data_row=21,
    footer_row=FOOTER_ROW_DISCOUNT,
    header_group_row=HEADER_GROUP_ROW_DISCOUNT,
    header_leaf_row=HEADER_LEAF_ROW_DISCOUNT,
    store_item_id="D1-endorse-discount-rows",
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_DISCOUNT,
    formula_columns=_FORMULA_COLUMNS_DISCOUNT,
    formula_templates=_FORMULA_TEMPLATES_DISCOUNT,
    footer_marker=FOOTER_MARKER_D108,
    error_label="D1-8 贴现明细",
)

SPEC_D108_TRANSFER: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D108,
    sheet_key=SHEET_KEY_D108,
    table_key="endorse_transfer_rows",
    template_id=f"{TEMPLATE_ID_D108}TRANSFER",
    table_name=f"GT_{TEMPLATE_ID_D108}_TRANSFER_ROWS",
    uuid_col="R",
    first_data_row=26,
    last_data_row=33,
    footer_row=FOOTER_ROW_TRANSFER,
    header_group_row=HEADER_GROUP_ROW_TRANSFER,
    header_leaf_row=HEADER_LEAF_ROW_TRANSFER,
    store_item_id="D1-endorse-transfer-rows",
    empty_payload="[]",
    row_identity_key="rowId",
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_TRANSFER,
    formula_columns=_FORMULA_COLUMNS_TRANSFER,
    formula_templates=_FORMULA_TEMPLATES_TRANSFER,
    footer_marker=FOOTER_MARKER_D108,
    error_label="D1-8 背书明细",
)

SPECS_D108: Final[tuple[RowTableSheetSpec, ...]] = (
    SPEC_D108_DISCOUNT,
    SPEC_D108_TRANSFER,
)
