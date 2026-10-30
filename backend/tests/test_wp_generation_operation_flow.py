from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routers import wp_generation_operation_flow as flow
from app.services.wp_generation_operation_service import (
    ClaimResult,
    MaterializationSnapshot,
    PrepareResult,
)

pytestmark = pytest.mark.asyncio


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _snapshot(operation_id, project_id, token):
    return MaterializationSnapshot(
        operation_id=operation_id,
        project_id=project_id,
        kind="template_set",
        failure_policy="atomic",
        scenario="normal",
        has_foreign_currency=False,
        lease_token=token,
        items=(),
    )


async def test_file_io_runs_only_after_phase_a_and_read_transactions_commit(monkeypatch):
    db = FakeDb()
    project_id, operation_id, token = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    events: list[str] = []
    snapshots = [_snapshot(operation_id, project_id, token), _snapshot(operation_id, project_id, token)]

    monkeypatch.setattr(flow, "prepare_operation", AsyncMock(return_value=PrepareResult(operation_id, "prepared", "created")))
    monkeypatch.setattr(flow, "claim_operation", AsyncMock(return_value=ClaimResult(operation_id, "materializing", token, False)))

    async def load(*_args):
        events.append(f"load@{db.commits}")
        return snapshots.pop(0)

    def freeze(*_args):
        events.append(f"freeze@{db.commits}")
        assert db.commits == 3
        return []

    def materialize(*_args, **_kwargs):
        events.append(f"materialize@{db.commits}")
        assert db.commits == 5, "模板 hash 与文件 IO 前必须已释放 Phase A/读取事务"
        return []

    monkeypatch.setattr(flow, "load_materialization_snapshot", load)
    monkeypatch.setattr(flow, "snapshot_sources", freeze)
    monkeypatch.setattr(flow, "record_source_snapshots", AsyncMock())
    monkeypatch.setattr(flow, "materialize_atomic", materialize)
    monkeypatch.setattr(flow, "record_materialized", AsyncMock())
    monkeypatch.setattr(flow, "assert_project_permission", AsyncMock())
    monkeypatch.setattr(flow, "finalize_operation", AsyncMock(return_value={
        "status": "succeeded", "receipt": {"created": 0, "operation_id": str(operation_id)},
    }))

    result = await flow.run_generation_operation(
        db, SimpleNamespace(id=uuid.uuid4()), operation_id=operation_id,
        project_id=project_id, year=2025, kind="template_set",
        template_set_id=uuid.uuid4(), codes=[],
    )

    assert result.status_code == 200 and result.payload["operation_id"] == str(operation_id)
    assert events == ["load@2", "freeze@3", "load@4", "materialize@5"]
    assert db.commits == 7 and db.rollbacks == 0


async def test_terminal_replay_skips_claim_and_file_io(monkeypatch):
    db = FakeDb()
    operation_id, project_id = uuid.uuid4(), uuid.uuid4()
    receipt = {"created": 2, "operation_id": str(operation_id), "status": "succeeded"}
    monkeypatch.setattr(flow, "prepare_operation", AsyncMock(
        return_value=PrepareResult(operation_id, "succeeded", "terminal", receipt),
    ))
    claim = AsyncMock()
    monkeypatch.setattr(flow, "claim_operation", claim)
    result = await flow.run_generation_operation(
        db, SimpleNamespace(id=uuid.uuid4()), operation_id=operation_id,
        project_id=project_id, year=2025, kind="template_set",
        template_set_id=uuid.uuid4(), codes=["D2"],
    )
    assert result.payload == receipt and db.commits == 1 and db.rollbacks == 0
    claim.assert_not_awaited()


async def test_materialize_failure_is_persisted_as_terminal_receipt(monkeypatch):
    db = FakeDb()
    operation_id, project_id, token = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(flow, "prepare_operation", AsyncMock(return_value=PrepareResult(operation_id, "prepared", "created")))
    monkeypatch.setattr(flow, "claim_operation", AsyncMock(return_value=ClaimResult(operation_id, "materializing", token, False)))
    monkeypatch.setattr(flow, "load_materialization_snapshot", AsyncMock(return_value=_snapshot(operation_id, project_id, token)))
    monkeypatch.setattr(flow, "snapshot_sources", lambda *_args: [])
    monkeypatch.setattr(flow, "record_source_snapshots", AsyncMock())
    monkeypatch.setattr(flow, "materialize_atomic", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("disk full")))
    monkeypatch.setattr(flow, "cleanup_staging", lambda *_args: None)
    monkeypatch.setattr(flow, "mark_operation_failed", AsyncMock(return_value={
        "receipt": {"created": 0, "status": "failed", "operation_id": str(operation_id)},
    }))
    result = await flow.run_generation_operation(
        db, SimpleNamespace(id=uuid.uuid4()), operation_id=operation_id,
        project_id=project_id, year=2025, kind="template_set",
        template_set_id=uuid.uuid4(), codes=["D2"],
    )
    assert result.payload["status"] == "failed"
    assert db.rollbacks == 1 and db.commits == 6
    flow.mark_operation_failed.assert_awaited_once()


async def test_final_commit_failure_releases_lease_without_deleting_recoverable_files(monkeypatch):
    class FailFinalCommitDb(FakeDb):
        async def commit(self):
            self.commits += 1
            if self.commits == 7:
                raise RuntimeError("commit response lost")

    db = FailFinalCommitDb()
    operation_id, project_id, token = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    snapshot = _snapshot(operation_id, project_id, token)
    monkeypatch.setattr(flow, "prepare_operation", AsyncMock(return_value=PrepareResult(operation_id, "prepared", "created")))
    monkeypatch.setattr(flow, "claim_operation", AsyncMock(return_value=ClaimResult(operation_id, "materializing", token, False)))
    monkeypatch.setattr(flow, "load_materialization_snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(flow, "snapshot_sources", lambda *_args: [])
    monkeypatch.setattr(flow, "record_source_snapshots", AsyncMock())
    monkeypatch.setattr(flow, "materialize_atomic", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(flow, "record_materialized", AsyncMock())
    monkeypatch.setattr(flow, "assert_project_permission", AsyncMock())
    monkeypatch.setattr(flow, "finalize_operation", AsyncMock(return_value={
        "status": "succeeded", "receipt": {"created": 0},
    }))
    release = AsyncMock()
    cleanup = lambda *_args: pytest.fail("commit 结果不确定时不得删除可能已提交的正式文件")
    monkeypatch.setattr(flow, "release_operation_lease", release)
    monkeypatch.setattr(flow, "cleanup_staging", cleanup)

    with pytest.raises(RuntimeError, match="commit response lost"):
        await flow.run_generation_operation(
            db, SimpleNamespace(id=uuid.uuid4()), operation_id=operation_id,
            project_id=project_id, year=2025, kind="template_set",
            template_set_id=uuid.uuid4(), codes=[],
        )
    assert db.rollbacks == 1 and db.commits == 8
    release.assert_awaited_once()
    args = release.await_args.args
    assert args[:4] == (db, project_id, operation_id, token)
    assert isinstance(args[4], RuntimeError) and str(args[4]) == "commit response lost"
