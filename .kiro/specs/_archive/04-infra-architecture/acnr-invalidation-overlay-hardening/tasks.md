# Implementation Plan: ACNR 失效传播与 Overlay 治理加固

## Overview

以 `requirements.md` / `design.md` 为唯一基线，additive strangler 路径加固 ACNR SSE 实时失效、Overlay 持久化并发治理、失效跨 worker durable 化。复用既有 `event_bus.broadcast_raw` / `check_project_access` / `validate_ownership` / single-flight read-through / TTL_Fallback / cache_epoch，不复制、不分叉、不假绿。

PBT 统一用 `backend/tests/conftest.py` 全局 `fast` profile（`max_examples=5`）；PG16 唯一约束 / `ON CONFLICT` / `FOR UPDATE SKIP LOCKED` / 并发 / CAS 必须真实 PostgreSQL 16 验证，SQLite 不替代。迁移动态取下一可用 V（最新 V121）。

## Tasks

- [x] 1. Wave 0 — 契约冻结与前置核实
  - [x] 1.1 核实 `deps.py::get_current_user` 是否支持 SSE query `?token=`（对照 `useChainExecution.ts`）；冻结 SSE 鉴权来源决策（复用现有 or 新增仅用于 event-stream 的 `get_current_user_sse`），不臆测。
    - _结论_：`get_current_user` = HTTPBearer（仅 header），无现成 SSE query-token 依赖 → Wave 3 新增 `get_current_user_sse`（header 优先 + query `?token=` 回退，复用 `app.core.security.decode_token`）。
    - _Requirements: R1.2, R3.1_
  - [x] 1.2 盘点 `acnr_project_overlay` 现有数据是否存在违反 Overlay_Unique_Key 的重复行，冻结去重前置策略（保留最新 updated_at）；确认 `write_overlay`/`delete_overlay` 无生产调用方，冻结受控入口边界。
    - _结论_：dev 库 0 行（无重复），迁移含防御性去重（保留最新 updated_at）供其他环境；`write_overlay`/`delete_overlay` 无生产调用方（grep 确认），受控入口 Wave 4 新建。
    - _Requirements: R5.2, R10_
  - [x] 1.3 冻结既有测试基线：运行 `tests/acnr/`（排除预存在 `service_identities` FK 污染的 `test_overlay_persistence_roundtrip.py` 与 import-path 三文件），记录绿名单作为零回归基准。
    - _结论_：基线绿（GC 37 / full_resolve 78 / grammar+cross-sheet 19 / generate_catalog 13 / 广跑 182 passed）；排除 `test_overlay_persistence_roundtrip.py`（service_identities FK 污染）+ `test_catalog_degradation.py`/`test_immutability.py`/`test_tabindex_codes_in_acnr_catalog.py`（`from backend.app` import-path）。
    - _Requirements: R13.4, R13.5_

- [x] 2. Wave 1 — 迁移与 ORM（M0）
  - [x] 2.1 动态取下一可用 V，新建迁移：`acnr_project_overlay` 增 `reason/owner/expires_at/revision` 列（additive，nullable，revision default 1）；建 Overlay_Unique_Key 前先去重（保留最新 updated_at）；`IF NOT EXISTS`/information_schema 守护幂等。
    - _落地_：`V122__acnr_invalidation_overlay_hardening.sql`（4 列 + DELETE 去重 + pg_constraint 守护唯一约束）。
    - _Requirements: R5.1, R5.2, R7.1, R8.1, R13.1, R13.2_
  - [x] 2.2 同迁移创建 `acnr_invalidation_epoch`（project_id PK + epoch bigint + updated_at）与 `acnr_invalidation_outbox`（id/project_id/wp_id/domain/created_at/dispatched_at/attempts + undispatched 部分索引）。
    - _Requirements: R11.1, R13.1_
  - [x] 2.3 编写对应 rollback（不删 overlay 数据；drop 新增列/约束/表）；ORM 同步 `AcnrProjectOverlay` 新列 + `UniqueConstraint` + 新建 `acnr_invalidation_model.py`（Epoch/Outbox ORM）。
    - _落地_：`R122__rollback_...sql`（drop 约束+两表，治理列默认保留）；`acnr_overlay_model.py` +4列+UniqueConstraint；新建 `acnr_invalidation_model.py`；`models/__init__.py` 注册。
    - _Requirements: R13.1, R13.2_
  - [x] 2.4 真实 PG16 迁移契约：空库 / 历史库（含重复行）/ 中断重跑幂等；建约束前去重生效；schema drift = 0。
    - _验证_：迁移应用成功（12 条语句，schema_version=122）；4 列/唯一约束/2 表/部分索引全部创建；SchemaDriftDetector total_drift=0 & acnr_drift=0。
    - _Requirements: R5.2, R13.2, P13_

