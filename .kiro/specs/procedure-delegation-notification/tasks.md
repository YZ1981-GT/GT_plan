# Implementation Plan

## Overview

本计划原以 V104 为基线并用 V105 完成 expand；当前代码库最高迁移已是 V105，主体领域链已实现。第四轮代码复盘发现若干 cutover 阻断项，因此保留 17 个原任务编号并把存在反例或缺少验收证据的任务回退为 `[~]`，新增 V106 additive hardening，不修改 V105。全部必做、无 optional。

状态语义：`[x]`=实现与证据均已核实；`[ ]`=尚未执行或主体已有但第四轮整改/证据未闭环。不得因为已有代码、单测或旧完成记录直接恢复 `[x]`；必须完成任务内新增整改项并更新 evidence manifest。

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

整改依赖：Task 2/3 完成 current revision/V106 后，Task 4 才能修精确 overlay 与绑定；Task 9 可与 Task 4 并行但必须在 Task 14 前完成；Task 10 完成 durable delivery/barrier/lifecycle 后 Task 11/13 才能关闭通知旁路；Task 12 依赖 Task 9/11；Task 14 依赖 Task 4/9/12/13；Task 15 依赖 Task 2-14；Task 16 依赖所有整改代码，Task 17 依赖 Task 16。

## Tasks

- [x] 1. 冻结基线与建立结构性护栏
  - 记录并测试真实粒度：`ProcedureInstance` 是 WorkpaperScopeInstance，不是程序行；禁止新增以其 id 作为 task id 的消费者。
  - 建立 GET/render-config 零写 baseline，捕获 definition/task/preview/projection/outbox 与 WorkingPaper version 前后快照。
  - 为现有真实前端 bug 建回归基线：UI 改 `execution_status` 却调用 `updateProcedureTrim`，payload 不含 `execution_status`。
  - 增加静态守卫 fixture：禁止直接写 parsed_data workflow、禁止绕开 TransitionService、禁止新增平行 MyProcedureTasks 页面。
  - 确认 migration status 最高 V104，预留 V105 文件名与 ORM/DDL 契约入口。
  - _需求：2.5, 7.3-7.5, 9.4, 9.7, 13.9_

- [x] 2. 实现 V105 expand 数据模型与 V106 cutover-hardening
  - 保留已落地 V105，不得回改；新增 V106 additive migration 与 ORM：`procedure_template_revisions` current registry、必要 barrier/heartbeat 索引或状态、history append-only 防护。
  - V106 回填只在某 template_code 存在可证明唯一 revision 时设 current；多 revision/歧义标 reconcile_pending，不按时间猜测。
  - 新建/核验 `procedure_row_definitions`、`procedure_row_tasks`、`procedure_row_task_history`、`procedure_operation_previews` 与现有字段/FK/nullability。
  - ProcedureRowTask 使用 `project_id + wp_index_id NOT NULL`，`wp_id NULL`；加入 audit_cycle_snapshot、due_at、assignment_version、lock_version、migration_confidence/detail。
  - active partial unique 与 materialize ON CONFLICT 谓词必须一致；保留 assignee/reviewer covering indexes 与 outbox claim/order index。
  - 用 information_schema/pg_catalog 验证 V105+V106 列类型、nullable、FK、index/include、partial predicate、current revision 唯一性与 append-only 防护；同名错结构 fail-fast。
  - 新增 V106 迁移契约与 P35 数据库属性测试。
  - _需求：1.1-1.2, 2.1-2.2, 4.2, 10.1, 12.1-12.7, 13.3, 15.1-15.2, 15.11_

- [x] 3. 实现 ProcedureRowDefinition 导入、current revision 与稳定行身份
  - 保留 DefinitionImporter 的 JSON/xlsx 规范化、SHA-256 revision、definition_key 与 legacy aliases；补 current revision registry 登记/显式激活，导入本身不得隐式切 current。
  - 把 `sheet_key + definition_key + definition_revision_hash` 写入标准 ProgramRow schema/模板快照/render 输入，禁止数组序号成为长期身份。
  - current 缺失、多值或 reconcile_pending 时 fail-closed；不得以最新 created_at/hash/导入顺序猜测。
  - 编写 PBT P1-P3/P35-P36：跨项目稳定、mtime 不敏感、语义变化、历史 revision 隔离、跨 sheet 重号、空 program_no。
  - _需求：1.1-1.7, 15.1-15.3_
