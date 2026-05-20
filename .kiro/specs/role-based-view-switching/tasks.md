# Implementation Plan: 角色视图切换 (Role-Based View Switching)

## Overview

基于 requirements.md 和 design.md，将角色视图切换功能拆分为 2 个 Sprint。纯前端实现（Vue 3 + TypeScript + Element Plus），不涉及后端改动。前端属性测试使用 fast-check。

预计工时：2 天（Sprint 1: 1 天，Sprint 2: 1 天）

## Tasks

- [ ] 1. Sprint 1 — composable + ViewSwitcher 组件 + 4 视图预设
  - [ ] 1.1 创建 viewPresetConfig.ts 配置文件
    - 创建 `frontend/src/composables/viewPresetConfig.ts`
    - 定义 `ViewPresetId` / `ViewPresetConfig` / `HighlightRule` / `BadgeRule` / `HighlightContext` 类型
    - 定义 `ROLE_DEFAULT_MAP`（角色→默认视图映射）
    - 定义 `STATUS_PRIORITY` 常量（pending=0 / in_progress=1 / completed=2 / reviewed=3）
    - 实现 `statusPrioritySort` / `riskLevelSort` / `wpCodeNaturalSort` 排序函数
    - 实现 `isKeyJudgmentPoint` 质控过滤函数（正则 `^(B15|A15|B50-4|[A-Z]\d+-1$)`）
    - 实现 `partnerSummary` / `qcSummary` 汇总函数
    - _Requirements: 3.1, 4.5, 5.1, 6.1_

  - [ ] 1.2 创建 useRoleViewPreset composable
    - 创建 `frontend/src/composables/useRoleViewPreset.ts`
    - 接收参数：`projectId` / `userId` / `wpList` / `searchKeyword` / `manualFilters`
    - 实现 localStorage 读写：key 格式 `gt_wp_view_preset_{userId}`
    - 实现 `getDefaultPreset(role)` 按 ROLE_DEFAULT_MAP 返回默认视图
    - 初始化逻辑：读 localStorage → 校验有效性 → 无效则回退角色默认
    - 实现 `switchPreset(id)` → 更新 activePreset + 写 localStorage
    - 实现 `processedList` computed：先 filterFn（质控）→ 再 sortFn → 叠加 manualFilters + searchKeyword
    - 实现 `highlightMap` computed：遍历 wpList 对每行应用 highlightRules
    - 实现 `badgeMap` computed：遍历 wpList 对每行应用 badgeRules
    - 实现 `groupedList` computed：经理视图按 groupBy 分组 + 计算进度 + 折叠状态
    - 实现 `summaryData` computed：调用 summaryFn
    - _Requirements: 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 7.2, 7.4_

  - [ ] 1.3 创建 HighlightContext 数据注入
    - 在 `useRoleViewPreset` 中构建 `HighlightContext` 对象
    - `prerequisiteStatus`：从已有 `usePrerequisiteStatus` 批量查询结果构建 Map
    - `consistencyGate`：从已有 consistency_gate 缓存数据构建 Map
    - `reviewRecords`：从已有 review_records 数据构建 Map（筛选 status=open）
    - 数据未就绪时返回空 Map（高亮规则安全跳过）
    - _Requirements: 3.2, 3.4, 5.1, 5.2, 5.4, 6.4_

  - [ ] 1.4 实现助理视图预设配置
    - 在 `VIEW_PRESET_CONFIG.assistant` 中配置：
    - sortFn: statusPrioritySort（pending→in_progress→completed→reviewed）
    - highlightRules[0]: prerequisite blocked → 橙色左边框 3px + tooltip 显示缺失编码
    - highlightRules[1]: completed/reviewed → 灰色文字 color:#999
    - 无 filterFn / 无 groupBy / 无 badgeRules
    - _Requirements: 3.1, 3.2, 3.3, 3.5_

  - [ ] 1.5 实现经理视图预设配置
    - 在 `VIEW_PRESET_CONFIG.manager` 中配置：
    - sortFn: wpCodeNaturalSort（分组内排序）
    - groupBy: `(item) => item.audit_cycle`
    - groupedList 计算：每组 completed/total 进度 + 裁剪数统计
    - 折叠逻辑：进度 < 100% 展开，100% 折叠
    - 无 highlightRules / 无 badgeRules
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ] 1.6 实现合伙人视图预设配置
    - 在 `VIEW_PRESET_CONFIG.partner` 中配置：
    - sortFn: riskLevelSort（高→中→低，基于 consistency_gate blocking/warning 状态）
    - highlightRules[0]: blocking VR 未通过 → 红色背景 rgba(255,0,0,0.08) + 红色左边框 3px
    - badgeRules[0]: 复核意见数 badge（status=open 计数，>0 显示 danger 类型）
    - summaryFn: partnerSummary（blocking 未通过总数 + 未解决复核意见总数）
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ] 1.7 实现质控视图预设配置
    - 在 `VIEW_PRESET_CONFIG.qc` 中配置：
    - sortFn: riskLevelSort
    - filterFn: isKeyJudgmentPoint（B15/A15/B50-4/各循环审定表 `^[A-Z]\d+-1$`）
    - highlightRules[0]: review_status !== 'reviewed' → 黄色背景 rgba(255,200,0,0.08)
    - summaryFn: qcSummary（抽查路径建议 — 按风险从高到低排列编码序列）
    - 空结果时返回空状态标记
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ] 1.8 创建 ViewSwitcher.vue 组件
    - 创建 `frontend/src/components/workpaper/ViewSwitcher.vue`
    - el-select 下拉，4 个选项带图标前缀（👤/📊/🔍/✅）
    - Props: `modelValue: ViewPresetId` / `disabled: boolean`
    - Emits: `update:modelValue`
    - 样式：与筛选栏其他 el-select 对齐（size=default, width=160px）
    - _Requirements: 1.1, 1.4_

