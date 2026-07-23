# Requirements Document

## Introduction

前端每个已加载项目页当前存在**多条到同一 `/api/projects/{pid}/events/stream` 的 SSE 连接**：`ThreeColumnLayout`（全局 sync 事件）、`useAcnr`（`acnr:invalidate`）、`ConsolidationIndex`（`consol.refresh.*`）、`LineagePanel`（`LINKAGE_STALE_CHANGED`）各自 `createSSE`/`EventSource` 独立订阅。实测一个合并项目下的底稿页可同时打开 3–4 条同端点连接，浪费客户端与服务端资源（每连接一个 `event_bus.create_sse_queue()` + 一个 30s 心跳循环），且各连接鉴权方式不一（`ThreeColumnLayout`/`useAcnr`/`ConsolidationIndex` 走 Authorization header，`LineagePanel` 用 native `EventSource` 无 token → 预存在恒 401 降级 poll）。

根因：`ThreeColumnLayout` 的全局 SSE 处理器**只转发含 `data.event_type` 的事件**（`sync.*`），丢弃 `broadcast_raw` 产出的具名裸事件（`acnr:invalidate` / `consol.refresh.*` / `LINKAGE_STALE_CHANGED` 的 `extra` 不含 `event_type`），导致各特性只能各开一条连接。

本规格引入**单例「项目事件流总线」（Project_Event_Stream_Bus）**：每个项目至多一条共享 SSE 连接，按事件名 fan-out 分发给订阅者；各消费者从「开自己的连接」迁移为「向总线订阅特定事件名」。目标是连接去重 + 鉴权统一（全部经 Authorization header），且**逐消费者行为等价零回归**。

本规格为纯前端重构，不改后端 SSE 端点 / 事件负载 / 鉴权语义；不改各消费者的业务处理逻辑与既有兜底（poll / TTL）。

## Glossary

- **Project_Event_Stream_Bus**：新单例模块，维护 `projectId → 单条共享 SSE 连接 + 事件名→监听器集合 + 引用计数`，对外暴露订阅/退订 API。
- **Shared_Connection**：某 projectId 的唯一底层 `createSSE`（fetch-based，Authorization header）连接。
- **Event_Name**：SSE 帧 `event:` 行的值（如 `acnr:invalidate` / `consol.refresh.progress` / `LINKAGE_STALE_CHANGED` / `sync.failed`）；createSSE 将其作为 `onMessage(data, event)` 的第二参传出。
- **Typed_Sync_Event**：负载含 `data.event_type` 的事件（`ThreeColumnLayout` 现有 `sync.*` 路径），迁移后按 `event_type` 或 `event` 名分发保持等价。
- **Subscriber**：调用总线订阅 API 的消费者（useAcnr / ConsolidationIndex / LineagePanel / ThreeColumnLayout）。
- **Reconnect_Recovery_Hook**：Shared_Connection 断线重连成功（`onOpen` 且此前 `onError` 过）时，总线通知各订阅者执行各自恢复动作（如 useAcnr 清项目 resolve 缓存、ConsolidationIndex 触发 poll 兜底）。
- **Degrade_Fallback**：Shared_Connection 超重试上限降级后，各消费者退回其既有兜底（poll / TTL），不返回陈旧数据。
- **Ref_Count_Lifecycle**：某 projectId 首个订阅者到来时建 Shared_Connection，末个订阅者退订时关闭。

## Requirements

### Requirement 1: 每项目至多一条共享 SSE 连接

**User Story:** 作为平台，我希望同一项目页无论多少特性消费 SSE，都只维持一条到 `/events/stream` 的连接，以减少客户端与服务端资源占用。

#### Acceptance Criteria

1. WHEN 同一 projectId 下有 ≥1 个订阅者 THEN 系统 SHALL 只创建一条 Shared_Connection（不因多消费者产生多条同端点连接）。
2. WHEN 某 projectId 的订阅者数量从 0 变为 ≥1 THEN 系统 SHALL 建立该项目的 Shared_Connection（Ref_Count_Lifecycle 起点）。
3. WHEN 某 projectId 的订阅者数量降为 0 THEN 系统 SHALL 关闭该项目的 Shared_Connection 并释放资源。
4. WHEN 不同 projectId 各有订阅者 THEN 系统 SHALL 每个 projectId 各一条独立 Shared_Connection（项目间隔离）。
5. WHEN 无 projectId（全局目录浏览等）THEN 系统 SHALL NOT 建立任何 Shared_Connection。

### Requirement 2: 按事件名 fan-out 分发（不丢裸事件）

**User Story:** 作为消费者，我希望向总线订阅我关心的事件名即可收到该事件，无论其负载是否含 `event_type`。

#### Acceptance Criteria

