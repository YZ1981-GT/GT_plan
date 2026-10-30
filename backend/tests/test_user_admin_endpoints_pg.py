# -*- coding: utf-8 -*-
"""用户接口的安全与功能（spec procedure-chain-followup-closure R1 / 任务 1.1、1.2、1.4）。

真实 PostgreSQL + 真实 app，外层事务（``create_savepoint``，路由里的 commit 只动保存点），用例结束回滚。
身份用真实 access token、走真实 ``get_current_user``（只替换 ``get_db``）——「停用后下一次请求即 401」才测得到。

- ``GET /api/users/`` 原先不要求登录；现须登录，并回 ``is_active``。
- ``PUT /api/users/{id}`` 原先不存在（用户管理页「编辑」恒 405）；仅 admin，不能停用 / 降级自己，至少保留一个启用的管理员。
- 锁定账户原先一调即 NameError、任何登录用户都能调；安全查询只要求登录 —— 现全部仅 admin。
- 私人库、改语言原先不校验本人（私人库甚至不鉴权）；私人库文件名可用 ``..`` 逃出本人目录。
"""
from __future__ import annotations

import types
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.models.base import UserRole
from app.models.core import User
from app.schemas.auth import UserUpdate
from app.services import auth_service

IS_PG = app_settings.DATABASE_URL.startswith("postgresql")
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")]


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    s = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield s
    finally:
        try:
            from app.main import app  # 导入失败（如别处语法错误）也必须回滚，否则留下未结束的事务挡住后面的用例

            app.dependency_overrides.pop(get_db, None)
        finally:
            await s.close()
            await trans.rollback()
            await conn.close()
            await engine.dispose()


@pytest.fixture(autouse=True)
def _no_side_writes(monkeypatch):
    """操作日志 / 安全审计都走独立连接，会在真库留下引用回滚数据的行 ⇒ 换成空操作。

    🔴 ``audit_logger_enhanced`` 写的是哈希链审计表 ``audit_log_entries``：漏掉它时每跑一次本文件就往真库链上
    追加几条指向已回滚用户的记录（2026-10-25 已累计 37 条；删掉会断链，留给人定）。要断言留痕的用例自己再替换。
    """
    from app.middleware import audit_log
    from app.services.audit_logger_enhanced import audit_logger

    async def _log(*_a, **_kw):
        return None

    monkeypatch.setattr(audit_log, "_write_log", _log)
    # 单例的方法在类上替换：在实例上替换的话，撤销时会把方法写成实例属性留在单例上
    monkeypatch.setattr(type(audit_logger), "log_action", _log)


async def _user(s, role: str, *, active: bool = True, password: str = "Init#2026") -> User:
    tag = uuid.uuid4().hex[:10]
    u = User(username=f"uadm_{tag}", email=f"uadm_{tag}@t.example", hashed_password=hash_password(password),
             role=UserRole(role), is_active=active)
    s.add(u)
    await s.flush()
    return u


def _auth(user: User | None) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"} if user else {}


def _client(s: AsyncSession) -> AsyncClient:
    from app.main import app

    async def _db():
        yield s

    app.dependency_overrides[get_db] = _db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _data(resp):
    body = resp.json()
    return body.get("data", body) if isinstance(body, dict) and "data" in body else body


async def _reload(s, user_id) -> User:
    return (await s.execute(sa.select(User).where(User.id == user_id).execution_options(populate_existing=True))).scalar_one()


# ---------------------------------------------------------------------------
# 用户列表 / 修改用户
# ---------------------------------------------------------------------------
async def test_list_users_requires_login_and_returns_is_active(db):
    auditor = await _user(db, "auditor")
    off = await _user(db, "auditor", active=False)
    async with _client(db) as c:
        assert (await c.get("/api/users/")).status_code == 401
        r = await c.get("/api/users/", headers=_auth(auditor))
    assert r.status_code == 200, r.text
    rows = {u["id"]: u for u in _data(r)}
    assert rows[str(off.id)]["is_active"] is False and rows[str(auditor.id)]["is_active"] is True
    assert rows[str(auditor.id)]["role"] == "auditor"


