"""Phase 15: 任务树路由"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.task_tree_service import task_tree_service

router = APIRouter(prefix="/task-tree", tags=["TaskTree"])


class TransitStatusRequest(BaseModel):
    next_status: str
    operator_id: uuid.UUID


class ReassignRequest(BaseModel):
    task_node_id: uuid.UUID
    assignee_id: uuid.UUID
    operator_id: uuid.UUID
    reason_code: str


@router.get("")
async def list_task_tree(
    project_id: uuid.UUID = Query(...),
    root_level: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    assignee_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_tree_service.list_nodes(
        db, project_id, root_level, status, assignee_id, page, page_size
    )


@router.get("/stats")
async def get_tree_stats(
    project_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_tree_service.get_stats(db, project_id)


@router.get("/{node_id}")
async def get_node(
    node_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    node = await task_tree_service.get_node(db, node_id)
    return task_tree_service._to_dict(node)


@router.put("/{node_id}/status")
async def transit_status(
    node_id: uuid.UUID,
    req: TransitStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_tree_service.transit_status(
        db, node_id, req.next_status, req.operator_id
    )


@router.post("/reassign")
async def reassign_node(
    req: ReassignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await task_tree_service.reassign(
        db, req.task_node_id, req.assignee_id, req.operator_id, req.reason_code
    )
