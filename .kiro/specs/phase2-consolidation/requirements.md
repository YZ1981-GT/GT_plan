# 需求文档：第二阶段集团合并 — 集团架构+组成部分审计师+合并抵消+商誉+少数股东+外币折算+合并报表+合并附注

## 简介

本文档定义审计作业平台第二阶段集团合并功能的需求。在第一阶段单户审计MVP（数据导入+科目映射+试算表+调整分录+底稿+报表+附注）基础上，叠加集团合并能力。涵盖七大核心模块：集团架构管理（三码体系+合并范围）、组成部分审计师管理（审计指令+结果接收+质量评价）、合并汇总与抵消分录（权益抵消/内部往来/内部交易/未实现利润，含连续编制）、商誉计算与少数股东权益、外币报表折算、合并报表与合并底稿、合并附注自动生成。本阶段依赖Phase 1已实现的试算表、调整分录、报表生成引擎、附注模版体系等模块。

## 术语表

- **Platform（审计作业平台）**：面向会计师事务所的本地私有化审计全流程作业系统
- **Auditor（审计员）**：执行审计程序、编制底稿的项目组成员
- **Manager（项目经理）**：负责项目管理、复核底稿质量的项目负责人
- **Partner（签字合伙人）**：对审计报告承担最终签字责任的合伙人
- **Group_Project（集团审计项目）**：包含母公司和多个子公司/联营/合营企业的审计项目，通过三码体系组织集团架构
- **Company_Code（本企业代码）**：唯一标识各法人主体的编码
- **Parent_Code（上级企业代码）**：构建集团股权层级的上级企业编码
- **Ultimate_Code（最终控制方代码）**：确定合并范围的最终控制方编码
- **Consol_Scope（合并范围）**：确定哪些企业纳入合并报表编制范围的配置，存储于`consol_scope`表
- **Consol_Method（合并方法）**：全额合并（子公司）、权益法（联营/合营企业）、比例合并（合营企业可选）三种方法
- **Consol_Trial（合并试算表）**：汇总各公司审定数、合并调整、合并抵消后得出合并数的工作表，存储于`consol_trial`表
- **Elimination_Entry（抵消分录）**：合并报表编制中消除集团内部交易和往来的分录，存储于`elimination_entries`表
- **Continuous_Elimination（连续编制）**：上年抵消分录本年需重新编制并调整的合并报表编制方法
- **Internal_Trade（内部交易）**：集团内部公司之间的商品/服务交易，存储于`internal_trade`表
- **Internal_AR_AP（内部往来）**：集团内部公司之间的应收应付款项，存储于`internal_ar_ap`表
- **Goodwill（商誉）**：合并成本超过被投资方可辨认净资产公允价值份额的差额，存储于`goodwill_calc`表
- **Minority_Interest（少数股东权益）**：子公司净资产中不属于母公司的份额，存储于`minority_interest`表
- **Forex_Translation（外币报表折算）**：将境外子公司以功能货币编制的报表折算为集团列报货币的过程，存储于`forex_translation`表
- **Component_Auditor（组成部分审计师）**：受主审事务所委托审计集团内部分子公司的其他事务所，存储于`component_auditors`表
- **Component_Instruction（审计指令）**：主审团队向组成部分审计师发送的工作要求，存储于`component_instructions`表
- **Component_Result（组成部分审计结果）**：组成部分审计师返回的审计结论和发现，存储于`component_results`表
- **Consol_Report（合并报表）**：合并资产负债表、合并利润表、合并现金流量表、合并所有者权益变动表的统称
- **Consol_Disclosure（合并附注）**：合并报表附注，包含合并范围说明、重要子公司信息、内部交易抵消说明等额外披露内容

## 需求

### 需求 1：集团架构管理

**用户故事：** 作为项目经理，我希望能维护集团的股权层级结构（三码体系），以便系统能正确确定合并范围和合并方法。

#### 验收标准

