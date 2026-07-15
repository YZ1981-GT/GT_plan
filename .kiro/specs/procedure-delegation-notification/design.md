# Design Document

## Overview

本设计把程序行拆成两层真源：模板级 `ProcedureRowDefinition` 负责跨项目稳定身份与 revision；项目级 `ProcedureRowTask` 负责适用性、委派、执行与操作复核。现有 `ProcedureInstance` 仅保留为 WorkpaperScopeInstance 粗裁兼容层，`WorkingPaper.parsed_data.procedure_status` 仅保留为可重建投影。

核心约束是“读路径绝不物化”：GET、render-config、列表和深链只读取 definition/task 并生成 overlay；只有显式 POST materialize、项目初始化、delegation preview 前置 materialize job、reconcile apply、backfill 可以写。任务以 `project_id + wp_index_id` 锚定，允许 `wp_id=NULL` 先委派后生成；底稿生成时只原子绑定既有 task，不换 task_id。

目标链路：

```text
模板导入 → ProcedureRowDefinition(definition_key, normalized SHA-256 revision)
                         ↓ explicit materialize / project init / preview job
项目+wp_index → ProcedureRowTask(wp_id nullable, task truth)
                         ↓ reconcile / trim / secure preview
循环·科目·行委派 → ack → start → submit → 一级复核/退回
                         ↓ same transaction
ordered Delivery Outbox → aggregate Notification → at-least-once SSE
                         ↓ overlay / deep link
MyProcedureTasks.vue + GtAProgramConsole + parsed_data compatibility projection
```

## Architecture

系统分为模板定义层、项目任务领域层、兼容投影层、可靠投递层和前端交互层。定义层只在显式导入时写；任务领域层通过 command service 写入；查询与 render 只组合 overlay；outbox 在领域事务内写意图、在独立 dispatcher 事务中生成通知；前端始终重新查询任务真源收敛状态。

## Components and Interfaces

核心接口由 `ProcedureDefinitionImporter`、`ProcedureTaskMaterializationService`、`ProcedureReconcileService`、`ProcedureTrimService`、`ProcedureDelegationService`、`ProcedureTaskTransitionService`、`ProcedureProjectionService`、`ProcedureReviewService`、`ProcedureDeliveryDispatcher` 与 `ProcedureTaskQueryService` 组成。所有 mutation 经项目/参与者 guard；所有 GET 只调用 query/overlay 纯读接口。

## Architecture Decisions

### D1. definition_key 是模板身份，task_id 是项目工作流身份

`definition_key` 由模板代码、稳定 sheet key、source locator 与定义语义形成，不含 project_id、wp_id、数组位置或 mtime。`template_revision_hash` 对规范化定义集合做 SHA-256。项目任务只引用 definition_key 并保存 revision/text/ref 快照；模板升级通过 reconcile 显式关联，不通过模糊覆盖继承。

### D2. 项目锚点先于底稿实例

`ProcedureRowTask(project_id, wp_index_id, sheet_key, definition_key)` 在底稿生成前即可存在。`wp_id` 是可后绑定外键。唯一性使用 active partial unique，不使用 wp_id；绑定服务在底稿创建事务中锁定同锚点任务并批量更新 wp_id，业务身份与 assignment_version 均保持不变。

### D3. Command/Query 分离禁止 GET 写库

- Query：GET/render-config 只读 definition/task，缺 task 时返回 `task_id=null, materialization_required=true`。
- Command：POST materialize、初始化、preview materialize job、reconcile apply、backfill。
- `render-config` 不调用任何 upsert/materialize/projector write。
- delegation preview 若缺任务，先提交 materialize job；job 完成后客户端重新请求 preview，而不是在 preview HTTP 事务中隐式写。

### D4. ProcedureOperationPreview 是敏感操作的一次性凭证

裁剪应用、委派、转派等操作统一保存 server-side preview。preview 绑定 actor user、project、operation、规范 request hash、目标 lock/assignment versions、active membership snapshot hash、scheme revision、TTL。apply 在事务内 `SELECT FOR UPDATE` preview，校验后设置 consumed_at/result；并发消费最多一次成功。相同 request_id 重试只返回保存结果。

