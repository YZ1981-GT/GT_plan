from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.archive_service import ArchiveService
from app.services.permission_service import Permission, check_project_permission

router = APIRouter(prefix="/archive", tags=["archive"])


class ArchiveItemResponse(BaseModel):
    id: str
    item_code: str
    item_name: str
    category: Optional[str]
    is_completed: bool
    completed_at: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True


@router.post("/{project_id}/checklist/init")
def init_checklist(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.ARCHIVE_MANAGE):
        raise HTTPException(403, "No permission")
    items = ArchiveService.init_checklist(db, project_id)
    return {"message": f"Initialized {len(items)} items"}


@router.get("/{project_id}/checklist")
def get_checklist(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = ArchiveService.get_checklist(db, project_id)
    return [
        ArchiveItemResponse(
            id=str(i.id),
            item_code=i.item_code or "",
            item_name=i.item_name,
            category=i.category,
            is_completed=i.is_completed,
            completed_at=str(i.completed_at) if i.completed_at else None,
            notes=i.notes,
        )
        for i in items
    ]


@router.post("/{project_id}/checklist/{item_id}/complete")
def complete_item(
    project_id: str,
    item_id: str,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = ArchiveService.complete_item(db, item_id, str(user.id), notes)
    if not item:
        raise HTTPException(404, "Item not found")
    return {"id": str(item.id), "is_completed": item.is_completed}


@router.post("/{project_id}/modifications")
def request_modification(
    project_id: str,
    modification_type: str = Query(...),
    description: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mod = ArchiveService.request_modification(
        db, project_id, str(user.id), modification_type, description
    )
    status_val = mod.approval_status.value if hasattr(mod.approval_status, "value") else str(mod.approval_status)
    return {"id": str(mod.id), "approval_status": status_val}


@router.post("/{project_id}/modifications/{mod_id}/approve")
def approve_modification(
    project_id: str,
    mod_id: str,
    comments: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mod = ArchiveService.approve_modification(db, mod_id, str(user.id), comments)
    if not mod:
        raise HTTPException(404, "Not found")
    status_val = mod.approval_status.value if hasattr(mod.approval_status, "value") else str(mod.approval_status)
    return {"id": str(mod.id), "status": status_val}


@router.post("/{project_id}/modifications/{mod_id}/reject")
def reject_modification(
    project_id: str,
    mod_id: str,
    comments: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mod = ArchiveService.reject_modification(db, mod_id, str(user.id), comments)
    if not mod:
        raise HTTPException(404, "Not found")
    status_val = mod.approval_status.value if hasattr(mod.approval_status, "value") else str(mod.approval_status)
    return {"id": str(mod.id), "status": status_val}


@router.get("/{project_id}/modifications/pending")
def pending_modifications(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mods = ArchiveService.get_pending_modifications(db, project_id)
    return [
        {
            "id": str(m.id),
            "modification_type": m.modification_type,
            "description": m.description,
            "approval_status": m.approval_status.value if hasattr(m.approval_status, "value") else str(m.approval_status),
        }
        for m in mods
    ]
