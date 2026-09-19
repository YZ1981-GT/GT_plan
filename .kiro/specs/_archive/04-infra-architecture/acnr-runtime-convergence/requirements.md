# Requirements Document

## Introduction

本 spec 聚焦 ACNR **运行时闭环修复**——CodeGraph 实证分析（2026-07-15）确认的 13 类真实缺口。

**不是大爆炸重写**，而是把已有五层模型（L0–L4）的**运行时管道焊死**：
- 公共 resolve 端点实际调用 `full_resolve`（当前只调 `catalog.resolve`，L2/L3/非 wp 域全绕过）
- Grammar 文件路径修正 + 启动 fail-fast
- 项目授权 + wp_id binding 完整性
- Overlay 持久化（当前纯内存，保存失效即永久丢失）
- RuntimeCell 保存后重建（当前 project 全量清除）
- Canonical identity 收敛（URI/formula/addr_id/custom_flat 多态统一）
- 分布式缓存 epoch + 增量失效
- 依赖图/反向索引收敛（FormulaReverseIndex 与 LinkageGraphBuilder 双重建模）
- 版本锁定真实实现（当前 warning 后继续用当前版）
- Catalog 治理指标真守卫（gap_count=0 但 5 conflict + 123 unregistered）
- Consumer Coverage 真实扫描器（当前只测 hypothetical records）
- 可观测性（hit/miss/ambiguous/fallback 指标）

**与 `acnr` spec 关系**：`acnr` 定义五层模型与 M0–M3 里程碑（已标 100% 但叶子 4.3 仍 `[ ]`）。本 spec 修运行时管道，不重新定义模型。
**与 `acnr-consumer-wiring` 关系**：consumer-wiring 关注消费者侧迁移（P1–P15）。本 spec 修基础设施，consumer-wiring 是下游受益者。

**Scope**：后端 `app/services/acnr/` + `app/routers/acnr.py` + 前端 `useAcnr.ts` cache 层 + CI 守卫。
**Non-goals**：不扩展业务消费者；不新增循环底稿；不改动 D~N 组件逻辑。

---

### 增量修订（Phase 2，2026-07-16）

基于 Phase 1 全部 15 任务完成后的 CodeGraph 实证分析，追加 4 条生产稳健性需求（Req-13 ~ Req-16），提升高并发/多 worker/长期运行场景的韧性。

---

## Requirements

---

### Req-1: 公共 Resolve 端点收敛

**User Story:** 作为任一前端消费者，我调用 `/api/acnr/resolve` 时期望获得与 `full_resolve` 完全等价的结果（含 L2 Overlay、L3 Runtime、非 wp 域委托），而非被限制在 L1 catalog.resolve。

#### Acceptance Criteria

1. WHEN 前端调用 `POST /api/acnr/resolve` 并传入 `uri/formula_ref/addr_id/index_ref` 任一语法，THE 端点 SHALL 内部调用 `resolver.full_resolve()` 并返回其完整结果。
2. WHEN 请求携带 `project_id`，THE 端点 SHALL 将 project_id 透传给 `full_resolve`，使 L2 Overlay 与 L3 Runtime 生效。
3. WHEN 请求携带 `wp_id`（显式绑定），THE 端点 SHALL 透传给 `full_resolve` 的 `explicit_wp_id` 参数。
4. THE `catalog.resolve()` SHALL 降为内部 L1 helper，不再作为公共端点的唯一出口。
5. WHEN 非 wp 域（tb/report/note/aux）输入经 `full_resolve` 委托 V1 动态 build，THE 端点 SHALL 以统一响应契约返回结果（与 wp 域格式一致）。


---

### Req-2: Grammar 源完整性与启动 Fail-Fast

**User Story:** 作为运维人员，我期望后端启动时若 `grammar_v1.json` 文件路径错误或内容不完整，服务直接拒绝启动而非静默落入硬编码默认值。

#### Acceptance Criteria

1. WHEN `grammar.py` 加载 `grammar_v1.json`，THE 路径 SHALL 正确指向 `backend/data/acnr/grammar_v1.json`（当前 `parents[4]` 偏移错误导致实际指向仓库根 `data/acnr/`）。
2. WHEN 文件不存在或 JSON 解析失败，THE 启动 SHALL 抛出明确异常（而非静默使用默认常量掩盖缺失）。
3. WHEN 文件加载成功，THE grammar SHALL 校验至少包含 5 个域定义、11 个命名空间映射、`STANDARD_WP_CODE_RE` 常量、且 `registry_version` 非空。
4. IF 校验项缺失，THEN 启动 SHALL fail-fast 并输出缺失项清单。

