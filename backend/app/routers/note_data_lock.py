"""报表附注数据锁定与版本快照路由

Requirements: 53.1-53.7
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.note_data_lock_service import NoteDataLockService

router = APIRouter(
    prefix="/api/projects/{project_id}/data-lock",
    tags=["note-data-lock"],
)


class LockRequest(BaseModel):
    year: int


class UnlockRequest(BaseModel):
    year: int
    reason: str = Field(..., min_length=1, description="解锁原因")


class SnapshotRequest(BaseModel):
    year: int


@router.post("/lock")
async def lock_on_sign_off(
    project_id: UUID,
    body: LockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """签字后锁定报表和附注数据"""
    svc = NoteDataLockService(db)
    result = await svc.lock_on_sign_off(project_id, body.year)
    await db.commit()
    return result


@router.post("/unlock")
async def unlock_data(
    project_id: UUID,
    body: UnlockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """管理员解锁（需填写原因）"""
    svc = NoteDataLockService(db)
    result = await svc.unlock(project_id, body.year, current_user.id, body.reason)
    await db.commit()
    return result


@router.post("/snapshot")
async def create_snapshot(
    project_id: UUID,
    body: SnapshotRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动创建数据快照"""
    svc = NoteDataLockService(db)
    result = await svc.create_snapshot(project_id, body.year)
    await db.commit()
    return result


@router.get("/snapshots")
async def get_snapshot_chain(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取版本快照历史链"""
    svc = NoteDataLockService(db)
    return await svc.get_snapshot_chain(project_id, year)


@router.get("/status")
async def get_lock_status(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取锁定状态"""
    svc = NoteDataLockService(db)
    locked = await svc.is_locked(project_id, year)
    return {"locked": locked, "project_id": str(project_id), "year": year}
