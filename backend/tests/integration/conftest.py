"""集成测试 fixtures — 使用真实 PostgreSQL

运行条件：
  - 环境变量 TEST_DATABASE_URL 指向测试数据库
  - 或 Docker 中有 postgres 容器可用

跳过条件：
  - 无 TEST_DATABASE_URL 且无法连接默认 PG → 自动 skip

用法：
  TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/audit_test \
  python -m pytest backend/tests/integration/ -v
"""

import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# 检测是否有可用的 PG
_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_test"
)

_PG_AVAILABLE = None


def _check_pg():
    """同步检测 PG 是否可连接"""
    global _PG_AVAILABLE
    if _PG_AVAILABLE is not None:
        return _PG_AVAILABLE
    try:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine

        async def _ping():
            engine = create_async_engine(_TEST_DB_URL, pool_size=1)
            async with engine.connect() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            await engine.dispose()

        asyncio.run(_ping())
        _PG_AVAILABLE = True
    except Exception:
        _PG_AVAILABLE = False
    return _PG_AVAILABLE


def pytest_collection_modifyitems(config, items):
    """PG 不可用时自动 skip 使用 pg_client fixture 的集成测试"""
    if not _check_pg():
        skip_marker = pytest.mark.skip(reason="PostgreSQL not available (set TEST_DATABASE_URL)")
        for item in items:
            if "integration" in str(item.fspath):
                # 只 skip 使用 pg_client fixture 的测试
                if "pg_client" in getattr(item, "fixturenames", []):
                    item.add_marker(skip_marker)


@pytest_asyncio.fixture
async def pg_client():
    """使用真实 PG 的测试客户端"""
    if not _check_pg():
        pytest.skip("PostgreSQL not available")

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.models.base import Base
    from app.main import app
    from app.core.database import get_db
    from app.core.redis import get_redis

    engine = create_async_engine(_TEST_DB_URL, pool_size=5)

    # 创建所有表（测试数据库）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSession = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_db():
        async with TestSession() as session:
            yield session

    # 使用 fakeredis 避免污染真实 Redis
    import fakeredis.aioredis
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def override_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis] = override_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()

    # 清理测试数据（不 drop 表，只清数据）
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())

    await engine.dispose()
