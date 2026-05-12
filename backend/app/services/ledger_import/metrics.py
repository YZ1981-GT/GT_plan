"""Prometheus 最小埋点（F16 / Sprint 4.9）。

3 + 2 核心指标：
- ledger_import_duration_seconds{phase} histogram
- ledger_import_jobs_total{status} counter
- ledger_dataset_count{project_id, status} gauge
- event_outbox_dlq_depth gauge (F45 预留)
- ledger_import_health_status gauge (F43 预留)

prometheus_client 未安装时用 _Stub 占位，保证 import 不破坏。
render_metrics() 产出 /metrics 端点的 body + content-type。
"""

from __future__ import annotations

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover — 仅开发环境无 prometheus_client 时触发
    _PROMETHEUS_AVAILABLE = False

    class _Stub:
        """Nil-op 占位 — 签名兼容 prometheus_client 的 Counter/Histogram/Gauge。"""

        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

        def dec(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

    Counter = Histogram = Gauge = _Stub  # type: ignore[misc,assignment]
    CollectorRegistry = _Stub  # type: ignore[misc,assignment]
    CONTENT_TYPE_LATEST = "text/plain"

    def generate_latest(*args, **kwargs):  # type: ignore[misc]
        return b"# prometheus_client not installed\n"


# 独立 registry — 避免与其他库（如 fastapi-prometheus）的默认 registry 冲突
REGISTRY = CollectorRegistry() if _PROMETHEUS_AVAILABLE else None


if _PROMETHEUS_AVAILABLE:
    IMPORT_DURATION = Histogram(
        "ledger_import_duration_seconds",
        "Ledger import phase duration in seconds",
        ["phase"],
        buckets=[1, 5, 15, 30, 60, 180, 300, 600, 1800, 3600],
        registry=REGISTRY,
    )
    IMPORT_JOBS_TOTAL = Counter(
        "ledger_import_jobs_total",
        "Ledger import job state transitions "
        "(queued/running/completed/failed/canceled/timed_out)",
        ["status"],
        registry=REGISTRY,
    )
    DATASET_COUNT = Gauge(
        "ledger_dataset_count",
        "Current dataset count by project and status",
        ["project_id", "status"],
        registry=REGISTRY,
    )
    EVENT_DLQ_DEPTH = Gauge(
        "event_outbox_dlq_depth",
        "Dead letter queue depth for failed event broadcasts",
        registry=REGISTRY,
    )
    HEALTH_STATUS = Gauge(
        "ledger_import_health_status",
        "Ledger import subsystem health (0=healthy, 1=degraded, 2=unhealthy)",
        registry=REGISTRY,
    )
else:
    IMPORT_DURATION = Histogram()
    IMPORT_JOBS_TOTAL = Counter()
    DATASET_COUNT = Gauge()
    EVENT_DLQ_DEPTH = Gauge()
    HEALTH_STATUS = Gauge()


def observe_phase_duration(phase: str, seconds: float) -> None:
    """记录某 phase 的耗时（供 pipeline._mark 调用）。"""
    if _PROMETHEUS_AVAILABLE:
        IMPORT_DURATION.labels(phase=phase).observe(seconds)


def inc_job_status(status: str) -> None:
    """记录一次 job 状态转换（供 ImportJobService.transition 调用）。"""
    if _PROMETHEUS_AVAILABLE:
        IMPORT_JOBS_TOTAL.labels(status=status).inc()


def set_dataset_count(project_id: str, status: str, count: int) -> None:
    """设置指定 project+status 组合的 dataset 数量（供定时扫描 worker 调用）。"""
    if _PROMETHEUS_AVAILABLE:
        DATASET_COUNT.labels(project_id=project_id, status=status).set(count)


def set_dlq_depth(depth: int) -> None:
    """设置 event_outbox DLQ 深度（F45 预留）。"""
    if _PROMETHEUS_AVAILABLE:
        EVENT_DLQ_DEPTH.set(depth)


def set_health_status(value: int) -> None:
    """设置健康状态 0=healthy / 1=degraded / 2=unhealthy（F43 预留）。"""
    if _PROMETHEUS_AVAILABLE:
        HEALTH_STATUS.set(value)


def render_metrics() -> tuple[bytes, str]:
    """生成 /metrics 响应体 + content-type。"""
    if not _PROMETHEUS_AVAILABLE:
        return b"# prometheus_client not installed\n", "text/plain"
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


__all__ = [
    "IMPORT_DURATION",
    "IMPORT_JOBS_TOTAL",
    "DATASET_COUNT",
    "EVENT_DLQ_DEPTH",
    "HEALTH_STATUS",
    "REGISTRY",
    "observe_phase_duration",
    "inc_job_status",
    "set_dataset_count",
    "set_dlq_depth",
    "set_health_status",
    "render_metrics",
]
