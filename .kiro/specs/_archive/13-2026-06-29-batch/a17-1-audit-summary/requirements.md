# Requirements Document

## Introduction

为 A17-1（重大事项概要汇总）创建专属 HTML 组件，将原 243 页/14 表的 Word 模板转化为 16 章折叠卡片 + 顶部签字表 + 左侧导航的结构化 UI。组件支持双模式（结构化视图 / OnlyOffice 在线编辑），数据持久化走 checklist_responses（item_id: `a171-{chapter}-{field_id}`）。

核心价值：审计总结的核心文档，16 章目录涵盖审计全流程要点。左侧章节导航快速跳转，每章内容为 textarea/表格/Y/N 确认。联动引用 B50 风险评估、A13 错报、A1-15 披露核对。

新增 componentType: `a17-1-audit-summary`，通过 wp_code_overrides 将 A17-1 映射为该类型（保持 skip 状态，在 A17 bundle Tab 内嵌渲染）。

## Glossary

- **GtA171AuditSummary**: 前端主组件（~800 行），渲染 16 章折叠卡片 UI
- **useA171AuditSummary**: 前端 composable，管理 16 章数据加载/保存/导航
- **useA171Navigation**: 前端 composable，管理左侧导航与 IntersectionObserver 联动
- **A171_Render_Strategy**: 后端渲染策略（`_a171_audit_summary.py`），从 checklist_responses 加载已填数据
- **Chapter_Card**: 章节折叠卡片，含章节标题 + 可编辑区域（textarea/表格/Y/N）
- **Signature_Table**: 顶部签字表（10 行 × 3 列），含编制/复核/审批/日期
- **Chapter_Nav**: 左侧 16 章导航面板

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A17-1 to use a dedicated componentType, so that the structured 16-chapter form replaces the generic word-template rendering.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A17-1" to componentType "a17-1-audit-summary" with skip status (rendered inside A17 bundle)
2. THE htmlRendererRegistry SHALL register componentType "a17-1-audit-summary" mapping to GtA171AuditSummary component
3. THE RENDERER_DISPATCH SHALL include an "a17-1-audit-summary" strategy function that invokes A171_Render_Strategy
4. THE VALID_COMPONENT_TYPES list SHALL include "a17-1-audit-summary"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing for A17-1, so that I can use the most efficient mode for my current task.

#### Acceptance Criteria

1. WHEN A17-1 workpaper loads, THE GtA171AuditSummary SHALL display an el-segmented control with two options: "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA171AuditSummary SHALL render GtOnlyOfficeSheet for the A17-1 docx file
4. WHILE OnlyOffice is unavailable (health check fails), THE Mode_Switch SHALL disable the "在线编辑" option and display tooltip "在线编辑不可用"
5. WHEN the user switches from structured view to online editor, THE GtA171AuditSummary SHALL flush all pending saves before initializing OnlyOffice

### Requirement 3: 顶部签字表

**User Story:** As a 业务合伙人, I want to see and fill the sign-off table at the top, so that I can track approval chain at a glance.

#### Acceptance Criteria

1. THE GtA171AuditSummary SHALL render a Signature_Table with 10 rows × 3 columns (角色/签名/日期)
2. THE Signature_Table SHALL include rows for: 编制人、一级复核、二级复核、三级复核、项目合伙人、质量控制复核、项目质量控制复核人、技术复核人、独立复核人、其他
3. THE Signature_Table SHALL auto-fill 编制人 from current user context
4. WHEN any signature field changes, THE useA171AuditSummary SHALL debounce-save (2s) to checklist_responses with item_id `a171-signature-{row}-{col}`

### Requirement 4: 左侧导航面板

**User Story:** As a 审计助理, I want a left-side navigation panel for 16 chapters, so that I can quickly jump to any section in this large document.

#### Acceptance Criteria

1. THE GtA171AuditSummary SHALL render a fixed-position left navigation panel listing all 16 chapter titles
2. WHEN the user clicks a navigation item, THE GtA171AuditSummary SHALL smooth-scroll to the corresponding chapter card
3. WHILE the user scrolls, THE Chapter_Nav SHALL highlight the currently visible chapter using IntersectionObserver
4. THE Chapter_Nav SHALL display a completion indicator (green dot) for chapters where all required fields are filled

### Requirement 5: 16 章折叠卡片

**User Story:** As a 审计助理, I want each chapter rendered as a collapsible card, so that I can focus on one section at a time.

#### Acceptance Criteria

