# 实现计划：第三阶段协作与质控 — 多用户权限+三级复核+期后事项+版本控制+项目看板+函证管理+审计档案归档

## 概述

本实现计划将设计文档中的架构和组件拆解为可执行的编码任务，按照数据库→后端服务→前端页面→测试的顺序递进实现。每个任务构建在前序任务之上。技术栈：Python（FastAPI + SQLAlchemy + Celery + Hypothesis）+ TypeScript（Vue 3 + Pinia）。

## 任务

- [ ] 1. 数据库迁移：创建21张协作相关表及索引
  - [ ] 1.1 扩展 `users` 表（Phase 0 已创建基础版本），无需新增字段（role 枚举已包含 qc_reviewer），仅验证索引完整性
    - _需求: 10.1_
  - [ ] 1.2 扩展 `project_users` 表（Phase 0 已创建基础版本），新增字段：assigned_cycles jsonb、assigned_account_ranges jsonb；更新 role 枚举为 project_role（与 phase0 的 role 字段区分）；及复合唯一索引 (project_id, user_id) 和索引 (project_id, project_role)
    - _需求: 10.2_
  - [ ] 1.3 扩展 `logs` 表（Phase 0 已创建基础版本），新增字段：operation_type 扩展枚举值（增加 review/archive）、object_type 扩展枚举值；及复合索引 (project_id, created_at) 和索引 (user_id, created_at)
    - _需求: 10.3_
  - [ ] 1.4 扩展 `review_records` 表（Phase 1b 已创建基础版本），新增字段：review_level enum level_1/level_2、object_type enum working_paper/adjustment/report/subsequent_event/confirmation、review_opinion text not null、review_result enum approved/rejected/needs_revision、response_content text nullable、response_by UUID FK nullable、response_at timestamp nullable、is_resolved boolean default false、project_id UUID FK、reviewer_id UUID FK；及复合索引 (project_id, object_type, object_id) 和索引 (reviewer_id, created_at)
    - _需求: 10.4_
  - [ ] 1.5 创建 `subsequent_events` 表（UUID PK、project_id UUID FK、event_type enum adjusting/non_adjusting、discovery_date date not null、event_description text not null、affected_accounts jsonb、impact_amount numeric(20,2) nullable、treatment enum adjusted/disclosed/no_action_needed、related_adjustment_id UUID FK nullable、related_note_section varchar nullable、identified_by UUID FK、review_status enum draft/pending_review/approved/rejected default draft、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, event_type)
    - _需求: 10.5_
  - [ ] 1.6 创建 `subsequent_events_checklist` 表（UUID PK、project_id UUID FK、procedure_name varchar not null、procedure_description text、execution_status enum not_started/in_progress/completed/not_applicable、executed_by UUID FK nullable、executed_at date nullable、findings_summary text nullable、is_deleted boolean default false、created_at、updated_at）及索引 (project_id, execution_status)
    - _需求: 10.6_
  - [ ] 1.7 创建 `project_sync` 表（UUID PK、project_id UUID FK unique、local_version int default 0、cloud_version int default 0、last_sync_time timestamp nullable、last_sync_by UUID FK nullable、sync_status enum idle/syncing/conflict/error default idle、is_deleted boolean default false、created_at、updated_at）及唯一索引 (project_id)
    - _需求: 10.7_
  - [ ] 1.8 创建 `sync_logs` 表（UUID PK、project_id UUID FK、sync_user_id UUID FK、sync_time timestamp、version_before int、version_after int、sync_direction enum upload/download/merge、change_summary text、backup_file_path varchar nullable、is_deleted boolean default false、created_at）及复合索引 (project_id, sync_time)
    - _需求: 10.8_
  - [ ] 1.9 创建 `project_timelines` 表（UUID PK、project_id UUID FK、milestone_type enum plan_start/field_entry/field_exit/report_date/archive_deadline、planned_date date、actual_date date nullable、notes text nullable、is_deleted boolean default false、created_at、updated_at）及复合唯一索引 (project_id, milestone_type)
    - _需求: 10.9_
  - [ ] 1.10 创建 `workhours` 表（UUID PK、project_id UUID FK、user_id UUID FK、work_date date not null、hours numeric(4,1) not null、work_description text、audit_cycle varchar nullable、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, user_id, work_date)
    - _需求: 10.10_
  - [ ] 1.11 创建 `budget_hours` 表（UUID PK、project_id UUID FK、role_type enum partner/manager/auditor、budget_hours numeric(8,1)、actual_hours numeric(8,1) default 0、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, role_type)
    - _需求: 10.11_
  - [ ] 1.12 创建 `pbc_checklist` 表（UUID PK、project_id UUID FK、item_name varchar not null、audit_cycle varchar、requested_from varchar、due_date date、received_status enum not_received/received/overdue、received_date date nullable、notes text nullable、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, audit_cycle)
    - _需求: 10.12_
  - [ ] 1.13 扩展 `notifications` 表（Phase 0 已创建基础版本），扩展 notification_type 枚举值（增加 ai_complete/import_complete/confirmation_overdue/sync_conflict）；及复合索引 (recipient_id, is_read, created_at)
    - _需求: 10.13_
  - [ ] 1.14 创建 `confirmation_list` 表（UUID PK、project_id UUID FK、confirmation_no varchar、confirmation_type enum bank/receivable/payable/lawyer/other、counterparty_name varchar not null、account_code varchar、book_amount numeric(20,2)、cutoff_date date、approval_status enum draft/approved/submitted_to_center、approved_by UUID FK nullable、submitted_at timestamp nullable、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, confirmation_type)
    - _需求: 10.14_
  - [ ] 1.15 创建 `confirmation_letter` 表（UUID PK、confirmation_list_id UUID FK、template_type enum bank/receivable/payable/lawyer、generated_at timestamp、letter_file_path varchar、is_deleted boolean default false、created_at）及索引 (confirmation_list_id)
    - _需求: 10.15_
  - [ ] 1.16 创建 `confirmation_result` 表（UUID PK、confirmation_list_id UUID FK、reply_date date nullable、reply_status enum confirmed_match/confirmed_mismatch/no_reply/returned、confirmed_amount numeric(20,2) nullable、difference_amount numeric(20,2) nullable、difference_reason text nullable、needs_adjustment boolean default false、alternative_procedure text nullable、alternative_conclusion text nullable、is_deleted boolean default false、created_at、updated_at）及索引 (confirmation_list_id)
    - _需求: 10.16_
  - [ ] 1.17 创建 `confirmation_summary` 表（UUID PK、project_id UUID FK、confirmation_type enum、total_count int、replied_count int、no_reply_count int、reply_rate numeric(5,2)、total_amount numeric(20,2)、matched_amount numeric(20,2)、difference_amount numeric(20,2)、coverage_rate numeric(5,2)、needs_adjustment_amount numeric(20,2)、is_deleted boolean default false、created_at、updated_at）及复合唯一索引 (project_id, confirmation_type)
    - _需求: 10.17_
  - [ ] 1.18 创建 `confirmation_attachment` 表（UUID PK、confirmation_list_id UUID FK、file_path varchar、file_name varchar、uploaded_at timestamp、uploaded_by UUID FK、is_deleted boolean default false、created_at）及索引 (confirmation_list_id)
    - _需求: 10.18_
  - [ ] 1.19 创建 `going_concern` 表（UUID PK、project_id UUID FK、evaluation_date date not null、management_assessment_summary text、identified_concerns text nullable、management_response_plan text nullable、auditor_evaluation text、conclusion_type enum no_significant_doubt/material_uncertainty/going_concern_inappropriate、impact_on_report text、review_status enum draft/pending_review/approved/rejected default draft、is_deleted boolean default false、created_at、updated_at）及唯一索引 (project_id) where is_deleted=false
    - _需求: 10.19_
  - [ ] 1.20 创建 `going_concern_indicators` 表（UUID PK、project_id UUID FK、indicator_category enum financial/operational/other、indicator_name varchar not null、indicator_status enum present/absent/not_applicable、evaluation_notes text nullable、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, indicator_category)
    - _需求: 10.20_
  - [ ] 1.21 创建 `archive_modifications` 表（UUID PK、project_id UUID FK、modification_reason text not null、modification_description text not null、approved_by UUID FK、approval_date date、modifier_id UUID FK、modified_at timestamp、old_value jsonb、new_value jsonb、is_deleted boolean default false、created_at）及索引 (project_id, created_at)
    - _需求: 10.21_

