"""Wave 0 frozen-contract tests — Task 1.3.

Feature: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R3, R5, R14
Properties (support): P3 (actor completeness), P9 (OCR closed state machine),
                      P6/P7 (persistent EvidenceRef), P28 (migration identity).

These tests FREEZE four P0 contracts and EMPIRICALLY document the current-state
gap so later waves cannot drift:

  1. actor_type user/service XOR + no-anonymous              (R1.4/R3.1/R5/R14.4)
  2. closed OCR enum + state machine                          (R5.2)
  3. persistent EvidenceRef physical model (not DTO-only)     (R3.1)
  4. legacy-ID resolution (old ID != new aggregate root)      (R14 / §4.1)

Wave 0 is a freeze: contracts live in `app.services.evidence_governance.contracts`
as pure predicates (no DB / no external engine). PG CHECK / trigger / partial
unique verification is deferred to Wave 1 (task 2.5). Property tests use the
global `fast` Hypothesis profile registered in conftest.
"""
from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.evidence_governance import contracts as C


# ─────────────────────────────────────────────────────────────────────────────
# 1) Actor XOR + no-anonymous  (R1.4/R3.1/R5/R14.4 ; P3)
# ─────────────────────────────────────────────────────────────────────────────
class TestActorXorContract:
    def test_actor_types_frozen(self):
        assert C.ACTOR_TYPES == frozenset({"user", "service"})

    def test_actor_columns_are_physical_xor_not_polymorphic(self):
        # The physical shape is three columns; a single polymorphic actor_id is
        # explicitly disallowed by the design.
        assert C.ACTOR_COLUMNS == (
            "actor_type", "actor_user_id", "actor_service_identity_id",
        )
        assert "actor_id" not in C.ACTOR_COLUMNS

    def test_valid_user_actor(self):
        assert C.is_valid_actor("user", "u-1", None)

    def test_valid_service_actor(self):
        assert C.is_valid_actor("service", None, "svc-1")

    @pytest.mark.parametrize(
        "atype,uid,sid,reason_kw",
        [
            (None, None, None, "actor_type"),        # anonymous -> forbidden
            ("", None, None, "actor_type"),
            ("user", None, None, "actor_user_id"),   # user without user id
            ("user", "u-1", "svc-1", "forbids"),     # both set
            ("service", None, None, "actor_service"),  # service without svc id
            ("service", "u-1", "svc-1", "forbids"),  # both ids on service
            ("service", "u-1", None, "actor_service"),  # user id + missing svc id
            ("robot", "u-1", None, "actor_type"),    # unknown type
        ],
    )
    def test_invalid_actor_tuples(self, atype, uid, sid, reason_kw):
        reason = C.validate_actor(atype, uid, sid)
        assert reason is not None
        assert reason_kw in reason

    def test_human_only_decision_fks_frozen(self):
        assert C.HUMAN_ONLY_DECISION_FKS == frozenset({
            "confirmed_by_user_id", "written_by_user_id",
            "closed_by_user_id", "released_by_user_id",
        })

    @given(
        atype=st.sampled_from(["user", "service"]),
        uid=st.one_of(st.none(), st.text(min_size=1, max_size=8)),
        sid=st.one_of(st.none(), st.text(min_size=1, max_size=8)),
    )
    def test_property_exactly_one_id_present_when_valid(self, atype, uid, sid):
        """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 3.

        A tuple is valid iff exactly one id column is populated and it matches
        the declared actor_type (never anonymous, never both).
        """
        valid = C.is_valid_actor(atype, uid, sid)
        if valid:
            populated = [x for x in (uid, sid) if x is not None]
            assert len(populated) == 1
            if atype == "user":
                assert uid is not None and sid is None
            else:
                assert sid is not None and uid is None


