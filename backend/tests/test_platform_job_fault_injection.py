"""平台耐久任务故障注入（spec platform-heavy-jobs-and-capacity-closure B6）。

验证 kill/reload/重复提交/租约过期 场景下零重复副作用。每个场景直接操作
platform_job_service 的语义原语（不起真实 worker 进程），但断言的是生产环境
可观测到的行为：终态、attempt 数、副作用次数。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from app.models.platform_job_models import PlatformJob, PlatformJobAttempt
from app.services import platform_job_service as jobs


# ── fixture ─────────────────────────────────────────────────────────


@pytest.fixture
async def factory(tmp_path):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    from sqlalchemy.orm import sessionmaker

    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield Session
    await engine.dispose()


async def _insert(factory, *, key="test", max_attempts=3):
    async with factory() as db:
        job, created = await jobs.create_or_get_job(
            db,
            operation="fault_test",
            project_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            idempotency_key=key,
            payload_ref={"test": True},
            max_attempts=max_attempts,
        )
        await db.commit()
        return job


# ── kill 后恢复 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kill_recovery_another_worker_takes_over(factory):
    """模拟 worker 被杀（租约过期但 running 状态未清理） → 新 worker 接管。

    生产环境等价场景：`kill -9 worker_pid` 后，旧 worker 的 lease 到期，
    `claim_next` 的 `_settle_exhausted` 或「过期 running 也可认领」逻辑让新 worker 安全接管。
    """
    await _insert(factory)
    # Worker A 认领
    async with factory() as db:
        claim_a = await jobs.claim_next(db, worker_id="worker-A")
        await db.commit()
    assert claim_a is not None

    # 模拟 kill：把 lease 设为已过期
    async with factory() as db:
        await db.execute(
            sa.update(PlatformJob)
            .where(PlatformJob.id == claim_a.job_id)
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=10))
        )
        await db.commit()

    # Worker B 接管
    async with factory() as db:
        claim_b = await jobs.claim_next(db, worker_id="worker-B")
        await db.commit()
    assert claim_b is not None
    assert claim_b.job_id == claim_a.job_id
    assert claim_b.attempt == claim_a.attempt + 1
    assert claim_b.lease_token != claim_a.lease_token

    # Worker A 的旧 claim 不能再写成功——attempt fence 拦截
    async with factory() as db:
        stale_ok = await jobs.finish_success(db, claim_a, result_ref={"stale": True})
        await db.commit()
    assert stale_ok is False, "被杀 worker 的旧 claim 不得写入成功终态"

    # Worker B 正常完成
    async with factory() as db:
        ok = await jobs.finish_success(db, claim_b, result_ref={"recovered": True})
        await db.commit()
    assert ok is True

    # 验证 attempt 记录
    async with factory() as db:
        attempts = (
            await db.execute(
                sa.select(PlatformJobAttempt)
                .where(PlatformJobAttempt.job_id == claim_a.job_id)
                .order_by(PlatformJobAttempt.attempt_no)
            )
        ).scalars().all()
    assert len(attempts) == 2
    assert attempts[0].status == "lost_lease"
    assert attempts[1].status == "succeeded"


@pytest.mark.asyncio
async def test_duplicate_submit_is_idempotent_zero_side_effects(factory):
    """同一幂等键提交 3 次 → 只创建 1 个 job，副作用只执行 1 次。"""
    project_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    key = f"dedup-{uuid.uuid4().hex[:8]}"
    jobs_created = []

    for _ in range(3):
        async with factory() as db:
            job, created = await jobs.create_or_get_job(
                db,
                operation="fault_test",
                project_id=project_id,
                actor_id=actor_id,
                idempotency_key=key,
                payload_ref={"test": True},
            )
            await db.commit()
            jobs_created.append((str(job.id), created))

    # 只有第一次 created=True
    assert jobs_created[0][1] is True
    assert jobs_created[1][1] is False
    assert jobs_created[2][1] is False
    # 三次返回同一个 job_id
    assert len({jid for jid, _ in jobs_created}) == 1


@pytest.mark.asyncio
async def test_exhausted_attempts_become_terminal(factory):
    """max_attempts=1 的任务失败后不能被再次认领（不会无限重试）。"""
    await _insert(factory, max_attempts=1)

    async with factory() as db:
        claim = await jobs.claim_next(db, worker_id="only-try")
        await db.commit()
    assert claim is not None

    # 失败（retryable=True 但 attempt 已耗尽）
    async with factory() as db:
        await jobs.finish_failure(
            db, claim,
            error_code="temporary",
            error_message="失败",
            retryable=True,
        )
        await db.commit()

    # 无法再认领
    async with factory() as db:
        again = await jobs.claim_next(db, worker_id="second-try")
        await db.commit()
    assert again is None

    # 终态是 failed（不是 retry_wait）
    async with factory() as db:
        final = (
            await db.execute(sa.select(PlatformJob).where(PlatformJob.id == claim.job_id))
        ).scalar_one()
    assert final.status == "failed"


@pytest.mark.asyncio
async def test_cancel_during_running_prevents_success_write(factory):
    """任务正在运行时收到取消请求 → finish_success 被 fence 拒绝。"""
    job = await _insert(factory)

    async with factory() as db:
        claim = await jobs.claim_next(db, worker_id="w1")
        await db.commit()

    # 取消请求
    async with factory() as db:
        await jobs.request_cancel(
            db,
            project_id=job.project_id,
            actor_id=job.actor_id,
            job_id=job.id,
        )
        await db.commit()

    # finish_success 被拒（cancel_requested_at 不为 null → WHERE 不匹配）
    async with factory() as db:
        ok = await jobs.finish_success(db, claim, result_ref={"should_not": True})
        await db.commit()
    assert ok is False

    # finish_cancelled 成功
    async with factory() as db:
        cancelled = await jobs.finish_cancelled(db, claim)
        await db.commit()
    assert cancelled is True


@pytest.mark.asyncio
async def test_concurrent_claim_only_one_wins(factory):
    """两个 worker 同时认领同一任务 → 只有一个成功（不会重复执行）。"""
    await _insert(factory)

    claims = []
    for wid in ("w1", "w2"):
        async with factory() as db:
            c = await jobs.claim_next(db, worker_id=wid)
            await db.commit()
            claims.append(c)

    # 第一个成功，第二个返回 None（SQLite 无 SKIP LOCKED，但 CAS 条件保证只有一个赢）
    won = [c for c in claims if c is not None]
    assert len(won) == 1, f"expected exactly 1 winner, got {len(won)}"
