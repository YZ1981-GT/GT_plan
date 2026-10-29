"""ledger_dataset_merge 的 PostgreSQL INSERT…SELECT、分区表与方向覆盖重映射。"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.audit_platform_models import (
    AccountChart,
    AccountCategory,
    AccountDirection,
    AccountSource,
    DirectionOverride,
    TbBalance,
    TbLedger,
)
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services.ledger_dataset_merge import merge_into_staged

pytestmark = pytest.mark.pg_only
ROOT = Path(__file__).resolve().parents[1]
PROJECT = uuid.UUID("ca8da212-8a0f-48b6-bd82-06660bd94380")
YEAR = 2025


async def _apply_v214(conn) -> None:
    body = "\n".join(
        line for line in (ROOT / "migrations/V215__account_chart_dataset_versioning.sql")
        .read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    for statement in body.split(";"):
        if statement.strip():
            await conn.execute(sa.text(statement))


@pytest.mark.asyncio
async def test_pg_overwrite_merge_keeps_base_immutable_and_remaps_override():
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        pytest.skip("需要真实 PostgreSQL")
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            exists = await session.scalar(sa.text(
                "SELECT count(*) FROM projects WHERE id=:pid AND client_name LIKE '【测试】%'"
            ), {"pid": PROJECT})
            if not exists:
                pytest.skip("凭证【测试】项目不存在")
            await _apply_v214(conn)
            await session.execute(sa.update(LedgerDataset).where(
                LedgerDataset.project_id == PROJECT,
                LedgerDataset.year == YEAR,
                LedgerDataset.status == DatasetStatus.active,
            ).values(status=DatasetStatus.superseded))
            base_id, staged_id = uuid.uuid4(), uuid.uuid4()
            session.add_all([
                LedgerDataset(
                    id=base_id,
                    project_id=PROJECT,
                    year=YEAR,
                    status=DatasetStatus.active,
                    source_type="test",
                    activated_at=datetime.now(timezone.utc),
                ),
                LedgerDataset(
                    id=staged_id,
                    project_id=PROJECT,
                    year=YEAR,
                    status=DatasetStatus.staged,
                    source_type="test",
                    previous_dataset_id=base_id,
                ),
            ])
            balance_id = uuid.uuid4()
            for dataset_id, month, amount, suffix in (
                (base_id, 1, "10", "base"),
                (base_id, 2, "20", "base"),
                (staged_id, 2, "200", "file"),
                (staged_id, 3, "300", "file"),
            ):
                session.add(TbLedger(
                    id=uuid.uuid4(),
                    project_id=PROJECT,
                    year=YEAR,
                    company_code="default",
                    voucher_date=date(YEAR, month, 1),
                    voucher_type="记",
                    voucher_no=f"LA-{month}-{suffix}",
                    account_code="1002",
                    account_name="银行存款",
                    debit_amount=Decimal(amount),
                    credit_amount=Decimal("0"),
                    dataset_id=dataset_id,
                    is_deleted=False,
                ))
            session.add(TbBalance(
                id=balance_id,
                project_id=PROJECT,
                year=YEAR,
                company_code="default",
                account_code="1002",
                account_name="银行存款",
                closing_balance=Decimal("30"),
                dataset_id=base_id,
                is_deleted=False,
            ))
            session.add(AccountChart(
                id=uuid.uuid4(),
                project_id=PROJECT,
                account_code="LA1002",
                account_name="【测试】银行存款",
                direction=AccountDirection.debit,
                level=1,
                category=AccountCategory.asset,
                source=AccountSource.client,
                dataset_id=base_id,
                is_deleted=False,
            ))
            session.add(DirectionOverride(
                id=uuid.uuid4(),
                project_id=PROJECT,
                dataset_id=base_id,
                table_name="tb_balance",
                record_id=balance_id,
                original_direction="credit",
                override_direction="debit",
                override_reason="【测试】跨版本重映射",
            ))
            await session.flush()

            report = await merge_into_staged(
                session,
                staged_id=staged_id,
                base_id=base_id,
                project_id=PROJECT,
                year=YEAR,
                strategy="overwrite",
                balance_carry_confirmed=True,
            )
            amounts = list((await session.scalars(
                sa.select(TbLedger.debit_amount)
                .where(TbLedger.dataset_id == staged_id, TbLedger.is_deleted == sa.false())
                .order_by(TbLedger.voucher_date)
            )).all())
            assert amounts == [Decimal("10"), Decimal("200"), Decimal("300")]
            assert await session.scalar(sa.select(sa.func.count()).select_from(TbLedger).where(
                TbLedger.dataset_id == base_id
            )) == 2
            new_balance = await session.scalar(sa.select(TbBalance.id).where(TbBalance.dataset_id == staged_id))
            new_override = await session.scalar(sa.select(DirectionOverride).where(
                DirectionOverride.dataset_id == staged_id
            ))
            assert new_balance != balance_id
            assert new_override is not None and new_override.record_id == new_balance
            assert report.tables["account_chart"].copied_rows == 1
            assert report.tables["tb_ledger"].actual_rows == 3
        finally:
            await session.close()
            await outer.rollback()
    await engine.dispose()
