# Requirements Document

## Introduction

为 C2~C15 控制测试底稿的 L1 Dialog（主控制测试详情弹窗）和 Cx-2 偏差评价表增加两项增强功能：

1. **编制提示琥珀块**：在 L1 Dialog 和 Cx-2 偏差评价弹窗中嵌入方法论上下文提示（琥珀色左边线+浅黄背景），内容来源于新建的 C2~C15 guidance JSON 文件（从源模板 BCD 类底稿 md 提取红字内容）。
2. **附件 OCR 作为 AI context**：用户在触发 AI 生成前可勾选已上传附件，将选中附件的 OCR 识别文本纳入 AI 上下文，提升生成质量。

增强覆盖组件：GtCControlTest.vue / CControlTestSubPage.vue / _c_control_test.py

## Glossary

- **System**：审计底稿平台（C 循环控制测试模块）
- **L1_Dialog**：C2~C15 主控制测试详情弹窗（GtCControlTest.vue 中的 controlDialogVisible 对话框）
- **Cx_2_Dialog**：Cx-2 偏差评价弹窗（deviationDialogVisible 对话框，以及独立 Cx-2 底稿的偏差评价视图）
- **Guidance_JSON**：`backend/data/wp_guidance/C{n}.json` 格式的静态编制指导 JSON 文件（n=2~15）
- **Amber_Block**：琥珀色左边线+浅黄背景的方法论上下文提示 UI 区块
- **AI_Generate_Endpoint**：`POST /api/workpapers/{wp_id}/ai/generate-text`，接收 prompt/context/existingContent/section
- **OCR_Endpoint**：`POST /api/workpapers/{wp_id}/d4/contract-ocr`，上传文件返回 extracted_fields
- **Attachment_OCR_Context**：用户勾选附件后，通过 OCR 识别获取的文本内容，作为 AI 生成的补充上下文
- **Audit_User**：审计助理或现场经理，执行控制测试底稿编制

## Requirements

### Requirement 1: 新建 C2~C15 Guidance JSON 文件

**User Story:** As an Audit_User, I want the system to provide control-test-specific guidance content for each cycle (C2~C15), so that I can reference methodology notes while filling in the control test worksheet.

#### Acceptance Criteria

1. THE System SHALL provide Guidance_JSON files at path `backend/data/wp_guidance/C{n}.json` for each cycle number n from 2 to 15 (14 files total)
2. WHEN the System loads a Guidance_JSON file, THE System SHALL parse the JSON structure containing fields: wp_code, title, sections (array of {heading, content}), and source
3. THE System SHALL extract Guidance_JSON content from BCD 类底稿 md source templates, retaining the red-text methodology annotations as section content
4. THE System SHALL set the source field of each Guidance_JSON file to "static_json"

### Requirement 2: L1 Dialog 编制提示琥珀块展示

**User Story:** As an Audit_User, I want to see methodology guidance displayed as an amber-styled block inside the L1 control test detail dialog, so that I can reference authoritative audit methodology while filling in the form without leaving the dialog.

#### Acceptance Criteria

