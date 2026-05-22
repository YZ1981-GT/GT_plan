"""工时填报 CRUD API — Phase 7 F7

POST/GET/PUT/DELETE /api/projects/{id}/workhours
+ batch-submit + summary

校验：日合计 ≤ 24h / 仅本人可操作（admin 除外）/ 自动推断 cycle
注册到 router_registry 协作域 §111。

Validates: Requirements F7.3, F7.4, F7.5, F7.6, F7.7
"""

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workhour_entry_models import WorkHourEntry, WorkHourEntryStatus

router = APIRouter(
    prefix="/api/projects/{project_id}/workhours",
    tags=["workhours-entries"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class WorkHourEntryCreate(BaseModel):
    date: date
    hours: Decimal = Field(gt=0, le=24)
    cycle: Optional[str] = None
    wp_code: Optional[str] = None
    procedure: Optional[str] = None
    description: Optional[str] = None


class WorkHourEntryUpdate(BaseModel):
    date: Optional[date] = None
    hours: Optional[Decimal] = Field(None, gt=0, le=24)
    cycle: Optional[str] = None
    wp_code: Optional[str] = None
    procedure: Optional[str] = None
    description: Optional[str] = None


class BatchSubmitRequest(BaseModel):
    entry_ids: list[UUID]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_cycle(wp_code: str | None, explicit_cycle: str | None) -> str:
    """Auto-infer cycle from wp_code prefix if cycle not explicitly provided."""
    if explicit_cycle:
        return explicit_cycle
    if wp_code:
        match = re.match(r"^([A-Z])", wp_code.upper())
        if match:
            return match.group(1)
    return "OTHER"


def _entry_to_dict(entry: WorkHourEntry) -> dict:
    return {
        "id": str(entry.id),
        "user_id": str(entry.user_id),
        "project_id": str(entry.project_id),
        "date": entry.date.isoformat(),
        "hours": float(entry.hours),
        "cycle": entry.cycle,
        "wp_code": entry.wp_code,
        "procedure": entry.procedure,
        "description": entry.description,
        "status": entry.status,
        "submitted_at": entry.submitted_at.isoformat() if entry.submitted_at else None,
        "approved_by": str(entry.approved_by) if entry.approved_by else None,
        "approved_at": entry.approved_at.isoformat() if entry.approved_at else None,
        "rejected_reason": entry.rejected_reason,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


async def _check_daily_limit(
    db: AsyncSession,
    user_id: UUID,
    target_date: date,
    exclude_entry_id: UUID | None = None,
    new_hours: Decimal = Decimal("0"),
) -> None:
    """Validate daily total ≤ 24h."""
    stmt = select(func.coalesce(func.sum(WorkHourEntry.hours), 0)).where(
        WorkHourEntry.user_id == user_id,
        WorkHourEntry.date == target_date,
    )
    if exclude_entry_id:
        stmt = stmt.where(WorkHourEntry.id != exclude_entry_id)
    result = await db.execute(stmt)
    existing_total = result.scalar() or Decimal("0")
    if existing_total + new_hours > Decimal("24"):
        raise HTTPException(
            status_code=422,
            detail=f"日合计工时超过 24 小时限制（当日已填 {float(existing_total)}h，本次 {float(new_hours)}h）",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("")
async def create_entry(
    project_id: UUID,
    body: WorkHourEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建工时条目（校验日合计 ≤ 24h）"""
    cycle = _infer_cycle(body.wp_code, body.cycle)
    await _check_daily_limit(db, current_user.id, body.date, new_hours=body.hours)

    entry = WorkHourEntry(
        user_id=current_user.id,
        project_id=project_id,
        date=body.date,
        hours=body.hours,
        cycle=cycle,
        wp_code=body.wp_code,
        procedure=body.procedure,
        description=body.description,
        status=WorkHourEntryStatus.draft.value,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _entry_to_dict(entry)


@router.get("")
async def list_entries(
    project_id: UUID,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出工时条目（支持日期过滤）"""
    stmt = select(WorkHourEntry).where(WorkHourEntry.project_id == project_id)

    # Only own entries unless admin
    if current_user.role.value != "admin":
        stmt = stmt.where(WorkHourEntry.user_id == current_user.id)

    if start_date:
        stmt = stmt.where(WorkHourEntry.date >= start_date)
    if end_date:
        stmt = stmt.where(WorkHourEntry.date <= end_date)

    stmt = stmt.order_by(WorkHourEntry.date.desc(), WorkHourEntry.created_at.desc())
    result = await db.execute(stmt)
    entries = result.scalars().all()
    return [_entry_to_dict(e) for e in entries]


@router.put("/{entry_id}")
async def update_entry(
    project_id: UUID,
    entry_id: UUID,
    body: WorkHourEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新工时条目（仅 draft 状态可改）"""
    result = await db.execute(
        select(WorkHourEntry).where(
            WorkHourEntry.id == entry_id,
            WorkHourEntry.project_id == project_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "工时条目不存在")

    # Only own entries (admin exempt)
    if current_user.role.value != "admin" and entry.user_id != current_user.id:
        raise HTTPException(403, "只能修改自己的工时")

    if entry.status != WorkHourEntryStatus.draft.value:
        raise HTTPException(422, "仅 draft 状态可修改")

    # Validate daily limit if hours changed
    new_hours = body.hours if body.hours is not None else entry.hours
    new_date = body.date if body.date is not None else entry.date
    if body.hours is not None or body.date is not None:
        await _check_daily_limit(db, entry.user_id, new_date, exclude_entry_id=entry_id, new_hours=new_hours)

    # Apply updates
    if body.date is not None:
        entry.date = body.date
    if body.hours is not None:
        entry.hours = body.hours
    if body.cycle is not None:
        entry.cycle = body.cycle
    elif body.wp_code is not None:
        entry.cycle = _infer_cycle(body.wp_code, None)
    if body.wp_code is not None:
        entry.wp_code = body.wp_code
    if body.procedure is not None:
        entry.procedure = body.procedure
    if body.description is not None:
        entry.description = body.description

    entry.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(entry)
    return _entry_to_dict(entry)


@router.delete("/{entry_id}")
async def delete_entry(
    project_id: UUID,
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除工时条目（仅 draft 状态可删）"""
    result = await db.execute(
        select(WorkHourEntry).where(
            WorkHourEntry.id == entry_id,
            WorkHourEntry.project_id == project_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "工时条目不存在")

    if current_user.role.value != "admin" and entry.user_id != current_user.id:
        raise HTTPException(403, "只能删除自己的工时")

    if entry.status != WorkHourEntryStatus.draft.value:
        raise HTTPException(422, "仅 draft 状态可删除")

    await db.delete(entry)
    await db.commit()
    return {"detail": "已删除"}


@router.post("/batch-submit")
async def batch_submit(
    project_id: UUID,
    body: BatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量提交工时（draft → submitted，单事务）"""
    result = await db.execute(
        select(WorkHourEntry).where(
            WorkHourEntry.id.in_(body.entry_ids),
            WorkHourEntry.project_id == project_id,
        )
    )
    entries = result.scalars().all()

    submitted_count = 0
    now = datetime.now(timezone.utc)
    for entry in entries:
        if current_user.role.value != "admin" and entry.user_id != current_user.id:
            continue
        if entry.status != WorkHourEntryStatus.draft.value:
            continue
        entry.status = WorkHourEntryStatus.submitted.value
        entry.submitted_at = now
        submitted_count += 1

    await db.commit()
    return {"submitted_count": submitted_count, "total_requested": len(body.entry_ids)}


@router.get("/summary")
async def get_summary(
    project_id: UUID,
    period: Literal["day", "week", "month"] = Query("week"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """工时汇总统计"""
    stmt = select(WorkHourEntry).where(WorkHourEntry.project_id == project_id)
    if current_user.role.value != "admin":
        stmt = stmt.where(WorkHourEntry.user_id == current_user.id)

    result = await db.execute(stmt)
    entries = result.scalars().all()

    by_day: dict[str, float] = {}
    by_cycle: dict[str, float] = {}
    total = Decimal("0")

    for e in entries:
        day_key = e.date.isoformat()
        by_day[day_key] = by_day.get(day_key, 0) + float(e.hours)
        by_cycle[e.cycle] = by_cycle.get(e.cycle, 0) + float(e.hours)
        total += e.hours

    return {
        "by_day": by_day,
        "by_cycle": by_cycle,
        "total": float(total),
    }
