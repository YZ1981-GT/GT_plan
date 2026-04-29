# Phase 15: 四级任务树与事件编排补偿 - 实施任务（企业级落地版）

## 阶段0: 规格硬化与实施前置

- [x] 1. 模型与事件目录冻结
  - [x] 1.1 冻结四级节点字典，写入 `backend/app/models/phase15_enums.py::NodeLevel(str, Enum)`：`unit/account/workpaper/evidence`
  - [x] 1.2 冻结任务状态枚举 `TaskNodeStatus(str, Enum)`：`pending/in_progress/blocked/done`，写入同文件
  - [x] 1.3 冻结事件类型枚举 `TaskEventType(str, Enum)`：`trim_applied/trim_rollback/task_reassigned/task_blocked/task_unblocked/issue_created/issue_escalated/issue_closed`
  - [x] 1.4 冻结问题单状态 `IssueStatus(str, Enum)`：`open/in_fix/pending_recheck/closed/rejected`（对齐 v2 4.5.15A）
  - [x] 1.5 冻结问题单来源 `IssueSource(str, Enum)`：`L2/L3/Q`
  - [x] 1.6 冻结问题单严重度 `IssueSeverity(str, Enum)`：`blocker/major/minor/suggestion`
  - [x] 1.7 冻结问题单分类 `IssueCategory(str, Enum)`：`data_mismatch/evidence_missing/explanation_incomplete/procedure_incomplete/policy_violation`（对齐 Phase 14 design §8.2 reason_code）
  - [x] 1.8 冻结 SLA 分级：`P0=4h/P1=24h/P2=72h`，写入 `backend/app/services/issue_ticket_service.py::SLA_HOURS`
  - [x] 1.9 冻结 RC 增强字段清单（对齐 v2 5.9.16 DDL），产出《RC字段变更清单.md》

## 阶段1: MVP核心闭环（任务树主链路）

- [x] 2. 任务树数据模型
  - [x] 2.1 创建 `backend/app/models/phase15_models.py`：
    - `TaskTreeNode` ORM：`id(UUID PK), project_id(UUID), node_level(VARCHAR16), parent_id(UUID nullable), ref_id(UUID), status(VARCHAR16 default 'pending'), assignee_id(UUID nullable), due_at(TIMESTAMP nullable), meta(JSONB nullable), created_at, updated_at`
    - `TaskEvent` ORM：`id(UUID PK), project_id(UUID), event_type(VARCHAR64), task_node_id(UUID nullable), payload(JSONB), status(VARCHAR16 default 'queued'), retry_count(INT default 0), max_retries(INT default 3), next_retry_at(TIMESTAMP nullable), error_message(TEXT nullable), trace_id(VARCHAR64), created_at`
    - `IssueTicket` ORM：`id(UUID PK), project_id(UUID), wp_id(UUID nullable), task_node_id(UUID nullable), conversation_id(UUID nullable), source(VARCHAR16), severity(VARCHAR16), category(VARCHAR64), title(VARCHAR200), description(TEXT nullable), owner_id(UUID), due_at(TIMESTAMP nullable), entity_id(UUID nullable), account_code(VARCHAR20 nullable), status(VARCHAR20 default 'open'), thread_id(UUID nullable), evidence_refs(JSONB default '[]'), reason_code(VARCHAR64 nullable), trace_id(VARCHAR64), created_at, updated_at, closed_at(TIMESTAMP nullable)`
  - [x] 2.2 创建 Alembic 迁移 `backend/alembic/versions/phase15_001_task_tree_and_issues.py`：建 task_tree_nodes + task_events + issue_tickets 三张表 + 全部索引（对齐 migration.sql）
  - [x] 2.3 创建 RC 增强迁移 `backend/alembic/versions/phase15_002_rc_enhancements.py`：
    - ALTER review_conversations 增加 6 字段（priority/sla_due_at/resolved_at/resolved_by/resolution_code/trace_id）
    - ALTER review_messages 增加 7 字段（reply_to/mentions/edited_at/redaction_flag/message_version/trace_id/reason_code）
    - CREATE review_conversation_participants 表
    - CREATE review_conversation_exports 表
    - 全部索引（对齐 migration.sql）

