"""调整分录最终处理：纳入工作试算表、不予更正、撤销及历史。"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import check_consol_lock, require_project_access, require_project_permission
from app.models.core import User
from app.services import adjustment_treatment_service as treatment
from app.services.event_bus import event_bus
from app.services.workpaper_sync.outbox import DurableEventOutboxService

router = APIRouter(prefix="/api/projects/{project_id}/adjustments", tags=["adjustments"])


class UnadjustedTreatmentRequest(BaseModel):
    year: int
    management_reason: str = Field(min_length=1, max_length=4000)
    management_communication_at: datetime
    auditor_evaluation: str | None = Field(default=None, max_length=4000)


class TreatmentChangeRequest(BaseModel):
    year: int
    reason: str | None = Field(default=None, max_length=1000)


def _http(exc: treatment.AdjustmentTreatmentError) -> HTTPException:
    conflict_codes = {
        "APPROVED_REQUIRED", "TREATMENT_NOT_WITHDRAWABLE", "MISSTATEMENT_NOT_FOUND",
    }
    return HTTPException(
        status_code=409 if exc.code in conflict_codes else 400,
        detail={"error_code": exc.code, "message": str(exc), "detail": exc.detail},
    )


async def _finish(db: AsyncSession, project_id: UUID, year: int, group_id: UUID, action: str) -> None:
    await DurableEventOutboxService.publish_pending(db)
    event_bus.broadcast_raw("adjustment:treatment-changed", extra={
        "project_id": str(project_id), "year": year,
        "entry_group_id": str(group_id), "action": action,
    })


@router.get("/{entry_group_id}/treatment")
async def get_adjustment_treatment(
    project_id: UUID,
    entry_group_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    projection = await treatment.treatment_projection(
        db, project_id=project_id, year=year, group_ids=[entry_group_id],
    )
    if str(entry_group_id) not in projection:
        raise HTTPException(status_code=404, detail="调整分录不存在")
    return projection[str(entry_group_id)].as_dict()


@router.get("/{entry_group_id}/treatment/history")
async def get_adjustment_treatment_history(
    project_id: UUID,
    entry_group_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await treatment.treatment_history(
        db, project_id=project_id, year=year, entry_group_id=entry_group_id,
    )


@router.post("/{entry_group_id}/treatment/unadjusted")
async def mark_adjustment_unadjusted(
    project_id: UUID,
    entry_group_id: UUID,
    body: UnadjustedTreatmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_permission("adjustment:convert_to_misstatement")),
    _lock_check=Depends(check_consol_lock),
):
    try:
        result = await treatment.convert_to_unadjusted_misstatement(
            db,
            project_id=project_id,
            year=body.year,
            entry_group_id=entry_group_id,
            actor_id=current_user.id,
            management_reason=body.management_reason,
            management_communication_at=body.management_communication_at,
            auditor_evaluation=body.auditor_evaluation,
        )
        await db.commit()
    except treatment.AdjustmentTreatmentError as exc:
        await db.rollback()
        raise _http(exc) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail={
            "error_code": "MISSTATEMENT_CONVERSION_FAILED", "message": str(exc),
        }) from exc
    await _finish(db, project_id, body.year, entry_group_id, "unadjusted_misstatement")
    return {"message": "已转为未更正错报，该 AJE 不再计入工作试算表", **result}


@router.post("/{entry_group_id}/treatment/include")
async def include_adjustment_in_working_tb(
    project_id: UUID,
    entry_group_id: UUID,
    body: TreatmentChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_permission("adjustment:approve")),
    _lock_check=Depends(check_consol_lock),
):
    try:
        result = await treatment.include_in_working_tb(
            db, project_id=project_id, year=body.year, entry_group_id=entry_group_id,
            actor_id=current_user.id, reason=body.reason,
        )
        await db.commit()
    except treatment.AdjustmentTreatmentError as exc:
        await db.rollback()
        raise _http(exc) from exc
    await _finish(db, project_id, body.year, entry_group_id, "include_in_working_tb")
    return {"message": "该调整已纳入工作试算表", **result}


@router.post("/{entry_group_id}/treatment/withdraw")
async def withdraw_adjustment_treatment(
    project_id: UUID,
    entry_group_id: UUID,
    body: TreatmentChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_permission("adjustment:approve")),
    _lock_check=Depends(check_consol_lock),
):
    if not (body.reason or "").strip():
        raise HTTPException(status_code=422, detail="撤销最终处理必须填写原因")
    try:
        result = await treatment.withdraw_current_treatment(
            db, project_id=project_id, year=body.year, entry_group_id=entry_group_id,
            actor_id=current_user.id, reason=body.reason or "",
        )
        await db.commit()
    except treatment.AdjustmentTreatmentError as exc:
        await db.rollback()
        raise _http(exc) from exc
    await _finish(db, project_id, body.year, entry_group_id, "withdraw")
    return {"message": "已撤销最终处理，该 AJE 恢复计入工作试算表", **result}
