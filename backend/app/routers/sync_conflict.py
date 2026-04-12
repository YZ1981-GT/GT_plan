from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.sync_conflict_service import SyncConflictService
from app.services.permission_service import Permission, check_project_permission

router = APIRouter(prefix="/sync-conflicts", tags=["sync-conflicts"])


class DetectConflictRequest(BaseModel):
    local_data: dict
    server_data: dict


class ResolveConflictRequest(BaseModel):
    winning_data: dict
    losing_data: dict
    resolution: str  # "server_wins", "client_wins", "manual_merge"


@router.post("/{project_id}/detect")
def detect_conflict(
    project_id: str,
    req: DetectConflictRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.SYNC_MANAGE):
        raise HTTPException(403, "No permission")
    has_conflict = SyncConflictService.detect_conflict(
        db, project_id, req.local_data, req.server_data
    )
    return {"has_conflict": has_conflict}


@router.post("/{project_id}/resolve")
def resolve_conflict(
    project_id: str,
    req: ResolveConflictRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.SYNC_MANAGE):
        raise HTTPException(403, "No permission")
    valid_resolutions = ["server_wins", "client_wins", "manual_merge"]
    if req.resolution not in valid_resolutions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resolution. Must be one of: {valid_resolutions}",
        )
    resolved = SyncConflictService.resolve_conflict(
        db, project_id, req.winning_data, req.losing_data, req.resolution, str(user.id)
    )
    return {"resolved_data": resolved, "resolution": req.resolution}


@router.get("/{project_id}/history")
def conflict_history(
    project_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.SYNC_MANAGE):
        raise HTTPException(403, "No permission")
    logs = SyncConflictService.get_conflict_history(db, project_id, skip, limit)
    return [
        {
            "id": str(l.id),
            "details": l.details,
            "created_at": l.created_at,
            "user_id": str(l.user_id),
        }
        for l in logs
    ]
