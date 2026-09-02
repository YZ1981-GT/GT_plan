# -*- coding: utf-8 -*-
"""底稿 HTML ↔ OnlyOffice 双向回写：V151 的 28 张表 ORM 映射。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 10
Requirements: 2.1, 2.4, 2.5, 2.9, 4.3, 5.4, 5.5, 5.10, 8.5, 10.5, 10.9, 10.10, 10.11, 13.5, 14.10
Properties: P4 / P5 / P18 / P36 / P43 / P59 / P63 / P64 / P68

═══ 边界（Task 9 已建 schema，本模块只映射，不重建）═══

`backend/migrations/V151__workpaper_sync_content_application_bundle_scope.sql`
是这些表的唯一 DDL 真源（215 条 CHECK / 19 条 UNIQUE / 34 触发器）。本模块**只做
列级映射**，刻意不在 ORM 侧复制 CHECK/UNIQUE 声明：

* 复制约束会形成第二真源 —— 改了 V151 而忘了 ORM（或反之）时两边静默分叉；
* 不可变性/跨行不变式（duplicate 链环、delivery 归属、bundle typed slots）由 DB
  触发器在 COMMIT 时强制，ORM 层无法表达；
* `backend/tests/workpaper_sync/test_task10_orm_repository_contract.py` 以
  **V151 DDL 文本 ↔ ORM 列集合双向比对**锁死映射（多一列/少一列/类型不符即红），
  这比在两处各写一遍约束更能抓漂移。

═══ Property 64 的 ORM 层判据 ═══

`application_key` 只能出现在 `working_paper_content_application`。
`WorkpaperSyncOperation` 出现同名字段即违反 Property 64（operation 不得复制
application identity 当幂等真源），守卫直接断言 ORM 列集合。
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# ---------------------------------------------------------------------------
# 复用列类型（与 V151 的 CHAR(64) / VARCHAR(n) 严格对齐）
# ---------------------------------------------------------------------------

_UUID = PG_UUID(as_uuid=True)
_DIGEST = sa.CHAR(64)
_TS = sa.DateTime(timezone=True)


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(_UUID, primary_key=True, default=uuid.uuid4)


# ═══════════════════════════════════════════════════════════════════════════
# 1. artifact / definition / bundle
# ═══════════════════════════════════════════════════════════════════════════


class WorkpaperArtifact(Base):
    """内容寻址不可变文件登记表。

    `kind=incoming` 永不 `published/current/resolvable`（Requirement 5.6）；
    `durable` 与 `quarantined` 互斥且不可互转，quarantined 保持 `durable_at IS NULL`。
    """

    __tablename__ = "working_paper_artifact"

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("projects.id"), nullable=False)
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("working_paper.id"), nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    state: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    relative_path: Mapped[str] = mapped_column(sa.Text, nullable=False)
    sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    document_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    retention_class: Mapped[str] = mapped_column(
        sa.String(40), nullable=False, server_default=sa.text("'default'")
    )
    legal_hold: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    source_delivery_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_callback_delivery.id"), nullable=True
    )
    created_by_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_operation.id"), nullable=True
    )
    durable_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    quarantined_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    orphaned_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


class WorkpaperSyncDefinitionArtifact(Base):
    """immutable template / instrumentation / contract / authority_model 定义快照。"""

    __tablename__ = "working_paper_sync_definition_artifact"

    id: Mapped[uuid.UUID] = _pk()
    kind: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    logical_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    semantic_version: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    blob_artifact_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_artifact.id"), nullable=False
    )
    sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    structure_hash: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    authority_model_type: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    source_commit: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_artifact.id"), nullable=True
    )
    state: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'candidate'")
    )
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    approved_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)


class WorkpaperSyncDefinitionNullMarker(Base):
    """optional child 的版本化 typed null marker registry（禁 SQL NULL/空串/全零 hash）。"""

    __tablename__ = "working_paper_sync_definition_null_marker"

    marker_id: Mapped[str] = mapped_column(sa.String(80), primary_key=True)
    applies_to_slot: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    marker_version: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    canonical_payload: Mapped[str] = mapped_column(sa.Text, nullable=False)
    sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    state: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'active'")
    )
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


class WorkpaperSyncDefinitionBundle(Base):
    """authority model + template/instrumentation/contract 三类 typed canonical slots。

    四个 slot 全部 NOT NULL；`projection_contract` 的三个 child 必须均为 approved
    definition（不得用 marker 冒充 contract）。
    """

    __tablename__ = "working_paper_sync_definition_bundle"

    id: Mapped[uuid.UUID] = _pk()
    schema_version: Mapped[str] = mapped_column(
        sa.String(50), nullable=False, server_default=sa.text("'definition-bundle:v1'")
    )
    authority_model_definition_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_artifact.id"), nullable=False
    )
    authority_model_definition_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    template_slot_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    template_slot_ref: Mapped[str] = mapped_column(sa.Text, nullable=False)
    template_slot_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    instrumentation_slot_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    instrumentation_slot_ref: Mapped[str] = mapped_column(sa.Text, nullable=False)
    instrumentation_slot_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    contract_slot_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    contract_slot_ref: Mapped[str] = mapped_column(sa.Text, nullable=False)
    contract_slot_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    canonical_payload_artifact_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_artifact.id"), nullable=False
    )
    canonical_payload_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    state: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'candidate'")
    )
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    approved_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)


# ═══════════════════════════════════════════════════════════════════════════
# 2. content version / representation / entry pointer / candidate
# ═══════════════════════════════════════════════════════════════════════════


class WorkpaperContentVersion(Base):
    """immutable 业务内容版本。`revision` 只因业务 projection/权威内容变化递增。"""

    __tablename__ = "working_paper_content_version"

    id: Mapped[uuid.UUID] = _pk()
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("working_paper.id"), nullable=False)
    revision: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_version.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    projection_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_artifact.id"), nullable=True
    )
    projection_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    authoritative_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_artifact.id"), nullable=True
    )
    authoritative_artifact_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    operation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_operation.id"), nullable=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


class WorkpaperContentRepresentation(Base):
    """同一 content version 的 1:N immutable OOXML representation generation。"""

    __tablename__ = "working_paper_content_representation"

    id: Mapped[uuid.UUID] = _pk()
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("working_paper.id"), nullable=False)
    content_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_content_version.id"), nullable=False
    )
    entry_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    generation: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    parent_representation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_representation.id"), nullable=True
    )
    document_type: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_artifact.id"), nullable=False
    )
    artifact_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    definition_bundle_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_bundle.id"), nullable=False
    )
    definition_bundle_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    authority_model_definition_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_artifact.id"), nullable=False
    )
    authority_model_definition_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    adapter_id: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    adapter_build_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    structure_hash: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    identity_inventory_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    reason: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


class WorkpaperSyncEntryState(Base):
    """entry 级 current representation pointer（candidate 不可引用）。"""

    __tablename__ = "working_paper_sync_entry_state"

    wp_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper.id"), primary_key=True
    )
    entry_id: Mapped[str] = mapped_column(sa.String(200), primary_key=True)
    current_representation_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_content_representation.id"), nullable=False
    )
    representation_generation: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


class WorkpaperRepresentationUpgradeCandidate(Base):
    """non-current representation 升级候选：resolver/room/current pointer 均不得读取。"""

    __tablename__ = "working_paper_representation_upgrade_candidate"

    id: Mapped[uuid.UUID] = _pk()
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("working_paper.id"), nullable=False)
    content_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_content_version.id"), nullable=False
    )
    entry_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    source_representation_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_content_representation.id"), nullable=False
    )
    staged_artifact_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_artifact.id"), nullable=False
    )
    staged_artifact_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    template_definition_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_artifact.id"), nullable=False
    )
    instrumentation_definition_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_artifact.id"), nullable=False
    )
    target_contract_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_artifact.id"), nullable=True
    )
    target_definition_bundle_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_bundle.id"), nullable=True
    )
    finalized_representation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_representation.id"), nullable=True
    )
    state: Mapped[str] = mapped_column(
        sa.String(30), nullable=False, server_default=sa.text("'staged'")
    )
    visible_equivalence_report_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    rollback_source_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    finalized_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)


class WorkpaperPendingMutation(Base):
    """HTML flush 产生的短 TTL 单次逻辑消费 mutation token。"""

    __tablename__ = "working_paper_pending_mutation"

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("projects.id"), nullable=False)
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("working_paper.id"), nullable=False)
    entry_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    sheet_key: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("users.id"), nullable=False)
    expected_revision: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    payload_artifact_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_artifact.id"), nullable=False
    )
    payload_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    state: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'pending'")
    )
    result_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_operation.id"), nullable=True
    )
    result_content_version_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_version.id"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(_TS, nullable=False)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    committed_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)


# ═══════════════════════════════════════════════════════════════════════════
# 3. authorization-only scope index
# ═══════════════════════════════════════════════════════════════════════════


class WorkpaperSyncScopeIndex(Base):
    """authorization-before-business-read 的非敏感归属索引。

    `(resource_kind, resource_id)` tombstone 永不物理删除/清空/复用；
    `resource_id` 只接受 opaque identity（纯数字 numeric revision 被 DB CHECK 拒绝）。
    """

    __tablename__ = "working_paper_sync_scope_index"

    resource_kind: Mapped[str] = mapped_column(sa.String(40), primary_key=True)
    resource_id: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("projects.id"), nullable=False)
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("working_paper.id"), nullable=False)
    entry_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    room_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True)
    generation: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    retired_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)


# ═══════════════════════════════════════════════════════════════════════════
# 4. room / participant / confirmation
# ═══════════════════════════════════════════════════════════════════════════


class WorkpaperOoRoom(Base):
    """共享 OO room：server last-applied 与 client-confirmed 是两套独立指针。"""

    __tablename__ = "working_paper_oo_room"

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("projects.id"), nullable=False)
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("working_paper.id"), nullable=False)
    entry_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    doc_key: Mapped[str] = mapped_column(sa.String(150), nullable=False)
    generation: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    opened_base_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_content_version.id"), nullable=False
    )
    last_applied_version_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_version.id"), nullable=True
    )
    client_confirmed_base_version_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_version.id"), nullable=True
    )
    client_confirmed_representation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_representation.id"), nullable=True
    )
    client_confirmed_definition_bundle_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_bundle.id"), nullable=True
    )
    client_confirmed_definition_bundle_sha256: Mapped[str | None] = mapped_column(
        _DIGEST, nullable=True
    )
    client_confirmed_projection_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    latest_request_sequence: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("0")
    )
    latest_durable_sequence: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("0")
    )
    latest_durable_application_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_application.id"), nullable=True
    )
    write_fence_epoch: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("1")
    )
    close_barrier_epoch: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("0")
    )
    close_leader_intent_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_close_intent.id"), nullable=True
    )
    close_leader_eligibility_epoch: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("0")
    )
    close_leader_eligibility_digest: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    state: Mapped[str] = mapped_column(
        sa.String(30), nullable=False, server_default=sa.text("'opening'")
    )
    refresh_required_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    refresh_reason: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(_TS, nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


class WorkpaperOoParticipant(Base):
    """逐用户 participant lease。`closing` 是 close intent 创建时的原子中间态。"""

    __tablename__ = "working_paper_oo_participant"

    id: Mapped[uuid.UUID] = _pk()
    room_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_room.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("users.id"), nullable=False)
    mode: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    state: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'active'")
    )
    permission_epoch: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    joined_write_fence_epoch: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    lease_token_hash: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(_TS, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    oo_drop_confirmed_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


class WorkpaperOoClientConfirmation(Base):
    """DocEditor `onDocumentReady` 后的 descriptor 逐项确认。"""

    __tablename__ = "working_paper_oo_client_confirmation"

    id: Mapped[uuid.UUID] = _pk()
    room_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_room.id"), nullable=False
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_participant.id"), nullable=False
    )
    generation: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    doc_key: Mapped[str] = mapped_column(sa.String(150), nullable=False)
    representation_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_content_representation.id"), nullable=False
    )
    artifact_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    content_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_content_version.id"), nullable=False
    )
    projection_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    definition_bundle_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_bundle.id"), nullable=False
    )
    definition_bundle_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    authority_model_definition_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    bundle_slots_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    write_fence_epoch: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(
        _TS, nullable=False, server_default=sa.func.now()
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)


# ═══════════════════════════════════════════════════════════════════════════
# 5. forcesave request / close intent
# ═══════════════════════════════════════════════════════════════════════════


class WorkpaperForcesaveRequest(Base):
    """Command Service 调用前冻结的 request。

    幂等唯一范围固定为 `(room_id, generation, initiated_by_participant_id, kind,
    idempotency_key)`，另存 canonical `frozen_request_fingerprint` 供逐项等值比对。
    """

    __tablename__ = "working_paper_forcesave_request"

    id: Mapped[uuid.UUID] = _pk()
    room_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_room.id"), nullable=False
    )
    generation: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    request_sequence: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    initiated_by_participant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_participant.id"), nullable=False
    )
    initiator_permission_epoch: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    client_edit_epoch: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    write_fence_epoch: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    client_base_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_content_version.id"), nullable=False
    )
    client_base_representation_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_content_representation.id"), nullable=False
    )
    client_base_projection_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    definition_bundle_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_bundle.id"), nullable=False
    )
    definition_bundle_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    authority_model_definition_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_artifact.id"), nullable=False
    )
    authority_model_definition_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    adapter_build_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    contributor_snapshot_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    frozen_request_fingerprint: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    state: Mapped[str] = mapped_column(
        sa.String(30), nullable=False, server_default=sa.text("'frozen'")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


class WorkpaperOoCloseIntent(Base):
    """clean close intent；只有 reconciler 可把 deterministic leader CAS 提升为 close_capture。"""

    __tablename__ = "working_paper_oo_close_intent"

    id: Mapped[uuid.UUID] = _pk()
    room_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_room.id"), nullable=False
    )
    generation: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    participant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_participant.id"), nullable=False
    )
    client_confirmation_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_client_confirmation.id"), nullable=False
    )
    intent_sequence: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    barrier_epoch: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    eligibility_epoch: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("0")
    )
    ordinary_forcesave_request_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_forcesave_request.id"), nullable=True
    )
    promoted_request_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_forcesave_request.id"), nullable=True
    )
    state: Mapped[str] = mapped_column(
        sa.String(30), nullable=False, server_default=sa.text("'created'")
    )
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    reconciled_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)


class WorkpaperOoCloseIntentEvent(Base):
    """close intent 的 append-only eligibility/leader timeline。"""

    __tablename__ = "working_paper_oo_close_intent_event"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    intent_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_close_intent.id"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    from_state: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    to_state: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    eligibility_epoch: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    eligibility_digest: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    actor_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True)
    authorization_result: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    error_code: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


# ═══════════════════════════════════════════════════════════════════════════
# 6. recovery case
# ═══════════════════════════════════════════════════════════════════════════


class WorkpaperCallbackRecoveryCase(Base):
    """无法唯一归组的 durable incoming 的可审计恢复案例。claim 前三实体恒空。"""

    __tablename__ = "working_paper_callback_recovery_case"

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("projects.id"), nullable=False)
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("working_paper.id"), nullable=False)
    entry_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    room_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_room.id"), nullable=False
    )
    generation: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    source_delivery_key: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    incoming_artifact_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_artifact.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    candidate_confirmation_digest: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    candidate_contributor_digest: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    state: Mapped[str] = mapped_column(
        sa.String(30), nullable=False, server_default=sa.text("'unclaimed'")
    )
    claimed_by_participant_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_participant.id"), nullable=True
    )
    prior_confirmation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_client_confirmation.id"), nullable=True
    )
    recovery_request_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_forcesave_request.id"), nullable=True
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_application.id"), nullable=True
    )
    operation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_operation.id"), nullable=True
    )
    claimed_definition_bundle_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_bundle.id"), nullable=True
    )
    claimed_definition_bundle_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(_TS, nullable=False)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    claimed_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)


class WorkpaperCallbackRecoveryCaseEvent(Base):
    """recovery case 的独立 append-only timeline（与 operation timeline 分离）。"""

    __tablename__ = "working_paper_callback_recovery_case_event"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_callback_recovery_case.id"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    from_state: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    to_state: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    actor_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True)
    authorization_result: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    prior_confirmation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_client_confirmation.id"), nullable=True
    )
    definition_bundle_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    error_code: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


# ═══════════════════════════════════════════════════════════════════════════
# 7. content application（frozen identity 的唯一 owner）
# ═══════════════════════════════════════════════════════════════════════════


class WorkpaperContentApplication(Base):
    """durable incoming 对业务状态的一次逻辑应用；`application_key` 的唯一 owner。

    `origin_request_sequence` 不可变；`effective_request_sequence` 只可 GREATEST
    单调提升，并与 room 的 `latest_durable_application_id/latest_durable_sequence`
    同事务更新。禁止 self-supersede。
    """

    __tablename__ = "working_paper_content_application"

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("projects.id"), nullable=False)
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("working_paper.id"), nullable=False)
    entry_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    room_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_room.id"), nullable=False
    )
    generation: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    origin_request_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_forcesave_request.id"), nullable=False
    )
    application_key: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    client_edit_epoch: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    origin_request_sequence: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    effective_request_sequence: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    base_version_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_content_version.id"), nullable=False
    )
    base_representation_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_content_representation.id"), nullable=False
    )
    current_revision: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    result_revision: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    incoming_artifact_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_artifact.id"), nullable=False
    )
    incoming_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    incoming_projection_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    merged_projection_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    result_representation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_representation.id"), nullable=True
    )
    result_artifact_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    definition_bundle_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_bundle.id"), nullable=False
    )
    definition_bundle_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    authority_model_definition_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_artifact.id"), nullable=False
    )
    authority_model_definition_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    adapter_id: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    adapter_build_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    contributor_snapshot_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    conflict_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    conflict_set_digest: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    state: Mapped[str] = mapped_column(
        sa.String(30), nullable=False, server_default=sa.text("'queued'")
    )
    superseded_by_application_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_application.id"), nullable=True
    )
    logical_result_code: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    durable_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)


class WorkpaperContentApplicationEvent(Base):
    """application 的 append-only timeline（含 `sequence_folded` 审计）。"""

    __tablename__ = "working_paper_content_application_event"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_content_application.id"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    from_state: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    to_state: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    folded_request_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_forcesave_request.id"), nullable=True
    )
    origin_request_sequence: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    effective_request_sequence: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    room_latest_durable_sequence: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    actor_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True)
    error_code: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


# ═══════════════════════════════════════════════════════════════════════════
# 8. operation / event / contributor
# ═══════════════════════════════════════════════════════════════════════════


class WorkpaperSyncOperation(Base):
    """用户轮询/执行/timeline 容器；**不承担** application identity。

    🔴 Property 64：本表不得出现 `application_key` 列。
    `application_id` 是 nullable UNIQUE primary FK；`duplicate_of_operation_id`
    是 nullable direct self FK，只能直指已绑定同一 application 的 primary。
    """

    __tablename__ = "working_paper_sync_operation"

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("projects.id"), nullable=False)
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("working_paper.id"), nullable=False)
    entry_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_room.id"), nullable=True
    )
    forcesave_request_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_forcesave_request.id"), nullable=True
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_application.id"), nullable=True
    )
    duplicate_of_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_operation.id"), nullable=True
    )
    initiated_by_participant_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_participant.id"), nullable=True
    )
    direction: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    state: Mapped[str] = mapped_column(
        sa.String(30), nullable=False, server_default=sa.text("'created'")
    )
    definition_bundle_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_bundle.id"), nullable=False
    )
    definition_bundle_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    authority_model_definition_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_artifact.id"), nullable=False
    )
    authority_model_definition_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    error_code: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    error_stage: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    application_bound_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


class WorkpaperSyncOperationEvent(Base):
    """operation 的 append-only transition event（current state 只是它的投影）。"""

    __tablename__ = "working_paper_sync_operation_event"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    operation_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_operation.id"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    from_state: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    to_state: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    stage: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    error_code: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    actor_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True)
    client_edit_epoch: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    origin_request_sequence: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    effective_request_sequence: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True)
    detail_digest: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


class WorkpaperSyncOperationContributor(Base):
    """聚合 callback 的 contributor 快照（initiator / route / contributor 三者分离）。"""

    __tablename__ = "working_paper_sync_operation_contributor"

    operation_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_operation.id"), primary_key=True
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_participant.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("users.id"), nullable=False)
    permission_epoch: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    confidence: Mapped[str] = mapped_column(sa.String(20), nullable=False)


# ═══════════════════════════════════════════════════════════════════════════
# 9. callback delivery / conflict
# ═══════════════════════════════════════════════════════════════════════════


class WorkpaperCallbackDelivery(Base):
    """每次 callback 投递。归属只以 immutable `durable_at` 判定。"""

    __tablename__ = "working_paper_callback_delivery"

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("projects.id"), nullable=False)
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("working_paper.id"), nullable=False)
    entry_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    room_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_oo_room.id"), nullable=False
    )
    generation: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    operation_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_operation.id"), nullable=True
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_application.id"), nullable=True
    )
    forcesave_request_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_forcesave_request.id"), nullable=True
    )
    callback_recovery_case_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_callback_recovery_case.id"), nullable=True
    )
    route_credential_id: Mapped[uuid.UUID] = mapped_column(_UUID, nullable=False)
    callback_status: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    delivery_key: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    state: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'received'")
    )
    payload_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    oo_users_digest: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    correlation_result: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    incoming_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_artifact.id"), nullable=True
    )
    response_error: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    received_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())
    durable_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)


class WorkpaperSyncConflict(Base):
    """字段级冲突记录（双侧可追溯 + canonical application fence）。"""

    __tablename__ = "working_paper_sync_conflict"

    id: Mapped[uuid.UUID] = _pk()
    operation_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_operation.id"), nullable=False
    )
    client_edit_epoch: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    canonical_application_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_content_application.id"), nullable=True
    )
    effective_request_sequence: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    stable_field_key: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    business_label: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    sheet_key: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    table_key: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    row_key: Mapped[str] = mapped_column(
        sa.String(200), nullable=False, server_default=sa.text("''")
    )
    json_pointer: Mapped[str] = mapped_column(sa.Text, nullable=False)
    oo_location: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("''"))
    field_source: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    protection_policy: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    suggested_action: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    conflict_kind: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    base_value: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    current_value: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    incoming_value: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    resolution: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    resolved_value: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


# ═══════════════════════════════════════════════════════════════════════════
# 10. evidence / 回填台账
# ═══════════════════════════════════════════════════════════════════════════


class WorkpaperSyncTestRun(Base):
    """一次可复现验收执行（source-backed capability identity，禁自由文本覆写）。"""

    __tablename__ = "working_paper_sync_test_run"

    id: Mapped[uuid.UUID] = _pk()
    entry_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    source_commit: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    runner_version: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    manifest_source_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    editability: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    room_model: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    scenario_profile_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    onlyoffice_build: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    browser_build: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    environment_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    required_scenario_set_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    authority_model_definition_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    definition_bundle_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    run_manifest_artifact_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_artifact.id"), nullable=False
    )
    run_manifest_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    started_at: Mapped[datetime] = mapped_column(_TS, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    aggregate_result: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'unverified'")
    )


class WorkpaperEntryEvidenceScenario(Base):
    """逐 scenario 证据行。download-only/recovery-reject 场景 operation/application 恒空。"""

    __tablename__ = "working_paper_entry_evidence_scenario"

    id: Mapped[uuid.UUID] = _pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_test_run.id"), nullable=False
    )
    scenario_id: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    ordinal: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    scenario_kind: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    result: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    # 🔴 server_default 写 `'[]'` 而不是 `'[]'::jsonb`（Task 12 复盘修正）：
    #
    # PostgreSQL 对 jsonb 列的 `DEFAULT '[]'` 会隐式转型，两种写法在真实库上等价
    # （真实表由 V151 SQL 创建，ORM 的 server_default 只影响 DDL 生成）。但带
    # `::jsonb` 的文本会被 SQLAlchemy 原样塞进 `CREATE TABLE`，SQLite 解析到 `:`
    # 直接 `unrecognized token: ":"` ⇒ 全平台**任何**用
    # `Base.metadata.create_all(sqlite)` 的测试在 setup 阶段就 ERROR。
    # 2026-08-25 实测辐射面：test_wopi_working_paper_qc_review(42) +
    # test_archive_orchestrator(15) + test_archive_deprecated(3) 共 60 例。
    operation_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'")
    )
    application_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'")
    )
    recovery_case_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'")
    )
    content_version_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'")
    )
    representation_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'")
    )
    authority_model_definition_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    definition_bundle_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    trace_bundle_artifact_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper_artifact.id"), nullable=False
    )
    trace_bundle_sha256: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    server_timeline_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    database_snapshot_digest: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    browser_build: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    error_code: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False, server_default=sa.func.now())


class WorkpaperContentRevisionBackfillLedger(Base):
    """V151 revision 0 回填台账：只记录，不创建 content version/representation。"""

    __tablename__ = "working_paper_content_revision_backfill_ledger"

    wp_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("working_paper.id"), primary_key=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(_UUID, ForeignKey("projects.id"), nullable=False)
    backfilled_content_revision: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    legacy_file_version: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    had_parsed_data: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    entry_verification_state: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'unverified'")
    )
    content_version_created: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    representation_created: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    migration_version: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, server_default=sa.text("'151'")
    )
    backfilled_at: Mapped[datetime] = mapped_column(
        _TS, nullable=False, server_default=sa.func.now()
    )


# ═══════════════════════════════════════════════════════════════════════════
# V153 追加（Task 76，只加不动）：candidate attach 的 append-only 审计轨
# ═══════════════════════════════════════════════════════════════════════════
class WorkpaperRepresentationCandidateEvent(Base):
    """candidate contract/bundle attach 的 append-only 审计事件（V153）。

    🔴 **刻意不进** :data:`WORKPAPER_SYNC_TABLES`：那张字典的语义是「V151 的 28 张表」，
    Task 10 的 `test_orm_covers_exactly_the_v151_tables` 以**完全相等**锁死它（多一张即红）。
    本表的 DDL 真源是
    `backend/migrations/V153__workpaper_representation_candidate_attach_event.sql`，
    由 Task 76 自己的守卫做 DDL ↔ ORM 双向比对，不挂在 V151 的分母上。
    """

    __tablename__ = "working_paper_representation_candidate_event"
    id: Mapped[uuid.UUID] = _pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        _UUID,
        ForeignKey("working_paper_representation_upgrade_candidate.id"),
        nullable=False,
    )
    sequence_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    from_state: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    to_state: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    contract_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_artifact.id"), nullable=True
    )
    definition_bundle_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_sync_definition_bundle.id"), nullable=True
    )
    definition_bundle_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("users.id"), nullable=True
    )
    correlation_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    detail: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        _TS, nullable=False, server_default=sa.func.now()
    )


#: V151 的 28 张表 → ORM 类。守卫用它做「DDL ↔ ORM」双向比对。
WORKPAPER_SYNC_TABLES: dict[str, type[Base]] = {
    m.__tablename__: m
    for m in (
        WorkpaperArtifact,
        WorkpaperSyncDefinitionArtifact,
        WorkpaperSyncDefinitionNullMarker,
        WorkpaperSyncDefinitionBundle,
        WorkpaperContentVersion,
        WorkpaperContentRepresentation,
        WorkpaperSyncEntryState,
        WorkpaperRepresentationUpgradeCandidate,
        WorkpaperPendingMutation,
        WorkpaperSyncScopeIndex,
        WorkpaperOoRoom,
        WorkpaperOoParticipant,
        WorkpaperOoClientConfirmation,
        WorkpaperForcesaveRequest,
        WorkpaperOoCloseIntent,
        WorkpaperOoCloseIntentEvent,
        WorkpaperCallbackRecoveryCase,
        WorkpaperCallbackRecoveryCaseEvent,
        WorkpaperContentApplication,
        WorkpaperContentApplicationEvent,
        WorkpaperSyncOperation,
        WorkpaperSyncOperationEvent,
        WorkpaperSyncOperationContributor,
        WorkpaperCallbackDelivery,
        WorkpaperSyncConflict,
        WorkpaperSyncTestRun,
        WorkpaperEntryEvidenceScenario,
        WorkpaperContentRevisionBackfillLedger,
    )
}
