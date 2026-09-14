# Feature: zero-downtime-deployment, Property 14
"""Property 14: Drain 时 SSE 被优雅关闭而非静默挂起。

**Validates: Requirements 7.1**
"""
import asyncio

import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

from app.core.sse_registry import sse_registry, _SSERegistry, SSEConnection


@pytest.fixture(autouse=True)
def fresh_registry():
    """Reset registry between tests."""
    sse_registry._active.clear()
    sse_registry._counter = 0
    yield
    sse_registry._active.clear()


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(n_connections=st.integers(min_value=0, max_value=10))
@pytest.mark.asyncio
async def test_property14_close_all_closes_all_connections(n_connections):
    """close_all() 后所有连接被关闭，无静默挂起。"""
    # Reset for each hypothesis example
    sse_registry._active.clear()
    sse_registry._counter = 0

    closed_flags: list[int] = []

    for i in range(n_connections):
        async def make_close_cb(idx=i):
            closed_flags.append(idx)

        conn = sse_registry.register(close_callback=make_close_cb)

    assert sse_registry.active_count == n_connections

    await sse_registry.close_all()

    assert sse_registry.active_count == 0
    assert len(closed_flags) == n_connections
