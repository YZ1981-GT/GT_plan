# Implementation Plan: Phase 6 — 数值精度 + 权限统一 + 安全加固

## Overview

基于 requirements.md v1.1 和 design.md v1.0，将 8 项功能拆为 4 个 Sprint 实施。Sprint 1 聚焦数值精度层（F1/F2/F3 可并行），Sprint 2 实施独立功能（F4/F5/F6），Sprint 3 实施依赖 F4 的功能（F7/F8），Sprint 4 集成测试 + UAT + 回归验证。

关键约束：F8 必须在 F4 之后实施（依赖项目级权限端点）；DB 迁移使用 V008（V007 已被 SC-1 占用）。

## Tasks

### Sprint 1: 数值精度层（2 天，F1/F2/F3 可并行）

- [ ] 1. F1 — 前端金额计算 Decimal.js 改造
  - [x] 1.1 安装 decimal.js + fast-check 并创建 useDecimalCalc composable
    - `npm install decimal.js`（生产依赖）
    - `npm install fast-check --save-dev`（PBT 测试依赖）
    - 创建 `frontend/src/composables/useDecimalCalc.ts`
    - 实现 add/sub/mul/div/sum 五个方法，默认 dp=2 + ROUND_HALF_EVEN
    - 处理非数值输入（返回 '0.00' + console.warn）和除以零（返回 '0.00'）
    - _Requirements: F1.1, F1.2, F1.4_

  - [x]* 1.2 Write property tests for useDecimalCalc (P1 + P2)
    - **Property 1: Decimal 加减 round-trip** — `add(a, b)` then `sub(result, b)` 精度损失 ≤ 1e-10
    - **Property 2: Decimal 乘除 round-trip** — `mul(a, b)` then `div(result, b)` 精度损失 ≤ 1e-10 (b≠0)
    - 使用 fast-check，numRuns: 30
    - 测试文件：`audit-platform/frontend/src/__tests__/useDecimalCalc.spec.ts`
    - **Validates: Requirements F1.4**

  - [x] 1.3a 改造高频文件 14 处金额算术运算为 useDecimalCalc
    - LedgerPenetration(8) + TrialBalance(3) + Adjustments(3)
    - 每个文件 import useDecimalCalc，替换 Number 直接运算为 composable 调用
    - 确保金额显示视觉零差异
    - _Requirements: F1.3, F1.6_

  - [ ] 1.3b 改造其余 16 处金额算术运算为 useDecimalCalc
    - ConsolidationIndex(1) + DCountDialog(1) + CapitalReserveSheet(1) + TAccountEditor(3) + InternalCashFlowSheet(1) + ConfirmationSummary(2) + InternalTradeSheet(2) + AuditFindingPanel(1) + EliminationSheet(4)
    - 每个文件 import useDecimalCalc，替换 Number 直接运算为 composable 调用
    - 确保金额显示视觉零差异
    - _Requirements: F1.3, F1.6_

  - [x] 1.4 创建 ESLint 本地规则 no-amount-arithmetic（warn 级别）
    - 创建 `eslint-local-rules/no-amount-arithmetic.js`
    - 变量名模式匹配：`*amount*`/`*balance*`/`*total*`/`*sum*`
    - 检测直接 `+`/`-`/`*`/`/` 运算符使用
    - 级别设为 `warn`（高误报风险，初期收集误报后再升级）
    - 支持 `// eslint-disable-next-line` 豁免
    - 配置到 `.eslintrc.js`：`'local-rules/no-amount-arithmetic': 'warn'`
    - _Requirements: F1.5, F1.6_

- [ ] 2. F2 — 单位换算时机规范化（ESLint 防护规则）
  - [x] 2.1 创建 ESLint 本地规则 no-amount-unit-in-script
    - 创建 `eslint-local-rules/no-amount-unit-in-script.js`
    - 禁止在 `<script>` 块中对金额变量做 `/ 10000` 或 `/ 1000` 换算
    - 仅匹配金额相关变量名模式（排除时间 ms→s 和百分比计算）
    - 级别设为 `warn`（与 F1 规则一致）
    - 配置到 `.eslintrc.js`：`'local-rules/no-amount-unit-in-script': 'warn'`
    - 当前 0 处违规，规则目的是防止新增违规
    - _Requirements: F2.1, F2.2, F2.3, F2.4, F2.5, F2.6_

