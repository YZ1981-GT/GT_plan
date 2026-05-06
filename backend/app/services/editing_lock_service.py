"""底稿编辑软锁服务

Refinement Round 4 — 需求 11

策略：
- 有效锁 = released_at IS NULL AND heartbeat_at > now - 5min
- 过期锁惰性清理：acquire / query 时将过期锁设 released_at = now
- 5 分钟无 heartbeat 自动视为过期
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_editing_lock_models import WorkpaperEditingLock

# 锁过期阈值：5 分钟
LOCK_EXPIRY_SECONDS = 300


def _now_naive() -> datetime:
    """返回 UTC naive datetime（DB 存 TIMESTAMP WITHOUT TIME ZONE）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _expiry_threshold() -> datetime:
    """返回过期判定阈值时间点"""
    return _now_naive() - timedelta(seconds=LOCK_EXPIRY_SECONDS)


async def _expire_stale_locks(db: AsyncSession, wp_id: uuid.UUID) -> None:
    """惰性清理：将该底稿所有过期锁标记为已释放"""
    threshold = _expiry_threshold()
    stmt = (
        update(WorkpaperEditingLock)
        .where(
            WorkpaperEditingLock.wp_id == wp_id,
            WorkpaperEditingLock.released_at.is_(None),
            WorkpaperEditingLock.heartbeat_at < threshold,
        )
        .values(released_at=_now_naive())
    )
    await db.execute(stmt)


async def acquire_lock(
    db: AsyncSession,
    wp_id: uuid.UUID,
    staff_id: uuid.UUID,
) -> dict:
    """尝试获取编辑锁

    Returns:
        成功: {"acquired": True, "lock_id": UUID}
        失败（已有活跃锁）: {"acquired": False, "locked_by": UUID, "acquired_at": datetime}
    """
    # 1. 惰性清理过期锁
    await _expire_stale_locks(db, wp_id)

    # 2. 查询是否有活跃锁
    threshold = _expiry_threshold()
    stmt = select(WorkpaperEditingLock).where(
        WorkpaperEditingLock.wp_id == wp_id,
        WorkpaperEditingLock.released_at.is_(None),
        WorkpaperEditingLock.heartbeat_at >= threshold,
    )
    result = await db.execute(stmt)
    active_lock = result.scalar_one_or_none()

    if active_lock is not None:
        # 如果是同一个人重新 acquire，直接续期
        if active_lock.staff_id == staff_id:
            active_lock.heartbeat_at = _now_naive()
            await db.flush()
            return {"acquired": True, "lock_id": str(active_lock.id)}
        # 其他人持有锁
        return {
            "acquired": False,
            "locked_by": str(active_lock.staff_id),
            "acquired_at": active_lock.acquired_at.isoformat(),
        }

    # 3. 无活跃锁，创建新锁
    now = _now_naive()
    new_lock = WorkpaperEditingLock(
        id=uuid.uuid4(),
        wp_id=wp_id,
        staff_id=staff_id,
        acquired_at=now,
        heartbeat_at=now,
    )
    db.add(new_lock)
    await db.flush()
    return {"acquired": True, "lock_id": str(new_lock.id)}


async def heartbeat_lock(
    db: AsyncSession,
    wp_id: uuid.UUID,
    staff_id: uuid.UUID,
) -> dict:
    """续期 heartbeat

    Returns:
        成功: {"ok": True}
        失败（无活跃锁）: {"ok": False, "reason": "no_active_lock"}
    """
    threshold = _expiry_threshold()
    stmt = select(WorkpaperEditingLock).where(
        WorkpaperEditingLock.wp_id == wp_id,
        WorkpaperEditingLock.staff_id == staff_id,
        WorkpaperEditingLock.released_at.is_(None),
        WorkpaperEditingLock.heartbeat_at >= threshold,
    )
    result = await db.execute(stmt)
    lock = result.scalar_one_or_none()

    if lock is None:
        return {"ok": False, "reason": "no_active_lock"}

    lock.heartbeat_at = _now_naive()
    await db.flush()
    return {"ok": True}


async def release_lock(
    db: AsyncSession,
    wp_id: uuid.UUID,
    staff_id: uuid.UUID,
) -> dict:
    """释放编辑锁

    Returns:
        成功: {"released": True}
        失败（无活跃锁）: {"released": False, "reason": "no_active_lock"}
    """
    stmt = select(WorkpaperEditingLock).where(
        WorkpaperEditingLock.wp_id == wp_id,
        WorkpaperEditingLock.staff_id == staff_id,
        WorkpaperEditingLock.released_at.is_(None),
    )
    result = await db.execute(stmt)
    lock = result.scalar_one_or_none()

    if lock is None:
        return {"released": False, "reason": "no_active_lock"}

    lock.released_at = _now_naive()
    await db.flush()
    return {"released": True}


async def force_acquire_lock(
    db: AsyncSession,
    wp_id: uuid.UUID,
    staff_id: uuid.UUID,
) -> dict:
    """强制获取锁（覆盖现有锁）

    释放当前活跃锁并创建新锁。用于"强制编辑"场景。

    Returns:
        {"acquired": True, "lock_id": UUID, "previous_holder": UUID | None}
    """
    # 1. 惰性清理过期锁
    await _expire_stale_locks(db, wp_id)

    # 2. 释放当前活跃锁
    previous_holder = None
    stmt = select(WorkpaperEditingLock).where(
        WorkpaperEditingLock.wp_id == wp_id,
        WorkpaperEditingLock.released_at.is_(None),
    )
    result = await db.execute(stmt)
    active_lock = result.scalar_one_or_none()

    if active_lock is not None:
        previous_holder = str(active_lock.staff_id)
        active_lock.released_at = _now_naive()
        await db.flush()

    # 3. 创建新锁
    now = _now_naive()
    new_lock = WorkpaperEditingLock(
        id=uuid.uuid4(),
        wp_id=wp_id,
        staff_id=staff_id,
        acquired_at=now,
        heartbeat_at=now,
    )
    db.add(new_lock)
    await db.flush()

    return {
        "acquired": True,
        "lock_id": str(new_lock.id),
        "previous_holder": previous_holder,
    }


async def get_active_locks(db: AsyncSession) -> list[dict]:
    """获取所有活跃锁列表（管理员监控用）

    返回包含 staff_name / wp_code / wp_name 的丰富信息，
    前端无需额外 N+1 请求解析 UUID。
    """
    from app.models.core import User
    from app.models.workpaper_models import WorkingPaper, WpIndex

    threshold = _expiry_threshold()
    stmt = (
        select(
            WorkpaperEditingLock,
            User.username.label("staff_name"),
            WpIndex.wp_code.label("wp_code"),
            WpIndex.wp_name.label("wp_name"),
        )
        .outerjoin(User, WorkpaperEditingLock.staff_id == User.id)
        .outerjoin(WorkingPaper, WorkpaperEditingLock.wp_id == WorkingPaper.id)
        .outerjoin(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkpaperEditingLock.released_at.is_(None),
            WorkpaperEditingLock.heartbeat_at >= threshold,
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "id": str(row.WorkpaperEditingLock.id),
            "wp_id": str(row.WorkpaperEditingLock.wp_id),
            "staff_id": str(row.WorkpaperEditingLock.staff_id),
            "staff_name": row.staff_name or "未知用户",
            "wp_code": row.wp_code or "—",
            "wp_name": row.wp_name or "未知底稿",
            "acquired_at": row.WorkpaperEditingLock.acquired_at.isoformat(),
            "heartbeat_at": row.WorkpaperEditingLock.heartbeat_at.isoformat(),
        }
        for row in rows
    ]