- [x] 3. 任务树服务
  - [x] 3.1 创建 `backend/app/services/task_tree_service.py`：
    - `async build_tree(db, project_id) -> list[TaskTreeNode]` — 从 working_papers + procedure_instances + attachments 构建四级树
    - `async list_nodes(db, project_id, filters: dict, page=1, page_size=50) -> dict` — 分页查询，filters 支持 node_level/status/assignee_id
    - `async get_node(db, node_id) -> TaskTreeNode`
    - `async transit_status(db, node_id, next_status, operator_id) -> TaskTreeNode` — 状态守卫：只允许 `VALID_TRANSITIONS = {('pending','in_progress'), ('in_progress','blocked'), ('blocked','in_progress'), ('in_progress','done')}`，非法迁移抛 `HTTPException(409, 'TASK_STATUS_INVALID_TRANSITION')`
    - `async reassign(db, node_id, assignee_id, operator_id, reason_code) -> TaskTreeNode` — 更新 assignee_id，写 trace_events(event_type='task_reassigned')
    - `async get_stats(db, project_id) -> dict` — 按 node_level × status 聚合统计
  - [x] 3.2 创建 `backend/app/routers/task_tree.py`：
    - `GET /api/task-tree?project_id=&root_level=&status=&assignee_id=&page=&page_size=`
    - `GET /api/task-tree/{node_id}`
    - `PUT /api/task-tree/{node_id}/status` body: `{next_status, operator_id}`
    - `POST /api/task-tree/reassign` body: `{task_node_id, assignee_id, operator_id, reason_code}`
    - `GET /api/task-tree/stats?project_id=`
  - [x] 3.3 注册路由到 `router_registry.py` 第 5 组（底稿管理）

## 阶段2: 事件编排与补偿闭环

- [x] 4. 事件总线服务
  - [x] 4.1 创建 `backend/app/services/task_event_bus.py`：
    - `async publish(db, project_id, event_type, task_node_id, payload, trace_id) -> UUID` — 写入 task_events(status='queued')，返回 event_id
    - `async consume(db, event_id) -> bool` — 执行事件处理逻辑，成功→status='succeeded'，失败→retry_count++，超 max_retries→status='dead_letter'
    - `async replay(db, event_id, operator_id, reason_code) -> dict` — 手动重放：检查 status in ('failed','dead_letter')，重置 retry_count=0 status='queued'，写 trace_events(event_type='event_replayed')
    - 幂等键：`project_id + event_type + payload->ref_id + payload->version`，重复发布返回已有 event_id
    - 重试策略：`next_retry_at = now() + (60 * 5^retry_count)` 秒（1m→5m→25m），超 max_retries=3 进入 dead_letter
  - [x] 4.2 创建 `backend/app/services/task_event_handlers.py`：
    - `async handle_trim_applied(db, payload)` — 查找关联 task_tree_node，transit_status → blocked
    - `async handle_trim_rollback(db, payload)` — 查找关联 task_tree_node，transit_status → in_progress，触发 QC 重跑
    - `async handle_task_reassigned(db, payload)` — 更新子节点 assignee_id（继承规则）
    - 注册到 `task_event_bus.py::EVENT_HANDLERS: dict[str, Callable]`
  - [x] 4.3 创建 `backend/app/routers/task_events.py`：
    - `POST /api/task-events/replay` body: `{event_id, operator_id, reason_code}` → 调用 `task_event_bus.replay()`
    - `GET /api/task-events?project_id=&status=&page=&page_size=` — 查询事件列表（含 dead_letter 筛选）
  - [x] 4.4 接入裁剪事件：`backend/app/routers/procedures.py::update_trim_status()` 在裁剪/恢复时调用 `task_event_bus.publish(event_type='trim_applied'|'trim_rollback')`
  - [x] 4.5 dead-letter 告警：在 `task_event_bus.consume()` 中，status 变为 dead_letter 时调用 `trace_event_service.write(event_type='event_dead_letter', decision='block')` + 日志 `logger.error(f"[DEAD_LETTER] event_id={event_id}")`

