"""调整分录“客户已入账”标记、撤销、历史与精确建议。"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import check_consol_lock, require_project_access, require_project_permission
from app.models.core import User
from app.services import adjustment_client_booking as booking
from app.services.event_bus import event_bus
from app.services.workpaper_sync.outbox import DurableEventOutboxService

router = APIRouter(prefix="/api/projects/{project_id}/adjustments", tags=["adjustments"])


class MarkClientBookingRequest(BaseModel):
    year: int
    voucher_keys: list[str] = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=1000)


class RevokeClientBookingRequest(BaseModel):
    year: int
    reason: str = Field(min_length=1, max_length=1000)


def _http(exc: booking.AdjustmentClientBookingError) -> HTTPException:
    conflict = {
        "ACTIVE_DATASET_REQUIRED", "VOUCHERS_NOT_IN_ACTIVE_DATASET", "BOOKING_NOT_ACTIVE",
    }
    return HTTPException(
        status_code=409 if exc.code in conflict else 400,
        detail={"error_code": exc.code, "message": str(exc), "detail": exc.detail},
    )


async def _publish_and_notify(db: AsyncSession, project_id: UUID, year: int, group_id: UUID, action: str) -> None:
    await DurableEventOutboxService.publish_pending(db)
    event_bus.broadcast_raw("adjustment:client-booking-changed", extra={
        "project_id": str(project_id), "year": year,
        "entry_group_id": str(group_id), "action": action,
    })


@router.post("/{entry_group_id}/client-booking")
async def mark_adjustment_client_booked(
    project_id: UUID,
    entry_group_id: UUID,
    body: MarkClientBookingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_permission("adjustment:edit")),
    _lock_check=Depends(check_consol_lock),
):
    try:
        row = await booking.mark_booked(
            db, project_id=project_id, year=body.year, entry_group_id=entry_group_id,
            voucher_key_values=body.voucher_keys, actor_id=current_user.id, note=body.note,
        )
        from app.services.adjustment_treatment_service import record_client_booking
        await record_client_booking(
            db, project_id=project_id, year=body.year, entry_group_id=entry_group_id,
            actor_id=current_user.id, booking=row,
        )
        recalculation = await booking.apply_booking_change(
            db, project_id=project_id, year=body.year, entry_group_id=entry_group_id,
            actor_id=current_user.id, action="book",
        )
        await db.commit()
    except booking.AdjustmentClientBookingError as exc:
        await db.rollback()
        raise _http(exc) from exc
    await _publish_and_notify(db, project_id, body.year, entry_group_id, "book")
    projection = await booking.booking_projection(
        db, project_id=project_id, year=body.year, group_ids=[entry_group_id],
    )
    return {
        "message": "已标记客户已入账，该 AJE 不再计入当前账套的调整额",
        "record_id": str(row.id), "client_booking": projection[str(entry_group_id)].as_dict(),
        "recalculation": recalculation,
    }


@router.post("/{entry_group_id}/client-booking/revoke")
async def revoke_adjustment_client_booking(
    project_id: UUID,
    entry_group_id: UUID,
    body: RevokeClientBookingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_permission("adjustment:edit")),
    _lock_check=Depends(check_consol_lock),
):
    try:
        row = await booking.revoke_booking(
            db, project_id=project_id, year=body.year, entry_group_id=entry_group_id,
            actor_id=current_user.id, reason=body.reason,
        )
        from app.services.adjustment_treatment_service import record_withdrawal
        await record_withdrawal(
            db, project_id=project_id, year=body.year, entry_group_id=entry_group_id,
            actor_id=current_user.id, reason=body.reason,
        )
        recalculation = await booking.apply_booking_change(
            db, project_id=project_id, year=body.year, entry_group_id=entry_group_id,
            actor_id=current_user.id, action="revoke",
        )
        await db.commit()
    except booking.AdjustmentClientBookingError as exc:
        await db.rollback()
        raise _http(exc) from exc
    await _publish_and_notify(db, project_id, body.year, entry_group_id, "revoke")
    return {
        "message": "已撤销客户已入账标记，该 AJE 已恢复计入当前账套调整额",
        "record_id": str(row.id), "recalculation": recalculation,
    }


@router.get("/{entry_group_id}/client-booking/history")
async def get_adjustment_client_booking_history(
    project_id: UUID,
    entry_group_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await booking.booking_history(
        db, project_id=project_id, year=year, entry_group_id=entry_group_id,
    )


@router.get("/client-booking/suggestions")
async def get_adjustment_client_booking_suggestions(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return await booking.suggest_bookings(db, project_id=project_id, year=year)
