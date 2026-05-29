# Implementation Plan: Phase 7 — EQCR + QC + 工时体验闭环

## Overview

基于 requirements.md v1.0 和 design.md v1.0，将 13 项功能拆为 6 个 Sprint（Sprint 0~5）实施。Sprint 0 基线实测，Sprint 1~4 按功能分组递进实施，Sprint 5 PBT + 回归 + UAT。总预计 ~21 天。

关键约束：
- F9 depends on F7（推荐算法需要工时数据）
- F10 depends on F7（审批页面需要工时模块）
- F2 depends on Phase 6 F4（EQCR 问题单可见性需要项目级权限端点）
- F12 复用 Phase 6 F7 urgency_score 算法
- 迁移编号用占位（V009~V012 或 max+1）
- PBT 使用 max_examples=30 / numRuns: 30

## Tasks

### Sprint 0: 基线实测（1 天）

- [ ] 1. 填充 requirements §三.C 所有"待实测"基线变量
  - [x] 1.1 编写一次性基线实测脚本 `_sprint0_phase7_baseline.py`
    - 实测 eqcr_snapshots 表字段数（N_eqcr_snapshots_columns）
    - 实测 IssueTicket.source 枚举值数（N_issue_ticket_source_values）
    - 实测 SSEEventType 联合类型值数（N_sse_event_types）
    - 实测各循环 *_cycle_validation_rules.json blocking 条数（N_vr_rules_per_cycle）
    - 实测全仓 VR 规则总数（N_vr_total_rules）
    - 实测 knowledge_base router 分类数（N_knowledge_base_categories）
    - 实测 PartnerProjectDashboard 子组件数（N_partner_dashboard_modules）
    - 实测 ForceGraph.vue 现有过滤器 prop 数（N_force_graph_filter_props）
    - 实测 python-docx 是否已安装（python_docx_installed）
    - 实测是否已有 WorkHour 模型（WorkHour_model_exists）
    - 实测是否已有 budget_alert_worker（budget_alert_worker_exists）
    - 实测 ProjectAssignment.role 枚举值数（ProjectAssignment_role_values）
    - 将实测结果回填 requirements.md §三.C 表格
    - 脚本用完即删
    - _Requirements: §三.C 全部基线变量_

### Sprint 1: EQCR 体验三件套（4 天，F1 + F2 + F3）

- [ ] 2. F1 — EQCR 结构化判断模板
  - [x] 2.1 DB 迁移：V009 eqcr_snapshots 新增 judgments JSONB 列
    - 创建 `V009__eqcr_judgments_column.sql`（编号实施时 max+1）
    - ALTER TABLE eqcr_snapshots ADD COLUMN judgments JSONB DEFAULT NULL
    - CREATE INDEX idx_eqcr_snapshots_judgments_gin USING GIN (judgments)
    - 更新 EqcrSnapshot ORM 模型添加 judgments 字段
    - _Requirements: F1.3_

  - [x] 2.2 后端：创建 eqcr_judgment router + 服务逻辑
    - 创建 `backend/app/routers/eqcr_judgment.py`
    - 实现 POST `/api/projects/{id}/eqcr-judgment`：提交 5 维度结构化判断
    - 实现 GET `/api/projects/{id}/eqcr-judgment`：获取当前判断（只读）
    - Pydantic 校验：dimensions 必须 5 个，key 枚举 5 值，conclusion 枚举 3 值
    - 双写：snapshot_data.judgments + 独立 judgments 列
    - 校验全部 5 维度已填写结论才允许提交
    - 任一维度 conclusion='fail' → can_sign=False 阻断签字
    - 提交写入 audit_log
    - 注册到 router_registry
    - _Requirements: F1.1, F1.2, F1.3, F1.4, F1.5, F1.6_

  - [x] 2.3 前端：创建 EqcrJudgmentForm.vue 组件
    - 创建 `frontend/src/components/eqcr/EqcrJudgmentForm.vue`
    - 5 个判断维度 Tab/Accordion 表单（结论下拉+依据富文本+引用底稿多选+风险等级）
    - readonly 模式展示已提交判断
    - 提交前校验 5 维度全部填写
    - fail 维度红色高亮
    - emit submitted 事件
    - _Requirements: F1.1, F1.2, F1.4, F1.5, F1.6_

  - [x]* 2.4 Write unit tests for eqcr_judgment
    - 后端：5 维度全 pass → canSign=true / 1 个 fail → canSign=false / 维度数 ≠ 5 → 422 / 非 EQCR 角色 → 403
    - 前端：EqcrJudgmentForm 渲染 + 校验 + emit
    - 测试文件：`backend/tests/test_eqcr_judgment.py` + `frontend/src/__tests__/EqcrJudgmentForm.spec.ts`
    - _Requirements: F1.1, F1.4, F1.6_

