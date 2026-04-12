# 实现计划：第四阶段AI赋能 — 本地LLM+OCR单据识别+AI辅助底稿+合同分析+证据链验证+知识库对话+函证AI+自然语言操控

## 概述

本实现计划将设计文档中的架构和组件拆解为可执行的编码任务，按照基础设施→AI服务层→业务服务→前端页面→测试的顺序递进实现。每个任务构建在前序任务之上。技术栈：Python（FastAPI + SQLAlchemy + Celery + Ollama + PaddleOCR + ChromaDB）+ TypeScript（Vue 3 + Pinia）。

## 任务

- [ ] 1. 数据库迁移：创建12张AI相关表及索引
  - [ ] 1.1 创建 Alembic 迁移脚本，定义 `ai_model_config` 表（UUID PK、model_name varchar not null、model_type enum chat/embedding/ocr、provider enum ollama/openai_compatible/paddleocr、endpoint_url varchar、is_active boolean default false、context_window integer、performance_notes text nullable、created_at、updated_at）及唯一索引 (model_name, model_type)
    - _需求: 10.1_
  - [ ] 1.2 创建 `document_scan` 表（UUID PK、project_id UUID FK、company_code varchar、year varchar(4)、file_path varchar not null、file_name varchar not null、file_size integer、document_type enum sales_invoice/purchase_invoice/bank_receipt/bank_statement/outbound_order/inbound_order/logistics_order/voucher/expense_report/toll_invoice/contract/customs_declaration/unknown、recognition_status enum pending/processing/completed/failed、uploaded_by UUID FK、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, document_type) 和索引 (recognition_status)
    - _需求: 10.2_
  - [ ] 1.3 创建 `document_extracted` 表（UUID PK、document_scan_id UUID FK、field_name varchar not null、field_value text、confidence_score numeric(3,2)、human_confirmed boolean default false、confirmed_by UUID FK nullable、confirmed_at timestamp nullable、is_deleted boolean default false、created_at、updated_at）及索引 (document_scan_id) 和索引 (confidence_score)
    - _需求: 10.3_
  - [ ] 1.4 创建 `document_match` 表（UUID PK、document_scan_id UUID FK、matched_voucher_no varchar nullable、matched_account_code varchar nullable、matched_amount numeric(20,2) nullable、match_result enum matched/mismatched/unmatched、difference_amount numeric(20,2) nullable、difference_description text nullable、is_deleted boolean default false、created_at、updated_at）及索引 (document_scan_id) 和索引 (match_result)
    - _需求: 10.4_
  - [ ] 1.5 创建 `ai_content` 表（UUID PK、project_id UUID FK、workpaper_id UUID FK nullable、content_type enum data_fill/analytical_review/risk_alert/test_summary/note_draft、content_text text not null、data_sources jsonb、generation_model varchar、generation_time timestamp、confidence_level enum high/medium/low、confirmation_status enum pending/accepted/modified/rejected/regenerated、confirmed_by UUID FK nullable、confirmed_at timestamp nullable、modification_note text nullable、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, workpaper_id, content_type) 和索引 (confirmation_status)
    - _需求: 10.5_
  - [ ] 1.6 创建 `contracts` 表（UUID PK、project_id UUID FK、company_code varchar、contract_no varchar、party_a varchar、party_b varchar、contract_amount numeric(20,2) nullable、contract_date date nullable、effective_date date nullable、expiry_date date nullable、contract_type enum sales/purchase/service/lease/loan/guarantee/other、file_path varchar、analysis_status enum pending/analyzing/completed/failed、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, contract_type)
    - _需求: 10.6_
  - [ ] 1.7 创建 `contract_extracted` 表（UUID PK、contract_id UUID FK、clause_type enum amount/payment_terms/delivery_terms/penalty/guarantee/pledge/related_party/special_terms/pricing/duration、clause_content text not null、confidence_score numeric(3,2)、human_confirmed boolean default false、is_deleted boolean default false、created_at、updated_at）及索引 (contract_id, clause_type)
    - _需求: 10.7_
  - [ ] 1.8 创建 `contract_wp_link` 表（UUID PK、contract_id UUID FK、workpaper_id UUID FK、link_type enum revenue_recognition/cutoff_test/contingent_liability/related_party/guarantee、link_description text nullable、is_deleted boolean default false、created_at）及复合索引 (contract_id, workpaper_id)
    - _需求: 10.8_
  - [ ] 1.9 创建 `evidence_chain` 表（UUID PK、project_id UUID FK、chain_type enum revenue/purchase/expense、source_document_id UUID FK、target_document_id UUID FK nullable、chain_step integer、match_status enum matched/mismatched/missing、mismatch_description text nullable、risk_level enum high/medium/low、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, chain_type) 和索引 (risk_level)
    - _需求: 10.9_
  - [ ] 1.10 创建 `knowledge_index` 表（UUID PK、project_id UUID FK、source_type enum trial_balance/journal/auxiliary/contract/document_scan/workpaper/adjustment/elimination/confirmation/review_comment/prior_year_summary、source_id UUID、content_text text not null、embedding_vector varchar、chunk_index integer、is_deleted boolean default false、created_at、updated_at）及复合索引 (project_id, source_type)
    - _需求: 10.10_
  - [ ] 1.11 创建 `ai_chat_history` 表（UUID PK、project_id UUID FK、conversation_id UUID、user_id UUID FK、role enum user/assistant/system、message_text text not null、referenced_sources jsonb nullable、model_used varchar、token_count integer nullable、created_at）及复合索引 (project_id, conversation_id, created_at) 和索引 (user_id)
    - _需求: 10.11_
  - [ ] 1.12 创建 `confirmation_ai_check` 表（UUID PK、confirmation_list_id UUID FK、check_type enum address_verify/reply_ocr/amount_compare/seal_check、check_result jsonb、risk_level enum high/medium/low/pass、human_confirmed boolean default false、confirmed_by UUID FK nullable、confirmed_at timestamp nullable、is_deleted boolean default false、created_at）及索引 (confirmation_list_id, check_type)
    - _需求: 10.12_

