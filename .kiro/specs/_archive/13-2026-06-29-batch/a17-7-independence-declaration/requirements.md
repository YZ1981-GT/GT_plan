# Requirements Document

## Introduction

为 A17-7（审计项目团队成员独立性声明书）和 A17-7A（专业技术委员会审核委员独立性声明书）创建专属 HTML 组件。两个变体共用一个组件（variant prop 切换）。

A17-7 适用所有项目组成员，A17-7A 仅适用专业技术委员会审核委员。原模板 A17-7(99P/27T) + A17-7A(81P/23T)。

核心内容：声明正文(公司/年度自动填) → 独立性期间承诺(2时间段) → 团队成员签字表(动态行) → 合伙人及负责经理声明(Y/N) → 附件独立性威胁记录(经济利益/贷款担保/商业关系，可选) → 编制指导(5条，el-collapse)。

新增 componentType: `a17-7-independence-declaration`，通过 wp_code_overrides 保持 skip 状态（在 A17 bundle Tab 内嵌渲染）。

## Glossary

- **GtA177IndependenceDeclaration**: 前端主组件（~400 行），渲染 5 区块
- **useA177IndependenceDeclaration**: 前端 composable，管理数据加载/保存/签字表操作
- **A177_Render_Strategy**: 后端渲染策略（`_a177_independence_declaration.py`）
- **Independence_Period**: 独立性承诺期间（业务期间 + 财报期间）
- **Threat_Record**: 独立性威胁记录（经济利益/贷款担保/商业关系三类表格）

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A17-7/A17-7A to use a dedicated componentType with variant support.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A17-7" to componentType "a17-7-independence-declaration" with skip status
2. THE wp_code_overrides SHALL map wp_code "A17-7A" to componentType "a17-7-independence-declaration" with skip status
3. THE htmlRendererRegistry SHALL register componentType "a17-7-independence-declaration" mapping to GtA177IndependenceDeclaration
4. THE RENDERER_DISPATCH SHALL include a "a17-7-independence-declaration" strategy function
5. THE VALID_COMPONENT_TYPES list SHALL include "a17-7-independence-declaration"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing.

#### Acceptance Criteria

1. WHEN the workpaper loads, THE GtA177IndependenceDeclaration SHALL display an el-segmented control with "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA177IndependenceDeclaration SHALL render GtOnlyOfficeSheet for the docx file
4. WHILE OnlyOffice is unavailable, THE Mode_Switch SHALL disable the "在线编辑" option
5. WHEN the user switches modes, THE useA177IndependenceDeclaration SHALL flush all pending saves before switching

### Requirement 3: Variant 切换

**User Story:** As a 前端开发者, I want a single component to handle both A17-7 and A17-7A variants.

#### Acceptance Criteria

1. THE GtA177IndependenceDeclaration SHALL accept a variant prop: 'team' (A17-7) or 'committee' (A17-7A)
2. WHEN variant is 'team', THE Component SHALL display title "审计项目团队成员独立性声明书"
3. WHEN variant is 'committee', THE Component SHALL display title "专业技术委员会审核委员独立性声明书"
4. THE item_id prefix SHALL be "a177-" for variant 'team' and "a177a-" for variant 'committee'

### Requirement 4: 声明正文与期间承诺区块

**User Story:** As a 审计助理, I want declaration text auto-filled with project info and commitment periods with date pickers.

#### Acceptance Criteria

1. THE GtA177IndependenceDeclaration SHALL render a declaration section with auto-filled company name and audit year from project context
2. THE Declaration_Section SHALL display fixed statement text (read-only)
3. THE GtA177IndependenceDeclaration SHALL render 2 date-range pickers for: 业务期间 (business period) and 财务报告期间 (financial report period)
4. WHEN any date changes, THE useA177IndependenceDeclaration SHALL debounce-save (2s) with item_id `{prefix}period-{field_id}`

### Requirement 5: 团队成员签字表

