# Requirements Document

## Introduction

F2-1 存货审定表（13 类别 × 原值/跌价/净值三块）当前**无导入导出能力**——后端 `_f2_import_export.py` 的 IE spec（`_SHEET_ITEM_ID` / `_FIELD_MAPS` / `_SHEET_HEADERS`）只覆盖 F2-3~F2-13 明细 + F2-14 调整 + F2-16~F2-20 分析/检查，唯独缺 `F2-1`。审计师无法离线填写审定表再导入、无法导出当前审定数据备份/复核。

### 实测依据

- `_f2_import_export.py` 的 `_F2_SPECS` 字典无 `"F2-1"` 键（grep 确认）
- 前端 `useF2ImportExport` 的 `F2_IMPORT_EXPORT_SHEETS` 清单无 `F2-1`
- F2-1 数据存 `checklist_responses`：`F2-1-{gross|impairment}-{rowKey}-{opening|increase|decrease|adjustment}`（值在 conclusion 字段），共 39+13=52 可编辑锚点（39 取数 + 13 adjustment）
- 审定表 render 输出 `F2_CATEGORIES`（13 类别 rowKey/label/account）

### 与 `f2-four-table-extraction-refresh` 的关系

本 spec 只做"F2-1 审定表的 xlsx 导入导出"（IE），不碰取数公式/刷新/公式管理（那是前一 spec 范畴）。导出模板含编制说明（标明四表取数可用），导入只写可编辑字段不改 computed 列。

## Requirements

### Requirement 1: F2-1 审定表导出模板

**User Story:** 作为审计助理，我希望能导出 F2-1 审定表的 xlsx 填写模板（含编制说明+行骨架+列头）。

#### Acceptance Criteria

1. WHEN 用户在 F2-1 审定表点「导入导出 ▾ → 导出模板」 THEN 系统 SHALL 返回 xlsx 文件（RFC5987 中文文件名：`F2-1 存货审定表_模板.xlsx`），含：
   - Sheet 1「编制说明」：审定表编制方法+四表取数说明+各字段含义
   - Sheet 2「原值」：13 行（类别 rowKey→中文 label）× 列（类别名/科目编码/期初/本期增加/本期减少/账项调整），表头 row 1
   - Sheet 3「跌价准备」：1 行（存货跌价准备 1471）× 同列结构
2. WHEN 导出模板 THEN 各行的「类别名」「科目编码」为只读参考（导入时按行序/类别名匹配，非按科目编码）。
3. WHERE 列名 THE 系统 SHALL 与前端 F2TabAdjudication 表头一致（期初未审数/本期增加/本期减少/账项调整）。

### Requirement 2: F2-1 审定表导出数据

**User Story:** 作为审计助理/复核人，我希望能导出 F2-1 审定表当前数据供离线核对/备份。

#### Acceptance Criteria

1. WHEN 用户点「导出数据」 THEN 系统 SHALL 返回 xlsx（文件名含时间戳），结构同模板但**填入当前 checklist_responses 值**。
2. WHERE 某锚点无值 THE 系统 SHALL 对应单元格空（不填 0），区分「未填」与「真实为 0」。
3. WHERE 值含千分符/显示格式 THE 系统 SHALL 导出原始数字（不含千分符），Excel 格式为数值两位小数。

### Requirement 3: F2-1 审定表导入

**User Story:** 作为审计助理，我希望能从 xlsx 导入 F2-1 审定表数据（离线填好后回导）。

#### Acceptance Criteria

1. WHEN 用户点「导入数据」上传 xlsx THEN 系统 SHALL 解析 Sheet 2「原值」和 Sheet 3「跌价准备」，按行匹配（类别名精确匹配 F2_CATEGORIES[].label，兼容 rowKey），逐字段写 checklist_responses（opening/increase/decrease/adjustment）。
2. WHERE 导入某字段值为空/非数值 THE 系统 SHALL 跳过该字段（不清空既有值）。
3. WHERE 导入行的类别名不在 F2_CATEGORIES THE 系统 SHALL 跳过该行 + warning。
4. WHEN 导入完成 THEN 系统 SHALL 返回 `imported_count` / `skipped_count` / `field_count`。
5. WHERE 后端 INSERT checklist_responses THE 系统 SHALL 带 `project_id`（NOT NULL，从 working_paper 反查），ON CONFLICT (wp_id, item_id) DO UPDATE。

### Requirement 4: 前端 UI 入口

**User Story:** F2-1 审定表工具栏加「导入导出 ▾」下拉（导出模板/导出数据/导入数据）。

#### Acceptance Criteria

1. WHEN F2-1 审定表工具栏 THEN 系统 SHALL 显示 el-dropdown「导入导出 ▾」（三项：导出模板/导出数据/导入数据），受编辑权限门控（只读隐藏导入）。
2. WHEN 导入成功 THEN 系统 SHALL 调 reloadFromServer 重新加载 checklist_responses 刷新页面。
3. WHERE 复用 `useF2ImportExport` THE 系统 SHALL 只扩展 `F2_IMPORT_EXPORT_SHEETS` 加 `F2-1`（其余 F2-3~14 IE 不动）。

### Requirement 5: 后端 IE spec 注册

**User Story:** 作为平台维护者，后端 IE spec 须正确注册 F2-1 条目，导入带 project_id 不违反 NOT NULL。

#### Acceptance Criteria

1. WHEN 后端 `_f2_import_export.py` THE 系统 SHALL 在 `_F2_SPECS` 新增 `"F2-1"` 条目：
   - `item_id`: `"F2-1-adjudication-data"`（或改用逐字段 item_id 写入，按 `F2-1-{block}-{rowKey}-{field}`）
   - `storage_field`: `"conclusion"`（对齐前端 `loadField` 读 `.conclusion`）
   - `_SHEET_HEADERS["F2-1"]`: 与模板列头一致
   - `_FIELD_MAPS["F2-1"]`: 行名→rowKey + 字段名→field 映射
   - `_NUMERIC_FIELDS`: opening/increase/decrease/adjustment
2. WHEN 导入 THE 后端 SHALL 带 project_id（从 working_paper 反查，不漏 NOT NULL）。

### Requirement 6: 零回归

**User Story:** 作为平台维护者，新增 F2-1 IE 不破坏既有 F2-3~14 IE 及其他联动。

#### Acceptance Criteria

1. WHEN 新增 F2-1 IE THEN 现有 F2-3~14 IE 的 export-template/export-data/import-data 三端点行为 SHALL 逐字节不变。
2. WHEN 导入 F2-1 THEN F2-3~13 明细表/F2-14 调整分录/审定表跨表联动/附注联动/四表取数面板 SHALL 不受影响。

## Glossary

| 术语 | 含义 |
|------|------|
| F2-1 审定表 | 13 类别 × 原值/跌价/净值三块，数据存 checklist_responses conclusion |
| IE spec | `_F2_SPECS` 字典条目（item_id/storage_field/headers/field_maps/numeric_fields） |
| `create_cycle_import_export_router` | 通用循环 IE 工厂（POST export-template/export-data/import-data，query `sheet`） |
| `F2_IMPORT_EXPORT_SHEETS` | 前端下拉可选 sheet 清单 |