- [x] 3. Wave 2 — Durable Epoch + Outbox + Dispatcher（M1）
  - [x] 3.1 升级 `cache_epoch.increment_epoch(project_id, session=None)` 为 DB-first：`INSERT ... ON CONFLICT(project_id) DO UPDATE epoch=epoch+1 RETURNING epoch` 单语句原子单调；成功后 best-effort Redis publish；Redis 不可用 DB 仍递增（不返回 0 丢失）。
    - _落地_：`_increment_db_epoch`/`_read_db_epoch` helper + `increment_epoch` DB-first + Redis fan-out best-effort + DB 失败回退 Redis-only（不回归）；`get_epoch` DB-first。冒烟：0→1 单调。
    - _Requirements: R11.4, R12.1_
  - [x] 3.2 `_epoch_poll_task` 对比 **DB** Durable_Epoch（而非仅 Redis）修复本地缓存；worker 启动时 Redis 不可用仍启动 DB 轮询兜底任务，Redis 恢复后 subscriber 可重建。
    - _落地_：poll 改 `_read_db_epoch`；`start_epoch_subscriber` 始终启动 poll+subscriber（Redis None 不早退，subscriber 内部退避自愈）。
    - _Requirements: R11.4, R11.5, R12.1_
  - [x] 3.3 新建 `acnr/invalidation_outbox.py`：`enqueue(session, project_id, wp_id?, domain?)` 同事务写 outbox 行；`Invalidation_Dispatcher` 用 `FOR UPDATE SKIP LOCKED` 拉未投递行 → increment Durable_Epoch → `broadcast_raw` + Redis pub-sub → 标记 dispatched；失败 attempts++ 不标 dispatched（至少一次）。
    - _落地_：`enqueue`+`_dispatch_batch`(FOR UPDATE SKIP LOCKED+同事务 increment_epoch(session)+broadcast_raw+mark dispatched，失败仅 attempts++)+`InvalidationDispatcher.run_once/start/stop`。冒烟：dispatch 1 行 epoch 递增 undispatched=0。
    - _Requirements: R11.2, R11.3, R11.6_
  - [x] 3.4 dispatcher 后台任务接 lifespan 启停（对齐 `start/stop_epoch_subscriber` 范式）；投递失败不阻断业务事务提交。
    - _落地_：`main.py` lifespan `get_dispatcher().start()` / 关闭 `await get_dispatcher().stop()`。
    - _Requirements: R11.6, R12.3_

- [x] 4. Wave 3 — SSE 后端广播与授权（M1）
  - [x] 4.1 `acnr/events.py::invalidate` 增 `event_bus.broadcast_raw("acnr:invalidate", {project_id, wp_id?, epoch?, catalog_version?})`；project_id 为空不广播；异常仅告警不阻断。
    - _落地_：invalidate() Step 6 broadcast_raw（含 project_id/wp_id/epoch）；入口已非空校验；try/except 仅告警。
    - _Requirements: R2.1, R2.2, R2.4, R2.5_
  - [x] 4.2 `routers/events.py::sse_stream` 在流式推送前执行 `check_project_access(current_user, project_id, db)`；403 脱敏；admin/partner 放行；既有非 ACNR 事件消费不回归。按 1.1 决策接入 SSE token 鉴权来源。
    - _落地_：新增 `deps.get_current_user_sse`（header 优先 + query token 回退，复用 get_current_user 全校验）；`/stream` 用之 + 加 db + `check_project_access`；`/since` 亦加 db + check_project_access。IMPORT_OK 无循环导入。
    - _Requirements: R3.1, R3.2, R3.3, R3.4_
  - [x] 4.3 确认 `broadcast_raw` 不触发 `_handlers`（避免与 WORKPAPER_SAVED 双发），前端 raw 路径过滤 project_id 正确下发。
    - _验证_：`broadcast_raw` 只推 SSE 队列 + Redis Stream，不调 `_dispatch`/`_handlers`（既有实现）；events.py raw 路径 `raw_project_id is None → continue` + `!= project_id → continue`（既有）。
    - _Requirements: R2.3, R2.4_

