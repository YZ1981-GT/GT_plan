"""凭证差异报告按完整凭证键和分录签名比较两个 dataset。"""
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

from app.models.audit_platform_models import TbLedger
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services import ledger_dataset_voucher_diff as diff_module
from app.services.ledger_dataset_voucher_diff import build_and_store_voucher_diff, build_voucher_diff
from tests.advanced_query_linkage.builder_tables import create_tables_with_closure

PROJECT = uuid.UUID("55555555-6666-7777-8888-999999999999")
BASE = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
NEW = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
YEAR = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(create_tables_with_closure, (TbLedger.__table__, LedgerDataset.__table__))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add_all([
            LedgerDataset(id=BASE, project_id=PROJECT, year=YEAR, status=DatasetStatus.active, source_type="base"),
            LedgerDataset(id=NEW, project_id=PROJECT, year=YEAR, status=DatasetStatus.staged, source_type="new"),
        ])
        await session.flush()
        yield session
    await engine.dispose()


def _line(dataset, month, no, account, debit, credit, *, vtype="记", company="C1"):
    return TbLedger(
        id=uuid.uuid4(), project_id=PROJECT, year=YEAR, company_code=company,
        voucher_date=date(YEAR, month, 1), voucher_type=vtype, voucher_no=no,
        account_code=account, account_name=account,
        debit_amount=Decimal(str(debit)), credit_amount=Decimal(str(credit)),
        dataset_id=dataset, is_deleted=False,
    )


@pytest.mark.asyncio
async def test_added_deleted_modified_and_voucher_type_identity(db: AsyncSession):
    db.add_all([
        # 未变
        _line(BASE, 1, "001", "1002", 10, 0),
        _line(BASE, 1, "001", "6001", 0, 10),
        _line(NEW, 1, "001", "1002", 10, 0),
        _line(NEW, 1, "001", "6001", 0, 10),
        # 删除 / 新增
        _line(BASE, 2, "002", "1002", 20, 0),
        _line(NEW, 3, "003", "1002", 30, 0),
        # 修改：总金额也变化
        _line(BASE, 4, "004", "1002", 40, 0, vtype="FY"),
        _line(NEW, 4, "004", "1002", 45, 0, vtype="FY"),
        # 同日同号但另一凭证字不应跟 FY 合并，且保持未变
        _line(BASE, 4, "004", "1002", 9, 0, vtype="ZZ"),
        _line(NEW, 4, "004", "1002", 9, 0, vtype="ZZ"),
    ])
    await db.flush()
    report = await build_voucher_diff(db, base_dataset_id=BASE, new_dataset_id=NEW)

    assert report["summary"] == {
        "added": {"count": 1, "amount": "30.00", "net_amount_change": "30.00"},
        "deleted": {"count": 1, "amount": "20.00", "net_amount_change": "-20.00"},
        "modified": {"count": 1, "amount": "45.00", "net_amount_change": "5.00"},
    }
    assert set(report["by_month"]) == {"2", "3", "4"}
    assert report["by_month"]["4"]["modified"]["count"] == 1
    assert len(report["samples"]["modified"]) == 1
    assert "FY" in report["samples"]["modified"][0]["voucher_key"]
    assert all("ZZ" not in row["voucher_key"] for rows in report["samples"].values() for row in rows)


@pytest.mark.asyncio
async def test_line_signature_detects_structure_change_with_same_total(db: AsyncSession):
    db.add_all([
        _line(BASE, 5, "005", "1002", 10, 0),
        _line(BASE, 5, "005", "6001", 0, 10),
        _line(NEW, 5, "005", "1003", 10, 0),
        _line(NEW, 5, "005", "6001", 0, 10),
    ])
    await db.flush()
    report = await build_voucher_diff(db, base_dataset_id=BASE, new_dataset_id=NEW)
    assert report["summary"]["modified"] == {
        "count": 1,
        "amount": "10.00",
        "net_amount_change": "0.00",
    }


@pytest.mark.asyncio
async def test_samples_are_capped_at_twenty_per_kind(db: AsyncSession):
    db.add_all([
        _line(NEW, 6, f"N{i:02d}", "1002", i + 1, 0)
        for i in range(25)
    ])
    await db.flush()
    report = await build_voucher_diff(db, base_dataset_id=BASE, new_dataset_id=NEW)
    assert report["summary"]["added"]["count"] == 25
    assert len(report["samples"]["added"]) == 20


@pytest.mark.asyncio
async def test_store_is_fail_open_but_records_reason(db: AsyncSession, monkeypatch):
    async def fail(*_args, **_kwargs):
        raise RuntimeError("diff unavailable")

    monkeypatch.setattr(diff_module, "build_voucher_diff", fail)
    report = await build_and_store_voucher_diff(
        db,
        staged_dataset_id=NEW,
        base_dataset_id=BASE,
    )
    assert report == {"status": "failed", "reason": "diff unavailable"}
    dataset = await db.get(LedgerDataset, NEW)
    assert dataset.source_summary["voucher_diff"] == report
