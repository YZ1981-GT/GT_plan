"""Tests for ReviewEvidenceService — Task 6.5, Wave 5.

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R9, R10, R12
Design: §4.6, §5.4

Properties validated:
  P21: Blocking Review 仅在权限、充分说明、至少一个有效非 stale ref 同时满足时关闭
  P22: 已关闭意见依据失效后进入待重新复核并阻断 QC/EQCR/partner gate
"""

from __future__ import annotations

import uuid

import pytest
from hypothesis import given, assume
from hypothesis import strategies as st

from app.services.evidence_governance.frozen_contracts import ActorContext
from app.services.evidence_governance.review_evidence_service import (
    CloseRejectReason,
    EvidenceDisplayItem,
    ReviewEvidenceService,
    ReviewEvidenceSnapshot,
    ReviewOpinion,
    ReviewStatus,
    BLOCKING_SEVERITIES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Strategies
# ─────────────────────────────────────────────────────────────────────────────

uuid_st = st.text(
    alphabet="0123456789abcdef-",
    min_size=36,
    max_size=36,
).map(lambda _: str(uuid.uuid4()))

evidence_ref_st = st.fixed_dictionaries({
    "evidence_ref_id": uuid_st,
    "evidence_type": st.sampled_from(["attachment_version", "ocr_result", "citation"]),
    "target_version": st.integers(min_value=1, max_value=100),
    "target_hash": st.text(alphabet="0123456789abcdef", min_size=64, max_size=64),
    "locator": st.text(min_size=1, max_size=50),
    "ocr_confirmed": st.booleans(),
    "ai_confirmed": st.booleans(),
    "stale": st.booleans(),
})

non_stale_ref_st = evidence_ref_st.map(lambda d: {**d, "stale": False})
stale_ref_st = evidence_ref_st.map(lambda d: {**d, "stale": True})

severity_st = st.sampled_from(["low", "medium", "high", "critical"])
explanation_st = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())
empty_explanation_st = st.sampled_from(["", "   ", "\t", "\n"])


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def service() -> ReviewEvidenceService:
    return ReviewEvidenceService()


@pytest.fixture
def sample_opinion(service: ReviewEvidenceService) -> ReviewOpinion:
    """A blocking review opinion (high severity, open)."""
    return service.create_opinion(
        project_id=str(uuid.uuid4()),
        audit_year=2025,
        target_type="workpaper",
        target_id=str(uuid.uuid4()),
        severity="high",
        content="发现重大错报",
        created_by_user_id=str(uuid.uuid4()),
        evidence_refs=[{
            "evidence_ref_id": str(uuid.uuid4()),
            "evidence_type": "attachment_version",
            "target_version": 1,
            "target_hash": "a" * 64,
            "locator": "storage://att/v1",
            "ocr_confirmed": True,
            "ai_confirmed": False,
            "stale": False,
        }],
    )


def make_human_actor() -> ActorContext:
    return ActorContext.for_user(uuid.uuid4())


