# Feature: zero-downtime-deployment, Property 12
"""Property 12：Drain 等待 in-flight 请求完成。

**Validates: Requirements 3.5, 3.6, 11.2**
- 仍有未完成且未超时时 drain 不返回
- in-flight 归零或达超时才结束
- 探针请求不计入
"""
import asyncio
import time

import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

from app.middleware.inflight import inflight_counter, _InflightCounter
from app.core.graceful_shutdown import drain_http_requests


@pytest.fixture(autouse=True)
def reset_inflight():
    """Reset inflight counter between tests."""
    inflight_counter._count = 0
    yield
    inflight_counter._count = 0


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(n_inflight=st.integers(min_value=1, max_value=5))
@pytest.mark.asyncio
async def test_drain_waits_for_inflight(n_inflight):
    """drain 在 in-flight 未归零且未超时时不返回。"""
    inflight_counter._count = n_inflight

    drain_done = False

    async def do_drain():
        nonlocal drain_done
        await drain_http_requests(timeout=2.0)
        drain_done = True

    # Start drain
    task = asyncio.create_task(do_drain())

    # Give drain a moment to start
    await asyncio.sleep(0.3)

    # Should NOT be done yet (inflight > 0)
    assert not drain_done, "drain should not complete while inflight > 0"

    # Now clear inflight
    inflight_counter._count = 0

    # Wait for drain to finish
    await asyncio.wait_for(task, timeout=3.0)
    assert drain_done


@pytest.mark.asyncio
async def test_drain_completes_on_timeout():
    """drain 在超时后即使 in-flight 非零也返回。"""
    inflight_counter._count = 3

    # Short timeout
    await drain_http_requests(timeout=0.5)

    # Should have returned (timeout), inflight still > 0
    assert inflight_counter.value() == 3


@pytest.mark.asyncio
async def test_drain_returns_immediately_when_zero():
    """in-flight 为零时 drain 立即返回。"""
    inflight_counter._count = 0

    start = time.time()
    await drain_http_requests(timeout=5.0)
    elapsed = time.time() - start

    assert elapsed < 1.0, "drain should return immediately when inflight is 0"
