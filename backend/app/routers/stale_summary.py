"""Stale 底稿汇总端点 [R7-S2-09]

GET /api/projects/{project_id}/stale-summary
返回当前项目中 prefill_stale=True 的底稿列表。
"""
from uuid import UUID

from fastapi import APIRouter, Depends
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
