"""现金流量表核查结果模型"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base


class CfVerificationResult(Base):
    """CF 核查结果缓存 + 用户差异说明"""

    __tablename__ = "cf_verification_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    check_type = Column(String(50), nullable=False)  # cash_equivalents/reconciliation/main_table/supplementary
    item_code = Column(String(20))  # CFS-002 等
    reported_amount = Column(Numeric(18, 2))
    calculated_amount = Column(Numeric(18, 2))
    difference = Column(Numeric(18, 2))
    pass_ = Column("pass", Boolean, default=False)
    explanation = Column(Text)
    result_data = Column(JSONB)
    calculated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "year", "check_type", "item_code", name="uq_cf_verification_project_year_type_item"),
        Index("idx_cf_verification_results_project_year", "project_id", "year"),
    )
