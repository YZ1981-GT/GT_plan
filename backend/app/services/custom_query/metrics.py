"""Prometheus 埋点 — 高级查询 / snapshot 单源化监控指标

Req 6（P2-10）：snapshot_missing_total — parsed_data['univer_snapshot'] 缺失时
走 LibreOffice 兜底的次数计数器。

prometheus_client 未安装时用 _Stub 占位，保证 import 不破坏。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

    class _Stub:
        """Nil-op 占位"""
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

    Counter = _Stub  # type: ignore[misc,assignment]


# 独立指标（不挂 registry，走默认 registry 或 ledger_import 的 REGISTRY 均可）
SNAPSHOT_MISSING_TOTAL = Counter(
    "snapshot_missing_total",
    "Number of times parsed_data['univer_snapshot'] was missing/corrupted, "
    "triggering LibreOffice fallback recompute",
    ["wp_code"],
) if _PROMETHEUS_AVAILABLE else _Stub(
    "snapshot_missing_total", "", ["wp_code"]
)


def inc_snapshot_missing(wp_code: str) -> None:
    """记录一次 snapshot 缺失事件（触发 LibreOffice 兜底）"""
    SNAPSHOT_MISSING_TOTAL.labels(wp_code=wp_code).inc()
    logger.warning("snapshot_missing: wp_code=%s, 走 LibreOffice 兜底", wp_code)


# ─── Simple Event Bus ────────────────────────────────────────────────────────


class _EventBus:
    """简单事件总线，用于 cross-ref:updated 等内部事件通知。"""

    def __init__(self):
        self._listeners: dict[str, list] = {}

    def on(self, event_name: str, callback):
        self._listeners.setdefault(event_name, []).append(callback)

    def emit(self, event_name: str, payload: dict | None = None):
        for cb in self._listeners.get(event_name, []):
            try:
                cb(payload)
            except Exception as e:
                logger.warning("event_bus emit error [%s]: %s", event_name, e)


event_bus = _EventBus()