- [ ] 2. 定义 SQLAlchemy ORM 模型与 Pydantic Schema
  - [ ] 2.1 在 `backend/app/models/` 下创建 `collaboration_models.py`，定义21张表对应的 SQLAlchemy ORM 模型（User、ProjectUser、Log、ReviewRecord扩展、SubsequentEvent、SEChecklist、ProjectSync、SyncLog、ProjectTimeline、Workhour、BudgetHour、PBCChecklist、Notification、ConfirmationList、ConfirmationLetter、ConfirmationResult、ConfirmationSummary、ConfirmationAttachment、GoingConcern、GoingConcernIndicator、ArchiveModification），包含所有字段、枚举类型、外键关系
    - _需求: 10.1-10.21_
  - [ ] 2.2 在 `backend/app/models/` 下创建 `collaboration_schemas.py`，定义所有 API 请求/响应的 Pydantic Schema（UserCreate/Update、LoginRequest/TokenPair、ProjectUserCreate、ReviewCreate/Response、SubsequentEventCreate/Update、SEChecklistUpdate、SyncStatus/Result/ConflictResolution、ExportScope/ImportResult、ProjectOverview/RiskAlert/WorkloadSummary、WorkhourCreate、BudgetHourUpdate、PBCCreate/Update、NotificationFilter、ConfirmationCreate/ResultCreate/Summary、GoingConcernCreate/Update/IndicatorUpdate、ArchiveChecklistItem/ModificationRequest 等）
    - _需求: 1-10_

