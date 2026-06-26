# Implementation Plan: A21~A25 复核表角色权限绑定

## Overview

为五级复核表实现 RBAC 权限控制、逐级前置校验、签字锁定/解锁、A1 状态看板、未清意见计数器。后端 Python/FastAPI，前端 Vue 3 + Element Plus。零新表设计，全部复用 `checklist_responses` + `project_assignments`。

## Tasks

- [ ] 1. 后端核心：review_rbac_guard.py 权限校验服务
  - [x] 1.1 创建 `backend/app/services/review_rbac_guard.py` 模块
    - 定义 `REVIEW_ROLE_MAP` 常量（A21→["senior","auditor"], A22→["manager"], A23→["signing_partner"], A24→["qc"], A25→["eqcr"]）
    - 定义 `REVIEW_DEPENDENCY` 常量（A22→A21, A23→A22, A24→A23, A25→A24）
    - 定义 `ReviewGuardResult` dataclass（readonly, locked, signed_by, signed_at, gate_reason, unresolved_count, rbac_denied）
    - _Requirements: 1.4, 2.1_

  - [x] 1.2 实现 RBAC 校验逻辑
    - 实现 `check_rbac(db, user_id, project_id, wp_code) → bool`
    - 从 `staff_members.user_id` 解析 staff_id
    - 查询 `project_assignments` 匹配 project_id + role in REVIEW_ROLE_MAP[level]
    - user_id 无对应 staff 记录时返回 rbac_denied=True（安全降级）
    - wp_code 不在 REVIEW_ROLE_MAP 时跳过（非复核表不受管辖）
    - _Requirements: 1.1, 1.7_

  - [x] 1.3 实现 Sequential Gate 逐级校验
    - 实现 `check_sequential_gate(db, project_id, wp_code) → (blocked: bool, gate_reason: str|None)`
    - 从 wp_code 提取 level 和变体后缀（-1/-2）
    - 查询前置级别的 `-sign` 记录 conclusion 是否为 'pass'
    - A21 无前置依赖直接放行
    - 含变体时匹配对应变体（A22-1 要求 A21-1 已签字）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 1.4 实现 Sign-Lock 锁定检查
    - 实现 `check_sign_lock(db, project_id, wp_code) → (locked: bool, signed_by: str|None, signed_at: str|None)`
    - 查询 checklist_responses 中 item_id=`{wp_code}-sign` 且 conclusion='pass' 的记录
    - 从 remark JSON 提取 signer_id → 关联 staff_members 获取姓名
    - _Requirements: 3.1, 3.2_

  - [x] 1.5 实现 Unresolved Count 计算
    - 实现 `calc_unresolved_count(db, wp_id) → int`
    - 查询 checklist_responses 中 conclusion='N' 的记录
    - 排除 item_id 以 `-sign`、`-record`、`-unlock-log` 结尾的系统项
    - _Requirements: 5.3_

  - [x] 1.6 实现统一入口 `evaluate_guard(db, user_id, project_id, wp_code, wp_id) → ReviewGuardResult`
    - 按顺序执行: sign_lock → rbac → sequential_gate → unresolved_count
    - locked=True 时直接返回 readonly=True（无需再查 rbac/gate）
    - 组合各结果填充 ReviewGuardResult
    - _Requirements: 1.1, 1.2, 1.3, 2.2, 3.2, 5.3_

  - [x]* 1.7 Property 1: RBAC Guard 正确性属性测试
    - **Property 1: RBAC Guard correctness**
    - 随机生成 user_id + project_assignments (0~5 条, 随机 role) + 随机 wp_code (A21~A25)
    - 验证 rbac_denied=True 当且仅当 user 无匹配角色
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.5, 1.6**

  - [x]* 1.8 Property 2: Sequential Gate 正确性属性测试
    - **Property 2: Sequential Gate correctness**
    - 随机生成 sign state dict (每级 pass/reject/None) + 随机目标 wp_code + 随机变体后缀
    - 验证 gate blocked 当且仅当前置级别未 pass
    - 验证 A21 从不被 gate-blocked
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

  - [x]* 1.9 Property 4: Sign-Lock 不变式属性测试
    - **Property 4: Sign-Lock invariant**
    - 随机生成 checklist_responses 含/不含 -sign 记录
    - 验证 locked=True 当且仅当 -sign conclusion='pass' 存在
    - 验证 locked 时 signed_by 非空 + signed_at 为有效 ISO 时间
    - **Validates: Requirements 3.1, 3.2**

  - [x]* 1.10 Property 8: Unresolved Count 计算属性测试
    - **Property 8: Unresolved Count computation**
    - 随机生成 checklist_responses (混合 Y/N/NA + system items)
    - 验证 count == conclusion='N' 且非 system item 的数量
    - **Validates: Requirements 5.3, 5.5**

