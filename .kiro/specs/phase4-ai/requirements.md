# 需求文档：第四阶段AI赋能 — 本地LLM+OCR单据识别+AI辅助底稿+合同分析+证据链验证+知识库对话+函证AI+自然语言操控

## 简介

本文档定义审计作业平台第四阶段AI赋能功能的需求。在Phase 0/1/2/3已实现的稳定业务基础上，叠加本地AI能力。核心原则：AI=提效工具，人工=最终责任。AI不替代专业判断，关键底稿必须人工确认。涵盖九大核心模块：本地LLM能力评估与部署（Ollama+AI服务层抽象+模型切换）、PaddleOCR本地部署与单据智能识别（12类单据结构化提取+批量处理+置信度标注）、AI辅助底稿填充与分析性复核（科目分析+变动率+异常波动+初稿生成+待确认机制）、合同智能分析（关键条款提取+账面数据交叉比对+底稿联动）、收入/采购/费用证据链交叉验证（全链条自动匹配+缺失/不一致标注）、项目知识库索引与AI对话（ChromaDB向量库+增量索引+SSE流式输出）、函证AI辅助（地址核查+回函OCR识别+金额比对+印章预检）、自然语言对话操控（语音/文字指令+操作确认+文件智能分析）、AI内容标注与确认机制（AI辅助生成标记+强制确认+审计档案合规）。本阶段依赖Phase 0/1/2/3已实现的全部基础设施和业务模块。

## 术语表

- **Platform（审计作业平台）**：面向会计师事务所的本地私有化审计全流程作业系统
- **AI_Service（AI服务层）**：统一的AI能力抽象层，屏蔽底层模型差异，提供LLM推理、OCR识别、向量检索等能力
- **Ollama（本地LLM引擎）**：本地部署的大语言模型推理引擎，支持多模型切换
- **PaddleOCR（本地OCR引擎）**：百度开源的本地OCR识别引擎，用于单据/回函扫描件的文字识别
- **ChromaDB（向量数据库）**：本地部署的向量数据库，用于项目知识库索引和语义检索
- **Document_Scan（单据扫描件）**：上传到系统的原始单据图片或PDF文件
- **Document_Extracted（结构化提取数据）**：AI从单据中提取的字段名、字段值、置信度等结构化数据
- **Contract（合同）**：被审计单位的业务合同，AI从中提取关键条款用于审计分析
- **Evidence_Chain（证据链）**：审计证据的完整链条，如收入循环：合同→出库→物流→发票→回款
- **Knowledge_Index（知识库索引）**：基于ChromaDB的项目级向量索引，支持语义检索
- **AI_Content（AI辅助内容）**：AI生成的底稿内容、分析结果等，必须标注为"AI辅助生成"并经人工确认
- **Confidence_Score（置信度分数）**：AI识别结果的可信程度，0-1之间的浮点数
- **SSE（Server-Sent Events）**：服务器推送事件协议，用于AI对话的流式输出
- **Confirmation_AI（函证AI辅助）**：AI在函证管理中的辅助能力，包括地址核查、回函OCR、金额比对

## 需求

### 需求 1：本地LLM能力评估与Ollama部署

**用户故事：** 作为项目经理，我希望系统能在本地部署LLM并提供统一的AI服务层，以便在不依赖外部网络的情况下使用AI辅助审计功能，同时支持灵活切换不同模型。

#### 验收标准

