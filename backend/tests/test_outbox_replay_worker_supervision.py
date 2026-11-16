"""Outbox worker 运行期监督和独立心跳契约。"""
from __future__ import annotations

import asyncio

import pytest

from app.core import startup_registry


@pytest.mark.asyncio
async def test_supervisor_restarts_worker_after_unexpected_return():
    stop_event = asyncio.Event()
    calls: list[int] = []

    async def fake_worker(stop: asyncio.Event) -> None:
        calls.append(1)
        if len(calls) > 1:
            await stop.wait()

    task = asyncio.create_task(startup_registry._supervise_worker(
        fake_worker,
        stop_event,
        "test-outbox",
        restart_delay_seconds=0.001,
    ))
    try:
        await asyncio.wait_for(_wait_until(lambda: len(calls) >= 2), timeout=1)
    finally:
        stop_event.set()
        await asyncio.wait_for(task, timeout=1)
    assert len(calls) >= 2


@pytest.mark.asyncio
async def test_outbox_heartbeat_is_refreshed_during_worker_wait(monkeypatch):
    stop_event = asyncio.Event()
    writes: list[str] = []

    async def fake_heartbeat(name: str, **_kwargs) -> None:
        writes.append(name)

    monkeypatch.setattr(startup_registry, "write_heartbeat", fake_heartbeat)
    task = asyncio.create_task(startup_registry._heartbeat_loop(
        stop_event,
        worker_name="outbox_replay_worker",
        interval_seconds=0.001,
    ))
    try:
        await asyncio.wait_for(_wait_until(lambda: len(writes) >= 2), timeout=1)
    finally:
        stop_event.set()
        await asyncio.wait_for(task, timeout=1)
    assert writes and set(writes) == {"outbox_replay_worker"}


async def _wait_until(predicate) -> None:
    while not predicate():
        await asyncio.sleep(0.001)


@pytest.mark.asyncio
async def test_outbox_run_stops_heartbeat_when_replay_loop_exits(monkeypatch):
    from app.workers import outbox_replay_worker

    stop_event = asyncio.Event()
    heartbeats: list[str] = []

    async def fake_loop(_stop: asyncio.Event) -> None:
        await asyncio.sleep(0)
        return None

    async def fake_heartbeat(name: str, **_kwargs) -> None:
        heartbeats.append(name)

    monkeypatch.setattr(outbox_replay_worker, "_run_loop", fake_loop)
    monkeypatch.setattr(outbox_replay_worker, "write_heartbeat", fake_heartbeat)
    await outbox_replay_worker.run(stop_event)
    assert heartbeats
    assert set(heartbeats) == {"outbox_replay_worker"}
