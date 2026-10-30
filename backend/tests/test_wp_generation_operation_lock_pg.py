from __future__ import annotations

import asyncio
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.routers import wp_generation_operation_flow as flow
from app.services.procedure_scope_retention import lock_project_procedure_scope
from app.services.wp_generation_operation_service import ClaimResult, MaterializationSnapshot, PrepareResult

pytestmark = pytest.mark.asyncio


async def test_phase_a_releases_project_lock_before_materialize(monkeypatch):
    if make_url(settings.DATABASE_URL).get_backend_name() != "postgresql":
        pytest.skip("项目咨询锁时长测试需要 PostgreSQL")
    engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        connect_args={"ssl": False} if settings.DB_DISABLE_SSL else {},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    project_id, operation_id, token = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    entered, release = threading.Event(), threading.Event()

    async def prepare(db, **_kwargs):
        await lock_project_procedure_scope(db, project_id)
        return PrepareResult(operation_id, "prepared", "created")

    def materialize(*_args, **_kwargs):
        entered.set()
        assert release.wait(5), "测试未释放文件物化 barrier"
        return []

    monkeypatch.setattr(flow, "prepare_operation", prepare)
    monkeypatch.setattr(flow, "claim_operation", AsyncMock(return_value=ClaimResult(operation_id, "materializing", token, False)))
    monkeypatch.setattr(flow, "load_materialization_snapshot", AsyncMock(return_value=MaterializationSnapshot(
        operation_id, project_id, "template_set", "atomic", "normal", False, token, (),
    )))
    monkeypatch.setattr(flow, "snapshot_sources", lambda *_args: [])
    monkeypatch.setattr(flow, "record_source_snapshots", AsyncMock())
    monkeypatch.setattr(flow, "materialize_atomic", materialize)
    monkeypatch.setattr(flow, "record_materialized", AsyncMock())
    monkeypatch.setattr(flow, "assert_project_permission", AsyncMock())
    monkeypatch.setattr(flow, "finalize_operation", AsyncMock(return_value={
        "status": "succeeded", "receipt": {"created": 0, "operation_id": str(operation_id)},
    }))

    try:
        async with factory() as first, factory() as second:
            running = asyncio.create_task(flow.run_generation_operation(
                first, SimpleNamespace(id=uuid.uuid4()), operation_id=operation_id,
                project_id=project_id, year=2025, kind="template_set",
                template_set_id=uuid.uuid4(), codes=[],
            ))
            assert await asyncio.to_thread(entered.wait, 5), "未进入锁外文件物化"
            await asyncio.wait_for(lock_project_procedure_scope(second, project_id), timeout=1)
            await second.commit()
            release.set()
            result = await asyncio.wait_for(running, timeout=5)
            assert result.payload["created"] == 0
    finally:
        release.set()
        await engine.dispose()
