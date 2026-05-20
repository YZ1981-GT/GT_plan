# Requirements Document — 角色视图切换 (Role-Based View Switching)

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v0.1 | 2026-05-20 | 初始起草 |

## 依赖矩阵

| 依赖项 | 类型 | 状态 |
|--------|------|------|
| usePermission composable | 前端 | ✅ 已有角色判断（role computed） |
| WorkpaperList.vue | 前端 | ✅ 已有页面，含筛选栏/排序/多视图模式 |
| usePrerequisiteStatus composable | 前端 | ✅ 已有前置依赖状态查询 |
| consistency_gate VR 结果 | 后端 | ✅ 已有 blocking/warning/info 三级 |
| review_records | 后端 | ✅ 已有复核意见数据 |
| RBAC 角色体系 | 后端 | ✅ 已有 admin/partner/manager/assistant/qc |
| Element Plus | 前端依赖 | ✅ 已有 |
| localStorage | 浏览器 API | ✅ 原生支持 |

## Introduction

### 业务痛点

1. **所有角色看到相同页面**：当前 WorkpaperList 页面对所有角色展示完全相同的排序/过滤/高亮，仅按钮 disabled/hidden 有差异，无法体现不同角色的工作重点
2. **助理找不到优先任务**：助理需要手动排序才能看到待完成程序的优先级，前置依赖未满足的底稿没有视觉提示
3. **经理缺少进度全景**：项目经理需要按循环分组查看进度百分比和裁剪状态，当前列表视图无此聚合
4. **合伙人无法快速定位阻断项**：blocking VR 未通过的底稿散落在列表中无高亮，复核意见数需逐个点开才能看到
5. **质控视角缺失**：质控只关心关键判断点底稿（B15/A15/B50-4/各循环审定表），当前无过滤预设，需手动搜索
6. **视图偏好不持久**：用户每次打开页面都需要重新设置排序/过滤条件

### 技术根因

- WorkpaperList.vue 的排序/过滤逻辑是全局统一的，无角色维度的预设配置
- 前端已有 `usePermission` 可获取当前角色，但未用于驱动视图差异化
- 已有 `usePrerequisiteStatus` 可查询前置依赖状态，但未在列表层面做高亮
- consistency_gate VR 结果已有但未在列表行级别做视觉标记
- review_records 数据已有但未在列表行级别显示 badge 计数
- 无 localStorage 持久化视图偏好的机制

### 范围边界

**必做（In Scope）：**
- WorkpaperList 页面顶部增加"视图切换"下拉组件
- 4 种角色视图预设（助理/经理/合伙人/质控）
- 默认视图按当前用户角色自动选择
- 助理视图：按状态排序 + 前置依赖未满足高亮
- 经理视图：按循环分组折叠 + 进度条 + 裁剪状态标记
- 合伙人视图：按风险等级排序 + blocking VR 红色高亮 + 复核意见数 badge
- 质控视图：只显示关键判断点底稿 + 独立复核标记
- 视图偏好持久化到 localStorage
- 用户可手动切换到非默认视图

**排除（Out of Scope）：**
- 不新增后端端点（前端纯展示层切换，数据已有）
- 不影响现有 WorkpaperList 的基础功能（搜索/分页/导出/批量操作）
- 不影响其他视图模式（看板/工作台/生命周期/依赖图/委派矩阵）
- 不涉及自定义视图配置（用户自建视图规则）
- 不涉及后端数据结构变更

## Glossary

- **View_Switcher**：视图切换下拉组件，位于 WorkpaperList 筛选栏区域
- **Role_View_Preset**：角色视图预设配置，定义排序/过滤/高亮规则
- **Assistant_View**：助理视图，按状态排序 + 前置依赖高亮
- **Manager_View**：经理视图，按循环分组折叠 + 进度条 + 裁剪标记
- **Partner_View**：合伙人视图，按风险等级排序 + blocking VR 高亮 + 复核意见 badge
- **QC_View**：质控视图，仅显示关键判断点底稿 + 独立复核标记
- **View_Persistence**：视图持久化模块，localStorage 存储用户上次选择的视图
- **Highlight_Rule**：高亮规则，定义行级别的视觉标记条件和样式

