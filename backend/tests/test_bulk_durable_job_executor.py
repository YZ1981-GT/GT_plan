"""bulk-tab durable executor 的原子完成、进度与 spool 完整性。"""
from __future__ import annotations

import asyncio
import io
import json
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import platform_job_service as jobs
from app.services.bulk_tab import bulk_async_runner
from app.services.bulk_tab import durable_job_executor as executor


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, user, events):
        self.user = user
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _statement):
        return _Result(self.user)

    async def commit(self):
        self.events.append("commit")

    async def rollback(self):
        self.events.append("rollback")


def _zip_payload() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"files": [{"sheet_code": "D2-1"}]}),
        )
    return buffer.getvalue()


def _claim(project_id, actor_id, path, sha256, size):
    return jobs.PlatformJobClaim(
        job_id=uuid.uuid4(),
        operation=executor.OPERATION,
        project_id=project_id,
        actor_id=actor_id,
        payload_ref={
            "spool_path": str(path),
            "sha256": sha256,
            "size": size,
            "strategy": "overwrite",
            "atomicity": "per-sheet",
        },
        attempt=1,
        max_attempts=3,
        lease_token=uuid.uuid4(),
        lease_seconds=300,
    )


@pytest.mark.asyncio
async def test_executor_finishes_job_in_same_transaction_then_cleans_spool(
    tmp_path, monkeypatch
):
    project_id, actor_id = uuid.uuid4(), uuid.uuid4()
    root = tmp_path / str(project_id)
    root.mkdir(parents=True)
    path = root / "input.zip"
    path.write_bytes(_zip_payload())
    sha256, size = bulk_async_runner.hash_spool_file(path)
    claim = _claim(project_id, actor_id, path, sha256, size)
    events: list[str] = []
    session = _Session(SimpleNamespace(id=actor_id), events)
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_DIR", tmp_path)
    monkeypatch.setattr(executor, "async_session", lambda: session)

    report_result = SimpleNamespace(
        to_dict=lambda: {"summary": {"success": 1}},
    )

    async def run_import(**kwargs):
        kwargs["progress"].tick("完成一张")
        await asyncio.sleep(0)
        return report_result

    async def finish_success(*_args, **_kwargs):
        events.append("finish")
        return True

    cleanup = AsyncMock()
    reporter = AsyncMock(return_value=True)
    with patch(
        "app.services.bulk_tab.bulk_import_service.run",
        side_effect=run_import,
    ), patch.object(jobs, "finish_success", side_effect=finish_success), patch(
        "app.services.wp_visibility.entry_integration.make_bulk_preflight",
        return_value=AsyncMock(),
    ), patch.object(bulk_async_runner, "cleanup_import_spool", cleanup):
        outcome = await executor.execute_bulk_import(claim, reporter)

    assert outcome.finalized is True
    assert outcome.result_ref == {"report": {"summary": {"success": 1}}}
    assert events == ["finish", "commit"]
    cleanup.assert_awaited_once_with(path)
    assert reporter.await_count >= 2


@pytest.mark.asyncio
async def test_executor_rejects_tampered_spool_before_database_write(
    tmp_path, monkeypatch
):
    project_id, actor_id = uuid.uuid4(), uuid.uuid4()
    root = tmp_path / str(project_id)
    root.mkdir(parents=True)
    path = root / "input.zip"
    path.write_bytes(b"PK changed")
    claim = _claim(project_id, actor_id, path, "0" * 64, path.stat().st_size)
    monkeypatch.setattr(bulk_async_runner, "BULK_IMPORT_DIR", tmp_path)

    with pytest.raises(executor.BulkImportJobError) as exc_info:
        await executor.execute_bulk_import(
            claim,
            AsyncMock(return_value=True),
        )

    assert exc_info.value.cleanup_path == path
    assert "摘要不匹配" in str(exc_info.value)


def test_executor_is_registered_for_worker_startup():
    from app.services.platform_job_registry import get_executor

    assert get_executor(executor.OPERATION) is executor.execute_bulk_import
