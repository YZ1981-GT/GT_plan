# Requirements Document

## Introduction

本 feature 建立“模板级程序定义 → 项目级程序任务物化 → 两层裁剪 → 三粒度委派 → 执行与一级复核 → 可靠通知与深链”的闭环。现有 `ProcedureInstance` 仍只表示按 `wp_code` 建立的底稿范围实例，不是具体程序行；具体程序行的项目级工作流以新增 `ProcedureRowTask` 为唯一真源。

第三轮修订固定以下边界：模板定义与项目任务分层；任务允许先委派后生成底稿；所有 GET/render-config 严格只读；执行人和操作复核人统一落到 `staff_members`，actor/通知收件人统一使用 `users.id`；本 feature 只覆盖程序行一级复核，不替代业务合伙人、QC、EQCR 在底稿/项目层的高阶复核；`parsed_data` 仅为可重建兼容投影；部署采用 expand→dual-read→backfill→cutover→contract，生产回滚不做破坏性 down。

## Scope

本 feature 必须完成模板定义真源、V105 expand 模型、V106 cutover-hardening 修正迁移、显式物化、原子底稿绑定、模板对账、两层裁剪、项目权限、委派预览与一次消费、状态机、兼容投影、旧状态保守迁移、一级复核、IssueTicket 闭环、事务 outbox、跨进程通知收敛、任务查询、现有页面重构、分阶段部署和四角色实测。所有任务均为必做，不设置 optional。

第四轮代码复盘（2026-07-16）确认：V105 与主要领域服务已经存在，但当前仍有按 `program_no` 猜测 overlay、历史 revision 混合物化、绑定冲突部分成功、非原子乐观锁、history 旧值失真、legacy 裁剪页未切换、进程内 SSE 无法跨 worker 收敛、dead-letter 后续越序及验收证据不足等 cutover 阻断项。因此本 feature 当前状态是“主体已实现、收敛整改中”，不得按 100% 完成发布。

## Glossary

- **ProcedureRowDefinition**：模板级程序行定义真源；跨项目稳定，以 `definition_key` 标识。
- **ProcedureRowTask**：项目级程序行任务真源；引用 `definition_key`，承载适用性、委派、执行和一级复核状态。
- **WorkpaperScopeInstance**：现有 `ProcedureInstance` 的语义别名，只表示循环/科目/底稿范围粗裁。
- **ProcedureOperationPreview**：服务端保存的敏感操作预览，绑定 actor、项目、请求摘要、目标版本、成员快照与方案 revision，只能消费一次。
- **Operation_Reviewer**：程序行“操作复核人/一级复核人”，对应 `reviewer_staff_id`；不是业务合伙人、QC 或 EQCR。
- **Compatibility_Projection**：`WorkingPaper.parsed_data.procedure_status` 中由任务真源重建的兼容视图。
- **Delivery_Outbox**：与领域变更同事务写入、提交后异步领取和投递的可靠事件记录。
- **Materialization**：把模板级 ProcedureRowDefinition 显式实例化为项目级 ProcedureRowTask 的写操作。

## Requirements

### Requirement 1: 建立模板级程序定义真源

**User Story:** 作为平台维护者，我希望程序行身份独立于项目和底稿实例，以便同一模板定义跨项目稳定复用并可安全升级。

#### Acceptance Criteria

