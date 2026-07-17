# Task 13 — persistent epoch 缓存 / measurement-mode 限流 / 性能观测

Feature: procedure-delegation-visibility-isolation
Component: C15 (Cache/Rate/Perf)
Migration head: V113 (V113 已建 wp_visibility_policy_epoch / wp_visibility_invalidation_outbox，Task 2)

## 实现文件

- `backend/app/services/wp_visibility/epoch_cache.py` — PersistentEpochCache（缓存 key = user+project+wp_index+持久 epoch；outbox→Redis 即时淘汰快路径 `invalidate()`；≤1s DB epoch 核对安全网 `current_epoch()`；epoch 不可得 → EpochUnavailable → fail-closed authoritative 现取，绝不 stale-allow）。
- `backend/app/services/wp_visibility/rate_limit_profile.py` — PerformanceProfile / CapacityReport / RateLimitProfile / MeasurementModeRateLimiter / freeze_rate_limit_profile。measurement mode 默认 inert（只观测、绝不限流、绝无预设阈值 / 无固定 10 RPS）；profile 必须引用容量报告 content hash 且 frozen=True 才 `is_active`（Property 19 激活门）。
- `backend/app/services/wp_visibility/perf_metrics.py` — VisibilityMetrics（gate/list latency p95、query count、cache hit/miss/stale-deny、拒绝 reason 分布、error_allow 越权放行数[验收恒 0]）。
- gate seam：`wp_bound_gate.py` 默认注入 `get_default_rate_limiter()`（measurement-mode）并接受 `epoch_cache=` 注入；资源无关限流在 Binding_Minimum 解析前执行（Req 14.18）。

## prompt↔design 属性编号映射

| prompt 提及 | design 权威编号 | 内容 | 覆盖 criteria |
|---|---|---|---|
| "property 16 (profile activation)" | **P19** (Rate profiles require measured capacity evidence) | profile 必须由容量报告+hash 生成并冻结才激活 | 14.1–14.12, 14.16, 14.17, 14.18 |
| epoch 缓存 / 撤权收敛 / 禁 stale allow | **P18** (Revocation converges within 1s without stale allow) | ≤1s 收敛 + fail-closed | 14.13, 14.14, 14.15, 14.21 |
| 资源无关 429 | **P11** (Rate limiting and resource denial do not reveal existence) | 429 解析前、404 统一 | 14.18, 14.19 |
| epoch 原子递增 | **P17** (Permission changes + persistent invalidation commit atomically) | 同事务 epoch/outbox（Task 2/7 已建） | 14.20 |

注：design 的 `Requirements Traceability` 将 Req14 映射到 P11/P17/P18/P19。design 中的 **P16** 实为"HTTP/非 HTTP 入口清单 = coverage ledger"（Req13，非 profile activation）。prompt 所指"profile activation"对应 design 的 **P19**。

## measurement mode 与阈值冻结（本任务边界）

- 本任务只建 schema + 机制 + measurement + 指标；**不预设任何业务阈值，不出现固定 10 RPS**。
- `measurement_only_profile()` 三维阈值皆空、frozen=False、capacity_report_hash=None → 永不限流。
- `MeasurementModeRateLimiter.check()` inert 时恒放行但记录观测（`observation_snapshot()`），供 Task 17 反推阈值。
- `freeze_rate_limit_profile()` 强约束：容量报告版本须匹配 Performance_Profile、至少一维阈值且全为正数、携带 `CapacityReport.content_hash()`、frozen=True，否则抛 `RateLimitProfileError`。

## DEFERRED → Task 17（明确非本任务完成项）

- 真实 Rate_Limit_Profile 阈值冻结（依据 6000 并发容量报告生成 frozen profile）。
- 6000 并发容量验收：list p95≤2s、gate p95≤1s、成功错误率≤1%、错误允许数=0、超阈 429+Retry-After、阈内不误限、资源存在性不可推断。
- Evidence_Manifest 记录 Performance_Profile 版本 / Rate_Limit_Profile 版本 / 配置摘要 / 测量结果（Req 14.17）由 Task 17 产出。

本任务已用**合成容量报告**（CapacityReport 测试夹具）验证 P19 激活门机制可用（`test_frozen_profile_activates_and_references_capacity_hash` 等），真实阈值与容量验收留 Task 17。

## 测试结果

命令：`python -m pytest tests/procedure_delegation_visibility/test_task13_epoch_cache_rate_profile.py`
环境：PostgreSQL `audit_platform`（持久 policy epoch 读自 wp_visibility_policy_epoch，非 sqlite/mock），事务隔离回滚。
结果：**21 passed**（Property 18 缓存机制单元 4 + invalidation channel 1 + Property 18 经 gate 端到端 2 + Property 19 profile 8 + Property 19 资源无关 429 经 gate 2 + 观测机制 4）。
