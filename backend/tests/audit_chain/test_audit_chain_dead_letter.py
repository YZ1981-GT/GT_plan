"""审计队列死信、健康字段、测试隔离与 503 提示（spec enterprise-embedding-rerank-closure R9 / R10）。

- 不合法条目（与写链内核同一套校验）逐条进死信并记原因，同链合法条目照常写入，不再整组滞留隔离区；
- 隔离区里已有的不合法条目在重放时移到死信（同一 Redis 事务，不重复、不丢失）；
- 健康端点报告死信条数，有死信即 degraded；
- 测试进程的审计日志只进 fakeredis（conftest autouse）；
- 审计链 fail-closed 拒绝写入时接口返回 503 与中文原因。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models.audit_log_models  # noqa: E402,F401
from app.models.audit_log_models import AuditLogEntry  # noqa: E402
from app.services.audit_chain.worker import (  # noqa: E402
    DEAD_LETTER_PREFIX,
    QUARANTINE_PREFIX,
    dead_letter_count,
    entry_problem,
    replay_quarantine,
    write_batch,
)

engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all, tables=[
            Base.metadata.tables["audit_log_entries"], Base.metadata.tables["audit_chain_head"],
        ])
    yield


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _entry(project_id: str | None, label: str, *, user_id: str | None = None) -> dict:
    return {
        "user_id": user_id if user_id is not None else str(uuid.uuid4()),
        "action_type": f"test.{label}",
        "object_type": "test",
        "object_id": None,
        "project_id": project_id,
        "payload": {"label": label},
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def _written() -> list[str]:
    async with factory() as db:
        return [r[0] for r in (await db.execute(select(AuditLogEntry.action_type).order_by(AuditLogEntry.ts))).all()]


def test_entry_problem_uses_kernel_checks() -> None:
    assert entry_problem(_entry(None, "ok")) is None
    assert "user_id 必须是 UUID" in entry_problem(_entry(None, "bad", user_id="user-001"))
    assert entry_problem({**_entry(None, "bad"), "ts": "not-a-time"}) is not None
    assert entry_problem({**_entry(None, "bad"), "payload": {"project_id": "x"}}) is not None, "全局链载荷不得带 project_id"
    assert entry_problem("not a dict") == "条目不是对象"


@pytest.mark.asyncio
async def test_write_batch_dead_letters_invalid_and_writes_the_rest(tables, fake_redis) -> None:
    pid = str(uuid.uuid4())
    batch = [_entry(pid, "first"), _entry(pid, "poison", user_id="user-001"), _entry(pid, "second")]
    written = await write_batch(batch, session_factory=factory, redis_client=fake_redis)
    assert written == 2
    assert await _written() == ["test.first", "test.second"]
    assert await fake_redis.llen(f"{QUARANTINE_PREFIX}project:{pid}") == 0
    dead = [json.loads(x) for x in await fake_redis.lrange(f"{DEAD_LETTER_PREFIX}project:{pid}", 0, -1)]
    assert [d["action_type"] for d in dead] == ["test.poison"]
    assert "user_id 必须是 UUID" in dead[0]["_dead_letter_reason"] and dead[0]["_dead_lettered_at"]


@pytest.mark.asyncio
async def test_replay_moves_invalid_quarantined_entries_once(tables, fake_redis) -> None:
    pid = str(uuid.uuid4())
    q_key = f"{QUARANTINE_PREFIX}project:{pid}"
    for item in (_entry(pid, "poison", user_id="user-001"), _entry(pid, "valid")):
        await fake_redis.rpush(q_key, json.dumps(item))

    assert await replay_quarantine(session_factory=factory, redis_client=fake_redis) == 1
    assert await _written() == ["test.valid"]
    assert not await fake_redis.exists(q_key)
    assert await dead_letter_count(fake_redis) == 1
    # 再跑一轮：不会重复写入、也不会重复进死信
    assert await replay_quarantine(session_factory=factory, redis_client=fake_redis) == 0
    assert await dead_letter_count(fake_redis) == 1
    async with factory() as db:
        assert (await db.execute(select(func.count()).select_from(AuditLogEntry))).scalar_one() == 1


@pytest.mark.asyncio
async def test_replay_all_invalid_clears_quarantine(tables, fake_redis) -> None:
    pid = str(uuid.uuid4())
    q_key = f"{QUARANTINE_PREFIX}project:{pid}"
    await fake_redis.rpush(q_key, *(json.dumps(_entry(pid, f"p{i}", user_id="user-001")) for i in range(3)))
    assert await replay_quarantine(session_factory=factory, redis_client=fake_redis) == 0
    assert not await fake_redis.exists(q_key)
    assert await dead_letter_count(fake_redis) == 3


@pytest.mark.asyncio
async def test_health_reports_dead_letters_and_degrades(fake_redis, monkeypatch) -> None:
    from types import SimpleNamespace

    from app.api import health as health_mod

    await fake_redis.rpush(f"{DEAD_LETTER_PREFIX}__global__", "{}")
    health_mod._audit_chain_cache.update(data=None, ts=0.0)
    try:
        with patch("app.services.audit_chain.forks.blocked_chains", AsyncMock(return_value=[])), \
                patch("app.core.redis.redis_client", fake_redis):
            info = await health_mod._query_audit_chain_health(AsyncMock())
        assert info["dead_letter_entries"] == 1 and info["quarantined_entries"] == 0

        ctx = SimpleNamespace(db=AsyncMock(), redis=AsyncMock())
        ctx.redis.ping.return_value = True
        monkeypatch.setattr(health_mod, "_query_migration_status", AsyncMock(return_value={"applied_count": 1, "failures": []}))
        monkeypatch.setattr(health_mod, "_query_schema_drift", AsyncMock(return_value={"count": 0, "critical_count": 0, "items": []}))
        monkeypatch.setattr(health_mod, "_query_audit_chain_health", AsyncMock(return_value={
            "unacknowledged_forks": 0, "quarantined_entries": 0, "dead_letter_entries": 2, "checked_at": "now",
        }))
        monkeypatch.setattr(health_mod, "audit_log_failure_state", lambda: {"failed_count": 0})
        monkeypatch.setattr(health_mod, "reload_status_snapshot", lambda: {})
        monkeypatch.setattr(health_mod, "startup_report_as_dict", lambda: {})
        monkeypatch.setattr(health_mod, "get_last_freeze_report", lambda: {})
        monkeypatch.setattr(health_mod, "_events_replay_info", lambda: {})
        monkeypatch.setattr("app.routers.health_redis._get_redis_health_info", AsyncMock(return_value={}))
        body = json.loads((await health_mod.health_check(ctx)).body)
        assert body["status"] == "degraded" and body["audit_chain"]["dead_letter_entries"] == 2
    finally:
        health_mod._audit_chain_cache.update(data=None, ts=0.0)


@pytest.mark.asyncio
async def test_test_process_never_pushes_audit_entries_to_shared_redis(monkeypatch) -> None:
    """conftest 的 autouse：非 fakeredis 客户端 ⇒ 降级队列；显式换 fakeredis ⇒ 照旧可测队列。

    这里不用真实共享 Redis 做反证：spy 的模块名不是 fakeredis，守卫失效时会收到 ``lpush``，
    所以磁盘变异也不会向开发环境写任何审计测试条目。
    """
    import app.core.redis as core_redis
    from app.services.audit_logger_enhanced import AUDIT_LOG_QUEUE_KEY, AuditLoggerEnhanced

    class SpyRedis:
        def __init__(self):
            self.pushed: list[tuple[str, str]] = []

        async def ping(self):
            return True

        async def lpush(self, key, value):
            self.pushed.append((key, value))
            return 1

    spy = SpyRedis()
    monkeypatch.setattr(core_redis, "redis_client", spy)
    logger = AuditLoggerEnhanced()
    assert await logger._get_redis() is None
    await logger.log_action(user_id=uuid.uuid4(), action="iso.real", object_type="test")
    assert logger._fallback_queue is not None and logger._fallback_queue.qsize() == 1
    assert spy.pushed == [], "测试条目不得推进共享 Redis 形态的客户端"

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(core_redis, "redis_client", fake)
    await logger.log_action(user_id=uuid.uuid4(), action="iso.fake", object_type="test")
    assert await fake.llen(AUDIT_LOG_QUEUE_KEY) == 1


def test_audit_chain_error_returns_503_with_reason() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.middleware.audit_chain_error_handler import audit_chain_error_handler
    from app.services.audit_chain.head import AuditChainBypassed, AuditChainError, AuditChainForked

    app = FastAPI()
    app.add_exception_handler(AuditChainError, audit_chain_error_handler)

    @app.post("/forked")
    async def _forked():
        raise AuditChainForked("链 __global__ 有 10 个未确认链尾，拒绝继续写入")

    @app.post("/bypassed")
    async def _bypassed():
        raise AuditChainBypassed("链 __global__ 的链尾 abc… 已有未登记后继")

    client = TestClient(app)
    forked = client.post("/forked")
    assert forked.status_code == 503
    body = forked.json()
    assert body["error_code"] == "AUDIT_CHAIN_BLOCKED"
    assert "未确认的分叉" in body["message"] and "本次操作未保存" in body["message"]
    assert "10 个未确认链尾" not in body["message"], "链尾数 / 链键只写服务端日志，不回显给普通接口调用方"
    assert "绕过写入" in client.post("/bypassed").json()["message"]


def test_main_app_registers_audit_chain_handler() -> None:
    from app.main import app
    from app.middleware.audit_chain_error_handler import audit_chain_error_handler
    from app.services.audit_chain.head import AuditChainError

    assert app.exception_handlers.get(AuditChainError) is audit_chain_error_handler


@pytest.mark.asyncio
async def test_replay_moves_malformed_raw_entry_to_dead_letter_and_keeps_valid(tables, fake_redis) -> None:
    """坏 JSON 以前会让隔离区整条链永久卡住；现在保留原始值进死信，合法同伴照常写。"""
    pid = str(uuid.uuid4())
    q_key = f"{QUARANTINE_PREFIX}project:{pid}"
    await fake_redis.rpush(q_key, "{not-json", json.dumps(_entry(pid, "valid")))
    assert await replay_quarantine(session_factory=factory, redis_client=fake_redis) == 1
    assert await _written() == ["test.valid"]
    dead = json.loads((await fake_redis.lrange(f"{DEAD_LETTER_PREFIX}project:{pid}", 0, -1))[0])
    assert dead["_dead_letter_raw"] == "{not-json"
    assert dead["_dead_letter_reason"].startswith("JSONDecodeError:")
    assert not await fake_redis.exists(q_key)


@pytest.mark.asyncio
async def test_health_treats_audit_chain_scan_failure_as_unknown_and_degraded(fake_redis, monkeypatch) -> None:
    """不能把扫描失败伪装为 0（旧实现 health 反而报 healthy，审计写入仍会 fail-closed）。"""
    from types import SimpleNamespace

    from app.api import health as health_mod

    health_mod._audit_chain_cache.update(data=None, ts=0.0)
    try:
        with patch("app.services.audit_chain.forks.blocked_chains", AsyncMock(side_effect=RuntimeError("db read failed"))), \
                patch("app.core.redis.redis_client", fake_redis):
            info = await health_mod._query_audit_chain_health(AsyncMock())
        assert info["unacknowledged_forks"] is None

        ctx = SimpleNamespace(db=AsyncMock(), redis=AsyncMock())
        ctx.redis.ping.return_value = True
        monkeypatch.setattr(health_mod, "_query_migration_status", AsyncMock(return_value={"applied_count": 1, "failures": []}))
        monkeypatch.setattr(health_mod, "_query_schema_drift", AsyncMock(return_value={"count": 0, "critical_count": 0, "items": []}))
        monkeypatch.setattr(health_mod, "_query_audit_chain_health", AsyncMock(return_value={
            "unacknowledged_forks": None, "quarantined_entries": 0, "dead_letter_entries": 0, "checked_at": "now",
        }))
        monkeypatch.setattr(health_mod, "audit_log_failure_state", lambda: {"failed_count": 0})
        monkeypatch.setattr(health_mod, "reload_status_snapshot", lambda: {})
        monkeypatch.setattr(health_mod, "startup_report_as_dict", lambda: {})
        monkeypatch.setattr(health_mod, "get_last_freeze_report", lambda: {})
        monkeypatch.setattr(health_mod, "_events_replay_info", lambda: {})
        monkeypatch.setattr("app.routers.health_redis._get_redis_health_info", AsyncMock(return_value={}))
        assert json.loads((await health_mod.health_check(ctx)).body)["status"] == "degraded"
    finally:
        health_mod._audit_chain_cache.update(data=None, ts=0.0)
