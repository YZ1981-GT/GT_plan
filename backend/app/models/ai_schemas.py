"""第四阶段AI赋能：Pydantic Schema 定义

覆盖所有 AI 相关 API 请求/响应模型：
- AI模型配置 (AIModelConfig)
- OCR单据识别 (DocumentScan, DocumentExtracted, DocumentMatch)
- AI内容管理 (AIContent)
- 合同分析 (Contract, ContractExtracted, ContractWPLink)
- 证据链验证 (EvidenceChain)
- 知识库索引 (KnowledgeIndex)
- AI对话 (AIChatHistory)
- 函证AI辅助 (ConfirmationAICheck)
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.ai_models import (
    AIContentType,
    AIConfirmationStatus,
    AIModelType,
    AIProvider,
    ChainMatchStatus,
    ChatRole,
    ClauseType,
    ConfirmationCheckType,
    ConfidenceLevel,
    ContractAnalysisStatus,
    ContractLinkType,
    ContractType,
    DocumentType,
    EvidenceChainType,
    KnowledgeSourceType,
    MatchResult,
    RecognitionStatus,
    RiskLevel,
)


# ===================================================================
# 通用 / 分页
# ===================================================================


class PageParams(BaseModel):
    """分页参数"""
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


class PageResult(BaseModel):
    """分页结果包装"""
    items: list[Any] = []
    total: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 0


# ===================================================================
# 1. AI模型配置 (AIModelConfig)
# ===================================================================


class AIModelConfigResponse(BaseModel):
    """AI模型配置响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_name: str
    model_type: AIModelType
    provider: AIProvider
    endpoint_url: str | None = None
    is_active: bool
    context_window: int | None = None
    performance_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class AIModelCreate(BaseModel):
    """创建AI模型配置"""
    model_name: str = Field(..., min_length=1, max_length=100)
    model_type: AIModelType
    provider: AIProvider
    endpoint_url: str | None = None
    is_active: bool = False
    context_window: int | None = None
    performance_notes: str | None = None


class AIModelActivateRequest(BaseModel):
    """激活模型请求"""
    model_name: str
    model_type: AIModelType


class AIHealthResponse(BaseModel):
    """AI引擎健康检查响应"""
    ollama_status: str  # healthy / unavailable
    paddleocr_status: str
    chromadb_status: str
    active_chat_model: str | None = None
    active_embedding_model: str | None = None
    timestamp: datetime


class AIEvaluationRequest(BaseModel):
    """LLM能力评估请求"""
    questions: list[str]
    expected_answers: list[str] | None = None


class AIEvaluationResult(BaseModel):
    """LLM能力评估结果"""
    model_name: str
    total_questions: int
    accuracy_score: float | None = None
    avg_response_time: float  # 秒
    domain_scores: dict[str, float] = {}
    details: list[dict[str, Any]] = []


# ===================================================================
# 2. OCR单据识别 (DocumentScan, DocumentExtracted, DocumentMatch)
# ===================================================================


class DocumentScanCreate(BaseModel):
    """单据扫描件创建"""
    company_code: str | None = None
    year: str | None = None
    document_type: DocumentType
    file_path: str
    file_name: str
    file_size: int | None = None


class DocumentScanResponse(BaseModel):
    """单据扫描件响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    company_code: str | None = None
    year: str | None = None
    file_path: str
    file_name: str
    file_size: int | None = None
    document_type: DocumentType
    recognition_status: RecognitionStatus
    uploaded_by: UUID | None = None
    created_at: datetime


class ExtractedFieldResponse(BaseModel):
    """提取字段响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_scan_id: UUID
    field_name: str
    field_value: str | None = None
    confidence_score: Decimal | None = None
    human_confirmed: bool
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None


class ExtractedFieldUpdate(BaseModel):
    """人工修正提取字段"""
    field_value: str
    human_confirmed: bool = True


