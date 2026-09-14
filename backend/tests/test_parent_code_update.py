"""PATCH /api/projects/{project_id}/parent-code 端点验证
（group-tree-architecture Task 15.2 / 16.1）。

覆盖：
- (a) 更新 parent_company_code 成功 + 字段已变更
- (b) 自引用（设为自身 company_code）→ 400 拒绝
- (c) 循环引用（A→B→A）→ 400 拒绝
- (d) parent 指向不存在的代码 → 允许（脱挂，200）
- (e) 端点已挂载

测试用内存 SQLite + ASGITransport。app_audit_log 是 PG 专用表
（gen_random_uuid/::jsonb），SQLite 上 INSERT 会失败，但端点 try/except 吞掉，
故主更新仍返回 200。
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, UserRole
from app.models.core import Project
from app.routers.project_wizard import router as project_wizard_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

USER_ID = uuid.uuid4()

ULTIMATE = "91110000000000000U"
CODE_A = "9111000000000000AA"
CODE_B = "9111000000000000BB"


class _FakeUser:
    def __init__(self, uid: uuid.UUID, role: UserRole = UserRole.admin):
        self.id = uid
        self.username = "test_user"
        self.email = "u@test.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


async def _seed(session: AsyncSession) -> dict[str, uuid.UUID]:
    """种子：合并根 + 子公司A + 子公司B（同一 ultimate, 2025）。

    初始关系：A.parent = ULTIMATE，B.parent = A。
    返回 {code: project_id}。
    """
    root_id = uuid.uuid4()
    a_id = uuid.uuid4()
    b_id = uuid.uuid4()
    session.add(Project(
        id=root_id,
        name="集团母公司_2025",
        client_name="集团母公司",
        company_code=ULTIMATE,
        parent_company_code=None,
        ultimate_company_code=ULTIMATE,
        report_scope="consolidated",
        audit_year=2025,
        audit_period_end=date(2025, 12, 31),
    ))
    session.add(Project(
        id=a_id,
        name="子公司A_2025",
        client_name="子公司A",
        company_code=CODE_A,
        parent_company_code=ULTIMATE,
        ultimate_company_code=ULTIMATE,
        report_scope="consolidated",
        audit_year=2025,
        audit_period_end=date(2025, 12, 31),
    ))
    session.add(Project(
        id=b_id,
        name="子公司B_2025",
        client_name="子公司B",
        company_code=CODE_B,
        parent_company_code=CODE_A,
        ultimate_company_code=ULTIMATE,
        report_scope="consolidated",
        audit_year=2025,
        audit_period_end=date(2025, 12, 31),
    ))
    await session.commit()
    return {ULTIMATE: root_id, CODE_A: a_id, CODE_B: b_id}


def _make_app(db_session: AsyncSession) -> FastAPI:
    app = FastAPI()
    app.include_router(project_wizard_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser(USER_ID)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


@pytest.mark.asyncio
async def test_update_parent_code_success(db_session: AsyncSession):
    """(a)+(e) 更新成功，字段变更，端点已挂载。

    将 B 的上级从 A 改为 ULTIMATE（直挂集团根）。
    """
    ids = await _seed(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/projects/{ids[CODE_B]}/parent-code",
            json={"parent_company_code": ULTIMATE},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["parent_company_code"] == ULTIMATE
    # parent_project_id 解析到合并根
    assert data["parent_project_id"] == str(ids[ULTIMATE])

    # DB 实际已变更
    db_session.expire_all()
    refreshed = await db_session.get(Project, ids[CODE_B])
    assert refreshed.parent_company_code == ULTIMATE


@pytest.mark.asyncio
async def test_update_parent_code_detach_to_top(db_session: AsyncSession):
    """空字符串 → 脱挂到顶层（parent_company_code=None, parent_project_id=None）。"""
    ids = await _seed(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/projects/{ids[CODE_B]}/parent-code",
            json={"parent_company_code": ""},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["parent_company_code"] is None
    assert data["parent_project_id"] is None


@pytest.mark.asyncio
async def test_self_parent_rejected(db_session: AsyncSession):
    """(b) 设为自身 company_code → 400。"""
    ids = await _seed(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/projects/{ids[CODE_A]}/parent-code",
            json={"parent_company_code": CODE_A},
        )

    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_cycle_rejected(db_session: AsyncSession):
    """(c) 循环引用（A→B→A）→ 400。

    初始 B.parent = A（B 是 A 的后代）。现尝试将 A.parent 设为 B
    → A 成为 B 的后代，而 B 又是 A 的后代 → 循环。
    """
    ids = await _seed(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/projects/{ids[CODE_A]}/parent-code",
            json={"parent_company_code": CODE_B},
        )

    assert resp.status_code == 400, resp.text
    assert "循环" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_parent_nonexistent_code_allowed(db_session: AsyncSession):
    """(d) parent 指向不存在的代码 → 允许（脱挂，200，parent_project_id=None）。"""
    ids = await _seed(db_session)
    app = _make_app(db_session)
    ghost_code = "9111000000000000ZZ"  # 不存在
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/projects/{ids[CODE_B]}/parent-code",
            json={"parent_company_code": ghost_code},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["parent_company_code"] == ghost_code
    # 指向不存在企业 → 脱挂，parent_project_id 置 None
    assert data["parent_project_id"] is None


@pytest.mark.asyncio
async def test_update_parent_code_project_not_found(db_session: AsyncSession):
    """不存在的 project_id → 404。"""
    await _seed(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            f"/api/projects/{uuid.uuid4()}/parent-code",
            json={"parent_company_code": ULTIMATE},
        )

    assert resp.status_code == 404, resp.text
