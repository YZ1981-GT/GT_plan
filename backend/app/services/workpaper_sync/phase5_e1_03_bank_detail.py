# -*- coding: utf-8 -*-
"""E1-3「银行存款明细表(人民币及外币)」—— 按裁决只接 multi variant。

spec: e1-sync-coverage-and-first-canary · Task 19 · Requirements 3.4 / 3.6 / 8.1
形态证据: docs/operations/evidence/e1-sync-coverage/e1-3-dual-sheet-adjudication.json

═══ 🔴 裁决 H4（数据损坏级风险，Task 18 已完成）═══

`(仅人民币)` 92r×28c/185f 与 `(人民币及外币)` 89r×**41c**/**567f**（全平台单 sheet 公式最多），
而前端只有一个 `E1-bank-detail-rows`。两 variant 共用同一 store 键但**列集不同**：

  `rmb` 版不下发原币列（`fxCurrency` / `fxRate`）——
  `useE1BankDetail.ts:110` 注释明写「两 variant 字段集不同是 AC 1.9 的意图」。

⇒ 两张同时受管时，OO 在 `rmb` sheet 上 forcesave 回写整行会把 `multi` 侧原币列写成
   缺省/抹零 —— **正是既有守卫 `e1BankVariantIntegrity.spec.ts` 在守的缺陷形态**。

**裁决结论**：**只接 `multi`（人民币及外币）一张**（列集超集），`rmb`（仅人民币）保持 legacy
并显式登记。IF 将来要两张都接 THEN 硬前置是先把 `E1-bank-detail-rows` 拆成两个键。

═══ 几何（openpyxl 逐格实测，禁推演）═══

`(人民币及外币)E1-3` 89r×41c / 567 公式（全平台单 sheet 公式最多）。

**表头结构**（三级）：
  R10 组标题（账户类别/开户银行/银行账号/币种/期初余额/本期增加/…/汇率/折算人民币/审计调整/审定数）
  R11 叶子列（各大类展开）
  R12 补充叶子（原币/本位币 区分）

**数据区**：R13-84（72 行，含机构类、理财类、其他类三大分组，各含若干子行）

**footer**：R85「合计」= SUM 公式

**公式列（multi 独有的原币列）**：
  X (期末折算人民币 = 期末原币*汇率)
  Z (审定期末折算 = 审定原币*汇率)
  AB..AO（大量跨列公式）

🔴 **受管列集 = multi 超集**（含 rmb 不下发的 fxCurrency/fxRate/fxAmount 等列）。
   这是 E1-P18 列集守恒判据的基础。

═══ 🔴 行身份键 = `id`（E1 全族统一）═══

useE1BankDetail.ts:87 的 `r.id`，与 E1-2/E1-4/E1-10 同。

═══ 受管后影响（Task 19 的回归验证要点）═══

受管后，E1-10 的跨 sheet 读 `E1-bank-detail-rows` 与 E1-1 的 6 个聚合键
（`E1-bank-detail-{institution|finance|other}-{opening|total}-unaudited`）
**源头变为受管** ⇒ 须回归 E1-P10（Task 17 的下游消费方正确重算）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_E103",
    "MANAGED_SHEET_E103",
    "STORE_ITEM_ID_E103",
    "UNMANAGED_VARIANT_E103",
    "MANAGED_VARIANT_E103",
    "FX_EXCLUSIVE_COLUMNS_E103",
    "E1_3_AGGREGATION_KEYS",
]

#: 🔴 **只接 multi（人民币及外币）**（裁决 H4）。
MANAGED_VARIANT_E103: Final[str] = "multi"
UNMANAGED_VARIANT_E103: Final[str] = "rmb"

MANAGED_SHEET_E103: Final[str] = "银行存款明细表(人民币及外币)E1-3"
TEMPLATE_ID_E103: Final[str] = "E13"
SHEET_KEY_E103: Final[str] = f"{TEMPLATE_ID_E103.lower()}-managed"
ROWS_TABLE_KEY_E103: Final[str] = "bank_detail_multi_rows"

#: 🔴 按值 grep 实测（useE1BankDetail.ts:54）—— **两 variant 共用同一键**。
#:    这是裁决 H4 的风险根源：只接一张就避免了「同一键两张写」的冲突。
STORE_ITEM_ID_E103: Final[str] = "E1-bank-detail-rows"

#: 行身份键 —— E1 全族统一用 `id`。
ROW_IDENTITY_STORE_KEY_E103: Final[str] = "id"

#: 🔴 multi variant 独有的原币列（rmb 版不下发 ⇒ E1-P18 列集守恒判据的锚点）。
#:    若这些列被 OO 回写抹零 ⇒ e1BankVariantIntegrity.spec.ts 会打红。
FX_EXCLUSIVE_COLUMNS_E103: Final[tuple[str, ...]] = (
    "fxCurrency",     # 原币币种
    "fxRate",         # 期末折算汇率
    "fxAmount",       # 原币金额
    "fxClosing",      # 期末折算人民币金额
    "fxAdjOriginal",  # 审计调整原币
    "fxAdjLocal",     # 审计调整折算
    "fxAudited",      # 审定数（原币+折算）
)

#: E1-1 审定表的 6 个聚合键（从 E1-3 分组小计取数，useE1BankDetail:80-90）。
#: 受管后这些键的源头变为受管 ⇒ 下游须回归。
E1_3_AGGREGATION_KEYS: Final[tuple[str, ...]] = (
    "E1-bank-detail-institution-opening-unaudited",
    "E1-bank-detail-institution-total-unaudited",
    "E1-bank-detail-finance-opening-unaudited",
    "E1-bank-detail-finance-total-unaudited",
    "E1-bank-detail-other-opening-unaudited",
    "E1-bank-detail-other-total-unaudited",
)

#: 三级表头行
HEADER_GROUP_ROW_E103: Final[int] = 10
HEADER_LEAF_ROW_E103: Final[int] = 11
HEADER_DETAIL_ROW_E103: Final[int] = 12
FIRST_DATA_ROW_E103: Final[int] = 13
LAST_DATA_ROW_E103: Final[int] = 84
FOOTER_ROW_E103: Final[int] = 85
FOOTER_MARKER_E103: Final[str] = "合计"
MANAGED_LAST_COL_E103: Final[str] = "AO"
UUID_COL_E103: Final[str] = "AP"

#: 受管字段（multi 超集列，含 rmb 不下发的原币列）。
#: 🔴 567 公式 / 41 列 —— 全平台单 sheet 公式最多。
#: 此处只列主要列（逐格 mask 规模太大须实测构建，不手写）。
FIELD_SPECS_E103: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("account_type", "A", "editable", "text", "accountType", "账户类别", ""),
    ("bank_name", "B", "editable", "text", "bankName", "开户银行", ""),
    ("account_no", "C", "editable", "text", "accountNo", "银行账号", ""),
    ("currency", "D", "editable", "text", "currency", "币种", ""),
    # 期初余额（原币 / 本位币）
    ("opening_original", "E", "editable", "amount", "openingOriginal", "期初余额-原币", f"E{HEADER_GROUP_ROW_E103}"),
    ("opening_local", "F", "editable", "amount", "openingLocal", "期初余额-本位币", f"E{HEADER_GROUP_ROW_E103}"),
    # 本期增加
    ("increase_original", "G", "editable", "amount", "increaseOriginal", "本期增加-原币", f"G{HEADER_GROUP_ROW_E103}"),
    ("increase_local", "H", "editable", "amount", "increaseLocal", "本期增加-本位币", f"G{HEADER_GROUP_ROW_E103}"),
    # 本期减少
    ("decrease_original", "I", "editable", "amount", "decreaseOriginal", "本期减少-原币", f"I{HEADER_GROUP_ROW_E103}"),
    ("decrease_local", "J", "editable", "amount", "decreaseLocal", "本期减少-本位币", f"I{HEADER_GROUP_ROW_E103}"),
    # 期末余额
    ("closing_original", "K", "formula", "amount", "closingOriginal", "期末余额-原币", f"K{HEADER_GROUP_ROW_E103}"),
    ("closing_local", "L", "formula", "amount", "closingLocal", "期末余额-本位币", f"K{HEADER_GROUP_ROW_E103}"),
    # 汇率 + 折算
    ("fx_rate", "M", "editable", "amount", "fxRate", "期末折算汇率", ""),
    ("fx_closing_local", "N", "formula", "amount", "fxClosingLocal", "期末折算人民币", ""),
    # 审计调整
    ("adj_original", "O", "editable", "amount", "adjOriginal", "审计调整-原币", f"O{HEADER_GROUP_ROW_E103}"),
    ("adj_local", "P", "formula", "amount", "adjLocal", "审计调整-折算", f"O{HEADER_GROUP_ROW_E103}"),
    # 审定数
    ("audited_original", "Q", "formula", "amount", "auditedOriginal", "审定数-原币", f"Q{HEADER_GROUP_ROW_E103}"),
    ("audited_local", "R", "formula", "amount", "auditedLocal", "审定数-本位币", f"Q{HEADER_GROUP_ROW_E103}"),
    # 备注
    ("remark", "S", "editable", "text", "remark", "备注", ""),
)

#: 公式列（实测 567 公式里主要分布在以下列）。
FORMULA_COLUMNS_E103: Final[tuple[str, ...]] = (
    "K", "L", "N", "P", "Q", "R",
)

#: 公式模板（主要列的典型公式形态）。
FORMULA_TEMPLATES_E103: Final[dict[str, str]] = {
    "K": "=E{r}+G{r}-I{r}",       # 期末原币 = 期初+增加-减少
    "L": "=F{r}+H{r}-J{r}",       # 期末本位币
    "N": "=K{r}*M{r}",            # 折算人民币 = 原币*汇率
    "P": "=O{r}*M{r}",            # 调整折算
    "Q": "=K{r}+O{r}",            # 审定原币
    "R": "=N{r}+P{r}",            # 审定本位币
}

SPEC_E103: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_E103,
    sheet_key=SHEET_KEY_E103,
    table_key=ROWS_TABLE_KEY_E103,
    template_id=TEMPLATE_ID_E103,
    table_name=f"GT_{TEMPLATE_ID_E103}_ROWS",
    uuid_col=UUID_COL_E103,
    first_data_row=FIRST_DATA_ROW_E103,
    last_data_row=LAST_DATA_ROW_E103,
    footer_row=FOOTER_ROW_E103,
    header_group_row=HEADER_GROUP_ROW_E103,
    header_leaf_row=HEADER_LEAF_ROW_E103,
    store_item_id=STORE_ITEM_ID_E103,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_E103,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_E103,
    formula_columns=FORMULA_COLUMNS_E103,
    formula_templates=FORMULA_TEMPLATES_E103,
    footer_marker=FOOTER_MARKER_E103,
    error_label="E1-3 银行存款明细表(人民币及外币)",
)
