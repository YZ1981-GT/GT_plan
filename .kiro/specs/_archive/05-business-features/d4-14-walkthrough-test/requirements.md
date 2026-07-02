# D4-14 营业收入发生检查表（穿行测试）升级 — 需求文档

## Introduction

D4-14 是 D4 营业收入循环中最关键的底稿——多维穿行测试矩阵。源模板为 30+ 列超宽表，每行代表一笔交易的完整证据链追溯：记账凭证 → 销售合同 → 出库单 → 运输单 → 签收单 → 发票 → 其他支持性文件。

当前实现（D4TabOccurrence.vue）是一个简化的凭证抽样表（12列），仅记录 Y/N 标志，丢失了多维度的详细检查数据（各维度编号/品名/金额/日期/审批人等）和自动一致性校验能力。

本次升级将其重构为与 D4-12 合同检查表相似的"事项卡片 + 矩阵视图 + 在线编辑"三模式组件，每笔交易作为一个事项卡片，内部按 7 个证据链维度分组，支持独立附件上传、OCR 识别、自动交叉校验和 AI 穿行分析。

## Glossary

- **Walkthrough_Test_System**: D4-14 穿行测试组件，负责管理交易事项的多维度证据链检查
- **Transaction_Item**: 一笔被检查的交易事项（穿行测试矩阵中的一行），包含 7 个证据链维度的完整数据
- **Evidence_Dimension**: 证据链维度，共 7 个：记账凭证、销售合同、出库单、运输单、签收单、发票、其他支持性文件
- **Consistency_Engine**: 一致性校验引擎，自动交叉比对各维度的金额/品名/日期数据
- **Matrix_View**: 矩阵视图，横向展示所有事项 × 纵向展示各维度检查状态的只读对比表
- **Card_View**: 事项卡片视图，每笔交易一个卡片，内部按维度分组展示详细字段
- **Walkthrough_AI**: AI 穿行分析模块，基于全维度数据判断交易真实性并识别异常

## Requirements

### Requirement 1: 三模式 UI 切换

**User Story:** As a 审计助理, I want to switch between card view, matrix view, and online editing mode, so that I can choose the most effective way to review walkthrough test data.

#### Acceptance Criteria

1. THE Walkthrough_Test_System SHALL provide three editor modes: card view, matrix view, and online editing (OnlyOffice)
2. WHEN the user selects a mode via el-segmented, THE Walkthrough_Test_System SHALL switch to the corresponding view without data loss
3. WHEN OnlyOffice is unhealthy, THE Walkthrough_Test_System SHALL disable the online editing option and display a tooltip indicating unavailability
4. THE Walkthrough_Test_System SHALL persist the last selected mode within the current session

### Requirement 2: 事项卡片视图

**User Story:** As a 审计助理, I want each transaction displayed as a card grouped by evidence dimensions, so that I can systematically verify all supporting documents for one transaction.

#### Acceptance Criteria

1. THE Card_View SHALL display each Transaction_Item as a separate card with an index number prefix "D4-14-{N}"
2. THE Card_View SHALL organize fields within each card into 7 evidence dimension groups: 记账凭证, 销售合同, 出库单, 运输单, 签收单, 发票, 其他支持性文件
3. WHEN the user clicks "添加事项", THE Walkthrough_Test_System SHALL prompt for a label via ElMessageBox.prompt before creating the card
4. THE Card_View SHALL support horizontal switching between cards via el-tabs (card style)
5. WHEN there are no Transaction_Items, THE Walkthrough_Test_System SHALL display an empty state with guidance text

### Requirement 3: 记账凭证维度字段

**User Story:** As a 审计助理, I want the voucher dimension to capture month, date, number, product name, quantity, amount, and date, so that I can trace the transaction back to the original accounting entry.

#### Acceptance Criteria

