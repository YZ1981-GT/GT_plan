"""Phase 16: 离线冲突路由"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.offline_conflict_service import offline_conflict_service

router = APIRouter(prefix="/offline/conflicts", tags=["OfflineConflicts"])


class ConflictDetectRequest(BaseModel):
    project_id: uuid.UUID
    wp_id: uuid.UUID


class ConflictResolveRequest(BaseModel):
    conflict_id: uuid.UUID
    resolution: str  # accept_local/accept_remote/manual_merge
    merged_value: Optional[dict] = None
    resolver_id: uuid.UUID
    reason_code: str


@router.post("/detect")
async def detect_conflicts(
    req: ConflictDetectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await offline_conflict_service.detect(db, req.project_id, req.wp_id)


@router.post("/resolve")
async def resolve_conflict(
    req: ConflictResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await offline_conflict_service.resolve(
        db, req.conflict_id, req.resolution, req.resolver_id,
        req.reason_code, req.merged_value,
    )


@router.get("")
async def list_conflicts(
    project_id: uuid.UUID = Query(...),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await offline_conflict_service.list_conflicts(db, project_id, status, page, page_size)
