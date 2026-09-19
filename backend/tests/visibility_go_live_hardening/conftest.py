# Feature: visibility-isolation-go-live-hardening — shared test fixtures
"""事务隔离 PG session fixture（用例结束回滚，不污染 dev 库）。

复用父 spec 同款语义：真实 PostgreSQL（audit_platform），单连接单事务，用例结束整体回滚。
本 spec 的 Task 5 缓存一致性用例（撤权收敛）需要一个可回滚的真实 session。
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings

_IS_PG = app_settings.DATABASE_URL.startswith("postgresql")


@pytest_asyncio.fixture
async def session():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (visibility go-live capacity acceptance)")
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
    try:
        conn = await engine.connect()
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    trans = await conn.begin()
    s = AsyncSession(bind=conn)
    try:
        yield s
    finally:
        await s.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()
