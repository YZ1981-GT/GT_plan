# 10 · 高级查询架构与接线现状

> 基于 HEAD `b5fc200e0` 源码现读 + 活体请求核对。符号与行号以文件为准；断点编号（AQ-xx）见 `report.md` §2。

## 1. 用户入口地图

| 入口 | 位置 | 打开什么 | 带入的上下文 | 门控 |
|---|---|---|---|---|
| 侧栏「高级查询」 | `layouts/ThreeColumnLayout.vue` L229-236 | `CustomQueryDialog`（全局弹窗） | project-id = 路由 `projectId`，但弹窗只在自身项目为空时采用（换项目页后不更新，AQ-37）；非项目页打开时取项目列表第一项；year = 路由 `?year` 或「日历年−1」（L589） | 无（所有登录用户） |
| 仪表盘快捷操作 | `views/Dashboard.vue` L436-440 | eventBus `open-custom-query`（无参）→ 同一弹窗 | 同上 | 无 |
| 模板库「高级查询」按钮 | `TemplateLibraryButton`，挂在 `WpTemplateDetail` / `ReportConfigTab` / `NoteTemplateTab` | eventBus `open-custom-query` `{tab, source, project_id}` → 弹窗预选数据源 | `project_id` 被 `onOpenCustomQueryEvent`（L961-966）忽略 | 无 |
| 弹窗「高级构建器」页签 | `CustomQueryDialog.vue` L206-212 | `AdvancedQueryBuilder`（embedded） | 无项目、无年度 | 写死 `ADVANCED_ROLES` + 原始 `authStore.user.role`（L262-263） |
| 弹窗「📑 模板」 | `CustomQueryDialog.vue` L264-268 | 跳 `/custom-query` | 无 | — |
| 路由 `/custom-query` | `router/domains/extension.ts`（meta `project:view`） | `CustomQuery.vue` → `CustomQueryTab` | 用户手选项目；年度跟随项目 `audit_year` | 登录 |
| 模板库「自定义查询」页签 | `TemplateLibraryMgmt.vue` L168 | `CustomQueryTab` | 同上 | 登录 |
| 页面内「高级构建器」按钮 | `CustomQueryTab.vue` L107-121 | 弹层内 `AdvancedQueryBuilder` | 无 | `useQueryBuilderAccess.canUseBuilder`（禁用 + 中文原因） |

子组件：`CustomQueryFieldPicker`（ACNR 选字段树，构建器与页面版使用）、`SheetCellRangePicker`（弹窗内底稿 sheet 选区；只传 wp-code / sheet-name / project-id，**不传 year 与 module-source** ⇒ 模块模式不可达）、`queryColumnLabels` / `queryExport` / `querySourceUri` / `queryFieldTiers`、`useAcnrDrill`（GtIndexChip 下钻）。
零挂载（只在 `components.d.ts` 声明）：`MyTemplatesDialog`、`SaveAsTemplateButton`、`MetabaseDashboard`、`DrillDownNavigator`。
没有任何「从试算表 / 报表 / 附注 / 底稿 / 调整分录页带当前对象打开查询」的入口（AQ-34）。

## 2. 后端端点（21 个，均已注册：`router_registry/system.py` L113-114、L137-139）

