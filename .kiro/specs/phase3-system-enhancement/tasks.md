# Implementation Plan: Phase 3 系统性增强

## Overview

基于 requirements.md v1.0 和 design.md v1.0，Phase 3 五项功能跨度大，拆分为 5 个 Sprint（每项功能一个 Sprint，可并行推进 F3/F4/F5）。

预计工时：15 天（Sprint 1: 3 天 / Sprint 2: 3 天 / Sprint 3: 3 天 / Sprint 4: 3 天 / Sprint 5: 3 天）

前置依赖：Phase 1 + Phase 2 specs 完成

## Tasks

### Sprint 1 — F1 双向穿透

- [x] 1.1 创建附注来源追溯 API
  - 创建 `backend/app/routers/note_trace.py`
  - `GET /api/projects/{pid}/notes/trace-source?cell_id={cell_id}`
  - 查询附注 cell 的公式定义 → 解析来源报表行 → 查询报表行对应的 TB 科目
  - 返回 source_type + report_line + tb_accounts 结构
  - 注册到 router_registry.py
  - _Requirements: F1.1_

- [x] 1.2 创建报表行构成科目 API
  - 在 `backend/app/routers/reports.py` 新增端点
  - `GET /api/projects/{pid}/reports/line-composition?line_code={line_code}`
  - 查询 report_line_mapping 获取该行对应的科目编号列表
  - 查询 tb_balance 获取各科目余额
  - 计算各科目占比(pct)
  - 返回 accounts 列表（按金额降序）
  - _Requirements: F1.2_

- [x] 1.3 创建 TraceSourcePopover 前端组件
  - 创建 `audit-platform/frontend/src/components/common/TraceSourcePopover.vue`
  - el-popover 触发方式：click
  - 显示来源报表行 + 构成科目列表
  - 科目列表每行：编号 + 名称 + 金额 + 占比
  - 底部"跳转到试算表"按钮
  - _Requirements: F1.1, F1.2_

- [x] 1.4 集成到 DisclosureEditor
  - DisclosureEditor.vue 中 auto 模式 cell 增加 @click 事件
  - 点击后调用 trace-source API → 显示 TraceSourcePopover
  - 跳转到试算表时记录到 useNavigationStack
  - _Requirements: F1.3, F1.4_

- [x] 1.5 集成到 ReportView
  - ReportView.vue 中金额列增加 @click 事件
  - 点击后调用 line-composition API → 显示构成科目弹窗
  - 科目列表中点击某科目 → 跳转到 TrialBalance 并定位
  - _Requirements: F1.2, F1.3_

- [x] 1.6 面包屑方向标记
  - 修改 DrilldownBreadcrumb 支持方向标记
  - NavigationItem 新增 `direction: 'down' | 'up'` 字段
  - 面包屑中显示 ↓/↑ 图标区分穿透方向
  - _Requirements: F1.5_

- [x] 1.7 双向穿透测试
  - `test_note_trace_source.py`：附注 cell 追溯 + 无来源 + 权限
  - `test_report_line_composition.py`：构成科目 + 空行 + 占比计算
  - `TraceSourcePopover.spec.ts`：渲染 + 跳转 + 空数据
  - _Requirements: 测试矩阵_

### Sprint 2 — F2 LLM 规则类引擎接入

- [x] 2.1 创建统一 LLM 调用服务
  - 创建 `backend/app/services/llm_service.py`
  - 实现 LLMService 类（generate 方法）
  - OpenAI 兼容 API 调用（httpx async）
  - 超时 30s + 失败降级（返回 is_stub=True）
  - 调用日志记录（耗时/token 数/成功率）
  - _Requirements: F2.1, F2.4_

- [x] 2.2 改造 wp_k_expense_analysis.py
  - 在规则引擎执行后增加 LLM 调用分支
  - 构建 prompt：规则结果 + 科目名称 + 行业数据 → 自然语言解释请求
  - LLM 成功：返回 ai_explanation + is_llm_stub=False
  - LLM 失败：返回规则结果 + is_llm_stub=True + 降级提示
  - 受 `settings.WP_AI_SERVICE_ENABLED` 控制
  - _Requirements: F2.1~F2.4_

- [x] 2.3 前端 Markdown 渲染集成
  - ExpenseAnalysisDialog.vue 中 ai_explanation 字段使用 Markdown 渲染
  - 安装 `marked` 或 `markdown-it`（轻量 Markdown 解析器）
  - XSS 防护：使用 DOMPurify 清理 HTML 输出
  - is_llm_stub=True 时显示灰色提示文本
  - _Requirements: F2.5_

