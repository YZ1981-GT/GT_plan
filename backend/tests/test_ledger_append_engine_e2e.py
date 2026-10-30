"""两条生产导入引擎都在激活前调用同一个 staged 追加合并。"""
from __future__ import annotations

import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.audit_platform_models import TbBalance, TbLedger
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services.dataset_service import DatasetService

_FIXTURES = Path(__file__).parent / "fixtures/ledger_samples"
sys.path.insert(0, str(_FIXTURES))
from minimal_balance_ledger import create_minimal_sample  # type: ignore  # noqa: E402

PROJECT = uuid.UUID("44444444-5555-6666-7777-888888888888")
YEAR = 2025


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


async def _seed_base(factory, *, month: int) -> uuid.UUID:
    async with factory() as db:
        base = LedgerDataset(
            id=uuid.uuid4(),
            project_id=PROJECT,
            year=YEAR,
            status=DatasetStatus.active,
            source_type="test-base",
        )
        db.add(base)
        db.add(TbLedger(
            id=uuid.uuid4(),
            project_id=PROJECT,
            year=YEAR,
            company_code="COMP01",
            voucher_date=date(YEAR, month, 20),
            voucher_type="记",
            voucher_no=f"BASE-{month}",
            account_code="1002",
            account_name="银行存款",
            debit_amount=Decimal("1"),
            credit_amount=Decimal("0"),
            dataset_id=base.id,
            is_deleted=False,
        ))
        db.add(TbBalance(
            id=uuid.uuid4(),
            project_id=PROJECT,
            year=YEAR,
            company_code="COMP01",
            account_code="1002",
            account_name="银行存款",
            closing_balance=Decimal("1"),
            dataset_id=base.id,
            is_deleted=False,
        ))
        await db.commit()
        return base.id


async def _months(factory, dataset_id: uuid.UUID) -> set[int]:
    async with factory() as db:
        values = await db.scalars(sa.select(TbLedger.voucher_date).where(
            TbLedger.dataset_id == dataset_id,
            TbLedger.is_deleted == sa.false(),
        ))
        return {value.month for value in values}


async def _noop_rebuild(*_args, **_kwargs) -> int:
    return 0


@pytest.mark.asyncio
async def test_v2_pipeline_inherits_base_month_before_activation(factory, tmp_path):
    from app.services.ledger_import.pipeline import execute_pipeline

    base_id = await _seed_base(factory, month=4)
    sample = create_minimal_sample(tmp_path / "append.xlsx")
    with patch("app.core.database.async_session", factory), \
         patch("app.services.ledger_import.pipeline._detect_memory_pressure", return_value=True), \
         patch("app.services.smart_import_engine.rebuild_aux_balance_summary", _noop_rebuild):
        result = await execute_pipeline(
            job_id=uuid.uuid4(),
            project_id=PROJECT,
            year=YEAR,
            custom_mapping=None,
            created_by=None,
            file_sources=[(sample.name, sample)],
            force_activate=True,
            append_options={
                "strategy": "overwrite",
                "base_dataset_id": str(base_id),
                "balance_carry_confirmed": True,
                "no_base": False,
            },
        )
    assert result.append_report["base_dataset_id"] == str(base_id)
    assert result.append_report["tables"]["tb_ledger"]["copied_rows"] == 1
    assert result.voucher_diff_report["status"] == "ok"
    assert result.voucher_diff_report["summary"]["added"]["count"] > 0
    assert await _months(factory, result.dataset_id) == {1, 2, 3, 4, 12}
    async with factory() as db:
        active = await db.get(LedgerDataset, result.dataset_id)
        assert active.source_summary["voucher_diff"]["status"] == "ok"
        assert (await db.get(LedgerDataset, base_id)).status == DatasetStatus.superseded
        assert await db.scalar(sa.select(sa.func.count()).select_from(TbLedger).where(
            TbLedger.dataset_id == base_id
        )) == 1


