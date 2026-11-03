"""A13 错报汇总 API 路由

GET  /api/workpapers/{project_id}/{year}/misstatement-summary
GET  /api/workpapers/{project_id}/{year}/misstatement-evaluation
GET  /api/workpapers/{project_id}/{year}/misstatement-for-letter
POST /api/workpapers/{project_id}/{year}/misstatement-communication

Requirements: 1.x, 2.x, 4.x
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access, require_project_permission
from app.models.core import User
from app.services.misstatement_summary_service import MisstatementSummaryService

router = APIRouter(prefix="/api/workpapers")


@router.get("/{project_id}/{year}/misstatement-summary")
async def get_misstatement_summary(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """A13-1 未更正错报汇总"""
    svc = MisstatementSummaryService(db)
    return await svc.get_uncorrected_misstatements(project_id, year)


@router.get("/{project_id}/{year}/misstatement-evaluation")
async def get_misstatement_evaluation(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """A13-3 评价错报（汇总 vs 重要性）"""
    svc = MisstatementSummaryService(db)
    return await svc.evaluate_misstatements(project_id, year)


@router.get("/{project_id}/{year}/misstatement-for-letter")
async def get_misstatement_for_letter(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> dict[str, str]:
    """A16 声明书用错报摘要文本"""
    svc = MisstatementSummaryService(db)
    text = await svc.get_for_representation_letter(project_id, year)
    return {"text": text}


@router.post("/{project_id}/{year}/misstatement-communication")
async def post_misstatement_communication(
    project_id: UUID,
    year: int,
    misstatement_id: UUID | None = Body(None),
    adjustment_id: UUID | None = Body(None),
    communication_date: str = Body(...),
    reason: str | None = Body(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_permission("adjustment:convert_to_misstatement")),
) -> dict[str, Any]:
    """A13 沟通记录；兼容旧 adjustment_id，但只更新正式错报表。"""
    target_id = misstatement_id
    if target_id is None and adjustment_id is not None:
        from app.models.audit_platform_models import UnadjustedMisstatement
        target_id = (await db.execute(select(UnadjustedMisstatement.id).where(
            UnadjustedMisstatement.project_id == project_id,
            UnadjustedMisstatement.year == year,
            UnadjustedMisstatement.source_adjustment_id == adjustment_id,
            UnadjustedMisstatement.is_deleted.is_(False),
        ))).scalar_one_or_none()
    if target_id is None:
        raise HTTPException(status_code=422, detail="misstatement_id 必填")
    svc = MisstatementSummaryService(db)
    try:
        result = await svc.record_communication(
            project_id, year, target_id, communication_date, reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return result
