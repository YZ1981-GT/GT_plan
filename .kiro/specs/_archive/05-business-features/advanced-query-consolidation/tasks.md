# Implementation Plan

## Overview

纯前端收敛：新增 3 个共享模块（列标签映射 / xlsx 导出工具 / 源 URI 解析纯函数）+ 3 组件接线复用 + 测试。零后端 / 零 DB 改动，execute 契约不变。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1"], "desc": "安全网基线 + 后端契约不变确认" },
    { "wave": 1, "tasks": ["2.1", "2.2"], "desc": "列标签共享映射 + 单测" },
    { "wave": 2, "tasks": ["3.1", "3.2"], "desc": "共享 xlsx 导出工具 + 单测" },
    { "wave": 3, "tasks": ["4.1", "4.2"], "desc": "源 URI 解析纯函数 + 单测" },
    { "wave": 4, "tasks": ["5.1", "5.2", "5.3"], "desc": "三组件接线复用" },
    { "wave": 5, "tasks": ["6.1", "6.2"], "desc": "零回归门 + Playwright" }
  ]
}
```

## Tasks

- [x] 1.1 安全网与契约基线
  - 运行并确认后端 `test_advanced_query_hardening_wave012.py::TestExecuteContractBaseline` 当前全绿（作为 Property 3 基线，本 spec 不改后端）
  - 记录 `CustomQueryDialog.COLUMN_LABELS` 现有键集合、`exportResult`/`onExportExcel`/`jumpToCell`/`onTraceToTemplate` 现有行为，作为收敛后逐字节比对基线
  - _Requirements: 4.1, 4.2_

- [x] 2.1 列标签共享映射模块
  - 新建 `src/components/query/queryColumnLabels.ts`：`QUERY_COLUMN_LABELS`（收敛 `CustomQueryDialog.COLUMN_LABELS` 全部键 + 补齐 Tab/Builder 常见列如 `standard_account_code`/`unadjusted_amount`/`aje_adjustment`/`review_status`/`work_date`/`hours` 等）+ `resolveColumnLabel(key, title?)` 三级兜底
  - _Requirements: 1.1, 1.4_

- [x] 2.2 列标签单测
  - 新建 `queryColumnLabels.spec.ts`（vitest）：Property 1（三级兜底：映射命中/title 非空≠key/key 原样）、Property 2（未知 key 原样、空 key 不抛）
  - _Requirements: 5.1_

- [x] 3.1 共享 xlsx 导出工具
  - 新建 `src/components/query/queryExport.ts`：`exportQueryResultToXlsx({columns, rows, labelFn, fileName, sheetName})`（动态 `import('xlsx')`，首行=labelFn(key) 缺省 resolveColumnLabel、数据行=row[key]??''、列宽默认）+ `sanitizeExportName`（去 `\/:*?"<>|` 与 emoji）
  - _Requirements: 2.1, 2.2_

- [x] 3.2 导出工具单测
  - 新建 `queryExport.spec.ts`（vitest，mock `xlsx`）：Property 4（aoa 首行=中文标题、数据行按 key 取值）、Property 6（sanitizeExportName 去非法字符/emoji）
  - _Requirements: 5.1_

- [x] 4.1 源 URI 解析纯函数
  - 新建 `src/components/query/querySourceUri.ts`：`buildWorkpaperUri(wpCode, sheetName?, cellRef?)`、`buildTraceUri(row, selectedSource)`（迁移 `onTraceToTemplate` 内 URI 推断逻辑）、`RESOLVE_FAIL_MSG` 文案常量
  - _Requirements: 3.1, 3.4_

- [x] 4.2 URI 纯函数单测
  - 新建 `querySourceUri.spec.ts`（vitest）：Property 7（`buildWorkpaperUri` 拼装/缺省省略段）、`buildTraceUri` 各分支（wp/report/note/source 回退）
  - _Requirements: 5.1_

- [x] 5.1 CustomQueryDialog 接线
  - 删内联 `COLUMN_LABELS`，`columnLabel` 委托 `resolveColumnLabel`；`exportResult` 委托 `exportQueryResultToXlsx`（文件名沿用现「项目_源_年度」经 sanitizeExportName）；`jumpToCell`/`onTraceToTemplate` 的 URI 构造委托 `querySourceUri`（跳转目标与提示不变）
  - get_diagnostics 全清 + `curl.exe` Vite transform 200
  - _Requirements: 1.2, 2.2, 3.1, 3.2, 3.3, 4.2_

- [x] 5.2 CustomQueryTab 接线
  - `displayColumns` 的 `title` 经 `resolveColumnLabel(key, meta.title)`；字段选择 checkbox 标签中文化；`onExportExcel` 委托 `exportQueryResultToXlsx`
  - get_diagnostics 全清 + Vite transform 200
  - _Requirements: 1.2, 2.1_

- [x] 5.3 AdvancedQueryBuilder 接线
  - `resultColumns` title 经 `resolveColumnLabel`；`doExport` 文件名经 `sanitizeExportName` 对齐（保留后端 `query/export-excel` blob 路径不变）
  - get_diagnostics 全清 + Vite transform 200
  - _Requirements: 1.2, 2.3_

- [x] 6.1 零回归门
  - 后端 `TestExecuteContractBaseline` 全绿（Property 3，确认未改后端）；三组件 get_diagnostics 全清 + Vite transform 200；三个 vitest spec 全绿；确认业务视图已交付基线能力（行数上限/历史/选区自动取数/转置空态/formatCell）行为不变
  - _Requirements: 4.1, 4.2, 4.3, 5.1_

- [x]* 6.2* Playwright 关键路径
  - 业务视图与高级构建器列名一致（中文）、导出 xlsx、cell_ref 下钻跳 WorkpaperEditor、右键溯源跳 /template-library；0 console error
  - _Requirements: 3.5, 5.2_

## Notes

- 零后端 / 零 DB：不改 `custom_query.py`、不新增迁移。
- 复用优先：三方复用共享模块，不复制导出/标签/URI 逻辑。
- Builder 保留后端 blob 导出（大数据），仅对齐文件名/列标题口径，不强改为前端 xlsx。
