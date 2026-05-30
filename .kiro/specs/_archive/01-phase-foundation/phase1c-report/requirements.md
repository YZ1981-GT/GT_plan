# 需求文档：第一阶段MVP报表 — 报表生成+现金流量表+附注+PDF导出

## 简介

本文档定义审计作业平台第一阶段MVP报表模块的需求。本阶段在Phase 1核心（数据导入+试算表+调整分录）和Phase 1b底稿（ONLYOFFICE+模板引擎）基础上，实现单户财务报表自动生成、现金流量表工作底稿法编制、附注自动生成、审计报告模板管理与PDF导出四大核心能力。

**执行顺序要求**：本阶段必须在 Phase 1b 底稿（phase1b-workpaper）完成后才能执行，因为报表生成引擎依赖底稿模块的取数公式引擎（FormulaEngine）和底稿模板引擎（TemplateEngine）。涵盖：报表格式配置引擎（行次定义+取数公式+多准则适配）、四张财务报表自动生成（资产负债表+利润表+现金流量表+所有者权益变动表）、现金流量表工作底稿法编制（资产负债表变动分析+调整分录还原+间接法勾稽校验）、附注模版体系（国企版/上市版两套模版+科目对照+校验公式+宽表公式）、审计报告模板管理（四种意见类型+段落模板）、PDF导出（异步任务+品牌排版+加密保护）。

## 术语表

- **Platform（审计作业平台）**：面向会计师事务所的本地私有化审计全流程作业系统
- **Auditor（审计员）**：执行审计程序、编制底稿的项目组成员
- **Manager（项目经理）**：负责项目管理、复核底稿质量的项目负责人
- **Partner（签字合伙人）**：对审计报告承担最终签字责任的合伙人
- **Report_Engine（报表生成引擎）**：根据报表格式配置和试算表数据自动生成四张财务报表的后端服务
- **Report_Config（报表格式配置）**：定义报表类型、行次结构、每行取数公式、适用准则的配置数据，存储于`report_config`表
- **Financial_Report（财务报表）**：系统生成的单户财务报表数据，含本期和比较期间数据，存储于`financial_report`表
- **Balance_Sheet（资产负债表）**：反映企业在特定日期财务状况的报表，列示资产、负债和所有者权益
- **Income_Statement（利润表）**：反映企业在一定会计期间经营成果的报表
- **Cash_Flow_Statement（现金流量表）**：反映企业在一定会计期间现金和现金等价物流入流出的报表
- **Equity_Statement（所有者权益变动表）**：反映企业所有者权益各组成部分当期增减变动的报表
- **CFS_Worksheet（现金流量表工作底稿）**：采用工作底稿法编制现金流量表的辅助底稿，基于资产负债表各项目期初期末变动和利润表项目，通过调整分录还原现金流量
- **CFS_Adjustment（现金流量表调整分录）**：在工作底稿法中用于将资产负债表变动还原为现金流量的调整分录，存储于`cfs_adjustments`表
- **Indirect_Method（间接法）**：从净利润出发，调整非现金项目和营运资本变动，推导经营活动现金流量的方法
- **Disclosure_Engine（附注生成引擎）**：根据附注模版和试算表/底稿数据自动生成财务报表附注的后端服务
- **Disclosure_Notes（附注）**：财务报表附注的结构化数据，按准则披露要求逐项组织，存储于`disclosure_notes`表
- **Note_Template（附注模版）**：系统内置的附注正文模版（国企版/上市版），包含科目对照、校验公式、宽表公式、正文模版四个配置
- **Account_Mapping_Template（科目对照模板）**：定义报表科目与附注表格的映射关系及校验角色
- **Check_Presets（校验公式预设）**：逐科目逐表格定义的校验公式，类型包括余额/宽表/纵向/交叉/其中项/账龄衔接/完整性/LLM审核
- **Wide_Table_Presets（宽表公式预设）**：定义多列变动表的标准列结构和横向公式（movement型和category_sum型）
- **Audit_Report（审计报告）**：审计师出具的正式审计报告，包含审计意见段、基础段、关键审计事项段等，存储于`audit_report`表
- **Audit_Report_Template（审计报告模板）**：审计报告的段落模板结构，按意见类型和适用场景组织，存储于`audit_report_template`表
- **PDF_Export_Engine（PDF导出引擎）**：将审计报告、财务报表、附注、底稿打包导出为PDF的异步任务服务
- **Export_Task（导出任务）**：PDF导出的异步任务记录，存储于`export_tasks`表

