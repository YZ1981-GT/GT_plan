# Requirements Document

## Introduction

底稿版本链通用组件（workpaper-version-trail）为平台所有底稿（D~N循环/A类/B类/C类）提供 field-level 数据版本历史记录。当前底稿数据存储在 `checklist_responses` 表中，每次编辑为覆盖式写入，无历史追溯。本组件实现完整版本快照创建、时间线展示、版本对比 diff、回滚能力，以满足审计留痕的合规要求。

区别于已有的 `DeliverableVersionList`（文件级 Word/PDF 版本链），本组件是数据级版本（每个版本 = checklist_responses 的 JSON 快照）。

## Glossary

- **Version_Trail_Service**: 后端版本链服务，负责快照创建、存储、对比、回滚的核心业务逻辑
- **GtWpVersionTrail**: 前端版本链侧栏组件（el-drawer），展示时间线、diff 对比、回滚操作
- **Snapshot**: 版本快照，某时刻底稿全部 checklist_responses 行的 JSONB 副本
- **Snapshot_Type**: 快照触发类型枚举（manual/auto_sampling/auto_import/review_sign/status_change/rollback）
- **Diff_Engine**: 版本对比引擎，在后端执行两个快照间的 field-level diff 计算
- **Change_Summary**: 变动摘要，自动生成的人可读变动说明文本
- **workpaper_snapshots**: 新数据库表，存储版本快照数据（V096 迁移）

## Requirements

### Requirement 1: 手动版本快照创建

**User Story:** As a 审计助理, I want to manually save a version snapshot of the workpaper, so that I can preserve the current state before making further edits.

#### Acceptance Criteria

1. WHEN the user clicks the "保存版本" button, THE Version_Trail_Service SHALL create a snapshot containing all checklist_responses rows for the specified workpaper
2. WHEN creating a manual snapshot, THE Version_Trail_Service SHALL store the complete JSON array of {item_id, conclusion, remark, wp_ref} for every row belonging to that workpaper_id
3. WHERE the user provides a description, THE Version_Trail_Service SHALL store the description as snapshot metadata
4. WHERE the user does not provide a description, THE Version_Trail_Service SHALL store the snapshot with an empty description
5. THE Version_Trail_Service SHALL record the snapshot metadata including timestamp, user_id, snapshot_type='manual', and description

### Requirement 2: 自动版本快照触发

**User Story:** As a 现场经理, I want automatic snapshots to be created at critical moments, so that the audit trail captures the workpaper state before any bulk or significant operation.

#### Acceptance Criteria

1. WHEN the cutoff-test-auto-sampling or voucher-sampling-engine initiates a fill operation, THE Version_Trail_Service SHALL create a snapshot with snapshot_type='auto_sampling' before the fill executes
2. WHEN a batch Excel import operation is initiated for a workpaper, THE Version_Trail_Service SHALL create a snapshot with snapshot_type='auto_import' before the import executes
3. WHEN a review signature is applied to a workpaper (现场经理/合伙人签字), THE Version_Trail_Service SHALL create a snapshot with snapshot_type='review_sign'
4. WHEN the workpaper status changes (e.g., from "编制中" to "待复核"), THE Version_Trail_Service SHALL create a snapshot with snapshot_type='status_change'
5. IF the automatic snapshot creation fails, THEN THE Version_Trail_Service SHALL log a warning and allow the main operation to proceed without blocking
6. THE Version_Trail_Service SHALL accept a caller-provided description parameter to override the auto-generated change summary

### Requirement 3: 版本时间线展示

**User Story:** As a 审计助理, I want to view the version history of a workpaper in a timeline, so that I can understand when and why changes were made.

#### Acceptance Criteria

1. WHEN the user opens the version trail drawer, THE GtWpVersionTrail SHALL display all snapshots for the workpaper in reverse chronological order (newest first)
2. THE GtWpVersionTrail SHALL display for each snapshot: timestamp, operator name, snapshot_type label, description, and change summary
3. THE GtWpVersionTrail SHALL display the change summary as a human-readable text (e.g., "修改了3个字段，新增2个字段，删除1个字段")
4. WHEN the user clicks to expand a snapshot node, THE GtWpVersionTrail SHALL display the detailed list of changed fields for that version
5. THE GtWpVersionTrail SHALL paginate the version list with page_size=20
6. THE GtWpVersionTrail SHALL distinguish snapshot types with colored labels (manual=蓝色, auto_sampling=橙色, auto_import=紫色, review_sign=绿色, status_change=灰色, rollback=红色)

