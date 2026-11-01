from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401
from app.models.base import Base, ProjectStatus
from app.models.consol_operation_models import ConsolOperation
from app.models.core import Project, User
from app.schemas.consol_context import ConsolContext
from app.schemas.consol_operation import ConsolVersionVector
from app.services import consol_operation_service as service
from app.services.consol_version_vector import vector_digest

YEAR = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[User.__table__, Project.__table__, ConsolOperation.__table__],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def project() -> Project:
    return Project(
        id=uuid.uuid4(), name="【测试】运行状态机_2025", client_name="【测试】运行状态机",
        company_code="OPS", audit_year=YEAR, report_scope="consolidated",
        status=ProjectStatus.execution, consol_lock=False,
    )


def vector() -> ConsolVersionVector:
    raw = {
        "schema_version": 1, "tree_revision": None, "tree_fingerprint": "a" * 64,
        "recorded_tree_fingerprint": None, "worksheet_versions": {},
        "tb_digest": "b" * 64, "elimination_digest": "c" * 64,
        "formula_digest": "d" * 64, "note_mapping_digest": "e" * 64,
        "template_digest": "f" * 64, "digest": "0" * 64,
    }
    raw["digest"] = vector_digest(raw)
    return ConsolVersionVector.model_validate(raw)


def install_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(_db, project_id, year, operation_id):
        return (
            ConsolContext(
                project_id=project_id, year=year, run_id=operation_id,
                tree_fingerprint="a" * 64, template_type="soe", report_scope="consolidated",
            ),
            vector(),
        )
    monkeypatch.setattr(service, "_snapshot", fake)


