# Requirements Document — 合伙人仪表盘 (Partner Dashboard)

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v0.1 | 2026-05-20 | 初始起草 |

## 依赖矩阵

| 依赖项 | 类型 | 状态 |
|--------|------|------|
| ConsistencyGate.run_all_checks | 后端服务 | ✅ 已有 33 条 VR 规则覆盖 11 循环 |
| GET /api/chain/{pid}/consistency-check?year=Y | 后端端点 | ✅ 已有，返回 checks[] + overall |
| GET /api/review-records?project_id=X&status=open | 后端端点 | ✅ 已有，返回 items[] + total |
| useProcedureStatus composable | 前端 | ✅ 已有三档状态追踪（pending/filled/reviewed/approved） |
| procedure-applicability-trimming spec | 前端 | 🔲 待实施（裁剪汇总数据源） |
| ECharts | 前端依赖 | ✅ 已有（package.json 已引入） |
| Element Plus | 前端依赖 | ✅ 已有 |
| Vue Router | 前端依赖 | ✅ 已有 |
| RBAC require_role | 后端 | ✅ 已有角色校验机制 |

## Introduction

### 业务痛点

1. **缺少宏观视角**：当前所有角色看到的 UI 完全相同（仅按钮 disabled/hidden），合伙人/质控无法一屏掌握项目全貌
2. **进度追踪低效**：合伙人需逐个打开 11 个循环底稿才能了解执行进度，无汇总视图
3. **Blocking VR 散落**：33 条 VR 规则结果分散在 consistency_gate 返回中，无按循环分组的 blocking 汇总
4. **复核意见追踪困难**：review_records 表有数据但无面向合伙人的优先级排序 + 跳转入口
5. **关键判断点入口深**：重要性水平(B15)、持续经营(A15)、特别风险(B50-4) 需多次点击才能到达
6. **项目里程碑不可见**：计划→执行→复核→报告的时间线无可视化展示
7. **质控缺少独立视角**：质控需要快速定位关键判断点 + 抽查路径，当前无专属入口

### 技术根因

- 前端路由无 `/projects/:id/dashboard` 页面
- `ConsistencyGate.run_all_checks` 返回扁平 checks[]，缺少按循环分组的聚合端点
- `review_records` 端点无优先级排序 + 关联底稿跳转元数据
- `useProcedureStatus` 按单底稿维度工作，缺少项目级全循环聚合
- 无项目里程碑数据模型（需从已有 project 表 + audit_trail 推断）

### 范围边界

**必做（In Scope）：**
- 新建 `/projects/:id/dashboard` 页面路由
- 全循环进度环形图（D~N 11 个循环完成百分比）
- Blocking VR 汇总卡片（按循环分组）
- 未解决复核意见列表（按优先级排序 + 跳转）
- 关键判断点快速入口（B15 / A15 / B50-4）
- 项目时间线（关键里程碑可视化）
- 裁剪汇总概览（条件渲染：仅当 procedure-applicability-trimming 已实施时显示）
- RBAC：所有角色可查看，合伙人/质控看到更多细节
- 后端聚合端点（不新增 PG 表，聚合已有数据）

**排除（Out of Scope）：**
- 不新增 PostgreSQL 表（纯聚合已有数据）
- 不影响现有 WorkpaperList / WorkpaperEditor 页面
- 不涉及实时 WebSocket 推送（轮询/手动刷新，≤ 5s 延迟）
- 不涉及跨项目汇总（仅单项目维度）
- 不涉及 LLM 智能分析/建议

## Glossary

- **Dashboard_Page**：项目仪表盘页面组件，路由 `/projects/:id/dashboard`
- **Cycle_Progress_Ring**：全循环进度环形图组件，展示 D~N 11 个循环完成百分比
- **VR_Summary_Card**：Blocking VR 汇总卡片组件，按循环分组展示未通过规则
- **Review_Opinion_List**：未解决复核意见列表组件，支持优先级排序和跳转
- **Quick_Entry_Panel**：关键判断点快速入口面板
- **Project_Timeline**：项目时间线组件，展示关键里程碑
- **Trimming_Overview**：裁剪汇总概览组件（条件渲染）
- **Dashboard_Aggregator**：后端聚合服务，组合多数据源返回仪表盘数据
- **Cycle_Code**：审计循环代号（D/E/F/G/H/I/J/K/L/M/N）

