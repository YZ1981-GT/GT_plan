# 公式管理平台全面审计：事实基线与调查地图

> 调查日期：2026-10-25。工作区：`d:\GT_plan`。本步严格只读；未运行会写缓存/快照的测试，未修改生产代码、配置、数据库业务数据、spec 或 Git 状态。唯一新增文件就是本调查产物。CodeGraph 可用且已优先使用（索引 15,780 文件、360,910 节点、548,930 边），随后以生产源码、路由注册和 live OpenAPI 精确确认。注释、docstring、spec 只作线索或“历史声称”，不作实现成立证据。

## 1. Git 事实基线

以下是创建本产物前捕获的 Git 自身输出；执行器的虚拟环境提示和 RTK 提示不属于 Git 输出，未混入代码块。

`git status --short --branch --untracked-files=all`
```text
## spec/disclosure-note-doc-upload-and-batch-fill...origin/spec/disclosure-note-doc-upload-and-batch-fill
 M .kiro/specs/INDEX.md
 M audit-platform/frontend/src/components.d.ts
?? .agents/tasks/s-cycle-investigation/findings.md
?? .agents/tasks/s-cycle-investigation/formula-impact-analysis.md
?? .agents/tasks/s-cycle-investigation/s-cycle-spec-review.json
?? .agents/tasks/s-cycle-investigation/s-cycle-spec-review.md
?? .kiro/specs/s-cycle-linkage-trimming-and-component-wiring/design.md
?? .kiro/specs/s-cycle-linkage-trimming-and-component-wiring/requirements.md
?? .kiro/specs/s-cycle-linkage-trimming-and-component-wiring/tasks.md
```

`git branch --show-current`
```text
spec/disclosure-note-doc-upload-and-batch-fill
```

`git rev-parse HEAD`
```text
779d8b43619c5946c198e11ca35b1ad9330c5dfa
```

`git log --oneline -5`
```text
779d8b436 (HEAD -> spec/disclosure-note-doc-upload-and-batch-fill, origin/spec/disclosure-note-doc-upload-and-batch-fill) fix(workpaper-sync): 在线编辑回表单无死路 + OO↔HTML 回写提速（oo-return-to-form-dead-end-and-save-speed R1~R5）
b273be750 docs(spec): formula-fetch-followup 7.3 补记合并树全量回归结果（新增 0、消除 1）
436fe2e98 fix(formula-fetch): 7.1/7.2 收尾 —— NOTE 取数唯一实现、悬空提示写明原因、锚点同步工具（formula-fetch-followup 7.1~7.3）
01ed968ec docs(spec): consol-note-header-library 批 9b-2 记录推送与主工作树对齐（task 58 收口、62 新增）
07bbbc4e1 fix(note): 两版单体附注模板按底稿披露表改结构并全链路收口；复位 Word 同步改坏的 15 处表名；删 30 条错数/无源推送规则（consol-note-header-library R8.4 批 9b-2）
```

### 1.1 四种状态必须分开

| 状态 | 本步事实 | 后续使用规则 |
|---|---|---|
| HEAD 已提交代码 | 以 `779d8b43619c5946c198e11ca35b1ad9330c5dfa` 为提交基线；生产源码定位均来自当前磁盘，但只有不在上方 status 清单内的路径可暂按“已在库”处理 | 后续必须用 `git show HEAD:<path>` 或干净 worktree 再确认关键结论，不能把当前磁盘一概当 HEAD |
| 当前未提交改动 | 上方 2 个 modified + 7 个 untracked 是创建本产物前的完整清单 | `INDEX.md`、`components.d.ts` 以及 S-cycle 调查/spec 内容均标为“来自未提交改动，不算已在库”；本报告不以它们证明公式实现 |
| 历史 spec 声称 | 仅记录 tasks/INDEX 的勾选、进度和文字证据 | 不等于代码入库、不等于测试当前仍绿、不等于运行时可达 |
| 实际运行 | `GET http://127.0.0.1:9980/api/health` 返回 HTTP 200、`status=healthy`、Postgres/Redis `ok`、`migration.applied_count=203`、失败迁移 0、schema drift 0、startup 38 项 complete；`http://127.0.0.1:3030/` 返回 HTTP 200 | 只证明采样时服务健康；不能证明运行进程精确对应 HEAD，也不能证明具体公式业务行为正确 |