### D5. staff 与 user 的边界唯一

assignee/reviewer 外键均指向 StaffMember；actor、history actor、notification recipient 指向 User。授权/SOD 统一通过 active StaffMember.user_id 归一，禁止比较 staff id 推断是否同人。partner/signing_partner/manager 都必须有当前项目 active ProjectAssignment；只有 admin 全局放行。

### D6. 程序行只做操作复核

`reviewer_staff_id` 表示操作复核人/一级复核人。任务 reviewed 只结束程序行一级复核，不改变底稿或项目层 partner/QC/EQCR 状态。高阶复核继续沿用既有机制，数据模型和 UI 不把这些角色塞进 reviewer_staff_id。

### D7. 任务真源与精确投影

TransitionService 先更新 task/history/outbox，再以 `jsonb_set` 更新单一 `parsed_data.procedure_status.{sheet_key}.{definition_key}` 路径。投影写使用 WorkingPaper version 条件或行锁；不同路径并发更新均保留。render 以 task overlay 覆盖 legacy 值；投影可删除后全量重建。

### D8. 有序 outbox 与聚合通知分离

每个 task 的领域变化都有独立 history/outbox event；同 aggregate 按 version 顺序。批量委派不把 N 个审计事件压成一个，但 NotificationProjection 按 `delegation_batch_id + recipient_user_id` 聚合用户通知，避免通知风暴。SSE 是 at-least-once，前端只按 event_id 去重后重新拉取。
## Data Models

### V105 Expand Overview

### procedure_row_definitions

| 字段 | 类型/约束 | 说明 |
|---|---|---|
| id | UUID PK | 内部主键 |
| definition_key | varchar(200) NOT NULL UNIQUE | 跨项目稳定身份 |
| template_code | varchar(80) NOT NULL | 模板/工作底稿编码 |
| template_revision_hash | char(64) NOT NULL | 规范化内容 SHA-256 |
| sheet_key | varchar(160) NOT NULL | 稳定 sheet key |
| source_locator | JSONB NOT NULL | 原始 JSON/xlsx 定位信息 |
| program_no | varchar(80) NULL | 展示程序号 |
| procedure_text | text NOT NULL | 规范程序文本 |
| ref_snapshot | JSONB NOT NULL DEFAULT '[]' | ref_index/auto source 快照 |
| legacy_aliases | JSONB NOT NULL DEFAULT '[]' | row-N/旧 key/历史定位 |
| normalized_content | JSONB NOT NULL | 哈希输入的规范形式 |
| created_at/updated_at | timestamptz | 生命周期 |

建议唯一约束：`(template_code, template_revision_hash, sheet_key, definition_key)`；definition_key 自身保持全局唯一。规范化规则：Unicode NFKC、换行统一、文本首尾 trim、对象 key 排序、数组仅在语义无序字段上排序；source_locator 去除绝对路径、mtime、导入时间。revision hash 对按 `(sheet_key, source_locator stable part, definition_key)` 排序后的定义集合做 canonical JSON SHA-256。

### procedure_row_tasks

| 字段 | 类型/约束 | 说明 |
|---|---|---|
| id | UUID PK | task_id |
| project_id | UUID FK NOT NULL | 项目边界 |
| wp_index_id | UUID FK NOT NULL | 项目底稿索引锚点 |
| wp_id | UUID FK NULL | 后生成底稿绑定 |
| definition_key | varchar(200) FK NOT NULL | 模板定义引用 |
| sheet_key | varchar(160) NOT NULL | 项目行定位 |
| wp_code/sheet_name/program_no/procedure_text/ref_snapshot | snapshot fields | 审计/展示快照 |
| definition_revision_hash | char(64) NOT NULL | 物化时 revision |
| audit_cycle_snapshot | varchar(40) NOT NULL | 委派/审计周期快照 |
| applicability_status | varchar NOT NULL | execute/not_applicable |
| workflow_status | varchar NOT NULL | 独立状态机 |
| assignee_staff_id | UUID FK staff_members NULL | 执行人 |
| reviewer_staff_id | UUID FK staff_members NULL | 操作复核人 |
| assignment_version | integer NOT NULL DEFAULT 0 | 每次有效 assignment 递增 |
| lock_version | integer NOT NULL DEFAULT 0 | 全任务乐观锁 |
| due_at | timestamptz NULL | 可选截止时间 |
| assigned/acknowledged/started/submitted/reviewed/cancelled_at | timestamptz NULL | SLA 时间 |
| execution_summary/evidence_snapshot | text/JSONB | 提交材料 |
| migration_confidence | varchar NULL | exact/conservative/conflict |
| migration_detail | JSONB NOT NULL DEFAULT '{}' | 旧状态证据/冲突 |
| is_deleted/created_at/updated_at | standard fields | 生命周期 |

