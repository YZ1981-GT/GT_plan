# Requirements Document

## Introduction

为 A12-1（法律事务确认函及律师回复函）创建专属 HTML 组件。原模板 36P/5T，两部分结构（发函 + 回函）。

第一部分（发函）：收件人(律师事务所+律师) → 说明段 → 三大问询事项(未决诉讼/其他法律责任/律师费) → 简化流程说明 → 公司盖章+日期 → 回函信息表。
第二部分（回函）：确认有无诉讼 → 律师费结算(未积欠/尚有未付+金额) → 律师签字+日期。

诉讼列表为动态增删（每条含案件描述/律师意见/金额估计）。联动仅做 GtIndexChip 跳转（A5-3 或有事项）。

新增 componentType: `a12-1-legal-confirmation`，通过 wp_code_overrides 保持 skip 状态。

## Glossary

- **GtA121LegalConfirmation**: 前端主组件（~450 行），渲染发函+回函 2 大区块
- **useA121LegalConfirmation**: 前端 composable，管理发函/回函数据加载/保存/诉讼列表
- **A121_Render_Strategy**: 后端渲染策略（`_a121_legal_confirmation.py`）
- **Litigation_Record**: 诉讼记录条目（案件描述/律师意见/金额估计）

## Requirements

### Requirement 1: 新 componentType 注册与路由

**User Story:** As a 前端开发者, I want A12-1 to use a dedicated componentType.

#### Acceptance Criteria

1. THE wp_code_overrides SHALL map wp_code "A12-1" to componentType "a12-1-legal-confirmation" with skip status
2. THE htmlRendererRegistry SHALL register componentType "a12-1-legal-confirmation" mapping to GtA121LegalConfirmation
3. THE RENDERER_DISPATCH SHALL include a "a12-1-legal-confirmation" strategy function
4. THE VALID_COMPONENT_TYPES list SHALL include "a12-1-legal-confirmation"

### Requirement 2: 双模式切换 UI

**User Story:** As a 审计助理, I want to switch between structured view and OnlyOffice editing.

#### Acceptance Criteria

1. WHEN the workpaper loads, THE GtA121LegalConfirmation SHALL display an el-segmented control with "结构化视图" and "在线编辑"
2. THE Mode_Switch SHALL default to "结构化视图" on initial load
3. WHEN the user clicks "在线编辑", THE GtA121LegalConfirmation SHALL render GtOnlyOfficeSheet for the docx file
4. WHILE OnlyOffice is unavailable, THE Mode_Switch SHALL disable the "在线编辑" option
5. WHEN the user switches modes, THE useA121LegalConfirmation SHALL flush all pending saves before switching

### Requirement 3: 发函收件人区块

**User Story:** As a 审计助理, I want to specify the law firm and lawyer receiving the confirmation letter.

#### Acceptance Criteria

1. THE GtA121LegalConfirmation SHALL render Part 1 header with: 律师事务所名称(el-input), 律师姓名(el-input)
2. WHEN any recipient field changes, THE useA121LegalConfirmation SHALL debounce-save (2s) with item_id `a121-send-recipient-{field}`
3. THE Send_Section SHALL display a read-only explanation paragraph below the recipient fields

### Requirement 4: 三大问询事项

**User Story:** As a 审计助理, I want to record the three inquiry items in the confirmation letter.

#### Acceptance Criteria

1. THE GtA121LegalConfirmation SHALL render 3 inquiry sections as numbered cards
2. THE Inquiry_1 (未决诉讼) SHALL contain a dynamic list of litigation records with add/delete capability
3. EACH Litigation_Record SHALL have 3 fields: 案件事实描述(textarea), 律师看法(textarea), 可能损失金额估计(el-input-number)
4. THE Inquiry_2 (其他法律责任事件) SHALL contain a textarea for description
5. THE Inquiry_3 (律师服务费结算) SHALL contain a textarea for description
6. WHEN any inquiry field changes, THE useA121LegalConfirmation SHALL debounce-save (2s) with item_id `a121-send-inquiry{N}-{field_id}`

### Requirement 5: 诉讼列表动态管理

**User Story:** As a 审计助理, I want to add/remove litigation records dynamically.

#### Acceptance Criteria