---

### Req-3: 项目授权与 Binding 完整性

**User Story:** 作为安全负责人，我期望 resolve/resolve-instance 在携带 project_id 时做项目访问授权，且 explicit wp_id 必须与请求的 project/sheet_code 对应，防止 IDOR 泄露。

#### Acceptance Criteria

1. WHEN `/api/acnr/resolve` 或 `/api/acnr/resolve-instance` 携带 `project_id`，THE 端点 SHALL 校验当前用户对该 project 有访问权（经 `project_assignments` 或角色）。
2. WHEN 请求携带 `explicit_wp_id`，THE 端点 SHALL 校验该 wp_id 属于请求的 `project_id` **且** 对应 `WpIndex.parent_wp_code` 与 `sheet_code` 匹配。
3. IF 授权失败或 binding 不匹配，THEN 端点 SHALL 返回 403（不泄露 wp_id/jump_route 元数据）。
4. WHEN 请求不携带 project_id（纯 catalog lookup），THE 端点 SHALL 不返回 wp_id/jump_route 等项目级数据。

---

### Req-4: Overlay 持久化与归属校验

**User Story:** 作为底稿编辑者，我期望项目级 Overlay（自定义别名、CUST 覆盖）在保存失效后仍可恢复，而非随内存清除永久丢失。

#### Acceptance Criteria

1. THE ProjectOverlay 权威数据 SHALL 持久化到 PostgreSQL（新表或扩展现有表），内存仅作派生缓存。
2. WHEN `events.invalidate()` 触发，THE invalidate SHALL 清除内存缓存但 **不删除** 持久化的 Overlay 数据。
3. WHEN Overlay 写入，THE 系统 SHALL 校验 wp_id 属于 project **且** 经 WpIndex 确认 parent/sheet/catalog 全链归属（修复当前 `JOIN working_paper wp ON wp.id = wi.wp_id` 的 ORM JOIN 错误）。
4. WHEN 缓存失效后首次读取，THE 系统 SHALL 从持久化存储重建内存缓存。

---

### Req-5: RuntimeCell 保存后重建与增量失效

**User Story:** 作为公式选址器用户，我期望底稿保存后新增/修改的自定义格立即可被搜索到，且不会因 project 全量清除导致其他底稿的 Runtime 条目丢失。

#### Acceptance Criteria

1. WHEN 底稿 parsed_data 保存提交后，THE 系统 SHALL 按 `wp_id` 增量重建 L3 RuntimeCell（仅重建该 wp 的条目，不清除同 project 其他 wp 的条目）。
2. WHEN `events.invalidate()` 触发，THE 系统 SHALL 仅清除触发 wp_id 相关的 L3 缓存（非 project 全量清除）。
3. WHEN L3 有多个候选匹配同一 `resolved_addr_id` 前缀，THE 系统 SHALL 返回 `ambiguous` 而非迭代顺序中的第一个（修复 `startswith` 错格风险）。
4. THE RuntimeCell SHALL 可从 parsed_data 确定性重建（重启/缓存冷启动时自动重建，不依赖一次性注册）。

---

### Req-6: Canonical Identity 收敛

**User Story:** 作为依赖图维护者，我期望每个物理格在系统内只有一个 canonical node id，URI/formula/index/addr_id 仅是边界语法适配，内部不产生双身份。

#### Acceptance Criteria

1. THE 系统 SHALL 定义 `CanonicalAddress` 值对象（或等价数据类），作为内部唯一标识。
2. WHEN 从 URI/formula_ref/index_ref/addr_id 四种语法输入解析，THE 系统 SHALL 收敛到同一 `CanonicalAddress`。
3. THE `custom_flat` profile（2 参 `WP(code,cell)`）SHALL 仅作为边界兼容 adapter，内部存储统一为 3 参标准形态的 canonical addr_id。
4. THE FormulaReverseIndex 的边端点 SHALL 全部使用 canonical addr_id（当前非 WP 端点仍保留 URI/legacy 字符串）。

---

### Req-7: 分布式缓存与 Epoch 机制

**User Story:** 作为多 worker 部署场景的运维人员，我期望任一 worker 的 Overlay/Runtime 更新能及时通知其他 worker 刷新本地缓存，避免长时间不一致。

#### Acceptance Criteria

