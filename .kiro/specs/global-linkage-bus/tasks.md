# 全局联动总线（Unified Linkage Bus）— 任务清单

## 任务总览

| Sprint | 主题 | 任务数 | 工时 |
|--------|------|--------|------|
| 1 | 统一依赖图 + 运行时解析器 | 12 | 3 天 |
| 2 | Stale 传播引擎统一化 | 10 | 2 天 |
| 3 | 反向联动 + 公式管理联动 | 12 | 2 天 |
| 4 | docx + 前端统一展示 | 8 | 2 天 |
| 5 | 公式穿透 UI | 10 | 3 天 |
| **合计** | | **52** | **12 天** |

---

## Sprint 1：统一依赖图 + 运行时解析器（3 天）

- [ ] 1.1 新建 `backend/app/services/linkage_graph_builder.py`：LinkageGraphBuilder 类骨架
- [ ] 1.2 实现 `_from_prefill_mapping()`：解析 prefill_formula_mapping.json → TB/ADJ/WP/PREV 边
- [ ] 1.3 实现 `_from_cross_wp_references()`：解析 cross_wp_references.json → WP→WP/NOTE/REPORT 边
- [ ] 1.4 实现 `_from_report_config()`：查 DB report_config.formula → TB→REPORT / ROW→REPORT 边
- [ ] 1.5 实现 `_from_l3_dependencies()`：读 address_registry_l3_dependencies.json → 同文件跨 sheet 边
- [ ] 1.6 实现 `_from_note_account_mapping()`：查 DB note_account_mapping → WP→NOTE 边
- [ ] 1.7 实现 `_from_account_mapping()`：查 DB account_mapping → MAPPING→TB/WP/REPORT 边
- [ ] 1.8 实现 `build()` + `_deduplicate()` + 输出 `unified_dependency_graph.json`
- [ ] 1.9 新建 `backend/app/services/linkage_label_resolver.py`：三层优先级解析器
- [ ] 1.10 新建 `backend/data/address_label_overrides.json`：初始空规则文件
- [ ] 1.11 新建 `backend/app/routers/linkage.py`：注册 GET /api/linkage/graph + /resolve + /override + /header-rule + /health
- [ ] 1.12 router_registry §60 注册 linkage_router

---

## Sprint 2：Stale 传播引擎统一化（2 天）

- [ ] 2.1 新建 `backend/app/services/stale_propagation_engine.py`：StalePropagationEngine 类
- [ ] 2.2 实现 `_bfs(start_uri, max_depth=5)` + visited 防环
- [ ] 2.3 实现 `_mark_stale_by_uri(uris, project_id, year)`：按 URI 前缀分发写 DB
- [ ] 2.4 实现 `_notify_frontend(project_id, affected_uris)`：SSE 推送
- [ ] 2.5 实现 `on_change(source_uri, project_id, year)` 统一入口
- [ ] 2.6 实现降级模式（_degraded + fallback to event_handlers）
- [ ] 2.7 linkage.py 追加 `POST /api/linkage/impact` 端点（替代 /v2/notify-cell-change）
- [ ] 2.8 event_handlers.py 每个 handler 末尾追加 `await stale_engine.on_change(uri, ...)`
- [ ] 2.9 前端 useStaleImpact.ts 改调 `/api/linkage/impact`
- [ ] 2.10 WorkpaperEditor.vue onSave 改调新 composable 方法

---

## Sprint 3：反向联动 + 公式管理联动（2 天）

- [ ] 3.1 新建 `backend/app/services/formula_reverse_index.py`：FormulaReverseIndex 类
- [ ] 3.2 实现 `build_from_prefill_mapping()` → 解析 =TB()/=WP()/=ADJ()/=NOTE() 公式
- [ ] 3.3 实现 `build_from_report_config()` → 解析 report_config.formula 中 TB()/SUM_TB()/ROW()
- [ ] 3.4 实现 `query(changed_uri)` → 返回引用方 URI 列表
- [ ] 3.5 report_config.py PUT 端点追加 FORMULA_CONFIG_CHANGED 事件发布
- [ ] 3.6 template_library_mgmt.py seed 端点追加 PREFILL_MAPPING_CHANGED 事件发布
- [ ] 3.7 disclosure_notes.py PUT 端点追加 NOTE_SECTION_SAVED 事件发布
- [ ] 3.8 account_chart.py POST/PUT/DELETE 追加 ACCOUNT_MAPPING_CHANGED 事件发布
- [ ] 3.9 report_engine.py generate_all_reports 末尾追加 REPORT_ROW_CHANGED 事件发布
- [ ] 3.10 event_handlers.py 注册 5 个新事件 handler（调用 stale_engine.on_change）
- [ ] 3.11 linkage_graph_builder.py 追加 `_build_formula_reverse_index()` 构建反向边
- [ ] 3.12 address_registry_v2.py notify_cell_change 追加 mark_stale 写 DB