- [ ] 3. F3 — el-table sortable 列 sort-method 基于原始数值
  - [x] 3.1 创建 numericSortMethod 工具函数
    - 创建 `frontend/src/utils/numericSort.ts`
    - 实现 `numericSortMethod(prop: string)` 返回比较函数
    - null/undefined/NaN 统一排到末尾
    - 内部 `toSortableNumber` 辅助函数处理类型转换
    - _Requirements: F3.2, F3.3_

  - [x]* 3.2 Write property tests for numericSortMethod (P3)
    - **Property 3: numericSortMethod 单调性** — a < b → sort(a,b) < 0；null 排末尾
    - 使用 fast-check，numRuns: 30
    - 测试文件：`audit-platform/frontend/src/__tests__/numericSortMethod.spec.ts`
    - **Validates: Requirements F3.2, F3.5**

  - [x] 3.3 为 LedgerPenetration 8 列 + WorkpaperTableEditor 动态列接入 sort-method
    - LedgerPenetration.vue 4+4 = 8 个金额 sortable 列添加 `:sort-method="numericSortMethod('propName')"`
    - WorkpaperTableEditor 动态列：金额/数值类型列自动绑定 numericSortMethod
    - 不影响非金额列的默认排序行为（ReportView 2 列已有 sort-method 不动）
    - _Requirements: F3.1, F3.4, F3.5, F3.6_

- [ ] 4. Checkpoint — Sprint 1 验证
  - 确保 vue-tsc 零新增错误
  - 确保 vitest 全绿（含 PBT）
  - 确保 ESLint 规则生效（warn 级别，不阻断构建）
  - 确保金额显示视觉零差异
  - Ensure all tests pass, ask the user if questions arise.

### Sprint 2: 独立功能（3 天，F4/F5/F6）

- [ ] 5. F4 — 项目级权限端点 + useProjectRole + 路由守卫改造
  - [x] 5.1 后端：创建项目级权限 API 端点
    - 创建 `backend/app/routers/project_permissions.py`
    - 实现 `GET /api/projects/{id}/my-permissions`：基于 ProjectAssignment.role 映射权限列表
    - 实现 `GET /api/projects/{id}/my-role`：返回项目角色 + 系统角色
    - 定义 `PROJECT_ROLE_PERMISSIONS` 映射表（6 种角色：manager/signing_partner/auditor/eqcr/qc/readonly）
    - admin 角色跳过项目级权限检查（返回所有权限）
    - 未分配用户返回 `{ project_role: null, system_role: "..." }`
    - 注册到 router_registry
    - _Requirements: F4.1, F4.2, F4.3, F4.7_

  - [x]* 5.2 Write property test for permission mapping (P4)
    - **Property 4: 项目权限映射正确性** — 任意角色的权限 = 项目角色权限集 ∪ 系统角色权限集；admin 始终全权限
    - 使用 hypothesis，max_examples=30
    - 测试文件：`backend/tests/test_project_permissions.py`
    - **Validates: Requirements F4.1, F4.6**

  - [x] 5.3 前端：创建 useProjectRole composable
    - 创建 `frontend/src/composables/useProjectRole.ts`
    - 从 `/api/projects/{id}/my-permissions` 获取权限列表
    - 缓存 5min TTL，项目切换时主动刷新
    - 暴露 `projectCan(permission)` 方法（结合系统角色+项目角色）
    - 暴露 `permissions`/`projectRole`/`systemRole`/`loading`/`refresh`
    - _Requirements: F4.4, F4.5, F4.6_

  - [x] 5.4 路由守卫改造：meta.roles → can(permission)（基础设施）
    - 在 router/index.ts beforeEach 中新增 permission guard 逻辑
    - 定义 `meta: { permission: string }` 类型扩展
    - 实现 `can(permission)` 调用 useProjectRole.projectCan 或 fallback 到 ROLE_PERMISSIONS
    - _Requirements: F4.5_

  - [x] 5.5 路由守卫改造：逐路由迁移 15 处 meta.roles → meta.permission
    - 改造 router/index.ts 中 15 处 `meta: { roles: [...] }` 为 `meta: { permission: '...' }`
    - 覆盖：ArchiveWizard×2 / QCDashboard / PartnerSignDecision / LinkagePanorama / SystemSettings / EqcrMetrics / QcRuleList / QcRuleEditor / QcInspectionWorkbench / ClientQualityTrend / QcCaseLibrary / QcAnnualReports / TemplateLibraryMgmt / CustomQuery
    - 确保每处迁移后功能不变（权限不足时仍显示 403 提示）
    - _Requirements: F4.5_

  - [x]* 5.6 Write unit tests for useProjectRole
    - 测试缓存 TTL 行为、项目切换刷新、admin 跳过检查
    - 测试文件：`audit-platform/frontend/src/__tests__/useProjectRole.spec.ts`
    - _Requirements: F4.4, F4.6, F4.7_

  > **Sprint 2 编号说明**：原 5.4 拆分为 5.4（路由守卫基础设施）+ 5.5（逐路由迁移 15 处）+ 5.6（useProjectRole 测试），编号连续无间断。

