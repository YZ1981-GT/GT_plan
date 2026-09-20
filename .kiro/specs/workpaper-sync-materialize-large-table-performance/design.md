# Design Document

## Overview

本设计把大表 materialize 从 **O(N × 表体积)** 降到 **O(N + 表体积)**，并把纯 CPU 段从事件循环卸载到工作线程，同时逐条保住既有正确性判据。它不改双向回写的语义与判据口径，只改「怎么算」。

三条改动彼此正交、可独立验证：

1. **坐标索引（治本，主）**：把 sheet XML 的「按坐标全扫」换成「单次建 `{coord: span}` 索引 + O(1) 命中」。消灭三处 O(N²)。
2. **单次解析共享（治本，次）**：一次 materialize 内 substrate 只解析一次，`substrate_view`/`entries`/`region` 向各阶段共享；extract 取值与取公式合并为一次工作簿遍历。把 ≥6 次解析降到 ≤2。
3. **线程卸载（止血，正交）**：把 `_stage_and_verify` 的纯 CPU 段（DB 事务之外）用 `asyncio.to_thread` 卸载，事件循环不再被独占。

算法改善（1、2）是根本；线程卸载（3）只是让「单次仍需的秒级计算」不阻塞其他请求，不替代算法改善。

---

## 2. 根因实证（context-gatherer 只读定位，带文件:行号）

所有优化点均来自实测定位，非推测：

### 2.1 三处 O(N²)（共同底层 `_cell_view`）

`excel_materialize._cell_view(xml, coord)`（`excel_materialize.py:817`）每次 `re.compile(_CELL_RE_TPL.format(coord=...)).search(xml)` 在**整份 sheet XML** 里找一个坐标，单次 O(XML 长度)。三处循环对它做 N 次调用：

- **A. `plan_managed_writes` 字段循环**：`_emit` 内 `view = _cell_view(xml, coord)`（`excel_materialize.py:1506`），被 `for identity in wanted: for spec in dynamic_table.fields: _emit(...)`（`:1560-1564`）调用 ≈ 行数 × 字段数 ≈ 28431 次 ⇒ O(字段数 × XML 长度)。
- **B. `_patch_sheet_xml` 写入循环**：`for write in writes:` 内 `view = _cell_view(xml, write.coord)`（`:931`）+ `xml = xml.replace(view.raw, new, 1)`（`:938`），每次全扫 + `str.replace` 重建整串 ⇒ 再一层 O(N²) 且常数更大。
- **C. `_staged_identity_inventory` 逐行循环**：`for row in region.row_span: view = _cell_view(xml, f"{uuid_column}{row}")`（`:2586-2588`）⇒ O(行数 × XML 长度)。

### 2.2 重复解析 ≥6 次

单次 `materialize_projection`（`:2438`）+ `_stage_and_verify`（`content_mutation.py:1527`）对同一工作簿解析/加载 ≥6 次：`extract_projection` 内两次 `openpyxl.load_workbook`（值/公式，`excel_extract.py:2178`/`:2185`）+ `_read_entries`（`:2482`）+ `read_runtime_binding_pairs`（`:2483`）+ `verify_unmanaged_regions` 的 before/after + `_projection_structure_hash` 的再 `read_bytes`（`content_mutation.py:1652`）+ `_staged_identity_inventory` 反读。彼此不复用。

### 2.3 同步阻塞

端点 `async def materialize`（`wp_sync_router.py:610`）→ `await coordinator.materialize`（`materialize_coordinator.py:1750`）→ `await self._mutations.commit`（`content_mutation.py:1026`）→ `_stage_and_verify`（`:1527`）内 `adapter.materialize/extract/verify_unmanaged_regions` 全是同步直调，无 `run_in_executor`/`to_thread`。计算期间独占 worker。

---

## 3. 改动一：坐标索引（消灭三处 O(N²)）

### 3.1 新增纯函数 `build_sheet_cell_index`

在 `excel_materialize.py` 新增：

```python
def build_sheet_cell_index(xml: str) -> "SheetCellIndex":
    """一遍 re.finditer(_ANY_CELL_RE, xml) 建 {coord: (start, end)} span 索引。O(表体积)。"""
```

`_ANY_CELL_RE`（`excel_materialize.py:273`）已能一遍捕获所有 `<c r="A1".../>` 与 `<c r="A1"...>...</c>` 的坐标（group 1/2 或 3/4）。索引一次遍历产出 `{coord: span}`，之后：