- [ ] 3. F2 — EQCR 问题单独立模块
  - [x] 3.1 后端：创建 eqcr_issues router + 可见性过滤
    - 创建 `backend/app/routers/eqcr_issues.py`
    - 实现 GET `/api/projects/{id}/eqcr-issues`：列出 EQCR 问题单（source='eqcr'）
    - 实现 POST `/api/projects/{id}/eqcr-issues`：创建问题单（自动 source='eqcr'）
    - 实现 POST `/api/projects/{id}/eqcr-issues/{iid}/reply`：回复问题单
    - 可见性过滤：仅 EQCR 角色 + 项目团队（manager/signing_partner/auditor）可访问
    - 非授权角色返回 403
    - 排序：severity 降序 + created_at 升序
    - 返回统计摘要：open/in_fix/closed 计数
    - 回复触发 SSE 通知到 EQCR 合伙人
    - IssueTicket.source 枚举新增 'eqcr' 值（String(32) 无需迁移）
    - 注册到 router_registry
    - _Requirements: F2.1, F2.2, F2.3, F2.4, F2.5, F2.6, F2.7, F2.8_

  - [x] 3.2 前端：创建 EqcrIssueList.vue 组件
    - 创建 `frontend/src/components/eqcr/EqcrIssueList.vue`
    - 路由 `/projects/:id/eqcr-issues`
    - 问题单列表（severity 颜色标签 + 状态标签）
    - 统计摘要卡片：open N / in_fix N / closed N
    - 创建问题单弹窗（severity/category/title/description/关联底稿）
    - 对话线程回复 UI（IssueTicket 复用 parent_id 自引用实现线程，无需新增 thread_id 字段）
    - 点击底稿编号跳转到对应底稿
    - _Requirements: F2.1, F2.4, F2.5, F2.7_

  - [x]* 3.3 Write unit tests for eqcr_issues
    - 后端：可见性过滤 / 非授权 403 / severity 排序 / 统计摘要
    - 前端：EqcrIssueList 渲染 + 创建 emit + 回复 UI
    - 测试文件：`backend/tests/test_eqcr_issues.py` + `frontend/src/__tests__/EqcrIssueList.spec.ts`
    - _Requirements: F2.1, F2.4, F2.8_

- [ ] 4. F3 — EQCR 历史趋势图
  - [x] 4.1 后端：创建 eqcr_trends router
    - 创建 `backend/app/routers/eqcr_trends.py`
    - 实现 GET `/api/eqcr/metrics/trends`：返回近 5 年趋势数据
    - 年度通过率：基于 judgments 字段 5 维度全 pass = 项目通过
    - 平均复核天数：eqcr_snapshots.created_at 与项目提交时间差值
    - 常见问题 Top 5：基于 EQCR 问题单 category 聚合
    - 查询超时降级：返回已计算部分 + warnings
    - 注册到 router_registry
    - _Requirements: F3.1, F3.2, F3.3, F3.4, F3.6_

  - [x] 4.2 前端：创建 EqcrTrendChart.vue 组件
    - 创建 `frontend/src/components/eqcr/EqcrTrendChart.vue`
    - 在 EqcrMetrics 页面新增"年度趋势"Tab
    - ECharts 折线图展示通过率 + 柱状图展示复核天数
    - 常见问题 Top 5 表格
    - _Requirements: F3.5, F3.6_

  - [x]* 4.3 Write unit tests for eqcr_trends
    - 后端：空数据返回空列表 / 通过率计算 / Top 5 排序
    - 前端：EqcrTrendChart 渲染 + 数据绑定
    - 测试文件：`backend/tests/test_eqcr_trends.py` + `frontend/src/__tests__/EqcrTrendChart.spec.ts`
    - _Requirements: F3.2, F3.3_

- [ ] 5. Checkpoint — Sprint 1 验证
  - 确保后端 pytest 全绿（含 F1/F2/F3 新增测试）
  - 确保前端 vitest 全绿
  - 确保 vue-tsc 零新增错误
  - 确保 F1 判断提交 ≤ 500ms
  - 确保 F3 趋势查询 ≤ 1s
  - 回归验证：eqcr_snapshot_service.py / IssueTicket source 枚举
  - Ensure all tests pass, ask the user if questions arise.