### Requirement 4: 版本对比 Diff

**User Story:** As a 现场经理, I want to compare two versions of a workpaper side by side, so that I can understand exactly what changed between them.

#### Acceptance Criteria

1. WHEN the user selects two versions for comparison, THE Diff_Engine SHALL compute the field-level diff between the two snapshots
2. THE Diff_Engine SHALL identify added items: item_ids present in version B but not in version A
3. THE Diff_Engine SHALL identify deleted items: item_ids present in version A but not in version B
4. THE Diff_Engine SHALL identify modified items: item_ids present in both versions where conclusion or remark values differ
5. THE GtWpVersionTrail SHALL display diff results in a table showing: item_id, field name (conclusion/remark), version A value, version B value, and change type (新增/删除/修改)
6. THE GtWpVersionTrail SHALL use color coding: green for added items, red for deleted items, yellow for modified items
7. THE Diff_Engine SHALL perform all diff computation on the backend (not in the browser)

### Requirement 5: 回滚到历史版本

**User Story:** As a 现场经理, I want to rollback the workpaper to a previous version, so that I can restore data after an incorrect bulk operation.

#### Acceptance Criteria

1. WHEN the user clicks the "回滚" button on a snapshot, THE GtWpVersionTrail SHALL display a confirmation dialog with the target version timestamp and a warning that the operation cannot be undone
2. WHEN the user confirms the rollback, THE Version_Trail_Service SHALL replace all current checklist_responses for the workpaper with the data from the selected snapshot
3. WHEN the rollback completes, THE Version_Trail_Service SHALL create a new snapshot with snapshot_type='rollback' and description="回滚到{target_version_timestamp}的版本"
4. THE Version_Trail_Service SHALL execute the rollback within a single database transaction (snapshot read + responses overwrite + new version creation)
5. WHEN the rollback completes, THE GtWpVersionTrail SHALL emit a 'rollback-completed' event to notify the parent component to refresh its data
6. THE Version_Trail_Service SHALL restrict rollback operations to users with 现场经理 or higher role (审计助理 cannot rollback)

### Requirement 6: 变动说明自动生成

**User Story:** As a 审计助理, I want the system to automatically generate a human-readable description of what changed in each version, so that I can quickly understand the nature of each change without examining the full diff.

#### Acceptance Criteria

1. WHEN a snapshot is created with snapshot_type='auto_sampling', THE Change_Summary SHALL generate a description based on the sampling context (e.g., "年审抽凭：随机抽样20笔，金额覆盖率78%")
2. WHEN a snapshot is created with snapshot_type='auto_import', THE Change_Summary SHALL generate a description based on the import context (e.g., "从Excel导入D2-2明细表：156行")
3. WHEN a snapshot is created with snapshot_type='review_sign', THE Change_Summary SHALL include the signer's name and role (e.g., "现场经理李明签字复核")
4. WHEN a snapshot is created with snapshot_type='rollback', THE Change_Summary SHALL include the target version reference (e.g., "回滚到2025-12-30版本")
5. FOR ALL snapshots, THE Change_Summary SHALL compute a diff-based summary against the previous snapshot: count of modified, added, and deleted fields
6. WHERE the caller provides a custom description, THE Version_Trail_Service SHALL use the custom description instead of the auto-generated one

### Requirement 7: 与底稿编辑器集成

**User Story:** As a 审计助理, I want to access the version trail from the workpaper editor toolbar, so that I can check history without leaving the editing context.

#### Acceptance Criteria

1. THE GtWpVersionTrail SHALL be a reusable component that accepts workpaperId as a prop and auto-loads the version list
2. WHEN the user clicks the "版本历史" button (clock icon) in the workpaper toolbar, THE GtWpVersionTrail SHALL open as an el-drawer sidebar
3. THE GtWpVersionTrail SHALL emit 'rollback-completed' event when a rollback is performed, enabling the parent component to refresh workpaper data
4. THE GtWpVersionTrail SHALL work with all workpaper types regardless of componentType (operates only on the checklist_responses data layer)