1. THE Card_View SHALL provide the following fields for the 记账凭证 dimension: 月份, 日期, 编号, 品名, 数量, 金额, 记账日期
2. WHEN a field value is modified, THE Walkthrough_Test_System SHALL trigger debounced auto-save within 2 seconds
3. THE Walkthrough_Test_System SHALL support importing voucher data from tb_ledger (序时账) to pre-fill the 记账凭证 dimension

### Requirement 4: 销售合同维度字段与 D4-12 联动

**User Story:** As a 审计助理, I want the sales contract dimension to reference contracts already inspected in D4-12, so that I avoid redundant data entry and ensure cross-referencing.

#### Acceptance Criteria

1. THE Card_View SHALL provide the following fields for the 销售合同 dimension: 编号, 品名, 金额, 签发审批, 签收确认
2. WHEN the user clicks "引用D4-12合同", THE Walkthrough_Test_System SHALL display a picker showing all contracts from the D4-12 inspection (reading from allResponses key "D4-12-contracts-v2")
3. WHEN a D4-12 contract is selected, THE Walkthrough_Test_System SHALL auto-fill the contract dimension fields (编号, 品名, 金额) from the referenced contract data
4. THE Card_View SHALL display a GtIndexChip linking to "wp:D4-12" next to the contract dimension header

### Requirement 5: 出库单/运输单/签收单/发票维度字段

**User Story:** As a 审计助理, I want dedicated fields for each document type in the evidence chain, so that I can record verification details for delivery, shipping, receipt, and invoicing.

#### Acceptance Criteria

1. THE Card_View SHALL provide the following fields for the 出库单 dimension: 日期, 品名, 金额, 仓库保管员
2. THE Card_View SHALL provide the following fields for the 运输单 dimension: 日期, 品名, 金额
3. THE Card_View SHALL provide the following fields for the 签收单 dimension: 日期, 品名, 金额
4. THE Card_View SHALL provide the following fields for the 发票 dimension: 日期, 编号, 金额
5. THE Card_View SHALL provide the following fields for the 其他支持性文件 dimension: 文件描述, 索引号

### Requirement 6: 维度级独立附件上传与 OCR

**User Story:** As a 审计助理, I want to upload supporting documents for each evidence dimension independently, so that OCR can extract and auto-fill dimension-specific fields.

#### Acceptance Criteria

1. THE Card_View SHALL provide an upload button (📎) for each Evidence_Dimension within a Transaction_Item
2. WHEN a file is uploaded for a dimension, THE Walkthrough_Test_System SHALL call the `/d4/contract-ocr` endpoint and display a processing indicator
3. WHEN OCR completes successfully, THE Walkthrough_Test_System SHALL extract dimension-relevant fields and present them in a confirmation dialog before filling
4. IF OCR fails, THEN THE Walkthrough_Test_System SHALL display a "failed" tag and provide a "重新识别" retry button
5. THE Walkthrough_Test_System SHALL support PDF, PNG, JPG, and JPEG files with a maximum size of 20MB per upload

### Requirement 7: 自动一致性校验

**User Story:** As a 审计助理, I want the system to automatically cross-check amounts, product names, and dates across all dimensions, so that I can quickly identify discrepancies in the evidence chain.

#### Acceptance Criteria

1. WHEN a Transaction_Item has data in two or more dimensions, THE Consistency_Engine SHALL cross-compare the 金额 fields across all populated dimensions
2. WHEN a Transaction_Item has data in two or more dimensions, THE Consistency_Engine SHALL cross-compare the 品名 fields across all populated dimensions
3. WHEN a Transaction_Item has data in two or more dimensions, THE Consistency_Engine SHALL cross-compare the 日期 fields across all populated dimensions
4. WHEN a discrepancy is detected, THE Consistency_Engine SHALL highlight the inconsistent field with a red border and display a tooltip showing the expected vs. actual values
5. THE Consistency_Engine SHALL compute a per-item consistency score (percentage of matching fields across dimensions)

### Requirement 8: 矩阵视图