### Sprint 2: QC 质控体验三件套（4 天，F4 + F5 + F6）

- [ ] 6. F4 — 复核意见模板库
  - [x] 6.1 DB 迁移：V012 新增 review_templates 表
    - 创建 `V012__review_templates.sql`（编号实施时 max+1）
    - CREATE TABLE review_templates（id/title/content/applicable_cycles JSONB/priority_tag/use_count/created_by/is_deleted/timestamps）
    - CREATE INDEX idx_review_templates_priority（partial: is_deleted=false）
    - CREATE INDEX idx_review_templates_cycles_gin USING GIN
    - 创建 ReviewTemplate ORM 模型
    - _Requirements: F4.1_

  - [x] 6.2 后端：创建 review_templates router + CRUD
    - 创建 `backend/app/routers/review_templates.py`
    - 实现 GET `/api/review-templates`：列出模板（支持 search + cycle 过滤）
    - 实现 POST `/api/review-templates`：创建模板
    - 实现 PUT `/api/review-templates/{id}`：更新模板
    - 实现 DELETE `/api/review-templates/{id}`：软删除
    - 实现 POST `/api/review-templates/{id}/use`：递增使用次数
    - 预置 10 条常用复核意见模板（seed data）
    - 注册到 router_registry
    - _Requirements: F4.2, F4.3, F4.6, F4.7_

  - [x] 6.3 前端：创建 ReviewTemplatePanel.vue 组件
    - 创建 `frontend/src/components/review/ReviewTemplatePanel.vue`
    - 模板选择面板（搜索+循环过滤+优先级标签）
    - 在 ReviewWorkbench 新增"插入模板"按钮
    - 选择模板 → emit insert(content) → 插入到复核意见输入框
    - 递增使用次数 API 调用
    - _Requirements: F4.4, F4.5, F4.6_

  - [x]* 6.4 Write unit tests for review_templates
    - 后端：CRUD 全流程 / 搜索过滤 / use_count 递增 / 软删除
    - 前端：ReviewTemplatePanel 渲染 + 搜索 + insert emit
    - 测试文件：`backend/tests/test_review_templates.py` + `frontend/src/__tests__/ReviewTemplatePanel.spec.ts`
    - _Requirements: F4.2, F4.5_

- [ ] 7. F5 — QC 报告 Word 导出
  - [x] 7.1 后端：创建 qc_report_export router
    - 创建 `backend/app/routers/qc_report_export.py`
    - 实现 GET `/api/projects/{id}/qc-report/export`：返回 .docx 文件流
    - 三线表格式（仅顶线+表头底线+底线，无竖线）
    - 字体：仿宋_GB2312（中文）+ Arial Narrow（数字）
    - 三章节：风险汇总表（循环×风险等级 VR 触发统计）+ 意见清单表（source='qc_inspection' IssueTicket）+ 整改状态表
    - 无 QC 记录时返回空报告模板（含表头无数据行）
    - 导出操作写入 audit_log
    - 权限：仅 qc/admin 可访问
    - 复用 Phase 3 python-docx 基础设施
    - 注册到 router_registry
    - _Requirements: F5.1, F5.2, F5.3, F5.4, F5.5, F5.6, F5.7_

  - [x]* 7.2 Write unit tests for qc_report_export
    - 三线表生成验证 / 空数据返回空模板 / 文件流 Content-Type 正确 / 非 qc 角色 403
    - 测试文件：`backend/tests/test_qc_word_export.py`
    - _Requirements: F5.2, F5.6, F5.7_

