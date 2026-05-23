"""DT-3 方案 B：枚举字典 label/color 覆盖测试

验证：
1. PUT /dicts/{key}/items/{value} 仅 admin 可调用（其他角色 403）
2. PUT 修改 label → GET 返回覆盖后的 label，value/其他字段不变
3. PUT 修改 color → GET 返回覆盖后的 color
4. PUT 同时修改 label + color → 都生效
5. PUT 不存在的 dict_key → 404
6. PUT 不存在的 value → 404（不允许新增）
7. PUT label/color 都为 None → 400
8. PUT color 非白名单值 → 400
9. POST /dicts/{key}/items → 405（不允许新增 value）
10. DELETE /dicts/{key}/items/{value} → 405（不允许物理删除 value）
11. DELETE /dicts/{key}/items/{value}/override → 清除覆盖，恢复代码默认值

Validates: spec proposal-remaining-18 task 1.5 复盘修复
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base
from app.models.core import User, UserRole
from app.models.enum_dict_override_models import EnumDictOverride  # noqa: F401  保证 metadata 注册

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
ADMIN_USER_ID = uuid.uuid4()
NON_ADMIN_USER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_app(db_session: AsyncSession, role: UserRole = UserRole.admin) -> FastAPI:
    from app.routers.system_dicts import router as sd_router

    app = FastAPI()
    app.include_router(sd_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return User(
            id=ADMIN_USER_ID if role == UserRole.admin else NON_ADMIN_USER_ID,
            username="testuser",
            email="t@example.com",
            hashed_password="x",
            role=role,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


# ─────────────────────────────────────────────────────────────────────────────
# RBAC
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_non_admin_returns_403(db_session):
    app = _make_app(db_session, role=UserRole.auditor)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/wp_status/items/draft",
            json={"label": "草稿v2"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "ENUM_DICT_FORBIDDEN"


# ─────────────────────────────────────────────────────────────────────────────
# 修改 label / color
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_label_then_get_returns_overridden(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        # 修改 wp_status.draft 的 label
        put_resp = await ac.put(
            "/api/system/dicts/wp_status/items/draft",
            json={"label": "草稿（已改）"},
        )
        assert put_resp.status_code == 200
        # GET 应返回覆盖后的 label
        get_resp = await ac.get("/api/system/dicts")
    assert get_resp.status_code == 200
    items = get_resp.json()["wp_status"]
    draft_item = next(x for x in items if x["value"] == "draft")
    assert draft_item["label"] == "草稿（已改）"
    # color 没改，应保持代码默认 warning
    assert draft_item["color"] == "warning"


@pytest.mark.asyncio
async def test_put_color_then_get_returns_overridden(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        put_resp = await ac.put(
            "/api/system/dicts/wp_status/items/draft",
            json={"color": "danger"},
        )
        assert put_resp.status_code == 200
        get_resp = await ac.get("/api/system/dicts")
    items = get_resp.json()["wp_status"]
    draft_item = next(x for x in items if x["value"] == "draft")
    assert draft_item["color"] == "danger"
    assert draft_item["label"] == "草稿"  # 代码默认值


@pytest.mark.asyncio
async def test_put_both_label_and_color(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        await ac.put(
            "/api/system/dicts/wp_status/items/draft",
            json={"label": "新标签", "color": "info"},
        )
        get_resp = await ac.get("/api/system/dicts")
    items = get_resp.json()["wp_status"]
    draft_item = next(x for x in items if x["value"] == "draft")
    assert draft_item["label"] == "新标签"
    assert draft_item["color"] == "info"


# ─────────────────────────────────────────────────────────────────────────────
# 错误路径
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_unknown_dict_key_returns_404(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/nonexistent_dict/items/draft",
            json={"label": "x"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error_code"] == "DICT_NOT_FOUND"


@pytest.mark.asyncio
async def test_put_unknown_value_returns_404(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/wp_status/items/totally_new_value",
            json={"label": "x"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error_code"] == "DICT_VALUE_NOT_FOUND"


@pytest.mark.asyncio
async def test_put_empty_payload_returns_400(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/wp_status/items/draft",
            json={},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "EMPTY_UPDATE"


@pytest.mark.asyncio
async def test_put_invalid_color_returns_400(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/wp_status/items/draft",
            json={"color": "rainbow"},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "INVALID_COLOR"


# ─────────────────────────────────────────────────────────────────────────────
# 405：仍拒绝新增 value 与物理删除 value
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_create_value_still_405(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/system/dicts/wp_status/items", json={})
    assert resp.status_code == 405
    assert resp.json()["detail"]["error_code"] == "ENUM_DICT_HARDCODED"


@pytest.mark.asyncio
async def test_delete_value_still_405(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.delete("/api/system/dicts/wp_status/items/draft")
    assert resp.status_code == 405
    assert resp.json()["detail"]["error_code"] == "ENUM_DICT_HARDCODED"


# ─────────────────────────────────────────────────────────────────────────────
# DELETE override：恢复代码默认值
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_override_restores_default(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        # 先改
        await ac.put(
            "/api/system/dicts/wp_status/items/draft",
            json={"label": "改了", "color": "danger"},
        )
        # 验证已改
        get1 = await ac.get("/api/system/dicts")
        assert next(x for x in get1.json()["wp_status"] if x["value"] == "draft")["label"] == "改了"
        # 重置覆盖
        del_resp = await ac.delete("/api/system/dicts/wp_status/items/draft/override")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] == 1
        # 验证恢复默认
        get2 = await ac.get("/api/system/dicts")
    items = get2.json()["wp_status"]
    draft_item = next(x for x in items if x["value"] == "draft")
    assert draft_item["label"] == "草稿"
    assert draft_item["color"] == "warning"


@pytest.mark.asyncio
async def test_delete_override_non_admin_403(db_session):
    app = _make_app(db_session, role=UserRole.qc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.delete("/api/system/dicts/wp_status/items/draft/override")
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Idempotent：PUT 同一项两次只产生 1 行 override
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_twice_is_upsert(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        await ac.put("/api/system/dicts/wp_status/items/draft", json={"label": "v1"})
        await ac.put("/api/system/dicts/wp_status/items/draft", json={"label": "v2"})
    # DB 中应只有 1 行
    import sqlalchemy as sa
    rows = (await db_session.execute(sa.select(EnumDictOverride))).scalars().all()
    assert len(rows) == 1
    assert rows[0].label_override == "v2"
