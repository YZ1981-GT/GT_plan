# -*- coding: utf-8 -*-
"""E1-10「已开立银行账户清单核对表」—— 动态行表（**不是** static_region）+ OCR 冲突源。

spec: e1-sync-coverage-and-first-canary · Task 17 · Requirements 2.1 / 2.5 / 2.6
形态证据: docs/operations/evidence/e1-sync-coverage/e1-form-verdicts.json

═══ 🔴 为什么它是动态行表（三元组实证，不是公式数推演）═══

| 维度 | 实测 |
|---|---|
| store 键 | ✅ `E1-account-list-rows`（useE1AccountList.ts:57） |
| addRow/removeRow | ✅ 两者齐备（:170 / :176） |
| composable 归属 | ✅ `useE1AccountList` 专属 |

⇒ `binding_kind = excel_table`（动态行表）。
   🔴 spec 首版按「只 7 公式」把本张判成 `static_region`，实证推翻。

═══ 三向联动 ═══

`useE1AccountList`(340) 另读 `E1-bank-detail-rows`（跨 sheet 取 E1-3 账户清单）
与 `E1-account-commit-snapshot`（与 E1-11 联动）⇒ 回写后须断言这两个下游正确重算。

═══ OCR 第二写入方（spec E1-P16）═══

OCR 提及 ×43，与 E1-11（同 43 次）**成对出现**。
`E1AccountListOcrConfirmDialog` 对 `E1-account-list-rows` 是**整表替换**语义。
受管后 OCR 确认入口在 OO 编辑态下须 `disabled` + 中文原因。

═══ 几何（openpyxl 逐格实测）═══

37r×12c / 7 公式（全是底稿目录引用，数据区内无公式）。
R11 双级表头（组标题 + 已开立银行结算账户清单 + 开户原因/销户原因/核对/不一致原因）
R12 叶子（开户银行名称/账号/账户性质/账户状态/开户日期/销户日期）
数据区 R13-15（R13=1 / R14=2 / R15=「……」）
R24 审计说明 / R27 审计结论 —— 无 footer 合计行。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_E110",
    "MANAGED_SHEET_E110",
    "STORE_ITEM_ID_E110",
    "CROSS_SHEET_KEYS_E110",
    "OCR_DIALOG_COMPONENTS_E110",
]

MANAGED_SHEET_E110: Final[str] = "已开立银行账户清单核对表E1-10"
TEMPLATE_ID_E110: Final[str] = "E110"
SHEET_KEY_E110: Final[str] = f"{TEMPLATE_ID_E110.lower()}-managed"
ROWS_TABLE_KEY_E110: Final[str] = "account_list_rows"

#: 🔴 按值 grep 实测（useE1AccountList.ts:57）。
STORE_ITEM_ID_E110: Final[str] = "E1-account-list-rows"

#: 行身份键 —— E1 全族统一用 `id`。
ROW_IDENTITY_STORE_KEY_E110: Final[str] = "id"

#: 三向联动的跨 sheet 键。
CROSS_SHEET_KEYS_E110: Final[tuple[str, ...]] = (
    "E1-bank-detail-rows",         # 跨 sheet 取 E1-3 银行账户清单
    "E1-account-commit-snapshot",  # 与 E1-11 联动（由 E1-10 写入）
)

#: 🔴 OCR 确认弹窗组件（提及 43 次，与 E1-11 成对）。
OCR_DIALOG_COMPONENTS_E110: Final[tuple[str, ...]] = (
    "E1AccountListOcrConfirmDialog",
)

HEADER_GROUP_ROW_E110: Final[int] = 11
HEADER_LEAF_ROW_E110: Final[int] = 12
FIRST_DATA_ROW_E110: Final[int] = 13
LAST_DATA_ROW_E110: Final[int] = 15
FOOTER_ROW_E110: Final[int] = 24
FOOTER_MARKER_E110: Final[str] = "三、审计说明"
MANAGED_LAST_COL_E110: Final[str] = "K"
UUID_COL_E110: Final[str] = "L"

#: 受管字段（7 元组）。
#: 🔴 数据区内零公式（7 个公式全是底稿目录引用 R3/R4），全部 editable。
FIELD_SPECS_E110: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("seq_no", "A", "editable", "integer", "seqNo", "序号", ""),
    ("bank_name", "B", "editable", "text", "bankName", "开户银行名称", ""),
    ("account_no", "C", "editable", "text", "accountNo", "账号", ""),
    ("account_type", "D", "editable", "text", "accountType", "账户性质", ""),
    ("account_status", "E", "editable", "text", "accountStatus", "账户状态", ""),
    ("open_date", "F", "editable", "text", "openDate", "开户日期", ""),
    ("close_date", "G", "editable", "text", "closeDate", "销户日期", ""),
    ("open_reason", "H", "editable", "text", "openReason", "开户原因", ""),
    ("close_reason", "I", "editable", "text", "closeReason", "销户原因", ""),
    ("check_consistent", "J", "editable", "text", "checkConsistent", "与企业信息核对一致", ""),
    ("inconsistency_reason", "K", "editable", "text", "inconsistencyReason", "不一致原因", ""),
)

FORMULA_TEMPLATES_E110: Final[dict[str, str]] = {}

SPEC_E110: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_E110,
    sheet_key=SHEET_KEY_E110,
    table_key=ROWS_TABLE_KEY_E110,
    template_id=TEMPLATE_ID_E110,
    table_name=f"GT_{TEMPLATE_ID_E110}_ROWS",
    uuid_col=UUID_COL_E110,
    first_data_row=FIRST_DATA_ROW_E110,
    last_data_row=LAST_DATA_ROW_E110,
    footer_row=FOOTER_ROW_E110,
    header_group_row=HEADER_GROUP_ROW_E110,
    header_leaf_row=HEADER_LEAF_ROW_E110,
    store_item_id=STORE_ITEM_ID_E110,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_E110,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_E110,
    formula_columns=(),
    formula_templates=FORMULA_TEMPLATES_E110,
    footer_marker=FOOTER_MARKER_E110,
    error_label="E1-10 已开立银行账户清单核对表",
)
