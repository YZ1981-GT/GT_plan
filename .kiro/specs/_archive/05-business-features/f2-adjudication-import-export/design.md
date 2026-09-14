# Design Document

## Overview

F2-1 存货审定表（13 类别 × 原值/跌价三块）加 xlsx 导入导出能力。后端在 `_f2_import_export.py` 的 `_F2_SPECS` 新增 `"F2-1"` 条目，前端 `useF2ImportExport` 扩展 `F2_IMPORT_EXPORT_SHEETS`。

## Architecture

### 决策 1：复用 `create_cycle_import_export_router` 工厂

不新建端点/路由——F2 IE 已有 `POST /f2/export-template?sheet=F2-1` / `POST /f2/export-data?sheet=F2-1` / `POST /f2/import-data?sheet=F2-1` 三端点（工厂自动注册），只需在 `_F2_SPECS` 字典加 `"F2-1"` 条目即可启用。

### 决策 2：数据模型——逐字段 item_id 写入（不用 JSON 打包）

F2-1 审定表数据存为 per-field item_id（`F2-1-{block}-{rowKey}-{field}`，值在 `conclusion` 列）。导入**逐条 upsert** `checklist_responses`（ON CONFLICT (wp_id, item_id) DO UPDATE），对齐前端 `useF2Adjudication.updateCell` 的写入路径。

导出时从 `checklist_responses WHERE item_id LIKE 'F2-1-%'` 按 item_id 解析 block/rowKey/field 重建行。

### 决策 3：两 sheet 工作表（原值 + 跌价准备）

| Sheet 名 | 行数 | 列 |
|----------|------|-----|
| 编制说明 | 参考文本 | 审定表编制方法 + 四表取数说明 |
| 原值 | 12 行（F2_CATEGORIES 除 impairment-provision） | 类别名/科目编码/期初未审/本期增加/本期减少/账项调整 |
| 跌价准备 | 1 行（impairment-provision） | 同上 |

导入时按 Sheet 名 → block 映射（原值→gross / 跌价准备→impairment），逐行按「类别名」精确匹配 `F2_CATEGORIES[].label`（兼容 rowKey），逐列解析 field。

### 决策 4：headers / field_maps / numeric_fields

```python
_F2_1_HEADERS_GROSS = ["类别名", "科目编码", "期初未审数", "本期增加", "本期减少", "账项调整"]
_F2_1_HEADERS_IMPAIRMENT = _F2_1_HEADERS_GROSS  # 同列结构

_F2_1_FIELD_MAP = {
    "期初未审数": "opening",
    "本期增加": "increase",
    "本期减少": "decrease",
    "账项调整": "adjustment",
}

_F2_1_NUMERIC_FIELDS = {"opening", "increase", "decrease", "adjustment"}
```

- 「类别名」「科目编码」为只读参考列（导入时按类别名匹配行，不靠科目编码）
- 空值/非数值字段跳过不清空既有值（R3.2）

### 决策 5：project_id 从 working_paper 反查

`INSERT checklist_responses` 带 NOT NULL `project_id`（从 `working_paper WHERE id=:wp_id` 反查），对齐 L3/J1/K 循环已修范式。

## Components and Interfaces

### 后端 `_f2_import_export.py` 改动

- `_F2_SPECS["F2-1"]`：
  - `item_id_pattern`: `"F2-1-{block}-{rowKey}-{field}"`（非单一 item_id，逐字段 upsert）
  - 自定义 `_export_f2_1` / `_import_f2_1` 函数（因 F2-1 是 per-field item_id 非 JSON 数组，不走通用 `_export_rows`/`_parse_rows`）
- 导出：查 `checklist_responses WHERE wp_id AND item_id LIKE 'F2-1-%'` → 按 item_id 解析 → 重建 {rowKey: {opening, increase, decrease, adjustment}} → 两 sheet 输出
- 导入：逐行按类别名匹配 → 各 field 非空非零 → `UPSERT(wp_id, item_id=F2-1-{block}-{rowKey}-{field}, conclusion=str(value))`
- `_SUPPORTED_SHEETS` 加 `"F2-1"`

### 前端 `useF2ImportExport` 改动

- `F2_IMPORT_EXPORT_SHEETS` 加 `{ code: 'F2-1', label: 'F2-1 存货审定表' }`
- F2TabAdjudication 工具栏加 el-dropdown「导入导出 ▾」（灰度无关，IE 是独立能力）

## Data Models

无新表/列。数据存现有 `checklist_responses` per-field item_id。

## Correctness Properties

### Property 1: 导出→导入 round-trip
导出数据 → 不改 → 导入 → 前端读取值 == 导出前值。
**Validates: Requirements 2.1, 3.1**

### Property 2: 空值不清空
导入 xlsx 某字段空 → 不覆盖 checklist_responses 既有值。
**Validates: Requirements 3.2**

### Property 3: 未知类别名跳过
导入行的「类别名」不在 F2_CATEGORIES → 跳过 + warning。
**Validates: Requirements 3.3**

### Property 4: project_id 不漏
INSERT/UPSERT 带 project_id（从 wp 反查），不违反 NOT NULL。
**Validates: Requirements 5.2**

### Property 5: 零回归
F2-3~14 IE 三端点行为逐字节不变。
**Validates: Requirements 6.1**

### Property 6: 文件名 RFC5987
导出文件名含中文正确编码。
**Validates: Requirements 1.1**

## Error Handling

- 未知 sheet (`sheet != 'F2-1'` 路由到旧逻辑) → 通用处理不变
- 导入行类别名不匹配 → skip + warning（不 400）
- openpyxl Sheet 名不匹配 → warning + imported_count=0
- 导入数值非法（非数字字符串）→ 该字段跳过

## Testing Strategy

- `test_f2_1_import_export.py`：导出→导入 round-trip（Property 1）/ 空值不清空（Property 2）/ 未知类别跳过（Property 3）/ F2-3~14 零回归（Property 5）
- `python -c "import ast; ast.parse(...)"` 语法
