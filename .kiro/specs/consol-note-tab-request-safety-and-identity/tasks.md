# 实施任务：合并附注页请求安全与身份校验（ConsolNoteTab CP-05）

> 关联：#[[file:.kiro/specs/consol-note-tab-request-safety-and-identity/requirements.md]] · #[[file:.kiro/specs/consol-note-tab-request-safety-and-identity/design.md]]
> `[x]` = 代码已落地且 50/50 验收通过；本 spec 为**已实现追认**（测试先行、实现补齐）。
> 铁律：不假绿（3 处变异抽验证明 load-bearing）、不弱化守卫、改动后实测（vitest 50/50 + 相邻回归）。

> 基线：引入时 PASS=2 / FAIL=48 → 收尾 PASS=50 / FAIL=0。consolRequestGuard 17/17 不回归。

- [x] 1. 基础设施：variant 线程化 + loadedNoteContext
  - `NotePageSnapshot` 加 `variant`；`capturePageSnapshot` / guard getContext / `isPageSnapshotCurrent` /
    `sameNoteContext` 全线程 variant；新增 `loadedNoteContext` ref。
  - _需求：R1.1~R1.3_

- [x] 2. isStale 增 signal.aborted（改 composable consolRequestGuard.ts）
  - `isStale` = `ticket.signal.aborted || sequence 变 || !sameContext`。
  - 变异反证：`false && ticket.signal.aborted` → 仅 `unmount aborts pending section load` 红；还原全绿。
  - 既有 `consolRequestGuard.spec.ts` 17/17 不回归。
  - _需求：R4.1、R5.6、R7.2_

- [x] 3. 脏确认门控 + 导航 epoch（行为域 2）
  - `confirmDiscardDirty()` 共享弹窗（文案「切换附注」/「放弃修改并切换」/ 含「未保存」）；
    `noteNavEpoch` + `navDirtyOriginal`/`navDirtyContext`；`onNoteNodeClick` 脏时门控、取消恢复 original
    返回 `'skipped'`、并发 latest-wins first 返 `'stale'`。
  - _需求：R2.1、R2.2、R2.5、R2.6_

- [x] 4. watch 从单 standard 扩为 scope+variant 对象 getter（行为域 3 + 域 2 模板切换）
  - getter `{projectId, year, nodeKey, variant}`；variantChanged 脏时确认（取消 emit
    `restore-note-context` + `revert-standard` + 暂存 `stashedNoteSection`，variant 回切原样恢复）；
    scopeChanged 清空 selection + loadedNoteContext + 关 4 弹窗 + clearDirty + abort 两守卫；
    等价 node（nodeKey 不变）不 fire；变体重载用 `requestedSectionId`（首个加载在飞也能重载，修 A-B-A 空态）。
  - 新增 emit 声明 `restore-note-context`。
  - _需求：R2.3、R2.4、R2.7、R3.1、R3.2_

- [x] 5. onNoteNodeClick 身份校验 + rejectNoteIdentity（行为域 5）
  - 校验①（detail 后）template_type≠variant / section_id≠请求；校验②（saved 后）node_key≠ /
    template_variant≠ / headers 列数≠模板 → `rejectNoteIdentity('failed')`（置空 selection+loadedNoteContext、
    `message.error`）；成功赋值 `loadedNoteContext`；章节 payload 加 `templateVariant`。
  - 变异反证：variant 校验 `if (false && ...)` → 仅 `rejects mismatched variant identity` 红。
  - _需求：R1.2、R5.1_

- [x] 6. saveNoteData 重写（行为域 5）
  - 保存前身份校验（variant / sectionId 不符直接 false 不 PUT）；冻结 data 快照 + `data.template_variant =
    loaded.variant`；A-B-A 保护（PUT 后 `sameNoteContext` + `selectedNoteSection===sec` 才认）；响应
    node_key 校验；`noteDirtyEpoch` 守卫（PUT 期间新编辑则不清 dirty，savedData 用快照、editRows 留新值）。
  - `noteDirtyEpoch` + `markNoteDirtyTracked()` 替换 5 处 markNoteDirty。
  - 变异反证：epoch 守卫 `if (true || ...)` → `save preserves edits during PUT` 等 3 例红。
  - _需求：R5.2~R5.5_

- [x] 7. 子操作接 noteSubOpGuard（行为域 4）
  - 新增独立 `noteSubOpGuard`（watch scope/variant + unmount 都 abort）；`loadNoteBreakdown` /
    `auditCurrentNote` / `fillAllByFormula` / `fillCurrentByFormula` / `confirmAndExecuteAggregate` /
    `jumpToNoteSection`(ACNR latest-wins) / `onNoteFileSelected` / `onNoteBatchImport` /
    `exportNoteFormulas` / `onNoteFormulaImport` / `deleteNoteRows`(内联 confirm+guard，不再用
    useTableToolbar.deleteSelectedRows) / 持久化重读 全部接 signal + 过期判定；stale 时不写回 / 不重开弹窗 /
    不清新 loading / 不 message / 不 PUT。
  - 服务层 signal 透传：`listConsolNoteFormulas` 第 3 参、`getConsolNoteBreakdown` opts.signal。
  - _需求：R4.1~R4.4_

