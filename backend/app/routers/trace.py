"""Phase 14: Trace 回放与查询路由

对齐 v2 5.9.3 A-02: GET /api/trace/{trace_id}/replay
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import PaginationParams
from app.deps import get_current_user
from app.models.core import User
from app.services.trace_event_service import trace_event_service

router = APIRouter(prefix="/trace", tags=["Trace"])


@router.get("/{trace_id}/replay")
async def replay_trace(
    trace_id: str,
    level: str = Query("L1", pattern="^(L1|L2|L3)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按 trace_id 回放完整事件链

    - L1: 事件摘要（who/what/when）
    - L2: 含 before/after snapshot
    - L3: 含 content_hash 可复算校验
    """
    result = await trace_event_service.replay(db, trace_id, level)
    if result["replay_status"] == "broken":
        raise HTTPException(status_code=404, detail={
            "error_code": "TRACE_NOT_FOUND",
            "message": f"trace_id '{trace_id}' 不存在",
            "trace_id": trace_id,
        })
    return result


@router.get("")
async def query_traces(
    project_id: uuid.UUID = Query(...),
    event_type: Optional[str] = Query(None),
    object_type: Optional[str] = Query(None),
    object_id: Optional[uuid.UUID] = Query(None),
    actor_id: Optional[uuid.UUID] = Query(None),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按项目/对象/时间/角色检索 trace 事件"""
    return await trace_event_service.query(
        db, project_id, event_type, object_type, object_id, actor_id,
        page=pagination.page, page_size=pagination.page_size,
    )
