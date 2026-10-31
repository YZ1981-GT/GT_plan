# 设计文档：公式中枢正确性与安全闭环（formula-hub-integrity-closure）

## 0. 概览

本设计只回答「怎么做」；需求、现状事实与默认决策见 requirements（需求 X.Y / F 编号 / D、X 编号，不复述）。主线是把「错误冒充 0 / 成功 / 最新 / 通过」的根因各收口到**一个**所有者：①取值失败语义 → L1 `FormulaResult`（ADR-01/02）；②TB 取数口径与告警 → 叶子纯函数 + 告警收集器（ADR-03）；③报表逐行计算与新鲜度 → 伴生函数 + 计算版本 + 定义写入出口同事务标过期（ADR-04/05）；④WP 单元格读取 → 与 ACNR spec 共用的一个读取函数（ADR-06、§8.2）；⑤写入前校验 → 「域 → 校验器」表（ADR-09）；⑥「刷新/回滚/删除是否真的生效」→ 服务端真实计数、原子修订号与 CAS（ADR-07/08/10/11）；⑦一致性门禁 → 五态 + 一个判定函数 + 默认只提示（ADR-14）。Runtime 先冻结，修好后同批解冻。审计哈希链加固不在本 spec（ADR-12、§8.1 S10）。

**技术栈（锁定）**：后端 Python 3.12 + FastAPI + SQLAlchemy 2 async（asyncpg）+ PostgreSQL 16（运行时迁移 `backend/migrations/V*.sql` + `R*.sql`，MigrationRunner）；前端 Vue 3 + TypeScript + Element Plus + vitest；测试 pytest（`-p no:playwright`，`pg_only` 标记真 PG，hypothesis `max_examples=5`）。不引入新依赖。新增后端模块均放 `backend/app/services/` 下所述路径，每个 ≤300 行。

## 1. 现状确认的新发现（N 编号，F 表不重抄）

| N | 发现 | 对设计的影响 |
|---|---|---|
| N1 | 跨合计行 `SUM_ROW` 的候选写入方：`report_formula_service._generate_sum_formula`（按同级收集子行生成区间）、`_convert_formula`（`ROW(X:Y)→SUM_ROW`）、`_build_cas_name_formulas`（按行名套 CAS 公式） | 任务 18 先逐一判定再修，结论写入任务说明 |
| N2 | 前端无 `/api/formula/execute`、`/batch-execute` 生产调用 | 失败时 `value=null` 不破坏前端 |
| N3 | `routers/draft_refresh.py` 显式 `no_effect→success` | ADR-08 删除 |
| N4 | `consistency_gate` 两份 `CheckItem` / `ConsistencyResult`（F52） | 删 `_impl.py` 副本，统一 `_models` |
| N5 | `formula_settings/audit.py::change_entry` 只存显示字符串 | ADR-10 增完整定义 |
| N6 | `report_config.py` 两个执行端点 `body.get("year", 2024)` | 搬迁时改为 year 必填（422），并下调年度棘轮该文件条目（F60） |
| N7 | `formula_preloader._load_tb` 前缀聚合，中央 execute 改用 preload 会把双计带进中央 API | 任务 9 先于任务 12 |
| N8 | 真库 `ROW`/`SUM_ROW` 前向、跨表、悬空为 0（F37） | ADR-01 的「ROW 缺行 = 错误」不会让现存定义变失败 |
| N9 | 利润表净利润以下行无公式（F34） | 新 IS-074 等在活项目值为 0，由需求 6.4 warning 暴露 |
| N12 | 稳定键推导、`normalize_sheet_key` 已是单一来源（F39） | ADR-06 复用，不另写 sheet 归一 |

N10、N11（审计链分叉与 v1 时间串）随审计哈希链一并移交 S10，见 §8.1。

## 2. 架构裁定

**ADR-FHIC-01 失败语义所有者 = L1 `FormulaResult`。** L1 对除零、`ROW` 缺行（`row_cache` 无键）、未注册函数、参数个数不足、AST 超预算（节点 > 2000 或深度 > 50）抛新异常 `FormulaEvalError`，与 `FormulaColumnError` 同处捕获（在兜底 `except Exception` 之前）记入 `errors`；`value` 仍为 `Decimal('0')` 兼容只读调用方，**写入方一律判 `ok`**（Runtime 计划、报表逐行计算、中央 execute）。报表路径求值前把本准则全部「无公式行」以 `_generate_report` 对无公式行写入的同一值（实施时现读，现为 0）预置进 `row_cache`，故只有「行不存在 / 前向引用 / 引用行未就绪（ADR-05）」才报错（前向引用由需求 6.3 守卫冻结为 0）。否决「失败时 value=None」：约 20 个 `Decimal` 运算调用方会崩，归后续 S1。

**ADR-FHIC-02 参数个数表只管内置函数。** 新模块 `services/formula_arity.py`：`BUILTIN_FUNCTION_NAMES: frozenset[str]`（实施时等于 HEAD `_REGISTRY` 的全部内置键，字面量写死）与手工 `ARITY: dict[str, tuple[int, int | None]]`（`IF` (3,3)、`MAX`/`MIN` (2,None)、`ROUND` (1,2)、`AUX` (2,4)、`PREV` (2,3)、`PLACEHOLDER` (0,1)、`TB`/`SUM_TB` (1,2)、`ROW` (1,1)、`SUM_ROW` (2,2)、`REPORT` (1,2)、`NOTE` (2,3)、`WP` (2,3)、`ADJ` (1,2)、`ABS` (1,1) 等）。守卫：`set(ARITY) == BUILTIN_FUNCTION_NAMES`、`BUILTIN_FUNCTION_NAMES ⊆ set(_REGISTRY)`、`set(_REGISTRY) − BUILTIN_FUNCTION_NAMES == 已注册自定义函数名集合`（注册一个自定义函数后再断言）。自定义函数个数 = `len(param_names)`（精确），由 ADR-17 的注册元数据给出。求值期只强制下限与 `IF` 上限；写入期 validator 强制上下限。

**ADR-FHIC-03 TB 叶子口径 + 告警收集。** 新模块 `services/tb_leaf_codes.py`：`select_leaves(rows, code_of, amount_of) -> LeafSelection(rows, warnings)`，保留「集合内不存在以本码为前缀且更长的其他码」的行；父行金额与其叶子合计差 > 0.005 时生成 `{"code", "parent", "leaf_sum", "diff", "message"}` 告警。新模块 `services/formula_warnings.py`：`ContextVar` 告警收集器 —— `collect() -> 上下文管理器（产出 list）`、`emit(w)`（无收集器时只 `logger.info`）。F8 的全部取数点先按前缀/区间取宽集合，再调 `select_leaves` 求和并 `emit(selection.warnings)`；严格轨精确码 `limit(1)` 改为同一宽集合 + 叶子。结果合并点：`report_engine.evaluate_formula_result` 外包 `collect()` 写入 `FormulaResult.warnings`；中央 execute / debug 响应 `warnings`；`report_row_compute.RowOutcome.warnings`；推送 `formula_push.engine.run` 的运行结果（返回 dict 增 `warnings`，持久化字段实施时现读，有 summary JSON 则并入）。推送不变式只比 `load_tb_audited` 与测试内叶子和（需求 4.4），不比前缀和。否决复用 `four_table/leaf_aggregation.select_leaves`：它按 `code + '.'` 判子级，是 `tb_balance` 口径。

**ADR-FHIC-04 报表新鲜度 = 计算版本 + 定义写入出口同事务标过期（含依赖闭包）。** `financial_report` 加 `calc_version int`、`calc_error varchar(500)`（V{n+2}，可空）。`calc_error` = 计算失败原因（保留旧值时写）；既有 `blank_reason`（V173）= 口径性留空原因；二者不同时写，读者两者都展示。`services/report_freshness.py`：`CALC_VERSION = 2`；`stale_clause()` = `is_stale OR calc_version IS DISTINCT FROM :v`（汇总类读者）；`is_effectively_stale(row, effective_formula)` = 上述判据 OR 规范化公式文本不同（逐行读者，生效公式取 `effective_report.load_effective_report_configs`）；`async mark_changed(db, changes: dict[UUID, set[str]])`（项目 → 变化的 row_code）：每个项目按 `ReportConfigService.resolve_applicable_standard` + `load_effective_report_configs` 取有效定义，经 `propagation.report_closure` 扩成闭包，执行 `UPDATE financial_report SET is_stale = true WHERE project_id = :p AND row_code = ANY(:closure) AND is_deleted = false`（全部年度，与 `propagate_report` 同口径），只 flush。挂点是三个出口（F49）：`publish.publish_global`（取 `changed_slots(items, outcomes)`，slot `{report_type}:{row_code}` 取 row_code）、`project_ops.save_overrides`、`project_ops.restore_global`（取本次写入且有效定义变化的 slot），domain 为 report 时在各自事务内调用；`report_config` 写端点与 `fill_all_formulas` 已经经这些出口，不新增 publish source。`propagation.propagate_report` 的提交后重算与事件保持不变。SQL 迁移路径由静态守卫 `test_report_config_sql_migration_marks_stale.py` 管：版本号 > 205 的 `backend/migrations/V*.sql` 中凡 `UPDATE report_config … formula` 或 `INSERT INTO report_config`，同文件须含 `UPDATE financial_report SET is_stale = true`（大小写与空白归一后匹配），守卫自带一条违规样本自检。读者接入 F38 + 报表视图 / 导出 + 高级查询报表源（若已入库，§8.3），`test_report_freshness_readers.py` 冻结读者清单。存量 `calc_version IS NULL` 判过期（D13-A）。

**ADR-FHIC-05 报表三路 = 一个逐行计算 + 一条依赖缓存规则。** 新模块 `services/report_row_compute.py`：`compute_row(parser, config, row_cache, *, mode, formula_less_codes) -> RowOutcome{value, state, errors, warnings}`（外包 `formula_warnings.collect()` 调 `parser.execute_with_status`；失败 ⇒ `state != ok`；值为 0 且 TB 兜底有余额 ⇒ 只追加 warning、不替换值；引用行属 `formula_less_codes` ⇒ warning「组成行 … 未定义公式」）；`build_row_cache(rows, *, current_version) -> dict[str, Decimal]`：库中行只有 `is_stale = false AND calc_version = current_version` 才入缓存，本轮成功的行随算随入，本轮失败的行从缓存删除；`ROW` / `SUM_ROW` 引用缓存中没有的非「无公式行」⇒ `FormulaEvalError`「引用行未就绪：{code}（过期或计算失败）」。`_generate_report`、`regenerate_affected`、`recalculate_stale_rows` 三路改调二者并统一写库：成功 ⇒ 值、`calc_version`、`calc_error=NULL`、`is_stale=false`、`formula_used`；失败 ⇒ 既有行保留旧值、新行 `current_period_amount=NULL`、均 `is_stale=true`、`calc_error=首条错误[:500]`。stale 重算仍只选 `is_stale = true` 的行（不因 D13-A 自动重算存量行，X3）；D13-A 下存量行版本为空 ⇒ stale / affected 重算中引用它们的行以「引用行未就绪」失败，直到该项目全量重新生成（X3）——这是 false-fresh = 0 的代价，写进报表页提示。`_is_affected` 改为「变更码是公式引用码本身或其后代」；准则缺省取 `resolve_applicable_standard`。`generate_all_reports(..., skip_recalc: bool = False, publish_events: bool = True, summary_out: GenerateSummary | None = None)`：返回值 dict 不变；调用方传入 `summary_out` 时函数把 `changed_rows / recomputed_rows / failed_rows`（before≠after / 成功未变 / 失败；规范化到分后比较）填进去。不把摘要放进返回 dict：`routers/reports.py` 对返回 dict 的每个值取 `len` 并把全部键当报表类型返回给前端、写进 `REPORTS_UPDATED` 的 `report_types`，多一个键就改了接口。`publish_events=False` 时不发 `REPORT_ROW_CHANGED`，`True` 时沿用 HEAD 的收集规则。`chain_orchestrator` 与 `routers/reports.py` 不改调用，各加一条回归用例断言返回结构与事件不变。

