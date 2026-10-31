# 需求文档：公式中枢正确性与安全闭环（formula-hub-integrity-closure）

## 概述

阶段一评估（`.agents/tasks/formula-management-comprehensive-assessment-2026-10-25/report.md`，第四轮复核 APPROVED）结论：公式管理结构/证据分 **36/100（1.8/5）**，风险调整后 **集成原型级**。治理层（V199 全局/项目/模板/冲突/CAS）保留；执行、写入、隔离与溯源存在确定性缺陷：错误结果表现为 0、成功、「已是最新」或「通过」。

本 spec 范围 = 近期 **正确性与安全闭环**（边界以 design §8.0 的边界裁定表为准，该表逐条取代 `p1-00-baseline-recon.md` §4 的旧边界）：

- 已确认的全部 6 个 P0（P0-1~P0-6），含阶段一 P0-1 验收 A1~A6 全部；
- 不需用户拍板的 P1：P1-1 UnifiedLineage、P1-2 timeline、P1-8（validator、执行预算、回滚取服务端快照、删除 CAS），以及 P1-3 中公式审计日志的伪造入口与年度（需求 11）。P1-3 的审计哈希链加固（锁、可重放哈希、唯一链尾、分叉确认、worker 隔离）整体移交后续 spec S10（design §8.1），本 spec 不改审计日志的写入语义；
- 同批 P2：P2-8 自定义函数递归 fail-closed、P2-7 依赖解析双引号；低成本 P2：P2-3 预设假保存宿主改只读、P2-2 未支持域禁用应用范围、P2-6 冲突决策键加 domain、P2-5 发布记录可见性与删除策略；P3-2 `specAReady` 写死；
- 需拍板但按 report.md §10 推荐默认纳入的：P1-11 一致性门禁（§4 D1、D2）、利润表归属行（D3）、舍入（D4）。

铁律：每项根因修复，禁止换参数绕开；任何失败状态不得表现为 0 / 成功 / 「已是最新」/ 「通过」；Formula Runtime 修复前其写入路径由服务端拒绝（fail-closed）；凡写真实项目数据或共享库结构的动作（存量报表定义升级、真实项目报表重算、迁移应用到共享库、开启门禁阻断）本 spec 只在【测试】项目或回滚事务内验证，列为 §4.2 决策项交用户决定。

术语：
- **金标准** = 测试内用独立 SQL 或独立求值器算出的期望值，不调用被测代码；验收中出现的真库数值只作记录，断言一律比对测试时现算的金标准。
- **真 PG** = `pg_only` 标记的测试；本 spec 验收时连接本机 `audit_platform` 的一次性快照库（design ADR-25：不含两张序时账表的数据、已由 MigrationRunner 执行本 spec 迁移、收尾删除），共享库本身不执行 DDL；写入型一律在回滚事务或快照库内的【测试】项目中；多会话并发用例在快照库内真提交、用后删除。
- **活项目** = `projects.is_deleted = false`。
- **项目年度** = `app/services/project_audit_year.fetch_project_audit_year`（SQL `PROJECT_AUDIT_YEAR_SQL`：audit_year → audit_period_end 年份 → audit_period_start 年份）；结果为空即「项目未设置审计年度」，不得改用日历年或单取 `audit_period_end`。
- **决策项** = §4.2 所列、本次不执行、交付后由用户决定的动作。

## 1. 现状事实表（来自阶段一复核与本轮现读；F 编号仅在本文件维护）

