"""自定义底稿模板的不可变 publication 登记（V275）。

Spec: custom-workpaper-template-ingestion-and-sync-closure, Task 16 / 20
关联：`app.services.custom_template_ingestion.publication_ops.PublicationRegistry`

设计要点（对应 AC「新 version 不覆盖旧 artifact」）：
- 一行一个 publication，`publication_id` 一经写入即不可变（无 UPDATE 路径写入
  artifact digest，只在 lifecycle 上推进 state）。
- `artifact_digest` 与 `authority_ref` 落库，保证 publication 能自证它冻结的是
  哪一份 artifact —— 内存版 `PublicationRegistry.artifacts` 曾因重启丢失。
- 项目 pin 单独一表，一个项目同一时刻只 pin 一个 publication（唯一约束），
  与内存版 `pins: dict[project_id, publication_id]` 语义一致。
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CustomTemplatePublication(Base):
    """ACTIVE / PENDING_VISIBILITY / WITHDRAWN / SECURITY_REVOKED 的 publication 行。"""

    __tablename__ = "custom_template_publications"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    #: 业务侧 publication 标识（PublicationRegistry 的 key，形如 pub-<uuid>）
    publication_key: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    candidate_id: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    candidate_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    #: finalized TemplateAuthorityIdentity 引用，不复制字段
    authority_ref: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    #: 冻结的 artifact 内容摘要 —— 不可变
    artifact_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    state: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    #: finalize handoff 的完整快照（含 handoffDigest），供 instantiate 复核
    handoff: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id", "publication_key", name="uq_custom_publication_org_key"
        ),
        sa.CheckConstraint(
            "state IN ('PENDING_VISIBILITY', 'ACTIVE', 'WITHDRAWN', 'SECURITY_REVOKED', 'FAILED')",
            name="ck_custom_publication_state",
        ),
        sa.CheckConstraint(
            "candidate_digest ~ '^[0-9a-f]{64}$'",
            name="ck_custom_publication_candidate_digest",
        ).ddl_if(dialect="postgresql"),
        sa.CheckConstraint(
            "artifact_digest ~ '^[0-9a-f]{64}$'",
            name="ck_custom_publication_artifact_digest",
        ).ddl_if(dialect="postgresql"),
        sa.CheckConstraint(
            "jsonb_typeof(handoff) = 'object'",
            name="ck_custom_publication_handoff_object",
        ).ddl_if(dialect="postgresql"),
        sa.Index("ix_custom_publication_org_state", "organization_id", "state"),
    )


class CustomTemplatePublicationPin(Base):
    """项目 → publication 的 pin；同一项目同一时刻只有一个生效 pin。"""

    __tablename__ = "custom_template_publication_pins"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    publication_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("custom_template_publications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    pinned_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("project_id", name="uq_custom_publication_pin_project"),
    )
