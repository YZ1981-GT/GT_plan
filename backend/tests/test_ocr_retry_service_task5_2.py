"""Tests for OCRRetryService — Task 5.2 (Wave 4).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R5, R12, R15
Properties: P9 (closed state machine), P10 (retry authorization / zero side effects)

Covers:
- Authorized retry (manager) succeeds: failed→queued with next_retry_at computed
- Unauthorized retry (auditor without ocr.retry) → zero side effects
- Retry at max_attempts → permanent failure, no state change
- Duplicate suppression: retry when already queued → idempotent return
- Recover stale leases: expired-lease running→queued
- Recover stale leases: expired-lease + max_attempts→failed
- Backoff computation: exponential with cap
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.evidence_governance.contracts import OcrState
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    ActorType,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.ocr_retry_service import (
    DEFAULT_BASE_DELAY_SECONDS,
    DEFAULT_MAX_DELAY_SECONDS,
    OCRRetryService,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_actor_user(user_id: uuid.UUID | None = None) -> ActorContext:
    return ActorContext.for_user(user_id or uuid.uuid4())


def _make_actor_service(sid: uuid.UUID | None = None) -> ActorContext:
    return ActorContext.for_service(sid or uuid.uuid4())


def _make_job(
    *,
    state: str = OcrState.failed.value,
    attempt_count: int = 1,
    max_attempts: int = 5,
    idempotency_key: str = "test-key",
    project_id: uuid.UUID | None = None,
    lease_expires_at: datetime | None = None,
    lease_owner: str | None = None,
) -> MagicMock:
    """Create a mock OcrJob for testing."""
    job = MagicMock()
    job.id = uuid.uuid4()
    job.project_id = project_id or uuid.uuid4()
    job.audit_year = 2025
    job.state = state
    job.attempt_count = attempt_count
    job.max_attempts = max_attempts
    job.idempotency_key = idempotency_key
    job.error_code = "SOME_ERROR" if state == OcrState.failed.value else None
    job.error_message = "Some error" if state == OcrState.failed.value else None
    job.lease_owner = lease_owner
    job.lease_expires_at = lease_expires_at
    job.next_retry_at = None
    job.updated_at = datetime.now(timezone.utc)
    return job


def _mock_db():
    """Create a mock AsyncSession."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _mock_execute_result(scalar_value):
    """Helper to create a mock execute result."""
    result = AsyncMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar_value)
    result.scalar_one = MagicMock(return_value=scalar_value)
    result.scalars = MagicMock()
    result.scalars.return_value.all = MagicMock(return_value=[])
    return result


# ---------------------------------------------------------------------------
# Test: Backoff computation
# ---------------------------------------------------------------------------

class TestComputeNextRetryAt:
    """Backoff computation: exponential with cap (R15.4)."""

    def test_first_attempt_uses_base_delay(self):
        db = _mock_db()
        svc = OCRRetryService(db, base_delay_seconds=30.0, max_delay_seconds=3600.0)

        before = datetime.now(timezone.utc)
        result = svc.compute_next_retry_at(1)
        after = datetime.now(timezone.utc)

        # attempt=1 → delay = 30 * 2^0 = 30s
        expected_min = before + timedelta(seconds=30)
        expected_max = after + timedelta(seconds=30)
        assert expected_min <= result <= expected_max

    def test_second_attempt_doubles(self):
        db = _mock_db()
        svc = OCRRetryService(db, base_delay_seconds=30.0, max_delay_seconds=3600.0)

        before = datetime.now(timezone.utc)
        result = svc.compute_next_retry_at(2)
        after = datetime.now(timezone.utc)

        # attempt=2 → delay = 30 * 2^1 = 60s
        expected_min = before + timedelta(seconds=60)
        expected_max = after + timedelta(seconds=60)
        assert expected_min <= result <= expected_max

    def test_exponential_growth(self):
        db = _mock_db()
        svc = OCRRetryService(db, base_delay_seconds=30.0, max_delay_seconds=3600.0)

        # attempt=5 → delay = 30 * 2^4 = 480s
        before = datetime.now(timezone.utc)
        result = svc.compute_next_retry_at(5)
        after = datetime.now(timezone.utc)

        expected_min = before + timedelta(seconds=480)
        expected_max = after + timedelta(seconds=480)
        assert expected_min <= result <= expected_max

    def test_caps_at_max_delay(self):
        db = _mock_db()
        svc = OCRRetryService(db, base_delay_seconds=30.0, max_delay_seconds=3600.0)

        # attempt=10 → 30 * 2^9 = 15360s > max(3600) → capped at 3600
        before = datetime.now(timezone.utc)
        result = svc.compute_next_retry_at(10)
        after = datetime.now(timezone.utc)

        expected_min = before + timedelta(seconds=3600)
        expected_max = after + timedelta(seconds=3600)
        assert expected_min <= result <= expected_max


