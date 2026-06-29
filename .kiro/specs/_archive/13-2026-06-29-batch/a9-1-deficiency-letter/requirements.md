# Requirements Document

## Introduction

为 A9-1（向管理层通报内部控制缺陷沟通函）创建专属 HTML 组件，将原 52 段落 + 2 表格的 Word 模板转化为 7 个结构化区块的精美卡片式 UI。组件支持双模式（结构化视图 / OnlyOffice 在线编辑），数据持久化走 checklist_responses（item_id: `a91-{section}-{field_id}`），核心价值在于与 B22B 内控缺陷评价表的联动——按严重程度自动分组填入缺陷列表。

新增 componentType: `a9-1-deficiency-letter`，通过 wp_code_overrides 将 A9-1 从 `word-template` 改映射为该类型。

## Glossary

- **GtA91DeficiencyLetter**: 前端主组件（`GtA91DeficiencyLetter.vue`，~600 行），渲染 A9-1 沟通函 7 区块卡片 UI
- **useA91DeficiencyLetter**: 前端 composable，管理区块数据加载/保存/联动逻辑
- **A91_Render_Strategy**: 后端渲染策略（`_a91_deficiency_letter.py`），从 checklist_responses 加载已填数据 + 从 B22B 联动查缺陷列表
- **Section**: A9-1 沟通函的 7 个结构化区块（收件人/正文引言/独立性声明/内部控制缺陷/审计委员会监督/签发区/管理层回复区）
- **Deficiency_Item**: 缺陷条目数据结构，含缺陷描述/影响说明/整改建议/索引号/severity
- **B22B_Link**: B22B 内控缺陷评价表与 A9-1 的联动关系，按 severity（重大/重要/一般）自动分组
- **GtIndexChip**: 索引号跳转组件（已有），显示可点击的底稿交叉引用标签
- **Mode_Switch**: el-segmented 双模式切换控件（「结构化视图」|「在线编辑」）
- **Checklist_Responses**: 数据持久化表，item_id 格式 `a91-{section}-{field_id}`

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A9-1 to use a dedicated componentType, so that the structured letter form replaces the generic word-template rendering.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A9-1" to componentType "a9-1-deficiency-letter"
2. THE htmlRendererRegistry SHALL register componentType "a9-1-deficiency-letter" mapping to GtA91DeficiencyLetter component
3. THE RENDERER_DISPATCH SHALL include an "a9-1-deficiency-letter" strategy function that invokes A91_Render_Strategy
4. THE VALID_COMPONENT_TYPES list SHALL include "a9-1-deficiency-letter"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing for A9-1, so that I can use the most efficient mode for my current task.

#### Acceptance Criteria

1. WHEN A9-1 workpaper loads, THE GtA91DeficiencyLetter SHALL display an el-segmented control with two options: "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA91DeficiencyLetter SHALL render GtOnlyOfficeSheet for the A9-1 docx file
4. WHILE OnlyOffice is unavailable (health check fails), THE Mode_Switch SHALL disable the "在线编辑" option and display tooltip "在线编辑不可用"
5. WHEN the user switches from structured view to online editor, THE GtA91DeficiencyLetter SHALL flush all pending saves before initializing OnlyOffice

### Requirement 3: 区块 1 — 收件人渲染

**User Story:** As a 审计助理, I want the addressee to be auto-filled from project client_name, so that I don't need to manually type the company name.

#### Acceptance Criteria

1. THE GtA91DeficiencyLetter SHALL render Section 1 (收件人) as a card with auto-filled text from project client_name
2. THE Section 1 card SHALL display format: `{client_name}总经理\财务总监\…：`
3. WHEN the project client_name is empty, THE Section 1 card SHALL display an editable el-input with placeholder "请输入收件单位"

### Requirement 4: 区块 2 — 正文引言（只读参考）

**User Story:** As a 审计助理, I want to see the standard audit responsibility and confidentiality statements as reference, so that I understand the context without accidentally editing boilerplate text.