| F | 事实 | 来源 |
|---|---|---|
| F1 | Runtime `formula_management/engine.py::execute_batch` 只把预载值写入 `row_cache[addr_id]`，`WP()` handler 读 `ctx.wp_data`（空）；`_topological_sort_formulas` 遇环按原序追加；`coordinator._build_batch_definitions` 只从 `wp_formula.refs` 取引用（29/29 为 `[]`）；目标 addr_id = `{wp_id}/{sheet_name}/{target_cell}`，与 ACNR `{wp_code}/{sheet_code}/{cell}` 不在同一命名空间 | [V] P0-1 |
| F2 | 29 条 `wp_formula` 全属已软删项目（Playwright 夹具 `PW*`），活项目 0 行；独立金标准下 Runtime 18/18 错（13 条自引用 1000→0、5 条跨底稿 1001→1），11 条字面量两轨都对；严格轨 5/18 对、自引用无环检测 | [V] P0-1 |
| F3 | `FormulaEngine.execute`（中央 `/api/formula/execute`、`/batch-execute`）只读 `unadjusted_amount` 并经 `from_simple_map` 冒充审定/期末，返回体 `error` 写死 `None`；华氏 1001 审定 100 返 0 | [V] P0-2 |
| F4 | L1：除零、`ROW` 缺行、未注册函数返回 0；`IF` 非 3 参、`MAX`/`MIN` 少于 2 参、`ROUND()`、单参 `AUX` 返回 0 且 `ok=True`；`ROUND` 用 `ROUND_HALF_EVEN`；`safe_eval_expr` 除零/异常一律 0；`_REGISTRY` 的 arity 与实际用法不符 | [V] P1-4 |
| F5 | 路由预检 `require_function_support(data.formula_type, …)` 只看请求字段；`expression_functions` 只提取已登记函数名 | 现读 |
| F6 | `DraftRefreshOrchestrator._dispatch` 四域全交 Runtime；无 mutation 时 `refresh()` 只写 marker/审计/快照并 `mark_stale`，返回 `success`；`execute_refresh` applied 为 0 有 marker 也调 `trigger_recalc`；路由把 `no_effect` 映射为 `success`；幂等短路、`preset_application`、scope 留痕只认 `success` | [V] P0-3 |
| F7 | 和平药房只读分派：report 0 mutation / 343 个预设单元只被打 draft 标记；预设库 17 条用未注册 `TB_SUM`（来自 `prefill_formula_mapping.json`，另被预填引擎、联动图消费）；`preset_acnr_migration.LEGACY_ALIAS_MAP` 含 `TB_SUM→SUM_TB`，也含把已注册 `TB_AUX` 改成 `AUX` 的条目；映射文件另有 2 处 `TB_AUX(` | [V] P0-3；现读 |
| F8 | TB 前缀聚合：`ReportFormulaParser._get_tb_rows_prefix`、`TrialBalanceResolver`、`formula_preloader._load_tb`、`formula_push/sources.load_tb_audited` 均 `LIKE 'code%'`，父子并存即双计；`_resolve_sum_tb` 区间不排父；严格轨 `_resolve_tb` 精确码 `limit(1)` | [V] P0-4 |
| F9 | 5 个活项目 410 行有公式报表行：50 行漂移、49 行 `is_stale=false`；医疗器械 BS-008/027/053 父科目 `1231` 双计 102,358,291.13 | [V] P0-4 |
| F10 | `financial_report` 无计算版本列；失败原因只有口径性留空 `blank_reason`（V173），没有计算失败原因；`_generate_report` 用 `execute()` 丢状态、报错按 0 写入并清 stale；`_check_tb_fallback` 把合法 0 换成首个科目余额；`regenerate_affected` 丢状态、`_is_affected` 只认精确码；`generate_all_reports` 默认准则 `enterprise`、先 `full_recalc` 且失败只 warning；`REPORTS_UPDATED` 由 `routers/reports.py`、`formula_settings/propagation.py` 与事件处理器（`after_commit_event_type`）发出（勘误：前稿写「无失败原因列」「只由报表路由发出」） | [V] P0-4；现读 |
| F11 | 真库四套准则共 8 条跨越其他合计行的 `SUM_ROW`（国企两套 IS-074/075、上市两套 IS-051/052）；种子这些行 `formula` 为 `null` ⇒ 错误定义来自其他写入路径；活项目 IS-074/075 有 4/5 行非零 | [V] N2；现查 |
| F12 | `unified_lineage_service._query_attachments`：SQL 只有 `target_type` + `target_ref LIKE '%{object_id}%'`，不用 `project_id`、不转义、不滤软删；`attachment_lineage` 无 `project_id` 列、无任何外键；本机 0 行 | [V] P0-5；现查 |
| F13 | `GET /api/formula-settings/publishes` 只依赖 `get_current_user`；`list_publishes` 先 `limit` 后返回；全局候选带 `note`、`source_project_id`；`target=projects` 的 `summary.changed_projects` 含他项目 UUID | report §11.3；现读 |
| F14 | project-origin pending：`upsert_pending(..., upstream_version=None)` 原地覆盖、无修订号；`resolve_items` 仅在 `expected is not None` 时比较 | [V] P0-6 |
| F15 | 冲突决策键 `{project}\|{slot_key}`；DB 身份 project+domain+slot；`template_sync._apply` 多域共用一个 `outcomes`；slot_key 可含 `\|` | [V] §3 |
| F16 | UnifiedLineage 以 3 参调用 4 参 `trace_upstream`，`TypeError` 被吞成 `[]`；`trace_section` 查不存在的表 `note_wp_mapping`，PG 事务中止后同请求后续子源全空；端点 `object_type` 另接受 `tb_row`、`adjustment` | [V] P1-1；现读 |
| F17 | timeline 五源字段漂移（`AuditLogEntry.project_id/created_at`、发布 `status=='applied'`、模板版本 `created_at`）；5 源 `except: return []`；医疗器械真实 `formula.changed` 1 条而 total=0 | [V] P1-2 |
| F18 | （移交 S10，本 spec 不改）`append_audit_log` 无项目链锁、按 `ts DESC` 取尾且异常返回 GENESIS；`verify_chain` 首条非 genesis 直接采信；worker 锁键 `hash(lock_key)`（进程随机）、取锁失败降级无锁、同样异常返回 GENESIS；worker 一批多链同一事务，重试超上限即丢弃 | [V] P1-3；现读 |
| F19 | `POST /api/formula-audit-log/{project}/{year}` 允许 edit 成员提交任意 `old/new_formula/result_value/trace`；GET 忽略 `year`；前端生产调用 0 | report §11.3 |
| F20 | `domain_stores.validate_definition` 只在模板路径调用；报表项目层接受 `EVIL(((`、`TB('1001'`、`PRIOR(...)`、`1/0`，全局发布接受 `EVIL(((`；各域已有校验器 `checked_wp_definition`、`check_note_definition`、`validate_note_formula`、`validate_push_definition`；`settings.FORMULA_EXECUTE_TIMEOUT=10` 无人消费 | [V] P1-8；现读 |
| F21 | `rollback_from_log` 写入值取请求体 `target_formula`、`expected_version` 缺省取当前；`cross_check` 一律 400；前端回滚 `validateStatus: s < 600` 且无条件提示成功 | report §11.3 |
| F22 | 删除无 CAS：`DELETE /api/workpapers/{wp_id}/formulas/{formula_id}`、`DELETE /api/formula-templates/{template_id}`、`DELETE /api/projects/{project_id}/formula-settings/{domain}/overrides` | [V] P1-8 |
| F23 | 审计变更条目 `change_entry` 只存显示用 `old_formula/new_formula` 字符串 | 现读 |
| F24 | `_custom_handler` 丢弃内层 errors；`SELF_AUDIT()=SELF_AUDIT()` 递归到上限后 `ok=True value=0` | [V] §3 |
| F25 | `formula_settings/dependencies.py` 9 个正则只认单引号 | [V] §3 |
| F26 | `GtFormulaPresetDialog` 生产挂载 4 处，仅 `FormulaTab` 绑定 `@edit-formula`；`canEdit` 默认 `true`；`onEditorSave` 无条件提示成功 | [V] §3 |
| F27 | `askApplyScope` 生产调用只在 report、tb_detail、cross_check | [V] §3 |
| F28 | `FormulaManagerDialog` 新增报表行与保存全部、`FormulaHistoryTab` 历史加载带 `validateStatus: s < 600`；`FormulaHistoryTab` 写死 `specAReady=false` | report §11.3、P3-2 |
| F29 | `consistency_gate/_impl.py`：检查方法 16 个、`passed=True` 82 处、`except Exception` 49 处；`CheckItem.severity ∈ {blocking, warning}`，`has_blocking_failures` = 未通过且 blocking；实跑 40 项中 32 项跳过且通过（21 项阻断级）；门禁检查不写库 | [M] T3；现读 |
| F30 | 试算表符号口径按项目不一致（医疗器械/华氏/宜宾/四川物流负债权益为负）；医疗器械试算平衡报差额 5,015,159,210.93，按借正贷负公式仍差 77,183,220.47（含费用类 75,360,658.15 未计入）；`trial_balance.account_category` 现有 asset / liability / equity / revenue / expense 五类 | [M] T3；现查 |
| F31 | `routers/formula_settings.py::WIRED_DOMAINS` 七域常量；`propagate_tb_detail` 把全项目底稿标 `prefill_stale` | [V] P1-5 |
| F32 | 行数门（`split('\n')`，阈值 = 白名单 × 1.05）：`formula_engine.py` 2198/2243；`report_engine.py` 2625/2827；`wp_formula.py` 1508/1534；`draft_refresh_service.py` 2384/2502；`FormulaManagerDialog.vue` 4216/4727；`report_config.py` 801、`consistency_gate/_impl.py` 2360 未登记 | 现算 |
| F33 | 迁移现扫最高 V205（本机已应用 205）；V199 六表业务行全 0 | 现扫 |
| F34 | 利润表净利润以下行真库无公式（国企 IS-046/048/049/053/054/072、上市 IS-029~032/049），活项目全为 0 | 现查 |
| F35 | `formula_engine.COLUMN_ALIASES["未审数"]="期末余额"`，`_load_tb` 不产未审数列；被 `test_formula_runtime_zero_regression.py::BASELINE_COLUMN_ALIASES_PRE_WAVE2` 冻结；报表与严格轨均为 未审数→`unadjusted_amount` | 现读 |
| F36 | `WorkingPaper`、`WpIndex` 无 year 列，`wp_index(project_id, wp_code)` 唯一；活项目一个 `wp_index` 对应多条未删 `working_paper` 现为 0；`WPExecutor.execute` 找不到底稿返回 0 | 现查 |
| F37 | 真库 `report_config` 的 `ROW`/`SUM_ROW` 前向、跨表、悬空引用现为 0 | 现查 |
| F38 | 过期状态读者：`deliverable_readiness_service`、`report_export_checks`、`stale_summary_aggregate`、公式健康度 | 现读 |
| F39 | `WpFormula` 已持久化稳定身份 `stable_sheet_key/row_key/field_key/stable_key_needs_review`（V163，唯一索引 `uq_wp_formula_stable_key`）；推导单一来源 `formula_management/stable_key.py`；`extract_custom_cells` 返回 `CellRecord(sheet, cell, row_label, value)`；`formula_wp_semantics.py` 登记三处 WP 实现与 3 条已知差异（只登记、不被取值实现引用，守卫精确相等） | 现读 |
| F40 | 并行 active spec `acnr-foundation-defect-closure` 0.4 / D1 / 1.2：要求 `WP(底稿,sheet,A1)` 三参精确读取与 acnr_targets 共用公式引擎同一 WP 读取函数，两参行为不变，动手前核对本 spec 是否已提交同函数改动 | 现读 |
| F41 | Runtime adapter：report `VALID_REPORT_TYPES={BS,IS,CFS,EQ,CFSS,IMP}`，PG 枚举 `financial_report_type` = `balance_sheet,income_statement,cash_flow_statement,equity_statement,cash_flow_supplement,impairment_provision`；note adapter 只读 `rows[].cells/key/id`，活项目 `rows` 为数组的 48 张表中首行有 `values` 30 张、有 `cells/key/id` 0 张；`write_cell_to_parsed_data` 在 sheet 不存在时新建；2 条 `wp_formula.sheet_name`「Playwright自定义底稿」与 `html_data` 键（wp_code）不符 | [V] P0-1 第 5、6 条；现查 |
| F42 | `DraftRefreshOrchestrator.generate` 第一步即取项目 advisory lock，再 `_dispatch`；`_dispatch` 只返回 `(units, page_keys)`；`RefreshResult` 计 marker、`ExecutionResult.applied_count = len(all_applied)`（不剔除 before == after） | 现读 |
| F43 | `upsert_pending` 先 SELECT 后改 ORM；部分唯一索引 `uq_formula_sync_item_pending(project_id, domain, slot_key) WHERE status='pending'`（PG 与 SQLite 都声明）；全部 upsert 与 resolve 路径先取 `lock_project` / `lock_domain` | 现读 |
| F44 | （移交 S10）审计链真库只读：1736 行、387 条链各恰 1 个 genesis；同链同 `ts` 49 组；全局链（project_id 为空，893 行）有 1 处未确认分叉（`download` 一支无后继、`view` 一支继续）；`prev_hash` 无索引；helper 用请求 `resource_id` 字符串参与哈希而 `object_id` 只存 UUID；唯一 `formula.changed` 行按 v1 公式重算不等于存值 | 现查；探针 |
| F45 | `function_support_matrix` 只登记 10 个取数函数（TB/SUM_TB/ROW/SUM_ROW/REPORT/NOTE/WP/PREV/AUX/ADJ）；路由把 `param_names` 传给不接收该参数的 `FormulaEngine.register_custom_function` | 现读 |
| F46 | `POST /api/formula/debug` 经 `formula_preloader.preload(..., gaps=)` 预载后同步 `execute`，无 deadline | 现读 |
| F47 | 附件三端点 `POST /api/attachments/{id}/link`、`GET /api/attachments/{id}/links`、`DELETE /api/attachments/{id}/link/{link_id}` 都只做 `enforce_attachment_wp_visibility(action="attach_read")`；lineage 对象类型 `note_cell`，附件 `target_type` 为 `note_section` | 现读 |
| F48 | 历史回滚端点外层 `require_role(["admin","partner","manager"])`、函数体再校项目 `review`；前端门控由 `formulaHistoryRollbackGate.spec.ts` 钉住 | 现读 |
| F49 | `publish_global` 已产出 `changed_slots(items, outcomes)` = 按项目列出有效定义真正变化的 slot；`template_access.Viewer.load(db, user).member_projects` = 本人未删 `ProjectUser` 项目集合；`report_config` 写端点经 `legacy_report` 走 `publish_global / save_overrides / restore_global`，`fill_all_formulas` 已 `publish_global(source="seed")`；`propagation.report_closure` 已有 ROW / SUM_ROW 闭包，`propagate_report` 提交后按闭包标该项目全部年度过期 | 现读 |
| F50 | （移交 S10）`GET /api/audit-logs/verify-chain`：admin 或项目内角色 ∈ `_ALLOWED_PROJECT_ROLES`；按 `ts, id` 排序校验，支持 `from/to` | 现读 |
| F51 | 一致性门禁的消费方（`ConsistencyGate.run_all_checks` 调用方）：`gate_rules_chain.ConsistencyPassedRule`（注册到 sign_off 与 export_package）对 `ConsistencyResult` dataclass 调 `.get`，AttributeError 被自身 `except` 吞掉 ⇒ 恒放行，年度 `year or 2025`；`export_package_service` 非 `force_export` 时 `has_blocking_failures` ⇒ `ConsistencyCheckError`；`chain_workflow /consistency-check` 只展示 `passed`；`dashboard_aggregator_service._aggregate_vr_summary` 计「未通过 ∧ blocking」、年度取 `audit_period_end` 否则今年；`qc_vr_heatmap` 计「未通过」按 severity、年度默认 2025、只依赖 `get_current_user`。`gate_rules_phase14.ConsistencyBlockingDiffRule` 走 `consistency_replay_engine`，不是本门禁的消费方；`gate_engine.evaluate` 每次写一条 `gate_decisions` | 现读 |
| F52 | `consistency_gate/_helpers.py` 8 处 `except Exception` 返回 None 或 1.0；16 个检查共用一个会话；`ConsistencyResult` 与 `CheckItem` 在 `_models.py`、`_impl.py` 各一份，`__init__` 导出 `_impl` 版；10 个循环勾稽只经 `_get_wp_parsed_data` 读 `working_paper.parsed_data`；活项目 1738 份底稿中 1708 份 `parsed_data` 为空，在线表单模式的数据在 `checklist_responses` | 现读；现查 |
| F53 | 活项目 85 个：`audit_period_end` 为空 81 个，按 `PROJECT_AUDIT_YEAR_SQL` 解析不出年度 73 个；有试算表的 10 个活项目年度全部可解析（6 个 `audit_period_end` 为空而 `audit_year=2025`，含华氏、和平药房、医疗器械、宜宾）；`PROJECT_AUDIT_YEAR_SQL` 含 PG 专用 `EXTRACT(...)::int`，在 SQLite 上报错 | 现查（只读） |
| F54 | `report_engine.generate_all_reports` 在函数内、提交前 `event_bus.publish(REPORT_ROW_CHANGED)`（按金额非 0 收集行次）；`chain_orchestrator` 与 `routers/reports.py` 依赖其 dict 返回值（前者对非 dict 静默得空列表）；`recalculate_stale_rows` 与 `regenerate_affected` 用库内非空金额建 row_cache；`report_engine.evaluate_formula_result` 自带两参 WP 预载段，不经 `formula_preloader.preload` | 现读 |
| F55 | `DraftRefreshResponse.status` 为 `success / partial_success / idempotent_hit / failed`，前端 `formulaRuntimeContract.ts` 的 `VALID_STATUSES` 同为四值、遇其他值抛错；`execute_refresh` 幂等 = 取咨询锁后按 mutation 指纹查审计记录，`refresh()` 幂等 = `tb_snapshot_hash + scope`；报表范围不在任一幂等短路内 | 现读 |
| F56 | `MigrationRunner.run_pending` 单文件失败记入 `schema_migration_failures` 并继续，应用照常启动，`/api/health` 据失败记录报 degraded；开发服热重载不跑迁移 | 现读 |
| F57 | `WPExecutor.execute(db, project_id, wp_code, column="审定数", field=None)`：第二参含「坏账准备明细表」走 `_resolve_d23`（找不到一律 0，同码底稿不存在时取任一有坏账行的底稿）；单元格写法先经 ACNR `full_resolve` 重定位再取 `extract_custom_cells` 首个同名格（不分 sheet）；列名写法按 审定数/未审数/期初余额/期末余额 映射读 `parsed_data` 顶层键；外层 `except Exception` 一律 0；`_REGISTRY` 登记的 WP 写法是列名两参；`write_cell_to_parsed_data` 的 `max_row/max_col` 是随写入单调扩展的数据范围（供前端 `hasData`），不是网格尺寸 | 现读 |
| F58 | `wp_formula_eval_service.evaluate_wp_formula_expression` 有三参（`_WP3_PATTERN`）与两参两个 WP 代入循环，均把 `str(val)` 直接代入（取不到返回 None 时会代入字面 `None`） | 现读 |
| F59 | 并发 spec `acnr-foundation-defect-closure`（设计中、无 tasks.md）§2.5 定义同名 `wp_cell_reader.resolve_wp_cell(db, project_id, year, wp_code, sheet_key, cell)`（按位置调用）、`WpCellRead(state ok\|missing, value, reason, wp_id, sheet_key)`、`exact_identity.sheet_of` 可接受键、`WPExecutor` 三参 A1 分支与 `preload_three_arg_refs`（挂在 `FormulaEngine.execute` 与报表预载段）、年度用 `audit_period_end`；其设计复核 F2 / F7 / F8 / F32 要求两边契约一致、三参取不到不代入、年度用单一来源、歧义 sheet 行为写明；另计划下调 `_BODY_IDENTITY_ONLY_BASELINE` 并删年度棘轮一条 | 现读 |
| F60 | 年度兜底棘轮 `tests/test_audit_year_calendar_fallback_ratchet.py` 按文件精确相等（变少也红），本 spec 涉及文件现有条目：`routers/report_config.py` 2、`routers/qc_vr_heatmap.py` 1、`services/dashboard_aggregator_service.py` 2、`services/gate_rules_chain.py` 3 | 现读 |
| F61 | 鉴权棘轮三个常量：路径维 `_IDENTITY_ONLY_BASELINE=200`、前缀维 `_PREFIXED_IDENTITY_ONLY_BASELINE=270`、请求体维 `_BODY_IDENTITY_ONLY_BASELINE=87`，均「不得增加 + 与现算差 ≤ 20」；`formula-fetch-followup-defect-closure` 4.5（路径维待其 4.2）与 ACNR spec 都计划下调 | 现读 |
| F62 | `/api/report-config/execute-formulas-batch` 无条数上限，调用方 `useCrossCheckRules.ts`（每条规则左右两式）与 `FormulaManagerDialog.vue`；本机 PG 16.13，测试连接角色有建库权限；`audit_platform` 47 GB，其中 `tb_aux_ledger` 32 GB、`tb_ledger` 15 GB，其余表合计约 1 GB；库内扩展仅 plpgsql；C 盘空闲 64.7 GB | 现读；现查 |
| F63 | `consistency_gate` 的 `CheckItem` 构造全部在 `_impl.py`：40 处异常出口与 41 处「跳过」出口均写字面量 `passed=True`，只有计算比较的 40 处可能为 False（另 1 处字面量 False 为 warning 级）⇒ HEAD 的 `has_blocking_failures` 只由真实比较失败触发；`_helpers.py` 与 `_impl.py` 以 `select(FinancialReport)` 取整行 | 现读（AST） |
| F64 | 事件总线把每个事件写入 Redis Stream `audit:events`（`settings.REDIS_URL`，默认 0 号库），开发服重启时经消费组重放并在本进程执行处理器；测试进程默认连同一 Redis | 现读 |