1. THE Platform SHALL provide a company management interface within the Group_Project to create and maintain company records in the `companies` table with the following fields: company_code (unique within project), company_name, parent_code (nullable for ultimate parent), ultimate_code, consol_level (integer, hierarchy depth), shareholding (numeric, percentage 0-100), consol_method (enum: full/equity/proportional), acquisition_date (date, nullable), disposal_date (date, nullable), functional_currency (varchar, default 'CNY'), and is_active (boolean)
2. WHEN Manager adds a new company with a parent_code, THE Platform SHALL automatically calculate the consol_level as parent's consol_level + 1 and set the ultimate_code to the root company's company_code
3. THE Platform SHALL display the group structure as an interactive tree diagram showing: company name, company code, shareholding percentage, consolidation method (color-coded: full=blue, equity=green, proportional=orange), and functional currency
4. WHEN Manager modifies a company's parent_code, THE Platform SHALL recalculate consol_level for the moved company and all its descendants, and update ultimate_code if the root changes
5. THE Platform SHALL maintain the `consol_scope` table with fields: project_id, year, company_code, is_included (boolean), inclusion_reason (enum: subsidiary/associate/joint_venture/special_purpose), exclusion_reason (text, nullable), scope_change_type (enum: none/new_inclusion/exclusion/method_change), scope_change_description (text, nullable)
6. WHEN Manager marks a company as excluded from consolidation scope, THE Platform SHALL require an exclusion_reason text and record the scope_change_type as "exclusion"
7. THE Platform SHALL validate the group structure integrity: every company's parent_code must reference an existing company_code within the same project, and no circular references are allowed in the parent-child chain
8. THE Platform SHALL support recording mid-year acquisition and disposal: WHEN a company has an acquisition_date within the audit year, THE Platform SHALL only include that company's income statement data from the acquisition_date to year-end in the consolidation

### 需求 2：组成部分审计师管理

**用户故事：** 作为项目经理，我希望能管理组成部分审计师的信息、发送审计指令并接收审计结果，以便完整记录集团审计中对组成部分审计师工作的监督过程（ISA 600/CSA 1401）。

#### 验收标准

1. THE Platform SHALL provide a component auditor management interface to create and maintain records in the `component_auditors` table with fields: project_id, company_code (FK to companies), firm_name, contact_person, contact_info, competence_rating (enum: reliable/additional_procedures_needed/unreliable), rating_basis (text), independence_confirmed (boolean), independence_date (date, nullable), is_deleted, created_at, updated_at
2. WHEN Manager creates a component auditor record, THE Platform SHALL require competence_rating and rating_basis fields to be filled, and display a warning if competence_rating is "unreliable"
3. THE Platform SHALL support creating audit instructions in the `component_instructions` table with fields: project_id, component_auditor_id (FK), instruction_date, due_date, materiality_level (numeric, the component materiality), audit_scope_description (text), reporting_format (text), special_attention_items (text), instruction_file_path (varchar, nullable), status (enum: draft/sent/acknowledged), sent_at (timestamp, nullable)
4. WHEN Manager marks an instruction as "sent", THE Platform SHALL record the sent_at timestamp and prevent further modification of the instruction content
5. THE Platform SHALL support recording component audit results in the `component_results` table with fields: project_id, component_auditor_id (FK), received_date, opinion_type (enum: unqualified/qualified/adverse/disclaimer), identified_misstatements (jsonb, array of {account, amount, description}), significant_findings (text), result_file_path (varchar, nullable), group_team_evaluation (text), needs_additional_procedures (boolean), evaluation_status (enum: pending/accepted/requires_followup)
6. WHEN a component result is received with opinion_type other than "unqualified" or needs_additional_procedures is true, THE Platform SHALL highlight the result in red and prompt Manager to document the impact assessment
7. WHEN a component result is accepted, THE Platform SHALL make the component's audited trial balance data available for consolidation by linking the component's company_code trial balance to the consol_trial aggregation

### 需求 3：合并汇总与抵消分录