- [ ] 2. Checkpoint - Guard 核心逻辑验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. 后端改造：render-config 注入 Guard 结果
  - [x] 3.1 改造 `wp_render_config.py` review-checklist renderer
    - 在 review-checklist componentType 渲染时调用 `evaluate_guard`
    - 将 ReviewGuardResult 注入 html_data：readonly, locked, signed_by, signed_at, gate_reason, unresolved_count
    - _Requirements: 1.2, 1.3, 2.2, 3.2, 5.3_

  - [x] 3.2 改造 `a21_review.py` review-sign 端点
    - 签字前调用 `check_rbac`，无权返回 403 "无权签署此级别复核表"
    - 签字前调用 `calc_unresolved_count`，>0 返回 422 "尚有 {count} 项复核意见未清零，无法签字"
    - action='pass' 签字成功后无需额外处理（现有逻辑已写 -sign 记录）
    - _Requirements: 1.5, 5.2, 5.6_

  - [x] 3.3 改造 `checklist_responses.py` PUT 端点
    - 对 review-checklist wp_code（匹配 A2[1-5] 模式）增加前置校验
    - 调用 `check_rbac`，无权返回 403 "无权编辑此级别复核表"
    - 调用 `check_sign_lock`，已锁定返回 403 "复核表已锁定"
    - _Requirements: 1.6, 3.1_

  - [x]* 3.4 Property 9: Unresolved Count 阻止签字属性测试
    - **Property 9: Unresolved Count blocks signing**
    - 随机生成含 N 结论的 responses + 尝试 sign pass
    - 验证 count > 0 时拒绝签字，count == 0 时允许
    - **Validates: Requirements 5.2, 5.6**

- [ ] 4. 后端新增：review-unlock 端点
  - [x] 4.1 实现 `POST /api/workpapers/{wp_id}/review-unlock` 端点
    - 请求体: `{ project_id: UUID, wp_code: str, reason: str }`
    - 校验 reason 非空，否则 422 "解锁必须填写原因"
    - 校验 -sign 记录存在，否则 422 "该复核表未签字，无需解锁"
    - 校验当前用户 role == signing_partner，否则 403 "仅合伙人可解锁已签字复核表"
    - 删除 -sign 记录
    - 创建 -unlock-log 记录（conclusion='unlocked', remark JSON 含 unlocked_by/unlocked_at/reason/original_signer_id）
    - 返回 `{ success: true, unlocked_at: str }`
    - _Requirements: 3.4, 3.5, 3.6, 3.7_

  - [x]* 4.2 Property 5: Unlock 往返恢复属性测试
    - **Property 5: Unlock round-trip recovery**
    - 随机生成已锁定状态 + 执行 unlock
    - 验证: -sign 记录被删除, -unlock-log 记录存在, guard 返回 locked=False
    - **Validates: Requirements 3.4, 3.6**

  - [x]* 4.3 Property 6: Unlock 角色限制属性测试
    - **Property 6: Unlock role restriction**
    - 随机生成 5 种 role + 执行 unlock
    - 验证仅 signing_partner 成功，其他角色 403
    - **Validates: Requirements 3.7**

  - [x]* 4.4 Property 3: 解锁级联只读属性测试
    - **Property 3: Unlock cascade readonly**
    - 随机生成已签字的多级链 + 随机选一级解锁
    - 验证上游所有级别 Sequential_Gate 返回 readonly=True
    - **Validates: Requirements 2.6**