1. THE Platform SHALL integrate Ollama as the local LLM inference engine, deployed via Docker container within the existing Docker Compose stack, with health check endpoint monitoring at `/api/ai/health`
2. THE AI_Service SHALL provide a unified abstraction layer with interface methods: `chat_completion(messages, model, stream)`, `embedding(text, model)`, `analyze(content, task_type, model)`, supporting both synchronous and asynchronous (SSE streaming) response modes
3. THE AI_Service SHALL support model switching through the `ai_model_config` table with fields: id (UUID PK), model_name (varchar not null), model_type (enum: chat/embedding/ocr), provider (enum: ollama/openai_compatible/paddleocr), endpoint_url (varchar), is_active (boolean default false), context_window (integer), performance_notes (text, nullable), created_at, updated_at; with unique index on (model_name, model_type)
4. WHEN the active LLM model is changed, THE AI_Service SHALL validate model availability by sending a test prompt and verifying response within 10 seconds before activating the new model
5. THE Platform SHALL provide an LLM capability evaluation interface at `/api/ai/evaluate` that accepts a test dataset of audit-domain questions and returns accuracy metrics, response latency, and domain-specific performance scores
6. IF Ollama service is unavailable, THEN THE AI_Service SHALL return a graceful degradation response with error code "AI_SERVICE_UNAVAILABLE" and all AI-dependent features SHALL display "AI服务暂不可用" without blocking core audit workflows

### 需求 2：PaddleOCR本地部署与单据智能识别

**用户故事：** 作为审计员，我希望能批量上传单据扫描件（发票、出入库单、物流单、报销单等），系统自动OCR识别并提取结构化数据，以便快速获取审计证据而无需手工录入。

#### 验收标准

1. THE Platform SHALL integrate PaddleOCR as the local OCR engine, deployed via Docker container or Python package within the backend service, supporting Chinese and English text recognition
2. THE Platform SHALL support OCR recognition for 12 document types stored in the `document_scan` table with fields: id (UUID PK), project_id (UUID FK), company_code (varchar), year (varchar(4)), file_path (varchar not null), file_name (varchar not null), file_size (integer), document_type (enum: sales_invoice/purchase_invoice/bank_receipt/bank_statement/outbound_order/inbound_order/logistics_order/voucher/expense_report/toll_invoice/contract/customs_declaration/unknown), recognition_status (enum: pending/processing/completed/failed), uploaded_by (UUID FK), is_deleted (boolean default false), created_at, updated_at; with composite index on (project_id, document_type)
3. THE Platform SHALL store AI-extracted structured data in the `document_extracted` table with fields: id (UUID PK), document_scan_id (UUID FK), field_name (varchar not null), field_value (text), confidence_score (numeric(3,2), range 0.00-1.00), human_confirmed (boolean default false), confirmed_by (UUID FK nullable), confirmed_at (timestamp nullable), is_deleted (boolean default false), created_at, updated_at; with index on (document_scan_id)
4. WHEN a batch of scanned documents is uploaded, THE Platform SHALL automatically classify document types using AI, process OCR recognition asynchronously via Celery task queue, and return a task_id for progress tracking; single document OCR processing SHALL complete within 5 seconds
5. THE Platform SHALL highlight extracted fields with confidence_score below 0.80 in the review interface, requiring mandatory human review before the data can be used in audit analysis
6. WHEN a user manually corrects an AI-extracted field value, THE Platform SHALL record the correction as training feedback in the `document_extracted` table by updating field_value and setting human_confirmed=true, confirmed_by, and confirmed_at
7. THE Platform SHALL support automatic matching of extracted document data with ledger data through the `document_match` table with fields: id (UUID PK), document_scan_id (UUID FK), matched_voucher_no (varchar nullable), matched_account_code (varchar nullable), matched_amount (numeric(20,2) nullable), match_result (enum: matched/mismatched/unmatched), difference_amount (numeric(20,2) nullable), difference_description (text nullable), is_deleted (boolean default false), created_at, updated_at; with index on (document_scan_id)

### 需求 3：AI辅助底稿填充与分析性复核

**用户故事：** 作为审计员，我希望AI能自动从试算表和账表数据中提取信息，生成底稿内容初稿（包括变动分析、异常标注、分析性复核），以便减少重复性数据整理工作，将精力集中在专业判断上。

#### 验收标准

