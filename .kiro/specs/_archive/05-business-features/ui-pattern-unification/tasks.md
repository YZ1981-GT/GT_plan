# Implementation Plan: UI Pattern Unification

## Overview

将 5 个抽凭引擎组件从 el-collapse 内嵌模式迁移到 dialog-mode 工具栏按钮模式，将 2 个版本链组件从 useVersionTrail 直调迁移到 useWorkpaperVersionToolbar 高层封装。每个组件独立迁移，互不影响。

**参考标准**：
- 抽凭迁移：`G5TabVoucherCheck.vue`（dialog-mode 集成方式）
- 版本链迁移：`GtG4BondInvestmentMain.vue`（useWorkpaperVersionToolbar 集成方式）

**编程语言**：Vue 3 + TypeScript（项目既有技术栈）

## Tasks

- [x] 1. D2TabVoucherCheck 抽凭模式迁移
  - [x] 1.1 迁移 D2TabVoucherCheck 为 dialog-mode（已验证：diagnostics 清洁 + voucherSampling PBT 13/13）
    - 在 `d2/D2TabVoucherCheck.vue` 的 `<template>` 中：
      - 删除 `<el-collapse class="sampling-engine-collapse">` 及其内部 `<el-collapse-item>` 包裹结构
      - 在工具栏区域（section-head > head-actions）放置 `<GtVoucherSamplingEngine :project-id="projectId" :account-codes="['1122']" dialog-mode @filled="handleSamplingFilled" />`
    - 保留 `handleSamplingFilled` 函数体不变（mapSampledVoucherToRow + fillMode 逻辑 + debounceSave）
    - 保留 accountCode="1122" 参数值
    - 确认 import 路径 `../../voucher-sampling/GtVoucherSamplingEngine.vue` 正确
    - 删除 sampling-engine-collapse 相关 CSS
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4_

- [x] 2. F2ValuationTestSheet 抽凭模式迁移
  - [x] 2.1 迁移 F2ValuationTestSheet 为 dialog-mode（已验证：diagnostics 清洁 + PBT 13/13）
    - 在 `F2ValuationTestSheet.vue` 的 `<template>` 中：
      - 删除 `<el-collapse class="sampling-collapse">` 包裹结构
      - 在工具栏区域放置 `<GtVoucherSamplingEngine :project-id="projectId" :account-codes="[accountCode]" dialog-mode @filled="handleSamplingFilled" />`
    - 保留原有 `handleSamplingFilled` / `handleAutoExtractFilled` 回调逻辑不变
    - 保留 accountCode / phase 等业务参数原有值
    - 确认 GtVoucherSamplingEngine import 路径正确
    - 删除 sampling-collapse 相关 CSS
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 3.1, 3.2, 3.5_

- [x] 3. F2TabPurchaseInboundCheck 抽凭模式迁移
  - [x] 3.1 迁移 F2TabPurchaseInboundCheck 为 dialog-mode（已验证：diagnostics 清洁 + PBT 13/13）
    - 在 `F2TabPurchaseInboundCheck.vue` 的 `<template>` 中：
      - 删除 el-collapse 包裹抽凭引擎的结构（如有）
      - 在工具栏区域放置 `<GtVoucherSamplingEngine :project-id="projectId" :account-codes="[accountCode]" dialog-mode @filled="handleSamplingFilled" />`
    - 保留原有 @filled 回调逻辑（样本到购入检查行的映射规则）
    - 保留 accountCode 等业务参数值
    - 确认 import 路径正确
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 3.3, 3.5_

- [x] 4. F2TabMaterialUsageCheck 抽凭模式迁移
  - [x] 4.1 迁移 F2TabMaterialUsageCheck 为 dialog-mode（已验证：diagnostics 清洁 + PBT 13/13）
    - 在 `F2TabMaterialUsageCheck.vue` 的 `<template>` 中：
      - 删除 el-collapse 包裹抽凭引擎的结构（如有）
      - 在工具栏区域放置 `<GtVoucherSamplingEngine :project-id="projectId" :account-codes="[accountCode]" dialog-mode @filled="handleSamplingFilled" />`
    - 保留原有 @filled 回调逻辑（样本到领用检查行的映射规则）
    - 保留 accountCode 等业务参数值
    - 确认 import 路径正确
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 3.4, 3.5_

- [x] 5. F5TabMajorAdjustment 抽凭模式迁移
  - [x] 5.1 迁移 F5TabMajorAdjustment 为 dialog-mode（已验证：diagnostics 清洁 + PBT 13/13）
    - 在 `F5TabMajorAdjustment.vue` 的 `<template>` 中：
      - 删除 `<el-collapse class="f5-sampling">` 包裹结构
      - 在工具栏区域放置 `<GtVoucherSamplingEngine :project-id="projectId" :account-codes="['6401']" dialog-mode :phase="'final'" @filled="handleSamplingFilled" />`
    - 保留 accountCode="6401" 及 phase="final" 参数不变
    - 保留原有 `handleSamplingFilled` 凭证到重大调整行的映射逻辑不变
    - 确认 import 路径正确
    - 删除 f5-sampling 相关 CSS
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 4.1, 4.2, 4.3, 4.4_

