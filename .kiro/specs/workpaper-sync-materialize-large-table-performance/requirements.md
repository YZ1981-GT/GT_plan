# Requirements Document

## Introduction

本 spec 解决 DEC-10 登记的阻塞：底稿 HTML→OnlyOffice 双向回写的 **materialize（把 projection 写进 substrate 副本并反读校验）在大表上超线性慢且同步阻塞 worker**。它是 D2 canary 真实 OnlyOffice 往返（`workpaper-html-onlyoffice-bidirectional-writeback-closure` 的 G4-0d / Phase 4）的**硬前置**：在 materialize 能在可接受时间内完成、且不独占 worker 之前，D2 的在线编辑会 >5min 并 wedge worker，比 legacy 旁路更差。

### 实测基线（本 spec 的事实依据，非估算）

- D2 底稿 28431 字段 / 729 行，走统一 materialize 时 HTTP **>300s 超时**且 CPU-bound。
- 离线剖析 `push_html_to_excel`：10 行 6.7s / 50 行 8.8s / 200 行 15.9s / 729 行 59.3s —— 每行成本随规模翻倍，呈超线性（≈O(n²)）。
- 根因（`context-gatherer` 只读定位，带文件:行号，见 design §2）：
  - **三处 O(N²)**：共同底层 `excel_materialize._cell_view()` 每次在整份 sheet XML 字符串上 `re.search` 一个坐标；被 `plan_managed_writes` 的字段循环（≈28431 次）、`_patch_sheet_xml` 的写入循环（每次 `str.replace` 重建整串）、`_staged_identity_inventory` 的逐行循环各调用 N 次。
  - **重复解析**：单次 materialize 对同一工作簿解析/加载 ≥6 次（`extract_projection` 内两次 `openpyxl.load_workbook` 取值/取公式 + `_read_entries` + `verify_unmanaged_regions` 的 before/after + `structure_hash` 的再 `read_bytes` + staged 反读），彼此不复用解析结果。
  - **同步阻塞**：整条 materialize+extract+verify+hash 是纯 CPU 同步代码，直接在 async 事件循环里 `await`，没有 `run_in_executor` / `asyncio.to_thread` 卸载 ⇒ 计算期间独占 worker。

### 本 spec 的边界（明确不做）

- **不改任何正确性判据的口径**：roundtrip 等值、未管理区域不漂移、structure_hash 同构、identity inventory 实测、单事务/单 commit/revision+1 全部保持不变。优化只改「怎么算」，不改「算什么」与「判什么」。
- **不改双向回写的语义**：materialize 的输入（projection + substrate + contract）与输出（staged representation + projection artifact + descriptor）逐字节等价，仅耗时下降。
- **不做真实 OnlyOffice 往返**：那是 closure spec 的 G4-0d；本 spec 只把它的性能前置扫清。
- **不引入新的第二真源**：坐标索引、缓存都是同一份 substrate/artifact 字节的**投影**，不得成为与 openpyxl/zip 解析并行的第二套结构真源。

---

## Requirements

### Requirement 1：大表 materialize 的复杂度回到线性

**User Story:** 作为审计助理，我在编辑 D2 这种 700+ 行的大底稿并触发 HTML→OO materialize 时，希望它在可接受时间内完成，而不是超时。

#### Acceptance Criteria

1. WHEN 一次 materialize 处理 N 个受管字段 / R 行 THEN 系统 SHALL 使坐标定位、写入、staged 反读三段的总复杂度为 O(N + R + 表体积)，不再是 O(N × 表体积)。
2. WHEN sheet XML 已被解析为坐标索引一次 THEN 后续对任一坐标的读/写 SHALL 按索引 O(1) 命中，不再对整份 XML 重新 `re.search`。
3. WHEN 写入 N 个受管格 THEN 系统 SHALL 一次性按位置拼接产出新 XML，不得对每个写入各做一次 `str.replace` 重建整串。
4. WHEN 同一份 substrate 在单次 materialize 内被多个阶段消费 THEN 系统 SHALL 只解析/加载它一次并向各阶段共享结果，重复解析次数从 ≥6 降到 ≤2（读入 + 写盘后一次 staged 反读）。
5. WHERE extract 需要同时取受管格的值与公式文本 THE 系统 SHALL 用一次工作簿遍历取回两者，不得为值与公式各 `load_workbook` 一遍。

### Requirement 2：materialize 不得独占 worker

**User Story:** 作为平台，当一个大表 materialize 在跑时，我不希望它阻塞同 worker 上其他用户的请求。

#### Acceptance Criteria