- **读**：`SheetCellIndex.view(coord)` 从 span 切出子串再走**现有** `_cell_view` 的解析逻辑（复用其正则解析单格，只是不再全扫定位）。返回的 `_CellView` 与直接 `_cell_view(xml, coord)` **逐字段一致**（Property 1 的等价判据）。
- **写**：见 3.2。

`SheetCellIndex` 是 `frozen` dataclass，持有 `xml` 与 `{coord: span}`，是该 `xml` 的**纯投影**（Requirement 5.1）—— 不与 openpyxl/zip 并存为第二真源。键与实际 XML 不一致（如切片解析失败）时 `view()` 抛（Requirement 5.2 / Property 10）。

### 3.2 写入改批量拼接 `patch_sheet_xml_indexed`

把 `_patch_sheet_xml`（`:924`）的逐个 `str.replace` 改为：先按索引把所有写入解析成 `(span, 新片段)`，按 span 排序后一次性拼接（现有 `_insert_cell` 里已有 `out.append` + 切片的成熟范式，`:962-971`）。缺格插入、缺行插入的**定位结果**与旧逐个 replace 逐字节相同（Property 2）。零写入时产物与旧逐字节相同。

### 3.3 `plan_managed_writes` 与 `_staged_identity_inventory` 改用索引

- `plan_managed_writes` 的 `_emit`：在进入字段循环前 `index = build_sheet_cell_index(xml)` 一次，`_emit` 内 `view = index.view(coord)` 取代 `_cell_view(xml, coord)`。
- `_staged_identity_inventory`：同样先建索引，逐行 `index.view(...)` O(1) 命中。

三处从 O(N × 表体积) 降到 O(N + 表体积)（Property 1）。

---

## 4. 改动二：单次解析共享

### 4.1 substrate 解析一次

`materialize_projection`（`:2438`）内 substrate 冻结不变。把 `extract_projection(substrate)` 产出的 `substrate_view`、`_read_entries(source_bytes)` 的 `entries`、`region` 作为**已算结果**在函数内向下游（`plan_managed_writes`、写盘、`verify`）共享，不再各自重开 zip。`plan_managed_writes` 已被标注纯函数（`:1346`），输入是不可变快照，天然可共享。

### 4.2 extract 取值/取公式合并一遍

`extract_projection` 里两次 `_read_cell_view`（`data_only=True` 值 / `data_only=False` 公式，`excel_extract.py:2178`/`:2185`）合并为一次 `openpyxl.iter_rows` 遍历，同时取 `cell.value` 与公式。合并后受管值与公式 inventory 与合并前逐字段一致（Property 3 + Property 5 的等值前提）。

### 4.3 解析次数上界断言

新增一个可选的**解析计数探针**（测试期启用）：materialize 内对 substrate 的解析/加载次数 ≤ 2。Property 3 用它把「有人又加了一次重复解析」打红。

---

## 5. 改动三：CPU 段线程卸载

### 5.1 卸载边界

`content_mutation._stage_and_verify`（`:1527`）的纯 CPU 段 = `adapter.materialize` + `adapter.extract` + `_assert_roundtrip_equivalent` + `adapter.verify_unmanaged_regions` + `_projection_structure_hash`。这一段**已在 DB 事务之外**（模块 docstring §三 + `commit` 步骤 4 明确 "全在事务外"）。把这整段包进一个同步内部函数 `_stage_cpu_segment(...)`，由 `_stage_and_verify` 用 `await asyncio.to_thread(_stage_cpu_segment, ...)` 调用。

### 5.2 事务隔离与异常传播

- 卸载段**不持有 DB 会话**：`stage_stream`/`publish_representation`/`stage_bytes`/`publish_projection` 是文件侧（artifact 仓储），`fence.before_publish` 是 async，留在事件循环侧（在 to_thread 段**之后**、拿到 CPU 段结果再 await），不进工作线程（Property 4 / Requirement 2.2）。
- CPU 段抛的领域异常穿过 `to_thread` 原样传播（`asyncio.to_thread` 保留异常），`commit` 的 `except Exception` 记终态后原样抛（Requirement 2.3 / Property 4）。

### 5.3 软上限 fail visible

新增配置 `materialize_soft_limit_seconds`（`SyncLimits`）。CPU 段完成后测得耗时超软上限时抛一个新领域错误 `MaterializeSoftTimeoutError`（`SyncDomainError` 子类，`http_status=422` 或专用码），fail visible 而非静默占用到 HTTP 层超时（Requirement 2.4）。软上限只做「告知 + 记录」，不中断已完成的正确产物。