- [ ] 8. F6 — VR 规则覆盖度标准 + 仪表盘
  - [x] 8.1 后端：创建 vr_coverage router
    - 创建 `backend/app/routers/vr_coverage.py`
    - 实现 GET `/api/qc/vr-coverage`：返回各循环 VR 规则覆盖度统计
    - 运行时扫描各循环 *_cycle_validation_rules.json 文件
    - 统计每循环 blocking/warning/info 条数
    - 达标标准：blocking ≥ 3 AND warning ≥ 2
    - 计算缺口数：gap_blocking = max(0, 3 - blocking_count)
    - 返回汇总：total_rules / compliant_cycles / non_compliant_cycles
    - 权限：仅 qc/admin 可访问
    - 注册到 router_registry
    - _Requirements: F6.1, F6.2, F6.3, F6.6_

  - [x] 8.2 前端：创建 VRCoverageTab.vue 组件
    - 创建 `frontend/src/components/qc/VRCoverageTab.vue`
    - 在 QCDashboard 新增"VR 覆盖度"Tab
    - 表格展示各循环达标情况 + 进度条
    - 未达标循环红色高亮
    - 点击循环行 emit cycle-click 事件
    - _Requirements: F6.4, F6.5_

  - [x]* 8.3 Write unit tests for vr_coverage
    - 后端：达标判断逻辑 / 缺口计算 / 规则文件读取失败降级 503
    - 前端：VRCoverageTab 渲染 + 红色高亮 + emit
    - 测试文件：`backend/tests/test_vr_coverage.py` + `frontend/src/__tests__/VRCoverageTab.spec.ts`
    - _Requirements: F6.1, F6.4, F6.5_

- [ ] 9. Checkpoint — Sprint 2 验证
  - 确保后端 pytest 全绿（含 F4/F5/F6 新增测试）
  - 确保前端 vitest 全绿
  - 确保 vue-tsc 零新增错误
  - 确保 F5 Word 导出 ≤ 3s（100 条意见规模）
  - 确保 F4 预置模板 ≥ 10 条
  - 回归验证：knowledge_base router / ReviewWorkbench
  - Ensure all tests pass, ask the user if questions arise.

### Sprint 3: 工时管理增强（6 天，F7 独立 3 天 + F8/F9/F10 合并 3 天，F9/F10 depend F7）

- [ ] 10. F7 — 工时填报粒度细化
  - [x] 10.1 DB 迁移：V010 新增 work_hour_entries 表
    - 创建 `V010__work_hour_entries.sql`（编号实施时 max+1）
    - CREATE TABLE work_hour_entries（id/user_id/project_id/date/hours DECIMAL(5,2)/cycle/wp_code/procedure/description/status/submitted_at/approved_by/approved_at/rejected_reason/timestamps）
    - CHECK (hours > 0 AND hours <= 24)
    - CREATE INDEX idx_whe_user_date / idx_whe_project_status / idx_whe_project_cycle
    - 创建 WorkHourEntry ORM 模型 + WorkHourEntryStatus 枚举
    - _Requirements: F7.1, F7.2_

  - [x] 10.2 后端：创建 workhour_entries router + CRUD
    - 创建 `backend/app/routers/workhour_entries.py`
    - 实现 POST `/api/projects/{id}/workhours`：创建工时条目（校验日合计 ≤ 24h）
    - 实现 GET `/api/projects/{id}/workhours`：列出工时条目（支持 start_date/end_date 过滤）
    - 实现 PUT `/api/projects/{id}/workhours/{eid}`：更新（仅 draft 状态可改）
    - 实现 DELETE `/api/projects/{id}/workhours/{eid}`：删除（仅 draft 状态可删）
    - 实现 POST `/api/projects/{id}/workhours/batch-submit`：批量提交（单事务 draft→submitted）
    - 实现 GET `/api/projects/{id}/workhours/summary`：按日/周/月汇总
    - 选择底稿级别时自动推断所属循环（基于 wp_code 前缀）
    - 仅本人可操作（admin 除外）
    - 工时状态变更写入 audit_log
    - 注册到 router_registry
    - _Requirements: F7.3, F7.4, F7.5, F7.6, F7.7_

  - [x] 10.3 前端：创建 WorkHoursPage.vue 视图
    - 创建 `frontend/src/views/WorkHoursPage.vue`
    - 日历视图（按日显示已填报工时）
    - 填报表单（循环下拉+底稿选择+程序输入+小时数+描述）
    - 汇总统计卡片（本日/本周/本月合计）
    - 批量提交按钮（选中 draft 条目一键提交）
    - 注册路由 `/projects/:id/workhours`
    - _Requirements: F7.5_

  - [x]* 10.4 Write unit tests for workhour_entries
    - 后端：创建+日合计校验 / 批量提交事务 / 状态流转 / 非本人 403
    - 前端：WorkHoursPage 渲染 + 表单提交 + 汇总显示
    - 测试文件：`backend/tests/test_workhour_crud.py` + `frontend/src/__tests__/WorkHoursPage.spec.ts`
    - _Requirements: F7.3, F7.7_

