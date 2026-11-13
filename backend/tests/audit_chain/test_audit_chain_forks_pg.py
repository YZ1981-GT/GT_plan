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

from app.models.audit_log_models import AuditChainHead, AuditLogEntry
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
            await conn.run_sync(AuditChainHead.__table__.create, checkfirst=True)
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


@pytest.mark.asyncio
async def test_scan_forks_ignores_independent_genesis_entries():
    """不同项目各自的创世条目不能被当成同一条链的分叉。"""
    from app.services.audit_chain.forks import scan_forks

    async with _throwaway_engine() as eng:
        async_session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            for _ in range(3):
                project_id = str(uuid.uuid4())
                session.add(
                    _make_entry(
                        "project.genesis",
                        GENESIS_HASH,
                        payload={"project_id": project_id},
                    )
                )
            await session.commit()

        async with async_session() as session:
            assert await scan_forks(session) == []


@pytest.mark.asyncio
async def test_fork_acks_multi_dead_on_pg():
    """真 PG（链锁 + JSONB 过滤）：一条链上 3 个死端（其一侧枝 2 条）一次确认；写后恰好一个链尾、可续写、链校验无分叉 / 内容不符。

    spec enterprise-embedding-rerank-closure R8（共享库 __global__ 10 个链尾、现有工具只接受恰 2 个链尾）。
    """
    from app.services.audit_chain.forks import _unconfirmed_tails, append_fork_acks, blocked_chains, scan_forks
    from app.services.audit_chain.head import append_entry, read_head
    from app.services.audit_chain.verify import verify_chain

    async with _throwaway_engine() as eng:
        async_session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            a = _make_entry("genesis.action", GENESIS_HASH)
            session.add(a)
            await session.flush()
            main = _make_entry("main", a.entry_hash)
            x = _make_entry("dead.x", a.entry_hash)
            y1 = _make_entry("dead.y1", a.entry_hash)
            session.add_all([main, x, y1])
            await session.flush()
            y2 = _make_entry("dead.y2", y1.entry_hash)
            z = _make_entry("dead.z", main.entry_hash)
            main2 = _make_entry("main2", main.entry_hash)
            session.add_all([y2, z, main2])
            await session.commit()

        async with async_session() as session:
            assert await blocked_chains(session) == [("__global__", 7, 4)]
            written = await append_fork_acks(
                session, chain_key="__global__", survivor_entry_id=main2.id,
                dead_entry_ids=[x.id, y2.id, z.id], operator_id=uuid.uuid4(), reason="真 PG 多死端",
            )
            await session.commit()
        assert {w.payload["dead_entry_id"] for w in written} == {str(i) for i in (x.id, y1.id, y2.id, z.id)}

        async with async_session() as session:
            assert await _unconfirmed_tails(session, "__global__") == {written[-1].id}
            head = await read_head(session, "__global__")
            assert head is not None and head.tail_entry_id == written[-1].id
            assert [f for f in await scan_forks(session) if len(f["survivors"]) > 1] == []
            result = await verify_chain(session)
            assert [p for p in result.problems if p["type"] in {"fork", "content_mismatch", "orphan"}] == []
            nxt = await append_entry(session, "__global__", action_type="after.ack", object_type="test")
            await session.commit()
            assert nxt.prev_hash == written[-1].entry_hash
            assert await blocked_chains(session) == []
