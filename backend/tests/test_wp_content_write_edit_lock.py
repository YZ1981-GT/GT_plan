"""底稿内容写入校验编辑锁（spec workpaper-multi-window-lock-gaps R2.3~R2.5）。

原先保存 / 导入接口都不看编辑锁，「同一底稿第二窗只读」只靠前端：只读窗口工具栏「导入」照样把数据写进库。
现在 ``dedicated_wp_gate`` 对内容写入（导入类 / checklist-responses / save / save-version）查该底稿的有效锁，
持锁人（用户 + 窗口）以外的请求 423。
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

import app.routers._wp_gate as wp_gate
from app.models.base import Base
from app.models.editing_lock_models import EditingLock
from app.services.editing_lock_service import find_blocking_lock

if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(_engine.sync_engine, "connect")
def _fk_off(dbapi_conn, _record):  # editing_locks.holder_id 引用 users，本文件不建 users 表
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=OFF")
    cur.close()


WP = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
ME = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER = uuid.UUID("22222222-2222-4222-8222-222222222222")
WIN_A = "window-a"
WIN_B = "window-b"


@pytest_asyncio.fixture
async def db():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=[EditingLock.__table__])
        await conn.run_sync(Base.metadata.create_all, tables=[EditingLock.__table__])
    async with _Session() as session:
        yield session


async def _lock(db, *, holder=ME, instance=WIN_A, idle=timedelta(0), released=False, name="张三"):
    now = datetime.now(timezone.utc)
    row = EditingLock(
        id=uuid.uuid4(), resource_type="workpaper", resource_id=str(WP), holder_id=holder,
        holder_name=name, acquired_at=now - idle, heartbeat_at=now - idle,
        released_at=now if released else None, client_instance=instance,
    )
    db.add(row)
    await db.flush()
    return row


# ── find_blocking_lock：判定口径 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_lock_does_not_block(db):
    assert await find_blocking_lock(db, "workpaper", str(WP), ME, WIN_A) is None


@pytest.mark.asyncio
async def test_holder_same_window_not_blocked(db):
    await _lock(db)
    assert await find_blocking_lock(db, "workpaper", str(WP), ME, WIN_A) is None


@pytest.mark.asyncio
async def test_same_user_other_window_blocked(db):
    lock = await _lock(db)
    assert await find_blocking_lock(db, "workpaper", str(WP), ME, WIN_B) is lock


@pytest.mark.asyncio
async def test_other_user_blocked_with_or_without_window(db):
    lock = await _lock(db, holder=OTHER)
    assert await find_blocking_lock(db, "workpaper", str(WP), ME, WIN_A) is lock
    assert await find_blocking_lock(db, "workpaper", str(WP), ME, None) is lock


@pytest.mark.asyncio
async def test_holder_request_without_window_not_blocked(db):
    """分不出是哪个窗口（请求没带编号）⇒ 保持原行为放行（R2.4）。"""
    await _lock(db)
    assert await find_blocking_lock(db, "workpaper", str(WP), ME, None) is None


@pytest.mark.asyncio
async def test_holder_lock_without_window_not_blocked(db):
    """锁上没记窗口（旧客户端取的锁）⇒ 本人任何窗口都放行（R2.4）。"""
    await _lock(db, instance=None)
    assert await find_blocking_lock(db, "workpaper", str(WP), ME, WIN_B) is None


@pytest.mark.asyncio
async def test_expired_or_released_lock_does_not_block(db):
    await _lock(db, holder=OTHER, idle=timedelta(minutes=6))
    await _lock(db, holder=OTHER, released=True)
    assert await find_blocking_lock(db, "workpaper", str(WP), ME, WIN_A) is None


@pytest.mark.asyncio
async def test_other_resource_lock_does_not_block(db):
    await _lock(db, holder=OTHER)
    assert await find_blocking_lock(db, "workpaper", str(uuid.uuid4()), ME, WIN_A) is None


# ── dedicated_wp_gate：只对内容写入生效 ───────────────────────────────────────


def _request(method: str, route_path: str, *, window: str | None, param: str = "wp_id") -> Request:
    headers = [(b"x-client-instance", window.encode())] if window else []
    return Request({
        "type": "http", "method": method, "path": route_path.replace("{wp_id}", str(WP)),
        "headers": headers, "query_string": b"", "path_params": {param: str(WP)},
        "route": SimpleNamespace(path=route_path),
    })


@pytest.fixture
def gate_passes(monkeypatch):
    """可见性门放行（本文件只测编辑锁），并记下它确实先被调用。"""
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(wp_gate, "enforce_wp_gate", mock)
    return mock


ME_USER = SimpleNamespace(id=ME)
CHECKLIST = "/api/workpapers/{wp_id}/checklist-responses"
D4_IMPORT = "/api/workpapers/{wp_id}/d4/import-data"


@pytest.mark.asyncio
async def test_gate_rejects_other_users_content_write(db, gate_passes):
    await _lock(db, holder=OTHER, name="李四")
    with pytest.raises(HTTPException) as exc:
        await wp_gate.dedicated_wp_gate(_request("PUT", CHECKLIST, window=WIN_A), db=db, current_user=ME_USER)
    assert exc.value.status_code == 423
    assert "李四 正在编辑这张底稿" in exc.value.detail
    gate_passes.assert_awaited_once()


@pytest.mark.asyncio
async def test_gate_rejects_import_from_my_other_window(db, gate_passes):
    await _lock(db)
    with pytest.raises(HTTPException) as exc:
        await wp_gate.dedicated_wp_gate(_request("POST", D4_IMPORT, window=WIN_B), db=db, current_user=ME_USER)
    assert exc.value.status_code == 423
    assert "你的另一个窗口" in exc.value.detail


@pytest.mark.asyncio
async def test_gate_allows_holder_window(db, gate_passes):
    await _lock(db)
    for method, path in (("PUT", CHECKLIST), ("POST", D4_IMPORT), ("POST", "/api/workpapers/{wp_id}/save")):
        await wp_gate.dedicated_wp_gate(_request(method, path, window=WIN_A), db=db, current_user=ME_USER)


@pytest.mark.asyncio
async def test_gate_ignores_reads_and_non_content_writes(db, gate_passes):
    await _lock(db, holder=OTHER)
    await wp_gate.dedicated_wp_gate(_request("GET", CHECKLIST, window=WIN_A), db=db, current_user=ME_USER)
    await wp_gate.dedicated_wp_gate(
        _request("POST", "/api/workpapers/{wp_id}/ai/tsj-review", window=WIN_A), db=db, current_user=ME_USER,
    )
    # 编辑锁按 working_paper.id 记：wp_index_id 绑定的路由不适用
    await wp_gate.dedicated_wp_gate(
        _request("POST", "/api/wp-index/{wp_index_id}/save", window=WIN_A, param="wp_index_id"),
        db=db, current_user=ME_USER,
    )


def test_content_write_route_pattern():
    yes = [CHECKLIST, D4_IMPORT, "/api/workpapers/{wp_id}/save", "/api/workpapers/{wp_id}/save-version",
           "/api/workpapers/{wp_id}/import-export/import", "/api/workpapers/{wp_id}/offline/import-apply",
           "/api/m7-special-reserve/{wp_id}/import-data", "/api/workpapers/{wp_id}/bad-debt-rows/import-commit"]
    no = ["/api/workpapers/{wp_id}/ai/tsj-review", "/api/workpapers/{wp_id}/export-data",
          "/api/workpapers/{wp_id}/g11/save-adjudication", "/api/workpapers/{wp_id}/review", None, ""]
    assert all(wp_gate.is_content_write_route(p) for p in yes)
    assert not any(wp_gate.is_content_write_route(p) for p in no)


def test_every_content_write_route_goes_through_the_gate():
    """内容写入路由都挂了 dedicated_wp_gate，校验才真的生效（新加的保存 / 导入路由漏挂会在这里打红）。"""
    from fastapi.routing import APIRoute

    from app.main import app

    def gated(dep) -> bool:
        return getattr(dep, "call", None) is wp_gate.dedicated_wp_gate or any(
            gated(d) for d in getattr(dep, "dependencies", []) or []
        )

    content = [
        r for r in app.routes
        if isinstance(r, APIRoute) and "{wp_id}" in r.path
        and r.methods & {"POST", "PUT", "PATCH", "DELETE"} and wp_gate.is_content_write_route(r.path)
    ]
    assert len(content) >= 100, f"扫描面异常：只找到 {len(content)} 条内容写入路由"
    missing = sorted(r.path for r in content if not gated(r.dependant))
    assert missing == [], f"这些内容写入路由没挂 dedicated_wp_gate（编辑锁校验不生效）: {missing}"
    assert any(re.search(r"/checklist-responses$", r.path) for r in content)
