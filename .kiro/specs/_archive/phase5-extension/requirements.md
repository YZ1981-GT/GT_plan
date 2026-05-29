# Phase 8 - 扩展能力与远期规划 需求文档

## 简介

本文档定义审计作业平台第八阶段"扩展能力与远期规划"的需求。本阶段在完成前七个阶段（基础设施、核心、底稿、报表、合并、协作、AI）的基础上，实现系统的扩展性能力、多准则适配、监管对接、用户自定义模板等高级功能，并为未来的AI能力扩展预留接口。

本阶段的目标是将系统从一个"企业会计准则下的年审工具"升级为"全场景审计作业平台"，支持多种审计类型、多种会计准则、多语言环境，并具备与监管系统对接的能力。

## 术语表

| 术语 | 英文全称 | 中文释义 |
|------|----------|----------|
| GAAP | Generally Accepted Accounting Principles | 一般公认会计原则 |
| IFRS | International Financial Reporting Standards | 国际财务报告准则 |
| CAS | Chinese Accounting Standards | 中国企业会计准则 |
| SME GAAP | Small and Medium-sized Entities GAAP | 小企业会计准则 |
| Government GAAP | Government Accounting Standards | 政府会计准则 |
| Financial GAAP | Financial Industry Accounting Standards | 金融企业会计准则 |
| i18n | Internationalization | 国际化，支持多语言 |
| CA Certificate | Certificate Authority Certificate | 数字证书，由权威机构颁发的电子签名证书 |
| WOPI | Web Application Open Platform Interface | Web应用开放平台接口协议 |
| API Gateway | Application Programming Interface Gateway | API网关，用于统一管理和路由API请求 |
| Webhook | Web回调 | 一种基于HTTP的回调机制，用于系统间事件通知 |

## 核心需求

### 需求 1：多准则适配

**用户故事：** 作为审计师，我希望系统能支持多种会计准则（企业会计准则、小企业准则、政府会计准则、金融企业准则、国际准则IFRS），以便为不同类型的客户提供服务。

#### 验收标准

1. THE Platform SHALL provide a `accounting_standards` table with fields: id (UUID PK), standard_code (varchar, unique, e.g., 'CAS', 'SME', 'GOV', 'FIN', 'IFRS'), standard_name (varchar, not null), standard_description (text), effective_date (date), is_active (boolean, default true), created_at, updated_at
2. THE Platform SHALL associate each project with an accounting standard via the `projects.accounting_standard` field
3. WHEN a project is created with a specific accounting standard, THE Platform SHALL load the corresponding standard chart of accounts and report formats
4. THE Platform SHALL support standard-specific report templates (资产负债表/利润表/现金流量表/权益变动表) with different line items and calculation formulas for each accounting standard
5. THE Platform SHALL provide standard-specific disclosure note templates for each accounting standard
6. WHEN the accounting standard is changed for a project, THE Platform SHALL warn the user that this may affect report formats and disclosure requirements

### 需求 2：多语言支持

**用户故事：** 作为审计师，我希望系统能支持中英双语界面和报表输出，以便为境外子公司审计项目提供服务。

#### 验收标准

1. THE Platform SHALL provide an i18n framework with language files for Chinese (zh-CN) and English (en-US)
2. THE Platform SHALL store user language preference in the `users.language` field (enum: zh-CN/en-US)
3. WHEN a user logs in, THE Platform SHALL load the interface in the user's preferred language
4. THE Platform SHALL support bilingual report generation (财务报表/审计报告/附注) with language selection during export
5. THE Platform SHALL provide language-specific terminology mapping for audit terms (AJE/RJE/TB/PBC etc.)
6. THE Platform SHALL support mixed-language projects (e.g., Chinese interface with English reports for international subsidiaries)

### 需求 3：审计类型扩展

**用户故事：** 作为审计师，我希望系统支持多种审计类型（年度财务报表审计、专项审计、IPO审计、内控审计、验资、税审），以便处理不同类型的审计项目。

#### 验收标准

