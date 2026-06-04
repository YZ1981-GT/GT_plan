# Tasks: xlsx 读路径 calamine 加速推广

## Overview

按 design 分 4 组：① 适配器 + 配置 → ② 逐点等价测试先行 → ③ 逐点切换 → ④ 性能验证 + 收尾。核心铁律：**先证等价再切**，每点独立可回退。

**勘察结论（实施前必读）**：
- 可复用：`backend/app/services/ledger_import/parsers/excel_parser_calamine.py` 的 `_load_sheet(path_or_bytes, sheet_name) -> list[list]`（内部 `CalamineWorkbook.from_path` / `from_filelike` + `wb.sheet_names` + `get_sheet_by_name(...).to_python()`）。**注意 `_load_sheet` 要求 sheet_name 必填且不存在时 raise RuntimeError**——适配器 `sheet_name=None`（取第一个表/活动表）需先 `wb.sheet_names[0]` 解析。
- 等价测试范式：`backend/tests/ledger_import/test_excel_parser_calamine.py` 已有归一化断言（`_norm` 处理 int/float 容忍 + None/"" 归一），直接参照。
- feature flag 体系：`backend/app/services/feature_flags.py` 有 `ledger_import_use_calamine`（含 `set_project_flag` 项目级回退）+ `is_enabled(flag, project_id)`。新开关与之解耦。
- 迁移点已确认（grep load_workbook 实证）：
  - **可迁移（纯取值 data_only=True）**：`wp_program_extract.py`(line 192) / `wp_audit_sheet_extract.py`(line 474/509/541 三处) / `wp_generic_processor.py`(line 84) / `wp_template_diff_service.py`(line 71) / `wp_fine_rule_engine.py`(line 139) / `import_template_service.py`(line 352/478)
  - **不迁移（样式依赖）**：`wp_grid_extract.py`(line 354，读 fill/bold/merged_cells/col_width)
  - **不迁移（写/公式）**：`wp_xlsx_export_service` / `report_excel_exporter` / `xlsx_to_univer`(data_only=False+True 双载读公式) / `prefill_engine` 写回 / `wp_header_service` / `wp_template_init_service`
- 真实模板路径：`backend/wp_templates/`（按循环分目录），D1 等审定表/程序表模板在此。

## Tasks

### 组 ① 统一只读取值适配器 + 配置

- [x] 1. 新建 `backend/app/services/xlsx_read_adapter.py`
  - `def read_sheet_values(path, sheet_name=None, *, prefer_calamine=True) -> list[list[Any]]`
    - sheet_name=None：calamine 走 `CalamineWorkbook.from_path(path).sheet_names[0]`；openpyxl 走 `wb.active`
    - calamine 分支：复用/调 `excel_parser_calamine._load_sheet(path, resolved_sheet_name)`
    - 降级分支：`openpyxl.load_workbook(path, read_only=True, data_only=True)` + `ws.iter_rows(values_only=True)` → `[list(r) for r in ...]`
    - 归一化层 `_normalize_row`：calamine `""`→`None`（与 openpyxl 空 cell 对齐）；int/float 保持（消费方容忍）
    - `prefer_calamine and settings.XLSX_READ_USE_CALAMINE and _calamine_available()` 才走 calamine，否则 openpyxl
  - `def list_sheet_names(path) -> list[str]`：calamine `wb.sheet_names` / openpyxl `wb.sheetnames`
  - `_calamine_available()`：try import python_calamine（模块级缓存），失败 False
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.2_

- [x] 2. 配置项
  - `backend/app/core/config.py` 加 `XLSX_READ_USE_CALAMINE: bool = True`（独立于 ledger_import_use_calamine）
  - `.env.example` 同步
  - _Requirements: 4.1, 4.3_

- [x] 3. 适配器单测 `backend/tests/test_xlsx_read_adapter.py`
  - 构造小 xlsx fixture（openpyxl 写）→ `read_sheet_values(prefer_calamine=True)` vs `prefer_calamine=False` 输出等价（归一化后）
  - calamine 不可用（monkeypatch `_calamine_available`→False）降级 openpyxl
  - `XLSX_READ_USE_CALAMINE=False` 走 openpyxl
  - sheet_name=None 取第一个表 / 多 sheet 指定名 / sheet 不存在行为
  - _Requirements: 1.4, 3.2, 4.3_

- [x] 4. 检查点 — 适配器单测全绿

### 组 ② 逐点等价测试先行（先证再切）