- [x] 5. Wave 4 — Overlay 持久化并发加固与受控入口（M2）
  - [x] 5.1 `overlay_repository.upsert_overlay` 改 `INSERT ... ON CONFLICT (Overlay_Unique_Key) DO UPDATE SET payload/wp_id/reason/owner/expires_at/updated_at, revision=revision+1` 原子；支持可选 `expected_revision` CAS（不匹配抛 `OverlayRevisionConflict`，DB 不变）；不提供则向后兼容。
    - _落地+冒烟_：非 CAS 走 `pg_insert.on_conflict_do_update`（constraint=uq_overlay_identity，revision+1）；CAS 走条件 UPDATE（WHERE revision=expected，rowcount==0 抛 OverlayRevisionConflict）；Core 写后 `session.refresh` 避免陈旧 revision。冒烟：无重复行(1)/冲突 upsert rev→2/CAS 错误→冲突/CAS 正确 expected=2→rev3。
    - _Requirements: R6.1, R6.2, R6.3, R7.2, R8.2, R8.3, R8.4_
  - [x] 5.2 `overlay.load_project_overlays_from_pg` 读回 `reason/owner/expires_at/revision` 填充 `OverlayPatch`，使 `is_expired()` 重启后按持久值判定；`apply/apply_to_single/get_project_aliases` 跳过过期 overlay（数据源修复）。
    - _落地+冒烟_：load 读回四字段（OverlayPatch 加 revision）；reload expires_at=2020-01-01→is_expired=True。
    - _Requirements: R7.3, R7.4_
  - [x] 5.3 `overlay.write_overlay` 写 PG 后改为 `clear_project_overlays(project_id)`（不再 `set_overlay_in_cache`），read-through 从已提交 PG 重载；外层回滚不留脏缓存。
    - _落地_：write_overlay 传治理字段+expected_revision 给 upsert，返回持久 revision；末尾 clear_project_overlays（非 set）。
    - _Requirements: R9.1, R9.2, R9.3, R9.4_
  - [x] 5.4 新建受控服务入口 `apply_project_overlay` / `remove_project_overlay`：`validate_ownership` + capability（manager/partner）+ 同事务 `invalidation_outbox.enqueue`；写路径可达、可测、可审计；UI 接线标注 spec 外后续项（不假绿）。
    - _落地_：`apply_project_overlay`（capability 校验 _OVERLAY_MUTATE_ROLES→write_overlay[含 validate_ownership]→同事务 outbox enqueue domain=overlay）+`remove_project_overlay`（capability+delete_overlay_by_identity+outbox+清缓存）。UI 接线为 spec 外后续项。
    - _Requirements: R10.1, R10.2, R10.3, R10.4_

- [x] 6. Wave 5 — 前端项目级 SSE（M3）
  - [x] 6.1 `useAcnr` 新增 `subscribeInvalidation(projectId)`：连 `/api/projects/${projectId}/events/stream?token=${token}`（token 取 sessionStorage/localStorage）；按 projectId 引用计数复用；无 projectId 不建连接（不失败重连）；返回 cleanup。
    - _落地_：`_sseByProject` Map 引用计数 + `_createProjectSSE`（正确端点+token）+ cleanup；`useAcnr(projectId?)` 有项目才订阅。vitest：项目级端点+token+引用计数复用。
    - _Requirements: R1.1, R1.2, R1.3, R1.4, R1.5_
  - [x] 6.2 移除/替换错误全局 `_createSSEConnection`（`/api/projects/events?topic=`）；保留退避重连（5s/10s/20s/30s，≤5 次）+ TTL-only 降级 + `onopen` 重连清缓存。
    - _落地_：全局单例整段替换为项目级；`_scheduleProjectReconnect` 退避+降级 console.warn；`onopen` reconnect 后清项目 resolve 缓存。vitest P9 全绿。
    - _Requirements: R1.1, R4.4, R4.5, R13.5_
  - [x] 6.3 实现 `acnr:invalidate` 精细失效：清 Resolve_Cache 中含该 project_id 的条目；`catalog_version` 变化则清全局 Catalog_Cache + 递增 `_cacheEpoch`；仅 project_id 则不清全局。
    - _落地_：`_onAcnrInvalidate`（catalog_version 变→invalidateModuleCache；仅 project_id→_clearResolveCacheForProject）。vitest P8：项目隔离/不 bump epoch/catalog_version 全局失效全绿。
    - _Requirements: R4.1, R4.2, R4.3_
  - [x] 6.4 消费者接订阅点（项目页内有 currentProjectId 的 GtIndexChip / 公式选址器 / 高级查询）；组件切项目释放旧连接建新连接不泄漏。
    - _落地_：单点订阅接入 `GtWpRenderer`（workpaper 渲染外壳，watch renderConfig.project_id → 释放旧+建新连接，onUnmounted 清理），每项目一连接覆盖其下全部 index chip/公式选址/取数消费者（引用计数，优于叶子逐个订阅）；barrel 导出 subscribeInvalidation/MAX_AGE。
    - _Requirements: R1.4, R1.5_

