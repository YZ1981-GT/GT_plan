# Requirements Document

## Introduction

为 A10-1（与治理层沟通函）创建专属 HTML 组件。原模板 162P/10T，大型多章节沟通函。

核心结构：收件人(董事会/监事会/审计委员会) → 引言(2段固定说明) → 十六个章节(textarea为主+第三章含非审计服务费表格) → 签发区(事务所+合伙人+日期) → 提示框。

设计方案：左侧章节导航 + 折叠卡片布局（类似 A17-1 大型文档模式）。联动仅做 GtIndexChip 跳转（A9-2 内控缺陷沟通函、A13 错报）。

新增 componentType: `a10-1-governance-communication`，通过 wp_code_overrides 映射。

## Glossary

- **GtA101GovernanceCommunication**: 前端主组件（~600 行），渲染 16 章节卡片 + 导航
- **useA101GovernanceCommunication**: 前端 composable，管理数据加载/保存/章节导航
- **A101_Render_Strategy**: 后端渲染策略（`_a101_governance_communication.py`）
- **Service_Fee_Table**: 第三章非审计服务费表格（5行×2列，可编辑金额）

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A10-1 to use a dedicated componentType.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A10-1" to componentType "a10-1-governance-communication" with skip status
2. THE htmlRendererRegistry SHALL register componentType "a10-1-governance-communication" mapping to GtA101GovernanceCommunication
3. THE RENDERER_DISPATCH SHALL include a "a10-1-governance-communication" strategy function
4. THE VALID_COMPONENT_TYPES list SHALL include "a10-1-governance-communication"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing.

#### Acceptance Criteria

1. WHEN the workpaper loads, THE GtA101GovernanceCommunication SHALL display an el-segmented control with "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA101GovernanceCommunication SHALL render GtOnlyOfficeSheet for the docx file
4. WHILE OnlyOffice is unavailable, THE Mode_Switch SHALL disable the "在线编辑" option
5. WHEN the user switches modes, THE useA101GovernanceCommunication SHALL flush all pending saves before switching

### Requirement 3: 左侧章节导航

**User Story:** As a 审计助理, I want quick navigation across 16 chapters of this large document.

#### Acceptance Criteria

1. THE GtA101GovernanceCommunication SHALL render a left sidebar navigation listing all 16 chapters plus header/footer sections
2. WHEN the user clicks a navigation item, THE Component SHALL smooth-scroll to the corresponding chapter card
3. WHILE the user scrolls, THE Navigation SHALL highlight the currently visible chapter (scrollspy behavior)
4. THE Navigation SHALL display chapter numbers and abbreviated titles

### Requirement 4: 收件人区块

**User Story:** As a 审计助理, I want to specify the communication recipient.

#### Acceptance Criteria

1. THE GtA101GovernanceCommunication SHALL render a recipient section with el-input for addressee (placeholder: "xx公司董事会/监事会/审计委员会")
2. WHEN recipient changes, THE useA101GovernanceCommunication SHALL debounce-save (2s) with item_id `a101-recipient`
3. THE Recipient_Section SHALL auto-fill with client_name + "董事会" from project context

### Requirement 5: 引言段

**User Story:** As a 审计助理, I want the introduction paragraphs displayed for reference.

#### Acceptance Criteria

1. THE GtA101GovernanceCommunication SHALL render 2 introduction paragraphs as read-only text (el-alert info style)
2. THE Introduction SHALL reference the audit period and client name from project context

### Requirement 6: 十六章节正文

**User Story:** As a 审计助理, I want to fill in content for each of the 16 communication chapters.

#### Acceptance Criteria

1. THE GtA101GovernanceCommunication SHALL render 16 chapter cards, each with chapter title and collapsible body
2. EACH chapter card body SHALL contain an el-input type="textarea" with autosize (min 4 rows)
3. WHEN any chapter content changes, THE useA101GovernanceCommunication SHALL debounce-save (2s) with item_id `a101-ch{N}-content` where N is 1-16
4. THE Chapter_Cards SHALL default to expanded state for chapters 1-5 and collapsed for chapters 6-16
5. EACH chapter card SHALL display a GtIndexChip where cross-reference is applicable (章九→A9-2, 章十三→A13)

### Requirement 7: 第三章非审计服务费表格

**User Story:** As a 审计助理, I want to record non-audit service fees in a structured table within Chapter 3.

#### Acceptance Criteria

1. THE Chapter_3 card SHALL contain an additional el-table with 5 rows × 2 columns (服务项目, 金额)
2. THE Service_Fee_Table SHALL have editable amount cells (el-input-number)
3. THE Service_Fee_Table rows SHALL be: 审计服务, 审阅服务, 其他鉴证服务, 税务服务, 其他服务
4. WHEN any fee amount changes, THE useA101GovernanceCommunication SHALL debounce-save (2s) with item_id `a101-ch3-fee-{row_index}`
5. THE Service_Fee_Table SHALL display a total row (auto-calculated sum, read-only)

### Requirement 8: 签发区

**User Story:** As a 业务合伙人, I want to sign the governance communication letter.

#### Acceptance Criteria

1. THE GtA101GovernanceCommunication SHALL render a signing section with: 事务所名称(auto-fill), 中国注册会计师(el-input for partner name), 日期(el-date-picker)
2. WHEN any signing field changes, THE useA101GovernanceCommunication SHALL debounce-save (2s) with item_id `a101-sign-{field_id}`
3. THE Firm_Name SHALL auto-fill from project context firm information

### Requirement 9: 提示框

**User Story:** As a 审计助理, I want to see template guidance notes.

#### Acceptance Criteria

1. THE GtA101GovernanceCommunication SHALL render a guidance tip section (el-collapse, default collapsed) at the bottom
2. THE Guidance_Section SHALL contain the Table 0 reference notes from the original template (read-only)

### Requirement 10: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A10-1 chapter data pre-loaded.

#### Acceptance Criteria

1. WHEN render-config is requested for A10-1, THE A101_Render_Strategy SHALL return: meta_info, recipient, introduction_text, chapters (16 entries with content), service_fees (5 rows), signing_section, guidance_notes, project_context
2. THE A101_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a101-%'
3. THE A101_Render_Strategy SHALL load cross-reference data for GtIndexChip rendering (A9-2, A13 workpaper IDs)

### Requirement 11: 数据持久化

**User Story:** As a 审计助理, I want all edits automatically saved.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA101GovernanceCommunication SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a101-{section}-{field_id}`
3. WHEN a save succeeds, THE GtA101GovernanceCommunication SHALL update save status indicator to "已保存"
4. IF a save fails, THEN THE GtA101GovernanceCommunication SHALL display el-message error
5. THE service fee table rows SHALL serialize as JSON in checklist_responses remark field
