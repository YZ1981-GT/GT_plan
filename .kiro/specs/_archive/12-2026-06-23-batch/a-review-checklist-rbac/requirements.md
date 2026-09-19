# Requirements Document

## Introduction

A21~A25 五级复核表是审计质量控制的核心链路，当前使用 `review-checklist` componentType（GtReviewChecklist.vue）统一渲染。现存核心缺陷：任何用户均可填写任何级别的复核表，无角色权限控制。

本功能将实现：
1. 基于 `project_assignments` 表的角色权限绑定，非本级角色用户只读
2. 逐级前置校验（下级未签字则上级不可开始）
3. 签字后锁定（签字完成即永久只读，合伙人可解锁）
4. A1 dashboard 五级复核状态看板
5. 未清复核意见计数器（阻止带未清意见签字）

角色映射关系：
- A21 → senior（项目中被分配为"现场负责人"的 staff）
- A22 → manager（经理）
- A23 → signing_partner（合伙人）
- A24 → qc（质控复核合伙人）
- A25 → eqcr（EQCR 技术复核人）

## Glossary

- **Review_RBAC_Guard**: 后端权限校验逻辑，在 render-config 和 review-sign 端点中根据当前用户角色决定 readonly 状态
- **Required_Role**: 复核表级别对应的 `project_assignments.role` 值，定义 A21~A25 与 AssignmentRole 的映射
- **Sequential_Gate**: 逐级前置检查逻辑，验证下级复核已签字后才允许上级复核表可编辑
- **Sign_Lock**: 签字后锁定机制，复核表签字 conclusion=pass 后该表变为永久只读
- **Unlock_Action**: 合伙人（signing_partner）专属操作，可撤销已签字的复核表锁定状态
- **Unresolved_Count**: 当前复核表关联的复核意见中尚未清零（conclusion 非 Y/NA）的条数
- **Review_Dashboard**: A1 dashboard 中展示五级复核状态的卡片区域，显示各级签字进度
- **checklist_responses**: 持久化表，存储复核检查项的勾选状态和签字记录（item_id=`{wp_code}-sign`）

## Requirements

### Requirement 1: 角色权限只读控制

**User Story:** As a 现场经理, I want only the designated reviewer for each level to be able to edit the corresponding review checklist, so that review responsibilities are clearly separated and audit trail integrity is maintained.

#### Acceptance Criteria

1. WHEN a user opens a review checklist (A21~A25), THE Review_RBAC_Guard SHALL query `project_assignments` to determine if the current user's staff_id matches a record with the Required_Role for that review level.
2. WHEN the user does NOT have the Required_Role for the review level, THE render-config endpoint SHALL return `readonly: true` in the sheet's html_data, causing GtReviewChecklist to disable all input controls.
3. WHEN the user has the Required_Role for the review level, THE render-config endpoint SHALL return `readonly: false`, allowing full editing of the checklist.
4. THE Review_RBAC_Guard SHALL use the following role mapping: A21 → ["senior", "auditor"], A22 → ["manager"], A23 → ["signing_partner"], A24 → ["qc"], A25 → ["eqcr"].
5. WHEN a user without the Required_Role attempts to POST to the review-sign endpoint, THE system SHALL return HTTP 403 with detail "无权签署此级别复核表".
6. WHEN a user without the Required_Role attempts to PUT checklist-responses for a review checklist, THE system SHALL return HTTP 403 with detail "无权编辑此级别复核表".
7. THE Review_RBAC_Guard SHALL resolve user→staff mapping via `staff_members.user_id = current_user.id`, then check `project_assignments` for the matching project_id and role.

### Requirement 2: 逐级前置校验

**User Story:** As a 业务合伙人, I want to ensure lower-level reviews are completed before I can start my review, so that the review chain follows proper quality control hierarchy per CAS 1220.

#### Acceptance Criteria

1. THE Sequential_Gate SHALL enforce the following dependency chain: A22 requires A21 signed, A23 requires A22 signed, A24 requires A23 signed, A25 requires A24 signed.
2. WHEN a user opens a review checklist whose prerequisite level has NOT been signed (conclusion != 'pass'), THE system SHALL return `readonly: true` with a `gate_reason` field explaining which prior level must be completed first.
3. WHEN the prerequisite level's sign status transitions to 'pass', THE Sequential_Gate SHALL allow the next level's checklist to become editable (readonly: false) on next render-config request.
4. THE A21 level (现场负责人复核) SHALL have no prerequisite and be always editable for authorized users.
5. WHEN both -1 (财报审计) and -2 (内控审计) variants exist for a level, THE Sequential_Gate SHALL check the corresponding variant: A22-1 requires A21-1 signed, A22-2 requires A21-2 signed.
6. IF a signed lower-level review is subsequently unlocked (sign removed), THEN THE Sequential_Gate SHALL revert all dependent higher-level checklists to readonly state.