class DocumentMatchResponse(BaseModel):
    """单据匹配结果响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_scan_id: UUID
    matched_voucher_no: str | None = None
    matched_account_code: str | None = None
    matched_amount: Decimal | None = None
    match_result: MatchResult
    difference_amount: Decimal | None = None
    difference_description: str | None = None


class OCRUploadResponse(BaseModel):
    """OCR单张上传响应"""
    document_id: UUID
    file_name: str
    recognition_status: RecognitionStatus
    extracted_fields: list[ExtractedFieldResponse] = []


class OCRBatchResult(BaseModel):
    """OCR批量识别结果"""
    task_id: str
    total_files: int
    processed: int = 0
    completed: int = 0
    failed: int = 0
    status: str  # pending / processing / completed / failed


class OCRTaskStatus(BaseModel):
    """OCR任务状态"""
    task_id: str
    status: str
    progress_percent: float = 0.0
    processed_count: int = 0
    total_count: int = 0
    results: list[OCRUploadResponse] = []


class DocumentFilter(BaseModel):
    """单据筛选"""
    document_type: DocumentType | None = None
    recognition_status: RecognitionStatus | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


# ===================================================================
# 3. AI内容管理 (AIContent)
# ===================================================================


class AIContentCreate(BaseModel):
    """创建AI内容"""
    workpaper_id: UUID | None = None
    content_type: AIContentType
    content_text: str
    data_sources: list[dict[str, Any]] | None = None
    confidence_level: ConfidenceLevel | None = None


class AIContentResponse(BaseModel):
    """AI内容响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    workpaper_id: UUID | None = None
    content_type: AIContentType
    content_text: str
    data_sources: list[dict[str, Any]] | None = None
    generation_model: str | None = None
    generation_time: datetime | None = None
    confidence_level: ConfidenceLevel | None = None
    confirmation_status: AIConfirmationStatus
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None
    modification_note: str | None = None
    created_at: datetime


class AIContentConfirmAction(BaseModel):
    """AI内容确认操作"""
    action: str  # accept / modify / reject / regenerate
    modification_note: str | None = None


class AIContentSummary(BaseModel):
    """AI内容汇总统计"""
    total: int = 0
    pending: int = 0
    accepted: int = 0
    modified: int = 0
    rejected: int = 0
    regenerated: int = 0
    modification_rate: float = 0.0


class AIContentFilter(BaseModel):
    """AI内容筛选"""
    workpaper_id: UUID | None = None
    content_type: AIContentType | None = None
    confirmation_status: AIConfirmationStatus | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


# ===================================================================
# 4. 合同分析 (Contract, ContractExtracted, ContractWPLink)
# ===================================================================


class ContractUpload(BaseModel):
    """上传合同"""
    company_code: str | None = None
    contract_no: str | None = None
    party_a: str | None = None
    party_b: str | None = None
    contract_amount: Decimal | None = None
    contract_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    contract_type: ContractType | None = None


class ContractResponse(BaseModel):
    """合同响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    company_code: str | None = None
    contract_no: str | None = None
    party_a: str | None = None
    party_b: str | None = None
    contract_amount: Decimal | None = None
    contract_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    contract_type: ContractType | None = None
    file_path: str | None = None
    analysis_status: ContractAnalysisStatus
    created_at: datetime


class ContractExtractedResponse(BaseModel):
    """合同条款提取响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_id: UUID
    clause_type: ClauseType
    clause_content: str
    confidence_score: Decimal | None = None
    human_confirmed: bool


class ContractCrossReferenceResult(BaseModel):
    """合同与账面交叉比对结果"""
    contract_id: UUID
    checks: list[dict[str, Any]] = []  # amount / payment_terms / expiry_date / related_party


class ContractWPLinkCreate(BaseModel):
    """关联底稿"""
    workpaper_id: UUID
    link_type: ContractLinkType
    link_description: str | None = None


