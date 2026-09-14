# Requirements Document

## Introduction

本规格加固 **ACNR（地址坐标名称注册中心）失效传播与 Overlay 治理** 的三条跨前后端缺口。这些缺口在 2026-07-23 源码复盘中确认为「架构级、需 spec」，区别于同批已直接落地的 P0 targeted 修复（前端 resolve LRU TTL、snapshot GC fail-closed、显式 wp_id 透传、invalid_addr_id、snapshot 缺失文案 —— 均已 commit-ready，本规格不重复，仅作回归保证纳入 Requirement 13）。

三条缺口：

1. **SSE 实时失效三重断链**：前端 `useAcnr` 的 `_createSSEConnection()` 连的是不存在的全局端点 `/api/projects/events?topic=acnr:invalidate`（真实为项目级 `/api/projects/{project_id}/events/stream`，且 `EventSource` 无法携带 Bearer），而后端 `acnr.events.invalidate()` **从不向前端 SSE 广播 `acnr:invalidate`**（只 `increment_epoch` 给后端 worker）。三者任一不通即前端收不到实时失效，当前靠 TTL 有界降级兜底（功能正确但非实时）。此外 `/events/stream` 只有 `get_current_user` 认证、**缺 `check_project_access` 项目授权**。

2. **Overlay 持久化与并发治理缺口**：`acnr_project_overlay` 表**无组合唯一约束**、`upsert_overlay` 是非原子 `SELECT→INSERT/UPDATE`（并发下产生重复行）、治理字段 `reason/owner/expires_at` **只在内存 `OverlayPatch` dataclass、从不落 PG**（重启后 `expires_at` 治理失效、`is_expired()` 恒 False）、**无 `revision`/CAS 乐观并发**、`write_overlay()` 在事务仅 `flush` 后即写内存缓存（外层回滚 → 缓存持有未提交状态）。且 `write_overlay`/`delete_overlay` **当前无任何生产调用方**（写路径存在但生产不可达，上述缺口为潜伏风险）。

3. **失效跨 worker 无 durable 机制**：Redis 不可用时 `increment_epoch()` 返回 0，业务变更成功但其他 worker 未必失效缓存；启动时 Redis client 为 None 则 subscriber/poll 任务直接退出、恢复后不自动重建；失效信号与业务变更非同事务，worker/Redis 崩溃可丢失失效。

### 现状映射（已核实）

- 前端：`audit-platform/frontend/src/services/acnr/useAcnr.ts`（模块级全局缓存 `_sheetsCache`/`_cellsCache`/`_resolveCache` + `_cacheEpoch` + `_createSSEConnection` 全局单例）。
- 后端 SSE：`backend/app/routers/events.py`（`/api/projects/{project_id}/events/stream`，`Depends(get_current_user)`，raw 事件按 `project_id` 过滤，`broadcast_raw` 产生 `{_raw, event_type, project_id, year, extra}`）。
- 后端失效：`backend/app/services/acnr/events.py::invalidate()`（L3→L2→reverse_index→legacy→`increment_epoch`）。
- 跨 worker：`backend/app/services/acnr/cache_epoch.py`（Redis INCR + pub-sub + 重连 + 60s 轮询；Redis 不可用返回 0）。
- Overlay：`overlay.py`（服务+内存缓存）/ `overlay_repository.py`（CRUD）/ `acnr_overlay_model.py`（ORM）/ `migrations/V103__acnr_project_overlay.sql`。
- 鉴权：`backend/app/services/acnr/auth.py::check_project_access`（已存在，admin/partner 放行，否则查 project_users / project_assignments）。
- 事件广播：`backend/app/services/event_bus.py::broadcast_raw(event_type, extra)`（同步，推所有内存 SSE 队列 + 异步持久化 Redis Stream）。
- 最新迁移 = V121（新迁移动态取下一可用 V，预期 V122+）。

### 目标

