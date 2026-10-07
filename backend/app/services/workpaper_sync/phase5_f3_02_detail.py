# -*- coding: utf-8 -*-
"""F3-2「明细表」—— sheet 层薄声明。

spec: f3-sync-coverage-and-first-canary · Task 15 · Requirements 3.1, 3.2, 3.3, 3.4
几何证据: openpyxl 逐格实测（2026-10-07）

═══ 几何 ═══

两级表头 **R13（组）/ R14（叶子）**：

R13 组表头（19 列，含 3 组合并区）：
    A(A13:A14) 票据号  |  B(B13:B14) 票据类别  |  C(C13:C14) 关联方类型  |
    D~F(D13) 票据关系人  |  G~I(G13) 票据期限  |
    J(J13:J14) 票面利率  |  K(K13:K14) 是否承兑  |
    L(L13:L14) 期初余额  |  M(M13:M14) 本期开票  |  N(N13:N14) 本期承兑  |
    O(O13:O14) 期末未审数  |  P(P13:P14) 账项调整  |  Q(Q13:Q14) 重分类调整  |
    R(R13:R14) 期末审定数  |  S(S13:S14) 已计利息  |  T(T13:T14) 是否函证  |
    U(U13:U14) 票据保证金比例  |  V(V13:V14) 保证金金额  |  W(W13:W14) 备注

R14 叶子（只有 D~F / G~I 六个分列有标签）：
    D14 出票人  |  E14 承兑人  |  F14 收款人  |
    G14 出票日  |  H14 到期日  |  I14 期限

数据区 **R15~R30**（16 行）· footer **R31** 「合  计」（双空格）。

═══ 公式列（2 列，逐行同构）═══

    O{r} = L{r}+M{r}-N{r}       期末未审数 = 期初+本期开票−本期承兑
    R{r} = O{r}+P{r}+Q{r}       期末审定数 = 期末未审+AJE+RJE

═══ 前端派生列（FC-7，模板无公式）═══

I 列（期限/天数）：模板 I 列**为空**（R15~R30 全部 empty），前端 `termDays` 是
computed 派生（`到期日−出票日`）⇒ 按 FC-7 判 `auto_source`（前端派生 HTML-only 列）。
同理 `maturityBucket` / `isOverdue` / `overdueDays` 是纯前端 computed，模板无对应列。

🔴 I 列是 editable 还是 auto_source？模板 I14 标题「期限」且 R15:I15 为空（无公式无值）
⇒ 前端填写后的值回写到 I 列。但前端 `termDays` 标记 `editable: false` + `formula` ⇒
该值由 `computeRow` 派生（到期日−出票日），用户不直接编辑。受管声明中**不登记 I 列**
（声明它 = editable 会让用户可覆盖派生值；声明它 = formula 但模板无公式会让 materialize
在空公式格写值时抛 ProtectedRegionWriteError）。I 列保持 HTML-only。

═══ FC-10 百分比格式 ═══

J(票面利率)/K(是否承兑)/U(保证金比例) 三列数据区有百分比格式 `%`。
J 和 U 是数值输入（百分比值）；K 是选择型（是/否/不适用，百分比格式为模板治理债）。
三列均为 editable，FC-10 处置：J 和 U 暂 HTML-only（spec 原文「J/U 两列 FC-10 暂
HTML-only」），K 照常 editable（它是选择型不是数值型，百分比格式不影响）。

🔴 **据此 J 和 U 不进 field_specs**（暂 HTML-only），等 FC-10 换算引擎落地后接入。

═══ footer ═══

A31 = `合  计`（双空格），SUM 列：L/M/N/O/P/Q/R/S/V（9 列有 SUM 公式）。
footer_carries_total_formula=True。

🔴 footer 标记双空格 `合  计` 与 D6-9 先例同型。

═══ UUID 列 ═══

max_col=Y(25)，X 列 non_null=0 ⇒ 取 **X**。

═══ 字段（逐列对齐前端 `StoredF3DetailRow`）═══

行身份 **`rowId`**。前端 `STORAGE_KEY = 'F3-2-rows'`。

store-only: `seq`（前端序号，模板 A 列实际用于票据号不是序号）—— 🔴 实测 A 列模板
表头是「票据号」不是「序号」⇒ `seq` 是前端维护的虚拟序号，A 列对应 `ticketNo`。

🔴 前端 `termDays`(I) / `isOverdue` / `overdueDays` / `maturityBucket` / `closingUnadjusted`(O) /
`closingAdjusted`(R) 是 `computeRow` 的派生出参（computed），不在 `StoredF3DetailRow` 中，
不进 field_specs。O 和 R 走 `formula_columns`。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F302",
    "MANAGED_SHEET_F302",
    "STORE_ITEM_ID_F302",
    "STORE_ONLY_KEYS_F302",
    "HTML_ONLY_COLUMNS_F302",
]

MANAGED_SHEET_F302: Final[str] = "明细表F3-2"
TEMPLATE_ID_F302: Final[str] = "F32"
SHEET_KEY_F302: Final[str] = "f32-managed"
ROWS_TABLE_KEY_F302: Final[str] = "note_detail_rows"
STORE_ITEM_ID_F302: Final[str] = "F3-2-rows"

ROW_IDENTITY_STORE_KEY_F302: Final[str] = "rowId"

HEADER_GROUP_ROW_F302: Final[int] = 13
HEADER_LEAF_ROW_F302: Final[int] = 14
FIRST_DATA_ROW_F302: Final[int] = 15
LAST_DATA_ROW_F302: Final[int] = 30
FOOTER_ROW_F302: Final[int] = 31
#: 🔴 footer 标记双空格（与 D6-9 先例同型）。
FOOTER_MARKER_F302: Final[str] = "合  计"
MANAGED_LAST_COL_F302: Final[str] = "W"
UUID_COL_F302: Final[str] = "X"

#: store-only 键（模板无对应列）。
STORE_ONLY_KEYS_F302: Final[tuple[tuple[str, str], ...]] = (
    ("seq", "前端序号（模板 A 列是票据号不是序号，seq 由前端维护）"),
)

#: HTML-only 列（FC-10 百分比 / FC-7 派生）——已登记原因。
HTML_ONLY_COLUMNS_F302: Final[tuple[tuple[str, str], ...]] = (
    ("I", "期限(天)：模板无公式，前端 termDays 是 computed 派生（FC-7 auto_source）"),
    ("J", "票面利率(%)：FC-10 百分比格式，暂 HTML-only 等换算引擎落地"),
    ("U", "票据保证金比例(%)：FC-10 百分比格式，暂 HTML-only 等换算引擎落地"),
)

#: 16 个受管 editable 字段（A~W 减去公式列 O/R 和 HTML-only 列 I/J/U）。
#: 7 元组: (column_key, column, mode, value_type, json_key, header_text, group_header_cell)
FIELD_SPECS_F302: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    # ── A 区: 基础信息（A~F，不含 I 列期限） ──
    ("ticket_no", "A", "editable", "text", "ticketNo", "票据号", ""),
    ("note_type", "B", "editable", "text", "noteType", "票据类别", ""),
    ("related_party_type", "C", "editable", "text", "relatedPartyType", "关联方类型", ""),
    ("drawer", "D", "editable", "text", "drawer", "出票人", "D13"),
    ("acceptor", "E", "editable", "text", "acceptor", "承兑人", "D13"),
    ("payee", "F", "editable", "text", "payee", "收款人", "D13"),
    # ── B 区: 票据条款（G~K，跳过 I/J） ──
    ("issue_date", "G", "editable", "text", "issueDate", "出票日", "G13"),
    ("due_date", "H", "editable", "text", "dueDate", "到期日", "G13"),
    # I 列(期限): HTML-only（FC-7 auto_source）
    # J 列(票面利率): HTML-only（FC-10 百分比）
    ("is_accepted", "K", "editable", "text", "isAccepted", "是否承兑", ""),
    # ── C 区: 余额及审计核对（L~W，跳过 O/R 公式列 和 U 百分比） ──
    ("opening_balance", "L", "editable", "amount", "openingBalance", "期初余额", ""),
    ("current_issued", "M", "editable", "amount", "currentIssued", "本期开票", ""),
    ("current_accepted", "N", "editable", "amount", "currentAccepted", "本期承兑", ""),
    # O 列: 公式 =L+M-N（期末未审数）
    ("aje", "P", "editable", "amount", "aje", "账项调整", ""),
    ("rje", "Q", "editable", "amount", "rje", "重分类调整", ""),
    # R 列: 公式 =O+P+Q（期末审定数）
    ("accrued_interest", "S", "editable", "amount", "accruedInterest", "已计利息", ""),
    ("is_confirmed", "T", "editable", "text", "isConfirmed", "是否函证", ""),
    # U 列(保证金比例): HTML-only（FC-10 百分比）
    ("deposit_amount", "V", "editable", "amount", "depositAmount", "保证金金额", ""),
    ("remark", "W", "editable", "text", "remark", "备注", ""),
)

SPEC_F302: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F302,
    sheet_key=SHEET_KEY_F302,
    table_key=ROWS_TABLE_KEY_F302,
    template_id=TEMPLATE_ID_F302,
    table_name=f"GT_{TEMPLATE_ID_F302}_ROWS",
    uuid_col=UUID_COL_F302,
    first_data_row=FIRST_DATA_ROW_F302,
    last_data_row=LAST_DATA_ROW_F302,
    footer_row=FOOTER_ROW_F302,
    header_group_row=HEADER_GROUP_ROW_F302,
    header_leaf_row=HEADER_LEAF_ROW_F302,
    store_item_id=STORE_ITEM_ID_F302,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F302,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F302,
    formula_columns=("O", "R"),
    formula_templates={
        "O": "=L{r}+M{r}-N{r}",
        "R": "=O{r}+P{r}+Q{r}",
    },
    footer_marker=FOOTER_MARKER_F302,
    footer_carries_total_formula=True,
    error_label="F3-2 应付票据明细表",
)
