# Implementation Plan

## Overview

F2-1 存货审定表 xlsx 导入导出。3 波 7 任务，后端 `_F2_SPECS["F2-1"]` + 前端扩展。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "W0", "name": "后端 IE 实现", "tasks": ["1.1", "1.2"] },
    { "id": "W1", "name": "前端入口 + 接线", "tasks": ["2.1", "2.2"] },
    { "id": "W2", "name": "测试 + 验证", "tasks": ["3.1", "3.2", "3.3"] }
  ]
}
```

## Tasks

- [x] 1. Wave 0 — 后端 IE 实现
  - [x] 1.1 `_f2_import_export.py` 加 F2-1 导出
  - [x] 1.2 `_f2_import_export.py` 加 F2-1 导入

- [x] 2. Wave 1 — 前端入口 + 接线
  - [x] 2.1 `useF2ImportExport` 扩展
  - [x] 2.2 `F2TabAdjudication.vue` 工具栏加「导入导出 ▾」

- [x] 3. Wave 2 — 测试 + 验证
  - [x] 3.1 后端测试 `test_f2_1_import_export.py`
  - [x] 3.2 前端验证
  - [ ] 3.3* live round-trip（可选，需实例化 F2 项目）

## Notes

- F2-1 IE 走自定义导出/导入函数（per-field item_id 非 JSON 数组，不适合通用 `_export_rows`/`_parse_rows`）
- 编制说明 sheet 含四表取数提示 + 各字段含义
- 导入 project_id 从 working_paper 反查（NOT NULL，对齐 L3/J1 范式）
- F2-3~14 IE 不动（零回归）
