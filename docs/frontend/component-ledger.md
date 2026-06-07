# 组件账

> 登记全局/通用组件的职责、适用场景、是否禁用、迁移计划。新增页面必须说明使用了哪些全局组件。

## 使用说明

- 全局组件位于 `audit-platform/frontend/src/components/common/`
- 新增页面的 PR 必须说明引用了哪些全局组件
- 标记 `🚫 禁用` 的组件不得在新代码中使用
- 标记 `⚠️ 收敛` 的组件有替代方案，应优先使用替代

## 全局组件登记表

| # | 组件名 | 文件路径 | 职责 | 适用场景 | 状态 |
|---|--------|---------|------|---------|------|
| 1 | GtAmountCell | `components/common/GtAmountCell.vue` | 金额显示（千分位、正负色、Decimal 精度） | 所有金额列 | ✅ 活跃 |
| 2 | GtEditableTable | `components/common/GtEditableTable.vue` | 可编辑表格（行增删改、校验） | 调整分录、底稿网格 | ✅ 活跃 |
| 3 | GtPageShell | `components/common/GtPageShell.vue` | 页面外壳（标题栏+面包屑+内容区） | 所有一级页面 | ✅ 活跃 |
| 4 | GtToolbar | `components/common/GtToolbar.vue` | 工具栏（按钮组+搜索+筛选） | 列表页顶部 | ✅ 活跃 |
| 5 | GtStatusTag | `components/common/GtStatusTag.vue` | 状态标签（颜色映射枚举状态） | 表格状态列 | ✅ 活跃 |
| 6 | GtVirtualTable | `components/common/GtVirtualTable.vue` | 虚拟滚动表格（大数据量） | 序时账、科目余额 >1000 行 | ✅ 活跃 |
| 7 | GtLoadingOverlay | `components/common/GtLoadingOverlay.vue` | 全局加载遮罩 | 异步操作等待 | ✅ 活跃 |
| 8 | GlobalSearchDialog | `components/common/GlobalSearchDialog.vue` | 全局搜索弹窗 | 顶部导航快捷键触发 | ✅ 活跃 |
| 9 | DrilldownBreadcrumb | `components/common/DrilldownBreadcrumb.vue` | 穿透面包屑导航 | 报表→科目→分录穿透链 | ✅ 活跃 |
| 10 | DegradedBanner | `components/DegradedBanner.vue` | 降级状态横幅（Redis/LLM 不可用提示） | 全局顶部 | ✅ 活跃 |

## 业务组件族（高频）

| 组件族 | 代表组件 | 数量 | 说明 |
|--------|---------|------|------|
| AI 组件 | `components/ai/AIChatPanel.vue` | 20+ | AI 对话、确认、内容审查 |
| 协作组件 | `components/collaboration/ReviewPanel.vue` | 20+ | 复核、PBC、时间轴 |
| 合并组件 | `components/consolidation/ConsolWorksheetTabs.vue` | 15+ | 合并底稿工作表 |
| 仪表盘组件 | `components/dashboard/CycleProgressRing.vue` | 10+ | 项目仪表盘卡片 |
| 底稿组件 | `components/workpaper/GtWpRenderer.vue` | 15+ | 底稿渲染、编辑 |

## 禁用/收敛组件

| 组件 | 原因 | 替代方案 | 迁移截止 |
|------|------|---------|---------|
| （暂无登记） | | | |

## 变更记录

| 日期 | 变更人 | 内容 |
|------|--------|------|
| 2026-06-06 | 初始化 | 创建账本骨架，登记 10 个全局组件 + 5 个组件族 |
