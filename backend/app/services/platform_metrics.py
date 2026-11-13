"""平台容量指标的统一 Prometheus 暴露面。"""
from __future__ import annotations

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY as DEFAULT_REGISTRY,
        Gauge,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain"
    DEFAULT_REGISTRY = None

    class _MetricStub:
        def __init__(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

    Gauge = Histogram = _MetricStub  # type: ignore[misc,assignment]


EVENT_LOOP_LAG_SECONDS = Gauge(
    "platform_event_loop_lag_seconds",
    "Current event-loop scheduling lag in this worker",
)
EVENT_LOOP_LAG_MAX_SECONDS = Gauge(
    "platform_event_loop_lag_max_seconds",
    "Maximum event-loop scheduling lag observed in this worker",
)
EVENT_LOOP_LAG_OBSERVATIONS = Histogram(
    "platform_event_loop_lag_observation_seconds",
    "Distribution of event-loop scheduling lag",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

_event_loop_snapshot = {
    "current_seconds": 0.0,
    "max_seconds": 0.0,
    "sampled_at_monotonic": 0.0,
}

DURABLE_QUEUE_DEPTH = Gauge(
    "platform_durable_queue_depth",
    "Non-terminal durable job rows by status",
    labelnames=("queue", "status"),
)
DURABLE_QUEUE_OLDEST_AGE_SECONDS = Gauge(
    "platform_durable_queue_oldest_age_seconds",
    "Age of the oldest row still waiting to be claimed",
    labelnames=("queue",),
)

#: health 固定展示这几条耐久队列：采样器没跑起来时要看得见「未采样」，而不是静默消失。
DURABLE_QUEUE_NAMES = ("platform_jobs", "ai_task_items")
DURABLE_QUEUE_STATUSES = ("queued", "retry_wait", "running")
#: 采样间隔 15s，超过这个年龄即判 stale。
DURABLE_QUEUE_STALE_AFTER_SECONDS = 60.0

_durable_queues: dict[str, dict[str, object]] = {}


def observe_durable_queue(
    queue: str,
    *,
    counts: dict[str, int],
    oldest_age_seconds: float,
    sampled_at: float,
) -> None:
    """记录一次成功采样。"""
    normalized = {
        status: max(0, int(counts.get(status, 0))) for status in DURABLE_QUEUE_STATUSES
    }
    oldest = max(0.0, float(oldest_age_seconds))
    for status, value in normalized.items():
        DURABLE_QUEUE_DEPTH.labels(queue=queue, status=status).set(value)
    DURABLE_QUEUE_OLDEST_AGE_SECONDS.labels(queue=queue).set(oldest)
    _durable_queues[queue] = {
        "available": True,
        **normalized,
        "oldest_queue_age_seconds": round(oldest, 3),
        "sampled_at_monotonic": float(sampled_at),
    }


def mark_durable_queue_unavailable(queue: str, *, reason: str, sampled_at: float) -> None:
    """采样失败。

    🔴 绝不发布 0：读不到队列深度和「队列是空的」是两件事，把失败写成 0 会让积压
    在图上凭空消失。这里只标记不可用并保留上一次已知值，由 snapshot 的
    ``available`` / ``stale`` 暴露出来。
    """
    previous = _durable_queues.get(queue, {})
    _durable_queues[queue] = {
        **previous,
        "available": False,
        "reason": reason,
        "sampled_at_monotonic": float(sampled_at),
    }


def durable_queue_snapshot(now_monotonic: float) -> dict[str, dict[str, object]]:
    """只读耐久队列快照；不做任何 I/O（health 在请求里不扫任务表）。"""
    snapshot: dict[str, dict[str, object]] = {}
    for queue in DURABLE_QUEUE_NAMES:
        entry = _durable_queues.get(queue)
        if entry is None:
            snapshot[queue] = {
                "available": False,
                "reason": "not_sampled",
                "stale": True,
            }
            continue
        sampled = float(entry.get("sampled_at_monotonic") or 0.0)
        snapshot[queue] = {
            **entry,
            "stale": sampled <= 0
            or now_monotonic - sampled > DURABLE_QUEUE_STALE_AFTER_SECONDS,
        }
    return snapshot


def observe_event_loop_lag(lag_seconds: float, sampled_at: float) -> None:
    lag = max(0.0, float(lag_seconds))
    _event_loop_snapshot["current_seconds"] = lag
    _event_loop_snapshot["max_seconds"] = max(
        _event_loop_snapshot["max_seconds"],
        lag,
    )
    _event_loop_snapshot["sampled_at_monotonic"] = float(sampled_at)
    EVENT_LOOP_LAG_SECONDS.set(lag)
    EVENT_LOOP_LAG_MAX_SECONDS.set(_event_loop_snapshot["max_seconds"])
    EVENT_LOOP_LAG_OBSERVATIONS.observe(lag)


def event_loop_snapshot(now_monotonic: float) -> dict[str, float | bool]:
    sampled = _event_loop_snapshot["sampled_at_monotonic"]
    return {
        **_event_loop_snapshot,
        "stale": sampled <= 0 or now_monotonic - sampled > 5.0,
    }


def render_platform_metrics() -> tuple[bytes, str]:
    """合并默认、账表导入与 AI Chat registry，保留旧独立端点兼容。"""
    if not PROMETHEUS_AVAILABLE:
        return b"# prometheus_client not installed\n", "text/plain"

    # 导入模块以确保默认 registry 上的容量指标已注册。
    from app.services import capacity_slots as _capacity_slots  # noqa: F401
    from app.services import libreoffice_pool as _libreoffice_pool  # noqa: F401
    from app.services.bulk_tab import bulk_async_runner as _bulk_async_runner  # noqa: F401
    from app.services.ai_chat.metrics import AI_CHAT_REGISTRY
    from app.services.ledger_import.metrics import REGISTRY as LEDGER_REGISTRY

    registries = []
    for registry in (DEFAULT_REGISTRY, LEDGER_REGISTRY, AI_CHAT_REGISTRY):
        if registry is not None and all(registry is not item for item in registries):
            registries.append(registry)
    chunks = [generate_latest(registry).rstrip() for registry in registries]
    return b"\n".join(chunk for chunk in chunks if chunk) + b"\n", CONTENT_TYPE_LATEST


__all__ = [
    "DURABLE_QUEUE_DEPTH",
    "DURABLE_QUEUE_NAMES",
    "DURABLE_QUEUE_OLDEST_AGE_SECONDS",
    "DURABLE_QUEUE_STALE_AFTER_SECONDS",
    "DURABLE_QUEUE_STATUSES",
    "EVENT_LOOP_LAG_MAX_SECONDS",
    "EVENT_LOOP_LAG_OBSERVATIONS",
    "EVENT_LOOP_LAG_SECONDS",
    "durable_queue_snapshot",
    "event_loop_snapshot",
    "mark_durable_queue_unavailable",
    "observe_durable_queue",
    "observe_event_loop_lag",
    "render_platform_metrics",
]
