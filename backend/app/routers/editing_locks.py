"""通用编辑锁端点 — global-refinement-v5-closure 能力域 C

POST   /api/editing-locks/{resource_type}/{resource_id}            — acquire
PATCH  /api/editing-locks/{resource_type}/{resource_id}/heartbeat  — 续期
DELETE /api/editing-locks/{resource_type}/{resource_id}            — release
POST   /api/editing-locks/{resource_type}/{resource_id}/force      — force-acquire
GET    /api/editing-locks/active                                   — 活跃锁列表
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.editing_lock_service_v2 import (
    acquire_lock,
    force_acquire_lock,
    get_active_locks,
    heartbeat_lock,
    release_lock,
)

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
    return result
