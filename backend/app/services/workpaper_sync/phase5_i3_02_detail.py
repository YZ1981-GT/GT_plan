# -*- coding: utf-8 -*-
"""I3-2「商誉明细表」—— sheet 层薄声明（四级表头 + 两处模板真实缺陷）。

spec: `i1-i3-disclosure-positional-identity-and-classification-source` · Task 13 / 15

═══ 🔴 两处模板真实缺陷（两种不同处置）═══

**缺陷①（IC-14 / ID-3）：`AA23:AD23` 四格引错区间 —— 走覆盖层修**

```
实际  AA23 = =SUM(AA27:AA30)    AB23/AC23/AD23 同型（各自列）
应为  AA23 = =SUM(AA14:AA22)    （数据区是 R14-22）
根因  R27-29 是**编制说明文本行**（B27='编制说明：' / B28 / B29 是说明文字）
      R30 **超出 max_row(29)**  ⇒ 引用区间完全落在数据区之外
后果  🔴 **减值准备区审定数四列（期初数/本期增加/本期减少/期末数）合计恒 0**
对照  同行左侧 S23..Z23 **全部正确** `=SUM(x14:x22)` ⇒ 四格错法一致 = **复制粘贴错误**
```

🔴 处置 = **模板覆盖层**（FC-5 的**第 5 个**例外；前四个是 `F2-26!J9` / `F5-7!G31` /
`G5-2` 45 格 / `G5-1!B35`）。`backend/wp_templates/` 字节**不动** ——
模板是审计准则产物，改字节会破坏与纸质底稿的对应关系，且 sha256 变了会让 6 条 I entry
的 `source_ref` 全部失效。覆盖层**只替换这 4 格**，R23 其余列一个都不碰。

🔴 **判据载荷必须是「只有减值准备区（R14:R22 的 AA:AD）有数、其他区为 0」** ——
用「全区都有数」的载荷时修复前后合计都非 0（因 R27:R30 可能被别的公式带出值）⇒ 判据**假绿**；
用「全区都是 0」则恒真。同时须断言 R23 的**非 AA:AD 列**在覆盖层前后取值**不变**（不误伤）。

**缺陷②（本轮新发现）：`I14` 缺公式 —— 登记不修**

`I15`..`I18` 逐行都是 `=SUM(Dx:Ex)-Gx`，但 **`I14`（数据区首行）是 `None`**
⇒ 🔴 首行的「商誉原值未审期末」不会自动计算。

处置 = **登记不修**（与缺陷① 的 `overlay_fixed` 是**两种处置**，不得混写）。理由：
它不是金额算错而是**首行漏公式**，前端 `useI3Detail` 的 `costEnding` 本就按同一套公式重算并落库
⇒ merge 时该格由 `formula_columns` 的模板重新写入，**实际不影响回写正确性**。
但仍须登记 —— 否则后来者会以为「I 列公式逐行齐全」。

═══ 几何（openpyxl 逐格实测）═══

`max_row=29` / `max_column=30` / **有效内容列 30（A..AD，两者相等）** / definedName **0** /
merged **47** / 无 Excel Table / `ws.protection.sheet=False` / 133 公式。

* 🔴 **四级表头 R10 / R11 / R12 / R13**（`header_group_row=10` + `header_leaf_row=13`
  ⇒ `header_rows = 13 - 10 + 1 = 4`）。平台的 `header_rows` 上界在 H9 那轮从 3 扩到 **4**，
  本表正好用到上界。
* 数据区 **R14-R22**（9 行）
* footer **R23**：🔴 **三种形态混在同一行**
  - 纯 SUM 14 格：E/G/J/K/L/R/S/T/U/V/W/X/Y/Z
  - **套用行公式 5 格**：`I23=SUM(D23:E23)-G23` · `M23=D23+J23` · `N23=E23+K23` ·
    `O23=G23+L23` · `P23=M23+N23-O23`
  - 🔴 **引错区间 4 格**：AA23/AB23/AC23/AD23（缺陷①）
  ⇒ `footer_kind = row_formula_applied` + `footer_convention_split`。
  🔴 照 I1/I2 的 `pure_sum` 口径去验本表 R23 会因「不是 SUM 开头」而**假红**。
* 🔴 **B 列与 C 列在数据区全空**：`C11='发生日期'` 只是表头、数据区 `C14..C22` 全 None；
  `B` 列**从表头到数据区全空**（间隔列）⇒ 两列都**不进 field_specs**。
* 公式列（逐行实测 R15 为准，🔴 R14 的 `I` 例外缺失见缺陷②）：
  **I / M / N / O / P / Q / W / AA / AB / AC / AD** 共 11 列
* `Q` 是**镜像列** `=A{r}`（右表的被投资单位名称镜像左表）⇒ 进 `formula_columns`
  且**不映射 store 字段**（同 I5 区②的 A 列口径）
* UUID 列 **AE**（= 有效内容列 30 + 1）。`max_column` 也是 30 ⇒ 两者相等，无空列间隙。

🔴 **`locked` 同样惰性**（`ws.protection.sheet=False`）⇒ mode 按「该格逐行有没有真公式」判。

═══ CD-7：分类 clean（源自身派生自明细）═══

I3 **无 impl 分类常量** ⇒ verdict `SOURCE_ITSELF_DERIVES_FROM_DETAIL` / status `clean`。

═══ 🔴 BP-6：位置化行身份 7 处全在 I3（但都在披露层不在本 sheet）═══

全 I 循环 8 处位置化 site 里 **I3 占 7 处**，全在 `useI3Disclosure.ts` 与
`i3/impairment/I3TabRecoverableTest.vue`（**披露层 / 减值测试层**）——
本 sheet（`明细表I3-2`）的行身份是 `useI3Detail.ts` 的 `rowId`（族 A 安全生成）⇒
本 sheet 契约 `positional_identity_sites` 为空，但**不得**据此推断「I3 无位置化问题」。
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

MANAGED_SHEET_I302: Final[str] = "明细表I3-2"
SHEET_KEY_I302: Final[str] = "i32-managed"
ROWS_TABLE_KEY_I302: Final[str] = "goodwill_detail_rows"
TEMPLATE_ID_I302: Final[str] = "I32"
UUID_COL_I302: Final[str] = "AE"
#: 🔴 四级表头：group=R10 / leaf=R13 ⇒ header_rows=4（平台上界，H9 那轮从 3 扩来）
HEADER_GROUP_ROW_I302: Final[int] = 10
HEADER_LEAF_ROW_I302: Final[int] = 13
FIRST_DATA_ROW_I302: Final[int] = 14
LAST_DATA_ROW_I302: Final[int] = 22
FOOTER_ROW_I302: Final[int] = 23
FOOTER_MARKER_I302: Final[str] = "合计"
EFFECTIVE_COLUMNS_I302: Final[int] = 30
MAX_COLUMN_I302: Final[int] = 30

# ═══════════════════════════════════════════════════════════════════════════
# 2. store 形态
# ═══════════════════════════════════════════════════════════════════════════

STORE_ITEM_ID_I302: Final[str] = "I3-2-rows"
ROW_IDENTITY_STORE_KEY_I302: Final[str] = "rowId"
EMPTY_PAYLOAD_I302: Final[str] = "[]"

# ═══════════════════════════════════════════════════════════════════════════
# 3. 🔴 两处模板真实缺陷（两种处置，不得混写）
# ═══════════════════════════════════════════════════════════════════════════

#: 缺陷①：AA23:AD23 四格引错区间 ⇒ **覆盖层修**（FC-5 第 5 个例外）
TEMPLATE_DEFECT_AA23_I302: Final[dict[str, object]] = {
    "cells": ["明细表I3-2!AA23", "明细表I3-2!AB23", "明细表I3-2!AC23", "明细表I3-2!AD23"],
    "actual": "=SUM(<列>27:<列>30)",
    "expected": "=SUM(<列>14:<列>22)",
    "root_cause": (
        "R27-29 是**编制说明文本行**（B27='编制说明：' / B28 / B29 是说明文字）；"
        "R30 **超出 max_row(29)** ⇒ 引用区间完全落在数据区（R14-22）之外。"
    ),
    "effect": "🔴 减值准备区审定数四列（期初数/本期增加/本期减少/期末数）合计恒 0",
    "evidence_of_copy_paste": "同行左侧 S23..Z23 全部正确 =SUM(x14:x22) ⇒ 四格错法一致",
    "handling": "overlay_fixed",
    "handling_note": (
        "🔴 走**模板覆盖层**（FC-5 的**第 5 个**例外；前四个 F2-26!J9 / F5-7!G31 / "
        "G5-2 45 格 / G5-1!B35）。`backend/wp_templates/` 字节**不动** —— 模板是审计准则产物，"
        "改字节会破坏与纸质底稿的对应关系，且 sha256 变了会让 6 条 I entry 的 source_ref 全失效。"
        "覆盖层**只替换这 4 格**，R23 其余列一个都不碰。"
    ),
    "assertion_payload_requirement": (
        "🔴 判据载荷必须是「**只有减值准备区（R14:R22 的 AA:AD）有数、其他区为 0**」—— "
        "用「全区都有数」时修复前后合计都非 0（R27:R30 可能被别的公式带出值）⇒ 判据**假绿**；"
        "用「全区都是 0」则恒真。同时断言 R23 的**非 AA:AD 列**在覆盖层前后取值**不变**（不误伤）。"
    ),
    "overlay_formulas": {
        "AA23": "=SUM(AA14:AA22)",
        "AB23": "=SUM(AB14:AB22)",
        "AC23": "=SUM(AC14:AC22)",
        "AD23": "=SUM(AD14:AD22)",
    },
}

#: 缺陷②（本轮新发现）：I14 缺公式 ⇒ **登记不修**
TEMPLATE_DEFECT_I14_I302: Final[dict[str, object]] = {
    "cells": ["明细表I3-2!I14"],
    "actual": None,
    "expected": "=SUM(D14:E14)-G14",
    "root_cause": "I15..I18 逐行都有该公式，唯**数据区首行 I14 是 None** ⇒ 首行漏公式",
    "effect": "首行的「商誉原值未审期末」不会自动计算",
    "handling": "registered_not_fixed",
    "handling_note": (
        "🔴 与缺陷① 的 `overlay_fixed` 是**两种处置，不得混写**。理由：它不是金额算错而是"
        "**首行漏公式**，前端 `useI3Detail` 的 `costEnding` 本就按同一套公式重算并落库 ⇒ "
        "merge 时该格由 `formula_columns` 的模板重新写入，**实际不影响回写正确性**。"
        "但仍须登记 —— 否则后来者会以为「I 列公式逐行齐全」。"
    ),
}

#: 🔴 footer R23 三种形态混在同一行（照 pure_sum 口径验会假红）
FOOTER_SHAPE_FACTS_I302: Final[dict[str, object]] = {
    "kind": "row_formula_applied",
    "convention_split": True,
    "pure_sum_columns": ["E", "G", "J", "K", "L", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"],
    "row_formula_applied_columns": ["I", "M", "N", "O", "P"],
    "row_formula_applied_detail": {
        "I23": "=SUM(D23:E23)-G23",
        "M23": "=D23+J23",
        "N23": "=E23+K23",
        "O23": "=G23+L23",
        "P23": "=M23+N23-O23",
    },
    "defect_columns": ["AA", "AB", "AC", "AD"],
    "note": (
        "🔴 **三种形态混在同一 footer 行**：14 格纯 SUM + 5 格套用行公式 + 4 格引错区间（缺陷①）。"
        "照 I1/I2 的 `pure_sum` 口径去验本表 R23 会因「不是 SUM 开头」而**假红**。"
    ),
}

TEMPLATE_CELL_LOCK_FACTS_I302: Final[dict[str, object]] = {
    "sheet_protection_enabled": False,
    "note": "ws.protection.sheet=False ⇒ locked 惰性；mode 按「该格逐行有没有真公式」判。",
}

#: CD-7：I3 无 impl 分类常量（源自身派生自明细）
CLASSIFICATION_FACTS_I302: Final[dict[str, object]] = {
    "impl_constant": None,
    "source_ref": None,
    "verdict": "SOURCE_ITSELF_DERIVES_FROM_DETAIL",
    "status": "clean",
}

#: 模板有列、store 侧是前端重算的派生值或镜像 ⇒ 只进 FORMULA_MASK。
TEMPLATE_ONLY_FORMULA_COLUMNS_I302: Final[tuple[tuple[str, str], ...]] = (
    ("I", "期末数（原值未审）= SUM(D:E)-G　🔴 R14 缺失见缺陷②"),
    ("M", "期初数（原值审定）= D+J"),
    ("N", "本期增加（原值审定）= E+K"),
    ("O", "本期减少（原值审定）= G+L"),
    ("P", "期末数（原值审定）= M+N-O"),
    ("Q", "被投资单位名称（🔴 **镜像列** =A{r}，不映射 store 字段）"),
    ("W", "期末数（减值未审）= R+S+T-U-V"),
    ("AA", "期初数（减值审定）= R+X"),
    ("AB", "本期增加（减值审定）= S+Y+T"),
    ("AC", "本期减少（减值审定）= U+Z+V"),
    ("AD", "期末数（减值审定）= AA+AB-AC"),
)

#: 🔴 数据区全空的两列（不进 field_specs）
EMPTY_DATA_COLUMNS_I302: Final[tuple[tuple[str, str], ...]] = (
    ("B", "从表头到数据区全空（间隔列）"),
    ("C", "C11='发生日期' 只是表头，数据区 C14..C22 全 None"),
)

# ═══════════════════════════════════════════════════════════════════════════
# 4. 字段声明（7 元组，顺序即 Excel 列序；跳过 11 个公式列 + 2 个空列）
# ═══════════════════════════════════════════════════════════════════════════

#: 12 个受管字段。`header_text` 取**该列最深的非空标题**
#: （A 在 R10 · D/J/K/L/R/X/Y/Z 在 R12 · E/F/G/H/S/T/U/V 在 R13）；
#: `group_header_cell` 给上一层组标题格坐标；`json_key` 逐字取 `useI3Detail.I3DetailRow`。
FIELD_SPECS_I302: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("investee", "A", "editable", "text", "investee", "被投资单位名称或形成商誉的事项", ""),
    # ── 左表：商誉原值（C10 组标题）──
    ("cost_opening", "D", "editable", "amount", "costOpening", "期初数", "D11"),
    ("cost_increase", "E", "editable", "amount", "costIncrease", "金额", "E12"),
    (
        "cost_increase_method",
        "F",
        "editable",
        "text",
        "costIncreaseMethod",
        "增加方式",
        "E12",
    ),
    ("cost_decrease", "G", "editable", "amount", "costDecrease", "金额", "G12"),
    (
        "cost_decrease_reason",
        "H",
        "editable",
        "text",
        "costDecreaseReason",
        "减少方式",
        "G12",
    ),
    ("cost_aje", "J", "editable", "amount", "costAje", "账项调整", "J11"),
    # ── 右表：减值准备（R10 组标题）──
    ("imp_opening", "R", "editable", "amount", "impOpening", "期初数", "R11"),
    ("imp_increase", "S", "editable", "amount", "impIncrease", "本期计提", "S12"),
    ("imp_decrease", "U", "editable", "amount", "impDecrease", "处置", "U12"),
    (
        "imp_increase_method",
        "T",
        "editable",
        "text",
        "impIncreaseMethod",
        "其他增加",
        "S12",
    ),
    (
        "imp_decrease_reason",
        "V",
        "editable",
        "text",
        "impDecreaseReason",
        "其他减少",
        "U12",
    ),
    ("imp_aje", "X", "editable", "amount", "impAje", "账项调整", "X11"),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R15（🔴 R14 的 I 列缺失见缺陷②）。
#: 🔴 `Q` 是**镜像列** `=A{r}` —— 进 formula_columns 保证 merge 不拿 HTML 的 None 覆盖它。
#: 🔴 `AB`/`AC` 的口径是**三项相加**（本期增加 = S+Y+T / 本期减少 = U+Z+V），
#: 抄成两项（S+Y / U+Z）会漏掉「其他增加 T」与「其他减少 V」。
FORMULA_TEMPLATES_I302: Final[dict[str, str]] = {
    "I": "=SUM(D{r}:E{r})-G{r}",
    "M": "=D{r}+J{r}",
    "N": "=E{r}+K{r}",
    "O": "=G{r}+L{r}",
    "P": "=M{r}+N{r}-O{r}",
    "Q": "=A{r}",
    "W": "=R{r}+S{r}+T{r}-U{r}-V{r}",
    "AA": "=R{r}+X{r}",
    "AB": "=S{r}+Y{r}+T{r}",
    "AC": "=U{r}+Z{r}+V{r}",
    "AD": "=AA{r}+AB{r}-AC{r}",
}
FORMULA_COLUMNS_I302: Final[tuple[str, ...]] = (
    "I",
    "M",
    "N",
    "O",
    "P",
    "Q",
    "W",
    "AA",
    "AB",
    "AC",
    "AD",
)

# ═══════════════════════════════════════════════════════════════════════════
# 5. spec
# ═══════════════════════════════════════════════════════════════════════════

SPEC_I302: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_I302,
    sheet_key=SHEET_KEY_I302,
    table_key=ROWS_TABLE_KEY_I302,
    template_id=TEMPLATE_ID_I302,
    table_name=f"GT_{TEMPLATE_ID_I302}_ROWS",
    uuid_col=UUID_COL_I302,
    first_data_row=FIRST_DATA_ROW_I302,
    last_data_row=LAST_DATA_ROW_I302,
    footer_row=FOOTER_ROW_I302,
    header_group_row=HEADER_GROUP_ROW_I302,
    header_leaf_row=HEADER_LEAF_ROW_I302,
    store_item_id=STORE_ITEM_ID_I302,
    empty_payload=EMPTY_PAYLOAD_I302,
    row_identity_key=ROW_IDENTITY_STORE_KEY_I302,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_I302,
    formula_columns=FORMULA_COLUMNS_I302,
    formula_templates=FORMULA_TEMPLATES_I302,
    footer_marker=FOOTER_MARKER_I302,
    error_label="I3-2 商誉明细表",
)
