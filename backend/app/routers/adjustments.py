"""审计调整分录 API

覆盖：
- GET  列表（支持 type/status 筛选）
- POST 创建
- PUT  修改
- DELETE 软删除
- POST review 变更状态
- GET  summary 汇总统计
- GET  account-dropdown 科目下拉
- GET  wp-summary/{wp_code} 底稿审定表数据
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, check_consol_lock
from app.models.audit_platform_models import AdjustmentType, ReviewStatus
from app.models.audit_platform_schemas import (
    AccountOption,
    AdjustmentCreate,
    AdjustmentSummary,
    AdjustmentUpdate,
    ReviewStatusChange,
    WPAdjustmentSummary,
)
from app.services.adjustment_service import AdjustmentService

router = APIRouter(
    prefix="/api/projects/{project_id}/adjustments",
    tags=["adjustments"],
)


@router.get("")
async def list_adjustments(
    project_id: UUID,
    year: int = Query(...),
    adjustment_type: AdjustmentType | None = Query(None),
    review_status: ReviewStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
current_user: User = Depends(get_current_user),
):
    """分录列表（支持 type/status 筛选）"""
    svc = AdjustmentService(db)
    return await svc.list_entries(
        project_id, year,
        adjustment_type=adjustment_type,
        review_status=review_status,
        page=page, page_size=page_size,
    )


@router.post("")
async def create_adjustment(
    project_id: UUID,
    data: AdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _lock_check=Depends(check_consol_lock),
):
    """创建调整分录（合并锁定期间禁止）"""
    svc = AdjustmentService(db)
    try:
        result = await svc.create_entry(project_id, data, user.id)
        await db.commit()
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{entry_group_id}")
async def update_adjustment(
    project_id: UUID,
    entry_group_id: UUID,
    data: AdjustmentUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _lock_check=Depends(check_consol_lock),
):
    """修改调整分录（合并锁定期间禁止）"""
    svc = AdjustmentService(db)
    try:
        result = await svc.update_entry(project_id, entry_group_id, data, user.id)
        await db.commit()
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{entry_group_id}")
async def delete_adjustment(
    project_id: UUID,
    entry_group_id: UUID,
    db: AsyncSession = Depends(get_db),
    _lock_check=Depends(check_consol_lock),
):
    """软删除调整分录（合并锁定期间禁止）"""
    svc = AdjustmentService(db)
    try:
        await svc.delete_entry(project_id, entry_group_id)
        await db.commit()
        return {"message": "删除成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{entry_group_id}/review")
async def review_adjustment(
    project_id: UUID,
    entry_group_id: UUID,
    change: ReviewStatusChange,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """变更复核状态"""
    svc = AdjustmentService(db)
    try:
        await svc.change_review_status(
            project_id, entry_group_id, change, user.id
        )
        await db.commit()
        return {"message": "状态变更成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/summary")
async def get_summary(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """汇总统计"""
    svc = AdjustmentService(db)
    result = await svc.get_summary(project_id, year)
    return result.model_dump()


@router.get("/account-dropdown")
async def get_account_dropdown(
    project_id: UUID,
    report_line_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
current_user: User = Depends(get_current_user),
):
    """科目下拉选项"""
    svc = AdjustmentService(db)
    options = await svc.get_account_dropdown(project_id, report_line_code)
    return [o.model_dump() for o in options]


@router.get("/wp-summary/{wp_code}")
async def get_wp_summary(
    project_id: UUID,
    wp_code: str,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
current_user: User = Depends(get_current_user),
):
    """底稿审定表数据"""
    svc = AdjustmentService(db)
    result = await svc.get_wp_adjustment_summary(project_id, year, wp_code)
    return result.model_dump()
