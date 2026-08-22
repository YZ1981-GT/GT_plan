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

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover
    Vector = None  # type: ignore[assignment,misc]

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
    knowledge_doc = "knowledge_doc"
    address_coordinate = "address_coordinate"  # Task 22 / V148


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
    embedding_vec = mapped_column(Vector(1024), nullable=True)
    chunk_index: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    is_stale: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    doc_version: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
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


# ---------------------------------------------------------------------------
# AI Chat 持久化取值域（dsh-agent-panel-integration Task 3）
#
# 🔴 这些是**列取值域的单一真源**。V147 迁移里的 CHECK 约束是它们的投影，
#    守卫 test_task3_chat_persistence 对 `pg_get_constraintdef` 与本组枚举做
#    **双向**比对（DB ⊆ Python 且 Python ⊆ DB），任一侧漂移即打红。
#
# 为什么用 VARCHAR + CHECK 而不是 PG enum：MigrationRunner 把整个迁移文件放在
# 一个事务里跑，PG 不允许在同一事务内 `ALTER TYPE ... ADD VALUE` 后立即使用新值，
# 于是"加枚举值 + 写该值"必然失败。VARCHAR + CHECK 从根上避开该约束。
# ---------------------------------------------------------------------------


class ChatRunStatus(str, enum.Enum):
    """Chat Run 状态机（design "4. Typed Chat Run" 的状态图）。

    queued → running → done | error | cancelled
    queued → cancelled
    running（lease 过期）→ interrupted → queued | error
    """

    queued = "queued"
    running = "running"
    done = "done"
    error = "error"
    cancelled = "cancelled"
    interrupted = "interrupted"


#: 终态集合：进入其一后不得再追加业务事件或 completed assistant 消息（Req 4.5）。
CHAT_RUN_TERMINAL_STATUSES: frozenset[ChatRunStatus] = frozenset(
    {ChatRunStatus.done, ChatRunStatus.error, ChatRunStatus.cancelled}
)


class ChatEngineName(str, enum.Enum):
    """engine 取值；只由服务端 config/feature flag 选择，请求字段不可覆盖（Req 10.1）。"""

    native = "native"
    dsh = "dsh"


class ChatMessageStatus(str, enum.Enum):
    """消息状态；只有 ``completed`` 的 assistant 消息可被复制/转存/采纳（Req 8.1）。"""

    draft = "draft"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ChatToolCallStatus(str, enum.Enum):
    """工具调用状态（每次调用 started + finished/failed 各一条哈希链记录，Req 11.10）。"""

    started = "started"
    finished = "finished"
    failed = "failed"
    cancelled = "cancelled"


class AttachmentOcrStatus(str, enum.Enum):
    """附件 OCR 状态机（Req 7.5/7.6，Property 19 的五态互斥落在此处）。

    ``empty`` 是**成功但无文字**（不得当失败或静默丢弃）；``unavailable`` /
    ``failed`` / ``timeout`` 三者互斥且各有独立 error code。
    """

    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    empty = "empty"
    failed = "failed"
    unavailable = "unavailable"
    timeout = "timeout"
    cancelled = "cancelled"


class ActionReceiptType(str, enum.Enum):
    """幂等收据覆盖的动作（与 AiChatAction 的写类动作对应）。"""

    note_create = "note-create"
    adopt = "adopt"


class ActionReceiptStatus(str, enum.Enum):
    """幂等收据状态；失败收据可被安全重试（Req 8.9）。"""

    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"


