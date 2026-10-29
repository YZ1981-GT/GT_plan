"""审计链分叉扫描与确认 — PG 一次性库测试

FEAT-002: scan_forks / append_fork_ack / health endpoint audit_chain 字段。
使用一次性 PG 库（gt_s10_ 前缀），PG 不可用时 skip。
"""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.models.audit_log_models import AuditLogEntry
from app.services.audit_chain.canonical import GENESIS_HASH, hash_v1


# ── PG 可用性检测 ────────────────────────────────────────────────


def _pg_available() -> bool:
    try:
        from app.core.config import settings
        return settings.DATABASE_URL.startswith("postgresql")
    except Exception:
        return False


def _base_url() -> str:
    from app.core.config import settings
    head, _ = settings.DATABASE_URL.rsplit("/", 1)
    return head


def _connect_args() -> dict:
    from app.core.config import settings
    return {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}


# ── 一次性 PG 库 ────────────────────────────────────────────────


@asynccontextmanager
async def _throwaway_engine():
    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"gt_s10_{uuid.uuid4().hex[:12]}"

    admin = create_async_engine(
        admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
    )
    async with admin.connect() as c:
        await c.exec_driver_sql(f'CREATE DATABASE "{tmp_db}"')
    await admin.dispose()

    eng = create_async_engine(head + "/" + tmp_db, poolclass=NullPool, connect_args=ca)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(AuditLogEntry.__table__.create, checkfirst=True)
        yield eng
    finally:
        await eng.dispose()
        admin = create_async_engine(
            admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
        )
        async with admin.connect() as c:
            await c.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{tmp_db}' AND pid<>pg_backend_pid()"
            )
            await c.exec_driver_sql(f'DROP DATABASE IF EXISTS "{tmp_db}"')
        await admin.dispose()


# ── 辅助：构造分叉链 ─────────────────────────────────────────────


def _make_entry(
    action_type: str = "test.action",
    prev_hash: str = GENESIS_HASH,
    payload: dict | None = None,
    user_id: uuid.UUID | None = None,
) -> AuditLogEntry:
    """构造 AuditLogEntry 实例，entry_hash 用 hash_v1。"""
    eid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    ts_str = now.isoformat(timespec="microseconds")
    pl = payload or {}
    pj = json.dumps(pl, sort_keys=True, ensure_ascii=False, default=str)
    eh = hash_v1(ts_str, str(user_id or ""), action_type, "", pj, prev_hash)
    return AuditLogEntry(
        id=eid, ts=now, user_id=user_id,
        action_type=action_type, object_type="test",
        payload=pl, prev_hash=prev_hash, entry_hash=eh,
    )


async def _insert_fork_chain(session: AsyncSession) -> dict:
    """插入 genesis→A, A→B, A→C 的分叉链。返回 {a, b, c} 条目。"""
    a = _make_entry("genesis.action", GENESIS_HASH)
    session.add(a)
    await session.flush()

    b = _make_entry("branch.b", a.entry_hash)
    c = _make_entry("branch.c", a.entry_hash)
    session.add_all([b, c])
    await session.flush()
    return {"a": a, "b": b, "c": c}


# ── 测试用例 ─────────────────────────────────────────────────────

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not _pg_available(), reason="PG 不可用"),
]


@pytest.mark.asyncio
async def test_scan_forks_detects_fork():
    """scan_forks 能检测到 A→B, A→C 分叉。"""
    from app.services.audit_chain.forks import scan_forks

    async with _throwaway_engine() as eng:
        async_session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            await _insert_fork_chain(session)
            await session.commit()

        async with async_session() as session:
            forks = await scan_forks(session)
            assert len(forks) >= 1
            fork = forks[0]
            assert len(fork["survivors"]) > 1, "应有多个存活后继"


@pytest.mark.asyncio
async def test_fork_ack_rejects_wrong_set():
    """append_fork_ack 传错误的 dead_entry_id → raises ValueError。"""
    from app.services.audit_chain.forks import append_fork_ack

    async with _throwaway_engine() as eng:
        async_session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            chain = await _insert_fork_chain(session)
            await session.commit()

        async with async_session() as session:
            wrong_dead = uuid.uuid4()  # 不是 C
            with pytest.raises(ValueError, match="未确认链尾不匹配"):
                await append_fork_ack(
                    session,
                    chain_key="__global__",
                    survivor_entry_id=chain["b"].id,
                    dead_entry_id=wrong_dead,
                    operator_id=uuid.uuid4(),
                    reason="test",
                )


@pytest.mark.asyncio
async def test_fork_ack_accepts_correct_set():
    """append_fork_ack 传正确的 survivor=B, dead=C → 成功写入；再 scan_forks 无未确认。"""
    from app.services.audit_chain.forks import append_fork_ack, scan_forks

    async with _throwaway_engine() as eng:
        async_session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            chain = await _insert_fork_chain(session)
            await session.commit()

        async with async_session() as session:
            entry = await append_fork_ack(
                session,
                chain_key="__global__",
                survivor_entry_id=chain["b"].id,
                dead_entry_id=chain["c"].id,
                operator_id=uuid.uuid4(),
                reason="保留 B 分支",
            )
            await session.commit()

        assert entry.action_type == "audit.fork_ack"
        assert entry.prev_hash == chain["b"].entry_hash

        # 确认后不再有未确认分叉
        async with async_session() as session:
            forks = await scan_forks(session)
            unack = [f for f in forks if len(f.get("survivors", [])) > 1]
            assert len(unack) == 0, f"仍有未确认分叉: {unack}"


@pytest.mark.asyncio
async def test_health_degraded_on_fork():
    """Health endpoint 在有未确认分叉时返回 degraded + audit_chain 字段。"""
    import app.api.health as health_mod
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    async with _throwaway_engine() as eng:
        async_session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

        # 插入分叉
        async with async_session() as session:
            await _insert_fork_chain(session)
            await session.commit()

        # 清空缓存以确保查询
        health_mod._audit_chain_cache["data"] = None
        health_mod._audit_chain_cache["ts"] = 0.0

        # 构建最小 app 并 override
        app = FastAPI()
        app.include_router(health_mod.router, prefix="/api")

        from app.core.container import ServiceContainer

        class _MockRedis:
            async def ping(self):
                return True

        async def _mock_container():
            async with async_session() as session:
                yield ServiceContainer(db=session, redis=_MockRedis())

        from app.core.container import get_container
        app.dependency_overrides[get_container] = _mock_container

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
            data = resp.json()

        assert "audit_chain" in data
        assert data["audit_chain"]["unacknowledged_forks"] >= 1
        # PG 可达所以不该是 unhealthy，但分叉→degraded
        assert data["status"] == "degraded"

        # 清理缓存
        health_mod._audit_chain_cache["data"] = None
        health_mod._audit_chain_cache["ts"] = 0.0