- [ ] 3. 检查点 — 确保数据库迁移和模型定义正确
  - 运行 `alembic upgrade head` 确认迁移成功，确保所有测试通过，如有问题请询问用户。

- [ ] 4. 认证与权限服务
  - [ ] 4.1 实现 `backend/app/services/auth_service.py`：login（验证用户名密码+JWT生成+登录失败计数Redis）、refresh_token（刷新access_token）、logout（Token加入Redis黑名单）、check_lockout（5次失败锁30分钟）
    - _需求: 1.6_
  - [ ] 4.2 实现 `backend/app/services/permission_service.py`：PERMISSION_MATRIX定义、check_permission（角色+项目级权限校验）、check_cycle_scope（审计循环分工范围校验）
    - _需求: 1.3, 1.4_
  - [ ] 4.3 实现权限中间件 `backend/app/middleware/auth_middleware.py`：JWT验证+用户提取+权限校验，注入到FastAPI依赖
    - _需求: 1.3, 1.6_
  - [ ] 4.4 实现操作日志中间件 `backend/app/middleware/audit_log_middleware.py`：拦截所有写操作，记录到logs表（含old_value/new_value）
    - _需求: 1.5_
  - [ ] 4.5 实现认证与用户管理 API 路由 `backend/app/routers/auth.py` 和 `backend/app/routers/users.py`：登录/登出/刷新Token、用户CRUD、项目成员管理
    - _需求: 1.1-1.7_

- [ ] 5. 复核服务 (ReviewService)
  - [ ] 5.1 实现 `backend/app/services/review_service.py`：submit_for_review（更新对象状态为prepared+通知复核人）、create_review（创建复核记录+状态变更+通知）、respond_to_review（编制人回复+通知复核人）、resolve_review（确认意见已解决）
    - _需求: 2.1-2.5_
  - [ ] 5.2 实现复核状态机：enforce_status_transition（校验合法转换：draft→prepared→level_1_approved→level_2_approved→archived，退回回到draft）、关键底稿二级复核强制校验
    - _需求: 2.2, 2.4_
  - [ ] 5.3 实现项目状态管理：check_review_gate（门控条件校验）、transition_project_status（状态转换+门控校验+事件发布）、get_review_timeliness（复核及时性统计）
    - _需求: 2.6, 2.7, 2.8_
  - [ ] 5.4 实现复核 API 路由 `backend/app/routers/reviews.py`：复核CRUD、回复、解决、项目状态变更、复核及时性报告
    - _需求: 2.1-2.8_

- [ ] 6. 检查点 — 确保认证、权限和复核服务正确
  - 运行单元测试确认JWT认证、权限矩阵、复核状态机、项目状态门控逻辑正确。

- [ ] 7. 期后事项服务 (SubsequentEventService)
  - [ ] 7.1 实现 `backend/app/services/subsequent_event_service.py`：create_event（创建期后事项+关联校验：调整事项必须关联调整分录、非调整事项必须关联附注章节）、update_event、delete_event
    - _需求: 3.1, 3.2, 3.3_
  - [ ] 7.2 实现 init_checklist（项目创建时预填充6项标准审阅程序）、update_checklist_item（更新执行状态）、check_completion（检查清单完成性，用于项目状态门控）
    - _需求: 3.4, 3.5, 3.6_
  - [ ] 7.3 实现 carry_forward_events（将上年非调整事项结转到新年度项目作为参考）
    - _需求: 3.7_
  - [ ] 7.4 实现期后事项 API 路由 `backend/app/routers/subsequent_events.py`：事项CRUD、审阅程序清单管理
    - _需求: 3.1-3.7_

