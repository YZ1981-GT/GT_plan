"""事务性 outbox / inbox 机制（Task 3.1, Wave 2）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R9, R12
Design: §3.1 信任边界(§6 同事务), §5.4 stale/统一图, §7.1 outbox/inbox 幂等
Properties: P25 (审计事件覆盖 — 同事务)

- **outbox**：与业务变化 + command-root 审计 **同事务** 写入（facade 保证）；按 ``event_id``
  幂等（``ON CONFLICT DO NOTHING``），worker 稍后读取并发布（外部 I/O 不占长事务，
  design §3.1）。有界抖动退避 + dead-letter（``compute_backoff`` 复用 command_audit）。
- **inbox**：按 ``event_id`` 幂等消费，避免重复副作用（P14/P25 语义支撑）。

不 commit：本 service 只 ``add/flush``（facade 管理短事务边界）。事件 payload 只放脱敏可
JSON 化数据，不放凭据/绝对路径/附件原文。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence_governance_models import EvidenceInbox, EvidenceOutbox
from app.services.evidence_governance.command_audit import (
    compute_backoff,
    next_attempt_at,
    redact_audit_metadata,
)
from app.services.evidence_governance.frozen_contracts import ActorContext, content_hash_of


def derive_event_id(
    *, command_root_id: uuid.UUID | str, event_type: str, seq: int = 0
) -> str:
    """从 (command_root_id, event_type, seq) 派生确定性 event_id（重放幂等）。"""
    return content_hash_of(
        {"root": str(command_root_id), "type": event_type, "seq": seq}
    )[:120]


def _actor_columns(actor: ActorContext) -> dict:
    return {
        "actor_type": actor.actor_type.value,
        "actor_user_id": actor.actor_user_id,
        "actor_service_identity_id": actor.actor_service_identity_id,
    }


class OutboxService:
    """事务性 outbox：按 event_id 幂等 enqueue + 有界退避 + dead-letter。只 flush。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def enqueue(
        self,
        *,
        project_id: uuid.UUID,
        audit_year: int | None,
        event_id: str,
        event_type: str,
        payload: dict,
        actor: ActorContext,
        command_root_id: uuid.UUID | None = None,
    ) -> bool:
        """幂等入队；返回 True=新增，False=已存在（重放不重复）。

        payload 经 ``redact_audit_metadata`` 脱敏后落库（防凭据/路径/原文外泄）。
        """
        vals = {
            "id": uuid.uuid4(),
            "project_id": project_id,
            "audit_year": audit_year,
            "event_id": event_id,
            "event_type": event_type,
            "payload": redact_audit_metadata(payload),
            "status": "pending",
            "attempt_count": 0,
            "command_root_id": command_root_id,
            **_actor_columns(actor),
        }
        ins = (
            pg_insert(EvidenceOutbox.__table__)
            .values(**vals)
            .on_conflict_do_nothing(index_elements=["event_id"])
            .returning(EvidenceOutbox.__table__.c.id)
        )
        inserted = (await self._db.execute(ins)).scalar()
        await self._db.flush()
        return inserted is not None

    async def claim_pending(self, *, limit: int = 50) -> list[EvidenceOutbox]:
        """认领 due 的 pending 行（``FOR UPDATE SKIP LOCKED``），置为 processing。

        供 outbox worker 使用；只 flush，事务由 worker 管理。
        """
        now = datetime.now(timezone.utc)
        t = EvidenceOutbox
        stmt = (
            sa.select(t)
            .where(
                t.status == "pending",
                sa.or_(t.next_attempt_at.is_(None), t.next_attempt_at <= now),
            )
            .order_by(t.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list((await self._db.execute(stmt)).scalars().all())
        for row in rows:
            row.status = "processing"
        await self._db.flush()
        return rows

    async def mark_done(self, row: EvidenceOutbox) -> None:
        row.status = "done"
        row.updated_at = datetime.now(timezone.utc)
        await self._db.flush()

    async def mark_failed(self, row: EvidenceOutbox, *, max_attempts: int = 8) -> str:
        """失败重排：attempt+1；超上限进 dead_letter，否则回 pending 并设退避 next_attempt_at。

        返回新状态（``pending`` / ``dead_letter``）。
        """
        row.attempt_count = (row.attempt_count or 0) + 1
        row.updated_at = datetime.now(timezone.utc)
        if row.attempt_count >= max_attempts:
            row.status = "dead_letter"
        else:
            row.status = "pending"
            row.next_attempt_at = next_attempt_at(row.attempt_count)
        await self._db.flush()
        return row.status


class InboxService:
    """inbox：按 event_id 幂等消费，避免重复副作用。只 flush。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def register(
        self,
        *,
        project_id: uuid.UUID,
        audit_year: int | None,
        event_id: str,
        event_type: str,
        actor: ActorContext,
    ) -> bool:
        """登记入站事件；返回 True=首次（应处理），False=已存在（跳过副作用）。"""
        vals = {
            "id": uuid.uuid4(),
            "project_id": project_id,
            "audit_year": audit_year,
            "event_id": event_id,
            "event_type": event_type,
            "status": "received",
            **_actor_columns(actor),
        }
        ins = (
            pg_insert(EvidenceInbox.__table__)
            .values(**vals)
            .on_conflict_do_nothing(index_elements=["event_id"])
            .returning(EvidenceInbox.__table__.c.id)
        )
        inserted = (await self._db.execute(ins)).scalar()
        await self._db.flush()
        return inserted is not None

    async def is_processed(self, event_id: str) -> bool:
        t = EvidenceInbox
        row = (
            await self._db.execute(
                sa.select(t.status).where(t.event_id == event_id).limit(1)
            )
        ).scalar_one_or_none()
        return row == "processed"

    async def mark_processed(self, event_id: str) -> None:
        t = EvidenceInbox
        await self._db.execute(
            sa.update(t)
            .where(t.event_id == event_id)
            .values(status="processed", processed_at=datetime.now(timezone.utc))
        )
        await self._db.flush()

    async def mark_dead_letter(self, event_id: str) -> None:
        t = EvidenceInbox
        await self._db.execute(
            sa.update(t).where(t.event_id == event_id).values(status="dead_letter")
        )
        await self._db.flush()


__all__ = [
    "OutboxService",
    "InboxService",
    "derive_event_id",
    "compute_backoff",
]
