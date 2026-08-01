# 程序裁剪与委派主链收敛 — Requirements

## 背景
现有 `ProcedureInstance` 粗裁范围、`WorkingPaper.assigned_to` 底稿主编与 `ProcedureRowTask` 行任务三层模型均需保留，但生产调用仍混用旧写链。本文只修复主链漂移，不修改已关闭 spec 的历史证据。

## 需求
1. **粗裁单一写入口**：系统必须按 canonical scope key（cycle + wp_index_code）执行 preview/apply；apply 必须消费同一 entries 和一次性 preview，返回真实 applied/unchanged/conflict。
2. **参照项目转换**：应用参照项目时必须读取源项目当前 `wp_code + status` 并构造 canonical entries；不得消费 UUID-key `trim_data`、不得按数组顺序静默映射。
3. **旧接口下线**：旧 trim、apply-scheme、batch-apply、execution、assign 写接口必须稳定返回 HTTP 410 和机器可读错误码；生产前端不得调用。
4. **授权完整性**：初始化、自定义程序、模板生成、底稿主编委派、materialize 与裁剪/委派 apply 等项目写入口必须统一通过项目 Delegator 守卫；读入口必须至少验证项目成员身份。
5. **底稿主编语义 API**：系统必须提供明确的 Workpaper Lead API，并原子更新 `WorkingPaper.assigned_to`、`ProcedureInstance.assigned_to` 投影、统一委派历史、policy epoch 与 invalidation outbox。
6. **行委派单一协调器**：生产行委派必须通过 `ProcedureRowDelegationCoordinator`，在同一事务内调用状态机并记录统一 history、policy epoch、invalidation outbox；不得直接接入旧 `delegate_row()`。
7. **reviewer-only 正确性**：同执行人仅变更操作复核人必须被识别并应用；old/new assignee/reviewer 快照必须准确；reviewer-only 不递增 assignment_version；no-op 零副作用。
8. **批事务语义**：默认批委派任一失败整体回滚；best_effort 每任务使用 savepoint，失败任务不得残留 ORM 修改或 visibility 副作用。
9. **物化语义**：materialize 写入口必须授权；委派 preview 遇未物化行时同步完成物化并继续返回 ready preview；不得依赖进程内 job 作为可追踪生产真源，旧 job 查询返回 410。
10. **生产授权缓存**：所有 Wp_Bound_Gate 调用必须注入持久 epoch cache，使撤权在 Redis 不可用时仍于安全窗口内重查或拒绝。
11. **rollout fail-fast**：写模式值域统一为 `legacy | dual | task_source | paused`；非法值或非法三开关组合必须在应用 Ready 前失败；本次不得修改本地 `.env` 强制 cutover。
12. **工程与验收**：CI 架构守卫必须阻止旧前端 API、旧服务生产调用、协调器外人员字段直写、进程内 materialize job 回流及 gate 漏 epoch；完成前必须通过针对性后端/前端测试、Vite 校验与 fresh-navigation 多角色 Playwright round-trip，且不得假绿。