**User Story:** As a 现场经理, I want a matrix overview showing all transactions with dimension-level check status, so that I can quickly assess the completeness and consistency of the walkthrough test.

#### Acceptance Criteria

1. THE Matrix_View SHALL display a table where rows represent Transaction_Items and columns represent Evidence_Dimensions
2. THE Matrix_View SHALL show ✓/× indicators for each dimension based on whether required fields are populated
3. THE Matrix_View SHALL display the 金额 value for each dimension and highlight amount discrepancies with a warning icon
4. THE Matrix_View SHALL display a consistency score per row (from the Consistency_Engine)
5. THE Matrix_View SHALL display a 检查结论 column showing per-item conclusion (Y/N/NA)
6. THE Matrix_View SHALL be read-only (data modification only via Card_View)

### Requirement 9: 抽样参数区

**User Story:** As a 审计助理, I want to configure and display sampling parameters, so that I can document the sampling methodology used for the walkthrough test.

#### Acceptance Criteria

1. THE Walkthrough_Test_System SHALL provide input fields for: 总体, 特定项目, 抽样总体, 抽样方法, 目标样本量
2. THE Walkthrough_Test_System SHALL compute and display 已检查数量 (count of Transaction_Items) and progress percentage
3. WHEN 已检查数量 reaches 目标样本量, THE Walkthrough_Test_System SHALL display a completion indicator
4. THE Walkthrough_Test_System SHALL reserve integration points for the voucher-sampling-engine component (props interface)

### Requirement 10: 从序时账导入

**User Story:** As a 审计助理, I want to import voucher entries from the ledger (tb_ledger), so that I can quickly populate the 记账凭证 dimension without manual transcription.

#### Acceptance Criteria

1. WHEN the user clicks "从序时账导入", THE Walkthrough_Test_System SHALL call the backend to retrieve ledger entries matching the project's revenue accounts
2. THE Walkthrough_Test_System SHALL display a selection dialog showing available ledger entries with columns: 日期, 凭证号, 摘要, 金额
3. WHEN entries are selected and confirmed, THE Walkthrough_Test_System SHALL create Transaction_Items with the 记账凭证 dimension pre-filled
4. IF no ledger data is available, THEN THE Walkthrough_Test_System SHALL display a message "暂无可导入的序时账数据"

### Requirement 11: AI 穿行分析

**User Story:** As a 审计助理, I want AI to analyze the complete evidence chain and assess transaction authenticity, so that I can identify potential fraud or anomalies more efficiently.

#### Acceptance Criteria

1. WHEN the user clicks "AI穿行分析" for a Transaction_Item, THE Walkthrough_AI SHALL collect all populated dimension data and send to the `/d4/ai-generate` endpoint with section "walkthrough-analysis"
2. THE Walkthrough_AI SHALL return an analysis covering: 交易真实性判断, 证据链完整性评价, 金额一致性评价, 时间线合理性, 异常风险提示
3. WHEN AI analysis identifies anomalies, THE Walkthrough_Test_System SHALL mark the Transaction_Item as potentially anomalous and display the AI reasoning
4. IF AI service is unavailable, THEN THE Walkthrough_Test_System SHALL disable the "AI穿行分析" button and show a tooltip "AI 服务暂不可用"

### Requirement 12: 检查结论与汇总统计

**User Story:** As a 现场经理, I want summary statistics including total checked amount, coverage rate, anomaly rate, and materiality comparison, so that I can evaluate the adequacy of the walkthrough test.

#### Acceptance Criteria

1. THE Walkthrough_Test_System SHALL compute and display: 合计金额 (sum of 记账凭证 dimension amounts), 本期发生额 (from trial_balance), 检查比例 (合计/发生额), 重要性水平 (from allResponses)
2. THE Walkthrough_Test_System SHALL display an anomaly rate (count of items with discrepancies / total items)
3. WHEN 检查比例 is below 60%, THE Walkthrough_Test_System SHALL display a warning indicator
4. THE Walkthrough_Test_System SHALL provide per-item 检查结论 field with options: 无异常, 存在差异已解释, 存在重大异常