## 需求

### 需求 1：报表格式配置

**用户故事：** 作为项目经理，我希望系统提供可配置的报表格式（行次定义+取数公式），以便适配不同行业（一般企业/金融/保险）和不同准则的报表格式差异。

#### 验收标准

1. THE Report_Engine SHALL support configuring report formats in the `report_config` table with the following fields per row: report_type (balance_sheet/income_statement/cash_flow_statement/equity_statement), row_number (integer, display order), row_code (varchar, unique identifier like "BS-001"), row_name (varchar, display label like "货币资金"), indent_level (integer, hierarchy depth for display), formula (varchar, the data extraction formula), applicable_standard (varchar, e.g. enterprise/financial/small_enterprise), and is_total_row (boolean, whether this row is a subtotal or total)
2. THE Platform SHALL provide built-in report format configurations for the enterprise accounting standard (企业会计准则) covering all four report types, with row structures matching the standard report templates published by the Ministry of Finance
3. WHEN Manager creates a project with a specific accounting standard, THE Report_Engine SHALL load the corresponding report format configuration as the project's report template
4. THE Report_Engine SHALL support the following formula syntax in the `formula` field for each report row:
   - `TB(account_code, column)` — fetch from trial balance (reusing the Formula_Engine from Phase 1b)
   - `SUM_TB(code_range, column)` — sum over account code range
   - `ROW(row_code) + ROW(row_code)` — arithmetic operations referencing other report rows by row_code
   - `PREV(formula)` — fetch prior year data
5. WHEN Manager needs to customize the report format for a specific project (e.g. adding industry-specific line items), THE Platform SHALL allow cloning the standard configuration and modifying row definitions without affecting the standard template


### 需求 2：单户财务报表自动生成

**用户故事：** 作为审计员，我希望系统根据试算表审定数自动生成四张财务报表（资产负债表+利润表+现金流量表+所有者权益变动表），以便报表数据始终与试算表保持一致，无需手工编制。

#### 验收标准

1. WHEN Auditor triggers report generation for a project, THE Report_Engine SHALL generate all four financial reports by executing the formula defined in each row of the `report_config` for the project's applicable standard, and store results in the `financial_report` table
2. THE Report_Engine SHALL generate the complete set of four financial reports within 10 seconds for a single entity with up to 500 accounts
3. THE Financial_Report SHALL store the following fields per report row: project_id, year, report_type, row_code, row_name, current_period_amount (numeric(20,2)), prior_period_amount (numeric(20,2)), and generated_at (timestamp)
4. WHEN the trial balance is recalculated (due to new adjustment entries or data import), THE Report_Engine SHALL automatically regenerate all affected financial reports to maintain consistency with the trial balance
5. THE Report_Engine SHALL generate both current period and prior period (comparative) data for each report row by executing the formula with current year data and prior year data respectively
6. THE Balance_Sheet SHALL verify the accounting equation: total assets = total liabilities + total owners equity, and display a balance check indicator (balanced/unbalanced)
7. THE Income_Statement SHALL verify that the net profit row equals revenue minus costs minus expenses plus/minus non-operating items, consistent with the trial balance net profit calculation
8. THE Platform SHALL display each financial report in a formatted table view with proper indentation based on indent_level, subtotal rows highlighted, and total rows in bold
9. WHEN Auditor clicks on any amount cell in a financial report, THE Platform SHALL provide a drill-down path showing: the formula used to calculate the value, the trial balance accounts contributing to the value, and a link to the four-table drill-down for each account
10. THE Platform SHALL support exporting individual financial reports to Excel format preserving the row structure, formatting, and both current and prior period data

### 需求 3：现金流量表工作底稿法编制