1. WHEN the L1_Dialog opens for a control point in cycle C{n}, THE System SHALL load the corresponding Guidance_JSON file `C{n}.json` and display its sections as an Amber_Block at the top of the dialog content area
2. THE System SHALL render the Amber_Block with a left amber border (4px solid amber/warning color), light yellow background (#FFFBEB or equivalent), and 12px base font
3. THE System SHALL render each guidance section heading in bold followed by the section content as paragraph text within the Amber_Block
4. WHILE the L1_Dialog is in readonly mode, THE System SHALL still display the Amber_Block (guidance is always visible regardless of edit state)
5. THE System SHALL render the Amber_Block as a collapsible `<details>` element with summary text "编制提示" to allow the user to expand or collapse the guidance
6. IF a Guidance_JSON file does not exist for a given cycle number, THEN THE System SHALL hide the Amber_Block without displaying an error

### Requirement 3: Cx-2 偏差评价弹窗编制提示琥珀块展示

**User Story:** As an Audit_User, I want to see deviation-evaluation methodology guidance displayed as an amber-styled block inside the Cx-2 deviation assessment dialog, so that I can follow the correct methodology when evaluating control deviations.

#### Acceptance Criteria

1. WHEN the Cx_2_Dialog opens for cycle C{n}, THE System SHALL load the corresponding Guidance_JSON file `C{n}-2.json` and display its sections as an Amber_Block at the top of the deviation evaluation content area
2. THE System SHALL apply the same Amber_Block styling (amber left border, light yellow background, collapsible details) as the L1_Dialog Amber_Block
3. WHILE the Cx_2_Dialog is in readonly mode, THE System SHALL still display the Amber_Block
4. IF a Guidance_JSON file `C{n}-2.json` does not exist for a given cycle number, THEN THE System SHALL hide the Amber_Block without displaying an error

### Requirement 4: L1 Dialog AI 按钮增加附件 OCR 上下文选择

**User Story:** As an Audit_User, I want to select which uploaded attachments should contribute OCR text to the AI generation context before triggering AI, so that the generated content references my actual audit evidence.

#### Acceptance Criteria

1. WHEN the Audit_User clicks the AI generate button in the L1_Dialog, THE System SHALL display an attachment selection popup listing all attachments associated with the current workpaper
2. THE System SHALL display each attachment in the selection list with its file name and an OCR eligibility indicator (image/PDF files marked as OCR-capable)
3. WHEN the Audit_User selects one or more attachments and confirms, THE System SHALL call the OCR_Endpoint for each selected attachment that has not been previously OCR-processed and collect the extracted text
4. WHEN OCR processing completes for all selected attachments, THE System SHALL include the concatenated OCR text (truncated to 3000 characters total) in the context parameter of the AI_Generate_Endpoint call
5. IF no attachments are selected by the Audit_User, THEN THE System SHALL proceed with AI generation using only form field context without attachment OCR text
6. IF an OCR call fails for a specific attachment, THEN THE System SHALL skip that attachment and proceed with successfully OCR-processed attachments, displaying a warning message identifying the failed attachment

### Requirement 5: Cx-2 偏差评价 AI 按钮增加附件 OCR 上下文选择

**User Story:** As an Audit_User, I want the same attachment OCR context selection capability in the deviation evaluation dialog, so that I can reference evidence documents when generating deviation analysis text.

#### Acceptance Criteria

1. WHEN the Audit_User clicks the AI generate button in the Cx_2_Dialog, THE System SHALL display the same attachment selection popup as the L1_Dialog
2. THE System SHALL reuse the same attachment list source (workpaper-associated attachments) and OCR processing logic as Requirement 4
3. WHEN the Audit_User selects attachments and confirms, THE System SHALL include the OCR text in the AI_Generate_Endpoint context under key "参考资料（OCR识别）"
4. IF no attachments exist for the current workpaper, THEN THE System SHALL disable the attachment selection option and proceed directly with AI generation

### Requirement 6: 附件列表数据来源与缓存

**User Story:** As an Audit_User, I want the attachment selection popup to load quickly with all relevant attachments, so that I do not experience delays when triggering AI generation.

#### Acceptance Criteria

1. WHEN the attachment selection popup opens, THE System SHALL fetch attachments from the workpaper's associated attachment list via the existing attachment query endpoint
2. THE System SHALL cache the fetched attachment list for the duration of the dialog session (until the dialog closes) to avoid redundant API calls
3. THE System SHALL cache OCR results per attachment ID for the duration of the component lifecycle, so that repeated AI generation requests do not re-OCR the same attachments
4. WHEN a new attachment is uploaded during the same dialog session, THE System SHALL refresh the cached attachment list to include the newly uploaded file

### Requirement 7: 后端 Guidance JSON 加载端点支持

**User Story:** As an Audit_User, I want the guidance content to load from the server consistently, so that guidance is always up-to-date when I open the dialog.

#### Acceptance Criteria

1. THE System SHALL serve Guidance_JSON content through the existing render-config mechanism, including guidance data in the html_data response under key "guidance"
2. WHEN the render strategy for c-control-test processes a workpaper, THE System SHALL read the corresponding `C{n}.json` file from `backend/data/wp_guidance/` and include its sections array in the response
3. IF the Guidance_JSON file is missing or malformed, THEN THE System SHALL return guidance as null in the response without raising an error
