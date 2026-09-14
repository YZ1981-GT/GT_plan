# Requirements Document

## Introduction

为所有 `word-template` 类型底稿（25 个 wp_code）统一实现双模式框架：结构化 HTML 精美视图 + OnlyOffice 在线编辑。在现有 `WorkpaperWordEditor.vue` 通用模式中增加 `el-segmented` 双模式切换，后端新增 docx 模板结构解析服务提取占位符和文档结构，前端以卡片式 UI 渲染可编辑字段，并预留 AI 填充能力。两种模式共享同一数据源（checklist_responses），切换时互刷新，导出时自动替换占位符生成最终 docx 文件。

## Glossary

- **Structured_View**: 结构化视图模式，从 docx 模板解析出的占位符/段落/表格以卡片式精美 HTML 渲染，支持交互编辑
- **Online_Editor**: 在线编辑模式，OnlyOffice 内嵌编辑器直接编辑 docx 文件
- **Template_Parser**: 后端 docx 模板结构解析服务，使用 python-docx 提取段落、表格、占位符列表
- **Template_Structure**: 解析器输出的结构化数据（段落列表、表格列表、占位符列表及其位置信息）
- **Placeholder**: docx 模板中的占位符标记（如 `${entity_name}`、`${audit_period}`、`××公司`、`202X年`）
- **Field_ID**: 每个可编辑字段的唯一标识符，格式 `wt-{wp_code}-{field_id}`
- **AI_Fill**: AI 预填功能，调用 `/ai-generate` 接口基于项目上下文自动生成字段内容（Phase3 待接入 vLLM）
- **Mode_Switch**: el-segmented 双模式切换控件（「结构化视图」|「在线编辑」）
- **WorkpaperWordEditor**: 现有通用 word-template 渲染组件（`WorkpaperWordEditor.vue`）
- **Checklist_Responses**: 数据持久化表，存储用户填写的结构化数据（item_id 格式：`wt-{wp_code}-{field_id}`）

## Requirements

### Requirement 1: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and online editing mode, so that I can choose the most efficient way to fill in word-template workpapers.

#### Acceptance Criteria

1. WHEN the WorkpaperWordEditor loads in generic mode (non-A16), THE Mode_Switch SHALL display an el-segmented control with two options: "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks a different mode option, THE WorkpaperWordEditor SHALL switch to the corresponding view without page reload
4. WHILE OnlyOffice is unavailable (health check fails), THE Mode_Switch SHALL disable the "在线编辑" option and display a tooltip "OnlyOffice 不可用"
5. WHILE OnlyOffice is unavailable, THE Structured_View SHALL remain fully functional as standalone editing mode
6. WHEN the user switches from Structured_View to Online_Editor, THE Online_Editor SHALL reflect the latest saved structured data in the document

### Requirement 2: 后端模板结构解析

**User Story:** As a 审计助理, I want the system to parse the docx template structure automatically, so that I can see a structured, fillable form instead of raw document content.

#### Acceptance Criteria

1. THE Template_Parser SHALL extract all placeholders from a docx template file, including `${...}` format markers and legacy Chinese markers (`××公司`/`XX公司`/`202X年`)
2. THE Template_Parser SHALL extract the document structure: ordered list of paragraphs (with heading level), tables (with row/column structure), and their relative positions
3. WHEN a valid docx template file is provided, THE Template_Parser SHALL return a Template_Structure object containing: paragraphs (text, style, heading_level, placeholder_ids), tables (rows, cells, placeholder_ids), and a flat placeholder_list with metadata (field_id, label, data_type, default_value)
4. WHEN an invalid or missing docx file is provided, THE Template_Parser SHALL return a descriptive error with HTTP 404 or 422 status
5. THE Template_Parser SHALL cache parsed results keyed by file path and mtime, reloading only when the template file modification time changes (same caching pattern as wp_code_overrides mtime hot-reload)
6. FOR ALL valid Template_Structure objects, parsing the template then formatting to a summary then re-parsing SHALL produce an equivalent placeholder_list (round-trip property on placeholder extraction)

### Requirement 3: 模板结构 API 端点

**User Story:** As a 前端开发者, I want a dedicated API endpoint that returns the parsed template structure for a given wp_code, so that the structured view can render the correct form fields.

#### Acceptance Criteria

1. WHEN a GET request is made to `/api/workpapers/{wp_id}/template-structure`, THE API SHALL return the cached Template_Structure for the corresponding word-template wp_code
2. THE API response SHALL include: `placeholders` (list of field definitions with id, label, data_type, position), `paragraphs` (ordered list with text and placeholder references), `tables` (list with cell structure and placeholder references), and `metadata` (template_name, wp_code, last_parsed_at)
3. WHEN the wp_code does not map to a word-template componentType, THE API SHALL return HTTP 400 with error message "该底稿不是 word-template 类型"
4. THE API SHALL merge user-filled responses from checklist_responses (by item_id pattern `wt-{wp_code}-{field_id}`) into the Template_Structure, returning each placeholder's current_value alongside its definition
5. IF the template file does not exist on disk, THEN THE API SHALL return HTTP 404 with error message "模板文件不存在: {wp_code}"

