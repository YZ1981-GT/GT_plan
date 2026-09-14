"""OCRGovernanceOrchestrator — 持久 OCR Job 编排层（Task 5.1, Wave 4）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R5, R12, R15
Design: §3.2 OCRGovernanceOrchestrator, §4.5 OCR 模型, §5.2 OCR 决策与写回
Properties: P9 (OCR 状态机封闭), P10 (重试授权 / 幂等复用), P25 (command-root 唯一)

本 orchestrator **只负责** 持久 Job、状态机、lease、attempt 与 transition；
**不** 实现 OCR 识别算法——实际识别由 worker 调用既有 ``UnifiedOCRService`` 完成。

核心流程:
1. ``submit_ocr_job`` — 幂等创建/复用绑定版本+hash+config 的 OCRJob，enqueue outbox。
2. ``acquire_lease`` — worker 在处理前获取 lease（queued→running）。
3. ``record_transition`` — 记录每次合法状态迁移 + 审计。
4. ``complete_recognition`` — running→awaiting_confirmation（结果由 worker 另存 OCRResult）。
5. ``fail_job`` — queued/running→failed。

事务边界: 本 service 只 ``flush``；facade/worker 管理 commit。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence_governance_models import OcrJob, OcrJobTransition
from app.services.evidence_governance.contracts import (
    OCR_TRANSITIONS,
    OcrState,
    is_legal_ocr_transition,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
    content_hash_of,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default lease duration (worker must complete within this window).
DEFAULT_LEASE_DURATION = timedelta(minutes=10)

#: Default maximum attempts before permanent failure.
DEFAULT_MAX_ATTEMPTS = 5

#: States considered "active" for idempotent reuse (R5.4).
_ACTIVE_REUSE_STATES: frozenset[str] = frozenset({
    OcrState.queued.value,
    OcrState.running.value,
    OcrState.awaiting_confirmation.value,
    OcrState.confirmed.value,
    OcrState.written_back.value,
})


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


def compute_idempotency_key(
    attachment_version_id: uuid.UUID,
    content_hash: str,
    parse_config: dict | None,
) -> str:
    """Derive idempotency key from (attachment_version_id, content_hash, parse_config_hash).

    Same attachment_version + content_hash + parse_config → same idempotency key (R5.4).
    None config uses literal "null"; empty dict {} hashes to its canonical JSON form.
    """
    parse_config_hash = content_hash_of(parse_config) if parse_config is not None else "null"
    return content_hash_of({
        "attachment_version_id": str(attachment_version_id),
        "content_hash": content_hash,
        "parse_config_hash": parse_config_hash,
    })


# ---------------------------------------------------------------------------
# OCRGovernanceOrchestrator
# ---------------------------------------------------------------------------

class OCRGovernanceOrchestrator:
    """持久 OCR Job 编排：创建/复用 Job，管理 lease、attempt、状态迁移和 transition。

    只负责 governance 持久化——不实现识别算法（worker 调 UnifiedOCRService）。
    只 flush，不 commit（facade/worker 管理事务边界）。
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # submit_ocr_job — 幂等创建/复用 Job (R5.1, R5.4)
    # ------------------------------------------------------------------

    async def submit_ocr_job(
        self,
        *,
        project_id: uuid.UUID,
        audit_year: int | None,
        attachment_id: uuid.UUID,
        attachment_version_id: uuid.UUID,
        content_hash: str,
        parse_config: dict | None = None,
        parse_config_version: str | None = None,
        actor: ActorContext,
        command_root_id: uuid.UUID | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> tuple[OcrJob, bool]:
        """幂等提交 OCR Job。

        Returns:
            (job, created): ``created=True`` → 新建；``False`` → 复用既有活动/完成 Job (R5.4)。

        idempotency_key = f(attachment_version_id, content_hash, parse_config_hash)。
        同一 key 若已有非 failed 的 Job → 幂等复用，不重复消费或覆盖历史结果。
        """
        idempotency_key = compute_idempotency_key(
            attachment_version_id, content_hash, parse_config
        )

        # Check for existing active/completed job (R5.4)
        existing = await self._find_reusable_job(
            project_id=project_id,
            audit_year=audit_year,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return existing, False

        # Create new Job in state=queued
        job = OcrJob(
            id=uuid.uuid4(),
            project_id=project_id,
            audit_year=audit_year,
            attachment_id=attachment_id,
            attachment_version_id=attachment_version_id,
            content_hash=content_hash,
            parse_config=parse_config,
            parse_config_version=parse_config_version,
            idempotency_key=idempotency_key,
            state=OcrState.queued.value,
            progress=0,
            attempt_count=0,
            max_attempts=max_attempts,
            command_root_id=command_root_id,
            **_actor_columns(actor),
        )
        self._db.add(job)
        await self._db.flush()

        # Record initial transition (queued)
        await self._record_transition_internal(
            ocr_job_id=job.id,
            from_state=None,
            to_state=OcrState.queued.value,
            actor=actor,
            command_root_id=command_root_id,
        )

        return job, True

    # ------------------------------------------------------------------
    # acquire_lease — worker 获取 lease (queued→running)
    # ------------------------------------------------------------------

    async def acquire_lease(
        self,
        *,
        job_id: uuid.UUID,
        lease_owner: str,
        actor: ActorContext,
        command_root_id: uuid.UUID | None = None,
        lease_duration: timedelta = DEFAULT_LEASE_DURATION,
    ) -> OcrJob:
        """Worker 获取 lease 并将 Job 从 queued→running。

        - Sets lease_owner, lease_expires_at.
        - Increments attempt_count.
        - Transitions state queued→running (P9).
        - If attempt_count > max_attempts, raises (bounded retry, R15.4).

        Raises:
            EvidenceGovernanceError: INVALID_STATE_TRANSITION if not in 'queued'.
        """
        job = await self._get_job_for_update(job_id)

        # Validate transition queued→running (P9)
        if job.state != OcrState.queued.value:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                f"Cannot acquire lease: job state is '{job.state}', expected 'queued'",
            )

        # Bounded retries (R15.4)
        new_attempt = (job.attempt_count or 0) + 1
        if new_attempt > job.max_attempts:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                f"Max attempts ({job.max_attempts}) exceeded",
            )

        now = datetime.now(timezone.utc)
        job.state = OcrState.running.value
        job.attempt_count = new_attempt
        job.lease_owner = lease_owner
        job.lease_expires_at = now + lease_duration
        job.updated_at = now

        await self._db.flush()

        # Record transition
        await self._record_transition_internal(
            ocr_job_id=job.id,
            from_state=OcrState.queued.value,
            to_state=OcrState.running.value,
            actor=actor,
            command_root_id=command_root_id,
        )

        return job

    # ------------------------------------------------------------------
    # record_transition — 通用合法状态迁移 (P9)
    # ------------------------------------------------------------------

    async def record_transition(
        self,
        *,
        job_id: uuid.UUID,
        to_state: str,
        actor: ActorContext,
        command_root_id: uuid.UUID | None = None,
        progress: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> OcrJob:
        """Validate and apply a state transition (P9 — closed state machine).

        Only transitions defined in ``OCR_TRANSITIONS`` are allowed. Illegal
        transitions raise ``INVALID_STATE_TRANSITION`` and leave state unchanged.
        """
        job = await self._get_job_for_update(job_id)
        from_state = job.state

        if not is_legal_ocr_transition(from_state, to_state):
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                f"Transition '{from_state}'→'{to_state}' is not allowed",
            )

        now = datetime.now(timezone.utc)
        job.state = to_state
        job.updated_at = now
        if progress is not None:
            job.progress = progress
        if error_code is not None:
            job.error_code = error_code
        if error_message is not None:
            job.error_message = error_message

        await self._db.flush()

        await self._record_transition_internal(
            ocr_job_id=job.id,
            from_state=from_state,
            to_state=to_state,
            actor=actor,
            command_root_id=command_root_id,
            progress=progress,
            error_code=error_code,
            error_message=error_message,
        )

        return job

    # ------------------------------------------------------------------
    # complete_recognition — running→awaiting_confirmation
    # ------------------------------------------------------------------

    async def complete_recognition(
        self,
        *,
        job_id: uuid.UUID,
        actor: ActorContext,
        command_root_id: uuid.UUID | None = None,
        progress: int = 100,
    ) -> OcrJob:
        """Worker 完成识别后调用：running→awaiting_confirmation。

        结果本身存 OCRResult（不由本方法处理），本方法只推进状态。
        """
        return await self.record_transition(
            job_id=job_id,
            to_state=OcrState.awaiting_confirmation.value,
            actor=actor,
            command_root_id=command_root_id,
            progress=progress,
        )

    # ------------------------------------------------------------------
    # fail_job — queued/running→failed
    # ------------------------------------------------------------------

    async def fail_job(
        self,
        *,
        job_id: uuid.UUID,
        actor: ActorContext,
        command_root_id: uuid.UUID | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> OcrJob:
        """将 Job 置为 failed（queued/running→failed）。

        保留已有结果和历史（P11）；记录错误详情供审计。
        """
        job = await self._get_job_for_update(job_id)
        from_state = job.state

        # Only queued/running may fail (P9)
        if from_state not in (OcrState.queued.value, OcrState.running.value):
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                f"Cannot fail job in state '{from_state}': only queued/running→failed allowed",
            )

        now = datetime.now(timezone.utc)
        job.state = OcrState.failed.value
        job.updated_at = now
        job.error_code = error_code
        job.error_message = error_message
        # Clear lease on failure
        job.lease_owner = None
        job.lease_expires_at = None

        await self._db.flush()

        await self._record_transition_internal(
            ocr_job_id=job.id,
            from_state=from_state,
            to_state=OcrState.failed.value,
            actor=actor,
            command_root_id=command_root_id,
            error_code=error_code,
            error_message=error_message,
        )

        return job

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _find_reusable_job(
        self,
        *,
        project_id: uuid.UUID,
        audit_year: int | None,
        idempotency_key: str,
    ) -> OcrJob | None:
        """Find existing active/completed Job for idempotent reuse (R5.4)."""
        stmt = (
            sa.select(OcrJob)
            .where(
                OcrJob.project_id == project_id,
                OcrJob.audit_year.is_not_distinct_from(audit_year),
                OcrJob.idempotency_key == idempotency_key,
                OcrJob.state.in_(_ACTIVE_REUSE_STATES),
            )
            .order_by(OcrJob.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_job_for_update(self, job_id: uuid.UUID) -> OcrJob:
        """Load Job with FOR UPDATE lock (prevents concurrent state changes)."""
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

    async def _record_transition_internal(
        self,
        *,
        ocr_job_id: uuid.UUID,
        from_state: str | None,
        to_state: str,
        actor: ActorContext,
        command_root_id: uuid.UUID | None = None,
        progress: int | None = None,
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
            progress=progress,
            error_code=error_code,
            error_message=error_message,
            **_actor_columns(actor),
        )
        self._db.add(transition)
        await self._db.flush()
        return transition


__all__ = [
    "OCRGovernanceOrchestrator",
    "compute_idempotency_key",
    "DEFAULT_LEASE_DURATION",
    "DEFAULT_MAX_ATTEMPTS",
]
