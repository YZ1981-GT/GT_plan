"""ledger_dataset_merge：SQLite 真表验证 staged 内覆盖/跳过、快照沿用与守恒。"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.audit_platform_models import (
    AccountChart,
    AccountCategory,
    AccountDirection,
    AccountSource,
    DirectionOverride,
    ImportBatch,
    TbAuxBalance,
    TbAuxLedger,
    TbBalance,
    TbLedger,
)
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services import _ledger_dataset_merge_tables as merge_tables
from app.services import mapping_service
from app.services.ledger_dataset_merge import (
    BalanceCarryConfirmationRequired,
    BaseDatasetChangedError,
    MergeRowCountError,
    freeze_append_options,
    merge_into_staged,
)
from tests.advanced_query_linkage.builder_tables import create_tables_with_closure

PROJECT = uuid.UUID("11111111-2222-3333-4444-555555555555")
BASE = uuid.UUID("aaaaaaaa-1111-2222-3333-444444444444")
STAGED = uuid.UUID("bbbbbbbb-1111-2222-3333-444444444444")
YEAR = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    seeds = (
        LedgerDataset.__table__,
        ImportBatch.__table__,
        TbLedger.__table__,
        TbAuxLedger.__table__,
        TbBalance.__table__,
        TbAuxBalance.__table__,
        AccountChart.__table__,
        DirectionOverride.__table__,
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables_with_closure, seeds)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _ledger(dataset_id: uuid.UUID, month: int, amount: str, suffix: str) -> TbLedger:
    return TbLedger(
        id=uuid.uuid4(),
        project_id=PROJECT,
        year=YEAR,
        company_code="default",
        voucher_date=date(YEAR, month, 1),
        voucher_type="记",
        voucher_no=f"{month:02d}-{suffix}",
        account_code="1002",
        account_name="银行存款",
        debit_amount=Decimal(amount),
        credit_amount=Decimal("0"),
        dataset_id=dataset_id,
        is_deleted=False,
    )


def _aux_ledger(dataset_id: uuid.UUID, month: int, amount: str, suffix: str) -> TbAuxLedger:
    return TbAuxLedger(
        id=uuid.uuid4(),
        project_id=PROJECT,
        year=YEAR,
        company_code="default",
        voucher_date=date(YEAR, month, 1),
        voucher_type="记",
        voucher_no=f"{month:02d}-{suffix}",
        account_code="1002",
        account_name="银行存款",
        aux_type="客户",
        aux_code="C1",
        aux_name="客户一",
        debit_amount=Decimal(amount),
        credit_amount=Decimal("0"),
        dataset_id=dataset_id,
        is_deleted=False,
    )


async def _seed(db: AsyncSession, *, staged_balance: bool = False, legacy_chart: bool = False):
    base = LedgerDataset(
        id=BASE,
        project_id=PROJECT,
        year=YEAR,
        status=DatasetStatus.active,
        source_type="import",
    )
    staged = LedgerDataset(
        id=STAGED,
        project_id=PROJECT,
        year=YEAR,
        status=DatasetStatus.staged,
        previous_dataset_id=BASE,
        source_type="import",
    )
    balance_id = uuid.uuid4()
    rows = [
        base,
        staged,
        _ledger(BASE, 1, "10", "base"),
        _ledger(BASE, 2, "20", "base"),
        _ledger(STAGED, 2, "200", "file"),
        _ledger(STAGED, 3, "300", "file"),
        _aux_ledger(BASE, 1, "11", "base"),
        _aux_ledger(BASE, 2, "21", "base"),
        _aux_ledger(STAGED, 2, "201", "file"),
        _aux_ledger(STAGED, 3, "301", "file"),
        TbBalance(
            id=balance_id,
            project_id=PROJECT,
            year=YEAR,
            company_code="default",
            account_code="1002",
            account_name="银行存款",
            closing_balance=Decimal("30"),
            dataset_id=BASE,
            is_deleted=False,
        ),
        AccountChart(
            id=uuid.uuid4(),
            project_id=PROJECT,
            account_code="1002",
            account_name="银行存款",
            direction=AccountDirection.debit,
            level=1,
            category=AccountCategory.asset,
            source=AccountSource.client,
            dataset_id=None if legacy_chart else BASE,
            is_deleted=False,
        ),
        DirectionOverride(
            id=uuid.uuid4(),
            project_id=PROJECT,
            dataset_id=BASE,
            table_name="tb_balance",
            record_id=balance_id,
            original_direction="credit",
            override_direction="debit",
            override_reason="测试继承重映射",
        ),
    ]
    if staged_balance:
        rows.append(TbBalance(
            id=uuid.uuid4(),
            project_id=PROJECT,
            year=YEAR,
            company_code="default",
            account_code="1002",
            account_name="文件余额",
            closing_balance=Decimal("999"),
            dataset_id=STAGED,
            is_deleted=False,
        ))
    db.add_all(rows)
    await db.flush()
    return balance_id


async def _ledger_amounts(db: AsyncSession, dataset_id: uuid.UUID) -> list[Decimal]:
    values = await db.scalars(
        sa.select(TbLedger.debit_amount)
        .where(TbLedger.dataset_id == dataset_id, TbLedger.is_deleted == sa.false())
        .order_by(TbLedger.voucher_date, TbLedger.debit_amount)
    )
    return list(values)


@pytest.mark.asyncio
async def test_overwrite_inherits_only_uncovered_months_and_remaps_override(db: AsyncSession):
    old_balance_id = await _seed(db)
    report = await merge_into_staged(
        db,
        staged_id=STAGED,
        base_id=BASE,
        project_id=PROJECT,
        year=YEAR,
        strategy="overwrite",
        balance_carry_confirmed=True,
    )

    assert await _ledger_amounts(db, STAGED) == [Decimal("10"), Decimal("200"), Decimal("300")]
    assert await _ledger_amounts(db, BASE) == [Decimal("10"), Decimal("20")]
    assert report.file_months == (2, 3)
    assert report.inherited_months == (1,)
    assert report.overwritten_months == (2,)
    assert report.tables["tb_ledger"].copied_rows == 1
    assert report.tables["tb_balance"].carried is True
    assert report.tables["account_chart"].carried is True

    new_balance_id = await db.scalar(
        sa.select(TbBalance.id).where(TbBalance.dataset_id == STAGED)
    )
    override = (
        await db.execute(
            sa.select(DirectionOverride).where(DirectionOverride.dataset_id == STAGED)
        )
    ).scalar_one()
    assert new_balance_id != old_balance_id
    assert override.record_id == new_balance_id
    assert override.record_id != old_balance_id
    assert (await db.get(LedgerDataset, STAGED)).source_summary["append"]["strategy"] == "overwrite"
    batch = await db.get(ImportBatch, report.inherited_batch_id)
    assert batch is not None and batch.source_type == "append_inherit"
@pytest.mark.asyncio
async def test_skip_drops_staged_overlap_and_keeps_base_month(db: AsyncSession):
    await _seed(db)
    report = await merge_into_staged(
        db,
        staged_id=STAGED,
        base_id=BASE,
        project_id=PROJECT,
        year=YEAR,
        strategy="skip",
        balance_carry_confirmed=True,
    )
    assert await _ledger_amounts(db, STAGED) == [Decimal("10"), Decimal("20"), Decimal("300")]
    assert report.inherited_months == (1, 2)
    assert report.skipped_months == (2,)
    assert report.overwritten_months == ()
    assert report.tables["tb_ledger"].initial_file_rows == 2
    assert report.tables["tb_ledger"].kept_file_rows == 1
    assert report.tables["tb_ledger"].expected_rows == 3
    assert report.tables["tb_aux_ledger"].expected_rows == 3


@pytest.mark.asyncio
async def test_new_month_with_carried_balance_requires_explicit_confirmation(db: AsyncSession):
    await _seed(db)
    with pytest.raises(BalanceCarryConfirmationRequired, match="余额表未随本次追加更新"):
        await merge_into_staged(
            db,
            staged_id=STAGED,
            base_id=BASE,
            project_id=PROJECT,
            year=YEAR,
            strategy="overwrite",
        )


@pytest.mark.asyncio
async def test_file_balance_does_not_require_carry_confirmation(db: AsyncSession):
    await _seed(db, staged_balance=True)
    report = await merge_into_staged(
        db,
        staged_id=STAGED,
        base_id=BASE,
        project_id=PROJECT,
        year=YEAR,
        strategy="overwrite",
    )
    assert report.balance_confirmation_required is False
    assert report.tables["tb_balance"].carried is False
    row = await db.scalar(sa.select(TbBalance.account_name).where(TbBalance.dataset_id == STAGED))
    assert row == "文件余额"
@pytest.mark.asyncio
async def test_changed_base_fails_without_touching_new_active(db: AsyncSession):
    await _seed(db)
    replacement = LedgerDataset(
        id=uuid.uuid4(),
        project_id=PROJECT,
        year=YEAR,
        status=DatasetStatus.active,
        source_type="import",
    )
    base = await db.get(LedgerDataset, BASE)
    base.status = DatasetStatus.superseded
    db.add(replacement)
    await db.flush()

    with pytest.raises(BaseDatasetChangedError, match="基准版本已变化"):
        await merge_into_staged(
            db,
            staged_id=STAGED,
            base_id=BASE,
            project_id=PROJECT,
            year=YEAR,
            strategy="skip",
            balance_carry_confirmed=True,
        )
    assert replacement.status == DatasetStatus.active


@pytest.mark.asyncio
async def test_legacy_client_chart_is_adopted_into_staged_dataset(db: AsyncSession):
    await _seed(db, legacy_chart=True)
    report = await merge_into_staged(
        db,
        staged_id=STAGED,
        base_id=BASE,
        project_id=PROJECT,
        year=YEAR,
        strategy="overwrite",
        balance_carry_confirmed=True,
    )
    assert report.tables["account_chart"].copied_rows == 1
    assert await db.scalar(
        sa.select(sa.func.count()).select_from(AccountChart).where(
            AccountChart.dataset_id == STAGED,
            AccountChart.account_code == "1002",
            AccountChart.is_deleted == sa.false(),
        )
    ) == 1


@pytest.mark.asyncio
async def test_row_count_gate_detects_copy_that_reports_but_does_not_insert(db: AsyncSession, monkeypatch):
    await _seed(db)

    async def fake_copy(*_args, **_kwargs):
        return 1

    monkeypatch.setattr(merge_tables, "_copy_rows", fake_copy)
    with pytest.raises(MergeRowCountError, match="tb_ledger 行数守恒失败"):
        await merge_into_staged(
            db,
            staged_id=STAGED,
            base_id=BASE,
            project_id=PROJECT,
            year=YEAR,
            strategy="overwrite",
            balance_carry_confirmed=True,
        )


@pytest.mark.asyncio
async def test_mapping_reads_only_active_dataset_when_same_code_exists_in_history(db: AsyncSession):
    await _seed(db)
    old_id = uuid.uuid4()
    db.add_all([
        LedgerDataset(
            id=old_id,
            project_id=PROJECT,
            year=YEAR,
            status=DatasetStatus.superseded,
            source_type="import",
        ),
        AccountChart(
            id=uuid.uuid4(),
            project_id=PROJECT,
            account_code="1002",
            account_name="旧版本银行",
            direction=AccountDirection.debit,
            level=1,
            category=AccountCategory.asset,
            source=AccountSource.client,
            dataset_id=old_id,
            is_deleted=False,
        ),
        AccountChart(
            id=uuid.uuid4(),
            project_id=PROJECT,
            account_code="1002",
            account_name="银行存款",
            direction=AccountDirection.debit,
            level=1,
            category=AccountCategory.asset,
            source=AccountSource.standard,
            is_deleted=False,
        ),
    ])
    await db.flush()
    suggestions = await mapping_service.auto_suggest(PROJECT, db, year=YEAR)
    assert [(item.original_account_code, item.original_account_name) for item in suggestions] == [
        ("1002", "银行存款")
    ]


@pytest.mark.asyncio
async def test_freeze_append_options_captures_current_active_or_no_base(db: AsyncSession):
    no_base = await freeze_append_options(
        db,
        project_id=PROJECT,
        year=YEAR,
        strategy="skip",
        balance_carry_confirmed=True,
    )
    assert no_base == {
        "strategy": "skip",
        "base_dataset_id": None,
        "balance_carry_confirmed": True,
        "no_base": True,
    }
    await _seed(db)
    frozen = await freeze_append_options(
        db,
        project_id=PROJECT,
        year=YEAR,
        strategy="overwrite",
    )
    assert frozen == {
        "strategy": "overwrite",
        "base_dataset_id": str(BASE),
        "balance_carry_confirmed": False,
        "no_base": False,
    }
