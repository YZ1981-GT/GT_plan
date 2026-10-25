# -*- coding: utf-8 -*-
"""I6-2「研发费用明细表」—— sheet 层薄声明（I 循环首张接入 canary）。

spec: `i-cycle-sync-foundation-and-first-canary` · Task 20 / 22

═══ 为什么选 I6-2 作 canary ═══

它是全 I 循环「真库有非空主表载荷 + 几何最简 + 与已接通形态同构」的唯一交集：

* 🔴 **真库非空主表载荷**：现算 `checklist_responses.remark`，I 前缀只 7 个 item_id 有行，
  6 条主表键里**只有 2 条非空** —— `I5-2-rows` 745 B（但 rowId 是 E2E 种子）与
  **`I6-2-detail-rows` 194 B / 2 行**。I1/I2/I3/I4 主表键 + `I6-2-rows`(legacy) 全部零载荷。
* **几何最简**：**单级表头 R8**（全 I 最浅）· 数据区 R9-18（10 行）· **84 公式** ·
  裸 `IF(` **45 格（全 I 最少）** · definedName **0** · merged **仅 2**（I1 是 72）。
* 🔴 **与 H10-2 / D4-2 高度同构**：12 月度列 B-M + 年度合计列 N=SUM(B:M) ⇒
  `months/0`…`months/11` 数组路径**复用 D4-2 已验通的范式**（`json_path` 是唯一数组段真源）。

三条逆风（如实登记，不粉饰）：

1. 🔴 **真库那 2 行原本既无 `id` 也无 `rowId`** ⇒ `useI6Detail.ts` 读时兜底每次生成新 id、
   roundtrip 恒判「全删全增」。已在 Task 19 一次性 backfill（`i6-detail-bf01-zhptyd` /
   `i6-detail-bf02-xplcsy`）；契约声明 `identity_backfill_required: True` 记录该前置。
2. 🔴 **主表键有 legacy alias `I6-2-rows`** 且 `I6-2-detail-rows` 被 **5 个跨 entry 消费方**读，
   其中 `h1DepAllocCounterpartPull.ts` 属 **H1 pilot**（adapter 已注册、golden 已锁）
   ⇒ 键名冻结，每次改动回归 H1 golden digest。
3. **BP-5②**：`useI6FormData.ts`（448 行）是**双零消费死代码**（import 生产 0 / 测试 0），
   却含完整 checklist GET/PUT + trial-balance/writeback 管道 ⇒ 契约 `forbidden_carriers`
   显式禁接，防「additive 注入即死代码」这个假绿第①源。

═══ 几何（openpyxl 逐格实测，禁推演）═══

`max_row=44` / `max_column=65` / **有效内容列 26（A..Z）** / **0 个 definedName** /
无 Excel Table / 册内有 `GT_Custom` hidden sheet / `ws.protection.sheet=False`。

* **单级**表头 **R8**（`header_row=8`）
* 数据区 **R9-R18**（10 行）
* footer **R19**「合计」：`B19..Y19` 各 `=SUM(x9:x18)`
* 🔴 **R20「各月比例」是第二派生行**（`B20 = =IF($N$19=0,0,B19/$N$19)`，仅 B..N 13 格）——
  它是 **R19 的派生**不是第二个合计锚点 ⇒ 引擎 `footer_row` 只取 **R19**；
  R20 不进受管区、插行时随 R19 的区间归一化自动跟随。契约的 `footer_rows=[19,20]` 是
  **事实声明**（供 roundtrip 判据知道 R20 不是业务行），与引擎锚点是两件事，不得混用。
* 公式列 **N / Q / R / W**（逐行实测 R9/R10 一致）：
  - `N{r} = SUM(B{r}:M{r})`　本期未审合计（12 月度列加总）
  - `Q{r} = N{r}+O{r}+P{r}`　本期审定数
  - `R{r} = IF(Q{r}=0,0,Q{r}/$Q$19)`　各项目占比（🔴 分母是 footer 的 `$Q$19` 绝对引用）
  - `W{r} = T{r}+U{r}+V{r}`　上期审定数
* UUID 列 **AA**（= 有效内容列 26 + 1）。🔴 **不得放 66**（`max_column` 是 65，
  有效与 max 之间 39 列全空 ⇒ 放 66 会让 OO 打开后列宽错位，IC-10/HC-13 同源规则）。

🔴 **`locked` 标志在本表同样惰性**：`ws.protection.sheet=False` ⇒ 数据行 26 列
`locked=True` 全是 Excel 默认值、不生效。契约 `mode` 一律按「该格逐行有没有真公式」判。

═══ 四个公式列**不进 field_specs** ═══

`N`/`Q`/`R`/`W` 在前端 `I6DetailStoredRow` 里**没有对应字段**（前端按同一套公式重算）
⇒ 按 D4-2 的口径（「P/S/T/U 是模板内部公式列，进 FORMULA_MASK 但不进契约」），
它们只进 `formula_columns`，**不进** `field_specs`。
反之 `expenseNature` 是 store 有字段、模板无列 ⇒ `store_only_fields`。

🔴 前端 `useI6Detail.ts` 的行类型注释把 `expenseNature` 标为「X列」有误 ——
X 列实测是 `个别报表下的重分类`（映射 `individualReclass`）。以模板叶子标题为权威（FC-5）。
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

MANAGED_SHEET_I602: Final[str] = "明细表I6-2"
SHEET_KEY_I602: Final[str] = "i62-managed"
ROWS_TABLE_KEY_I602: Final[str] = "rd_expense_detail_rows"
TEMPLATE_ID_I602: Final[str] = "I62"
UUID_COL_I602: Final[str] = "AA"
HEADER_ROW_I602: Final[int] = 8
FIRST_DATA_ROW_I602: Final[int] = 9
LAST_DATA_ROW_I602: Final[int] = 18
#: 🔴 引擎锚点只取 R19（真合计行）。R20「各月比例」是 R19 的派生，见模块 docstring。
FOOTER_ROW_I602: Final[int] = 19
FOOTER_MARKER_I602: Final[str] = "合计"
#: 事实声明：本表有**两个** footer 形态行。契约据此让 roundtrip 排除 R20 出业务行比对。
FOOTER_ROWS_FACT_I602: Final[tuple[int, ...]] = (19, 20)
FOOTER_KINDS_FACT_I602: Final[dict[int, str]] = {19: "pure_sum", 20: "ratio_footer"}
FOOTER_LABELS_FACT_I602: Final[dict[int, str]] = {19: "合计", 20: "各月比例"}
EFFECTIVE_COLUMNS_I602: Final[int] = 26
MAX_COLUMN_I602: Final[int] = 65

# ═══════════════════════════════════════════════════════════════════════════
# 2. store 形态
# ═══════════════════════════════════════════════════════════════════════════

STORE_ITEM_ID_I602: Final[str] = "I6-2-detail-rows"
#: 🔴 IC-4：读认两键、写只写主键。`LEGACY_STORAGE_KEY` 在 `useI6Detail.ts` 真存在。
LEGACY_STORE_ITEM_ID_I602: Final[str] = "I6-2-rows"
#: 🔴 身份字段是 `id` 不是 `rowId`（按 owner 常量现读，不按命名规律推断）。
ROW_IDENTITY_STORE_KEY_I602: Final[str] = "id"
EMPTY_PAYLOAD_I602: Final[str] = "[]"

#: store 有字段、模板无列 ⇒ 不映射任何格（merge 只动受管列，原样保留）。
STORE_ONLY_FIELDS_I602: Final[tuple[str, ...]] = ("expenseNature",)

#: 模板有列、store 无字段 ⇒ 只进 FORMULA_MASK，不进 field_specs（D4-2 同源口径）。
TEMPLATE_ONLY_FORMULA_COLUMNS_I602: Final[tuple[tuple[str, str], ...]] = (
    ("N", "本期未审合计"),
    ("Q", "本期审定数"),
    ("R", "各项目占比"),
    ("W", "上期审定数"),
)

#: 🔴 单元格锁标志实测事实（sheet 级保护未启用 ⇒ locked 惰性，不得据它判 mode）。
TEMPLATE_CELL_LOCK_FACTS_I602: Final[dict[str, object]] = {
    "sheet_protection_enabled": False,
    "data_row_all_locked": True,
    "note": (
        "ws.protection.sheet=False / 无密码 / workbook 未锁结构 ⇒ 数据行 26 列 locked=True "
        "全是 Excel 默认值不生效。契约 mode 一律按「该格逐行有没有真公式」判，"
        "merge._protection 也只看契约 mode + formula_mask，不读模板 locked。"
    ),
}

#: 🔴 IC-13 登记不修：R19 合计行对**文本列**与**占比列**也求和。
KNOWN_TEMPLATE_QUIRKS_I602: Final[tuple[str, ...]] = (
    "S19=SUM(S9:S18) 对文本列（与相关科目勾稽，模板值「开发支出等」）求和恒 0",
    "R19=SUM(R9:R18) 对占比列求和（语义勉强，各行占比之和≈1 无业务含义）",
)

# ═══════════════════════════════════════════════════════════════════════════
# 3. 字段声明（7 元组，顺序即 Excel 列序）
# ═══════════════════════════════════════════════════════════════════════════


def _month_field_specs() -> tuple[tuple[str, str, str, str, str, str, str], ...]:
    """B..M → `month_01`..`month_12`，json_key 用数组下标 `months/0`..`months/11`。

    🔴 数组段读写必须走 `app.services.workpaper_sync.json_path`（唯一允许的数组段实现真源）。
    D4-2 是首个生产形态，本表同构复用，不新造第二份解析。
    """
    return tuple(
        (
            f"month_{idx + 1:02d}",
            chr(ord("B") + idx),
            "editable",
            "amount",
            f"months/{idx}",
            f"{idx + 1}月",
            "",
        )
        for idx in range(12)
    )


#: 18 个受管字段（7 元组，第 7 位 `group_header_cell`）。
#: 顺序即 Excel 列序 A→Z（跳过 N/Q/R/W 四个模板内部公式列）；
#: `header_text` 逐字取模板 **R8** 叶子格；`group_header_cell` 全空（单级表头无横向分组）；
#: `json_key` 逐字取 `useI6Detail.I6DetailStoredRow`（除 12 个月度列用数组下标）。
FIELD_SPECS_I602: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("category", "A", "editable", "text", "category", "类别", ""),
    *_month_field_specs(),
    ("aje", "O", "editable", "amount", "aje", "账项调整", ""),
    ("rje", "P", "editable", "amount", "rje", "重分类调整", ""),
    ("reconciliation", "S", "editable", "text", "reconciliation", "与相关科目勾稽", ""),
    ("prior_unadj", "T", "editable", "amount", "priorUnadj", "上期未审数", ""),
    ("prior_aje", "U", "editable", "amount", "priorAje", "上期账项调整", ""),
    ("prior_rje", "V", "editable", "amount", "priorRje", "上期重分类调整", ""),
    (
        "individual_reclass",
        "X",
        "editable",
        "amount",
        "individualReclass",
        "个别报表下的重分类",
        "",
    ),
    (
        "consolidated_reclass",
        "Y",
        "editable",
        "amount",
        "consolidatedReclass",
        "合并报表下的重分类",
        "",
    ),
    ("remark", "Z", "editable", "text", "remark", "备注", ""),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R9/R10。
#: 🔴 `R` 的分母是 **footer 的绝对引用 `$Q$19`** —— 插行后区间归一化必须同步它，
#: 抄成相对引用会让每行占比指向错误的分母行。
FORMULA_TEMPLATES_I602: Final[dict[str, str]] = {
    "N": "=SUM(B{r}:M{r})",
    "Q": "=N{r}+O{r}+P{r}",
    "R": "=IF(Q{r}=0,0,Q{r}/$Q$19)",
    "W": "=T{r}+U{r}+V{r}",
}
FORMULA_COLUMNS_I602: Final[tuple[str, ...]] = ("N", "Q", "R", "W")

# ═══════════════════════════════════════════════════════════════════════════
# 4. spec
# ═══════════════════════════════════════════════════════════════════════════

SPEC_I602: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_I602,
    sheet_key=SHEET_KEY_I602,
    table_key=ROWS_TABLE_KEY_I602,
    template_id=TEMPLATE_ID_I602,
    table_name=f"GT_{TEMPLATE_ID_I602}_ROWS",
    uuid_col=UUID_COL_I602,
    first_data_row=FIRST_DATA_ROW_I602,
    last_data_row=LAST_DATA_ROW_I602,
    footer_row=FOOTER_ROW_I602,
    header_row=HEADER_ROW_I602,
    store_item_id=STORE_ITEM_ID_I602,
    empty_payload=EMPTY_PAYLOAD_I602,
    row_identity_key=ROW_IDENTITY_STORE_KEY_I602,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_I602,
    formula_columns=FORMULA_COLUMNS_I602,
    formula_templates=FORMULA_TEMPLATES_I602,
    footer_marker=FOOTER_MARKER_I602,
    error_label="I6-2 研发费用明细表",
)
