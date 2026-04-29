"""工时管理 API 路由

Phase 9 Task 1.6
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.staff_schemas import WorkHourCreate, WorkHourUpdate
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
    svc = WorkHourService(db)
    return await svc.list_hours(staff_id, start_date, end_date)


@router.post("/staff/{staff_id}/work-hours")
async def create_hour(
    staff_id: UUID,
    data: WorkHourCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WorkHourService(db)
    wh, warnings = await svc.create_hour(staff_id, data.model_dump())
    await db.commit()
    return {
        "id": str(wh.id),
        "work_date": str(wh.work_date),
        "hours": float(wh.hours),
        "warnings": warnings,
    }


@router.put("/work-hours/{hour_id}")
async def update_hour(
    hour_id: UUID,
    data: WorkHourUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = WorkHourService(db)
    wh = await svc.update_hour(hour_id, data.model_dump(exclude_none=True))
    if not wh:
        raise HTTPException(404, "工时记录不存在")
    await db.commit()
    return {"id": str(wh.id), "status": wh.status}


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