1. THE AI_Service SHALL provide a workpaper auto-fill function that reads data from trial_balance, journal_entries, and auxiliary_balance tables for the specified project, account code, and year, generating structured workpaper content including: period-over-period change amounts and rates, significant fluctuation annotations (change rate exceeding 20% or change amount exceeding performance materiality), top-N transaction summaries, and analytical review narrative draft
2. WHEN AI generates workpaper content, THE Platform SHALL store each generated item in the `ai_content` table with fields: id (UUID PK), project_id (UUID FK), workpaper_id (UUID FK nullable), content_type (enum: data_fill/analytical_review/risk_alert/test_summary/note_draft), content_text (text not null), data_sources (jsonb, array of source references), generation_model (varchar), generation_time (timestamp), confidence_level (enum: high/medium/low), confirmation_status (enum: pending/accepted/modified/rejected/regenerated), confirmed_by (UUID FK nullable), confirmed_at (timestamp nullable), modification_note (text nullable), is_deleted (boolean default false), created_at, updated_at; with composite index on (project_id, workpaper_id, content_type)
3. THE Platform SHALL mark all AI-generated content with visual indicator: GT light purple background color `rgba(75,45,119,0.08)` and a label "AI辅助生成-待确认"; each AI content item SHALL display: data source references, analysis logic, confidence level, and risk rating (high/medium/low)
4. WHEN Auditor reviews AI-generated content, THE Platform SHALL support four actions: accept (confirmation_status="accepted"), modify and accept (confirmation_status="modified" with modification_note), reject (confirmation_status="rejected"), or regenerate (confirmation_status="regenerated" triggering a new AI generation); only accepted or modified content SHALL be included in the audited workpaper data
5. THE Platform SHALL enforce that critical workpapers (revenue, receivables/payables, inventory impairment, long-term investments, consolidation, contingent liabilities, related party transactions, going concern, subsequent events) cannot have any AI content with confirmation_status="pending" when submitted for review; THE Platform SHALL block review submission and display the count of unconfirmed AI items
6. THE AI_Service SHALL generate analytical review drafts that include: account balance comparison (current year vs prior year), change amount and percentage calculation, industry benchmark comparison (when available), identification of unusual fluctuations with suggested explanations, and recommended additional audit procedures for significant variances
7. WHEN AI performs workpaper review or generates analytical review content, THE AI_Service SHALL automatically load the corresponding audit review prompt from the `TSJ/` prompt library based on the workpaper's audit cycle mapping (e.g., workpaper code "E1" maps to audit cycle "货币资金" which loads "货币资金提示词.md"); the loaded prompt SHALL be injected as the LLM system prompt to drive structured review covering: audit assertion checkpoints (existence/completeness/accuracy/rights_obligations/classification), risk-prioritized review items (high/medium/low), industry-specific review points, and standardized finding report format
8. THE Platform SHALL manage the audit review prompt library (`TSJ/` directory, ~70 Markdown files organized by report line item) with the following capabilities: auto-load all prompt files on system startup into the prompt registry, support online editing with version history (edit/replace/append/restore), automatic matching between workpaper audit cycle and prompt file via account name keywords, and support for firm-level customization (add industry-specific prompts, modify existing review checkpoints)
9. WHEN AI generates review findings from prompt-driven workpaper review, THE Platform SHALL output structured findings containing: finding_type (data_discrepancy/logic_contradiction/completeness_gap/accuracy_error), severity (level_1_high/level_2_medium/level_3_low), description (with specific sheet name and cell range reference), evidence_reference (linked audit evidence location), and remediation_suggestion (with specific target location), following the standardized problem report format defined in the prompt templates

### 需求 4：合同智能分析

**用户故事：** 作为审计员，我希望AI能从合同文本中自动提取关键条款（金额、账期、交货条件、违约条款等），并与账面数据交叉比对，以便快速识别收入确认、或有负债、关联方交易等关键审计事项。

#### 验收标准

