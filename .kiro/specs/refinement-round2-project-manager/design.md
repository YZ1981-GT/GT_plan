# Refinement Round 2 — 设计文档

## 概要

本轮聚焦项目经理视角，让 PM 有专属工作台 + 通知铃铛 + 强化委派/催办/工时审批 + 跨项目简报。所有设计遵守 [README v2.2](../refinement-round1-review-closure/README.md)。

实施依赖：R1 需求 2 的 `IssueTicket.source` 枚举扩展必须先完成，本轮直接复用 `source='client_commitment' / 'reminder'`。

## 架构决策一览

| 决策 | 方案 | 理由 |
|------|------|------|
| 通知铃铛组件复用 | 直接挂 `NotificationCenter.vue` 到 `DefaultLayout` 的 `#nav-notifications` slot | 组件/store/API 都齐全（代码锚定），缺的只是入口 |
| PM 看板数据聚合 | 后端新建 `ManagerDashboardService`，整合现有 `ReviewInboxService + WorkingPaperService + AssignmentService + WorkHourService` | 不新建底层表，只做聚合端点 |
| 沟通记录承诺升级 | `Project.wizard_state.communications[].commitments` 从 string 升级为结构化数组 | `ClientCommunicationService` 已存在，不新建表 |
| 催办语义修正 | 不说"逾期"只说"已创建 N 天尚未完成" | `WorkingPaper` 无 `due_date`，严格锚定现有数据 |
| 简报跨项目合并 | 新端点 `POST /briefs/batch`，内部调 N 次现有 `ProgressBriefService` 拼接 | 不重写简报引擎 |
| 工时审批幂等 | `idempotency_key` 头 + Redis 5 分钟防重 | 网络抖动不致双批准 |
| 已读回执展示 | 查询时实时算（用现有 `Notification.is_read + read_at`） | 无需新 worker |
| SSE 推送通知 | 复用 `event_bus._notify_sse`，不新增 WebSocket | 现有 SSE 基础设施够用 |

## 数据模型变更

### 修改现有 JSONB 字段结构

```python
# Project.wizard_state['communications'][i] 升级
# 既有:
{
  "id": "...", "date": "...", "contact_person": "...",
  "topic": "...", "content": "...",
  "commitments": "string",  # ← 本轮升级
  "related_wp_codes": [...], "related_accounts": [...]
}

# 升级后:
{
  ...,
  "commitments": [
    {
      "id": "uuid",
      "content": "本周五前提供银行询证函回函",
      "due_date": "2026-05-10",
      "status": "pending" | "done" | "overdue",
      "related_pbc_id": "uuid?",
      "issue_ticket_id": "uuid",  # 双向关联
      "completed_at": "datetime?"
    }
  ]
}
```

**兼容迁移策略**：`ClientCommunicationService.list_communications` 读取时判断 `commitments` 类型，若为 string 则自动包装为 `[{content: str, due_date: null, status: 'pending'}]`。写入强制为数组。

### 新增表

无。本轮全部复用既有模型。

### 新增/使用枚举

```python
# 依赖 R1 需求 2 已扩展:
IssueTicket.source: 'reminder' | 'client_commitment' (复用)

# WorkHourRecord.status (既有): draft | confirmed | approved (本轮使用 approved 流转)
# 本轮不改模型，只扩展业务流
```

## API 变更

### 新增端点

```
GET   /api/dashboard/manager/overview
  resp: {projects: [...], cross_todos: {...}, team_load: [...]}
  权限: role='manager' or project_assignment.role IN ('manager','signing_partner')

GET   /api/dashboard/manager/assignment-status?days=7
  resp: [{wp_code, assignee_name, assigned_at, notification_read_at|null}]

POST  /api/projects/{project_id}/workpapers/{wp_id}/remind
  body: {message?: str}
  resp: {ticket_id, notification_id, remind_count, allowed_next}

POST  /api/projects/briefs/batch
  body: {project_ids: UUID[], use_ai: bool}
  resp: {export_job_id}  异步，前端轮询

POST  /api/workhours/batch-approve
  body: {hour_ids: UUID[], action: 'approve'|'reject', reason?: str}
  header: Idempotency-Key: <uuid>
  resp: {approved_count, rejected_count, failed: [...]}

POST  /api/workpapers/batch-assign-enhanced  (在现有 batch-assign 基础上包装)
  body: {wp_ids, strategy: 'manual'|'round_robin'|'by_level', 
         candidates: [user_id], reviewer_id?, override_assignments?: [{wp_id, user_id}]}
  resp: {assignments: [...]}  返回预览/已执行
```

### 修改端点

```
POST  /api/projects/{project_id}/communications
  内部：若 body.commitments 是数组，每项创建 IssueTicket(source='client_commitment')
  内部：记 issue_ticket_id 回写到 commitments[i].issue_ticket_id

DELETE /api/projects/{project_id}/communications/{comm_id}
  内部：级联关闭关联的 client_commitment IssueTicket

PATCH /api/projects/{project_id}/communications/{comm_id}/commitments/{commitment_id}
  标记承诺完成；关闭关联 ticket；时间线追加"✅ 已完成"
```

