# 修复与验收清单

- [x] 1. 建立锁定隔离候选、所有权与spec三件套（R1~R5）
- [x] 2. 修复报表PREV/AUX明确拒绝、WP年度与缺失语义、审核NULL（R1；反例1/2）
- [x] 3. 修复scope编辑篮及异步上下文、模板锁后重读、本地编辑revision（R2；反例3/4/5）
- [x] 4. 验证模板连续升级保留原版本暂缓项（R2；反例6）
- [x] 5. 贯通实际输入、采用/最近尝试、来源缓存与冻结年度穿透（R3）
- [x] 6. 集成S2规则能力/结果展示并透传项目上下文（R3）
- [x] 7. 修复完整slot传播、持久业务回执及真实状态展示（R4；反例7/8）
- [x] 8. 修复稳定事件幂等、历史精确查询与重复重算复用（R4）
- [x] 9. 点名隔离回归、多项目/年度/角色/连续版本联合验收（R5）
- [x] 10. 独立浏览器运行验证、变更边界核对与交付记录（R5）

## 验证记录

### 2026-11-08 回填勘误（任务 2/3/5/6/7/8 据 v1.0.149 入库证据改 [x]）
下文"尚未运行"等旧记录是 tasks.md 唯一提交版（`cccd3b6e0` 当时）的过时陈述，保留留痕。
实际上本 spec 的生产修复与测试已随同一提交 **`cccd3b6e0`（tag v1.0.149，2026-11-08）** 入库，且在当前 HEAD 祖先链上。该提交正文逐条列明交付（审核 strict 五态持久化 + 报表检查前端融合）：
- 后端：`report_engine.py`(+656/-647)、`report_row_compute.py`、`report_config_execute.py` 的 strict 三入口 + 失败 attempt 记录；`cross_check_rules.py` / `logic_check.py` / `report_audit_checks.py` 的 strict 传播、row_cache 保 None 不补 0、SAVEPOINT + 写入数量校验；`formula_check_catalog.py` + `formula_catalog.py` 加 year 参数 + 五态聚合 + history_note（对应任务 2、5、6、7、8）。
- 前端：`ReportView.vue` / `useReportData.ts` / `useReportRequestFence.ts`（请求围栏）/ `useReportTrace.ts` / `ReportBalanceBanner.vue` / `FormulaHealthPanel.vue`（真零）/ CSV 导出保 0 与缺数（对应任务 3 的 revision/本地编辑、任务 6 结果展示）。
- 测试：新增 `test_formula_integrity_strict_errors.py`(754 行)、`test_formula_integrity_compute.py`、`test_formula_integrity_audit.py`、`test_formula_integrity_strict_seams.py`、`formula_settings/test_r4_action_receipts.py`、`test_formula_check_catalog_history.py`。
- 提交正文声明验收：CAS R4 七红全修（63 passed）；strict 核心 910 passed；前端 7/8 套件 93 passed。
- 本次核验（2026-11-08，SQLite）：`test_formula_integrity_strict_errors / compute / audit / strict_seams` 四文件实跑 **558 passed / 0 failed**，坐实"代码 + 测试通过"。

保留 `[ ]` 的两项（无本轮完成证据）：
- 任务 4（模板连续升级保留原版本暂缓项，反例 6）：提交正文未提及该模板升级暂缓主题的专门修复与用例，不据现有证据标完成。
- 任务 9（多项目/年度/角色/连续版本联合验收）、任务 10（独立浏览器运行验证 + 交付记录）：属需运行环境的联合/浏览器验收，提交正文记 `balance.spec 待后续适配主树接口形态`，未坐实，保留未勾。

### 旧记录（过时，留痕）
尚未运行本轮生产修复回归或浏览器验收。未执行共享业务写入、迁移、提交或推送。

### S2 按块整合进度（2026-11-07）
源码接缝已核对，人工结论词表已按真实用途登记排除，问题面板已分开展示严重级别与执行状态。此阶段只有源码和编辑器诊断证据，尚未运行测试；任务 2–10 保持未勾选，后续以隔离联合验收结果为准。

### 2026-11-08 主树整合阶段（实际验收尚未完成）
用户追加主树、必要共享库及主后端真实验收授权；本轮基线已成功导出二进制patch，并保存原始文件blob与各树完整索引stage清单。主树67项、候选91项、重叠18项；旧测试数量不计本轮证据。任务2–10继续未勾选，随后以主树实际测试、接口与浏览器证据收口。

