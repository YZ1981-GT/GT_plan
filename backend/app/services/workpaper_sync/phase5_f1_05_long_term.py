# -*- coding: utf-8 -*-
"""F1-5「长期挂款检查表」—— sheet 层薄声明。

spec: f1-sync-coverage-and-first-canary · Task 13

═══ 几何（openpyxl 逐格实测）═══

单级表头 R5 · 数据区 R6-14（9 行）· footer R15「合计」
数据区**零公式**（J 列审定余额在模板中无公式）。

═══ FC-7 派生列裁决 ═══

J 列「审定余额」：模板无公式，前端 `recalcLongTermRow` 自动派生
`auditedBalance = endBalance − badDebtProvision`（useF1LongTerm.ts:55-62）。

裁决：`auto_source`（默认①，FC-7）—— OO 改 J 后 forcesave → 受保护字段冲突，
不合并（`contracts.PROTECTED_MODES` 覆盖）。用户在 OO 侧无法改这列。

如果选②（注入模板公式 `=B{r}-I{r}`），需走模板覆盖层改权威模板字节（代价高）。
默认①不改模板。

⇒ J 列 mode = `auto_source`（不是 `editable`，不是 `formula`）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F105",
    "MANAGED_SHEET_F105",
    "STORE_ITEM_ID_F105",
]

MANAGED_SHEET_F105: Final[str] = "长期挂款检查表F1-5"
TEMPLATE_ID_F105: Final[str] = "F15"
SHEET_KEY_F105: Final[str] = "f15-managed"
ROWS_TABLE_KEY_F105: Final[str] = "long_term_rows"
STORE_ITEM_ID_F105: Final[str] = "F1-lt-rows"
ROW_IDENTITY_STORE_KEY_F105: Final[str] = "rowId"

HEADER_ROW_F105: Final[int] = 5
FIRST_DATA_ROW_F105: Final[int] = 6
LAST_DATA_ROW_F105: Final[int] = 14
FOOTER_ROW_F105: Final[int] = 15
FOOTER_MARKER_F105: Final[str] = "合计"
UUID_COL_F105: Final[str] = "N"


#: 13 个受管字段。键名取自 useF1LongTerm.LongTermRow。
#: J 列 mode=auto_source（FC-7 派生列：模板无公式，前端自动派生，OO 改动不合并）。
#: B/I/K 列 footer SUM 有公式，但数据区无公式 ⇒ formula_columns 为空。
FIELD_SPECS_F105: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("customer_name", "A", "editable", "text", "customerName", "债权人名称", ""),
    ("end_balance", "B", "editable", "amount", "endBalance", "期末余额", ""),
    ("nature", "C", "editable", "text", "nature", "款项性质", ""),
    ("contract_date", "D", "editable", "text", "contractDate", "合同/协议签订日", ""),
    ("aging_description", "E", "editable", "text", "agingDescription", "账龄", ""),
    ("reason", "F", "editable", "text", "reason", "未及时结算原因", ""),
    ("recoverability", "G", "editable", "text", "recoverability", "可收回性评价", ""),
    ("evidence", "H", "editable", "text", "evidence", "支持性证据", ""),
    ("bad_debt_provision", "I", "editable", "amount", "badDebtProvision", "坏账准备", ""),
    ("audited_balance", "J", "auto_source", "amount", "auditedBalance", "审定余额", ""),
    ("post_period", "K", "editable", "amount", "postPeriodSettlement", "期后结算", ""),
    ("index_ref", "L", "editable", "text", "indexRef", "索引号", ""),
    ("remark", "M", "editable", "text", "remark", "备注", ""),
)

SPEC_F105: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F105,
    sheet_key=SHEET_KEY_F105,
    table_key=ROWS_TABLE_KEY_F105,
    template_id=TEMPLATE_ID_F105,
    table_name=f"GT_{TEMPLATE_ID_F105}_ROWS",
    uuid_col=UUID_COL_F105,
    first_data_row=FIRST_DATA_ROW_F105,
    last_data_row=LAST_DATA_ROW_F105,
    footer_row=FOOTER_ROW_F105,
    header_row=HEADER_ROW_F105,
    store_item_id=STORE_ITEM_ID_F105,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F105,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F105,
    formula_columns=(),  # 数据区零公式（J 列是 auto_source）
    footer_marker=FOOTER_MARKER_F105,
    error_label="F1-5 长期挂款检查表",
)