- [x] 2.4 LLM 调用监控
  - 创建 `backend/app/services/llm_metrics.py`
  - 记录每次调用：timestamp / duration_ms / tokens_used / success / model
  - 提供 `GET /api/admin/llm-metrics` 端点（仅 admin）
  - 前端 PerformanceMonitor 页面新增 LLM 调用统计 Tab
  - _Requirements: 非功能需求-可观测性_

- [x] 2.5 LLM 接入测试
  - `test_llm_service.py`：mock vLLM 响应 + 超时降级 + 错误处理
  - `test_k_expense_with_llm.py`：WP_AI_SERVICE_ENABLED=True/False 两态测试
  - 集成测试（需真实 vLLM 运行）：验证端到端 LLM 调用
  - _Requirements: 测试矩阵_

### Sprint 3 — F3 压力测试 + 性能优化

- [x] 3.1 安装配置 Locust
  - `pip install locust` 添加到 dev dependencies
  - 创建 `tests/load/locustfile.py`
  - 创建 `tests/load/README.md`（使用说明）
  - _Requirements: F3.1_

- [x] 3.2 编写压测场景
  - 场景 1：登录（权重 1）
  - 场景 2：查询试算表（权重 3）
  - 场景 3：查询底稿列表（权重 2）
  - 场景 4：编辑并保存底稿（权重 1）
  - 场景 5：穿透查询（权重 2）
  - 配置梯度加压：100→500→1000→3000→6000
  - _Requirements: F3.1, F3.2_

- [x] 3.3 执行基线压测
  - 运行 Locust 100 用户基线测试
  - 记录 P50/P95/P99 响应时间
  - 记录吞吐量(RPS) + 错误率
  - 记录 CPU/内存/DB 连接数
  - 输出基线报告 `tests/load/baseline_report.md`
  - _Requirements: F3.3_

- [x] 3.4 识别瓶颈并优化
  - 分析慢查询（PG pg_stat_statements）
  - 优化 DB 连接池配置（pool_size/max_overflow）
  - 添加关键查询索引（tb_balance 复合索引）
  - 添加 Redis 查询缓存（TB 数据 60s TTL）
  - 优化 prefill 结果缓存
  - _Requirements: F3.4_

- [x] 3.5 执行目标压测
  - 运行 Locust 6000 用户压测
  - 验证 P95 ≤ 2s / 错误率 < 0.1%
  - 如未达标：继续优化 → 重测
  - 输出最终报告 `tests/load/final_report.md`
  - _Requirements: F3.4_

### Sprint 4 — F4 暗色模式

- [x] 4.1 定义暗色 CSS 变量
  - 在 `gt-design-tokens.css` 新增 `html.dark { ... }` 变量集
  - 覆盖所有 `--gt-*` 变量（背景/文字/边框/表格/弹窗/图表）
  - 确保对比度满足 WCAG AA（文字与背景对比度 ≥ 4.5:1）
  - _Requirements: F4.3_

- [x] 4.2 创建 useTheme composable
  - 创建 `audit-platform/frontend/src/composables/useTheme.ts`
  - isDark ref + toggle 方法
  - localStorage 持久化 `gt_theme`
  - onMounted 初始化 html.dark class
  - 监听系统主题偏好（prefers-color-scheme）作为默认值
  - _Requirements: F4.1, F4.4_

- [x] 4.3 集成 Element Plus 暗色主题
  - main.ts 引入 `element-plus/theme-chalk/dark/css-vars.css`
  - App.vue 或 DefaultLayout 中根据 isDark 切换 html class
  - 验证 el-table/el-dialog/el-form 等核心组件暗色正确
  - _Requirements: F4.5_

- [x] 4.4 顶栏主题切换按钮
  - DefaultLayout.vue 顶栏右侧新增主题切换按钮（☀️/🌙）
  - 点击调用 useTheme.toggle()
  - 切换动画：200ms transition（background-color + color）
  - _Requirements: F4.1, F4.2_

- [x] 4.5 核心页面暗色适配
  - 适配 TrialBalance.vue（表格/工具栏/穿透弹窗）
  - 适配 WorkpaperEditor.vue（Univer 编辑器/工具栏/侧边栏）
  - 适配 ReportView.vue（报表表格/横幅）
  - 适配 Dashboard.vue / PartnerProjectDashboard.vue（图表/卡片）
  - 适配 WorkpaperList.vue / Adjustments.vue / Misstatements.vue
  - 适配 Login.vue / Projects.vue
  - 验证 ≥ 10 个核心页面暗色正确
  - _Requirements: F4.3_

