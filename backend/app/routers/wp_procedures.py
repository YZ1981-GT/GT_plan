"""底稿审计程序管理路由

Sprint 2 Task 2.2:
  GET  /                    获取程序清单（含裁剪状态）
  PATCH /{proc_id}/complete 标记程序完成
  PATCH /{proc_id}/trim     裁剪程序（经理/合伙人）
  POST  /custom             新增自定义程序
  POST  /copy-from-prior    从上年复制程序清单
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.wp_procedure_service import WpProcedureService
from app.services.wp_quality_score_linkage import recalc_quality_score

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/procedures",
    tags=["workpaper-procedures"],
)


# ─── Request / Response Models ────────────────────────────────────────────────


class TrimRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class CustomProcedureRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=1000)
    category: str = Field(default="custom", max_length=30)
    evidence_type: str | None = None


class CopyFromPriorRequest(BaseModel):
    prior_wp_id: str


class CompleteRequest(BaseModel):
    user_id: str


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("")
async def get_procedures(
    project_id: str,
    wp_id: str,
    include_trimmed: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """获取程序清单（含裁剪状态）"""
    svc = WpProcedureService(db)
    procedures = await svc.list_procedures(
        UUID(wp_id),
        include_trimmed=include_trimmed,
    )
    return {"items": procedures, "total": len(procedures)}


@router.patch("/{proc_id}/complete")
async def complete_procedure(
    project_id: str,
    wp_id: str,
    proc_id: str,
    body: CompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """标记程序完成"""
    svc = WpProcedureService(db)
    result = await svc.mark_complete(UUID(proc_id), UUID(body.user_id))
    if not result:
        raise HTTPException(status_code=404, detail="程序不存在")
    # 触发 quality_score 重算
    await recalc_quality_score(db, UUID(wp_id))
    await db.commit()
    return result


@router.patch("/{proc_id}/trim")
async def trim_procedure(
    project_id: str,
    wp_id: str,
    proc_id: str,
    body: TrimRequest,
    db: AsyncSession = Depends(get_db),
):
    """裁剪程序（经理/合伙人权限）"""
    svc = WpProcedureService(db)
    try:
        result = await svc.trim_procedure(
            UUID(proc_id),
            # TODO: 从 auth context 获取 user_id
            UUID("00000000-0000-0000-0000-000000000000"),
            body.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="程序不存在")
    # 裁剪影响完成率，触发 quality_score 重算
    await recalc_quality_score(db, UUID(wp_id))
    await db.commit()
    return result


@router.post("/custom")
async def create_custom_procedure(
    project_id: str,
    wp_id: str,
    body: CustomProcedureRequest,
    db: AsyncSession = Depends(get_db),
):
    """新增自定义程序"""
    svc = WpProcedureService(db)
    result = await svc.create_custom(
        wp_id=UUID(wp_id),
        project_id=UUID(project_id),
        description=body.description,
        category=body.category,
        evidence_type=body.evidence_type,
    )
    await db.commit()
    return result


@router.post("/copy-from-prior")
async def copy_from_prior(
    project_id: str,
    wp_id: str,
    body: CopyFromPriorRequest,
    db: AsyncSession = Depends(get_db),
):
    """从上年复制程序清单"""
    svc = WpProcedureService(db)
    results = await svc.copy_from_prior(
        wp_id=UUID(wp_id),
        project_id=UUID(project_id),
        prior_wp_id=UUID(body.prior_wp_id),
    )
    await db.commit()
    return {"items": results, "total": len(results)}
