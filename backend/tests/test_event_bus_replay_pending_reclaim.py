# -*- coding: utf-8 -*-
"""Redis PEL 恢复与有界批次（spec runtime-performance-and-reload-hardening-followup R3.3）。

修的两件事：

1. ``xreadgroup(..., ">")`` 只读「还没投递给本组」的条目，**永不** reclaim 已投递未确认的
   PEL 条目 —— 某个 worker 崩掉后它名下的条目就永久滞留（本机真库现量 pending=264）；
   所有进程又共用同一个 consumer 名 ``worker-1``，连「换个 consumer 接手」都做不到。
2. 一次读 100 条、逐条 await handler 全压在 readiness 前（首次完整启动实测 4787 ms）。

判据：先 XAUTOCLAIM 再读新条目、单轮总量有界、consumer 名含进程号、剩余量可见、
后台续跑把积压清空、XAUTOCLAIM 不可用时降级但仍处理新条目。
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest

from app.models.audit_platform_schemas import EventType
from app.services.event_bus import (
    PEL_MIN_IDLE_MS,
    REPLAY_BATCH_SIZE,
    EventBus,
    serialize_payload_for_stream,
    stream_consumer_name,
)
from app.models.audit_platform_schemas import EventPayload


PROJECT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")


def _entry(idx: int) -> tuple[str, dict[str, str]]:
    payload = EventPayload(event_type=EventType.TRIAL_BALANCE_UPDATED, project_id=PROJECT_ID, year=2025)
    return f"{1000 + idx}-0", {"payload_json": serialize_payload_for_stream(payload)}


class FakeRedis:
    """按 PEL / 新条目两个队列回放的假 Redis，记录每次调用的 consumer 与 count。"""

    def __init__(self, pending: int = 0, fresh: int = 0, *, support_autoclaim: bool = True) -> None:
        self.pending = [_entry(i) for i in range(pending)]
        self.fresh = [_entry(1000 + i) for i in range(fresh)]
        self.support_autoclaim = support_autoclaim
        self.acked: list[str] = []
        self.claim_calls: list[dict[str, Any]] = []
        self.read_calls: list[dict[str, Any]] = []

    async def ping(self) -> bool:
        return True

    async def xgroup_create(self, *_args: Any, **_kwargs: Any) -> bool:
        return True

    async def xautoclaim(self, _key: str, _group: str, consumer: str, **kwargs: Any):
        if not self.support_autoclaim:
            raise AttributeError("unknown command 'XAUTOCLAIM'")
        count = int(kwargs.get("count") or 1)
        self.claim_calls.append({"consumer": consumer, "count": count,
                                 "min_idle_time": kwargs.get("min_idle_time")})
        batch, self.pending = self.pending[:count], self.pending[count:]
        return "0-0", batch, []

    async def xreadgroup(self, _group: str, consumer: str, _streams: dict, **kwargs: Any):
        count = int(kwargs.get("count") or 1)
        self.read_calls.append({"consumer": consumer, "count": count, "block": kwargs.get("block")})
        batch, self.fresh = self.fresh[:count], self.fresh[count:]
        return [("audit:events", batch)] if batch else []

    async def xack(self, _key: str, _group: str, msg_id: str) -> int:
        self.acked.append(msg_id)
        return 1

    async def xpending(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"pending": len(self.pending)}


def _bus_with(redis: FakeRedis) -> EventBus:
    bus = EventBus(debounce_ms=0)
    bus._redis_available = True

    async def _get_redis():
        return redis

    bus._get_redis = _get_redis  # type: ignore[assignment]
    return bus


def test_pending_entries_are_claimed_before_new_entries():
    redis = FakeRedis(pending=3, fresh=2)
    bus = _bus_with(redis)
    recovered = asyncio.run(bus.replay_pending_events(batch_size=10))
    report = bus.get_replay_report()
    assert recovered == 5
    assert report["claimed_count"] == 3 and report["read_count"] == 5
    assert report["acked_count"] == 5 and len(redis.acked) == 5
    assert redis.claim_calls and redis.read_calls
    assert redis.claim_calls[0]["count"] == 10
    assert redis.claim_calls[0]["min_idle_time"] == PEL_MIN_IDLE_MS
    # 新条目的预算要扣掉认领掉的数量，单轮总量不超过批次上限
    assert redis.read_calls[0]["count"] == 7
    assert report["pending_remaining"] == 0 and report["exhausted"] is True


def test_single_round_is_bounded_and_leaves_remaining_visible():
    redis = FakeRedis(pending=15)
    bus = _bus_with(redis)
    recovered = asyncio.run(bus.replay_pending_events(batch_size=5))
    report = bus.get_replay_report()
    assert recovered == 5, "单轮不得被积压长度绑定"
    assert redis.read_calls == [], "本轮预算已被认领用光，不再读新条目"
    assert report["pending_remaining"] == 10 and report["exhausted"] is False


def test_default_batch_size_stays_bounded():
    """默认批次必须是小常量 —— 否则启动又会被积压长度绑定（实测曾 4787 ms）。

    判据写死上限、不引用常量自身：只断言 ``== REPLAY_BATCH_SIZE`` 的用例对「把它改成 500」
    完全不敏感（本轮首次变异即以此存活）。
    """
    assert 0 < REPLAY_BATCH_SIZE <= 50


def test_background_drain_clears_backlog_then_stops():
    backlog = REPLAY_BATCH_SIZE * 2 + 3
    redis = FakeRedis(pending=backlog)
    bus = _bus_with(redis)
    total = asyncio.run(bus.drain_pending_events_in_background(pause_s=0))
    assert total == backlog
    assert bus.get_replay_report()["pending_remaining"] == 0
    assert len(redis.claim_calls) == 3, "逐批清空，不是一次读完"


def test_background_drain_stops_on_stop_event():
    redis = FakeRedis(pending=REPLAY_BATCH_SIZE * 5)
    bus = _bus_with(redis)

    async def run() -> int:
        stop = asyncio.Event()
        stop.set()
        return await bus.drain_pending_events_in_background(stop, pause_s=0)

    assert asyncio.run(run()) == 0


def test_consumer_name_is_per_process():
    assert stream_consumer_name() == f"worker-{os.getpid()}"
    assert stream_consumer_name() != "worker-1" or os.getpid() == 1
    redis = FakeRedis(fresh=1)
    bus = _bus_with(redis)
    asyncio.run(bus.replay_pending_events())
    assert redis.read_calls[0]["consumer"] == stream_consumer_name()
    assert bus.get_replay_report()["consumer"] == stream_consumer_name()


def test_autoclaim_unavailable_degrades_but_still_reads_new_entries():
    redis = FakeRedis(pending=2, fresh=2, support_autoclaim=False)
    bus = _bus_with(redis)
    recovered = asyncio.run(bus.replay_pending_events())
    report = bus.get_replay_report()
    assert recovered == 2 and report["claimed_count"] == 0
    assert "xautoclaim" in (report["last_error"] or "")
    assert redis.read_calls[0]["count"] == REPLAY_BATCH_SIZE


def test_replay_never_blocks_on_empty_stream():
    redis = FakeRedis()
    bus = _bus_with(redis)
    assert asyncio.run(asyncio.wait_for(bus.replay_pending_events(), timeout=2.0)) == 0
    assert redis.read_calls[0]["block"] is None


@pytest.mark.asyncio
async def test_handlers_run_for_claimed_entries():
    seen: list[EventType] = []

    async def handler(payload: EventPayload) -> None:
        seen.append(payload.event_type)

    redis = FakeRedis(pending=2)
    bus = _bus_with(redis)
    bus.subscribe(EventType.TRIAL_BALANCE_UPDATED, handler)
    await bus.replay_pending_events()
    assert seen == [EventType.TRIAL_BALANCE_UPDATED] * 2


def test_health_marks_replay_unavailable_without_redis(monkeypatch):
    """R3.4：Redis 不可用时 live 仍降级可用，但补拉不可用必须显式说出来。"""
    from app.api import health
    import app.services.event_bus as eb

    class _Bus:
        def __init__(self, report: dict) -> None:
            self._report = report

        def get_replay_report(self) -> dict:
            return dict(self._report)

    monkeypatch.setattr(eb, "event_bus", _Bus({
        "redis_available": False, "pending_remaining": None,
        "checked_at": "2026-10-29T00:00:00+00:00", "last_error": "redis down",
    }))
    down = health._events_replay_info()
    assert down["replay_available"] is False and down["last_error"] == "redis down"

    monkeypatch.setattr(eb, "event_bus", _Bus({
        "redis_available": True, "pending_remaining": 7,
        "checked_at": "2026-10-29T00:00:01+00:00", "last_error": None,
    }))
    up = health._events_replay_info()
    assert up["replay_available"] is True and up["pending_remaining"] == 7
