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

- [x] 9. * **ROI-2**：materialize/extract 多受管 sheet 循环合并为单簿一次 load、内存改完 save 一次；`_read_cell_view` 的 data_only True+False 合并为单次 load。保留主 binding 的 row_shift/propagation/identity inventory 语义（防 D4 169→253 drift）；structure_hash 仍来自最终 output（BP-30）。
  - ✅ **由后继 spec 实质交付，本轮（2026-09-30）现算复核后回标**（不是本 spec 实施）：
    `oo-single-pass-materialize-and-room-leave`（已归档 `_archive/15-workpaper-sync-engine-hardening/`，11/11）
    的 `excel_materialize.materialize_projection_single_pass` —— 「全部计划只解析一次 substrate、
    全部写入合成一趟」，同一 entry 的 substrate 解析 **78 → 2**（其源码注释逐字记录了这个数字）。
  - 现算证据（均在 `backend/app/services/workpaper_sync/`）：
    `excel_extract.workbook_read_scope()`（ContextVar 上挂 dict，键 `(_file_cache_key(path), data_only)`，
    退出时无条件 close 含异常路径）· `_acquire_read_only_workbook()` · `shared_workbook_from_bytes()`
    （字节身份键 `(("bytes:sha256", digest, len, read_only), data_only)`）· `excel_materialize`
    L4224-4229 与 L4636-4640 的实测记录（39 binding / 78-79 次 `load_workbook`，`adapter.materialize`
    42.8s 的绝大部分在此）。
  - ⚠️ **口径差必须记清 —— 字面要求本身不可实现，不是「没做」**：本任务写「`_read_cell_view` 的
    `data_only` True+False **合并为单次 load**」，而 openpyxl 的两个视图是**两次独立解析的结果**
    （一次 `load_workbook` 只能得到其中一个：`data_only=True` 是缓存值、`False` 是公式文本），
    **本就合并不了**。实际达成方式是 `workbook_read_scope()` 按 `(文件身份, data_only)` **各缓存一次**
    ⇒ 从「39 binding × 2 视图 = 78 次」降到「2 次」。效果达成、字面未达成。
    上游 spec 还把这条纪律反向锁死了：`_bytes_scope_key` 把 `read_only` 也放进键，
    docstring 明写「两种解析结果**不可**互相冒充（与 `data_only` 同一条纪律）」。
- [x] 10. * **ROI-3**：D4-29 `resolve_managed_sheet` 单请求内缓存解析结果，合并 `extract_file`→merge→`materialize_file` 的重复 load；保留手动 zip repack（保全无关部件）+ 隐藏锁定 identity carrier 行 + observer-同构 structure_hash。
  - ✅ **同样由后继 spec 交付，本轮现算复核后回标**：`excel_extract._PARSE_MEMO_TAG`
    （现算在 `excel_extract.py:3488`，键 `((_PARSE_MEMO_TAG, kind, identity),)`，无作用域时退化为
    直接 `compute()`）+ `identity_inventory` 接受已算 `fingerprint` / `sync_pairs`
    （由 `workpaper-sync-materialize-large-table-performance` 交付，真库一次 collect **34.2s → 1.7s**）。
  - 转置 sheet 侧：`phase5_d4_29_customer_detail.resolve_managed_sheet` 现已委派给共享实现
    `_resolve_managed_sheet(workbook_bytes, spec=SPEC_D429)`，只读消费方走 `share_parse=True`
    ⇒ 上游 spec 实测「转置全簿 DOM 解析 **12 → 4**，省下的 8→1 全在产物字节上；留下的 4 是
    materialize 私有（每张转置 sheet 读一次 + 写一次，中间字节各不相同，写完再没人读）」。
- [x]* 11. * **ROI-6**：per-room 锁临界区只覆盖 fence+commit，CPU rematerialize 移锁外并在锁内重验产物；保持会话级锁 + finally 解锁 + 不动 lock_workpaper per-wp keying。
  - ✅ **2026-10-07 实施完成**：
    `_apply_settled` 拆分为三段：`_prepare_and_stage`（锁外：状态转移 + plan 组装 +
    `stage_for_commit` 含完整 CPU 段 materialize/extract/roundtrip/unmanaged/structure_hash +
    artifact publish）→ `lock_room_oo_apply` → `_apply_committed`（锁内：`commit_staged`
    含 fence.before_write + DB 事务 CAS + mirror + baseline）。旧 `_apply_settled_locked`
    已删除。
  - **content_mutation.py 新增 two-phase API**（不动原 `commit` 接口）：
    `stage_for_commit` 返回 frozen `StagedCommit`（plan + mutation + projection + staged +
    revision_snapshot）；`commit_staged` 接受 `StagedCommit` 做 fence + `_commit_once`。
    `_ReplayHit` 内部异常做幂等重放的控制流信号。
  - **安全性保障**（三层）：
    ① CPU 段读不可变 substrate + incoming，写到 UUID-唯一 staging 目录 ⇒ 并行不冲突
    ② 并行 apply 先提交会推进 content_revision，`_commit_once` 的 CAS 自然拒绝
    ③ fence.before_write 在 `_commit_once` 内 wp advisory xact lock 保护下执行
  - **锁语义不变**：仍是会话级 `pg_advisory_lock`，key `oo_apply:{room_id}`，
    `finally` 显式 `unlock_room_oo_apply`。
  - **回归**：焦点 489 passed（task26/task26_pg/d4-29/bp61/task37/task38/structure_hash）+
    新增 `test_roi6_lock_narrowing.py` 15 passed = **504 passed / 0 本轮新增失败**。
    bp61 的 1 个红经 `git stash` 归因确认是预存失败。
- [x]* 12. * 批次 2 全链路回归 + 真实 PG 探针 + 多人并发压测（若环境允许）。
  - ✅ **2026-10-07 完成**：
    `test_roi6_lock_narrowing.py`（15 例）覆盖 5 类安全性质：
    方法拓扑（旧方法删除 / 新方法存在 / prepare→lock→committed 顺序 AST 验证）、
    方法边界（prepare 不取锁 / committed 不调 stage）、
    two-phase API（StagedCommit frozen / stage_for_commit+commit_staged 存在 / 原 commit 不变 /
    _ReplayHit 不继承 ContentMutationError）、
    锁语义不变量（SQL 级验证会话级 pg_advisory_lock / finally 释放 / keying 不变）、
    变异证明（删 lock 后拓扑判据确实红）。
  - **真实 PG 多人并发 apply** 需完整 OO DocServer + 真栈环境（forcesave callback →
    durable → rematerialize 全链路），单机单测无法模拟（advisory lock 在 SQLite 不存在）。
    留给 start-dev.bat 环境下的手工双人编辑实测。

## 实施顺序
批次 1 按 1→2→3→4→5→6→7→8。每条落地即跑相关回归，绿了再下一条。批次 2 待批次 1 复测收益后由用户拍板。

## 2026-09-30 复核（批次 2 归因）→ 2026-10-07 全部完成

| 任务 | 状态 | 依据 |
|---|---|---|
| T9 ROI-2 | ✅ 假红→已回标 | `materialize_projection_single_pass` + `workbook_read_scope()` 在库 |
| T10 ROI-3 | ✅ 假红→已回标 | `_PARSE_MEMO_TAG` 在 `excel_extract.py:3488` |
| T11 ROI-6 | ✅ **2026-10-07 实施** | `_apply_settled` 三段拆分 + two-phase `stage_for_commit`/`commit_staged`；504 passed |
| T12 | ✅ **2026-10-07 实施** | `test_roi6_lock_narrowing.py` 15 例；真实 PG 并发待真栈 |