1. THE Platform SHALL extend the `projects.audit_type` enum to include: 'annual_audit' (年度审计), 'special_audit' (专项审计), 'ipo_audit' (IPO审计), 'internal_control_audit' (内控审计), 'capital_verification' (验资), 'tax_audit' (税审)
2. THE Platform SHALL provide audit type-specific working paper template sets (e.g., IPO审计 requires additional IPO-specific working papers)
3. THE Platform SHALL provide audit type-specific report templates (e.g., 验资 requires a capital verification report template)
4. THE Platform SHALL support audit type-specific audit procedures and risk assessment frameworks
5. WHEN a project is created with a specific audit type, THE Platform SHALL automatically recommend the corresponding template set and procedures

### 需求 4：用户自定义底稿模板

**用户故事：** 作为审计师，我希望能够创建自定义底稿模板、行业专用模板，并扩展取数公式DSL，以便满足不同行业和客户的特殊需求。

#### 验收标准

1. THE Platform SHALL allow users to create custom working paper templates via the UI (upload .xlsx/.docx files with custom formulas and regions)
2. THE Platform SHALL provide a template marketplace/sharing mechanism within the firm (users can publish templates for other users to use)
3. THE Platform SHALL allow users to extend the formula DSL with custom functions (e.g., industry-specific calculation functions)
4. THE Platform SHALL support template versioning for user-created templates
5. THE Platform SHALL provide template categories (行业专用/客户专用/个人收藏) for organization
6. WHEN a user uploads a custom template, THE Platform SHALL validate the formula syntax and region definitions before accepting it

### 需求 5：电子签名方案

**用户故事：** 作为审计师，我希望系统支持电子签名/签章，以便实现审计复核的电子化签核流程，并满足审计档案的合规要求。

#### 验收标准

1. THE Platform SHALL implement a `sign_service` interface with three implementation levels:
   - Level 1 (MVP): Username + password confirmation (记录操作人、时间、IP地址)
   - Level 2 (正式阶段): Handwritten signature image + timestamp (手写签名图片绑定时间戳和操作记录)
   - Level 3 (远期扩展): CA digital certificate signature (对接第三方CA机构，具备法律效力)
2. THE Platform SHALL store signature records in a `signature_records` table with fields: id (UUID PK), object_type (enum: working_paper/adjustment/audit_report), object_id (UUID), signer_id (UUID FK), signature_level (enum: level1/level2/level3), signature_data (jsonb, 存储签名图片或证书信息), timestamp (timestamp), ip_address (varchar), is_deleted (boolean, default false), created_at
3. WHEN a user signs a document, THE Platform SHALL record the complete operation chain (who, when, what, IP address)
4. THE Platform SHALL support signature verification for Level 3 (CA certificate)
5. THE Platform SHALL embed digital signatures in exported PDF archives for Level 3
6. THE Platform SHALL support signature revocation and re-signing for archived documents (with approval workflow)

### 需求 6：监管对接

**用户故事：** 作为事务所管理员，我希望系统能对接中注协审计报告备案接口和电子底稿归档标准接口，以便满足监管要求。

#### 验收标准

1. THE Platform SHALL provide API interfaces for CICPA (中国注册会计师协会) audit report filing (审计报告备案)
2. THE Platform SHALL provide API interfaces for electronic working paper archiving standards (电子底稿归档标准)
3. THE Platform SHALL support data format conversion to meet regulatory requirements (e.g., specific XML/JSON schemas)
4. THE Platform SHALL provide regulatory filing status tracking (submitted/pending/approved/rejected)
5. THE Platform SHALL maintain regulatory filing logs for audit trail
6. WHEN a regulatory filing fails, THE Platform SHALL provide detailed error messages and retry mechanisms

### 需求 7：致同底稿编码体系

**用户故事：** 作为审计师，我希望系统内置致同标准的底稿编码体系（B/C/D-N/A/S/Q/Z类底稿），以便与事务所现有的底稿管理体系保持一致。

#### 验收标准

1. THE Platform SHALL provide a built-in Grant Thornton working paper coding system with the following structure:
   - B类 (B1-B60): 初步业务活动 + 风险评估
   - C类 (C1-C26): 控制测试
   - D-N类: 实质性程序 (D销售循环、E货币资金、F存货、G投资、H固定资产、I无形资产、J职工薪酬、K管理、L债务、M权益、N税金)
   - Q类: 关联方循环
   - A类 (A1-A30): 完成阶段
   - S类: 特定项目程序
   - T类: 通用底稿
   - Z类: 永久性档案