class ContractWPLinkResponse(BaseModel):
    """合同与底稿关联响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contract_id: UUID
    workpaper_id: UUID
    link_type: ContractLinkType
    link_description: str | None = None
    created_at: datetime


class ContractSummary(BaseModel):
    """合同汇总报告"""
    total_contracts: int = 0
    by_type: dict[str, int] = {}
    total_amount: Decimal = Decimal("0")
    pending_analysis: int = 0
    completed_analysis: int = 0
    special_terms_count: int = 0
    related_party_count: int = 0


class ContractFilter(BaseModel):
    """合同筛选"""
    contract_type: ContractType | None = None
    analysis_status: ContractAnalysisStatus | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


# ===================================================================
# 5. 证据链验证 (EvidenceChain)
# ===================================================================


class EvidenceChainResult(BaseModel):
    """证据链验证结果"""
    chain_type: EvidenceChainType
    chain_step: int
    source_document_id: UUID
    target_document_id: UUID | None = None
    match_status: ChainMatchStatus
    mismatch_description: str | None = None
    risk_level: RiskLevel | None = None


class EvidenceChainSummary(BaseModel):
    """证据链汇总报告"""
    chain_type: EvidenceChainType
    total_transactions: int = 0
    matched: int = 0
    mismatched: int = 0
    missing: int = 0
    high_risk: int = 0
    medium_risk: int = 0
    low_risk: int = 0


class BankAnalysisResult(BaseModel):
    """银行流水分析结果"""
    large_transactions: list[dict[str, Any]] = []
    circular_transfers: list[list[UUID]] = []
    related_party_flows: list[dict[str, Any]] = []
    period_end_concentrations: list[dict[str, Any]] = []
    non_business_hours: list[dict[str, Any]] = []
    round_amount_transfers: list[dict[str, Any]] = []


class EvidenceChainFilter(BaseModel):
    """证据链筛选"""
    chain_type: EvidenceChainType | None = None
    match_status: ChainMatchStatus | None = None
    risk_level: RiskLevel | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)


# ===================================================================
# 6. 知识库索引 (KnowledgeIndex)
# ===================================================================


class KnowledgeSearchResult(BaseModel):
    """知识库检索结果"""
    source_type: KnowledgeSourceType
    source_id: UUID
    content_text: str
    similarity_score: float
    chunk_index: int | None = None


class KnowledgeSearchResponse(BaseModel):
    """知识库检索响应"""
    query: str
    results: list[KnowledgeSearchResult] = []
    total: int = 0


class KnowledgeIndexBuildResponse(BaseModel):
    """知识库构建响应"""
    project_id: UUID
    total_documents: int = 0
    status: str  # building / completed / failed


# ===================================================================
# 7. AI对话 (AIChatHistory)
# ===================================================================


class ChatRequest(BaseModel):
    """对话请求"""
    project_id: UUID
    message: str
    conversation_id: UUID | None = None
    attachments: list[str] = []  # 文件路径列表


class ChatStreamResponse(BaseModel):
    """对话流式响应"""
    conversation_id: UUID
    role: ChatRole
    content: str
    model_used: str | None = None
    referenced_sources: list[dict[str, Any]] | None = None
    finish_reason: str | None = None


class ChatHistoryResponse(BaseModel):
    """对话历史响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    conversation_id: UUID
    user_id: UUID | None = None
    role: ChatRole
    message_text: str
    referenced_sources: list[dict[str, Any]] | None = None
    model_used: str | None = None
    token_count: int | None = None
    created_at: datetime


class ConversationSummary(BaseModel):
    """对话会话摘要"""
    conversation_id: UUID
    message_count: int = 0
    last_message_at: datetime | None = None
    first_message: str | None = None


class FileAnalysisRequest(BaseModel):
    """文件分析请求"""
    file_path: str
    file_type: str | None = None  # contract / excel / bank_statement / scanned


class FileAnalysisResult(BaseModel):
    """文件分析结果"""
    file_path: str
    file_type: str
    summary: str
    key_data: dict[str, Any] = {}
    anomalies: list[str] = []
    suggested_workpaper_link: str | None = None


class FolderAnalysisRequest(BaseModel):
    """文件夹分析请求"""
    folder_path: str
    include_subfolders: bool = True


class FolderAnalysisResult(BaseModel):
    """文件夹分析结果"""
    folder_path: str
    total_files: int = 0
    by_type: dict[str, int] = {}
    file_listings: list[dict[str, Any]] = []
    missing_documents: list[str] = []
    pbc_status: dict[str, Any] | None = None


# ===================================================================
# 8. 函证AI辅助 (ConfirmationAICheck)
# ===================================================================


class ConfirmationAddressVerifyRequest(BaseModel):
    """地址核查请求"""
    confirmation_type: str | None = None  # bank / customer / supplier


class ConfirmationAddressCheckResult(BaseModel):
    """地址核查结果"""
    confirmation_list_id: UUID
    counterparty_name: str
    mailing_address: str
    check_result: str  # normal / suspicious / mismatch
    issues: list[str] = []
    risk_level: RiskLevel | None = None


class ConfirmationOCRReplyResult(BaseModel):
    """回函OCR识别结果"""
    confirmation_list_id: UUID
    replying_entity: str | None = None
    confirmed_amount: Decimal | None = None
    original_book_amount: Decimal | None = None
    amount_difference: Decimal | None = None
    amount_match: bool | None = None
    seal_detected: bool = False
    seal_name: str | None = None
    signatory: str | None = None
    reply_date: date | None = None


class ConfirmationMismatchAnalysisRequest(BaseModel):
    """差异分析请求"""
    confirmation_list_id: UUID


class ConfirmationMismatchAnalysisResult(BaseModel):
    """差异分析结果"""
    confirmation_list_id: UUID
    likely_reasons: list[str] = []
    in_transit_items: list[dict[str, Any]] = []
    timing_differences: list[dict[str, Any]] = []
    suggested_reconciliation: str | None = None