#### Acceptance Criteria

1. THE GtA91DeficiencyLetter SHALL render Section 2 (正文引言) as a read-only card displaying 3 fixed paragraphs (审计责任/准则依据/保密声明)
2. THE Section 2 content SHALL be rendered with muted text styling to distinguish from editable content
3. THE Section 2 card SHALL be collapsible (el-collapse) with default expanded state

### Requirement 5: 区块 3 — 独立性声明

**User Story:** As a 审计助理, I want to confirm independence declarations with Y/N radio controls, so that I can quickly record the audit team's independence status.

#### Acceptance Criteria

1. THE GtA91DeficiencyLetter SHALL render Section 3 (独立性声明) with title "一、独立性问题"
2. THE Section 3 SHALL include sub-item (一) "审计项目组成员保持独立性" with el-radio-group (Y/N) control
3. THE Section 3 SHALL include sub-item (二) "不存在影响独立性的关系和事项" with el-radio-group (Y/N) and a conditional textarea for supplementary explanation visible only when answer is "N"
4. THE Section 3 SHALL include sub-item (三) "已采取必要防护措施" with el-radio-group (Y/N) control
5. THE Section 3 SHALL include "非审计服务声明" with el-radio-group (Y/N 是否提供非审计服务) and a conditional textarea for service description visible only when answer is "Y"
6. WHEN any radio selection changes, THE GtA91DeficiencyLetter SHALL debounce-save (2s) the value to checklist_responses with item_id `a91-independence-{sub_item_id}`

### Requirement 6: 区块 4 — 内部控制缺陷（核心联动区）

**User Story:** As a 审计助理, I want deficiencies from B22B to automatically populate into the correct severity group, so that I don't need to manually copy deficiency data between workpapers.

#### Acceptance Criteria

1. THE GtA91DeficiencyLetter SHALL render Section 4 (内部控制缺陷) with title "二、内部控制缺陷"
2. THE Section 4 SHALL display deficiency definitions (重大/重要/一般缺陷定义) as read-only reference text in an el-collapse panel
3. THE Section 4 SHALL render three severity sub-groups: (一) 重大缺陷, (二) 重要缺陷, (三) 一般缺陷
4. WHEN the component loads, THE A91_Render_Strategy SHALL query B22B evaluated deficiencies and group them by severity into the three sub-groups
5. THE each Deficiency_Item SHALL display: 缺陷描述 (textarea), 影响说明 (textarea), 整改建议 (textarea), 索引号 (GtIndexChip linking to B22B)
6. THE Section 4 SHALL provide an "新增缺陷" el-button in each severity sub-group for manual addition of deficiency items
7. THE each manually added Deficiency_Item SHALL include a delete button for removal
8. WHEN B22B publishes EventBus event `DEFICIENCY_EVALUATED`, THE GtA91DeficiencyLetter SHALL refresh the deficiency list from B22B
9. THE each deficiency 整改建议 field SHALL have an adjacent AI button (disabled, tooltip "AI 生成整改建议即将上线") for Phase3 vLLM integration
10. WHEN any deficiency field changes, THE GtA91DeficiencyLetter SHALL debounce-save (2s) the entire deficiency list to checklist_responses with item_id `a91-deficiency-{severity}-{index}`

### Requirement 7: 区块 5 — 审计委员会监督（可选区块）

**User Story:** As a 审计助理, I want an optional section for audit committee oversight ineffectiveness, so that I can document this finding only when applicable.

#### Acceptance Criteria

1. THE GtA91DeficiencyLetter SHALL render Section 5 (审计委员会监督) with title "三、审计委员会和内部审计机构对内部控制的监督无效"
2. THE Section 5 SHALL include an applicability control with three options: Y (适用) / N (不适用) / NA (不涉及)
3. WHEN applicability is "Y", THE Section 5 SHALL display an editable textarea for the audit committee findings description
4. WHEN applicability is "N" or "NA", THE Section 5 SHALL hide the textarea
5. WHEN the applicability selection changes, THE GtA91DeficiencyLetter SHALL debounce-save (2s) to checklist_responses with item_id `a91-committee-applicability`

