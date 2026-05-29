# 需求文档：第一阶段MVP核心 — 数据导入+科目映射+四表联动+试算表+调整分录+重要性水平

## 简介

本文档定义审计作业平台第一阶段MVP核心功能的需求，目标是跑通一个单户审计项目的数据处理全流程。涵盖六大核心模块：项目初始化向导（基本信息→科目导入→科目映射→重要性水平→团队分工→底稿模板集）、数据导入与校验、科目映射、四表联动穿透查询、试算表（四列结构）、审计调整分录管理（AJE+RJE）、重要性水平计算。本阶段依赖第零阶段已搭建的技术基础设施（PostgreSQL、Redis、FastAPI、Vue 3骨架、JWT认证、权限框架）。

## 术语表

- **Platform（审计作业平台）**：面向会计师事务所的本地私有化审计全流程作业系统
- **Auditor（审计员）**：执行审计程序、编制底稿、录入调整分录的项目组成员
- **Manager（项目经理）**：负责项目管理、复核底稿质量、审批调整分录的项目负责人
- **Partner（签字合伙人）**：对审计报告承担最终签字责任的合伙人
- **Project_Wizard（项目初始化向导）**：引导式项目创建流程，包含基本信息、科目导入、科目映射、重要性水平、团队分工、底稿模板集等步骤
- **Account_Chart（标准科目表）**：系统内置的标准审计科目体系，包含科目编码、名称、借贷方向、级次、类别（资产/负债/权益/收入/成本/费用）
- **Account_Mapping（科目映射）**：将被审计单位原始科目映射到标准审计科目的对照关系，支持多对一映射
- **Import_Engine（数据导入引擎）**：负责解析、校验和导入财务数据（科目余额表、序时账、辅助余额表、辅助明细账）的后端服务模块
- **Validation_Engine（校验引擎）**：在数据导入过程中执行借贷平衡、期初期末勾稽、科目完整性等校验规则的引擎
- **TB_Balance（科目余额表）**：记录各科目年初余额、本期借方发生额、本期贷方发生额、期末余额的汇总表，存储于 `tb_balance` 表
- **TB_Ledger（序时账）**：按时间顺序记录每笔会计凭证明细的账簿，存储于 `tb_ledger` 表
- **TB_Aux_Balance（辅助余额表）**：按客户/供应商/部门/项目等辅助维度汇总的科目余额表，存储于 `tb_aux_balance` 表
- **TB_Aux_Ledger（辅助明细账）**：凭证明细级的辅助核算记录，存储于 `tb_aux_ledger` 表
- **Four_Table_Drilldown（四表联动穿透）**：从科目余额表穿透到序时账、辅助余额表、辅助明细账的逐级查询能力
- **Trial_Balance（试算表）**：以四列结构（未审数/RJE调整/AJE调整/审定数）展示各科目审计前后金额变化的核心工作表，存储于 `trial_balance` 表
- **AJE（审计调整分录）**：Audit Journal Entry，审计师发现的需要被审计单位调整账面的分录，影响财务报表数据
- **RJE（重分类调整分录）**：Reclassification Journal Entry，仅在审计报表层面进行的科目重分类，不影响被审计单位账面
- **Adjustment（审计调整）**：AJE和RJE的统称，存储于 `adjustments` 表
- **Materiality（重要性水平）**：贯穿整个审计的核心参数，包含整体重要性水平、实际执行的重要性水平、明显微小错报临界值，存储于 `materiality` 表
- **Unadjusted_Amount（未审数）**：被审计单位账面原始金额，即导入数据经科目映射后的标准科目口径余额
- **Audited_Amount（审定数）**：经审计调整后的最终金额，计算公式为：未审数 + RJE调整 + AJE调整

## 需求

### 需求 1：项目初始化向导

**用户故事：** 作为项目经理，我希望通过引导式向导创建审计项目并完成关键配置，以便项目创建时不遗漏科目导入、科目映射、重要性水平等关键步骤。

#### 验收标准