**ADR-FHIC-06 Runtime 修复 = 稳定身份 + 共享读取（契约 §8.2）+ 严格外部取值 + 目标校验。**
1. **读取函数**：`services/wp_cell_reader.py::resolve_wp_cell` 按 §8.2 契约实现（年度闸门 `_year_gate`、目录可接受键 `_catalog_sheet_keys` 为模块内函数）。`formula_wp_semantics.py`：新增 `WP_IMPLS` 条目 `app/services/wp_cell_reader.py::resolve_wp_cell`；`EXECUTOR_WP_IMPL.data_source` 改写为「两参单元格经读取函数」；新增差异维度 `typed_eval_strictness`（typed_eval 与严格轨缺数 blocked，`WPExecutor` 两参与默认调用缺数 0；归属 S1），守卫的精确相等断言同步改。
2. **`WPExecutor.execute(db, project_id, wp_code, column="审定数", field=None, *, year=None)`**：单元格分支在既有 ACNR 重定位之后改调 `resolve_wp_cell(db, project_id, year, wp_code, None, cell)`，`state != ok` 返回 `D("0")`、ok 返回其值（两参行为不变；`matches > 1` 仍取第一个，登记差异）；列名与 D2-3 分支不改；列名映射提为模块常量 `WP_COLUMN_KEYS`（同一字典、值不变）供严格读取复用。三参 A1 分支归 ACNR。
3. **严格外部取值** `services/wp_ref_strict.py::read_wp_ref_strict(db, project_id, year, wp_code, second, third) -> WpCellRead`（先过 `_year_gate`；数据库异常上抛）：第三参为 A1，或无第三参且第二参为 A1 ⇒ `resolve_wp_cell`；列名两参 ⇒ 按读取函数同一规则绑定底稿，键取 `WP_COLUMN_KEYS.get(second, second)`，键缺失或值为 None / 空串 ⇒ missing「底稿 X 无字段「…」的值」，非数值 ⇒ blocked；坏账明细三参（第二参含 `_D23_SHEET_MARKER`）⇒ 只认同 wp_code 的 `bad_debt_detail_rows`（没有 ⇒ missing，不像 `_resolve_d23` 那样退到任一底稿），字段名（含「父行.字段」写法）不在 `_D23_FIELD_TO_COLUMN` ⇒ blocked「坏账明细字段无法识别」，父行找不到或金额为 None ⇒ missing；其余写法 ⇒ blocked「引用写法无法识别」。
4. **节点身份** = `(wp_code.upper(), stable_sheet_key, field_key + row_key)`：取 `WpFormula` 已存三元组，为空才 `stable_key.derive_stable_key(sheet_name, target_cell)`；`stable_key_needs_review` ⇒ blocked「公式位置待复核」。引用由 `dependencies.upstream_refs`（需求 14.3 后）解析 `WP()` 实参并按写法分类：单元格三参（sheet 经 `normalize_sheet_key`）与单元格两参（sheet = None）参与依赖图；列名两参与坏账明细三参是外部取值，不建依赖边。
5. **匹配与环**：单元格三参精确匹配批内目标；单元格两参命中「同 wp_code、同 cell」的批内目标 —— 唯一 ⇒ 依赖边，多个 ⇒ blocked「引用有歧义」，零个 ⇒ 读存值（`resolve_wp_cell`，`matches > 1` ⇒ blocked）。Tarjan 强连通分量，环上（含自环）全部 blocked「循环引用」。
6. **目标校验**（需求 1.8）：新函数 `wp_parsed_data_service.resolve_target_sheet(parsed_data, stable_sheet_key) -> TargetSheet(state, sheet_name, candidates)`（与写入函数同模块，typed_eval 不直接访问 `html_data`）在 `html_data` 中找 `normalize_sheet_key(key) == stable_sheet_key` 的真实表名，0 个 ⇒ blocked「目标工作表不存在」、多个 ⇒ blocked「目标工作表名有歧义」；单元格只校验 A1 写法。`max_row/max_col` 是数据范围（F57，`write_cell_to_parsed_data` 写入时单调扩展、供前端 `hasData`），不作越界边界。mutation 的 locator 写真实表名。`write_cell_to_parsed_data` 增 `require_existing_sheet: bool = False`，Runtime workpaper adapter 传 True（缺表抛 `ValueError`，双重防线），其他调用方不变。
7. **求值**：计划开始时做一次年度闸门（与读取函数共用 `_year_gate`，比较请求年度与项目年度）：项目年度为空 ⇒ 全部 WP 引用 blocked「项目未设置审计年度」，不符 ⇒ 全部 WP 引用 missing「底稿年度与项目年度不符」；通过后逐引用调用读取函数时传 `year=None`（避免逐引用重复查询）。图构造与求值写成纯函数 `plan_batch(definitions, *, year_verdict, read_ref)`，年度结论与读取函数由调用方注入（`_year_gate` 的 SQL 只能在 PG 上执行，SQLite 单测直接注入）。拓扑序；每条公式先为全部 WP 引用备好 `wp_values: dict[(wp_code, sheet | None, ref), Decimal]`（批内取上游已算值，批外经 `resolve_wp_cell` / `read_wp_ref_strict`，非 ok ⇒ 本条 blocked 并带原因），再调 `evaluate_wp_formula_expression(..., wp_values=wp_values, strict_wp=True)`（两个新关键字参数，默认 None/False 零回归）。该函数两个 WP 代入循环（F58）：先查 `wp_values`；查不到且 `strict_wp` ⇒ 记错误、不调 `WPExecutor`；`WPExecutor` 返回 None（ACNR 三参取不到、或传了不符的 year）⇒ 记中文错误、不代入、该式无值，不论 `strict_wp`（即 ACNR 设计复核 F7 要求的处理，只在本函数实现一次）。errors 非空 ⇒ blocked、不产 mutation。`typed_eval.evaluate_single(db, formula)` 供预览端点 `GET /api/workpapers/{wp_id}/formulas` 使用（批大小为 1；请求年度 = 项目年度，只做「未设置」判定），四方一致由构造保证、测试验证。
8. **adapter 真形状**：`adapters/report.py` 的 `VALID_REPORT_TYPES` 改为 F41 六个 PG 枚举值（短码一律拒绝）；`adapters/note.py` 的读写函数增 `rows[].values` 分支（locator `row` 为行序号或首格文本、`column` 为列序号，字段名按真库样本现读后写死并配样本测试）。coordinator 目前不为 report/note 构造目标，adapter 修复保证任何后续调用方不拒读。
9. coordinator：`_build_batch_definitions` 改产出 typed_eval 计划；`engine.execute_batch` 不再被 coordinator 调用（其他调用方不改）。ACNR `full_resolve` 不参与身份判定。

**ADR-FHIC-07 冻结 = 计划阶段闸门，先于锁。** `DraftRefreshOrchestrator.generate` 拆为三段：①**计划**（只读、无锁）——校验 scopes、对每个 scope 产 `ScopePlan{scope, kind ∈ runtime|report|marker, mutations, units, page_keys}`（runtime 范围调 coordinator 只读产计划；report 范围只登记，不写）；②**冻结判定** `formula_runtime/freeze.py::check_runtime_frozen(plans)`：任一 runtime 范围的计划含 mutation ⇒ 抛 `RuntimeFrozen`（409），不看 `source_formula_id` 能否解析（Runtime 只产出 wp_formula 来源的 mutation）；③**执行**——`await self._acquire_project_lock(project_id)`（从 generate 顶部移出的原锁逻辑，单独方法供测试 spy）→ 幂等判定（ADR-08）→ 依次执行各范围。计划在锁外产出，并发写由 mutation 自带 `expected_version` CAS 兜住（既有机制）。`routers/draft_refresh.py` 在通用 `except Exception` 之前捕获 `RuntimeFrozen` → 409、不 commit。解冻批删除 `freeze.py` 与调用点。否决 feature flag（D8）。单个提交流程下冻结只存在于 WIP 提交之间；若实施中途停止而需要合入部分成果，合入内容必须含任务 2 的冻结（Runtime 未修好前不得以可写状态上线）。

**ADR-FHIC-08 Draft Refresh 结果聚合合同。** 新模块 `formula_management/refresh_outcome.py`：`ScopeOutcome{scope, value_changes, recomputed, draft_marked, failures: list[dict], post_commit_events: list[EventPayload]}` 与 `derive_outcome(outcomes, transaction_mode) -> (outcome, status)`（需求 3.2 的表，表驱动实现）。执行段：
- **幂等**：取锁后算计划指纹 `plan_fp` = sha256(规范 JSON：排序后的 scopes、四表快照指纹（`refresh()` 写 `tb_snapshot_hash` 的既有算法）、runtime 的 `formula_revision` 与 `preset_revision`；勾选 report 时再加本项目年度 `trial_balance` 未删行（科目码, 审定, 未审, 期初）排序后的哈希、有效报表定义（类型, 行次, 规范化公式）排序后的哈希、`CALC_VERSION`、`stale_clause()` 行数)；请求未带 `idempotency_key` 时以 `plan_fp` 为键。按 `draft_refresh_audit(project_id, year, idempotency_key)` 取最近一条：`result_status = executing` ⇒ 409（既有语义）；`detail.outcome ∈ {applied, recomputed, draft_marked, no_effect}` ⇒ 命中，返回 `idempotent_hit` 与该记录的 outcome 及四个计数，不执行任何范围；partial / failed / 无记录 ⇒ 执行。每次执行恰写一条审计（有 runtime mutation 时由 `execute_refresh` 写，否则由 `refresh()` 写；仅报表范围时以零单元调用，实施时现读确认零单元也写审计，否则由编排器直接写），`idempotency_key = plan_fp`；编排器调用二者时传新参数 `idempotency_checked=True`，二者跳过各自的幂等短路（其他调用方默认 False，行为不变）。指纹含报表输入与过期行数 ⇒ 输入变化后的首个请求必然执行，输入未变时至多多执行一次（结果为 recomputed）。
- **runtime 范围**：before 与 after 规范化（Decimal 量化到 0.01，文本去首尾空白）后相等的 mutation 移出写入集合、计入 `recomputed`；其余一次 `execute_refresh`，`value_changes = applied_count`。
- **report 范围**：`async with db.begin_nested(): await TrialBalanceService(db).full_recalc(pid, year)`（失败 ⇒ 本范围 failures、保存点回滚、不生成报表）→ `ReportEngine.generate_all_reports(pid, year, applicable_standard=<项目真实准则>, skip_recalc=True, publish_events=False)`（审定模式按该函数现有参数传入）→ 由传入的 `summary_out` 得 `value_changes`、`recomputed`，失败行进 failures；`value_changes > 0` 时 `post_commit_events` 追加 `REPORT_ROW_CHANGED(row_codes=changed_rows 的行次)` 与 `REPORTS_UPDATED`。
- **marker 路径** ⇒ `draft_marked`。

`generate` 汇总后写回结果对象：`RefreshResult` 与 `ExecutionResult` 各增 `outcome / recomputed_count / draft_marked_count / post_commit_events`（后者不序列化），`affected_count = applied_count + recomputed_count`；`draft_refresh_audit.result_status` 写法不变，`detail` 记 outcome 与四个计数（供幂等重放）。`refresh()` 与 `execute_refresh` 仅在 `value_changes > 0` 时 `trigger_recalc` / `mark_stale`。路由：`outcome == failed` ⇒ `await db.rollback()`，返回 200 `status=failed` + failures，不发事件；否则 commit 后逐个 `event_bus.publish_immediate(ev)`（与 `routers/reports.py` 同法）；删除 `no_effect→success` 映射。`DraftRefreshResponse.status` 的 Literal 扩为 7 值（`success / recomputed / draft_marked / no_effect / partial_success / failed / idempotent_hit`），增 `recomputed_count / draft_marked_count / outcome`；前端 `components/formula/formulaRuntimeContract.ts` 的 `VALID_STATUSES`、类型与 `isPartialSuccess` 同步，`GtRefreshScopeDialog` 按 status 显示文案。report 范围 `rollback_available=false`（中文说明「报表可重新生成，不支持一键回滚」）。

**ADR-FHIC-09 统一 validator = 域 → 校验器表 + 静态错误检查。** 新模块 `services/formula_settings/validator.py::validate_formula_definition(domain, definition, *, label, slot_key)`，全部先查长度 ≤4000、括号嵌套 ≤50：

| 域 | 校验器 |
|---|---|
| report / tb_detail / cross_check | L1 解析 + 函数名 ⊆ `_REGISTRY` + `ARITY` 上下限 + TB/SUM_TB 列名 ∈ `COLUMN_ALIASES` + 常量零除数检查 |
| wp | 现有 `checked_wp_definition`（含 `unsupported_formula_function_issues`，允许 `Sheet!Cell`） |
| note | 现有 `check_note_definition` |
| consol_note | 现有 `validate_note_formula` |
| push | 现有 `validate_push_definition` |

常量零除数检查：遍历 L1 AST，对每个除法 / 取模节点的右操作数做常量折叠（只折叠数字字面量与 `+ - * /` 一元二元运算，遇函数调用、行引用即视为非常量）；折叠结果为 0 ⇒ 问题「除数恒为 0」。不在空上下文执行整式（否则误拒 TB/ROW）。调用点：`SettingStore.write_global/write_project` 基类、`ReportStore` 等自定义 store 写方法、`report_config` 直写逻辑；`domain_stores.validate_definition` 改薄转发。错误统一 `FormulaSettingError(422, code=FORMULA_DEFINITION_INVALID, detail={problems:[{slot_key, message}]})`；`disabled=true` 只校验结构。

**ADR-FHIC-10 历史回滚 = 服务端快照 + CAS。** `rollback_from_log(db, project_id, source_log_id, expected_version, user_id)`：删 `target_formula`；目标定义取条目 `changes[].old_definition`（需求 13.2 新写入），旧条目仅报表域取 `{formula: old_formula}`；`RollbackRequest.expected_version: int | None = Field(None, ge=0)`，缺失由服务层抛 `VersionRequired`（428），不靠 pydantic 必填（否则是 422）。历史 GET 为每条计算 `rollbackable`（复用 `_locate` + 目标定义可得）与 `rollback_blocked_reason`。权限不改（F48 外层角色 + 项目 review）；前端 `specAReady` 删除，按钮只看 `rollbackable` 与既有角色门控（`formulaHistoryRollbackGate.spec.ts` 继续守）。

**ADR-FHIC-11 待确认修订号原子递增 + 三段决策键。** `formula_sync_item.revision int not null default 1`（V{n+1}）。`upsert_pending` 改为单条原子语句：按方言取 `sqlalchemy.dialects.postgresql.insert` 或 `sqlalchemy.dialects.sqlite.insert`，`.on_conflict_do_update(index_elements=["project_id","domain","slot_key"], index_where=text("status = 'pending'"), set_={…覆盖字段, "revision": FormulaSyncItem.revision + 1, "updated_at": now}).returning(FormulaSyncItem)`（冲突目标与 F43 部分唯一索引一致）；新建行 `revision=1`。`resolve_items` 以 `revision` 为唯一 CAS 依据。版本类入参一律「模型可空、服务层判缺」：`ResolveBody.resolutions[].revision: int | None = Field(None, ge=1)`、三个删除端点的 `expected_version: int | None`，缺失抛 `VersionRequired`（428），不等抛 409；overrides DELETE 用重复 Query 参数 `expected_version`，与 `slot_key` 按出现顺序配对，个数不等 ⇒ 422。`project_ops.restore_global(..., expected_versions: list[int] | None = None)`：None 只供已在同一事务内做过 CAS 的内部调用方（`setting_sets.replace_set`、`legacy_report`，实施时 grep 补全并在调用点注释），端点层一律传入。决策键 = `f"{domain}|{project.id}|{slot_key}"`，解析 `key.split("|", 2)`；旧两段键 = 首段不在 `KNOWN_DOMAINS`，按 `(当前域, 首段, 余下)` 映射。`PlanItem.key`、`Decisions.conflict()`（先查三段再查旧键）、`apply_ops`、`template_sync._apply`（`outcomes` 按域分组）同改。

**ADR-FHIC-12 公式审计日志：年度与人工补记；哈希链不在本 spec。** `routers/formula_audit_log.py`：GET 按 `payload->>'year' = :year`（参数化）过滤，无年度的旧条目单列 `legacy_without_year`；POST 请求体改为 `ManualNoteBody(extra='forbid')`，经既有 `append_audit_log` 写 `action="manual_note"`；`formula_settings/audit.py` 与 `routers/wp_formula.py::_write_wp_formula_audit` 写入的载荷增加 `year`（调用方式与异常处理不变）。`audit_log_helper.py`、`workers/audit_log_writer_worker.py`、`routers/audit_logs.py` 不改；哈希链加固的设计输入（含第 3 轮复核第 3、13、21 条的修法）整理在 §8.1 S10。