修复 SSE 三重断链使前端获得实时（best-effort）+ 最终一致（TTL/durable epoch）双层失效；加固 Overlay 持久化并发正确性与治理字段持久化；引入 DB-backed durable epoch + invalidation outbox 使跨 worker 失效不依赖 Redis 可用性。**全程 additive strangler、fail-closed、零回归**。

## Glossary

- **ACNR_Invalidate_Event**：前端 SSE 事件类型字符串 `acnr:invalidate`，payload 含 `project_id`、可选 `wp_id`/`epoch`/`catalog_version`。
- **Project_Scoped_SSE**：前端按当前项目连接 `/api/projects/{project_id}/events/stream?token=<jwt>` 的订阅（区别于当前错误的全局单例）。
- **SSE_Token_Auth**：`EventSource` 无法设置 Authorization 头，鉴权 token 经 query 参数 `?token=` 传递（对齐 `useChainExecution.ts` 既有模式）。
- **Module_Cache**：`useAcnr` 的三层模块级缓存（sheets/cells/resolve）+ `_cacheEpoch`。
- **Resolve_Cache**：`_resolveCache`，key 含 `project_id` 的项目级 resolve 结果缓存。
- **Catalog_Cache**：`_sheetsCache`/`_cellsCache`，L1 静态目录缓存（项目无关）。
- **TTL_Fallback**：`MAX_AGE=300s` 缓存过期兜底（已修，Requirement 13 回归保证）。
- **Overlay_Row**：`acnr_project_overlay` 表一行，唯一身份 = (project_id, parent_wp_code, sheet_code, overlay_type)。
- **Overlay_Unique_Key**：组合唯一约束 `UNIQUE(project_id, parent_wp_code, sheet_code, overlay_type)`。
- **Overlay_Governance_Fields**：`reason` / `owner` / `expires_at`（治理元数据，须持久化并重启恢复）。
- **Overlay_Revision**：`revision` 整型列，CAS 乐观并发版本号。
- **Atomic_Upsert**：`INSERT ... ON CONFLICT (Overlay_Unique_Key) DO UPDATE`，单语句原子。
- **Cache_After_Commit**：Overlay 写入只在事务提交后使缓存生效（写路径清缓存 + 读路径 read-through 重载，绝不缓存未提交 flush 状态）。
- **Durable_Epoch**：DB-backed per-project 失效计数器（Redis 不可用仍单调递增），Redis 仅作 commit 后 fan-out。
- **Invalidation_Outbox**：`acnr_invalidation_outbox` 表，业务变更与失效信号同事务写入，dispatcher 至少一次投递（递增 Durable_Epoch + Redis fan-out + SSE 广播）。
- **Invalidation_Dispatcher**：读取未投递 outbox 行 → 递增 Durable_Epoch → `broadcast_raw` + Redis pub-sub → 标记已投递。
- **Fail_Closed**：Redis/SSE/DB 任一不可用时，绝不返回可能陈旧的 allow；退化到更保守的失效（清缓存/TTL 兜底/拒绝写），不静默保留旧值。

## Requirements

### Requirement 1: 前端项目作用域 SSE 订阅（修正端点与鉴权）

**User Story:** 作为使用 ACNR 消费库的前端组件，我希望在当前项目底稿保存后实时收到 ACNR 缓存失效通知，以便公式选址/索引跳转/取数不依赖 5 分钟 TTL 才刷新。

#### Acceptance Criteria

1. WHEN `useAcnr` 在具备当前项目上下文时建立 SSE 订阅 THEN 系统 SHALL 连接项目级端点 `/api/projects/{project_id}/events/stream`，而非当前错误的全局 `/api/projects/events?topic=acnr:invalidate`。
2. WHEN 建立 `EventSource` 连接 THEN 系统 SHALL 通过 query 参数 `?token=<jwt>` 传递鉴权 token（`EventSource` 无法设置 Authorization 头），token 来源与 `useChainExecution.ts` 既有模式一致。
3. WHEN 无当前项目上下文（如全局目录浏览）THEN 系统 SHALL NOT 建立项目级 SSE，仅依赖 TTL_Fallback + 手动 `invalidateModuleCache`，且不产生对不存在端点的失败重连日志。
4. WHEN 同一项目被多个 `useAcnr` 实例订阅 THEN 系统 SHALL 复用单一项目级连接（按 project_id 引用计数），所有引用释放后关闭该项目连接。
5. WHEN 组件切换项目 THEN 系统 SHALL 释放旧项目连接并按需建立新项目连接，不泄漏 `EventSource`。

