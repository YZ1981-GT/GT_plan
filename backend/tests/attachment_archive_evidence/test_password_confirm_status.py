"""二次密码确认：密码错误不再返回 401（spec attachment-archive-and-a-class-evidence 需求 4.1，ADR-AE-07）。

回归背景：密码错误返回 401 ⇒ 前端拦截器当会话过期：刷新令牌后重发（同一次输错记两次失败），仍 401 即登出跳登录页；
二次确认对话框里的「剩余次数」分支从未被走到。
"""
from __future__ import annotations

import pytest_asyncio

from app.core.security import hash_password
from app.routers.password_confirm import MAX_ATTEMPTS
from app.routers.password_confirm import router as password_router
from tests.attachment_security_baseline._world import sqlite_attachment_world

URL = "/api/auth/verify-password"


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


async def _user(world):
    user = await world.user()
    user.hashed_password = hash_password("Right#123")
    await world.db.flush()
    return user


def _detail(resp):
    body = resp.json()
    return body.get("detail", body)


async def test_wrong_password_is_403_with_remaining_count(world):
    user = await _user(world)
    async with world.client(password_router, user=user) as c:
        first = await c.post(URL, json={"password": "wrong"})
        second = await c.post(URL, json={"password": "wrong"})
    assert first.status_code == 403
    assert _detail(first)["error_code"] == "PASSWORD_INVALID"
    assert _detail(first)["message"] == "密码错误"
    # 每次请求只记一次失败（401 时拦截器刷新重发会记两次）
    assert (_detail(first)["attempts_remaining"], _detail(second)["attempts_remaining"]) == (
        MAX_ATTEMPTS - 1, MAX_ATTEMPTS - 2)
    assert int(await world.redis.get(f"confirm_fail:{user.id}")) == 2


async def test_lock_after_max_attempts_is_423(world):
    user = await _user(world)
    async with world.client(password_router, user=user) as c:
        for _ in range(MAX_ATTEMPTS):
            assert (await c.post(URL, json={"password": "wrong"})).status_code == 403
        locked = await c.post(URL, json={"password": "Right#123"})
    assert locked.status_code == 423
    assert "locked_until" in _detail(locked)


async def test_correct_password_returns_one_time_token(world):
    user = await _user(world)
    async with world.client(password_router, user=user) as c:
        await c.post(URL, json={"password": "wrong"})
        ok = await c.post(URL, json={"password": "Right#123"})
    assert ok.status_code == 200
    token = ok.json()["confirmation_token"]
    assert await world.redis.get(f"confirm:{token}") in (str(user.id), str(user.id).encode())
    assert await world.redis.get(f"confirm_fail:{user.id}") is None  # 成功清零失败计数