1. THE Project_Wizard SHALL provide a step-by-step guided flow with the following ordered steps: basic information, account chart import, account mapping, materiality level, team assignment, and workpaper template set
2. WHEN Manager fills in basic information, THE Project_Wizard SHALL require: client name, audit period (year), project type (annual/special/ipo/internal_control), applicable accounting standard (enterprise/small_enterprise/financial/government), signing partner, and project manager
3. WHEN Manager completes basic information and clicks next, THE Project_Wizard SHALL create a project record in `projects` table with status "created" and persist the data so that the wizard can be resumed later
4. THE Project_Wizard SHALL allow Manager to navigate back to any previously completed step and modify the saved data
5. WHEN Manager exits the wizard before completion, THE Project_Wizard SHALL preserve all data entered in completed steps so that the wizard can be resumed from the last incomplete step
6. WHEN Manager reaches the confirmation step, THE Project_Wizard SHALL display a summary of all configured items including: basic information, account mapping completion rate, materiality levels, team members and their assigned audit cycles, and selected workpaper template set
7. WHEN Manager confirms project creation on the summary step, THE Project_Wizard SHALL update the project status from "created" to "planning"
8. IF a required step has incomplete mandatory fields, THEN THE Project_Wizard SHALL prevent navigation to subsequent dependent steps and display a validation message indicating the missing fields

### 需求 2：标准科目表管理与科目导入

**用户故事：** 作为项目经理，我希望系统内置标准科目模板并支持导入被审计单位的原始科目表，以便后续进行科目映射和标准化取数。

#### 验收标准

1. THE Platform SHALL provide built-in standard account chart templates for enterprise accounting standards containing first-level and second-level accounts with the following attributes per account: account code, account name, debit/credit direction, level (hierarchy depth), and category (asset/liability/equity/revenue/cost/expense)
2. WHEN Manager selects an accounting standard in the project wizard, THE Platform SHALL load the corresponding standard account chart template as the project's target account chart
3. WHEN Manager uploads an Excel/CSV file containing the client's original account chart, THE Import_Engine SHALL parse the file and extract account code, account name, debit/credit direction, and parent account code for each account
4. IF the uploaded account chart file has missing required columns (account code or account name), THEN THE Import_Engine SHALL reject the import and return a specific error message listing the missing columns
5. THE Platform SHALL store the imported client account chart in the `account_chart` table with `project_id`, `source` field marked as "client", and all parsed attributes
6. WHEN the client account chart is successfully imported, THE Platform SHALL display the imported accounts in a tree structure grouped by account category, showing the total count of imported accounts

### 需求 3：科目映射

**用户故事：** 作为项目经理，我希望系统能自动建议科目映射关系并支持人工调整，以便将被审计单位的原始科目统一映射到标准审计科目，实现底稿和报表的标准化取数。

#### 验收标准

1. WHEN the client account chart has been imported, THE Platform SHALL automatically generate mapping suggestions by matching client account codes and names against the standard account chart using code prefix matching and name similarity algorithms
2. THE Platform SHALL display the mapping result in a three-column layout: client original account (left), mapping status indicator (center), and standard account (right), with unmatched accounts highlighted in yellow
3. WHEN Manager selects a client account and assigns it to a standard account, THE Account_Mapping SHALL save the mapping relationship in the `account_mapping` table with fields: project_id, original_account_code, original_account_name, standard_account_code, and mapping_type (auto/manual)
4. THE Account_Mapping SHALL support many-to-one mapping where multiple client accounts map to a single standard account
5. WHEN Manager confirms all mappings, THE Platform SHALL calculate and display the mapping completion rate as: (number of mapped accounts / total client accounts) × 100%
6. IF any client accounts with non-zero balances remain unmapped, THEN THE Platform SHALL display a warning listing the unmapped accounts and their balances, and prevent proceeding to the next wizard step until all accounts with balances are mapped
7. THE Platform SHALL allow Manager to modify existing mappings at any time after the initial mapping is confirmed, and recalculate all dependent data (trial balance, reports) after mapping changes
8. FOR ALL mapped accounts, applying the mapping and then looking up the original account code SHALL return the correct standard account code (round-trip consistency)

#### 3.1 报表行次映射（余额表→报表科目对应）

