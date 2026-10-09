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

═══ 🔴 模板四处行级缺陷 ⇒ `R`/`T` 判 editable、`M`/`P` 不进 formula_templates ═══

逐行实测 R11-R20：

| 行 | `M` 本期变动合计 | `P` 期末累计FV变动 | `R` 期末OCI累计 | `T` 审定数 |
|---|---|---|---|---|
| R11 | `=SUM(I:L)` ✅含 L | `=D+J` ❌漏 K | ✅ `=F+J+L` | ✅ `=Q+S` |
| R12 | `=SUM(I:K)` ❌漏 L | `=D+J+K` ✅含 K | ✅ `=F+J+L` | ❌**无公式** |
| R13..R20 | `=SUM(I:K)` ❌漏 L | `=D+J` ❌漏 K | ❌**无公式** | ✅ `=Q+S` |

会计判读：`M` 应含 L · `P` 应含 K · `R` 与 `T` 每行都该有（都是恒等式）。
即 **R11 与 R12 各对一半、R13-R20 两处都漏**，且 R12 缺 T、R13-R20 缺 R。
与 G5「三段合计各漏加一个小计」同族 —— 本 spec 已确立的规则：**模板真实缺陷走覆盖层，
不改模板字节**（`backend/wp_templates/` 运行时只读 + sha 冻结）。

处置由框架层的**两条硬约束**唯一确定，不是风格选择：

1. `contracts._parse_table` 的 **CS-13**：`mode=formula` 的列必须落在 `formula_mask`
   覆盖的列跨度内（`formula_mask` 由 `formula_columns` 现算）。
2. `excel_materialize` 写受保护格时的 **`ProtectedRegionWriteError`**：`mode=formula` 的
   格在模板里**必须真有公式**（`view.has_formula`），否则直接抛。

⇒ 逐列裁决：

* `M`/`P`：模板每行**都有**公式（只是口径逐行不同）⇒ 可判 `formula`，进
  :data:`FORMULA_COLUMNS_G802`（受保护，OO 侧改不了）。但**不进**
  :data:`FORMULA_TEMPLATES_G802` —— 它们逐行不同形，单条模板表达不了；逐行实测落
  :data:`TEMPLATE_ROW_FORMULAS_G802`，由判据按行比对。
* `R`/`T`：模板在 R13-R20 / R12 **整格无公式** ⇒ 判 `formula` 会让 materialize 抛
  ⇒ 只能判 **`editable`**。这正是判据 P12 要求证明的「R13 的 `R` 列与 R12 的 `T` 列
  **不被误标** formula」—— 它的技术根据就是上面第 2 条硬约束。

🔴 **因此 `R`/`T` 两列会双向同步**：OO 侧可以填，回写 store 后前端
`useG8Detail.enrichG8DetailRow` 按会计恒等式（`R=F+J+L` / `T=Q+S`）**重算覆盖**。
这个「OO 侧改动被前端重算」是如实登记的欠账（见 spec evidence
`task9b-c8-g8-rootfix.md` §3.2），根因是模板漏了这两列的公式：修模板要么改字节
（`backend/wp_templates/` 运行时只读 + sha 冻结，禁止）、要么走覆盖层（框架层尚无该
机制）+ 会计专业复核，两者都不在本 lane 范围。前端 UI 已把这两列渲染成只读公式格，
用户在平台侧不会误填。

🔴 **裁决 G1R-H3 的两处措辞需修正**（实测后）：
① 「拆 `g802-r11` + `g802-r12plus`（或三 spec）」**不可行** —— 引擎只支持
`row_section_field`（按**字段值**过滤），而 G8 是连续 R11-R20 里逐行公式不同，前端数组
没有也不该有区归属字段（行的物理位置不是业务属性，那会变成 BP-11 语义耦合行身份的
同族问题）。单 spec + 逐行实测台账是正解。
② 「并集取 formula、交集取 editable」若按字面取并集，`R`/`T` 都会标 formula ⇒ 撞
`ProtectedRegionWriteError`。正确口径是「**模板每行都有公式**才可判 formula」。

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
    "TEMPLATE_ROW_FORMULAS_G802",
    "FRONTEND_DERIVED_COLUMNS_G802",
    "TEMPLATE_ROW_DEFECTS_G802",
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

#: 公式列（受 `formula_mask` 保护，OO 侧改不了）。
#:
#: 🔴 判据是「模板 **R11-R20 每行都有公式**」，不是「公式逐行同形」：
#: * `M`/`P` 每行都有（口径逐行不同，见 :data:`TEMPLATE_ROW_FORMULAS_G802`）⇒ 在此表内；
#: * `R`/`T` 在 R13-R20 / R12 整格无公式 ⇒ **不在**此表，判 `editable`
#:   （判 formula 会撞 `excel_materialize` 的 `ProtectedRegionWriteError`）。
FORMULA_COLUMNS_G802: Final[tuple[str, ...]] = ("E", "H", "M", "O", "P", "Q")

