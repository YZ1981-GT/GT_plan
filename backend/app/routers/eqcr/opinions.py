"""EQCR 判断域聚合 + 意见 CRUD"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.eqcr_service import EqcrService

from .schemas import EqcrOpinionCreate, EqcrOpinionUpdate

router = APIRouter()


# ---------------------------------------------------------------------------
# 5 个判断域聚合 API
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/materiality")
async def get_eqcr_materiality(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """需求 2.2：重要性 Tab 数据聚合 + 本域意见历史。"""
    svc = EqcrService(db)
    return await svc.get_materiality(project_id)


@router.get("/projects/{project_id}/estimates")
async def get_eqcr_estimates(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """需求 2.3：会计估计 Tab 数据（底稿维度聚合）。"""
    svc = EqcrService(db)
    return await svc.get_estimates(project_id)


@router.get("/projects/{project_id}/related-parties")
async def get_eqcr_related_parties(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """需求 2.4：关联方 Tab 数据（注册表 + 交易明细）。"""
    svc = EqcrService(db)
    return await svc.get_related_parties(project_id)


@router.get("/projects/{project_id}/going-concern")
async def get_eqcr_going_concern(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """需求 2.5：持续经营 Tab 数据（复用 GoingConcernEvaluation 模型）。"""
    svc = EqcrService(db)
    return await svc.get_going_concern(project_id)


@router.get("/projects/{project_id}/opinion-type")
async def get_eqcr_opinion_type(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """需求 2.6：审计意见类型 Tab 数据（AuditReport 视角 + 本域意见历史）。"""
    svc = EqcrService(db)
    return await svc.get_opinion_type(project_id)


# ---------------------------------------------------------------------------
# 意见 CRUD
# ---------------------------------------------------------------------------


@router.post("/opinions")
async def create_eqcr_opinion(
    payload: EqcrOpinionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建一条 EQCR 判断域意见（对应需求 2.7）。"""
    svc = EqcrService(db)
    try:
        result = await svc.create_opinion(
            project_id=payload.project_id,
            domain=payload.domain,
            verdict=payload.verdict,
            comment=payload.comment,
            extra_payload=payload.extra_payload,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return result


@router.patch("/opinions/{opinion_id}")
async def update_eqcr_opinion(
    opinion_id: UUID,
    payload: EqcrOpinionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新一条 EQCR 意见。只有创建人（或 admin）可改。"""
    svc = EqcrService(db)
    from app.models.eqcr_models import EqcrOpinion

    existing = (
        await db.execute(
            select(EqcrOpinion).where(
                EqcrOpinion.id == opinion_id,
                EqcrOpinion.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="意见不存在")
    is_admin = current_user.role.value == "admin" if current_user.role else False
    if existing.created_by != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="只有创建人或管理员可修改")

    try:
        result = await svc.update_opinion(
            opinion_id=opinion_id,
            user_id=current_user.id,
            verdict=payload.verdict,
            comment=payload.comment,
            extra_payload=payload.extra_payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="意见不存在")
    await db.commit()
    return result
