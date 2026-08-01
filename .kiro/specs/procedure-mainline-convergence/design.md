# 程序裁剪与委派主链收敛 — Design

## 1. 真源与边界
- WorkpaperScopeInstance：`ProcedureInstance.status`，仅表示科目/底稿范围粗裁。
- Workpaper Lead：`WorkingPaper.assigned_to`（user_id）为权威，`ProcedureInstance.assigned_to`（staff_id）为投影。
- Row Task：`ProcedureRowTask.applicability_status/workflow_status/assignee_staff_id/reviewer_staff_id` 为程序行真源。
- Git/迁移承担回滚；不保留第二套线上写链。

## 2. API
- 粗裁：`POST /api/projects/{pid}/procedure-trim/preview|apply`。
- 主编：`PUT /api/projects/{pid}/workpaper-leads`，请求 `{assignments:[{procedure_id,staff_id,request_id}]}`。
- 旧 `/procedures/{cycle}/trim|apply-scheme|batch-apply`、`/procedures/assign`、`/procedures/instance/{id}/execution` 返回 410 + 固定 error code。
- materialize POST 保留同步命令；兼容 `materialize-jobs` POST 同步返回 succeeded；job GET 返回 410。

## 3. 前端流
`ProcedureTrimming.vue` 将当前行转换为 canonical scope entries，先 preview、展示变化统计、确认后以同一 entries + request_id apply；409 清空 preview 并要求重预览。参照项目先 GET 源项目当前程序，再按源 `wp_code/status` 构造 entries。模板与主编请求统一走 `apiPaths/commonApi`。

## 4. 行委派事务
新增 `ProcedureRowDelegationCoordinator`：预检 staff/user、scope、SOD → 调 `ProcedureTaskTransitionService.assign/reassign/set_reviewer` → 仅 changed 时调用 `DelegationTransactionService.record_row_visibility_effects` 写统一历史 + epoch + outbox → flush。协调器不调用旧 `delegate_row()`。

`ProcedureTaskTransitionService` 使用 `_UNSET` 区分“未提供”和真实 `None`；assign/reassign 在 mutation 前捕获四个旧值；`set_reviewer` 只改 reviewer 和 lock_version，不改 assignment_version；reopen 记录 assignee old→None。

## 5. 批量与物化
`ProcedureDelegationService._classify` 增加 `reviewer_update`。apply 的 atomic 模式在单事务内执行；best_effort 每任务 `begin_nested()`。preview 同步 materialize 后重查 targets 并直接创建 ready preview。

## 6. 授权与 rollout
`procedures.py` 的项目写入口使用统一 Delegator dependency；项目读使用成员校验。`_wp_gate.py` 两条生产入口传 `get_epoch_cache()`。rollout 值域采用下划线 `task_source`，增加 `paused`，lifespan 在迁移前执行纯配置合法组合 fail-fast；示例环境变量明确默认 legacy，不自动 cutover。

## 7. 守卫与验证
扩展 AST/文本守卫禁止旧 API 与旧服务调用、禁止协调器/状态机/迁移外直接写行人员字段、禁止 preview 依赖 materialize_job_store、强制 epoch cache 接线。验证覆盖 canonical 参照转换、410、授权、reviewer-only、old/new 快照、事务回滚/savepoint、同步物化、rollout fail-fast、fresh-navigation 五角色关键路径。