**用户故事：** 作为审计员，我希望系统能自动汇总各子公司审定数并支持编制抵消分录（含连续编制），以便高效完成合并报表的核心编制工作。

#### 验收标准

1. THE Platform SHALL generate the `consol_trial` table by aggregating trial balance data from all companies included in the consolidation scope, with columns: project_id, year, standard_account_code, account_name, account_category, individual_sum (sum of all companies' audited amounts), consol_adjustment (consolidation adjustments), consol_elimination (elimination entries total), consol_amount (final consolidated amount), is_deleted, created_at, updated_at
2. THE Platform SHALL calculate individual_sum by summing the audited_amount from each company's trial_balance where the company is included in consol_scope with is_included=true
3. WHEN Auditor creates an elimination entry, THE Platform SHALL store it in the `elimination_entries` table with fields: project_id, year, entry_no (auto-generated, format "CE-001"), entry_type (enum: equity/internal_trade/internal_ar_ap/unrealized_profit/other), description (text), account_code (varchar), account_name (varchar), debit_amount (numeric(20,2)), credit_amount (numeric(20,2)), entry_group_id (UUID), related_company_codes (jsonb, array of company_codes involved), is_continuous (boolean, true if carried forward from prior year), prior_year_entry_id (UUID, nullable, reference to original prior year entry), review_status (enum: draft/pending_review/approved/rejected), is_deleted, created_at, updated_at, created_by
4. WHEN an elimination entry is created, modified, or deleted, THE Platform SHALL automatically recalculate the consol_trial for all affected accounts: consol_elimination = SUM(debit_amount) - SUM(credit_amount) from all non-deleted elimination entries for that account, and consol_amount = individual_sum + consol_adjustment + consol_elimination
5. THE Platform SHALL enforce debit-credit balance for each elimination entry group: the sum of debit_amount must equal the sum of credit_amount across all lines with the same entry_group_id
6. THE Platform SHALL support continuous elimination (连续编制): WHEN Manager triggers "carry forward prior year eliminations", THE Platform SHALL copy all approved elimination entries from the prior year (year-1) into the current year with is_continuous=true and prior_year_entry_id set to the original entry's id, adjusting the affected accounts (e.g., converting prior year income statement eliminations to opening retained earnings adjustments)
7. WHEN carrying forward equity elimination entries from prior year, THE Platform SHALL adjust the entry to replace income statement accounts (revenue/cost/expense) with "未分配利润—年初" (opening retained earnings) account, preserving the original elimination logic
8. THE Platform SHALL provide an elimination entry summary view grouped by entry_type, showing: count of entries, total debit/credit amounts, and continuous vs current year breakdown

### 需求 4：内部交易与内部往来管理

**用户故事：** 作为审计员，我希望能记录和核对集团内部交易和内部往来，以便准确编制内部交易抵消分录和内部往来抵消分录。

#### 验收标准

1. THE Platform SHALL provide an internal trade management interface to record transactions in the `internal_trade` table with fields: project_id, year, seller_company_code, buyer_company_code, trade_type (enum: goods/services/assets/other), trade_amount (numeric(20,2)), cost_amount (numeric(20,2), seller's cost of goods sold), unrealized_profit (numeric(20,2), calculated), inventory_remaining_ratio (numeric(5,4), percentage of goods still in buyer's inventory at year-end), description (text), is_deleted, created_at, updated_at
2. THE Platform SHALL automatically calculate unrealized_profit as: (trade_amount - cost_amount) × inventory_remaining_ratio for goods-type internal trades
3. THE Platform SHALL provide an internal AR/AP reconciliation interface using the `internal_ar_ap` table with fields: project_id, year, debtor_company_code, creditor_company_code, debtor_amount (numeric(20,2), amount per debtor's books), creditor_amount (numeric(20,2), amount per creditor's books), difference_amount (numeric(20,2), calculated), difference_reason (text, nullable), reconciliation_status (enum: matched/unmatched/adjusted), is_deleted, created_at, updated_at
4. THE Platform SHALL automatically calculate difference_amount as debtor_amount - creditor_amount and set reconciliation_status to "matched" when difference_amount equals zero, "unmatched" otherwise
5. WHEN Auditor confirms an internal trade record, THE Platform SHALL offer to auto-generate the corresponding elimination entries: for goods trades, generate revenue/cost elimination and unrealized profit elimination; for AR/AP, generate receivable/payable elimination
6. WHEN auto-generating elimination entries from internal trades, THE Platform SHALL create entries with entry_type="internal_trade" for goods/services and entry_type="internal_ar_ap" for receivables/payables, linking related_company_codes to the involved parties
7. THE Platform SHALL display an internal transaction matrix showing all inter-company transactions in a grid format (rows=sellers, columns=buyers) with amounts at intersections, and highlight unreconciled AR/AP pairs in red

### 需求 5：商誉计算与少数股东权益

**用户故事：** 作为审计员，我希望系统能计算和跟踪各子公司的商誉及少数股东权益，以便在合并报表中准确列示这两个关键项目。

#### 验收标准

1. THE Platform SHALL provide a goodwill calculation interface using the `goodwill_calc` table with fields: project_id, year, subsidiary_company_code, acquisition_date, acquisition_cost (numeric(20,2)), identifiable_net_assets_fv (numeric(20,2), fair value of identifiable net assets at acquisition), parent_share_ratio (numeric(5,4)), goodwill_amount (numeric(20,2), calculated), accumulated_impairment (numeric(20,2), default 0), current_year_impairment (numeric(20,2), default 0), carrying_amount (numeric(20,2), calculated), is_negative_goodwill (boolean), negative_goodwill_treatment (text, nullable), is_deleted, created_at, updated_at
2. THE Platform SHALL calculate goodwill_amount as: acquisition_cost - (identifiable_net_assets_fv × parent_share_ratio); IF the result is negative, THEN set is_negative_goodwill=true and record the treatment in negative_goodwill_treatment
3. THE Platform SHALL calculate carrying_amount as: goodwill_amount - accumulated_impairment - current_year_impairment
4. WHEN current_year_impairment is entered, THE Platform SHALL automatically generate a goodwill impairment elimination entry (debit: 资产减值损失, credit: 商誉减值准备) and update accumulated_impairment for next year's carry-forward
5. THE Platform SHALL provide a minority interest calculation interface using the `minority_interest` table with fields: project_id, year, subsidiary_company_code, subsidiary_net_assets (numeric(20,2)), minority_share_ratio (numeric(5,4), calculated as 1 - parent_share_ratio), minority_equity (numeric(20,2), calculated), subsidiary_net_profit (numeric(20,2)), minority_profit (numeric(20,2), calculated), minority_equity_opening (numeric(20,2)), minority_equity_movement (jsonb, breakdown of changes), is_excess_loss (boolean, true if subsidiary's accumulated losses exceed minority's share), excess_loss_amount (numeric(20,2), default 0), is_deleted, created_at, updated_at
6. THE Platform SHALL calculate minority_equity as: subsidiary_net_assets × minority_share_ratio, and minority_profit as: subsidiary_net_profit × minority_share_ratio
7. IF a subsidiary's accumulated losses cause the minority equity to become negative and the minority shareholders have no obligation to bear excess losses, THEN THE Platform SHALL set is_excess_loss=true, cap minority_equity at zero, and record the excess_loss_amount
8. WHEN goodwill or minority interest calculations are completed, THE Platform SHALL automatically generate the corresponding equity elimination entries with entry_type="equity"

### 需求 6：外币报表折算

**用户故事：** 作为审计员，我希望系统能将境外子公司的外币报表折算为集团列报货币，以便将折算后的数据纳入合并汇总。

#### 验收标准

1. THE Platform SHALL provide a forex translation interface using the `forex_translation` table with fields: project_id, year, company_code, functional_currency (varchar), reporting_currency (varchar, default 'CNY'), bs_closing_rate (numeric(10,6), balance sheet closing rate), pl_average_rate (numeric(10,6), income statement average rate), equity_historical_rate (numeric(10,6), equity items historical rate), opening_retained_earnings_translated (numeric(20,2)), translation_difference (numeric(20,2), calculated), translation_difference_oci (numeric(20,2), accumulated OCI balance), is_deleted, created_at, updated_at
2. WHEN Auditor inputs exchange rates for a foreign subsidiary, THE Platform SHALL apply the following translation rules: balance sheet items (assets and liabilities) translated at bs_closing_rate, income statement items translated at pl_average_rate, equity items (paid-in capital, capital reserve) translated at equity_historical_rate, and retained earnings calculated by formula
3. THE Platform SHALL calculate translation_difference as the balancing figure that makes the translated balance sheet balance: translation_difference = translated_total_assets - translated_total_liabilities - translated_equity_items - translated_retained_earnings
4. THE Platform SHALL record translation_difference_oci as the cumulative other comprehensive income balance from foreign currency translation, and automatically generate an elimination entry crediting "其他综合收益—外币报表折算差额"
5. WHEN the forex translation is completed for a foreign subsidiary, THE Platform SHALL replace that company's original currency trial balance data with the translated CNY amounts in the consol_trial aggregation
6. THE Platform SHALL display a translation worksheet showing side-by-side: original currency amounts, exchange rates applied, and translated amounts for each account, with the translation difference clearly highlighted

### 需求 7：合并报表与合并底稿

**用户故事：** 作为项目经理，我希望系统能基于合并试算表自动生成合并四表（资产负债表、利润表、现金流量表、所有者权益变动表）和合并底稿，以便高效完成集团审计的最终交付物。

#### 验收标准

1. WHEN all elimination entries are approved and the consol_trial is finalized, THE Platform SHALL generate consolidated financial reports by applying the Phase 1 Report_Engine to the consol_trial data, producing: consolidated balance sheet, consolidated income statement, consolidated cash flow statement, and consolidated equity statement
2. THE Platform SHALL add consolidation-specific line items to the consolidated reports: goodwill (in assets), minority interest equity (in equity section), and minority interest profit (in income statement below net profit)
3. THE Platform SHALL generate a consolidation workpaper (合并底稿) as an .xlsx file containing: (a) individual company trial balances side by side, (b) elimination entries summary, (c) consol_trial with all columns (individual_sum / consol_adjustment / consol_elimination / consol_amount), and (d) reconciliation checks
4. THE Platform SHALL verify the consolidated balance sheet balances: total consolidated assets = total consolidated liabilities + total consolidated equity (including minority interest)
5. THE Platform SHALL support comparing consolidated report data with prior year consolidated data, displaying variance amounts and percentages for each line item
6. THE Platform SHALL allow Manager to export the consolidation workpaper and consolidated reports to Excel format preserving all formulas, formatting, and cross-references

### 需求 8：合并附注自动生成

**用户故事：** 作为审计员，我希望系统能自动生成合并报表附注中与合并相关的特殊披露内容，以便减少手工编写合并附注的工作量。

#### 验收标准

1. THE Disclosure_Engine SHALL generate consolidation-specific note sections including: consolidation scope description (listing all subsidiaries with name, registered capital, shareholding, business nature), changes in consolidation scope during the year, and reasons for exclusion of any entities
2. THE Disclosure_Engine SHALL generate a subsidiary information table from the `companies` and `consol_scope` data, containing: subsidiary name, registered location, business nature, registered capital, shareholding percentage (direct and indirect), consolidation method, and whether the subsidiary is a significant subsidiary
3. THE Disclosure_Engine SHALL generate goodwill disclosure notes from `goodwill_calc` data, including: goodwill by subsidiary (acquisition cost, accumulated impairment, carrying amount), current year impairment testing results, and key assumptions used in impairment testing
4. THE Disclosure_Engine SHALL generate minority interest disclosure notes from `minority_interest` data, including: minority interest by subsidiary (opening balance, share of profit/loss, dividends, other changes, closing balance)
5. THE Disclosure_Engine SHALL generate internal transaction elimination disclosure notes summarizing: types and amounts of eliminated internal transactions, unrealized profit amounts, and internal AR/AP elimination amounts
6. WHEN a foreign subsidiary exists in the consolidation scope, THE Disclosure_Engine SHALL generate foreign currency translation disclosure notes including: functional currency of each foreign subsidiary, exchange rates used (closing/average/historical), and translation differences recognized in OCI
7. THE Disclosure_Engine SHALL integrate consolidation-specific notes with the Phase 1 note template system, inserting consolidation sections at the appropriate positions in the overall note structure

### 需求 9：数据表Schema定义（第二阶段合并表）

**用户故事：** 作为开发者，我希望第二阶段合并相关数据表的Schema明确定义，以便通过Alembic迁移脚本创建表结构。

#### 验收标准

1. THE Migration_Framework SHALL create the `companies` table with columns: `id` (UUID PK), `project_id` (UUID FK to projects), `company_code` (varchar, not null), `company_name` (varchar, not null), `parent_code` (varchar, nullable), `ultimate_code` (varchar, not null), `consol_level` (integer, default 0), `shareholding` (numeric(5,2)), `consol_method` (enum: full/equity/proportional), `acquisition_date` (date, nullable), `disposal_date` (date, nullable), `functional_currency` (varchar, default 'CNY'), `is_active` (boolean, default true), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (project_id, company_code)
2. THE Migration_Framework SHALL create the `consol_scope` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer, not null), `company_code` (varchar, not null), `is_included` (boolean, default true), `inclusion_reason` (enum: subsidiary/associate/joint_venture/special_purpose), `exclusion_reason` (text, nullable), `scope_change_type` (enum: none/new_inclusion/exclusion/method_change, default none), `scope_change_description` (text, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (project_id, year, company_code)
3. THE Migration_Framework SHALL create the `consol_trial` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer, not null), `standard_account_code` (varchar, not null), `account_name` (varchar), `account_category` (enum: asset/liability/equity/revenue/cost/expense), `individual_sum` (numeric(20,2), default 0), `consol_adjustment` (numeric(20,2), default 0), `consol_elimination` (numeric(20,2), default 0), `consol_amount` (numeric(20,2), default 0), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (project_id, year, standard_account_code)
4. THE Migration_Framework SHALL create the `elimination_entries` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer, not null), `entry_no` (varchar, not null), `entry_type` (enum: equity/internal_trade/internal_ar_ap/unrealized_profit/other), `description` (text), `account_code` (varchar, not null), `account_name` (varchar), `debit_amount` (numeric(20,2), default 0), `credit_amount` (numeric(20,2), default 0), `entry_group_id` (UUID, not null), `related_company_codes` (jsonb), `is_continuous` (boolean, default false), `prior_year_entry_id` (UUID, nullable), `review_status` (enum: draft/pending_review/approved/rejected, default draft), `reviewer_id` (UUID FK to users, nullable), `reviewed_at` (timestamp, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users); with composite index on (project_id, year, entry_type) and index on (project_id, entry_group_id)
5. THE Migration_Framework SHALL create the `internal_trade` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer, not null), `seller_company_code` (varchar, not null), `buyer_company_code` (varchar, not null), `trade_type` (enum: goods/services/assets/other), `trade_amount` (numeric(20,2)), `cost_amount` (numeric(20,2)), `unrealized_profit` (numeric(20,2)), `inventory_remaining_ratio` (numeric(5,4)), `description` (text), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite index on (project_id, year)
6. THE Migration_Framework SHALL create the `internal_ar_ap` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer, not null), `debtor_company_code` (varchar, not null), `creditor_company_code` (varchar, not null), `debtor_amount` (numeric(20,2)), `creditor_amount` (numeric(20,2)), `difference_amount` (numeric(20,2)), `difference_reason` (text, nullable), `reconciliation_status` (enum: matched/unmatched/adjusted, default unmatched), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite index on (project_id, year)
7. THE Migration_Framework SHALL create the `goodwill_calc` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer, not null), `subsidiary_company_code` (varchar, not null), `acquisition_date` (date), `acquisition_cost` (numeric(20,2)), `identifiable_net_assets_fv` (numeric(20,2)), `parent_share_ratio` (numeric(5,4)), `goodwill_amount` (numeric(20,2)), `accumulated_impairment` (numeric(20,2), default 0), `current_year_impairment` (numeric(20,2), default 0), `carrying_amount` (numeric(20,2)), `is_negative_goodwill` (boolean, default false), `negative_goodwill_treatment` (text, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (project_id, year, subsidiary_company_code)
8. THE Migration_Framework SHALL create the `minority_interest` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer, not null), `subsidiary_company_code` (varchar, not null), `subsidiary_net_assets` (numeric(20,2)), `minority_share_ratio` (numeric(5,4)), `minority_equity` (numeric(20,2)), `subsidiary_net_profit` (numeric(20,2)), `minority_profit` (numeric(20,2)), `minority_equity_opening` (numeric(20,2)), `minority_equity_movement` (jsonb), `is_excess_loss` (boolean, default false), `excess_loss_amount` (numeric(20,2), default 0), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (project_id, year, subsidiary_company_code)
9. THE Migration_Framework SHALL create the `forex_translation` table with columns: `id` (UUID PK), `project_id` (UUID FK), `year` (integer, not null), `company_code` (varchar, not null), `functional_currency` (varchar, not null), `reporting_currency` (varchar, default 'CNY'), `bs_closing_rate` (numeric(10,6)), `pl_average_rate` (numeric(10,6)), `equity_historical_rate` (numeric(10,6)), `opening_retained_earnings_translated` (numeric(20,2)), `translation_difference` (numeric(20,2)), `translation_difference_oci` (numeric(20,2)), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (project_id, year, company_code)
10. THE Migration_Framework SHALL create the `component_auditors` table with columns: `id` (UUID PK), `project_id` (UUID FK), `company_code` (varchar, not null), `firm_name` (varchar, not null), `contact_person` (varchar), `contact_info` (varchar), `competence_rating` (enum: reliable/additional_procedures_needed/unreliable), `rating_basis` (text), `independence_confirmed` (boolean, default false), `independence_date` (date, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with composite unique index on (project_id, company_code)
11. THE Migration_Framework SHALL create the `component_instructions` table with columns: `id` (UUID PK), `project_id` (UUID FK), `component_auditor_id` (UUID FK to component_auditors), `instruction_date` (date), `due_date` (date), `materiality_level` (numeric(20,2)), `audit_scope_description` (text), `reporting_format` (text), `special_attention_items` (text), `instruction_file_path` (varchar, nullable), `status` (enum: draft/sent/acknowledged, default draft), `sent_at` (timestamp, nullable), `is_deleted` (boolean, default false), `created_at`, `updated_at`, `created_by` (UUID FK to users); with index on (project_id, component_auditor_id)
12. THE Migration_Framework SHALL create the `component_results` table with columns: `id` (UUID PK), `project_id` (UUID FK), `component_auditor_id` (UUID FK to component_auditors), `received_date` (date), `opinion_type` (enum: unqualified/qualified/adverse/disclaimer), `identified_misstatements` (jsonb), `significant_findings` (text), `result_file_path` (varchar, nullable), `group_team_evaluation` (text), `needs_additional_procedures` (boolean, default false), `evaluation_status` (enum: pending/accepted/requires_followup, default pending), `is_deleted` (boolean, default false), `created_at`, `updated_at`; with index on (project_id, component_auditor_id)
