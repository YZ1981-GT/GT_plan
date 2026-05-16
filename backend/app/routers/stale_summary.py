"""Stale 底稿汇总端点 [R7-S2-09 + Spec A R2]

GET /api/projects/{project_id}/stale-summary       — 仅底稿粒度（向后兼容）
GET /api/projects/{project_id}/stale-summary/full  — Spec A 多模块聚合
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["stale"],
)


@router.get("/stale-summary")
async def get_stale_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回项目中标记为 stale 的底稿列表"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    stmt = (
        select(WorkingPaper, WpIndex.wp_code, WpIndex.wp_name)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.prefill_stale == True,  # noqa: E712
            WorkingPaper.is_deleted == False,  # noqa: E712
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {
        "stale_count": len(rows),
        "items": [
            {
                "id": str(wp.id),
                "wp_code": wp_code,
                "wp_name": wp_name,
                "stale_reason": None,
            }
            for wp, wp_code, wp_name in rows
        ],
    }


@router.get("/stale-summary/full")
async def get_stale_summary_full(
    project_id: UUID,
    year: int = Query(..., description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Spec A R2: 多模块聚合 stale 摘要

    返回 4 个模块（workpapers / reports / notes / misstatements）
    的 stale 计数 + 至多 30 条 items 摘要 + last_event_at。

    供 PartnerSignDecision / EqcrProjectView / WorkpaperList 使用。
    """
    from app.services.stale_summary_aggregate import get_full_summary

    return await get_full_summary(db, project_id, year)
