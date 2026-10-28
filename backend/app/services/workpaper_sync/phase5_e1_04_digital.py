# -*- coding: utf-8 -*-
"""E1-4「数字货币明细表」—— 第二张行表（验证「复用框架层零改动」）。

spec: e1-sync-coverage-and-first-canary · Task 13 · Requirements 2.1
形态证据: docs/operations/evidence/e1-sync-coverage/e1-form-verdicts.json

═══ 本张的作用（spec Task 13 原话）═══

**验证「第二张复用框架层零改动」** —— 它独立键、零 OCR、零跨 sheet 取数，若接它需要改框架层，
说明框架层抽象不足，须先回上游 `d1-sync-row-table-engine-and-d1-coverage` 修。

实测结论：**零改动**。本模块只有 `RowTableSheetSpec` 一个常量声明，无任何算法、无框架层改动。

═══ 几何（openpyxl 逐格实测，禁推演）═══

单级表头 R9（17 列 A..Q）· 数据区 **R10-16**（7 行，A 列预填序号 1-7、B 列预填「北京」）·
footer **R17「合计」** = SUM(10:16) · 公式列 **H/I/K/L/N**：

  H = `=E{r}+F{r}-G{r}`   期末余额（原币）
  I = `=H{r}*D{r}`        期末余额（本位币，🔴 乘法）
  K = `=H{r}+J{r}`        期末审定数（原币）
  L = `=K{r}*D{r}`        期末审定数（人民币，🔴 乘法）
  N = `=M{r}-K{r}`        期末账面余额与银行查询余额的差异

⇒ 与 E1-2 同属「乘法派生」族（E1-2 的 G=`E*F` / I=`G+H*F`），`mode=formula` 路径不依赖算式形态。

🔴 spec oo-writeback-template-parity-closure R3：json 键逐字取前端 `e1DigitalRowCalc.E1DigitalRow`
（原写 seqNo / bank / *Original / *Local，前端存 seq / bankName / opening / endingFc / auditedRmb …）；
A 序号前端按位置编号 ⇒ `auto_source`（同 H1-8）；M~Q 模板 R9 有表头（查询余额 / 差异 / 两个索引号 /
备注，原注释说「无表头」不实），前端都有对应字段，一并受管。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_E104",
    "MANAGED_SHEET_E104",
    "STORE_ITEM_ID_E104",
    "PREFILLED_SEQ_ROWS_E104",
]

MANAGED_SHEET_E104: Final[str] = "数字货币明细表E1-4"
TEMPLATE_ID_E104: Final[str] = "E14"
SHEET_KEY_E104: Final[str] = f"{TEMPLATE_ID_E104.lower()}-managed"
ROWS_TABLE_KEY_E104: Final[str] = "digital_currency_rows"

#: 🔴 按值 grep 实测（spec Task 13 声明值）。
STORE_ITEM_ID_E104: Final[str] = "E1-digital-rows"

#: 行身份键 —— 与 E1-2 同族（E1 侧统一用 `id`，不是 D 类的 `rowId`）。
ROW_IDENTITY_STORE_KEY_E104: Final[str] = "id"

HEADER_ROW_E104: Final[int] = 9
FIRST_DATA_ROW_E104: Final[int] = 10
LAST_DATA_ROW_E104: Final[int] = 16
FOOTER_ROW_E104: Final[int] = 17
FOOTER_MARKER_E104: Final[str] = "合计"
MANAGED_LAST_COL_E104: Final[str] = "Q"
UUID_COL_E104: Final[str] = "R"

#: 模板预填的 7 行序号（A 列 1-7，B 列「北京」）。动态行从 R10 起覆盖/扩张。
PREFILLED_SEQ_ROWS_E104: Final[tuple[tuple[int, int], ...]] = tuple(
    (row, seq) for seq, row in enumerate(range(FIRST_DATA_ROW_E104, LAST_DATA_ROW_E104 + 1), start=1)
)

#: 公式模板（逐格实测）。I/L 两列是**乘法**（原币 × 汇率）。
FORMULA_TEMPLATES_E104: Final[dict[str, str]] = {
    "H": "=E{r}+F{r}-G{r}",
    "I": "=H{r}*D{r}",
    "K": "=H{r}+J{r}",
    "L": "=K{r}*D{r}",
    "N": "=M{r}-K{r}",
}

#: 17 个受管字段（7 元组，单级表头故 group_header_cell 全空）。顺序即 Excel 列序 A→Q，表头逐格取 R9。
FIELD_SPECS_E104: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("seq_no", "A", "auto_source", "integer", "seq", "序号", ""),
    ("bank", "B", "editable", "text", "bankName", "开户银行", ""),
    ("currency", "C", "editable", "text", "currency", "币种", ""),
    ("fx_rate", "D", "editable", "amount", "fxRate", "汇率", ""),
    ("opening_original", "E", "editable", "amount", "opening", "期初余额(原币)", ""),
    ("increase_original", "F", "editable", "amount", "increase", "本期增加(原币)", ""),
    ("decrease_original", "G", "editable", "amount", "decrease", "本期减少(原币)", ""),
    ("closing_original", "H", "formula", "amount", "endingFc", "期末余额(原币)", ""),
    ("closing_local", "I", "formula", "amount", "endingRmb", "期末余额(本位币)", ""),
    ("adjustment_original", "J", "editable", "amount", "adjustment", "账项调整（原币）", ""),
    ("audited_original", "K", "formula", "amount", "auditedFc", "期末审定数（原币）", ""),
    ("audited_local", "L", "formula", "amount", "auditedRmb", "期末审定数（人民币）", ""),
    ("query_balance", "M", "editable", "amount", "queryBalance", "期末银行查询余额", ""),
    ("balance_diff", "N", "formula", "amount", "diff", "期末账面余额与银行查询余额的差异", ""),
    ("index_no", "O", "editable", "text", "indexNo", "银行余额索引号", ""),
    ("confirmation_index_no", "P", "editable", "text", "confirmationIndexNo", "银行询证函索引号", ""),
    ("note", "Q", "editable", "text", "note", "备注", ""),
)

SPEC_E104: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_E104,
    sheet_key=SHEET_KEY_E104,
    table_key=ROWS_TABLE_KEY_E104,
    template_id=TEMPLATE_ID_E104,
    table_name=f"GT_{TEMPLATE_ID_E104}_ROWS",
    uuid_col=UUID_COL_E104,
    first_data_row=FIRST_DATA_ROW_E104,
    last_data_row=LAST_DATA_ROW_E104,
    footer_row=FOOTER_ROW_E104,
    header_row=HEADER_ROW_E104,
    store_item_id=STORE_ITEM_ID_E104,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_E104,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_E104,
    formula_columns=("H", "I", "K", "L", "N"),
    formula_templates=FORMULA_TEMPLATES_E104,
    # A 序号是 auto_source（受保护、回写不合并）⇒ 新增行的锚点必须是 B 开户银行，否则全被当幽灵行剔除
    ghost_row_anchor_index=1,
    footer_marker=FOOTER_MARKER_E104,
    error_label="E1-4 数字货币明细表",
)
