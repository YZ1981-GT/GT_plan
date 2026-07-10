# Requirements Document

## Introduction

往来款账龄枚举可配置化功能。当前系统中 D2 应收账款硬编码为 5 年段（6 个区间），D3 预收账款和 F1 预付款项硬编码为 3 年段（4 个区间），K1/K3/G5 等其他往来科目也各自硬编码。本功能将账龄段配置提升到项目级别，支持 3 年段、5 年段和自定义三种模式，所有涉及往来款的底稿（D2/D3/F1/K1/K3/G5）统一从项目级配置读取账龄段定义，前端动态适配列数。

现有系统中已实现底稿级 `aging_segments` 表（仅服务于 D6 坏账准备明细表），项目级配置存储在 `projects.wizard_state.aging_config` 中（仅含 preset 和 custom_segments），但 D2/D3/F1/K1/K3/G5 明细表的账龄字段仍为硬编码。本需求统一这些底稿的账龄段数据结构，使其从项目级配置动态派生。

## Glossary

- **Aging_Config_Service**: 项目级账龄配置统一服务，提供段定义的读取、保存、校验和变更通知
- **Aging_Preset**: 账龄预设方案枚举，包含 THREE_YEAR（3 年段）、FIVE_YEAR（5 年段）、CUSTOM（自定义）
- **Aging_Segment**: 单个账龄段定义，包含段名（label）和天数范围（dayFrom/dayTo）
- **Aging_Band**: 前端渲染用的账龄列定义，从 Aging_Segment 列表动态生成
- **useAgingConfig**: 前端统一 composable，提供响应式的账龄段列表和列定义
- **Project_Settings**: 项目级配置存储（wizard_state.aging_config），包含 preset 选择和自定义段定义
- **Detail_Composable**: 往来款明细表的 composable（useD2Detail/useD3Detail/useF1Detail/useK1Detail/useK3Detail/useG5Detail）
- **Affected_Subjects**: 受影响的科目列表：D2(1122)/D3(2203)/F1(1123)/K1(1221)/K3(2241)/G5(1531)
- **EventBus**: 进程内事件总线，用于账龄配置变更后通知已打开的底稿刷新列定义

## Requirements

### Requirement 1: 项目级账龄配置存储

**User Story:** As a 现场经理, I want to configure the aging band scheme at the project level, so that all working papers in the project use a consistent aging classification.

#### Acceptance Criteria

1. THE Aging_Config_Service SHALL support three Aging_Preset values: THREE_YEAR (segments: 1年以内/1-2年/2-3年/3年以上), FIVE_YEAR (segments: 1年以内/1-2年/2-3年/3-4年/4-5年/5年以上), and CUSTOM (user-defined segments)
2. WHEN a project is created, THE Aging_Config_Service SHALL default the Aging_Preset to FIVE_YEAR for D2/K1/K3/G5 subjects and THREE_YEAR for D3/F1 subjects
3. THE Aging_Config_Service SHALL store the aging configuration in Project_Settings (wizard_state.aging_config) with fields: preset, custom_segments (array of Aging_Segment objects), and subject_overrides (per-subject preset overrides)
4. WHEN Aging_Preset is CUSTOM, THE Aging_Config_Service SHALL require at least 2 segments and at most 10 segments
5. THE Aging_Config_Service SHALL validate that each Aging_Segment has a non-empty label and that no two segments share the same label

### Requirement 2: 账龄配置 API

**User Story:** As a 审计助理, I want to read and update the project aging configuration through API endpoints, so that the configuration can be managed from the frontend.

#### Acceptance Criteria

1. THE Aging_Config_Service SHALL expose GET /api/projects/{id}/aging/config returning the current preset, effective segments list, and subject_overrides
2. THE Aging_Config_Service SHALL expose PUT /api/projects/{id}/aging/config accepting preset, custom_segments, and subject_overrides fields
3. WHEN the PUT endpoint receives an invalid configuration (empty segment names, duplicate labels, fewer than 2 or more than 10 custom segments), THE Aging_Config_Service SHALL return HTTP 422 with error_code and detail fields
4. THE Aging_Config_Service SHALL expose GET /api/aging/presets returning the predefined preset definitions (THREE_YEAR and FIVE_YEAR segment lists)
5. WHEN a project has no aging_config in wizard_state, THE Aging_Config_Service SHALL return the default configuration (FIVE_YEAR for receivable subjects, THREE_YEAR for advance-received subjects)