1. THE Platform SHALL provide a contract analysis interface that accepts contract files (scanned PDF via OCR or electronic PDF/Word) and stores contract metadata in the `contracts` table with fields: id (UUID PK), project_id (UUID FK), company_code (varchar), contract_no (varchar), party_a (varchar), party_b (varchar), contract_amount (numeric(20,2) nullable), contract_date (date nullable), effective_date (date nullable), expiry_date (date nullable), contract_type (enum: sales/purchase/service/lease/loan/guarantee/other), file_path (varchar), analysis_status (enum: pending/analyzing/completed/failed), is_deleted (boolean default false), created_at, updated_at; with composite index on (project_id, contract_type)
2. THE AI_Service SHALL extract key contract terms and store them in the `contract_extracted` table with fields: id (UUID PK), contract_id (UUID FK), clause_type (enum: amount/payment_terms/delivery_terms/penalty/guarantee/pledge/related_party/special_terms/pricing/duration), clause_content (text not null), confidence_score (numeric(3,2)), human_confirmed (boolean default false), is_deleted (boolean default false), created_at, updated_at; with index on (contract_id, clause_type)
3. THE Platform SHALL automatically cross-reference contract data with ledger data: contract amount vs corresponding revenue/cost account balances (annotate differences), contract payment terms vs actual collection period (calculate overdue days and link to receivable aging analysis), contract expiry date vs audit base date (identify cross-period contracts for cutoff testing), contract counterparty name vs related party list (auto-match and flag related party transactions)
4. THE Platform SHALL maintain contract-to-workpaper linkage through the `contract_wp_link` table with fields: id (UUID PK), contract_id (UUID FK), workpaper_id (UUID FK), link_type (enum: revenue_recognition/cutoff_test/contingent_liability/related_party/guarantee), link_description (text nullable), is_deleted (boolean default false), created_at; with composite index on (contract_id, workpaper_id)
5. WHEN a contract contains special terms (return rights, price adjustments, repurchase obligations, variable consideration), THE AI_Service SHALL automatically generate a risk alert with content_type="risk_alert" in the ai_content table, flagging the revenue recognition method requires attention
6. THE Platform SHALL support batch contract analysis: WHEN multiple contract files are uploaded, THE Platform SHALL process them asynchronously, classify by contract_type, and generate a contract summary report listing all extracted key terms grouped by contract type

### 需求 5：收入/采购/费用证据链交叉验证

**用户故事：** 作为审计员，我希望AI能自动匹配收入、采购、费用循环中的多种单据数据，构建完整的审计证据链，标注缺失环节或数据不一致，以便快速发现异常交易和潜在风险。

#### 验收标准

1. THE AI_Service SHALL provide revenue cycle evidence chain verification by automatically matching: contract → order → outbound_order → logistics_order (delivery confirmation) → sales_invoice → voucher → bank_receipt (collection); matching criteria include amount, date, customer name, and product name/quantity; THE Platform SHALL store matching results in the `evidence_chain` table with fields: id (UUID PK), project_id (UUID FK), chain_type (enum: revenue/purchase/expense), source_document_id (UUID FK to document_scan or contracts), target_document_id (UUID FK nullable), chain_step (integer, sequence position in the chain), match_status (enum: matched/mismatched/missing), mismatch_description (text nullable), risk_level (enum: high/medium/low), is_deleted (boolean default false), created_at, updated_at; with composite index on (project_id, chain_type)
2. THE AI_Service SHALL provide purchase cycle evidence chain verification by automatically matching: purchase_contract → purchase_order → inbound_order → purchase_invoice → voucher → bank_payment; flagging anomalies including: payment without inbound record, inbound quantity mismatching invoice quantity, payment recipient mismatching contract supplier
3. THE AI_Service SHALL provide expense reimbursement evidence chain verification by automatically matching: travel_request → expense_invoices (transport/hotel/meal/toll) → expense_report → approval_record → voucher; flagging anomalies including: invoice date mismatching travel date, hotel location mismatching travel destination, consecutive invoice numbers, amounts exactly at approval threshold, weekend/holiday large reimbursements, same person frequent short-interval travel
4. THE AI_Service SHALL provide bank statement deep analysis: automatically identify large abnormal transactions (exceeding performance materiality), flag circular fund transfers (A→B→C→A patterns), identify related party fund flows (matching against related party list), flag period-end concentrated large receipts/payments (cutoff testing focus), flag non-business-hours transactions, flag round-number large transfers
5. WHEN evidence chain verification identifies missing links or inconsistencies, THE Platform SHALL automatically generate ai_content records with content_type="risk_alert" linked to the corresponding workpaper, with risk_level classification and recommended follow-up procedures
6. THE Platform SHALL generate evidence chain verification summary reports per audit cycle (revenue/purchase/expense), listing: total transactions verified, matched count, mismatched count, missing link count, high-risk items requiring attention, and auto-populate these into the corresponding workpaper "需关注事项" section

