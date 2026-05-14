"""Conflict Guard Service — 调整分录编辑锁 + 乐观锁版本校验

编辑锁获取/释放/心跳续期/过期清理。
乐观锁版本校验（WHERE version = expected）。

使用 adjustment_editing_locks 表（Task 1.1 创建）。

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 心跳过期阈值（秒）
LOCK_EXPIRE_SECONDS = 60


class ConflictGuardService:
    """调整分录冲突守卫服务"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # 编辑锁
    # ------------------------------------------------------------------

    async def acquire_lock(
        self,
        project_id: UUID,
        entry_group_id: UUID,
        user_id: UUID,
        user_name: str,
    ) -> dict[str, Any]:
        """获取编辑锁。

        如果该 entry_group_id 已被其他用户锁定（且未过期），返回 409。

        Returns
        -------
        dict
            锁信息 {id, locked_by, locked_by_name, acquired_at, heartbeat_at}
        """
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - LOCK_EXPIRE_SECONDS

        # 检查是否已有活跃锁（未释放且未过期）
        result = await self._db.execute(
            text("""
                SELECT id, locked_by, locked_by_name, acquired_at, heartbeat_at
                FROM adjustment_editing_locks
                WHERE entry_group_id = :entry_group_id
                  AND released_at IS NULL
                ORDER BY acquired_at DESC
                LIMIT 1
            """),
            {"entry_group_id": str(entry_group_id)},
        )
        existing = result.mappings().first()

        if existing:
            # 检查是否过期
            heartbeat_at = existing["heartbeat_at"]
            if isinstance(heartbeat_at, datetime):
                heartbeat_ts = heartbeat_at.timestamp()
            else:
                heartbeat_ts = heartbeat_at

            if heartbeat_ts > cutoff:
                # 锁仍有效
                if str(existing["locked_by"]) == str(user_id):
                    # 同一用户重复获取，续期
                    await self._db.execute(
                        text("""
                            UPDATE adjustment_editing_locks
                            SET heartbeat_at = :now
                            WHERE id = :lock_id
                        """),
                        {"now": now, "lock_id": existing["id"]},
                    )
                    return {
                        "id": str(existing["id"]),
                        "locked_by": str(existing["locked_by"]),
                        "locked_by_name": existing["locked_by_name"],
                        "acquired_at": str(existing["acquired_at"]),
                        "heartbeat_at": str(now),
                    }
                else:
                    # 被其他用户锁定
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error_code": "LOCK_HELD",
                            "locked_by": str(existing["locked_by"]),
                            "locked_by_name": existing["locked_by_name"],
                            "acquired_at": str(existing["acquired_at"]),
                        },
                    )
            else:
                # 锁已过期，释放它
                await self._db.execute(
                    text("""
                        UPDATE adjustment_editing_locks
                        SET released_at = :now
                        WHERE id = :lock_id
                    """),
                    {"now": now, "lock_id": existing["id"]},
                )

        # 创建新锁
        import uuid as _uuid

        lock_id = _uuid.uuid4()
        await self._db.execute(
            text("""
                INSERT INTO adjustment_editing_locks
                    (id, project_id, entry_group_id, locked_by, locked_by_name, acquired_at, heartbeat_at)
                VALUES
                    (:id, :project_id, :entry_group_id, :locked_by, :locked_by_name, :acquired_at, :heartbeat_at)
            """),
            {
                "id": str(lock_id),
                "project_id": str(project_id),
                "entry_group_id": str(entry_group_id),
                "locked_by": str(user_id),
                "locked_by_name": user_name,
                "acquired_at": now,
                "heartbeat_at": now,
            },
        )

        return {
            "id": str(lock_id),
            "locked_by": str(user_id),
            "locked_by_name": user_name,
            "acquired_at": str(now),
            "heartbeat_at": str(now),
        }

    async def release_lock(
        self,
        project_id: UUID,
        entry_group_id: UUID,
        user_id: UUID,
    ) -> bool:
        """释放编辑锁。

        Returns
        -------
        bool
            是否成功释放
        """
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            text("""
                UPDATE adjustment_editing_locks
                SET released_at = :now
                WHERE entry_group_id = :entry_group_id
                  AND locked_by = :user_id
                  AND released_at IS NULL
            """),
            {
                "now": now,
                "entry_group_id": str(entry_group_id),
                "user_id": str(user_id),
            },
        )
        return result.rowcount > 0

    async def heartbeat_lock(
        self,
        project_id: UUID,
        entry_group_id: UUID,
        user_id: UUID,
    ) -> bool:
        """续期编辑锁心跳。

        Returns
        -------
        bool
            是否成功续期
        """
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            text("""
                UPDATE adjustment_editing_locks
                SET heartbeat_at = :now
                WHERE entry_group_id = :entry_group_id
                  AND locked_by = :user_id
                  AND released_at IS NULL
            """),
            {
                "now": now,
                "entry_group_id": str(entry_group_id),
                "user_id": str(user_id),
            },
        )
        return result.rowcount > 0

    async def cleanup_expired_locks(self) -> int:
        """清理过期锁（heartbeat_at 超过 60s 且未释放）。

        Returns
        -------
        int
            清理的过期锁数量
        """
        now = datetime.now(timezone.utc)
        # 使用 interval 语法兼容 PG，SQLite 用 datetime 函数
        try:
            result = await self._db.execute(
                text("""
                    UPDATE adjustment_editing_locks
                    SET released_at = :now
                    WHERE released_at IS NULL
                      AND heartbeat_at < :cutoff
                """),
                {
                    "now": now,
                    "cutoff": datetime.fromtimestamp(
                        now.timestamp() - LOCK_EXPIRE_SECONDS, tz=timezone.utc
                    ),
                },
            )
            return result.rowcount
        except Exception as e:
            logger.warning("cleanup_expired_locks failed: %s", e)
            return 0

    # ------------------------------------------------------------------
    # 乐观锁版本校验
    # ------------------------------------------------------------------

    async def check_version(
        self,
        adjustment_id: UUID,
        expected_version: int,
    ) -> None:
        """检查调整分录版本号是否匹配。

        Raises
        ------
        HTTPException(409)
            版本不匹配时抛出
        """
        result = await self._db.execute(
            text("""
                SELECT version FROM adjustments
                WHERE id = :adjustment_id
            """),
            {"adjustment_id": str(adjustment_id)},
        )
        row = result.first()
        if row is None:
            raise HTTPException(status_code=404, detail="Adjustment not found")

        current_version = row[0]
        if current_version != expected_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "VERSION_CONFLICT",
                    "current_version": current_version,
                    "expected_version": expected_version,
                },
            )

    async def increment_version(
        self,
        adjustment_id: UUID,
        expected_version: int,
    ) -> int:
        """递增调整分录版本号（乐观锁 CAS）。

        Returns
        -------
        int
            新版本号

        Raises
        ------
        HTTPException(409)
            版本不匹配时抛出（0 rows affected）
        """
        result = await self._db.execute(
            text("""
                UPDATE adjustments
                SET version = version + 1
                WHERE id = :adjustment_id
                  AND version = :expected_version
            """),
            {
                "adjustment_id": str(adjustment_id),
                "expected_version": expected_version,
            },
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "VERSION_CONFLICT",
                    "message": "Adjustment was modified by another user",
                },
            )
        return expected_version + 1