### Requirement 2: 后端向前端 SSE 广播 ACNR 失效

**User Story:** 作为后端失效链，我希望在项目底稿保存触发 ACNR 失效时，向该项目的前端 SSE 流广播 `acnr:invalidate`，使前端能实时清对应缓存。

#### Acceptance Criteria

1. WHEN `acnr.events.invalidate(project_id, ...)` 执行 THEN 系统 SHALL 调用 `event_bus.broadcast_raw("acnr:invalidate", {"project_id": project_id, ...})` 向前端 SSE 队列推送项目级失效事件。
2. WHEN 广播 ACNR_Invalidate_Event THEN payload SHALL 至少含 `project_id`，并附带可用于前端精细失效的可选字段（`wp_id` 增量、`epoch` 对比、`catalog_version` 目录版本）。
3. WHEN `broadcast_raw` 推送 THEN 系统 SHALL NOT 触发 EventBus `_handlers`（避免与 `WORKPAPER_SAVED` 处理链双发/成环），与既有 `broadcast_raw` 语义一致。
4. IF `project_id` 为空 THEN 系统 SHALL NOT 广播（events/stream 的 raw 路径对 `project_id is None` 直接跳过，不下发到具体项目流）。
5. WHEN ACNR 广播失败（如无 SSE 队列/异常）THEN 系统 SHALL 仅告警不抛出，不阻断 `invalidate()` 主流程（TTL 与 Durable_Epoch 为最终兜底）。

### Requirement 3: SSE 端点项目授权

**User Story:** 作为平台，我希望订阅某项目事件流的用户必须对该项目有访问权，避免越权接收其他项目的失效/进度事件。

#### Acceptance Criteria

1. WHEN 用户连接 `/api/projects/{project_id}/events/stream` THEN 系统 SHALL 在开始流式推送前执行 `check_project_access(current_user, project_id, db)`。
2. IF 用户对该项目无访问权 THEN 系统 SHALL 返回 403 且不建立事件流，不泄露项目是否存在等元数据。
3. WHEN 用户为 admin / partner THEN 系统 SHALL 按 `check_project_access` 既有规则放行（可访问全部项目）。
4. WHEN 为 SSE 端点增加项目授权 THEN 系统 SHALL NOT 破坏既有非 ACNR 事件（试算表更新等）消费者的连接行为（授权通过后事件过滤/心跳/drain 不变）。

### Requirement 4: 前端 SSE 失效语义与降级

**User Story:** 作为前端缓存，我希望收到 `acnr:invalidate` 时按项目精细失效，且在 SSE 不可用时安全降级到 TTL，不返回陈旧结果。

#### Acceptance Criteria

1. WHEN 前端收到项目 P 的 ACNR_Invalidate_Event THEN 系统 SHALL 清除 Resolve_Cache 中属于项目 P 的条目（key 含该 project_id）。
2. WHEN 事件携带 `catalog_version` 且与本地已知目录版本不同 THEN 系统 SHALL 一并清除项目无关的 Catalog_Cache（sheets/cells）并递增 `_cacheEpoch`。
3. WHEN 事件仅含 `project_id`（无版本变化信号）THEN 系统 SHALL 仅失效项目级 Resolve_Cache，不必清全局 Catalog_Cache（避免过度失效）。
4. IF SSE 连接断开 THEN 系统 SHALL 按既有指数退避（5s/10s/20s/30s，最多 5 次）重连；超限降级为 TTL-only（`isSSEDegraded()=true`）并停止重连。
5. WHEN SSE 重连成功 THEN 系统 SHALL 清空缓存以同步断连期间可能遗漏的失效消息（既有 `onopen` 行为保留）。
6. WHEN SSE 处于 TTL-only 降级 THEN Resolve_Cache/Catalog_Cache SHALL 仍受 TTL_Fallback（`MAX_AGE`）约束不返回超时陈旧值（Requirement 13 回归保证）。

