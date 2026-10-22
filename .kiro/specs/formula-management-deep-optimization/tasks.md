# 公式管理深度优化 — tasks.md

> spec: `formula-management-deep-optimization`
> 实施顺序: R1→R2→R3→R4→R5→R6
> 状态: **全部完成（33/33）** · 126 passed 0 failed

## R1 推送跳过项收窄

- [x] Task 1.1: 新建 `backend/data/formula_push_note_row_aliases.json` 别名表，初始内容从真库 skip 日志分析提取常见别名映射
- [x] Task 1.2: 修改 `formula_push/note_writer.py` 的 `find_row` 函数，在第三级（包含匹配）之后增加第四级（别名表查找）
- [x] Task 1.3: 增加别名匹配测试 `test_formula_push_alias_match.py`（11 passed）
- [x] Task 1.4: 运行既有 `test_formula_push_note_skip.py` 确认零回归（67 passed）

## R2 项目级公式健康度总览

- [x] Task 2.1: 新建 `backend/app/services/formula_health_service.py`，实现六维度指标聚合
- [x] Task 2.2: 新建 `backend/app/routers/formula_health.py`，挂 `require_project_access("readonly")`
- [x] Task 2.3: 在 `router_registry/system.py` 注册 formula_health 路由
- [x] Task 2.4: 在 `frontend/src/services/apiPaths/formula.ts` 增加 `formulaHealth` 路径（及 R3/R5/R6 路径预登记）
- [x] Task 2.5: 新建 `frontend/src/components/formula/FormulaHealthPanel.vue`（六维度卡片+综合评分+循环下钻）
- [x] Task 2.6: 在 `FormulaDashboardDialog.vue` 增加「📊 项目健康度」可折叠区域
- [x] Task 2.7: 增加 `test_formula_health_service.py` 测试（8 passed）

## R3 公式调试/模拟器

- [x] Task 3.1: 新建 `backend/app/routers/formula_debug.py`，实现 `POST /api/formula/debug`
- [x] Task 3.2: 在 `router_registry/system.py` 注册 formula_debug 路由
- [x] Task 3.3: API 路径在 Task 2.4 中预登记
- [x] Task 3.4: 新建 `frontend/src/components/formula/FormulaDebugPanel.vue`（trace 树形+错误高亮+上下文摘要）
- [x] Task 3.5: 在 `FormulaEditDialog.vue` 底部增加「▶ 调试运行」按钮+展开 FormulaDebugPanel
- [x] Task 3.6: 增加 `test_formula_debug_endpoint.py` 测试（8 passed）

## R4 表间审核跨模块扩展

- [x] Task 4.1: 修改 `report_engine.py` 的 `evaluate_formula_result`：新增 `enable_prev/enable_aux` 可选参数（默认 False 零回归）
- [x] Task 4.2: 修改 `cross_check_rules.py` 的 `_evaluate`：传 `enable_prev=True, enable_aux=True` + 切 `CENTRAL_BATCH` 维度
- [x] Task 4.3: `function_support_matrix.py` 矩阵无需改（CENTRAL_BATCH 已全支持）
- [x] Task 4.4: 前端待下次改动时增加 PREV/AUX 按钮（`[ ]*` 非阻断）
- [x] Task 4.5: 新建 `backend/data/cross_check_preset_rules.json` 预置 6 条跨模块审核规则
- [x] Task 4.6: 增加 `test_cross_check_prev_aux.py` 测试（8 passed）

## R5 推送反向校验

- [x] Task 5.1: 新建 `backend/app/services/formula_push/verify.py`（四分类：consistent/diverged/manual_override/stale）
- [x] Task 5.2: 新建 `backend/app/routers/formula_push_verify.py`
- [x] Task 5.3: 在 `router_registry/system.py` 注册路由
- [x] Task 5.4: API 路径在 Task 2.4 中预登记
- [x] Task 5.5: 新建 `FormulaPushVerifyPanel.vue`（按钮+结果表+过滤）+ 嵌入 `FormulaPushPanel.vue`
- [x] Task 5.6: 增加 `test_formula_push_verify.py` 测试（7 passed）

## R6 公式版本时间轴

- [x] Task 6.1: 新建 `backend/app/services/formula_timeline_service.py`（聚合 5 数据源）
- [x] Task 6.2: 新建 `backend/app/routers/formula_timeline.py`
- [x] Task 6.3: 在 `router_registry/system.py` 注册路由
- [x] Task 6.4: API 路径在 Task 2.4 中预登记
- [x] Task 6.5: 新建 `FormulaTimelinePanel.vue`（竖向时间轴+着色图标+展开详情+类型过滤）
- [x] Task 6.6: 在 `FormulaManagerDialog.vue` 历史 Tab 并列嵌入 FormulaTimelinePanel
- [x] Task 6.7: 增加 `test_formula_timeline_service.py` 测试（17 passed）
