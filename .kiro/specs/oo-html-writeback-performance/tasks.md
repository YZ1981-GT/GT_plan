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
- [ ]* 11. * **ROI-6**：per-room 锁临界区只覆盖 fence+commit，CPU rematerialize 移锁外并在锁内重验产物；保持会话级锁 + finally 解锁 + 不动 lock_workpaper per-wp keying。
  - 🔴 **真未做（2026-09-30 现算确认，与 T9/T10 的「假红」不同）**：
    `repository.lock_room_oo_apply` 仍是**会话级** `pg_advisory_lock(:ns, hashtext('oo_apply:{room_id}'))`，
    `oo_to_html.py:2462` 注释明写它「跨越下方 commit + rematerialize CPU」⇒ 多人同编同底稿仍串行排队。
  - **ROI 评估（按 spec 纪律，`*` 评估任务在动手前先给判断）**：
    - **收益仍在、未被批次 1 抹平**：批次 1 解决的是「单请求 34-46s → 0.05-0.07s」（只读端点的
      registry / baseline / 字段索引），**没动** apply 路径的 rematerialize CPU。后继 spec 把
      rematerialize 从 138.7s 降到 **69.33s**（软上限 120 未放宽），collect 34.2s → 1.7s ——
      **69s 量级的串行窗口依然存在**，多人同编同一底稿时第二个人仍要排队等完。
    - **改动面**：`oo_to_html.py`（3232 行）的 `_apply_settled` 临界区结构 + `_apply_settled_locked`
      拆分；不动 `repository.lock_room_oo_apply` 的 keying 与会话级语义。
    - **风险（这是不敢顺手做的真原因）**：那把锁的存在理由被注释点名 ——
      防并行 apply「在 fence 上互踩（G4-0d `result_bundle_identity_mismatch`）」。把 CPU 段移到锁外
      就必须在锁内**重验产物**，而「重验什么才算够」本身是一个需要设计的判据：漏一项就是
      间歇性的 bundle identity 错配，且它只在真并发下复现 —— 单测与单人真栈都测不出来。
    - **前置**：需要多人并发压测环境（T12），否则改完无法证明没引入间歇性错配。
  - ⇒ **维持未做，等用户拍板**。design §「锁临界区（ROI-6，可选，本批不做）」原话：
    「真要缩临界区（CPU 移锁外）需在锁内重验产物，风险高，本批不动，留 `*` 评估」；
    tasks.md 末尾原话：「批次 2 待批次 1 复测收益后由用户拍板」。本轮只补 ROI 评估，不擅自改
    并发正确性相关代码。
- [ ]* 12. * 批次 2 全链路回归 + 真实 PG 探针 + 多人并发压测（若环境允许）。
  - 卡外部依赖：多人并发压测需要并发客户端环境；且它是 T11 的**验收前置**（见上），
    T11 未拍板则本任务无对象。

## 实施顺序
批次 1 按 1→2→3→4→5→6→7→8。每条落地即跑相关回归，绿了再下一条。批次 2 待批次 1 复测收益后由用户拍板。

## 2026-09-30 复核（批次 2 归因）

现算三条批次 2 任务的真实状态，结论与 INDEX.md 既有登记一致：

| 任务 | 状态 | 依据 |
|---|---|---|
| T9 ROI-2 | **假红 → 已回标** | `materialize_projection_single_pass` + `workbook_read_scope()` 在库，substrate 解析 78→2；字面「两视图合并单次 load」不可实现（openpyxl 两视图是两次解析） |
| T10 ROI-3 | **假红 → 已回标** | `_PARSE_MEMO_TAG` 在 `excel_extract.py:3488`；转置 DOM 解析 12→4 |
| T11 ROI-6 | **真未做** | `lock_room_oo_apply` 仍会话级且跨 commit + rematerialize CPU；收益仍在（69s 串行窗口），但属并发正确性改动 ⇒ 待拍板 |
| T12 | **真未做** | 多人并发压测环境 + T11 前置 |

🔴 **这轮最该记住的一条**：T9/T10 是「交付物在库、清单没勾」的**假红**，而不是待办。
判定它们靠的**不是**读 tasks.md，而是去生产代码里现算符号是否存在
（`workbook_read_scope` / `_PARSE_MEMO_TAG` / `materialize_projection_single_pass`）。
若按清单直接开工，会把已经做完的事重做一遍，且很可能在核心路径上引入第二套 workbook 缓存
—— 那正是上游 spec 的 Requirement 2.2 明文禁止的（「不得新引入第二套 workbook 缓存：
模块级长存缓存会让 Windows 删不掉临时文件」）。
