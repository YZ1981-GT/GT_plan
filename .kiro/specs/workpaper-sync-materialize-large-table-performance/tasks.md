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
