"""同步路由 — ProjectSync 状态查询、锁定与同步记录"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.sync_service import SyncService
from app.services.permission_service import Permission, check_project_permission
from app.models.collaboration_models import SyncType

router = APIRouter(prefix="/sync", tags=["sync"])


class SyncStatusResponse(BaseModel):
    """同步状态响应"""
    project_id: str
    global_version: int
    sync_status: str
    is_locked: bool
    locked_by: Optional[str]
    locked_at: Optional[datetime]
    last_synced_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/status/{project_id}", response_model=SyncStatusResponse)
def get_status(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取项目同步状态"""
    if not check_project_permission(
        db, str(user.id), project_id, Permission.PROJECT_READ
    ):
        raise HTTPException(status_code=403, detail="No access to this project")
    sync = SyncService.get_sync_status(db, project_id)
    if not sync:
        return SyncStatusResponse(
            project_id=project_id,
            global_version=0,
            sync_status="idle",
            is_locked=False,
            locked_by=None,
            locked_at=None,
            last_synced_at=None,
        )
    return SyncStatusResponse(
        project_id=str(sync.project_id),
        global_version=sync.global_version,
        sync_status=sync.sync_status.value
        if hasattr(sync.sync_status, "value")
        else str(sync.sync_status),
        is_locked=sync.is_locked,
        locked_by=str(sync.locked_by) if sync.locked_by else None,
        locked_at=sync.locked_at,
        last_synced_at=sync.last_synced_at,
    )


@router.post("/lock/{project_id}")
def acquire_lock(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取项目同步锁定"""
    if not check_project_permission(
        db, str(user.id), project_id, Permission.SYNC_MANAGE
    ):
        raise HTTPException(status_code=403, detail="No permission")
    ok = SyncService.acquire_lock(db, project_id, str(user.id))
    if not ok:
        raise HTTPException(status_code=409, detail="Project is already locked")
    return {"message": "Lock acquired"}


@router.post("/unlock/{project_id}")
def release_lock(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """释放项目同步锁定"""
    ok = SyncService.release_lock(db, project_id, str(user.id))
    return {"message": "Lock released" if ok else "Not your lock"}


@router.post("/sync/{project_id}")
def record_sync(
    project_id: str,
    sync_type: str = "upload",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """记录项目同步操作"""
    if not check_project_permission(
        db, str(user.id), project_id, Permission.SYNC_MANAGE
    ):
        raise HTTPException(status_code=403, detail="No permission")
    valid_types = [e.name for e in SyncType]
    st = SyncType[sync_type] if sync_type in valid_types else SyncType.UPLOAD
    sync = SyncService.record_sync(db, project_id, str(user.id), st)
    return {
        "global_version": sync.global_version,
        "status": str(sync.sync_status.value),
    }
