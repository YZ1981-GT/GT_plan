"""审计哈希链 — 链键与锁（batch A 最小实现）

batch B 将在此文件添加 read_head / append_entry。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


def chain_key_of(project_id: str | None) -> str:
    """返回链键：按项目隔离或全局链。"""
    return f"project:{project_id}" if project_id else "__global__"


async def lock_chain(db: AsyncSession, key: str) -> None:
    """PG 事务级咨询锁；SQLite 无操作。"""
    dialect = db.bind.dialect.name if db.bind else ""
    if dialect == "postgresql":
        from sqlalchemy import text
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended('audit_chain:' || :key, 0))"),
            {"key": key},
        )
