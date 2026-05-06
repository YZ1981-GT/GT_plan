"""底稿编辑软锁端点 — Round 4 需求 11

POST   /api/workpapers/{wp_id}/editing-lock          — 获取锁
PATCH  /api/workpapers/{wp_id}/editing-lock/heartbeat — 续期
DELETE /api/workpapers/{wp_id}/editing-lock           — 释放锁
POST   /api/workpapers/{wp_id}/editing-lock/force     — 强制获取（覆盖）
GET    /api/workpapers/editing-locks/active           — 管理员查看所有活跃锁
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services import editing_lock_service

router = APIRouter(
    prefix="/api/workpapers",
    tags=["editing-lock"],
)


@router.post("/{wp_id}/editing-lock")
async def acquire_lock(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取底稿编辑锁

    如果已有活跃锁（heartbeat_at > now - 5min），返回锁持有者信息。
    如果是同一用户重复 acquire，自动续期。
    """
    result = await editing_lock_service.acquire_lock(db, wp_id, current_user.id)
    await db.commit()
    if not result["acquired"]:
        # 返回 409 表示锁冲突
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "LOCK_HELD",
                "locked_by": result["locked_by"],
                "acquired_at": result["acquired_at"],
            },
        )
    return result


@router.patch("/{wp_id}/editing-lock/heartbeat")
async def heartbeat(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """续期编辑锁 heartbeat

    前端每 2 分钟调用一次。无活跃锁时返回 404。
    """
    result = await editing_lock_service.heartbeat_lock(db, wp_id, current_user.id)
    await db.commit()
    if not result["ok"]:
        raise HTTPException(status_code=404, detail="无活跃锁")
    return result


@router.delete("/{wp_id}/editing-lock")
async def release(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """释放编辑锁

    页面关闭前调用。无活跃锁时返回 404。
    """
    result = await editing_lock_service.release_lock(db, wp_id, current_user.id)
    await db.commit()
    if not result["released"]:
        raise HTTPException(status_code=404, detail="无活跃锁")
    return result


@router.post("/{wp_id}/editing-lock/force")
async def force_acquire(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """强制获取编辑锁（覆盖现有锁）

    用于"强制编辑"场景。释放当前持有者的锁并创建新锁。
    原持有者应收到通知（由前端或后续 notification 处理）。
    """
    result = await editing_lock_service.force_acquire_lock(
        db, wp_id, current_user.id
    )
    await db.commit()
    return result


@router.get("/editing-locks/active")
async def list_active_locks(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取所有活跃编辑锁列表（管理员/经理监控用）"""
    locks = await editing_lock_service.get_active_locks(db)
    return {"locks": locks}