- [ ] 11. F8 — 工时预算 vs 实际可视化
  - [x] 11.1 DB 迁移：V011 projects 新增 budget_config JSONB 列
    - 创建 `V011__project_budget_config.sql`（编号实施时 max+1）
    - ALTER TABLE projects ADD COLUMN budget_config JSONB DEFAULT NULL
    - 更新 Project ORM 模型添加 budget_config 字段
    - _Requirements: F8.7_

  - [x] 11.2 后端：创建 workhour_budget router
    - 创建 `backend/app/routers/workhour_budget.py`
    - 实现 GET `/api/projects/{id}/workhours/budget-vs-actual`
    - 按循环聚合：cycle_name / budget_hours / actual_hours / variance_pct / is_over_budget(>20%)
    - 按人员聚合：user_name / budget_hours / actual_hours / variance_pct / is_over_budget
    - 无 budget_config 时返回空列表 + warning
    - 权限：仅 manager+ 可访问
    - 注册到 router_registry
    - _Requirements: F8.1, F8.2, F8.3, F8.4, F8.7_

  - [x] 11.3 前端：创建 BudgetCompareChart.vue 组件
    - 创建 `frontend/src/components/workhour/BudgetCompareChart.vue`
    - 在 WorkHoursPage 新增"预算对比"Tab
    - ECharts 分组柱状图（预算 vs 实际，按循环/按人员切换）
    - 超预算 120% 红色标注
    - _Requirements: F8.5, F8.6_

  - [x]* 11.4 Write unit tests for workhour_budget
    - 后端：方差计算 / 超预算标记 / 无 budget_config 降级
    - 前端：BudgetCompareChart 渲染 + 红色标注
    - 测试文件：`backend/tests/test_workhour_budget_compare.py` + `frontend/src/__tests__/BudgetCompareChart.spec.ts`
    - _Requirements: F8.3, F8.6_

- [ ] 12. F9 — 复核分派智能推荐（depends F7）
  - [x] 12.1 后端：创建 review_recommend router + 推荐算法
    - 创建 `backend/app/routers/review_recommend.py`
    - 实现 GET `/api/projects/{id}/review-recommend?cycle={cycle}&wp_code={wp_code}`
    - 三因子加权评分：历史复核记录 40% + 工时余量 30% + 循环专长 30%
    - history_factor = min(review_count_in_cycle / 10, 1.0)
    - capacity_factor = max(0, (40 - current_week_hours) / 40)
    - expertise_factor = len(matched_cycles) / len(candidate_all_cycles)
    - 返回 Top 3 推荐人选 + 评分明细
    - 团队人数 < 3 时返回全部可用人员
    - 算法超时降级：返回按名字排序 + degraded=true
    - 权限：仅 manager+ 可访问
    - 注册到 router_registry
    - _Requirements: F9.1, F9.2, F9.3, F9.4, F9.5, F9.6, F9.7, F9.8_

  - [x] 12.2 前端：创建 ReviewRecommendCard.vue 组件
    - 创建 `frontend/src/components/review/ReviewRecommendCard.vue`
    - 在复核分派弹窗中显示"推荐复核人"卡片
    - 展示 Top 3 候选人（评分+三维度明细）
    - 一键选择按钮 emit select(userId)
    - _Requirements: F9.7_

  - [x]* 12.3 Write unit tests for review_recommend
    - 后端：Top 3 返回 / 小团队全返回 / 三维度评分计算 / 超时降级
    - 前端：ReviewRecommendCard 渲染 + select emit
    - 测试文件：`backend/tests/test_review_recommend.py` + `frontend/src/__tests__/ReviewRecommendCard.spec.ts`
    - _Requirements: F9.2, F9.6, F9.8_

