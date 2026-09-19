"""底稿性能与可观测性指标收集器

Design §10 指标：
- wp_render_config_duration_ms{component_type,cold} — render-config 冷/热耗时
- wp_renderer_invocations{component_type} — renderer 调用次数
- wp_checklist_save_duration_ms{status} — 保存耗时（按状态）
- wp_checklist_conflicts_total — 409 冲突计数

Requirements: 8.1-8.3
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator

logger = logging.getLogger(__name__)


@dataclass
class _HistogramBucket:
    """固定窗口直方图（保留最近 500 个观测值）。"""
    values: list[float] = field(default_factory=list)
    _max_size: int = 500

    def observe(self, value: float) -> None:
        self.values.append(value)
        if len(self.values) > self._max_size:
            self.values = self.values[-self._max_size:]

    def stats(self) -> dict:
        if not self.values:
            return {"count": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
        sorted_v = sorted(self.values)
        n = len(sorted_v)
        return {
            "count": n,
            "avg": round(sum(sorted_v) / n, 2),
            "p50": round(sorted_v[int(n * 0.5)], 2),
            "p95": round(sorted_v[min(int(n * 0.95), n - 1)], 2),
            "max": round(sorted_v[-1], 2),
        }


class WpMetricsCollector:
    """底稿模块专用指标收集器（进程内单例，无外部依赖）。

    所有方法线程安全（GIL 保护；asyncio 单线程无竞争）。
    """

    def __init__(self) -> None:
        self._render_config_duration: dict[str, _HistogramBucket] = defaultdict(
            _HistogramBucket
        )
        self._renderer_invocations: dict[str, int] = defaultdict(int)
        self._save_duration: dict[str, _HistogramBucket] = defaultdict(
            _HistogramBucket
        )
        self._conflicts_total: int = 0
        self._save_failures_total: int = 0

    # ─── render-config 耗时 ──────────────────────────────────────────────────

    def observe_render_config(
        self, component_type: str, duration_ms: float, *, cold: bool
    ) -> None:
        """记录一次 render-config 请求耗时。"""
        label = f"{component_type}|{'cold' if cold else 'hot'}"
        self._render_config_duration[label].observe(duration_ms)
        if duration_ms > 3000:
            logger.warning(
                "wp_render_config slow: component_type=%s cold=%s duration_ms=%.1f",
                component_type,
                cold,
                duration_ms,
            )

    @contextmanager
    def time_render_config(
        self, component_type: str, *, cold: bool
    ) -> Generator[None, None, None]:
        """上下文管理器：自动计时 render-config。"""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.observe_render_config(component_type, elapsed_ms, cold=cold)

    # ─── renderer 调用次数 ───────────────────────────────────────────────────

    def inc_renderer_invocation(self, component_type: str) -> None:
        """记录一次 renderer 实际调用（非 memo 命中）。"""
        self._renderer_invocations[component_type] += 1

    # ─── checklist save 耗时 ─────────────────────────────────────────────────

    def observe_save(self, duration_ms: float, *, status: str) -> None:
        """记录一次 checklist 保存耗时。

        status: 'success' | 'conflict' | 'error'
        """
        self._save_duration[status].observe(duration_ms)
        if status == "conflict":
            self._conflicts_total += 1
        elif status == "error":
            self._save_failures_total += 1

    @contextmanager
    def time_save(self) -> Generator[dict, None, None]:
        """上下文管理器：自动计时保存操作。

        用法:
            with wp_metrics.time_save() as ctx:
                ... do save ...
                ctx['status'] = 'success'  # 或 'conflict' / 'error'
        """
        ctx: dict = {"status": "success"}
        start = time.perf_counter()
        try:
            yield ctx
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.observe_save(elapsed_ms, status=ctx.get("status", "error"))

    # ─── 查询接口 ───────────────────────────────────────────────────────────

    def get_render_config_stats(self) -> dict:
        """返回 render-config 各 label 的统计。"""
        return {
            label: bucket.stats()
            for label, bucket in self._render_config_duration.items()
        }

    def get_renderer_invocations(self) -> dict[str, int]:
        """返回各 componentType 的 renderer 调用次数。"""
        return dict(self._renderer_invocations)

    def get_save_stats(self) -> dict:
        """返回保存耗时统计。"""
        return {
            "by_status": {
                status: bucket.stats()
                for status, bucket in self._save_duration.items()
            },
            "conflicts_total": self._conflicts_total,
            "failures_total": self._save_failures_total,
        }

    def get_summary(self) -> dict:
        """返回完整指标摘要（供 admin 端点消费）。"""
        return {
            "render_config": self.get_render_config_stats(),
            "renderer_invocations": self.get_renderer_invocations(),
            "save": self.get_save_stats(),
        }

    def reset(self) -> None:
        """重置所有指标（测试用）。"""
        self._render_config_duration.clear()
        self._renderer_invocations.clear()
        self._save_duration.clear()
        self._conflicts_total = 0
        self._save_failures_total = 0


# 进程级单例
wp_metrics = WpMetricsCollector()
