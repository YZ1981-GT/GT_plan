"""跨模块冲突 router 测试 — V3 收官增强 Req 7.4

覆盖 3 个端点：
- GET  /api/projects/{pid}/conflicts/pending      列出 pending + count
- GET  /api/projects/{pid}/conflicts              列出（status/target_module 过滤）
- POST /api/conflicts/{conflict_id}/resolve       调解（keep_manual / accept_new / merge）

测试用例：
1. test_list_pending_returns_count_and_items — 3 条 pending → count=3 + 3 items
2. test_resolve_keep_manual_sets_final_to_manual — 成功调解 keep_manual
3. test_resolve_accept_new_sets_final_to_upstream — 成功调解 accept_new
4. test_resolve_merge_with_value — 成功调解 merge，final_value=merge_value
5. test_resolve_merge_without_value_returns_400 — merge 缺 merge_value → 400
6. test_resolve_invalid_resolution_returns_400 — resolution 非法值 → 400
7. test_resolve_nonexistent_returns_404 — conflict_id 不存在 → 404
8. test_resolve_already_resolved_returns_422 — 重复调解 → 422
9. test_list_conflicts_filters_by_status — status='resolved' 过滤
10. test_list_conflicts_invalid_status_returns_400

Validates: Requirements 7.4
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容 JSONB + ARRAY（先于模型导入）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

# 仅注册测试所需的模型
import app.models.core  # noqa: F401, E402
import app.models.audit_log_models  # noqa: F401, E402
import app.models.v3_refinement_models  # noqa: F401, E402

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base, ProjectStatus, UserRole  # noqa: E402
from app.routers.cross_module_conflicts import router  # noqa: E402
from app.services import conflict_resolution_service as svc  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Fake user
# ---------------------------------------------------------------------------


class _FakeUser:
    def __init__(self, role: UserRole = UserRole.admin):
        self.id = uuid.uuid4()
        self.username = f"test_{role.value}"
        self.email = f"{role.value}@test.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


ADMIN_USER = _FakeUser(UserRole.admin)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["projects"],
            Base.metadata.tables["audit_log_entries"],
            Base.metadata.tables["cross_module_conflicts"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables_to_create)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def project_id(db_session: AsyncSession) -> uuid.UUID:
    """预先写入 admin user + 项目，返回 project_id。"""
    from app.models.core import Project, User

    user = User(
        id=ADMIN_USER.id,
        username=ADMIN_USER.username,
        email=ADMIN_USER.email,
        hashed_password="hashed",
        role=ADMIN_USER.role,
        is_active=True,
    )
    pid = uuid.uuid4()
    project = Project(
        id=pid,
        name="测试项目",
        client_name="测试客户",
        status=ProjectStatus.execution,
    )
    db_session.add(user)
    db_session.add(project)
    await db_session.commit()
    return pid


def _make_client(db_session: AsyncSession, user: _FakeUser):
    """构造测试客户端。"""
    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _create_pending(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    n: int = 1,
    target_module: str = "disclosure",
) -> list:
    """快速创建 n 条 pending 冲突记录。"""
    conflicts = []
    for i in range(n):
        c = await svc.enqueue(
            db=db,
            project_id=project_id,
            source_module="workpaper",
            source_id=uuid.uuid4(),
            target_module=target_module,
            target_id=uuid.uuid4(),
            target_field=f"field_{i}",
            upstream_value=f"upstream-{i}",
            manual_value=f"manual-{i}",
            user_id=ADMIN_USER.id,
            propagation_origin="user_edit",
        )
        conflicts.append(c)
    await db.commit()
    return conflicts


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pending_returns_count_and_items(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """3 条 pending → count=3 + 3 items。"""
    await _create_pending(db_session, project_id, n=3)

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.get(f"/api/projects/{project_id}/conflicts/pending")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["count"] == 3
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 3
    for item in data["items"]:
        assert "id" in item
        assert item["status"] == "pending"
        assert item["resolution"] is None
        assert item["final_value"] is None
        assert item["source_module"] == "workpaper"
        assert item["target_module"] == "disclosure"


@pytest.mark.asyncio
async def test_list_pending_zero_when_empty(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """无 pending → count=0 + items=[]。"""
    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.get(f"/api/projects/{project_id}/conflicts/pending")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_resolve_keep_manual_sets_final_to_manual(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """resolve keep_manual → status='resolved' + final_value=manual_value。"""
    conflicts = await _create_pending(db_session, project_id, n=1)
    cid = conflicts[0].id
    expected_manual = conflicts[0].manual_value

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/conflicts/{cid}/resolve",
            json={"resolution": "keep_manual"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(cid)
    assert data["status"] == "resolved"
    assert data["resolution"] == "keep_manual"
    assert data["final_value"] == expected_manual


@pytest.mark.asyncio
async def test_resolve_accept_new_sets_final_to_upstream(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """resolve accept_new → final_value=upstream_value。"""
    conflicts = await _create_pending(db_session, project_id, n=1)
    cid = conflicts[0].id
    expected_upstream = conflicts[0].upstream_value

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/conflicts/{cid}/resolve",
            json={"resolution": "accept_new"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["resolution"] == "accept_new"
    assert data["final_value"] == expected_upstream


@pytest.mark.asyncio
async def test_resolve_merge_with_value(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """resolve merge + merge_value → final_value=merge_value。"""
    conflicts = await _create_pending(db_session, project_id, n=1)
    cid = conflicts[0].id
    custom = "用户手编合并值"

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/conflicts/{cid}/resolve",
            json={"resolution": "merge", "merge_value": custom},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["resolution"] == "merge"
    assert data["final_value"] == custom


@pytest.mark.asyncio
async def test_resolve_merge_without_value_returns_400(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """merge 缺 merge_value → 400。"""
    conflicts = await _create_pending(db_session, project_id, n=1)
    cid = conflicts[0].id

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/conflicts/{cid}/resolve",
            json={"resolution": "merge"},
        )

    assert resp.status_code == 400
    assert "merge_value" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_resolve_invalid_resolution_returns_400(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """resolution 非法值 → 400。"""
    conflicts = await _create_pending(db_session, project_id, n=1)
    cid = conflicts[0].id

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/conflicts/{cid}/resolve",
            json={"resolution": "invalid_choice"},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resolve_nonexistent_returns_404(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """conflict_id 不存在 → 404。"""
    fake_id = uuid.uuid4()
    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/conflicts/{fake_id}/resolve",
            json={"resolution": "keep_manual"},
        )

    assert resp.status_code == 404
    assert "冲突记录不存在" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_resolve_already_resolved_returns_422(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """重复 resolve → 422。"""
    conflicts = await _create_pending(db_session, project_id, n=1)
    cid = conflicts[0].id

    async with _make_client(db_session, ADMIN_USER) as client:
        # 第一次成功
        resp1 = await client.post(
            f"/api/conflicts/{cid}/resolve",
            json={"resolution": "accept_new"},
        )
        assert resp1.status_code == 200

        # 第二次应失败 422
        resp2 = await client.post(
            f"/api/conflicts/{cid}/resolve",
            json={"resolution": "accept_new"},
        )
        assert resp2.status_code == 422
        assert "已调解" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_list_conflicts_filters_by_status(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """list /conflicts 支持 status 过滤。"""
    conflicts = await _create_pending(db_session, project_id, n=3)
    # 调解一条
    await svc.resolve(
        db=db_session,
        conflict_id=conflicts[0].id,
        user_id=ADMIN_USER.id,
        resolution="accept_new",
    )
    await db_session.commit()

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.get(
            f"/api/projects/{project_id}/conflicts",
            params={"status": "resolved"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "resolved"
        assert data["items"][0]["resolution"] == "accept_new"

        resp2 = await client.get(
            f"/api/projects/{project_id}/conflicts",
            params={"status": "pending"},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) == 2


@pytest.mark.asyncio
async def test_list_conflicts_invalid_status_returns_400(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """list /conflicts 非法 status → 400。"""
    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.get(
            f"/api/projects/{project_id}/conflicts",
            params={"status": "garbage"},
        )

    assert resp.status_code == 400