1. THE System SHALL 新增模板级 `ProcedureRowDefinition`，并以跨项目稳定的 `definition_key` 作为程序行身份真源；`ProcedureRowTask` SHALL 仅引用该 key，不自行生成另一套项目内行身份。
2. EACH definition SHALL 至少保存 `template_code, template_revision_hash, sheet_key, source_locator, program_no, procedure_text, ref_snapshot, legacy_aliases`。
3. THE `template_revision_hash` SHALL 由规范化定义内容计算 SHA-256；规范化内容至少覆盖 sheet、定位信息、程序号、程序文本、引用快照和影响身份的模板字段，且 SHALL NOT 使用文件 mtime、导入时间或项目数据。
4. WHEN 相同规范化定义内容被不同项目或不同机器导入，THE System SHALL 产生相同 `template_revision_hash` 与 `definition_key`。
5. WHEN 仅文件 mtime、路径展示形式或导入顺序变化而规范化内容不变，THE System SHALL 保持 revision 与 definition_key 不变。
6. WHEN 模板定义内容改变，THE System SHALL 创建或登记新 revision，并通过 reconcile 显式决定继承关系；不得静默覆盖旧定义快照。
7. WHEN 旧模板仅有 `row-{program_no}`、数组序号或历史别名，THE System SHALL 将其登记到 `legacy_aliases`；临时数组序号不得成为长期 definition_key。

### Requirement 2: 项目任务锚点、显式物化与只读渲染

**User Story:** 作为现场经理，我希望在底稿生成前也能委派程序任务，并确保浏览页面不会暗中写库。

#### Acceptance Criteria

1. EACH `ProcedureRowTask` SHALL 以 `project_id + wp_index_id` 为非空项目锚点，并保存 `sheet_key + definition_key`；`wp_id` SHALL nullable，以支持先委派后生成底稿。
2. THE active unique constraint SHALL 为 `(project_id, wp_index_id, sheet_key, definition_key) WHERE is_deleted=false`，不得依赖 nullable `wp_id` 保证唯一性。
3. WHEN 底稿生成且发现待绑定任务，THE System SHALL 在同一事务中原子设置 `wp_id`，并保持 task_id、assignee、reviewer、workflow、assignment_version 和历史不变。
4. WHEN 同一底稿生成或绑定请求重试，THE System SHALL 幂等返回原绑定结果，不创建新任务或更换 task_id。
5. THE System SHALL 明文禁止任何 GET、`render-config`、页面加载或任务查询路径创建/更新 ProcedureRowDefinition、ProcedureRowTask、投影或 preview。
6. ONLY 显式 POST materialize、项目初始化、delegation preview 前置 materialize job、reconcile apply 和 backfill MAY 执行物化写入。
7. WHEN GET/render-config 发现定义尚未物化，THE System SHALL 仅返回 overlay，且对应行包含 `task_id=null` 与 `materialization_required=true`。
8. WHEN delegation preview 需要未物化行，THE System SHALL 创建可追踪的前置 materialize job；preview 只有在 job 成功后才能生成可消费结果。
### Requirement 3: 模板修订对账与两层裁剪

**User Story:** 作为项目合伙人或现场经理，我希望模板升级和裁剪都经过可审计预览，避免把旧任务错误继承到新程序。

#### Acceptance Criteria

1. THE reconcile process SHALL 按 `definition_key → legacy_alias → 唯一规范化内容匹配` 产生 matched、unmatched、ambiguous、orphaned 与 conflict 明细。
2. IF reconcile 为 ambiguous、orphaned 或 conflict，THEN THE System SHALL 禁止自动继承 assignee、reviewer、workflow、IssueTicket 或复核历史，并要求 Delegator 显式处理。
3. THE System SHALL 保留 WorkpaperScopeInstance 的 `execute/skip/not_applicable` 粗裁状态，并以 ProcedureRowTask 的 `applicability_status ∈ {execute, not_applicable}` 表示细裁；适用性不得伪装成工作流完成状态。
4. WHEN 粗裁为 skip/not_applicable，THE System SHALL 阻止新委派并预览受影响任务；已有未完成任务必须经取消转换保留历史。
5. WHEN 行细裁为 not_applicable，THE System SHALL 设置 applicability 为 not_applicable，并将 workflow 转为 cancelled；恢复 execute 时必须显式 reopen，不得自动完成或直接恢复执行。
6. THE canonical trim key SHALL 分别为 `scope:{cycle}:{wp_index_code}` 与 `row:{template_code}:{sheet_key}:{definition_key}`，并保存 definition revision 与文本快照。
7. WHEN 应用参照方案，THE System SHALL 先创建服务端 ProcedureOperationPreview；实际 applied 数 SHALL 等于真实改变数，无真实修改时返回 `applied=0`。
8. IF legacy UUID key 无法唯一转换，THEN THE System SHALL 记录 migration_conflict 并返回 409，不得按数组顺序或相似文本猜测。

