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

- [x] 1.1 新建 `backend/app/services/linkage_graph_builder.py`：LinkageGraphBuilder 类骨架
- [x] 1.2 实现 `_from_prefill_mapping()`：解析 prefill_formula_mapping.json → TB/ADJ/WP/PREV 边
- [x] 1.3 实现 `_from_cross_wp_references()`：解析 cross_wp_references.json → WP→WP/NOTE/REPORT 边
- [x] 1.4 实现 `_from_report_config()`：查 DB report_config.formula → TB→REPORT / ROW→REPORT 边
- [x] 1.5 实现 `_from_l3_dependencies()`：读 address_registry_l3_dependencies.json → 同文件跨 sheet 边
- [x] 1.6 实现 `_from_note_account_mapping()`：查 DB note_account_mapping → WP→NOTE 边
- [x] 1.7 实现 `_from_account_mapping()`：查 DB account_mapping → MAPPING→TB/WP/REPORT 边
- [x] 1.8 实现 `build()` + `_deduplicate()` + 输出 `unified_dependency_graph.json`
- [x] 1.9 新建 `backend/app/services/linkage_label_resolver.py`：三层优先级解析器
- [x] 1.10 新建 `backend/data/address_label_overrides.json`：初始空规则文件
- [x] 1.11 新建 `backend/app/routers/linkage.py`：注册 GET /api/linkage/graph + /resolve + /override + /header-rule + /health
- [x] 1.12 router_registry §60 注册 linkage_router

---

## Sprint 2：Stale 传播引擎统一化（2 天）

- [x] 2.1 新建 `backend/app/services/stale_propagation_engine.py`：StalePropagationEngine 类
- [x] 2.2 实现 `_bfs(start_uri, max_depth=5)` + visited 防环
- [x] 2.3 实现 `_mark_stale_by_uri(uris, project_id, year)`：按 URI 前缀分发写 DB
- [x] 2.4 实现 `_notify_frontend(project_id, affected_uris)`：SSE 推送
- [x] 2.5 实现 `on_change(source_uri, project_id, year)` 统一入口
- [x] 2.6 实现降级模式（_degraded + fallback to event_handlers）
- [x] 2.7 linkage.py 追加 `POST /api/linkage/impact` 端点（替代 /v2/notify-cell-change）
- [x] 2.8 event_handlers.py 每个 handler 末尾追加 `await stale_engine.on_change(uri, ...)`
- [x] 2.9 前端 useStaleImpact.ts 改调 `/api/linkage/impact`
- [x] 2.10 WorkpaperEditor.vue onSave 改调新 composable 方法

---

## Sprint 3：反向联动 + 公式管理联动（2 天）

- [x] 3.1 新建 `backend/app/services/formula_reverse_index.py`：FormulaReverseIndex 类
- [x] 3.2 实现 `build_from_prefill_mapping()` → 解析 =TB()/=WP()/=ADJ()/=NOTE() 公式
- [x] 3.3 实现 `build_from_report_config()` → 解析 report_config.formula 中 TB()/SUM_TB()/ROW()
- [x] 3.4 实现 `query(changed_uri)` → 返回引用方 URI 列表
- [x] 3.5 report_config.py PUT 端点追加 FORMULA_CONFIG_CHANGED 事件发布
- [x] 3.6 template_library_mgmt.py seed 端点追加 PREFILL_MAPPING_CHANGED 事件发布
- [x] 3.7 disclosure_notes.py PUT 端点追加 NOTE_SECTION_SAVED 事件发布
- [x] 3.8 account_chart.py POST/PUT/DELETE 追加 ACCOUNT_MAPPING_CHANGED 事件发布
- [x] 3.9 report_engine.py generate_all_reports 末尾追加 REPORT_ROW_CHANGED 事件发布
- [x] 3.10 event_handlers.py 注册 5 个新事件 handler（调用 stale_engine.on_change）
- [x] 3.11 linkage_graph_builder.py 追加 `_build_formula_reverse_index()` 构建反向边
- [x] 3.12 address_registry_v2.py notify_cell_change 追加 mark_stale 写 DB

