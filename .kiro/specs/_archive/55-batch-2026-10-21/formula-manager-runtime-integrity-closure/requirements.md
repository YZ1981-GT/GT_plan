# 需求文档：公式管理运行时完整性闭环

> spec：`formula-manager-runtime-integrity-closure`
> 来源：`docs/proposals/formula-management-platform-audit-2026-10-17.md`、`formula-manager-closure` 实施后复核。
> 类型：安全修复 + 执行闭环 + 并发一致性 + 真实门禁；不是新建公式引擎。

## 范围与证据纪律

- 复用现有 FormulaEngine、FormulaRuntimeCoordinator、DraftRefreshService、ACNR 与 domain adapters；禁止再造平行执行链。
- `[x]` 仅用于代码已落地且验收通过；诊断发现失败不得标完成，必须拆出整改任务。
- 项目鉴权以服务端数据层查询条件和真实请求 403+零副作用为准，不能以测试文件存在或源码字符串为证。
- 真实运行以目标载体、snapshot、outbox、audit、last_computed_at 同一 run_id 逐值对拍为准。

## R1：封堵全部公式项目鉴权旁路

1. WHEN 批量公式执行被请求 THEN 每条 SHALL 与首条具有相同 project_id/year，目标项目 SHALL 通过 readonly 权限；混合项目/年度 SHALL 返回 422，越权 SHALL 返回 403。
2. WHEN `/report-config/execute-formula` 使用 project_id THEN SHALL 校验 readonly 权限；非法非空 UUID SHALL 返回 400，不得降级纯计算。
3. WHEN list/types 直接传 `applicable_standard=project:{id}` THEN SHALL 反解项目并鉴权；与 project_id 不一致 SHALL 返回 403。
4. WHEN `/report-config/seed` 被调用 THEN SHALL 仅 admin 可执行。

## R2：执行器能力必须由后端强制

1. 每个执行入口 SHALL 根据执行器检查函数支持；不支持、上下文缺失 SHALL 返回结构化错误，禁止静默 0。
2. wp 单条与 batch 保存 SHALL 使用同一函数校验；batch 不得绕过。
3. 支持矩阵 SHALL 区分当前已实现能力与目标能力，禁止用“已注册”替代“上下文可求值”。

## R3：wp_formula 使用数据库原子 CAS

1. 更新已有公式 SHALL 必须携带 expected_version；缺失返回 428。
2. 更新 SHALL 使用单条条件 UPDATE/行锁保证并发原子性；两个并发 PG 事务只允许一个成功。
3. batch SHALL 在一个事务内复用同一 CAS；任一冲突整批回滚。

## R4：standalone 公式必须真正应用到目标载体

1. 生产 draft-refresh SHALL 保留完整 FormulaMutation，不得降格丢失 locator/before/version/source_formula_id。
2. 成功运行 SHALL 调用 adapter.apply_many，更新目标值与 WpFormula.last_computed_at。
3. audit.id、snapshot.refresh_id、outbox.run_id SHALL 相同；响应 run_id SHALL 为真实 audit id，不得回退 project_id。
4. all_or_nothing 任一失败 SHALL 回滚全部业务值、snapshot、outbox 与 last_computed_at；partial_success 只计真正提交的 domain。

## R5：执行观测与传播原子

1. outbox/audit 写入 SHALL 与主写同事务；可降级写入必须使用 SAVEPOINT，禁止吞异常后让 PG 事务 aborted。
2. 历史 issue SHALL 按 run 保留，不得删除后破坏旧 run 可查询性。
3. report_config 保存后的传播 SHALL 走事务 outbox，禁止 commit 后异常静默丢失。

## R6：真实 capability 与保存 pin

1. 工作底稿打开 SHALL 使用服务端返回的 capability snapshot；缺失、过期、subject/epoch 不匹配 SHALL 不打开。
2. formulaView 允许但 formulaEditUser 拒绝时 SHALL 只读打开；所有写入口在请求前 SHALL 统一再校验。
3. capability 请求的迟到响应 SHALL 不得覆盖新项目/sheet；失败 SHALL 立即重置为 deny。
4. 保存 SHALL 使用 pinned canonical location 与 definition_version；打开期间位置/scope 变化 SHALL 保留完整原上下文并显示提示，403/409 后 SHALL 保留草稿。
5. consolidation/report/note/tb SHALL 使用显式 scope context，不得伪造 wpId。

## R7：两层真实门禁

1. 快速 CI SHALL 运行端点鉴权、能力矩阵、CAS、生产调用与前端纯契约测试。
2. 快速层 SHALL 枚举 distinct componentType×host×scope；blocking Playwright SHALL 在 fresh DB 上真实验证 A1、普通底稿及合并三 scope，并禁止夹具缺失时降级通过。
3. 门禁 SHALL 禁止恒真断言、仅检查测试文件存在、后端缺失时默认成功 skip。
4. UAT evidence SHALL 稳定排序、不含凭据，记录 commit、working-tree 状态、run_id、输入、前后值和查询口径。

## R8：覆盖治理与原子回滚

1. runtime 执行 SHALL 在写值前按 canonical unit_scope 检查 `DraftMarker`；未确认时跳过 `human_edited`，确认策略 SHALL 进入幂等 fingerprint。
2. runtime mutation、DraftMarker、preset marker、snapshot、公式生命周期与 outbox SHALL 位于同一事务；无 canonical binding 的 preset 不得计为已应用。
3. rollback SHALL 以 snapshot.before_value 恢复，并以 after_version 做 CAS；任一业务值或 marker 冲突 SHALL 回滚整个恢复 savepoint、返回 HTTP 409，且 restored_count=0。
4. durable outbox SHALL 有生产重放消费者；多 worker SHALL 以行锁跳过已被其他 worker claim 的事件。

## R9：文档状态诚实

1. 旧 `formula-manager-closure` SHALL 追加实施后勘误，明确 30/30 不等于 AC 全通过。
2. 审计报告 SHALL 以 delta 方式更新，不改写历史快照。
3. warnings 与 RTK 仅在真实修复并接入门禁后才可标完成。