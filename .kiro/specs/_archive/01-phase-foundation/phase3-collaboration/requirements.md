# 需求文档：第三阶段协作与质控 — 多用户权限+三级复核+期后事项+版本控制+项目看板+函证管理+审计档案归档

## 简介

本文档定义审计作业平台第三阶段协作与质控功能的需求。在第一阶段单户审计MVP和第二阶段集团合并基础上，叠加多人协作和质量管理能力。涵盖七大核心模块：多用户权限与项目隔离（六种角色+权限矩阵+按循环分工）、三级复核流程（编制→一级复核→二级复核+项目状态管理）、期后事项管理（期后事项记录+审阅程序清单+与调整分录/附注联动）、版本控制与私有云同步（全局版本号+冲突检测+离线协作）、项目管理看板（进度跟踪+风险预警+工时管理）、函证管理（函证清单+询证函生成+回函跟踪+统计表）、审计档案归档（归档检查清单+电子档案导出+10年保存期）。本阶段依赖Phase 0/1/2已实现的基础设施、试算表、调整分录、底稿、报表、合并等模块。

## 术语表

- **Platform（审计作业平台）**：面向会计师事务所的本地私有化审计全流程作业系统
- **Admin（管理员）**：系统管理员，负责用户管理、系统配置
- **Partner（签字合伙人）**：对审计报告承担最终签字责任的合伙人，执行二级复核
- **Manager（项目经理）**：负责项目管理、执行一级复核的项目负责人
- **Auditor（审计员）**：执行审计程序、编制底稿的项目组成员
- **QC_Reviewer（质控部）**：独立于项目组的质量控制人员，可查看所有项目但不可编辑
- **ReadOnly（只读用户）**：仅有查看权限的用户
- **Review_Record（复核记录）**：记录复核意见、处理状态、回复内容的数据，存储于`review_records`表
- **Project_Status（项目状态）**：项目生命周期阶段，包括创建→计划→执行→完成→报告→归档锁定
- **Subsequent_Event（期后事项）**：资产负债表日至审计报告日之间发生的重大事项，分为调整事项和非调整事项
- **SE_Checklist（期后事项审阅程序清单）**：审计师执行期后事项审阅的标准程序清单
- **Sync_Version（同步版本）**：项目级版本控制的版本号，用于私有云同步和离线协作的冲突检测
- **Confirmation（函证）**：审计师直接向第三方发函确认信息的审计程序
- **Confirmation_Center（函证中心）**：事务所统一管控函证发送和接收的部门
- **Archive（审计档案）**：审计项目完成后归档的全部审计工作底稿和报告
- **Archive_Checklist（归档检查清单）**：确认归档内容完整性的检查清单
- **Notification（通知）**：系统内消息通知，存储于`notifications`表
- **PBC_Checklist（审计资料需求清单）**：向被审计单位发出的资料需求清单
- **Going_Concern（持续经营评价）**：评估被审计单位持续经营假设适当性的审计程序
- **Project_Dashboard（项目看板）**：展示项目进度、风险预警、人员工时的管理视图

## 需求

### 需求 1：多用户权限与项目隔离

**用户故事：** 作为管理员，我希望能管理系统用户和角色权限，实现项目级数据隔离和按审计循环分工，以便多人安全高效地协作完成审计项目。

#### 验收标准