1. WHEN materialize 的纯 CPU 段（materialize + extract 反读 + verify + structure_hash）执行时 THEN 系统 SHALL 在工作线程（`asyncio.to_thread` 或等价 executor）里运行它，使事件循环可继续处理其他请求。
2. WHERE CPU 段被卸载到工作线程 THE 系统 SHALL 保持它在 DB 事务之外（与现状一致），卸载边界不得把任何 DB 会话操作带入工作线程。
3. WHEN CPU 段在工作线程抛出领域异常 THEN 系统 SHALL 原样传播该异常到调用方并记终态，不得因跨线程而降级或吞掉。
4. IF materialize 单次耗时仍超过配置的软上限 THEN 系统 SHALL 以明确的领域错误 fail visible，而不是静默继续占用 worker 直到 HTTP 层超时。

### Requirement 3：正确性判据逐条不回退

**User Story:** 作为质量控制复核合伙人，我要求性能优化绝不牺牲双向回写的任何正确性保证。

#### Acceptance Criteria

1. WHEN 优化后的 materialize 完成 THEN 反读 roundtrip 等值判据（intended projection == extracted，按现有 `values_equal` 口径）SHALL 仍逐字段成立。
2. WHEN 优化后的 materialize 完成 THEN 未管理区域比对 SHALL 仍以来自同一 `plan` 的 `row_shift` / `total_formula_rows` / `propagation` 声明值判等价，不得改从产物 diff 事后推断。
3. WHEN 优化后的 materialize 完成 THEN projection lane 的 `structure_hash` SHALL 仍与请求时刻观测器（`compute_structure_hash_from_artifact`）算得同一个量，且 fence 与 representation 收到同一值。
4. WHEN 优化后的 materialize 完成 THEN staged identity inventory SHALL 仍由**实测** staged 产物得出（证明 minted UUID 真落盘），不得改为由 substrate inventory 加 minted 集合推导。
5. WHEN 优化后的 commit 完成 THEN 单事务 / 单 business commit / `revision` 恰 +1 的记账判据 SHALL 仍成立。
6. WHERE 存在结构性插行（`row_shift is not None`）THE 优化 SHALL 保持位移→Table ref 增长→引用侧传播→`_GT_SYNC` 重冻结→写格的阶段顺序不变。
7. WHERE 本次没有插行（`row_shift is None`）THE 优化后的 zip 定点改写路径 SHALL 与优化前逐字节相同（不解析 Table part、不传播、不重冻结）。

### Requirement 4：可复算的性能基线与验收判据

**User Story:** 作为现场经理，我要求「变快了」是可复算的实测事实，不是感觉。

#### Acceptance Criteria

1. WHEN 需要证明复杂度改善 THEN 系统 SHALL 提供一个可复跑的离线剖析脚本，对同一份 D2 substrate 在多个行规模（如 10 / 50 / 200 / 729 行）测 materialize 耗时并输出每规模耗时。
2. WHEN 剖析在多个行规模上运行 THEN 每行摊销成本 SHALL 不随规模上升（线性或更好），且该判据由脚本按实测数据自动判定并给出通过/失败。
3. WHEN 优化落地后在真库对 D2（28431 字段 / 729 行）跑一次真实 HTTP materialize THEN 它 SHALL 在配置的软上限内完成且返回有效 descriptor，作为解除 DEC-10 的直接证据。
4. WHERE 性能基线以数字形式记录 THE 这些数字 SHALL 由脚本现场实测得出，不得手抄常量；改了实现没重跑就过期的数字要能被判据打红。

### Requirement 5：优化不引入第二真源，且受变异检验

**User Story:** 作为 EQCR 技术复核人，我要求优化引入的索引/缓存不会成为与真实解析漂移的第二套结构真源。

#### Acceptance Criteria

1. WHERE 引入坐标索引或 substrate 解析缓存 THE 它 SHALL 是同一份 substrate/artifact 字节的纯投影，由该字节单次解析派生，不得与 openpyxl/zip 的解析结果并存为两套可漂移的真源。
2. WHEN 索引/缓存的键（坐标、sheet part、行号）与真实解析不一致 THEN 系统 SHALL fail visible，不得按索引静默返回错值。
3. WHEN 为每条正确性判据（Requirement 3）与复杂度判据（Requirement 1）编写守卫 THEN 每条守卫 SHALL 附一个变异反证：把优化改回 O(N²) 形态、或破坏某条等值判据时，对应守卫必须打红。
4. WHERE 优化改动落在既有引擎文件（`excel_materialize.py` / `excel_extract.py` / `content_mutation.py`）THE 改动 SHALL 复用现有守卫测试（`test_task38` / `test_task37` / `test_task15` / `test_task25`），新增判据挂在这些文件的既有归属边界内，不另起平行测试。

