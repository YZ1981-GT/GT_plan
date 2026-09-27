# -*- coding: utf-8 -*-
"""J1-6「计提情况检查表」短期薪酬区 —— sheet 层薄声明（J 循环 canary）。

spec: `j-cycle-sync-foundation-and-first-canary` · Task 21 / 22

═══ 🔴 canary 选型：D~I 的硬标准在 J 不成立，须改口径 ═══

D~I 六轮的硬标准是「**primary managed table** 真库有非空载荷」。但 J 循环：
`J1-2-detail-{shortTerm,postEmployment,severance}` 三键 + `J1-1-rows`（审定表）
+ `J1-3-adjustment-rows`（调整分录）**真库全部无行**。

⇒ 硬标准改四项：**真库有非空载荷 + 在 entry 内 + 非 parent_duplicate + 单 sheet 单键组**。
`J1-6-short-term` 真库 **3473 B（全 J 最大）** 且满足其余三项 ⇒ 选它。

四候选裁决：

| 候选 | 真库 | 裁决 |
|---|---|---|
| ✅ **`J1-6-short-term`** | **3473 B** | entry 内 / 非 parent_dup / 单 sheet 单键组 / id 形态安全 |
| ❌ `J1-disc-soe-short-term` | 1325 B **且有真金额** | 披露层叠 5 个最难形态（双变体 / 49 硬编码 id / **同 id 跨变体语义不同** / 第三条写路径写另一张表 / 非行对行映射） |
| ❌ `J1-8-voucher-check` | 911 B | 属 **parent_duplicate** ⇒ 不独立发布 contract / bundle / candidate / evidence |
| ❌ `J1-2-detail-*` | **0 B** | primary managed table 真库空，不满足硬标准 |

🔴 **三条逆风如实登记**：

1. **3473 B 载荷的金额字段全 0**（`baseAmount`/`rate`/`estimated`/`actual`/`diff` 全 0；
   `baseName`/`baseIndex`/`diffReason`/`conclusion` 全空串）⇒ 它是「**骨架已落库、业务未填**」
   ⇒ roundtrip 只能验结构 ⇒ 须**另造带金额的合成载荷**补第二轮。
2. **RD-5 三边校验缺口须在 canary 内先补**（见下方「RD-5」节）。
3. 同 Tab 的 `J1-6-questions` **901 B 是 AI 生成 markdown 长文本**（5 元素字符串数组，
   首元素是含 `###` 标题与列表的整段中文）⇒ representation 须区分
   「结构化行数组」与「自由文本数组」两种 shape。

═══ 几何（openpyxl 逐格实测）═══

`max_row=60` / `max_column=11` / **有效内容列 11（A..K，两者相等）** / definedName **0** /
merged **17** / 无 Excel Table / `ws.protection.sheet=False` / 63 公式 /
🔴 **本 sheet 裸 IF 0**（整册 J1 是 224，但本表一个都没有）。

* **分区标题行 R14**：`（1）短期薪酬`
* 🔴 **两级表头 R15 / R16**（`header_group_row=15` + `header_leaf_row=16` ⇒ `header_rows=2`）
  —— R15 是 `项目 / 计提基数 / 计提比例 / 应提金额 / 实际计提数 / 差异 / 差异原因 / 结论`，
  R16 只有 `C=名称 / D=金额 / E=索引`（计提基数的三个子列）
* 数据区 **R17-R35（19 行）**
* 🔴 **`footer_rows: []` —— 本 sheet 无 footer 合计行**。R36 只有 G/I 两个公式（`=ROUND(D36*F36,2)`
  / `=G36-H36`）但 **A36 无标签**，R37 已是第二分区标题 `（2）离职后福利中设定提存计划…`
  ⇒ R36 是**模板预留的第 20 行**不是 footer。
  🔴 引擎 `footer_row` 仍须给一个值（dataclass 必填）⇒ 给 **36**（预留行）并在契约里
  显式声明 `footer_rows: []` + `footer_carries_total_formula=False`；
  判据 SHALL 断言该行**无 `合计` 标签**，变异「把它当 footer 验合计公式」SHALL 打红。
* 第二分区 **R37/R38 + R40-47**（离职后福利，对应 `J1-6-post-employment` 键）⇒ 本批不接
* 公式列 **G / I**：`G{r} = ROUND(D{r}*F{r}, 2)` · `I{r} = G{r}-H{r}`
* UUID 列 **L**（= 有效内容列 11 + 1）

═══ 🔴 RD-5（本轮新登记）：`SHORT_TERM_DEFAULTS` 19 项 vs 模板 A17:A35 十处不等 ═══

行数 **19/19 一致**但内容 10 处不等，三类分开记：

| 类 | 处数 | 差异 |
|---|---|---|
| ① 序号分隔符 | 9 | 模板**全角 `．`**（U+FF0E）/ impl **半角 `.`** |
| ② 缩进前缀 | 9（同上 9 处） | 模板带 **3 个全角空格 `\u3000`** / impl 无前缀（靠 `indent: 1` 字段表达） |
| ③ 🔴 **单元格内换行符** | **1** | 模板 `八、辞退福利\n（因解除劳动关系给予的补偿）` / impl 写成一行 |

🔴 **禁标点归一化**（`NFKC` 会同时洗掉 RD-2 的 5 处与本条的 9 处）⇒ 逐格**字节**比对。
🔴 修法标 `[ ]*`（业务确认改哪一侧）；本 sheet spec 只登记差异清单，
**不**把错标签固化进契约 —— `header_text` 取**模板原字节**。
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

MANAGED_SHEET_J106: Final[str] = "计提情况检查表J1-6"
SHEET_KEY_J106: Final[str] = "j16-short-term-managed"
ROWS_TABLE_KEY_J106: Final[str] = "accrual_check_short_term_rows"
TEMPLATE_ID_J106: Final[str] = "J16S"
UUID_COL_J106: Final[str] = "L"
SECTION_TITLE_ROW_J106: Final[int] = 14
SECTION_TITLE_J106: Final[str] = "（1）短期薪酬"
#: 🔴 两级表头：group=R15 / leaf=R16 ⇒ header_rows=2
HEADER_GROUP_ROW_J106: Final[int] = 15
HEADER_LEAF_ROW_J106: Final[int] = 16
FIRST_DATA_ROW_J106: Final[int] = 17
LAST_DATA_ROW_J106: Final[int] = 35
#: 🔴 **本 sheet 无 footer 合计行**。R36 是模板预留的第 20 行（只有 G/I 公式、A36 无标签），
#: R37 已是第二分区标题。引擎 dataclass 必填 footer_row ⇒ 给 36 并在契约声明 footer_rows=[]。
FOOTER_ROW_J106: Final[int] = 36
FOOTER_MARKER_J106: Final[str] = ""
EFFECTIVE_COLUMNS_J106: Final[int] = 11
MAX_COLUMN_J106: Final[int] = 11

#: 🔴 无 footer 的事实声明（供判据断言该行无「合计」标签）。
NO_FOOTER_FACTS_J106: Final[dict[str, object]] = {
    "footer_rows": [],
    "reserved_row": 36,
    "reserved_row_evidence": (
        "R36 只有 G36=`=ROUND(D36*F36,2)` 与 I36=`=G36-H36` 两个公式，**A36 无标签**；"
        "R37 已是第二分区标题 `（2）离职后福利中设定提存计划、其他长期福利中符合设定提存条件的负债`"
        "⇒ R36 是**模板预留的第 20 行**不是 footer。"
    ),
    "engine_footer_row_is_placeholder": True,
    "assertion": (
        "🔴 判据 SHALL 断言 R36 **无 `合计` 标签** 且 `footer_carries_total_formula=False`；"
        "变异「把它当 footer 验合计公式」SHALL 打红。"
        "🔴 更不得套 `明细表J1-2 ` 的「B 列 + 三 footer」口径 —— 本表按 **A 列非空**判业务行。"
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# 2. store 形态
# ═══════════════════════════════════════════════════════════════════════════

STORE_ITEM_ID_J106: Final[str] = "J1-6-short-term"
#: 🔴 J 循环行身份字段是 `id` 不是 `rowId`（按 owner 常量现读）。
ROW_IDENTITY_STORE_KEY_J106: Final[str] = "id"
EMPTY_PAYLOAD_J106: Final[str] = "[]"

#: 🔴 同 Tab 的三个兄弟键 shape **三值不同**（representation 必须区分）。
SIBLING_SHAPES_J106: Final[dict[str, str]] = {
    "J1-6-short-term": "structured_row_array",
    "J1-6-post-employment": "structured_row_array",
    "J1-6-questions": "free_text_array",
    "J1-6-conclusion": "free_text_scalar",
}
SIBLING_SHAPES_NOTE_J106: Final[str] = (
    "🔴 `J1-6-questions` 真库 **901 B 是 AI 生成 markdown 长文本**（5 元素字符串数组，"
    "首元素是含 `###` 标题与列表的整段中文）⇒ 与 `structured_row_array` 是**两种 shape**，"
    "按行数组解析会失败。`J1-6-conclusion` 是自由文本标量。"
)

#: 🔴 真库载荷是「骨架已落库、业务未填」。
LIVE_PAYLOAD_FACTS_J106: Final[dict[str, object]] = {
    "bytes": 3473,
    "note": "全 J 最大载荷",
    "flag": "skeleton_persisted_no_business_values",
    "zero_fields": ["baseAmount", "rate", "estimated", "actual", "diff"],
    "empty_string_fields": ["baseName", "baseIndex", "diffReason", "conclusion"],
    "consequence": (
        "🔴 roundtrip **只能验结构** ⇒ 须另造带金额的合成载荷补第二轮，"
        "验 `G=ROUND(D*F,2)` 与 `I=G-H` 两个公式。"
    ),
}

#: 🔴 RD-5（本轮新登记）：impl 19 项 vs 模板 A17:A35 十处不等。
RD5_DIFF_FACTS_J106: Final[dict[str, object]] = {
    "impl_constant": "j1/inspection/J1TabAccrualCheck.vue#SHORT_TERM_DEFAULTS",
    "impl_count": 19,
    "source_ref": "计提情况检查表J1-6!A17:A35",
    "source_count": 19,
    "row_count_match": True,
    "content_mismatch_count": 10,
    "diff_classes": {
        "separator_fullwidth_vs_halfwidth": {
            "count": 9,
            "detail": "模板**全角 `．`**（U+FF0E）/ impl **半角 `.`**",
        },
        "indent_prefix": {
            "count": 9,
            "detail": (
                "模板带 **3 个全角空格 `\\u3000`**（如 `\\u3000\\u3000\\u30002．奖金`）/ "
                "impl 无前缀（靠 `indent: 1` 字段表达）"
            ),
        },
        "newline_in_cell": {
            "count": 1,
            "detail": (
                "🔴 模板 `八、辞退福利\\n（因解除劳动关系给予的补偿）` **含换行符** / "
                "impl 写成一行 `八、辞退福利（因解除劳动关系给予的补偿）`"
            ),
        },
    },
    "forbidden_shortcut": (
        "🔴 **禁标点归一化** —— `NFKC` 会同时洗掉 RD-2 的 5 处与本条的 9 处 ⇒ "
        "逐格**字节**比对。"
    ),
    "fix_blocked_by": "business_confirmation",
    "fix_blocked_note": (
        "改哪一侧是业务判断（模板是审计准则产物 / impl 是用户可见文案）⇒ 本轮只登记差异清单，"
        "**不**把错标签固化进契约 —— `header_text` 取**模板原字节**。"
    ),
}

TEMPLATE_CELL_LOCK_FACTS_J106: Final[dict[str, object]] = {
    "sheet_protection_enabled": False,
    "note": "ws.protection.sheet=False ⇒ locked 惰性；mode 按「该格逐行有没有真公式」判。",
}

#: 模板有列、store 侧是前端重算的派生值 ⇒ 只进 FORMULA_MASK。
TEMPLATE_ONLY_FORMULA_COLUMNS_J106: Final[tuple[tuple[str, str], ...]] = (
    ("G", "应提金额 = ROUND(D*F, 2)"),
    ("I", "差异 = G-H"),
)

# ═══════════════════════════════════════════════════════════════════════════
# 3. 字段声明（7 元组）
# ═══════════════════════════════════════════════════════════════════════════

#: 8 个受管字段（跳过 G/I 两个公式列）。`json_key` 逐字取 `J1TabAccrualCheck.AccrualRow`。
#: 🔴 `A` 列的 `header_text` 取 **R15 的 `项目`**（R16 的 A 是 None）。
FIELD_SPECS_J106: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("label", "A", "editable", "text", "label", "项目", ""),
    ("base_name", "C", "editable", "text", "baseName", "名称", "C15"),
    ("base_amount", "D", "editable", "amount", "baseAmount", "金额", "C15"),
    ("base_index", "E", "editable", "text", "baseIndex", "索引", "C15"),
    ("rate", "F", "editable", "amount", "rate", "计提比例", ""),
    ("actual", "H", "editable", "amount", "actual", "实际计提数", ""),
    ("diff_reason", "J", "editable", "text", "diffReason", "差异原因", ""),
    ("conclusion", "K", "editable", "text", "conclusion", "结论", ""),
)

#: 公式列 → 数据行公式模板。逐字实测自 R17/R18（全 19 行同形）。
FORMULA_TEMPLATES_J106: Final[dict[str, str]] = {
    "G": "=ROUND(D{r}*F{r},2)",
    "I": "=G{r}-H{r}",
}
FORMULA_COLUMNS_J106: Final[tuple[str, ...]] = ("G", "I")

# ═══════════════════════════════════════════════════════════════════════════
# 4. spec
# ═══════════════════════════════════════════════════════════════════════════

SPEC_J106: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_J106,
    sheet_key=SHEET_KEY_J106,
    table_key=ROWS_TABLE_KEY_J106,
    template_id=TEMPLATE_ID_J106,
    table_name=f"GT_{TEMPLATE_ID_J106}_ROWS",
    uuid_col=UUID_COL_J106,
    first_data_row=FIRST_DATA_ROW_J106,
    last_data_row=LAST_DATA_ROW_J106,
    footer_row=FOOTER_ROW_J106,
    header_group_row=HEADER_GROUP_ROW_J106,
    header_leaf_row=HEADER_LEAF_ROW_J106,
    store_item_id=STORE_ITEM_ID_J106,
    empty_payload=EMPTY_PAYLOAD_J106,
    row_identity_key=ROW_IDENTITY_STORE_KEY_J106,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_J106,
    formula_columns=FORMULA_COLUMNS_J106,
    formula_templates=FORMULA_TEMPLATES_J106,
    footer_marker=FOOTER_MARKER_J106,
    #: 🔴 本 sheet 无 footer 合计行 ⇒ 显式 False（同 D3-4 段② 的先例）
    footer_carries_total_formula=False,
    error_label="J1-6 计提情况检查表（短期薪酬区）",
)
