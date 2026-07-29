"""附件↔底稿关联 — fail-open 结构化可观测日志。

spec 复盘收口：双写 / 函证 / 证据声明 / stale / OCR 回流失败时统一事件名，
便于检索 ``event=awp_*_fail_open``，不改变 fail-open 语义。

并挂 Prometheus Counter（未安装 prometheus_client 时 stub）。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.attachment_wp_linkage")

try:
    from prometheus_client import Counter

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

    class _Stub:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def labels(self, *args: Any, **kwargs: Any) -> "_Stub":
            return self

        def inc(self, *args: Any, **kwargs: Any) -> None:
            pass

    Counter = _Stub  # type: ignore[misc,assignment]


AWP_FAIL_OPEN_TOTAL = (
    Counter(
        "awp_fail_open_total",
        "Attachment↔workpaper linkage fail-open events",
        ["event"],
    )
    if _PROMETHEUS_AVAILABLE
    else _Stub("awp_fail_open_total", "", ["event"])
)


def log_awp_fail_open(event: str, *, exc_info: bool = True, **fields: Any) -> None:
    """记录结构化 fail-open warning，并递增 ``awp_fail_open_total{event=}``。"""
    parts = [f"event={event}"]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    logger.warning(" ".join(parts), exc_info=exc_info)
    try:
        AWP_FAIL_OPEN_TOTAL.labels(event=event).inc()
    except Exception:
        pass
