"""Tests for LLM metrics service and endpoint.

Requirements: 非功能需求-可观测性 (Task 2.4)
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.llm_metrics import LLMMetricsCollector, llm_metrics


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests for LLMMetricsCollector
# ═══════════════════════════════════════════════════════════════════════════════


class TestLLMMetricsCollector:
    """LLMMetricsCollector 单元测试"""

    def setup_method(self):
        self.collector = LLMMetricsCollector()

    def test_initial_state(self):
        """初始状态应为空"""
        metrics = self.collector.get_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["success_count"] == 0
        assert metrics["failure_count"] == 0
        assert metrics["avg_duration_ms"] == 0.0
        assert metrics["total_tokens"] == 0
        assert metrics["recent_calls"] == []

    def test_record_successful_call(self):
        """记录成功调用"""
        self.collector.record_call(
            duration_ms=150.5,
            tokens_used=200,
            success=True,
            model="Qwen3.5-27B",
        )
        metrics = self.collector.get_metrics()
        assert metrics["total_calls"] == 1
        assert metrics["success_count"] == 1
        assert metrics["failure_count"] == 0
        assert metrics["avg_duration_ms"] == 150.5
        assert metrics["total_tokens"] == 200
        assert len(metrics["recent_calls"]) == 1
        assert metrics["recent_calls"][0]["success"] is True
        assert metrics["recent_calls"][0]["model"] == "Qwen3.5-27B"
        assert metrics["recent_calls"][0]["error"] is None

    def test_record_failed_call(self):
        """记录失败调用"""
        self.collector.record_call(
            duration_ms=30000.0,
            tokens_used=0,
            success=False,
            model="Qwen3.5-27B",
            error="LLM call timeout after 30s",
        )
        metrics = self.collector.get_metrics()
        assert metrics["total_calls"] == 1
        assert metrics["success_count"] == 0
        assert metrics["failure_count"] == 1
        assert metrics["total_tokens"] == 0
        assert metrics["recent_calls"][0]["success"] is False
        assert metrics["recent_calls"][0]["error"] == "LLM call timeout after 30s"

    def test_multiple_calls_aggregation(self):
        """多次调用聚合统计"""
        self.collector.record_call(duration_ms=100, tokens_used=150, success=True, model="m1")
        self.collector.record_call(duration_ms=200, tokens_used=250, success=True, model="m1")
        self.collector.record_call(duration_ms=300, tokens_used=0, success=False, model="m1", error="timeout")

        metrics = self.collector.get_metrics()
        assert metrics["total_calls"] == 3
        assert metrics["success_count"] == 2
        assert metrics["failure_count"] == 1
        assert metrics["avg_duration_ms"] == 200.0  # (100+200+300)/3
        assert metrics["total_tokens"] == 400  # 150+250+0

    def test_recent_calls_max_100(self):
        """recent_calls 最多保留 100 条"""
        for i in range(120):
            self.collector.record_call(
                duration_ms=float(i),
                tokens_used=i,
                success=True,
                model="test",
            )
        metrics = self.collector.get_metrics()
        assert len(metrics["recent_calls"]) == 100
        # 最新的在前（reversed order）
        assert metrics["recent_calls"][0]["duration_ms"] == 119.0
        # 总计数仍然是 120
        assert metrics["total_calls"] == 120

    def test_recent_calls_newest_first(self):
        """recent_calls 按时间倒序（最新在前）"""
        self.collector.record_call(duration_ms=10, tokens_used=10, success=True, model="first")
        time.sleep(0.01)
        self.collector.record_call(duration_ms=20, tokens_used=20, success=True, model="second")

        metrics = self.collector.get_metrics()
        assert metrics["recent_calls"][0]["model"] == "second"
        assert metrics["recent_calls"][1]["model"] == "first"

    def test_reset(self):
        """reset 清空所有指标"""
        self.collector.record_call(duration_ms=100, tokens_used=50, success=True, model="m")
        self.collector.reset()
        metrics = self.collector.get_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["recent_calls"] == []

    def test_thread_safety(self):
        """并发写入不丢数据"""
        import threading

        def record_batch(start: int):
            for i in range(50):
                self.collector.record_call(
                    duration_ms=float(start + i),
                    tokens_used=1,
                    success=True,
                    model="test",
                )

        threads = [threading.Thread(target=record_batch, args=(i * 50,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        metrics = self.collector.get_metrics()
        assert metrics["total_calls"] == 200
        assert metrics["total_tokens"] == 200


# ═══════════════════════════════════════════════════════════════════════════════
# API endpoint tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_admin_user():
    """Mock admin user"""
    from unittest.mock import MagicMock
    user = MagicMock()
    user.id = "admin-uuid"
    user.role = MagicMock()
    user.role.value = "admin"
    user.username = "admin"
    return user


@pytest.fixture
def mock_auditor_user():
    """Mock auditor user (non-admin)"""
    from unittest.mock import MagicMock
    user = MagicMock()
    user.id = "auditor-uuid"
    user.role = MagicMock()
    user.role.value = "auditor"
    user.username = "auditor"
    return user


@pytest.fixture
def reset_llm_metrics():
    """Reset global llm_metrics before/after test"""
    llm_metrics.reset()
    yield
    llm_metrics.reset()


@pytest.mark.asyncio
async def test_llm_metrics_endpoint_admin(mock_admin_user, reset_llm_metrics):
    """Admin 用户可以访问 LLM 指标端点"""
    from app.main import app
    from app.deps import get_current_user

    # 预填一些数据
    llm_metrics.record_call(duration_ms=100, tokens_used=50, success=True, model="Qwen3.5-27B")
    llm_metrics.record_call(duration_ms=200, tokens_used=0, success=False, model="Qwen3.5-27B", error="timeout")

    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/admin/llm-metrics")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Handle possible wrapper: some endpoints wrap in {"data": ...}
        if "data" in data and "total_calls" not in data:
            data = data["data"]
        assert data["total_calls"] == 2
        assert data["success_count"] == 1
        assert data["failure_count"] == 1
        assert data["avg_duration_ms"] == 150.0
        assert data["total_tokens"] == 50
        assert len(data["recent_calls"]) == 2
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_llm_metrics_endpoint_non_admin_forbidden(mock_auditor_user, reset_llm_metrics):
    """非 admin 用户访问 LLM 指标端点返回 403"""
    from app.main import app
    from app.deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: mock_auditor_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/admin/llm-metrics")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_llm_metrics_endpoint_empty(mock_admin_user, reset_llm_metrics):
    """无调用记录时返回空指标"""
    from app.main import app
    from app.deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/admin/llm-metrics")
        assert resp.status_code == 200
        data = resp.json()
        if "data" in data and "total_calls" not in data:
            data = data["data"]
        assert data["total_calls"] == 0
        assert data["recent_calls"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)
