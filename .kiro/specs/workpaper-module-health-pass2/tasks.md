# 实施计划：底稿模块健康度二期

## 概述

按 4 个 Sprint 渐进式交付 9 项代码健康度治理。每个 Sprint 内的任务原子提交，Sprint 间互不阻塞。语言：Python（FastAPI + SQLAlchemy + pytest + hypothesis）。

## Tasks

- [x] 1. Sprint 1：循环依赖消除 + Helper 迁出（Req 1 + Req 2，原子提交）
  - [x] 1.1 创建 `backend/app/services/wp_preparation_info_service.py`
    - 将 `wp_render_config.py` L298-390 的 `_build_preparation_info` 函数迁入
    - 改为模块级异步函数 `build_preparation_info(db, project_id, wp_id) -> dict[str, str]`
    - 保留原有 SQL 逻辑和逐字段 try/except 降级
    - 添加 docstring（用途 + 返回 7 字段说明）
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 更新策略文件 import 路径
    - `_b_index.py` L37-39: `from app.routers.wp_render_config import _build_preparation_info` → `from app.services.wp_preparation_info_service import build_preparation_info`
    - `_c_note.py` L70-72: 同上
    - `wp_render_config.py` 中 `get_preparation_info` 端点（~L960）改为调用 service
    - _Requirements: 1.3, 1.4_

  - [x] 1.3 删除 `wp_render_config.py` 中已被策略替代的冗余 Helper
    - 删除 `_generate_b_index_data` (L392-465) — 已被 `_b_index.py` render() 替代
    - 删除 `_generate_a_program_data` (L467-575) — 已被 `_a_program.py` render() 替代；同步更新 `_a_program.py` L33-38 的 import（改为本地实现或调用 `wp_program_extract` service）
    - 删除 `_generate_grid_data` (L577-619) + `_has_grid_cells` — 已被 `_univer_grid.py` render() 替代
    - 删除 `_generate_audit_sheet_data` (L713-) — 已被 `_audit_sheet.py` render() 替代
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 1.4 迁移 `_fetch_audit_sheet_tb_values` + `_decimal_to_float` 到 service 层
    - 创建 `backend/app/services/wp_audit_sheet_tb_service.py`
    - 将 `_fetch_audit_sheet_tb_values` (wp_render_config.py L621-711) 和 `_decimal_to_float` (L514-523) 迁入
    - 更新 `_audit_sheet.py` L35-37 的本地 `_fetch_audit_sheet_tb_values`：改为从 service import（或确认策略文件已有独立实现，则删除 router 中的旧版本即可）
    - _Requirements: 2.4_

  - [x] 1.5 更新受影响的测试文件 import 路径
    - `test_no_accounting_period_pbt.py` L13-16: 改从 service import `build_preparation_info`；删除对 `_generate_b_index_data` 的 import
    - `test_preparation_info.py` L16: 改从 service import
    - `test_preparation_info_pbt.py` L11: 改从 service import
    - `test_wp_program_extract.py` L136/149: 验证 `_generate_a_program_data` 是否还需（若策略已完全替代则删除对应测试或改指向策略）
    - `test_audit_sheet_tb_fetch.py` L27-31: 改从 service import `_fetch_audit_sheet_tb_values` 和 `_decimal_to_float`
    - _Requirements: 1.4, 2.6_

  - [x] 1.6 验证 wp_render_config.py 行数 ≤ 800 且零回归
    - 运行 `python -m pytest backend/tests/test_render_config_smoke.py`（1096 冒烟测试）
    - 运行全量循环验证测试（2457 条）
    - `wc -l backend/app/routers/wp_render_config.py` 确认 ≤ 800 行
    - _Requirements: 1.5, 2.5, 2.6_

- [x] 2. Sprint 1 检查点
  - 确保 1096 冒烟测试 + 2457 循环验证测试全部通过，如有问题向用户确认。

