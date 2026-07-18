"""性能与安全观测指标（Task 13 / 组件 C15 Cache/Rate/Perf）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 14.2/14.3：底稿列表延迟 p95 ≤ 2s、单资源 gate 延迟 p95 ≤ 1s（本模块提供延迟直方图与 p95）。
  - 14.4：预期成功请求错误率 ≤ 1%（成功/错误计数）。
  - 14.5：越权请求"错误允许数"= 0（``error_allow`` 计数；任何越权被放行都应 +1，验收须恒 0）。
  - 14.13/14.14/14.15/14.21：权限缓存 1 秒内收敛；cache hit/miss、stale-deny（缓存失效/传播失败
    时 fail-closed 重取或拒绝）计数。
  - 9.9：拒绝 reason 分布（与 ``DenialReason`` 取值域一致）。
Design: 组件 C15 / "Load, frontend and evidence"（先 measurement baseline，指标供 Task 17 冻结阈值）。

**measurement mode 定位**：本模块只"观测"，不"限流"、不"预设阈值"。冻结阈值与最终 6000 并发容量
验收由 Task 17 依据这里采集的 measurement 结果生成 ``Rate_Limit_Profile``（见 rate_limit_profile.py）。

进程内单实例（``get_metrics()``），单进程 async 无需锁；``reset_metrics()`` 供测试隔离。
percentile 用 nearest-rank，空样本返回 0.0。
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator

__all__ = [
    "VisibilityMetrics",
    "percentile",
    "get_metrics",
    "reset_metrics",
    "measure",
]


def percentile(values: list[float], q: float) -> float:
    """nearest-rank 百分位（``q`` ∈ [0,100]）；空样本返回 0.0。"""
    if not values:
        return 0.0
    q = max(0.0, min(100.0, float(q)))
    ordered = sorted(values)
    if q <= 0:
        return ordered[0]
    # nearest-rank: rank = ceil(q/100 * N)（tail latency 不得被 floor 低估）。
    n = len(ordered)
    rank = math.ceil((q / 100.0) * n)
    if rank < 1:
        rank = 1
    if rank > n:
        rank = n
    return ordered[rank - 1]


@dataclass
class VisibilityMetrics:
    """可见性隔离运行观测指标（延迟 / 查询数 / 缓存 / 拒绝 reason / 错误允许数）。"""

    # 延迟样本（秒）
    gate_latencies: list[float] = field(default_factory=list)
    list_latencies: list[float] = field(default_factory=list)
    # 每次授权判定的 DB 查询数（用于证明无 per-wp N+1）
    query_counts: list[int] = field(default_factory=list)
    # 缓存
    cache_hit: int = 0
    cache_miss: int = 0
    cache_stale_deny: int = 0
    # 判定结果
    gate_allow: int = 0
    success: int = 0
    error: int = 0
    rate_limited: int = 0
    # 越权被放行数（验收硬指标：必须恒 0，Req 14.5）
    error_allow: int = 0
    # 拒绝 reason 分布（reason 值 → 次数）
    denials: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # ---- 采集 ----
    def observe_gate_latency(self, seconds: float) -> None:
        self.gate_latencies.append(float(seconds))

    def observe_list_latency(self, seconds: float) -> None:
        self.list_latencies.append(float(seconds))

    def observe_query_count(self, n: int) -> None:
        self.query_counts.append(int(n))

    def record_cache_hit(self) -> None:
        self.cache_hit += 1

    def record_cache_miss(self) -> None:
        self.cache_miss += 1

    def record_cache_stale_deny(self) -> None:
        """缓存过期/传播失败 → fail-closed 重取或拒绝（Req 14.15/14.21）计数。"""
        self.cache_stale_deny += 1

    def record_gate_allow(self) -> None:
        self.gate_allow += 1
        self.success += 1

    def record_rate_limited(self) -> None:
        self.rate_limited += 1

    def record_error(self) -> None:
        self.error += 1

    def record_error_allow(self, n: int = 1) -> None:
        """越权请求被错误放行（绝不应发生；验收断言恒 0，Req 14.5）。"""
        self.error_allow += int(n)

    def record_denial(self, reason: str) -> None:
        self.denials[str(reason)] += 1

    # ---- 汇总 ----
    def p95_gate_latency(self) -> float:
        return percentile(self.gate_latencies, 95)

    def p95_list_latency(self) -> float:
        return percentile(self.list_latencies, 95)

    def max_query_count(self) -> int:
        return max(self.query_counts) if self.query_counts else 0

    def error_rate(self) -> float:
        total = self.success + self.error
        return (self.error / total) if total else 0.0

    def snapshot(self) -> dict:
        return {
            "gate_p95_seconds": round(self.p95_gate_latency(), 6),
            "list_p95_seconds": round(self.p95_list_latency(), 6),
            "gate_samples": len(self.gate_latencies),
            "list_samples": len(self.list_latencies),
            "max_query_count": self.max_query_count(),
            "cache_hit": self.cache_hit,
            "cache_miss": self.cache_miss,
            "cache_stale_deny": self.cache_stale_deny,
            "gate_allow": self.gate_allow,
            "success": self.success,
            "error": self.error,
            "error_rate": round(self.error_rate(), 6),
            "rate_limited": self.rate_limited,
            "error_allow": self.error_allow,
            "denials": dict(self.denials),
        }

    def reset(self) -> None:
        self.gate_latencies.clear()
        self.list_latencies.clear()
        self.query_counts.clear()
        self.cache_hit = 0
        self.cache_miss = 0
        self.cache_stale_deny = 0
        self.gate_allow = 0
        self.success = 0
        self.error = 0
        self.rate_limited = 0
        self.error_allow = 0
        self.denials = defaultdict(int)


# 进程内默认单实例
_METRICS = VisibilityMetrics()


def get_metrics() -> VisibilityMetrics:
    return _METRICS


def reset_metrics() -> None:
    _METRICS.reset()


@contextmanager
def measure(observe: Callable[[float], None], *, clock: Callable[[], float] = time.perf_counter) -> Iterator[None]:
    """计时上下文：退出时把耗时（秒）交给 ``observe``（如 ``metrics.observe_gate_latency``）。"""
    start = clock()
    try:
        yield
    finally:
        observe(clock() - start)
