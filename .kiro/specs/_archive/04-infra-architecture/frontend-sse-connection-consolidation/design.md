# Design: 前端项目事件流连接去重（Project_Event_Stream_Bus）

## Overview

以 `requirements.md` 为唯一基线。引入单例 `projectEventStream` 模块，每 projectId 维持一条 `createSSE` Shared_Connection，按 Event_Name fan-out 给订阅者；`ThreeColumnLayout` / `useAcnr` / `ConsolidationIndex` / `LineagePanel` 从各自 `createSSE`/`EventSource` 迁移为向总线订阅。additive strangler：先建总线并存，逐消费者迁移，每步行为等价、可独立回退。不改后端、不改各消费者业务逻辑与既有兜底。

## Architecture

单例 `services/sse/projectEventStream.ts` 拥有「每 projectId 一条 `createSSE` Shared_Connection」，按 Event_Name fan-out 给订阅者。消费者（ThreeColumnLayout / useAcnr / ConsolidationIndex / LineagePanel）不再各自建连接，改为 `subscribeProjectEvent(projectId, eventName, handler, hooks)`。断线重连/退避委托 `createSSE`（单一真源）；总线做 Ref_Count_Lifecycle + fan-out + 重连/降级 hook。下列决策逐条展开。

### 决策 1：新建单例总线 vs 复用 ThreeColumnLayout 全局连接

`ThreeColumnLayout` 已有一条全局 `createSSE`（按 `route.params.projectId` 切换），但它 hard-coded 只转发 `data.event_type` 事件到 mitt `eventBus`（`sse:sync-event`/`sse:sync-failed`），**丢弃裸事件**（Req2.3 根因）。

**决策**：抽独立单例模块 `services/sse/projectEventStream.ts`（非把逻辑塞进 ThreeColumnLayout），因为：①useAcnr / ConsolidationIndex 是 composable/view 级消费者，不应依赖布局组件生命周期；②总线需 Ref_Count_Lifecycle（Req1.2/1.3），布局组件的单实例生命周期无法表达多消费者引用计数；③ThreeColumnLayout 自身降级为总线的一个订阅者（订阅 `sync.*` 转发到 mitt，保持 `sse:*` 事件契约不变，Req5.4）。总线拥有连接，ThreeColumnLayout 的 `route.projectId` watch 改为「订阅/退订」而非「connect/close」。

### 决策 2：分发键 = Event_Name（不依赖 data.event_type）

createSSE 的 `onMessage(data, event)` 第二参即 SSE `event:` 行值。总线按 `event`（Event_Name）分发，彻底绕开「无 event_type 被丢弃」缺陷（Req2.3）。对 `Typed_Sync_Event`（`sync.failed`/其他 `sync.*`），ThreeColumnLayout 订阅这些 Event_Name 后在其 handler 内维持原 `data.event_type` 分支逻辑（等价，Req5.4）。总线不解释负载语义，只按名 fan-out。

### 决策 3：订阅 API 形状

```ts
// services/sse/projectEventStream.ts
export interface ProjectEventSubscription { close(): void }
export function subscribeProjectEvent(
  projectId: string,
  eventName: string,
  handler: (data: unknown, eventName: string) => void,
  options?: { onReconnect?: () => void; onDegraded?: () => void },
): ProjectEventSubscription
```

- `projectId` 空 → no-op 订阅（Req1.5），`close()` 安全幂等。
- 同 projectId 多次 `subscribeProjectEvent`（任意 Event_Name）共享一条 Shared_Connection，Ref_Count = 订阅总数。
- `onReconnect` = Reconnect_Recovery_Hook（Req4.2）；`onDegraded` = Degrade_Fallback 通知（Req4.3）。
- `close()` 移除该监听器并 refCount--，降为 0 关闭 Shared_Connection（Req1.3）。

### 决策 4：连接生命周期与 createSSE 委托

