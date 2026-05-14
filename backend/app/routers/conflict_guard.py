"""Conflict Guard API — 调整分录编辑锁端点

POST /{entry_group_id}/lock — 获取编辑锁
PATCH /{entry_group_id}/lock/heartbeat — 续期
DELETE /{entry_group_id}/lock — 释放锁

409 状态码返回锁定者信息。

Validates: Requirements 5.1, 5.2, 5.3
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.conflict_guard_service import ConflictGuardService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/adjustments",
    tags=["conflict-guard"],
)


@router.post("/{entry_group_id}/lock")
async def acquire_lock(
    project_id: UUID,
    entry_group_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取调整分录编辑锁。

    成功返回锁信息，已被他人锁定返回 409。
    """
    svc = ConflictGuardService(db)
    result = await svc.acquire_lock(
        project_id=project_id,
        entry_group_id=entry_group_id,
        user_id=current_user.id,
        user_name=current_user.username or str(current_user.id),
    )
    await db.commit()
    return result


@router.patch("/{entry_group_id}/lock/heartbeat")
async def heartbeat_lock(
    project_id: UUID,
    entry_group_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """续期编辑锁心跳。"""
    svc = ConflictGuardService(db)
    success = await svc.heartbeat_lock(
        project_id=project_id,
        entry_group_id=entry_group_id,
        user_id=current_user.id,
    )
    await db.commit()
    if not success:
        return {"status": "not_found", "message": "No active lock found for this user"}
    return {"status": "ok"}


@router.delete("/{entry_group_id}/lock")
async def release_lock(
    project_id: UUID,
    entry_group_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """释放编辑锁。"""
    svc = ConflictGuardService(db)
    success = await svc.release_lock(
        project_id=project_id,
        entry_group_id=entry_group_id,
        user_id=current_user.id,
    )
    await db.commit()
    if not success:
        return {"status": "not_found", "message": "No active lock found for this user"}
    return {"status": "released"}
