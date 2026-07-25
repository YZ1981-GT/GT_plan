# Design Document

## Overview

本设计以 additive strangler 路径加固 ACNR 三条架构级缺口：SSE 实时失效、Overlay 持久化并发治理、失效跨 worker durable 化。核心原则：

- **双层失效**：SSE = best-effort 实时（连接所在 worker）；Durable_Epoch + 轮询 + TTL = 最终一致兜底。两层独立，任一失效不导致陈旧 allow。
- **Cache_After_Commit**：Overlay 写路径**清缓存**而非写缓存，read-through 从已提交 PG 重载，从根本消除未提交脏缓存。
- **约束层兜底 + 应用层原子**：唯一约束 + `ON CONFLICT` 原子 upsert 双保险。
- **Fail_Closed**：Redis/SSE/DB 任一降级都退到更保守路径，不静默保留陈旧值。
- **零回归**：不改既有公共 API 形状；新增参数带默认值；已修 P0 与既有能力经回归测试守护。

## Architecture

### 失效传播全景（目标态）

```
业务变更
 ├─ 底稿保存 → WORKPAPER_SAVED(post-commit) → acnr.events.invalidate(project_id)
 │      ├─ [即时] L3/L2/reverse_index/legacy 本地清缓存（既有）
 │      ├─ [即时] event_bus.broadcast_raw("acnr:invalidate",{project_id,...})  ← 新增(R2)
 │      │        └─→ 同 worker 的 /events/stream SSE 队列 → 前端实时清项目缓存(R1/R4)
 │      └─ [durable] increment_epoch(project_id) 写 DB Durable_Epoch + Redis fan-out  ← 升级(R11)
 │               └─→ 其他 worker: pub-sub 即时 / 60s 轮询对比 DB epoch 兜底
 │
 └─ Overlay 变更(受控入口 R10) ──同一事务──┐
        ├─ Atomic_Upsert(ON CONFLICT) 写 acnr_project_overlay(R5/R6/R7/R8)
        ├─ 写 acnr_invalidation_outbox 一行(R11.2, 同事务)
        └─ commit 后 clear_project_overlays(project_id)(R9)
                 Invalidation_Dispatcher 轮询 outbox 未投递行:
                   → increment Durable_Epoch → broadcast_raw + Redis pub-sub → mark dispatched(R11.3, 至少一次)
```

### 决策 1：SSE 双层而非替代 TTL

前端 SSE 是 best-effort 实时层，**不替代** TTL_Fallback / Durable_Epoch。理由：`broadcast_raw` 只推**当前 worker 内存 SSE 队列**，多 worker 部署下连接在 worker B 的客户端收不到 worker A 的 `broadcast_raw`；跨 worker 的权威机制是 Durable_Epoch（后端 worker 清本地缓存）+ 前端 `/events/since` 重连补拉 + TTL。故 SSE 修复目标是「实时性提升」而非「唯一可靠通道」，与既有 3 层（SSE/epoch/TTL）分工一致。

### 决策 2：前端全局缓存 vs 项目级 SSE 的失效粒度

`useAcnr` 的 Catalog_Cache（sheets/cells）是 L1 静态、项目无关；Resolve_Cache 的 key 含 `project_id`。故：

- 项目 P 的 `acnr:invalidate`（无版本变化）→ 只清 Resolve_Cache 中 key 含 P 的条目（R4.1/4.3），不动全局 Catalog_Cache（避免一个项目保存拖累全局目录缓存）。
- 携带 `catalog_version` 变化 → 说明 L1 目录本身变了（catalog 重生成）→ 清全局 Catalog_Cache + 递增 `_cacheEpoch`（R4.2）。

Resolve_Cache key 格式已为 `resolve:${JSON.stringify({... project_id})}`，可用「key 字符串含该 project_id」子串匹配清除（project_id 是 UUID，误伤概率可忽略；实现用解析后精确比对更稳）。

### 决策 3：项目级 SSE 订阅入口

`useAcnr` 当前 `_connectSSE()` 是无项目上下文的全局单例，且连错端点。改为：

