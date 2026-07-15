"""OCRRetryService — 封闭 OCR state CAS + ocr.retry 权限 + 有界退避 + 重启恢复（Task 5.2, Wave 4）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R5, R12, R15
Design: §2.2 Capability 基线 (ocr.retry), §4.5 OCR 模型, §5.2 OCR 决策与写回
Properties: P9 (状态机封闭), P10 (重试授权 / 幂等), P25 (command-root)

职责:
1. ``retry_failed_job`` — 授权重试 failed→queued（P10: 越权零副作用）。
2. ``recover_stale_leases`` — 重启恢复过期 lease 的 running 任务（R5.1）。
3. ``compute_next_retry_at`` — 有界指数退避（R15.4）。
4. ``is_retry_eligible`` — 重试资格判断（attempt < max，非 already queued/running）。

事务边界: 只 flush，不 commit（facade/worker 管理事务）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence_governance_models import OcrJob, OcrJobTransition
from app.services.evidence_governance.capability_guard import CapabilityGuard
from app.services.evidence_governance.contracts import OcrState, is_legal_ocr_transition
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.role_capability_contract import Capability

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Base delay for exponential backoff (seconds).
DEFAULT_BASE_DELAY_SECONDS: float = 30.0

#: Maximum delay cap for exponential backoff (seconds).
DEFAULT_MAX_DELAY_SECONDS: float = 3600.0  # 1 hour

#: Default maximum retry attempts before permanent failure.
DEFAULT_MAX_ATTEMPTS: int = 5

#: Default lease age for stale recovery (how old an expired lease must be
#: before it's considered stale and eligible for recovery).
DEFAULT_STALE_LEASE_AGE = timedelta(minutes=15)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _actor_columns(actor: ActorContext) -> dict:
    """Map ActorContext to ORM column dict."""
    return {
        "actor_type": actor.actor_type.value,
        "actor_user_id": actor.actor_user_id,
        "actor_service_identity_id": actor.actor_service_identity_id,
    }


# ---------------------------------------------------------------------------
# OCRRetryService
# ---------------------------------------------------------------------------

class OCRRetryService:
    """封闭 OCR state CAS + ocr.retry 权限 + 有界退避 + 重启恢复 + 重复调度抑制。

    核心不变量:
    - P9: 只允许 failed→queued 重试迁移。
    - P10: 越权重试零副作用（状态不变、无 transition、无 outbox 事件）。
    - R15.4: 超限后永久失败。
    - R5.1: 重启恢复过期 lease。
    - R5.4: 重复调度抑制（已 queued/running 不重复入队）。
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
        max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
    ) -> None:
        self._db = db
        self._capability_guard = CapabilityGuard()
        self._base_delay = base_delay_seconds
        self._max_delay = max_delay_seconds

    # ------------------------------------------------------------------
    # retry_failed_job — authorized retry (failed→queued) with bounded backoff
    # ------------------------------------------------------------------

    async def retry_failed_job(
        self,
        *,
        job_id: uuid.UUID,
        actor: ActorContext,
        actor_role: str,
        command_root_id: uuid.UUID | None = None,
    ) -> OcrJob:
        """Retry a failed OCR job (failed→queued).

        Validates (IN ORDER — first failure aborts with zero side effects):
        1. Actor has ocr.retry capability (P10: unauthorized → zero effects).
        2. Job exists and is in 'failed' state (P9: closed state machine).
        3. attempt_count < max_attempts (R15.4: bounded retries).
        4. Job is not already queued/running (R5.4: duplicate suppression).

        On unauthorized retry: ZERO side effects (P10) — no state change,
        no transition recorded, no outbox event.

        Returns:
            The job with state updated to 'queued' and next_retry_at set.

        Raises:
            EvidenceGovernanceError: SCOPE_NOT_FOUND_OR_FORBIDDEN (unauthorized)
            EvidenceGovernanceError: INVALID_STATE_TRANSITION (wrong state / max exceeded)
        """
        # 1. Capability check BEFORE any state change (P10: zero effects on denial)
        self._capability_guard.authorize(
            actor_role,
            Capability.ocr_retry.value,
            actor=actor,
        )

        # 2. Load job with FOR UPDATE lock
        job = await self._get_job_for_update(job_id)

        # 3. Check state is 'failed' (P9: only failed→queued allowed for retry)
        if job.state != OcrState.failed.value:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                f"Cannot retry job in state '{job.state}': only 'failed' jobs can be retried",
            )

        # 4. Bounded retries — attempt_count < max_attempts (R15.4)
        current_attempts = job.attempt_count or 0
        if current_attempts >= (job.max_attempts or DEFAULT_MAX_ATTEMPTS):
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                f"Max attempts ({job.max_attempts}) reached; job is permanently failed",
            )

        # 5. Duplicate dispatch suppression (R5.4): check if there's already an
        #    active job with the same idempotency_key in queued/running state.
        #    This prevents re-enqueuing when the same retry is submitted twice.
        if await self._has_active_duplicate(job):
            # Idempotent return: job already queued/running, no-op
            return job

        # --- All checks passed: apply state transition ---
        now = datetime.now(timezone.utc)
        next_retry_at = self.compute_next_retry_at(current_attempts + 1)

        job.state = OcrState.queued.value
        job.updated_at = now
        job.next_retry_at = next_retry_at
        # Clear error state from previous failure
        job.error_code = None
        job.error_message = None
        # Clear lease from previous attempt
        job.lease_owner = None
        job.lease_expires_at = None

        await self._db.flush()

        # Record transition (append-only audit trail)
        await self._record_transition(
            ocr_job_id=job.id,
            from_state=OcrState.failed.value,
            to_state=OcrState.queued.value,
            actor=actor,
            command_root_id=command_root_id,
        )

        return job

    # ------------------------------------------------------------------
    # recover_stale_leases — restart recovery (R5.1)
    # ------------------------------------------------------------------

    async def recover_stale_leases(
        self,
        *,
        max_age: timedelta = DEFAULT_STALE_LEASE_AGE,
        service_actor: ActorContext | None = None,
    ) -> list[uuid.UUID]:
        """Recovery scan: reset expired-lease running jobs to queued.

        Called on worker startup. Resets jobs where:
        - state='running'
        - lease_expires_at < now (expired)
        - lease has been expired for at least ``max_age``

        Jobs at or exceeding max_attempts → set to 'failed' instead of queued.
        Jobs not exceeding max_attempts → set to 'queued' with next_retry_at.

        Returns:
            List of job IDs that were recovered (either to queued or failed).
        """
        now = datetime.now(timezone.utc)
        cutoff = now - max_age

        # Find all running jobs with expired leases
        stmt = (
            sa.select(OcrJob)
            .where(
                OcrJob.state == OcrState.running.value,
                OcrJob.lease_expires_at.isnot(None),
                OcrJob.lease_expires_at < cutoff,
            )
            .with_for_update(skip_locked=True)
        )
        result = await self._db.execute(stmt)
        stale_jobs: list[OcrJob] = list(result.scalars().all())

        recovered_ids: list[uuid.UUID] = []
        actor = service_actor or ActorContext.for_service(
            uuid.UUID("00000000-0000-0000-0000-000000000001")  # system recovery identity
        )

        for job in stale_jobs:
            current_attempts = job.attempt_count or 0
            max_attempts = job.max_attempts or DEFAULT_MAX_ATTEMPTS

            if current_attempts >= max_attempts:
                # Exceeded max attempts → permanent failure
                job.state = OcrState.failed.value
                job.error_code = "LEASE_EXPIRED_MAX_ATTEMPTS"
                job.error_message = (
                    f"Lease expired and max attempts ({max_attempts}) reached"
                )
            else:
                # Still retriable → reset to queued
                job.state = OcrState.queued.value
                job.next_retry_at = self.compute_next_retry_at(current_attempts + 1)

            job.updated_at = now
            job.lease_owner = None
            job.lease_expires_at = None

            await self._db.flush()

            # Record recovery transition
            to_state = job.state
            await self._record_transition(
                ocr_job_id=job.id,
                from_state=OcrState.running.value,
                to_state=to_state,
                actor=actor,
                command_root_id=None,
                error_code="LEASE_RECOVERY" if to_state == OcrState.queued.value else "LEASE_EXPIRED_MAX_ATTEMPTS",
                error_message=f"Recovered stale lease (expired at {cutoff.isoformat()})",
            )

            recovered_ids.append(job.id)

        return recovered_ids

    # ------------------------------------------------------------------
    # compute_next_retry_at — exponential backoff with cap (R15.4)
    # ------------------------------------------------------------------

    def compute_next_retry_at(self, attempt_count: int) -> datetime:
        """Exponential backoff: min(base_delay * 2^(attempt-1), max_delay).

        Args:
            attempt_count: The attempt number (1-based) that will run next.

        Returns:
            The earliest datetime when the job becomes eligible for pickup.
        """
        delay_seconds = min(
            self._base_delay * (2 ** (attempt_count - 1)),
            self._max_delay,
        )
        return datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)

    # ------------------------------------------------------------------
    # is_retry_eligible — eligibility check
    # ------------------------------------------------------------------

    async def is_retry_eligible(self, job_id: uuid.UUID) -> bool:
        """Check if job can be retried (not at max, not already queued/running).

        This is a read-only check — no state changes, no locks.
        """
        stmt = sa.select(OcrJob).where(OcrJob.id == job_id)
        result = await self._db.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            return False

        # Must be in failed state
        if job.state != OcrState.failed.value:
            return False

        # Must not have exceeded max attempts
        current_attempts = job.attempt_count or 0
        max_attempts = job.max_attempts or DEFAULT_MAX_ATTEMPTS
        if current_attempts >= max_attempts:
            return False

        # Must not already have an active duplicate
        if await self._has_active_duplicate(job):
            return False

        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_job_for_update(self, job_id: uuid.UUID) -> OcrJob:
        """Load Job with FOR UPDATE lock."""
        stmt = (
            sa.select(OcrJob)
            .where(OcrJob.id == job_id)
            .with_for_update()
        )
        result = await self._db.execute(stmt)
        job = result.scalar_one_or_none()
        if job is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "OCR job not found",
            )
        return job

    async def _has_active_duplicate(self, job: OcrJob) -> bool:
        """Check if there's already an active (queued/running) job with same idempotency_key.

        Duplicate suppression (R5.4): if a job is already queued or running,
        a retry request should not create a second queue entry.
        """
        if not job.idempotency_key:
            return False

        stmt = (
            sa.select(sa.func.count())
            .select_from(OcrJob)
            .where(
                OcrJob.project_id == job.project_id,
                OcrJob.idempotency_key == job.idempotency_key,
                OcrJob.state.in_([OcrState.queued.value, OcrState.running.value]),
                OcrJob.id != job.id,  # exclude self
            )
        )
        result = await self._db.execute(stmt)
        count = result.scalar_one()
        return count > 0

    async def _record_transition(
        self,
        *,
        ocr_job_id: uuid.UUID,
        from_state: str,
        to_state: str,
        actor: ActorContext,
        command_root_id: uuid.UUID | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> OcrJobTransition:
        """Append a transition row (append-only audit trail)."""
        transition = OcrJobTransition(
            id=uuid.uuid4(),
            ocr_job_id=ocr_job_id,
            command_root_id=command_root_id,
            from_state=from_state,
            to_state=to_state,
            error_code=error_code,
            error_message=error_message,
            **_actor_columns(actor),
        )
        self._db.add(transition)
        await self._db.flush()
        return transition


__all__ = [
    "OCRRetryService",
    "DEFAULT_BASE_DELAY_SECONDS",
    "DEFAULT_MAX_DELAY_SECONDS",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_STALE_LEASE_AGE",
]