| 端点 | 鉴权 | 前端调用方 | 链路要点 |
|---|---|---|---|
| `GET /api/query/schema` | `require_query_builder_access`（系统角色 admin / manager / partner） | 构建器、`queryFieldTiers` | 15 张白名单表；按角色隐去 PII 列 |
| `POST /api/query/preview` · `/execute` · `/export-excel` | 同上 | 构建器 | `resolve_builder_scope`（三处都不传 `requested_project_id`）→ `builder_dsl._build_select`（复杂度预算 / PII / JOIN 业务键 / `enforce_query_plan` / `param_sql_builder` 谓词 / `apply_scope_to_select`）→ `query_cache` → `cancellable_query`（30 s / 导出 120 s）→ `formula_refs` |
| `GET /api/custom-query/indicators` | 登录；带 project_id 时 OwnershipGuard | 弹窗、页面版 | 报表 / 试算 / 附注 / 调整 / 工作底稿 / 底稿 / 报表行次 / 工时 八大类；`depth=1` 骨架、`branch=` 分支 |
| `GET /wp-id-by-code` | 登录 + guard | 弹窗 + 30 余个底稿 composable（平台公用） | `working_paper ⋈ wp_index` |
| `GET /wp-sheet-preview` | 登录 + guard | `SheetCellRangePicker` | `univer_snapshot` → storage xlsx（无文件则 `init_workpaper_from_template` 写文件） |
| `POST /execute` | 登录 + guard（编排器 step1） | 弹窗、页面版、`SheetCellRangePicker` | 见 §3 |
| `GET/POST /templates`、`GET/PUT/DELETE /templates/{id}` | 登录；改删仅作者 | 页面版；弹窗只 POST | `template_scope_guard` + `TemplateScopeAdapter` + `template_service`（两套 scope 归一，AQ-16） |
| `POST /templates/{id}/execute` | 登录 + `assert_executable` + 复用 execute | **无** | — |
| `POST /batch-execute` | 登录 + guard | **无**（apiPaths 只登记常量） | 多 wp_code 取数 |
| `POST /cell-writeback` | 登录 + body.project_id 可见 + edit 级 | **无**（apiPaths 只登记常量） | `snapshot_writer.write_cell`：workpaper / report / note / adj / tb |
| `POST /writeback-preview` · `/writeback-confirm` | `_assert_writeback_authorized`（可见 → edit → 逐目标项目） | **无** | `WritebackPreviewService` → `WritebackConfirmationGate` → `snapshot_writer` |
| `GET /index-health` | 登录 | **无** | `gin_index_monitor` |
| `GET /cross-sheet-trace` | 登录 + guard | **无** | `cross_sheet_trace_orchestrator`（同步 BFS + 异步 addr_id）+ 审计 |
| `GET /address-resolve` | 登录 | 弹窗右键「跳模板溯源」 | 查 `wp_template_registry`（表不存在，AQ-17） |

## 3. 执行链

业务视图：

```
POST /api/custom-query/execute
 └ ExecuteCompatibilityAdapter.execute → QueryOrchestrator.execute
    step1   OwnershipGuard.assert_target_accessible(project_id)           ✅ 实测有效
    step1.5 validate_pagination（limit 1..2000，offset ≥ 0）
    step2   AddressingService.resolve_many(acnr_targets)                 ⚠ 只校验，不参与取数（AQ-15）
    step3   QueryCache（键含 project_id + 作用域签名）
    step4   business_fetcher → _dispatch(source) → routers.custom_query._query_*（text SQL + 绑定参数）
            fetch_limit=None → _effective_limit → FETCH_HARD_CAP = 5000    ❌ AQ-03
    step5/6 grouping_engine / pivot_engine（内存，基于 ≤5000 行样本）        ❌ AQ-03
    step7   resolve_sort + sort_rows（内存）→ total = len(rows) → 切片       ❌ total 恒 ≤ 5000
    step8   _finalize_columns（addr_id 挂载；取数器从不提供 addr_id）         ❌ AQ-14
 └ router：fetch_cap_warning(len(本页行))，本页 ≤ 2000 < 5000 ⇒ 永不触发；敏感源按 60 s 节流记审计
```

构建器：`require_query_builder_access` → `resolve_builder_scope`（admin / partner = 全部项目；manager = 可访问集合；无 `project_id` 列的表不过滤）→ `_build_select` → SQL `LIMIT ≤ 1000 OFFSET` → `total = len(rows)`；前端无翻页控件。

