"""Frozen role & capability contract tests — Task 1.1 (Wave 0).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R5, R6, R10, R13
Design refs: §2.1 角色契约, §2.2 Capability 基线

Locks the frozen seven-value ``SystemRole``, the design Chinese display names,
and the four priority capability rules:
  * ``ocr.retry`` baseline authorization,
  * EQCR as an independent legal role,
  * Service Identity forbidden from human-confirm / review-close / hold-release /
    QC-EQCR-complete / signoff,
  * NO role (incl. admin / Service Identity / emergency) bypasses Legal Hold.

Property tests rely on the repo-global Hypothesis ``fast`` profile registered in
``backend/tests/conftest.py`` (no per-test ``max_examples`` override).
"""
from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.security import create_access_token, decode_token
from app.models.base import ProjectUserRole, UserRole
from app.services.evidence_governance import role_capability_contract as rc

FEATURE = "attachment-ocr-ai-evidence-governance-hardening"

# Actors used by property tests: every matrix actor plus junk/emergency tokens
# that must NEVER unlock a forbidden capability or a Legal Hold bypass.
_JUNK_ACTORS = ["emergency", "root", "superadmin", "", "SERVICE", "unknown", None]
_ALL_ACTOR_STRATEGY = st.sampled_from(sorted(rc.CAPABILITY_MATRIX_ACTORS) + _JUNK_ACTORS)


# ─────────────────────────────────────────────────────────────────────────────
# 1) SystemRole seven-value freeze + display names (design §2.1)
# ─────────────────────────────────────────────────────────────────────────────

def test_system_roles_are_exactly_seven_frozen_values():
    assert rc.SYSTEM_ROLES == (
        "admin", "partner", "manager", "auditor", "qc", "eqcr", "readonly",
    )
    assert len(rc.SYSTEM_ROLES) == 7
    assert len(rc.SYSTEM_ROLE_SET) == 7


def test_display_names_match_design_exactly():
    assert rc.SYSTEM_ROLE_DISPLAY_NAMES == {
        "admin": "管理员",
        "partner": "业务合伙人",
        "manager": "现场负责人",
        "auditor": "审计助理",
        "qc": "质量控制复核人",
        "eqcr": "EQCR技术复核人",
        "readonly": "只读用户",
    }
    # every system role has a display name; no extras
    assert set(rc.SYSTEM_ROLE_DISPLAY_NAMES) == rc.SYSTEM_ROLE_SET


def test_orm_userrole_enum_matches_frozen_system_roles():
    """The backend ORM enum must equal the frozen seven-value contract."""
    orm_values = {r.value for r in UserRole}
    assert orm_values == rc.SYSTEM_ROLE_SET, (
        f"UserRole drift: {orm_values ^ rc.SYSTEM_ROLE_SET}"
    )


def test_orm_projectuserrole_enum_matches_frozen_project_roles():
    orm_values = {r.value for r in ProjectUserRole}
    assert orm_values == rc.PROJECT_ROLE_SET, (
        f"ProjectUserRole drift: {orm_values ^ rc.PROJECT_ROLE_SET}"
    )


def test_project_roles_include_eqcr_and_exclude_admin():
    assert "eqcr" in rc.PROJECT_ROLE_SET
    # admin is a system-only role, never a per-project assignment role
    assert "admin" not in rc.PROJECT_ROLE_SET


# ─────────────────────────────────────────────────────────────────────────────
# 2) JWT role claim contract — role is DB-authoritative, never trusted from token
# ─────────────────────────────────────────────────────────────────────────────

def test_role_source_of_truth_is_database():
    assert rc.ROLE_SOURCE_OF_TRUTH == "database"


def test_access_token_carries_no_role_claim():
    """Empirical lock: JWT payload has no role claim; role is re-resolved from DB."""
    token = create_access_token({"sub": "00000000-0000-0000-0000-000000000001"})
    payload = decode_token(token)
    assert "role" not in payload
    assert payload["sub"] == "00000000-0000-0000-0000-000000000001"
    assert payload["type"] == "access"


# ─────────────────────────────────────────────────────────────────────────────
# 3) ocr.retry baseline authorization (design §2.2)
# ─────────────────────────────────────────────────────────────────────────────

