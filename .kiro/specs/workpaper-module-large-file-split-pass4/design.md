# 设计文档：底稿模块大文件拆分 pass4（P1）

## 概述

3 个超标服务文件按各自最自然的内聚边界拆分，全部降到 ≤800 行。核心原则：**结构搬运、零行为变更、对外入口不变**。沿用 pass3 验证过的手法（纯函数→子模块、大 class→mixin 组合、主文件 re-export 保向后兼容）。

## 影响面（codegraph + readCode 实测）

- `wp_template_init_service`：纯函数集合，无 class。对外入口 `init_workpaper_from_template`/`prefill_workpaper_xlsx`/`find_template_file`/`find_template_file_any`/`find_all_template_files`/`get_workpaper_file`/`get_workpaper_storage_path`/`list_available_templates`。大量私有 helper（_normalize/_find_*/_mark_*/_extract_*/_is_*）。
- `wp_standard_conversion_service`：单 class `WpStandardConversionService` + 异常类 `WorkpaperConversionPreconditionError`。对外 4 方法（classify/preview/convert/check_preconditions），其余为私有 `_*`。
- `wp_fine_rule_engine`：纯函数。对外 `load_fine_rule`/`list_fine_rules`/`extract_with_fine_rule`。私有为提取（_extract_*_grid/_extract_*）+ 审计检查（_run_audit_checks/_check_*）+ 网格 helper（_grid_cell/_safe_num/_find_sheet*）。

调用点核对（拆分后必复跑 codegraph）：确保对外入口的导入路径不变；私有 helper 随其调用方迁移，不产生跨模块反向依赖。

## 拆分方案

### 1. `wp_template_init_service.py` → 主文件 + 2 子模块

建立 `backend/app/services/wp_template_init/` 包（同名模块转包，导入路径 `app.services.wp_template_init_service` 需保留——见下）：

> **导入路径策略**：保持 `wp_template_init_service.py` 为主文件（不转包），新建**同目录平级子模块** `wp_template_finder.py` + `wp_template_xlsx_ops.py`，主文件 import 并 re-export。这样对外 `from app.services.wp_template_init_service import init_workpaper_from_template` 等全部不变，零调用点改动，最稳。

```
wp_template_init_service.py    # 主：init_workpaper_from_template / prefill_workpaper_xlsx /
                               #     get_workpaper_storage_path / get_workpaper_file /
                               #     _ensure_ipo_loaded / _merge_sheets_* / 场景过滤；
                               #     末尾 re-export finder + xlsx_ops 的对外符号
wp_template_finder.py          # 模板查找：_load_index / find_template_file / find_all_template_files /
                               #     _match_filename_prefix / _find_docx_* / find_template_file_any /
                               #     list_available_templates / _normalize_sheet_name / _should_skip_historical_sheet
wp_template_xlsx_ops.py        # xlsx 单元格 helper：_extract_tb_column / _extract_adj_type /
                               #     _is_cell_coordinate / _is_formula_cell / _find_column_by_keyword /
                               #     _find_first_data_row / _mark_prefilled_cell / _mark_user_formula_cell /
                               #     _find_semantic_row / _find_data_column
```

- prefill_workpaper_xlsx（最大函数）保留在主文件，从 `wp_template_xlsx_ops` import 它依赖的 helper。
- 主文件目标 ≤700；finder ~250；xlsx_ops ~250。

### 2. `wp_standard_conversion_service.py` → 主 class + 生成 mixin

`WpStandardConversionService` 方法被测试以 `service.method()` 访问 → 用 **mixin 继承**保持方法挂在实例上：

```
wp_standard_conversion_service.py   # class WpStandardConversionService(WpConversionGenerateMixin):
                                    #   __init__ + classify_workpapers / preview_conversion /
                                    #   convert_workpapers / check_preconditions /
                                    #   _load_existing_wp_codes / _load_registry_standard_map /
                                    #   _is_applicable / _retain_shared / _archive_source_only /
                                    #   _create_target_only；异常类 WorkpaperConversionPreconditionError
wp_conversion/_generate.py          # WpConversionGenerateMixin: _generate_one_workpaper /
                                    #   _load_template_library / _derive_year / _copy_template_file /
                                    #   _populate_parsed_data（底稿生成相关，~330 行）
```

- 底稿生成块（_generate_one_workpaper 等，约 330 行）抽到 mixin，主 class 多继承组合。
- `self.db` 在 `__init__` 设置，mixin 内 `self.db` 正常访问。
- 主文件目标 ≤620；mixin ~330。

### 3. `wp_fine_rule_engine.py` → 主文件 + 审计检查子模块

```
wp_fine_rule_engine.py        # 主：load_fine_rule / list_fine_rules / extract_with_fine_rule /
                              #     _find_sheet* / _grid_cell / _safe_num /
                              #     _extract_summary_rows* / _extract_detail_rows* / _extract_adjustments* ；
                              #     末尾 re-export 审计检查符号（若有外部引用）
wp_fine_rule_checks.py        # 审计检查：_run_audit_checks / _check_balance / _check_cross_ref /
                              #     _check_movement / _check_formula / _check_completeness /
                              #     _check_aging / _check_confirmation / _check_sheet_filled / _check_reconciliation
```

- `extract_with_fine_rule` 调用 `_run_audit_checks` → 主文件 `from .wp_fine_rule_checks import _run_audit_checks`。
- 审计检查块（_run + 9 个 _check_*，约 280 行）抽出。
- 主文件目标 ≤620；checks ~280。

## 守卫与验证

- 复用 pass3 `test_wp_large_file_size_guard.py`：在目标清单加入这 3 个文件 ≤800 的断言。
- 全量：渲染冒烟 + 模板初始化/转换/精细规则相关测试 + pass2/pass3 核心 + router registry。
- `app.main` 导入无误、路由总数 1522 不变。
- codegraph 核对 import 无循环、无遗漏调用点。

## 不做的事

- 不动 pass2/pass3 已达标文件。
- 不改任何函数签名、对外入口、SQL、xlsx 提取逻辑、规则文本。
- 不拆 `workpaper_models.py`（ORM 循环导入风险，本轮不含）。
- 不为追求更小行数制造碎片；每文件 ≤800 即止。