@pytest.mark.asyncio
async def test_request_replay_coalesce_and_conflict(db: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    p = project(); db.add(p); await db.commit(); install_snapshot(monkeypatch)
    first = await service.request_operation(
        db, project_id=p.id, year=YEAR, operation_type="push",
        idempotency_key="request-one", trigger_source="formula_changed", requested_actions=("notes",),
    )
    await db.commit()
    second = await service.request_operation(
        db, project_id=p.id, year=YEAR, operation_type="refresh_all",
        idempotency_key="request-two", trigger_source="manual", requested_actions=("report",),
    )
    await db.commit()
    assert second.disposition == "coalesced" and second.operation.id == first.operation.id
    assert second.operation.revision == 2
    assert second.operation.operation_type == "refresh_all"
    assert set(second.operation.idempotency_keys) == {"request-one", "request-two"}
    assert second.operation.request_payload["requested_actions"] == ["notes", "report"]

    replay = await service.request_operation(
        db, project_id=p.id, year=YEAR, operation_type="refresh_all",
        idempotency_key="request-two", trigger_source="manual", requested_actions=("report",),
    )
    assert replay.disposition == "replayed" and replay.operation.id == first.operation.id
    with pytest.raises(service.OperationConflict):
        await service.request_operation(
            db, project_id=p.id, year=YEAR, operation_type="refresh_all",
            idempotency_key="request-two", trigger_source="manual", requested_actions=("trial",),
        )


@pytest.mark.asyncio
async def test_claim_blocks_pending_then_expired_lease_is_reclaimed(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    p = project(); db.add(p); await db.commit(); install_snapshot(monkeypatch)
    first = await service.request_operation(
        db, project_id=p.id, year=YEAR, operation_type="push",
        idempotency_key="claim-one", trigger_source="manual",
    )
    await db.commit()
    owner_one = uuid.uuid4()
    claim_one = await service.claim_next_operation(db, lease_owner=owner_one)
    assert claim_one and claim_one.operation_id == first.operation.id
    await db.commit()

    pending = await service.request_operation(
        db, project_id=p.id, year=YEAR, operation_type="refresh_all",
        idempotency_key="claim-two", trigger_source="manual",
    )
    await db.commit()
    assert pending.disposition == "created" and pending.operation.id != first.operation.id
    assert await service.claim_next_operation(db, lease_owner=uuid.uuid4()) is None

    assert await service.complete_operation(
        db, claim_one, "succeeded", steps=[], errors=[], metrics={}, result_refs={},
    )
    await db.commit()
    owner_two = uuid.uuid4()
    claim_two = await service.claim_next_operation(db, lease_owner=owner_two)
    assert claim_two and claim_two.operation_id == pending.operation.id
    await db.commit()

    await db.execute(sa.update(ConsolOperation).where(
        ConsolOperation.id == claim_two.operation_id,
    ).values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    await db.commit()
    owner_three = uuid.uuid4()
    reclaimed = await service.claim_next_operation(db, lease_owner=owner_three)
    assert reclaimed and reclaimed.operation_id == claim_two.operation_id
    assert reclaimed.lease_owner == owner_three
    assert not await service.complete_operation(
        db, claim_two, "succeeded", steps=[], errors=[], metrics={}, result_refs={},
    )
    assert await service.complete_operation(
        db, reclaimed, "failed", steps=[], errors=[{"error": "injected"}], metrics={}, result_refs={},
    )
    await db.commit()
    final = await service.get_operation(db, p.id, YEAR, reclaimed.operation_id)
    assert final and final.status == "failed" and final.attempt == 2
    assert final.lease_owner is None and final.lease_expires_at is None


@pytest.mark.asyncio
async def test_cancel_and_legacy_partial_payload(db: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    p = project(); db.add(p); await db.commit(); install_snapshot(monkeypatch)
    created = await service.request_operation(
        db, project_id=p.id, year=YEAR, operation_type="refresh_all",
        idempotency_key="cancel-me", trigger_source="manual",
    )
    cancelled = await service.cancel_operation(db, p.id, YEAR, created.operation.id)
    assert cancelled and cancelled.status == "cancelled"
    await db.commit()

    partial = ConsolOperation(
        id=uuid.uuid4(), project_id=p.id, year=YEAR, operation_type="refresh_all",
        idempotency_key="partial-row", idempotency_keys={"partial-row": "x" * 64},
        request_hash="x" * 64, request_payload={}, context_json={}, version_vector={},
        status="partial", revision=1, trigger_source="manual", steps=[
            {"step": "tree", "status": "succeeded"},
            {"step": "notes", "status": "failed"},
        ], errors=[{"step": "notes", "error": "injected"}], result_refs={}, metrics={},
    )
    db.add(partial); await db.commit()
    payload = service.legacy_refresh_payload(partial)
    assert payload["status"] == "completed"
    assert payload["operation_status"] == "partial"
    assert payload["errors"][0]["step"] == "notes"


@pytest.mark.asyncio
async def test_refresh_runner_publishes_report_run_ref_with_existing_refs_preserved():
    """refresh 最终 CAS 同时写 refresh_result、report_run_id 与 input revision；漏任一项都应失败。"""
    from app.services import consol_operation_runner as runner

    pid = uuid.uuid4()
    op_id = uuid.uuid4()
    report_run_id = uuid.uuid4()
    claim = service.OperationClaim(
        operation_id=op_id, project_id=pid, year=YEAR, operation_type="refresh_all",
        lease_owner=uuid.uuid4(), revision=3,
    )
    v = vector()
    operation = SimpleNamespace(
        id=op_id, trigger_source="manual", triggered_by=None,
        version_vector=v.model_dump(mode="json"),
    )
    refresh_result = SimpleNamespace(
        nodes_refreshed=4,
        steps_completed=["tree", "worksheet", "trial", "reconcile", "report", "notes"],
        steps_skipped=[], errors=[], duration_ms=25, reconciliation=None,
        report_run_id=report_run_id, report_row_digest="r" * 64,
    )
    complete = AsyncMock(return_value=True)
    with patch("app.services.consol_cascade_refresh_service.refresh_all", new=AsyncMock(return_value=refresh_result)) as refresh, \
         patch.object(runner, "_post_vector", new=AsyncMock(return_value=v)), \
         patch.object(runner, "complete_operation", new=complete):
        result = await runner._execute_refresh(
            AsyncMock(), operation, claim,
            ConsolContext(project_id=pid, year=YEAR, run_id=op_id, tree_fingerprint="a" * 64),
            SimpleNamespace(node_key="ROOT:consol"), 0.0,
        )
    assert result.status == "succeeded"
    assert refresh.await_args.kwargs["operation_revision"] == 3
    refs = complete.await_args.kwargs["result_refs"]
    assert refs["report_run_id"] == str(report_run_id)
    assert refs["report_row_digest"] == "r" * 64
    assert refs["input_revision"] == 3
    assert "refresh_result" in refs and "post_version_vector" in refs


@pytest.mark.asyncio
async def test_push_runner_publishes_source_and_parent_report_run_refs():
    """push 多目标运行保留完整 run map，同时把源项目 run 提升为默认 published 引用。"""
    from app.services import consol_operation_runner as runner

    pid = uuid.uuid4()
    parent_id = uuid.uuid4()
    op_id = uuid.uuid4()
    source_run = uuid.uuid4()
    parent_run = uuid.uuid4()
    claim = service.OperationClaim(
        operation_id=op_id, project_id=pid, year=YEAR, operation_type="push",
        lease_owner=uuid.uuid4(), revision=2,
    )
    v = vector()
    operation = SimpleNamespace(
        id=op_id, trigger_source="formula_changed", triggered_by=None,
        version_vector=v.model_dump(mode="json"),
    )
    push_result = SimpleNamespace(
        run_id=uuid.uuid4(), status="succeeded", warnings=[], steps=[],
        pushed_projects=[str(pid), str(parent_id)],
        report_run_ids={str(pid): str(source_run), str(parent_id): str(parent_run)},
        report_row_digests={str(pid): "s" * 64, str(parent_id): "p" * 64},
    )
    complete = AsyncMock(return_value=True)
    with patch("app.services.consol_push_service.push", new=AsyncMock(return_value=push_result)) as push, \
         patch.object(runner, "_post_vector", new=AsyncMock(return_value=v)), \
         patch.object(runner, "complete_operation", new=complete):
        result = await runner._execute_push(
            AsyncMock(), operation, claim,
            ConsolContext(project_id=pid, year=YEAR, run_id=op_id, tree_fingerprint="a" * 64),
            SimpleNamespace(node_key="ROOT:consol"), 0.0,
        )
    assert result.status == "succeeded"
    assert push.await_args.kwargs["operation_revision"] == 2
    refs = complete.await_args.kwargs["result_refs"]
    assert refs["report_run_ids"] == push_result.report_run_ids
    assert refs["report_row_digests"] == push_result.report_row_digests
    assert refs["report_run_id"] == str(source_run)
    assert refs["report_row_digest"] == "s" * 64
    assert refs["input_revision"] == 2
    assert "push_run_id" in refs and "post_version_vector" in refs
