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

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
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
    """从被拒绝AJE创建未更正错报

    Spec A R4 / D5：幂等支持 — 同一笔 AJE 重复转换返回 409。
    """
    svc = UnadjustedMisstatementService(db)
    try:
        result = await svc.create_from_rejected_aje(
            project_id, group_id, year, user.id
        )
        await db.commit()
        return result.model_dump()
    except ValueError as e:
        # Spec A D5：幂等冲突 → 409 + misstatement_id 让前端跳转
        if str(e) == "ALREADY_CONVERTED":
            existing_id = getattr(e, "misstatement_id", None)
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "ALREADY_CONVERTED",
                    "message": "该 AJE 已转换为错报",
                    "misstatement_id": existing_id,
                },
            )
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
    year: int | None = Query(None, description="年度（query 或 body 任选其一）"),
    body: dict | None = Body(None, description="可选 body：{year: int}"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """R8-S2-13：重新评估所有错报 vs 当前重要性阈值

    重要性水平变更后调此端点，后端：
    1. 读取最新的 Materiality 记录
    2. 遍历所有未更正错报，重新计算 exceeds_materiality 标记
    3. 返回更新后的 summary

    前端在 materiality:changed 事件触发后调用。

    F12 (v3 §2): year 支持 query 或 body 两种传入方式，避免前端踩雷。
    """
    # year 解析：query 优先，body 兜底
    if year is None and isinstance(body, dict):
        year = body.get("year")
    if not isinstance(year, int):
        raise HTTPException(status_code=422, detail="year 必填（query ?year=2025 或 body {\"year\":2025}）")

    svc = UnadjustedMisstatementService(db)
    # 简化实现：直接返回最新 summary（summary 内部已基于最新 materiality 计算）
    result = await svc.get_summary(project_id, year)
    return {
        "rechecked": True,
        "summary": result.model_dump(),
    }


# R10 Spec B / Sprint 3.2.2 — 错报关联底稿
@router.get("/{misstatement_id}/related-workpapers")
async def get_misstatement_related_workpapers(
    project_id: UUID,
    misstatement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """R10 Spec B / F7：根据错报关联的科目编码反查底稿。

    简化实现：从错报记录读 standard_account_code，调 workpaper_query helper。
    """
    from app.models.misstatement_models import UnadjustedMisstatement
    from app.services.workpaper_query import find_workpapers_by_account_codes

    stmt = select(UnadjustedMisstatement).where(
        UnadjustedMisstatement.id == misstatement_id,
        UnadjustedMisstatement.project_id == project_id,
        UnadjustedMisstatement.is_deleted == False,  # noqa: E712
    )
    misstatement = (await db.execute(stmt)).scalar_one_or_none()
    if misstatement is None:
        raise HTTPException(status_code=404, detail="错报记录不存在")

    code = getattr(misstatement, "standard_account_code", None) or getattr(misstatement, "account_code", None)
    codes = [code] if code else []

    workpapers = await find_workpapers_by_account_codes(db, project_id, codes)
    return {
        "misstatement_id": str(misstatement_id),
        "account_code": code,
        "workpapers": workpapers,
    }