---

## 6. 性能基线与验收（可复算）

### 6.1 离线剖析脚本

新增 `backend/scripts/diagnose/profile_materialize_large_table.py`：

- 对同一份真实 D2 substrate，在多个行规模（10 / 50 / 200 / 729）各跑一次 `materialize_projection`（纯引擎，不连库），测耗时。
- 输出每规模 `(rows, seconds, seconds_per_row)`，并**自动判定**「每行摊销成本不随规模上升」（如 `seconds_per_row[729] <= seconds_per_row[200] * tolerance`），给通过/失败。
- 数字现场实测，不手抄（Requirement 4.4 / Property 9）。改了实现没重跑 ⇒ 判据用新实测数据自证，过期数字无处藏。

### 6.2 真库 HTTP 验证（解除 DEC-10 的直接证据）

优化落地后，对真库 D2（28431 字段 / 729 行）跑一次真实 `POST .../materialize`，在软上限内返回有效 descriptor（Requirement 4.3）。这一步是 tasks 的收尾验收，产 evidence，作为把 DEC-10 从 BLOCKED 解除的凭证。

---

## 7. 选型与拒绝方案

**选型：三条全做。** ①②治本（去 O(N²) + 去重复解析），③止血（不阻塞 worker）。三者正交，可分 task 独立守卫。

拒绝的替代方案：

- **拒绝「整表 openpyxl 写回」**：openpyxl 全量重写实测在 K11 上丢 18 个 zip 部件、摊平 12 个共享公式组（`excel_materialize.py:1889-1897` 已有此判据），与零位移 zip 定点改写不兼容，且不解决 O(N²)（openpyxl 建整表对象本身开销更大）。
- **拒绝「换 lxml/C 解析器重写引擎」**：改动面波及整个 extract/materialize 链、破坏既有逐字节判据的可复算性，且根因是「重复全扫」不是「正则慢」——建索引即可，不需换栈。
- **拒绝「只加线程卸载不改算法」**：卸载让单请求不阻塞别人，但 729 行仍 59s（DEC-10 剖析值），单用户体验仍不可接受，且 O(N²) 在更大表上会继续恶化。卸载是止血不是治本。
- **拒绝「增量反读（只 extract 写过的格）替代整表 roundtrip」**：这会改变 Property 65 的口径（从「整表反读等值」变成「只验我写的格」），削弱对「写入副作用波及非目标格」的检测。本 spec 明确不改判据口径（Requirement 3），故 roundtrip 仍整表反读，只把整表反读本身的解析成本降下来（改动二）。

---

## 8. 不可变输入 / 输出（语义等价）

优化前后，materialize 的契约不变：

- **输入**：`projection`（受管字段值 + 行集）、`substrate`（冻结的 published representation 字节）、`contract`、`binding`、`definitions`。
- **输出**：`ExcelMaterializeOutcome`（`MaterializeResult` 含 `artifact_sha256` / `structure_hash` / `identity_inventory_sha256` / `row_shift` / `total_formula_rows` / `workbook_row_change` / `managed_field_count`）+ staged/published artifact + projection artifact + descriptor。

对同一组输入，优化后产出的 `artifact_sha256`（写盘字节）SHALL 与优化前逐字节相同（这是 Property 2/8 的最强判据：产物字节不变）。耗时下降是唯一可观察差异。

---

## 9. Property → 实现映射

| Property | 实现落点 | 守卫（复用既有 + 新增判据） |
|---|---|---|
| P1 坐标定位 O(1) | `build_sheet_cell_index` / `SheetCellIndex.view` | `test_task38_excel_materialize`：index.view 与 `_cell_view` 逐字段一致 + 复杂度探针 |
| P2 写入批量拼接等价 | `patch_sheet_xml_indexed` | `test_task38`：同一 writes 序列产物与旧 `_patch_sheet_xml` 逐字节相同 |
| P3 解析次数 ≤2 / 值公式一遍 | 4.1 / 4.2 + 解析计数探针 | `test_task37_excel_extract`：合并遍历值/公式一致 + 计数 ≤2 |
| P4 线程卸载 + 事务隔离 | `_stage_cpu_segment` + `to_thread` | `test_task15_content_mutation`：卸载段无 DB 会话 + 异常原样传播 |
| P5 roundtrip / 未管理区域 | 不改判据，仅提速 | `test_task38` / `test_task15` 既有等值判据 |
| P6 structure_hash / inventory | 不改判据 | `test_task38` / `test_task25` 既有判据 |
| P7 单事务 / revision+1 | 不改 commit 边界 | `test_task15` / `test_task25` 既有 `assert_revision_delta` |
| P8 阶段顺序 / 零位移逐字节 | 改动仅在读写实现，阶段顺序不动 | `test_task38`：`row_shift is None` 产物逐字节相同 + 插行阶段顺序 |
| P9 性能基线自证 | `profile_materialize_large_table.py` | 脚本自判 + 变异（改回 O(N²) 使判据失败） |
| P10 单一真源 + 变异反证 | `SheetCellIndex` 是 xml 纯投影 | 变异脚本：改回全扫 / 破坏等值 → 对应守卫打红 |