## 2. 功能需求与验收标准

> 验收编号 `需求 X.Y`；每条写明机器核查方式。测试文件放 `backend/tests/formula_hub/`（另注明者除外）。变异编号见 design §10.4。

### 需求 1　Formula Runtime：先冻结、再修求值（P0-1，A1~A6）

1.1 冻结：本需求 1.3~1.10 全部通过前，`POST /api/workpapers/draft-refresh` 的计划中只要含 Runtime 产出的 mutation（不论其 `source_formula_id` 能否解析）即返回 409 `FORMULA_RUNTIME_FROZEN`；拒绝发生在取项目锁、写审计、调用任何写入方之前；业务表 before==after、`draft_refresh_audit` 行数不变、项目锁函数调用 0 次。核查：`test_runtime_freeze_gate.py`（TestClient；锁函数为下一层 spy；含 `formula_id` 不是 UUID 的夹具）。
1.2 解冻只与 1.3~1.10 同批完成，不提供开关；解冻后同文件改为端点级正向用例：【测试】夹具经 `POST /api/workpapers/draft-refresh` 真实 apply，跨底稿目标 = 金标准、自引用 0 mutation、夹具其余单元格不变。核查：`test_runtime_freeze_gate.py`（不含任何「文件 / 常量存在」断言）。
1.3 目标身份取 `WpFormula` 已存稳定三元组；三元组为空的旧行才由 `stable_key` 推导；`stable_key_needs_review=true` ⇒ `blocked`「公式位置待复核」。引用从表达式解析（不依赖 `refs`），四种 WP 写法都识别：单元格两参、单元格三参经需求 1.9 的读取函数取值；列名两参、坏账明细三参作为外部取值经严格读取取值；取不到一律 `blocked` 并给中文原因，不按 0 代入；其余写法 `blocked`「引用写法无法识别」。核查：`test_runtime_typed_eval.py`（needs_review、空三元组、四种写法各一组取到 / 取不到夹具）。
1.4 环（含自引用）上的公式 `blocked`「循环引用」、不产生 mutation；单元格两参 `WP('X','B5')` 命中多个批内目标或存值在多个工作表 ⇒ `blocked`「引用有歧义」。核查：同上，13 条自引用 + 合成 A↔B 环 + 歧义夹具 0 mutation。
1.5 四方一致：Runtime 计划值、严格轨（= `evaluate_wp_formula_expression(..., wp_values=<严格读取结果>, strict_wp=True)`）、`GET /api/workpapers/{wp_id}/formulas` 预览值、apply 后业务表值对同一夹具逐值相等（表驱动，夹具覆盖四种 WP 写法）；默认（非严格）调用与严格轨的差异只允许是 `formula_wp_semantics.py` 已登记的维度。核查：`test_runtime_four_way_parity.py` + 既有 `tests/test_formula_wp_semantics.py`。
1.6 年度契约：读取函数收到 year 时与项目年度比较 —— 项目年度为空 ⇒ `blocked`「项目未设置审计年度」；不等 ⇒ `missing`「底稿年度与项目年度不符」；`audit_period_end` 为空、`audit_year=2025`、year=2025 ⇒ 正常取值；同一 `wp_index` 下多于一条未删 `working_paper` ⇒ `blocked`「底稿记录有歧义」。真库守卫：有试算表的活项目年度全部可解析，为空即列出项目。核查：`test_wp_executor_project_year_contract.py`（真 PG：回滚事务内【测试】项目三种年度夹具 + 一对多夹具 + 守卫）。
1.7 TB/NOTE/REPORT 引用各一条，期望值为金标准（TB 取叶子 `audited_amount` 之和）。核查：`test_runtime_typed_eval.py::test_non_wp_refs_against_gold`（真 PG）。
1.8 写入前目标校验与 adapter 真形状：workpaper 目标工作表不存在 ⇒ 计划阶段 `blocked`，任何路径不得新建工作表；目标单元格在现有数据范围（`max_row/max_col`，F57）之外照常写入并扩展数据范围；report adapter 接受 F41 的六个 PG 枚举值、拒绝短码；note adapter 读写 `rows[].values` 形状。核查：`test_runtime_adapter_pg_shapes.py`（真 PG 回滚事务：六枚举各一行 + 一张 `rows[].values` 附注表，before 读取零拒读、apply 后值正确）+ `test_runtime_typed_eval.py::test_missing_target_sheet_blocked`、`::test_write_beyond_extent_allowed`。
1.9 WP 单元格读取单一实现：Runtime、严格轨、`WPExecutor` 的单元格分支（两参归本 spec，三参 A1 由 ACNR spec 接线）、预览只调用同一个读取函数，契约见 design §8.2（与 ACNR spec 共用，先落地方提交契约测试）；按（项目, 年度, 底稿, 工作表, A1）精确读，取不到返回 `missing` / `blocked` 与原因而非 0；`WPExecutor` 两参既有取值行为不变（唯一变化：同一 `wp_index` 多条底稿记录时由「任取一条」改为 0，现网 0 例）。核查：`tests/test_wp_cell_reader_contract.py`（可按位置调用、ACNR 依赖字段齐全、三种状态、可接受键并集、数据库异常上抛）+ `test_wp_cell_reader.py`（同一底稿两表同 A1 不同值各取各的）+ `test_wp_cell_reader_single_source.py`（AST：`WPExecutor.execute`、`typed_eval`、`wp_ref_strict`、`evaluate_wp_formula_expression`、预览函数体内不得调用 `extract_custom_cells` 或访问 `html_data`）+ 既有 `tests/test_formula_wp_semantics.py`。
1.10 29 行重放：回滚事务内把 F2 的 29 条 `wp_formula` 及其底稿复制到【测试】项目（原行只读），调生产 `generate_mutation_plan` + apply：跨底稿 5 条 = 金标准；13 条自引用与 A↔B 环 `blocked`；11 条字面量值不变；2 条错 sheet 目标 `blocked` 且 `html_data` 键集合不变；未被成功写入的底稿 `parsed_data` 规范化 JSON 的 sha256 前后相等。核查：`test_runtime_replay_29_pg.py`（表驱动，29 行逐行断言）。