- [x] 4. 收敛显式 materialize、精确 overlay 与底稿原子绑定
  - materialize 未显式给 revision 时只从 current registry 唯一解析；一次性集合查询全部目标 wp_index/wp_code/revision definitions，消除 per-wp_index N+1。
  - ProgramRow overlay 只按 `sheet_key+definition_key+definition_revision_hash`；删除按 program_no 的 `setdefault`/first-match，旧行缺 key 仅显示待对账。
  - bind 锁定全部 anchor tasks 后先校验；任一 task 已绑定异 wp 则整批 409/零写，全部合法才批量绑定并在同事务 rebuild projection。
  - 建立全部 WorkingPaper 创建/复制/导入入口 inventory 与 CI bind coverage guard。
  - 保留 delegation preview 前置 materialize job；job 失败不产生 preview。
  - 编写 PBT P4-P7/P35-P37 与 PostgreSQL 测试：历史 revision 隔离、跨 sheet 重号、绑定冲突零写、投影原子、5000 行 query-count/EXPLAIN。
  - _需求：2.1-2.8, 12.2, 15.2-15.5, 15.9_

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

- [x] 9. 收敛状态机 CAS、任务真源、精确投影与审计快照
  - 保留 TransitionService 转换表；所有外部 mutation 强制 expected lock_version，assignment mutation 再强制 expected assignment_version。
  - CAS 由 service 内原子 UPDATE RETURNING 或 service-owned FOR UPDATE 保证，不依赖 router；cancel/reopen/trim/scope mutation 同样覆盖。
  - mutation 前冻结 old snapshot、后生成 new snapshot；history writer 用 sentinel 区分未提供与真实 NULL，修首次 assign/reopen/reviewer 变化审计。
  - task/history/outbox/projection 同事务；parsed_data 仅 jsonb_set 精确路径，旧写入口只作 TransitionService adapter。
  - 编写 PBT P19-P24/P33/P38 与真实 PG 并发测试，覆盖首次 assign、换人、清人、同版本竞态、失败零副作用。
  - _需求：6.1-6.9, 7.1-7.9, 12.5-12.6, 15.6-15.7_
- [x] 10. 收敛 ordered outbox、aggregate barrier 与跨 worker dispatcher
  - 保留 claim lease/退避/replay/Notification dedup；修 dead-letter 前序仍阻塞后续 version，新增审计 waive/skip 决议。
  - dispatcher 在应用 lifespan 显式 start/stop，多 worker 依赖 lease/SKIP LOCKED；暴露 heartbeat/backlog/oldest/barrier/跨进程 publish 指标与健康状态。
  - Notification commit 后通过 Redis Pub/Sub（或共享 broker）发布 event_id，各 worker 本地 SSE fan-out；SSE 只作 wake-up，客户端持久化 API catch-up。
  - 开关关闭停止 claim 但保留事件；comment/reply 等禁止直发旁路。
  - 编写 PBT P29-P30/P39-P40 与双 worker、断线重连、dead-letter barrier、lease 超时、Notification 成功/wake-up 失败/replay 集成测试。
  - _需求：10.1-10.12, 13.2, 13.8, 15.12_

- [x] 11. 收敛通知聚合、metadata 与前端刷新
  - Notification dedup/批量摘要/metadata 深链继续复用；assign/reassign/submit/changes_requested/review/reviewer_missing/comment/reply 类型全部走 outbox。
  - 前端按 event_id LRU 幂等，并以 200–500ms debounce 合并任务与未读数刷新；N 个任务事件不得触发 N 次全量请求。
  - 支持 reconnect cursor/last event id 后从持久化 API catch-up；已读通知仍可跳转。
  - 编写 PBT P30-P31/P39 与 N task/M recipient、重复/漏失 wake-up、跨 worker、刷新次数上限组件测试。
  - _需求：5.6, 8.7, 10.4-10.12, 14.2-14.3_

- [x] 12. 收敛任务查询 API 与 MyProcedureTasks.vue
  - 查询补 project/wp_index/due range、服务端 overdue total、assignee/reviewer 展示与 materialization 状态，保持 active staff covering index。
  - UI 补项目/底稿/截止筛选、参与者列、底稿未生成的刷新/提醒、review conversation/IssueTicket 入口。
  - 409 按 reason code 展示可操作信息（版本冲突、reviewer_missing、issue 未关闭、preview 过期），按钮按 request_id 防重复。
  - nullable wp 不造链接；有 wp 携带 task_id+sheet_key+definition_key+revision。
  - wake-up 采用合并刷新；逾期总数不得按当前页计算。
  - 编写 PBT P27-P28/P39、API schema/filter/pagination/空态/权限与前端 payload/刷新次数回归测试。
  - _需求：9.1-9.8, 12.3, 14.3-14.4, 15.3_

- [x] 13. 收敛操作复核、IssueTicket、历史参与者与通知路径
  - 保留 reviewer resolver、ReviewConversation 与 IssueTicket 门槛；确认 GET conversation 严格零写。
  - comment/reply/reviewer_missing/changes_requested/review 全部同事务写 outbox，删除直接 Notification/SSE 旁路。
  - reviewer 转派后历史参与者可读参与期间记录但无当前动作权限；高阶复核不受影响。
  - 编写 PBT P17-P18/P25-P26 与通知重试、GET 零写、多轮返修集成测试。
  - _需求：5.4-5.8, 8.1-8.8, 10.10_