**用户故事：** 作为审计员，我希望系统提供工作底稿法编制现金流量表的能力，基于资产负债表变动和利润表项目通过调整分录还原现金流量，以便准确编制这张最难的报表。

#### 验收标准

1. THE CFS_Worksheet SHALL automatically populate the following data from the trial balance: opening and closing balances for all balance sheet accounts, and all income statement line items for the current period
2. THE CFS_Worksheet SHALL calculate the period change for each balance sheet account as: closing balance minus opening balance, and display it in a dedicated "变动额" column
3. THE Platform SHALL provide a CFS adjustment entry interface where Auditor can create CFS_Adjustment entries to reclassify balance sheet changes into cash flow categories (operating/investing/financing activities), with fields: adjustment_no (auto-generated), description, debit_account (balance sheet account or cash flow line item), credit_account, amount, and cash_flow_category (operating/investing/financing/supplementary)
4. WHEN Auditor submits a CFS_Adjustment entry, THE Platform SHALL validate that total debits equal total credits across all line items of the entry
5. THE CFS_Worksheet SHALL display a reconciliation view showing for each balance sheet account: opening balance, closing balance, period change, allocated adjustments total, and unallocated remainder (period change minus allocated adjustments)
6. WHEN all balance sheet account changes have been fully allocated (unallocated remainder equals zero for all accounts), THE CFS_Worksheet SHALL indicate "工作底稿已平衡" status
7. THE Report_Engine SHALL automatically generate the cash flow statement main table by aggregating CFS_Adjustment entries grouped by cash_flow_category and cash flow line items
8. THE Platform SHALL auto-identify common adjustment items from the trial balance and income statement: depreciation and amortization, asset impairment losses, gains/losses on disposal of assets, investment income, deferred tax changes, and financial expenses, and pre-populate corresponding CFS_Adjustment entries as drafts for Auditor review

#### 3.1 间接法勾稽校验

9. THE Report_Engine SHALL generate the indirect method supplementary schedule (补充资料) starting from net profit and adjusting for: depreciation of fixed assets, amortization of intangible assets, amortization of long-term deferred expenses, losses on disposal of assets, asset impairment provisions, financial expenses, investment losses, changes in deferred tax, changes in inventories, changes in operating receivables, and changes in operating payables
10. THE Report_Engine SHALL verify the indirect method reconciliation: the operating cash flow calculated via the indirect method must equal the operating cash flow in the main cash flow statement, and display a reconciliation check indicator
11. THE Report_Engine SHALL verify the cash reconciliation: net increase in cash and cash equivalents = closing cash balance minus opening cash balance, where cash balance is derived from the trial balance accounts mapped to cash and cash equivalents
12. IF any reconciliation check fails, THEN THE Report_Engine SHALL display the discrepancy amount and highlight the failing check in red

### 需求 4：附注模版管理与附注自动生成

**用户故事：** 作为审计员，我希望系统根据附注模版自动生成财务报表附注初稿，数值从试算表和底稿自动取数，文字部分提供模版文本供人工修改，以便大幅减少附注编制的重复劳动。

#### 验收标准

1. THE Platform SHALL provide two built-in note template sets: SOE version (国企版) for state-owned enterprises and Listed version (上市版) for listed companies, each containing four configuration components: account mapping template, check presets, wide table presets, and disclosure text template
2. WHEN Manager selects a note template set during project initialization or report generation, THE Disclosure_Engine SHALL load the corresponding template configurations
3. THE Disclosure_Engine SHALL generate disclosure notes by iterating through the account mapping template, and for each report line item that has mapped note tables, create a `disclosure_notes` record with: project_id, year, note_section (chapter number), section_title, account_name, content_type (table/text/mixed), table_data (jsonb, structured table content), text_content (text, narrative content), source_template (SOE/listed), and status (draft/confirmed)
4. FOR ALL note tables with check role "[余额]", THE Disclosure_Engine SHALL auto-populate the total row value from the corresponding trial balance audited amount and verify it matches the financial report row amount
5. FOR ALL note tables with check role "[宽表]", THE Disclosure_Engine SHALL apply the wide table preset formula (movement type: opening ± changes = closing) to verify horizontal consistency across columns
6. FOR ALL note tables with check role "[交叉]", THE Disclosure_Engine SHALL verify cross-table consistency within the same account (e.g. bad debt provision movement table ending balance equals the provision column in the summary table)
7. FOR ALL note tables with check role "[其中项]", THE Disclosure_Engine SHALL verify that the sum of detail rows equals the total row
8. THE Disclosure_Engine SHALL auto-populate numerical data in note tables from the trial balance and auxiliary balance data using the formula engine, and mark text sections as "待填写" for manual input
9. THE Disclosure_Engine SHALL generate the standard disclosure chapters: company overview, basis of preparation, compliance statement, significant accounting policies, taxation, notes to financial statement line items (core chapter with per-account tables), and other important matters
10. WHEN Auditor modifies a disclosure note section, THE Platform SHALL save the changes and update the status from "draft" to "confirmed" for that section
11. THE Platform SHALL display disclosure notes in a structured navigation tree (left panel) with content editor (right panel), allowing Auditor to navigate between sections and edit content inline


