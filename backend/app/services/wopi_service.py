"""WOPI Host 服务 — 文件元信息查询、读取、写入、锁管理、访问令牌

MVP实现：
- check_file_info: 从 working_paper 表获取元数据
- get_file / put_file: stub（返回占位数据/递增版本号）
- lock/unlock/refresh_lock: 内存字典模拟 Redis 锁
- generate_access_token / validate_access_token: 复用 JWT 模块

Validates: Requirements 3.1, 3.2, 3.3, 3.7
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.config import settings
from app.models.workpaper_models import WorkingPaper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory lock store (MVP替代Redis)
# ---------------------------------------------------------------------------

_locks: dict[str, dict[str, Any]] = {}
_LOCK_TTL_SECONDS = 30 * 60  # 30 minutes


class WOPIHostService:
    """WOPI Host 服务

    Validates: Requirements 3.1, 3.2, 3.3, 3.7
    """

    # ------------------------------------------------------------------
    # 9.1  check_file_info / get_file / put_file
    # ------------------------------------------------------------------

    async def check_file_info(
        self,
        db: AsyncSession,
        file_id: UUID,
        user_id: UUID | None = None,
    ) -> dict:
        """WOPI CheckFileInfo: 返回文件元数据。

        Validates: Requirements 3.1
        """
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == file_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise FileNotFoundError(f"底稿不存在: {file_id}")

        return {
            "BaseFileName": wp.file_path.split("/")[-1] if wp.file_path else str(file_id),
            "Size": 0,  # stub — 实际文件大小需读取文件系统
            "OwnerId": str(wp.created_by) if wp.created_by else "",
            "Version": str(wp.file_version),
            "UserCanWrite": True,
            "UserCanNotWriteRelative": True,
            "SupportsLocks": True,
            "UserFriendlyName": str(user_id) if user_id else "",
        }

    async def get_file(self, db: AsyncSession, file_id: UUID) -> bytes:
        """WOPI GetFile: 返回文件二进制内容 (stub)。

        Validates: Requirements 3.1
        """
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == file_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise FileNotFoundError(f"底稿不存在: {file_id}")

        # MVP stub: return empty bytes
        return b""

    async def put_file(
        self,
        db: AsyncSession,
        file_id: UUID,
        content: bytes,
        lock_id: str | None = None,
    ) -> dict:
        """WOPI PutFile: 写入文件 + 递增版本号。

        Validates: Requirements 3.7
        """
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == file_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise FileNotFoundError(f"底稿不存在: {file_id}")

        # Check lock if provided
        if lock_id:
            file_key = str(file_id)
            if file_key in _locks:
                lock_info = _locks[file_key]
                if lock_info["lock_id"] != lock_id:
                    raise PermissionError("锁冲突: lock_id 不匹配")

        # Increment version (stub — no actual file write)
        wp.file_version += 1
        wp.updated_at = datetime.now(timezone.utc)
        await db.flush()

        return {
            "version": wp.file_version,
            "message": "文件保存成功",
        }

    # ------------------------------------------------------------------
    # 9.2  Lock management (in-memory dict for MVP)
    # ------------------------------------------------------------------

    def lock(self, file_id: UUID, lock_id: str) -> dict:
        """WOPI Lock: 获取排他锁。

        Validates: Requirements 3.3
        """
        file_key = str(file_id)
        now = time.time()

        if file_key in _locks:
            existing = _locks[file_key]
            # Check if expired
            if existing["expires_at"] > now:
                if existing["lock_id"] != lock_id:
                    return {
                        "success": False,
                        "status": 409,
                        "existing_lock": existing["lock_id"],
                        "message": "文件已被其他用户锁定",
                    }
                # Same lock_id — refresh
                existing["expires_at"] = now + _LOCK_TTL_SECONDS
                return {"success": True, "message": "锁已刷新"}
            # Expired — remove and proceed
            del _locks[file_key]

        _locks[file_key] = {
            "lock_id": lock_id,
            "expires_at": now + _LOCK_TTL_SECONDS,
        }
        return {"success": True, "message": "锁定成功"}

    def unlock(self, file_id: UUID, lock_id: str) -> dict:
        """WOPI Unlock: 释放锁。

        Validates: Requirements 3.3
        """
        file_key = str(file_id)

        if file_key not in _locks:
            return {"success": True, "message": "无锁可释放"}

        existing = _locks[file_key]
        if existing["lock_id"] != lock_id:
            return {
                "success": False,
                "status": 409,
                "existing_lock": existing["lock_id"],
                "message": "lock_id 不匹配",
            }

        del _locks[file_key]
        return {"success": True, "message": "锁已释放"}

    def refresh_lock(self, file_id: UUID, lock_id: str) -> dict:
        """WOPI RefreshLock: 延长锁超时。

        Validates: Requirements 3.3
        """
        file_key = str(file_id)

        if file_key not in _locks:
            return {
                "success": False,
                "status": 409,
                "message": "锁不存在",
            }

        existing = _locks[file_key]
        if existing["lock_id"] != lock_id:
            return {
                "success": False,
                "status": 409,
                "existing_lock": existing["lock_id"],
                "message": "lock_id 不匹配",
            }

        existing["expires_at"] = time.time() + _LOCK_TTL_SECONDS
        return {"success": True, "message": "锁已刷新"}

    # ------------------------------------------------------------------
    # 9.3  Access token (JWT)
    # ------------------------------------------------------------------

    @staticmethod
    def generate_access_token(
        user_id: UUID,
        project_id: UUID,
        file_id: UUID,
        expires_minutes: int = 120,
    ) -> str:
        """生成 WOPI 访问令牌 (JWT)。

        Validates: Requirements 3.2
        """
        expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        payload = {
            "sub": str(user_id),
            "project_id": str(project_id),
            "file_id": str(file_id),
            "exp": expire,
            "type": "wopi",
        }
        return jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

    @staticmethod
    def validate_access_token(token: str) -> dict:
        """校验 WOPI 访问令牌。

        Validates: Requirements 3.2
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            if payload.get("type") != "wopi":
                raise ValueError("非 WOPI 令牌")
            return {
                "user_id": payload["sub"],
                "project_id": payload.get("project_id"),
                "file_id": payload.get("file_id"),
            }
        except JWTError as e:
            raise ValueError(f"令牌无效: {e}")


def clear_locks() -> None:
    """Clear all locks (for testing)."""
    _locks.clear()
