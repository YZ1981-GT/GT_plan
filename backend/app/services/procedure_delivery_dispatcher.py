"""程序行任务有序投递 dispatcher（Delivery_Outbox → 聚合通知 → at-least-once SSE）。

Feature: procedure-delegation-notification / Task 10
需求：10.1-10.6, 10.9, 13.2, 13.8
Design：C10（ProcedureDeliveryDispatcher）、D8（有序 outbox 与聚合通知分离）
Properties：
  - P29（aggregate version 有序投递）：任意乱序 available 的同 aggregate events，processed
    aggregate_version 严格单调；前一版本失败/在途时后一版本不越序。
    Validates Requirements 10.1/10.2/10.3。
  - P30（Notification 与 SSE 幂等收敛）：每个 event+recipient 最多一条 Notification；重复
    event_id 的 SSE 不造成重复状态动作，最终 API 状态一致。
    Validates Requirements 10.4/10.5/10.6/10.9。

=== 投递语义（Design C10） =====================================================

领取（claim）条件（并发安全，多 dispatcher 不重复领取）：
  - ``aggregate_type = 'procedure_row_task'``、``processed_at IS NULL``、``dead_letter_at IS NULL``。
  - ``available_at`` 已到期（退避控制）。
  - lease 为空或已过期（``lease_expires_at IS NULL OR lease_expires_at < now()``）——支持过期回收。
  - **同 aggregate 仅领取最小未完成 version**：若存在更小 aggregate_version 的 event 仍未
    processed 且未 dead-letter（在途/失败重试中），则本 version 不得越序领取（Req 10.3）。

领取用 ``SELECT ... FOR UPDATE SKIP LOCKED``（PostgreSQL），跨 dispatcher 天然去重；领取后设置
``lease_expires_at`` / ``claimed_by``。

处理（process）单条 event（Design C10 顺序，Req 10.5）：
  1. **独立事务**插入去重 Notification（``ON CONFLICT (event_id, recipient_user_id) DO NOTHING``）并 commit。
  2. 广播含 ``event_id`` 的 SSE（at-least-once）。
  3. **另一独立事务**标记 ``processed_at``。
SSE 失败 → 不标 processed → 退避后重试；Notification dedup 阻止重复（Req 10.4/10.6/10.9）。
超过最大重试 → dead-letter（保留事件供 replay，Req 10.2）。

**领域事务不回滚**：Notification/SSE 失败绝不回滚已提交的领域事务（Req 10.9），event 保持可重试。

批量委派通知聚合（``delegation_batch_id + recipient``）由 Task 11 的聚合投影插入；本 dispatcher
提供 ``NotificationProjection`` 接口，Task 11 可替换默认逐事件投影为批量摘要投影。

约定：dispatcher 显式管理自己的事务（不复用请求 session）；开关
``PROCEDURE_TASK_DISPATCHER_ENABLED=False`` 时停止 claim，但保留全部事件（Req 13.2/13.8）。
"""

from __future__ import annotations

import logging
import os
import socket
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session as async_session_factory
from app.models.core import Notification
from app.services.event_bus import event_bus
from app.services.procedure_task_transition_service import (
    AGGREGATE_PROCEDURE_ROW_TASK,
)

logger = logging.getLogger("procedure_dispatcher")

# 投递调优参数（可用环境变量覆盖，避免 config 频繁改动）。
LEASE_SECONDS = int(os.getenv("PROCEDURE_DISPATCHER_LEASE_SECONDS", "30"))
BATCH_SIZE = int(os.getenv("PROCEDURE_DISPATCHER_BATCH_SIZE", "20"))
MAX_RETRIES = int(os.getenv("PROCEDURE_DISPATCHER_MAX_RETRIES", "5"))
BASE_BACKOFF_SECONDS = float(os.getenv("PROCEDURE_DISPATCHER_BASE_BACKOFF", "2"))
MAX_BACKOFF_SECONDS = float(os.getenv("PROCEDURE_DISPATCHER_MAX_BACKOFF", "300"))

# SSE 事件类型（前端按 event_id LRU 幂等去重后重新拉取任务/未读数，Task 11 F4）。
SSE_EVENT_TYPE = "procedure_task.event"

