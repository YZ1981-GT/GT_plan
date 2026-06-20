# 实施计划：底稿前端大组件拆分（P1，Top 3）

## 概述

3 个最大底稿组件按"逻辑域抽 composable + 展示域拆子组件"降到 ≤800 行，行为零变更。每组件独立 Sprint，互不阻塞，**每 Sprint 末必 Playwright 实测**。语言：Vue 3 + TypeScript + Element Plus + vitest + Playwright。

## Tasks

- [x] 1. 先扩前端大文件守卫（红灯起步）
  - [x] 1.1 新建 `audit-platform/frontend/src/components/workpaper/__tests__/large_component_guard.spec.ts`
    - 断言 GtAProgramConsole/GtChecklistTable/GtAuditSheet 三个 .vue 行数 ≤800
    - 此时预期红灯（3 组件超标），确认守卫准确
    - _Requirements: 4.1_

- [x] 2. Sprint A：`GtAProgramConsole.vue` → 抽 2 composable（Req 1）
  - [x] 2.1 建 `composables/useAProgramReview.ts`
    - 迁移 reviewTemplates/a17_5Versions state + resolveReviewWpCode/reviewChipDisplayValue/isReviewChipDisabled + 加载逻辑，逐字搬运保响应式
    - _Requirements: 1.2_
  - [x] 2.2 建 `composables/useAProgramData.ts`
    - 迁移 loadProjectInfo/projectInfo/applicableWhen/isNotApplicable，逐字搬运
    - _Requirements: 1.2_
  - [x] 2.3 主组件 import composable + wiring
    - 主组件调用 composable 取回 ref/computed/方法；props/emit 逐字不变；template 引用不变
    - _Requirements: 1.3_
  - [x] 2.4 验证 Sprint A：vitest + tsc + **Playwright 实测**
    - GtAProgramConsole.vue ≤800；getDiagnostics 清；现有 vitest spec 全绿；`npx tsc --noEmit` 无新错
    - Playwright 起前后端，打开程序表底稿，实测渲染/裁剪/状态流转/弹窗/审计逻辑图无崩
    - _Requirements: 1.1, 1.4, 4.2, 4.3, 4.4_

- [x] 3. Sprint A 检查点
  - props/emit 契约不变、主链路 Playwright 通过，如有问题向用户确认。

- [x] 4. Sprint B：`GtChecklistTable.vue` → 抽 3 composable（Req 2）
  - [x] 4.1 建 `composables/useChecklistResponses.ts`
    - 迁移 responses/pendingChanges/hasDirtyData state + getResponse/updateConclusion/updateRemark/updateWpRef + doSave/scheduleSave/handleManualSave/handleReset（debounce 2s 不变）
    - _Requirements: 2.2, 2.3_
  - [x] 4.2 建 `composables/useChecklistSearch.ts`
    - 迁移 searchQuery/searchResults/highlightText/jumpToSearchResult/clearSearch
    - _Requirements: 2.2_
  - [x] 4.3 建 `composables/useChecklistApplicability.ts`
    - 迁移 sectionApplicability/isSectionApplicable/toggleSectionApplicability/confirmApplicability/openApplicabilityDialog
    - _Requirements: 2.2_
  - [x] 4.4 主组件 import composable + wiring
    - props/emit 逐字不变；自动保存成功 emit 由主组件持有
    - _Requirements: 2.3_
  - [x] 4.5 验证 Sprint B：vitest + tsc + **Playwright 实测**
    - GtChecklistTable.vue ≤800；vitest 全绿；tsc 无新错
    - Playwright 实测核对表导航/填写/搜索/批量标记/适用性/保存全链路无崩
    - _Requirements: 2.1, 2.4, 4.2, 4.3, 4.4_

- [x] 5. Sprint B 检查点
  - props/emit 契约不变、自动保存行为不变、主链路 Playwright 通过，如有问题向用户确认。

- [x] 6. Sprint C：`GtAuditSheet.vue` → 抽 3 composable（Req 3）
  - [x] 6.1 建 `composables/useAuditSheetTable.ts`
    - 迁移 tableData/buildTableData/isBoldRow/isEditableRow + TB 取数 + 合计汇总，逐字搬运
    - _Requirements: 3.2, 3.3_
  - [x] 6.2 建 `composables/useAuditSheetColumns.ts`
    - 迁移 isDynamicColumns/dynamicColumnDefs/columnGroups/期初区折叠状态
    - _Requirements: 3.2_
  - [x] 6.3 建 `composables/useAuditSheetSections.ts`
    - 迁移 auditSections state/buildSections/onSectionChange
    - _Requirements: 3.2_
  - [x] 6.4 主组件 import composable + wiring
    - props/emit 逐字不变；TB 取数/合计/可编辑行判定行为不变
    - _Requirements: 3.3_
  - [x] 6.5 验证 Sprint C：vitest + tsc + **Playwright 实测**
    - GtAuditSheet.vue ≤800；vitest 全绿；tsc 无新错
    - Playwright 实测审定表渲染/编辑/动态列/说明结论/合计全链路无崩
    - _Requirements: 3.1, 3.4, 4.2, 4.3, 4.4_

- [x] 7. Sprint C 检查点
  - props/emit 契约不变、主链路 Playwright 通过，如有问题向用户确认。

- [x] 8. 终验：守卫转绿 + 全量零回归
  - [x] 8.1 `large_component_guard.spec.ts` 全绿（3 组件 ≤800）
  - [x] 8.2 `npx vitest run`（底稿组件相关 spec）全绿
  - [x] 8.3 `npx tsc --noEmit` 无新增类型错误
  - [x] 8.4 Playwright 实测 3 组件主链路全部通过
  - [x] 8.5 composable/子组件依赖单向，无循环引用
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 9. 最终检查点
  - 3 组件全部 ≤800、守卫绿、零回归、props/emit 契约全不变。如有问题向用户确认。

## Notes

- 三个 Sprint 互不阻塞，可独立提交；**每 Sprint 末必 Playwright 实测**（铁律，前端拆分风险高）
- **铁律**：props/emit 契约逐字不变；composable 保响应式（ref/computed）；依赖单向不循环
- composable 内不直接 emit，emit 仍由主组件持有，回调 wire
- **绝不动** 其他底稿组件、views 层、后端
- 每组件 ≤800 即止，不过度碎片化
- rtk 前缀跑 vitest/tsc/playwright；前端路径 `audit-platform/frontend/`