9. THE Platform SHALL provide a report line mapping interface using the `report_line_mapping` table with fields: `id` (UUID PK), `project_id` (UUID FK), `standard_account_code` (varchar, not null), `report_type` (enum: balance_sheet/income_statement/cash_flow, not null), `report_line_code` (varchar, not null, the report line item code), `report_line_name` (varchar, not null, e.g. "应收账款", "营业收入"), `report_line_level` (integer, 1 for primary line items, 2 for secondary), `parent_line_code` (varchar, nullable, parent line for level-2 items), `mapping_type` (enum: ai_suggested/manual/reference_copied, not null), `is_confirmed` (boolean, default false), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK); with composite index on (project_id, report_type, standard_account_code)
10. WHEN the account mapping (Requirement 3.1-3.8) is completed, THE Platform SHALL invoke an AI matching service to automatically generate report line mapping suggestions by analyzing standard account codes, account names, and account categories against the standard report line structure, and save the suggestions with mapping_type="ai_suggested" and is_confirmed=false
11. THE Platform SHALL display the AI-suggested report line mappings in a confirmation interface showing: standard account (left), suggested report line (right, with confidence score), and a confirm/reject/reassign action for each row; Manager must confirm each mapping (is_confirmed=true) before the mapping takes effect in trial balance and report generation
12. WHEN a project belongs to a group (has parent company in `companies` table) and another company in the same group already has confirmed report line mappings, THE Platform SHALL provide a "一键参照" (one-click reference) function that copies the confirmed mappings from the reference company to the current company, setting mapping_type="reference_copied" and is_confirmed=false, allowing Manager to review and confirm
13. THE Platform SHALL validate reference copy compatibility: WHEN copying mappings from a reference company, THE Platform SHALL only copy mappings for standard account codes that exist in both companies' account charts, and flag any accounts in the current company that have no corresponding mapping in the reference company
14. THE Platform SHALL persist report line mappings across project years: WHEN creating a new year project for the same client, THE Platform SHALL automatically inherit the prior year's confirmed report line mappings, requiring Manager to only handle newly added accounts

### 需求 4：数据导入与校验

**用户故事：** 作为项目经理，我希望能从主流财务软件导入四表数据（科目余额表、序时账、辅助余额表、辅助明细账）并自动执行校验规则，以便确保导入数据的准确性和完整性。

#### 验收标准

1. THE Import_Engine SHALL support importing data from the following sources via Excel/CSV file upload: Yonyou U8/T+, Kingdee K3/KIS, SAP, and a generic standard template provided by the system
2. THE Import_Engine SHALL support importing four types of financial data: account balance sheet (tb_balance), general ledger (tb_ledger), auxiliary balance sheet (tb_aux_balance), and auxiliary detail ledger (tb_aux_ledger)
3. WHEN Manager uploads data files, THE Import_Engine SHALL execute the import as an asynchronous background task and return a task ID immediately so that the frontend is not blocked
4. WHILE the import task is running, THE Platform SHALL display real-time progress including: current processing stage (parsing/validating/importing), number of records processed, and elapsed time
5. THE Import_Engine SHALL import 100,000 journal entries within 3 minutes including all validation rule execution
6. WHEN the import task completes, THE Import_Engine SHALL generate an import log recording: import timestamp, data source type, file name, record counts per table, validation results summary, and operator user ID

#### 4.1 校验规则

7. WHEN importing general ledger data, THE Validation_Engine SHALL verify debit-credit balance for each voucher: the sum of debit amounts equals the sum of credit amounts for each unique voucher number and date combination
8. IF any voucher fails the debit-credit balance check, THEN THE Validation_Engine SHALL reject the entire import and return a list of unbalanced vouchers with their voucher numbers, dates, debit totals, and credit totals
9. WHEN importing account balance data, THE Validation_Engine SHALL verify the opening-closing reconciliation for each account: opening balance + debit amount - credit amount = closing balance (for debit-direction accounts) or opening balance - debit amount + credit amount = closing balance (for credit-direction accounts)
10. IF any account fails the opening-closing reconciliation, THEN THE Validation_Engine SHALL flag the account with a warning, allow the import to proceed, and record the discrepancy in the import log
11. THE Validation_Engine SHALL verify account completeness: every account code appearing in the balance sheet must exist in the project's account chart (either standard or client chart)
12. IF any account codes in the balance sheet do not exist in the account chart, THEN THE Validation_Engine SHALL add them to an "unmapped accounts" queue and prompt Manager to supplement the account chart or mapping
13. THE Validation_Engine SHALL verify year consistency: the fiscal year in the imported data must match the project's audit period year
14. IF the imported data year does not match the project year, THEN THE Validation_Engine SHALL reject the entire import with error message "导入数据年度({data_year})与项目年度({project_year})不匹配"
15. THE Validation_Engine SHALL detect duplicate records: the same voucher number + voucher date combination must not be imported twice for the same project and year
16. IF duplicate records are detected, THEN THE Validation_Engine SHALL prompt Manager to choose: skip duplicates or overwrite existing records
17. WHEN both balance sheet and general ledger data have been imported, THE Validation_Engine SHALL verify ledger-balance reconciliation: the sum of debit amounts and credit amounts in the general ledger grouped by account code must equal the corresponding debit and credit period amounts in the balance sheet
18. IF the ledger-balance reconciliation finds discrepancies, THEN THE Validation_Engine SHALL flag the discrepant accounts with warnings, allow the import to proceed, and record the differences in the import log
19. WHEN both auxiliary balance data and main balance data have been imported, THE Validation_Engine SHALL verify auxiliary-main reconciliation: the sum of auxiliary balances for each account code must equal the corresponding main account balance
20. IF the auxiliary-main reconciliation finds discrepancies, THEN THE Validation_Engine SHALL flag the discrepant accounts with warnings and record the differences in the import log

