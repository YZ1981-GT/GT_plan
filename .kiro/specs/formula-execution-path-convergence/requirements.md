# 需求：公式执行路径收敛（Formula Execution Path Convergence）

> 本 spec 对应评估报告的 **Step 2**：将三套独立执行器收敛为 L2 预载 → L1 内核的统一模式。

## 背景

Step 1 统一了函数注册表（`_REGISTRY` 20 函数）和语法定义（`FORMULA_ARITY` 单一真源），但**执行路径仍然碎片化**：

| 路径 | 消费者 | 执行模式 | 与 L1 内核的关系 |
|------|--------|---------|----------------|
| `report_engine.evaluate_formula_result` | 报表生成、表间审核 | L2 预载（regex 替换 TB/SUM_TB→数值）→ L1 `execute()` | ✓ 经 L1 |
| `prefill_engine.resolve_extended_formula` | 底稿预填充 | 逐格调独立 resolver → 各自查 DB | ✗ 完全绕过 L1 |
| `FormulaEngine.execute` | 公式管理页 API | 构建 `tb_map` → `FormulaContext.from_simple_map` → L1 | ✓ 经 L1 |

**核心问题**：
1. `prefill_engine` 的 8 个 resolver 各自查 DB，无法受益于 L1 内核的安全校验（blocked 检测、列名白名单、trace 审计）
2. 同一个 `ADJ()` 函数在两条路径下口径刻意不同（底稿不排 origin，报表排 workpaper），但这个差异藏在两份独立代码里
3. `LEDGER` / `LEDGER_DETAIL` / `TB_AUX` / `COUNT_LEDGER` 在 L1 内核里只有占位 handler（返回 0），底稿预填充是唯一真实执行路径
4. `PREV()` 在 prefill 里恒返 None（fail-closed），在 report 里替换为 0 — 不同的「不支持」表达

## R1 统一预载层（Unified Preloader）

- R1.1 新建 `backend/app/services/formula_preloader.py`，提供 `async def preload(db, project_id, year, formulas: list[str]) -> FormulaContext`：批量扫描公式文本中引用的全部数据源（TB/SUM_TB/ADJ/AUX/WP/NOTE/LEDGER 等），一次性查 DB 构建 `FormulaContext`。
- R1.2 `FormulaContext` 扩展两个新字段：`ledger_data: dict[str, dict[str, Decimal]]`（序时账发生额）和 `ledger_detail_data: dict[str, list[dict]]`（序时账明细行）。
- R1.3 预载层的 TB 取数走 `TrialBalanceResolver`（前缀聚合口径，与报表一致）；ADJ 取数参数化（`exclude_origins` 由调用方传入，底稿传空集、报表传 `{"workpaper"}`）。
- R1.4 **NOTE 取数对齐披露表变更**：`_load_note` 改为从 `disclosure_notes.table_data.sub_table_data` 读取（与 `note-data-from-disclosure-table` spec 的 `DisclosureSourceBinding` 同源），不再直接查 `table_data.rows`。动态行由 `sub_table_data` 的实际行决定。
- R1.5 `preload` 返回的 `FormulaContext` 可直接喂给 `formula_engine.execute()`。

## R2 L1 handler 实装（从占位到真实）

- R2.1 `_handle_ledger`：从 `ctx.ledger_data[account_code][direction_period]` 取值（不再返回 0）。
- R2.2 `_handle_ledger_detail`：从 `ctx.ledger_detail_data` 取值，返回行数（Decimal）。
- R2.3 `_handle_tb_aux`：从 `ctx.aux_data` 取值（key = `{account}:{aux_type}:{aux_code}`）。
- R2.4 `_handle_count_ledger`：从 `ctx.ledger_data` 取笔数。
- R2.5 各 handler 保持纯同步函数（从 ctx dict 取值），不查 DB。

## R3 prefill_engine 改走 L1

- R3.1 `prefill_workpaper_real` 的执行循环改为：先调 `preload()` 构建 `FormulaContext`，再逐格调 `formula_engine.execute(formula_text, ctx)`。
- R3.2 `resolve_extended_formula` 保留为兼容入口，内部改为 `preload([formula]) → execute`。
- R3.3 删除 `_FORMULA_RESOLVERS` dict 及 8 个独立 resolver 函数（`_resolve_*`）。保留 `_parse_args`（被其他模块引用）和 `_parse_period_range`（移入 preloader 或 utils）。
- R3.4 ADJ 口径差异显式化：`preload` 接收 `adj_exclude_origins` 参数，底稿路径传 `frozenset()`，报表路径传 `frozenset({"workpaper"})`。
- R3.5 `PREV()` 统一为 `preload` 取上年 trial_balance 数据并填入 `ctx.prior_tb_data`（底稿路径同样取上年 TB，不再恒 None；但跨年度底稿取数仍无解——数据模型缺 year 列）。

## R4 与 note-data-from-disclosure-table 对齐

- R4.1 `formula_preloader._load_note` 复用 `disclosure_source.load_disclosure_sub_table_data` 和 `note_rows_from_disclosure` 从披露表取数（不再查 `disclosure_notes.table_data.rows`）。
- R4.2 NOTE() 在 L1 内核的 handler（`_handle_note`）从 `ctx.note_data` 取值时，key 格式须与披露表行的动态 key 对齐（`{section}:{row_label}:{column}` 而非静态 `{section}:{field}`）。
- R4.3 公式管理面板的 NOTE() 依赖查询也需对齐——依赖的 addr_id 是章节级（`note:{section}`），不因动态行而改变。

## R4 report_engine 改走统一预载

- R4.1 `evaluate_formula_result` 的 regex 预替换改为调 `preload()`（消灭第二份 TB/SUM_TB regex 替换逻辑）。
- R4.2 `ReportFormulaParser` 的 `_resolve_tb` / `_resolve_sum_tb` 保留为 `AmountResolver` 协议实现（合并路径的 `ConsolTrialResolver` 注入不变），但单体路径改为从 `FormulaContext.tb_data` 读取。
- R4.3 **渐进式**：Phase 1 先统一 prefill，Phase 2 再改 report_engine（改动面最大，单独 Phase）。

## R5 验收

- R5.1 `test_formula_preloader.py`：preload 批量查一次 DB → ctx 含全部数据源 → execute 结果与旧 resolver 逐格一致
- R5.2 `test_prefill_convergence.py`：底稿预填充走 L1 后，与旧路径结果逐格对比（合成底稿 + 真实 PG 数据）
- R5.3 ADJ 口径守卫：断言底稿路径 `exclude_origins=frozenset()` 而报表路径 `exclude_origins=frozenset({"workpaper"})`
- R5.4 回归：formula_settings 236+ passed、全域 961+ passed、前端全绿
