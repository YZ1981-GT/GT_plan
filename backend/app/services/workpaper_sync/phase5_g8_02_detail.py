# -*- coding: utf-8 -*-
"""G8-2「其他权益工具投资明细表」—— sheet 层薄声明（单区，FVOCI）。

spec: `g-cycle-single-region-detail-lanes` · Task 9b / C-8
　　　列模型依据 `evidence/task8-c6-remaining-eight-template-logic.md` §3 + 本轮逐格实测

═══ 几何（openpyxl 逐格实测，禁推演）═══

`明细表G8-2`：`max_row=39` / `max_column=24` / **0 个 definedName**。

* **两级**表头 **R9（组）/ R10（叶子）** —— R9 的**横向**合并区只有三个：
  `C9:F9` 期初余额 · `I9:N9` 本期变动 · `O9:R9` 期末余额。
  另有九个跨两行的单列合并（`A9:A10` 被投资单位名称 · `B9:B10` 投资比例 ·
  `G9:G10` 期初调整数 · `H9:H10` 期初审定数 · `S9:S10` 调整数 · `T9:T10` 审定数 ·
  `U9:U10` 指定为…原因 · `V9:V10` 其他综合收益转入留存收益的原因 · `W9:W10` 发函情况）。
* **单个受管区** R11-R20（10 行），footer **R21** 合计（逐列 `=SUM(x11:x20)`）。
* 有效内容列 **23**（A..W），`X` 空 ⇒ UUID 列取 `X`。
* 🔴 `R22` 是「三、审计说明：」且 `N22 = =A22`（模板怪癖，在受管区之外，不碰）。

═══ 🔴 G8 是 FVOCI —— OCI 三列是准则要求，**绝不可照抄 G9/G10 的「删 OCI」** ═══

受管表内注释逐字：「在初始确认时，企业可以将非交易性权益工具投资**指定为以公允价值计量
且其变动计入其他综合收益**的金融资产。该指定一经作出，**不得撤销**。」
⇒ 模板的三个 OCI 列（`F` 期初累计 / `L` 本期转留存 / `R` 期末累计）是 CAS22 要求的。
G9/G10 删 OCI 的依据是「那两张表全 FVTPL」，对 G8 **反向**成立。同理 G6（其他债权投资）。

═══ 模板行级缺陷已修（spec oo-writeback-template-parity-closure R1）═══

修复前逐行实测 R11-R20：`M` 在 R11 是 `=SUM(I:L)`、其余 `=SUM(I:K)`；`P` 只有 R12 含 K；
`R` 在 R13-R20 整格无公式；`T` 在 R12 整格无公式；合计行 K / L / R 三列无 SUM。
当时为避开 `ProtectedRegionWriteError`（`mode=formula` 的格模板里必须真有公式），`R`/`T` 只能判
editable，OO 侧可填、回到表单又被前端重算覆盖（如实登记的欠账）。

现已用 `scripts/fix/fix_template_formula_defects.py` 把模板逐行统一为
`M=SUM(I:K)` / `P=D+J+K` / `R=F+J+L` / `T=Q+S`（合计行补 K / L / R），于是：

* 八个公式列 **E·H·M·O·P·Q·R·T** 逐行同形，全部进 :data:`FORMULA_TEMPLATES_G802`，判据逐格比对；
* `R`/`T` 改判 **formula**（受保护，OO 侧改不了，与前端只读公式格一致）。

🔴 `M` 不含 L（推翻 C-6 §3.3「M 应含 L」的判读）：`M` 是投资账面的本期变动，必须满足
`E + M = Q`；`L`「其他综合收益转入留存收益」是终止确认时权益内部的结转（注3），只减少 `R`
列的 OCI 累计、不改变投资账面。修复前 10 行里 9 行本就是 `SUM(I:K)`，只有 R11 多加了 L。

═══ 字段键逐字取自前端行接口 ═══

`useG8Detail.G8DetailRow`（23 字段，与模板列序 A..W 逐列对应）。
`rowId` 是行身份（`generated_prefixed_opaque_string`，`genId()` 带随机后缀）、
`seq` 是显示序号 —— 两者都**不是**受管列。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G802",
    "MANAGED_SHEET_G802",
    "STORE_ITEM_ID_G802",
    "FORMULA_TEMPLATES_G802",
    "FORMULA_COLUMNS_G802",
    "FIELD_SPECS_G802",
    "FOOTER_ROW_G802",
]

MANAGED_SHEET_G802: Final[str] = "明细表G8-2"
TEMPLATE_ID_G802: Final[str] = "G802"
SHEET_KEY_G802: Final[str] = "g802-managed"

#: 🔴 按值取自 `useG8Detail.ts` 的 `ITEM_ID_ROWS`，**不按 sheet 号推演**。
STORE_ITEM_ID_G802: Final[str] = "G8-detail-rows"
ROW_IDENTITY_STORE_KEY_G802: Final[str] = "rowId"

HEADER_GROUP_ROW_G802: Final[int] = 9
HEADER_LEAF_ROW_G802: Final[int] = 10
FIRST_DATA_ROW_G802: Final[int] = 11
LAST_DATA_ROW_G802: Final[int] = 20
#: footer 合计行（**不受管**）：逐列 `=SUM(x11:x20)`
FOOTER_ROW_G802: Final[int] = 21
FOOTER_MARKER_G802: Final[str] = "合计"

#: 公式列 → 数据行公式模板（`{r}` 为行号）。模板 R11-R20 逐行同形，判据逐格比对。
FORMULA_TEMPLATES_G802: Final[dict[str, str]] = {
    "E": "=SUM(C{r}:D{r})",         # 期初合计 = 成本 + 累计公允价值变动
    "H": "=E{r}+G{r}",              # 期初审定数
    "M": "=SUM(I{r}:K{r})",         # 本期变动合计 = 成本 + 公允价值变动 + 处置结转（= Q − E）
    "O": "=C{r}+I{r}",              # 期末成本（未审线）
    "P": "=D{r}+J{r}+K{r}",         # 期末累计公允价值变动（含处置结转）
    "Q": "=SUM(O{r}:P{r})",         # 期末合计 = 期末成本 + 期末累计公允价值变动
    "R": "=F{r}+J{r}+L{r}",         # 期末 OCI 累计 = 期初累计 + 本期公允价值变动 + 转入留存收益
    "T": "=Q{r}+S{r}",              # 期末审定数
}

#: 公式列（受 `formula_mask` 保护，OO 侧改不了）：模板 R11-R20 每行都有公式。
FORMULA_COLUMNS_G802: Final[tuple[str, ...]] = tuple(FORMULA_TEMPLATES_G802)

#: 23 个受管字段（7 元组 `(column_key, column, mode, value_type, json_key, header_text, group_header_cell)`）。
#:
#: 顺序即 Excel 列序 A→W；`header_text` 逐字取模板（落在 R9 横向合并区内的取叶子行 R10，
#: 跨两行合并的单列取 R9）；`json_key` 逐字取 `useG8Detail.G8DetailRow`；
#: `group_header_cell` 指向该列所属一级分组的合并区起始格（跨两行的单列为 `""`）。
FIELD_SPECS_G802: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("investee_name", "A", "editable", "text", "investeeName", "被投资单位名称", ""),
    ("investment_ratio", "B", "editable", "amount", "investmentRatio", "投资比例", ""),
    # ── C9:F9 期初余额（三分量 + OCI 旁列）────────────────────────────
    ("opening_cost", "C", "editable", "amount", "openingCost", "成本", "C9"),
    ("opening_fv_accum", "D", "editable", "amount", "openingFvAccum", "累计公允价值变动", "C9"),
    ("opening_total", "E", "formula", "amount", "openingTotal", "合计", "C9"),
    (
        "opening_oci_cumulative", "F", "editable", "amount", "openingOciCumulative",
        "计入其他综合收益的累计利得或损失", "C9",
    ),
    # ── G / H 单列（期初调整 / 期初审定）──────────────────────────────
    ("opening_adjustment", "G", "editable", "amount", "openingAdjustment", "期初调整数", ""),
    ("opening_adjusted", "H", "formula", "amount", "openingAdjusted", "期初审定数", ""),
    # ── I9:N9 本期变动（成本净额 / FV变动 / 处置结转 / OCI转留存 / 合计 / 股利）──
    ("movement_cost", "I", "editable", "amount", "movementCost", "成本", "I9"),
    ("movement_fv_change", "J", "editable", "amount", "movementFvChange", "本期公允价值变动", "I9"),
    (
        "disposal_fv_transfer", "K", "editable", "amount", "disposalFvTransfer",
        "处置时公允价值变动结转", "I9",
    ),
    (
        "oci_to_retained_earnings", "L", "editable", "amount", "ociToRetainedEarnings",
        "其他综合收益转入留存收益", "I9",
    ),
    ("movement_total", "M", "formula", "amount", "movementTotal", "合计", "I9"),
    ("dividend_income", "N", "editable", "amount", "dividendIncome", "本期确认的股利收入", "I9"),
    # ── O9:R9 期末余额（三分量 + OCI 旁列）────────────────────────────
    ("closing_cost", "O", "formula", "amount", "closingCost", "成本", "O9"),
    ("closing_fv_accum", "P", "formula", "amount", "closingFvAccum", "累计公允价值变动", "O9"),
    ("closing_total", "Q", "formula", "amount", "closingTotal", "合计", "O9"),
    (
        "closing_oci_cumulative", "R", "formula", "amount", "closingOciCumulative",
        "计入其他综合收益的累计利得或损失", "O9",
    ),
    # ── S / T 单列（调整数 / 审定数）──────────────────────────────────
    ("closing_adjustment", "S", "editable", "amount", "closingAdjustment", "调整数", ""),
    ("closing_adjusted", "T", "formula", "amount", "closingAdjusted", "审定数", ""),
    # ── U / V / W 单列说明（均跨 R9:R10 合并）─────────────────────────
    (
        "designation_reason", "U", "editable", "text", "designationReason",
        "指定为以公允价值计量且其变动计入其他综合收益的原因", "",
    ),
    ("transfer_reason", "V", "editable", "text", "transferReason", "其他综合收益转入留存收益的原因", ""),
    ("confirmation_status", "W", "editable", "text", "confirmationStatus", "发函情况", ""),
)

SPEC_G802: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_G802,
    sheet_key=SHEET_KEY_G802,
    table_key="g8_detail_rows",
    template_id=TEMPLATE_ID_G802,
    table_name=f"GT_{TEMPLATE_ID_G802}_DETAIL_ROWS",
    #: 🔴 有效内容列 23（A..W），X 空 ⇒ UUID 列取 X（不是 max_column+1=Y：
    #:   `max_column=24` 含空列，按**有效**列右移一列才是判据 GC-3 的口径）
    uuid_col="X",
    first_data_row=FIRST_DATA_ROW_G802,
    last_data_row=LAST_DATA_ROW_G802,
    footer_row=FOOTER_ROW_G802,
    header_group_row=HEADER_GROUP_ROW_G802,
    header_leaf_row=HEADER_LEAF_ROW_G802,
    store_item_id=STORE_ITEM_ID_G802,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_G802,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_G802,
    formula_columns=FORMULA_COLUMNS_G802,
    formula_templates=FORMULA_TEMPLATES_G802,
    footer_marker=FOOTER_MARKER_G802,
    error_label="G8-2 其他权益工具投资明细表",
    #: 幽灵行锚点用默认的 `[0]`（A 列「被投资单位名称」）—— 与 G9/G10 不同：
    #: A 列在 G8 就是业务名称本身（模板 R11 无预填值），不需要像它们那样改指 B 列。
)