## Requirements

### Requirement 1: 视图切换组件

**User Story:** As a 审计团队成员, I want to 在底稿列表页面顶部看到视图切换下拉, so that 我可以快速切换到适合自己角色的视图预设。

#### Acceptance Criteria

1. THE View_Switcher SHALL 在 WorkpaperList 筛选栏左侧显示为 el-select 下拉组件，提供四个选项：助理视图 / 经理视图 / 合伙人视图 / 质控视图
2. WHEN 用户首次打开 WorkpaperList 页面, THE View_Switcher SHALL 根据当前用户角色自动选择默认视图（assistant→助理视图 / manager→经理视图 / partner→合伙人视图 / qc→质控视图 / admin→合伙人视图）
3. WHEN 用户手动选择一个视图, THE View_Switcher SHALL 立即应用该视图的排序/过滤/高亮规则，无需刷新页面
4. THE View_Switcher SHALL 允许任何角色切换到任何视图（如助理可选择合伙人视图查看风险分布）
5. WHEN 视图切换时, THE View_Switcher SHALL 保留用户已输入的搜索关键词（searchKeyword 不清空）

### Requirement 2: 视图偏好持久化

**User Story:** As a 用户, I want to 下次打开页面时自动恢复上次选择的视图, so that 我不需要每次重新选择。

#### Acceptance Criteria

1. WHEN 用户切换视图, THE View_Persistence SHALL 将选择的视图标识写入 localStorage（key 格式：`gt_wp_view_preset_{userId}`）
2. WHEN 用户再次打开 WorkpaperList 页面, THE View_Persistence SHALL 优先从 localStorage 读取上次选择的视图标识
3. IF localStorage 中无存储值, THEN THE View_Persistence SHALL 回退到按角色自动选择默认视图
4. IF localStorage 中存储的视图标识无效（如被篡改）, THEN THE View_Persistence SHALL 忽略无效值并回退到角色默认视图

### Requirement 3: 助理视图

**User Story:** As a 审计助理, I want to 看到按优先级排列的待完成底稿并高亮前置依赖未满足的项, so that 我可以按正确顺序执行工作。

#### Acceptance Criteria

1. WHILE 助理视图激活, THE Assistant_View SHALL 按状态排序底稿列表：pending → in_progress → completed → reviewed
2. WHILE 助理视图激活, THE Assistant_View SHALL 对前置依赖未满足的底稿行添加橙色左边框（3px solid）+ 工具提示显示缺失的前置底稿编码
3. WHILE 助理视图激活, THE Assistant_View SHALL 在状态列旁显示前置依赖图标（⚠️），hover 时展示具体缺失项列表
4. THE Assistant_View SHALL 使用已有 usePrerequisiteStatus composable 获取前置依赖数据，对 overall='blocked' 的底稿触发高亮
5. WHILE 助理视图激活, THE Assistant_View SHALL 将已完成（completed/reviewed）底稿行文字颜色降为灰色（视觉降权）

### Requirement 4: 经理视图

**User Story:** As a 项目经理, I want to 按循环分组查看底稿并看到每组的进度百分比和裁剪状态, so that 我可以快速掌握各循环执行进度。

#### Acceptance Criteria

1. WHILE 经理视图激活, THE Manager_View SHALL 将底稿列表按审计循环（audit_cycle 字段）分组，每组显示为可折叠的分组头
2. WHILE 经理视图激活, THE Manager_View SHALL 在每个循环分组头显示进度条（已完成数 / 总数 × 100%）
3. WHILE 经理视图激活, THE Manager_View SHALL 在分组头右侧显示裁剪状态标记（如有已裁剪程序则显示"已裁剪 N 项"灰色标签）
4. WHILE 经理视图激活, THE Manager_View SHALL 默认展开进度 < 100% 的循环分组，折叠已 100% 完成的分组
5. WHILE 经理视图激活, THE Manager_View SHALL 在分组内按 wp_code 自然排序底稿

### Requirement 5: 合伙人视图

**User Story:** As a 合伙人, I want to 按风险等级排序底稿并高亮 blocking VR 未通过项和复核意见数, so that 我可以快速判断项目是否具备签字条件。

