# Task 14 证据：D3-1 四态覆盖状态机 + 覆盖 UI

spec: `d3-sync-coverage-via-row-table-engine` · Task 14 · Requirements 4.4 / 4.5 / 4.6 / 6.1
日期：2026-09-26 · 数字均现测

---

## 0. 一句话结论

D3-1 审定表逐格接入选项 b 四态覆盖状态机（**复用**平台级共享件
`shared/dynamicAdjudicationRows.resolveCellState`/`displayValueForCellState`，**未在 D3 侧另写一套**）；
Property 8 反证式（纯函数）+ **跑同步器**运行时判据双绿；Property 7（逐格 mask 下受管金额字段仍
`editable`）转绿；第二套 gating（`isD3AdjudicationSyncSheet`）独立接入不与 D3-2 混桥；受管区
7→8（组合口径，如实登记审定表 vs 行表口径差异）；back-compat 基线断言显式扩允许清单。

**整册 materialize 真栈标 `[ ]*`**（双卡点：①另一会话在途把 D3-1 接进行表契约但结构非法致
`parse_contract` 抛错 ②D3 `adapter_registered=False` 裁决 F5），详 §7。

---

## 1. 改动/新建文件清单

### 前端（生产代码）
- `audit-platform/frontend/src/components/workpaper/composables/useD3Adjudication.ts`（改）
  - import 共享 `resolveCellState`/`displayValueForCellState`（**不另写**）。
  - `AdjudicationRow` 加 `cellOverrides?`（仅派生格 `currentUnadjusted` 在 S2/S4 有值）。
  - 新 `snapItemId(section,rowKey,field)` = `${makeItemId}-snap`（照 D4 `snapItemId` 同款存法）。
  - 新 `readStoredCell`/`readSnapCell`/`resolveDerivedCell`（逐格三量→四态）。
  - `buildRow` 的 `currentUnadjusted` 从「非零二选一」改为四态：S1/S3 显示派生、S2/S4 显示覆盖值。
  - 新 `syncDerivedCellsIntoStore`（幂等写 stored+snap，仅未覆盖格）+ `restoreDerivedValue`（逐格恢复取数，当场写对）+ `_derivedCells` computed + watch(immediate)。
  - return 暴露 `restoreDerivedValue` + `_derivedCells`/`_syncDerivedCellsIntoStore`（测试用）。
- `audit-platform/frontend/src/components/workpaper/GtD3PrepaidAccounts.vue`（改）
  - 新增**第二套 gating** `isD3AdjudicationSyncSheet = computed(() => currentSheet.value === 'D3-1')`，**未**并进 `isD3DetailSheet`。
  - `renderModeOptions` 三分支（D3-2 syncBridge / D3-1 专用同步 sheet 但 adapter 未注册暂禁用在线编辑 / 其余 dualMode）；工具条加「审定表在线编辑待接入」info tag。
- `audit-platform/frontend/src/components/workpaper/d3/D3TabAdjudication.vue`（改）
  - 期末未审格渲染「已人工覆盖」badge（S2/S4）+ S4 三值 tooltip（覆盖值/原取数/现取数，提示人工裁决）+ 逐格「恢复取数」按钮。
  - 新 helper `sectionTokenOf`/`currentUnadjTitle`/`onRestoreCurrentUnadjusted`；destructure 取 `restoreDerivedValue`。

### 前端（判据）
- `.../composables/__tests__/d3CellOverrideRender.spec.ts`（新，8 判据）：Property 8 纯函数反证 + **跑同步器**（真实实例化 useD3Adjudication，S1/S2/S3/S4 全可达 + snap 冻结 + 恢复取数作用域一格 + 当场写对）。
- `.../composables/__tests__/d3AdjudicationGatingBoundary.spec.ts`（新，3 判据）：源码级钉死第二套 gating 存在 + `isD3DetailSheet` 绝不含 D3-1 + 第二套被真实消费。
- `.../composables/__tests__/dynamicAdjRowsBackcompatBaseline.spec.ts`（改）：**显式**把 `useD3Adjudication.ts` 加进运行时 value-importer 允许清单（第三个），文件头注明「预期扩散、非悄悄污染」。

### 后端（判据）
- `backend/tests/workpaper_sync/test_d3_01_coverage_and_property7.py`（新，7 判据）：Property 7 转绿（手工金额格逐格不 mask 仍 editable + 变异必红）+ 受管区 7→8 组合口径 + 口径隔离。

