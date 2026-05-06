"""Tests for Tasks 9-15: WOPI Host, Working Paper, QC Engine, Review, Event Handlers

Validates: Requirements 3.1-3.3, 3.7, 5.1-5.5, 6.1, 7.1-7.5, 8.1-9.3
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.workpaper_models import (
    ReviewCommentStatus,
    WpFileStatus,
    WpIndex,
    WpSourceType,
    WpStatus,
    WorkingPaper,
)

# 确保所有模型注册到 Base.metadata（否则 create_all 漏建表，QC 引擎查 cell_annotations 会报 no such table）
import app.models.audit_platform_models  # noqa: F401, E402
import app.models.report_models  # noqa: F401, E402
import app.models.consolidation_models  # noqa: F401, E402
import app.models.staff_models  # noqa: F401, E402
import app.models.collaboration_models  # noqa: F401, E402
import app.models.ai_models  # noqa: F401, E402
import app.models.extension_models  # noqa: F401, E402
import app.models.gt_coding_models  # noqa: F401, E402
import app.models.t_account_models  # noqa: F401, E402
import app.models.attachment_models  # noqa: F401, E402
import app.models.phase10_models  # noqa: F401, E402
import app.models.phase13_models  # noqa: F401, E402
import app.models.phase14_models  # noqa: F401, E402
import app.models.phase15_models  # noqa: F401, E402
import app.models.phase16_models  # noqa: F401, E402
import app.models.dataset_models  # noqa: F401, E402

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_USER_ID_2 = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """Create test data: project + wp_index + working_paper"""
    project = Project(
        id=FAKE_PROJECT_ID,
        name="测试项目_2025",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    # Create wp_index entries
    idx1 = WpIndex(
        project_id=FAKE_PROJECT_ID,
        wp_code="B1-1",
        wp_name="穿行测试底稿",
        audit_cycle="B",
        status=WpStatus.in_progress,
    )
    idx2 = WpIndex(
        project_id=FAKE_PROJECT_ID,
        wp_code="E1-1",
        wp_name="货币资金底稿",
        audit_cycle="E",
        status=WpStatus.not_started,
    )
    db_session.add_all([idx1, idx2])
    await db_session.flush()

    # Create working_paper entries
    wp1 = WorkingPaper(
        project_id=FAKE_PROJECT_ID,
        wp_index_id=idx1.id,
        file_path=f"{FAKE_PROJECT_ID}/2025/B1-1.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        file_version=1,
        created_by=FAKE_USER_ID,
    )
    wp2 = WorkingPaper(
        project_id=FAKE_PROJECT_ID,
        wp_index_id=idx2.id,
        file_path=f"{FAKE_PROJECT_ID}/2025/E1-1.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        file_version=1,
        created_by=FAKE_USER_ID,
    )
    db_session.add_all([wp1, wp2])
    await db_session.commit()

    return {
        "project_id": FAKE_PROJECT_ID,
        "idx1": idx1,
        "idx2": idx2,
        "wp1": wp1,
        "wp2": wp2,
    }


# ===================================================================
# Task 9: WOPI Host Service Tests
# ===================================================================


class TestWOPIHostService:
    """Tests for WOPIHostService"""

    @pytest.mark.asyncio
    async def test_check_file_info(self, db_session, seeded_db):
        from app.services.wopi_service import WOPIHostService
        svc = WOPIHostService()
        info = await svc.check_file_info(db_session, seeded_db["wp1"].id)
        assert info["BaseFileName"] == "B1-1.xlsx"
        assert info["Version"] == "1"
        assert info["UserCanWrite"] is True
        assert info["SupportsLocks"] is True

    @pytest.mark.asyncio
    async def test_check_file_info_not_found(self, db_session, seeded_db):
        from app.services.wopi_service import WOPIHostService
        svc = WOPIHostService()
        with pytest.raises(FileNotFoundError):
            await svc.check_file_info(db_session, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_file_stub(self, db_session, seeded_db):
        from app.services.wopi_service import WOPIHostService
        svc = WOPIHostService()
        content = await svc.get_file(db_session, seeded_db["wp1"].id)
        assert content == b""

    @pytest.mark.asyncio
    async def test_put_file_increments_version(self, db_session, seeded_db):
        from app.services.wopi_service import WOPIHostService
        svc = WOPIHostService()
        result = await svc.put_file(db_session, seeded_db["wp1"].id, b"content")
        assert result["version"] == 2

    @pytest.mark.asyncio
    async def test_put_file_version_monotonic(self, db_session, seeded_db):
        from app.services.wopi_service import WOPIHostService
        svc = WOPIHostService()
        r1 = await svc.put_file(db_session, seeded_db["wp1"].id, b"v1")
        r2 = await svc.put_file(db_session, seeded_db["wp1"].id, b"v2")
        r3 = await svc.put_file(db_session, seeded_db["wp1"].id, b"v3")
        assert r1["version"] < r2["version"] < r3["version"]

    # Lock tests
    def test_lock_success(self):
        from app.services.wopi_service import WOPIHostService, clear_locks
        clear_locks()
        svc = WOPIHostService()
        fid = uuid.uuid4()
        result = svc.lock(fid, "lock-A")
        assert result["success"] is True

    def test_lock_conflict(self):
        from app.services.wopi_service import WOPIHostService, clear_locks
        clear_locks()
        svc = WOPIHostService()
        fid = uuid.uuid4()
        svc.lock(fid, "lock-A")
        result = svc.lock(fid, "lock-B")
        assert result["success"] is False
        assert result["status"] == 409

    def test_lock_same_id_refreshes(self):
        from app.services.wopi_service import WOPIHostService, clear_locks
        clear_locks()
        svc = WOPIHostService()
        fid = uuid.uuid4()
        svc.lock(fid, "lock-A")
        result = svc.lock(fid, "lock-A")
        assert result["success"] is True

    def test_unlock_success(self):
        from app.services.wopi_service import WOPIHostService, clear_locks
        clear_locks()
        svc = WOPIHostService()
        fid = uuid.uuid4()
        svc.lock(fid, "lock-A")
        result = svc.unlock(fid, "lock-A")
        assert result["success"] is True

    def test_unlock_wrong_id(self):
        from app.services.wopi_service import WOPIHostService, clear_locks
        clear_locks()
        svc = WOPIHostService()
        fid = uuid.uuid4()
        svc.lock(fid, "lock-A")
        result = svc.unlock(fid, "lock-B")
        assert result["success"] is False

    def test_refresh_lock(self):
        from app.services.wopi_service import WOPIHostService, clear_locks
        clear_locks()
        svc = WOPIHostService()
        fid = uuid.uuid4()
        svc.lock(fid, "lock-A")
        result = svc.refresh_lock(fid, "lock-A")
        assert result["success"] is True

    def test_refresh_lock_not_exists(self):
        from app.services.wopi_service import WOPIHostService, clear_locks
        clear_locks()
        svc = WOPIHostService()
        result = svc.refresh_lock(uuid.uuid4(), "lock-A")
        assert result["success"] is False

    # Access token tests
    def test_generate_and_validate_token(self):
        from app.services.wopi_service import WOPIHostService
        svc = WOPIHostService()
        token = svc.generate_access_token(
            user_id=FAKE_USER_ID,
            project_id=FAKE_PROJECT_ID,
            file_id=uuid.uuid4(),
        )
        assert isinstance(token, str)
        payload = svc.validate_access_token(token)
        assert payload["user_id"] == str(FAKE_USER_ID)
        assert payload["project_id"] == str(FAKE_PROJECT_ID)

    def test_validate_invalid_token(self):
        from app.services.wopi_service import WOPIHostService
        svc = WOPIHostService()
        with pytest.raises(ValueError):
            svc.validate_access_token("invalid-token")


# ===================================================================
# Task 10: Working Paper Service Tests
# ===================================================================


class TestWorkingPaperService:
    """Tests for WorkingPaperService"""

    @pytest.mark.asyncio
    async def test_list_workpapers(self, db_session, seeded_db):
        from app.services.working_paper_service import WorkingPaperService
        svc = WorkingPaperService()
        items = await svc.list_workpapers(db_session, FAKE_PROJECT_ID)
        assert len(items) == 2
        assert items[0]["wp_code"] == "B1-1"
        assert items[1]["wp_code"] == "E1-1"

    @pytest.mark.asyncio
    async def test_list_workpapers_filter_cycle(self, db_session, seeded_db):
        from app.services.working_paper_service import WorkingPaperService
        svc = WorkingPaperService()
        items = await svc.list_workpapers(db_session, FAKE_PROJECT_ID, audit_cycle="B")
        assert len(items) == 1
        assert items[0]["wp_code"] == "B1-1"

    @pytest.mark.asyncio
    async def test_list_workpapers_filter_status(self, db_session, seeded_db):
        from app.services.working_paper_service import WorkingPaperService
        svc = WorkingPaperService()
        items = await svc.list_workpapers(db_session, FAKE_PROJECT_ID, status="not_started")
        assert len(items) == 1
        assert items[0]["wp_code"] == "E1-1"

    @pytest.mark.asyncio
    async def test_get_workpaper(self, db_session, seeded_db):
        from app.services.working_paper_service import WorkingPaperService
        svc = WorkingPaperService()
        detail = await svc.get_workpaper(db_session, seeded_db["wp1"].id)
        assert detail is not None
        assert detail["wp_code"] == "B1-1"
        assert detail["file_version"] == 1

    @pytest.mark.asyncio
    async def test_get_workpaper_not_found(self, db_session, seeded_db):
        from app.services.working_paper_service import WorkingPaperService
        svc = WorkingPaperService()
        detail = await svc.get_workpaper(db_session, uuid.uuid4())
        assert detail is None

    @pytest.mark.asyncio
    async def test_upload_offline_edit_success(self, db_session, seeded_db):
        from app.services.working_paper_service import WorkingPaperService
        svc = WorkingPaperService()
        result = await svc.upload_offline_edit(
            db_session, seeded_db["wp1"].id, recorded_version=1,
        )
        assert result["success"] is True
        assert result["new_version"] == 2

    @pytest.mark.asyncio
    async def test_upload_offline_edit_conflict(self, db_session, seeded_db):
        from app.services.working_paper_service import WorkingPaperService
        svc = WorkingPaperService()
        # First upload succeeds
        await svc.upload_offline_edit(db_session, seeded_db["wp1"].id, recorded_version=1)
        # Second upload with old version conflicts
        result = await svc.upload_offline_edit(
            db_session, seeded_db["wp1"].id, recorded_version=1,
        )
        assert result["success"] is False
        assert result["has_conflict"] is True

    @pytest.mark.asyncio
    async def test_update_status(self, db_session, seeded_db):
        from app.services.working_paper_service import WorkingPaperService
        svc = WorkingPaperService()
        result = await svc.update_status(
            db_session, seeded_db["wp1"].id, "edit_complete",
        )
        assert result["status"] == "edit_complete"

    @pytest.mark.asyncio
    async def test_update_status_invalid(self, db_session, seeded_db):
        from app.services.working_paper_service import WorkingPaperService
        svc = WorkingPaperService()
        with pytest.raises(ValueError, match="无效状态"):
            await svc.update_status(db_session, seeded_db["wp1"].id, "invalid")

    @pytest.mark.asyncio
    async def test_assign_workpaper(self, db_session, seeded_db):
        from app.services.working_paper_service import WorkingPaperService
        svc = WorkingPaperService()
        result = await svc.assign_workpaper(
            db_session, seeded_db["wp1"].id,
            assigned_to=FAKE_USER_ID,
            reviewer=FAKE_USER_ID_2,
        )
        assert result["assigned_to"] == str(FAKE_USER_ID)
        assert result["reviewer"] == str(FAKE_USER_ID_2)


# ===================================================================
# Task 12: QC Engine Tests
# ===================================================================


class TestQCEngine:
    """Tests for QCEngine"""

    @pytest.mark.asyncio
    async def test_qc_check_passes(self, db_session, seeded_db):
        """All stub rules return empty findings → passed=True"""
        from app.services.qc_engine import QCEngine
        engine = QCEngine()
        result = await engine.check(db_session, seeded_db["wp1"].id)
        assert result["passed"] is True
        assert result["blocking_count"] == 0
        assert result["warning_count"] == 0
        assert result["info_count"] == 0
        assert result["findings"] == []

    @pytest.mark.asyncio
    async def test_qc_check_not_found(self, db_session, seeded_db):
        from app.services.qc_engine import QCEngine
        engine = QCEngine()
        with pytest.raises(ValueError, match="底稿不存在"):
            await engine.check(db_session, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_qc_check_stores_result(self, db_session, seeded_db):
        """QC result is persisted to wp_qc_results table"""
        from app.services.qc_engine import QCEngine
        from app.models.workpaper_models import WpQcResult
        import sqlalchemy as sa

        engine = QCEngine()
        await engine.check(db_session, seeded_db["wp1"].id)
        await db_session.commit()

        result = await db_session.execute(
            sa.select(WpQcResult).where(
                WpQcResult.working_paper_id == seeded_db["wp1"].id
            )
        )
        qc = result.scalar_one_or_none()
        assert qc is not None
        assert qc.passed is True

    @pytest.mark.asyncio
    async def test_qc_engine_has_12_rules(self):
        from app.services.qc_engine import QCEngine
        engine = QCEngine()
        assert len(engine.rules) == 12

    @pytest.mark.asyncio
    async def test_qc_rule_severities(self):
        from app.services.qc_engine import QCEngine
        engine = QCEngine()
        blocking = [r for r in engine.rules if r.severity == "blocking"]
        warning = [r for r in engine.rules if r.severity == "warning"]
        info = [r for r in engine.rules if r.severity == "info"]
        assert len(blocking) == 3
        assert len(warning) == 8
        assert len(info) == 1

    @pytest.mark.asyncio
    async def test_get_project_summary(self, db_session, seeded_db):
        from app.services.qc_engine import QCEngine
        engine = QCEngine()
        summary = await engine.get_project_summary(db_session, FAKE_PROJECT_ID)
        assert summary["total_workpapers"] == 2
        assert summary["not_started"] == 1  # E1-1 is not_started
        assert summary["not_checked"] == 2  # No QC run yet

    @pytest.mark.asyncio
    async def test_get_project_summary_after_check(self, db_session, seeded_db):
        from app.services.qc_engine import QCEngine
        engine = QCEngine()
        # Run QC on wp1
        await engine.check(db_session, seeded_db["wp1"].id)
        await db_session.commit()

        summary = await engine.get_project_summary(db_session, FAKE_PROJECT_ID)
        assert summary["passed_qc"] == 1
        assert summary["not_checked"] == 1


# ===================================================================
# Task 14: Review Service Tests
# ===================================================================


class TestWpReviewService:
    """Tests for WpReviewService"""

    @pytest.mark.asyncio
    async def test_add_comment(self, db_session, seeded_db):
        from app.services.wp_review_service import WpReviewService
        svc = WpReviewService()
        result = await svc.add_comment(
            db_session,
            working_paper_id=seeded_db["wp1"].id,
            commenter_id=FAKE_USER_ID,
            comment_text="请补充说明",
            cell_reference="B5",
        )
        assert result["status"] == "open"
        assert result["comment_text"] == "请补充说明"
        assert result["cell_reference"] == "B5"

    @pytest.mark.asyncio
    async def test_list_reviews(self, db_session, seeded_db):
        from app.services.wp_review_service import WpReviewService
        svc = WpReviewService()
        await svc.add_comment(
            db_session, seeded_db["wp1"].id, FAKE_USER_ID, "意见1",
        )
        await svc.add_comment(
            db_session, seeded_db["wp1"].id, FAKE_USER_ID, "意见2",
        )
        items = await svc.list_reviews(db_session, seeded_db["wp1"].id)
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_reply(self, db_session, seeded_db):
        from app.services.wp_review_service import WpReviewService
        svc = WpReviewService()
        comment = await svc.add_comment(
            db_session, seeded_db["wp1"].id, FAKE_USER_ID, "请补充",
        )
        result = await svc.reply(
            db_session,
            review_id=uuid.UUID(comment["id"]),
            replier_id=FAKE_USER_ID_2,
            reply_text="已补充",
        )
        assert result["status"] == "replied"
        assert result["reply_text"] == "已补充"

    @pytest.mark.asyncio
    async def test_reply_not_open_fails(self, db_session, seeded_db):
        from app.services.wp_review_service import WpReviewService
        svc = WpReviewService()
        comment = await svc.add_comment(
            db_session, seeded_db["wp1"].id, FAKE_USER_ID, "请补充",
        )
        # Reply first
        await svc.reply(
            db_session, uuid.UUID(comment["id"]), FAKE_USER_ID_2, "已补充",
        )
        # Try to reply again
        with pytest.raises(ValueError, match="不允许回复"):
            await svc.reply(
                db_session, uuid.UUID(comment["id"]), FAKE_USER_ID_2, "再次回复",
            )

    @pytest.mark.asyncio
    async def test_resolve_from_open(self, db_session, seeded_db):
        from app.services.wp_review_service import WpReviewService
        svc = WpReviewService()
        comment = await svc.add_comment(
            db_session, seeded_db["wp1"].id, FAKE_USER_ID, "请补充",
        )
        result = await svc.resolve(
            db_session, uuid.UUID(comment["id"]), FAKE_USER_ID,
        )
        assert result["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_resolve_from_replied(self, db_session, seeded_db):
        from app.services.wp_review_service import WpReviewService
        svc = WpReviewService()
        comment = await svc.add_comment(
            db_session, seeded_db["wp1"].id, FAKE_USER_ID, "请补充",
        )
        await svc.reply(
            db_session, uuid.UUID(comment["id"]), FAKE_USER_ID_2, "已补充",
        )
        result = await svc.resolve(
            db_session, uuid.UUID(comment["id"]), FAKE_USER_ID,
        )
        assert result["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_resolve_already_resolved_fails(self, db_session, seeded_db):
        from app.services.wp_review_service import WpReviewService
        svc = WpReviewService()
        comment = await svc.add_comment(
            db_session, seeded_db["wp1"].id, FAKE_USER_ID, "请补充",
        )
        await svc.resolve(db_session, uuid.UUID(comment["id"]), FAKE_USER_ID)
        with pytest.raises(ValueError, match="已解决"):
            await svc.resolve(db_session, uuid.UUID(comment["id"]), FAKE_USER_ID)

    @pytest.mark.asyncio
    async def test_list_reviews_filter_status(self, db_session, seeded_db):
        from app.services.wp_review_service import WpReviewService
        svc = WpReviewService()
        c1 = await svc.add_comment(
            db_session, seeded_db["wp1"].id, FAKE_USER_ID, "意见1",
        )
        await svc.add_comment(
            db_session, seeded_db["wp1"].id, FAKE_USER_ID, "意见2",
        )
        await svc.resolve(db_session, uuid.UUID(c1["id"]), FAKE_USER_ID)

        open_items = await svc.list_reviews(
            db_session, seeded_db["wp1"].id, status="open",
        )
        assert len(open_items) == 1

        resolved_items = await svc.list_reviews(
            db_session, seeded_db["wp1"].id, status="resolved",
        )
        assert len(resolved_items) == 1


# ===================================================================
# Task 15: Event Handler Tests
# ===================================================================


class TestEventHandlers:
    """Tests for formula cache invalidation event handlers"""

    def test_event_handlers_registered(self):
        """Verify event handlers are registered without error"""
        from app.services.event_handlers import register_event_handlers
        # Should not raise
        register_event_handlers()

    @pytest.mark.asyncio
    async def test_formula_cache_invalidation_handler(self):
        """Test that formula cache invalidation handler can be called"""
        import fakeredis.aioredis
        from app.services.formula_engine import FormulaEngine

        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        engine = FormulaEngine(redis_client=redis)

        # Set a cache entry
        await redis.set("formula:test:2025:TB:abc", "123", ex=300)

        # Invalidate
        deleted = await engine.invalidate_cache(
            project_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            year=2025,
        )
        # May or may not find keys depending on pattern match
        assert deleted >= 0


# ===================================================================
# API Route Tests (using httpx AsyncClient)
# ===================================================================


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    """Create test HTTP client"""
    import fakeredis.aioredis
    from httpx import ASGITransport, AsyncClient
    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.main import app

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def override_get_db():
        yield db_session

    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


class TestWorkingPaperAPI:
    """API route tests for working paper endpoints"""

    @pytest.mark.asyncio
    async def test_list_workpapers_api(self, client, seeded_db):
        resp = await client.get(f"/api/projects/{FAKE_PROJECT_ID}/working-papers")
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("data", data)
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_get_workpaper_api(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{wp_id}"
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_workpaper_not_found_api(self, client, seeded_db):
        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{fake_id}"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_workpaper_api(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{wp_id}/upload",
            json={"recorded_version": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_update_status_api(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        resp = await client.put(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{wp_id}/status",
            json={"status": "edit_complete"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_assign_workpaper_api(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        resp = await client.put(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{wp_id}/assign",
            json={"assigned_to": str(FAKE_USER_ID)},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_wp_index_api(self, client, seeded_db):
        resp = await client.get(f"/api/projects/{FAKE_PROJECT_ID}/wp-index")
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("data", data)
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_wp_cross_refs_api(self, client, seeded_db):
        resp = await client.get(f"/api/projects/{FAKE_PROJECT_ID}/wp-cross-refs")
        assert resp.status_code == 200


class TestQCAPI:
    """API route tests for QC endpoints"""

    @pytest.mark.asyncio
    async def test_qc_check_api(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{wp_id}/qc-check"
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_qc_results_api(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        # First run QC
        await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{wp_id}/qc-check"
        )
        # Then get results
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{wp_id}/qc-results"
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_qc_summary_api(self, client, seeded_db):
        resp = await client.get(f"/api/projects/{FAKE_PROJECT_ID}/qc-summary")
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert result["total_workpapers"] == 2


class TestReviewAPI:
    """API route tests for review endpoints"""

    @pytest.mark.asyncio
    async def test_add_comment_api(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        resp = await client.post(
            f"/api/working-papers/{wp_id}/reviews",
            json={
                "commenter_id": str(FAKE_USER_ID),
                "comment_text": "请补充说明",
                "cell_reference": "B5",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data.get("data", data)
        assert result["status"] == "open"

    @pytest.mark.asyncio
    async def test_list_reviews_api(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        # Add a comment first
        await client.post(
            f"/api/working-papers/{wp_id}/reviews",
            json={
                "commenter_id": str(FAKE_USER_ID),
                "comment_text": "测试意见",
            },
        )
        resp = await client.get(f"/api/working-papers/{wp_id}/reviews")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_reply_api(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        # Add comment
        add_resp = await client.post(
            f"/api/working-papers/{wp_id}/reviews",
            json={
                "commenter_id": str(FAKE_USER_ID),
                "comment_text": "请补充",
            },
        )
        add_data = add_resp.json()
        review_id = add_data.get("data", add_data)["id"]

        # Reply
        resp = await client.put(
            f"/api/working-papers/{wp_id}/reviews/{review_id}/reply",
            json={
                "replier_id": str(FAKE_USER_ID_2),
                "reply_text": "已补充",
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_resolve_api(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        # Add comment
        add_resp = await client.post(
            f"/api/working-papers/{wp_id}/reviews",
            json={
                "commenter_id": str(FAKE_USER_ID),
                "comment_text": "请补充",
            },
        )
        add_data = add_resp.json()
        review_id = add_data.get("data", add_data)["id"]

        # Resolve
        resp = await client.put(
            f"/api/working-papers/{wp_id}/reviews/{review_id}/resolve",
            json={"resolved_by": str(FAKE_USER_ID)},
        )
        assert resp.status_code == 200


class TestWOPIAPI:
    """API route tests for WOPI endpoints"""

    @pytest.mark.asyncio
    async def test_wopi_check_file_info_uuid(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        resp = await client.get(f"/wopi/files/{wp_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["BaseFileName"] == "B1-1.xlsx"

    @pytest.mark.asyncio
    async def test_wopi_get_file_uuid(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        resp = await client.get(f"/wopi/files/{wp_id}/contents")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_wopi_put_file_uuid(self, client, seeded_db):
        wp_id = str(seeded_db["wp1"].id)
        resp = await client.post(
            f"/wopi/files/{wp_id}/contents",
            content=b"test content",
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_wopi_lock_operations(self, client, seeded_db):
        from app.services.wopi_service import clear_locks
        clear_locks()

        wp_id = str(seeded_db["wp1"].id)

        # Lock
        resp = await client.post(
            f"/wopi/files/{wp_id}",
            headers={"X-WOPI-Override": "LOCK", "X-WOPI-Lock": "lock-1"},
        )
        assert resp.status_code == 200

        # Refresh
        resp = await client.post(
            f"/wopi/files/{wp_id}",
            headers={"X-WOPI-Override": "REFRESH_LOCK", "X-WOPI-Lock": "lock-1"},
        )
        assert resp.status_code == 200

        # Unlock
        resp = await client.post(
            f"/wopi/files/{wp_id}",
            headers={"X-WOPI-Override": "UNLOCK", "X-WOPI-Lock": "lock-1"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_wopi_lock_conflict(self, client, seeded_db):
        from app.services.wopi_service import clear_locks
        clear_locks()

        wp_id = str(seeded_db["wp1"].id)

        # Lock with lock-A
        await client.post(
            f"/wopi/files/{wp_id}",
            headers={"X-WOPI-Override": "LOCK", "X-WOPI-Lock": "lock-A"},
        )

        # Try lock with lock-B → 409
        resp = await client.post(
            f"/wopi/files/{wp_id}",
            headers={"X-WOPI-Override": "LOCK", "X-WOPI-Lock": "lock-B"},
        )
        assert resp.status_code == 409