2. THE Platform SHALL support the "三测联动" structure (B类穿行测试 → C类控制测试 → D-N类实质性程序) for each audit cycle
3. THE Platform SHALL provide built-in working paper templates following the GT coding system (approximately 600+ templates)
4. THE Platform SHALL allow users to customize the coding system for specific projects or firms
5. THE Platform SHALL generate the working paper index automatically based on the GT coding system when a project is created
6. THE Platform SHALL provide 6 built-in template sets associated with the GT coding system (as defined in 需求文档 附录G.6): 标准年审、精简版、上市公司、IPO、国企附注、上市附注, each template set referencing specific GT coding ranges

### 需求 8：致同品牌视觉规范详细实现

**用户故事：** 作为前端开发者，我希望系统严格遵循《致同GT审计手册设计规范》，以便确保系统外观与事务所品牌形象一致。

#### 验收标准

1. THE Platform SHALL implement the GT brand color system with the following color palette:
   - GT核心紫色: #4b2d77 (主操作按钮、链接、卡片头部背景)
   - GT亮紫色: #A06DFF (渐变终点色、焦点样式)
   - GT深紫色: #2B1D4D (按钮hover状态)
   - 水鸭蓝: #0094B3 (辅助强调色)
   - 珊瑚橙: #FF5149 (错误/高风险状态)
   - 麦田黄: #FFC23D (警告/注意状态)
   - 成功绿: #28A745 (完成/通过状态)
2. THE Platform SHALL use the CSS class naming convention `gt-{component}-{modifier}` for all custom styles
3. THE Platform SHALL implement the spacing system based on 4px grid with primary rhythm unit of 8px
4. THE Platform SHALL implement border radius values: small 4px / medium 8px / large 12px
5. THE Platform SHALL implement GT purple-toned shadows: rgba(75, 45, 119, 0.075/0.15/0.175)
6. THE Platform SHALL implement the font degradation chain: Chinese: 方正悦黑 → 微软雅黑 → 苹方; English: GT Walsheim → Helvetica Neue → Arial
7. THE Platform SHALL implement the working paper visual markers as specified in the design document (AI生成内容、复核意见、审定数等)
8. THE Platform SHALL implement print styles following the GT design specifications (A4, black and white, avoid page breaks)
9. THE Platform SHALL meet WCAG 2.1 AA accessibility standards (contrast ratio ≥ 4.5:1 for normal text, ≥ 3:1 for large text)
10. THE Platform SHALL provide a dark mode CSS variable mapping for future implementation

### 需求 9：附注模版体系完善

**用户故事：** 作为审计师，我希望系统提供完整的国企版和上市版附注模版，包含科目对照、校验公式、宽表公式、正文模版四个配置文件，以便自动生成符合准则要求的附注。

#### 验收标准

1. THE Platform SHALL provide complete SOE (国企版) and Listed (上市版) disclosure note template sets, each containing four configuration components:
   - Account mapping template (科目对照模板): 报表科目→附注表格的映射关系及校验角色
   - Check presets (校验公式预设): 逐科目逐表格定义的校验公式
   - Wide table presets (宽表公式预设): 附注宽表的横向和纵向公式
   - Disclosure text template (报表附注正文模版): 附注正文的文字模版
2. THE Platform SHALL support the following check formula types: 余额核对、宽表横向公式、纵向勾稽、交叉校验、其中项校验、账龄衔接、完整性检查、LLM审核
3. THE Platform SHALL implement the disclosure validation engine with a dual-layer architecture: local rule engine priority + LLM fallback
4. THE Platform SHALL allow users to customize disclosure templates for specific industries or clients
5. THE Platform SHALL support disclosure template versioning and migration

### 需求 10：T型账户法（现金流量表编制）

**用户故事：** 作为审计师，我希望系统提供T型账户分析工具，以便处理固定资产处置、债务重组等复杂现金流量表编制场景。

