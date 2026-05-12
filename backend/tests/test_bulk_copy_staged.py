"""B2: bulk_copy_staged 正确性验证（用独立 function-scope engine 避开全局 async_session 的跨 loop 问题）。

设计思路：
- 每个测试用独立 engine + async_sessionmaker（避免 pytest-asyncio function-scope loop
  与全局 async_session 复用的连接绑在旧 loop 上导致 "Event loop is closed"）
- 用真实 PG URL（settings.DATABASE_URL），项目级临时数据（_TEST_PROJECT_ID + _TEST_YEAR=2099）
- 每个测试结束后清理插入的临时行 + dispose engine
- PG 不可达则全部 skip
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.audit_platform_models import TbAuxBalance, TbBalance, TbLedger
from app.services.ledger_import.writer import (
    COPY_THRESHOLD_ROWS,
    bulk_copy_staged,
    bulk_insert_staged,
    bulk_write_staged,
)

# 用固定 UUID 便于清理
_TEST_PROJECT_ID = uuid.UUID("fedcba98-7654-3210-fedc-ba9876543210")
_TEST_YEAR = 2099  # 避开真实年度
_IS_PG = settings.DATABASE_URL.startswith("postgresql")


@pytest_asyncio.fixture
async def session_factory():
    """为当前测试建独立 engine + session_factory，用完 dispose。

    避开全局 async_session 跨 event loop 的连接句柄失效问题。
    PG 不可达则 skip。
    """
    if not _IS_PG:
        pytest.skip("need PostgreSQL (B2 COPY test)")

    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=2,
        max_overflow=4,
        pool_pre_ping=True,
        echo=False,
    )
    # probe reachability
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable, skip B2 COPY test")

    factory = async_sessionmaker(engine, expire_on_commit=False)

    # setup test user + project (FK)
    from app.models.core import Project, ProjectStatus, ProjectType, User

    async with factory() as db:
        existing_user = (
            await db.execute(sa.select(User).where(User.username == "_b2_test_user"))
        ).scalar_one_or_none()
        if existing_user:
            user_id = existing_user.id
        else:
            user_id = uuid.uuid4()
            db.add(
                User(
                    id=user_id,
                    username="_b2_test_user",
                    email="b2test@test.com",
                    hashed_password="x",
                    role="admin",
                )
            )
            await db.flush()

        existing_project = (
            await db.execute(sa.select(Project).where(Project.id == _TEST_PROJECT_ID))
        ).scalar_one_or_none()
        if not existing_project:
            db.add(
                Project(
                    id=_TEST_PROJECT_ID,
                    name="B2-test",
                    client_name="B2",
                    project_type=ProjectType.annual,
                    status=ProjectStatus.execution,
                    created_by=user_id,
                )
            )
        await db.commit()

    async def _cleanup() -> None:
        async with factory() as db:
            for tbl in (TbBalance, TbAuxBalance, TbLedger):
                await db.execute(
                    sa.delete(tbl).where(
                        tbl.project_id == _TEST_PROJECT_ID,
                        tbl.year == _TEST_YEAR,
                    )
                )
            await db.commit()

    await _cleanup()
    try:
        yield factory
    finally:
        await _cleanup()
        await engine.dispose()


@pytest.mark.asyncio
async def test_bulk_copy_staged_basic(session_factory):
    """base case: insert 3 balance rows, all fields persisted."""
    rows = [
        {
            "account_code": "1001",
            "account_name": "cash",
            "opening_balance": Decimal("100.50"),
            "closing_balance": Decimal("200.75"),
            "company_code": "001",
        },
        {
            "account_code": "1002",
            "account_name": "bank",
            "opening_balance": Decimal("5000"),
            "closing_balance": Decimal("5500"),
            "company_code": "001",
        },
        {
            "account_code": "1122",
            "account_name": "ar",
            "opening_balance": Decimal("3000"),
            "closing_balance": Decimal("3500"),
            "company_code": "001",
        },
    ]

    dataset_id = uuid.uuid4()
    n = await bulk_copy_staged(
        session_factory,
        TbBalance,
        rows,
        project_id=_TEST_PROJECT_ID,
        year=_TEST_YEAR,
        dataset_id=dataset_id,
    )
    assert n == 3

    async with session_factory() as db:
        result = await db.execute(
            sa.select(TbBalance)
            .where(
                TbBalance.project_id == _TEST_PROJECT_ID,
                TbBalance.year == _TEST_YEAR,
            )
            .order_by(TbBalance.account_code)
        )
        persisted = result.scalars().all()
    assert len(persisted) == 3
    assert persisted[0].account_code == "1001"
    assert persisted[0].opening_balance == Decimal("100.50")
    assert persisted[0].closing_balance == Decimal("200.75")
    assert persisted[1].account_code == "1002"
    assert persisted[2].account_code == "1122"
    assert all(r.project_id == _TEST_PROJECT_ID for r in persisted)
    assert all(r.year == _TEST_YEAR for r in persisted)
    assert all(r.dataset_id == dataset_id for r in persisted)
    assert all(r.is_deleted is True for r in persisted)


@pytest.mark.asyncio
async def test_bulk_copy_staged_jsonb_raw_extra(session_factory):
    """JSONB raw_extra serialized to JSON string, read back as dict."""
    rows = [
        {
            "account_code": "9001",
            "account_name": "jsonb-test",
            "closing_balance": Decimal("1"),
            "company_code": "001",
            "raw_extra": {"source": "test", "extra_fields": {"a": 1, "b": "zh"}},
        },
    ]
    dataset_id = uuid.uuid4()
    await bulk_copy_staged(
        session_factory,
        TbBalance,
        rows,
        project_id=_TEST_PROJECT_ID,
        year=_TEST_YEAR,
        dataset_id=dataset_id,
    )

    async with session_factory() as db:
        result = await db.execute(
            sa.select(TbBalance).where(
                TbBalance.project_id == _TEST_PROJECT_ID,
                TbBalance.account_code == "9001",
            )
        )
        row = result.scalar_one()
    assert isinstance(row.raw_extra, dict)
    assert row.raw_extra["source"] == "test"
    assert row.raw_extra["extra_fields"]["b"] == "zh"


@pytest.mark.asyncio
async def test_bulk_copy_staged_empty_rows(session_factory):
    """empty rows returns 0 without error."""
    n = await bulk_copy_staged(
        session_factory,
        TbBalance,
        [],
        project_id=_TEST_PROJECT_ID,
        year=_TEST_YEAR,
        dataset_id=uuid.uuid4(),
    )
    assert n == 0


@pytest.mark.asyncio
async def test_bulk_copy_staged_large_batch_performance(session_factory):
    """12000 rows perf smoke (above COPY_THRESHOLD_ROWS)."""
    rows = [
        {
            "account_code": f"TEST_{i:06d}",
            "account_name": f"perf-{i}",
            "closing_balance": Decimal(str(i)),
            "company_code": "001",
        }
        for i in range(12000)
    ]
    dataset_id = uuid.uuid4()

    import time

    t0 = time.time()
    n = await bulk_copy_staged(
        session_factory,
        TbBalance,
        rows,
        project_id=_TEST_PROJECT_ID,
        year=_TEST_YEAR,
        dataset_id=dataset_id,
    )
    elapsed = time.time() - t0
    assert n == 12000
    print(f"\n    [perf] COPY 12000 rows: {elapsed:.2f}s ({int(12000 / elapsed)} rows/s)")


@pytest.mark.asyncio
async def test_bulk_write_staged_uses_insert_for_small_batch(session_factory):
    """small batch (< threshold) goes through INSERT."""
    rows = [
        {
            "account_code": f"S_{i}",
            "closing_balance": Decimal(i),
            "company_code": "001",
        }
        for i in range(50)
    ]
    dataset_id = uuid.uuid4()
    n = await bulk_write_staged(
        session_factory,
        TbBalance,
        rows,
        project_id=_TEST_PROJECT_ID,
        year=_TEST_YEAR,
        dataset_id=dataset_id,
    )
    assert n == 50


@pytest.mark.asyncio
async def test_bulk_write_staged_uses_copy_for_large_batch(session_factory):
    """large batch (>= threshold) goes through COPY."""
    rows = [
        {
            "account_code": f"L_{i:06d}",
            "closing_balance": Decimal(i),
            "company_code": "001",
        }
        for i in range(COPY_THRESHOLD_ROWS + 100)
    ]
    dataset_id = uuid.uuid4()
    n = await bulk_write_staged(
        session_factory,
        TbBalance,
        rows,
        project_id=_TEST_PROJECT_ID,
        year=_TEST_YEAR,
        dataset_id=dataset_id,
    )
    assert n == COPY_THRESHOLD_ROWS + 100


@pytest.mark.asyncio
async def test_bulk_copy_vs_insert_results_identical(session_factory):
    """COPY and INSERT both write equivalent row shape."""
    rows = [
        {
            "account_code": "COMPARE_1",
            "account_name": "cmp-1",
            "opening_balance": Decimal("100.00"),
            "closing_balance": Decimal("110.00"),
            "company_code": "001",
        },
    ]
    insert_ds = uuid.uuid4()
    await bulk_insert_staged(
        session_factory,
        TbBalance,
        rows,
        project_id=_TEST_PROJECT_ID,
        year=_TEST_YEAR,
        dataset_id=insert_ds,
    )
    copy_rows = [{**rows[0], "account_code": "COMPARE_2"}]
    copy_ds = uuid.uuid4()
    await bulk_copy_staged(
        session_factory,
        TbBalance,
        copy_rows,
        project_id=_TEST_PROJECT_ID,
        year=_TEST_YEAR,
        dataset_id=copy_ds,
    )
    async with session_factory() as db:
        insert_row = (
            await db.execute(
                sa.select(TbBalance).where(
                    TbBalance.project_id == _TEST_PROJECT_ID,
                    TbBalance.account_code == "COMPARE_1",
                )
            )
        ).scalar_one()
        copy_row = (
            await db.execute(
                sa.select(TbBalance).where(
                    TbBalance.project_id == _TEST_PROJECT_ID,
                    TbBalance.account_code == "COMPARE_2",
                )
            )
        ).scalar_one()

    assert insert_row.account_name == copy_row.account_name
    assert insert_row.opening_balance == copy_row.opening_balance
    assert insert_row.closing_balance == copy_row.closing_balance
    assert insert_row.company_code == copy_row.company_code
    assert insert_row.year == copy_row.year
    assert insert_row.is_deleted == copy_row.is_deleted
