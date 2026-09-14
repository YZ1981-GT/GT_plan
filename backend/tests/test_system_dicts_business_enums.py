"""P2-6: 枚举字典扩展核心业务枚举测试

验证:
1. GET /dicts 返回 elimination_entry_type / audit_cycle / risk_level 三个新字典
2. 新字典 value 与源枚举一致（EliminationEntryType / 审计循环 A~N+S / RiskLevel）
3. PUT 带 value 字段 → 405（value 硬编码锁死）
4. 新字典的 label/color 可通过 PUT 正常修改
5. POST/DELETE 新字典值仍返 405

Validates: Requirements 5.1, 5.2, 5.3
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
from app.models.enum_dict_override_models import EnumDictOverride  # noqa: F401

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
ADMIN_USER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_app(db_session: AsyncSession) -> FastAPI:
    from app.routers.system_dicts import router as sd_router

    app = FastAPI()
    app.include_router(sd_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return User(
            id=ADMIN_USER_ID,
            username="admin",
            email="admin@example.com",
            hashed_password="x",
            role=UserRole.admin,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


# ─────────────────────────────────────────────────────────────────────────────
# 5.1: 新字典出现在 GET /dicts 且 value 与源枚举一致
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_dicts_includes_elimination_entry_type(db_session):
    """GET /dicts 包含 elimination_entry_type，value 与 EliminationEntryType 枚举一致。"""
    from app.models.consolidation_models import EliminationEntryType

    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.get("/api/system/dicts")
    assert resp.status_code == 200
    data = resp.json()
    assert "elimination_entry_type" in data

    items = data["elimination_entry_type"]
    dict_values = {item["value"] for item in items}
    enum_values = {e.value for e in EliminationEntryType}
    assert dict_values == enum_values


@pytest.mark.asyncio
async def test_get_dicts_includes_audit_cycle(db_session):
    """GET /dicts 包含 audit_cycle，value 为 A~N + S 共 15 个代号。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.get("/api/system/dicts")
    assert resp.status_code == 200
    data = resp.json()
    assert "audit_cycle" in data

    items = data["audit_cycle"]
    expected_codes = set("ABCDEFGHIJKLMNS")
    dict_values = {item["value"] for item in items}
    assert dict_values == expected_codes


@pytest.mark.asyncio
async def test_get_dicts_includes_risk_level(db_session):
    """GET /dicts 包含 risk_level，value 与 RiskLevel 枚举一致。"""
    from app.models.collaboration_models import RiskLevel

    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.get("/api/system/dicts")
    assert resp.status_code == 200
    data = resp.json()
    assert "risk_level" in data

    items = data["risk_level"]
    dict_values = {item["value"] for item in items}
    enum_values = {e.value for e in RiskLevel}
    assert dict_values == enum_values


# ─────────────────────────────────────────────────────────────────────────────
# 5.2: value 硬编码锁死 — PUT 带 value 字段返 405
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_with_value_field_returns_405(db_session):
    """PUT 请求体含 value 字段 → 405（value 锁死不可改）。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/elimination_entry_type/items/equity",
            json={"value": "new_value", "label": "新标签"},
        )
    assert resp.status_code == 405
    assert resp.json()["detail"]["error_code"] == "ENUM_DICT_VALUE_LOCKED"


@pytest.mark.asyncio
async def test_put_with_value_field_on_audit_cycle_returns_405(db_session):
    """PUT audit_cycle 带 value 字段 → 405。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/audit_cycle/items/A",
            json={"value": "Z", "label": "改了"},
        )
    assert resp.status_code == 405
    assert resp.json()["detail"]["error_code"] == "ENUM_DICT_VALUE_LOCKED"


@pytest.mark.asyncio
async def test_put_with_value_field_on_risk_level_returns_405(db_session):
    """PUT risk_level 带 value 字段 → 405。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/risk_level/items/high",
            json={"value": "critical"},
        )
    assert resp.status_code == 405
    assert resp.json()["detail"]["error_code"] == "ENUM_DICT_VALUE_LOCKED"


# ─────────────────────────────────────────────────────────────────────────────
# 5.2: label/color 可正常治理
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_label_on_new_dict_works(db_session):
    """PUT 仅修改 label（不含 value）→ 200，GET 返回覆盖后的 label。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/elimination_entry_type/items/equity",
            json={"label": "长期股权投资抵销"},
        )
        assert resp.status_code == 200

        get_resp = await ac.get("/api/system/dicts")
    items = get_resp.json()["elimination_entry_type"]
    equity_item = next(x for x in items if x["value"] == "equity")
    assert equity_item["label"] == "长期股权投资抵销"


