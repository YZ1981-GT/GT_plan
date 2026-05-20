"""合伙人仪表盘聚合端点单元测试

Validates: Requirements 9.1, 9.2, 9.5, 9.6

测试覆盖：
- GET /summary happy path（mock 各子查询返回正常数据）
- 认证守卫（未登录 → 401）
- 权限校验（无项目访问权限 → 403）
- project 不存在 → 404
- 单个子查询失败 → 对应字段 null + errors 非空 + 其他字段正常
- 全部子查询失败 → 所有字段 null + errors 全量
- 响应结构完整性（所有字段存在）
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project
from app.routers.dashboard_aggregator import router as dashboard_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

# ---------------------------------------------------------------------------
# Fake user for dependency override
# ---------------------------------------------------------------------------

PROJECT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class _FakeUser:
    """轻量级用户替身 — 绕开 User ORM 的 AuditMixin 字段依赖。"""

    def __init__(self, uid: uuid.UUID, role: UserRole = UserRole.admin):
        self.id = uid
        self.username = "test_partner"
        self.email = "partner@test.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


# ---------------------------------------------------------------------------
# Mock data for sub-queries
# ---------------------------------------------------------------------------

MOCK_CYCLE_PROGRESS = [
    {
        "cycle": "D",
        "cycle_name": "销售收入",
        "total_procedures": 10,
        "completed_procedures": 5,
        "trimmed_procedures": 2,
        "progress_rate": 62.5,
    }
]

MOCK_VR_SUMMARY = {
    "total_rules": 33,
    "blocking_failed": 2,
    "all_passed": False,
    "by_cycle": [
        {
            "cycle": "D",
            "blocking_failed": 2,
            "failed_rules": [
                {"rule_id": "d4_revenue", "rule_name": "d4_revenue", "details": "mismatch"},
            ],
        }
    ],
}

MOCK_OPEN_REVIEWS = {
    "total": 3,
    "by_layer": {"L5": 1, "L4": 2},
    "items": [
        {
            "id": str(uuid.uuid4()),
            "review_layer": "L5",
            "summary": "需要补充说明",
            "created_at": "2026-05-20T10:00:00",
            "wp_code": "D4-1",
            "sheet_name": "审定表",
            "cell_ref": "B5",
        }
    ],
}

MOCK_TIMELINE = {
    "current_stage": "execution",
    "stages": [
        {"name": "planning", "status": "completed", "entered_at": "2026-01-01T00:00:00", "completed_at": "2026-02-01T00:00:00", "summary": None},
        {"name": "execution", "status": "current", "entered_at": "2026-02-01T00:00:00", "completed_at": None, "summary": None},
        {"name": "review", "status": "pending", "entered_at": None, "completed_at": None, "summary": None},
        {"name": "reporting", "status": "pending", "entered_at": None, "completed_at": None, "summary": None},
    ],
}

MOCK_TRIMMING = {
    "available": True,
    "total_procedures": 100,
    "trimmed_count": 15,
    "trim_rate": 15.0,
    "by_cycle": [
        {"cycle": "D", "total": 10, "trimmed": 2, "rate": 20.0, "warning": False},
    ],
}


def _build_mock_summary_result(
    *,
    cycle_progress=MOCK_CYCLE_PROGRESS,
    vr_summary=MOCK_VR_SUMMARY,
    open_reviews=MOCK_OPEN_REVIEWS,
    timeline=MOCK_TIMELINE,
    trimming_overview=MOCK_TRIMMING,
    errors=None,
) -> dict:
    """Build a complete mock summary result dict."""
    return {
        "project_name": "测试项目",
        "audit_year": 2025,
        "last_updated": datetime.now().isoformat(),
        "cycle_progress": cycle_progress,
        "vr_summary": vr_summary,
        "open_reviews": open_reviews,
        "timeline": timeline,
        "trimming_overview": trimming_overview,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每测试独立内存库。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _make_app_authenticated(db_session: AsyncSession, user: _FakeUser | None = None) -> FastAPI:
    """构造带认证的测试 app。"""
    app = FastAPI()
    app.include_router(dashboard_router)

    async def _override_db():
        yield db_session

    if user is not None:
        async def _override_user():
            return user

        # Override require_project_access to return the fake user directly
        def _override_project_access(min_permission: str = "readonly"):
            async def _dep(project_id: uuid.UUID):
                return user
            return _dep

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[require_project_access] = _override_project_access
    else:
        app.dependency_overrides[get_db] = _override_db

    return app


def _make_app_no_auth(db_session: AsyncSession) -> FastAPI:
    """构造不带认证覆盖的测试 app（测试 401）。"""
    app = FastAPI()
    app.include_router(dashboard_router)

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    return app


def _make_app_forbidden(db_session: AsyncSession) -> FastAPI:
    """构造返回 403 的测试 app（模拟无项目访问权限）。"""
    from fastapi import HTTPException

    app = FastAPI()
    app.include_router(dashboard_router)

    async def _override_db():
        yield db_session

    # Need a fake user so get_current_user doesn't block with 401
    non_admin_user = _FakeUser(USER_ID, role=UserRole.auditor)

    async def _override_user():
        return non_admin_user

    def _override_project_access_forbidden(min_permission: str = "readonly"):
        async def _dep(project_id: uuid.UUID):
            raise HTTPException(status_code=403, detail="权限不足")
        return _dep

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[require_project_access] = _override_project_access_forbidden
    return app


# ---------------------------------------------------------------------------
# Tests: Happy Path
# ---------------------------------------------------------------------------


class TestDashboardSummaryHappyPath:
    """GET /summary happy path — mock 各子查询返回正常数据。"""

    @pytest.mark.asyncio
    async def test_returns_200_with_full_data(self, db_session):
        """正常请求返回 200 + 完整仪表盘数据。"""
        user = _FakeUser(USER_ID, role=UserRole.admin)
        app = _make_app_authenticated(db_session, user)

        mock_result = _build_mock_summary_result()

        with patch(
            "app.routers.dashboard_aggregator.DashboardAggregatorService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_summary = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    f"/api/projects/{PROJECT_ID}/dashboard/summary"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["project_name"] == "测试项目"
        assert body["audit_year"] == 2025
        assert body["cycle_progress"] is not None
        assert body["vr_summary"] is not None
        assert body["open_reviews"] is not None
        assert body["timeline"] is not None
        assert body["trimming_overview"] is not None
        assert body["errors"] is None


# ---------------------------------------------------------------------------
# Tests: Authentication Guard (401)
# ---------------------------------------------------------------------------


class TestDashboardAuthGuard:
    """认证守卫 — 未登录 → 401。"""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, db_session):
        """无 Authorization header 时返回 401。"""
        app = _make_app_no_auth(db_session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/projects/{PROJECT_ID}/dashboard/summary"
            )

        assert resp.status_code in (401, 403)  # HTTPBearer returns 403 when no header


# ---------------------------------------------------------------------------
# Tests: Permission Check (403)
# ---------------------------------------------------------------------------


class TestDashboardPermissionCheck:
    """权限校验 — 无项目访问权限 → 403。"""

    @pytest.mark.asyncio
    async def test_no_project_access_returns_403(self, db_session):
        """用户无项目访问权限时返回 403。"""
        app = _make_app_forbidden(db_session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/projects/{PROJECT_ID}/dashboard/summary"
            )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: Project Not Found (404)
# ---------------------------------------------------------------------------


class TestDashboardProjectNotFound:
    """project 不存在 → 404。"""

    @pytest.mark.asyncio
    async def test_project_not_found_returns_404(self, db_session):
        """project_id 不存在时返回 404。"""
        user = _FakeUser(USER_ID, role=UserRole.admin)
        app = _make_app_authenticated(db_session, user)

        # Service returns project_not_found marker
        mock_result = {"error": "project_not_found"}

        with patch(
            "app.routers.dashboard_aggregator.DashboardAggregatorService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_summary = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    f"/api/projects/{uuid.uuid4()}/dashboard/summary"
                )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Single Sub-query Failure (Graceful Degradation)
# ---------------------------------------------------------------------------


class TestDashboardSingleSubQueryFailure:
    """单个子查询失败 → 对应字段 null + errors 非空 + 其他字段正常。"""

    @pytest.mark.asyncio
    async def test_vr_summary_failure_degrades_gracefully(self, db_session):
        """vr_summary 子查询失败时，该字段为 null，其他字段正常。"""
        user = _FakeUser(USER_ID, role=UserRole.admin)
        app = _make_app_authenticated(db_session, user)

        mock_result = _build_mock_summary_result(
            vr_summary=None,
            errors={"vr_summary": "ConsistencyGate timeout"},
        )

        with patch(
            "app.routers.dashboard_aggregator.DashboardAggregatorService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_summary = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    f"/api/projects/{PROJECT_ID}/dashboard/summary"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["vr_summary"] is None
        assert body["errors"] is not None
        assert "vr_summary" in body["errors"]
        # Other fields should still be present
        assert body["cycle_progress"] is not None
        assert body["open_reviews"] is not None
        assert body["timeline"] is not None
        assert body["trimming_overview"] is not None

    @pytest.mark.asyncio
    async def test_open_reviews_failure_degrades_gracefully(self, db_session):
        """open_reviews 子查询失败时，该字段为 null，其他字段正常。"""
        user = _FakeUser(USER_ID, role=UserRole.admin)
        app = _make_app_authenticated(db_session, user)

        mock_result = _build_mock_summary_result(
            open_reviews=None,
            errors={"open_reviews": "Database connection error"},
        )

        with patch(
            "app.routers.dashboard_aggregator.DashboardAggregatorService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_summary = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    f"/api/projects/{PROJECT_ID}/dashboard/summary"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["open_reviews"] is None
        assert body["errors"] is not None
        assert "open_reviews" in body["errors"]
        assert body["cycle_progress"] is not None
        assert body["vr_summary"] is not None

    @pytest.mark.asyncio
    async def test_cycle_progress_failure_degrades_gracefully(self, db_session):
        """cycle_progress 子查询失败时，该字段为 null，其他字段正常。"""
        user = _FakeUser(USER_ID, role=UserRole.admin)
        app = _make_app_authenticated(db_session, user)

        mock_result = _build_mock_summary_result(
            cycle_progress=None,
            errors={"cycle_progress": "Query timeout"},
        )

        with patch(
            "app.routers.dashboard_aggregator.DashboardAggregatorService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_summary = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    f"/api/projects/{PROJECT_ID}/dashboard/summary"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["cycle_progress"] is None
        assert body["errors"] is not None
        assert "cycle_progress" in body["errors"]
        assert body["vr_summary"] is not None
        assert body["open_reviews"] is not None


# ---------------------------------------------------------------------------
# Tests: All Sub-queries Fail
# ---------------------------------------------------------------------------


class TestDashboardAllSubQueriesFail:
    """全部子查询失败 → 所有字段 null + errors 全量。"""

    @pytest.mark.asyncio
    async def test_all_failures_returns_all_null_with_errors(self, db_session):
        """所有子查询失败时，所有可选字段为 null，errors 包含全部失败信息。"""
        user = _FakeUser(USER_ID, role=UserRole.admin)
        app = _make_app_authenticated(db_session, user)

        mock_result = _build_mock_summary_result(
            cycle_progress=None,
            vr_summary=None,
            open_reviews=None,
            timeline=None,
            trimming_overview=None,
            errors={
                "cycle_progress": "timeout",
                "vr_summary": "ConsistencyGate unavailable",
                "open_reviews": "DB error",
                "timeline": "inference failed",
                "trimming_overview": "query error",
            },
        )

        with patch(
            "app.routers.dashboard_aggregator.DashboardAggregatorService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_summary = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    f"/api/projects/{PROJECT_ID}/dashboard/summary"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["cycle_progress"] is None
        assert body["vr_summary"] is None
        assert body["open_reviews"] is None
        assert body["timeline"] is None
        assert body["trimming_overview"] is None
        assert body["errors"] is not None
        assert len(body["errors"]) == 5
        assert "cycle_progress" in body["errors"]
        assert "vr_summary" in body["errors"]
        assert "open_reviews" in body["errors"]
        assert "timeline" in body["errors"]
        assert "trimming_overview" in body["errors"]


# ---------------------------------------------------------------------------
# Tests: Response Structure Completeness
# ---------------------------------------------------------------------------


class TestDashboardResponseStructure:
    """响应结构完整性 — 所有字段存在。"""

    @pytest.mark.asyncio
    async def test_response_contains_all_required_fields(self, db_session):
        """响应体包含所有 DashboardSummaryResponse 定义的字段。"""
        user = _FakeUser(USER_ID, role=UserRole.admin)
        app = _make_app_authenticated(db_session, user)

        mock_result = _build_mock_summary_result()

        with patch(
            "app.routers.dashboard_aggregator.DashboardAggregatorService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_summary = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    f"/api/projects/{PROJECT_ID}/dashboard/summary"
                )

        assert resp.status_code == 200
        body = resp.json()

        # Required top-level fields
        required_fields = [
            "project_name",
            "audit_year",
            "last_updated",
            "cycle_progress",
            "vr_summary",
            "open_reviews",
            "timeline",
            "trimming_overview",
            "errors",
        ]
        for field in required_fields:
            assert field in body, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_cycle_progress_item_structure(self, db_session):
        """cycle_progress 中每个 item 包含完整字段。"""
        user = _FakeUser(USER_ID, role=UserRole.admin)
        app = _make_app_authenticated(db_session, user)

        mock_result = _build_mock_summary_result()

        with patch(
            "app.routers.dashboard_aggregator.DashboardAggregatorService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_summary = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    f"/api/projects/{PROJECT_ID}/dashboard/summary"
                )

        body = resp.json()
        assert body["cycle_progress"] is not None
        item = body["cycle_progress"][0]
        assert "cycle" in item
        assert "cycle_name" in item
        assert "total_procedures" in item
        assert "completed_procedures" in item
        assert "trimmed_procedures" in item
        assert "progress_rate" in item

    @pytest.mark.asyncio
    async def test_vr_summary_structure(self, db_session):
        """vr_summary 包含完整字段结构。"""
        user = _FakeUser(USER_ID, role=UserRole.admin)
        app = _make_app_authenticated(db_session, user)

        mock_result = _build_mock_summary_result()

        with patch(
            "app.routers.dashboard_aggregator.DashboardAggregatorService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_summary = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    f"/api/projects/{PROJECT_ID}/dashboard/summary"
                )

        body = resp.json()
        vr = body["vr_summary"]
        assert vr is not None
        assert "total_rules" in vr
        assert "blocking_failed" in vr
        assert "all_passed" in vr
        assert "by_cycle" in vr

    @pytest.mark.asyncio
    async def test_open_reviews_structure(self, db_session):
        """open_reviews 包含完整字段结构。"""
        user = _FakeUser(USER_ID, role=UserRole.admin)
        app = _make_app_authenticated(db_session, user)

        mock_result = _build_mock_summary_result()

        with patch(
            "app.routers.dashboard_aggregator.DashboardAggregatorService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_summary = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    f"/api/projects/{PROJECT_ID}/dashboard/summary"
                )

        body = resp.json()
        reviews = body["open_reviews"]
        assert reviews is not None
        assert "total" in reviews
        assert "by_layer" in reviews
        assert "items" in reviews

    @pytest.mark.asyncio
    async def test_timeline_structure(self, db_session):
        """timeline 包含完整字段结构。"""
        user = _FakeUser(USER_ID, role=UserRole.admin)
        app = _make_app_authenticated(db_session, user)

        mock_result = _build_mock_summary_result()

        with patch(
            "app.routers.dashboard_aggregator.DashboardAggregatorService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_summary = AsyncMock(return_value=mock_result)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    f"/api/projects/{PROJECT_ID}/dashboard/summary"
                )

        body = resp.json()
        tl = body["timeline"]
        assert tl is not None
        assert "current_stage" in tl
        assert "stages" in tl
        assert len(tl["stages"]) == 4
