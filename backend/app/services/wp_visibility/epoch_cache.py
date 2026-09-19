"""持久 policy-epoch 缓存（Task 13 / 组件 C15 Cache/Rate/Perf）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 14.13：权限/委派/scope/角色变更事务提交后，权限缓存 1 秒内反映提交后授权结果。
  - 14.14：委派/权限撤销后，权限缓存 1 秒内拒绝已撤销访问。
  - 14.15：权限缓存缺失/过期/传播失败 → fail-closed 重取权威结果或拒绝，绝不 stale-allow。
  - 14.21：invalidation outbox 提交后投递失败时，通过 **最多 1 秒** 的持久 policy epoch 校验
    发现 stale cache 并重取或拒绝。
Design: 组件 C15 / Property 18（Revocation converges within one second without stale allow）。

**唯一真源 = ``wp_visibility_policy_epoch``（V113，每项目持久单调 epoch）**。缓存条目 key 必含
``user + project + persistent epoch``（本实现再附 ``wp_index`` 精确到底稿，属 key 超集，语义不变）。

**收敛与 fail-closed 三条路径**（缺一不可）：
  1. **outbox → Redis 即时淘汰（快路径）**：DelegationTransaction 同事务递增 epoch + 写
     invalidation outbox；dispatcher 提交后发布到 Redis channel；订阅节点收到即
     ``invalidate(project_id)`` 立刻丢弃该项目 epoch 新鲜度与缓存条目 → 下次请求重读 DB。
  2. **≤1 秒 DB epoch 核对（安全网）**：每节点对每项目最多每 ``epoch_ttl``（默认 1s）核对一次
     DB epoch。即使 Redis/dispatcher 全挂，最坏 stale 窗口 = ``epoch_ttl`` ≤ 1s（Property 18）。
  3. **epoch 不可得 → 不走缓存（fail-closed）**：DB epoch 读取失败时绝不返回缓存条目，直接以
     authoritative loader 现取（非 stale）或由调用方拒绝，绝不 stale-allow（Req 14.15）。

**为何“老 epoch 缓存永不被 allow”**：条目按 ``(user, project, wp_index, epoch)`` 存储并连同其
写入时的 epoch 一并保存；命中判定要求 ``entry_epoch == current_epoch``。撤权→epoch 递增后，
一旦本节点 epoch 新鲜度刷新（Redis 即时或 ≤1s DB 核对），旧 epoch 条目再不匹配 → 强制重取。

约定：纯读 policy_epoch 表；Redis 全程 best-effort（不可用即降级到 DB 安全网）；``clock`` 可注入
（测试用单调假时钟精确验证 ≤1s 收敛）。进程内单实例（``get_epoch_cache()``），单进程 async 无锁。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Hashable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wp_visibility_models import WpVisibilityPolicyEpoch
from app.services.wp_visibility.perf_metrics import VisibilityMetrics, get_metrics

logger = logging.getLogger(__name__)

__all__ = [
    "PersistentEpochCache",
    "EpochUnavailable",
    "get_epoch_cache",
    "reset_epoch_cache",
    "EPOCH_INVALIDATE_CHANNEL_PREFIX",
    "invalidation_channel",
]

# Redis pub-sub channel 前缀（dispatcher 发布 / 节点订阅；outbox→Redis 即时淘汰快路径）。
EPOCH_INVALIDATE_CHANNEL_PREFIX = "wp_visibility:invalidate:"


def invalidation_channel(project_id: UUID | str) -> str:
    """某项目的失效 channel 名。"""
    return f"{EPOCH_INVALIDATE_CHANNEL_PREFIX}{project_id}"


class EpochUnavailable(Exception):
    """持久 policy epoch 无法确定（DB 读取失败）。语义 = fail-closed，禁止使用任何缓存条目。"""


@dataclass
class _EpochFreshness:
    """某项目 epoch 的本地新鲜度快照。"""

    epoch: int
    checked_at: float


@dataclass
class PersistentEpochCache:
    """按 ``(user, project, wp_index, epoch)`` 缓存授权结果的持久 epoch 缓存。

    - ``epoch_ttl_seconds``：DB epoch 核对节流窗口（Property 18 的最坏 stale 上界，默认 1.0s）。
    - ``clock``：单调时钟（默认 ``time.monotonic``；测试注入假时钟验证 ≤1s 收敛）。
    - ``metrics``：观测指标（cache hit/miss/stale-deny，默认进程单实例）。
    """

    epoch_ttl_seconds: float = 1.0
    clock: Callable[[], float] = time.monotonic
    metrics: VisibilityMetrics = field(default_factory=get_metrics)
    _epoch_freshness: dict[UUID, _EpochFreshness] = field(default_factory=dict)
    _entries: dict[tuple, tuple[int, object]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # epoch 读取（≤1s 节流 DB 核对；fail-closed）
    # ------------------------------------------------------------------
    async def current_epoch(self, db: AsyncSession, project_id: UUID) -> int:
        """返回项目当前持久 epoch；对每项目最多每 ``epoch_ttl`` 核对一次 DB。

        DB 读取失败 → 抛 ``EpochUnavailable``（fail-closed，调用方不得使用缓存）。
        缺行（项目从未变更过）视为 epoch=0（合法初值，非失败）。
        """
        now = self.clock()
        fresh = self._epoch_freshness.get(project_id)
        if fresh is not None and (now - fresh.checked_at) < self.epoch_ttl_seconds:
            return fresh.epoch
        try:
            epoch = (
                await db.execute(
                    sa.select(WpVisibilityPolicyEpoch.epoch).where(
                        WpVisibilityPolicyEpoch.project_id == project_id
                    )
                )
            ).scalar_one_or_none()
        except Exception as exc:  # noqa: BLE001 — fail-closed
            logger.warning("epoch_cache: DB epoch 读取失败 project=%s: %s", project_id, exc)
            raise EpochUnavailable(str(project_id)) from exc
        epoch_val = int(epoch) if epoch is not None else 0
        self._epoch_freshness[project_id] = _EpochFreshness(epoch_val, now)
        return epoch_val

    # ------------------------------------------------------------------
    # 快路径：Redis 失效通知 → 立即淘汰
    # ------------------------------------------------------------------
    def invalidate(self, project_id: UUID) -> None:
        """收到某项目 Redis 失效通知（或本地强制）时立即丢弃其 epoch 新鲜度与全部缓存条目。

        下次请求将重读 DB epoch → 立即收敛（快于 ≤1s 安全网）。
        """
        self._epoch_freshness.pop(project_id, None)
        stale_keys = [k for k in self._entries if k[1] == project_id]
        for k in stale_keys:
            self._entries.pop(k, None)

    def invalidate_all(self) -> None:
        """丢弃全部 epoch 新鲜度与缓存条目（Redis 重连后可能错过消息时使用）。"""
        self._epoch_freshness.clear()
        self._entries.clear()

    # ------------------------------------------------------------------
    # 核心：按 epoch 命中或 authoritative 重取（绝不 stale-allow）
    # ------------------------------------------------------------------
    async def get_or_load(
        self,
        db: AsyncSession,
        *,
        user_id: Hashable,
        project_id: UUID,
        wp_index_id: Hashable,
        loader: Callable[[], Awaitable[object]],
    ) -> object:
        """返回缓存授权结果；epoch 变更/不可得时以 ``loader`` 现取 authoritative 结果。

        - epoch 可得且缓存条目 epoch == current_epoch → 命中（cache_hit）。
        - epoch 可得但缓存 epoch != current_epoch → stale，丢弃并重取（stale_deny + miss）。
        - epoch 不可得（``EpochUnavailable``）→ fail-closed：绝不返回缓存，直接 authoritative
          现取（loader 本身即权威、非 stale）并记 stale_deny（Req 14.15/14.21）。
        """
        key = (user_id, project_id, wp_index_id)
        try:
            epoch = await self.current_epoch(db, project_id)
        except EpochUnavailable:
            # fail-closed：不信任任何缓存条目，直接权威重取（非 stale-allow）。
            self.metrics.record_cache_stale_deny()
            return await loader()

        cached = self._entries.get(key)
        if cached is not None:
            if cached[0] == epoch:
                self.metrics.record_cache_hit()
                return cached[1]
            # epoch 已推进（撤权/变更）→ 旧条目永不被 allow。
            self.metrics.record_cache_stale_deny()
            self._entries.pop(key, None)

        self.metrics.record_cache_miss()
        value = await loader()
        self._entries[key] = (epoch, value)
        return value

    # ------------------------------------------------------------------
    # 观测辅助
    # ------------------------------------------------------------------
    def cached_epoch_for(self, project_id: UUID) -> int | None:
        """当前本地记录的项目 epoch 新鲜度值（无则 None），供测试/诊断。"""
        fresh = self._epoch_freshness.get(project_id)
        return fresh.epoch if fresh is not None else None

    def entry_count(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# 进程内默认单实例（生产由 Task 9–11/17 注入到 gate；lifespan 可挂 Redis 订阅调 invalidate）
# ---------------------------------------------------------------------------
_EPOCH_CACHE = PersistentEpochCache()


def get_epoch_cache() -> PersistentEpochCache:
    return _EPOCH_CACHE


def reset_epoch_cache() -> None:
    """清空默认实例（测试隔离用）。"""
    _EPOCH_CACHE.invalidate_all()
