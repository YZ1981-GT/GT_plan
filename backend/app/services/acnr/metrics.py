"""ACNR Metrics — 结构化指标收集器 [Req-12]

full_resolve 每次调用结束记录：
  {domain, layer_hit, result(found/ambiguous/miss/fallback), latency_ms}

降级/异常事件主动告警：
  - fallback: 非 wp 域委托 V1 / snapshot fallback
  - auth_reject: 项目授权拒绝（不含敏感数据）
  - alias_conflict: 别名冲突
  - version_mismatch: 版本快照缺失/不匹配
  - overlay_persist_fail: Overlay 持久化失败

提供 /api/acnr/metrics 端点返回近期聚合指标。

Requirements: Req-12.1, Req-12.2, Req-12.3, Req-12.4, Req-12.5
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─── Alert Severity ──────────────────────────────────────────────────────────

ALERT_WARNING = "warning"
ALERT_ERROR = "error"


# ─── Structured Metric Record ────────────────────────────────────────────────


@dataclass
class ResolveMetricRecord:
    """full_resolve 调用指标 (Req-12.1)。"""

    domain: str  # "wp" | "tb" | "report" | "note" | "aux" | "unknown"
    layer_hit: Optional[str]  # "L1_cell" | "L1_sheet" | "L2" | "L3" | "V1" | None
    result: str  # "found" | "ambiguous" | "miss" | "fallback"
    latency_ms: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class AlertEvent:
    """主动告警事件 (Req-12.5)。"""

    event_type: str  # "fallback" | "auth_reject" | "alias_conflict" | "version_mismatch" | "overlay_persist_fail"
    reason: str
    severity: str = ALERT_WARNING
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


# ─── AcnrMetricsCollector (Singleton) ────────────────────────────────────────

MAX_RECENT_RECORDS = 500
MAX_RECENT_ALERTS = 200


class AcnrMetricsCollector:
    """ACNR 结构化指标收集器 — 进程内单例 (Req-12)。

    线程安全（GIL + lock 双保险；asyncio 单线程无竞争）。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._recent_records: deque[ResolveMetricRecord] = deque(maxlen=MAX_RECENT_RECORDS)
        self._recent_alerts: deque[AlertEvent] = deque(maxlen=MAX_RECENT_ALERTS)

        # 聚合计数器
        self._result_counts: dict[str, int] = defaultdict(int)  # found/miss/ambiguous/fallback
        self._domain_counts: dict[str, int] = defaultdict(int)  # wp/tb/report/...
        self._layer_counts: dict[str, int] = defaultdict(int)  # L1_cell/L1_sheet/L2/L3/V1
        self._alert_type_counts: dict[str, int] = defaultdict(int)
        self._total_calls: int = 0
        self._total_latency_ms: float = 0.0

    # ─── Record a resolve call (Req-12.1) ────────────────────────────────

    def record_resolve(
        self,
        *,
        domain: str,
        layer_hit: Optional[str],
        result: str,
        latency_ms: float,
    ) -> None:
        """记录一次 full_resolve 调用结束指标。"""
        record = ResolveMetricRecord(
            domain=domain,
            layer_hit=layer_hit,
            result=result,
            latency_ms=latency_ms,
        )
        with self._lock:
            self._recent_records.append(record)
            self._result_counts[result] += 1
            self._domain_counts[domain] += 1
            if layer_hit:
                self._layer_counts[layer_hit] += 1
            self._total_calls += 1
            self._total_latency_ms += latency_ms

    # ─── Record alert events (Req-12.2, 12.3, 12.5) ─────────────────────

    def record_alert(
        self,
        *,
        event_type: str,
        reason: str,
        severity: str = ALERT_WARNING,
        metadata: Optional[dict] = None,
    ) -> None:
        """记录告警事件（fallback/auth_reject/alias_conflict/version_mismatch 等）。

        主动告警 = logger.warning + 记录到 metrics（不只 logger）。
        """
        event = AlertEvent(
            event_type=event_type,
            reason=reason,
            severity=severity,
            metadata=metadata or {},
        )
        with self._lock:
            self._recent_alerts.append(event)
            self._alert_type_counts[event_type] += 1

        # Req-12.5: 主动告警（非仅 logger.warning）
        if severity == ALERT_ERROR:
            logger.error(
                "ACNR alert [%s]: %s metadata=%s",
                event_type, reason, metadata or {},
            )
        else:
            logger.warning(
                "ACNR alert [%s]: %s metadata=%s",
                event_type, reason, metadata or {},
            )

    # ─── Convenience shortcuts ───────────────────────────────────────────

    def record_fallback(self, reason: str, *, domain: str = "unknown") -> None:
        """Req-12.2: 记录 fallback 事件。"""
        self.record_alert(
            event_type="fallback",
            reason=reason,
            metadata={"domain": domain},
        )

    def record_auth_reject(self, *, project_id: Optional[str] = None) -> None:
        """Req-12.3: 记录 auth_reject（不含敏感数据）。"""
        self.record_alert(
            event_type="auth_reject",
            reason="项目授权拒绝",
            metadata={"has_project_id": bool(project_id)},
        )

    def record_alias_conflict(self, alias: str, candidates_count: int) -> None:
        """Req-12.5: alias conflict 告警。"""
        self.record_alert(
            event_type="alias_conflict",
            reason=f"别名冲突: {alias} ({candidates_count} candidates)",
            severity=ALERT_ERROR,
            metadata={"alias": alias, "candidates": candidates_count},
        )

    def record_version_mismatch(self, version: str, reason: str) -> None:
        """Req-12.5: version mismatch 告警。"""
        self.record_alert(
            event_type="version_mismatch",
            reason=reason,
            severity=ALERT_ERROR,
            metadata={"version": version},
        )

    def record_overlay_persist_fail(self, reason: str) -> None:
        """Req-12.5: Overlay 持久化失败告警。"""
        self.record_alert(
            event_type="overlay_persist_fail",
            reason=reason,
            severity=ALERT_ERROR,
        )

    # ─── Aggregation for endpoint (Req-12.4) ─────────────────────────────

    def get_aggregated_metrics(self) -> dict[str, Any]:
        """返回近期聚合指标（供 /api/acnr/metrics 端点）。"""
        with self._lock:
            avg_latency = (
                self._total_latency_ms / self._total_calls
                if self._total_calls > 0
                else 0.0
            )
            return {
                "total_calls": self._total_calls,
                "avg_latency_ms": round(avg_latency, 2),
                "by_result": dict(self._result_counts),
                "by_domain": dict(self._domain_counts),
                "by_layer": dict(self._layer_counts),
                "alerts": {
                    "total": sum(self._alert_type_counts.values()),
                    "by_type": dict(self._alert_type_counts),
                    "recent": [
                        asdict(a) for a in list(self._recent_alerts)[-20:]
                    ],
                },
                "recent_records": [
                    asdict(r) for r in list(self._recent_records)[-50:]
                ],
            }

    # ─── Reset (for testing) ─────────────────────────────────────────────

    def reset(self) -> None:
        """重置所有指标（测试用）。"""
        with self._lock:
            self._recent_records.clear()
            self._recent_alerts.clear()
            self._result_counts.clear()
            self._domain_counts.clear()
            self._layer_counts.clear()
            self._alert_type_counts.clear()
            self._total_calls = 0
            self._total_latency_ms = 0.0


# ─── Module-level singleton ──────────────────────────────────────────────────

_metrics_collector: Optional[AcnrMetricsCollector] = None


def get_acnr_metrics() -> AcnrMetricsCollector:
    """获取全局 ACNR 指标收集器单例。"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = AcnrMetricsCollector()
    return _metrics_collector


def reset_acnr_metrics() -> None:
    """重置全局指标（测试用）。"""
    global _metrics_collector
    _metrics_collector = AcnrMetricsCollector()
