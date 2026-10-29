"""凭证差异报告 PostgreSQL 单次聚合查询。"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.audit_platform_models import TbLedger
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services import ledger_dataset_voucher_diff as diff_module
from app.services.ledger_dataset_voucher_diff import build_and_store_voucher_diff, build_voucher_diff

pytestmark = pytest.mark.pg_only
PROJECT = uuid.UUID("ca8da212-8a0f-48b6-bd82-06660bd94380")
YEAR = 2025


def _row(dataset, month, no, account, debit, credit, vtype="记"):
    return TbLedger(
        id=uuid.uuid4(), project_id=PROJECT, year=YEAR, company_code="default",
        voucher_date=date(YEAR, month, 1), voucher_type=vtype, voucher_no=no,
        account_code=account, account_name=account,
        debit_amount=Decimal(str(debit)), credit_amount=Decimal(str(credit)),
        dataset_id=dataset, is_deleted=False,
    )


@pytest.mark.asyncio
async def test_pg_diff_keeps_voucher_type_separate_and_detects_same_total_change():
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
            base, new = uuid.uuid4(), uuid.uuid4()
            db.add_all([
                _row(base, 1, "001", "1002", 10, 0),
                _row(base, 1, "001", "1003", 20, 0),
                _row(base, 1, "001", "6001", 0, 30),
                _row(new, 1, "001", "1002", 15, 0),
                _row(new, 1, "001", "1003", 15, 0),
                _row(new, 1, "001", "6001", 0, 30),
                _row(base, 1, "001", "1002", 8, 0, "ZZ"),
                _row(new, 1, "001", "1002", 8, 0, "ZZ"),
                _row(base, 2, "002", "1002", 20, 0),
                _row(new, 3, "003", "1002", 30, 0),
            ])
            await db.flush()
            report = await build_voucher_diff(db, base_dataset_id=base, new_dataset_id=new)
            assert {kind: report["summary"][kind]["count"] for kind in ("added", "deleted", "modified")} == {
                "added": 1, "deleted": 1, "modified": 1,
            }
            assert report["summary"]["modified"]["net_amount_change"] == "0.00"
            assert len(report["samples"]["modified"]) == 1
            assert "记" in report["samples"]["modified"][0]["voucher_key"]
        finally:
            await db.close()
            await outer.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_pg_diff_failure_rolls_back_savepoint_and_stores_reason(monkeypatch):
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        pytest.skip("需要真实 PostgreSQL")
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        outer = await conn.begin()
        db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            dataset = LedgerDataset(
                id=uuid.uuid4(), project_id=PROJECT, year=YEAR,
                status=DatasetStatus.staged, source_type="test-diff-failure",
            )
            db.add(dataset)
            await db.flush()

            async def broken(db, **_kwargs):
                await db.execute(sa.text("SELECT * FROM definitely_missing_diff_table"))

            monkeypatch.setattr(diff_module, "build_voucher_diff", broken)
            report = await build_and_store_voucher_diff(
                db,
                staged_dataset_id=dataset.id,
                base_dataset_id=uuid.uuid4(),
            )
            assert report["status"] == "failed"
            assert "definitely_missing_diff_table" in report["reason"]
            await db.flush()
            stored = await db.get(LedgerDataset, dataset.id)
            assert stored.source_summary["voucher_diff"] == report
        finally:
            await db.close()
            await outer.rollback()
    await engine.dispose()