### 需求 5：附注校验引擎

**用户故事：** 作为审计员，我希望系统自动执行附注校验（余额核对、宽表公式、纵向勾稽、交叉校验等），以便在附注定稿前发现数据不一致问题。

#### 验收标准

1. THE Disclosure_Engine SHALL execute the following 8 types of validation checks on generated disclosure notes, using the check presets configuration:
   - Balance check (余额): verify report amount equals note total row amount
   - Wide table check (宽表): verify horizontal formula (opening ± movements = closing)
   - Vertical check (纵向): verify multi-section vertical reconciliation (e.g. original cost minus depreciation minus impairment = book value)
   - Cross-table check (交叉): verify consistency across multiple tables within the same account
   - Sub-item check (其中项): verify detail rows sum to total row
   - Aging transition check (账龄衔接): verify current period aging brackets are consistent with prior period (e.g. current "1-2 years" should not exceed prior "within 1 year")
   - Completeness check (完整性): verify data rows with non-zero balances have all required columns populated
   - LLM review (LLM审核): for text-type sections, use LLM to check accounting policy descriptions against standard templates
2. THE Disclosure_Engine SHALL execute validation checks using a "local rule engine first, LLM fallback" architecture: rules 1-7 are executed by deterministic rule engine, rule 8 is executed by LLM service
3. THE Disclosure_Engine SHALL return validation results as a structured list with each finding containing: note_section, table_name, check_type, severity (error/warning/info), message, expected_value (if applicable), actual_value (if applicable), and cell_reference (if applicable)
4. WHEN Auditor triggers note validation, THE Platform SHALL display results grouped by account name and check type, with error-level findings highlighted in red and warning-level findings in orange
5. THE Platform SHALL allow Auditor to mark individual validation findings as "已确认-无需修改" with a reason text, so that known acceptable differences do not block the workflow

### 需求 6：审计报告模板管理

**用户故事：** 作为项目经理，我希望系统提供审计报告模板（四种意见类型），支持从模板生成审计报告初稿并自动填充财务数据，以便标准化审计报告的出具流程。

#### 验收标准

1. THE Platform SHALL provide built-in audit report templates in the `audit_report_template` table for four opinion types: unqualified (标准无保留意见), qualified (保留意见), adverse (否定意见), and disclaimer (无法表示意见), each containing paragraph templates for: auditor opinion section, basis for opinion section, key audit matters section (KAM), other information section, management responsibility section, governance responsibility section, and auditor responsibility section
2. THE Platform SHALL provide separate template variants for listed companies and non-listed companies within each opinion type
3. WHEN Manager selects an opinion type and company type, THE Platform SHALL generate an audit report draft in the `audit_report` table by populating the template paragraphs, with fields: project_id, year, opinion_type, company_type (listed/non_listed), report_date, signing_partner, paragraphs (jsonb, structured paragraph content), financial_data (jsonb, key figures auto-populated from financial reports), and status (draft/review/final)
4. THE Platform SHALL auto-populate financial data references in the audit report from the generated financial reports: total assets, total revenue, net profit, and other key figures mentioned in the report template
5. WHEN the financial reports are regenerated (due to trial balance changes), THE Platform SHALL update the financial data references in the audit report to maintain consistency
6. THE Platform SHALL allow Manager to edit each paragraph of the audit report independently, with a rich text editor supporting the GT brand formatting specifications (仿宋_GB2312 font, Arial Narrow for numbers)
7. WHEN the project is a listed company audit, THE Platform SHALL require at least one Key Audit Matter (KAM) entry before the audit report can be finalized