### Requirement 5: Overlay 组合唯一约束

**User Story:** 作为 Overlay 持久层，我希望同一 (项目, 父底稿, sheet, overlay 类型) 至多一行，避免并发写产生重复行导致 read-through 缓存二义。

#### Acceptance Criteria

1. WHEN 迁移应用 THEN 系统 SHALL 在 `acnr_project_overlay` 上创建 `UNIQUE(project_id, parent_wp_code, sheet_code, overlay_type)`（Overlay_Unique_Key）。
2. IF 既有数据存在违反该唯一键的重复行 THEN 迁移 SHALL 在建约束前先去重（保留最新 `updated_at` 一行，合并/丢弃其余），避免建约束失败。
3. WHEN 唯一约束存在 THEN 任何绕过 Atomic_Upsert 的重复插入 SHALL 被 DB 拒绝（约束层兜底）。

### Requirement 6: Overlay 原子 upsert

**User Story:** 作为 Overlay 写路径，我希望 upsert 是单语句原子操作，消除 `SELECT→INSERT/UPDATE` 之间的竞态窗口。

#### Acceptance Criteria

1. WHEN `upsert_overlay` 执行 THEN 系统 SHALL 使用 `INSERT ... ON CONFLICT (Overlay_Unique_Key) DO UPDATE SET ...` 单语句原子写，而非先 `SELECT` 再分支 `INSERT/UPDATE`。
2. WHEN 两个并发事务对同一 Overlay_Unique_Key upsert THEN 系统 SHALL 恰好保留一行（不产生重复），且不因竞态抛未处理异常。
3. WHEN Atomic_Upsert 命中冲突走 UPDATE 分支 THEN 系统 SHALL 更新 `payload`、`wp_id`、Overlay_Governance_Fields、`updated_at` 并递增 `revision`。

### Requirement 7: Overlay 治理字段持久化与重启恢复

**User Story:** 作为审计治理，我希望 overlay 的 `reason/owner/expires_at` 持久化，使过期治理在进程重启后仍生效。

#### Acceptance Criteria

1. WHEN 迁移应用 THEN 系统 SHALL 在 `acnr_project_overlay` 增加 `reason`（text）/ `owner`（varchar）/ `expires_at`（date，nullable）列（additive，nullable，不破坏既有行）。
2. WHEN `write_overlay(... reason=, owner=, expires_at=)` 执行 THEN 系统 SHALL 将三字段持久化到 PG（而非仅内存 `OverlayPatch`）。
3. WHEN `load_project_overlays_from_pg` 从 PG 重载 THEN 系统 SHALL 读回 `reason/owner/expires_at` 填充 `OverlayPatch`，使 `is_expired()` 在重启后按持久化的 `expires_at` 正确判定。
4. IF overlay 已过 `expires_at` THEN `ProjectOverlay.apply`/`apply_to_single`/`get_project_aliases` SHALL 跳过该 overlay（既有 `is_expired()` 逻辑，修复其数据源）。

### Requirement 8: Overlay 乐观并发（revision/CAS）

**User Story:** 作为 Overlay 写路径，我希望以 revision 做乐观并发控制，避免两个写方互相覆盖而不自知。

#### Acceptance Criteria

1. WHEN 迁移应用 THEN 系统 SHALL 增加 `revision`（int，NOT NULL，default 1）列。
2. WHEN 调用方提供 `expected_revision` 且与当前行 `revision` 不一致 THEN 系统 SHALL 拒绝该写（抛可识别的冲突错误），不覆盖对方修改。
3. WHEN 未提供 `expected_revision`（首次创建或不启用 CAS）THEN 系统 SHALL 正常 upsert（向后兼容，不强制 CAS）。
4. WHEN UPDATE 成功 THEN `revision` SHALL 单调递增。