1. THE Inquiry_1 section SHALL support adding new litigation records via "添加诉讼" button
2. THE Inquiry_1 section SHALL support deleting records via row-level delete icon (with confirmation)
3. WHEN the list is empty, THE Inquiry_1 SHALL display a placeholder "无未决诉讼" with add button
4. WHEN any litigation row changes, THE useA121LegalConfirmation SHALL debounce-save (2s) with item_id `a121-send-litigation-{row_index}`
5. THE litigation record list SHALL serialize each record as JSON in checklist_responses remark field

### Requirement 6: 发函签章区

**User Story:** As a 审计助理, I want to record company seal and date for the outgoing letter.

#### Acceptance Criteria

1. THE Part_1 SHALL render a signing area with: 公司名称(auto-fill from project), 日期(el-date-picker)
2. THE Part_1 SHALL render a reply information table: 回函地址(el-input), 电话(el-input), 联系人(el-input)
3. WHEN any field changes, THE useA121LegalConfirmation SHALL debounce-save (2s) with item_id `a121-send-sign-{field_id}`

### Requirement 7: 回函确认区块

**User Story:** As a 审计助理, I want to record the lawyer's reply confirming litigation status.

#### Acceptance Criteria

1. THE GtA121LegalConfirmation SHALL render Part 2 (回函) as a visually distinct section (different card background)
2. THE Reply_Section SHALL contain an el-radio-group: "确认无诉讼" / "确认有诉讼"
3. WHEN "确认有诉讼" is selected, THE Reply_Section SHALL display a conditional textarea for details
4. WHEN reply status changes, THE useA121LegalConfirmation SHALL debounce-save (2s) with item_id `a121-reply-status`

### Requirement 8: 回函律师费结算

**User Story:** As a 审计助理, I want to record lawyer fee settlement status in the reply.

#### Acceptance Criteria

1. THE Reply_Section SHALL contain an el-radio-group for fee status: "未积欠" / "尚有未付"
2. WHEN "尚有未付" is selected, THE Reply_Section SHALL display an el-input-number for outstanding amount
3. WHEN fee status changes, THE useA121LegalConfirmation SHALL debounce-save (2s) with item_id `a121-reply-fee-{field}`

### Requirement 9: 回函签字区

**User Story:** As a 审计助理, I want to record the lawyer's signature on the reply.

#### Acceptance Criteria

1. THE Reply_Section SHALL render: 律师事务所名称(el-input), 律师签字(el-input), 日期(el-date-picker)
2. WHEN any reply sign field changes, THE useA121LegalConfirmation SHALL debounce-save (2s) with item_id `a121-reply-sign-{field}`

### Requirement 10: 跨底稿联动

**User Story:** As a 审计助理, I want to navigate to related workpapers from the confirmation letter.

#### Acceptance Criteria

1. THE GtA121LegalConfirmation SHALL render a GtIndexChip linking to A5-3 (或有事项) in the Inquiry_1 section header
2. WHEN the chip is clicked, THE Component SHALL navigate to the A5-3 workpaper

### Requirement 11: 后端渲染策略

**User Story:** As a 前端开发者, I want the render-config API to return all A12-1 data pre-loaded.

#### Acceptance Criteria

1. WHEN render-config is requested for A12-1, THE A121_Render_Strategy SHALL return: meta_info, send_section (recipient, inquiries, litigation_list, sign_info, reply_info_table), reply_section (status, fee, sign), cross_references, project_context
2. THE A121_Render_Strategy SHALL query checklist_responses with item_id LIKE 'a121-%'
3. THE A121_Render_Strategy SHALL load A5-3 workpaper ID for GtIndexChip

### Requirement 12: 数据持久化

**User Story:** As a 审计助理, I want all edits automatically saved.

#### Acceptance Criteria

1. WHEN any editable field changes, THE useA121LegalConfirmation SHALL debounce-save (2s) to checklist_responses via POST `/api/checklist-responses/batch`
2. THE save operation SHALL use item_id format: `a121-{part}-{field_id}` where part is "send" or "reply"
3. WHEN a save succeeds, THE GtA121LegalConfirmation SHALL update save status indicator to "已保存"
4. IF a save fails, THEN THE GtA121LegalConfirmation SHALL display el-message error