1. WHEN Shared_Connection 收到具名事件（`onMessage(data, event)`）THEN 系统 SHALL 将其分发给所有订阅了该 Event_Name 的监听器。
2. WHEN 同一 Event_Name 有多个订阅者 THEN 系统 SHALL 全部 fan-out（不止第一个）。
3. WHEN 事件负载不含 `data.event_type`（如 `acnr:invalidate` / `consol.refresh.*`）THEN 系统 SHALL 仍按 `event` 名正确分发（修复现全局处理器丢弃裸事件的缺陷）。
4. WHEN 某订阅者的处理器抛异常 THEN 系统 SHALL 隔离该异常（记录告警），不影响同事件其他订阅者与后续事件分发。
5. WHERE 消费者只关心特定 Event_Name THE 系统 SHALL NOT 将无关 Event_Name 的事件投递给它。

### Requirement 3: 鉴权统一（Authorization header，token 不入 URL）

**User Story:** 作为安全负责人，我希望所有项目事件流连接都经 Authorization header 鉴权，token 不出现在 URL query。

#### Acceptance Criteria

1. WHEN 建立 Shared_Connection THEN 系统 SHALL 经 `createSSE`（fetch-based，Authorization header）连接，URL SHALL NOT 含 `token=` query。
2. WHEN `LineagePanel` 迁移到总线 THEN 其事件订阅 SHALL 经已鉴权的 Shared_Connection（消除其 native EventSource 无 token 的预存在 401 降级）。
3. WHERE 后端 `/events/stream` 要求鉴权（`get_current_user_sse` + `check_project_access`）THE Shared_Connection SHALL 满足之（Authorization header）。

### Requirement 4: 断线重连与降级（不返回陈旧）

**User Story:** 作为消费者，我希望共享连接断线重连由总线统一处理，重连成功后我能被通知做恢复，降级后退回既有兜底。

#### Acceptance Criteria

1. WHEN Shared_Connection 断线 THEN 系统 SHALL 由 `createSSE` 内部按其退避策略重连（单一真源，消费者不各自重连）。
2. WHEN Shared_Connection 重连成功且此前曾断线 THEN 系统 SHALL 触发 Reconnect_Recovery_Hook 通知所有订阅者。
3. WHEN Shared_Connection 超重试上限降级 THEN 系统 SHALL 通知订阅者进入 Degrade_Fallback，且各消费者的既有兜底（poll / TTL）SHALL 仍有效。
4. WHEN 降级后又调用订阅 THEN 系统 SHALL NOT 无谓重建已降级连接（与既有 useAcnr 降级语义一致）。
5. WHILE 处于降级 THE 系统 SHALL NOT 因缺少实时事件而返回陈旧数据（依赖各消费者 TTL / poll 兜底）。

### Requirement 5: 逐消费者迁移与行为等价（零回归）

**User Story:** 作为维护者，我希望消费者逐个从「自建连接」迁移到「订阅总线」，每步行为等价、可独立验证、失败可回退。

#### Acceptance Criteria

1. WHEN `useAcnr` 迁移到总线 THEN `acnr:invalidate` 的接收与 `_onAcnrInvalidate`（项目隔离失效 / catalog_version 全局失效 / 重连清缓存 / 降级 TTL-only）行为 SHALL 保持等价。
2. WHEN `ConsolidationIndex` 迁移到总线 THEN `consol.refresh.progress/completed/error` 的进度渲染与 SSE 断开轮询兜底 SHALL 保持等价。
3. WHEN `LineagePanel` 迁移到总线 THEN `LINKAGE_STALE_CHANGED` 徽标实时更新 SHALL 生效（且经鉴权连接，非降级 poll）。
4. WHEN `ThreeColumnLayout` 迁移到总线 THEN 现有 `sse:connected` / `sse:sync-event` / `sse:sync-failed` / `sse:disconnected` 事件转发 SHALL 保持等价。
5. WHEN 任一消费者迁移引入回归 THEN 该消费者 SHALL 可独立回退到自建连接（迁移增量、互不阻塞）。
6. WHERE 存在其他 SSE 端点消费者（如 `AttachmentManagement` 连 `/api/sse/projects/{pid}`，非 `/events/stream`）THE 本规格 SHALL NOT 改动之（范围仅 `/events/stream`）。

### Requirement 6: 校验与守卫

**User Story:** 作为维护者，我希望有测试与守卫防止连接去重回归、防止裸事件再被丢弃、防止 token 回流 URL。

#### Acceptance Criteria

1. WHEN 运行前端单测 THEN 系统 SHALL 覆盖 Ref_Count_Lifecycle（P1/P3）、fan-out（P2）、裸事件分发（P9）、异常隔离（P8）、鉴权 URL 无 token（P6）。
2. WHEN 运行 Playwright 实测 THEN 系统 SHALL 验证一个含 ≥2 个 `/events/stream` 消费者的项目页最终只保留一条该端点连接（0 console error）。
3. WHEN 迁移完成 THEN 系统 SHALL NOT 存在对 `/events/stream` 的裸 `new EventSource` 或第二个 `createSSE` 直连（仅经总线）。