---

## 10. 影响面与边界

- **改动文件**：`excel_materialize.py`（索引 + 批量拼接 + 共享 + 卸载段的 CPU 部分）、`excel_extract.py`（值/公式合并遍历）、`content_mutation.py`（`_stage_and_verify` 卸载边界）、`materialize_coordinator.py`（若卸载边界需上移则涉及，优先不动）。这些文件**已在 file_size_whitelist**（closure spec 债务批），改动须让文件不膨胀 >5%，超了就抽伴生模块。
- **不改**：双向回写语义、正确性判据口径、DB schema、前端、manifest/registry、其他 owner 的文件。
- **前置关系**：本 spec 完成是 `workpaper-html-onlyoffice-bidirectional-writeback-closure` 的 G4-0d（D2 真实 OO 往返）与 DEC-10 解除的前置。
- **验证纪律**：每条守卫必做变异检验（改一字看是否变红）；真库验证查数据不看 exit code；改共享引擎文件前 grep 并发 spec 是否也在改。

---

## 11. 追加批次设计：多 sheet / 多 binding 的观测解析复用（Wave 5，2026-09-20）

### 11.1 为什么原 Wave 2「单次解析共享」没覆盖到这里

原 §4.1 的共享只作用在 `materialize_projection` **函数内**（substrate_view / entries / region 向下游共享），
改动清单是 `excel_materialize.py` / `excel_extract.py` / `content_mutation.py`。而 138s 的最大头
（189.5s of 350s profiled）落在**另外两个文件**：

- `app/services/workpaper_sync/published_identity_observer.py:1357` `collect_workbook_structure`
- `app/services/excel_structure_fingerprint.py:539` `_read_gt_sync_pairs` / `:560` `identity_inventory`

它们在原 spec 立项时不在视野内（当时验收锚点 D2 只有 1 个 binding，M=1 时该重复不可见）。D4 把 M 拉到 34，
重复放大 34 倍后才显形。**这是同一类根因（已算结果未共享）在新维度的复现，故 append 本 spec 而非新立。**

### 11.2 根因链（实测，带文件:行号）

```
content_mutation._projection_structure_hash                        2 calls / 189.5s
└ publish_time_structure_hash.compute_structure_hash_from_artifact
  └ published_identity_observer.collect_workbook_structure (:1357)
    ├ structure_fingerprint(data)                     ← 入口算 1 次
    └ for anchor in sheet_anchors:                    ← 34 个 anchor（每 binding 一个）
        identity_inventory(data, ...) (fingerprint.py:560)
        ├ fp = structure_fingerprint(data)            ← 🔴 每 anchor 又全簿 load 一次
        └ _read_gt_sync_pairs(data) (:539)            ← 🔴 每 anchor 又全簿 load 一次
```

实测次数 `structure_fingerprint=106` / `identity_inventory=69` / `_read_gt_sync_pairs=69`，与
`1 + 34 + 34` 及 `collect_workbook_structure` 被调 2 次的组合吻合。

**关键性质：`data` 是同一份不变字节**（staged 产物已写盘冻结）。所以这是纯粹的"算了 69 遍同一个纯函数"。

### 11.3 改动：把已算 fingerprint / sync pairs 显式下传（不引缓存状态）

**选型：显式传参共享**，而非进程内 memo 缓存。

| 方案 | 取 | 舍 |
|---|---|---|
| **A. 显式传参（选中）** | 无缓存状态、无内存增长、无陈旧风险；纯函数性与 Property 10/12「不引入可漂移第二真源」天然相容；与原 §4.1 共享范式同构 | 需扩 `identity_inventory` 签名（加**可选** kwarg，向后兼容） |
| B. 按 sha256 memo 缓存 | 调用方零改动 | 引入进程内可变状态 + 内存增长 + 跨请求陈旧风险；与 Property 10 的"不得并存为第二真源"需额外论证 |