- 新增 `subscribeInvalidation(projectId: string)`：按 projectId 引用计数复用连接，返回 cleanup（R1.4/1.5）。
- `useAcnr()` 不再无条件建全局 SSE；由**有项目上下文的消费者**（GtIndexChip / 公式选址器 / 高级查询等在项目页内）显式调用 `subscribeInvalidation(currentProjectId)`，或 `useAcnr(projectId?)` 传入可选项目 → 内部订阅。无 projectId → 不建连接（R1.3）。
- 连接 URL：`/api/projects/${projectId}/events/stream?token=${token}`，token 取自 auth store（对齐 `useChainExecution.ts`）。

### 决策 4：SSE 端点 token 鉴权

`EventSource` 无法设置 Authorization 头。设计前置**核实点**：确认后端 `get_current_user`（`app/deps.py`）是否已支持从 query `?token=` 读取 JWT（`useChainExecution` 既有 `?token=` 用法暗示某些 SSE 端点支持）。

- IF `get_current_user` 已支持 query token → `/events/stream` 无需改鉴权来源，仅加 `check_project_access`（R3）。
- IF 不支持 → 为 SSE 端点新增 `get_current_user_sse` 依赖（优先 header，回退 query `token`），仅用于 `text/event-stream` 端点，不改全局鉴权。此为 Task 明确验证/实现项，不臆测。

### 决策 5：Overlay 写路径 clear 而非 set

当前 `write_overlay` 在 `flush`（非 commit）后 `set_overlay_in_cache`，外层回滚 → 缓存脏（R9 缺口）。改为写 PG 后 **`clear_project_overlays(project_id)`**：下次读经 `ensure_cache_loaded`/`get_overlay_cached`（single-flight read-through）从已提交 PG 重载。回滚后 PG 无新行，重载得旧状态，天然满足 R9.1~9.4。不引入 after_commit hook（避免与既有 flush-only 服务约定冲突）。

### 决策 6：Durable_Epoch DB-first + Outbox 边界（诚实说明）

- **Durable_Epoch**：`increment_epoch(project_id, session=None)` 升级为 **DB 权威**：`INSERT INTO acnr_invalidation_epoch(project_id,epoch) VALUES(:p,1) ON CONFLICT(project_id) DO UPDATE SET epoch=epoch+1, updated_at=now() RETURNING epoch`（单语句原子单调）；成功后 best-effort Redis publish。Redis 不可用 → DB epoch 仍递增（消除当前返回 0 丢失失效）。`_epoch_poll_task` 对比 **DB** epoch（而非仅 Redis）修复本地缓存（R11.4）。
- **Invalidation_Outbox（真·至少一次，事务性）**：仅在**持有业务事务/session** 的路径可用 —— 即 Overlay 受控变更入口（R10）。overlay 写与 outbox 行同事务提交，Dispatcher 保证至少一次投递。
- **底稿保存路径的诚实边界**：`acnr.events.invalidate` 由 `WORKPAPER_SAVED`（post-commit）触发，此处已无原业务事务，故走 **DB-durable-epoch（post-commit best-effort）**，而非 outbox。残余风险：save-commit 与 epoch-bump 之间进程崩溃 → 丢失一次 epoch bump，由 60s 轮询/TTL 最终修复。此为**记录在案的可接受残余**，不谎称底稿保存路径拥有事务性至少一次。

### 涉及文件