关键 DDL：

```sql
CREATE UNIQUE INDEX uq_procedure_row_tasks_active
ON procedure_row_tasks(project_id, wp_index_id, sheet_key, definition_key)
WHERE is_deleted = false;
```

所有 upsert 必须使用同一列和同一谓词：

```sql
ON CONFLICT (project_id, wp_index_id, sheet_key, definition_key)
WHERE is_deleted = false DO UPDATE ...
```

禁止使用 `ON CONFLICT (wp_id, ...)`。assignee/reviewer covering index 以 staff→user 项目查询为目标，分别从 `(assignee_staff_id, workflow_status, due_at, project_id)` 与 `(reviewer_staff_id, workflow_status, due_at, project_id)` 起始，并 INCLUDE `(id, wp_index_id, wp_id, sheet_key, definition_key, lock_version, assignment_version)`；最终顺序以真实查询计划验证。

### procedure_row_task_history

追加式保存 `task_id, project_id, event_type, from_status, to_status, old/new_assignee_staff_id, old/new_reviewer_staff_id, actor_user_id, reason, request_id, assignment_version, lock_version, definition_revision_hash, audit_cycle_snapshot, detail, created_at`。`(task_id, request_id, event_type)` 唯一，禁止覆盖更新历史。

### procedure_operation_previews

保存 `id, actor_user_id, project_id, operation, request_hash, request_payload_snapshot, target_versions, membership_snapshot, membership_snapshot_hash, scheme_revision, expires_at, consumed_at, consumed_request_id, result, created_at`。active preview 按 actor/project/operation 查询；消费必须行锁。request hash 使用 canonical JSON SHA-256，敏感正文只存必要摘要。

### delivery_outbox / notifications

Delivery outbox 在现有 task_events 基础上扩展：`aggregate_type, aggregate_id, aggregate_version, event_type, idempotency_key, delegation_batch_id, payload, available_at, lease_expires_at, claimed_by, processed_at, retry_count, dead_letter_at, last_error`。唯一 `idempotency_key`；claim partial index 面向 `processed_at IS NULL AND dead_letter_at IS NULL`，以 available_at/lease_expires_at/aggregate/version 排序。

Notification 增 `event_id, recipient_user_id, dedup_key, metadata`；唯一 dedup 至少等价于 `(event_id, recipient_user_id)`。批量摘要的 event_id 使用聚合投影事件，metadata 保留 underlying task event ids 与 batch id。
## Backend Components

### C1. ProcedureDefinitionImporter

- 从 JSON 模板与 xlsx fallback 提取定义。
- 执行规范化、revision SHA-256 与 definition_key 生成。
- import 是显式写命令；render 只读取已导入定义。
- 保留旧 revision，不按 mtime 覆盖。

### C2. ProcedureTaskMaterializationService

```python
materialize(project_id, wp_index_ids, definition_revision, actor, request_id)
bind_working_paper(project_id, wp_index_id, wp_id, request_id)
```

materialize 批量查询 definitions，使用 active partial unique upsert；已存在任务只允许补充安全快照，不改 assignment/workflow。bind 在底稿生成事务中锁定 wp_index 与 active tasks，验证 wp 属于同 project/wp_index 后一次更新 nullable wp_id。项目初始化和 backfill 直接复用该服务；delegation preview 通过 materialize job 调用。

### C3. ProcedureReconcileService