### 2026-11-09 续做（主工作树 + 隔离 worktree `tmp_formula_close/head_wt`（HEAD `aff1741de` 干净检出））

- **任务 4（反例 6）：验证完成，实现未入库 ⇒ 保持 `[ ]`**。新增 `backend/tests/formula_settings/test_template_consecutive_upgrade_deferral.py` 2 例：v2 改 A+B 且项目暂缓 ⇒ v3 只改 B 时 A 的暂缓待确认仍在、仍指向 v2 定义，订阅保持固定在 v1、有效公式仍是旧值；逐位结案后才解除固定并跟上 v3；只结案 A 时订阅仍固定。主工作树 2 passed；磁盘变异（`publish_template` 里把「固定订阅调 `refresh_subscription`」换回「直接解除固定并跟上新版本」）2/2 红，恢复后 sha256 与变异前一致。被验证的实现（`template_sync.py` 的这一分支）只在主工作树未提交的改动里，HEAD 上这两例会红
- **任务 9（点名隔离联合验收）：保持 `[ ]`**。非 PG 联合回归（`tests/formula_hub` + `tests/formula_settings` + `tests/formula_management`，`-m "not pg_only"`，`DATABASE_URL` 指向不存在的库）：主工作树 2245 passed / 49 failed（去重后 47 个节点）；同一选集在干净 HEAD 上 1892 passed / 86 failed + 1 收集错误（去重后 85 个节点）。逐条差集：主工作树修好 41 条、新增 3 条：
  - `test_pending_revision.py::test_three_origins_create_at_one_and_overwrite_to_two[template]`：`publish_template` 现在强制预览指纹（R2），用例仍直接发布 ⇒ 用例过期，应先预览再发布
  - `test_l1_failure_semantics.py::...[regex-EVIL(1)]`：正则降级路径去掉了 blocked 前置判定，拦截原因从「未注册的函数：EVIL()」退化成「公式含非白名单内容，已拦截」⇒ 原因可解释性回退，需修 `formula_engine.py`
  - `test_formula_history_production_wiring.py::test_consistency_rule_exception_is_not_silent_pass`：一致性规则异常文案改成「检查异常，未执行：…」，来自 `gate_rules_chain.py` 的未提交改动（S2 在途），语义仍不放行，用例需随 S2 改
  - 另：`test_domain_adapters.py` 两例按 R2 / R4 新契约改写（无载入快照时与现有定义完全相同的整表是空操作、真正改动才 428；`propagate_note` 必须带冻结年度，`None` 走 `no_year` 跳过），改后 11 passed
- **任务 10：保持 `[ ]`**。浏览器（开发服 9980 / 3030，只读）：【测试】公式同步甲报表页显示「审核明细 4 项：通过 2 / 未通过 2 / 未执行 0 / 不适用 0 / 错误 0」与「后端汇总：失败 2 项，提示 0 项（提示不计入失败）」，缺数行显示「-」不显示 0；全局公式设置页、校对规则目录页可打开；控制台只有既有 `notes-tree` 404 与 Transition 警告。共享库无公式模板，连续升级暂缓的界面走查需要新建全局模板（全局对象，不属于【测试】项目），未做
- 🔴 **P0 归档阻断：v1.0.149 是半提交**。`cccd3b6e0` 提交了调用方与测试，没提交被调实现：HEAD 的 `report_engine.py` 导入 `formula_engine.formula_number`、`report_row_compute.py` 导入 `formula_engine.formula_technical_error`、`tests/formula_settings/test_r4_action_receipts.py` 导入 `outbox.action_status`，三者在 HEAD 都不存在、只在主工作树未提交的 `formula_engine.py` / `outbox.py` 里 ⇒ 干净检出上报表生成 `ImportError`，`test_r4_action_receipts.py` 收集即失败。2026-11-08 回填勘误据「v1.0.149 入库」把任务 2/3/5/6/7/8 改 `[x]` 的依据只对已提交部分成立：R4 回执 / 幂等（任务 7/8）与 strict 求值内核的实现仍在工作区。主工作树当前 59 个已修改 + 若干未跟踪文件，混有 S2 `check-contract-and-note-executor`（在途）与 `display-core-violations-cleanup` 等其他会话的改动，按文件归属拆分提交需用户拍板

### 2026-11-09 主树红项逐一收口（用户「主树存在红，你需要逐一修复」）