# ---------------------------------------------------------------------------
# Test: Authorized retry (manager succeeds)
# ---------------------------------------------------------------------------

class TestRetryFailedJobAuthorized:
    """Authorized retry (manager) succeeds: failed→queued with next_retry_at computed."""

    @pytest.mark.asyncio
    async def test_manager_can_retry_failed_job(self):
        db = _mock_db()
        job = _make_job(state=OcrState.failed.value, attempt_count=2, max_attempts=5)

        # We need to handle multiple execute calls:
        # 1. _get_job_for_update (FOR UPDATE) → returns the job
        # 2. _has_active_duplicate (COUNT) → returns 0
        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: _get_job_for_update → scalar_one_or_none returns job
                return _mock_execute_result(job)
            else:
                # Second call: _has_active_duplicate → scalar_one returns 0
                return _mock_execute_result(0)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        actor = _make_actor_user()

        result = await svc.retry_failed_job(
            job_id=job.id,
            actor=actor,
            actor_role="manager",
        )

        assert result.state == OcrState.queued.value
        assert result.next_retry_at is not None
        assert result.error_code is None
        assert result.error_message is None
        assert result.lease_owner is None
        assert result.lease_expires_at is None

    @pytest.mark.asyncio
    async def test_admin_can_retry_failed_job(self):
        db = _mock_db()
        job = _make_job(state=OcrState.failed.value, attempt_count=1, max_attempts=5)

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_execute_result(job)
            else:
                return _mock_execute_result(0)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        actor = _make_actor_user()

        result = await svc.retry_failed_job(
            job_id=job.id,
            actor=actor,
            actor_role="admin",
        )

        assert result.state == OcrState.queued.value

    @pytest.mark.asyncio
    async def test_partner_can_retry_failed_job(self):
        db = _mock_db()
        job = _make_job(state=OcrState.failed.value, attempt_count=1, max_attempts=5)

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_execute_result(job)
            else:
                return _mock_execute_result(0)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        actor = _make_actor_user()

        result = await svc.retry_failed_job(
            job_id=job.id,
            actor=actor,
            actor_role="partner",
        )

        assert result.state == OcrState.queued.value


# ---------------------------------------------------------------------------
# Test: Unauthorized retry → zero side effects (P10)
# ---------------------------------------------------------------------------

class TestRetryUnauthorized:
    """Unauthorized retry (auditor without ocr.retry) → zero side effects."""

    @pytest.mark.asyncio
    async def test_auditor_retry_denied_zero_effects(self):
        """auditor has ocr.retry=denied → must raise without any DB changes."""
        db = _mock_db()
        job = _make_job(state=OcrState.failed.value)

        # The service should NOT even call execute (zero side effects)
        svc = OCRRetryService(db)
        actor = _make_actor_user()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await svc.retry_failed_job(
                job_id=job.id,
                actor=actor,
                actor_role="auditor",
            )

        assert exc_info.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN
        # Zero side effects: no flush, no add called
        db.flush.assert_not_awaited()
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_readonly_retry_denied_zero_effects(self):
        db = _mock_db()
        job = _make_job(state=OcrState.failed.value)

        svc = OCRRetryService(db)
        actor = _make_actor_user()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await svc.retry_failed_job(
                job_id=job.id,
                actor=actor,
                actor_role="readonly",
            )

        assert exc_info.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN
        db.flush.assert_not_awaited()
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_qc_retry_denied_zero_effects(self):
        db = _mock_db()
        svc = OCRRetryService(db)
        actor = _make_actor_user()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await svc.retry_failed_job(
                job_id=uuid.uuid4(),
                actor=actor,
                actor_role="qc",
            )

        assert exc_info.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN
        db.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_eqcr_retry_denied_zero_effects(self):
        db = _mock_db()
        svc = OCRRetryService(db)
        actor = _make_actor_user()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await svc.retry_failed_job(
                job_id=uuid.uuid4(),
                actor=actor,
                actor_role="eqcr",
            )

        assert exc_info.value.error_code == EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN
        db.flush.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: Retry at max_attempts → permanent failure