### Requirement 4: 三粒度委派与安全预览

**User Story:** 作为现场经理，我希望按循环、科目或具体程序进行委派，并确保预览结果不能被篡改、重放或跨项目消费。

#### Acceptance Criteria

1. THE DelegationService SHALL 接受 cycle、workpaper/wp_index、row/task 三种 selector，并确定性展开为当前粗裁保留且 applicability=execute 的 ProcedureRowTask 集合。
2. BEFORE delegation apply，THE System SHALL 创建服务端 `ProcedureOperationPreview` 记录：actor user、project、operation、规范化 request hash、target versions、membership snapshot、scheme revision、expires_at、consumed_at 与 result。
3. THE preview SHALL 返回目标数、物化 job/result、已分配数、执行中数、已提交数、冲突数、成员负载、受影响底稿和逐项版本。
4. THE apply request SHALL 仅提交 preview id/token 与必要确认；服务端 SHALL 重算 request hash 并校验 actor、project、operation、TTL、目标版本、成员快照和 scheme revision。
5. WHEN preview 已消费、过期、被篡改、跨 actor/project 使用、目标版本变化或成员资格变化，THE System SHALL 返回 409 且不产生部分写入。
6. THE preview SHALL 一次消费；相同 request_id 的网络重试 MAY 幂等返回已保存 result，但不得再次执行领域变更。
7. THE DelegationService SHALL 支持 `unassigned_only`、`reject_on_conflict`、`replace_with_reason`；默认 reject_on_conflict，转派理由长度 5–500 字符。
8. WHEN 新旧执行人相同，THE System SHALL 计为 unchanged，不递增 assignment_version，不重复历史或 outbox。
9. THE default batch mode SHALL 原子全成全败；只有显式 best_effort MAY 返回逐任务结果。
10. 行级委派 SHALL NOT 隐式修改 `WorkingPaper.assigned_to` 或 `ProjectAssignment.assigned_cycles`；底稿主编和循环责任范围只能通过独立显式操作更新。

### Requirement 5: 统一参与者身份、复核人回退与职责分离

**User Story:** 作为业务合伙人，我希望参与者身份、项目成员资格和复核回退规则唯一且可验证，避免错误授权或自我复核。

#### Acceptance Criteria

1. `assignee_staff_id` 与 `reviewer_staff_id` SHALL 均引用 `staff_members.id`；领域 actor、history actor 与 notification recipient SHALL 使用 `users.id`。
2. ALL SOD、授权和收件人解析 SHALL 先通过 active `StaffMember.user_id` 归一到 user；无 user_id 的 StaffMember SHALL 禁止被委派或设为 reviewer。
3. THE System SHALL 禁止同一归一化 user 同时成为同一任务的 assignee 与 reviewer。
4. THE reviewer fallback SHALL 严格依次为：显式 `reviewer_staff_id`；`WorkingPaper.reviewer` 或 `WpIndex.reviewer` 映射到本项目唯一 active StaffMember；本项目唯一 primary manager；否则 `reviewer_missing`。
5. IF reviewer 映射不存在、跨项目、inactive 或重复不唯一，THEN THE System SHALL fail-closed 到 `reviewer_missing`，不得任取第一条。
6. WHEN reviewer_missing，THE System SHALL 阻止 review 转换并向有权限的 Delegator 产生可靠通知意图。
7. 本 feature SHALL 仅实现程序行 Operation_Reviewer 的一级复核；业务合伙人、质量控制复核合伙人和 EQCR 的高阶复核继续由既有底稿/项目层机制负责。
8. 程序行 reviewed SHALL NOT 自动完成、豁免或削弱底稿/项目层合伙人、QC、EQCR 复核门槛。

