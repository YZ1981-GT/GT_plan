# Implementation Plan: 合伙人仪表盘 (Partner Dashboard)

## Overview

基于 requirements.md 和 design.md，将合伙人仪表盘功能拆分为 2 个 Sprint：Sprint 1 后端聚合端点（service + router + 测试 + PBT），Sprint 2 前端页面（composable + 6 模块组件 + RBAC + 测试 + 回归）。后端使用 Python（FastAPI + hypothesis PBT），前端使用 TypeScript（Vue 3 + ECharts + Element Plus + vitest）。

预计工时：3 天（Sprint 1 约 1 天，Sprint 2 约 2 天）。

## Tasks

- [x] 1. Sprint 1 — 后端聚合端点
  - [x] 1.1 创建 DashboardAggregatorService 服务
    - 创建 `backend/app/services/dashboard_aggregator_service.py`
    - 实现 `DashboardAggregatorService` 类
    - `get_summary()`: 并发调用 4 个子查询（asyncio.gather），任一失败降级为 null + errors 记录
    - `_aggregate_cycle_progress()`: 遍历 D~N 11 循环，从 procedure_status 聚合 total/completed/trimmed，调用 `calc_progress_rate`
    - `_aggregate_vr_summary()`: 调用 `ConsistencyGate.run_all_checks`，按循环分组统计 blocking 未通过数
    - `_aggregate_open_reviews()`: 查询 review_records WHERE status='open'，按 LAYER_PRIORITY 排序，截取 summary 前 80 字符
    - `_aggregate_timeline()`: 从 project 表 + audit_trail 推断当前阶段（planning/execution/review/reporting）
    - `_aggregate_trimming()`: 从 parsed_data.trimming_metadata 聚合裁剪统计（trimming 未实施时返回 available=false）
    - 实现 `calc_progress_rate(total, completed, trimmed)` 纯函数：`clamp(completed / (total - trimmed) * 100, 0, 100)`
    - 实现 `sort_reviews(items)` 纯函数：按 LAYER_PRIORITY desc + created_at desc
    - _Requirements: 2.2, 3.1, 3.2, 4.1, 4.2, 7.2, 9.2, 9.3, 9.5_

  - [x] 1.2 创建 Pydantic Schema 定义
    - 创建 `backend/app/schemas/dashboard.py`（或追加到已有 schemas 目录）
    - 定义 `DashboardSummaryResponse` / `CycleProgressItem` / `VRSummaryData` / `CycleVRStat` / `FailedRuleItem` / `OpenReviewsData` / `ReviewItem` / `TimelineData` / `StageItem` / `TrimmingData` / `CycleTrimStat`
    - _Requirements: 9.2_

  - [x] 1.3 创建 dashboard_aggregator.py 路由
    - 创建 `backend/app/routers/dashboard_aggregator.py`
    - `GET /api/projects/{project_id}/dashboard/summary` — 调用 DashboardAggregatorService.get_summary
    - 使用 `Depends(get_current_user)` 认证守卫
    - 校验用户对 project_id 的访问权限（复用已有 project membership 校验逻辑）
    - 注册路由到 `router_registry.py`
    - 添加日志：记录 project_id + user_id + 响应耗时
    - _Requirements: 9.1, 9.4, 9.6_

  - [x] 1.4 编写后端单元测试
    - 创建 `backend/tests/test_dashboard_aggregator.py`
    - 测试 GET /summary happy path（mock 各子查询返回正常数据）
    - 测试认证守卫（未登录 → 401）
    - 测试权限校验（无项目访问权限 → 403）
    - 测试 project 不存在 → 404
    - 测试单个子查询失败 → 对应字段 null + errors 非空 + 其他字段正常
    - 测试全部子查询失败 → 所有字段 null + errors 全量
    - 测试响应结构完整性（所有字段存在）
    - _Requirements: 9.1, 9.2, 9.5, 9.6_

  - [x] 1.5 编写 DashboardAggregatorService 服务单元测试
    - 创建 `backend/tests/test_dashboard_aggregator_service.py`
    - 测试 `calc_progress_rate`：正常值 / total=0 / trimmed=total / completed > total-trimmed（clamp）
    - 测试 `sort_reviews`：多层级混合排序 / 同层级时间排序 / 空列表
    - 测试 `_aggregate_cycle_progress`：11 循环全覆盖 / 部分循环无数据
    - 测试 `_aggregate_vr_summary`：全通过 / 部分 blocking / ConsistencyGate 异常降级
    - 测试 `_aggregate_open_reviews`：有数据 / 无数据（空列表）/ summary 截断 80 字符
    - 测试 `_aggregate_timeline`：各阶段推断逻辑
    - _Requirements: 2.2, 3.1, 4.2, 7.2, 9.5_

  - [x] 1.6 编写后端 PBT 属性测试
    - 创建 `backend/tests/test_dashboard_pbt.py`
    - **Property 1: progress rate bounds** — 使用 hypothesis 生成 total ∈ [0, 500], completed ∈ [0, total], trimmed ∈ [0, total]，验证 `0.0 <= calc_progress_rate(total, completed, trimmed) <= 100.0`；当 total==trimmed 时验证 rate==100.0
    - **Property 2: blocking count monotone** — 生成 total_rules ∈ [1, 100] + per_cycle blocking counts（sum ≤ total），验证 `blocking_failed <= total_rules` 且 `sum(by_cycle.blocking_failed) == blocking_failed`
    - **Property 3: review sort stability** — 生成随机 ReviewItem 列表（layer ∈ L1~L5, created_at 随机 ISO），调用 sort_reviews，验证相邻元素满足排序约束
    - 每个 property ≥ 100 iterations
    - 标签：`Feature: partner-dashboard, Property {N}: {title}`
    - _Requirements: 2.2, 3.1, 3.2, 4.2_

