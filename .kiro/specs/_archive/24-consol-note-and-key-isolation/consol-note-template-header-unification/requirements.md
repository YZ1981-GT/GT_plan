# 统一合并附注模板与单体附注模板的表头格式

## 背景

平台有**两套独立的附注模板体系**，表头格式不兼容：

| 维度 | 单体附注模板 | 合并附注模板 |
|------|------|------|
| 文件 | `note_template_soe/listed.json` | `consol_note_sections_soe/listed.json` |
| 表头分组 | `_column_groups`（前端消费 ✅） | `multi_header`（前端仅 P0 修复后消费） |
| 行结构 | `{label, end_amount, prior_amount, is_total}` 字典 | `["库存现金", "", ""]` 二维数组 |
| 列定义 | `columns[{key, label, is_label, format}]` | `headers["项目", "期末余额", "期初余额"]` 扁平字符串 |
| 数据来源 | 前端 `buildXSyncPayload` 推送 | 后端 `refresh_note_by_formula` 从 TB 填 |
| 生成方式 | 从 md 模板自动提取 | `seed_consol_note_sections.py` 脚本从 Word 样式提取 |

两套格式的不兼容导致：
1. 合并附注的公式种子引擎（`consol_note_formula_service`）遇到 `multi_header` 非 null 时**列不确定、不种公式**
2. 合并附注刷新（`refresh_note_by_formula`）对多级表头的列匹配靠字符串包含（`"期末" in h`），不精确
3. 前端需要维护两套渲染逻辑（`DisclosureEditor` 用 `_column_groups`，`ConsolNoteTab` 用扁平 `headers` + P0 新增的 `multi_header` 解析）
4. 导入导出走两条不同的列映射路径

## 现状实证（2026-10-05 现算）

| 编号 | 事实 |
|------|------|
| P2-S1 | 合并 soe 模板 221 张表中 `multi_header` 非 null 的有 **3 张**（五-5-1 应收账款账龄、五-5-2 应收账款分类、五-8-1 其他应收账款账龄） |
| P2-S2 | 合并 listed 模板 282 张表情况须现算 |
| P2-S3 | 单体 soe 模板 304 张表中有 `_column_groups` 的须现算 |
| P2-S4 | `seed_consol_note_sections.py` 从 Word 表格提取多行表头为 `multi_header`（空字符串表示被合并），同时用斜杠拼接为 `headers`（如 `"期末数/账面余额/金额"`） |
| P2-S5 | `consol_note_formula_service.py` 的 `value_column()` 对 `headers` 中有空列名的（即 `multi_header` 展开导致的占位空串）返回"列不确定"，**不种公式** |
| P2-S6 | ConsolNoteTab.vue P0 已修复 `multi_header` 渲染（嵌套 `el-table-column`），但合并附注的**编辑、保存、公式种子**仍依赖二维数组 `rows` 结构 |

## 需求

### 需求 1：合并附注模板补齐 `_column_groups`

1. `seed_consol_note_sections.py` SHALL 在生成合并附注模板时，同时产出 `_column_groups`（与单体附注模板同格式）
2. `_column_groups` SHALL 从 `multi_header` 自动推导（`multi_header` 保留作为 Word 导出的原始数据源）
3. 无 `multi_header` 的表 SHALL 不生成 `_column_groups`（保持扁平）

### 需求 2：合并附注数据结构向字典行靠拢

1. 合并附注的行数据 SHALL 支持字典格式 `{label, end_amount, prior_amount, ...}`（与单体附注对齐）
2. 二维数组格式 SHALL 保持向后兼容（已保存的用户数据不迁移）
3. `refresh_note_by_formula` 和 `consol_note_formula_service` SHALL 按列 `key`（`end_amount`/`prior_amount`）取数，不按表头字符串匹配

### 需求 3：ConsolNoteTab 渲染统一

1. ConsolNoteTab.vue SHALL 能同时渲染字典行和二维数组行（按数据类型自动适配）
2. 有 `_column_groups` 时 SHALL 优先用分组表头渲染（与 DisclosureEditor 同逻辑）
3. `multi_header` 解析（P0 实现）SHALL 保留作为降级路径

### 需求 4：公式种子能力

1. `consol_note_formula_service.plan_seed()` 的 `value_column()` SHALL 按 `_column_groups` 定位列（而非按 `headers` 空列名判定）
2. 有 `_column_groups` 的合并附注表 SHALL 能正确种公式（当前因"列不确定"被跳过的 3 张表）

### 需求 5：验收

1. 模板重生成后 `--check` 幂等
2. 已保存的合并附注数据加载和编辑不受影响（向后兼容）
3. ConsolNoteTab 渲染在四种组合（有/无 _column_groups × 字典/数组行）下正确
4. 公式种子对应收账款等 3 张 multi_header 表能成功种公式

## 非目标

- 迁移已保存的用户数据到字典格式（运行时兼容即可）
- 重写 `seed_consol_note_sections.py` 的 Word 提取逻辑
- 单体附注改为二维数组行
