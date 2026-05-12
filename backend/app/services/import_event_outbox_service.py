"""DB-backed outbox for ledger import activation events."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.dataset_models import (
    EventOutboxDLQ,
    ImportEventOutbox,
    OutboxStatus,
)
from app.services.event_bus import event_bus


logger = logging.getLogger(__name__)


class ImportEventOutboxService:
    @staticmethod
    async def enqueue(
        db: AsyncSession,
        *,
        event_type: EventType,
        project_id: UUID,
        year: int | None,
        payload: dict[str, Any] | None = None,
    ) -> ImportEventOutbox:
        item = ImportEventOutbox(
            event_type=event_type.value,
            project_id=project_id,
            year=year,
            payload=payload or {},
            status=OutboxStatus.pending,
        )
        db.add(item)
        await db.flush()
        return item

    @staticmethod
    async def get(db: AsyncSession, outbox_id: UUID) -> ImportEventOutbox | None:
        result = await db.execute(
            sa.select(ImportEventOutbox).where(ImportEventOutbox.id == outbox_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def publish_one(db: AsyncSession, outbox_id: UUID) -> bool:
        item = await ImportEventOutboxService.get(db, outbox_id)
        if item is None or item.status == OutboxStatus.published:
            return False
        try:
            event_extra = dict(item.payload or {})
            event_extra.setdefault("__event_id", str(item.id))
            await event_bus.publish_immediate(EventPayload(
                event_type=EventType(item.event_type),
                project_id=item.project_id,
                year=item.year,
                extra=event_extra,
            ))
            item.status = OutboxStatus.published
            item.published_at = datetime.now(timezone.utc)
            item.last_error = None
            await db.flush()
            return True
        except Exception as exc:
            item.status = OutboxStatus.failed
            item.attempt_count = int(item.attempt_count or 0) + 1
            item.last_error = str(exc)[:1000]
            await db.flush()
            return False

    @staticmethod
    async def replay_pending(
        db: AsyncSession,
        *,
        limit: int = 100,
        max_attempts: int | None = None,
        project_id: UUID | None = None,
        year: int | None = None,
    ) -> dict[str, Any]:
        filters = []
        if project_id is not None:
            filters.append(ImportEventOutbox.project_id == project_id)
        if year is not None:
            filters.append(ImportEventOutbox.year == year)

        where_clause = sa.and_(
            *filters,
            ImportEventOutbox.status.in_([OutboxStatus.pending, OutboxStatus.failed]),
        ) if filters else ImportEventOutbox.status.in_([OutboxStatus.pending, OutboxStatus.failed])
        if max_attempts is not None and max_attempts > 0:
            status_filter = sa.or_(
                ImportEventOutbox.status == OutboxStatus.pending,
                sa.and_(
                    ImportEventOutbox.status == OutboxStatus.failed,
                    ImportEventOutbox.attempt_count < max_attempts,
                ),
            )
            where_clause = sa.and_(*filters, status_filter) if filters else status_filter
        result = await db.execute(
            sa.select(ImportEventOutbox)
            .where(where_clause)
            .order_by(ImportEventOutbox.created_at.asc())
            .limit(max(1, limit))
            .with_for_update(skip_locked=True)
        )
        items = list(result.scalars().all())
        report = {
            "read_count": len(items),
            "published_count": 0,
            "failed_count": 0,
            "last_error": None,
            "skipped_exhausted_count": 0,
            "exhausted_total_count": 0,
            "exhausted_skipped_in_this_run": 0,
            "moved_to_dlq_count": 0,
            "max_attempts": max_attempts if (max_attempts is not None and max_attempts > 0) else None,
        }
        if max_attempts is not None and max_attempts > 0:
            exhausted_result = await db.execute(
                sa.select(sa.func.count())
                .select_from(ImportEventOutbox)
                .where(
                    *filters,
                    ImportEventOutbox.status == OutboxStatus.failed,
                    ImportEventOutbox.attempt_count >= max_attempts,
                )
            )
            exhausted_total = int(exhausted_result.scalar_one() or 0)
            # 统计“本次重放窗口”里因超过重试上限被跳过的数量，避免与全量累计混淆。
            replay_window = (
                sa.select(
                    ImportEventOutbox.status.label("status"),
                    ImportEventOutbox.attempt_count.label("attempt_count"),
                )
                .where(
                    *filters,
                    ImportEventOutbox.status.in_([OutboxStatus.pending, OutboxStatus.failed]),
                )
                .order_by(ImportEventOutbox.created_at.asc())
                .limit(max(1, limit))
                .subquery()
            )
            exhausted_in_window_result = await db.execute(
                sa.select(sa.func.count())
                .select_from(replay_window)
                .where(
                    replay_window.c.status == OutboxStatus.failed,
                    replay_window.c.attempt_count >= max_attempts,
                )
            )
            exhausted_in_window = int(exhausted_in_window_result.scalar_one() or 0)
            report["exhausted_total_count"] = exhausted_total
            report["skipped_exhausted_count"] = exhausted_total
            report["exhausted_skipped_in_this_run"] = exhausted_in_window
        for item in items:
            try:
                item.status = OutboxStatus.pending
                item.attempt_count = int(item.attempt_count or 0) + 1
                event_extra = dict(item.payload or {})
                event_extra.setdefault("__event_id", str(item.id))
                await event_bus.publish_immediate(EventPayload(
                    event_type=EventType(item.event_type),
                    project_id=item.project_id,
                    year=item.year,
                    extra=event_extra,
                ))
                item.status = OutboxStatus.published
                item.published_at = datetime.now(timezone.utc)
                item.last_error = None
                report["published_count"] += 1
            except Exception as exc:
                item.status = OutboxStatus.failed
                item.last_error = str(exc)[:1000]
                report["failed_count"] += 1
                report["last_error"] = str(exc)
                # F45 / Sprint 7.18: 重试 N 次仍失败 → 移入 DLQ
                if (
                    max_attempts is not None
                    and max_attempts > 0
                    and int(item.attempt_count or 0) >= max_attempts
                ):
                    await ImportEventOutboxService._move_to_dlq(db, item, reason=str(exc))
                    report["moved_to_dlq_count"] = (
                        report.get("moved_to_dlq_count", 0) + 1
                    )
        await db.flush()
        return report

    @staticmethod
    async def summary(
        db: AsyncSession,
        *,
        project_id: UUID | None = None,
        year: int | None = None,
        max_attempts: int | None = None,
    ) -> dict[str, Any]:
        filters = []
        if project_id is not None:
            filters.append(ImportEventOutbox.project_id == project_id)
        if year is not None:
            filters.append(ImportEventOutbox.year == year)

        rows = (await db.execute(
            sa.select(ImportEventOutbox.status, sa.func.count())
            .where(*filters)
            .group_by(ImportEventOutbox.status)
        )).all()
        by_status = {status.value if hasattr(status, "value") else str(status): int(count) for status, count in rows}
        recent_failed = (await db.execute(
            sa.select(ImportEventOutbox)
            .where(*filters, ImportEventOutbox.status == OutboxStatus.failed)
            .order_by(ImportEventOutbox.created_at.desc())
            .limit(10)
        )).scalars().all()
        exhausted_failed_count = 0
        if max_attempts is not None and max_attempts > 0:
            exhausted_failed_count = int((await db.execute(
                sa.select(sa.func.count())
                .select_from(ImportEventOutbox)
                .where(
                    *filters,
                    ImportEventOutbox.status == OutboxStatus.failed,
                    ImportEventOutbox.attempt_count >= max_attempts,
                )
            )).scalar_one() or 0)
        return {
            "by_status": by_status,
            "pending_count": by_status.get(OutboxStatus.pending.value, 0),
            "failed_count": by_status.get(OutboxStatus.failed.value, 0),
            "exhausted_failed_count": exhausted_failed_count,
            "max_attempts": max_attempts if (max_attempts is not None and max_attempts > 0) else None,
            "recent_failed": [
                {
                    "id": str(item.id),
                    "event_type": item.event_type,
                    "project_id": str(item.project_id),
                    "year": item.year,
                    "attempt_count": item.attempt_count,
                    "last_error": item.last_error,
                }
                for item in recent_failed
            ],
        }

    # ------------------------------------------------------------------
    # F45 / Sprint 7.18: DLQ (dead letter queue) 相关操作
    # ------------------------------------------------------------------
    @staticmethod
    async def _move_to_dlq(
        db: AsyncSession,
        item: ImportEventOutbox,
        *,
        reason: str,
    ) -> EventOutboxDLQ:
        """把 outbox 行 snapshot 进 DLQ。

        原 outbox 行保留（status=failed + attempt_count），不删除，作为审计痕迹。
        DLQ 行独立保存 payload/attempt_count/failure_reason，方便手动重投。

        调用方负责 flush / commit。
        """
        dlq = EventOutboxDLQ(
            original_event_id=item.id,
            event_type=item.event_type,
            project_id=item.project_id,
            year=item.year,
            payload=item.payload,
            failure_reason=(reason or "")[:2000] if reason else None,
            attempt_count=int(item.attempt_count or 0),
        )
        db.add(dlq)
        try:
            await db.flush()
        except Exception:  # pragma: no cover - flush 失败极少见
            logger.exception(
                "[EventOutboxDLQ] flush failed for outbox_id=%s", item.id
            )
            raise
        logger.warning(
            "[EventOutboxDLQ] moved event to DLQ: "
            "event_type=%s project_id=%s year=%s attempt_count=%s reason=%s",
            item.event_type,
            item.project_id,
            item.year,
            item.attempt_count,
            (reason or "")[:200],
        )
        return dlq

    @staticmethod
    async def dlq_depth(db: AsyncSession) -> int:
        """查询未处理（resolved_at IS NULL）的 DLQ 深度，供 /metrics 消费。"""
        result = await db.execute(
            sa.select(sa.func.count())
            .select_from(EventOutboxDLQ)
            .where(EventOutboxDLQ.resolved_at.is_(None))
        )
        return int(result.scalar_one() or 0)