### Requirement 9: Overlay 缓存 commit 后生效

**User Story:** 作为 Overlay 读路径，我希望内存缓存只反映已提交的 PG 状态，外层事务回滚不得留下脏缓存。

#### Acceptance Criteria

1. WHEN `write_overlay` 写 PG 后 THEN 系统 SHALL NOT 在同一未提交事务内把新 patch 直接 `set_overlay_in_cache`（当前行为，flush ≠ commit）。
2. WHEN overlay 写入完成 THEN 系统 SHALL 清除该 project 的内存缓存（`clear_project_overlays`），使下次读经 read-through 从**已提交**的 PG 重载。
3. IF 外层事务回滚 THEN 系统 SHALL NOT 保留任何该 project 的未提交 overlay 缓存（清缓存策略天然满足：回滚后 PG 无该行，重载得到旧状态）。
4. WHEN 并发读在写事务提交前发生 THEN read-through SHALL 返回旧的已提交状态（不返回未提交的新值）。

### Requirement 10: 受控 Overlay 变更入口

**User Story:** 作为平台，我希望 overlay 写/删有受控的服务层入口与权限校验，使加固后的写路径可达、可测、可审计（当前 `write_overlay`/`delete_overlay` 无生产调用方）。

#### Acceptance Criteria

1. WHEN 提供 Overlay 变更服务入口 THEN 系统 SHALL 在写/删前执行既有 `validate_ownership`（wp_id 属于 project + 经 WpIndex 全链归属）。
2. WHEN 执行 overlay 变更 THEN 系统 SHALL 经 Invalidation_Outbox 同事务写入失效信号（Requirement 11），而非仅内存 epoch。
3. IF 调用者权限不足 THEN 系统 SHALL 拒绝变更（capability 校验，manager / partner 或平台既有 overlay 治理角色）。
4. WHEN 本规格不落地 overlay 编辑 UI THEN 系统 SHALL 明确以服务层入口 + 契约/集成测试证明写路径正确，UI 接线标注为 spec 外后续项（不假绿）。

### Requirement 11: Durable Epoch + Invalidation Outbox

**User Story:** 作为跨 worker 失效机制，我希望失效信号与业务变更同事务持久化，即使 Redis 不可用或 worker 崩溃也不丢失失效。

#### Acceptance Criteria

1. WHEN 迁移应用 THEN 系统 SHALL 创建 Durable_Epoch 持久化（per-project 单调递增计数器，DB-backed）与 Invalidation_Outbox 表（含 project_id、可选 wp_id/domain、created_at、dispatched_at）。
2. WHEN 业务变更（overlay 写/底稿保存触发的 ACNR 失效）发生 THEN 系统 SHALL 在**同一事务**写入一条 Invalidation_Outbox 行。
3. WHEN Invalidation_Dispatcher 运行 THEN 系统 SHALL 读取未投递（dispatched_at 为空）的 outbox 行 → 递增该 project 的 Durable_Epoch → `broadcast_raw` 前端 + Redis pub-sub 通知其他 worker → 标记 dispatched_at；投递保证至少一次。
4. IF Redis 不可用 THEN Durable_Epoch SHALL 仍在 DB 递增，worker 的 60s 轮询 SHALL 对比 DB Durable_Epoch（而非仅 Redis）以修复本地缓存，不因 Redis 不可用而丢失失效（消除当前 `increment_epoch` 返回 0 即失效丢失）。
5. WHEN worker 启动时 Redis 不可用 THEN 系统 SHALL 仍启动 DB 轮询兜底任务；Redis 恢复后 subscriber SHALL 能重建（不因启动即 None 而永久退出）。
6. WHEN outbox 投递失败（Redis/广播异常）THEN 系统 SHALL NOT 标记 dispatched，下次重试（至少一次投递），且不阻断业务事务提交。