_OCR_RETRY_PERMITTED = ["manager", "partner", "admin"]
_OCR_RETRY_DENIED = ["auditor", "qc", "eqcr", "readonly"]


@pytest.mark.parametrize("role", _OCR_RETRY_PERMITTED)
def test_ocr_retry_permitted_roles(role):
    assert rc.can_retry_ocr(role) is True
    assert rc.is_permitted(role, rc.Capability.ocr_retry.value)


@pytest.mark.parametrize("role", _OCR_RETRY_DENIED)
def test_ocr_retry_denied_roles(role):
    assert rc.can_retry_ocr(role) is False
    assert rc.is_forbidden(role, rc.Capability.ocr_retry.value)


def test_ocr_retry_auditor_default_denied():
    """auditor 可启动 OCR 但重试默认禁（design §2.2 "启动；重试默认禁"）。"""
    assert rc.is_permitted("auditor", rc.Capability.ocr_start.value)
    assert rc.is_forbidden("auditor", rc.Capability.ocr_retry.value)


def test_ocr_retry_service_identity_bounded_only():
    """Service Identity may retry only as bounded auto-retry (conditional)."""
    assert rc.can_retry_ocr(rc.SERVICE_IDENTITY) is True
    assert rc.allowance(rc.SERVICE_IDENTITY, rc.Capability.ocr_retry.value) is rc.Allow.conditional
    assert rc.allowance_condition(rc.SERVICE_IDENTITY, rc.Capability.ocr_retry.value)


# ─────────────────────────────────────────────────────────────────────────────
# 4) EQCR is an independent legal role (design §2.1)
# ─────────────────────────────────────────────────────────────────────────────

def test_eqcr_is_independent_system_and_project_role():
    assert "eqcr" in rc.SYSTEM_ROLE_SET
    assert "eqcr" in rc.PROJECT_ROLE_SET
    assert "eqcr" in rc.CAPABILITY_MATRIX_ACTORS


def test_eqcr_candidate_not_restricted_to_admin_partner():
    """The "EQCR 候选仅 admin/partner" restriction is forbidden — eqcr qualifies itself."""
    assert rc.is_eqcr_candidate("eqcr") is True
    assert rc.is_eqcr_candidate("admin") is True
    assert rc.is_eqcr_candidate("partner") is True
    # non-EQCR roles are not EQCR candidates
    for role in ("manager", "auditor", "qc", "readonly"):
        assert rc.is_eqcr_candidate(role) is False


def test_eqcr_complete_is_eqcr_exclusive():
    """eqcr.complete permitted only for eqcr (+ admin manage); denied elsewhere."""
    assert rc.is_permitted("eqcr", rc.Capability.eqcr_complete.value)
    assert rc.is_permitted("admin", rc.Capability.eqcr_complete.value)
    for actor in ("auditor", "manager", "partner", "qc", "readonly", rc.SERVICE_IDENTITY):
        assert rc.is_forbidden(actor, rc.Capability.eqcr_complete.value), actor


def test_qc_complete_is_qc_exclusive():
    assert rc.is_permitted("qc", rc.Capability.qc_complete.value)
    assert rc.is_permitted("admin", rc.Capability.qc_complete.value)
    for actor in ("auditor", "manager", "partner", "eqcr", "readonly", rc.SERVICE_IDENTITY):
        assert rc.is_forbidden(actor, rc.Capability.qc_complete.value), actor


# ─────────────────────────────────────────────────────────────────────────────
# 5) Service Identity forbidden actions (design §2.2)
# ─────────────────────────────────────────────────────────────────────────────

def test_service_identity_forbidden_set_covers_required_actions():
    required = {
        rc.Capability.ocr_confirm.value,
        rc.Capability.ocr_writeback.value,
        rc.Capability.ai_confirm.value,
        rc.Capability.review_close.value,
        rc.Capability.legal_hold_release.value,
        rc.Capability.qc_complete.value,
        rc.Capability.eqcr_complete.value,
        rc.Capability.signoff.value,
    }
    assert required <= rc.SERVICE_IDENTITY_FORBIDDEN_CAPABILITIES