- [x] 6. Checkpoint - 抽凭迁移验证
  - Ensure all tests pass, ask the user if questions arise.
  - 运行 `npx vitest run --reporter=verbose` 确认无类型错误（voucherSampling PBT 13/13 全绿）
  - 确认 5 个组件的 el-collapse 引用已全部移除（grep 0 匹配）

- [x] 7. GtG5LongTermReceivable 版本链模式迁移
  - [x] 7.1 迁移 GtG5LongTermReceivable 版本链为 useWorkpaperVersionToolbar（已验证：diagnostics 清洁 + versionTrail 15/15）
    - 在 `GtG5LongTermReceivable.vue` 的 `<script setup>` 中：
      - 将 `import { useVersionTrail }` 替换为 `import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'`
      - 将 `const { autoSnapshot } = useVersionTrail(computed(() => props.wpId))` 替换为：
        ```typescript
        const versionToolbar = useWorkpaperVersionToolbar({
          wpId: computed(() => props.wpId),
          projectId: computed(() => props.projectId),
        })
        const { versionTrailRef } = versionToolbar
        ```
      - 将 `showVersionHistory()` 函数体替换为 `versionToolbar.openVersionHistory()`
      - 删除旧的 `versionTrailRef.value?.open?.()` 调用
      - 删除手动 autoSnapshot 调用逻辑（已由 toolbar 的 scheduleAutoSnapshot 内置）
    - 在 `<template>` 中：
      - 版本历史按钮 @click 改为 `versionToolbar.openVersionHistory()`
      - 确认 `<GtWpVersionTrail ref="versionTrailRef" ...>` 组件保留
    - 保持版本快照的创建/对比/回滚功能不变
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 7.2_

- [x] 8. GtConfirmationAlternativeL05 版本链模式迁移
  - [x] 8.1 迁移 GtConfirmationAlternativeL05 版本链为 useWorkpaperVersionToolbar（已验证：diagnostics 清洁 + versionTrail 15/15；顺带修正 useWorkpaperImportExport 路径）
    - 在 `confirmation/alternativeL05/GtConfirmationAlternativeL05.vue` 的 `<script setup>` 中：
      - 将 `import useVersionTrail from '../composables/useVersionTrail'` 替换为 `import { useWorkpaperVersionToolbar } from '../composables/useWorkpaperVersionToolbar'`
      - 将 `const versionTrail = useVersionTrail({ projectId: projectIdRef, workpaperId: wpIdRefVt })` 替换为：
        ```typescript
        const versionToolbar = useWorkpaperVersionToolbar({
          wpId: wpIdRefVt,
          projectId: projectIdRef,
        })
        const { versionTrailRef } = versionToolbar
        ```
      - 删除 `watch(() => data.isDirty.value, ...)` 中的 `versionTrail.createSnapshot('auto', '自动保存快照')` 逻辑，替换为 `versionToolbar.scheduleAutoSnapshot()`
      - 更新 `provide('versionTrail', ...)` 为 `provide('versionTrail', versionToolbar)`（或移除如不再被子组件 inject）
    - 在 `<template>` 中添加版本历史按钮（如缺少）：`<el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>`
    - 添加 `<GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />` 组件（如缺少）
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.2_

- [x] 9. Checkpoint - 版本链迁移验证
  - Ensure all tests pass, ask the user if questions arise.
  - 运行 `npx vitest run --reporter=verbose` 确认 versionTrail.spec.ts 全部通过（15/15 全绿）

- [x] 10. 回归验证
  - [x] 10.1 运行全量已有测试确认无破坏（28/28 全绿：抽凭 PBT 13 + 版本链 15；7 组件 diagnostics 全清洁）
    - 运行 `npx vitest run` 确认以下测试全量通过：
      - `voucherSampling.property.spec.ts`（抽凭 PBT）
      - `versionTrail.spec.ts`（版本链单元测试）
    - 不修改任何已有测试文件的断言逻辑
    - 确认所有 7 个迁移组件无 TypeScript 编译错误
    - _Requirements: 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.2, 9.3_

## Notes

- 不需要 PBT（纯 UI 集成模式迁移，底层逻辑不变，已有测试覆盖）
- 每个组件独立完成迁移，互不影响（Requirement 8）
- 不修改 GtVoucherSamplingEngine / useWorkpaperVersionToolbar 本身的 API
- 不引入新的共享状态或跨组件依赖
- 各组件 @filled handler 函数体保持原有逻辑不变，仅改变 UI 集成模式
- Checkpoints 确保增量验证

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1", "4.1", "5.1"] },
    { "id": 1, "tasks": ["7.1", "8.1"] },
    { "id": 2, "tasks": ["10.1"] }
  ]
}
```
