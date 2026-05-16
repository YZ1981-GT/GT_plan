"""Spec C R10 Sprint 1.1.6 — worker 心跳单测

覆盖：
1. write_heartbeat 写入成功（payload 格式正确）
2. Redis 不可用降级（仅日志，不抛异常）
3. TTL 设置正确（60s）
4. payload 含 last_heartbeat / pid / version / hostname 4 字段
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.worker_helpers import write_heartbeat


@pytest.mark.asyncio
async def test_write_heartbeat_success_format():
    """payload 含 4 字段且 ISO8601 时间。"""
    mock_redis = AsyncMock()
    captured = {}

    async def setex_capture(key, ttl, value):
        captured["key"] = key
        captured["ttl"] = ttl
        captured["value"] = value

    mock_redis.setex.side_effect = setex_capture

    with patch("app.core.redis.redis_client", mock_redis):
        await write_heartbeat("test_worker")

    assert captured["key"] == "worker_heartbeat:test_worker"
    assert captured["ttl"] == 60

    payload = json.loads(captured["value"])
    assert "last_heartbeat" in payload
    assert "pid" in payload and isinstance(payload["pid"], int)
    assert "version" in payload
    assert "hostname" in payload
    # 时间能被 ISO8601 解析
    datetime.fromisoformat(payload["last_heartbeat"])


@pytest.mark.asyncio
async def test_write_heartbeat_redis_unavailable_degrades_silently():
    """redis_client is None → 静默返回不抛异常。"""
    with patch("app.core.redis.redis_client", None):
        # 不应抛异常
        await write_heartbeat("test_worker")


@pytest.mark.asyncio
async def test_write_heartbeat_redis_exception_degrades_silently():
    """Redis setex 抛异常 → 静默降级仅日志。"""
    mock_redis = AsyncMock()
    mock_redis.setex.side_effect = ConnectionError("Redis down")

    with patch("app.core.redis.redis_client", mock_redis):
        # 不应抛异常
        await write_heartbeat("test_worker")


@pytest.mark.asyncio
async def test_write_heartbeat_custom_version():
    """version 参数被正确写入 payload。"""
    mock_redis = AsyncMock()
    captured = {}

    async def setex_capture(key, ttl, value):
        captured["value"] = value

    mock_redis.setex.side_effect = setex_capture

    with patch("app.core.redis.redis_client", mock_redis):
        await write_heartbeat("test_worker", version="2.5.1")

    payload = json.loads(captured["value"])
    assert payload["version"] == "2.5.1"