### 需求 6：项目知识库索引与AI对话

**用户故事：** 作为审计员，我希望能通过自然语言与AI对话，基于当前项目的全部数据（账表、底稿、合同、单据、调整分录、函证等）获取即时回答，以便快速查询项目信息和获取分析支持。

#### 验收标准

1. THE Platform SHALL build a project-level knowledge index using ChromaDB vector database, storing embeddings in the `knowledge_index` table with fields: id (UUID PK), project_id (UUID FK), source_type (enum: trial_balance/journal/auxiliary/contract/document_scan/workpaper/adjustment/elimination/confirmation/review_comment/prior_year_summary), source_id (UUID, reference to the source record), content_text (text not null), embedding_vector (varchar, ChromaDB collection reference), chunk_index (integer, for large documents split into chunks), is_deleted (boolean default false), created_at, updated_at; with composite index on (project_id, source_type)
2. WHEN project data changes (data import, workpaper editing, adjustment entry, confirmation result update), THE Platform SHALL automatically trigger incremental index update via Celery background task, updating only the changed records in ChromaDB; full re-index SHALL be available as a manual operation
3. THE Platform SHALL provide a project-scoped AI chat interface at `/api/ai/chat` accepting SSE streaming responses with fields: project_id (UUID), message (text), conversation_id (UUID for multi-turn context), attachments (array of file references, optional); first token output SHALL appear within 3 seconds
4. THE AI_Service SHALL implement RAG (Retrieval-Augmented Generation) for chat: retrieve top-K relevant chunks from ChromaDB based on user query embedding similarity, inject retrieved context into LLM prompt along with project metadata (company name, audit year, materiality level), and generate contextually accurate responses with source citations
5. THE Platform SHALL store chat history in the `ai_chat_history` table with fields: id (UUID PK), project_id (UUID FK), conversation_id (UUID), user_id (UUID FK), role (enum: user/assistant/system), message_text (text not null), referenced_sources (jsonb nullable, array of source citations), model_used (varchar), token_count (integer nullable), created_at; with composite index on (project_id, conversation_id, created_at)
6. THE Platform SHALL support cross-year project knowledge linking: WHEN a user queries about prior year audit data, THE AI_Service SHALL search the prior year project's knowledge index (if accessible) and include relevant prior year context in the response, clearly labeling it as "上年数据参考"
7. WHEN the project enters "archived" status, THE Platform SHALL lock the knowledge index as read-only, preventing further updates; the archived index SHALL remain queryable for reference purposes

### 需求 7：函证AI辅助（地址核查+回函OCR比对）

**用户故事：** 作为审计员，我希望AI能在函证管理流程中提供辅助：发函前自动核查收件地址的合理性，回函后自动OCR识别扫描件并与原始函证金额比对，以便降低退函率并加速回函核对工作。

#### 验收标准