#### 验收标准

1. THE Platform SHALL provide a T-account analysis tool for complex cash flow statement items
2. THE Platform SHALL support T-account creation for specific accounts (固定资产、累计折旧、债务重组等)
3. THE Platform SHALL allow users to input debit and credit entries to T-accounts
4. THE Platform SHALL automatically calculate net changes and reconcile with balance sheet movements
5. THE Platform SHALL integrate T-account analysis results into the cash flow statement working paper
6. THE Platform SHALL provide T-account templates for common complex transactions

### 需求 11：AI能力预留接口

**用户故事：** 作为系统架构师，我希望系统为未来的AI能力预留接口，以便快速集成新的AI功能而不需要重构核心架构。

#### 验收标准

1. THE Platform SHALL provide extensible AI service interfaces for the following scenarios:
   - 电子发票真伪验证 (对接税务局发票查验接口)
   - 工商信息实时查询 (对接天眼查/企查查API或定期导入缓存)
   - 银行对账单自动对账 (银行流水与账面逐笔自动对账)
   - 印章/签名真伪检测 (对比历史印章样本)
   - 语音审计笔记 (语音转文字)
   - 审计底稿智能复核 (AI辅助检查底稿完整性)
   - 持续审计/实时监控 (对接被审计单位ERP)
   - 多人团队AI群聊协作 (项目组成员在同一对话空间中与AI协同讨论)
2. THE Platform SHALL provide a plugin architecture for AI services (each AI capability as an independent plugin)
3. THE Platform SHALL provide external API integration interfaces with rate limiting and error handling
4. THE Platform SHALL support model switching without code changes (通过配置切换不同LLM模型)
5. THE Platform SHALL provide AI capability enable/disable configuration at the project level

### 需求 12：数据表Schema定义（第八阶段扩展表）

**用户故事：** 作为开发者，我希望第八阶段的数据表Schema清晰定义，以便正确实现扩展功能。

#### 验收标准

1. THE Migration_Framework SHALL create the `accounting_standards` table with columns as defined in Requirement 1
2. THE Migration_Framework SHALL add the `language` column to the `users` table as defined in Requirement 2
3. THE Migration_Framework SHALL extend the `audit_type` enum in the `projects` table as defined in Requirement 3
4. THE Migration_Framework SHALL create the `signature_records` table with columns as defined in Requirement 5
5. THE Migration_Framework SHALL create the `wp_template_custom` table for user-created templates (id UUID PK, user_id UUID FK, template_name varchar, category enum industry/client/personal, template_file_path varchar, is_published boolean, version varchar, is_deleted boolean default false, created_at, updated_at)
6. THE Migration_Framework SHALL create the `regulatory_filing` table for regulatory tracking (id UUID PK, project_id UUID FK, filing_type enum cicpa_report/archival_standard, filing_status enum submitted/pending/approved/rejected, submission_data jsonb, response_data jsonb, submitted_at timestamp, responded_at timestamp, error_message text, is_deleted boolean default false, created_at, updated_at)
7. THE Migration_Framework SHALL create the `gt_wp_coding` table for GT working paper coding system (id UUID PK, code_prefix varchar, code_range varchar, cycle_name varchar, wp_type enum preliminary/risk_assessment/control_test/substantive/completion/specific/general/permanent, description text, sort_order integer, is_active boolean default true, is_deleted boolean default false, created_at, updated_at)
8. THE Migration_Framework SHALL create the `attachments` table for attachment management (id UUID PK, project_id UUID FK, file_name varchar, file_path varchar, file_type varchar, file_size bigint, paperless_document_id integer, ocr_status enum pending/processing/completed/failed, ocr_text text, is_deleted boolean default false, created_at, updated_at) with composite index on (project_id, ocr_status)

> **注意：** `journal_entries` 分区表和穿透查询索引的定义见需求15（大数据处理优化），此处不重复定义，避免冗余。

### 需求 13：Metabase数据可视化集成

**冲突说明：**