**ADR-FHIC-13 附件隔离：可空列 + 回填 + 列未就绪 503 + 端点分级 + 字面匹配。** 迁移 V{n} 的步骤以本 ADR 为准（§7 只列摘要）：①`ADD COLUMN IF NOT EXISTS project_id uuid`（可空：X1 先迁移后推送，其间旧代码写入的行不带该列，非空约束会让旧代码报错）；②`UPDATE attachment_lineage al SET project_id = a.project_id FROM attachments a WHERE a.id = al.attachment_id AND al.project_id IS NULL`；③`CREATE INDEX IF NOT EXISTS (project_id, target_type, target_ref)`。不删行、不加外键（附件回收站清理路径有物理删除，实施时 grep 确认；外键会把清理变成报错）、不因孤儿失败：孤儿（附件已不存在）与迁移后旧代码写入的行 `project_id` 为空，查询条件 `al.project_id = :pid` 使其对任何项目不可见（fail-closed）。修复工具 `backend/scripts/fix/attachment_lineage_orphans.py`：默认只读逐行列出 `{lineage_id, attachment_id, 原因 ∈ 孤儿 | 未回填}`；`--apply` 先把这些行原文写入 `backend/backups/attachment_lineage_orphans_<时间>.json`，再回填可归属的行、删除孤儿。代码先于迁移运行（列不存在，F56 的迁移失败或部署顺序错误）时：新模块 `services/attachment_lineage_schema.py::lineage_project_column_ready(db) -> bool` 查 `information_schema.columns`，只缓存 True（False 每次重查，单次 < 1 ms，测试可清缓存）；附件三端点、`unified_lineage_service._query_attachments` 与全部 `AttachmentLineage` ORM 使用点（实施时 grep，清单写入任务说明）在 False 时返回 503 `ATTACHMENT_LINEAGE_MIGRATION_PENDING`「附件溯源迁移 V{n} 未完成，请先执行迁移」（溯源子源记入 `errors`），不触达新列。端点：三端点在既有可见性检查后取附件 `project_id`（附件不存在 404），POST/DELETE `assert_project_permission(..., "edit")`、GET `"readonly"`；POST 写入 `project_id`。查询：`al.project_id = :pid AND al.target_type = :t AND (al.target_ref = :ref OR al.target_ref LIKE :prefix ESCAPE '\\') AND wa.is_deleted = false`，`prefix = escape_like(object_id) + '!%'`（`object_id` 含 `!` 时只做等值）；对象类型映射 `{"wp_cell":"wp_cell","report_row":"report_row","note_cell":"note_section"}`，其他类型按原值精确匹配（ADR-16）。

**ADR-FHIC-14 门禁：五态 + 分支清单 + 保存点包装 + 一个判定函数 + 默认只提示（D2）。**
1. **模型**：`_models.py` 为唯一 `CheckItem` / `ConsistencyResult`（删 `_impl.py` 副本，`__init__` 改导出 `_models`）。`CheckItem` 增 `status: Literal["passed","failed","not_executed","not_applicable","error"]`、`reason: str = ""`、`branch_id: str = ""`；`passed` 字段保留，由工厂按 `status == "passed"` 填写（不再单独传入），读 `.passed` 的旧调用方语义随之变严（未执行不再算通过）；工厂 `_ok / _fail / _not_executed(name, branch_id, reason, severity) / _not_applicable(...)`。HEAD 的出口按 F63 一一转换：比较出口 → `_ok` / `_fail`（同一比较表达式），字面量 `passed=True` 的跳过出口 → `_not_executed` / `_not_applicable`，异常出口 → `_guarded`。`has_blocking_failures` = 「阻断级 ∧ failed」，与 HEAD 逐项同义（HEAD 只有比较出口会为 False）；新增 `would_block_when_enforced`（阻断级 ∧ status ∈ {failed, not_executed, error}）与 `status_counts()`。
2. **取数辅助**：`_helpers.py` 删除 8 处吞异常（异常上抛给包装），返回 None 只表示真实无数据；`_get_wp_parsed_data` 改为 `_probe_wp(project_id, wp_code) -> WpDataProbe{state ∈ present|empty|empty_form|trimmed|absent, parsed_data}`：absent = 无 wp_index；trimmed = 有 wp_index 但无未删 working_paper 且有已删记录（裁剪的落库形态实施时现读确认，写入任务说明）；empty_form = `parsed_data` 为空且该底稿有 `checklist_responses` 行；empty = 两者皆空。映射：present ⇒ 计算；absent / empty ⇒ `_not_executed`（kind=missing）；empty_form / trimmed ⇒ `_not_applicable`。
3. **包装**：每个检查方法挂 `@_guarded("<check_id>")`：`async with self.db.begin_nested():` 包住方法体；任何异常 ⇒ 回滚到保存点，产出 `CheckItem(status="error", branch_id=f"{check_id}.exception", reason=f"检查异常：{类型}：{消息[:200]}")` + `logger.warning`，后续检查不受影响。方法体内既有 `except Exception` 删除或改为带字面量分支号的工厂调用。
4. **分支清单** `_branches.py`：`BRANCHES: dict[str, BranchSpec(check, kind ∈ missing|unsaved|partial|not_applicable|exception, fixture)]`。AST 守卫：`{装饰器字面量 check_id + ".exception"} ∪ {_not_executed / _not_applicable 的 branch_id 字面量}` == 清单键集合（branch_id 实参必须是字符串字面量，装饰器实参同样）；`except` 块内不得调用 `_ok`；`_models` 之外不得直接构造 `CheckItem(`。
5. **判定**：新模块 `consistency_gate/_decision.py::gate_decision(result, *, consumer: Literal["chain_rule","export_package"]) -> GateDecision{blocks, items, mode}`，`mode = settings.CONSISTENCY_GATE_ENFORCEMENT`（`app/core/config.py` 新设置 `Literal["observe","enforce"] = "observe"`）。各消费方：

| 消费方 | observe（默认，= HEAD 实际效果） | enforce |
|---|---|---|
| `gate_rules_chain.ConsistencyPassedRule`（sign_off、export_package） | 不阻断；`would_block_when_enforced` 时返回 `GateSeverity.warning` 命中「一致性检查有 N 项未通过或未执行（当前为只提示模式）」，location 列检查名与状态 | `would_block_when_enforced` ⇒ blocking 命中「…请补齐数据后重新检查」 |
| `export_package_service`（非 force_export） | `has_blocking_failures` ⇒ `ConsistencyCheckError`（与 HEAD 同） | `would_block_when_enforced` ⇒ 同左 |
| 展示：`chain_workflow /consistency-check`、`dashboard_aggregator._aggregate_vr_summary`、`qc_vr_heatmap`、前端 `ConsistencyGatePanel` | 逐项输出 `status / reason / branch_id` 与五态计数；原计数字段保持「failed」含义，另增未执行 / 不适用 / 异常计数 | 同左 |

`ConsistencyPassedRule` 改属性访问并删 `except → None`：`run_all_checks` 本身抛错 ⇒ observe 下 warning 命中「一致性检查未能运行：…」，enforce 下 blocking 命中。全部消费方年度改取项目年度：为空 ⇒ 规则返回 warning 命中「项目未设置审计年度，未运行一致性检查」，看板该段返回 `unavailable` 原因，热力图 422，consistency-check 维持既有 400；删 `year or 2025`（同文件另两条规则同改）、`year = 2025`、`datetime.now().year`；`qc_vr_heatmap` 补 `require_project_access("readonly")`。消费方守卫（AST）：`backend/app` 中 `run_all_checks(` 的调用方集合 == 上表登记集合（实施时现扫补全），阻断类消费方的函数体内必须调用 `gate_decision`。`ConsistencyBlockingDiffRule` 不是消费方（F51），不改。
6. **影响预览与差分**：一次性脚本 `_tmp_formula_hub/probes/gate_enforcement_preview.py` 在快照库上对每个活项目开 `SET TRANSACTION READ ONLY` 的独立事务跑 `run_all_checks`（项目年度为空的列为「未运行」），输出每项目的导出包判定（observe）、enforce 下会阻断的检查项、状态与原因。同一脚本分别在基线 worktree 与实施 worktree 中运行（候选代码读新列，只能连已迁移的快照库；门禁检查不读序时账，快照缺这两张表的数据不影响结果），逐项目比较导出包判定：差异只允许来自需求 16.1 的口径修正并逐项列出，其余差异数须为 0。输出作为决策项 X4 的附件。

**ADR-FHIC-15 试算平衡口径识别。** 纯函数 `consistency_gate/_tb_sign.py::balance_diff(sums: dict[str, Decimal]) -> BalanceVerdict{diff, convention, warning}`，`sums` = 五类叶子合计（类别内先 `tb_leaf_codes.select_leaves`；类别为 asset / liability / equity / revenue / expense，出现其他类别 ⇒ `_not_executed(branch_id="tb_balance.unknown_category")`）。口径：负债合计 < 0 ⇒ `debit_positive`；> 0 ⇒ `v2_positive`；= 0 时按权益同规则判；两者都为 0 ⇒ `_not_executed(branch_id="tb_balance.sign_unknown")`。差额：`debit_positive` ⇒ 五类之和（附告警「试算表为借正贷负口径」）；`v2_positive` ⇒ `asset − liability − equity − (revenue − expense)`。|diff| ≤ 动态容差 ⇒ passed，否则 failed（details 列五类合计与口径）。资不抵债（v2 下权益为负、负债为正）按负债符号仍判 v2。`TrialBalanceService.check_consistency` 若为同一判据（实施时 grep）共用。

**ADR-FHIC-16 lineage / timeline 子源隔离。** 每个子源包 `async with db.begin_nested()`，异常 ⇒ 回滚到保存点、`errors.append({"source","message"})`、`logger.warning`。`_SOURCE_BY_OBJECT_TYPE = {"wp_cell": "workpaper", "report_row": "report", "note_cell": "disclosure"}`；`tb_row`、`adjustment` 不在表中 ⇒ 溯源来源为空、`partial=false`，附件子源按请求的 `object_type` 原值精确匹配 `target_type`。identifier：wp_cell = `object_id.split("!", 1)[0]`、report_row = 行次、note_cell = 章节码；`trace_section` 只对 note_cell 调用。timeline 五源字段：审计 `payload->>'project_id'` + `ts`；发布 `status='published'` + `published_at/change_set/published_by`；模板版本 `published_at`；项目准则取 `formula_settings.projects.get_project`。响应加 `partial/errors`、`unavailable_sources`。

**ADR-FHIC-17 自定义函数移出内核。** 注册与 handler 搬到 `services/formula_custom_functions.py`：`register_custom_function(name, expression, description="", param_names=()) -> dict`（名称 `.upper()`、参数名去重校验，元数据 `{expression, description, param_names}` 存进程内表，`FormulaEngine` 同名方法只转发，路由不改调用形状）；注册时用 `called_function_names` 建「自定义 → 引用函数」图做 DFS，自环 / 互环 ⇒ `ValueError`（路由既有 400）；handler 用 `ContextVar` 记嵌套深度（上限 8），内层 `not ok` ⇒ `raise FormulaEvalError(内层原因)`；参数个数 ≠ `len(param_names)` ⇒ `FormulaEvalError`。

**ADR-FHIC-18 「未审数」成为规范列。** `COLUMN_ALIASES["未审数"] = "未审数"`；`_load_tb` 增列 `"未审数": unadjusted_amount`（叶子求和同 ADR-03）；`from_simple_map` 不再被中央 execute 使用。同任务改写 `test_formula_runtime_zero_regression.py::BASELINE_COLUMN_ALIASES_PRE_WAVE2` 该键，说明「旧断言固化了缺陷」。受影响消费方：中央 execute、debug、XR-07、底稿 ADJ 预载路径，各配回归（需求 2.1、2.8）。

**ADR-FHIC-19 中央执行合同 + 执行预算。** 新模块 `services/formula_central_execute.py::execute_central(db, project_id, year, formula) -> dict`（`FormulaEngine.execute/batch_execute` 薄转发）：①预检 `function_support_matrix.called_function_names(expr)`（剔除引号段后提取全部 `标识符(`，大写）逐个分类 —— ∈ `FUNCTIONS` ⇒ `require_function_support(name, CENTRAL_BATCH)`；∈ `BUILTIN_FUNCTION_NAMES` 或已注册自定义函数 ⇒ 放行；否则 `FormulaSupportViolation`（路由 422）；②`formula_preloader.preload(..., gaps=gaps)`；③缺科目：公式引用科目码（含区间）对本项目年度 `trial_balance` 做一次前缀 `EXISTS`，零命中记 `missing`；④`execute`（外包 `formula_warnings.collect()`）→ `ok = result.ok and not gaps and not missing`；返回 `{value: float | None, ok, state, errors, warnings, formula, error}`。`report_config` 两执行端点逻辑搬入 `services/report_config_execute.py`（batch 串行 `for`；请求体改 pydantic 模型、`year` 必填，N6）。`/api/formula/debug` 改用同一预检与预算。

预算 `services/formula_budget.py::run_with_deadline(db, factory, *, seconds)`：`nested = await db.begin_nested()`；PG 上先读 `current_setting('statement_timeout')`，再 `set_config('statement_timeout', :ms, true)`，`ms = settings.FORMULA_EXECUTE_TIMEOUT × 1000 − 500`（单条语句由数据库先以 QueryCanceled 结束，属普通数据库错误、保存点可回滚）；`await asyncio.wait_for(factory(), seconds)` 只作 Python 侧兜底；成功 ⇒ 恢复原值后 `nested.commit()`；`asyncio.TimeoutError` 或语句被取消（`DBAPIError` 的 `orig.sqlstate == "57014"`，不依赖驱动异常类名）⇒ `nested.rollback()`（同时撤销该 GUC）后抛 `FormulaTimeout`（504）；保存点回滚本身失败（驱动停在操作进行中）⇒ `await db.invalidate()` 后抛 504，该会话不再复用；其他异常回滚后原样上抛。`seconds`：单条 execute / debug / report-config 单条 = `FORMULA_EXECUTE_TIMEOUT`（现值 10）；两个 batch 端点整批 = 新设置 `FORMULA_BATCH_TIMEOUT`（默认 60）。条数上限：`batch-execute` 200（既有）、`execute-formulas-batch` 1000（新；实施时现算全部活项目「内置 + 用户表间审核规则数 × 2」与报表试算的最大批量写入任务说明，须 < 1000，否则调整上限并说明）。SQLite 跳过 `set_config`。