1. THE 系统 SHALL 维护 `registry_version`（全局 catalog 版本）与 `project_epoch`（per-project 变更计数器）。
2. WHEN Overlay/Runtime 写入后，THE 系统 SHALL 递增对应 `project_epoch` 并经 Redis pub-sub 通知其他 worker。
3. WHEN worker 收到 epoch 变更通知，THE worker SHALL 清除对应 project 的本地缓存（下次请求重建）。
4. WHEN 前端 `useAcnr.ts` module-level cache 过期（或收到 SSE/WebSocket 通知），THE 前端 SHALL 统一失效并重新请求（当前无失效机制）。

---

### Req-8: 依赖图与反向索引收敛

**User Story:** 作为 stale 影响分析的消费者，我期望 forward（谁依赖我）和 reverse（我依赖谁）查询来自同一份边数据，而非 FormulaReverseIndex 与 LinkageGraphBuilder 各自独立读取数据源导致不一致。

#### Acceptance Criteria

1. THE `LinkageGraphBuilder` SHALL 作为边的单一真源（收集所有边源：CCR、公式、渲染依赖等）。
2. THE `FormulaReverseIndex` SHALL 作为 LinkageGraphBuilder 的派生视图（仅读取 graph 构建的边，不独立扫描数据源）。
3. ALL 边端点 SHALL 使用 canonical addr_id（当前 FormulaReverseIndex 仅 WP 端转 addr_id，其他域保留旧格式）。
4. THE `CrossSheetResolver._sync_resolve()` 在 async 热路径检测到 event loop 时 SHALL 使用 async orchestrator 预解析（而非静默返回 None 降级到 snapshot fallback）。

---

### Req-9: 版本锁定真实实现

**User Story:** 作为归档合规负责人，我期望归档项目的引用按项目创建时锁定的 `registry_version` 解析，而非 warning 后继续用当前版本。

#### Acceptance Criteria

1. WHEN `full_resolve` 发现项目锁定版本与当前 Catalog 不同，THE 系统 SHALL 加载对应版本的 Catalog 快照进行解析（而非 warning 后继续用当前版）。
2. THE 系统 SHALL 实现 `load_versioned_catalog(version)` 方法（当前为 TODO stub）。
3. WHEN 请求的 `registry_version` 不存在对应快照，THE 系统 SHALL 返回明确治理错误（而非静默降级到当前版）。
4. WHEN Catalog 新版本发布，THE 系统 SHALL 自动归档当前版本为不可变快照（append-only）。

---

### Req-10: Catalog 治理指标真守卫

**User Story:** 作为治理看板消费者，我期望 `catalog_report.json` 的 `gap_count` 真实反映冲突与未登记项，而非在有 5 个 alias conflict + 123 个 unregistered aliases 时报 0。

#### Acceptance Criteria

1. THE `gap_count` SHALL 等于 `alias_conflicts.length + unregistered_aliases.length + 其他缺口类计数`（当前为 0 是错误的）。
2. WHEN CI 运行 `check-acnr-catalog-drift`，THE CI SHALL 校验 `gap_count` 与明细计数一致（不一致则阻断）。
3. THE `catalog_report.json` SHALL 包含 `generated_at` 时间戳且 CI 校验其不超过 7 天（防止陈旧报告掩盖漂移）。
4. WHEN alias conflict 被确认为已知例外（有 reason），THE 系统 SHALL 在 `acknowledged_conflicts` 段登记并从 gap_count 扣除。

---

### Req-11: Consumer Coverage 真实扫描器

**User Story:** 作为架构治理负责人，我期望 CI 守卫能真实扫描源码中 `address_registry.` 直接调用，阻断未经 ACNR 的新增 legacy 消费者，而非只测 hypothetical records。

#### Acceptance Criteria

1. THE CI SHALL 包含真实源码扫描器（扫描 `backend/app/` 下 `address_registry.` 直接调用/import），不仅仅是 PBT hypothetical consumer drift guard。
2. WHEN 新增文件包含 `address_registry.` 直接消费且未在 Coverage Ledger allowlist 登记，THE CI SHALL 阻断 PR。
3. THE Coverage Ledger allowlist SHALL 位于可审计的配置文件中（如 `backend/data/acnr/coverage_ledger.json`），每项标注迁移目标 P 编号。
4. THE 扫描器 SHALL 区分「直接消费」（import address_registry 并调用）与「间接经 ACNR facade」（import useAcnr/acnr service），后者不计入违规。

---