### 1.2 live 路由与迁移快照

- live `/openapi.json` 已出现主要路由族：`/api/formula/*`、`/api/formula-settings/*`、`/api/projects/{project_id}/formula-settings/*`、`/api/formula-templates/*`、`/api/projects/{project_id}/formula-templates/*`、`/api/projects/{project_id}/formula-catalog*`、`/api/formula-catalog/check-rules`、`/api/projects/{project_id}/formula-push/*`、`/api/formula-audit-log/*`、`/api/address-registry*`、`/api/projects/{project_id}/lineage`、`/api/projects/{project_id}/stale-summary*`、附注/合并附注/底稿公式端点。该证据只证明路由已注册。
- 仓库迁移扫描：`backend/migrations` 有 203 个 `V*.sql`，最高 `V205`；live health 报 applied_count 203。启动报告同时显示本 worker 的 `run_migrations` 因 `GT_BOOTSTRAP_DONE=1` 被跳过，因此后续仍要逐 migration checksum/表列核验，不能仅凭计数判一致。

## 2. 调查地图：从入口到事实验证

1. 用户入口：`audit-platform/frontend/src/layouts/ThreeColumnLayout.vue` 是全局 `FormulaManagerDialog` 挂载点；`audit-platform/frontend/src/components/formula/FormulaManagerDialog.vue` 汇聚报表、TB 明细、表间审核、底稿、附注、合并、推送、历史、时间线、依赖面板。
2. 前端请求单一定位：`audit-platform/frontend/src/services/apiPaths/formula.ts`（运行、底稿、附注、推送、健康、调试、时间线）与 `audit-platform/frontend/src/services/apiPaths/formulaSettings.ts`（全局、项目适配、冲突、模板、订阅）；调用封装 `audit-platform/frontend/src/services/formulaSettingsApi.ts`。
3. 后端注册：`backend/app/router_registry/report.py` 注册 `tb_detail_formulas`、`formula_logic_check`、`formula_push`、`formula_settings`、`formula_templates`、`formula_catalog`；`backend/app/router_registry/workpaper.py` 注册 `formula`、`wp_formula`、`wp_user_formulas*`、`formula_scope_query`；`backend/app/router_registry/system.py` 注册 formula audit/health/debug/timeline、address registry、consol note formulas、linkage。
4. 执行与传播：L1 求值 `formula_engine.py` → 严格引用预载 `formula_ref_preload.py` / 数据预载 → 域适配或 `formula_runtime` 生成 mutation plan → router 统一 commit → `EventBus`/outbox → stale、recalc、push、SSE。
5. 治理与模板：`formula_settings` 的有效定义、发布、项目覆盖、pending 冲突、模板订阅/版本均通过 V199 模型；后续必须沿“定义写入 → effective 读取 → 实际执行消费者 → 传播”逐域闭环，而不能只验 CRUD。
6. 溯源：公式结果的 trace、规范 refs/addr_id、ACNR resolve、依赖图、统一 lineage、审计 hash chain 是不同层；后续须验证它们指向同一真实来源且可从 UI 跳转，不能把“有 trace 字段”当成可用溯源。

## 3. 公式域与引擎定位清单（本步只定位，不判完成）