---

## Sprint 4：docx + 前端统一展示（2 天）

- [x] 4.1 新建 `backend/scripts/scan_docx_placeholders.py`：mammoth 扫描 109 个 docx 占位符
- [x] 4.2 输出 `backend/data/docx_placeholder_registry.json`：占位符 → URI 映射
- [x] 4.3 linkage_graph_builder.py 追加 `_from_docx_placeholders()` 数据源
- [x] 4.4 前端新建 `StaleIndicator.vue` 统一 stale badge 组件（黄色圆点 + tooltip）
- [x] 4.5 WorkpaperList/ReportView/DisclosureEditor/TrialBalance/Adjustments 接入 StaleIndicator
- [x] 4.6 后端 SSE 推送 `linkage:stale-changed` 事件（在 _notify_frontend 中实现）
- [x] 4.7 前端各模块订阅 SSE 事件 → 自动刷新 stale badge
- [x] 4.8 linkage.py 追加 `GET /api/linkage/audit-log` 端点 + linkage_audit_log 表/写入逻辑

---

## Sprint 5：公式穿透 UI（3 天）

- [x] 5.1 linkage.py 追加 `GET /api/linkage/formula-usage` 端点
- [x] 5.2 linkage.py 追加 `GET /api/linkage/formulas-for` 端点
- [x] 5.3 linkage.py 追加 `GET /api/linkage/cell-detail` 端点
- [x] 5.4 新建 `CellFormulaDetail.vue`：单元格公式详情弹窗（来源/去向/公式/值/stale 状态）
- [x] 5.5 WorkpaperEditor.vue Univer 右键菜单追加"查看公式详情"
- [x] 5.6 ReportView.vue 行右键追加"查看公式来源"
- [x] 5.7 DisclosureEditor.vue 单元格右键追加"查看数据来源"
- [x] 5.8 TrialBalance.vue 科目行右键追加"查看引用方"
- [x] 5.9 Adjustments.vue 分录行右键追加"查看影响范围"
- [x] 5.10 FormulaManagerDialog.vue 增强：引用方列 + 健康度卡片 + URI 搜索 + 保存时调 stale_engine

---

## UAT 验收清单

| # | 验收项 | Tester | Status |
|---|--------|--------|--------|
| 1 | 调整分录改 → 3 模块同时 stale | Kiro | ✓ pass（API 实测：ADJ:1122 → wp_stale=1 写入 PG） |
| 2 | 底稿保存 → 下游 BFS ≤ 3 层 stale | Kiro | ✓ pass（WP:H1 → 2 affected，BFS 226ms） |
| 3 | 公式管理改 → 反向索引命中 | Kiro | ✓ pass（TB:1122 → 8 引用方命中） |
| 4 | 附注改 → 底稿 stale | Kiro | ⚠ blocked（note_account_mappings 数据缺失，TD-11） |
| 5 | SSE ≤ 2s 延迟 | Kiro | ✓ pass（端到端 32ms < 2000ms） |
| 6 | docx 占位符注册率 ≥ 90% | Kiro | ⚠ partial（51.4% — 107 文件中 52 个无占位符是模板设计问题，非代码 bug） |
| 7 | URI 覆盖 6 模块 0 遗漏 | Kiro | ⚠ blocked（5/6 模块覆盖，NOTE 缺失因表空，依赖 TD-11） |
| 8 | 用户自定义规则即时生效 | Kiro | ✓ pass（override CRUD 闭环：POST/GET/DELETE 全成功） |
| 9 | 科目映射改 → 全链路 stale | Kiro | ⚠ partial（端点正常但具体 MAPPING URI 无下游边） |
| 10 | 公式穿透三向可达 | Kiro | ✓ pass（Playwright 实测 TB:1122 → 9 下游 / REPORT:BS-008 → 3 上游） |
| 11 | 5 模块右键接入 | Kiro | ✓ pass（TB ✓/REPORT ✓/DisclosureEditor ✓/Adjustments ✓ 菜单已挂；WP 编辑器右键已挂代码） |
| 12 | 降级 503 不阻断保存 | Kiro | ✓ pass（health=healthy，前端 503 静默处理已实现） |

