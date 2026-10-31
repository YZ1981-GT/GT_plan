"""底稿写入校验编辑锁（spec workpaper-multi-window-lock-gaps R2.3~R2.5、R3.1）。

原先保存 / 导入接口都不看编辑锁，「同一底稿第二窗只读」只靠前端：只读窗口工具栏「导入」照样把数据写进库。
第一轮 ``dedicated_wp_gate`` 只对导入类 / checklist-responses / save / save-version 查锁；第二轮改为 ``{wp_id}`` 写路由默认都查，
豁免四类见 ``_wp_edit_lock_scope``（全量路由守卫在 ``test_wp_edit_lock_scope_guard.py``）。持锁人（用户 + 窗口）以外 423。
"""
from __future__ import annotations

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
from app.routers._wp_edit_lock_scope import EditLockScope, edit_lock_scope
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


def test_edit_lock_scope_of_route_templates():
    """第二轮（R3.1）：默认校验，只有四类不在门里判。第一轮漏掉的裁决保存、OCR、公式、Univer 保存现在都校验。"""
    check = [CHECKLIST, D4_IMPORT, "/api/workpapers/{wp_id}/save", "/api/workpapers/{wp_id}/save-version",
             "/api/workpapers/{wp_id}/g11/save-adjudication", "/api/workpapers/{wp_id}/e1/statement-ocr",
             "/api/workpapers/{wp_id}/formulas", "/api/projects/{project_id}/working-papers/{wp_id}/univer-save",
             "/api/projects/{project_id}/workpapers/{wp_id}/template-file/init", "/api/brand-new/{wp_id}/whatever",
             None, ""]
    expected = {
        "/api/workpapers/{wp_id}/ai/tsj-review": EditLockScope.NO_WRITE,
        "/api/workpapers/{wp_id}/export-data": EditLockScope.NO_WRITE,
        "/api/workpapers/{wp_id}/d1/ai-generate": EditLockScope.NO_WRITE,
        "/api/working-papers/{wp_id}/reviews": EditLockScope.COLLAB,
        "/api/workpapers/{wp_id}/annotations": EditLockScope.COLLAB,
        "/api/workpapers/{wp_id}/sheets/{sheet_name}/lock": EditLockScope.LOCK,
        "/api/projects/{project_id}/workpapers/{wp_id}/h1/depreciation-calc": EditLockScope.ON_APPLY,
    }
    assert [p for p in check if edit_lock_scope(p) is not EditLockScope.CHECK] == []
    assert {p: edit_lock_scope(p) for p in expected} == expected


OCR = "/api/workpapers/{wp_id}/e1/statement-ocr"
REVIEWS = "/api/working-papers/{wp_id}/reviews"
CALC = "/api/projects/{project_id}/workpapers/{wp_id}/h1/depreciation-calc"


@pytest.mark.asyncio
async def test_gate_rejects_writes_missed_in_round_one(db, gate_passes):
    await _lock(db, holder=OTHER, name="李四")
    for path in (OCR, "/api/workpapers/{wp_id}/g11/save-adjudication", "/api/workpapers/{wp_id}/formulas"):
        with pytest.raises(HTTPException) as exc:
            await wp_gate.dedicated_wp_gate(_request("POST", path, window=WIN_A), db=db, current_user=ME_USER)
        assert exc.value.status_code == 423 and "李四 正在编辑" in exc.value.detail, path


@pytest.mark.asyncio
async def test_gate_lets_collaboration_and_calculation_through(db, gate_passes):
    """复核意见、批注、sheet 锁、AI 文本、只算不写的计算：编制人持锁时照常（R3.1 ①~④）。"""
    await _lock(db, holder=OTHER)
    for path in (REVIEWS, "/api/workpapers/{wp_id}/annotations", "/api/workpapers/{wp_id}/sheets/{sheet_name}/lock",
                 "/api/workpapers/{wp_id}/d1/ai-generate", CALC):
        await wp_gate.dedicated_wp_gate(_request("POST", path, window=WIN_A), db=db, current_user=ME_USER)


