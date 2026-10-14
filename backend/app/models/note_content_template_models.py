"""附注正文内容模板、不可变版本和批量应用审计 ORM。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NoteContentTemplate(Base):
    """个人或集团可见的附注内容模板目录。"""

    __tablename__ = "note_content_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    owner_group_project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("note_content_template_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_deleted: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "owner_scope IN ('personal', 'group')", name="ck_nct_owner_scope"
        ),
        CheckConstraint(
            "(owner_scope = 'personal' AND owner_user_id IS NOT NULL "
            "AND owner_group_project_id IS NULL) OR "
            "(owner_scope = 'group' AND owner_user_id IS NULL "
            "AND owner_group_project_id IS NOT NULL)",
            name="ck_nct_owner_shape",
        ),
        Index(
            "ux_nct_personal_active_name",
            "owner_user_id",
            func.lower(name),
            unique=True,
            postgresql_where=text("is_deleted = false AND owner_scope = 'personal'"),
        ),
        Index(
            "ux_nct_group_active_name",
            "owner_group_project_id",
            func.lower(name),
            unique=True,
            postgresql_where=text("is_deleted = false AND owner_scope = 'group'"),
        ),
        Index(
            "idx_nct_group_visible",
            "owner_group_project_id",
            "updated_at",
            postgresql_where=text("is_deleted = false"),
        ),
    )


class NoteContentTemplateVersion(Base):
    """模板的不可变正文快照。"""

    __tablename__ = "note_content_template_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("note_content_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    source_project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    source_year: Mapped[int] = mapped_column(Integer, nullable=False)
    source_project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_type: Mapped[str] = mapped_column(String(20), nullable=False)
    report_scope: Mapped[str] = mapped_column(String(20), nullable=False)
    sections_data: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )

    quality_summary: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint("version_no > 0", name="ck_nctv_version_positive"),
        CheckConstraint("schema_version > 0", name="ck_nctv_schema_positive"),
        CheckConstraint("length(content_hash) = 64", name="ck_nctv_hash_length"),
        CheckConstraint("byte_size >= 0", name="ck_nctv_byte_size_nonnegative"),
        Index("ux_nctv_template_version", "template_id", "version_no", unique=True),
        Index("ux_nctv_template_hash", "template_id", "content_hash", unique=True),
        Index("idx_nctv_source", "source_project_id", "source_year"),
    )


class NoteTextBatchApplication(Base):
    """一次成功的附注正文原子批量应用审计。"""

    __tablename__ = "note_text_batch_applications"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    template_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("note_content_template_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    target_project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    target_year: Mapped[int] = mapped_column(Integer, nullable=False)
    mutation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mode_summary: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )

    detail: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="succeeded", server_default=text("'succeeded'")
    )
    applied_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    applied_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('upload', 'knowledge', 'content_template')",
            name="ck_ntba_source_kind",
        ),
        CheckConstraint(
            "(source_kind = 'content_template' AND template_version_id IS NOT NULL) OR "
            "(source_kind <> 'content_template' AND template_version_id IS NULL)",
            name="ck_ntba_source_template",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64", name="ck_ntba_request_hash"
        ),
        CheckConstraint("length(preview_digest) = 64", name="ck_ntba_preview_hash"),
        CheckConstraint("applied_count >= 0", name="ck_ntba_applied_count"),
        CheckConstraint("status = 'succeeded'", name="ck_ntba_status"),
        Index(
            "ux_ntba_project_mutation",
            "target_project_id",
            "mutation_id",
            unique=True,
        ),
        Index("idx_ntba_target_year", "target_project_id", "target_year", "applied_at"),
        Index(
            "idx_ntba_template_version",
            "template_version_id",
            postgresql_where=text("template_version_id IS NOT NULL"),
        ),
    )
