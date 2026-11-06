"""Task 8：真实 PostgreSQL 复核退回、重提与多层角色闭环。"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.base import UserRole
from app.models.core import Project, User
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpQcResult,
    WpReviewStatus,
    WpSourceType,
)
from app.services.workpaper_review_submission_service import (
    WorkpaperReviewSubmissionService,
    assert_review_level_actor,
)
from app.services.working_paper_service import WorkingPaperService

pytestmark = [pytest.mark.asyncio, pytest.mark.pg_only]


def _require_disposable_database() -> None:
    database = make_url(settings.DATABASE_URL).database or ""
    declared = os.getenv("GT_PG_DISPOSABLE_DB", "")
    if declared != database:
        pytest.skip(
            "复核生命周期会写数据，只在 GT_PG_DISPOSABLE_DB 指向当前一次性库时运行"
        )


def _user(role: UserRole, label: str) -> User:
    token = uuid4().hex
    return User(
        id=uuid4(),
        username=f"release-{label}-{token[:10]}",
        email=f"release-{label}-{token[:10]}@example.test",
        hashed_password="not-used",
        role=role,
        is_active=True,
    )


async def _assert_actor(db, project_id, wp_id, status, actor) -> None:
    await assert_review_level_actor(
        db,
        project_id=project_id,
        wp_id=wp_id,
        new_review_status=status,
        actor=actor,
    )


async def test_reject_edit_complete_resubmit_and_three_level_role_chain():
    _require_disposable_database()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            auditor = _user(UserRole.auditor, "auditor")
            manager = _user(UserRole.manager, "manager")
            partner = _user(UserRole.partner, "partner")
            qc = _user(UserRole.qc, "qc")
            eqcr = _user(UserRole.eqcr, "eqcr")
            db.add_all([auditor, manager, partner, qc, eqcr])
            await db.flush()

            project = Project(
                id=uuid4(),
                name="【测试】发布阻断复核闭环",
                client_name="【测试】复核客户",
                audit_year=2025,
                template_type="soe",
                report_scope="standalone",
                manager_id=manager.id,
                partner_id=partner.id,
                review_config={
                    "levels": 3,
                    "level_roles": {"L1": "manager", "L2": "partner", "L3": "qc"},
                },
            )
            index = WpIndex(
                id=uuid4(),
                project_id=project.id,
                wp_code="D4-8",
                wp_name="【测试】销售毛利分析",
                audit_cycle="D",
                assigned_to=auditor.id,
                reviewer=manager.id,
            )
            wp = WorkingPaper(
                id=uuid4(),
                project_id=project.id,
                wp_index_id=index.id,
                file_path="release-review-test.xlsx",
                source_type=WpSourceType.template,
                status=WpFileStatus.draft,
                review_status=WpReviewStatus.not_submitted,
                assigned_to=auditor.id,
                reviewer=manager.id,
                created_by=auditor.id,
            )
            qc_result = WpQcResult(
                id=uuid4(),
                working_paper_id=wp.id,
                check_timestamp=datetime.now(timezone.utc),
                findings={},
                passed=True,
                blocking_count=0,
                warning_count=0,
                info_count=0,
                checked_by=auditor.id,
            )
            db.add(project)
            await db.flush()
            db.add(index)
            await db.flush()
            db.add(wp)
            await db.flush()
            db.add(qc_result)
            await db.flush()

            submit = WorkpaperReviewSubmissionService()
            submit._evaluate_gate = AsyncMock(return_value=None)
            submit._assert_sod = AsyncMock()
            with patch(
                "app.services.wp_review_service.WpReviewService.add_comment",
                new=AsyncMock(return_value={}),
            ):
                first = await submit.submit(
                    db,
                    project_id=project.id,
                    wp_id=wp.id,
                    actor_id=auditor.id,
                )
                assert first.can_submit is True
                assert (wp.status, wp.review_status) == (
                    WpFileStatus.under_review,
                    WpReviewStatus.pending_level1,
                )

                await _assert_actor(db, project.id, wp.id, "level1_rejected", manager)
                rejected = await WorkingPaperService().update_review_status(
                    db,
                    wp.id,
                    "level1_rejected",
                    project_id=project.id,
                    reason="请补充截止测试说明",
                    rejected_by_id=manager.id,
                )
                assert rejected["status"] == "revision_required"
                assert rejected["review_status"] == "level1_rejected"

                completed = await WorkingPaperService().update_status(
                    db, wp.id, "edit_complete", project_id=project.id
                )
                assert completed["review_status"] == "not_submitted"

                second = await submit.submit(
                    db,
                    project_id=project.id,
                    wp_id=wp.id,
                    actor_id=auditor.id,
                )
                assert second.can_submit is True
                assert wp.review_status == WpReviewStatus.pending_level1

                await _assert_actor(db, project.id, wp.id, "level1_passed", manager)
                await WorkingPaperService().update_review_status(
                    db, wp.id, "level1_passed", project_id=project.id
                )
                assert wp.review_status == WpReviewStatus.pending_level2

                await _assert_actor(db, project.id, wp.id, "level2_passed", partner)
                await WorkingPaperService().update_review_status(
                    db, wp.id, "level2_passed", project_id=project.id
                )
                assert wp.review_status == WpReviewStatus.pending_level3

                with pytest.raises(PermissionError, match="质控"):
                    await _assert_actor(db, project.id, wp.id, "level3_passed", eqcr)
                await _assert_actor(db, project.id, wp.id, "level3_passed", qc)
                await WorkingPaperService().update_review_status(
                    db, wp.id, "level3_passed", project_id=project.id
                )
                assert (wp.status, wp.review_status) == (
                    WpFileStatus.review_passed,
                    WpReviewStatus.level3_passed,
                )
            await db.rollback()
    finally:
        await engine.dispose()


async def test_content_write_and_terminal_transition_serialize_on_workpaper_row():
    """终态与内容写只能按锁顺序串行，禁止终态提交后内容再落地。"""
    import asyncio

    from app.services.workpaper_content_freeze import (
        WorkpaperContentFrozenError,
        assert_workpaper_content_writable,
    )

    _require_disposable_database()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    project_id, wp_id = uuid4(), uuid4()
    try:
        async with Session() as seed:
            actor = _user(UserRole.auditor, "freeze")
            project = Project(
                id=project_id,
                name="【测试】发布阻断终态并发",
                client_name="【测试】终态客户",
                audit_year=2025,
                template_type="soe",
                report_scope="standalone",
            )
            index = WpIndex(
                id=uuid4(), project_id=project_id, wp_code="E1", wp_name="货币资金",
                audit_cycle="E", assigned_to=actor.id,
            )
            wp = WorkingPaper(
                id=wp_id,
                project_id=project_id,
                wp_index_id=index.id,
                file_path="release-freeze-test.xlsx",
                source_type=WpSourceType.template,
                status=WpFileStatus.under_review,
                review_status=WpReviewStatus.pending_level1,
                assigned_to=actor.id,
                created_by=actor.id,
                parsed_data={"value": "before"},
            )
            seed.add(actor)
            await seed.flush()
            seed.add(project)
            await seed.flush()
            seed.add(index)
            await seed.flush()
            seed.add(wp)
            await seed.commit()

        writer_locked = asyncio.Event()
        allow_writer_commit = asyncio.Event()
        transition_started = asyncio.Event()

        async def writer() -> None:
            async with Session() as db:
                await assert_workpaper_content_writable(db, wp_id, for_update=True)
                writer_locked.set()
                await allow_writer_commit.wait()
                await db.execute(
                    sa.update(WorkingPaper)
                    .where(WorkingPaper.id == wp_id)
                    .values(parsed_data={"value": "written-before-terminal"})
                )
                await db.commit()

        async def terminal_transition() -> None:
            await writer_locked.wait()
            async with Session() as db:
                transition_started.set()
                row = (
                    await db.execute(
                        sa.select(WorkingPaper)
                        .where(WorkingPaper.id == wp_id)
                        .with_for_update()
                    )
                ).scalar_one()
                row.status = WpFileStatus.review_passed
                await db.commit()

        writer_task = asyncio.create_task(writer())
        transition_task = asyncio.create_task(terminal_transition())
        await writer_locked.wait()
        await transition_started.wait()
        await asyncio.sleep(0.05)
        assert not transition_task.done(), "终态事务不应越过正在进行的内容写行锁"
        allow_writer_commit.set()
        await asyncio.gather(writer_task, transition_task)

        async with Session() as verify:
            row = await verify.get(WorkingPaper, wp_id)
            assert row is not None
            assert row.status == WpFileStatus.review_passed
            assert row.parsed_data == {"value": "written-before-terminal"}
            with pytest.raises(WorkpaperContentFrozenError):
                await assert_workpaper_content_writable(verify, wp_id, for_update=True)
            await verify.rollback()
    finally:
        await engine.dispose()
