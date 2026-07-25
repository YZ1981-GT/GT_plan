# Implementation Plan: 前端项目事件流连接去重

## Overview

以 `requirements.md` / `design.md` 为唯一基线。additive strangler：先建单例 `projectEventStream` 总线并存，逐消费者从自建 `createSSE`/`EventSource` 迁移为向总线订阅，每步行为等价、独立可回退、重跑该消费者既有单测保持绿。纯前端，不改后端 SSE 端点 / 负载 / 鉴权，不改各消费者业务逻辑与既有兜底（poll / TTL）。范围仅 `/events/stream`（不含 `AttachmentManagement` 的 `/api/sse/projects/{pid}`）。

前端单测 mock `createSSE`（不 mock fetch/ReadableStream）；Playwright 验证单连接。

## Tasks

- [x] 1. Wave 0 — 契约冻结与前置核实
  - [x] 1.1 盘点 `/events/stream` 全部消费者与其 Event_Name + 兜底：ThreeColumnLayout(`sync.*`→`sse:*`)、useAcnr(`acnr:invalidate`)、ConsolidationIndex(`consol.refresh.progress/completed/error`+poll)、LineagePanel(`LINKAGE_STALE_CHANGED`+poll)；确认 `AttachmentManagement` 走 `/api/sse/projects/` 不同端点（排除）。冻结各消费者迁移前的绿名单单测作为零回归基准。
    - _结论_：4 个 `/events/stream` 消费者已确认（grep 实证）：ThreeColumnLayout `connectSSE`（typed `sync.*`→mitt `sse:connected`/`sse:sync-event`/`sse:sync-failed`/`sse:disconnected`）、useAcnr `_createProjectSSE`（`acnr:invalidate`）、ConsolidationIndex `refreshSSE`（`consol.refresh.progress/completed/error`+`refreshPollTimer` 兜底）、LineagePanel `useSSEReconnect`（`LINKAGE_STALE_CHANGED`+`pollFallback`，native EventSource 无 token）。`AttachmentManagement` 连 `/api/sse/projects/{pid}`（不同端点）→排除。
    - _Requirements: 5.6, 6.1_
  - [x] 1.2 核实 `createSSE` 的 `onMessage(data, event)` 对 backend `broadcast_raw`（`event: {name}\ndata: {extra}`）与 typed（`event: {event_type}\ndata: {全量}`）两类帧的解析行为，冻结 Event_Name 分发键决策（不依赖 `data.event_type`）。
    - _结论_：`createSSE` 解析 `event:` 行为 currentEvent、`data:` 行 JSON.parse → `onMessage(parsed, currentEvent)`。两类帧均把 SSE `event:` 名作为第二参传出（raw: event_type 名；typed: event_type 名）。分发键统一用 `event`（Event_Name），不依赖 `data.event_type`（修复裸事件丢弃）。
    - _Requirements: 2.1, 2.3_

- [x] 2. Wave 1 — 单例总线 Project_Event_Stream_Bus（M1）
  - [x] 2.1 新建 `services/sse/projectEventStream.ts`：`subscribeProjectEvent(projectId, eventName, handler, {onReconnect?, onDegraded?})` + 内部 `_byProject` Map（conn/listeners/reconnectHooks/degradedHooks/refCount/errorCount/everConnected/degraded）+ `_ensureConnection`/`_dispatch`。空 projectId no-op（P7）。
    - _落地_：`services/sse/projectEventStream.ts`（subscribeProjectEvent + isProjectStreamDegraded + _getProjectRefCount 观测）。
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 3.1_
  - [x] 2.2 实现连接生命周期：首订阅 `createSSE(eventPaths.stream(pid))`（Authorization header，无 token= query）；`onMessage`→按 event 名 fan-out（handler `try/catch` 隔离）；`onOpen`→everConnected 守卫触发 reconnectHooks；`onError`→errorCount 超 MAX(5) 降级+触发 degradedHooks+关连接；末退订 refCount→0 关连接。
    - _Requirements: 1.3, 2.1, 2.2, 2.4, 3.1, 4.1, 4.2, 4.3, 4.4_
  - [x] 2.3 单测（mock createSSE）P1–P10：`projectEventStream.spec.ts` **11 passed**（单连接/fan-out/ref-count/close幂等/项目隔离/重连通知/URL无token/no-op/异常隔离/裸事件分发/降级不重建）。
    - _Requirements: 6.1_
    - _Properties: P1, P2, P3, P4, P5, P6, P7, P8, P9, P10_