---

## Sprint 4：docx + 前端统一展示（2 天）

- [ ] 4.1 新建 `backend/scripts/scan_docx_placeholders.py`：mammoth 扫描 109 个 docx 占位符
- [ ] 4.2 输出 `backend/data/docx_placeholder_registry.json`：占位符 → URI 映射
- [ ] 4.3 linkage_graph_builder.py 追加 `_from_docx_placeholders()` 数据源
- [ ] 4.4 前端新建 `StaleIndicator.vue` 统一 stale badge 组件（黄色圆点 + tooltip）
- [ ] 4.5 WorkpaperList/ReportView/DisclosureEditor/TrialBalance/Adjustments 接入 StaleIndicator
- [ ] 4.6 后端 SSE 推送 `linkage:stale-changed` 事件（在 _notify_frontend 中实现）
- [ ] 4.7 前端各模块订阅 SSE 事件 → 自动刷新 stale badge
- [ ] 4.8 linkage.py 追加 `GET /api/linkage/audit-log` 端点 + linkage_audit_log 表/写入逻辑

---

## Sprint 5：公式穿透 UI（3 天）

- [ ] 5.1 linkage.py 追加 `GET /api/linkage/formula-usage` 端点
- [ ] 5.2 linkage.py 追加 `GET /api/linkage/formulas-for` 端点
- [ ] 5.3 linkage.py 追加 `GET /api/linkage/cell-detail` 端点
- [ ] 5.4 新建 `CellFormulaDetail.vue`：单元格公式详情弹窗（来源/去向/公式/值/stale 状态）
- [ ] 5.5 WorkpaperEditor.vue Univer 右键菜单追加"查看公式详情"
- [ ] 5.6 ReportView.vue 行右键追加"查看公式来源"
- [ ] 5.7 DisclosureEditor.vue 单元格右键追加"查看数据来源"
- [ ] 5.8 TrialBalance.vue 科目行右键追加"查看引用方"
- [ ] 5.9 Adjustments.vue 分录行右键追加"查看影响范围"
- [ ] 5.10 FormulaManagerDialog.vue 增强：引用方列 + 健康度卡片 + URI 搜索 + 保存时调 stale_engine

---

## UAT 验收清单

| # | 验收项 | Tester | Status |
|---|--------|--------|--------|
| 1 | 调整分录改 → 3 模块同时 stale | ○ pending |
| 2 | 底稿保存 → 下游 BFS ≤ 3 层 stale | ○ pending |
| 3 | 公式管理改 → 反向索引命中 | ○ pending |
| 4 | 附注改 → 底稿 stale | ○ pending |
| 5 | SSE ≤ 2s 延迟 | ○ pending |
| 6 | docx 占位符注册率 ≥ 90% | ○ pending |
| 7 | URI 覆盖 6 模块 0 遗漏 | ○ pending |
| 8 | 用户自定义规则即时生效 | ○ pending |
| 9 | 科目映射改 → 全链路 stale | ○ pending |
| 10 | 公式穿透三向可达 | ○ pending |
| 11 | 5 模块右键接入 | ○ pending |
| 12 | 降级 503 不阻断保存 | ○ pending |

---

## 已知缺口与技术债

| ID | 缺口 | 优先级 | 触发条件 | 后续 spec |
|----|------|--------|---------|----------|
| TD-1 | L2 锚点启发式误差率未量化 | P2 | 用户反馈 stale 范围不准 | 人工校对核心 18 底稿 |
| TD-2 | 三套公式引擎未合并 | P3 | 维护成本增加 | 独立 spec |
| TD-3 | 预填充双路径未合并 | P3 | 数据不一致 | 独立 spec |
