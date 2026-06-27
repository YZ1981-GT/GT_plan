# Requirements Document

## Introduction

为 A17-2-1（关键审计事项 KAM）创建专属 HTML 组件，将原 31 页/5 表的 Word 模板转化为 KAM 动态增删卡片列表的结构化 UI。组件支持双模式（结构化视图 / OnlyOffice 在线编辑），数据持久化走 checklist_responses（item_id: `a1721-{kam_index}-{field_id}`）。

核心价值：KAM 列表为动态增删卡片，每个 KAM 含 6 个核心字段（基本情况+会计政策+认定原因+审计应对+审计结果+底稿索引）。第四节为适用性开关（不存在/不沟通关键审计事项）。联动 A17-1 第十二章。

新增 componentType: `a17-2-1-kam`，通过 wp_code_overrides 保持 skip 状态（在 A17 bundle Tab 内嵌渲染）。

## Glossary

- **GtA1721Kam**: 前端主组件（~500 行），渲染 KAM 动态卡片列表
- **useA1721Kam**: 前端 composable，管理 KAM 增删/数据加载/保存
- **A1721_Render_Strategy**: 后端渲染策略（`_a1721_kam.py`），从 checklist_responses 加载已填数据
- **KAM_Card**: 关键审计事项卡片，含 6 个 textarea 字段 + 索引号
- **KAM_Candidate_Table**: 第一节 KAM 候选清单表格
- **Applicability_Switch**: 第四节适用性开关（不存在/不沟通 KAM 时整体禁用）

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A17-2-1 to use a dedicated componentType, so that the structured KAM form replaces the generic word-template rendering.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A17-2-1" to componentType "a17-2-1-kam" with skip status
2. THE htmlRendererRegistry SHALL register componentType "a17-2-1-kam" mapping to GtA1721Kam component
3. THE RENDERER_DISPATCH SHALL include a "a17-2-1-kam" strategy function that invokes A1721_Render_Strategy
4. THE VALID_COMPONENT_TYPES list SHALL include "a17-2-1-kam"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing for A17-2-1, so that I can use the most efficient mode.

#### Acceptance Criteria

1. WHEN A17-2-1 workpaper loads, THE GtA1721Kam SHALL display an el-segmented control with two options: "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA1721Kam SHALL render GtOnlyOfficeSheet for the A17-2-1 docx file
4. WHILE OnlyOffice is unavailable, THE Mode_Switch SHALL disable the "在线编辑" option and display tooltip "在线编辑不可用"
5. WHEN the user switches modes, THE GtA1721Kam SHALL flush all pending saves before switching

### Requirement 3: 第一节 — KAM 候选清单表格

**User Story:** As a 业务合伙人, I want to see and edit a KAM candidate list table, so that I can identify which items qualify as KAM.

#### Acceptance Criteria

1. THE GtA1721Kam SHALL render a KAM_Candidate_Table as the first section with columns: 序号/事项描述/风险等级/是否沟通/原因
2. THE KAM_Candidate_Table rows SHALL support dynamic add/delete operations
3. WHEN the "是否沟通" column value is "是", THE corresponding row SHALL be highlighted and linked to section 二
4. WHEN table data changes, THE useA1721Kam SHALL debounce-save (2s) with item_id `a1721-candidates-row{N}-{col}`

### Requirement 4: 第二节 — KAM 详情卡片列表

**User Story:** As a 业务合伙人, I want to fill detailed KAM information in card format, so that each KAM has complete documentation.

#### Acceptance Criteria

1. THE GtA1721Kam SHALL render a dynamic list of KAM_Cards for section 二
2. EACH KAM_Card SHALL contain 6 textarea fields: 基本情况, 会计政策及重大会计估计, 认定为关键审计事项的原因, 审计应对措施, 审计结果, 底稿索引号
3. THE KAM_Card list SHALL support adding new KAM via "添加关键审计事项" button
4. THE KAM_Card list SHALL support removing KAM via card-level delete button with confirmation dialog
5. WHEN any KAM field changes, THE useA1721Kam SHALL debounce-save (2s) with item_id `a1721-kam{N}-{field_id}`
6. THE 底稿索引号 field SHALL render as GtIndexChip for cross-reference navigation

### Requirement 5: 第三节 — 附注披露引用

**User Story:** As a 审计助理, I want to list note disclosures per KAM, so that the linkage to financial statement notes is documented.

#### Acceptance Criteria

1. THE GtA1721Kam SHALL render a section 三 with one textarea per KAM for note disclosure references
2. THE note disclosure section SHALL automatically create entries matching the number of KAMs in section 二
3. WHEN note content changes, THE useA1721Kam SHALL debounce-save (2s) with item_id `a1721-notes-{kam_index}`

### Requirement 6: 第四节 — 适用性开关

**User Story:** As a 业务合伙人, I want an applicability switch for when no KAM exists, so that I can document the absence of KAM.

#### Acceptance Criteria

1. THE GtA1721Kam SHALL render a section 四 with el-switch labeled "不存在/不沟通关键审计事项"
2. WHEN the switch is ON, THE sections 二 and 三 SHALL be hidden (not rendered) and a textarea for reason SHALL appear
3. WHEN the switch is OFF, THE sections 二 and 三 SHALL be visible and editable
4. WHEN the switch changes, THE useA1721Kam SHALL save with item_id `a1721-applicability`

### Requirement 7: 联动 A17-1 第十二章

**User Story:** As a 审计助理, I want KAM data to be referenced from A17-1 chapter 12, so that the audit summary links to detailed KAM documentation.

#### Acceptance Criteria

1. WHEN KAM data is saved, THE useA1721Kam SHALL emit EventBus event KAM_UPDATED with KAM count and summaries
2. THE GtA1721Kam SHALL display a GtIndexChip reference to "A17-1 第十二章" for cross-navigation

### Requirement 8: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A17-2-1 data pre-loaded.

#### Acceptance Criteria

1. WHEN render-config is requested for A17-2-1, THE A1721_Render_Strategy SHALL return: candidates (table rows), kams (array of KAM objects with 6 fields each), notes (per-KAM note disclosures), applicability (switch state + reason), project_context
2. THE A1721_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a1721-%'
3. THE KAM detail fields SHALL be stored in remark column as JSON objects

### Requirement 9: 数据持久化

**User Story:** As a 审计助理, I want all my edits automatically saved.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA1721Kam SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a1721-candidates-row{N}-{col}`, `a1721-kam{N}-{field_id}`, `a1721-notes-{N}`, `a1721-applicability`
3. WHEN a save succeeds, THE GtA1721Kam SHALL update save status to "已保存"
4. IF a save fails, THEN THE GtA1721Kam SHALL display el-message error and mark status as "未保存"

### Requirement 10: 自动填充项目信息

**User Story:** As a 审计助理, I want project information auto-filled.

#### Acceptance Criteria

1. THE GtA1721Kam SHALL auto-fill client_name from project context
2. THE GtA1721Kam SHALL auto-fill audit period from project context
