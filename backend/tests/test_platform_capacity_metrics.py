"""平台容量指标统一暴露与关键采样器测试。"""
from __future__ import annotations

import asyncio
import time

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db_pool_metrics import (
    InstrumentedAsyncAdaptedQueuePool,
    install_pool_metrics,
    pool_capacity_snapshot,
)
from app.services.platform_metrics import (
    PROMETHEUS_AVAILABLE,
    event_loop_snapshot,
    render_platform_metrics,
)


def test_root_metrics_payload_contains_all_capacity_families():
    body, content_type = render_platform_metrics()
    text = body.decode("utf-8")
    assert "text/plain" in content_type
    if not PROMETHEUS_AVAILABLE:
        assert text == "# prometheus_client not installed\n"
        return
    for metric in (
        "ledger_import_jobs_total",
        "ai_chat_active_runs",
        "libreoffice_queue_depth",
        "platform_event_loop_lag_seconds",
        "db_pool_checked_out_connections",
    ):
        assert metric in text


@pytest.mark.asyncio
async def test_instrumented_pool_records_capacity_and_real_timeout(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'pool.db'}",
        poolclass=InstrumentedAsyncAdaptedQueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.02,
    )
    install_pool_metrics(
        engine.sync_engine.pool,
        mode="test",
        configured_size=1,
        configured_overflow=0,
    )
    first = await engine.connect()
    try:
        snapshot = pool_capacity_snapshot(engine.sync_engine.pool)
        assert snapshot == {
            "mode": "test",
            "checked_out": 1,
            "configured_size": 1,
            "configured_overflow": 0,
            "capacity": 1,
        }
        with pytest.raises(sa.exc.TimeoutError):
            await engine.connect()
    finally:
        await first.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_event_loop_worker_observes_blocking_lag(monkeypatch):
    from app.workers import event_loop_lag_worker as worker

    monkeypatch.setattr(worker, "INTERVAL_SECONDS", 0.005)
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(0.01)
    time.sleep(0.03)
    await asyncio.sleep(0.01)
    stop.set()
    await task

    snapshot = event_loop_snapshot(asyncio.get_running_loop().time())
    assert snapshot["stale"] is False
    assert snapshot["max_seconds"] >= 0.015


def test_health_capacity_snapshot_is_read_only_and_complete():
    from app.api.health import _capacity_snapshot

    snapshot = _capacity_snapshot()
    assert set(snapshot) == {
        "db_pool",
        "event_loop",
        "libreoffice",
        "bulk_import",
    }
    assert "capacity" in snapshot["db_pool"]
    assert "stale" in snapshot["event_loop"]
    assert "queue_limit" in snapshot["libreoffice"]
    assert "spool_budget_bytes" in snapshot["bulk_import"]
