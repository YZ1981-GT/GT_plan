# Requirements Document

## Introduction

为 A8-1（管理层对审计报告日后公布其他信息的书面声明）创建专属 HTML 组件，将原 48 段落 + 1 表格的 Word 模板转化为 6 条声明卡片 + 签字区的结构化 UI。组件支持双模式（结构化视图 / OnlyOffice 在线编辑），数据持久化走 checklist_responses（item_id: `a81-{section}-{field_id}`）。

核心价值：6 条声明以卡片式渲染，其中 3 条含动态文件清单（增删 tag），1 条含日期选择器，1 条含 Y/N 确认，1 条含自由文本。签字区自动填充公司名和法定代表人。

新增 componentType: `a8-1-other-info-representation`，通过 wp_code_overrides 将 A8-1 映射为该类型。

## Glossary

- **GtA81OtherInfoRepresentation**: 前端主组件（~400 行），渲染书面声明 6 条卡片 UI
- **useA81OtherInfoRepresentation**: 前端 composable，管理声明数据加载/保存/文件清单增删
- **A81_Render_Strategy**: 后端渲染策略（`_a81_other_info_representation.py`），从 checklist_responses 加载已填数据
- **Statement_Card**: 声明条款卡片，含条款序号 + 条款文本 + 可编辑区域（文件清单/日期/Y/N/textarea）
- **File_List**: 动态文件清单（可增删的 tag 数组），用于第1/4/5条声明
- **Signature_Area**: 签字区（公司名称自动填 + 法定代表人 + 日期）

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A8-1 to use a dedicated componentType, so that the structured statement form replaces the generic word-template rendering.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A8-1" to componentType "a8-1-other-info-representation"
2. THE htmlRendererRegistry SHALL register componentType "a8-1-other-info-representation" mapping to GtA81OtherInfoRepresentation component
3. THE RENDERER_DISPATCH SHALL include an "a8-1-other-info-representation" strategy function that invokes A81_Render_Strategy
4. THE VALID_COMPONENT_TYPES list SHALL include "a8-1-other-info-representation"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing for A8-1, so that I can use the most efficient mode for my current task.

#### Acceptance Criteria

1. WHEN A8-1 workpaper loads, THE GtA81OtherInfoRepresentation SHALL display an el-segmented control with two options: "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA81OtherInfoRepresentation SHALL render GtOnlyOfficeSheet for the A8-1 docx file
4. WHILE OnlyOffice is unavailable (health check fails), THE Mode_Switch SHALL disable the "在线编辑" option and display tooltip "在线编辑不可用"
5. WHEN the user switches from structured view to online editor, THE GtA81OtherInfoRepresentation SHALL flush all pending saves before initializing OnlyOffice

### Requirement 3: 抬头与致辞（自动填充）

**User Story:** As a 审计助理, I want the header and addressee to be auto-filled from project context, so that I don't need to manually type standard text.

#### Acceptance Criteria

1. THE GtA81OtherInfoRepresentation SHALL render a header area with auto-filled company name from project client_name
2. THE header SHALL display "致：致同会计师事务所" and auto-fill signing CPA names from project context
3. THE GtA81OtherInfoRepresentation SHALL render a read-only introduction paragraph (引言段) with muted styling

### Requirement 4: 声明第1条 — 年度报告文件清单

**User Story:** As a 审计助理, I want to manage a dynamic list of annual report documents, so that I can accurately declare what files are included.

#### Acceptance Criteria

1. THE Statement_Card 1 SHALL display the clause text: "本公司XX年度报告包含以下文件："
2. THE Statement_Card 1 SHALL render a File_List with el-tag components for each document name
3. THE File_List SHALL support adding new items via el-input + confirm button
4. THE File_List SHALL support removing items via tag close button
5. WHEN the file list changes, THE useA81OtherInfoRepresentation SHALL debounce-save (2s) the list as JSON array to checklist_responses with item_id `a81-statement-1-files`
6. THE Statement_Card 1 SHALL have an AI button (disabled, tooltip "AI 根据年度报告内容自动生成文件清单即将上线")

### Requirement 5: 声明第2条 — 计划公布日期

**User Story:** As a 审计助理, I want to select the planned publication date, so that I can declare when the annual report will be published.

#### Acceptance Criteria

1. THE Statement_Card 2 SHALL display the clause text about planned publication date
2. THE Statement_Card 2 SHALL render an el-date-picker for the planned publication date
3. WHEN the date changes, THE useA81OtherInfoRepresentation SHALL debounce-save (2s) to checklist_responses with item_id `a81-statement-2-date`