- [ ] 5. Checkpoint - 后端权限链路完整验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. 后端新增：review_dashboard_status auto_resolver
  - [x] 6.1 实现 `review_dashboard_status` resolver
    - 在 `backend/app/services/auto_data_resolvers/_completion.py` 新增 resolver
    - 查询项目下 A21~A25（含 -1/-2 变体）的 working_paper 记录
    - 对每个级别：查 project_assignments 获取 reviewer_name
    - 对每个级别：查 checklist_responses -sign 记录确定 sign_status
    - 对每个级别：统计已填写项 / 总适用项（排除 system items）作为 progress
    - sign_status 逻辑：有 pass → "pass"；有 reject → "reject"；有任意 response → "in_progress"；无 → "not_started"
    - 返回 `{ levels: [...] }` 结构
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x]* 6.2 Property 7: Dashboard Resolver 输出 Schema 属性测试
    - **Property 7: Dashboard Resolver output schema**
    - 随机生成项目（0~5 级有分配/有签字/有进度）
    - 验证输出包含所有必需字段 + sign_status 值域正确 + progress.completed ≤ progress.total
    - **Validates: Requirements 4.1, 4.2, 4.5**

- [ ] 7. 前端改造：GtReviewChecklist.vue 权限消费
  - [x] 7.1 消费 readonly/locked/gate_reason 字段
    - 从 render-config 返回的 html_data 中读取 readonly/locked/gate_reason
    - readonly=true 时禁用所有 input 控件（el-radio/el-input/el-select）
    - gate_reason 非空时顶部显示 el-alert type="warning" 展示阻止原因
    - _Requirements: 1.2, 2.2_

  - [x] 7.2 实现锁定状态 Banner
    - locked=true 时渲染 el-alert type="info" 显示 "已由 {signed_by} 于 {signed_at} 签字锁定"
    - signed_at 格式化为本地日期时间
    - _Requirements: 3.3_

  - [x] 7.3 实现未清意见 Badge
    - 在签字按钮区域显示 el-badge type="danger" 展示 unresolved_count
    - unresolved_count > 0 时签字按钮 disabled + tooltip "尚有未清复核意见"
    - unresolved_count == 0 时 badge 隐藏
    - _Requirements: 5.1, 5.4, 5.5_

  - [x] 7.4 实现解锁按钮（合伙人专属）
    - locked=true 时，若当前用户角色为 signing_partner 显示 "解锁" 按钮
    - 点击弹出 el-dialog 要求填写解锁原因
    - 调用 POST review-unlock 端点
    - 成功后刷新 render-config 恢复可编辑状态
    - 403 时 ElMessage.error 提示
    - _Requirements: 3.4, 3.7_

- [ ] 8. 前端新增：ReviewDashboardCard.vue
  - [x] 8.1 创建 ReviewDashboardCard 组件
    - 消费 `review_dashboard_status` resolver 数据
    - 渲染 5 个级别卡片：level_label + reviewer_name + sign_status + progress
    - pass 状态：绿色 el-icon (CircleCheck) + signer name + signed_at
    - reject 状态：橙色 el-icon (Warning) + rejection reason
    - not_started 状态：灰色 "未开始"
    - in_progress 状态：蓝色 el-progress 百分比
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 8.2 集成到 A1 Dashboard 页面
    - 在 A1 dashboard 中引入 ReviewDashboardCard
    - 绑定 auto_data_resolver 数据源
    - _Requirements: 4.6, 4.7_

- [ ] 9. Checkpoint - 前端功能验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. 集成联调：权限链路端到端验证
  - [x] 10.1 验证 RBAC 完整链路
    - 确认 render-config → guard → readonly 注入 → 前端禁用全链路正确
    - 确认无权用户 POST review-sign / PUT checklist-responses 返回 403
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6_

  - [x] 10.2 验证签字→锁定→解锁完整流程
    - 签字后 render-config 返回 locked=true + signed_by/signed_at
    - 解锁后 render-config 返回 locked=false + -unlock-log 记录存在
    - 解锁后依赖链上游重新 gate-blocked
    - _Requirements: 2.6, 3.1, 3.2, 3.4, 3.6_

  - [x] 10.3 验证 Sequential Gate + Dashboard 联动
    - A21 签字后 A22 变为可编辑
    - Dashboard 实时反映各级状态变化
    - _Requirements: 2.3, 4.7_

- [x] 11. Final checkpoint - 全功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 后端属性测试使用 hypothesis（`@settings(max_examples=100)`）
- 零新表设计：sign/lock/unlock-log 全部复用 checklist_responses 的 item_id 变体
- Guard 异常时安全降级为 readonly=True（永远不放行不确定状态）
- 前端 readonly 防误操作 + 后端 403 防绕过（双重校验）
- 解锁操作会级联影响上游复核表的 Sequential Gate 状态
