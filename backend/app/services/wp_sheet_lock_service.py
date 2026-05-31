"""底稿 sheet 级软锁服务 — 复用 note_section_lock 模式

支持 sheet 级编辑锁、心跳续期、自动释放。
用于 HTML 渲染器多人协作场景，防止同一 sheet 被多人同时编辑。

Requirements: 6.1, 6.4
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 锁超时（秒）— 5 分钟无心跳自动释放
SHEET_LOCK_EXPIRE_SECONDS = 300


class WpSheetLockService:
    """底稿 sheet 级锁定服务"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def acquire_lock(
        self,
        wp_id: UUID,
        sheet_name: str,
        user_id: UUID,
        user_name: str = "",
    ) -> dict[str, Any]:
        """获取 sheet 级编辑锁。

        同一用户重复获取则续期。
        其他用户持有且未过期则返回冲突信息。
        """
        now = datetime.now(timezone.utc)
        cutoff = datetime.fromtimestamp(
            now.timestamp() - SHEET_LOCK_EXPIRE_SECONDS, tz=timezone.utc
        )

        # 检查是否已有活跃锁
        result = await self._db.execute(
            text("""
                SELECT id, locked_by, locked_by_name, acquired_at, heartbeat_at
                FROM wp_sheet_locks
                WHERE wp_id = :wp_id AND sheet_name = :sheet_name
                  AND released_at IS NULL
                ORDER BY acquired_at DESC
                LIMIT 1
            """),
            {"wp_id": str(wp_id), "sheet_name": sheet_name},
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
                            UPDATE wp_sheet_locks
                            SET heartbeat_at = :now
                            WHERE id = :lock_id
                        """),
                        {"now": now, "lock_id": existing["id"]},
                    )
                    return {
                        "acquired": True,
                        "lock_id": str(existing["id"]),
                        "locked_by": str(user_id),
                        "locked_by_name": existing["locked_by_name"],
                        "status": "renewed",
                    }
                else:
                    # 被其他用户锁定
                    return {
                        "acquired": False,
                        "locked_by": str(existing["locked_by"]),
                        "locked_by_name": existing["locked_by_name"],
                        "acquired_at": str(existing["acquired_at"]),
                    }
            else:
                # 锁已过期，释放
                await self._db.execute(
                    text("UPDATE wp_sheet_locks SET released_at = :now WHERE id = :id"),
                    {"now": now, "id": existing["id"]},
                )

        # 创建新锁
        from uuid import uuid4
        lock_id = uuid4()
        await self._db.execute(
            text("""
                INSERT INTO wp_sheet_locks
                    (id, wp_id, sheet_name, locked_by, locked_by_name,
                     acquired_at, heartbeat_at)
                VALUES
                    (:id, :wp_id, :sheet_name, :uid, :uname, :now, :now)
            """),
            {
                "id": str(lock_id),
                "wp_id": str(wp_id),
                "sheet_name": sheet_name,
                "uid": str(user_id),
                "uname": user_name,
                "now": now,
            },
        )

        logger.debug(
            "[SheetLock] Acquired: wp=%s sheet=%s user=%s",
            wp_id, sheet_name, user_id,
        )

        return {
            "acquired": True,
            "lock_id": str(lock_id),
            "locked_by": str(user_id),
            "locked_by_name": user_name,
            "status": "acquired",
        }

    async def release_lock(
        self,
        wp_id: UUID,
        sheet_name: str,
        user_id: UUID,
    ) -> bool:
        """释放 sheet 锁（仅锁持有者可释放）。"""
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            text("""
                UPDATE wp_sheet_locks
                SET released_at = :now
                WHERE wp_id = :wp_id AND sheet_name = :sheet_name
                  AND locked_by = :uid AND released_at IS NULL
            """),
            {
                "now": now,
                "wp_id": str(wp_id),
                "sheet_name": sheet_name,
                "uid": str(user_id),
            },
        )
        released = result.rowcount > 0
        if released:
            logger.debug("[SheetLock] Released: wp=%s sheet=%s", wp_id, sheet_name)
        return released

    async def heartbeat(
        self,
        wp_id: UUID,
        sheet_name: str,
        user_id: UUID,
    ) -> bool:
        """心跳续期。"""
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            text("""
                UPDATE wp_sheet_locks
                SET heartbeat_at = :now
                WHERE wp_id = :wp_id AND sheet_name = :sheet_name
                  AND locked_by = :uid AND released_at IS NULL
            """),
            {
                "now": now,
                "wp_id": str(wp_id),
                "sheet_name": sheet_name,
                "uid": str(user_id),
            },
        )
        return result.rowcount > 0

    async def get_lock_holder(
        self,
        wp_id: UUID,
        sheet_name: str,
    ) -> dict[str, Any] | None:
        """获取当前 sheet 锁持有者信息（未过期的活跃锁）。"""
        now = datetime.now(timezone.utc)
        cutoff = datetime.fromtimestamp(
            now.timestamp() - SHEET_LOCK_EXPIRE_SECONDS, tz=timezone.utc
        )

        result = await self._db.execute(
            text("""
                SELECT locked_by, locked_by_name, acquired_at, heartbeat_at
                FROM wp_sheet_locks
                WHERE wp_id = :wp_id AND sheet_name = :sheet_name
                  AND released_at IS NULL AND heartbeat_at > :cutoff
                ORDER BY acquired_at DESC
                LIMIT 1
            """),
            {"wp_id": str(wp_id), "sheet_name": sheet_name, "cutoff": cutoff},
        )
        row = result.mappings().first()
        if not row:
            return None
        return {
            "locked_by": str(row["locked_by"]),
            "locked_by_name": row["locked_by_name"],
            "acquired_at": str(row["acquired_at"]),
        }

    async def get_wp_active_locks(
        self,
        wp_id: UUID,
    ) -> list[dict[str, Any]]:
        """获取底稿所有活跃 sheet 锁。"""
        now = datetime.now(timezone.utc)
        cutoff = datetime.fromtimestamp(
            now.timestamp() - SHEET_LOCK_EXPIRE_SECONDS, tz=timezone.utc
        )

        result = await self._db.execute(
            text("""
                SELECT sheet_name, locked_by, locked_by_name, acquired_at, heartbeat_at
                FROM wp_sheet_locks
                WHERE wp_id = :wp_id
                  AND released_at IS NULL AND heartbeat_at > :cutoff
                ORDER BY acquired_at
            """),
            {"wp_id": str(wp_id), "cutoff": cutoff},
        )

        return [
            {
                "sheet_name": r["sheet_name"],
                "locked_by": str(r["locked_by"]),
                "locked_by_name": r["locked_by_name"],
                "acquired_at": str(r["acquired_at"]),
            }
            for r in result.mappings().fetchall()
        ]


@asynccontextmanager
async def wp_sheet_lock(
    db: AsyncSession,
    wp_id: UUID,
    sheet_name: str,
    user_id: UUID,
    user_name: str = "",
    *,
    timeout: int = SHEET_LOCK_EXPIRE_SECONDS,
) -> AsyncGenerator[None, None]:
    """Sheet 级锁 context manager（退出时必释放）。

    Raises:
        HTTPException(409): 锁冲突（其他用户持有）
    """
    service = WpSheetLockService(db)
    result = await service.acquire_lock(
        wp_id=wp_id,
        sheet_name=sheet_name,
        user_id=user_id,
        user_name=user_name,
    )

    if not result.get("acquired"):
        holder_name = result.get("locked_by_name", "其他用户")
        raise HTTPException(
            status_code=409,
            detail={
                "error": "SHEET_LOCK_HELD",
                "message": f"{holder_name} 正在编辑此 sheet",
                "locked_by": result.get("locked_by"),
                "locked_by_name": holder_name,
            },
        )

    try:
        yield
    finally:
        try:
            await service.release_lock(
                wp_id=wp_id,
                sheet_name=sheet_name,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning(
                "wp_sheet_lock release failed for %s/%s: %s",
                wp_id, sheet_name, exc,
            )
