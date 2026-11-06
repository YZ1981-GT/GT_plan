"""自定义底稿工作簿的不可变单位 authority（V265，platform-global-display-settings-closure R9）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CustomWorkbookUnitAuthority(Base):
    __tablename__ = "custom_workbook_unit_authorities"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    working_paper_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("working_paper.id", ondelete="RESTRICT"), nullable=False
    )
    workbook_sha256: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    manifest: Mapped[dict] = mapped_column(sa.JSON().with_variant(JSONB, "postgresql"), nullable=False)
    manifest_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("working_paper_id", "workbook_sha256", name="uq_custom_wp_unit_authority_wp_hash"),
        sa.CheckConstraint(
            "workbook_sha256 ~ '^[0-9a-f]{64}$'", name="ck_custom_wp_unit_authority_workbook_digest"
        ).ddl_if(dialect="postgresql"),
        sa.CheckConstraint(
            "manifest_digest ~ '^[0-9a-f]{64}$'", name="ck_custom_wp_unit_authority_manifest_digest"
        ).ddl_if(dialect="postgresql"),
        sa.CheckConstraint(
            "jsonb_typeof(manifest) = 'object'", name="ck_custom_wp_unit_authority_manifest_object"
        ).ddl_if(dialect="postgresql"),
    )
