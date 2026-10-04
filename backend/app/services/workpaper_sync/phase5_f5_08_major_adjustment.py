# -*- coding: utf-8 -*-
"""F5-8「重大调整核查表」—— sheet 层薄声明（F5 首张 canary）。

spec: f5-sync-coverage-and-first-canary · Task 8 · Requirements 1.1 / 1.4 / 2.1
几何证据: .kiro/specs/f5-sync-coverage-and-first-canary/evidence/task2-morphology-and-geometry.md

═══ 为什么它排 F5 首张（裁决 F5-H1）═══

| 候选 | 数据区公式 | BP-7 | footer | 跨 sheet |
|---|---|---|---|---|
| F5-2 月度明细 | 5 列 | 🔴 有 | 有 | F5-1 引它 167 处 |
| F5-5 比较分析 | 8 列（含除零） | 🔴 有 | 有 | 0 |
| F5-3 其他业务 | 6 列 | 🔴 有 | 有 | F5-1 引 |
| **F5-8 重大调整** | **0** | **无** | 无（锚行） | 0 |

F5-8 同时验证两件事：从零 canary 链路（FC-1）与**无 footer 合计的锚行处置**（需求 1.4）——
后者在 F5 有两张（F5-7 / F5-8），先在最简的那张验通。

═══ 几何（openpyxl 逐格实测）═══

两级表头 **R12（组标题）/ R13（叶子）**，受管 8 列 A-H：

    A 日期(A12:A13)  B 凭证号(B12:B13)  C 重大调整事项内容(C12:C13)
    D-E 组「调整金额」(D12:E12)：D 借方 / E 贷方
    F 调整理由(F12:G13 —— 🔴 跨两行两列合并，G 被 F 吞掉，逐行亦有 F{r}:G{r} 合并)
    H 理由是否充分(H12:H13)

数据区 **R14-29**（16 行，逐行有 `F{r}:G{r}` 合并）· **无 footer 合计**。

🔴 **数据区零公式**：全表 7 个公式全在页眉 R3/R4（引「底稿目录」）⇒ `formula_columns=()`。

═══ 🔴 无 footer 合计的锚行处置（需求 1.4）═══

`footer_row` 指向数据区之后第一个非数据锚行 = **R30**，
`footer_carries_total_formula=False`（框架层 L152 支持，生产先例 D3-4 段②
`analysis_credit_rows` / marker「差异合理性分析」）。

🔴 **marker 逐字实测带全角冒号**：A30 = `'三、审计说明：'`。
spec Task 8 写的是 `footer_marker="三、审计说明"`（**无冒号**）——
`assert_footer_anchor_stable` 是逐字匹配，用 spec 的值会定位失败。本声明取**实测值**。

其后 A33 = `'四、审计结论：'` / A37 = `'提示：'` + R38/R39 两行编制提示，均在锚行之下，
属 HTML-only 区，不进 `field_specs`。

═══ UUID 列（逐格实测）═══

全空列 = I / J / K / L ⇒ 取 **I**。
🔴 sheet 的 `max_column` 实测是 **H**（8 列），故 UUID 列 I **超出 max_col** ——
instrumentation 需扩列（需求 2.5 / Property 6：扩列后 `print_area` / `page_setup` 须与基线一致）。
（spec 受管区清单写「39r×I」，实际是 39r×H；差异不影响声明。）

═══ 字段（逐列对齐前端 `useF5MajorAdjustment.MajorAdjustmentRow`）═══

🔴 行身份是 **`id`** 不是 `rowId`（与 D 类惯例相反，同 E1 教训；按值实测所得）。
G 列不单独声明（被 F 合并）。`netAmount`（借 − 贷）是前端派生，模板无列 ⇒ store-only。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F508",
    "MANAGED_SHEET_F508",
    "STORE_ITEM_ID_F508",
    "STORE_ONLY_KEYS_F508",
    "HTML_ONLY_ANCHOR_ROWS_F508",
]

MANAGED_SHEET_F508: Final[str] = "重大调整核查表F5-8"
TEMPLATE_ID_F508: Final[str] = "F58"
SHEET_KEY_F508: Final[str] = "f58-managed"
ROWS_TABLE_KEY_F508: Final[str] = "major_adjustment_rows"
#: 按值 grep 实测（`useF5MajorAdjustment.ts` 的 `STORAGE_KEY`）。
#: 🔴 F5-8 的 legacy 键只有 `F5-8-conclusion`（结论键，非行数组键）⇒ 主键无别名冲突。
STORE_ITEM_ID_F508: Final[str] = "F5-8-rows"

#: 🔴 行身份 `id`（**不是** `rowId`）—— F5-2/3/5/8 四张皆如此，与 D 类惯例相反。
ROW_IDENTITY_STORE_KEY_F508: Final[str] = "id"

#: 两级表头：R12 组标题 / R13 叶子（合并区实测 D12:E12 组「调整金额」+ F12:G13 跨行列）。
HEADER_GROUP_ROW_F508: Final[int] = 12
HEADER_LEAF_ROW_F508: Final[int] = 13

FIRST_DATA_ROW_F508: Final[int] = 14
LAST_DATA_ROW_F508: Final[int] = 29
#: 🔴 无 footer 合计 —— 指向数据区之后第一个非数据锚行。
FOOTER_ROW_F508: Final[int] = 30
#: 🔴 逐字实测 A30 带全角冒号（spec Task 8 漏了冒号，会让逐字匹配失败）。
FOOTER_MARKER_F508: Final[str] = "三、审计说明："
MANAGED_LAST_COL_F508: Final[str] = "H"
#: 全空列 I/J/K/L 取 I。🔴 超出 max_column(H) ⇒ instrumentation 扩列（需求 2.5）。
UUID_COL_F508: Final[str] = "I"

#: 锚行及其之后的 HTML-only 区（登记以证明"不是漏声明"）。
HTML_ONLY_ANCHOR_ROWS_F508: Final[tuple[tuple[int, str], ...]] = (
    (30, "三、审计说明："),
    (33, "四、审计结论："),
    (37, "提示："),
    (38, "1.本表是销售成本审定表的附表，用于审查销售成本帐户中重大调整事项的理由是否充分。"),
    (39, "2.检查现金返利、实物返利是否冲减或调整存货或购货当期的主营业务成本。"),
)

#: store-only 键（模板无对应列）。
STORE_ONLY_KEYS_F508: Final[tuple[tuple[str, str], ...]] = (
    ("netAmount", "借方 − 贷方，前端派生用于展示与重要性判断；模板无该列"),
)

#: 7 个受管字段（7 元组）。G 列不声明 —— 它被 F 列的 F{r}:G{r} 合并吞掉。
FIELD_SPECS_F508: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    # A 列数据区格式实测含 `mm-dd-yy` ⇒ value_type=date（既有口径 D5/D6/D7/H1 共 7 处）
    ("adjustment_date", "A", "editable", "date", "date", "日期", ""),
    ("voucher_no", "B", "editable", "text", "voucherNo", "凭证号", ""),
    ("item_content", "C", "editable", "text", "itemContent", "重大调整事项内容", ""),
    ("debit_amount", "D", "editable", "amount", "debitAmount", "借方", "D12"),
    ("credit_amount", "E", "editable", "amount", "creditAmount", "贷方", "D12"),
    ("adjustment_reason", "F", "editable", "text", "adjustmentReason", "调整理由", ""),
    ("reason_adequate", "H", "editable", "text", "reasonAdequate", "理由是否充分", ""),
)

SPEC_F508: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F508,
    sheet_key=SHEET_KEY_F508,
    table_key=ROWS_TABLE_KEY_F508,
    template_id=TEMPLATE_ID_F508,
    table_name=f"GT_{TEMPLATE_ID_F508}_ROWS",
    uuid_col=UUID_COL_F508,
    first_data_row=FIRST_DATA_ROW_F508,
    last_data_row=LAST_DATA_ROW_F508,
    footer_row=FOOTER_ROW_F508,
    header_group_row=HEADER_GROUP_ROW_F508,
    header_leaf_row=HEADER_LEAF_ROW_F508,
    store_item_id=STORE_ITEM_ID_F508,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F508,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F508,
    # 数据区零公式（7 个公式全在页眉 R3/R4）。
    formula_columns=(),
    formula_templates={},
    footer_marker=FOOTER_MARKER_F508,
    # 🔴 锚行不携带合计公式（D3-4 段② 先例）。
    footer_carries_total_formula=False,
    error_label="F5-8 重大调整核查表",
)