**ADR-FHIC-20 发布记录可见性（SQL 下推）。** `publish.list_publishes(db, *, viewer, domain, scope, status, limit)`，`viewer = await template_access.Viewer.load(db, user)`（`member_projects` 即本人项目集合，F49）：admin 不过滤；否则 SQL 条件 = ①`target='global' AND status='published'` OR ②`target='global' AND status='pending' AND (published_by = :uid OR source_project_id = ANY(:member))` OR ③`target='projects' AND (source_project_id = ANY(:member) OR summary->'changed_projects' ?| :member_text)` OR ④`target='template'`。④的模板可见性在 Python 侧逐条 `viewer.can_view`；本批过滤后不足 limit 时以最后一条的 `(published_at, id)` 为游标继续取下一批（每批 limit 条），直到满 limit 或无更多。③的返回项从 `summary` / `change_set` 删去非本人项目条目。`summary` 列类型实施时现读，非 jsonb 则条件写 `summary::jsonb`；SQLite（单测）按方言改走同一四条规则的 Python 过滤 + 同一游标补取。

**ADR-FHIC-21 预设库归一只改未注册别名。** `preset_library.convert_prefill_presets` 只把 `TB_SUM(` 改为 `SUM_TB(`（正则限定函数名边界与引号外），不调用 `preset_acnr_migration` 的整表 `LEGACY_ALIAS_MAP`（它会把已注册的 `TB_AUX` 改成 `AUX`，两者取数口径不同，F7）；数据文件 `prefill_formula_mapping.json` 不改。

**ADR-FHIC-22 wired 由读取入口派生。** `formula_settings/consumers.py::READER_ENTRIES: dict[str, tuple[str, ...]]` 写死各域有效定义读取入口：report → `effective_report.load_effective_report_configs`；push → `push_settings.effective_push_rules`；consol_note → `consol_note_settings.effective_formulas`；cross_check → `cross_check_rules.run_user_rules`；note → `note_settings.materialize`；wp → `wp_effective.effective_cell_formulas`；tb_detail → 无。`wired_domains()` = 入口非空且该入口在 `backend/app`（排除 `formula_settings` 包与 `routers/formula_settings.py`）中至少被一个生产模块调用的域。守卫 AST 统计对这些名字的调用（`Name` / `Attribute` 末段），通用 `effective_slots`（目录、依赖面板读全部域）不计；登记表与 AST 结果不一致即红；删 `WIRED_DOMAINS` 常量。

**ADR-FHIC-23 利润表归属行：种子 + 生成器守卫 + 存量升级工具（决策项）。** 种子四套按需求 6.1 写显式公式（行次按种子行名定位）；N1 判定出的写入方加两条约束：已有显式定义不覆盖；生成区间含其他 `is_total_row` 则不生成并 warning。存量升级工具 `backend/scripts/fix/republish_report_seed_rows.py`：常量 `KNOWN_BAD`（每套准则 × 行次的精确旧公式文本，实施时由只读查询取得并注明查询）与目标（由需求 6.1 按行名解析）；默认只读打印旧值 / 目标 / 动作；`--apply` 在事务内 `SELECT … FOR UPDATE`，旧值 ≠ `KNOWN_BAD` 的行跳过并报告，其余经 `publish_global(domain="report", scope=<准则>, source="seed", request_id="seed-upgrade-is-attribution-<准则>")` 发布（同 request_id 重放即幂等），标过期走 ADR-04，不调报表重算。本 spec 只在回滚事务内跑 `--apply`（测试）；对真库执行为决策项 X2。真库守卫 `test_report_attribution_rows_live_pg.py`：8 行各自 ∈ {目标定义, `KNOWN_BAD` 对应文本}，否则红；输出待升级清单。

**ADR-FHIC-24 独立金标准求值器。** `tests/formula_hub/gold_report_evaluator.py`（只在测试中）：输入 = 原始 SQL 行（`report_config` 生效公式文本、`trial_balance` 行）；独立实现词法 + 递归下降，支持现存报表公式实际出现的 `TB`、`SUM_TB`、`ROW`、`SUM_ROW`、数字、`+ - * /`、括号（语法以实施时扫描现存公式所得为准，未识别项收集后断言为 0）；叶子筛选在测试内另写（不 import 生产叶子函数）；列名映射在测试内写死；按（报表类型序, 行次）顺序求值，`SUM_ROW` 取同表行次区间。独立性守卫 `test_gold_evaluator_independence.py`：AST 断言该文件只 import 标准库、`sqlalchemy` 与测试夹具，禁止 `app.services.report_engine`、`amount_resolver`、`tb_leaf_codes`、`report_row_compute`、`formula_engine`、`formula_preloader`。false-fresh 正例数据（需求 5.4）：回滚事务内新建【测试】项目，`INSERT … SELECT` 复制医疗器械（按项目名定位、未删、年度 2025）的 `trial_balance` 全部行并替换 `project_id`；`report_config` 按准则全局共享、V199 项目层 0 行（F33），故只需把【测试】项目的准则设为与医疗器械相同；以 `skip_recalc=True` 重新生成（不重算试算表，保持复制来的数据）后断言「未过期行数 > 0 且至少 1 行引用父子并存科目」。反向变异：生产 `select_leaves` 改为返回全部行 ⇒ false-fresh 守卫必红。

**ADR-FHIC-25 真 PG 测试基座 = 一次性快照库（共享库不执行任何 DDL）。** 候选代码给三张表映射了新列，直接连未迁移的共享库会让 ORM 读写这些表报列不存在；在共享库的事务里临时执行迁移 SQL 又会让 ALTER 的排他锁挡住开发服到用例结束（第 3 轮设计的做法，弃用）。
1. **快照**：一次性脚本 `_tmp_formula_hub/probes/snapshot_db.py create | migrate | drop`。`create`：经 `docker exec audit-postgres` 在容器内执行 `createdb fh_snap_<yyyymmddHHMM>`，再 `pg_dump -Fc --exclude-table-data=tb_ledger --exclude-table-data=tb_aux_ledger audit_platform | pg_restore --no-owner -d <快照>`（数据走容器内管道，不落主机文件；两张序时账表只建结构，其余约 1 GB，F62；dump 持共享读锁，期间并发会话的 DDL 会等待）。`migrate`：用实施 worktree 的代码执行 `MigrationRunner(database_url=<快照>).run_pending()`，输出 executed / failed（即 X1 的预演）；本 spec 迁移文件改动后先 `drop` 再 `create` + `migrate`。`drop`：`DROP DATABASE … WITH (FORCE)`。门禁检查与报表生成（`skip_recalc=True`）不读序时账；依赖序时账数据的既有用例在基线与候选上同样受影响，回归时按基线复现登记。
2. **测试进程环境**：`run_pg_suite.py` 与回归、预览、基准脚本一律以子进程启动，环境 = `DATABASE_URL=<快照>`、`GT_REQUIRE_PG=1`、`REDIS_URL=redis://localhost:6379/15`（F64：事件流不进开发服的 0 号库，免得开发服重启时重放测试事件；开工前确认 15 号库 `DBSIZE = 0`，收尾 `FLUSHDB` 该库）。
3. **`tests/formula_hub/conftest.py`**：`@pytest.hookimpl(trylast=True) pytest_collection_modifyitems`：`GT_REQUIRE_PG=1` 而 `DATABASE_URL` 非 PostgreSQL ⇒ `pytest.UsageError`（整轮失败，不出现 skip）；根 conftest 的跳过逻辑不改。夹具 `pg_tx`：独立连接 + 外层事务 + `AsyncSession(bind=conn, join_transaction_mode="create_savepoint")`，结束一律回滚。夹具 `committed_project`（只供需求 8.1 的多会话并发用例）：库名不以 `fh_snap_` 开头 ⇒ `pytest.fail`（提交型夹具绝不连共享库），真提交建【测试】项目与所需行，结束按主键删除并断言删净。连不上库且 `GT_REQUIRE_PG=1` ⇒ `pytest.fail`。

## 3. 逐需求实现要点（文件 / 接口 / 边界）

- **需求 1**：ADR-06/07、§8.2；`formula_runtime/freeze.py`（新，暂存）、`draft_refresh_orchestrator.py`（三段式 + `_acquire_project_lock`）、`routers/draft_refresh.py`；`wp_cell_reader.py`、`wp_ref_strict.py`（新）、`formula_wp_semantics.py` + `tests/test_formula_wp_semantics.py`；`formula_runtime/typed_eval.py`（新）、`coordinator._build_batch_definitions`；`wp_formula_eval_service.evaluate_wp_formula_expression`（`wp_values` / `strict_wp` / None 不代入）；`formula_engine.WPExecutor.execute`（`year`、单元格分支、`WP_COLUMN_KEYS`）；`adapters/report.py`、`adapters/note.py`、`adapters/workpaper.py`、`wp_parsed_data_service.write_cell_to_parsed_data`（`require_existing_sheet`）；预览端点 `routers/wp_formula.py` 改调 `typed_eval.evaluate_single`。边界：单元格两参零个批内目标且存值不存在 ⇒ blocked「单元格不存在」；目标单元格为空但工作表存在 ⇒ 允许写。
- **需求 2**：ADR-01/02/18/19；`formula_engine.py`（失败语义、`ROUND_HALF_UP`、别名、AST 预算）、`formula_arity.py`、`formula_central_execute.py`、`formula_budget.py`、`function_support_matrix.called_function_names`、`routers/formula.py`、`routers/formula_debug.py`、`report_config_execute.py`、`routers/report_config.py`、`models/workpaper_schemas.FormulaResult`（增 `ok/state/errors/warnings`）、`core/config.py`（`FORMULA_BATCH_TIMEOUT`）。
- **需求 3**：ADR-07/08/21；`refresh_outcome.py`（新）、`draft_refresh_orchestrator.py`、`draft_refresh_service.py`（结果字段、两路径计数门槛）、`report_engine.generate_all_reports(skip_recalc, publish_events, summary_out)` + `GenerateSummary`、`routers/draft_refresh.py`、`schemas/formula_runtime.DraftRefreshResponse`、前端 `formulaRuntimeContract.ts`、`GtRefreshScopeDialog`；`preset_library.convert_prefill_presets`。
- **需求 4**：ADR-03；`tb_leaf_codes.py`、`formula_warnings.py`（新）+ F8 取数函数；`_get_tb_rows_prefix` 缓存宽集合、叶子筛选在求和时做；`formula_push/engine.run` 结果并入告警。
- **需求 5**：ADR-04/05/24；`report_freshness.py`、`report_row_compute.py`（新）；`report_engine` 三路；F38 读者 + 报表视图 / 导出；`publish.publish_global`、`project_ops.save_overrides / restore_global` 出口调 `mark_changed`。
- **需求 6**：ADR-23 + ADR-05 组成行 warning；`backend/data/report_config_seed.json`、`report_formula_service.py`、`scripts/fix/republish_report_seed_rows.py`。
- **需求 7**：ADR-13/20；V{n} + R{n}、`models/attachment_lineage_model.py`、`attachment_lineage_schema.py`（新）、`routers/attachment_lineage.py`、`unified_lineage_service._query_attachments`、`scripts/fix/attachment_lineage_orphans.py`；`routers/formula_settings.py::get_publishes` + `publish.list_publishes`。
- **需求 8**：ADR-11；V{n+1}、`FormulaSyncItem.revision`、`pending.upsert_pending`、`project_ops.resolve_items`、`engine.PlanItem/Decisions`、`apply_ops`、`template_sync`、`routers/formula_settings.py::ResolveBody`；前端 `components/formula/settings/FormulaPendingSyncDialog.vue`、`FormulaConflictTable.vue`。
- **需求 9、10**：ADR-16；`unified_lineage_service.py`、`formula_timeline_service.py` 与响应 schema。
- **需求 11**：ADR-12；`routers/formula_audit_log.py`（GET 年度、POST `ManualNoteBody`）、`formula_settings/audit.py`、`routers/wp_formula.py::_write_wp_formula_audit`（载荷 `year`）。
- **需求 12**：ADR-09/19；`formula_settings/validator.py`（新）、`stores.py` / `domain_stores.py`、`publish.py`、`apply_ops.py`、`rollback.py`、`report_config_execute.py`。守卫 AST 扫 `ReportConfig(`、`.formula =`、`update(ReportConfig)`、`FormulaSetting(`、`.definition =`。
- **需求 13**：ADR-10/11；`rollback.py`、`routers/formula_audit_log.py::RollbackRequest`、`audit.change_entry`（`old_definition/new_definition`）、三个删除端点 + `project_ops.restore_global(expected_versions=…)`；前端 `FormulaHistoryTab.vue`、`workpaper/FormulaStatusPanel.vue`、`settings/FormulaTemplateDetailDrawer.vue`、`settings/reportEffectiveRows.ts::restoreReportRows`、`services/formulaSettingsApi.ts`。
- **需求 14**：ADR-17；`formula_custom_functions.py`（新）；`formula_settings/dependencies.py` 正则改 `(['"])(…)\1`、捕获组编号随之调整。
- **需求 15**：`GtFormulaPresetDialog.vue`、`template-library/FormulaTab.vue`、`settings/FormulaSettingsToolbar.vue`（`APPLY_SCOPE_DOMAINS = ['report','tb_detail','cross_check']` 单一来源）、`FormulaManagerDialog.vue`、`FormulaHistoryTab.vue`；后端 `formula_settings/tb_detail.py::propagate_tb_detail`、ADR-22。
- **需求 16**：ADR-14/15；`consistency_gate/_models.py`、`_impl.py`、`_helpers.py`、`_cycle_checks.py`/`_base_checks.py`/`_d4_checks.py`/`_e1_checks.py`（若含构造点）、`_branches.py`、`_decision.py`、`_tb_sign.py`（新）；消费方 `gate_rules_chain.py`、`export_package_service.py`、`routers/chain_workflow.py`、`dashboard_aggregator_service.py`、`routers/qc_vr_heatmap.py`；`core/config.py`（`CONSISTENCY_GATE_ENFORCEMENT`）；前端 `workpaper/ConsistencyGatePanel.vue`。

## 4. 错误处理（失败条件 → 可恢复性 → 调用方收到 → 日志）

