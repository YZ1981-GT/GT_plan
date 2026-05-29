"""归档项目只读守卫测试

验证：归档项目的 mutation 端点返回 HTTP 423 (Locked)，
error_code = "PROJECT_ARCHIVED"。

Validates: Requirements 1.1 (归档项目只读保护)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

from app.core.database import get_db
from app.deps import get_current_user, _check_project_not_archived
from app.models.base import Base, ProjectStatus, UserRole
from app.models.core import Project, ProjectType

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "test_admin"
        self.email = "admin@test.com"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


TEST_USER = _FakeUser()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        # 仅创建测试所需的表（避免其他模型的 PG 特有语法在 SQLite 报错）
        tables_to_create = [
            Base.metadata.tables["projects"],
            Base.metadata.tables["users"],
            Base.metadata.tables["project_users"],
        ]
        await conn.run_sync(
            Base.metadata.create_all, tables=tables_to_create
        )
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def archived_project(db_session: AsyncSession) -> uuid.UUID:
    """创建一个归档状态的项目"""
    project = Project(
        id=uuid.uuid4(),
        name="归档测试项目_2025",
        client_name="归档测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.archived,
        created_by=TEST_USER.id,
    )
    db_session.add(project)
    await db_session.commit()
    return project.id


@pytest_asyncio.fixture
async def active_project(db_session: AsyncSession) -> uuid.UUID:
    """创建一个活跃状态的项目"""
    project = Project(
        id=uuid.uuid4(),
        name="活跃测试项目_2025",
        client_name="活跃测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=TEST_USER.id,
    )
    db_session.add(project)
    await db_session.commit()
    return project.id


def _make_app(db_session: AsyncSession) -> FastAPI:
    """构建包含 adjustments 路由的测试 app"""
    from app.routers.adjustments import router as adj_router

    app = FastAPI()
    app.include_router(adj_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return TEST_USER

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    return app


# ---------------------------------------------------------------------------
# 单元测试：_check_project_not_archived 函数
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guard_skips_readonly(db_session: AsyncSession, archived_project: uuid.UUID):
    """readonly 权限不触发归档守卫"""
    # 不应抛异常
    await _check_project_not_archived(db_session, archived_project, TEST_USER, "readonly")


@pytest.mark.asyncio
async def test_guard_blocks_edit_on_archived(db_session: AsyncSession, archived_project: uuid.UUID):
    """edit 权限 + 归档项目 → 抛 423"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await _check_project_not_archived(db_session, archived_project, TEST_USER, "edit")

    assert exc_info.value.status_code == 423
    assert exc_info.value.detail["error_code"] == "PROJECT_ARCHIVED"
    assert "message" in exc_info.value.detail
    assert "message_en" in exc_info.value.detail


