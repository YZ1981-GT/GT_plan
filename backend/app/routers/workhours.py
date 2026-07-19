"""工时管理 API 路由 — 兼容层

原 Phase 9 端点，V117 迁移后改为从 work_hour_entries 读写。
保持旧接口格式向后兼容（WeeklyTimesheet 已迁移到 batch-quick，此处供旧版客户端/第三方）。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.staff_models import StaffMember
from app.models.workhour_entry_models import WorkHourEntry
from app.models.staff_schemas import WorkHourCreate, WorkHourUpdate
from app.models.core import Project
from app.services.workhour_service import WorkHourService

router = APIRouter(prefix="/api", tags=["workhours"])


@router.get("/staff/{staff_id}/work-hours")
async def list_hours(
    staff_id: UUID,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """兼容层：从 work_hour_entries 读取并返回旧格式"""
    # staff_id → user_id
    staff_result = await db.execute(
        sa.select(StaffMember.user_id).where(
            StaffMember.id == staff_id,
            StaffMember.is_deleted == False,
        )
    )
    staff_user_id = staff_result.scalar_one_or_none()
    if not staff_user_id:
        return []

    q = (
        sa.select(WorkHourEntry, Project.name.label("project_name"))
        .join(Project, WorkHourEntry.project_id == Project.id)
        .where(WorkHourEntry.user_id == staff_user_id)
    )
    if start_date:
        q = q.where(WorkHourEntry.date >= start_date)
    if end_date:
        q = q.where(WorkHourEntry.date <= end_date)
    q = q.order_by(WorkHourEntry.date.desc(), WorkHourEntry.created_at.desc())

    rows = (await db.execute(q)).all()
    return [
        {
            "id": str(entry.id),
            "staff_id": str(staff_id),
            "project_id": str(entry.project_id),
            "project_name": project_name,
            "work_date": str(entry.date),
            "hours": float(entry.hours),
            "start_time": None,
            "end_time": None,
            "description": entry.description,
            "status": entry.status,
            "ai_suggested": False,
        }
        for entry, project_name in rows
    ]


@router.post("/staff/{staff_id}/work-hours")
async def create_hour(
    staff_id: UUID,
    data: WorkHourCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """兼容层：写入 work_hour_entries"""
    # staff_id → user_id
    staff_result = await db.execute(
        sa.select(StaffMember.user_id).where(
            StaffMember.id == staff_id,
            StaffMember.is_deleted == False,
        )
    )
    staff_user_id = staff_result.scalar_one_or_none()
    if not staff_user_id:
        raise HTTPException(404, "人员不存在或未关联用户")

    entry = WorkHourEntry(
        user_id=staff_user_id,
        project_id=data.project_id,
        date=data.work_date,
        hours=data.hours,
        cycle="OTHER",
        description=data.description or "",
        status="draft",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return {
        "id": str(entry.id),
        "work_date": str(entry.date),
        "hours": float(entry.hours),
        "warnings": [],
    }


@router.put("/work-hours/{hour_id}")
async def update_hour(
    hour_id: UUID,
    data: WorkHourUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """兼容层：更新 work_hour_entries"""
    result = await db.execute(
        sa.select(WorkHourEntry).where(WorkHourEntry.id == hour_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "工时记录不存在")

    if data.hours is not None:
        entry.hours = data.hours
    if data.description is not None:
        entry.description = data.description
    if data.status is not None:
        entry.status = data.status
    entry.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return {"id": str(entry.id), "status": entry.status}


@router.post("/work-hours/ai-suggest")
async def ai_suggest(
    staff_id: UUID = Query(...),
    target_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WorkHourService(db)
    suggestions = await svc.ai_suggest(staff_id, target_date)
    return {"suggestions": suggestions}


@router.get("/projects/{project_id}/work-hours")
async def project_hours(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WorkHourService(db)
    return await svc.project_summary(project_id)


# ---------------------------------------------------------------------------
# 批量保存工时（消除 N+1 串行 HTTP）
# ---------------------------------------------------------------------------

class WorkHourBatchItem(BaseModel):
    project_id: UUID
    work_date: date
    hours: Decimal = Field(ge=0, le=24)
    description: str | None = None


class WorkHourBatchRequest(BaseModel):
    items: list[WorkHourBatchItem] = Field(..., min_length=1, max_length=50)


@router.post("/staff/{staff_id}/work-hours/batch")
async def batch_save_hours(
    staff_id: UUID,
    data: WorkHourBatchRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """批量保存工时（upsert 语义：同 staff+project+date 有记录则更新，无则创建）。

    单次请求最多 50 条，消除前端逐条保存的 N+1 问题。
    权限：只能操作自己关联的 staff 记录（admin 豁免）。
    """
    import sqlalchemy as sa
    from app.models.staff_models import WorkHour, StaffMember

    # 权限校验：staff_id 必须关联到当前用户（admin 豁免）
    if user.role.value != "admin":
        staff_result = await db.execute(
            sa.select(StaffMember.user_id).where(
                StaffMember.id == staff_id,
                StaffMember.is_deleted == False,
            )
        )
        staff_user_id = staff_result.scalar_one_or_none()
        if staff_user_id != user.id:
            from fastapi import HTTPException as _H
            raise _H(status_code=403, detail="只能操作自己的工时记录")

    created = 0
    updated = 0

    for item in data.items:
        # 查找是否已有记录
        result = await db.execute(
            sa.select(WorkHour).where(
                WorkHour.staff_id == staff_id,
                WorkHour.project_id == item.project_id,
                WorkHour.work_date == item.work_date,
                WorkHour.is_deleted == False,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            if float(existing.hours) != float(item.hours) or existing.description != item.description:
                existing.hours = item.hours
                if item.description is not None:
                    existing.description = item.description
                updated += 1
        else:
            if float(item.hours) > 0:
                wh = WorkHour(
                    staff_id=staff_id,
                    project_id=item.project_id,
                    work_date=item.work_date,
                    hours=item.hours,
                    description=item.description or "",
                )
                db.add(wh)
                created += 1

    await db.commit()
    return {"created": created, "updated": updated, "total": created + updated}


@router.get("/work-hours/edit-time-suggest")
async def edit_time_suggest(
    staff_id: UUID = Query(...),
    target_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """基于底稿编辑时间自动生成工时建议

    从审计日志中提取该用户当天编辑了哪些底稿、各花了多少时间，
    作为工时填报的预填建议。
    """
    import sqlalchemy as sa
    from app.models.core import Log
    from app.models.workpaper_models import WpIndex
    from datetime import datetime, timedelta

    # 查找该用户当天的底稿编辑日志
    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    result = await db.execute(
        sa.select(Log.new_value, Log.created_at).where(
            Log.user_id == staff_id,
            Log.action.in_(["workpaper_online_open", "workpaper_online_save"]),
            Log.created_at >= day_start,
            Log.created_at < day_end,
        ).order_by(Log.created_at)
    )
    logs = result.all()

    if not logs:
        return {"suggestions": [], "message": "当天无底稿编辑记录"}

    # 按底稿分组计算时间
    wp_times: dict[str, dict] = {}  # wp_id → {first, last, count}
    for log_value, log_time in logs:
        # new_value 中包含 wp_id
        wp_id = ""
        if log_value and isinstance(log_value, (str, dict)):
            val = log_value if isinstance(log_value, dict) else {}
            wp_id = val.get("wp_id", str(log_value)[:36] if len(str(log_value)) >= 36 else "")

        if not wp_id:
            continue

        if wp_id not in wp_times:
            wp_times[wp_id] = {"first": log_time, "last": log_time, "count": 0}
        wp_times[wp_id]["last"] = log_time
        wp_times[wp_id]["count"] += 1

    # 生成建议
    suggestions = []
    for wp_id, times in wp_times.items():
        duration_min = (times["last"] - times["first"]).total_seconds() / 60
        if duration_min < 1:
            duration_min = 15  # 最少15分钟

        # 查找底稿名称
        wp_name = wp_id[:8]
        try:
            idx_result = await db.execute(
                sa.select(WpIndex.wp_code, WpIndex.wp_name).where(
                    WpIndex.id == sa.select(sa.text("wp_index_id")).select_from(
                        sa.text("working_paper")
                    ).where(sa.text(f"id = '{wp_id}'")).scalar_subquery()
                )
            )
            idx_row = idx_result.first()
            if idx_row:
                wp_name = f"{idx_row[0]} {idx_row[1]}"
        except Exception:
            pass

        suggestions.append({
            "wp_id": wp_id,
            "wp_name": wp_name,
            "duration_minutes": round(duration_min),
            "start_time": times["first"].strftime("%H:%M"),
            "end_time": times["last"].strftime("%H:%M"),
            "sessions": times["count"],
        })

    total_minutes = sum(s["duration_minutes"] for s in suggestions)
    return {
        "date": target_date.isoformat(),
        "suggestions": suggestions,
        "total_minutes": total_minutes,
        "total_hours": round(total_minutes / 60, 1),
        "message": f"当天编辑了 {len(suggestions)} 个底稿，共约 {round(total_minutes/60, 1)} 小时",
    }


# ---------------------------------------------------------------------------
# 跨项目工时查询（消除 WeeklyTimesheet 逐项目 N+1）
# ---------------------------------------------------------------------------


@router.get("/my/work-hour-entries")
async def my_work_hour_entries(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """当前用户跨项目工时条目查询。

    返回当前用户在所有项目的 work_hour_entries，支持日期范围过滤。
    消除 WeeklyTimesheet 逐项目调 listEntries 的 N+1 问题。
    """
    from app.models.core import Project as _P

    q = (
        sa.select(WorkHourEntry, _P.name.label("project_name"))
        .join(_P, WorkHourEntry.project_id == _P.id)
        .where(WorkHourEntry.user_id == user.id)
    )
    if start_date:
        q = q.where(WorkHourEntry.date >= start_date)
    if end_date:
        q = q.where(WorkHourEntry.date <= end_date)
    q = q.order_by(WorkHourEntry.date.desc(), WorkHourEntry.created_at.desc())

    rows = (await db.execute(q)).all()
    return [
        {
            "id": str(entry.id),
            "user_id": str(entry.user_id),
            "project_id": str(entry.project_id),
            "project_name": project_name,
            "date": str(entry.date),
            "hours": float(entry.hours),
            "cycle": entry.cycle,
            "wp_code": entry.wp_code,
            "procedure": entry.procedure,
            "description": entry.description,
            "status": entry.status,
        }
        for entry, project_name in rows
    ]
