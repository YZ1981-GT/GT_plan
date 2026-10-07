# 任务：用户自定义公式 — 跨表格 / 跨科目 / 跨模块

> 顺序即依赖。

## 阶段 1：求值内核扩展

- [x] 1. FormulaContext 扩展 `wp_data` / `note_data`
  - ✅ 已有：`formula_engine.FormulaContext` 的 `wp_data` (L104) 和 `note_data` (L103) 字段已存在，默认空 dict
  - _需求：U1, U2_

- [x] 2. `WP()` 函数实现
  - ✅ 已有：`_handle_wp` (L952) 已注册到 `_REGISTRY`，从 `ctx.wp_data` 按 `(wp_code, column)` 取值，支持列名和单元格地址（如 B5）
  - 注：实际签名为 2 参 `WP('wp_code','column')`（非 spec 写的 3 参），以代码为准
  - _需求：U1_

- [x] 3. `NOTE()` 函数实现
  - ✅ 已有：`_handle_note` (L940) 已注册到 `_REGISTRY`，从 `ctx.note_data` 按 `(section, field_name, column)` 取值
  - 注：实际签名为 3 参（非 spec 写的 4 参），以代码为准
  - _需求：U2_

- [x] 4. `validate_formula` 扩展
  - ✅ 已有：`WP`/`NOTE` 已在 `_REGISTRY.known_function_names()` 中（白名单自动包含）；`_extract_formula_codes` (L1480-1483) 已覆盖 WP/NOTE 编码提取
  - _需求：U1, U2_

## 阶段 2：公式管理面板后端

- [x] 5. 公式求值端点预载 `wp_data` / `note_data`
  - ✅ `FormulaEngine.execute` 现在解析公式中的 `WP()` / `NOTE()` 引用，通过 `WPExecutor` / `NOTEExecutor` 异步查库预载数据，塞入 `FormulaContext.wp_data` / `note_data`
  - 新增辅助函数 `_extract_wp_refs` / `_extract_note_refs` 提取参数对
  - 预载失败时降级为 `Decimal("0")`（与 L1 handler 的缺值口径一致），不阻断求值
  - _需求：U1, U2_

- [x] 6. 用户公式 vs 系统推送优先级
  - ✅ 前端：`FormulaManagerDialog.vue` 导入 `isOwnedKey`，主表格编辑按钮对独占行置灰 + tooltip「此单元格由系统公式推送维护，不可编辑」
  - 🔴 复盘修正：后端拦截已移除——公式推送写 `checklist_responses`（键=item_id），用户公式写 `wp_formula`（键=sheet+cell_ref），两者不同存储不同命名空间，后端 cell_key→target_cell 匹配 owned_item_ids 永远不命中属形同虚设。守护完全由前端 isOwnedKey 承担
  - _需求：U3_

- [x] 7. 「应用自动运算」支持跨引用公式
  - ✅ `report_engine.evaluate_formula` 的 WP/NOTE 预替换从硬替换 `"0"` 改为通过 `WPExecutor`/`NOTEExecutor` 异步预载数据到 `FormulaContext.wp_data`/`note_data`
  - PREV/AUX 保持报表域置 0（上年数据和辅助核算在报表域确实不可用）
  - 跨底稿引用的计算结果展示在本弹窗中（不写别的底稿，符合 spec 需求 U4）
  - _需求：U4_

## 阶段 3：前端 UI

- [x] 8. 公式编辑器跨引用自动补全
  - ✅ `FormulaEditDialog.vue` 已有按钮式源浏览器：点击 WP → 从 ACNR catalog 弹出底稿选择器；点击 NOTE → 附注章节选择器。选中后自动插入完整公式
  - ✅ `FormulaManagerDialog.vue` 主表格行内编辑模式新增 TB/WP/NOTE/ROW 快捷函数按钮，点击即插入模板骨架
  - _需求：U6_

- [x] 9. 表间审核 tab 扩展 `WP()` / `NOTE()`
  - ✅ 预置规则已含 WP/NOTE 引用（`cross_report_note` 3 条 / `cross_report_wp` 2 条 / `cross_note_wp` 1 条）
  - ✅ 规则编辑弹窗语法提示已覆盖 `NOTE('章节','字段')` / `WP('底稿','sheet','坐标')` / `TB('科目','字段')`
  - ✅ 新增「▶ 执行校验」按钮：批量执行左右两侧公式 → 对比差额 → 表格显示 ✅/❌ + 计算值 + 差额列
  - 校验精度 0.01（审计惯例允许尾差）
  - _需求：U7_

## 阶段 4：跨科目依赖（Phase 2，可选）

- [x] 10. 跨科目依赖图
  - ✅ 新增 EventBus handler `_on_workpaper_saved_wp_formula_stale`（注册在 `event_handlers_cycle_linkage.py`）
  - 链路：`WORKPAPER_SAVED` → `wp_formula_linkage_service.propagate_custom_wp_cell_change` → 动态扫描 `wp_formula` 表中 WP() 引用 → 标引用方 `prefill_stale=true` + 静态图 BFS
  - 复用现有基础设施：`StalePropagationEngine.on_change`（BFS + 写 DB + SSE）+ `wp_formula_linkage_service`（WP 正则解析 + 依赖扫描）
  - 例：D2 审定合计变化 → K1 的用户公式 `WP('D2','审定数')` → K1 标 stale → 用户打开 K1 时重算
  - _需求：U5_

## 阶段 5：收尾

- [x] 11. 全套回归 + 公式函数文档更新
  - ✅ 新增测试 21 passed / 0 failed（test_formula_cross_module_refs.py）
  - ✅ 既有公式引擎测试 148 passed（3 个预存失败与本 spec 无关：ADJ 注册基线漂移，stash 归因已确认）
  - ✅ validate/user-formula 测试 57 passed（1 个预存失败与本 spec 无关：唯一索引变更来自同分支别的 spec）
  - _需求：U1~U7_