### Requirement 12: 降级安全与 Fail-Closed

**User Story:** 作为平台，我希望 SSE/Overlay/失效链任一依赖不可用时都以更保守的方式退化，绝不返回可能陈旧的 allow。

#### Acceptance Criteria

1. WHEN Redis 不可用 THEN 失效 SHALL 退化到 DB Durable_Epoch + 轮询（Requirement 11），前端退化到 TTL_Fallback；SHALL NOT 因 Redis 缺失而静默保留跨 worker 陈旧缓存。
2. WHEN SSE 不可用/降级 THEN 前端 SHALL 退化到 TTL_Fallback（Requirement 4.6），SHALL NOT 无限期返回陈旧 resolve 结果。
3. WHEN Overlay 写路径 DB 异常 THEN 系统 SHALL 使写失败（抛错），SHALL NOT 假成功或留下脏缓存；single-flight/read-through 既有降级（保留旧缓存 + re-raise）不回归。
4. WHEN 事件流授权失败 THEN 系统 SHALL fail-closed 拒绝（403），SHALL NOT 建立可能越权的流。

### Requirement 13: 迁移卫生与已修 P0 回归保证

**User Story:** 作为维护者，我希望本规格迁移 additive 幂等、且不回归同批已直接落地的 ACNR P0 修复与既有 ACNR 能力。

#### Acceptance Criteria

1. WHEN 新增迁移 THEN 系统 SHALL 动态取下一可用 V（最新 V121，预期 V122+），additive、可重复检测（`IF NOT EXISTS` / information_schema 守护）、不删除 legacy 列，且提供对应 rollback。
2. WHEN 迁移在空库、历史库、中断重跑执行 THEN 系统 SHALL 幂等且不损坏既有数据；ORM/Pydantic 同步后 schema drift = 0。
3. WHEN 本规格落地 THEN 系统 SHALL NOT 回归同批已修 P0：前端 resolve LRU TTL、snapshot GC fail-closed（`referenced_versions=None → 不删`）、`full_resolve` 显式 `explicit_wp_id` 透传、`invalid_addr_id` 返回、version-lock 快照缺失 fail-closed 文案。
4. WHEN 本规格落地 THEN 系统 SHALL NOT 回归既有 ACNR 能力：TTL_Fallback、single-flight（`get_overlay_cached`）、`validate_ownership` JOIN 方向、`verify_wp_binding`、四语法 resolve 决策树、L3 收紧、canonical round-trip、consumer coverage guard。
5. WHEN 引入前端项目级 SSE THEN 系统 SHALL 移除/替换错误的全局 SSE 单例，且 `test_epoch_reconnect` 等既有失效测试不回归。

### Requirement 14: 正确性属性（PBT 可测）

**User Story:** 作为质量门，我希望核心不变量以属性测试锁定，避免回归。

#### Acceptance Criteria

1. WHEN 对任意并发 upsert 序列 THEN Overlay_Unique_Key 下 SHALL 恒为至多一行（P: 唯一性）。
2. WHEN 对任意 write→（模拟回滚）序列 THEN 缓存 SHALL 不含未提交状态（P: Cache_After_Commit）。
3. WHEN 对任意 `expires_at` 过去/未来/空 THEN 重启重载后 `is_expired()` 判定 SHALL 与持久化值一致（P: 治理持久化）。
4. WHEN 对任意 outbox 行序列在 Redis 可用/不可用下 THEN Durable_Epoch SHALL 单调递增且每行至少投递一次（P: 至少一次投递 + 单调）。
5. WHEN 对任意 SSE 事件（含错序/重复/仅 project_id/含 catalog_version）THEN 前端失效 SHALL 收敛到「不返回超过 TTL 的陈旧值」且项目隔离（P: 失效收敛 + 项目隔离）。
6. WHEN `expected_revision` 不匹配 THEN 写 SHALL 恒被拒绝且不改 DB（P: CAS 安全）。