## Requirements

### Requirement 1: 仪表盘页面路由与布局

**User Story:** As a 合伙人, I want to 在项目中有一个专属仪表盘首页, so that 我可以一屏掌握项目全貌而无需逐个打开底稿。

#### Acceptance Criteria

1. THE Dashboard_Page SHALL 注册路由 `/projects/:id/dashboard`，合伙人/质控角色登录后默认跳转至此页面
2. THE Dashboard_Page SHALL 采用响应式网格布局，在 1920×1080 分辨率下一屏展示所有核心模块（无需滚动查看关键信息）
3. THE Dashboard_Page SHALL 在页面顶部显示项目名称 + 审计年度 + 最后更新时间
4. WHEN 用户手动点击"刷新"按钮, THE Dashboard_Page SHALL 重新拉取所有聚合数据并更新展示
5. THE Dashboard_Page SHALL 在数据加载期间显示骨架屏（skeleton）占位

### Requirement 2: 全循环进度环形图

**User Story:** As a 合伙人, I want to 一眼看到 11 个审计循环的完成进度, so that 我可以快速识别进度滞后的循环并跟进。

#### Acceptance Criteria

1. THE Cycle_Progress_Ring SHALL 展示 D/E/F/G/H/I/J/K/L/M/N 共 11 个循环的完成百分比环形图
2. THE Cycle_Progress_Ring SHALL 对每个循环计算完成率 = 已完成程序数 / (总程序数 − 已裁剪程序数) × 100%
3. WHEN 某循环完成率 < 50%, THE Cycle_Progress_Ring SHALL 将该循环环形图标记为红色警告色
4. WHEN 某循环完成率 ≥ 50% 且 < 100%, THE Cycle_Progress_Ring SHALL 将该循环环形图标记为橙色进行中色
5. WHEN 某循环完成率 = 100%, THE Cycle_Progress_Ring SHALL 将该循环环形图标记为绿色完成色
6. WHEN 用户点击某个循环环形图, THE Cycle_Progress_Ring SHALL 跳转到该循环的底稿列表页

### Requirement 3: Blocking VR 汇总卡片

**User Story:** As a 合伙人, I want to 看到当前有多少 blocking 规则未通过及其分布, so that 我可以判断项目是否具备签字条件。

#### Acceptance Criteria

1. THE VR_Summary_Card SHALL 在顶部显示 blocking 未通过总数 + 总 VR 规则数（如 "3 / 33 blocking"）
2. THE VR_Summary_Card SHALL 按循环分组展示每个循环的 blocking 未通过数量
3. WHEN 所有 blocking 规则均通过, THE VR_Summary_Card SHALL 显示绿色"全部通过"状态标识
4. WHEN 存在 blocking 未通过, THE VR_Summary_Card SHALL 将对应循环行标记为红色并显示具体规则名称
5. WHEN 用户点击某条未通过规则, THE VR_Summary_Card SHALL 展开显示该规则的 details 描述信息
6. IF ConsistencyGate 返回错误, THEN THE VR_Summary_Card SHALL 显示"数据获取失败"提示并提供重试按钮

### Requirement 4: 未解决复核意见列表

**User Story:** As a 合伙人, I want to 看到所有未解决的复核意见并按优先级排序, so that 我可以追踪关键问题的解决进度。

#### Acceptance Criteria

1. THE Review_Opinion_List SHALL 展示当前项目所有 status=open 的复核意见记录
2. THE Review_Opinion_List SHALL 按以下优先级排序：review_layer 为 L5(合伙人) > L4(经理) > L3(主管) > L2(高级) > L1(助理) > 其他
3. THE Review_Opinion_List SHALL 对每条意见显示：复核层级标签 + 意见摘要（前 80 字符）+ 创建时间 + 关联底稿编码
4. WHEN 用户点击某条复核意见, THE Review_Opinion_List SHALL 跳转到对应底稿的对应 sheet 和 cell 位置
5. THE Review_Opinion_List SHALL 在列表顶部显示统计摘要：总未解决数 + 按层级分布饼图
6. WHEN 未解决意见数为 0, THE Review_Opinion_List SHALL 显示"所有复核意见已解决"的空状态提示

### Requirement 5: 关键判断点快速入口

