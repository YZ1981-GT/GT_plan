"""底稿文件打包导出的耐久任务迁移（spec platform-heavy-jobs-and-capacity-closure B3）。"""
from __future__ import annotations

import inspect
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, User  # noqa: F401 - 解析 PlatformJob 外键
from app.models.platform_job_models import PlatformJob, PlatformJobAttempt
from app.services import platform_job_service as jobs
from app.services import export_pack_executor as executor
from app.services.export_pack_executor import (
    OPERATION,
    ExportPackLeaseLost,
    _ExportFile,
    execute_export_pack,
)
from app.services.platform_job_registry import get_executor, registered_operations
from app.services.export_progress_service import (
    LEGACY_EXPORT_PROGRESS_READ_UNTIL,
    legacy_export_task_readable,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid


@pytest_asyncio.fixture
async def job_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[PlatformJob.__table__, PlatformJobAttempt.__table__],
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _claimed_job(factory, *, wp_ids: list[str] | None = None):
    project_id, actor_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as db:
        job, _ = await jobs.create_or_get_job(
            db,
            operation=OPERATION,
            project_id=project_id,
            actor_id=actor_id,
            idempotency_key=uuid.uuid4().hex,
            payload_ref={"wp_ids": wp_ids or [str(uuid.uuid4())]},
            progress_total=len(wp_ids or ["placeholder"]),
        )
        await db.commit()
    async with factory() as db:
        claim = await jobs.claim_next(db, worker_id="test-worker", lease_seconds=30)
        await db.commit()
    assert claim is not None
    return job, claim


def test_executor_is_registered_under_the_expected_operation():
    assert OPERATION in registered_operations()
    assert get_executor(OPERATION) is execute_export_pack


def test_executor_rechecks_visibility_before_metadata_query():
    """排队期间撤权不能只靠提交时的 visible_wp_ids 快照。"""
    source = inspect.getsource(executor._load_export_files)
    assert "make_bulk_visible_filter" in source
    assert "entry_kind=\"worker\"" in source
    assert "if not permitted" in source


@pytest.mark.asyncio
async def test_executor_commits_success_before_complete_event(job_factory, tmp_path, monkeypatch):
    """进度严格先于 complete，且 complete 事件发出前 DB 已成功写入 result_ref。"""
    wp1, wp2 = tmp_path / "wp1.xlsx", tmp_path / "wp2.xlsx"
    wp1.write_bytes(b"PK-fake-wp1")
    wp2.write_bytes(b"PK-fake-wp2")
    job, claim = await _claimed_job(job_factory, wp_ids=[str(uuid.uuid4()), str(uuid.uuid4())])
    files = [_ExportFile(wp1, "D/D1.xlsx"), _ExportFile(wp2, "D/D2.xlsx")]

    monkeypatch.setattr(executor, "async_session", job_factory)
    monkeypatch.setattr(executor, "EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(executor, "_load_export_files", AsyncMock(return_value=files))

    order: list[str] = []
    events: list[tuple[str, dict]] = []
    original_finish = jobs.finish_success

    async def finish_success(*args, **kwargs):
        order.append("finish_success")
        return await original_finish(*args, **kwargs)

    def broadcast(event_type, payload):
        order.append(event_type)
        events.append((event_type, payload))

    monkeypatch.setattr(jobs, "finish_success", finish_success)
    monkeypatch.setattr("app.services.event_bus.event_bus.broadcast_raw", broadcast)

    async def report(current, total=None, message=None, stage=None):
        async with job_factory() as db:
            accepted = await jobs.update_progress(
                db, claim, current=current, total=total, message=message, stage=stage
            )
            await db.commit()
            return accepted

    outcome = await execute_export_pack(claim, report)

    assert outcome.finalized is True
    assert outcome.result_ref is not None
    zip_path = Path(outcome.result_ref["zip_path"])
    assert zip_path.is_file()
    assert outcome.result_ref["written"] == 2
    assert ".a1." in zip_path.name, "每个 attempt 必须有独有 artifact 名，旧 worker 不能覆盖新 worker"

    assert [kind for kind, _ in events] == [
        "export.progress", "export.progress", "platform.job.updated", "export.complete"
    ]
    assert order.index("finish_success") < order.index("platform.job.updated") < order.index("export.complete")
    assert [payload["done"] for kind, payload in events if kind == "export.progress"] == [1, 2]

    async with job_factory() as db:
        persisted = await db.get(PlatformJob, job.id)
    assert persisted.status == "succeeded"
    assert persisted.result_ref["zip_path"] == str(zip_path)


@pytest.mark.asyncio
async def test_cancellation_during_packing_removes_artifact_and_never_completes(
    job_factory, tmp_path, monkeypatch
):
    """packing 中取消 → callback 返回 False，线程停写、DB 终态 cancelled、只有 failed SSE。"""
    source = tmp_path / "wp.xlsx"
    source.write_bytes(b"PK-fake")
    job, claim = await _claimed_job(job_factory, wp_ids=[str(uuid.uuid4())])

    monkeypatch.setattr(executor, "async_session", job_factory)
    monkeypatch.setattr(executor, "EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(
        executor, "_load_export_files", AsyncMock(return_value=[_ExportFile(source, "D/D1.xlsx")])
    )
    events: list[str] = []
    monkeypatch.setattr(
        "app.services.event_bus.event_bus.broadcast_raw", lambda event, _data: events.append(event)
    )

    async def report(current, total=None, message=None, stage=None):
        if stage == "packing":
            async with job_factory() as db:
                await jobs.request_cancel(
                    db, project_id=job.project_id, actor_id=job.actor_id, job_id=job.id
                )
                await db.commit()
            return False
        async with job_factory() as db:
            accepted = await jobs.update_progress(
                db, claim, current=current, total=total, message=message, stage=stage
            )
            await db.commit()
            return accepted

    outcome = await execute_export_pack(claim, report)

    assert outcome.finalized is True
    assert events == ["platform.job.updated", "export.failed"]
    assert not list((tmp_path / "exports").glob("*.zip"))
    async with job_factory() as db:
        persisted = await db.get(PlatformJob, job.id)
    assert persisted.status == "cancelled"


@pytest.mark.asyncio
async def test_lost_lease_does_not_emit_terminal_event_or_leave_artifact(job_factory, tmp_path, monkeypatch):
    """旧 worker 失去 lease 时只清自己的 artifact，不通知用户完成/失败，不覆盖新 worker。"""
    _job, claim = await _claimed_job(job_factory)
    monkeypatch.setattr(executor, "async_session", job_factory)
    monkeypatch.setattr(executor, "EXPORT_DIR", tmp_path / "exports")
    events: list[str] = []
    monkeypatch.setattr(
        "app.services.event_bus.event_bus.broadcast_raw", lambda event, _data: events.append(event)
    )

    async def lost_report(*_args, **_kwargs):
        return False

    with pytest.raises(ExportPackLeaseLost):
        await execute_export_pack(claim, lost_report)
    assert events == []
    assert not (tmp_path / "exports").exists()


@pytest.mark.asyncio
async def test_failure_is_committed_before_export_failed_event(job_factory, tmp_path, monkeypatch):
    """普通失败写入 failed 终态后才通知前端，轮询和 SSE 一致。"""
    job, claim = await _claimed_job(job_factory)
    monkeypatch.setattr(executor, "async_session", job_factory)
    monkeypatch.setattr(executor, "EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(
        executor, "_load_export_files", AsyncMock(side_effect=OSError("metadata unavailable"))
    )

    events: list[str] = []
    monkeypatch.setattr(
        "app.services.event_bus.event_bus.broadcast_raw", lambda event, _data: events.append(event)
    )

    async def report(current, total=None, message=None, stage=None):
        async with job_factory() as db:
            accepted = await jobs.update_progress(
                db, claim, current=current, total=total, message=message, stage=stage
            )
            await db.commit()
            return accepted

    outcome = await execute_export_pack(claim, report)
    assert outcome.finalized is True
    assert events == ["platform.job.updated", "export.failed"]
    async with job_factory() as db:
        persisted = await db.get(PlatformJob, job.id)
    assert persisted.status == "failed"
    assert "metadata unavailable" in persisted.error_message


@pytest.mark.asyncio
async def test_submit_operation_id_replays_only_the_same_user_operation(job_factory, monkeypatch):
    """相同 operation_id 重试复用 job；不带 operation_id 的两次新点击不复用旧 ZIP。"""
    from app.routers import batch_export_progress as route
    from app.services.wp_visibility import entry_integration

    project, actor = uuid.uuid4(), uuid.uuid4()
    user = SimpleNamespace(id=actor)

    async def visible(_wp_id, _sheet):
        return True

    monkeypatch.setattr(entry_integration, "make_bulk_visible_filter", lambda *_a, **_k: visible)
    body = route.BatchExportAsyncRequest(
        wp_ids=[str(uuid.uuid4()), str(uuid.uuid4())], operation_id="one-click"
    )
    async with job_factory() as db:
        first = await route.batch_export_async(project, body, db, user)
    async with job_factory() as db:
        same = await route.batch_export_async(project, body, db, user)
    assert first.task_id == same.task_id
    assert first.status == "pending"

    no_key = route.BatchExportAsyncRequest(wp_ids=body.wp_ids)
    async with job_factory() as db:
        second_click = await route.batch_export_async(project, no_key, db, user)
    assert second_click.task_id != first.task_id

    changed = route.BatchExportAsyncRequest(wp_ids=[str(uuid.uuid4())], operation_id="one-click")
    async with job_factory() as db:
        with pytest.raises(HTTPException) as conflict:
            await route.batch_export_async(project, changed, db, user)
    assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_status_lookup_is_operation_and_project_permission_scoped(job_factory, monkeypatch):
    """同用户的其他 job 不能借导出端点读取；导出 job 读取时必须重新校验项目权限。"""
    from app.core import database
    from app.routers import batch_export_progress as route

    project, actor = uuid.uuid4(), uuid.uuid4()
    user = SimpleNamespace(id=actor)
    async with job_factory() as db:
        export_job, _ = await jobs.create_or_get_job(
            db, operation=OPERATION, project_id=project, actor_id=actor,
            idempotency_key="export", payload_ref={"wp_ids": [str(uuid.uuid4())]},
        )
        other_job, _ = await jobs.create_or_get_job(
            db, operation="bulk_tab_import", project_id=project, actor_id=actor,
            idempotency_key="other", payload_ref={"path": "a.zip"},
        )
        await db.commit()

    permission = AsyncMock(return_value=user)
    monkeypatch.setattr(database, "async_session", job_factory)
    monkeypatch.setattr(route, "assert_project_permission", permission)

    found = await route._owned_durable_snapshot(str(export_job.id), user)
    hidden = await route._owned_durable_snapshot(str(other_job.id), user)
    assert found is not None and found["job_id"] == str(export_job.id)
    assert hidden is None
    permission.assert_awaited_once_with(ANY, user, project, "readonly")


def test_status_mapping_and_artifact_path_are_safe(tmp_path, monkeypatch):
    from app.routers import batch_export_progress as route

    monkeypatch.setattr(route, "EXPORT_DIR", tmp_path / "exports")
    safe = route.EXPORT_DIR / "safe.zip"
    safe.parent.mkdir(parents=True)
    safe.write_bytes(b"PK")
    assert route._durable_export_path({"result_ref": {"zip_path": str(safe)}}) == safe.resolve()
    assert route._durable_export_path({"result_ref": {"zip_path": str(tmp_path / "outside.zip")}}) is None

    complete = route._status_from_durable("id", {
        "status": "succeeded", "progress_current": 2, "progress_total": 2,
        "result_ref": {"zip_path": str(safe), "download_url": "/api/exports/id"},
    })
    cancelled = route._status_from_durable("id", {"status": "cancelled"})
    assert complete.status == "complete" and complete.download_url == "/api/exports/id"
    assert cancelled.status == "failed" and cancelled.error == "导出已取消"


def test_idempotency_key_is_bounded_and_operation_scoped():
    from app.routers.batch_export_progress import _idempotency_key

    key = _idempotency_key("a" * 100)
    assert len(key) < 128
    assert key == _idempotency_key("a" * 100)
    # 不传客户端 operation id 时是两次独立点击，禁止永久复用先前 artifact。
    assert _idempotency_key(None) != _idempotency_key(None)


def test_legacy_compatibility_has_explicit_retirement_date():
    assert LEGACY_EXPORT_PROGRESS_READ_UNTIL.isoformat() == "2027-02-05"
    assert legacy_export_task_readable(LEGACY_EXPORT_PROGRESS_READ_UNTIL) is True
    assert legacy_export_task_readable(LEGACY_EXPORT_PROGRESS_READ_UNTIL.replace(day=6)) is False
