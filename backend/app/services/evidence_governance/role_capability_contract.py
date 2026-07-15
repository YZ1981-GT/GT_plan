"""Frozen role & capability contract — Task 1.1 (Wave 0).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R5, R6, R10, R13
Design refs: §2.1 角色契约, §2.2 Capability 基线

This module is the *single source of truth* for the seven-value ``SystemRole``,
the frozen Chinese display names, and the high-risk capability baseline. Later
waves (migrations, ORM, capability guards, UI) implement against this contract
without drift; the frontend only displays/hides/explains and never carries
authorization.

Frozen invariants (locked by contract tests, changing any is a governance
decision requiring a spec update + updated tests):

* ``SystemRole`` == exactly seven values (design §2.1).
* Display names == design §2.1 Chinese names.
* ``ocr.retry`` baseline (design §2.2): auditor default-denied; manager/partner/
  admin permitted; qc/eqcr/readonly denied; Service Identity bounded-auto only.
* ``eqcr`` is an *independent legal role* — a system role in its own right and a
  valid EQCR candidate on its own; it is NEVER restricted to "only admin/partner".
* Service Identity can NEVER perform human confirmation, review-close,
  hold-release, QC/EQCR-complete or signoff.
* NO role — including ``admin`` and any Service Identity or emergency grant —
  can bypass Legal Hold (delete / purge / overwrite are zero-effect within an
  active hold).

The backend capability decision is authoritative. Role is resolved from the
database (``users.role``), never trusted from a JWT claim (see
``ROLE_SOURCE_OF_TRUTH``).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# 1) SystemRole — frozen seven values + Chinese display names (design §2.1)
# ─────────────────────────────────────────────────────────────────────────────

#: The frozen, ordered seven system roles. This is the canonical set the DB
#: ``userrole`` enum, the ORM ``UserRole`` enum and every capability decision
#: must agree with.
SYSTEM_ROLES: tuple[str, ...] = (
    "admin",
    "partner",
    "manager",
    "auditor",
    "qc",
    "eqcr",
    "readonly",
)

SYSTEM_ROLE_SET: frozenset[str] = frozenset(SYSTEM_ROLES)

#: Frozen Chinese display names (design §2.1). The backend owns these; the UI
#: only renders them. Divergence is drift.
SYSTEM_ROLE_DISPLAY_NAMES: dict[str, str] = {
    "admin": "管理员",
    "partner": "业务合伙人",
    "manager": "现场负责人",
    "auditor": "审计助理",
    "qc": "质量控制复核人",
    "eqcr": "EQCR技术复核人",
    "readonly": "只读用户",
}

#: Legal project-assignment roles. ``eqcr`` is an independent legal project role
#: (design §2.1); ``admin`` is a system-only role and is not assigned per project.
PROJECT_ROLES: tuple[str, ...] = (
    "partner",
    "manager",
    "auditor",
    "qc",
    "eqcr",
    "readonly",
)

PROJECT_ROLE_SET: frozenset[str] = frozenset(PROJECT_ROLES)

#: Role is authoritative from the database; it is never read from a JWT claim.
#: (Empirically verified: ``create_access_token`` embeds only sub/exp/type/jti,
#: and ``get_current_user`` re-resolves ``users.role`` from the database.)
ROLE_SOURCE_OF_TRUTH: str = "database"


def is_system_role(role: Optional[str]) -> bool:
    return role in SYSTEM_ROLE_SET


def display_name(role: Optional[str]) -> Optional[str]:
    """Return the frozen Chinese display name for a system role, else ``None``."""
    if role is None:
        return None
    return SYSTEM_ROLE_DISPLAY_NAMES.get(role)


# ─────────────────────────────────────────────────────────────────────────────
# 2) High-risk capability baseline (design §2.2)
# ─────────────────────────────────────────────────────────────────────────────

class Capability(str, Enum):
    """High-risk capability codes (design §2.2, "最少包括")."""

    attachment_create = "attachment.create"
    attachment_replace = "attachment.replace"
    attachment_deactivate = "attachment.deactivate"
    evidence_ref_create = "evidence_ref.create"
    evidence_ref_deactivate = "evidence_ref.deactivate"
    ocr_start = "ocr.start"
    ocr_retry = "ocr.retry"
    ocr_confirm = "ocr.confirm"
    ocr_writeback = "ocr.writeback"
    ai_generate = "ai.generate"
    ai_confirm = "ai.confirm"
    review_close = "review.close"
    qc_complete = "qc.complete"
    eqcr_complete = "eqcr.complete"
    archive_seal = "archive.seal"
    legal_hold_create = "legal_hold.create"
    legal_hold_release = "legal_hold.release"
    retention_purge = "retention.purge"
    #: Formal signoff of a workpaper/report (design §2.2 lists signoff among the
    #: actions a Service Identity can never perform).
    signoff = "signoff"


HIGH_RISK_CAPABILITIES: frozenset[str] = frozenset(c.value for c in Capability)


class Allow(str, Enum):
    """Baseline allowance for a (role, capability) cell.

    * ``denied``      — never permitted at the baseline.
    * ``allowed``     — permitted (project scope + capability guard still apply).
    * ``conditional`` — permitted only under a stated condition (e.g. "有目标编辑
      权时", "分配范围", "有界自动重试"); still counts as *permitted* for coverage.
    """

    denied = "denied"
    allowed = "allowed"
    conditional = "conditional"


#: Actor token for the non-human system worker (design §2.2 last column).
SERVICE_IDENTITY = "service"

# Condition notes (design §2.2 nuances) kept alongside conditional cells.
_C_TARGET_EDIT = "仅当对目标具编辑权"
_C_ASSIGNED_SCOPE = "仅分配范围内"
_C_BOUNDED_RETRY = "仅有界自动重试"
_C_APPROVED_TASK = "仅执行已批准任务"
_C_L1_REVIEW = "仅一级复核范围"
_C_PARTNER_SCOPE = "仅合伙人范围"
_C_HAS_CAPABILITY = "仅在具备该能力时"

# The frozen capability matrix. Every cell is (Allow, condition-note|None).
# Rows: SYSTEM_ROLES + SERVICE_IDENTITY. Columns: every HIGH_RISK_CAPABILITIES code.
# Derived directly from design §2.2. ``admin`` "管理" == allowed but still bound by
# scope/actor/reason/human-confirmation/Legal Hold/FormalOutput gates (never a bypass).
_D = (Allow.denied, None)


def _a(note: Optional[str] = None) -> tuple[Allow, Optional[str]]:
    return (Allow.allowed, note)


def _c(note: str) -> tuple[Allow, Optional[str]]:
    return (Allow.conditional, note)


CAPABILITY_MATRIX: dict[str, dict[str, tuple[Allow, Optional[str]]]] = {
    "auditor": {
        Capability.attachment_create.value: _c(_C_ASSIGNED_SCOPE),
        Capability.attachment_replace.value: _c("仅非受保护替换"),
        Capability.attachment_deactivate.value: _D,
        Capability.evidence_ref_create.value: _c(_C_ASSIGNED_SCOPE),
        Capability.evidence_ref_deactivate.value: _c(_C_ASSIGNED_SCOPE),
        Capability.ocr_start.value: _a(),
        Capability.ocr_retry.value: _D,  # 重试默认禁（需显式授予）
        Capability.ocr_confirm.value: _c(_C_TARGET_EDIT),
        Capability.ocr_writeback.value: _c(_C_TARGET_EDIT),
        Capability.ai_generate.value: _a(),
        Capability.ai_confirm.value: _c(_C_TARGET_EDIT),
        Capability.review_close.value: _D,
        Capability.qc_complete.value: _D,
        Capability.eqcr_complete.value: _D,
        Capability.archive_seal.value: _D,
        Capability.legal_hold_create.value: _D,
        Capability.legal_hold_release.value: _D,
        Capability.retention_purge.value: _D,
        Capability.signoff.value: _D,
    },
    "manager": {
        Capability.attachment_create.value: _a("项目读写"),
        Capability.attachment_replace.value: _a(),
        Capability.attachment_deactivate.value: _a(),
        Capability.evidence_ref_create.value: _a(),
        Capability.evidence_ref_deactivate.value: _a(),
        Capability.ocr_start.value: _a(),
        Capability.ocr_retry.value: _a(),
        Capability.ocr_confirm.value: _c(_C_TARGET_EDIT),
        Capability.ocr_writeback.value: _c(_C_TARGET_EDIT),
        Capability.ai_generate.value: _a(),
        Capability.ai_confirm.value: _c(_C_TARGET_EDIT),
        Capability.review_close.value: _c(_C_L1_REVIEW),
        Capability.qc_complete.value: _D,
        Capability.eqcr_complete.value: _D,
        Capability.archive_seal.value: _D,
        Capability.legal_hold_create.value: _D,
        Capability.legal_hold_release.value: _D,
        Capability.retention_purge.value: _D,
        Capability.signoff.value: _D,
    },
    "partner": {
        Capability.attachment_create.value: _a("项目读写"),
        Capability.attachment_replace.value: _a(),
        Capability.attachment_deactivate.value: _a(),
        Capability.evidence_ref_create.value: _a(),
        Capability.evidence_ref_deactivate.value: _a(),
        Capability.ocr_start.value: _a(),
        Capability.ocr_retry.value: _a(),
        Capability.ocr_confirm.value: _c(_C_TARGET_EDIT),
        Capability.ocr_writeback.value: _c(_C_TARGET_EDIT),
        Capability.ai_generate.value: _a(),
        Capability.ai_confirm.value: _c(_C_TARGET_EDIT),
        Capability.review_close.value: _c(_C_PARTNER_SCOPE),
        Capability.qc_complete.value: _D,  # partner: 查看/最终门禁, 非 QC 完成
        Capability.eqcr_complete.value: _D,
        Capability.archive_seal.value: _c(_C_HAS_CAPABILITY),
        Capability.legal_hold_create.value: _c(_C_HAS_CAPABILITY),
        Capability.legal_hold_release.value: _c(_C_HAS_CAPABILITY),
        Capability.retention_purge.value: _c(_C_HAS_CAPABILITY),
        Capability.signoff.value: _a(),
    },
    "qc": {
        Capability.attachment_create.value: _c("只读"),
        Capability.attachment_replace.value: _D,
        Capability.attachment_deactivate.value: _D,
        Capability.evidence_ref_create.value: _D,
        Capability.evidence_ref_deactivate.value: _D,
        Capability.ocr_start.value: _D,
        Capability.ocr_retry.value: _D,
        Capability.ocr_confirm.value: _D,
        Capability.ocr_writeback.value: _D,
        Capability.ai_generate.value: _D,
        Capability.ai_confirm.value: _D,
        Capability.review_close.value: _c("仅 QC 意见"),
        Capability.qc_complete.value: _a(),
        Capability.eqcr_complete.value: _D,
        Capability.archive_seal.value: _D,
        Capability.legal_hold_create.value: _D,
        Capability.legal_hold_release.value: _D,
        Capability.retention_purge.value: _D,
        Capability.signoff.value: _D,
    },
    "eqcr": {
        Capability.attachment_create.value: _c("只读"),
        Capability.attachment_replace.value: _D,
        Capability.attachment_deactivate.value: _D,
        Capability.evidence_ref_create.value: _D,
        Capability.evidence_ref_deactivate.value: _D,
        Capability.ocr_start.value: _D,
        Capability.ocr_retry.value: _D,
        Capability.ocr_confirm.value: _D,
        Capability.ocr_writeback.value: _D,
        Capability.ai_generate.value: _D,
        Capability.ai_confirm.value: _D,
        Capability.review_close.value: _c("仅 EQCR 意见"),
        Capability.qc_complete.value: _D,
        Capability.eqcr_complete.value: _a(),
        Capability.archive_seal.value: _D,
        Capability.legal_hold_create.value: _D,
        Capability.legal_hold_release.value: _D,
        Capability.retention_purge.value: _D,
        Capability.signoff.value: _D,
    },
    "admin": {
        Capability.attachment_create.value: _a("管理"),
        Capability.attachment_replace.value: _a("管理"),
        Capability.attachment_deactivate.value: _a("管理"),
        Capability.evidence_ref_create.value: _a("管理"),
        Capability.evidence_ref_deactivate.value: _a("管理"),
        Capability.ocr_start.value: _a("管理"),
        Capability.ocr_retry.value: _a("管理"),
        Capability.ocr_confirm.value: _c(_C_TARGET_EDIT),
        Capability.ocr_writeback.value: _c(_C_TARGET_EDIT),
        Capability.ai_generate.value: _a("管理"),
        Capability.ai_confirm.value: _c(_C_TARGET_EDIT),
        Capability.review_close.value: _a("管理"),
        Capability.qc_complete.value: _a("管理"),
        Capability.eqcr_complete.value: _a("管理"),
        Capability.archive_seal.value: _c(_C_HAS_CAPABILITY),
        Capability.legal_hold_create.value: _c(_C_HAS_CAPABILITY),
        Capability.legal_hold_release.value: _c(_C_HAS_CAPABILITY),
        Capability.retention_purge.value: _c(_C_HAS_CAPABILITY),
        Capability.signoff.value: _a("管理"),
    },
    "readonly": {c: _D for c in HIGH_RISK_CAPABILITIES},
    SERVICE_IDENTITY: {
        Capability.attachment_create.value: _c("任务 scope 受限"),
        Capability.attachment_replace.value: _D,
        Capability.attachment_deactivate.value: _D,
        Capability.evidence_ref_create.value: _c(_C_APPROVED_TASK),
        Capability.evidence_ref_deactivate.value: _D,
        Capability.ocr_start.value: _a(),
        Capability.ocr_retry.value: _c(_C_BOUNDED_RETRY),
        Capability.ocr_confirm.value: _D,      # human-confirm forbidden
        Capability.ocr_writeback.value: _D,    # human-approved writeback forbidden
        Capability.ai_generate.value: _c(_C_APPROVED_TASK),
        Capability.ai_confirm.value: _D,       # human-confirm forbidden
        Capability.review_close.value: _D,     # forbidden
        Capability.qc_complete.value: _D,      # forbidden
        Capability.eqcr_complete.value: _D,    # forbidden
        Capability.archive_seal.value: _c(_C_APPROVED_TASK),
        Capability.legal_hold_create.value: _D,
        Capability.legal_hold_release.value: _D,  # hold-release forbidden
        Capability.retention_purge.value: _D,
        Capability.signoff.value: _D,          # signoff forbidden
    },
}

#: Every actor row present in the matrix (all system roles + service identity).
CAPABILITY_MATRIX_ACTORS: frozenset[str] = frozenset(CAPABILITY_MATRIX)


# ─────────────────────────────────────────────────────────────────────────────
# 3) Service Identity forbidden actions (design §2.2)
# ─────────────────────────────────────────────────────────────────────────────

#: A Service Identity can NEVER perform these — human confirmation, review-close,
#: hold-release, QC/EQCR-complete or signoff (design §2.2).
SERVICE_IDENTITY_FORBIDDEN_CAPABILITIES: frozenset[str] = frozenset({
    Capability.ocr_confirm.value,     # human confirmation
    Capability.ocr_writeback.value,   # human-approved writeback
    Capability.ai_confirm.value,      # human confirmation
    Capability.review_close.value,
    Capability.legal_hold_release.value,
    Capability.qc_complete.value,
    Capability.eqcr_complete.value,
    Capability.signoff.value,
})


# ─────────────────────────────────────────────────────────────────────────────
# 4) Legal Hold — no bypass for any actor (design §2.2 / §5.5 / R13)
# ─────────────────────────────────────────────────────────────────────────────

#: Destructive operations that are zero-effect within an active Legal Hold.
LEGAL_HOLD_PROTECTED_OPERATIONS: frozenset[str] = frozenset({"delete", "purge", "overwrite"})

#: The set of actors allowed to bypass an active Legal Hold. Frozen EMPTY: no
#: role, admin, Service Identity or emergency grant may bypass (R13.2).
LEGAL_HOLD_BYPASS_ALLOWED_ACTORS: frozenset[str] = frozenset()


# ─────────────────────────────────────────────────────────────────────────────
# 5) EQCR independence (design §2.1)
# ─────────────────────────────────────────────────────────────────────────────

#: System roles that may act as an EQCR candidate. ``eqcr`` MUST be included on
#: its own — the "EQCR 候选仅 admin/partner" restriction is explicitly forbidden.
EQCR_CANDIDATE_SYSTEM_ROLES: frozenset[str] = frozenset({"eqcr", "admin", "partner"})


def is_eqcr_candidate(system_role: Optional[str]) -> bool:
    """True iff ``system_role`` may be an EQCR candidate.

    Locks EQCR as an *independent* role: a user whose system role is ``eqcr`` is
    always eligible, never gated behind admin/partner (design §2.1).
    """
    return system_role in EQCR_CANDIDATE_SYSTEM_ROLES


# ─────────────────────────────────────────────────────────────────────────────
# Predicates (the frozen decision surface)
# ─────────────────────────────────────────────────────────────────────────────

def _cell(actor: str, capability: str) -> tuple[Allow, Optional[str]]:
    row = CAPABILITY_MATRIX.get(actor)
    if row is None:
        return _D
    return row.get(capability, _D)


def allowance(actor: str, capability: str) -> Allow:
    """Return the baseline :class:`Allow` for ``(actor, capability)``.

    Unknown actor/capability defaults to :attr:`Allow.denied` (deny-by-default).
    """
    return _cell(actor, capability)[0]


def allowance_condition(actor: str, capability: str) -> Optional[str]:
    """Return the human-readable condition note for a conditional cell, else None."""
    return _cell(actor, capability)[1]


def is_permitted(actor: str, capability: str) -> bool:
    """True iff the baseline permits the capability (allowed or conditional)."""
    return allowance(actor, capability) in (Allow.allowed, Allow.conditional)


def is_forbidden(actor: str, capability: str) -> bool:
    """True iff the baseline forbids the capability outright."""
    return allowance(actor, capability) == Allow.denied


def service_identity_can(capability: str) -> bool:
    """True iff a Service Identity may (ever) perform ``capability``.

    Always False for the frozen forbidden set (human-confirm / review-close /
    hold-release / QC-EQCR-complete / signoff).
    """
    if capability in SERVICE_IDENTITY_FORBIDDEN_CAPABILITIES:
        return False
    return is_permitted(SERVICE_IDENTITY, capability)


def can_retry_ocr(actor: str) -> bool:
    """True iff ``actor`` may retry OCR at the baseline (``ocr.retry`` capability).

    auditor is default-denied; qc/eqcr/readonly denied; manager/partner/admin
    permitted; Service Identity permitted for bounded auto-retry only.
    """
    return is_permitted(actor, Capability.ocr_retry.value)


def can_bypass_legal_hold(actor: Optional[str]) -> bool:
    """Always False — no actor bypasses an active Legal Hold (R13.2 / P26)."""
    return actor in LEGAL_HOLD_BYPASS_ALLOWED_ACTORS


def legal_hold_permits(actor: Optional[str], operation: str) -> bool:
    """True iff ``actor`` may perform a *destructive* ``operation`` inside an
    active Legal Hold. Always False for protected operations regardless of actor
    (including admin / Service Identity / emergency)."""
    if operation in LEGAL_HOLD_PROTECTED_OPERATIONS:
        return False
    # Non-destructive operations (e.g. adding a new version) are out of scope of
    # the hold's zero-effect guarantee and are governed elsewhere.
    return True
