# Design Document

## Overview

Fix 64 violations.

## Architecture

Reuse useDisplayPreferencesRuntime.

## Components and Interfaces

New useSheetCellFont.ts helper.

## Data Models

No new models.

# 设计：前端核心违规清零

## 1. 违规分布

| 域 | 文件数 | 违规数 | 违规码 |
|----|--------|--------|--------|
| 合并工作底稿 worksheets | 12 | 24 | v2_fixed_px_font_size |
| TrialBalance | 1 | 7 | v2_fixed_px_font_size |
| composables (useWorkflowGuide/ReviewMarkers/ContextMenu) | 3 | 12 | v2_fixed_px_font_size |
| 凭证检查类 (D3/G4/G8/G9) | 4 | 4 | v2_fixed_px_font_size |
| GtGridCell | 1 | 1 | gt_amount_cell_with_unit |
| 散件 (GtEditableTable/GtFormulaEditDialog/A177/ConfirmationHub/DeliverableCenter 等) | 10 | 16 | v2_fixed_px_font_size |

## 2. 修复策略

### 2.1 el-table-v2 cellRenderer 字号（48/63）

合并工作底稿 12 个 sheet 和 TrialBalance 都在 `cellRenderer` / `headerCellRenderer` 中写死
`fontSize: '12px'`。改为：

```ts
import { useDisplayPreferencesRuntime } from '@/composables/useDisplayPreferencesRuntime'
const { fontSizePx } = useDisplayPreferencesRuntime()
// cellRenderer 中使用 fontSizePx.value 而非 '12px'
```

12 个合并 worksheet 的 cellRenderer 结构高度同质，提取为
`components/consolidation/worksheets/useSheetCellFont.ts` 共享 helper。

### 2.2 内联样式字号（15/63）

composables 和散件中的 `font-size: 12px` 内联样式改为 `font-size: var(--gt-display-font-size)`。

### 2.3 GtGridCell :unit（1/64）

删除 `:unit` prop 传递。`GtAmountCell` 已内部读取 effective store。

## 3. 验证

- 每批修完跑 `--check` 确认 violations 逐批减少
- 全部修完跑 `--update-baseline --force` 归零
- CI 移除 `continue-on-error`
- vitest 无新增失败
