"""B4：公式推送迁入 platform durable job 的行为守卫。"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, User  # noqa: F401 - PlatformJob 外键
from app.models.platform_job_models import PlatformJob, PlatformJobAttempt
from app.routers import formula_push as route
from app.services import platform_job_service as jobs
from app.services.formula_push import durable_job_executor as executor
from app.services.platform_job_registry import get_executor

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


def _claim(**payload):
    return jobs.PlatformJobClaim(
        job_id=uuid.uuid4(),
        operation=executor.OPERATION,
        project_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        payload_ref={'year': 2025, **payload},
        attempt=1,
        max_attempts=3,
        lease_token=uuid.uuid4(),
        lease_seconds=60,
    )


class _Result:
    def __init__(self, value): self.value = value
    def scalar_one_or_none(self): return self.value


class _Session:
    async def __aenter__(self): return self
    async def __aexit__(self, *_args): return False
    async def execute(self, _statement): return _Result(SimpleNamespace(id=uuid.uuid4()))


def test_executor_registered():
    assert get_executor(executor.OPERATION) is executor.execute_formula_push


@pytest.mark.asyncio
async def test_executor_rechecks_permission_reports_stages_and_returns_summary(monkeypatch):
    claim = _claim(wp_codes=['E1'])
    reports: list[tuple] = []
    summary = {'run_id': 'r1', 'written_count': 3, 'kept_count': 1}
    fake_result = SimpleNamespace(summary=lambda: summary)

    monkeypatch.setattr(executor, 'async_session', lambda: _Session())
    permission = AsyncMock()
    monkeypatch.setattr(executor, 'assert_project_permission', permission)
    run = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(executor.engine, 'run_and_commit', run)

    async def report(*args):
        reports.append(args)
        return True

    outcome = await executor.execute_formula_push(claim, report)
    assert outcome.result_ref == {'summary': summary, 'formula_push_run_id': 'r1'}
    assert [entry[3] for entry in reports] == ['authorizing', 'finalizing']
    permission.assert_awaited_once()
    run.assert_awaited_once()
    assert run.await_args.kwargs['dry_run'] is False
    assert run.await_args.kwargs['codes'] == ['E1']


@pytest.mark.asyncio
async def test_executor_stops_before_engine_when_lease_is_lost(monkeypatch):
    claim = _claim()
    run = AsyncMock()
    monkeypatch.setattr(executor.engine, 'run_and_commit', run)

    async def lost(*_args): return False

    with pytest.raises(executor.FormulaPushLeaseLost):
        await executor.execute_formula_push(claim, lost)
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_executor_rejects_invalid_payload_before_side_effects(monkeypatch):
    run = AsyncMock()
    monkeypatch.setattr(executor.engine, 'run_and_commit', run)

    async def ok(*_args): return True

    with pytest.raises(executor.FormulaPushJobError, match='年度'):
        await executor.execute_formula_push(_claim(year='x'), ok)
    with pytest.raises(executor.FormulaPushJobError, match='超过 50'):
        await executor.execute_formula_push(_claim(wp_codes=['E1'] * 51), ok)
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_router_keeps_dry_run_sync_and_queues_real_write(factory, monkeypatch):
    project, actor = uuid.uuid4(), uuid.uuid4()
    user = SimpleNamespace(id=actor)
    fake_result = SimpleNamespace(
        summary=lambda: {'dry_run': True, 'written_count': 2},
        items=[],
    )
    monkeypatch.setattr(route.engine, 'run_and_commit', AsyncMock(return_value=fake_result))
    monkeypatch.setattr(route.panel, 'orphan_state_count', AsyncMock(return_value=0))

    async with factory() as db:
        dry = await route.run_push(project, route.RunBody(year=2025, dry_run=True), db, user)
    assert dry['dry_run'] is True

    body = route.RunBody(year=2025, dry_run=False, wp_codes=['E1'], operation_id='click-1', async_mode=True)
    async with factory() as db:
        accepted = await route.run_push(project, body, db, user)
    assert accepted['accepted'] is True
    assert accepted['status'] == 'queued'

    async with factory() as db:
        replay = await route.run_push(project, body, db, user)
    assert replay['job_id'] == accepted['job_id']

    changed = route.RunBody(year=2026, dry_run=False, wp_codes=['E1'], operation_id='click-1', async_mode=True)
    async with factory() as db:
        with pytest.raises(HTTPException) as conflict:
            await route.run_push(project, changed, db, user)
    assert conflict.value.status_code == 409