#### 4.2 导入后处理

21. WHEN data import completes successfully, THE Import_Engine SHALL automatically apply existing account mappings to all imported balance data, converting original account codes to standard account codes
22. WHEN data import completes, THE Import_Engine SHALL identify accounts that have no mapping and add them to a pending mapping queue visible in the account mapping interface
23. THE Import_Engine SHALL support full import rollback: Manager can undo an entire import batch, removing all records imported in that batch from all affected tables
24. FOR ALL successfully imported and mapped data, exporting the trial balance and re-importing it SHALL produce equivalent account balances (round-trip data integrity)

### 需求 5：四表联动穿透查询

**用户故事：** 作为审计员，我希望能从科目余额表逐级穿透到序时账、辅助余额表和辅助明细账，以便快速定位和核查具体交易明细。

#### 验收标准

1. THE Platform SHALL display the account balance sheet (TB_Balance) as the primary entry point, showing for each account: account code, account name, opening balance, debit period amount, credit period amount, and closing balance
2. WHEN Auditor clicks on an account row in the balance sheet, THE Platform SHALL display a drill-down panel showing the general ledger (TB_Ledger) entries filtered by that account code, sorted by voucher date ascending
3. WHEN Auditor clicks on an account that has auxiliary accounting dimensions, THE Platform SHALL display the auxiliary balance sheet (TB_Aux_Balance) grouped by the applicable dimensions (customer/supplier/department/project)
4. WHEN Auditor clicks on a specific auxiliary balance row, THE Platform SHALL display the auxiliary detail ledger (TB_Aux_Ledger) entries for that account and dimension value combination
5. THE Four_Table_Drilldown SHALL complete any single drill-down query within 2 seconds when the project contains up to 100,000 journal entries
6. THE Platform SHALL display each general ledger entry with the following fields: voucher date, voucher number, account code, account name, debit amount, credit amount, counterpart account, summary/description, and preparer
7. THE Platform SHALL support filtering the general ledger view by: date range, amount range (minimum and maximum), voucher number, summary keyword search, and counterpart account
8. THE Platform SHALL support filtering the account balance sheet by: account category (asset/liability/equity/revenue/cost/expense), account level, and keyword search on account name
9. WHEN Auditor navigates from a drill-down view back to the parent view, THE Platform SHALL preserve the scroll position and filter state of the parent view

### 需求 6：试算表（四列结构）

**用户故事：** 作为审计员，我希望系统自动生成四列结构的试算表（未审数/RJE调整/AJE调整/审定数），以便清晰展示每个科目从账面原始金额到审计最终金额的调整过程。

#### 验收标准

1. THE Trial_Balance SHALL display four columns for each standard account: unadjusted amount (未审数), RJE adjustment total (重分类调整), AJE adjustment total (审计调整), and audited amount (审定数)
2. THE Trial_Balance SHALL calculate the unadjusted amount for each standard account by summing the closing balances of all client accounts mapped to that standard account via the account mapping
3. THE Trial_Balance SHALL calculate the RJE adjustment total for each standard account by summing all RJE-type adjustment entries affecting that account
4. THE Trial_Balance SHALL calculate the AJE adjustment total for each standard account by summing all AJE-type adjustment entries affecting that account
5. THE Trial_Balance SHALL calculate the audited amount using the formula: audited amount = unadjusted amount + RJE adjustment total + AJE adjustment total
6. WHEN any adjustment entry is created, modified, or deleted, THE Trial_Balance SHALL automatically recalculate the affected accounts within 5 seconds for a project with up to 500 accounts
7. THE Trial_Balance SHALL display accounts grouped by category (asset/liability/equity/revenue/cost/expense) with subtotals for each category
8. THE Trial_Balance SHALL verify that total debits equal total credits for: unadjusted amounts, RJE adjustments, AJE adjustments, and audited amounts, and display a balance check indicator (balanced/unbalanced) for each column
9. WHEN Auditor clicks on the RJE or AJE adjustment amount for a specific account, THE Trial_Balance SHALL display a list of all adjustment entries contributing to that total
10. WHEN Auditor clicks on the unadjusted amount for a specific account, THE Trial_Balance SHALL navigate to the four-table drill-down view for that account
11. THE Trial_Balance SHALL support exporting to Excel format preserving the four-column structure, account grouping, and subtotals
12. THE Trial_Balance full recalculation SHALL complete within 5 seconds for a project with 500 accounts including all AJE and RJE adjustments