**User Story:** As a 质控人员, I want to 一键跳转到重要性水平/持续经营/特别风险底稿, so that 我可以快速审阅关键判断点而无需在底稿列表中搜索。

#### Acceptance Criteria

1. THE Quick_Entry_Panel SHALL 提供三个快速入口卡片：重要性水平(B15) / 持续经营(A15) / 特别风险(B50-4)
2. WHEN 用户点击某个快速入口卡片, THE Quick_Entry_Panel SHALL 直接跳转到对应底稿编辑器页面
3. THE Quick_Entry_Panel SHALL 在每个卡片上显示该底稿的当前状态（未开始/进行中/已完成/已复核）
4. IF 对应底稿在当前项目中不存在, THEN THE Quick_Entry_Panel SHALL 将该卡片标记为灰色不可点击并显示"未创建"提示

### Requirement 6: 裁剪汇总概览

**User Story:** As a 合伙人, I want to 看到程序裁剪的汇总情况, so that 我可以评估裁剪决策是否合理。

#### Acceptance Criteria

1. WHILE procedure-applicability-trimming 功能已实施, THE Trimming_Overview SHALL 显示裁剪汇总面板
2. WHILE procedure-applicability-trimming 功能未实施, THE Trimming_Overview SHALL 不渲染（条件隐藏）
3. THE Trimming_Overview SHALL 展示：总裁剪程序数 / 总程序数 / 裁剪率百分比 / 按循环分布
4. WHEN 某循环裁剪率超过 50%, THE Trimming_Overview SHALL 对该循环标记黄色警告

### Requirement 7: 项目时间线

**User Story:** As a 合伙人, I want to 看到项目关键里程碑的时间线, so that 我可以掌握项目整体节奏和当前阶段。

#### Acceptance Criteria

1. THE Project_Timeline SHALL 展示四个关键里程碑阶段：计划 → 执行 → 复核 → 报告
2. THE Project_Timeline SHALL 根据项目实际数据推断当前所处阶段并高亮标记
3. THE Project_Timeline SHALL 对已完成阶段显示完成时间，对当前阶段显示进入时间
4. WHEN 项目处于"执行"阶段, THE Project_Timeline SHALL 在执行阶段节点下方显示全循环完成率摘要

### Requirement 8: RBAC 与角色差异化展示

**User Story:** As a 系统管理员, I want to 所有角色都能查看仪表盘但合伙人/质控看到更多细节, so that 信息展示与角色职责匹配。

#### Acceptance Criteria

1. THE Dashboard_Page SHALL 对所有已认证角色（admin/partner/manager/assistant）开放只读访问
2. WHILE 当前用户角色为 partner 或 admin, THE Dashboard_Page SHALL 额外显示：复核意见详细列表 + VR 规则 details 展开 + 裁剪汇总
3. WHILE 当前用户角色为 assistant, THE Dashboard_Page SHALL 仅显示：全循环进度环形图 + 项目时间线 + 关键判断点入口（简化视图）
4. WHILE 当前用户角色为 manager, THE Dashboard_Page SHALL 显示除裁剪汇总外的所有模块
5. THE Dashboard_Page SHALL 通过前端角色判断控制模块显隐，后端聚合端点统一返回全量数据（不按角色裁剪响应体）

### Requirement 9: 后端聚合端点

**User Story:** As a 前端开发者, I want to 通过单个 API 获取仪表盘所需的全部聚合数据, so that 页面加载只需一次网络请求。

#### Acceptance Criteria

1. THE Dashboard_Aggregator SHALL 提供 GET /api/projects/{pid}/dashboard/summary 端点
2. THE Dashboard_Aggregator SHALL 在响应中包含：cycle_progress（11 循环完成率）+ vr_summary（blocking 汇总）+ open_reviews（未解决复核意见）+ timeline（里程碑状态）+ trimming_overview（裁剪汇总，可为 null）
3. THE Dashboard_Aggregator SHALL 聚合已有数据源（procedure_status + consistency_gate + review_records），不新增 PG 表
4. THE Dashboard_Aggregator SHALL 在 ≤ 2000ms 内返回响应（含所有子查询）
5. IF 某个子查询失败, THEN THE Dashboard_Aggregator SHALL 在响应中将该字段标记为 null 并附带 error 描述，不阻断整体响应
6. THE Dashboard_Aggregator SHALL 使用 `Depends(get_current_user)` 认证守卫，并校验用户对该 project_id 的访问权限