### Requirement 6: 独立状态机、重新确认与委派版本

**User Story:** 作为执行成员，我希望任务状态推进清晰，转派、取消和恢复不会绕过接收确认。

#### Acceptance Criteria

1. THE workflow SHALL 使用 `unassigned → assigned → acknowledged → in_progress → submitted → reviewed` 主路径，并支持 `submitted → changes_requested → in_progress → submitted`。
2. THE assign action SHALL 只允许 `unassigned → assigned`；cancelled 任务必须先执行 reopen，不得由 assign 直接恢复。
3. THE reopen action SHALL 把 cancelled 恢复为 unassigned；若需恢复原执行人，也必须随后 assign 并重新 acknowledge。
4. WHEN assignment 发生首次分配或执行人改变，THE System SHALL 递增 `assignment_version`、清空 acknowledged_at，并要求当前 assignment_version 下重新确认。
5. WHEN 同一执行人在同一 assignment_version 重复 acknowledge，THE System SHALL 返回业务 no-op，不新增 history/outbox，也不递增 lock_version。
6. ONLY assignee SHALL acknowledge/start/submit；ONLY Operation_Reviewer SHALL request_changes/review；Delegator MAY cancel/reopen/reassign，但不得替代 reviewer 给出 reviewed。
7. submit SHALL 要求非空执行说明与证据引用快照；applicability 非 execute 或 wp_id 仍为空时 SHALL 拒绝 start/submit。
8. IF 状态边、actor、expected lock_version 或 assignment_version 不合法，THEN THE System SHALL 返回 409 且任务、history、投影和 outbox 均无变化。
9. EACH 成功领域动作 SHALL 追加 history，记录 from/to、旧/新 staff、actor user、reason、request_id、assignment_version、audit_cycle_snapshot 与时间。
### Requirement 7: 任务真源、兼容投影与旧状态保守迁移

**User Story:** 作为平台维护者，我希望只有一套工作流真源，同时保留旧程序表显示和迁移兼容。

#### Acceptance Criteria

1. `ProcedureRowTask` SHALL 是适用性、委派、执行和一级复核状态唯一真源；`parsed_data.procedure_status` SHALL 仅为可删除后重建的 Compatibility_Projection。
2. GET/render-config SHALL 以 task overlay 覆盖程序行展示状态，不得把 parsed_data 的旧值反向覆盖任务。
3. THE legacy `wp_procedure_status` write endpoint SHALL 转调同一 `ProcedureTaskTransitionService`；不得保留第二套状态机。
4. THE System SHALL 禁止对 `parsed_data` 整列执行 read-modify-write 来更新单条程序状态。
5. WHEN 必须镜像投影，THE System SHALL 使用 `jsonb_set` 精确到 sheet_key/definition_key 路径，并结合 WorkingPaper version 乐观锁或行锁，保证不同路径并发更新不丢失。
6. THE backfill SHALL 保守映射旧状态：`pending/not_started` 在有 assignee 时为 assigned、无 assignee 时为 unassigned；`in_progress` 为 in_progress；`filled/completed` 为 submitted；`reviewed/approved` 为 reviewed。
7. THE backfill SHALL 将 `not_applicable` 映射为 applicability=not_applicable 且 workflow=cancelled。
8. IF 旧值、assignee、复核记录或多来源互相矛盾，THEN THE System SHALL 写 `migration_confidence` 与 conflict detail，保留原值快照且不得猜测。
9. THE compatibility projection SHALL 可由 ProcedureRowTask 全量重建，并有校验报告比较 task/projection 差异。

### Requirement 8: 一级复核、正式未解决项与历史参与者访问

**User Story:** 作为程序行复核人，我希望退回事项可被正式跟踪，转派后历史参与者仍能读取自己参与期间的记录。

#### Acceptance Criteria