### 需求 7：审计调整分录管理（AJE + RJE）

**用户故事：** 作为审计员，我希望能在独立的分录编辑界面中录入、编辑和管理审计调整分录（AJE）和重分类调整分录（RJE），科目选择基于报表一级/二级科目下拉联动，以便保证科目标准统一，并驱动试算表、底稿和报表的自动更新。

#### 验收标准

1. THE Platform SHALL provide an adjustment entry form with the following fields: adjustment type (AJE or RJE), adjustment number (auto-generated sequential), description/explanation, and one or more debit/credit line items each containing: standard account code, account name (auto-filled from account chart), debit amount, and credit amount
2. WHEN Auditor submits a new adjustment entry, THE Platform SHALL validate that the total debit amount equals the total credit amount across all line items
3. IF the debit-credit totals of an adjustment entry are not equal, THEN THE Platform SHALL reject the submission and display the difference amount
4. WHEN a new adjustment entry is saved, THE Platform SHALL automatically update the Trial_Balance for all affected accounts and record the creator user ID and creation timestamp
5. THE Platform SHALL display AJE and RJE entries in separate tabs with a combined view option, each showing: adjustment number, type (AJE/RJE), description, total amount, creator, creation date, and review status
6. THE Platform SHALL support the following review statuses for each adjustment entry: draft (草稿), pending review (待复核), approved (已批准), rejected (已驳回)
7. WHEN Manager changes the review status of an adjustment entry to "approved", THE Platform SHALL record the reviewer user ID and review timestamp
8. WHEN Manager changes the review status to "rejected", THE Platform SHALL require a rejection reason and record it along with the reviewer user ID and timestamp
9. THE Platform SHALL allow Auditor to edit or delete adjustment entries that are in "draft" or "rejected" status
10. THE Platform SHALL prevent modification or deletion of adjustment entries that are in "approved" status
11. WHEN an adjustment entry is deleted, THE Platform SHALL perform a soft delete (set is_deleted flag) and automatically recalculate the Trial_Balance for all affected accounts
12. THE Platform SHALL display a summary panel showing: total number of AJE entries, total number of RJE entries, total AJE debit/credit amounts, total RJE debit/credit amounts, and counts by review status
13. FOR ALL adjustment entries, the sum of debit amounts SHALL equal the sum of credit amounts (debit-credit balance invariant preserved across all CRUD operations)

#### 7.1 科目下拉选择与标准化

14. WHEN Auditor adds a debit/credit line item in the adjustment entry form, THE Platform SHALL provide a two-level cascading dropdown for account selection: the first level shows report line items (一级科目, e.g. "应收账款", "营业收入") sourced from the confirmed `report_line_mapping` where report_line_level=1; the second level shows the standard accounts (二级科目) mapped under the selected report line item
15. THE Platform SHALL also support direct manual input of standard account codes in the account field, with auto-complete suggestions from the project's `account_chart` (source=standard); WHEN a manually entered code matches a standard account, THE Platform SHALL auto-fill the account name
16. THE Platform SHALL enforce that all adjustment entry line items use standard account codes that exist in the project's `account_chart`, rejecting any non-existent account codes with error message "科目编码{code}不存在于标准科目表中"
17. THE Platform SHALL store each adjustment line item in the `adjustment_entries` table (independent detail table) with fields: `id` (UUID PK), `adjustment_id` (UUID FK to adjustments header), `entry_group_id` (UUID, groups all lines of the same entry), `line_no` (integer, sequential within group), `standard_account_code` (varchar, not null), `account_name` (varchar, auto-filled), `report_line_code` (varchar, nullable, the report line this account maps to), `debit_amount` (numeric(20,2), default 0), `credit_amount` (numeric(20,2), default 0), `is_deleted` (boolean, default false), `created_at`, `updated_at`

#### 7.2 底稿调用调整分录

18. THE Platform SHALL support workpaper-level adjustment summary: for each working paper (D-N cycle) that corresponds to one or more report line items, THE Platform SHALL provide an "审定表" (audit determination sheet) view that automatically aggregates all AJE and RJE entries affecting the working paper's associated accounts, displaying: unadjusted amount (from trial balance), individual AJE adjustment details (entry number + amount per entry), individual RJE adjustment details (entry number + amount per entry), and audited amount (= unadjusted + sum of AJE + sum of RJE)
19. THE Platform SHALL link adjustment entries to working papers through the account-to-cycle mapping: each adjustment line item's standard_account_code maps to an audit cycle via the `account_chart` category, and each working paper belongs to an audit cycle via `wp_index.audit_cycle`, enabling automatic aggregation of relevant adjustments per working paper
20. THE Platform SHALL support bidirectional drill-through between adjustments and working papers: clicking an adjustment entry in the list navigates to the working paper(s) that reference it; clicking an adjustment amount in a working paper's audit determination sheet navigates to the adjustment entry detail

