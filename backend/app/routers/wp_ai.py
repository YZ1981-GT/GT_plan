"""AI 辅助底稿 API

Phase 9 Task 9.8
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.wp_ai_service import WpAIService

router = APIRouter(prefix="/api/workpapers", tags=["wp-ai"])


@router.post("/{wp_id}/ai/analytical-review")
async def analytical_review(
    wp_id: UUID,
    account_code: str = Query(...),
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.models.workpaper_models import WorkingPaper
    wp = (await db.execute(
        __import__("sqlalchemy").select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()
    if not wp:
        from fastapi import HTTPException
        raise HTTPException(404, "底稿不存在")
    svc = WpAIService(db)
    return await svc.analytical_review(wp.project_id, account_code, year)


@router.post("/{wp_id}/ai/extract-confirmations")
async def extract_confirmations(
    wp_id: UUID,
    account_code: str = Query(...),
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.models.workpaper_models import WorkingPaper
    import sqlalchemy as sa
    wp = (await db.execute(sa.select(WorkingPaper).where(WorkingPaper.id == wp_id))).scalar_one_or_none()
    if not wp:
        from fastapi import HTTPException
        raise HTTPException(404, "底稿不存在")
    svc = WpAIService(db)
    return await svc.extract_confirmations(wp.project_id, account_code, year)


@router.post("/{wp_id}/ai/check-consistency")
async def check_consistency(
    wp_id: UUID,
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.models.workpaper_models import WorkingPaper
    import sqlalchemy as sa
    wp = (await db.execute(sa.select(WorkingPaper).where(WorkingPaper.id == wp_id))).scalar_one_or_none()
    if not wp:
        from fastapi import HTTPException
        raise HTTPException(404, "底稿不存在")
    svc = WpAIService(db)
    return await svc.check_wp_report_consistency(wp.project_id, year)