#: 公式列 → 数据行公式模板（`{r}` 为行号）。只放 R11-R20 **逐行同形**的四列，
#: 判据可逐格比对。`M`/`P` 逐行不同形（单条模板表达不了）⇒ 见
#: :data:`TEMPLATE_ROW_FORMULAS_G802`。
FORMULA_TEMPLATES_G802: Final[dict[str, str]] = {
    "E": "=SUM(C{r}:D{r})",         # 期初合计 = 成本 + 累计公允价值变动
    "H": "=E{r}+G{r}",              # 期初审定数
    "O": "=C{r}+I{r}",              # 期末成本（未审线）
    "Q": "=SUM(O{r}:P{r})",         # 期末合计 = 期末成本 + 期末累计公允价值变动
}

#: 🔴 `M`/`P` 的**逐行实测**公式（`(column, row) -> 公式`）。判据按它逐格比对 ——
#: 一旦模板被修复成逐行同形，判据会红并提示把该列提进 `FORMULA_TEMPLATES_G802`
#: （而不是静默失配）。
TEMPLATE_ROW_FORMULAS_G802: Final[dict[tuple[str, int], str]] = {
    **{("M", 11): "=SUM(I11:L11)"},                                  # ✅ 含 L
    **{("M", r): f"=SUM(I{r}:K{r})" for r in range(12, 21)},          # ❌ 漏 L
    **{("P", 12): "=D12+J12+K12"},                                   # ✅ 含 K
    **{("P", r): f"=D{r}+J{r}" for r in (11, *range(13, 21))},        # ❌ 漏 K
}

#: 🔴 由**前端**按会计恒等式重算的派生列（`mode=editable`，因模板部分行无公式）。
#: OO 侧可填，但回写 store 后前端 `enrichG8DetailRow` 会重算覆盖 —— 见模块头。
FRONTEND_DERIVED_COLUMNS_G802: Final[dict[str, str]] = {
    "R": "F+J+L",       # 期末 OCI 累计（模板 R13-R20 整格无公式）
    "T": "Q+S",         # 期末审定数（模板 R12 整格无公式）
}

#: 模板行级缺陷台账（逐格实测）。判据按它断言「缺陷仍在」—— 一旦模板被修复，
#: 判据会红，提示同步更新本表与 `FORMULA_COLUMNS_G802`（而不是静默失配）。
TEMPLATE_ROW_DEFECTS_G802: Final[
    tuple[tuple[str, tuple[int, ...], str], ...]
] = (
    ("M", tuple(range(12, 21)), "=SUM(I{r}:K{r}) 漏加 L（其他综合收益转入留存收益）"),
    ("P", (11, *range(13, 21)), "=D{r}+J{r} 漏加 K（处置时公允价值变动结转）"),
    ("R", tuple(range(13, 21)), "整格无公式，会计上应为 =F{r}+J{r}+L{r}"),
    ("T", (12,), "整格无公式，会计上应为 =Q{r}+S{r}"),
)

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
    #: 🔴 mode=formula 但不在 FORMULA_COLUMNS（模板 R12-R20 漏加 L）
    ("movement_total", "M", "formula", "amount", "movementTotal", "合计", "I9"),
    ("dividend_income", "N", "editable", "amount", "dividendIncome", "本期确认的股利收入", "I9"),
    # ── O9:R9 期末余额（三分量 + OCI 旁列）────────────────────────────
    ("closing_cost", "O", "formula", "amount", "closingCost", "成本", "O9"),
    #: 🔴 mode=formula 但不在 FORMULA_COLUMNS（模板仅 R12 含 K）
    ("closing_fv_accum", "P", "formula", "amount", "closingFvAccum", "累计公允价值变动", "O9"),
    ("closing_total", "Q", "formula", "amount", "closingTotal", "合计", "O9"),
    #: 🔴 判 editable：模板 R13-R20 整格无公式，判 formula 会撞 ProtectedRegionWriteError
    #:   （判据 P12 要求证明的正是这条）。前端按 `=F+J+L` 重算覆盖。
    (
        "closing_oci_cumulative", "R", "editable", "amount", "closingOciCumulative",
        "计入其他综合收益的累计利得或损失", "O9",
    ),
    # ── S / T 单列（调整数 / 审定数）──────────────────────────────────
    ("closing_adjustment", "S", "editable", "amount", "closingAdjustment", "调整数", ""),
    #: 🔴 判 editable：模板 R12 整格无公式（同上）。前端按 `=Q+S` 重算覆盖。
    ("closing_adjusted", "T", "editable", "amount", "closingAdjusted", "审定数", ""),
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