- [x] 3. Sprint 2：测试补全（Req 3 + Req 4）
  - [x] 3.1 创建策略单元测试文件 `backend/tests/test_workpaper_render_strategies.py`
    - 为 7 个策略各写至少 1 个单元测试：`_b_index`, `_a_program`, `_audit_sheet`, `_checklist`, `_analytical_review`, `_c_note`, `_univer_grid`
    - Mock `RenderContext`（AsyncMock db、MagicMock working_paper/classification）
    - 测试正常路径：返回 `dict` 或 `None`
    - 测试降级路径：`sheet_html_data=None, sheet_schema=None, template_file_path=None` 时不抛异常
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 3.2 为策略编写 Property-Based 测试
    - **Property 2: 策略函数返回类型约束** — `render(ctx)` 对任意有效 RenderContext 返回 dict | None
    - **Property 3: 策略函数优雅降级** — 缺失数据时不抛异常
    - 使用 hypothesis，`@settings(max_examples=100)`
    - **Validates: Requirements 3.3, 3.4**

  - [x] 3.3 创建 Override 契约测试 `backend/tests/test_wp_code_override_contract.py`
    - 断言 `_WP_CODE_OVERRIDE` 全部 value ∈ `VALID_COMPONENT_TYPES`
    - 失败时报告具体非法 wp_code 和 value
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ]* 3.4 为 Override 编写 Property-Based 测试
    - **Property 4: Override 映射值合法性**
    - 使用 `st.sampled_from(list(_WP_CODE_OVERRIDE.keys()))` 遍历验证
    - **Validates: Requirements 4.1**

  - [x] 3.5 运行全部新增测试确认通过
    - `python -m pytest backend/tests/test_workpaper_render_strategies.py backend/tests/test_wp_code_override_contract.py -v`
    - _Requirements: 3.5, 4.3_

- [x] 4. Sprint 2 检查点
  - 确保所有新增测试通过，已有 1096 冒烟测试不受影响，如有问题向用户确认。

- [x] 5. Sprint 3：DRY + JSON 外置（Req 5 + Req 6）
  - [x] 5.1 创建共享 helper `backend/app/services/wp_adjustment_helpers.py`
    - 提取 `auto_data_resolvers.py` L98-149 的 `_count_adjustments` + `_count_adjustments_with_pending`
    - 改为模块级异步函数 `count_adjustments(db, project_id, year, adj_type)` 和 `count_adjustments_with_pending(...)`
    - 添加 docstring
    - _Requirements: 5.1_

  - [x] 5.2 替换 `auto_data_resolvers.py` 中的重复实现
    - 删除 L98-149 的本地 `_count_adjustments` / `_count_adjustments_with_pending`
    - 替换为 `from app.services.wp_adjustment_helpers import count_adjustments, count_adjustments_with_pending`
    - 更新 4 处调用点（L154, L164, L174, L192）
    - _Requirements: 5.2_

  - [x] 5.3 替换 `procedure_table_auto_service.py` 中的重复实现
    - 删除 `ProcedureTableService._count_adjustments` (L214-235) 和 `_count_adjustments_with_pending` (L236-)
    - 在类中改为调用 `from app.services.wp_adjustment_helpers import count_adjustments, count_adjustments_with_pending`
    - _Requirements: 5.3_

  - [x] 5.4 验证 DRY 重构零回归
    - 运行 `python -m pytest backend/tests/test_auto_data_resolvers.py`（28 条）
    - 运行涉及 procedure_table_auto_service 的测试
    - _Requirements: 5.4, 5.5_

  - [x] 5.5 创建 `backend/app/data/wp_code_overrides.json`
    - 从 `wp_classification_service.py` 中 `_WP_CODE_OVERRIDE` 字典提取全部 ~910 条映射
    - 格式：扁平 `{"wp_code": "componentType"}` JSON 对象
    - 按循环分段注释（JSON 不支持注释，改为按 A-S 字母顺序排列）
    - _Requirements: 6.1_

  - [x] 5.6 创建 JSON 加载器 `backend/app/services/wp_code_override_loader.py`
    - 实现 `load_wp_code_overrides() -> dict[str, str]`：基于 mtime 缓存 + 热重载
    - 实现 `validate_overrides(overrides)`：校验所有 value ∈ VALID_COMPONENT_TYPES
    - 启动时加载 + 验证；文件损坏时保留旧缓存 + WARNING 日志
    - _Requirements: 6.2, 6.3, 6.4_

  - [x] 5.7 替换 `wp_classification_service.py` 中的内嵌 dict
    - 删除 ~910 行 `_WP_CODE_OVERRIDE = {...}` 字面量
    - 替换为 `from app.services.wp_code_override_loader import load_wp_code_overrides`
    - 保留模块级 `_WP_CODE_OVERRIDE = load_wp_code_overrides()` 兼容现有引用
    - _Requirements: 6.5_

  - [ ]* 5.8 编写 JSON 热重载 Property-Based 测试
    - **Property 5: Override JSON 热重载正确性** — 修改 JSON 后 mtime 变化触发重载
    - 使用 tmpfile + patch `_JSON_PATH` 模拟热重载
    - **Validates: Requirements 6.4**

  - [x] 5.9 运行冒烟测试确认 JSON 外置零回归
    - `python -m pytest backend/tests/test_render_config_smoke.py`（1096 条）
    - `python -m pytest backend/tests/test_wp_code_override_contract.py`（Sprint 2 已建）
    - _Requirements: 6.6_

- [x] 6. Sprint 3 检查点
  - 确保 1096 冒烟测试 + 28 auto_data_resolvers 测试 + 契约测试全部通过，如有问题向用户确认。