| 域/能力 | 后端生产入口与关键符号 | 前端入口 | 表/迁移或持久载体 | 代表性测试位置（本步未执行） |
|---|---|---|---|---|
| 统一公式引擎 | `backend/app/services/formula_engine.py`：`FormulaContext`、`_REGISTRY`、`execute()`（L1 唯一求值入口）、兼容 `FormulaEngine`; `backend/app/routers/formula.py`：`execute_formula`/`batch_execute_formulas` | `FormulaInput.vue`、`FormulaEditDialog.vue`、`FormulaDebugPanel.vue`、`composables/formula/formulaSyntaxParser.ts` | 引擎纯计算；上下文读 `trial_balance`/四表/报表/附注/底稿；自定义函数兼容层含 Redis | `backend/tests/test_formula_engine.py`、`test_formula_engine_registry.py`、`test_formula_engine_contract.py`、`backend/tests/formula_management/test_execute_formula_dispatch.py`、前端 `formulaGrammarClosure.contract.test.ts` |
| 批量 Runtime/刷新 | `backend/app/services/formula_management/engine.py::execute_batch`；`formula_runtime/coordinator.py::FormulaRuntimeCoordinator.generate_mutation_plan`；`formula_runtime/adapters/{report,note,workpaper,adjudication,consol_worksheet}.py`；`draft_refresh_orchestrator.py` | `GtRefreshScopeDialog.vue`、`formulaRuntimeContract.ts` | `wp_formula`、`draft_refresh_audit`、`draft_refresh_snapshot`、`formula_runtime_outbox`; V100/V104/V178 | `backend/tests/formula_runtime/**`、`backend/tests/formula_management/test_draft_refresh_orchestrator.py`、`test_pbt_p21_recalc_vs_refresh.py` |
| 全局设置/项目适配/冲突 | `routers/formula_settings.py`；`services/formula_settings/{definitions,effective,publish,project_ops,apply_ops,pending,sync,rollback,stores,propagation}.py`；`DOMAINS` 实码含 report/tb_detail/cross_check/wp/note/consol_note/push | `views/FormulaGlobalSettings.vue`、`settings/FormulaSettingsToolbar.vue`、`FormulaGlobalScopeDialog.vue`、`FormulaPendingSyncDialog.vue`、`FormulaApplyScopeDialog.vue`、`FormulaConflictTable.vue` | `formula_setting`、`formula_sync_item`、`formula_publish`；报表全局/项目层仍在 `report_config`；V199/R199 | `backend/tests/formula_settings/test_{sync_kernel,effective_report,publish_report,project_ops,propagation,endpoints}.py`；前端 `settings/__tests__/*` |
| 公式模板/共享/订阅 | `routers/formula_templates.py`；`services/formula_settings/{template_service,template_access,template_sync,templates}.py` | `FormulaTemplateManager.vue`、`FormulaTemplateDetailDrawer.vue`、`FormulaTemplateSaveDialog.vue`、`FormulaTemplateSubscribeDialog.vue` | `formula_template`、`formula_template_version`、`formula_template_subscription` + 模板层 `formula_setting`; V199/R199 | `backend/tests/formula_settings/test_templates.py`、`test_template_endpoints.py`；前端 `FormulaTemplateManage.spec.ts`、`FormulaTemplateSubscribeDialog.spec.ts` |
| 公式目录/函数目录/校对目录 | `routers/formula_catalog.py::{formula_catalog,formula_catalog_stats,check_rules_catalog,formula_functions}`；`services/formula_catalog.py`、`formula_check_catalog.py` | `FormulaCheckCatalog.vue`、`FormulaDashboardDialog.vue`、`FormulaManagerDialog.vue` | 目录聚合有效定义与静态规则，不是独立公式表 | `backend/tests/formula_settings/test_formula_catalog.py`、`test_formula_check_catalog.py`、`test_unified_registry.py`；前端 `FormulaCheckCatalog.spec.ts` |
| 公式推送 | `routers/formula_push.py`；`services/formula_push/engine.py::{run,run_and_commit}`、`rules.py`、`bindings/*`、`policy.py`、`note_writer.py`、`triggers.py`；规则源 `backend/data/formula_push_rules.json` | `FormulaPushPanel.vue`、`FormulaPushVerifyPanel.vue`、`formulaPushView.ts`、`generated/formulaPushOwnedKeys.ts` | `formula_push_run`、`formula_push_state`; V169/R169；合并推送另有 `consol_push_run` V172 | `backend/tests/test_formula_push_*.py`、`tests/_formula_push_env.py`、`tests/_formula_push_binding.py`；前端 `FormulaPushPanel.spec.ts`、`formulaPushRuleActions.spec.ts` |
| 公式审计日志/历史 | `routers/formula_audit_log.py`；`services/audit_log_helper.py::append_audit_log`，`details.event_type='formula_changed'`；各写入口调用 helper | `FormulaHistoryTab.vue`、`FormulaTimelinePanel.vue` | 共用 `audit_log_entries` hash chain，无独立 formula audit 表；时间线另由运行/发布/变更记录聚合 | `backend/tests/test_formula_audit_log_get.py`、`test_formula_audit_pbt.py`、`formula_management/test_pbt_p18_audit_trail.py`；前端 `formulaHistoryRollbackGate.spec.ts` |
| Address Registry V1 / ACNR / V2 | `routers/address_registry.py` + `services/address_registry.py::AddressRegistryService`（动态五域、内存+Redis `addr_reg:*`）；`services/acnr/{catalog,resolver,formula_validation,non_wp_verification,events}.py`（`global_catalog.json`）；`routers/address_registry_v2.py`（静态依赖图） | `stores/addressRegistry.ts`、`FormulaRefPicker.vue`、`CellSelector.vue`、`GtFormulaSourceTooltip.vue` | V1 由业务表动态组装并缓存；ACNR 静态 `backend/data/acnr/global_catalog.json`；V2 `address_registry_l2_semantic.json`、`address_registry_resolved_refs.json`、`address_registry_l3_dependencies.json`、`cross_wp_references.json` | `backend/tests/test_address_registry_{authz,limit,redis_l2,single_flight,invalidation_coverage}.py`、`backend/tests/acnr/test_pbt_formula_roundtrip.py`；前端 `formulaPickers.acnr.pbt.test.ts` |
| 严格引用预载/存在性 | `services/formula_ref_preload.py::{substitute_prev_aux,load_report_rows,load_note_values}`；`formula_preloader.py`；`formula_ref_check.py`；`acnr/non_wp_verification.py` | `FormulaRefPicker.vue`、`GtFormulaIssuePanel.vue`、`formulaIssueHint.ts` | 只读 `tb_aux_balance`、`financial_report`、`disclosure_notes`、上年项目/试算表；无独立表 | `backend/tests/formula_settings/test_formula_ref_preload.py`、`test_formula_preloader.py`、`test_prev_prior_wp_field.py`、`backend/tests/test_formula_ref_check.py` |
| 报表公式 | `routers/report_config.py::{fill_formulas,execute_formula,execute_formulas_batch}`；`services/report_formula_service.py::ReportFormulaService.fill_all_formulas`；`report_engine.py`；`formula_settings/effective_report.py` | `FormulaManagerDialog.vue` 报表节点、`settings/reportEffectiveRows.ts`、报表公式栏 | `report_config`（定义、V199 版本/基线列、V179 AJE/RJE 公式列）、`financial_report`（结果与 stale） | `backend/tests/test_report_formula_coverage.py`、`four_table/test_report_formula_filler_mirror.py`、`formula_settings/test_execution_path_parity.py`、`test_report_audit_checks.py` |
| TB 科目明细公式 | `routers/tb_detail_formulas.py::{get_tb_detail_formulas,save_tb_detail_formulas}`；`services/formula_settings/tb_detail.py` | `components/formula/composables/useTbDetailFormulas.ts`、`FormulaManagerDialog.vue` | V199 后存 `formula_setting(domain='tb_detail')`；旧 `projects.wizard_state.tb_detail_formulas` 由迁移导入 | `backend/tests/formula_settings/test_tb_detail_and_cross_check.py`、`test_wiring_closure_endpoints.py`；前端 `useTbDetailFormulas.spec.ts` |
| 表间审核/逻辑校对/提示规则 | `routers/formula_logic_check.py`；`services/formula_settings/cross_check_rules.py::{load,save,run_user_rules,evaluate_strict}`；`formula_management/logic_check.py`；规则目录 `formula_check_catalog.py` | `FormulaCrossCheckPanel.vue`、`useCrossCheckRules.ts`、`GtFormulaIssuePanel.vue`、`CrossCheckHistoryPanel.vue` | V199 后用户规则存 `formula_setting(domain='cross_check')`；执行结果 `cross_check_results` | `backend/tests/formula_management/test_cross_check_rules_persistence.py`、`test_cross_check_run_observability.py`、`formula_settings/test_tb_detail_and_cross_check.py`；前端 `useCrossCheckRules.spec.ts`、`crossCheckKeyConsistency.spec.ts` |
| 底稿用户/预设/引用公式 | `routers/wp_formula.py`（`/formulas` CRUD/CAS/校验/求值）；`routers/wp_user_formulas.py`（兼容 API）；`wp_user_formulas_v2.py`；`services/wp_formula_{service,eval_service,dependency,linkage_service}.py` | `FormulaManagerDialog.vue` 用户自定义页、`GtFormulaEditDialog.vue`、`workpaper/FormulaStatusPanel.vue`、`GtCustomWpEditor.vue` | 权威 `wp_formula`：V052，V100 类型列，V104 生命周期，V163 稳定键，V178 source_scope/binding，V199 基线列；`working_paper.parsed_data.user_formulas` 仅兼容/溯源元数据 | `backend/tests/test_user_formula_storage_convergence.py`、`test_custom_wp_formula_full_chain.py`、`formula_management/test_wp_formula_atomic_cas_pg.py`、`formula_runtime/test_wp_formula_lifecycle.py`；前端 `wpFormulaFields.spec.ts` |
| 单体附注公式 | `routers/disclosure_notes.py::{list_note_formulas,upsert_note_formulas,apply_formulas,clear_formulas,formula_health}`；`services/note_formula_{service,evaluator,engine,dependency_service,derivation}.py` | `NoteFormulaDialog.vue`、`noteScopeTargeting.ts`、附注编辑器公式入口 | `disclosure_notes.table_data JSONB` 的 `_user_formulas`/表内 binding；有效项目层另用 `formula_setting(domain='note')`; V020/V039/V129 等附注演进迁移 | `backend/tests/test_note_formula_save_ref_check.py`、`services/test_note_formula_{dsl,user_merge,signed_sum,evaluated_at}.py`、`formula_management/test_note_formula_endpoints_auth_unchanged.py`；前端 `NoteFormulaDialog.spec.ts`、`noteUserFormulaMerge.spec.ts` |
| 合并附注/合并公式 | `routers/consol_note_formulas.py`；`routers/consol_note_sections.py::apply_all_formulas/fill_by_formula`；`services/consol_note_formula_service.py::{seed_note_formulas,fill_note_sections}`；`consol_note_formula_refresh_handler.py`；合并报表求值 `consol_report_values.py` | `ConsolFormulaManagementPanel.vue`、`consolFormulaManagement.ts`、合并附注页面 | `consol_note_formula`、`consol_note_data.is_stale/last_formula_value/locked_cells`; V172/V182/V184/V199(version) | `backend/tests/test_consol_note_formulas.py`、`services/test_consol_note_formula_refresh_handler.py`、`services/test_consol_report_formula_eval.py`；前端 `ConsolFormulaManagementPanel.spec.ts`、`consolFormulaWiring.spec.ts` |
| 四表/TB→报表/底稿/附注 | 数据源 `tb_balance/tb_aux_balance/tb_ledger/tb_aux_ledger` 经 `dataset_query.get_active_filter`、`amount_resolver.py`、`tb_formula_context.py`、`formula_preloader.py`；`trial_balance_service.py` 产 `trial_balance`；`formula_push/sources.py` 与各 binding 消费 | TB/四表页面的公式入口最终进入 FormulaManager；取数选择器由 address registry 提供 | `ledger_datasets` + 四表 + `trial_balance`; 公式相关快照/过期列见 V013/V018/V023 等 | `backend/tests/four_table/test_*formula*.py`、`test_formula_cross_module_refs.py`、`test_formula_eval_v2_sign_integration.py`、`test_adj_formula_resolution.py` |
| EventBus/跨模块传播 | `services/event_bus.py::EventBus`，Redis Stream `audit:events`；事件枚举 `models/audit_platform_schemas.py::EventType`；启动唯一接线 `core/startup_registry.py::_task_register_phase_handlers` 注册 adjustment recalc、formula push、formula settings propagation、consol note refresh | `utils/sse.ts`/项目事件订阅，`ThreeColumnLayout.vue` 接收待确认与刷新状态 | Redis Stream；可靠公式刷新 outbox 为 `formula_runtime_outbox`（V104） | `backend/tests/test_event_bus.py`、`formula_settings/test_propagation.py`、`test_event_year_contract.py`、`test_formula_push_triggers.py` |
| stale/recalc | `services/stale_propagation_engine.py::StalePropagationEngine.on_change`；`formula_settings/propagation.py::{propagate_report,propagate_wp,propagate_note,propagate_consol_note,propagate_push}`；`adjustment_approved_recalc_handler.py`；`report_stale_service.py`、`note_stale_service.py` | `composables/useStaleStatus.ts`、`DefaultLayout.vue` stale-summary、公式健康/问题/刷新面板 | `working_paper.prefill_stale`、`financial_report.is_stale`、`report_config.is_stale`、`disclosure_notes.is_stale`、`consol_trial.is_stale`、`consol_note_data.is_stale`; V013/V018/V023/V036/V044/V049/V129/V172 | `backend/tests/formula_settings/test_propagation.py`、`formula_management/test_pbt_p30_reference_invalidation.py`、`test_formula_push_triggers.py`、各 stale service 测试 |
| lineage/provenance | `routers/lineage.py::get_lineage`；`services/unified_lineage_service.py::UnifiedLineageService.query_lineage` 委托 `wp_trace_service`/`report_trace_service`/`version_line_service`；公式 refs/trace 另见 `formula_engine.FormulaResult.trace`、`formula_reverse_index.py`、ACNR | `workpaper/LineageGraphPanel.vue`、`formula/panels/FormulaDependencyPanel.vue`、`GtFormulaSourceTooltip.vue`、`custom-query/FormulaTracePopover.vue` | `attachment_lineage` V029；`disclosure_notes` provenance V039；`consol_trial.consolidation_breakdown` V034；依赖 JSON/`cross_wp_references` 与各公式 `refs/source_scope` | `backend/tests/services/test_unified_lineage_service.py`、`test_formula_gid_location_consumption.py`、`test_formula_config_reverse_linkage.py`；前端 `LineageGraphPanel.spec.ts`、`formulaBarSourceRefs.spec.ts` |