### 需求 8：重要性水平计算

**用户故事：** 作为项目经理，我希望系统能根据选定的基准自动计算重要性水平三级指标，以便为审计抽样范围和错报评价提供量化标准。

#### 验收标准

1. THE Platform SHALL provide a materiality calculation interface within the project wizard and as a standalone accessible page, with the following configurable inputs: benchmark type (pre-tax profit / revenue / total assets / net assets / custom), benchmark amount (numeric input or auto-populated from imported trial balance data), and percentage for overall materiality
2. WHEN Manager selects a benchmark type and the trial balance data has been imported, THE Platform SHALL auto-populate the benchmark amount from the corresponding trial balance figure
3. THE Platform SHALL calculate three materiality levels: overall materiality = benchmark amount × percentage, performance materiality = overall materiality × performance ratio (configurable, default 50%-75%), and clearly trivial threshold = overall materiality × trivial ratio (configurable, default 5%)
4. THE Platform SHALL store the materiality calculation in the `materiality` table with fields: project_id, year, benchmark_type, benchmark_amount, overall_percentage, overall_materiality, performance_ratio, performance_materiality, trivial_ratio, trivial_threshold, calculated_by (user_id), calculated_at (timestamp), and notes (text for documenting the rationale)
5. WHEN Manager adjusts any input parameter (benchmark type, amount, or percentages), THE Platform SHALL immediately recalculate all three materiality levels and display the updated values
6. THE Platform SHALL allow Manager to manually override any calculated materiality level and require a text explanation for the override reason
7. WHEN the materiality level is confirmed, THE Platform SHALL make the three materiality values available to other modules: trial balance (for highlighting accounts exceeding materiality), adjustment entries (for flagging adjustments below the trivial threshold), and future sampling modules
8. THE Platform SHALL display a materiality summary card on the project dashboard showing: benchmark type, benchmark amount, overall materiality, performance materiality, and clearly trivial threshold
9. IF Manager changes the materiality level after it has been initially confirmed, THEN THE Platform SHALL record the change history including: previous values, new values, change reason, changed_by, and changed_at

### 需求 9：数据表Schema定义（第一阶段核心表）

**用户故事：** 作为开发者，我希望第一阶段核心数据表的Schema明确定义，以便通过Alembic迁移脚本创建表结构并支持后续业务功能开发。

#### 验收标准

