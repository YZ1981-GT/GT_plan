# Implementation Plan: display-core-violations-cleanup

## Task Dependency Graph.

1-3 parallel, 4 after 1-3, 5 after 4.

## Overview

5 tasks.

## Tasks

# 任务清单

- [x] 1. 合并工作底稿 12 文件统一字号（24 violations）
  - 新建 `useSheetCellFont.ts` 共享 helper
  - 12 个 worksheet 的 cellRenderer fontSize 改用 helper
  - 跑 `--check` 确认 violations 减少 24

- [x] 2. TrialBalance + composables（19 violations）
  - TrialBalance.vue 的 7 处 cellRenderer 字号改动态
  - useWorkflowGuide.ts（6 处）、useWorkpaperReviewMarkers.ts（5 处）、useReviewContextMenu.ts（1 处）
  - 跑 `--check` 确认 violations 减少 19

- [x] 3. 凭证类 + GtGridCell + 散件（21 violations）
  - D3VoucherCheckDialog、G4TabVoucherCheck、useD3VoucherCheck、g9VoucherCross、useG8VoucherCheck（4 处）
  - GtGridCell.vue 删除 :unit prop（1 处 gt_amount_cell_with_unit）
  - GtEditableTable（2）、GtFormulaEditDialog（1）、A177IndependenceDeclaration（2）、
    ConsolNoteMappingDialog（1）、noteConsistencyMessage（1）、RiskAssessmentPanel（1）、
    ConfirmationHub（3）、DeliverableCenter（1）、CapitalReserveSheet 重复计数已在任务 1
  - 跑 `--check` 确认 total_core_violations = 0

- [x] 4. CI 硬门禁与基线归零
  - `_HISTORICAL_UPPER_LIMIT` 从错误的 88 修正为 2000（旧值从未与真实 baseline 对齐）
  - `--update-baseline --force` 在工作树上运行：total_core_violations 0，total_candidates 1451
  - ci.yml `frontend-build` job 新增 "Amount display AST guard" 步骤（无 continue-on-error）
  - 全量 vitest 无新增失败：36 passed

- [x] 5. 验收
  - 全量 `--check` exit 0 ✅（Amount guard check passed: 1451 candidates, 18 scopes）
  - guard tests 36/36 passed
  - 候选树 ci.yml 新增步骤无 continue-on-error ✅