| 操作 | 失败条件 | 可恢复 | 调用方收到 | 日志 |
|---|---|---|---|---|
| Runtime 刷新（冻结期） | 计划含 Runtime mutation | 可（等解冻） | 409 `FORMULA_RUNTIME_FROZEN`，未取锁、业务表不变 | info |
| Runtime 计划 | 环 / 歧义 / 底稿、表、格不存在 / 目标表缺失 / 年度不符或未设置 / needs_review / 外部取值取不到 / 引用写法无法识别 | 可 | 该条 `blocked` + 中文原因，不产 mutation；整体按 ADR-08 派生 | warning（含 formula_id） |
| WP 读取 / 严格外部取值 | 同上各类 | 可 | `WpCellRead.state/reason`；`WPExecutor` 两参仍得 0（登记差异） | debug |
| WP 读取 / 严格外部取值 | 数据库异常 | 否 | 原样上抛（端点 500，事务回滚） | exception |
| 中央 execute / debug | 除零 / 参数 / 列名 / 缺数 / 缺科目 / 超预算 | 可 | 200，`ok=false, value=null, errors` | warning |
| 中央 execute / debug | 表达式含未知或未支持函数 | 可 | 422 `FORMULA_FUNCTION_UNSUPPORTED` | info |
| 执行预算 | 语句超时（QueryCanceled）或整体超时 | 可 | 504 `FORMULA_TIMEOUT`，会话已回到保存点、GUC 已撤销；保存点回滚失败 ⇒ 会话作废后 504 | warning |
| 报表逐行计算 | `FormulaResult` 非 ok / 引用行未就绪 | 可 | 旧行保留旧值 / 新行 NULL，`is_stale=true`、`calc_error`，进 `failed_rows`；生成接口 200 | warning |
| TB 父子不符 / 组成行无公式 | — | 可 | 结果 `warnings`，值按叶子 / 按 0 | info |
| 定义写入标过期 | `mark_changed` 抛错 | 否 | 随定义写入事务回滚（定义与过期标记同成同败），端点 500 | exception |
| Draft Refresh report 范围 | 试算表重算失败 | 可 | 该范围 failures（保存点回滚）⇒ `partial_success` / `failed` | warning |
| Draft Refresh | `outcome=failed` | 可 | 200 `status=failed` + failures，路由回滚、无事件 | warning |
| Draft Refresh | 幂等命中 | — | 200 `status=idempotent_hit` + 首次 outcome 与计数，不执行 | info |
| Draft Refresh | `ReportEngine` 抛未预期异常 | 致命 | 500 + 回滚（既有路由行为） | exception |
| 附件写入 / 删除 | 附件不存在 / 无本项目 edit | 否 | 404 / 403，行不变 | warning |
| 附件溯源（列未就绪） | V{n} 未执行或失败（代码先于迁移运行） | 可（执行迁移） | 503 `ATTACHMENT_LINEAGE_MIGRATION_PENDING`；溯源子源记入 `errors` | warning |
| 附件迁移 V{n} | 存在无法归属的行 | — | 迁移照常完成，孤儿 `project_id` 为空、对任何项目不可见，修复工具列出 | 迁移内 `RAISE NOTICE` 计数 |
| 任一迁移 | SQL 执行失败 | 可 | 记入 `schema_migration_failures`、应用继续启动、health degraded（F56）；依赖该列的路径按上一行 503 或随事务报错 | error |
| 待确认处理 | 缺 revision / 过期 | 可 | 428 / 409 `SYNC_ITEM_STALE`，目标不变 | info |
| validator | 任一规则不过 | 可 | 422 `FORMULA_DEFINITION_INVALID` + `problems[]` | info |
| 回滚 | 条目不存在或不属本项目 / 无快照 / 缺版本 / 版本不符 | 可 | 404 / 422 `ROLLBACK_NOT_AVAILABLE` / 428 / 409 | info |
| 删除 | 缺版本 / 版本不符 / overrides 版本个数不等 | 可 | 428 / 409 / 422，行不变 | info |
| 自定义函数注册 | 自环 / 互环 / 参数名重复 | 可 | 400 中文原因 | info |
| lineage / timeline 子源 | 任一子源异常 | 可 | 200 + `partial=true` / `unavailable_sources` | warning |
| 门禁检查项 | 缺数 / 未保存 / 部分数据 / 口径无法识别 | 可 | `status=not_executed` + `reason` + `branch_id` | debug |
| 门禁检查项 | 结构性不可用（在线表单模式、已裁剪） | — | `status=not_applicable`，任何模式都不阻断 | debug |
| 门禁检查项 | 检查方法或取数辅助抛异常 | 可 | 保存点回滚，`status=error` + 原因，其余检查照常 | warning |
| 门禁消费方 | `run_all_checks` 自身抛错 / 项目年度为空 | 可 | 规则：observe warning 命中、enforce blocking 命中；看板 `unavailable`；热力图 422；consistency-check 400 | warning |
| 归属行升级工具 | 旧值与 `KNOWN_BAD` 不符 | 可 | 该行跳过并报告，其余照常 | — |
| 修复 / 升级工具参数 | 缺 `--apply` 以外的必需参数或值非法 | 可 | 退出码 2 + 中文原因，不写 | — |

## 5. 外部输入校验

| 输入 | 规则 | 失败 |
|---|---|---|
| `FormulaRequest.params.formula` | 必填字符串，1~4000 字符 | 422 |
| batch-execute 列表 | 1~200 条，同项目同年度（既有） | 422 |
| report-config 执行请求体 | pydantic：`project_id` UUID 必填、`year` int 必填、`formula` 1~4000、batch `formulas` 1~1000 | 422 |
| `ResolveBody.resolutions[].revision` | `int \| None`，`ge=1`；缺失由服务层判定 | 428（缺）/ 422（类型）/ 409（不符） |
| `RollbackRequest` | `source_log_id` UUID 必填；`expected_version: int \| None`（`ge=0`）；`extra='forbid'` | 422 / 428 |
| `ManualNoteBody` | `note` 1~500 字符；`row_code` ≤64；`module` ∈ 已知模块；`extra='forbid'` | 422 |
| 删除 `expected_version` | `int \| None`（`ge=0`）；overrides 为重复 Query 参数，个数 = `slot_key` 个数 | 428 / 422 |
| lineage `object_id` | 1~200 字符，字面匹配 | 422 |
| 公式定义 | ADR-09 域表；`disabled=true` 只校验结构 | 422 |
| 自定义函数 | 名称 `^[A-Za-z_][A-Za-z0-9_]{0,63}$`、不与内置重名；`param_names` ≤10 个且不重复；表达式既有语法校验 + 环检测 | 400 |
| WP 引用实参（typed_eval） | wp_code 非空；单元格 `^[A-Z]+\d+$`（不区分大小写）；sheet 可空；列名与坏账明细写法按 ADR-06 第 3 点 | blocked「引用写法无法识别」 |
| `CONSISTENCY_GATE_ENFORCEMENT` / `FORMULA_BATCH_TIMEOUT` | 前者 ∈ {observe, enforce}；后者 int 1~600 | 启动时配置校验失败（pydantic settings） |
| 修复 / 升级工具参数 | `--apply` 必须显式给出 | 退出码 2，不写 |

## 6. 不变量与所有者

| 不变量 | 所有者 | 理由 |
|---|---|---|
| 失败不冒充成功值 | L1 `FormulaResult` + 写入方判 `ok` | 一处定义状态 |
| TB 只取叶子、父子不符可见 | `tb_leaf_codes.select_leaves` + `formula_warnings` | 全部取数点共用，结果合并点固定 |
| WP 单元格只有一种读法 | `wp_cell_reader.resolve_wp_cell`（§8.2 契约，两 spec 共用） | 契约测试 + 单一来源 AST 守卫 + `formula_wp_semantics` 登记 |
| Runtime 节点身份稳定 | `WpFormula` 已存稳定三元组 | 展示名重命名不改键（V163 既有约束） |
| 报表新鲜 = 版本一致且未标过期 | `report_freshness` + 三个定义写入出口 | 同事务、含依赖闭包、全部年度 |
| 失败 / 过期行不进依赖计算 | `report_row_compute.build_row_cache` | 三路共用一条缓存规则 |
| 刷新结果真实 | `refresh_outcome.derive_outcome` | 一个状态表，路由只按它提交 / 回滚 |
| 写入前必校验 | `DomainStore` 写方法 + 域校验器表 | 所有发布 / 保存 / 应用 / 回滚最终落到 store |
| 待确认决策不陈旧 | `formula_sync_item.revision`（原子 upsert） | DB 层单语句递增 |
| 附件只在本项目可见 | `attachment_lineage.project_id` + 查询条件 | 数据层隔离；空值行对任何项目不可见 |
| 门禁不假通过、阻断口径一致 | `_models` 工厂 + `_branches` 清单 + `_guarded` + `_decision.gate_decision` | 静态双射 + 逐分支变异 + 消费方守卫 |
| 项目年度唯一来源 | `project_audit_year.fetch_project_audit_year` | 读取函数、门禁消费方共用，不退日历年 |

## 7. 迁移（实施时现扫 `MAX(V*.sql)+1` 取号，写进 tasks 勾选说明；现最高 V205；本 spec 不对共享库执行，见 X1）

| 迁移 | 内容 | 回滚 R |
|---|---|---|
| V{n} | `attachment_lineage.project_id`：加可空列 → 回填 → 索引（步骤见 ADR-13；孤儿保持空值） | DROP INDEX / DROP COLUMN |
| V{n+1} | `formula_sync_item` ADD COLUMN IF NOT EXISTS `revision int NOT NULL DEFAULT 1` | DROP COLUMN |
| V{n+2} | `financial_report` ADD COLUMN IF NOT EXISTS `calc_version int`、`calc_error varchar(500)` | DROP COLUMN |

不跑 ALTER TYPE；新列可空或有默认值 ⇒ 先迁移后换代码时旧代码不受影响（X1 的顺序依据）。三个迁移在快照库上由 MigrationRunner 执行（ADR-25 第 1 点）；V{n} 的孤儿路径在快照库的回滚事务内删列后重放其 SQL 验证。

## 8. 边界裁定、所有权与后续 spec

### 8.0 边界裁定（取代 `p1-00-baseline-recon.md` §4）

依据：①阶段一最终版 `report.md`（APPROVED，晚于 p1-00）§9.1 近期 R1~R8 与 §10 推荐默认；②本工作流阶段二任务书与父会话裁定（第 3 轮复核 HIGH-3：审计哈希链整体移出；HIGH-4：门禁默认不新增阻断）。p1-00 是阶段一的中间稿，凡与上述冲突以后者为准。

| p1-00 条目 | 旧裁定 | 最新决定 | 依据 | 唯一负责方 |
|---|---|---|---|---|
| P0-1~P0-6 | 本轮 | 本 spec（含 P0-1 A1~A6 全部） | 任务书 | 本 spec |
| P1-1、P1-2、P1-8 | 本轮 | 本 spec | 任务书 | 本 spec |
| P1-3 审计链 | 本轮 | 公式审计日志伪造入口与年度在本 spec；哈希链加固（锁、可重放哈希、链尾、分叉、worker）移出 | 父会话裁定（复核第 3 条上线顺序风险） | 本 spec / S10 |
| P1-5 wp 全轨读 effective + S5 旧保存路径 | 本轮 | 移出：属全域 resolver 迁移 | 任务书中期清单；report §9.2 M1~M2 | S1 |
| P1-7 settings durable outbox | 本轮 | 移出：规模中等，任务书允许「规模小才纳入」 | 任务书；report §9.2 M4 | S4 |
| P2-1 consol_note scope / 角色 | 本轮 | 移出 | 任务书中期清单 | S7 |
| P2-3 预设假保存 / 写请求判状态码 | 本轮 | 本 spec；试算平衡表手工值读回移出 | 任务书；report §9.1 R7 | 本 spec / S3 |
| P2-5 发布可见性 / 删除策略 / 订阅按钮权限 | 本轮 | 可见性与删除 CAS 本 spec；订阅按钮权限移出 | 任务书清单只列前两项 | 本 spec / S6 |
| P3-1 wired 常量、P3-2 `specAReady` | 本轮 | 本 spec | report §9.1 R5、R7 | 本 spec |
| consistency_gate 82 处 `passed=True` | 不碰（待拍板） | 本 spec：五态 + 默认只提示，开启阻断为决策项 X4；签字人逐项确认留痕移出 | report §9.1 R8 + §10；父会话裁定 | 本 spec / S2 |
| 附注执行器只回写 auto_calc（P1-12）、校对目录执行状态（P1-13） | — | 移出 | 任务书未列；report §9.1 R8 其余两项 | S2 |
| 勘误承接（`formula-global-settings-sync` S5/8.2、`formula-governance-coverage-closure` L1 期间/列名） | 本轮 | 本 spec 发布验收清单登记勘误；实现归 S1 | p1-00 §4.1 | 本 spec（登记）/ S1（实现） |
| p1-00 §4.2 其余（附注模板绑定、生成鉴权、`legacy_value_keys`、S 循环文件、年度兜底、附注权威源、tb_detail 定位） | 不碰 | 不变 | — | 原 spec |

### 8.1 后续 spec（发布验收清单在归档前为每项建目录 + requirements.md（含负责范围、依赖、触发条件）+ INDEX 行）