### Requirement 3: 前端统一 useAgingConfig composable

**User Story:** As a 审计助理, I want all inter-company account detail worksheets to dynamically display aging columns matching the project configuration, so that I see the correct number of aging bands without manual adjustment.

#### Acceptance Criteria

1. THE useAgingConfig composable SHALL expose a reactive `segments` array (ordered list of segment labels) derived from the project-level Aging_Config_Service
2. THE useAgingConfig composable SHALL expose a reactive `bands` array, where each band contains fields: key (unique identifier), label (display name), priorField (prior-period field key), currentField (current-period field key), and auditedField (audited field key)
3. WHEN the project aging configuration changes, THE useAgingConfig composable SHALL emit an event via EventBus to notify all open Detail_Composable instances to refresh their column definitions
4. THE useAgingConfig composable SHALL accept an optional subject parameter (e.g., 'D2', 'D3') to resolve subject-specific overrides from the project configuration
5. THE useAgingConfig composable SHALL cache the configuration per project session and only re-fetch when the EventBus notifies a configuration change

### Requirement 4: D2 明细表账龄列动态化

**User Story:** As a 审计助理, I want the D2 receivable detail worksheet to display aging columns based on the project aging configuration, so that I can use 3-year, 5-year, or custom aging bands as configured.

#### Acceptance Criteria

1. WHEN the useAgingConfig composable provides N segments, THE D2 Detail_Composable SHALL generate 3×N aging fields (prior/current/audited × N segments) in each DetailRow
2. THE D2 Detail_Composable SHALL store aging values as a nested object (agingPrior: Record<string, number>, agingCurrent: Record<string, number>, agingAudited: Record<string, number>) keyed by segment key instead of hardcoded field names
3. WHEN loading legacy data that uses hardcoded field names (priorAging1Year, priorAging1to2, etc.), THE D2 Detail_Composable SHALL migrate the values into the new nested structure without data loss
4. THE D2 Tab Detail view SHALL render aging columns dynamically based on the `bands` array from useAgingConfig, with each band generating three columns (期初/期末未审/期末审定)
5. WHEN the aging configuration changes while a D2 detail worksheet is open, THE D2 Detail_Composable SHALL preserve existing data for segments that still exist and zero-initialize new segments

### Requirement 5: D3/F1 明细表账龄列动态化

**User Story:** As a 审计助理, I want the D3 advance-received and F1 prepayment detail worksheets to display aging columns based on the project aging configuration, so that these worksheets also support configurable aging bands.

#### Acceptance Criteria

1. WHEN the useAgingConfig composable provides N segments for subject D3, THE D3 Detail_Composable SHALL generate 2×N aging fields (agingPrior and agingAudited × N segments) in each DetailRow
2. WHEN the useAgingConfig composable provides N segments for subject F1, THE F1 Detail_Composable SHALL generate 2×N aging fields (agingPrior and agingAudited × N segments) in each DetailRow
3. WHEN loading legacy D3 data that uses hardcoded aging object (within1/y1to2/y2to3/over3), THE D3 Detail_Composable SHALL migrate the values into the new keyed structure without data loss
4. WHEN loading legacy F1 data that uses hardcoded aging object (within1/y1to2/y2to3/over3), THE F1 Detail_Composable SHALL migrate the values into the new keyed structure without data loss
5. THE D3 and F1 tab detail views SHALL render aging columns dynamically based on the `bands` array from useAgingConfig

### Requirement 6: K1/K3/G5 明细表账龄列动态化

**User Story:** As a 审计助理, I want the K1 other receivable, K3 other payable, and G5 long-term receivable detail worksheets to also use the project aging configuration, so that all inter-company account worksheets are consistent.

#### Acceptance Criteria

