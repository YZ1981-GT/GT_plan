"""spec attachment-evidence-intake：真 PG 事务隔离会话（用例结束整体回滚，不落共享库）。"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings

IS_PG = app_settings.DATABASE_URL.startswith("postgresql")


@pytest_asyncio.fixture
async def pg_session():
    if not IS_PG:
        pytest.skip("need PostgreSQL（统一门的角色 / 委派判定）")
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
    try:
        conn = await engine.connect()
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()
