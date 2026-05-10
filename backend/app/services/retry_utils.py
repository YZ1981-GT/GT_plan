"""事务重试装饰器 — Sprint 10 Task 10.37 (F29).

在高并发场景下，PostgreSQL 的 REPEATABLE READ 隔离级别可能抛
``SerializationFailure`` (SQLSTATE 40001)；此时需要重试整个事务。

用法：

    @retry_on_serialization_failure(max_retries=3, initial_delay_ms=50)
    async def critical_op(db, ...):
        ...

仅针对 PG；SQLite 下 serialization failure 概率为零，装饰器无副作用
（普通异常直接冒泡）。
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

# PG SerializationFailure SQLSTATE
_SERIALIZATION_FAILURE_CODE = "40001"
# PG DeadlockDetected SQLSTATE（同样需要重试）
_DEADLOCK_DETECTED_CODE = "40P01"

T = TypeVar("T")


def _is_serialization_failure(exc: BaseException) -> bool:
    """检查异常是否为 PG 串行化失败 / 死锁（需重试）。"""
    # sqlalchemy.exc.DBAPIError / OperationalError 都有 .orig
    orig = getattr(exc, "orig", None) or exc
    sqlstate = (
        getattr(orig, "sqlstate", None)
        or getattr(orig, "pgcode", None)
        or getattr(orig, "code", None)
    )
    if sqlstate in (_SERIALIZATION_FAILURE_CODE, _DEADLOCK_DETECTED_CODE):
        return True
    # asyncpg 直接抛 SerializationError 类
    cls_name = type(orig).__name__
    return cls_name in (
        "SerializationError",
        "SerializationFailureError",
        "DeadlockDetectedError",
    )


def retry_on_serialization_failure(
    max_retries: int = 3,
    initial_delay_ms: int = 50,
    max_delay_ms: int = 1000,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """装饰异步事务函数，在 PG 串行化失败 / 死锁时指数退避重试。

    Args:
        max_retries: 最大重试次数（不含首次执行）
        initial_delay_ms: 首次退避毫秒数
        max_delay_ms: 单次退避上限
    """

    def decorator(
        func: Callable[..., Awaitable[T]],
    ) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay_ms / 1000.0
            last_exc: BaseException | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - 精确识别后只重试特定异常
                    if not _is_serialization_failure(exc):
                        raise
                    last_exc = exc
                    if attempt >= max_retries:
                        logger.warning(
                            "[%s] serialization failure after %d retries: %s",
                            func.__qualname__,
                            attempt,
                            exc,
                        )
                        raise
                    # 指数退避 + 抖动，避免惊群
                    jitter = random.uniform(0.5, 1.5)
                    await asyncio.sleep(min(delay * jitter, max_delay_ms / 1000.0))
                    delay = min(delay * 2, max_delay_ms / 1000.0)
                    logger.info(
                        "[%s] serialization failure on attempt %d, retrying",
                        func.__qualname__,
                        attempt + 1,
                    )
            # 不可达（上面 raise 或 return）
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator


__all__ = ["retry_on_serialization_failure"]