### Requirement 3: 签字后锁定

**User Story:** As a 质量控制复核合伙人, I want a signed review checklist to become permanently readonly, so that the audit trail cannot be tampered with after formal sign-off.

#### Acceptance Criteria

1. WHEN a reviewer signs a checklist with action='pass', THE Sign_Lock SHALL mark the checklist as permanently readonly for all users including the original signer.
2. WHEN a locked checklist is opened via render-config, THE system SHALL return `readonly: true` and `locked: true` and `signed_by` (signer name) and `signed_at` (ISO timestamp) in the response.
3. THE GtReviewChecklist component SHALL display a lock banner showing "已由 {signer_name} 于 {date} 签字锁定" when `locked: true`.
4. WHEN a user with role 'signing_partner' requests unlock on a signed checklist, THE Unlock_Action SHALL remove the sign record from checklist_responses and restore the checklist to editable state.
5. THE Unlock_Action endpoint SHALL be `POST /api/workpapers/{wp_id}/review-unlock` accepting `{ project_id, wp_code, reason }`.
6. WHEN unlock is performed, THE system SHALL log the unlock event including: who unlocked, when, and the stated reason, to an audit trail (stored as a checklist_response with item_id=`{wp_code}-unlock-log`).
7. IF a non-partner user attempts the Unlock_Action, THEN THE system SHALL return HTTP 403 with detail "仅合伙人可解锁已签字复核表".

### Requirement 4: A1 复核状态看板

**User Story:** As a 现场经理, I want to see the completion status of all 5 review levels on the A1 dashboard, so that I can track the overall review progress at a glance.

#### Acceptance Criteria

1. THE Review_Dashboard SHALL display a card for each of the 5 review levels: A21 (现场负责人), A22 (经理), A23 (合伙人), A24 (质控), A25 (EQCR).
2. EACH card SHALL show: level label, assigned reviewer name, sign status (未开始/进行中/已通过/已退回), sign date if signed, and a progress indicator (completed items / total applicable items).
3. WHEN a level has sign status 'pass', THE card SHALL display a green checkmark icon and the signer's name with timestamp.
4. WHEN a level has sign status 'reject', THE card SHALL display an orange warning icon with the rejection reason.
5. WHEN a level has not been started (no responses exist), THE card SHALL display a gray "未开始" state.
6. THE Review_Dashboard data SHALL be provided by a new auto_data_resolver `review_dashboard_status` that aggregates sign statuses, assigned reviewer names, and item completion counts for all 5 levels.
7. WHEN any review checklist's sign status changes, THE Review_Dashboard SHALL reflect the update on next A1 dashboard render (no manual refresh required beyond page load).

### Requirement 5: 未清复核意见计数器

**User Story:** As a 现场负责人, I want to see how many review comments remain unresolved before I can sign off, so that all issues are properly addressed before formal sign-off per CAS 1220.16.

#### Acceptance Criteria

1. THE GtReviewChecklist component SHALL display an Unresolved_Count badge showing the number of checklist items with conclusion='N' (不符合) that have not been subsequently changed to 'Y' or 'NA'.
2. WHEN Unresolved_Count > 0 and a user attempts to sign (action='pass'), THE save_review_sign function SHALL reject the sign with error "尚有 {count} 项复核意见未清零，无法签字".
3. THE Unresolved_Count SHALL be computed server-side from checklist_responses: count of items where conclusion='N' for the current wp_id, excluding the `-sign` and `-record` system items.
4. THE GtReviewChecklist SHALL display the Unresolved_Count near the sign button area as an el-badge with type="danger" when count > 0.
5. WHEN all items with conclusion='N' are changed to 'Y' or 'NA', THE Unresolved_Count SHALL become 0 and the sign button SHALL become enabled (provided allItemsDone is also true).
6. THE backend review-sign endpoint SHALL independently verify Unresolved_Count == 0 before accepting a 'pass' action, regardless of frontend state.