### Requirement 8: 与抽凭/截止测试集成升级

**User Story:** As a 审计助理, I want the sampling and cutoff operations to automatically use the version trail for snapshots, so that the before_data pattern is unified across the platform.

#### Acceptance Criteria

1. WHEN cutoff-test-auto-sampling creates a before_data snapshot, THE Version_Trail_Service SHALL be called via its createSnapshot API instead of storing before_data locally
2. WHEN voucher-sampling-engine creates a before_data snapshot, THE Version_Trail_Service SHALL be called via its createSnapshot API instead of storing before_data locally
3. THE Version_Trail_Service SHALL support a programmatic API (non-HTTP function call) for internal callers within the same backend process

### Requirement 9: 存储与生命周期管理

**User Story:** As a 平台运维, I want the version storage to be bounded and efficient, so that it does not cause unbounded database growth.

#### Acceptance Criteria

1. THE Version_Trail_Service SHALL store each snapshot as a JSONB column in the workpaper_snapshots table
2. THE Version_Trail_Service SHALL enforce a maximum of 50 snapshots per workpaper
3. WHEN a workpaper exceeds 50 snapshots, THE Version_Trail_Service SHALL delete the oldest non-manual snapshots (snapshot_type != 'manual') first
4. THE Version_Trail_Service SHALL preserve all manual snapshots regardless of the 50-snapshot limit
5. IF a single snapshot exceeds 2MB in size, THEN THE Version_Trail_Service SHALL log a warning and store only the item_id list without full remark text
6. THE workpaper_snapshots table SHALL be created by migration V096
7. THE workpaper_snapshots table SHALL have indexes on (workpaper_id, created_at DESC) for efficient timeline queries

### Requirement 10: 权限与安全

**User Story:** As a 质量控制复核合伙人, I want the version trail to enforce proper access controls, so that audit evidence integrity is maintained.

#### Acceptance Criteria

1. THE Version_Trail_Service SHALL allow snapshot creation by all users with workpaper edit permission
2. THE Version_Trail_Service SHALL allow snapshot viewing by all users with workpaper view permission
3. THE Version_Trail_Service SHALL restrict rollback operations to 现场经理 role or above (审计助理 cannot rollback)
4. THE Version_Trail_Service SHALL prohibit deletion of any snapshot (version trail is immutable audit evidence)
5. THE Version_Trail_Service SHALL enforce project_id + workpaper_id isolation (users cannot access snapshots from other projects)

### Requirement 11: 后端 API 规格

**User Story:** As a 前端开发者, I want well-defined API endpoints for the version trail, so that I can integrate the frontend component with consistent interfaces.

#### Acceptance Criteria

1. WHEN POST /api/projects/{pid}/workpapers/{wp_id}/versions is called, THE Version_Trail_Service SHALL create a new snapshot and return the snapshot metadata
2. WHEN GET /api/projects/{pid}/workpapers/{wp_id}/versions is called, THE Version_Trail_Service SHALL return the paginated list of snapshots (page_size=20, ordered by created_at DESC)
3. WHEN GET /api/projects/{pid}/workpapers/{wp_id}/versions/{vid} is called, THE Version_Trail_Service SHALL return the full snapshot detail including the data_json payload
4. WHEN POST /api/projects/{pid}/workpapers/{wp_id}/versions/{vid}/rollback is called, THE Version_Trail_Service SHALL execute the rollback and return the new snapshot created
5. WHEN POST /api/projects/{pid}/workpapers/{wp_id}/versions/compare is called with {version_a_id, version_b_id}, THE Diff_Engine SHALL return the field-level diff result
6. THE Version_Trail_Service SHALL validate that the requested workpaper belongs to the specified project (security isolation)

### Requirement 12: 通用性

**User Story:** As a 平台架构师, I want the version trail to be universally applicable to all workpaper types, so that every workpaper has consistent audit history capability.

#### Acceptance Criteria

1. THE Version_Trail_Service SHALL operate solely on the checklist_responses data layer without knowledge of the workpaper's componentType
2. THE GtWpVersionTrail SHALL render identically regardless of the underlying workpaper type (D~N循环/A类/B类/C类/word-template/audit-sheet)
3. THE Version_Trail_Service SHALL isolate each workpaper's version chain by workpaper_id (independent histories per workpaper)