- [x] 2. Checkpoint — 后端测试全绿
  - 运行 `python -m pytest backend/tests/test_dashboard_aggregator.py backend/tests/test_dashboard_aggregator_service.py backend/tests/test_dashboard_pbt.py -v`
  - 确认全部通过，如有问题修复后继续

- [x] 3. Sprint 2 — 前端页面 + 6 模块
  - [x] 3.1 创建 useDashboardData composable
    - 创建 `frontend/src/composables/useDashboardData.ts`
    - 实现 `useDashboardData(projectId)` 返回 data / loading / error / lastUpdated
    - `refresh()`: 调用 `GET /api/projects/{pid}/dashboard/summary`
    - 计算属性：cycleProgress / vrSummary / openReviews / timeline / trimmingOverview
    - 自动 onMounted 调用 refresh
    - 错误处理：网络错误 → error ref 赋值 + console.warn
    - _Requirements: 1.4, 9.1_

  - [x] 3.2 注册路由 + 创建 ProjectDashboard.vue 页面骨架
    - 在 Vue Router 中注册 `/projects/:id/dashboard` 路由
    - 创建 `frontend/src/views/ProjectDashboard.vue`
    - 页面 Header：项目名称 + 审计年度 + 最后更新时间 + 刷新按钮
    - 骨架屏：loading 时显示 `el-skeleton` 占位
    - 响应式网格布局：el-row + el-col（Row1 12/12, Row2 14/10, Row3 14/10）
    - RBAC 模块显隐逻辑：根据 currentUser.role 控制 6 模块 v-if
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 8.1, 8.2, 8.3, 8.4_

  - [x] 3.3 创建 CycleProgressRing.vue 组件
    - 创建 `frontend/src/components/dashboard/CycleProgressRing.vue`
    - 使用 ECharts gauge/pie 渲染 11 个循环环形图
    - 颜色映射：< 50% 红色 / 50%~99% 橙色 / 100% 绿色
    - 点击环形图 → router.push 到对应循环底稿列表
    - Props: `cycleProgress: CycleProgressItem[]`
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.4 创建 VRSummaryCard.vue 组件
    - 创建 `frontend/src/components/dashboard/VRSummaryCard.vue`
    - 顶部：blocking 未通过总数 / 总规则数（如 "3 / 33 blocking"）
    - 全通过时：绿色"全部通过"标识
    - 按循环分组列表：循环名 + blocking 数 + 红色标记
    - 点击规则 → 展开 details 描述（el-collapse）
    - 降级状态：vrSummary 为 null 时显示"数据获取失败" + 重试按钮
    - Props: `vrSummary: VRSummaryData | null`, `error: string | null`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 3.5 创建 ReviewOpinionList.vue 组件
    - 创建 `frontend/src/components/dashboard/ReviewOpinionList.vue`
    - 顶部统计：总未解决数 + 按层级分布（可用 mini 饼图或标签）
    - 列表：层级标签 + 意见摘要（80 字符）+ 创建时间 + 关联底稿编码
    - 点击 → router.push 到对应底稿 sheet + cell
    - 空状态：未解决数为 0 时显示"所有复核意见已解决"
    - Props: `openReviews: OpenReviewsData | null`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 3.6 创建 QuickEntryPanel.vue 组件
    - 创建 `frontend/src/components/dashboard/QuickEntryPanel.vue`
    - 三个卡片：重要性水平(B15) / 持续经营(A15) / 特别风险(B50-4)
    - 每个卡片显示底稿当前状态标签
    - 点击 → router.push 到对应底稿编辑器
    - 底稿不存在时：灰色不可点击 + "未创建"提示
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 3.7 创建 ProjectTimeline.vue 组件
    - 创建 `frontend/src/components/dashboard/ProjectTimeline.vue`
    - 四阶段水平时间线：计划 → 执行 → 复核 → 报告
    - 当前阶段高亮 + 已完成阶段显示完成时间
    - 执行阶段时：节点下方显示全循环完成率摘要
    - 使用 Element Plus `el-steps` 或自定义 timeline
    - Props: `timeline: TimelineData | null`
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 3.8 创建 TrimmingOverview.vue 组件
    - 创建 `frontend/src/components/dashboard/TrimmingOverview.vue`
    - 条件渲染：`v-if="trimmingOverview?.available"`
    - 展示：总裁剪数 / 总程序数 / 裁剪率 / 按循环分布
    - 裁剪率 > 50% 循环标记黄色警告
    - Props: `trimmingOverview: TrimmingData | null`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 3.9 合伙人/质控角色默认跳转逻辑
    - 在项目入口路由（如 `/projects/:id`）添加 beforeEnter guard
    - partner/admin 角色 → 默认 redirect 到 `/projects/:id/dashboard`
    - 其他角色 → 保持原有默认页面
    - _Requirements: 1.1_

