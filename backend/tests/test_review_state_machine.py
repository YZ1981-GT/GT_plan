"""F8 配置驱动的复核流转状态机（spec platform-performance §9.5 方案 A）

测试覆盖：
1. _build_review_transitions 对 2/3/4 级的转换表正确性
2. update_review_status 按项目 review_config 走动态状态机（SQLite 真 ORM 行）
3. 批量端点 batch_review 的通过/退回/跳过逻辑
4. 前端直接发 levelN_passed 不再被拒（核心 bug 修复验证）
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectType, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.workpaper_models import WpFileStatus, WpIndex, WpReviewStatus, WpSourceType, WpStatus, WorkingPaper
from app.routers import batch_review, wp_review_router
from app.services.working_paper_service import WorkingPaperService, _build_review_transitions
from tests._test_auth_helper import FakeAuthUser

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

P = uuid.uuid4()
MGR, AUDITOR = uuid.uuid4(), uuid.uuid4()


# ─── _build_review_transitions 单元测试 ──────────────────────────────────────


class TestBuildReviewTransitions:
    """转换表生成器的纯函数测试。"""

    def test_two_levels_allows_direct_pass_from_pending(self):
        t = _build_review_transitions(2)
        assert "level1_passed" in t["pending_level1"]
        assert "level2_passed" in t["pending_level2"]

    def test_two_levels_terminal_is_level2_passed(self):
        t = _build_review_transitions(2)
        assert t["level2_passed"] == []

    def test_two_levels_level1_passed_advances_to_pending_level2(self):
        t = _build_review_transitions(2)
        assert t["level1_passed"] == ["pending_level2"]

    def test_three_levels_level2_passed_advances_to_pending_level3(self):
        t = _build_review_transitions(3)
        assert t["level2_passed"] == ["pending_level3"]
        assert t["level3_passed"] == []

    def test_four_levels_terminal_is_level4_passed(self):
        t = _build_review_transitions(4)
        assert t["level3_passed"] == ["pending_level4"]
        assert t["level4_passed"] == []

    def test_rejected_always_goes_to_not_submitted(self):
        for lvl in (2, 3, 4):
            t = _build_review_transitions(lvl)
            for n in range(1, lvl + 1):
                assert t[f"level{n}_rejected"] == ["not_submitted"], f"levels={lvl} level{n}_rejected"

    def test_in_progress_can_also_pass_or_reject(self):
        t = _build_review_transitions(2)
        assert "level1_passed" in t["level1_in_progress"]
        assert "level1_rejected" in t["level1_in_progress"]

    def test_pending_can_withdraw_to_not_submitted(self):
        t = _build_review_transitions(3)
        for n in range(1, 4):
            assert "not_submitted" in t[f"pending_level{n}"]


# ─── SQLite 真 ORM 行集成测试 ────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=MGR, username="mgr", email="m@t.l", hashed_password="x", role=UserRole.manager))
        session.add(User(id=AUDITOR, username="aud", email="a@t.l", hashed_password="x", role=UserRole.auditor))
        session.add(Project(id=P, name="【测试】复核状态机", client_name="测试",
                            project_type=ProjectType.annual, status=ProjectStatus.execution,
                            created_by=MGR, audit_year=2025))
        session.add(ProjectUser(project_id=P, user_id=MGR, role=ProjectUserRole.manager,
                                permission_level=PermissionLevel.edit))
        session.add(ProjectUser(project_id=P, user_id=AUDITOR, role=ProjectUserRole.auditor,
                                permission_level=PermissionLevel.edit))
        await session.commit()
        yield session
    await engine.dispose()


_wp_counter = 0


def _wp(db_session, wp_id=None, review_status="not_submitted", status="draft"):
    global _wp_counter
    _wp_counter += 1
    wp_id = wp_id or uuid.uuid4()
    code = f"D2-T{_wp_counter}"
    idx = WpIndex(id=uuid.uuid4(), project_id=P, wp_code=code, wp_name=f"测试{_wp_counter}", audit_cycle="D",
                  status=WpStatus.not_started)
    db_session.add(idx)
    wp = WorkingPaper(id=wp_id, project_id=P, wp_index_id=idx.id, file_path="x.xlsx",
                      source_type=WpSourceType.template, file_version=1,
                      review_status=WpReviewStatus(review_status), status=WpFileStatus(status))
    db_session.add(wp)
    return wp


class TestUpdateReviewStatus:
    """update_review_status 按项目 review_config 走动态状态机。"""

    @pytest.mark.asyncio
    async def test_direct_pass_from_pending_level1_succeeds(self, db):
        """核心 bug 修复：前端直接发 level1_passed 不再被拒。"""
        wp = _wp(db, review_status="pending_level1", status="under_review")
        await db.flush()
        svc = WorkingPaperService()
        result = await svc.update_review_status(db, wp.id, "level1_passed", project_id=P)
        assert result["review_status"] == "pending_level2"  # 非末级自动推进

    @pytest.mark.asyncio
    async def test_direct_reject_from_pending_level1_succeeds(self, db):
        wp = _wp(db, review_status="pending_level1", status="under_review")
        await db.flush()
        svc = WorkingPaperService()
        result = await svc.update_review_status(db, wp.id, "level1_rejected", project_id=P,
                                                 reason="格式不规范", rejected_by_id=MGR)
        assert result["review_status"] == "level1_rejected"
        assert result["status"] == "revision_required"

    @pytest.mark.asyncio
    async def test_last_level_passed_marks_review_passed(self, db):
        """默认 2 级：level2_passed 是终态，底稿标 review_passed。"""
        wp = _wp(db, review_status="pending_level2", status="under_review")
        await db.flush()
        svc = WorkingPaperService()
        result = await svc.update_review_status(db, wp.id, "level2_passed", project_id=P)
        assert result["review_status"] == "level2_passed"
        assert result["status"] == "review_passed"

    @pytest.mark.asyncio
    async def test_three_level_config_advances_to_level3(self, db):
        """项目配成 3 级：level2_passed 不是终态，推进到 pending_level3。"""
        # 设 review_config
        from sqlalchemy import update
        await db.execute(update(Project).where(Project.id == P).values(
            review_config={"levels": 3, "level_roles": {"L1": "manager", "L2": "partner", "L3": "qc"}}
        ))
        await db.flush()
        wp = _wp(db, review_status="pending_level2", status="under_review")
        await db.flush()
        svc = WorkingPaperService()
        result = await svc.update_review_status(db, wp.id, "level2_passed", project_id=P)
        assert result["review_status"] == "pending_level3"
        assert result["status"] != "review_passed"

    @pytest.mark.asyncio
    async def test_illegal_transition_raises(self, db):
        wp = _wp(db, review_status="not_submitted", status="draft")
        await db.flush()
        svc = WorkingPaperService()
        with pytest.raises(ValueError, match="复核状态转换不允许"):
            await svc.update_review_status(db, wp.id, "level1_passed", project_id=P)

    @pytest.mark.asyncio
    async def test_reject_without_reason_raises(self, db):
        wp = _wp(db, review_status="pending_level1", status="under_review")
        await db.flush()
        svc = WorkingPaperService()
        with pytest.raises(ValueError, match="退回时必须填写退回原因"):
            await svc.update_review_status(db, wp.id, "level1_rejected", project_id=P,
                                            reason="", rejected_by_id=MGR)


# ─── 批量端点测试 ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(db):
    app = FastAPI()
    app.include_router(wp_review_router.router)
    app.include_router(batch_review.router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    state: dict = {"user": MGR}

    async def _user():
        uid = state["user"]
        role = UserRole.manager if uid == MGR else UserRole.auditor
        return FakeAuthUser(user_id=uid, username="u", role=role)

    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = lambda uid: state.update(user=uid)  # type: ignore[attr-defined]
        yield c


class TestBatchReviewEndpoint:
    @pytest.mark.asyncio
    async def test_batch_approve_passes_reviewable_skips_others(self, client, db):
        wp1 = _wp(db, review_status="pending_level1", status="under_review")
        wp2 = _wp(db, review_status="not_submitted", status="draft")
        await db.commit()
        resp = await client.post(f"/api/projects/{P}/batch-review", json={
            "wp_ids": [str(wp1.id), str(wp2.id)], "action": "approve",
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success_count"] == 1
        assert body["skipped_count"] == 1
        assert any("not_submitted" in item["reason"] for item in body["skipped_items"])

    @pytest.mark.asyncio
    async def test_batch_reject_requires_comment(self, client, db):
        wp = _wp(db, review_status="pending_level1", status="under_review")
        await db.commit()
        resp = await client.post(f"/api/projects/{P}/batch-review", json={
            "wp_ids": [str(wp.id)], "action": "reject", "comment": "",
        })
        assert resp.status_code == 200
        assert resp.json()["skipped_count"] == 1
        assert "退回时必须填写退回原因" in resp.json()["skipped_items"][0]["reason"]

    @pytest.mark.asyncio
    async def test_batch_reject_with_reason_succeeds(self, client, db):
        wp = _wp(db, review_status="pending_level1", status="under_review")
        await db.commit()
        resp = await client.post(f"/api/projects/{P}/batch-review", json={
            "wp_ids": [str(wp.id)], "action": "reject", "comment": "格式不对",
        })
        assert resp.status_code == 200
        assert resp.json()["success_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_wp_ids_returns_zero(self, client, db):
        resp = await client.post(f"/api/projects/{P}/batch-review", json={
            "wp_ids": [], "action": "approve",
        })
        assert resp.status_code == 200
        assert resp.json() == {"success_count": 0, "skipped_count": 0, "skipped_items": []}

    @pytest.mark.asyncio
    async def test_invalid_action_returns_422(self, client, db):
        resp = await client.post(f"/api/projects/{P}/batch-review", json={
            "wp_ids": [str(uuid.uuid4())], "action": "invalid",
        })
        assert resp.status_code == 422