### 需求 7：PDF导出

**用户故事：** 作为项目经理，我希望能将审计报告、财务报表、附注和底稿打包导出为PDF电子档案，以便生成可归档的审计档案文件。

#### 验收标准

1. THE PDF_Export_Engine SHALL support exporting the following document types individually or as a combined package: audit report, balance sheet, income statement, cash flow statement, equity statement, disclosure notes, and selected working papers
2. WHEN Manager triggers a full project PDF export, THE PDF_Export_Engine SHALL execute the export as an asynchronous background task, return a task ID immediately, and complete the export within 5 minutes for a single project's complete archive
3. WHILE the export task is running, THE Platform SHALL display real-time progress including: current processing stage (generating/rendering/packaging), number of documents processed out of total, and elapsed time
4. THE PDF_Export_Engine SHALL apply the GT brand formatting specifications to all exported PDFs: page margins (left 3cm, right 3.18cm, top 3.2cm, bottom 2.54cm), Chinese font 仿宋_GB2312 小四, English/number font Arial Narrow, table borders (top and bottom 1pt, no left/right borders), title row bold with 0.5pt bottom border
5. THE PDF_Export_Engine SHALL generate a table of contents page listing all included documents with page numbers, organized by document category (audit report → financial statements → disclosure notes → working papers)
6. THE PDF_Export_Engine SHALL support password-protected PDF export where Manager can set an open password for the exported PDF file
7. THE PDF_Export_Engine SHALL store export task records in the `export_tasks` table with fields: project_id, task_type (single_document/full_archive), status (queued/processing/completed/failed), progress_percentage (integer), file_path (varchar, path to generated PDF), file_size (bigint), started_at, completed_at, created_by (user_id), error_message (text, nullable)
8. WHEN the export task completes, THE Platform SHALL provide a download link for the generated PDF file, valid for 24 hours
9. THE PDF_Export_Engine SHALL convert .xlsx working papers to PDF format preserving the sheet layout, column widths, and print area settings
10. THE PDF_Export_Engine SHALL add page headers (project name, document title) and page footers (page number in "第X页 共Y页" format) to all exported PDF pages

### 需求 8：报表↔底稿联动

**用户故事：** 作为审计员，我希望报表数据与底稿数据始终保持一致，调整分录变更能自动驱动试算表→报表→附注的级联更新，以便实现全链路数据联动。

#### 验收标准

1. WHEN a new adjustment entry (AJE/RJE) is created or modified, THE Platform SHALL trigger the following cascade update within 15 seconds: recalculate trial balance → regenerate affected financial report rows → update affected disclosure note table values
2. WHEN the trial balance is recalculated, THE Report_Engine SHALL identify which financial report rows are affected by comparing the changed account codes against the formulas in `report_config`, and regenerate only the affected rows (incremental update)
3. THE Platform SHALL maintain the data lineage: each financial report cell SHALL record the formula used and the trial balance accounts that contributed to its value, enabling full traceability from report → trial balance → journal entries → vouchers
4. WHEN Auditor views a financial report, THE Platform SHALL provide a "穿透查询" button on each amount cell that navigates through: report row → formula → trial balance accounts → four-table drill-down → individual vouchers
5. THE Platform SHALL verify cross-report consistency: balance sheet net profit must equal income statement net profit, and cash flow statement ending cash must equal balance sheet cash and cash equivalents closing balance
6. IF any cross-report consistency check fails, THEN THE Platform SHALL display a prominent warning banner on the report view indicating the inconsistency with the discrepancy amount

### 需求 9：报表相关数据表Schema定义

**用户故事：** 作为开发者，我希望报表相关数据表的Schema明确定义，以便通过Alembic迁移脚本创建表结构。

