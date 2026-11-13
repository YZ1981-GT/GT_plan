"""platform-release-blocker-closure Tasks 6-9: review submission single source."""
from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.base import UserRole
from app.models.workpaper_models import WpFileStatus, WpReviewStatus
from app.services.workpaper_review_submission_service import (
    ReviewSubmissionResult,
    ReviewSubmissionUnavailable,
    WorkpaperReviewSubmissionService,
    assert_review_level_actor,
)


def _wp(status=WpFileStatus.draft, review=WpReviewStatus.not_submitted):
    return SimpleNamespace(
        id=uuid.uuid4(), project_id=uuid.uuid4(), wp_index_id=uuid.uuid4(),
        status=status, review_status=review, reviewer=uuid.uuid4(), year=2025,
    )


def _db_with(row):
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_submit_from_draft_uses_all_gates_and_one_transition():
    wp = _wp()
    db = _db_with(wp)
    service = WorkpaperReviewSubmissionService()
    service._evaluate_gate = AsyncMock(return_value=None)
    service._assert_sod = AsyncMock()
    service._blocking_reasons = AsyncMock(return_value=[])
    service._complete_program = AsyncMock()
    with patch(
        "app.services.workpaper_review_submission_service.WorkingPaperService.update_review_status",
        new=AsyncMock(return_value={"status": "under_review", "review_status": "pending_level1"}),
    ) as transition:
        result = await service.submit(
            db, project_id=wp.project_id, wp_id=wp.id, actor_id=uuid.uuid4(),
        )
    assert result == ReviewSubmissionResult(
        True, "submitted", (), (), None, "under_review", "pending_level1",
    )
    service._evaluate_gate.assert_awaited_once()
    service._assert_sod.assert_awaited_once()
    transition.assert_awaited_once()
    service._complete_program.assert_awaited_once()


@pytest.mark.asyncio
async def test_blocked_submission_does_not_mutate_or_transition():
    wp = _wp()
    db = _db_with(wp)
    service = WorkpaperReviewSubmissionService()
    service._evaluate_gate = AsyncMock(return_value=None)
    service._assert_sod = AsyncMock()
    service._blocking_reasons = AsyncMock(return_value=["未执行质量自检"])
    with patch(
        "app.services.workpaper_review_submission_service.WorkingPaperService.update_review_status",
        new=AsyncMock(),
    ) as transition:
        result = await service.submit(
            db, project_id=wp.project_id, wp_id=wp.id, actor_id=uuid.uuid4(),
        )
    assert result.can_submit is False
    assert result.blocking_reasons == ("未执行质量自检",)
    assert wp.status == WpFileStatus.draft
    assert transition.await_count == 0


@pytest.mark.asyncio
async def test_gate_and_sod_infrastructure_fail_closed():
    wp = _wp()
    db = _db_with(wp)
    service = WorkpaperReviewSubmissionService()
    service._evaluate_gate = AsyncMock(side_effect=ReviewSubmissionUnavailable("门禁不可用"))
    with pytest.raises(ReviewSubmissionUnavailable, match="门禁不可用"):
        await service.submit(db, project_id=wp.project_id, wp_id=wp.id, actor_id=uuid.uuid4())
    assert wp.status == WpFileStatus.draft

@pytest.mark.asyncio
async def test_review_level_requires_role_and_designated_reviewer():
    wp = _wp(WpFileStatus.under_review, WpReviewStatus.pending_level1)
    manager = SimpleNamespace(id=wp.reviewer, role=UserRole.manager)
    project = SimpleNamespace(review_config=None, manager_id=manager.id, partner_id=uuid.uuid4())
    result = MagicMock(); result.first.return_value = (wp, project)
    db = AsyncMock(); db.execute = AsyncMock(return_value=result)
    await assert_review_level_actor(
        db, project_id=wp.project_id, wp_id=wp.id,
        new_review_status="level1_passed", actor=manager,
    )
    with pytest.raises(PermissionError, match="经理"):
        await assert_review_level_actor(
            db, project_id=wp.project_id, wp_id=wp.id,
            new_review_status="level1_passed",
            actor=SimpleNamespace(id=uuid.uuid4(), role=UserRole.partner),
        )
    with pytest.raises(PermissionError, match="指定复核人"):
        await assert_review_level_actor(
            db, project_id=wp.project_id, wp_id=wp.id,
            new_review_status="level1_passed",
            actor=SimpleNamespace(id=uuid.uuid4(), role=UserRole.manager),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [WpFileStatus.review_passed, WpFileStatus.archived])
async def test_central_content_guard_blocks_frozen_workpaper(status):
    from app.routers._wp_gate import raise_if_workpaper_frozen

    # 冻结判据在 PG / 无 bind 的替身会话上走 ``to_jsonb(working_paper)->>'status'`` + ``.first()``
    # （workpaper_content_freeze.load_workpaper_status）；原替身只给 scalar_one_or_none ⇒ 读到 MagicMock、
    # 判非终态放行，用例从未真正走到 423。按真实行形态 (status, is_deleted) 模拟。
    result = MagicMock(); result.first.return_value = (status.value, "false")
    db = AsyncMock(); db.execute = AsyncMock(return_value=result)
    with pytest.raises(HTTPException) as caught:
        await raise_if_workpaper_frozen(db, uuid.uuid4())
    assert caught.value.status_code == 423
    assert "内容已冻结" in str(caught.value.detail)


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [("draft", "false"), ("review_passed", "true"), None])
async def test_central_content_guard_allows_writable_or_deleted(row):
    """反向：未冻结、已删除、不存在的底稿不报 423（防上一条用例因替身形态恒绿 / 恒红）。"""
    from app.routers._wp_gate import raise_if_workpaper_frozen

    result = MagicMock(); result.first.return_value = row
    db = AsyncMock(); db.execute = AsyncMock(return_value=result)
    await raise_if_workpaper_frozen(db, uuid.uuid4())


def test_all_review_submission_routes_use_single_service_or_are_retired():
    from app.routers import workpaper_batch_status, wp_batch_ops, wp_batch_router, wp_review_router

    single = inspect.getsource(wp_review_router.submit_review)
    batch = inspect.getsource(wp_batch_router.batch_submit_review)
    legacy_status = inspect.getsource(workpaper_batch_status.batch_status_change)
    legacy_ops = inspect.getsource(wp_batch_ops.batch_submit_review)
    assert "WorkpaperReviewSubmissionService" in single
    assert "WorkpaperReviewSubmissionService" in batch
    assert "status_code=410" in legacy_status
    assert "status_code=410" in legacy_ops

@pytest.mark.asyncio
async def test_marking_rejected_revision_complete_resets_review_for_resubmit():
    from app.models.workpaper_models import WpStatus
    from app.services.working_paper_service import WorkingPaperService

    wp = _wp(WpFileStatus.revision_required, WpReviewStatus.level1_rejected)
    wp.updated_at = None
    index = SimpleNamespace(status=WpStatus.in_progress)
    first = MagicMock(); first.scalar_one_or_none.return_value = wp
    second = MagicMock(); second.scalar_one_or_none.return_value = index
    db = AsyncMock(); db.execute = AsyncMock(side_effect=[first, second])
    result = await WorkingPaperService().update_status(
        db, wp.id, "edit_complete", project_id=wp.project_id,
    )
    assert result["status"] == "edit_complete"
    assert result["review_status"] == "not_submitted"
    assert wp.review_status == WpReviewStatus.not_submitted
