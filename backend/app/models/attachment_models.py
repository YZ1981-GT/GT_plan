"""附件管理 ORM 模型

对应 Alembic 迁移脚本 013_attachments.py
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Attachment(Base):
    """附件"""

    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    attachment_type: Mapped[str] = mapped_column(String(50), server_default=text("'general'"), nullable=False)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    storage_type: Mapped[str] = mapped_column(String(20), server_default=text("'paperless'"), nullable=False)
    paperless_document_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    ocr_status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"), nullable=False)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_fields_cache: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_attachments_project", "project_id"),
        Index("idx_attachments_ocr_status", "project_id", "ocr_status"),
        Index("idx_attachments_paperless", "paperless_document_id"),
        Index("idx_attachments_type_ref", "attachment_type", "reference_type", "reference_id"),
        Index("idx_attachments_storage_type", "storage_type"),
    )


class AttachmentWorkingPaper(Base):
    """附件-底稿关联"""

    __tablename__ = "attachment_working_paper"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attachment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attachments.id"), nullable=False)
    wp_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("working_paper.id"), nullable=False)
    association_type: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_attachment_wp_attachment", "attachment_id"),
        Index("idx_attachment_wp_wp", "wp_id"),
    )
