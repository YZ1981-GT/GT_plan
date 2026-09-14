"""Frozen P0 contracts — Task 1.3 (Wave 0).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R3, R5, R14
Design refs: §Data Models (actor XOR), §4.1 (legacy ID resolution),
             §4.4 (persistent EvidenceRef), §4.5 (OCR model)

This module freezes four P0 contracts as pure, dependency-free definitions so
that later waves (migrations / ORM / services) implement *against a single
source of truth* rather than re-deriving them:

1. Actor XOR + no-anonymous invariant .......... `validate_actor` / `ACTOR_*`
2. Closed OCR enum + state machine ............. `OcrState` / `OCR_TRANSITIONS`
3. Persistent EvidenceRef physical model shape . `EVIDENCE_REF_PERSISTENT_COLUMNS`
4. Legacy attachment ID resolution contract .... `LegacyResolutionKind` / `validate_legacy_resolution`

These are frozen: changing any set/rule here is a governance decision and must
be accompanied by a spec update + updated contract tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# 1) Actor contract — R1.4 / R3.1 / R5 / R14.4 ; Property P3
#    Every governance table carrying an actor uses a *physical* XOR, never a
#    single polymorphic actor_id. Anonymous new records are forbidden.
# ─────────────────────────────────────────────────────────────────────────────

ACTOR_TYPES: frozenset[str] = frozenset({"user", "service"})

#: Physical column names frozen by the design's shared actor block. Table
#: prefixes are allowed (e.g. ``uploaded_by_*``) but the *semantics* — three
#: columns forming a XOR — must not collapse into one polymorphic ``actor_id``.
ACTOR_COLUMNS: tuple[str, ...] = (
    "actor_type",
    "actor_user_id",
    "actor_service_identity_id",
)

#: Human-only decision FKs. A Service Identity MUST NEVER populate these, and
#: they are ``NOT NULL`` on their tables (design §Data Models).
HUMAN_ONLY_DECISION_FKS: frozenset[str] = frozenset({
    "confirmed_by_user_id",   # OCR / AI human confirmation
    "written_by_user_id",     # OCR writeback approval
    "closed_by_user_id",      # Review close
    "released_by_user_id",    # Legal hold release
})


def validate_actor(
    actor_type: Optional[str],
    actor_user_id: Optional[str],
    actor_service_identity_id: Optional[str],
) -> Optional[str]:
    """Return ``None`` if the actor tuple satisfies the frozen XOR + no-anonymous
    invariant, otherwise a short failure reason (used for diagnostics/tests).

    Invariant (P3):
      * ``actor_type`` must be exactly one of ``{'user','service'}`` (no NULL →
        no anonymous new records).
      * ``user``  → ``actor_user_id`` set AND ``actor_service_identity_id`` NULL.
      * ``service`` → ``actor_service_identity_id`` set AND ``actor_user_id`` NULL.
    """
    if actor_type not in ACTOR_TYPES:
        return f"actor_type must be one of {sorted(ACTOR_TYPES)}, got {actor_type!r}"
    if actor_type == "user":
        if actor_user_id is None:
            return "actor_type='user' requires actor_user_id"
        if actor_service_identity_id is not None:
            return "actor_type='user' forbids actor_service_identity_id"
        return None
    # actor_type == "service"
    if actor_service_identity_id is None:
        return "actor_type='service' requires actor_service_identity_id"
    if actor_user_id is not None:
        return "actor_type='service' forbids actor_user_id"
    return None


def is_valid_actor(
    actor_type: Optional[str],
    actor_user_id: Optional[str],
    actor_service_identity_id: Optional[str],
) -> bool:
    return validate_actor(actor_type, actor_user_id, actor_service_identity_id) is None


# ─────────────────────────────────────────────────────────────────────────────
# 2) OCR state machine — R5.2 ; Property P9 (closed state machine)
# ─────────────────────────────────────────────────────────────────────────────

class OcrState(str, Enum):
    queued = "queued"
    running = "running"
    awaiting_confirmation = "awaiting_confirmation"
    confirmed = "confirmed"
    written_back = "written_back"
    failed = "failed"


#: The complete closed set of legal OCR job states.
OCR_STATES: frozenset[str] = frozenset(s.value for s in OcrState)

#: The ONLY legal directed transitions (design §4.5 / R5.2).
#: Any (from, to) pair not in this set is illegal and must leave state + history
#: unchanged (P9).
OCR_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    (OcrState.queued.value, OcrState.running.value),
    (OcrState.running.value, OcrState.awaiting_confirmation.value),
    (OcrState.awaiting_confirmation.value, OcrState.confirmed.value),
    (OcrState.confirmed.value, OcrState.written_back.value),
    (OcrState.queued.value, OcrState.failed.value),
    (OcrState.running.value, OcrState.failed.value),
    (OcrState.failed.value, OcrState.queued.value),  # retry
})

#: States with no outgoing transition (final).
OCR_TERMINAL_STATES: frozenset[str] = frozenset({OcrState.written_back.value})


def is_legal_ocr_transition(from_state: str, to_state: str) -> bool:
    """True iff ``from_state → to_state`` is one of the frozen legal transitions."""
    return (from_state, to_state) in OCR_TRANSITIONS


#: OCR human-confirmation field decisions (R6.2). Only ``accepted``/``corrected``
#: may enter a writeback mapping; ``rejected`` is a *decided* outcome that never
#: enters the mapping.
OCR_FIELD_DECISIONS: frozenset[str] = frozenset({"accepted", "corrected", "rejected"})
OCR_WRITEBACK_ELIGIBLE_DECISIONS: frozenset[str] = frozenset({"accepted", "corrected"})


# ─────────────────────────────────────────────────────────────────────────────
# 3) Persistent EvidenceRef physical model — R3.1 ; Properties P6/P7
#    EvidenceRef MUST be a persistent, queryable, retained row — not a per-request
#    DTO. This freezes the minimum required persistent columns.
# ─────────────────────────────────────────────────────────────────────────────

#: Minimum required columns for the persistent EvidenceRef table (design §4.4).
#: Wave 1 migrations MUST provide (at least) these; names may not silently drop
#: scope, target-binding, actor, intent or status.
EVIDENCE_REF_PERSISTENT_COLUMNS: frozenset[str] = frozenset({
    "id",                       # persistent reference id (NOT a transient DTO)
    "project_id",
    "audit_year",
    "source_type",
    "source_id",
    "source_version",
    "evidence_type",
    "evidence_id",              # target id
    "attachment_version_id",
    "target_version",
    "target_hash",
    "label",
    "context",
    "intent_hash",              # basis of active-intent idempotency (P7)
    "status",                   # active / inactive — not a DTO
    "created_by",               # actor (mirrors actor XOR block)
    "created_at",
})

#: EvidenceRef status is a closed set; only ``active`` participates in new
#: FormalOutput and the active-intent partial-unique index (P7).
EVIDENCE_REF_STATUSES: frozenset[str] = frozenset({"active", "inactive"})

#: The active-intent uniqueness key (partial unique WHERE status='active').
EVIDENCE_REF_ACTIVE_INTENT_UNIQUE: tuple[str, ...] = ("project_id", "audit_year", "intent_hash")

#: Columns present on the *current* DTO-only schema (app.schemas.evidence_ref).
#: Kept here so the regression guard can prove the DTO→persistent gap explicitly.
EVIDENCE_REF_LEGACY_DTO_FIELDS: frozenset[str] = frozenset({
    "evidence_type", "evidence_id", "project_id", "year",
    "label", "route", "hash", "version",
})


def evidence_ref_missing_persistent_columns(present_columns: set[str]) -> set[str]:
    """Return required persistent columns absent from ``present_columns``.

    Empty set ⇒ the (future) physical model satisfies the frozen shape.
    """
    return set(EVIDENCE_REF_PERSISTENT_COLUMNS) - set(present_columns)


# ─────────────────────────────────────────────────────────────────────────────
# 4) Legacy attachment ID resolution — R14 / design §4.1 ; Property P28 (support)
#    The old attachment ID is NOT assumed equal to a new aggregate root. Every
#    old ID resolves through the alias table to (root, definite version).
# ─────────────────────────────────────────────────────────────────────────────

class LegacyResolutionKind(str, Enum):
    root = "root"
    current_version = "current_version"
    historical_version = "historical_version"


LEGACY_RESOLUTION_KINDS: frozenset[str] = frozenset(k.value for k in LegacyResolutionKind)

#: Frozen columns of the ``legacy_attachment_alias`` table (design §4.1).
LEGACY_ALIAS_COLUMNS: frozenset[str] = frozenset({
    "old_attachment_id",        # PK
    "attachment_id",            # FK -> new aggregate root
    "attachment_version_id",    # FK -> definite version
    "project_id",
    "audit_year",
    "resolution_kind",
    "created_at",
})


@dataclass(frozen=True)
class LegacyResolution:
    """Result contract of ``LegacyAttachmentResolver`` — always returns BOTH the
    new aggregate root AND a definite version; never a silent "current version"."""

    old_attachment_id: str
    attachment_id: str          # resolved aggregate root
    attachment_version_id: str  # resolved definite version
    project_id: str
    audit_year: int
    resolution_kind: str
    # True only when the old ID was *explicitly created* as a new aggregate root.
    resolved_as_new_root: bool = False


def validate_legacy_resolution(res: LegacyResolution) -> Optional[str]:
    """Return ``None`` if a resolution satisfies the frozen contract, else a reason.

    Contract:
      * ``resolution_kind`` ∈ frozen set.
      * root + definite version are ALWAYS present (never resolve to an id only).
      * old ID is not assumed == root unless it was explicitly created as a new
        aggregate root (``resolved_as_new_root``). When it was NOT, the old ID
        and the resolved root must be treated as *distinct* identities — the API
        must not silently reinterpret an old ID as a "current version".
    """
    if res.resolution_kind not in LEGACY_RESOLUTION_KINDS:
        return f"resolution_kind must be one of {sorted(LEGACY_RESOLUTION_KINDS)}"
    if not res.attachment_id:
        return "resolution must yield an aggregate root attachment_id"
    if not res.attachment_version_id:
        return "resolution must yield a definite attachment_version_id"
    if not res.resolved_as_new_root and res.old_attachment_id == res.attachment_id:
        # Old-ID == new-root is only allowed when explicitly created as new root.
        return "old_attachment_id must not be assumed equal to the new aggregate root"
    return None


def is_valid_legacy_resolution(res: LegacyResolution) -> bool:
    return validate_legacy_resolution(res) is None