## 4. 相关 spec 的“历史声称”清单（不作实现结论）

> 统计口径：直接读取各 `tasks.md` 的 Markdown 标记；`[x]*` 同时属于“已勾选”和“可选”，`[-]`/`[~]` 不计入标准 checkbox。路径在 `_archive` 只表示档案位置，不证明代码仍在 HEAD。当前 `.kiro/specs/INDEX.md` 有未提交改动，因此 INDEX 中新增/改写内容一律标“来自未提交改动，不算已在库”；下列重点状态优先取各 tasks 文件本身。

| 重点 spec | 路径与声称 |
|---|---|
| `formula-global-settings-sync` | `_archive/55-batch-2026-10-21/...`；原始标记 36 项均 `[x]`（其中 8.2 为 `[x]*`），但文首同时写“35/36 必做完成、完整登录态 UI 走查未做”，属于文内状态口径不一致，待后续按代码/运行时复核 |
| `formula-governance-coverage-closure` | `_archive/67-...`；36/36 `[x]`，声称覆盖鉴权、严格取数、push 域、校对目录、组件挂载、底稿函数与真库走查；这里只记录声称 |
| `formula-fetch-and-wp-generation-defect-closure` | `_archive/71-...`；19/19 `[x]`，声称实施提交 `d9f08b55c`，覆盖推送科目、PREV 三参、地址库与生成流程；这里只记录声称 |
| `formula-fetch-followup-defect-closure` | active；30/34，未勾 4 项为 3.6 附注模板绑定、4.2 生成/自定义底稿后端门禁、4.3 模板清单门禁、4.5 鉴权基线收口；其余任务声称已完成 |
| formula-push 主系列 | `_archive/23-formula-push-engine-complete/chain-closure-phase2-formula-push-engine` 18/18；`formula-push-all-subjects-rollout` 原始 26/26（含 2 个 `[x]*`，正文仍散有“待实施/待集成”文字）；`_archive/25-.../chain-closure-phase3-push-rollout` 历史索引声称 15/15，但 tasks 另含 `[-]`/`[~]` 收尾项；均待事实复核 |
| formula-push 批次 | `_archive/23-...`：balance-adj-batch-c 11/11（1 optional）、income-stmt-batch-d 7/7、note-rollout-batch-c 7/7、batch-d 8/8、batch-e 16/16、tier-a-anchor-batch-b 12/12、user-custom-cross-module 11/11 |
| formula-push 附注质量 | `_archive/41-.../formula-push-note-skip-reduction` 原始 30 个 `[x]`，另有 2 个 `[-]`；`formula-push-note-row-matching` 39/39 `[x]`（其中 10 optional）；历史摘要另称 32/32 与 39/39，需后续统一口径 |
| `disclosure-payload-authority-source` | `_archive/08-disclosure-notes/...`；25 个 `[x]` + 1 个未完成 optional Playwright（gt-plan 报 25/26、96.2%）；声称载荷权威源留前端并新增覆盖率与不变量守卫，不作实现结论 |

