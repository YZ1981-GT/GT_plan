"""健康检查路由单元测试

Validates: Requirements 4.8, 4.9
"""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.health import router
from app.core.database import get_db
from app.core.redis import get_redis


def _create_app(
    *,
    pg_healthy: bool = True,
    redis_healthy: bool = True,
) -> FastAPI:
    """创建带健康检查路由的测试应用，可控制 PG/Redis 可用性。"""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")

    # Mock DB session
    async def _mock_db():
        session = AsyncMock()
        if pg_healthy:
            session.execute = AsyncMock(return_value=None)
        else:
            session.execute = AsyncMock(side_effect=Exception("pg down"))
        yield session

    # Mock Redis client
    async def _mock_redis():
        client = AsyncMock()
        if redis_healthy:
            client.ping = AsyncMock(return_value=True)
        else:
            client.ping = AsyncMock(side_effect=Exception("redis down"))
        yield client

    test_app.dependency_overrides[get_db] = _mock_db
    test_app.dependency_overrides[get_redis] = _mock_redis

    return test_app


@pytest.mark.asyncio
async def test_all_healthy():
    """PG 和 Redis 均可用 → 200 + healthy。"""
    app = _create_app(pg_healthy=True, redis_healthy=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["services"]["postgres"] == "ok"
    assert body["services"]["redis"] == "ok"


@pytest.mark.asyncio
async def test_pg_down():
    """PG 不可用 → 503 + postgres unavailable。"""
    app = _create_app(pg_healthy=False, redis_healthy=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unhealthy"
    assert body["services"]["postgres"] == "unavailable"
    assert body["services"]["redis"] == "ok"


@pytest.mark.asyncio
async def test_redis_down():
    """Redis 不可用 → 503 + redis unavailable。"""
    app = _create_app(pg_healthy=True, redis_healthy=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unhealthy"
    assert body["services"]["postgres"] == "ok"
    assert body["services"]["redis"] == "unavailable"


@pytest.mark.asyncio
async def test_both_down():
    """PG 和 Redis 均不可用 → 503 + 两者均 unavailable。"""
    app = _create_app(pg_healthy=False, redis_healthy=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unhealthy"
    assert body["services"]["postgres"] == "unavailable"
    assert body["services"]["redis"] == "unavailable"
