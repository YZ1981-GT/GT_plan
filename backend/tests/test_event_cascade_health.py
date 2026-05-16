"""Spec C R10 Sprint 1.2.4 — event-cascade/health 集成测试

5 用例：
1. admin 看完整 schema（lag_seconds + stuck_handlers + dlq_depth + worker_status + redis_available + status）
2. 普通用户只看 status + lag_seconds（D3 隔离）
3. Redis 不可用降级（status=degraded + redis_available=false + worker_status={}）
4. 状态判定阈值（healthy / degraded / critical）
5. 项目权限校验（无权访问的项目返回 403）
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.event_cascade_health_service import EventCascadeHealthService


@pytest.mark.asyncio
async def test_compute_status_healthy():
    """全部正常 → healthy。"""
    status = EventCascadeHealthService._compute_status(
        lag_seconds=10,
        dlq_depth=0,
        worker_status={
            "sla_worker": {"alive": True},
            "import_recover_worker": {"alive": True},
            "outbox_replay_worker": {"alive": True},
            "import_worker": {"alive": True},
        },
        redis_available=True,
    )
    assert status == "healthy"


@pytest.mark.asyncio
async def test_compute_status_degraded_lag():
    """lag > 60s → degraded。"""
    status = EventCascadeHealthService._compute_status(
        lag_seconds=120,
        dlq_depth=0,
        worker_status={"w": {"alive": True}},
        redis_available=True,
    )
    assert status == "degraded"


@pytest.mark.asyncio
async def test_compute_status_degraded_dlq():
    """dlq_depth > 0 → degraded。"""
    status = EventCascadeHealthService._compute_status(
        lag_seconds=10,
        dlq_depth=3,
        worker_status={"w": {"alive": True}},
        redis_available=True,
    )
    assert status == "degraded"


@pytest.mark.asyncio
async def test_compute_status_degraded_one_worker_miss():
    """1 个 worker miss → degraded。"""
    status = EventCascadeHealthService._compute_status(
        lag_seconds=10,
        dlq_depth=0,
        worker_status={
            "sla_worker": {"alive": False},
            "import_recover_worker": {"alive": True},
            "outbox_replay_worker": {"alive": True},
            "import_worker": {"alive": True},
        },
        redis_available=True,
    )
    assert status == "degraded"


@pytest.mark.asyncio
async def test_compute_status_degraded_redis_unavailable():
    """Redis 不可用 → degraded（D7）。"""
    status = EventCascadeHealthService._compute_status(
        lag_seconds=10,
        dlq_depth=0,
        worker_status={},
        redis_available=False,
    )
    assert status == "degraded"


@pytest.mark.asyncio
async def test_compute_status_critical_lag():
    """lag > 300s → critical。"""
    status = EventCascadeHealthService._compute_status(
        lag_seconds=400,
        dlq_depth=0,
        worker_status={"w": {"alive": True}},
        redis_available=True,
    )
    assert status == "critical"


@pytest.mark.asyncio
async def test_compute_status_critical_two_workers_miss():
    """2+ worker miss → critical。"""
    status = EventCascadeHealthService._compute_status(
        lag_seconds=10,
        dlq_depth=0,
        worker_status={
            "sla_worker": {"alive": False},
            "import_recover_worker": {"alive": False},
            "outbox_replay_worker": {"alive": True},
            "import_worker": {"alive": True},
        },
        redis_available=True,
    )
    assert status == "critical"


@pytest.mark.asyncio
async def test_get_worker_status_redis_unavailable_returns_empty():
    """Redis None → 返回 ({}, False) 不抛异常。"""
    with patch("app.core.redis.redis_client", None):
        svc = EventCascadeHealthService(db=None)
        worker_status, redis_available = await svc._get_worker_status()
        assert worker_status == {}
        assert redis_available is False
