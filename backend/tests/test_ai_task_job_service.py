"""耐久 AI 批任务：幂等、逐项租约、围栏、取消与恢复。"""

import dataclasses
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.ai_models import AIChatMessage, AIChatSession, AIContent
from app.models.ai_task_job_models import AiTaskItem, AiTaskJob
from app.models.base import Base
from app.models.core import Project, User
from app.services.ai_task_job_service import (
    AiTaskJobConflict,
    AiTaskTarget,
    claim_next,
    create_or_get_job,
    finish_failure,
    finish_success,
    get_job_snapshot,
    request_cancel,
    retry_item,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


@pytest_asyncio.fixture
async def sessions():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__, Project.__table__, AIChatSession.__table__,
        AIChatMessage.__table__, AIContent.__table__,
        AiTaskJob.__table__, AiTaskItem.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_idempotent_create_returns_same_job_and_rejects_changed_request(sessions) -> None:
    project_id, actor_id, target_id = uuid4(), uuid4(), uuid4()
    async with sessions() as db:
        first, created = await create_or_get_job(
            db, project_id=project_id, year=2025,
            task_kind="note_batch_prefill", actor_id=actor_id,
            idempotency_key="same", request_payload={"year": 2025},
            targets=[AiTaskTarget("note_section", target_id, "五、1", {"x": 1})],
        )
        await db.commit()
        second, replay_created = await create_or_get_job(
            db, project_id=project_id, year=2025,
            task_kind="note_batch_prefill", actor_id=actor_id,
            idempotency_key="same", request_payload={"year": 2025},
            targets=[AiTaskTarget("note_section", target_id, "五、1", {"x": 1})],
        )
        assert created is True and replay_created is False
        assert second.id == first.id
        with pytest.raises(AiTaskJobConflict):
            await create_or_get_job(
                db, project_id=project_id, year=2025,
                task_kind="note_batch_prefill", actor_id=actor_id,
                idempotency_key="same", request_payload={"year": 2026}, targets=[],
            )


@pytest.mark.asyncio
async def test_lease_token_rejects_stale_result_and_accepts_owner(sessions) -> None:
    project_id, actor_id = uuid4(), uuid4()
    async with sessions() as db:
        job, _ = await create_or_get_job(
            db, project_id=project_id, year=2025,
            task_kind="note_batch_prefill", actor_id=actor_id,
            idempotency_key="lease", request_payload={},
            targets=[AiTaskTarget("note_section", uuid4(), "五、1", {})],
        )
        await db.commit()
    async with sessions() as db:
        claim = await claim_next(db, worker_id="worker-a", lease_seconds=60)
        assert claim is not None
        await db.commit()
    async with sessions() as db:
        stale = dataclasses.replace(claim, lease_token=uuid4())
        assert await finish_success(db, stale, result_summary={"bad": True}) is False
        await db.rollback()
    async with sessions() as db:
        assert await finish_success(db, claim, result_summary={"ok": True}) is True
        await db.commit()
        snapshot = await get_job_snapshot(db, project_id=project_id, job_id=job.id)
        assert snapshot["status"] == "succeeded"
        assert snapshot["items"][0]["generation_id"] == str(claim.generation_id)
        assert snapshot["items"][0]["result"] == {"ok": True}


@pytest.mark.asyncio
async def test_cancel_marks_queued_items_without_changing_generation_ids(sessions) -> None:
    project_id, actor_id = uuid4(), uuid4()
    async with sessions() as db:
        job, _ = await create_or_get_job(
            db, project_id=project_id, year=2025,
            task_kind="workpaper_batch_review", actor_id=actor_id,
            idempotency_key="cancel", request_payload={},
            targets=[
                AiTaskTarget("workpaper", uuid4(), "E1", {}),
                AiTaskTarget("workpaper", uuid4(), "E2", {}),
            ],
        )
        await db.commit()
        before = await get_job_snapshot(db, project_id=project_id, job_id=job.id)
        cancelled = await request_cancel(db, project_id=project_id, job_id=job.id)
        await db.commit()
        assert cancelled["status"] == "cancelled"
        assert cancelled["cancelled_count"] == 2
        assert [i["generation_id"] for i in cancelled["items"]] == [
            i["generation_id"] for i in before["items"]
        ]


@pytest.mark.asyncio
async def test_empty_job_finishes_immediately(sessions) -> None:
    project_id, actor_id = uuid4(), uuid4()
    async with sessions() as db:
        job, created = await create_or_get_job(
            db, project_id=project_id, year=2025,
            task_kind="note_batch_prefill", actor_id=actor_id,
            idempotency_key="empty", request_payload={}, targets=[],
        )
        await db.commit()
        snapshot = await get_job_snapshot(db, project_id=project_id, job_id=job.id)
    assert created is True
    assert snapshot["status"] == "succeeded"
    assert snapshot["progress_total"] == 0
    assert snapshot["finished_at"] is not None


@pytest.mark.asyncio
async def test_item_max_attempts_is_single_source(sessions) -> None:
    project_id, actor_id = uuid4(), uuid4()
    async with sessions() as db:
        job, _ = await create_or_get_job(
            db, project_id=project_id, year=2025,
            task_kind="note_batch_prefill", actor_id=actor_id,
            idempotency_key="one-attempt", request_payload={},
            targets=[AiTaskTarget("note_section", uuid4(), "五、1", {})],
        )
        item = (await db.execute(
            sa.select(AiTaskItem).where(AiTaskItem.job_id == job.id)
        )).scalar_one()
        item.max_attempts = 1
        await db.commit()
    async with sessions() as db:
        claim = await claim_next(db, worker_id="worker-a", lease_seconds=60)
        assert claim is not None and claim.max_attempts == 1
        await db.commit()
    async with sessions() as db:
        assert await finish_failure(
            db, claim, error_code="offline", error_message="offline", retryable=True
        ) is True
        await db.commit()
        snapshot = await get_job_snapshot(db, project_id=project_id, job_id=job.id)
    assert snapshot["status"] == "failed"
    assert snapshot["items"][0]["status"] == "failed"
    assert snapshot["items"][0]["next_attempt_at"] is None


@pytest.mark.asyncio
async def test_cancel_running_item_invalidates_lease(sessions) -> None:
    project_id, actor_id = uuid4(), uuid4()
    async with sessions() as db:
        job, _ = await create_or_get_job(
            db, project_id=project_id, year=2025,
            task_kind="note_batch_prefill", actor_id=actor_id,
            idempotency_key="cancel-running", request_payload={},
            targets=[AiTaskTarget("note_section", uuid4(), "五、1", {})],
        )
        await db.commit()
    async with sessions() as db:
        claim = await claim_next(db, worker_id="worker-a", lease_seconds=60)
        assert claim is not None
        await db.commit()
    async with sessions() as db:
        cancelled = await request_cancel(db, project_id=project_id, job_id=job.id)
        await db.commit()
        assert cancelled["status"] == "cancelled"
        assert cancelled["items"][0]["status"] == "cancelled"
    async with sessions() as db:
        assert await finish_success(db, claim, result_summary={"late": True}) is False
        await db.rollback()


@pytest.mark.asyncio
async def test_expired_final_attempt_is_recovered_to_failed(sessions) -> None:
    project_id, actor_id = uuid4(), uuid4()
    async with sessions() as db:
        job, _ = await create_or_get_job(
            db, project_id=project_id, year=2025,
            task_kind="note_batch_prefill", actor_id=actor_id,
            idempotency_key="expired", request_payload={},
            targets=[AiTaskTarget("note_section", uuid4(), "五、1", {})],
        )
        item = (await db.execute(
            sa.select(AiTaskItem).where(AiTaskItem.job_id == job.id)
        )).scalar_one()
        item.max_attempts = 1
        await db.commit()
    async with sessions() as db:
        claim = await claim_next(db, worker_id="worker-a", lease_seconds=1)
        assert claim is not None
        await db.execute(
            sa.update(AiTaskItem).where(AiTaskItem.id == claim.item_id).values(
                lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
            )
        )
        await db.commit()
    async with sessions() as db:
        assert await claim_next(db, worker_id="worker-b", lease_seconds=60) is None
        await db.commit()
        snapshot = await get_job_snapshot(db, project_id=project_id, job_id=job.id)
    assert snapshot["status"] == "failed"
    assert snapshot["items"][0]["error_code"] == "lease_expired_attempts_exhausted"


@pytest.mark.asyncio
async def test_manual_retry_resets_budget_but_preserves_generation(sessions) -> None:
    project_id, actor_id = uuid4(), uuid4()
    async with sessions() as db:
        job, _ = await create_or_get_job(
            db, project_id=project_id, year=2025,
            task_kind="note_batch_prefill", actor_id=actor_id,
            idempotency_key="manual-retry", request_payload={},
            targets=[AiTaskTarget("note_section", uuid4(), "五、1", {})],
        )
        await db.commit()
    async with sessions() as db:
        claim = await claim_next(db, worker_id="worker-a")
        assert claim is not None
        await db.commit()
    async with sessions() as db:
        assert await finish_failure(
            db, claim, error_code="bad", error_message="bad", retryable=False
        ) is True
        await db.commit()
        before = await get_job_snapshot(db, project_id=project_id, job_id=job.id)
        retried = await retry_item(
            db, project_id=project_id, job_id=job.id, item_id=claim.item_id
        )
        await db.commit()
    assert retried["items"][0]["attempt_count"] == 0
    assert retried["items"][0]["generation_id"] == before["items"][0]["generation_id"]
    async with sessions() as db:
        second = await claim_next(db, worker_id="worker-b")
        assert second is not None and second.attempt == 1


@pytest.mark.asyncio
async def test_review_artifact_and_job_report_share_stable_finding_ids(sessions) -> None:
    from types import SimpleNamespace

    from app.services.ai_review_artifact import persist_review_findings
    from app.services.ai_task_review_report import load_review_job_report

    project_id, actor_id, wp_id = uuid4(), uuid4(), uuid4()
    async with sessions() as db:
        job, _ = await create_or_get_job(
            db, project_id=project_id, year=2025,
            task_kind="workpaper_batch_review", actor_id=actor_id,
            idempotency_key="review-artifact",
            request_payload={"wp_code_prefix": "D2"},
            targets=[AiTaskTarget("workpaper", wp_id, "应收账款", {})],
        )
        await db.commit()
    async with sessions() as db:
        claim = await claim_next(db, worker_id="worker-a")
        assert claim is not None
        await db.commit()
    finding = SimpleNamespace(
        description="期初余额待核对", risk_level="high", pass_status=False,
        category="数据完整性", sheet_location="D2!C8", suggestion="核对上年审定数",
    )
    async with sessions() as db:
        persisted = await persist_review_findings(
            db, project_id=project_id, workpaper_id=wp_id,
            job_id=job.id, generation_id=claim.generation_id,
            wp_code="D2-1", sheet_name="应收账款", model_used="fake",
            prompt_source="sheet", findings=[finding],
        )
        summary = {
            "wp_id": str(wp_id), "wp_code": "D2-1", "sheet_name": "应收账款",
            "review_status": "ai_findings_present", "model_used": "fake",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "prompt_source": "sheet", "findings": persisted,
            "risk_summary": {"high": 1, "medium": 0, "low": 0},
        }
        assert await finish_success(db, claim, result_summary=summary) is True
        await db.commit()
        report = await load_review_job_report(
            db, project_id=project_id, wp_code_prefix="D2", job_id=job.id,
        )
        rows = list((await db.execute(sa.select(AIContent))).scalars().all())
    assert report is not None
    assert report.results[0].findings[0].id == persisted[0]["id"]
    assert str(rows[0].id) == persisted[0]["id"]
    assert rows[0].data_sources["generation_id"] == str(claim.generation_id)


@pytest.mark.asyncio
async def test_job_report_keeps_valid_empty_findings(sessions) -> None:
    from app.services.ai_task_review_report import load_review_job_report

    project_id, actor_id, wp_id = uuid4(), uuid4(), uuid4()
    async with sessions() as db:
        job, _ = await create_or_get_job(
            db, project_id=project_id, year=2025,
            task_kind="workpaper_batch_review", actor_id=actor_id,
            idempotency_key="empty-findings",
            request_payload={"wp_code_prefix": "D2"},
            targets=[AiTaskTarget("workpaper", wp_id, "应收账款", {})],
        )
        await db.commit()
    async with sessions() as db:
        claim = await claim_next(db, worker_id="worker-a")
        assert claim is not None
        await db.commit()
    async with sessions() as db:
        assert await finish_success(db, claim, result_summary={
            "wp_id": str(wp_id), "wp_code": "D2-1", "sheet_name": "应收账款",
            "review_status": "ai_no_new_findings", "model_used": "fake",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "prompt_source": "sheet", "findings": [],
            "risk_summary": {"high": 0, "medium": 0, "low": 0},
        }) is True
        await db.commit()
        report = await load_review_job_report(
            db, project_id=project_id, wp_code_prefix="D2", job_id=job.id,
        )
    assert report is not None
    assert len(report.results) == 1
    assert report.results[0].pass_status == "ai_no_new_findings"
    assert report.statistics.passed_count == 0