# 领域 event_type（payload["event_type"]，短名）→ 通知收件人角色。
# 仅这些类型产生逐事件通知；其余（acknowledged/started/cancel/reopen）不生成通知但仍
# 广播 SSE 并标 processed。Task 11 会以 delegation_batch_id 聚合并扩充类型映射。
_RECIPIENT_ASSIGNEE = "assignee"
_RECIPIENT_REVIEWER = "reviewer"
_EVENT_RECIPIENT_RULES: dict[str, str] = {
    "assigned": _RECIPIENT_ASSIGNEE,
    "reassigned": _RECIPIENT_ASSIGNEE,
    "changes_requested": _RECIPIENT_ASSIGNEE,
    "reviewed": _RECIPIENT_ASSIGNEE,
    "submitted": _RECIPIENT_REVIEWER,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _backoff_seconds(retry_count: int) -> float:
    """指数退避（含上限）：retry_count 从 1 起。"""
    delay = BASE_BACKOFF_SECONDS * (2 ** max(0, retry_count - 1))
    return min(delay, MAX_BACKOFF_SECONDS)


def _default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


class NotificationProjection:
    """逐事件通知投影（Task 10 默认实现）。

    Task 11 会插入以 ``delegation_batch_id + recipient_user_id`` 聚合的摘要投影；届时可
    替换 dispatcher 的 ``projection`` 属性，逐任务 history/outbox 仍保留。
    """

    async def project(self, db: AsyncSession, event: dict) -> int:
        """把一条 outbox event 投影为去重 Notification，返回新增通知条数（dedup 命中记 0）。"""
        payload = event.get("payload") or {}
        event_type = payload.get("event_type") or ""
        recipient_role = _EVENT_RECIPIENT_RULES.get(event_type)
        if recipient_role is None:
            return 0

        staff_id = (
            payload.get("assignee_staff_id")
            if recipient_role == _RECIPIENT_ASSIGNEE
            else payload.get("reviewer_staff_id")
        )
        if not staff_id:
            return 0

        # staff → user 归一（无 active user_id 的 staff 不接收通知，Req 5.2）。
        recipient_user_id = await self._resolve_recipient_user(db, staff_id)
        if recipient_user_id is None:
            return 0

        event_id = event.get("idempotency_key") or str(event.get("id"))
        dedup_key = f"{event_id}:{recipient_user_id}"
        task_id = payload.get("task_id")
        metadata = {
            "event_id": event_id,
            "event_type": event_type,
            "task_id": task_id,
            "project_id": payload.get("project_id"),
            "wp_index_id": payload.get("wp_index_id"),
            "wp_id": payload.get("wp_id"),
            "sheet_key": payload.get("sheet_key"),
            "definition_key": payload.get("definition_key"),
            "aggregate_version": event.get("aggregate_version"),
            "delegation_batch_id": (
                str(event["delegation_batch_id"]) if event.get("delegation_batch_id") else None
            ),
        }

        values = {
            "id": uuid.uuid4(),
            "recipient_id": recipient_user_id,
            "recipient_user_id": recipient_user_id,
            "message_type": f"procedure_task.{event_type}",
            "title": self._title_for(event_type),
            "content": None,
            "related_object_type": "procedure_row_task",
            "related_object_id": uuid.UUID(task_id) if task_id else None,
            "is_read": False,
            "event_id": event_id,
            "dedup_key": dedup_key,
            "notification_metadata": metadata,
        }
        stmt = pg_insert(Notification).values(**values)
        # 去重：与 uq_notifications_event_recipient 部分唯一索引谓词一致。
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["event_id", "recipient_user_id"],
            index_where=sa.text("event_id IS NOT NULL AND recipient_user_id IS NOT NULL"),
        )
        result = await db.execute(stmt)
        return int(result.rowcount or 0)

    async def _resolve_recipient_user(self, db: AsyncSession, staff_id) -> uuid.UUID | None:
        row = (
            await db.execute(
                sa.text(
                    "SELECT user_id FROM staff_members "
                    "WHERE id = :sid AND is_deleted = false AND user_id IS NOT NULL"
                ),
                {"sid": staff_id},
            )
        ).first()
        return row[0] if row else None

    @staticmethod
    def _title_for(event_type: str) -> str:
        return {
            "assigned": "程序任务已分配给你",
            "reassigned": "程序任务已转派给你",
            "changes_requested": "程序任务被退回，请修改",
            "reviewed": "程序任务已通过一级复核",
            "submitted": "有程序任务待你复核",
        }.get(event_type, "程序任务通知")


# 聚合摘要通知类型（前后端同步，见 notification_types.py / notificationTypes.ts）。
AGG_MESSAGE_TYPE = "procedure_task.delegation_batch"