### Requirement 8: 区块 6 — 签发区

**User Story:** As a 审计助理, I want the firm name auto-filled and a date picker for the issuance date, so that I can quickly complete the sign-off section.

#### Acceptance Criteria

1. THE GtA91DeficiencyLetter SHALL render Section 6 (签发区) with auto-filled firm name "致同会计师事务所（特殊普通合伙）"
2. THE Section 6 SHALL include an el-date-picker for issuance date
3. WHEN the workpaper has a linked audit report date in project context, THE date-picker SHALL use that date as default value
4. WHEN the issuance date changes, THE GtA91DeficiencyLetter SHALL debounce-save (2s) to checklist_responses with item_id `a91-signature-date`

### Requirement 9: 区块 7 — 管理层回复区

**User Story:** As a 审计助理, I want a management response section with pre-filled default text, so that I can record the client's formal response to the deficiency letter.

#### Acceptance Criteria

1. THE GtA91DeficiencyLetter SHALL render Section 7 (管理层回复区) with three sub-fields
2. THE Section 7 SHALL include: 管理层意见 (textarea), 管理层结论 (textarea with default text "同意上述贵所就独立性问题所做的声明…"), 授权代表签字 (el-input) + 日期 (el-date-picker)
3. WHEN any management response field changes, THE GtA91DeficiencyLetter SHALL debounce-save (2s) to checklist_responses with item_id `a91-response-{field_id}`
4. THE 管理层结论 textarea SHALL pre-fill the default conclusion text on first load if no saved value exists

### Requirement 10: 编制指导与导航

**User Story:** As a 审计助理, I want collapsible guidance tips and section navigation, so that I can quickly reference instructions and jump between sections.

#### Acceptance Criteria

1. THE GtA91DeficiencyLetter SHALL render template guidance notes (from Table 0 and Table 1 in the original docx) as el-collapse panels with el-alert styling
2. THE GtA91DeficiencyLetter SHALL display a left-side mini navigation (anchor links) or scrollspy showing the 7 section titles for quick navigation
3. WHEN the user clicks a navigation item, THE view SHALL smooth-scroll to the corresponding section card

### Requirement 11: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A9-1 section data pre-loaded, so that the component can render immediately without extra API calls.

#### Acceptance Criteria

1. WHEN render-config is requested for A9-1, THE A91_Render_Strategy SHALL return: section_data (7 sections with field definitions and current values), deficiency_list (from B22B grouped by severity), project_context (client_name, audit_report_date, firm_name)
2. THE A91_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a91-%' for the given project and workpaper
3. THE A91_Render_Strategy SHALL query B22B deficiency evaluation data (from B22B workpaper's checklist_responses or dedicated table) and classify by severity
4. IF the B22B workpaper does not exist for the project, THEN THE A91_Render_Strategy SHALL return an empty deficiency_list with a warning message "未找到B22B内控缺陷评价表"

### Requirement 12: 数据持久化

**User Story:** As a 审计助理, I want all my edits to be automatically saved, so that I can resume editing A9-1 at any time without data loss.

#### Acceptance Criteria

1. WHEN any editable field in GtA91DeficiencyLetter changes, THE useA91DeficiencyLetter composable SHALL debounce-save (2 seconds) the value to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format `a91-{section}-{field_id}` where section is one of: addressee, independence, deficiency, committee, signature, response
3. THE deficiency list SHALL be serialized as JSON in the remark field of checklist_responses (one record per severity group)
4. WHEN a save succeeds, THE GtA91DeficiencyLetter SHALL update save status indicator to "已保存"
5. IF a save fails, THEN THE GtA91DeficiencyLetter SHALL display el-message error and mark status as "未保存"
