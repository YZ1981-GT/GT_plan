# Technical Design

## Overview

ACNR 运行时收敛：修复公共 resolve 端点、Grammar 源、Overlay 持久化、Runtime 增量重建、Canonical Identity、分布式缓存、依赖图收敛、版本锁定、治理守卫、可观测性。聚焦运行时管道闭环，不扩展业务消费者、不新增循环底稿。

**与 `acnr` spec 关系**：acnr 定义五层模型，本 spec 修运行时管道。
**与 `acnr-consumer-wiring` 关系**：consumer-wiring 迁移消费者，本 spec 修基础设施。

---

## Architecture

### 当前架构（问题）

```
前端 useAcnr.ts ─── POST /api/acnr/resolve ───► acnr.py (router)
                                                      │
                                                      ▼
                                              catalog.resolve()  ◄── 只走 L1
                                                      ✗ 不调 full_resolve
                                                      ✗ L2/L3/非wp 全绕过
```

### 目标架构

```
前端 useAcnr.ts ─── POST /api/acnr/resolve ───► acnr.py (router)
     │(epoch cache)                                   │ auth check
     │                                                ▼
     │                                        resolver.full_resolve(
     │                                          input, project_id?, wp_id?, session
     │                                        )
     │                                    ┌──────┼──────┐
     │                                    ▼      ▼      ▼
     │                              L2 Overlay  L1 Cat  L3 Runtime
     │                              (PG-backed) (ver.)  (wp-scoped)
     │                                    └──────┼──────┘
     │                                           ▼
     │                                   CanonicalAddress
     │                                    ┌──────┼──────┐
     │                                    ▼      ▼      ▼
     │                              非wp委托 jump_route metrics
     └── SSE epoch → cache invalidation
```

---

## Components and Interfaces

### 3.1 Router 层 (`routers/acnr.py`)

- `POST /api/acnr/resolve`：调 `resolver.full_resolve` (非 `catalog.resolve`)
  - 携带 project_id → `check_project_access(user, project_id, session)`
  - 携带 wp_id → `verify_wp_binding(wp_id, project_id, sheet_code, session)`
- `GET /api/acnr/resolve-instance`：内部增项目授权 + binding 校验
- `GET /api/acnr/metrics`：聚合指标（admin/manager）

### 3.2 Grammar (`services/acnr/grammar.py`)

- 路径修正：`Path(__file__).resolve().parent.parent.parent.parent / "data/acnr/grammar_v1.json"`
- 启动校验：`_validate_grammar(data)` → 缺失则 `sys.exit(1)`

### 3.3 Auth (`services/acnr/auth.py` 新建)

- `check_project_access(user, project_id, session)` → project_assignments 或角色
- `verify_wp_binding(wp_id, project_id, sheet_code, session)` → WpIndex 全链校验

### 3.4 Overlay (`services/acnr/overlay.py` + `overlay_repository.py` 新建)

- PG 表 `acnr_project_overlay`（持久化权威）
- 内存 `_overlay_store` 改为 read-through 缓存
- invalidate 只清内存不删 PG
- 修复 ORM JOIN：`WorkingPaper.wp_index_id → WpIndex.id`

### 3.5 Runtime (`services/acnr/runtime.py`)

- `rebuild_runtime_for_wp(wp_id, parsed_data)` 增量重建
- 冷启动从 DB parsed_data 惰性重建
- L3 匹配修复：精确或 `startswith(target + "/")`，多候选 → ambiguous

### 3.6 Events (`services/acnr/events.py`)

- `invalidate(trigger, project_id, wp_id?, extra?)`
  - 有 wp_id → 仅清该 wp L3 + Overlay 缓存
  - 递增 `project_epoch` (Redis INCR)
  - Redis pub-sub `acnr:invalidate:{project_id}`

### 3.7 Canonical (`services/acnr/canonical.py` 新建)

- `CanonicalAddress(frozen dataclass)`: domain/parent/sheet/coordinate
- `from_addr_id` / `from_uri` / `from_formula_ref` / `addr_id` property
- 内部统一标识，URI/formula/index 仅边界适配

### 3.8 Cache Epoch (`services/acnr/cache_epoch.py` 新建)

- `increment_epoch(project_id)` / `get_epoch(project_id)` → Redis
- worker 订阅 `acnr:invalidate:*` → 清本地缓存

### 3.9 前端 (`useAcnr.ts`)

- module cache + `cacheEpoch` 字段
- SSE `acnr:invalidate` → 清缓存

### 3.10 图收敛

- `LinkageGraphBuilder.get_edges_for/predecessors` 单一边源
- `FormulaReverseIndex` 改为读 graph 边
- `CrossSheetResolver` async 热路径 `await full_resolve_async`