---

## Correctness Properties

### Property 1: 坐标定位复杂度不变式

*For any* 一份 sheet XML 与其上 N 个待读/待写坐标，坐标索引一旦从该 XML 单次构建，任一坐标的命中 SHALL 为 O(1)，N 次命中的总成本 SHALL 为 O(N + XML 长度)，不得随 N 呈 O(N × XML 长度)。同一份 XML 派生的索引与直接 `_cell_view` 全扫返回的格视图 SHALL 逐字段一致（值、样式、公式文本、shared_ref）。

**Validates: Requirements 1.1, 1.2**

### Property 2: 写入批量拼接等价性

*For any* 一组作用于同一 sheet XML 的 CellWrite 序列，一次性按坐标位置拼接产出的 XML SHALL 与逐个 `str.replace` 依次应用产出的 XML 逐字节相同（含缺格插入、缺行插入的定位结果），且拼接路径不得对每个写入重建整份字符串。

**Validates: Requirements 1.3**

### Property 3: 单次 materialize 的工作簿解析次数上界

*For any* 一次 projection-based materialize，对同一份 substrate 的解析/加载次数 SHALL ≤ 2（读入解析一次 + 写盘后 staged 反读一次）；extract 取受管格的值与公式 SHALL 由一次工作簿遍历同时得出。解析次数超过上界或值/公式分两遍读时判据打红。

**Validates: Requirements 1.4, 1.5**

### Property 4: CPU 段线程卸载且事务隔离

*For any* 一次 materialize，其纯 CPU 段（materialize + extract 反读 + verify + structure_hash）SHALL 在工作线程执行，事件循环在该段执行期间可推进其他任务；该段 SHALL 不持有或操作任何 DB 会话，且其抛出的领域异常 SHALL 原样传播至调用方。

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 5: roundtrip 等值与未管理区域判据保持

*For any* 优化后 materialize 产出的 staged 产物，反读 extract 的受管值 SHALL 与 intended projection 按 `values_equal` 口径逐字段等值；未管理区域比对 SHALL 以来自同一 `plan` 的 `row_shift`/`total_formula_rows`/`propagation` 声明值判等价。任一判据被绕过或改为事后 diff 推断时判据打红。

**Validates: Requirements 3.1, 3.2**

### Property 6: structure_hash 与 identity inventory 保持

*For any* 优化后 projection lane 的 materialize，`structure_hash` SHALL 与 `compute_structure_hash_from_artifact` 算得同一量且 fence 与 representation 收到同一值；staged identity inventory SHALL 由实测 staged 产物得出而非由 substrate inventory 加 minted 集合推导。

**Validates: Requirements 3.3, 3.4**

### Property 7: 单事务提交与 revision 记账保持

*For any* 优化后的一次业务 commit，业务事务数 SHALL 恰为 1、business commit 数 SHALL 恰为 1、`content_revision` 增量 SHALL 恰为 +1（重放/复用路径恰为 0），与优化前一致。

**Validates: Requirements 3.5**

### Property 8: 结构性插行阶段顺序与零位移逐字节保持

*For any* 需要结构性插行的 materialize（`row_shift is not None`），位移 → Table ref 增长 → 引用侧传播 → `_GT_SYNC` 重冻结 → 写格的阶段顺序 SHALL 不变；*for any* 无插行的 materialize（`row_shift is None`），优化后的 zip 定点改写产物 SHALL 与优化前逐字节相同。

**Validates: Requirements 3.6, 3.7**

### Property 9: 性能基线由实测现算且判据自证

*For any* 记录在案的每规模 materialize 耗时数字，它 SHALL 由离线剖析脚本对同一份 substrate 现场实测得出（非手抄常量），且「每行摊销成本不随规模上升」由脚本按实测数据自动判定；改了实现未重跑导致数字过期时该判据打红。

**Validates: Requirements 4.1, 4.2, 4.4**

### Property 10: 索引/缓存是单一真源的纯投影且受变异反证

*For any* 引入的坐标索引或 substrate 解析缓存，它 SHALL 由同一份字节单次解析派生、不与 openpyxl/zip 解析并存为可漂移的第二真源；键与真实解析不一致时 SHALL fail visible。*For any* 每条正确性/复杂度守卫，把优化改回 O(N²) 形态或破坏对应等值判据时该守卫 SHALL 打红。

**Validates: Requirements 5.1, 5.2, 5.3**