preview 产生 exact key、legacy alias、unique normalized match、ambiguous、orphaned、conflict 分类；apply 使用 ProcedureOperationPreview。只有显式 resolution 才能迁移 task 关联；IssueTicket/history 不复制到不确定定义。模板升级后旧 task 可保留 orphaned 快照供审计。

### C4. ProcedureTrimService

保留 WorkpaperScopeInstance 粗裁并管理 task applicability。细裁 not_applicable 调 TransitionService cancel；恢复先改 execute，再由 Delegator reopen→assign。scheme 保存 canonical key。trim preview/apply 与 delegation 共用 ProcedureOperationPreview 安全模型和真实 applied 计数。

### C5. ProcedureProjectAuthorization

`require_project_delegator` 规则：

1. authenticated admin：全局通过。
2. 其余 user：唯一 active StaffMember(user_id)；唯一 active ProjectAssignment(project_id, staff_id)。
3. assignment role 必须在 partner/signing_partner/manager。
4. 任何缺失、重复、inactive、查询异常均 403。

participant guard 从 task 反查 project/wp_index/wp；动作授权比较归一化 user，而非 staff id。历史参与者通过 history/conversation/issue 建只读 access set。

### C6. ProcedureDelegationService

`DelegationResolver` 把 cycle/workpaper/row selector 转为任务集合。preview 若发现 materialization_required，返回/启动 job 并处于 pending；完成后创建 ProcedureOperationPreview。apply 默认整批原子，支持显式 best_effort。首次分配或换人递增 assignment_version、清 ack；同人重复分配为 no-op。每 task 独立 history/outbox，并共享 delegation_batch_id。

### C7. ProcedureTaskTransitionService

状态转换表：

| action | from | to | actor | 关键条件 |
|---|---|---|---|---|
| assign | unassigned | assigned | Delegator | active assignee；assignment_version+1 |
| acknowledge | assigned | acknowledged | assignee | assignment_version 匹配；重复为 no-op |
| start | acknowledged / changes_requested | in_progress | assignee | wp_id 非空、execute |
| submit | in_progress | submitted | assignee | 说明/证据快照完整 |
| request_changes | submitted | changes_requested | reviewer | 创建/复用 IssueTicket |
| review | submitted | reviewed | reviewer | 全部关联 IssueTicket closed |
| cancel | 任意未终态 | cancelled | Delegator/trim | 原因必填 |
| reopen | cancelled | unassigned | Delegator | 不保留 ack；后续重新 assign |

`assign` 不接受 cancelled；`start` 不接受 bare assigned，确保每次 assignment 都 ack。reviewer 缺失时 submitted 可保留，但 review 被阻止并产生 reviewer_missing event。所有成功转换：task update + history + outbox + 精确 projection 同事务。

### C8. ProcedureProjectionService

- `overlay(definitions, tasks, legacy_projection)` 是纯函数，task 优先。
- `write_path()` 只用 jsonb_set 精确路径，带 WorkingPaper version 条件。
- `rebuild(wp_id)` 从 tasks 重建完整 procedure_status，仅用于显式维护/backfill，不由 GET 调用。
- 旧 `wp_procedure_status` router 解析动作后调用 TransitionService。

### C9. ProcedureReviewService

reviewer resolver 严格按 explicit staff → WorkingPaper.reviewer/WpIndex.reviewer 映射项目唯一 active staff → 唯一 primary manager → reviewer_missing。对话用 ReviewConversation；changes_requested 用现有 IssueTicket：`source=review_comment, source_ref_id=task_id, conversation_id`。权限集合包含当前参与者、历史参与者、ticket 参与者和 Delegator；历史集合只有读权限。

### C10. ProcedureDeliveryDispatcher

claim 条件为未 processed、未 dead-letter、available_at 到期、lease 为空或过期。领取后设置 lease_expires_at/claimed_by；同 aggregate 只领取最小未处理 version。NotificationProjection 先在独立事务插入去重通知并 commit，再广播含 event_id 的 SSE，最后标 processed。SSE 失败可重试，Notification dedup 阻止重复。

批量委派聚合器以 batch+recipient 收集 task events，产生一条摘要 Notification；history/outbox 仍逐任务。dispatcher 开关关闭时不 claim，已有 rows 保留。

