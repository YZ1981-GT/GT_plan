"""通用编辑锁服务（resource_type + resource_id 维度）

能力域 C — global-refinement-v5-closure

策略：
- 有效锁 = released_at IS NULL AND heartbeat_at > now - 5min
- 过期锁惰性清理：acquire 时将过期锁设 released_at = now
- 5 分钟无 heartbeat 自动视为过期
- 并发保护：SELECT ... FOR UPDATE + 部分唯一索引冲突 SAVEPOINT 捕获

铁律：service 只 flush 不 commit（router 统一 commit）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.editing_lock_models import EditingLock

# 锁过期阈值：5 分钟
LOCK_EXPIRY = timedelta(minutes=5)


def _now() -> datetime:
    """返回 UTC aware datetime"""
    return datetime.now(timezone.utc)


def _expiry_threshold() -> datetime:
    """返回过期判定阈值时间点"""
    return _now() - LOCK_EXPIRY


async def _expire_stale_locks(
    db: AsyncSession, resource_type: str, resource_id: str
) -> None:
    """惰性清理：将该资源所有过期锁标记为已释放"""
    threshold = _expiry_threshold()
    stmt = (
        update(EditingLock)
        .where(
            EditingLock.resource_type == resource_type,
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
            EditingLock.heartbeat_at < threshold,
        )
        .values(released_at=_now())
    )
    await db.execute(stmt)



async def acquire_lock(
    db: AsyncSession,
    resource_type: str,
    resource_id: str,
    holder_id: uuid.UUID,
    holder_name: str,
) -> dict:
    """尝试获取编辑锁

    流程：惰性清理过期锁 → SELECT FOR UPDATE 行锁 → 查活跃锁 → 无则创建
    并发保护：部分唯一索引冲突时用 SAVEPOINT 捕获 IntegrityError 转为锁冲突响应

    Returns:
        无活跃锁（获取成功）: {"locked": False, "lock_id": str, "acquired_at": str}
        有活跃锁（获取失败）: {"locked": True, "locked_by": str, "locked_by_name": str, "acquired_at": str}
    """
    # 1. 惰性清理过期锁
    await _expire_stale_locks(db, resource_type, resource_id)

    # 2. SELECT FOR UPDATE 尝试行锁（PG 生效，SQLite 忽略）
    try:
        stmt = (
            select(EditingLock)
            .where(
                EditingLock.resource_type == resource_type,
                EditingLock.resource_id == resource_id,
                EditingLock.released_at.is_(None),
            )
            .with_for_update()
        )
        result = await db.execute(stmt)
        active_lock = result.scalar_one_or_none()
    except Exception:
        # SQLite 不支持 FOR UPDATE，降级为普通查询
        stmt = select(EditingLock).where(
            EditingLock.resource_type == resource_type,
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await db.execute(stmt)
        active_lock = result.scalar_one_or_none()

    # 3. 有活跃锁 → 判断是否同人续期或他人冲突
    if active_lock is not None:
        # 同人重复 acquire → 刷新 heartbeat 返回成功（对齐 v1 自动续期语义）
        if active_lock.holder_id == holder_id:
            active_lock.heartbeat_at = _now()
            await db.flush()
            return {
                "locked": False,
                "lock_id": str(active_lock.id),
                "acquired_at": active_lock.acquired_at.isoformat()
                if active_lock.acquired_at
                else "",
            }
        # 他人持锁 → 返回冲突信息（router 转 409）
        return {
            "locked": True,
            "locked_by": str(active_lock.holder_id),
            "locked_by_name": active_lock.holder_name or "",
            "acquired_at": active_lock.acquired_at.isoformat()
            if active_lock.acquired_at
            else "",
        }

    # 4. 无活跃锁 → 创建新锁（SAVEPOINT 保护唯一索引冲突）
    now = _now()
    new_lock = EditingLock(
        id=uuid.uuid4(),
        resource_type=resource_type,
        resource_id=resource_id,
        holder_id=holder_id,
        holder_name=(holder_name or None),
        acquired_at=now,
        heartbeat_at=now,
    )

    # 使用 SAVEPOINT（begin_nested）捕获唯一索引冲突
    try:
        nested = await db.begin_nested()
        db.add(new_lock)
        await db.flush()
        await nested.commit()
    except IntegrityError:
        await nested.rollback()
        # 冲突：并发插入，重新查询当前持有人
        stmt = select(EditingLock).where(
            EditingLock.resource_type == resource_type,
            EditingLock.resource_id == resource_id,
            EditingLock.released_at.is_(None),
        )
        result = await db.execute(stmt)
        conflict_lock = result.scalar_one_or_none()
        if conflict_lock is not None:
            return {
                "locked": True,
                "locked_by": str(conflict_lock.holder_id),
                "locked_by_name": conflict_lock.holder_name or "",
                "acquired_at": conflict_lock.acquired_at.isoformat()
                if conflict_lock.acquired_at
                else "",
            }
        # 极端情况：冲突后又释放了，返回通用锁冲突
        return {
            "locked": True,
            "locked_by": "",
            "locked_by_name": "",
            "acquired_at": "",
        }

    return {
        "locked": False,
        "lock_id": str(new_lock.id),
        "acquired_at": now.isoformat(),
    }



async def release_lock(
    db: AsyncSession,
    resource_type: str,
    resource_id: str,
    holder_id: uuid.UUID,
) -> dict:
    """释放编辑锁

    Returns:
        成功: {"released": True}
        失败: {"released": False, "reason": "无活跃锁"}
    """
    stmt = select(EditingLock).where(
        EditingLock.resource_type == resource_type,
        EditingLock.resource_id == resource_id,
        EditingLock.holder_id == holder_id,
        EditingLock.released_at.is_(None),
    )
    result = await db.execute(stmt)
    lock = result.scalar_one_or_none()

    if lock is None:
        return {"released": False, "reason": "无活跃锁"}

    lock.released_at = _now()
    await db.flush()
    return {"released": True}


async def heartbeat_lock(
    db: AsyncSession,
    resource_type: str,
    resource_id: str,
    holder_id: uuid.UUID,
) -> dict:
    """续期 heartbeat

    Returns:
        成功: {"refreshed": True, "heartbeat_at": str}
        失败: {"refreshed": False, "reason": "无活跃锁或非持有人"}
    """
    stmt = select(EditingLock).where(
        EditingLock.resource_type == resource_type,
        EditingLock.resource_id == resource_id,
        EditingLock.holder_id == holder_id,
        EditingLock.released_at.is_(None),
    )
    result = await db.execute(stmt)
    lock = result.scalar_one_or_none()

    if lock is None:
        return {"refreshed": False, "reason": "无活跃锁或非持有人"}

    now = _now()
    lock.heartbeat_at = now
    await db.flush()
    return {"refreshed": True, "heartbeat_at": now.isoformat()}


async def force_acquire_lock(
    db: AsyncSession,
    resource_type: str,
    resource_id: str,
    holder_id: uuid.UUID,
    holder_name: str,
) -> dict:
    """强制获取锁（释放原锁 + 创建新锁）

    Returns:
        {"lock_id": str, "previous_holder_id": str|None, "previous_holder_name": str|None, "acquired_at": str}
    """
    # 1. 惰性清理过期锁
    await _expire_stale_locks(db, resource_type, resource_id)

    # 2. 释放当前活跃锁
    previous_holder_id: str | None = None
    previous_holder_name: str | None = None

    stmt = select(EditingLock).where(
        EditingLock.resource_type == resource_type,
        EditingLock.resource_id == resource_id,
        EditingLock.released_at.is_(None),
    )
    result = await db.execute(stmt)
    active_lock = result.scalar_one_or_none()

    if active_lock is not None:
        previous_holder_id = str(active_lock.holder_id)
        previous_holder_name = active_lock.holder_name
        active_lock.released_at = _now()
        await db.flush()

    # 3. 创建新锁
    now = _now()
    new_lock = EditingLock(
        id=uuid.uuid4(),
        resource_type=resource_type,
        resource_id=resource_id,
        holder_id=holder_id,
        holder_name=(holder_name or None),
        acquired_at=now,
        heartbeat_at=now,
    )
    db.add(new_lock)
    await db.flush()

    return {
        "lock_id": str(new_lock.id),
        "previous_holder_id": previous_holder_id,
        "previous_holder_name": previous_holder_name,
        "acquired_at": now.isoformat(),
    }


async def get_active_locks(
    db: AsyncSession,
    resource_type: str | None = None,
) -> list[dict]:
    """获取活跃锁列表（heartbeat 未过期 + released_at IS NULL）

    Args:
        resource_type: 可选，按资源类型过滤

    Returns:
        活跃锁列表
    """
    threshold = _expiry_threshold()
    conditions = [
        EditingLock.released_at.is_(None),
        EditingLock.heartbeat_at >= threshold,
    ]
    if resource_type is not None:
        conditions.append(EditingLock.resource_type == resource_type)

    stmt = select(EditingLock).where(*conditions)
    result = await db.execute(stmt)
    locks = result.scalars().all()

    return [
        {
            "id": str(lock.id),
            "resource_type": lock.resource_type,
            "resource_id": lock.resource_id,
            "holder_id": str(lock.holder_id),
            "holder_name": lock.holder_name or "",
            "acquired_at": lock.acquired_at.isoformat() if lock.acquired_at else "",
            "heartbeat_at": lock.heartbeat_at.isoformat()
            if lock.heartbeat_at
            else "",
        }
        for lock in locks
    ]
