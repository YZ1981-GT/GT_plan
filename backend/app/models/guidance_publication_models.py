"""Guidance 发布生命周期 ORM 模型（V156）

四张表：
    guidance_publication            发布主体（draft → reviewed → published → withdrawn）
    guidance_publication_event      生命周期事件（actor/reviewer/diff/digests/reason）
    project_guidance_supplement     项目级补充（独立版本，不写回 canonical）
    guidance_exemption_record       有效豁免（scope/owner/approver/expires_at）

🔴 铁律（由服务层 enforcement，不由 ORM/表结构保证）：
    * published 后 content_json 冻结 —— `guidance_publication_service._assert_mutable`
    * author ≠ reviewer —— `guidance_publication_service._assert_can` 复验 capability
    * supplement 不得补齐 canonical 缺失段后推 complete
      —— `guidance_completion_guard._canonical_section_presence`
    * supplement 的 project_evidence 必须非空
    * exemption 的 approver ≠ owner，且必须有 expires_at

digests 铁律（spec Req 6.5 / mutation C01）：
    * content_digest = sha256(content_json)
    * source_digest  = sha256(源材料)
    两者必须解耦 —— 同源会让 C01 变异（constants 化）永远抓不到。
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


# ---------------------------------------------------------------------------
# 状态枚举（与服务层常量保持一致；DB CHECK 约束在迁移里定义）
# ---------------------------------------------------------------------------

PUBLICATION_DRAFT = "draft"
PUBLICATION_REVIEWED = "reviewed"
PUBLICATION_PUBLISHED = "published"
PUBLICATION_WITHDRAWN = "withdrawn"

PUBLICATION_STATUSES = frozenset(
    {PUBLICATION_DRAFT, PUBLICATION_REVIEWED, PUBLICATION_PUBLISHED, PUBLICATION_WITHDRAWN}
)

REVIEW_PENDING = "pending"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"

WHOLE_WORKBOOK_SHEET_KEY = "*"

EVENT_DRAFTED = "drafted"
EVENT_SUBMITTED_FOR_REVIEW = "submitted_for_review"
EVENT_REVIEW_APPROVED = "review_approved"
EVENT_REVIEW_REJECTED = "review_rejected"
EVENT_PUBLISHED = "published"
EVENT_WITHDRAWN = "withdrawn"
EVENT_RESTORED = "restored"
EVENT_SUPERSEDED = "superseded"


class GuidancePublication(Base):
    """guidance 发布主体。

    draft → reviewed → published；published 后不可修改（immutable gate 在服务层）。
    一个 (lineage_id, version, wp_code, sheet_key) 下至多一行 active。
    """

    __tablename__ = "guidance_publication"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lineage_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    wp_code: Mapped[str] = mapped_column(String(32), nullable=False)
    sheet_key: Mapped[str] = mapped_column(String(128), nullable=False, default=WHOLE_WORKBOOK_SHEET_KEY)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PUBLICATION_DRAFT)

    content_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source_refs_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default=REVIEW_PENDING)
    author_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    withdrawn_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    withdrawn_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("guidance_publication.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )

    events: Mapped[list[GuidancePublicationEvent]] = relationship(
        back_populates="publication", order_by="GuidancePublicationEvent.created_at", lazy="selectin"
    )

    # -- 业务判据 --

    @property
    def is_active(self) -> bool:
        """未 supersede 且未 withdraw。"""
        return self.superseded_by is None and self.withdrawn_at is None

    @property
    def is_immutable(self) -> bool:
        """published 后不可再改内容。"""
        return self.status == PUBLICATION_PUBLISHED

    def is_author_equal_to_reviewer(self) -> bool:
        return self.author_user_id == self.reviewer_user_id


class GuidancePublicationEvent(Base):
    """发布生命周期事件。

    每次状态迁移写一行；actor/reviewer/diff/digests/reason 全留痕，供审计与
    outbox 消费。before_digest 与 after_digest 都留痕，便于回放核对。
    """

    __tablename__ = "guidance_publication_event"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    publication_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("guidance_publication.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    actor_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    diff_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    before_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)

    audit_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    outbox_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())

    publication: Mapped[GuidancePublication] = relationship(back_populates="events")


class ProjectGuidanceSupplement(Base):
    """项目级 guidance 补充。

    独立版本号（supplement_version 与 base publication.version 不同源）；
    base_publication_id 仅作锚定基准，内容不写回 canonical。
    project_evidence_json 必须非空 —— 服务端 `_assert_runtime_subject_bound`。
    """

    __tablename__ = "project_guidance_supplement"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    entry_id: Mapped[str] = mapped_column(String(512), nullable=False)
    wp_code: Mapped[str] = mapped_column(String(32), nullable=False)
    sheet_key: Mapped[str] = mapped_column(String(128), nullable=False)

    supplement_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PUBLICATION_DRAFT)

    content_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)

    base_publication_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("guidance_publication.id", ondelete="SET NULL"),
        nullable=True,
    )
    base_content_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)

    project_evidence_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)

    author_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )

    @property
    def is_published(self) -> bool:
        return self.status == PUBLICATION_PUBLISHED

    @property
    def has_evidence(self) -> bool:
        return bool(self.project_evidence_json)


class GuidanceExemptionRecord(Base):
    """guidance 有效豁免记录。

    scope_type 决定粒度（project > entry > wp > sheet）；entry_ids_json 在同 scope
    下精确定位条目。approver ≠ owner；expires_at 必须非空。
    """

    __tablename__ = "guidance_exemption_record"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    entry_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    wp_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sheet_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    entry_ids_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    reason: Mapped[str] = mapped_column(String(256), nullable=False)

    owner_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    approver_user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    source_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())

    @property
    def is_valid(self) -> bool:
        """未撤销且未过期。"""
        if self.revoked_at is not None:
            return False
        now = datetime.now(tz=self.expires_at.tzinfo)
        return self.expires_at > now

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= datetime.now(tz=self.expires_at.tzinfo)
