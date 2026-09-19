"""OCRConfirmationService — immutable OCRResult + append-only confirmation (Task 5.3, Wave 4).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R6, R7, R12
Design: §4.5 OCR 模型, §5.2 OCR 决策与写回
Properties:
  - P11: OCR 原始结果不可变（确认/修正/写回不改变原识别值）
  - P12: 未确认不可写回（任一 required 未决定或拟 mapping 含 rejected → 目标零变化）

核心职责:
1. ``create_result``  — 创建不可变 OCRResult（P11: 创建后原值不可修改）。
2. ``add_confirmation`` — append-only 字段确认（人工用户 only，Service Identity 禁止）。
3. ``check_all_required_decided`` — 检查全部 required 字段是否已作决定。
4. ``build_mapping`` — 只从 current accepted/corrected 构造 mapping（rejected 排除）。
5. ``can_advance_to_confirmed`` — Job 是否可进入 confirmed 状态。

事务边界: 本 service 只 ``flush``；facade/worker 管理 commit。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence_governance_models import OcrConfirmation, OcrJob, OcrResult
from app.services.evidence_governance.contracts import (
    OCR_FIELD_DECISIONS,
    OCR_WRITEBACK_ELIGIBLE_DECISIONS,
    OcrState,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
    content_hash_of,
)


# ---------------------------------------------------------------------------
# OCRConfirmationService
# ---------------------------------------------------------------------------


class OCRConfirmationService:
    """Immutable OCRResult 管理 + append-only 人工确认修订。

    - OCRResult 创建后不可修改（P11: immutable 触发器由 DB 层保障）。
    - 每个 required 字段必须最终有 current accepted|corrected|rejected 决定。
    - rejected 满足 "required decided" 但永不进入字段 mapping。
    - Service Identity 不得执行人工确认（R6.2 / design §2.2）。
    - 只 flush，不 commit（facade/worker 管理事务边界）。
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # create_result — 创建不可变 OCR 结果 (R6.1 / P11)
    # ------------------------------------------------------------------

    async def create_result(
        self,
        *,
        ocr_job_id: uuid.UUID,
        project_id: uuid.UUID,
        audit_year: int | None,
        attachment_version_id: uuid.UUID,
        source_content_hash: str,
        raw_text: str | None = None,
        pages: dict | None = None,
        fields: dict | None = None,
        confidence: float | None = None,
        page: int | None = None,
        region: dict | None = None,
        engine: str | None = None,
        model_version: str | None = None,
        config_version: str | None = None,
        actor: ActorContext,
    ) -> OcrResult:
        """Create immutable OCR result after recognition completes.

        The result_hash is computed from (raw_text, pages, fields, confidence,
        page, region, engine, model_version, config_version) to guarantee
        content identity. Once created, original values cannot be modified (P11 —
        DB immutable trigger prevents UPDATE on these columns).
        """
        # Compute result hash from immutable fields
        result_hash = content_hash_of({
            "raw_text": raw_text,
            "pages": pages,
            "fields": fields,
            "confidence": float(confidence) if confidence is not None else None,
            "page": page,
            "region": region,
            "engine": engine,
            "model_version": model_version,
            "config_version": config_version,
        })

        result = OcrResult(
            id=uuid.uuid4(),
            ocr_job_id=ocr_job_id,
            project_id=project_id,
            audit_year=audit_year,
            attachment_version_id=attachment_version_id,
            source_content_hash=source_content_hash,
            raw_text=raw_text,
            pages=pages,
            fields=fields,
            confidence=confidence,
            page=page,
            region=region,
            engine=engine,
            model_version=model_version,
            config_version=config_version,
            result_hash=result_hash,
            actor_type=actor.actor_type.value,
            actor_user_id=actor.actor_user_id,
            actor_service_identity_id=actor.actor_service_identity_id,
        )
        self._db.add(result)
        await self._db.flush()
        return result

    # ------------------------------------------------------------------
    # add_confirmation — append-only field confirmation (R6.2 / P11 / P12)
    # ------------------------------------------------------------------

    async def add_confirmation(
        self,
        *,
        result_id: uuid.UUID,
        field_name: str,
        decision: str,
        confirmed_value: str | None = None,
        original_value: str | None = None,
        is_required: bool = True,
        actor: ActorContext,
    ) -> OcrConfirmation:
        """Append a field confirmation (accepted/corrected/rejected).

        Validates:
        - Actor is human (NOT Service Identity) — P11, R6.2, design §2.2
        - Decision is one of accepted/corrected/rejected
        - accepted/corrected must have confirmed_value
        - Appends to history (does NOT modify OCRResult original values — P11)

        Append-only semantics:
        - New confirmations set is_current=true for the field
        - Previous same-field confirmations are marked is_current=false
        - revision_no increments per field
        """
        # ── Validate actor is human (Service Identity cannot confirm) ──
        actor.assert_human_action("human_confirm")

        # ── Validate decision ──
        if decision not in OCR_FIELD_DECISIONS:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                f"Invalid OCR field decision: {decision!r}; "
                f"must be one of {sorted(OCR_FIELD_DECISIONS)}",
            )

        # ── accepted/corrected must have confirmed_value ──
        if decision in OCR_WRITEBACK_ELIGIBLE_DECISIONS and confirmed_value is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.METADATA_INCOMPLETE,
                f"Decision '{decision}' requires a confirmed_value",
            )

        # ── Load the OCR result to get job context ──
        result = await self._get_result(result_id)

        # ── Determine next revision_no for this field ──
        max_revision_stmt = (
            sa.select(sa.func.coalesce(sa.func.max(OcrConfirmation.revision_no), 0))
            .where(
                OcrConfirmation.ocr_result_id == result_id,
                OcrConfirmation.field_key == field_name,
            )
        )
        max_revision_result = await self._db.execute(max_revision_stmt)
        current_max = max_revision_result.scalar_one()
        next_revision = current_max + 1

        # ── Mark previous same-field confirmations as not current ──
        update_stmt = (
            sa.update(OcrConfirmation)
            .where(
                OcrConfirmation.ocr_result_id == result_id,
                OcrConfirmation.field_key == field_name,
                OcrConfirmation.is_current.is_(True),
            )
            .values(is_current=False)
        )
        await self._db.execute(update_stmt)
        # Flush the UPDATE before INSERT to satisfy partial unique constraint
        await self._db.flush()

        # ── Create new current confirmation ──
        confirmation = OcrConfirmation(
            id=uuid.uuid4(),
            ocr_job_id=result.ocr_job_id,
            ocr_result_id=result_id,
            project_id=result.project_id,
            audit_year=result.audit_year,
            field_key=field_name,
            is_required=is_required,
            original_value=original_value,
            confirmed_value=confirmed_value,
            decision=decision,
            is_current=True,
            revision_no=next_revision,
            confirmed_by_user_id=actor.actor_user_id,
            confirmed_at=datetime.now(timezone.utc),
        )
        self._db.add(confirmation)
        await self._db.flush()
        return confirmation

    # ------------------------------------------------------------------
    # check_all_required_decided — all required fields have a decision
    # ------------------------------------------------------------------

    async def check_all_required_decided(
        self, result_id: uuid.UUID
    ) -> tuple[bool, list[str]]:
        """Check if all required fields have a decision.

        Returns:
            (all_decided, undecided_fields):
            - all_decided=True if every required field has a current decision
            - undecided_fields lists field_keys of required fields without a decision

        A field is "decided" when it has a current confirmation (accepted, corrected,
        or rejected). Even rejected fields count as decided (design §5.2).
        """
        # Get the OCRResult's fields to determine which are required
        result = await self._get_result(result_id)

        # Get all required field names from the result's fields JSONB
        required_fields = self._extract_required_field_names(result)

        if not required_fields:
            # No required fields means all decided (vacuously true)
            return True, []

        # Get current confirmations for this result
        decided_stmt = (
            sa.select(OcrConfirmation.field_key)
            .where(
                OcrConfirmation.ocr_result_id == result_id,
                OcrConfirmation.is_current.is_(True),
                OcrConfirmation.is_required.is_(True),
            )
        )
        decided_result = await self._db.execute(decided_stmt)
        decided_fields = {row[0] for row in decided_result.all()}

        undecided = [f for f in required_fields if f not in decided_fields]
        return len(undecided) == 0, undecided

    # ------------------------------------------------------------------
    # build_mapping — mapping from ONLY accepted/corrected (P12)
    # ------------------------------------------------------------------

    async def build_mapping(self, result_id: uuid.UUID) -> dict[str, Any] | None:
        """Build field mapping from ONLY accepted/corrected confirmations.

        Rules (P12):
        - rejected fields: excluded entirely from mapping
        - undecided required fields: return None (mapping invalid, cannot proceed)
        - Returns dict[field_name → confirmed_value] for writeback

        Returns:
            dict mapping field_name→confirmed_value if valid, None if any
            required field is undecided (P12: target changes = 0).
        """
        # First check all required fields are decided
        all_decided, undecided = await self.check_all_required_decided(result_id)
        if not all_decided:
            return None  # Mapping invalid: required field(s) undecided

        # Get ALL current confirmations for this result
        stmt = (
            sa.select(OcrConfirmation)
            .where(
                OcrConfirmation.ocr_result_id == result_id,
                OcrConfirmation.is_current.is_(True),
            )
        )
        result = await self._db.execute(stmt)
        confirmations = result.scalars().all()

        # Build mapping: only accepted/corrected enter mapping; rejected excluded
        mapping: dict[str, Any] = {}
        for conf in confirmations:
            if conf.decision in OCR_WRITEBACK_ELIGIBLE_DECISIONS:
                mapping[conf.field_key] = conf.confirmed_value
            # rejected: excluded entirely (P12 — "rejected 永不进入 mapping")
            # undecided: already handled above (returned None)

        return mapping

    # ------------------------------------------------------------------
    # can_advance_to_confirmed — Job can advance to "confirmed"
    # ------------------------------------------------------------------

    async def can_advance_to_confirmed(self, job_id: uuid.UUID) -> bool:
        """Check if job can advance to 'confirmed' (all required fields decided).

        A job can enter "confirmed" when ALL required fields have a current
        decision (accepted/corrected/rejected). Even if some fields are rejected,
        job is "confirmed" (all decided) — design §5.2.
        """
        # Find the OCR result for this job
        result_stmt = (
            sa.select(OcrResult.id)
            .where(OcrResult.ocr_job_id == job_id)
            .order_by(OcrResult.created_at.desc())
            .limit(1)
        )
        result_row = await self._db.execute(result_stmt)
        result_id = result_row.scalar_one_or_none()

        if result_id is None:
            return False  # No result yet, cannot confirm

        all_decided, _ = await self.check_all_required_decided(result_id)
        return all_decided

    # ------------------------------------------------------------------
    # advance_to_confirmed — transition Job state
    # ------------------------------------------------------------------

    async def advance_to_confirmed(
        self,
        *,
        job_id: uuid.UUID,
        actor: ActorContext,
    ) -> bool:
        """Attempt to advance Job to 'confirmed' if all required decided.

        Returns True if successfully advanced, False if preconditions not met.
        Only works if job is in awaiting_confirmation state.
        """
        # Validate actor is human (confirmation is human-only action)
        actor.assert_human_action("human_confirm")

        # Check job state
        stmt = sa.select(OcrJob).where(OcrJob.id == job_id).with_for_update()
        result = await self._db.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "OCR job not found",
            )

        if job.state != OcrState.awaiting_confirmation.value:
            return False  # Not in correct state to advance

        # Check all required fields are decided
        can_advance = await self.can_advance_to_confirmed(job_id)
        if not can_advance:
            return False

        # Advance state
        job.state = OcrState.confirmed.value
        job.updated_at = datetime.now(timezone.utc)
        await self._db.flush()
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_result(self, result_id: uuid.UUID) -> OcrResult:
        """Load OCRResult by ID."""
        stmt = sa.select(OcrResult).where(OcrResult.id == result_id)
        result = await self._db.execute(stmt)
        ocr_result = result.scalar_one_or_none()
        if ocr_result is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "OCR result not found",
            )
        return ocr_result

    @staticmethod
    def _extract_required_field_names(result: OcrResult) -> list[str]:
        """Extract required field names from the OCRResult's fields JSONB.

        The `fields` column stores recognized fields as a dict/list.
        Convention: if fields is a dict, all top-level keys are required fields.
        If fields is a list of dicts with 'name' and optional 'required' key,
        only those with required=True (or no required key, defaulting to True) are required.
        """
        fields = result.fields
        if fields is None:
            return []

        if isinstance(fields, dict):
            # All top-level keys are required field names
            return list(fields.keys())

        if isinstance(fields, list):
            # List of field descriptors: [{name: str, required?: bool, ...}, ...]
            required = []
            for item in fields:
                if isinstance(item, dict) and "name" in item:
                    # Default to required=True if not specified
                    if item.get("required", True):
                        required.append(item["name"])
            return required

        return []


__all__ = [
    "OCRConfirmationService",
]