def make_service_actor() -> ActorContext:
    return ActorContext.for_service(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — ReviewEvidenceSnapshot
# ─────────────────────────────────────────────────────────────────────────────


class TestReviewEvidenceSnapshot:
    """Tests for snapshot creation and immutability."""

    def test_create_snapshot(self, service: ReviewEvidenceService):
        snap = service.create_snapshot(
            evidence_ref_id="ref-1",
            evidence_type="attachment_version",
            target_version=3,
            target_hash="b" * 64,
            locator="storage://att/v3",
            ocr_confirmed=True,
            ai_confirmed=False,
            stale=False,
        )
        assert snap.evidence_ref_id == "ref-1"
        assert snap.target_version == 3
        assert snap.target_hash == "b" * 64
        assert snap.locator == "storage://att/v3"
        assert snap.ocr_confirmed is True
        assert snap.ai_confirmed is False
        assert snap.stale is False
        assert snap.snapshot_id  # UUID assigned
        assert snap.snapshot_at  # timestamp assigned

    def test_snapshot_is_frozen(self, service: ReviewEvidenceService):
        snap = service.create_snapshot(
            evidence_ref_id="ref-1",
            evidence_type="attachment_version",
            target_version=1,
            target_hash="c" * 64,
            locator="loc",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            snap.target_version = 99  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — create_opinion
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateOpinion:
    """Tests for opinion creation with evidence snapshot freezing."""

    def test_create_opinion_with_evidence(self, service: ReviewEvidenceService):
        opinion = service.create_opinion(
            project_id="proj-1",
            audit_year=2025,
            target_type="workpaper",
            target_id="wp-1",
            severity="high",
            content="测试意见",
            created_by_user_id="user-1",
            evidence_refs=[{
                "evidence_ref_id": "ref-1",
                "evidence_type": "attachment_version",
                "target_version": 2,
                "target_hash": "d" * 64,
                "locator": "loc-1",
                "stale": False,
            }],
        )
        assert opinion.status == ReviewStatus.open.value
        assert opinion.severity == "high"
        assert opinion.is_blocking is True
        assert len(opinion.evidence_snapshots) == 1
        assert opinion.evidence_snapshots[0].target_version == 2
        assert len(opinion.history) == 1
        assert opinion.history[0]["action"] == "created"

    def test_create_opinion_without_evidence(self, service: ReviewEvidenceService):
        opinion = service.create_opinion(
            project_id="proj-1",
            audit_year=2025,
            target_type="workpaper",
            target_id="wp-1",
            severity="low",
            content="小意见",
            created_by_user_id="user-1",
        )
        assert opinion.status == ReviewStatus.open.value
        assert opinion.is_blocking is False  # low severity
        assert len(opinion.evidence_snapshots) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — close_review gate (P21)
# ─────────────────────────────────────────────────────────────────────────────


class TestCloseReviewGate:
    """Tests for close_review gate logic (P21)."""

    def test_close_succeeds_all_conditions_met(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        result = service.close_review(
            sample_opinion,
            closing_explanation="问题已解决，证据充分",
            closer_user_id=str(uuid.uuid4()),
            actor=make_human_actor(),
            has_close_permission=True,
            current_evidence_refs=[{
                "evidence_ref_id": str(uuid.uuid4()),
                "evidence_type": "attachment_version",
                "target_version": 1,
                "target_hash": "e" * 64,
                "locator": "loc",
                "stale": False,
            }],
        )
        assert result.allowed is True
        assert sample_opinion.status == ReviewStatus.closed.value
        assert sample_opinion.closed_by_user_id is not None
        assert sample_opinion.closing_explanation == "问题已解决，证据充分"
        assert len(sample_opinion.close_snapshots) == 1

    def test_close_rejected_no_permission(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        result = service.close_review(
            sample_opinion,
            closing_explanation="说明",
            closer_user_id=str(uuid.uuid4()),
            actor=make_human_actor(),
            has_close_permission=False,
            current_evidence_refs=[{
                "evidence_ref_id": "r1",
                "evidence_type": "att",
                "target_version": 1,
                "target_hash": "f" * 64,
                "locator": "l",
                "stale": False,
            }],
        )
        assert result.allowed is False
        assert CloseRejectReason.permission_denied in result.reject_reasons
        assert sample_opinion.status == ReviewStatus.open.value

    def test_close_rejected_empty_explanation(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        result = service.close_review(
            sample_opinion,
            closing_explanation="",
            closer_user_id=str(uuid.uuid4()),
            actor=make_human_actor(),
            has_close_permission=True,
            current_evidence_refs=[{
                "evidence_ref_id": "r1",
                "evidence_type": "att",
                "target_version": 1,
                "target_hash": "f" * 64,
                "locator": "l",
                "stale": False,
            }],
        )
        assert result.allowed is False
        assert CloseRejectReason.insufficient_explanation in result.reject_reasons
        assert sample_opinion.status == ReviewStatus.open.value

    def test_close_rejected_all_refs_stale(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        result = service.close_review(
            sample_opinion,
            closing_explanation="说明",
            closer_user_id=str(uuid.uuid4()),
            actor=make_human_actor(),
            has_close_permission=True,
            current_evidence_refs=[{
                "evidence_ref_id": "r1",
                "evidence_type": "att",
                "target_version": 1,
                "target_hash": "f" * 64,
                "locator": "l",
                "stale": True,
            }],
        )
        assert result.allowed is False
        assert CloseRejectReason.no_valid_evidence_ref in result.reject_reasons

    def test_close_rejected_no_refs(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        result = service.close_review(
            sample_opinion,
            closing_explanation="说明",
            closer_user_id=str(uuid.uuid4()),
            actor=make_human_actor(),
            has_close_permission=True,
            current_evidence_refs=[],
        )
        assert result.allowed is False
        assert CloseRejectReason.no_valid_evidence_ref in result.reject_reasons

    def test_close_rejected_service_identity(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        result = service.close_review(
            sample_opinion,
            closing_explanation="说明",
            closer_user_id=str(uuid.uuid4()),
            actor=make_service_actor(),
            has_close_permission=True,
            current_evidence_refs=[{
                "evidence_ref_id": "r1",
                "evidence_type": "att",
                "target_version": 1,
                "target_hash": "f" * 64,
                "locator": "l",
                "stale": False,
            }],
        )
        assert result.allowed is False
        assert CloseRejectReason.service_identity_forbidden in result.reject_reasons

    def test_close_preserves_history_on_rejection(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        initial_history_len = len(sample_opinion.history)
        service.close_review(
            sample_opinion,
            closing_explanation="",
            closer_user_id="user-1",
            actor=make_human_actor(),
            has_close_permission=False,
            current_evidence_refs=[],
        )
        # History should have a rejection entry
        assert len(sample_opinion.history) == initial_history_len + 1
        assert sample_opinion.history[-1]["action"] == "close_rejected"


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — auto_reopen (P22)
# ─────────────────────────────────────────────────────────────────────────────


class TestAutoReopen:
    """Tests for auto-reopen when evidence is invalidated (P22)."""

    def test_reopen_closed_opinion(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        # First close it
        service.close_review(
            sample_opinion,
            closing_explanation="resolved",
            closer_user_id=str(uuid.uuid4()),
            actor=make_human_actor(),
            has_close_permission=True,
            current_evidence_refs=[{
                "evidence_ref_id": "r1",
                "evidence_type": "att",
                "target_version": 1,
                "target_hash": "f" * 64,
                "locator": "l",
                "stale": False,
            }],
        )
        assert sample_opinion.status == ReviewStatus.closed.value

        # Now auto-reopen
        reopened = service.auto_reopen(
            sample_opinion,
            reason="evidence_replaced",
            invalidated_ref_ids=["r1"],
        )
        assert reopened is True
        assert sample_opinion.status == ReviewStatus.re_review_required.value
        assert sample_opinion.history[-1]["action"] == "auto_reopened"
        assert sample_opinion.history[-1]["reason"] == "evidence_replaced"

    def test_reopen_already_open_is_noop(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        assert sample_opinion.status == ReviewStatus.open.value
        reopened = service.auto_reopen(sample_opinion, reason="stale")
        assert reopened is False
        assert sample_opinion.status == ReviewStatus.open.value

    def test_reopen_already_re_review_is_noop(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        # Close then reopen
        service.close_review(
            sample_opinion,
            closing_explanation="ok",
            closer_user_id=str(uuid.uuid4()),
            actor=make_human_actor(),
            has_close_permission=True,
            current_evidence_refs=[{
                "evidence_ref_id": "r1",
                "evidence_type": "att",
                "target_version": 1,
                "target_hash": "f" * 64,
                "locator": "l",
                "stale": False,
            }],
        )
        service.auto_reopen(sample_opinion, reason="stale")
        assert sample_opinion.status == ReviewStatus.re_review_required.value

        # Second reopen is noop
        reopened = service.auto_reopen(sample_opinion, reason="replaced")
        assert reopened is False


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — completion blocking
# ─────────────────────────────────────────────────────────────────────────────


class TestCompletionBlocking:
    """Tests for QC/EQCR/partner completion blocking."""

    def test_blocked_when_re_review_exists(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        # Close and reopen
        service.close_review(
            sample_opinion,
            closing_explanation="ok",
            closer_user_id=str(uuid.uuid4()),
            actor=make_human_actor(),
            has_close_permission=True,
            current_evidence_refs=[{
                "evidence_ref_id": "r1",
                "evidence_type": "att",
                "target_version": 1,
                "target_hash": "f" * 64,
                "locator": "l",
                "stale": False,
            }],
        )
        service.auto_reopen(sample_opinion, reason="stale")

        blocked = service.check_completion_blocked([sample_opinion])
        assert blocked is True

    def test_not_blocked_when_all_closed(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        service.close_review(
            sample_opinion,
            closing_explanation="ok",
            closer_user_id=str(uuid.uuid4()),
            actor=make_human_actor(),
            has_close_permission=True,
            current_evidence_refs=[{
                "evidence_ref_id": "r1",
                "evidence_type": "att",
                "target_version": 1,
                "target_hash": "f" * 64,
                "locator": "l",
                "stale": False,
            }],
        )
        blocked = service.check_completion_blocked([sample_opinion])
        assert blocked is False

    def test_not_blocked_when_no_opinions(self, service: ReviewEvidenceService):
        blocked = service.check_completion_blocked([])
        assert blocked is False

    def test_blocked_filters_by_target(
        self, service: ReviewEvidenceService
    ):
        op1 = service.create_opinion(
            project_id="p1",
            audit_year=2025,
            target_type="workpaper",
            target_id="wp-1",
            severity="high",
            content="test",
            created_by_user_id="u1",
        )
        op1.status = ReviewStatus.re_review_required.value

        # Match target
        blocked = service.check_completion_blocked(
            [op1], target_type="workpaper", target_id="wp-1"
        )
        assert blocked is True

        # Non-match target
        blocked = service.check_completion_blocked(
            [op1], target_type="workpaper", target_id="wp-999"
        )
        assert blocked is False


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — evidence display (R10.4)
# ─────────────────────────────────────────────────────────────────────────────


class TestEvidenceDisplay:
    """Tests for QC/EQCR evidence display."""

    def test_display_from_snapshots(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        items = service.get_evidence_display(sample_opinion)
        assert len(items) == 1
        item = items[0]
        assert item.source_version == 1
        assert item.content_hash == "a" * 64
        assert item.locator == "storage://att/v1"

    def test_display_merges_current_state(
        self, service: ReviewEvidenceService, sample_opinion: ReviewOpinion
    ):
        ref_id = sample_opinion.evidence_snapshots[0].evidence_ref_id
        current = [{
            "evidence_ref_id": ref_id,
            "ocr_confirmed": True,
            "ocr_confirmation_at": "2025-01-01T00:00:00Z",
            "ocr_confirmed_by": "user-ocr",
            "ai_confirmed": True,
            "ai_confirmation_at": "2025-01-02T00:00:00Z",
            "ai_confirmed_by": "user-ai",
            "stale": True,
            "stale_path": ["node-1", "node-2"],
            "locator": "storage://att/v2",
            "locator_type": "download_url",
        }]
        items = service.get_evidence_display(
            sample_opinion, current_evidence_state=current
        )
        assert len(items) == 1
        item = items[0]
        assert item.ocr_confirmed is True
        assert item.ocr_confirmed_by == "user-ocr"
        assert item.ai_confirmed is True
        assert item.is_stale is True
        assert item.stale_path == ["node-1", "node-2"]
        assert item.locator == "storage://att/v2"
        assert item.locator_type == "download_url"


# ─────────────────────────────────────────────────────────────────────────────
# PBT — P21 Blocking Review 关闭门禁
# ─────────────────────────────────────────────────────────────────────────────


class TestPropertyP21BlockingReviewCloseGate:
    """**Validates: Requirements 10.2**

    P21: Blocking_Review 仅在权限、充分说明、至少一个有效非 stale ref 同时满足时关闭。
    """

    @given(
        has_perm=st.booleans(),
        has_explanation=st.booleans(),
        has_valid_ref=st.booleans(),
        is_service=st.booleans(),
    )
    def test_close_gate_p21(
        self,
        has_perm: bool,
        has_explanation: bool,
        has_valid_ref: bool,
        is_service: bool,
    ):
        """Close succeeds iff ALL four conditions hold: human + permission + explanation + valid ref."""
        service = ReviewEvidenceService()
        opinion = service.create_opinion(
            project_id="p1",
            audit_year=2025,
            target_type="workpaper",
            target_id="wp-1",
            severity="critical",
            content="blocking opinion",
            created_by_user_id="u1",
        )

        actor = make_service_actor() if is_service else make_human_actor()
        explanation = "充分说明" if has_explanation else ""
        refs: list[dict] = []
        if has_valid_ref:
            refs = [{
                "evidence_ref_id": "r1",
                "evidence_type": "attachment_version",
                "target_version": 1,
                "target_hash": "a" * 64,
                "locator": "loc",
                "stale": False,
            }]
        else:
            refs = [{
                "evidence_ref_id": "r1",
                "evidence_type": "attachment_version",
                "target_version": 1,
                "target_hash": "a" * 64,
                "locator": "loc",
                "stale": True,
            }]

        result = service.evaluate_close_gate(
            opinion,
            closing_explanation=explanation,
            closer_user_id="u2",
            actor=actor,
            has_close_permission=has_perm,
            current_evidence_refs=refs,
        )

        # P21 invariant: all four must be True for allowed
        all_met = (not is_service) and has_perm and has_explanation and has_valid_ref
        assert result.allowed == all_met, (
            f"Expected allowed={all_met} but got {result.allowed}. "
            f"is_service={is_service}, perm={has_perm}, "
            f"explanation={has_explanation}, valid_ref={has_valid_ref}"
        )

    @given(severity=st.sampled_from(["low", "medium", "high", "critical"]))
    def test_blocking_only_high_critical(self, severity: str):
        """Only high/critical severity reviews are blocking."""
        service = ReviewEvidenceService()
        opinion = service.create_opinion(
            project_id="p1",
            audit_year=2025,
            target_type="workpaper",
            target_id="wp-1",
            severity=severity,
            content="test",
            created_by_user_id="u1",
        )
        expected_blocking = severity in BLOCKING_SEVERITIES
        assert opinion.is_blocking == expected_blocking


# ─────────────────────────────────────────────────────────────────────────────
# PBT — P22 复核自动重开
# ─────────────────────────────────────────────────────────────────────────────


class TestPropertyP22AutoReopen:
    """**Validates: Requirements 10.3**

    P22: 已关闭意见依据失效后为 re_review_required，QC/EQCR/partner gate 拒绝。
    """

    @given(
        invalidation_reason=st.sampled_from([
            "evidence_replaced",
            "evidence_deactivated",
            "evidence_stale",
        ]),
    )
    def test_auto_reopen_blocks_completion_p22(self, invalidation_reason: str):
        """After auto-reopen, QC/EQCR/partner completion is always blocked."""
        service = ReviewEvidenceService()
        opinion = service.create_opinion(
            project_id="p1",
            audit_year=2025,
            target_type="workpaper",
            target_id="wp-1",
            severity="high",
            content="blocking",
            created_by_user_id="u1",
        )

        # Close the opinion
        service.close_review(
            opinion,
            closing_explanation="resolved",
            closer_user_id="u2",
            actor=make_human_actor(),
            has_close_permission=True,
            current_evidence_refs=[{
                "evidence_ref_id": "r1",
                "evidence_type": "att",
                "target_version": 1,
                "target_hash": "b" * 64,
                "locator": "l",
                "stale": False,
            }],
        )
        assert opinion.status == ReviewStatus.closed.value

        # Auto-reopen due to evidence invalidation
        reopened = service.auto_reopen(opinion, reason=invalidation_reason)
        assert reopened is True
        assert opinion.status == ReviewStatus.re_review_required.value

        # P22 invariant: completion is blocked
        blocked = service.check_completion_blocked([opinion])
        assert blocked is True, (
            f"Expected completion blocked after auto_reopen "
            f"with reason={invalidation_reason}"
        )

    @given(n_opinions=st.integers(min_value=1, max_value=5))
    def test_any_re_review_blocks_all(self, n_opinions: int):
        """Even one re_review_required opinion blocks completion."""
        service = ReviewEvidenceService()
        opinions = []
        for i in range(n_opinions):
            op = service.create_opinion(
                project_id="p1",
                audit_year=2025,
                target_type="workpaper",
                target_id="wp-1",
                severity="high",
                content=f"opinion-{i}",
                created_by_user_id="u1",
            )
            # Close all
            service.close_review(
                op,
                closing_explanation="ok",
                closer_user_id="u2",
                actor=make_human_actor(),
                has_close_permission=True,
                current_evidence_refs=[{
                    "evidence_ref_id": f"r{i}",
                    "evidence_type": "att",
                    "target_version": 1,
                    "target_hash": "c" * 64,
                    "locator": "l",
                    "stale": False,
                }],
            )
            opinions.append(op)

        # All closed → not blocked
        assert service.check_completion_blocked(opinions) is False

        # Reopen just the first one → blocked
        service.auto_reopen(opinions[0], reason="evidence_stale")
        assert service.check_completion_blocked(opinions) is True