| # | spec 名 | 内容 | 依赖 / 先后 |
|---|---|---|---|
| S1 | `formula-grammar-resolver-unification` | 单一 registry 生成前后端函数表（前端 `PRIOR`、`%`）；多余参数报错；`value=None` 全量迁移；note/cell 求值器 float→Decimal；wp 全轨读 effective + S5；报表按依赖排序求值；`typed_eval_strictness` 差异收敛；两份勘误的实现 | 依赖本 spec ADR-01~03、06、18、19；ACNR spec 之后 |
| S2 | `check-contract-and-note-executor` | 附注执行器只回写 auto_calc；校对目录执行状态；XR skip 计入签字；表间审核规则「只提示」；门禁开启阻断后签字人逐项确认留痕（D2）；`ConsistencyBlockingDiffRule` 吞异常 | 依赖 ADR-14 |
| S3 | `formula-writer-ownership-and-stale` | section+field 唯一写方矩阵、stale 状态机、`stale_source` 必写、值不变也清 stale；试算平衡表手工值读回；`useEditorSave.ts` 与其余 14 处 `validateStatus` 写请求 | 依赖附注权威源拍板 |
| S4 | `formula-settings-durable-outbox` | 定义与 outbox 同事务、幂等 worker、扇出分批、过期标记入发布事务（P1-7、P1-14、P2-11） | 独立；建议在 S1 前 |
| S5 | `formula-provenance-envelope` | 最终值持久化定义版本 / run_id / 输入摘要；`note_wp_mapping` 来源；零挂载组件裁决 | 依赖 ADR-04、16 |
| S6 | `formula-template-dual-project-pilot` | 双项目真 PG + 登录态 UAT；模板回滚发版、diff、新增 slot；订阅按钮按 edit 权限 | 依赖 S4 |
| S7 | `consol-note-formula-scope-and-roles` | consol_note 只列 consolidated、全局写只给 admin（§10 默认） | 独立 |
| S8 | `formula-e2e-ci-gate` | 公式 Playwright 规格接入会实际运行的 CI | 依赖 CI 环境 |
| S9 | `income-statement-lower-section-formulas` | 利润表净利润 / 综合收益总额及归属拆分行公式补全（D14） | 依赖 ADR-05、23 |
| S10 | `audit-log-chain-integrity` | 审计哈希链加固（原 ADR-12 全部内容）+ `append_audit_log` 调用方吞异常逐个裁决（p1-00 现算 41 处 / 25 个文件）。设计输入：①链尾按链接关系唯一（非 `ts`），新表 `audit_chain_head(chain_key PK, tail_entry_id, tail_hash, updated_at)` 一次性回填，写入时锁内读 head、`EXISTS(prev_hash = head.tail_hash)` 判绕过写入、插入后更新 head，全链反连接只用于校验与分叉工具；②`append_fork_ack(db, key, *, survivor_entry_id, dead_entry_id, operator_id, reason)` 锁内校验「未确认链尾集合 == {survivor, dead}」后以 survivor 的 `entry_hash` 为 `prev_hash` 直接插入、不经链尾查找；③worker `_write_batch` 每条链一个 SAVEPOINT，链损坏只回滚该链、条目进 `audit:log:quarantine:<chain>`（不计重试上限、不丢弃）；④上线前置：目标库只读分叉扫描「未确认分叉 = 0」（本机全局链现有 1 处，F44），`/api/health` 增 `audit_chain.unacknowledged_forks`（>0 即 degraded），确认工具先于 fail-closed 代码交付并执行，公式发布等写全局链的路径在确认前不得改为 fail-closed；⑤审计链咨询锁是事务内最后获取的咨询锁，先写审计后取锁的调用点登记；⑥v2 可重放哈希：`_hash_v: 2`、`_resource_id` 原样字符串、`_year`（兼容本 spec 在公式审计载荷中写入的 `year`），float 落库前转定点字符串（`format(Decimal(repr(x)), 'f')`）、拒绝 NaN/Inf，往返测试含 1e20；v1 兼容计 `legacy_verified / legacy_unverifiable`；⑦verify-chain 片外前驱锚点与 fork / orphan / missing_prefix / content_mismatch 原因；⑧helper 与 worker 取锁、读链尾失败不写 GENESIS，删 `hash(lock_key)` 与无锁降级。相关事实 F18、F44、F50 | 独立；本 spec 不阻塞它，它也不依赖本 spec |

### 8.2 与 `acnr-foundation-defect-closure` 共用的 WP 单元格读取契约（第 3 轮复核第 1 条，按父会话裁定）

本 spec 采用与 ACNR 设计 §2.5 现行文本**调用兼容**的签名，在其上做向后兼容扩展：ACNR 依赖的参数顺序与字段（`state / value / reason / wp_id / sheet_key`）不变，增加 `blocked` 状态与 `matches / candidates` 字段；ACNR 把非 ok 一律当缺失仍然成立。先落地的一方按下表实现并提交 `backend/tests/test_wp_cell_reader_contract.py`（钉住下表全部行），后落地的一方只接线、不改该测试断言；本 spec 不改 ACNR 的任何文件。

| 项 | 契约 |
|---|---|
| 位置与签名 | `backend/app/services/wp_cell_reader.py`：`async def resolve_wp_cell(db, project_id, year, wp_code, sheet_key, cell) -> WpCellRead`；六个参数均为「位置或关键字」参数（ACNR 的位置调用 `resolve_wp_cell(db, project_id, None, wp_code, column, field)` 成立） |
| 返回 | `WpCellRead`（frozen dataclass）：`state: Literal["ok","missing","blocked"]`、`value: Decimal \| None`（仅 ok 非空）、`reason: str \| None`（非 ok 必有中文原因）、`wp_id: UUID \| None`、`sheet_key: str \| None`（命中记录在 `html_data` 中的真实表名）；扩展字段 `matches: int = 0`、`candidates: tuple[str, ...] = ()`。只认 ok / missing 的调用方把 `state != "ok"` 一律当缺失 |
| 年度 | `year is None` 不比对；否则 `project_audit_year.fetch_project_audit_year(db, project_id)`：None ⇒ blocked「项目未设置审计年度」；≠ year ⇒ missing「底稿年度与项目年度不符」；不退回日历年或 `audit_period_end`（与 `audit-year-calendar-fallback-ratchet` 方向一致） |
| 底稿绑定 | `wp_index.wp_code == wp_code` JOIN 未删 `working_paper`：0 ⇒ missing「项目中没有底稿 {wp_code}」；> 1 ⇒ blocked「底稿记录有歧义」 |
| 工作表 | `sheet_key is None`（两参）：不判表，`matches` = 含该单元格的表数，值取 `extract_custom_cells` 顺序第一个，state 按该值判，调用方自行处理 `matches > 1`；非空：可接受键 = `_catalog_sheet_keys(wp_code, sheet_key).keys`（目录可接受键：模板名 / sheet_code / 别名）∪ {sheet_key}，两侧都经 `stable_key.normalize_sheet_key` 后比较；`_catalog_sheet_keys` 返回 `CatalogSheetKeys(keys, verdict ∈ found|not_found|ambiguous|alias_forbidden, candidates)`，本 spec 落地时恒为 `not_found`（空集），ACNR 落地 `exact_identity.sheet_of` 时只改写该函数体；verdict 为 ambiguous / alias_forbidden ⇒ blocked「工作表名有歧义 / 该别名不能用于取值」并带 candidates |
| 单元格 | `cell.upper()` 与 `rec.cell` 精确相等；同一可接受键集合命中多条且值不同 ⇒ blocked「同一工作表有多份数据」（candidates = 各键）；命中 0 ⇒ missing，区分「没有该工作表的数据」与「单元格未录入」；空串 / None ⇒ missing「单元格未录入」；不能转 Decimal ⇒ blocked「单元格内容不是数值：…」 |
| 异常 | 数据库异常原样上抛，不转 missing |
| `WPExecutor` | 两参单元格分支（本 spec）：既有 ACNR 重定位之后调 `resolve_wp_cell(db, project_id, year, wp_code, None, cell)`，`state != ok` 仍返回 `D("0")`；三参 A1 分支（ACNR）：`resolve_wp_cell(db, project_id, year, wp_code, column, field)` 返回 `.value`；`year` 为仅关键字参数、默认 None；列名与 D2-3 分支两边都不改行为 |
| 三参预载挂点 | 中央 execute / debug：`formula_preloader.preload` 内 `_load_wp` 之后（ACNR 加 1 行 `preload_three_arg_refs`；`FormulaEngine.execute` 由本 spec 搬进 `formula_central_execute`，不再是挂点）；报表：`report_engine.evaluate_formula_result` 的 WP 预载段（ACNR 加 1 行）。本 spec 不改这两处 WP 预载代码，只在 `evaluate_formula_result` 外包告警收集、在调用 `preload` 时传 `gaps` |
| 底稿公式代入 | `evaluate_wp_formula_expression` 两个 WP 代入循环：值为 None ⇒ 记中文错误、不代入、该式无值（本 spec 实现，ACNR 三参返回 None 依赖此行为）；`wp_values` / `strict_wp` 为本 spec 新增 |
| `formula_wp_semantics.py` | 本 spec：新增 `WP_IMPLS` 条目 `wp_cell_reader.resolve_wp_cell`、差异维度 `typed_eval_strictness`、改写 `EXECUTOR_WP_IMPL.data_source`；ACNR：`positional_args` 与 `positional_arg_count` 差异条目（三参 A1）。各改自己的字段，后落地者以先落地者的文件为底 |

**需 ACNR spec 同步采用（交用户转达，本 spec 不改其文件）**：①§2.5 返回值加 `blocked` 与 `matches / candidates`，`acnr_target_values` 把 `state != "ok"` 映射为其输出的 missing（或新增 blocked 展示）；②年度改用 `fetch_project_audit_year`、为空 blocked，删 `EXTRACT(YEAR FROM audit_period_end)`；③可接受键 = 目录键 ∪ `normalize_sheet_key`，实现落在 `_catalog_sheet_keys`；歧义与非数值改为 blocked；④三参预载挂点改为 `formula_preloader.preload` 与 `evaluate_formula_result`，不挂 `FormulaEngine.execute`；⑤三参分支透传 `year=year`；⑥三参取不到代入 None 的处理由本 spec 在 `evaluate_wp_formula_expression` 实现，ACNR 不另写；⑦`formula_wp_semantics.py` 字段分工；⑧契约测试文件名与「后落地方不改断言」；⑨两边都改的棘轮基线（§8.3）后落地方重算；⑩`WpCellRead.sheet_key` 是命中记录在 `html_data` 中的真实键，结果展示用的目录 sheet 名取 ACNR 自己的解析结果。

### 8.3 与其他进行中 spec 的协调（第 3 轮复核第 32 条及现扫）

| spec | 交集 | 约定 |
|---|---|---|
| `audit-year-calendar-fallback-ratchet`（3/18） | 年度棘轮按文件精确相等（F60）；本 spec 修掉 `report_config.py` 2、`qc_vr_heatmap.py` 1、`dashboard_aggregator_service.py` 2、`gate_rules_chain.py` 3 处 | 本 spec 在同一提交下调 `tests/test_audit_year_calendar_fallback_ratchet.py` 对应条目（为 0 删行），只动这四个文件的条目；ACNR 删 `address_registry_v2.py` 一条，后落地方以先落地方的基线为底重算 |
| `formula-fetch-followup-defect-closure`（30/34）、ACNR | 三个鉴权棘轮常量（F61）：本 spec 给 `qc_vr_heatmap`（路径维）与附件、执行类端点补项目校验，现算值下降 | 不主动改三个常量；本 spec 验收（全量回归含三个鉴权守卫）若「与现算差 ≤ 20」断言变红，在本提交把对应常量下调到现算值并记入任务说明；X1 推送时若对方已先下调，冲突以重算的现值解决；本 spec 的端点由自己的配方表钉住，不写入对方的 `_FIXED_ENDPOINTS` |
| `advanced-query-linkage-closure`（设计中） | 其报表源读 `financial_report.is_stale` / `blank_reason` | 本 spec 的过期判据（ADR-04）落地后，该报表源应读 `report_freshness.stale_clause()`；若对方先入库，本 spec 任务 14 把该读者纳入读者清单并改为 `stale_clause()` |
| `s-cycle-linkage-trimming-and-component-wiring`、`consol-note-header-library-and-node-reaggregate`、`d2-skeleton-slot-reuse-and-writeback-speed`、`writeback-followup-issue-closure` | 现扫三件套，未提及本 spec 改动的文件 | 不协调；实施前按 tasks 通用纪律再查一次 |

## 9. 行数门处理（F32；阈值 = 白名单 × 1.05）

| 文件 | 现/阈值 | 处理 |
|---|---|---|
| `formula_engine.py` | 2198/2243 | 中央 execute → `formula_central_execute.py`、自定义函数 → `formula_custom_functions.py`，内核净减；失败语义、舍入、别名、`WPExecutor` 只改分支并提出 `WP_COLUMN_KEYS`。交付后白名单按实测下调 |
| `report_engine.py` | 2625/2827 | 三路逐行逻辑与缓存规则抽到 `report_row_compute.py`，净减 |
| `wp_formula.py` | 1508/1534 | 删除 CAS、审计 `year`、预览改调 typed_eval；超限先把 `_write_wp_formula_audit` 抽到 `wp_formula_audit.py` |
| `draft_refresh_service.py` | 2384/2502 | 结果字段与计数门槛 +20；聚合逻辑在 `refresh_outcome.py` |
| `draft_refresh_orchestrator.py` | 475 | 三段式 + 幂等 +80，仍 < 800 |
| `report_config.py` | 801/未登记 | 执行端点搬到 `report_config_execute.py`，降到 800 内不登记 |
| `consistency_gate/_impl.py` | 2360/未登记 | 删重复类 + 工厂化 + 去内层 except 净减；以 HEAD 真实行数首次登记，交付后改实测 |
| `chain_workflow.py` / `dashboard_aggregator_service.py` / `gate_rules_chain.py` | 699 / 561 / 169 | 只改判定调用与年度，每个净增 ≤ 30 |
| `FormulaManagerDialog.vue` | 4216/4727 | 只改 4 处写请求判定 |
| 新模块 | 每个 ≤ 300 行 | — |

## 10. 测试与变异计划

### 10.1 单元（SQLite / 纯函数）

`tb_leaf_codes`（PBT：随机科目树叶子和恒等、父不计入、告警阈值）、`formula_warnings` 收集嵌套、`formula_arity` 键集守卫、L1 失败语义与舍入、AST 预算、`called_function_names` 与预检分类、常量零除数折叠（`1/0`、`1/(2-2)` 拒、`1/TB(...)` 过）、`_tb_sign` 四口径 + 资不抵债、门禁分支清单双射与消费方守卫、`gate_decision` 两模式 × 两消费方、自定义函数环检测与参数个数、dependencies 单双引号、决策键 `split('|', 2)` 与旧键、`refresh_outcome.derive_outcome` 表驱动（7 行）、`report_row_compute` 三路一致与 `build_row_cache`（只桩数据源）、typed_eval 图构造（歧义 / 环 / 三参精确 / needs_review / 目标表缺失 / 四种写法分类）、`resolve_wp_cell` 与 `read_wp_ref_strict` 各状态（`year=None`；年度分支在真 PG）、`formulaRuntimeContract` 解析器 7 状态。

### 10.2 真 PG（`pg_only`，快照库 + ADR-25 夹具；统计 SQL 排除软删项目）

Runtime 29 行重放与四方一致、adapter 六枚举与 `rows[].values` 形状、读取函数年度契约（三种年度夹具 + 一对多）、冻结 / 解冻端点、中央 execute 华氏 / UAT 金标准与 XR-07、执行预算 `pg_sleep`、Draft Refresh before/after 与事件、报表 false-fresh 守卫（含医疗器械复制正例）、BS-008 叶子金标准、推送 `load_tb_audited` = 叶子和、归属行【测试】重算与 live 状态守卫、附件迁移（回滚事务内重放）与列未就绪 503 与隔离、pending 原子修订号并发（`committed_project`）、timeline 5 类、lineage D2、门禁分支夹具、门禁保存点隔离、门禁消费方端点级用例、医疗器械与华氏口径差额。

### 10.3 端点权限配方表（`test_formula_hub_endpoint_authz.py`）

