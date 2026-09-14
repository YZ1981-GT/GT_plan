"""Performance_Profile / Rate_Limit_Profile schema + measurement-mode 限流（Task 13 / 组件 C15）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 14.1：Performance_Profile 以 6000 并发已认证用户为目标负载。
  - 14.6：6000 并发容量测试后，依据测量结果确定每用户/每项目/每 Entry_Family 阈值。
  - 14.7/14.8：Rate_Limit_Profile 以可版本化配置保存阈值；系统仅从 profile 读取阈值。
  - 14.9：以 6000 并发容量结果替代固定 10 RPS 基线（**本模块绝不出现固定 10 RPS/任何预设业务阈值**）。
  - 14.10/14.11/14.12：超阈 429 + 有效 Retry-After；阈内不限流照常判定。
  - 14.16：Performance_Profile 以可版本化配置固定 ramp/项目分布/速率/数据规模/动作组合/持续方式。
  - 14.17：产生验收证据时记录 Performance_Profile 版本、Rate_Limit_Profile 版本、配置摘要与结果。
  - 14.18：资源无关 429（仅 principal/project/family），不表明资源存在性。
Design: 组件 C15 / Property 19（Rate profiles require measured capacity evidence）。

**measurement-mode（本任务默认）**：无容量证据时 Rate_Limit_Profile **inert**——只观测、绝不限流，
也绝不预设任何阈值。真实阈值冻结与 6000 并发容量验收由 Task 17 用 ``freeze_rate_limit_profile``
依据 ``CapacityReport``（含 hash）生成 **frozen + 引用容量报告 hash** 的激活 profile。

**激活门（Property 19 核心）**：``RateLimitProfile.is_active`` 当且仅当 ``frozen is True`` 且
``capacity_report_hash`` 非空且与来源 ``CapacityReport`` 内容 hash 一致。任一缺失 → inert → 永不限流。

``MeasurementModeRateLimiter`` 实现 gate 的 ``RateLimiter`` 协议（同步、纯内存、无 DB），可直接注入
``resolve_wp_binding_and_access`` 的 rate_limiter seam；inert 时行为等价 ``NullRateLimiter``。
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Mapping
from uuid import UUID

from app.services.wp_visibility.perf_metrics import VisibilityMetrics, get_metrics

__all__ = [
    "PerformanceProfile",
    "CapacityReport",
    "RateLimitProfile",
    "RateLimitProfileError",
    "measurement_only_profile",
    "freeze_rate_limit_profile",
    "MeasurementModeRateLimiter",
    "get_default_rate_limiter",
    "reset_default_rate_limiter",
    "TARGET_CONCURRENCY",
]

# 目标并发（Req 14.1）。这是负载目标，不是限流阈值。
TARGET_CONCURRENCY = 6000


def _canonical_hash(payload: object) -> str:
    """规范化 JSON 的 SHA-256（稳定跨进程 / 排序键，用于容量报告与配置摘要）。"""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class RateLimitProfileError(Exception):
    """Rate_Limit_Profile 构造/冻结违反证据约束（缺容量 hash、阈值非正、版本不匹配等）。"""


# ---------------------------------------------------------------------------
# Performance_Profile（负载测试配置；可版本化，Req 14.16）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PerformanceProfile:
    """6000 并发容量测试的可版本化配置（Req 14.1/14.16）。不含任何限流阈值。"""

    version: str
    target_concurrency: int = TARGET_CONCURRENCY
    ramp: str = ""
    project_distribution: str = ""
    request_rate: str = ""
    data_scale: str = ""
    action_mix: Mapping[str, float] = field(default_factory=dict)
    duration: str = ""

    def config_digest(self) -> str:
        """配置摘要 hash（写入 Evidence_Manifest，Req 14.17）。"""
        return _canonical_hash(
            {
                "version": self.version,
                "target_concurrency": self.target_concurrency,
                "ramp": self.ramp,
                "project_distribution": self.project_distribution,
                "request_rate": self.request_rate,
                "data_scale": self.data_scale,
                "action_mix": dict(sorted(self.action_mix.items())),
                "duration": self.duration,
            }
        )


# ---------------------------------------------------------------------------
# Capacity report（6000 并发测量结果；hash 是激活 Rate_Limit_Profile 的唯一证据）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CapacityReport:
    """6000 并发容量测量结果（Task 17 产出）。``content_hash`` 是激活 profile 的证据锚。"""

    performance_profile_version: str
    measured_at: str
    results: Mapping[str, object] = field(default_factory=dict)

    def content_hash(self) -> str:
        return _canonical_hash(
            {
                "performance_profile_version": self.performance_profile_version,
                "measured_at": self.measured_at,
                "results": self.results,
            }
        )


# ---------------------------------------------------------------------------
# Rate_Limit_Profile（可版本化阈值；inert 直到有容量证据，Req 14.7/14.8/14.9）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RateLimitProfile:
    """每用户/每项目/每 Entry_Family 限流阈值（req/window）。

    阈值字典 ``family -> 每窗口最大请求数``。**无预设阈值**：measurement_only 时三者皆空。
    ``is_active`` 需 ``frozen`` 且 ``capacity_report_hash`` 非空——无容量证据永不生效（Property 19）。
    """

    version: str
    window_seconds: float = 1.0
    per_user: Mapping[str, float] = field(default_factory=dict)
    per_project: Mapping[str, float] = field(default_factory=dict)
    per_family: Mapping[str, float] = field(default_factory=dict)
    capacity_report_hash: str | None = None
    source_performance_profile_version: str | None = None
    frozen: bool = False
    created_at: str | None = None

    @property
    def is_active(self) -> bool:
        """当且仅当已冻结且引用了非空容量报告 hash 时才启用限流（Property 19）。"""
        return bool(self.frozen and self.capacity_report_hash)

    def limit_for(self, scope: str, family: str) -> float | None:
        """取某维度（user/project/family）+ family 的阈值；未配置返回 None（该维度不限流）。"""
        table = {
            "user": self.per_user,
            "project": self.per_project,
            "family": self.per_family,
        }.get(scope, {})
        return table.get(family)

    def summary(self) -> dict:
        """写入 Evidence_Manifest 的摘要（Req 14.17）。"""
        return {
            "version": self.version,
            "window_seconds": self.window_seconds,
            "active": self.is_active,
            "frozen": self.frozen,
            "capacity_report_hash": self.capacity_report_hash,
            "source_performance_profile_version": self.source_performance_profile_version,
            "per_user_families": sorted(self.per_user),
            "per_project_families": sorted(self.per_project),
            "per_family_families": sorted(self.per_family),
        }


def measurement_only_profile(version: str = "measurement-0") -> RateLimitProfile:
    """inert 观测-only profile：无任何阈值、未冻结、无容量 hash → 永不限流（Task 13 默认）。"""
    return RateLimitProfile(
        version=version,
        per_user={},
        per_project={},
        per_family={},
        capacity_report_hash=None,
        source_performance_profile_version=None,
        frozen=False,
    )


def freeze_rate_limit_profile(
    *,
    version: str,
    performance_profile: PerformanceProfile,
    capacity_report: CapacityReport,
    per_user: Mapping[str, float] | None = None,
    per_project: Mapping[str, float] | None = None,
    per_family: Mapping[str, float] | None = None,
    window_seconds: float = 1.0,
) -> RateLimitProfile:
    """由 6000 并发容量报告生成 **冻结且激活** 的 Rate_Limit_Profile（Task 17 调用）。

    强约束（Property 19）：
      - ``capacity_report.performance_profile_version`` 必须等于 ``performance_profile.version``。
      - 至少一个维度提供阈值，且全部阈值为正数（不接受 0/负/非数）。
      - profile 携带 ``capacity_report.content_hash()`` 与来源 Performance_Profile 版本，``frozen=True``。
    任何违反抛 ``RateLimitProfileError``（无证据/无阈值绝不产出激活 profile）。
    """
    if capacity_report.performance_profile_version != performance_profile.version:
        raise RateLimitProfileError(
            "capacity report 与 performance profile 版本不一致："
            f"{capacity_report.performance_profile_version!r} != {performance_profile.version!r}"
        )
    per_user = dict(per_user or {})
    per_project = dict(per_project or {})
    per_family = dict(per_family or {})
    if not (per_user or per_project or per_family):
        raise RateLimitProfileError("冻结 Rate_Limit_Profile 必须至少提供一个维度的阈值")
    for scope, table in (("user", per_user), ("project", per_project), ("family", per_family)):
        for fam, limit in table.items():
            if not isinstance(limit, (int, float)) or limit <= 0:
                raise RateLimitProfileError(
                    f"阈值必须为正数：{scope}/{fam}={limit!r}（阈值须由容量测量得出，非预设）"
                )
    if window_seconds <= 0:
        raise RateLimitProfileError("window_seconds 必须为正数")
    return RateLimitProfile(
        version=version,
        window_seconds=window_seconds,
        per_user=per_user,
        per_project=per_project,
        per_family=per_family,
        capacity_report_hash=capacity_report.content_hash(),
        source_performance_profile_version=performance_profile.version,
        frozen=True,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# measurement-mode 限流器（实现 gate RateLimiter 协议；同步、纯内存）
# ---------------------------------------------------------------------------
class MeasurementModeRateLimiter:
    """资源无关限流器：inert profile → 只观测永不限流；激活 profile → 滑窗阈值强制。

    - ``check(principal, project_id, entry_family)`` 恒先记录一次观测（供 Task 17 反推阈值）。
    - inert（``profile.is_active`` False）→ 返回 None（放行，measurement-only；不预设阈值/无 10 RPS）。
    - 激活 → 对 (user,family)/(project,family)/(family) 三维滑窗计数，任一超阈 →
      ``RateLimitDecision(allowed=False, retry_after)``（Retry-After = 窗口剩余秒，min 1）。
    仅用 principal/project/family（Req 14.18 资源无关）。
    """

    def __init__(
        self,
        profile: RateLimitProfile | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        metrics: VisibilityMetrics | None = None,
    ) -> None:
        self.profile = profile or measurement_only_profile()
        self.clock = clock
        self.metrics = metrics or get_metrics()
        # 滑窗时间戳桶：key -> [ts, ...]
        self._buckets: dict[tuple, list[float]] = defaultdict(list)
        # measurement 观测计数：(scope, id, family) -> 总次数（供容量分析）
        self._observations: dict[tuple, int] = defaultdict(int)

    # -- 协议实现 -----------------------------------------------------------
    def check(
        self,
        *,
        principal: UUID | None,
        project_id: UUID | None,
        entry_family: str,
    ):
        from app.services.wp_visibility.wp_bound_gate import RateLimitDecision

        now = self.clock()
        family = entry_family or "unknown"
        dims = (
            ("user", principal, family),
            ("project", project_id, family),
            ("family", None, family),
        )
        # 观测（无论是否激活）——measurement baseline 的原始数据（Task 17 据此定阈值）。
        for scope, ident, fam in dims:
            self._observations[(scope, ident, fam)] += 1

        if not self.profile.is_active:
            return None  # measurement-only：绝不限流，绝不预设阈值。

        window = self.profile.window_seconds
        cutoff = now - window
        limited_retry: float | None = None
        for scope, ident, fam in dims:
            limit = self.profile.limit_for(scope, fam)
            if limit is None:
                continue
            bucket = self._buckets[(scope, ident, fam)]
            # 丢弃窗口外时间戳
            i = 0
            for i, ts in enumerate(bucket):
                if ts > cutoff:
                    break
            else:
                i = len(bucket)
            if i:
                del bucket[:i]
            if len(bucket) >= limit:
                # 超阈：Retry-After = 最老样本离开窗口所需秒（min 1）。
                oldest = bucket[0]
                retry = max(1.0, math.ceil(window - (now - oldest)))
                limited_retry = retry if limited_retry is None else min(limited_retry, retry)
            bucket.append(now)

        if limited_retry is not None:
            self.metrics.record_rate_limited()
            return RateLimitDecision(allowed=False, retry_after=int(limited_retry))
        return None

    # -- 观测导出（Task 17 容量分析用）-------------------------------------
    def observation_snapshot(self) -> dict[str, int]:
        """观测计数快照：``"scope:ident:family" -> count``（供 6000 并发反推阈值）。"""
        return {
            f"{scope}:{ident}:{fam}": n
            for (scope, ident, fam), n in sorted(
                self._observations.items(), key=lambda kv: str(kv[0])
            )
        }

    def reset(self) -> None:
        self._buckets.clear()
        self._observations.clear()


# ---------------------------------------------------------------------------
# 进程内默认限流器（gate seam 生产默认；inert measurement-mode，永不限流）
# ---------------------------------------------------------------------------
_DEFAULT_RATE_LIMITER = MeasurementModeRateLimiter()


def get_default_rate_limiter() -> MeasurementModeRateLimiter:
    """gate 默认注入的 measurement-mode 限流器（Task 17 可 swap 冻结 profile）。"""
    return _DEFAULT_RATE_LIMITER


def reset_default_rate_limiter() -> None:
    """重置默认限流器状态（测试隔离用）。"""
    _DEFAULT_RATE_LIMITER.reset()
    _DEFAULT_RATE_LIMITER.profile = measurement_only_profile()
