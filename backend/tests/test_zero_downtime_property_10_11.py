# Feature: zero-downtime-deployment, Property 10, Property 11
"""Property 10：readyz 状态机正确反映可接流量。
Property 11：livez 在进程存活时恒为就绪。

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 6.3
"""
import httpx
import pytest
from hypothesis import given, settings, HealthCheck, strategies as st
from unittest.mock import patch, AsyncMock

from app.core.runtime_state import migration_state, shutdown_state, _MigrationState, _ShutdownState
from app.main import app


@pytest.fixture(autouse=True)
def reset_runtime_state():
    """Reset singletons between tests."""
    # Save original state
    orig_migration = migration_state._complete
    orig_draining = shutdown_state._draining
    yield
    # Restore
    migration_state._complete = orig_migration
    shutdown_state._draining = orig_draining


# --- Property 10: readyz state machine ---

health_status_st = st.sampled_from(["healthy", "degraded", "unhealthy"])
bool_st = st.booleans()


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(
    migration_complete=bool_st,
    health_status=health_status_st,
    draining=bool_st,
)
@pytest.mark.asyncio
async def test_readyz_state_machine(migration_complete, health_status, draining):
    """readyz 状态机：
    - draining → 503
    - migration incomplete → 503
    - health unhealthy → 503
    - otherwise → 200, with degraded flag
    """
    # Set up state
    migration_state._complete = migration_complete
    shutdown_state._draining = draining

    # Mock health check
    mock_health = {"status": health_status}

    # Clear health cache
    from app.api.probes import _health_cache
    _health_cache["data"] = None
    _health_cache["ts"] = 0.0

    with patch("app.api.probes._get_health_snapshot_cached", new_callable=AsyncMock, return_value=mock_health):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/readyz")

            if draining:
                assert resp.status_code == 503
                assert resp.json()["status"] == "draining"
            elif not migration_complete:
                assert resp.status_code == 503
                assert resp.json()["migration_complete"] is False
            elif health_status == "unhealthy":
                assert resp.status_code == 503
                assert resp.json()["health"] == "unhealthy"
            else:
                assert resp.status_code == 200
                body = resp.json()
                assert body["status"] == "ready"
                assert body["degraded"] == (health_status == "degraded")


# --- Property 11: livez always alive ---

@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(
    migration_complete=bool_st,
    health_status=health_status_st,
    draining=bool_st,
)
@pytest.mark.asyncio
async def test_livez_always_alive(migration_complete, health_status, draining):
    """livez 恒 200，不因 DB/依赖不可达/draining/migration 而非 200。"""
    migration_state._complete = migration_complete
    shutdown_state._draining = draining

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/livez")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"
