# Requirements Document

## Introduction

为 A11-1（期后事项问询函/问询记录）创建专属 HTML 组件，将原 52 段落 + 1 表格的 Word 模板转化为 10 个 Q&A 卡片 + 签字元信息的结构化 UI。组件支持双模式（结构化视图 / OnlyOffice 在线编辑），数据持久化走 checklist_responses（item_id: `a111-{section}-{field_id}`）。

核心价值：10 个固定问询事项（CAS 规定的期后事项问询清单）以卡片式渲染，问题只读 + 答复 textarea 可编辑 + AI 建议按钮预留，顶部问询元信息（日期/受访对象/地点），左侧 10 题快速跳转导航。

新增 componentType: `a11-1-subsequent-events-inquiry`，通过 wp_code_overrides 将 A11-1 映射为该类型。

## Glossary

- **GtA111SubsequentEventsInquiry**: 前端主组件（~450 行），渲染期后事项问询记录卡片 UI
- **useA111SubsequentEvents**: 前端 composable，管理 10 题 Q&A 数据加载/保存/导航逻辑
- **A111_Render_Strategy**: 后端渲染策略（`_a111_subsequent_events_inquiry.py`），从 checklist_responses 加载已填答复数据
- **QA_Card**: 问答卡片数据结构，含固定问题文本 + 可编辑答复 + 编制指导提示
- **Inquiry_Meta**: 问询元信息（询问日期/受访对象/询问地点/项目组签字）
- **Mode_Switch**: el-segmented 双模式切换控件（「结构化视图」|「在线编辑」）

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A11-1 to use a dedicated componentType, so that the structured Q&A form replaces the generic word-template rendering.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A11-1" to componentType "a11-1-subsequent-events-inquiry"
2. THE htmlRendererRegistry SHALL register componentType "a11-1-subsequent-events-inquiry" mapping to GtA111SubsequentEventsInquiry component
3. THE RENDERER_DISPATCH SHALL include an "a11-1-subsequent-events-inquiry" strategy function that invokes A111_Render_Strategy
4. THE VALID_COMPONENT_TYPES list SHALL include "a11-1-subsequent-events-inquiry"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing for A11-1, so that I can use the most efficient mode for my current task.

#### Acceptance Criteria

1. WHEN A11-1 workpaper loads, THE GtA111SubsequentEventsInquiry SHALL display an el-segmented control with two options: "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA111SubsequentEventsInquiry SHALL render GtOnlyOfficeSheet for the A11-1 docx file
4. WHILE OnlyOffice is unavailable (health check fails), THE Mode_Switch SHALL disable the "在线编辑" option and display tooltip "在线编辑不可用"
5. WHEN the user switches from structured view to online editor, THE GtA111SubsequentEventsInquiry SHALL flush all pending saves before initializing OnlyOffice

### Requirement 3: 问询元信息区

**User Story:** As a 审计助理, I want to fill in the inquiry metadata (date, interviewee, location, team signature), so that the form header is complete.

#### Acceptance Criteria

1. THE GtA111SubsequentEventsInquiry SHALL render an Inquiry_Meta card at the top with 4 fields: 询问日期 (el-date-picker), 受访对象 (el-input), 询问地点 (el-input), 项目组签字 (el-input)
2. WHEN the project has a balance_sheet_date in context, THE 询问日期 SHALL default to a date after balance_sheet_date
3. WHEN any meta field changes, THE useA111SubsequentEvents composable SHALL debounce-save (2s) to checklist_responses with item_id `a111-meta-{field_id}`

### Requirement 4: 问询目的（只读参考）

**User Story:** As a 审计助理, I want to see the inquiry purpose statement as reference, so that I understand the context of this form.

#### Acceptance Criteria

1. THE GtA111SubsequentEventsInquiry SHALL render a collapsible (el-collapse) "问询目的" section with fixed read-only text describing the CAS requirements for subsequent events inquiry
2. THE 问询目的 section SHALL use muted text styling and default to collapsed state