### C11. ProcedureTaskQueryService

查询以当前 user→active staff ids 为入口，分别走 assignee/reviewer covering index。overdue 只对 due_at 非空且非 reviewed/cancelled。详情返回 nullable wp_id 与 materialization_required；深链不接受 program_no fallback。
## API Design

```text
POST /api/procedure-definitions/import
POST /api/projects/{pid}/procedure-row-tasks/materialize
POST /api/projects/{pid}/procedure-row-tasks/materialize-jobs
GET  /api/projects/{pid}/procedure-row-tasks/materialize-jobs/{job_id}
POST /api/projects/{pid}/procedure-row-tasks/reconcile/preview
POST /api/projects/{pid}/procedure-row-tasks/reconcile/apply

POST /api/projects/{pid}/procedure-trim/preview
POST /api/projects/{pid}/procedure-trim/apply
POST /api/projects/{pid}/procedure-delegations/preview
POST /api/projects/{pid}/procedure-delegations/apply

GET  /api/projects/{pid}/procedure-row-tasks
GET  /api/my/procedure-row-tasks
GET  /api/projects/{pid}/procedure-row-tasks/{task_id}
POST /api/projects/{pid}/procedure-row-tasks/{task_id}/transitions
GET  /api/projects/{pid}/procedure-row-tasks/{task_id}/conversation
POST /api/projects/{pid}/procedure-row-tasks/{task_id}/messages
POST /api/projects/{pid}/procedure-row-tasks/{task_id}/issues/{issue_id}/close

GET  /api/projects/{pid}/procedure-delivery/dead-letters
POST /api/projects/{pid}/procedure-delivery/{event_id}/replay
```

所有 GET 严格只读。所有敏感 apply 接受 preview id/token；transition 接受 `request_id, expected_version, expected_assignment_version`。409 统一返回当前版本/preview 失效原因，不泄露跨项目对象。

## Frontend Design

### F1. MyProcedureTasks.vue 原位重构

不创建新任务页。现有页面增加“我执行的/我复核的”筛选、项目/循环/状态/逾期筛选、assignment_version 状态动作、nullable wp 空态、聚合通知入口。建立回归测试锁定旧 bug：不得再以 `updateProcedureTrim` 提交 execution_status；状态动作必须调用 transition API 且 payload 包含 expected versions。

### F2. GtAProgramConsole overlay 与深链

ProgramRow 接收 `definition_key, task_id, materialization_required, assignee, reviewer, workflow_status, applicability_status, assignment_version, lock_version`。未物化只展示，不触发写。深链按 sheet_key+definition_key 精确定位，数据加载后清筛选、展开、滚动、高亮；失败显示“模板已变化”。

### F3. 现有裁剪页/控制台

粗裁明确“底稿范围/底稿主编”，细裁明确“程序适用性/程序执行人/操作复核人”。委派向导展示 materialize job、服务端 preview 统计、TTL 和 409 原因；apply 后显示真实 changed/unchanged/conflict。

### F4. NotificationCenter

metadata 驱动跳转；批量摘要进入 MyProcedureTasks.vue 并带 batch/project/filter。SSE handler 保存最近 event_id LRU，重复事件只触发至多一次刷新；即使丢失/重复也通过 API 拉取收敛。已读通知点击仍可跳转。

### F5. ProcedureReviewPanel

在程序控制台复用现有对话 UI，展示当前/历史参与者权限、IssueTicket 未解决数、退回/回复/关闭项/通过。高阶 partner/QC/EQCR 状态在独立区域展示，只读且不与一级 reviewed 合并。

## Legacy State Mapping

| legacy | assignee | task applicability | task workflow | confidence |
|---|---|---|---|---|
| pending/not_started | 有 | execute | assigned | conservative |
| pending/not_started | 无 | execute | unassigned | conservative |
| in_progress | 任意 | execute | in_progress | conservative；缺 assignee 记 conflict |
| filled/completed | 任意 | execute | submitted | conservative |
| reviewed/approved | 任意 | execute | reviewed | conservative |
| not_applicable | 任意 | not_applicable | cancelled | conservative |
| 未知/多来源矛盾 | 任意 | 保留可证值 | 不猜测 | conflict |