class ConfirmationAICheckResponse(BaseModel):
    """函证AI检查结果响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    confirmation_list_id: UUID
    check_type: ConfirmationCheckType
    check_result: dict[str, Any] | None = None
    risk_level: str | None = None
    human_confirmed: bool
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None


class ConfirmationAICheckConfirmAction(BaseModel):
    """确认函证AI检查结果"""
    action: str  # accept / reject
    notes: str | None = None


# ===================================================================
# 9. AI辅助底稿填充
# ===================================================================


class WorkpaperFillRequest(BaseModel):
    """底稿填充请求"""
    project_id: UUID
    workpaper_id: UUID | None = None
    account_code: str | None = None
    year: int
    template_type: str | None = None  # analytical_review / data_fill / note_draft


class AnalyticalReviewRequest(BaseModel):
    """分析性复核请求"""
    project_id: UUID
    account_code: str
    year: int


class NoteDraftRequest(BaseModel):
    """附注初稿请求"""
    project_id: UUID
    note_section: str
    year: int


class WorkpaperReviewRequest(BaseModel):
    """底稿AI复核请求"""
    project_id: UUID
    workpaper_id: UUID


# ===================================================================
# 10. 自然语言指令
# ===================================================================


class NLCommandIntent(BaseModel):
    """自然语言指令意图"""
    intent_type: str  # project_switch / year_switch / open_workpaper / query_data / generate_analysis / show_difference / file_analysis / chat
    parameters: dict[str, Any] = {}
    requires_confirmation: bool = False
    raw_message: str


class NLCommandConfirmRequest(BaseModel):
    """指令确认执行请求"""
    command_id: str
    confirmed: bool


# ===================================================================
# 11. AI问答会话 (AIChatSession)
# ===================================================================


class SessionType(str, enum.Enum):
    """会话类型"""
    general = "general"
    contract = "contract"
    workpaper = "workpaper"
    confirmation = "confirmation"


class AIChatSessionCreate(BaseModel):
    """创建问答会话"""
    project_id: UUID
    session_type: SessionType = SessionType.general
    title: str | None = None
    user_id: UUID | None = None


class AIChatSessionResponse(BaseModel):
    """问答会话响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    session_type: SessionType
    title: str | None = None
    user_id: UUID | None = None
    total_messages: int
    total_tokens: int
    context_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class AIChatMessageCreate(BaseModel):
    """创建消息"""
    role: ChatRole
    message_text: str
    referenced_sources: dict | None = None
    model_used: str | None = None
    tokens_used: int | None = None
    latency_ms: int | None = None


class AIChatMessageResponse(BaseModel):
    """消息响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    role: ChatRole
    message_text: str
    referenced_sources: dict | None = None
    model_used: str | None = None
    tokens_used: int | None = None
    latency_ms: int | None = None
    created_at: datetime


class AIChatRequest(BaseModel):
    """AI问答请求"""
    session_id: UUID
    message: str
    use_rag: bool = True
    stream: bool = True


class AIChatResponse(BaseModel):
    """AI问答响应"""
    session_id: UUID
    message: str
    sources: list[dict] = []
    tokens_used: int = 0
    latency_ms: int = 0


# ===================================================================
# 12. AI知识库 (AIKnowledgeBase)
# ===================================================================


class AIKnowledgeBaseResponse(BaseModel):
    """知识库文档响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    doc_uuid: UUID
    source_type: SourceType
    chunk_index: int | None = None
    content_hash: str
    created_at: datetime


# ===================================================================
# 13. AI合同分析报告 (AIAnalysisReport)
# ===================================================================


class AnalysisReportStatus(str, enum.Enum):
    """分析报告状态"""
    pending = "pending"
    analyzing = "analyzing"
    completed = "completed"
    failed = "failed"


class AIAnalysisReportCreate(BaseModel):
    """创建分析报告"""
    project_id: UUID
    document_type: str
    document_name: str | None = None


class AIAnalysisReportResponse(BaseModel):
    """分析报告响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    document_type: str
    document_name: str | None = None
    summary: str | None = None
    key_findings: dict | None = None
    risk_indicators: dict | None = None
    confidence_score: Decimal | None = None
    status: AnalysisReportStatus
    created_at: datetime
    updated_at: datetime


class AIAnalysisItemResponse(BaseModel):
    """分析条目响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    report_id: UUID
    clause_type: ClauseType | None = None
    clause_text: str
    extraction_result: dict | None = None
    risk_flag: bool
    risk_reason: str | None = None
    confidence_score: Decimal | None = None
    human_confirmed: bool
    human_note: str | None = None
    created_at: datetime


# ===================================================================
# 14. AI函证审核 (AIConfirmationAudit)
# ===================================================================


class AIConfirmationAuditCreate(BaseModel):
    """创建函证审核"""
    project_id: UUID
    confirmation_type: str
    original_content: str
    response_content: str | None = None
    audit_period: str
    audit_result: dict | None = None
    user_id: UUID | None = None


class AIConfirmationAuditResponse(BaseModel):
    """函证审核响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    confirmation_type: str
    original_content: str
    response_content: str | None = None
    audit_period: str
    audit_result: dict | None = None
    status: AIConfirmationStatus
    user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