### 需求 2　中央执行与 L1 失败语义（P0-2，舍入默认 D4）

2.1 `/api/formula/execute`、`/batch-execute`、`/api/formula/debug` 按列名语义取值：`TB(code,'审定数')` = 叶子 `audited_amount` 之和、`TB(code,'未审数')` = 叶子 `unadjusted_amount` 之和（金标准）；夹具为华氏 1001 与 UAT 子公司（现值 100 / 0 / 1,200,000 只作记录）。核查：`test_central_execute_contract.py`（真 PG 只读）。
2.2 除零、`ROW` 缺行、未注册列名、参数个数不足（`IF` 非 3 参、`MAX`/`MIN` 少于 2 参、`ROUND()`、`AUX` 少于 2 参）：响应 200、`ok=false`、`value=null`、`errors` 非空、`state ∈ {blocked, error}`；科目在本项目年度试算表零命中 ⇒ `state=missing`「试算表无科目 9999」。核查：同上，参数化 9 例。
2.3 L1 `execute` 对上列情形与未知函数 `FormulaResult.ok=False` 且 `errors` 含中文原因（`value` 保持 `Decimal('0')` 供只读调用方，写入方须判 `ok`）。核查：`test_l1_failure_semantics.py`。
2.4 端点预检按表达式内全部函数调用名分类（分类规则见 design ADR-19）：`formula_type=TB` + `EVIL()` ⇒ 422 `FORMULA_FUNCTION_UNSUPPORTED`；`ROUND(TB('1001','审定数'),2)`、`IF(1>0,TB('1001','审定数'),0)`、`MAX(1,2)`、已注册自定义函数 ⇒ 200 且 `ok=true`。核查：`test_central_execute_contract.py::test_precheck_classification`（正反各 4 例）。
2.5 trace 与 value 来自同一次求值：`POST /api/report-config/execute-formula` 对 BS-002 返回 trace 各 `TB(...) = x` 之和等于 value。核查：`test_report_config_execute_trace.py`。
2.6 `ROUND` 统一 `ROUND_HALF_UP`：`ROUND(1.005,2)=1.01`、`ROUND(-1.005,2)=-1.01`，L1 与 `safe_eval_expr` 同口径。核查：`test_l1_failure_semantics.py::test_round_half_up`。
2.7 `POST /api/report-config/execute-formulas-batch` 不在同一 `AsyncSession` 上并发：真 PG 10 条独立公式全部返回数值。核查：`test_report_config_execute_trace.py::test_batch_serial`。
2.8 表间审核 `XR-07`（审定数 = 未审数 + ADJ + ADJ）在「审定 ≠ 未审」夹具上判出差异、一致夹具上通过。核查：`test_central_execute_contract.py::test_xr07_unadjusted_semantics`。
2.9 参数个数表只覆盖 L1 内置函数：其键集合 == 冻结常量 `BUILTIN_FUNCTION_NAMES`；注册自定义函数后该断言仍成立；自定义函数个数 = 注册时 `param_names` 长度。核查：`test_l1_failure_semantics.py::test_arity_keys`（先注册一个自定义函数再断言）。
2.10 变异：审定口径改回 `unadjusted_amount`、`error` 改回 `None`、除零返回 0、`未审数` 别名改回 `期末余额`、预检改回 `expression_functions`，对应测试必红。核查：tasks 变异表。