## 阶段3: 统一问题单与RC增强

- [x] 5. 问题单服务
  - [x] 5.1 创建 `backend/app/services/issue_ticket_service.py`：
    - `SLA_HOURS = {'P0': 4, 'P1': 24, 'P2': 72}`
    - `async create_from_conversation(db, conversation_id, task_node_id, operator_id, sla_level) -> IssueTicket`：
      - 从 review_conversations 提取 project_id/wp_id/title
      - source 从 operator 角色推断：manager→L2, partner→L3, qc→Q
      - due_at = now() + SLA_HOURS[sla_level] hours
      - 写 trace_events(event_type='issue_created')
    - `async update_status(db, issue_id, status, operator_id, reason_code, evidence_refs=None) -> IssueTicket`：
      - 状态守卫：`VALID_TRANSITIONS = {('open','in_fix'), ('in_fix','pending_recheck'), ('pending_recheck','closed'), ('pending_recheck','rejected'), ('rejected','in_fix')}`
      - 关闭/驳回必须带 reason_code 和 evidence_refs
      - 写 trace_events(event_type='issue_status_changed', from_status=old, to_status=new)
    - `async escalate(db, issue_id, from_level, to_level, reason_code) -> IssueTicket`：
      - 校验 from_level < to_level（L2<L3<Q）
      - 更新 source = to_level
      - 写 trace_events(event_type='issue_escalated')
    - `async check_sla_timeout(db) -> list[IssueTicket]`：
      - 查询 `status IN ('open','in_fix') AND due_at < now()`
      - 超时的自动 escalate 到下一级
    - `async list_issues(db, project_id, filters, page, page_size) -> dict`
  - [x] 5.2 创建 `backend/app/routers/issues.py`：
    - `POST /api/issues/from-conversation` body: `{conversation_id, task_node_id?, operator_id, sla_level}`
    - `GET /api/issues?project_id=&status=&severity=&source=&owner_id=&page=&page_size=`
    - `PUT /api/issues/{issue_id}/status` body: `{status, operator_id, reason_code, evidence_refs[]?}`
    - `POST /api/issues/{issue_id}/escalate` body: `{from_level, to_level, reason_code}`
  - [x] 5.3 注册路由到 `router_registry.py`

- [x] 6. RC 增强服务
  - [x] 6.1 创建 `backend/app/services/rc_enhanced_service.py`：
    - `async add_participant(db, conversation_id, user_id, role, is_required_ack=False) -> ReviewConversationParticipant`
    - `async remove_participant(db, conversation_id, user_id) -> None` — 软删除 is_deleted=True
    - `async export_evidence(db, conversation_id, purpose, receiver, export_scope, mask_policy, include_hash_manifest, requested_by) -> ReviewConversationExport`：
      - 校验必填：purpose/receiver/mask_policy 非空，否则 400 RC_REQUIRED_FIELD_MISSING
      - 构建导出内容（按 export_scope: full_timeline=全部消息+附件, summary=摘要, attachments_only=仅附件）
      - 计算 file_hash = SHA-256
      - 写入 review_conversation_exports(status='ready')
      - 写 trace_events(event_type='rc_evidence_exported')
    - `async check_closed_state_guard(db, conversation_id, message_type) -> None`：
      - 查询 conversation status，如果 IN ('closed','resolved') 且 message_type='text'，抛 422 RC_CONVERSATION_CLOSED
  - [x] 6.2 修改 `backend/app/routers/review_conversations.py`：
    - 现有 `POST /{id}/messages` 入口增加调用 `rc_enhanced_service.check_closed_state_guard()`
    - 新增 `POST /api/review-conversations/{id}/export-evidence`
    - 新增 `POST /api/review-conversations/{id}/participants` body: `{user_id, role, is_required_ack?}`
    - 新增 `DELETE /api/review-conversations/{id}/participants/{user_id}`
  - [x] 6.3 创建 `backend/app/schemas/phase15_schemas.py`：
    - `TaskTreeNodeSchema`, `TaskEventSchema`, `IssueTicketSchema`, `IssueFromConversationRequest`, `IssueStatusUpdateRequest`, `IssueEscalateRequest`
    - `RCExportEvidenceRequest`, `RCExportEvidenceResponse`, `RCParticipantRequest`
    - 所有响应统一包含 `trace_id` 字段