class AIChatSession(Base):
    """AI问答会话（会话维度聚合）

    Task 3 扩展：服务端生成的 ``session_key``（唯一定位）+ host type/id + audit year
    + review mode + last_message_at。唯一约束 ``uq_ai_chat_session_user_key``
    由 V147 拥有（部分唯一索引，带 ``WHERE user_id IS NOT NULL AND session_key IS NOT NULL``
    谓词，ORM 不重复声明以免 SQLite create_all 与 PG 方言差异）。
    """

    __tablename__ = "ai_chat_session"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 无项目的受限全局知识模式为 NULL；V147 的 ck_ai_chat_session_project_required
    # 保证只有 host_type='global_knowledge' 才允许 NULL（禁止空 UUID 伪装项目）。
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
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
    #: 服务端规范化定位 hash；唯一真源 = ai_chat.persistence.build_session_key。
    session_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: 取值域 = app.services.ai_chat.contracts.HostType（V147 CHECK 锁死）。
    host_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: 全局知识模式使用 GLOBAL_KNOWLEDGE_HOST_ID sentinel，不用空字符串。
    host_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    engine_preference: Mapped[str | None] = mapped_column(String(32), nullable=True)
    review_mode: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=text("false"), nullable=False, default=False
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime, nullable=True
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
    """AI问答消息（详细消息记录）

    Task 3 扩展：run 关联、状态、content hash、context manifest 与单调 ``seq``。
    🔴 citations 复用既有 ``referenced_sources``，**不新增 citations 列**；
       model/token/latency 复用 ``model_used`` / ``tokens_used`` / ``latency_ms``。
    """

    __tablename__ = "ai_chat_message"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_chat_session.id"), nullable=False
    )
    #: 单调插入序。PG 侧由 V147 的 BIGSERIAL 默认值填充（真源在 DB）。
    #: 🔴 必须声明 `server_default=FetchedValue()`：否则 ORM insert 会把未赋值的列
    #:    当 NULL 一起写进 INSERT 列表，PG 的 BIGSERIAL 默认值永远不生效
    #:    ⇒ NotNullViolationError（实测踩过）。
    #: 🔴 且必须 `nullable=True`：SQLite `create_all` 不支持 Identity/SERIAL，
    #:    声明 NOT NULL 会让全部 sqlite 集成测试插入 ai_chat_message 时炸 NOT NULL。
    seq: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.FetchedValue(), nullable=True
    )
    role: Mapped[ChatRole] = mapped_column(
        sa.Enum(ChatRole, name="chat_role_enum", create_type=False),
        nullable=False,
    )
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: citations 的唯一存放位置（勿新增 citations 列）。
    referenced_sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_chat_runs.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'completed'"),
        nullable=False,
        default=ChatMessageStatus.completed.value,
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_manifest: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_ai_chat_message_session", "session_id"),
    )


class AIChatRun(Base):
    """Chat Run —— 一次模型/Agent 执行的持久化摘要。

    Requirements 4.6/4.11 · Property 6：并发幂等由数据库唯一约束
    ``uq_ai_chat_runs_idempotency (actor_id, session_id, idempotency_key)`` 保证，
    **不允许**"先查后建"。状态更新由 Task 4 的 compare-and-set 使用本表的
    ``status`` 列完成（terminal event 恰好一个）。

    Req 4.12：数据库只保存 run/message/tool **摘要**，逐 token 的 delta 走 Redis。
    """

    __tablename__ = "ai_chat_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_chat_session.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    host_type: Mapped[str] = mapped_column(String(32), nullable=False)
    host_id: Mapped[str] = mapped_column(String(128), nullable=False)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'queued'"),
        nullable=False,
        default=ChatRunStatus.queued.value,
    )
    capability_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False, default=0
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class AIChatToolCall(Base):
    """工具调用摘要（Req 11.10：每次调用产生 started + finished/failed 记录）。

    🔴 ``arg_hash`` 是入参哈希；**不得**保存 scoped token 或完整工具入参正文
    （Req 11.9/12.7）。``result_bytes`` 只记字节数，不记返回正文。
    """

    __tablename__ = "ai_chat_tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_chat_runs.id", ondelete="CASCADE"), nullable=False
    )
    parent_call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_chat_tool_calls.id", ondelete="SET NULL"), nullable=True
    )
    tool_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    arg_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_bytes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'started'"),
        nullable=False,
        default=ChatToolCallStatus.started.value,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class AIChatAttachment(Base):
    """会话附件 metadata（Req 7.3）。

    独立 ``storage/ai_chat/`` 空间，**不写业务证据附件表**（Req 7.8）。上传只返回
    attachment ID 与状态，不返回服务器物理路径；聊天请求只提交 attachment ID。
    ``ocr_text_protected`` 对应 design 的 ``ocr_text_encrypted_or_protected``。
    """

    __tablename__ = "ai_chat_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_chat_session.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_chat_runs.id", ondelete="SET NULL"), nullable=True
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    ocr_status: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'pending'"),
        nullable=False,
        default=AttachmentOcrStatus.pending.value,
    )
    ocr_text_protected: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    legal_hold: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=text("false"), nullable=False, default=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class AIChatActionReceipt(Base):
    """note save / adopt 的通用幂等收据（Req 8.2/8.3 · Property 21）。

    唯一约束 ``uq_ai_chat_action_receipts_idempotency
    (action_type, actor_id, session_id, idempotency_key)``：并发重复请求只有一个
    插入成功，其余读回同一收据 ⇒ 不创建重复文件夹/文档。
    ``source_message_hash`` / ``result_resource_id`` 只存哈希与引用 ID，
    不重复存储完整敏感正文（Req 8.9）。
    """

    __tablename__ = "ai_chat_action_receipts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_chat_session.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_message_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_resource_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'pending'"),
        nullable=False,
        default=ActionReceiptStatus.pending.value,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
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
        ForeignKey("working_paper.id"), nullable=False
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
        ForeignKey("working_paper.id"), nullable=False
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