### 需求 3　Draft Refresh 只报真实结果（P0-3）

3.1 `report` 范围按项目真实准则、审定模式调用报表权威生成路径；【测试】项目 `financial_report` 逐行 before/after 与 `gold_report_evaluator` 金标准一致；试算表重算失败 ⇒ 本范围失败、试算表不变。核查：`test_draft_refresh_truthful.py`（真 PG 回滚事务）。
3.2 每个范围产出：金额变化数（规范化后 before≠after）、仅重算数（计算成功但金额未变；Runtime 中 before == after 的 mutation 计入此项且不下发写入方）、draft 标记数、失败清单、提交后待发事件；整体 `outcome` 与响应 `status` 按下表派生（「有效」= 金额变化 + 仅重算 + draft 标记 > 0）。核查：同上，表驱动 7 行各一夹具。

| 条件 | outcome | 响应 `status` |
|---|---|---|
| 金额变化 > 0，无失败 | applied | success |
| 金额变化 = 0、仅重算 > 0，无失败 | recomputed | recomputed |
| 金额变化 = 仅重算 = 0、draft 标记 > 0，无失败 | draft_marked | draft_marked |
| 三者均为 0，无失败 | no_effect | no_effect |
| 有失败且有效 > 0（`partial_success` 事务模式） | partial | partial_success |
| 有失败且有效 = 0，或 `all_or_nothing` 模式下任一失败 | failed | failed |
| 幂等命中 | 首次运行记录的 outcome | idempotent_hit |

3.3 计数：`applied_count` = 金额变化数，`recomputed_count`、`draft_marked_count` 分列，`affected_count = applied_count + recomputed_count`（无可执行写入方的范围为 0，对应 p1-10 P0-3 验收）；`failed` 时整体回滚、不留业务写入、不发事件；`success` 只用于 applied；幂等判定在取项目锁之后、任何范围执行之前，命中则 report 范围也不执行，返回首次的 outcome 与计数；`preset_application`、scope 留痕在 applied 下与改造前一致。核查：`test_draft_refresh_router_status.py`。
3.4 `trigger_recalc` / `mark_stale` 只在金额变化 > 0 时调用（`refresh()` 与 `execute_refresh` 两路径）：marker-only 后 `working_paper.prefill_stale` 计数不变。核查：`test_draft_refresh_truthful.py`。
3.5 报表范围的 `REPORT_ROW_CHANGED`（只含 before≠after 的行次）与 `REPORTS_UPDATED` 只在提交成功后、金额变化 > 0 时各投递一次；回滚或仅重算均不投递；`generate_all_reports` 的其余调用方（`routers/reports.py`、`chain_orchestrator`）的返回值结构与事件行为不变。核查：同上（事件总线 spy 只记录不替换）+ 两个调用方各一条回归用例。
3.6 冻结判定（需求 1.1）在取项目锁之前完成；`report` 范围的写入只在取锁之后发生。核查：`test_runtime_freeze_gate.py::test_lock_after_freeze`。
3.7 预设库归一后全量函数名 ⊆ L1 registry（`TB_SUM` 17→0），两条 `TB_AUX(` 预设表达式不变，`prefill_formula_mapping.json` 字节不变。核查：`test_preset_library_registered_functions.py`（含 sha256）。
3.8 前端：刷新响应解析器接受 3.2 表中 7 种 status（逐个单测，缺一即红）；对 `recomputed` / `draft_marked` / `no_effect` / `partial_success` / `failed` / `idempotent_hit` 显示中文说明，不显示「刷新成功」；已提交的刷新不再弹「刷新失败」。核查：`formulaRuntimeContract` 解析器 vitest + `GtRefreshScopeDialog` vitest。
3.9 变异：`report` 范围恢复交 Runtime、路由恢复 `no_effect→success`、报表生成忽略 `publish_events`，对应测试必红。核查：tasks 变异表。

### 需求 4　试算表取数统一叶子口径（P0-4 ②）

4.1 同一项目年度内，若存在以本码为前缀且更长的其他行，本行不计入；F8 列出的全部取数函数遵守。核查：`test_tb_leaf_codes.py`（纯函数 PBT max_examples=5 + 父子并存夹具表驱动全部取数函数 = 叶子和）。
4.2 `1231` 与 `1231-01/02` 并存时 `TB('1231','期末余额')` 只算一次；只有子科目时等于子科目和；医疗器械 BS-008 重算 = 金标准（现值 1,771,446,049.03 只作记录）。核查：`test_tb_leaf_codes.py` + `test_report_leaf_gold_pg.py`。
4.3 父行金额与叶子合计差 > 0.005 时，告警到达用户可见结果：中央 execute 与 debug 响应 `warnings`、报表行结果、推送运行结果都含科目码与差额；夹具父=100、子=40+50 ⇒ 值 90、warning 含「1231」与「10.00」。核查：`test_tb_leaf_warning_propagation.py`（端点 + 报表行 + 推送三处，不接受只测纯函数）。
4.4 推送取数：全部活项目 × 推送规则引用的科目码，`load_tb_audited` = 测试内独立 SQL 叶子和；另有合成父子并存夹具（父行金额 ≠ 叶子和）保证断言非空转；「前缀和 ≠ 叶子和」的项目与科目只输出报告，不作红灯判据。核查：`test_formula_push_leaf_invariant_pg.py`。

### 需求 5　报表计算版本、三路统一与 false-fresh = 0（P0-4 ①④）

5.1 报表行「是否过期」= 已标过期，或计算版本不是当前版本，或（逐行读者）生成时公式文本与当前生效公式规范化后不同。报表定义经全局发布、项目适配保存、恢复全局三个出口写入后，同一事务内把有效定义真正变化的行、以及经 `ROW` / `SUM_ROW` 直接或间接引用它们的行，在该项目全部年度标过期：跟随全局的项目被标，有本项目覆盖、模板订阅或 pinned 使有效定义不变的项目不标。版本号大于 V205 的迁移文件若改写 `report_config.formula`，同一文件必须把报表行标过期。核查：`test_report_freshness.py` + `test_report_config_writer_marks_stale.py`（三出口 × follow / override / pinned / template 四类项目 + 「BS-002 变化 ⇒ 引用它的合计行同事务标过期」）+ `test_report_config_sql_migration_marks_stale.py`（静态，带违规样本自检）。
5.2 全量生成、affected 重算、stale 重算三路调用同一逐行计算：失败不写 0、保留旧值并标过期、计算失败原因可读（与口径性留空 `blank_reason` 分开显示；首次生成即失败的新行金额为空）；缺科目 ⇒ 0、状态正常、trace 注明；合法 0 不被替换（只产生 warning）；失败、过期或计算版本不是当前版本的行不作为其他行的输入 —— 引用它的行失败「引用行未就绪」并保持过期。核查：`test_report_three_path_parity.py`（含「A 失败 ⇒ 合计 T 失败且过期」三路一致用例）。
5.3 `regenerate_affected(changed_accounts=['1231-02'])` 命中引用 `TB('1231')` 的行；未传准则时按项目真实准则。核查：同上。
5.4 真 PG 守卫：活项目全部有公式报表行，读取侧判「未过期」的行与独立叶子金标准差 ≤0.005；正例：回滚事务内新建【测试】项目，复制医疗器械 2025 试算表全部行（含 `1231` 与其子科目），准则与医疗器械相同，不重算试算表直接重新生成报表后「未过期」行数 > 0、至少 1 行引用父子并存科目、且全部等于金标准。金标准求值器只读原始 SQL 行与公式文本，不 import 生产报表、取数、叶子、逐行计算模块；未识别语法数 = 0；生产叶子函数改为返回全部行时该守卫必红。核查：`test_report_false_fresh_guard_pg.py` + `test_gold_evaluator_independence.py`（AST import 黑名单）。
5.5 不重新生成真实项目报表（决策项 X3）；计算版本为空的存量行读取侧判过期（D13 默认 A）。核查：`test_report_freshness.py::test_legacy_rows_read_as_stale`。

