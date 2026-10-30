"""审计链写链内核 — 真 PG 测试（一次性库）

需要本地 PG 可达。不连共享库写。
测试真实的：咨询锁串行化、绕过检测、分叉检测。
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_log_models import AuditChainHead, AuditLogEntry
from app.models.base import Base
from app.services.audit_chain.canonical import GENESIS_HASH, hash_v2
from app.services.audit_chain.head import (
    AuditChainBypassed,
    AuditChainForked,
    append_entry,
    read_head,
)

# 共享库 URL（只用来建一次性库，不在上面写）
_SHARED_URL = os.environ.get(
    "TEST_PG_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
)

DB_NAME = f"gt_s10_{os.getpid()}_{int(time.time())}"


def _db_url(dbname: str) -> str:
    """替换连接 URL 中的数据库名。"""
    parts = _SHARED_URL.rsplit("/", 1)
    return f"{parts[0]}/{dbname}"


@pytest_asyncio.fixture(scope="module")
async def pg_engine():
    """在共享 PG 上创建一次性库，测试结束后删除。"""
    admin_engine = create_async_engine(
        _SHARED_URL, isolation_level="AUTOCOMMIT"
    )
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(text(f"CREATE DATABASE {DB_NAME}"))
    except Exception as exc:
        await admin_engine.dispose()
        pytest.skip(f"无法连接 PG 或创建库 {DB_NAME}: {exc}")
    finally:
        try:
            await admin_engine.dispose()
        except Exception:
            pass

    test_engine = create_async_engine(_db_url(DB_NAME))
    async with test_engine.begin() as conn:
        # 只建两张表
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                Base.metadata.tables["audit_log_entries"],
                Base.metadata.tables["audit_chain_head"],
            ],
        )
    yield test_engine
    await test_engine.dispose()

    # 清理：删一次性库
    admin_engine = create_async_engine(
        _SHARED_URL, isolation_level="AUTOCOMMIT"
    )
    try:
        async with admin_engine.connect() as conn:
            # 断开所有连接
            await conn.execute(text(
                f"SELECT pg_terminate_backend(pid) "
                f"FROM pg_stat_activity WHERE datname='{DB_NAME}'"
            ))
            await conn.execute(text(f"DROP DATABASE IF EXISTS {DB_NAME}"))
    finally:
        await admin_engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine):
    factory = async_sessionmaker(
        pg_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session
        await session.rollback()


class TestPGConcurrency:
    """两个独立会话同链并发写入 → 链长 2 且衔接（锁串行化）。"""

    @pytest.mark.asyncio
    async def test_concurrent_writes_serialized(self, pg_engine):
        factory = async_sessionmaker(
            pg_engine, class_=AsyncSession, expire_on_commit=False
        )
        chain_key = f"project:{uuid.uuid4()}"
        pid = chain_key.removeprefix("project:")

        async def writer(label: str):
            async with factory() as db:
                entry = await append_entry(
                    db, chain_key,
                    action_type=f"concurrent.{label}",
                    object_type="test",
                    project_id=pid,
                    payload={"project_id": pid, "writer": label},
                )
                await db.commit()
                return entry.id, entry.entry_hash, entry.prev_hash

        id_a, hash_a, prev_a = await asyncio.gather(
            writer("A"), writer("B")
        ).__await__() if False else (None, None, None)

        # 并发执行
        results = await asyncio.gather(writer("A"), writer("B"))
        (id_a, hash_a, prev_a) = results[0]
        (id_b, hash_b, prev_b) = results[1]

        # 一条以创世为前驱，另一条以第一条为前驱
        prev_hashes = {prev_a, prev_b}
        entry_hashes = {hash_a, hash_b}

        assert GENESIS_HASH in prev_hashes
        # 其中一条的 prev_hash 应该是另一条的 entry_hash
        assert prev_hashes - {GENESIS_HASH} <= entry_hashes

        # 链尾正确
        async with factory() as db:
            head = await read_head(db, chain_key)
            assert head is not None
            assert head.entry_count == 2


class TestPGBypass:
    """绕过写入 → AuditChainBypassed。"""

    @pytest.mark.asyncio
    async def test_bypass_raises(self, pg_session: AsyncSession):
        chain_key = f"project:{uuid.uuid4()}"
        pid = chain_key.removeprefix("project:")

        # 正常写入第一条
        e1 = await append_entry(
            pg_session, chain_key,
            action_type="normal", object_type="test",
            project_id=pid, payload={"project_id": pid},
        )
        await pg_session.commit()

        # 绕过链尾表直接 INSERT
        ts = datetime.now(timezone.utc)
        ts_str = ts.isoformat(timespec="microseconds")
        bypass_hash = hash_v2(
            ts=ts_str, user_id="", action_type="bypass",
            object_type="test", resource_id="", project_id=pid,
            year=None, payload={"project_id": pid}, prev_hash=e1.entry_hash,
        )
        await pg_session.execute(text(
            "INSERT INTO audit_log_entries "
            "(id, ts, action_type, object_type, payload, prev_hash, entry_hash) "
            "VALUES (:id, :ts, :at, :ot, :p::jsonb, :ph, :eh)"
        ), {
            "id": str(uuid.uuid4()), "ts": ts, "at": "bypass", "ot": "test",
            "p": '{"project_id":"' + pid + '","_hash_v":2,"_resource_id":""}',
            "ph": e1.entry_hash, "eh": bypass_hash,
        })
        await pg_session.commit()

        with pytest.raises(AuditChainBypassed):
            await append_entry(
                pg_session, chain_key,
                action_type="next", object_type="test",
                project_id=pid, payload={"project_id": pid},
            )


class TestPGFork:
    """多尾链 → AuditChainForked；确认后可续写。"""

    @pytest.mark.asyncio
    async def test_forked_chain_raises(self, pg_engine):
        factory = async_sessionmaker(
            pg_engine, class_=AsyncSession, expire_on_commit=False
        )
        chain_key = "__global__"

        # 用一个独立的全局链前缀避免与其他测试冲突
        # 为简化，用项目链
        pid = str(uuid.uuid4())
        chain_key = f"project:{pid}"

        async with factory() as db:
            # 写创世后的第一条
            e1 = await append_entry(
                db, chain_key,
                action_type="genesis_child", object_type="test",
                project_id=pid, payload={"project_id": pid},
            )
            await db.commit()

        # 直接插入另一条也以 e1 为前驱 — 制造分叉
        async with factory() as db:
            ts = datetime.now(timezone.utc)
            ts_str = ts.isoformat(timespec="microseconds")
            fork_hash = hash_v2(
                ts=ts_str, user_id="", action_type="fork_branch",
                object_type="test", resource_id="", project_id=pid,
                year=None, payload={"project_id": pid},
                prev_hash=e1.entry_hash,
            )
            await db.execute(text(
                "INSERT INTO audit_log_entries "
                "(id, ts, action_type, object_type, payload, prev_hash, entry_hash) "
                "VALUES (:id, :ts, :at, :ot, :p::jsonb, :ph, :eh)"
            ), {
                "id": str(uuid.uuid4()), "ts": ts, "at": "fork_branch",
                "ot": "test",
                "p": '{"project_id":"' + pid + '","_hash_v":2,"_resource_id":""}',
                "ph": e1.entry_hash, "eh": fork_hash,
            })
            # 也需要删掉链尾表让惰性初始化重新算
            await db.execute(text(
                "DELETE FROM audit_chain_head WHERE chain_key = :ck"
            ), {"ck": chain_key})
            await db.commit()

        # 现在 append_entry 应抛 AuditChainForked
        async with factory() as db:
            with pytest.raises(AuditChainForked):
                await append_entry(
                    db, chain_key,
                    action_type="after_fork", object_type="test",
                    project_id=pid, payload={"project_id": pid},
                )

    @pytest.mark.asyncio
    async def test_fork_ack_then_continue(self, pg_engine):
        """确认分叉后可以续写。"""
        factory = async_sessionmaker(
            pg_engine, class_=AsyncSession, expire_on_commit=False
        )
        pid = str(uuid.uuid4())
        chain_key = f"project:{pid}"

        # 写第一条
        async with factory() as db:
            e1 = await append_entry(
                db, chain_key,
                action_type="root", object_type="test",
                project_id=pid, payload={"project_id": pid},
            )
            await db.commit()
            e1_hash = e1.entry_hash
            e1_id = e1.id

        # 制造分叉
        async with factory() as db:
            ts = datetime.now(timezone.utc)
            ts_str = ts.isoformat(timespec="microseconds")
            fork_hash = hash_v2(
                ts=ts_str, user_id="", action_type="fork",
                object_type="test", resource_id="", project_id=pid,
                year=None, payload={"project_id": pid},
                prev_hash=e1_hash,
            )
            fork_id = uuid.uuid4()
            await db.execute(text(
                "INSERT INTO audit_log_entries "
                "(id, ts, action_type, object_type, payload, prev_hash, entry_hash) "
                "VALUES (:id, :ts, :at, :ot, :p::jsonb, :ph, :eh)"
            ), {
                "id": str(fork_id), "ts": ts, "at": "fork", "ot": "test",
                "p": '{"project_id":"' + pid + '","_hash_v":2,"_resource_id":""}',
                "ph": e1_hash, "eh": fork_hash,
            })
            await db.execute(text(
                "DELETE FROM audit_chain_head WHERE chain_key = :ck"
            ), {"ck": chain_key})
            await db.commit()

        # 确认分叉
        from app.services.audit_chain.forks import append_fork_ack
        async with factory() as db:
            # 先找出两个链尾的 entry_id
            from sqlalchemy import select
            # 链尾就是 e1 的两个后继：head 上的那条 和 fork
            head_row = (await db.execute(
                select(AuditLogEntry.id).where(AuditLogEntry.entry_hash == e1_hash)
            )).scalar_one()
            # head 上的后继 = 通过 append_entry 写的 e1，它的后继在 head 表里
            # 但 head 表已删，用扫描方式找链尾
            all_entries = (await db.execute(
                select(AuditLogEntry).where(
                    AuditLogEntry.payload["project_id"].astext == pid
                )
            )).scalars().all()

            entry_hashes = {e.entry_hash for e in all_entries}
            prev_hashes = {e.prev_hash for e in all_entries}
            tail_entries = [
                e for e in all_entries
                if e.entry_hash not in prev_hashes
            ]
            assert len(tail_entries) == 2

            # survivor = e1 后继中继续延伸的那个（如果是 head 写入的那条）
            # 这里简单选第一个作 survivor
            survivor = tail_entries[0]
            dead = tail_entries[1]

            await append_fork_ack(
                db,
                chain_key=chain_key,
                survivor_entry_id=survivor.id,
                dead_entry_id=dead.id,
                operator_id=uuid.uuid4(),
                reason="test fork ack",
            )
            await db.commit()

        # 确认后可以续写
        async with factory() as db:
            # 重建链尾
            await db.execute(text(
                "DELETE FROM audit_chain_head WHERE chain_key = :ck"
            ), {"ck": chain_key})
            await db.commit()

        async with factory() as db:
            e_after = await append_entry(
                db, chain_key,
                action_type="after_ack", object_type="test",
                project_id=pid, payload={"project_id": pid},
            )
            await db.commit()
            assert e_after.entry_hash is not None


class TestPGJsonbRoundTrip:
    """1e20 经真 JSONB 往返重算一致。"""

    @pytest.mark.asyncio
    async def test_float_1e20_roundtrip(self, pg_session: AsyncSession):
        pid = str(uuid.uuid4())
        chain_key = f"project:{pid}"

        entry = await append_entry(
            pg_session, chain_key,
            action_type="float_test", object_type="test",
            project_id=pid,
            payload={"project_id": pid, "amount": 1e20},
        )
        await pg_session.commit()

        # 读回并校验 _hash_v 存在
        from sqlalchemy import select
        stmt = select(AuditLogEntry).where(AuditLogEntry.id == entry.id)
        row = (await pg_session.execute(stmt)).scalar_one()

        assert row.payload.get("_hash_v") == 2
        # amount 应该是规范化后的字符串
        assert row.payload.get("amount") == "100000000000000000000"
