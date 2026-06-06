"""Stale 降级记录器 — 任何 stale 更新失败都记录到此，不允许静默 pass。"""
from __future__ import annotations
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_degraded_records: list[dict] = []


def log_stale_degraded(
    source: str,
    target: str,
    error: str,
    context: dict | None = None,
) -> None:
    """记录 stale 传播失败为 degraded。"""
    record = {
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "target": target,
        "error": error,
        "context": context or {},
    }
    _degraded_records.append(record)
    logger.warning(f"[stale-degraded] {source} → {target}: {error}")


def get_degraded_records() -> list[dict]:
    """获取所有降级记录（用于健康检查和 UI 展示）。"""
    return list(_degraded_records)


def clear_degraded_records() -> None:
    """清理降级记录（测试用）。"""
    _degraded_records.clear()
