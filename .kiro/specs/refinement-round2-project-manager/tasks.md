# Refinement Round 2 — 任务清单

按 README 约定：一轮 ≤ 20 任务，分 2 个 Sprint。前置依赖：R1 需求 2 的 `IssueTicket.source` 枚举必须已完成迁移。

## Sprint 1：通知 + PM 看板 + 委派增强（需求 1~3, 8）

- [x] 1. 顶部通知铃铛接入
  - `DefaultLayout.vue` 顶部新增 `#nav-notifications` slot 挂 `NotificationCenter.vue`
  - `collaboration.ts` store 启动时调 `fetchNotifications()` + 订阅 SSE 通知事件
  - 未读 badge 实时刷新
  - _需求_ 2

- [x] 2. Notification type 字典扩展
  - **依赖 R1 tasks 19 已创建** `backend/app/services/notification_types.py`；R2 本任务向其追加类型常量，**不重复创建**
  - 前端 `src/services/notificationTypes.ts` 同步扩充 type → label + jump_handler
  - 本轮追加：`workpaper_reminder / workhour_approved / workhour_rejected / assignment_created / commitment_due`
  - _依赖_ README 跨轮约束第 1 条 + R1 tasks 19；_需求_ 2, 4, 5, 7

- [x] 3. 后端：ManagerDashboardService 聚合
  - 新建 `backend/app/services/manager_dashboard_service.py`
  - `GET /api/dashboard/manager/overview` 返回项目卡片 + 跨项目待办 + 团队负载
  - 权限守卫 `role='manager'` 或 `project_assignment.role IN ('manager','signing_partner')`
  - Redis 缓存 5 分钟
  - _需求_ 1

- [x] 4. 前端：ManagerDashboard 页面
  - 新建 `src/views/ManagerDashboard.vue`
  - 四区块：项目总览（卡片网格）+ 跨项目待办 + 本周关键动作 + 团队负载
  - 路由 `/dashboard/manager`，权限 `role='manager'` 或 admin
  - 导航入口加到 DefaultLayout "我的工作台" 分组
  - _需求_ 1

- [x] 5. 后端：增强批量委派端点
  - 包装现有 `POST /api/projects/{id}/working-papers/batch-assign`
  - 新增 `POST .../batch-assign-enhanced`：支持策略 `manual / round_robin / by_level`，可选 `override_assignments` 批量微调
  - 服务层 `BatchAssignStrategy` 纯函数，便于单元测试
  - _需求_ 3

- [x] 6. 前端：BatchAssignDialog 组件
  - `src/components/assignment/BatchAssignDialog.vue`
  - 三策略选择 + 预览表（每行可单独改）+ 提交
  - `WorkpaperList.vue` 用新组件替换现有批量分配
  - 提交后 toast 含"已分配 N 张，M 人收到通知"
  - _需求_ 3

- [x] 7. 后端：委派已读回执 API
  - `GET /api/dashboard/manager/assignment-status?days=7`
  - 联合 `Notification.is_read + read_at + assignment 记录`
  - 48 小时未读标红（查询时实时算，无 worker）
  - _需求_ 8

- [x] 8. 前端：PM 看板委派状态展示
  - ManagerDashboard 新增"近期委派"卡片
  - 调用 assignment-status 端点，展示已读/未读时间
  - 48h 未读红标提示
  - _需求_ 8

- [ ] Sprint 1 验收
  - 单元测试：`BatchAssignStrategy` 三策略 9 用例全过
  - 集成测试：`test_manager_dashboard.py` 聚合端点性能 < 500ms（10 项目）
  - UAT：requirements.md UAT 清单第 1/2/3 条走完

## Sprint 2：催办 + 沟通承诺 + 简报 + 工时审批（需求 4~7）

- [x] 9. 后端：催办端点
  - `POST /api/projects/{id}/workpapers/{wp_id}/remind`
  - 创建 `IssueTicket(source='reminder')` + `Notification(type='workpaper_reminder')`
  - 消息模板用"已创建 X 天尚未完成"措辞（不用"逾期"）
  - 7 天内 3 次限流（Redis `remind:{wp_id}:{day}` 计数）
  - 超限返回 429 + 提示消息
  - _需求_ 4

- [x] 10. 后端：重新分配增强
  - 复用 `PUT /working-papers/{wp_id}/assign`
  - 分配后通知原编制人"底稿已被重新分配"+ 新编制人"底稿已转交给您"
  - _需求_ 4

- [x] 11. 前端：ProjectDashboard 催办按钮
  - `ProjectDashboard.vue` overdue 表新增"操作"列
  - "催办"调催办端点，3 次后置灰提示
  - "重新分配"弹 StaffSelectDialog（复用）
  - _需求_ 4

- [x] 12. 后端：沟通记录 commitments 升级
  - `ClientCommunicationService` 读时兼容 string（自动包装），写时强制数组
  - 每条 commitment 创建 `IssueTicket(source='client_commitment')`，回写 `issue_ticket_id`
  - 新增 `PATCH /communications/{comm_id}/commitments/{commitment_id}` 标完成
  - _需求_ 5

- [x] 13. 前端：CommunicationCommitmentsEditor 组件
  - `src/components/pm/CommunicationCommitmentsEditor.vue`
  - 多条承诺输入（content + due_date）
  - 替换 `ProjectProgressBoard.vue` 沟通记录弹窗里原 string 输入
  - _需求_ 5

