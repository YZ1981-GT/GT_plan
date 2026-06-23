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


# ─── 孤立 EventBus 已删除 ────────────────────────────────────────────────────
# snapshot_writer 现使用主 event_bus (app.services.event_bus) 通过 orchestrator 发布事件。
# 保留此注释便于追溯：原 _EventBus 类和 event_bus 实例在此处，
# 迁移至 WorkpaperSaveOrchestrator 后不再需要。
