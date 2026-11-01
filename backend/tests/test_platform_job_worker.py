"""通用耐久 worker 的 claim、执行和围栏终态。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services import platform_job_service as jobs
from app.services.platform_job_registry import ExecutorOutcome
from app.workers import platform_job_worker as worker


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _claim():
    return jobs.PlatformJobClaim(
        job_id=uuid.uuid4(),
        operation="test",
        project_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        payload_ref={},
        attempt=1,
        max_attempts=3,
        lease_token=uuid.uuid4(),
        lease_seconds=300,
    )


@pytest.mark.asyncio
async def test_worker_claims_executes_and_fenced_finishes(monkeypatch):
    claim = _claim()
    executor = AsyncMock(return_value=ExecutorOutcome({"ok": True}))
    monkeypatch.setattr(worker, "async_session", lambda: _Session())
    monkeypatch.setattr(worker, "get_executor", lambda _operation: executor)

    with patch.object(jobs, "claim_next", new=AsyncMock(return_value=claim)), patch.object(
        jobs, "cancellation_requested", new=AsyncMock(return_value=False)
    ), patch.object(jobs, "finish_success", new=AsyncMock(return_value=True)) as finish:
        assert await worker.run_once() is True

    executor.assert_awaited_once()
    finish.assert_awaited_once()
    assert finish.call_args.kwargs["result_ref"] == {"ok": True}


@pytest.mark.asyncio
async def test_worker_does_not_double_finish_executor_atomic_outcome(monkeypatch):
    claim = _claim()
    executor = AsyncMock(return_value=ExecutorOutcome({"ok": True}, finalized=True))
    monkeypatch.setattr(worker, "async_session", lambda: _Session())
    monkeypatch.setattr(worker, "get_executor", lambda _operation: executor)

    with patch.object(jobs, "claim_next", new=AsyncMock(return_value=claim)), patch.object(
        jobs, "finish_success", new=AsyncMock()
    ) as finish:
        assert await worker.run_once() is True

    finish.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_executor_is_terminal_not_infinite_retry(monkeypatch):
    claim = _claim()
    monkeypatch.setattr(worker, "async_session", lambda: _Session())
    monkeypatch.setattr(worker, "get_executor", lambda _operation: None)

    with patch.object(jobs, "claim_next", new=AsyncMock(return_value=claim)), patch.object(
        jobs, "finish_failure", new=AsyncMock(return_value=True)
    ) as finish:
        assert await worker.run_once() is True

    assert finish.call_args.kwargs["retryable"] is False
    assert finish.call_args.kwargs["error_code"] == "executor_missing"