- [x] 3. Wave 2 — 迁移 ThreeColumnLayout（M2）
  - [x] 3.1 `connectSSE` → `subscribeProjectEvent(pid, WILDCARD_EVENT, handler, {onReconnect→sse:connected, onDegraded→sse:disconnected})`；handler 内维持 `data.event_type` 分支 → mitt `sse:sync-event`/`sse:sync-failed`（catch-all 语义靠总线新增 `'*'` 通配订阅保持等价）；`route.projectId` watch 改订阅/退订（切项目先 close 旧再订新）；移除未用的 `createSSE`/`eventPaths` import。
    - _落地_：总线新增 `WILDCARD_EVENT='*'` fan-out（`_dispatch` 精确+通配双投，通配不重复精确）；`sse:connected`/`sse:disconnected` 无 `.on()` 消费者（grep 实证），映射到 onReconnect/onDegraded 无回归。
    - _Requirements: 5.4, 4.2_
  - [x] 3.2 重跑 ThreeColumnLayout 既有单测（含 formula-runtime spec）保持绿：`src/layouts` **9 passed**；get_diagnostics 全清。
    - _Requirements: 5.4_
    - _Properties: P11_

- [x] 4. Wave 3 — 迁移 useAcnr（M2）
  - [x] 4.1 `subscribeInvalidation` 委托总线：`subscribeProjectEvent(pid, 'acnr:invalidate', _handleAcnrInvalidate, {onReconnect: 清项目resolve缓存})`；useAcnr 侧 `_acnrSubByProject` 引用计数复用单一总线订阅（同项目多订阅只建一个 bus sub）；`isSSEDegraded` 委托 `isProjectStreamDegraded`；`_onAcnrInvalidate`（catalog_version 全局失效 vs 项目隔离）原样保留；移除自建 `_createProjectSSE`/`_sseByProject`/`createSSE` import。
    - _Requirements: 5.1, 4.2, 4.4_
  - [x] 4.2 重跑 useAcnr P8/P9 单测——无需改测试：其 mock `@/utils/sse` createSSE 经真实总线间接生效（URL 同为 `/api/projects/{pid}/events/stream` 无 token=），`src/services/acnr` **38 passed** + 总线 **13 passed** = 51 全绿。
    - _Requirements: 5.1_
    - _Properties: P11_

- [x] 5. Wave 4 — 迁移 ConsolidationIndex（M2）
  - [x] 5.1 `refreshSSE = createSSE(...)` → 3 个 `subscribeProjectEvent(pid, 'consol.refresh.progress'|'completed'|'error', onConsolEvent)`（共享 handler switch on event，按 job_id 客户端过滤）；`refreshPollTimer` 断开轮询兜底保留；`_stopRefreshTracking` close 全部订阅；移除 `createSSE`/`SSEConnection`/`P_events` import。原 URL `?year=` 服务端过滤由 job_id 唯一性替代。
    - _Requirements: 5.2_
  - [x] 5.2 ConsolidationIndex 无专属单测（file_search 确认）；get_diagnostics 全清；改动隔离在 refresh SSE 块；`src/views` 广跑的失败（WorkpaperListShell/useEditingLock 等）为 pre-existing，未 import 本 spec 改动模块。
    - _Requirements: 5.2_
    - _Properties: P11_

- [x] 6. Wave 5 — 迁移 LineagePanel（M2）
  - [x] 6.1 `useSSEReconnect`(native EventSource,无token) → `subscribeProjectEvent(pid, 'LINKAGE_STALE_CHANGED', ...)`（经鉴权 Shared_Connection，附带修复预存在 401 降级 → 实时徽标首次真正生效）；`closeSSE` 保留（defineExpose）+ `onUnmounted(closeSSE)`；移除 `useSSEReconnect` import。
    - _Requirements: 5.3, 3.2_
  - [x] 6.2 重跑 LineagePanel refresh spec 保持绿：更新 3 个 SSE 测试从 mock native EventSource → mock 总线 `subscribeProjectEvent`（挂载订阅/事件重拉/卸载 close）；`LineagePanel.refresh.spec.ts` **16 passed**。
    - _Requirements: 5.3_
    - _Properties: P11_

