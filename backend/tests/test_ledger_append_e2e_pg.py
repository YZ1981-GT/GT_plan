"""真 PG：1~11 月基准 + 11/12 月文件，覆盖/跳过后 12 月齐全并可回滚。"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.audit_platform_models import TbBalance, TbLedger
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services.dataset_service import DatasetService
from app.services.ledger_data_service import summarize_ledger_data
from app.services.ledger_dataset_merge import merge_into_staged
from app.services.ledger_dataset_voucher_diff import build_and_store_voucher_diff

pytestmark = pytest.mark.pg_only
PROJECT = uuid.UUID("ca8da212-8a0f-48b6-bd82-06660bd94380")
YEAR = 2025


def _lines(dataset_id: uuid.UUID, month: int, amount: int, suffix: str):
    common = {
        "project_id": PROJECT,
        "year": YEAR,
        "company_code": "default",
        "voucher_date": date(YEAR, month, 15),
        "voucher_type": "记",
        "voucher_no": f"LA-{month:02d}-{suffix}",
        "dataset_id": dataset_id,
        "is_deleted": False,
    }
    return [
        TbLedger(id=uuid.uuid4(), account_code="1002", account_name="银行存款",
                 debit_amount=Decimal(amount), credit_amount=Decimal(0), **common),
        TbLedger(id=uuid.uuid4(), account_code="6001", account_name="费用",
                 debit_amount=Decimal(0), credit_amount=Decimal(amount), **common),
    ]


async def _months(db: AsyncSession, dataset_id: uuid.UUID) -> set[int]:
    values = await db.scalars(sa.select(TbLedger.voucher_date).where(
        TbLedger.dataset_id == dataset_id,
        TbLedger.is_deleted == sa.false(),
    ))
    return {value.month for value in values}


@pytest.mark.asyncio
@pytest.mark.parametrize(("strategy", "month11_amount"), [("overwrite", 1100), ("skip", 110)])
async def test_append_twelve_months_and_rollback(strategy: str, month11_amount: int):
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        pytest.skip("需要真实 PostgreSQL")
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        outer = await conn.begin()
        db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            exists = await db.scalar(sa.text(
                "SELECT count(*) FROM projects WHERE id=:pid AND client_name LIKE '【测试】%'"
            ), {"pid": PROJECT})
            if not exists:
                pytest.skip("凭证【测试】项目不存在")
            await db.execute(sa.update(LedgerDataset).where(
                LedgerDataset.project_id == PROJECT,
                LedgerDataset.year == YEAR,
                LedgerDataset.status == DatasetStatus.active,
            ).values(status=DatasetStatus.superseded))
            base_id = uuid.uuid4()
            base = LedgerDataset(
                id=base_id, project_id=PROJECT, year=YEAR,
                status=DatasetStatus.active, source_type="test-base",
                activated_at=datetime.now(timezone.utc),
            )
            db.add(base)
            for month in range(1, 12):
                db.add_all(_lines(base_id, month, month * 10, "base"))
            db.add(TbBalance(
                id=uuid.uuid4(), project_id=PROJECT, year=YEAR, company_code="default",
                account_code="1002", account_name="银行存款", closing_balance=Decimal("660"),
                dataset_id=base_id, is_deleted=False,
            ))
            await db.flush()
            base_count = await db.scalar(sa.select(sa.func.count()).select_from(TbLedger).where(
                TbLedger.dataset_id == base_id
            ))
            base_debit = await db.scalar(sa.select(sa.func.sum(TbLedger.debit_amount)).where(
                TbLedger.dataset_id == base_id
            ))

            staged = await DatasetService.create_staged(db, PROJECT, YEAR, source_type="append-test")
            db.add_all(_lines(staged.id, 11, 1100, "base"))
            db.add_all(_lines(staged.id, 12, 1200, "file"))
            await db.flush()
            report = await merge_into_staged(
                db,
                staged_id=staged.id,
                base_id=base_id,
                project_id=PROJECT,
                year=YEAR,
                strategy=strategy,
                balance_carry_confirmed=True,
            )
            diff = await build_and_store_voucher_diff(
                db,
                staged_dataset_id=staged.id,
                base_dataset_id=base_id,
            )
            await DatasetService.activate(
                db,
                staged.id,
                record_summary={name: item.actual_rows for name, item in report.tables.items() if name.startswith("tb_")},
                expected_active_dataset_id=base_id,
            )
            await db.flush()

            assert await _months(db, staged.id) == set(range(1, 13))
            month11 = await db.scalar(sa.select(sa.func.sum(TbLedger.debit_amount)).where(
                TbLedger.dataset_id == staged.id,
                sa.extract("month", TbLedger.voucher_date) == 11,
            ))
            assert month11 == Decimal(month11_amount)
            assert diff["status"] == "ok"
            assert diff["summary"]["added"]["count"] == 1
            assert diff["summary"]["deleted"]["count"] == 0
            assert diff["summary"]["modified"]["count"] == (1 if strategy == "overwrite" else 0)
            assert await db.scalar(sa.select(sa.func.count()).select_from(TbLedger).where(
                TbLedger.dataset_id == base_id
            )) == base_count
            assert await db.scalar(sa.select(sa.func.sum(TbLedger.debit_amount)).where(
                TbLedger.dataset_id == base_id
            )) == base_debit
            summary = await summarize_ledger_data(db, project_id=PROJECT, year=YEAR)
            active_summary = summary["datasets"][YEAR]["source_summary"]
            assert active_summary["append"]["strategy"] == strategy
            assert active_summary["voucher_diff"]["status"] == "ok"

            with patch("app.services.import_queue_service.ImportQueueService.try_acquire_action_lock", return_value=True), \
                 patch("app.services.import_queue_service.ImportQueueService.release_action_lock", return_value=None):
                restored = await DatasetService.rollback(db, PROJECT, YEAR, reason="【测试】追加回滚")
            await db.flush()
            assert restored is not None and restored.id == base_id
            assert (await db.get(LedgerDataset, base_id)).status == DatasetStatus.active
            assert (await db.get(LedgerDataset, staged.id)).status == DatasetStatus.rolled_back
            assert await _months(db, base_id) == set(range(1, 12))
            assert await db.scalar(sa.select(sa.func.count()).select_from(TbLedger).where(
                TbLedger.dataset_id == base_id
            )) == base_count
            assert await db.scalar(sa.select(sa.func.sum(TbLedger.debit_amount)).where(
                TbLedger.dataset_id == base_id
            )) == base_debit
        finally:
            await db.close()
            await outer.rollback()
    await engine.dispose()