总线内部结构：
```ts
interface _ProjectStream {
  conn: SSEConnection | null
  listeners: Map<string /*eventName*/, Set<Handler>>
  reconnectHooks: Set<() => void>
  degradedHooks: Set<() => void>
  refCount: number
  errorCount: number
  everConnected: boolean
  degraded: boolean
}
const _byProject = new Map<string, _ProjectStream>()
```
- 断线重连/退避 = `createSSE` 内部（Req4.1，单一真源，与 #1 一致）。总线 `conn.onError` 累计 `errorCount`，超 `MAX_RECONNECT_ATTEMPTS(5)` → `degraded=true` + `close()` + 触发 `degradedHooks`（Req4.3/4.4）。
- `conn.onOpen`：若 `everConnected` 已为真 → 触发 `reconnectHooks`（Req4.2）；置 `everConnected=true`、`errorCount=0`。
- `conn.onMessage(data, event)`：查 `listeners.get(event)` fan-out，每个 handler `try/catch` 隔离（Req2.4）。

### 决策 5：鉴权

Shared_Connection 经 `createSSE(url)`（内部读 `useAuthStore().token` 加 Authorization header），URL = `/api/projects/{pid}/events/stream`（无 `token=`，Req3.1）。LineagePanel 迁移后即用此鉴权连接，天然修复其 native EventSource 无 token 的预存在 401（Req3.2）——本规格附带收益，不单独为 LineagePanel 造鉴权路径。

### 决策 6：迁移顺序与回退

strangler 顺序：W1 建总线 → W2 ThreeColumnLayout（验证 `sse:*` 契约不破）→ W3 useAcnr（复用其已封装的 refCount/degrade 语义，改为委托总线）→ W4 ConsolidationIndex → W5 LineagePanel。每消费者迁移是独立 commit-able 步骤；若某步回归，该消费者可回退自建连接而不影响已迁移者（Req5.5）。`AttachmentManagement`（`/api/sse/projects/{pid}` 不同端点）不在范围（Req5.6）。

### 决策 7：useAcnr 迁移的语义保持

`useAcnr` 现有 `_ProjectSSE`（refCount/degrade/everConnected/onAcnrInvalidate）与总线高度同构。迁移 = `_createProjectSSE` 内部不再自建 `createSSE`，改为 `subscribeProjectEvent(pid, 'acnr:invalidate', onMsg, { onReconnect: clearProjectCache, onDegraded: markDegraded })`；`subscribeInvalidation` 的 refCount 语义并入总线（useAcnr 侧保留薄封装以兼容现有导出 + P8/P9 测试对 `subscribeInvalidation`/`isSSEDegraded` 的调用）。`_onAcnrInvalidate`（catalog_version 全局失效 vs 项目隔离失效）逻辑原样保留（Req5.1）。

## Data Models

无后端 schema 变更（纯前端）。前端内部数据结构：

```ts
// 每 projectId 一条流的内部状态
interface _ProjectStream {
  conn: SSEConnection | null            // 底层 createSSE 连接（唯一）
  listeners: Map<string, Set<Handler>>  // eventName → 处理器集合（fan-out）
  reconnectHooks: Set<() => void>       // Reconnect_Recovery_Hook 集合
  degradedHooks: Set<() => void>        // Degrade_Fallback 通知集合
  refCount: number                      // 订阅总数（Ref_Count_Lifecycle）
  errorCount: number                    // 连续 onError 计数（降级判定）
  everConnected: boolean                // 是否曾成功 open（区分首连/重连）
  degraded: boolean                     // 是否已降级 TTL-only
}

type Handler = (data: unknown, eventName: string) => void

// 对外订阅句柄
interface ProjectEventSubscription { close(): void }
```

- `_byProject: Map<string /*projectId*/, _ProjectStream>` — 模块级单例。
- 订阅记录以 `(projectId, eventName, handler, hooks)` 为单位；`close()` 移除对应 handler/hooks 并 refCount--。
- 事件负载 `data` 为 `createSSE` 已 `JSON.parse` 的对象（或原始字符串），总线不解释语义，仅按 `eventName` 分发。

## Components and Interfaces