1. THE Platform SHALL support six user roles stored in the `users` table: admin, partner, manager, auditor, qc_reviewer, readonly; each user record containing: id (UUID PK), username (varchar unique), password_hash (varchar), display_name (varchar), role (enum), office_code (varchar, nullable), email (varchar, nullable), is_active (boolean default true), is_deleted (boolean default false), created_at, updated_at
2. THE Platform SHALL enforce project-level data isolation through the `project_users` table with fields: id (UUID PK), project_id (UUID FK), user_id (UUID FK), project_role (enum: partner/manager/auditor/qc_reviewer/readonly), assigned_cycles (jsonb, array of audit cycle codes the user is responsible for), assigned_account_ranges (jsonb, array of account code ranges), valid_from (date), valid_to (date, nullable), is_deleted (boolean default false), created_at, updated_at; with composite unique index on (project_id, user_id)
3. THE Platform SHALL enforce the permission matrix: admin and partner can create projects; admin, partner, and manager can assign project members; only auditor and manager can edit working papers within their assigned cycle scope; only manager and partner can perform level-1 review; only partner can perform level-2 review and sign audit reports; qc_reviewer can view all projects but cannot edit any data
4. WHEN Auditor attempts to edit a working paper or adjustment entry outside the assigned_cycles or assigned_account_ranges, THE Platform SHALL reject the operation and return an error message specifying the permission boundary
5. THE Platform SHALL record all write operations in the `logs` table with fields: id (UUID PK), project_id (UUID FK nullable), user_id (UUID FK), operation_type (enum: create/update/delete/review/archive/login/logout), object_type (varchar), object_id (varchar), old_value (jsonb, nullable), new_value (jsonb, nullable), ip_address (varchar), created_at; with composite index on (project_id, created_at)
6. THE Platform SHALL implement JWT-based authentication with 2-hour token expiry, refresh token support, and account lockout after 5 consecutive failed login attempts for 30 minutes
7. WHEN Admin creates or modifies a user, THE Platform SHALL validate that username is unique, password meets minimum complexity requirements (at least 8 characters with mixed case and digits), and role is a valid enum value

### 需求 2：三级复核流程

**用户故事：** 作为项目经理，我希望系统支持编制→一级复核→二级复核的三级复核流程，以便确保审计底稿质量符合质量管理准则要求。

#### 验收标准