backfill 保存原始来源、值、映射规则和 conflict；不因为 legacy 名称 `completed` 猜成 reviewed。

## Deployment and Rollback

| 阶段 | TASKS_ENABLED | WRITE_MODE | DISPATCHER | 行为 |
|---|---|---|---|---|
| expand | false | legacy | false | 仅 V105 结构/兼容代码 |
| dual-read | true | legacy/dual | false | 读比较、可选双写、记录差异 |
| backfill | true | dual | false | 可恢复导入、投影核对 |
| cutover | true | task-source | true | task 真源、dispatcher 领取 |
| contract | true | task-source | true | 删除旧代码入口，保留物理列表 |

开关名固定为 `PROCEDURE_ROW_TASKS_ENABLED`、`PROCEDURE_ROW_TASK_WRITE_MODE`、`PROCEDURE_TASK_DISPATCHER_ENABLED`。阶段推进 guard 检查 schema、coverage/conflict、projection diff、backlog 和回滚演练。

生产回滚：先把 WRITE_MODE 停到 no-new-task-writes/legacy-safe 模式，再关闭 dispatcher，保持 outbox/新表/列不动，读取退回 dual-read/legacy fallback。不得执行 V105 destructive down。恢复后 dispatcher 从未 processed event 继续。

V105 migration 使用 information_schema 与 pg catalog 做幂等保护，并由契约测试精确校验类型、FK、nullable、index columns/include、partial predicate；仅 `IF NOT EXISTS` 不足以接受错误旧结构。
## Correctness Properties

以下属性由 Hypothesis/fast-check/PG integration 验证；PBT 默认使用项目 fast profile。数据库约束、索引谓词和事务语义必须在 PostgreSQL 验证，不以 sqlite 替代。

### Property 1: definition 跨项目稳定
任意规范化定义集合，在改变 project、导入机器、导入顺序后产生相同 definition_key 与 revision hash。
**Validates: Requirements 1.1, 1.3, 1.4**

### Property 2: revision 对非内容元数据不敏感
任意定义只改变 mtime、绝对路径展示或导入时间，revision 不变；改变规范语义字段时 revision 改变。
**Validates: Requirements 1.3, 1.5, 1.6**

### Property 3: legacy alias 不成为项目身份
任意 row-N/数组序号只进入 legacy_aliases，任务仍引用 definition_key。
**Validates: Requirements 1.7**

### Property 4: active task 唯一性
任意并发物化序列对同 `(project,wp_index,sheet,definition)` 最多产生一个 active task。
**Validates: Requirements 2.1, 2.2, 12.2**

### Property 5: nullable wp 原子绑定不换 task
任意未绑定 task 集合绑定 wp 后，task id、assignee、reviewer、workflow、assignment_version 与历史保持不变；重试结果相同。
**Validates: Requirements 2.3, 2.4**

### Property 6: GET/render-config 零写入
任意数据库初态和任意 GET/render-config 调用序列，definition/task/preview/projection/outbox 表及 WorkingPaper version 均不变化。
**Validates: Requirements 2.5, 2.7**

### Property 7: 未物化 overlay 完整
任意存在 definition 但不存在 task 的行，query overlay 均返回 task_id=null、materialization_required=true，且不产生 task。
**Validates: Requirements 2.6, 2.7, 2.8**

### Property 8: reconcile 不确定项零继承
任意 ambiguous/orphaned/conflict 映射均不复制 assignee、reviewer、workflow、IssueTicket 或 review history。
**Validates: Requirements 3.1, 3.2, 3.8**

### Property 9: 裁剪与 workflow 正交
任意 applicability 变化不伪造 submitted/reviewed；not_applicable 进入 cancelled，恢复后必须 reopen→assign→ack。
**Validates: Requirements 3.3, 3.4, 3.5, 6.2, 6.3**

### Property 10: 方案 applied 真实
任意方案应用中 `applied == 实际发生字段变化的 task/scope 数`，unchanged/conflict 不计入。
**Validates: Requirements 3.6, 3.7**

