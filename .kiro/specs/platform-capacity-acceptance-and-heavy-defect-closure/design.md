# 平台容量验收与重任务残留缺陷收口 — 设计

## 1. 承接边界与不重复实现

上游 `platform-heavy-jobs-and-capacity-closure` 交接式归档（`_archive/188`）。已交付且**不许放宽**的资产：

| 资产 | 位置 | 本 spec 的用法 |
|---|---|---|
| 负载梯度契约 | `tests/load/load_contract.py`（stage_timeline） | R1 直接消费，不再改形状 |
| 六类安全计数校验 | `run_final.py --safety-evidence` | R1.3 先建生产者，再喂给校验 |
| 分布式合并 | `load_stage_stats.merge_stage_payloads`（18 例） | R1.4 逐桶相加后判定 |
| PgBouncer 契约 | `test_pgbouncer_transaction_contract_pg.py`（9 例） | R2.1 作灰度前置门 |
| 连接预算 | `app/core/connection_budget.py`（14 例，4 副本结论） | R2.2 容量规划输入 |
| 事件总线外置 | `event_bus_state_adapter.py` + `event_bus_state_redis.py` | R3.1 多 worker 时注入 |
| 故障注入 | `test_platform_job_fault_injection.py`（5 例） | R3.2 多 worker 重跑 |
| 章节锁并发 barrier | `test_note_section_lock_concurrency_pg.py`（5 例） | R4.1 语义裁决后回归 |
| EXPLAIN 基准 | `test_knowledge_retrieval_explain_pg.py`（5 例） | R4.2 选型证据 |
| statement 计数棘轮 | `test_formula_push_statement_count.py`（20 上限） | R4.3 真 PG 复核 |
| 流式路由棘轮 | `check_streaming_db_scope.py` + 基线 111 | R6 逐条迁移、只降不升 |

## 2. R1 容量环境拓扑

```
负载机（Locust master + workers，--worker-stats-dir 共享目录）
   |  HTTP
   v
后端 2/4/8 worker（uvicorn，EventBus 注入 RedisStateAdapter）
   |  PgBouncer（transaction 模式，POOL_MODE=transaction）
   v
专用可销毁 PG（GT_LOAD_DISPOSABLE_DB_URL，库名黑名单校验）
```

- 压测发起过 `load_guard` 三重闸门；写场景必须 `GT_LOAD_ALLOW_WRITES=1`
  + `GT_LOAD_DISPOSABLE_ENV=YES`。
- 六类安全计数生产者（R1.3，上游 E6 登记的缺口）：
  ①越权回放（低权账号逐端点探测，期望 401/403/404 计为 0 成功）
  ②连接池对账（`/metrics` pool checked_out 采样对账 PG `pg_stat_activity` 计数差）
  ③连接超时（pool checkout timeout 异常计数）
  ④事件丢失（SSE 事件序号对账：发送序列 vs 接收序列差集）
  ⑤重复副作用（幂等键重放采样，同 operation_id 两次请求副作用次数）
  ⑥数据损坏（业务恒等式探针：合并数 = individual_sum + adjustment + elimination 等）
- 探针全部挂在 Locust `events.request` 采样后处理，随 `stage_stats.json` 输出。

## 3. R2 灰度脚本形态

`scripts/ops/pgbouncer_gradual_rollout.py`（新）：三阶段状态机
`pct=2% → 25% → 100%`，每阶段 ①切 `DB_USE_PGBOUNCER` ②观测窗口（pool wait/hold/timeout、
event-loop lag、错误率）③越门自动回退并留 `rollout_incident.json`。前置断言：契约 9 例全过 + 连接预算 `binding_constraint` 报告可行。回退 = 直接关 `DB_USE_PGBOUNCER`（单文件开关）。

## 4. R3 多 worker

- Redis adapter 注入点：`install_event_bus_state_adapter(RedisEventBusStateAdapter(...))`，
  仅在 `GT_WORKERS > 1` 时启用；单 worker 保持内存实现（上游已证行为 100% 等价）。
- 进度 / 失效状态外置补齐：进度写 `platform_jobs.progress`（已 DB 耐久，补读侧聚合）；
  失效状态（`is_stale` 标记）经 EventBus 广播，多 worker 下天然跨进程，补对账探针。
- 2/4/8 验证用例：每 worker 起独立进程消费同一 `platform_jobs` 队列，
  断言每 job 恰被执行一次（attempt 围栏）+ SSE 事件零丢失。

## 5. R4 SQL 与索引

- 差额节点 `fill_by_formula`：裁决「公式中间态」与「差额列」语义是否需要
  纯内存内核（上游 C3 登记：不能写成不存在的 `_compute_elimination`）。
- 索引落地：按 EXPLAIN 结论二选一（pg_trgm 零改表 / tsvector 需生成列），
  产出迁移 + 在线建索引窗口评估（`knowledge_documents` 2 万+ 行，
  `CREATE INDEX CONCURRENTLY`）。
- statement 计数：`_MAX_STATEMENTS_PER_RUN=20` 棘轮在真 PG 用一次性库复核。

## 6. R5 虚拟化交互契约（独立工作量的切入方式）

新模块 `frontend/src/components/grid/virtualInteractionContract.ts`：
离屏选区 / 键盘导航 / 公式格 / 批注锚点 / 无障碍标签的协议定义 +
GtVirtualTable 接入层；TB canary 用 GridKernel 事件对拍单测先行，
真实 1000/5000 行 Playwright 在容量环境一并取证。

## 7. R6 流式路由逐条迁移节奏

- 每批 10~20 条，按「响应生成器是否读 DB」分两桶：
  不读 DB → 直接 `scope="function"`；读 DB → 抽 `prepare_xxx()` 先取数再开流。
- 每批完成跑 `check_streaming_db_scope.py --check` + `--write` 收紧，
  变异：任选一条已迁移路由去掉 scope 改回请求级 ⇒ 棘轮红。

## 8. 测试与验收纪律

- 全部 PG 用例带一次性库 skipif + `audit_platform` 拒绝断言（沿用上游 188 模式）。
- 每个 R 批次留 evidence 文件（实跑 JSON / 截图 / 探针输出）。
- 迁移号共享库现算取号；写共享库前用户放行。
