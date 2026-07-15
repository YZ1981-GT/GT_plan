"""Evidence Governance ORM 模型 — Task 2.2 (Wave 1)。

Spec: attachment-ocr-ai-evidence-governance-hardening
迁移: V106__evidence_governance_attachment_versions.sql
Requirements: R1, R2, R12, R13
Design: §Data Models(actor XOR), §4.0(UploadAttempt/隔离区), §4.2(Attachment 聚合), §4.3(AttachmentVersion)

本模块与 V106 迁移物理形状严格对齐（列名/类型/可空性/默认值）。actor XOR、OCR enum、
legacy 解析等语义契约的单一真源是 ``app.services.evidence_governance.contracts``；
这里只做 ORM 映射，不重复定义谓词。

- ``service_identities``          → :class:`ServiceIdentity`
- ``evidence_upload_attempts``    → :class:`UploadAttempt`
- ``evidence_quarantine_handles`` → :class:`QuarantineHandle`
- ``attachment_versions``         → :class:`AttachmentVersion`

Attachment 聚合根本身在既有 ``attachments`` 表上 additive 扩展（见
``app.models.attachment_models.Attachment`` 新增治理列）。
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 复用统一的 actor XOR CHECK 片段（新表严格版：actor_type NOT NULL）。
# 与 contracts.validate_actor / migration chk_*_actor_xor 语义一致。
_STRICT_ACTOR_XOR_SQL = (
    "(actor_type = 'user' AND actor_user_id IS NOT NULL AND actor_service_identity_id IS NULL) "
    "OR (actor_type = 'service' AND actor_user_id IS NULL AND actor_service_identity_id IS NOT NULL)"
)


class ServiceIdentity(Base):
    """系统作业主体（Service Identity）—— actor XOR 的 service 侧 FK 目标。

    永不获得人工确认/复核关闭/hold 解除/QC-EQCR 完成/signoff 能力（design §2.2）。
    """

    __tablename__ = "service_identities"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identity_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), server_default=text("'system'"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class UploadAttempt(Base):
    """UploadAttempt —— 内容验证前的最小上传审计（design §4.0 / R1.1 / R12）。

    ``validation_outcome`` 从 ``pending`` 收敛为 ``accepted|rejected|quarantined|failed``；
    验证失败更新同一 attempt 而非另建匿名尝试。原始文件名/绝对路径/凭据/恶意正文不得进入。
    """

    __tablename__ = "evidence_upload_attempts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    sanitized_file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    declared_media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detected_media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    received_byte_size: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_outcome: Mapped[str] = mapped_column(
        String(20), server_default=text("'pending'"), nullable=False
    )
    failure_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    command_root_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "validation_outcome IN ('pending','accepted','rejected','quarantined','failed')",
            name="chk_upload_attempt_outcome",
        ),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_upload_attempt_actor_xor"),
        Index("idx_upload_attempt_scope", "project_id", "audit_year"),
        Index("idx_upload_attempt_outcome", "project_id", "validation_outcome"),
        Index("idx_upload_attempt_command_root", "command_root_id"),
    )


class QuarantineHandle(Base):
    """隔离/暂存句柄 —— 内容不可公开读取（design §4.0）。

    ``is_publicly_readable`` 恒为 ``false``（DB CHECK 强制）；无效/恶意/完整性失败内容
    不得成为可访问文件。
    """

    __tablename__ = "evidence_quarantine_handles"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_upload_attempts.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    handle_state: Mapped[str] = mapped_column(
        String(20), server_default=text("'staged'"), nullable=False
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    detected_media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_publicly_readable: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    purged_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "handle_state IN ('staged','quarantined','purged','promoted')",
            name="chk_quarantine_state",
        ),
        CheckConstraint("is_publicly_readable = false", name="chk_quarantine_not_public"),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_quarantine_actor_xor"),
        Index("idx_quarantine_attempt", "upload_attempt_id"),
        Index("idx_quarantine_scope_state", "project_id", "handle_state"),
    )


class AttachmentVersion(Base):
    """不可变内容快照（design §4.3）。

    - ``UNIQUE(id, attachment_id, project_id, audit_year)`` 供复合 scope FK 引用。
    - ``UNIQUE(attachment_id, version_no)`` 保证版本号唯一（冗余
      ``UNIQUE(attachment_id,content_hash,version_no)`` 有意不创建，见迁移 §4.3 step 7）。
    - 复合 scope FK / previous 复合 FK / current 复合 FK / deferrable 约束触发器 / immutable
      触发器由迁移在 DB 层定义（ORM 不强制表达 DEFERRABLE/trigger 语义）。
    """

    __tablename__ = "attachment_versions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attachment_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    version_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    storage_type: Mapped[str] = mapped_column(
        String(20), server_default=text("'paperless'"), nullable=False
    )
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    availability: Mapped[str] = mapped_column(
        String(20), server_default=text("'staged'"), nullable=False
    )
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    original_creator_unknown: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "attachment_id", "project_id", "audit_year", name="uq_av_scope_identity"),
        UniqueConstraint("attachment_id", "version_no", name="uq_av_attachment_version"),
        CheckConstraint(
            "availability IN ('staged','available','quarantined','inactive')",
            name="chk_av_availability",
        ),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_av_actor_xor"),
        Index("idx_av_content_hash", "attachment_id", "content_hash"),
        Index("idx_av_scope", "project_id", "audit_year"),
        Index("idx_av_availability", "attachment_id", "availability"),
    )


# =============================================================================
# Task 2.3 (Wave 1) — legacy_attachment_alias / 持久 EvidenceRef / EvidenceDependency
# 迁移: V107__evidence_governance_legacy_alias_evidence_ref.sql
# Requirements: R3, R4, R9, R14 · Design: §4.1, §4.4 · Properties: P1,P6,P7,P8,P20,P28
# 语义契约单一真源: app.services.evidence_governance.contracts
#   (EVIDENCE_REF_PERSISTENT_COLUMNS / EVIDENCE_REF_ACTIVE_INTENT_UNIQUE /
#    EVIDENCE_REF_STATUSES / LEGACY_ALIAS_COLUMNS / LegacyResolutionKind)
# =============================================================================


class LegacyAttachmentAlias(Base):
    """旧附件 ID → (新聚合根, 确定版本) 解析别名（design §4.1）。

    ``old_attachment_id`` 是旧 ``attachments.id``，**不假设等于新聚合根**；每个旧行
    经别名解析到 root + 确定版本（永不 id-only / 静默 "current version"）。复合 scope FK
    由迁移在 DB 层定义（``fk_legacy_alias_attachment_scope`` / ``fk_legacy_alias_version_scope``），
    均 ``ON DELETE RESTRICT``。
    """

    __tablename__ = "legacy_attachment_alias"

    old_attachment_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    attachment_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    attachment_version_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    resolution_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "resolution_kind IN ('root','current_version','historical_version')",
            name="chk_legacy_alias_resolution_kind",
        ),
        Index("idx_legacy_alias_root", "attachment_id"),
        Index("idx_legacy_alias_scope", "project_id", "audit_year"),
    )


class EvidenceRef(Base):
    """持久 EvidenceRef（design §4.4；R3.1）—— 可查询、可保留的持久记录（非 per-request DTO）。

    活动引用 partial unique ``(project_id, audit_year, intent_hash) WHERE status='active'``
    由迁移的 ``uq_evidence_ref_active_intent`` 定义（P7）。反向关系不复制，使用 source /
    evidence 两套索引查询同一行（P8）。``created_by`` 是 legacy 兼容镜像列
    （``EVIDENCE_REF_PERSISTENT_COLUMNS`` 冻结）；新写真源是 ``actor_*`` XOR。
    """

    __tablename__ = "evidence_refs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(200), nullable=False)
    attachment_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attachment_versions.id", ondelete="RESTRICT"), nullable=True
    )
    target_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    intent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'active'"), nullable=False)
    deactivation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    original_creator_unknown: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active','inactive')", name="chk_evidence_ref_status"),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_evidence_ref_actor_xor"),
        # 活动 intent partial unique（P7）；反向索引 source/evidence（P8）。
        Index(
            "uq_evidence_ref_active_intent",
            "project_id",
            "audit_year",
            "intent_hash",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("idx_evidence_ref_source", "project_id", "audit_year", "source_type", "source_id", "status"),
        Index("idx_evidence_ref_evidence", "project_id", "audit_year", "evidence_type", "evidence_id", "status"),
        Index("idx_evidence_ref_attachment_version", "attachment_version_id"),
    )


class EvidenceDependency(Base):
    """统一依赖图的动态边 source→target（design §4.4；R9/P20）。

    ``source`` 变化使 ``target`` stale。canonical ``edge_hash`` 去重活动边（partial unique
    ``uq_evidence_dep_active_edge``）。与规范化 ACNR/legacy 边并集构成 ``UnifiedGraph``；
    双向索引支持正向（按 source 求下游闭包）与反向（按 target 找上游）遍历。
    """

    __tablename__ = "evidence_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(200), nullable=False)
    target_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acnr_addr_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    relation: Mapped[str] = mapped_column(String(50), nullable=False)
    edge_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'active'"), nullable=False)
    evidence_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_refs.id", ondelete="RESTRICT"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active','inactive')", name="chk_evidence_dep_status"),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_evidence_dep_actor_xor"),
        Index(
            "uq_evidence_dep_active_edge",
            "project_id",
            "audit_year",
            "edge_hash",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("idx_evidence_dep_source", "project_id", "audit_year", "source_type", "source_id", "status"),
        Index("idx_evidence_dep_target", "project_id", "audit_year", "target_type", "target_id", "status"),
        Index("idx_evidence_dep_edge_hash", "project_id", "audit_year", "edge_hash"),
        Index("idx_evidence_dep_evidence_ref", "evidence_ref_id"),
    )


# =============================================================================
# Task 2.4 (Wave 1) — OCR Job/Transition/Result/Confirmation/Writeback(+staging),
#   CitationSnapshot, ReviewEvidenceSnapshot/ReviewClose,
#   EvidenceAuditCommandRoot/Transition, outbox/inbox,
#   ArchiveManifest/Entry/Edge, LegalHold/Scope, migration checkpoint, quality snapshot
# 迁移: V108__evidence_governance_ocr_citation_review_archive_hold.sql
# Requirements: R5, R6, R7, R8, R10, R11, R12, R13, R16
# Design: §4.5(OCR 模型), §4.6(Citation/AI/Review/Manifest/Hold 与审计), §7.1(command-root)
# 语义契约单一真源: app.services.evidence_governance.contracts
#   (OcrState / OCR_TRANSITIONS / OCR_FIELD_DECISIONS / OCR_WRITEBACK_ELIGIBLE_DECISIONS /
#    HUMAN_ONLY_DECISION_FKS)
# 人工专属 FK confirmed_by_user_id / written_by_user_id / closed_by_user_id / released_by_user_id
#   为 NOT NULL（或 released 时 CHECK 非空）REFERENCES users，不接受 Service Identity。
# 不可变/append-only 触发器（ocr_results / ocr_confirmations / citation_snapshots /
#   *_transitions / archive_manifest_entries|edges / archive_manifests(sealed) /
#   evidence_quality_snapshots）由迁移在 DB 层定义（ORM 不表达触发器语义）。
# =============================================================================


class EvidenceAuditCommandRoot(Base):
    """command-root（design §7.1；R12/P25）—— 每敏感命令+幂等键+scope 恰一个 root。

    ``UNIQUE(command_type, idempotency_key, project_id, audit_year)`` 保证执行/拒绝/重放
    都不多建 root（P25）。
    """

    __tablename__ = "evidence_audit_command_roots"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    command_type: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "command_type", "idempotency_key", "project_id", "audit_year",
            name="uq_audit_command_root",
        ),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_audit_root_actor_xor"),
        Index("idx_audit_root_scope", "project_id", "audit_year"),
        Index("idx_audit_root_type", "command_type"),
    )


class EvidenceAuditTransition(Base):
    """command-root 的多行 transition 审计（design §7.1；R12/P25）—— append-only。"""

    __tablename__ = "evidence_audit_transitions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    command_root_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_audit_command_roots.id", ondelete="RESTRICT"), nullable=False
    )
    transition_type: Mapped[str] = mapped_column(String(80), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    metadata_redacted: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_audit_transition_actor_xor"),
        Index("idx_audit_transition_root", "command_root_id", "at"),
    )


class OcrJob(Base):
    """OCRJob（design §4.5；R5/P9）—— 绑定确定版本/hash/config/幂等键/lease/actor。

    ``state`` CHECK 封闭集与 ``contracts.OCR_STATES`` 一致；合法迁移由 ``contracts.OCR_TRANSITIONS``
    在服务层 CAS 强制（P9）。幂等复用 ``uq_ocr_job_idempotency``（R5.4）。
    """

    __tablename__ = "ocr_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    attachment_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    attachment_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attachment_versions.id", ondelete="RESTRICT"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parse_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    parse_config_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(30), server_default=text("'queued'"), nullable=False)
    progress: Mapped[int] = mapped_column(sa.Integer, server_default=text("0"), nullable=False)
    attempt_count: Mapped[int] = mapped_column(sa.Integer, server_default=text("0"), nullable=False)
    max_attempts: Mapped[int] = mapped_column(sa.Integer, server_default=text("5"), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    command_root_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_audit_command_roots.id", ondelete="RESTRICT"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "audit_year", "idempotency_key", name="uq_ocr_job_idempotency"),
        CheckConstraint(
            "state IN ('queued','running','awaiting_confirmation','confirmed','written_back','failed')",
            name="chk_ocr_job_state",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="chk_ocr_job_progress"),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_ocr_job_actor_xor"),
        Index("idx_ocr_job_scope", "project_id", "audit_year"),
        Index("idx_ocr_job_version", "attachment_version_id"),
        Index("idx_ocr_job_state", "project_id", "state"),
        Index("idx_ocr_job_lease", "state", "lease_expires_at"),
    )


class OcrJobTransition(Base):
    """OCRJobTransition（design §4.5）—— 每次状态迁移一条，关联 command-root；append-only。"""

    __tablename__ = "ocr_job_transitions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ocr_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ocr_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    command_root_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_audit_command_roots.id", ondelete="RESTRICT"), nullable=True
    )
    from_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_state: Mapped[str] = mapped_column(String(30), nullable=False)
    progress: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "to_state IN ('queued','running','awaiting_confirmation','confirmed','written_back','failed')",
            name="chk_ocr_transition_to_state",
        ),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_ocr_transition_actor_xor"),
        Index("idx_ocr_transition_job", "ocr_job_id", "at"),
    )


class OcrResult(Base):
    """OCRResult（design §4.5；R6.1/P11）—— 不可变原始识别结果（immutable 触发器）。"""

    __tablename__ = "ocr_results"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ocr_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ocr_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    attachment_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attachment_versions.id", ondelete="RESTRICT"), nullable=False
    )
    source_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    pages: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    page: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    region: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    engine: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    config_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_ocr_result_actor_xor"),
        Index("idx_ocr_result_job", "ocr_job_id"),
        Index("idx_ocr_result_scope", "project_id", "audit_year"),
        Index("idx_ocr_result_version", "attachment_version_id"),
    )


class OcrConfirmation(Base):
    """OCRConfirmation（design §4.5；R6.2/P12）—— append-only 人工确认修订。

    ``decision ∈ {accepted, corrected, rejected}``；``rejected`` 满足 required decided 但永不进
    mapping。``confirmed_by_user_id`` 人工专属（NOT NULL）。每字段仅一条 ``is_current`` 决定
    （partial unique ``uq_ocr_confirmation_current``）。
    """

    __tablename__ = "ocr_confirmations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ocr_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ocr_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    ocr_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ocr_results.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    field_key: Mapped[str] = mapped_column(String(200), nullable=False)
    is_required: Mapped[bool] = mapped_column(server_default=text("true"), nullable=False)
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    is_current: Mapped[bool] = mapped_column(server_default=text("true"), nullable=False)
    revision_no: Mapped[int] = mapped_column(sa.Integer, server_default=text("1"), nullable=False)
    confirmed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    confirmed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "decision IN ('accepted','corrected','rejected')", name="chk_ocr_confirmation_decision"
        ),
        CheckConstraint(
            "decision = 'rejected' OR confirmed_value IS NOT NULL", name="chk_ocr_confirmation_value"
        ),
        Index("idx_ocr_confirmation_job", "ocr_job_id", "field_key"),
        Index("idx_ocr_confirmation_result", "ocr_result_id"),
        Index(
            "uq_ocr_confirmation_current",
            "ocr_job_id",
            "field_key",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
    )


class OcrWriteback(Base):
    """OCRWriteback（design §4.5；R6.4/P13/P14）—— 目标版本/mapping/confirmation IDs/幂等/payload hash。

    ``write_mode ∈ {transactional-local, staged-external}``；``written_by_user_id`` 人工专属
    （NOT NULL）。幂等 ``uq_ocr_writeback_idempotency``（P14）。
    """

    __tablename__ = "ocr_writebacks"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ocr_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ocr_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(200), nullable=False)
    target_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    write_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    field_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confirmation_ids: Mapped[dict | list] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"), nullable=False)
    command_root_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_audit_command_roots.id", ondelete="RESTRICT"), nullable=True
    )
    written_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "audit_year", "idempotency_key", name="uq_ocr_writeback_idempotency"
        ),
        CheckConstraint(
            "write_mode IN ('transactional-local','staged-external')", name="chk_ocr_writeback_mode"
        ),
        CheckConstraint("result IN ('pending','success','failed')", name="chk_ocr_writeback_result"),
        Index("idx_ocr_writeback_job", "ocr_job_id"),
        Index("idx_ocr_writeback_target", "project_id", "target_type", "target_id"),
    )


class OcrWritebackStaging(Base):
    """staged-external 写回暂存（design §4.5；R6.4/P13）—— 目标模块以幂等键消费后回执推进。"""

    __tablename__ = "ocr_writeback_staging"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ocr_writeback_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ocr_writebacks.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    consume_state: Mapped[str] = mapped_column(
        String(20), server_default=text("'pending'"), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    receipt: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "target_type", "target_id", "idempotency_key", name="uq_ocr_wb_staging_idempotency"
        ),
        CheckConstraint(
            "consume_state IN ('pending','consumed','failed')", name="chk_ocr_wb_staging_state"
        ),
        Index("idx_ocr_wb_staging_writeback", "ocr_writeback_id"),
        Index("idx_ocr_wb_staging_state", "consume_state"),
    )


class CitationSnapshot(Base):
    """CitationSnapshot（design §4.6；R7/P15/P16）—— 不可变（immutable 触发器）。

    绑定 AiContentLog + EvidenceRef + 版本/hash + page + region + excerpt hash + index/locator version。
    """

    __tablename__ = "citation_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_content_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_content_log.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_ref_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_refs.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    target_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    region: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    excerpt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    index_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locator_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_citation_actor_xor"),
        Index("idx_citation_ai_log", "ai_content_log_id"),
        Index("idx_citation_evidence_ref", "evidence_ref_id"),
        Index("idx_citation_scope", "project_id", "audit_year"),
    )


class ReviewEvidenceSnapshot(Base):
    """ReviewEvidenceSnapshot（design §4.6；R10/P22）—— 冻结提出/关闭时 ref/version/hash/locator。"""

    __tablename__ = "review_evidence_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    evidence_ref_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_refs.id", ondelete="RESTRICT"), nullable=False
    )
    target_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locator: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    snapshot_phase: Mapped[str] = mapped_column(
        String(20), server_default=text("'raised'"), nullable=False
    )
    is_stale: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "snapshot_phase IN ('raised','closed')", name="chk_review_snapshot_phase"
        ),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_review_snapshot_actor_xor"),
        Index("idx_review_snapshot_review", "review_id", "snapshot_phase"),
        Index("idx_review_snapshot_scope", "project_id", "audit_year"),
        Index("idx_review_snapshot_evidence_ref", "evidence_ref_id"),
    )


class ReviewClose(Base):
    """ReviewClose（design §4.6；R10.2/P21）—— closed_by_user_id NOT NULL（人工专属）。"""

    __tablename__ = "review_closes"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    close_note: Mapped[str] = mapped_column(Text, nullable=False)
    closed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    command_root_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_audit_command_roots.id", ondelete="RESTRICT"), nullable=True
    )
    reopened: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    reopened_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_review_close_review", "review_id"),
        Index("idx_review_close_scope", "project_id", "audit_year"),
    )


class ArchiveManifest(Base):
    """ArchiveManifest（design §4.6/§5.5；R11/P24）—— sealed 后不可变，每次归档递增版本。"""

    __tablename__ = "archive_manifests"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    version_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    watermark: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retention_policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    package_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(String(20), server_default=text("'building'"), nullable=False)
    blocking_difference_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sealed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "audit_year", "version_no", name="uq_archive_manifest_version"),
        CheckConstraint("state IN ('building','sealed')", name="chk_archive_manifest_state"),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_archive_manifest_actor_xor"),
        Index("idx_archive_manifest_scope", "project_id", "audit_year"),
        Index("idx_archive_manifest_state", "state"),
    )


class ArchiveManifestEntry(Base):
    """ArchiveManifestEntry（design §4.6；R11/P23）—— manifest 覆盖的证据节点；append-only。"""

    __tablename__ = "archive_manifest_entries"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    archive_manifest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("archive_manifests.id", ondelete="RESTRICT"), nullable=False
    )
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    node_id: Mapped[str] = mapped_column(String(200), nullable=False)
    node_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    node_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    node_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_archive_entry_manifest", "archive_manifest_id"),
        Index("idx_archive_entry_node", "archive_manifest_id", "node_type", "node_id"),
    )


class ArchiveManifestEdge(Base):
    """ArchiveManifestEdge（design §4.6；R11/P23）—— manifest 冻结的证据图边；append-only。"""

    __tablename__ = "archive_manifest_edges"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    archive_manifest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("archive_manifests.id", ondelete="RESTRICT"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(200), nullable=False)
    relation: Mapped[str] = mapped_column(String(50), nullable=False)
    edge_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_archive_edge_manifest", "archive_manifest_id"),
        Index("idx_archive_edge_source", "archive_manifest_id", "source_type", "source_id"),
    )


class LegalHold(Base):
    """LegalHold（design §4.6/§5.5；R13/P26/P27）—— released_by_user_id 人工专属（released 时 CHECK 非空）。"""

    __tablename__ = "legal_holds"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(20), server_default=text("'active'"), nullable=False)
    graph_watermark: Mapped[str | None] = mapped_column(String(64), nullable=True)
    release_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    released_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    released_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("state IN ('active','released')", name="chk_legal_hold_state"),
        CheckConstraint(
            "(state = 'active' AND released_by_user_id IS NULL AND released_at IS NULL) "
            "OR (state = 'released' AND released_by_user_id IS NOT NULL AND released_at IS NOT NULL "
            "AND release_reason IS NOT NULL)",
            name="chk_legal_hold_release",
        ),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_legal_hold_actor_xor"),
        Index("idx_legal_hold_scope", "project_id", "audit_year"),
        Index("idx_legal_hold_state", "project_id", "state"),
    )


class LegalHoldScope(Base):
    """LegalHoldScope（design §4.6；R13/P26）—— 固化 direct/transitive 范围；范围历史不删除。"""

    __tablename__ = "legal_hold_scopes"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legal_hold_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("legal_holds.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    node_id: Mapped[str] = mapped_column(String(200), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(20), server_default=text("'direct'"), nullable=False)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("scope_kind IN ('direct','transitive')", name="chk_legal_hold_scope_kind"),
        Index("idx_legal_hold_scope_hold", "legal_hold_id"),
        Index("idx_legal_hold_scope_node", "project_id", "node_type", "node_id", "is_active"),
    )


class EvidenceOutbox(Base):
    """事务性 outbox（design §5.4/§7.1；R12/R9）—— 按 event_id 幂等，有界退避 + dead_letter。"""

    __tablename__ = "evidence_outbox"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"), nullable=False)
    attempt_count: Mapped[int] = mapped_column(sa.Integer, server_default=text("0"), nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    command_root_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_audit_command_roots.id", ondelete="RESTRICT"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("event_id", name="uq_evidence_outbox_event"),
        CheckConstraint(
            "status IN ('pending','processing','done','dead_letter')", name="chk_evidence_outbox_status"
        ),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_evidence_outbox_actor_xor"),
        Index("idx_evidence_outbox_status", "status", "next_attempt_at"),
        Index("idx_evidence_outbox_scope", "project_id", "audit_year"),
    )


class EvidenceInbox(Base):
    """inbox（design §5.4；R12）—— 按 event_id 幂等消费，避免重复副作用。"""

    __tablename__ = "evidence_inbox"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'received'"), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("event_id", name="uq_evidence_inbox_event"),
        CheckConstraint(
            "status IN ('received','processed','dead_letter')", name="chk_evidence_inbox_status"
        ),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_evidence_inbox_actor_xor"),
        Index("idx_evidence_inbox_status", "status"),
        Index("idx_evidence_inbox_scope", "project_id", "audit_year"),
    )


class EvidenceMigrationCheckpoint(Base):
    """迁移 checkpoint（design §8.2 M1；R14/P28）—— batch_key 幂等，重跑从检查点恢复不重复对象。"""

    __tablename__ = "evidence_migration_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    migration_version: Mapped[str] = mapped_column(String(20), nullable=False)
    batch_key: Mapped[str] = mapped_column(String(200), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    partition_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cursor_position: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"), nullable=False)
    processed_count: Mapped[int] = mapped_column(sa.Integer, server_default=text("0"), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("migration_version", "batch_key", name="uq_migration_checkpoint_batch"),
        CheckConstraint(
            "status IN ('pending','running','done','failed')", name="chk_migration_checkpoint_status"
        ),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_migration_checkpoint_actor_xor"),
        Index("idx_migration_checkpoint_status", "status"),
        Index("idx_migration_checkpoint_scope", "project_id", "audit_year"),
    )


class EvidenceQualitySnapshot(Base):
    """质量快照（design §9；R16/P30）—— 固定不可变快照（immutable 触发器），可复算。"""

    __tablename__ = "evidence_quality_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True
    )
    audit_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    snapshot_key: Mapped[str] = mapped_column(String(200), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    aging_buckets: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    issue_list: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_service_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_identities.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("snapshot_key", name="uq_quality_snapshot_key"),
        CheckConstraint(_STRICT_ACTOR_XOR_SQL, name="chk_quality_snapshot_actor_xor"),
        Index("idx_quality_snapshot_scope", "project_id", "audit_year"),
    )
