# Implementation Plan

## Overview

本计划实现服务端强制的底稿与页面可见性隔离，并修复底稿主编与程序行委派“分层但不联动”的问题。全部 18 个叶子任务均为必做任务，没有 optional/`*`。任务先建立 inventory、证据与持久真源，再实现角色/解析/grant/gate 和两层事务，随后覆盖全部 HTTP/非 HTTP 入口、前端、缓存限流和真实验收。

当前迁移 head 已核实为 V112，但 Task 2 开始前必须重新扫描；若候选版本被占用，使用当时下一空闲版本并同步契约，不得静态抢占 V113。

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 1, "tasks": ["1", "2"]},
    {"wave": 2, "tasks": ["3", "4"]},
    {"wave": 3, "tasks": ["5", "7"]},
    {"wave": 4, "tasks": ["6", "8"]},
    {"wave": 5, "tasks": ["9", "10", "11"]},
    {"wave": 6, "tasks": ["12", "13"]},
    {"wave": 7, "tasks": ["14", "15", "16"]},
    {"wave": 8, "tasks": ["17"]},
    {"wave": 9, "tasks": ["18"]}
  ]
}
```

依赖：Task 1/2 冻结入口、证据和 schema；Task 3/4 建角色映射与绑定解析；Task 5/7 建 grants 与权限事务；Task 6 组装矩阵/gate，Task 8 建正式列表；Task 9–11 覆盖入口；Task 12/13 完成 UX、缓存与 measurement；Task 14–16 完成正确性、集成和漂移门；Task 17 生成并冻结真实限流 profile 后验收；Task 18 仅在全部证据通过后关闭规格。

## Tasks
- [x] 1. 建立入口基线、Evidence Schema/Manifest 与规格护栏
  - 扫描 FastAPI routes、router registry、callback/worker/retry/dead-letter registry，生成 `wp_bound_entry_coverage.json` 初始 ledger；每条登记 kind、稳定 entrypoint/callable、route/method、family、action、binding、gate、matrix 和稳定 test ids，现存缺口只能标 `unmigrated`，不能漏项。
  - 创建 spec `evidence/manifest.schema.json`、初始 `manifest.json`、append-only run writer 与 precheck；从本任务起记录 task/test id、当前 run、spec 内相对 artifact、SHA-256、size，保留失败 run。
  - 添加 baseline 契约：`working_paper` 单数、lead user_id、projection/row staff_id、render/AI/attachment/WOPI 当前缺口、V112 head 与 traceback 临时日志风险；baseline 不得假装实现通过。
  - _Requirements: 2.2–2.10, 8.5–8.17, 13.1–13.15, 15.1–15.11, 16.21–16.23_

- [x] 2. 实现统一委派历史、安全审计与持久 policy epoch 迁移
  - 开始前重新扫描迁移 head并分配下一空闲版本；同步 migration/schema drift/column contract，处理 V105/V112 后续漂移。
  - 新增 append-only `workpaper_delegation_history`，同时快照 lead/assignee/reviewer 的 project/wp_index/wp/task/sheet/old+new user/old+new staff/actor/reason/scope/time；History_Set 禁止回查当前 staff/task 归属。
  - 新增 `wp_access_security_outbox`、`wp_visibility_policy_epoch`、`wp_visibility_invalidation_outbox`；权限变更事务可原子递增 epoch 并写 invalidation row。history/outbox 禁 UPDATE/DELETE，reason 含 `rate_limited`，敏感正文/token 不入表。
  - 先跑 PostgreSQL EXPLAIN；只在实证必要时增加 `working_paper`/history 支撑索引。实现 ORM、幂等 DDL、防改触发器、schema contract 和 rollback 测试。
  - _Requirements: 3.13–3.15, 5.18, 9.8–9.11, 14.20–14.21_

- [x] 3. 实现唯一角色分类与严格 staff↔user 映射
  - 新建 `StaffUserMappingService`：写事务只接受目标项目唯一 active StaffMember、非空 user_id、唯一反向映射；跨项目、缺失、重复、inactive 均拒绝。
  - 新建 `VisibilityRoleClassifier`：admin 唯一免 scope；Non_Admin 只有同时具唯一 active StaffMember、ProjectAssignment（项目角色权威）和 ProjectUser（scope 权威）且角色属于允许集合才是 Supervisor；其余 Restricted。
  - scope 缺失/失败解释为空集；未知角色/查询异常 fail-closed，不让实现者在 ProjectAssignment/ProjectUser 间任选角色来源。
  - _Requirements: 1.1–1.11, 2.4–2.6, 3.1–3.6_

- [x] 4. 实现 ProcedureWpResolver 与服务端 sheet binding catalog
  - 联合解析 project、标准/自定义 procedure、已有 wp_index/wp、wp_code、sheet_key/sheet_name；每个已提供来源必须唯一且全部一致。
  - `sheet_name` 只能在确定的 project+wp_index+version 内解析，禁止全局唯一推断；零/多候选、冲突 fail-closed、不改业务数据并记 `binding_conflict`。
  - 建立 checklist item、render sheet、ProcedureRowTask 到稳定 sheet_key 的服务端映射；row-only 入口无法唯一映射时拒绝，不能退化整稿授权。
  - _Requirements: 4.1–4.14, 5.8–5.11, 8.3–8.4_

- [x] 5. 实现 AccessGrant CTE、页面集与历史 Current-Version 只读
  - `VisibilityQueryService` 用单次 UNION ALL 产生 `lead/assignee/reviewer/lead_history/row_history`；history 仅读 Task 2 不可变快照；Admin 显式产生 `admin` grant，Supervisor 对 scope 内 wp 显式产生 `supervisor_scope` grant。
  - 全部 Non_Admin grants 与 `wp_index.audit_cycle∈scope_cycles` 相交；按 wp_index 去重但保留独立 grant/access_kind，nullable wp 仍以 wp_index 计入，空集不回退循环级。
  - lead/admin/supervisor_scope 为 all pages；row 当前/历史只含对应 current/snapshot sheet；History_Only 只读 Current_Version。未知 kind 丢弃该 grant，多 grant 逐个完整匹配后才并集。
  - 用 PostgreSQL query-count/属性测试证明无按底稿 N+1，staff/task 重绑不改变历史归属。
  - _Requirements: 5.1–5.18, 11.1–11.5, 16.5–16.13_

- [x] 6. 实现 Action Matrix、Review Whitelist、Wp_Bound_Gate 与统一拒绝
  - 矩阵键包含 user_class/access_kind/identity/entrypoint/route/method/action/source/target；任一维度未登记即拒绝，多身份禁止拼接。
  - reviewer 白名单仅允许 `submitted→reviewed/changes_requested` 和同 task/sheet 的复核会话动作，拒绝通用 status/checklist/parsed_data/附件关联/version restore/editor write。
  - `resolve_wp_binding_and_access()` 按设计顺序执行资源无关限流→Binding_Minimum→分类/scope/grants/version→claims→matrix；allow 后才读正文或 mutate。
  - 限流 429 在资源解析前产生且不表明存在；进入 gate 后所有不存在/跨项目/out-of-scope/未委派/sheet/action/history/binding/token 拒绝统一 wire 404。安全 outbox 失败保持响应并告警；删除 `_render_config_500.log` 写盘。
  - _Requirements: 7.1–7.10, 8.1–8.4, 8.18–8.19, 9.1–9.11, 14.18–14.19_
- [x] 7. 实现两层委派、清空、scope expansion 与 epoch 原子事务
  - Lead 路径严格映射 staff→user、唯一解析 wp_index，锁行后同事务写 `working_paper.assigned_to=user_id`、`procedure_instances.assigned_to=staff_id` 投影、统一 delegation history、可选 scope、policy epoch 与 invalidation outbox；任一步失败全部回滚。
  - Row 路径只写明确目标 ProcedureRowTask + 既有 task history + 统一 delegation history + epoch/outbox，不写 projection；清空一个角色保留另一 row role、lead 和 projection。
  - 跨循环默认拒绝；仅 delegator 显式 `expand_scope=true` + 非空 reason 才同事务扩权。撤销委派不自动缩 scope；ProjectUser/ProjectAssignment/角色变更入口也必须同事务 epoch/outbox，不能提交后 best-effort 才失效。
  - 改造 `assign_procedures` 走 lead 事务；两层互不覆盖、无 last-write-wins。增加 request_id 幂等、并发转派和崩溃恢复测试。
  - _Requirements: 2.1–2.15, 3.7–3.15, 6.1–6.8, 14.20–14.21_

- [x] 8. 实现服务端正式分页、状态拆分与独立主编视图
  - SQL 顺序固定为参数校验→classification/scope/grants→业务过滤→wp_index 去重→分页前 total/stats→NULLS LAST + wp_index_id ASC→分页→仅 hydrate 可见项；禁止全量到 Python/前端再过滤。
  - data payload 仅 `{items,total,stats,page,page_size}`；空 stats 两字典；非法 page/page_size/sort 在底稿查询前 422。拆 `index_status/file_status` 并记录 legacy mapping。
  - MyProcedureTasks 仅 assignee/reviewer；MyLeadWorkpapers 独立返回 lead 并复用分页/stats；`visibility_mode` 仅 UX；nullable wp 禁止文件动作。
  - _Requirements: 11.1–11.13, 12.1–12.9_

- [x] 9. 将核心底稿、复核、AI、版本与专属子路由接入 gate
  - 覆盖列表/详情/render-config/HTML/checklist、parsed_data/status/专属 `/{wp_id}/...`、试算表回写、task detail/transition/deep-link、review thread/conversation/message/comment、版本/snapshot/compare/restore、AI generate/summarize/OCR context。
  - 每个入口使用 ledger 指定 adapter/action；无 project_id 的 route 服务端反查。row-only 只操作映射 sheet，reviewer 只走 whitelist，History_Only 写入/历史版本统一 404，AI gate 后构造 context。
  - 为每个 route+method 添加 allow/deny/cross-project/sheet/version 测试并更新 ledger stable test ids。
  - _Requirements: 5.8–5.18, 7.5, 8.5, 8.10–8.12, 8.15, 9, 12.7–12.9_

- [x] 10. 将附件、文件、导入导出、批量和非 HTTP 执行器接入 gate
  - 附件 upload/list/read/preview/download/delete/OCR/version/associate 全覆盖；associate 同时校验附件项目、目标 wp 同项目、附件源权限与目标 sheet 写权限。
  - 覆盖 file read/download/preview/convert/PDF/Word/Excel/ZIP、单 sheet import/export/template、bulk dry-run/commit/async/download/result/SSE。
  - manifest 只由可见集构建；显式任一资源拒绝则副作用前整请求失败，bulk write 逐资源 preflight 后按原子模式执行，不能 fail-soft 跳过泄露存在性。
  - callback/worker/retry/dead-letter 实际执行时重新 gate；撤权后排队任务拒绝。登记 kind/callable 和稳定测试 id。
  - _Requirements: 8.6–8.8, 8.13–8.17, 9, 13.13–13.15, 16.17_

- [x] 11. 加固 OnlyOffice/WOPI claims、文件权限与 callback
  - 签名 token 必含非空 `sub,project_id,wp_id,sheet_name,wp_code,version,action,iat,exp,jti`，逐项绑定 URL/服务端资源；secret 缺失、JWT disabled bypass、签名/过期/空值/不一致 fail-closed。
  - config/file read/callback/convert 与 WOPI CheckFileInfo/GetFile/PutFile/lock 全接 gate；`UserCanWrite=gate∩file state∩lock`。
  - callback/PutFile 落盘前重新校验 Current_Version、actor、action、Page_Visibility_Set、persistent epoch；只读 token、跨资源重放、已撤权会话拒绝。
  - 冻结有限 JWT lifetime 并写 evidence；添加 claim、重放、撤权、版本冲突测试。
  - _Requirements: 8.8–8.9, 10.1–10.11, 16.14–16.17_

- [x] 12. 改造前端工作台、深链与两层委派呈现
  - Workbench/详情/目录仅消费服务端分页/allow actions，移除客户端全量过滤边界；404 统一显示“资源不存在或不可访问”，不得闪现缓存名称/正文。
  - MyProcedureTasks 与 MyLeadWorkpapers 分区；nullable wp 显示“底稿尚未生成”并禁用编辑器/下载；深链参数只定位，拒绝后清理缓存。
  - ProcedureTrimming 分别标注底稿层主编和程序行执行/操作复核并读取各自真源；高阶复核不显示为 row reviewer。
  - 添加 vitest/fast-check：分页 envelope、状态拆分、安全占位、nullable wp、client role/visibility_mode 无权、两层状态不串线。
  - _Requirements: 11.10–11.13, 12.1–12.10, 16.19–16.20_
- [x] 13. 实现 persistent epoch 缓存、measurement-mode 限流与性能观测
  - 缓存 key 含 user/project/persistent epoch；outbox→Redis 即时淘汰，节点最多每 1 秒核对 DB epoch；Redis/dispatcher 失败时同步查 DB 或拒绝，禁止 stale allow。
  - 建 Performance_Profile/Rate_Limit_Profile schema 与 measurement mode，不预设业务阈值，不出现固定 10 RPS；profile 必须引用容量报告/hash 才能激活。
  - 实现资源无关 429 + Retry-After 及 gate/list latency、query count、cache hit/miss/stale deny、reason、错误允许数指标；冻结阈值和最终容量验收留 Task 17。
  - _Requirements: 14.1–14.16, 14.18–14.21_

- [x] 14. 建立同源 PBT smoke/correctness profiles 并实现 P1–P20
  - Smoke=5、Correctness 每 property≥100 有效样例，收集相同函数；smoke 不得写完成证据。数据库属性跑 PostgreSQL。
  - 实现 design P1–P20：分类/scope、staff-user、projection/清空、resolver、集合、immutable history、页面、grant/matrix/reviewer、binding/404/outbox、token、分页、UX 参数、HTTP/worker ledger、epoch 原子/撤权、profile activation、evidence hash。
  - 每测试标 feature/property id 并输出有效样例数；profile activation 属性可用合成容量报告验证机制，真实阈值由 Task 17 生成。
  - _Requirements: 15.6–15.12, 16.1–16.16, 16.21–16.24_

- [x] 15. 完成全入口 PostgreSQL/FastAPI 集成、安全回归与 EXPLAIN
  - 每 Entry_Family 代表性 allow/deny/cross-project/sheet/version；直接比较不存在/跨项目/越权/未映射页/历史版本最终 wire 404。
  - 验证 outbox 故障不改 404/429、拒绝前无敏感读取/副作用、两层事务/history/scope/epoch 原子、callback 撤权、bulk preflight。
  - 运行 EXPLAIN/query-count；仅实证后新增索引并证明计划改善。测试 permission commit 后 publish 前崩溃，持久 epoch/outbox 仍阻止 stale allow。
  - _Requirements: 3.14–3.15, 8.1–8.19, 9, 10, 14.20–14.21, 16.15–16.18_

- [x] 16. 完成 HTTP/worker Coverage Ledger、漂移守卫与 CI
  - 将所有 `unmigrated` 更新为真实 gate/matrix/stable test ids；生产 HTTP route+method 与 ledger 双向相等，callback/worker/retry/dead-letter registry/callable 同样双向相等。
  - 完成 AST/registry scanner：展开 prefix/method/dynamic routes，检查重复/stale/缺 gate/matrix；非 HTTP callable 新增或未执行时 re-gate 亦失败。
  - ledger 保存稳定 test id，Evidence Manifest 绑定当前 CI run/artifact。挂 correctness、PostgreSQL integration、token、coverage 和 evidence precheck CI；为 scanner 添加动态/间接 wrapper/伪注释自测。
  - _Requirements: 13.1–13.15, 16.17, 16.21–16.23_

- [x] 17. 运行 6000 并发、冻结 Rate_Limit_Profile 并完成 fresh-context 角色验收
  - 先按版本化 Performance_Profile 运行 6000 已认证用户 baseline，测列表/gate/附件/AI/editor callback/bulk/worker；据结果生成并冻结 Rate_Limit_Profile，记录报告/hash。
  - 使用冻结 profile 再跑完整容量与限流验收：list p95≤2s、gate p95≤1s、成功错误率≤1%、错误允许数=0、阈内不误限、超阈 429 + Retry-After、资源存在性不可推断。
  - 新 browser context + fresh navigation 验收 Admin、Supervisor、Lead、Assignee、Reviewer、History Lead/Row，以及普通无委派 Restricted：scope 内未委派与 scope 外被委派均拒绝。
  - 覆盖列表/tab/URL/write/review/attachment/AI/version/OO-WOPI/刷新与撤权≤1s；排队 callback/worker 重 gate，console error=0，无名称/正文闪现。
  - _Requirements: 5.8–5.18, 9, 10, 14.1–14.21, 16.18–16.20_

- [x] 18. 执行最终 Completion Guard 并关闭规格
  - 汇总 Task 1–18、全部 criteria、stable test ids→当前 CI run、correctness/integration/coverage/performance/Playwright artifacts；失败重跑记录必须保留。
  - Completion Guard 重算 JSON Schema、路径、SHA-256、size，拒绝绝对路径/`..`、缺 artifact、旧 run、smoke 冒充 correctness、任一任务/criterion 最新非 passed。
  - 只有全部门禁通过才将 tasks/spec 标 completed，并更新 INDEX/memory，记录真实迁移号、Performance/Rate profile 版本；否则保持未完成且列出失败证据。
  - _Requirements: 15.1–15.12, 16.21–16.24_

## Notes

- **规格已完成并关闭（2026-07-17）**：Task 1–18 全部实现完毕，最终 Completion Guard 通过。
  - Completion Guard = `app.security.completion_guard`（函数 `run_completion_guard()`/`close_spec()` + CLI `python -m app.security.completion_guard [--strict|--close]`），采用 **latest-run-per-task / latest-run-per-criterion** 语义：Task 1–18 最新 run 全 `passed`；每个被引用 criterion 最新 run `passed`；最新 run artifact 重算 SHA-256/size/相对路径安全/JSON-Schema 全部干净；覆盖/漂移守卫 0 unmigrated 且 HTTP/worker 生产面⇔ledger 双向相等；correctness ≥100 有效样例、smoke 未冒充 correctness。
  - Task 18 证据：seq-32（`evidence/artifacts/task18/completion_guard_report.json`，确定性、byte-reproducible）。测试 `tests/procedure_delegation_visibility/test_task18_completion_guard.py`（3 passed，含 strict 全 1–18 绿）。
  - Task 15 证据确定性重录：seq-31 pin `task15_explain_summary.json`（剥离 EXPLAIN ANALYZE 计时/buffers/行数/成本/时间戳，两次生成 SHA-256 一致），supersedes seq-26/27（`explain_plans.txt` 字节易变，原始文件保留在磁盘不 hash-pin）。真实 app + PostgreSQL `audit_platform` 重跑 45 passed。
  - 历史 superseded run（Task 14 seq-24、Task 15 seq-26/27）按 append-only 保留，其漂移 artifact 不阻断完成，已记录哈希从不改写；全局 `evidence_manifest.precheck()` 会如实列出这 8 条历史漂移，属预期（非 latest run）。
  - 真实迁移号 **V113**（`V113__wp_visibility_delegation_history_audit_epoch.sql`）；Performance_Profile 版本 **perf-6000-visibility-v1**，Rate_Limit_Profile 版本 **rate-6000-visibility-v1**（capacity_report_hash `469e19db…06229`）。
- 历史约束（实施期间遵循）：不得因文档完成而标绿实现任务；任务标记不能假绿；验收以 Evidence Manifest + Completion Guard 为准。
- 本 feature 建立在已提交的 `procedure-delegation-notification` 之上，只消费 `ProcedureRowTask`/`ProcedureRowTaskHistory`（程序行层）与 `WorkingPaper.assigned_to`（底稿主编层）两个既有委派真源，不重建委派模型、不改委派工作流状态机、不改 `scope_cycles` 数据模型与 `require_project_access` 语义。
- 实施 Task 2 前重扫迁移 head；当前基线为 V112，不静态占用 V113。Task 1/16 以真实 app、router 与 worker/callback/retry/dead-letter registry 为准，不以文档清单替代扫描。
- 仅新增统一 append-only 委派历史快照、安全审计 outbox 与 policy epoch/invalidation outbox；可见性支撑索引仅在 PostgreSQL EXPLAIN 证明必要时 additive 增加。
- 表名固定真实 `working_paper`/`wp_index`/`procedure_instances`/`procedure_row_tasks`/`staff_members`/`project_assignments`/`project_users`，禁止 `working_papers`。
- wp-bound 资源判定统一 External_Not_Found；只有认证失败、资源无关前置限流和请求格式校验分别保留 401/429/422。前端隐藏、路由守卫、`visibility_mode` 均不授权。
- 前端验收必须 fresh navigation；SQL/事务/索引必须用 PostgreSQL，不能只靠 SQLite/mock。
- 遵循仓库 steering：async service 只 flush（router 提交）；PowerShell 不触碰 Vue/Markdown；asyncpg 用 `= ANY(:list)`；验收以 Evidence Manifest + Completion_Guard 为准，任务标记不能假绿。