1. THE System SHALL 使用 `ReviewConversation(related_object_type='procedure_row_task', related_object_id=task_id)` 保存程序行讨论，并以 `cell_ref='proc:{sheet_key}:{definition_key}'` 定位。
2. THE System SHALL NOT 用 task_id 替代 `ReviewThread.wp_id`，也不得创建缺失 conversation_id 的 ReviewMessage。
3. EACH changes_requested SHALL 创建或复用 `IssueTicket(source='review_comment', source_ref_id=task_id, conversation_id=...)` 作为正式未解决项。
4. BEFORE review，THE System SHALL 验证该 task 关联的全部 changes_requested IssueTicket 均为 closed；否则返回 409。
5. WHEN reviewer 转派，历史 assignee/reviewer SHALL 保留对其参与期间 history、message 和 issue 的只读访问，但不得获得当前动作权限。
6. THE conversation authorization SHALL 基于当前参与者、历史参与者、IssueTicket 参与关系和项目 Delegator 的并集；不得只依赖 conversation initiator/target。
7. comment/reply SHALL 通知当前相关参与者；历史只读参与者是否收新通知 SHALL 由显式订阅状态决定，不得因历史访问自动扩大收件范围。
8. 文本 trim 后长度 SHALL 为 1–5000 字符；消息和历史按 `created_at,id` 稳定排序。

### Requirement 9: 任务查询、深链与现有页面重构

**User Story:** 作为审计成员，我希望在现有任务页查看程序任务，并准确进入对应程序行。

#### Acceptance Criteria

1. THE System SHALL 提供项目级与跨项目“我的程序任务”分页查询，支持 project、cycle、wp_index、workflow、reviewer、due 状态筛选。
2. EACH result SHALL 返回 task_id、project、wp_index_id、nullable wp_id、definition/sheet 快照、assignee/reviewer、workflow、applicability、assignment_version、lock_version、due_at 和 materialization_required。
3. overdue SHALL 仅在 `due_at IS NOT NULL` 且任务未完成/未取消且当前时间晚于 due_at 时为 true。
4. THE Frontend SHALL 重构现有 `MyProcedureTasks.vue`，不得新建平行任务页或重复路由。
5. WHERE wp_id 为空，THE UI SHALL 显示“底稿未生成”与刷新/提醒操作，不构造无效编辑器链接。
6. WHERE wp_id 有效，THE deep link SHALL 携带 `task_id, sheet_key, definition_key`；控制台 SHALL 清理筛选、展开并高亮精确行，找不到时提示模板变化，不按 program_no 猜测。
7. THE System SHALL 记录现有真实 bug 作为回归基线：当前 UI 修改 `execution_status` 却调用 `updateProcedureTrim`，且 payload 不含 `execution_status`；重构后状态动作必须调用 TransitionService 契约。
8. 任务详情和深链 SHALL 校验 task→project→wp_index→wp 绑定；未授权请求返回 403/404 且不泄露程序文本。

### Requirement 10: 有序 Outbox、跨进程通知收敛与可恢复唤醒

**User Story:** 作为任务参与者，我希望领域通知可靠、有序且跨 worker 可见，批量操作不会造成通知或刷新风暴；短暂断线后仍能通过持久化游标恢复。

#### Acceptance Criteria

