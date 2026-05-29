"""Property 1: 归档不变量 — hypothesis 属性测试

∀ project P, ∀ mutation endpoint E, ∀ user U:
  P.status == archived ∧ E ∈ MUTATION_ENDPOINTS ⇒ E(P, U) returns 423

验证：所有 mutation 端点对归档项目必须返回 423 Locked，
无论用户角色如何（admin/partner/manager/auditor/qc）。

**Validates: Requirements 1.1**

文件：backend/tests/test_property_archived_invariant.py
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings, strategies as st
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, UserRole
from app.models.core import Project, ProjectType

# SQLite JSONB 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Mutation endpoints: (method, path_template, sample_body)
# path_template 中 {pid} 会被替换为实际项目 ID
# ---------------------------------------------------------------------------

MUTATION_ENDPOINTS = [
    # Adjustments - POST create (require_project_access("edit"))
    ("POST", "/api/projects/{pid}/adjustments", {
        "adjustment_type": "aje",
        "year": 2025,
        "line_items": [
            {"standard_account_code": "1001", "debit_amount": "100"},
            {"standard_account_code": "6001", "credit_amount": "100"},
        ],
    }),
    # Adjustments - PUT update (require_project_access("edit"))
    ("PUT", "/api/projects/{pid}/adjustments/{gid}", {
        "description": "尝试修改",
    }),
    # Adjustments - DELETE (require_project_access("edit"))
    ("DELETE", "/api/projects/{pid}/adjustments/{gid}", None),
    # Adjustments - batch-delete (require_project_access("edit"))
    ("POST", "/api/projects/{pid}/adjustments/batch-delete", {
        "entry_group_ids": ["00000000-0000-0000-0000-000000000001"],
    }),
    # Adjustments - review (require_project_access("review"))
    ("POST", "/api/projects/{pid}/adjustments/{gid}/review", {
        "status": "pending_review",
    }),
    # Working paper - univer-save (require_project_access("edit"))
    ("POST", "/api/projects/{pid}/working-papers/{wp_id}/univer-save", {
        "sheets": {},
    }),
    # Working paper - status update (require_project_access("edit"))
    ("PUT", "/api/projects/{pid}/working-papers/{wp_id}/status", {
        "status": "in_progress",
    }),
    # Working paper - assign (require_project_access("review"))
    ("PUT", "/api/projects/{pid}/working-papers/{wp_id}/assign", {
        "preparer_id": "00000000-0000-0000-0000-000000000001",
    }),
    # Working paper - submit review (require_project_access("edit"))
    ("POST", "/api/projects/{pid}/working-papers/{wp_id}/submit-review", None),
    # Working paper - batch submit (require_project_access("edit"))
    ("POST", "/api/projects/{pid}/working-papers/batch-submit", {
        "wp_ids": ["00000000-0000-0000-0000-000000000001"],
    }),
]

# User roles to test
USER_ROLES = [UserRole.admin, UserRole.partner, UserRole.manager, UserRole.auditor, UserRole.qc]


class _FakeUser:
    """模拟用户对象"""

    def __init__(self, role: UserRole):
        self.id = uuid.uuid4()
        self.username = f"test_{role.value}"
        self.email = f"{role.value}@test.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


def _build_app(db_session: AsyncSession, user: _FakeUser) -> FastAPI:
    """构建包含多个 mutation 路由的测试 app"""
    from app.routers.adjustments import router as adj_router
    from app.routers.working_paper import router as wp_router

    app = FastAPI()
    app.include_router(adj_router)
    app.include_router(wp_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    return app


def _resolve_path(path_template: str, project_id: uuid.UUID) -> str:
    """将路径模板中的占位符替换为实际值"""
    gid = str(uuid.uuid4())
    wp_id = str(uuid.uuid4())
    return (
        path_template
        .replace("{pid}", str(project_id))
        .replace("{gid}", gid)
        .replace("{wp_id}", wp_id)
    )


# ---------------------------------------------------------------------------
# Fixture: 创建归档项目的 DB session
# ---------------------------------------------------------------------------

async def _create_archived_project_session():
    """创建内存 DB + 归档项目，返回 (session, project_id)"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables_to_create = [
            Base.metadata.tables["projects"],
            Base.metadata.tables["users"],
            Base.metadata.tables["project_users"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables_to_create)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    session = session_factory()

    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        name="PBT归档测试项目",
        client_name="PBT测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.archived,
        created_by=uuid.uuid4(),
    )
    session.add(project)
    await session.commit()

    return session, project_id


# ---------------------------------------------------------------------------
# Property 1: 归档不变量
# ---------------------------------------------------------------------------

class TestArchivedProjectMutationInvariant:
    """Property 1: 归档项目所有 mutation 端点必返回 423

    **Validates: Requirements 1.1**

    ∀ project P (status=archived), ∀ mutation endpoint E, ∀ user role R:
      E(P, user_with_role_R) → HTTP 423 Locked
    """

    @settings(max_examples=15, deadline=None)
    @given(
        endpoint_idx=st.integers(min_value=0, max_value=len(MUTATION_ENDPOINTS) - 1),
        role_idx=st.integers(min_value=0, max_value=len(USER_ROLES) - 1),
    )
    @pytest.mark.asyncio
    async def test_archived_project_mutation_returns_423(
        self, endpoint_idx: int, role_idx: int
    ):
        """归档项目 + 任意 mutation 端点 + 任意角色 → 423

        **Validates: Requirements 1.1**
        """
        method, path_template, body = MUTATION_ENDPOINTS[endpoint_idx]
        role = USER_ROLES[role_idx]
        user = _FakeUser(role)

        session, project_id = await _create_archived_project_session()
        try:
            app = _build_app(session, user)
            path = _resolve_path(path_template, project_id)

            with patch("app.deps.set_rls_context", new=AsyncMock()):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    if method == "POST":
                        resp = await client.post(path, json=body)
                    elif method == "PUT":
                        resp = await client.put(path, json=body or {})
                    elif method == "DELETE":
                        resp = await client.delete(path)
                    else:
                        raise ValueError(f"Unsupported method: {method}")

            assert resp.status_code == 423, (
                f"Expected 423 for archived project, got {resp.status_code}. "
                f"Endpoint: {method} {path_template}, Role: {role.value}, "
                f"Response: {resp.text[:200]}"
            )

            # 验证响应体包含正确的 error_code
            resp_body = resp.json()
            assert resp_body["detail"]["error_code"] == "PROJECT_ARCHIVED", (
                f"Expected error_code=PROJECT_ARCHIVED, got: {resp_body}"
            )
        finally:
            await session.close()