1. THE GtA171AuditSummary SHALL render 16 Chapter_Cards using el-collapse with chapter titles as headers
2. THE Chapter_Cards SHALL default to all-collapsed state on initial load
3. WHEN a chapter contains unsaved changes, THE Chapter_Card header SHALL display an orange dot indicator
4. THE Chapter_Cards SHALL render chapter-specific content based on template structure (textarea, table, or Y/N fields)

### Requirement 6: 章节内容 — textarea 类型

**User Story:** As a 审计助理, I want large text areas for narrative chapters, so that I can write detailed audit summaries.

#### Acceptance Criteria

1. FOR chapters 一/二/三/四/五/七/十三/十四/十五/十六, THE Chapter_Card SHALL render an el-input type="textarea" with autosize (min 4 rows)
2. WHEN textarea content changes, THE useA171AuditSummary SHALL debounce-save (2s) to checklist_responses with item_id `a171-ch{N}-{field_id}`
3. THE textarea fields SHALL have an AI button (disabled, tooltip "AI 辅助填写即将上线")

### Requirement 7: 章节内容 — 表格类型

**User Story:** As a 审计助理, I want structured tables for tabular chapters, so that I can record information in organized format.

#### Acceptance Criteria

1. FOR chapter 六（重大错报风险应对）, THE Chapter_Card SHALL render a dynamic el-table with columns: 风险描述/应对措施/执行情况/结论
2. FOR chapter 八（已审财务报表分析）, THE Chapter_Card SHALL render a summary table with key financial metrics
3. THE table rows SHALL support dynamic add/delete operations
4. WHEN table data changes, THE useA171AuditSummary SHALL debounce-save (2s) to checklist_responses with item_id `a171-ch{N}-row{R}-{col}`

### Requirement 8: 章节内容 — Y/N 确认类型

**User Story:** As a 审计助理, I want Y/N confirmations for applicable/not-applicable questions, so that I can quickly mark section applicability.

#### Acceptance Criteria

1. FOR chapters 九/十/十一/十二, THE Chapter_Card SHALL render Y/N confirmation questions as el-radio-group
2. WHEN answer is "Y", THE Chapter_Card SHALL expand additional textarea for detailed explanation
3. WHEN answer is "N" or "不适用", THE Chapter_Card SHALL show brief reason textarea
4. WHEN the selection changes, THE useA171AuditSummary SHALL debounce-save (2s) to checklist_responses with item_id `a171-ch{N}-{field_id}`

### Requirement 9: 跨底稿联动引用

**User Story:** As a 审计助理, I want cross-references to related workpapers (B50, A13, A1-15), so that I can navigate to source data directly.

#### Acceptance Criteria

1. THE Chapter_Card 六 SHALL display GtIndexChip links to B50 risk assessment items
2. THE Chapter_Card 十四 SHALL display GtIndexChip links to A13 misstatement summary
3. THE Chapter_Card 十四 SHALL display GtIndexChip links to A1-15 disclosure checklist
4. WHEN the user clicks a GtIndexChip, THE GtA171AuditSummary SHALL emit navigation event to open the referenced workpaper

### Requirement 10: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A17-1 data pre-loaded, so that the component can render immediately.

#### Acceptance Criteria

1. WHEN render-config is requested for A17-1, THE A171_Render_Strategy SHALL return: chapters (16 chapters with field definitions and current values), signature_table (10 rows), project_context (client_name, period, preparer)
2. THE A171_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a171-%' for the given project and workpaper
3. THE table fields (chapters 6, 8) SHALL be stored as JSON arrays in the remark column of checklist_responses

### Requirement 11: 数据持久化

**User Story:** As a 审计助理, I want all my edits automatically saved, so that I can resume editing at any time without data loss.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA171AuditSummary composable SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a171-ch{N}-{field_id}` for chapter fields, `a171-signature-{row}-{col}` for signature fields
3. WHEN a save succeeds, THE GtA171AuditSummary SHALL update save status indicator to "已保存"
4. IF a save fails, THEN THE GtA171AuditSummary SHALL display el-message error and mark status as "未保存"

### Requirement 12: 自动填充项目信息

**User Story:** As a 审计助理, I want project information auto-filled, so that I don't need to manually type repetitive information.

#### Acceptance Criteria

1. THE GtA171AuditSummary SHALL auto-fill client_name from project context
2. THE GtA171AuditSummary SHALL auto-fill audit period from project context
3. THE Signature_Table 编制人 row SHALL auto-fill from current user display name
