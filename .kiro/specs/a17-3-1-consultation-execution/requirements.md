# Requirements Document

## Introduction

为 A17-3-1（业务咨询结果执行情况记录）创建专属 HTML 组件，将原 4 页/1 表的极简 Word 模板（9 行 × 4 列表格）转化为 5 区块卡片（元信息 + 4 章）的结构化 UI。组件支持双模式（结构化视图 / OnlyOffice 在线编辑），数据持久化走 checklist_responses（item_id: `a1731-{section}-{field_id}`）。

核心价值：极简表格结构，记录咨询结果的执行落实情况。联动引用 A17-3 的咨询事项内容。

新增 componentType: `a17-3-1-consultation-execution`，通过 wp_code_overrides 保持 skip 状态（在 A17 bundle Tab 内嵌渲染）。

## Glossary

- **GtA1731ConsultationExecution**: 前端主组件（~250 行），渲染 5 区块卡片
- **useA1731ConsultationExecution**: 前端 composable，管理数据加载/保存
- **A1731_Render_Strategy**: 后端渲染策略（`_a1731_consultation_execution.py`），从 checklist_responses 加载已填数据
- **Meta_Info_Card**: 元信息区块（办公室/客户/类型/期间）
- **Section_Card**: 章节卡片

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A17-3-1 to use a dedicated componentType, so that the structured execution record form replaces the generic word-template rendering.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A17-3-1" to componentType "a17-3-1-consultation-execution" with skip status
2. THE htmlRendererRegistry SHALL register componentType "a17-3-1-consultation-execution" mapping to GtA1731ConsultationExecution component
3. THE RENDERER_DISPATCH SHALL include a "a17-3-1-consultation-execution" strategy function that invokes A1731_Render_Strategy
4. THE VALID_COMPONENT_TYPES list SHALL include "a17-3-1-consultation-execution"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing for A17-3-1.

#### Acceptance Criteria

1. WHEN A17-3-1 workpaper loads, THE GtA1731ConsultationExecution SHALL display an el-segmented control with two options: "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA1731ConsultationExecution SHALL render GtOnlyOfficeSheet for the A17-3-1 docx file
4. WHILE OnlyOffice is unavailable, THE Mode_Switch SHALL disable the "在线编辑" option
5. WHEN the user switches modes, THE GtA1731ConsultationExecution SHALL flush all pending saves before switching

### Requirement 3: 元信息区块

**User Story:** As a 审计助理, I want the meta information auto-filled from project context.

#### Acceptance Criteria

1. THE GtA1731ConsultationExecution SHALL render a Meta_Info_Card with fields: 办公室, 客户名称, 咨询类型, 审计期间
2. THE Meta_Info_Card SHALL auto-fill 客户名称 from project client_name and 审计期间 from project period
3. WHEN any meta field changes, THE useA1731ConsultationExecution SHALL debounce-save (2s) with item_id `a1731-meta-{field_id}`

### Requirement 4: 第一节 — 咨询事项描述（引用 A17-3）

**User Story:** As a 审计助理, I want the consultation matter description to reference A17-3, so that I can see the original consultation context.

#### Acceptance Criteria

1. THE Section_Card 一 SHALL render a read-only reference area showing A17-3 consultation matter summary
2. THE Section_Card 一 SHALL display a GtIndexChip link to "A17-3" for cross-navigation
3. THE Section_Card 一 SHALL include an optional editable textarea for supplementary notes
4. WHEN supplementary notes change, THE useA1731ConsultationExecution SHALL debounce-save (2s) with item_id `a1731-sec1-notes`

### Requirement 5: 第二节 — 咨询结果

**User Story:** As a 审计助理, I want to record the consultation result.

#### Acceptance Criteria

1. THE Section_Card 二 SHALL render a textarea for consultation result
2. THE textarea SHALL have autosize (min 3 rows)
3. WHEN content changes, THE useA1731ConsultationExecution SHALL debounce-save (2s) with item_id `a1731-sec2-result`

### Requirement 6: 第三节 — 执行情况

**User Story:** As a 审计助理, I want to record how the consultation result was implemented.

#### Acceptance Criteria

1. THE Section_Card 三 SHALL render a textarea for execution details
2. THE textarea SHALL have autosize (min 3 rows)
3. WHEN content changes, THE useA1731ConsultationExecution SHALL debounce-save (2s) with item_id `a1731-sec3-execution`

### Requirement 7: 第四节 — 结论

**User Story:** As a 现场经理, I want to record the final conclusion.

#### Acceptance Criteria

1. THE Section_Card 四 SHALL render a textarea for conclusion
2. THE textarea SHALL have autosize (min 2 rows)
3. WHEN content changes, THE useA1731ConsultationExecution SHALL debounce-save (2s) with item_id `a1731-sec4-conclusion`

### Requirement 8: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A17-3-1 data pre-loaded.

#### Acceptance Criteria

1. WHEN render-config is requested for A17-3-1, THE A1731_Render_Strategy SHALL return: meta_info (4 fields), sections (4 sections with current values), a173_reference (summary from A17-3), project_context
2. THE A1731_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a1731-%'
3. THE A1731_Render_Strategy SHALL also query A17-3 checklist_responses (item_id LIKE 'a173-sec1-%') to populate the reference area

### Requirement 9: 数据持久化

**User Story:** As a 审计助理, I want all my edits automatically saved.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA1731ConsultationExecution SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a1731-meta-{field_id}`, `a1731-sec{N}-{field_id}`
3. WHEN a save succeeds, THE GtA1731ConsultationExecution SHALL update save status to "已保存"
4. IF a save fails, THEN THE GtA1731ConsultationExecution SHALL display el-message error and mark status as "未保存"