- [ ] 6. F5 — 待回复批注聚合面板（MyReviewsPanel）
  - [x] 6.1 后端：创建 my-reviews 聚合端点
    - 创建 `backend/app/routers/my_reviews.py`
    - 实现 `GET /api/projects/{project_id}/my-reviews?status=open`
    - JOIN working_paper.assigned_to = current_user.id 查询 open 状态 ReviewRecord
    - 排序：优先级降序（must_fix > suggest > info）+ 创建时间升序
    - ReviewRecord.priority 字段已存在（Phase 2 F5 添加，server_default='suggest'，值域 must_fix/suggest/info）
    - 返回：review_id / wp_code / wp_name / cell_reference / comment_text / commenter_name / priority / created_at
    - 返回统计摘要：must_fix / suggest / info / total
    - 注册到 router_registry
    - _Requirements: F5.1, F5.2, F5.3, F5.4, F5.8_

  - [x] 6.2 前端：创建 MyReviewsPanel 组件
    - 创建 `frontend/src/components/MyReviewsPanel.vue`
    - 展示待回复批注列表（按优先级+时间排序）
    - 显示统计摘要卡片：必须修改 N 条 / 建议修改 N 条 / 仅供参考 N 条
    - 点击批注 emit `navigate` 事件（payload: { wpId, cellRef }）跳转到对应底稿 cell
    - 集成到路由 `/projects/:id/my-reviews`
    - _Requirements: F5.5, F5.6, F5.7, F5.8_

  - [x]* 6.3 Write unit tests for MyReviewsPanel + my-reviews endpoint
    - 后端：测试排序逻辑 + JOIN 查询 + 空列表返回
    - 前端：测试组件渲染 + navigate emit + 统计摘要
    - 测试文件：`backend/tests/test_my_reviews_aggregation.py` + `audit-platform/frontend/src/__tests__/MyReviewsPanel.spec.ts`
    - _Requirements: F5.2, F5.3, F5.6_