- [ ] 8. 通知服务 (NotificationService)
  - [ ] 8.1 实现 `backend/app/services/notification_service.py`：create_notification、get_notifications（分页+筛选）、mark_read、mark_all_read、get_unread_count（Redis缓存30秒TTL）
    - _需求: 6.1, 6.5_
  - [ ] 8.2 实现事件处理器：on_review_submitted（复核待办通知）、on_review_completed（复核完成通知）、on_review_responded（回复通知）、on_misstatement_alert（错报超限通知）、on_confirmation_overdue（函证超期通知）、on_sync_conflict（同步冲突通知）、on_going_concern_alert（持续经营预警通知）
    - _需求: 6.2, 6.3, 6.4_
  - [ ] 8.3 注册EventBus事件处理器，实现事件→通知的自动映射
    - _需求: 6.2-6.4_
  - [ ] 8.4 实现通知 API 路由 `backend/app/routers/notifications.py`：通知列表、标记已读、全部已读、未读数量
    - _需求: 6.5, 6.6_

- [ ] 9. 版本控制与同步服务 (SyncService)
  - [ ] 9.1 实现 `backend/app/services/sync_service.py`：check_sync_status（本地vs云端版本比较）、upload（版本校验+数据打包+上传+版本号递增+记录sync_log）、download（拉取最新+更新本地版本号）
    - _需求: 4.1, 4.2_
  - [ ] 9.2 实现冲突解决：resolve_conflict（按用户选择合并数据：不同科目自动合并、同一分录展示差异、已审核数据不可覆盖）
    - _需求: 4.3, 4.4_
  - [ ] 9.3 实现离线协作：export_package（导出Excel/JSON数据包含版本元数据）、import_package（导入+校验项目存在性/年度匹配/科目合法性/借贷平衡/版本过期）
    - _需求: 4.5_
  - [ ] 9.4 实现同步 API 路由 `backend/app/routers/sync.py`：同步状态、上传、下载、冲突解决、导出/导入离线包、同步日志
    - _需求: 4.1-4.7_

- [ ] 10. 项目看板服务 (DashboardService)
  - [ ] 10.1 实现 `backend/app/services/dashboard_service.py`：get_project_overview（项目进度+底稿完成率+复核完成率+距截止日天数）、get_risk_alerts（超期/错报超限/关键底稿未复核/函证超期）
    - _需求: 5.1_
  - [ ] 10.2 实现工时管理：record_workhours（记录工时）、get_workload_summary（预算vs实际工时汇总）、auto_update_actual_hours（工时变更时自动更新budget_hours.actual_hours）
    - _需求: 5.4, 5.5_
  - [ ] 10.3 实现项目时间节点管理：create/update_timeline（时间节点CRUD）、auto_calc_archive_deadline（report_date+60天）、check_overdue（距截止日≤15天触发通知）
    - _需求: 5.2, 5.3_
  - [ ] 10.4 实现PBC清单管理：create/update_pbc_item、get_pbc_status（接收状态汇总）
    - _需求: 5.6_
  - [ ] 10.5 实现看板 API 路由 `backend/app/routers/dashboard.py`：项目概览、风险预警、工时管理、时间节点、PBC清单
    - _需求: 5.1-5.6_

- [ ] 11. 检查点 — 确保期后事项、通知、同步、看板服务正确
  - 运行单元测试确认：期后事项关联校验、通知事件映射、同步版本号逻辑、看板统计计算。

- [ ] 12. 函证服务 (ConfirmationService)
  - [ ] 12.1 实现 `backend/app/services/confirmation_service.py`：auto_extract_candidates（从余额表/辅助余额表自动提取函证候选：银行存款/应收客户/应付供应商）、create_confirmation（创建函证清单项+自动编号CF-{type}-{seq}）
    - _需求: 7.1, 7.2_
  - [ ] 12.2 实现 approve_list（项目经理审核函证清单）、generate_letters（批量生成询证函PDF/Excel，自动填充被审计单位信息+金额+截止日期）
    - _需求: 7.3_
  - [ ] 12.3 实现 record_result（登记回函结果+自动计算差异金额）、未回函强制替代程序校验、upload_attachment（上传回函扫描件）
    - _需求: 7.4, 7.5, 7.7_
  - [ ] 12.4 实现 update_summary（更新函证统计表：回函率/金额覆盖率/差异金额/需调整金额）、check_overdue（检查超30天未回函+触发通知）
    - _需求: 7.6_
  - [ ] 12.5 实现函证 API 路由 `backend/app/routers/confirmations.py`：函证清单CRUD、自动提取、审核、生成询证函、回函登记、统计表、附件上传
    - _需求: 7.1-7.7_

