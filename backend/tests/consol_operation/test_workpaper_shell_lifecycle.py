"""批 6.2：合并薄底稿壳的负责人 / 复核 / 回收站联动，与 parsed_data 不变量（SQLite 单测）。

验证：
- 指派 / 取消负责人（WpIndex 与 WorkingPaper 两层同步）。
- 指派 / 取消复核人。
- 复核状态机：提交 → 通过 / 退回 → 重新提交；非法转换抛 ReviewTransitionError。
- 回收站移入（kind=consol）后 get 返回 None，恢复后原样回来；只恢复 kind=consol 移入的。
- 业务 JSON 永不写入 parsed_data（R8.2 / ADR-CRW-006）。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # noqa: E305

import tests.conftest  # noqa: F401,E402
from app.models.base import Base, ProjectStatus, UserRole  # noqa: E402
from app.models.consol_workpaper_instance_models import ConsolWorkpaperInstance  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.workpaper_lifecycle_models import WorkpaperLifecycleEvent  # noqa: E402
from app.models.workpaper_models import (  # noqa: E402
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
)
from app.services import consol_workpaper_shell as shell  # noqa: E402
from app.services import workpaper_recycle_service as recycle_svc  # noqa: E402

YEAR = 2025
_TABLES = [
    User.__table__, Project.__table__,
    WpIndex.__table__, WorkingPaper.__table__,
    ConsolWorkpaperInstance.__table__, WorkpaperLifecycleEvent.__table__,
]

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db(monkeypatch) -> AsyncSession:
    # 可见性策略纪元用 pg_insert（PG 专用），SQLite 单测里置空：只断言底稿两层与事件表的改动。
    async def _no_epoch(_db, _pid, _action, _codes, _actor, _req):
        return None

    monkeypatch.setattr(recycle_svc, "_bump_epoch", _no_epoch)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _project() -> Project:
    return Project(
        id=uuid.uuid4(), name="【测试】壳生命周期_2025", client_name="【测试】壳生命周期",
        company_code="SH", audit_year=YEAR, report_scope="consolidated",
        status=ProjectStatus.execution,
    )


def _user(name: str) -> User:
    return User(
        id=uuid.uuid4(), username=name, email=f"{name}@shell.test",
        hashed_password="x", role=UserRole.auditor, is_active=True,
    )


async def _seed(db: AsyncSession) -> tuple[Project, User, User]:
    project, owner, reviewer = _project(), _user("owner"), _user("reviewer")
    db.add_all([project, owner, reviewer])
    await db.commit()
    await shell.ensure_consol_workpaper_shell(db, project.id)
    await db.commit()
    return project, owner, reviewer


class TestOwnerReviewer:
    async def test_assign_and_clear_owner_syncs_both_layers(self, db: AsyncSession):
        project, owner, _ = await _seed(db)
        result = await shell.set_consol_workpaper_owner(db, project.id, assigned_to=owner.id)
        await db.commit()
        assert result["assigned_to"] == str(owner.id)

        idx = (await db.execute(sa.select(WpIndex).where(WpIndex.project_id == project.id))).scalar_one()
        wp = (await db.execute(sa.select(WorkingPaper).where(WorkingPaper.project_id == project.id))).scalar_one()
        assert idx.assigned_to == owner.id
        assert wp.assigned_to == owner.id

        cleared = await shell.set_consol_workpaper_owner(db, project.id, assigned_to=None)
        await db.commit()
        assert cleared["assigned_to"] is None

    async def test_assign_reviewer_syncs_both_layers(self, db: AsyncSession):
        project, _, reviewer = await _seed(db)
        result = await shell.set_consol_workpaper_reviewer(db, project.id, reviewer=reviewer.id)
        await db.commit()
        assert result["reviewer"] == str(reviewer.id)
        idx = (await db.execute(sa.select(WpIndex).where(WpIndex.project_id == project.id))).scalar_one()
        wp = (await db.execute(sa.select(WorkingPaper).where(WorkingPaper.project_id == project.id))).scalar_one()
        assert idx.reviewer == reviewer.id
        assert wp.reviewer == reviewer.id

    async def test_owner_on_missing_shell_raises(self, db: AsyncSession):
        project = _project()
        db.add(project)
        await db.commit()
        with pytest.raises(shell.ShellNotFound):
            await shell.set_consol_workpaper_owner(db, project.id, assigned_to=None)


class TestReviewStateMachine:
    async def test_submit_then_approve(self, db: AsyncSession):
        project, owner, reviewer = await _seed(db)
        submitted = await shell.submit_consol_workpaper_review(db, project.id, actor_user_id=owner.id)
        await db.commit()
        assert submitted["review_status"] == WpReviewStatus.pending_level1.value
        assert submitted["status"] == WpFileStatus.under_review.value

        approved = await shell.review_consol_workpaper(db, project.id, approved=True, actor_user_id=reviewer.id)
        await db.commit()
        assert approved["review_status"] == WpReviewStatus.level1_passed.value
        assert approved["status"] == WpFileStatus.review_passed.value
        assert approved["rejection_reason"] is None

    async def test_submit_then_reject_requires_reason_then_resubmit(self, db: AsyncSession):
        project, owner, reviewer = await _seed(db)
        pid, owner_id, reviewer_id = project.id, owner.id, reviewer.id  # 先取标量，避免过期对象懒加载
        await shell.submit_consol_workpaper_review(db, pid, actor_user_id=owner_id)
        await db.commit()

        # 退回必须给原因：缺原因抛错，且不改状态（仍处于 pending_level1）
        with pytest.raises(shell.ReviewTransitionError):
            await shell.review_consol_workpaper(db, pid, approved=False, actor_user_id=reviewer_id)
        await db.rollback()
        still = await shell.get_consol_workpaper_shell(db, pid)
        assert still["review_status"] == WpReviewStatus.pending_level1.value

        rejected = await shell.review_consol_workpaper(
            db, pid, approved=False, actor_user_id=reviewer_id, rejection_reason="抵销分录缺失",
        )
        await db.commit()
        assert rejected["review_status"] == WpReviewStatus.level1_rejected.value
        assert rejected["status"] == WpFileStatus.revision_required.value
        assert rejected["rejection_reason"] == "抵销分录缺失"

        # 退回后可重新提交
        resubmitted = await shell.submit_consol_workpaper_review(db, pid, actor_user_id=owner_id)
        await db.commit()
        assert resubmitted["review_status"] == WpReviewStatus.pending_level1.value

    async def test_approve_without_submit_is_rejected(self, db: AsyncSession):
        project, _, reviewer = await _seed(db)
        with pytest.raises(shell.ReviewTransitionError):
            await shell.review_consol_workpaper(db, project.id, approved=True, actor_user_id=reviewer.id)

    async def test_double_submit_is_rejected(self, db: AsyncSession):
        project, owner, _ = await _seed(db)
        await shell.submit_consol_workpaper_review(db, project.id, actor_user_id=owner.id)
        await db.commit()
        with pytest.raises(shell.ReviewTransitionError):
            await shell.submit_consol_workpaper_review(db, project.id, actor_user_id=owner.id)


class TestRecycleBin:
    async def test_recycle_then_get_returns_none_then_restore(self, db: AsyncSession):
        project, owner, _ = await _seed(db)
        # 先指派负责人，确认恢复后原样回来
        await shell.set_consol_workpaper_owner(db, project.id, assigned_to=owner.id)
        await db.commit()

        moved = await shell.recycle_consol_workpaper_shell(db, project.id, actor_user_id=owner.id)
        await db.commit()
        assert moved == [shell.WP_CODE]
        # get 只看未删除 ⇒ None
        assert await shell.get_consol_workpaper_shell(db, project.id) is None
        # 两层都软删
        idx = (await db.execute(sa.select(WpIndex).where(WpIndex.project_id == project.id))).scalar_one()
        wp = (await db.execute(sa.select(WorkingPaper).where(WorkingPaper.project_id == project.id))).scalar_one()
        assert idx.is_deleted is True and wp.is_deleted is True
        # 去向记录标 kind=consol
        assert recycle_svc.last_recycle_kind(idx.cross_ref_codes) == recycle_svc.KIND_CONSOL

        restored = await shell.restore_consol_workpaper_shell(db, project.id, actor_user_id=owner.id)
        await db.commit()
        assert restored == [shell.WP_CODE]
        shell_now = await shell.get_consol_workpaper_shell(db, project.id)
        assert shell_now is not None
        assert shell_now["assigned_to"] == str(owner.id)  # 原样回来

    async def test_restore_only_consol_kind(self, db: AsyncSession):
        """手工（别的 kind）移入的，kind=consol 的恢复不会碰。"""
        project, owner, _ = await _seed(db)
        await recycle_svc.move_to_recycle_bin(
            db, project.id, [shell.WP_CODE], kind="manual", reason="手工删除", actor_user_id=owner.id,
        )
        await db.commit()
        restored = await shell.restore_consol_workpaper_shell(db, project.id, actor_user_id=owner.id)
        await db.commit()
        assert restored == []  # kind 不匹配，不恢复
        assert await shell.get_consol_workpaper_shell(db, project.id) is None

    async def test_recycle_idempotent_when_already_in_bin(self, db: AsyncSession):
        project, owner, _ = await _seed(db)
        await shell.recycle_consol_workpaper_shell(db, project.id, actor_user_id=owner.id)
        await db.commit()
        again = await shell.recycle_consol_workpaper_shell(db, project.id, actor_user_id=owner.id)
        await db.commit()
        assert again == []  # 已在回收站，不重复移入


class TestParsedDataInvariant:
    async def test_parsed_data_never_written_through_lifecycle(self, db: AsyncSession):
        project, owner, reviewer = await _seed(db)
        await shell.set_consol_workpaper_owner(db, project.id, assigned_to=owner.id)
        await shell.set_consol_workpaper_reviewer(db, project.id, reviewer=reviewer.id)
        await shell.submit_consol_workpaper_review(db, project.id, actor_user_id=owner.id)
        await shell.review_consol_workpaper(
            db, project.id, approved=False, actor_user_id=reviewer.id, rejection_reason="需补充",
        )
        await db.commit()
        wp = (await db.execute(sa.select(WorkingPaper).where(WorkingPaper.project_id == project.id))).scalar_one()
        assert wp.parsed_data is None

    async def test_ensure_guard_rejects_parsed_data(self, db: AsyncSession):
        """防御性：若壳的 WorkingPaper 被别处写了 parsed_data，再次 ensure 的不变量断言会打红。"""
        project = _project()
        db.add(project)
        await db.commit()
        await shell.ensure_consol_workpaper_shell(db, project.id)
        await db.commit()
        wp = (await db.execute(sa.select(WorkingPaper).where(WorkingPaper.project_id == project.id))).scalar_one()
        wp.parsed_data = {"rows": [1, 2, 3]}
        await db.flush()
        with pytest.raises(AssertionError):
            await shell.ensure_consol_workpaper_shell(db, project.id)
