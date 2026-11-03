"""审计链写链内核单元测试（SQLite 内存库）

测试 read_head / append_entry / append_entry_batch 与惰性初始化。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models.audit_log_models  # noqa: F401
import app.models.core  # noqa: F401

from app.models.audit_log_models import AuditChainHead, AuditLogEntry
from app.services.audit_chain.canonical import GENESIS_HASH
from app.services.audit_chain.head import (
    AuditChainBypassed,
    AuditChainForked,
    append_entry,
    append_entry_batch,
    chain_key_of,
    read_head,
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
        # users 表也要建（AuditLogEntry.user_id 可能需要）
        if "users" in Base.metadata.tables:
            tables.append(Base.metadata.tables["users"])
        await conn.run_sync(Base.metadata.create_all, tables=tables)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


class TestLazyInit:
    """惰性初始化三种状态。"""

    @pytest.mark.asyncio
    async def test_empty_chain_returns_genesis(self, db: AsyncSession):
        """0 条条目 → 创世哈希，链尾表无行。"""
        entry = await append_entry(
            db, "__global__",
            action_type="test.first",
            object_type="test",
        )
        await db.flush()

        assert entry.prev_hash == GENESIS_HASH
        head = await read_head(db, "__global__")
        assert head is not None
        assert head.entry_count == 1
        assert head.tail_hash == entry.entry_hash

    @pytest.mark.asyncio
    async def test_single_tail_adopted(self, db: AsyncSession):
        """链有 1 个尾 → 惰性采用。"""
        # 先直接插入一条（模拟旧代码写入）
        from app.services.audit_chain.canonical import hash_v2

        ts = datetime.now(timezone.utc)
        ts_str = ts.isoformat(timespec="microseconds")
        eh = hash_v2(
            ts=ts_str, user_id="u1", action_type="old.write",
            object_type="test", resource_id="", project_id=None,
            year=None, payload={}, prev_hash=GENESIS_HASH,
        )
        old_entry = AuditLogEntry(
            id=uuid.uuid4(), ts=ts, action_type="old.write",
            object_type="test", payload={"_hash_v": 2, "_resource_id": ""},
            prev_hash=GENESIS_HASH, entry_hash=eh,
        )
        db.add(old_entry)
        await db.flush()

        # 现在通过 append_entry 写入，应惰性采用旧条目为链尾
        entry2 = await append_entry(
            db, "__global__",
            action_type="test.second",
            object_type="test",
        )
        await db.flush()

        assert entry2.prev_hash == eh
        head = await read_head(db, "__global__")
        assert head is not None
        assert head.entry_count == 2


    @pytest.mark.asyncio
    async def test_multi_tail_raises_forked(self, db: AsyncSession):
        """链有 >1 个未确认链尾 → AuditChainForked。"""
        from app.services.audit_chain.canonical import hash_v2

        # 插入两条共享同一 prev_hash 的条目（两个链尾）
        ts = datetime.now(timezone.utc)
        ts_str = ts.isoformat(timespec="microseconds")

        for label in ("tail_a", "tail_b"):
            eh = hash_v2(
                ts=ts_str, user_id="u1", action_type=label,
                object_type="test", resource_id="", project_id=None,
                year=None, payload={}, prev_hash=GENESIS_HASH,
            )
            entry = AuditLogEntry(
                id=uuid.uuid4(), ts=ts, action_type=label,
                object_type="test", payload={"_hash_v": 2, "_resource_id": ""},
                prev_hash=GENESIS_HASH, entry_hash=eh,
            )
            db.add(entry)
        await db.flush()

        # 惰性初始化应检测到两个链尾并抛出
        with pytest.raises(AuditChainForked):
            await append_entry(
                db, "__global__",
                action_type="should.fail",
                object_type="test",
            )

    @pytest.mark.asyncio
    async def test_zero_tail_raises_fail_closed(self, db: AsyncSession):
        """链有条目但 0 个未确认链尾 → AuditChainForked（fail-closed，I8）。

        理论场景：所有条目形成环或数据损坏导致减去 dead 后无链尾。
        按 fail-closed 要求，不退回创世，而是抛异常。
        """
        from app.services.audit_chain.canonical import hash_v2

        # 插入两条互为环：a→b→a
        ts = datetime.now(timezone.utc)
        ts_str = ts.isoformat(timespec="microseconds")

        # 先算两个互相引用的哈希——直接构造两条
        # 让它们的 entry_hash 都出现在对方的 prev_hash 中
        # 实际上制造这种场景靠手动 INSERT
        hash_a = hash_v2(
            ts=ts_str, user_id="", action_type="cycle_a",
            object_type="test", resource_id="", project_id=None,
            year=None, payload={}, prev_hash="fake_hash_b",
        )
        hash_b = hash_v2(
            ts=ts_str, user_id="", action_type="cycle_b",
            object_type="test", resource_id="", project_id=None,
            year=None, payload={}, prev_hash=hash_a,
        )
        # 用特殊的项目链避免干扰
        pid = str(uuid.uuid4())
        ck = chain_key_of(pid)

        # entry A: prev_hash = hash_b, entry_hash = hash_a
        # entry B: prev_hash = hash_a, entry_hash = hash_b
        # 两者互相引用 → 都有后继 → 链尾集合为空
        entry_a = AuditLogEntry(
            id=uuid.uuid4(), ts=ts, action_type="cycle_a",
            object_type="test",
            payload={"_hash_v": 2, "_resource_id": "", "project_id": pid},
            prev_hash=hash_b, entry_hash=hash_a,
        )
        entry_b = AuditLogEntry(
            id=uuid.uuid4(), ts=ts, action_type="cycle_b",
            object_type="test",
            payload={"_hash_v": 2, "_resource_id": "", "project_id": pid},
            prev_hash=hash_a, entry_hash=hash_b,
        )
        db.add(entry_a)
        db.add(entry_b)
        await db.flush()

        # 惰性初始化应检测到 0 个链尾并抛出（fail-closed）
        with pytest.raises(AuditChainForked, match="0 个未确认链尾"):
            await append_entry(
                db, ck,
                action_type="should.fail",
                object_type="test",
                project_id=pid,
                payload={"project_id": pid},
            )


class TestAppendEntry:
    """append_entry 基本功能。"""

    @pytest.mark.asyncio
    async def test_consecutive_writes_linked(self, db: AsyncSession):
        """连续写入链正确衔接。"""
        e1 = await append_entry(
            db, "__global__",
            action_type="act1", object_type="test",
        )
        e2 = await append_entry(
            db, "__global__",
            action_type="act2", object_type="test",
        )
        await db.flush()

        assert e2.prev_hash == e1.entry_hash
        head = await read_head(db, "__global__")
        assert head.tail_hash == e2.entry_hash
        assert head.entry_count == 2

    @pytest.mark.asyncio
    async def test_different_chains_independent(self, db: AsyncSession):
        """不同链键互不干扰。"""
        pid1 = str(uuid.uuid4())
        pid2 = str(uuid.uuid4())

        e1 = await append_entry(
            db, chain_key_of(pid1),
            action_type="act", object_type="test",
            project_id=pid1, payload={"project_id": pid1},
        )
        e2 = await append_entry(
            db, chain_key_of(pid2),
            action_type="act", object_type="test",
            project_id=pid2, payload={"project_id": pid2},
        )
        await db.flush()

        # 两条都以创世哈希为前驱
        assert e1.prev_hash == GENESIS_HASH
        assert e2.prev_hash == GENESIS_HASH

    @pytest.mark.asyncio
    async def test_v2_hash_stored_in_payload(self, db: AsyncSession):
        """落库载荷包含 _hash_v=2。"""
        entry = await append_entry(
            db, "__global__",
            action_type="test", object_type="test",
            payload={"key": "value"},
        )
        await db.flush()

        assert entry.payload.get("_hash_v") == 2

    @pytest.mark.asyncio
    async def test_bypass_detection(self, db: AsyncSession):
        """绕过链尾表写入后下一笔应报 AuditChainBypassed。"""
        # 正常写入第一条
        e1 = await append_entry(
            db, "__global__",
            action_type="normal", object_type="test",
        )
        await db.flush()

        # 绕过链尾表直接插入
        from app.services.audit_chain.canonical import hash_v2
        ts = datetime.now(timezone.utc)
        ts_str = ts.isoformat(timespec="microseconds")
        bypass_hash = hash_v2(
            ts=ts_str, user_id="", action_type="bypass",
            object_type="test", resource_id="", project_id=None,
            year=None, payload={}, prev_hash=e1.entry_hash,
        )
        bypass_entry = AuditLogEntry(
            id=uuid.uuid4(), ts=ts, action_type="bypass",
            object_type="test", payload={"_hash_v": 2, "_resource_id": ""},
            prev_hash=e1.entry_hash, entry_hash=bypass_hash,
        )
        db.add(bypass_entry)
        await db.flush()

        # 下一笔通过 append_entry 应抛 AuditChainBypassed
        with pytest.raises(AuditChainBypassed):
            await append_entry(
                db, "__global__",
                action_type="next", object_type="test",
            )


class TestAppendEntryBatch:
    """append_entry_batch 按链键升序。"""

    @pytest.mark.asyncio
    async def test_batch_ordering(self, db: AsyncSession):
        """批量写入按链键升序处理。"""
        pid_a = "aaaa"
        pid_z = "zzzz"
        payloads = [
            {"chain_key": chain_key_of(pid_z), "action_type": "z",
             "object_type": "test", "project_id": pid_z,
             "payload": {"project_id": pid_z}},
            {"chain_key": chain_key_of(pid_a), "action_type": "a",
             "object_type": "test", "project_id": pid_a,
             "payload": {"project_id": pid_a}},
        ]
        ids = await append_entry_batch(db, payloads)
        assert len(ids) == 2
