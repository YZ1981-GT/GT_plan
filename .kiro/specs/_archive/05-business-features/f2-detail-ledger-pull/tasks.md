# Implementation Plan

## Overview

F2-3~F2-13 存货明细表「📥 从序时账取数」入口。3 波 8 任务，纯前端+灰度门控。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "W0", "name": "共享 helper + 测试", "tasks": ["1.1", "1.2"] },
    { "id": "W1", "name": "接入 11 张明细表", "tasks": ["2.1", "2.2"] },
    { "id": "W2", "name": "验证 + 勾稽提示", "tasks": ["3.1", "3.2", "3.3", "3.4"] }
  ]
}
```

## Tasks

- [x] 1. Wave 0 — 共享 helper + 测试
  - [x] 1.1 新建 `f2DetailLedgerPull.ts`
    - 新建 `audit-platform/frontend/src/components/workpaper/composables/f2DetailLedgerPull.ts`
    - `F2_DETAIL_SHEET_ACCOUNT` 映射表（11 张 sheet→科目码）
    - `pullF2DetailFromLedger(projectId, accountCode, year)` 纯前端游标分页（复用 `/ledger/entries/{code}` 接口，page_size=200 循环翻页直到无更多，按 account_name 去尾段分组，Σdebit_amount→increase / Σcredit_amount→decrease）
    - 返回 `LedgerPullResult { rows, totalIncrease, totalDecrease, pagesFetched }`
    - 异常 try/catch 返回空结果（Property 4）
    - _Requirements: 1.2, 4.1, 5.1_
  - [x] 1.2 vitest `f2DetailLedgerPull.spec.ts`
    - mock `api.get` 返回序时账分页数据
    - `test_aggregates_by_account_name`（Property 1）
    - `test_empty_returns_zero`（Property 4）
    - `test_only_target_account`（Property 5）
    - `test_multi_page_aggregation`
    - 运行 `npx vitest run` 确认全绿
    - _Requirements: 7.1_

- [x] 2. Wave 1 — 接入 11 张明细表
  - [x] 2.1 确认各明细表 composable 行写入接口
    - 逐一 read_code F2-3~F2-13 对应 composable（useF2Detail 或各自 useF2Detail*）确认 `addRow`/`updateRow`/`setField` 签名
    - 确认行名字段（`itemName`/`name`/`productName` 等）+ increase/decrease 字段名
    - 产出映射文档（每 sheet 的 composable 接口+字段名）
    - _Requirements: 4.3_
  - [x] 2.2 各明细表工具栏加按钮 + 取数逻辑
    - 11 个 F2DetailSheet 组件各自加「📥 从序时账取数」按钮（`v-if` 灰度开 + `:disabled="isReadonly"` + `:loading="ledgerPulling"`）
    - 点击→`pullF2DetailFromLedger(projectId, F2_DETAIL_SHEET_ACCOUNT[sheetCode], year)`
    - 结果预览 ElMessageBox.confirm（N 行匹配 / M 行新增 / 共 X 行）
    - 确认后逐行：已有同名行且 increase/decrease 非零→跳过（手工优先）；已有同名行字段为空→填入；无同名行→addRow
    - 持久化经 composable 既有 save 路径
    - 灰度关时按钮不渲染（Property 6）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 5.1, 6.1_

- [x] 3. Wave 2 — 验证 + 勾稽提示
  - [x] 3.1 Vite transform 全 11 文件 200
    - curl.exe 验证各 F2DetailSheet Vite transform 200
    - _Requirements: 6.1_
  - [x] 3.2 get_diagnostics 全清
    - 11 个组件 + f2DetailLedgerPull.ts 全清
    - _Requirements: 6.1_
  - [x] 3.3 勾稽提示（可选）
    - 取数完成后在明细表底部显示勾稽提示：「序时账合计 increase=X / decrease=Y vs 审定表 F2-1 该类别 increase/decrease 差异」
    - 差异 > 1 元 warning tag
    - _Requirements: 3.1, 3.2, 3.3_
  - [x] 3.4* live round-trip（可选，需灰度开+实例化项目+存货科目有序时账数据）
    - 实测某明细表「从序时账取数」→填入行→持久化→刷新回显
    - _Requirements: 7.1_

## Notes

- 不新建后端端点（纯前端取数，复用 `/ledger/entries/{code}` 游标分页）
- 期初余额（opening）不从四表库取（决策 4：K8/K9 范式只取发生额不取期初，opening 留手工/导入补）
- 灰度开关 `F2_FOUR_TABLE_EXTRACTION_ENABLED` 门控（已由 f2-four-table-extraction-refresh 建好，复用）
- 若所有 11 张明细表共用同一 `F2DetailSheet.vue` 组件（config 驱动），则只改一处（待 Task 2.1 确认）