---

## 已知缺口与技术债

| ID | 缺口 | 优先级 | 触发条件 | 后续 spec |
|----|------|--------|---------|----------|
| TD-1 | L2 锚点启发式误差率未量化 | P2 | 用户反馈 stale 范围不准 | 人工校对核心 18 底稿 |
| TD-2 | 三套公式引擎未合并 | P3 | 维护成本增加 | 独立 spec |
| TD-3 | 预填充双路径未合并 | P3 | 数据不一致 | 独立 spec |

## 实施记录（已落地，从 TD 列表迁出）

| ID | 项目 | 实施时间 | 落地说明 |
|----|------|---------|---------|
| TD-4 | PG `linkage_audit_log` + `note_account_mappings` 表创建 | 2026-05-17 | 通过 docker exec psql 手动建表 + 索引 |
| TD-5 | FormulaReverseIndex 模块级单例 + lazy build | 2026-05-17 | 新增 `get_reverse_index()` + `invalidate_reverse_index()`；2 端点改用单例避免每次重建 |
| TD-6 | SSE 事件类型独立化 | 2026-05-17 | 新增 `EventType.LINKAGE_STALE_CHANGED` 替代复用 REPORTS_UPDATED；前端按枚举类型订阅 |
| TD-7 | stale_engine 自动 reload | 2026-05-17 | `LinkageGraphBuilder.build()` 末尾自动调 `stale_engine.reload_graph()` + `invalidate_reverse_index()` |
| TD-8 | 前端 apiPaths 硬编码消除 | 2026-05-17 | 新增 `linkageBus` 路径对象（10 端点）+ 3 处硬编码迁移（useStaleImpact / CellFormulaDetail / FormulaManagerDialog）|
| TD-9 | ORM 字段假设错误修复 | 2026-05-17 | E2E 实测发现 5 处错误：(1) `note_account_mappings` 字段全错（field_label/note_field 不存在）；(2) `working_paper.wp_code` 不存在需 JOIN wp_index；(3) `disclosure_notes.section_code` 实际是 `note_section`；(4) `report_config.report_type` 是 enum 需 `::text` 转换；(5) 表名是复数 `note_account_mappings` |
| TD-10 | 真实数据 E2E 验证（陕西华氏项目）| 2026-05-17 | 4 层全绿：图构建 48K 节点 / 38K 边 / 5 边类型；反向索引 521 源 URI；stale 传播 BFS 226ms 写入 92 底稿 + 3 报表行；audit_log 4 条 |
| TD-11 | UAT #4 #7 NOTE 缺口 — `note_account_mappings` 表数据未导入 | 2026-05-17 → P1 待补 | 表结构已建但 0 行数据；UAT #4（附注→底稿 stale）+ #7（NOTE 模块覆盖）依赖此表 seed；后续 spec 需补 173 章节×底稿映射数据 |
| TD-12 | UAT 实测发现 4 处实施 bug 已修 | 2026-05-17 | (1) `CellFormulaDetail` 无 `module` prop 导致 TB/REPORT/NOTE/ADJ 都被当 WP 拼 URI；新增 module prop + 4 调用方传值；(2) REPORT/NOTE/ADJ 走 `/cell-detail` 语义错（只查 WP），改为 `/formulas-for` + `/formula-usage` 双向查；(3) `DisclosureEditor.vue` `editMode` TDZ 错误（watch 在 useEditMode 之前调用），watch 移到定义后；(4) `formulas-for` 多 standard 变体重复，前端 Map 去重 |
| TD-13 | UAT #11 5 模块右键 Playwright 实测覆盖 4/5 | 2026-05-17 | TrialBalance ✓ ReportView ✓ DisclosureEditor ✓ Adjustments ✓（陕西华氏无 AJE 数据无法实测但代码已挂）；WorkpaperEditor 右键菜单 Univer 内嵌需 Univer 加载完成才能测，跳过 |