#### Acceptance Criteria

1. WHILE 合伙人视图激活, THE Partner_View SHALL 按风险等级排序底稿列表：高风险 → 中风险 → 低风险（风险等级从底稿关联的 VR 规则 severity 推断：有 blocking 未通过 = 高风险 / 有 warning 未通过 = 中风险 / 全部通过 = 低风险）
2. WHILE 合伙人视图激活, THE Partner_View SHALL 对 blocking VR 未通过的底稿行添加红色背景高亮（rgba(255,0,0,0.08)）+ 左侧 3px 红色竖线
3. WHILE 合伙人视图激活, THE Partner_View SHALL 在每行右侧显示复核意见数 badge（el-badge），数值为该底稿关联的 status=open 复核意见条数
4. WHEN 复核意见数 > 0, THE Partner_View SHALL 将 badge 显示为红色（type=danger）
5. WHILE 合伙人视图激活, THE Partner_View SHALL 在列表顶部显示汇总统计：blocking 未通过总数 / 未解决复核意见总数

### Requirement 6: 质控视图

**User Story:** As a 质控人员, I want to 只看到关键判断点底稿并标记独立复核状态, so that 我可以快速定位需要审阅的核心底稿。

#### Acceptance Criteria

1. WHILE 质控视图激活, THE QC_View SHALL 仅显示关键判断点底稿：B15（重要性水平）/ A15（持续经营）/ B50-4（特别风险）/ 各循环审定表（wp_code 匹配 `^[A-Z]\d+-1$` 模式，如 D2-1/F2-1/H1-1）
2. WHILE 质控视图激活, THE QC_View SHALL 在每行显示独立复核标记列（已复核 ✓ / 未复核 ○），数据来源为 review_status 字段
3. WHILE 质控视图激活, THE QC_View SHALL 在列表顶部显示抽查路径建议（按风险从高到低排列的底稿编码序列）
4. WHILE 质控视图激活, THE QC_View SHALL 对未复核的关键判断点底稿行添加黄色背景高亮（rgba(255,200,0,0.08)）
5. IF 当前项目无匹配的关键判断点底稿, THEN THE QC_View SHALL 显示空状态提示"当前项目暂无关键判断点底稿"

### Requirement 7: 视图切换不影响数据

**User Story:** As a 开发者, I want to 视图切换仅改变展示方式而不影响底层数据, so that 不同视图看到的是同一份数据的不同呈现。

#### Acceptance Criteria

1. THE View_Switcher SHALL 在切换视图时不触发任何后端 API 请求（纯前端排序/过滤/高亮）
2. THE View_Switcher SHALL 保证切换视图前后底稿总数不变（质控视图的过滤除外，质控视图显示过滤后的子集但不删除数据）
3. WHEN 从质控视图切换到其他视图, THE View_Switcher SHALL 恢复显示全部底稿（移除质控过滤）
4. THE View_Switcher SHALL 与现有筛选栏（循环/状态/编制人）叠加生效：视图预设的排序/高亮 + 用户手动筛选条件同时作用

### Requirement 8: 与现有功能兼容

**User Story:** As a 用户, I want to 视图切换不影响现有的搜索/分页/导出/批量操作功能, so that 我的日常工作流不被打断。

#### Acceptance Criteria

1. THE View_Switcher SHALL 仅在 viewMode='list' 时生效（看板/工作台/生命周期/依赖图/委派矩阵模式下隐藏视图切换下拉）
2. THE View_Switcher SHALL 不影响现有的搜索关键词过滤逻辑
3. THE View_Switcher SHALL 不影响现有的批量下载/批量委派功能
4. THE View_Switcher SHALL 不影响右侧详情面板的展示内容
5. WHEN viewMode 从 'list' 切换到其他模式再切回, THE View_Switcher SHALL 恢复之前选择的角色视图

## Non-Functional Requirements

### 性能

- 视图切换响应时间 ≤ 100ms（纯前端排序/过滤/高亮，无网络请求）
- 助理视图前置依赖高亮：复用已缓存的 usePrerequisiteStatus 数据，不额外请求
- 合伙人视图 VR 状态：复用已有 consistency_gate 缓存数据

