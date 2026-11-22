# 平台容量验收与重任务残留缺陷收口 — 需求

来源：`platform-heavy-jobs-and-capacity-closure`（2026-11-22 交接式归档 `_archive/188`）。
原 spec 的**本机可做部分已全部交付**（durable jobs V243/R243、容量指标与压测硬闸门、
SSE 选主与配额、附注章节锁真实 PG 并发 barrier、Ledger 分阶段 profiler 含 WAL 探针、
分布式 stage_stats 逐桶合并、PgBouncer transaction 契约本机实测、知识检索真实 EXPLAIN
基准、连接预算按副本计算）；本 spec 只承接**必须专用容量环境或需独立 spec 工作量**
的余项。归档裁决：用户 2026-11-22「拆独立 spec 后交接式归档」。

## 背景与范围边界

- 共享 PG（`audit_platform`）禁止写压测与性能基线：容量环境项全部在专用可销毁库上跑
  （复用上游 0.3 已建的 `GT_LOAD_DISPOSABLE_DB_URL` / `GT_PERF_DISPOSABLE_DB` 硬闸门）。
- 上游已交付的守卫（棘轮 / 梯度契约 / 安全计数校验）**只许变严不许放宽**；
  本 spec 不重复实现、只消费。
- 迁移纪律：新迁移按共享库 `schema_version` 现算取号（2026-11-22 现扫最高 V274），
  写共享库前须用户放行。

## R1 6000 并发容量验收（承接 E5/E6 + F1③）

1. 按 `tests/load/load_contract.py` 梯度 100 → 1000 → 3000 → 6000 VU 实跑，
   6000 稳态 ≥ 30 分钟；原始 CSV / `summary.json` / `resource_samples.json` 归档提交。
2. 达成核心读 p95 ≤ 300ms、p99 ≤ 1s、核心错误率 < 0.1%；全场景错误率 < 1%。
3. 六类安全计数（越权回放 / 连接泄露 / 连接超时 / 事件丢失 / 重复副作用 / 数据损坏）
   必须为 0 —— **生产者尚未存在**，先建探针再实跑（run_final 只校验不生成，见上游 E6 登记）。
4. 分布式负载机：各 worker 的 `stage_stats.json` 经 `merge_stage_payloads` 逐桶相加后判定，
   fail-closed；任一阶段无样本强制 FAIL。

## R2 PgBouncer transaction 灰度（承接 E1 + F1④）

1. 已实证的契约（RLS fail-closed / `SET LOCAL` 不泄露 / `statement_cache_size=0` /
   取消后 rollback）作为灰度前置，不得重测绕过。
2. 建 2% → 25% → 100% 灰度脚本与回退路径；连接预算按
   `app/core/connection_budget.py` 的实测结论执行（默认池配置 4 副本硬阻塞，
   4 副本前必须先降池配置或上 PgBouncer）。
3. 灰度窗口内监控 pool wait / hold / timeout 与 event-loop lag，任一越门即停。

## R3 多 worker 扩展验证（承接 E2 + F1④）

1. 2/4/8 worker 零丢失 / 零重复验证：EventBus 状态外置注入 Redis adapter
   （`event_bus_state_redis.py` 已就绪）后实跑；进度 / 失效状态外置先补。
2. `platform_jobs` / AI 任务已 DB 耐久，跨 worker 认领经 SKIP LOCKED，
   故障注入复用上游 B6 套件在多 worker 下重跑。

## R4 SQL 与检索索引落地（承接 C2/C3/C4/C5 余项）

1. 合并附注差额节点走 `fill_by_formula` 的语义裁决 + 叶子来源整章批取；
   真实大项目（10000 公式单元 / 真实大账套）上的 rows/s、WAL、COPY 基线。
2. 知识检索按 EXPLAIN 证据把 pg_trgm / tsvector 索引落生产迁移
   （需产品裁决选型 + 在线建索引窗口评估）；`CANDIDATE_CAP` 告警阈值保持实测依据。
3. 引擎级 statement 计数棘轮在真 PG 复核（`_MAX_STATEMENTS_PER_RUN=20` 只降不升）。

## R5 前端大表虚拟化（承接 D1/D3）

1. 先补齐虚拟化表交互契约：离屏逻辑选区 / 编辑器回收 / 稳定行与列 key /
   公式 / 批注 / 无障碍（约 1000 行前端，独立工作量）。
2. 契约齐全后 TB 1000/5000 行 canary → 附注与合并表按同一套协议接入；
   任何能力回退即阻断。

## R6 流式路由 DB 作用域逐条迁移（承接 A6 余量）

1. 冻结基线 111 条候选只减不增（棘轮已建）；逐条迁移前先判
   「响应生成器是否仍读 DB」，读 DB 的不得简单改 scope。
2. 每迁 10~20 条收紧一次基线（`--write` 只在下降时允许），保持可回滚。

## R7 归档门

1. 各批次以「真库实跑证据 + 棘轮收紧」为完成判据，禁止以本机合成数据外推。
2. tasks.md 只在代码与验证真实通过后勾选；无法在本机验证的项保持
   `[ ]*` 并写明环境前提。
