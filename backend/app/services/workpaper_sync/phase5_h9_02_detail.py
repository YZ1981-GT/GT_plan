# -*- coding: utf-8 -*-
"""H9-2「租赁负债明细表」—— sheet 层薄声明（H 循环首张接入 canary）。

spec: `h-cycle-sync-foundation-and-first-canary` · Task 20

═══ 为什么选 H9-2 作 canary ═══

它是全 H 循环「真库有非空主表载荷 + 几何最简 + 无专属阻塞」的唯一交集：

* 🔴 **真库唯一非空主表载荷**：现算 `checklist_responses` 的 `remark` 列，9 条 entry 的
  主表键只有 3 条命中 —— `H8-2-rows` = `[]`（2 B）· `H10-detail-rows` = `[]`（2 B）·
  **`H9-2-rows` = 819 B / 2 行真实数据**。其余 6 条无行。
  沿用 G2 的选型标准「真库有非空载荷」——否则 roundtrip 断言只能造数据，等于伪实证。
* **几何最简族**：两级表头 R7/R8 · 数据区 **R9-13（仅 5 行）** · footer R14 纯 SUM ·
  22 有效列 · 54 公式 · 裸 `IF(` **24 格（全 H 次少，仅多于 H6 的 12）**。
* **无专属阻塞**：`capability_target_blocked_by` 在 BP-1~BP-4 之外为空。

三条逆风（如实登记，不粉饰）：

1. 🔴 H9 **无 TB 发布门**（`publishToTb` 在 H9 全链路实测 **0 处**）⇒
   **canary 不覆盖发布链**，发布链首例归 `h2-h6-h10-pilot-cross-reference-lanes`。
2. 读路径是 HD-2 **第三族**（`GET /render-config?force_component_type=…` 再合并
   `sheets[].html_data.responses_snapshot`），不是最简的 checklist GET ⇒
   代价是 canary 复杂度上升，收益是**最复杂读路径先打通**。
3. 载荷含**跨 entry 派生标记** `terminatedFromH8` + **3 个中文枚举字段** ⇒
   契约必须先解决 HC-11 两类声明，绕不开。

═══ 几何（openpyxl 逐格实测，禁推演）═══

`max_row=26` / `max_column=22`（有效内容列同为 22 = A..V）/ **0 个 definedName** /
无 Excel Table / 册内有 `GT_Custom` hidden sheet（与 H10 两册独有）。

* **两级**表头 **R7 / R8**（`header_rows = 8 - 7 + 1 = 2`）
* 数据区 **R9-R13**（5 行）
* footer **R14**「合计」，`B14..R14` 与 `U14` 各为 `=SUM(x9:x13)`
* 公式列 **E / I / J / K / L / N**（逐行实测）：
  - `E{r} = B{r}-C{r}+D{r}`　未审期末（🔴 负债贷方：期初 − 偿还 + 利息）
  - `I{r} = B{r}+F{r}`　审定期初
  - `J{r} = C{r}+G{r}`　审定借方
  - `K{r} = D{r}+H{r}`　审定贷方
  - `L{r} = I{r}-J{r}+K{r}`　审定期末
  - `N{r} = L{r}-M{r}`　期末报表数
* UUID 列 **W** = 有效内容列（22）+ 1（HC-13）

🔴 **`locked` 标志在 H 循环是惰性的，不得用它推断 formula / editable**：
实测 9 张 H 主受管表的 **sheet 级保护全部未启用**（`ws.protection.sheet is False`、无密码、
workbook 未锁结构）⇒ 单元格的 `locked=True` 只是 Excel 未设样式时的**默认值**，不生效。

本表数据行 `locked=True` 的是 **E / I / J / K / L / M / N 七列**，其中 `M`（重分类）
**没有公式**且 HTML 侧是可编辑数值列（`useH9Detail.updateCell` 的 `case 'reclassification'`）。
这**不是模板缺陷**（保护没开，锁与不锁无差别），而是「`locked` 无判读价值」的实证。

⇒ 契约的 `mode` 一律由**「该格逐行有没有真公式」**决定，`merge._protection` 也只看契约
的 `mode` + `formula_mask`（不读模板 `locked`）。两边口径一致，无需覆盖层。
该事实登记在 `TEMPLATE_CELL_LOCK_FACTS_H902`，供后续排查时不再重复判读。

═══ 字段键逐字取自前端 `_persist()` 落盘列表 ═══

`useH9Detail.ts` 的 `_persist()` 明确列出 **22 个**落库字段。🔴 spec Requirement 5.3
写「23 字段」但其自身枚举也是 22 —— 真库 819 B 载荷逐字段现算亦为 **22**，按 22 为准。

**模板列 ↔ store 字段**（FC-5「以模板为权威」）：

| 列 | 模板叶子标题 | store 字段 | mode |
|---|---|---|---|
| A | 出租方名称 | `lessor` | editable |
| B | 期初余额 | `beginBalance` | editable |
| C | 借方发生（未审数） | `repayment` | editable |
| D | 贷方发生（未审数） | `interestAccrued` | editable |
| E | 期末余额（未审数） | `endBalance` | **formula** |
| F | 期初调整 | `beginAje` | editable |
| G | 借方发生（本期调整） | `repayAje` | editable |
| H | 贷方发生（本期调整） | `interestAje` | editable |
| I | 期初余额（审定数） | `auditedBegin` | **formula** |
| J | 借方发生（审定数） | `auditedRepay` | **formula** |
| K | 贷方发生（审定数） | `auditedInterest` | **formula** |
| L | 期末余额（审定数） | `auditedEnd` | **formula** |
| M | 重分类：减一年内到期的租赁负债 | `reclassification` | editable |
| N | 期末报表数 | `finalAudited` | **formula** |
| O~R | 1年以下 / 1～2年 / ２～3年 / 3年以上 | `dueWithin1Y` / `due1To2Y` / `due2To3Y` / `dueOver3Y` | editable |
| S | 是否关联方 | `isRelatedParty` | editable（🔴 中文枚举） |
| T | 发函或替代情况 | `isConfirmed` | editable（🔴 中文枚举） |

🔴 **两处口径差异必须登记，不得静默抹平**：

1. **模板有列、HTML 无字段**：`U 期后付款` / `V 备注` —— `_persist()` 里没有对应键。
   照 H1 pilot 对占位列 `X` 的处置（Requirement 6.1「禁止无来源自造字段」），
   这两列**不进 `field_specs`**，登记为 HTML-only。
2. **HTML 有字段、模板无列**：`contractNo` / `assetDesc` / `ibrRate` / `leaseTerm` /
   `isTerminated` / `terminationDate` / `terminatedFromH8` **7 个 store-only 字段**。
   它们不映射任何格；merge 只更新受管列，base 行的这些字段原样保留。

🔴 **6 个公式列的 json_key 不落库**：`_persist()` 不写 `endBalance` / `auditedBegin` /
`auditedRepay` / `auditedInterest` / `auditedEnd` / `finalAudited` —— 前端 `load()` 时
由 `_normalizeRow()` 按同一套公式重算。契约仍声明它们的 `json_pointer`（可追溯 + 将来落库即生效），
`formula_mask` 保证 OO 侧不被 HTML 的 `None` 覆盖。

🔴 **前端注释有一处与模板不符**（FC-5，登记不改）：`useH9Detail.ts` 顶部注释写
「O~R其他列(合同号/承租资产/利率IBR/租赁期)」，但模板 O~R 是**期末到期日分析**四档；
同文件接口内 `dueWithin1Y` 的注释「对齐 Excel O」才是对的。
以模板为权威 ⇒ O~R 映射到期日分析四字段。

═══ 行身份两形态，均属 HC-7 族 A（安全）═══

真库实证 `row-liab-H91-FILL-1784691549786`（H9-1 联动填充，带时间戳）与
`row-mrvjayxr-u0mc`（随机）；生成点 `useH9Detail._normalizeRow` 用
`` `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}` `` ⇒
**canary 不含身份改造**（族 B/C 的改造留给三份 lane spec）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_H902",
    "MANAGED_SHEET_H902",
    "STORE_ITEM_ID_H902",
    "FORMULA_TEMPLATES_H902",
    "CHINESE_ENUM_FIELDS_H902",
    "DERIVED_STORE_ONLY_FIELDS_H902",
    "STORE_ONLY_FIELDS_H902",
    "TEMPLATE_ONLY_COLUMNS_H902",
    "TEMPLATE_CELL_LOCK_FACTS_H902",
]

MANAGED_SHEET_H902: Final[str] = "租赁负债明细表H9-2"
TEMPLATE_ID_H902: Final[str] = "H92"
SHEET_KEY_H902: Final[str] = "h902-managed"
ROWS_TABLE_KEY_H902: Final[str] = "lease_liability_detail_rows"

#: 🔴 按值取自 `useH9Detail.ts` 的 `ROWS_KEY`，**不按 sheet 号推演**。
#: 该键被 `useH8CrossSheet.ts` / `useH8DisposalCheck.ts` 跨 entry 消费 ⇒ 改名会打断 H8。
STORE_ITEM_ID_H902: Final[str] = "H9-2-rows"
ROW_IDENTITY_STORE_KEY_H902: Final[str] = "rowId"

HEADER_GROUP_ROW_H902: Final[int] = 7
HEADER_LEAF_ROW_H902: Final[int] = 8
FIRST_DATA_ROW_H902: Final[int] = 9
LAST_DATA_ROW_H902: Final[int] = 13
FOOTER_ROW_H902: Final[int] = 14
FOOTER_MARKER_H902: Final[str] = "合计"
EFFECTIVE_COLUMNS_H902: Final[int] = 22
UUID_COL_H902: Final[str] = "W"

#: 🔴 模板有列但 HTML 侧无对应 store 字段 ⇒ 不进 `field_specs`（Requirement 6.1）。
TEMPLATE_ONLY_COLUMNS_H902: Final[tuple[tuple[str, str], ...]] = (
    ("U", "期后付款"),
    ("V", "备注"),
)

#: 🔴 HTML 侧有字段但模板无列 ⇒ store-only，不映射任何格。
STORE_ONLY_FIELDS_H902: Final[tuple[str, ...]] = (
    "contractNo",
    "assetDesc",
    "ibrRate",
    "leaseTerm",
    "isTerminated",
    "terminationDate",
    "terminatedFromH8",
)

#: 🔴 HC-11：中文枚举域字段（值域是中文字面量，**不得**声明为 boolean）。
#: 实测真库取值全为 `"否"`；`useH9Detail._normalizeRow` 的缺省值亦为 `'否'`，
#: 且 `isTerminated` 的归一化分支显式比较 `=== '是'` ⇒ 值域 `{"是","否"}`。
CHINESE_ENUM_FIELDS_H902: Final[dict[str, tuple[str, ...]]] = {
    "isRelatedParty": ("是", "否"),
    "isConfirmed": ("是", "否"),
    "isTerminated": ("是", "否"),
}

#: 🔴 HC-11：跨 entry 派生标记，OO 侧不可编辑 —— 由 H8 终止租赁流程回传
#: （`applyH8TerminationToH92Rows` / `markTerminatedFromH8`），OO 侧改了下次会被覆盖。
DERIVED_STORE_ONLY_FIELDS_H902: Final[tuple[str, ...]] = ("terminatedFromH8",)

#: 🔴 单元格锁标志的实测事实 —— **登记它是为了说明「不能拿它判读 mode」**。
#: sheet 级保护未启用 ⇒ `locked` 是 Excel 默认值，惰性；`locked_without_formula` 里的 `M`
#: 不是"模板少解锁"，而是这批标志整体无判读价值的实证。
TEMPLATE_CELL_LOCK_FACTS_H902: Final[dict[str, object]] = {
    "sheet_protection_enabled": False,
    "locked_columns": ("E", "I", "J", "K", "L", "M", "N"),
    "locked_without_formula": ("M",),
    "formula_without_locked": (),
    "note": (
        "sheet 级保护未启用（ws.protection.sheet=False / 无密码 / workbook 未锁结构）⇒ "
        "locked 标志惰性。契约 mode 一律按「该格逐行有没有真公式」判，"
        "merge._protection 也只看契约 mode + formula_mask，不读模板 locked。"
    ),
}


#: 20 个受管字段（7 元组，第 7 位 `group_header_cell`）。
#: 顺序即 Excel 列序 A→T；`header_text` 逐字取模板**叶子**格；
#: `group_header_cell` 只在真有横向分组时给（A/B/F/M/N/S/T 的 R7:R8 纵向合并 ⇒ 空）。
#: `json_key` 逐字取 `useH9Detail.H9DetailRow`。
FIELD_SPECS_H902: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("lessor", "A", "editable", "text", "lessor", "出租方名称", ""),
    ("begin_balance", "B", "editable", "amount", "beginBalance", "期初余额", ""),
    ("repayment", "C", "editable", "amount", "repayment", "借方发生", "C7"),
    ("interest_accrued", "D", "editable", "amount", "interestAccrued", "贷方发生", "C7"),
    ("end_balance", "E", "formula", "amount", "endBalance", "期末余额", "C7"),
    ("begin_aje", "F", "editable", "amount", "beginAje", "期初调整", ""),
    ("repay_aje", "G", "editable", "amount", "repayAje", "借方发生", "G7"),
    ("interest_aje", "H", "editable", "amount", "interestAje", "贷方发生", "G7"),
    ("audited_begin", "I", "formula", "amount", "auditedBegin", "期初余额", "I7"),
    ("audited_repay", "J", "formula", "amount", "auditedRepay", "借方发生", "I7"),
    ("audited_interest", "K", "formula", "amount", "auditedInterest", "贷方发生", "I7"),
    ("audited_end", "L", "formula", "amount", "auditedEnd", "期末余额", "I7"),
    (
        "reclassification",
        "M",
        "editable",
        "amount",
        "reclassification",
        "重分类：减一年内到期的租赁负债",
        "",
    ),
    ("final_audited", "N", "formula", "amount", "finalAudited", "期末报表数", ""),
    ("due_within_1y", "O", "editable", "amount", "dueWithin1Y", "1年以下", "O7"),
    ("due_1_to_2y", "P", "editable", "amount", "due1To2Y", "1～2年", "O7"),
    ("due_2_to_3y", "Q", "editable", "amount", "due2To3Y", "２～3年", "O7"),
    ("due_over_3y", "R", "editable", "amount", "dueOver3Y", "3年以上", "O7"),
    ("is_related_party", "S", "editable", "text", "isRelatedParty", "是否关联方", ""),
    ("is_confirmed", "T", "editable", "text", "isConfirmed", "发函或替代情况", ""),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R9-R13。
#: 🔴 `E` / `L` 是**负债贷方**口径（期初 − 借方 + 贷方），与资产类相反 —— 抄反会让审定期末反号。
FORMULA_TEMPLATES_H902: Final[dict[str, str]] = {
    "E": "=B{r}-C{r}+D{r}",
    "I": "=B{r}+F{r}",
    "J": "=C{r}+G{r}",
    "K": "=D{r}+H{r}",
    "L": "=I{r}-J{r}+K{r}",
    "N": "=L{r}-M{r}",
}

SPEC_H902: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_H902,
    sheet_key=SHEET_KEY_H902,
    table_key=ROWS_TABLE_KEY_H902,
    template_id=TEMPLATE_ID_H902,
    table_name=f"GT_{TEMPLATE_ID_H902}_ROWS",
    uuid_col=UUID_COL_H902,
    first_data_row=FIRST_DATA_ROW_H902,
    last_data_row=LAST_DATA_ROW_H902,
    footer_row=FOOTER_ROW_H902,
    header_group_row=HEADER_GROUP_ROW_H902,
    header_leaf_row=HEADER_LEAF_ROW_H902,
    store_item_id=STORE_ITEM_ID_H902,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_H902,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_H902,
    formula_columns=("E", "I", "J", "K", "L", "N"),
    formula_templates=FORMULA_TEMPLATES_H902,
    footer_marker=FOOTER_MARKER_H902,
    error_label="H9-2 租赁负债明细表",
)
