# -*- coding: utf-8 -*-
"""E1-2「现金明细表」—— E1 canary 的 sheet 层薄声明。

spec: e1-sync-coverage-and-first-canary · Task 8 · Requirements 1.1 / 1.3 / 2.2
形态证据: docs/operations/evidence/e1-sync-coverage/e1-form-verdicts.json

═══ 为什么选它作 canary（spec Task 8 的三条理由，逐条实测成立）═══

1. **零 OCR**：`useE1CashDetail` 无任何 `E1*OcrConfirmDialog` 引用 —— E1 全目录有 7 个 OCR
   确认弹窗（454 次提及）构成「第二批量写入方」，canary 阶段必须避开它（spec 裁决 H10）。
2. **零跨 sheet 取数**：`loadFromResponses` 只读自身 `STORAGE_KEY`，不读别张的 store。
3. **键独立**：`E1-cash-detail-rows` 无 variant 后缀、无 legacy 兜底键、无 pack 形态。

⇒ 第一册 16 张里失败面最小的行表（34r×22c / 38 公式）。

═══ 🔴 形态判定用前端三元组，不是模板公式数（裁决 H8）═══

| 维度 | 实测 |
|---|---|
| store 键存在 | ✅ `E1-cash-detail-rows`（useE1CashDetail.ts:50，按值 grep） |
| addRow/removeRow 信号 | ✅ 两者齐备（:275 / :282）+ updateCell(:292) |
| composable 归属 | ✅ `useE1CashDetail` 专属 |

⇒ `binding_kind = excel_table`（动态行表），**不是** static_region。

═══ 🔴 两处实测推翻 spec 的隐含假设 ═══

1. **行身份字段名是 `id`，不是 D 类惯用的 `rowId`**（useE1CashDetail.ts:104/144/285 的 `r.id`）。
   照 D 类写 `rowId` 会让 store-projection fail-closed 抛「缺稳定行身份」，把整个 entry 打挂
   —— D4-1 曾因 `rowKey`/`rowId` 之误踩过同款（那次是「任何有真载荷的底稿一进在线编辑即 500」）。
2. **本张是「固定行 + 动态行」混合身份**：R15 人民币行对应前端不可删除的 `fixed-rmb`
   （useE1CashDetail.ts:284 `if (rowId === 'fixed-rmb') return`），其余是 `cash-<uuid>` 动态行。
   两者同在 `id` 字段 ⇒ `row_identity_key='id'` 可同时容纳，**无需拆区**。

═══ 几何（openpyxl 逐格实测，禁推演）═══

两级表头 R13（组标题）/ R14（叶子）· 数据区 **R15-21**（R15-19 预填币种、R20-21 空白待扩）·
footer **R22「合计」** = SUM(15:21) · 公式列 **E/G/I**：

  E = `=B{r}+C{r}-D{r}`   期末余额（原币）
  G = `=E{r}*F{r}`        期末折算人民币金额（🔴 **乘法**，引擎首次在 E1 遇到）
  I = `=G{r}+H{r}*F{r}`   期末审定数（🔴 **乘加混合**：调整额按汇率折算后加总）

🔴 **footer 之下还有 R23**「其中：存放在境外的款项总额」（E/G 两列有公式）—— 与 D1-4 第三区
   同型的「footer 下 static 行」。它不属本受管区，按 spec 表四（HTML-only item 子集）处置：
   本 canary **不受管它**，登记在 `HTML_ONLY_ROWS_E102` 说明原因，不强行塞进动态区
   （`ExcelInstrumentationSpec` 强制 footer_row > last_data_row，塞进去会构造即抛）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_E102",
    "MANAGED_SHEET_E102",
    "STORE_ITEM_ID_E102",
    "ROW_IDENTITY_STORE_KEY_E102",
    "FIXED_ROW_KEY_E102",
    "PREFILLED_CURRENCY_ROWS_E102",
    "HTML_ONLY_ROWS_E102",
]

MANAGED_SHEET_E102: Final[str] = "现金明细表E1-2"
TEMPLATE_ID_E102: Final[str] = "E12"
SHEET_KEY_E102: Final[str] = f"{TEMPLATE_ID_E102.lower()}-managed"
ROWS_TABLE_KEY_E102: Final[str] = "cash_detail_rows"

#: 🔴 按值 grep 实测（useE1CashDetail.ts:50）。四种命名风格里的「语义」风格。
STORE_ITEM_ID_E102: Final[str] = "E1-cash-detail-rows"

#: 🔴 实测行身份字段名是 `id`（不是 D 类的 `rowId`）—— 照抄 D 类会 fail-closed 打挂整个 entry。
ROW_IDENTITY_STORE_KEY_E102: Final[str] = "id"

#: 不可删除的固定行 key（前端 useE1CashDetail.ts:284 硬挡 removeRow）。对应模板 R15 人民币行。
FIXED_ROW_KEY_E102: Final[str] = "fixed-rmb"

#: 模板预填的币种行（R15-19）。R20-21 为空白待扩行 —— 动态行插入从 R20 起。
PREFILLED_CURRENCY_ROWS_E102: Final[tuple[tuple[int, str], ...]] = (
    (15, "人民币"),
    (16, "美元"),
    (17, "日元"),
    (18, "澳元"),
    (19, "欧元"),
)

HEADER_GROUP_ROW_E102: Final[int] = 13
HEADER_LEAF_ROW_E102: Final[int] = 14
FIRST_DATA_ROW_E102: Final[int] = 15
LAST_DATA_ROW_E102: Final[int] = 21
FOOTER_ROW_E102: Final[int] = 22
FOOTER_MARKER_E102: Final[str] = "合计"
MANAGED_LAST_COL_E102: Final[str] = "J"
UUID_COL_E102: Final[str] = "K"

#: 🔴 footer 之下的 static 行（R23「其中：存放在境外的款项总额」，E/G 两列有公式）。
#:    与 D1-4 第三区同型。本 canary **不受管它**：动态 spec 表达不了 footer 下的行
#:    （`ExcelInstrumentationSpec.__post_init__` 强制 footer_row > last_data_row），
#:    且它是单行汇总口径、无行维度 ⇒ 若将来要受管应走 static_region，不进本区。
HTML_ONLY_ROWS_E102: Final[tuple[tuple[int, str, str], ...]] = (
    (
        23,
        "其中：存放在境外的款项总额",
        "在 footer R22 之下，动态 spec 表达不了（footer_row 必须 > last_data_row）；"
        "单行汇总口径无行维度 ⇒ 将来受管须走 static_region（同 D1-4 第三区裁决）",
    ),
)

#: 10 个受管字段（7 元组）。顺序即 Excel 列序 A→J。
#: 表头文本：A/H/I/J 取 R13 组标题，B..G 取 R14 叶子（两级表头，逐格实测）。
#: E/G/I 三列模板内逐行有真公式 ⇒ formula；其余 7 列 editable。
FIELD_SPECS_E102: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("currency", "A", "editable", "text", "currency", "币种", ""),
    ("opening", "B", "editable", "amount", "opening", "期初余额", f"B{HEADER_GROUP_ROW_E102}"),
    ("increase", "C", "editable", "amount", "increase", "本期增加", f"B{HEADER_GROUP_ROW_E102}"),
    ("decrease", "D", "editable", "amount", "decrease", "本期减少", f"B{HEADER_GROUP_ROW_E102}"),
    ("closing_original", "E", "formula", "amount", "closingOriginal", "期末余额（原币）", f"B{HEADER_GROUP_ROW_E102}"),
    ("fx_rate", "F", "editable", "amount", "fxRate", "期末折算汇率", f"B{HEADER_GROUP_ROW_E102}"),
    ("closing_rmb", "G", "formula", "amount", "closingRmb", "期末折算人民币金额", f"B{HEADER_GROUP_ROW_E102}"),
    ("adjustment_original", "H", "editable", "amount", "adjustmentOriginal", "审计调整-原币（调减为负数）", ""),
    ("closing_audited", "I", "formula", "amount", "closingAudited", "期末审定数（人民币金额）", ""),
    ("remark", "J", "editable", "text", "remark", "备注", ""),
)

#: 公式模板（逐格实测）。
#: 🔴 G 是**乘法**、I 是**乘加混合** —— 引擎首次在 E1 遇到非纯加减派生；
#:    `mode=formula` 路径不依赖算式形态，materialize 不覆盖公式格、由 OO 重算。
FORMULA_TEMPLATES_E102: Final[dict[str, str]] = {
    "E": "=B{r}+C{r}-D{r}",
    "G": "=E{r}*F{r}",
    "I": "=G{r}+H{r}*F{r}",
}

SPEC_E102: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_E102,
    sheet_key=SHEET_KEY_E102,
    table_key=ROWS_TABLE_KEY_E102,
    template_id=TEMPLATE_ID_E102,
    table_name=f"GT_{TEMPLATE_ID_E102}_ROWS",
    uuid_col=UUID_COL_E102,
    first_data_row=FIRST_DATA_ROW_E102,
    last_data_row=LAST_DATA_ROW_E102,
    footer_row=FOOTER_ROW_E102,
    header_group_row=HEADER_GROUP_ROW_E102,
    header_leaf_row=HEADER_LEAF_ROW_E102,
    store_item_id=STORE_ITEM_ID_E102,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_E102,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_E102,
    formula_columns=("E", "G", "I"),
    formula_templates=FORMULA_TEMPLATES_E102,
    footer_marker=FOOTER_MARKER_E102,
    error_label="E1-2 现金明细表",
)