1. THE Platform SHALL extend the `review_records` table (defined in Phase 1) with additional fields to support three-level review: id (UUID PK), project_id (UUID FK), reviewer_id (UUID FK to users), review_level (enum: level_1/level_2), object_type (enum: working_paper/adjustment/report/subsequent_event/confirmation), object_id (UUID), review_opinion (text, not null), review_result (enum: approved/rejected/needs_revision), response_content (text, nullable, preparer's response), response_by (UUID FK nullable), response_at (timestamp nullable), is_resolved (boolean default false), is_deleted (boolean default false), created_at, updated_at
2. THE Platform SHALL enforce the working paper status flow: draft → prepared → level_1_approved → level_2_approved → archived; WHEN a reviewer rejects, THE Platform SHALL revert the status to "draft" and require the preparer to address all review comments before resubmitting
3. WHEN Manager submits a level-1 review with review_result="rejected", THE Platform SHALL require a non-empty review_opinion text and notify the preparer via the notification system
4. THE Platform SHALL enforce that critical working papers (revenue, receivables, inventory, long-term investments, consolidation) must pass level-2 review by Partner before the project can enter the "report" phase
5. WHEN Auditor responds to a review comment, THE Platform SHALL record the response_content, response_by, and response_at, and notify the reviewer; the reviewer must mark the comment as is_resolved=true before the working paper can be resubmitted for review
6. THE Platform SHALL track review timeliness: record the timestamp of each review action and calculate the elapsed time between submission and review completion, making this data available for QC_Reviewer inspection
7. THE Platform SHALL enforce project status transitions with gate conditions: created→planning (project created, members assigned), planning→execution (audit plan prepared, materiality determined, account mapping completed), execution→completion (all working papers status ≥ prepared, quality self-check passed, adjustments entered, confirmations completed), completion→reporting (all working papers passed level-1 review, unadjusted misstatements evaluated, trial balance balanced, subsequent events review completed, going concern evaluation completed), reporting→archived (critical working papers passed level-2 review, audit report signed, management letter issued), archived requires archive checklist fully completed within 60 days of report date
8. WHEN a project enters "archived" status, THE Platform SHALL lock all project data (working papers, adjustments, eliminations, reports) as read-only; any post-archive modification requires a special approval workflow recording: modification_reason (text), approved_by (UUID FK), approval_date, and preserving before/after comparison

### 需求 3：期后事项管理

**用户故事：** 作为审计员，我希望能记录和跟踪资产负债表日至审计报告日之间的期后事项，并将调整事项关联到调整分录、非调整事项关联到附注披露，以便满足CSA 1501的审计准则要求。

#### 验收标准

1. THE Platform SHALL provide a subsequent events management interface using the `subsequent_events` table with fields: id (UUID PK), project_id (UUID FK), event_type (enum: adjusting/non_adjusting), discovery_date (date, not null), event_description (text, not null), affected_accounts (jsonb, array of account codes), impact_amount (numeric(20,2), nullable), treatment (enum: adjusted/disclosed/no_action_needed), related_adjustment_id (UUID FK to adjustments, nullable), related_note_section (varchar, nullable, reference to disclosure note section), identified_by (UUID FK to users), review_status (enum: draft/pending_review/approved/rejected, default draft), is_deleted (boolean default false), created_at, updated_at
2. WHEN Auditor records an adjusting subsequent event (event_type="adjusting") with treatment="adjusted", THE Platform SHALL require a non-null related_adjustment_id linking to an existing adjustment entry, and display the linked adjustment details in the subsequent event view
3. WHEN Auditor records a non-adjusting subsequent event (event_type="non_adjusting") with treatment="disclosed", THE Platform SHALL require a non-null related_note_section indicating which disclosure note section covers this event
4. THE Platform SHALL provide a subsequent events review checklist using the `subsequent_events_checklist` table with fields: id (UUID PK), project_id (UUID FK), procedure_name (varchar, not null), procedure_description (text), execution_status (enum: not_started/in_progress/completed/not_applicable), executed_by (UUID FK to users, nullable), executed_at (date, nullable), findings_summary (text, nullable), is_deleted (boolean default false), created_at, updated_at
5. THE Platform SHALL pre-populate the subsequent events checklist with standard review procedures when a project is created: review post-period bank statements, review post-period board meeting minutes, review post-period litigation developments, inquire management about subsequent events, review post-period significant contracts, review post-period tax assessments
6. WHEN the project attempts to transition from "completion" to "reporting" phase, THE Platform SHALL verify that all subsequent events checklist items have execution_status of "completed" or "not_applicable", blocking the transition if any item remains "not_started" or "in_progress"
7. THE Platform SHALL support linking subsequent events to prior year data: WHEN creating a new year project, THE Platform SHALL carry forward non-adjusting events from the prior year as reference items with a flag indicating they require follow-up assessment

### 需求 4：版本控制与私有云同步

**用户故事：** 作为项目经理，我希望系统支持版本控制和私有云同步，以便团队成员在内网和客户现场都能安全地协作编辑项目数据。

#### 验收标准

1. THE Platform SHALL maintain project-level version control using the `project_sync` table with fields: id (UUID PK), project_id (UUID FK, unique), local_version (integer, default 0), cloud_version (integer, default 0), last_sync_time (timestamp, nullable), last_sync_by (UUID FK to users, nullable), sync_status (enum: idle/syncing/conflict/error, default idle), is_deleted (boolean default false), created_at, updated_at
2. THE Platform SHALL enforce sync validation rules: WHEN local_version < cloud_version, THE Platform SHALL block upload and require the user to pull the latest version first; WHEN local_version == cloud_version, THE Platform SHALL allow upload and increment both versions by 1; WHEN local_version > cloud_version, THE Platform SHALL flag a conflict and enter the merge workflow
3. THE Platform SHALL support conflict resolution strategies: different working papers (different account cycles) auto-merge without conflict; same adjustment entry conflict shows diff view for user to choose (keep local / keep cloud / manual merge); same working paper cell conflict keeps the most recently modified version and marks a conflict flag
4. THE Platform SHALL enforce immutability rules: original imported account data cannot be overwritten (append-only with import batch tracking); approved adjustment entries cannot be overwritten (must reverse and re-create); working papers that have passed review cannot be directly modified (must be returned to draft status first)
5. THE Platform SHALL support offline collaboration through template export/import: export project data as standardized Excel/JSON packages containing project_id, year, company_code, export_version, export_time; import with automatic validation of project existence, year matching, account validity, debit-credit balance, and version staleness
6. THE Platform SHALL generate a sync log for every synchronization operation recording: sync_user, sync_time, version_before, version_after, change_summary (text), backup_file_path (varchar), stored in the `sync_logs` table with fields: id (UUID PK), project_id (UUID FK), sync_user_id (UUID FK), sync_time (timestamp), version_before (integer), version_after (integer), sync_direction (enum: upload/download/merge), change_summary (text), backup_file_path (varchar, nullable), is_deleted (boolean default false), created_at
7. THE Platform SHALL support private cloud sync via WebDAV or NAS protocol: sync at project folder granularity, incremental sync based on file modification timestamps, VPN-compatible for field audit scenarios where auditors work at client sites

### 需求 5：项目管理看板

**用户故事：** 作为合伙人，我希望能通过项目看板查看所有负责项目的进度、风险预警和人员工时，以便及时发现和处理项目风险。

#### 验收标准

1. THE Platform SHALL provide a project dashboard view accessible to admin, partner, manager, and qc_reviewer roles, displaying: project progress (current phase, working paper completion rate, review completion rate, estimated completion date), risk alerts (overdue projects, unadjusted misstatements exceeding materiality, critical working papers not reviewed), personnel workload (projects per auditor, hours invested, task assignments), and report status (pending reports, issued reports, archived projects)
2. THE Platform SHALL manage project timeline milestones using the `project_timelines` table with fields: id (UUID PK), project_id (UUID FK), milestone_type (enum: plan_start/field_entry/field_exit/report_date/archive_deadline), planned_date (date), actual_date (date, nullable), notes (text, nullable), is_deleted (boolean default false), created_at, updated_at; with composite unique index on (project_id, milestone_type)
3. THE Platform SHALL automatically calculate the archive_deadline as report_date + 60 days, and display remaining days for each milestone; WHEN remaining days ≤ 15 for archive_deadline, THE Platform SHALL highlight the project in red on the dashboard and send a notification to the manager and partner
4. THE Platform SHALL support work hour tracking using the `workhours` table with fields: id (UUID PK), project_id (UUID FK), user_id (UUID FK), work_date (date, not null), hours (numeric(4,1), not null, range 0.5-24), work_description (text), audit_cycle (varchar, nullable), is_deleted (boolean default false), created_at, updated_at; with composite index on (project_id, user_id, work_date)
5. THE Platform SHALL support budget hour management using the `budget_hours` table with fields: id (UUID PK), project_id (UUID FK), role_type (enum: partner/manager/auditor), budget_hours (numeric(8,1)), actual_hours (numeric(8,1), default 0, auto-calculated from workhours), is_deleted (boolean default false), created_at, updated_at; WHEN actual_hours exceeds budget_hours, THE Platform SHALL display a warning indicator on the dashboard
6. THE Platform SHALL provide a PBC checklist management interface using the `pbc_checklist` table with fields: id (UUID PK), project_id (UUID FK), item_name (varchar, not null), audit_cycle (varchar), requested_from (varchar, the party who should provide the document), due_date (date), received_status (enum: not_received/received/overdue), received_date (date, nullable), notes (text, nullable), is_deleted (boolean default false), created_at, updated_at; with composite index on (project_id, audit_cycle)

### 需求 6：通知与提醒机制

**用户故事：** 作为项目组成员，我希望在复核待办、超期预警、同步冲突等关键事件发生时收到系统通知，以便及时响应和处理。

#### 验收标准

1. THE Platform SHALL store notifications in the `notifications` table with fields: id (UUID PK), recipient_id (UUID FK to users), notification_type (enum: review_pending/review_response/overdue_warning/misstatement_alert/sync_conflict/ai_complete/import_complete/confirmation_overdue), title (varchar, not null), content (text, not null), related_object_type (varchar, nullable), related_object_id (UUID, nullable), is_read (boolean default false), created_at
2. WHEN a working paper is submitted for review, THE Platform SHALL create a notification with type="review_pending" for the designated reviewer, including the working paper name and submitter information in the content
3. WHEN the cumulative unadjusted misstatements amount reaches or exceeds the overall materiality level, THE Platform SHALL create a notification with type="misstatement_alert" for the project manager and partner
4. WHEN a confirmation has been sent for more than 30 days without a reply, THE Platform SHALL create a notification with type="confirmation_overdue" for the project manager
5. THE Platform SHALL provide a notification center API: GET /api/notifications (list with pagination and filter by type/read status), PUT /api/notifications/{id}/read (mark as read), PUT /api/notifications/read-all (mark all as read), GET /api/notifications/unread-count (badge count)
6. THE Platform SHALL implement notification delivery via polling in MVP phase (frontend polls /api/notifications/unread-count every 30 seconds), with WebSocket real-time push reserved for the production phase

### 需求 7：函证管理

**用户故事：** 作为审计员，我希望能编制函证清单、生成询证函、跟踪回函状态并生成函证统计表，以便完整记录函证审计程序的执行过程。

#### 验收标准

1. THE Platform SHALL provide a confirmation list management interface using the `confirmation_list` table with fields: id (UUID PK), project_id (UUID FK), confirmation_no (varchar, auto-generated format "CF-{type_code}-{seq}", e.g. CF-BK-001 for bank), confirmation_type (enum: bank/receivable/payable/lawyer/other), counterparty_name (varchar, not null), account_code (varchar), book_amount (numeric(20,2)), cutoff_date (date), approval_status (enum: draft/approved/submitted_to_center), approved_by (UUID FK nullable), submitted_at (timestamp nullable), is_deleted (boolean default false), created_at, updated_at; with composite index on (project_id, confirmation_type)
2. THE Platform SHALL auto-extract confirmation candidates from the trial balance: for bank confirmations, extract all bank deposit accounts; for receivable confirmations, extract accounts receivable by customer from auxiliary balance; for payable confirmations, extract accounts payable by supplier; Auditor can manually add or remove candidates from the list
3. WHEN Manager approves the confirmation list (approval_status changes to "approved"), THE Platform SHALL generate confirmation letters using the `confirmation_letter` table with fields: id (UUID PK), confirmation_list_id (UUID FK), template_type (enum: bank/receivable/payable/lawyer), generated_at (timestamp), letter_file_path (varchar, path to generated PDF/Excel), is_deleted (boolean default false), created_at; auto-filling: auditee name, counterparty name, confirmation amount, cutoff date, project reference number
4. THE Platform SHALL track confirmation results using the `confirmation_result` table with fields: id (UUID PK), confirmation_list_id (UUID FK), reply_date (date, nullable), reply_status (enum: confirmed_match/confirmed_mismatch/no_reply/returned), confirmed_amount (numeric(20,2), nullable), difference_amount (numeric(20,2), nullable, calculated as book_amount - confirmed_amount), difference_reason (text, nullable), needs_adjustment (boolean default false), alternative_procedure (text, nullable, for no_reply items), alternative_conclusion (text, nullable), is_deleted (boolean default false), created_at, updated_at
5. THE Platform SHALL automatically calculate difference_amount when confirmed_amount is entered; WHEN reply_status is "no_reply" or "returned", THE Platform SHALL require alternative_procedure and alternative_conclusion to be filled before the confirmation can be marked as complete
6. THE Platform SHALL generate confirmation summary statistics using the `confirmation_summary` table with fields: id (UUID PK), project_id (UUID FK), confirmation_type (enum), total_count (integer), replied_count (integer), no_reply_count (integer), reply_rate (numeric(5,2), calculated), total_amount (numeric(20,2)), matched_amount (numeric(20,2)), difference_amount (numeric(20,2)), coverage_rate (numeric(5,2), total_amount / account balance), needs_adjustment_amount (numeric(20,2)), is_deleted (boolean default false), created_at, updated_at; auto-calculated when confirmation results are updated
7. THE Platform SHALL store confirmation attachments (reply scans) using the `confirmation_attachment` table with fields: id (UUID PK), confirmation_list_id (UUID FK), file_path (varchar), file_name (varchar), uploaded_at (timestamp), uploaded_by (UUID FK), is_deleted (boolean default false), created_at

### 需求 8：审计档案归档

**用户故事：** 作为项目经理，我希望系统能自动生成归档检查清单并支持电子档案导出，以便在审计报告日后60天内完成归档，满足审计准则对10年保存期的要求。

#### 验收标准

1. THE Platform SHALL provide an archive checklist interface that auto-generates a checklist when the project enters "reporting" phase, containing the following mandatory items: audit plan and risk assessment working papers, materiality determination working paper, all cycle working papers (with index), adjustment entries summary (AJE + RJE), unadjusted misstatements summary, trial balance (unaudited → audited), financial statements (individual/consolidated), notes to financial statements, audit report, management letter, review records, confirmation working papers, subsequent events review working papers (including checklist and event records), going concern evaluation working papers, sampling records, quality self-check report; each item tracked with completion status (boolean) and responsible person
2. WHEN the project attempts to transition to "archived" status, THE Platform SHALL verify that all archive checklist items are marked as complete; IF any item is incomplete, THEN THE Platform SHALL block the archival and display the list of incomplete items
3. THE Platform SHALL support electronic archive export: export the complete project archive as a single PDF package organized by working paper index number, with an auto-generated table of contents page, GT brand elements on cover page (GT purple title bar, firm logo, project information watermark), page headers/footers per GT design specification
4. THE Platform SHALL enforce archive integrity: archived projects are fully read-only; post-archive modifications require a special approval record in the `archive_modifications` table with fields: id (UUID PK), project_id (UUID FK), modification_reason (text, not null), modification_description (text, not null), approved_by (UUID FK to users), approval_date (date), modifier_id (UUID FK to users), modified_at (timestamp), old_value (jsonb), new_value (jsonb), is_deleted (boolean default false), created_at
5. THE Platform SHALL track archive retention: record the archive_date (report_date + actual archive completion date) and calculate the retention_expiry_date as archive_date + 10 years; THE Platform SHALL prevent deletion of any archived project data before the retention_expiry_date
6. THE Platform SHALL support encrypted PDF export with password protection for electronic archives, and preserve cross-reference hyperlinks within the exported PDF (clicking a reference jumps to the linked working paper page)

### 需求 9：持续经营评价

**用户故事：** 作为审计员，我希望系统能支持持续经营评价流程，包括风险指标检查和评价结论记录，以便满足CSA 1324的审计准则要求并与审计报告联动。

#### 验收标准

1. THE Platform SHALL provide a going concern evaluation interface using the `going_concern` table with fields: id (UUID PK), project_id (UUID FK), evaluation_date (date, not null), management_assessment_summary (text), identified_concerns (text, nullable), management_response_plan (text, nullable), auditor_evaluation (text), conclusion_type (enum: no_significant_doubt/material_uncertainty/going_concern_inappropriate), impact_on_report (text, describing the impact on audit report type), review_status (enum: draft/pending_review/approved/rejected, default draft), is_deleted (boolean default false), created_at, updated_at
2. THE Platform SHALL provide a going concern indicators checklist using the `going_concern_indicators` table with fields: id (UUID PK), project_id (UUID FK), indicator_category (enum: financial/operational/other), indicator_name (varchar, not null), indicator_status (enum: present/absent/not_applicable), evaluation_notes (text, nullable), is_deleted (boolean default false), created_at, updated_at
3. THE Platform SHALL pre-populate the going concern indicators checklist when a project is created, including standard financial indicators (recurring operating losses, negative operating cash flows, working capital deficiency, inability to pay debts when due, inability to comply with loan covenants), operational indicators (loss of key management, loss of major market/customer/supplier, labor difficulties), and other indicators (pending litigation with potentially adverse outcomes, changes in legislation or government policy)
4. WHEN the going concern conclusion_type is "material_uncertainty", THE Platform SHALL create a notification to the partner indicating that the audit report must include a "Material Uncertainty Related to Going Concern" paragraph
5. WHEN the going concern conclusion_type is "going_concern_inappropriate", THE Platform SHALL create a notification to the partner indicating that an adverse opinion should be considered

### 需求 10：数据表Schema定义（第三阶段协作表）

**用户故事：** 作为开发者，我希望第三阶段协作相关数据表的Schema明确定义，以便通过Alembic迁移脚本创建表结构。

#### 验收标准

1. THE Migration_Framework SHALL create the `users` table with columns as defined in Requirement 1.1, with unique index on (username) and index on (role, is_active)
2. THE Migration_Framework SHALL create the `project_users` table with columns as defined in Requirement 1.2, with composite unique index on (project_id, user_id) and index on (project_id, project_role)
3. THE Migration_Framework SHALL create the `logs` table with columns as defined in Requirement 1.5, with composite index on (project_id, created_at) and index on (user_id, created_at)
4. THE Migration_Framework SHALL extend the `review_records` table with columns as defined in Requirement 2.1, with composite index on (project_id, object_type, object_id) and index on (reviewer_id, created_at)
5. THE Migration_Framework SHALL create the `subsequent_events` table with columns as defined in Requirement 3.1, with composite index on (project_id, event_type) and index on (project_id, review_status)
6. THE Migration_Framework SHALL create the `subsequent_events_checklist` table with columns as defined in Requirement 3.4, with index on (project_id, execution_status)
7. THE Migration_Framework SHALL create the `project_sync` table with columns as defined in Requirement 4.1, with unique index on (project_id)
8. THE Migration_Framework SHALL create the `sync_logs` table with columns as defined in Requirement 4.6, with composite index on (project_id, sync_time)
9. THE Migration_Framework SHALL create the `project_timelines` table with columns as defined in Requirement 5.2, with composite unique index on (project_id, milestone_type)
10. THE Migration_Framework SHALL create the `workhours` table with columns as defined in Requirement 5.4, with composite index on (project_id, user_id, work_date)
11. THE Migration_Framework SHALL create the `budget_hours` table with columns as defined in Requirement 5.5, with composite index on (project_id, role_type)
12. THE Migration_Framework SHALL create the `pbc_checklist` table with columns as defined in Requirement 5.6, with composite index on (project_id, audit_cycle)
13. THE Migration_Framework SHALL create the `notifications` table with columns as defined in Requirement 6.1, with composite index on (recipient_id, is_read, created_at)
14. THE Migration_Framework SHALL create the `confirmation_list` table with columns as defined in Requirement 7.1, with composite index on (project_id, confirmation_type)
15. THE Migration_Framework SHALL create the `confirmation_letter` table with columns as defined in Requirement 7.3, with index on (confirmation_list_id)
16. THE Migration_Framework SHALL create the `confirmation_result` table with columns as defined in Requirement 7.4, with index on (confirmation_list_id)
17. THE Migration_Framework SHALL create the `confirmation_summary` table with columns as defined in Requirement 7.6, with composite unique index on (project_id, confirmation_type)
18. THE Migration_Framework SHALL create the `confirmation_attachment` table with columns as defined in Requirement 7.7, with index on (confirmation_list_id)
19. THE Migration_Framework SHALL create the `going_concern` table with columns as defined in Requirement 9.1, with unique index on (project_id) where is_deleted=false
20. THE Migration_Framework SHALL create the `going_concern_indicators` table with columns as defined in Requirement 9.2, with composite index on (project_id, indicator_category)
21. THE Migration_Framework SHALL create the `archive_modifications` table with columns as defined in Requirement 8.4, with index on (project_id, created_at)


### 需求 11：审计程序与风险管理

**用户故事：** 作为项目经理，我希望系统能支持风险评估表编制、审计计划管理、审计程序清单跟踪、审计发现记录和管理建议书事项管理，以便完整覆盖审计的"前端"流程（了解被审计单位→风险评估→制定审计计划→执行审计程序→形成结论）。

#### 验收标准

1. THE Platform SHALL provide a risk assessment interface using the `risk_assessment` table with fields: `id` (UUID PK), `project_id` (UUID FK to projects), `assertion_level` (enum: existence/completeness/accuracy/cutoff/classification/occurrence/rights_obligations/valuation, not null), `account_or_cycle` (varchar, not null, the account or audit cycle being assessed), `inherent_risk` (enum: high/medium/low, not null), `control_risk` (enum: high/medium/low, not null), `combined_risk` (enum: high/medium/low, auto-calculated), `is_significant_risk` (boolean, default false), `risk_description` (text), `response_strategy` (text, the planned audit response), `related_audit_procedures` (jsonb, array of audit_procedure IDs), `review_status` (enum: draft/pending_review/approved/rejected, default draft), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users); with composite index on (project_id, account_or_cycle)
2. THE Platform SHALL provide an audit plan interface using the `audit_plan` table with fields: `id` (UUID PK), `project_id` (UUID FK to projects), `plan_version` (integer, default 1), `audit_strategy` (text, overall audit strategy description), `planned_start_date` (date), `planned_end_date` (date), `key_focus_areas` (jsonb, array of focus area descriptions), `team_assignment_summary` (jsonb, summary of team roles and responsibilities), `materiality_reference` (text, reference to materiality determination), `status` (enum: draft/approved/revised, default draft), `approved_by` (UUID FK to users, nullable), `approved_at` (timestamp, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users); with unique index on (project_id) where is_deleted=false
3. THE Platform SHALL provide an audit procedures checklist using the `audit_procedures` table with fields: `id` (UUID PK), `project_id` (UUID FK to projects), `procedure_code` (varchar, not null, e.g. "RA-01", "CT-01", "SP-01"), `procedure_name` (varchar, not null), `procedure_type` (enum: risk_assessment/control_test/substantive, not null), `audit_cycle` (varchar), `account_code` (varchar, nullable), `description` (text), `execution_status` (enum: not_started/in_progress/completed/not_applicable, default not_started), `executed_by` (UUID FK to users, nullable), `executed_at` (date, nullable), `conclusion` (text, nullable), `related_wp_code` (varchar, nullable, linked working paper code), `related_risk_id` (UUID FK to risk_assessment, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite index on (project_id, procedure_type) and index on (project_id, audit_cycle)
4. THE Platform SHALL provide an audit findings interface using the `audit_findings` table with fields: `id` (UUID PK), `project_id` (UUID FK to projects), `finding_code` (varchar, auto-generated), `finding_description` (text, not null), `severity` (enum: high/medium/low, not null), `affected_account` (varchar, nullable), `finding_amount` (numeric(20,2), nullable), `management_response` (text, nullable), `final_treatment` (enum: adjusted/unadjusted/disclosed/no_action, nullable), `related_adjustment_id` (UUID FK to adjustments, nullable), `related_wp_code` (varchar, nullable), `identified_by` (UUID FK to users), `review_status` (enum: draft/pending_review/approved/rejected, default draft), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite index on (project_id, severity)
5. THE Platform SHALL provide a management letter items interface using the `management_letter` table with fields: `id` (UUID PK), `project_id` (UUID FK to projects), `item_code` (varchar, auto-generated, e.g. "ML-001"), `deficiency_type` (enum: significant_deficiency/material_weakness/other_deficiency, not null), `deficiency_description` (text, not null), `potential_impact` (text), `recommendation` (text, not null), `management_response` (text, nullable), `response_deadline` (date, nullable), `prior_year_item_id` (UUID FK to management_letter, nullable, for tracking prior year items), `follow_up_status` (enum: new/in_progress/resolved/carried_forward, default new), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users); with composite index on (project_id, deficiency_type)
6. WHEN Manager creates a risk assessment with is_significant_risk=true, THE Platform SHALL require a non-empty response_strategy describing the specific audit procedures planned to address the significant risk
7. THE Platform SHALL auto-calculate combined_risk based on inherent_risk and control_risk using the risk matrix: (high, high)→high, (high, medium)→high, (high, low)→medium, (medium, high)→high, (medium, medium)→medium, (medium, low)→low, (low, high)→medium, (low, medium)→low, (low, low)→low
8. THE Platform SHALL support linking audit procedures to risk assessments (related_risk_id) and working papers (related_wp_code), enabling traceability from identified risks through planned procedures to executed working papers
9. THE Platform SHALL support management letter item tracking across years: WHEN creating a new year project, THE Platform SHALL carry forward unresolved management letter items from the prior year with follow_up_status="carried_forward" and prior_year_item_id referencing the original item
10. THE Platform SHALL provide a risk-procedure coverage matrix view showing: each identified risk (rows) × planned audit procedures (columns), with indicators showing which procedures address which risks, highlighting any risks without corresponding procedures

### 需求 12：审计程序与风险管理数据表Schema定义

**用户故事：** 作为开发者，我希望审计程序与风险管理相关数据表的Schema明确定义，以便通过Alembic迁移脚本创建表结构。

#### 验收标准

1. THE Migration_Framework SHALL create the `risk_assessment` table with columns as defined in Requirement 11.1, with composite index on (project_id, account_or_cycle)
2. THE Migration_Framework SHALL create the `audit_plan` table with columns as defined in Requirement 11.2, with unique index on (project_id) where is_deleted=false
3. THE Migration_Framework SHALL create the `audit_procedures` table with columns as defined in Requirement 11.3, with composite index on (project_id, procedure_type) and index on (project_id, audit_cycle)
4. THE Migration_Framework SHALL create the `audit_findings` table with columns as defined in Requirement 11.4, with composite index on (project_id, severity)
5. THE Migration_Framework SHALL create the `management_letter` table with columns as defined in Requirement 11.5, with composite index on (project_id, deficiency_type)
