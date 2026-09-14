# OO/HTML 双向回写性能优化 — Requirements

## 背景与问题陈述

OnlyOffice ↔ HTML 双向回写的三个核心端点单次请求耗时极慢（真实后端 SLOW_REQUEST 日志实测）：

| 端点 | 实测耗时 | 性质 |
|------|---------|------|
| `GET .../store-projection` | 37–46s | 只读端点，喂编辑器 |
| `POST .../pending-mutations` | 24–33s | 只暂存不推 revision |
| `POST .../materialize` | 23–99s | 生成 OO 产物（超线性 O(n²)） |
| OO apply（callback→durable→rematerialize） | 与 materialize 同量级 | 回读闭环 |

对多人平台这是致命的：`lock_room_oo_apply` 是**会话级 per-room 锁，横跨整个 23–99s 的 CPU 段**，同一底稿多人编辑时全部串行排队等待。

### 已定位的根因（context-gatherer + 现状 grep 实证）

1. **整簿重复解析**：三个端点每次都用 openpyxl 把整本 46-sheet 大工作簿（`xlsx/gt-d4-operating-revenue`，28431 字段/729 行级别）完整解析多遍。openpyxl 的 `load_workbook` 成本按**整簿所有 sheet 所有 cell** 计，与实际只碰的受管小区无关。
   - store-projection：`_overlay_with_published_substrate` 每次 `adapter.extract` 整簿（2–3 次全量 load），**且无缓存**，而 store 本身只是 checklist_responses 里的 JSON（取出毫秒级）。
   - materialize：≥3 次全量解析（materialize 内部 + roundtrip extract + verify before/after），D4-29 转置手术叠加后实测 8–10 次全量 load/save。
2. **`SyncContract.field_by_stable_key` 是 O(n) 线性扫描**（`contracts.py:720-723`，且每次重建 `all_fields()` tuple）。`endpoint_payloads.build_projection` 对每个字段调它 2 次 → 28431 字段 → **O(字段²)**，这是 pending-mutations 30s 的来源。且 `build_projection` **跑在事件循环上未 offload**，一个人 materialize 时所有人的轻量轮询端点被连累到数秒级。
3. **verify 的 before 侧 digest 是不变量却每次重算**：`before` 是已发布 substrate 在已知 revision 的字节，恒定，却在每次 materialize 都重新逐 part 字节 digest 整簿。

## 核心约束（不可违反）

### 约束 1：绝不砍任何正确性校验
性能优化**只做**：加缓存、挪线程池、换数据结构（O(n) → O(1)）、单簿单次 load。**绝不**削弱以下任何一项：
- roundtrip 等值校验（`_assert_roundtrip_equivalent`）
- 未管理区域漂移校验（`verify_unmanaged_regions` / `unmanaged_region_digest` 的逐 part 比对与 `zf.namelist()` 完整性扫描）
- structure_hash（发布时刻公式，`_projection_structure_hash` 必须来自最终 output，BP-30）
- identity carrier 校验（`_GT_SYNC` runtime binding、identity inventory 保留门）
- final authorization fence（contributor snapshot / initiator / bundle identity）
- `value_type`/`mode` 只从 contract 取（AC 6.1/6.5，protected 字段不得变可写）

### 约束 2：缓存正确性 = 键必须覆盖全部可变输入
- baseline extract 缓存键必须能被 substrate 的任何变化失效。已实证：substrate representation 只在 `content_revision` 变化时才变（业务应用 CAS `+1`，`repository.py:277`；纯定义升级不推进 revision）。故键含 `(wp_id, content_revision, entry_id)`。
- before-digest 缓存键必须能被 substrate 字节变化失效。用 substrate 文件的 sha256（内容寻址）作键，字节一变键就变。
- 缓存**只存不可变的解析产物**（extract 出的 Projection / digest），绝不缓存跨请求的可变状态。

### 约束 3：进程内 LRU + revision key（用户拍板的方案）
- 进程内 LRU 缓存（本地优先轻量方案），不引入 Redis。
- 多 worker 不共享缓存 = 可接受（每 worker 首次冷、后续热；正确性不依赖共享）。
- 重启失效 = 可接受（缓存是纯派生数据，冷启动重算即可）。
- 缓存必须有上限（LRU 淘汰），不得无界增长导致内存泄漏。

### 约束 4：行为等价
优化前后，所有现有测试必须全绿；三个端点的**返回值逐字节等价**（缓存命中与否结果一致）。

## 需求

### 需求 1：store-projection 只读端点秒级返回（ROI-1）
**用户故事**：作为审计人员，点击"在线编辑"后应在 1-2 秒内看到编辑器，而不是等 40 秒。

#### 验收标准
1. WHEN 同一 wp 的 substrate 在 `content_revision` 未变期间被重复请求 store-projection，THEN baseline extract 命中进程内缓存，端点耗时从 37–46s 降到 <2s。
2. WHEN `content_revision` 推进（一次业务应用），THEN 缓存键随之变化，下次请求重新 extract（不返回陈旧 baseline）。
3. 缓存 miss（首次/revision 变更后）的耗时不劣于当前（不引入额外解析）。
4. 返回值与未缓存时逐字节一致（约束 4）。

### 需求 2：pending-mutations 去 O(n²) + 不阻塞事件循环（ROI-5）
**用户故事**：作为多人协作用户，一个人暂存改动时，其他人的界面轮询不应卡顿数秒。

#### 验收标准
1. WHEN `build_projection` 处理 28431 字段的 payload，THEN `field_by_stable_key` 为 O(1) dict 查找（不再 O(字段²)），pending-mutations 从 24–33s 降到个位数秒。
2. WHEN `build_projection` + canonical 序列化在跑，THEN 它在线程池执行（`asyncio.to_thread`），不阻塞事件循环；并发的轻量轮询端点（active-job / notifications）不被连累。
3. `field_by_stable_key` 找不到 key 时仍抛 `ContractSchemaError`（行为不变）。
4. `value_type`/`mode` 仍只从 contract 取（约束 1）。

### 需求 3：materialize 的 verify before 侧缓存（ROI-4）
**用户故事**：作为审计人员，强制保存回读应尽快完成。

#### 验收标准
1. WHEN 同一 substrate（相同 sha256）被多次 materialize 的 verify 用作 before 侧，THEN before digest 命中缓存，不重复逐 part 整簿 digest。
2. after 侧 digest 每次照常重算（它是本次产物，必变）。
3. 未管理区域漂移检测的判定结果与未缓存时完全一致（约束 1：only 避免重算不变量，不弱化比较）。

### 需求 4（可选，`*`）：单簿单次 load + 缩小 per-room 锁临界区（ROI-2/3/6）
**用户故事**：作为多人平台，同一底稿多人 apply 不应互相排队几十秒。

#### 验收标准（评估后决定是否做）
1. `*` materialize/extract 的多受管 sheet 循环合并为单簿一次 load、内存改完 save 一次。
2. `*` D4-29 转置手术减少冗余 load+repack 次数（`resolve_managed_sheet` 单请求内缓存解析结果）。
3. `*` per-room 锁临界区只覆盖 fence + commit，纯 CPU rematerialize 移到锁外（须在锁内重验产物）。
4. 这些改动动 materialize/apply 核心路径，**必须**充分回归 + 真实 PG 探针复测，风险高，ROI 评估后再决定实施范围。

## 非目标
- 不引入 Redis / 外部缓存中间件。
- 不改 OnlyOffice DocServer 本身的行为。
- 不改数据流语义、不改 API 契约、不改前端。
- 不解决 DocServer forcesave 在 dev 容器不回调的环境问题（正交）。
