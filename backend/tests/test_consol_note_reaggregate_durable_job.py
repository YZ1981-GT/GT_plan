"""B4：合并附注重新汇总的耐久任务 executor / 提交端点。"""
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
from app.routers import consol_notes as route
from app.services import consol_note_reaggregate_executor as executor
from app.services import platform_job_service as jobs
from app.services.consol_note_subtree_reaggregate import ReaggregateCancelled
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


class _Result:
    def __init__(self, value): self.value = value
    def scalar_one_or_none(self): return self.value


class _Session:
    committed = 0
    async def __aenter__(self): return self
    async def __aexit__(self, *_args): return False
    async def execute(self, _statement): return _Result(SimpleNamespace(id=uuid.uuid4()))
    async def commit(self): self.committed += 1


def _claim(**payload):
    return jobs.PlatformJobClaim(
        job_id=uuid.uuid4(), operation=executor.OPERATION, project_id=uuid.uuid4(), actor_id=uuid.uuid4(),
        payload_ref={'year': 2025, 'section_ids': ['五、1'], **payload},
        attempt=1, max_attempts=3, lease_token=uuid.uuid4(), lease_seconds=60,
    )


def test_executor_registered():
    assert get_executor(executor.OPERATION) is executor.execute_consol_note_reaggregate


@pytest.mark.asyncio
async def test_executor_rechecks_guards_and_preserves_reaggregate_result(monkeypatch):
    claim = _claim()
    session = _Session()
    monkeypatch.setattr(executor, 'async_session', lambda: session)
    permission = AsyncMock()
    lock = AsyncMock()
    monkeypatch.setattr(executor, 'assert_project_permission', permission)
    monkeypatch.setattr(executor, 'check_consol_lock', lock)

    from app.services import consol_node_scope, consol_note_aggregation_service, consol_note_formula_service
    scope = SimpleNamespace(year=2025, node_key='root', tree=object())
    monkeypatch.setattr(consol_node_scope, 'resolve_requested_node_key', lambda *_a: 'root')
    monkeypatch.setattr(consol_node_scope, 'resolve_node_scope', AsyncMock(return_value=scope))
    monkeypatch.setattr(consol_note_aggregation_service, 'validate_lineage_dag', AsyncMock(return_value=True))
    monkeypatch.setattr(consol_note_formula_service, 'note_template_type', lambda value: value)
    result = {'sections_processed': 1, 'sections_updated': 1, 'status': 'persisted'}
    aggregate = AsyncMock(return_value=result)
    monkeypatch.setattr(executor, 'reaggregate_subtree', aggregate)

    reports: list[tuple] = []
    async def report(*args):
        reports.append(args)
        return True

    outcome = await executor.execute_consol_note_reaggregate(claim, report)
    assert outcome.result_ref == {'result': result}
    assert reports[0][3] == 'authorizing'
    assert reports[-1][3] == 'finalizing'
    permission.assert_awaited_once()
    lock.assert_awaited_once()
    aggregate.assert_awaited_once()
    assert aggregate.await_args.kwargs['progress'] is not None
    assert session.committed == 1


@pytest.mark.asyncio
async def test_executor_turns_callback_cancellation_into_lease_lost(monkeypatch):
    claim = _claim()
    session = _Session()
    monkeypatch.setattr(executor, 'async_session', lambda: session)
    monkeypatch.setattr(executor, 'assert_project_permission', AsyncMock())
    monkeypatch.setattr(executor, 'check_consol_lock', AsyncMock())
    from app.services import consol_node_scope, consol_note_aggregation_service, consol_note_formula_service
    monkeypatch.setattr(consol_node_scope, 'resolve_requested_node_key', lambda *_a: None)
    monkeypatch.setattr(consol_node_scope, 'resolve_node_scope', AsyncMock(return_value=SimpleNamespace(year=2025, node_key=None, tree=object())))
    monkeypatch.setattr(consol_note_aggregation_service, 'validate_lineage_dag', AsyncMock(return_value=True))
    monkeypatch.setattr(consol_note_formula_service, 'note_template_type', lambda value: value)
    monkeypatch.setattr(executor, 'reaggregate_subtree', AsyncMock(side_effect=ReaggregateCancelled('cancelled')))

    async def report(*_args): return True

    with pytest.raises(executor.ConsolReaggregateLeaseLost):
        await executor.execute_consol_note_reaggregate(claim, report)


@pytest.mark.asyncio
async def test_async_route_creates_idempotent_job(factory, monkeypatch):
    project, actor = uuid.uuid4(), uuid.uuid4()
    user = SimpleNamespace(id=actor)
    from app.services import consol_node_scope, consol_note_formula_service

    monkeypatch.setattr(consol_node_scope, 'resolve_requested_node_key', lambda *_a: 'root')
    monkeypatch.setattr(consol_note_formula_service, 'note_template_type', lambda value: value)
    body = route.ReaggregateRequest(section_ids=['五、1'], node_key='root', operation_id='one-click')

    async with factory() as db:
        first = await route.reaggregate_consol_notes_async(project, 2025, body, None, db, user, None)
    async with factory() as db:
        replay = await route.reaggregate_consol_notes_async(project, 2025, body, None, db, user, None)
    assert first.job_id == replay.job_id
    assert first.status == 'queued'

    changed = route.ReaggregateRequest(section_ids=['五、2'], node_key='root', operation_id='one-click')
    async with factory() as db:
        with pytest.raises(HTTPException) as conflict:
            await route.reaggregate_consol_notes_async(project, 2025, changed, None, db, user, None)
    assert conflict.value.status_code == 409