1. THE AI_Service SHALL provide confirmation address verification: WHEN a confirmation list is submitted for approval, THE Platform SHALL automatically compare each counterparty's mailing address against: business registration address (from cached business data), prior year confirmation address (from prior year project data), and flag suspicious addresses including: incomplete address, mismatch with business registration, address changed from prior year, suspected non-business location (residential address); results stored in the `confirmation_ai_check` table with fields: id (UUID PK), confirmation_list_id (UUID FK), check_type (enum: address_verify/reply_ocr/amount_compare/seal_check), check_result (jsonb, structured check findings), risk_level (enum: high/medium/low/pass), human_confirmed (boolean default false), confirmed_by (UUID FK nullable), confirmed_at (timestamp nullable), is_deleted (boolean default false), created_at; with index on (confirmation_list_id, check_type)
2. WHEN a confirmation reply scan is uploaded, THE AI_Service SHALL perform OCR recognition to extract: replying entity name, confirmed amount, seal/stamp presence, signatory name, reply date; THE Platform SHALL automatically compare OCR-extracted confirmed_amount with the original book_amount from confirmation_list, flagging matches and mismatches with difference amounts
3. THE AI_Service SHALL perform seal verification on reply scans: detect presence of official seal, extract seal text, compare seal entity name with the expected counterparty name; mismatches SHALL be flagged as high-risk with check_type="seal_check"
4. FOR bank confirmations specifically, THE AI_Service SHALL verify that the bank seal name matches the account-opening bank name from the confirmation list; mismatches SHALL generate a high-risk alert
5. THE Platform SHALL mark all AI-assisted confirmation check results with label "AI辅助-待人工确认"; Auditor MUST review and confirm each AI check result before the confirmation can be marked as complete in the confirmation workflow
6. THE AI_Service SHALL provide intelligent mismatch reason analysis: WHEN a confirmation reply amount does not match the book amount, THE Platform SHALL automatically search for in-transit items (matching against post-period bank statements and receipt/payment records) and timing differences (matching against voucher dates), generating suggested mismatch reasons for human review

### 需求 8：自然语言对话操控与文件智能分析

**用户故事：** 作为审计员，我希望能通过自然语言指令操控系统（切换项目、打开底稿、查询数据等），并能拖入文件让AI自动分析，以便提高操作效率和减少界面导航时间。

#### 验收标准

1. THE Platform SHALL provide a natural language command interface within the AI chat panel that recognizes and dispatches the following command types: project switching ("切换到XX项目"), year switching ("切换到2024年度"), workpaper navigation ("打开货币资金底稿"), data query ("查询应收账款前五大客户"), analysis generation ("生成收入变动分析"), difference display ("展示本年与上年利润表差异")
2. WHEN AI interprets a user command as a system operation (navigation, data modification, report generation), THE Platform SHALL display the interpreted action as a confirmation card in the chat interface; the operation SHALL only execute after the user clicks the "确认执行" button; AI SHALL NOT auto-execute any system operations
3. THE Platform SHALL support single-file intelligent analysis: WHEN a user drags or selects a file (PDF contract, Excel report, scanned document, Word document) into the chat panel, THE AI_Service SHALL automatically detect file type and execute corresponding analysis: contract → extract key terms summary, Excel → identify report type and extract key data and flag anomalies, bank statement → parse transaction details and flag large anomalies, scanned document → OCR then structured extraction; analysis results can be inserted into the current workpaper with one click
4. THE Platform SHALL support folder batch analysis: WHEN a user selects a folder, THE AI_Service SHALL traverse all files, classify by type, generate a structured inventory listing (file name, type, key information summary, suggested audit area linkage), flag missing documents (e.g., "有采购合同但未见对应入库单"), and support automatic comparison with PBC checklist to identify received/outstanding items
5. THE Platform SHALL store all natural language commands and their execution results in the ai_chat_history table with role="user" for commands and role="assistant" for responses, maintaining full audit trail of AI-assisted operations
6. WHEN AI chat is used within a project context, THE Platform SHALL automatically inject project metadata (project name, audit year, company name, materiality level, current project phase) into the system prompt, ensuring all AI responses are contextually relevant to the current project

### 需求 9：AI内容标注与确认机制（人机联动合规）

**用户故事：** 作为合伙人，我希望系统能确保所有AI辅助生成的内容在审计档案中被明确标注，且关键底稿的AI内容必须经过人工确认，以便满足监管对审计档案真实性和审计师责任的要求。

