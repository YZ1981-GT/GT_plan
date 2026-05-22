"""SLA 超时检查 Worker — 每 15 分钟检查一次 + 每 30 秒写心跳

需求 10.1/10.3/10.5：从 main.py lifespan 中拆出 `_sla_check_loop`，
使用独立的 async 会话避免与请求连接池竞争。

R10 Spec C Sprint 1.1.2：每 30s 写心跳到 Redis（不阻断主检查间隔）。

Phase 5 F6: SLA 前置预警（Requirements 6.1, 6.2, 6.5, 6.6）
- 查询 IssueTicket.due_at 在 (now, now+24h] → 黄色预警
- 查询 IssueTicket.due_at 在 (now, now+8h] → 橙色预警
- 幂等去重：Redis key `sla:prewarning:{ticket_id}:{level}` TTL=24h
- Redis 不可用时降级（允许重复通知，宁多勿漏）
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.worker_helpers import write_heartbeat

logger = logging.getLogger("sla_check")

INTERVAL_SECONDS = 900  # 15 分钟主检查间隔
HEARTBEAT_INTERVAL_SECONDS = 30
PREWARNING_REDIS_TTL = 86400  # 24h


async def run(stop_event: asyncio.Event) -> None:
    """SLA 超时检查主循环。

    - 每 30s 写一次心跳（不依赖业务检查节奏）
    - 每 15 分钟做一次 SLA 检查 + 前置预警检查
    - stop_event.set() 后退出循环
    """
    last_check_at = 0.0
    loop_count = 0
    while not stop_event.is_set():
        # 每轮先写心跳
        await write_heartbeat("sla_worker")

        # 计算距离上次 check 还剩多久
        loop_count += 1
        elapsed = loop_count * HEARTBEAT_INTERVAL_SECONDS

        if elapsed >= INTERVAL_SECONDS:
            try:
                from app.core.database import async_session
                from app.services.issue_ticket_service import issue_ticket_service
                async with async_session() as db:
                    escalated = await issue_ticket_service.check_sla_timeout(db)
                    if escalated:
                        await db.commit()
                        logger.info("[SLA] auto-escalated %d issues", len(escalated))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[SLA] check loop error: %s", e)

            # Phase 5 F6: 前置预警检查
            try:
                from app.core.database import async_session
                async with async_session() as db:
                    warned_count = await _check_prewarning(db)
                    if warned_count:
                        await db.commit()
                        logger.info("[SLA] prewarning sent %d notifications", warned_count)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[SLA] prewarning check error: %s", e)

            loop_count = 0  # 重置计数

        # 等待 30s 或 stop_event
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)
            break
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            break


# ---------------------------------------------------------------------------
# Phase 5 F6: 前置预警逻辑
# ---------------------------------------------------------------------------


async def _check_prewarning(db: AsyncSession) -> int:
    """检查即将超时的问题单（IssueTicket），生成前置预警通知。

    Requirements: 6.1, 6.2, 6.5

    - due_at 在 (now, now+8h] → 橙色预警（orange）
    - due_at 在 (now+8h, now+24h] → 黄色预警（yellow）
    - 幂等去重：Redis key `sla:prewarning:{ticket_id}:{level}` TTL=24h
    - Redis 不可用时降级为不去重（宁多勿漏）
    """
    from app.core.redis import get_redis
    from app.models.phase15_models import IssueTicket

    now = datetime.now(timezone.utc)
    t_8h = now + timedelta(hours=8)
    t_24h = now + timedelta(hours=24)

    # Query tickets approaching deadline (open/in_fix status only)
    stmt = (
        select(IssueTicket)
        .where(
            IssueTicket.status.in_(["open", "in_fix"]),
            IssueTicket.due_at.isnot(None),
            IssueTicket.due_at > now,
            IssueTicket.due_at <= t_24h,
        )
    )
    result = await db.execute(stmt)
    tickets = result.scalars().all()

    if not tickets:
        return 0

    redis = await get_redis()
    warned_count = 0

    for ticket in tickets:
        # Determine warning level
        if ticket.due_at <= t_8h:
            level = "orange"
        else:
            level = "yellow"

        # Idempotent dedup via Redis
        redis_key = f"sla:prewarning:{ticket.id}:{level}"
        should_send = True

        if redis is not None:
            try:
                existing = await redis.get(redis_key)
                if existing:
                    should_send = False
            except Exception as e:
                logger.warning("[SLA] Redis get failed for %s: %s", redis_key, e)
                # Degrade: allow duplicate (宁多勿漏)

        if not should_send:
            continue

        # Send notification
        remaining_hours = (ticket.due_at - now).total_seconds() / 3600
        await _send_prewarning_notification(
            db=db,
            ticket=ticket,
            level=level,
            remaining_hours=remaining_hours,
        )

        # Mark in Redis (idempotent)
        if redis is not None:
            try:
                await redis.set(redis_key, "1", ex=PREWARNING_REDIS_TTL)
            except Exception as e:
                logger.warning("[SLA] Redis set failed for %s: %s", redis_key, e)

        warned_count += 1

    return warned_count


async def _send_prewarning_notification(
    db: AsyncSession,
    ticket,
    level: str,
    remaining_hours: float,
) -> None:
    """写入预警通知到 NotificationCenter + audit_log。

    Requirements: 6.3, 6.4
    """
    from app.models.core import Notification

    # Build notification content
    remaining_str = f"{remaining_hours:.1f}h"
    title = f"SLA 预警（{level}）：问题单即将超时"
    content = (
        f"问题单 [{ticket.title}] 距截止时间仅剩 {remaining_str}，"
        f"请及时处理。责任人：{ticket.owner_id}"
    )

    # Push to project manager (owner_id is the responsible person)
    notification = Notification(
        recipient_id=ticket.owner_id,
        message_type="sla_prewarning",
        title=title,
        content=content,
        related_object_type="issue_ticket",
        related_object_id=ticket.id,
    )
    db.add(notification)

    # Write to audit_log for observability
    logger.info(
        "[SLA-PREWARNING] ticket_id=%s level=%s remaining=%.1fh owner=%s project=%s",
        ticket.id,
        level,
        remaining_hours,
        ticket.owner_id,
        ticket.project_id,
    )


async def resolve_prewarning_for_ticket(
    db: AsyncSession,
    ticket_id: UUID,
) -> int:
    """当问题单状态变为 resolved/closed 时，标记对应预警为已解决。

    Requirements: 6.6

    Returns the number of notifications marked as resolved.
    """
    from app.models.core import Notification

    # Mark all sla_prewarning notifications for this ticket as read
    stmt = (
        update(Notification)
        .where(
            Notification.related_object_type == "issue_ticket",
            Notification.related_object_id == ticket_id,
            Notification.message_type == "sla_prewarning",
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    result = await db.execute(stmt)

    # Also clear Redis keys if available
    from app.core.redis import get_redis
    redis = await get_redis()
    if redis is not None:
        for level in ("yellow", "orange"):
            redis_key = f"sla:prewarning:{ticket_id}:{level}"
            try:
                await redis.delete(redis_key)
            except Exception as e:
                logger.warning("[SLA] Redis delete failed for %s: %s", redis_key, e)

    resolved_count = result.rowcount  # type: ignore[attr-defined]
    if resolved_count:
        logger.info(
            "[SLA-PREWARNING] resolved %d notifications for ticket %s",
            resolved_count,
            ticket_id,
        )

    return resolved_count
