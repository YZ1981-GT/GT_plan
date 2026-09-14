# Requirements Document

## Introduction

为 A17-6（总结会会议纪要）创建专属 HTML 组件，将原 4 页/2 表的极简 Word 模板（11 行 × 3 列）转化为 6 字段卡片的结构化 UI。组件支持双模式（结构化视图 / OnlyOffice 在线编辑），数据持久化走 checklist_responses（item_id: `a176-{field_id}`）。

核心价值：最简单的子底稿组件——元信息 + 会议时间 + 参加人员 + 会议纪要内容 + 结论 + 附件。

新增 componentType: `a17-6-closing-meeting`，通过 wp_code_overrides 保持 skip 状态（在 A17 bundle Tab 内嵌渲染）。

## Glossary

- **GtA176ClosingMeeting**: 前端主组件（~200 行），渲染 6 字段卡片
- **useA176ClosingMeeting**: 前端 composable，管理数据加载/保存
- **A176_Render_Strategy**: 后端渲染策略（`_a176_closing_meeting.py`）

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A17-6 to use a dedicated componentType.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A17-6" to componentType "a17-6-closing-meeting" with skip status
2. THE htmlRendererRegistry SHALL register componentType "a17-6-closing-meeting" mapping to GtA176ClosingMeeting
3. THE RENDERER_DISPATCH SHALL include a "a17-6-closing-meeting" strategy function
4. THE VALID_COMPONENT_TYPES list SHALL include "a17-6-closing-meeting"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing for A17-6.

#### Acceptance Criteria

1. WHEN A17-6 workpaper loads, THE GtA176ClosingMeeting SHALL display an el-segmented control with two options: "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA176ClosingMeeting SHALL render GtOnlyOfficeSheet for the A17-6 docx file
4. WHILE OnlyOffice is unavailable, THE Mode_Switch SHALL disable the "在线编辑" option
5. WHEN the user switches modes, THE GtA176ClosingMeeting SHALL flush all pending saves before switching

### Requirement 3: 元信息区块

**User Story:** As a 审计助理, I want project metadata auto-filled.

#### Acceptance Criteria

1. THE GtA176ClosingMeeting SHALL render a meta area with: 被审计单位(auto-fill), 审计期间(auto-fill), 编制人(auto-fill current user), 复核人(el-input), 日期(el-date-picker), 索引号(read-only "A17-6")
2. WHEN any meta field changes, THE useA176ClosingMeeting SHALL debounce-save (2s) with item_id `a176-meta-{field_id}`

### Requirement 4: 会议时间

**User Story:** As a 审计助理, I want to record the meeting date/time.

#### Acceptance Criteria

1. THE GtA176ClosingMeeting SHALL render an el-date-picker (type="datetime") for meeting time
2. WHEN date changes, THE useA176ClosingMeeting SHALL debounce-save (2s) with item_id `a176-meeting-time`

### Requirement 5: 参加人员

**User Story:** As a 审计助理, I want to record meeting attendees.

#### Acceptance Criteria

1. THE GtA176ClosingMeeting SHALL render an el-input for attendee list
2. WHEN content changes, THE useA176ClosingMeeting SHALL debounce-save (2s) with item_id `a176-attendees`

### Requirement 6: 会议纪要内容

**User Story:** As a 审计助理, I want a large textarea for meeting minutes content.

#### Acceptance Criteria

1. THE GtA176ClosingMeeting SHALL render a textarea with autosize (min 8 rows) for meeting minutes
2. WHEN content changes, THE useA176ClosingMeeting SHALL debounce-save (2s) with item_id `a176-minutes`

### Requirement 7: 结论

**User Story:** As a 现场经理, I want to record the meeting conclusion.

#### Acceptance Criteria

1. THE GtA176ClosingMeeting SHALL render a textarea with autosize (min 3 rows) for conclusion
2. WHEN content changes, THE useA176ClosingMeeting SHALL debounce-save (2s) with item_id `a176-conclusion`

### Requirement 8: 附件

**User Story:** As a 审计助理, I want to note any attachments to the meeting minutes.

#### Acceptance Criteria

1. THE GtA176ClosingMeeting SHALL render an el-input for attachment description (placeholder "附件说明")
2. WHEN content changes, THE useA176ClosingMeeting SHALL debounce-save (2s) with item_id `a176-attachments`

### Requirement 9: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A17-6 data pre-loaded.

#### Acceptance Criteria

1. WHEN render-config is requested for A17-6, THE A176_Render_Strategy SHALL return: meta_info (6 fields), fields (meeting_time, attendees, minutes, conclusion, attachments), project_context
2. THE A176_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a176-%'

### Requirement 10: 数据持久化

**User Story:** As a 审计助理, I want all my edits automatically saved.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA176ClosingMeeting SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a176-meta-{field_id}`, `a176-{field_id}`
3. WHEN a save succeeds, THE GtA176ClosingMeeting SHALL update save status to "已保存"
4. IF a save fails, THEN THE GtA176ClosingMeeting SHALL display el-message error
