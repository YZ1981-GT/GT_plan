> `[x]` = 代码与验收均通过；诊断完成但验收失败仍保持 `[ ]`。
> 不修改其他会话的附注模板、模型与迁移在途文件。

## Phase 1：安全旁路

- [x] 1.1 修复 `/api/formula/batch-execute` 项目鉴权与同项目/年度校验
- [x] 1.2 修复 report-config execute/list/types/seed 鉴权旁路
- [x] 1.3 增加跨项目 TestClient：403 + 零副作用 + 混合批次 422

## Phase 2：函数能力

- [x] 2.1 后端实现表达式函数提取与 executor preflight
- [x] 2.2 接入 report 单条/批量、formula 单条/批量、wp 单条/batch 保存
- [x] 2.3 移除静默 0 成功语义，补 unsupported/context_required 契约测试

## Phase 3：原子 CAS

- [x] 3.1 已有公式更新强制 expected_version，缺失返回 428
- [x] 3.2 改为数据库条件 UPDATE，并处理并发插入冲突
- [x] 3.3 增加真实 PG 双事务竞争测试和 batch 全回滚测试

## Phase 4：standalone 执行闭环

- [x] 4.1 coordinator 按 scope/year 规划一次并保留完整 FormulaMutation
- [x] 4.2 仅对有显式安全载体的 A1 `parsed_data` 构造 target；其他域缺 binding 时可见失败且禁止猜 `item_id`
- [x] 4.3 production orchestrator 接 `execute_refresh`，透传 transaction_mode/idempotency_key/operator
- [x] 4.4 同事务 apply、snapshot.source_formula_id、last_computed_at、outbox、audit
- [x] 4.5 修复 all_or_nothing/partial_success rollback 与响应真实 run_id

## Phase 5：真实 capability 与统一 context

- [x] 5.1 删除 synthetic allow capability，WorkpaperEditor 传真实 snapshot/location
- [x] 5.2 capability 请求加 subject/epoch 竞态守卫，失败立即重置 deny
- [x] 5.3 workpaper 与 scope context 显式分流；合并入口不伪造 wpId
- [x] 5.4 dirty 会话固定完整 canonical context；保存消费 pinnedLocation + definition_version，403/409 不丢草稿

## Phase 6：门禁与证据

- [x] 6.1 快速契约门禁接入现有 frontend/backend CI
- [x] 6.2 新增 A1 + 普通底稿 + 合并三 scope 的 blocking Playwright 门禁，禁止恒真/默认 skip
- [x] 6.3 RTK 检查器接 governance CI；warnings 基座另列真实未完成项
- [x] 6.4 输出稳定、无秘密的 UAT evidence JSON（commit/run_id/前后值/ORM 对拍；未提交态显式 `working_tree=true`）

## Phase 7：验收

- [x] 7.1 后端目标矩阵、真实 PG CAS、production-chain、覆盖治理与 rollback 测试全绿
- [x] 7.2a 前端目标 Vitest、纯契约 vue-tsc、IDE diagnostics、ESLint 与 Playwright 代表矩阵全绿
- [ ]* 7.2b `FormulaManagerDialog.vue` 单文件 `vue-tsc` 完整语义检查
  - 2026-10-18 实测 `NODE_OPTIONS=--max-old-space-size=4096` 仍报 `FATAL ERROR: Ineffective mark-compacts near heap limit`；此前 8GB 区域检查同样 OOM。
  - 代码已由 getDiagnostics（改动 Vue 全部 0）+ targeted ESLint（0 error）+ Vitest 527 passed + Playwright 3 passed 覆盖，但不能把 OOM 写成全量类型检查通过。
- [x] 7.3 更新审计 delta、旧 spec 勘误和 INDEX；因 7.2b 外部环境限制保持 active，不归档

## Phase 8：复核新增的运行时治理缺口

- [x] 8.1 `confirm_overwrite` 进入 fingerprint；项目年度级锁串行化不同策略，未确认时跳过 human_edited
- [x] 8.2 runtime mutation 与 DraftMarker/preset marker 同事务；无 canonical binding 的 preset 只记待编制且不计 applied
- [x] 8.3 rollback 修正 before/after 方向，业务值/marker/公式生命周期原子恢复；冲突零部分提交并返回 HTTP 409
- [x] 8.4 `formula_runtime_outbox` 接既有重放 worker（独立 session + `SKIP LOCKED`）；formula_push PG 测试改独立 engine/dispose，消除 `_cancel` 未 await 告警

## 最终证据（2026-10-18，未提交工作树）

- 后端目标矩阵：`163 passed`；严格 PG：`5 passed`（CAS、production apply/rollback、formula_push SQL 故障隔离）。
- 前端公式目标区域：`527 passed / 3 skipped`；3 条 skip 为显式 live-denominator 环境门，不是 blocking Playwright 的默认跳过。
- 浏览器：`formula-manager-runtime-gate.spec.ts` 3/3，真实 admin 登录、A1/D2-1 capability + 当前实例请求、合并三 scope、deny 禁用。
- 门禁：`check_rtk_inner_exit_validation.py` passed；targeted ESLint 0 error；纯契约 `vue-tsc` passed。
- 外部/预存红：全目录 811 项会被历史全 metadata drop 的环 FK SAWarning 打断；live 404 新出现 `B5附件` 未登记；`FormulaPushPanel.spec.ts` 仍按旧 3 GET 断言而生产已有 `/runs`；旧全局 readiness 有非 `/api` 路由基线。这些均非本 spec 生产改动，未越界修改。