- [ ] 13. 归档服务 (ArchiveService)
  - [ ] 13.1 实现 `backend/app/services/archive_service.py`：generate_checklist（生成归档检查清单预填充17项标准项目）、update_checklist_item（更新完成状态）、check_archive_ready（校验清单全部完成）
    - _需求: 8.1, 8.2_
  - [ ] 13.2 实现 archive_project（执行归档：校验清单+锁定所有数据为只读+记录archive_date+计算retention_expiry_date=archive_date+10年）
    - _需求: 8.4, 8.5_
  - [ ] 13.3 实现 export_archive_pdf（导出电子档案PDF：按索引排序+目录页+GT品牌封面+页眉页脚+可选密码保护+交叉引用超链接）
    - _需求: 8.3, 8.6_
  - [ ] 13.4 实现 request_post_archive_modification（申请归档后修改）和 approve_modification（审批修改+记录before/after对比）
    - _需求: 8.4_
  - [ ] 13.5 实现归档 API 路由 `backend/app/routers/archive.py`：归档检查清单、执行归档、PDF导出、归档后修改申请/审批
    - _需求: 8.1-8.6_

- [ ] 14. 持续经营服务 (GoingConcernService)
  - [ ] 14.1 实现 `backend/app/services/going_concern_service.py`：init_indicators（项目创建时预填充标准风险指标：财务指标5项+经营指标3项+其他指标3项）、update_indicator（更新指标评估状态）
    - _需求: 9.2, 9.3_
  - [ ] 14.2 实现 create_evaluation（创建持续经营评价记录）、update_evaluation（更新评价+结论类型+对报告影响）、check_report_impact（material_uncertainty→通知增加段落、going_concern_inappropriate→通知考虑否定意见）
    - _需求: 9.1, 9.4, 9.5_
  - [ ] 14.3 实现持续经营 API 路由 `backend/app/routers/going_concern.py`：评价CRUD、风险指标清单管理
    - _需求: 9.1-9.5_

- [ ] 15. 检查点 — 确保所有后端服务正确
  - 运行单元测试确认：函证差异计算、统计表自动更新、归档检查清单门控、归档后数据锁定、持续经营结论与报告联动。

- [ ] 16. 前端：登录与用户管理页面
  - [ ] 16.1 创建 `frontend/src/views/Login.vue`：GT品牌登录页（紫色渐变背景+Logo+用户名密码表单+记住我+错误提示）
    - _需求: 1.6_
  - [ ] 16.2 创建 `frontend/src/views/UserManagement.vue`：用户列表表格+创建/编辑弹窗（角色下拉+密码强度指示器），仅Admin可见
    - _需求: 1.1, 1.7_
  - [ ] 16.3 创建 `frontend/src/components/collaboration/ProjectMemberPanel.vue`：项目成员管理（成员列表+角色+分工循环标签+添加成员弹窗含审计循环多选）
    - _需求: 1.2, 1.3_

- [ ] 17. 前端：复核面板
  - [ ] 17.1 创建 `frontend/src/components/collaboration/ReviewPanel.vue`：底稿详情页右侧复核侧边栏（复核意见列表+新建意见表单+编制人回复区域+复核历史时间线），未解决意见红色标注置顶
    - _需求: 2.1-2.5_
  - [ ] 17.2 创建 `frontend/src/components/collaboration/ProjectStatusBar.vue`：项目状态流转指示器（六阶段进度条+当前阶段高亮+门控条件检查弹窗）
    - _需求: 2.7_

- [ ] 18. 前端：期后事项管理页面
  - [ ] 18.1 创建 `frontend/src/components/collaboration/SubsequentEventsPanel.vue`：双Tab（期后事项记录|审阅程序清单），事项表格+新建弹窗（类型选择+描述+影响金额+关联调整/附注），清单表格含状态色标
    - _需求: 3.1-3.6_