### 3.11 版本快照

- Generator 归档 `data/acnr/catalog_snapshots/{version}.json`
- `load_versioned_catalog(version)` + LRU (5)
- full_resolve 版本不同 → 加载快照

### 3.12 Metrics (`services/acnr/metrics.py` 新建)

- 结构化指标：domain/layer_hit/result/latency_ms
- `GET /api/acnr/metrics` 端点

---

## Data Models

### acnr_project_overlay 表（新建）

```sql
CREATE TABLE IF NOT EXISTS acnr_project_overlay (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id),
  wp_id UUID REFERENCES working_paper(id),
  parent_wp_code VARCHAR(20) NOT NULL,
  sheet_code VARCHAR(40) NOT NULL,
  overlay_type VARCHAR(20) NOT NULL,  -- 'alias' | 'cust' | 'binding'
  payload JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_overlay_project ON acnr_project_overlay(project_id);
```

### CanonicalAddress 值对象

```python
@dataclass(frozen=True)
class CanonicalAddress:
    domain: str        # 'wp' | 'tb' | 'report' | 'note' | 'aux'
    parent: str        # wp_code / account_code / report_code / note_code / aux_type
    sheet: str         # sheet_code / ''
    coordinate: str    # cell_address / semantic_slug / ''
    
    @property
    def addr_id(self) -> str: ...
    
    @classmethod
    def from_addr_id(cls, s: str) -> 'CanonicalAddress': ...
```

### Redis Keys

- `acnr:epoch:{project_id}` → int（单调递增）
- `acnr:invalidate:{project_id}` → pub-sub channel

---

## Correctness Properties

### Property 1: 公共 API resolve == full_resolve 直调
PBT 两路径一致 [Req-1]

### Property 2: 四语法殊途同归
PBT 等价四语法 → 同一 CanonicalAddress [Req-1, Req-6]

### Property 3: 项目隔离
PBT 交叉 project → 403 [Req-3]

### Property 4: wp_id binding 三元组匹配
集成测试 不匹配 → 403 [Req-3]

### Property 5: Overlay 保存/失效后可恢复
PBT write→invalidate→read roundtrip [Req-4]

### Property 6: Runtime 保存后立即可解析
集成 save→resolve→found [Req-5]

### Property 7: 增量失效不影响无关 wp
PBT 两wp各注册→invalidate A→B仍可resolve [Req-5]

### Property 8: epoch 单调递增
PBT 并发 INCR [Req-7]

### Property 9: CanonicalAddress round-trip
PBT from_addr_id(ca.addr_id)==ca [Req-6]

### Property 10: 反向索引 == graph 反向投影
PBT dependents==predecessors [Req-8]

### Property 11: 锁定版本确定性
PBT 同input+同version→幂等 [Req-9]

### Property 12: legacy consumer drift 被阻断
集成 新增消费者→exit 1 [Req-11]

### Property 13: gap_count == 明细计数之和
单元测试 [Req-10]

### Property 14: 降级路径可观测
集成 fallback→metrics有条目 [Req-12]

---

## Error Handling

- Grammar 加载失败 → lifespan `sys.exit(1)`（启动阻断）
- 项目授权失败 → 403 Forbidden（不泄露元数据）
- Overlay ORM 写入失败 → 500 + 主动告警 + 内存缓存保持旧值
- Runtime rebuild 异常 → 记录 error metric + 保留旧 L3（不清除）
- 版本快照缺失 → `VersionNotFoundError` 返回客户端 + 告警
- Redis 不可用 → 本地缓存降级（epoch=0，每次请求重建）+ 记录 fallback

---

## Testing Strategy

- **PBT**：P1–P11 使用 Hypothesis `@settings(max_examples=5, deadline=None)`
- **集成测试**：P4/P6/P12/P14 使用真实 PG + async session
- **CI 守卫**：check_acnr_catalog_drift + check_acnr_consumer_coverage 挂 governance-checks.yml
- **Playwright**：公式选址器搜索 + GtIndexChip 跳转 + 项目隔离 403
- **回归**：Task 15 运行全部 `tests/acnr/` 确保零回归

---

## Phase 2: 生产稳健性增强（增量修订）

### 3.13 Overlay Single-Flight (`services/acnr/overlay.py` 扩展)

- `_flight_locks: dict[str, asyncio.Lock]` — per-project 锁
- `get_overlay_cached(project_id, session)` 包裹 single-flight 逻辑：
  - cache hit → 直接返回
  - cache miss → acquire lock → 二次检查 cache → miss 则 DB 查询 → 写缓存 → release lock
  - DB 异常 → release lock + raise（不死锁）
