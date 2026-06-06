# 组件账

> 登记平台全局/公共组件的适用场景、禁用规则和迁移计划。新增页面 PR 必须声明使用了哪些全局组件。

## 登记规则

- 全局组件位于 `frontend/src/components/common/`
- 业务组件位于对应模块目录（workpaper/report/disclosure 等）
- 新增页面必须优先使用已有全局组件，不可重复造轮子
- 标记 ⛔ 的组件禁止新代码使用

## 全局组件登记表

| 组件名 | 路径 | 适用场景 | 状态 | 备注 |
|--------|------|----------|------|------|
| GtAmountCell | `components/common/GtAmountCell.vue` | 金额单元格展示（元、千分位） | ✅ 推荐 | 统一金额格式化 |
| GtTableExtended | `components/common/GtTableExtended.vue` | 带排序/筛选/合计行的表格 | ✅ 推荐 | 替代裸 el-table |
| GtFormTable | `components/common/GtFormTable.vue` | 表单内嵌表格（可编辑行） | ✅ 推荐 | 调整分录/科目映射 |
| GtToolbar | `components/common/GtToolbar.vue` | 页面顶部操作栏 | ✅ 推荐 | 搜索+批量操作 |
| GtEmpty | `components/common/GtEmpty.vue` | 空状态占位 | ✅ 推荐 | 中文空态文案 |
| GtInfoBar | `components/common/GtInfoBar.vue` | 页面信息提示条 | ✅ 推荐 | 警告/提示 |
| GtPageHeader | `components/common/GtPageHeader.vue` | 页面标题+面包屑 | ✅ 推荐 | 统一导航 |
| CellContextMenu | `components/common/CellContextMenu.vue` | 单元格右键菜单 | ✅ 推荐 | 报表/底稿穿透 |
| GtDForm | `components/workpaper/GtDForm/` | D 类审计程序表 | ✅ 业务 | 含 QA/Review/Table 子组件 |
| GtBIndex | `components/workpaper/GtBIndex.vue` | B-Index 底稿目录 | ✅ 业务 | 流程图+循环导航 |

## 禁用/待迁移组件

| 组件名 | 原因 | 替代方案 | 迁移计划 |
|--------|------|----------|----------|
| GTChart | 功能与 ECharts 直接调用重复 | 按需直接用 ECharts | P2 统一图表方案 |

## 变更历史

| 日期 | 变更 | PR |
|------|------|----|
| 2025-01-01 | 初始骨架创建 | — |