- [x] 7. Sprint 4：Docstring + Router 校验 + Template 拆分（Req 7 + Req 8 + Req 9）
  - [x] 7.1 为 `auto_data_resolvers.py` 全部 resolver 补充 docstring
    - 遍历所有 `@auto_resolver` 装饰的函数（约 35-40 个）
    - 为每个缺少 docstring 的 resolver 添加：用途描述 + 数据来源 + 返回结构概要
    - 格式参照设计文档 Resolver Docstring 模板
    - _Requirements: 7.1, 7.2, 7.4_

  - [ ]* 7.2 编写 Resolver docstring 覆盖 Property-Based 测试
    - **Property 6: 所有 Resolver 均有 docstring**
    - 使用 `st.sampled_from(get_registered_sources())` + `@settings(max_examples=100)`
    - 追加到 `backend/tests/test_auto_data_resolvers.py` 或新建 `test_resolver_docstring_pbt.py`
    - **Validates: Requirements 7.1, 7.4**

  - [x] 7.3 实现 Router Registry 启动完整性校验
    - 在 `backend/app/router_registry/__init__.py` 的 `register_all_routers()` 末尾追加 `_validate_registry_completeness(app)`
    - 扫描 `backend/app/routers/` 全部含 `router = APIRouter` 的模块
    - 与已注册 router 对比，WARNING 日志输出遗漏（不阻断启动）
    - 添加 `_EXCLUDED_ROUTERS` 排除列表
    - _Requirements: 8.1, 8.2, 8.3, 8.5_

  - [x] 7.4 创建 Router 注册完整性 CI 测试 `backend/tests/test_router_registry_completeness.py`
    - 断言所有含 `router = APIRouter` 的模块已注册（CI 阻断）
    - 排除 `_EXCLUDED_ROUTERS` 中的豁免模块
    - _Requirements: 8.4_

  - [ ]* 7.5 编写 Router 注册完整性 Property-Based 测试
    - **Property 7: Router 注册完整性**
    - 使用 `st.sampled_from(discovered_router_modules)` 逐模块验证
    - **Validates: Requirements 8.1, 8.2, 8.4, 8.5**

  - [x] 7.6 拆分 `wp_template_files.py` — 创建 `wp_template_xlsx.py`
    - 迁入端点：`convert_xlsx_to_json` (L187), `convert_xlsx_storage_to_json` (L353)
    - 迁入 helper：`_build_sheet_obj_from_ws` (L1045), `_extract_conditional_formatting` (L820), `_extract_data_validations` (L881), `_parse_range_string` (L950), `_col_letter_to_idx` (L986), `_extract_images` (L994)
    - 使用相同路由前缀，在 `router_registry/workpaper.py` 追加注册
    - _Requirements: 9.2_

  - [x] 7.7 拆分 `wp_template_files.py` — 创建 `wp_template_docx.py`
    - 迁入端点：`convert_docx_to_univer_doc` (L524)
    - 迁入 helper：`_has_style` (L595), `_safe_hex_rgb` (L639), `_extract_cell_style` (L665)
    - 使用相同路由前缀，在 `router_registry/workpaper.py` 追加注册
    - _Requirements: 9.3_

  - [x] 7.8 验证 `wp_template_files.py` 拆分后行数 ≤ 800
    - 确认保留端点：`get_workpaper_xlsx`, `init_from_template`, `get_available_templates`, `upload_xlsx_file`, `get_single_sheet_data`, `_get_tb_data_for_prefill`
    - `wc -l` 确认 ≤ 800 行
    - _Requirements: 9.1_

  - [ ]* 7.9 编写端点路径拆分不变性 Property-Based 测试
    - **Property 8: 端点路径拆分不变性** — 拆分前后 API 端点路径集合不变
    - 基于 FastAPI `app.routes` 枚举 (path, method) 对比
    - **Validates: Requirements 9.4**

  - [x] 7.10 运行全量测试确认零回归
    - `python -m pytest backend/tests/ -v --tb=short`（全量）
    - 重点关注：1096 冒烟 + 2457 循环验证 + 28 auto_data + 新增测试
    - _Requirements: 7.4, 8.4, 9.4, 9.5_

- [x] 8. Sprint 4 最终检查点
  - 确保所有测试通过，运行 `python -m pytest backend/tests/ --tb=short` 全绿，如有问题向用户确认。

## Notes

- 标记 `*` 的子任务为可选（Property-Based 测试），跳过不影响功能完整性
- Sprint 1 的所有任务（1.1-1.6）必须原子提交（循环依赖消除不能半途断开）
- 每个 Sprint 末尾的检查点确保增量验证
- Property-Based 测试使用项目已有的 `hypothesis` 库
- 所有新建 service 文件遵循 `from __future__ import annotations` + type hints 规范
