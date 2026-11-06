# Requirements Document

## Introduction

64 core violations cleanup.

## Requirements

# 前端核心违规清零

> 修复 `platform-global-display-settings-closure` 任务 11A 守卫发现的 64 个 core violations，
> 使 CI 步骤从 `continue-on-error` 变成硬门禁。

## R1. 固定像素字号改为动态变量

全部 63 个 `v2_fixed_px_font_size` 违规（31 个文件）改为从 `var(--gt-display-font-size)` 或
`useDisplayPreferencesRuntime` 消费动态字号。不改变组件的功能行为。

## R2. GtGridCell 删除 :unit prop

`components/grid/GtGridCell.vue` 的 `<GtAmountCell :unit>` 删除 `:unit` prop。
金额显示已从 effective displayPrefs store 读取。

## R3. 守卫基线归零

修复后 `frontend_amount_guard.cli --check` 的 `total_core_violations` 必须为 0。
`--update-baseline` 须在候选 worktree 上运行。

## R4. CI 硬门禁

`.github/workflows/ci.yml` 的 "Amount display AST guard" 步骤移除 `continue-on-error: true`。

## NFR

- 不改变组件的功能行为
- 四档字号切换后 el-table-v2 行高跟随
- 修复后全量 vitest 无新增失败
