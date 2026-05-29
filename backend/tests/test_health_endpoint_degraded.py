"""migration-runner-resilience spec / Sprint 2 / Task 2.6

/api/health endpoint degraded 测试。

覆盖 CI-6：health JSON 含 migration / schema_drift 两字段，任一非空 → status=degraded。
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.health import router
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.schema_drift_detector import DriftItem


def _create_app(
    *,
    pg_healthy: bool = True,
    redis_healthy: bool = True,
) -> FastAPI:
    """创建测试应用 + mock PG/Redis。"""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")

    async def _mock_db():
        session = AsyncMock()
        if pg_healthy:
            session.execute = AsyncMock(return_value=None)
        else:
            session.execute = AsyncMock(side_effect=Exception("pg down"))
        yield session

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clean_state_returns_healthy():
    """无迁移失败 + 无 drift → status=healthy。"""
    app = _create_app()
    with patch("app.api.health._query_migration_status", new=AsyncMock(
        return_value={"applied_count": 26, "failures": []}
    )), patch("app.api.health._query_schema_drift", new=AsyncMock(
        return_value={"count": 0, "items": []}
    )):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["migration"]["applied_count"] == 26
    assert body["migration"]["failures"] == []
    assert body["schema_drift"]["count"] == 0


@pytest.mark.asyncio
async def test_migration_failure_triggers_degraded():
    """有迁移失败 → status=degraded（200 仍可用）。"""
    app = _create_app()
    with patch("app.api.health._query_migration_status", new=AsyncMock(
        return_value={"applied_count": 25, "failures": [
            {"version": "099", "filename": "V099__bad.sql",
             "error_type": "ProgrammingError",
             "error_message": "table does not exist", "attempt_count": 1}
        ]}
    )), patch("app.api.health._query_schema_drift", new=AsyncMock(
        return_value={"count": 0, "items": []}
    )):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert len(body["migration"]["failures"]) == 1
    assert body["migration"]["failures"][0]["version"] == "099"


@pytest.mark.asyncio
async def test_schema_drift_triggers_degraded():
    """有 schema 漂移 → status=degraded。"""
    app = _create_app()
    with patch("app.api.health._query_migration_status", new=AsyncMock(
        return_value={"applied_count": 26, "failures": []}
    )), patch("app.api.health._query_schema_drift", new=AsyncMock(
        return_value={
            "count": 2,
            "items": [
                {"table": "financial_report", "column": "is_stale",
                 "drift_type": "orm_extra", "detail": "ORM 定义但 DB 缺"},
                {"table": "wp_file_status", "column": None,
                 "drift_type": "enum_mismatch", "detail": "缺 3 值"},
            ],
        }
    )):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["schema_drift"]["count"] == 2
    drift_types = {it["drift_type"] for it in body["schema_drift"]["items"]}
    assert "orm_extra" in drift_types
    assert "enum_mismatch" in drift_types


@pytest.mark.asyncio
async def test_pg_unhealthy_overrides_degraded():
    """PG 不可达时返回 unhealthy（503），即使有迁移失败也优先 unhealthy。"""
    app = _create_app(pg_healthy=False)
    with patch("app.api.health._query_migration_status", new=AsyncMock(
        return_value={"applied_count": 0, "failures": [
            {"version": "099", "filename": "V099__bad.sql",
             "error_type": "X", "error_message": "y", "attempt_count": 1}
        ]}
    )), patch("app.api.health._query_schema_drift", new=AsyncMock(
        return_value={"count": 0, "items": []}
    )):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_response_schema_contract_stable():
    """JSON 响应结构契约稳定（前端 DegradedBanner 依赖）。"""
    app = _create_app()
    with patch("app.api.health._query_migration_status", new=AsyncMock(
        return_value={"applied_count": 26, "failures": []}
    )), patch("app.api.health._query_schema_drift", new=AsyncMock(
        return_value={"count": 0, "items": []}
    )):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
    body = resp.json()
    # 必须包含的顶层字段
    for k in ("status", "services", "migration", "schema_drift"):
        assert k in body, f"missing field: {k}"
    # migration 子字段
    assert "applied_count" in body["migration"]
    assert "failures" in body["migration"]
    assert isinstance(body["migration"]["failures"], list)
    # schema_drift 子字段
    assert "count" in body["schema_drift"]
    assert "items" in body["schema_drift"]
    assert isinstance(body["schema_drift"]["items"], list)