#### 验收标准

1. THE Migration_Framework SHALL create the `report_config` table with columns: `id` (UUID PK), `report_type` (enum: balance_sheet/income_statement/cash_flow_statement/equity_statement, not null), `row_number` (integer, not null), `row_code` (varchar, not null), `row_name` (varchar, not null), `indent_level` (integer, default 0), `formula` (text), `applicable_standard` (varchar, not null), `is_total_row` (boolean, default false), `parent_row_code` (varchar, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (report_type, row_code, applicable_standard)
2. THE Migration_Framework SHALL create the `financial_report` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `year` (integer, not null), `report_type` (enum: balance_sheet/income_statement/cash_flow_statement/equity_statement, not null), `row_code` (varchar, not null), `row_name` (varchar), `current_period_amount` (numeric(20,2)), `prior_period_amount` (numeric(20,2)), `formula_used` (text), `source_accounts` (jsonb, array of account codes that contributed), `generated_at` (timestamp), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (project_id, year, report_type, row_code)
3. THE Migration_Framework SHALL create the `cfs_adjustments` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `year` (integer, not null), `adjustment_no` (varchar, not null, auto-generated), `description` (text), `debit_account` (varchar, not null), `credit_account` (varchar, not null), `amount` (numeric(20,2), not null), `cash_flow_category` (enum: operating/investing/financing/supplementary), `cash_flow_line_item` (varchar, the specific line in cash flow statement), `entry_group_id` (UUID, groups multi-line entries), `is_auto_generated` (boolean, default false), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users); with composite index on (project_id, year, cash_flow_category)
4. THE Migration_Framework SHALL create the `disclosure_notes` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `year` (integer, not null), `note_section` (varchar, not null, chapter number like "五、1"), `section_title` (varchar, not null), `account_name` (varchar), `content_type` (enum: table/text/mixed), `table_data` (jsonb, structured table content with headers and rows), `text_content` (text, narrative content), `source_template` (enum: soe/listed), `status` (enum: draft/confirmed, default draft), `sort_order` (integer), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `updated_by` (UUID FK to users); with composite unique index on (project_id, year, note_section)
5. THE Migration_Framework SHALL create the `audit_report` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `year` (integer, not null), `opinion_type` (enum: unqualified/qualified/adverse/disclaimer, not null), `company_type` (enum: listed/non_listed, default non_listed), `report_date` (date, nullable), `signing_partner` (varchar), `paragraphs` (jsonb, structured paragraph content keyed by section name), `financial_data` (jsonb, key financial figures), `status` (enum: draft/review/final, default draft), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users), `updated_by` (UUID FK to users); with composite unique index on (project_id, year)
6. THE Migration_Framework SHALL create the `audit_report_template` table with columns: `id` (UUID PK), `opinion_type` (enum: unqualified/qualified/adverse/disclaimer, not null), `company_type` (enum: listed/non_listed, not null), `section_name` (varchar, not null, e.g. "审计意见段"), `section_order` (integer, not null), `template_text` (text, not null, the paragraph template with placeholders like {entity_name}, {audit_period}), `is_required` (boolean, default true), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (opinion_type, company_type, section_name)
7. THE Migration_Framework SHALL create the `export_tasks` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `task_type` (enum: single_document/full_archive), `document_type` (varchar, nullable, e.g. "audit_report"/"balance_sheet"), `status` (enum: queued/processing/completed/failed, default queued), `progress_percentage` (integer, default 0), `file_path` (varchar, nullable), `file_size` (bigint, nullable), `password_protected` (boolean, default false), `started_at` (timestamp, nullable), `completed_at` (timestamp, nullable), `error_message` (text, nullable), `created_by` (UUID FK to users), `created_at`; with index on (project_id, status)
8. THE Migration_Framework SHALL create the `note_validation_results` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `year` (integer, not null), `validation_timestamp` (timestamp, not null), `findings` (jsonb, not null, array of validation findings), `error_count` (integer, default 0), `warning_count` (integer, default 0), `info_count` (integer, default 0), `validated_by` (UUID FK to users), `created_at`; with index on (project_id, year)
