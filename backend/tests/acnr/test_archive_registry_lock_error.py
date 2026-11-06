"""归档编排遇 ACNR 版本锁失败：保留 durable job 失败记录，同时向客户端返回稳定 409。

普通 gate/package/cloud 失败仍沿用「200 + failed job」契约；只有 RegistryLockError 是目录治理终态，
由全局 handler 映射 409。这里只测服务 / 路由事务边界，HTTP 409 线格式由
``test_registry_lock_error_http.py`` 对真实 ``app.main`` 覆盖。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routers import archive as archive_router
from app.services.acnr.project_registry_lock import RegistryLockError
from app.services.archive_orchestrator import ArchiveOrchestrator


async def test_orchestrator_marks_failed_job_then_reraises_registry_lock_error(monkeypatch):
    db = SimpleNamespace(flush=AsyncMock())
    orchestrator = ArchiveOrchestrator(db)
    error = RegistryLockError(
        "lock_failed",
        "无法记录归档时的地址目录版本：地址目录快照正在维护，请稍后重试；本次归档未生效",
    )

    async def fail_lock(_job):
        raise error

    monkeypatch.setattr(orchestrator, "_build_steps", lambda *_args: [("lock", fail_lock)])
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        push_to_cloud=False,
        purge_local=False,
        section_progress={},
        status="running",
        failed_section=None,
        failed_reason=None,
        finished_at=None,
        last_succeeded_section=None,
    )

    with pytest.raises(RegistryLockError) as caught:
        await orchestrator._run(job, start_from=0)

    assert caught.value is error
    assert job.status == "failed"
    assert job.failed_section == "lock"
    assert "正在维护" in job.failed_reason
    assert job.section_progress["lock"]["status"] == "failed"
    db.flush.assert_awaited_once()


async def test_orchestrate_route_commits_failed_job_before_propagating_409(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock())
    error = RegistryLockError("lock_failed", "无法记录归档时的地址目录版本：测试；本次归档未生效")
    run = AsyncMock(side_effect=error)
    monkeypatch.setattr(ArchiveOrchestrator, "orchestrate", run)
    project_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    with pytest.raises(RegistryLockError) as caught:
        await archive_router.orchestrate_archive(
            project_id=project_id,
            body=archive_router.OrchestrateRequest(),
            db=db,
            current_user=SimpleNamespace(id=actor_id),
            _token=None,
        )

    assert caught.value is error
    db.commit.assert_awaited_once()
    run.assert_awaited_once_with(
        project_id=project_id,
        scope="final",
        push_to_cloud=False,
        purge_local=False,
        gate_eval_id=None,
        initiated_by=actor_id,
    )


async def test_retry_route_commits_failed_job_before_propagating_409(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock())
    error = RegistryLockError("lock_failed", "无法记录归档时的地址目录版本：测试；本次归档未生效")
    monkeypatch.setattr(archive_router, "_job_of_project", AsyncMock(return_value=object()))
    retry = AsyncMock(side_effect=error)
    monkeypatch.setattr(ArchiveOrchestrator, "retry", retry)
    project_id, job_id, actor_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    with pytest.raises(RegistryLockError) as caught:
        await archive_router.retry_archive_job(
            project_id=project_id,
            job_id=job_id,
            db=db,
            current_user=SimpleNamespace(id=actor_id),
            _token=None,
        )

    assert caught.value is error
    db.commit.assert_awaited_once()
    retry.assert_awaited_once_with(job_id=job_id, initiated_by=actor_id)