1. EACH domain mutation SHALL 在同一事务写 Delivery_Outbox，字段至少包含 `aggregate_type, aggregate_id, aggregate_version, event_type, idempotency_key, available_at, lease_expires_at, claimed_by, processed_at, payload`。
2. THE dispatcher SHALL 使用 claim lease 与并发安全领取；过期 lease 可回收，失败按 available_at 退避，超限进入 dead-letter。
3. EVENTS of the same aggregate SHALL 按 aggregate_version 顺序处理；前一版本未 processed（包括 dead-letter 未处置）时后续版本不得越序投递。dead-letter 只有经有审计记录的 replay 或 waive/skip 决议后才能解除 aggregate barrier。
4. Notification dedup SHALL 至少覆盖 `event_id + recipient_user_id`；重试不得生成重复通知。
5. THE dispatcher SHALL 先提交 Notification，再发布跨进程 wake-up。持久化 Notification/outbox 投影采用 at-least-once；SSE 仅作为可重复、可丢失的失效唤醒信号，不得被描述为状态真源或独立可靠队列。
6. THE cross-worker wake-up SHALL 经 Redis Pub/Sub（或等价共享 broker）广播；每个 API worker 只向本进程 SSE 连接 fan-out。客户端重连 SHALL 携带游标/最后已见 event_id，并从持久化 Notification/任务 API catch-up 后再恢复实时监听。
7. THE Frontend SHALL 以 event_id 幂等处理 wake-up，并在 200–500ms 窗口内合并任务列表/未读数刷新；单批 N 个底层事件不得触发 N 次全量请求。
8. 批量委派 SHALL 为每个 task 记录独立 history/outbox audit event，但用户通知 SHALL 按 `delegation_batch_id + recipient_user_id` 聚合为摘要。
9. THE aggregate notification metadata SHALL 包含 event_id/batch_id、project、任务计数、可跳转 task 列表或任务筛选条件；不得从中文 content 解析路由。
10. assign/reassign/submit/changes_requested/review/reviewer_missing/comment/reply SHALL 全部通过同一 outbox→Notification→wake-up 路径；禁止在领域服务或 review service 中直接写 Notification/SSE 形成旁路。
11. Notification/wake-up 失败 SHALL NOT 回滚已提交领域事务；event 保持可重试并提供 backlog、oldest age、lease、失败、dead-letter barrier、dispatcher heartbeat 和延迟指标。
12. THE dispatcher SHALL 在应用 lifespan 中显式 start/stop，多个 worker 可依赖 lease/`SKIP LOCKED` 安全并行；健康端点必须区分“开关关闭、循环未运行、积压、阻塞、正常”。
### Requirement 11: 项目权限与 fail-closed 授权

**User Story:** 作为项目负责人，我希望只有当前项目中的授权人员能裁剪、委派和处理任务。

#### Acceptance Criteria

1. ONLY system admin SHALL 全局放行；partner、signing_partner、manager 均 SHALL 具有当前项目 active ProjectAssignment 才能执行 Delegator 操作。
2. THE project guard SHALL 通过 active StaffMember.user_id 与 ProjectAssignment.staff_id 建立唯一链路；不得仅凭系统 role 放行 partner。
3. IF StaffMember 缺失/inactive、user_id 缺失、ProjectAssignment inactive、映射重复、跨项目或查询异常，THEN THE System SHALL fail-closed 返回 403。
4. 粗裁、细裁、reconcile apply、scheme apply、materialize、delegation preview/apply、转派、cancel/reopen 与 dead-letter replay SHALL 使用同一项目级 guard。
5. assignee/reviewer 动作 SHALL 同时校验 active membership、任务参与关系、assignment_version 与 SOD；历史参与者仅拥有 Requirement 8 定义的只读范围。
6. ALL task、preview、conversation、issue、notification deep-link endpoints SHALL 从服务端对象反查 project binding，不信任客户端 project_id。

### Requirement 12: 数据约束、索引、并发与审计字段

**User Story:** 作为平台维护者，我希望数据约束和索引直接表达业务不变量，并支撑大项目并发查询。

#### Acceptance Criteria

1. ProcedureRowTask SHALL 包含 `audit_cycle_snapshot, due_at nullable, assignment_version, lock_version, migration_confidence` 及必要时间戳/快照字段。
2. THE V105 migration SHALL 建 active partial unique index，并在所有 upsert 的 `ON CONFLICT` 中使用与索引完全一致的列和 `WHERE is_deleted=false` 谓词。
3. THE System SHALL 建跨项目 assignee/reviewer covering indexes，覆盖 user task query 所需 project、workflow、due_at、wp_index、task id 等字段。
4. THE System SHALL 建 outbox claim index，至少覆盖未处理、available_at、lease_expires_at 和同 aggregate version 排序条件。
5. EACH write SHALL 使用 expected lock_version；assignment 相关动作还 SHALL 校验 assignment_version。同版本并发最多一个成功，其余返回 409 当前快照。
6. THE append-only history SHALL 可按 task_id/project_id 稳定查询，并记录 definition revision、audit_cycle_snapshot、actor user、staff 变化、request_id 和 reason。
7. THE migration contract test SHALL 通过 information_schema/pg catalog 校验列类型、nullable、FK 目标、covering index 列顺序、partial index predicate 与 ON CONFLICT predicate 一致性。