## 前端变更

### 新增页面

```
src/views/ManagerDashboard.vue         (聚合看板)
src/views/WorkHoursApproval.vue        (批量审批)
src/components/assignment/BatchAssignDialog.vue  (策略+预览)
src/components/pm/CommunicationCommitmentsEditor.vue  (承诺编辑器)
src/components/pm/CrossProjectBriefExporter.vue
```

### 修改

```
src/layouts/DefaultLayout.vue    (#nav-notifications slot 挂 NotificationCenter)
src/stores/collaboration.ts      (startup 调 fetchNotifications + 订阅 SSE 通知类型)
src/views/ProjectDashboard.vue   (overdue 表新增催办/重新分配按钮)
src/views/ProjectProgressBoard.vue  (CommunicationCommitmentsEditor 替换旧字符串输入)
src/views/WorkpaperList.vue      (批量委派弹窗改为 BatchAssignDialog)
src/router/index.ts              (新增 /dashboard/manager、/work-hours/approve 路由)
src/composables/usePermission.ts (ROLE_PERMISSIONS 扩展 manager 的 view_dashboard_manager / approve_workhours)
```

## 跨轮约束遵守

| 约束 | 本轮落地方式 |
|------|--------------|
| 1 Notification type 统一字典 | 本轮新增：`workpaper_reminder / workhour_approved / workhour_rejected / assignment_created / commitment_due` |
| 2 权限四点同步 | PM 新动作 `approve_workhours / send_reminder / batch_brief` 加入权限字典 |
| 3 状态机不重叠 | 不涉及 |
| 4 SOD | 工时审批人不能是被审批人自己，复用 `sod_guard_service` |
| 5 自然日 SLA | 催办 "7 天内最多 3 次" 按自然日 |
| 6 归档章节化 | 不涉及 |
| 7 i18n | 不涉及新 role |
| 8 焦点时长隐私 | 不涉及 |

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| SSE 连接 6000 并发下压力 | SSE per-user 队列；按需订阅通知类型过滤；离线期间积压从 DB 补拉 |
| commitments 升级迁移破坏既有数据 | 读时自动兼容 string（ClientCommunicationService 包装），写时强制数组 |
| 轮询批量简报长时间挂起 | 走 ExportJobService 异步，前端轮询 status，超 10 分钟强制 timeout |
| 经理看板 6000 并发查询压 DB | 聚合 endpoint 走 Redis 缓存 5 分钟，带 project_id 列表作为缓存键 |
| 批量委派策略选错分给错人 | 预览表强制展示所有分配，用户确认后才提交；提交后可 1 小时内批量撤销 |

## 测试策略

- **单元测试**：`BatchAssignStrategy` 三种策略（manual/round_robin/by_level）各 3 个用例
- **集成测试**：`test_manager_dashboard_e2e.py` 走完：创建项目 → 委派 → 催办 → 工时提交 → 审批 → 简报导出
- **并发测试**：`test_workhour_batch_approve_idempotency.py` 模拟同 key 重复提交 10 次，结果一致
- **回归**：现有 `batch-assign` 原端点继续可用

## 补充设计（v1.1，需求 9~10）

### 需求 9 预算与成本

```python
# Project 扩展
budget_hours: int | None
contract_amount: Decimal | None  # Numeric(20, 2)
budgeted_by: UUID | None
budgeted_at: datetime | None

# system_settings.hourly_rates = {
#   'partner': 3000, 'manager': 1500, 'senior': 900, 'auditor': 500, 'intern': 200
# }
```

`cost_overview_service.compute` 纯函数，按项目内 `WorkHourRecord.status='approved'` 分组 role 乘以 rate 得成本；burn_rate_per_day = 近 14 天已批准工时 / 14；projected_overrun_date = remaining_hours / burn_rate_per_day。

`budget_alert_worker` 每日凌晨扫描，幂等键 `budget_alert:{project_id}:{threshold}:{YYYYMMDD}`，一天内同阈值不重复发。

### 需求 10 交接

```python
# backend/app/models/handover_models.py
class HandoverRecord(Base, TimestampMixin):
    id, from_staff_id, to_staff_id, scope ('all' | 'by_project'),
    project_ids: list[UUID] | None,
    reason_code, reason_detail,
    effective_date: date,
    workpapers_moved: int, issues_moved: int, assignments_moved: int,
    executed_by: UUID, executed_at
```

`handover_service.execute` 同事务：
1. WorkingPaper.assigned_to / reviewer 批量 UPDATE
2. IssueTicket.owner_id 批量 UPDATE
3. ProjectAssignment 软删除 from_staff + 新增 to_staff
4. 写 HandoverRecord 汇总
5. 调 audit_logger_enhanced.log_action(action_type='staff_handover')

resignation 时同步标记 `IndependenceDeclaration.status='superseded_by_handover'`（R1 需求 10 联动），避免被 gate 阻断。

**风险**：事务过大可能锁表。分批执行（每批 100 条），失败重试从上次断点续跑。