- [ ] 2. 定义 SQLAlchemy ORM 模型与 Pydantic Schema
  - [ ] 2.1 在 `backend/app/models/` 下创建 `ai_models.py`，定义12张表对应的 SQLAlchemy ORM 模型（AIModelConfig、DocumentScan、DocumentExtracted、DocumentMatch、AIContent、Contract、ContractExtracted、ContractWPLink、EvidenceChain、KnowledgeIndex、AIChatHistory、ConfirmationAICheck），包含所有字段、枚举类型、外键关系
    - _需求: 10.1-10.12_
  - [ ] 2.2 在 `backend/app/models/` 下创建 `ai_schemas.py`，定义所有 API 请求/响应的 Pydantic Schema（AIModelConfigResponse、OCRUploadResponse/BatchResult、DocumentScanList/ExtractedFieldUpdate、AIContentCreate/ConfirmAction/Summary、ContractUpload/ExtractedResponse/CrossReferenceResult/WPLinkCreate、EvidenceChainResult/Summary、ChatRequest/StreamResponse/HistoryList、ConfirmationAICheckResult/ConfirmAction、FileAnalysisRequest/FolderAnalysisResult 等）
    - _需求: 1-10_

- [ ] 3. 检查点 — 确保数据库迁移和模型定义正确
  - 运行 `alembic upgrade head` 确认迁移成功，确保所有ORM模型和Schema定义无语法错误。

