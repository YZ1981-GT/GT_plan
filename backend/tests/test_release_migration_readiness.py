"""platform-release-blocker-closure Tasks 17/19: migration readiness gates."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import migration_runner as migration_module
from app.core import startup_registry as startup
from app.core.migration_runner import (
    FailureRecord,
    MigrationReadiness,
    MigrationRunner,
    RunPendingResult,
)
from app.core.runtime_state import migration_state, shutdown_state


_SCHEMA_DDL = """
CREATE TABLE schema_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version VARCHAR(20) NOT NULL UNIQUE,
    filename VARCHAR(255) NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checksum VARCHAR(64) NOT NULL
)
"""
_FAILURE_DDL = """
CREATE TABLE schema_migration_failures (
    version VARCHAR(20) PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    error_type VARCHAR(100) NOT NULL,
    error_message TEXT NOT NULL,
    attempted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    attempt_count INTEGER NOT NULL DEFAULT 1
)
"""


@pytest.fixture(autouse=True)
def restore_process_state():
    complete = migration_state.is_complete()
    draining = shutdown_state.is_draining()
    report = startup.get_startup_report()
    yield
    migration_state._complete = complete  # noqa: SLF001
    shutdown_state._draining = draining  # noqa: SLF001
    if report is None:
        startup.reset_startup_report()
    else:
        startup._set_runtime_report(report)


@pytest.fixture
async def readiness_world(tmp_path: Path):
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "V001__baseline.sql").write_text("-- no-op baseline\n", encoding="utf-8")
    (migration_dir / "V229__pending_release_gate.sql").write_text(
        "CREATE TABLE release_gate_probe (id INTEGER);\n", encoding="utf-8"
    )

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'readiness.db'}")
    async with engine.begin() as conn:
        await conn.execute(text(_SCHEMA_DDL))
        await conn.execute(text(_FAILURE_DDL))
        await conn.execute(
            text(
                "INSERT INTO schema_version(version, filename, checksum) "
                "VALUES ('001', 'V001__baseline.sql', 'baseline')"
            )
        )
    try:
        yield engine, migration_dir
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_readiness_reports_pending_v229_without_writes(readiness_world):
    engine, migration_dir = readiness_world
    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        status = await MigrationRunner(
            engine=engine, migrations_dir=migration_dir
        ).inspect_readiness()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_statement)

    assert status.disk_versions == ("001", "229")
    assert status.applied_versions == ("001",)
    assert status.pending_versions == ("229",)
    assert status.failures == ()
    assert status.is_complete is False
    assert statements
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in statements), statements


@pytest.mark.asyncio
async def test_readiness_failure_table_row_blocks_complete(readiness_world):
    engine, migration_dir = readiness_world
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO schema_version(version, filename, checksum) "
            "VALUES ('229', 'V229__pending_release_gate.sql', 'applied')"
        ))
        await conn.execute(text(
            "INSERT INTO schema_migration_failures"
            "(version, filename, error_type, error_message, attempt_count) "
            "VALUES ('229', 'V229__pending_release_gate.sql', 'TestError', 'boom', 3)"
        ))

    status = await MigrationRunner(
        engine=engine, migrations_dir=migration_dir
    ).inspect_readiness()
    assert status.pending_versions == ()
    assert [(f.version, f.attempt_count) for f in status.failures] == [("229", 3)]
    assert status.is_complete is False


class _RecordingRunner:
    def __init__(self, events: list[str], readiness: MigrationReadiness):
        self.events = events
        self.readiness = readiness

    async def run_pending(self) -> RunPendingResult:
        self.events.append("run_pending")
        return RunPendingResult(executed=[], failed=[])

    async def inspect_readiness(self) -> MigrationReadiness:
        self.events.append("inspect_readiness")
        return self.readiness

    async def close(self) -> None:
        self.events.append("close")


def _patch_runner(monkeypatch, events: list[str], readiness: MigrationReadiness) -> None:
    monkeypatch.setattr(
        migration_module,
        "MigrationRunner",
        lambda **_kwargs: _RecordingRunner(events, readiness),
    )


def _migration_tasks() -> tuple[startup.StartupTaskSpec, ...]:
    """按名字取迁移两步（注册表前部会插入新任务，按下标切片会错位）。"""
    by_name = {spec.name: spec for spec in startup.STARTUP_TASKS}
    return (by_name["run_migrations"], by_name["migration_mark_complete"])


def _complete_readiness() -> MigrationReadiness:
    return MigrationReadiness(
        disk_versions=("001", "229"),
        applied_versions=("001", "229"),
        pending_versions=(),
        failures=(),
    )


@pytest.mark.asyncio
async def test_initial_worker_runs_then_read_only_verifies(monkeypatch):
    events: list[str] = []
    _patch_runner(monkeypatch, events, _complete_readiness())
    monkeypatch.delenv("GT_BOOTSTRAP_DONE", raising=False)
    migration_state.mark_incomplete()
    ctx = startup.StartupContext()

    results = await startup.run_startup_tasks(_migration_tasks(), context=ctx)

    assert [item.status for item in results] == ["ok", "ok"]
    assert events == ["run_pending", "close", "inspect_readiness", "close"]
    assert isinstance(ctx.extras["migration_run_result"], RunPendingResult)
    assert ctx.extras["migration_readiness"].is_complete is True
    assert migration_state.is_complete() is True


@pytest.mark.asyncio
async def test_reload_worker_skips_execution_but_still_verifies(monkeypatch):
    events: list[str] = []
    pending = MigrationReadiness(
        disk_versions=("001", "229"),
        applied_versions=("001",),
        pending_versions=("229",),
        failures=(),
    )
    _patch_runner(monkeypatch, events, pending)
    monkeypatch.setenv("GT_BOOTSTRAP_DONE", "1")
    migration_state.mark_complete()
    startup.reset_startup_report()

    with pytest.raises(RuntimeError, match=r"pending_versions=\['229'\]"):
        await startup.run_startup_tasks(_migration_tasks())

    report = startup.get_startup_report()
    assert report is not None
    assert [(item.name, item.status) for item in report] == [
        ("run_migrations", "skipped"),
        ("migration_mark_complete", "failed"),
    ]
    assert events == ["inspect_readiness", "close"]
    assert migration_state.is_complete() is False


@pytest.mark.asyncio
async def test_startup_failure_record_is_critical(monkeypatch):
    events: list[str] = []
    failed = MigrationReadiness(
        disk_versions=("001",),
        applied_versions=("001",),
        pending_versions=(),
        failures=(FailureRecord("229", "V229__bad.sql", "TestError", "boom", 2),),
    )
    _patch_runner(monkeypatch, events, failed)
    migration_state.mark_complete()

    with pytest.raises(RuntimeError, match=r"failed_versions=\['229'\]"):
        await startup._task_migration_mark_complete(startup.StartupContext())
    assert migration_state.is_complete() is False


def _health_app() -> FastAPI:
    from app.api.health import router
    from app.core.database import get_db
    from app.core.redis import get_redis

    app = FastAPI()
    app.include_router(router, prefix="/api")

    async def db_override():
        session = AsyncMock()
        session.execute = AsyncMock(return_value=None)
        yield session

    async def redis_override():
        client = AsyncMock()
        client.ping = AsyncMock(return_value=True)
        yield client

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_redis] = redis_override
    return app


@pytest.mark.asyncio
async def test_health_exposes_pending_versions_and_degraded_status():
    migration = {
        "applied_count": 228,
        "disk_count": 229,
        "pending_versions": ["229"],
        "failures": [],
        "complete": False,
    }
    drift = {"count": 0, "critical_count": 0, "items": []}
    with (
        patch("app.api.health._query_migration_status", new=AsyncMock(return_value=migration)),
        patch("app.api.health._query_schema_drift", new=AsyncMock(return_value=drift)),
        patch(
            "app.api.health._query_audit_chain_health",
            new=AsyncMock(return_value={"unacknowledged_forks": 0, "quarantined_entries": 0}),
        ),
        patch("app.api.health.audit_log_failure_state", return_value={"failed_count": 0}),
        patch("app.api.health.reload_status_snapshot", return_value={}),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=_health_app()), base_url="http://test"
        ) as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["migration"]["pending_versions"] == ["229"]
    assert body["migration"]["complete"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("migration", "drift", "migration_complete"),
    [
        ({"complete": False, "pending_versions": ["229"], "failures": []},
         {"critical_count": 0}, False),
        ({"complete": False, "pending_versions": [], "failures": [{"version": "229"}]},
         {"critical_count": 0}, False),
        ({"complete": True, "pending_versions": [], "failures": []},
         {"critical_count": 1}, True),
    ],
)
async def test_readyz_rejects_migration_or_critical_drift(
    migration: dict, drift: dict, migration_complete: bool
):
    from app.api.probes import router

    migration_state.mark_complete()
    shutdown_state._draining = False  # noqa: SLF001
    app = FastAPI()
    app.include_router(router)
    snapshot = {"status": "degraded", "migration": migration, "schema_drift": drift}
    with patch(
        "app.api.probes._get_health_snapshot_cached",
        new=AsyncMock(return_value=snapshot),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["health"] == "degraded"
    assert body["degraded"] is True
    assert body["migration_complete"] is migration_complete