### 需求 6　利润表归属行定义与合计行守卫（P0-4 ③，默认 D3、D14）

6.1 国企两套：IS-074 = IS-048 + IS-054；合并 IS-075 = IS-049 + IS-072；单体 IS-075 无公式。上市两套：IS-051 = IS-029 + IS-032；合并 IS-052 = IS-030 + IS-049；单体 IS-052 无公式（本条为这些公式的唯一权威文本）。核查：`test_report_seed_attribution_rows.py`（按行名定位）。
6.2 定义变更经 V199 同步内核写入；产生跨合计行 `SUM_ROW` 的写入路径定位后加守卫。核查：同上 + 生成器单测。
6.3 守卫：`is_total_row` 行的 `SUM_ROW` 区间不含另一合计行（现存违规棘轮只许减少）；`ROW`/`SUM_ROW` 前向、跨表、悬空 = 0（冻结）。核查：`test_report_total_row_range_guard.py`、`test_report_row_ref_order_guard.py`。
6.4 合计行组成行无公式时结果带 warning「组成行 IS-048、IS-054 未定义公式」。核查：`test_report_three_path_parity.py::test_formula_less_component_warning`。
6.5 回滚事务内给【测试】项目组成行写字面量后重算，IS-074、IS-075 与测试内按行名独立求和一致。核查：`test_report_seed_attribution_rows.py::test_test_project_recalc`（真 PG）。
6.6 存量升级（决策项 X2）：正式工具默认只读列出 8 行旧值与目标值；`--apply` 只在旧值精确等于已知坏式时更新、经同步内核发布、可重复执行（第二次 0 变更）、不重算报表（受影响行按 5.1 标过期）；本 spec 只在回滚事务内验证 `--apply`，不对真库执行。真库守卫：8 行每行要么已是目标定义、要么精确等于已知坏式（待升级，守卫输出清单），出现第三种定义即红。核查：`test_report_seed_upgrade_tool.py`（回滚事务：dry-run 不写、apply 后 8/8、第二次 0 变更、旧值不符跳过）+ `test_report_attribution_rows_live_pg.py`。

### 需求 7　附件溯源项目隔离与发布记录可见性（P0-5、P2-5）