@pytest.mark.asyncio
async def test_legacy_streaming_inherits_base_month_and_keeps_rows_visible(factory):
    from app.services.smart_import_engine import smart_import_streaming

    base_id = await _seed_base(factory, month=1)
    csv = (
        "记账日期,凭证号,凭证类型,摘要,科目编码,科目名称,借方,贷方\n"
        "2025-12-31,100,记,追加,1002,银行存款,10,0\n"
        "2025-12-31,100,记,追加,6001,费用,0,10\n"
    ).encode("utf-8-sig")
    async with factory() as db:
        with patch("app.services.smart_import_engine.rebuild_aux_balance_summary", _noop_rebuild):
            result = await smart_import_streaming(
                project_id=PROJECT,
                file_contents=[("append.csv", csv)],
                db=db,
                year_override=YEAR,
                force_activate=True,
                custom_mapping={"confirmed_mappings": [{
                    "file_name": "append.csv",
                    "sheet_name": "CSV",
                    "mappings": {
                        "记账日期": "voucher_date",
                        "凭证号": "voucher_no",
                        "凭证类型": "voucher_type",
                        "摘要": "summary",
                        "科目编码": "account_code",
                        "科目名称": "account_name",
                        "借方": "debit_amount",
                        "贷方": "credit_amount",
                    },
                }]},
                append_options={
                    "strategy": "overwrite",
                    "base_dataset_id": str(base_id),
                    "balance_carry_confirmed": True,
                    "no_base": False,
                },
            )
    dataset_id = uuid.UUID(result["dataset_id"])
    assert result["sheet_diagnostics"][0]["data_type"] == "ledger", result["sheet_diagnostics"]
    assert result["append"]["tables"]["tb_ledger"]["copied_rows"] == 1
    assert result["voucher_diff"]["status"] == "ok"
    assert result["voucher_diff"]["summary"]["added"]["count"] == 1
    assert await _months(factory, dataset_id) == {1, 12}, result
    async with factory() as db:
        assert await db.scalar(sa.select(sa.func.count()).select_from(TbLedger).where(
            TbLedger.dataset_id == dataset_id,
            TbLedger.is_deleted == sa.false(),
        )) == 3
        assert (await db.get(LedgerDataset, base_id)).status == DatasetStatus.superseded


@pytest.mark.asyncio
async def test_v2_validates_merged_dataset_not_only_uploaded_file(factory, tmp_path):
    from app.services.ledger_import.pipeline import execute_pipeline

    base_id = await _seed_base(factory, month=4)  # 单边 1 元凭证，完整数据集校验必须发现
    sample = create_minimal_sample(tmp_path / "append-validation.xlsx")

    async def merged_validation(db, *, dataset_id, **_kwargs):
        months = list((await db.scalars(sa.select(TbLedger.voucher_date).where(
            TbLedger.dataset_id == dataset_id,
            TbLedger.is_deleted == sa.false(),
        ))).all())
        assert {value.month for value in months} == {1, 2, 3, 4, 12}
        return [SimpleNamespace(to_dict=lambda: {
            "rule_code": "merged_probe",
            "severity": "fatal",
            "message": "合并后发现阻塞项",
        })]

    with patch("app.core.database.async_session", factory), \
         patch("app.services.ledger_import.pipeline._detect_memory_pressure", return_value=True), \
         patch("app.services.smart_import_engine.rebuild_aux_balance_summary", _noop_rebuild), \
         patch("app.services.import_validation_service.ImportValidationService.run_dataset_business_validation", merged_validation):
        with pytest.raises(RuntimeError, match="合并后完整账套校验失败"):
            await execute_pipeline(
                job_id=uuid.uuid4(),
                project_id=PROJECT,
                year=YEAR,
                custom_mapping=None,
                created_by=None,
                file_sources=[(sample.name, sample)],
                force_activate=False,
                append_options={
                    "strategy": "overwrite",
                    "base_dataset_id": str(base_id),
                    "balance_carry_confirmed": True,
                    "no_base": False,
                },
            )
    async with factory() as db:
        assert (await db.get(LedgerDataset, base_id)).status == DatasetStatus.active
        failed = list((await db.scalars(sa.select(LedgerDataset).where(
            LedgerDataset.previous_dataset_id == base_id,
            LedgerDataset.status == DatasetStatus.failed,
        ))).all())
        assert len(failed) == 1
        assert await db.scalar(sa.select(sa.func.count()).select_from(TbLedger).where(
            TbLedger.dataset_id == failed[0].id
        )) == 0