- [ ] 19. 前端：项目看板页面
  - [ ] 19.1 创建 `frontend/src/views/Dashboard.vue`：四象限布局（项目进度卡片+风险预警列表+人员工时柱状图+报告状态饼图），admin/partner/manager/qc_reviewer可见
    - _需求: 5.1_
  - [ ] 19.2 创建 `frontend/src/components/collaboration/WorkhourForm.vue`：工时记录表单（项目+日期+工时+工作内容+审计循环）
    - _需求: 5.4_
  - [ ] 19.3 创建 `frontend/src/components/collaboration/TimelinePanel.vue`：项目时间节点管理（里程碑列表+计划/实际日期+剩余天数+超期红色标注）
    - _需求: 5.2, 5.3_
  - [ ] 19.4 创建 `frontend/src/components/collaboration/PBCPanel.vue`：PBC清单管理（资料列表+接收状态+截止日期+超期标注）
    - _需求: 5.6_

- [ ] 20. 前端：函证管理页面
  - [ ] 20.1 创建 `frontend/src/components/collaboration/ConfirmationPanel.vue`：Tab切换（银行/应收/应付/律师/全部），函证清单表格+自动提取按钮+审核按钮+生成询证函按钮
    - _需求: 7.1-7.3_
  - [ ] 20.2 创建 `frontend/src/components/collaboration/ConfirmationResultForm.vue`：回函登记弹窗（回函状态+确认金额+差异原因+替代程序）+回函附件上传
    - _需求: 7.4, 7.5, 7.7_
  - [ ] 20.3 创建 `frontend/src/components/collaboration/ConfirmationSummary.vue`：函证统计表视图（回函率/金额覆盖率/差异金额汇总表格+图表）
    - _需求: 7.6_

- [ ] 21. 前端：归档管理页面
  - [ ] 21.1 创建 `frontend/src/components/collaboration/ArchivePanel.vue`：归档检查清单（勾选列表+负责人+完成状态）+归档操作按钮+PDF导出按钮（含密码设置）
    - _需求: 8.1-8.3, 8.6_
  - [ ] 21.2 创建 `frontend/src/components/collaboration/ArchiveModificationForm.vue`：归档后修改申请表单+审批流程展示
    - _需求: 8.4_

- [ ] 22. 前端：通知中心与持续经营
  - [ ] 22.1 创建 `frontend/src/components/collaboration/NotificationCenter.vue`：顶部导航栏通知铃铛+未读数角标+下拉面板（通知列表+类型图标+标题+时间+已读状态），点击跳转关联对象，30秒轮询未读数
    - _需求: 6.1-6.6_
  - [ ] 22.2 创建 `frontend/src/components/collaboration/GoingConcernPanel.vue`：双Tab（风险指标检查清单|评价记录），指标分类分组+状态切换+评价表单（管理层评估+审计师评价+结论类型+对报告影响）
    - _需求: 9.1-9.5_

- [ ] 23. 前端：路由与状态管理
  - [ ] 23.1 在 `frontend/src/router/` 中注册协作模块路由（/login、/users、/dashboard、/projects/{id}/reviews、/projects/{id}/subsequent-events、/projects/{id}/confirmations、/projects/{id}/archive、/projects/{id}/going-concern），在 `frontend/src/stores/` 中创建 collaboration store（Pinia）管理认证状态、通知状态、看板数据
    - _需求: 1-10_
  - [ ] 23.2 实现路由守卫：未登录重定向到登录页、权限不足页面隐藏/禁用、JWT Token自动刷新
    - _需求: 1.3, 1.6_

- [ ] 24. 前端：API服务层
  - [ ] 24.1 在 `frontend/src/services/` 中创建 `collaborationApi.ts`，封装所有协作相关API调用（auth、users、project-members、reviews、subsequent-events、sync、dashboard、workhours、timelines、pbc、confirmations、archive、notifications、going-concern），含JWT Token自动注入和刷新拦截器
    - _需求: 1-10_

- [ ] 25. 检查点 — 确保前端页面和API集成正确
  - 手动测试完整流程：登录→创建用户→分配项目成员→编制底稿→提交复核→一级复核→二级复核→记录期后事项→编制函证清单→登记回函→归档检查→执行归档→PDF导出。