- **`services/sse/projectEventStream.ts`（新）**：单例总线。`subscribeProjectEvent` / 内部 `_ensureConnection(pid)` / `_dispatch(pid, event, data)` / `_teardown(pid)`。
- **`ThreeColumnLayout.vue`（改）**：`connectSSE` → 订阅 `sync.failed` 等 Event_Name（handler 内维持 `event_type` 分支 → mitt `sse:*`），`route.projectId` watch 改订阅/退订；`onOpen/onError` → `sse:connected`/`sse:disconnected` 经总线 hook。
- **`useAcnr.ts`（改）**：`_createProjectSSE` 委托总线（决策 7）；保留 `subscribeInvalidation`/`isSSEDegraded` 导出。
- **`ConsolidationIndex.vue`（改）**：`refreshSSE = createSSE(...)` → `subscribeProjectEvent(pid, 'consol.refresh.progress'|'completed'|'error', ...)`；保留 `refreshPollTimer` 兜底（Req5.2）。
- **`LineagePanel.vue`（改）**：`useSSEReconnect` → `subscribeProjectEvent(pid, 'LINKAGE_STALE_CHANGED', ...)`；保留其 `pollFallback`（Req5.3）。
- **不改**：`utils/sse.ts::createSSE`（复用）、后端 `events.py`、`AttachmentManagement.vue`。

## Correctness Properties

### Property 1: 单连接
每 projectId 在任意订阅者数下，底层 createSSE 调用数 = 1。
**Validates: Requirements 1.1, 1.2, 1.4**

### Property 2: fan-out 完整
同 Event_Name 的 N 个订阅者全部收到该事件。
**Validates: Requirements 2.1, 2.2**

### Property 3: Ref_Count_Lifecycle
首订阅开连接、末退订关连接；close 幂等。
**Validates: Requirements 1.2, 1.3**

### Property 4: 项目隔离
projectA 事件不投递给仅订阅 projectB 的监听器；切项目关旧开新。
**Validates: Requirements 1.4, 2.5**

### Property 5: 重连通知
断后重连成功触发 onReconnect；首次 open 不触发。
**Validates: Requirements 4.2**

### Property 6: 鉴权 URL 无 token
Shared_Connection URL 不含 `token=`。
**Validates: Requirements 3.1, 3.2**

### Property 7: 无 projectId no-op
空 projectId 不建连接、close 安全。
**Validates: Requirements 1.5**

### Property 8: 异常隔离
一个 handler 抛错不阻断同事件其他 handler 及后续分发。
**Validates: Requirements 2.4**

### Property 9: 裸事件分发
负载无 event_type 的具名事件仍按 event 名投递。
**Validates: Requirements 2.3**

### Property 10: 降级不重建 + 兜底存活
降级后再订阅不重建；onDegraded 触发。
**Validates: Requirements 4.3, 4.4, 4.5**

### Property 11: 消费者行为等价
各消费者迁移前后：事件到达 + 兜底不变；ThreeColumnLayout `sse:*` 契约不破。
**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

## Error Handling

- createSSE 不可用/抛错 → 总线 `try/catch`，靠各消费者 TTL/poll 兜底（Req4.5）。
- handler 抛错 → 总线 `try/catch` 每 handler 隔离 + `console.warn`（Req2.4/P8）。
- 降级 → `degradedHooks` 通知；不再重建（Req4.4/P10）。
- 项目切换竞态 → 切换时先退订旧 projectId（refCount--）再订阅新，避免连接泄漏（P4）。

## Testing Strategy

- 前端 vitest（mock `createSSE`）：P1–P10 逐条；mock 连接暴露 `_emit(event, data)` / `_open()` / `_error()` 驱动。
- 消费者等价（P11）：各消费者迁移后重跑其现有单测（useAcnr P8/P9、ConsolidationIndex 刷新、LineagePanel refresh spec、ThreeColumnLayout formula-runtime spec）保持绿。
- Playwright（Req6.2）：合并项目底稿页实测 `/events/stream` 连接数 = 1（网络面统计），0 console error。
- 守卫（Req6.3）：脚本/测试断言 `src/` 下除 `projectEventStream.ts` 外无对 `/events/stream` 的 `createSSE(` 直连或 `new EventSource(.../events/stream`。

## Migration / Rollout

- M0（W0）：冻结各消费者事件名与兜底契约（characterization）。
- M1（W1）：建总线 + 单测（P1–P10）。
- M2（W2–W5）：逐消费者迁移（ThreeColumnLayout → useAcnr → ConsolidationIndex → LineagePanel），每步重跑该消费者既有单测 + 独立可回退。
- M3（W6–W7）：Playwright 单连接实测 + 守卫 + 零回归门。
- 不新增后端迁移（纯前端）。
