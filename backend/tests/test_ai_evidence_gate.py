"""Tests for AIEvidenceGate — Task 6.2 (Wave 5).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R8, R12, R15
Properties: P17, P18, P19

Covers:
- register_generation creates proper record
- confirm requires human actor (Service Identity blocked)
- confirm fails if content hash changed since generation
- confirm fails if any referenced evidence is stale
- reject marks content rejected
- invalidate_on_evidence_change marks confirmed → stale (P19)
- check_formal_output_eligibility blocks unconfirmed/stale content
- Coverage scanner logic (pure function test of set difference)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.evidence_governance.ai_evidence_gate import (
    AI_ENTRY_REGISTRY,
    AIEvidenceGate,
    AiContentRegistration,
    AiLifecycleStatus,
    AiServiceStatus,
    GateBlockReason,
    GateCheckResult,
    GateCheckStatus,
    compute_coverage_gap,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    ActorType,
    EvidenceErrorCode,
    EvidenceGovernanceError,
    sha256_hex,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _user_actor() -> ActorContext:
    return ActorContext.for_user(uuid.uuid4())


def _service_actor() -> ActorContext:
    return ActorContext.for_service(uuid.uuid4())


def _mock_db_for_register() -> AsyncMock:
    """Create a mock DB that returns expected results for register_generation."""
    db = AsyncMock()
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = {
        "id": str(uuid.uuid4()),
        "created_at": now,
    }
    db.execute.return_value = mock_result
    return db


def _mock_db_for_confirm(
    lifecycle_status: str = "draft",
    output_text: str = "Test AI output",
    evidence_refs: str | None = None,
    service_status: str = "available",
) -> AsyncMock:
    """Create a mock DB for confirm/reject/check operations."""
    db = AsyncMock()
    output_hash = sha256_hex(output_text)

    # First call: _load_content (SELECT)
    content_row = {
        "id": str(uuid.uuid4()),
        "project_id": str(uuid.uuid4()),
        "audit_year": 2025,
        "wp_id": None,
        "entry_point": "generate_text",
        "prompt_hash": sha256_hex("test prompt"),
        "model_name": "qwen3.5-27b",
        "service_status": service_status,
        "output_text": output_text,
        "output_hash": output_hash,
        "target_cell": None,
        "evidence_refs": evidence_refs,
        "citation_snapshots": None,
        "lifecycle_status": lifecycle_status,
        "content_version": 1,
        "confirmed_by_user_id": None,
        "confirmed_at": None,
    }

    # Setup execute to return different results based on call order
    select_result = MagicMock()
    select_result.mappings.return_value.first.return_value = content_row

    update_result = MagicMock()
    update_result.rowcount = 1

    db.execute.side_effect = [select_result, update_result]
    return db


# ─────────────────────────────────────────────────────────────────────────────
# Tests: register_generation
# ─────────────────────────────────────────────────────────────────────────────


class TestRegisterGeneration:
    """register_generation creates proper record with all governance fields."""

    @pytest.mark.asyncio
    async def test_register_creates_record(self):
        """Validates: Requirements 8.1 — register records prompt hash, model, output hash."""
        db = _mock_db_for_register()
        gate = AIEvidenceGate(db)
        actor = _user_actor()
        project_id = uuid.uuid4()

        result = await gate.register_generation(
            entry_point="generate_text",
            prompt_hash=sha256_hex("What is the audit conclusion?"),
            model_name="qwen3.5-27b",
            output="The audit conclusion is...",
            actor=actor,
            project_id=project_id,
            audit_year=2025,
        )

        assert isinstance(result, AiContentRegistration)
        assert result.entry_point == "generate_text"
        assert result.model_name == "qwen3.5-27b"
        assert result.lifecycle_status == AiLifecycleStatus.DRAFT
        assert result.service_status == AiServiceStatus.AVAILABLE
        assert result.content_version == 1
        assert result.output_hash == sha256_hex("The audit conclusion is...")

    @pytest.mark.asyncio
    async def test_register_rejects_undeclared_entry_point(self):
        """Validates: Property P18 — undeclared entry points are rejected."""
        db = _mock_db_for_register()
        gate = AIEvidenceGate(db)
        actor = _user_actor()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await gate.register_generation(
                entry_point="undeclared_ai_function",
                prompt_hash=sha256_hex("test"),
                model_name="test-model",
                output="test output",
                actor=actor,
                project_id=uuid.uuid4(),
            )

        assert exc_info.value.error_code == EvidenceErrorCode.EVIDENCE_GATE_BLOCKED

    @pytest.mark.asyncio
    async def test_register_with_context_refs(self):
        """register_generation records context EvidenceRef IDs."""
        db = _mock_db_for_register()
        gate = AIEvidenceGate(db)
        actor = _user_actor()
        ref1 = uuid.uuid4()
        ref2 = uuid.uuid4()

        result = await gate.register_generation(
            entry_point="generate_analysis",
            prompt_hash=sha256_hex("analyze"),
            model_name="qwen3.5-27b",
            output="Analysis result",
            actor=actor,
            project_id=uuid.uuid4(),
            context_refs=[ref1, ref2],
        )

        assert isinstance(result, AiContentRegistration)
        # DB execute was called with the refs serialized
        assert db.execute.called

    @pytest.mark.asyncio
    async def test_register_with_service_actor(self):
        """Service Identity can register (generate) but cannot confirm."""
        db = _mock_db_for_register()
        gate = AIEvidenceGate(db)
        actor = _service_actor()

        # Service actors CAN register generation (R8.1)
        result = await gate.register_generation(
            entry_point="chat_completion",
            prompt_hash=sha256_hex("service prompt"),
            model_name="qwen3.5-27b",
            output="Service generated output",
            actor=actor,
            project_id=uuid.uuid4(),
        )

        assert result.lifecycle_status == AiLifecycleStatus.DRAFT


# ─────────────────────────────────────────────────────────────────────────────
# Tests: confirm_content
# ─────────────────────────────────────────────────────────────────────────────


class TestConfirmContent:
    """Human confirm/revise/reject lifecycle tests."""

    @pytest.mark.asyncio
    async def test_confirm_requires_human_actor(self):
        """Validates: Requirements 8.1 — Service Identity cannot confirm AI content."""
        db = _mock_db_for_confirm()
        gate = AIEvidenceGate(db)
        service_actor = _service_actor()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await gate.confirm_content(
                content_id=uuid.uuid4(),
                actor=service_actor,
                project_id=uuid.uuid4(),
            )

        assert exc_info.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN

    @pytest.mark.asyncio
    async def test_confirm_succeeds_with_human_actor(self):
        """Human user can confirm draft AI content."""
        db = _mock_db_for_confirm(lifecycle_status="draft")
        gate = AIEvidenceGate(db)
        actor = _user_actor()

        result = await gate.confirm_content(
            content_id=uuid.uuid4(),
            actor=actor,
            project_id=uuid.uuid4(),
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_confirm_fails_if_hash_changed(self):
        """Validates: Requirements 8.3 — hash change blocks confirmation."""
        db = AsyncMock()
        # Return a row where stored output_hash doesn't match actual content
        content_row = {
            "id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "audit_year": 2025,
            "wp_id": None,
            "entry_point": "generate_text",
            "prompt_hash": sha256_hex("test"),
            "model_name": "test-model",
            "service_status": "available",
            "output_text": "Modified content",  # Content was modified
            "output_hash": sha256_hex("Original content"),  # Hash of original
            "target_cell": None,
            "evidence_refs": None,
            "citation_snapshots": None,
            "lifecycle_status": "draft",
            "content_version": 1,
            "confirmed_by_user_id": None,
            "confirmed_at": None,
        }
        select_result = MagicMock()
        select_result.mappings.return_value.first.return_value = content_row
        db.execute.return_value = select_result

        gate = AIEvidenceGate(db)
        actor = _user_actor()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await gate.confirm_content(
                content_id=uuid.uuid4(),
                actor=actor,
                project_id=uuid.uuid4(),
            )

        assert exc_info.value.error_code == EvidenceErrorCode.EVIDENCE_GATE_BLOCKED
        assert "hash changed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_confirm_fails_if_evidence_stale(self):
        """Validates: Property P19 — stale evidence blocks confirmation."""
        import json

        ref_id = uuid.uuid4()
        refs_json = json.dumps([str(ref_id)])
        output_text = "AI output with refs"

        db = AsyncMock()
        content_row = {
            "id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "audit_year": 2025,
            "wp_id": None,
            "entry_point": "generate_text",
            "prompt_hash": sha256_hex("test"),
            "model_name": "test-model",
            "service_status": "available",
            "output_text": output_text,
            "output_hash": sha256_hex(output_text),
            "target_cell": None,
            "evidence_refs": refs_json,
            "citation_snapshots": None,
            "lifecycle_status": "draft",
            "content_version": 1,
            "confirmed_by_user_id": None,
            "confirmed_at": None,
        }
        select_result = MagicMock()
        select_result.mappings.return_value.first.return_value = content_row

        # Second call: _check_evidence_refs_valid — returns 0 active refs
        refs_check_result = MagicMock()
        refs_check_result.mappings.return_value.first.return_value = {"cnt": 0}

        db.execute.side_effect = [select_result, refs_check_result]

        gate = AIEvidenceGate(db)
        actor = _user_actor()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await gate.confirm_content(
                content_id=uuid.uuid4(),
                actor=actor,
                project_id=uuid.uuid4(),
            )

        assert exc_info.value.error_code == EvidenceErrorCode.EVIDENCE_GATE_BLOCKED
        assert "stale" in str(exc_info.value).lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: reject_content
# ─────────────────────────────────────────────────────────────────────────────


class TestRejectContent:
    """reject_content marks draft → rejected."""

    @pytest.mark.asyncio
    async def test_reject_marks_content_rejected(self):
        """Validates: Requirements 8.1 — reject lifecycle."""
        db = _mock_db_for_confirm(lifecycle_status="draft")
        gate = AIEvidenceGate(db)
        actor = _user_actor()

        result = await gate.reject_content(
            content_id=uuid.uuid4(),
            reason="Content is inaccurate",
            actor=actor,
            project_id=uuid.uuid4(),
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_reject_fails_for_non_draft(self):
        """Cannot reject already confirmed content."""
        db = _mock_db_for_confirm(lifecycle_status="confirmed")
        gate = AIEvidenceGate(db)
        actor = _user_actor()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await gate.reject_content(
                content_id=uuid.uuid4(),
                reason="Too late",
                actor=actor,
                project_id=uuid.uuid4(),
            )

        assert exc_info.value.error_code == EvidenceErrorCode.INVALID_STATE_TRANSITION


# ─────────────────────────────────────────────────────────────────────────────
# Tests: invalidate_on_evidence_change (P19)
# ─────────────────────────────────────────────────────────────────────────────


class TestInvalidateOnEvidenceChange:
    """P19: confirmed content becomes stale when dependencies change."""

    @pytest.mark.asyncio
    async def test_invalidate_marks_confirmed_stale(self):
        """Validates: Property P19 — confirmed → stale on evidence change."""
        db = AsyncMock()
        update_result = MagicMock()
        update_result.rowcount = 1
        db.execute.return_value = update_result

        gate = AIEvidenceGate(db)

        await gate.invalidate_on_evidence_change(
            content_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
        )

        # Verify UPDATE was called with confirmed → stale
        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql_text = str(call_args[0][0].text)
        assert "lifecycle_status = 'stale'" in sql_text
        assert "lifecycle_status = 'confirmed'" in sql_text


# ─────────────────────────────────────────────────────────────────────────────
# Tests: check_formal_output_eligibility (R8.3)
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckFormalOutputEligibility:
    """R8.3: FormalOutput gate blocks unconfirmed/stale content."""

    @pytest.mark.asyncio
    async def test_eligible_when_confirmed_and_valid(self):
        """Confirmed content with valid hash and refs is eligible."""
        output_text = "Confirmed AI output"
        db = AsyncMock()
        content_row = {
            "id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "audit_year": 2025,
            "wp_id": None,
            "entry_point": "generate_text",
            "prompt_hash": sha256_hex("test"),
            "model_name": "test-model",
            "service_status": "available",
            "output_text": output_text,
            "output_hash": sha256_hex(output_text),
            "target_cell": None,
            "evidence_refs": None,
            "citation_snapshots": None,
            "lifecycle_status": "confirmed",
            "content_version": 1,
            "confirmed_by_user_id": str(uuid.uuid4()),
            "confirmed_at": "2025-01-01T00:00:00Z",
        }
        select_result = MagicMock()
        select_result.mappings.return_value.first.return_value = content_row
        db.execute.return_value = select_result

        gate = AIEvidenceGate(db)
        actor = _user_actor()

        result = await gate.check_formal_output_eligibility(
            content_id=uuid.uuid4(),
            actor=actor,
            project_id=uuid.uuid4(),
        )

        assert result.eligible is True
        assert result.status == GateCheckStatus.ELIGIBLE
        assert len(result.reasons) == 0

    @pytest.mark.asyncio
    async def test_blocked_when_not_confirmed(self):
        """Validates: Requirements 8.3 — unconfirmed content is blocked."""
        db = AsyncMock()
        output_text = "Draft AI output"
        content_row = {
            "id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "audit_year": 2025,
            "wp_id": None,
            "entry_point": "generate_text",
            "prompt_hash": sha256_hex("test"),
            "model_name": "test-model",
            "service_status": "available",
            "output_text": output_text,
            "output_hash": sha256_hex(output_text),
            "target_cell": None,
            "evidence_refs": None,
            "citation_snapshots": None,
            "lifecycle_status": "draft",
            "content_version": 1,
            "confirmed_by_user_id": None,
            "confirmed_at": None,
        }
        select_result = MagicMock()
        select_result.mappings.return_value.first.return_value = content_row
        db.execute.return_value = select_result

        gate = AIEvidenceGate(db)
        actor = _user_actor()

        result = await gate.check_formal_output_eligibility(
            content_id=uuid.uuid4(),
            actor=actor,
            project_id=uuid.uuid4(),
        )

        assert result.eligible is False
        assert result.status == GateCheckStatus.BLOCKED
        assert any(r.code == "NOT_CONFIRMED" for r in result.reasons)

    @pytest.mark.asyncio
    async def test_blocked_when_stale(self):
        """Validates: Property P19 — stale content is blocked from FormalOutput."""
        db = AsyncMock()
        output_text = "Stale AI output"
        content_row = {
            "id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "audit_year": 2025,
            "wp_id": None,
            "entry_point": "generate_text",
            "prompt_hash": sha256_hex("test"),
            "model_name": "test-model",
            "service_status": "available",
            "output_text": output_text,
            "output_hash": sha256_hex(output_text),
            "target_cell": None,
            "evidence_refs": None,
            "citation_snapshots": None,
            "lifecycle_status": "stale",
            "content_version": 1,
            "confirmed_by_user_id": None,
            "confirmed_at": None,
        }
        select_result = MagicMock()
        select_result.mappings.return_value.first.return_value = content_row
        db.execute.return_value = select_result

        gate = AIEvidenceGate(db)
        actor = _user_actor()

        result = await gate.check_formal_output_eligibility(
            content_id=uuid.uuid4(),
            actor=actor,
            project_id=uuid.uuid4(),
        )

        assert result.eligible is False
        assert any(r.code == "NOT_CONFIRMED" for r in result.reasons)

    @pytest.mark.asyncio
    async def test_blocked_when_service_unavailable(self):
        """Validates: Requirements 8.4 — unavailable service blocks output."""
        db = AsyncMock()
        output_text = "Degraded output"
        content_row = {
            "id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "audit_year": 2025,
            "wp_id": None,
            "entry_point": "generate_text",
            "prompt_hash": sha256_hex("test"),
            "model_name": "test-model",
            "service_status": "unavailable",
            "output_text": output_text,
            "output_hash": sha256_hex(output_text),
            "target_cell": None,
            "evidence_refs": None,
            "citation_snapshots": None,
            "lifecycle_status": "confirmed",
            "content_version": 1,
            "confirmed_by_user_id": str(uuid.uuid4()),
            "confirmed_at": "2025-01-01T00:00:00Z",
        }
        select_result = MagicMock()
        select_result.mappings.return_value.first.return_value = content_row
        db.execute.return_value = select_result

        gate = AIEvidenceGate(db)
        actor = _user_actor()

        result = await gate.check_formal_output_eligibility(
            content_id=uuid.uuid4(),
            actor=actor,
            project_id=uuid.uuid4(),
        )

        assert result.eligible is False
        assert any(r.code == "SERVICE_UNAVAILABLE" for r in result.reasons)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Coverage scanner (P18 pure function)
# ─────────────────────────────────────────────────────────────────────────────


class TestCoverageScanner:
    """P18: AI_entry_scan_set ∩ gate_declared_set_complement = ∅."""

    def test_no_gap_when_all_discovered_are_declared(self):
        """Validates: Property P18 — complete coverage."""
        discovered = {"generate_text", "chat_completion"}
        gap = compute_coverage_gap(discovered, AI_ENTRY_REGISTRY)
        assert gap == set()

    def test_gap_detected_when_undeclared_exists(self):
        """Validates: Property P18 — undeclared entry blocks merge."""
        discovered = {"generate_text", "totally_new_ai_call"}
        gap = compute_coverage_gap(discovered, AI_ENTRY_REGISTRY)
        assert gap == {"totally_new_ai_call"}

    def test_empty_discovered_no_gap(self):
        """Empty scan result means no violations."""
        gap = compute_coverage_gap(set(), AI_ENTRY_REGISTRY)
        assert gap == set()

    def test_gap_with_multiple_undeclared(self):
        """Multiple undeclared entries all reported."""
        discovered = {"undeclared_1", "undeclared_2", "generate_text"}
        gap = compute_coverage_gap(discovered, AI_ENTRY_REGISTRY)
        assert gap == {"undeclared_1", "undeclared_2"}

    def test_declared_superset_of_discovered_is_fine(self):
        """Declared set can be larger than discovered (not yet used entries)."""
        discovered = {"generate_text"}
        declared = frozenset({"generate_text", "extra_future_entry"})
        gap = compute_coverage_gap(discovered, declared)
        assert gap == set()

    def test_default_registry_used_when_none(self):
        """When declared_gated_set is None, uses AI_ENTRY_REGISTRY."""
        discovered = {"generate_text"}
        gap = compute_coverage_gap(discovered)
        assert gap == set()

    def test_registry_contains_known_entries(self):
        """AI_ENTRY_REGISTRY contains expected standard entries."""
        assert "generate_text" in AI_ENTRY_REGISTRY
        assert "chat_completion" in AI_ENTRY_REGISTRY
        assert "rewrite_content" in AI_ENTRY_REGISTRY
        assert "summarize_content" in AI_ENTRY_REGISTRY
        assert "complete_content" in AI_ENTRY_REGISTRY