- [ ] 7. F6 — 高危操作二次密码验证
  - [x] 7.1 后端：创建 verify-password 端点 + confirmation_token 机制
    - 创建 `backend/app/routers/password_confirm.py`
    - 实现 `POST /api/auth/verify-password`：验证密码 → 生成 UUID v4 token → Redis 存储（TTL=300s）
    - 密码验证失败：401 + 失败计数（Redis key `confirm_fail:{user_id}` TTL=1800s）
    - 5 次失败锁定 30 分钟（复用 LOGIN_MAX_ATTEMPTS/LOGIN_LOCK_MINUTES 配置）
    - 成功返回 `{ confirmation_token, expires_in: 300 }`
    - 注册到 router_registry
    - _Requirements: F6.1, F6.2, F6.3_

  - [x] 7.2 后端：创建 require_confirmation_token 依赖
    - 创建依赖函数 `require_confirmation_token`
    - 从 `X-Confirmation-Token` header 读取 token
    - Redis GETDEL 原子操作验证 + 消费 token（一次性使用）
    - Token 缺失/过期/已使用 → 403
    - 接入高危操作端点：sign / archive / delete_project / batch_delete
    - 成功/失败均写入 audit_log
    - _Requirements: F6.4, F6.5, F6.8_

  - [x]* 7.3 Write property test for confirmation_token one-time-use (P7)
    - **Property 7: confirmation_token 一次性使用** — 使用一次成功(200)，再次使用失败(403)；5min 后过期
    - 使用 hypothesis，max_examples=30
    - 测试文件：`backend/tests/test_password_verification.py`
    - **Validates: Requirements F6.2, F6.8**

  - [x] 7.4 前端：创建 PasswordConfirmDialog 组件
    - 创建 `frontend/src/components/PasswordConfirmDialog.vue`
    - Props: visible / title（默认"安全验证"）
    - Emits: confirmed(token) / cancelled / update:visible
    - 密码输入框 + 提交按钮 + 错误提示（剩余尝试次数 / 锁定状态）
    - 成功后 emit confirmed 携带 token，调用方自动附加到后续请求 X-Confirmation-Token header
    - _Requirements: F6.6, F6.7_

  - [x]* 7.5 Write unit tests for PasswordConfirmDialog + verify-password endpoint
    - 后端：正确密码返回 token / 错误密码 401 / 第 5 次锁定 423 / token 一次性消费
    - 前端：组件渲染 / emit confirmed / 错误状态显示
    - 测试文件：`backend/tests/test_password_verification.py` + `audit-platform/frontend/src/__tests__/PasswordConfirmDialog.spec.ts`
    - _Requirements: F6.1, F6.3, F6.6_

- [ ] 8. Checkpoint — Sprint 2 验证
  - 确保后端 pytest 全绿（含 F4/F5/F6 新增测试）
  - 确保前端 vitest 全绿
  - 确保 vue-tsc 零新增错误
  - 确保 F4 my-permissions 端点响应 ≤ 200ms
  - 确保 F5 my-reviews 端点响应 ≤ 500ms
  - Ensure all tests pass, ask the user if questions arise.

### Sprint 3: 依赖功能（3 天，F7 + F8，F8 depends on F4）

- [ ] 9. F7 — 项目经理多项目进度总览（ManagerDashboard）
  - [x] 9.1 后端：创建 manager projects-overview 端点
    - 扩展 `backend/app/routers/manager_dashboard.py`
    - 实现 `GET /api/dashboard/manager/projects-overview`
    - 查询 projects.manager_id = current_user.id 的所有项目
    - 计算每个项目：overall_progress / cycle_progress[] / sla_urgency_score / blocking_vr_count / unresolved_review_count
    - urgency_score 公式：0.4 * sla_factor + 0.3 * vr_factor + 0.3 * wp_factor
    - 按 sla_urgency_score 降序排列
    - 仅 manager/admin 可访问（RBAC）
    - _Requirements: F7.1, F7.2, F7.3, F7.4_

  - [x]* 9.2 Write property test for urgency_score monotonicity (P5)
    - **Property 5: urgency_score 单调性** — SLA 剩余时间越少 → score 越高（其他因子相等时）
    - 同理验证 blocking_vr_count 和 incomplete_wp_ratio 的单调性
    - 使用 hypothesis，max_examples=30
    - 测试文件：`backend/tests/test_manager_dashboard_v2.py`
    - **Validates: Requirements F7.3, F7.4**

  - [x] 9.3 前端：创建 ManagerDashboard.vue 视图
    - 创建 `frontend/src/views/ManagerDashboard.vue`
    - 项目列表（卡片/表格切换视图）
    - 循环维度环形图/进度条（每个循环 completed/total + 百分比）
    - 按 urgency_score 排序显示
    - 点击项目卡片跳转到 PartnerProjectDashboard
    - 导航栏"我的项目群"入口（仅 manager/admin 可见）
    - 注册路由
    - _Requirements: F7.5, F7.6, F7.7, F7.8_

  - [x]* 9.4 Write unit tests for ManagerDashboard
    - 后端：urgency_score 计算 / 空项目列表 / 非 manager 403
    - 前端：组件渲染 / 卡片点击跳转 / 排序验证
    - 测试文件：`backend/tests/test_manager_dashboard_v2.py` + `audit-platform/frontend/src/__tests__/ManagerDashboard.spec.ts`
    - _Requirements: F7.1, F7.3, F7.8_

