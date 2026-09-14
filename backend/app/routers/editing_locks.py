"""通用编辑锁端点 — global-refinement-v5-closure 能力域 C

POST   /api/editing-locks/{resource_type}/{resource_id}            — acquire
PATCH  /api/editing-locks/{resource_type}/{resource_id}/heartbeat  — 续期
DELETE /api/editing-locks/{resource_type}/{resource_id}            — release
POST   /api/editing-locks/{resource_type}/{resource_id}/force      — force-acquire
GET    /api/editing-locks/active                                   — 活跃锁列表
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.editing_lock_service import (
    acquire_lock,
    force_acquire_lock,
    get_active_locks,
    heartbeat_lock,
    release_lock,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/editing-locks",
    tags=["editing-locks"],
)


def _holder_name(user: User) -> str:
    """从 User 取 holder_name：full_name > username > 空串"""
    return getattr(user, "full_name", None) or user.username or ""


@router.get("/active")
async def list_active_locks(
    resource_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取活跃锁列表（可选 ?resource_type= 过滤）"""
    locks = await get_active_locks(db, resource_type=resource_type)
    await db.commit()
    return {"locks": locks}


@router.post("/{resource_type}/{resource_id}")
async def acquire(
    resource_type: str,
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取编辑锁"""
    result = await acquire_lock(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        holder_id=current_user.id,
        holder_name=_holder_name(current_user),
    )
    await db.commit()

    if result.get("locked"):
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "LOCK_HELD",
                "locked_by": result["locked_by"],
                "locked_by_name": result["locked_by_name"],
                "acquired_at": result["acquired_at"],
            },
        )
    return result


@router.patch("/{resource_type}/{resource_id}/heartbeat")
async def heartbeat(
    resource_type: str,
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """续期 heartbeat"""
    result = await heartbeat_lock(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        holder_id=current_user.id,
    )
    await db.commit()

    if not result.get("refreshed"):
        raise HTTPException(status_code=404, detail="无活跃锁")
    return result


@router.delete("/{resource_type}/{resource_id}")
async def release(
    resource_type: str,
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """释放编辑锁"""
    result = await release_lock(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        holder_id=current_user.id,
    )
    await db.commit()

    if not result.get("released"):
        raise HTTPException(status_code=404, detail="无活跃锁")
    return result


@router.post("/{resource_type}/{resource_id}/force")
async def force_acquire(
    resource_type: str,
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """强制获取锁（释放原锁 + 创建新锁）"""
    result = await force_acquire_lock(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        holder_id=current_user.id,
        holder_name=_holder_name(current_user),
    )
    await db.commit()

    # Best-effort SSE notification for force-acquired event
    try:
        from app.services.event_bus import event_bus

        # Resolve project_id for SSE routing
        project_id = await _resolve_project_id(db, resource_type, resource_id)

        payload = {
            "project_id": str(project_id) if project_id else None,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "new_holder_id": str(current_user.id),
            "new_holder_name": _holder_name(current_user),
            "previous_holder_id": result.get("previous_holder_id"),
        }
        # Frontend useEditingLock matches force events by wp_id for workpapers
        if resource_type == "workpaper":
            payload["wp_id"] = resource_id

        event_bus.broadcast_raw("editing_lock.force_acquired", payload)
    except Exception as exc:
        logger.warning(
            "Failed to broadcast editing_lock.force_acquired for %s/%s: %s",
            resource_type,
            resource_id,
            exc,
        )

    return result


async def _resolve_project_id(
    db: AsyncSession, resource_type: str, resource_id: str
) -> UUID | None:
    """Best-effort resolve project_id from the resource for SSE routing.

    Returns None if resolution fails (non-blocking).
    """
    try:
        if resource_type == "workpaper":
            from sqlalchemy import select

            from app.models.workpaper_models import WorkingPaper

            # resource_id 来自 URL path（str），WorkingPaper.id 是 UUID 列
            # 需显式转 UUID 以兼容 SQLite 测试环境（PG 隐式转换但显式更健壮）
            wp_uuid = UUID(resource_id)
            stmt = select(WorkingPaper.project_id).where(
                WorkingPaper.id == wp_uuid
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            return row
    except Exception as exc:
        logger.warning(
            "_resolve_project_id failed for %s/%s: %s",
            resource_type,
            resource_id,
            exc,
        )
    return None