# ---------------------------------------------------------------------------

class TestRetryMaxAttempts:
    """Retry at max_attempts → permanent failure, no state change."""

    @pytest.mark.asyncio
    async def test_retry_at_max_attempts_raises(self):
        db = _mock_db()
        job = _make_job(
            state=OcrState.failed.value,
            attempt_count=5,
            max_attempts=5,
        )

        async def mock_execute(stmt):
            return _mock_execute_result(job)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        actor = _make_actor_user()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await svc.retry_failed_job(
                job_id=job.id,
                actor=actor,
                actor_role="manager",
            )

        assert exc_info.value.error_code == EvidenceErrorCode.INVALID_STATE_TRANSITION
        # State unchanged
        assert job.state == OcrState.failed.value

    @pytest.mark.asyncio
    async def test_retry_exceeds_max_attempts_raises(self):
        db = _mock_db()
        job = _make_job(
            state=OcrState.failed.value,
            attempt_count=10,
            max_attempts=5,
        )

        async def mock_execute(stmt):
            return _mock_execute_result(job)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        actor = _make_actor_user()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await svc.retry_failed_job(
                job_id=job.id,
                actor=actor,
                actor_role="manager",
            )

        assert exc_info.value.error_code == EvidenceErrorCode.INVALID_STATE_TRANSITION


# ---------------------------------------------------------------------------
# Test: Retry on non-failed state → invalid transition
# ---------------------------------------------------------------------------

class TestRetryWrongState:
    """Retry when state != 'failed' → INVALID_STATE_TRANSITION."""

    @pytest.mark.asyncio
    async def test_retry_running_job_raises(self):
        db = _mock_db()
        job = _make_job(state=OcrState.running.value)

        async def mock_execute(stmt):
            return _mock_execute_result(job)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        actor = _make_actor_user()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await svc.retry_failed_job(
                job_id=job.id,
                actor=actor,
                actor_role="manager",
            )

        assert exc_info.value.error_code == EvidenceErrorCode.INVALID_STATE_TRANSITION

    @pytest.mark.asyncio
    async def test_retry_queued_job_raises(self):
        db = _mock_db()
        job = _make_job(state=OcrState.queued.value)

        async def mock_execute(stmt):
            return _mock_execute_result(job)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        actor = _make_actor_user()

        with pytest.raises(EvidenceGovernanceError) as exc_info:
            await svc.retry_failed_job(
                job_id=job.id,
                actor=actor,
                actor_role="manager",
            )

        assert exc_info.value.error_code == EvidenceErrorCode.INVALID_STATE_TRANSITION


# ---------------------------------------------------------------------------
# Test: Duplicate suppression
# ---------------------------------------------------------------------------

class TestDuplicateSuppression:
    """Duplicate suppression: retry when already queued → idempotent return."""

    @pytest.mark.asyncio
    async def test_duplicate_queued_returns_idempotent(self):
        db = _mock_db()
        job = _make_job(state=OcrState.failed.value, attempt_count=2, max_attempts=5)

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: _get_job_for_update → returns job
                return _mock_execute_result(job)
            else:
                # Second call: _has_active_duplicate → returns 1 (has duplicate)
                return _mock_execute_result(1)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        actor = _make_actor_user()

        # Should return idempotently (no state change since duplicate exists)
        result = await svc.retry_failed_job(
            job_id=job.id,
            actor=actor,
            actor_role="manager",
        )

        # Job returned as-is (state still 'failed' since it's the duplicate
        # that's already active, not this job being retried)
        assert result is job


# ---------------------------------------------------------------------------
# Test: Recover stale leases
# ---------------------------------------------------------------------------

