"""集团三码拓扑的年度事务级逻辑锁。"""
from __future__ import annotations

from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# 两参数 advisory lock 的 namespace；ASCII "GTPL" 对应的稳定正 int4。
GROUP_TOPOLOGY_LOCK_NAMESPACE = 1_196_701_772
# 未设置年度也属于一个明确拓扑域；使用业务年度不可能取到的 int4 最小值。
NULL_AUDIT_YEAR_LOCK_KEY = -2_147_483_648


def _lock_key(year: int | None) -> int:
    return NULL_AUDIT_YEAR_LOCK_KEY if year is None else int(year)


async def lock_topology_years(db: AsyncSession, years: Iterable[int | None]) -> tuple[int, ...]:
    """按锁键升序锁住拓扑写域；PG 以专用键覆盖空年度，SQLite 测试 no-op。"""
    normalized = tuple(sorted({_lock_key(year) for year in years}))
    if not normalized:
        return normalized
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return normalized
    for year in normalized:
        await db.execute(
            sa.text("SELECT pg_advisory_xact_lock(:namespace, :year)"),
            {"namespace": GROUP_TOPOLOGY_LOCK_NAMESPACE, "year": year},
        )
    return normalized


__all__ = [
    "GROUP_TOPOLOGY_LOCK_NAMESPACE",
    "NULL_AUDIT_YEAR_LOCK_KEY",
    "lock_topology_years",
]