具体改动（**两个文件、各一处，改动面极小**）：

1. `excel_structure_fingerprint.identity_inventory(data, *, ..., fingerprint=None, sync_pairs=None)`
   —— 新增两个**可选** kwarg：
   - `fingerprint is None` → 保持现状自算（既有单独调用点零回归）；
   - `fingerprint` 给定 → 复用之，并**校验 `fingerprint.byte_sha256 == sha256(data)`**，不符即 fail visible
     （Property 12）。
   - `sync_pairs` 同理（给定即复用，不再 `_read_gt_sync_pairs(data)`）。
2. `published_identity_observer.collect_workbook_structure` —— 入口已有 `fingerprint = structure_fingerprint(data)`，
   再算**一次** `sync_pairs = _read_gt_sync_pairs(data)`，然后把两者透传给循环内每次
   `identity_inventory(data, ..., fingerprint=fingerprint, sync_pairs=sync_pairs)`。

效果：`structure_fingerprint` 106 → **2**（两次 collect 各 1 次）；`_read_gt_sync_pairs` 69 → **2**。
189.5s(profiled) → ~1.5s。按 profile overhead 折算（350s profiled ↔ 138s 真实，≈2.53x），真实侧约
**-74s ⇒ 138s → ~65s**，已回到 120s 软上限内（Requirement 7.1 达成）。

### 11.4 后续可选加固（本批次不做，按需再开）

实测第二/第三大头，**修完 11.3 若已满足软上限则不动**（避免动高风险结构）：

- **P1 `adapter.extract` 的多 binding 解析共享**（`extract_projection` 102 calls / `_read_cell_view` 204 calls
  / 84.5s profiled）：roundtrip 校验对**同一份 staged 字节**做 M 次 extract，可共享一次 openpyxl 解析。
- **P2 materialize 34 趟链式 → 单趟多 binding**（`materialize_projection` 34 calls / 79.9s profiled）：
  `adapters/excel.py:363-405` 现为「每 binding 一趟、上一趟输出作下一趟输入」的串行链，每趟各自整册
  读/解压/重压/写。合并为「一次读 → 各 binding 各算 plan → 合并 CellWrite → 一次写」可再降一个量级，
  但须正确处理同 sheet 多区插行的行号偏移与 per-binding footer/identity 校验，**风险最高，单独立 task 再评估**。

### 11.5 Property → 实现映射（追加）

| Property | 实现落点 | 守卫 |
|---|---|---|
| P11 观测解析次数与 anchor 数无关 | `collect_workbook_structure` 透传 + `identity_inventory` 复用 | 新增：计数探针（monkeypatch 计数）`structure_fingerprint`/`_read_gt_sync_pairs` 调用次数与 M 无关 + 共享前后产出逐字段相同；变异：改回逐 anchor 重算 → 次数判据打红、等价判据仍绿 |
| P12 共享结果是纯投影 | `identity_inventory` 校验 `byte_sha256` | 新增：传入错 fingerprint（改字节）→ fail visible |
| P13 同字节 load 次数与 M 无关 | 11.3 合计效果 | 新增：CPU 段 `load_workbook` 计数探针，次数不随 M 增长 |
| P14 D4 软上限内 + 基线自证 | 真库 rematerialize + 剖析脚本 | 新增 `profile_materialize_multi_sheet.py`：实测 CPU 段耗时 + load 次数，自判 |

### 11.6 影响面与边界（追加）

- **改动文件**：`app/services/excel_structure_fingerprint.py`（+2 可选 kwarg & 复用分支）、
  `app/services/workpaper_sync/published_identity_observer.py`（+1 次 sync_pairs 预读 & 透传）。
  两处均为**加可选参数 + 复用已算值**，不删不改既有语义分支，既有单独调用点（不传 kwarg）逐字节等价。
- **不动**：`excel_materialize.py` / `excel_extract.py` / `content_mutation.py` / `adapters/excel.py`
  （11.4 的 P1/P2 才涉及，本批次不碰）⇒ 与并发 D4 sheet spec 的改动面**零重叠**。
- **不动判据**：`assert_no_structure_drift`、`observe_structure_inventory`、`parse_identity_inventory`
  的输入输出与调用顺序不变。