# ─────────────────────────────────────────────────────────────────────────────
# 2) Closed OCR enum + state machine  (R5.2 ; P9)
# ─────────────────────────────────────────────────────────────────────────────
class TestOcrStateMachineContract:
    def test_states_frozen(self):
        assert C.OCR_STATES == frozenset({
            "queued", "running", "awaiting_confirmation",
            "confirmed", "written_back", "failed",
        })

    def test_transitions_frozen(self):
        assert C.OCR_TRANSITIONS == frozenset({
            ("queued", "running"),
            ("running", "awaiting_confirmation"),
            ("awaiting_confirmation", "confirmed"),
            ("confirmed", "written_back"),
            ("queued", "failed"),
            ("running", "failed"),
            ("failed", "queued"),
        })

    def test_written_back_is_terminal(self):
        assert C.OCR_TERMINAL_STATES == frozenset({"written_back"})
        assert not any(f == "written_back" for (f, _t) in C.OCR_TRANSITIONS)

    def test_happy_path_is_legal(self):
        happy = [
            ("queued", "running"),
            ("running", "awaiting_confirmation"),
            ("awaiting_confirmation", "confirmed"),
            ("confirmed", "written_back"),
        ]
        assert all(C.is_legal_ocr_transition(f, t) for f, t in happy)

    def test_retry_only_from_failed(self):
        assert C.is_legal_ocr_transition("failed", "queued")
        # cannot resurrect a terminal or skip to queued from elsewhere
        assert not C.is_legal_ocr_transition("written_back", "queued")
        assert not C.is_legal_ocr_transition("confirmed", "queued")

    def test_writeback_decisions_frozen(self):
        assert C.OCR_FIELD_DECISIONS == frozenset({"accepted", "corrected", "rejected"})
        # rejected is decided but NEVER writeback-eligible (R6.2 / P12)
        assert C.OCR_WRITEBACK_ELIGIBLE_DECISIONS == frozenset({"accepted", "corrected"})
        assert "rejected" not in C.OCR_WRITEBACK_ELIGIBLE_DECISIONS

    @given(
        f=st.sampled_from(sorted(C.OCR_STATES)),
        t=st.sampled_from(sorted(C.OCR_STATES)),
    )
    def test_property_only_frozen_transitions_are_legal(self, f, t):
        """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 9.

        A transition is legal iff it is in the frozen set; nothing else.
        """
        assert C.is_legal_ocr_transition(f, t) == ((f, t) in C.OCR_TRANSITIONS)

    @given(s=st.text(max_size=20))
    def test_property_unknown_states_never_transition(self, s):
        if s not in C.OCR_STATES:
            assert not any(
                C.is_legal_ocr_transition(s, t) or C.is_legal_ocr_transition(t, s)
                for t in C.OCR_STATES
            )


# ─────────────────────────────────────────────────────────────────────────────
# 3) Persistent EvidenceRef physical model  (R3.1 ; P6/P7)
# ─────────────────────────────────────────────────────────────────────────────
class TestEvidenceRefPersistentContract:
    def test_required_persistent_columns_frozen(self):
        assert C.EVIDENCE_REF_PERSISTENT_COLUMNS == frozenset({
            "id", "project_id", "audit_year", "source_type", "source_id",
            "source_version", "evidence_type", "evidence_id",
            "attachment_version_id", "target_version", "target_hash",
            "label", "context", "intent_hash", "status", "created_by",
            "created_at",
        })

    def test_status_and_active_intent_key_frozen(self):
        assert C.EVIDENCE_REF_STATUSES == frozenset({"active", "inactive"})
        assert C.EVIDENCE_REF_ACTIVE_INTENT_UNIQUE == (
            "project_id", "audit_year", "intent_hash",
        )

    def test_current_evidence_ref_is_dto_only_gap_documented(self):
        """Empirical regression guard: prove the CURRENT EvidenceRef is a
        DTO-only Pydantic schema missing the persistent shape.

        When Wave 1 lands the persistent model, this test's ``missing`` set for
        the *DTO* stays non-empty (the DTO stays a DTO); the persistent ORM is
        checked separately in Wave 1 (task 2.5). This guard freezes the gap so
        the DTO is never mistaken for the source of truth.
        """
        from app.schemas.evidence_ref import EvidenceRef as DtoEvidenceRef

        dto_fields = set(DtoEvidenceRef.model_fields.keys())
        # The DTO fields are exactly the frozen legacy DTO field set.
        assert dto_fields == set(C.EVIDENCE_REF_LEGACY_DTO_FIELDS)

        missing = C.evidence_ref_missing_persistent_columns(dto_fields)
        # DTO-only today: at minimum it lacks persistent id, status, created_by,
        # intent_hash, target binding and audit_year.
        for required in ("id", "status", "created_by", "intent_hash",
                         "target_version", "target_hash", "audit_year"):
            assert required in missing

    def test_helper_reports_empty_when_shape_satisfied(self):
        assert C.evidence_ref_missing_persistent_columns(
            set(C.EVIDENCE_REF_PERSISTENT_COLUMNS)
        ) == set()


