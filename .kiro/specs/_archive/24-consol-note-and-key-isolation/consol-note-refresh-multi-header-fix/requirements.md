# 完善合并附注刷新对多级表头的列定位

## 背景

上游：`consol-note-template-header-unification`（P2，模板层加 `_column_groups`）

合并附注的"按公式填入"和"刷新"功能通过 `consol_note_sections.py` 的 `refresh_note_by_formula` 端点实现。当前列定位逻辑有两个层面：

1. **合并附注公式种子**（`consol_note_formula_service.py`）：`value_column()` 按 headers 关键词匹配，`multi_header` 非 null 时因空列名而"列不确定"不种公式 → P2 通过 `_column_groups` 解决
2. **合并附注刷新**（`refresh_note_by_formula` 端点）：直接按 `headers` 字符串匹配列，逻辑更粗糙

本 spec 专注于第 2 层——让 `refresh_note_by_formula` 端点正确处理所有表头结构。

## 现状实证（2026-10-05 现算）

| 编号 | 事实 |
|------|------|
| P3-S1 | `refresh_note_by_formula` 的列匹配逻辑：`h_lower = h.replace(" ", "").replace("　", "")` 然后 `if "期末" in h_lower or "本期" in h_lower`，对扁平表头基本可用，但 `multi_header` 展开后 headers 含斜杠路径（如 `"期末数/账面余额/金额"`）会命中多列 |
| P3-S2 | 合并附注行数据是二维数组 `[["库存现金", "", ""], ...]`，刷新写入用 `new_row[ci] = str(matched["audited"])` 按列索引写 |
| P3-S3 | 合并附注的试算表取数（`_load_tb_map`）返回 `{科目名: {audited, opening}}`，按科目名匹配行（`tb_map.get(clean_name)`），对有标准码前缀的科目不走试算表而走合并报表值 |
| P3-S4 | 合并附注刷新只有在合并项目（有企业树）时才有数据源——单体项目不走此端点 |
| P3-S5 | "按公式填入"（`fill_note_by_formula` 端点）走的是另一条路径——`consol_note_formula_service.fill_by_formula`，按种子公式求值填入，列定位用 `value_column` 的结果。P2 完成后此路径已修复 |
| P3-S6 | 合并附注共 4 个数据操作端点：`get`/`save`/`refresh`/`fill-by-formula`/`audit-all`，其中只有 `refresh` 和 `fill-by-formula` 涉及列定位 |

## 需求

### 需求 1：列定位改进

1. `refresh_note_by_formula` SHALL 优先按 `_column_groups`（P2 产出）定位数值列
2. 当 `_column_groups` 可用时，SHALL 按组名（如"期末数"/"期初数"/"本期数"）定位到组内第一个数值列
3. 降级逻辑（无 `_column_groups`）SHALL 保持原行为

### 需求 2：多级表头精确匹配

1. 对 `multi_header` 非 null 的表，SHALL 定位到叶子列而非分组列
2. 应收账款账龄表（`multi_header` 2 行）：期末数→账面余额列、期初数→账面余额列
3. 应收账款分类表（`multi_header` 3 行）：期末数→账面余额→金额列、期初数→账面余额→金额列

### 需求 3：向后兼容

1. 无 `multi_header` / 无 `_column_groups` 的表 SHALL 行为不变
2. 已保存的二维数组行数据 SHALL 按列索引正确写入

### 需求 4：验收

1. 3 张 multi_header 表的刷新结果列值正确（不在错误列上）
2. 简单表头（无分组）的刷新行为不变
3. 合并附注全套端点回归

## 非目标

- `fill_note_by_formula` 端点改进（P2 已处理）
- 合并附注数据格式迁移
- 单体附注的列定位（单体附注用 `note_writer.py` 的不同列定位逻辑）