- [ ] 2. Sprint 2 — 集成 WorkpaperList + 测试 + 回归
  - [ ] 2.1 集成 ViewSwitcher 到 WorkpaperList.vue
    - 在筛选栏 `.gt-wp-filter-bar` 最左侧插入 ViewSwitcher 组件
    - 仅 `viewMode === 'list'` 时显示（v-if）
    - 绑定 `useRoleViewPreset` 的 activePreset
    - 视图切换时保留 searchKeyword（不清空）
    - viewMode 切换到其他模式再切回时恢复之前的 activePreset
    - _Requirements: 1.3, 1.5, 8.1, 8.5_

  - [ ] 2.2 集成排序/过滤到 WorkpaperList 列表渲染
    - 将现有 el-table :data 绑定替换为 `processedList`（已排序+已过滤）
    - 经理视图：替换为分组折叠渲染（v-for groupedList + el-collapse）
    - 质控视图：使用 filterFn 过滤后的子集 + 空状态提示
    - 确保与现有 manualFilters（循环/状态/编制人）叠加生效
    - _Requirements: 3.1, 4.1, 5.1, 6.1, 7.4_

  - [ ] 2.3 集成高亮/badge 到列表行渲染
    - el-table :row-style 绑定 highlightMap（行级样式）
    - 助理视图：橙色左边框 + ⚠️ 图标（hover tooltip 显示缺失前置编码）
    - 合伙人视图：红色背景 + 复核意见数 el-badge
    - 质控视图：黄色背景 + 独立复核标记列（✓/○）
    - 经理视图：分组头进度条 + 裁剪标签
    - _Requirements: 3.2, 3.3, 3.5, 4.2, 4.3, 5.2, 5.3, 5.4, 6.2, 6.4_

  - [ ] 2.4 集成汇总统计面板
    - 合伙人视图：列表顶部显示 blocking 未通过总数 + 未解决复核意见总数
    - 质控视图：列表顶部显示抽查路径建议（编码序列）
    - 仅对应视图激活时显示（v-if activePreset === 'partner'/'qc'）
    - _Requirements: 5.5, 6.3_

  - [ ] 2.5 编写 useRoleViewPreset 单元测试
    - 创建 `frontend/src/composables/__tests__/useRoleViewPreset.spec.ts`
    - 测试角色默认映射：assistant→assistant / manager→manager / partner→partner / qc→qc / admin→partner
    - 测试 localStorage 读写：写入后读取一致 / 无效值回退 / 空值回退
    - 测试助理视图排序：pending < in_progress < completed < reviewed
    - 测试合伙人视图排序：blocking > warning > pass
    - 测试质控视图过滤：B15/A15/B50-4/D2-1 通过 / D2-2/B23-1 不通过
    - 测试高亮规则：blocked prereq → 橙色 / blocking VR → 红色 / unreviewed → 黄色
    - 测试搜索关键词保留：切换视图后 searchKeyword 不变
    - _Requirements: 1.2, 2.1-2.4, 3.1, 5.1, 6.1, 7.2_

  - [ ] 2.6 编写 ViewSwitcher 组件测试
    - 创建 `frontend/src/components/workpaper/__tests__/ViewSwitcher.spec.ts`
    - 测试渲染 4 个选项（助理/经理/合伙人/质控）
    - 测试选择事件 emit update:modelValue
    - 测试 disabled 状态
    - 测试 viewMode !== 'list' 时不渲染（由父组件 v-if 控制）
    - _Requirements: 1.1, 1.4, 8.1_

  - [ ]* 2.7 Write property test: view switch data invariant (P1)
    - **Property 1: View switch data invariant**
    - 创建 `frontend/src/composables/__tests__/useRoleViewPreset.pbt.spec.ts`
    - 使用 fast-check 生成随机底稿列表（1~100 项，随机 wp_code/status/audit_cycle）
    - 对非 QC 视图切换：验证 processedList 的 ID 集合 === 输入 ID 集合
    - 对 QC 视图：验证 processedList ID 集合 ⊆ 输入 ID 集合
    - 对 QC→其他视图切换：验证恢复完整集合
    - ≥ 100 iterations
    - **Validates: Requirements 7.2, 7.3**

  - [ ]* 2.8 Write property test: persistence round-trip (P2)
    - **Property 2: Persistence round-trip**
    - 使用 fast-check 生成随机 ViewPresetId + 随机 userId
    - 执行 switchPreset → 模拟页面重载（重新初始化 composable）→ 验证 activePreset === 写入值
    - 生成随机无效字符串写入 localStorage → 验证初始化后回退到角色默认
    - ≥ 100 iterations
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

  - [ ]* 2.9 Write property test: sort stability (P3)
    - **Property 3: Sort stability**
    - 使用 fast-check 生成含重复 sort key 的底稿列表（如多个 pending 状态）
    - 对每种视图执行排序 → 验证同 sort key 的项保持原始相对顺序
    - 切换视图再切回 → 验证同 key 项顺序不变
    - ≥ 100 iterations
    - **Validates: Requirements 3.1, 4.5, 5.1**

- [ ] 3. Checkpoint — 全部测试通过 + 回归验证
  - [ ] 3.1 运行现有 WorkpaperList 相关测试确认零回归
    - 运行 `vitest --run` 确认现有 workpaper 相关测试全绿
    - 确认 viewMode 切换（kanban/workbench/lifecycle/graph/matrix）不受影响
    - 确认搜索/批量下载/批量委派功能正常
    - _Requirements: 8.2, 8.3, 8.4_

  - [ ] 3.2 vue-tsc 类型检查通过
    - 运行 `vue-tsc --noEmit` 确认零新增类型错误
    - 确认 ViewPresetConfig 类型定义与实际使用一致

## Notes

- Tasks marked with `*` are optional PBT tasks (can be skipped for faster MVP)
- Sprint 1（composable + 组件 + 4 预设）预计 1 天
- Sprint 2（集成 + 测试 + 回归）预计 1 天
- 纯前端实现，不涉及后端改动，不需要 Alembic 迁移
- 前端 PBT 使用 fast-check（≥ 100 iterations）
- 复用已有数据源：usePrerequisiteStatus / consistency_gate 缓存 / review_records
- localStorage key 含 userId 避免多用户冲突
