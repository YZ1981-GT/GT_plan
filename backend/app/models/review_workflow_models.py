"""复核流程与独立性签署模型"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base


class ReviewChecklistRecord(Base):
    """复核检查表记录（A21~A25 各级勾选+意见）"""

    __tablename__ = "review_checklist_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    template_code = Column(String(10), nullable=False)
    reviewer_id = Column(UUID(as_uuid=True), nullable=False)
    items = Column(JSONB, nullable=False, default=list)
    opinion = Column(Text)
    status = Column(String(20), nullable=False, default="draft")
    submitted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "year", "template_code", "reviewer_id", name="uq_review_checklist_record"),
        Index("idx_review_checklist_records_project_year", "project_id", "year"),
    )


class IndependenceSigningTask(Base):
    """A17-7 独立性声明书电子签署任务"""

    __tablename__ = "independence_signing_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    template_code = Column(String(10), nullable=False, default="A17-7")
    status = Column(String(20), nullable=False, default="pending")
    signed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", "template_code", name="uq_signing_task"),
        Index("idx_independence_signing_project", "project_id"),
    )
