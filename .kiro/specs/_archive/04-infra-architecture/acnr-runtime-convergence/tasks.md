# Implementation Plan

## Overview

ACNR 运行时收敛：12 条需求 / 14 条正确性属性 / 15 个顶层任务。

**并行策略**：最大化子代理并发——同一 Wave 内的 Task 互不修改相同文件，可由独立子代理同时执行。

**文件隔离矩阵**（确保无竞态冲突）：

| 子代理 | 主要修改文件 | 不可同时运行 |
|--------|-------------|--------------|
| Task 1 | tests/acnr/test_public_resolve_contract.py, test_resolve_instance_contract.py | — |
| Task 2 | services/acnr/grammar.py, tests/acnr/test_grammar_integrity.py | — |
| Task 3 | routers/acnr.py, tests/acnr/test_public_vs_full_resolve_equivalence.py | Task 4（同改 acnr.py） |
| Task 4 | services/acnr/auth.py, routers/acnr.py, tests/acnr/test_acnr_project_isolation.py | Task 3 |
| Task 5 | services/acnr/overlay.py, overlay_repository.py, migrations/V{N}.sql | — |
| Task 6 | services/acnr/runtime.py, events.py, tests/acnr/test_runtime_*.py | — |
| Task 7 | services/acnr/canonical.py, tests/acnr/test_canonical_*.py | — |
| Task 8 | services/acnr/cache_epoch.py, events.py | Task 6（同改 events.py） |
| Task 9 | frontend useAcnr.ts, tests/useAcnr*.spec.ts | — |
| Task 10 | formula_reverse_index.py, linkage_graph_builder.py, cross_sheet_resolver.py | — |
| Task 11 | services/acnr/resolver.py, data/acnr/catalog_snapshots/ | — |
| Task 12 | scripts/check/check_acnr_catalog_drift.py, data/acnr/catalog_report.json | — |
| Task 13 | scripts/check/check_acnr_consumer_coverage.py, data/acnr/coverage_ledger.json | — |
| Task 14 | services/acnr/metrics.py, routers/acnr.py(metrics端点) | Task 3/4 完成后 |
| Task 15 | 无新文件（只跑测试+Playwright） | 全部完成后 |

---

## Tasks

- [x] 1. 建立 API 契约基线测试 [Req-1, P1]
  - 新建 `tests/acnr/test_public_resolve_contract.py`：5 个金样例（URI/formula/addr_id/index/non-wp 各一），记录当前返回值 baseline
  - 新建 `tests/acnr/test_resolve_instance_contract.py`：3 场景（正常/无权限/binding不匹配），记录 baseline
  - **子代理自包含**：仅新建测试文件，不修改源码
- [x] 2. Grammar 源完整性修复 [Req-2]
  - 修复 `services/acnr/grammar.py` 路径（`parents[4]` → 正确偏移指向 `backend/data/acnr/grammar_v1.json`）
  - 新建 `_validate_grammar(data)` 校验（5域/11ns/STANDARD_WP_CODE_RE/registry_version）
  - lifespan 启动调用校验，失败 `sys.exit(1)`
  - 新建 `tests/acnr/test_grammar_integrity.py`
  - **子代理自包含**：仅改 grammar.py + 新建测试
- [x] 3. 公共端点改调 full_resolve [Req-1, P1, P2]
  - 修改 `routers/acnr.py`：resolve 端点导入 `resolver.full_resolve` 替代 `catalog.resolve`
  - 请求模型增加 `project_id/wp_id/domain` Optional 字段
  - 响应模型统一（wp/非wp 同一 schema）
  - PBT `test_public_vs_full_resolve_equivalence.py`
  - **前置**：Task 1 完成（有 baseline 可对比）
- [x] 4. 项目授权与 Binding 校验 [Req-3, P3, P4]
  - 新建 `services/acnr/auth.py`：`check_project_access` + `verify_wp_binding`
  - 在 resolve/resolve-instance 端点接入（有 project_id 时）
  - PBT `test_acnr_project_isolation.py` [P3] + 集成测试 `test_acnr_binding_integrity.py` [P4]
  - **前置**：Task 3 完成（端点已改为 full_resolve）