7.1 `attachment_lineage` 增加可空列 `project_id`（迁移 V{n}，由 `attachments.project_id` 回填；可空以兼容 X1 的「先迁移、后推送代码」顺序）：迁移不删任何行、不因孤儿失败；无法归属的行（附件已不存在）与迁移后旧代码写入的行 `project_id` 为空，对任何项目都不可见；新代码写入一律带 `project_id`。代码运行时该列不存在（迁移未执行或失败）⇒ 附件三端点与溯源附件子源返回 503「附件溯源迁移未完成」。另有默认只读的修复工具逐行列出孤儿与未回填行，`--apply` 先备份再回填可归属的行、删除孤儿。迁移在快照库上由 MigrationRunner 执行验证，应用到共享库为决策项 X1。核查：`test_attachment_lineage_migration_pg.py`（回滚事务内删列、造 1 条孤儿与 1 条正常行后执行迁移 SQL ⇒ 不报错、正常行已回填、孤儿为空且原行仍在、索引存在；空值行不出现在任何项目的查询结果）+ `test_attachment_lineage_column_missing.py`（列缺失 ⇒ 三端点与子源 503）+ `test_attachment_lineage_repair_tool.py`。
7.2 查询限本项目、附件未软删、`object_id` 字面匹配（`%`、`_`、`\` 不作通配）；`note_cell` 对应附件 `note_section`。双项目同 `target_ref`：A 的成员只拿到 A，B 的 id 不出现在响应任何字段。核查：`test_attachment_lineage_isolation_pg.py`（TestClient + 真实鉴权链）。
7.3 附件三端点：关联与删除关联要求附件所属项目 edit，查询要求 readonly；拒绝时 `attachment_lineage` 行不变。核查：配方表 `test_formula_hub_endpoint_authz.py`。
7.4 `GET /api/formula-settings/publishes` 对非 admin：已发布全局记录可见；全局候选仅提交人或对源项目有权限者可见；项目间应用仅源项目或目标项目与本人项目有交集时可见且他项目信息裁掉；模板记录按模板可见性；过滤不造成空页：存在可见记录时第一页非空、按时间倒序。核查：配方表（含「非成员看不到他项目候选 note」「changed_projects 不含无权项目」「最近 limit 条全不可见时仍返回其后的可见记录」）。

### 需求 8　待确认事项修订号与决策键（P0-6、P2-6）

8.1 `formula_sync_item` 增加修订号（迁移 V{n+1}）：新建为 1，每次覆盖待确认项原子递增，三种来源一律携带并在列表输出。两个独立会话并发覆盖同一待确认项：两次返回修订号集合为 {2,3}、最终为 3；并发新建：{1,2}、最终 2，且不抛唯一约束错误。核查：`test_pending_revision.py` + `test_pending_revision_concurrency_pg.py`（快照库内两个独立会话真提交、屏障同时起跑、用后删除）。
8.2 处理待确认项：缺修订号 428；不等 409，目标定义不变；F14 三步回归第 3 步必 409。核查：`test_pending_revision.py`（生产函数不 mock）。
8.3 前端待确认弹窗回传修订号；409 提示刷新并重新拉取。核查：`FormulaPendingSyncDialog.spec.ts`。
8.4 两个域同名 slot 的冲突决策分别设置、各自生效；旧格式决策仍被识别。核查：`test_decision_key_domain.py`。

### 需求 9　UnifiedLineage 签名与部分错误可见（P1-1）

9.1 按对象类型选择溯源来源并传入正确标识；和平药房 `wp_cell D2` 上游条数 = 测试内直接调用 `trace_upstream` 的结果；`tb_row`、`adjustment` 两类返回空来源且 `partial=false`，附件按请求的对象类型原值精确匹配。核查：`test_unified_lineage_contract_pg.py`。
9.2 子源失败互不影响：`partial=true` + `errors[{source, message}]`（中文），其余子源照常。核查：同上（`note_wp_mapping` 不存在场景）。
9.3 单测不得 patch 掉被测 wrapper 调用的真实函数；守卫用 `inspect.signature` 断言实参个数与被调函数一致。核查：`test_unified_lineage_signature_guard.py`。

### 需求 10　公式时间轴真实字段与「不可用」标记（P1-2）

10.1 五类来源各用真实字段；真 ORM 行各造 1 条，返回 5 类各 1 条。核查：`test_formula_timeline_pg.py`。
10.2 任一来源失败：`unavailable_sources[{source, message}]` 列出，其余照常。核查：同上。
10.3 医疗器械只读复核 `total ≥ 1`。核查：同上。

### 需求 11　公式审计日志：年度与人工补记（P1-3 的公式域入口；哈希链加固移交 S10）

11.1 `formula.changed` 载荷含 `year`；按年度查询只返回本年度条目，无年度的旧条目单列 `legacy_without_year`。核查：`test_formula_audit_log_year.py`。
11.2 客户端提交端点只收「人工补记」备注（≤500 字），记为 `action="manual_note"`；提交 `old_formula/new_formula/result_value/trace` 一律 422。核查：同上 + 配方表。
11.3 本 spec 不改审计日志写入语义：`audit_log_helper.py`、`workers/audit_log_writer_worker.py`、`routers/audit_logs.py` 在最终提交中 0 改动。核查：发布验收清单 `git diff --stat` 记录。

### 需求 12　服务端统一 validator 与资源预算（P1-8 前半）

12.1 全局发布、项目适配保存、模板发布、项目间应用、历史回滚、`report_config` 直写端点写入前按域校验（各域语法以本域求值器为准，均加长度 ≤4000 与嵌套 ≤50）。report（项目层 + 全局）、tb_detail、cross_check：`EVIL(((`、`TB('1001'`、`PRIOR(...)`、`1/0`、`1/(2-2)` 均 422，`1/TB('1001','审定数')` 正常保存；附注 / 合并附注本域坏式（`cell(1,` 不闭合、未知函数）422、`PRIOR(...)`、`cell(1,2)` 正常；底稿 `Sheet!B5` 正常。核查：`test_formula_definition_validator.py`（域 × 写入入口参数化）。
12.2 守卫：AST 扫描 `ReportConfig.formula` 与 `FormulaSetting.definition` 全部写入点，每个都经 validator 或在豁免表写明理由（豁免表配「条目真实存在」反向断言）。核查：`test_formula_writer_validator_guard.py`。
12.3 执行预算：单条 execute、debug、`report-config/execute-formula` 每请求一个时限；`batch-execute` 与 `report-config/execute-formulas-batch` 整批一个时限；任一数据库语句超时或整体超时 ⇒ 504 `FORMULA_TIMEOUT`、不返回部分结果，之后同一会话可继续查询；`batch-execute` 超过 200 条、`execute-formulas-batch` 超过 1000 条 ⇒ 422；表达式 AST 节点 > 2000 或深度 > 50 在求值前报错。核查：`test_formula_execute_budget.py`（四类端点各一个慢 resolver 用例 + 真 PG `pg_sleep` 慢语句用例 + 超大表达式用例）。

### 需求 13　回滚取服务端快照、删除强制 CAS（P1-8 后半、P2-5、P3-2）

13.1 历史回滚请求体只收 `source_log_id` + `expected_version`；目标定义由服务端从该历史条目读取，写为本项目新版本并留痕 `action=rollback`；带 `target_formula` 一律 422；缺版本 428、不符 409。权限维持现状：admin，或合伙人 / 经理且为本项目 review 以上成员；质控 / EQCR / 审计员拒绝。核查：`test_formula_rollback_snapshot.py` + 配方表。
13.2 新变更条目存完整变更前/后定义，含 cross_check 在内可回滚；旧条目只有显示字符串时仅报表域可回滚，其余域判不可回滚并给原因。核查：同上。
13.3 历史列表每条带服务端计算的 `rollbackable` 与 `rollback_blocked_reason`；前端只对 `rollbackable=true` 显示回滚按钮，删除写死的 `specAReady=false`。核查：同上 + `FormulaHistoryTab.spec.ts`。
13.4 F22 三个删除端点均要求 `expected_version`（overrides 为与 `slot_key` 等长、按序配对的列表），缺 428、不符 409、业务行不变。核查：`test_formula_delete_cas.py`。
13.5 前端三个删除入口回传当前版本，409/428 显示中文原因并刷新。核查：对应 vitest。

### 需求 14　自定义函数递归 fail-closed、依赖解析双引号（P2-8、P2-7）

14.1 注册接收名称、表达式、说明、参数名列表，名称统一大写；自引用或与已注册自定义函数成环 ⇒ 400（中文原因）；`POST /api/formula/custom-functions` 带 `param_names` 正常注册（不再 500）。核查：`test_custom_function_cycle.py`。
14.2 执行时内层结果有错误或 blocked，外层 `ok=False` 并带内层原因；嵌套超过上限报错而非返回 0。核查：同上。
14.3 9 个引用解析函数同时认单、双引号；两种写法 `upstream_refs`、`references()` 结果相等。核查：`test_formula_dependencies_quotes.py`。

### 需求 15　低成本止血（P2-3、P2-2、P1-5 / P3-1 止血）

15.1 `GtFormulaPresetDialog` 默认只读；未绑定 `@edit-formula` 的宿主不显示「编辑 / 新建」；成功提示只由宿主在真实保存成功后给出。核查：挂载守卫 vitest。
15.2 wp / note / consol_note / push 的「应用范围」入口禁用并显示「本域暂不支持推广到其他项目或全局」，保存后不弹选择框。核查：前端契约测试枚举 7 个域。
15.3 `FormulaManagerDialog` 新增报表行、「保存全部」的新增报表行与底稿公式写入、`FormulaHistoryTab` 历史加载与回滚按状态码判成功；失败时不改界面、不提示成功、不计入「已保存 N 个」；历史加载失败显示「加载失败」。核查：vitest 注入 409/422/428/500。
15.4 保存 tb_detail 不改任何 `working_paper.prefill_stale`；`/api/formula-settings/domains` 的 `wired` = 生产代码是否调用该域的有效定义读取入口（入口清单写死在 `formula_settings/consumers.py`，通用 `effective_slots` 不计）；tb_detail 无读者时为 `false` 并附中文说明。核查：`test_tb_detail_stop_bleeding.py` + `test_wired_domains_derived.py`（变异「给 tb_detail 加假读者」必红）。

### 需求 16　一致性门禁：五态、口径识别与可控阻断（P1-11，默认 D1、D2）

16.1 试算平衡检查按负债合计符号识别口径（负 ⇒ 借正贷负；正 ⇒ v2 正数；为 0 时按权益判；两者都为 0 ⇒ 未执行「口径无法识别」）；差额覆盖资产、负债、权益、收入、费用五类（各类先取叶子），借正贷负给出告警；不改试算表数据。核查：`test_tb_balance_sign_convention.py`（借正贷负 / v2 × 已结转 / 未结转 4 个夹具 + v2 资不抵债夹具）+ 医疗器械、华氏真 PG 只读：生产差额 = 独立 SQL 差额；|差额| > 容差时该项 `failed` 且 details 含五类叶子合计。
16.2 每个检查项有 `status ∈ {passed, failed, not_executed, not_applicable, error}`、`reason` 与稳定的分支编号：数据缺失 / 未保存 / 部分数据 ⇒ not_executed；结构性不可用（在线表单模式数据不在本检查读取的结构内、底稿已裁剪）⇒ not_applicable；检查异常（含取数辅助函数中的数据库异常）⇒ error，且一项检查的 SQL 失败不影响其余检查的结果。全部非通过出口登记在一张分支清单中，与源码出口一一对应，每个出口由参数化夹具实际触发并断言产出该分支编号；异常处理块中不得出现「通过」。核查：`test_consistency_gate_branches.py`（清单双射 AST + 参数化每分支）+ `test_consistency_gate_status.py`（AST：`_models` 之外直接构造 `CheckItem(` = 0、`except` 块内调用「通过」工厂 = 0；真 PG：第一个检查方法注入 SQL 错误 ⇒ 该方法产出 error、其余 15 个检查方法的结果与未注入时相同）。
16.3 逐分支变异：把任一登记分支改为「通过」，对应参数化用例必红；全部登记分支跑完。核查：`_tmp_formula_hub/probes/mutate_gate_branches.py` 输出「N/N 打红」（N = 清单条数）。
16.4 阻断由设置 `CONSISTENCY_GATE_ENFORCEMENT ∈ {observe, enforce}` 控制，默认 observe：observe 下每个消费方的阻断结果与改造前的实际效果相同 —— 签发 / 导出包门禁规则不阻断，改为给出 warning 级提示「有 N 项未通过或未执行（当前为只提示模式）」；导出包服务按改造前口径拒绝（只看阻断级比较失败；改造前跳过与异常出口都记为通过，F63）；enforce 下阻断级 failed / not_executed / error 阻断签发与导出包并提示「请补齐数据后重新检查」；not_applicable 在任何模式下都不阻断。F51 的全部消费方（实施时现扫补全）读同一判定函数，年度一律取项目年度。核查：`test_consistency_gate_enforcement.py`（端点级用例：`GET /api/projects/{pid}/sign-readiness` 经门禁引擎 sign_off 触达 `ConsistencyPassedRule`、`POST /api/projects/{pid}/workflow/export-package` 经 `export_package_service`，observe / enforce 各一组）+ 消费方 AST 守卫 + 16.6 的差分。
16.5 前端门禁面板与展示端点（consistency-check、看板、热力图）按五态显示：「未执行（数据缺失）」「不适用」「检查异常」各有标签与原因，不显示「通过」；`ConsistencyGatePanel` 不再自补「通过」。核查：vitest + 三个展示端点的响应快照。
16.6 收尾在快照库上对全部活项目只读运行门禁（每项目一个只读事务）：①候选代码产出「若开启阻断会被卡住的项目与检查项」清单（决策项 X4）；②基线代码与候选代码（observe）的导出包判定逐项目比较，差异只允许来自 16.1 的口径修正且逐项列出，其余差异数必须为 0。核查：发布验收清单记录（项目数、已运行数、无年度未运行数、enforce 下被卡住项目数、按检查项计数、差分数）。

### 需求 17　门禁与证据纪律（贯穿）

17.1 每个 P0 至少 1 条真 PG 测试 + 1 条磁盘变异（变异后对应测试红、恢复后逐字节一致）。核查：tasks 变异表。
17.2 端点权限配方表覆盖本 spec 改变权限、所有权或请求/响应合同的全部端点（design §10.3 逐条列绝对路由）；身份 = 未登录 / 非成员 / readonly / 审计员（edit）/ 经理（edit）/ 质控（review）/ EQCR（review）/ 合伙人 / admin；放行者成功、拒绝者 401/403 且业务表不变；对账：配方表涉及的每个路由模块内全部路由要么在配方表、要么在 `_UNCHANGED_ROUTES` 豁免表（豁免条目须真实存在），未登记即红。核查：`test_formula_hub_endpoint_authz.py`。
17.3 本 spec 新增真 PG 测试与金标准求值器中的 SQL：语句出现 `projects`（FROM / JOIN）即须同一语句含 `is_deleted = false` 或 `NOT <别名>.is_deleted`。核查：`test_pg_sql_excludes_soft_deleted.py`（扫描 `tests/formula_hub/*_pg.py` 与 `gold_report_evaluator.py` 中的 SQL 字符串，带违规样本自检）。
17.4 完成判定：PG 预检通过后，以子进程环境同时设 `DATABASE_URL`（快照库）、`GT_REQUIRE_PG=1` 与隔离的 `REDIS_URL` 单独运行本 spec 全部 `pg_only` 用例，selected / passed / skipped 由 junit 结果统计，skipped 必须为 0；在实施 worktree 检出最终提交的 tree 跑全部后端用例与相关 vitest；最终单个提交的 tree 与验收时的 tree 相同。PG 不可用 ⇒ spec 保持未完成；只有浏览器实测可按外部环境保持 `[ ]*`，其余任务不得改标星。核查：tasks 发布验收清单记录。
17.5 交接：design §8.1 的 S1~S10 在本 spec 归档前均已有带负责范围的 spec 目录（至少 requirements.md）并登记 INDEX；§4.2 决策项逐条附验证证据交给用户；design §8.2 的「需 ACNR spec 同步采用」清单交给用户转达。核查：发布验收清单记录。

## 3. 非功能需求

- 性能：两个 worktree（基线 / 候选）连同一个快照库，各预热一轮后按 A-B-B-A 交替各跑 10 次 `_tmp_formula_hub/probes/bench_central_execute.py`；判据中央 execute `median_after ≤ 1.5 × median_before`，和平药房回滚事务内报表全量生成 `≤ 1.3 ×`；另记录现网最大一次表间审核批量的耗时；记录 CPU、Python 版本、PG 版本。
- 兼容：响应字段只增不减（`value` 失败为 `null` 是语义修正，实施时 grep 前端调用方）。
- 中文化：新增用户可见文本全部中文（错误码保留英文）。
- 行数门：遵守 F32；超限文件先抽伴生模块，禁止靠扩白名单；`report_config.py` 降到 800 行以内不登记；`consistency_gate/_impl.py` 以 HEAD 真实行数首次登记后只许减少。
- 不新增第三方依赖；新代码不引入日历年兜底；修掉的年度兜底与鉴权缺口在同一提交里按 design §8.3 调整对应棘轮。

## 4. 默认决策与决策项

### 4.1 默认采用，待用户确认

| D | 事项 | 本 spec 采用的默认（report.md §10 推荐） | 用户若改选的影响 |
|---|---|---|---|
| D1 | 试算表符号口径（F30） | 检查识别口径并告警，不改试算表数据；修数据另立 spec | — |
| D2 | 门禁缺数（F29、F51、F52） | 五态可见；默认只提示（observe），阻断由设置项开启（决策项 X4，附影响清单）；签字人逐项确认留痕归 S2 | 直接开启阻断：被清单列出的项目立即无法签发 / 导出 |
| D3 | 利润表归属行 | 归母 = 归母净利润 + 归母其他综合收益；少数股东 = 少数股东损益 + 少数股东其他综合收益（仅合并）；种子与生成器在本 spec 改，存量 8 行升级为决策项 X2 | 不升级 ⇒ 存量项目归属行仍为旧定义 |
| D4 | 金额舍入 | `ROUND_HALF_UP`，各执行轨共用 | 保留银行家舍入：需求 2.6 改为界面声明 |
| D5 | 软删项目数据 | 不删；统计与守卫排除 | — |
| D6 | 真实项目报表重算 | 只在【测试】项目验证；真实项目由用户决定（X3） | — |
| D7 | tb_detail 定位 | 「试算取数公式预览」，只止血 | — |
| D8 | Runtime 冻结方式 | 服务端直接拒绝，无开关 | — |
| D9 | 附件项目归属 | 迁移补 `project_id` 并回填，孤儿 fail-closed | 改 join 反查则少一个迁移 |
| D10 | 冲突默认行为 | ask + 保留本地；旧修订号禁采用 | — |
| D11 | 审计日志强度 | 移交 S10（本 spec 不涉及） | — |
| D12 | 自定义函数去留 | 只做递归 fail-closed；无客户场景则退役待用户决定 | 退役则端点改 410 |
| D13 | 存量报表行无计算版本 | A：读取侧全部判过期，由用户逐项目重新生成 | B：回填工具（默认 dry-run）只回填存值 = 金标准的行，增 1 任务 |
| D14 | 利润表净利润以下行无公式（F34） | 本 spec 只让「组成行未定义」以 warning 可见，补全归 S9 | 本 spec 内补全增 1 任务 |
| D15 | 审计链已有分叉（F44） | 移交 S10（本 spec 不涉及） | — |

### 4.2 决策项（本次不执行，交付时附验证证据）

| X | 动作 | 本 spec 内的验证 | 执行方式与影响 |
|---|---|---|---|
| X1 | 迁移 V{n}~V{n+2} 应用到共享库，并推送单个提交 | 快照库上由 MigrationRunner 执行迁移 + 全部真 PG 用例 | 顺序固定：①对共享库执行 `MigrationRunner(...).run_pending()`（与启动同一路径）②fetch，远端已前移则在 worktree 内 cherry-pick 并重跑验收 ③推送。反序（先推送）会让同步该分支的工作树在迁移前读写 `financial_report` / `formula_sync_item` 报列不存在；先迁移对旧代码无影响（新列可空或有默认值）。有附件孤儿时 V{n} 失败，需先运行修复工具 |
| X2 | 存量 8 行归属行公式升级 | 工具在回滚事务内 dry-run / apply / 重放 | X1 之后运行 `republish_report_seed_rows.py --apply`；只改全局报表定义，受影响行标过期 |
| X3 | 真实项目报表重新生成 | 快照库内【测试】项目复制数据后重新生成 | X1 之后逐项目在报表页重新生成；D13-A 下存量行在此之前一律显示过期 |
| X4 | 一致性门禁切到 enforce | 需求 16.6 的影响清单与差分 | X1 之后设 `CONSISTENCY_GATE_ENFORCEMENT=enforce` 并重启；清单中的项目随即无法签发 / 导出 |
| X5 | D1~D15 默认值确认 | — | 改选按 §4.1 影响列调整 |

## 5. 范围外

- 不改：tb_detail 产品定位、预设停用语义、附注权威源、模板共享范围、全局发布审批流程。
- 不改审计日志写入语义与哈希链（锁、可重放哈希、链尾、分叉确认、worker 隔离、非公式域调用方吞异常），归 S10。
- 不改 ACNR 目录生成器、`global_catalog.json`、高级查询 DSL、acnr_targets 接线、`exact_identity`、`WPExecutor` 三参 A1 分支与三参预载（归 `acnr-foundation-defect-closure`，它与本 spec 共用 design §8.2 的读取契约）。
- 中期事项与 p1-00 旧边界中延期的项（design §8）：全域 grammar/resolver 迁移（含 wp 全轨读 effective 与 S5 旧保存路径）、writer ownership 与 stale 状态机、durable outbox、provenance envelope、模板双项目试点与订阅按钮权限、consol_note scope 与角色、附注执行器只回写 auto_calc、校对目录执行状态、利润表下半段公式、Playwright 接入 CI、试算平衡表手工值读回。
- 不处理：`procedure-trim-generation-delegation-chain` 下落、S-cycle 文件、`note_writer.legacy_value_keys`、全平台年度兜底（归 `audit-year-calendar-fallback-ratchet`，本 spec 只改自己触及的文件）。