选集 `tests/formula_hub` + `tests/formula_settings` + `tests/formula_management`（非 PG，`DATABASE_URL` 指向不存在的库）：开工 49 failed → 中途 17 failed → 收口后见下方回归行。按根因分组，生产缺陷修主代码、过期断言按现行契约改写（不降级成恒绿）：

- **生产缺陷（改主代码）**
  - `formula_engine._execute_regex`：被拦截时原因退化为「公式含非白名单内容，已拦截」⇒ 新增 `_blocked_reason` 点名首个未注册函数（与 `_is_blocked_formula` 同一判据）
  - `formula_engine.FunctionRegistry.register`：内置函数的 `arity` / `syntax` 元数据改从函数目录（S1 单一真源）取，另给 `arity_max`；原先 TB / SUM_TB / ADJ / REPORT / ROUND / NOTE / AUX / LEDGER* / COUNT_LEDGER 十个函数注册表写的参数个数与目录、求值期校验各说各话（如 TB 已支持单参，注册表仍写 2）
  - `report_freshness.is_effectively_stale`：新增可选 `definition_hash`（S5 ADR-FPE-06）—— 行上有生成时定义哈希就以哈希为准，存量行退回按公式文本；`row_status` 复用同一判据（不再各写一份）
  - `formula_check_catalog._rule`：严重级为 `(str, Enum)` 时 `str()` 得「GateSeverity.blocking」、标签查不到 ⇒ 取 `.value`
  - `unified_lineage_service._source_error`：附注→底稿映射的两类配置错误不再并进「LINEAGE_SOURCE_FAILED」，分别报 `REGISTRY_UNAVAILABLE`（503）/ `PROJECT_MAPPING_INVALID`（422），重试无用、要修注册表或项目映射
  - `report_trace_service.report_trace_to_locate_targets`：sheet 级降级只给第一张底稿 ⇒ 复数章节（G1 / G10 等、项目自定义多底稿映射）每张底稿一个目标
  - `routers/formula_debug`：取数缺口只并进 warnings、结果照样 ok ⇒ 调整分录取数失败时调试显示 ok + 0，与中央执行合同（有缺口即失败）相反；改为同口径（缺口进 errors、`ok=false`、`state=missing`），前端 `FormulaDebugPanel` 本就展示 errors
- **夹具缺表（取数失败被静默成 0 / 审计与 outbox 无表可写）**：`_central_world`、`test_wp_formula_eval_functions` 补 `adjustment_treatment_events` / `adjustment_client_bookings`（ADJ 恒 0 → XR-07 一致项目误判差异）；`test_wp_formula_save_gate` 补 `audit_log_entries` / `audit_chain_head` / `import_event_outbox`；`test_formula_provenance_lineage_endpoint` 补 `trial_balance` / `tb_ledger` / `ledger_datasets`；`test_draft_refresh_service_counts` 的 AsyncMock 会话撑不起审计链，在 `append_audit_log` 一层记录，并新增「运行时哈希审计 mandatory：写失败 ⇒ 整次刷新失败」用例
- **过期断言按现行契约改写**：L1 失败值为 `None`（不再是 0 / 部分和）；模板发布必须带预览指纹（`test_pending_revision` / `test_decision_key_domain`）；含附注域的模板必须声明 soe / listed；S2 统一的「检查异常，未执行：…」文案；报表路径 PREV / AUX 明确拒绝（`test_function_support_matrix` 原「置 0」锚点改为「拒绝且写明不支持」，真取数或退回置 0 都打红）；报表 ADJ 守卫由「不在置 0 列表」改为按行为判定（取到调整额、只加载一次、期初模式显式记 0）；缺 NOTE 两种模式都是业务失败不补 0；报表配置执行改走 `ReportFormulaParser`，预算用例的慢取数注入点两条路径都换；冻结读者清单随 `deliverable_readiness_sources` 拆分改限定名并登记 `consol_report_run_service._definition_hash`；`test_fix_report_bs_book_value_formulas` 真库留底用例补 `pg_only`（共享库只读实跑 1 passed）
- **范围外预存红（干净 HEAD 同红，未改）**：`test_wp_traceability_panel_property.py::TestProperty2AttachmentLinkQueryable`（附件溯源 PBT，`hypothesis` 反例 `wp_cell` / `'0'`）

### 2026-11-09 收尾（补齐半提交、联合验收、浏览器验证，归档）