- [x] 4.6 打印强制 light 主题
  - `@media print { html.dark { ... } }` 强制覆盖为 light 变量
  - 验证暗色模式下打印预览为白色背景
  - _Requirements: 非功能需求_

- [x] 4.7 暗色模式测试
  - `useTheme.spec.ts`：toggle + 持久化 + 初始化
  - vitest snapshot：核心组件 dark class 下渲染正确
  - 手动验证：10 个页面暗色无明显视觉问题
  - _Requirements: 测试矩阵_

### Sprint 5 — F5 Storybook 搭建

- [x] 5.1 安装配置 Storybook
  - `npx storybook@latest init --type vue3-vite`
  - 配置 `.storybook/main.ts`（Vite 插件/alias/静态资源）
  - 配置 `.storybook/preview.ts`（全局样式/Element Plus/Pinia mock）
  - 验证 `npm run storybook` 启动成功
  - _Requirements: F5.3_

- [x] 5.2 编写 common 组件 stories（第一批 14 个）
  - GtEditableTable / GtToolbar / GtPageHeader / GtAmountCell / GtStatusTag / GtInfoBar / GtPrintPreview
  - CellContextMenu / SelectionBar / TableSearchBar / CommentTooltip / LoadingState / ValidationList / OperationFeedback
  - 每个 story 含：Default + Props 变体 + 交互示例
  - _Requirements: F5.1, F5.2_

- [x] 5.3 编写 common 组件 stories（第二批 14 个）
  - VirtualScrollTable / CommentThread / SyncStatusIndicator / ExcelImportPreviewDialog
  - KnowledgePickerDialog / SharedTemplatePicker / GtConsolWizard
  - GlobalSearchDialog / DrilldownBreadcrumb / ConflictDialog / BatchActionBar
  - PrefillDiffPanel / SignGateChecklist / VRHeatmap
  - _Requirements: F5.1, F5.2_

- [x] 5.4 编写业务组件 stories（5 个）
  - WorkpaperEditor 子组件（ReviewLayerBadges / ProcedureTrimmingPanel）
  - PartnerProjectDashboard 子组件（CycleProgressRing / VRSummaryCard）
  - ForceGraph（联动全景图）
  - _Requirements: F5.1_

- [x] 5.5 编写组件使用指南文档
  - 创建 `frontend/src/stories/docs/ComponentGuide.mdx`
  - 内容：何时用 GtEditableTable vs 原生 el-table / 何时用 GtPageHeader vs 白色工具栏 / 金额格式化规范 / 表格字号规范
  - _Requirements: F5.4_

- [x] 5.6 Storybook 构建验证
  - `npm run build-storybook` 成功
  - 所有 stories 无 console error
  - 输出静态文件可部署到内网
  - _Requirements: F5.3_

---

## UAT 验收清单

- [x] UAT-1 (P0): 附注 auto cell 点击 → 显示来源报表行 + 构成科目
- [x] UAT-2 (P0): 报表行点击 → 显示构成科目 → 点击科目跳转 TB
- [ ] UAT-3 (P0): K 费用异常分析 → LLM 返回自然语言解释（非 stub 文本）
- [x] UAT-4 (P0): LLM 超时 → 降级显示规则结果 + 提示
- [ ] UAT-5 (P0): 6000 并发压测 P95 ≤ 2s
- [x] UAT-6 (P1): 暗色模式切换 → 10 个核心页面正确显示
- [x] UAT-7 (P1): 暗色模式打印 → 强制 light 主题
- [x] UAT-8 (P1): Storybook 启动 → 33+ stories 可浏览
- [x] UAT-9 (P1): 面包屑显示穿透方向（↑/↓）
- [x] UAT-10 (P2): Storybook 组件指南文档可读

---

## 摘要

| Sprint | 功能 | Tasks | 预计工时 |
|--------|------|-------|---------|
| Sprint 1 | F1 双向穿透 | 1.1~1.7 (7 tasks) | 3 天 |
| Sprint 2 | F2 LLM 接入 | 2.1~2.5 (5 tasks) | 3 天 |
| Sprint 3 | F3 压力测试 | 3.1~3.5 (5 tasks) | 3 天 |
| Sprint 4 | F4 暗色模式 | 4.1~4.7 (7 tasks) | 3 天 |
| Sprint 5 | F5 Storybook | 5.1~5.6 (6 tasks) | 3 天 |
| **合计** | | **30 tasks** | **15 天** |

注：Sprint 3/4/5 可并行推进（无依赖关系），实际工期可压缩到 ~10 天。
