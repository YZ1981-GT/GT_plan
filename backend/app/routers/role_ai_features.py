"""角色化 LLM 辅助功能 API"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.role_ai_features import (
    get_stale_workpapers,
    generate_weekly_report,
    get_qc_trend,
    generate_project_summary,
)

router = APIRouter(prefix="/api/projects/{project_id}/ai-assist", tags=["角色AI辅助"])


@router.get("/stale-reminders")
async def stale_reminders(
    project_id: UUID,
    staff_id: UUID | None = Query(None),
    stale_days: int = Query(default=3, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """审计员：超期底稿提醒"""
    items = await get_stale_workpapers(db, project_id, staff_id, stale_days)
    return {"count": len(items), "stale_days": stale_days, "items": items}


@router.get("/weekly-report")
async def weekly_report(
    project_id: UUID,
    week_start: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """项目经理：项目周报自动生成（含LLM润色）"""
    return await generate_weekly_report(db, project_id, week_start)


@router.get("/qc-trend")
async def qc_trend(
    project_id: UUID,
    weeks: int = Query(default=4, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """质控人员：QC问题趋势"""
    return await get_qc_trend(db, project_id, weeks)


@router.get("/project-summary")
async def project_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """合伙人：一页纸项目摘要（含LLM生成叙述）"""
    return await generate_project_summary(db, project_id)