- [x] 7. 问题线程升级链路
  - [x] 7.1 SLA 超时定时任务：在 `backend/app/main.py` lifespan 中注册 `asyncio.create_task(_sla_check_loop())`，每 15 分钟调用 `issue_ticket_service.check_sla_timeout()`
  - [x] 7.2 升级通知：超时升级时调用 `notification_service.send(user_id=escalated_owner, type='issue_sla_timeout', payload={issue_id, sla_level})`
  - [x] 7.3 前端 `audit-platform/frontend/src/views/IssueTicketList.vue`：
    - 表格列：ID/标题/来源(L2/L3/Q 标签色)/严重度/状态/负责人/SLA 倒计时/创建时间
    - SLA 倒计时：距 due_at 剩余时间，<4h 红色，<24h 橙色
    - 筛选栏：项目/状态/严重度/来源/负责人
    - 行操作：查看详情/更新状态/升级
  - [x] 7.4 前端 `audit-platform/frontend/src/views/TaskTreeView.vue`：
    - 左栏：el-tree 四级展开（unit→account→workpaper→evidence），懒加载
    - 节点状态色：pending 灰/in_progress 蓝/blocked 红/done 绿
    - 右栏：选中节点详情（assignee/due_at/meta/关联问题单列表）
    - 操作：转派/变更状态/查看事件历史
  - [x] 7.5 前端 `audit-platform/frontend/src/services/phase15Api.ts`：
    - `listTaskTree(params)`, `reassignNode(params)`, `transitStatus(params)`, `getTreeStats(params)`
    - `replayEvent(params)`, `listEvents(params)`
    - `createIssueFromConversation(params)`, `listIssues(params)`, `updateIssueStatus(params)`, `escalateIssue(params)`
    - `exportConversationEvidence(params)`, `addParticipant(params)`, `removeParticipant(params)`

## 阶段4: 增强能力

- [x] 8. 流程增强
  - [x] 8.1 节点转派继承：`task_tree_service.reassign()` 中，如果 node_level='unit'|'account'，自动更新所有子节点 assignee_id
  - [x] 8.2 程序恢复联动：`task_event_handlers.handle_trim_rollback()` 中，受影响节点自动 transit_status → in_progress，并触发 `gate_engine.evaluate()` 重新评估
  - [x] 8.3 与风险看板联动：`pm_dashboard.py::get_progress_board()` 增加从 task_tree_nodes 聚合的完成率数据

## 阶段5: 企业级增强

- [x] 9. 运维监控
  - [x] 9.1 Prometheus 指标：
    - `task_event_dead_letter_total` (counter) — dead-letter 进入数
    - `task_event_compensation_success_total` (counter) — 补偿成功数
    - `task_event_compensation_fail_total` (counter) — 补偿失败数
    - `task_tree_query_duration_seconds` (histogram, labels: node_level)
    - `issue_sla_timeout_total` (counter, labels: sla_level)
  - [x] 9.2 告警规则：
    - `task_event_dead_letter_total > 10` 持续 30min → P1
    - `rate(task_event_compensation_fail_total[1h]) / rate(task_event_compensation_success_total[1h]) > 0.05` → P1
    - `histogram_quantile(0.95, task_tree_query_duration_seconds) > 2` 持续 5min → P2
    - `issue_sla_timeout_total > 0` 持续 4h → P0

