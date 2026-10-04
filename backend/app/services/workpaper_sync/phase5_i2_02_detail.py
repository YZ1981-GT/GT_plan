# -*- coding: utf-8 -*-
"""I2-2「开发支出明细表」—— sheet 层薄声明（I 循环第二张接入）。

spec: `i2-i4-i5-carrier-and-structure-exceptions` · Task 17

═══ 为什么 I2-2 排在 I6-2 之后 ═══

I6 是 canary（真库唯一可用非空载荷），I2-2 是**除 canary 外几何最简的单区表**：
单区（无派生区）· 有效列 **20**（A..T）· 数据区 R13-22 十行 · footer R23 纯 SUM。

🔴 但 I2 是 I 循环**唯一「双例外」**的 entry，本 sheet 的契约必须带这两条声明：

1. **唯一缺二级 UI 门控**：宿主 `isOoAvailable` 与「仅结构化视图」tag 命中**均为 0**
   ⇒ OO 探测失败时切换按钮照样显示（违反 AC 1.5「不显示不可兑现的按钮」）。
2. **唯一发布门不在 composable 而在 `.vue` 自建**：`useI2Adjudication.ts` 里 `publishToTb`
   **0 命中**，门在 `I2TabAdjudication.vue#L384` ⇒ 契约 `gate_layer = "host_tab"`。
   🔴 若判据写成「composable 里必须有 `publishToTb`」，**I2 会假红** ——
   「I 循环 6/6 全有发布门」是 **entry 维度**成立的结论。

═══ 🔴 主表键 `I2-2-rows` 是跨 lane 冻结键 ═══

`composables/useI1AdditionCheck.ts#L250-251` 跨 entry 读它，且读法是
`allResponses.get('I2-2-rows')?.remark ?? ?.conclusion`（**remark 优先、conclusion 兜底**）
⇒ ①键名冻结 ②`payload_column_mode` 从 `remark_only` 改成别的会影响那条消费边。
另 `composables/i2ConsistencyModel.ts#L213` 的前缀映射 `'I2-2-': ['I2-2-rows']` 也依赖它。

═══ 几何（openpyxl 逐格实测，禁推演）═══

`max_row=51` / `max_column=61` / **有效内容列 20（A..T）** / **0 个 definedName** /
merged **21** / 无 Excel Table / `ws.protection.sheet=False`。

* 🔴 **三级表头 R10 / R11 / R12**（`header_group_row=10` + `header_leaf_row=12`
  ⇒ `header_rows = 12 - 10 + 1 = 3`）。
  各列的 `header_text` 取**该列最深的非空标题**：A/Q/R/S/T 在 R10 · B/G/H/I/L/M/P 在 R11 ·
  C/D/E/F/J/K/N/O 在 R12。照「统一取 leaf 行」会让 12 列取到 None。
* 数据区 **R13-R22**（10 行）
* footer **R23**「合计」：`B23..P23` 各 `=SUM(x13:x22)`；🔴 **`R23` 例外是 `=P23-Q23`**
  （footer 行套用**行公式**而不是 SUM —— 同 I3-2 R23 的 `row_formula_applied` 形态，
  但本表只有 R 列一格如此，其余 14 格是纯 SUM）⇒ `footer_carries_total_formula=True` 成立，
  但 roundtrip 判据**不得**假设 footer 全列同形态。
* 公式列 **G / L / M / N / O / P / R**（逐行实测 R13/R14 一致）
* UUID 列 **U**（= 有效内容列 20 + 1）。🔴 **不得放 62** —— `max_column` 是 61，
  有效与 max 之间 **41 列全空**（全 I 差距最大的一册），放 62 会让 OO 打开后列宽错位。

🔴 **`locked` 同样惰性**（`ws.protection.sheet=False`）⇒ mode 一律按「该格逐行有没有真公式」判。

═══ 七个公式列**不进 field_specs** ═══

`G`/`L`/`M`/`N`/`O`/`P`/`R` 在 `useI2Detail.I2DetailRow` 里虽有同名字段
（`unadjEnding` / `auditedOpening` / … / `diffVsIA`），但它们是**前端按同一套公式重算的派生值**
（行类型注释逐条标了「公式 G = B+C-E-F」等）⇒ 按 D4-2 口径只进 `formula_columns`、
**不进** `field_specs`，`formula_mask` 保证 OO 侧不被 HTML 的派生值覆盖。
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

MANAGED_SHEET_I202: Final[str] = "明细表I2-2"
SHEET_KEY_I202: Final[str] = "i22-managed"
ROWS_TABLE_KEY_I202: Final[str] = "development_expenditure_rows"
TEMPLATE_ID_I202: Final[str] = "I22"
UUID_COL_I202: Final[str] = "U"
#: 🔴 三级表头：group=R10 / leaf=R12 ⇒ header_rows=3
HEADER_GROUP_ROW_I202: Final[int] = 10
HEADER_LEAF_ROW_I202: Final[int] = 12
FIRST_DATA_ROW_I202: Final[int] = 13
LAST_DATA_ROW_I202: Final[int] = 22
FOOTER_ROW_I202: Final[int] = 23
FOOTER_MARKER_I202: Final[str] = "合计"
EFFECTIVE_COLUMNS_I202: Final[int] = 20
MAX_COLUMN_I202: Final[int] = 61

# ═══════════════════════════════════════════════════════════════════════════
# 2. store 形态
# ═══════════════════════════════════════════════════════════════════════════

STORE_ITEM_ID_I202: Final[str] = "I2-2-rows"
ROW_IDENTITY_STORE_KEY_I202: Final[str] = "rowId"
EMPTY_PAYLOAD_I202: Final[str] = "[]"

#: 🔴 跨 lane 冻结键的消费方（lane 1 的 I1 + I2 自身的一致性前缀表）。
FROZEN_CROSS_REF_I202: Final[tuple[str, ...]] = (
    "composables/useI1AdditionCheck.ts#L250-251（remark 优先 / conclusion 兜底，跨 entry）",
    "composables/i2ConsistencyModel.ts#L213（前缀映射 'I2-2-': ['I2-2-rows']）",
)

#: 模板有列、store 侧是前端重算的派生值 ⇒ 只进 FORMULA_MASK，不进 field_specs。
TEMPLATE_ONLY_FORMULA_COLUMNS_I202: Final[tuple[tuple[str, str], ...]] = (
    ("G", "期末数（未审）"),
    ("L", "期初数（审定）"),
    ("M", "本期增加（审定）"),
    ("N", "计入无形资产/存货（审定减少）"),
    ("O", "计入当期损益（审定减少）"),
    ("P", "期末数（审定）"),
    ("R", "差异"),
)

TEMPLATE_CELL_LOCK_FACTS_I202: Final[dict[str, object]] = {
    "sheet_protection_enabled": False,
    "note": (
        "ws.protection.sheet=False ⇒ locked 标志惰性。契约 mode 一律按"
        "「该格逐行有没有真公式」判，merge._protection 只看契约 mode + formula_mask。"
    ),
}

#: 🔴 footer 行**不是单一形态**（登记，供 roundtrip 判据不做统一假设）。
FOOTER_SHAPE_FACTS_I202: Final[dict[str, object]] = {
    "pure_sum_columns": ["B", "C", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P"],
    "row_formula_applied_columns": ["R"],
    "row_formula_applied_detail": "R23 = =P23-Q23（套用行公式，非 SUM）",
    "empty_columns": ["D", "Q", "S", "T"],
    "note": (
        "同一 footer 行两种约定：14 格纯 SUM + 1 格套用行公式（同 I3-2 R23 的 "
        "row_formula_applied 形态，但本表只有 R 一格）⇒ 按单一约定校验会有一格假红。"
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# 3. 字段声明（7 元组，顺序即 Excel 列序；跳过 7 个公式列）
# ═══════════════════════════════════════════════════════════════════════════

#: 13 个受管字段。`header_text` 取**该列最深的非空标题**（A/Q/S/T 在 R10、B/H/I 在 R11、
#: C/D/E/F/J/K 在 R12）；`group_header_cell` 给上一层组标题格坐标。
#: `json_key` 逐字取 `useI2Detail.I2DetailRow`。
FIELD_SPECS_I202: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("project_name", "A", "editable", "text", "projectName", "研究开发项目名称", ""),
    ("unadj_opening", "B", "editable", "amount", "unadjOpening", "期初数", "B10"),
    ("unadj_increase", "C", "editable", "amount", "unadjIncrease", "金额", "C11"),
    ("increase_method", "D", "editable", "text", "increaseMethod", "增加方式", "C11"),
    (
        "unadj_dec_to_ia",
        "E",
        "editable",
        "amount",
        "unadjDecToIA",
        "计入无形资产/存货",
        "E11",
    ),
    ("unadj_dec_to_pl", "F", "editable", "amount", "unadjDecToPL", "计入当期损益", "E11"),
    ("opening_adj", "H", "editable", "amount", "openingAdj", "账项调整", "H10"),
    ("aje_increase", "I", "editable", "amount", "ajeIncrease", "本期增加", "I10"),
    ("aje_dec_to_ia", "J", "editable", "amount", "ajeDecToIA", "计入无形资产/存货", "J11"),
    ("aje_dec_to_pl", "K", "editable", "amount", "ajeDecToPL", "计入当期损益", "J11"),
    (
        "related_ia_audited_end",
        "Q",
        "editable",
        "amount",
        "relatedIAAuditedEnd",
        "无形资产/存货科目记录期末审定数",
        "",
    ),
    ("rd_progress", "S", "editable", "text", "rdProgress", "截至期末的研发进度", ""),
    ("remark", "T", "editable", "text", "remark", "备注", ""),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R13/R14。
#: 🔴 `G` 与 `P` 是**减两项**口径（期初 + 增加 − 计入资产 − 计入损益），
#: 抄成「期初 + 增加 − 减少」会漏掉一个减项。
FORMULA_TEMPLATES_I202: Final[dict[str, str]] = {
    "G": "=B{r}+C{r}-E{r}-F{r}",
    "L": "=B{r}+H{r}",
    "M": "=C{r}+I{r}",
    "N": "=E{r}+J{r}",
    "O": "=F{r}+K{r}",
    "P": "=L{r}+M{r}-N{r}-O{r}",
    "R": "=P{r}-Q{r}",
}
FORMULA_COLUMNS_I202: Final[tuple[str, ...]] = ("G", "L", "M", "N", "O", "P", "R")

# ═══════════════════════════════════════════════════════════════════════════
# 4. spec
# ═══════════════════════════════════════════════════════════════════════════

SPEC_I202: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_I202,
    sheet_key=SHEET_KEY_I202,
    table_key=ROWS_TABLE_KEY_I202,
    template_id=TEMPLATE_ID_I202,
    table_name=f"GT_{TEMPLATE_ID_I202}_ROWS",
    uuid_col=UUID_COL_I202,
    first_data_row=FIRST_DATA_ROW_I202,
    last_data_row=LAST_DATA_ROW_I202,
    footer_row=FOOTER_ROW_I202,
    header_group_row=HEADER_GROUP_ROW_I202,
    header_leaf_row=HEADER_LEAF_ROW_I202,
    store_item_id=STORE_ITEM_ID_I202,
    empty_payload=EMPTY_PAYLOAD_I202,
    row_identity_key=ROW_IDENTITY_STORE_KEY_I202,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_I202,
    formula_columns=FORMULA_COLUMNS_I202,
    formula_templates=FORMULA_TEMPLATES_I202,
    footer_marker=FOOTER_MARKER_I202,
    error_label="I2-2 开发支出明细表",
)