- [x] 5. `wp_program_extract` 等价测试
  - 取真实程序表模板（如 `backend/wp_templates/D-销售收入循环/` 下含程序表的 xlsx）
  - 临时双路径：`extract_program_rows` 用 read_sheet_values(calamine) vs 现 openpyxl 提取结果断言 == （程序行数/认定映射/索引列一致）
  - _Requirements: 3.1, 3.2_

- [x] 6. `wp_audit_sheet_extract` 等价测试（三函数）
  - `extract_audit_rows` / `extract_audit_sections` / `extract_audit_rows_with_values` 对真实审定表模板（D1-1 等）calamine vs openpyxl 等价
  - 重点验证：合并单元格区的取值（审定表多合并）calamine 展平值是否与 openpyxl 一致——**不一致则该函数标记回退**
  - _Requirements: 3.1, 3.2_

- [x] 7. 其余点等价测试
  - `wp_generic_processor` / `wp_template_diff_service` / `wp_fine_rule_engine` / `import_template_service` 各对真实模板 calamine vs openpyxl 等价
  - 发现合并/取值差异影响结果的点 → 记入"回退清单"（保持 openpyxl，不切）
  - _Requirements: 3.1, 4.4_

- [x] 8. 检查点 — 所有可迁移点等价测试通过；不等价点登记回退清单（写入本 tasks 末尾或 design 注释）

### 组 ③ 逐点切换到适配器

- [x] 9. 切换 `wp_program_extract`（line ~192）→ read_sheet_values
  - 前置：task 5 等价测试已通过（先证再切）
  - 把 `openpyxl.load_workbook(...) + ws.iter_rows` 换为 `rows = read_sheet_values(fp, sheet_name)`，下游遍历逻辑不变
  - _Requirements: 2.1, 3.3, 6.1, 6.2_

- [x] 10. 切换 `wp_audit_sheet_extract` 三函数（line ~474/509/541）→ read_sheet_values
  - 前置：task 6 等价测试已通过；task 6 标记回退的函数保持 openpyxl
  - _Requirements: 2.1, 3.3, 6.1, 6.2_

- [x] 11. 切换其余点（`wp_generic_processor`/`wp_template_diff_service`/`wp_fine_rule_engine`/`import_template_service` 读取部分）
  - 前置：task 7 等价测试已通过
  - task 7/8 回退清单中的点保持 openpyxl（不切）
  - _Requirements: 2.1, 2.4, 3.3, 6.1, 6.2_

- [x] 12. 确认未迁移点不动（防误改）
  - `wp_grid_extract`(line 354 样式) / 写路径(wp_xlsx_export/report_excel_exporter/prefill 写回) / `xlsx_to_univer`(公式双载) / `wp_header_service` / `wp_template_init_service` 保持 openpyxl
  - grep 确认这些文件无 `read_sheet_values` 引入
  - _Requirements: 2.2, 2.3_

- [x] 13. 检查点 — 各提取点原有单元测试全绿（`test_wp_program_extract` / `test_wp_audit_sheet_extract` / `test_wp_grid_extract` 等无回归）

### 组 ④ 性能验证 + 收尾

- [x] 14. 性能微基准 `backend/tests/test_xlsx_read_benchmark.py`（或 `backend/scripts/analyze/` 脚本）
  - 真实 D1.xlsx 等模板：`read_sheet_values` calamine vs openpyxl 各跑 N 次取均值，记录耗时
  - 软断言/记录加速比（3-5× 量级；用 `>1.5×` 软门限避免环境抖动 flaky，主要是记录而非强卡）
  - _Requirements: 5.1, 5.2_

- [x] 15. 最终检查点
  - `python -m pytest backend/tests/test_xlsx_read_adapter.py backend/tests/test_wp_program_extract.py backend/tests/test_wp_audit_sheet_extract.py backend/tests/test_wp_grid_extract.py -v` 全绿
  - `XLSX_READ_USE_CALAMINE=False` 回退路径验证（所有迁移点走 openpyxl 行为不变）
  - 回退清单（不可迁移点）记录在案
  - _Requirements: 6.1, 6.2_

## 回退清单（组②等价测试后填写）

> 等价测试发现 calamine 与 openpyxl 输出不一致、影响结果的提取点登记于此，保持 openpyxl：
> - `import_template_service.validate_import_file` / `parse_import_data` —— 操作对象是 BytesIO（用户上传字节流），非磁盘文件路径，read_sheet_values 适配器不支持 BytesIO 输入，保持 openpyxl
> - `wp_audit_sheet_extract.extract_audit_rows_with_values_from_file` —— 需要 ws.cell 逐列访问模式（多列明细表值提取 + column_defs 动态匹配），保持 openpyxl（extract_audit_rows / extract_audit_sections 已切换）
