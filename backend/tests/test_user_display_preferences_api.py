"""账号显示偏好 API、CAS 与审计脱敏集成测试。

所有写入都落在 pytest 临时 SQLite 文件；审计测试使用真实 AuditLogMiddleware 和
真实 Log ORM 表，不连接共享开发库。

Validates: Requirements R2、NFR 安全 / AC-01～AC-03、AC-24。
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import create_access_token
from app.deps import get_current_user
from app.middleware import audit_log
from app.middleware.audit_log import AuditLogMiddleware
from app.middleware.error_handler import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.middleware.response import ResponseWrapperMiddleware
from app.models.base import UserRole
from app.models.core import Log, User
from app.models.user_display_preferences import UserDisplayPreferences
from app.routers.user_display_preferences import router
from app.schemas.display_preferences import DisplayPreferencesPatch
from app.services.user_display_preferences_service import (
    DisplayPrefsRevisionConflict,
    patch_preferences,
)

_TABLES = (User.__table__, UserDisplayPreferences.__table__, Log.__table__)


def _headers(user_id) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}


def _data(response) -> dict:
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code"] == 200
    return payload["data"]


@pytest_asyncio.fixture
async def prefs_world(tmp_path, monkeypatch):
    """带实际路由、响应包装和审计中间件的隔离 API 世界。"""

    database_path = (tmp_path / "display-preferences.sqlite").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: User.metadata.create_all(
                sync_connection,
                tables=_TABLES,
            )
        )

    users = [uuid4(), uuid4()]
    async with sessions() as db:
        for index, user_id in enumerate(users):
            db.add(User(
                id=user_id,
                username=f"display-prefs-{index}",
                email=f"display-prefs-{index}@test.invalid",
                hashed_password="test-only",
                role=UserRole.auditor,
            ))
        await db.commit()

    current = {"user": SimpleNamespace(id=users[0])}
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    app.include_router(router)

    async def override_db():
        async with sessions() as db:
            yield db

    async def override_user():
        return current["user"]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    # 顺序与 main.py 的内层片段一致：审计看到路由原始成功体，外层再包 ApiResponse。
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(ResponseWrapperMiddleware)
    monkeypatch.setattr(audit_log, "async_session", sessions)

    world = SimpleNamespace(app=app, sessions=sessions, users=users, current=current)
    try:
        yield world
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_returns_complete_defaults_and_never_creates_a_row(prefs_world):
    async with AsyncClient(
        transport=ASGITransport(app=prefs_world.app), base_url="http://test",
    ) as client:
        data = _data(await client.get(
            "/api/users/me/display-preferences", headers=_headers(prefs_world.users[0]),
        ))

    assert data == {
        "amount_unit_override": None,
        "font_size": "sm",
        "show_zero": False,
        "decimals": 2,
        "negative_red": True,
        "highlight_threshold": 0.2,
        "density": "default",
        "grid_edit_mode": "excel",
        "fixed_columns": {},
        "revision": 0,
        "updated_at": None,
    }
    async with prefs_world.sessions() as db:
        assert (await db.execute(select(UserDisplayPreferences))).scalars().all() == []


@pytest.mark.asyncio
async def test_current_user_api_rejects_unauthenticated_requests(prefs_world):
    """去掉 get_current_user 依赖覆盖时，端点仍由真实鉴权依赖返回 401。"""

    override = prefs_world.app.dependency_overrides.pop(get_current_user)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=prefs_world.app), base_url="http://test",
        ) as client:
            response = await client.get("/api/users/me/display-preferences")
        assert response.status_code == 401
    finally:
        prefs_world.app.dependency_overrides[get_current_user] = override


@pytest.mark.asyncio
async def test_current_user_isolation_keeps_each_account_preferences_separate(prefs_world):
    async with AsyncClient(
        transport=ASGITransport(app=prefs_world.app), base_url="http://test",
    ) as client:
        first = _data(await client.patch(
            "/api/users/me/display-preferences",
            headers=_headers(prefs_world.users[0]),
            json={"base_revision": 0, "font_size": "lg", "amount_unit_override": "wan"},
        ))
        prefs_world.current["user"] = SimpleNamespace(id=prefs_world.users[1])
        second = _data(await client.get(
            "/api/users/me/display-preferences", headers=_headers(prefs_world.users[1]),
        ))
        own = _data(await client.patch(
            "/api/users/me/display-preferences",
            headers=_headers(prefs_world.users[1]),
            json={"base_revision": 0, "font_size": "xs"},
        ))
        prefs_world.current["user"] = SimpleNamespace(id=prefs_world.users[0])
        reread = _data(await client.get(
            "/api/users/me/display-preferences", headers=_headers(prefs_world.users[0]),
        ))

    assert first["revision"] == reread["revision"] == 1
    assert reread["font_size"] == "lg" and reread["amount_unit_override"] == "wan"
    assert second["revision"] == 0 and second["font_size"] == "sm"
    assert own["revision"] == 1 and own["font_size"] == "xs"


@pytest.mark.asyncio
async def test_patch_replaces_fixed_column_mapping_and_preserves_unchanged_saved_at(prefs_world):
    async with AsyncClient(
        transport=ASGITransport(app=prefs_world.app), base_url="http://test",
    ) as client:
        initial = _data(await client.patch(
            "/api/users/me/display-preferences",
            headers=_headers(prefs_world.users[0]),
            json={
                "base_revision": 0,
                "fixed_columns": {
                    "trial-balance": {"columns": ["account_code"]},
                    "report-view:normal": {"columns": ["row_code"]},
                },
            },
        ))
        original_saved_at = initial["fixed_columns"]["trial-balance"]["saved_at"]
        replacement = _data(await client.patch(
            "/api/users/me/display-preferences",
            headers=_headers(prefs_world.users[0]),
            json={
                "base_revision": initial["revision"],
                "font_size": "md",
                "fixed_columns": {
                    "trial-balance": {"columns": ["account_code"]},
                    "report-view:compare": {"columns": ["variance"]},
                },
            },
        ))

    fixed = replacement["fixed_columns"]
    assert replacement["revision"] == 2
    assert replacement["font_size"] == "md"
    assert set(fixed) == {"trial-balance", "report-view:compare"}
    assert fixed["trial-balance"]["saved_at"] == original_saved_at
    assert fixed["report-view:compare"]["columns"] == ["variance"]
    assert "saved_at" in fixed["report-view:compare"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"base_revision": 0},
        {"base_revision": 0, "font_size": None},
        {"base_revision": 0, "fixed_columns": None},
        {"base_revision": 0, "font_size": "sm", "extra": "no"},
        {"base_revision": 0, "decimals": 7},
        {"base_revision": 0, "highlight_threshold": 0.12345},
        {"base_revision": 0, "fixed_columns": {"page": {"columns": ["x"], "saved_at": "x"}}},
    ],
)
async def test_patch_rejects_empty_or_invalid_boundary_payloads(prefs_world, body):
    async with AsyncClient(
        transport=ASGITransport(app=prefs_world.app), base_url="http://test",
    ) as client:
        response = await client.patch(
            "/api/users/me/display-preferences",
            headers=_headers(prefs_world.users[0]),
            json=body,
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_stale_revision_returns_current_instead_of_reporting_success(prefs_world):
    async with AsyncClient(
        transport=ASGITransport(app=prefs_world.app), base_url="http://test",
    ) as client:
        created = _data(await client.patch(
            "/api/users/me/display-preferences",
            headers=_headers(prefs_world.users[0]),
            json={"base_revision": 0, "font_size": "lg"},
        ))
        conflict = await client.patch(
            "/api/users/me/display-preferences",
            headers=_headers(prefs_world.users[0]),
            json={"base_revision": 0, "font_size": "xs"},
        )
        final = _data(await client.get(
            "/api/users/me/display-preferences", headers=_headers(prefs_world.users[0]),
        ))

    assert created["revision"] == 1
    assert conflict.status_code == 409
    payload = conflict.json()
    assert payload["code"] == "DISPLAY_PREFS_REVISION_CONFLICT"
    assert payload["current"]["revision"] == 1
    assert payload["current"]["font_size"] == "lg"
    assert final["revision"] == 1 and final["font_size"] == "lg"


@pytest.mark.asyncio
async def test_real_audit_middleware_logs_only_revision_and_changed_field_names(prefs_world):
    marker_page_key = "private-page-key-must-not-be-logged"
    async with AsyncClient(
        transport=ASGITransport(app=prefs_world.app), base_url="http://test",
    ) as client:
        response = await client.patch(
            "/api/users/me/display-preferences",
            headers=_headers(prefs_world.users[0]),
            json={
                "base_revision": 0,
                "amount_unit_override": "wan",
                "font_size": "lg",
                "decimals": 4,
                "highlight_threshold": 0.3456,
                "fixed_columns": {marker_page_key: {"columns": ["secret-column-key"]}},
            },
        )
    assert _data(response)["revision"] == 1

    async with prefs_world.sessions() as db:
        log = (await db.execute(select(Log).order_by(Log.id))).scalar_one()
    assert log.user_id == prefs_world.users[0]
    assert log.new_value == {
        "revision": 1,
        "changed_fields": [
            "amount_unit_override",
            "decimals",
            "fixed_columns",
            "font_size",
            "highlight_threshold",
        ],
    }
    serialized = repr(log.new_value)
    for secret in (marker_page_key, "secret-column-key", "wan", "0.3456"):
        assert secret not in serialized


@pytest.mark.asyncio
async def test_service_uses_database_revision_predicate_after_a_stale_read(prefs_world):
    """去掉 UPDATE 的 ``WHERE revision`` 时，这个交错写入会错误地覆盖获胜方。"""

    user_id = prefs_world.users[0]
    async with prefs_world.sessions() as seed:
        await patch_preferences(seed, user_id, DisplayPreferencesPatch(
            base_revision=0, font_size="sm",
        ))
        await seed.commit()

    async with prefs_world.sessions() as stale, prefs_world.sessions() as winner:
        stale_row = (await stale.execute(
            select(UserDisplayPreferences).where(UserDisplayPreferences.user_id == user_id)
        )).scalar_one()
        await patch_preferences(winner, user_id, DisplayPreferencesPatch(
            base_revision=1, font_size="lg",
        ))
        await winner.commit()
        # 保留读取到的 base revision，但结束 SQLite 的旧读事务，使冲突回读可见获胜提交。
        await stale.rollback()

        with pytest.raises(DisplayPrefsRevisionConflict) as raised:
            await patch_preferences(
                stale,
                user_id,
                DisplayPreferencesPatch(base_revision=1, font_size="xs"),
            )
        await stale.rollback()

    assert raised.value.current.revision == 2
    assert raised.value.current.font_size == "lg"


@pytest.mark.asyncio
async def test_service_flushes_without_committing_its_caller_transaction(prefs_world, monkeypatch):
    """SQLite 中先建立真实外层写事务，SAVEPOINT 才不会独自提交。"""

    user_id = prefs_world.users[0]
    async with prefs_world.sessions() as db:
        outer = await db.begin()
        try:
            user = await db.get(User, user_id)
            assert user is not None
            original_username = user.username
            transaction_marker = "outer-transaction-marker"
            # SQLite 的 ``Session.begin()`` 是惰性的。先发出可回滚的 DML，确保 service
            # 创建的 begin_nested() 是外层事务中的 SAVEPOINT，而不是根事务。
            await db.execute(
                update(User)
                .where(User.id == user_id)
                .values(username=transaction_marker)
            )
            persisted_marker = await db.scalar(
                select(User.username).where(User.id == user_id)
            )
            assert persisted_marker == transaction_marker

            commit = AsyncMock(wraps=db.commit)
            monkeypatch.setattr(db, "commit", commit)
            result, _ = await patch_preferences(
                db,
                user_id,
                DisplayPreferencesPatch(base_revision=0, show_zero=True),
            )
            assert result.revision == 1
            commit.assert_not_awaited()
        finally:
            if outer.is_active:
                await outer.rollback()

    async with prefs_world.sessions() as verify:
        restored_user = await verify.get(User, user_id)
        rows = (await verify.execute(select(UserDisplayPreferences))).scalars().all()
    assert restored_user is not None
    assert restored_user.username == original_username
    assert rows == []


class _FailingDb:
    """路由异常分支只需要 execute/rollback；execute 模拟数据库不可用。"""

    def __init__(self) -> None:
        self.rollback = AsyncMock()
        self.commit = AsyncMock()

    async def execute(self, *_args, **_kwargs):
        raise RuntimeError("test database failure")


@pytest.mark.asyncio
async def test_database_failure_rolls_back_router_transaction_without_exposing_payload():
    failing_db = _FailingDb()
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: failing_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
        ) as client:
            response = await client.patch(
                "/api/users/me/display-preferences",
                json={"base_revision": 0, "font_size": "lg"},
            )
        assert response.status_code == 500
        assert response.json()["message"] == "服务器内部错误"
        failing_db.rollback.assert_awaited_once()
        failing_db.commit.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_explicit_follow_project_null_is_persisted_not_dropped(prefs_world):
    """把 exclude_unset 错换为 exclude_none 会使这条回归失败。"""

    async with AsyncClient(
        transport=ASGITransport(app=prefs_world.app), base_url="http://test",
    ) as client:
        first = _data(await client.patch(
            "/api/users/me/display-preferences",
            headers=_headers(prefs_world.users[0]),
            json={"base_revision": 0, "amount_unit_override": "wan"},
        ))
        followed = _data(await client.patch(
            "/api/users/me/display-preferences",
            headers=_headers(prefs_world.users[0]),
            json={"base_revision": first["revision"], "amount_unit_override": None},
        ))

    assert followed["revision"] == 2
    assert followed["amount_unit_override"] is None


@pytest.mark.asyncio
async def test_endpoint_rejects_fixed_columns_that_exceed_canonical_storage_limit(prefs_world):
    oversized = {
        f"page-{index:03d}": {"columns": [f"column-{column:03d}-" + "x" * 88 for column in range(20)]}
        for index in range(100)
    }
    async with AsyncClient(
        transport=ASGITransport(app=prefs_world.app), base_url="http://test",
    ) as client:
        response = await client.patch(
            "/api/users/me/display-preferences",
            headers=_headers(prefs_world.users[0]),
            json={"base_revision": 0, "fixed_columns": oversized},
        )
    assert response.status_code == 422