## Non-Functional Requirements

### 性能

- 仪表盘聚合端点响应时间 ≤ 2000ms（含 11 循环进度 + VR 检查 + 复核意见查询）
- 前端页面首次渲染（含骨架屏）≤ 500ms，数据填充 ≤ 3000ms
- 数据实时性：≤ 5s 延迟（手动刷新/轮询，非实时推送）

### 兼容性

- 不新增 PostgreSQL 表（纯聚合已有数据）
- 不影响现有 WorkpaperList / WorkpaperEditor 页面路由和功能
- 兼容已有 `useProcedureStatus` composable 的数据结构
- 兼容已有 `ConsistencyGate.run_all_checks` 返回格式

### 可观测性

- 后端日志记录每次仪表盘聚合请求的 project_id + user_id + 响应耗时
- 前端 console.warn 记录数据加载失败的具体模块

## Test Matrix

### 单元测试

| 文件 | 覆盖范围 |
|------|----------|
| `backend/tests/test_dashboard_aggregator.py` | 聚合端点 + 各子查询 + 错误降级 |
| `frontend/src/views/__tests__/ProjectDashboard.spec.ts` | 页面渲染 + 模块显隐 + RBAC |
| `frontend/src/composables/__tests__/useDashboardData.spec.ts` | 数据拉取 + 轮询 + 错误处理 |

### PBT (Property-Based Tests)

| ID | Property | 描述 |
|----|----------|------|
| PBT-P1 | progress_rate_bounds | 任意循环完成率 ∈ [0, 100]（数量守恒） |
| PBT-P2 | blocking_count_monotone | blocking 未通过数 ≤ 总 VR 规则数（上界约束） |
| PBT-P3 | review_sort_stability | 按优先级排序后相同层级内按时间倒序（排序稳定性） |

### 集成测试

- 聚合端点 → ConsistencyGate + review_records + procedure_status 联合查询
- 前端页面 → API 调用 → 数据渲染 → 点击跳转

### UAT

| # | 验收项 | P |
|---|--------|---|
| 1 | 合伙人登录后默认跳转到 /projects/:id/dashboard | P0 |
| 2 | 全循环进度环形图正确展示 11 个循环完成百分比 | P0 |
| 3 | Blocking VR 汇总卡片按循环分组展示未通过规则 | P0 |
| 4 | 未解决复核意见列表按优先级排序 + 点击跳转到底稿 | P0 |
| 5 | 关键判断点快速入口（B15/A15/B50-4）可点击跳转 | P0 |
| 6 | 项目时间线展示四阶段 + 当前阶段高亮 | P1 |
| 7 | 裁剪汇总概览条件渲染（trimming 未实施时不显示） | P1 |
| 8 | assistant 角色看到简化视图（无复核意见详情/VR details） | P1 |
| 9 | 聚合端点响应时间 ≤ 2000ms | P1 |
| 10 | 手动刷新按钮重新拉取数据 | P2 |
| 11 | 某子查询失败时其他模块正常展示（降级） | P2 |

**上线门槛：P0 全部 ✓ + P1 ≥ 80% ✓**

## Success Criteria

- 合伙人/质控可在单页面内一屏掌握：全循环进度 + blocking VR 状态 + 未解决复核意见
- 从仪表盘到任意底稿的跳转路径 ≤ 2 次点击
- 聚合端点不新增 PG 表，纯聚合已有数据
- 数据延迟 ≤ 5s（手动刷新即可获取最新状态）

## Terminology

| 术语 | 定义 |
|------|------|
| VR | Validation Rule，验证规则（consistency_gate 中的检查项） |
| Blocking | 阻断签字的严重级别，未通过则项目不可出具报告 |
| 循环 (Cycle) | 审计业务循环，D~N 共 11 个（D 销售/E 货币资金/F 采购存货/G 投资/H 固定资产/I 无形资产/J 薪酬/K 管理/L 筹资/M 权益/N 税费） |
| 复核意见 | review_records 表中 status=open 的记录 |
| 裁剪 (Trimming) | 将不适用的审计程序标记为 N/A |
| 里程碑 | 项目关键阶段节点：计划/执行/复核/报告 |
