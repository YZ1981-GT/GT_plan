"""耐久 AI 批任务状态机、认领租约和迟到结果围栏。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_task_job_models import AiTaskItem, AiTaskJob

TERMINAL_ITEM = frozenset({"succeeded", "failed", "cancelled"})
TERMINAL_JOB = frozenset({"succeeded", "partial_failed", "failed", "cancelled"})


class AiTaskJobConflict(ValueError):
    pass


class AiTaskJobNotFound(LookupError):
    pass


@dataclass(frozen=True)
class AiTaskTarget:
    target_type: str
    target_id: UUID
    target_key: str | None = None
    payload: dict[str, Any] | None = None
    baseline_version: str | None = None
    before_hash: str | None = None


@dataclass(frozen=True)
class AiTaskClaim:
    item_id: UUID
    job_id: UUID
    project_id: UUID
    year: int
    task_kind: str
    actor_id: UUID
    target_type: str
    target_id: UUID
    target_key: str | None
    generation_id: UUID
    request_payload: dict[str, Any]
    request_hash: str
    baseline_version: str | None
    before_hash: str | None
    attempt: int
    max_attempts: int
    lease_seconds: int
    lease_token: UUID


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def create_or_get_job(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    task_kind: str,
    actor_id: UUID,
    idempotency_key: str,
    request_payload: dict[str, Any],
    targets: Iterable[AiTaskTarget],
) -> tuple[AiTaskJob, bool]:
    """原子创建 job；同 key 同请求返回原 job，不同请求拒绝。"""
    if not idempotency_key:
        raise ValueError("idempotency_key 不得为空")
    target_rows = list(targets)
    request_hash = canonical_hash(request_payload)
    now = datetime.now(timezone.utc)
    values = {
        "id": uuid4(), "project_id": project_id, "year": year,
        "task_kind": task_kind, "actor_id": actor_id,
        "idempotency_key": idempotency_key, "request_hash": request_hash,
        "request_payload": request_payload,
        "status": "queued" if target_rows else "succeeded",
        "progress_total": len(target_rows), "version": 1,
        "finished_at": None if target_rows else now,
        "updated_at": now,
    }
    dialect = db.get_bind().dialect.name
    insert_fn = pg_insert if dialect == "postgresql" else sqlite_insert
    stmt = insert_fn(AiTaskJob).values(**values).on_conflict_do_nothing(
        index_elements=[
            AiTaskJob.actor_id, AiTaskJob.project_id,
            AiTaskJob.task_kind, AiTaskJob.idempotency_key,
        ]
    ).returning(AiTaskJob.id)
    inserted_id = (await db.execute(stmt)).scalar_one_or_none()
    created = inserted_id is not None
    job = (
        await db.execute(
            sa.select(AiTaskJob).where(
                AiTaskJob.id == inserted_id if created else sa.and_(
                    AiTaskJob.actor_id == actor_id,
                    AiTaskJob.project_id == project_id,
                    AiTaskJob.task_kind == task_kind,
                    AiTaskJob.idempotency_key == idempotency_key,
                )
            )
        )
    ).scalar_one()
    if job.request_hash != request_hash:
        raise AiTaskJobConflict("同一幂等键已用于不同请求")
    if created:
        for ordinal, target in enumerate(target_rows):
            payload = target.payload or {}
            db.add(AiTaskItem(
                job_id=job.id, ordinal=ordinal,
                target_type=target.target_type, target_id=target.target_id,
                target_key=target.target_key, generation_id=uuid4(),
                baseline_version=target.baseline_version,
                before_hash=target.before_hash,
                request_hash=canonical_hash(payload), request_payload=payload,
            ))
        await db.flush()
    return job, created


async def get_job_snapshot(db: AsyncSession, *, project_id: UUID, job_id: UUID) -> dict[str, Any]:
    job = (
        await db.execute(sa.select(AiTaskJob).where(
            AiTaskJob.id == job_id, AiTaskJob.project_id == project_id,
        ))
    ).scalar_one_or_none()
    if job is None:
        raise AiTaskJobNotFound("AI 批任务不存在")
    items = list((await db.execute(sa.select(AiTaskItem).where(
        AiTaskItem.job_id == job.id
    ).order_by(AiTaskItem.ordinal))).scalars().all())
    return {
        "job_id": str(job.id), "project_id": str(job.project_id),
        "year": job.year, "task_kind": job.task_kind, "status": job.status,
        "version": int(job.version or 0), "progress_total": job.progress_total,
        "progress_done": job.progress_done, "failed_count": job.failed_count,
        "cancelled_count": job.cancelled_count,
        "cancel_requested": job.cancel_requested_at is not None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "items": [
            {
                "item_id": str(item.id), "ordinal": item.ordinal,
                "target_type": item.target_type, "target_id": str(item.target_id),
                "target_key": item.target_key, "status": item.status,
                "generation_id": str(item.generation_id),
                "message_id": str(item.message_id) if item.message_id else None,
                "attempt_count": item.attempt_count,
                "max_attempts": item.max_attempts,
                "next_attempt_at": item.next_attempt_at.isoformat() if item.next_attempt_at else None,
                "baseline_version": item.baseline_version,
                "before_hash": item.before_hash,
                "started_at": item.started_at.isoformat() if item.started_at else None,
                "finished_at": item.finished_at.isoformat() if item.finished_at else None,
                "result": item.result_summary, "error_code": item.error_code,
                "error_message": item.error_message,
            }
            for item in items
        ],
    }


async def _settle_expired_terminal_items(
    db: AsyncSession, *, now: datetime
) -> bool:
    """收口一个无法再认领的过期 job，避免 running/cancelling 永久卡住。"""
    terminal_expired = sa.and_(
        AiTaskItem.status == "running",
        AiTaskItem.lease_expires_at.is_not(None),
        AiTaskItem.lease_expires_at <= now,
        sa.or_(
            AiTaskJob.cancel_requested_at.is_not(None),
            AiTaskItem.attempt_count >= AiTaskItem.max_attempts,
        ),
    )
    stmt = (
        sa.select(AiTaskJob)
        .join(AiTaskItem, AiTaskItem.job_id == AiTaskJob.id)
        .where(terminal_expired, ~AiTaskJob.status.in_(TERMINAL_JOB))
        .order_by(AiTaskJob.created_at)
        .limit(1)
    )
    if db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True, of=AiTaskJob)
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job is None:
        return False

    cancelled = job.cancel_requested_at is not None
    values: dict[str, Any] = {
        "status": "cancelled" if cancelled else "failed",
        "lease_owner": None,
        "lease_token": None,
        "lease_expires_at": None,
        "next_attempt_at": None,
        "finished_at": now,
        "updated_at": now,
    }
    if cancelled:
        values.update(error_code=None, error_message=None)
    else:
        values.update(
            error_code="lease_expired_attempts_exhausted",
            error_message="worker 租约过期且重试次数已耗尽",
        )
    await db.execute(
        sa.update(AiTaskItem)
        .where(
            AiTaskItem.job_id == job.id,
            AiTaskItem.status == "running",
            AiTaskItem.lease_expires_at.is_not(None),
            AiTaskItem.lease_expires_at <= now,
            sa.or_(
                job.cancel_requested_at is not None,
                AiTaskItem.attempt_count >= AiTaskItem.max_attempts,
            ),
        )
        .values(**values)
    )
    await aggregate_job(db, job.id)
    return True


async def claim_next(
    db: AsyncSession, *, worker_id: str, lease_seconds: int = 300
) -> AiTaskClaim | None:
    """认领一项；PG 用 SKIP LOCKED，完成时以随机 lease_token 围栏。"""
    now = datetime.now(timezone.utc)
    # 先清理取消后遗留或已耗尽重试次数的过期租约。一次调用最多收口
    # 100 个 job，避免异常积压阻塞后续正常任务，又不给单轮查询无界工作量。
    for _ in range(100):
        if not await _settle_expired_terminal_items(db, now=now):
            break
    claimable = sa.or_(
        sa.and_(
            AiTaskItem.status.in_(["queued", "retry_wait"]),
            sa.or_(AiTaskItem.next_attempt_at.is_(None), AiTaskItem.next_attempt_at <= now),
        ),
        sa.and_(AiTaskItem.status == "running", AiTaskItem.lease_expires_at <= now),
    )
    stmt = (
        sa.select(AiTaskItem, AiTaskJob)
        .join(AiTaskJob, AiTaskJob.id == AiTaskItem.job_id)
        .where(
            claimable,
            AiTaskItem.attempt_count < AiTaskItem.max_attempts,
            AiTaskJob.cancel_requested_at.is_(None),
            ~AiTaskJob.status.in_(TERMINAL_JOB),
        )
        .order_by(AiTaskJob.created_at, AiTaskItem.ordinal)
        .limit(1)
    )
    if db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True, of=AiTaskItem)
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    item, job = row
    token = uuid4()
    attempt = int(item.attempt_count or 0) + 1
    previous_status = item.status
    result = await db.execute(
        sa.update(AiTaskItem)
        .where(
            AiTaskItem.id == item.id,
            AiTaskItem.status == previous_status,
            AiTaskItem.attempt_count == item.attempt_count,
        )
        .values(
            status="running", attempt_count=attempt,
            lease_owner=worker_id, lease_token=token,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            next_attempt_at=None, started_at=sa.func.coalesce(AiTaskItem.started_at, now),
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        return None
    if job.status == "queued":
        job.status = "running"
        job.started_at = job.started_at or now
        job.version = int(job.version or 0) + 1
    await db.flush()
    return AiTaskClaim(
        item.id, job.id, job.project_id, job.year, job.task_kind, job.actor_id,
        item.target_type, item.target_id, item.target_key, item.generation_id,
        dict(item.request_payload or {}), item.request_hash,
        item.baseline_version, item.before_hash,
        attempt, int(item.max_attempts or 1), max(1, lease_seconds), token,
    )


async def renew_lease(
    db: AsyncSession,
    claim: AiTaskClaim,
    *,
    lease_seconds: int = 300,
) -> bool:
    """延长当前 claimant 的租约；取消、重领或终态均返回 False。"""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        sa.update(AiTaskItem)
        .where(
            AiTaskItem.id == claim.item_id,
            AiTaskItem.status == "running",
            AiTaskItem.lease_token == claim.lease_token,
            AiTaskItem.attempt_count == claim.attempt,
            sa.exists(
                sa.select(AiTaskJob.id).where(
                    AiTaskJob.id == AiTaskItem.job_id,
                    AiTaskJob.cancel_requested_at.is_(None),
                    ~AiTaskJob.status.in_(TERMINAL_JOB),
                )
            ),
        )
        .values(
            lease_expires_at=now + timedelta(seconds=max(1, lease_seconds)),
            updated_at=now,
        )
    )
    await db.flush()
    return result.rowcount == 1


async def _lock_job_for_completion(db: AsyncSession, claim: AiTaskClaim) -> bool:
    stmt = sa.select(AiTaskJob).where(AiTaskJob.id == claim.job_id)
    if db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    job = (await db.execute(stmt)).scalar_one_or_none()
    return bool(
        job is not None
        and job.cancel_requested_at is None
        and job.status not in TERMINAL_JOB
    )


async def finish_success(
    db: AsyncSession,
    claim: AiTaskClaim,
    *,
    result_summary: dict[str, Any],
    message_id: UUID | None = None,
) -> bool:
    if not await _lock_job_for_completion(db, claim):
        return False
    now = datetime.now(timezone.utc)
    result = await db.execute(sa.update(AiTaskItem).where(
        AiTaskItem.id == claim.item_id,
        AiTaskItem.status == "running",
        AiTaskItem.lease_token == claim.lease_token,
        AiTaskItem.attempt_count == claim.attempt,
    ).values(
        status="succeeded", result_summary=result_summary, message_id=message_id,
        lease_owner=None, lease_token=None, lease_expires_at=None,
        error_code=None, error_message=None, finished_at=now, updated_at=now,
    ))
    if result.rowcount != 1:
        return False
    await aggregate_job(db, claim.job_id)
    return True


async def finish_failure(
    db: AsyncSession,
    claim: AiTaskClaim,
    *,
    error_code: str,
    error_message: str,
    retryable: bool,
) -> bool:
    if not await _lock_job_for_completion(db, claim):
        return False
    now = datetime.now(timezone.utc)
    terminal = not retryable or claim.attempt >= claim.max_attempts
    status = "failed" if terminal else "retry_wait"
    due = None if terminal else now + timedelta(seconds=min(900, 60 * claim.attempt))
    result = await db.execute(sa.update(AiTaskItem).where(
        AiTaskItem.id == claim.item_id,
        AiTaskItem.status == "running",
        AiTaskItem.lease_token == claim.lease_token,
        AiTaskItem.attempt_count == claim.attempt,
    ).values(
        status=status, next_attempt_at=due,
        lease_owner=None, lease_token=None, lease_expires_at=None,
        error_code=error_code, error_message=error_message[:2000],
        finished_at=now if terminal else None, updated_at=now,
    ))
    if result.rowcount != 1:
        return False
    await aggregate_job(db, claim.job_id)
    return True


async def aggregate_job(db: AsyncSession, job_id: UUID) -> None:
    stmt = sa.select(AiTaskJob).where(AiTaskJob.id == job_id)
    if db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job is None:
        return
    counts = dict((await db.execute(
        sa.select(AiTaskItem.status, sa.func.count()).where(
            AiTaskItem.job_id == job_id
        ).group_by(AiTaskItem.status)
    )).all())
    total = sum(int(v) for v in counts.values())
    done = sum(int(counts.get(s, 0)) for s in TERMINAL_ITEM)
    failed = int(counts.get("failed", 0))
    cancelled = int(counts.get("cancelled", 0))
    active = int(counts.get("running", 0)) + int(counts.get("queued", 0)) + int(counts.get("retry_wait", 0))
    if active:
        status = "cancelling" if job.cancel_requested_at else "running"
        finished = None
    elif total == 0:
        status, finished = "succeeded", datetime.now(timezone.utc)
    elif cancelled == total:
        status, finished = "cancelled", datetime.now(timezone.utc)
    elif failed == total:
        status, finished = "failed", datetime.now(timezone.utc)
    elif failed or cancelled:
        status, finished = "partial_failed", datetime.now(timezone.utc)
    else:
        status, finished = "succeeded", datetime.now(timezone.utc)
    job.progress_total = total
    job.progress_done = done
    job.failed_count = failed
    job.cancelled_count = cancelled
    job.status = status
    job.finished_at = finished
    job.version = int(job.version or 0) + 1
    job.updated_at = datetime.now(timezone.utc)
    await db.flush()


async def request_cancel(db: AsyncSession, *, project_id: UUID, job_id: UUID) -> dict[str, Any]:
    job = (
        await db.execute(sa.select(AiTaskJob).where(
            AiTaskJob.id == job_id, AiTaskJob.project_id == project_id,
        ).with_for_update())
    ).scalar_one_or_none()
    if job is None:
        raise AiTaskJobNotFound("AI 批任务不存在")
    if job.status in TERMINAL_JOB:
        return await get_job_snapshot(db, project_id=project_id, job_id=job_id)
    now = datetime.now(timezone.utc)
    job.cancel_requested_at = job.cancel_requested_at or now
    await db.execute(sa.update(AiTaskItem).where(
        AiTaskItem.job_id == job.id,
        AiTaskItem.status.in_(["queued", "retry_wait", "running"]),
    ).values(
        status="cancelled", next_attempt_at=None,
        lease_owner=None, lease_token=None, lease_expires_at=None,
        error_code=None, error_message=None,
        finished_at=now, updated_at=now,
    ))
    await aggregate_job(db, job.id)
    return await get_job_snapshot(db, project_id=project_id, job_id=job_id)


async def retry_item(
    db: AsyncSession, *, project_id: UUID, job_id: UUID, item_id: UUID
) -> dict[str, Any]:
    row = (
        await db.execute(sa.select(AiTaskItem, AiTaskJob).join(
            AiTaskJob, AiTaskJob.id == AiTaskItem.job_id
        ).where(
            AiTaskItem.id == item_id, AiTaskItem.job_id == job_id,
            AiTaskJob.project_id == project_id,
        ).with_for_update())
    ).first()
    if row is None:
        raise AiTaskJobNotFound("AI 批任务明细不存在")
    item, job = row
    if item.status != "failed":
        raise AiTaskJobConflict("仅失败明细可以重试；成功结果不会重新生成")
    if job.cancel_requested_at is not None or job.status == "cancelled":
        raise AiTaskJobConflict("已取消的任务不能重试，请重新发起")
    item.status = "queued"
    # 人工重试开启新的重试预算，但 generation_id 保持不变，用户采纳的仍是
    # 这一个逻辑目标，不会因 transport 重试生成第二个身份。
    item.attempt_count = 0
    item.next_attempt_at = None
    item.finished_at = None
    item.result_summary = None
    item.message_id = None
    item.error_code = None
    item.error_message = None
    job.status = "running"
    job.finished_at = None
    job.version = int(job.version or 0) + 1
    await db.flush()
    return await get_job_snapshot(db, project_id=project_id, job_id=job_id)
