# Requirements Document

## Introduction

为 A17-4（重大专业分歧事项记录）创建专属 HTML 组件，将原 46 页/4 表的 Word 模板转化为人员表 + 6 章卡片 + 签字区的结构化 UI。组件支持双模式（结构化视图 / OnlyOffice 在线编辑），数据持久化走 checklist_responses（item_id: `a174-{section}-{field_id}`）。

核心价值：结构化记录审计团队内部的重大专业分歧——人员动态表 + 6 章详述 + 签字区。人员表为 el-table 动态增删行。

新增 componentType: `a17-4-disagreement-record`，通过 wp_code_overrides 保持 skip 状态（在 A17 bundle Tab 内嵌渲染）。

## Glossary

- **GtA174DisagreementRecord**: 前端主组件（~400 行），渲染人员表 + 6 章卡片 + 签字区
- **useA174DisagreementRecord**: 前端 composable，管理数据加载/保存/人员表增删
- **A174_Render_Strategy**: 后端渲染策略（`_a174_disagreement_record.py`），从 checklist_responses 加载已填数据
- **Personnel_Table**: 人员表格（姓名/职位/项目角色，动态增删行）
- **Section_Card**: 章节卡片（textarea 内容区）
- **Signature_Area**: 签字区（编制人/复核人/日期）

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A17-4 to use a dedicated componentType, so that the structured disagreement record form replaces the generic word-template rendering.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A17-4" to componentType "a17-4-disagreement-record" with skip status
2. THE htmlRendererRegistry SHALL register componentType "a17-4-disagreement-record" mapping to GtA174DisagreementRecord component
3. THE RENDERER_DISPATCH SHALL include a "a17-4-disagreement-record" strategy function that invokes A174_Render_Strategy
4. THE VALID_COMPONENT_TYPES list SHALL include "a17-4-disagreement-record"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing for A17-4.

#### Acceptance Criteria

1. WHEN A17-4 workpaper loads, THE GtA174DisagreementRecord SHALL display an el-segmented control with two options: "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA174DisagreementRecord SHALL render GtOnlyOfficeSheet for the A17-4 docx file
4. WHILE OnlyOffice is unavailable, THE Mode_Switch SHALL disable the "在线编辑" option
5. WHEN the user switches modes, THE GtA174DisagreementRecord SHALL flush all pending saves before switching

### Requirement 3: 人员表格

**User Story:** As a 审计助理, I want a dynamic personnel table, so that I can list all parties involved in the disagreement.

#### Acceptance Criteria

1. THE GtA174DisagreementRecord SHALL render a Personnel_Table with columns: 序号(auto), 姓名, 职位, 项目角色
2. THE Personnel_Table SHALL support adding new rows via "添加人员" button
3. THE Personnel_Table SHALL support removing rows via row-level delete button
4. WHEN table data changes, THE useA174DisagreementRecord SHALL debounce-save (2s) with item_id `a174-personnel-row{N}-{col}`
5. THE Personnel_Table data SHALL be stored as JSON array in a single checklist_response remark (item_id `a174-personnel`)

### Requirement 4: 第一节 — 存在专业意见分歧的人员及其职位

**User Story:** As a 审计助理, I want to describe who has the disagreement.

#### Acceptance Criteria

1. THE Section_Card 一 SHALL render a textarea for describing the disagreeing parties
2. THE textarea SHALL have autosize (min 3 rows)
3. WHEN content changes, THE useA174DisagreementRecord SHALL debounce-save (2s) with item_id `a174-sec1-parties`

### Requirement 5: 第二节 — 专业意见分歧事由

**User Story:** As a 审计助理, I want to describe the cause of the disagreement.

#### Acceptance Criteria

1. THE Section_Card 二 SHALL render a textarea for describing the disagreement cause
2. THE textarea SHALL have autosize (min 4 rows)
3. WHEN content changes, THE useA174DisagreementRecord SHALL debounce-save (2s) with item_id `a174-sec2-cause`

### Requirement 6: 第三节 — 已执行的审计程序

**User Story:** As a 审计助理, I want to record the audit procedures already performed.

#### Acceptance Criteria

1. THE Section_Card 三 SHALL render a textarea for describing performed audit procedures
2. THE textarea SHALL have autosize (min 4 rows)
3. WHEN content changes, THE useA174DisagreementRecord SHALL debounce-save (2s) with item_id `a174-sec3-procedures`

### Requirement 7: 第四节 — 被审计单位和监管机构的意见

**User Story:** As a 审计助理, I want to record the auditee and regulator opinions.

#### Acceptance Criteria

1. THE Section_Card 四 SHALL render a textarea for auditee/regulator opinions
2. THE textarea SHALL have autosize (min 3 rows)
3. WHEN content changes, THE useA174DisagreementRecord SHALL debounce-save (2s) with item_id `a174-sec4-opinions`

### Requirement 8: 第五节 — 项目各层级对分歧的考虑

**User Story:** As a 业务合伙人, I want to document considerations at each project level.

#### Acceptance Criteria

1. THE Section_Card 五 SHALL render a textarea for multi-level considerations
2. THE textarea SHALL have autosize (min 4 rows)
3. WHEN content changes, THE useA174DisagreementRecord SHALL debounce-save (2s) with item_id `a174-sec5-considerations`

### Requirement 9: 第六节 — 得出的结论

**User Story:** As a 业务合伙人, I want to record the final conclusion on the disagreement.

#### Acceptance Criteria

1. THE Section_Card 六 SHALL render a textarea for conclusion
2. THE textarea SHALL have autosize (min 3 rows)
3. WHEN content changes, THE useA174DisagreementRecord SHALL debounce-save (2s) with item_id `a174-sec6-conclusion`

### Requirement 10: 签字区

**User Story:** As a 审计助理, I want a signature area with preparer/reviewer/date fields.

#### Acceptance Criteria

1. THE Signature_Area SHALL render 编制人 (auto-fill current user), 复核人 (el-input), 日期 (el-date-picker)
2. WHEN any signature field changes, THE useA174DisagreementRecord SHALL debounce-save (2s) with item_id `a174-signature-{field_id}`

### Requirement 11: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A17-4 data pre-loaded.

#### Acceptance Criteria

1. WHEN render-config is requested for A17-4, THE A174_Render_Strategy SHALL return: personnel (JSON array), sections (6 sections with current values), signature_data, project_context
2. THE A174_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a174-%'
3. THE personnel table SHALL be stored as JSON array in remark column

### Requirement 12: 数据持久化

**User Story:** As a 审计助理, I want all my edits automatically saved.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA174DisagreementRecord SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a174-personnel`, `a174-sec{N}-{field_id}`, `a174-signature-{field_id}`
3. WHEN a save succeeds, THE GtA174DisagreementRecord SHALL update save status to "已保存"
4. IF a save fails, THEN THE GtA174DisagreementRecord SHALL display el-message error and mark status as "未保存"