@pytest.mark.parametrize("capability", sorted(rc.SERVICE_IDENTITY_FORBIDDEN_CAPABILITIES))
def test_service_identity_cannot_do_forbidden_capability(capability):
    assert rc.service_identity_can(capability) is False
    assert rc.is_forbidden(rc.SERVICE_IDENTITY, capability)


# ─────────────────────────────────────────────────────────────────────────────
# 6) Legal Hold — no bypass for any actor incl. admin (design §2.2 / R13)
# ─────────────────────────────────────────────────────────────────────────────

def test_legal_hold_bypass_allowlist_is_empty():
    assert rc.LEGAL_HOLD_BYPASS_ALLOWED_ACTORS == frozenset()


@pytest.mark.parametrize(
    "actor",
    ["admin", "partner", "manager", "auditor", "qc", "eqcr", "readonly",
     rc.SERVICE_IDENTITY, "emergency", "root", None],
)
def test_no_actor_can_bypass_legal_hold(actor):
    assert rc.can_bypass_legal_hold(actor) is False


@pytest.mark.parametrize(
    "actor",
    ["admin", "partner", "manager", "auditor", "qc", "eqcr", "readonly",
     rc.SERVICE_IDENTITY, "emergency"],
)
@pytest.mark.parametrize("operation", sorted(rc.LEGAL_HOLD_PROTECTED_OPERATIONS))
def test_legal_hold_blocks_all_destructive_ops_for_all_actors(actor, operation):
    assert rc.legal_hold_permits(actor, operation) is False


# ─────────────────────────────────────────────────────────────────────────────
# 7) Matrix structural consistency
# ─────────────────────────────────────────────────────────────────────────────

def test_matrix_actors_are_system_roles_plus_service_identity():
    assert rc.CAPABILITY_MATRIX_ACTORS == rc.SYSTEM_ROLE_SET | {rc.SERVICE_IDENTITY}


def test_every_actor_row_covers_every_capability():
    for actor, row in rc.CAPABILITY_MATRIX.items():
        assert set(row) == rc.HIGH_RISK_CAPABILITIES, f"{actor} missing capabilities"


def test_readonly_is_denied_all_high_risk_capabilities():
    for cap in rc.HIGH_RISK_CAPABILITIES:
        assert rc.is_forbidden("readonly", cap), cap


def test_unknown_actor_or_capability_denied_by_default():
    assert rc.is_forbidden("no-such-role", rc.Capability.ocr_retry.value)
    assert rc.is_forbidden("admin", "no.such.capability")
    assert rc.allowance("ghost", "ghost.cap") is rc.Allow.denied


# ─────────────────────────────────────────────────────────────────────────────
# 8) Property-based locks (global fast profile — no max_examples override)
# ─────────────────────────────────────────────────────────────────────────────

@given(actor=_ALL_ACTOR_STRATEGY)
def test_property_no_actor_ever_bypasses_legal_hold(actor):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property P26 (support).

    No actor — role, admin, service, junk or emergency — bypasses a Legal Hold,
    and every protected destructive operation is zero-effect for every actor.
    """
    assert rc.can_bypass_legal_hold(actor) is False
    for op in rc.LEGAL_HOLD_PROTECTED_OPERATIONS:
        assert rc.legal_hold_permits(actor, op) is False


@given(capability=st.sampled_from(sorted(rc.SERVICE_IDENTITY_FORBIDDEN_CAPABILITIES)))
def test_property_service_identity_never_performs_forbidden(capability):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property (Service Identity).

    A Service Identity can never perform any forbidden capability, regardless of
    the matrix cell.
    """
    assert rc.service_identity_can(capability) is False


@given(actor=_ALL_ACTOR_STRATEGY)
def test_property_ocr_retry_only_for_authorized_actors(actor):
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Property P10 (support).

    ``can_retry_ocr`` is True only for the authorized baseline set; everyone else
    (incl. auditor default, qc/eqcr/readonly, junk) is denied.
    """
    authorized = {"manager", "partner", "admin", rc.SERVICE_IDENTITY}
    assert rc.can_retry_ocr(actor) is (actor in authorized)