async def test_update_user_is_admin_only_and_edits_fields(db):
    admin = await _user(db, "admin")
    auditor = await _user(db, "auditor")
    target = await _user(db, "auditor")
    url = f"/api/users/{target.id}"
    async with _client(db) as c:
        assert (await c.put(url, json={"role": "manager"})).status_code == 401
        assert (await c.put(url, json={"role": "manager"}, headers=_auth(auditor))).status_code == 403
        r = await c.put(url, json={"role": "manager", "email": f"new_{target.email}", "office_code": "CQ"},
                        headers=_auth(admin))
        assert r.status_code == 200, r.text
        assert (_data(r)["role"], _data(r)["office_code"]) == ("manager", "CQ")
        # 编辑表单不填密码（空串）⇒ 不改；改密码长度 8~64；用户名不可改（多余字段 422）
        assert (await c.put(url, json={"password": ""}, headers=_auth(admin))).status_code == 200
        assert verify_password("Init#2026", (await _reload(db, target.id)).hashed_password)
        assert (await c.put(url, json={"password": "1234567"}, headers=_auth(admin))).status_code == 422
        # V149 权限中心：用户名可改（唯一性由 service 校验）
        assert (await c.put(url, json={"username": "renamed"}, headers=_auth(admin))).status_code == 200
        assert (await _reload(db, target.id)).username == "renamed"
        assert (await c.put(url, json={"password": "Rst#2026"}, headers=_auth(admin))).status_code == 200  # 恰 8 位
        # 邮箱全表唯一
        assert (await c.put(url, json={"email": admin.email}, headers=_auth(admin))).status_code == 409
        assert (await c.put(f"/api/users/{uuid.uuid4()}", json={"role": "auditor"},
                            headers=_auth(admin))).status_code == 404
    fresh = await _reload(db, target.id)
    assert verify_password("Rst#2026", fresh.hashed_password) and fresh.role == UserRole.manager


async def test_deactivated_user_is_rejected_on_next_request(db):
    admin = await _user(db, "admin")
    target = await _user(db, "auditor")
    async with _client(db) as c:
        assert (await c.get("/api/users/me", headers=_auth(target))).status_code == 200
        r = await c.put(f"/api/users/{target.id}", json={"is_active": False}, headers=_auth(admin))
        assert r.status_code == 200 and _data(r)["is_active"] is False
        assert (await c.get("/api/users/me", headers=_auth(target))).status_code == 401, "停用后旧令牌下一次请求即 401"
        assert (await c.put(f"/api/users/{target.id}", json={"is_active": True},
                            headers=_auth(admin))).status_code == 200
        assert (await c.get("/api/users/me", headers=_auth(target))).status_code == 200


async def test_admin_cannot_deactivate_or_demote_self(db):
    admin = await _user(db, "admin")
    url = f"/api/users/{admin.id}"
    async with _client(db) as c:
        for body in ({"is_active": False}, {"role": "manager"}):
            r = await c.put(url, json=body, headers=_auth(admin))
            assert r.status_code == 409, (body, r.text)
        assert (await c.put(url, json={"office_code": "BJ"}, headers=_auth(admin))).status_code == 200
    assert (await _reload(db, admin.id)).is_active is True


async def test_last_active_admin_is_kept(db):
    """管理员互相停用的并发场景落到这条规则：锁住全部启用中的管理员后计数，改完必须还剩至少一个。"""
    await db.execute(sa.update(User).where(User.role == UserRole.admin).values(is_active=False))  # 外层事务，回滚复原
    last = await _user(db, "admin")
    someone = uuid.uuid4()  # 服务层不看操作人角色（路由已挡）
    for data in (UserUpdate(is_active=False), UserUpdate(role=UserRole.auditor)):
        with pytest.raises(Exception) as ei:
            await auth_service.update_user(db, actor_id=someone, user_id=last.id, data=data)
        assert getattr(ei.value, "status_code", None) == 409 and "至少要保留一个启用的管理员" in str(ei.value.detail)
    await _user(db, "admin")
    out = await auth_service.update_user(db, actor_id=someone, user_id=last.id, data=UserUpdate(is_active=False))
    assert out.is_active is False


# ---------------------------------------------------------------------------
# 安全接口
# ---------------------------------------------------------------------------
async def test_lock_account_is_admin_only_and_deactivates(db):
    admin = await _user(db, "admin")
    auditor = await _user(db, "auditor")
    target = await _user(db, "auditor")
    url = "/api/security/lock-account"
    async with _client(db) as c:
        assert (await c.post(url, params={"username": target.username}, headers=_auth(auditor))).status_code == 403
        r = await c.post(url, params={"username": target.username}, headers=_auth(admin))
        assert r.status_code == 200, r.text
        assert (await c.get("/api/users/me", headers=_auth(target))).status_code == 401
        assert (await c.post(url, params={"username": admin.username}, headers=_auth(admin))).status_code == 409
        assert (await c.post(url, params={"username": "no_such_user_x"}, headers=_auth(admin))).status_code == 404
    assert (await _reload(db, target.id)).is_active is False


@pytest.mark.parametrize("path", ["/api/security/login-attempts", "/api/security/sessions", "/api/audit-logs/export"])
async def test_security_queries_are_admin_only(db, path):
    admin = await _user(db, "admin")
    auditor = await _user(db, "auditor")
    async with _client(db) as c:
        assert (await c.get(path, headers=_auth(auditor))).status_code == 403
        assert (await c.get(path, headers=_auth(admin))).status_code == 200


# ---------------------------------------------------------------------------
# 私人库 / 改语言：本人或 admin
# ---------------------------------------------------------------------------
async def test_private_storage_is_self_or_admin_and_names_cannot_escape(db, tmp_path, monkeypatch):
    from app.services import private_storage_service

    monkeypatch.setattr(private_storage_service, "STORAGE_ROOT", tmp_path)
    owner = await _user(db, "auditor")
    other = await _user(db, "auditor")
    admin = await _user(db, "admin")
    base = f"/api/users/{owner.id}/private-storage"
    async with _client(db) as c:
        assert (await c.get(base)).status_code == 401
        assert (await c.get(base, headers=_auth(other))).status_code == 403
        assert (await c.get(f"{base}/quota", headers=_auth(other))).status_code == 403
        up = await c.post(f"{base}/upload", files={"file": ("底稿笔记.txt", b"abc")}, headers=_auth(owner))
        assert up.status_code == 200, up.text
        assert (await c.post(f"{base}/upload", files={"file": ("x.txt", b"x")}, headers=_auth(other))).status_code == 403
        assert [f["name"] for f in _data(await c.get(base, headers=_auth(admin)))] == ["底稿笔记.txt"]
        # 文件名带路径 ⇒ 400，私人库目录外没有新文件
        bad = await c.post(f"{base}/upload", files={"file": ("..\\..\\escape.txt", b"x")}, headers=_auth(owner))
        assert bad.status_code == 400, bad.text
        assert (await c.delete(f"{base}/..%5C..%5Cescape.txt", headers=_auth(owner))).status_code == 400
        assert (await c.delete(f"{base}/底稿笔记.txt", headers=_auth(other))).status_code == 403
        assert (await c.delete(f"{base}/底稿笔记.txt", headers=_auth(owner))).status_code == 200
    assert not list(tmp_path.rglob("escape.txt"))


async def test_set_language_is_self_or_admin(db):
    owner = await _user(db, "auditor")
    other = await _user(db, "auditor")
    admin = await _user(db, "admin")
    url = f"/api/users/{owner.id}/language"
    async with _client(db) as c:
        assert (await c.put(url, json={"language": "en-US"}, headers=_auth(other))).status_code == 403
        assert (await c.put(url, json={"language": "en-US"}, headers=_auth(owner))).status_code == 200
        assert (await c.put(url, json={"language": "zh-CN"}, headers=_auth(admin))).status_code == 200
    assert (await _reload(db, owner.id)).language == "zh-CN"


class _MemoryRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.blacklist: set[str] = set()

    async def exists(self, key: str) -> bool:
        return key in self.values or key in self.blacklist

    async def ttl(self, _key: str) -> int:
        return 3600

    async def set(self, key: str, value, **_kwargs):
        self.values[key] = str(value)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


async def test_deactivated_user_cannot_refresh_existing_token(db):
    target = await _user(db, "auditor")
    token = create_refresh_token({"sub": str(target.id)})
    redis = _MemoryRedis()
    redis.values[auth_service._refresh_token_key(token)] = str(target.id)
    target.is_active = False
    await db.flush()

    with pytest.raises(Exception) as ei:
        await auth_service.refresh(token, redis, db)
    assert getattr(ei.value, "status_code", None) == 401
    assert auth_service._refresh_token_key(token) in redis.values, "停用用户的旧 refresh token 不应被轮换消费"


async def test_password_and_active_state_changes_are_audited(db, monkeypatch):
    admin = await _user(db, "admin")
    target = await _user(db, "auditor")
    from app.services.audit_logger_enhanced import audit_logger

    calls: list[dict] = []

    async def _capture(_self, **payload):
        calls.append(payload)
        return payload

    monkeypatch.setattr(type(audit_logger), "log_action", _capture)
    await auth_service.update_user(
        db,
        actor_id=admin.id,
        user_id=target.id,
        data=UserUpdate(password="Reset#2026", is_active=False),
    )

    assert len(calls) == 1
    assert calls[0]["action"] == "user.security_changed"
    assert calls[0]["object_type"] == "user"
    assert calls[0]["object_id"] == target.id
    assert calls[0]["details"]["password_reset"] is True
    assert calls[0]["details"]["is_active"] == {"from": True, "to": False}
