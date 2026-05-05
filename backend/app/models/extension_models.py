"""Phase 8 扩展表 ORM 模型

对应 Alembic 迁移脚本 014_extension_tables.py
包含：AccountingStandard、SignatureRecord、WpTemplateCustom、RegulatoryFiling、AIPlugin
"""

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AccountingStandard(Base):
    """会计准则"""

    __tablename__ = "accounting_standards"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    standard_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    standard_name: Mapped[str] = mapped_column(String(100), nullable=False)
    standard_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_accounting_standards_code", "standard_code"),
        Index("idx_accounting_standards_active", "is_active"),
    )


class SignatureRecord(Base):
    """签名记录"""

    __tablename__ = "signature_records"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False)  # working_paper/adjustment/audit_report
    object_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    signer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    signature_level: Mapped[str] = mapped_column(String(20), nullable=False)  # level1/level2/level3
    # Round 1: 三级/多级签字顺序与前置依赖（R5 扩至 order=4/5 EQCR + 归档签字）
    required_order: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    required_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    prerequisite_signature_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    signature_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    signature_timestamp: Mapped[datetime | None] = mapped_column(nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_signature_records_object", "object_type", "object_id"),
        Index("idx_signature_records_signer", "signer_id"),
        Index("idx_signature_records_order", "object_type", "object_id", "required_order"),
    )


class WpTemplateCustom(Base):
    """自定义底稿模板"""

    __tablename__ = "wp_template_custom"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    template_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # industry/client/personal
    template_file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    is_published: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_wp_template_custom_user", "user_id"),
        Index("idx_wp_template_custom_category", "category"),
        Index("idx_wp_template_custom_published", "is_published"),
    )


class RegulatoryFiling(Base):
    """监管备案"""

    __tablename__ = "regulatory_filing"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    filing_type: Mapped[str] = mapped_column(String(50), nullable=False)  # cicpa_report/archival_standard
    filing_status: Mapped[str] = mapped_column(String(50), nullable=False)  # submitted/pending/approved/rejected
    submission_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_regulatory_filing_project", "project_id"),
        Index("idx_regulatory_filing_type", "filing_type"),
        Index("idx_regulatory_filing_status", "filing_status"),
    )


class AIPlugin(Base):
    """AI插件"""

    __tablename__ = "ai_plugins"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plugin_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plugin_name: Mapped[str] = mapped_column(String(200), nullable=False)
    plugin_version: Mapped[str] = mapped_column(String(20), nullable=False)
    plugin_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_ai_plugins_id", "plugin_id"),
        Index("idx_ai_plugins_enabled", "is_enabled"),
    )


# ---------------------------------------------------------------------------
# 会计准则种子数据
# ---------------------------------------------------------------------------

ACCOUNTING_STANDARD_SEEDS: list[dict] = [
    {"standard_code": "CAS", "standard_name": "企业会计准则", "standard_description": "中国企业会计准则体系"},
    {"standard_code": "SME", "standard_name": "小企业会计准则", "standard_description": "适用于小企业的简化会计准则"},
    {"standard_code": "GOV", "standard_name": "政府会计准则", "standard_description": "政府及事业单位会计准则"},
    {"standard_code": "FIN", "standard_name": "金融企业会计准则", "standard_description": "金融行业专用会计准则"},
    {"standard_code": "IFRS", "standard_name": "国际财务报告准则", "standard_description": "International Financial Reporting Standards"},
]