### Property 11: selector 展开等价
cycle/workpaper selector 展开集合等于对同项目全部 tasks 应用范围、粗裁和 applicability 谓词后的 row selector 集合。
**Validates: Requirements 4.1, 4.3**

### Property 12: preview token 防篡改与越权
任意 request hash、actor、project、operation、scheme revision、membership snapshot、target version 或 TTL 的单点变化都使 apply 返回 409 且零副作用。
**Validates: Requirements 4.2, 4.4, 4.5**

### Property 13: preview 最多一次消费
任意并发消费者对同 preview 最多一个执行领域变更；同 request_id 重试只返回同 result。
**Validates: Requirements 4.5, 4.6**

### Property 14: 批量委派原子与 owner 隔离
默认模式任一目标冲突则全批零写；任意行委派序列均不改变 WorkingPaper.assigned_to 或 assigned_cycles。
**Validates: Requirements 4.9, 4.10**

### Property 15: 同人委派业务 no-op
任意相同 assignee 的重复委派不改变 assignment_version/lock_version，不新增 history/outbox。
**Validates: Requirements 4.8**

### Property 16: staff/user 归一化 SOD
任意两个 StaffMember 只要归一到同一 user，就不能分别成为同 task assignee/reviewer；无 active user_id 的 staff 不能参与。
**Validates: Requirements 5.1, 5.2, 5.3**

### Property 17: reviewer fallback 决定性
任意成员图按显式 reviewer→唯一有效 wp/wp_index reviewer→唯一 primary manager 取值；缺失或重复只得到 reviewer_missing。
**Validates: Requirements 5.4, 5.5, 5.6**

### Property 18: 一级复核不改变高阶复核
任意 task review 序列不改变底稿/项目 partner、QC、EQCR 状态与门禁。
**Validates: Requirements 5.7, 5.8**

### Property 19: 状态机封闭性
任意动作序列只产生转换表允许的边；cancelled→assign、assigned→start、非 reviewer→review 均零副作用。
**Validates: Requirements 6.1, 6.2, 6.6, 6.7, 6.8**

### Property 20: assignment_version 与 ack
assignment 每次有效改变恰好递增一次并清 ack；同 assignment_version 重复 ack 是 no-op；恢复原执行人仍需新版本 ack。
**Validates: Requirements 6.3, 6.4, 6.5**

### Property 21: 成功动作审计完备
每个非 no-op 成功动作恰有一条 history 和一条幂等 outbox，包含 actor user、assignment_version 与 audit_cycle_snapshot。
**Validates: Requirements 6.9, 12.6**

### Property 22: 投影可重建且 task 优先
任意 task 集合重建投影后 overlay 与 task 一致；legacy projection 冲突时 task 值获胜。
**Validates: Requirements 7.1, 7.2, 7.3, 7.9**

### Property 23: parsed_data 不同路径并发不丢
任意两个事务更新不同 sheet/definition 路径，冲突重试后最终投影同时包含两项更新，不发生整列覆盖。
**Validates: Requirements 7.4, 7.5**

### Property 24: 旧状态保守映射
任意已知 legacy 状态严格映射到 Requirement 7.6–7.7 的表；未知或矛盾输入只产生 conflict/confidence，不猜测更高状态。
**Validates: Requirements 7.6, 7.7, 7.8**

### Property 25: IssueTicket 关闭门槛
任意 task 只有在全部关联 changes_requested IssueTicket closed 时才能 reviewed；一个未关闭即 409。
**Validates: Requirements 8.3, 8.4**

### Property 26: reviewer 转派历史可读、动作不可用
任意 reviewer/assignee 转派后，历史参与者可读其参与期间记录，但不能执行当前 transition；对话授权不依赖 initiator/target 单点。
**Validates: Requirements 8.5, 8.6, 8.7**

### Property 27: due_at 逾期谓词
任意 due_at/time/workflow 组合只有 due_at 非空、已过期且状态非 reviewed/cancelled 时 overdue=true。
**Validates: Requirements 9.1, 9.2, 9.3**

### Property 28: 深链与项目边界
任意跨项目 task/wp_index/wp 组合均 403/404 且不泄露文本；合法深链只按 sheet_key+definition_key 定位，不按 program_no 降级。
**Validates: Requirements 9.5, 9.6, 9.8**

