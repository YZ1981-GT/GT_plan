"""调整分录最终财务处理的单一投影与追加式历史。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adjustment_review_models import (
    AdjustmentClientBooking,
    AdjustmentTreatmentEvent,
)
from app.models.audit_platform_models import (
    Adjustment,
    ReviewStatus,
    UnadjustedMisstatement,
)
from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.workpaper_sync.outbox import DurableEventOutboxService


class AdjustmentTreatmentError(ValueError):
    def __init__(self, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class TreatmentProjection:
    status: str
    effective: bool
    latest_action: str | None
    sequence: int | None
    misstatement_id: UUID | None = None
    client_booking_id: UUID | None = None
    reason: str | None = None
    created_by: UUID | None = None
    created_at: Any = None
    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "effective": self.effective,
            "latest_action": self.latest_action,
            "sequence": self.sequence,
            "misstatement_id": str(self.misstatement_id) if self.misstatement_id else None,
            "client_booking_id": str(self.client_booking_id) if self.client_booking_id else None,
            "reason": self.reason,
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


async def _latest_events(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    group_ids: Iterable[UUID] | None = None,
) -> dict[UUID, AdjustmentTreatmentEvent]:
    stmt = sa.select(AdjustmentTreatmentEvent).where(
        AdjustmentTreatmentEvent.project_id == project_id,
        AdjustmentTreatmentEvent.year == year,
    )
    ids = list(group_ids or [])
    if ids:
        stmt = stmt.where(AdjustmentTreatmentEvent.entry_group_id.in_(ids))
    stmt = stmt.order_by(
        AdjustmentTreatmentEvent.entry_group_id,
        AdjustmentTreatmentEvent.sequence.desc(),
        AdjustmentTreatmentEvent.id.desc(),
    )
    latest: dict[UUID, AdjustmentTreatmentEvent] = {}
    for row in (await db.execute(stmt)).scalars().all():
        latest.setdefault(row.entry_group_id, row)
    return latest


async def _lock_group(
    db: AsyncSession, project_id: UUID, year: int, entry_group_id: UUID,
) -> list[Adjustment]:
    stmt = sa.select(Adjustment).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.entry_group_id == entry_group_id,
        Adjustment.is_deleted == sa.false(),
    )
    if db.get_bind() is not None and db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    rows = list((await db.execute(stmt)).scalars().all())
    if not rows:
        raise AdjustmentTreatmentError("GROUP_NOT_FOUND", "调整分录不存在或已删除")
    if {row.review_status for row in rows} != {ReviewStatus.approved}:
        raise AdjustmentTreatmentError("APPROVED_REQUIRED", "只有已批准的调整分录可以选择最终处理")
    return rows


async def append_treatment_event(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    entry_group_id: UUID,
    action: str,
    actor_id: UUID,
    dataset_id: UUID | None = None,
    voucher_keys: list[str] | None = None,
    misstatement_id: UUID | None = None,
    client_booking_id: UUID | None = None,
    reverses_event_id: UUID | None = None,
    reason: str | None = None,
) -> AdjustmentTreatmentEvent:
    """锁定分录组并追加一个有单调序号的处理事件。"""
    await _lock_group(db, project_id, year, entry_group_id)
    current = (await db.execute(sa.select(sa.func.max(AdjustmentTreatmentEvent.sequence)).where(
        AdjustmentTreatmentEvent.project_id == project_id,
        AdjustmentTreatmentEvent.entry_group_id == entry_group_id,
    ))).scalar_one_or_none()
    row = AdjustmentTreatmentEvent(
        project_id=project_id,
        year=year,
        entry_group_id=entry_group_id,
        sequence=int(current or 0) + 1,
        action=action,
        dataset_id=dataset_id,
        voucher_keys=list(voucher_keys or []),
        misstatement_id=misstatement_id,
        client_booking_id=client_booking_id,
        reverses_event_id=reverses_event_id,
        reason=(reason or "").strip() or None,
        created_by=actor_id,
    )
    db.add(row)
    await db.flush()
    return row


async def treatment_projection(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    group_ids: Iterable[UUID],
) -> dict[str, TreatmentProjection]:
    requested_ids = list(dict.fromkeys(group_ids))
    group_rows = (await db.execute(sa.select(
        Adjustment.entry_group_id,
        Adjustment.review_status,
        Adjustment.origin,
    ).where(
        Adjustment.project_id == project_id,
        Adjustment.year == year,
        Adjustment.entry_group_id.in_(requested_ids),
        Adjustment.is_deleted == sa.false(),
    ))).all()
    group_info: dict[UUID, tuple[Any, str]] = {}
    for group_id, review_status, origin in group_rows:
        group_info.setdefault(group_id, (review_status, origin or "manual"))
    ids = list(group_info)
    latest = await _latest_events(db, project_id, year, ids)
    from app.services.adjustment_client_booking import booking_projection

    booking = await booking_projection(
        db, project_id=project_id, year=year, group_ids=ids,
    )
    misstatement_ids = {
        row.misstatement_id for row in latest.values()
        if row.action == "unadjusted_misstatement" and row.misstatement_id is not None
    }
    active_misstatements: set[UUID] = set()
    if misstatement_ids:
        active_misstatements = set((await db.execute(sa.select(UnadjustedMisstatement.id).where(
            UnadjustedMisstatement.id.in_(misstatement_ids),
            UnadjustedMisstatement.project_id == project_id,
            UnadjustedMisstatement.year == year,
            UnadjustedMisstatement.is_deleted == sa.false(),
            UnadjustedMisstatement.prior_year_status != "reversed",
        ))).scalars().all())

    out: dict[str, TreatmentProjection] = {}
    for group_id in ids:
        event = latest.get(group_id)
        booked = booking.get(str(group_id))
        review_status, origin = group_info[group_id]
        raw_review_status = str(getattr(review_status, "value", review_status))
        if raw_review_status != ReviewStatus.approved.value:
            out[str(group_id)] = TreatmentProjection(
                "pending_internal_review", False, event.action if event else None,
                event.sequence if event else None,
            )
            continue
        if origin == "workpaper":
            out[str(group_id)] = TreatmentProjection(
                "awaiting_workpaper_publish", True, event.action if event else None,
                event.sequence if event else None,
            )
            continue
        if event is None:
            status = "client_booked" if booked and booked.status == "booked" else "include_in_working_tb"
            effective = bool(booked.effective) if status == "client_booked" and booked else True
            out[str(group_id)] = TreatmentProjection(status, effective, None, None)
            continue
        if event.action == "client_booked":
            status, effective = "client_booked", bool(booked and booked.effective)
        elif event.action == "unadjusted_misstatement":
            status = "unadjusted_misstatement"
            effective = event.misstatement_id in active_misstatements
        else:
            status, effective = "include_in_working_tb", True
        out[str(group_id)] = TreatmentProjection(
            status=status, effective=effective, latest_action=event.action,
            sequence=event.sequence, misstatement_id=event.misstatement_id,
            client_booking_id=event.client_booking_id, reason=event.reason,
            created_by=event.created_by, created_at=event.created_at,
        )
    return out


async def effective_excluded_group_ids(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    group_ids: Iterable[UUID] | None = None,
) -> set[UUID]:
    """返回不应计入工作试算表 AJE/RJE 的当前处理组。"""
    ids = list(group_ids or [])
    latest = await _latest_events(db, project_id, year, ids or None)
    from app.services.adjustment_client_booking import effective_booked_group_ids

    booked = await effective_booked_group_ids(
        db, project_id=project_id, year=year, group_ids=ids or None,
    )
    excluded = {
        gid for gid in booked
        if gid not in latest or latest[gid].action == "client_booked"
    }
    misstatement_events = {
        gid: row.misstatement_id for gid, row in latest.items()
        if row.action == "unadjusted_misstatement" and row.misstatement_id is not None
    }
    if misstatement_events:
        active = set((await db.execute(sa.select(UnadjustedMisstatement.id).where(
            UnadjustedMisstatement.id.in_(misstatement_events.values()),
            UnadjustedMisstatement.project_id == project_id,
            UnadjustedMisstatement.year == year,
            UnadjustedMisstatement.is_deleted == sa.false(),
            UnadjustedMisstatement.prior_year_status != "reversed",
        ))).scalars().all())
        excluded.update(gid for gid, mid in misstatement_events.items() if mid in active)
    return excluded


async def effective_groups_clause(
    db: AsyncSession,
    adjustment_table: Any,
    *,
    project_id: UUID,
    year: int,
) -> sa.ColumnElement:
    c = adjustment_table.c if hasattr(adjustment_table, "c") else adjustment_table.__table__.c
    ids = await effective_excluded_group_ids(db, project_id=project_id, year=year)
    return c.entry_group_id.notin_(sorted(ids, key=str)) if ids else sa.true()


async def treatment_history(
    db: AsyncSession, *, project_id: UUID, year: int, entry_group_id: UUID,
) -> list[dict[str, Any]]:
    rows = list((await db.execute(sa.select(AdjustmentTreatmentEvent).where(
        AdjustmentTreatmentEvent.project_id == project_id,
        AdjustmentTreatmentEvent.year == year,
        AdjustmentTreatmentEvent.entry_group_id == entry_group_id,
    ).order_by(
        AdjustmentTreatmentEvent.sequence.desc(),
        AdjustmentTreatmentEvent.id.desc(),
    ))).scalars().all())
    return [{
        "id": str(row.id),
        "sequence": row.sequence,
        "action": row.action,
        "dataset_id": str(row.dataset_id) if row.dataset_id else None,
        "voucher_keys": list(row.voucher_keys or []),
        "misstatement_id": str(row.misstatement_id) if row.misstatement_id else None,
        "client_booking_id": str(row.client_booking_id) if row.client_booking_id else None,
        "reverses_event_id": str(row.reverses_event_id) if row.reverses_event_id else None,
        "reason": row.reason,
        "created_by": str(row.created_by),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    } for row in rows]


async def record_initial_inclusion(
    db: AsyncSession, *, project_id: UUID, year: int, entry_group_id: UUID, actor_id: UUID,
) -> AdjustmentTreatmentEvent | None:
    """批准手工分录时补初始“纳入工作试算表”；重复调用不新增历史。"""
    if await _latest_events(db, project_id, year, [entry_group_id]):
        return None
    return await append_treatment_event(
        db, project_id=project_id, year=year, entry_group_id=entry_group_id,
        action="include_in_working_tb", actor_id=actor_id,
        reason="内部复核批准后纳入工作试算表",
    )


async def record_client_booking(
    db: AsyncSession, *, project_id: UUID, year: int, entry_group_id: UUID,
    actor_id: UUID, booking: AdjustmentClientBooking,
) -> AdjustmentTreatmentEvent:
    latest = (await _latest_events(db, project_id, year, [entry_group_id])).get(entry_group_id)
    if latest and latest.action == "unadjusted_misstatement" and latest.misstatement_id:
        misstatement = (await db.execute(sa.select(UnadjustedMisstatement).where(
            UnadjustedMisstatement.id == latest.misstatement_id,
            UnadjustedMisstatement.project_id == project_id,
            UnadjustedMisstatement.year == year,
            UnadjustedMisstatement.is_deleted == sa.false(),
        ))).scalar_one_or_none()
        if misstatement is not None:
            misstatement.is_deleted = True
            misstatement.deleted_at = datetime.now(timezone.utc)
            await db.flush()
    return await append_treatment_event(
        db, project_id=project_id, year=year, entry_group_id=entry_group_id,
        action="client_booked", actor_id=actor_id,
        dataset_id=booking.booked_dataset_id, voucher_keys=list(booking.voucher_keys or []),
        client_booking_id=booking.id, reason=booking.note,
    )


async def record_withdrawal(
    db: AsyncSession, *, project_id: UUID, year: int, entry_group_id: UUID,
    actor_id: UUID, reason: str,
) -> AdjustmentTreatmentEvent:
    latest = (await _latest_events(db, project_id, year, [entry_group_id])).get(entry_group_id)
    return await append_treatment_event(
        db, project_id=project_id, year=year, entry_group_id=entry_group_id,
        action="withdraw", actor_id=actor_id,
        reverses_event_id=latest.id if latest else None, reason=reason,
    )


async def _recalculate_and_enqueue(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    entry_group_id: UUID,
    actor_id: UUID,
    action: str,
) -> dict[str, Any]:
    rows = await _lock_group(db, project_id, year, entry_group_id)
    account_codes = sorted({row.account_code for row in rows if row.account_code})
    company_codes = {row.company_code for row in rows if row.company_code}
    if len(company_codes) != 1:
        raise AdjustmentTreatmentError("COMPANY_AMBIGUOUS", "分录组所属主体不一致，无法重算试算表")
    from app.services.adjustment_review_coordinator import AdjustmentReviewCoordinator
    from app.services.trial_balance_service import TrialBalanceService

    company_code = next(iter(company_codes))
    await AdjustmentReviewCoordinator(db).ensure_tb_rows(
        project_id=project_id, year=year, company_code=company_code,
        account_codes=account_codes,
    )
    tb = TrialBalanceService(db)
    await tb.recalc_adjustments(
        project_id, year, company_code=company_code, account_codes=account_codes,
    )
    await tb.recalc_audited(
        project_id, year, company_code=company_code, account_codes=account_codes,
    )
    extra = {
        "trigger": "adjustment_treatment_changed",
        "action": action,
        "operator_id": str(actor_id),
        "tb_recalc_committed": True,
    }
    await DurableEventOutboxService.enqueue_event(db, EventPayload(
        event_type=EventType.ADJUSTMENT_TREATMENT_CHANGED,
        project_id=project_id,
        year=year,
        account_codes=account_codes,
        entry_group_id=entry_group_id,
        extra=extra,
    ))
    await DurableEventOutboxService.enqueue_event(db, EventPayload(
        event_type=EventType.TRIAL_BALANCE_UPDATED,
        project_id=project_id,
        year=year,
        account_codes=account_codes,
        entry_group_id=entry_group_id,
        extra=extra,
    ))
    return {"account_codes": account_codes, "company_code": company_code}


async def convert_to_unadjusted_misstatement(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    entry_group_id: UUID,
    actor_id: UUID,
    management_reason: str,
    management_communication_at: datetime,
    auditor_evaluation: str | None = None,
) -> dict[str, Any]:
    reason = (management_reason or "").strip()
    if not reason:
        raise AdjustmentTreatmentError("MANAGEMENT_REASON_REQUIRED", "请选择不予更正时必须填写管理层原因")
    if management_communication_at.tzinfo is None:
        management_communication_at = management_communication_at.replace(tzinfo=timezone.utc)
    rows = await _lock_group(db, project_id, year, entry_group_id)
    if {str(getattr(row.adjustment_type, "value", row.adjustment_type)) for row in rows} != {"aje"}:
        raise AdjustmentTreatmentError("AJE_REQUIRED", "只有审计调整 AJE 可以转为未更正错报")
    previous = (await _latest_events(db, project_id, year, [entry_group_id])).get(entry_group_id)
    if previous and previous.action == "client_booked":
        from app.services.adjustment_client_booking import revoke_booking
        await revoke_booking(
            db, project_id=project_id, year=year, entry_group_id=entry_group_id,
            actor_id=actor_id, reason="改为不予更正并转错报",
        )

    first_ids = [row.id for row in rows]
    existing = (await db.execute(sa.select(UnadjustedMisstatement).where(
        UnadjustedMisstatement.project_id == project_id,
        UnadjustedMisstatement.source_adjustment_id.in_(first_ids),
        UnadjustedMisstatement.is_deleted == sa.false(),
    ).limit(1))).scalar_one_or_none()
    if existing is None:
        from app.services.misstatement_service import UnadjustedMisstatementService
        response = await UnadjustedMisstatementService(db).create_from_adjustment_group(
            project_id, entry_group_id, year, actor_id,
            management_reason=reason,
            management_communication_at=management_communication_at,
            auditor_evaluation=auditor_evaluation,
            required_review_status=ReviewStatus.approved,
        )
        misstatement_id = response.id
    else:
        existing.management_reason = reason
        existing.management_communication_at = management_communication_at
        if auditor_evaluation is not None:
            existing.auditor_evaluation = auditor_evaluation.strip() or None
        misstatement_id = existing.id
        await db.flush()
    latest = (await _latest_events(db, project_id, year, [entry_group_id])).get(entry_group_id)
    if not (latest and latest.action == "unadjusted_misstatement" and latest.misstatement_id == misstatement_id):
        event = await append_treatment_event(
            db, project_id=project_id, year=year, entry_group_id=entry_group_id,
            action="unadjusted_misstatement", actor_id=actor_id,
            misstatement_id=misstatement_id, reason=reason,
        )
    else:
        event = latest
    recalculation = await _recalculate_and_enqueue(
        db, project_id=project_id, year=year, entry_group_id=entry_group_id,
        actor_id=actor_id, action="unadjusted_misstatement",
    )
    return {
        "misstatement_id": str(misstatement_id),
        "treatment_event_id": str(event.id),
        "recalculation": recalculation,
    }


async def withdraw_current_treatment(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    entry_group_id: UUID,
    actor_id: UUID,
    reason: str,
) -> dict[str, Any]:
    reason = (reason or "").strip()
    if not reason:
        raise AdjustmentTreatmentError("WITHDRAW_REASON_REQUIRED", "撤销最终处理必须填写原因")
    await _lock_group(db, project_id, year, entry_group_id)
    latest = (await _latest_events(db, project_id, year, [entry_group_id])).get(entry_group_id)
    if latest is None or latest.action in {"include_in_working_tb", "withdraw"}:
        raise AdjustmentTreatmentError("TREATMENT_NOT_WITHDRAWABLE", "当前没有可撤销的客户已入账或不予更正处理")

    if latest.action == "client_booked":
        from app.services.adjustment_client_booking import revoke_booking
        await revoke_booking(
            db, project_id=project_id, year=year, entry_group_id=entry_group_id,
            actor_id=actor_id, reason=reason,
        )
    elif latest.action == "unadjusted_misstatement" and latest.misstatement_id:
        row = (await db.execute(sa.select(UnadjustedMisstatement).where(
            UnadjustedMisstatement.id == latest.misstatement_id,
            UnadjustedMisstatement.project_id == project_id,
            UnadjustedMisstatement.year == year,
            UnadjustedMisstatement.is_deleted == sa.false(),
        ))).scalar_one_or_none()
        if row is None:
            raise AdjustmentTreatmentError("MISSTATEMENT_NOT_FOUND", "关联的未更正错报不存在或已撤销")
        row.is_deleted = True
        row.deleted_at = datetime.now(timezone.utc)
        await db.flush()
    event = await append_treatment_event(
        db, project_id=project_id, year=year, entry_group_id=entry_group_id,
        action="withdraw", actor_id=actor_id,
        reverses_event_id=latest.id, reason=reason,
    )
    recalculation = await _recalculate_and_enqueue(
        db, project_id=project_id, year=year, entry_group_id=entry_group_id,
        actor_id=actor_id, action="withdraw",
    )
    return {
        "treatment_event_id": str(event.id),
        "restored_status": "include_in_working_tb",
        "recalculation": recalculation,
    }


async def include_in_working_tb(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    entry_group_id: UUID,
    actor_id: UUID,
    reason: str | None = None,
) -> dict[str, Any]:
    """显式选择纳入工作试算表；若当前是其他处理，先按审计轨迹撤销。"""
    latest = (await _latest_events(db, project_id, year, [entry_group_id])).get(entry_group_id)
    if latest and latest.action in {"client_booked", "unadjusted_misstatement"}:
        return await withdraw_current_treatment(
            db, project_id=project_id, year=year, entry_group_id=entry_group_id,
            actor_id=actor_id, reason=(reason or "改为纳入工作试算表"),
        )
    if latest and latest.action == "include_in_working_tb":
        return {"treatment_event_id": str(latest.id), "restored_status": "include_in_working_tb", "duplicate": True}
    event = await append_treatment_event(
        db, project_id=project_id, year=year, entry_group_id=entry_group_id,
        action="include_in_working_tb", actor_id=actor_id, reason=reason,
    )
    recalculation = await _recalculate_and_enqueue(
        db, project_id=project_id, year=year, entry_group_id=entry_group_id,
        actor_id=actor_id, action="include_in_working_tb",
    )
    return {
        "treatment_event_id": str(event.id),
        "restored_status": "include_in_working_tb",
        "recalculation": recalculation,
    }