回写：`cell-writeback` →（body.project_id 可见 + edit）→ `snapshot_writer.write_cell(module)`：
- `workpaper`：11 步事务（addr_id 解析、xlsx cache、`orchestrator.after_save`、耐久 outbox、事务内审计）✅
- `note`：`consol_note_data` 行锁 + project / year / section / node_key 逐项复验 ✅
- `report`：写 `report_snapshot`（全库 0 行）
- `adj`：`UPDATE adjustments SET {列} WHERE id=:aid`（不校验项目、不经调整分录服务）❌
- `tb`：`SELECT … FROM trial_balance WHERE id=:tid FOR UPDATE` → `tb_audited_writer.publish_rows(source='custom-query:tb-cell')`（不校验项目、不经发布门）❌

## 4. 业务视图数据源 → 表

| 数据源（叶子 key） | 取数器 | 读的表 | 数据集可见性 | 断点 |
|---|---|---|---|---|
| `report`、`report_*` | `_query_report` | `report_config`（结构）+ `report_snapshot`（金额，全库 0 行） | — | AQ-01 |
| `trial_balance`、`tb_detail`、`consol_unit:*:tb_detail` | `_query_trial_balance` | `trial_balance` | TB 无数据集 | AQ-26（缺 RJE、排序） |
| `tb_summary` | `_query_tb_summary` | `consol_worksheet_data`（`tb_summary_*`） | — | AQ-11 |
| `account_balance`、`consol_unit:*:account_balance` | `_query_account_balance` | `tb_balance` | ❌ 只写 `is_deleted=false` | AQ-02 |
| `ledger_entries`、`consol_unit:*:ledger_entries` | `_query_ledger_entries` | `tb_ledger`（`ORDER BY voucher_date DESC`） | ❌ 同上 | AQ-02（潜在）、AQ-03 |
| `disclosure`、`disclosure_note:{id}` | `_query_disclosure` | `disclosure_notes` → 回退 `consol_note_data` | — | AQ-10 |
| `adjustment`、`adj_*`、`consol_unit:*:adjustment` | `_query_adjustments` | `adjustments`（传 'AJE' / 'RCL'） | — | AQ-07 |
| `worksheet`、`ws_*` | `_query_worksheet` | `consol_worksheet_data` | — | AQ-11 |
| `workpaper`、`workpaper:{code}[\|sheet]` | `_query_workpaper` / `_query_workpaper_cell_range` | `working_paper ⋈ wp_index`；cell_range → `univer_snapshot` → storage xlsx → LibreOffice | — | AQ-14、AQ-23 |
| `report_lines` | `_query_report_lines` | `report_config`（`sort_order` 列不存在） | — | AQ-08 |
| `workhours` | `_query_workhours` | `work_hours`（全库 0 行） | — | — |
| `report:` / `note:` / `adj:` / `tb:{限定}\|{区间}` | `module_cell_resolver` | `report_snapshot` / `consol_note_data` / `adjustments` / `trial_balance` 虚拟 sheet | — | AQ-01、AQ-07（大写枚举被 except 吞成 0 行） |
| 缺失 | — | `tb_aux_balance`、`tb_aux_ledger`、`financial_report` | — | AQ-12、AQ-01 |

构建器白名单 15 张表：trial_balance、adjustments、unadjusted_misstatements、report_line_mapping、report_config、working_paper、wp_index、tb_balance、tb_ledger、account_chart、materiality、projects、disclosure_notes、staff_members、work_hours。没有辅助核算、financial_report、合并表；四表不经数据集过滤、默认不滤 `is_deleted`（AQ-02）。登记的 `trial_balance / tb_balance / tb_ledger → account_chart` JOIN 只按科目码关联、不区分 `account_chart.source`（每个码 client + standard 各一行）⇒ 结果行翻倍（AQ-19）。SQL 层的分组 / 求和本身与库内逐值一致。

## 5. 服务模块接线现状（`services/custom_query/` 27 个模块，全仓 importer 现扫）

