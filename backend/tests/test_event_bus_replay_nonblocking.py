"""启动重放不得阻塞（spec platform-perf-hotspots R8）。

`replay_pending_events` 原先 `xreadgroup(..., block=0)`：Redis 的 BLOCK 0 是「无限等」，Stream 里没有新条目时
一直挂着，直到启动任务 `wait_for(5s)` 取消 ⇒ 每次启动（含热重载）白等 5 秒才开始服务（/api/health 的
startup 报告实测 `replay_startup_events` 5050ms），重放报告也从不更新。

- 假 Redis 按真实语义模拟 BLOCK（block=0 永远等、不传立即返回）——确定性；
- 真 Redis 用一次性键（不碰 audit:events，结束删除），钉住 redis-py + 服务端的真实行为。
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import pytest

from app.services import event_bus as event_bus_module
from app.services.event_bus import EventBus


class _BlockSemanticsRedis:
    """空 Stream：block=0 永远挂起（与 Redis 一致），不传 block 立即返回空列表。"""

    def __init__(self) -> None:
        self.read_kwargs: list[dict[str, Any]] = []

    async def ping(self) -> bool:
        return True

    async def xgroup_create(self, *_args: Any, **_kwargs: Any) -> bool:
        return True

    async def xreadgroup(self, *_args: Any, **kwargs: Any):
        self.read_kwargs.append(kwargs)
        if kwargs.get("block") is not None:
            await asyncio.Event().wait()  # BLOCK 0 = 无限等
        return []


@pytest.fixture()
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _BlockSemanticsRedis:
    import app.core.redis as redis_module

    fake = _BlockSemanticsRedis()
    monkeypatch.setattr(redis_module, "redis_client", fake)
    return fake


def test_empty_stream_returns_immediately_and_updates_report(fake_redis: _BlockSemanticsRedis) -> None:
    bus = EventBus()
    t0 = time.perf_counter()
    replayed = asyncio.run(asyncio.wait_for(bus.replay_pending_events(), timeout=2.0))
    assert replayed == 0
    assert time.perf_counter() - t0 < 1.0
    assert fake_redis.read_kwargs and all(k.get("block") is None for k in fake_redis.read_kwargs)
    report = bus.get_replay_report()
    assert report["redis_available"] is True and report["checked_at"] and report["read_count"] == 0


def test_fake_reproduces_the_old_hang(fake_redis: _BlockSemanticsRedis) -> None:
    """守卫自身：同一个假 Redis 下 block=0 的调用确实挂到超时（否则上一例对改回 block=0 不敏感）。"""
    async def old_call() -> None:
        await fake_redis.xreadgroup("g", "c", {"k": ">"}, count=100, block=0)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(asyncio.wait_for(old_call(), timeout=0.3))


def test_real_redis_empty_stream_does_not_block(monkeypatch: pytest.MonkeyPatch) -> None:
    """真 Redis、一次性键。客户端在本用例自己的事件循环里新建：模块级 redis_client 的连接绑在别的
    loop 上时 ping 会失败、replay 按「Redis 不可用」直接返回 0 —— 那样「很快返回」是假绿，故断言 redis_available。"""
    import app.core.redis as redis_module
    from redis.asyncio import from_url

    from app.core.config import settings

    key = f"test:perf-hotspots:events:{uuid.uuid4().hex}"
    monkeypatch.setattr(event_bus_module, "_STREAM_KEY", key)
    monkeypatch.setattr(event_bus_module, "_CONSUMER_GROUP", "test_group")

    async def scenario():
        client = from_url(settings.REDIS_URL, decode_responses=True)
        try:
            try:
                await asyncio.wait_for(client.ping(), timeout=2.0)
            except Exception:  # noqa: BLE001
                return None
            monkeypatch.setattr(redis_module, "redis_client", client)
            bus = EventBus()
            t0 = time.perf_counter()
            empty = await asyncio.wait_for(bus.replay_pending_events(), timeout=3.0)
            elapsed = time.perf_counter() - t0
            report_empty = bus.get_replay_report()
            # 有新条目时照常读到并确认（不带 payload_json 的旧形态条目按「无法解析」确认掉，同样不阻塞）
            await client.xadd(key, {"event_type": "not-a-real-event"})
            await asyncio.wait_for(bus.replay_pending_events(), timeout=3.0)
            return empty, elapsed, report_empty, bus.get_replay_report()
        finally:
            try:
                await client.delete(key)
            finally:
                await client.aclose()

    result = asyncio.run(scenario())
    if result is None:
        pytest.skip("Redis 不可用")
    empty, elapsed, report_empty, report_after = result
    assert report_empty["redis_available"] is True and report_empty["last_error"] is None
    assert empty == 0
    assert elapsed < 1.0, f"空 Stream 重放用了 {elapsed:.2f}s（BLOCK 0 会一直等到超时）"
    assert report_after["read_count"] == 1 and report_after["acked_count"] + report_after["dropped_unparseable_count"] >= 1