1. THE Migration_Framework SHALL create the `account_chart` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `account_code` (varchar, not null), `account_name` (varchar, not null), `direction` (enum: debit/credit), `level` (integer, account hierarchy depth), `category` (enum: asset/liability/equity/revenue/cost/expense), `parent_code` (varchar, nullable), `source` (enum: standard/client), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (project_id, account_code, source)
2. THE Migration_Framework SHALL create the `account_mapping` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `original_account_code` (varchar, not null), `original_account_name` (varchar), `standard_account_code` (varchar, not null), `mapping_type` (enum: auto/manual), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users); with composite unique index on (project_id, original_account_code)
3. THE Migration_Framework SHALL create the `tb_balance` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer, not null), `company_code` (varchar, not null), `account_code` (varchar, not null), `account_name` (varchar), `opening_balance` (numeric(20,2)), `debit_amount` (numeric(20,2)), `credit_amount` (numeric(20,2)), `closing_balance` (numeric(20,2)), `currency_code` (varchar, default 'CNY'), `import_batch_id` (UUID), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite index on (project_id, year, account_code)
4. THE Migration_Framework SHALL create the `tb_ledger` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer), `company_code` (varchar), `voucher_date` (date, not null), `voucher_no` (varchar, not null), `account_code` (varchar, not null), `account_name` (varchar), `debit_amount` (numeric(20,2)), `credit_amount` (numeric(20,2)), `counterpart_account` (varchar), `summary` (text), `preparer` (varchar), `currency_code` (varchar, default 'CNY'), `import_batch_id` (UUID), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite index on (project_id, year, voucher_date, voucher_no) and index on (project_id, year, account_code)
5. THE Migration_Framework SHALL create the `tb_aux_balance` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer), `company_code` (varchar), `account_code` (varchar, not null), `aux_type` (varchar, not null, e.g. customer/supplier/department/project), `aux_code` (varchar), `aux_name` (varchar), `opening_balance` (numeric(20,2)), `debit_amount` (numeric(20,2)), `credit_amount` (numeric(20,2)), `closing_balance` (numeric(20,2)), `currency_code` (varchar, default 'CNY'), `import_batch_id` (UUID), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite index on (project_id, year, account_code, aux_type)
6. THE Migration_Framework SHALL create the `tb_aux_ledger` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer), `company_code` (varchar), `voucher_date` (date), `voucher_no` (varchar), `account_code` (varchar, not null), `aux_type` (varchar), `aux_code` (varchar), `aux_name` (varchar), `debit_amount` (numeric(20,2)), `credit_amount` (numeric(20,2)), `summary` (text), `preparer` (varchar), `currency_code` (varchar, default 'CNY'), `import_batch_id` (UUID), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite index on (project_id, year, account_code, aux_type)
7. THE Migration_Framework SHALL create the `adjustments` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer, not null), `company_code` (varchar, not null), `adjustment_no` (varchar, not null, auto-generated), `adjustment_type` (enum: AJE/RJE, not null), `description` (text), `account_code` (varchar, not null, standard account code), `account_name` (varchar), `debit_amount` (numeric(20,2), default 0), `credit_amount` (numeric(20,2), default 0), `entry_group_id` (UUID, not null, groups debit/credit lines of the same entry), `review_status` (enum: draft/pending_review/approved/rejected, default draft), `reviewer_id` (UUID FK to users, nullable), `reviewed_at` (timestamp, nullable), `rejection_reason` (text, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users), `updated_by` (UUID FK to users); with composite index on (project_id, year, adjustment_type) and index on (project_id, entry_group_id)
8. THE Migration_Framework SHALL create the `trial_balance` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer, not null), `company_code` (varchar, not null), `standard_account_code` (varchar, not null), `account_name` (varchar), `account_category` (enum: asset/liability/equity/revenue/cost/expense), `unadjusted_amount` (numeric(20,2), default 0), `rje_adjustment` (numeric(20,2), default 0), `aje_adjustment` (numeric(20,2), default 0), `audited_amount` (numeric(20,2), default 0), `opening_balance` (numeric(20,2), default 0), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (project_id, year, company_code, standard_account_code)
9. THE Migration_Framework SHALL create the `materiality` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer, not null), `benchmark_type` (varchar, not null), `benchmark_amount` (numeric(20,2)), `overall_percentage` (numeric(5,4)), `overall_materiality` (numeric(20,2)), `performance_ratio` (numeric(5,4)), `performance_materiality` (numeric(20,2)), `trivial_ratio` (numeric(5,4)), `trivial_threshold` (numeric(20,2)), `is_override` (boolean, default false), `override_reason` (text, nullable), `notes` (text, nullable), `calculated_by` (UUID FK to users), `calculated_at` (timestamp), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (project_id, year)
10. THE Migration_Framework SHALL create the `import_batches` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer), `source_type` (varchar, e.g. yonyou/kingdee/sap/generic), `file_name` (varchar), `data_type` (varchar, e.g. balance/ledger/aux_balance/aux_ledger), `record_count` (integer), `status` (enum: processing/completed/failed/rolled_back), `validation_summary` (jsonb), `started_at` (timestamp), `completed_at` (timestamp), `created_by` (UUID FK to users), `created_at`; with index on (project_id, year)

### 需求 10：联动逻辑与数据一致性

**用户故事：** 作为审计员，我希望调整分录的变更能自动驱动试算表更新，试算表数据能反向穿透到科目余额和凭证，以便实现"调整变→试算变→报表变"和"报表→科目→凭证"的双向联动。

#### 验收标准

