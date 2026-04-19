"""性能监控服务 — Prometheus 指标 + 告警 + 慢查询

Phase 8 Task 8: 性能监控
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus-style metrics (in-memory, no prometheus_client dependency needed)
# ---------------------------------------------------------------------------


class MetricsCollector:
    """轻量级指标收集器（兼容 prometheus_client 接口）。"""

    def __init__(self):
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = defaultdict(float)

    def observe_histogram(self, name: str, value: float, labels: dict | None = None):
        key = self._label_key(name, labels)
        self._histograms[key].append(value)
        # Keep only last 1000 observations
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]

    def inc_counter(self, name: str, labels: dict | None = None):
        key = self._label_key(name, labels)
        self._counters[key] += 1

    def set_gauge(self, name: str, value: float, labels: dict | None = None):
        key = self._label_key(name, labels)
        self._gauges[key] = value

    def get_histogram_stats(self, name: str, labels: dict | None = None) -> dict:
        key = self._label_key(name, labels)
        values = self._histograms.get(key, [])
        if not values:
            return {"count": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0, "max": 0}
        sorted_v = sorted(values)
        n = len(sorted_v)
        return {
            "count": n,
            "avg": sum(sorted_v) / n,
            "p50": sorted_v[int(n * 0.5)],
            "p95": sorted_v[min(int(n * 0.95), n - 1)],
            "p99": sorted_v[min(int(n * 0.99), n - 1)],
            "max": sorted_v[-1],
        }

    def get_counter(self, name: str, labels: dict | None = None) -> int:
        return self._counters.get(self._label_key(name, labels), 0)

    def get_gauge(self, name: str, labels: dict | None = None) -> float:
        return self._gauges.get(self._label_key(name, labels), 0.0)

    def _label_key(self, name: str, labels: dict | None) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def reset(self):
        self._histograms.clear()
        self._counters.clear()
        self._gauges.clear()


# Global metrics collector
metrics = MetricsCollector()


# ---------------------------------------------------------------------------
# Performance thresholds & alerts
# ---------------------------------------------------------------------------

THRESHOLDS = {
    "api_response_time_seconds": {"warning": 1.0, "critical": 3.0},
    "db_query_time_seconds": {"warning": 0.5, "critical": 2.0},
    "cache_hit_rate": {"warning": 0.5, "critical": 0.3},  # below = bad
}


class PerformanceMonitor:
    """性能监控服务。"""

    def __init__(self):
        self._slow_queries: list[dict] = []
        self._alerts: list[dict] = []

    def record_api_response(self, endpoint: str, method: str, duration: float):
        """记录 API 响应时间。"""
        metrics.observe_histogram(
            "api_response_time_seconds",
            duration,
            {"endpoint": endpoint, "method": method},
        )
        metrics.inc_counter("api_requests_total", {"endpoint": endpoint, "method": method})

        # Check threshold
        threshold = THRESHOLDS["api_response_time_seconds"]
        if duration > threshold["critical"]:
            self._add_alert("critical", f"API {method} {endpoint} 响应时间 {duration:.2f}s 超过阈值 {threshold['critical']}s")
        elif duration > threshold["warning"]:
            self._add_alert("warning", f"API {method} {endpoint} 响应时间 {duration:.2f}s 超过警告阈值 {threshold['warning']}s")

    def record_db_query(self, query_type: str, duration: float, sql: str = ""):
        """记录数据库查询时间。"""
        metrics.observe_histogram("db_query_time_seconds", duration, {"query_type": query_type})

        threshold = THRESHOLDS["db_query_time_seconds"]
        if duration > threshold["warning"]:
            self._slow_queries.append({
                "query_type": query_type,
                "duration": duration,
                "sql": sql[:200] if sql else "",
                "timestamp": time.time(),
            })
            # Keep only last 100 slow queries
            if len(self._slow_queries) > 100:
                self._slow_queries = self._slow_queries[-100:]

    def record_cache_hit(self, cache_name: str, hit: bool):
        """记录缓存命中。"""
        metrics.inc_counter(f"cache_{'hit' if hit else 'miss'}", {"cache_name": cache_name})
        # Update hit rate gauge
        hits = metrics.get_counter("cache_hit", {"cache_name": cache_name})
        misses = metrics.get_counter("cache_miss", {"cache_name": cache_name})
        total = hits + misses
        rate = hits / total if total > 0 else 0
        metrics.set_gauge("cache_hit_rate", rate, {"cache_name": cache_name})

    def get_performance_stats(self) -> dict:
        """获取性能统计摘要。"""
        return {
            "api_response_time": metrics.get_histogram_stats("api_response_time_seconds"),
            "db_query_time": metrics.get_histogram_stats("db_query_time_seconds"),
            "cache_hit_rate": metrics.get_gauge("cache_hit_rate"),
            "total_requests": sum(
                v for k, v in metrics._counters.items() if k.startswith("api_requests_total")
            ),
            "slow_query_count": len(self._slow_queries),
            "alert_count": len(self._alerts),
        }

    def get_slow_queries(self, limit: int = 20) -> list[dict]:
        """获取慢查询列表。"""
        return self._slow_queries[-limit:]

    def get_alerts(self, limit: int = 50) -> list[dict]:
        """获取告警列表。"""
        return self._alerts[-limit:]

    def get_metrics(self) -> dict:
        """获取所有指标。"""
        return {
            "histograms": {k: metrics.get_histogram_stats(k) for k in set(
                k.split("{")[0] for k in metrics._histograms.keys()
            )},
            "counters": dict(metrics._counters),
            "gauges": dict(metrics._gauges),
        }

    def _add_alert(self, level: str, message: str):
        self._alerts.append({
            "level": level,
            "message": message,
            "timestamp": time.time(),
        })
        if len(self._alerts) > 200:
            self._alerts = self._alerts[-200:]


# Global instance
performance_monitor = PerformanceMonitor()