- [ ] 4. AI基础设施：Ollama + PaddleOCR + ChromaDB 部署与集成
  - [ ] 4.1 更新 `docker-compose.yml`，新增 Ollama 容器（端口11434、GPU透传可选、模型持久化卷）和 ChromaDB 容器（端口8000、数据持久化卷）；PaddleOCR 作为 Python 包安装在后端容器中
    - _需求: 1.1_
  - [ ] 4.2 实现 `backend/app/services/ai_service.py` — AI服务统一抽象层：chat_completion（调Ollama API，支持同步和SSE流式）、embedding（调Ollama embedding API）、ocr_recognize（调PaddleOCR）、get_active_model（从ai_model_config表读取）、switch_model（含10秒可用性验证）、health_check（检查Ollama/PaddleOCR/ChromaDB三个引擎状态）
    - _需求: 1.2, 1.4, 1.6_
  - [ ] 4.3 实现 AI 服务管理 API 路由 `backend/app/routers/ai_admin.py`：GET /api/ai/health（健康检查）、GET /api/ai/models（模型列表）、PUT /api/ai/models/{id}/activate（激活模型+可用性验证）、POST /api/ai/evaluate（LLM能力评估接口）
    - _需求: 1.1, 1.3, 1.4, 1.5_
  - [ ] 4.4 预置 ai_model_config 初始数据：插入默认模型配置（qwen2.5:7b chat模型、nomic-embed-text embedding模型、paddleocr ocr引擎），Ollama chat模型设为is_active=true
    - _需求: 1.3_

- [ ] 5. 检查点 — 确保AI基础设施正常运行
  - 启动Docker Compose，验证Ollama健康检查通过、PaddleOCR可识别测试图片、ChromaDB可创建collection。

- [ ] 6. OCR识别服务 (OCRService)
  - [ ] 6.1 实现 `backend/app/services/ocr_service_v2.py`：recognize_single（单张单据OCR识别，调PaddleOCR，≤5秒）、classify_document（AI自动分类单据类型，调LLM）、extract_fields（按DOCUMENT_FIELD_RULES提取结构化字段，调LLM语义理解）
    - _需求: 2.1, 2.2, 2.4_
  - [ ] 6.2 实现 batch_recognize（批量OCR识别，提交Celery异步任务，逐个文件处理：OCR→分类→字段提取→写入document_scan和document_extracted表）、get_task_status（查询异步任务进度）
    - _需求: 2.4_
  - [ ] 6.3 实现 match_with_ledger（单据数据与账面数据自动匹配：按金额+日期+摘要关键词匹配journal_entries，写入document_match表）
    - _需求: 2.7_
  - [ ] 6.4 实现 OCR API 路由 `backend/app/routers/ai_ocr.py`：POST /api/ai/ocr/upload（单张上传+识别）、POST /api/ai/ocr/batch-upload（批量上传+异步识别）、GET /api/ai/ocr/task/{task_id}（任务进度）、GET /api/projects/{id}/documents（单据列表）、GET /api/projects/{id}/documents/{did}/extracted（提取结果）、PUT /api/projects/{id}/documents/{did}/extracted/{eid}（人工修正）、POST /api/projects/{id}/documents/{did}/match（触发匹配）
    - _需求: 2.2-2.7_

