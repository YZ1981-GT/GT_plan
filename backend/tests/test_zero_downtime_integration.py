# Feature: zero-downtime-deployment, Property 20
"""Integration tests for zero-downtime deployment.

Task 15: 零停机不变量集成测试
Task 16: drain 集成 + 版本协商端到端
"""
import asyncio
import json
import os
from unittest.mock import patch

import httpx
import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

from app.core.build_version import get_build_version
from app.core.runtime_state import migration_state, shutdown_state
from app.middleware.inflight import inflight_counter
from app.main import app


@pytest.fixture(autouse=True)
def reset_state():
    """Reset all process-level state between tests."""
    orig_migration = migration_state._complete
    orig_draining = shutdown_state._draining
    orig_inflight = inflight_counter._count
    get_build_version.cache_clear()
    yield
    migration_state._complete = orig_migration
    shutdown_state._draining = orig_draining
    inflight_counter._count = orig_inflight
    get_build_version.cache_clear()


# --- Task 15.1: Rolling period load invariant ---

@pytest.mark.asyncio
async def test_rolling_period_no_5xx():
    """滚动期持续负载零 5xx：模拟新旧共存时并发请求全不返回 5xx。

    Validates: Requirements 5.4, 11.1, 11.3
    """
    # Simulate: migration complete, not draining, healthy
    migration_state._complete = True
    shutdown_state._draining = False

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Send burst of concurrent requests to endpoints that don't depend on external DB/Redis.
        # /api/health and /readyz intentionally return 503 when DB/Redis are unreachable
        # (by design), so we test with endpoints whose contract is to never 5xx
        # when the process is alive and migration complete.
        endpoints = ["/api/version", "/livez", "/readyz"]
        tasks = [client.get(ep) for ep in endpoints * 4]  # 12 concurrent requests
        responses = await asyncio.gather(*tasks)

        # Zero 5xx — readyz returns 200 because migration_state is complete and
        # health cache returns healthy on first call within TTL window
        for resp in responses:
            assert resp.status_code < 500, (
                f"Got {resp.status_code} on {resp.request.url} during simulated rolling period"
            )


# --- Task 15.2: Property 20 — Zero-downtime invariant ---

@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    n_requests=st.integers(min_value=1, max_value=5),
    endpoint_idx=st.integers(min_value=0, max_value=1),
)
@pytest.mark.asyncio
async def test_property20_zero_downtime_invariant(n_requests, endpoint_idx):
    """Property 20: 滚动期任意请求不 5xx。

    新旧共存同一 DB，请求始终成功（200 or 4xx，非 5xx）。
    PBT 内只测不依赖外部连接的端点（/api/version, /livez），避免
    Hypothesis 多 example 间 event loop 生命周期导致 asyncpg 连接池
    flaky（readyz 通过 health cache 查 DB，跨 example 连接池可能
    已关闭）。/readyz 由 test_rolling_period_no_5xx 单独覆盖。

    Validates: Requirements 5.2, 5.3, 5.4, 11.1, 11.3
    """
    migration_state._complete = True
    shutdown_state._draining = False

    endpoints = ["/api/version", "/livez"]
    ep = endpoints[endpoint_idx]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        for _ in range(n_requests):
            resp = await client.get(ep)
            assert resp.status_code < 500, f"5xx on {ep}: {resp.status_code}"


# --- Task 16.1: Drain integration test ---

@pytest.mark.asyncio
async def test_drain_integration_sigterm_readyz_503():
    """SIGTERM → readyz 立即 503 → drain 窗口内 in-flight 完成 → 退出。

    Validates: Requirements 3.4, 3.5, 11.2
    """
    migration_state._complete = True
    shutdown_state._draining = False

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Before SIGTERM: readyz should be 200
        resp = await client.get("/readyz")
        assert resp.status_code == 200

        # Simulate SIGTERM
        shutdown_state.start_draining()

        # After SIGTERM: readyz immediately 503
        resp = await client.get("/readyz")
        assert resp.status_code == 503
        assert resp.json()["status"] == "draining"

        # But livez still 200 (process alive)
        resp = await client.get("/livez")
        assert resp.status_code == 200

        # In-flight requests during drain window should still complete
        resp = await client.get("/api/version")
        assert resp.status_code == 200  # request completes, not rejected


# --- Task 16.2: Version negotiation end-to-end ---

@pytest.mark.asyncio
async def test_version_negotiation_e2e():
    """构建期注入版本 → /api/version 返真实值 → X-App-Version 一致。

    Validates: Requirements 1.1, 1.2, 1.4
    """
    test_version = {
        "semantic_version": "1.2.3",
        "git_commit": "abc1234",
        "build_time": "2026-06-09T12:00:00Z",
    }

    with patch.dict(os.environ, {"BUILD_VERSION_JSON": json.dumps(test_version)}):
        get_build_version.cache_clear()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # /api/version returns real values
            resp = await client.get("/api/version")
            assert resp.status_code == 200
            # Unwrap ResponseWrapper if needed
            body = resp.json()
            if "data" in body and "code" in body:
                body = body["data"]
            assert body["version"] == "1.2.3"
            assert body["git_commit"] == "abc1234"
            assert body["build_time"] == "2026-06-09T12:00:00Z"

            # X-App-Version header matches git_commit
            assert resp.headers.get("X-App-Version") == "abc1234"
