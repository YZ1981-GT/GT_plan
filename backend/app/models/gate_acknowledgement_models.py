"""S2 ADR-CCN-06: 门禁逐项确认留痕 ORM 模型

对齐迁移 V217__consistency_gate_acknowledgements.sql。
三层一致：DDL → ORM → service。
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class GateAcknowledgement(Base):
    """门禁逐项确认留痕表

    enforce 模式下，签字人逐项确认阻断项并留痕。
    result_fingerprint = sha256(check_name + branch_id + status + sorted key_numbers)，
    数据变了指纹就变、确认自动失效。

    部分唯一索引 (project_id, year, check_name) WHERE revoked_at IS NULL
    由迁移管理，ORM 侧不声明。
    """
    __tablename__ = "consistency_gate_acknowledgements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    check_name = Column(String(128), nullable=False)
    branch_id = Column(String(64), nullable=False, server_default="")
    status = Column(String(32), nullable=False)
    result_fingerprint = Column(String(128), nullable=False)
    reason = Column(Text, nullable=False)
    acknowledged_by = Column(UUID(as_uuid=True), nullable=False)
    acknowledged_role = Column(String(64), nullable=False, server_default="")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(UUID(as_uuid=True), nullable=True)