@pytest.mark.asyncio
async def test_write_point_checks_the_requester_recorded_by_the_gate(db, gate_passes):
    """计算后写回（R3.1 ④）：门放行并记下请求人，写回函数在写之前判。"""
    await _lock(db)
    token = wp_gate._WRITE_REQUESTER.set(None)
    try:
        await wp_gate.dedicated_wp_gate(_request("POST", CALC, window=WIN_B), db=db, current_user=ME_USER)
        with pytest.raises(HTTPException) as exc:
            await wp_gate.enforce_edit_lock_at_write_point(db, str(WP))
        assert exc.value.status_code == 423 and "你的另一个窗口" in exc.value.detail
        await wp_gate.enforce_edit_lock_at_write_point(db, str(uuid.uuid4()))  # 别的底稿：不判
        await wp_gate.dedicated_wp_gate(_request("POST", CALC, window=WIN_A), db=db, current_user=ME_USER)
        await wp_gate.enforce_edit_lock_at_write_point(db, WP)  # 持锁窗口：放行
    finally:
        wp_gate._WRITE_REQUESTER.reset(token)


@pytest.mark.asyncio
async def test_write_point_without_gate_does_not_judge(db):
    await _lock(db, holder=OTHER)
    token = wp_gate._WRITE_REQUESTER.set(None)
    try:
        await wp_gate.enforce_edit_lock_at_write_point(db, WP)
    finally:
        wp_gate._WRITE_REQUESTER.reset(token)


@pytest.mark.asyncio
async def test_online_edit_message_for_other_user(db):
    await _lock(db, holder=OTHER, name="李四")
    with pytest.raises(HTTPException) as exc:
        await wp_gate.raise_if_edit_locked(db, ME, WIN_A, WP, purpose="online_edit")
    assert exc.value.status_code == 423
    assert exc.value.detail == "李四 正在编辑这张底稿，当前为只读，不能进入在线编辑。"


@pytest.mark.asyncio
async def test_online_edit_message_for_my_other_window(db):
    await _lock(db)
    with pytest.raises(HTTPException) as exc:
        await wp_gate.raise_if_edit_locked(db, ME, WIN_B, WP, purpose="online_edit")
    assert exc.value.detail.startswith("这张底稿正在你的另一个窗口编辑，本窗口为只读，不能进入在线编辑。")


@pytest.mark.asyncio
async def test_online_edit_entry_rejects_read_only_window(db):
    """在线编辑平台入口（R3.3）：持锁窗口照常，本人另一个窗口 / 别人 423「不能进入在线编辑」。"""
    from app.routers import wp_sync_router as SR

    await _lock(db)
    svc, scope = SimpleNamespace(session=db, user_id=ME), SimpleNamespace(wp_id=WP)
    await SR._enforce_entry_edit_lock(svc, _request("POST", "/sync", window=WIN_A), scope)
    with pytest.raises(HTTPException) as exc:
        await SR._enforce_entry_edit_lock(svc, _request("POST", "/sync", window=WIN_B), scope)
    assert exc.value.status_code == 423 and "不能进入在线编辑" in exc.value.detail
    with pytest.raises(HTTPException):
        await SR._enforce_entry_edit_lock(SimpleNamespace(session=db, user_id=OTHER), _request(
            "POST", "/sync", window=WIN_A), scope)


def test_requester_recorded_in_dependency_reaches_the_endpoint(monkeypatch):
    """`ContextVar` 在依赖里设、在处理函数里读：同一请求可见，请求之间不串（真走一遍 FastAPI）。"""
    from fastapi import APIRouter, Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.deps import get_current_user

    monkeypatch.setattr(wp_gate, "enforce_wp_gate", AsyncMock(return_value=None))
    monkeypatch.setattr(wp_gate, "edit_lock_scope", lambda _path: EditLockScope.ON_APPLY)
    router = APIRouter(dependencies=[Depends(wp_gate.dedicated_wp_gate)])

    @router.post("/x/{wp_id}/calc")
    async def calc(wp_id: str):
        req = wp_gate._WRITE_REQUESTER.get()
        return {"user": str(req.user_id), "instance": req.instance, "wp": str(req.wp_id)}

    @router.post("/x/plain")
    async def plain():
        return {"requester": wp_gate._WRITE_REQUESTER.get() is not None}

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: ME_USER
    client = TestClient(app)
    got = client.post(f"/x/{WP}/calc", headers={"X-Client-Instance": WIN_B}).json()
    assert got == {"user": str(ME), "instance": WIN_B, "wp": str(WP)}
    assert client.post("/x/plain").json() == {"requester": False}
