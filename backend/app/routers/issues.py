"""Phase 15: 统一问题单路由"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import PaginationParams
from app.deps import get_current_user
from app.models.core import User
from app.services.issue_ticket_service import issue_ticket_service

router = APIRouter(prefix="/issues", tags=["IssueTickets"])


class IssueFromConversationRequest(BaseModel):
    conversation_id: uuid.UUID
    task_node_id: Optional[uuid.UUID] = None
    operator_id: uuid.UUID
    sla_level: str  # P0/P1/P2


class IssueStatusUpdateRequest(BaseModel):
    status: str
    operator_id: uuid.UUID
    reason_code: str
    evidence_refs: Optional[list] = None


class IssueEscalateRequest(BaseModel):
    from_level: str
    to_level: str
    reason_code: str


@router.post("/from-conversation")
async def create_issue_from_conversation(
    req: IssueFromConversationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await issue_ticket_service.create_from_conversation(
        db, req.conversation_id, req.operator_id, req.sla_level, req.task_node_id
    )


@router.get("")
async def list_issues(
    project_id: uuid.UUID = Query(...),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    owner_id: Optional[uuid.UUID] = Query(None),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await issue_ticket_service.list_issues(
        db, project_id, status, severity, source, owner_id,
        page=pagination.page, page_size=pagination.page_size,
    )


@router.put("/{issue_id}/status")
async def update_issue_status(
    issue_id: uuid.UUID,
    req: IssueStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await issue_ticket_service.update_status(
        db, issue_id, req.status, req.operator_id, req.reason_code, req.evidence_refs
    )


@router.post("/{issue_id}/escalate")
async def escalate_issue(
    issue_id: uuid.UUID,
    req: IssueEscalateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await issue_ticket_service.escalate(
        db, issue_id, req.from_level, req.to_level, req.reason_code
    )