### Req-12: 可观测性与降级指标

**User Story:** 作为平台运维人员，我期望 resolve 链路的 hit/miss/ambiguous/fallback/auth-reject 有结构化指标，异常降级不再是 TODO logger。

#### Acceptance Criteria

1. THE `full_resolve` SHALL 在每次调用结束时记录结构化指标：`{domain, layer_hit, result(found/ambiguous/miss/fallback), latency_ms}`。
2. WHEN 解析降级到 V1 动态 build（非 wp 域委托）或 snapshot fallback，THE 系统 SHALL 记录 `fallback` 事件及原因。
3. WHEN 项目授权拒绝，THE 系统 SHALL 记录 `auth_reject` 事件（不含敏感数据）。
4. THE 系统 SHALL 提供 `/api/acnr/metrics` 端点（或 Prometheus exporter）返回近期聚合指标。
5. THE 管理端 SHALL 在 alias conflict / version mismatch / Overlay 持久化失败时主动告警（不仅 logger.warning）。

---

### Req-13: Overlay 缓存冷启动 Single-Flight 防护

**User Story:** 作为高并发场景的运维人员，我期望 Overlay 缓存冷启动时同一 project 的并发请求不会触发 N 次重复 DB 查询（惊群效应），而是只有一次查询在飞，其他等待复用结果。

#### Acceptance Criteria

1. WHEN 多个并发请求同时触发同一 project_id 的 Overlay 缓存重建，THE 系统 SHALL 确保只有一个 DB 查询实际执行（single-flight 语义）。
2. WHEN single-flight 查询完成，THE 系统 SHALL 将结果广播给所有等待中的请求（不重复查询）。
3. THE single-flight 实现 SHALL 使用 `asyncio.Lock` per-project（或等价并发原语），不阻塞不同 project 的请求。
4. WHEN single-flight 查询失败（DB 异常），THE 系统 SHALL 释放锁并允许后续请求重试（不死锁）。

---

### Req-14: Redis Pub-Sub 订阅断连重连与 Epoch 轮询兜底

**User Story:** 作为多 worker 部署的运维人员，我期望 Redis pub-sub 订阅在网络抖动断连后能自动重连，且有轮询机制兜底确保缓存最终一致性。

#### Acceptance Criteria

1. WHEN Redis pub-sub 订阅连接断开，THE worker SHALL 在 5 秒内自动尝试重连（指数退避，最大 30 秒）。
2. WHEN 重连成功，THE worker SHALL 清除全部本地缓存（因断连期间可能错过消息）。
3. THE worker SHALL 每 60 秒执行一次 epoch 轮询：对本地缓存的每个 project_id，对比本地 epoch 与 Redis epoch，不一致则清除本地缓存。
4. WHEN Redis 完全不可用（连接超时），THE worker SHALL 降级为每次请求重建缓存（epoch=0 模式），并记录 `fallback` metric。

---

### Req-15: 前端缓存 TTL 兜底与批量 Resolve

**User Story:** 作为前端消费者，我期望 `useAcnr.ts` 的 module-level cache 有最大生存时间兜底（即使 SSE 推送失败），且高频场景（公式选址器搜索）支持批量 resolve 减少网络往返。

#### Acceptance Criteria

1. THE `useAcnr.ts` module-level cache SHALL 为每条缓存项设置 `maxAge`（默认 300 秒 / 5 分钟），超时后下次访问自动失效并重新请求。
2. WHEN SSE `acnr:invalidate` 事件到达，THE 前端 SHALL 立即清除对应 project 的全部缓存（不等 TTL 过期）。
3. THE 前端 SHALL 提供 `batchResolve(inputs[])` 方法，单次 HTTP 请求解析多个地址（减少公式选址器 20+ 格搜索的 RTT）。
4. THE 后端 SHALL 新增 `POST /api/acnr/resolve-batch` 端点，接受 `items: Array<{uri?, formula_ref?, addr_id?, index_ref?}>` + `project_id`，返回等长结果数组。

---

### Req-16: Catalog 版本快照生命周期管理

**User Story:** 作为运维人员，我期望 Catalog 版本快照不会无限膨胀，系统自动清理无引用的旧版本快照，同时确保被项目锁定的版本永不删除。

#### Acceptance Criteria