#### 验收标准

1. THE Platform SHALL enforce that all AI-generated content displayed in workpapers, analysis reports, and audit documentation carries a persistent label "AI辅助生成" with the generation timestamp and model version; this label SHALL be preserved in exported PDF archives and printed documents
2. THE Platform SHALL maintain an AI content audit trail: every AI generation, human confirmation, modification, or rejection action SHALL be recorded in the ai_content table with full history (no physical deletion, only status changes), enabling QC_Reviewer to trace the complete lifecycle of any AI-assisted content
3. THE Platform SHALL enforce the AI boundary rules: AI SHALL NOT auto-process or generate conclusions for: significant audit judgments, impairment/fair value/provision estimates, fraud risk identification conclusions, consolidation scope decisions, audit opinion type determination; WHEN AI detects that a user request falls within these boundaries, THE AI_Service SHALL respond with "此事项需要审计师专业判断，AI仅提供数据参考，不生成结论"
4. THE Platform SHALL provide an AI content summary dashboard per project showing: total AI-generated items count, confirmed count, pending count, rejected count, modification rate; this dashboard SHALL be accessible to manager, partner, and qc_reviewer roles
5. WHEN a project enters the "reporting" phase, THE Platform SHALL verify that zero AI content items remain with confirmation_status="pending" across all workpapers; IF pending items exist, THEN THE Platform SHALL block the phase transition and display the list of workpapers with unconfirmed AI content
6. THE Platform SHALL ensure all AI processing occurs locally: document scans, contract texts, and financial data SHALL NOT be transmitted to any external service; OCR and LLM inference SHALL use locally deployed PaddleOCR and Ollama exclusively; the AI_Service SHALL reject any configuration that points to external API endpoints for processing audit client data

### 需求 10：数据表Schema定义（第四阶段AI相关表）

**用户故事：** 作为开发者，我希望第四阶段AI相关数据表的Schema明确定义，以便通过Alembic迁移脚本创建表结构。

#### 验收标准

1. THE Migration_Framework SHALL create the `ai_model_config` table with columns as defined in Requirement 1.3, with unique index on (model_name, model_type)
2. THE Migration_Framework SHALL create the `document_scan` table with columns as defined in Requirement 2.2, with composite index on (project_id, document_type) and index on (recognition_status)
3. THE Migration_Framework SHALL create the `document_extracted` table with columns as defined in Requirement 2.3, with index on (document_scan_id) and index on (confidence_score)
4. THE Migration_Framework SHALL create the `document_match` table with columns as defined in Requirement 2.7, with index on (document_scan_id) and index on (match_result)
5. THE Migration_Framework SHALL create the `ai_content` table with columns as defined in Requirement 3.2, with composite index on (project_id, workpaper_id, content_type) and index on (confirmation_status)
6. THE Migration_Framework SHALL create the `contracts` table with columns as defined in Requirement 4.1, with composite index on (project_id, contract_type)
7. THE Migration_Framework SHALL create the `contract_extracted` table with columns as defined in Requirement 4.2, with index on (contract_id, clause_type)
8. THE Migration_Framework SHALL create the `contract_wp_link` table with columns as defined in Requirement 4.4, with composite index on (contract_id, workpaper_id)
9. THE Migration_Framework SHALL create the `evidence_chain` table with columns as defined in Requirement 5.1, with composite index on (project_id, chain_type) and index on (risk_level)
10. THE Migration_Framework SHALL create the `knowledge_index` table with columns as defined in Requirement 6.1, with composite index on (project_id, source_type)
11. THE Migration_Framework SHALL create the `ai_chat_history` table with columns as defined in Requirement 6.5, with composite index on (project_id, conversation_id, created_at) and index on (user_id)
12. THE Migration_Framework SHALL create the `confirmation_ai_check` table with columns as defined in Requirement 7.1, with index on (confirmation_list_id, check_type)