### Requirement 13: 审计说明与审计结论

**User Story:** As a 审计助理, I want dedicated sections for audit notes and conclusions with AI assistance, so that I can document findings and form an opinion on the occurrence assertion.

#### Acceptance Criteria

1. THE Walkthrough_Test_System SHALL provide an el-card section "审计意见区" containing 审计说明 textarea and 审计结论 textarea
2. WHEN the user clicks "AI辅助" for 审计说明, THE Walkthrough_Test_System SHALL call `/d4/ai-generate` with section "adj-note" and walkthrough context (sampling params, anomaly rate, consistency scores)
3. WHEN the user clicks "AI辅助" for 审计结论, THE Walkthrough_Test_System SHALL call `/d4/ai-generate` with section "adj-conclusion" and walkthrough context
4. THE Walkthrough_Test_System SHALL display AI-generated text in a confirmation dialog before filling into the textarea

### Requirement 14: 编制提示

**User Story:** As a 审计助理, I want to reference the 6 compilation tips from the source template, so that I understand the methodology and focus areas for the walkthrough test.

#### Acceptance Criteria

1. THE Walkthrough_Test_System SHALL display 6 compilation tips in a `<details>` collapsible section at the bottom
2. THE Walkthrough_Test_System SHALL style the tips section with a red left border and light red background (matching source template red-text format)
3. THE Walkthrough_Test_System SHALL default the tips section to collapsed state

### Requirement 15: 溯源跳转与关联

**User Story:** As a 审计助理, I want quick navigation links to related workpapers, so that I can trace cross-references in the audit evidence chain.

#### Acceptance Criteria

1. THE Walkthrough_Test_System SHALL display GtIndexChip components linking to: wp:D4-1 (审定表), wp:D4-12 (合同检查), wp:D4-4 (调整分录)
2. WHEN a GtIndexChip is clicked, THE Walkthrough_Test_System SHALL navigate to the referenced workpaper
3. THE Walkthrough_Test_System SHALL display a "复核" button that invokes the review dialog (inject openReviewDialog)

### Requirement 16: 持久化

**User Story:** As a 审计助理, I want all walkthrough test data to be automatically saved, so that I never lose my work.

#### Acceptance Criteria

1. THE Walkthrough_Test_System SHALL persist Transaction_Items as a JSON array under item_id "D4-14-transactions"
2. THE Walkthrough_Test_System SHALL persist sampling parameters under item_id "D4-14-sampling"
3. THE Walkthrough_Test_System SHALL persist audit note under item_id "D4-14-note" and conclusion under item_id "D4-14-conclusion"
4. WHEN any data changes, THE Walkthrough_Test_System SHALL debounce save operations with a 2-second delay
5. THE Walkthrough_Test_System SHALL dispatch CustomEvent "d4:save-items" with the items payload and update allResponses Map

### Requirement 17: 导入导出

**User Story:** As a 审计助理, I want to export/import walkthrough test data via Excel, so that I can work offline or exchange data with colleagues.

#### Acceptance Criteria

1. THE Walkthrough_Test_System SHALL provide an el-dropdown "导入导出 ▾" menu with options: 导出模板, 导出数据, 导入数据
2. WHEN "导出模板" is clicked, THE Walkthrough_Test_System SHALL call the backend `/d4/export-template?sheet=营业收入发生检查表D4-14` to download an xlsx template with guidance
3. WHEN "导出数据" is clicked, THE Walkthrough_Test_System SHALL call `/d4/export-data?sheet=营业收入发生检查表D4-14` to download current data as xlsx
4. WHEN "导入数据" is clicked, THE Walkthrough_Test_System SHALL accept an xlsx file upload and call `/d4/import-data?sheet=营业收入发生检查表D4-14` to parse and load data
5. THE Walkthrough_Test_System SHALL use the useD4ImportExport composable for all import/export operations