- [ ] 10. F8 — 复核层级灵活化（2-4 级可配置）
  - [x] 10.1 DB 迁移：V008 新增 review_config + 扩展 WpReviewStatus 枚举
    - 创建 `V008__add_review_config.sql`
    - ALTER TABLE projects ADD COLUMN review_config JSONB DEFAULT NULL
    - ALTER TYPE wp_review_status ADD VALUE IF NOT EXISTS 'pending_level3'/'level3_in_progress'/'level3_passed'/'level3_rejected'/'pending_level4'/'level4_in_progress'/'level4_passed'/'level4_rejected'
    - 更新 Python WpReviewStatus 枚举类添加 level3/level4 状态
    - 更新 Project 模型添加 review_config 字段
    - _Requirements: F8.1, F8.8_

  - [x] 10.2 后端：创建 review-config API 端点
    - 创建 `backend/app/routers/review_config.py`
    - 实现 `GET /api/projects/{id}/review-config`：返回配置（null 时返回默认 2 级）
    - 实现 `PUT /api/projects/{id}/review-config`：更新配置
    - 权限校验：仅 manager/partner/admin 可修改
    - 前置检查：存在进行中复核（status 非 not_submitted）时返回 409 禁止修改
    - Pydantic 校验：levels ∈ [2,4]，level_roles 必须定义 L1..L{levels}
    - review_config=null 时默认行为 = 2 级（L1=manager, L2=partner）
    - 注册到 router_registry
    - _Requirements: F8.2, F8.3, F8.4, F8.10_

  - [x] 10.3 后端：实现配置驱动的复核状态机
    - 创建 `ReviewStateMachine` 类或扩展现有复核流转逻辑
    - 根据 project.review_config.levels 动态决定下一状态
    - 状态流转公式：not_submitted → pending_level1 → level1_passed → ... → levelN_passed
    - 最终层级 pass 时标记"复核完成"
    - 更新 `batch_review.py` 的 `REVIEWABLE_REVIEW_STATUSES` 常量：
      - 添加 `WpReviewStatus.pending_level3`, `WpReviewStatus.level3_in_progress`
      - 添加 `WpReviewStatus.pending_level4`, `WpReviewStatus.level4_in_progress`
      - 这些是允许执行复核通过操作的状态（与现有 level1/level2 同模式）
    - 更新 `wp_review.py` 复核状态流转逻辑支持动态层级
    - _Requirements: F8.5, F8.6, F8.7_

  - [x]* 10.4 Write property test for review state machine N-level chain (P6)
    - **Property 6: 复核状态机 N 级链完整性** — levels=N → submit 后恰好经过 N 次 pass 到达 completed
    - 验证 N ∈ {2, 3, 4} 三种配置
    - 使用 hypothesis，max_examples=30
    - 测试文件：`backend/tests/test_review_chain_config.py`
    - **Validates: Requirements F8.5, F8.6, F8.7**

  - [x] 10.5 前端：创建 ReviewChainConfig 组件
    - 创建 `frontend/src/components/ReviewChainConfig.vue`
    - 下拉选择层级数（2/3/4）
    - 各层级角色分配（从项目成员中选择）
    - 保存时调用 PUT /api/projects/{id}/review-config
    - 进行中复核时禁用编辑（显示提示）
    - 集成到项目设置页面
    - _Requirements: F8.9, F8.10_

  - [x]* 10.6 Write unit tests for ReviewChainConfig + review_config endpoint
    - 后端：2/3/4 级配置 CRUD / 进行中复核阻止修改 / 权限校验 / 默认 2 级
    - 前端：组件渲染 / 层级切换 / 保存 emit / 禁用状态
    - 测试文件：`backend/tests/test_review_chain_config.py` + `audit-platform/frontend/src/__tests__/ReviewChainConfig.spec.ts`
    - _Requirements: F8.3, F8.4, F8.9, F8.10_