| 模块 | 生产 importer | 前端可达 | 结论 |
|---|---|---|---|
| query_orchestrator / execute_compatibility / business_fetchers / pagination / query_cache / addressing_service | router + 包内 | 是（execute） | 保留；pagination 改为配合 SQL COUNT 与下推 |
| grouping_engine / pivot_engine | orchestrator 惰性导入 | 否（前端不发 group / pivot） | 保留，加「取数未触顶才可用」门禁或下推 SQL |
| builder_dsl / builder_scope / table_whitelist / execution_guard / param_sql_builder | query_builder | 是 | 保留；scope 补 projects 过滤与 requested_project_id；param_sql_builder 继续作谓词单一真源 |
| module_cell_resolver | router + 包内 | 仅 SheetCellRangePicker 模块模式（不可达） | 保留，修枚举与报表源 |
| export_service | query_builder 只用常量 `EXPORT_ROW_HARD_LIMIT` | 否 | 接线（全量流式导出）或删除 |
| snapshot_writer（+ _addr_id / _modules / _shared） | cell-writeback、writeback-confirm、workpaper_save_orchestrator | 否 | 保留；先修 AQ-04 / AQ-05 再接前端 |
| writeback_preview | custom_query_writeback | 否 | 保留 |
| cross_sheet_resolver | 包内 + `wp_formula_eval_service` | — | 保留（他模块在用） |
| cross_sheet_trace_orchestrator | `GET /cross-sheet-trace` | 否 | 接线到底稿单元格结果的公式溯源；不要则连端点一起删 |
| template_scope_adapter / template_scope_guard / template_service | router | 是 | 保留，scope 归一合并为一处（AQ-16） |
| ownership_guard / audit_helper / metrics | router + 包内 | 是 | 保留 |

## 6. 权限模型

- 两层身份：系统角色 `users.role`（admin / partner / manager / auditor / qc / readonly / eqcr）与项目成员（`project_users.role` + `permission_level`，以及 `project_assignments` 经 `staff_members.user_id`）。
- 业务视图：`OwnershipGuard` 可访问集合 = project_users ∪ project_assignments；admin / partner 视为全部项目。实测有效：非成员 403 `FORBIDDEN_PROJECT`「无权访问该项目数据」，成员 200，空 project_id 403。
- 构建器：只看系统角色 `_QUERY_BUILDER_ROLES = (admin, manager, partner)`；前端 `useQueryBuilderAccess`（`normalizeRole`）与弹窗写死的 `ADVANCED_ROLES` 集合逐值相同。真实现场经理是系统角色 auditor + 项目角色 manager ⇒ 被 403（AQ-21）。
- 构建器作用域：manager 只看可访问项目；**无 `project_id` 列的表（projects、staff_members、report_config）一律不过滤**（AQ-06）。
- PII：`staff_members.email / phone / user_id` 只对 admin / partner 下发，manager 显式请求 403 `PII_FIELD_FORBIDDEN`（实测）。
- 回写：body.project_id 可见 + edit + 逐目标 project_id；**记录 id 是否属于该项目从不校验**（AQ-04）。

## 7. 写路径与平台铁律对照

| 写路径 | 平台铁律 | 现状 |
|---|---|---|
| TB 审定数 | 只经 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`：二次确认 + `publish_token` + 带 `publish_confirmed` 的 WORKPAPER_SAVED，handler 幂等回写并级联下游 | `cell-writeback` module=tb 直接调 `tb_audited_writer.publish_rows`，无确认、无 token、无事件 ❌ AQ-05 |
| 调整分录 | 经调整分录服务（复核状态、ADJUSTMENT_APPROVED → TB 重算） | module=adj 直接 `UPDATE adjustments` ❌ AQ-05 |
| 底稿单元格 | 保存协调器（版本号、prefill_stale、WORKPAPER_SAVED 耐久 outbox） | module=workpaper 符合 ✅；查询路径 `init_workpaper_from_template` / LibreOffice 覆盖 xlsx 不经协调器 ❌ AQ-23 |
| 合并附注 | 归属元组复验 | module=note 符合 ✅ |
| 查询模板 | 删除二次确认 + 回收站 | 前端有二次确认，后端硬删除 ⚠ AQ-30 |
