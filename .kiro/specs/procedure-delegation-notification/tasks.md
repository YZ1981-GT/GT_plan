# Implementation Plan

## Overview

本计划基于当前最高迁移 V104，为本 feature 固定 V105。共 17 个任务、11 个 waves，全部必做且初始状态均为 `[ ]`。顺序遵循“基线护栏 → expand 模型 → definition 真源 → 显式物化 → reconcile → trim → 权限 → delegation → 状态真源 → dispatcher/查询/复核 → 通知/UI/部署 → 自动验证 → 四角色实测”。

禁止在本计划执行前把任何任务标绿；第三轮文档修订不开始 Wave 1 源码实现。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"] },
    { "wave": 2, "tasks": ["2"] },
    { "wave": 3, "tasks": ["3"] },
    { "wave": 4, "tasks": ["4", "7"] },
    { "wave": 5, "tasks": ["5"] },
    { "wave": 6, "tasks": ["6"] },
    { "wave": 7, "tasks": ["8", "9"] },
    { "wave": 8, "tasks": ["10", "12", "13"] },
    { "wave": 9, "tasks": ["11", "14", "15"] },
    { "wave": 10, "tasks": ["16"] },
    { "wave": 11, "tasks": ["17"] }
  ]
}
```

依赖约束：Task 2 依赖 Task 1；Task 3 依赖 Task 2；Task 4 依赖 Task 3；Task 5 依赖 Task 4；Task 6 依赖 Task 5；Task 7 依赖 Task 2；Task 8 依赖 Task 4/6/7；Task 9 依赖 Task 2/4/7；Task 10 依赖 Task 9；Task 11 依赖 Task 10；Task 12 依赖 Task 4/7/9；Task 13 依赖 Task 5/7/9；Task 14 依赖 Task 6/8/9/12/13；Task 15 依赖 Task 2-10/12/13；Task 16 依赖 Task 1-15；Task 17 依赖 Task 16。Task 3（definition identity）与 Task 6（trim）不在同一 wave。

## Tasks

- [x] 1. 冻结基线与建立结构性护栏
  - 记录并测试真实粒度：`ProcedureInstance` 是 WorkpaperScopeInstance，不是程序行；禁止新增以其 id 作为 task id 的消费者。
  - 建立 GET/render-config 零写 baseline，捕获 definition/task/preview/projection/outbox 与 WorkingPaper version 前后快照。
  - 为现有真实前端 bug 建回归基线：UI 改 `execution_status` 却调用 `updateProcedureTrim`，payload 不含 `execution_status`。
  - 增加静态守卫 fixture：禁止直接写 parsed_data workflow、禁止绕开 TransitionService、禁止新增平行 MyProcedureTasks 页面。
  - 确认 migration status 最高 V104，预留 V105 文件名与 ORM/DDL 契约入口。
  - _需求：2.5, 7.3-7.5, 9.4, 9.7, 13.9_

- [x] 2. 实现 V105 expand 数据模型
  - 新建 `procedure_row_definitions`、`procedure_row_tasks`、`procedure_row_task_history`、`procedure_operation_previews`，补齐 design 定义的字段/FK/nullability。
  - ProcedureRowTask 使用 `project_id + wp_index_id NOT NULL`，`wp_id NULL`；加入 audit_cycle_snapshot、due_at、assignment_version、lock_version、migration_confidence/detail。
  - 建 active partial unique `(project_id,wp_index_id,sheet_key,definition_key) WHERE is_deleted=false`，并让 materialize upsert 的 ON CONFLICT 谓词完全一致。
  - 扩展 outbox 的 aggregate/version/idempotency/available/lease/claim/processed 字段与 Notification event_id/recipient/dedup/metadata。
  - 建 assignee/reviewer covering indexes 与 outbox claim/order index；同步 ORM。
  - 用 information_schema/pg catalog 验证列类型、nullable、FK、index/include、partial predicate，不把 `IF NOT EXISTS` 当结构正确证明。
  - _需求：1.1-1.2, 2.1-2.2, 4.2, 10.1, 12.1-12.7, 13.3_

- [x] 3. 实现 ProcedureRowDefinition 导入与规范化修订哈希
  - 新建 DefinitionImporter，统一 JSON 模板与 xlsx fallback 的 source locator、program text、ref snapshot 与 legacy aliases。
  - 实现 canonical JSON 规范化与 SHA-256 revision；排除 mtime、绝对路径、导入时间、项目 id 和数组位置。
  - 生成跨项目稳定 definition_key，保留旧 revision，不静默覆盖。
  - 把 row-{program_no}/数组序号仅登记为 legacy alias。
  - 编写 PBT P1-P3：跨项目/机器/顺序稳定、mtime 不敏感、语义变化 revision 改变、legacy alias 不成为身份。
  - _需求：1.1-1.7_
- [x] 4. 实现显式 materialize 与底稿原子绑定
  - 新建 `ProcedureTaskMaterializationService` 与显式 POST；项目初始化、backfill、preview job 复用同一服务。
  - 按 active partial unique 批量 upsert，禁止逐行 N+1；已存在 task 不得被重置 assignee/reviewer/workflow/versions。
  - 实现 `wp_id=NULL` 先委派模型与底稿生成事务内 bind；验证 wp/project/wp_index 唯一绑定。
  - render-config 只做 definition/task overlay；未物化返回 `task_id=null/materialization_required=true`。
  - 实现 delegation preview 前置 materialize job 与状态查询；job 失败不产生 preview。
  - 编写 PBT P4-P7：并发物化唯一、绑定不换 task、重试幂等、GET 零写与未物化 overlay。
  - _需求：2.1-2.8, 12.2_

- [x] 5. 实现模板 reconcile 与显式继承
  - 实现 definition_key→legacy alias→唯一规范内容匹配，输出 matched/unmatched/ambiguous/orphaned/conflict。
  - reconcile preview/apply 使用 ProcedureOperationPreview；目标 revision/version 变化返回 409。
  - ambiguous/orphaned/conflict 不继承 assignee/reviewer/workflow/IssueTicket/history；仅 Delegator 显式 resolution 可应用。
  - 保留旧 definition/task 快照供审计并记录 reconcile history。
  - 编写 PBT P8 与 revision/别名/歧义/孤儿 PostgreSQL 集成测试。
  - _需求：1.6, 3.1-3.2, 3.8, 4.2-4.6_

- [x] 6. 重建粗裁/细裁与方案应用
  - 保留 WorkpaperScopeInstance 的 execute/skip/not_applicable 粗裁；ProcedureRowTask applicability 只表达 execute/not_applicable。
  - 细裁 not_applicable 调 TransitionService cancel；恢复为 execute 后必须 reopen→assign→ack。
  - 方案 key 改为 `scope:{cycle}:{wp_index_code}` / `row:{template_code}:{sheet_key}:{definition_key}`，保存 revision/text snapshot。
  - 重写 scheme preview/apply，使用一次性 ProcedureOperationPreview，返回真实 applied/unchanged/conflict。
  - legacy UUID key 无法唯一转换时 migration_conflict + 409，不按顺序或文本猜测。
  - 编写 PBT P9-P10 与 preview 后版本变化/无变化 applied=0 测试。
  - _需求：3.3-3.8, 4.2-4.6_

- [x] 7. 收敛项目权限、成员归一化与 SOD
  - 实现唯一 `require_project_delegator`：仅 admin 全局放行；partner/signing_partner/manager 必须当前项目 active ProjectAssignment。
  - 通过 active StaffMember.user_id→ProjectAssignment.staff_id 唯一链路授权；缺失、无 user_id、inactive、重复映射、查询异常均 fail-closed 403。
  - assignee_staff_id/reviewer_staff_id 均引用 staff；actor/recipient 使用 user；所有 SOD 先归一 user。
  - 为 materialize、reconcile、trim、scheme、delegation、cancel/reopen、dead-letter replay 挂同一 guard。
  - 建 participant/history-readonly guard 与跨项目 task/preview/conversation/issue/deep-link 绑定测试。
  - 编写 PBT P16、P32 及角色×项目 assignment 权限矩阵。
  - _需求：5.1-5.3, 8.5-8.6, 11.1-11.6_

- [x] 8. 实现三粒度 delegation 与安全 preview/apply
  - 实现 cycle/workpaper/wp_index/row selector，展开到粗裁保留且 applicability=execute 的 tasks。
  - preview 输出 materialize job、目标/状态/冲突/成员负载/受影响底稿和目标双版本。
  - 保存 actor/project/operation/request hash/target versions/membership snapshot/scheme revision/TTL/result；apply 校验并一次消费。
  - 支持 unassigned_only/reject_on_conflict/replace_with_reason；默认原子，显式 best_effort 才允许逐项结果。
  - 同执行人重复分配为 no-op；转派理由 5–500 字符；首次/换人递增 assignment_version 并清 ack。
  - 每 task 写独立 history/outbox，共享 delegation_batch_id；不得修改底稿主编或循环责任范围。
  - 编写 PBT P11-P15：selector 等价、篡改/重放/越权/过期 409、一次消费、批量原子、owner 隔离。
  - _需求：4.1-4.10, 6.4, 10.7_

- [x] 9. 实现状态机、任务真源、精确投影与旧状态映射
  - 实现 TransitionService 的 assign/ack/start/submit/request_changes/review/cancel/reopen 转换表；assign 仅 unassigned→assigned，cancelled 必须 reopen。
  - 同 assignment_version 重复 ack 是业务 no-op；恢复原执行人仍需新 assign/ack。
  - 校验 actor、wp_id、applicability、执行说明/证据、lock_version、assignment_version；非法转换零副作用 409。
  - task/history/outbox 同事务；parsed_data 仅用 jsonb_set 精确路径 + WorkingPaper version/lock 镜像，禁止整列 RMW。
  - 旧 `wp_procedure_status` 与控制台状态写入口全部转调 TransitionService；render task overlay 优先。
  - 实现保守映射表和 migration_confidence/conflict，未知/矛盾不猜测。
  - 编写 PBT P19-P24/P33，含不同 JSON 路径并发不丢、投影删除重建、旧状态表驱动测试。
  - _需求：6.1-6.9, 7.1-7.9, 12.5-12.6_
- [x] 10. 实现 ordered outbox dispatcher
  - 扩展领域 outbox 写入 aggregate_type/id/version、idempotency_key、available_at、lease_expires_at、claimed_by、processed_at。
  - 实现 startup/shutdown dispatcher、并发 claim lease、过期回收、退避、dead-letter、replay 与指标。
  - 同 aggregate 仅处理最小未完成 version；前序失败时后序不得越序。
  - 用独立事务写并提交 Notification，再发送含 event_id 的 at-least-once SSE，最后标 processed。
  - 开关 `PROCEDURE_TASK_DISPATCHER_ENABLED=false` 时停止 claim 但保留事件。
  - 编写 PBT P29-P30 与双 dispatcher、lease 超时、notification 成功/SSE 失败、replay 集成测试。
  - _需求：10.1-10.6, 10.9, 13.2, 13.8_

- [x] 11. 实现通知聚合、metadata 与深链刷新
  - Notification dedup 使用 event_id+recipient_user_id；API 返回 metadata，不从中文 content 解析路由。
  - 批量委派按 delegation_batch_id+recipient 聚合一条摘要通知，同时保留逐任务 history/outbox。
  - 聚合 metadata 保存 batch/project/task count/task ids 或筛选条件；已读/未读点击均可跳转。
  - 前端 SSE 按 event_id LRU 幂等，收到后重新拉取未读数和任务列表；重复/丢失最终收敛。
  - reviewer_missing、assign/reassign/submit/changes_requested/review/comment/reply 类型前后端同步。
  - 编写 PBT P30-P31 与 N task/M recipient 聚合、重复 SSE、已读深链组件测试。
  - _需求：5.6, 8.7, 10.4-10.9, 14.2-14.3_

- [x] 12. 实现任务查询 API 并重构 MyProcedureTasks.vue
  - 新建项目级/跨项目分页查询，按 active staff 的 assignee/reviewer covering index 过滤。
  - 返回 nullable wp_id、definition/sheet 快照、双版本、due_at、overdue、materialization_required；due_at 为空永不逾期。
  - 原位重构现有 `MyProcedureTasks.vue`，增加我执行的/我复核的、筛选、状态动作、未生成空态，不新建平行页面/路由。
  - 无 wp_id 不构造链接；有 wp_id 携带 task_id+sheet_key+definition_key。
  - 修复旧 execution_status→updateProcedureTrim bug，状态动作使用 transition API 和 expected versions。
  - 编写 PBT P27-P28、API schema/pagination/空态/跨项目权限、前端网络 payload 回归测试。
  - _需求：9.1-9.8, 12.3, 14.3-14.4_

- [x] 13. 实现操作复核、IssueTicket 与历史参与者授权
  - reviewer resolver 严格按显式 staff→WorkingPaper/WpIndex reviewer 的项目唯一 active staff→唯一 primary manager→reviewer_missing。
  - 使用 ReviewConversation 关联 procedure_row_task；不把 task_id 塞入 ReviewThread.wp_id。
  - changes_requested 创建/复用 `IssueTicket(source=review_comment, source_ref_id=task_id, conversation_id)`；review 前全部 closed。
  - reviewer 转派后历史参与者可读参与期间历史/消息/issue，但没有当前 transition 权限；授权不只依赖 initiator/target。
  - 明确程序行 reviewed 只表示一级复核，不改变 partner/QC/EQCR 高阶复核状态。
  - 编写 PBT P17-P18/P25-P26 与多轮退回→回复→关闭 issue→再提交→通过集成测试。
  - _需求：5.4-5.8, 8.1-8.8_

- [x] 14. 重构裁剪页、程序控制台与一级复核 UI
  - 裁剪页明确底稿范围/底稿主编与程序适用性/程序执行人/操作复核人；显示 materialize job 和 server preview。
  - GtAProgramConsole 使用 task overlay，未物化只展示；管理者可选行委派，成员按状态动作。
  - 深链按 sheet_key+definition_key 清筛选、展开、滚动、高亮；失配显示模板变化，不按 program_no 猜测。
  - 接入 ProcedureReviewPanel、IssueTicket 未解决数和历史只读标识；高阶复核独立显示且不削弱门槛。
  - 统一中文术语，真实展示 applied/unchanged/conflict、preview TTL/一次消费 409。
  - 运行相关 vitest/fast-check、Vite transform；不得仅依赖 get_diagnostics 判断 SFC 运行时正确。
  - _需求：3.7, 5.7-5.8, 8.1-8.8, 9.5-9.7, 14.1-14.3_
- [x] 15. 完成 backfill、cutover 与非破坏回滚
  - 实现可恢复/可重复 backfill：definition import、task materialize、legacy alias、保守状态映射、canonical trim key、coverage/conflict/orphan 报告。
  - legacy ProcedureInstance assignment 仅作底稿主编候选，不复制到每条程序；矛盾写 migration_confidence/conflict。
  - 落地 expand→dual-read→backfill→cutover→contract 阶段 guard 与三开关行为矩阵。
  - dual-read 比较 task/projection；cutover 前校验 coverage、冲突阈值、投影一致性、dispatcher backlog 和回滚演练。
  - 生产回滚停止 task 新写、停止 dispatcher、保留新表/列/outbox，退回 dual-read/legacy fallback；不提供破坏性 down。
  - 加 CI guard：GET 禁写、TransitionService 单入口、ProcedureInstance 粒度、parsed_data 精确写、前后端通知类型。
  - 编写 PBT P34 与中断恢复、重复 backfill、开关矩阵、回滚数据保留测试。
  - _需求：7.6-7.9, 13.1-13.9_

- [x] 16. 完成 CI、自动化与性能验证
  - 运行 V105 migration/ORM/schema drift/information_schema/partial index/ON CONFLICT 契约测试。
  - 运行后端 targeted unit/PBT P1-P34、PostgreSQL 并发/事务/dispatcher 测试；PBT 使用项目 fast profile并报告真实反例。
  - 运行前端 vitest/fast-check、相关 Vite transform 和 GET 零写/旧 bug 契约守卫。
  - 压测 5000 task preview ≤3s、任务查询 p95≤2s、单任务转换 p95≤1s，并验证 covering/claim index 查询计划。
  - 验证结构化 metrics/trace_id 与日志隐私，不记录附件正文或敏感凭证明细。
  - 任一失败必须修复后重跑；不得以跳过、降低断言或假绿完成任务。
  - _需求：1-14 全部自动化验收_

- [x] 17. 完成四角色 Playwright 全链路实测
  - 使用 admin、现场经理、审计助理、操作复核人四角色 fresh navigation；partner/manager 无项目 assignment 必须 403。
  - 验证先委派后生成：task wp_id 为空可分配；底稿生成后原子绑定且 task_id/assignment/history 不变。
  - 验证按循环/科目/行 preview、一次消费、篡改/重放/过期 409、同人 no-op、转派重新 ack。
  - 验证助理 ack→start→submit，复核人 changes_requested→IssueTicket→回复/关闭→再提交→review；高阶复核门槛不变。
  - 验证批量委派逐任务历史但每 recipient 聚合通知、重复 SSE event_id 幂等、已读通知仍跳转。
  - 验证 nullable wp 空态、深链精确 definition、模板失配、跨项目 IDOR、due_at null、刷新 round-trip。
  - 验证 production rollback 演练后的 dual-read 可用、dispatcher 停止且新表/outbox 保留；全程 0 console error，并保存截图/网络/数据库证据。
  - _需求：14.6 及 Requirements 1-14 全链路_

## Notes

- Wave 1 只能执行 Task 1；本次文档修订完成后不得开始 Wave 1。
- 17 个任务全部必做，无 optional、`*` 或“可跳过”任务。
- ProcedureRowDefinition 是模板身份真源；ProcedureRowTask 是项目工作流真源；parsed_data 是可重建投影；ProcedureInstance 只是粗裁范围。
- 所有 GET/render-config 只读。所有写入必须来自显式 command、初始化、preview materialize job、reconcile apply 或 backfill。
- service 只 flush；router/dispatcher 明确 commit。领域状态与 outbox intent 原子，Notification 提交后才发送 at-least-once SSE。