### 兼容性

- 不新增后端端点（纯前端展示层逻辑）
- 不影响现有 WorkpaperList 的 6 种视图模式（list/kanban/workbench/lifecycle/graph/matrix）
- 不影响现有筛选栏组件（搜索/循环/状态/编制人）
- 兼容已有 `usePermission` composable 的角色判断逻辑
- localStorage key 含 userId 避免多用户冲突

### 可观测性

- 前端 console.debug 记录视图切换事件（from → to + userId + timestamp）
- localStorage 写入失败时 console.warn 降级为内存态（不阻断功能）

## Test Matrix

### 单元测试

| 文件 | 覆盖范围 |
|------|----------|
| `frontend/src/composables/__tests__/useRoleViewPreset.spec.ts` | 视图预设逻辑 + 角色默认映射 + localStorage 读写 |
| `frontend/src/components/workpaper/__tests__/ViewSwitcher.spec.ts` | 下拉组件渲染 + 切换事件 + 选项列表 |
| `frontend/src/composables/__tests__/useViewHighlight.spec.ts` | 高亮规则计算 + 行样式生成 |

### PBT (Property-Based Tests)

| ID | Property | 描述 |
|----|----------|------|
| PBT-P1 | view_switch_data_invariant | 任意视图切换前后底稿 ID 集合不变（数据守恒，质控视图为子集） |
| PBT-P2 | persistence_roundtrip | 写入 localStorage 后读取 = 原始视图标识（round-trip） |
| PBT-P3 | sort_stability | 同风险等级/同状态的底稿在排序后保持原始相对顺序（排序稳定性） |

### 集成测试

- 视图切换 → 排序变更 → 高亮应用 → 筛选叠加
- localStorage 持久化 → 页面刷新 → 视图恢复

### UAT

| # | 验收项 | P |
|---|--------|---|
| 1 | 助理登录后默认选中"助理视图"，列表按状态排序 | P0 |
| 2 | 经理登录后默认选中"经理视图"，列表按循环分组折叠 | P0 |
| 3 | 合伙人登录后默认选中"合伙人视图"，blocking VR 底稿红色高亮 | P0 |
| 4 | 质控登录后默认选中"质控视图"，仅显示关键判断点底稿 | P0 |
| 5 | 手动切换视图后刷新页面，恢复上次选择的视图 | P0 |
| 6 | 助理视图中前置依赖未满足的底稿有橙色左边框 + ⚠️ 图标 | P1 |
| 7 | 经理视图中每个循环分组头显示进度条 | P1 |
| 8 | 合伙人视图中复核意见数 badge 正确显示 | P1 |
| 9 | 质控视图中未复核底稿有黄色背景高亮 | P1 |
| 10 | 视图切换不影响搜索/批量下载/批量委派功能 | P0 |
| 11 | 视图切换仅在列表模式下可见（看板等模式隐藏） | P1 |
| 12 | 任何角色可切换到任何视图（无权限限制） | P1 |

**上线门槛：P0 全部 ✓ + P1 ≥ 80% ✓**

## Success Criteria

- 4 种角色登录后各自看到差异化的默认视图（排序/过滤/高亮不同）
- 视图切换 ≤ 100ms 响应（纯前端，零网络请求）
- 视图偏好持久化到 localStorage，刷新后自动恢复
- 不新增后端端点，不影响现有 WorkpaperList 基础功能

## Terminology

| 术语 | 定义 |
|------|------|
| 视图预设 (View Preset) | 预定义的排序/过滤/高亮规则组合 |
| 前置依赖 (Prerequisite) | 底稿执行前需要完成的前置底稿（如 C2 是 D 循环前置） |
| Blocking VR | 阻断签字的验证规则，未通过则项目不可出具报告 |
| 关键判断点 | 审计中需要重大职业判断的底稿（B15/A15/B50-4/各循环审定表） |
| 裁剪状态 | 程序被标记为"不适用"(N/A) 的状态 |
| 独立复核标记 | 质控/EQCR 对底稿进行独立复核后的状态标记 |