- [ ] 13. F10 — 工时审批与底稿进度关联（depends F7）
  - [x] 13.1 后端：创建 workhour_approval router
    - 创建 `backend/app/routers/workhour_approval.py`
    - 实现 GET `/api/projects/{id}/workhours/approval`：待审批列表（含底稿进度列）
    - 实现 POST `/api/projects/{id}/workhours/approval/approve`：批量审批
    - 实现 POST `/api/projects/{id}/workhours/approval/reject`：批量退回
    - 底稿进度计算：level2_passed+ = 100% / level1_passed = 50% / 其余 = 0%
    - 按 assigned_to 聚合加权平均
    - 警告条件：进度 < 30% 且工时 > 预算 80% → 橙色警告
    - 进度数据与工时数据同一 API 响应（避免 N+1）
    - 权限：仅 manager/partner/admin 可操作
    - 注册到 router_registry
    - _Requirements: F10.1, F10.2, F10.3, F10.4, F10.6_

  - [x] 13.2 前端：创建 WorkHourApprovalTable.vue 组件
    - 创建 `frontend/src/components/workhour/WorkHourApprovalTable.vue`
    - 工时审批表格（含"关联底稿进度"列 — 进度条形式）
    - 橙色警告行标注（进度低+工时高）
    - 批量审批/退回按钮
    - 集成到 WorkHoursPage 或独立路由
    - _Requirements: F10.1, F10.3, F10.5_

  - [x]* 13.3 Write unit tests for workhour_approval
    - 后端：进度百分比计算 / 警告条件判断 / 批量审批状态流转 / 非 manager 403
    - 前端：WorkHourApprovalTable 渲染 + 进度条 + 警告标注
    - 测试文件：`backend/tests/test_workhour_approval.py` + `frontend/src/__tests__/WorkHourApprovalTable.spec.ts`
    - _Requirements: F10.2, F10.3, F10.5_

- [ ] 14. Checkpoint — Sprint 3 验证
  - 确保后端 pytest 全绿（含 F7/F8/F9/F10 新增测试）
  - 确保前端 vitest 全绿
  - 确保 vue-tsc 零新增错误
  - 确保 F7 工时 CRUD ≤ 200ms
  - 确保 F8 预算对比查询 ≤ 500ms
  - 确保 F9 推荐算法 ≤ 500ms（20 人团队规模）
  - 确保 F9 depends F7 联动正确（推荐算法读取 work_hour_entries 数据）
  - 确保 F10 depends F7 联动正确（审批列表读取 work_hour_entries 数据）
  - Ensure all tests pass, ask the user if questions arise.

### Sprint 4: 复核通知 + 合伙人视角（3 天，F11 + F12 + F13）

- [ ] 15. F11 — 复核进度实时通知（SSE 推送）
  - [x] 15.1 后端：扩展 EventType 枚举 + 创建 review_notification_service
    - EventType 枚举新增 2 值：REVIEW_ACCEPTED / REVIEW_COMPLETED
    - 创建 `backend/app/services/review_notification_service.py`
    - 实现 notify_review_accepted / notify_review_completed
    - Redis 幂等 key：`sse:review_status:{review_id}:{status}` TTL=3600s
    - SSE payload：review_id / wp_code / reviewer_name / status / timestamp
    - 断连补发：基于 last_event_id 机制
    - 集成到复核流程触发点（打开底稿/提交结论）
    - _Requirements: F11.1, F11.2, F11.3, F11.5, F11.8_

  - [x] 15.2 前端：SSEEventType 同步 + NotificationCard + ReviewWorkbench 状态更新
    - 前端 SSEEventType 联合类型新增 2 个值（review.accepted / review.completed）
    - eventBus.ts 注册新事件处理
    - NotificationCenter 显示复核进度通知卡片（底稿编号+复核人+状态）
    - ReviewWorkbench "我提交的"列表实时更新状态标签（灰→蓝→绿/红）
    - _Requirements: F11.6, F11.7_

  - [x]* 15.3 Write unit tests for review_notification_service
    - 后端：SSE 事件发送 / 幂等去重 / payload 结构 / Redis 不可用降级
    - 前端：NotificationCard 渲染 + 状态标签颜色切换
    - 测试文件：`backend/tests/test_review_notification_sse.py` + `frontend/src/__tests__/ReviewNotificationCard.spec.ts`
    - _Requirements: F11.1, F11.5, F11.8_

