from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import date

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.confirmation_service import ConfirmationService
from app.services.permission_service import Permission, check_project_permission

router = APIRouter(prefix="/confirmations", tags=["confirmations"])


class CreateConfirmationRequest(BaseModel):
    confirmation_type: str  # BANK, ACCOUNT_RECEIVABLE, OTHER
    description: str
    counterparty_name: str
    account_info: Optional[str] = None
    balance: Optional[float] = None
    balance_date: Optional[date] = None


class RecordResultRequest(BaseModel):
    reply_status: str  # CONFIRMED_MATCH, CONFIRMED_MISMATCH, NO_REPLY, RETURNED
    confirmed_amount: Optional[float] = None
    difference_amount: Optional[float] = None
    difference_reason: Optional[str] = None
    alternative_procedure: Optional[str] = None
    alternative_conclusion: Optional[str] = None


@router.post("/{project_id}/confirmations")
def create_confirmation(
    project_id: str,
    req: CreateConfirmationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_WRITE):
        raise HTTPException(status_code=403, detail="No permission")
    c = ConfirmationService.create_confirmation(
        db, project_id, req.confirmation_type, req.description,
        req.counterparty_name, req.account_info, req.balance, req.balance_date, str(user.id)
    )
    return {
        "id": str(c.id),
        "status": str(c.status.value) if hasattr(c.status, 'value') else str(c.status)
    }


@router.get("/{project_id}/confirmations")
def get_confirmations(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = ConfirmationService.get_confirmations(db, project_id)
    return [
        {
            "id": str(c.id),
            "confirmation_type": str(c.confirmation_type.value) if hasattr(c.confirmation_type, 'value') else str(c.confirmation_type),
            "description": c.description,
            "counterparty_name": c.counterparty_name,
            "balance": float(c.balance) if c.balance else None,
            "status": str(c.status.value) if hasattr(c.status, 'value') else str(c.status),
        }
        for c in items
    ]


@router.post("/{project_id}/confirmations/{conf_id}/letter")
def generate_letter(
    project_id: str,
    conf_id: str,
    letter_content: str = Query(...),
    letter_format: str = Query("standard"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_WRITE):
        raise HTTPException(status_code=403, detail="No permission")
    letter = ConfirmationService.generate_letter(
        db, conf_id, letter_content, letter_format, str(user.id)
    )
    return {"id": str(letter.id), "generated_at": str(letter.generated_at)}


@router.post("/{project_id}/confirmations/{conf_id}/result")
def record_result(
    project_id: str,
    conf_id: str,
    req: RecordResultRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_WRITE):
        raise HTTPException(status_code=403, detail="No permission")
    result = ConfirmationService.record_result(
        db, conf_id, req.reply_status, req.confirmed_amount, req.difference_amount,
        req.difference_reason, req.alternative_procedure, req.alternative_conclusion,
    )
    return {"id": str(result.id), "needs_adjustment": result.needs_adjustment}


@router.post("/{project_id}/summary")
def create_summary(
    project_id: str,
    summary_date: date = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not check_project_permission(db, str(user.id), project_id, Permission.PROJECT_READ):
        raise HTTPException(status_code=403, detail="No permission")
    s = ConfirmationService.create_summary(db, project_id, summary_date, str(user.id))
    return {
        "id": str(s.id),
        "total_count": s.total_count,
        "sent_count": s.sent_count,
        "replied_count": s.replied_count,
        "matched_count": s.matched_count,
        "mismatched_count": s.mismatched_count,
        "not_replied_count": s.not_replied_count,
        "returned_count": s.returned_count,
    }
