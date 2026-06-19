# 底稿渲染配置重构 — 任务清单

## Sprint 1：策略拆分（P0，核心）

> ⚠️ Sprint 1 为**原子 commit**——1.1~1.10 在同一次提交内完成，不可中间提交（否则主函数和策略文件重复）。

- [x] 1.1 新建 `backend/app/routers/wp_render_strategies/` 目录 + `__init__.py` + `_context.py`（RenderContext dataclass，含 lazy `prep_info` 字段）
- [x] 1.2 拆 `_b_index.py`：从 get_render_config 提取 B-Index 生成逻辑（~50行）
- [x] 1.3 拆 `_a_program.py`：提取 A-程序表中控台生成逻辑（~40行）
- [x] 1.4 拆 `_audit_sheet.py`：提取审定表 TB 取数逻辑（~60行）+ `_fetch_audit_sheet_tb_values` 搬迁
- [x] 1.5 拆 `_checklist.py`：提取核对表模板+响应加载逻辑（~40行）
- [x] 1.6 拆 `_analytical_review.py`：提取分析性复核取数（~25行）
- [x] 1.7 拆 `_c_note.py`：提取 C-附注披露网格兜底 + fixed_cells 占位替换（~40行）
- [x] 1.8 拆 `_univer_grid.py`：提取 Univer 网格提取逻辑（~15行）
- [x] 1.9 重写 `get_render_config` 主函数为 dispatch 模式（≤120行），引用 RENDERER_DISPATCH
- [x] 1.10 跑 1096 render-config 冒烟测试全绿 + 2457 循环验证测试全绿

## Sprint 2：联动测试 + Legacy 清理（P1）

- [x] 2.1 新建 `test_cycle_linkage_handlers_integration.py`：`_on_d_audit_determination_saved` 集成测试
- [x] 2.2 补 `_on_c_control_test_saved` 集成测试
- [x] 2.3 补 `_on_f_workpaper_conclusion_saved` 集成测试
- [x] 2.4 将 `control_deficiency_count` 从 `_resolve_legacy_source` 迁入 `_REGISTRY`
- [x] 2.5 删除 `_resolve_legacy_source` 方法 + fallback 调用（procedure_table_auto_service.py:197~231）
- [x] 2.6 验证 25 auto_data_resolvers 测试 + 新 resolver 测试全绿

## Sprint 3：去重 + 分组（P2~P3）

- [x] 3.1 新建 `backend/app/services/wp_component_type_mapping.py`，提取 `class_code_to_component` 纯函数
- [x] 3.2 改造 `wp_classification_service.derive_component_type` 调 `class_code_to_component`
- [x] 3.3 改造 `generate_wp_render_schema.derive_component_type` 调 `class_code_to_component`
- [x] 3.4 `_WP_CODE_OVERRIDE` 按循环分区域注释（A/B/C/D/E/F/G/H/I/J/K/L/M/N/S + 通用）
- [x] 3.5 跑全量冒烟测试确认零回归

## 验收门槛

- [ ] V1 wp_render_config.py ≤800 行（当前 1474）
- [ ] V2 get_render_config 函数体 ≤120 行（当前 475）
- [ ] V3 1096 + 2457 + 25 = 3578 测试全绿
- [ ] V4 `_resolve_legacy_source` 不存在
- [ ] V5 `class_code_to_component` 单一真源

## 已知限制

- `_fetch_audit_sheet_tb_values`（90行）搬入 `_audit_sheet.py` 后仍较大，后续可再拆 service
- 前端无改动（response 结构不变）
- conventions.md 重复章节清理列为 P3 但不阻塞本 spec 关闭
