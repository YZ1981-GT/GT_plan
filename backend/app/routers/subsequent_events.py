from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.subsequent_event_service import SubsequentEventService
from app.services.permission_service import Permission, check_project_permission

router = APIRouter(prefix="/subsequent-events", tags=["subsequent-events"])


class CreateEventRequest(BaseModel):
    event_date: date
    event_type: str  # "ADJUSTING" or "NON_ADJUSTING"
    description: str
    financial_impact: Optional[float] = None


class ChecklistItemCreate(BaseModel):
    item_code: Optional[str]
    description: str
    is_completed: bool = False


class ChecklistItemUpdate(BaseModel):
    item_code: Optional[str] = None
    description: Optional[str] = None
    is_completed: Optional[bool] = None
    notes: Optional[str] = None


class ChecklistItemResponse(BaseModel):
    id: str
    item_code: Optional[str]
    description: str
    is_completed: bool
    completed_at: Optional[datetime]
    notes: Optional[str]
    completed_by: Optional[str] = None
    notes: Optional[str]

    class Config:
        from_attributes = True


@router.post("/{project_id}/events")
def create_event(
    project_id: str,
    req: CreateEventRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_WRITE):
        raise HTTPException(status_code=403, detail="No permission")
    e = SubsequentEventService.create_event(
        db,
        project_id,
        str(req.event_date),
        req.event_type,
        req.description,
        req.financial_impact,
        str(user.id),
    )
    return {
        "id": str(e.id),
        "event_type": str(e.event_type.value),
        "event_date": str(e.event_date),
    }


@router.get("/{project_id}/events")
def get_events(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    events = SubsequentEventService.get_project_events(db, project_id)
    return [
        {
            "id": str(e.id),
            "event_date": str(e.event_date),
            "event_type": str(e.event_type.value)
            if hasattr(e.event_type, "value")
            else str(e.event_type),
            "description": e.description,
            "financial_impact": float(e.financial_impact) if e.financial_impact else None,
            "is_disclosed": e.is_disclosed,
        }
        for e in events
    ]


@router.post("/{project_id}/checklist/init")
def init_checklist(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_WRITE):
        raise HTTPException(status_code=403, detail="No permission")
    items = SubsequentEventService.init_checklist(db, project_id)
    return {"message": f"Initialized {len(items)} checklist items"}


@router.get("/{project_id}/checklist")
def get_checklist(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = SubsequentEventService.get_checklist(db, project_id)
    return [
        ChecklistItemResponse(
            id=str(i.id),
            item_code=i.item_code,
            description=i.description,
            is_completed=i.is_completed,
            completed_at=i.completed_at,
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
    item = SubsequentEventService.complete_checklist_item(db, item_id, str(user.id), notes)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"id": str(item.id), "is_completed": item.is_completed}


@router.post("/{project_id}/checklist")
def create_checklist_item(
    project_id: str,
    body: ChecklistItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = SubsequentEventService.create_checklist_item(db, project_id, body.dict())
    return {"id": str(item.id)}


@router.patch("/{project_id}/checklist/{item_id}")
def update_checklist_item(
    project_id: str,
    item_id: str,
    body: ChecklistItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = SubsequentEventService.update_checklist_item(db, item_id, body.dict(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {
        "id": str(item.id),
        "item_code": item.item_code,
        "description": item.description,
        "is_completed": item.is_completed,
        "completed_at": item.completed_at,
        "notes": item.notes,
    }


@router.delete("/{project_id}/checklist/{item_id}")
def delete_checklist_item(
    project_id: str,
    item_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ok = SubsequentEventService.delete_checklist_item(db, item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}