本需求与Phase 4 AI功能存在潜在功能重叠（都提供数据分析能力），与前端三栏布局存在iframe嵌入冲突，与ONLYOFFICE存在使用场景混淆风险。此外，Metabase看板中的"项目进度看板"与三栏布局右侧栏的"项目概览/关键指标"Tab存在功能重叠——Metabase侧重管理层全局视角（跨项目汇总、趋势分析），右侧栏侧重单项目操作视角（当前项目的快捷入口和实时指标）。解决方案详见design.md"与以往需求的冲突及解决方案"章节。

**用户故事：** 作为审计师，我希望系统能提供数据可视化看板，以便直观查看项目进度、账套数据、审计调整汇总等信息。

#### 验收标准

1. THE Platform SHALL integrate Metabase as an independent service (Docker deployment) connected to the audit system PostgreSQL database
2. THE Platform SHALL provide pre-built dashboard templates for:
   - Project overview (项目进度看板): working paper completion rate, review completion rate, days to archive deadline
   - Account set overview (账套总览): general ledger balance, subsidiary ledger balance, voucher count
   - Account penetration (科目穿透): selected account → automatically generate penetration query view
   - Auxiliary account analysis (辅助账分析): balance analysis by dimension (customer/supplier/department)
   - Voucher trend (凭证趋势): time series chart of voucher count and amount
3. THE Platform SHALL provide SQL query templates for ledger penetration (total/ledger/voucher/auxiliary account queries)
4. THE Platform SHALL embed Metabase dashboards in the frontend using Metabase Embedding API or iframe
5. THE Platform SHALL support drill-down from dashboard visualizations to underlying data (total ledger → subsidiary ledger → vouchers)
6. THE Platform SHALL cache dashboard query results in Redis (TTL=5 minutes) to improve performance

### 需求 14：Paperless-ngx附件文档管理集成

**冲突说明：**

本需求与Phase 3协作功能的附件管理存在重叠（两套附件管理系统），与Phase 4 PaddleOCR存在OCR引擎选择冲突，与现有文件存储机制存在冲突。解决方案详见design.md"与以往需求的冲突及解决方案"章节。

**用户故事：** 作为审计师，我希望系统能管理附件文档（合同、发票、银行对账单、证照等），支持OCR识别和全文搜索，并关联到底稿作为审计证据。

#### 验收标准

1. THE Platform SHALL integrate Paperless-ngx as an independent service (Docker deployment) for document management
2. THE Platform SHALL provide REST API integration with Paperless-ngx for:
   - Upload documents to Paperless-ngx
   - Retrieve documents from Paperless-ngx
   - Full-text search across documents
3. THE Platform SHALL support OCR recognition for scanned documents (using Tesseract built into Paperless-ngx)
4. THE Platform SHALL support automatic document classification by customer, period, and document type
5. THE Platform SHALL allow users to associate attachments with working papers for audit evidence chain management
6. THE Platform SHALL support confirmation reply management with OCR recognition to extract reply amount, reply date, and reply entity
7. THE Platform SHALL provide attachment preview in the frontend using vue-office components for quick viewing
8. THE Platform SHALL store OCR results in the `attachments` table for full-text search

### 需求 15：大数据处理优化（账套数据联动查询）

**冲突说明：**

本需求与现有数据库结构存在冲突（需要分区表迁移），与现有查询API存在功能重叠，与前端现有组件存在一致性冲突。解决方案详见design.md"与以往需求的冲突及解决方案"章节。

**用户故事：** 作为审计师，我希望系统能高效处理大量账套数据的联动查询（总账→明细账→凭证→辅助账），以便快速穿透查询和数据分析。

#### 验收标准

1. THE Platform SHALL implement ledger penetration query API: GET /api/projects/{id}/ledger/penetrate with parameters for account_code, date_range, drill_level, company_code
2. THE Platform SHALL return penetration data in three levels: total (aggregate totals), ledger (detailed entries), voucher (voucher-level detail)
3. THE Platform SHALL use Common Table Expressions (CTE) to query multiple levels in a single database query for optimal performance
4. THE Platform SHALL implement Redis caching for penetration query results (TTL=5 minutes) to reduce database load
5. THE Platform SHALL implement frontend virtual scrolling for large datasets (render only visible rows to handle tens of thousands of records)
6. THE Platform SHALL partition the `journal_entries` table by year to improve query performance for historical data
7. THE Platform SHALL provide composite indexes on core query paths (project_id + year + company_code + account_code)
8. THE Platform SHALL support drill-down from dashboard visualizations to ledger penetration queries


