"""Shared PostgreSQL session fixture for pg_only guidance tests."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _pg_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url or "postgresql" not in url:
        pytest.skip("requires PostgreSQL DATABASE_URL")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


@pytest_asyncio.fixture
async def pg_session() -> AsyncSession:
    """PG 会话，外层事务 + savepoint，teardown 整体回滚 → 对共享 dev DB 零污染。

    测试内的 `await session.commit()` 只提交到 savepoint（不真正落库）；
    fixture teardown 回滚外层事务，撤销测试期间所有写入（projects/notes/备份表行）。
    避免 pg_only 测试把 `guidance-mig-p*` 项目与 `_note_guidance_split_backup`
    行残留在共享 dev DB。
    """
    engine = create_async_engine(_pg_url(), echo=False)
    conn = await engine.connect()
    outer_trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        await session.close()
        if outer_trans.is_active:
            await outer_trans.rollback()
        await conn.close()
        await engine.dispose()

