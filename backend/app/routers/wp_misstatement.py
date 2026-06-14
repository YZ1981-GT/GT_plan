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

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.misstatement_summary_service import MisstatementSummaryService

router = APIRouter(prefix="/api/workpapers")


@router.get("/{project_id}/{year}/misstatement-summary")
async def get_misstatement_summary(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """A13-1 未更正错报汇总"""
    svc = MisstatementSummaryService(db)
    return await svc.get_uncorrected_misstatements(project_id, year)


@router.get("/{project_id}/{year}/misstatement-evaluation")
async def get_misstatement_evaluation(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """A13-3 评价错报（汇总 vs 重要性）"""
    svc = MisstatementSummaryService(db)
    return await svc.evaluate_misstatements(project_id, year)


@router.get("/{project_id}/{year}/misstatement-for-letter")
async def get_misstatement_for_letter(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, str]:
    """A16 声明书用错报摘要文本"""
    svc = MisstatementSummaryService(db)
    text = await svc.get_for_representation_letter(project_id, year)
    return {"text": text}


@router.post("/{project_id}/{year}/misstatement-communication")
async def post_misstatement_communication(
    project_id: UUID,
    year: int,
    adjustment_id: UUID = Body(...),
    communication_date: str = Body(...),
    reason: str | None = Body(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """A13-5 沟通记录（回写 adjustment 的 passed_reason + 日期）"""
    svc = MisstatementSummaryService(db)
    result = await svc.record_communication(adjustment_id, communication_date, reason)
    await db.commit()
    return result