- [x] 8. 缺失方法 + 叶子列 :prop（行为域 6）
  - `leaveNoteEdit`（自管确认，晚到 `sameNoteContext` 校验后作废，`exitNoteEdit(true)` 避免二次确认）；
    `onNoteDragStart`/`onNoteDragMove`（`parseNoteDragCell`：td.cellIndex=col，tbody 行号 +
    `noteDataRowStart`=storage row；preventDefault；range 选区）；`onNoteCellClick`/`onNoteCellContextMenu`
    改用 `noteCellColIndex`（column.property 优先，回退 label）；`noteVisibleRows` computed；叶子
    `el-table-column` 全部绑定 `:prop=String(colIndex)`（6 处：普通 3 级 + 全屏 3 级 + 两处扁平回退）。
  - `onNoteBatchImport` 成功路径重写：取模板为基底，上传数据行按 `dataStart` 槽位覆盖，manual_cells
    全在数据区，`template_variant` 透传。
  - `useCellComments.loadComments` 加可选 signal（晚到不覆盖），`onNoteNodeClick` 传 ticket.signal。
  - _需求：R1.3、R4.1、R6.1~R6.3_

- [x] 9. 顺带修真实生产 bug（HEAD 既有，非本功能）
  - `onUnmounted` 删 `autoSync.cancelPending()`：`autoSync` 从未定义，每次卸载抛 `ReferenceError`
    （污染测试 + 生产卸载报错）；`useAutoSave` 内部 `onBeforeUnmount` 已 `stopTimer` 自取消，无此 API。
  - _需求：—（独立缺陷）_

- [x] 10. 测试侧 fixture 漂移校准（非假绿，git 实证）
  - 恢复自定义 Table/Column/Dialog/Button/Pass stub（加固：无 prop 展示列传 `{row:{},$index:0}`
    作用域，避免差额弹窗 `#default="{row}"` 解构崩溃）；copy/export 索引 `[1]→[3]`（listed 五-5-2
    从 11 行 fixture 清理到 9 行，editRows[2] 输出位从 1 变 3），行为意图不变。
  - `consolRefreshWiring.spec.ts` 的 `hasApiFailure` 扫描窗口由固定 3000 字改为按函数边界（本轮顶部加
    门控/校验把第二个检查挤出窗口，两个检查都在，仍断言 ≥2）——修我引入的回归。
  - _需求：R7.1、R7.3_

## 验收证据（现算核实）

- `ConsolNoteTab.spec.ts` 50/50；`consolRequestGuard.spec.ts` 17/17；`consolRefreshWiring.spec.ts` 绿；
  `useCellComments.spec.ts` 绿；合并目录 + useCellComments 共 295 passed（另 2 为 pre-existing fixture
  漂移红，见下）。
- 变异抽验 3 处全 load-bearing（design §六）。
- 诊断/复盘：`docs/proposals/consol-note-tab-spec-stale-vs-phase5-2026-10-20.md`。

## 相邻 pre-existing 红处置（独立判定，已完成）

- [x]* `consolNoteHeaders.spec.ts` listed 五-5-2/五-5-3 两例红：`git stash` 实证本轮改动前就红，同一
  fixture 漂移。**判定根因 = 测试硬编码旧 fixture，`noteBodyRows` 行为正确**：`noteBodyRows(rows,
  headerIndexes)` 只排除显式配置的表头行；现 fixture `_header_row_indexes` 为 undefined ⇒ 正确返回全部
  9 行（含空白业务行 rows[2]/[3]），正是用例标题「keeps blank business rows」之意。测试原 `body ===
  sec.rows.slice(2)` 假设 2 个已删除的 `类  别` 表头行。**处置 = 校准测试**（`slice(2)→sec.rows` +
  断言 `_header_row_indexes` 为 undefined 钉住意图），**不改 composable**。变异反证：`noteBodyRows`
  末尾加 `.slice(1)` → 5 例红（含这 2 例），证明校准后断言 load-bearing。consolNoteHeaders 12/12，
  合并目录 + useCellComments 297/0 全绿。

## 改动文件（均未提交）

- `audit-platform/frontend/src/components/consolidation/ConsolNoteTab.vue`（6 域实现；并发会话的
  `openFormulaManagerScope` 行未触碰）
- `audit-platform/frontend/src/components/consolidation/composables/consolRequestGuard.ts`
- `audit-platform/frontend/src/services/consolidationApi.ts`
- `audit-platform/frontend/src/composables/useCellComments.ts`
- `audit-platform/frontend/src/components/consolidation/__tests__/ConsolNoteTab.spec.ts`
- `audit-platform/frontend/src/components/consolidation/__tests__/consolRefreshWiring.spec.ts`
- `audit-platform/frontend/src/components/consolidation/__tests__/consolNoteHeaders.spec.ts`（fixture 漂移校准）
- `docs/proposals/consol-note-tab-spec-stale-vs-phase5-2026-10-20.md`
