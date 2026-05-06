"""Phase 15: 事件总线与补偿队列

发布/消费/幂等/重试/dead-letter 完整闭环。
裁剪/转派/升级等业务动作通过此总线驱动任务树状态变更。
"""
import uuid
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable, Awaitable

from fastapi import HTTPException
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase15_models import TaskEvent
from app.models.phase15_enums import TaskEventStatus
from app.services.trace_event_service import trace_event_service, generate_trace_id

logger = logging.getLogger(__name__)

# 重试退避：1m → 5m → 25m（60 * 5^retry_count 秒）
RETRY_BASE_SECONDS = 60
RETRY_MULTIPLIER = 5


def _idempotency_key(project_id, event_type: str, payload: dict) -> str:
    """幂等键：project_id + event_type + payload->ref_id + payload->version"""
    ref_id = payload.get("ref_id", "")
    version = payload.get("version", "")
    raw = f"{project_id}:{event_type}:{ref_id}:{version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class TaskEventBus:
    """事件总线：发布 → 消费 → 重试 → dead-letter"""

    # 事件处理器注册表
    _handlers: dict[str, Callable] = {}

    @classmethod
    def register_handler(cls, event_type: str, handler: Callable):
        cls._handlers[event_type] = handler

    async def publish(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        event_type: str,
        task_node_id: Optional[uuid.UUID],
        payload: dict,
        trace_id: Optional[str] = None,
    ) -> uuid.UUID:
        """发布事件，幂等：同 payload 返回已有 event_id"""
        if trace_id is None:
            trace_id = generate_trace_id()

        # 幂等检查
        idem_key = _idempotency_key(project_id, event_type, payload)
        stmt = (
            select(TaskEvent)
            .where(TaskEvent.project_id == project_id)
            .where(TaskEvent.event_type == event_type)
            .where(TaskEvent.trace_id.like(f"%{idem_key[-12:]}%"))
            .where(TaskEvent.status.in_([
                TaskEventStatus.queued,
                TaskEventStatus.succeeded,
            ]))
            .limit(1)
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            logger.info(f"[EVENT_BUS] idempotent hit: event_id={existing.id}")
            return existing.id

        event = TaskEvent(
            project_id=project_id,
            event_type=event_type,
            task_node_id=task_node_id,
            payload=payload,
            status=TaskEventStatus.queued,
            trace_id=trace_id,
        )
        db.add(event)
        await db.flush()

        logger.info(f"[EVENT_BUS] published: event_id={event.id} type={event_type} trace={trace_id}")
        return event.id

    async def consume(
        self,
        db: AsyncSession,
        event_id: uuid.UUID,
    ) -> bool:
        """消费事件：执行处理器，失败重试，超限进 dead-letter"""
        stmt = select(TaskEvent).where(TaskEvent.id == event_id)
        result = await db.execute(stmt)
        event = result.scalar_one_or_none()
        if not event:
            logger.error(f"[EVENT_BUS] event not found: {event_id}")
            return False

        if event.status not in (TaskEventStatus.queued, TaskEventStatus.failed):
            logger.warning(f"[EVENT_BUS] skip non-consumable: event_id={event_id} status={event.status}")
            return False

        handler = self._handlers.get(event.event_type)
        if not handler:
            logger.error(f"[EVENT_BUS] no handler for: {event.event_type}")
            event.status = TaskEventStatus.failed
            event.error_message = f"No handler registered for {event.event_type}"
            await db.flush()
            return False

        try:
            await handler(db, event.payload)
            event.status = TaskEventStatus.succeeded
            await db.flush()

            logger.info(f"[EVENT_BUS] consumed ok: event_id={event_id}")
            return True

        except Exception as e:
            event.retry_count += 1
            event.error_message = str(e)[:500]

            if event.retry_count >= event.max_retries:
                event.status = TaskEventStatus.dead_letter
                event.next_retry_at = None
                logger.error(
                    f"[DEAD_LETTER] event_id={event_id} type={event.event_type} "
                    f"retries={event.retry_count} error={e}"
                )
                # 写 trace_events 告警
                try:
                    await trace_event_service.write(
                        db=db,
                        project_id=event.project_id,
                        event_type="event_dead_letter",
                        object_type="task_event",
                        object_id=event.id,
                        actor_id=event.project_id,
                        action=f"dead_letter:{event.event_type}",
                        decision="block",
                        reason_code=event.error_message[:64],
                        trace_id=event.trace_id,
                    )
                except Exception:
                    pass
            else:
                event.status = TaskEventStatus.failed
                delay = RETRY_BASE_SECONDS * (RETRY_MULTIPLIER ** event.retry_count)
                event.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                logger.warning(
                    f"[EVENT_BUS] retry scheduled: event_id={event_id} "
                    f"retry={event.retry_count}/{event.max_retries} "
                    f"next_at={event.next_retry_at}"
                )

            await db.flush()
            return False

    async def replay(
        self,
        db: AsyncSession,
        event_id: uuid.UUID,
        operator_id: uuid.UUID,
        reason_code: str,
    ) -> dict:
        """手动重放：重置 failed/dead_letter 事件"""
        stmt = select(TaskEvent).where(TaskEvent.id == event_id)
        result = await db.execute(stmt)
        event = result.scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=404, detail="TASK_EVENT_NOT_FOUND")

        if event.status not in (TaskEventStatus.failed, TaskEventStatus.dead_letter):
            raise HTTPException(status_code=409, detail={
                "error_code": "TASK_EVENT_NOT_REPLAYABLE",
                "message": f"事件状态 {event.status} 不可重放，仅 failed/dead_letter 可重放",
            })

        old_status = event.status
        event.status = TaskEventStatus.queued
        event.retry_count = 0
        event.next_retry_at = None
        event.error_message = None
        await db.flush()

        trace_id = generate_trace_id()
        await trace_event_service.write(
            db=db,
            project_id=event.project_id,
            event_type="event_replayed",
            object_type="task_event",
            object_id=event.id,
            actor_id=operator_id,
            action=f"replay:{old_status}->queued",
            from_status=old_status,
            to_status=TaskEventStatus.queued,
            reason_code=reason_code,
            trace_id=trace_id,
        )

        return {
            "event_id": str(event.id),
            "status": TaskEventStatus.queued,
            "trace_id": trace_id,
        }

    async def get_pending_retries(self, db: AsyncSession) -> list[TaskEvent]:
        """获取到期需重试的事件"""
        stmt = (
            select(TaskEvent)
            .where(TaskEvent.status == TaskEventStatus.failed)
            .where(TaskEvent.next_retry_at <= datetime.now(timezone.utc))
            .order_by(TaskEvent.next_retry_at.asc())
            .limit(50)
        )
        result = await db.execute(stmt)
        return result.scalars().all()


# 全局单例
task_event_bus = TaskEventBus()