- [ ] 7. AI辅助底稿填充服务 (WorkpaperFillService)
  - [ ] 7.1 实现 `backend/app/services/workpaper_fill_service.py`：generate_analytical_review（从trial_balance取本年/上年余额→计算变动额和变动率→从journal_entries取大额交易摘要→从auxiliary_balance取前N大客户/供应商→LLM生成分析叙述含变动原因分析+异常标注+建议程序）
    - _需求: 3.1, 3.6_
  - [ ] 7.2 实现 generate_workpaper_data（按底稿模板类型生成填充数据：表格数据+测试说明+变动分析+风险提示）、generate_note_draft（按附注模板自动取数填充生成初稿文字）
    - _需求: 3.1_
  - [ ] 7.2a 实现 review_workpaper_with_prompt（提示词驱动的底稿AI智能复核：通过workpaper_id→audit_cycle→匹配TSJ/下对应提示词→注入LLM system prompt替换{{#sys.files#}}→按提示词框架逐项检查→输出结构化复核发现→存入ai_content表）和 load_review_prompt（按科目名称关键词匹配TSJ/下的.md文件）
    - _需求: 3.7, 3.8, 3.9_
  - [ ] 7.3 实现 AI内容管理服务 `backend/app/services/ai_content_service.py`：create_content（创建AI内容记录，初始状态pending）、confirm_content（确认/修改/拒绝/重新生成）、get_pending_count（未确认数量）、get_project_summary（项目AI内容汇总统计）、check_phase_gate（检查阶段转换门控）、check_boundary（检查AI边界）
    - _需求: 3.2, 3.3, 3.4, 3.5, 9.1-9.5_
  - [ ] 7.4 实现 AI辅助底稿 API 路由 `backend/app/routers/ai_workpaper.py`：POST /api/ai/workpaper-fill（生成底稿填充）、POST /api/ai/analytical-review（生成分析性复核）、POST /api/ai/note-draft（生成附注初稿）、POST /api/ai/workpaper-review（提示词驱动底稿AI复核）、GET /api/projects/{id}/ai-content（AI内容列表）、PUT /api/projects/{id}/ai-content/{cid}/confirm（确认AI内容）、GET /api/projects/{id}/ai-content/summary（汇总统计）、GET /api/projects/{id}/ai-content/pending-count（未确认数量）
    - _需求: 3.1-3.9, 9.1-9.5_

- [ ] 8. 检查点 — 确保OCR和底稿填充服务正确
  - 运行单元测试确认：OCR识别流程、字段提取、账面匹配、AI内容创建和确认流程、边界检查。

- [ ] 9. 合同分析服务 (ContractAnalysisService)
  - [ ] 9.1 实现 `backend/app/services/contract_analysis_service.py`：analyze_contract（单个合同分析：扫描件先OCR→LLM提取关键条款→写入contract_extracted表）、batch_analyze（批量合同分析，Celery异步任务）
    - _需求: 4.1, 4.2, 4.6_
  - [ ] 9.2 实现 cross_reference_ledger（合同与账面数据交叉比对：合同金额vs收入/成本发生额、合同账期vs实际回款周期、合同到期日vs审计基准日、合同对方vs关联方清单）、link_to_workpaper（建立合同与底稿关联）、generate_contract_summary（项目合同汇总报告）
    - _需求: 4.3, 4.4, 4.5_
  - [ ] 9.3 实现合同分析 API 路由 `backend/app/routers/ai_contract.py`：POST /api/projects/{id}/contracts/upload（上传合同）、POST /api/projects/{id}/contracts/batch-analyze（批量分析）、GET /api/projects/{id}/contracts（合同列表）、GET /api/projects/{id}/contracts/{cid}/extracted（条款提取结果）、POST /api/projects/{id}/contracts/{cid}/cross-reference（交叉比对）、POST /api/projects/{id}/contracts/{cid}/link-workpaper（关联底稿）、GET /api/projects/{id}/contracts/summary（汇总报告）
    - _需求: 4.1-4.6_

- [ ] 10. 证据链验证服务 (EvidenceChainService)
  - [ ] 10.1 实现 `backend/app/services/evidence_chain_service.py`：verify_revenue_chain（收入循环证据链验证：合同→出库→物流→发票→凭证→回款，按金额/日期/客户名/品名匹配，标注缺失和不一致）
    - _需求: 5.1_
  - [ ] 10.2 实现 verify_purchase_chain（采购循环证据链验证：合同→入库→发票→凭证→付款，标注异常：有付款无入库、数量不符、付款对象不一致）
    - _需求: 5.2_
  - [ ] 10.3 实现 verify_expense_chain（费用报销证据链验证：申请→发票→报销单→审批→凭证，标注异常：日期不匹配、地点不一致、发票连号、金额卡审批临界值、周末大额报销）
    - _需求: 5.3_
  - [ ] 10.4 实现 analyze_bank_statements（银行流水深度分析：大额异常交易识别、资金体外循环检测A→B→C→A、关联方资金往来标注、期末集中收付款标注、非营业时间交易、整数金额大额转账）
    - _需求: 5.4_
  - [ ] 10.5 实现 generate_chain_summary（生成证据链验证汇总报告：总数/匹配/不匹配/缺失/高风险）、自动生成ai_content风险提示记录关联到对应底稿
    - _需求: 5.5, 5.6_
  - [ ] 10.6 实现证据链验证 API 路由 `backend/app/routers/ai_evidence_chain.py`：POST /api/projects/{id}/evidence-chain/revenue（收入验证）、POST /api/projects/{id}/evidence-chain/purchase（采购验证）、POST /api/projects/{id}/evidence-chain/expense（费用验证）、POST /api/projects/{id}/evidence-chain/bank-analysis（银行流水分析）、GET /api/projects/{id}/evidence-chain（结果列表）、GET /api/projects/{id}/evidence-chain/summary/{type}（汇总报告）
    - _需求: 5.1-5.6_

- [ ] 11. 检查点 — 确保合同分析和证据链验证服务正确
  - 运行单元测试确认：合同条款提取、交叉比对逻辑、证据链匹配算法、银行流水分析、风险提示自动生成。

- [ ] 12. 知识库索引与AI对话服务
  - [ ] 12.1 实现 `backend/app/services/knowledge_index_service.py`：build_index（全量构建项目知识库索引，遍历trial_balance/journal/auxiliary/contract/document_scan/workpaper/adjustment/elimination/confirmation/review_comment数据，分块→embedding→写入ChromaDB collection）、incremental_update（增量更新，数据变更时触发）、lock_index（归档时锁定为只读）、delete_index（项目删除时清理）
    - _需求: 6.1, 6.2, 6.7_
  - [ ] 12.2 实现 semantic_search（语义检索：query embedding→ChromaDB similarity_search top_k=10→返回相关文档片段和相似度分数）、search_cross_year（跨年度检索：同时搜索当前项目和上年项目的索引）
    - _需求: 6.4, 6.6_
  - [ ] 12.3 实现 `backend/app/services/ai_chat_service.py`：chat_with_rag（RAG增强对话：解析意图→语义检索→注入上下文→LLM生成→SSE流式输出→记录ai_chat_history）、build_system_prompt（注入项目元数据：公司名/审计年度/重要性水平/当前阶段）、get_conversation_history（获取多轮对话历史）
    - _需求: 6.3, 6.4, 6.5_
  - [ ] 12.4 注册数据变更事件处理器：在EventBus中订阅数据导入完成、底稿保存、调整分录变更、函证结果更新等事件，触发knowledge_index_service.incremental_update
    - _需求: 6.2_
  - [ ] 12.5 实现 AI对话 API 路由 `backend/app/routers/ai_chat.py`：POST /api/ai/chat（SSE流式对话）、GET /api/projects/{id}/chat/history（对话历史）、POST /api/ai/chat/file-analysis（文件智能分析）、POST /api/ai/chat/folder-analysis（文件夹批量分析）、DELETE /api/projects/{id}/chat/conversations/{cid}（删除对话）
    - _需求: 6.3-6.6, 8.3, 8.4_

- [ ] 13. 函证AI辅助服务 (ConfirmationAIService)
  - [ ] 13.1 实现 `backend/app/services/confirmation_ai_service.py`：verify_addresses（批量地址核查：比对工商登记地址缓存+上年函证地址+标注异常地址+银行函证校验开户行名称，写入confirmation_ai_check表）
    - _需求: 7.1_
  - [ ] 13.2 实现 ocr_reply_scan（回函扫描件OCR识别：PaddleOCR提取文字→LLM提取回函单位名称/确认金额/签章/回函日期→与原始函证金额比对→写入confirmation_ai_check表）
    - _需求: 7.2_
  - [ ] 13.3 实现 check_seal（印章检测与名称比对：检测印章存在性→提取印章文字→与函证对象名称比对→银行函证校验银行业务专用章）、analyze_mismatch_reason（不符差异原因智能分析：匹配在途款项+识别记账时间差+生成差异原因建议）
    - _需求: 7.3, 7.4, 7.6_
  - [ ] 13.4 实现函证AI辅助 API 路由 `backend/app/routers/ai_confirmation.py`：POST /api/projects/{id}/confirmations/ai/address-verify（地址核查）、POST /api/projects/{id}/confirmations/{cid}/ai/ocr-reply（回函OCR）、POST /api/projects/{id}/confirmations/{cid}/ai/mismatch-analysis（差异分析）、GET /api/projects/{id}/confirmations/ai/checks（AI检查结果列表）、PUT /api/projects/{id}/confirmations/ai/checks/{chk}/confirm（确认AI检查结果）
    - _需求: 7.1-7.6_

- [ ] 14. 自然语言指令服务 (NLCommandService)
  - [ ] 14.1 实现 `backend/app/services/nl_command_service.py`：parse_intent（解析用户意图：正则匹配已知指令模式→附件检测→分类为系统操作/数据查询/文件分析/通用对话）、execute_command（执行已确认的系统操作指令：项目切换/年度切换/底稿导航/数据查询/分析生成/差异展示）
    - _需求: 8.1, 8.2_
  - [ ] 14.2 实现 analyze_file（单文件智能分析：检测文件类型→合同走合同分析/Excel走报表分析/银行流水走流水分析/扫描件走OCR→返回结构化分析结果）、analyze_folder（文件夹批量分析：遍历文件→分类统计→生成资料清单→标注缺失→与PBC清单比对）
    - _需求: 8.3, 8.4_
  - [ ] 14.3 集成自然语言指令到AI对话流程：在ai_chat_service.chat_with_rag中增加意图解析前置步骤，系统操作指令返回确认卡片，文件分析请求调用对应分析服务，通用查询走RAG流程
    - _需求: 8.1-8.6_

- [ ] 15. 检查点 — 确保所有后端AI服务正确
  - 运行单元测试确认：知识库索引构建和检索、RAG对话流程、函证地址核查、回函OCR、印章检测、自然语言指令解析、AI内容门控。

- [ ] 16. 前端：AI对话面板
  - [ ] 16.1 创建 `frontend/src/components/ai/AIChatPanel.vue`：项目页面右侧可折叠侧边栏，SSE流式输出+Markdown渲染、多轮对话历史（按conversation_id分组）、文件拖入/选择上传区域、项目上下文自动注入（项目名/年度/公司/重要性水平）、数据来源引用标签（点击跳转源数据）
    - _需求: 6.3, 8.1_
  - [ ] 16.2 创建 `frontend/src/components/ai/CommandConfirmCard.vue`：系统操作确认卡片组件（操作名称+参数+确认执行/取消按钮），嵌入AI对话消息流中，用户点击确认后才执行操作
    - _需求: 8.2_

- [ ] 17. 前端：单据识别页面
  - [ ] 17.1 创建 `frontend/src/components/ai/DocumentOCRPanel.vue`：Tab切换（按12种单据类型分类+全部），批量上传区域（拖拽+点击，支持图片/PDF），异步识别进度条，识别结果表格（字段名/字段值/置信度/确认状态），低置信度字段（<0.80）红色高亮，人工修正编辑功能，与账面数据匹配结果展示
    - _需求: 2.2-2.7_

- [ ] 18. 前端：合同分析页面
  - [ ] 18.1 创建 `frontend/src/components/ai/ContractAnalysisPanel.vue`：双栏布局（左栏合同文件预览PDF/图片，右栏AI提取的关键条款列表含条款类型/内容/置信度），底部与账面数据交叉比对结果表格，关联底稿操作按钮，批量分析进度和汇总报告视图
    - _需求: 4.1-4.6_

- [ ] 19. 前端：证据链验证页面
  - [ ] 19.1 创建 `frontend/src/components/ai/EvidenceChainPanel.vue`：三Tab（收入循环/采购循环/费用报销）+银行流水分析Tab，证据链可视化流程图（节点=单据，连线=匹配关系，红色=缺失/不一致），异常清单表格（风险等级/异常描述/涉及单据/建议程序），验证汇总统计卡片（总数/匹配/不匹配/缺失/高风险）
    - _需求: 5.1-5.6_

- [ ] 20. 前端：函证AI辅助面板
  - [ ] 20.1 创建 `frontend/src/components/ai/ConfirmationAIPanel.vue`：嵌入函证管理页面的AI辅助区域，地址核查结果列表（地址/核查结果/风险等级/确认状态），回函OCR识别结果（提取字段/金额比对/印章检测），不符差异原因建议，所有结果标注"AI辅助-待人工确认"，确认/拒绝操作按钮
    - _需求: 7.1-7.6_

- [ ] 21. 前端：AI内容管理看板
  - [ ] 21.1 创建 `frontend/src/components/ai/AIContentDashboard.vue`：项目级AI内容统计视图，汇总卡片（总数/已确认/待确认/已拒绝/修改率），按底稿分组的AI内容列表，按内容类型筛选（数据填充/分析复核/风险提示/测试摘要/附注初稿），批量确认/拒绝操作
    - _需求: 9.4_

- [ ] 22. 前端：路由与状态管理
  - [ ] 22.1 在 `frontend/src/router/` 中注册AI模块路由（/projects/{id}/ai-chat、/projects/{id}/documents、/projects/{id}/contracts、/projects/{id}/evidence-chain、/projects/{id}/ai-content），在 `frontend/src/stores/` 中创建 ai store（Pinia）管理AI服务状态、对话历史、OCR任务进度、AI内容统计
    - _需求: 1-10_
  - [ ] 22.2 在 `frontend/src/services/` 中创建 `aiApi.ts`，封装所有AI相关API调用（ai-admin、ai-ocr、ai-workpaper、ai-contract、ai-evidence-chain、ai-chat、ai-confirmation），含SSE流式响应处理和异步任务轮询
    - _需求: 1-10_

- [ ] 23. 检查点 — 确保前端页面和API集成正确
  - 手动测试完整流程：上传单据→OCR识别→人工确认→上传合同→AI分析→交叉比对→证据链验证→AI对话查询→函证地址核查→回函OCR→AI内容确认→查看AI看板。

- [ ] 24. 后端单元测试
  - [ ] 24.1 编写 `backend/tests/test_ai_service.py`：测试AI服务统一抽象层（健康检查、模型切换+可用性验证、降级处理、边界检查）
    - _需求: 1.2, 1.4, 1.6, 9.3_
  - [ ] 24.2 编写 `backend/tests/test_ocr_service.py`：测试OCR识别流程（单张识别≤5秒、批量异步处理、字段提取、置信度标注、低置信度强制复核、人工修正记录、账面数据匹配）
    - _需求: 2.1-2.7_
  - [ ] 24.3 编写 `backend/tests/test_workpaper_fill.py`：测试AI底稿填充（分析性复核生成、AI内容创建/确认/拒绝/重新生成、关键底稿pending门控、阶段转换门控、AI标注持久化）
    - _需求: 3.1-3.6, 9.1, 9.2, 9.5_
  - [ ] 24.4 编写 `backend/tests/test_contract_analysis.py`：测试合同分析（条款提取、交叉比对四项检查、特殊条款风险提示、合同与底稿关联、批量分析）
    - _需求: 4.1-4.6_
  - [ ] 24.5 编写 `backend/tests/test_evidence_chain.py`：测试证据链验证（收入/采购/费用三条链匹配逻辑、缺失环节标注、不一致标注、银行流水分析六项检测、风险提示自动生成）
    - _需求: 5.1-5.6_
  - [ ] 24.6 编写 `backend/tests/test_knowledge_index.py`：测试知识库索引（全量构建、增量更新、语义检索、跨年度检索、归档锁定、数据变更触发更新）
    - _需求: 6.1-6.7_
  - [ ] 24.7 编写 `backend/tests/test_confirmation_ai.py`：测试函证AI辅助（地址核查、回函OCR识别、金额比对、印章检测、差异原因分析、强制人工确认门控）
    - _需求: 7.1-7.6_
  - [ ] 24.8 编写 `backend/tests/test_nl_command.py`：测试自然语言指令（意图解析六种指令类型、操作确认机制、文件分析路由、文件夹批量分析、PBC清单比对）
    - _需求: 8.1-8.6_
  - [ ] 24.9 编写 `backend/tests/test_ai_content_compliance.py`：测试AI合规性（AI内容标注持久化、PDF导出保留标签、AI边界不可逾越、数据本地处理不外传、模型切换可用性验证）
    - _需求: 9.1-9.6_