- [x] 14. 完成 legacy 裁剪页 cutover、精确控制台深链与一级复核 UI
  - 将 `ProcedureTrimming.vue/commonApi` 的保存裁剪、方案应用和委派切到新 materialize→preview→apply/transition 契约；显示 job、TTL、真实 changed/unchanged/conflict 与结构化 409。
  - GtAProgramConsole 使用三元组 task overlay；未物化只展示。深链必须真实清筛选、展开、滚动、高亮，失配提示模板变化，不按 program_no 猜测。
  - 接入 ProcedureReviewPanel、IssueTicket 未解决数和历史只读标识；高阶复核独立显示。
  - 运行 vitest/fast-check/Vite transform，并用 Playwright fresh navigation 验证真实控制台行为，不只断言 URL。
  - _需求：3.7, 5.7-5.8, 8.1-8.8, 9.5-9.7, 14.1-14.3, 14.8, 15.3, 15.8_
- [x] 15. 完成 V106 backfill、write freeze、cutover 与非破坏回滚
  - 保留可恢复 backfill 与 dual-read diff；新增 current revision 回填/歧义报告、WorkingPaper 创建入口 bind inventory。
  - 统一 WRITE_MODE 为 `legacy|dual|task_source|paused` 并实现合法迁移；删除/拒绝未声明的同义模式。
  - 建 legacy endpoint/page 调用清单与 guard；task_source 下用户可达路径不得写 legacy，paused 下所有新领域写零副作用拒绝。
  - cutover 前校验 current revision、coverage/conflict、projection、legacy write freeze、dispatcher heartbeat/backlog/barrier 和回滚演练。
  - 保留 V105/V106 新表列/outbox，不提供 destructive down。
  - 编写 PBT P34/P41 与中断恢复、模式矩阵、入口 drift、回滚数据保留测试。
  - _需求：7.6-7.9, 13.1-13.9, 15.8-15.12_

- [x] 16. 完成 CI、自动化、性能验证与 evidence manifest
  - 运行 V105/V106 migration、ORM/schema drift、pg_catalog/current revision/partial index/append-only 契约测试。
  - 运行后端 targeted unit/PBT P1-P42、PostgreSQL 并发/事务/dispatcher；前端 vitest/fast-check/Vite transform 与 GET 零写守卫。
  - 压测 5000 task preview≤3s、materialize query-count/EXPLAIN、任务查询 p95≤2s、transition p95≤1s、跨 worker wake-up 与 debounce 刷新上限。
  - 建 `.kiro/specs/procedure-delegation-notification/evidence/acceptance-manifest.md`（或机器可校验 JSON+Markdown），逐项记录命令、环境、时间、结果、关键输出与失败修复。
  - 增加 completion guard：Task 2-15 的必需 evidence 缺失时禁止 Task 16/17 和 spec 100%。
  - 任一失败必须修复后重跑，不得跳过、降断言或假绿。
  - _需求：1-15 全部自动化验收，14.7, 15.12_

- [x] 17. 完成四角色 Playwright 全链路实测与最终复盘
  - 使用 admin、现场经理、审计助理、操作复核人 fresh navigation；验证项目权限与跨项目 IDOR。
  - 验证先委派后生成、bind 冲突零写/成功原子投影、revision 精确身份、同版本并发、返修/IssueTicket/review。
  - 验证 legacy 裁剪页已切新契约、task_source write freeze、paused rollback、跨 worker wake-up/重连 catch-up/dead-letter barrier。
  - 验证真实 GtAProgramConsole 清筛选/展开/滚动/高亮、nullable wp、模板失配、due_at、刷新 round-trip、0 console error。
  - 保存截图、network、数据库与日志证据到 manifest；复盘发现的可修缺口必须先补 spec/代码/测试再重跑。
  - 仅当 P1-P42、性能、四角色、回滚和证据 guard 全绿时标记 Task 2-17 完成并更新 INDEX。
  - _需求：14.6-14.8, 15.12 及 Requirements 1-15 全链路_

## Notes

- 当前最高迁移 V105；整改从 Wave 12 开始，V106 只 additive，禁止修改已存在 V105。
- 17 个任务全部必做，无 optional、`*` 或“可跳过”任务；整改项统一使用标准 `[ ]`，确保计入 pending。
- ProcedureRowDefinition 是模板身份真源；current revision registry 是运行时 revision 选择真源；ProcedureRowTask 是项目工作流真源；parsed_data 是可重建投影；ProcedureInstance 只是粗裁范围。
- 所有 GET/render-config 只读。所有写入必须来自显式 command、初始化、preview materialize job、reconcile apply 或 backfill。
- service 只 flush；router/dispatcher 明确 commit。领域状态与 outbox intent 原子，Notification 提交后才发布跨进程 wake-up；SSE 不作为可靠队列或状态真源。
- 每个 `[x]` 必须有 evidence manifest 条目。三件套或代码复盘发现反例时，应先回退状态、修 spec/实现/测试，再恢复完成。
