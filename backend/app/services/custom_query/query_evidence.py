"""查询运行记录与证据的数据库能力探测。"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_CACHE_TTL_SECONDS = 60.0
# key = 绑定的同步 Engine 身份；避免一个进程内不同数据库共用结果。
_availability_cache: dict[int, tuple[float, bool]] = {}


def _cache_key(db: AsyncSession) -> int:
    """取 session 绑定 engine 的稳定进程内身份。"""
    bind: Any = db.get_bind()
    return id(bind)


async def query_evidence_available(db: AsyncSession) -> bool:
    """判断运行记录与查询证据迁移是否已落库。

    这是 R8.2 的 fail-closed 探测：只在两个表都存在时返回 True，数据库查询
    出错也返回 False。结果按绑定 engine 缓存 60 秒，避免每次查询都查系统目录。
    """
    key = _cache_key(db)
    now = time.monotonic()
    cached = _availability_cache.get(key)
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    dialect = db.get_bind().dialect.name
    try:
        if dialect == "postgresql":
            stmt = text(
                "SELECT to_regclass('public.query_runs') IS NOT NULL "
                "AND to_regclass('public.query_artifacts') IS NOT NULL"
            )
        elif dialect == "sqlite":
            stmt = text(
                "SELECT COUNT(*) = 2 FROM sqlite_master "
                "WHERE type = 'table' AND name IN ('query_runs', 'query_artifacts')"
            )
        else:
            _availability_cache[key] = (now, False)
            return False
        available = bool((await db.execute(stmt)).scalar())
    except Exception:
        available = False

    _availability_cache[key] = (now, available)
    return available


__all__ = ["query_evidence_available"]
