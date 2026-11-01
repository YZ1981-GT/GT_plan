"""批量建项 status 锁定读的 PostgreSQL 有界等待。"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")
STATUS_LOCK_TIMEOUT_MS = 1500
STATUS_BUSY_ERROR_CODE = "BATCH_PLAN_STATUS_BUSY"


class BatchPlanStatusBusy(RuntimeError):
    """计划正由 apply 持锁，status 在预算内无法读取终态。"""


def _sqlstate(error: BaseException) -> str | None:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        value = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if value:
            return str(value)
        current = getattr(current, "orig", None) or getattr(current, "__cause__", None)
    return None


async def with_status_lock_timeout(
    db: AsyncSession,
    operation: Callable[[], Awaitable[T]],
    *,
    timeout_ms: int = STATUS_LOCK_TIMEOUT_MS,
) -> T:
    """PG 中最多等待指定时间；超时不做普通读回退，SQLite 直接执行。"""
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return await operation()
    timeout_ms = max(1, min(int(timeout_ms), 30_000))
    savepoint = await db.begin_nested()
    try:
        await db.execute(
            sa.text("SELECT set_config('lock_timeout', :timeout, true)"),
            {"timeout": f"{timeout_ms}ms"},
        )
        result = await operation()
    except DBAPIError as exc:
        await savepoint.rollback()
        if _sqlstate(exc) == "55P03":
            raise BatchPlanStatusBusy("批量建项结果仍在确认") from exc
        raise
    except Exception:
        await savepoint.rollback()
        raise
    else:
        await savepoint.commit()
        return result


__all__ = [
    "BatchPlanStatusBusy",
    "STATUS_BUSY_ERROR_CODE",
    "STATUS_LOCK_TIMEOUT_MS",
    "with_status_lock_timeout",
]
