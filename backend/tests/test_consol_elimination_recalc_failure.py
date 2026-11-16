"""抵销审批下游重算入队失败的可见留痕契约。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import consol_elimination_recalc_handler as handler


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_recalc_enqueue_failure_records_failed_run_and_broadcasts(monkeypatch):
    project_id = uuid4()
    request_operation = AsyncMock(side_effect=RuntimeError("企业树不存在"))

    def wake():
        return None

    record_failure = AsyncMock(return_value=uuid4())

    monkeypatch.setattr("app.core.database.async_session", lambda: _Session())
    monkeypatch.setattr("app.services.consol_operation_service.request_operation", request_operation)
    monkeypatch.setattr("app.workers.consol_operation_worker.wake", wake)
    monkeypatch.setattr("app.services.consol_push_failure_record.record_consol_push_failure", record_failure)

    await handler._push(
        SimpleNamespace(project_id=project_id, year=2025, extra={"entry_id": "entry-1"}),
        "elimination_approved",
    )

    request_operation.assert_awaited_once()
    record_failure.assert_awaited_once()
    args = record_failure.await_args
    assert args.args == (project_id, 2025)
    assert args.kwargs["trigger"] == "elimination_approved"
    assert "企业树不存在" in args.kwargs["reason"]
    assert args.kwargs["source_id"] == "entry-1"
