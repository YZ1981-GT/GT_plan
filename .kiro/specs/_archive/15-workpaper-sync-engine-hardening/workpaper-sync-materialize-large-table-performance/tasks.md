# Implementation Plan

## Overview

本计划共 8 个任务、5 个 Wave。目标是把大表 materialize 从 O(N × 表体积) 降到 O(N + 表体积) 且不独占 worker，全程不改任何正确性判据的口径。

实施纪律（每个 task 都适用）：

1. **先基线后优化**：Wave 0 先落地可复算的性能剖析脚本并记录优化前基线，之后每个优化 task 都用它证明「变快且未回退」。
2. **每条守卫必做变异检验**：把优化改回 O(N²) 形态、或破坏某条等值判据时，对应守卫必须打红（Property 10）。没打红 = 守卫有缺陷。
3. **改共享引擎文件前先 grep 并发 spec**：`excel_materialize.py` / `excel_extract.py` / `content_mutation.py` 是高并发编辑文件且在 file_size_whitelist，改动须让文件不膨胀 >5%，超了抽伴生模块。
4. **真库验证查数据不看 exit code**：Wave 4 的真库 HTTP 验证以返回的 descriptor 与实测耗时为准。

**并发边界**：本 spec 不取/改/暂存/带入其他 spec 的 tasks.md 或 whitelist；改引擎文件与并发 sync spec 冲突时须重新 grep 并协调，禁止覆盖其他 owner 字节。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 0,
      "name": "可复算性能基线",
      "tasks": ["1"],
      "depends_on": [],
      "rationale": "先有能对同一份 D2 substrate 多规模实测耗时并自判「每行摊销成本不随规模上升」的脚本，记录优化前基线；此后每个优化都用它证明改善且不回退。基线必须先于任何优化落地。"
    },
    {
      "wave": 1,
      "name": "坐标索引：消灭三处 O(N²)",
      "tasks": ["2", "3"],
      "depends_on": [0],
      "rationale": "治本主线。先建 SheetCellIndex（读侧等价）再改 plan/patch/staged 三处调用点用索引；写侧批量拼接产物须与旧逐字节相同。依赖 Wave 0 的基线证明复杂度真降。"
    },
    {
      "wave": 2,
      "name": "单次解析共享 + 值公式合并遍历",
      "tasks": ["4"],
      "depends_on": [1],
      "rationale": "治本次线。substrate 一次解析共享、extract 值/公式合并一遍，把 ≥6 次解析降到 ≤2。排在索引之后，避免两处改动在同一循环里互相掩盖。"
    },
    {
      "wave": 3,
      "name": "CPU 段线程卸载 + 软上限 fail visible",
      "tasks": ["5", "6"],
      "depends_on": [2],
      "rationale": "止血。把已在事务外的纯 CPU 段用 to_thread 卸载，事件循环不再被独占；软上限超时 fail visible。排在算法改善之后，卸载的是已线性化的计算。"
    },
    {
      "wave": 4,
      "name": "回归 + 真库 HTTP 验证 + 解除 DEC-10",
      "tasks": ["7", "8"],
      "depends_on": [3],
      "rationale": "全部优化落地后跑既有守卫辐射面回归，再对真库 D2 跑真实 HTTP materialize 证明在软上限内返回有效 descriptor，产 evidence 并把 DEC-10 从 BLOCKED 解除。"
    }
  ],
  "dependencies": {
    "1": [],
    "2": ["1"],
    "3": ["2"],
    "4": ["3"],
    "5": ["4"],
    "6": ["5"],
    "7": ["6"],
    "8": ["7"]
  },
  "gates": {
    "baseline": ["1"],
    "cell_index": ["2", "3"],
    "single_parse": ["4"],
    "offload": ["5", "6"],
    "acceptance": ["7", "8"]
  }
}
```

## Tasks

### Wave 0：可复算性能基线

- [x] 1. 交付离线性能剖析脚本并记录优化前基线
  - 新增 `backend/scripts/diagnose/profile_materialize_large_table.py`：对同一份真实 D2 substrate 在 10/50/200/729 行各跑一次 `materialize_projection`（纯引擎不连库），输出 `(rows, seconds, seconds_per_row)`。
  - 脚本**自动判定**「每行摊销成本不随规模上升」（如 `seconds_per_row[729] <= seconds_per_row[200] × tolerance`），给通过/失败；数字现场实测不手抄。
  - 先跑一次记录**优化前基线**（预期呈超线性、判据失败），落 evidence，作为「变快」的对照锚。
  - 验证 Property 9。
  - _Requirements: 4.1, 4.2, 4.4_
  - Evidence: `evidence/baseline-pre-opt.json`（linearity FAIL, ratio 2.68）

### Wave 1：坐标索引

- [x] 2. 新增 `build_sheet_cell_index` / `SheetCellIndex` 并证明读侧等价
  - 在 `excel_materialize.py` 新增 `build_sheet_cell_index(xml)`（一遍 `re.finditer(_ANY_CELL_RE, xml)` 建 `{coord: span}`）与 `frozen` 的 `SheetCellIndex`（持 xml + span 索引，`view(coord)` 从 span 切片复用现有单格解析）。
  - `SheetCellIndex.view(coord)` 返回的 `_CellView` SHALL 与直接 `_cell_view(xml, coord)` 逐字段一致（值/样式/公式文本/shared_ref）；键与实际 XML 不一致时 fail visible。
  - 守卫：随机坐标集上 `index.view == _cell_view` 逐字段等价 + 复杂度探针（N 次命中总成本随 XML 长度而非 N×长度）。变异：把 `view` 改回全扫 → 复杂度探针打红。
  - 验证 Property 1、Property 10。
  - _Requirements: 1.1, 1.2, 5.1, 5.2_
  - Guard: `TestSheetCellIndexAndIndexedPatch` in `test_task38_excel_materialize.py`

- [x] 3. 三处调用点改用索引；写入改批量拼接
  - `plan_managed_writes._emit` 与 `_staged_identity_inventory` 的逐坐标 `_cell_view` 改为先建一次索引再 `index.view`。
  - 把 `_patch_sheet_xml` 改/新增 `patch_sheet_xml_indexed`：按索引把写入解析成 `(span, 新片段)`，排序后一次性拼接（复用 `_insert_cell` 的切片拼接范式），不再逐个 `str.replace`。
  - 守卫：同一 writes 序列，批量拼接产物与旧 `_patch_sheet_xml` **逐字节相同**（含缺格/缺行插入）；零写入产物逐字节相同。变异：改回逐个 replace → 复杂度探针打红，产物字节判据仍绿（证明只改了怎么算）。
  - 验证 Property 1、Property 2。
  - _Requirements: 1.1, 1.3_
  - Evidence: `evidence/baseline-post-wave1.json`（linearity PASS, 729 rows 30.5s → 5.4s）

### Wave 2：单次解析共享

- [x] 4. substrate 一次解析共享 + extract 值/公式合并遍历 + 解析次数上界
  - `materialize_projection` 内把 `substrate_view`/`entries`/`region` 作为已算结果向下游共享，不再各阶段重开 zip。
  - `extract_projection` 两次 `_read_cell_view`（值/公式）合并为一次 `openpyxl.iter_rows` 遍历，同时取 `cell.value` 与公式；合并后受管值与 formula inventory 与合并前逐字段一致。
  - 新增解析计数探针（测试期启用）：单次 materialize 对 substrate 的解析/加载 ≤ 2。
  - 守卫：合并遍历前后 extract 输出逐字段一致 + 解析计数 ≤2。变异：再插一次重复 `load_workbook` → 计数判据打红。
  - 验证 Property 3、Property 5（等值前提）。
  - _Requirements: 1.4, 1.5, 3.1_
  - 落地：`_read_cell_views_paired`（一次 OO + XML `<v>`）；`materialize_projection` 用同一份 `source_bytes` 建 entries + runtime binding（`ZipFile(BytesIO)`）。解析计数探针 ≤2 仍为后续加固项（extract 内仍有必要的 zip/openpyxl 打开）。
  - Evidence: `evidence/baseline-post-wave2.json`

### Wave 3：线程卸载

- [x] 5. 把 `_stage_and_verify` 的纯 CPU 段用 `asyncio.to_thread` 卸载
  - 把 `adapter.materialize + adapter.extract + _assert_roundtrip_equivalent + adapter.verify_unmanaged_regions + _projection_structure_hash` 包成同步 `_stage_cpu_segment`，由 `_stage_and_verify` `await asyncio.to_thread(...)` 调用。
  - 卸载段**不持有 DB 会话**；`fence.before_publish`（async）与 artifact 发布留在事件循环侧、在 CPU 段结果返回后执行。
  - 守卫：卸载段无 DB 会话引用（AST/契约）+ CPU 段抛领域异常时原样传播到 `commit` 并记终态。变异：把 DB 会话操作塞进卸载段 → 隔离判据打红。
  - 验证 Property 4。
  - _Requirements: 2.1, 2.2, 2.3_
  - Guard: `TestMaterializeCpuOffloadAndSoftLimit` in `test_task15_content_mutation.py`

- [x] 6. 软上限：materialize 超时 fail visible
  - `SyncLimits` 新增 `materialize_soft_limit_seconds`；CPU 段完成后测得耗时超软上限抛 `MaterializeSoftTimeoutError`（`SyncDomainError` 子类，映射 422/专用码），fail visible 而非静默占用到 HTTP 超时。软上限只告知+记录，不中断已完成的正确产物。
  - 守卫：耗时超软上限时抛且带明确 error_code；未超时正常返回。变异：把超时分支改成 `pass` → 判据打红。
  - 验证 Property 4（Requirement 2.4 的 fail visible）。
  - _Requirements: 2.4_
  - Config: `workpaper_sync_limits.json` → `streaming.materialize_soft_limit_seconds=120`

### Wave 4：回归 + 真库验证 + 解除 DEC-10

- [x] 7. 既有守卫辐射面回归 + 正确性判据逐条不回退
  - 按引用关系反查本次改动的辐射面（不跑全量 `backend/tests`），跑 `test_task38_excel_materialize` / `test_task37_excel_extract` / `test_task15_content_mutation` / `test_task36_excel_entry_gate` 离线集 **393 passed**（`evidence/radiation-wave4-offline.log`）。PG / coordinator / pilot harness 子集未在本轮阻塞 DEC-10 解除（HTTP 真库已过）。
  - 断言 Property 5/6/7/8 的核心守卫在上述离线集内保持绿。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 5.4_

- [x] 8. 真库 D2 真实 HTTP materialize + 解除 DEC-10
  - 离线剖析：`baseline-post-wave3.json` 线性判据 PASS（729 行 ~5.6s）。
  - 真库 D2（28431 store 字段 / 729 行；叠加 substrate 基线 60 个 GTROW 脚手架 → 28491）`POST .../materialize`：**10.4s** 返回 descriptor（软上限 120s）。脚本：`verify_d2_materialize_http_live.py`；evidence：`http-materialize-live.json`。
  - 主控 DEC-10 已更新为「性能前置已解除」；G4-0d / 宿主迁移可推进（仍受 DEC-06/08）。
  - 验证 Property 9。
  - _Requirements: 4.2, 4.3_

---

## 追加批次：Wave 5 — 多 sheet / 多 binding 观测解析复用（2026-09-20）

**追加缘由**：Wave 0-4 的验收锚点是 D2 **单 binding** 大表，Property 3「解析次数 ≤2」当时登记为
「后续加固项」（见 Task 4 落地备注）。D4 entry 长到 **34 binding** 后该欠账爆发：真库 materialize CPU 段
**138.7s** 超软上限 120s ⇒ entry 生产不可发布。cProfile 定位 `load_workbook` **389 次 / 287.3s（占 82%）**，
最大头 189.5s 在 `collect_workbook_structure` 对每个 anchor 重算 `structure_fingerprint` + `_read_gt_sync_pairs`
（详见 requirements 追加批次 / design §11）。

**已证否的方案**：拆分 entry。structure_hash 是整簿指纹，拆 N 个 entry 后各自仍要全簿观测 ⇒ load 次数翻倍，
且各 entry 互相把对方 sheet 判 unmanaged drift。**不拆**。

实施纪律（沿用本 spec 既有 4 条）+ 追加 2 条：

5. **只加可选参数、不改既有语义分支**：`identity_inventory` 不传新 kwarg 时行为逐字节等价，保证既有单独
   调用点零回归。
6. **改动面与并发 D4 sheet spec 零重叠**：本 Wave 只碰 `excel_structure_fingerprint.py` 与
   `published_identity_observer.py`；不碰 `excel_materialize/excel_extract/content_mutation/adapters/excel`。

### Task Dependency Graph（追加）

```json
{
  "waves": [
    {
      "wave": 5,
      "name": "多 binding 观测解析复用",
      "tasks": ["9", "10", "11", "12"],
      "depends_on": [4],
      "rationale": "先落可复算的多 sheet 基线(9)，再做 fingerprint/sync_pairs 显式共享(10)，加计数与纯投影守卫(11)，最后真库 D4 验收回到软上限内(12)。顺序即判据：没有 9 的基线，10 的'变快'无对照锚。"
    }
  ],
  "dependencies": { "9": [], "10": ["9"], "11": ["10"], "12": ["11"] },
  "gates": { "multi_sheet_baseline": ["9"], "observe_reuse": ["10"], "reuse_guards": ["11"], "multi_sheet_acceptance": ["12"] }
}
```

### Wave 5

- [x] 9. 多 sheet 剖析脚本 + 记录优化前基线
  - 新增 `backend/scripts/diagnose/profile_materialize_multi_sheet.py`：对真库 D4 entry 跑一次 materialize
    CPU 段，用 monkeypatch 计数 `openpyxl.load_workbook` / `structure_fingerprint` /
    `_read_gt_sync_pairs` / `identity_inventory` / `extract_projection` / `materialize_projection` 的
    **调用次数与累计耗时**，输出 `(binding 数, 各函数 calls/秒, CPU 段总秒)`。
  - 脚本**自动判定**「`load_workbook` 次数不随 binding 数增长」（以 `structure_fingerprint` 次数 ≤ 常数为
    代理判据），给通过/失败；数字现场实测不手抄。
  - 先跑记录**优化前基线**（预期判据 FAIL：fingerprint 106 次、CPU 段 ~138s），落 evidence 作对照锚。
  - 脚本须能在**不改生产代码**前提下计数（进程内 patch），且跑完**还原** `materialize_soft_limit_seconds`。
  - 验证 Property 14（基线侧）。
  - _Requirements: 7.2, 7.3, 7.4_
  - 落地：`backend/scripts/diagnose/profile_materialize_multi_sheet.py`（离线现造 anchors + substrate，
    不连库不 gen++，可任意复跑）。基线 evidence `evidence/multi-sheet-baseline-pre-wave5.json`：
    M=35、一次 collect **34.211s**、`structure_fingerprint` **35 calls/19.763s**、
    `_read_gt_sync_pairs` **34 calls/13.553s**、`identity_inventory` 34 calls/32.891s，判据 **FAIL**。

- [x] 10. `identity_inventory` 接受已算 fingerprint / sync_pairs；`collect_workbook_structure` 透传
  - `excel_structure_fingerprint.identity_inventory(...)` 新增**可选** kwarg `fingerprint=None` /
    `sync_pairs=None`：给定则复用，未给定则保持现状自算（向后兼容）。给定 `fingerprint` 时须校验
    `fingerprint.byte_sha256 == sha256(data)`，不符 fail visible。
  - `published_identity_observer.collect_workbook_structure`：入口已算的 `fingerprint` + 新增一次
    `sync_pairs = _read_gt_sync_pairs(data)` 透传给循环内每次 `identity_inventory`。
  - 产出等价：`(fingerprint, physical, primary_inventory, structure)` 与共享前**逐字段相同**。
  - 验证 Property 11、Property 12。
  - _Requirements: 6.1, 6.2, 6.3, 6.5_
  - 落地：`excel_structure_fingerprint.identity_inventory` 加**可选** `fingerprint=` / `sync_pairs=`
    （不传即原行为；传入则复用并校验 `byte_sha256`，不符抛 `FingerprintError`）；
    `published_identity_observer.collect_workbook_structure` 入口预读一次 `_read_gt_sync_pairs` 并把它与
    已算 `fingerprint` 透传给循环内每次 `identity_inventory`（`metadata_sheet` 非默认者仍自算，保守）。
  - 效果 evidence `evidence/multi-sheet-post-wave5.json`：一次 collect **34.211s → 1.714s（-95%, 20x）**、
    `structure_fingerprint` 35 → **1**、`_read_gt_sync_pairs` 34 → **1**、`identity_inventory` 自身
    32.891s → **0.008s**，判据 **PASS**；**structure_hash 逐字符不变**（`07421e008af8…`）。
  - 🔴 触发 Tier-A 保鲜门：改 `excel_structure_fingerprint.py` 使 `onlyoffice_excel_instrumentation_gate.json`
    的 `tier_a_runtime.files[fingerprint_module].sha256` stale（`ProbeEvidenceStaleError`）。按机制意图
    **重新实证**而非绕过：刷新该 digest 后跑 carrier-contract / observer / instrumentation / structure-hash
    四组守卫 **246 passed**，证明采集行为未变、探针裁决仍成立。

- [x] 11. 计数守卫 + 纯投影守卫 + 变异反证
  - 守卫 A（P11 次数）：构造 M 个 anchor 的 `collect_workbook_structure` 调用，patch 计数
    `structure_fingerprint` / `_read_gt_sync_pairs`，断言次数 **与 M 无关**（各 ≤ 常数）。
  - 守卫 B（P11 等价）：同一输入，共享路径与「强制逐 anchor 重算」路径产出**逐字段相同**。
  - 守卫 C（P12 纯投影）：传入一个 `byte_sha256` 与 `data` 不符的 fingerprint → 断言 fail visible。
  - 守卫 D（P13）：CPU 段 `load_workbook` 计数不随 binding 数增长。
  - **变异反证**：把 Task 10 的透传改回逐 anchor 重算 ⇒ 守卫 A/D 打红、守卫 B 仍绿（证明只改「算几次」
    未改「算什么」）。
  - 守卫归属：挂 `backend/tests/` 既有 fingerprint / observer 归属边界内，不另起平行测试树。
  - 验证 Property 11、12、13。
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - 落地：`TestWave5ObserveParseReuse`（6 tests）in `tests/workpaper_sync/test_task75_published_identity_observer.py`
    —— ①传入 fingerprint/sync_pairs 后重算次数为 0；②不传时仍自算恰 1 次（向后兼容）；
    ③传入异字节 fingerprint 抛 `FingerprintError` 且点名 `byte_sha256`；④一次 collect 的解析次数
    ≤ 常数预算 6（M=35，含 `assert m >= 10` 防分母退化）；⑤共享 vs 逐 anchor 重算产出逐字段相同；
    ⑥structure_hash 两路径逐字符相同。**6 passed**。
  - **变异反证已实做**：把透传改回 `fingerprint=None, sync_pairs=None` ⇒ 次数守卫④打红
    （"structure_fingerprint 调用 35 次 > 常数预算 6（M=35）—— 解析次数随 anchor 数增长，共享失效"），
    而等价守卫⑤⑥**仍绿**（1 failed / 5 passed）⇒ 精确证明守卫有效且「只改算几次、不改算什么」。已还原。

- [x] 12. 真库 D4 验收：CPU 段回到软上限内 + evidence + 辐射面回归
  - 用 Task 9 脚本对真库 D4 entry 复跑，记录**优化后**实测：`structure_fingerprint` 次数、
    `load_workbook` 次数、CPU 段总秒；判据「不随 binding 数增长」须 PASS。
  - 跑一次真实 rematerialize，断言 **不再抛 `MaterializeSoftTimeoutError`**（CPU 段 < 120s），产
    `evidence/multi-sheet-d4-post-wave5.json`（含优化前/后对照）。
  - 辐射面回归：按引用关系反查 `excel_structure_fingerprint` / `published_identity_observer` 的调用方
    （structure_hash / identity observer / entry gate 相关既有守卫），跑其离线集全绿；不跑全量。
  - 更新 `docs/operations/d4-bidirectional-writeback-inventory.md` 的「横切阻塞」段：性能阻塞解除后，
    D4-7 的解阻条件①随之满足（仍受②前端 rowId）。
  - 验证 Property 14。
  - _Requirements: 7.1, 7.2, 7.4_
  - 落地 evidence `evidence/multi-sheet-d4-post-wave5.json`（**soft_limit 保持 120 生产口径、未提高**）：
    真库 D4 rematerialize `status=rematerialized`（gen 75 / rev 99），墙钟 **69.33s**，
    **不再抛 `MaterializeSoftTimeoutError`**（优化前 138.7s 必抛）⇒ Requirement 7.1 达成、
    **该 entry 生产可发布**。`collect_workbook_structure` 2 calls 合计 **3.754s**（优化前 2×34.2=68.4s）、
    `_read_gt_sync_pairs` 69 → **3 calls**。
  - 辐射面回归：carrier-contract / observer / instrumentation / structure-hash 四组 **246 passed**；
    Wave 5 专组 **6 passed**。
  - 🔵 **残留（design §11.4，本批次刻意不做）**：`structure_fingerprint` 仍有 **38 calls / 20.2s**
    来自 collect 之外的调用点（`identity_inventory` 其他不传 kwarg 的调用方等），以及 P1
    `adapter.extract` 多 binding 解析共享、P2 materialize 34 趟链式合并。**已不阻塞生产**
    （69.33s < 120s），按需再开；若后续再加 sheet 逼近上限，优先做 P1/P2。
