"""artifact reference graph、retention、访问与审计（Task 17）。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Mapping, Sequence

from app.services.custom_template_ingestion.lifecycles import Clock, FakeClock, SystemClock

__all__ = [
    "ArtifactKind",
    "ArtifactRef",
    "RetentionIntent",
    "RetentionResult",
    "ReferenceGraph",
    "EvidenceEnvelopeLite",
    "register_ref",
    "plan_retention",
    "execute_retention",
    "build_evidence_envelope",
]


class ArtifactKind(str, Enum):
    UPLOAD = "upload"
    CANDIDATE = "candidate"
    PUBLICATION = "publication"
    GENERATION = "generation"
    OPERATION = "operation"
    ROLLBACK = "rollback"
    EVIDENCE = "evidence"
    LEGAL_HOLD = "legal_hold"
    LEASE = "lease"


@dataclass
class ArtifactRef:
    artifact_id: str
    kind: ArtifactKind
    digest: str
    created_at: datetime
    ttl_seconds: int | None
    referenced_by: set[str] = field(default_factory=set)
    tombstoned: bool = False
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class RetentionIntent:
    artifact_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class RetentionResult:
    artifact_id: str
    deleted: bool
    deferred_reason: str | None


@dataclass
class ReferenceGraph:
    nodes: dict[str, ArtifactRef] = field(default_factory=dict)

    def add_edge(self, from_id: str, to_id: str) -> None:
        if to_id not in self.nodes or from_id not in self.nodes:
            raise KeyError("unknown artifact in edge")
        self.nodes[to_id].referenced_by.add(from_id)


@dataclass(frozen=True, slots=True)
class EvidenceEnvelopeLite:
    scope: Mapping[str, str]
    digests: Mapping[str, str]
    scanner_fingerprint: str
    revisions: Mapping[str, str]
    operations: tuple[str, ...]
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        # 不写正文 / token
        return {
            "scope": dict(self.scope),
            "digests": dict(self.digests),
            "scannerFingerprint": self.scanner_fingerprint,
            "revisions": dict(self.revisions),
            "operations": list(self.operations),
            "verdict": self.verdict,
        }


def register_ref(
    graph: ReferenceGraph,
    *,
    kind: ArtifactKind,
    digest: str,
    clock: Clock,
    ttl_seconds: int | None,
    artifact_id: str | None = None,
) -> ArtifactRef:
    ref = ArtifactRef(
        artifact_id=artifact_id or f"art-{uuid.uuid4()}",
        kind=kind,
        digest=digest,
        created_at=clock.now(),
        ttl_seconds=ttl_seconds,
    )
    graph.nodes[ref.artifact_id] = ref
    return ref


def plan_retention(graph: ReferenceGraph, *, clock: Clock) -> list[RetentionIntent]:
    intents: list[RetentionIntent] = []
    now = clock.now()
    for ref in graph.nodes.values():
        if ref.deleted or ref.tombstoned:
            continue
        if ref.ttl_seconds is None:
            continue
        if now >= ref.created_at + timedelta(seconds=ref.ttl_seconds):
            intents.append(RetentionIntent(artifact_id=ref.artifact_id, reason="ttl_expired"))
    return intents


def execute_retention(
    graph: ReferenceGraph,
    intent: RetentionIntent,
    *,
    protect_kinds: Sequence[ArtifactKind] = (
        ArtifactKind.PUBLICATION,
        ArtifactKind.LEGAL_HOLD,
        ArtifactKind.LEASE,
        ArtifactKind.EVIDENCE,
        ArtifactKind.ROLLBACK,
    ),
) -> RetentionResult:
    ref = graph.nodes[intent.artifact_id]
    if ref.kind in protect_kinds:
        return RetentionResult(
            artifact_id=ref.artifact_id,
            deleted=False,
            deferred_reason=f"protected_kind:{ref.kind.value}",
        )
    if ref.referenced_by:
        ref.tombstoned = True
        return RetentionResult(
            artifact_id=ref.artifact_id,
            deleted=False,
            deferred_reason="still_referenced",
        )
    ref.tombstoned = True
    ref.deleted = True
    return RetentionResult(artifact_id=ref.artifact_id, deleted=True, deferred_reason=None)


def build_evidence_envelope(
    *,
    scope: Mapping[str, str],
    digests: Mapping[str, str],
    scanner_fingerprint: str,
    revisions: Mapping[str, str],
    operations: Sequence[str],
    verdict: str,
) -> EvidenceEnvelopeLite:
    forbidden = ("token", "password", "raw_bytes", "body", "content")
    blob = " ".join(list(scope.values()) + list(digests.values())).lower()
    for f in forbidden:
        if f in blob:
            raise ValueError(f"EvidenceEnvelope 不得含 {f}")
    return EvidenceEnvelopeLite(
        scope=dict(scope),
        digests=dict(digests),
        scanner_fingerprint=scanner_fingerprint,
        revisions=dict(revisions),
        operations=tuple(operations),
        verdict=verdict,
    )
