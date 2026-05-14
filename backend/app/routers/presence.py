"""Presence API — 在线感知端点

POST /heartbeat — 心跳上报
GET /online — 获取在线成员列表
GET /editing — 获取编辑状态列表

Validates: Requirements 2.1, 2.4, 2.5
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from redis.asyncio import Redis

from app.core.redis import get_redis
from app.deps import get_current_user
from app.models.core import User
from app.services.presence_service import PresenceService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/presence",
    tags=["presence"],
)


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class HeartbeatRequest(BaseModel):
    """心跳请求体"""
    view_name: str
    editing_info: dict[str, Any] | None = None


class OnlineMember(BaseModel):
    """在线成员"""
    user_id: str
    user_name: str
    view_name: str
    last_heartbeat: float


class EditingState(BaseModel):
    """编辑状态"""
    user_id: str
    user_name: str | None = None
    view: str | None = None
    account_code: str | None = None
    entry_group_id: str | None = None
    started_at: float | None = None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("/heartbeat")
async def heartbeat(
    project_id: UUID,
    body: HeartbeatRequest,
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict[str, str]:
    """心跳上报：更新用户在线状态和编辑状态。"""
    svc = PresenceService(redis)
    await svc.heartbeat(
        project_id=project_id,
        user_id=current_user.id,
        user_name=current_user.username or str(current_user.id),
        view_name=body.view_name,
        editing_info=body.editing_info,
    )
    return {"status": "ok"}


@router.get("/online", response_model=list[OnlineMember])
async def get_online_members(
    project_id: UUID,
    view_name: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> list[dict[str, Any]]:
    """获取当前在线成员列表。"""
    svc = PresenceService(redis)
    return await svc.get_online_members(project_id, view_name)


@router.get("/editing", response_model=list[EditingState])
async def get_editing_states(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> list[dict[str, Any]]:
    """获取当前编辑状态列表。"""
    svc = PresenceService(redis)
    return await svc.get_editing_states(project_id)
