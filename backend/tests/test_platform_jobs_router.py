"""B5 通用耐久任务状态/取消/重试路由的行为守卫。"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, User  # noqa: F401 - PlatformJob 外键目标
from app.models.platform_job_models import PlatformJob, PlatformJobAttempt
from app.routers import platform_jobs as route
from app.services import platform_job_service as jobs

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, 'visit_uuid'):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(
            sync, tables=[PlatformJob.__table__, PlatformJobAttempt.__table__],
        ))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _job(factory, *, status: str = 'failed', actor=None, project=None):
    actor = actor or uuid.uuid4()
    project = project or uuid.uuid4()
    async with factory() as db:
        item, _ = await jobs.create_or_get_job(
            db,
            operation='workpaper_pack_export',
            project_id=project,
            actor_id=actor,
            idempotency_key=uuid.uuid4().hex,
            payload_ref={'wp_ids': ['a']},
            progress_total=1,
        )
        claim = await jobs.claim_next(db, worker_id='worker')
        assert claim is not None
        if status == 'failed':
            await jobs.finish_failure(db, claim, error_code='boom', error_message='boom', retryable=False)
        elif status == 'cancelled':
            await jobs.request_cancel(db, project_id=project, actor_id=actor, job_id=item.id)
        elif status == 'succeeded':
            await jobs.finish_success(db, claim, result_ref={'ok': True})
        await db.commit()
    return item, actor, project


@pytest.mark.asyncio
async def test_get_requires_owned_project_job(factory):
    job, actor, project = await _job(factory, status='succeeded')
    user = SimpleNamespace(id=actor)
    async with factory() as db:
        payload = await route.get_platform_job(project, job.id, db, user)
    assert payload['job_id'] == str(job.id)
    assert payload['status'] == 'succeeded'

    async with factory() as db:
        with pytest.raises(HTTPException) as missing:
            await route.get_platform_job(project, job.id, db, SimpleNamespace(id=uuid.uuid4()))
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_cancel_returns_terminal_snapshot(factory):
    job, actor, project = await _job(factory, status='succeeded')
    # terminal success cancel is idempotent: no state rollback
    async with factory() as db:
        payload = await route.cancel_platform_job(project, job.id, db, SimpleNamespace(id=actor))
    assert payload['status'] == 'succeeded'


@pytest.mark.asyncio
async def test_retry_creates_new_job_and_preserves_failed_history(factory):
    old, actor, project = await _job(factory, status='failed')
    user = SimpleNamespace(id=actor)

    async with factory() as db:
        fresh = await route.retry_platform_job(
            project, old.id, route.RetryBody(operation_id='retry-click'), db, user,
        )
    assert fresh['job_id'] != str(old.id)
    assert fresh['status'] == 'queued'
    assert fresh['operation'] == 'workpaper_pack_export'

    # 同一 retry operation id 的 HTTP 重试返回同一个新 job。
    async with factory() as db:
        replay = await route.retry_platform_job(
            project, old.id, route.RetryBody(operation_id='retry-click'), db, user,
        )
    assert replay['job_id'] == fresh['job_id']

    # 原失败 job 仍保留供审计，不会被 reset/覆盖。
    async with factory() as db:
        persisted = await db.get(PlatformJob, old.id)
    assert persisted.status == 'failed'


@pytest.mark.asyncio
async def test_retry_rejects_nonterminal_and_foreign_job(factory):
    job, actor, project = await _job(factory, status='succeeded')
    user = SimpleNamespace(id=actor)
    async with factory() as db:
        with pytest.raises(HTTPException) as terminal:
            await route.retry_platform_job(project, job.id, route.RetryBody(operation_id='x'), db, user)
    assert terminal.value.status_code == 409

    async with factory() as db:
        with pytest.raises(HTTPException) as foreign:
            await route.retry_platform_job(project, job.id, route.RetryBody(operation_id='x'), db, SimpleNamespace(id=uuid.uuid4()))
    assert foreign.value.status_code == 404