@pytest.mark.asyncio
async def test_guard_blocks_review_on_archived(db_session: AsyncSession, archived_project: uuid.UUID):
    """review 权限 + 归档项目 → 抛 423"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await _check_project_not_archived(db_session, archived_project, TEST_USER, "review")

    assert exc_info.value.status_code == 423
    assert exc_info.value.detail["error_code"] == "PROJECT_ARCHIVED"


@pytest.mark.asyncio
async def test_guard_allows_edit_on_active(db_session: AsyncSession, active_project: uuid.UUID):
    """edit 权限 + 活跃项目 → 不抛异常"""
    await _check_project_not_archived(db_session, active_project, TEST_USER, "edit")


# ---------------------------------------------------------------------------
# 端点集成测试：5 个 mutation 端点对归档项目返回 423
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adjustments_post_returns_423_for_archived(
    db_session: AsyncSession, archived_project: uuid.UUID
):
    """POST /api/projects/{pid}/adjustments → 423 (归档项目)"""
    app = _make_app(db_session)

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{archived_project}/adjustments",
                json={
                    "adjustment_type": "aje",
                    "year": 2025,
                    "line_items": [
                        {"standard_account_code": "1001", "debit_amount": "100"},
                        {"standard_account_code": "6001", "credit_amount": "100"},
                    ],
                },
            )
    assert resp.status_code == 423
    body = resp.json()
    assert body["detail"]["error_code"] == "PROJECT_ARCHIVED"
    assert body["detail"]["message"] == "项目已归档，无法编辑"
    assert body["detail"]["message_en"] == "Project archived (read-only)"


@pytest.mark.asyncio
async def test_adjustments_put_returns_423_for_archived(
    db_session: AsyncSession, archived_project: uuid.UUID
):
    """PUT /api/projects/{pid}/adjustments/{gid} → 423 (归档项目)"""
    app = _make_app(db_session)
    fake_group_id = uuid.uuid4()

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                f"/api/projects/{archived_project}/adjustments/{fake_group_id}",
                json={"description": "尝试修改"},
            )
    assert resp.status_code == 423
    body = resp.json()
    assert body["detail"]["error_code"] == "PROJECT_ARCHIVED"


@pytest.mark.asyncio
async def test_adjustments_delete_returns_423_for_archived(
    db_session: AsyncSession, archived_project: uuid.UUID
):
    """DELETE /api/projects/{pid}/adjustments/{gid} → 423 (归档项目)"""
    app = _make_app(db_session)
    fake_group_id = uuid.uuid4()

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.delete(
                f"/api/projects/{archived_project}/adjustments/{fake_group_id}",
            )
    assert resp.status_code == 423
    body = resp.json()
    assert body["detail"]["error_code"] == "PROJECT_ARCHIVED"


@pytest.mark.asyncio
async def test_adjustments_review_returns_423_for_archived(
    db_session: AsyncSession, archived_project: uuid.UUID
):
    """POST /api/projects/{pid}/adjustments/{gid}/review → 423 (归档项目)"""
    app = _make_app(db_session)
    fake_group_id = uuid.uuid4()

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{archived_project}/adjustments/{fake_group_id}/review",
                json={"status": "pending_review"},
            )
    assert resp.status_code == 423
    body = resp.json()
    assert body["detail"]["error_code"] == "PROJECT_ARCHIVED"


@pytest.mark.asyncio
async def test_adjustments_batch_delete_returns_423_for_archived(
    db_session: AsyncSession, archived_project: uuid.UUID
):
    """POST /api/projects/{pid}/adjustments/batch-delete → 423 (归档项目)"""
    app = _make_app(db_session)

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{archived_project}/adjustments/batch-delete",
                json={"entry_group_ids": [str(uuid.uuid4())]},
            )
    assert resp.status_code == 423
    body = resp.json()
    assert body["detail"]["error_code"] == "PROJECT_ARCHIVED"


# ---------------------------------------------------------------------------
# 对照测试：活跃项目不触发 423
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adjustments_post_allowed_for_active_project(
    db_session: AsyncSession, active_project: uuid.UUID
):
    """POST /api/projects/{pid}/adjustments → 非 423 (活跃项目)

    活跃项目请求通过归档守卫后进入业务逻辑，可能因缺少测试数据而返回
    400/500 或抛出异常，但绝不应返回 423。
    """
    app = _make_app(db_session)

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            try:
                resp = await client.post(
                    f"/api/projects/{active_project}/adjustments",
                    json={
                        "adjustment_type": "aje",
                        "year": 2025,
                        "line_items": [
                            {"standard_account_code": "1001", "debit_amount": "100"},
                            {"standard_account_code": "6001", "credit_amount": "100"},
                        ],
                    },
                )
                # 如果请求成功返回响应，验证不是 423
                assert resp.status_code != 423, (
                    f"活跃项目不应被归档守卫拦截，实际返回 {resp.status_code}"
                )
            except Exception as exc:
                # 如果因缺少测试表而抛出异常（如 OperationalError），
                # 说明请求已通过归档守卫进入业务逻辑，测试目的达成
                assert "account_chart" in str(exc) or "OperationalError" in str(type(exc).__name__), (
                    f"意外异常: {exc}"
                )
