"""附件溯源关联 ORM 模型 — wp-traceability-panel Task 2.2

将附件关联到具体位置（wp_cell / report_row / note_section），
使附件进入溯源网络。
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AttachmentLineage(Base):
    """附件溯源关联"""

    __tablename__ = "attachment_lineage"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    attachment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wp_attachments.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # wp_cell / report_row / note_section
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    target_ref: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )  # 精确位置引用，如 "D2-3!B5"
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_attachment_lineage_attachment_id", "attachment_id"),
        Index("idx_attachment_lineage_target", "target_type", "target_ref"),
        Index("idx_attachment_lineage_target_id", "target_id"),
    )
