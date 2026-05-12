"""EQCR 工时追踪端点"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.eqcr_service import EqcrService

from .schemas import EqcrTimeTrackStartRequest, EqcrTimeTrackStopRequest

router = APIRouter()


@router.post("/projects/{project_id}/time-track/start")
async def eqcr_time_track_start(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 开始复核计时（需求 8）。"""
    from app.models.staff_models import WorkHour, StaffMember

    svc = EqcrService(db)
    is_eqcr = await svc._is_user_eqcr_on(current_user.id, project_id)
    if not is_eqcr:
        raise HTTPException(status_code=403, detail="非本项目 EQCR")

    staff_q = select(StaffMember.id).where(
        StaffMember.user_id == current_user.id,
        StaffMember.is_deleted == False,  # noqa: E712
    )
    staff_id = (await db.execute(staff_q)).scalar_one_or_none()
    if staff_id is None:
        raise HTTPException(status_code=404, detail="未找到员工记录")

    existing_q = select(WorkHour).where(
        WorkHour.staff_id == staff_id,
        WorkHour.project_id == project_id,
        WorkHour.purpose == "eqcr",
        WorkHour.status == "tracking",
        WorkHour.is_deleted == False,  # noqa: E712
    )
    existing = (await db.execute(existing_q)).scalar_one_or_none()
    if existing:
        return {
            "status": "already_tracking",
            "tracking_id": str(existing.id),
            "started_at": existing.start_time.isoformat() if existing.start_time else existing.created_at.isoformat(),
        }

    now = datetime.now(timezone.utc)
    wh = WorkHour(
        staff_id=staff_id,
        project_id=project_id,
        work_date=now.date(),
        hours=0,
        start_time=now.time(),
        end_time=None,
        description="EQCR 独立复核",
        status="tracking",
        purpose="eqcr",
    )
    db.add(wh)
    await db.commit()
    await db.refresh(wh)

    return {
        "status": "started",
        "tracking_id": str(wh.id),
        "started_at": now.isoformat(),
    }


@router.post("/projects/{project_id}/time-track/stop")
async def eqcr_time_track_stop(
    project_id: UUID,
    payload: EqcrTimeTrackStopRequest = EqcrTimeTrackStopRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 结束复核计时，生成正式工时记录（需求 8）。"""
    from app.models.staff_models import WorkHour, StaffMember

    svc = EqcrService(db)
    is_eqcr = await svc._is_user_eqcr_on(current_user.id, project_id)
    if not is_eqcr:
        raise HTTPException(status_code=403, detail="非本项目 EQCR")

    staff_q = select(StaffMember.id).where(
        StaffMember.user_id == current_user.id,
        StaffMember.is_deleted == False,  # noqa: E712
    )
    staff_id = (await db.execute(staff_q)).scalar_one_or_none()
    if staff_id is None:
        raise HTTPException(status_code=404, detail="未找到员工记录")

    tracking_q = select(WorkHour).where(
        WorkHour.staff_id == staff_id,
        WorkHour.project_id == project_id,
        WorkHour.purpose == "eqcr",
        WorkHour.status == "tracking",
        WorkHour.is_deleted == False,  # noqa: E712
    )
    tracking = (await db.execute(tracking_q)).scalar_one_or_none()
    if tracking is None:
        raise HTTPException(status_code=404, detail="无进行中的 EQCR 计时")

    now = datetime.now(timezone.utc)
    start_dt = datetime.combine(tracking.work_date, tracking.start_time, tzinfo=timezone.utc)
    elapsed = (now - start_dt).total_seconds() / 3600.0
    hours = Decimal(str(round(elapsed, 2)))
    if hours <= 0:
        hours = Decimal("0.01")

    tracking.end_time = now.time()
    tracking.hours = hours
    tracking.status = "draft"
    if payload.description:
        tracking.description = payload.description

    await db.commit()
    await db.refresh(tracking)

    return {
        "status": "stopped",
        "tracking_id": str(tracking.id),
        "hours": float(tracking.hours),
        "work_date": str(tracking.work_date),
        "description": tracking.description,
    }


@router.get("/projects/{project_id}/time-summary")
async def eqcr_time_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取 EQCR 在该项目的工时汇总（需求 8）。"""
    from app.models.staff_models import WorkHour, StaffMember

    staff_q = select(StaffMember.id).where(
        StaffMember.user_id == current_user.id,
        StaffMember.is_deleted == False,  # noqa: E712
    )
    staff_id = (await db.execute(staff_q)).scalar_one_or_none()
    if staff_id is None:
        return {"total_hours": 0, "records": []}

    q = (
        select(WorkHour)
        .where(
            WorkHour.staff_id == staff_id,
            WorkHour.project_id == project_id,
            WorkHour.purpose == "eqcr",
            WorkHour.status != "tracking",
            WorkHour.is_deleted == False,  # noqa: E712
        )
        .order_by(WorkHour.work_date.desc())
    )
    records = list((await db.execute(q)).scalars().all())

    total_hours = sum(float(r.hours) for r in records)

    return {
        "total_hours": round(total_hours, 2),
        "record_count": len(records),
        "records": [
            {
                "id": str(r.id),
                "work_date": str(r.work_date),
                "hours": float(r.hours),
                "start_time": str(r.start_time) if r.start_time else None,
                "end_time": str(r.end_time) if r.end_time else None,
                "description": r.description,
                "status": r.status,
            }
            for r in records
        ],
    }