一份配方表 + `_assert_allowed/_assert_denied`；身份 anon / non_member / ro / auditor(edit) / manager(edit) / qc(review) / eqcr(review) / partner(edit) / admin；`stub_factory` 只桩下游写入，鉴权链真实运行，override 内层 `get_current_user`/`get_db`，禁止 override `require_project_access`；守卫断言 overrides 键集合。对账：配方表涉及的路由模块（`routers/formula.py`、`formula_debug.py`、`report_config.py`、`attachment_lineage.py`、`formula_settings.py`、`formula_audit_log.py`、`wp_formula.py`、`formula_templates.py`、`draft_refresh.py`、`lineage.py`、`formula_timeline.py`、`qc_vr_heatmap.py`、`chain_workflow.py`、`partner_dashboard.py`）中的全部路由，要么在配方表、要么在 `_UNCHANGED_ROUTES`（每条须在 `app.routes` 中真实存在），未登记即红。拒绝用例断言列出的表行数与内容哈希不变。

| 方法 路由 | 放行 | 拒绝 | 拒绝时不变的表 |
|---|---|---|---|
| POST `/api/formula/execute`、`/api/formula/batch-execute`、`/api/formula/debug` | ro, auditor, manager, qc, eqcr, partner, admin | anon 401, non_member 403 | — |
| POST `/api/formula/custom-functions` | admin | 其余登录者 403 | 自定义函数表 |
| POST `/api/report-config/execute-formula`、`/execute-formulas-batch` | ro+ 成员, admin | anon, non_member | — |
| GET `/api/projects/{project_id}/lineage` | ro+ 成员, admin | anon, non_member | — |
| GET `/api/formula-timeline/{project_id}/{year}` | ro+ 成员, admin | anon, non_member | — |
| POST `/api/attachments/{id}/link`、DELETE `/api/attachments/{id}/link/{link_id}` | auditor, manager, partner, admin（附件所属项目 edit） | anon, non_member, ro, qc, eqcr | `attachment_lineage` |
| GET `/api/attachments/{id}/links` | ro+ 成员, admin | anon, non_member | — |
| GET `/api/formula-settings/publishes` | 全部登录者（结果按 ADR-20 过滤） | anon；结果集断言 non_member 看不到他项目候选 note、`changed_projects` 不含无权项目、前 limit 条全不可见时仍返回其后的可见记录 | — |
| POST `/api/projects/{project_id}/formula-settings/pending/resolve` | auditor, manager, partner, admin | anon, non_member, ro, qc, eqcr | `formula_sync_item`、`formula_setting` |
| GET / POST `/api/formula-audit-log/{project_id}/{year}` | GET ro+；POST auditor, manager, partner, admin | anon, non_member（POST 另拒 ro、qc、eqcr） | `audit_log_entries` |
| POST `/api/formula-audit-log/{project_id}/{year}/rollback` | admin；partner / manager 且本项目 review 以上成员 | anon, non_member, ro, auditor, qc, eqcr | `formula_setting`、`audit_log_entries` |
| DELETE `/api/workpapers/{wp_id}/formulas/{formula_id}` | auditor, manager, partner, admin | anon, non_member, ro | `wp_formula` |
| DELETE `/api/formula-templates/{template_id}` | 模板管理者（既有判定）, admin | 其他 | `formula_template` |
| DELETE `/api/projects/{project_id}/formula-settings/{domain}/overrides` | auditor, manager, partner, admin | anon, non_member, ro | `formula_setting` |
| POST `/api/workpapers/draft-refresh` | 既有判定（合伙人 + 项目 edit；manager 等按现读逐身份写入） | 其他 | 业务表、`draft_refresh_audit` |
| GET `/api/projects/{project_id}/qc/vr-heatmap` | ro+ 成员, admin（新增项目只读校验） | anon 401, non_member 403 | — |
| GET `/api/projects/{project_id}/workflow/consistency-check`、POST `.../workflow/export-package`、GET `/api/projects/{project_id}/sign-readiness` | 既有判定（实施时现读，逐身份写入） | 既有 | 导出包拒绝时 `gate_decisions` 以外的表 |

validator 改动的写入端点权限不变，由 `test_formula_definition_validator.py` 覆盖合同，不进配方表；看板中调用 `_aggregate_vr_summary` 的端点权限不变，由响应快照覆盖（需求 16.5）。

### 10.4 磁盘变异（变异 → 期望打红 → 逐字节恢复；单独一条命令跑，跑完 sha256 核对；备份放 `_tmp_formula_hub/mutations/`）

| # | 变异 | 期望打红 |
|---|---|---|
| 1 | 删冻结闸门判定 | `test_runtime_freeze_gate` |
| 2 | 项目锁移回计划段之前 | `test_runtime_freeze_gate::test_lock_after_freeze` |
| 3 | typed_eval 环检测改「按原序追加」 | `test_runtime_typed_eval` 自引用 |
| 4 | 歧义判定改取第一个 | `test_runtime_typed_eval` 歧义 |
| 5 | `evaluate_wp_formula_expression` 忽略 `wp_values` | `test_runtime_four_way_parity` |
| 6 | `require_existing_sheet` 默认改回新建表 | `test_runtime_replay_29_pg` 错 sheet 行 |
| 7 | report adapter 枚举改回短码 | `test_runtime_adapter_pg_shapes` |
| 8 | 节点身份改回从 `sheet_name/target_cell` 推导（忽略 needs_review） | `test_runtime_typed_eval` needs_review |
| 9 | 读取函数去掉年度闸门 | `test_wp_executor_project_year_contract` |
| 10 | `read_wp_ref_strict` 列名缺键返回 0 | `test_runtime_four_way_parity` 列名两参行 |
| 11 | `WPExecutor` 单元格分支恢复 `extract_custom_cells` 循环 | `test_wp_cell_reader_single_source` |
| 12 | 中央 execute 改回 `unadjusted_amount` / `error=None` | `test_central_execute_contract` |
| 13 | `COLUMN_ALIASES["未审数"]` 改回 `期末余额` | `test_central_execute_contract` 未审 = 0 与 XR-07 |
| 14 | 预检改回 `expression_functions` | `test_precheck_classification` |
| 15 | 预检对内置纯函数也查矩阵 | `test_precheck_classification` 正例 |
| 16 | L1 除零恢复返回 0 | `test_l1_failure_semantics` |
| 17 | `select_leaves` 返回全部行 | `test_tb_leaf_codes` + BS-008 + false-fresh 守卫 |
| 18 | 告警只记日志不 `emit` | `test_tb_leaf_warning_propagation` |
| 19 | `compute_row` 恢复兜底替换 | `test_report_three_path_parity` 合法 0 |
| 20 | `stale_clause` 去 `calc_version` 条件 | `test_legacy_rows_read_as_stale` |
| 21 | 标过期改为「该准则全部项目」 | `test_report_config_writer_marks_stale` override / pinned |
| 22 | `mark_changed` 不扩闭包 | `test_report_config_writer_marks_stale` 合计行 |
| 23 | `build_row_cache` 收入过期或失败行 | `test_report_three_path_parity`「A 失败 ⇒ T 失败」 |
| 24 | 归属行升级工具去掉旧值精确比对 | `test_report_seed_upgrade_tool` 旧值不符 |
| 25 | report 范围恢复交 Runtime | `test_draft_refresh_truthful` |
| 26 | 路由恢复 `no_effect→success` | `test_draft_refresh_router_status` |
| 27 | `generate_all_reports` 忽略 `publish_events` | `test_draft_refresh_truthful` 回滚 / 仅重算无事件 |
| 28 | 附件查询去 `project_id` 条件 | `test_attachment_lineage_isolation_pg` |
| 29 | 迁移孤儿检测改为删除 | `test_attachment_lineage_migration_pg` |
| 30 | `upsert_pending` 改回先查后改 | `test_pending_revision_concurrency_pg` |
| 31 | `resolve_items` 去 revision 比较 | `test_pending_revision` 三步回归 |
| 32 | lineage 恢复 3 参调用 | `test_unified_lineage_signature_guard` |
| 33 | validator 在 `write_project` 处摘除 | `test_formula_definition_validator` |
| 34 | 常量零除数检查摘除 | `test_formula_definition_validator` `1/(2-2)` |
| 35 | 回滚恢复读请求体 `target_formula` | `test_formula_rollback_snapshot` |
| 36 | `_tb_sign` 恒按 v2 口径 | `test_tb_balance_sign_convention` |
| 37 | 门禁逐分支改为「通过」（脚本遍历全部登记分支；exception 类改 `_guarded` 产出通过） | `test_consistency_gate_branches` 对应用例 |
| 38 | `ConsistencyPassedRule` 恢复 `.get` + `except → None` | `test_consistency_gate_enforcement` enforce 组 |
| 39 | `_guarded` 去保存点 | `test_consistency_gate_status` 级联用例（真 PG） |
| 40 | 预算不把 QueryCanceled 映射为 504 | `test_formula_execute_budget` `pg_sleep` 用例 |

P0 覆盖：P0-1 #1~11；P0-2 #12~16；P0-3 #25~27；P0-4 #17~24；P0-5 #28、29；P0-6 #30、31。

### 10.5 实施与发布流程（tasks 通用纪律与发布验收清单的执行方法）

- **工作区**：实施在仓库根 `_tmp_formula_hub/wt`（`git worktree add --detach` 当前 HEAD 后 `git worktree lock --reason`），命令用 cwd 参数、不 `Set-Location` 进去；一次性脚本、日志、截图、变异备份都放 `_tmp_formula_hub/` 下（`_tmp_*` 已被忽略；变异备份用 `.fhbak` 后缀，不用他会话按仓库根 rglob 还原的 `.mutbak`）。worktree 不在开发服 `--reload-dir app` 与前端 dev server 的监视范围内。不建分支、不 stash、不在共享终端设 `GIT_*` 环境变量。
- **WIP 提交**：每批任务完成且该批测试全绿后，在 worktree 内提交一个 WIP 提交（不跳过钩子），并 `git update-ref refs/wip/formula-hub/<批> HEAD` 作恢复点。
- **单个提交**：全部批次与发布验收完成后 `git fetch --prune`；远端分支已前移则在 worktree 内把 WIP 链 squash 后 cherry-pick 到新远端头、解决冲突并在新 tree 上重跑发布清单的验收项；以最终 tree 经 `git commit-tree <tree> -p <远端头>` 生成单个提交，断言其 tree == 验收时的 tree，写到 `refs/wip/formula-hub/final`。**不推送**：推送与共享库迁移同属决策项 X1，且必须先迁移后推送（新代码映射了共享库尚不存在的列，先推送会让同步该分支的工作树读写这些表报错）。
- **前端与后端运行**：vitest 需要依赖时在 worktree 前端目录建指向主树 `node_modules` 的联接，跑完立即 `cmd /c rmdir` 拆除；后端测试必要时把 `BACKEND_ROOT` 指回主树（storage 未入库）。真 PG 用例、回归、预览与基准按 ADR-25 第 2 点的子进程环境运行，结果取 junit。
- **性能**：基线 worktree `_tmp_formula_hub/wt_base`（检出基线提交）与实施 worktree 连同一个快照库，各预热 1 轮，A-B-B-A 交替各 10 次取中位数。
- **收尾**：删除 `refs/wip/formula-hub/` 下除 `final` 以外的引用；unlock + 删除两个 worktree + `git worktree prune`；`snapshot_db.py drop` 并核对 `pg_database` 无 `fh_snap_%`；Redis 15 号库 `FLUSHDB`；最后删除 `_tmp_formula_hub/`，断言 `Test-Path _tmp_formula_hub` 为 False。

## 11. 第 3 轮复核意见回应（`p2-design-review.round3.json` / `p2-design-review-doc.round3.md`，HIGH 4 / MEDIUM 13 / NIT 16）

