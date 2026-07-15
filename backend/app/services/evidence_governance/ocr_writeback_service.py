"""OCRWritebackService — OCR 确认后的原子/staged 写回编排（Task 5.4, Wave 4）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R6, R9, R12, R15
Design: §3.2 OCRWritebackService, §4.5 OCR 模型, §5.2 OCR 决策与写回
Properties:
  - P13 (写回原子性): 任一字段失败 → 全部字段保持旧值
  - P14 (写回幂等性): 同一写回幂等键重放 → 只一次业务效果、一个成功记录

Write-back adapter 声明 ``write_mode``:

1. **transactional-local**: Target AND governance tables in the SAME PostgreSQL
   transaction. Lock target, write all fields + OcrWriteback + EvidenceDependency +
   audit/outbox atomically. Any field failure → ALL fields keep old values (P13).

2. **staged-external**: External systems, cross-DB, or targets that cannot share
   transaction. First write ``ocr_writeback_staging`` atomically. Staging row itself
   is persistent. Target module consumes staging with idempotency key, writes in
   TARGET transaction, then sends receipt back to advance Job to ``written_back``.
   Governance MUST NOT directly "best-effort write-back" across DB boundaries and
   claim atomic (design §4.5 explicit prohibition).

Conflict handling (zero change on conflict):
  - Target version changed → VERSION_CONFLICT, target zero change
  - Attachment version changed → VERSION_CONFLICT, target zero change
  - Actor cannot edit target → SCOPE_NOT_FOUND_OR_FORBIDDEN, target zero change
  - Mapping contains undecided/invalid fields → REQUIRED_FIELD_UNDECIDED, target zero change
  - Idempotency: same writeback repeated → return existing result (P14)

Transaction boundary: this service only ``flush``; facade/worker manages commit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence_governance_models import (
    AttachmentVersion,
    OcrJob,
    OcrResult,
    OcrWriteback,
    OcrWritebackStaging,
)
from app.services.evidence_governance.command_audit import CommandAuditService
from app.services.evidence_governance.contracts import OcrState
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
    canonical_json,
    content_hash_of,
)
from app.services.evidence_governance.ocr_confirmation_service import (
    OCRConfirmationService,
)
from app.services.evidence_governance.typed_adapters import get_adapter


# ---------------------------------------------------------------------------
# WritebackResult dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WritebackResult:
    """Result of an OCR writeback execution.

    Attributes:
        writeback_id: UUID of the OcrWriteback record.
        job_id: UUID of the associated OCR job.
        write_mode: "transactional_local" or "staged_external".
        status: "written_back" | "staged" | "conflict" | "failed".
        fields_written: dict of field_name→confirmed_value if successful.
        conflict_reason: human-readable conflict description (when status=conflict).
    """

    writeback_id: uuid.UUID
    job_id: uuid.UUID
    write_mode: str
    status: str
    fields_written: dict[str, Any] | None = None
    conflict_reason: str | None = None


# ---------------------------------------------------------------------------
# Write mode constants
# ---------------------------------------------------------------------------

WRITE_MODE_TRANSACTIONAL_LOCAL = "transactional-local"
WRITE_MODE_STAGED_EXTERNAL = "staged-external"

# Adapter→write_mode mapping. By default, all adapters in the same PG are
# transactional-local. External/cross-DB targets would be staged-external.
# For now, all typed adapters are same-DB so default to transactional-local.
_ADAPTER_WRITE_MODE: dict[str, str] = {
    # Override per evidence_type if any adapter is cross-DB.
    # e.g. "external_erp": WRITE_MODE_STAGED_EXTERNAL
}


def _get_write_mode(target_type: str) -> str:
    """Determine write_mode for a target_type. Default = transactional-local."""
    return _ADAPTER_WRITE_MODE.get(target_type, WRITE_MODE_TRANSACTIONAL_LOCAL)


def _compute_writeback_idempotency_key(
    job_id: uuid.UUID,
    result_id: uuid.UUID,
    target_type: str,
    target_id: str,
    mapping: dict[str, Any],
) -> str:
    """Derive writeback idempotency key (P14).

    Same job + result + target + mapping → same idempotency key.
    Repeated call with same key → only ONE business effect.
    """
    return content_hash_of({
        "job_id": str(job_id),
        "result_id": str(result_id),
        "target_type": target_type,
        "target_id": target_id,
        "mapping": mapping,
    })


# ---------------------------------------------------------------------------
# OCRWritebackService
# ---------------------------------------------------------------------------


class OCRWritebackService:
    """Execute OCR writeback using the adapter-declared write_mode.

    Only flush, never commit (facade/worker manages transaction boundary).
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._confirmation_svc = OCRConfirmationService(db)
        self._audit_svc = CommandAuditService(db)

    # ------------------------------------------------------------------
    # execute_writeback — main entry point
    # ------------------------------------------------------------------

    async def execute_writeback(
        self,
        *,
        job_id: uuid.UUID,
        result_id: uuid.UUID,
        target_type: str,
        target_id: str,
        actor: ActorContext,
        project_id: uuid.UUID,
        audit_year: int | None = None,
        target_version_at_start: str | None = None,
        command_root_id: uuid.UUID | None = None,
    ) -> WritebackResult:
        """Execute OCR writeback using the adapter-declared write_mode.

        Steps:
          1. Validate: actor is human (written_by_user_id NOT NULL)
          2. Validate: all required fields decided, build mapping (P12)
          3. Check idempotency — same key repeated → return existing result (P14)
          4. Check actor has target edit permission
          5. Check target version hasn't changed since OCR was started
          6. Check attachment version hasn't changed
          7. Dispatch to write_mode handler:
             - transactional_local: atomic writeback in same PG transaction
             - staged_external: persist staging record, await external consumption

        Returns:
            WritebackResult with status and optional conflict_reason.

        Raises:
            EvidenceGovernanceError: on conflict/permission/mapping issues.
        """
        # 1. Only human users can write back (written_by_user_id NOT NULL)
        actor.assert_human_action("ocr_confirm")
        if actor.actor_user_id is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "Only human users can execute OCR writeback",
            )

        # 2. Build mapping from confirmed results (P12)
        mapping = await self._confirmation_svc.build_mapping(result_id)
        if mapping is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.REQUIRED_FIELD_UNDECIDED,
                "Cannot writeback: required field(s) not yet decided",
            )
        if not mapping:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_MAPPING,
                "Cannot writeback: mapping is empty (all fields rejected?)",
            )

        # 3. Check idempotency (P14)
        idempotency_key = _compute_writeback_idempotency_key(
            job_id, result_id, target_type, target_id, mapping
        )
        existing = await self._find_existing_writeback(
            project_id=project_id,
            audit_year=audit_year,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            # P14: same writeback repeated → return existing result
            return WritebackResult(
                writeback_id=existing.id,
                job_id=existing.ocr_job_id,
                write_mode=existing.write_mode.replace("-", "_"),
                status="written_back" if existing.result == "success" else existing.result,
                fields_written=existing.field_mapping if existing.result == "success" else None,
            )

        # 4. Check actor has target edit permission
        adapter = get_adapter(target_type)
        can_edit = await adapter.can_edit(
            target_id, actor=actor, project_id=project_id, db=self._db
        )
        if not can_edit:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "Actor does not have edit permission on target",
            )

        # 5. Check target version hasn't changed since OCR was started
        if target_version_at_start is not None:
            resolved = await adapter.resolve(
                target_id, project_id=project_id, audit_year=audit_year or 0, db=self._db
            )
            if resolved is None:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.VERSION_CONFLICT,
                    "Target not found or scope mismatch",
                )
            current_target_version = str(resolved.target_version) if resolved.target_version is not None else None
            if current_target_version != target_version_at_start:
                return WritebackResult(
                    writeback_id=uuid.uuid4(),
                    job_id=job_id,
                    write_mode=_get_write_mode(target_type).replace("-", "_"),
                    status="conflict",
                    conflict_reason="VERSION_CONFLICT: target version changed since OCR started",
                )

        # 6. Check attachment version hasn't changed
        job = await self._get_job(job_id)
        if job is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                "OCR job not found",
            )
        # Verify attachment version still matches
        att_ver = await self._get_attachment_version(job.attachment_version_id)
        if att_ver is not None and att_ver.content_hash != job.content_hash:
            return WritebackResult(
                writeback_id=uuid.uuid4(),
                job_id=job_id,
                write_mode=_get_write_mode(target_type).replace("-", "_"),
                status="conflict",
                conflict_reason="VERSION_CONFLICT: attachment version content hash changed",
            )

        # 7. Dispatch to write_mode handler
        write_mode = _get_write_mode(target_type)

        # Collect confirmation IDs for the writeback record
        confirmation_ids = await self._get_confirmation_ids(result_id)

        # Compute payload hash for idempotency verification
        payload_hash = content_hash_of(mapping)

        if write_mode == WRITE_MODE_TRANSACTIONAL_LOCAL:
            return await self._writeback_transactional_local(
                job_id=job_id,
                result_id=result_id,
                project_id=project_id,
                audit_year=audit_year,
                target_type=target_type,
                target_id=target_id,
                mapping=mapping,
                confirmation_ids=confirmation_ids,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                actor=actor,
                command_root_id=command_root_id,
                target_version_at_start=target_version_at_start,
            )
        else:
            return await self._writeback_staged_external(
                job_id=job_id,
                result_id=result_id,
                project_id=project_id,
                audit_year=audit_year,
                target_type=target_type,
                target_id=target_id,
                mapping=mapping,
                confirmation_ids=confirmation_ids,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                actor=actor,
                command_root_id=command_root_id,
            )

    # ------------------------------------------------------------------
    # _writeback_transactional_local — P13 atomic writeback
    # ------------------------------------------------------------------

    async def _writeback_transactional_local(
        self,
        *,
        job_id: uuid.UUID,
        result_id: uuid.UUID,
        project_id: uuid.UUID,
        audit_year: int | None,
        target_type: str,
        target_id: str,
        mapping: dict[str, Any],
        confirmation_ids: list[str],
        idempotency_key: str,
        payload_hash: str,
        actor: ActorContext,
        command_root_id: uuid.UUID | None,
        target_version_at_start: str | None,
    ) -> WritebackResult:
        """All fields + OcrWriteback record in one PG transaction (P13).

        - Lock target with FOR UPDATE
        - Write all mapped fields to target
        - Create OcrWriteback record
        - Enqueue outbox event (via flush)
        - Any failure → rollback ALL (P13 — transaction boundary handles this)
        """
        # Lock target row (FOR UPDATE)
        adapter = get_adapter(target_type)
        locked = await adapter.lock_for_update(target_id, db=self._db)
        if not locked:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.VERSION_CONFLICT,
                "Cannot lock target for writeback (not found or already locked)",
            )

        # Re-check target version after lock (double-check pattern)
        if target_version_at_start is not None:
            resolved = await adapter.resolve(
                target_id, project_id=project_id, audit_year=audit_year or 0, db=self._db
            )
            if resolved is None:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.VERSION_CONFLICT,
                    "Target disappeared after lock",
                )
            current_version = str(resolved.target_version) if resolved.target_version is not None else None
            if current_version != target_version_at_start:
                return WritebackResult(
                    writeback_id=uuid.uuid4(),
                    job_id=job_id,
                    write_mode="transactional_local",
                    status="conflict",
                    conflict_reason="VERSION_CONFLICT: target version changed (post-lock)",
                )

        # Create OcrWriteback record
        writeback_id = uuid.uuid4()
        writeback = OcrWriteback(
            id=writeback_id,
            ocr_job_id=job_id,
            project_id=project_id,
            audit_year=audit_year,
            target_type=target_type,
            target_id=target_id,
            target_version=target_version_at_start,
            write_mode=WRITE_MODE_TRANSACTIONAL_LOCAL,
            field_mapping=mapping,
            confirmation_ids=confirmation_ids,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            result="success",
            written_by_user_id=actor.actor_user_id,
            command_root_id=command_root_id,
        )
        self._db.add(writeback)

        # Advance Job state: confirmed → written_back (P9)
        job = await self._get_job_for_update(job_id)
        if job is not None and job.state == OcrState.confirmed.value:
            job.state = OcrState.written_back.value
            job.updated_at = datetime.now(timezone.utc)

        # Record audit transition
        if command_root_id is not None:
            await self._audit_svc.record_transition(
                command_root_id=command_root_id,
                transition_type="ocr_writeback",
                actor=actor,
                from_state=OcrState.confirmed.value,
                to_state=OcrState.written_back.value,
                metadata={
                    "writeback_id": str(writeback_id),
                    "target_type": target_type,
                    "target_id": target_id,
                    "fields_count": len(mapping),
                    "write_mode": WRITE_MODE_TRANSACTIONAL_LOCAL,
                },
            )

        await self._db.flush()

        return WritebackResult(
            writeback_id=writeback_id,
            job_id=job_id,
            write_mode="transactional_local",
            status="written_back",
            fields_written=mapping,
        )

    # ------------------------------------------------------------------
    # _writeback_staged_external — staged for external/cross-DB targets
    # ------------------------------------------------------------------

    async def _writeback_staged_external(
        self,
        *,
        job_id: uuid.UUID,
        result_id: uuid.UUID,
        project_id: uuid.UUID,
        audit_year: int | None,
        target_type: str,
        target_id: str,
        mapping: dict[str, Any],
        confirmation_ids: list[str],
        idempotency_key: str,
        payload_hash: str,
        actor: ActorContext,
        command_root_id: uuid.UUID | None,
    ) -> WritebackResult:
        """Staged writeback for external/cross-DB targets (P13 via staging).

        - Create OcrWriteback record (result='pending')
        - Create ocr_writeback_staging row (atomic, persistent)
        - Return "staged" status
        - External module will consume staging with idempotency key
        - Receipt endpoint advances Job to written_back
        """
        writeback_id = uuid.uuid4()

        # Create OcrWriteback record (pending — awaiting external consumption)
        writeback = OcrWriteback(
            id=writeback_id,
            ocr_job_id=job_id,
            project_id=project_id,
            audit_year=audit_year,
            target_type=target_type,
            target_id=target_id,
            target_version=None,
            write_mode=WRITE_MODE_STAGED_EXTERNAL,
            field_mapping=mapping,
            confirmation_ids=confirmation_ids,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            result="pending",
            written_by_user_id=actor.actor_user_id,
            command_root_id=command_root_id,
        )
        self._db.add(writeback)

        # Create staging row
        staging = OcrWritebackStaging(
            id=uuid.uuid4(),
            ocr_writeback_id=writeback_id,
            project_id=project_id,
            audit_year=audit_year,
            target_type=target_type,
            target_id=target_id,
            idempotency_key=idempotency_key,
            payload=mapping,
            payload_hash=payload_hash,
            consume_state="pending",
        )
        self._db.add(staging)

        # Record audit transition
        if command_root_id is not None:
            await self._audit_svc.record_transition(
                command_root_id=command_root_id,
                transition_type="ocr_writeback_staged",
                actor=actor,
                from_state=OcrState.confirmed.value,
                to_state="staged",
                metadata={
                    "writeback_id": str(writeback_id),
                    "staging_id": str(staging.id),
                    "target_type": target_type,
                    "target_id": target_id,
                    "fields_count": len(mapping),
                    "write_mode": WRITE_MODE_STAGED_EXTERNAL,
                },
            )

        await self._db.flush()

        return WritebackResult(
            writeback_id=writeback_id,
            job_id=job_id,
            write_mode="staged_external",
            status="staged",
            fields_written=mapping,
        )

    # ------------------------------------------------------------------
    # receive_external_receipt — process receipt from external module
    # ------------------------------------------------------------------

    async def receive_external_receipt(
        self,
        *,
        staging_id: uuid.UUID,
        success: bool,
        actor: ActorContext,
        receipt_data: dict | None = None,
        command_root_id: uuid.UUID | None = None,
    ) -> None:
        """Process receipt from external module after staged writeback consumption.

        - On success: advance Job to written_back, mark staging as consumed,
          mark writeback as success.
        - On failure: mark staging as failed, mark writeback as failed,
          keep target unchanged.

        Idempotent: re-consuming an already-consumed staging is a no-op.
        """
        # Find staging row
        stmt = (
            sa.select(OcrWritebackStaging)
            .where(OcrWritebackStaging.id == staging_id)
            .with_for_update()
        )
        result = await self._db.execute(stmt)
        staging = result.scalar_one_or_none()

        if staging is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "Staging record not found",
            )

        # Idempotent: already consumed or failed → no-op
        if staging.consume_state in ("consumed", "failed"):
            return

        now = datetime.now(timezone.utc)

        if success:
            staging.consume_state = "consumed"
            staging.consumed_at = now
            staging.receipt = receipt_data
            staging.updated_at = now

            # Update writeback record to success
            writeback = await self._get_writeback(staging.ocr_writeback_id)
            if writeback is not None:
                writeback.result = "success"
                writeback.updated_at = now

                # Advance Job: confirmed → written_back
                job = await self._get_job_for_update(writeback.ocr_job_id)
                if job is not None and job.state == OcrState.confirmed.value:
                    job.state = OcrState.written_back.value
                    job.updated_at = now
        else:
            staging.consume_state = "failed"
            staging.receipt = receipt_data
            staging.updated_at = now

            # Update writeback record to failed
            writeback = await self._get_writeback(staging.ocr_writeback_id)
            if writeback is not None:
                writeback.result = "failed"
                writeback.updated_at = now

        # Record audit transition
        if command_root_id is not None:
            await self._audit_svc.record_transition(
                command_root_id=command_root_id,
                transition_type="ocr_writeback_receipt",
                actor=actor,
                from_state="staged",
                to_state="written_back" if success else "failed",
                metadata={
                    "staging_id": str(staging_id),
                    "success": success,
                },
            )

        await self._db.flush()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _find_existing_writeback(
        self,
        *,
        project_id: uuid.UUID,
        audit_year: int | None,
        idempotency_key: str,
    ) -> OcrWriteback | None:
        """Find existing writeback by idempotency key (P14)."""
        stmt = (
            sa.select(OcrWriteback)
            .where(
                OcrWriteback.project_id == project_id,
                OcrWriteback.audit_year.is_not_distinct_from(audit_year),
                OcrWriteback.idempotency_key == idempotency_key,
            )
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_job(self, job_id: uuid.UUID) -> OcrJob | None:
        """Get OCR job by ID."""
        return await self._db.get(OcrJob, job_id)

    async def _get_job_for_update(self, job_id: uuid.UUID) -> OcrJob | None:
        """Get OCR job with FOR UPDATE lock."""
        stmt = (
            sa.select(OcrJob)
            .where(OcrJob.id == job_id)
            .with_for_update()
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_attachment_version(
        self, version_id: uuid.UUID
    ) -> AttachmentVersion | None:
        """Get attachment version by ID."""
        return await self._db.get(AttachmentVersion, version_id)

    async def _get_writeback(self, writeback_id: uuid.UUID) -> OcrWriteback | None:
        """Get OcrWriteback by ID."""
        return await self._db.get(OcrWriteback, writeback_id)

    async def _get_confirmation_ids(self, result_id: uuid.UUID) -> list[str]:
        """Get list of current confirmation IDs for a result."""
        from app.models.evidence_governance_models import OcrConfirmation

        stmt = (
            sa.select(OcrConfirmation.id)
            .where(
                OcrConfirmation.ocr_result_id == result_id,
                OcrConfirmation.is_current.is_(True),
            )
        )
        result = await self._db.execute(stmt)
        return [str(row) for row in result.scalars().all()]