### Property 29: aggregate version 有序投递
任意乱序 available 的同 aggregate events，processed aggregate_version 严格单调；前一版本失败时后一版本不越序。
**Validates: Requirements 10.1, 10.2, 10.3**

### Property 30: Notification 与 SSE 幂等收敛
任意 dispatcher/SSE 重试次数下，每个 event+recipient 最多一条 Notification；重复 event_id 的 SSE 不造成重复状态动作，最终 API 状态一致。
**Validates: Requirements 10.4, 10.5, 10.6, 10.9**

### Property 31: 批量通知聚合不损失审计
N 个 task 委派始终产生 N 组 task history/outbox；每个 recipient/batch 最多一条摘要通知，摘要计数等于其相关任务数。
**Validates: Requirements 10.7, 10.8**

### Property 32: 项目授权 fail-closed
除 admin 外，任意 partner/signing_partner/manager 若无唯一 active StaffMember→ProjectAssignment 链均拒绝；查询异常与重复映射同样拒绝。
**Validates: Requirements 11.1, 11.2, 11.3, 11.4**

### Property 33: 双版本并发
同 lock_version/assignment_version 的并发写最多一个成功，其余 409；失败事务不留下 history/projection/outbox。
**Validates: Requirements 12.5**

### Property 34: 部署阶段单调与回滚保留
任意阶段跳跃在 guard 未满足时被拒绝；生产回滚关闭写/dispatcher 后 V105 表列、task、history、outbox 均保留。
**Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8**

## Error Handling

- 401/403：认证、项目 active assignment、参与者或历史只读授权失败；异常统一 fail-closed。
- 404：对象不存在或服务端绑定校验失败；不泄露跨项目程序文本和 metadata。
- 409：preview 过期/篡改/重放、版本冲突、非法状态边、SOD、reconcile 冲突、IssueTicket 未关闭。
- 422：selector、理由、执行说明、消息或成员输入不符合契约。
- dispatcher 错误：领域事务保持已提交，event 退避重试或进入 dead-letter；不得回滚任务。

## Testing Strategy

- **契约/静态守卫**：GET 禁写调用图、ProcedureInstance 粒度、TransitionService 单入口、MyProcedureTasks 单页面、notification type 同步。
- **PostgreSQL integration**：V105 类型/FK/nullable/partial predicate/ON CONFLICT、covering/claim index、jsonb_set 并发、preview 并发消费、aggregate ordering、事务回滚。
- **后端 unit/PBT**：规范化 hash、reconcile、selector、reviewer fallback、权限矩阵、状态机、legacy mapping、notification aggregation。
- **前端 vitest/fast-check**：旧 execution_status bug 回归、preview 409、nullable wp、event_id 去重、深链精确定位、IssueTicket 门槛展示。
- **性能**：6000 并发目标环境下任务查询/transition；5000 task preview；dispatcher backlog/lease 恢复。
- **Playwright**：admin、现场经理、审计助理、操作复核人四角色 fresh navigation；先委派后生成、wp 原子绑定、返修闭环、聚合通知、重复 SSE、跨项目拒绝、刷新落库、0 console error。

## Requirement Traceability

| Requirement | Design | Properties |
|---|---|---|
| Req1 | D1, C1, definition model | P1-P3 |
| Req2 | D2-D3, C2, task model | P4-P7 |
| Req3 | C3-C4, legacy mapping | P8-P10 |
| Req4 | D4, C6 | P11-P15 |
| Req5 | D5-D6, C5/C9 | P16-P18 |
| Req6 | C7 | P19-P21/P33 |
| Req7 | D7, C8 | P22-P24 |
| Req8 | C9, F5 | P25-P26 |
| Req9 | C11, F1-F2 | P27-P28 |
| Req10 | D8, C10, F4 | P29-P31 |
| Req11 | C5 | P32 |
| Req12 | V105 models/indexes | P4/P21/P33 + schema contracts |
| Req13 | Deployment and Rollback | P34 |
| Req14 | F1-F5, performance/E2E | example/performance/Playwright acceptance |