- [x] 5. Overlay 持久化与归属校验 [Req-4, P5]
  - 调用 `migration_status` 确认最高 V 号，新建迁移 `V{N+1}_acnr_project_overlay.sql`
  - 新建 ORM `AcnrProjectOverlay` + `overlay_repository.py`（CRUD + per-project）
  - 修改 `overlay.py`：写入走 PG，内存改 read-through 缓存
  - 修复 ORM JOIN 方向 + 写入时全链归属校验
  - PBT `test_overlay_persistence_roundtrip.py` [P5]
  - **子代理自包含**：仅改 overlay 层 + 新建 migration/repo/测试，不改 router
- [x] 6. Runtime 增量重建 + L3 错格修复 [Req-5, P6, P7]
  - 新建 `runtime.rebuild_runtime_for_wp(wp_id, parsed_data)`
  - 修改 `events.invalidate`：有 wp_id 时仅清该 wp L3（非 project 全量）
  - 修复 L3 匹配：startswith(wp_code) → 精确或 startswith(target+"/")，多候选返回 ambiguous
  - 冷启动从 DB parsed_data 惰性重建 L3
  - PBT `test_runtime_incremental_invalidation.py` [P7] + 集成 `test_runtime_save_then_resolve.py` [P6]
  - **子代理自包含**：仅改 runtime.py + events.py + 新建测试
- [x] 7. CanonicalAddress 值对象 [Req-6, P9, P2]
  - 新建 `services/acnr/canonical.py`：frozen dataclass + from_addr_id/from_uri/from_formula_ref/addr_id
  - PBT `test_canonical_roundtrip.py` [P9] + `test_four_syntax_convergence.py` [P2]
  - FormulaReverseIndex 内部改用 CanonicalAddress
  - full_resolve 内部匹配改 CanonicalAddress 比较
  - **子代理自包含**：新建 canonical.py 纯无副作用模块 + 改引用点
- [x] 8. 分布式缓存 Epoch [Req-7, P8]
  - 新建 `services/acnr/cache_epoch.py`：increment_epoch/get_epoch (Redis INCR + pub-sub)
  - 修改 `events.invalidate`：invalidate 后调 increment_epoch
  - worker 订阅 `acnr:invalidate:*` 清本地缓存
  - PBT `test_epoch_monotonic.py` [P8]
  - **前置**：Task 6 完成（events.invalidate 已改为增量）
- [x] 9. 前端缓存失效 [Req-7]
  - 修改 `useAcnr.ts`：module cache 加 cacheEpoch + 监听 SSE `acnr:invalidate` → 清缓存
  - vitest `test_useAcnr_cache_invalidation.spec.ts`
  - **子代理自包含**：仅改前端文件，无后端依赖
- [x] 10. 依赖图与反向索引收敛 [Req-8, P10]
  - LinkageGraphBuilder 增加 `get_edges_for/predecessors` 方法
  - FormulaReverseIndex 改为读 LinkageGraphBuilder 边（不独立扫描）
  - PBT `test_reverse_index_is_graph_projection.py` [P10]
  - CrossSheetResolver：async 热路径 `await full_resolve_async` 替代 `_sync_resolve()` None 降级
  - **前置**：Task 7 完成（CanonicalAddress 用于边端点统一）
- [x] 11. Catalog 版本快照与锁定解析 [Req-9, P11]
  - ACNR_Generator 生成时自动归档 `data/acnr/catalog_snapshots/{version}.json`
  - 实现 `load_versioned_catalog(version)` + LRU 缓存
  - full_resolve 检测版本不同时调 load_versioned_catalog
  - 版本缺失返回 `VersionNotFoundError`
  - PBT `test_versioned_resolve_determinism.py` [P11]
  - **子代理自包含**：仅改 resolver.py 版本分支 + 新建 snapshots 逻辑 + 测试
