"""审计日志 worker 逐链事务 + 隔离区测试

ADR-ALC-06: 每条链一个独立事务，链失败进隔离区，重放可出列。
使用 SQLite 内存库 + fakeredis。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models.audit_log_models  # noqa: F401
import app.models.core  # noqa: F401

from app.models.audit_log_models import AuditLogEntry
from app.services.audit_chain.canonical import GENESIS_HASH
from app.workers.audit_log_writer_worker import (
    QUARANTINE_PREFIX,
    _replay_quarantine,
    _write_batch,
)

TEST_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_URL, echo=False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables = [
            Base.metadata.tables["audit_log_entries"],
            Base.metadata.tables["audit_chain_head"],
        ]
        if "users" in Base.metadata.tables:
            tables.append(Base.metadata.tables["users"])
        await conn.run_sync(Base.metadata.create_all, tables=tables)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _make_entry(project_id: str, label: str) -> dict:
    return {
        "user_id": str(uuid.uuid4()),
        "action_type": f"test.{label}",
        "object_type": "test",
        "object_id": str(uuid.uuid4()),
        "project_id": project_id,
        "payload": {"project_id": project_id, "label": label},
        "ts": datetime.now(timezone.utc).isoformat(),
    }


class TestWorkerPerChainTransaction:
    """每条链一个独立事务：一条链失败不影响另一条。"""

    @pytest.mark.asyncio
    async def test_one_chain_fails_other_committed(self, db, fake_redis):
        """两条链其一注入失败 → 另一条已提交、失败条目在隔离区。"""
        pid_ok = str(uuid.uuid4())
        pid_fail = str(uuid.uuid4())

        entries = [
            _make_entry(pid_ok, "ok"),
            _make_entry(pid_fail, "fail"),
        ]

        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async def mock_factory():
            return session_factory

        original_append_entry = None

        # 用 monkeypatch 让特定链抛异常
        from app.services.audit_chain import head as head_mod
        real_append = head_mod.append_entry

        call_count = {"fail_chain": 0}
        fail_chain_key = f"project:{pid_fail}"

        async def patched_append(db, key, **kwargs):
            if key == fail_chain_key:
                call_count["fail_chain"] += 1
                raise RuntimeError("injected failure for test")
            return await real_append(db, key, **kwargs)

        with patch(
            "app.workers.audit_log_writer_worker._get_session_factory",
            mock_factory,
        ), patch(
            "app.services.audit_chain.head.append_entry",
            patched_append,
        ), patch(
            "app.core.redis.redis_client",
            fake_redis,
        ):
            written = await _write_batch(entries)

        # 成功链应该写入
        assert written >= 1

        # 失败链条目应该在隔离区
        q_key = f"{QUARANTINE_PREFIX}{fail_chain_key}"
        q_len = await fake_redis.llen(q_key)
        assert q_len >= 1

    @pytest.mark.asyncio
    async def test_quarantine_replay_success(self, db, fake_redis):
        """隔离区重放：恢复后条目出列。"""
        pid = str(uuid.uuid4())
        chain_key = f"project:{pid}"
        q_key = f"{QUARANTINE_PREFIX}{chain_key}"

        # 手动放一条进隔离区
        entry = _make_entry(pid, "quarantined")
        await fake_redis.lpush(q_key, json.dumps(entry, default=str))

        assert await fake_redis.llen(q_key) == 1

        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async def mock_factory():
            return session_factory

        with patch(
            "app.workers.audit_log_writer_worker._get_session_factory",
            mock_factory,
        ), patch(
            "app.core.redis.redis_client",
            fake_redis,
        ):
            replayed = await _replay_quarantine()

        assert replayed == 1
        assert await fake_redis.llen(q_key) == 0


class TestHealthQuarantineCount:
    """健康端点返回隔离区条目计数。"""

    @pytest.mark.asyncio
    async def test_quarantine_count_in_health(self, fake_redis):
        """隔离区有条目时 _query_audit_chain_health 返回 quarantined_entries > 0。"""
        q_key = f"{QUARANTINE_PREFIX}project:test123"
        await fake_redis.lpush(q_key, '{"test": true}')
        await fake_redis.lpush(q_key, '{"test": true}')

        from unittest.mock import AsyncMock
        from app.api.health import _query_audit_chain_health, _audit_chain_cache

        # 清除缓存，确保真正执行查询
        _audit_chain_cache["data"] = None
        _audit_chain_cache["ts"] = 0.0

        # _query_audit_chain_health 内部 lazy import redis_client 和 scan_forks
        # patch 源模块让 lazy import 拿到 fake 实例
        mock_db = AsyncMock()
        with patch(
            "app.services.audit_chain.forks.scan_forks",
            AsyncMock(return_value=[]),
        ), patch(
            "app.core.redis.redis_client",
            fake_redis,
        ):
            result = await _query_audit_chain_health(mock_db)

        assert result["quarantined_entries"] == 2
        assert result["unacknowledged_forks"] == 0

        # 清除缓存避免污染其他测试
        _audit_chain_cache["data"] = None
        _audit_chain_cache["ts"] = 0.0
