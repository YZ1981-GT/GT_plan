"""第四阶段AI赋能：12张AI相关表的 SQLAlchemy ORM 模型

对应 Alembic 迁移脚本 016_ai_tables.py，包含：
- AIModelConfig：AI模型配置
- DocumentScan：单据扫描件
- DocumentExtracted：单据结构化提取
- DocumentMatch：单据与账面匹配
- AIContent：AI生成内容
- Contract：合同
- ContractExtracted：合同条款提取
- ContractWPLink：合同与底稿关联
- EvidenceChain：证据链
- KnowledgeIndex：知识库索引
- AIChatHistory：AI对话历史
- ConfirmationAICheck：函证AI检查
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin


# ---------------------------------------------------------------------------
# PostgreSQL 枚举类型（与迁移 016 一致）
# ---------------------------------------------------------------------------


class AIModelType(str, enum.Enum):
    """AI模型类型"""
    chat = "chat"
    embedding = "embedding"
    ocr = "ocr"


class AIProvider(str, enum.Enum):
    """AI模型供应商"""
    ollama = "ollama"
    openai_compatible = "openai_compatible"
    paddleocr = "paddleocr"


class DocumentType(str, enum.Enum):
    """单据类型"""
    sales_invoice = "sales_invoice"
    purchase_invoice = "purchase_invoice"
    bank_receipt = "bank_receipt"
    bank_statement = "bank_statement"
    outbound_order = "outbound_order"
    inbound_order = "inbound_order"
    logistics_order = "logistics_order"
    voucher = "voucher"
    expense_report = "expense_report"
    toll_invoice = "toll_invoice"
    contract = "contract"
    customs_declaration = "customs_declaration"
    unknown = "unknown"


class RecognitionStatus(str, enum.Enum):
    """OCR识别状态"""
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class MatchResult(str, enum.Enum):
    """匹配结果"""
    matched = "matched"
    mismatched = "mismatched"
    unmatched = "unmatched"


class AIContentType(str, enum.Enum):
    """AI内容类型"""
    data_fill = "data_fill"
    analytical_review = "analytical_review"
    risk_alert = "risk_alert"
    test_summary = "test_summary"
    note_draft = "note_draft"


class ConfidenceLevel(str, enum.Enum):
    """置信度等级"""
    high = "high"
    medium = "medium"
    low = "low"


class AIConfirmationStatus(str, enum.Enum):
    """AI内容确认状态"""
    pending = "pending"
    accepted = "accepted"
    modified = "modified"
    rejected = "rejected"
    regenerated = "regenerated"


class ContractType(str, enum.Enum):
    """合同类型"""
    sales = "sales"
    purchase = "purchase"
    service = "service"
    lease = "lease"
    loan = "loan"
    guarantee = "guarantee"
    other = "other"


class ContractAnalysisStatus(str, enum.Enum):
    """合同分析状态"""
    pending = "pending"
    analyzing = "analyzing"
    completed = "completed"
    failed = "failed"


class ClauseType(str, enum.Enum):
    """合同条款类型"""
    amount = "amount"
    payment_terms = "payment_terms"
    delivery_terms = "delivery_terms"
    penalty = "penalty"
    guarantee = "guarantee"
    pledge = "pledge"
    related_party = "related_party"
    special_terms = "special_terms"
    pricing = "pricing"
    duration = "duration"


class ContractLinkType(str, enum.Enum):
    """合同与底稿关联类型"""
    revenue_recognition = "revenue_recognition"
    cutoff_test = "cutoff_test"
    contingent_liability = "contingent_liability"
    related_party = "related_party"
    guarantee = "guarantee"


class EvidenceChainType(str, enum.Enum):
    """证据链类型"""
    revenue = "revenue"
    purchase = "purchase"
    expense = "expense"


class ChainMatchStatus(str, enum.Enum):
    """证据链匹配状态"""
    matched = "matched"
    mismatched = "mismatched"
    missing = "missing"


class RiskLevel(str, enum.Enum):
    """风险等级"""
    high = "high"
    medium = "medium"
    low = "low"


class KnowledgeSourceType(str, enum.Enum):
    """知识库来源类型"""
    trial_balance = "trial_balance"
    journal = "journal"
    auxiliary = "auxiliary"
    contract = "contract"
    document_scan = "document_scan"
    workpaper = "workpaper"
    adjustment = "adjustment"
    elimination = "elimination"
    confirmation = "confirmation"
    review_comment = "review_comment"
    prior_year_summary = "prior_year_summary"


class ChatRole(str, enum.Enum):
    """对话角色"""
    user = "user"
    assistant = "assistant"
    system = "system"


class ConfirmationCheckType(str, enum.Enum):
    """函证AI检查类型"""
    address_verify = "address_verify"
    reply_ocr = "reply_ocr"
    amount_compare = "amount_compare"
    seal_check = "seal_check"


class ConfirmationRiskLevel(str, enum.Enum):
    """函证风险等级"""
    high = "high"
    medium = "medium"
    low = "low"
    pass_ = "pass"


# ---------------------------------------------------------------------------
# AIModelConfig 模型
# ---------------------------------------------------------------------------


class AIModelConfig(Base, SoftDeleteMixin):
    """AI模型配置"""

    __tablename__ = "ai_model_config"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_type: Mapped[AIModelType] = mapped_column(
        sa.Enum(AIModelType, name="ai_model_type_enum", create_type=False),
        nullable=False,
    )
    provider: Mapped[AIProvider] = mapped_column(
        sa.Enum(AIProvider, name="ai_provider_enum", create_type=False),
        nullable=False,
    )
    endpoint_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    context_window: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    performance_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "ix_ai_model_config_name_type",
            "model_name", "model_type",
            unique=True,
        ),
    )


# ---------------------------------------------------------------------------
# DocumentScan 模型
# ---------------------------------------------------------------------------


class DocumentScan(Base):
    """单据扫描件"""

    __tablename__ = "document_scan"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    company_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    year: Mapped[str | None] = mapped_column(String(4), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    file_size: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    document_type: Mapped[DocumentType] = mapped_column(
        sa.Enum(DocumentType, name="document_type_enum", create_type=False),
        nullable=False,
    )
    recognition_status: Mapped[RecognitionStatus] = mapped_column(
        sa.Enum(RecognitionStatus, name="recognition_status_enum", create_type=False),
        server_default=text("'pending'"),
        nullable=False,
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # 关系
    extracted_fields: Mapped[list["DocumentExtracted"]] = relationship(
        "DocumentExtracted", back_populates="document_scan", lazy="selectin"
    )
    match_results: Mapped[list["DocumentMatch"]] = relationship(
        "DocumentMatch", back_populates="document_scan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_document_scan_project_type", "project_id", "document_type"),
        Index("ix_document_scan_status", "recognition_status"),
    )


# ---------------------------------------------------------------------------
# DocumentExtracted 模型
# ---------------------------------------------------------------------------


class DocumentExtracted(Base):
    """单据结构化提取数据"""

    __tablename__ = "document_extracted"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_scan.id"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(3, 2), nullable=True
    )
    human_confirmed: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # 关系
    document_scan: Mapped["DocumentScan"] = relationship(
        "DocumentScan", back_populates="extracted_fields"
    )

    __table_args__ = (
        Index("ix_document_extracted_scan", "document_scan_id"),
        Index("ix_document_extracted_confidence", "confidence_score"),
    )


# ---------------------------------------------------------------------------
# DocumentMatch 模型
# ---------------------------------------------------------------------------


class DocumentMatch(Base):
    """单据与账面数据匹配"""

    __tablename__ = "document_match"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_scan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_scan.id"), nullable=False
    )
    matched_voucher_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    matched_account_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    matched_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    match_result: Mapped[MatchResult] = mapped_column(
        sa.Enum(MatchResult, name="match_result_enum", create_type=False),
        nullable=False,
    )
    difference_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    difference_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # 关系
    document_scan: Mapped["DocumentScan"] = relationship(
        "DocumentScan", back_populates="match_results"
    )

    __table_args__ = (
        Index("ix_document_match_scan", "document_scan_id"),
        Index("ix_document_match_result", "match_result"),
    )


# ---------------------------------------------------------------------------
# AIContent 模型
# ---------------------------------------------------------------------------


class AIContent(Base):
    """AI生成内容"""

    __tablename__ = "ai_content"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    workpaper_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    content_type: Mapped[AIContentType] = mapped_column(
        sa.Enum(AIContentType, name="ai_content_type_enum", create_type=False),
        nullable=False,
    )
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    data_sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    generation_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generation_time: Mapped[datetime | None] = mapped_column(nullable=True)
    confidence_level: Mapped[ConfidenceLevel | None] = mapped_column(
        sa.Enum(ConfidenceLevel, name="confidence_level_enum", create_type=False),
        nullable=True,
    )
    confirmation_status: Mapped[AIConfirmationStatus] = mapped_column(
        sa.Enum(
            AIConfirmationStatus,
            name="ai_confirmation_status_enum",
            create_type=False,
        ),
        server_default=text("'pending'"),
        nullable=False,
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    modification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "ix_ai_content_project_workpaper_type",
            "project_id", "workpaper_id", "content_type",
        ),
        Index("ix_ai_content_confirmation", "confirmation_status"),
    )


# ---------------------------------------------------------------------------
# Contract 模型
# ---------------------------------------------------------------------------


class Contract(Base):
    """合同"""

    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    company_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contract_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    party_a: Mapped[str | None] = mapped_column(String(200), nullable=True)
    party_b: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contract_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    contract_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    contract_type: Mapped[ContractType | None] = mapped_column(
        sa.Enum(ContractType, name="contract_type_enum", create_type=False),
        nullable=True,
    )
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    analysis_status: Mapped[ContractAnalysisStatus] = mapped_column(
        sa.Enum(
            ContractAnalysisStatus,
            name="contract_analysis_status_enum",
            create_type=False,
        ),
        server_default=text("'pending'"),
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # 关系
    extracted_clauses: Mapped[list["ContractExtracted"]] = relationship(
        "ContractExtracted", back_populates="contract", lazy="selectin"
    )
    workpaper_links: Mapped[list["ContractWPLink"]] = relationship(
        "ContractWPLink", back_populates="contract", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_contracts_project_type", "project_id", "contract_type"),
    )


# ---------------------------------------------------------------------------
# ContractExtracted 模型
# ---------------------------------------------------------------------------


class ContractExtracted(Base):
    """合同条款提取"""

    __tablename__ = "contract_extracted"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id"), nullable=False
    )
    clause_type: Mapped[ClauseType] = mapped_column(
        sa.Enum(ClauseType, name="clause_type_enum", create_type=False),
        nullable=False,
    )
    clause_content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(3, 2), nullable=True
    )
    human_confirmed: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # 关系
    contract: Mapped["Contract"] = relationship(
        "Contract", back_populates="extracted_clauses"
    )

    __table_args__ = (
        Index("ix_contract_extracted_contract_clause", "contract_id", "clause_type"),
    )


# ---------------------------------------------------------------------------
# ContractWPLink 模型
# ---------------------------------------------------------------------------


class ContractWPLink(Base):
    """合同与底稿关联"""

    __tablename__ = "contract_wp_link"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id"), nullable=False
    )
    workpaper_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    link_type: Mapped[ContractLinkType] = mapped_column(
        sa.Enum(ContractLinkType, name="contract_link_type_enum", create_type=False),
        nullable=False,
    )
    link_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # 关系
    contract: Mapped["Contract"] = relationship(
        "Contract", back_populates="workpaper_links"
    )

    __table_args__ = (
        Index("ix_contract_wp_link_contract_workpaper", "contract_id", "workpaper_id"),
    )


# ---------------------------------------------------------------------------
# EvidenceChain 模型
# ---------------------------------------------------------------------------


class EvidenceChain(Base):
    """证据链"""

    __tablename__ = "evidence_chain"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    chain_type: Mapped[EvidenceChainType] = mapped_column(
        sa.Enum(EvidenceChainType, name="evidence_chain_type_enum", create_type=False),
        nullable=False,
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    target_document_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    chain_step: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    match_status: Mapped[ChainMatchStatus] = mapped_column(
        sa.Enum(ChainMatchStatus, name="chain_match_status_enum", create_type=False),
        nullable=False,
    )
    mismatch_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[RiskLevel | None] = mapped_column(
        sa.Enum(RiskLevel, name="risk_level_enum", create_type=False),
        nullable=True,
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_evidence_chain_project_type", "project_id", "chain_type"),
        Index("ix_evidence_chain_risk", "risk_level"),
    )


# ---------------------------------------------------------------------------
# KnowledgeIndex 模型
# ---------------------------------------------------------------------------


class KnowledgeIndex(Base):
    """知识库索引"""

    __tablename__ = "knowledge_index"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    source_type: Mapped[KnowledgeSourceType] = mapped_column(
        sa.Enum(
            KnowledgeSourceType, name="knowledge_source_type_enum", create_type=False
        ),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_vector: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    chunk_index: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_knowledge_index_project_source", "project_id", "source_type"),
    )


# ---------------------------------------------------------------------------
# AIChatHistory 模型
# ---------------------------------------------------------------------------


class AIChatHistory(Base):
    """AI对话历史"""

    __tablename__ = "ai_chat_history"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    role: Mapped[ChatRole] = mapped_column(
        sa.Enum(ChatRole, name="chat_role_enum", create_type=False),
        nullable=False,
    )
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    referenced_sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "ix_ai_chat_project_conv",
            "project_id", "conversation_id", "created_at",
        ),
        Index("ix_ai_chat_user", "user_id"),
    )


# ---------------------------------------------------------------------------
# AI问答会话模型（扩展AIChatHistory，补充会话级信息）
# ---------------------------------------------------------------------------


class SessionType(str, enum.Enum):
    """会话类型"""
    general = "general"
    contract = "contract"
    workpaper = "workpaper"
    confirmation = "confirmation"


class AIChatSession(Base):
    """AI问答会话（会话维度聚合）"""

    __tablename__ = "ai_chat_session"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    session_type: Mapped[SessionType] = mapped_column(
        sa.Enum(SessionType, name="session_type_enum", create_type=False),
        nullable=False,
        default=SessionType.general,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    total_messages: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    total_tokens: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_ai_chat_session_project", "project_id"),
        Index("ix_ai_chat_session_user", "user_id"),
    )


class AIChatMessage(Base):
    """AI问答消息（详细消息记录）"""

    __tablename__ = "ai_chat_message"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_chat_session.id"), nullable=False
    )
    role: Mapped[ChatRole] = mapped_column(
        sa.Enum(ChatRole, name="chat_role_enum", create_type=False),
        nullable=False,
    )
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    referenced_sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_ai_chat_message_session", "session_id"),
    )


# ---------------------------------------------------------------------------
# AI知识库模型（文档索引）
# ---------------------------------------------------------------------------


class SourceType(str, enum.Enum):
    """文档来源类型（别名，与KnowledgeSourceType一致）"""
    workpaper = "workpaper"
    contract = "contract"
    confirmation = "confirmation"
    document = "document"
    report = "report"


class AIKnowledgeBase(Base):
    """AI知识库文档索引"""

    __tablename__ = "ai_knowledge_base"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    doc_uuid: Mapped[uuid.UUID] = mapped_column(nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        sa.Enum(SourceType, name="source_type_enum", create_type=False),
        nullable=False,
    )
    chunk_index: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_ai_knowledge_base_project", "project_id"),
        Index("ix_ai_knowledge_base_doc", "doc_uuid"),
        Index("ix_ai_knowledge_base_hash", "content_hash"),
    )


# ---------------------------------------------------------------------------
# AI合同分析报告模型
# ---------------------------------------------------------------------------


class AnalysisReportStatus(str, enum.Enum):
    """分析报告状态"""
    pending = "pending"
    analyzing = "analyzing"
    completed = "completed"
    failed = "failed"


class AIAnalysisReport(Base):
    """AI分析报告"""

    __tablename__ = "ai_analysis_report"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    document_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_findings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    risk_indicators: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(3, 2), nullable=True
    )
    status: Mapped[AnalysisReportStatus] = mapped_column(
        sa.Enum(AnalysisReportStatus, name="analysis_report_status_enum", create_type=False),
        nullable=False,
        default=AnalysisReportStatus.pending,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_ai_analysis_report_project", "project_id"),
        Index("ix_ai_analysis_report_status", "status"),
    )


class AIAnalysisItem(Base):
    """AI分析报告条目"""

    __tablename__ = "ai_analysis_item"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_analysis_report.id"), nullable=False
    )
    clause_type: Mapped[ClauseType | None] = mapped_column(
        sa.Enum(ClauseType, name="clause_type_enum", create_type=False),
        nullable=True,
    )
    clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    risk_flag: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    risk_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(3, 2), nullable=True
    )
    human_confirmed: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    human_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_ai_analysis_item_report", "report_id"),
    )


# ---------------------------------------------------------------------------
# AI函证审核模型
# ---------------------------------------------------------------------------


class AIConfirmationAudit(Base):
    """AI函证审核记录"""

    __tablename__ = "ai_confirmation_audit"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    confirmation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    original_content: Mapped[str] = mapped_column(Text, nullable=False)
    response_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_period: Mapped[str] = mapped_column(String(50), nullable=False)
    audit_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[AIConfirmationStatus] = mapped_column(
        sa.Enum(AIConfirmationStatus, name="ai_confirmation_status_enum", create_type=False),
        nullable=False,
        default=AIConfirmationStatus.pending,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_ai_confirmation_audit_project", "project_id"),
        Index("ix_ai_confirmation_audit_status", "status"),
    )


# ---------------------------------------------------------------------------
# ConfirmationAICheck 模型
# ---------------------------------------------------------------------------


class ConfirmationAICheck(Base):
    """函证AI检查"""

    __tablename__ = "confirmation_ai_check"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    confirmation_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("confirmation_lists.id"), nullable=False
    )
    check_type: Mapped[ConfirmationCheckType] = mapped_column(
        sa.Enum(
            ConfirmationCheckType,
            name="confirmation_check_type_enum",
            create_type=False,
        ),
        nullable=False,
    )
    check_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    risk_level: Mapped[ConfirmationRiskLevel | None] = mapped_column(
        sa.Enum(
            ConfirmationRiskLevel,
            name="confirmation_risk_level_enum",
            create_type=False,
        ),
        nullable=True,
    )
    human_confirmed: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "ix_confirmation_ai_check_list_type",
            "confirmation_list_id", "check_type",
        ),
    )



# ---------------------------------------------------------------------------
# AI底稿填充模型
# ---------------------------------------------------------------------------


class WorkpaperPhase(str, enum.Enum):
    """底稿阶段"""
    PLANNING = "planning"           # 计划阶段
    RISK_ASSESSMENT = "risk_assessment"  # 风险评估
    SUBSTANTIVE_PROCEDURES = "substantive_procedures"  # 实质性程序
    COMPLETION = "completion"       # 完成阶段


class WorkpaperTaskStatus(str, enum.Enum):
    """任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AIWorkpaperTask(Base):
    """AI底稿填充任务"""

    __tablename__ = "ai_workpaper_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workpaper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workpapers.id"), nullable=False
    )
    task_type: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[WorkpaperTaskStatus] = mapped_column(
        sa.Enum(
            WorkpaperTaskStatus,
            name="workpaper_task_status_enum",
            create_type=False,
        ),
        nullable=False,
        default=WorkpaperTaskStatus.PENDING,
    )
    request_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_ai_workpaper_task_workpaper", "workpaper_id"),
        Index("ix_ai_workpaper_task_status", "status"),
    )


