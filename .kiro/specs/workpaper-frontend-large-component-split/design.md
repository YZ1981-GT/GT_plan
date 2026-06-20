# 设计文档：底稿前端大组件拆分（P1，Top 3）

## 概述

3 个最大底稿组件按"逻辑域抽 composable + 展示域拆子组件"降到 ≤800 行。核心原则：**结构搬运、props/emit 契约零变更、响应式与事件流不破**。主 .vue 保持为编排器（template + 少量 wiring），重逻辑迁入 `composables/`，重复/独立的展示块迁入子组件。

## 拆分手法（前端通用模式）

- **composable**：`src/composables/useXxx.ts` 导出一个函数，接收主组件传入的 props/ref，返回 ref/computed/methods。状态用 `ref`/`reactive` 保持响应式；不在 composable 内直接 emit（emit 仍由主组件持有，composable 返回数据/回调由主组件 wire）。
- **子组件**：纯展示型块（如对话框、面板）抽为 `.vue`，props 下行 + emit 上行，主组件透传。
- **依赖单向**：主组件 → composable → util；composable 之间不互相 import（共享状态由主组件协调）。

## 影响面（grep 实测）

3 组件均为 `htmlData`/`schema` 驱动的展示+编辑组件，对外契约清晰：
- `GtAProgramConsole`：props(wpId/sheetName/schema/htmlData/readonly) + 6 emit。逻辑簇：复核子码解析（resolveReviewWpCode/reviewChipDisplayValue/isReviewChipDisabled + reviewTemplates state）、A17 版本适用性（a17_5Versions）、数据加载（loadProjectInfo/applicableWhen）、裁剪/状态流转、弹窗。
- `GtChecklistTable`：props + emit。逻辑簇：响应填写（getResponse/updateConclusion/updateRemark/updateWpRef + responses state + 自动保存 doSave/scheduleSave debounce）、搜索（searchResults/highlightText/jumpToSearchResult/clearSearch）、适用性（isSectionApplicable/toggleSectionApplicability/confirmApplicability）、复核签字提示（loadReviewSignHints/signHintForItem/applySignHint）。
- `GtAuditSheet`：props + emit。逻辑簇：表格构建（buildTableData/isBoldRow/isEditableRow + 合计汇总）、动态列（isDynamicColumns/dynamicColumnDefs/columnGroups/期初区折叠）、说明结论（buildSections/onSectionChange/auditSections state）。

## 拆分方案

### 1. `GtAProgramConsole.vue`（1625 → ≤800）

```
GtAProgramConsole.vue              # 编排器：template + props/emit + 程序行表格渲染 + wiring
composables/useAProgramReview.ts   # 复核子码解析 + A17 版本适用性（reviewTemplates/a17_5Versions
                                   #   + resolveReviewWpCode/reviewChipDisplayValue/isReviewChipDisabled
                                   #   + 加载 review templates/a17_5 versions）
composables/useAProgramData.ts     # 程序行加载 + 项目信息 + applicable_when/isNotApplicable
```

- composable 接收 `wpId`/`sheetName`/`projectId` ref，返回所需 ref/computed/load 方法。
- 审计逻辑图（GtAuditFlowGraph）和弹窗（WpInlinePopup）已是子组件，无需再拆，仅保留 wiring。
- **复盘修正①（实施发现）**：仅抽 2 composable 后主组件仍 1517 行；template ~230 行"关联底稿"chip 块抽为展示型子组件 `GtAProgramLinkedChips.vue`（props 下行 + emit 上行，主组件 props/emit 契约不变），降到 1322。
- **复盘修正②（再实施发现）**：抽 chip 子组件后主体实为 **script 723 行**（非 template）。追加第 3 composable `composables/useAProgramPopups.ts` 迁出弹窗完成状态(popupCompletionStatus/checkCompletion/loadPopupCompletionStatus) + A16 推荐版本 + 程序表加载(initData/fetchProcedureTableData) + 导出等 ~570 行 script 逻辑；对话框 state 与 emit 仍由主组件持有。三者合力达 ≤800。
- 主组件目标 ≤800。

### 2. `GtChecklistTable.vue`（1437 → ≤800）

```
GtChecklistTable.vue                   # 编排器：template + props/emit + 章节导航/条目渲染 + wiring
composables/useChecklistResponses.ts   # responses state + getResponse/updateConclusion/updateRemark/
                                       #   updateWpRef + doSave/scheduleSave/handleManualSave/handleReset
                                       #   + pendingChanges/hasDirtyData（自动保存 debounce 2s 不变）
composables/useChecklistSearch.ts      # searchQuery/searchResults/highlightText/jumpToSearchResult/clearSearch
composables/useChecklistApplicability.ts # sectionApplicability/isSectionApplicable/toggleSectionApplicability/
                                       #   confirmApplicability/openApplicabilityDialog
```

- 自动保存涉及 api 调用 + projectId，composable 接收 projectId ref + emit 回调（保存成功通知由主组件 emit）。
- 主组件目标 ≤800。

### 3. `GtAuditSheet.vue`（1405 → ≤800）

```
GtAuditSheet.vue                    # 编排器：template + props/emit + 表格渲染 + wiring
composables/useAuditSheetTable.ts   # tableData/buildTableData/isBoldRow/isEditableRow + TB 取数 + 合计汇总
composables/useAuditSheetColumns.ts # isDynamicColumns/dynamicColumnDefs/columnGroups/期初区折叠状态
composables/useAuditSheetSections.ts# auditSections state/buildSections/onSectionChange
```

- 主组件目标 ≤800。

## 守卫与验证

- 每组件拆完：getDiagnostics 清 → `npx vitest run`（该组件 spec）→ `npx tsc --noEmit` → **Playwright 实测主链路**（起后端 9980 + 前端 3030，打开对应底稿，验渲染/编辑/保存/联动）。
- 全量：3 组件 ≤800、相关 vitest 全绿、tsc 无新错、Playwright 3 组件主链路通过。

## 不做的事

- 不改任何 props 契约、emit 事件、用户可见交互、联动行为。
- 不动其他底稿组件、views 层、后端。
- 不滥用 provide/inject（保持 props/emit 显式契约）。
- 不为追求更小行数制造碎片；每组件 ≤800 即止。
