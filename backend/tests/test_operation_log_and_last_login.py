# -*- coding: utf-8 -*-
"""操作日志与最后登录时间（spec operation-log-and-last-login，V274）

覆盖：
- 登录成功：last_login_at/ip 更新 + sys_login_log success 行（独立会话）。
- 登录失败（401）/锁定（423）：留痕在异常响应后仍可查（独立会话证据）。
- 登出：logout 行 + user_id 回填；token 解不出时 user_id 为空。
- GET /api/system/operation-logs：仅 admin；类型筛选语义正确（login 系↔login_log，
  业务类↔logs）；分页。
- list_users 返回 last_login 字段。
- 清理函数只删超期行（SQLite 内存库）。

登录留痕经独立会话写共享 factory（async_session）；本文件用 monkeypatch 把
auth_service._record_login_log 与 logout 内部的 async_session 指向测试库的
sessionmaker —— 判据是「留痕行为发生且行归属正确」，连接注入方式不属被测行为。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.base import UserRole
from app.models.core import Department, Log, SysLoginLog, User

IS_PG = app_settings.DATABASE_URL.startswith("postgresql")

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: __import__("app.models.core", fromlist=["Base"]).Base.metadata.create_all(
                c, tables=[
                    User.__table__, Department.__table__, SysLoginLog.__table__, Log.__table__,
                ]
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)

    from app.models.base import Base  # noqa: F401 — 确保模型已注册

    session = maker()
    admin = User(username=f"adm_{uuid.uuid4().hex[:8]}", email=f"adm_{uuid.uuid4().hex[:6]}@t.example",
                 hashed_password=hash_password("Init#2026"), role=UserRole.admin)
    session.add(admin)
    await session.flush()
    await session.commit()

    from app.main import app

    # 共享的 Redis 桩：同一实例贯穿所有请求，失败计数跨请求可见（423 路径依赖它）
    fake_redis = _FakeRedis()

    async def _db():
        yield session

    async def _redis():
        return fake_redis

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _redis
    yield {"app": app, "session": session, "maker": maker, "admin": admin, "redis": fake_redis}
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_redis, None)
    await session.close()
    await engine.dispose()


def _auth(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(u.id)})}"}


class _FakeRedis:
    """auth_service 依赖的最小 Redis 桩（记录调用，不连真 Redis）。"""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = str(v)

    async def delete(self, k):
        self.store.pop(k, None)

    async def exists(self, k):
        return k in self.store

    async def incr(self, k):
        self.store[k] = str(int(self.store.get(k, "0")) + 1)
        return int(self.store[k])

    async def expire(self, k, ttl):
        return True

    async def ttl(self, k):
        return 3600


class _FakeRequest:
    """只带 headers/client 的最小 Request 桩。"""

    def __init__(self, ip="10.1.2.3", ua="pytest-ua"):
        self.headers = {"user-agent": ua, "x-forwarded-for": ip}
        self.client = None


@pytest.fixture(autouse=True)
def _redirect_session_factory(monkeypatch, env):
    """把登录留痕的独立会话工厂与登出内的工厂都指向测试库。"""
    import app.services.auth_service as svc

    monkeypatch.setattr(svc, "async_session", env["maker"], raising=False)
    # _record_login_log / logout 内部是函数内 import async_session ⇒ 还要补模块级补丁：
    import app.core.database as dbmod

    monkeypatch.setattr(dbmod, "async_session", env["maker"], raising=False)


async def _login(env, username: str, password: str, ip: str = "10.1.2.3"):
    c = AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://t")
    resp = await c.post("/api/auth/login", json={"username": username, "password": password},
                        headers={"user-agent": "pytest", "x-forwarded-for": ip})
    await c.aclose()
    return resp


async def test_login_success_updates_user_and_logs(env):
    u = User(username=f"ok_{uuid.uuid4().hex[:6]}", email=f"ok_{uuid.uuid4().hex[:6]}@t.example",
             hashed_password=hash_password("Passw0rd!"), role=UserRole.auditor)
    env["session"].add(u)
    await env["session"].commit()

    resp = await _login(env, u.username, "Passw0rd!")
    assert resp.status_code == 200, resp.text

    fresh = (await env["session"].execute(
        select(User).where(User.id == u.id)
    )).scalar_one()
    assert fresh.last_login_at is not None, "登录成功必须写 last_login_at"
    assert fresh.last_login_ip == "10.1.2.3"

    rows = (await env["session"].execute(
        select(SysLoginLog).where(SysLoginLog.username == u.username)
    )).scalars().all()
    assert len(rows) == 1 and rows[0].result == "success"
    assert rows[0].user_id == u.id and rows[0].ip == "10.1.2.3"
    assert rows[0].user_agent == "pytest"


async def test_failed_login_still_recorded_after_401(env):
    u = User(username=f"bad_{uuid.uuid4().hex[:6]}", email=f"bad_{uuid.uuid4().hex[:6]}@t.example",
             hashed_password=hash_password("Passw0rd!"), role=UserRole.auditor)
    env["session"].add(u)
    await env["session"].commit()

    resp = await _login(env, u.username, "wrong-password")
    assert resp.status_code == 401

    rows = (await env["session"].execute(
        select(SysLoginLog).where(SysLoginLog.username == u.username)
    )).scalars().all()
    assert len(rows) == 1 and rows[0].result == "failed"
    # 账号存在但密码错：user_id 回填
    assert rows[0].user_id == u.id
    # 失败不得更新 last_login
    fresh = (await env["session"].execute(select(User).where(User.id == u.id))).scalar_one()
    assert fresh.last_login_at is None


async def test_unknown_username_failed_login_user_id_null(env):
    resp = await _login(env, f"ghost_{uuid.uuid4().hex[:6]}", "whatever1")
    assert resp.status_code == 401
    rows = (await env["session"].execute(
        select(SysLoginLog).where(SysLoginLog.result == "failed")
    )).scalars().all()
    assert len(rows) == 1 and rows[0].user_id is None


async def test_locked_login_recorded_with_423(env):
    u = User(username=f"lk_{uuid.uuid4().hex[:6]}", email=f"lk_{uuid.uuid4().hex[:6]}@t.example",
             hashed_password=hash_password("Passw0rd!"), role=UserRole.auditor)
    env["session"].add(u)
    await env["session"].commit()
    # 撑满失败计数（依赖注入返回的就是这个共享桩实例）
    env["redis"].store[f"login_fail:{u.username}"] = str(app_settings.LOGIN_MAX_ATTEMPTS)

    c = AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://t")
    resp = await c.post("/api/auth/login", json={"username": u.username, "password": "whatever1"},
                        headers={"user-agent": "pytest"})
    await c.aclose()
    assert resp.status_code == 423
    rows = (await env["session"].execute(
        select(SysLoginLog).where(SysLoginLog.username == u.username)
    )).scalars().all()
    assert len(rows) == 1 and rows[0].result == "locked"


async def test_logout_records_with_user_id(env):
    u = User(username=f"lo_{uuid.uuid4().hex[:6]}", email=f"lo_{uuid.uuid4().hex[:6]}@t.example",
             hashed_password=hash_password("Passw0rd!"), role=UserRole.auditor)
    env["session"].add(u)
    await env["session"].commit()
    rt = create_refresh_token({"sub": str(u.id)})

    c = AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://t")
    resp = await c.post("/api/auth/logout", json={"refresh_token": rt})
    await c.aclose()
    assert resp.status_code == 200

    rows = (await env["session"].execute(
        select(SysLoginLog).where(SysLoginLog.result == "logout")
    )).scalars().all()
    assert len(rows) == 1 and rows[0].user_id == u.id and rows[0].username == u.username


async def test_logout_with_invalid_token_user_id_null(env):
    c = AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://t")
    resp = await c.post("/api/auth/logout", json={"refresh_token": "not-a-jwt"})
    await c.aclose()
    assert resp.status_code == 200
    rows = (await env["session"].execute(
        select(SysLoginLog).where(SysLoginLog.result == "logout")
    )).scalars().all()
    assert len(rows) == 1 and rows[0].user_id is None


# ---------------------------------------------------------------------------
# 查询端点
# ---------------------------------------------------------------------------

async def _seed_mixed_logs(env, admin: User):
    """1 条登录成功 + 1 条登录失败 + 1 条业务 create + 1 条业务 delete。"""
    session = env["session"]
    session.add(SysLoginLog(username="mixin", result="success", user_id=admin.id,
                            ip="1.1.1.1", user_agent=None))
    session.add(SysLoginLog(username="mixin", result="failed", user_id=None, ip="2.2.2.2"))
    session.add(Log(user_id=admin.id, action_type="create", object_type="project",
                    object_id=uuid.uuid4(), ip_address="3.3.3.3"))
    session.add(Log(user_id=admin.id, action_type="delete", object_type="adjustment",
                    object_id=None, ip_address="4.4.4.4"))
    await session.commit()


async def test_operation_logs_requires_admin(env):
    u = User(username=f"au_{uuid.uuid4().hex[:6]}", email=f"au_{uuid.uuid4().hex[:6]}@t.example",
             hashed_password=hash_password("Passw0rd!"), role=UserRole.auditor)
    env["session"].add(u)
    await env["session"].commit()
    async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://t") as c:
        assert (await c.get("/api/system/operation-logs")).status_code == 401
        assert (await c.get("/api/system/operation-logs", headers=_auth(u))).status_code == 403


async def test_operation_logs_admin_and_filters(env):
    admin = env["admin"]
    await _seed_mixed_logs(env, admin)
    async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://t") as c:
        r = await c.get("/api/system/operation-logs", headers=_auth(admin))
        assert r.status_code == 200, r.text
        body = r.json().get("data", r.json())
        assert body["total"] >= 4
        types = {row["type"] for row in body["items"]}
        assert {"success", "failed", "create", "delete"} <= types

        # type=failed 只出登录失败
        r = await c.get("/api/system/operation-logs", params={"type": "failed"}, headers=_auth(admin))
        items = r.json().get("data", r.json())["items"]
        assert items and all(i["type"] == "failed" for i in items)

        # type=create 只出业务 create
        r = await c.get("/api/system/operation-logs", params={"type": "create"}, headers=_auth(admin))
        items = r.json().get("data", r.json())["items"]
        assert items and all(i["type"] == "create" for i in items)

        # 非法 type 422
        assert (await c.get("/api/system/operation-logs",
                            params={"type": "evil"}, headers=_auth(admin))).status_code == 422

        # 分页
        r = await c.get("/api/system/operation-logs",
                        params={"page": 1, "page_size": 2}, headers=_auth(admin))
        assert len(r.json().get("data", r.json())["items"]) == 2


async def test_list_users_returns_last_login(env):
    admin = env["admin"]
    admin.last_login_at = datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    admin.last_login_ip = "9.9.9.9"
    await env["session"].commit()
    async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://t") as c:
        r = await c.get("/api/users/", headers=_auth(admin))
        assert r.status_code == 200
        rows = r.json().get("data", r.json())
        me = next(row for row in rows if row["id"] == str(admin.id))
        assert me["last_login_at"] is not None and me["last_login_ip"] == "9.9.9.9"


# ---------------------------------------------------------------------------
# 清理函数（纯函数层，直接调 worker 的 _cleanup_table）
# ---------------------------------------------------------------------------

async def test_cleanup_only_deletes_expired(env, monkeypatch):
    import app.workers.log_retention_worker as worker

    old_ts = datetime.now(timezone.utc) - timedelta(days=400)
    session = env["session"]
    old_log = Log(user_id=None, action_type="update", object_type="x", created_at=old_ts)
    new_log = Log(user_id=None, action_type="update", object_type="x")
    old_ll = SysLoginLog(username="old", result="failed", ip=None)
    new_ll = SysLoginLog(username="fresh", result="success", ip=None)
    session.add_all([old_log, new_log, old_ll, new_ll])
    await session.flush()
    # 手动把 login_log 旧行时间拨回 400 天前
    await session.execute(sa.update(SysLoginLog).where(SysLoginLog.id == old_ll.id)
                          .values(ts=old_ts))
    await session.commit()

    # 把 worker 的会话工厂指到测试库
    monkeypatch.setattr(worker, "db_execute", None, raising=False)

    from app.core.database import async_session as real_factory  # noqa: F401

    async def _exec(stmt, commit=False):
        async with env["maker"]() as s:
            res = await s.execute(stmt)
            if commit:
                await s.commit()
            is_select = isinstance(stmt, sa.Select)
            return res.fetchall() if is_select else []

    monkeypatch.setattr(worker, "db_execute", _exec)

    n1 = await worker._cleanup_table(Log, Log.created_at, 365)
    n2 = await worker._cleanup_table(SysLoginLog, SysLoginLog.ts, 180)
    assert n1 == 1 and n2 == 1, "只应各删 1 条超期行"

    remain_logs = (await env["session"].execute(sa.select(Log))).scalars().all()
    remain_ll = (await env["session"].execute(sa.select(SysLoginLog))).scalars().all()
    assert len(remain_logs) == 1 and len(remain_ll) == 1
