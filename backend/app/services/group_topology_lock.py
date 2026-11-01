"""集团三码拓扑的 PostgreSQL 事务级年度逻辑锁。

同一年度的关系写入必须串行；不同年度可以并行。``None`` 使用独立稳定键，避免旧项目
因年度为空绕过互斥。事务 commit/rollback 自动释放；SQLite 等测试方言 no-op。

spec: batch-project-authorization-and-lock-hardening R4
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

_LOCK_PREFIX = "group_topology:year:"
_NULL_YEAR_KEY = "__none__"


def _lock_keys(years: Iterable[Any]) -> list[str]:
    normalised: set[int | None] = set()
    for raw in years:
        if raw is None or raw == "":
            normalised.add(None)
        else:
            normalised.add(int(raw))
    ordered = sorted(normalised, key=lambda value: (value is not None, value or 0))
    return [f"{_LOCK_PREFIX}{_NULL_YEAR_KEY if value is None else value}" for value in ordered]


async def lock_topology_years(db: AsyncSession, years: Iterable[Any]) -> None:
    """按稳定顺序获取涉及年度的事务级 advisory lock，避免交叉年度死锁。"""
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    for key in _lock_keys(years):
        await db.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": key},
        )


__all__ = ["lock_topology_years"]
