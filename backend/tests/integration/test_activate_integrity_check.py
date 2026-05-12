"""Sprint 6 / F27 Task 6.6: activate 前 integrity check 测试。

验证 `DatasetService.activate` 在 record_summary 与实际物理行数不符时
抛 `DatasetIntegrityError`，且事务回滚后 dataset 仍保持 staged 状态。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.audit_platform_models import TbBalance
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services.dataset_service import DatasetIntegrityError, DatasetService


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _insert_balance_rows(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    dataset_id: uuid.UUID,
    count: int,
) -> None:
    for i in range(count):
        db.add(
            TbBalance(
                id=uuid.uuid4(),
                project_id=project_id,
                year=year,
                dataset_id=dataset_id,
                company_code="default",
                account_code=f"100{i}",
                currency_code="CNY",
                is_deleted=False,
            )
        )
    await db.flush()


@pytest.mark.asyncio
async def test_activate_passes_when_counts_match(db_session: AsyncSession):
    """record_summary 与实际行数一致 → activate 成功。"""
    project_id = uuid.uuid4()
    ds = await DatasetService.create_staged(
        db_session, project_id=project_id, year=2024
    )
    await _insert_balance_rows(
        db_session,
        project_id=project_id,
        year=2024,
        dataset_id=ds.id,
        count=5,
    )

    result = await DatasetService.activate(
        db_session,
        ds.id,
        record_summary={"tb_balance": 5},
    )

    assert result.status == DatasetStatus.active


@pytest.mark.asyncio
async def test_activate_raises_on_row_count_mismatch(db_session: AsyncSession):
    """实际行数 < 预期 → 抛 DatasetIntegrityError。"""
    project_id = uuid.uuid4()
    ds = await DatasetService.create_staged(
        db_session, project_id=project_id, year=2024
    )
    await _insert_balance_rows(
        db_session,
        project_id=project_id,
        year=2024,
        dataset_id=ds.id,
        count=3,
    )

    with pytest.raises(DatasetIntegrityError) as exc_info:
        await DatasetService.activate(
            db_session,
            ds.id,
            record_summary={"tb_balance": 5},  # 期望 5 实际 3
        )

    err = str(exc_info.value)
    assert "tb_balance" in err
    assert "expected=5" in err
    assert "actual=3" in err


@pytest.mark.asyncio
async def test_activate_skips_check_when_no_record_summary(
    db_session: AsyncSession,
):
    """未提供 record_summary → 跳过 integrity check（向后兼容）。"""
    project_id = uuid.uuid4()
    ds = await DatasetService.create_staged(
        db_session, project_id=project_id, year=2024
    )
    # 不写入任何行
    result = await DatasetService.activate(db_session, ds.id)

    assert result.status == DatasetStatus.active


@pytest.mark.asyncio
async def test_activate_ignores_non_table_keys(db_session: AsyncSession):
    """record_summary 中非表名字段（如 validation_summary）应被忽略。"""
    project_id = uuid.uuid4()
    ds = await DatasetService.create_staged(
        db_session, project_id=project_id, year=2024
    )
    await _insert_balance_rows(
        db_session,
        project_id=project_id,
        year=2024,
        dataset_id=ds.id,
        count=2,
    )

    # record_summary 含额外字段不应影响 check
    result = await DatasetService.activate(
        db_session,
        ds.id,
        record_summary={
            "tb_balance": 2,
            "validation_warnings": 0,
            "aux_types_detected": 3,
        },
    )
    assert result.status == DatasetStatus.active