- [ ] 16. F12 — 多项目紧急度评分排序
  - [x] 16.1 后端：创建 partner_urgency router
    - 创建 `backend/app/routers/partner_urgency.py`
    - 实现 GET `/api/partner/projects/urgency`
    - 复用 Phase 6 F7 urgency_score 三因子加权公式：
      - sla_factor = 1 - (days_remaining / max_days)
      - vr_factor = min(blocking_vr_count / 10, 1.0)
      - wp_factor = 1 - (completed_wp / total_wp)
      - urgency_score = round((0.4 * sla_factor + 0.3 * vr_factor + 0.3 * wp_factor) * 100)
    - 标签分类：≥80 红色"urgent" / ≥60 橙色"attention" / ≥40 黄色"normal" / <40 绿色"safe"
    - 按 urgency_score 降序排列
    - 子查询超时降级：对应项目 score=0 + warnings
    - 权限：仅 partner/admin 可访问
    - 注册到 router_registry
    - _Requirements: F12.1, F12.2, F12.3, F12.4, F12.6, F12.7_

  - [x] 16.2 前端：创建 UrgencyRankCard.vue 组件
    - 创建 `frontend/src/components/partner/UrgencyRankCard.vue`
    - 在 PartnerProjectDashboard 顶部新增"项目紧急度排行"卡片
    - 项目列表（名称+客户+评分+颜色标签+关键指标摘要）
    - 点击项目 emit project-click 跳转
    - _Requirements: F12.4, F12.5_

  - [x]* 16.3 Write unit tests for partner_urgency
    - 后端：评分计算 / 标签分类 / 降序排列 / 非 partner 403 / 超时降级
    - 前端：UrgencyRankCard 渲染 + 颜色标签 + emit
    - 测试文件：`backend/tests/test_partner_urgency.py` + `frontend/src/__tests__/UrgencyRankCard.spec.ts`
    - _Requirements: F12.2, F12.6, F12.7_

- [ ] 17. F13 — 联动全景图"仅显示 stale"过滤器
  - [x] 17.1 前端：创建 useStaleFilter composable + ForceGraph staleOnly prop
    - 创建 `frontend/src/composables/useStaleFilter.ts`
    - 实现 staleOnly ref + filteredNodes/filteredLinks computed
    - staleOnly=true 时：仅显示 is_stale=true 节点 + 一跳邻居 + 相关边
    - ForceGraph.vue 新增 staleOnly prop（默认 false）
    - 平滑过渡：非 stale 节点 fade out（opacity 动画），stale 节点保持位置
    - 不重新计算力模拟布局
    - _Requirements: F13.1, F13.2, F13.4, F13.5_

  - [x] 17.2 前端：LinkagePanoramaView 工具栏 + URL 持久化
    - LinkagePanoramaView 工具栏新增"仅显示 stale"el-switch
    - 无 stale 节点时显示空状态提示"当前无 stale 底稿 ✓"
    - URL query 参数持久化：`?stale_only=1`，刷新后保持
    - 确保不影响 ForceGraph 现有交互（zoom/drag/hover）
    - _Requirements: F13.3, F13.6, F13.7_

  - [x]* 17.3 Write unit tests for stale filter
    - 前端：stale 子图提取 / 一跳邻居包含 / 空 stale 空状态 / 幂等性
    - 测试文件：`frontend/src/__tests__/ForceGraphStaleFilter.spec.ts`
    - _Requirements: F13.2, F13.5, F13.6_

- [ ] 18. Checkpoint — Sprint 4 验证
  - 确保后端 pytest 全绿（含 F11/F12 新增测试）
  - 确保前端 vitest 全绿
  - 确保 vue-tsc 零新增错误（含 SSEEventType 扩展后）
  - 确保 F11 SSE 事件延迟 ≤ 2s
  - 确保 F12 紧急度评分查询 ≤ 1s（10 项目规模）
  - 确保 F13 stale 过滤渲染 ≤ 500ms（128 节点规模）
  - 确保 F13 不影响 ForceGraph 现有交互
  - 回归验证：EventType 枚举 / eventBus.ts / ForceGraph.vue / PartnerProjectDashboard.vue
  - Ensure all tests pass, ask the user if questions arise.

### Sprint 5: PBT + 回归 + UAT（3 天）