- [x] 7. Wave 6 — Playwright 单连接实测 + 守卫
  - [x]* 7.1 Playwright 实测（重药控股安徽 0ec33ac9/D2 wp e2c95d10）：workpaper 页（ThreeColumnLayout + useAcnr 两个消费者）`/events/stream` 连接数 = **1**（迁移前为 2：request 376+403），单连接用 `authorization: Bearer` header + `accept: text/event-stream`（**URL 无 token=**）；触发 workpaper 保存 PUT **200** 后 **0 console error**（共享连接处理 acnr:invalidate + WORKPAPER_SAVED sync 事件无异常）；数据幂等写回无污染。
    - _Requirements: 6.2_
    - _Properties: P1, P11_
  - [x] 7.2 守卫 `services/sse/sseConsolidationGuard.spec.ts`（**2 passed**）：断言除 `projectEventStream.ts`/`utils/sse.ts` 外无 `createSSE` 直连 `/events/stream`（bulk `/progress` 等其它 SSE 端点不受约束，R5.6），且无 `new EventSource` 连 `/events/stream`。
    - _Requirements: 6.3_

- [x] 8. Wave 7 — 零回归门与最终验证
  - [x] 8.1 全量重跑迁移涉及消费者的既有单测 + 总线新单测全绿（acnr 38 + sse[总线15+守卫2] + layouts 9 + LineagePanel 16）；get_diagnostics 全清（7 改动源文件）；改动文件 Vite transform 200；守卫（7.2）通过；`src/views` 广跑的失败（WorkpaperListShell/useEditingLock 等）为 pre-existing，未 import 本 spec 改动模块。
    - _Requirements: 6.1, 6.3_
    - _Properties: P11_

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 0, "tasks": ["1.1", "1.2"], "depends_on": []},
    {"wave": 1, "tasks": ["2.1", "2.2", "2.3"], "depends_on": ["1.1", "1.2"]},
    {"wave": 2, "tasks": ["3.1", "3.2"], "depends_on": ["2.1", "2.2", "2.3"]},
    {"wave": 3, "tasks": ["4.1", "4.2"], "depends_on": ["2.1", "2.2", "2.3"]},
    {"wave": 4, "tasks": ["5.1", "5.2"], "depends_on": ["2.1", "2.2", "2.3"]},
    {"wave": 5, "tasks": ["6.1", "6.2"], "depends_on": ["2.1", "2.2", "2.3"]},
    {"wave": 6, "tasks": ["7.1", "7.2"], "depends_on": ["3.1", "3.2", "4.1", "4.2", "5.1", "5.2", "6.1", "6.2"]},
    {"wave": 7, "tasks": ["8.1"], "depends_on": ["7.1", "7.2"]}
  ]
}
```

## Notes

### 执行规则

1. additive strangler：先建总线并存，逐消费者迁移；每消费者迁移是独立 commit-able 步骤，回归可单独回退（Req5.5），不阻塞其他消费者。
2. 行为等价优先：每步迁移后必须重跑该消费者既有单测保持绿（P11）；不放宽/跳过断言。
3. 单一真源：断线重连/退避归 `createSSE`（不在总线或消费者重复实现，与 acnr-invalidation-overlay-hardening #1 一致）。
4. 分发键 = Event_Name（不依赖 `data.event_type`），彻底修复裸事件被丢弃缺陷（Req2.3）。
5. 鉴权统一：所有 Shared_Connection 经 `createSSE`（Authorization header），token 不入 URL；LineagePanel 迁移附带修复其预存在 401。
6. 不假绿：Playwright 单连接（7.1）若受环境阻断以真实网络面统计为准，不伪造；标 `[ ]*` optional 但仍尽力实测。

### 范围边界

- 仅 `/events/stream` 端点消费者。`AttachmentManagement.vue` 的 `/api/sse/projects/{pid}` 为不同端点，不在范围（Req5.6）。
- 不改后端 `events.py` / SSE 负载 / 鉴权（`get_current_user_sse` + `check_project_access`）。
- 不改 `utils/sse.ts::createSSE`（复用其 fetch-based + Authorization header + 重连）。

### 附带收益

- LineagePanel 从 native EventSource（无 token，预存在恒 401 降级 poll）迁到鉴权 Shared_Connection → 其 `LINKAGE_STALE_CHANGED` 实时徽标首次真正生效（非仅 poll 兜底）。