- [x] 10. 数据迁移
  - [x] 10.1 创建 `backend/scripts/phase15/init_task_tree.py`：从 working_papers + procedure_instances 构建初始 task_tree_nodes（unit 从 projects，account 从 trial_balance distinct account_code，workpaper 从 working_papers，evidence 从 attachments）
  - [x] 10.2 RC 增强字段回填：`backend/scripts/phase15/backfill_rc_fields.py` — 历史 review_conversations 设 priority='medium'/trace_id=null，历史 review_messages 设 message_version=1/redaction_flag=false
  - [x] 10.3 现有 review_records 与 issue_tickets 共存策略：新问题走 issue_tickets，历史 review_records 保留只读，前端问题列表同时查两张表合并展示

- [x] 11. 灰度与回滚
  - [x] 11.1 创建 `backend/scripts/phase15/rollback_task_tree.py`：TRUNCATE task_tree_nodes + task_events（不影响业务数据）
  - [x] 11.2 创建 `backend/scripts/phase15/rollback_issues.py`：issue_tickets 状态回退到 open + 清理通知
  - [x] 11.3 执行一次完整回滚演练，产出《Phase15回滚演练报告.md》

- [x] 12. 前端交互规范
  - [x] 12.1 TaskTreeView 性能：el-tree lazy 加载，每级最多渲染 200 节点，超出分页
  - [x] 12.2 IssueTicketList SLA 倒计时：`setInterval` 每分钟刷新，<1h 时每 10 秒刷新
  - [x] 12.3 RC 关闭态门禁：`ReviewConversationDetail.vue` 输入框根据 conversation.status 动态 disabled，关闭态显示 "会话已关闭" + trace_id
  - [x] 12.4 RC 实时消息：SSE `GET /api/review-conversations/{id}/messages/stream`，断连指数退避重试（1s→2s→4s→8s max），重连后用 `last_message_cursor` 补拉

- [x] 13. CI 门槛
  - [x] 13.1 PR 阶段：`python -m pytest backend/tests/test_phase15*.py -v` 通过率 = 100%
  - [x] 13.2 预发阶段：全量 IT 通过率 >= 99%
  - [x] 13.3 生产前：`check_task_tree_integrity.py` + `check_event_idempotency.py` + `check_issue_sla_escalation.py` + `check_rc_export_compliance.py` 全部 PASS

## 测试与验收

- [x] 14. 单元测试 `backend/tests/test_phase15_tree.py`
  - [x] P15-UT-001: build_tree 从 3 个 working_papers 构建 → 返回 3 个 workpaper 节点
  - [x] P15-UT-002: transit_status pending→in_progress → 成功
  - [x] P15-UT-003: transit_status pending→done → 409 TASK_STATUS_INVALID_TRANSITION
  - [x] P15-UT-004: transit_status blocked→in_progress → 成功
  - [x] P15-UT-005: reassign unit 节点 → 子节点 assignee_id 同步更新
  - [x] P15-UT-006: get_stats → 按 node_level × status 聚合正确

- [x] 15. 单元测试 `backend/tests/test_phase15_events.py`
  - [x] P15-UT-007: publish 幂等 → 同 payload 返回同 event_id
  - [x] P15-UT-008: consume 成功 → status='succeeded'
  - [x] P15-UT-009: consume 失败 → retry_count++ + next_retry_at 设置
  - [x] P15-UT-010: consume 超 max_retries → status='dead_letter'
  - [x] P15-UT-011: replay dead_letter → status='queued' + retry_count=0
  - [x] P15-UT-012: handle_trim_applied → 关联节点 status='blocked'
  - [x] P15-UT-013: handle_trim_rollback → 关联节点 status='in_progress' + QC 重跑触发

- [x] 16. 单元测试 `backend/tests/test_phase15_issues.py`
  - [x] P15-UT-014: create_from_conversation → issue_ticket 创建成功 + due_at 正确
  - [x] P15-UT-015: update_status open→in_fix → 成功
  - [x] P15-UT-016: update_status open→closed → 409（跳过 in_fix）
  - [x] P15-UT-017: escalate L2→L3 → source 更新 + trace 写入
  - [x] P15-UT-018: escalate L3→L2 → 409（不允许降级）
  - [x] P15-UT-019: check_sla_timeout → 超时 issue 自动升级

