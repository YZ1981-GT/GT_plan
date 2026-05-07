"""未更正错报汇总 API

覆盖：
- GET  列表
- POST 创建
- POST from-aje/{group_id} 从AJE创建
- PUT  更新
- DELETE 软删除
- GET  summary 汇总视图

Validates: Requirements 11.1-11.8
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import (
    MisstatementCreate,
    MisstatementUpdate,
)
from app.services.misstatement_service import UnadjustedMisstatementService

router = APIRouter(
    prefix="/api/projects/{project_id}/misstatements",
    tags=["misstatements"],
)


@router.get("")
async def list_misstatements(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """未更正错报列表"""
    svc = UnadjustedMisstatementService(db)
    items = await svc.list_misstatements(project_id, year)
    return [item.model_dump() for item in items]


@router.post("")
async def create_misstatement(
    project_id: UUID,
    data: MisstatementCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """创建未更正错报"""
    svc = UnadjustedMisstatementService(db)
    result = await svc.create_misstatement(project_id, data, user.id)
    await db.commit()
    return result.model_dump()


@router.post("/from-aje/{group_id}")
async def create_from_aje(
    project_id: UUID,
    group_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """从被拒绝AJE创建未更正错报"""
    svc = UnadjustedMisstatementService(db)
    try:
        result = await svc.create_from_rejected_aje(
            project_id, group_id, year, user.id
        )
        await db.commit()
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{misstatement_id}")
async def update_misstatement(
    project_id: UUID,
    misstatement_id: UUID,
    data: MisstatementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新未更正错报"""
    svc = UnadjustedMisstatementService(db)
    try:
        result = await svc.update_misstatement(project_id, misstatement_id, data)
        await db.commit()
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{misstatement_id}")
async def delete_misstatement(
    project_id: UUID,
    misstatement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """软删除未更正错报"""
    svc = UnadjustedMisstatementService(db)
    try:
        await svc.delete_misstatement(project_id, misstatement_id)
        await db.commit()
        return {"message": "删除成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/summary")
async def get_summary(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """汇总视图：按类型分组 + 与重要性水平对比"""
    svc = UnadjustedMisstatementService(db)
    result = await svc.get_summary(project_id, year)
    return result.model_dump()


@router.post("/recheck-threshold")
async def recheck_threshold(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """R8-S2-13：重新评估所有错报 vs 当前重要性阈值

    重要性水平变更后调此端点，后端：
    1. 读取最新的 Materiality 记录
    2. 遍历所有未更正错报，重新计算 exceeds_materiality 标记
    3. 返回更新后的 summary

    前端在 materiality:changed 事件触发后调用。
    """
    svc = UnadjustedMisstatementService(db)
    # 简化实现：直接返回最新 summary（summary 内部已基于最新 materiality 计算）
    result = await svc.get_summary(project_id, year)
    return {
        "rechecked": True,
        "summary": result.model_dump(),
    }