### Requirement 4: 结构化视图渲染

**User Story:** As a 审计助理, I want to see the word template as a beautifully rendered card-based form, so that I can quickly identify and fill in each required field.

#### Acceptance Criteria

1. THE Structured_View SHALL render each document section (heading + following paragraphs) as a visual card with the heading as card title
2. THE Structured_View SHALL render each placeholder field as an inline-editable element (el-input for short text, el-input type="textarea" for paragraphs, el-date-picker for date fields)
3. THE Structured_View SHALL render tables from the template as el-table components with editable cells for placeholder positions
4. WHEN a placeholder has a current_value from checklist_responses, THE Structured_View SHALL display that value pre-filled in the corresponding input
5. WHEN a placeholder has no current_value and has a default_value from template parsing, THE Structured_View SHALL display the default_value as input placeholder text
6. THE Structured_View SHALL display non-editable template text (guidance paragraphs, fixed headings) as read-only styled content between editable fields

### Requirement 5: 结构化数据保存

**User Story:** As a 审计助理, I want my filled-in data to be automatically saved, so that I don't lose my work and can resume editing later.

#### Acceptance Criteria

1. WHEN the user modifies a field in Structured_View, THE WorkpaperWordEditor SHALL debounce-save (2 seconds) the field value to checklist_responses with item_id format `wt-{wp_code}-{field_id}`
2. THE save operation SHALL use POST `/api/checklist-responses/batch` with project_id, wp_id, and a list of {item_id, conclusion, remark} objects
3. WHEN a save operation succeeds, THE WorkpaperWordEditor SHALL update the save status indicator to "已保存"
4. WHEN a save operation fails, THE WorkpaperWordEditor SHALL display an error notification and update save status to "未保存"
5. IF the network is offline, THEN THE WorkpaperWordEditor SHALL queue save operations and retry when connectivity is restored
6. WHEN the user switches from Structured_View to Online_Editor, THE WorkpaperWordEditor SHALL flush all pending saves before initializing the OnlyOffice editor

### Requirement 6: 导出与占位符回写

**User Story:** As a 审计助理, I want to export the final docx file with all my structured data merged into the template placeholders, so that I get a complete, professionally formatted document.

#### Acceptance Criteria

1. WHEN the user clicks the export button while in Structured_View, THE WorkpaperWordEditor SHALL call `GET /api/projects/{pid}/wp-templates/{wp_code}/prefilled-download` with additional query parameter `include_responses=true`
2. WHEN `include_responses=true` is specified, THE prefilled-download endpoint SHALL read all checklist_responses for the workpaper (item_id pattern `wt-{wp_code}-*`) and replace corresponding placeholders in the docx template
3. THE placeholder replacement SHALL preserve the original formatting (font, size, bold, color) of the placeholder text in the output docx
4. WHEN a placeholder has no user-provided value in checklist_responses, THE export SHALL retain the original placeholder text unchanged
5. FOR ALL Template_Structure objects with fully populated field values, exporting to docx then re-parsing the exported docx SHALL produce the same field values (round-trip property on export/re-parse)

### Requirement 7: AI 预填功能（占位按钮）

**User Story:** As a 审计助理, I want an AI fill button next to each editable field, so that I can leverage AI to auto-generate content based on project context when the feature becomes available.

#### Acceptance Criteria

1. THE Structured_View SHALL display an "AI 填充" icon button (el-button with icon) adjacent to each paragraph-type and text-type editable field
2. WHILE the AI service is unavailable (Phase3 not yet deployed), THE AI_Fill button SHALL be rendered in disabled state with tooltip "AI 填充功能即将上线"
3. WHEN the AI service becomes available AND the user clicks AI_Fill, THE WorkpaperWordEditor SHALL call POST `/api/ai-generate` with context parameters (project_id, wp_code, field_id, surrounding_text)
4. WHEN the AI_Fill API returns a generated text, THE Structured_View SHALL populate the corresponding field with the generated content and mark it as unsaved
5. IF the AI_Fill API returns an error, THEN THE Structured_View SHALL display an el-message error notification without affecting the existing field value

### Requirement 8: 数据同步与模式互刷新

**User Story:** As a 审计助理, I want my edits in one mode to be reflected when I switch to the other mode, so that I have a consistent editing experience regardless of which mode I use.

#### Acceptance Criteria

1. WHEN the user switches from Online_Editor to Structured_View, THE WorkpaperWordEditor SHALL reload the template-structure API to fetch latest responses (which may have been updated via OnlyOffice save callback)
2. WHEN the user switches from Structured_View to Online_Editor, THE WorkpaperWordEditor SHALL first flush pending saves, then regenerate the docx file with current responses merged, and initialize OnlyOffice with the updated file
3. THE WorkpaperWordEditor SHALL maintain a single source of truth: checklist_responses table (item_id pattern `wt-{wp_code}-{field_id}`)
4. WHEN the OnlyOffice callback fires (document saved), THE system SHALL extract placeholder values from the saved docx and update corresponding checklist_responses records

### Requirement 9: 通用适用性