- **补齐 v1.0.149 半提交**：按文件归属从主工作树挑出本 spec 与 hub spec 的改动（`formula_engine` / `formula_function_catalog` / `formula_check_catalog` / `report_freshness` / `report_trace_service` / `unified_lineage_service` / `wp_formula_eval_service` / `formula_settings/*`（含新 `project_year_guard.py`）/ `formula_management/engine` / 三个公式路由 / `stale_propagation_engine`（R4 严格依赖图写入）/ `routers/reports.py`（审核严重级汇总）+ 前端 `FormulaGlobalSettings` / `FormulaTemplateDetailDrawer` / 新 `formulaTemplateCas.ts` / `formulaFunctionCatalog` 生成物 / `FormulaManagerDialog` 计数），放进最新 HEAD（`e25895b20`）的干净 worktree 组成候选树；S2 `check-contract-and-note-executor`、显示设置、高级查询等其他会话的文件不带入（`gate_rules_*` 留给 S2，对应用例 `test_consistency_rule_exception_is_not_silent_pass` 用 HEAD 版）
- **任务 4 → `[x]`**：`template_sync.py` 连续升级暂缓实现随本次入库；`test_template_consecutive_upgrade_deferral.py` 2 例在候选树通过（变异证据见上一节）
- **任务 9 → `[x]`**：候选树非 PG 联合回归 `tests/formula_hub` + `tests/formula_settings` + `tests/formula_management` + `test_formula_integrity_*` + `test_adj_formula_function` + `test_formula_debug_endpoint` + `test_release_lazy_import_closure`：**2745 passed / 0 failed**（多项目 / 多年度 / 角色 / 连续版本覆盖在 `test_r4_year_isolation`、`test_project_integrity_concurrency`、`test_template_integrity_concurrency`、`test_template_consecutive_upgrade_deferral`、`test_r4_operation_idempotency`）。首轮 11 红逐条归因：9 条 `test_r4_year_isolation` = 漏带 `stale_propagation_engine.py`（补入）；1 条审核汇总 = 漏带 `routers/reports.py`（补入）；1 条 = S2 文案（换回 HEAD 用例）。`test_release_lazy_import_closure` 两例断言旧调用签名，按 R4 新契约改写（`strict=True`、写入前核对项目年度）并新增「年度已变化不进依赖图」「依赖图 degraded 不当成功」两例；去掉 outbox 年度核对的变异让新用例红。stale 引擎下游 20 个用例文件：`test_deliverable_lineage_properties` 2 红、`test_g_cross_wp_refs` 1 红在干净 HEAD 同红；`test_h9_h8_lease_callback` / `test_i6_i2_reverse_backfill` 在干净 HEAD 同样超时，非本次引入。前端候选树 `src/components/formula` + `src/services` + 全局设置作用域 1100 passed / 3 failed，3 条（`consolFormulaWiring` 读 `ThreeColumnLayout` 源码、`formulaPaths` barrel 两条）在干净 HEAD 同红
- **任务 10 → `[x]`**：主开发服 9980 / 3030（admin，共享库）浏览器实测：全局公式设置页编辑弹窗按会话打开、公式模板页可用、控制台无错误；【测试】公式同步甲报表页「⚡ 应用自动运算」得 64 / 70 已计算，失败行悬停显示「失败原因：公式来源加载失败：ROW('BS-013')：引用的行次不存在或尚未计算」；BS-003 本项目适配 `+ 0` → 历史出现带年度条目与「↺ 一键回滚」→ 确认回滚提示「已回滚」→ 刷新后 BS-003 回到 `TB('1101','期末余额')`（写入已由回滚还原）。走查抓到两处界面问题已修：回滚条目类型显示英文 `rollback` 且不展示公式变化（`FormulaHistoryTab.vue`，新增 `FormulaHistoryTab.actionLabel.spec.ts`）；时间轴「操作人」原样显示用户 id（`formula_timeline_service._attach_user_names` 补人员档案姓名 / 登录名，前端无姓名显示「未知用户」；新增后端 1 例、前端 `FormulaTimelinePanel.operator.spec.ts`），两组新用例在 HEAD 版组件上红、修后绿，后端变异（姓名改回 id）红
- 未改、交后续：附注 / 报表试算里 `ROW()` 引用未配置公式的行（如 BS-013）按「缺数」整行失败，而报表生成按默认推导得出合计 350 —— 试算与生成口径不一致（见改进建议）