class AggregatingNotificationProjection(NotificationProjection):
    """批量委派聚合通知投影（Task 11，Design D8 / C10）。

    - 无 ``delegation_batch_id`` 的 event → 逐事件通知（回退 ``super().project``）。
    - 有 ``delegation_batch_id`` 且命中 recipient 规则 → 按 ``(batch_id, recipient_user_id)``
      聚合为 **一条** 摘要通知：首个事件插入 summary（task_count=1），后续同批同收件人事件
      合并（count+1、追加 task_id），避免批量委派通知风暴（Req 10.7）。
    - 摘要 metadata 保存 ``event_id/batch_id/project/task_count/task_ids/filter``，驱动前端跳转
      （Req 10.8，不从中文 content 解析路由）；``task_event_ids`` 记录底层逐任务 outbox
      idempotency_key，保证 at-least-once 重投递下计数幂等（Req 10.4 / P30 / P31）。

    逐任务 history/outbox 仍由 ``ProcedureTaskTransitionService`` 逐事件保留（N 个 task 委派 →
    N 组 history/outbox），本投影只聚合 **用户可见通知**（P31）。
    """

    _AGG_UPSERT = sa.text(
        """
        INSERT INTO notifications
            (id, recipient_id, recipient_user_id, message_type, title, content,
             related_object_type, related_object_id, is_read, event_id, dedup_key,
             metadata, created_at)
        VALUES
            (:id, :ruid, :ruid, CAST(:mtype AS varchar), CAST(:title AS varchar), NULL,
             'procedure_row_task', NULL, false,
             CAST(:agg_event_id AS varchar), CAST(:dedup_key AS varchar),
             jsonb_build_object(
                'kind', 'delegation_batch',
                'batch_id', CAST(:batch_id AS text),
                'project_id', CAST(:project_id AS text),
                'event_id', CAST(:agg_event_id AS text),
                'recipient_role', CAST(:role AS text),
                'task_count', 1,
                'task_ids', jsonb_build_array(CAST(:task_id AS text)),
                'task_event_ids', jsonb_build_array(CAST(:underlying AS text)),
                'filter', jsonb_build_object(
                    'delegation_batch_id', CAST(:batch_id AS text),
                    'project_id', CAST(:project_id AS text))
             ),
             now())
        ON CONFLICT (event_id, recipient_user_id)
            WHERE event_id IS NOT NULL AND recipient_user_id IS NOT NULL
        DO UPDATE SET
            metadata = CASE
                WHEN jsonb_exists(notifications.metadata->'task_event_ids', CAST(:underlying AS text))
                    THEN notifications.metadata
                ELSE jsonb_set(
                        jsonb_set(
                            jsonb_set(
                                notifications.metadata,
                                '{task_count}',
                                to_jsonb(
                                    COALESCE((notifications.metadata->>'task_count')::int, 0) + 1)
                            ),
                            '{task_ids}',
                            COALESCE(notifications.metadata->'task_ids', '[]'::jsonb)
                                || jsonb_build_array(CAST(:task_id AS text))
                        ),
                        '{task_event_ids}',
                        COALESCE(notifications.metadata->'task_event_ids', '[]'::jsonb)
                            || jsonb_build_array(CAST(:underlying AS text))
                     )
            END,
            is_read = CASE
                WHEN jsonb_exists(notifications.metadata->'task_event_ids', CAST(:underlying AS text))
                    THEN notifications.is_read
                ELSE false
            END,
            read_at = CASE
                WHEN jsonb_exists(notifications.metadata->'task_event_ids', CAST(:underlying AS text))
                    THEN notifications.read_at
                ELSE NULL
            END
        RETURNING (xmax = 0) AS inserted
        """
    )

    async def project(self, db: AsyncSession, event: dict) -> int:
        batch_id = event.get("delegation_batch_id")
        if not batch_id:
            # 非批量领域事件（submit/changes_requested/reviewed 等）→ 逐事件通知
            return await super().project(db, event)

        payload = event.get("payload") or {}
        event_type = payload.get("event_type") or ""
        recipient_role = _EVENT_RECIPIENT_RULES.get(event_type)
        if recipient_role is None:
            return 0

        staff_id = (
            payload.get("assignee_staff_id")
            if recipient_role == _RECIPIENT_ASSIGNEE
            else payload.get("reviewer_staff_id")
        )
        if not staff_id:
            return 0

        recipient_user_id = await self._resolve_recipient_user(db, staff_id)
        if recipient_user_id is None:
            return 0

        underlying = event.get("idempotency_key") or str(event.get("id"))
        batch_str = str(batch_id)
        agg_event_id = f"batch:{batch_str}"
        result = await db.execute(
            self._AGG_UPSERT,
            {
                "id": uuid.uuid4(),
                "ruid": recipient_user_id,
                "mtype": AGG_MESSAGE_TYPE,
                "title": "程序任务批量委派",
                "agg_event_id": agg_event_id,
                "dedup_key": f"{agg_event_id}:{recipient_user_id}",
                "batch_id": batch_str,
                "project_id": str(payload.get("project_id")) if payload.get("project_id") else None,
                "role": recipient_role,
                "task_id": payload.get("task_id"),
                "underlying": underlying,
            },
        )
        row = result.first()
        # 首次插入 summary → 记 1 条新通知；合并/重投递 → 0（每 batch+recipient 至多一条通知）
        return 1 if (row is not None and row[0]) else 0


