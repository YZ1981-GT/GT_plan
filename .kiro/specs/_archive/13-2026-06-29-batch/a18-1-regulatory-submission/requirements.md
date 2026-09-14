# Requirements Document

## Introduction

为 A18-1（向监管部门报送审计小结的函）创建专属 HTML 组件，将原 17 页/0 表的极简信函模板转化为 3 区块卡片结构化 UI。组件支持双模式（结构化视图 / OnlyOffice 在线编辑），数据持久化走 checklist_responses（item_id: `a181-{field_id}`）。

核心价值：极简信函格式——收件人 + 正文（固定说明 + 联系人） + 签发区。自动从项目上下文填充公司名、年度、合伙人。

新增 componentType: `a18-1-regulatory-submission`，通过 wp_code_overrides 映射（保持 skip 状态，在父组件内嵌渲染或独立访问）。

## Glossary

- **GtA181RegulatorySubmission**: 前端主组件（~150 行），渲染 3 区块卡片
- **useA181RegulatorySubmission**: 前端 composable，管理数据加载/保存
- **A181_Render_Strategy**: 后端渲染策略（`_a181_regulatory_submission.py`）
- **监管局名称**: 用户可编辑的监管局名称（如"北京"、"上海"等），自动拼接"中国证券监督管理委员会"前缀

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A18-1 to use a dedicated componentType.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A18-1" to componentType "a18-1-regulatory-submission" with skip status
2. THE htmlRendererRegistry SHALL register componentType "a18-1-regulatory-submission" mapping to GtA181RegulatorySubmission
3. THE RENDERER_DISPATCH SHALL include a "a18-1-regulatory-submission" strategy function
4. THE VALID_COMPONENT_TYPES list SHALL include "a18-1-regulatory-submission"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing for A18-1.

#### Acceptance Criteria

1. WHEN A18-1 workpaper loads, THE GtA181RegulatorySubmission SHALL display an el-segmented control with two options: "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA181RegulatorySubmission SHALL render GtOnlyOfficeSheet for the A18-1 docx file
4. WHILE OnlyOffice is unavailable, THE Mode_Switch SHALL disable the "在线编辑" option
5. WHEN the user switches modes, THE GtA181RegulatorySubmission SHALL flush all pending saves before switching

### Requirement 3: 收件人卡片

**User Story:** As a 审计助理, I want to input the regulatory bureau name with automatic CSRC prefix.

#### Acceptance Criteria

1. THE GtA181RegulatorySubmission SHALL render a recipient card with an el-input for bureau name (placeholder "XX监管局")
2. THE Recipient_Card SHALL display fixed prefix "中国证券监督管理委员会" before the input
3. WHEN bureau name changes, THE useA181RegulatorySubmission SHALL debounce-save (2s) with item_id `a181-recipient-bureau`

### Requirement 4: 正文卡片

**User Story:** As a 审计助理, I want the letter body with auto-filled project info and editable contact person.

#### Acceptance Criteria

1. THE GtA181RegulatorySubmission SHALL render a body card containing: two read-only paragraphs (委托说明 + 报送依据), auto-filled client_name and audit_year placeholders, and an editable contact section
2. THE Body_Card SHALL auto-fill client_name from project context into "XX公司" placeholder
3. THE Body_Card SHALL auto-fill audit_year from project context into "XX年度" placeholder
4. THE Body_Card SHALL render an el-input for contact partner name (auto-fill from partner_name context)
5. THE Body_Card SHALL render an el-input for contact phone number
6. WHEN contact partner or phone changes, THE useA181RegulatorySubmission SHALL debounce-save (2s) with item_id `a181-contact-partner` or `a181-contact-phone`
7. THE Body_Card SHALL display attachment description: "后附我所对{client_name}{audit_year}年度财务报表审计的审计情况小结"

### Requirement 5: 签发卡片

**User Story:** As a 业务合伙人, I want the issuance section with firm name auto-filled and partner signature.

#### Acceptance Criteria

1. THE GtA181RegulatorySubmission SHALL render an issuance card with: firm name (auto-fill, read-only), partner signature (el-input), and date (el-date-picker)
2. THE Issuance_Card SHALL auto-fill firm name from project context
3. WHEN partner signature changes, THE useA181RegulatorySubmission SHALL debounce-save (2s) with item_id `a181-sign-partner`
4. WHEN date changes, THE useA181RegulatorySubmission SHALL debounce-save (2s) with item_id `a181-sign-date`

### Requirement 6: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A18-1 data pre-loaded.

#### Acceptance Criteria

1. WHEN render-config is requested for A18-1, THE A181_Render_Strategy SHALL return: recipient (bureau), body (contact_partner, contact_phone), issuance (partner, date), project_context
2. THE A181_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a181-%'

### Requirement 7: 数据持久化

**User Story:** As a 审计助理, I want all my edits automatically saved.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA181RegulatorySubmission SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a181-{section}-{field_id}`
3. WHEN a save succeeds, THE GtA181RegulatorySubmission SHALL update save status to "已保存"
4. IF a save fails, THEN THE GtA181RegulatorySubmission SHALL display el-message error

### Requirement 8: AI 按钮预留

**User Story:** As a 产品经理, I want an AI assist button placeholder for future integration.

#### Acceptance Criteria

1. THE GtA181RegulatorySubmission SHALL render an AI assist button (disabled) in the toolbar area
2. THE AI_Button SHALL display tooltip "AI辅助（即将上线）"
