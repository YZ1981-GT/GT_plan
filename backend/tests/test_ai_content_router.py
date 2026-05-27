"""AI 内容溯源 router 测试 — V3 收官增强 Req 6.5

覆盖 4 个端点：
- GET  /api/projects/{pid}/ai-content/pending      列出待确认 + count
- POST /api/ai-content/{log_id}/confirm            确认
- POST /api/ai-content/{log_id}/revise             修订
- POST /api/ai-content/{log_id}/reject             拒绝

测试用例（最小集合）：
1. test_list_pending_returns_count_and_items — 4 条 pending → count=4 + 4 items
2. test_confirm_endpoint_changes_status — POST /confirm 后 confirm_action='confirmed'
3. test_revise_endpoint_writes_content — POST /revise 含 revised_content
4. test_reject_endpoint — POST /reject 标记为 rejected
5. test_confirm_already_processed_returns_422 — 重复 confirm 返回 422
6. test_revise_with_empty_content_returns_422 — 修订内容为空 → 422
7. test_pending_excludes_confirmed_items — 已确认条目不在 pending 列表

由于 require_project_access("readonly") 工厂每次返新闭包导致 dep_overrides 不命中，
测试时仅 override get_current_user + get_db，readonly 守卫的 RLS 检查
在 SQLite + admin 角色路径下被 set_rls_context mock 旁路。

Validates: Requirements 6.5
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
from app.routers.ai_content import router  # noqa: E402
from app.services import ai_content_log_service as svc  # noqa: E402


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
            Base.metadata.tables["ai_content_log"],
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
    """构造测试客户端，注入指定用户 + db。

    require_project_access('readonly') 工厂每次返新闭包，dep_overrides 不命中，
    需 mock set_rls_context 以避免 SQLite 不支持 PostgreSQL set_config 调用。
    """
    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _create_pending(db: AsyncSession, project_id: uuid.UUID, n: int = 1) -> list:
    """快速创建 n 条 pending 状态的 AI 内容记录。"""
    logs = []
    for i in range(n):
        log = await svc.create(
            db=db,
            project_id=project_id,
            user_id=ADMIN_USER.id,
            instance_type="workpaper",
            instance_id=uuid.uuid4(),
            target_cell=f"narrative_{i}",
            model="qwen3.5-27b",
            prompt_hash=None,
            content_hash="c" * 64,
            generated_content=f"AI 生成内容 #{i}",
            confidence=0.85,
        )
        logs.append(log)
    await db.commit()
    return logs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pending_returns_count_and_items(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """4 条 pending → count=4 + 4 items。"""
    await _create_pending(db_session, project_id, n=4)

    with patch("app.deps.set_rls_context", new=AsyncMock(return_value=None)):
        async with _make_client(db_session, ADMIN_USER) as client:
            resp = await client.get(
                f"/api/projects/{project_id}/ai-content/pending"
            )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["count"] == 4
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 4
    for item in data["items"]:
        assert "id" in item
        assert "ai_content_log_id" in item
        assert item["confirm_action"] == "pending"
        assert item["instance_type"] == "workpaper"
        assert item["model"] == "qwen3.5-27b"
        assert item["confidence"] == 0.85
        assert item["content"].startswith("AI 生成内容")


@pytest.mark.asyncio
async def test_pending_excludes_confirmed_items(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """已确认条目不应出现在 pending 列表中。"""
    logs = await _create_pending(db_session, project_id, n=3)
    # 确认其中一条
    await svc.confirm(db=db_session, log_id=logs[0].id, user_id=ADMIN_USER.id)
    await db_session.commit()

    with patch("app.deps.set_rls_context", new=AsyncMock(return_value=None)):
        async with _make_client(db_session, ADMIN_USER) as client:
            resp = await client.get(
                f"/api/projects/{project_id}/ai-content/pending"
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert len(data["items"]) == 2
    confirmed_id = str(logs[0].id)
    returned_ids = {it["id"] for it in data["items"]}
    assert confirmed_id not in returned_ids


@pytest.mark.asyncio
async def test_confirm_endpoint_changes_status(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """POST /confirm 后 confirm_action='confirmed'。"""
    logs = await _create_pending(db_session, project_id, n=1)
    log_id = logs[0].id

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(f"/api/ai-content/{log_id}/confirm")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(log_id)
    assert data["confirm_action"] == "confirmed"


@pytest.mark.asyncio
async def test_revise_endpoint_writes_content(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """POST /revise 含 revised_content → confirm_action='revised'。"""
    logs = await _create_pending(db_session, project_id, n=1)
    log_id = logs[0].id

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/ai-content/{log_id}/revise",
            json={"revised_content": "审计师人工修订后的内容"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(log_id)
    assert data["confirm_action"] == "revised"


@pytest.mark.asyncio
async def test_reject_endpoint(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """POST /reject 后 confirm_action='rejected'。"""
    logs = await _create_pending(db_session, project_id, n=1)
    log_id = logs[0].id

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(f"/api/ai-content/{log_id}/reject")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(log_id)
    assert data["confirm_action"] == "rejected"


@pytest.mark.asyncio
async def test_confirm_already_processed_returns_422(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """重复 confirm 返回 422。"""
    logs = await _create_pending(db_session, project_id, n=1)
    log_id = logs[0].id

    async with _make_client(db_session, ADMIN_USER) as client:
        # 第一次确认成功
        resp1 = await client.post(f"/api/ai-content/{log_id}/confirm")
        assert resp1.status_code == 200

        # 第二次确认应失败
        resp2 = await client.post(f"/api/ai-content/{log_id}/confirm")
        assert resp2.status_code == 422
        assert "已处理过" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_revise_with_empty_content_returns_422(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """修订内容为空字符串 → 422。"""
    logs = await _create_pending(db_session, project_id, n=1)
    log_id = logs[0].id

    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(
            f"/api/ai-content/{log_id}/revise",
            json={"revised_content": "   "},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_confirm_nonexistent_returns_404(
    db_session: AsyncSession, project_id: uuid.UUID
):
    """不存在的 log_id 返回 404。"""
    fake_id = uuid.uuid4()
    async with _make_client(db_session, ADMIN_USER) as client:
        resp = await client.post(f"/api/ai-content/{fake_id}/confirm")
    assert resp.status_code == 404
