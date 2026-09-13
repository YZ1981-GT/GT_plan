"""四 lifecycle repositories、idempotency、lease 与 injectable clock（Task 7）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7

## 四条生命周期互不混用

* ``UploadArtifactLifecycle`` —— 只表达 quarantine/preflight（可与 quarantine
  模块的 ``ArtifactState`` 对齐，但本仓库是可恢复状态机 + lease，不写盘）。
* ``MappingDraft`` / ``TemplateCandidate`` —— draft 可变；candidate immutable。
* ``TemplatePublication`` —— PENDING_VISIBILITY / ACTIVE / …，引用 finalized authority。
* ``ProjectOperation`` —— 实例化/写入/forcesave/merge/upgrade/rollback/remap。

崩溃恢复依赖 durable operation + lease + injectable clock，不靠混合枚举猜事务。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Mapping, Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass
class FakeClock:
    """测试专用：可推进，禁止 sleep（Requirement 6.7）。"""

    _now: datetime

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)


class InvalidLifecycleTransition(ValueError):
    pass


class LifecycleError(ValueError):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# 1) UploadArtifact
# ─────────────────────────────────────────────────────────────────────────────


class UploadArtifactState(str, Enum):
    QUARANTINED = "QUARANTINED"
    PREFLIGHT_RUNNING = "PREFLIGHT_RUNNING"
    PREFLIGHT_READY = "PREFLIGHT_READY"
    PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


_UPLOAD_TRANSITIONS: dict[UploadArtifactState, frozenset[UploadArtifactState]] = {
    UploadArtifactState.QUARANTINED: frozenset({
        UploadArtifactState.PREFLIGHT_RUNNING,
        UploadArtifactState.REJECTED,
        UploadArtifactState.EXPIRED,
    }),
    UploadArtifactState.PREFLIGHT_RUNNING: frozenset({
        UploadArtifactState.PREFLIGHT_READY,
        UploadArtifactState.PREFLIGHT_FAILED,
        UploadArtifactState.REJECTED,
        UploadArtifactState.EXPIRED,
    }),
    UploadArtifactState.PREFLIGHT_READY: frozenset({
        UploadArtifactState.REJECTED,
        UploadArtifactState.EXPIRED,
    }),
    UploadArtifactState.PREFLIGHT_FAILED: frozenset({
        UploadArtifactState.REJECTED,
        UploadArtifactState.EXPIRED,
    }),
    UploadArtifactState.REJECTED: frozenset({UploadArtifactState.EXPIRED}),
    UploadArtifactState.EXPIRED: frozenset(),
}


@dataclass
class UploadArtifactRecord:
    artifact_id: str
    organization_id: str
    project_id: str | None
    state: UploadArtifactState
    artifact_sha256: str
    created_at: datetime
    updated_at: datetime
    input_digest: str | None = None
    output_digest: str | None = None
    reason: str | None = None

    def transition(
        self,
        to: UploadArtifactState,
        *,
        clock: Clock,
        reason: str,
        output_digest: str | None = None,
    ) -> None:
        allowed = _UPLOAD_TRANSITIONS.get(self.state, frozenset())
        if to not in allowed:
            raise InvalidLifecycleTransition(
                f"UploadArtifact {self.state.value} -> {to.value} 非法"
            )
        # 结构性：不得跳到 publication/ACTIVE 之类 —— 枚举里根本没有那些成员
        self.state = to
        self.updated_at = clock.now()
        self.reason = reason
        if output_digest is not None:
            self.output_digest = output_digest


# ─────────────────────────────────────────────────────────────────────────────
# 2) MappingDraft / TemplateCandidate
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class MappingDraft:
    draft_id: str
    organization_id: str
    artifact_id: str
    revision: int
    mapping: dict[str, Any]
    guidance_revision: str
    updated_at: datetime
    frozen: bool = False

    def update_mapping(
        self,
        mapping: dict[str, Any],
        *,
        clock: Clock,
        expected_revision: int,
    ) -> None:
        if self.frozen:
            raise LifecycleError("frozen draft 不可变；必须 freeze 出新 candidate")
        if expected_revision != self.revision:
            raise LifecycleError(
                f"draft revision conflict: base={expected_revision} current={self.revision}"
            )
        self.mapping = dict(mapping)
        self.revision += 1
        self.updated_at = clock.now()


@dataclass(frozen=True)
class TemplateCandidate:
    """artifact+mapping+guidance 的不可变候选 revision。"""

    candidate_id: str
    candidate_revision: str
    organization_id: str
    artifact_id: str
    artifact_sha256: str
    policy_digest: str
    scanner_digest: str
    mapping_digest: str
    guidance_digest: str
    adapter_digest: str | None
    mapping: Mapping[str, Any]
    created_at: datetime
    supersedes: str | None = None

    @property
    def digest(self) -> str:
        payload = json.dumps(
            {
                "candidateId": self.candidate_id,
                "revision": self.candidate_revision,
                "artifact": self.artifact_sha256,
                "policy": self.policy_digest,
                "scanner": self.scanner_digest,
                "mapping": self.mapping_digest,
                "guidance": self.guidance_digest,
                "adapter": self.adapter_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def freeze_candidate(
    draft: MappingDraft,
    *,
    artifact_sha256: str,
    policy_digest: str,
    scanner_digest: str,
    guidance_digest: str,
    adapter_digest: str | None,
    clock: Clock,
    supersedes: str | None = None,
) -> TemplateCandidate:
    if draft.frozen:
        raise LifecycleError("draft 已 freeze")
    mapping_digest = hashlib.sha256(
        json.dumps(draft.mapping, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    candidate = TemplateCandidate(
        candidate_id=f"cand-{uuid.uuid4().hex[:16]}",
        candidate_revision=f"r{draft.revision}-{uuid.uuid4().hex[:8]}",
        organization_id=draft.organization_id,
        artifact_id=draft.artifact_id,
        artifact_sha256=artifact_sha256,
        policy_digest=policy_digest,
        scanner_digest=scanner_digest,
        mapping_digest=mapping_digest,
        guidance_digest=guidance_digest,
        adapter_digest=adapter_digest,
        mapping=dict(draft.mapping),
        created_at=clock.now(),
        supersedes=supersedes,
    )
    draft.frozen = True
    draft.updated_at = clock.now()
    return candidate


# ─────────────────────────────────────────────────────────────────────────────
# 3) TemplatePublication
# ─────────────────────────────────────────────────────────────────────────────


class PublicationState(str, Enum):
    PENDING_VISIBILITY = "PENDING_VISIBILITY"
    ACTIVE = "ACTIVE"
    WITHDRAWN = "WITHDRAWN"
    SECURITY_REVOKED = "SECURITY_REVOKED"
    FAILED = "FAILED"


_PUBLICATION_TRANSITIONS: dict[PublicationState, frozenset[PublicationState]] = {
    PublicationState.PENDING_VISIBILITY: frozenset({
        PublicationState.ACTIVE,
        PublicationState.FAILED,
    }),
    PublicationState.ACTIVE: frozenset({
        PublicationState.WITHDRAWN,
        PublicationState.SECURITY_REVOKED,
    }),
    PublicationState.WITHDRAWN: frozenset(),
    PublicationState.SECURITY_REVOKED: frozenset(),
    PublicationState.FAILED: frozenset(),
}


@dataclass
class TemplatePublicationRecord:
    publication_id: str
    organization_id: str
    candidate_id: str
    candidate_digest: str
    authority_ref: str  # finalized TemplateAuthorityIdentity 引用，不复制字段
    state: PublicationState
    created_at: datetime
    updated_at: datetime
    reason: str | None = None

    def transition(
        self,
        to: PublicationState,
        *,
        clock: Clock,
        reason: str,
    ) -> None:
        allowed = _PUBLICATION_TRANSITIONS.get(self.state, frozenset())
        if to not in allowed:
            raise InvalidLifecycleTransition(
                f"Publication {self.state.value} -> {to.value} 非法"
            )
        self.state = to
        self.updated_at = clock.now()
        self.reason = reason


# ─────────────────────────────────────────────────────────────────────────────
# 4) ProjectOperation + lease + idempotency
# ─────────────────────────────────────────────────────────────────────────────


class ProjectOperationType(str, Enum):
    INSTANTIATE = "instantiate"
    GRID_MUTATION = "grid_mutation"
    FORCESAVE = "forcesave"
    MERGE = "merge"
    REMAP = "remap"
    UPGRADE = "upgrade"
    ROLLBACK = "rollback"
    SECURITY_MIGRATE = "security_migrate"


class ProjectOperationState(str, Enum):
    PENDING = "PENDING"
    APPLYING = "APPLYING"
    COMMITTED = "COMMITTED"
    CONFLICT = "CONFLICT"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    COMPENSATED = "COMPENSATED"


_OPERATION_TRANSITIONS: dict[ProjectOperationState, frozenset[ProjectOperationState]] = {
    ProjectOperationState.PENDING: frozenset({
        ProjectOperationState.APPLYING,
        ProjectOperationState.BLOCKED,
        ProjectOperationState.FAILED,
    }),
    ProjectOperationState.APPLYING: frozenset({
        ProjectOperationState.COMMITTED,
        ProjectOperationState.CONFLICT,
        ProjectOperationState.BLOCKED,
        ProjectOperationState.FAILED,
        ProjectOperationState.COMPENSATED,
    }),
    ProjectOperationState.COMMITTED: frozenset(),
    ProjectOperationState.CONFLICT: frozenset({ProjectOperationState.COMPENSATED}),
    ProjectOperationState.BLOCKED: frozenset({ProjectOperationState.COMPENSATED}),
    ProjectOperationState.FAILED: frozenset({ProjectOperationState.COMPENSATED}),
    ProjectOperationState.COMPENSATED: frozenset(),
}


@dataclass
class Lease:
    lease_id: str
    owner: str
    expires_at: datetime

    def is_expired(self, clock: Clock) -> bool:
        return clock.now() >= self.expires_at


@dataclass
class ProjectOperationRecord:
    operation_id: str
    organization_id: str
    project_id: str
    operation_type: ProjectOperationType
    state: ProjectOperationState
    idempotency_key: str
    base_revision: str
    current_revision: str | None
    incoming_revision: str | None
    authorization_epoch: int
    write_fence: str
    input_digest: str
    output_digest: str | None
    created_at: datetime
    updated_at: datetime
    lease: Lease | None = None
    reason: str | None = None
    result: dict[str, Any] | None = None

    def transition(
        self,
        to: ProjectOperationState,
        *,
        clock: Clock,
        reason: str,
        output_digest: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        allowed = _OPERATION_TRANSITIONS.get(self.state, frozenset())
        if to not in allowed:
            raise InvalidLifecycleTransition(
                f"ProjectOperation {self.state.value} -> {to.value} 非法"
            )
        if self.lease and self.lease.is_expired(clock) and to is ProjectOperationState.COMMITTED:
            raise LifecycleError("lease 过期，不得 COMMITTED")
        self.state = to
        self.updated_at = clock.now()
        self.reason = reason
        if output_digest is not None:
            self.output_digest = output_digest
        if result is not None:
            self.result = result


class InMemoryLifecycleRepository:
    """进程内仓库：供单元测试与未接 DB 前的状态机验证。

    生产落库属后续 migration；本仓库保证 transition/idempotency/lease 语义。
    """

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock: Clock = clock or SystemClock()
        self.uploads: dict[str, UploadArtifactRecord] = {}
        self.drafts: dict[str, MappingDraft] = {}
        self.candidates: dict[str, TemplateCandidate] = {}
        self.publications: dict[str, TemplatePublicationRecord] = {}
        self.operations: dict[str, ProjectOperationRecord] = {}
        self._idempotency: dict[str, str] = {}  # key -> operation_id

    # ── upload ──

    def create_upload(
        self,
        *,
        organization_id: str,
        project_id: str | None,
        artifact_sha256: str,
    ) -> UploadArtifactRecord:
        now = self.clock.now()
        rec = UploadArtifactRecord(
            artifact_id=f"up-{uuid.uuid4().hex[:16]}",
            organization_id=organization_id,
            project_id=project_id,
            state=UploadArtifactState.QUARANTINED,
            artifact_sha256=artifact_sha256,
            created_at=now,
            updated_at=now,
        )
        self.uploads[rec.artifact_id] = rec
        return rec

    # ── draft / candidate ──

    def create_draft(
        self,
        *,
        organization_id: str,
        artifact_id: str,
        mapping: dict[str, Any] | None = None,
    ) -> MappingDraft:
        now = self.clock.now()
        draft = MappingDraft(
            draft_id=f"draft-{uuid.uuid4().hex[:16]}",
            organization_id=organization_id,
            artifact_id=artifact_id,
            revision=1,
            mapping=dict(mapping or {}),
            guidance_revision="g-0",
            updated_at=now,
        )
        self.drafts[draft.draft_id] = draft
        return draft

    def freeze_draft(
        self,
        draft_id: str,
        *,
        artifact_sha256: str,
        policy_digest: str,
        scanner_digest: str,
        guidance_digest: str,
        adapter_digest: str | None = None,
        supersedes: str | None = None,
    ) -> TemplateCandidate:
        draft = self.drafts[draft_id]
        candidate = freeze_candidate(
            draft,
            artifact_sha256=artifact_sha256,
            policy_digest=policy_digest,
            scanner_digest=scanner_digest,
            guidance_digest=guidance_digest,
            adapter_digest=adapter_digest,
            clock=self.clock,
            supersedes=supersedes,
        )
        self.candidates[candidate.candidate_id] = candidate
        return candidate

    # ── publication ──

    def create_publication(
        self,
        *,
        organization_id: str,
        candidate_id: str,
        candidate_digest: str,
        authority_ref: str,
    ) -> TemplatePublicationRecord:
        now = self.clock.now()
        rec = TemplatePublicationRecord(
            publication_id=f"pub-{uuid.uuid4().hex[:16]}",
            organization_id=organization_id,
            candidate_id=candidate_id,
            candidate_digest=candidate_digest,
            authority_ref=authority_ref,
            state=PublicationState.PENDING_VISIBILITY,
            created_at=now,
            updated_at=now,
        )
        self.publications[rec.publication_id] = rec
        return rec

    # ── operations ──

    def begin_operation(
        self,
        *,
        organization_id: str,
        project_id: str,
        operation_type: ProjectOperationType,
        idempotency_key: str,
        base_revision: str,
        authorization_epoch: int,
        write_fence: str,
        input_digest: str,
        lease_owner: str,
        lease_ttl_seconds: float = 120.0,
        incoming_revision: str | None = None,
    ) -> ProjectOperationRecord:
        existing_id = self._idempotency.get(idempotency_key)
        if existing_id is not None:
            return self.operations[existing_id]
        now = self.clock.now()
        lease = Lease(
            lease_id=f"lease-{uuid.uuid4().hex[:12]}",
            owner=lease_owner,
            expires_at=now + timedelta(seconds=lease_ttl_seconds),
        )
        rec = ProjectOperationRecord(
            operation_id=f"op-{uuid.uuid4().hex[:16]}",
            organization_id=organization_id,
            project_id=project_id,
            operation_type=operation_type,
            state=ProjectOperationState.PENDING,
            idempotency_key=idempotency_key,
            base_revision=base_revision,
            current_revision=None,
            incoming_revision=incoming_revision,
            authorization_epoch=authorization_epoch,
            write_fence=write_fence,
            input_digest=input_digest,
            output_digest=None,
            created_at=now,
            updated_at=now,
            lease=lease,
        )
        self.operations[rec.operation_id] = rec
        self._idempotency[idempotency_key] = rec.operation_id
        return rec

    def recover_expired_leases(self) -> list[str]:
        """watchdog：lease 过期且仍 APPLYING → FAILED，可补偿。"""
        recovered: list[str] = []
        for op in self.operations.values():
            if op.state is not ProjectOperationState.APPLYING:
                continue
            if op.lease and op.lease.is_expired(self.clock):
                op.transition(
                    ProjectOperationState.FAILED,
                    clock=self.clock,
                    reason="lease_expired_watchdog",
                )
                recovered.append(op.operation_id)
        return recovered