- [x] 17. 单元测试 `backend/tests/test_phase15_rc.py`
  - [x] P15-UT-020: check_closed_state_guard closed + text → 422 RC_CONVERSATION_CLOSED
  - [x] P15-UT-021: check_closed_state_guard open + text → 通过
  - [x] P15-UT-022: export_evidence 缺 purpose → 400 RC_REQUIRED_FIELD_MISSING
  - [x] P15-UT-023: export_evidence 完整参数 → 返回 export_id + file_hash
  - [x] P15-UT-024: add_participant → 写入 review_conversation_participants

- [x] 18. 集成测试 `backend/tests/test_phase15_integration.py`
  - [x] P15-IT-001: trim_applied 事件 → task_tree_node blocked → 补偿重放 → in_progress
  - [x] P15-IT-002: 创建对话 → 发消息 → 转问题单 → 升级 L2→L3 → 关闭 → 全链路 trace 完整
  - [x] P15-IT-003: 导出取证 → hash 生成 → review_conversation_exports 记录写入
  - [x] P15-IT-004: 关闭态发送消息 → 422 RC_CONVERSATION_CLOSED
  - [x] P15-IT-005: RC 错误码一致性：所有 RC_ 前缀错误码与 v2 5.9.14.7 一致

- [x] 19. 非功能测试
  - [x] P15-PERF-001: 5000 节点 task_tree 查询 P95 <= 1s
  - [x] P15-PERF-002: 100 个并发 publish → 幂等正确 + 无重复 event
  - [x] P15-CONTRACT-001: `/api/task-tree` 合同测试（字段类型/枚举值）
  - [x] P15-CONTRACT-002: `/api/issues` 合同测试
  - [x] P15-CONTRACT-003: `/api/review-conversations/{id}/export-evidence` 合同测试

## 验收脚本（必须产出）

- [x] 20. 脚本化验收
  - [x] 20.1 `backend/scripts/phase15/check_task_tree_integrity.py` — 断言所有节点 parent_id 引用有效 + status 枚举值合法
  - [x] 20.2 `backend/scripts/phase15/check_event_idempotency.py` — 同 payload 发布 2 次，断言 event_id 相同
  - [x] 20.3 `backend/scripts/phase15/check_compensation_replay.py` — 创建 failed 事件 → replay → 断言 status='queued'
  - [x] 20.4 `backend/scripts/phase15/check_issue_sla_escalation.py` — 创建 P0 issue + 模拟 5h 超时 → 断言自动升级到 L3
  - [x] 20.5 `backend/scripts/phase15/check_rc_export_compliance.py` — 导出取证 → 断言 file_hash 非空 + trace_events 有记录
  - [x] 20.6 `backend/scripts/phase15/check_rc_closed_state_guard.py` — 关闭会话 → 发消息 → 断言 422

## 放行门槛（Go/No-Go）

- [x] G1 四级任务树主路径可用：P15-UT-001~006 + P15-IT-001 通过
- [x] G2 trim 事件失败补偿可追溯率 = 100%：P15-UT-007~013 + check_compensation_replay.py 通过
- [x] G3 问题单升级 SLA 达标率 >= 95%：P15-UT-014~019 + check_issue_sla_escalation.py 通过
- [x] G4 任务树查询性能达标 P95 <= 1s：P15-PERF-001 通过
- [x] G5 issue_tickets L2/L3/Q 可检索可追溯：P15-IT-002 通过
- [x] G6 RC 关闭态写入阻断生效：P15-UT-020/021 + P15-IT-004 通过
- [x] G7 RC 取证导出合规率 = 100%：P15-UT-022/023 + P15-IT-003 + check_rc_export_compliance.py 通过
- [x] G8 RC 接口返回统一结构 code/message/data/trace_id：P15-CONTRACT-001~003 通过
- [x] G9 灰度回滚演练通过：rollback_task_tree.py + rollback_issues.py 执行成功
- [x] G10 CI 门槛全部 PASS