### 需求 16：前端三栏布局（对应需求文档 12.2.2）

**用户故事：** 作为审计师，我希望系统提供三栏式工作台布局（左侧功能导航 + 中间内容列表 + 右侧详情预览），以便在多任务并行工作场景下高效操作。

#### 验收标准

1. THE Platform SHALL implement a three-column layout with: left sidebar (1级功能导航, default 220px, collapsible to 56px icon mode), middle panel (2级内容区域, default 340px), right panel (项目详情预览, auto-fill remaining width)
2. THE Platform SHALL provide draggable resizers between columns with width constraints: left sidebar 180-300px, middle panel 250-500px, right panel minimum 600px
3. THE Platform SHALL persist user layout preferences (column widths, collapsed state) in localStorage
4. THE Platform SHALL support responsive design: auto-collapse sidebar at screen width < 1200px, hide sidebar at < 1000px with hamburger menu
5. THE Platform SHALL support fullscreen mode for the right panel (double-click tab to enter, ESC to exit, hides left and middle columns)
6. THE Platform SHALL implement keyboard navigation: Tab to switch between columns, arrow keys for list items, Enter to open details, ESC to close dialogs/exit fullscreen
7. THE Platform SHALL use ARIA roles for accessibility: left sidebar `role="navigation"`, middle panel `role="main"` (in browse mode), right panel `role="complementary"` (in browse mode) or `role="main"` (in full-width mode)
8. WHEN user is on the project browse page (/ or /projects), THE Platform SHALL show three-column mode with project list in middle and project detail in right panel
9. WHEN user navigates to a specific project sub-page (/projects/:id/xxx), THE Platform SHALL hide the middle panel and show the sub-page content in full-width right panel

### 需求 17：vue-office 轻量级文档预览（对应需求文档 12.9.1 第3项）

**冲突说明：**

本需求与ONLYOFFICE存在使用场景重叠。vue-office仅用于附件快速预览（只读），ONLYOFFICE用于底稿编辑（读写）。在附件列表中使用vue-office预览，点击"编辑"按钮才打开ONLYOFFICE。

**用户故事：** 作为审计师，我希望能快速预览附件文档（合同、发票、回函等），无需打开完整编辑器，以便提高审阅效率。

#### 验收标准

1. THE Platform SHALL integrate vue-office components (@vue-office/docx, @vue-office/excel, @vue-office/pdf) for lightweight document preview
2. THE Platform SHALL provide a unified AttachmentPreview.vue component that auto-detects file type and renders the appropriate vue-office component
3. THE Platform SHALL use vue-office for read-only preview in: attachment list, confirmation reply preview, knowledge base document preview
4. THE Platform SHALL use scoped styles to isolate vue-office components from the GT brand style system, preventing style conflicts
5. THE Platform SHALL clearly distinguish preview mode (vue-office, read-only) from edit mode (ONLYOFFICE, full editing) in the UI

### 需求 18：Teable/Grist 评估（对应需求文档 12.9.4 P2）

**用户故事：** 作为系统架构师，我希望评估 Teable 或 Grist 作为辅助数据管理工具的可行性，以便为 PBC 清单管理、函证管理、底稿索引管理等场景提供更灵活的表格化管理能力。

#### 验收标准

1. THE Platform SHALL evaluate Teable and Grist as potential auxiliary tools for structured data management scenarios
2. THE evaluation SHALL cover the following use cases: PBC checklist management (PBC清单管理), confirmation management (函证管理), working paper index management (底稿索引管理)
3. THE evaluation SHALL assess: deployment complexity (Docker), API integration feasibility, data synchronization with PostgreSQL, UI embedding options, licensing compatibility
4. IF evaluation is positive, THE Platform SHALL provide integration guidelines and a proof-of-concept implementation for one use case
5. THE evaluation results SHALL be documented with a recommendation (adopt/defer/reject) and rationale
