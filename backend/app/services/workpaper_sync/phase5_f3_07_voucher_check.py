# -*- coding: utf-8 -*-
"""F3-7「应付票据检查表」—— **三区**声明（凭证抽查，F3 最复杂的一张）。

spec: f3-sync-coverage-and-first-canary · Task 14 · Requirements 5.2 / 5.3 / 5.4
几何证据: openpyxl 逐格实测（见各常量注释）

═══ 🔴 为什么必须三份独立 field_specs（裁决 F3-H3 同型）═══

三区**看起来对称**（都是「记账凭证 + 证据 + 索引/异常」），实测却在列布局上分叉：

| 区 | 证据组（合并区） | 「……」 | 索引号 | 是否异常 | footer SUM |
|---|---|---|---|---|---|
| ① 借方 R17-36 | `H15:I15` 付款审批单(2) + `J15:L15` 银行回单(3) | M | N | O | F, **L** |
| ② 贷方 R41-58 | `H39:K39` 入库单/验收单(4) + `L39:N39` 采购发票(3) | O | P | Q | F, **N** |
| ③ 日后 R63-79 | `H61:I61` 付款审批单(2) + `J61:L61` 银行回单(3) | M | N | O | F, **L** |

区②的证据组宽 7 列（4+3）而区①③宽 5 列（2+3）⇒ 其后所有列**整体右移 2 列**。
拿区①的 field_specs 套区②，会把「索引号」写进「……」列、「是否异常」写进「索引号」列 ——
一整列的静默错位，且三谓词全都会通过（值都落库了，只是落错列）。

前端同一份 `F3VoucherCheckRow` interface 覆盖三区，靠 `sectionEvidenceKind()` 区分
（`credit → purchase`，其余 `payment`）—— 与模板实测的分叉**完全吻合**，互为交叉验证。

═══ 几何（openpyxl 逐格实测）═══

`应付票据检查表F3-7` `visible` 92r × 18c（max_col = R）

    R14 标题「1.本期借方金额检查」
    R15/R16 两级表头 · 数据区 **R17~R36**（20 行）· footer **R37** 合计
    R38 标题「2.贷方金额检查」
    R39/R40 两级表头 · 数据区 **R41~R58**（18 行）· footer **R59** 合计
    R60 标题「3.资产负债表日后借方检查」
    R61/R62 两级表头 · 数据区 **R63~R79**（17 行）· footer **R80** 合计
    R81 起 审计说明 / 比例计算（R83~R85 引 `明细表F3-2`）/ 审计结论（HTML-only）

🔴 **三区行数各不相同**（20 / 18 / 17）—— 不是笔误，模板就是这么画的。

═══ 🔴 兄弟 Table ref 位移（需求 5.4）═══

三区同属一个 sheet 且**上下相邻**，任一区插行都会把下方区整体推下去。框架层已支持
（`excel_materialize._shift_sibling_table_refs` / `_grow_managed_table_ref` /
`assert_shifted_footer_gates`），配对靠 **各区独立的 `uuid_col`**：

    区① S  ·  区② T  ·  区③ U        （全空列实测 S/T/U/V，均在 max_col=R 之外）

⚠️ S/T/U **超出 `max_column=R`** ⇒ instrumentation 需扩列（同 F5-8 的 uuid_col I）。

═══ 数据区零公式 ═══

三区数据区**全部零公式**：整表公式只在页眉 R3/R4、三个 footer（`SUM`）、
以及 R83~R85 的检查比例区（`='明细表F3-2'!N31` / `=F37` / `=ROUND(F83/E83,4)`）。
⇒ 三区 `formula_columns=()`，footer 各自携带合计公式。

═══ FC-10（不命中受管区）═══

百分比格式仅 5 格，全在 **R83~R87** 的比例区（G83/G84/G85 有公式、G86/G87 无公式）——
都在三个数据区之外 ⇒ 受管区 **FC-10 零命中**，无需 pct mask。
（G 列在数据区是「票据类别」文本 + DV 下拉，与比例区的 G 列语义无关。）

═══ 数据验证（三区共用一条，无源区依赖）═══

    G17:G36 G41:G58 G63:G79   list   "银行承兑汇票,商业承兑汇票"

内联枚举 ⇒ **不像 F3-6 那样依赖表内源区**，插行不会打断 DV。
🔴 但注意前端 `F3_VOUCHER_NOTE_TYPES` 有 **4 个**值（银行承兑汇票/商业承兑汇票/供应链票据/其他），
模板 DV 只给 **2 个** —— 前端可写出模板 DV 不接受的值。登记为模板债（不改字节）：
DV 是软校验（Excel 只在手工输入时提示），程序写入不受限，故不阻塞受管。

═══ 字段（逐列对齐前端 `F3VoucherCheckRow`）═══

行身份 **`rowId`**；三个 store key 按值实测（`ITEM_KEYS`）：

    debit      → F3-7-debit-rows
    credit     → F3-7-credit-rows
    subsequent → F3-7-subsequent-rows      🔴 **不是** F1 式的 `post`

store-only（模板无列）：`seq` / `attSlot` / `issueDesc` / `sampleSource`。
区级不适用字段（区①③ 的 `receipt*`/`invoice*`、区② 的 `approval*`/`bank*`）**不登记**
到该区的 field_specs —— 它们在各自的区里才是受管字段。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F307_DEBIT",
    "SPEC_F307_CREDIT",
    "SPEC_F307_SUBSEQUENT",
    "SPECS_F307",
    "MANAGED_SHEET_F307",
    "STORE_ITEM_IDS_F307",
    "STORE_ONLY_KEYS_F307",
    "HTML_ONLY_ANCHOR_ROWS_F307",
    "DATA_VALIDATIONS_F307",
    "NOTE_TYPE_ENUM_DEBT_F307",
]

MANAGED_SHEET_F307: Final[str] = "应付票据检查表F3-7"
TEMPLATE_ID_F307: Final[str] = "F37"
#: 🔴 单一共享 sheet_key（D3-4 先例）：同 managed_sheet 映射到多个 sheet_key 会让契约装配
#: 产生「同 excel_name 多个 sheet 条目」冲突。区级唯一性靠 table_key / template_id /
#: table_name / uuid_col 四项。
SHEET_KEY_F307: Final[str] = "f37-managed"

ROW_IDENTITY_STORE_KEY_F307: Final[str] = "rowId"

#: 按值 grep 实测（`useF3VoucherCheck.ts` 的 `ITEM_KEYS`）。
STORE_ITEM_IDS_F307: Final[dict[str, str]] = {
    "debit": "F3-7-debit-rows",
    "credit": "F3-7-credit-rows",
    "subsequent": "F3-7-subsequent-rows",
}

#: 三区几何：(header_group_row, header_leaf_row, first_data_row, last_data_row, footer_row)
GEOMETRY_F307: Final[dict[str, tuple[int, int, int, int, int]]] = {
    "debit": (15, 16, 17, 36, 37),
    "credit": (39, 40, 41, 58, 59),
    "subsequent": (61, 62, 63, 79, 80),
}

#: 各区独立 uuid_col（框架层用它配对 spec↔contract table）。🔴 均超 max_column=R ⇒ 需扩列。
UUID_COLS_F307: Final[dict[str, str]] = {
    "debit": "S",
    "credit": "T",
    "subsequent": "U",
}

#: 各区 footer 的 SUM 列集（实测；区②用 N 而区①③用 L —— 随证据组宽度右移）。
FOOTER_SUM_COLUMNS_F307: Final[dict[str, tuple[str, ...]]] = {
    "debit": ("F", "L"),
    "credit": ("F", "N"),
    "subsequent": ("F", "L"),
}

#: 三区共用一条 DV（内联枚举，无表内源区依赖）。
DATA_VALIDATIONS_F307: Final[tuple[tuple[str, str, str], ...]] = (
    ("G17:G36 G41:G58 G63:G79", "list", "银行承兑汇票,商业承兑汇票"),
)

#: 🔴 模板债（登记不改字节）：前端枚举 4 值 vs 模板 DV 2 值。
NOTE_TYPE_ENUM_DEBT_F307: Final[tuple[tuple[str, ...], tuple[str, ...], str]] = (
    ("银行承兑汇票", "商业承兑汇票", "供应链票据", "其他"),
    ("银行承兑汇票", "商业承兑汇票"),
    "前端 F3_VOUCHER_NOTE_TYPES 有 4 值，模板 DV 只给 2 值 ⇒ 前端可写出 DV 不接受的值。"
    "DV 是软校验（只在手工输入时提示），程序写入不受限，故不阻塞受管；登记为模板治理债。",
)

#: 三区之外的锚行（HTML-only，登记以证明"不是漏声明"）。
HTML_ONLY_ANCHOR_ROWS_F307: Final[tuple[tuple[int, str], ...]] = (
    (5, "一、审计目标："),
    (8, "二、样本选取标准与规模："),
    (12, "三、测试："),
    (14, "1.本期借方金额检查"),
    (38, "2.贷方金额检查"),
    (60, "3.资产负债表日后借方检查"),
    (81, "四、审计说明："),
    (82, "1.本期发生额、期末余额检查比例："),
    (88, "五、审计结论："),
)

#: store-only 键（模板无对应列，三区共有）。
STORE_ONLY_KEYS_F307: Final[tuple[tuple[str, str], ...]] = (
    ("seq", "显示序号，按当前位置重算；模板无序号列（行身份走 rowId）"),
    ("attSlot", "附件槽位号，用于 OCR 附件挂载；模板无该列"),
    ("issueDesc", "异常问题描述，前端在弹窗里编辑；模板无独立列"),
    ("sampleSource", "样本来源标记（特定样本/随机抽样），前端派生；模板无该列"),
)


#: 三区共有的前 7 列（记账凭证组 A:F + 票据类别 G）。
#: `amount` 的表头文本各区不同（借方金额 / 贷方金额 / 借方金额），故由各区自己给。
def _common_head(amount_header: str, group_cell: str) -> tuple[
    tuple[str, str, str, str, str, str, str], ...
]:
    return (
        ("voucher_date", "A", "editable", "date", "voucherDate", "日期", group_cell),
        ("voucher_no", "B", "editable", "text", "voucherNo", "凭证编号", group_cell),
        ("business_content", "C", "editable", "text", "businessContent", "业务内容", group_cell),
        ("counter_account", "D", "editable", "text", "counterAccount", "对方科目", group_cell),
        ("detail_account", "E", "editable", "text", "detailAccount", "明细科目", group_cell),
        ("amount", "F", "editable", "amount", "amount", amount_header, group_cell),
        ("note_type", "G", "editable", "text", "noteType", "票据类别", ""),
    )


#: 区①③ 的证据列（payment：付款审批单 2 列 + 银行回单 3 列），其后 M/N/O。
def _payment_tail(approval_cell: str, bank_cell: str) -> tuple[
    tuple[str, str, str, str, str, str, str], ...
]:
    return (
        ("approval_date_no", "H", "editable", "text", "approvalDateNo", "日期/编号", approval_cell),
        ("approval_proper", "I", "editable", "text", "approvalProper", "是否经过恰当审批", approval_cell),
        ("bank_receipt_date", "J", "editable", "text", "bankReceiptDate", "日期", bank_cell),
        ("bank_payee", "K", "editable", "text", "bankPayee", "收款方", bank_cell),
        ("bank_amount", "L", "editable", "amount", "bankAmount", "金额", bank_cell),
        ("other_evidence", "M", "editable", "text", "otherEvidence", "……", ""),
        ("index_no", "N", "editable", "text", "indexNo", "索引号", ""),
        ("is_abnormal", "O", "editable", "text", "isAbnormal", "是否异常", ""),
    )


#: 区② 的证据列（purchase：入库单/验收单 4 列 + 采购发票 3 列），其后右移到 O/P/Q。
def _purchase_tail() -> tuple[tuple[str, str, str, str, str, str, str], ...]:
    return (
        ("receipt_date_no", "H", "editable", "text", "receiptDateNo", "日期/编号", "H39"),
        ("receipt_product", "I", "editable", "text", "receiptProduct", "品名", "H39"),
        ("receipt_unit", "J", "editable", "text", "receiptUnit", "单位", "H39"),
        ("receipt_qty", "K", "editable", "amount", "receiptQty", "数量", "H39"),
        ("invoice_date_no", "L", "editable", "text", "invoiceDateNo", "日期/编号", "L39"),
        (
            "invoice_counterparty",
            "M",
            "editable",
            "text",
            "invoiceCounterparty",
            "对手方名称",
            "L39",
        ),
        ("invoice_amount", "N", "editable", "amount", "invoiceAmount", "金额", "L39"),
        ("other_evidence", "O", "editable", "text", "otherEvidence", "……", ""),
        ("index_no", "P", "editable", "text", "indexNo", "索引号", ""),
        ("is_abnormal", "Q", "editable", "text", "isAbnormal", "是否异常", ""),
    )


FIELD_SPECS_F307_DEBIT: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = _common_head("借方金额", "A15") + _payment_tail("H15", "J15")

FIELD_SPECS_F307_CREDIT: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = _common_head("贷方金额", "A39") + _purchase_tail()

FIELD_SPECS_F307_SUBSEQUENT: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = _common_head("借方金额", "A61") + _payment_tail("H61", "J61")


def _section_spec(
    *,
    section: str,
    field_specs: tuple[tuple[str, str, str, str, str, str, str], ...],
    error_label: str,
) -> RowTableSheetSpec:
    """三区共用装配（照 D3-4 `_base_spec()`）——几何/uuid/字段逐区给，其余共享。"""
    header_group, header_leaf, first_row, last_row, footer_row = GEOMETRY_F307[section]
    return RowTableSheetSpec(
        managed_sheet=MANAGED_SHEET_F307,
        sheet_key=SHEET_KEY_F307,
        table_key=f"voucher_{section}_rows",
        template_id=f"{TEMPLATE_ID_F307}{section.upper()}",
        table_name=f"GT_{TEMPLATE_ID_F307}_{section.upper()}_ROWS",
        uuid_col=UUID_COLS_F307[section],
        first_data_row=first_row,
        last_data_row=last_row,
        footer_row=footer_row,
        header_group_row=header_group,
        header_leaf_row=header_leaf,
        store_item_id=STORE_ITEM_IDS_F307[section],
        empty_payload="[]",
        row_identity_key=ROW_IDENTITY_STORE_KEY_F307,
        store_kind=StoreKind.rows,
        field_specs=field_specs,
        # 三区数据区零公式（公式只在页眉 / footer / R83-85 比例区）。
        formula_columns=(),
        formula_templates={},
        footer_marker="合计",
        # 各区 footer 都有 SUM（列集见 FOOTER_SUM_COLUMNS_F307）。
        footer_carries_total_formula=True,
        error_label=error_label,
    )


SPEC_F307_DEBIT: Final[RowTableSheetSpec] = _section_spec(
    section="debit",
    field_specs=FIELD_SPECS_F307_DEBIT,
    error_label="F3-7 应付票据检查表（本期借方金额检查）",
)

SPEC_F307_CREDIT: Final[RowTableSheetSpec] = _section_spec(
    section="credit",
    field_specs=FIELD_SPECS_F307_CREDIT,
    error_label="F3-7 应付票据检查表（本期贷方金额检查）",
)

SPEC_F307_SUBSEQUENT: Final[RowTableSheetSpec] = _section_spec(
    section="subsequent",
    field_specs=FIELD_SPECS_F307_SUBSEQUENT,
    error_label="F3-7 应付票据检查表（资产负债表日后借方检查）",
)

#: 三区清单（顺序即 Excel 行序：借方在上、贷方居中、日后在下）。
SPECS_F307: Final[tuple[RowTableSheetSpec, ...]] = (
    SPEC_F307_DEBIT,
    SPEC_F307_CREDIT,
    SPEC_F307_SUBSEQUENT,
)
