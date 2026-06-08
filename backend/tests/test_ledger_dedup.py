"""导入数据去重 dedup_ledger_data 回归测试（2026-06-08）。

核心不变量：
1. 整行字节级完全相同的重复 → 只保留每组首条（最小 id），其余被删
2. 任一业务列有差异（如金额/摘要/raw_extra）→ 不算重复，全部保留
3. 默认软删（is_deleted=true），不物理删，可恢复
4. 只作用 active dataset，superseded 历史版本不动
5. dry_run 只统计不删

需真实 PG（窗口函数 + ledger_datasets EXISTS 关联），PG 不可达则 skip。
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.models.audit_platform_models import TbLedger
from app.services.ledger_data_service import dedup_ledger_data

_TEST_PROJECT_ID = uuid.UUID("dedc0de0-0000-4000-8000-000000000abc")
_TEST_YEAR = 2098
_IS_PG = settings.DATABASE_URL.startswith("postgresql")


@pytest_asyncio.fixture
async def setup():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (dedup window-function test)")

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")

    factory = async_sessionmaker(engine, expire_on_commit=False)

    from app.models.core import Project, ProjectStatus, ProjectType, User

    active_ds = uuid.uuid4()
    super_ds = uuid.uuid4()

    async def _cleanup():
        async with factory() as db:
            await db.execute(sa.delete(TbLedger).where(
                TbLedger.project_id == _TEST_PROJECT_ID, TbLedger.year == _TEST_YEAR))
            await db.execute(sa.delete(LedgerDataset).where(
                LedgerDataset.project_id == _TEST_PROJECT_ID))
            await db.commit()

    await _cleanup()

    async with factory() as db:
        user = (await db.execute(sa.select(User).where(User.username == "_dedup_test_user"))).scalar_one_or_none()
        if user:
            uid = user.id
        else:
            uid = uuid.uuid4()
            db.add(User(id=uid, username="_dedup_test_user", email="dedup@test.com",
                        hashed_password="x", role="admin"))
            await db.flush()
        if not (await db.execute(sa.select(Project).where(Project.id == _TEST_PROJECT_ID))).scalar_one_or_none():
            db.add(Project(id=_TEST_PROJECT_ID, name="dedup-test", client_name="X",
                           project_type=ProjectType.annual, status=ProjectStatus.execution, created_by=uid))
        # active + superseded 两个 dataset
        db.add(LedgerDataset(id=active_ds, project_id=_TEST_PROJECT_ID, year=_TEST_YEAR,
                             status=DatasetStatus.active, source_type="test"))
        db.add(LedgerDataset(id=super_ds, project_id=_TEST_PROJECT_ID, year=_TEST_YEAR,
                             status=DatasetStatus.superseded, source_type="test"))
        await db.commit()

    yield factory, active_ds, super_ds
    await _cleanup()
    await engine.dispose()


def _row(dataset_id, *, vno, acct, debit=None, credit=None, summary="结转", raw_extra=None):
    return TbLedger(
        id=uuid.uuid4(), project_id=_TEST_PROJECT_ID, year=_TEST_YEAR,
        company_code="C1", voucher_date=date(2098, 1, 31), voucher_no=vno, account_code=acct,
        account_name="测试科目", debit_amount=debit, credit_amount=credit,
        summary=summary, dataset_id=dataset_id, is_deleted=False, raw_extra=raw_extra,
    )


@pytest.mark.asyncio
async def test_dedup_removes_exact_duplicates_keeps_distinct(setup):
    factory, active_ds, _ = setup
    async with factory() as db:
        # 3 行完全相同（应删 2 留 1）
        for _ in range(3):
            db.add(_row(active_ds, vno="0001", acct="6001", credit=Decimal("0.01")))
        # 1 行金额不同（保留）
        db.add(_row(active_ds, vno="0001", acct="6001", credit=Decimal("9.99")))
        # 1 行 raw_extra 不同（保留）
        db.add(_row(active_ds, vno="0001", acct="6001", credit=Decimal("0.01"), raw_extra={"x": 1}))
        await db.commit()

    # dry_run 预览
    async with factory() as db:
        preview = await dedup_ledger_data(db, project_id=_TEST_PROJECT_ID, year=_TEST_YEAR, dry_run=True)
    assert preview["tb_ledger"] == 2  # 3 个相同的删 2

    # 实际执行（默认软删）
    async with factory() as db:
        result = await dedup_ledger_data(db, project_id=_TEST_PROJECT_ID, year=_TEST_YEAR)
    assert result["tb_ledger"] == 2
    assert result["mode"] == "soft"

    # 校验：可见行 = 3（1 个去重后保留 + 金额不同 + raw_extra 不同），软删 2 行
    async with factory() as db:
        visible = (await db.execute(sa.text(
            "SELECT count(*) FROM tb_ledger WHERE project_id=:p AND year=:y AND is_deleted=false"
        ), {"p": str(_TEST_PROJECT_ID), "y": _TEST_YEAR})).scalar()
        soft_deleted = (await db.execute(sa.text(
            "SELECT count(*) FROM tb_ledger WHERE project_id=:p AND year=:y AND is_deleted=true"
        ), {"p": str(_TEST_PROJECT_ID), "y": _TEST_YEAR})).scalar()
    assert visible == 3
    assert soft_deleted == 2


@pytest.mark.asyncio
async def test_dedup_ignores_superseded_dataset(setup):
    factory, active_ds, super_ds = setup
    async with factory() as db:
        # superseded 里放 3 行完全相同
        for _ in range(3):
            db.add(_row(super_ds, vno="0002", acct="6401", debit=Decimal("5")))
        await db.commit()

    async with factory() as db:
        result = await dedup_ledger_data(db, project_id=_TEST_PROJECT_ID, year=_TEST_YEAR)
    # superseded 不动
    assert result["tb_ledger"] == 0
    async with factory() as db:
        cnt = (await db.execute(sa.text(
            "SELECT count(*) FROM tb_ledger WHERE dataset_id=:d AND is_deleted=false"
        ), {"d": str(super_ds)})).scalar()
    assert cnt == 3


@pytest.mark.asyncio
async def test_dedup_no_duplicates_returns_zero(setup):
    factory, active_ds, _ = setup
    async with factory() as db:
        db.add(_row(active_ds, vno="0003", acct="1002", debit=Decimal("1")))
        db.add(_row(active_ds, vno="0003", acct="1002", debit=Decimal("2")))
        await db.commit()
    async with factory() as db:
        result = await dedup_ledger_data(db, project_id=_TEST_PROJECT_ID, year=_TEST_YEAR, dry_run=True)
    assert result["tb_ledger"] == 0
    assert result["total_deleted"] == 0