- [x] 4. Sprint 2 — 前端测试
  - [x] 4.1 编写 useDashboardData composable 测试
    - 创建 `frontend/src/composables/__tests__/useDashboardData.spec.ts`
    - 测试 refresh 调用 API + 更新 data ref
    - 测试 loading 状态切换
    - 测试错误处理（网络失败 → error ref）
    - 测试 lastUpdated 更新
    - 测试计算属性正确解构响应数据
    - _Requirements: 1.4, 9.1_

  - [x] 4.2 编写 ProjectDashboard.vue 页面测试
    - 创建 `frontend/src/views/__tests__/ProjectDashboard.spec.ts`
    - 测试骨架屏渲染（loading=true）
    - 测试 RBAC 模块显隐：partner 看全量 / assistant 看简化 / manager 看除裁剪外
    - 测试刷新按钮点击 → 调用 refresh
    - 测试 Header 信息渲染（项目名 + 年度 + 更新时间）
    - _Requirements: 1.3, 1.4, 1.5, 8.1, 8.2, 8.3, 8.4_

  - [x] 4.3 编写 6 模块组件测试
    - 创建 `frontend/src/components/dashboard/__tests__/CycleProgressRing.spec.ts`
      - 测试 11 环渲染 + 颜色映射（<50% 红 / 50-99% 橙 / 100% 绿）+ 点击跳转
    - 创建 `frontend/src/components/dashboard/__tests__/VRSummaryCard.spec.ts`
      - 测试全通过绿色标识 / blocking 红色标记 / 展开 details / 降级提示
    - 创建 `frontend/src/components/dashboard/__tests__/ReviewOpinionList.spec.ts`
      - 测试排序正确性 / 点击跳转 / 空状态
    - _Requirements: 2.1~2.6, 3.1~3.6, 4.1~4.6_

- [x] 5. Checkpoint — 前端测试全绿
  - 运行 vitest 确认全部通过

- [ ] 6. 回归验证
  - [x] 6.1 验证现有路由不受影响
    - 确认 `/projects/:id/workpapers` 等现有路由正常工作
    - 确认 WorkpaperList / WorkpaperEditor 页面无回归
    - 运行现有前端测试套件确认零回归
    - _Requirements: 非功能需求-兼容性_

  - [x] 6.2 验证 ConsistencyGate 集成
    - 确认 `ConsistencyGate.run_all_checks` 调用参数正确
    - 确认 VR 规则结果按循环分组逻辑与现有 consistency_gate 返回格式兼容
    - 运行现有 `backend/tests/test_consistency_gate*.py` 确认零回归
    - _Requirements: 9.3, 非功能需求-兼容性_

- [x] 7. Final checkpoint — 全部测试通过 + 回归零失败

## Notes

- Sprint 1（后端）预计 1 天，Sprint 2（前端）预计 2 天，合计 3 天
- 后端 PBT 使用 hypothesis（≥ 100 iterations），标签格式 `Feature: partner-dashboard, Property {N}: {title}`
- 不新增 PG 表，不需要 Alembic 迁移
- ECharts 已在 package.json 中，零新增前端依赖
- 后端聚合端点复用已有 `ConsistencyGate` + `review_records` 查询 + `useProcedureStatus` 数据结构
- RBAC 前端控制：partner/admin 全量 / manager 除裁剪外 / assistant 简化视图
- trimming_overview 条件渲染：仅当 procedure-applicability-trimming spec 已实施时 available=true
