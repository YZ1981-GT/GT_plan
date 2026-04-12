from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import date

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.pbc_service import PBCService
from app.services.permission_service import Permission, check_project_permission

router = APIRouter(prefix="/pbc", tags=["pbc"])


class CreatePBCItemRequest(BaseModel):
    item_name: str
    category: Optional[str] = None
    requested_date: Optional[date] = None


class PBCChecklistResponse(BaseModel):
    id: str
    item_name: str
    category: Optional[str]
    requested_date: Optional[date]
    received_date: Optional[date]
    status: str
    notes: Optional[str]

    class Config:
        from_attributes = True


@router.post("/{project_id}/items")
def create_item(
    project_id: str,
    req: CreatePBCItemRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_WRITE):
        raise HTTPException(status_code=403, detail="No permission")
    item = PBCService.create_item(
        db, project_id, req.item_name, req.category, req.requested_date, str(user.id)
    )
    return {"id": str(item.id), "item_name": item.item_name}


@router.get("/{project_id}/items")
def get_items(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = PBCService.get_project_items(db, project_id)
    return [
        PBCChecklistResponse(
            id=str(i.id),
            item_name=i.item_name,
            category=i.category,
            requested_date=i.requested_date,
            received_date=i.received_date,
            status=str(i.status.value) if hasattr(i.status, "value") else str(i.status),
            notes=i.notes,
        )
        for i in items
    ]


@router.patch("/{project_id}/items/{item_id}/status")
def update_status(
    project_id: str,
    item_id: str,
    status: str = Query(...),
    received_date: Optional[date] = None,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        item = PBCService.update_status(db, item_id, status, received_date, notes)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"id": str(item.id), "status": str(item.status.value)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{project_id}/pending-reminders")
def pending_reminders(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = PBCService.get_pending_reminders(db, project_id)
    return [
        PBCChecklistResponse(
            id=str(i.id),
            item_name=i.item_name,
            category=i.category,
            requested_date=i.requested_date,
            received_date=i.received_date,
            status=str(i.status.value) if hasattr(i.status, "value") else str(i.status),
            notes=i.notes,
        )
        for i in items
    ]