# ─────────────────────────────────────────────────────────────────────────────
# 4) Legacy attachment ID resolution  (R14 / §4.1 ; P28 support)
# ─────────────────────────────────────────────────────────────────────────────
class TestLegacyResolutionContract:
    def test_resolution_kinds_frozen(self):
        assert C.LEGACY_RESOLUTION_KINDS == frozenset({
            "root", "current_version", "historical_version",
        })

    def test_alias_columns_frozen(self):
        assert C.LEGACY_ALIAS_COLUMNS == frozenset({
            "old_attachment_id", "attachment_id", "attachment_version_id",
            "project_id", "audit_year", "resolution_kind", "created_at",
        })

    def test_valid_resolution_returns_root_and_definite_version(self):
        res = C.LegacyResolution(
            old_attachment_id="old-1",
            attachment_id="root-1",
            attachment_version_id="ver-1",
            project_id="p-1",
            audit_year=2025,
            resolution_kind="current_version",
        )
        assert C.is_valid_legacy_resolution(res)

    def test_old_id_not_assumed_equal_to_new_root(self):
        """Core R14/§4.1 rule: old ID == new aggregate root is only allowed when
        the old ID was *explicitly created* as a new root."""
        bad = C.LegacyResolution(
            old_attachment_id="same-id",
            attachment_id="same-id",   # silently assumed equal -> forbidden
            attachment_version_id="ver-1",
            project_id="p-1",
            audit_year=2025,
            resolution_kind="root",
            resolved_as_new_root=False,
        )
        reason = C.validate_legacy_resolution(bad)
        assert reason is not None and "not be assumed equal" in reason

        ok = C.LegacyResolution(
            old_attachment_id="same-id",
            attachment_id="same-id",
            attachment_version_id="ver-1",
            project_id="p-1",
            audit_year=2025,
            resolution_kind="root",
            resolved_as_new_root=True,   # explicitly created as new root -> allowed
        )
        assert C.is_valid_legacy_resolution(ok)

    def test_resolution_requires_definite_version(self):
        no_ver = C.LegacyResolution(
            old_attachment_id="old-2",
            attachment_id="root-2",
            attachment_version_id="",   # no definite version -> forbidden
            project_id="p-1",
            audit_year=2025,
            resolution_kind="root",
        )
        assert C.validate_legacy_resolution(no_ver) is not None

    @given(
        old_id=st.text(min_size=1, max_size=8),
        root=st.text(min_size=1, max_size=8),
        kind=st.sampled_from(sorted(C.LEGACY_RESOLUTION_KINDS)),
        as_new_root=st.booleans(),
    )
    def test_property_resolution_never_silently_reinterprets_old_id(
        self, old_id, root, kind, as_new_root
    ):
        """Feature: attachment-ocr-ai-evidence-governance-hardening, Property 28.

        A resolution with a definite version is valid iff its kind is frozen AND
        it does not silently equate old_id with the new root (unless explicitly
        created as a new root).
        """
        res = C.LegacyResolution(
            old_attachment_id=old_id,
            attachment_id=root,
            attachment_version_id="ver",
            project_id="p-1",
            audit_year=2025,
            resolution_kind=kind,
            resolved_as_new_root=as_new_root,
        )
        valid = C.is_valid_legacy_resolution(res)
        silent_equal = (old_id == root) and not as_new_root
        assert valid == (not silent_equal)


# ─────────────────────────────────────────────────────────────────────────────
# 5) Empirical current-state guard (documents the gap Task 1.3 froze)
# ─────────────────────────────────────────────────────────────────────────────
class TestCurrentStateEmpiricalGap:
    def test_current_attachment_created_by_is_nullable_no_actor_xor(self):
        """Wave 1 (Task 2.2 / V106) closed the actor-XOR gap on the Attachment aggregate.

        The frozen contract anticipated this transition. legacy ``created_by`` is
        retained as a read-only compatibility mirror (still nullable), and the
        frozen actor XOR columns are now present. The service layer enforces the
        no-anonymous XOR for new records; legacy rows are grandfathered (DB CHECK
        允许 actor_type IS NULL). Full physical-shape契约 → task 2.5.
        """
        from app.models.attachment_models import Attachment

        cols = Attachment.__table__.columns
        # legacy read-only mirror retained (not destructively removed)
        assert "created_by" in cols
        assert cols["created_by"].nullable is True
        # gap closed: frozen actor XOR columns now exist on the aggregate
        for actor_col in C.ACTOR_COLUMNS:
            assert actor_col in cols

    def test_current_ocr_status_is_freeform_no_check(self):
        """Prove today's ocr_status is a free-form String with no closed set."""
        from app.models.attachment_models import Attachment

        col = Attachment.__table__.columns["ocr_status"]
        # String type, not an Enum/closed set at the model level.
        assert col.type.__class__.__name__ in {"String", "VARCHAR"}
