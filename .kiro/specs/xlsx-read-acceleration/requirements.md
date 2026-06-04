# Requirements: xlsx 读路径 calamine 加速推广

## Introduction

python-calamine（Rust xlsx 解析）已在账表导入链路成熟落地并验证（feature flag + 行为等价测试 + 500k 行动态切换 + 内存降级，实测 3-5× 提速）。本 spec 把这套**已验证的只读取值能力推广到底稿模板提取场景**（程序表/审定表/通用处理/模板 diff 等纯取值点），复用既有等价性方法论，提升底稿加载速度。**写路径与依赖样式/公式/合并单元格的提取点（如 wp_grid_extract）不迁移，保持 openpyxl。**

## Glossary

- **calamine / python-calamine**: Rust 实现的 xlsx 解析库，纯读取值（不含样式/公式/合并元数据），比 openpyxl 快 3-5×
- **纯读取值点**: 只调 `iter_rows(values_only=True)` 取单元格值、不读样式/公式的 openpyxl 使用点
- **样式依赖点**: 需要 fill/bold/merged_cells/col_width 的提取点（如 wp_grid_extract），不可迁移
- **写路径**: 用 openpyxl 写入/导出 xlsx 的场景（导出/预填回写），不迁移
- **xlsx_read_adapter**: 新建统一只读取值入口，内部按 flag 选 calamine/openpyxl
- **行为等价测试**: 对同一文件 calamine 与 openpyxl 输出做数值语义相等断言（先证等价再切）
- **XLSX_READ_USE_CALAMINE**: 只读取值统一开关，独立于 ledger import 的 flag

## Requirements

### Requirement 1: 统一只读取值适配器

**User Story:** As a 后端开发者, I want 一个统一的 `read_sheet_values(path, sheet_name)` 入口, so that 所有纯取值的底稿提取点共用一套 calamine/openpyxl 切换与归一化逻辑。

#### Acceptance Criteria
1. THE 系统 SHALL 提供 `xlsx_read_adapter.read_sheet_values(path, sheet_name=None, *, prefer_calamine=True) -> list[list[Any]]` 与 `list_sheet_names(path)`。
2. WHEN `prefer_calamine` 真且 calamine 可用, THE 适配器 SHALL 走 CalamineWorkbook（复用 `excel_parser_calamine` 加载逻辑）。
3. WHEN calamine 不可用（未安装/导入失败）, THE 适配器 SHALL 自动降级 openpyxl `read_only=True, data_only=True`。
4. THE 适配器 SHALL 做数值归一化（int/float 容忍、空单元格 calamine `""`→`None`），保证替换 openpyxl 后消费方行为等价。

### Requirement 2: 只迁移纯取值点，保护样式/写路径

**User Story:** As a 后端开发者, I want 仅迁移不依赖样式的只读点, so that calamine 无样式的限制不破坏依赖样式的功能。

#### Acceptance Criteria
1. THE 系统 SHALL 迁移以下纯取值点到 `read_sheet_values`：`wp_program_extract` / `wp_audit_sheet_extract`（extract_audit_rows/sections/with_values）/ `wp_generic_processor` / `wp_template_diff_service` / `wp_fine_rule_engine` / `import_template_service` 读取部分。
2. THE 系统 SHALL NOT 迁移 `wp_grid_extract`（依赖 fill/bold/merged_cells/col_width 样式）。
3. THE 系统 SHALL NOT 迁移写路径与公式文本依赖点（`wp_xlsx_export_service` / `report_excel_exporter` / `xlsx_to_univer` / `prefill_engine` 写回 / `wp_header_service`）。
4. WHERE 某迁移点的等价测试发现合并单元格/取值差异影响结果, THE 系统 SHALL 该点回退 openpyxl 并记录原因。

### Requirement 3: 行为等价先行

**User Story:** As a 开发者, I want 每个迁移点先有 calamine vs openpyxl 等价测试再切换, so that 不引入静默数据差异。

#### Acceptance Criteria
1. THE 每个迁移点 SHALL 先有"同一真实底稿模板 calamine 输出 == openpyxl 输出（数值语义）"的等价测试。
2. THE 等价测试 SHALL 参照现有 `test_excel_parser_calamine.py` 的归一化断言模式（int/float 容忍、空值归一）。
3. WHEN 等价测试通过, THE 该提取点方可切换到 `read_sheet_values`。

### Requirement 4: 配置开关与回退

**User Story:** As a 运维, I want 全局开关 + 单点回退, so that calamine 在某场景出问题时可快速降级不影响整体。

#### Acceptance Criteria
1. THE 系统 SHALL 提供 `XLSX_READ_USE_CALAMINE`（默认 True），独立于 `ledger_import_use_calamine`。
2. THE 适配器 SHALL 支持调用点 `prefer_calamine=False` 局部回退。
3. WHEN `XLSX_READ_USE_CALAMINE` 为假, THE 所有迁移点 SHALL 走 openpyxl（行为与迁移前一致）。

### Requirement 5: 性能验证

**User Story:** As a 性能工程师, I want 微基准证明加速, so that 确认推广有实际收益。

#### Acceptance Criteria
1. THE 系统 SHALL 对真实底稿模板（如 D1.xlsx）做 calamine vs openpyxl 读耗时微基准并记录。
2. THE 加速比 SHOULD 与 ledger import 基线一致（3-5× 量级）。

### Requirement 6: 不回归

#### Acceptance Criteria
1. THE 迁移后 SHALL 通过各提取点原有单元测试（wp_program_extract / wp_audit_sheet_extract / wp_grid_extract 等现有测试全绿）。
2. THE 迁移 SHALL NOT 改变各提取点对外返回结构（行项目/程序行/diff 结果等）。
