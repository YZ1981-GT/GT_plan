"""EQCR 工作台路由

Refinement Round 5 任务 3 + 任务 5 — EQCR 工作台 REST API。

访问控制说明（与需求 1 验收标准 2 对齐）：
- 统一用 ``Depends(get_current_user)``，service 层按 user → staff →
  ``ProjectAssignment.role='eqcr'`` 自行过滤，保证"本人作为 EQCR 的项目"
  的隐私边界。不强制检查 ``user.role``（UserRole 是系统级，
  ProjectAssignment.role 是项目级，分层独立）。
- overview 端点在用户不是该项目 EQCR 时仍返回数据，但把
  ``my_role_confirmed=false`` 回传前端，由 UI 决定是否展示"只读模式"
  或跳转；这样更便于跨角色复盘。

任务 5 新增（需求 2）：
- 5 个判断域聚合接口（materiality / estimates / related-parties /
  going-concern / opinion-type），每个接口返回统一 shape::

      {"project_id": str, "domain": str, "data": {...},
       "current_opinion": dict|None, "history_opinions": list[dict]}

- 意见 CRUD 两个接口：``POST /api/eqcr/opinions`` 新建；
  ``PATCH /api/eqcr/opinions/{opinion_id}`` 更新。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.eqcr_service import EqcrService


router = APIRouter(prefix="/api/eqcr", tags=["eqcr"])


# ---------------------------------------------------------------------------
# Pydantic 请求模型（任务 5 内联，集中放在路由文件避免 schemas 文件蔓延）
# ---------------------------------------------------------------------------


class EqcrOpinionCreate(BaseModel):
    """POST /api/eqcr/opinions 请求体。"""

    project_id: UUID = Field(..., description="项目 ID")
    domain: str = Field(
        ...,
        description=(
            "判断域；允许值 materiality / estimate / related_party / "
            "going_concern / opinion_type / component_auditor"
        ),
    )
    verdict: str = Field(
        ...,
        description="评议结论；允许值 agree / disagree / need_more_evidence",
    )
    comment: str | None = Field(None, description="意见说明")
    extra_payload: dict[str, Any] | None = Field(
        None,
        description="附加结构化数据；需求 11 组成部分审计师场景可携带 auditor_id/name",
    )


class EqcrOpinionUpdate(BaseModel):
    """PATCH /api/eqcr/opinions/{id} 请求体；所有字段可选。"""

    verdict: str | None = Field(None)
    comment: str | None = Field(None)
    extra_payload: dict[str, Any] | None = Field(None)


# ---------------------------------------------------------------------------
# 任务 3：工作台列表 + 项目总览
# ---------------------------------------------------------------------------


@router.get("/projects")
async def list_my_eqcr_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回本人作为 EQCR 的项目卡片列表（签字日升序）。"""
    svc = EqcrService(db)
    return await svc.list_my_projects(current_user.id)


@router.get("/projects/{project_id}/overview")
async def get_eqcr_project_overview(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回项目 EQCR 总览数据（用于 EqcrProjectView 详情页壳）。"""
    svc = EqcrService(db)
    data = await svc.get_project_overview(current_user.id, project_id)
    if data is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return data


# ---------------------------------------------------------------------------
# 任务 5：5 个判断域聚合 API
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
# 任务 5：意见 CRUD
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
    # 先查询原 opinion 以校验创建人
    from sqlalchemy import select
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
