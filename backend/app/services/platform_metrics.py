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
    "EVENT_LOOP_LAG_MAX_SECONDS",
    "EVENT_LOOP_LAG_OBSERVATIONS",
    "EVENT_LOOP_LAG_SECONDS",
    "event_loop_snapshot",
    "observe_event_loop_lag",
    "render_platform_metrics",
]
