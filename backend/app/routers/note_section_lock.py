"""附注章节锁定路由 — 多人协作

Requirements: 44.1-44.6
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.note_section_lock_service import NoteSectionLockService

router = APIRouter(
    prefix="/api/projects/{project_id}/notes/locks",
    tags=["note-section-lock"],
)


class AcquireLockRequest(BaseModel):
    year: int
    section_code: str


class ReleaseLockRequest(BaseModel):
    year: int
    section_code: str


class ForceReleaseRequest(BaseModel):
    year: int
    section_code: str


@router.post("/acquire")
async def acquire_lock(
    project_id: UUID,
    body: AcquireLockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取章节编辑锁"""
    svc = NoteSectionLockService(db)
    result = await svc.acquire_lock(
        project_id=project_id,
        year=body.year,
        section_code=body.section_code,
        user_id=current_user.id,
        user_name=getattr(current_user, "display_name", "") or str(current_user.id),
    )
    await db.commit()

    if "error" in result and result["error"] == "LOCK_HELD":
        raise HTTPException(status_code=409, detail=result)

    return result


@router.post("/release")
async def release_lock(
    project_id: UUID,
    body: ReleaseLockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """释放章节编辑锁"""
    svc = NoteSectionLockService(db)
    released = await svc.release_lock(
        project_id=project_id,
        year=body.year,
        section_code=body.section_code,
        user_id=current_user.id,
    )
    await db.commit()
    return {"released": released}


@router.post("/force-release")
async def force_release_lock(
    project_id: UUID,
    body: ForceReleaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """项目经理强制解锁"""
    svc = NoteSectionLockService(db)
    released = await svc.force_release(
        project_id=project_id,
        year=body.year,
        section_code=body.section_code,
        admin_user_id=current_user.id,
    )
    await db.commit()
    return {"released": released}


@router.post("/heartbeat")
async def heartbeat(
    project_id: UUID,
    body: AcquireLockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """心跳续期"""
    svc = NoteSectionLockService(db)
    renewed = await svc.heartbeat(
        project_id=project_id,
        year=body.year,
        section_code=body.section_code,
        user_id=current_user.id,
    )
    await db.commit()
    return {"renewed": renewed}


@router.get("/active")
async def get_active_locks(
    project_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取项目所有活跃锁"""
    svc = NoteSectionLockService(db)
    return await svc.get_active_locks(project_id, year)