- 其余归档公式基础/治理 spec 的 checkbox 声称：`formula-engine-unification` 20/20；`formula-management-runtime-closure` 18/18；`formula-runtime-convergence` 18/18；`formula-management-library` 92/92（31 optional）；`formula-row-name-alignment-confirmation` 15/15；`formula-manager-closure` 30/30；`formula-manager-runtime-integrity-closure` 29/30（1 optional）；`formula-settings-wiring-closure` 14/14；`unified-formula-registry` 18/18（1 optional）；`formula-execution-path-convergence` 13/14（1 optional）；`formula-management-deep-optimization` 36/36；`formula-input-param-completion` 21/21；`formula-management-ux-improvements` 23/23（3 optional）；`formula-push-subtable-expansion` 19/19。
- 其余归档业务接线 spec 的 checkbox 声称：`custom-workpaper-formula-binding` 58/58（23 optional）；`custom-workpaper-dual-mode-formula-and-batch` 29/29；`d-cycle-four-table-extraction-formulas` 30/30（1 optional）；`template-library-formula-preset-custom` 16/16（1 optional）；`workpaper-page-formula-toolbar-closure` 17/17；`adj-formula-repair-and-approval-gate-wiring` 40/40；`d1-four-table-extraction-formula-wiring` 14/14；`disclosure-note-formula-and-report-sync` 29/29；`disclosure-note-formula-data-population` 25/25；E/H/I/K/L cycle extraction-formula 系列分别 24/24、18/18、26/26、25/25、26/26；`note-sub-table-formula-and-cross-check` 26/26；`consol-note-node-refresh-and-formula-orchestration` 28/28（3 optional）；`tb-adjustment-column-formula-closure` 44/44（1 optional）。
- D4/双向回写名称含 formula 的归档 spec 声称：`d4-1-adjudication-bidirectional-writeback-and-formula-io` 12/12；`d4-21-24-oo-bidirectional-and-cross-sheet-formula` 10/10；`d4-33-36-writeback-formula-and-io-closure` 35/37（2 optional）；`d4-cutoff-return-writeback-formula-io` 13/13；`d4-dual-mode-formula-governance` 16/16；`d4-inspection-writeback-formula-io` 9/16（7 未勾）；`d4-ipo-checklist-dual-mode-writeback-and-formula` 28/28；`d4-ipo-fraud-writeback-formula-io` 11/11。

## 5. 下一阶段四个调查角度

1. **执行正确性与会计口径**：逐函数验证 TB/SUM_TB/PREV/AUX/ROW/REPORT/NOTE/WP/ADJ 取数、父子科目防双计、借贷方向、缺数不冒充 0，并对四表、TB、报表、附注和底稿的真实值逐格对账。2. **跨模块贯通与传播**：从四表导入、调整审批、公式变更三类入口追到 EventBus、stale、recalc、push、SSE，核实每条链既不漏触发也不回环、不覆盖人工值。3. **全局/项目/模板治理**：验证有效定义四层优先级、CAS、发布、冲突弹窗、采用/保留/自定义、模板订阅与版本升级是否真正影响各域消费者，而非只完成 CRUD。4. **溯源、可观测与用户可达**：验证每个结果能显示来源、公式、实际值、版本、审计记录与可跳转地址，公式目录/健康度/历史/依赖/提示规则在真实登录态 UI 可达，且 spec 声称、HEAD 与 live 行为一致。