class AIWorkpaperFill(Base):
    """AI底稿填充记录"""

    __tablename__ = "ai_workpaper_fills"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_workpaper_tasks.id"), nullable=True
    )
    workpaper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workpapers.id"), nullable=False
    )
    field_path: Mapped[str] = mapped_column(nullable=False)
    field_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    fill_type: Mapped[str] = mapped_column(nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(3, 2), nullable=True
    )
    model_name: Mapped[str | None] = mapped_column(nullable=True)
    human_reviewed: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    human_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_ai_generated: Mapped[bool] = mapped_column(
        server_default=text("true"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_ai_workpaper_fill_workpaper", "workpaper_id"),
        Index("ix_ai_workpaper_fill_task", "task_id"),
    )


# ---------------------------------------------------------------------------
# AI证据链模型
# ---------------------------------------------------------------------------


class AIEvidenceChain(Base):
    """AI证据链"""

    __tablename__ = "ai_evidence_chains"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    chain_type: Mapped[str] = mapped_column(nullable=False)
    source_type: Mapped[str] = mapped_column(nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    title: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(3, 2), nullable=True
    )
    risk_level: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        server_default="pending", nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_ai_evidence_chain_project", "project_id"),
    )


class AIEvidenceItem(Base):
    """AI证据项"""

    __tablename__ = "ai_evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chain_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_evidence_chains.id"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    document_name: Mapped[str | None] = mapped_column(nullable=True)
    field_path: Mapped[str | None] = mapped_column(nullable=True)
    field_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_number: Mapped[int | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(3, 2), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_ai_evidence_item_chain", "chain_id"),
    )