- [ ] 26. 后端单元测试
  - [ ] 26.1 编写 `backend/tests/test_auth_permission.py`：测试JWT认证（登录/刷新/登出/过期/锁定）、权限矩阵校验（六种角色×各操作）、审计循环分工范围校验
    - _需求: 1.3, 1.4, 1.6_
  - [ ] 26.2 编写 `backend/tests/test_review_service.py`：测试复核状态机（合法/非法转换）、复核退回必须附带意见、项目状态门控条件、关键底稿二级复核强制、复核及时性统计
    - _需求: 2.2-2.8_
  - [ ] 26.3 编写 `backend/tests/test_subsequent_events.py`：测试期后事项关联完整性（调整事项→调整分录、非调整事项→附注）、审阅程序清单完成性门控、上年事项结转
    - _需求: 3.2, 3.3, 3.6, 3.7_
  - [ ] 26.4 编写 `backend/tests/test_sync_service.py`：测试同步版本号逻辑（上传/下载/冲突检测）、已审核数据不可覆盖、离线包导入校验
    - _需求: 4.2, 4.4, 4.5_
  - [ ] 26.5 编写 `backend/tests/test_confirmation_service.py`：测试函证差异金额计算、未回函替代程序强制、统计表自动计算一致性、超期检测
    - _需求: 7.5, 7.6_
  - [ ] 26.6 编写 `backend/tests/test_archive_service.py`：测试归档检查清单门控、归档后数据锁定、归档保存期不可违反、归档后修改审批流程
    - _需求: 8.2, 8.4, 8.5_
  - [ ] 26.7 编写 `backend/tests/test_going_concern.py`：测试持续经营结论与报告联动（material_uncertainty→通知、going_concern_inappropriate→通知）、风险指标预填充
    - _需求: 9.3, 9.4, 9.5_
  - [ ] 26.8 编写 `backend/tests/test_notification_service.py`：测试事件→通知映射（复核提交/超期/错报超限/函证超期/同步冲突）、未读数缓存
    - _需求: 6.2-6.4_

- [ ] 27. 审计程序与风险管理
  - [ ] 27.1 创建 Alembic 迁移脚本，定义 `risk_assessment` 表（UUID PK、project_id FK、assertion_level enum existence/completeness/accuracy/cutoff/classification/occurrence/rights_obligations/valuation、account_or_cycle varchar、inherent_risk enum high/medium/low、control_risk enum high/medium/low、combined_risk enum high/medium/low、is_significant_risk boolean default false、risk_description text、response_strategy text、related_audit_procedures jsonb、review_status enum draft/pending_review/approved/rejected、is_deleted boolean default false、created_at、updated_at、created_by FK）及复合索引 (project_id, account_or_cycle)
    - _需求: 12.1_
  - [ ] 27.2 创建 `audit_plan` 表（UUID PK、project_id FK、plan_version int default 1、audit_strategy text、planned_start_date date、planned_end_date date、key_focus_areas jsonb、team_assignment_summary jsonb、materiality_reference text、status enum draft/approved/revised、approved_by FK nullable、approved_at timestamp nullable、is_deleted boolean default false、created_at、updated_at、created_by FK）及唯一索引 (project_id) where is_deleted=false
    - _需求: 12.2_
  - [ ] 27.3 创建 `audit_procedures` 表（UUID PK、project_id FK、procedure_code varchar、procedure_name varchar、procedure_type enum risk_assessment/control_test/substantive、audit_cycle varchar、account_code varchar nullable、description text、execution_status enum not_started/in_progress/completed/not_applicable、executed_by FK nullable、executed_at date nullable、conclusion text nullable、related_wp_code varchar nullable、related_risk_id FK nullable、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, procedure_type) 和索引 (project_id, audit_cycle)
    - _需求: 12.3_
  - [ ] 27.4 创建 `audit_findings` 表（UUID PK、project_id FK、finding_code varchar、finding_description text、severity enum high/medium/low、affected_account varchar nullable、finding_amount numeric(20,2) nullable、management_response text nullable、final_treatment enum adjusted/unadjusted/disclosed/no_action nullable、related_adjustment_id FK nullable、related_wp_code varchar nullable、identified_by FK、review_status enum draft/pending_review/approved/rejected、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, severity)
    - _需求: 12.4_
  - [ ] 27.5 创建 `management_letter` 表（UUID PK、project_id FK、item_code varchar、deficiency_type enum significant_deficiency/material_weakness/other_deficiency、deficiency_description text、potential_impact text、recommendation text、management_response text nullable、response_deadline date nullable、prior_year_item_id FK nullable、follow_up_status enum new/in_progress/resolved/carried_forward、is_deleted boolean default false、created_at、updated_at、created_by FK）及复合索引 (project_id, deficiency_type)
    - _需求: 12.5_
  - [ ] 27.6 在 `collaboration_models.py` 中新增 `RiskAssessment`、`AuditPlan`、`AuditProcedure`、`AuditFinding`、`ManagementLetter` ORM 模型，在 `collaboration_schemas.py` 中新增对应 Pydantic Schema
    - _需求: 11.1-11.10, 12.1-12.5_
  - [ ] 27.7 实现 `RiskAssessmentService`：create_assessment（创建风险评估+自动计算combined_risk+特别风险校验response_strategy）、get_risk_procedure_matrix（风险-程序覆盖矩阵视图）
    - _需求: 11.1, 11.6, 11.7, 11.10_
  - [ ] 27.8 实现 `AuditPlanService`：create_plan（创建审计计划）、approve_plan（审批审计计划）
    - _需求: 11.2_
  - [ ] 27.9 实现 `AuditProcedureService`：create_procedure（创建审计程序关联风险评估和底稿）、update_execution_status（更新执行状态和结论）
    - _需求: 11.3, 11.8_
  - [ ] 27.10 实现 `AuditFindingService`：create_finding（创建审计发现关联调整分录和底稿）、record_management_response（记录管理层回复和最终处理）
    - _需求: 11.4_
  - [ ] 27.11 实现 `ManagementLetterService`：create_item（创建管理建议书事项）、carry_forward（将上年未解决事项结转到新年度，follow_up_status=carried_forward+prior_year_item_id）
    - _需求: 11.5, 11.9_
  - [ ] 27.12 实现审计程序与风险管理 API 路由（`backend/app/routers/audit_program.py`）：风险评估CRUD+覆盖矩阵、审计计划CRUD+审批、审计程序CRUD、审计发现CRUD、管理建议书CRUD
    - _需求: 11.1-11.10_