- 不同 project 互不阻塞

### 3.14 Redis Pub-Sub 订阅重连 (`services/acnr/cache_epoch.py` 扩展)

- `start_epoch_subscriber()` → lifespan 启动时调用
- 订阅 `acnr:invalidate:*` 通道
- 连接断开 → 指数退避重连（5s/10s/20s/30s max）
- 重连成功 → 清除全部本地缓存
- 轮询兜底：每 60s `_epoch_poll_task()` 对比本地 vs Redis epoch → 不一致清缓存
- Redis 完全不可用 → epoch=0 降级 + fallback metric

### 3.15 前端 TTL + 批量 Resolve

**前端 `useAcnr.ts`：**
- `CacheEntry { data, timestamp }` → `Date.now() - timestamp > MAX_AGE` 时过期
- `batchResolve(inputs[])` → `POST /api/acnr/resolve-batch` → 返回等长结果数组
- SSE 仍优先清缓存，TTL 仅为兜底

**后端 `routers/acnr.py`：**
- `POST /api/acnr/resolve-batch` 端点
- 接受 `{items: [...], project_id?}` → 内部循环调 `full_resolve` + 项目授权复用
- 限制 `items.length ≤ 50`（防滥用）

### 3.16 Catalog 快照生命周期 (`services/acnr/catalog_snapshot_gc.py` 新建)

- `cleanup_stale_snapshots(keep_recent=10)`:
  - 列 `data/acnr/catalog_snapshots/` 全部版本
  - 查 PG `SELECT DISTINCT registry_version FROM projects WHERE registry_version IS NOT NULL`
  - 保留最近 10 + 被引用版本 → 其余删除
- CI 守卫 `check_acnr_snapshot_count.py`：总数 ≤ keep_recent + referenced_count

### 3.17 resolve_instance 请求级缓存 (`services/acnr/resolver.py` 扩展)

- `_RequestScopedInstanceCache` context var（或函数参数传递 memo dict）
- `_attach_wp_id` 调用前先查 memo → 命中则跳过 DB
- batch resolve 端点创建 memo → 传入各次 full_resolve → 自动复用
- disambiguation 结果不缓存（每次重新查询）

### 3.18 前端 SSE 自动重建 (`useAcnr.ts` _connectSSE 扩展)

- `onerror` 时不仅关闭旧连接，还启动重建定时器
- 指数退避 5s/10s/20s/30s max，最多重试 5 次
- 重建成功 → `invalidateModuleCache()` 立即执行
- 超过 5 次 → 降级为 TTL-only（停止重试）

### 3.19 L3 模糊搜索收紧 (`services/acnr/resolver.py` Step 6 修复)

- 删除 `resolved_addr_id.startswith(rt_entry.wp_code)` 宽松条件
- 保留：精确 addr_id / cell_address 精确 / endswith("/" + cell_address)
- 多候选 → ambiguous（与 L1 行为对齐）

### 3.20 前端 resolve 结果 LRU 缓存 (`useAcnr.ts` 扩展)

- `_resolveCache = new Map<string, {result, timestamp}>()`
- key = `resolve:${JSON.stringify(params)}`
- LRU 最大 200 条（超出删除最旧）
- epoch 变 → 清空 resolveCache（与 sheets/cells 同步）
- found=false 不缓存

---

## Phase 2 Correctness Properties

### Property 15: Single-flight 不重复查询
**Validates: Req-13**
PBT 10 并发同 project → DB 仅调 1 次

### Property 16: Pub-sub 断连后 epoch 轮询修复
**Validates: Req-14**
集成测试：断开 → 远程 incr → 60s 内本地缓存被清

### Property 17: 前端 TTL 过期后重新请求
**Validates: Req-15**
vitest：写入 cache → sleep 300s(mock) → 下次 resolve 走网络

### Property 18: 快照 GC 不删被引用版本
**Validates: Req-16**
PBT 随机版本集 + 随机引用集 → 被引用版本永不删除

### Property 19: resolve_instance 请求内去重
**Validates: Req-17**
集成测试：batch 10 个同 sheet 输入 → DB resolve_instance 仅调 1 次

### Property 20: SSE 断连自动重建
**Validates: Req-18**
vitest：mock onerror → 5s 后新 EventSource 建立 + invalidateModuleCache 被调

### Property 21: L3 模糊搜索不跨 wp 错格
**Validates: Req-19**
PBT：wp_code="D2" 注册 cell → resolved_addr_id="D2-2/xxx" 不命中 D2 的 L3 条目

### Property 22: 非 wp 域 resolve 缓存命中率
**Validates: Req-20**
vitest：连续 2 次 resolveFormula 同输入 → 第 2 次不触发 HTTP
