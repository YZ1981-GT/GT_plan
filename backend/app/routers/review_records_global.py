"""复核记录全局列表端点（E1 spec UAT 修复）

- GET /api/review-records?project_id=X&target_wp=Y — 项目+底稿过滤的复核记录列表

前端 ReviewLayerBadges.vue 调用此端点拉取 L1-L5+专+IT+税 8 层 badge 状态。
通过 JOIN working_paper + wp_index 过滤项目和 wp_code。
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import ReviewRecord, WorkingPaper, WpIndex


router = APIRouter(prefix="/api/review-records", tags=["review-records"])


@router.get("")
async def list_review_records(
    project_id: UUID | None = Query(None),
    target_wp: str | None = Query(None, description="底稿编码 wp_code（如 E1）"),
    review_layer: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全局复核记录列表（按项目+底稿编码过滤）"""
    # JOIN working_paper + wp_index，按 project_id + wp_code 过滤
    stmt = (
        sa.select(ReviewRecord)
        .join(WorkingPaper, WorkingPaper.id == ReviewRecord.working_paper_id)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(ReviewRecord.is_deleted == False)
    )
    if project_id:
        stmt = stmt.where(WorkingPaper.project_id == project_id)
    if target_wp:
        stmt = stmt.where(WpIndex.wp_code == target_wp)
    if review_layer:
        stmt = stmt.where(ReviewRecord.review_layer == review_layer)
    if status:
        stmt = stmt.where(ReviewRecord.status == status)
    stmt = stmt.order_by(ReviewRecord.created_at.desc()).limit(500)

    result = await db.execute(stmt)
    items = result.scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "working_paper_id": str(r.working_paper_id),
                "cell_reference": r.cell_reference,
                "comment_text": r.comment_text,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "review_layer": r.review_layer,
                "source_sheet": r.source_sheet,
                "target_sheet": r.target_sheet,
                "target_cell": r.target_cell,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in items
        ],
        "total": len(items),
    }