- [ ] 11. Checkpoint — Sprint 3 验证
  - 确保后端 pytest 全绿（含 F7/F8 新增测试）
  - 确保前端 vitest 全绿
  - 确保 vue-tsc 零新增错误
  - 确保 F7 manager/dashboard 端点响应 ≤ 1s
  - 确保 F8 review_config=null 时行为与当前完全一致（默认 2 级）
  - 确保 F8 WpReviewStatus 扩展后现有 level1/level2 逻辑零回归
  - 回归验证白名单：batch_review.py / wp_review.py / ReviewWorkbench.vue
  - Ensure all tests pass, ask the user if questions arise.

### Sprint 4: 集成测试 + UAT + 回归验证（2 天）

- [ ] 12. 集成测试 + 回归验证
  - [ ] 12.1 F4+F8 集成验证：项目级权限 + 复核配置联动
    - 验证 useProjectRole.projectCan('review_config:edit') 正确控制 ReviewChainConfig 编辑权限
    - 验证路由守卫 can(permission) 与项目级角色联动
    - 验证 admin 跳过所有权限检查
    - _Requirements: F4.5, F4.6, F4.7, F8.4_

  - [ ] 12.2 F6 高危操作端到端验证
    - 验证 sign/archive/delete_project/batch_delete 四个端点均要求 X-Confirmation-Token
    - 验证 token 一次性消费 + 5min TTL
    - 验证密码错误 5 次锁定 + audit_log 记录
    - _Requirements: F6.4, F6.5, F6.8_

  - [ ] 12.3 全量回归测试
    - 运行全部后端 pytest（确保零新增失败）
    - 运行全部前端 vitest（确保零新增失败）
    - vue-tsc 编译零新增错误
    - 重点回归：batch_review.py REVIEWABLE_REVIEW_STATUSES / wp_review.py 状态流转 / ReviewWorkbench.vue 状态筛选
    - _Requirements: 非功能需求 — 兼容性_

- [ ] 13. UAT 验收
  - [ ] 13.1 程序化 UAT 验收脚本
    - 编写一次性 `_uat_phase6.py` 验收脚本
    - 验证 14 项 UAT 清单（P0 全 ✓ 为上线门槛）
    - 量化指标：Decimal 精度 / ESLint 规则生效 / sort-method 覆盖 / 端点响应时间 / token 安全性 / 层级流转
    - 脚本用完即删
    - _Requirements: 成功判据全部_

- [ ] 14. Final checkpoint — 确保所有测试通过
  - 全部后端 pytest 全绿
  - 全部前端 vitest 全绿
  - vue-tsc 零新增错误
  - P0 UAT 项全部 ✓
  - 关键回归零失败
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 总计：14 顶层 task / 31 子 task（含拆分后的 1.3a/1.3b 和 5.4/5.5/5.6）
- Tasks marked with `*` are optional and can be skipped for faster MVP
- F8 MUST come after F4（F8 复核配置 UI 需要 F4 项目级权限端点判断编辑权限）
- DB 迁移使用 V008__add_review_config.sql（V007 已被 SC-1 audit_log append-only 占用）
- F1 ESLint 规则为 warning 级别（高误报风险，初期收集误报后再升级 error）
- F2 当前 0 处违规，规则目的是防止新增违规（无需迁移现有代码）
- PBT 使用 max_examples=30（用户偏好，兼顾速度）
- 后端 PBT 使用 hypothesis / 前端 PBT 使用 fast-check
- Property tests validate universal correctness properties; unit tests validate specific examples and edge cases
- Checkpoints ensure incremental validation at each Sprint boundary