- [ ] 28. 前端：审计程序与风险管理页面
  - [ ] 28.1 创建 `frontend/src/components/collaboration/RiskAssessmentPanel.vue`：风险评估表格（认定层次+科目/循环+固有风险+控制风险+组合风险+特别风险标记+应对策略），风险-程序覆盖矩阵视图
    - _需求: 11.1, 11.7, 11.10_
  - [ ] 28.2 创建 `frontend/src/components/collaboration/AuditPlanPanel.vue`：审计计划编辑（审计策略+时间安排+重点领域+团队分工摘要+审批状态）
    - _需求: 11.2_
  - [ ] 28.3 创建 `frontend/src/components/collaboration/AuditProcedurePanel.vue`：审计程序清单（程序编号+名称+类型+循环+执行状态+结论+关联底稿+关联风险），支持按类型/循环筛选
    - _需求: 11.3, 11.8_
  - [ ] 28.4 创建 `frontend/src/components/collaboration/AuditFindingPanel.vue`：审计发现列表（发现编号+描述+严重程度+影响金额+管理层回复+最终处理+关联调整/底稿）
    - _需求: 11.4_
  - [ ] 28.5 创建 `frontend/src/components/collaboration/ManagementLetterPanel.vue`：管理建议书事项列表（事项编号+缺陷类型+描述+建议+管理层回复+跟踪状态），支持上年事项结转展示
    - _需求: 11.5, 11.9_

- [ ] 29. 审计程序与风险管理测试
  - [ ] 29.1 编写 `backend/tests/test_risk_assessment.py`：测试组合风险自动计算（风险矩阵9种组合）、特别风险必须有应对策略、风险-程序覆盖矩阵
    - _需求: 11.6, 11.7, 11.10_
  - [ ] 29.2 编写 `backend/tests/test_management_letter.py`：测试管理建议书跨年结转（未解决事项结转+prior_year_item_id+follow_up_status）
    - _需求: 11.9_
  - [ ]* 29.3 编写属性测试：风险评估组合风险自动计算
    - **Property 19: 风险评估组合风险自动计算**
    - 使用 Hypothesis 生成随机 inherent_risk+control_risk 组合，验证 combined_risk 符合风险矩阵
    - **验证: 需求 11.7**
  - [ ]* 29.4 编写属性测试：特别风险必须有应对策略
    - **Property 20: 特别风险必须有应对策略**
    - 使用 Hypothesis 生成随机风险评估记录，验证 is_significant_risk=true 时 response_strategy 非空
    - **验证: 需求 11.6**

- [ ] 30. 最终检查点 — 全量测试通过
  - 运行全部单元测试和属性测试，确保所有测试通过。如有问题请询问用户。