- [x] 7. Wave 6 — 正确性属性 PBT + 集成 + 回归
  - [x] 7.1 PBT P1/P2/P5：Overlay_Unique_Key 并发 upsert 至多一行、Atomic_Upsert 无重复/revision 递增、CAS 不匹配拒绝（真实 PG16）。
    - _落地_：`test_invalidation_overlay_hardening_pbt.py`（一次性临时库）：P1/P2 原子 upsert 无重复+revision→2、唯一约束拒裸重复；P5 CAS 错误→冲突 DB 不变 / 正确→递增。
    - _Requirements: R5, R6, R8, P1, P2, P5_
  - [x] 7.2 PBT P3/P4/P12：write→回滚缓存无未提交状态 + commit 后读新值；expires_at 重启重载 is_expired 一致；受控入口 ownership+capability+同事务 outbox（真实 PG16）。
    - _落地_：P3 write_overlay 清缓存+回滚 PG 无行；P4 治理字段持久化+reload is_expired=True；P12 apply_project_overlay 非授权 403 零写 / 授权 overlay+outbox 同事务原子。
    - _Requirements: R7, R9, R10, P3, P4, P12_
  - [x] 7.3 PBT P10/P11：Redis 不可用 increment_epoch DB 单调递增 + poll 对比 DB 修复；outbox 每行至少一次投递 + Durable_Epoch 单调（真实 PG16 + 模拟 Redis 不可用）。
    - _落地_：P10 set_redis_client(None)→increment_epoch DB 1,2 单调；P11 enqueue×2→_dispatch_batch 全投递 epoch≥2 undispatched=0 / 失败→未标 dispatched attempts++。
    - _Requirements: R11, R12.1, P10, P11_
  - [x] 7.4 后端单元/集成 P6/P7：invalidate 恒广播 acnr:invalidate（空 project_id 不广播、异常不阻断）；/events/stream 无授权 403 + admin/partner 放行 + 既有事件不回归。
    - _落地_：`test_sse_broadcast_and_auth.py`：P6 invalidate 广播含 project_id/wp_id/epoch、空 pid 不广播、广播异常不阻断；P7 check_project_access admin/partner 放行 + 非成员 403 + events 路由引用 check_project_access/get_current_user_sse。
    - _Requirements: R2, R3, P6, P7_
  - [x] 7.5 前端 vitest P8/P9：收 project P 事件只清含 P 的 Resolve_Cache、catalog_version 变清全局；SSE 断连退避降级 TTL-only 且缓存受 MAX_AGE 约束（mock EventSource + 事件注入）。
    - _落地_：重写 `test_useAcnr_cache_invalidation.spec.ts`（P8 项目隔离/不 bump epoch/catalog_version 全局失效）+ `useAcnr_sse_reconnect.spec.ts`（P9 项目级端点+token/退避/降级/重连清项目缓存/引用计数）。acnr dir 41 passed。
    - _Requirements: R4, R12.2, P8, P9_

