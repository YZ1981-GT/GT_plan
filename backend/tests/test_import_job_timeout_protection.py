"""回归：超时检测必须保护本进程内仍活跃运行的导入作业（2026-06-08）。

根因：慢 DB 下大批写入/激活阶段长时间无进度回调→心跳落后→
`check_timed_out` 把仍在跑的作业标 timed_out + 其 dataset 标 failed→
worker 走到 activate 时撞 "Dataset is not staged (failed)" 崩溃。

修复：`check_timed_out(db, protected_job_ids=...)` 跳过 protected 集合内的作业，
`ImportJobRunner.recover_jobs` 传入 `_active_job_ids()`（_running_tasks 内未结束的 task）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.dataset_models import ImportJob, JobStatus
from app.services.import_job_service import ImportJobService

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _create_stale_running_job(factory) -> uuid.UUID:
    """建一个心跳已远超 timeout_seconds 的 running 作业。"""
    job_id = uuid.uuid4()
    # 心跳在很久以前（远超默认 600s timeout）
    stale_hb = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5000)
    async with factory() as db:
        db.add(
            ImportJob(
                id=job_id,
                project_id=uuid.uuid4(),
                year=2025,
                status=JobStatus.running,
                current_phase="running",
                heartbeat_at=stale_hb,
                started_at=stale_hb,
                timeout_seconds=600,
            )
        )
        await db.commit()
    return job_id


@pytest.mark.asyncio
async def test_check_timed_out_marks_unprotected_job(session_factory):
    """无保护时，心跳超时的作业被标 timed_out（基线行为）。"""
    job_id = await _create_stale_running_job(session_factory)
    async with session_factory() as db:
        timed_out = await ImportJobService.check_timed_out(db)
        await db.commit()
    assert any(j.id == job_id for j in timed_out)
    async with session_factory() as db:
        job = (await db.execute(sa.select(ImportJob).where(ImportJob.id == job_id))).scalar_one()
    assert job.status == JobStatus.timed_out


@pytest.mark.asyncio
async def test_check_timed_out_skips_protected_active_job(session_factory):
    """protected_job_ids 内的作业即使心跳超时也不被标 timed_out（核心回归）。"""
    job_id = await _create_stale_running_job(session_factory)
    async with session_factory() as db:
        timed_out = await ImportJobService.check_timed_out(
            db, protected_job_ids={job_id}
        )
        await db.commit()
    assert all(j.id != job_id for j in timed_out)
    async with session_factory() as db:
        job = (await db.execute(sa.select(ImportJob).where(ImportJob.id == job_id))).scalar_one()
    # 仍是 running，未被误杀
    assert job.status == JobStatus.running