- [ ] 19. Property-Based Tests（7 个正确性属性）
  - [x]* 19.1 Write PBT P1: 工时日合计不变量
    - **Property 1: 工时日合计不变量**
    - 生成随机 (user, date, hours[]) 组合，验证 sum ≤ 24.0
    - 任何成功的 create/update 后不变量成立
    - hypothesis max_examples=30
    - 测试文件：`backend/tests/test_phase7_pbt.py`
    - **Validates: Requirements F7.7**

  - [x]* 19.2 Write PBT P2: 工时粒度汇总一致性
    - **Property 2: 工时粒度汇总一致性**
    - 生成随机多级 entries，验证 sum(cycle=C) == sum(cycle=C, wp_code IN wps_of_C) + sum(cycle=C, wp_code IS NULL)
    - hypothesis max_examples=30
    - 测试文件：`backend/tests/test_phase7_pbt.py`
    - **Validates: Requirements F7.4**

  - [x]* 19.3 Write PBT P3: 推荐评分单调性（工时余量）
    - **Property 3: 推荐评分单调性（工时余量）**
    - 生成两组 capacity 不同的候选人（其他因子固定），验证余量大 → score 高
    - hypothesis max_examples=30
    - 测试文件：`backend/tests/test_phase7_pbt.py`
    - **Validates: Requirements F9.2, F9.4**

  - [x]* 19.4 Write PBT P4: 推荐评分单调性（历史复核）
    - **Property 4: 推荐评分单调性（历史复核）**
    - 生成两组 history 不同的候选人（其他因子固定），验证历史多 → score 高
    - hypothesis max_examples=30
    - 测试文件：`backend/tests/test_phase7_pbt.py`
    - **Validates: Requirements F9.2, F9.3**

  - [x]* 19.5 Write PBT P5: 紧急度评分单调性
    - **Property 5: 紧急度评分单调性**
    - 生成两组 SLA 不同的项目（其他因子固定），验证 SLA 少 → score 高
    - hypothesis max_examples=30
    - 测试文件：`backend/tests/test_phase7_pbt.py`
    - **Validates: Requirements F12.2**

  - [x]* 19.6 Write PBT P6: 紧急度评分范围不变量
    - **Property 6: 紧急度评分范围不变量**
    - 生成随机三因子（SLA ≥ 0, VR ≥ 0, wp_ratio ∈ [0,1]），验证 0 ≤ score ≤ 100
    - hypothesis max_examples=30
    - 测试文件：`backend/tests/test_phase7_pbt.py`
    - **Validates: Requirements F12.2, F12.6, F12.7**

  - [x]* 19.7 Write PBT P7: stale 过滤幂等性
    - **Property 7: stale 过滤幂等性**
    - 生成随机图（nodes + links），验证 filter(filter(g)) == filter(g)
    - fast-check numRuns: 30
    - 测试文件：`frontend/src/__tests__/ForceGraphStaleFilter.spec.ts`
    - **Validates: Requirements F13.2**

- [ ] 20. 全量回归测试
  - [ ] 20.1 后端全量 pytest 回归
    - 运行全部后端 pytest（确保零新增失败）
    - 重点回归白名单：eqcr_snapshot_service.py / IssueTicket source / EventType 枚举 / eventBus.ts
    - _Requirements: 非功能需求 — 兼容性_

  - [ ] 20.2 前端全量 vitest + vue-tsc 回归
    - 运行全部前端 vitest（确保零新增失败）
    - vue-tsc 编译零新增错误
    - 重点回归：ForceGraph.vue / PartnerProjectDashboard.vue / LinkagePanoramaView.vue / ReviewWorkbench.vue
    - _Requirements: 非功能需求 — 兼容性_

- [ ] 21. UAT 验收
  - [ ] 21.1 程序化 UAT 验收
    - 编写一次性 `_uat_phase7.py` 验收脚本
    - 验证 14 项 UAT 清单（P0 全 ✓ 为上线门槛）
    - 量化指标：EQCR 5 维度 / 问题单 403 / 趋势图 / 模板 ≥ 10 / Word 三章 / VR 覆盖度 / 工时三级 / 预算对比 / 推荐 Top 3 / 进度列 / SSE 3 事件 / 紧急度排序 / stale 过滤
    - 脚本用完即删
    - _Requirements: 成功判据全部_

- [ ] 22. Final checkpoint — 确保所有测试通过
  - 全部后端 pytest 全绿（含 PBT）
  - 全部前端 vitest 全绿（含 fast-check PBT）
  - vue-tsc 零新增错误
  - P0 UAT 项全部 ✓
  - 关键回归零失败
  - 现有测试回归零新增失败
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- F9/F10 MUST come after F7（工时数据依赖）
- F2 depends on Phase 6 F4（项目级权限端点判断 EQCR 可见性）
- F12 复用 Phase 6 F7 urgency_score 三因子加权公式（无需新算法）
- DB 迁移编号 V009~V012 为占位，实施时动态确定 max+1
- PBT 后端使用 hypothesis max_examples=30 / 前端使用 fast-check numRuns: 30
- Property tests validate universal correctness properties; unit tests validate specific examples and edge cases
- Checkpoints ensure incremental validation at each Sprint boundary
- 13 features total: F1~F13 covering EQCR(3) + QC(3) + 工时(4) + 通知+合伙人(3)
