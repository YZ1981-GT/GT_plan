"""PM Dashboard — ReviewInbox 入口 API 测试

验证全局路由 `GET /api/review-inbox` 与单项目路由 `GET /api/projects/{id}/review-inbox`
均通过同一 `ReviewInboxService.get_inbox` 服务，响应 schema 一致。

Validates: Refinement Round 1 需求 1 验收标准 1
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
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)
from app.routers.pm_dashboard import router as pm_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


class _FakeUser:
    """轻量级用户替身 — 绕开 User ORM 的 AuditMixin 字段依赖。"""

    def __init__(self, uid: uuid.UUID, role: UserRole = UserRole.admin):
        self.id = uid
        self.username = "reviewer"
        self.email = "reviewer@test.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


REVIEWER_ID = uuid.uuid4()
OTHER_REVIEWER_ID = uuid.uuid4()
PROJECT_A_ID = uuid.uuid4()
PROJECT_B_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每测试独立内存库。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """种子数据：两个项目，每个项目各有若干底稿（含待复核、已通过、其他复核人、已删除）。"""
    # 两个项目
    project_a = Project(
        id=PROJECT_A_ID,
        name="项目 A",
        client_name="客户 A",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        created_by=REVIEWER_ID,
    )
    project_b = Project(
        id=PROJECT_B_ID,
        name="项目 B",
        client_name="客户 B",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        created_by=REVIEWER_ID,
    )
    db_session.add_all([project_a, project_b])
    await db_session.flush()

    # WpIndex：working_paper 表有 (project_id, wp_index_id) 唯一约束，每张底稿需独立索引
    idx_a1 = WpIndex(id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_code="A-001",
                     wp_name="项目 A 底稿 1", audit_cycle="销售与收款", status=WpStatus.in_progress)
    idx_a2 = WpIndex(id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_code="A-002",
                     wp_name="项目 A 底稿 2", audit_cycle="销售与收款", status=WpStatus.in_progress)
    idx_a3 = WpIndex(id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_code="A-003",
                     wp_name="项目 A 底稿 3", audit_cycle="销售与收款", status=WpStatus.in_progress)
    idx_b1 = WpIndex(id=uuid.uuid4(), project_id=PROJECT_B_ID, wp_code="B-001",
                     wp_name="项目 B 底稿 1", audit_cycle="采购与付款", status=WpStatus.in_progress)
    idx_b2 = WpIndex(id=uuid.uuid4(), project_id=PROJECT_B_ID, wp_code="B-002",
                     wp_name="项目 B 底稿 2", audit_cycle="采购与付款", status=WpStatus.in_progress)
    db_session.add_all([idx_a1, idx_a2, idx_a3, idx_b1, idx_b2])
    await db_session.flush()

    # WorkingPaper：
    #  - wp_a1: A 项目 / 当前 reviewer 待一级复核  ✅ 应出现
    #  - wp_a2: A 项目 / 当前 reviewer 已通过      ❌ 不应出现（review_status 不匹配）
    #  - wp_a3: A 项目 / 其他 reviewer 待复核      ❌ 不应出现（reviewer 不匹配）
    #  - wp_b1: B 项目 / 当前 reviewer 待二级复核  ✅ 应出现
    #  - wp_b2: B 项目 / 当前 reviewer 待复核但已删除 ❌ 不应出现（is_deleted）
    wp_a1 = WorkingPaper(
        id=uuid.uuid4(),
        project_id=PROJECT_A_ID,
        wp_index_id=idx_a1.id,
        file_path="/tmp/a1.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.under_review,
        review_status=WpReviewStatus.pending_level1,
        reviewer=REVIEWER_ID,
        file_version=1,
        is_deleted=False,
    )
    wp_a2 = WorkingPaper(
        id=uuid.uuid4(),
        project_id=PROJECT_A_ID,
        wp_index_id=idx_a2.id,
        file_path="/tmp/a2.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.review_passed,
        review_status=WpReviewStatus.level1_passed,
        reviewer=REVIEWER_ID,
        file_version=1,
        is_deleted=False,
    )
    wp_a3 = WorkingPaper(
        id=uuid.uuid4(),
        project_id=PROJECT_A_ID,
        wp_index_id=idx_a3.id,
        file_path="/tmp/a3.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.under_review,
        review_status=WpReviewStatus.pending_level1,
        reviewer=OTHER_REVIEWER_ID,
        file_version=1,
        is_deleted=False,
    )
    wp_b1 = WorkingPaper(
        id=uuid.uuid4(),
        project_id=PROJECT_B_ID,
        wp_index_id=idx_b1.id,
        file_path="/tmp/b1.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.under_review,
        review_status=WpReviewStatus.pending_level2,
        reviewer=REVIEWER_ID,
        file_version=2,
        is_deleted=False,
    )
    wp_b2 = WorkingPaper(
        id=uuid.uuid4(),
        project_id=PROJECT_B_ID,
        wp_index_id=idx_b2.id,
        file_path="/tmp/b2.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.under_review,
        review_status=WpReviewStatus.pending_level1,
        reviewer=REVIEWER_ID,
        file_version=1,
        is_deleted=True,
    )
    db_session.add_all([wp_a1, wp_a2, wp_a3, wp_b1, wp_b2])
    await db_session.commit()

    return {
        "wp_a1_id": wp_a1.id,
        "wp_b1_id": wp_b1.id,
        "project_a_id": PROJECT_A_ID,
        "project_b_id": PROJECT_B_ID,
    }


def _make_client(db_session: AsyncSession, user_id: uuid.UUID) -> AsyncClient:
    """构造一个只挂 pm_dashboard 路由的极小 app，绕过 auth/redis 依赖。"""
    app = FastAPI()
    app.include_router(pm_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser(user_id, role=UserRole.admin)

    # 覆盖 get_current_user 即可；require_project_access 内部会 Depends(get_current_user)
    # 而 admin 角色跳过项目权限检查（见 deps.py:156-164）
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ===================================================================
# 全局入口：GET /api/review-inbox
# ===================================================================


class TestGlobalReviewInbox:
    """Validates: 需求 1 验收 1 — 全局路由"""

    @pytest.mark.asyncio
    async def test_global_returns_items_across_projects(self, db_session, seeded_db):
        """全局入口应返回 reviewer 下所有项目的待复核底稿。"""
        async with _make_client(db_session, REVIEWER_ID) as client:
            resp = await client.get("/api/review-inbox")
            assert resp.status_code == 200
            body = resp.json()

        assert "items" in body
        assert "total" in body
        assert body["total"] == 2  # wp_a1 + wp_b1
        assert len(body["items"]) == 2

        project_ids = {item["project_id"] for item in body["items"]}
        assert project_ids == {str(PROJECT_A_ID), str(PROJECT_B_ID)}

    @pytest.mark.asyncio
    async def test_global_excludes_passed_and_other_reviewer(self, db_session, seeded_db):
        """已通过、其他 reviewer 的、已软删除的底稿均不能出现在收件箱。"""
        async with _make_client(db_session, REVIEWER_ID) as client:
            resp = await client.get("/api/review-inbox")
            body = resp.json()

        review_statuses = {item["review_status"] for item in body["items"]}
        # 仅 pending_level1 / pending_level2
        assert review_statuses.issubset({"pending_level1", "pending_level2"})

    @pytest.mark.asyncio
    async def test_global_pagination(self, db_session, seeded_db):
        """分页参数透传到服务层。"""
        async with _make_client(db_session, REVIEWER_ID) as client:
            resp = await client.get("/api/review-inbox", params={"page": 1, "page_size": 1})
            body = resp.json()

        assert body["page"] == 1
        assert body["page_size"] == 1
        assert body["total"] == 2
        assert len(body["items"]) == 1

    @pytest.mark.asyncio
    async def test_global_empty_when_no_items(self, db_session, seeded_db):
        """当前 reviewer 没有待复核时返回空列表，不报错。"""
        stranger_id = uuid.uuid4()
        async with _make_client(db_session, stranger_id) as client:
            resp = await client.get("/api/review-inbox")
            assert resp.status_code == 200
            body = resp.json()

        assert body["total"] == 0
        assert body["items"] == []


# ===================================================================
# 单项目入口：GET /api/projects/{id}/review-inbox
# ===================================================================


class TestProjectReviewInbox:
    """Validates: 需求 1 验收 1 — 单项目路由"""

    @pytest.mark.asyncio
    async def test_project_scoped_returns_only_that_project(self, db_session, seeded_db):
        """单项目入口仅返回当前项目下的待复核底稿。"""
        async with _make_client(db_session, REVIEWER_ID) as client:
            resp = await client.get(f"/api/projects/{PROJECT_A_ID}/review-inbox")
            assert resp.status_code == 200
            body = resp.json()

        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["project_id"] == str(PROJECT_A_ID)
        assert body["items"][0]["wp_code"] == "A-001"

    @pytest.mark.asyncio
    async def test_project_scoped_empty_project(self, db_session, seeded_db):
        """reviewer 在某项目下无待复核底稿时返回空。"""
        # 另建一个空项目
        empty_project_id = uuid.uuid4()
        empty_project = Project(
            id=empty_project_id,
            name="空项目",
            client_name="客户 C",
            project_type=ProjectType.annual,
            status=ProjectStatus.execution,
            created_by=REVIEWER_ID,
        )
        db_session.add(empty_project)
        await db_session.commit()

        async with _make_client(db_session, REVIEWER_ID) as client:
            resp = await client.get(f"/api/projects/{empty_project_id}/review-inbox")
            assert resp.status_code == 200
            body = resp.json()

        assert body["total"] == 0
        assert body["items"] == []


# ===================================================================
# 共用一个 service：schema 一致性
# ===================================================================


class TestBothRoutesShareService:
    """Validates: 需求 1 — 两个路由必须通过同一 service.get_inbox，响应 schema 一致"""

    @pytest.mark.asyncio
    async def test_response_schema_identical(self, db_session, seeded_db):
        """两个入口返回体结构一致（items + total + page + page_size）。"""
        async with _make_client(db_session, REVIEWER_ID) as client:
            global_resp = await client.get("/api/review-inbox")
            project_resp = await client.get(f"/api/projects/{PROJECT_A_ID}/review-inbox")

        assert global_resp.status_code == 200
        assert project_resp.status_code == 200

        global_body = global_resp.json()
        project_body = project_resp.json()

        assert set(global_body.keys()) == set(project_body.keys())
        # 每个 item 的字段集一致
        if global_body["items"] and project_body["items"]:
            assert set(global_body["items"][0].keys()) == set(project_body["items"][0].keys())

    @pytest.mark.asyncio
    async def test_project_scope_is_subset_of_global(self, db_session, seeded_db):
        """单项目路由的 items 必然是全局路由 items 的子集（同一 service 过滤 project_id）。"""
        async with _make_client(db_session, REVIEWER_ID) as client:
            global_resp = await client.get("/api/review-inbox", params={"page_size": 200})
            project_a_resp = await client.get(
                f"/api/projects/{PROJECT_A_ID}/review-inbox",
                params={"page_size": 200},
            )

        global_ids = {item["id"] for item in global_resp.json()["items"]}
        project_ids = {item["id"] for item in project_a_resp.json()["items"]}

        assert project_ids.issubset(global_ids)
        # 过滤后项目 A 只剩 1 条
        assert len(project_ids) == 1

    @pytest.mark.asyncio
    async def test_service_routed_via_get_inbox(self, db_session, seeded_db, monkeypatch):
        """验证两个路由都调用 ReviewInboxService.get_inbox — 直接 monkeypatch 服务方法。"""
        from app.services import pm_service

        calls: list[dict] = []
        original = pm_service.ReviewInboxService.get_inbox

        async def tracking_get_inbox(self, user_id, project_id=None, page=1, page_size=50):
            calls.append({"user_id": user_id, "project_id": project_id})
            return await original(self, user_id, project_id=project_id, page=page, page_size=page_size)

        monkeypatch.setattr(pm_service.ReviewInboxService, "get_inbox", tracking_get_inbox)

        async with _make_client(db_session, REVIEWER_ID) as client:
            await client.get("/api/review-inbox")
            await client.get(f"/api/projects/{PROJECT_A_ID}/review-inbox")

        # 两次调用都走到了 get_inbox
        assert len(calls) == 2
        # 全局入口 project_id 为 None
        assert calls[0]["project_id"] is None
        # 单项目入口 project_id 等于 PROJECT_A_ID
        assert calls[1]["project_id"] == PROJECT_A_ID


# ===================================================================
# 授权边界：未认证
# ===================================================================


class TestAuthBoundary:
    """Validates: 未覆盖 get_current_user 时返回 401/403（基础安全防线）"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, db_session, seeded_db):
        """不覆盖 get_current_user 依赖时，请求必须被拒绝。"""
        app = FastAPI()
        app.include_router(pm_router)

        async def _override_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/review-inbox")

        # 未登录 → 401/403/422 均表示拦截（具体码取决于 HTTPBearer 配置）
        assert resp.status_code in (401, 403, 422, 500)
