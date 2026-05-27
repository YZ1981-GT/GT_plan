# 附注公式 DSL — 完整语法参考

> **版本**：v1.0（Sprint 1.5 Task 1.5.1）
> **配套实现**：`backend/app/services/note_formula_generator.py`（入口 `generate_formulas_for_table` / `execute_note_formulas` / 单 token 解析 `_resolve_single_cross_ref`）
> **存储位置**：`DisclosureNote.table_data._formulas`（顶层 `dict[str, dict]`）
> **错误处理铁律**：缺数据返 `None`（章节标 `not_applicable`），**不抛错**

## 目录

1. [DSL 函数总览](#1-dsl-函数总览)
2. [函数详细说明](#2-函数详细说明)
   - [TB — 试算表取数](#21-tbaccount_codecolumn--试算表取数)
   - [WP — 底稿单元格取数](#22-wpwp_codesheetcell_ref--底稿单元格取数)
   - [REPORT — 财报取数](#23-reportrow_codeperiod--财报取数)
   - [NOTE — 当年其他附注合计](#24-notesectionperiod--当年其他附注合计)
   - [cell / SUM — 表内引用](#25-cellrow-col--sumstartend-col--表内引用)
   - [PRIOR — 上年附注取数](#26-prioraccount_nameperiod--上年附注取数)
   - [AGING — 账龄分桶](#27-agingaccount_namebucket--账龄分桶)
3. [加减组合表达式](#3-加减组合表达式)
4. [`_formulas` 单元格级公式存储 schema](#4-_formulas-单元格级公式存储-schema)
5. [错误处理铁律](#5-错误处理铁律)

---

## 1. DSL 函数总览

| 函数 | 作用 | 数据来源 | 引入 | 实现入口（行号示意） |
|------|------|---------|------|----------------------|
| `TB` | 试算表余额 | `cross_data["tb"]`（`TrialBalance`） | 已有 | `_resolve_single_cross_ref` 末尾 TB 分支 |
| `WP` | 底稿单元格 | `cross_data["wp"]`（`WorkingPaper.parsed_data.cells`） | 已有 | `_resolve_single_cross_ref` WP 分支 |
| `REPORT` | 财报项 | `cross_data["report"]`（`FinancialReport`） | 已有 | `_resolve_single_cross_ref` REPORT 分支 |
| `NOTE` | 当年其他附注合计 | `cross_data["notes"]`（同年 `DisclosureNote` 末尾合计行） | 已有 | `_resolve_single_cross_ref` NOTE 分支 |
| `cell` / `SUM` | 表内引用 | 当前 `note.table_data.rows[].values[]` | 已有 | `_exec_horizontal` / `_exec_vertical_sum` |
| `PRIOR` | 上年附注期末/期初 | `cross_data["prior"]`（`year-1` `DisclosureNote`） | 🆕 Sprint 1.5 | `_resolve_single_cross_ref` PRIOR 分支 |
| `AGING` | 账龄分桶（5 桶） | `cross_data["aging"]`（`TbAuxLedger` 反推） | 🆕 Sprint 1.5 | `_resolve_single_cross_ref` AGING 分支 |

数据预加载入口：`_load_cross_table_data(db, project_id, year)`（一次性批量查询 6 张表）。

---

## 2. 函数详细说明

### 2.1 `TB(account_code, column)` — 试算表取数

**语法**：`TB('1001','期末')`

**参数**：
- `account_code`：科目代码（与 `TrialBalance.standard_account_code` 对齐），如 `'1001'`、`'1122'`。
- `column`：列名，白名单：
  - `'期末'` / `'closing'` → `audited_amount`（期末余额 = 审定数）
  - `'期初'` / `'opening'` → `opening_balance`
  - `'审定数'` / `'audited'` → `audited_amount`
  - `'未审数'` / `'unadjusted'` → `unadjusted_amount`

**正常 case**：
```
TB('1001','期末')         # 库存现金期末审定数
TB('1122','审定数')       # 应收账款审定数
```

**缺数据 case**：
- `account_code` 不存在 → 返回 `0.0`（不是 `None`，与历史行为对齐：列名合法但科目缺失视为零余额）。
- `column` 不识别 → 返回 `None`。

**边界 case**：
- `cross_data["tb"]` 整体为空（试算表未导入）→ 单条 TB 返回 `0.0`（值为 `None` 的字段会兜底）。
- 多科目累加见 [§3 加减组合表达式](#3-加减组合表达式)。

**实现入口**：`note_formula_generator._resolve_single_cross_ref` 末尾 `TB('...','...')` 正则分支。

---

### 2.2 `WP(wp_code, sheet, cell_ref)` — 底稿单元格取数

**语法**：`WP('E1','审定表E1','B5')`

**参数**：
- `wp_code`：底稿编码（与 `WpIndex.wp_code` 对齐），如 `'E1'`、`'D-1'`。
- `sheet`：sheet 名（可空），如 `'审定表E1'`、`''`。
- `cell_ref`：单元格地址，如 `'B5'`。

**取数逻辑**：
1. 优先匹配复合 key `"sheet!cell_ref"`（如 `"审定表E1!B5"`）。
2. fallback 单 cell_ref（如 `"B5"`）。

**正常 case**：
```
WP('E1','审定表E1','B5')   # 命中 cells["审定表E1!B5"]
WP('E1','','B5')            # 命中 cells["B5"]
```

**缺数据 case**：
- `wp_code` 不存在 / `wp.parsed_data` 为 None / 单元格未填 → 返回 `None`。
- 单元格值非数值（字符串注释等）→ 在 `_load_cross_table_data` 阶段已被 `isinstance(v, (int, float))` 过滤，不会进入 `cross_data["wp"]`。

**边界 case**：
- `cell_ref` 大小写敏感（`B5` ≠ `b5`），上游 `excel_html_converter` 统一大写。

**实现入口**：`note_formula_generator._resolve_single_cross_ref` WP 正则分支。

---

### 2.3 `REPORT(row_code, period)` — 财报取数

**语法**：`REPORT('BS-002','期末')`

**参数**：
- `row_code`：报表行编码（与 `FinancialReport.row_code` 对齐），如 `'BS-002'`（资产负债表行 002）、`'IS-015'`。
- `period`：期间，白名单：
  - `'期末'` / `'current'` / `'本期'` → `current_period_amount`
  - `'期初'` / `'prior'` / `'上期'` → `prior_period_amount`

**正常 case**：
```
REPORT('BS-002','期末')   # 货币资金期末值
REPORT('IS-015','本期')   # 营业收入本期数
```

**缺数据 case**：
- `row_code` 不存在 → 返回 `None`。
- 字段值为 `NULL` → `_load_cross_table_data` 阶段 `float(current) if current else 0` 兜底 `0.0`。

**边界 case**：
- `period` 同时含「本期」和「期初」字符（不规范输入）→ 优先匹配「期末/current/本期」分支。

**实现入口**：`note_formula_generator._resolve_single_cross_ref` REPORT 正则分支。

---

### 2.4 `NOTE(section, '*', period)` — 当年其他附注合计

**语法**：`NOTE('五、3','合计','期末')`

**参数**：
- `section`：附注章节号（与 `DisclosureNote.note_section` 对齐），如 `'五、3'`、`'五、1'`。
- 第二参数：占位标识（实现侧不解析，传 `'合计'` 或 `'*'` 都可，仅校验三参数结构）。
- `period`：期间：
  - `'期末'` 含 → `total_closing`（取末尾合计行 values[0]）
  - `'期初'` 含 → `total_opening`（取末尾合计行 values[1]）

**正常 case**：
```
NOTE('五、3','合计','期末')   # 五、3 末尾合计行第 1 列
NOTE('五、3','*','期初')       # 五、3 末尾合计行第 2 列
```

**缺数据 case**：
- `section` 不存在 / 该章节无 `is_total` 行 → 返回 `None`。
- `period` 既非「期末」也非「期初」→ 返回 `None`。

**边界 case**：
- 章节有多个合计行（如分组合计）→ 取**最后一个**（`total_rows[-1]`），与历史行为一致。

**实现入口**：`note_formula_generator._resolve_single_cross_ref` NOTE 正则分支 + `_load_cross_table_data` notes 加载。

---

### 2.5 `cell(row, col)` / `SUM(start:end, col)` — 表内引用

**语法**：
- `cell(3, 2)` — 引用当前表第 3 行第 2 列（0-based）的 `values[col]`。
- `SUM(0:3, 1)` — 求和当前表第 0-3 行第 1 列。

**取数逻辑**：从 `note.table_data.rows[row].values[col]` 直接读取；`None` 跳过累加。

**正常 case**：
```
cell(3, 0) + cell(3, 1) - cell(3, 2)    # 横向公式
SUM(0:5, 1)                              # 第 0-5 行第 1 列纵向求和
```

**缺数据 case**：
- `row` 越界 → 跳过该项（不累加，不抛错）。
- `values[col]` 为 `None` → 跳过该项。

**边界 case**：
- `cell(row, col)` 内部带空格（`cell( 3 , 2 )`）会失配 — 当前正则 `cell\((\d+),(\d+)\)` 严格要求无空格。
- `SUM(start:end, col)` end 含义为 **闭区间**（与 `_topological_sort_formulas` 一致）。

**实现入口**：
- `cell(...)` → `note_formula_generator._exec_horizontal`
- `SUM(...)` → `note_formula_generator._exec_vertical_sum`

---

### 2.6 `PRIOR(account_name, period)` — 上年附注取数

> 🆕 Sprint 1.5 Task 1.5.2 新建。

**语法**：`PRIOR('货币资金','期末')`

**参数**：
- `account_name`：上年附注的科目名（`section_title`）或章节号（`note_section`）。两种 key 都被索引到同一 entry。
- `period`：
  - 含「期末」或 `'closing'` → 上年 `total_closing`
  - 含「期初」或 `'opening'` → 上年 `total_opening`

**正常 case**：
```
PRIOR('货币资金','期末')      # 上年货币资金附注期末合计
PRIOR('五、1','期末')          # 同上，按章节号索引
PRIOR('应收账款','期初')      # 上年应收账款附注期初合计
```

**缺数据 case**：
- `account_name` 不在上年任何附注中 → 返回 `None`（章节会被标 `not_applicable`）。
- 上年附注 `is_total` 行不存在 → `_load_cross_table_data` 阶段不会把该 entry 写入 `cross_data["prior"]`，结果同上 → `None`。
- 上年 `DisclosureNote` 整张表不存在（首年项目）→ `cross_data["prior"]` 为空 dict → `None`。

**边界 case**：
- 同一上年 entry 被两种 key（`section_title` + `section_number`）双索引，确保模板写 `PRIOR('货币资金',...)` 或 `PRIOR('五、1',...)` 都能命中。
- `period` 既非「期末」也非「期初」→ 返回 `None`。

**实现入口**：
- 数据预加载：`note_formula_generator._load_cross_table_data` 中 `Sprint 1.5 Task 1.5.2: 加载上年（year-1）附注` 段落。
- 解析：`note_formula_generator._resolve_single_cross_ref` 中 PRIOR 正则分支（位于函数顶部，优先匹配避免被 TB 等覆盖）。

---

### 2.7 `AGING(account_name, bucket)` — 账龄分桶

> 🆕 Sprint 1.5 Task 1.5.2 新建。从 `TbAuxLedger` 反推 5 桶。

**语法**：`AGING('应收账款','1年以内')`

**参数**：
- `account_name`：科目名（与 `wp_account_mapping.json` 中 `account_name` 字段对齐）。
- `bucket`：5 桶白名单（与 `note_source_resolvers._AGING_BUCKETS` 对齐）：
  - `'1年以内'`：账龄 [0, 366) 天
  - `'1-2年'`：[366, 731) 天
  - `'2-3年'`：[731, 1096) 天
  - `'3-5年'`：[1096, 1826) 天
  - `'5年以上'`：[1826, ∞) 天

**取数逻辑**：
1. 基准日 = `YYYY-12-31`（年末）。
2. 单笔账龄 = `base_date - voucher_date`（天数）。
3. 桶内累加 `(debit_amount - credit_amount)`（净额）。
4. 上下闭开区间：`low ≤ days < high`。

**正常 case**：
```
AGING('应收账款','1年以内')   # 应收账款 1 年以内挂账净额
AGING('其他应收款','3-5年')   # 其他应收款 3-5 年挂账净额
```

**缺数据 case**（铁律：缺数据 → `None`，不抛错）：
- 客户未提供辅助序时账（`cross_data["aging"]` 为空 dict）→ 返回 `None`，章节标 `not_applicable`。
- 科目完全不在 aging 中（任何桶都没数据）→ 返回 `None`。
- 科目存在但请求的桶下无数据（其他应收款无 `5年以上` 桶）→ 返回 `0.0`（行为对齐 TB：科目存在但桶为零）。

**边界 case**：
- `bucket` 不在白名单（如 `'超长龄'`）→ 返回 `None`。
- `voucher_date` 早于年末未来年份（`days < 0`）→ 跳过该笔（不累加）。
- 同一科目代码映射到多个 `account_name` 时，按 `wp_account_mapping.json` 文件读取顺序首次写入（`if code and code not in account_to_name`）。

**实现入口**：
- 桶定义：`backend/app/services/note_source_resolvers.py::_AGING_BUCKETS`
- 数据预加载：`note_formula_generator._load_cross_table_data` 中 `Sprint 1.5 Task 1.5.2: 加载账龄分桶` 段落（含 wp_account_mapping 加载、`account_code → account_name` 反查、按 `voucher_date` 分桶累加）。
- 解析：`note_formula_generator._resolve_single_cross_ref` 中 AGING 正则分支。

---

## 3. 加减组合表达式

DSL 支持任意函数 token 用 `+` / `-` 组合：

```
TB('1001','期末') + TB('1002','期末')
TB('1001','期末') - WP('E1','审定表E1','C5')
PRIOR('货币资金','期末') - PRIOR('货币资金','期初')   # 同比变化
AGING('应收账款','1年以内') + AGING('应收账款','1-2年')  # 2 年内合计
REPORT('BS-002','期末') + NOTE('五、3','合计','期末')
```

**解析流程**（`_exec_cross_table`）：
1. 用正则 `([+-]?)\s*((?:TB|REPORT|WP|NOTE|PRIOR|AGING)\([^)]*\))` 拆解为 `[(sign, token), ...]`。
2. 重组无空格表达式与原表达式比对，**不允许混入** `*` `/` 或函数列表外的 token（防 SQL 注入式攻击）。
3. 任一 token 解析失败（`_resolve_single_cross_ref` 返回 `None`）→ 整个表达式返回 `None`，章节标 `not_applicable`。
4. 否则按符号累加 / 减。

**注意**：
- 横向公式（`cell(row,col)` 加减）走单独通道 `_exec_horizontal`，不能与跨表 token 混用。
- 通用兜底 `_exec_generic` 会先试 `_exec_cross_table`，再试 `_exec_horizontal`，两者都失败则返回 `None`。

---

## 4. `_formulas` 单元格级公式存储 schema

### Schema 形态澄清

`note.table_data._formulas` **是 `dict[str, dict]`，不是 list**（spec design D4 描述「数组」与代码事实有差异，本节为唯一权威说明）。

- key 格式：`"row_idx:col_idx"`（0-based，标签列已扣除，`row_idx` 指 `rows` 数组下标）。
- 顶层 dict 已经事实满足「不污染 row 结构，独立顶层数组」的设计意图（位于 `table_data` 顶层，与 `rows` / `headers` 平级）。
- `row` / `col` 字段从 key 解出（`key.split(":")`），**无需冗余存储** 在 value 中。

### Value 字段表

| 字段 | 类型 | 含义 | 引入 |
|------|------|------|------|
| `type` | str | 公式类型：`vertical_sum` / `horizontal_balance` / `book_value` / `cross_table` | 已有 |
| `expression` | str | DSL 表达式原文，如 `"TB('1001','期末')"` | 已有 |
| `description` | str | 人类可读说明，如 `"合计 = 子项之和"` | 已有 |
| `category` | str | 分类标签：`"auto_calc"` / 自定义 | 已有 |
| `source` | str \| None | 公式来源：`"wp_mapping"` / `"account_codes"` / `"report_row_code"` / `"check_presets.sub_item"` 等 | 已有 |
| `binding_id` | str \| None | 关联 1.3 输出的 `_cell_meta.binding_id`；`generate_formulas_for_table` 自动生成时占位 `None`，由 `_build_with_binding` 阶段写入 | 🆕 Sprint 1.5 Task 1.5.4 |
| `evaluated_at` | str (ISO 8601) | 公式最近一次执行成功的 UTC 时间戳；仅在 `execute_note_formulas` 公式实际成功执行时更新 | 🆕 Sprint 1.5 Task 1.5.4 |

### 字段写入路径

| 字段 | 写入入口 | 时机 |
|------|---------|------|
| `type / expression / description / category / source` | `generate_formulas_for_table` | 模板阶段（基于 check_presets / wp_mapping / account_codes / report_row_code） |
| `binding_id` | `generate_formulas_for_table`（占位 `None`）→ `_build_with_binding`（实写） | 模板阶段 + 引擎重生成阶段 |
| `evaluated_at` | `execute_note_formulas` | 公式实际执行成功（`calc_value is not None` 且写回 `values[col]`）时 |

### 示例

```jsonc
{
  "table_data": {
    "headers": ["项目", "期末余额", "期初余额"],
    "rows": [
      {"label": "库存现金", "values": [50.0, 40.0]},
      {"label": "银行存款", "values": [1184.56, 1060.0]},
      {"label": "合计", "values": [1234.56, 1100.0], "is_total": true}
    ],
    "_formulas": {
      "0:0": {
        "type": "cross_table",
        "expression": "TB('1001','期末')",
        "description": "库存现金 期末",
        "category": "auto_calc",
        "source": "account_codes",
        "binding_id": "binding_huobi_1001_closing",
        "evaluated_at": "2026-05-27T10:23:45.123456+00:00"
      },
      "2:0": {
        "type": "vertical_sum",
        "expression": "SUM(0:1, 0)",
        "description": "合计 = 第1~2行之和",
        "category": "auto_calc",
        "source": "check_presets.sub_item",
        "binding_id": null,
        "evaluated_at": "2026-05-27T10:23:45.456789+00:00"
      }
    }
  }
}
```

---

## 5. 错误处理铁律

> **缺数据返 `None`，不抛错。**

所有 DSL 函数在以下场景必须返回 `None`，由调用方（`execute_note_formulas` / `disclosure_engine._build_with_binding`）决定章节是否标 `not_applicable`：

| 场景 | 返回 | 备注 |
|------|------|------|
| `account_code` / `row_code` / `wp_code` / `section` 整体不存在 | `None` | 上游数据未导入 |
| `column` / `period` / `bucket` 白名单未命中 | `None` | 模板写错或语义不识别 |
| 上年附注不存在（首年项目） | `None`（PRIOR） | `cross_data["prior"]` 为空 dict |
| 客户未提供辅助序时账 | `None`（AGING） | `cross_data["aging"]` 为空 dict |
| 加减组合中任一 token 解析失败 | `None` | 整个表达式作废 |
| `_load_cross_table_data` DB 异常 | 各子键空 dict | `try/except pass` 静默兜底，不阻塞其他章节 |

**禁止**：
- 任何 DSL 函数抛 `KeyError` / `ValueError` / `TypeError`，必须在内部捕获并返回 `None`。
- 凭空生成 `0.0` 替代缺数据（除非显式约定，如 `TB` 列名合法但 account 不存在 → `0.0`，与历史行为对齐）。
- 在公式执行后修改非 `auto` 模式的单元格（`_cell_modes[col] != "auto"` 的格子必须跳过）。

---

## 附录：相关文档

- ADR-007（本 spec 配套）：`docs/adr/ADR-007-note-triple-format-source-of-truth.md` — `DisclosureNote.table_data` 唯一真源。
- ADR-008（待落地）：Note cell mode persistence (auto/manual/locked)。
- Spec：`.kiro/specs/disclosure-note-full-revamp/`（D1 sidecar / D4 公式 DSL / R1.2 七种 source）。
- 测试：`backend/tests/services/test_note_formula_dsl.py`（PRIOR / AGING + 5 已有函数回归 ≥ 25 用例）。
