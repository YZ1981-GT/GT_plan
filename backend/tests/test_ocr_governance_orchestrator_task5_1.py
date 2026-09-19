"""Unit tests for OCRGovernanceOrchestrator (Task 5.1, Wave 4).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R5, R12, R15
Properties: P9 (state machine), P10 (idempotent reuse), P25 (command-root)

Tests:
- submit_ocr_job: creates new job / reuses existing (R5.4)
- acquire_lease: queued→running, increments attempt, sets lease
- record_transition: validates against closed state machine (P9)
- complete_recognition: running→awaiting_confirmation
- fail_job: queued/running→failed, clears lease
- idempotency key derivation deterministic
- bounded retries (R15.4)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.evidence_governance_models import OcrJob, OcrJobTransition
from app.services.evidence_governance.contracts import OcrState
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    ActorType,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.ocr_governance import (
    DEFAULT_LEASE_DURATION,
    DEFAULT_MAX_ATTEMPTS,
    OCRGovernanceOrchestrator,
    compute_idempotency_key,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_actor() -> ActorContext:
    return ActorContext.for_user(uuid.uuid4())


def _make_service_actor() -> ActorContext:
    return ActorContext.for_service(uuid.uuid4())


# ---------------------------------------------------------------------------
# compute_idempotency_key tests
# ---------------------------------------------------------------------------

class TestComputeIdempotencyKey:
    """Test idempotency key derivation is deterministic and collision-free."""

    def test_same_inputs_same_key(self):
        vid = uuid.uuid4()
        h = "a" * 64
        cfg = {"lang": "zh-CN", "engine": "rapid"}

        key1 = compute_idempotency_key(vid, h, cfg)
        key2 = compute_idempotency_key(vid, h, cfg)
        assert key1 == key2

    def test_different_hash_different_key(self):
        vid = uuid.uuid4()
        key1 = compute_idempotency_key(vid, "a" * 64, None)
        key2 = compute_idempotency_key(vid, "b" * 64, None)
        assert key1 != key2

    def test_different_config_different_key(self):
        vid = uuid.uuid4()
        h = "c" * 64
        key1 = compute_idempotency_key(vid, h, {"lang": "zh"})
        key2 = compute_idempotency_key(vid, h, {"lang": "en"})
        assert key1 != key2

    def test_none_config_vs_empty_dict(self):
        vid = uuid.uuid4()
        h = "d" * 64
        key1 = compute_idempotency_key(vid, h, None)
        key2 = compute_idempotency_key(vid, h, {})
        # None and {} produce different keys (distinct configs)
        assert key1 != key2

    def test_key_is_hex_string(self):
        vid = uuid.uuid4()
        key = compute_idempotency_key(vid, "e" * 64, None)
        assert isinstance(key, str)
        assert len(key) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# OCRGovernanceOrchestrator tests (mocked DB)
# ---------------------------------------------------------------------------

class TestSubmitOcrJob:
    """Test submit_ocr_job creates/reuses jobs idempotently."""

    @pytest.mark.asyncio
    async def test_creates_new_job_when_no_existing(self):
        """New job is created when no reusable job exists."""
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        # _find_reusable_job returns None
        orch = OCRGovernanceOrchestrator(db)

        # Mock execute to return no existing job
        db.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        actor = _make_actor()
        project_id = uuid.uuid4()
        attachment_id = uuid.uuid4()
        version_id = uuid.uuid4()

        job, created = await orch.submit_ocr_job(
            project_id=project_id,
            audit_year=2025,
            attachment_id=attachment_id,
            attachment_version_id=version_id,
            content_hash="f" * 64,
            parse_config={"lang": "zh"},
            actor=actor,
        )

        assert created is True
        assert job.state == OcrState.queued.value
        assert job.project_id == project_id
        assert job.attachment_version_id == version_id
        assert job.content_hash == "f" * 64
        assert job.attempt_count == 0
        assert job.max_attempts == DEFAULT_MAX_ATTEMPTS
        # db.add called for job + transition
        assert db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_reuses_existing_active_job(self):
        """Existing active job is returned without creating a new one (R5.4)."""
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        existing_job = MagicMock()
        existing_job.state = OcrState.running.value
        existing_job.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_job
        db.execute = AsyncMock(return_value=mock_result)

        orch = OCRGovernanceOrchestrator(db)
        actor = _make_actor()

        job, created = await orch.submit_ocr_job(
            project_id=uuid.uuid4(),
            audit_year=2025,
            attachment_id=uuid.uuid4(),
            attachment_version_id=uuid.uuid4(),
            content_hash="a" * 64,
            actor=actor,
        )

        assert created is False
        assert job is existing_job
        # No new job or transition added
        assert db.add.call_count == 0


class TestAcquireLease:
    """Test acquire_lease transitions queued→running with lease + attempt."""

    @pytest.mark.asyncio
    async def test_acquires_lease_on_queued_job(self):
        """Queued job transitions to running with lease set."""
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        job = OcrJob(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            audit_year=2025,
            attachment_id=uuid.uuid4(),
            attachment_version_id=uuid.uuid4(),
            content_hash="b" * 64,
            idempotency_key="test_key",
            state=OcrState.queued.value,
            attempt_count=0,
            max_attempts=5,
            actor_type="user",
            actor_user_id=uuid.uuid4(),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        db.execute = AsyncMock(return_value=mock_result)

        orch = OCRGovernanceOrchestrator(db)
        actor = _make_service_actor()

        result = await orch.acquire_lease(
            job_id=job.id,
            lease_owner="worker-1",
            actor=actor,
        )

        assert result.state == OcrState.running.value
        assert result.lease_owner == "worker-1"
        assert result.lease_expires_at is not None
        assert result.attempt_count == 1
        # Transition recorded
        assert db.add.call_count == 1

    @pytest.mark.asyncio
    async def test_rejects_lease_on_non_queued_job(self):
        """Non-queued job cannot acquire lease (P9)."""
        db = AsyncMock()
        db.flush = AsyncMock()

        job = OcrJob(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            audit_year=2025,
            attachment_id=uuid.uuid4(),
            attachment_version_id=uuid.uuid4(),
            content_hash="c" * 64,
            idempotency_key="test_key2",
            state=OcrState.running.value,
            attempt_count=1,
            max_attempts=5,
            actor_type="user",
            actor_user_id=uuid.uuid4(),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        db.execute = AsyncMock(return_value=mock_result)

        orch = OCRGovernanceOrchestrator(db)
        actor = _make_service_actor()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await orch.acquire_lease(
                job_id=job.id,
                lease_owner="worker-2",
                actor=actor,
            )
        assert exc_info.value.error_code == EvidenceErrorCode.INVALID_STATE_TRANSITION

    @pytest.mark.asyncio
    async def test_rejects_lease_when_max_attempts_exceeded(self):
        """Bounded retries: attempt > max_attempts fails (R15.4)."""
        db = AsyncMock()
        db.flush = AsyncMock()

        job = OcrJob(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            audit_year=2025,
            attachment_id=uuid.uuid4(),
            attachment_version_id=uuid.uuid4(),
            content_hash="d" * 64,
            idempotency_key="test_key3",
            state=OcrState.queued.value,
            attempt_count=5,  # already at max
            max_attempts=5,
            actor_type="user",
            actor_user_id=uuid.uuid4(),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        db.execute = AsyncMock(return_value=mock_result)

        orch = OCRGovernanceOrchestrator(db)
        actor = _make_service_actor()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await orch.acquire_lease(
                job_id=job.id,
                lease_owner="worker-3",
                actor=actor,
            )
        assert exc_info.value.error_code == EvidenceErrorCode.INVALID_STATE_TRANSITION


class TestRecordTransition:
    """Test record_transition validates against closed state machine (P9)."""

    @pytest.mark.asyncio
    async def test_legal_transition_succeeds(self):
        """Legal transition updates state and records transition."""
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        job = OcrJob(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            audit_year=2025,
            attachment_id=uuid.uuid4(),
            attachment_version_id=uuid.uuid4(),
            content_hash="e" * 64,
            idempotency_key="test_key4",
            state=OcrState.awaiting_confirmation.value,
            progress=100,
            attempt_count=1,
            max_attempts=5,
            actor_type="user",
            actor_user_id=uuid.uuid4(),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        db.execute = AsyncMock(return_value=mock_result)

        orch = OCRGovernanceOrchestrator(db)
        actor = _make_actor()

        result = await orch.record_transition(
            job_id=job.id,
            to_state=OcrState.confirmed.value,
            actor=actor,
        )

        assert result.state == OcrState.confirmed.value

    @pytest.mark.asyncio
    async def test_illegal_transition_raises(self):
        """Illegal transition raises and leaves state unchanged (P9)."""
        db = AsyncMock()
        db.flush = AsyncMock()

        job = OcrJob(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            audit_year=2025,
            attachment_id=uuid.uuid4(),
            attachment_version_id=uuid.uuid4(),
            content_hash="g" * 64,
            idempotency_key="test_key5",
            state=OcrState.queued.value,
            progress=0,
            attempt_count=0,
            max_attempts=5,
            actor_type="user",
            actor_user_id=uuid.uuid4(),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        db.execute = AsyncMock(return_value=mock_result)

        orch = OCRGovernanceOrchestrator(db)
        actor = _make_actor()

        # queued→confirmed is NOT legal
        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await orch.record_transition(
                job_id=job.id,
                to_state=OcrState.confirmed.value,
                actor=actor,
            )
        assert exc_info.value.error_code == EvidenceErrorCode.INVALID_STATE_TRANSITION
        # State unchanged
        assert job.state == OcrState.queued.value


class TestCompleteRecognition:
    """Test complete_recognition delegates to record_transition (running→awaiting_confirmation)."""

    @pytest.mark.asyncio
    async def test_transitions_running_to_awaiting(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        job = OcrJob(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            audit_year=2025,
            attachment_id=uuid.uuid4(),
            attachment_version_id=uuid.uuid4(),
            content_hash="h" * 64,
            idempotency_key="test_key6",
            state=OcrState.running.value,
            progress=50,
            attempt_count=1,
            max_attempts=5,
            actor_type="service",
            actor_service_identity_id=uuid.uuid4(),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        db.execute = AsyncMock(return_value=mock_result)

        orch = OCRGovernanceOrchestrator(db)
        actor = _make_service_actor()

        result = await orch.complete_recognition(
            job_id=job.id,
            actor=actor,
        )

        assert result.state == OcrState.awaiting_confirmation.value
        assert result.progress == 100


class TestFailJob:
    """Test fail_job transitions queued/running→failed."""

    @pytest.mark.asyncio
    async def test_fails_queued_job(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        job = OcrJob(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            audit_year=2025,
            attachment_id=uuid.uuid4(),
            attachment_version_id=uuid.uuid4(),
            content_hash="i" * 64,
            idempotency_key="test_key7",
            state=OcrState.queued.value,
            progress=0,
            attempt_count=0,
            max_attempts=5,
            lease_owner="worker-x",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            actor_type="user",
            actor_user_id=uuid.uuid4(),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        db.execute = AsyncMock(return_value=mock_result)

        orch = OCRGovernanceOrchestrator(db)
        actor = _make_service_actor()

        result = await orch.fail_job(
            job_id=job.id,
            actor=actor,
            error_code="TIMEOUT",
            error_message="OCR service timeout",
        )

        assert result.state == OcrState.failed.value
        assert result.error_code == "TIMEOUT"
        assert result.error_message == "OCR service timeout"
        # Lease cleared on failure
        assert result.lease_owner is None
        assert result.lease_expires_at is None

    @pytest.mark.asyncio
    async def test_fails_running_job(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        job = OcrJob(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            audit_year=2025,
            attachment_id=uuid.uuid4(),
            attachment_version_id=uuid.uuid4(),
            content_hash="j" * 64,
            idempotency_key="test_key8",
            state=OcrState.running.value,
            progress=30,
            attempt_count=1,
            max_attempts=5,
            actor_type="user",
            actor_user_id=uuid.uuid4(),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        db.execute = AsyncMock(return_value=mock_result)

        orch = OCRGovernanceOrchestrator(db)
        actor = _make_service_actor()

        result = await orch.fail_job(
            job_id=job.id,
            actor=actor,
            error_code="ENGINE_ERROR",
        )

        assert result.state == OcrState.failed.value

    @pytest.mark.asyncio
    async def test_cannot_fail_confirmed_job(self):
        """Confirmed job cannot be failed (P9)."""
        db = AsyncMock()
        db.flush = AsyncMock()

        job = OcrJob(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            audit_year=2025,
            attachment_id=uuid.uuid4(),
            attachment_version_id=uuid.uuid4(),
            content_hash="k" * 64,
            idempotency_key="test_key9",
            state=OcrState.confirmed.value,
            progress=100,
            attempt_count=1,
            max_attempts=5,
            actor_type="user",
            actor_user_id=uuid.uuid4(),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        db.execute = AsyncMock(return_value=mock_result)

        orch = OCRGovernanceOrchestrator(db)
        actor = _make_service_actor()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await orch.fail_job(
                job_id=job.id,
                actor=actor,
            )
        assert exc_info.value.error_code == EvidenceErrorCode.INVALID_STATE_TRANSITION


class TestJobNotFound:
    """Test that accessing a non-existent job raises appropriately."""

    @pytest.mark.asyncio
    async def test_acquire_lease_not_found(self):
        db = AsyncMock()
        db.flush = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        orch = OCRGovernanceOrchestrator(db)
        actor = _make_service_actor()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await orch.acquire_lease(
                job_id=uuid.uuid4(),
                lease_owner="worker-x",
                actor=actor,
            )
        assert exc_info.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN
