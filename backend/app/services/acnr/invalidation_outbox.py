"""ACNR Invalidation Outbox + Dispatcher (R11)

- enqueue(session, project_id, ...): 业务变更**同事务**写一条 outbox 行（R11.2）。
- InvalidationDispatcher: 轮询未投递行 → 递增 Durable_Epoch（同事务）→ broadcast_raw 前端
  + Redis fan-out（经 increment_epoch）→ 标记 dispatched；失败仅 attempts++ 不标 dispatched
  （至少一次投递，R11.3/R11.6）。

投递失败不阻断业务事务提交（R12.3）：outbox 与业务变更同事务提交后，dispatcher 是独立
后台任务，其失败只影响投递重试，不回滚业务变更。
"""
from __future__ import annotations

import asyncio
import logging

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DISPATCH_BATCH = 50
DEFAULT_INTERVAL = 2.0  # 秒；无积压时轮询间隔
# 死信阈值：连续失败 >= MAX 次的行从活跃队列剔除（保留供人工排查），避免毒行每 2s 永久重试
# + 占满 LIMIT 批次槽位阻塞新行（R11.6 至少一次 vs 毒行饥饿的平衡）。
MAX_DISPATCH_ATTEMPTS = 10
# 已投递行保留天数：dispatcher 周期性 prune 删除过期已投递行，防 outbox 表无界增长。
PRUNE_AFTER_DAYS = 7
# 每 N 个 loop 周期跑一次 prune（idle 时约 5 分钟 @ 2s 间隔）。
_PRUNE_EVERY_CYCLES = 150


async def enqueue(
    session: AsyncSession,
    project_id: str,
    *,
    wp_id: str | None = None,
    domain: str | None = None,
) -> None:
    """在调用方事务内写一条 outbox 行（R11.2，与业务变更同事务）。

    不 commit（由调用方事务提交），保证 outbox 行与业务变更原子提交。
    """
    if not project_id:
        return
    await session.execute(
        sa.text(
            "INSERT INTO acnr_invalidation_outbox (id, project_id, wp_id, domain) "
            "VALUES (gen_random_uuid(), CAST(:pid AS uuid), "
            "CAST(:wp AS uuid), :domain)"
        ),
        {
            "pid": str(project_id),
            "wp": str(wp_id) if wp_id else None,
            "domain": domain,
        },
    )
    await session.flush()


async def _dispatch_batch(session: AsyncSession) -> tuple[int, list[dict]]:
    """拉一批未投递行并投递，返回 (处理行数, 待广播 payload 列表)。

    同事务内：increment_epoch(session=session)（DB 递增）+ mark dispatched。
    广播**不在此处发**——收集成功行的 payload 由 run_once 在 **commit 之后** 发送
    （#5：避免事务回滚后仍向客户端广播已回滚的 epoch，导致虚假缓存清除）。

    死信（#4）：SELECT 排除 attempts >= MAX_DISPATCH_ATTEMPTS 的行，毒行不再占用批次
    槽位、不再每轮重试；跨过阈值时告警 + metric，行保留在表中供人工排查。
    """
    rows = (
        await session.execute(
            sa.text(
                "SELECT id, project_id, wp_id, domain, attempts "
                "FROM acnr_invalidation_outbox "
                "WHERE dispatched_at IS NULL AND attempts < :max "
                "ORDER BY created_at "
                "FOR UPDATE SKIP LOCKED LIMIT :lim"
            ),
            {"lim": DISPATCH_BATCH, "max": MAX_DISPATCH_ATTEMPTS},
        )
    ).fetchall()
    if not rows:
        return 0, []

    from app.services.acnr.cache_epoch import increment_epoch

    broadcasts: list[dict] = []
    for r in rows:
        rid = r[0]
        pid = str(r[1])
        wp_id = str(r[2]) if r[2] else None
        domain = r[3]
        attempts = int(r[4] or 0)
        try:
            # 递增 Durable_Epoch（同事务 session）→ 与 mark-dispatched 原子提交
            epoch = await increment_epoch(pid, session=session)
            # 广播延后到 commit 之后（#5）；此处仅收集 payload
            broadcasts.append(
                {"project_id": pid, "wp_id": wp_id, "domain": domain, "epoch": epoch}
            )
            await session.execute(
                sa.text(
                    "UPDATE acnr_invalidation_outbox "
                    "SET dispatched_at = now(), attempts = attempts + 1 "
                    "WHERE id = :id"
                ),
                {"id": rid},
            )
        except Exception as exc:
            # 至少一次：不标 dispatched，仅 attempts++，下轮重试（R11.6）
            new_attempts = attempts + 1
            logger.warning(
                "acnr outbox dispatch failed id=%s (attempt %d/%d): %s",
                rid, new_attempts, MAX_DISPATCH_ATTEMPTS, exc,
            )
            await session.execute(
                sa.text(
                    "UPDATE acnr_invalidation_outbox "
                    "SET attempts = attempts + 1 WHERE id = :id"
                ),
                {"id": rid},
            )
            # #4：跨过死信阈值 → 告警 + metric（行将从后续 SELECT 中被排除）
            if new_attempts >= MAX_DISPATCH_ATTEMPTS:
                logger.error(
                    "acnr outbox row id=%s DEAD-LETTERED after %d attempts "
                    "(project=%s domain=%s) — excluded from active dispatch, kept for inspection",
                    rid, new_attempts, pid, domain,
                )
                _record_deadletter_metric(pid, domain)
    return len(rows), broadcasts


def _record_deadletter_metric(project_id: str, domain: str | None) -> None:
    """记录 outbox 死信 metric（#4，best-effort）。"""
    try:
        from app.services.acnr.metrics import get_acnr_metrics

        get_acnr_metrics().record_fallback(
            f"outbox dead-letter project={project_id} domain={domain}",
            domain="invalidation_outbox",
        )
    except Exception:
        pass


async def prune_dispatched(
    session: AsyncSession, older_than_days: int = PRUNE_AFTER_DAYS
) -> int:
    """删除 older_than_days 之前的已投递行（#3：防 outbox 表无界增长）。返回删除行数。"""
    res = await session.execute(
        sa.text(
            "DELETE FROM acnr_invalidation_outbox "
            "WHERE dispatched_at IS NOT NULL "
            "AND dispatched_at < now() - make_interval(days => :d)"
        ),
        {"d": older_than_days},
    )
    return res.rowcount or 0


class InvalidationDispatcher:
    """后台 dispatcher：轮询 outbox → 至少一次投递。"""

    def __init__(self, interval: float = DEFAULT_INTERVAL) -> None:
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def run_once(self) -> int:
        """处理一批未投递行，返回处理行数（供测试直接驱动）。

        #5：epoch 递增 + mark dispatched 在事务内提交后，才向前端 broadcast_raw
        （commit 失败/回滚则不广播，避免虚假缓存清除）。
        """
        from app.core.database import async_session

        async with async_session() as s:
            try:
                n, broadcasts = await _dispatch_batch(s)
                await s.commit()
            except Exception:
                await s.rollback()
                raise

        # ── commit 之后广播（#5，best-effort，不影响已提交的 epoch/dispatched）──
        if broadcasts:
            from app.services.event_bus import event_bus

            for b in broadcasts:
                try:
                    event_bus.broadcast_raw("acnr:invalidate", b)
                except Exception as exc:
                    logger.warning("acnr outbox post-commit broadcast failed: %s", exc)
        return n

    async def run_prune(self) -> int:
        """删除过期已投递行（#3，best-effort，独立短事务）。返回删除行数。"""
        from app.core.database import async_session

        async with async_session() as s:
            try:
                n = await prune_dispatched(s)
                await s.commit()
                if n:
                    logger.info("acnr outbox pruned %d dispatched rows", n)
                return n
            except Exception as exc:
                await s.rollback()
                logger.warning("acnr outbox prune failed: %s", exc)
                return 0

    async def _loop(self) -> None:
        cycles = 0
        while True:
            try:
                processed = await self.run_once()
                cycles += 1
                # #3：周期性 prune 已投递旧行（idle 时约每 5 分钟）
                if cycles % _PRUNE_EVERY_CYCLES == 0:
                    await self.run_prune()
                # 有积压则立即继续排空；无积压才睡
                if processed == 0:
                    await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                logger.info("acnr InvalidationDispatcher cancelled, exiting")
                return
            except Exception as exc:
                logger.warning("acnr InvalidationDispatcher loop error: %s", exc)
                await asyncio.sleep(self._interval)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("acnr InvalidationDispatcher started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None


_dispatcher = InvalidationDispatcher()


def get_dispatcher() -> InvalidationDispatcher:
    return _dispatcher