| 层 | 文件 | 改动 |
|----|------|------|
| 前端 SSE | `useAcnr.ts` | 项目级 `subscribeInvalidation` 替换全局 `_createSSEConnection`；正确 URL + `?token=`；`acnr:invalidate` 精细失效(R1/R4) |
| 后端广播 | `acnr/events.py::invalidate` | 增 `broadcast_raw("acnr:invalidate",{project_id,...})`(R2) |
| SSE 授权 | `routers/events.py::sse_stream` | 流式前 `check_project_access`(R3)；必要时 SSE token 依赖(决策4) |
| 鉴权 | `deps.py` | 核实/新增 SSE query-token 依赖(决策4，条件性) |
| Overlay 模型 | `acnr_overlay_model.py` | 增 `reason/owner/expires_at/revision` 列 + `UniqueConstraint`(R5/R7/R8) |
| Overlay 仓库 | `overlay_repository.py` | `upsert_overlay` 改 ON CONFLICT 原子 + revision/CAS + 治理字段(R6/R7/R8) |
| Overlay 服务 | `overlay.py` | `load_*` 读回治理字段；`write_overlay` clear 而非 set；新增受控 `apply_project_overlay`/`remove_project_overlay` 服务入口(R7/R9/R10) |
| 失效 durable | `cache_epoch.py` | `increment_epoch` DB-first；poll 对比 DB epoch；启动兜底任务始终建(R11) |
| Outbox | 新建 `acnr/invalidation_outbox.py` + dispatcher | outbox 写入 + Invalidation_Dispatcher(R11) |
| 模型 | 新建 `acnr_invalidation_model.py` | `AcnrInvalidationEpoch` / `AcnrInvalidationOutbox` ORM |
| 迁移 | 新建 `migrations/V1xx__acnr_invalidation_overlay_hardening.sql` + rollback | 唯一约束+去重+治理列+revision+epoch表+outbox表(R5/R7/R8/R11/R13) |

## Data Models

### acnr_project_overlay（ALTER，additive）

```sql
ALTER TABLE acnr_project_overlay ADD COLUMN IF NOT EXISTS reason      TEXT;
ALTER TABLE acnr_project_overlay ADD COLUMN IF NOT EXISTS owner       VARCHAR(100);
ALTER TABLE acnr_project_overlay ADD COLUMN IF NOT EXISTS expires_at  DATE;
ALTER TABLE acnr_project_overlay ADD COLUMN IF NOT EXISTS revision    INTEGER NOT NULL DEFAULT 1;
-- 建唯一约束前先去重（保留最新 updated_at）
-- 然后：
ALTER TABLE acnr_project_overlay
  ADD CONSTRAINT uq_overlay_identity
  UNIQUE (project_id, parent_wp_code, sheet_code, overlay_type);
```

ORM `AcnrProjectOverlay` 同步新增 4 列 + `UniqueConstraint("project_id","parent_wp_code","sheet_code","overlay_type", name="uq_overlay_identity")`。

### acnr_invalidation_epoch（新建）

```sql
CREATE TABLE IF NOT EXISTS acnr_invalidation_epoch (
    project_id UUID PRIMARY KEY,
    epoch      BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### acnr_invalidation_outbox（新建）

```sql
CREATE TABLE IF NOT EXISTS acnr_invalidation_outbox (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID NOT NULL,
    wp_id        UUID,
    domain       VARCHAR(20),          -- wp/tb/report/note/aux/overlay
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    dispatched_at TIMESTAMPTZ,          -- NULL = 未投递
    attempts     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_inval_outbox_undispatched
  ON acnr_invalidation_outbox (created_at) WHERE dispatched_at IS NULL;
```

Dispatcher 用 `SELECT ... WHERE dispatched_at IS NULL ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT N` 拉批，投递后 `UPDATE dispatched_at=now()`；失败 `attempts=attempts+1` 不标 dispatched（至少一次，R11.6）。

### OverlayPatch（内存，扩字段来源）

`load_project_overlays_from_pg` 读回 `reason/owner/expires_at/revision` 填充 `OverlayPatch`（现只填 overrides/type/wp_id），使 `is_expired()` 重启后正确。

### ACNR_Invalidate_Event（SSE payload）

```json
{ "project_id": "<uuid>", "wp_id": "<uuid|null>", "epoch": 42, "catalog_version": "2026..." }
```

## Components and Interfaces

### 后端

- **`acnr/events.py::invalidate(project_id, *, wp_id?, addr_id?, trigger?, extra_sheets?)`**：既有失效链末尾新增 `event_bus.broadcast_raw("acnr:invalidate", {project_id, wp_id?, epoch?, catalog_version?})`（R2）。签名不变（新增内部广播，不改参数）。
- **`routers/events.py::sse_stream(project_id, year, current_user)`**：流式前 `await check_project_access(current_user, project_id, db)`（R3）；按决策 4 接入 SSE token 鉴权依赖。
- **`cache_epoch.increment_epoch(project_id, session: AsyncSession | None = None) -> int`**：DB-first 单调递增（`ON CONFLICT DO UPDATE epoch=epoch+1 RETURNING`）+ best-effort Redis publish；返回 DB epoch（R11.4）。新增可选 `session`（默认 None 时开短事务），向后兼容。
- **`acnr/invalidation_outbox.py`（新建）**：`async enqueue(session, project_id, *, wp_id=None, domain=None)` 同事务写 outbox 行；`InvalidationDispatcher.run_once(session)` / `start()/stop()`（lifespan 接管，`FOR UPDATE SKIP LOCKED` 拉批 → increment epoch + broadcast_raw + Redis publish → mark dispatched；失败 attempts++）。
- **`overlay_repository.upsert_overlay(session, *, project_id, wp_id, parent_wp_code, sheet_code, overlay_type, payload, reason=None, owner=None, expires_at=None, expected_revision: int | None = None) -> AcnrProjectOverlay`**：`ON CONFLICT (uq_overlay_identity) DO UPDATE ... revision=revision+1`；`expected_revision` 不匹配抛 `OverlayRevisionConflict`（R6/R8）。新增参数均带默认，向后兼容。
- **`overlay.write_overlay(...)`**：写 PG 后 `clear_project_overlays(project_id)`（替代 `set_overlay_in_cache`，R9）。
- **`overlay.apply_project_overlay(db, project_id, addr_id, overrides, *, wp_id=None, reason='', owner='', expires_at=None, overlay_type='cust', expected_revision=None, actor)` / `remove_project_overlay(...)`（新建受控入口）**：`validate_ownership` + capability 校验 + 同事务 `invalidation_outbox.enqueue`（R10）。
- **`acnr_invalidation_model.py`（新建）**：`AcnrInvalidationEpoch` / `AcnrInvalidationOutbox` ORM。
- **`OverlayRevisionConflict`（新建异常）**：CAS 冲突可识别错误。

### 前端 `useAcnr`

- **`subscribeInvalidation(projectId: string): () => void`（新建）**：按 projectId 引用计数连 `/api/projects/${projectId}/events/stream?token=${token}`；返回 cleanup（R1）。替换全局 `_createSSEConnection`。
- **`useAcnr(projectId?: string)`**：可选传入项目 → 内部 `subscribeInvalidation`；无则不建连接（R1.3）。
- **`_onAcnrInvalidate(payload)`（新建内部）**：清 Resolve_Cache 中含该 project_id 条目；`catalog_version` 变则清 Catalog_Cache + `_cacheEpoch++`（R4.1~4.3）。
- 保留：`_resolveCacheGet` TTL（已修）、退避重连、`onopen` 清缓存、`invalidateModuleCache`、`isSSEDegraded`（R4/R13.5）。

## Correctness Properties

### Property 1: Overlay 唯一性

Overlay_Unique_Key 下任意并发 upsert 序列后至多一行。

**Validates: Requirements 5.1, 6.1, 6.2**

### Property 2: 原子 upsert 无重复

Atomic_Upsert 并发不产生重复且不抛未处理异常，UPDATE 分支 revision 递增。

**Validates: Requirements 6.2, 8.4**

### Property 3: Cache_After_Commit

write→（模拟回滚）后缓存不含未提交状态；write→commit 后读得新值。

**Validates: Requirements 9.1, 9.2, 9.3, 9.4**

### Property 4: 治理字段持久化

任意 expires_at（过去/未来/空）重启重载后 is_expired() 与持久值一致。

**Validates: Requirements 7.2, 7.3, 7.4**

### Property 5: CAS 安全

expected_revision 不匹配 → 写恒被拒且 DB 不变；不提供则向后兼容 upsert。

**Validates: Requirements 8.2, 8.3, 8.4**

### Property 6: 失效广播不变量

invalidate() 恒调用 broadcast_raw("acnr:invalidate")，project_id 为空则不广播，异常不阻断主流程。

**Validates: Requirements 2.1, 2.4, 2.5**

### Property 7: SSE 项目授权

无项目授权连 /events/stream → 403 且不建流；admin/partner 放行；既有事件消费不回归。

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 8: 前端失效项目隔离

前端收 project P 事件 → 只清含 P 的 Resolve_Cache；catalog_version 变则清全局 Catalog_Cache。

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 9: SSE 降级不返回陈旧

SSE 断连按退避重连≤5 次后 TTL-only；降级期缓存仍受 MAX_AGE 约束不返回陈旧值。

**Validates: Requirements 4.4, 4.5, 4.6, 12.2**

### Property 10: Durable_Epoch 抗 Redis 故障

Redis 不可用时 increment_epoch 仍在 DB 单调递增；poll 对比 DB 修复缓存。

**Validates: Requirements 11.4, 12.1**

### Property 11: Outbox 至少一次 + 单调

每条 outbox 行至少投递一次（投递失败不标 dispatched，重试）；Durable_Epoch 单调递增。

**Validates: Requirements 11.3, 11.6**

### Property 12: 受控入口安全

overlay 变更入口执行 validate_ownership + capability，未授权拒绝，同事务写 outbox。

**Validates: Requirements 10.1, 10.2, 10.3**

### Property 13: 迁移幂等

迁移空库/历史库/中断重跑幂等；ORM drift=0；含唯一约束前去重。

**Validates: Requirements 13.1, 13.2, 5.2**

### Property 14: 零回归

已修 P0（TTL / GC fail-closed / explicit_wp_id / invalid_addr_id / version-lock 文案）+ 既有能力（single-flight / ownership / binding / L3 收紧）不回归。

**Validates: Requirements 13.3, 13.4, 13.5**

## Error Handling

- **broadcast_raw 异常**（无队列/序列化失败）→ try/except warning，不阻断 `invalidate()`（R2.5）。
- **SSE 授权失败** → 403 HTTPException，脱敏（R3.2/R12.4）。
- **前端 SSE 连接失败** → 既有 `onerror` 退避重连 → 超限 TTL-only 降级（R4.4/R12.2）。
- **Atomic_Upsert 冲突/CAS 失败** → 抛可识别 `OverlayRevisionConflict`（区别于 ownership/DB 错误），调用方按需重试或提示（R8.2）。
- **Redis 不可用** → `increment_epoch` DB 递增成功即算成功，Redis publish 失败仅 warning + fallback metric（既有 `_record_fallback_metric`）（R11.4/R12.1）。
- **Outbox dispatch 失败** → `attempts++`，不标 dispatched，下轮重试；连续失败超阈值告警（R11.6）。
- **迁移去重冲突** → 去重步骤在建约束前执行，保留最新 `updated_at`；若去重逻辑异常，迁移整体回滚（幂等重跑）（R5.2/R13.2）。

## Testing Strategy

- **PBT（fast profile, max_examples=5）**：P1~P14 各一组，PG16 真实约束/并发/`ON CONFLICT`/`FOR UPDATE SKIP LOCKED` 必须真实 PG 验证（SQLite 不替代唯一约束/并发/CAS）。
- **单元**：前端 `useAcnr` SSE 失效语义（vitest，mock EventSource + 事件注入）；`increment_epoch` DB-first 降级；`upsert_overlay` ON CONFLICT。
- **集成**：Overlay 受控入口 round-trip（写→重启重载→治理字段/is_expired）；Outbox→Dispatcher→epoch 递增。
- **回归**：既有 `tests/acnr/` 全套（除预存在 `service_identities` FK 污染 3 项与 import-path 3 项）+ 已修 P0 相关测试。
- **Playwright**（UI 相关，若接入项目级 SSE 订阅点）：项目页内底稿保存 → 前端实时收 `acnr:invalidate` → resolve 缓存刷新（0 console error）。若本规格不接 UI 订阅点则以 vitest + 端点契约覆盖，明确标注不假绿。

## Migration & Rollout (M0–M3)

- **M0**：迁移 additive（列/表/唯一约束，含去重前置）+ rollback；ORM 同步；drift=0。
- **M1**：后端 durable epoch + outbox + dispatcher + broadcast_raw；SSE 授权。默认行为兼容（无 outbox 消费者时 epoch DB-first 已生效）。
- **M2**：Overlay 受控入口 + clear-cache 写路径 + 治理字段持久化。
- **M3**：前端项目级 SSE 订阅替换全局单例；消费者接订阅点。
- 回滚不删 overlay 数据/epoch/outbox 表；前端可关订阅点退回 TTL-only。
