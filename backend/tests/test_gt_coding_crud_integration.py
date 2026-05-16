"""GtCoding CRUD 后端端点真实存在性核验 + 集成测试 [template-library-coordination Sprint 6 Task 6.3]

复盘退回原因：原 Task 6.3 GtCodingTab.vue 假设 POST/PUT/DELETE `/api/gt-coding/{id}`
存在但未核实。本测试通过：
  1. 遍历 router.routes 验证三个端点存在并接受正确的 HTTP method
  2. admin 角色 POST 创建成功；auditor 角色 POST 返回 403（require_role 把关）
  3. POST 创建 → PUT 更新 description → GET 验证持久化
  4. admin DELETE 成功；auditor DELETE 返回 403

Validates: Requirements 11.5 (admin-only edit), Property 16 (Backend mutation authorization)
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# SQLite JSONB 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.core import User, UserRole  # noqa: E402

# 注册全部 ORM 模型到 metadata
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.phase10_models  # noqa: E402, F401
import app.models.phase12_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401
import app.models.phase15_models  # noqa: E402, F401
import app.models.phase16_models  # noqa: E402, F401
import app.models.archive_models  # noqa: E402, F401
import app.models.knowledge_models  # noqa: E402, F401

import sqlalchemy as _sa  # noqa: E402

# Stub for 'workpapers' table referenced by AI models FK
class _WorkpaperStub(Base):
    __tablename__ = "workpapers"
    __table_args__ = {"extend_existing": True}
    id = _sa.Column(_sa.Uuid, primary_key=True)


_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


ADMIN_USER_ID = uuid.uuid4()
AUDITOR_USER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        admin = User(
            id=ADMIN_USER_ID,
            username="gt_admin",
            email="gt_admin@test.com",
            hashed_password="x",
            role=UserRole.admin,
        )
        auditor = User(
            id=AUDITOR_USER_ID,
            username="gt_auditor",
            email="gt_auditor@test.com",
            hashed_password="x",
            role=UserRole.auditor,
        )
        session.add_all([admin, auditor])
        await session.commit()
        yield session


def _make_app(db_session: AsyncSession, user_id: uuid.UUID, role: UserRole) -> FastAPI:
    """构造最小 FastAPI app，挂载 gt_coding router；不绕过 require_role。"""
    from app.routers.gt_coding import router as gt_router

    app = FastAPI()
    app.include_router(gt_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return User(
            id=user_id,
            username=f"test_{role.value}",
            email=f"{role.value}@test.com",
            hashed_password="x",
            role=role,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    # 关键：不 override require_role，让真实权限守卫触发
    return app


def _client(db_session: AsyncSession, user_id: uuid.UUID, role: UserRole):
    return AsyncClient(transport=ASGITransport(app=_make_app(db_session, user_id, role)), base_url="http://test")


# ---------------------------------------------------------------------------
# Test 1: 三个 CRUD 端点存在性核验（router.routes 遍历）
# ---------------------------------------------------------------------------


def test_gt_coding_routes_registered():
    """遍历 router.routes，验证 POST /api/gt-coding、PUT /api/gt-coding/{id}、
    DELETE /api/gt-coding/{id} 三个端点均已注册到 router 上。

    Validates: GtCodingTab.vue 假设的端点真实存在（修复退回原因之一）
    """
    from app.routers.gt_coding import router

    # 收集 (method, path) 元组集合
    registered: set[tuple[str, str]] = set()
    for route in router.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                registered.add((method, route.path))

    # 必须存在的三个端点
    assert ("POST", "/api/gt-coding") in registered, (
        f"POST /api/gt-coding 未注册！已注册路由: {sorted(registered)}"
    )
    assert ("PUT", "/api/gt-coding/{coding_id}") in registered, (
        f"PUT /api/gt-coding/{{coding_id}} 未注册！已注册路由: {sorted(registered)}"
    )
    assert ("DELETE", "/api/gt-coding/{coding_id}") in registered, (
        f"DELETE /api/gt-coding/{{coding_id}} 未注册！已注册路由: {sorted(registered)}"
    )


# ---------------------------------------------------------------------------
# Test 2: admin 创建成功 / auditor 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_gt_coding_admin_only(db_session: AsyncSession):
    """admin 角色 POST 创建编码 → 200；auditor 角色 → 403（require_role 把关）。

    Validates: Requirements 11.5 (admin-only edit) + Property 16
    """
    payload = {
        "code_prefix": "X1",
        "code_range": "X1-1",
        "cycle_name": "测试循环",
        "wp_type": "specific",
        "description": "集成测试新建",
        "sort_order": 999,
    }

    # auditor → 403
    async with _client(db_session, AUDITOR_USER_ID, UserRole.auditor) as ac:
        resp_auditor = await ac.post("/api/gt-coding", json=payload)
    assert resp_auditor.status_code == 403, (
        f"auditor 应被拒绝，实际 {resp_auditor.status_code}: {resp_auditor.text}"
    )

    # admin → 200
    async with _client(db_session, ADMIN_USER_ID, UserRole.admin) as ac:
        resp_admin = await ac.post("/api/gt-coding", json=payload)
    assert resp_admin.status_code == 200, (
        f"admin 创建应成功，实际 {resp_admin.status_code}: {resp_admin.text}"
    )
    body = resp_admin.json()
    # 全局 ResponseWrapperMiddleware 可能包裹响应，业务字段在顶层或 data 字段
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    assert data.get("code_prefix") == "X1"
    assert data.get("code_range") == "X1-1"
    assert data.get("description") == "集成测试新建"


# ---------------------------------------------------------------------------
# Test 3: POST 创建 → PUT 更新 → GET 验证持久化
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_gt_coding_persists(db_session: AsyncSession):
    """POST 创建一条 → PUT 更新 description → GET 验证 description 已变。

    Validates: Requirements 11.5（编辑功能真实可用）
    """
    create_payload = {
        "code_prefix": "X2",
        "code_range": "X2-1",
        "cycle_name": "更新测试",
        "wp_type": "specific",
        "description": "原始描述",
        "sort_order": 998,
    }

    async with _client(db_session, ADMIN_USER_ID, UserRole.admin) as ac:
        # 创建
        r_create = await ac.post("/api/gt-coding", json=create_payload)
        assert r_create.status_code == 200, r_create.text
        body = r_create.json()
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        coding_id = data["id"]

        # 更新 description
        update_payload = {"description": "已更新描述"}
        r_update = await ac.put(f"/api/gt-coding/{coding_id}", json=update_payload)
        assert r_update.status_code == 200, r_update.text
        u_body = r_update.json()
        u_data = u_body.get("data") if isinstance(u_body.get("data"), dict) else u_body
        assert u_data.get("description") == "已更新描述"

        # GET 验证持久化
        r_get = await ac.get(f"/api/gt-coding/{coding_id}")
        assert r_get.status_code == 200, r_get.text
        g_body = r_get.json()
        g_data = g_body.get("data") if isinstance(g_body.get("data"), dict) else g_body
        assert g_data.get("description") == "已更新描述"
        assert g_data.get("code_prefix") == "X2"  # 其他字段保持


# ---------------------------------------------------------------------------
# Test 4: admin DELETE 成功 / auditor DELETE 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_gt_coding_admin_only(db_session: AsyncSession):
    """admin DELETE 成功（软删除）；auditor DELETE 403。

    Validates: Requirements 11.5 + Property 16
    """
    create_payload = {
        "code_prefix": "X3",
        "code_range": "X3-1",
        "cycle_name": "删除测试",
        "wp_type": "specific",
        "description": "待删除",
        "sort_order": 997,
    }

    async with _client(db_session, ADMIN_USER_ID, UserRole.admin) as ac:
        r_create = await ac.post("/api/gt-coding", json=create_payload)
        assert r_create.status_code == 200, r_create.text
        body = r_create.json()
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        coding_id = data["id"]

    # auditor 删 → 403
    async with _client(db_session, AUDITOR_USER_ID, UserRole.auditor) as ac:
        r_aud = await ac.delete(f"/api/gt-coding/{coding_id}")
    assert r_aud.status_code == 403, (
        f"auditor 应被拒绝，实际 {r_aud.status_code}: {r_aud.text}"
    )

    # admin 删 → 200
    async with _client(db_session, ADMIN_USER_ID, UserRole.admin) as ac:
        r_adm = await ac.delete(f"/api/gt-coding/{coding_id}")
    assert r_adm.status_code == 200, (
        f"admin 删除应成功，实际 {r_adm.status_code}: {r_adm.text}"
    )
    d_body = r_adm.json()
    d_data = d_body.get("data") if isinstance(d_body.get("data"), dict) else d_body
    assert d_data.get("deleted") is True
