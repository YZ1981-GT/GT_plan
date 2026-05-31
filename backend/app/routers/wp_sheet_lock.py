"""底稿 sheet 级软锁端点

POST   /api/workpapers/{wp_id}/sheets/{sheet_name}/lock           — 获取锁
PATCH  /api/workpapers/{wp_id}/sheets/{sheet_name}/lock/heartbeat — 续期
DELETE /api/workpapers/{wp_id}/sheets/{sheet_name}/lock           — 释放锁
GET    /api/workpapers/{wp_id}/sheets/{sheet_name}/lock           — 查询锁持有者
GET    /api/workpapers/{wp_id}/sheet-locks                        — 查询底稿所有活跃锁

Requirements: 6.1, 6.2, 6.4
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.wp_sheet_lock_service import WpSheetLockService

router = APIRouter(
    prefix="/api/workpapers",
    tags=["wp-sheet-lock"],
)


@router.post("/{wp_id}/sheets/{sheet_name}/lock")
async def acquire_sheet_lock(
    wp_id: UUID,
    sheet_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取 sheet 级编辑锁。

    同一用户重复 acquire 自动续期。
    其他用户持有时返回 409。
    """
    service = WpSheetLockService(db)
    result = await service.acquire_lock(
        wp_id=wp_id,
        sheet_name=sheet_name,
        user_id=current_user.id,
        user_name=getattr(current_user, "display_name", None)
        or getattr(current_user, "username", ""),
    )
    await db.commit()

    if not result.get("acquired"):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "SHEET_LOCK_HELD",
                "message": f"{result.get('locked_by_name', '其他用户')} 正在编辑此 sheet",
                "locked_by": result.get("locked_by"),
                "locked_by_name": result.get("locked_by_name"),
                "acquired_at": result.get("acquired_at"),
            },
        )
    return result


@router.patch("/{wp_id}/sheets/{sheet_name}/lock/heartbeat")
async def heartbeat_sheet_lock(
    wp_id: UUID,
    sheet_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """续期 sheet 锁心跳。前端每 2 分钟调用一次。"""
    service = WpSheetLockService(db)
    ok = await service.heartbeat(
        wp_id=wp_id,
        sheet_name=sheet_name,
        user_id=current_user.id,
    )
    await db.commit()

    if not ok:
        raise HTTPException(status_code=404, detail="无活跃锁")
    return {"ok": True}


@router.delete("/{wp_id}/sheets/{sheet_name}/lock")
async def release_sheet_lock(
    wp_id: UUID,
    sheet_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """释放 sheet 锁。页面关闭/切 tab 时调用。"""
    service = WpSheetLockService(db)
    released = await service.release_lock(
        wp_id=wp_id,
        sheet_name=sheet_name,
        user_id=current_user.id,
    )
    await db.commit()

    if not released:
        raise HTTPException(status_code=404, detail="无活跃锁")
    return {"released": True}


@router.get("/{wp_id}/sheets/{sheet_name}/lock")
async def get_sheet_lock_holder(
    wp_id: UUID,
    sheet_name: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """查询 sheet 锁持有者。无锁时返回 null。"""
    service = WpSheetLockService(db)
    holder = await service.get_lock_holder(wp_id=wp_id, sheet_name=sheet_name)
    return {"holder": holder}


@router.get("/{wp_id}/sheet-locks")
async def get_wp_sheet_locks(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """查询底稿所有活跃 sheet 锁。"""
    service = WpSheetLockService(db)
    locks = await service.get_wp_active_locks(wp_id=wp_id)
    return {"locks": locks}