### Requirement 13: 分阶段部署、特性开关与非破坏回滚

**User Story:** 作为发布负责人，我希望新旧模型可分阶段切换，并能在生产异常时安全退回 dual-read。

#### Acceptance Criteria

1. THE rollout SHALL 按 expand → dual-read → backfill → cutover → contract 顺序执行；未满足阶段 guard 不得进入下一阶段。
2. THE feature SHALL 提供 `PROCEDURE_ROW_TASKS_ENABLED`、`PROCEDURE_ROW_TASK_WRITE_MODE`、`PROCEDURE_TASK_DISPATCHER_ENABLED` 三个开关，并定义每个阶段允许的读写行为。
3. DURING expand，THE System SHALL 只增加 V105 表/列/索引和兼容代码；不得删除旧列或改变既有读语义。
4. DURING dual-read，THE System SHALL 比较 task overlay 与 legacy projection，记录差异；write mode 只能按明确配置为 legacy、dual 或 task-source，不能由请求自行选择。
5. THE backfill SHALL 可恢复、可重复执行，输出 definition/task/alias/conflict/orphan/status mapping coverage，并保留原始快照。
6. BEFORE cutover，THE System SHALL 验证 coverage、冲突阈值、投影一致性、dispatcher backlog 与回滚演练；cutover 后 ProcedureRowTask 成为读写真源。
7. DURING contract，THE System MAY 删除代码路径，但生产发布 SHALL 保留新表和新增列；物理删列/删表必须进入后续独立迁移，不属于本 feature。
8. PRODUCTION rollback SHALL 停止 task 新写、停止 dispatcher、保留 V105 表列与 outbox、把读取退回 dual-read/legacy fallback；不得执行破坏性 down migration。
9. THE System SHALL 提供 CI guard，禁止新增 GET 写库、直接写 parsed_data workflow、把 ProcedureInstance 当程序行任务或绕开 TransitionService。

### Requirement 14: 用户界面、性能与验收

**User Story:** 作为项目团队，我希望界面术语明确、操作可预览，并在目标并发下保持可用。

#### Acceptance Criteria

1. THE UI SHALL 明确区分循环责任人、底稿主编、程序执行人、操作复核人、业务合伙人/QC/EQCR，不得把高阶复核显示为程序行 reviewer。
2. THE existing 裁剪页与程序控制台 SHALL 展示服务端 preview、真实 applied/unchanged/conflict 统计、materialization job 状态和一次消费错误。
3. `MyProcedureTasks.vue` SHALL 提供执行任务与复核任务筛选、ack/start/submit/review 动作、逾期提示和深链，不复制现有任务中心能力。
4. UNDER 6000 concurrent users target，常规任务分页查询 p95 SHALL ≤2 秒，单任务转换 p95 SHALL ≤1 秒；5000 行 delegation preview（不含异步 materialize 等待）SHALL ≤3 秒。
5. THE System SHALL 记录 materialize、reconcile、preview、delegation、transition、projection、dispatcher 的结构化指标与 trace_id，且日志不得包含附件正文或敏感凭证明细。
6. THE acceptance suite SHALL 包含 admin/现场经理/审计助理/操作复核人四角色 fresh-navigation Playwright，覆盖先委派后生成、原子 wp 绑定、退回再提交、review、聚合通知、重复 wake-up、越权、刷新 round-trip 和 0 console error。
7. EACH 验收任务 SHALL 在 spec evidence manifest 中记录命令、时间、环境、结果、关键截图/网络/数据库证据和失败修复记录；无可复核证据不得标记完成。
8. THE deep-link acceptance SHALL 验证真实 `GtAProgramConsole` 清筛选、展开、滚动与高亮行为，不得只断言 URL/query payload。