### Requirement 5: 10 个问答卡片（核心区域）

**User Story:** As a 审计助理, I want to see 10 pre-defined inquiry questions with editable answer fields, so that I can record management's responses to each subsequent events question.

#### Acceptance Criteria

1. THE GtA111SubsequentEventsInquiry SHALL render 10 QA_Card components in sequential order
2. THE each QA_Card SHALL display: a numbered question title (只读), the fixed question text (只读, muted styling), and an editable textarea for "受访对象答复"
3. THE 10 questions SHALL cover: (1)承诺借款担保 (2)资产出售购置 (3)资本发行/债务 (4)政府征用/灾害 (5)或有事项进展 (6)重大调整事项 (7)持续经营事项 (8)会计估计变更 (9)资产可收回性 (10)其他重大事项
4. WHERE a question has editorial guidance (编制指导), THE QA_Card SHALL display it as an el-alert (type=info) below the question text
5. THE each QA_Card answer textarea SHALL have an adjacent AI button (disabled, tooltip "AI 生成建议答复即将上线") for Phase3 vLLM integration
6. WHEN any answer textarea changes, THE useA111SubsequentEvents composable SHALL debounce-save (2s) to checklist_responses with item_id `a111-qa-{question_number}`

### Requirement 6: 证据提供区

**User Story:** As a 审计助理, I want a section to record what evidence the client has provided, so that I can document supporting materials.

#### Acceptance Criteria

1. THE GtA111SubsequentEventsInquiry SHALL render a "贵公司已提供的相关证据" section after the 10 Q&A cards
2. THE evidence section SHALL contain an editable textarea for free-form evidence description
3. WHEN the evidence textarea changes, THE useA111SubsequentEvents composable SHALL debounce-save (2s) to checklist_responses with item_id `a111-evidence-description`

### Requirement 7: 左侧快速导航

**User Story:** As a 审计助理, I want a left-side navigation for quick access to each of the 10 questions, so that I can jump between questions efficiently.

#### Acceptance Criteria

1. THE GtA111SubsequentEventsInquiry SHALL display a left-side mini navigation showing: "元信息", "Q1" through "Q10", "证据"
2. WHEN the user clicks a navigation item, THE view SHALL smooth-scroll to the corresponding card
3. THE navigation SHALL highlight the currently visible card using scrollspy behavior

### Requirement 8: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A11-1 data pre-loaded, so that the component can render immediately.

#### Acceptance Criteria

1. WHEN render-config is requested for A11-1, THE A111_Render_Strategy SHALL return: meta_data (4 meta fields with current values), qa_list (10 questions with fixed text + saved answers), evidence (saved text), project_context (client_name, balance_sheet_date), questions_config (10 question definitions with guidance flags)
2. THE A111_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a111-%' for the given project and workpaper
3. THE questions_config SHALL be a static list of 10 question definitions (number, title, text, has_guidance, guidance_text)

### Requirement 9: 数据持久化

**User Story:** As a 审计助理, I want all my edits to be automatically saved, so that I can resume editing at any time without data loss.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA111SubsequentEvents composable SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a111-meta-{field_id}` for meta fields, `a111-qa-{N}` for answers (N=1..10), `a111-evidence-description` for evidence
3. WHEN a save succeeds, THE GtA111SubsequentEventsInquiry SHALL update save status indicator to "已保存"
4. IF a save fails, THEN THE GtA111SubsequentEventsInquiry SHALL display el-message error and mark status as "未保存"

### Requirement 10: 编制指导提示

**User Story:** As a 审计助理, I want to see editorial guidance for questions that have special instructions, so that I can correctly fill in answers.

#### Acceptance Criteria

1. THE GtA111SubsequentEventsInquiry SHALL render guidance tips for questions with has_guidance=true as el-alert (type=warning) panels
2. THE guidance tips SHALL be collapsible and default to visible
3. THE guidance content SHALL include timing requirements (如问询时间要求) rendered as an el-alert at the top of the form