**User Story:** As a 现场经理, I want all team members to sign the independence declaration with dynamic row management.

#### Acceptance Criteria

1. THE GtA177IndependenceDeclaration SHALL render a dynamic table with columns: 序号, 姓名, 签字, 日期
2. WHEN the workpaper loads, THE useA177IndependenceDeclaration SHALL pre-fill team member names from project assignments data
3. THE Table SHALL support adding new rows via "添加成员" button
4. THE Table SHALL support deleting rows via row-level delete icon (with confirmation)
5. WHEN any row changes, THE useA177IndependenceDeclaration SHALL debounce-save (2s) with item_id `{prefix}sign-{row_index}`
6. THE Table SHALL display a minimum of 1 row (empty placeholder when no members)

### Requirement 6: 合伙人及负责经理声明与签字

**User Story:** As a 业务合伙人, I want to confirm team independence and sign.

#### Acceptance Criteria

1. THE GtA177IndependenceDeclaration SHALL render a partner declaration area with Y/N radio for independence confirmation
2. WHEN N is selected, THE Component SHALL show a conditional textarea for explanation
3. THE Partner_Sign_Table SHALL contain 2 fixed rows: 合伙人 and 负责经理 (columns: 角色, 姓名, 签字, 日期)
4. WHEN partner declaration changes, THE useA177IndependenceDeclaration SHALL debounce-save (2s) with item_id `{prefix}partner-{field_id}`

### Requirement 7: 附件独立性威胁记录

**User Story:** As a 审计助理, I want to optionally record independence threats in structured tables.

#### Acceptance Criteria

1. THE GtA177IndependenceDeclaration SHALL render an expandable attachment section (el-collapse, default collapsed)
2. THE Attachment_Section SHALL contain 3 dynamic tables: 经济利益记录, 贷款担保记录, 商业关系记录
3. EACH threat table SHALL support dynamic row add/delete
4. THE 经济利益记录 table SHALL have columns: 成员姓名, 利益类型, 金额, 处理措施
5. THE 贷款担保记录 table SHALL have columns: 成员姓名, 贷款类型, 金额, 处理措施
6. THE 商业关系记录 table SHALL have columns: 成员姓名, 关系描述, 处理措施
7. WHEN any threat row changes, THE useA177IndependenceDeclaration SHALL debounce-save (2s) with item_id `{prefix}threat-{type}-{row_index}`

### Requirement 8: 编制指导

**User Story:** As a 审计助理, I want to reference preparation guidance notes.

#### Acceptance Criteria

1. THE GtA177IndependenceDeclaration SHALL render 5 guidance notes in el-collapse panels (default collapsed)
2. THE Guidance_Notes SHALL be read-only reference text
3. THE Guidance_Collapse SHALL display title "编制指导" with note count badge

### Requirement 9: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A17-7 data pre-loaded including team assignments.

#### Acceptance Criteria

1. WHEN render-config is requested for A17-7, THE A177_Render_Strategy SHALL return: meta_info, declaration_text, period_data, team_sign_table, partner_section, threat_records, guidance_notes, project_context
2. THE A177_Render_Strategy SHALL query checklist_responses with item_id LIKE '{prefix}%'
3. THE A177_Render_Strategy SHALL query project assignments to provide team_members list for pre-fill
4. WHEN variant is determined by wp_code (A17-7→team, A17-7A→committee), THE Strategy SHALL set variant field in response

### Requirement 10: 数据持久化

**User Story:** As a 审计助理, I want all edits automatically saved.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA177IndependenceDeclaration SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `{prefix}{section}-{field_id}` where prefix is "a177-" or "a177a-"
3. WHEN a save succeeds, THE GtA177IndependenceDeclaration SHALL update save status indicator to "已保存"
4. IF a save fails, THEN THE GtA177IndependenceDeclaration SHALL display el-message error
5. THE team sign table rows SHALL serialize as JSON in checklist_responses remark field
