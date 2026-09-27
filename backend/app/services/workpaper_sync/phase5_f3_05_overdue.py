# -*- coding: utf-8 -*-
"""F3-5「逾期票据检查」—— sheet 层薄声明（F3 首张 canary）。

spec: f3-sync-coverage-and-first-canary · Task 8 · Requirements 1.1 / 2.2 / 3.3
几何证据: .kiro/specs/f3-sync-coverage-and-first-canary/evidence/task2-morphology-and-geometry.md

═══ 为什么它排 F3 首张（裁决 F3-H1）═══

| 候选 | 数据区公式 | FC-10 | 真库载荷 | 跨 sheet 消费方 |
|---|---|---|---|---|
| F3-2 明细 | 2 列（O/R） | 🔴 J/U 两列 | 0 行 | 6 处 |
| **F3-5 逾期** | **0**（footer 才有 SUM） | 🔴 仅 I 列，可 HTML-only 绕开 | **675 B / 2 行（全 F3 唯一）** | 0 |
| F3-6 关联方 | 1 列（G） | 无 | 0 行 | 0 |

canary 的职责是验证**发布链**（FC-1）而非引擎，失败面越小越好；且 F3-5 是 F3 唯一有真载荷的
store 键 ⇒ 能做真数据 roundtrip，比空表往返更有说服力。

═══ 几何（openpyxl 逐格实测，禁推演）═══

两级表头 **R5（组标题）/ R6（叶子）**，15 列 A-O：

    A 票据类别(A5:A6)  B 票据号(B5:B6)
    C-E 组「票据关系人」(C5:E5)：C 出票人 / D 承兑人 / E 收款人
    F-H 组「票据期限」(F5:H5)：F 出票日 / G 到期日 / H 期限
    I 票面利率(I5:I6)  J 票面金额(J5:J6)  K 期后支付金额(K5:K6)
    L 借款条件(L5:L6)  M 是否调整(M5:M6)
    N-O 组「抵押情况」(N5:O5)：N 物品名称 / O 金额

数据区 **R7-21**（15 行，A 列无预填文字标签）· footer **R22**「合计」（纯两字，**无空格** ——
与同册 F3-2 R31 / F3-4 R32 的「合␠␠计」不同，别照搬）。

🔴 **数据区零公式**：全表 10 个公式全在页眉（R3/R4 引「底稿目录」）与 footer
（R22 `SUM(J7:J21)` / `SUM(K7:K21)` / `SUM(O7:O21)`）⇒ `formula_columns=()`。
这也印证 FC-4 的判据必须用前端三元组：若按"公式数阈值"判，本表会被误判成 `static_region`。

数据验证：`A7:A21` = 「银行承兑汇票,商业承兑汇票」（🔴 模板只 2 枚举，而前端
`F3_OVERDUE_NOTE_TYPES` 有 4 项含「供应链票据/其他」⇒ 受管后 OO 侧下拉选不到后两项，
与 F3 红基线 B3 同源，归裁决 F3-H5 的降级面，本 spec 不改模板 DV）；`M7:M21` = 「是,否」
（前端 `F3_YES_NO_OPTIONS` 另有「不适用」，同上）。

═══ UUID 列（逐格实测）═══

全空列 = P / Q / R / S（数据区与表头皆空）⇒ 取最靠近受管区的 **P**。
🔴 O 列**不可**作 UUID：它是「抵押情况-金额」业务列且 footer R22 有 `SUM(O7:O21)`。

═══ FC-10 命中判定（🔴 方法论：三条同时成立才算命中）═══

`number_format` 含 `%` 的数据区列实测有 **C / D / E / I** 四列，但只有 **I** 真命中 FC-10：

| 列 | 语义（R6 表头） | 模板格式 | 前端字段 | 判定 |
|---|---|---|---|---|
| C | 出票人 | `0.00%` | `drawer: string` | ❌ 文本列套错格式（模板治理债，登记不修） |
| D | 承兑人 | `0.00%` | `acceptor: string` | ❌ 同上 |
| E | 收款人 | `0.00%` | `payee: string` | ❌ 同上 |
| **I** | **票面利率** | `0.00%` | `interestRate: number`，标签「(%)」存百分数 | 🔴 **命中** |

⇒ FC-10 的判据是「前端存 % 数值 ∧ 模板百分比格式 ∧ **该列语义确实是比率**」三者同时成立。
只看 `number_format` 会把 C/D/E 这类"文本列套错格式"误判成命中（本 spec 实施中曾误判一次）。

I 列按需求 1.1 **不进 `field_specs`**，待 FC-10 换算（`value_type=percent_points`）落地后再纳入。
🔴 `merge.py` 现无任何 percent 换算（`_DECIMAL_TYPES` 只做 Decimal 规范化）—— 直接受管会让
OO 显示 350% 而 HTML 存 3.5。

═══ 字段（逐列对齐前端 `useF3OverdueCheck.F3OverdueNoteRow`）═══

store-only（模板无对应列，不进 `field_specs`）：`seq`（模板 A 列是票据类别不是序号）·
`attSlot`（附件槽位）· `overdueDays`（前端 `calcOverdueDays` 派生）· `unpaidAmount`
（`faceValue - postPaymentAmount` 派生）· `riskFlags`（派生数组）。

FC-7 派生列：**H `termDays`** —— 模板 H 列数据区无公式、前端每次 `calcTermDays(issueDate, dueDate)`
重算。按 FC-7 判 `mode=auto_source`（受保护，OO 改动产生受保护字段冲突），**不得标 editable**
（否则用户在 OO 改 H 后回写入 store，HTML 下一次 recalc 即静默覆盖）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F305",
    "MANAGED_SHEET_F305",
    "STORE_ITEM_ID_F305",
    "FC10_DEFERRED_COLUMNS_F305",
    "STORE_ONLY_KEYS_F305",
]

MANAGED_SHEET_F305: Final[str] = "逾期票据检查F3-5"
TEMPLATE_ID_F305: Final[str] = "F35"
SHEET_KEY_F305: Final[str] = "f35-managed"
ROWS_TABLE_KEY_F305: Final[str] = "overdue_notes_rows"
#: 🔴 按值 grep 实测（`useF3OverdueCheck.ts:55 STORAGE_KEY`）+ 真库 675 B / 2 行确认。
#: 无 legacy 别名键（与 F5 的五张双键表不同）。
STORE_ITEM_ID_F305: Final[str] = "F3-5-rows"

#: 🔴 行身份是 `rowId`（真库 2 行全带 `rowId`、0 行带 `id`）—— 与 F5-2/3/5/8 的 `id` 相反，
#: 逐 entry 按值实测，不照搬（FC-4）。
ROW_IDENTITY_STORE_KEY_F305: Final[str] = "rowId"

#: 两级表头：R5 组标题 / R6 叶子（合并区实测 C5:E5 / F5:H5 / N5:O5 三个横向组）。
HEADER_GROUP_ROW_F305: Final[int] = 5
HEADER_LEAF_ROW_F305: Final[int] = 6

FIRST_DATA_ROW_F305: Final[int] = 7
LAST_DATA_ROW_F305: Final[int] = 21
FOOTER_ROW_F305: Final[int] = 22
#: 🔴 纯「合计」两字无空格（同册 F3-2 R31 / F3-4 R32 是「合␠␠计」，不可混用）。
FOOTER_MARKER_F305: Final[str] = "合计"
MANAGED_LAST_COL_F305: Final[str] = "O"
#: 全空列 P/Q/R/S 中最靠近受管区者；O 是有 SUM 的业务列不可占用。
UUID_COL_F305: Final[str] = "P"

#: 🔴 FC-10 待换算列：暂不进 `field_specs`（需求 1.1 / 3.3）。
FC10_DEFERRED_COLUMNS_F305: Final[tuple[tuple[str, str, str], ...]] = (
    ("I", "interestRate", "票面利率(%)：前端存 3.5 表示 3.5%，模板格式 0.00% 期望小数 0.035"),
)

#: store-only 键（模板无对应列，登记以证明"不是漏声明"）。
STORE_ONLY_KEYS_F305: Final[tuple[tuple[str, str], ...]] = (
    ("seq", "行序号；模板 A 列是「票据类别」不是序号列"),
    ("attSlot", "附件槽位，纯前端附件绑定用"),
    ("overdueDays", "前端 calcOverdueDays(dueDate, now) 派生，模板无列"),
    ("unpaidAmount", "前端 faceValue - postPaymentAmount 派生，模板无列"),
    ("riskFlags", "前端风险提示数组，模板无列"),
)

#: 14 个受管字段（7 元组，第 7 位是组标题格；横向组取组标题格，纵向合并单列取 ""）。
#: 顺序即 Excel 列序 A→O，**跳过 FC-10 待换算的 I 列** ⇒ 15 列模板 - 1 = 14。
FIELD_SPECS_F305: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("note_type", "A", "editable", "text", "noteType", "票据类别", ""),
    ("ticket_no", "B", "editable", "text", "ticketNo", "票据号", ""),
    ("drawer", "C", "editable", "text", "drawer", "出票人", "C5"),
    ("acceptor", "D", "editable", "text", "acceptor", "承兑人", "C5"),
    ("payee", "E", "editable", "text", "payee", "收款人", "C5"),
    # 模板 F/G 列格式实测 `mm-dd-yy` ⇒ `value_type=date`（既有口径：D5 `到期日` / D6·D7 `日期`
    # / H1 `减少日期` 共 7 处均用 date）。前端存 ISO 字符串，规范化由 merge 统一处理。
    ("issue_date", "F", "editable", "date", "issueDate", "出票日", "F5"),
    ("due_date", "G", "editable", "date", "dueDate", "到期日", "F5"),
    # 🔴 FC-7 派生列：模板无公式、HTML 每次重算 ⇒ auto_source（受保护），不得 editable。
    #    `value_type=integer`（天数；封闭枚举无 `number` —— 既有 5 处 integer 全是序号类整数）。
    ("term_days", "H", "auto_source", "integer", "termDays", "期限", "F5"),
    ("face_value", "J", "editable", "amount", "faceValue", "票面金额", ""),
    ("post_payment_amount", "K", "editable", "amount", "postPaymentAmount", "期后支付金额", ""),
    ("loan_conditions", "L", "editable", "text", "loanConditions", "借款条件", ""),
    ("is_adjusted", "M", "editable", "text", "isAdjusted", "是否调整", ""),
    ("collateral_name", "N", "editable", "text", "collateralName", "物品名称", "N5"),
    ("collateral_amount", "O", "editable", "amount", "collateralAmount", "金额", "N5"),
)

SPEC_F305: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F305,
    sheet_key=SHEET_KEY_F305,
    table_key=ROWS_TABLE_KEY_F305,
    template_id=TEMPLATE_ID_F305,
    table_name=f"GT_{TEMPLATE_ID_F305}_ROWS",
    uuid_col=UUID_COL_F305,
    first_data_row=FIRST_DATA_ROW_F305,
    last_data_row=LAST_DATA_ROW_F305,
    footer_row=FOOTER_ROW_F305,
    header_group_row=HEADER_GROUP_ROW_F305,
    header_leaf_row=HEADER_LEAF_ROW_F305,
    store_item_id=STORE_ITEM_ID_F305,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F305,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F305,
    # 🔴 数据区零公式（10 个公式全在页眉 R3/R4 与 footer R22）。
    formula_columns=(),
    formula_templates={},
    footer_marker=FOOTER_MARKER_F305,
    error_label="F3-5 逾期票据检查表",
)