class TestRecoverStaleLeases:
    """Recover stale leases: expired-lease running→queued / →failed."""

    @pytest.mark.asyncio
    async def test_recover_running_to_queued(self):
        """Expired-lease running job within max_attempts → queued."""
        db = _mock_db()
        now = datetime.now(timezone.utc)
        stale_job = _make_job(
            state=OcrState.running.value,
            attempt_count=2,
            max_attempts=5,
            lease_expires_at=now - timedelta(minutes=20),
            lease_owner="worker-1",
        )

        # Mock execute: first call returns stale jobs, second for transition
        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Return stale jobs list
                result = AsyncMock()
                scalars_mock = MagicMock()
                scalars_mock.all = MagicMock(return_value=[stale_job])
                result.scalars = MagicMock(return_value=scalars_mock)
                return result
            return _mock_execute_result(None)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        recovered = await svc.recover_stale_leases(max_age=timedelta(minutes=15))

        assert len(recovered) == 1
        assert recovered[0] == stale_job.id
        assert stale_job.state == OcrState.queued.value
        assert stale_job.lease_owner is None
        assert stale_job.lease_expires_at is None
        assert stale_job.next_retry_at is not None

    @pytest.mark.asyncio
    async def test_recover_running_to_failed_at_max_attempts(self):
        """Expired-lease running job at max_attempts → failed."""
        db = _mock_db()
        now = datetime.now(timezone.utc)
        stale_job = _make_job(
            state=OcrState.running.value,
            attempt_count=5,
            max_attempts=5,
            lease_expires_at=now - timedelta(minutes=20),
            lease_owner="worker-1",
        )

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                result = AsyncMock()
                scalars_mock = MagicMock()
                scalars_mock.all = MagicMock(return_value=[stale_job])
                result.scalars = MagicMock(return_value=scalars_mock)
                return result
            return _mock_execute_result(None)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        recovered = await svc.recover_stale_leases(max_age=timedelta(minutes=15))

        assert len(recovered) == 1
        assert recovered[0] == stale_job.id
        assert stale_job.state == OcrState.failed.value
        assert stale_job.error_code == "LEASE_EXPIRED_MAX_ATTEMPTS"
        assert stale_job.lease_owner is None
        assert stale_job.lease_expires_at is None

    @pytest.mark.asyncio
    async def test_recover_no_stale_jobs(self):
        """No stale jobs → empty list."""
        db = _mock_db()

        async def mock_execute(stmt):
            result = AsyncMock()
            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=[])
            result.scalars = MagicMock(return_value=scalars_mock)
            return result

        db.execute = mock_execute

        svc = OCRRetryService(db)
        recovered = await svc.recover_stale_leases()

        assert recovered == []


# ---------------------------------------------------------------------------
# Test: is_retry_eligible
# ---------------------------------------------------------------------------

class TestIsRetryEligible:
    """is_retry_eligible checks."""

    @pytest.mark.asyncio
    async def test_eligible_failed_within_max(self):
        db = _mock_db()
        job = _make_job(state=OcrState.failed.value, attempt_count=2, max_attempts=5)

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: load job (no FOR UPDATE here)
                return _mock_execute_result(job)
            else:
                # Second call: _has_active_duplicate → returns 0
                return _mock_execute_result(0)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        assert await svc.is_retry_eligible(job.id) is True

    @pytest.mark.asyncio
    async def test_not_eligible_at_max_attempts(self):
        db = _mock_db()
        job = _make_job(state=OcrState.failed.value, attempt_count=5, max_attempts=5)

        async def mock_execute(stmt):
            return _mock_execute_result(job)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        assert await svc.is_retry_eligible(job.id) is False

    @pytest.mark.asyncio
    async def test_not_eligible_wrong_state(self):
        db = _mock_db()
        job = _make_job(state=OcrState.running.value)

        async def mock_execute(stmt):
            return _mock_execute_result(job)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        assert await svc.is_retry_eligible(job.id) is False

    @pytest.mark.asyncio
    async def test_not_eligible_job_not_found(self):
        db = _mock_db()

        async def mock_execute(stmt):
            return _mock_execute_result(None)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        assert await svc.is_retry_eligible(uuid.uuid4()) is False


# ---------------------------------------------------------------------------
# Test: Service Identity bounded retry
# ---------------------------------------------------------------------------

class TestServiceIdentityRetry:
    """Service Identity has bounded auto-retry (conditional permission)."""

    @pytest.mark.asyncio
    async def test_service_identity_can_retry(self):
        """Service Identity has conditional ocr.retry (bounded auto-retry)."""
        db = _mock_db()
        job = _make_job(state=OcrState.failed.value, attempt_count=1, max_attempts=5)

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_execute_result(job)
            else:
                return _mock_execute_result(0)

        db.execute = mock_execute

        svc = OCRRetryService(db)
        actor = _make_actor_service()

        result = await svc.retry_failed_job(
            job_id=job.id,
            actor=actor,
            actor_role="service",  # Service Identity role
        )

        assert result.state == OcrState.queued.value