### Requirement 6: 声明第3条 — 一致性确认

**User Story:** As a 审计助理, I want to confirm consistency between other information and financial statements with Y/N, so that I can quickly record the confirmation status.

#### Acceptance Criteria

1. THE Statement_Card 3 SHALL display the clause text about consistency confirmation
2. THE Statement_Card 3 SHALL render an el-radio-group with options: Y (一致) / N (不一致)
3. WHEN answer is "N", THE Statement_Card 3 SHALL display a conditional textarea for inconsistency explanation
4. WHEN the selection changes, THE useA81OtherInfoRepresentation SHALL debounce-save (2s) to checklist_responses with item_id `a81-statement-3-consistency`

### Requirement 7: 声明第4条 — 审计报告日前提交文件清单

**User Story:** As a 审计助理, I want to manage the list of documents submitted before audit report date, so that I can declare pre-report submissions.

#### Acceptance Criteria

1. THE Statement_Card 4 SHALL display the clause text about pre-audit-report-date documents
2. THE Statement_Card 4 SHALL render a File_List with add/remove functionality (same as Statement 1)
3. WHEN the file list changes, THE useA81OtherInfoRepresentation SHALL debounce-save (2s) to checklist_responses with item_id `a81-statement-4-files`

### Requirement 8: 声明第5条 — 审计报告日后提供文件清单

**User Story:** As a 审计助理, I want to manage the list of documents to be provided after audit report date, so that I can declare post-report submissions.

#### Acceptance Criteria

1. THE Statement_Card 5 SHALL display the clause text about post-audit-report-date documents
2. THE Statement_Card 5 SHALL render a File_List with add/remove functionality (same as Statement 1)
3. WHEN the file list changes, THE useA81OtherInfoRepresentation SHALL debounce-save (2s) to checklist_responses with item_id `a81-statement-5-files`

### Requirement 9: 声明第6条 — 其他事项

**User Story:** As a 审计助理, I want an optional textarea for other matters, so that I can add additional declarations when needed.

#### Acceptance Criteria

1. THE Statement_Card 6 SHALL display the clause text about other matters
2. THE Statement_Card 6 SHALL render an editable textarea with placeholder "如无其他事项，可留空"
3. WHEN the textarea changes, THE useA81OtherInfoRepresentation SHALL debounce-save (2s) to checklist_responses with item_id `a81-statement-6-other`

### Requirement 10: 签字区

**User Story:** As a 审计助理, I want the signature area with auto-filled company name and a date picker, so that I can quickly complete the sign-off.

#### Acceptance Criteria

1. THE Signature_Area SHALL auto-fill company name from project client_name
2. THE Signature_Area SHALL include an el-input for "法定代表人签字"
3. THE Signature_Area SHALL include an el-date-picker for signature date
4. WHEN the project has audit_report_date in context, THE signature date SHALL default to that date
5. WHEN any signature field changes, THE useA81OtherInfoRepresentation SHALL debounce-save (2s) to checklist_responses with item_id `a81-signature-{field_id}`

### Requirement 11: 编制指导

**User Story:** As a 审计助理, I want to see editorial guidance as a collapsible panel, so that I can reference instructions when needed.

#### Acceptance Criteria

1. THE GtA81OtherInfoRepresentation SHALL render the template guidance (from Table 0) as an el-collapse panel with el-alert styling at the top of the form
2. THE guidance panel SHALL default to collapsed state

### Requirement 12: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A8-1 data pre-loaded, so that the component can render immediately.

#### Acceptance Criteria

1. WHEN render-config is requested for A8-1, THE A81_Render_Strategy SHALL return: statements (6 statements with field definitions and current values), signature_data (3 fields), project_context (client_name, audit_report_date, cpa_names)
2. THE A81_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a81-%' for the given project and workpaper
3. THE file list fields (statements 1, 4, 5) SHALL be stored as JSON arrays in the remark column of checklist_responses

### Requirement 13: 数据持久化

**User Story:** As a 审计助理, I want all my edits to be automatically saved, so that I can resume editing at any time without data loss.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA81OtherInfoRepresentation composable SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a81-statement-{N}-{field_id}` for statement fields, `a81-signature-{field_id}` for signature fields
3. WHEN a save succeeds, THE GtA81OtherInfoRepresentation SHALL update save status indicator to "已保存"
4. IF a save fails, THEN THE GtA81OtherInfoRepresentation SHALL display el-message error and mark status as "未保存"