- [x] 12. Catalog 治理指标修复 [Req-10, P13]
  - 修改 catalog 报告生成：gap_count = alias_conflicts + unregistered_aliases + ...
  - CI `check_acnr_catalog_drift.py` 增加 gap_count 守恒 + generated_at 陈旧度校验
  - 单元测试 `test_catalog_gap_count_integrity.py` [P13]
  - **子代理自包含**：仅改报告生成 + CI 脚本 + 测试
- [x] 13. Consumer Coverage 真实扫描器 [Req-11, P12]
  - 新建 `scripts/check/check_acnr_consumer_coverage.py`：扫描 backend/app/ 下 address_registry. 直接调用
  - 新建 `data/acnr/coverage_ledger.json` allowlist（每项标注迁移目标 P 编号）
  - 区分直接消费 vs 间接经 ACNR facade
  - 挂 governance-checks.yml
  - 集成测试 `test_consumer_coverage_scanner.py` [P12]
  - **子代理自包含**：仅新建脚本/配置/测试
- [x] 14. 可观测性 [Req-12, P14]
  - 新建 `services/acnr/metrics.py`：结构化指标收集器
  - full_resolve 调用结束记录指标
  - 新建 `GET /api/acnr/metrics` 端点（admin/manager 限制）
  - fallback/auth_reject/alias-conflict/version-mismatch → 主动告警
  - 集成测试 `test_acnr_metrics_fallback.py` [P14]
  - **前置**：Task 3 + Task 4 完成（端点已改造）
