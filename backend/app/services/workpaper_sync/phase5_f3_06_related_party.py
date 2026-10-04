# -*- coding: utf-8 -*-
"""F3-6「关联方及交易检查表」—— sheet 层薄声明（F3 第二张）。

spec: f3-sync-coverage-and-first-canary · Task 13 · Requirements 2.3 / 5.1
几何证据: openpyxl 逐格实测（见下方各常量的注释），模板 sha256 与 canary 同册

═══ 为什么它排第二（验证"复用框架层零改动"）═══

F3-5 canary 已把发布链跑通。F3-6 的价值是**证明第二张 sheet 不需要改框架层**：
单级表头 + 单区 + 一个公式列，是行表引擎最标准的形态。若它需要新增框架能力，说明
canary 的抽象没做对。实测结论：`RowTableSheetSpec` 原样够用，零框架改动。

═══ 几何（openpyxl 逐格实测）═══

`关联方及交易检查表F3-6` `visible` 26r × 16c（max_col = P）

    R5  一段说明文字（A5 长句，**不是表头**）
    R6  单级表头 13 列：
        A 关联方名称  B 关联关系  C 票据类别  D 期初余额  E 借方发生  F 贷方发生
        G 期末余额    H 账龄     I 定价政策  J 发生原因（款项性质）
        K 期后付款金额 L 索引号   M 备注
    R7~R12  数据区（6 行）
    R13     合计 —— 🔴 SUM 只覆盖 **D,E,F,G,K 五列**（不是全部数值列）
    R14/R16 审计说明 / 审计结论（HTML-only）
    R18~R26 🔴 **下拉源区**（见下）

═══ 🔴 下拉源区 R18~R26 必须保护（F3-P11）═══

数据验证实测两条：

    C7:C12  list  "银行承兑汇票,商业承兑汇票"        ← 内联枚举，无源区依赖
    B7:B12  list  $B$19:$B$26                     ← **指向表内源区**

源区内容（B 列）：R18 `勿改、勿删`（标记行）· R19~R26 八个关联关系枚举值
（实际控制人 / 控股股东 / 控股股东、实际控制人的附属企业 / 持有5%以上股份的法人或其他组织 /
联营企业 / 合营企业 / 董高监等关键管理人员 / 其他关联方）。

⇒ 受管区插行若把源区推下去，`$B$19:$B$26` 不会跟着移（DV 的 formula1 是字面量），
下拉会指向错误区域甚至空白。保护范围取 **R18~R26**（含 `勿改、勿删` 标记行）：
数据区末行 R12 与源区之间只隔 footer R13 + 说明 R14~R17，插行余量为 0
⇒ `last_data_row=12` 是**硬上限**，扩行必须走"先下移源区再改 DV"的显式迁移，不能静默插行。
本声明如实把 `last_data_row` 钉在 12，不预留虚假余量。

═══ 公式列（FC-5 前端等价核）═══

模板：`G{r} = =D{r}+F{r}-E{r}`（期末 = 期初 + 贷方 − 借方），R7~R12 逐行同构。

前端 `useF3RelatedParty.computeRelatedPartyRow`：

    closingBalance = round2(openingBalance + creditMovement - debitMovement)

逐字等价（D=期初 / F=贷方 / E=借方）⇒ FC-5 通过，两边不需要统一口径。
（spec Task 13 写的函数名 `recalcRelatedPartyRow` 实测不存在，真名是
`computeRelatedPartyRow`；等价性结论不变。）

═══ UUID 列 ═══

全空列实测 N/O/P/Q/R/S/T ⇒ 取 **N**（spec 声明值，实测可用）。
N 在 `max_column=P` 内 ⇒ **无需扩列**（与 F3-5 的 uuid_col P 同册但不同列，兄弟区无冲突）。

═══ FC-10 ═══

整表 **0 个**百分比格式格 ⇒ 不命中，无需 pct mask
（与同册 F3-5 的 I 列命中形成对照）。

═══ 字段（逐列对齐前端 `F3RelatedPartyNoteRow`）═══

行身份 **`rowId`**（按值实测 `STORAGE_KEY='F3-6-rows'` 同文件）。

12 个受管字段；`G`（期末余额）是公式列不进 `field_specs`；三个派生字段
（`seq` 序号 / `concentration` 占比 / `riskFlags` 风险标记）模板无列 ⇒ store-only。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F306",
    "MANAGED_SHEET_F306",
    "STORE_ITEM_ID_F306",
    "STORE_ONLY_KEYS_F306",
    "HTML_ONLY_ANCHOR_ROWS_F306",
    "DROPDOWN_SOURCE_ROWS_F306",
    "DATA_VALIDATIONS_F306",
]

MANAGED_SHEET_F306: Final[str] = "关联方及交易检查表F3-6"
TEMPLATE_ID_F306: Final[str] = "F36"
SHEET_KEY_F306: Final[str] = "f36-managed"
ROWS_TABLE_KEY_F306: Final[str] = "related_party_rows"
#: 按值 grep 实测（`useF3RelatedParty.ts` 的 `STORAGE_KEY`）。
STORE_ITEM_ID_F306: Final[str] = "F3-6-rows"

ROW_IDENTITY_STORE_KEY_F306: Final[str] = "rowId"

#: 单级表头（R5 是说明文字，不是表头行）。
HEADER_ROW_F306: Final[int] = 6

FIRST_DATA_ROW_F306: Final[int] = 7
#: 🔴 硬上限：R13 footer 之后 R18~R26 是 DV 源区，插行余量为 0（见模块 docstring）。
LAST_DATA_ROW_F306: Final[int] = 12
FOOTER_ROW_F306: Final[int] = 13
FOOTER_MARKER_F306: Final[str] = "合计"
MANAGED_LAST_COL_F306: Final[str] = "M"
#: 全空列 N~T 取 N。在 max_column(P) 内 ⇒ 无需扩列。
UUID_COL_F306: Final[str] = "N"

#: 🔴 下拉源区（F3-P11 保护对象）：`B7:B12` 的 DV formula1 是字面量 `$B$19:$B$26`，
#: 源区被插行推下去时不会跟着移 ⇒ 受管区不得越过 `LAST_DATA_ROW_F306` 扩行。
DROPDOWN_SOURCE_ROWS_F306: Final[tuple[int, int]] = (18, 26)

#: 实测两条 DV（保留原样，不改模板字节）。
DATA_VALIDATIONS_F306: Final[tuple[tuple[str, str, str], ...]] = (
    ("C7:C12", "list", "银行承兑汇票,商业承兑汇票"),
    ("B7:B12", "list", "$B$19:$B$26"),
)

#: footer 之后的 HTML-only 区（登记以证明"不是漏声明"）。
HTML_ONLY_ANCHOR_ROWS_F306: Final[tuple[tuple[int, str], ...]] = (
    (13, "合计"),
    (14, "1、审计说明："),
    (16, "2、审计结论："),
    (18, "勿改、勿删"),
)

#: store-only 键（模板无对应列）。
STORE_ONLY_KEYS_F306: Final[tuple[tuple[str, str], ...]] = (
    ("seq", "显示序号，按当前位置重算；模板无序号列（行身份走 rowId，不是 seq）"),
    ("concentration", "该行期末余额占合计的占比，前端派生用于集中度提示；模板无该列"),
    ("riskFlags", "风险标记数组（关联关系待核实 / 定价政策未说明等），前端派生；模板无该列"),
)

#: 12 个受管字段（7 元组）。G 列是公式列，不进 field_specs。
FIELD_SPECS_F306: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("party_name", "A", "editable", "text", "partyName", "关联方名称", ""),
    ("relationship", "B", "editable", "text", "relationship", "关联关系", ""),
    ("note_type", "C", "editable", "text", "noteType", "票据类别", ""),
    ("opening_balance", "D", "editable", "amount", "openingBalance", "期初余额", ""),
    ("debit_movement", "E", "editable", "amount", "debitMovement", "借方发生", ""),
    ("credit_movement", "F", "editable", "amount", "creditMovement", "贷方发生", ""),
    ("aging", "H", "editable", "text", "aging", "账龄", ""),
    ("pricing_policy", "I", "editable", "text", "pricingPolicy", "定价政策", ""),
    ("transaction_reason", "J", "editable", "text", "transactionReason", "发生原因（款项性质）", ""),
    (
        "subsequent_payment_amount",
        "K",
        "editable",
        "amount",
        "subsequentPaymentAmount",
        "期后付款金额",
        "",
    ),
    ("index_no", "L", "editable", "text", "indexNo", "索引号", ""),
    ("remark", "M", "editable", "text", "remark", "备注", ""),
)

SPEC_F306: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F306,
    sheet_key=SHEET_KEY_F306,
    table_key=ROWS_TABLE_KEY_F306,
    template_id=TEMPLATE_ID_F306,
    table_name=f"GT_{TEMPLATE_ID_F306}_ROWS",
    uuid_col=UUID_COL_F306,
    first_data_row=FIRST_DATA_ROW_F306,
    last_data_row=LAST_DATA_ROW_F306,
    footer_row=FOOTER_ROW_F306,
    header_row=HEADER_ROW_F306,
    store_item_id=STORE_ITEM_ID_F306,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F306,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F306,
    formula_columns=("G",),
    formula_templates={"G": "=D{r}+F{r}-E{r}"},
    footer_marker=FOOTER_MARKER_F306,
    # footer R13 的 SUM 只覆盖 D/E/F/G/K 五列，但确实携带合计公式。
    footer_carries_total_formula=True,
    error_label="F3-6 关联方及交易检查表",
)