1. WHEN the useAgingConfig composable provides N segments for subject K1, THE K1 Detail_Composable SHALL generate aging fields following the same nested structure as the D2 pattern
2. WHEN the useAgingConfig composable provides N segments for subject K3, THE K3 Detail_Composable SHALL generate aging fields following the same nested structure as the D2 pattern
3. WHEN the useAgingConfig composable provides N segments for subject G5, THE G5 Detail_Composable SHALL generate aging fields following the same nested structure as the D2 pattern
4. THE K1, K3, and G5 tab detail views SHALL render aging columns dynamically based on the `bands` array from useAgingConfig

### Requirement 7: 账龄配置 UI 管理界面

**User Story:** As a 现场经理, I want a configuration dialog to select and customize aging band schemes, so that I can easily switch between presets or define custom aging segments.

#### Acceptance Criteria

1. THE Aging Configuration Dialog SHALL display three preset options: 3年段、5年段、自定义，with radio/segmented selection
2. WHEN the user selects 3年段 or 5年段, THE Aging Configuration Dialog SHALL display the preset segments as read-only labels
3. WHEN the user selects 自定义, THE Aging Configuration Dialog SHALL display an editable list of segment names with add/remove controls
4. THE Aging Configuration Dialog SHALL validate segment names in real-time (no empty names, no duplicates) and disable the confirm button when validation fails
5. WHEN the user confirms a configuration change and existing aging data has been filled, THE Aging Configuration Dialog SHALL display a warning that data for removed segments will be lost, requiring explicit confirmation
6. THE Aging Configuration Dialog SHALL support subject-level override (allow different presets for receivable vs advance-received subjects) via a toggle or dropdown

### Requirement 8: 导入导出兼容性

**User Story:** As a 审计助理, I want the import/export functionality to correctly handle dynamic aging columns, so that exported templates reflect the current aging configuration and imported data maps correctly.

#### Acceptance Criteria

1. WHEN exporting a detail worksheet template, THE Export Service SHALL generate aging column headers based on the current project aging configuration (not hardcoded 5-year or 3-year headers)
2. WHEN importing data into a detail worksheet, THE Import Service SHALL map imported aging columns by matching segment labels to the current project configuration
3. IF an imported file contains aging columns that do not match the current configuration, THEN THE Import Service SHALL report unmatched columns as warnings and skip those values
4. WHEN the aging configuration has changed since a template was exported, THE Import Service SHALL attempt to match columns by label and map old segment names to new ones where possible

### Requirement 9: D6 坏账准备 ECL 联动

**User Story:** As a 审计助理, I want the D6 bad debt provision ECL calculation to use the same aging segments as the project configuration, so that ECL groups align with the detail worksheet aging bands.

#### Acceptance Criteria

1. WHEN a D6 ECL aging group is created, THE D6 ECL Calculation composable SHALL initialize aging rows based on the current project aging segments (from useAgingConfig) instead of a hardcoded 6-row list
2. WHEN the project aging configuration changes, THE D6 ECL Calculation composable SHALL update the aging rows in existing groups to match the new segment list (add new rows with zero values, mark removed rows for archival)
3. THE D6 ECL Calculation composable SHALL preserve the lossRate and bookBalance values for segments that continue to exist after a configuration change

### Requirement 10: 旧数据迁移策略

**User Story:** As a 现场经理, I want existing projects with hardcoded aging data to continue working correctly after the upgrade, so that no data is lost during the migration.

#### Acceptance Criteria

1. WHEN the system encounters a project without aging_config in wizard_state, THE Aging_Config_Service SHALL infer the default preset based on the subject type (FIVE_YEAR for D2/K1/K3/G5, THREE_YEAR for D3/F1)
2. WHEN loading DetailRow data in the old flat-field format (priorAging1Year, priorAging1to2, etc.), THE Detail_Composable SHALL automatically convert to the new nested format using a deterministic field-to-segment mapping
3. THE migration mapping SHALL be: priorAging1Year→segments[0], priorAging1to2→segments[1], priorAging2to3→segments[2], priorAging3to4→segments[3], priorAging4to5→segments[4], priorAgingOver5→segments[5] for 5-year; and within1→segments[0], y1to2→segments[1], y2to3→segments[2], over3→segments[3] for 3-year
4. THE Detail_Composable SHALL serialize data exclusively in the new nested format after migration, eliminating the old flat-field keys from stored JSON
