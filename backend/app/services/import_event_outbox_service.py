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


#: 业务域自注册的专用派发器（🔴 2026-11-14 解耦，替代原先硬编码的 formula 分支）。
#:
#: 背景：``_deliver`` 里曾内联 "if event_type == FORMULA_CONFIG_CHANGED: import formula 的
#: deliver"——通用 outbox 因此反向依赖 formula_settings，形成
#: ``formula -> import-export`` 与 ``import-export -> formula`` 双向边（domain-boundary 门禁
#: 的两条 forbidden_edge）。问题不在「谁 import 谁」而在**位置**：事件派发是开放扩展点，
#: 通用 outbox 不该知道任何具体业务域。
#:
#: 现语义：域自己调 :func:`register_typed_deliverer` 注册
#: ``event_type -> (async deliverer(db, item, payload) -> None)``；outbox 只查表派发。
#: 没有注册的分支照旧走事件总线（与原先 else 分支一致）。
_TYPED_DELIVERERS: dict[str, Any] = {}


def register_typed_deliverer(event_type: str, deliverer: Any) -> None:
    """注册某事件类型的专用派发器（覆盖事件总线默认派发）。

    ``deliverer`` 签名：``async (db, item: ImportEventOutbox, payload: EventPayload) -> None``。
    各业务域在自己的模块导入期调用本函数（见 formula_settings/outbox.py 底部）。
    """
    _TYPED_DELIVERERS[str(event_type)] = deliverer


def registered_typed_event_types() -> tuple[str, ...]:
    """已注册专用派发器的事件类型（供守卫/诊断断言「注册确实发生」）。"""
    return tuple(sorted(_TYPED_DELIVERERS))


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
    async def _deliver(db: AsyncSession, item: ImportEventOutbox) -> bool:
        """把一条 outbox 行的副作用派发出去（in-process handler 链 + SSE）。

        **唯一派发口**。`publish_one` 与 `replay_pending` 都只经这里，否则
        Requirement 13.3 的 fan-out 闸门会被其中一条路径绕过 —— 那种缺陷从行为上看是
        "服务重启/重试后下游被刷了两遍"，很难归因。

        Returns:
            ``False`` 表示这条事件的副作用**此前已经派发过**，本次按 Requirement 13.3
            跳过（不重复刷新、不重复 after-save、不重复生成 artifact）。``True`` 表示
            本次真的派发了。

        Raises:
            Exception: 派发失败原样上抛，由调用方按 Requirement 13.4 落
                pending/failed/DLQ。抛之前已把派发权归还，重放能重新抢到。

        spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Task 16
        """
        from app.services.workpaper_sync.outbox import (
            DurableEventOutboxService,
            TYPED_EVENT_PAYLOAD_KEY,
        )

        stored_payload = dict(item.payload or {})
        typed = stored_payload.get(TYPED_EVENT_PAYLOAD_KEY)
        if typed is not None:
            payload = EventPayload.model_validate(typed)
            if payload.event_type.value != item.event_type or payload.project_id != item.project_id or payload.year != item.year:
                raise ValueError("耐久事件 envelope 与 outbox 路由字段不一致")
            event_extra = dict(payload.extra or {})
            event_extra.setdefault("__event_id", str(item.id))
            payload = payload.model_copy(update={"extra": event_extra})
        else:
            event_extra = stored_payload
            event_extra.setdefault("__event_id", str(item.id))
            payload = EventPayload(
                event_type=EventType(item.event_type),
                project_id=item.project_id,
                year=item.year,
                extra=event_extra,
            )
        gated = DurableEventOutboxService.is_fanout_gated(item.event_type)
        if gated and not await DurableEventOutboxService.begin_fanout(
            db, event_id=item.id, project_id=item.project_id, year=item.year
        ):
            logger.info(
                "[outbox] fan-out 已消费过，跳过重复派发 outbox_id=%s event_type=%s",
                item.id,
                item.event_type,
            )
            return False
        try:
            # 🔴 2026-11-14：改为查**注册表**派发 —— 通用 outbox 不再 import 任何业务域
            # （原先内联 formula 分支造成 formula <-> import-export 双向依赖）。
            # 域未注册 ⇒ 走事件总线（与原先 else 分支一致，行为不变）。
            deliverer = _TYPED_DELIVERERS.get(str(item.event_type))
            if deliverer is not None:
                await deliverer(db, item, payload)
            else:
                await event_bus.publish_immediate(payload)
        except Exception:
            if gated:
                await DurableEventOutboxService.abort_fanout(db, event_id=item.id)
            raise
        return True

    @staticmethod
    async def publish_one(db: AsyncSession, outbox_id: UUID) -> bool:
        item = await ImportEventOutboxService.get(db, outbox_id)
        if item is None or item.status == OutboxStatus.published:
            return False
        try:
            await ImportEventOutboxService._deliver(db, item)
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
            # Requirement 13.3：本轮有多少行因"副作用已派发过"被闸门跳过。
            "deduplicated_fanout_count": 0,
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
                if not await ImportEventOutboxService._deliver(db, item):
                    # Requirement 13.3 / 13.9：副作用此前已派发过，本轮只把行收敛成
                    # published，并让"去重"这件事在报告里可见（否则运维看到的是
                    # published_count 涨了却没有任何下游动作）。
                    report["deduplicated_fanout_count"] += 1
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