**未碰**：引擎/框架层（`phase5_adjudication_sheet.py`/`merge.py`/`contracts.py`）、模板、灰度开关、
磁盘契约、`phase5_d3_prepaid_receipts.py`/`phase5_d3_expansion.py`（**别的会话在途文件**）、tasks.md
标题行与复选框。**零 `if is_d3`/`if wp_code==` 分支。** 一次性探针未产生（全用现有工具）。

---

## 2. Property 8 反证式 + 跑同步器 判据运行结果

`npx vitest run .../d3CellOverrideRender.spec.ts` → **8 passed**。

- **Property 8 反证（纯函数）**：`fc.property`（numRuns=5）——只改 derived、stored==snap（upstreamChanged
  但未 overridden）⇒ 一批格覆盖标记数(S2+S4) 恒为 0。对照条：stored≠snap 时 S2/S4 出现（证明非恒真装饰）。
- **🔴 跑同步器（关键）**：真实实例化 `useD3Adjudication`（喂 crossSheet 聚合 + 手工覆盖 allResponses）：
  - 只改上游派生（不碰 stored/snap）⇒ 真实 sections 全表零覆盖标记（S3 跟随到新派生值 250）。
  - S2：手工覆盖 ⇒ `cellOverrides.currentUnadjusted.state==='S2'` + 显示覆盖值。
  - **S4**：覆盖后上游再变 ⇒ state==='S4'，三值(stored/snap/derived)同时可读且互不相等（`new Set(...).size===3`），显示仍是覆盖值（系统不自动二选一）。
  - snap 在 store 里**真冻结**（`{itemId}-snap` 仍是覆盖时派生值 derived1，不追上新派生 250）。
  - 恢复取数：当场（不 await）写 store=派生值（P15 同款「不靠下一 tick 自愈」）+ 作用域一格（另一派生行保持覆盖态）。

---

## 3. Property 7 转绿证明

`pytest test_d3_01_coverage_and_property7.py` → **7 passed**。

- `test_p7_managed_manual_amount_cells_stay_editable_under_cell_mask`：账龄区（区2）数据行 17-20 的
  B/C/D/F/G/H 手工金额格逐格判定 `is_cell_masked(col,row)==False` ⇒ editable（mask 只覆盖派生/合计/差异
  公式格，不误伤手工金额格）。
- `test_p7_derived_and_computed_cells_are_not_oo_writable`：对照——currentUnadjusted(cross_sheet)/
  audited/change(computed) `is_oo_writable==False`；手工金额/文本 True。
- `test_p7_editable_cells_never_masked_selfcheck`：`assert_data_cells_not_masked()` 不抛。
- `test_p7_mutation_masking_a_manual_amount_cell_would_be_caught`：把 B17 塞进 mask ⇒ 判据能检出（有牙齿）。

---

## 4. 第二套 gating 接法

`GtD3PrepaidAccounts.vue` 新增 `isD3AdjudicationSyncSheet = computed(() => currentSheet.value === 'D3-1')`，
**独立于** `isD3DetailSheet`（后者只判 `'D3-2'`）。理由（evidence task1 §3.2）：D3-2 是行表 rows kind
（d32-managed / syncBridge），D3-1 是 AdjudicationSheetSpec 逐格 mask kind（d31-managed）——entry_id/store
形态完全不同，混用会切错桥 + 工具条叠加冲突。`renderModeOptions` 三分支：D3-1 因 adapter 未注册
（裁决 F5）在线编辑暂禁用、保持结构化视图（Task 16 adapter 注册后接第二套桥再放开）。守卫判据
`d3AdjudicationGatingBoundary.spec.ts`（3 passed）源码级钉死「不得把 D3-1 并进 isD3DetailSheet」。

---

## 5. 受管区 7→8 口径说明（🔴 审定表 vs 行表口径不同，不硬凑）

Task 12 的 `_STAGE2_REGIONS_BY_SHEET` 数的是**行表契约**（`RowTableSheetSpec` →
`build_contract_payload()` → `contract.sheets[].tables[]`）TableSpec 总数 = 7（d32/d36/d34×2/d35/d37×2）。

D3-1 与 D4-1 关键区别：D4-1 审定行是**动态行**（UUID 列 W/X）⇒ 接成行表契约 `d41-managed` 两 TableSpec；
**D3-1 是 `row_mode=fixed_rows` 逐格 mask**（固定 4/4 行、无 UUID、无动态 Table）⇒ 独立 `AdjudicationSheetSpec`，
**不进** 行表契约。⇒ 行表契约计数**仍 7**（非遗漏，口径本质不同）。D3-1 作为**第 8 个受管区**登记在
**组合口径** = 行表 7 + 审定表 sheet 1（`d31-managed`，两 section nature/aging 属同一受管 sheet，sheet 级计 1，
同 D4-1）。判据 `test_combined_managed_region_count_reaches_eight_with_d3_01` 断言组合口径 8、
`test_rowtable_region_baseline_is_seven` 钉住行表基线不变、`test_d3_01_managed_sheet_distinct_from_rowtable_sheets`
钉口径隔离。