class ProcedureDeliveryDispatcher:
    """有序 outbox dispatcher：并发 claim lease + 有序投递 + 退避 + dead-letter + replay + 指标。"""

    def __init__(
        self,
        *,
        worker_id: str | None = None,
        lease_seconds: int = LEASE_SECONDS,
        batch_size: int = BATCH_SIZE,
        max_retries: int = MAX_RETRIES,
        projection: NotificationProjection | None = None,
        session_factory=None,
    ):
        self.worker_id = worker_id or _default_worker_id()
        self.lease_seconds = lease_seconds
        self.batch_size = batch_size
        self.max_retries = max_retries
        # Task 11：默认插入聚合投影（批量委派按 batch+recipient 聚合摘要通知，逐任务
        # history/outbox 仍保留）。非批量事件回退逐事件通知。
        self.projection = projection or AggregatingNotificationProjection()
        # 独立事务用的 session 工厂：生产默认全局 async_session；测试可注入 per-loop 工厂
        # 以避免全局引擎连接池跨事件循环复用（RuntimeError: Event loop is closed）。
        self._session_factory = session_factory or async_session_factory

    # ---- claim（并发安全 + 有序 + 过期回收）--------------------------------

    async def claim_batch(self, db: AsyncSession) -> list[dict]:
        """领取一批可投递 event（同 aggregate 只取最小未完成 version）。

        使用 ``FOR UPDATE SKIP LOCKED`` 保证跨 dispatcher 不重复领取；领取后设置 lease/claimed_by。
        调用方负责 commit（router/worker 显式 commit）。
        """
        stmt = sa.text(
            """
            WITH claimable AS (
                SELECT te.id
                FROM task_events te
                WHERE te.aggregate_type = :agg
                  AND te.processed_at IS NULL
                  AND te.dead_letter_at IS NULL
                  AND (te.available_at IS NULL OR te.available_at <= now())
                  AND (te.lease_expires_at IS NULL OR te.lease_expires_at < now())
                  AND NOT EXISTS (
                      SELECT 1 FROM task_events e2
                      WHERE e2.aggregate_type = te.aggregate_type
                        AND e2.aggregate_id = te.aggregate_id
                        AND e2.aggregate_version < te.aggregate_version
                        AND e2.processed_at IS NULL
                        AND e2.dead_letter_at IS NULL
                  )
                ORDER BY te.available_at NULLS FIRST, te.aggregate_id, te.aggregate_version
                LIMIT :batch
                FOR UPDATE SKIP LOCKED
            )
            UPDATE task_events t
            SET lease_expires_at = now() + make_interval(secs => :lease),
                claimed_by = :worker
            FROM claimable c
            WHERE t.id = c.id
            RETURNING t.id, t.project_id, t.aggregate_id, t.aggregate_version,
                      t.event_type, t.idempotency_key, t.payload,
                      t.delegation_batch_id, t.retry_count
            """
        )
        rows = (
            await db.execute(
                stmt,
                {
                    "agg": AGGREGATE_PROCEDURE_ROW_TASK,
                    "batch": self.batch_size,
                    "lease": float(self.lease_seconds),
                    "worker": self.worker_id,
                },
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    # ---- process（独立事务通知 → SSE → 标 processed）------------------------

    async def process_event(self, event: dict) -> str:
        """投递单条 event：通知（独立事务 commit）→ SSE → 标 processed。

        返回 "processed" | "failed" | "dead_letter"。每步用自有 session，绝不复用请求 session。
        """
        event_id = event.get("idempotency_key") or str(event.get("id"))
        try:
            # 1) 独立事务插入去重通知并 commit（Notification dedup 阻止重复）。
            async with self._session_factory() as db:
                await self.projection.project(db, event)
                await db.commit()

            # 2) at-least-once SSE，payload 必含 event_id（前端按 event_id 幂等）。
            self._broadcast_sse(event)

            # 3) 另一独立事务标 processed（清 lease）。
            async with self._session_factory() as db:
                await self._mark_processed(db, event["id"])
                await db.commit()
            return "processed"
        except Exception as exc:  # noqa: BLE001 — 投递失败不回滚领域事务，退避重试/进 dead-letter
            logger.warning(
                "[dispatcher] 投递失败 event=%s type=%s: %s",
                event_id, (event.get("payload") or {}).get("event_type"), exc,
            )
            async with self._session_factory() as db:
                outcome = await self._handle_failure(db, event["id"], str(exc))
                await db.commit()
            return outcome

    def _broadcast_sse(self, event: dict) -> None:
        """广播含 event_id 的 SSE（at-least-once）。失败上抛 → event 重试（Req 10.5/10.9）。"""
        payload = event.get("payload") or {}
        event_id = event.get("idempotency_key") or str(event.get("id"))
        event_bus.broadcast_raw(
            SSE_EVENT_TYPE,
            {
                "project_id": str(event.get("project_id")) if event.get("project_id") else None,
                "event_id": event_id,
                "event_type": payload.get("event_type"),
                "task_id": payload.get("task_id"),
                "aggregate_version": event.get("aggregate_version"),
                "delegation_batch_id": (
                    str(event["delegation_batch_id"]) if event.get("delegation_batch_id") else None
                ),
            },
        )

    async def _mark_processed(self, db: AsyncSession, outbox_id) -> None:
        await db.execute(
            sa.text(
                "UPDATE task_events "
                "SET processed_at = now(), status = 'succeeded', "
                "    lease_expires_at = NULL, claimed_by = NULL "
                "WHERE id = :id AND processed_at IS NULL"
            ),
            {"id": outbox_id},
        )

    async def _handle_failure(self, db: AsyncSession, outbox_id, error: str) -> str:
        """失败处理：超限进 dead-letter，否则退避后释放 lease 供重试。"""
        row = (
            await db.execute(
                sa.text(
                    "SELECT retry_count FROM task_events WHERE id = :id FOR UPDATE"
                ),
                {"id": outbox_id},
            )
        ).first()
        if row is None:
            return "failed"
        retry_count = int(row[0] or 0) + 1
        if retry_count > self.max_retries:
            await db.execute(
                sa.text(
                    "UPDATE task_events "
                    "SET retry_count = :rc, dead_letter_at = now(), status = 'dead_letter', "
                    "    last_error = :err, lease_expires_at = NULL, claimed_by = NULL "
                    "WHERE id = :id"
                ),
                {"rc": retry_count, "err": error[:2000], "id": outbox_id},
            )
            logger.error("[dispatcher] event %s 超过最大重试进入 dead-letter", outbox_id)
            return "dead_letter"
        await db.execute(
            sa.text(
                "UPDATE task_events "
                "SET retry_count = :rc, status = 'failed', last_error = :err, "
                "    available_at = now() + make_interval(secs => :backoff), "
                "    lease_expires_at = NULL, claimed_by = NULL "
                "WHERE id = :id"
            ),
            {
                "rc": retry_count,
                "err": error[:2000],
                "backoff": _backoff_seconds(retry_count),
                "id": outbox_id,
            },
        )
        return "failed"

    # ---- run_once（供 worker 主循环调用）-----------------------------------

    async def run_once(self) -> dict:
        """领取一批并逐条投递。开关关闭时不 claim。返回本轮结果计数。"""
        from app.core.config import settings

        if not getattr(settings, "PROCEDURE_TASK_DISPATCHER_ENABLED", False):
            return {"claimed": 0, "processed": 0, "failed": 0, "dead_letter": 0, "skipped": True}

        async with self._session_factory() as db:
            claimed = await self.claim_batch(db)
            await db.commit()

        counts = {"claimed": len(claimed), "processed": 0, "failed": 0, "dead_letter": 0}
        for event in claimed:
            outcome = await self.process_event(event)
            if outcome == "processed":
                counts["processed"] += 1
            elif outcome == "dead_letter":
                counts["dead_letter"] += 1
            else:
                counts["failed"] += 1
        return counts

    # ---- 指标（backlog / oldest age / lease / 失败 / 延迟 / dead-letter）----

    async def metrics(self, db: AsyncSession) -> dict:
        row = (
            await db.execute(
                sa.text(
                    """
                    SELECT
                        count(*) FILTER (
                            WHERE processed_at IS NULL AND dead_letter_at IS NULL
                        ) AS backlog,
                        count(*) FILTER (
                            WHERE processed_at IS NULL AND dead_letter_at IS NULL
                              AND lease_expires_at IS NOT NULL AND lease_expires_at >= now()
                        ) AS leased,
                        count(*) FILTER (
                            WHERE processed_at IS NULL AND dead_letter_at IS NULL
                              AND retry_count > 0
                        ) AS failing,
                        count(*) FILTER (WHERE dead_letter_at IS NOT NULL) AS dead_letter,
                        count(*) FILTER (WHERE processed_at IS NOT NULL) AS processed,
                        EXTRACT(EPOCH FROM (now() - min(created_at) FILTER (
                            WHERE processed_at IS NULL AND dead_letter_at IS NULL
                        ))) AS oldest_age_seconds
                    FROM task_events
                    WHERE aggregate_type = :agg
                    """
                ),
                {"agg": AGGREGATE_PROCEDURE_ROW_TASK},
            )
        ).mappings().first()
        m = dict(row) if row else {}
        oldest = m.get("oldest_age_seconds")
        return {
            "backlog": int(m.get("backlog") or 0),
            "leased": int(m.get("leased") or 0),
            "failing": int(m.get("failing") or 0),
            "dead_letter": int(m.get("dead_letter") or 0),
            "processed": int(m.get("processed") or 0),
            "oldest_age_seconds": float(oldest) if oldest is not None else 0.0,
        }

    # ---- dead-letter 列表 + replay -----------------------------------------

    async def list_dead_letters(self, db: AsyncSession, project_id) -> list[dict]:
        rows = (
            await db.execute(
                sa.text(
                    """
                    SELECT id, aggregate_id, aggregate_version, event_type,
                           idempotency_key, retry_count, last_error,
                           dead_letter_at, payload
                    FROM task_events
                    WHERE aggregate_type = :agg
                      AND project_id = :pid
                      AND dead_letter_at IS NOT NULL
                    ORDER BY dead_letter_at DESC
                    """
                ),
                {"agg": AGGREGATE_PROCEDURE_ROW_TASK, "pid": project_id},
            )
        ).mappings().all()
        return [
            {
                "id": str(r["id"]),
                "aggregate_id": str(r["aggregate_id"]) if r["aggregate_id"] else None,
                "aggregate_version": r["aggregate_version"],
                "event_type": r["event_type"],
                "idempotency_key": r["idempotency_key"],
                "retry_count": r["retry_count"],
                "last_error": r["last_error"],
                "dead_letter_at": r["dead_letter_at"].isoformat() if r["dead_letter_at"] else None,
                "payload": r["payload"],
            }
            for r in rows
        ]

    async def replay(self, db: AsyncSession, project_id, outbox_id) -> dict:
        """把 dead-letter event 重置为可领取（保留事件、清 dead_letter/lease/backoff）。

        仅允许 replay 本项目、aggregate_type=procedure_row_task 且已 dead-letter 的 event。
        调用方负责 commit。
        """
        row = (
            await db.execute(
                sa.text(
                    "SELECT id, dead_letter_at FROM task_events "
                    "WHERE id = :id AND project_id = :pid AND aggregate_type = :agg "
                    "FOR UPDATE"
                ),
                {"id": outbox_id, "pid": project_id, "agg": AGGREGATE_PROCEDURE_ROW_TASK},
            )
        ).first()
        if row is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="event 不存在或不属于本项目")
        if row[1] is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=409, detail="event 未处于 dead-letter，无需 replay")

        await db.execute(
            sa.text(
                "UPDATE task_events "
                "SET dead_letter_at = NULL, processed_at = NULL, retry_count = 0, "
                "    last_error = NULL, available_at = now(), "
                "    lease_expires_at = NULL, claimed_by = NULL, status = 'queued' "
                "WHERE id = :id"
            ),
            {"id": outbox_id},
        )
        return {"id": str(outbox_id), "status": "requeued"}