**User Story:** As a 现场经理, I want this dual-mode framework to work for all 25 word-template workpapers without per-template customization, so that the team has a consistent editing experience across all document-type workpapers.

#### Acceptance Criteria

1. THE dual-mode framework SHALL apply to all wp_codes where wp_code_overrides maps to componentType "word-template" (currently 25 codes: A8-1, A8-2, A9-1, A9-2, A10-1, A11-1, A12-1, A16-1~A16-7, A17-2-1, A17-3, A17-3-1, A17-4, A17-6, A18-1, A26-1~A26-4, A27-1, S12A, S33-REV, S34-1-1)
2. THE WorkpaperWordEditor SHALL not introduce a new componentType — it SHALL continue using "word-template" and add structured view capability internally
3. THE A16 mode (wp_code === 'A16') SHALL remain unchanged — dual-mode only applies to generic (non-A16) word-template workpapers
4. WHEN a word-template workpaper has no parseable placeholders (pure static document), THE Structured_View SHALL render it as read-only formatted content with a message "该模板无可编辑字段，请使用在线编辑模式"

### Requirement 10: 渲染策略集成

**User Story:** As a 前端开发者, I want the template-structure data to be included in the existing render-config response, so that the structured view can be initialized without extra API calls on first load.

#### Acceptance Criteria

1. WHEN a word-template workpaper's render-config is requested, THE RENDERER_DISPATCH SHALL include a "word-template" strategy function that returns template_structure alongside the existing html_data
2. THE word-template render strategy SHALL return: template_structure (from cached parser output), filled_responses (from checklist_responses), and sign_status (from field_overrides)
3. WHEN the Template_Parser cache is cold (first request after server restart), THE render strategy SHALL parse the template synchronously and populate the cache before responding
4. THE render-config response for word-template SHALL include `component_type: "word-template"` and `extra_props: { template_structure, filled_responses }` following the established render-config format

### Requirement 11: 导出 Word（完成稿合并导出）

**User Story:** As a 审计助理, I want to export the completed workpaper as a final Word document with all my structured data merged into the template, so that I get a professionally formatted docx ready for filing.

#### Acceptance Criteria

1. THE Structured_View toolbar SHALL display a "导出 Word" button (el-button with Download icon)
2. WHEN the user clicks "导出 Word", THE WorkpaperWordEditor SHALL first flush all pending saves, then call `GET /api/projects/{pid}/wp-templates/{wp_code}/prefilled-download?include_responses=true`
3. THE exported docx SHALL replace all placeholders with corresponding checklist_responses values, preserving original formatting (font/size/bold/color)
4. WHEN a placeholder has no user-provided value, THE export SHALL retain the original placeholder text (e.g. "××公司") unchanged
5. THE exported file SHALL be named `{wp_code}_{client_name}_{audit_year}.docx`
6. IF the export request fails, THEN THE WorkpaperWordEditor SHALL display el-message error "导出失败，请重试"

### Requirement 12: 导出模板（带说明事项的空白模板）

**User Story:** As a 审计助理, I want to download a blank template with embedded instructions/guidance, so that I can fill it in offline or share with team members who don't have platform access.

#### Acceptance Criteria

1. THE Structured_View toolbar SHALL display a "导出模板" button (el-button with Document icon)
2. WHEN the user clicks "导出模板", THE WorkpaperWordEditor SHALL call `GET /api/projects/{pid}/wp-templates/{wp_code}/prefilled-download?include_guidance=true`
3. THE exported template SHALL contain all original placeholders (unfilled) PLUS embedded guidance/instructions as visible comments or colored-text annotations
4. THE guidance annotations SHALL include: field descriptions, acceptable value ranges, CAS reference numbers, and sample fill examples (from template's editorial notes)
5. THE exported template file SHALL be named `{wp_code}_模板_带说明.docx`
6. THE guidance text SHALL be rendered in a distinct style (e.g. blue italic or comment boxes) so users can distinguish instructions from actual content

### Requirement 13: 导入数据（离线填写后上传解析）

**User Story:** As a 审计助理, I want to upload an offline-filled template and have the system automatically extract field values, so that I can complete workpapers offline and sync back to the platform.

#### Acceptance Criteria

1. THE Structured_View toolbar SHALL display a "导入数据" button (el-button with Upload icon)
2. WHEN the user clicks "导入数据", THE WorkpaperWordEditor SHALL display an el-upload dialog accepting .docx files
3. WHEN a valid docx file is uploaded, THE system SHALL call `POST /api/workpapers/{wp_id}/import-structured` with the file content
4. THE backend import endpoint SHALL use Template_Parser to extract placeholder values from the uploaded docx by comparing against the template structure
5. THE extracted values SHALL be written to checklist_responses (item_id pattern matching the workpaper's prefix), overwriting existing values for matched fields
6. WHEN import succeeds, THE Structured_View SHALL refresh to display the imported values and show el-message success "已导入 {N} 个字段"
7. IF any placeholder cannot be matched (template structure mismatch), THE response SHALL include a warning list of unmatched fields
8. IF the uploaded file is not a valid docx or doesn't match the expected template, THE system SHALL return HTTP 422 with error message "文件格式不匹配，请使用正确的模板"
