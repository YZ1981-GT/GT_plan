# -*- coding: utf-8 -*-
"""G14-2「信用减值损失明细表」—— sheet 层薄声明（固定 9 行 + 布尔核对列）。

spec: `g-cycle-single-region-detail-lanes` · Task 10 / C-9
　　　列模型依据 `evidence/task8-c6-remaining-eight-template-logic.md` §4 + 本轮逐格实测

═══ 几何（openpyxl 逐格实测，禁推演）═══

`明细表G14-2`：`max_row=36` / `max_column=13` / **0 个 definedName**。

* **两级**表头 **R9（组）/ R10（叶子）** —— R9 的**横向**合并区只有两个：
  `B9:D9` 本期数 · `F9:K9` 对应科目-减值准备。
  另有四个跨两行的单列合并（`A9:A10` 项目 · `E9:E10` 对应科目 ·
  `L9:L10` 核对 · `M9:M10` 索引号）。
* **固定 9 行** R11-R19（行集由模板 A 列写死，见 :data:`TEMPLATE_ROW_LABELS_G1402`），
  footer **R20** 合计（逐列 `=SUM(x11:x19)`，🔴 `L20` 例外是布尔 `=D20=K20`）。
* 有效内容列 **13**（A..M）—— 与 `max_column` 相等（全满，无空尾列）⇒ UUID 列取 `N`。
* R21「三、审计说明：」/ R23「四、审计结论：」在受管区之外。

═══ 🔴 一：固定行集 —— 行数必须恰是 9 ═══

行表引擎按**数组顺序**把 store 行映射到 R11-R19。改造前前端自研了第 10 行
`rowKey: 'ca'`（合同资产减值损失），10 行数据落进 9 行区会扩行、把 footer R20 挤下去。
已按选项 A 把合同资产的 1142 取数、D6 的 ECL 事件、含「合同资产」的调整分录三处落点
并入模板 R19「其他」行（前端 `DROPPED_LEGACY_G14_ROWS` 记了原因）。

行身份是 `rowKey`（`stable_template_row_key`）—— 全 G 循环唯一一家不用生成式 id 的，
GC-6 裁决它是**最稳**的一族（源模板固定行集，插行/改名都不漂移）。
🔴 照抄 F 循环的 `row_identity_key in ('rowId','id')` 白名单会把它判违规。

═══ 🔴 二：`K` 列公式是模板缺陷（`=G+H` 应为 `=G-H`）═══

逐格实测 R11-R19 四个公式列（每行同型）：

| 列 | 模板公式 | 口径 |
|---|---|---|
| `D` | `=B{r}+C{r}` | 审定数 = 未审 + 调整 |
| `J` | `=F{r}+G{r}-H{r}-I{r}` | 期末余额 = 期初 + 计提 − 转回 − 转销 |
| `K` | `=G{r}+H{r}` | 🔴 计入损益，**应为 `=G-H`** |
| `L` | `=D{r}=K{r}` | 布尔核对：审定数 == 计入损益 |

`J` 要求 `H`「本期转回」填**正数**（转回减少准备）。同一张表里 `K=G+H` 却把转回当成
**增加**损益 —— 两式对 `H` 的符号约定互相矛盾，必有一错。判定「`K` 错」的三条依据：

1. 会计口径：信用减值损失（损益）= 本期计提 − 本期转回，转回冲减损益；
2. `J` 的形式与准则口径「期初 + 计提 − 转回 − 转销 = 期末」逐字一致，它是对的；
3. 平台早已裁定「转回填正数」—— 前端 `useG14FormulaEngine.migrateReversalToPositive`
   专门把历史负数统一成正数。

处置同 G8 的模板缺陷口径：`K` 在模板**每行都有公式** ⇒ 判 `mode=formula`（进
:data:`FORMULA_COLUMNS_G1402`，OO 侧改不了），`formula_templates` 逐字记模板原式
（判据要逐格比对模板，记成 `=G-H` 会必红）。前端按会计正确口径 `计提 − 转回` 算 ⇒
**有转回时 Excel 侧 `K` 比平台侧多 2×转回**。这个差异是如实登记的欠账（见 spec
evidence `task10-c9-g14-rootfix.md` §2.2）：修模板要么改字节（`backend/wp_templates/`
运行时只读 + sha 冻结，禁止）、要么走覆盖层（框架层尚无该机制）+ 会计专业复核。
🔴 模板自带的 `L=D=K` 核对列会在有转回时显示不平 —— 用户看得见，不是静默错。

═══ 🔴 三：`L` 是布尔校验列（裁决 G1R-H4）═══

`L{r} = =D{r}=K{r}` 求值为 TRUE/FALSE ⇒ `value_type="boolean"` + `mode="formula"`。
按值读 `excel_extract.py`：对 formula 格也读值并 `normalize_value`，失败记
`SchemaAnomalyKind.type_normalization_failure` 并保留原值；`PROTECTED_MODES` 使其
不入 store。判据三条（P9）：①extract 不抛 ②异常类型是 `type_normalization_failure`
③store 中该字段不出现 `TRUE`/`FALSE` 字面量。与 F5 变动率除零（`#DIV/0!`）同族。

═══ 字段键逐字取自前端行接口 ═══

`useG14Detail.G14DetailRow` 的**前 13 个**字段（与模板列序 A..M 逐列对应）。
其后三个（`tbClosing`/`tbClosingMatched`/`tbClosingVariance`）是试算余额对账的派生值，
**不是模板列、不受管、不进 store**。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G1402",
    "MANAGED_SHEET_G1402",
    "STORE_ITEM_ID_G1402",
    "FORMULA_TEMPLATES_G1402",
    "FORMULA_COLUMNS_G1402",
    "BOOLEAN_COLUMNS_G1402",
    "TEMPLATE_ROW_LABELS_G1402",
    "TEMPLATE_ROW_DEFECTS_G1402",
    "FRONTEND_ONLY_FIELDS_G1402",
    "FIELD_SPECS_G1402",
    "FOOTER_ROW_G1402",
]

MANAGED_SHEET_G1402: Final[str] = "明细表G14-2"
TEMPLATE_ID_G1402: Final[str] = "G1402"
SHEET_KEY_G1402: Final[str] = "g1402-managed"

#: 🔴 按值取自 `useG14Detail.ts` 的 `ITEM_ID_ROWS`，**不按 sheet 号推演**。
STORE_ITEM_ID_G1402: Final[str] = "G14-detail-rows"
#: 🔴 全 G 循环唯一的 `rowKey`（`stable_template_row_key`，GC-6 裁决为最稳一族）
ROW_IDENTITY_STORE_KEY_G1402: Final[str] = "rowKey"

HEADER_GROUP_ROW_G1402: Final[int] = 9
HEADER_LEAF_ROW_G1402: Final[int] = 10
FIRST_DATA_ROW_G1402: Final[int] = 11
LAST_DATA_ROW_G1402: Final[int] = 19
#: footer 合计行（**不受管**）：逐列 `=SUM(x11:x19)`，`L20` 例外是布尔 `=D20=K20`
FOOTER_ROW_G1402: Final[int] = 20
FOOTER_MARKER_G1402: Final[str] = "合计"

#: 🔴 模板 A 列 R11-R19 的**固定行序**（逐字实测）。受管行集必须逐项等于它 ——
#: 行表引擎按数组顺序映射，多一行就扩行、把 footer 挤下去。
#: 前端侧的同一份真源是 `g14Constants.G14_TEMPLATE_ROW_LABELS`，判据双向锁。
TEMPLATE_ROW_LABELS_G1402: Final[tuple[str, ...]] = (
    "应收票据坏账损失",
    "应收账款坏账损失",
    "应收款项融资坏账损失",
    "其他应收款坏账损失",
    "债权投资减值损失",
    "其他债权投资减值损失",
    "长期应收款坏账损失",
    "财务担保预计损失",
    "其他",
)

#: 4 个公式列（模板 R11-R19 每行都有，逐行同型）
FORMULA_COLUMNS_G1402: Final[tuple[str, ...]] = ("D", "J", "K", "L")

#: 🔴 布尔校验列（裁决 G1R-H4）：求值为 TRUE/FALSE，`value_type="boolean"`
BOOLEAN_COLUMNS_G1402: Final[tuple[str, ...]] = ("L",)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。**逐字实测**自 R11 且 R11-R19 同型。
#: 🔴 `K` 逐字记模板原式 `=G+H`（含缺陷）—— 判据逐格比对模板，记成 `=G-H` 会必红。
#:   会计正确口径 `计提 − 转回` 由前端算，差异见模块头与 TEMPLATE_ROW_DEFECTS。
FORMULA_TEMPLATES_G1402: Final[dict[str, str]] = {
    "D": "=B{r}+C{r}",                      # 审定数 = 未审 + 调整
    "J": "=F{r}+G{r}-H{r}-I{r}",            # 期末余额 = 期初 + 计提 − 转回 − 转销
    "K": "=G{r}+H{r}",                      # 🔴 计入损益，应为 =G-H（模板缺陷）
    "L": "=D{r}=K{r}",                      # 布尔核对：审定数 == 计入损益
}

#: 模板缺陷台账（逐格实测）。判据按它断言「缺陷仍在」—— 一旦模板被修复，判据会红并
#: 提示同步更新本表与 `FORMULA_TEMPLATES_G1402`（而不是静默失配）。
TEMPLATE_ROW_DEFECTS_G1402: Final[
    tuple[tuple[str, tuple[int, ...], str], ...]
] = (
    (
        "K",
        tuple(range(11, 20)),
        "=G{r}+H{r} 把「本期转回」当成增加损益；同表 J 的 -H 要求 H 填正数 ⇒ "
        "会计正确应为 =G{r}-H{r}（信用减值损失 = 计提 − 转回）",
    ),
)

#: 前端行接口里**不是模板列**的派生字段（试算余额对账用，不受管、不进 store）。
FRONTEND_ONLY_FIELDS_G1402: Final[tuple[str, ...]] = (
    "tbClosing",
    "tbClosingMatched",
    "tbClosingVariance",
)

#: 13 个受管字段（7 元组 `(column_key, column, mode, value_type, json_key, header_text, group_header_cell)`）。
#:
#: 顺序即 Excel 列序 A→M；`header_text` 逐字取模板（落在 R9 横向合并区内的取叶子行 R10，
#: 跨两行合并的单列取 R9）；`json_key` 逐字取 `useG14Detail.G14DetailRow`。
FIELD_SPECS_G1402: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("line_label", "A", "editable", "text", "label", "项目", ""),
    # ── B9:D9 本期数 ───────────────────────────────────────────────────
    ("current_unadjusted", "B", "editable", "amount", "currentUnadjusted", "未审数", "B9"),
    ("current_adjustment", "C", "editable", "amount", "currentAdjustment", "调整数", "B9"),
    ("current_audited", "D", "formula", "amount", "currentAudited", "审定数", "B9"),
    # ── E 单列（对应科目）─────────────────────────────────────────────
    ("provision_account", "E", "editable", "text", "provisionAccount", "对应科目", ""),
    # ── F9:K9 对应科目-减值准备 ────────────────────────────────────────
    ("opening_provision", "F", "editable", "amount", "openingProvision", "期初余额", "F9"),
    ("current_provision", "G", "editable", "amount", "currentProvision", "本期计提", "F9"),
    #: 🔴 「本期转回」填**正数**（J 的 -H 与前端 migrateReversalToPositive 同口径）
    ("current_reversal", "H", "editable", "amount", "currentReversal", "本期转回", "F9"),
    ("current_writeoff", "I", "editable", "amount", "currentWriteoff", "本期转销", "F9"),
    ("closing_provision", "J", "formula", "amount", "closingProvision", "期末余额", "F9"),
    #: 🔴 模板公式 `=G+H` 是缺陷（应 `=G-H`）；每行都有公式 ⇒ 仍判 formula
    ("profit_loss", "K", "formula", "amount", "profitLoss", "计入损益", "F9"),
    # ── L / M 单列（布尔核对 / 索引号）────────────────────────────────
    #: 🔴 布尔校验列（裁决 G1R-H4）：`value_type="boolean"` + `mode="formula"`
    ("reconcile_check", "L", "formula", "boolean", "reconciled", "核对", ""),
    ("index_ref", "M", "editable", "text", "indexRef", "索引号", ""),
)

SPEC_G1402: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_G1402,
    sheet_key=SHEET_KEY_G1402,
    table_key="g14_detail_rows",
    template_id=TEMPLATE_ID_G1402,
    table_name=f"GT_{TEMPLATE_ID_G1402}_DETAIL_ROWS",
    #: 🔴 有效内容列 13（A..M）**恰等于** `max_column` —— 这张表没有空尾列，
    #:   所以 UUID 列取 `N` 时「有效列右移一列」与「max_column+1」两个口径**重合**。
    #:   G10/G8 是 max_column 含空列的情形（取有效列口径），此处不构成反例。
    uuid_col="N",
    first_data_row=FIRST_DATA_ROW_G1402,
    last_data_row=LAST_DATA_ROW_G1402,
    footer_row=FOOTER_ROW_G1402,
    header_group_row=HEADER_GROUP_ROW_G1402,
    header_leaf_row=HEADER_LEAF_ROW_G1402,
    store_item_id=STORE_ITEM_ID_G1402,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_G1402,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_G1402,
    formula_columns=FORMULA_COLUMNS_G1402,
    formula_templates=FORMULA_TEMPLATES_G1402,
    footer_marker=FOOTER_MARKER_G1402,
    error_label="G14-2 信用减值损失明细表",
    #: 幽灵行锚点用默认 `[0]`（A 列「项目」）—— 固定行集下 A 列恒非空（模板预填 9 个
    #: 行名），任何一行都不会被当幽灵行剔除。
)