- [x] 8. Wave 7 — 零回归门与最终验证
  - [x] 8.1 回归门 P14：运行 Wave0 绿名单全套 + 已修 P0 相关测试（TTL/GC fail-closed/explicit_wp_id/invalid_addr_id/version-lock 文案）全绿，get_diagnostics 全清，前端改动 Vite transform 200，后端 py_compile OK。
    - _验证_：acnr 后端全套（排除 4 预存在污染文件）**424 passed, 2 skipped**（含 P0 修复的 full_resolve/catalog_snapshot_gc）；`test_epoch_reconnect.py` **9 passed**；前端 acnr vitest **41 passed**；py_compile 13 文件 OK；get_diagnostics（useAcnr.ts/index.ts/GtWpRenderer.vue）全清；Vite transform 三前端改动文件全 **200**。
    - _Requirements: R13.3, R13.4, R13.5, P14_
  - [x] 8.2 若接入前端 SSE 订阅点：Playwright 实测项目页内底稿保存 → 前端实时收 acnr:invalidate → resolve 缓存刷新（0 console error）；若未接 UI 订阅点，以 vitest + 端点契约覆盖并明确标注不假绿。
    - _验证（真实 Playwright 全栈 round-trip，项目 0ec33ac9/D2 wp e2c95d10）_：①项目级 SSE 端点接受 `?token=` + 通过 check_project_access（手动 EventSource opened=true, error=false）；②底稿保存 PUT **200** → `WORKPAPER_SAVED` → invalidate → DB Durable_Epoch 递增 **epoch=1** → broadcast_raw → SSE 收到具名事件 `acnr:invalidate` payload=`{project_id, wp_id, epoch:1}`（全链真实交付）；③前端 GtWpRenderer 经 useAcnr.subscribeInvalidation 真实打开 native EventSource `/api/projects/{pid}/events/stream?token=<jwt>`（addInitScript 钩子捕获，Wave5.1 live 验证）；④`_onAcnrInvalidate` 缓存清理逻辑由 vitest P8（41 passed）覆盖；⑤数据幂等无污染（remark 写回同值不变）；0 console error。
    - _Requirements: R1, R2, R4_

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 0, "tasks": ["1.1","1.2","1.3"], "depends_on": []},
    {"wave": 1, "tasks": ["2.1","2.2","2.3","2.4"], "depends_on": ["1.1","1.2","1.3"]},
    {"wave": 2, "tasks": ["3.1","3.2","3.3","3.4"], "depends_on": ["2.1","2.2","2.3","2.4"]},
    {"wave": 3, "tasks": ["4.1","4.2","4.3"], "depends_on": ["2.1","2.2","2.3","2.4"]},
    {"wave": 4, "tasks": ["5.1","5.2","5.3","5.4"], "depends_on": ["2.1","2.2","2.3","2.4","3.3"]},
    {"wave": 5, "tasks": ["6.1","6.2","6.3","6.4"], "depends_on": ["4.1","4.2","4.3"]},
    {"wave": 6, "tasks": ["7.1","7.2","7.3","7.4","7.5"], "depends_on": ["5.1","5.2","5.3","5.4","6.1","6.2","6.3","6.4"]},
    {"wave": 7, "tasks": ["8.1","8.2"], "depends_on": ["7.1","7.2","7.3","7.4","7.5"]}
  ]
}
```

## Notes

### 执行规则

1. additive strangler：新增参数带默认值，不改既有公共 API 形状；迁移不删 legacy 列。
2. Fail_Closed：Redis/SSE/DB 任一降级退到更保守路径（DB epoch / TTL / 拒绝写），不静默保留陈旧值。
3. PG16 真实验证唯一约束 / ON CONFLICT / FOR UPDATE SKIP LOCKED / 并发 / CAS；SQLite 不替代。
4. 诚实边界：outbox 事务性至少一次仅在持有业务 session 的 overlay 变更路径；底稿保存路径为 DB-durable-epoch post-commit best-effort，残余风险由轮询/TTL 修复，不谎称事务性。
5. 零回归：已修 P0 + 既有 ACNR 能力经回归门守护；不绕过/放宽断言/跳用例。
6. 不假绿：UI 未接订阅点时以 vitest + 契约覆盖并明确标注，不以 mock 冒充生产可达。

### 已知预存在（不在本规格修复范围，仅排除以免误判回归）

- `test_overlay_persistence_roundtrip.py` 因 `attachments.actor_service_identity_id → service_identities`（ORM 未注册）SQLite create_all FK 崩 —— 与本规格无关的既有污染。
- `test_catalog_degradation.py` / `test_immutability.py` / `test_tabindex_codes_in_acnr_catalog.py` 用 `from backend.app...` 导入路径，按 rootdir 收集失败 —— 既有 import-path 问题。