- [x] 14. 前端：客户承诺 Tab
  - ManagerDashboard "跨项目待办" 区新增"客户承诺"子 Tab
  - 聚合所有项目 commitments，7 天内到期正常显示，逾期置顶红标
  - 点击"已完成"调 PATCH 端点
  - _需求_ 5

- [x] 15. 后端：批量简报端点
  - `POST /api/projects/briefs/batch?project_ids=&use_ai=`
  - 走 `ExportJobService` 异步，内部循环调 `ProgressBriefService.generate`
  - AI 模式拼完后走 `unified_ai_service` 做综合总结，失败回退纯拼接
  - 结果存 `ExportTaskService` 历史，7 天内相同项目组合复用
  - _需求_ 6

- [x] 16. 前端：CrossProjectBriefExporter 组件
  - `src/components/pm/CrossProjectBriefExporter.vue`
  - 多选项目 + "导出合并简报" 按钮
  - 轮询导出任务状态，完成后自动下载
  - 集成到 ManagerDashboard 项目总览区
  - _需求_ 6

- [x] 17. 后端：工时批量审批
  - `POST /api/workhours/batch-approve`，幂等键头 `Idempotency-Key`
  - 状态流转 `confirmed→approved` 或 `confirmed→draft`（退回附原因）
  - SOD 守卫：审批人 ≠ 被审批人
  - 发通知 `workhour_approved / workhour_rejected`
  - _需求_ 7

- [x] 18. 前端：WorkHoursApproval 页面
  - `src/views/WorkHoursApproval.vue`
  - 表格 + 多选 + 批量按钮
  - 默认筛选状态=confirmed + 日期=上周
  - 本周已审批/未审批统计卡
  - 路由 `/work-hours/approve`，权限 `manager` 或 `admin`
  - _需求_ 7

- [x] 19. 权限与导航收口
  - `composables/usePermission.ts` 扩 `approve_workhours / send_reminder / batch_brief / view_dashboard_manager`
  - `assignment_service.ROLE_MAP / role_context_service._ROLE_PRIORITY` 已含 manager，只补前端 ROLE_PERMISSIONS
  - DefaultLayout 侧边栏对 manager 显示新入口
  - _依赖_ README 跨轮约束第 2 条；_需求_ 1, 4, 6, 7

- [ ] Sprint 2 验收
  - 单元测试：催办 7 天限流 + 工时幂等各 3 用例
  - 集成测试：`test_pm_workflow_e2e.py`（委派→催办→重新分配→承诺→审批→简报）
  - 回归：现有 batch-assign 原端点可用
  - UAT：requirements.md UAT 第 4/5/6/7 条走完

## 完成标志

- 所有任务 `[x]`
- UAT 7 项有通过记录
- `pytest backend/tests/ -v` 全过
- vue-tsc 新增错误 ≤ 0
- Round 2 关闭，R3 与 R4 可并行启动

## Sprint 3：长期运营合规（需求 9~10，新增）

5 个任务，Sprint 3 独立跑。依赖 R1 Sprint 3（审计日志落库）完成。

- [x] 20. 数据模型：预算字段 + 交接记录表
  - `Project` 新增 `budget_hours / contract_amount / budgeted_by / budgeted_at`
  - 新建 `backend/app/models/handover_models.py` (`HandoverRecord`)
  - `system_settings.hourly_rates` 配置 schema
  - Alembic 脚本 `round2_budget_handover_{date}.py`
  - _需求_ 9, 10

- [x] 21. 后端：成本看板 + 预警
  - `backend/app/services/cost_overview_service.py`
  - `GET /api/projects/{id}/cost-overview` 返回 burn rate / 超支预计
  - 新增 `budget_alert_worker`：每日凌晨扫项目工时，80%/100% 触发通知
  - _需求_ 9

- [x] 22. 前端：ProjectWizard 填预算字段 + ManagerDashboard 成本卡
  - `ProjectWizard.vue` BasicInfoStep 新增 `budget_hours / contract_amount` 输入
  - `ManagerDashboard.vue` 项目卡新增工时进度条（>90% 橙 / >100% 红闪）
  - `WorkHoursApproval.vue` 批量审批前置预估"将超预算 N 小时"
  - _需求_ 9

- [x] 23. 后端：人员交接端点
  - `backend/app/services/handover_service.py`
  - `POST /api/staff/{staff_id}/handover` 批量转移底稿/工单/项目委派
  - 写 `HandoverRecord` + `audit_log`（R1 需求 9 哈希链）
  - resignation 时标记 superseded_by_handover
  - _需求_ 10

- [x] 24. 前端：StaffManagement 交接按钮 + 预览
  - `StaffManagement.vue` 新增"交接"按钮
  - 弹窗选目标人 + 原因码 + 预览"将转交 N 张底稿 / M 张工单"
  - 执行后刷新并发通知
  - _需求_ 10

- [ ] Sprint 3 验收
  - 集成测试：`test_handover_e2e.py`（建 staff→分配底稿→离职交接→验证数据全迁移+留痕）
  - UAT 新增：
    - 建项目填 budget_hours=200，团队填到 180h 时收到 80% 预警
    - 某员工离职，一键交接 15 张底稿 + 5 张工单给目标人，新负责人收到通知且 handover_records 有记录
