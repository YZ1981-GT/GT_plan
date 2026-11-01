"""跨领域不可变字节与显式桥接记录。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AssetBlob(Base):
    __tablename__ = "asset_blobs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    detected_media_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_type: Mapped[str] = mapped_column(String(24), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    ingress_policy_version: Mapped[str] = mapped_column(String(32), server_default=text("'apc-v1'"), nullable=False)
    security_status: Mapped[str] = mapped_column(String(20), server_default=text("'accepted'"), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("storage_type", "storage_key", name="uq_asset_blobs_storage"),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_asset_blobs_hash",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("byte_size >= 0", name="ck_asset_blobs_size"),
        CheckConstraint("security_status IN ('accepted','quarantined','rejected')", name="ck_asset_blobs_security"),
        CheckConstraint(
            "(actor_type = 'user' AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL) OR "
            "(actor_type = 'service' AND actor_user_id IS NULL AND actor_service_identity_id IS NOT NULL)",
            name="ck_asset_blobs_actor",
        ),
        Index("ix_asset_blobs_hash_size", "content_hash", "byte_size"),
    )


class KnowledgeEvidencePromotion(Base):
    __tablename__ = "knowledge_evidence_promotions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="RESTRICT"), nullable=False)
    source_document_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    source_blob_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("asset_blobs.id", ondelete="RESTRICT"), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_attachment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attachments.id", ondelete="RESTRICT"), nullable=False)
    target_attachment_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attachment_versions.id", ondelete="RESTRICT"), nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    audit_year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "actor_user_id", "idempotency_key", name="uq_kep_idempotency"),
        Index("ix_kep_source", "source_document_id", "source_document_version"),
        Index("ix_kep_target", "target_attachment_id"),
    )


class AiChatRunResource(Base):
    __tablename__ = "ai_chat_run_resources"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_chat_runs.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_chat_session.id", ondelete="CASCADE"), nullable=False)
    resource_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    attachment_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attachment_versions.id", ondelete="RESTRICT"), nullable=True,
    )
    blob_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("asset_blobs.id", ondelete="RESTRICT"), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "resource_kind", "resource_id", name="uq_ai_run_resource"),
        CheckConstraint("resource_kind IN ('chat_upload','project_attachment')", name="ck_ai_run_resource_kind"),
        CheckConstraint(
            "resource_kind <> 'project_attachment' OR "
            "(attachment_version_id IS NOT NULL AND blob_id IS NOT NULL AND "
            "length(content_hash) = 64)",
            name="ck_ai_run_project_attachment_pin",
        ),
        Index("ix_ai_run_resources_session", "session_id", "run_id"),
    )