---

## 6. back-compat 基线断言的显式更新

`dynamicAdjRowsBackcompatBaseline.spec.ts` §「运行时消费方边界」：允许清单
`{useD4Adjudication, useK2Adjudication}` → **加 `useD3Adjudication.ts` 为第三个**（并把它加进 `files` 扫描列表）。
文件头明确注明：**这是预期扩散、不是悄悄污染** —— 四态状态机本就是平台级共享件、要给每张审定表用，
D3 只复用纯函数判定 + 显示逻辑，**未改动共享件本身任何默认路径**（P10 逐字节冻结判据仍绿）。
运行：**3 passed**。绝未为规避基线而 type-only import 或另写一套状态机。

---

## 7. 整册 materialize / 耗时 —— `[ ]*` 卡点（如实登记）

**真栈整册 materialize 跑不起来，标 `[ ]*`**，双卡点：

1. **🔴 另一会话在途冲突**：工作树里 `d3.prepaid_receipts_detail.json`（磁盘契约）+
   `phase5_d3_prepaid_receipts.py`/`phase5_d3_expansion.py` 被**别的 lane 在途**修改，把 `d31-managed`
   接成了行表契约第 6 张 sheet（`build_contract_payload()` 现算得 9 table），但**结构非法**：
   `parse_contract` 抛 `contract[...].sheets[d31-managed].tables[adj_nature_rows].fields[...]:
   cell.row_from=row_identity 只能用于行域字段`（D3-1 是固定行 per-cell，不是行域字段）。
   `git show HEAD:` 的磁盘契约**无** `d31-managed` ⇒ 确认是**在途、非本任务引入**。本任务
   **不碰**该 lane 的 provider/契约/expansion 文件，判据改为不依赖被污染的
   `assert_contract_file_matches_source()`（用 HEAD committed 行表基线常量 + 干净 `SPEC_D301`）。
2. **adapter_registered=False（裁决 F5）**：真库 `register_from_manifest()` 只注册 {d2,d4,g7,h1}，D3
   未注册 ⇒ 真栈 materialize/OO 直写链跑不起来（同 Task 5/7/10/12）。

替代口径：引擎层/合成基线判据均已绿（§2/§3 覆盖派生格四态、snap 冻结、恢复取数、Property 7）。
真栈整册 materialize + 端到端耗时留待：①上述在途 lane 把 D3-1 行表契约结构修合法（或明确 D3-1 只走
审定表口径不进行表契约）②adapter 注册（Task 16 前端接线阶段）。

---

## 8. 测试运行汇总（现测）

| 判据 | 结果 |
|---|---|
| `d3CellOverrideRender.spec.ts`（Property 8 反证 + 跑同步器 S1~S4/snap/恢复取数） | 8 passed |
| `d3AdjudicationGatingBoundary.spec.ts`（第二套 gating 守卫） | 3 passed |
| `dynamicAdjRowsBackcompatBaseline.spec.ts`（back-compat 扩允许清单） | 3 passed |
| `useD3Adjudication.spec.ts`（既有 Property 9 EventBus，零回归） | 3 passed |
| 10 张 D3 前端 composable/component 套件（零回归） | 90 passed |
| `test_d3_01_coverage_and_property7.py`（Property 7 + 受管区 7→8） | 7 passed |
| `test_d3_01_adjudication_spec.py`（Task 13 声明，零回归） | 15 passed |
| `test_phase5_adjudication_sheet.py` + `test_adjudication_sheet_spec.py`（框架层零回归） | 34 passed |
| `vue-tsc --noEmit` 全仓（含改动文件） | 0 error TS |

## 9. 已知基线红（非本任务引入）
- `test_task5…real_registration`（adapter 未注册，裁决 F5）。
- `test_fail_closed_behaviours_match[d3]`（xfail）。
- `test_current_d3_managed_region_count_after_stage2_is_five`（**在途 lane** 把非法 `d31-managed` 写进磁盘契约致 `parse_contract` 抛错——见 §7.1，`git show HEAD:` 证实非本任务引入）。
- `test_sibling_table_ref_row_shift[D1-8]` / definition_store。
