"""通用耐久任务：幂等创建、DB 租约、attempt 围栏、恢复与取消。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_job_models import PlatformJob, PlatformJobAttempt

TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


class PlatformJobConflict(ValueError):
    pass


class PlatformJobCapacityExceeded(PlatformJobConflict):
    pass


class PlatformJobNotFound(ValueError):
    pass


@dataclass(frozen=True)
class PlatformJobClaim:
    job_id: UUID
    operation: str
    project_id: UUID
    actor_id: UUID
    payload_ref: dict[str, Any]
    attempt: int
    max_attempts: int
    lease_token: UUID
    lease_seconds: int


def canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def _db_now(db: AsyncSession) -> datetime:
    value = (await db.execute(sa.select(sa.func.now()))).scalar_one()
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def create_or_get_job(
    db: AsyncSession,
    *,
    operation: str,
    project_id: UUID,
    actor_id: UUID,
    idempotency_key: str,
    payload_ref: dict[str, Any],
    request_payload: dict[str, Any] | None = None,
    progress_total: int = 0,
    reserved_bytes: int = 0,
    max_attempts: int = 3,
) -> tuple[PlatformJob, bool]:
    """原子创建；同键同请求返回原任务，不同请求拒绝。"""
    key = idempotency_key.strip()
    if not key:
        raise ValueError("idempotency_key 不得为空")
    if not operation.strip():
        raise ValueError("operation 不得为空")
    request_hash = canonical_hash(
        payload_ref if request_payload is None else request_payload
    )
    values = {
        "id": uuid4(),
        "operation": operation,
        "project_id": project_id,
        "actor_id": actor_id,
        "idempotency_key": key,
        "request_hash": request_hash,
        "payload_ref": payload_ref,
        "progress_total": max(0, int(progress_total)),
        "reserved_bytes": max(0, int(reserved_bytes)),
        "max_attempts": max(1, int(max_attempts)),
        "status": "queued",
        "version": 1,
    }
    dialect = db.get_bind().dialect.name
    insert_fn = pg_insert if dialect == "postgresql" else sqlite_insert
    statement = (
        insert_fn(PlatformJob)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=[
                PlatformJob.actor_id,
                PlatformJob.project_id,
                PlatformJob.operation,
                PlatformJob.idempotency_key,
            ]
        )
        .returning(PlatformJob.id)
    )
    inserted_id = (await db.execute(statement)).scalar_one_or_none()
    created = inserted_id is not None
    job = (
        await db.execute(
            sa.select(PlatformJob).where(
                PlatformJob.id == inserted_id
                if created
                else sa.and_(
                    PlatformJob.actor_id == actor_id,
                    PlatformJob.project_id == project_id,
                    PlatformJob.operation == operation,
                    PlatformJob.idempotency_key == key,
                )
            )
        )
    ).scalar_one()
    if job.request_hash != request_hash:
        raise PlatformJobConflict("同一幂等键已用于不同请求")
    return job, created


async def _settle_exhausted(db: AsyncSession, now: datetime) -> None:
    """过期且耗尽的 running 任务直接收口，不能永久卡住。"""
    rows = (
        await db.execute(
            sa.select(PlatformJob)
            .where(
                PlatformJob.status == "running",
                PlatformJob.lease_expires_at <= now,
                PlatformJob.attempt_count >= PlatformJob.max_attempts,
            )
            .limit(100)
        )
    ).scalars().all()
    for job in rows:
        old_token = job.lease_token
        job.status = "cancelled" if job.cancel_requested_at else "failed"
        job.error_code = None if job.cancel_requested_at else "attempts_exhausted"
        job.error_message = (
            None
            if job.cancel_requested_at
            else "worker 租约过期且重试次数已耗尽"
        )
        job.lease_owner = None
        job.lease_token = None
        job.lease_expires_at = None
        job.finished_at = now
        job.updated_at = now
        job.version = int(job.version or 0) + 1
        if old_token is not None:
            await db.execute(
                sa.update(PlatformJobAttempt)
                .where(
                    PlatformJobAttempt.lease_token == old_token,
                    PlatformJobAttempt.status == "running",
                )
                .values(
                    status="lost_lease",
                    finished_at=now,
                    error_code="lease_expired",
                    error_message="租约过期且任务已收口",
                )
            )


async def claim_next(
    db: AsyncSession,
    *,
    worker_id: str,
    lease_seconds: int = 300,
) -> PlatformJobClaim | None:
    """认领一个 queued/retry_wait/过期 running 任务。"""
    now = await _db_now(db)
    await _settle_exhausted(db, now)
    claimable = sa.or_(
        PlatformJob.status == "queued",
        sa.and_(
            PlatformJob.status == "retry_wait",
            sa.or_(
                PlatformJob.next_attempt_at.is_(None),
                PlatformJob.next_attempt_at <= now,
            ),
        ),
        sa.and_(
            PlatformJob.status == "running",
            PlatformJob.lease_expires_at <= now,
        ),
    )
    statement = (
        sa.select(PlatformJob)
        .where(
            claimable,
            PlatformJob.cancel_requested_at.is_(None),
            PlatformJob.attempt_count < PlatformJob.max_attempts,
        )
        .order_by(PlatformJob.queued_at, PlatformJob.id)
        .limit(1)
    )
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    job = (await db.execute(statement)).scalar_one_or_none()
    if job is None:
        return None

    previous_status = job.status
    previous_attempt = int(job.attempt_count or 0)
    previous_token = job.lease_token
    attempt = previous_attempt + 1
    token = uuid4()
    lease = max(1, int(lease_seconds))
    conditions = [
        PlatformJob.id == job.id,
        PlatformJob.status == previous_status,
        PlatformJob.attempt_count == previous_attempt,
        PlatformJob.cancel_requested_at.is_(None),
    ]
    if previous_status == "running":
        conditions.extend(
            [
                PlatformJob.lease_token == previous_token,
                PlatformJob.lease_expires_at <= now,
            ]
        )
    result = await db.execute(
        sa.update(PlatformJob)
        .execution_options(synchronize_session=False)
        .where(*conditions)
        .values(
            status="running",
            attempt_count=attempt,
            next_attempt_at=None,
            lease_owner=worker_id,
            lease_token=token,
            lease_expires_at=now + timedelta(seconds=lease),
            heartbeat_at=now,
            started_at=sa.func.coalesce(PlatformJob.started_at, now),
            updated_at=now,
            version=PlatformJob.version + 1,
        )
    )
    if result.rowcount != 1:
        return None
    if previous_token is not None:
        await db.execute(
            sa.update(PlatformJobAttempt)
            .where(
                PlatformJobAttempt.lease_token == previous_token,
                PlatformJobAttempt.status == "running",
            )
            .values(
                status="lost_lease",
                finished_at=now,
                error_code="lease_expired",
                error_message="租约过期，已由新 worker 接管",
            )
        )
    db.add(
        PlatformJobAttempt(
            job_id=job.id,
            attempt_no=attempt,
            lease_token=token,
            worker_id=worker_id,
            status="running",
            started_at=now,
        )
    )
    await db.flush()
    return PlatformJobClaim(
        job_id=job.id,
        operation=job.operation,
        project_id=job.project_id,
        actor_id=job.actor_id,
        payload_ref=dict(job.payload_ref or {}),
        attempt=attempt,
        max_attempts=int(job.max_attempts or 1),
        lease_token=token,
        lease_seconds=lease,
    )


def _claim_filter(claim: PlatformJobClaim):
    return sa.and_(
        PlatformJob.id == claim.job_id,
        PlatformJob.status == "running",
        PlatformJob.attempt_count == claim.attempt,
        PlatformJob.lease_token == claim.lease_token,
    )


async def renew_lease(db: AsyncSession, claim: PlatformJobClaim) -> bool:
    now = await _db_now(db)
    result = await db.execute(
        sa.update(PlatformJob)
        .execution_options(synchronize_session=False)
        .where(
            _claim_filter(claim),
            PlatformJob.cancel_requested_at.is_(None),
        )
        .values(
            lease_expires_at=now + timedelta(seconds=claim.lease_seconds),
            heartbeat_at=now,
            updated_at=now,
        )
    )
    return result.rowcount == 1


async def update_progress(
    db: AsyncSession,
    claim: PlatformJobClaim,
    *,
    current: int,
    total: int | None = None,
    message: str | None = None,
    stage: str | None = None,
) -> bool:
    """只允许当前 claimant 写进度；current 在乱序回调下保持单调。"""
    now = await _db_now(db)
    bounded = max(0, int(current))
    values: dict[str, Any] = {
        "progress_current": sa.case(
            (PlatformJob.progress_current > bounded, PlatformJob.progress_current),
            else_=bounded,
        ),
        "heartbeat_at": now,
        "updated_at": now,
        "version": PlatformJob.version + 1,
    }
    if total is not None:
        bounded_total = max(0, int(total))
        values["progress_total"] = sa.case(
            (
                PlatformJob.progress_total > bounded_total,
                PlatformJob.progress_total,
            ),
            else_=bounded_total,
        )
    if message is not None:
        values["progress_message"] = sa.case(
            (
                PlatformJob.progress_current > bounded,
                PlatformJob.progress_message,
            ),
            else_=message[:2000],
        )
    if stage is not None:
        values["stage"] = sa.case(
            (PlatformJob.progress_current > bounded, PlatformJob.stage),
            else_=stage[:64],
        )
    result = await db.execute(
        sa.update(PlatformJob)
        .execution_options(synchronize_session=False)
        .where(
            _claim_filter(claim),
            PlatformJob.cancel_requested_at.is_(None),
        )
        .values(**values)
    )
    return result.rowcount == 1


async def cancellation_requested(
    db: AsyncSession,
    claim: PlatformJobClaim,
) -> bool:
    row = (
        await db.execute(
            sa.select(PlatformJob.cancel_requested_at).where(
                PlatformJob.id == claim.job_id,
                PlatformJob.attempt_count == claim.attempt,
                PlatformJob.lease_token == claim.lease_token,
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def finish_success(
    db: AsyncSession,
    claim: PlatformJobClaim,
    *,
    result_ref: dict[str, Any] | None = None,
    message: str = "完成",
) -> bool:
    now = await _db_now(db)
    result = await db.execute(
        sa.update(PlatformJob)
        .execution_options(synchronize_session=False)
        .where(
            _claim_filter(claim),
            PlatformJob.cancel_requested_at.is_(None),
        )
        .values(
            status="succeeded",
            stage="completed",
            progress_current=sa.case(
                (
                    PlatformJob.progress_total > PlatformJob.progress_current,
                    PlatformJob.progress_total,
                ),
                else_=PlatformJob.progress_current,
            ),
            progress_message=message,
            result_ref=result_ref,
            error_code=None,
            error_message=None,
            lease_owner=None,
            lease_token=None,
            lease_expires_at=None,
            heartbeat_at=now,
            finished_at=now,
            updated_at=now,
            version=PlatformJob.version + 1,
        )
    )
    if result.rowcount != 1:
        return False
    await db.execute(
        sa.update(PlatformJobAttempt)
        .where(
            PlatformJobAttempt.lease_token == claim.lease_token,
            PlatformJobAttempt.status == "running",
        )
        .values(status="succeeded", finished_at=now)
    )
    return True


async def finish_failure(
    db: AsyncSession,
    claim: PlatformJobClaim,
    *,
    error_code: str,
    error_message: str,
    retryable: bool,
) -> bool:
    now = await _db_now(db)
    terminal = not retryable or claim.attempt >= claim.max_attempts
    status = "failed" if terminal else "retry_wait"
    due = None if terminal else now + timedelta(seconds=min(900, 30 * claim.attempt))
    result = await db.execute(
        sa.update(PlatformJob)
        .execution_options(synchronize_session=False)
        .where(_claim_filter(claim))
        .values(
            status=status,
            next_attempt_at=due,
            error_code=error_code[:80],
            error_message=error_message[:2000],
            lease_owner=None,
            lease_token=None,
            lease_expires_at=None,
            heartbeat_at=now,
            finished_at=now if terminal else None,
            updated_at=now,
            version=PlatformJob.version + 1,
        )
    )
    if result.rowcount != 1:
        return False
    await db.execute(
        sa.update(PlatformJobAttempt)
        .where(
            PlatformJobAttempt.lease_token == claim.lease_token,
            PlatformJobAttempt.status == "running",
        )
        .values(
            status="failed",
            finished_at=now,
            error_code=error_code[:80],
            error_message=error_message[:2000],
        )
    )
    return True


async def request_cancel(
    db: AsyncSession,
    *,
    project_id: UUID,
    actor_id: UUID,
    job_id: UUID,
) -> dict[str, Any]:
    statement = sa.select(PlatformJob).where(
        PlatformJob.id == job_id,
        PlatformJob.project_id == project_id,
        PlatformJob.actor_id == actor_id,
    )
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    job = (await db.execute(statement)).scalar_one_or_none()
    if job is None:
        raise PlatformJobNotFound("任务不存在或已过期")
    if job.status in TERMINAL_STATUSES:
        return job_snapshot(job)
    now = await _db_now(db)
    job.cancel_requested_at = job.cancel_requested_at or now
    if job.status in {"queued", "retry_wait"}:
        job.status = "cancelled"
        job.finished_at = now
    job.updated_at = now
    job.version = int(job.version or 0) + 1
    await db.flush()
    return job_snapshot(job)


def job_snapshot(job: PlatformJob) -> dict[str, Any]:
    return {
        "job_id": str(job.id),
        "operation": job.operation,
        "project_id": str(job.project_id),
        "actor_id": str(job.actor_id),
        "status": job.status,
        "stage": job.stage,
        "progress_current": int(job.progress_current or 0),
        "progress_total": int(job.progress_total or 0),
        "progress_message": job.progress_message,
        "reserved_bytes": int(job.reserved_bytes or 0),
        "attempt_count": int(job.attempt_count or 0),
        "max_attempts": int(job.max_attempts or 0),
        "cancel_requested": job.cancel_requested_at is not None,
        "result_ref": job.result_ref,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "version": int(job.version or 0),
        "queued_at": job.queued_at.isoformat() if job.queued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


async def get_job_snapshot(
    db: AsyncSession,
    *,
    project_id: UUID,
    actor_id: UUID,
    job_id: UUID,
) -> dict[str, Any]:
    job = (
        await db.execute(
            sa.select(PlatformJob).where(
                PlatformJob.id == job_id,
                PlatformJob.project_id == project_id,
                PlatformJob.actor_id == actor_id,
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise PlatformJobNotFound("任务不存在或已过期")
    return job_snapshot(job)


async def queue_snapshot(db: AsyncSession) -> dict[str, int | float]:
    now = await _db_now(db)
    rows = (
        await db.execute(
            sa.select(PlatformJob.status, sa.func.count())
            .where(~PlatformJob.status.in_(TERMINAL_STATUSES))
            .group_by(PlatformJob.status)
        )
    ).all()
    counts = {str(status): int(count) for status, count in rows}
    oldest = (
        await db.execute(
            sa.select(sa.func.min(PlatformJob.queued_at)).where(
                PlatformJob.status.in_(("queued", "retry_wait"))
            )
        )
    ).scalar_one_or_none()
    if isinstance(oldest, str):
        oldest = datetime.fromisoformat(oldest)
    if oldest is not None and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    return {
        "queued": counts.get("queued", 0),
        "retry_wait": counts.get("retry_wait", 0),
        "running": counts.get("running", 0),
        "oldest_queue_age_seconds": (
            max(0.0, (now - oldest).total_seconds()) if oldest else 0.0
        ),
    }


async def finish_cancelled(
    db: AsyncSession,
    claim: PlatformJobClaim,
    *,
    message: str = "任务已取消",
) -> bool:
    now = await _db_now(db)
    result = await db.execute(
        sa.update(PlatformJob)
        .execution_options(synchronize_session=False)
        .where(_claim_filter(claim))
        .values(
            status="cancelled",
            stage="cancelled",
            progress_message=message,
            lease_owner=None,
            lease_token=None,
            lease_expires_at=None,
            heartbeat_at=now,
            finished_at=now,
            updated_at=now,
            version=PlatformJob.version + 1,
        )
    )
    if result.rowcount != 1:
        return False
    await db.execute(
        sa.update(PlatformJobAttempt)
        .where(
            PlatformJobAttempt.lease_token == claim.lease_token,
            PlatformJobAttempt.status == "running",
        )
        .values(status="cancelled", finished_at=now)
    )
    return True


async def acquire_admission_lock(db: AsyncSession) -> None:
    """PG 上串行化容量检查与任务插入；SQLite 测试单事务执行。"""
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(
            sa.text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended('platform_job_admission', 0))"
            )
        )


async def enforce_active_capacity(
    db: AsyncSession,
    job: PlatformJob,
    *,
    global_limit: int,
    user_limit: int,
    project_limit: int,
    reserved_bytes_limit: int,
) -> None:
    """在 admission lock 内检查跨 worker 活动任务及保守磁盘预算。"""
    active = ("queued", "running", "retry_wait")
    row = (
        await db.execute(
            sa.select(
                sa.func.count(PlatformJob.id),
                sa.func.count(PlatformJob.id).filter(
                    PlatformJob.actor_id == job.actor_id
                ),
                sa.func.count(PlatformJob.id).filter(
                    PlatformJob.project_id == job.project_id
                ),
                sa.func.coalesce(sa.func.sum(PlatformJob.reserved_bytes), 0),
            ).where(PlatformJob.status.in_(active))
        )
    ).one()
    global_count, user_count, project_count, reserved = map(int, row)
    if global_count > max(1, global_limit):
        raise PlatformJobCapacityExceeded("平台批量导入任务已满，请稍后重试")
    if user_count > max(1, user_limit):
        raise PlatformJobCapacityExceeded("您已有过多批量导入任务，请等待现有任务完成")
    if project_count > max(1, project_limit):
        raise PlatformJobCapacityExceeded("当前项目已有过多批量导入任务，请稍后重试")
    if reserved > max(1, reserved_bytes_limit):
        raise PlatformJobCapacityExceeded("批量导入暂存空间预算不足，请稍后重试")