| # | 级别 | 处置 |
|---|---|---|
| 1 | HIGH | 已修（父会话裁定）：§8.2 契约表 —— 签名保持 ACNR 现行的位置调用兼容（未按复核改成仅关键字），扩展 `blocked` 与 `matches / candidates`；可接受键 = `_catalog_sheet_keys`（ACNR 落地 `exact_identity` 时改写）∪ `normalize_sheet_key`；歧义与非数值 blocked、缺失 missing、异常上抛；两参单元格分支归本 spec、三参 A1 归 ACNR；三参预载挂点改为 `formula_preloader.preload`，报表侧为 `evaluate_formula_result`（报表不经 `preload`，F54）；先落地方提交契约测试；「需 ACNR 同步」清单。需求 1.9；任务 23 |
| 2 | HIGH | 已修：术语「项目年度」、需求 1.6（`audit_period_end` 空 + `audit_year=2025` 夹具、未设置 ⇒ blocked、有试算表活项目年度非空守卫）、§8.2 年度行、ADR-14 消费方年度、F53；`PROJECT_AUDIT_YEAR_SQL` 在 SQLite 报错 ⇒ 年度分支只在真 PG 测；与年度棘轮 spec 的关系见 §8.3 |
| 3 | HIGH | 移为后续 spec：审计哈希链加固整体移到 S10，复核修法（`append_fork_ack`、worker 每链保存点与隔离队列、上线前「未确认分叉 = 0」与 health 计数、确认工具先于 fail-closed）列为 S10 设计输入；需求 11.3 钉住本 spec 不改写入语义；原任务 28、29 删除，编号重排 |
| 4 | HIGH | 已修（父会话裁定）：ADR-14 —— `ConsistencyPassedRule` 属性访问并去掉 fail-open；五态（not_applicable 只显示不阻断、error 独立）；全部消费方读 `gate_decision`；设置项默认 observe（= HEAD 实际效果，无项目被新卡住）；经门禁引擎的端点级测试（需求 16.4）；收尾只读影响清单（需求 16.6、X4）。与复核建议的差异：不在实施中等用户确认后启用阻断，改为默认不阻断 + 决策项；签字人逐项确认留痕归 S2 |
| 5 | MEDIUM | 已修：ADR-04 `mark_changed` 经 `report_closure` 扩闭包、全部年度、同事务、挂三个出口；SQL 迁移静态守卫；需求 5.1；变异 #21、#22 |
| 6 | MEDIUM | 已修：ADR-05 `build_row_cache` 与「引用行未就绪」；需求 5.2；变异 #23 |
| 7 | MEDIUM | 已修：ADR-24 医疗器械复制正例（断言引用父子并存科目）；需求 4.4 改为 `load_tb_audited` = 叶子和 + 合成夹具，前缀差只报告 |
| 8 | MEDIUM | 已修：需求 3.2 七行状态表（沿用 `partial_success`，`idempotent_hit` 返回首次 outcome）；ADR-08 前后端状态同步 + 解析器逐状态单测、before == after 不下发、幂等在取锁后任何执行前。替代：`affected_count = applied + recomputed`（不含 draft 标记），理由：p1-10 P0-3 验收要求无可执行写入方的范围 `affected_count = 0`，含 draft 标记会让 marker-only 为 343 |
| 9 | MEDIUM | 已修：ADR-05 `publish_events`、返回 dict 不变；ADR-08 两个事件提交后发；需求 3.5 两调用方回归；变异 #27。替代：摘要经 `summary_out` 参数传出而不放进 `results["generate_summary"]`，理由：`routers/reports.py` 把返回 dict 的全部键当报表类型返回前端并写进事件，多一个键即改接口（现读确认） |
| 10 | MEDIUM | 已修：ADR-06 第 3、4、7 点（四种写法、`wp_ref_strict`、外部取值不建边）；需求 1.3、1.5（严格轨定义、四写法夹具、允许差异登记）；变异 #10 |
| 11 | MEDIUM | 已修：ADR-14 第 2~4 点（保存点包装、`_helpers` 不吞异常、`ConsistencyResult` 统一、装饰器字面量 ∪ 工厂字面量双射）；需求 16.2 真 PG 级联用例；变异 #39 |
| 12 | MEDIUM | 已修：ADR-15（只按负债符号、五类、类别内叶子、资不抵债）；需求 16.1（4 口径定义；医疗器械、华氏断言生产差额 = 独立 SQL，超容差时 details 可见） |
| 13 | MEDIUM | 移为后续 spec：S10 设计输入①（`audit_chain_head`）与⑤（锁顺序） |
| 14 | MEDIUM | 已修：ADR-19（`statement_timeout = FORMULA_EXECUTE_TIMEOUT × 1000 − 500`、`wait_for` 兜底、QueryCanceled ⇒ 504、保存点回滚失败作废会话）；需求 12.3 `pg_sleep` 用例；变异 #40。另：整批时限用新设置 `FORMULA_BATCH_TIMEOUT`（60 秒），理由：整批只给 10 秒会让现有表间审核批量超时 |
| 15 | MEDIUM | 已修，并改了迁移本身：V{n} 改为可空列 + 回填，不再因孤儿失败（孤儿保持空值、对任何项目不可见，修复工具列出），可空也是 X1「先迁移后推送」时旧代码继续可写的前提；任一迁移失败按 F56 记录并继续启动、health degraded（§4）；代码先于迁移运行时附件路径 503（ADR-13）；需求 7.1 + `test_attachment_lineage_column_missing.py`；迁移在快照库上由 MigrationRunner 执行（ADR-25），不对共享库跑 |
| 16 | MEDIUM | 已修：需求 17.2 九种身份（加 manager、eqcr）与按路由模块全集对账 + `_UNCHANGED_ROUTES` 反向断言；§10.3 |
| 17 | MEDIUM | 已修：需求 1.9 守卫限定五个 WP 取值实现（变异 #11）；ADR-22 `READER_ENTRIES` 写死入口、`effective_slots` 不计；需求 17.3 识别规则 + 违规样本自检 |
| 18 | NIT | 已修：ADR-04 挂三个出口、不新增 source、`calc_error` 与 `blank_reason` 分工；F10 勘误 |
| 19 | NIT | 已修：ADR-10、ADR-11、§5 —— 模型可空 + 服务层 428；`restore_global(expected_versions=None)` 只供内部；DELETE 重复 Query 参数按序配对 |
| 20 | NIT | 已修：ADR-21 只改 `TB_SUM`；需求 3.7 两条 `TB_AUX` 不变；F7 |
| 21 | NIT | 移为后续 spec：哈希往返部分写入 S10 设计输入⑥；本 spec 的公式审计载荷只用 `year` 一种写法（ADR-12、需求 11.1） |
| 22 | NIT | 已修：ADR-07、需求 1.1 改为「计划含任何 Runtime mutation」，夹具含非 UUID `formula_id` |
| 23 | NIT | 已修：需求 1.2、1.10、2.1、4.2、9.1 改为金标准现算、现值只作记录；需求 3.1 用 `gold_report_evaluator`；任务 20 依赖任务 17 |
| 24 | NIT | 已修：tasks 依赖补齐（新编号 2→20、20→21、13→15、15→19、17→20）；原任务 29 删除，提交方式统一为 §10.5 单个提交 |
| 25 | NIT | 已修：ADR-20 规则①~③下推 SQL、④按游标补取；需求 7.4「不出空页」用例 |
| 26 | NIT | 已修：需求 2.4、7.1、11、12.3 只留可观察行为；迁移步骤只在 ADR-13、§7 引用；预检分类只在 ADR-19 |
| 27 | NIT | 已修：ADR-25 第 3 点（trylast 钩子、`UsageError`）；第 2 点子进程同传 `DATABASE_URL`（快照库）、`GT_REQUIRE_PG=1` 与隔离的 `REDIS_URL`，结果取 junit |
| 28 | NIT | 已修：ADR-16、需求 9.1 |
| 29 | NIT | 已修（已现读确认）：`write_cell_to_parsed_data` 单调扩展 `max_row/max_col` 供 `hasData`（F57）⇒ 数据范围；ADR-06 第 6 点不作边界，需求 1.8 越界照常写入 |
| 30 | NIT | 已修：ADR-06 第 1 点新增差异维度 `typed_eval_strictness`（归 S1），守卫同步 |
| 31 | NIT | 替代方案：`execute-formulas-batch` 上限定 1000 并在实施时现算最大批量写入任务说明（ADR-19），不改前端分批；理由：整批一个时限与「不返回部分结果」的语义在前端分批后会被拆散 |
| 32 | NIT | 已修：§8.3（不改鉴权常量、后合入方下调、不写对方 `_FIXED_ENDPOINTS`；另登记年度棘轮） |
| 33 | NIT | 已修：§10.5 worktree 实施、每批 WIP 提交 + `refs/wip/formula-hub/<批>`，最后合成单个提交写到 `refs/wip/formula-hub/final`（推送随 X1） |

本轮另有三处作者发起的变更（不对应复核条目，请一并复核）：①真 PG 基座改为一次性快照库（ADR-25）：候选代码映射了共享库没有的列，第 3 轮「在共享库事务内执行迁移 SQL」的做法会让 ALTER 的排他锁挡住开发服；快照不含两张序时账表的数据（二者约 47 GB，其余约 1 GB，F62）。②推送并入 X1（§10.5、requirements §4.2）：先推送会让同步该分支的并发工作树在迁移前报列不存在。③V{n} 改可空列（ADR-13）：见第 15 条。

## 12. 历史轮次

- 第 2 轮（HIGH 8 / MEDIUM 10 / NIT 4，归档 `p2-design-review*.round2.*`）：全部采纳，落点为 P0-1 验收并入（需求 1.8、1.10）、原子修订号、刷新三段式与结果聚合、存量归属行升级工具、`GT_REQUIRE_PG`、迁移不删行、预检分类与内置参数表、常量零除数、执行预算、告警传播、只标真正变化、金标准独立性、门禁分支清单、配方表绝对路由、发布清单不编号、§8.0 边界裁定、可见性改用 `Viewer.load`。其中审计链 v2 哈希、唯一链尾与分叉确认在第 3 轮整体移交 S10。
- 第 1 轮（HIGH 6 / MEDIUM 15 / NIT 14）：原文被第 2 轮覆盖、不可恢复；处置已体现在节点命名空间、年度契约、「未审数」规范列、ROW 缺行规则、分域 validator、冻结判据与位置、正向解冻用例、严格 WP 代入、缺科目 missing、D13、读写两侧新鲜度、推送不变式、发布可见性、预设归一、wired 派生、门禁空项目对账与性能判据。

## 13. 交接与承接勘误（发布验收清单「交接」，2026-10-30 阶段 E，只追加）

### 13.1 S1~S10 交接产物（需求 17.5；现扫主工作树 `.kiro/specs/<名>/requirements.md`）

| # | 目录 | requirements.md | 负责范围 / 依赖 / 触发条件 | 处置 |
|---|---|---|---|---|
| S1 | `formula-grammar-resolver-unification` | 已存在（未跟踪，46 行） | §1 / §2 / §3 齐 | 本阶段只核对，未改 |
| S2 | `check-contract-and-note-executor` | 已存在（已跟踪） | 齐 | 并发会话实施中，不碰 |
| S3 | `formula-writer-ownership-and-stale` | 已存在（未跟踪，34 行） | 齐 | 只核对 |
| S4 | `formula-settings-durable-outbox` | 已存在（未跟踪，35 行） | 齐 | 只核对 |
| S5 | `formula-provenance-envelope` | 已存在（未跟踪，33 行） | 齐 | 只核对 |
| S6 | `formula-template-dual-project-pilot` | 已存在（未跟踪，33 行） | 齐 | 只核对 |
| S7 | `consol-note-formula-scope-and-roles` | 已存在（已跟踪） | 齐 | 不动 |
| S8 | `formula-e2e-ci-gate` | 已存在（未跟踪，32 行） | 齐 | 只核对 |
| S9 | `income-statement-lower-section-formulas` | 已存在（未跟踪，35 行） | 齐 | 只核对 |
| S10 | `audit-log-chain-integrity` | 已存在（已跟踪） | 齐；§1 第 1~8 条即 §8.1 设计输入 ①~⑧ 与相关事实 F18 / F44 / F50 | 不动 |

十个目录都已有 requirements.md，本阶段没有新建。七个未跟踪目录由阶段 F 随 `final` 提交入库。

### 13.2 对三份已归档 spec 的承接勘误（已归档 spec 不回填修改，勘误只登记在这里）

本 spec 的 S5 指 `formula-provenance-envelope`。下面 ① 里的「S5」是 `formula-global-settings-sync` 自己 tasks.md「交付勘误」里的编号，两者无关。

**① `formula-global-settings-sync`（`_archive/55-batch-2026-10-21/formula-global-settings-sync/`，记 36/36）**

| 项 | 原 spec 的交付 | 现状事实 | 承接 |
|---|---|---|---|
| P0-6 待确认陈旧决策 | 待确认事项按 `upstream_version` 比较 | `apply_to_projects` 写 `upstream_version=None`；`upsert_pending` 原地覆盖同一条；`resolve_items` 只在 expected 非空时比较；前端原样回传 null ⇒ 来源二次推送后，旧弹窗的「采用」照样被接受（评估 report §6.2 P0-6，SQLite + 生产服务函数复现） | 本 spec ADR-FHIC-11 收口：V219 `formula_sync_item.revision` 原子递增、三段决策键、缺修订号 428、不等 409。阶段 D 浏览器实测第 ③ 项通过（409 `FORMULA_SYNC_ITEM_STALE` 后只清被更新那条的选择） |
| 交付勘误 S5 底稿旧保存路径 | 登记「`wp_formula_service.save`（经 `wp_formula.py` / `wp_user_formulas`）接入同步内核暂缓」 | 至今未接：Runtime / Tier A 只读 `wp_formula`（评估 P1-5） | 本 spec §8.0 移出，归 S1（`formula-grammar-resolver-unification` §1「wp 全轨读 effective + S5」） |
| wired 常量 | 能力状态以常量标 `wired` | tb_detail 生产 import 只有 1 个路由却标 wired（评估 P1-5 / P3-1） | 本 spec ADR-FHIC-22 收口：`formula_settings/consumers.py::READER_ENTRIES` 由读取入口派生；前端 `specAReady` 删除（ADR-FHIC-10） |
| 8.2 登录态 UI 走查 | 首版误标 `[x]*`，后改 `[ ]*` | 仍未做 | 不在本 spec 范围；与 S6 的双项目登录态 UAT 同类，S6 启动时可一并覆盖（建议，未改 S6 文件） |

**② `formula-governance-coverage-closure`（`_archive/67-formula-governance-coverage-closure/`，36/36）**

| 项 | 原 spec 的登记 | 现状事实 | 承接 |
|---|---|---|---|
| L1 `_handle_report` 不看期间 | 范围外第 2 条：底稿求值器前置代入规避，内核修正另评估 | 仍成立：`REPORT('BS-002','上期')` 取的是本期（S1 design §1 第 9 行现读） | 归 S1，实现与变异写在 S1 design §1 / §10 |
| L1 `_handle_prev` 不看列名 | 范围外第 3 条 | 本 spec 整合树已按列取，未注册列报错 ⇒ 这一项已修 | S1 只保留回归守卫，不再实现 |
| 预填非严格 | 范围外 | 本 spec ADR-FHIC-06（严格外部取值、None 不代入）覆盖写入路径 | 剩余口径差异由 S1 `typed_eval_strictness` 收敛 |

**③ `formula-execution-path-convergence`（`_archive/60-formula-execution-path-convergence/`，13/14，余 17 `[ ]*` start-dev 实测）**

原设计「决策」节把三条执行路径都记为「✅ 已走 L1」：路径 A 报表生成（regex 预替换 → L1）、路径 B 底稿预填充（preload → L1）、路径 C 公式管理页（`from_simple_map` → L1），并以「路径一致性守卫」保证三条路径对同一公式给出同一结果。勘误：走同一个 L1 内核，不等于结果一致。

| 路径 | 本 spec 现读的偏差 | 承接 |
|---|---|---|
| A 报表生成 | 报表内又分三路（`_generate_report` / `regenerate_affected` / `recalculate_stale_rows`），各自处理失败、依赖缓存与新鲜度；L1 失败返回 0 且 ok；TB 前缀聚合父子双计（评估 P0-4 ②） | ADR-FHIC-01（`FormulaEvalError`）+ ADR-FHIC-03（叶子口径）+ ADR-FHIC-04 / 05（`report_row_compute` 统一逐行计算与缓存规则、`calc_version`） |
| B 底稿预填充 | 预载层本身保留；WP 单元格读取与三参取值口径不一 | ADR-FHIC-06 + §8.2 WP 读取契约 |
| C 公式管理页 | 只取 `unadjusted_amount` 经 `from_simple_map` 冒充审定 / 期末，返回体 `error` 写死 None（评估 P0-2） | ADR-FHIC-18（「未审数」成为规范列，审定 / 未审不再互相冒充）+ ADR-FHIC-19（中央执行合同 + 执行预算，实现在 `formula_central_execute`） |
| 一致性守卫 | 只比较三路 L1 结果值，看不到失败语义与口径（三路都返回 0 时判一致） | 本 spec 用逐值金标准与失败用例替代；报表按依赖拓扑序求值、`typed_eval_strictness` 差异、合并口径 `BasisResolver` 父子并存仍按前缀全加（阶段 B 移交）归 S1 |
