"""FormalOutputGate — Task 6.3 (Wave 5) unit + PBT tests.

Feature: attachment-ocr-ai-evidence-governance-hardening
Requirements: R8, R9, R10, R11, R15
Properties:
  P17 — AI 状态门禁 (only human-confirmed + hash-consistent AI can enter)
  P19 — 已确认内容变更失效 (confirmed content/dependency change → stale → blocked)
  P29 — 降级安全 (external dependency failure → fail-closed)

Tests the FormalOutputGate service:
  - preflight() and finalize() dual gate
  - RequiredEvidence set = policy + existing dependencies (no historical auto-violate)
  - P0 constraint validation for each evidence type
  - Watermark comparison between preflight and finalize
  - Degraded detection → fail-closed
  - Blocking review gate

Uses the global `fast` Hypothesis profile from conftest (max_examples=5).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.evidence_governance.formal_output_gate import (
    BlockReasonCode,
    BlockingReason,
    BlockingReviewChecker,
    EvidenceItem,
    ExternalDependencyChecker,
    ExternalDependencyStatus,
    FormalOutputGate,
    GateEvaluation,
    GatePhase,
    GateVerdict,
    PolicyProvider,
    UnifiedGraphProvider,
    FORMAL_OUTPUT_TARGET_TYPES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Strategies
# ─────────────────────────────────────────────────────────────────────────────

evidence_type_st = st.sampled_from(
    ["attachment_version", "ocr_result", "ai_content", "citation", "ref"]
)

source_st = st.sampled_from(["policy", "dependency"])


def evidence_item_st(
    *,
    force_stale: bool | None = None,
    force_ai_confirmed: bool | None = None,
) -> st.SearchStrategy[EvidenceItem]:
    """Strategy that generates valid EvidenceItems with controlled fields."""
    return st.builds(
        EvidenceItem,
        evidence_id=st.uuids().map(str),
        evidence_type=evidence_type_st,
        source=source_st,
        metadata_complete=st.just(True),
        has_actor=st.just(True),
        version=st.text(min_size=1, max_size=8),
        content_hash=st.text(min_size=64, max_size=64, alphabet="0123456789abcdef"),
        is_active_ref=st.just(True),
        ocr_confirmed=st.just(True),
        ocr_written_back=st.just(True),
        ai_human_confirmed=st.just(True) if force_ai_confirmed is None else st.just(force_ai_confirmed),
        ai_hash_consistent=st.just(True),
        citation_locatable=st.just(True),
        is_stale=st.just(False) if force_stale is None else st.just(force_stale),
        has_pending_propagation=st.just(False),
        has_blocking_review=st.just(False),
        hold_retention_consistent=st.just(True),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mock providers
# ─────────────────────────────────────────────────────────────────────────────


class MockPolicyProvider(PolicyProvider):
    def __init__(self, items: list[EvidenceItem] | None = None):
        self._items = items or []

    async def get_policy_required_evidence(
        self, target_id: str, target_type: str, policy_version: str | None = None
    ) -> list[EvidenceItem]:
        return self._items

    async def get_policy_version(
        self, target_id: str, target_type: str
    ) -> str | None:
        return "v1.0"


class MockGraphProvider(UnifiedGraphProvider):
    def __init__(self, items: list[EvidenceItem] | None = None):
        self._items = items or []

    async def get_existing_dependencies(
        self, target_id: str, target_type: str
    ) -> list[EvidenceItem]:
        return self._items


class MockDepChecker(ExternalDependencyChecker):
    def __init__(self, all_available: bool = True, unavailable: list[str] | None = None):
        self._all_available = all_available
        self._unavailable = unavailable or []

    async def check_dependencies(self) -> list[ExternalDependencyStatus]:
        deps = ["storage", "ocr", "retrieval", "ai"]
        return [
            ExternalDependencyStatus(
                name=d,
                available=(d not in self._unavailable) if self._unavailable else self._all_available,
            )
            for d in deps
        ]


class MockReviewChecker(BlockingReviewChecker):
    def __init__(self, has_blocking: bool = False):
        self._has_blocking = has_blocking

    async def has_blocking_reviews(
        self, target_id: str, target_type: str
    ) -> bool:
        return self._has_blocking


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — basic gate behavior
# ─────────────────────────────────────────────────────────────────────────────


class TestFormalOutputGateBasic:
    """Basic gate behavior tests."""

    @pytest.mark.asyncio
    async def test_preflight_pass_empty_evidence(self):
        """No evidence required, no blocking → pass."""
        gate = FormalOutputGate()
        result = await gate.preflight("target-1", "workpaper_conclusion")
        assert result.passed
        assert result.phase == GatePhase.PREFLIGHT
        assert result.verdict == GateVerdict.PASS
        assert result.blocking_reasons == []

    @pytest.mark.asyncio
    async def test_preflight_pass_with_valid_evidence(self):
        """All evidence valid → pass."""
        items = [
            EvidenceItem(
                evidence_id="ev-1",
                evidence_type="attachment_version",
                source="policy",
                metadata_complete=True,
                has_actor=True,
                version="v1",
                content_hash="a" * 64,
                is_active_ref=True,
                is_stale=False,
                has_pending_propagation=False,
                hold_retention_consistent=True,
            ),
        ]
        gate = FormalOutputGate(
            policy_provider=MockPolicyProvider(items),
        )
        result = await gate.preflight("target-1", "workpaper_conclusion")
        assert result.passed
        assert result.evidence_count == 1

    @pytest.mark.asyncio
    async def test_preflight_fail_metadata_incomplete(self):
        """Evidence with incomplete metadata → blocked."""
        items = [
            EvidenceItem(
                evidence_id="ev-1",
                evidence_type="attachment_version",
                source="policy",
                metadata_complete=False,
                has_actor=True,
            ),
        ]
        gate = FormalOutputGate(policy_provider=MockPolicyProvider(items))
        result = await gate.preflight("target-1", "report")
        assert result.failed
        codes = [r.code for r in result.blocking_reasons]
        assert BlockReasonCode.METADATA_INCOMPLETE in codes

    @pytest.mark.asyncio
    async def test_preflight_fail_actor_missing(self):
        """Evidence without actor → blocked."""
        items = [
            EvidenceItem(
                evidence_id="ev-1",
                evidence_type="ref",
                source="dependency",
                metadata_complete=True,
                has_actor=False,
            ),
        ]
        gate = FormalOutputGate(graph_provider=MockGraphProvider(items))
        result = await gate.preflight("target-1", "deliverable")
        assert result.failed
        codes = [r.code for r in result.blocking_reasons]
        assert BlockReasonCode.ACTOR_MISSING in codes

    @pytest.mark.asyncio
    async def test_watermark_stable_when_evidence_unchanged(self):
        """Watermark should be deterministic for the same evidence set."""
        items = [
            EvidenceItem(
                evidence_id="ev-1",
                evidence_type="attachment_version",
                source="policy",
                metadata_complete=True,
                has_actor=True,
                version="v1",
                content_hash="b" * 64,
                is_active_ref=True,
                is_stale=False,
                has_pending_propagation=False,
                hold_retention_consistent=True,
            ),
        ]
        gate = FormalOutputGate(policy_provider=MockPolicyProvider(items))
        r1 = await gate.preflight("t-1", "report")
        r2 = await gate.preflight("t-1", "report")
        assert r1.watermark == r2.watermark
        assert r1.watermark is not None


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — historical objects without attachments (R8.3)
# ─────────────────────────────────────────────────────────────────────────────


class TestHistoricalNoAutoViolate:
    """Historical objects without attachments don't auto-violate when policy
    doesn't require them and no existing attachment dependencies exist.

    Validates: Requirements R8.3, R11.2 — gate only checks policy-required + existing deps.
    """

    @pytest.mark.asyncio
    async def test_no_policy_no_deps_passes(self):
        """If policy doesn't require evidence and no existing deps → pass.

        Historical object with no attachments is NOT auto-violated.
        """
        gate = FormalOutputGate(
            policy_provider=MockPolicyProvider([]),  # Policy doesn't require anything
            graph_provider=MockGraphProvider([]),  # No existing dependencies
        )
        result = await gate.preflight("historical-obj-1", "workpaper_conclusion")
        assert result.passed
        assert result.evidence_count == 0

    @pytest.mark.asyncio
    async def test_existing_dep_must_satisfy_constraints(self):
        """If an existing dependency exists, it MUST satisfy P0 constraints.

        Even for historical objects — any existing evidence must be valid.
        """
        # Existing dependency with stale evidence — must fail
        items = [
            EvidenceItem(
                evidence_id="dep-1",
                evidence_type="attachment_version",
                source="dependency",
                metadata_complete=True,
                has_actor=True,
                version="v1",
                content_hash="c" * 64,
                is_active_ref=True,
                is_stale=True,  # stale!
                has_pending_propagation=False,
                hold_retention_consistent=True,
            ),
        ]
        gate = FormalOutputGate(graph_provider=MockGraphProvider(items))
        result = await gate.preflight("historical-obj-1", "workpaper_conclusion")
        assert result.failed
        codes = [r.code for r in result.blocking_reasons]
        assert BlockReasonCode.STALE_EVIDENCE in codes


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — P29 degraded safety (fail-closed)
# ─────────────────────────────────────────────────────────────────────────────


class TestDegradedSafety:
    """External dependency unavailable → fail-closed (P29).

    Validates: Requirements R15.3
    """

    @pytest.mark.asyncio
    async def test_storage_unavailable_fails_closed(self):
        """Storage unavailable → gate fails."""
        gate = FormalOutputGate(
            dependency_checker=MockDepChecker(unavailable=["storage"]),
        )
        result = await gate.preflight("t-1", "archive")
        assert result.failed
        assert result.degraded is True
        codes = [r.code for r in result.blocking_reasons]
        assert BlockReasonCode.DEPENDENCY_DEGRADED in codes

    @pytest.mark.asyncio
    async def test_ai_unavailable_fails_closed(self):
        """AI service unavailable → gate fails."""
        gate = FormalOutputGate(
            dependency_checker=MockDepChecker(unavailable=["ai"]),
        )
        result = await gate.preflight("t-1", "qc_conclusion")
        assert result.failed
        assert result.degraded is True

    @pytest.mark.asyncio
    async def test_multiple_deps_unavailable(self):
        """Multiple deps unavailable → multiple blocking reasons."""
        gate = FormalOutputGate(
            dependency_checker=MockDepChecker(unavailable=["storage", "ocr", "ai"]),
        )
        result = await gate.preflight("t-1", "report")
        assert result.failed
        assert result.degraded is True
        dep_reasons = [r for r in result.blocking_reasons if r.code == BlockReasonCode.DEPENDENCY_DEGRADED]
        assert len(dep_reasons) == 3

    @pytest.mark.asyncio
    async def test_finalize_also_checks_degraded(self):
        """Finalize gate also checks degraded status."""
        gate = FormalOutputGate(
            dependency_checker=MockDepChecker(unavailable=["retrieval"]),
        )
        result = await gate.finalize("t-1", "deliverable", "fake-watermark")
        assert result.failed
        assert result.degraded is True


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — watermark comparison (preflight→finalize)
# ─────────────────────────────────────────────────────────────────────────────


class TestWatermarkComparison:
    """Watermark change between preflight and finalize triggers failure."""

    @pytest.mark.asyncio
    async def test_finalize_passes_with_matching_watermark(self):
        """Finalize passes when watermark matches preflight."""
        items = [
            EvidenceItem(
                evidence_id="ev-1",
                evidence_type="ref",
                source="policy",
                metadata_complete=True,
                has_actor=True,
                version="v1",
                content_hash="d" * 64,
                is_active_ref=True,
                is_stale=False,
                has_pending_propagation=False,
                hold_retention_consistent=True,
            ),
        ]
        gate = FormalOutputGate(policy_provider=MockPolicyProvider(items))
        preflight = await gate.preflight("t-1", "signoff")
        assert preflight.passed

        finalize = await gate.finalize("t-1", "signoff", preflight.watermark)
        assert finalize.passed

    @pytest.mark.asyncio
    async def test_finalize_fails_on_watermark_mismatch(self):
        """Finalize fails when evidence changed → watermark mismatch."""
        items_v1 = [
            EvidenceItem(
                evidence_id="ev-1",
                evidence_type="ref",
                source="policy",
                metadata_complete=True,
                has_actor=True,
                version="v1",
                content_hash="e" * 64,
                is_active_ref=True,
                is_stale=False,
                has_pending_propagation=False,
                hold_retention_consistent=True,
            ),
        ]
        gate_v1 = FormalOutputGate(policy_provider=MockPolicyProvider(items_v1))
        preflight = await gate_v1.preflight("t-1", "report")
        assert preflight.passed

        # Evidence changed (version updated)
        items_v2 = [
            EvidenceItem(
                evidence_id="ev-1",
                evidence_type="ref",
                source="policy",
                metadata_complete=True,
                has_actor=True,
                version="v2",  # changed!
                content_hash="f" * 64,  # changed!
                is_active_ref=True,
                is_stale=False,
                has_pending_propagation=False,
                hold_retention_consistent=True,
            ),
        ]
        gate_v2 = FormalOutputGate(policy_provider=MockPolicyProvider(items_v2))
        finalize = await gate_v2.finalize("t-1", "report", preflight.watermark)
        assert finalize.failed
        codes = [r.code for r in finalize.blocking_reasons]
        assert BlockReasonCode.WATERMARK_CHANGED in codes


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — Blocking Review (R10)
# ─────────────────────────────────────────────────────────────────────────────


class TestBlockingReview:
    """Blocking Review gate (R10)."""

    @pytest.mark.asyncio
    async def test_blocking_review_fails_gate(self):
        """Active blocking review → gate fails."""
        gate = FormalOutputGate(
            review_checker=MockReviewChecker(has_blocking=True),
        )
        result = await gate.preflight("t-1", "qc_conclusion")
        assert result.failed
        codes = [r.code for r in result.blocking_reasons]
        assert BlockReasonCode.BLOCKING_REVIEW in codes


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — OCR / AI specific checks
# ─────────────────────────────────────────────────────────────────────────────


class TestOcrAiChecks:
    """OCR and AI-specific constraint validation."""

    @pytest.mark.asyncio
    async def test_ocr_not_confirmed_blocks(self):
        """OCR result without human confirmation → blocked."""
        items = [
            EvidenceItem(
                evidence_id="ocr-1",
                evidence_type="ocr_result",
                source="dependency",
                metadata_complete=True,
                has_actor=True,
                ocr_confirmed=False,
                ocr_written_back=True,
                is_stale=False,
                has_pending_propagation=False,
                hold_retention_consistent=True,
            ),
        ]
        gate = FormalOutputGate(graph_provider=MockGraphProvider(items))
        result = await gate.preflight("t-1", "workpaper_conclusion")
        assert result.failed
        codes = [r.code for r in result.blocking_reasons]
        assert BlockReasonCode.OCR_NOT_CONFIRMED in codes

    @pytest.mark.asyncio
    async def test_ai_not_confirmed_blocks(self):
        """AI content without human confirmation → blocked (P17)."""
        items = [
            EvidenceItem(
                evidence_id="ai-1",
                evidence_type="ai_content",
                source="policy",
                metadata_complete=True,
                has_actor=True,
                ai_human_confirmed=False,
                ai_hash_consistent=True,
                is_stale=False,
                has_pending_propagation=False,
                hold_retention_consistent=True,
            ),
        ]
        gate = FormalOutputGate(policy_provider=MockPolicyProvider(items))
        result = await gate.preflight("t-1", "disclosure_note")
        assert result.failed
        codes = [r.code for r in result.blocking_reasons]
        assert BlockReasonCode.AI_NOT_CONFIRMED in codes

    @pytest.mark.asyncio
    async def test_ai_hash_changed_blocks(self):
        """AI content with hash change → blocked (P19)."""
        items = [
            EvidenceItem(
                evidence_id="ai-2",
                evidence_type="ai_content",
                source="dependency",
                metadata_complete=True,
                has_actor=True,
                ai_human_confirmed=True,
                ai_hash_consistent=False,  # hash changed!
                is_stale=False,
                has_pending_propagation=False,
                hold_retention_consistent=True,
            ),
        ]
        gate = FormalOutputGate(graph_provider=MockGraphProvider(items))
        result = await gate.preflight("t-1", "report")
        assert result.failed
        codes = [r.code for r in result.blocking_reasons]
        assert BlockReasonCode.AI_HASH_CHANGED in codes


# ─────────────────────────────────────────────────────────────────────────────
# PBT — Property P17: AI 状态门禁
# ─────────────────────────────────────────────────────────────────────────────


class TestPropertyP17AiStateGate:
    """**Validates: Requirements R8.3**

    P17: Only human-confirmed, hash-consistent AI content with valid policy-required
    evidence and existing dependencies can enter FormalOutput. Historical objects
    without attachments don't auto-violate.
    """

    @given(
        confirmed=st.booleans(),
        hash_consistent=st.booleans(),
    )
    @pytest.mark.asyncio
    async def test_ai_content_gate_p17(self, confirmed: bool, hash_consistent: bool):
        """AI content only passes when both confirmed AND hash consistent."""
        items = [
            EvidenceItem(
                evidence_id=str(uuid.uuid4()),
                evidence_type="ai_content",
                source="policy",
                metadata_complete=True,
                has_actor=True,
                ai_human_confirmed=confirmed,
                ai_hash_consistent=hash_consistent,
                is_stale=False,
                has_pending_propagation=False,
                hold_retention_consistent=True,
            ),
        ]
        gate = FormalOutputGate(policy_provider=MockPolicyProvider(items))
        result = await gate.preflight("t-pbt", "workpaper_conclusion")

        should_pass = confirmed and hash_consistent
        if should_pass:
            assert result.passed, f"Expected pass: confirmed={confirmed}, hash={hash_consistent}"
        else:
            assert result.failed, f"Expected fail: confirmed={confirmed}, hash={hash_consistent}"
            codes = {r.code for r in result.blocking_reasons}
            if not confirmed:
                assert BlockReasonCode.AI_NOT_CONFIRMED in codes
            if not hash_consistent:
                assert BlockReasonCode.AI_HASH_CHANGED in codes


# ─────────────────────────────────────────────────────────────────────────────
# PBT — Property P19: 已确认内容变更失效
# ─────────────────────────────────────────────────────────────────────────────


class TestPropertyP19ConfirmedContentInvalidation:
    """**Validates: Requirements R8.3, R9.2**

    P19: Confirmed content or any dependency change → draft/stale, original
    confirmation no longer authorizes output. Stale evidence blocks gate.
    """

    @given(is_stale=st.booleans())
    @pytest.mark.asyncio
    async def test_stale_evidence_blocks_gate(self, is_stale: bool):
        """Stale evidence always blocks; non-stale with valid fields passes."""
        items = [
            EvidenceItem(
                evidence_id=str(uuid.uuid4()),
                evidence_type="attachment_version",
                source="dependency",
                metadata_complete=True,
                has_actor=True,
                version="v1",
                content_hash="a" * 64,
                is_active_ref=True,
                is_stale=is_stale,
                has_pending_propagation=False,
                hold_retention_consistent=True,
            ),
        ]
        gate = FormalOutputGate(graph_provider=MockGraphProvider(items))
        result = await gate.preflight("t-pbt", "deliverable")

        if is_stale:
            assert result.failed
            codes = {r.code for r in result.blocking_reasons}
            assert BlockReasonCode.STALE_EVIDENCE in codes
        else:
            assert result.passed


# ─────────────────────────────────────────────────────────────────────────────
# PBT — Property P29: 降级安全
# ─────────────────────────────────────────────────────────────────────────────


class TestPropertyP29DegradedSafety:
    """**Validates: Requirements R15.3**

    P29: External dependency (storage/OCR/retrieval/AI) failure → fail-closed.
    No confirmed/written_back/archived terminal state when ANY dep is unavailable.
    """

    @given(
        unavailable_dep=st.sampled_from(["storage", "ocr", "retrieval", "ai"]),
    )
    @pytest.mark.asyncio
    async def test_any_dep_unavailable_fails_closed(self, unavailable_dep: str):
        """Any single external dependency failure → gate fails (fail-closed)."""
        gate = FormalOutputGate(
            dependency_checker=MockDepChecker(unavailable=[unavailable_dep]),
        )
        result = await gate.preflight("t-pbt", "archive")
        assert result.failed
        assert result.degraded is True
        codes = {r.code for r in result.blocking_reasons}
        assert BlockReasonCode.DEPENDENCY_DEGRADED in codes

    @given(
        deps=st.lists(
            st.sampled_from(["storage", "ocr", "retrieval", "ai"]),
            min_size=1,
            max_size=4,
            unique=True,
        ),
    )
    @pytest.mark.asyncio
    async def test_multiple_deps_unavailable_still_fails(self, deps: list[str]):
        """Multiple dependency failures still fail-closed (never partial pass)."""
        gate = FormalOutputGate(
            dependency_checker=MockDepChecker(unavailable=deps),
        )
        result = await gate.preflight("t-pbt", "signoff")
        assert result.failed
        assert result.degraded is True
        # Each unavailable dep produces a blocking reason
        dep_reasons = [
            r for r in result.blocking_reasons
            if r.code == BlockReasonCode.DEPENDENCY_DEGRADED
        ]
        assert len(dep_reasons) == len(deps)


# ─────────────────────────────────────────────────────────────────────────────
# Unit test — RequiredEvidence deduplication
# ─────────────────────────────────────────────────────────────────────────────


class TestRequiredEvidenceSet:
    """RequiredEvidence = Policy ∪ ExistingDeps (union, deduplicated by evidence_id)."""

    @pytest.mark.asyncio
    async def test_union_deduplicates(self):
        """Same evidence_id in both policy + graph → counted once."""
        shared_item = EvidenceItem(
            evidence_id="shared-1",
            evidence_type="attachment_version",
            source="policy",
            metadata_complete=True,
            has_actor=True,
            is_stale=False,
            has_pending_propagation=False,
            hold_retention_consistent=True,
        )
        dep_item = EvidenceItem(
            evidence_id="shared-1",  # same ID!
            evidence_type="attachment_version",
            source="dependency",
            metadata_complete=True,
            has_actor=True,
            is_stale=False,
            has_pending_propagation=False,
            hold_retention_consistent=True,
        )
        gate = FormalOutputGate(
            policy_provider=MockPolicyProvider([shared_item]),
            graph_provider=MockGraphProvider([dep_item]),
        )
        result = await gate.preflight("t-1", "report")
        assert result.evidence_count == 1  # deduplicated
        assert result.passed

    @pytest.mark.asyncio
    async def test_union_includes_both_sources(self):
        """Distinct items from policy and graph are both included."""
        policy_item = EvidenceItem(
            evidence_id="policy-1",
            evidence_type="ref",
            source="policy",
            metadata_complete=True,
            has_actor=True,
            is_stale=False,
            has_pending_propagation=False,
            hold_retention_consistent=True,
        )
        dep_item = EvidenceItem(
            evidence_id="dep-1",
            evidence_type="attachment_version",
            source="dependency",
            metadata_complete=True,
            has_actor=True,
            is_stale=False,
            has_pending_propagation=False,
            hold_retention_consistent=True,
        )
        gate = FormalOutputGate(
            policy_provider=MockPolicyProvider([policy_item]),
            graph_provider=MockGraphProvider([dep_item]),
        )
        result = await gate.preflight("t-1", "report")
        assert result.evidence_count == 2
        assert result.passed


# ─────────────────────────────────────────────────────────────────────────────
# Unit test — FORMAL_OUTPUT_TARGET_TYPES
# ─────────────────────────────────────────────────────────────────────────────


class TestTargetTypes:
    """Gate target types coverage."""

    def test_all_formal_output_types_present(self):
        expected = {
            "workpaper_conclusion",
            "disclosure_note",
            "report",
            "signoff",
            "qc_conclusion",
            "eqcr_conclusion",
            "deliverable",
            "archive",
        }
        assert FORMAL_OUTPUT_TARGET_TYPES == frozenset(expected)
