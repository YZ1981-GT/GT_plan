"""SQLAlchemy pool 容量、持有时长、获取等待和超时指标。"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import event
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.pool import AsyncAdaptedQueuePool

try:
    from prometheus_client import Counter, Gauge, Histogram
except ImportError:  # pragma: no cover
    class _MetricStub:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

        def dec(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

    Counter = Gauge = Histogram = _MetricStub  # type: ignore[misc,assignment]


DB_POOL_CHECKED_OUT = Gauge(
    "db_pool_checked_out_connections",
    "Connections currently checked out from this process",
    labelnames=("mode",),
)
DB_POOL_CAPACITY = Gauge(
    "db_pool_configured_capacity",
    "Configured direct-pool capacity; zero means externally managed",
    labelnames=("mode",),
)
DB_POOL_HOLD_SECONDS = Histogram(
    "db_pool_connection_hold_seconds",
    "Time a checked-out connection remains held",
    labelnames=("mode",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 15, 30, 60),
)
DB_POOL_WAIT_SECONDS = Histogram(
    "db_pool_checkout_wait_seconds",
    "Time spent acquiring a direct pooled connection",
    labelnames=("mode",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 5, 15, 30),
)
DB_POOL_TIMEOUTS = Counter(
    "db_pool_checkout_timeouts_total",
    "Direct pool acquisition timeouts",
    labelnames=("mode",),
)


class InstrumentedAsyncAdaptedQueuePool(AsyncAdaptedQueuePool):
    """只覆写获取边界；其余排队语义完全交给 SQLAlchemy。"""

    metrics_mode = "direct"

    def _do_get(self):  # noqa: ANN202 - SQLAlchemy protected hook signature
        started = time.perf_counter()
        try:
            return super()._do_get()
        except SqlAlchemyTimeoutError:
            DB_POOL_TIMEOUTS.labels(mode=self.metrics_mode).inc()
            raise
        finally:
            DB_POOL_WAIT_SECONDS.labels(mode=self.metrics_mode).observe(
                time.perf_counter() - started
            )


_POOL_CONFIG: dict[int, dict[str, Any]] = {}


def install_pool_metrics(
    pool: Any,
    *,
    mode: str,
    configured_size: int | None,
    configured_overflow: int | None,
) -> None:
    """为一个 pool 安装一次 checkout/checkin listener。"""
    identity = id(pool)
    if identity in _POOL_CONFIG:
        return
    capacity = (
        None
        if configured_size is None or configured_overflow is None
        else configured_size + configured_overflow
    )
    _POOL_CONFIG[identity] = {
        "pool": pool,
        "mode": mode,
        "configured_size": configured_size,
        "configured_overflow": configured_overflow,
        "capacity": capacity,
    }
    DB_POOL_CAPACITY.labels(mode=mode).set(capacity or 0)
    DB_POOL_CHECKED_OUT.labels(mode=mode).set(0)

    @event.listens_for(pool, "checkout")
    def _checkout(_dbapi_connection, connection_record, _connection_proxy):
        connection_record.info["gt_checked_out_at"] = time.perf_counter()
        DB_POOL_CHECKED_OUT.labels(mode=mode).inc()

    @event.listens_for(pool, "checkin")
    def _checkin(_dbapi_connection, connection_record):
        DB_POOL_CHECKED_OUT.labels(mode=mode).dec()
        started = connection_record.info.pop("gt_checked_out_at", None)
        if started is not None:
            DB_POOL_HOLD_SECONDS.labels(mode=mode).observe(
                max(0.0, time.perf_counter() - float(started))
            )


def pool_capacity_snapshot(pool: Any) -> dict[str, Any]:
    """只读当前 pool 状态；外部 PgBouncer 容量明确返回 unknown。"""
    config = _POOL_CONFIG.get(id(pool), {})
    checked_out_fn = getattr(pool, "checkedout", None)
    checked_out = int(checked_out_fn()) if callable(checked_out_fn) else None
    return {
        "mode": config.get("mode", "unknown"),
        "checked_out": checked_out,
        "configured_size": config.get("configured_size"),
        "configured_overflow": config.get("configured_overflow"),
        "capacity": config.get("capacity"),
    }


__all__ = [
    "InstrumentedAsyncAdaptedQueuePool",
    "install_pool_metrics",
    "pool_capacity_snapshot",
]
