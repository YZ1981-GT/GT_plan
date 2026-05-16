"""附注章节级锁定服务 — 多人协作与锁定机制

支持章节级编辑锁、心跳续期、自动释放、强制解锁、乐观锁版本校验。

Requirements: 44.1-44.6
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 心跳过期阈值（秒）— 5 分钟无操作自动释放
LOCK_EXPIRE_SECONDS = 300


class NoteSectionLockService:
    """附注章节锁定服务"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def acquire_lock(
        self,
        project_id: UUID,
        year: int,
        section_code: str,
        user_id: UUID,
        user_name: str = "",
    ) -> dict[str, Any]:
        """获取章节级编辑锁。

        如果该章节已被其他用户锁定（且未过期），返回 409 冲突。
        同一用户重复获取则续期。
        """
        now = datetime.now(timezone.utc)
        cutoff = datetime.fromtimestamp(
            now.timestamp() - LOCK_EXPIRE_SECONDS, tz=timezone.utc
        )

        # 检查是否已有活跃锁
        result = await self._db.execute(
            text("""
                SELECT id, locked_by, locked_by_name, acquired_at, heartbeat_at
                FROM note_section_locks
                WHERE project_id = :pid AND year = :year
                  AND section_code = :code AND released_at IS NULL
                ORDER BY acquired_at DESC
                LIMIT 1
            """),
            {"pid": str(project_id), "year": year, "code": section_code},
        )
        existing = result.mappings().first()

        if existing:
            heartbeat_at = existing["heartbeat_at"]
            if isinstance(heartbeat_at, str):
                heartbeat_at = datetime.fromisoformat(heartbeat_at)

            if heartbeat_at and heartbeat_at > cutoff:
                # 锁仍有效
                if str(existing["locked_by"]) == str(user_id):
                    # 同一用户续期
                    await self._db.execute(
                        text("""
                            UPDATE note_section_locks
                            SET heartbeat_at = :now
                            WHERE id = :lock_id
                        """),
                        {"now": now, "lock_id": existing["id"]},
                    )
                    return {
                        "lock_id": str(existing["id"]),
                        "locked_by": str(user_id),
                        "locked_by_name": existing["locked_by_name"],
                        "acquired_at": str(existing["acquired_at"]),
                        "heartbeat_at": now.isoformat(),
                        "status": "renewed",
                    }
                else:
                    # 被其他用户锁定
                    return {
                        "error": "LOCK_HELD",
                        "locked_by": str(existing["locked_by"]),
                        "locked_by_name": existing["locked_by_name"],
                        "acquired_at": str(existing["acquired_at"]),
                    }
            else:
                # 锁已过期，释放
                await self._db.execute(
                    text("UPDATE note_section_locks SET released_at = :now WHERE id = :id"),
                    {"now": now, "id": existing["id"]},
                )

        # 创建新锁
        lock_id = uuid4()
        await self._db.execute(
            text("""
                INSERT INTO note_section_locks
                    (id, project_id, year, section_code, locked_by, locked_by_name,
                     acquired_at, heartbeat_at)
                VALUES
                    (:id, :pid, :year, :code, :uid, :uname, :now, :now)
            """),
            {
                "id": str(lock_id),
                "pid": str(project_id),
                "year": year,
                "code": section_code,
                "uid": str(user_id),
                "uname": user_name,
                "now": now,
            },
        )

        logger.info(
            "[SectionLock] Acquired: project=%s section=%s user=%s",
            project_id, section_code, user_id,
        )

        return {
            "lock_id": str(lock_id),
            "locked_by": str(user_id),
            "locked_by_name": user_name,
            "acquired_at": now.isoformat(),
            "heartbeat_at": now.isoformat(),
            "status": "acquired",
        }

    async def release_lock(
        self,
        project_id: UUID,
        year: int,
        section_code: str,
        user_id: UUID,
    ) -> bool:
        """释放章节锁（仅锁持有者可释放）。"""
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            text("""
                UPDATE note_section_locks
                SET released_at = :now
                WHERE project_id = :pid AND year = :year
                  AND section_code = :code AND locked_by = :uid
                  AND released_at IS NULL
            """),
            {
                "now": now,
                "pid": str(project_id),
                "year": year,
                "code": section_code,
                "uid": str(user_id),
            },
        )
        released = result.rowcount > 0
        if released:
            logger.info("[SectionLock] Released: section=%s user=%s", section_code, user_id)
        return released

    async def force_release(
        self,
        project_id: UUID,
        year: int,
        section_code: str,
        admin_user_id: UUID,
    ) -> bool:
        """项目经理/管理员强制解锁。"""
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            text("""
                UPDATE note_section_locks
                SET released_at = :now
                WHERE project_id = :pid AND year = :year
                  AND section_code = :code AND released_at IS NULL
            """),
            {
                "now": now,
                "pid": str(project_id),
                "year": year,
                "code": section_code,
            },
        )
        released = result.rowcount > 0
        if released:
            logger.info(
                "[SectionLock] Force released: section=%s by admin=%s",
                section_code, admin_user_id,
            )
        return released

    async def heartbeat(
        self,
        project_id: UUID,
        year: int,
        section_code: str,
        user_id: UUID,
    ) -> bool:
        """心跳续期。"""
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            text("""
                UPDATE note_section_locks
                SET heartbeat_at = :now
                WHERE project_id = :pid AND year = :year
                  AND section_code = :code AND locked_by = :uid
                  AND released_at IS NULL
            """),
            {
                "now": now,
                "pid": str(project_id),
                "year": year,
                "code": section_code,
                "uid": str(user_id),
            },
        )
        return result.rowcount > 0

    async def get_active_locks(
        self,
        project_id: UUID,
        year: int,
    ) -> list[dict[str, Any]]:
        """获取项目所有活跃锁。"""
        now = datetime.now(timezone.utc)
        cutoff = datetime.fromtimestamp(
            now.timestamp() - LOCK_EXPIRE_SECONDS, tz=timezone.utc
        )

        result = await self._db.execute(
            text("""
                SELECT section_code, locked_by, locked_by_name, acquired_at, heartbeat_at
                FROM note_section_locks
                WHERE project_id = :pid AND year = :year
                  AND released_at IS NULL AND heartbeat_at > :cutoff
                ORDER BY acquired_at
            """),
            {"pid": str(project_id), "year": year, "cutoff": cutoff},
        )

        return [
            {
                "section_code": r["section_code"],
                "locked_by": str(r["locked_by"]),
                "locked_by_name": r["locked_by_name"],
                "acquired_at": str(r["acquired_at"]),
                "heartbeat_at": str(r["heartbeat_at"]),
            }
            for r in result.mappings().fetchall()
        ]

    async def cleanup_expired(self) -> int:
        """清理过期锁。"""
        now = datetime.now(timezone.utc)
        cutoff = datetime.fromtimestamp(
            now.timestamp() - LOCK_EXPIRE_SECONDS, tz=timezone.utc
        )
        result = await self._db.execute(
            text("""
                UPDATE note_section_locks
                SET released_at = :now
                WHERE released_at IS NULL AND heartbeat_at < :cutoff
            """),
            {"now": now, "cutoff": cutoff},
        )
        count = result.rowcount
        if count > 0:
            logger.info("[SectionLock] Cleaned up %d expired locks", count)
        return count