- [x] 15. 全量验证 + Playwright [Req-1–12, P1–14]
  - 运行全部 `tests/acnr/` 测试套件确保回归零
  - Playwright：公式选址器搜索 D2/D2-2/E100 → 命中 + jump_route 正确
  - Playwright：GtIndexChip `value="wp:D2"` → resolve → 跳转
  - Playwright：不同项目用户 → resolve 另一项目 wp_id → 403
  - 更新 INDEX.md 状态
  - **前置**：全部 Task 1–14 完成

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": "wave-a",
      "name": "并行组A: 无依赖（最大并行度=8）",
      "tasks": [1, 2, 5, 7, 9, 11, 12, 13],
      "dependsOn": []
    },
    {
      "id": "wave-b",
      "name": "并行组B: 公共Resolve改造",
      "tasks": [3],
      "dependsOn": ["wave-a"]
    },
    {
      "id": "wave-c",
      "name": "并行组C: 授权+可观测性",
      "tasks": [4, 14],
      "dependsOn": ["wave-b"]
    },
    {
      "id": "wave-d",
      "name": "并行组D: Runtime增量+Epoch",
      "tasks": [6],
      "dependsOn": ["wave-a"]
    },
    {
      "id": "wave-e",
      "name": "并行组E: Redis Epoch",
      "tasks": [8],
      "dependsOn": ["wave-d"]
    },
    {
      "id": "wave-f",
      "name": "并行组F: 图收敛",
      "tasks": [10],
      "dependsOn": ["wave-a"]
    },
    {
      "id": "wave-final",
      "name": "最终验证",
      "tasks": [15],
      "dependsOn": ["wave-c", "wave-e", "wave-f", "wave-a"]
    }
  ]
}
```

**最大并行度 = 8**（Task 1/2/5/7/9/11/12/13 可同时启动，互不修改相同文件）

## Notes

- 每个 Task 标注了「子代理自包含」说明，确保子代理有明确的文件边界
- Task 3 与 Task 4 不可并行（共改 `routers/acnr.py`），必须串行
- Task 6 与 Task 8 不可并行（共改 `events.py`），必须串行
- Task 9（前端）与所有后端 Task 天然隔离，随时可并行
- 子代理执行时必须先 `read_file` 目标文件确认当前状态，再动手修改
- PBT 统一 `@settings(max_examples=5)` + `deadline=None`
- 迁移版本以 `migration_status` 实测为准，禁凭 memory 认定

---

## Phase 2 Tasks (增量修订: 生产稳健性)

- [x] 16. Overlay Single-Flight 防护 [Req-13, P15]
  - 修改 `services/acnr/overlay.py`：增加 `_flight_locks: dict[str, asyncio.Lock]`
  - 实现 `get_overlay_cached(project_id, session)` 的 single-flight 逻辑（acquire lock → 二次检查 → DB query → 写缓存 → release）
  - DB 异常时释放锁不死锁 + 保留旧缓存
  - PBT `tests/acnr/test_overlay_single_flight.py` [P15]：asyncio.gather 10 并发 → assert DB 调用仅 1 次
  - **子代理自包含**：仅改 overlay.py + 新建测试

- [x] 17. Redis Pub-Sub 订阅重连与 Epoch 轮询兜底 [Req-14, P16]
  - 修改 `services/acnr/cache_epoch.py`：新增 `start_epoch_subscriber()` + `_reconnect_loop()` + `_epoch_poll_task()`
  - 指数退避重连（5s/10s/20s/30s max）；重连后清全部本地缓存
  - 轮询兜底每 60s 对比本地 epoch vs Redis epoch → 不一致清缓存
  - 在 `main.py` lifespan 中调用 `start_epoch_subscriber()`
  - 集成测试 `tests/acnr/test_epoch_reconnect.py` [P16]：mock 断开 → remote INCR → 60s 内 poll 修复
  - **子代理自包含**：仅改 cache_epoch.py + main.py lifespan + 新建测试

- [x] 18. 前端缓存 TTL 兜底 + 批量 Resolve [Req-15, P17]
  - 修改 `useAcnr.ts`：cache entry 加 `timestamp` 字段 + `MAX_AGE=300_000` 过期判断
  - 新增 `batchResolve(inputs[])` → `POST /api/acnr/resolve-batch`
  - 后端 `routers/acnr.py` 新增 `POST /api/acnr/resolve-batch` 端点（items ≤ 50 限制 + 复用 auth + 循环 full_resolve）
  - vitest `tests/useAcnr_cache_ttl.spec.ts` [P17] + 后端集成 `tests/acnr/test_resolve_batch.py`
  - **前置**：Task 3/4 完成（端点授权已到位）

- [x] 19. Catalog 快照生命周期管理 [Req-16, P18]
  - 新建 `services/acnr/catalog_snapshot_gc.py`：`cleanup_stale_snapshots(keep_recent=10)`
  - 查 PG `projects.registry_version` 被引用集 → 保留 recent + referenced → 删其余
  - 被引用版本拒绝删除 + warning
  - ACNR Generator 生成新版本后自动调 cleanup
  - PBT `tests/acnr/test_snapshot_gc_safety.py` [P18]：随机版本+引用 → 被引用永不删除
  - CI 守卫 `check_acnr_snapshot_count.py` 校验总数 ≤ keep_recent + referenced
  - **子代理自包含**：新建 gc 模块 + 改 generator 调 cleanup + 新建测试 + CI 脚本

- [x] 20. Phase 2 全量验证 [Req-13–16, P15–18]
  - 运行全部 `tests/acnr/` 确保 Phase 1 + Phase 2 回归零
  - 并发压测：httpx 50 并发 resolve 同 project → 确认 single-flight 生效 + metrics 正常
  - Playwright：公式选址器批量搜索 20 格 → batchResolve 一次 HTTP 往返
  - 更新 INDEX.md 状态
  - **前置**：Task 16–19 全部完成

- [x] 21. resolve_instance 请求级缓存 [Req-17, P19]
  - 修改 `services/acnr/resolver.py`：`_attach_wp_id` 接受 `_instance_memo: dict` 参数
  - 缓存 key = `f"{project_id}:{parent_wp_code}:{sheet_code}"`，命中则跳过 DB
  - `resolve-batch` 端点创建 memo dict 传入各次 full_resolve
  - disambiguation 结果不缓存
  - 集成测试 `tests/acnr/test_resolve_instance_memo.py` [P19]：batch 10 同 sheet → DB 仅调 1 次
  - **子代理自包含**：仅改 resolver.py + resolve-batch 端点 + 新建测试
  - **前置**：Task 18 完成（resolve-batch 端点已存在）

- [x] 22. 前端 SSE 断连自动重建 [Req-18, P20]
  - 修改 `useAcnr.ts` `_connectSSE`：onerror 启动重建定时器（指数退避 5/10/20/30s max, 最多 5 次）
  - 重建成功 → `invalidateModuleCache()` 立即调用
  - 超 5 次 → 降级 TTL-only（停止重建）+ console.warn
  - vitest `tests/useAcnr_sse_reconnect.spec.ts` [P20]
  - **子代理自包含**：仅改前端文件

- [x] 23. L3 模糊搜索收紧 [Req-19, P21]
  - 修改 `services/acnr/resolver.py` Step 6：删除 `startswith(rt_entry.wp_code)` 条件
  - 保留精确 addr_id + cell_address 精确 + endswith("/" + cell_address)
  - 多候选 → ambiguous
  - PBT `tests/acnr/test_l3_no_cross_wp_hit.py` [P21]：D2 vs D2-2 不互相命中
  - **子代理自包含**：仅改 resolver.py Step 6 + 新建测试

- [x] 24. 前端 resolve 结果 LRU 缓存 [Req-20, P22]
  - 修改 `useAcnr.ts`：新增 `_resolveCache` Map + LRU 淘汰（max 200）
  - resolveFormula/resolveUri/resolveAddr/resolveIndex 调用前检查缓存
  - found=false 不缓存；epoch 变清空
  - vitest `tests/useAcnr_resolve_cache.spec.ts` [P22]
  - **子代理自包含**：仅改前端文件

- [x] 25. Phase 2 完整全量验证 [Req-13–20, P15–22]
  - 运行全部 `tests/acnr/` + 前端 vitest 确保 Phase 1 + Phase 2 全量回归零
  - 并发压测：httpx 50 并发 resolve 同 project → single-flight 生效 + instance memo 去重
  - Playwright：公式选址器批量搜索 20 格 → batchResolve 一次 HTTP + 第二次缓存命中无网络
  - Playwright：SSE 断连后 5s 自动重连 → 缓存被清
  - 更新 INDEX.md 状态
  - **前置**：Task 16–24 全部完成

## Phase 2 Task Dependency Graph

```json
{
  "waves": [
    {
      "id": "wave-p2a",
      "name": "Phase2 并行组A: 无依赖（最大并行度=4）",
      "tasks": [16, 17, 19, 22],
      "dependsOn": []
    },
    {
      "id": "wave-p2b",
      "name": "Phase2 并行组B: 前端批量+L3收紧+resolve缓存（依赖wave-p2a）",
      "tasks": [18, 23, 24],
      "dependsOn": ["wave-p2a"]
    },
    {
      "id": "wave-p2c",
      "name": "Phase2 并行组C: instance memo（依赖batch端点）",
      "tasks": [21],
      "dependsOn": ["wave-p2b"]
    },
    {
      "id": "wave-p2d",
      "name": "Phase2 中间验证",
      "tasks": [20],
      "dependsOn": ["wave-p2a", "wave-p2b"]
    },
    {
      "id": "wave-p2final",
      "name": "Phase2 最终验证",
      "tasks": [25],
      "dependsOn": ["wave-p2c", "wave-p2d"]
    }
  ]
}
```

**Phase 2 最大并行度 = 4**（Task 16/17/19/22 互不修改相同文件）

### 文件隔离矩阵 (Phase 2)

| 子代理 | 主要修改文件 | 不可同时运行 |
|--------|-------------|--------------|
| Task 16 | services/acnr/overlay.py | — |
| Task 17 | services/acnr/cache_epoch.py, main.py | — |
| Task 18 | useAcnr.ts, routers/acnr.py(batch端点) | Task 21（同改 resolver） |
| Task 19 | services/acnr/catalog_snapshot_gc.py | — |
| Task 20 | 无新文件（验证） | 前置完成后 |
| Task 21 | services/acnr/resolver.py | Task 23（同改 resolver） |
| Task 22 | useAcnr.ts（SSE 部分） | Task 24（同改 useAcnr） |
| Task 23 | services/acnr/resolver.py（Step 6） | Task 21 |
| Task 24 | useAcnr.ts（resolve 缓存） | Task 22 |
| Task 25 | 无新文件（全量验证） | 全部完成后 |
