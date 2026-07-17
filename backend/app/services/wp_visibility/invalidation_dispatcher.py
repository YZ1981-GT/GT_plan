"""失效发件箱 → Redis fan-out 分发器与订阅器（Task 13 / 组件 C15 Cache/Rate/Perf）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 14.20：权限/委派/history/scope/角色/项目成员变更在同一 DB 事务内递增 policy epoch 并写
    invalidation outbox（由 ``DelegationTransaction`` 完成，本模块只做 **提交后 fan-out**）。
  - 14.21：invalidation outbox 提交后投递失败时，靠持久 policy epoch 的 ≤1s 校验兜底发现 stale
    并重取或拒绝，绝不 stale-allow。故本分发器 **纯 best-effort**：Redis 不可得即降级为 no-op，
    正确性完全由 ``PersistentEpochCache`` 的 ≤1s DB epoch 安全网保证。
  - 14.14：委派/权限撤销后 ≤1s 内拒绝已撤销访问——Redis fan-out 是加速路径（即时淘汰），
    DB 安全网是收敛上界。
Design: 组件 C15 / Data Models §"wp_visibility_policy_epoch + wp_visibility_invalidation_outbox"
  （"Redis 仅在提交后 fan-out。节点最多缓存 epoch 1 秒，Redis/dispatcher 失败时同步核对 DB 或拒绝，
  禁止 stale allow。"）/ Property 18。

**append-only 约束下的投递跟踪（无 UPDATE）**：``wp_visibility_invalidation_outbox`` 是 append-only
（V113 BEFORE UPDATE/DELETE forbid 触发器），投递跟踪不能改写 ``delivery_state``，改由 **消费方
in-memory checkpoint 游标**（``(created_at, id)`` 高水位）实现。**重复发布是幂等且无害的**
（``invalidate`` 仅丢弃本地缓存 → 下次请求重读 DB epoch），故游标语义只影响 fan-out 延迟，
不影响正确性（即使整段漏发，≤1s DB 安全网仍收敛，绝不 stale-allow）。

**优雅降级铁律（仓库 steering）**：``get_redis()`` 返回 None（Redis 全挂）→ 分发器 ``publish_pending``
返回 0（no-op），订阅器 ``run`` 直接退出；任何 Redis 异常只 warning，绝不冒泡改变授权结果。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wp_visibility_models import WpVisibilityInvalidationOutbox
from app.services.wp_visibility.epoch_cache import (
    EPOCH_INVALIDATE_CHANNEL_PREFIX,
    PersistentEpochCache,
    get_epoch_cache,
    invalidation_channel,
)

logger = logging.getLogger(__name__)

__all__ = [
    "InvalidationDispatcher",
    "handle_invalidation_message",
    "run_invalidation_subscriber",
]


class InvalidationDispatcher:
    """读取 pending 失效 outbox 行并按项目 fan-out 到 Redis（提交后即时淘汰快路径）。

    - append-only outbox → 不改写 delivery_state；用 in-memory ``(created_at, id)`` 高水位游标
      跟踪已发布（重复发布幂等无害）。
    - Redis 不可得 → ``publish_pending`` 返回 0（降级；正确性由 ≤1s DB 安全网保证）。
    - 可选 ``local_cache``：同节点在发布时一并 ``invalidate`` 本地缓存（本进程即时收敛）。
    """

    def __init__(self, *, local_cache: PersistentEpochCache | None = None) -> None:
        self._local_cache = local_cache
        self._cursor_ts: datetime | None = None
        self._seen_ids_at_cursor: set[UUID] = set()

    async def publish_pending(
        self,
        db: AsyncSession,
        redis=None,
        *,
        limit: int = 1000,
    ) -> int:
        """把游标之后的失效行 fan-out 到各项目 Redis channel；返回发布条数。

        ``redis`` 缺省时经 ``get_redis()`` 惰性获取；None → 降级 no-op 返回 0。
        """
        client = redis
        if client is None:
            try:
                from app.core.redis import get_redis

                client = await get_redis()
            except Exception as exc:  # noqa: BLE001 — Redis 获取失败即降级
                logger.warning("invalidation_dispatcher: get_redis 失败，降级 no-op: %s", exc)
                return 0
        if client is None:
            return 0  # Redis 全挂：降级（DB ≤1s 安全网兜底）

        try:
            rows = await self._fetch_pending(db, limit)
        except Exception as exc:  # noqa: BLE001 — 读 outbox 失败不改变授权结果
            logger.warning("invalidation_dispatcher: 读取 outbox 失败: %s", exc)
            return 0

        published = 0
        for project_id, epoch, row_id, created_at in rows:
            # 游标推进：时间戳前进则清空同刻已见集合。
            if self._cursor_ts is None or created_at > self._cursor_ts:
                self._cursor_ts = created_at
                self._seen_ids_at_cursor = set()
            elif created_at == self._cursor_ts and row_id in self._seen_ids_at_cursor:
                continue  # 同刻且已发布 → 跳过（幂等）
            try:
                await client.publish(invalidation_channel(project_id), str(epoch))
            except Exception as exc:  # noqa: BLE001 — 单条发布失败只 warning，继续
                logger.warning(
                    "invalidation_dispatcher: publish 失败 project=%s: %s", project_id, exc
                )
                continue
            self._seen_ids_at_cursor.add(row_id)
            if self._local_cache is not None:
                self._local_cache.invalidate(project_id)  # 同节点即时收敛
            published += 1
        return published

    async def _fetch_pending(
        self, db: AsyncSession, limit: int
    ) -> list[tuple[UUID, int, UUID, datetime]]:
        stmt = sa.select(
            WpVisibilityInvalidationOutbox.project_id,
            WpVisibilityInvalidationOutbox.epoch,
            WpVisibilityInvalidationOutbox.id,
            WpVisibilityInvalidationOutbox.created_at,
        ).order_by(
            WpVisibilityInvalidationOutbox.created_at.asc(),
            WpVisibilityInvalidationOutbox.id.asc(),
        )
        if self._cursor_ts is not None:
            # >= 游标时间戳：同刻新行也纳入（同刻已见集合去重），避免边界漏发。
            stmt = stmt.where(
                WpVisibilityInvalidationOutbox.created_at >= self._cursor_ts
            )
        stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        return [(r[0], int(r[1]), r[2], r[3]) for r in result.all()]


def handle_invalidation_message(cache: PersistentEpochCache, channel: str) -> bool:
    """从失效 channel 名解析 project_id 并淘汰缓存；成功返回 True（纯函数，供订阅器与单测）。

    channel 形如 ``wp_visibility:invalidate:{project_id}``；非本前缀或 project_id 非法 → 返回 False。
    """
    if not channel or not channel.startswith(EPOCH_INVALIDATE_CHANNEL_PREFIX):
        return False
    pid_str = channel[len(EPOCH_INVALIDATE_CHANNEL_PREFIX):]
    try:
        pid = UUID(pid_str)
    except (ValueError, AttributeError):
        return False
    cache.invalidate(pid)
    return True


async def run_invalidation_subscriber(
    cache: PersistentEpochCache | None = None,
    *,
    redis=None,
    stop_event: asyncio.Event | None = None,
) -> None:
    """订阅所有项目失效 channel，收到即淘汰本地缓存（生产由 Task 17 在 lifespan/leader 节点调度）。

    Redis 不可得 → 直接返回（降级，正确性由 ≤1s DB 安全网保证）。异常只 warning，不冒泡。
    """
    cache = cache if cache is not None else get_epoch_cache()
    client = redis
    if client is None:
        try:
            from app.core.redis import get_redis

            client = await get_redis()
        except Exception as exc:  # noqa: BLE001
            logger.warning("invalidation_subscriber: get_redis 失败，退出: %s", exc)
            return
    if client is None:
        logger.info("invalidation_subscriber: Redis 不可用，跳过（DB ≤1s 安全网兜底）")
        return

    pubsub = client.pubsub()
    pattern = f"{EPOCH_INVALIDATE_CHANNEL_PREFIX}*"
    try:
        await pubsub.psubscribe(pattern)
        while stop_event is None or not stop_event.is_set():
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg is None:
                continue
            if msg.get("type") not in ("pmessage", "message"):
                continue
            channel = msg.get("channel")
            if isinstance(channel, bytes):
                channel = channel.decode("utf-8", "ignore")
            handle_invalidation_message(cache, channel or "")
    except asyncio.CancelledError:  # 正常关闭
        raise
    except Exception as exc:  # noqa: BLE001 — 订阅循环异常不冒泡
        logger.warning("invalidation_subscriber: 循环异常退出: %s", exc)
    finally:
        try:
            await pubsub.punsubscribe(pattern)
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass
