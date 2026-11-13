"""迁移未执行时明确报错（spec voucher-workflow-linkage-lineage-closure R2）

- 异常链上任一环是 PG「表 / 列不存在」（42P01 / 42703）才算结构缺失：直接、经 ``orig``、经 ``__cause__`` 都认；
- 有未执行迁移 ⇒ 503 MIGRATION_PENDING，消息写明两边版本与个数；没有 ⇒ 照旧 500；判定读库失败 ⇒ 500；
- 判定结果缓存 60 秒，期内不重复查库。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import migration_pending as mp
from app.middleware.error_handler import generic_exception_handler

pytestmark = pytest.mark.asyncio


class _PgError(Exception):
    def __init__(self, sqlstate: str):
        super().__init__(f"pg {sqlstate}")
        self.sqlstate = sqlstate


class _Wrapped(Exception):
    """SQLAlchemy DBAPIError 的形状：原始异常在 ``orig``。"""

    def __init__(self, orig):
        super().__init__("wrapped")
        self.orig = orig


@pytest.fixture(autouse=True)
def _reset():
    mp.reset_cache_for_test()
    yield
    mp.reset_cache_for_test()


def _pending(n: int = 17) -> mp.PendingMigrations:
    return mp.PendingMigrations(db_max="234", disk_max="251", pending_count=n)


async def test_missing_schema_detection_walks_the_chain():
    assert mp.is_missing_schema_error(_PgError("42P01"))
    assert mp.is_missing_schema_error(_Wrapped(_PgError("42703")))
    try:
        try:
            raise _PgError("42P01")
        except _PgError as inner:
            raise RuntimeError("业务层包了一层") from inner
    except RuntimeError as outer:
        assert mp.is_missing_schema_error(outer)
    assert not mp.is_missing_schema_error(_PgError("23505"))  # 唯一约束冲突不是结构缺失
    assert not mp.is_missing_schema_error(ValueError("x"))
    loop = _Wrapped(None)
    loop.orig = loop  # 自引用不死循环
    assert not mp.is_missing_schema_error(loop)


async def test_pending_info_is_cached_for_60_seconds(monkeypatch):
    calls = []

    async def _inspect():
        calls.append(1)
        return _pending()

    monkeypatch.setattr(mp, "_inspect", _inspect)
    now = [1000.0]
    assert (await mp.pending_migration_info(clock=lambda: now[0])) == _pending()
    now[0] += 59
    await mp.pending_migration_info(clock=lambda: now[0])
    assert len(calls) == 1
    now[0] += 2
    await mp.pending_migration_info(clock=lambda: now[0])
    assert len(calls) == 2


async def test_inspection_failure_returns_none(monkeypatch):
    async def _boom():
        raise RuntimeError("schema_version 读不了")

    monkeypatch.setattr(mp, "_inspect", _boom)
    assert await mp.pending_migration_info() is None


async def test_message_names_versions_and_count():
    text = _pending(3).message()
    assert "V251" in text and "V234" in text and "3 个迁移未执行" in text and "重启后端" in text
    assert "库里还没有登记任何迁移" in mp.PendingMigrations(db_max=None, disk_max="001", pending_count=1).message()


def _app(exc: Exception) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(Exception, generic_exception_handler)

    @app.get("/boom")
    async def _boom():
        raise exc

    return app


async def _get(app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t") as c:
        return await c.get("/boom")


async def test_handler_returns_503_when_migrations_pending(monkeypatch):
    async def _info():
        return _pending()

    monkeypatch.setattr(mp, "pending_migration_info", _info)
    resp = await _get(_app(_Wrapped(_PgError("42P01"))))
    assert resp.status_code == 503
    body = resp.json()["message"]
    assert body["error_code"] == "MIGRATION_PENDING"
    assert (body["db_version"], body["code_version"], body["pending_count"]) == ("234", "251", 17)


async def test_handler_keeps_500_without_pending_or_for_other_errors(monkeypatch):
    seen = []

    async def _none():
        seen.append(1)
        return None

    monkeypatch.setattr(mp, "pending_migration_info", _none)
    resp = await _get(_app(_Wrapped(_PgError("42703"))))
    assert resp.status_code == 500 and resp.json()["message"] == "服务器内部错误"
    assert seen == [1]
    resp = await _get(_app(ValueError("代码缺陷")))
    assert resp.status_code == 500
    assert seen == [1], "非结构缺失的异常不该去查迁移"