1. THE 系统 SHALL 保留最近 N 个版本快照（默认 N=10），加上所有被项目锁定引用的版本。
2. WHEN Catalog 新版本发布后，THE 系统 SHALL 检查旧快照引用计数（查 projects 表 `registry_version` 列），引用计数为 0 且不在最近 N 内的快照 SHALL 被安全删除。
3. WHEN 试图删除仍被引用的快照，THE 系统 SHALL 拒绝删除并记录 warning。
4. THE CI SHALL 校验快照目录总数不超过 N + 被引用版本数（防止清理逻辑失效导致膨胀）。

---

### Req-17: resolve_instance 结果缓存（减少 N+1 DB 查询）

**User Story:** 作为公式选址器用户，我期望在一次 resolve 会话中，相同 project_id + sheet_code 的 `resolve_instance` 不会重复查询 DB，而是复用上一次结果。

#### Acceptance Criteria

1. WHEN `full_resolve` 在同一请求内多次调用 `_attach_wp_id`（如批量 resolve），THE 系统 SHALL 缓存 `resolve_instance` 结果（per-request 级别 memo，key = `project_id:parent_wp_code:sheet_code`）。
2. WHEN 批量 resolve（resolve-batch）处理 N 个输入，THE `_attach_wp_id` 对相同 (project_id, parent, sheet_code) 三元组 SHALL 仅查 1 次 DB。
3. THE 缓存生命周期 SHALL 限定为单次 HTTP 请求（request-scoped），不跨请求保留。
4. WHEN `resolve_instance` 返回 `disambiguation`（多实例），THE 缓存 SHALL 不缓存该结果（每次重新查询以获取最新状态）。

---

### Req-18: 前端 SSE 断连自动重建

**User Story:** 作为前端用户，我期望 `useAcnr.ts` 的 SSE 连接在断开后自动重建（而非等待页面切换创建新 composable 实例），确保缓存失效通知不中断。

#### Acceptance Criteria

1. WHEN SSE `onerror` 触发连接断开，THE 前端 SHALL 在 5 秒后自动尝试重建连接（而非仅关闭旧连接等待下次实例化）。
2. THE 重建 SHALL 使用指数退避（5s/10s/20s/30s max），连续失败不超过 5 次后停止重试并降级为 TTL-only 模式。
3. WHEN 重建成功，THE 前端 SHALL 立即执行 `invalidateModuleCache()`（断连期间可能错过消息）。
4. THE 系统 SHALL 记录 SSE 断连/重连事件到 console.warn（非 silent）。

---

### Req-19: L3 Runtime 模糊搜索收紧

**User Story:** 作为 resolve 准确性的保障，我期望 Step 6（L3 RuntimeCellEntry 搜索）的 fallback 分支不会因 `startswith(wp_code)` 宽松匹配导致跨底稿错格。

#### Acceptance Criteria

1. THE L3 模糊搜索 SHALL 移除 `resolved_addr_id.startswith(rt_entry.wp_code)` 条件（当前 Step 6 fallback 仍保留此宽松条件）。
2. THE L3 搜索 SHALL 仅保留以下匹配逻辑：精确 `addr_id` 匹配 OR `resolved_addr_id == rt_entry.cell_address`（cell 级精确）OR `resolved_addr_id.endswith("/" + rt_entry.cell_address)`（含路径的 cell 精确）。
3. WHEN 多个 L3 条目匹配，THE 系统 SHALL 返回 `ambiguous`（而非第一个命中，修复 Req-5.3 在 Step 6 的残留漏洞）。
4. THE 修复 SHALL 有 PBT 验证：相邻 wp_code（如 D2 vs D2-2）不会因 startswith 互相命中。

---

### Req-20: 非 wp 域 resolve 结果前端缓存

**User Story:** 作为前端消费者，我期望 tb/report/note/aux 域的 resolve 结果也被缓存（与 wp 域同等待遇），减少审定表/报表引用密集场景的重复网络请求。

#### Acceptance Criteria

1. THE `useAcnr.ts` SHALL 为 `resolveFormula/resolveUri/resolveAddr/resolveIndex` 的结果提供 resolve 级缓存（key = 输入参数哈希）。
2. THE resolve 缓存 SHALL 与 sheets/cells 缓存共享同一 `_cacheEpoch` 失效机制（epoch 变则全部过期）。
3. THE resolve 缓存 SHALL 有独立 `MAX_RESOLVE_CACHE_SIZE`（默认 200 条）LRU 淘汰策略，防止无限膨胀。
4. WHEN resolve 返回 `found=false`，THE 缓存 SHALL 不缓存该结果（miss 可能因数据变更而在下次成功）。
