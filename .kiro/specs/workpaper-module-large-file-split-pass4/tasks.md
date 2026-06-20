# 实施计划：底稿模块大文件拆分 pass4（P1）

## 概述

3 个超标服务文件按内聚边界拆到 ≤800 行，零行为变更。每文件独立 Sprint，互不阻塞，每 Sprint 末验证零回归。语言：Python（FastAPI + SQLAlchemy + pytest）。沿用 pass3 打法：纯函数→平级子模块、大 class→mixin、主文件 re-export 保导入路径。

## Tasks

- [x] 1. 先扩文件大小守卫（红灯起步）
  - [x] 1.1 在 `backend/tests/test_wp_large_file_size_guard.py` 加入 pass4 三目标
    - 断言 `wp_template_init_service.py`/`wp_standard_conversion_service.py`/`wp_fine_rule_engine.py` ≤800 行
    - 同时保留 pass2/pass3 已达标文件未回升断言
    - 此时预期红灯（3 文件超标），确认守卫准确
    - _Requirements: 4.1, 4.2_

- [x] 2. Sprint A：`wp_template_init_service.py` → 主文件 + 2 子模块（Req 1）
  - [x] 2.1 建 `wp_template_finder.py`（模板查找域）
    - 迁移 `_load_index`/`find_template_file`/`find_all_template_files`/`_match_filename_prefix`/`_find_docx_on_disk`/`_find_docx_by_index_or_disk`/`find_template_file_any`/`list_available_templates`/`_normalize_sheet_name`/`_should_skip_historical_sheet`，逐字搬运
    - _Requirements: 1.2_
  - [x] 2.2 建 `wp_template_xlsx_ops.py`（单元格 helper 域）
    - 迁移 `_extract_tb_column`/`_extract_adj_type`/`_is_cell_coordinate`/`_is_formula_cell`/`_find_column_by_keyword`/`_find_first_data_row`/`_mark_prefilled_cell`/`_mark_user_formula_cell`/`_find_semantic_row`/`_find_data_column`，逐字搬运
    - _Requirements: 1.2_
  - [x] 2.3 主文件 import 子模块 + re-export 对外符号
    - 保留 `init_workpaper_from_template`/`prefill_workpaper_xlsx`/`get_workpaper_storage_path`/`get_workpaper_file`/`_ensure_ipo_loaded`/`_merge_sheets_*` 等主流程；从子模块 import 依赖的 helper；末尾 re-export finder 的对外函数保导入路径不变
    - _Requirements: 1.3_
  - [x] 2.4 验证 Sprint A 零回归
    - `wp_template_init_service.py` ≤800；getDiagnostics 三文件无误；`from app.main import app` 无误
    - 跑模板初始化/预填相关测试全绿
    - _Requirements: 1.1, 1.4, 4.4_

- [x] 3. Sprint A 检查点
  - 对外入口导入路径不变、相关测试通过，如有问题向用户确认。

- [x] 4. Sprint B：`wp_standard_conversion_service.py` → 主 class + 生成 mixin（Req 2）
  - [x] 4.1 建 `wp_conversion/_generate.py`（WpConversionGenerateMixin）
    - 迁移 `_generate_one_workpaper`/`_load_template_library`/`_derive_year`/`_copy_template_file`/`_populate_parsed_data`，方法含 `self` 逐字搬运
    - _Requirements: 2.2_
  - [x] 4.2 主 class 改为 mixin 组合
    - `class WpStandardConversionService(WpConversionGenerateMixin)`，保留 `__init__` + classify/preview/convert/check_preconditions + 其余私有方法；确认 `self.db` 在 mixin 内可访问；异常类 `WorkpaperConversionPreconditionError` 保留主文件
    - _Requirements: 2.2, 2.3_
  - [x] 4.3 验证 Sprint B 零回归
    - `wp_standard_conversion_service.py` ≤800；对外 4 方法挂实例上；相关测试全绿
    - _Requirements: 2.1, 2.3, 2.4, 4.4_

- [x] 5. Sprint B 检查点
  - WpStandardConversionService 对外方法零变更、相关测试通过，如有问题向用户确认。

- [x] 6. Sprint C：`wp_fine_rule_engine.py` → 主文件 + 审计检查子模块（Req 3）
  - [x] 6.1 建 `wp_fine_rule_checks.py`（审计检查域）
    - 迁移 `_run_audit_checks`/`_check_balance`/`_check_cross_ref`/`_check_movement`/`_check_formula`/`_check_completeness`/`_check_aging`/`_check_confirmation`/`_check_sheet_filled`/`_check_reconciliation`，逐字搬运
    - _Requirements: 3.2_
  - [x] 6.2 主文件 import `_run_audit_checks`
    - `extract_with_fine_rule` 改为 `from app.services.wp_fine_rule_checks import _run_audit_checks`；保留 load/list/extract 主入口 + 提取 helper + 网格 helper
    - _Requirements: 3.2, 3.3_
  - [x] 6.3 验证 Sprint C 零回归
    - `wp_fine_rule_engine.py` ≤800；对外 load/list/extract 导入路径不变；相关测试全绿
    - _Requirements: 3.1, 3.3, 3.4, 4.4_

- [x] 7. Sprint C 检查点
  - 对外入口导入路径不变、相关测试通过，如有问题向用户确认。

- [x] 8. 终验：守卫转绿 + 全量零回归
  - [x] 8.1 `test_wp_large_file_size_guard.py` 全绿（3 文件 ≤800 且 pass2/pass3 文件未回升）
  - [x] 8.2 跑 `test_render_config_smoke.py` + 模板/转换/精细规则相关测试 + pass2/pass3 核心 + router registry
  - [x] 8.3 `python -c "from app.main import app; print(len(app.routes))"` = 1522
  - [x] 8.4 codegraph 核对无循环导入、无遗漏调用点
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 9. 最终检查点
  - 3 文件全部 ≤800、守卫绿、零回归、对外入口/方法签名全不变。如有问题向用户确认。

## Notes

- 三个 Sprint 互不阻塞，可独立提交；每 Sprint 末必验证零回归
- **铁律**：对外入口/方法签名逐字不变；mixin 保方法挂实例上；纯函数子模块用主文件 re-export 保导入路径
- **绝不动** pass2/pass3 已达标文件（render/classification/template_files/strategies/working_paper/wp_fill/auto_data_resolvers）
- 平级子模块（非转包）优先，避免同名模块转包的导入路径风险
- 每文件 ≤800 即停，不过度碎片化
- **本轮不含** `workpaper_models.py`（ORM 循环导入风险，后续单独评估）
