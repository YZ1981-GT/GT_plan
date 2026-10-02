# -*- coding: utf-8 -*-
"""I4-2「长期待摊费用明细表」—— sheet 层薄声明（I 循环第三张接入）。

spec: `i2-i4-i5-carrier-and-structure-exceptions` · Task 17

═══ 🔴 I4 是 definedName 基线口径的唯一实证场之一 ═══

本册 definedName **476**（I5 是 334，其余四册 I1/I2/I3/I6 全 0，合计 810）。

⇒ 判据 SHALL 用「**登记基线 + 断言不增长**」口径，**不得**照抄 H 循环 HC-14 的「断言全 0」——
那在 I1/I2/I3/I6 上恒真悄悄通过，**只有 I4/I5 会把它打红**。本册是捕获「照抄 H 口径」的地方。

🔴 **不删这 476 个**：它们是模板公式的命名引用，删了会让 `max_column` 内的公式整片失效。
只声明「同步时不新增、不改写」。

═══ 双区结构：R11-22 业务区 + R24-28 派生区 ═══

* 第 1 区 **R11-R22**（12 行）：受管业务行
* footer **R23**「合计」：`E23..S23` 各 `=SUM(x11:x22)`（A/B/C/D/T/U 无合计）
* 🔴 第 2 区 **R24「其中：」+ R25-R28**（4 行）：**派生区不受管**
  - A 列逐格 `=底稿目录!A9`..`=底稿目录!A12`（**4 类**，对应 CD-8 的分类源）
  - E..J 等列是 **ArrayFormula**（数组公式）按 B 列类别回汇总第 1 区
  ⇒ 按 IC-19 标 `derived`，**不纳入业务行比对**；否则 roundtrip 会把「第 1 区改动引起的
  派生区重算」判成用户编辑了派生区。

═══ 几何（openpyxl 逐格实测，禁推演）═══

`max_row=53` / `max_column=25` / **有效内容列 22（A..V）** / definedName **476** /
merged **27** / 无 Excel Table / `ws.protection.sheet=False`。

* 🔴 **三级表头 R8 / R9 / R10**（`header_group_row=8` + `header_leaf_row=10`
  ⇒ `header_rows = 10 - 8 + 1 = 3`）。
  各列 `header_text` 取**该列最深的非空标题**：A/B/C/D/E/T/U 在 R8 · F/G/J/K/L/O/P/S 在 R9 ·
  H/I/M/N/Q/R 在 R10。
* 数据区 **R11-R22**（12 行）
* 公式列 **J / O / P / Q / R / S**（逐行实测 R11/R12 一致）
* UUID 列 **W**（= 有效内容列 22 + 1）。`max_column` 是 25，差 3 列。

🔴 **`locked` 同样惰性**（`ws.protection.sheet=False`）⇒ mode 按「该格逐行有没有真公式」判。

═══ CD-8 = BP-8②：分类枚举后 3 条无真源 ═══

`CATEGORY_OPTIONS`（impl **6 条**）对源 `明细表I4-2!A11`（openpyxl 真读**仅 1 条**
`使用权资产改良及维护支出`；`A9`/`A10` 空 + `A12:A22` **全空**）
⇒ verdict `PREFIX_MATCH_WITH_UNSOURCED_TAIL`，无真源尾部 **3 条**
（`租入固定资产改良支出` / `固定资产大修理支出` / `开办费`）。
🔴 **修法归业务确认**（这三条是否属长期待摊费用的合法分类是会计判断）⇒ 本轮登记不修。

═══ 🔴 BP-5：`useI4FormData.ts` 是双零消费死代码，禁接 ═══

394 行、import 生产消费 **0** / import 测试消费 **0**（按 import 路径字面量三形态现算）。
对比同名同型的 `useI2FormData.ts`（501 行）消费计数 **4** 是**活代码** ——
三个 FormData 文件名同型但只有 I2 那个是活的，一刀切会把 I2 的写路径删掉。
本 sheet 契约 `forbidden_carriers` 显式禁接；🔴 **本轮不删文件**（删除是跨 spec 清理动作）。

═══ payload mode `dual_write` 未被真库证实 ═══

slice 记 I4 是 `dual_write_remark_and_conclusion_for_status_marker`，但真库 I 循环
**7 行全部 remark_only**（`conclusion` 全 NULL）⇒ 标 `unverified_in_live_db`，
**不得**把 slice 声明当已验证事实。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. 几何常量（逐格实测）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_I402: Final[str] = "明细表I4-2"
SHEET_KEY_I402: Final[str] = "i42-managed"
ROWS_TABLE_KEY_I402: Final[str] = "long_term_prepaid_rows"
TEMPLATE_ID_I402: Final[str] = "I42"
UUID_COL_I402: Final[str] = "W"
#: 🔴 三级表头：group=R8 / leaf=R10 ⇒ header_rows=3
HEADER_GROUP_ROW_I402: Final[int] = 8
HEADER_LEAF_ROW_I402: Final[int] = 10
FIRST_DATA_ROW_I402: Final[int] = 11
LAST_DATA_ROW_I402: Final[int] = 22
FOOTER_ROW_I402: Final[int] = 23
FOOTER_MARKER_I402: Final[str] = "合计"
EFFECTIVE_COLUMNS_I402: Final[int] = 22
MAX_COLUMN_I402: Final[int] = 25
#: 🔴 IC-10：definedName 基线（**非 0** —— 本册与 I5 是「基线不增长」口径的唯一实证场）
DEFINED_NAME_BASELINE_I402: Final[int] = 476

#: 🔴 IC-19：第二区是派生区，不受管、不纳入业务行比对。
DERIVED_REGION_I402: Final[dict[str, object]] = {
    "marker_row": 24,
    "marker_label": "其中：",
    "rows": [25, 28],
    "row_count": 4,
    "label_source": "底稿目录!A9:A12",
    "label_form": "A 列逐格 =底稿目录!A9..=底稿目录!A12",
    "value_form": "E..J 等列是 ArrayFormula（数组公式）按 B 列类别回汇总第 1 区",
    "editable_labels": False,
    "note": (
        "按 IC-19 标 derived、不纳入业务行比对；否则 roundtrip 会把「第 1 区改动引起的"
        "派生区重算」判成用户编辑了派生区。🔴 A 列标签由 `底稿目录` 下发 ⇒ 允许用户改会被"
        "下次 render 静默覆盖。"
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# 2. store 形态
# ═══════════════════════════════════════════════════════════════════════════

STORE_ITEM_ID_I402: Final[str] = "I4-2-rows"
ROW_IDENTITY_STORE_KEY_I402: Final[str] = "rowId"
EMPTY_PAYLOAD_I402: Final[str] = "[]"

#: 模板有列、store 侧是前端重算的派生值 ⇒ 只进 FORMULA_MASK，不进 field_specs。
TEMPLATE_ONLY_FORMULA_COLUMNS_I402: Final[tuple[tuple[str, str], ...]] = (
    ("J", "期末数（未审）"),
    ("O", "期初数（审定）"),
    ("P", "本期增加（审定）"),
    ("Q", "本期摊销（审定）"),
    ("R", "其他减少（审定）"),
    ("S", "期末数（审定）"),
)

TEMPLATE_CELL_LOCK_FACTS_I402: Final[dict[str, object]] = {
    "sheet_protection_enabled": False,
    "note": (
        "ws.protection.sheet=False ⇒ locked 惰性。契约 mode 一律按"
        "「该格逐行有没有真公式」判。"
    ),
}

#: 🔴 CD-8 = BP-8②（2026-10-01 resolved）：impl 比模板多出的 3 条**有税法条文依据**，
#: 模板 `A11` 只列 1 条是模板不完整，不是 impl 多列错。verdict 从
#: `PREFIX_MATCH_WITH_UNSOURCED_TAIL` 改为 `IMPL_AUTHORITATIVE_TEMPLATE_INCOMPLETE`。
#: 依据见 `useI4Detail.ts#I4_2_TAX_NOTES`：《企业所得税法》第十三条明列「租入固定资产的
#: 改建支出、固定资产的大修理支出及其他规定支出」作为长期待摊费用；《实施条例》第六十八条
#: 规定其认定与摊销；`开办费` 为筹建期费用的会计实务经典长期待摊科目。
#: `category` 是明细行自由下拉选项（非固定表结构行）⇒ 选项增减不影响已填数据 key。
CLASSIFICATION_FACTS_I402: Final[dict[str, object]] = {
    "impl_constant": "CATEGORY_OPTIONS",
    "impl_count": 6,
    "source_ref": "明细表I4-2!A11",
    "source_real_count": 1,
    "source_real_label": "使用权资产改良及维护支出",
    "source_empty_cells": "A9/A10 空 + A12:A22 全空",
    "verdict": "IMPL_AUTHORITATIVE_TEMPLATE_INCOMPLETE",
    "status": "resolved",
    "impl_authoritative_tail": ["租入固定资产改良支出", "固定资产大修理支出", "开办费"],
    "authority_refs": [
        "《企业所得税法》第十三条（租入固定资产改建支出 / 固定资产大修理支出 / 其他规定支出）",
        "《企业所得税法实施条例》第六十八条（大修理支出认定与摊销年限）",
        "会计实务：开办费为筹建期费用的长期待摊科目",
    ],
    "authority_impl_ref": "useI4Detail.ts#I4_2_TAX_NOTES",
    "resolution_note": (
        "模板不完整（A11 仅 1 条），impl 的税尾 3 条有税法条文依据 ⇒ 保留 impl 并登记依据。"
        "业务方如需增补常用分类见 evidence/classification-decision-and-business-checklist-2026-10-01.md B-2。"
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# 3. 字段声明（7 元组，顺序即 Excel 列序；跳过 6 个公式列）
# ═══════════════════════════════════════════════════════════════════════════

#: 15 个受管字段。`header_text` 取**该列最深的非空标题**
#: （A/B/C/D/E/T/U 在 R8 · F/G/K/L 在 R9 · H/I/M/N 在 R10）；
#: `group_header_cell` 给上一层组标题格坐标；`json_key` 逐字取 `useI4Detail.I4DetailRow`。
FIELD_SPECS_I402: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("project_name", "A", "editable", "text", "projectName", "项目名称", ""),
    ("category", "B", "editable", "text", "category", "类别", ""),
    ("asset_type", "C", "editable", "text", "assetType", "资产类型", ""),
    ("project_code", "D", "editable", "text", "projectCode", "项目编码", ""),
    ("original_amount", "E", "editable", "amount", "originalAmount", "初始入账金额", ""),
    ("unadj_opening", "F", "editable", "amount", "unadjOpening", "期初数", "F8"),
    ("unadj_increase", "G", "editable", "amount", "unadjIncrease", "本期增加", "F8"),
    (
        "unadj_amortization",
        "H",
        "editable",
        "amount",
        "unadjAmortization",
        "本期摊销",
        "H9",
    ),
    (
        "unadj_other_decrease",
        "I",
        "editable",
        "amount",
        "unadjOtherDecrease",
        "其他减少",
        "H9",
    ),
    ("opening_adj", "K", "editable", "amount", "openingAdj", "账项调整", "K8"),
    ("aje_increase", "L", "editable", "amount", "ajeIncrease", "本期增加", "L8"),
    (
        "aje_amortization",
        "M",
        "editable",
        "amount",
        "ajeAmortization",
        "本期摊销",
        "M9",
    ),
    (
        "aje_other_decrease",
        "N",
        "editable",
        "amount",
        "ajeOtherDecrease",
        "其他减少",
        "M9",
    ),
    ("index_no", "T", "editable", "text", "indexNo", "合同协议等索引号", ""),
    ("remark", "U", "editable", "text", "remark", "备注", ""),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R11/R12。
#: 🔴 `J` 与 `S` 是**减两项**口径（期初 + 增加 − 本期摊销 − 其他减少）。
FORMULA_TEMPLATES_I402: Final[dict[str, str]] = {
    "J": "=F{r}+G{r}-H{r}-I{r}",
    "O": "=F{r}+K{r}",
    "P": "=G{r}+L{r}",
    "Q": "=H{r}+M{r}",
    "R": "=I{r}+N{r}",
    "S": "=O{r}+P{r}-Q{r}-R{r}",
}
FORMULA_COLUMNS_I402: Final[tuple[str, ...]] = ("J", "O", "P", "Q", "R", "S")

# ═══════════════════════════════════════════════════════════════════════════
# 4. spec
# ═══════════════════════════════════════════════════════════════════════════

SPEC_I402: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_I402,
    sheet_key=SHEET_KEY_I402,
    table_key=ROWS_TABLE_KEY_I402,
    template_id=TEMPLATE_ID_I402,
    table_name=f"GT_{TEMPLATE_ID_I402}_ROWS",
    uuid_col=UUID_COL_I402,
    first_data_row=FIRST_DATA_ROW_I402,
    last_data_row=LAST_DATA_ROW_I402,
    footer_row=FOOTER_ROW_I402,
    header_group_row=HEADER_GROUP_ROW_I402,
    header_leaf_row=HEADER_LEAF_ROW_I402,
    store_item_id=STORE_ITEM_ID_I402,
    empty_payload=EMPTY_PAYLOAD_I402,
    row_identity_key=ROW_IDENTITY_STORE_KEY_I402,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_I402,
    formula_columns=FORMULA_COLUMNS_I402,
    formula_templates=FORMULA_TEMPLATES_I402,
    footer_marker=FOOTER_MARKER_I402,
    error_label="I4-2 长期待摊费用明细表",
)
