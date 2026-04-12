"""Management Letter API Router.

Validates: Requirements 11.5, 11.9
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.services.management_letter_service import ManagementLetterService

router = APIRouter(prefix="/management-letter", tags=["管理建议书"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ManagementLetterItemCreate(BaseModel):
    deficiency_type: str  # significant_deficiency / material_weakness / other_deficiency
    deficiency_description: str
    potential_impact: str = ""
    recommendation: str = ""
    management_response: Optional[str] = None
    response_deadline: Optional[str] = None


class FollowUpUpdate(BaseModel):
    follow_up_status: str  # new / in_progress / resolved / carried_forward
    management_response: Optional[str] = None
    response_deadline: Optional[str] = None
    notes: Optional[str] = None


class CarryForwardRequest(BaseModel):
    source_project_id: str


class ManagementLetterItemResponse(BaseModel):
    id: str
    project_id: str
    item_code: str
    deficiency_type: str
    deficiency_description: str
    potential_impact: str
    recommendation: str
    management_response: Optional[str]
    response_deadline: Optional[str]
    prior_year_item_id: Optional[str]
    follow_up_status: str
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------
_items_store: List[dict] = []
_prior_items_store: List[dict] = {}  # project_id -> items


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/management-letter-items",
             response_model=ManagementLetterItemResponse)
def create_management_letter_item(
    project_id: str,
    data: ManagementLetterItemCreate,
    db: Session = Depends(get_db),
):
    """Create a new management letter item."""
    item = ManagementLetterService.create_item(
        db=db,
        project_id=project_id,
        deficiency_type=data.deficiency_type,
        deficiency_description=data.deficiency_description,
        potential_impact=data.potential_impact,
        recommendation=data.recommendation,
        management_response=data.management_response,
        response_deadline=data.response_deadline,
    )
    _items_store.append(item)
    return ManagementLetterItemResponse(**item)


@router.get("/projects/{project_id}/management-letter-items",
            response_model=List[ManagementLetterItemResponse])
def list_management_letter_items(
    project_id: str,
    include_resolved: bool = True,
    db: Session = Depends(get_db),
):
    """Get all management letter items for a project."""
    items = [i for i in _items_store if i["project_id"] == project_id]
    if not include_resolved:
        items = [i for i in items if i["follow_up_status"] != "resolved"]
    return [ManagementLetterItemResponse(**i) for i in items]


@router.put("/items/{item_id}/follow-up")
def update_follow_up(
    item_id: str,
    data: FollowUpUpdate,
    db: Session = Depends(get_db),
):
    """Update follow-up status of a management letter item."""
    try:
        result = ManagementLetterService.update_follow_up(
            db=db,
            item_id=item_id,
            follow_up_status=data.follow_up_status,
            management_response=data.management_response,
            response_deadline=data.response_deadline,
            notes=data.notes,
        )
        # Update in store
        for item in _items_store:
            if item["id"] == item_id:
                item.update(result)
                break
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/carry-forward")
def carry_forward_items(
    project_id: str,
    data: CarryForwardRequest,
    db: Session = Depends(get_db),
):
    """Carry forward unresolved items from prior year project."""
    source_project_id = data.source_project_id
    prior_items = _prior_items_store.get(source_project_id, [])

    carried = ManagementLetterService.carry_forward_items(
        db=db,
        source_project_id=source_project_id,
        target_project_id=project_id,
        prior_items=prior_items,
    )

    # Add to store
    for item in carried:
        _items_store.append(item)

    return {
        "message": f"Carried forward {len(carried)} items from project {source_project_id}",
        "carried_items": [ManagementLetterItemResponse(**i) for i in carried],
    }


@router.get("/items/{item_id}", response_model=ManagementLetterItemResponse)
def get_management_letter_item(
    item_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific management letter item."""
    for item in _items_store:
        if item["id"] == item_id:
            return ManagementLetterItemResponse(**item)
    raise HTTPException(status_code=404, detail="Management letter item not found")
