"""三层一致测试：V221 迁移 SQL + ORM AuditChainHead + service。

用 SQLite 内存库验证 ORM 映射正确。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# SQLite 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models.audit_log_models  # noqa: F401
import app.models.core  # noqa: F401

from app.models.audit_log_models import AuditChainHead

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables = [
            Base.metadata.tables["audit_chain_head"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


class TestAuditChainHeadORM:
    """ORM 映射验证：写一行、读回字段全等。"""

    @pytest.mark.asyncio
    async def test_write_and_read_back(self, db: AsyncSession):
        entry_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        head = AuditChainHead(
            chain_key="__global__",
            tail_entry_id=entry_id,
            tail_hash="a" * 64,
            entry_count=42,
            updated_at=now,
        )
        db.add(head)
        await db.flush()

        from sqlalchemy import select
        stmt = select(AuditChainHead).where(
            AuditChainHead.chain_key == "__global__"
        )
        result = await db.execute(stmt)
        row = result.scalar_one()

        assert row.chain_key == "__global__"
        assert row.tail_entry_id == entry_id
        assert row.tail_hash == "a" * 64
        assert row.entry_count == 42

    @pytest.mark.asyncio
    async def test_primary_key_constraint(self, db: AsyncSession):
        """同一 chain_key 写两次应该冲突。"""
        from sqlalchemy.exc import IntegrityError

        head1 = AuditChainHead(
            chain_key="test_key",
            tail_entry_id=uuid.uuid4(),
            tail_hash="b" * 64,
            entry_count=1,
        )
        db.add(head1)
        await db.flush()

        head2 = AuditChainHead(
            chain_key="test_key",
            tail_entry_id=uuid.uuid4(),
            tail_hash="c" * 64,
            entry_count=2,
        )
        db.add(head2)
        with pytest.raises(IntegrityError):
            await db.flush()