1. WHEN a new adjustment entry is created and saved, THE Platform SHALL recalculate the trial balance for all standard accounts affected by the adjustment within 5 seconds
2. WHEN an existing adjustment entry is modified, THE Platform SHALL recalculate the trial balance by removing the old adjustment amounts and applying the new amounts for all affected accounts
3. WHEN an adjustment entry is deleted (soft delete), THE Platform SHALL recalculate the trial balance by removing the deleted adjustment amounts from all affected accounts
4. WHEN account mapping is modified (an original account is remapped to a different standard account), THE Platform SHALL recalculate the unadjusted amounts in the trial balance for both the old and new standard accounts
5. WHEN new financial data is imported for a project that already has trial balance data, THE Platform SHALL recalculate all unadjusted amounts in the trial balance based on the updated balance data and existing mappings
6. THE Platform SHALL maintain the invariant: for each standard account, audited_amount = unadjusted_amount + rje_adjustment + aje_adjustment at all times after any data modification
7. WHEN Auditor clicks on any amount cell in the trial balance, THE Platform SHALL provide a drill-down path: audited amount → adjustment entries list → individual entry details, and unadjusted amount → account balance → general ledger entries → individual voucher
8. THE Platform SHALL provide a data consistency check function that verifies: (a) trial balance unadjusted amounts match the sum of mapped balance data, (b) trial balance adjustment amounts match the sum of approved and draft adjustment entries, (c) audited amount formula is correct for all accounts
9. IF the data consistency check finds any discrepancy, THEN THE Platform SHALL display the discrepant accounts with expected vs actual values and provide a one-click recalculation option


### 需求 11：未更正错报汇总管理

**用户故事：** 作为项目经理，我希望系统能汇总管理所有未更正错报（被审计单位拒绝调整的AJE），自动计算累计影响并与重要性水平联动评价，以便在出具审计报告前评估未更正错报对审计意见的影响。

#### 验收标准

1. THE Platform SHALL provide an unadjusted misstatements management interface using the `unadjusted_misstatements` table with fields: `id` (UUID PK), `project_id` (UUID FK to projects), `year` (integer, not null), `source_adjustment_id` (UUID FK to adjustments, nullable, the rejected AJE that originated this misstatement), `misstatement_description` (text, not null), `affected_account_code` (varchar), `affected_account_name` (varchar), `misstatement_amount` (numeric(20,2), not null), `misstatement_type` (enum: factual/judgmental/projected, not null), `management_reason` (text, nullable, management's reason for not adjusting), `auditor_evaluation` (text, nullable, auditor's assessment of management's reason), `is_carried_forward` (boolean, default false, whether carried from prior year), `prior_year_id` (UUID FK to unadjusted_misstatements, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users); with composite index on (project_id, year)
2. WHEN Manager changes an AJE adjustment entry's review_status to "rejected" and the rejection indicates the client refuses to adjust, THE Platform SHALL prompt Manager to create a corresponding unadjusted misstatement record, pre-filling the misstatement_description, affected_account_code, affected_account_name, and misstatement_amount from the rejected AJE
3. THE Platform SHALL automatically calculate the cumulative impact of all unadjusted misstatements for a project: total_misstatement_amount = SUM(misstatement_amount) for all non-deleted records, and display this alongside the overall materiality level for comparison
4. WHEN the cumulative total_misstatement_amount reaches or exceeds the overall materiality level from the `materiality` table, THE Platform SHALL display a prominent warning: "未更正错报累计金额({total_amount})已达到或超过整体重要性水平({materiality_amount})，可能需要出具保留意见或否定意见"
5. THE Platform SHALL support carrying forward prior year unadjusted misstatements: WHEN creating a new year project, THE Platform SHALL copy non-deleted unadjusted misstatements from the prior year with is_carried_forward=true and prior_year_id referencing the original record, so that cumulative impact across years can be assessed
6. THE Platform SHALL provide an unadjusted misstatements summary view displaying: a list of all misstatements (current year + carried forward), grouped by misstatement_type (factual/judgmental/projected), with subtotals per type and a grand total, alongside the three materiality levels (overall/performance/trivial threshold) for comparison
7. THE Platform SHALL allow Manager to record management_reason (why the client refuses to adjust) and auditor_evaluation (auditor's assessment) for each misstatement, and these fields must be non-empty before the project can transition from "completion" to "reporting" phase
8. FOR ALL unadjusted misstatements, the cumulative total displayed in the summary view SHALL equal the SUM of all individual misstatement_amount values (summation consistency)

### 需求 12：未更正错报汇总表Schema定义

**用户故事：** 作为开发者，我希望未更正错报汇总表的Schema明确定义，以便通过Alembic迁移脚本创建表结构。

#### 验收标准

1. THE Migration_Framework SHALL create the `unadjusted_misstatements` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `year` (integer, not null), `source_adjustment_id` (UUID FK to adjustments, nullable), `misstatement_description` (text, not null), `affected_account_code` (varchar), `affected_account_name` (varchar), `misstatement_amount` (numeric(20,2), not null), `misstatement_type` (enum: factual/judgmental/projected, not null), `management_reason` (text, nullable), `auditor_evaluation` (text, nullable), `is_carried_forward` (boolean, default false), `prior_year_id` (UUID FK to unadjusted_misstatements, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users); with composite index on (project_id, year) and index on (source_adjustment_id)
