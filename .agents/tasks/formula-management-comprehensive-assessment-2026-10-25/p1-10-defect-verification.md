# 阶段一 · P1-10 缺陷逐项复核（P0-1~P0-6、P1-1~P1-9 与附加缺陷）

> 2026-10-25 · HEAD `072cb8459`（与 p1-00 基线相同；公式内核路径在基线..HEAD、HEAD..工作树两段 diff 中均无改动）。
> 方法：每项都在当前 HEAD 重新复现，用权威表（`trial_balance` / `working_paper.parsed_data` / `report_config` / `financial_report`）或自写的独立求值器算金标准，不抄旧报告数字。PG 只做 `SELECT`；需要调用生产函数的探针一律在不提交的事务里跑并 `rollback`（P0-5 的同 ref 双项目场景在回滚事务内插入两条【探针】附件，回滚后复核残留 0 行）；P0-6 / P1-8 的写入链路用 `tests/formula_settings/_env.make_db()`（SQLite 内存库）跑生产服务函数。探针放 `C:\gt_wt\_probes\`，已删除（目录里剩下的 `cm_*` 是并发会话的文件，未动）。
> 本文件是本步唯一写入。

## 0. 结论总表

| ID | 结论 | 级别（原→复核） | 根因（文件:符号） | 一句话现算证据 |
|---|---|---|---|---|
| P0-1 Runtime 上下文断裂 | **确认，证据需勘误** | P0→P0 | `formula_management/engine.py::execute_batch`（只填 `row_cache`）、`::_topological_sort_formulas`（环按原序追加）、`formula_runtime/coordinator.py::_build_batch_definitions`（`refs=[]` 时无引用目标） | 18 条 WP 引用 runtime 18/18 错（13 格 1000→0、5 格 1001→1）；严格轨 5/18 对、13/18 自引用未报环。**这 29 条全是 Playwright 夹具，所在项目已软删** |
| P0-2 中央 execute fail-open | **确认** | P0→P0 | `formula_engine.py::FormulaEngine.execute`、`::FormulaContext.from_simple_map`、`::_safe_eval`（ZeroDivision→0）、`routers/formula.py::execute_formula`（预检只看 `formula_type`） | 华氏 1001：未审 0 / AJE 100 / 审定 100，`TB('1001','审定数')` 返 0、`error=null`；`EVIL()`、`1/0`、`ROW('MISSING')`、未注册列名均 0 且 `error=null` |
| P0-3 Draft Refresh 假刷新 | **确认** | P0→P0 | `formula_management/draft_refresh_orchestrator.py::_dispatch`（四域都走 Runtime）、`::generate` 无 mutation 时走 `DraftRefreshService.refresh_with_presets`（只写 marker / 审计 / 快照 / prefill_stale） | 和平药房：report 0 mutation、343 条预设只打 draft 标记；note 0/0；adjudication 0/0；workpaper:D 0 mutation、78 条标记。业务表一行不动 |
| P0-4 报表 false-fresh | **确认，根因改写** | P0→P0 | ①存量未随引擎 / 定义变更失效（无计算版本）②`report_engine.py::ReportFormulaParser._resolve_tb` 与 `amount_resolver.py::TrialBalanceResolver.resolve_tb` 前缀聚合父子双计 ③`report_config` 种子 IS-074/075 定义错 | 410 行重算：50 漂移、49 `is_stale=false`、最大差 3,928,889,818.20（同旧报告）。**50 行没有一行由「三路语义差异」或「试算表后改」造成**：47 行存量错（现算=金标准）、3 行现算错（存量=金标准） |
| P0-5 lineage 附件跨项目 | **确认，范围比原描述更大** | P0→P0 | `unified_lineage_service.py::_query_attachments`（SQL 无 `project_id`、`LIKE` 未转义、无 `is_deleted`） | 回滚事务内：以 A 项目身份查 `wp_cell D2!B5` 拿到 B 项目【探针】附件；`object_id='_'`（或 `%`）不需同 ref 即可列出全平台附件 |
| P0-6 project-origin 陈旧决策 | **确认（动态复现）** | P0→P0 | `formula_settings/apply_ops.py::apply_to_projects`（`upsert_pending(..., upstream_version=None)`）、`pending.py::upsert_pending`（原地覆盖同一条）、`project_ops.py::resolve_items`（expected 为空不比较） | 用户审阅的是 `ROW('BS-009')`，来源二次推送后旧弹窗「采用」被接受，目标项目写成 `TB('9999','期末余额')*100` |
| P1-1 UnifiedLineage 少参吞空 | **确认 + 扩展** | P1→P1 | `unified_lineage_service.py::_query_wp_upstream/_downstream`（3 参调 4 参函数）；`report_trace_service.py::trace_section` 查不存在的 `note_wp_mapping` | 和平药房 `D2` 真实上游 7 条，wrapper 0 条；report_row / note_cell 查询使 PG 事务中止，后续附件、版本链被吞成空 |
| P1-2 timeline 3/5 源漂移 | **确认 + 扩展** | P1→P1 | `formula_timeline_service.py::_audit_log_events/_publish_events/_template_events` | 医疗器械有 1 条真实 `formula.changed`（2026-10-18），时间轴 total=0；另 `_publish_events` 从错误模块 import `Project` 且查不存在的 `accounting_standard` |
| P1-3 审计哈希链无锁 | **确认，细节改述** | P1→P1 | `audit_log_helper.py::append_audit_log` / `::_get_prev_hash`；`routers/audit_logs.py::verify_chain` | AST 现算 41 调用 / 25 文件；无 advisory lock；verify 接受任意首条 prev_hash |
| P1-4 语法 / 元数 / PREV / 精度多轨 | **确认 + 新增 4 条** | P1→P1 | `formula_engine.py`（无 arity 校验、`ROUND` 用 HALF_EVEN）、前端 `formulaSyntaxParser.ts`（含 `PRIOR`、`%`）、`note_formula_generator.py`/`cell_formula_evaluator.py`（float） | `IF(1>0,1)`=0 ok；`ROUND(1.005,2)`=1.00；`TB('1001','期末余额','x','y')` ok；TB 取数三套口径（前缀 / 精确 / 精确 limit 1） |
| P1-5 wp effective / tb_detail 消费不全 | **确认** | P1→P1 | `formula_settings/wp_effective.py`（docstring 自认限制）、`coordinator.py::_load_formulas`、`wp_formula_service.py`（不接同步内核）、`routers/formula_settings.py::WIRED_DOMAINS` | `formula_settings.tb_detail` 生产 import 只有 1 个 router；`wp_effective` 只被初始化 / 预填 / 模板初始化 / PREV3 定位消费 |
| P1-6 附注多写方 / stale 不收敛 | **确认，数字修正** | P1→P1 | `disclosure_engine.py::refill_sections`（值不变不进 `sections_recomputed`）、`note_stale_service.py` | stale 227 里 187 属已软删项目，活项目 stale 40（华氏）；`stale_source` 全表 1090 行全 NULL |
| P1-7 settings 无 durable outbox | **确认** | P1→P1 | `formula_settings/propagation.py::publish_events`（commit 后发、异常只 warning） | 包内无 outbox / retry；降级只进日志 |
| P1-8 validator / 预算 / 回滚 | **确认（动态复现）** | P1→P1 | `domain_stores.py::validate_definition`（report/tb_detail/cross_check 不校验）、`rollback.py::rollback_from_log`、`routers/wp_formula.py::delete_formula`、`core/config.py::FORMULA_EXECUTE_TIMEOUT` | 报表项目层存 `EVIL(((`、`TB('1001'`、`PRIOR(...)` 全部接受；全局发布 `EVIL(((` 接受 |
| P1-9 最终值不绑计算版本 | **确认** | P1→P1 | `financial_report`（无 version / run 列）、`disclosure_notes.stale_source`（从未写入）、`wp_formula.last_computed_at` | `wp_formula` 29/29 `refs=[]`、29/29 `last_computed_at IS NULL` |
| 依赖解析漏双引号 | **确认** | P2→P2 | `formula_settings/dependencies.py::_TB` 等 9 个正则只认单引号 | `TB("1001","期末余额")` L1 求值 123，`upstream_refs` 返 `[]`、`references(account='1001')` 返 False |
| 自定义函数自引用 | **确认** | P1→P2（仅 admin、进程内、不持久） | `formula_engine.py::FormulaEngine.register_custom_function::_custom_handler`（丢弃内层 errors） | `SELF_AUDIT()` 递归到上限，最终 `ok=True value=0`；新实例 list 为空、注销 False |
| preset 4 挂载仅 1 有保存 | **确认** | P2→P2 | `GtFormulaPresetDialog.vue::onEditorSave`（`canEdit` 默认 true、无条件 success 提示） | `FormulaTab` 有 `@edit-formula`；`ReportConfigTab` / `NoteTemplateTab` / `WpTemplateDetail` 没有 |
| 应用范围 3/7 域接线 | **确认** | P2→P2 | 前端 `askApplyScope` 只在 report / tb_detail / cross_check 保存链调用 | 生产调用 3 处（`FormulaManagerDialog` 报表、`useTbDetailFormulas`、`useCrossCheckRules`） |
| 冲突决策 key 缺 domain | **确认（结构性，触发需同名 slot）** | P2→P2 | `formula_settings/engine.py::PlanItem.key`、`apply_ops.py` L74/L124、`template_sync.py::_apply`（多域共用 `outcomes` dict） | key = `{project}\|{slot}`；DB 唯一身份是 project+domain+slot |

新增发现（旧报告未列）：N1 批量执行在同一 `AsyncSession` 上 `asyncio.gather` 并发（P1）、N2 IS-074/075 种子公式会计错误（P1）、N3 预设库 17 条用未注册的 `TB_SUM`（P2）、N4 `regenerate_affected` 科目命中只认精确码（P1）、N5 全量生成的「结果为 0 用首个科目余额兜底」（P1）、N6 软删项目数据污染统计（P3）。见 §4。

## 1. P0 逐项

### P0-1 Formula Runtime 上下文断裂 —— 确认（P0），证据勘误

**现场事实（勘误）**：live `wp_formula` 共 29 行，全部属于项目 `37814426…`「辽宁卫生服务有限公司_2025」，**该项目 `is_deleted=true`**；29 张底稿都是 Playwright 建的自定义底稿（`PWJNV*` / `PWX*`）。旧报告的「18 个真实 WP 引用」实为测试夹具，其中 **13 条是自引用**（目标格引用自己）。活项目 `wp_formula` 为 0 行。另外 `RefreshScopeDiscovery` 只发现 `workpaper:A~N`，这些 P 开头的底稿从界面勾选不到。所以**现网暴露为 0**，但缺陷是确定性的：任何活项目在 A~N 底稿里存一条带 `WP/TB/NOTE/REPORT` 的用户公式，一键刷新就会写错值。维持 P0。

**复现**：`FormulaRuntimeCoordinator(s).generate_mutation_plan(PID, 2025, ['workpaper'])` 产 29 个 mutation、0 个 scope_failure；对每条用 `evaluate_wp_formula_expression`（严格轨）与独立金标准对拍。金标准：被引格的值 = 被引底稿 `parsed_data.html_data[sheet].cells[cell]` 的当前值，且被引格本身若有字面量公式则按公式值；自引用 = 环，正确语义是报错不写。

| 类别 | 条数 | 金标准 | 严格轨 | Runtime（before→after） | 判定 |
|---|---:|---|---|---|---|
| 自引用 `WP('X','B5')` → X!B5 | 13 | 环，blocked，不写 | 1000，无错误 | 1000→**0**（其中 2 条 before=None） | 严格轨错（没报环但值不变）；Runtime 错且破坏数据 |
| 跨底稿 `WP('Y','B5')+1` | 5 | Y!B5 定义 2000、存值 2000 ⇒ **2001** | 2001 | 1001→**1** | 严格轨对；Runtime 错 |
| 字面量 2000 / 8888 | 11 | 原值 | 对 | 对 | 两边都对 |

逐条（18 条引用）：自引用 PWJNVSU20、PWXD9ZXL、PWXDAA0E、PWXDHA9P、PWXDHLUF、PWXDOVDA、PWXEXFZ6、PWXF7SII、PWXKO3FH、PWXKORNQ、PWXKPJHP、PWXKQI4V0、PWXLISD30（期望 blocked / 严格 1000 / Runtime 0）；跨底稿 PWJNVXHT0←PWJNVWP50、PWXKP9RF←PWXKP9OJ、PWXKPKD1←PWXKPJHL、PWXKQINB0←PWXKQI4R0、PWXLIU170←PWXLITMI1（期望 2001 / 严格 2001 / Runtime 1）。

**根因**：
1. `formula_management/engine.py::execute_batch` 把预载值放进 `kernel_ctx.row_cache[addr_id]`，而 `WP()` 的 handler 读 `ctx.wp_data`（空）。实测：`execute("WP('PWJNVWP50','B5')+1", FormulaContext(row_cache={"<wp_id>/PWJNVWP50/B5": 2000}))` = 1，trace `WP(...) = 0`，`ok=True`。
2. `coordinator.py::_build_batch_definitions` 只从 `wp_formula.refs` 取引用；29/29 `refs=[]`，表达式里的引用从未被解析成 addr_id，也就没有预载、没有拓扑序。
3. `_topological_sort_formulas` 遇环把节点按原序追加；合成 A↔B（A=`ROW('B')+1`、B=`ROW('A')+1`，预载 A=20、B=21）得 intents A=22、B=23，`errors=[]`。
4. 严格轨 `WPExecutor.execute` 只按 `project_id + wp_code` 取底稿，**不看年度**；对自引用无环检测。
5. Runtime workpaper adapter 按 `wp_formula.sheet_name` 读 `html_data[sheet]`；有 2 行 sheet_name=「Playwright自定义底稿」而 html_data 键是 wp_code，before_value 读成 None（写入会落到不存在的 sheet）。
6. adapter 形状与真库不符（复读确认仍在）：report adapter `VALID_REPORT_TYPES={BS,IS,CFS,EQ,CFSS,IMP}`，PG 枚举是 `balance_sheet…impairment_provision`；活项目附注顶层 `rows` 为数组的 48 张里首行有 `values` 30 张、有 `cells/key/id` 0 张。

**修复验收（机器可核）**：
- A1 未修复前：`execute_refresh` 收到任何 `source_formula_id` 来自 `wp_formula` 的 mutation 时服务端拒绝（端点测试断言 409/422 + 业务表 before==after），变异「去掉闸门」必红。
- A2 Runtime 求值改走统一 typed resolver：上表 29 条 + 合成用例全部满足——跨底稿 5 条 after=2001；13 条自引用与 A↔B 环 `state=blocked`、不产 mutation；字面量 11 条不变。测试调生产 `generate_mutation_plan`，不 mock 求值。
- A3 Runtime、严格轨、`/workpapers/{id}/formulas` 预览、实际 apply 写入四方对同一夹具逐值相等（参数化表驱动）。
- A4 TB / NOTE / REPORT 各一条引用：期望值由测试内独立 SQL（`trial_balance.audited_amount` 叶子求和、`disclosure_notes` 单元格、`financial_report.current_period_amount`）算出再比对。
- A5 adapter 契约测试用真 PG 形状：report 枚举 6 值 + 附注 `rows[].values` 结构零拒读。
- A6 `WPExecutor.execute` 带年度过滤：同 wp_code 跨年度两份底稿取到本年那份。

### P0-2 中央 `/api/formula/execute` fail-open —— 确认（P0）

**金标准**：华氏（`005a6f2d…`，2025）`trial_balance` 1001 一行：未审 0.00、AJE 100.00、RJE 0、审定 100.00；`TrialBalanceResolver.resolve_tb` 审定数 / 期末余额 = 100、未审数 = 0。另一 UAT 合并子公司 1001：未审 NULL、审定 1,200,000。

| 表达式 | 期望 | `FormulaEngine.execute` 实际 | L1 `execute` 自身 |
|---|---|---|---|
| `TB('1001','审定数')`（华氏） | 100，ok | **0**，error=null | — |
| `TB('1001','期末余额')`（华氏） | 100 | **0** | — |
| `TB('1001','未审数')` | 0 | 0 | — |
| `TB('1001','审定数')`（UAT 子公司） | 1,200,000 | **0** | — |
| `EVIL()` | 非 ok | 0，**error=null** | blocked（错误被 execute 丢弃） |
| `1/0` | 非 ok | 0，error=null | **ok=True value=0** |
| `ROW('MISSING')` | 非 ok | 0，error=null | **ok=True value=0** |
| `TB('1001','乱写列')` | 非 ok | 0，error=null | 有 errors（被丢弃） |
| `TB('9999','审定数')` | 缺数提示 | 0，无 warning | — |

**根因**：`FormulaEngine.execute` 只 SELECT `unadjusted_amount` 建 `tb_map`；`FormulaContext.from_simple_map` 把同一个值同时塞给 `期末余额/审定数/未审数`；返回体写死 `"error": None`，`formula_result.errors / blocked` 不出参；`tb_map` 精确码不做叶子聚合。L1 `_safe_eval` 对 `ZeroDivisionError` 返 0，`ROW()` 缺行返 0 不记错。路由 `require_function_support(data.formula_type, …)` 只校验请求里的 `formula_type` 字段，不校验表达式里的函数，`EVIL()` 能过预检。`/batch-execute` 同链路。同族：`routers/report_config.py::execute_formula` 的 trace 用空 `FormulaContext` 重跑、`error` 恒 None。

**修复验收**：
- 华氏夹具：`/api/formula/execute` 返 100；`TB('1001','未审数')` 返 0；UAT 子公司返 1,200,000（端点测试，真实 resolver）。
- `EVIL()`、`1/0`、`ROW('MISSING')`、未注册列名、缺科目：响应 `ok=false`（或 HTTP 422）且不给可写值；`1/0` 与 `ROW('MISSING')` 在 L1 层也须 `ok=False`（L1 单测）。
- 预检改按表达式函数（`require_expression_support`），`formula_type=TB` + 表达式 `EVIL()` 必 422。
- trace 与 value 同一次求值：`report-config/execute-formula` 对 BS-002 返回的 trace 里每个 `TB(...) = x` 之和 = value。
- 变异：把 `audited_amount` 改回 `unadjusted_amount`、或把 `error` 改回 None，相应测试必红。

### P0-3 Draft Refresh 假刷新 —— 确认（P0）

**复现**：对和平药房（`5942c12e…`，2025）逐 scope 调生产 `DraftRefreshOrchestrator._dispatch`（只读部分：Runtime 计划 + 页面键），再调 `build_preset_draft_units`；未调 `generate()`（会写 marker / 审计 / `prefill_stale`）。基线业务表：`financial_report` 352 行、`disclosure_notes` 166 行、`trial_balance` 53 行、`draft_marker` 0 行、`wp_formula` 0 行。

| scope | 应调的权威生成器 | 实际 | Runtime mutation | 交给 `refresh_with_presets` 的预设单元 | 业务表 before→after 的实际含义 |
|---|---|---|---|---|---|
| report | `ReportEngine.generate_*` | Runtime（只认 `wp_formula`） | 0 | 343（7 页） | `financial_report` 不变；`draft_marker` +343 行 state=draft、审计 1 行、按单元写快照；`trigger_recalc` 把项目内「持有已落库派生值」的底稿全标 `prefill_stale` |
| note | `execute_note_formulas` | Runtime | 0 | 0 | 不变；告警「无公式定义」 |
| adjudication | 审定表回写 | Runtime | 0 | 0（16 页 pending，辽宁活项目） | 不变 |
| workpaper:D | 预设库初稿 | Runtime | 0 | 78（4 页） | 底稿 `parsed_data` 不变；只打 78 个 marker |

`refresh()` 在 precheck 通过时返回 `status="success"`、`affected_count=len(refreshed)`（= marker 数，report scope 为 343）。用户看到的是「成功、343 处」，而业务表一行没变。预设单元里 17 条用了未注册函数 `TB_SUM`（L1 只有 `SUM_TB`），这些「初稿」本身就不可执行（N3）。

**根因**：`draft_refresh_orchestrator.py::_dispatch` 把 report / note / adjudication / workpaper 全部转给 `_dispatch_via_coordinator`；`coordinator._load_formulas` 只查 `WpFormula`、按 `category` 文本推断域，report / note 定义根本不在这张表里。`generate()` 无 mutation 时走 `DraftRefreshService.refresh_with_presets → refresh()`，后者只写 `DraftMarker` / `DraftRefreshAudit` / `DraftRefreshSnapshot` 并调用 `prefill_engine.mark_stale`。

**修复验收**：
- report scope 调 `ReportEngine` 权威路径：【测试】项目上 `financial_report` 逐行 before/after 与独立重算一致；无可执行 writer 的 scope 返回 `status` ∉ {success} 且 `affected_count=0`。
- marker-only 不计成功：响应区分 `applied_count`（业务表实际变更格数，按 before≠after 统计）与 `draft_marked_count`；测试断言业务表无变化时 `applied_count=0`。
- `trigger_recalc` 只在业务值实际变更时调用（测试：marker-only 刷新后 `working_paper.prefill_stale` 计数不变）。
- 预设库全量扫描：未注册函数名 0 个（`TB_SUM` 17→0），作为守卫测试。

### P0-4 报表 false-fresh —— 确认（P0），根因改写

**复现**：5 个活的非测试项目（安徽骨科、重庆医疗器械、宜宾临港店、和平药房、华氏）各 82 行有公式 = 410 行。按 `generate_all_reports` 的类型顺序与行序，用生产 `ReportFormulaParser.execute_with_status` + `_check_tb_fallback` 复刻全量生成语义求现值；另写独立求值器算金标准（TB / SUM_TB 只取**叶子**科目，不用平台代码）。

| 项目 | 比对 | 漂移 | 其中 `is_stale=false` | 存量=金标准 | 现算=金标准 |
|---|---:|---:|---:|---:|---:|
| 安徽骨科 | 82 | 0 | 0 | — | — |
| 重庆医疗器械 | 82 | 3 | 2 | **3** | 0 |
| 宜宾临港店 | 82 | 0 | 0 | — | — |
| 和平药房 | 82 | 47 | 47 | 0 | **47** |
| 华氏 | 82 | 0 | 0 | — | — |
| 合计 | 410 | 50 | 49 | 3 | 47 |

**逐行归因**（50 行）：
- **试算表在报表生成后变更但未标过期：0 行。** 和平药房 53 行 TB 全部创建 / 更新于 2026-05-13 01:24，报表行创建于 05-13 07:42（`generated_at` 记为 05-25）；医疗器械 TB 最后更新 06-07 07:24，报表生成 06-07 10:51。都是先改 TB 后出报表。
- **「三路重算语义差异」：0 行。** 410 行中触发 TB 兜底或公式报错的行为 0，全量 / stale / affected 三条路径在这批数据上算出的值相同。三路差异是潜在缺陷（见下 N4、N5），不是这 50 行的成因。
- **存量由旧口径生成、口径变更后从未失效：46 行（和平药房）。** TB 自 05-13 起未变，存量却普遍是现值的 ±2 倍（负债 / 权益为 −2×，资产为 +2×，个别 3×、7×），例：BS-102 实收资本 `TB('4001')` 存 −300,000,000.00，TB 审定 150,000,000.00；BS-061 应付账款存 −534,617,953.54，TB 267,308,976.77。现算与叶子金标准 46/46 一致 ⇒ **存量错**。平台没有「计算口径版本」，引擎改口径后旧行不会变 stale。
- **定义变更未失效：1 行（和平药房 BS-117 专项储备）。** `report_config` 于 2026-09-13 把公式从 `TB('4103')` 改成 `TB('4301')`，`financial_report.formula_used` 仍是旧式、值 53,384,067.82、`is_stale=false`；现算 0 = 金标准。
- **现算错、存量对：3 行（医疗器械 BS-008 / BS-027 / BS-053）。** TB 同时存在父科目 `1231`（−102,358,291.13）和子科目 `1231-01~05`（合计同额）。`_resolve_tb` 前缀聚合把父子都加进来，`TB('1122')-TB('1231')` 现算 1,873,804,340.16，叶子金标准 1,771,446,049.03（= 存量）。**若此时全量重新生成，会把 102,358,291.13 的错误写进这 3 行并标 fresh。**
- **最大差额样本 IS-075（和平药房，3,928,889,818.20）**：存量 −700,568,256.30、现算 3,228,321,561.90，按公式口径现算正确，但公式本身会计错误：IS-075「*归属于少数股东的综合收益总额」= `SUM_ROW('IS-001','IS-074')`，IS-074「归属于母公司所有者的综合收益总额」= `SUM_ROW('IS-001','IS-073')`（把收入、成本、IS-001 与 IS-002 重复的营业收入全部相加）。两边都不是会计上正确的数（N2）。
- 待核数据口径（未下结论）：医疗器械 `1231` 坏账准备在 `trial_balance` 里是负数，`TB('1122')-TB('1231')` 实际是相加；按 v2 正数口径应为正数。需与 TB 方向口径负责人确认。

**根因**：①`financial_report` 只有 `formula_used` / `generated_at`，没有计算版本或输入指纹，引擎 / 定义变更不会让旧行失效；`report_config` 被直接改写（不经 V199 同步内核）时不发 stale。②`ReportFormulaParser._resolve_tb` / `_resolve_sum_tb`、`TrialBalanceResolver.resolve_tb` 用 `LIKE 'code%'` 前缀聚合，不排除「有子科目的父科目」，与平台叶子聚合铁律（`four_table/leaf_aggregation.py`）不一致。③全量生成 `_generate_report` 丢弃 `FormulaResult` 状态、报错按 0 写入并清 stale，且 `_check_tb_fallback` 会把合法的 0 替换成首个科目余额（N5）；`regenerate_affected` 也丢状态、`_is_affected` 只认 `TB('{account}'` 精确串、默认准则 `enterprise`（N4）。

**修复验收**：
- 410 行逐值：对每个 `is_stale=false` 的行，`current_period_amount` 与独立叶子金标准差 ≤0.005，否则该行必须 `is_stale=true` 或带 blocked 原因；断言 false-fresh = 0（真 PG 只读重算守卫，不写库）。
- 父子并存夹具：TB 含 `1231` 与 `1231-01/02`，`TB('1231','期末余额')` 只算一次；医疗器械 BS-008 重算 = 1,771,446,049.03。
- `report_config.formula` 改写（任何写入路径）后，同准则项目对应 `financial_report` 行变 stale（测试覆盖 `fill_all_formulas`、迁移脚本路径、V199 发布三条）。
- 全量 / affected / stale 三条路径对同一夹具（含 `1/0`、缺科目、合法 0 结果）逐值与状态一致；合法 0 不得被兜底替换。
- `regenerate_affected(changed_accounts=['1231-02'])` 命中引用 `TB('1231')` 的行。
- 种子公式守卫：IS-074 / IS-075 不得是覆盖整张利润表的 `SUM_ROW`（按准则逐行核定后的金标准断言）。

### P0-5 lineage 附件跨项目泄露 —— 确认（P0），范围更大

**复现**（单个回滚事务）：A=和平药房、B=华氏，各插一条【探针】附件，`attachment_lineage` 两条都挂 `target_type='wp_cell', target_ref='D2!B5'`（另各挂一条 `report_row / BS-002`）。

| 调用 | 期望 | 实际 |
|---|---|---|
| `query_lineage(A, wp_cell, 'D2!B5')` | 只有 A 的附件 | **A + B 两条**（B 的文件名、类型、attachment_id 全部可见） |
| `_query_attachments(A, wp_cell, '_')` | 0（无此 ref） | **A + B 两条**（`_` / `%` 是 LIKE 通配符，用户传入即可列出全平台最近 20 条） |
| `_query_attachments(A, report_row, 'BS-002')` | 只有 A | A + B |
| `query_lineage(A, report_row, 'BS-002')` | 只有 A | 空 —— 不是隔离生效，而是同请求里 `report_trace_service` 查不存在的表 `note_wp_mapping` 让 PG 事务中止，附件查询被吞（见 P1-1） |

回滚后 `attachments` 中【探针】行 0。live `attachment_lineage` 目前 0 行，但写入端点 `routers/attachment_lineage.py` 已注册，前置条件正常可满足，维持 P0。`attachments` / `attachment_lineage` 均未启用 RLS。

**根因**：`unified_lineage_service.py::_query_attachments` 的 SQL 只有 `al.target_type = :t AND al.target_ref LIKE '%{object_id}%'`；入参 `project_id` 未使用；`object_id` 未转义；不过滤 `attachments.is_deleted`。`attachment_lineage` 表无 `project_id` 列（`attachments.project_id` 有）。

**修复验收**：
- 端点测试（TestClient + 真实鉴权链）：A、B 同 `target_ref`，A 的成员只拿到 A；B 的 attachment_id 不出现在响应任何字段。
- `object_id` 含 `%`、`_`、`\` 时按字面匹配，跨项目结果 0。
- 软删附件不返回。
- 实现方式（join `attachments.project_id = :pid`，或迁移给 `attachment_lineage` 补 `project_id` 并回填）任选，但上面三条都必须是真 PG 测试，SQLite 不能证明。

### P0-6 project-origin pending 陈旧决策 —— 确认（P0，动态复现）

**复现**（`_env.make_db()` + 生产 `apply_ops` / `project_ops`）：
1. 来源项目把 BS-001 改成 `ROW('BS-009')`，`apply_to_projects` 推给有本地改动的目标项目 → 目标得到 pending，`upstream_origin='project'`、`upstream_version=None`。弹窗快照：item_id=X，显示上游 `ROW('BS-009')`。
2. 来源项目再改成 `TB('9999','期末余额')*100` 并再次推送 → **同一条 item（id 仍是 X）被原地覆盖**，`upstream_version` 仍为 None。
3. 旧弹窗提交 `{item_id: X, choice: adopt, upstream_version: None}` → **被接受**，目标项目公式变成 `TB('9999','期末余额')*100`，用户审阅的却是 `ROW('BS-009')`。

前端 `FormulaPendingSyncDialog.vue` L247 原样回传 `i.upstream_version`（null）。

**根因**：`apply_ops.py::apply_to_projects` 调 `upsert_pending(..., upstream_version=None, upstream_origin="project")`；`pending.py::upsert_pending` 按 project+domain+slot 找到旧行就地改 `upstream_definition`，不递增任何修订号；`project_ops.py::resolve_items` 仅在 `expected is not None` 时比较。

**修复验收**：
- 上面三步写成回归测试（生产函数、不 mock），第 3 步必须抛 `SyncItemStale`（HTTP 409），目标项目公式不变。
- pending 行每次 upsert 都递增修订号（新列或复用 `updated_at` 精度足够的 token），全局 / 模板 / 项目三种来源一律携带；resolve 缺修订号返回 428。
- 同一测试跑真 PG 一次（`pg_only`），确认并发两次推送下修订号单调。

## 2. P1 逐项

### P1-1 UnifiedLineage 少参 + broad catch —— 确认，扩展

- `_query_wp_upstream / _downstream` 调 `trace_upstream(self.db, project_id, identifier)`；真实签名 `(db, project_id, source, identifier)`。实测 3 参调用抛 `TypeError: missing 1 required positional argument: 'identifier'`，被 `except Exception: logger.debug` 吞成 `[]`。
- 金标准：和平药房 `trace_upstream(db, A, 'workpaper', 'D2')` 返 **7** 条；wrapper 对 `wp_cell D2` 返 0。`report_row BS-002`、`note_cell 五、1` 真实结果也是 0（无可对比差异）。
- 扩展：`report_row` / `note_cell` 都调 `ReportTraceService.trace_section`，把报表行次当附注章节；该函数第一条 SQL 查 `note_wp_mapping`，**live 库无此表**（UndefinedTableError），PG 事务中止，同请求后续的试算表、版本链、附件查询全部失败并被吞，表现为「无溯源、无附件」。服务 5 处 broad catch 都只 debug。

**验收**：wrapper 按 `object_type → source`（wp_cell→workpaper、report_row→report、note_cell→disclosure）调用，和平药房 `wp_cell D2` 上游条数 = 直接调用结果（7）；每个子源在 SAVEPOINT 内执行，失败时响应带 `partial=true` + `errors[{source, message}]`，不再返回静默空数组；原生 SQL 表名契约测试覆盖 `report_trace_service`（`note_wp_mapping` 不存在即红）；单测不得 patch 掉被测 wrapper 调用的真实函数签名（用 `inspect.signature` 断言实参个数）。

### P1-2 timeline 3/5 源字段漂移 —— 确认，扩展

| 源 | 用到的字段 | 真实模型 | 结果 |
|---|---|---|---|
| 审计日志 | `AuditLogEntry.project_id`、`.created_at` | 无这两个属性（项目在 `payload->>'project_id'`，时间是 `ts`） | AttributeError 被吞 |
| 全局发布 | `status=='applied'`、`.created_at`、`.changes`、`.user_id` | CHECK 只允许 published/pending/rejected；字段是 `published_at/change_set/published_by` | AttributeError 被吞 |
| 模板版本 | `.created_at` | 只有 `published_at` | 当前无订阅时提前 return，**潜伏** |
| 推送 / 冲突 | — | 字段正确 | 正常 |

扩展：`_publish_events` 先 `from app.models.audit_platform_models import Project`（该模块没有 `Project`，ImportError 被内层 `except: pass` 吞），又查不存在的 `Project.accounting_standard` ⇒ 准则过滤静默关闭。实测医疗器械（`5e193c68…`）有 1 条 `formula.changed`（2026-10-18 12:12），`build_timeline` 返回 total=0。

**验收**：用真 ORM 行（PG）各造一条审计 / 发布 / 模板版本 / 推送 / 冲突事件，`build_timeline` 返回 5 类各 1 条；任一源失败时响应 `unavailable_sources` 列出该源，不返回空；医疗器械真实数据只读复核 total≥1。

### P1-3 审计哈希链无项目锁 —— 确认，细节改述

- AST 现算 `append_audit_log` **41 处调用 / 25 个文件**；helper 无 `pg_advisory_xact_lock`（worker 同名函数有）。同项目两个并发事务会读到同一 `prev_hash`，产生分叉。
- 「查询失败退回 genesis」改述：在 PG 上 SQL 失败会让事务中止，随后的 INSERT 也会失败，实际结果是**审计写入失败**而非静默新链；只有非 SQL 异常（如配置读取失败、走错方言分支）才会落一条 `prev_hash=0…0` 的新链首。仍应 fail-closed。
- `routers/audit_logs.py::verify_chain`：第一条 prev_hash ≠ genesis 时直接采信；删掉链前缀仍判有效；时间片查询不校验与片外前序的衔接。
- 链按 `ORDER BY ts DESC LIMIT 1` 取前序，同微秒并发写无确定序。

**验收**：PG 并发测试（同项目 2 个事务各写 1 条）链长 2、`entry[1].prev_hash == entry[0].entry_hash`；`_get_prev_hash` 任何异常向上抛；verify-chain 对「删除首条」「首条 prev_hash 非 genesis」返回 invalid；时间片校验需带片外前一条哈希。

### P1-4 语法 / 元数 / PREV / 错误 / 精度多轨 —— 确认，新增 4 条

L1 `execute` 现测（`FormulaContext` 内 1001=123、BS-001=10）：

| 表达式 | 结果 | 问题 |
|---|---|---|
| `PRIOR('1001','期末余额')` | blocked | 前端 `formulaSyntaxParser.ts` 认 `PRIOR`，后端 L1 不认 |
| `5%2`、`1=1` | damaged（AST 解析失败） | 前端 parser 接受 `%` |
| `TB('1001')`、`TB('1001','期末余额','x','y')` | 123，ok | 无 arity 校验，多余参数静默忽略 |
| `IF(1>0,1)` | **0，ok** | 少参返 0 不报错（新增） |
| `MAX()`、`NOTE('五、1','合计','期末','多余')`、`AUX('1122')` | 0，ok | 同上 |
| `1/0`、`ROW('NOPE')` | 0，ok | 错误冒充 0 |
| `ROUND(1.005,2)` | **1.00** | `Decimal` 默认 ROUND_HALF_EVEN（银行家舍入），会计 / Excel 期望 1.01（新增） |
| `TB("1001","期末余额")` | 123，ok | L1 支持双引号，依赖解析不支持（见附加） |

新增：TB 取数在平台里有三套口径——报表 / `TrialBalanceResolver` 按前缀聚合（父子并存时双计，P0-4）、中央 execute 精确码累加、严格轨 `wp_formula_eval_service._resolve_tb` 精确码 `limit(1)`；`WPExecutor.execute` 不看年度（P0-1）。`note_formula_generator.py` 32 处 `float(` / 0 处 `Decimal(`，`cell_formula_evaluator.py` 7 处 `float(` 且自带 `_safe_eval`。

**验收**：一份 registry 同时生成前端已知函数表与后端 arity / 列名表（前后端契约测试：集合相等）；arity 不符 → `ok=False`；`1/0`、缺行 → `ok=False`；`ROUND(1.005,2)=1.01`、`ROUND(-1.005,2)=-1.01`；同一组夹具在 L1、报表 parser、严格轨、附注 generator 上数值与状态逐一相等；TB 取数统一按叶子聚合。

### P1-5 wp effective 与 tb_detail 消费不完整 —— 确认

- `formula_settings/wp_effective.py` 文首自认：`formula_runtime` 与各循环 Tier A 预设只读 `wp_formula`，不读全局层。现读消费方：`routers/wp_template_files.py`（初始化）、`prefill_engine.py::overlay_prefill_formulas`、`wp_template_init_service.py`、`prev3_prefill_locator.py`；`coordinator._load_formulas` 直接 `select(WpFormula)`。
- `wp_formula_service.py` 无任何 `formula_settings` 引用（S5 旧保存路径未接同步内核）。
- `formula_settings.tb_detail` 生产 import 仅 `routers/tb_detail_formulas.py`；`propagate_tb_detail` 把全项目底稿标 `prefill_stale`；`WIRED_DOMAINS` 是包含 tb_detail 的常量。

**验收**：全局层发布一条 wp 定义后，Runtime 计划、Tier A 预设、预填三条路径对同一单元格读到同一表达式（测试调三条生产路径）；`wp_formula_service.save` 写入后 `base_version/base_definition` 与同步内核一致（再发布全局时分类为 follow 而非 conflict）；`/formula-settings/domains` 的能力状态由消费方注册表派生，tb_detail 在无业务读者时不得显示 wired，保存 tb_detail 不改任何 `working_paper.prefill_stale`。

### P1-6 附注多写方与 stale 不收敛 —— 确认，数字修正

- 现算（口径：`audit-platform/frontend/src` 下非测试 `.ts/.vue`，`export function build\w*SyncPayload`）：**109 个定义 / 79 个文件**；`useDisclosureAutoSync` 144 个文件；含 `sync-from-workpaper` 161 个文件。与旧报告 67/57、141 不同，口径或代码已变，**以口径 + 现算为准，禁写死**。
- `disclosure_notes` stale 227 行中 **187 行属于已软删项目 `37814426…`**，活项目只有华氏 40 行；`stale_source` 在全表 1090 行（含 863 行 fresh）**全部为 NULL** ⇒ 这个字段从未被写过。
- `disclosure_engine.py::refill_sections` 只在 `_values_differ(old,new)` 为真时把章节放进 `sections_recomputed`；`note_stale_service` 只清这些章节 ⇒ 重算成功但值不变的章节永远 stale。

**验收**：重算成功（无错误）即清 stale，值未变也清；`stale_source` 在每个标 stale 的写入点被赋值（守卫：全仓置 `is_stale=True` 的点都同时写 `stale_source`）；活项目口径的 stale 统计排除软删项目；字段级 ownership 矩阵产出前不动写方（受 `disclosure-payload-authority-source` 裁定约束）。

### P1-7 settings 传播无 durable outbox —— 确认

`propagation.py::publish_events` 在路由 commit 之后逐项目 `publish`，异常只 `logger.warning`；`on_formula_config_changed` 失败只写 `stale_degraded_logger`（进程内）。`formula_settings` 包内无 outbox / retry。

**验收**：定义写入与 outbox 行同事务；模拟 EventBus 抛错后，outbox 行保持 pending，worker 重试成功后对应项目 stale / 重算发生且只发生一次（幂等 key = publish_id + project_id）；界面能查到 pending / failed。

### P1-8 validator / 资源预算 / 回滚 —— 确认（动态复现）

- `_env` 内存库：报表项目层 `save_overrides` 依次存 `EVIL(((`、`TB('1001'`、`PRIOR('1001','期末余额')`、`1/0` **全部接受**；`publish_global(report, EVIL((()` **接受**。`domain_stores.py::validate_definition` 只校验 wp / push / note / consol_note，且只在模板路径调用。
- `FORMULA_EXECUTE_TIMEOUT` 只出现在 `core/config.py` 与系统设置展示（后端 `system_settings.py` + 前端 `SystemSettings.vue`），无执行路径消费。
- `formula_settings/rollback.py::rollback_from_log`：写入值取请求体 `target_formula`，不与日志 `old_formula` 比对；`expected_version` 缺省时自动取当前版本 ⇒ 陈旧页面也能覆盖。
- `routers/wp_formula.py::delete_formula` 无 `expected_version`。

**验收**：所有 global / project / template / package 写入共用服务端 validator（语法 + 函数登记 + arity + 列名），上面 4 个坏式均 422；执行带 deadline（超时返回 timeout 状态，测试用人为慢 resolver）；回滚只接受 `source_log_id + expected_version`，目标公式由服务端从日志读取，缺版本 428、版本不符 409；删除缺 `expected_version` 428、不符 409。

### P1-9 最终值不绑定计算版本 —— 确认

`financial_report` 列：`formula_used`（文本）、`source_accounts`、`generated_at`，无定义版本 / run_id / 输入指纹（`information_schema` 现查无 `%version%` 列）；`disclosure_notes` 有 `stale_source / last_sync_source / source_template / source_project_id`，其中 `stale_source` 全 NULL；`wp_formula` 29/29 `refs=[]`、`last_computed_at IS NULL`。P0-4 的 46 行旧口径存量正是因为没有计算版本才无法被识别。

**验收**：每次写最终值同时写 `formula_definition_version + evaluated_at + run_id + inputs_digest`；引擎口径版本号变更时，旧版本行可被 SQL 一次查出并标 stale；最终值组件读取该 envelope 展示（前端挂载守卫扫描真实宿主）。

## 3. 附加缺陷

| 缺陷 | 结论 | 复现 | 根因 | 验收 |
|---|---|---|---|---|
| UnifiedLineage 少参吞空 / timeline / 哈希链 / 多轨语法 / wp effective / 附注 / outbox / validator / provenance | 同 P1-1~P1-9 | 见 §2 | 见 §2 | 见 §2 |
| 依赖解析漏双引号（P2） | 确认 | `execute('TB("1001","期末余额")')`=123 ok；`upstream_refs` 返 `[]`；`references(account='1001')`=False | `formula_settings/dependencies.py` 9 个正则（`_TB`…`_PREV`）只写了 `'` | 单 / 双引号同一公式 `upstream_refs` 结果相等（参数化覆盖 9 个函数）。影响面：只被依赖面板（`routers/formula_settings.py`）和 `formula_catalog.py` 使用，不参与 stale 传播，故维持 P2 |
| 自定义函数自引用（P1→P2） | 确认 | 注册 `SELF_AUDIT()=SELF_AUDIT()` 后执行：递归到上限，最终 `ok=True, value=0`；`FormulaEngine().list_custom_functions()` 为 `[]`、新实例注销返回 False | `register_custom_function::_custom_handler` 只取内层 `.value`、丢弃 errors；注册表是模块级 `_REGISTRY` 但列表是实例级；无依赖图 | 降级理由：注册端点仅 admin，状态不持久、不跨进程。验收：自引用 / 互引用注册时被拒，或执行时 `ok=False`；若决定退役，端点返回 410 且 `_REGISTRY` 不再接受运行时注册 |
| preset 4 挂载仅 1 有保存（P2） | 确认 | `<GtFormulaPresetDialog>` 生产挂载 4 处：`FormulaTab`（有 `@edit-formula="onSaveCustomPreset"`）、`ReportConfigTab`、`NoteTemplateTab`、`WpTemplateDetail`（都没有） | `GtFormulaPresetDialog.vue`：`canEdit` 默认 true；`onEditorSave` 无条件 `ElMessage.success('公式已编辑（可经导入或底稿保存持久化）')` | 挂载守卫：每个传 `canEdit≠false` 的挂载点必须绑定 `@edit-formula`；无 handler 的 3 处渲染时无「编辑 / 新建」按钮（vitest 挂真实宿主断言） |
| 应用范围 3/7 域接线（P2） | 确认 | `askApplyScope(` 生产调用：`FormulaManagerDialog.vue`（report 单行 / 批量保存）、`useTbDetailFormulas.ts`、`useCrossCheckRules.ts` | wp / note / consol_note / push 保存链未调用 | 7 个域的保存成功回调要么调用 `askApplyScope(domain, slots)`，要么在界面显式标注「本域不支持推广」（前端契约测试枚举 `DOMAINS`） |
| 冲突决策 key 缺 domain（P2） | 确认（结构性） | `engine.py::PlanItem.key = f"{project.id}\|{slot_key}"`；`apply_ops.py` L74、L124 同式；`template_sync.py::_apply` 多域共用一个 `outcomes` dict | DB 身份含 domain，内存决策键不含 | 两域同名 slot 的模板发布：两域决策可分别设置、`outcomes` 两条、摘要 pending 数正确（单测）；旧两段键兼容映射到三段键。现行各域 slot 格式不同（`balance_sheet:BS-001`、`{wp}\|{sheet}\|{cell}`、`{章节}\|{目标}`…），撞键需同名，故 P2 |

## 4. 新增发现（旧报告未列）

| # | 级别 | 现象 | 根因 | 验收 |
|---|---|---|---|---|
| N1 | P1 | `report-config/execute-formulas-batch` 同一轮多条公式用 `asyncio.gather` 并发跑在**同一个 AsyncSession** 上。按同样模式对和平药房 6 个科目并发 `TrialBalanceResolver.resolve_tb`：1 个成功、5 个 `InvalidRequestError: concurrent operations are not permitted`。该端点被 tb_detail 批量预览和报表批量执行使用，异常被 `_exec_one` 吞成 `'执行错误: …'`、value=None | `routers/report_config.py::execute_formulas_batch::_exec_one` | 批量执行 10 条独立公式（真 PG）全部返回数值、无「执行错误」；实现改为串行或每任务独立 session。注：本条只在 resolver 层复现，未经 HTTP 端点 |
| N2 | P1 | `report_config` soe_standalone 种子：IS-074「归属于母公司所有者的综合收益总额」=`SUM_ROW('IS-001','IS-073')`，IS-075「*归属于少数股东的综合收益总额」=`SUM_ROW('IS-001','IS-074')`；把收入、成本、重复的营业收入一起相加，P0-4 最大差额样本即此行 | 种子定义错误 | 按准则逐行核定 IS-074/075（及同类 `SUM_ROW` 合计行）后加金标准守卫；和平药房重算 IS-074 = IS-073 − 少数股东部分 |
| N3 | P2 | 预设库 4250 条中 17 条使用未注册函数 `TB_SUM`（应为 `SUM_TB`），会被 L1 blocked；Draft Refresh 会把它们当「初稿」打标记 | `formula_management/preset_library` 数据源 | 预设库全量扫描未注册函数 = 0（守卫测试） |
| N4 | P1 | `ReportEngine.regenerate_affected`：`_is_affected` 只认 `TB('{account}'` 精确串，子科目变化（如 `1231-02`）不会命中引用 `TB('1231')` 的行；默认 `applicable_standard='enterprise'`；用 `execute()` 丢状态并清 stale | `report_engine.py::regenerate_affected / _is_affected` | 见 P0-4 验收第 5 条；调用方未传准则时按项目真实准则解析 |
| N5 | P1 | 全量生成 `_check_tb_fallback`：公式结果为 0 且首个 `TB()` 科目有余额时，直接用该科目余额覆盖（`TB(A)-TB(B)` 合法为 0 也会被改成 `TB(A)`）；stale 重算与增量重算没有这一步。本批 410 行未触发 | `report_engine.py::_generate_report` + `_check_tb_fallback` | 合法 0 结果夹具在三条路径上都写 0；如保留兜底，须写入 warning 且不清 stale |
| N6 | P3 | 已软删项目 `37814426…` 仍持有全部 29 条 `wp_formula`、187 条 stale 附注、2 条 stale 报表行（`financial_report` stale 8 行中 2 行），旧报告的 stale / 公式规模统计混入了它 | 软删不级联、统计不排除 | 统计 / 守卫 SQL 一律 `JOIN projects … is_deleted=false`；是否清理软删项目数据由用户拍板 |

## 5. 对评估报告的勘误

1. P0-1「18 个真实 WP 引用」是软删项目里的 Playwright 夹具，13 条为自引用；结论（Runtime 必错、无环检测）成立，「现网暴露」应写 0。
2. P0-4 的成因不是「三路重算语义不同」（本批 0 行由此造成），而是「存量未随口径 / 定义变更失效」+「前缀聚合父子双计」+「种子公式错」；且 3 行是**现算错、存量对**，按旧验收「410 行与现算逐值一致」去修会把错误写进报表。验收必须对独立叶子金标准。
3. P0-5 不需要「同 ref」：`object_id` 是未转义的 LIKE 片段，`_` / `%` 直接跨项目列出附件。
4. P1-3「查询失败退回 genesis」在 PG 上多数表现为写入失败而非静默新链。
5. P1-6 的 227 stale 中 187 属软删项目；`stale_source` 不是「stale 行为空」，而是全表从未写入。builder 数现算 109/79（口径见 §2），不写死。
6. 自定义函数自引用按「仅 admin、进程内」降为 P2。

## 6. 未验证 / 限制

- 未调用 `DraftRefreshOrchestrator.generate()` / `execute_refresh()`（会写 marker、快照、`prefill_stale`，并可能 apply mutation）；P0-1 / P0-3 的「写入」结论来自 `prepare` 结果 + adapter / service 源码。
- N1 只在 resolver 层复现了同 session 并发异常，没有经 HTTP 调用该端点。
- P0-6、P1-8 的动态复现跑在 SQLite 内存库；P0-6 的 PG 并发版本单调性未测。
- P1-6 附注字段级多写冲突没有逐格对拍，只复核了章节级机制与计数。
- P0-4 中和平药房存量「±2 倍」的历史生成口径无法从现库还原（TB 无历史版本），只能确定存量与金标准不符、现算相符。
- 医疗器械 `1231` 坏账准备为负数是否符合 v2 正数口径未下结论。
- 未跑 pytest / vitest 全量；未做登录态浏览器验证。
