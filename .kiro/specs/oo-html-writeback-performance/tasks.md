# OO/HTML 双向回写性能优化 — Tasks

现状实证补充：D4 契约模板字段 **180 个（无重复 stable_key）**；运行时 payload key 28431（=729 行×~39 字段实例化）。`build_projection` 每 payload key 调 `field_by_stable_key` 2 次 × 线性扫 180 = ~1000 万次比较 + `all_fields()` 反复重建 tuple → 30s。

## 批次 1：零风险缓存/数据结构（✅ 已实施，evidence/batch1-results.md）

- [x] 0. **ROI-0（真实探针复测发现的最大热点，21-27s/请求）**：`wp_sync_router._attach_pilot_adapters` 按已发布状态指纹（一次 entry_state 查询 + manifest 大小）进程级缓存 `AdapterRegistration`，命中重放 `register()`（全量重校验，跳过 186×2 DB 往返 + 观测器重跑）。
- [x] 1. 新建 `parse_cache.py`：线程安全有界 LRU（`OrderedDict + threading.Lock`）+ hit/miss 计数；单例 `BASELINE_EXTRACT_CACHE(64)` / `BEFORE_DIGEST_CACHE(128)` + `_REGISTRATION_CACHE(8)` in router。
- [x] 2. **ROI-5a**：`contracts.py::SyncContract` memoized `{stable_key:spec}` 索引（`setdefault` 保留首个），`field_by_stable_key` O(1)；对拍 180 字段 0 mismatch，未登记仍抛 `ContractSchemaError`。
- [x] 3. **ROI-5b**：`_materialize_request` 的 `build_projection` 包 `asyncio.to_thread`。
- [x] 4. **ROI-1**：`_overlay_with_published_substrate` 按 `{contract_id}:{artifact_sha256}` 缓存 baseline extract。
- [x] 5. **ROI-4**：`excel_extract.verify_unmanaged_regions` before 侧 digest 按 before 字节 sha256 + region/binding/extra 缓存；after 侧不缓存；D4-29 after-dependent before 自然 miss。
- [x] 6. 焦点回归：349 + 153 + 107 passed（bp61/d4-29/callback/task37/task38/router/pilot AST/callback_pg/room_service_pg）；零新增失败。
- [x] 7. 真实 PG 探针复测：store-projection 34s→0.05-0.07s / pending 21.7s→0.07s（据实见 evidence）。
- [x] 8. evidence 记录（evidence/batch1-results.md）。

## 批次 2：核心路径重构（`*` 可选，评估后决定，需充分回归）

- [ ] 9. * **ROI-2**：materialize/extract 多受管 sheet 循环合并为单簿一次 load、内存改完 save 一次；`_read_cell_view` 的 data_only True+False 合并为单次 load。保留主 binding 的 row_shift/propagation/identity inventory 语义（防 D4 169→253 drift）；structure_hash 仍来自最终 output（BP-30）。
- [ ] 10. * **ROI-3**：D4-29 `resolve_managed_sheet` 单请求内缓存解析结果，合并 `extract_file`→merge→`materialize_file` 的重复 load；保留手动 zip repack（保全无关部件）+ 隐藏锁定 identity carrier 行 + observer-同构 structure_hash。
- [ ] 11. * **ROI-6**：per-room 锁临界区只覆盖 fence+commit，CPU rematerialize 移锁外并在锁内重验产物；保持会话级锁 + finally 解锁 + 不动 lock_workpaper per-wp keying。
- [ ] 12. * 批次 2 全链路回归 + 真实 PG 探针 + 多人并发压测（若环境允许）。

## 实施顺序
批次 1 按 1→2→3→4→5→6→7→8。每条落地即跑相关回归，绿了再下一条。批次 2 待批次 1 复测收益后由用户拍板。
