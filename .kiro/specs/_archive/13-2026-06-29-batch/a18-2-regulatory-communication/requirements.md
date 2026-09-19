# Requirements Document

## Introduction

为 A18-2（与监管层沟通函）创建专属 HTML 组件，将原 26 页/2 表的 4 事项沟通函模板转化为 5 区块卡片结构化 UI。组件支持双模式（结构化视图 / OnlyOffice 在线编辑），数据持久化走 checklist_responses（item_id: `a182-{section}-{field_id}`）。

核心价值：4 个沟通事项（舞弊/违法/不一致错报/其他）各有适用性开关（Y/N/NA），不适用时隐藏 textarea，双 CPA 签发。2 个提示表格以只读折叠形式展示。

新增 componentType: `a18-2-regulatory-communication`，通过 wp_code_overrides 映射。

## Glossary

- **GtA182RegulatoryCommunication**: 前端主组件（~300 行），渲染 5 区块卡片
- **useA182RegulatoryCommunication**: 前端 composable，管理数据加载/保存/适用性状态
- **A182_Render_Strategy**: 后端渲染策略（`_a182_regulatory_communication.py`）
- **适用性开关**: 每个事项的 Y/N/NA 三态开关，控制 textarea 显隐
- **双签**: 两名注册会计师签名 + 事务所名称 + 日期

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A18-2 to use a dedicated componentType.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A18-2" to componentType "a18-2-regulatory-communication" with skip status
2. THE htmlRendererRegistry SHALL register componentType "a18-2-regulatory-communication" mapping to GtA182RegulatoryCommunication
3. THE RENDERER_DISPATCH SHALL include a "a18-2-regulatory-communication" strategy function
4. THE VALID_COMPONENT_TYPES list SHALL include "a18-2-regulatory-communication"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing for A18-2.

#### Acceptance Criteria

1. WHEN A18-2 workpaper loads, THE GtA182RegulatoryCommunication SHALL display an el-segmented control with two options: "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA182RegulatoryCommunication SHALL render GtOnlyOfficeSheet for the A18-2 docx file
4. WHILE OnlyOffice is unavailable, THE Mode_Switch SHALL disable the "在线编辑" option
5. WHEN the user switches modes, THE GtA182RegulatoryCommunication SHALL flush all pending saves before switching

### Requirement 3: 收件人区块

**User Story:** As a 审计助理, I want to select or input the regulatory authority name.

#### Acceptance Criteria

1. THE GtA182RegulatoryCommunication SHALL render a recipient card with an el-select (options: "中国证券监督管理委员会", "中国银行保险监督管理委员会", "其他") and a conditional el-input for custom authority name
2. WHEN "其他" is selected, THE Recipient_Card SHALL show an el-input for custom authority name
3. WHEN recipient changes, THE useA182RegulatoryCommunication SHALL debounce-save (2s) with item_id `a182-recipient-authority` and `a182-recipient-custom`

### Requirement 4: 引言区块

**User Story:** As a 审计助理, I want to see the introductory text for reference.

#### Acceptance Criteria

1. THE GtA182RegulatoryCommunication SHALL render an introduction section as el-collapse with two read-only paragraphs (沟通目的 + 依据说明)
2. THE Introduction_Section SHALL auto-fill client_name and audit_year from project context into placeholders

### Requirement 5: 4 事项沟通卡片

**User Story:** As a 审计助理, I want to document each communication matter with applicability control.

#### Acceptance Criteria

1. THE GtA182RegulatoryCommunication SHALL render 4 matter cards: (1)舞弊, (2)重大违反法律法规行为, (3)年度报告中信息不一致或错报, (4)其他事项
2. EACH Matter_Card SHALL display an applicability switch with 3 states: Y(适用), N(不适用), NA(不涉及)
3. WHEN applicability is Y, THE Matter_Card SHALL display a textarea (autosize, min 4 rows) for content description
4. WHEN applicability is N or NA, THE Matter_Card SHALL hide the textarea
5. WHEN applicability changes, THE useA182RegulatoryCommunication SHALL debounce-save (2s) with item_id `a182-matter{N}-applicability`
6. WHEN textarea content changes, THE useA182RegulatoryCommunication SHALL debounce-save (2s) with item_id `a182-matter{N}-content`

### Requirement 6: 签发区块（双签）

**User Story:** As a 业务合伙人, I want the dual-signature issuance section.

#### Acceptance Criteria

1. THE GtA182RegulatoryCommunication SHALL render an issuance card with: firm name (auto-fill, read-only), CPA 1 name (el-input), CPA 2 name (el-input), date (el-date-picker)
2. THE Issuance_Card SHALL auto-fill firm name from project context
3. WHEN CPA 1 name changes, THE useA182RegulatoryCommunication SHALL debounce-save (2s) with item_id `a182-sign-cpa1`
4. WHEN CPA 2 name changes, THE useA182RegulatoryCommunication SHALL debounce-save (2s) with item_id `a182-sign-cpa2`
5. WHEN date changes, THE useA182RegulatoryCommunication SHALL debounce-save (2s) with item_id `a182-sign-date`

### Requirement 7: 提示表格（只读参考）

**User Story:** As a 审计助理, I want to reference the guidance tables when needed.

#### Acceptance Criteria

1. THE GtA182RegulatoryCommunication SHALL render 2 guidance tables as el-collapse (collapsed by default)
2. THE Guidance_Tables SHALL be read-only static content (not editable, not saved)

### Requirement 8: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A18-2 data pre-loaded.

#### Acceptance Criteria

1. WHEN render-config is requested for A18-2, THE A182_Render_Strategy SHALL return: recipient, matters (4 items with applicability + content), issuance (cpa1, cpa2, date), project_context
2. THE A182_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a182-%'

### Requirement 9: 数据持久化

**User Story:** As a 审计助理, I want all my edits automatically saved.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA182RegulatoryCommunication SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a182-{section}-{field_id}`
3. WHEN a save succeeds, THE GtA182RegulatoryCommunication SHALL update save status to "已保存"
4. IF a save fails, THEN THE GtA182RegulatoryCommunication SHALL display el-message error

### Requirement 10: AI 按钮预留

**User Story:** As a 产品经理, I want an AI assist button placeholder for future integration.

#### Acceptance Criteria

1. THE GtA182RegulatoryCommunication SHALL render an AI assist button (disabled) in the toolbar area
2. THE AI_Button SHALL display tooltip "AI辅助（即将上线）"
