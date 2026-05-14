"""联动查询 API — 企业级联动

GET /tb-row/{row_code}/adjustments — 试算表行关联的调整分录
GET /tb-row/{row_code}/workpapers — 试算表行关联的底稿
GET /impact-preview — 影响预判（query: account_code, amount）
GET /change-history/{row_code} — 审定数变更历史时间线

Validates: Requirements 3.1, 3.3, 4.1, 8.3
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.linkage_service import LinkageService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/linkage",
    tags=["linkage"],
)


@router.get("/tb-row/{row_code}/adjustments")
async def get_tb_row_adjustments(
    project_id: UUID,
    row_code: str,
    year: int = Query(..., description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取试算平衡表某行关联的调整分录列表。"""
    svc = LinkageService(db)
    adjustments = await svc.get_adjustments_for_tb_row(project_id, year, row_code)
    return {"items": adjustments, "total": len(adjustments)}


@router.get("/tb-row/{row_code}/workpapers")
async def get_tb_row_workpapers(
    project_id: UUID,
    row_code: str,
    year: int = Query(..., description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取试算平衡表某行关联的底稿列表。"""
    svc = LinkageService(db)
    workpapers = await svc.get_workpapers_for_tb_row(project_id, year, row_code)
    return {"items": workpapers, "total": len(workpapers)}


@router.get("/impact-preview")
async def get_impact_preview(
    project_id: UUID,
    account_code: str = Query(..., description="科目编码"),
    year: int = Query(..., description="年度"),
    amount: float | None = Query(None, description="变动金额（可选）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """影响预判：输入科目编码，返回受影响的 TB 行/报表行/底稿。"""
    svc = LinkageService(db)
    preview = await svc.get_impact_preview(project_id, year, account_code, amount)
    return preview


@router.get("/change-history/{row_code}")
async def get_change_history(
    project_id: UUID,
    row_code: str,
    year: int = Query(..., description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取试算平衡表某行的变更历史时间线。"""
    svc = LinkageService(db)
    history = await svc.get_change_history(project_id, year, row_code)
    return {"items": history, "total": len(history)}


@router.post("/consistency-check")
async def run_consistency_check(
    project_id: UUID,
    year: int = Query(..., description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """一致性校验：全量重算对比增量结果。

    Returns differences between incremental TB values and full recalculation.
    Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
    """
    svc = LinkageService(db)
    result = await svc.run_consistency_check(project_id, year)
    return result