### Requirement 15: 第四轮 cutover 收敛与 V106 修正

**User Story:** 作为发布负责人，我希望主体实现与真实用户路径、模板身份、并发和投递语义完全一致，避免“新域模型已存在但旧路径仍在写”的半迁移状态进入生产。

#### Acceptance Criteria

1. THE System SHALL 新增 `procedure_template_revisions`（或等价单一 current-revision registry），以 `template_code + revision_hash` 登记 revision，并保证每个 template_code 最多一个 active current revision；切换 current 必须事务化、可审计且只能来自显式 import/reconcile apply。
2. WHEN materialize/overlay 未显式给出 revision，THE System SHALL 只使用 registry 指向的 current revision；缺 current、多 current 或待 reconcile 时 fail-closed，不得读取全部历史 revision。
3. EACH rendered ProgramRow SHALL 携带 `sheet_key + definition_key + definition_revision_hash`；overlay/deep-link SHALL 只按该三元组精确连接。`program_no` 仅用于展示或显式 legacy reconcile，不得用于 `setdefault`、first-match 或静默 fallback。
4. THE materialize implementation SHALL 以 set-based 查询一次取得目标 wp_code/revision definitions，禁止按每个 wp_index 循环查询；5000 行场景必须提交真实 PostgreSQL query-count/EXPLAIN 证据。
5. WHEN bind_working_paper 发现同一 project/wp_index 下任一 active task 已绑定其他 wp，THE System SHALL 整批 409 且零写；不得先绑定 pending 再仅返回 conflict 计数。成功绑定 SHALL 在同一事务重建该 wp 的 Compatibility_Projection。
6. ALL externally callable mutations SHALL 强制要求 expected lock_version；assignment mutation 还要求 expected assignment_version。CAS SHALL 在 TransitionService 内以 `UPDATE ... WHERE lock_version=:expected RETURNING` 或 service-owned `SELECT FOR UPDATE` 保证，不得依赖 router 调用习惯。
7. THE history writer SHALL 在 mutation 前捕获 old/new snapshot，并用 sentinel 区分“未提供”与“真实 NULL”；首次 assign、转派、reopen 清人、reviewer 变化的 old/new 值必须可验证准确。
8. THE existing `ProcedureTrimming.vue`、`commonApi` 与 legacy routers SHALL 完成调用清单和切换：用户可达裁剪/方案/委派路径只调用新 preview/apply/transition 契约；legacy 写端点在 dual 阶段仅作受控 adapter，cutover 后拒写，不得维持第二状态机。
9. THE WorkingPaper creation inventory SHALL 覆盖全部生成/复制/导入入口；每个入口必须在同一事务调用 bind_working_paper，CI coverage guard 防止新增入口漏绑。
10. `PROCEDURE_ROW_TASK_WRITE_MODE` SHALL 仅允许 `legacy | dual | task_source | paused`。合法迁移为 legacy→dual→task_source，紧急回滚可由 dual/task_source→paused；paused 禁止新领域写并使用 dual-read/legacy fallback，不引入文档外的 `no-new-task-writes/legacy-safe` 隐式值。
11. THE V106 migration SHALL 以 additive 方式补 revision registry、所需约束/索引/审计字段和 history append-only 防护；不得修改已可能执行的 V105 文件。V106 启动契约必须通过 pg_catalog 校验对象定义而非只看对象名。
12. BEFORE cutover，THE System SHALL 关闭所有本 requirement 的 blocker，并完成：跨 sheet 重号、旧 revision、绑定冲突、同版本并发、history NULL、跨 worker wake-up、dead-letter barrier、legacy write freeze、真实控制台深链和四角色 round-trip 的实证验收。