@pytest.mark.asyncio
async def test_put_color_on_audit_cycle_works(db_session):
    """PUT 修改 audit_cycle 的 color → 200。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/audit_cycle/items/D",
            json={"color": "danger"},
        )
        assert resp.status_code == 200

        get_resp = await ac.get("/api/system/dicts")
    items = get_resp.json()["audit_cycle"]
    d_item = next(x for x in items if x["value"] == "D")
    assert d_item["color"] == "danger"


# ─────────────────────────────────────────────────────────────────────────────
# 5.2: POST/DELETE 新字典值仍返 405
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_new_value_to_business_enum_returns_405(db_session):
    """POST 尝试新增 value → 405。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/system/dicts/elimination_entry_type/items",
            json={"value": "new_type", "label": "新类型"},
        )
    assert resp.status_code == 405


@pytest.mark.asyncio
async def test_delete_value_from_business_enum_returns_405(db_session):
    """DELETE 尝试删除 value → 405。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.delete(
            "/api/system/dicts/risk_level/items/high",
        )
    assert resp.status_code == 405


# ─────────────────────────────────────────────────────────────────────────────
# P1-3.1: ai_content_status / archive_status 新增字典验证
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_dicts_includes_ai_content_status(db_session):
    """GET /dicts 包含 ai_content_status，4 个值：pending/confirmed/rejected/expired。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.get("/api/system/dicts")
    assert resp.status_code == 200
    data = resp.json()
    assert "ai_content_status" in data

    items = data["ai_content_status"]
    expected_values = {"pending", "confirmed", "rejected", "expired"}
    dict_values = {item["value"] for item in items}
    assert dict_values == expected_values


@pytest.mark.asyncio
async def test_get_dicts_includes_archive_status(db_session):
    """GET /dicts 包含 archive_status，4 个值：not_archived/archiving/archived/archive_failed。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.get("/api/system/dicts")
    assert resp.status_code == 200
    data = resp.json()
    assert "archive_status" in data

    items = data["archive_status"]
    expected_values = {"not_archived", "archiving", "archived", "archive_failed"}
    dict_values = {item["value"] for item in items}
    assert dict_values == expected_values


@pytest.mark.asyncio
async def test_put_value_on_ai_content_status_returns_405(db_session):
    """PUT ai_content_status 带 value 字段 → 405（P1-3.4: value 不可修改）。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/ai_content_status/items/pending",
            json={"value": "new_pending", "label": "改名"},
        )
    assert resp.status_code == 405
    assert resp.json()["detail"]["error_code"] == "ENUM_DICT_VALUE_LOCKED"


@pytest.mark.asyncio
async def test_put_value_on_archive_status_returns_405(db_session):
    """PUT archive_status 带 value 字段 → 405（P1-3.4: value 不可修改）。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/archive_status/items/archived",
            json={"value": "finished", "label": "完成归档"},
        )
    assert resp.status_code == 405
    assert resp.json()["detail"]["error_code"] == "ENUM_DICT_VALUE_LOCKED"


@pytest.mark.asyncio
async def test_post_new_value_to_ai_content_status_returns_405(db_session):
    """POST 尝试新增 ai_content_status value → 405。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/system/dicts/ai_content_status/items",
            json={"value": "auto_approved", "label": "自动通过"},
        )
    assert resp.status_code == 405


@pytest.mark.asyncio
async def test_put_label_on_ai_content_status_works(db_session):
    """PUT 修改 ai_content_status 的 label（不含 value）→ 200（label 可覆盖）。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/ai_content_status/items/confirmed",
            json={"label": "AI已确认"},
        )
        assert resp.status_code == 200

        get_resp = await ac.get("/api/system/dicts")
    items = get_resp.json()["ai_content_status"]
    confirmed = next(x for x in items if x["value"] == "confirmed")
    assert confirmed["label"] == "AI已确认"


@pytest.mark.asyncio
async def test_put_color_on_archive_status_works(db_session):
    """PUT 修改 archive_status 的 color → 200（color 可覆盖）。"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.put(
            "/api/system/dicts/archive_status/items/archive_failed",
            json={"color": "warning"},
        )
        assert resp.status_code == 200

        get_resp = await ac.get("/api/system/dicts")
    items = get_resp.json()["archive_status"]
    failed = next(x for x in items if x["value"] == "archive_failed")
    assert failed["color"] == "warning"
