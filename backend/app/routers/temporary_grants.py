"""临时授权 API（P2-1 补全）。

Endpoints:
- POST /api/projects/{project_id}/temporary-grants — 创建临时授权
- GET  /api/projects/{project_id}/temporary-grants — 列出项目临时授权
- DELETE /api/projects/{project_id}/temporary-grants/{grant_id} — 撤销临时授权
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.core import User
from app.models.temporary_grant_schemas import (
    TemporaryGrantCreate,
    TemporaryGrantListResponse,
    TemporaryGrantResponse,
)
from app.services.temporary_grant_service import (
    TemporaryGrantError,
    TemporaryGrantService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/temporary-grants",
    tags=["temporary-grants"],
)


@router.post("", response_model=TemporaryGrantResponse, status_code=201)
async def create_temporary_grant(
    project_id: UUID,
    body: TemporaryGrantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TemporaryGrantResponse:
    """创建临时授权。仅项目经理/合伙人/admin 可操作。"""
    svc = TemporaryGrantService(db)
    try:
        grant = await svc.create_grant(
            project_id=project_id,
            approver_id=current_user.id,
            data=body,
        )
        await db.commit()
        return TemporaryGrantResponse.model_validate(grant)
    except TemporaryGrantError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=TemporaryGrantListResponse)
async def list_temporary_grants(
    project_id: UUID,
    active_only: bool = Query(True, description="仅返回有效授权"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TemporaryGrantListResponse:
    """列出项目的临时授权。"""
    svc = TemporaryGrantService(db)
    grants = await svc.list_grants(project_id, active_only=active_only)
    return TemporaryGrantListResponse(
        grants=[TemporaryGrantResponse.model_validate(g) for g in grants],
        total=len(grants),
    )


@router.delete("/{grant_id}", status_code=200)
async def revoke_temporary_grant(
    project_id: UUID,
    grant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """撤销临时授权。"""
    svc = TemporaryGrantService(db)
    grant = await svc.revoke_grant(grant_id, revoker_id=current_user.id)
    if not grant:
        raise HTTPException(status_code=404, detail="授权记录不存在或已撤销")
    await db.commit()
    return {"status": "revoked", "grant_id": str(grant_id)}
