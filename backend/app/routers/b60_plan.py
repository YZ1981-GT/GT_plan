# -*- coding: utf-8 -*-
"""B60 适用性矩阵 / 计划更新 / SCOT / B60D 存档 / 质控状态 API"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.b60_plan_service import (
    AttachmentFlagsPayload,
    AttachmentFlagsResponse,
    B60dArchivePayload,
    B60dArchiveResponse,
    PlanUpdatePayload,
    PlanUpdateResponse,
    QcStatusResponse,
    ScotRowsPayload,
    ScotRowsResponse,
    bump_plan_version,
    evaluate_qc,
    get_attachment_flags,
    get_scot_rows,
    save_attachment_flags,
    save_b60d_archive,
    save_scot_rows,
)

router = APIRouter(prefix="/api", tags=["b60-plan"])


@router.get("/projects/{project_id}/b60/attachment-flags")
async def get_b60_attachment_flags(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AttachmentFlagsResponse:
    return await get_attachment_flags(project_id, db)


@router.put("/projects/{project_id}/b60/attachment-flags")
async def put_b60_attachment_flags(
    project_id: UUID,
    payload: AttachmentFlagsPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AttachmentFlagsResponse:
    result = await save_attachment_flags(project_id, payload, db)
    await db.commit()
    return result


@router.post("/projects/{project_id}/b60/plan-update")
async def post_b60_plan_update(
    project_id: UUID,
    payload: PlanUpdatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlanUpdateResponse:
    """第十五章重大更新：须 confirm_major_change + reason，递增 plan_version。"""
    if payload.bump_version:
        result = await bump_plan_version(
            project_id,
            db,
            reason=payload.reason,
            materiality_reference=payload.materiality_reference,
            flags=payload.flags,
            confirm_major_change=payload.confirm_major_change,
        )
    else:
        if payload.flags is not None or payload.materiality_reference is not None:
            await save_attachment_flags(
                project_id,
                AttachmentFlagsPayload(
                    flags=payload.flags or {},
                    materiality_reference=payload.materiality_reference,
                    auto_generate_missing=False,
                ),
                db,
            )
        state = await get_attachment_flags(project_id, db)
        result = PlanUpdateResponse(
            plan_version=state.plan_version or 1,
            materiality_reference=state.materiality_reference,
            flags=state.flags,
            reason=payload.reason,
        )
    await db.commit()
    return result


@router.get("/projects/{project_id}/b60/scot-rows")
async def get_b60_scot_rows(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScotRowsResponse:
    return await get_scot_rows(project_id, db)


@router.put("/projects/{project_id}/b60/scot-rows")
async def put_b60_scot_rows(
    project_id: UUID,
    payload: ScotRowsPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScotRowsResponse:
    result = await save_scot_rows(project_id, payload, db)
    await db.commit()
    return result


@router.put("/projects/{project_id}/b60/b60d-archive")
async def put_b60_b60d_archive(
    project_id: UUID,
    payload: B60dArchivePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> B60dArchiveResponse:
    result = await save_b60d_archive(project_id, payload, db)
    await db.commit()
    return result


@router.get("/projects/{project_id}/b60/qc-status")
async def get_b60_qc_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QcStatusResponse:
    return await evaluate_qc(project_id, db)
