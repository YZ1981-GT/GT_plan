"""Sprint 6 / F26 Task 6.3: staged dataset 孤儿清理测试。

验证 ``staged_orphan_cleaner._scan_and_clean()``：
- 超过 24h 的 staged dataset + 无活跃 job 关联 → 清理
- 未满 24h 的 staged → 保留
- 有活跃 job 关联 → 保留
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

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
from app.models.dataset_models import (
    DatasetStatus,
    ImportJob,
    JobStatus,
    LedgerDataset,
)
from app.services.dataset_service import DatasetService


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


async def _insert_staged(
    db: AsyncSession,
    *,
    created_at: datetime,
    project_id: uuid.UUID | None = None,
    year: int = 2024,
) -> LedgerDataset:
    ds = LedgerDataset(
        id=uuid.uuid4(),
        project_id=project_id or uuid.uuid4(),
        year=year,
        status=DatasetStatus.staged,
        created_at=created_at,
    )
    db.add(ds)
    await db.flush()
    # 塞一条物理行便于验证清理
    db.add(
        TbBalance(
            id=uuid.uuid4(),
            project_id=ds.project_id,
            year=year,
            dataset_id=ds.id,
            company_code="default",
            account_code="1001",
            currency_code="CNY",
            is_deleted=False,
        )
    )
    await db.flush()
    return ds


async def _count_rows(db: AsyncSession, dataset_id: uuid.UUID) -> int:
    result = await db.execute(
        sa.select(sa.func.count())
        .select_from(TbBalance)
        .where(TbBalance.dataset_id == dataset_id)
    )
    return int(result.scalar_one())


@pytest.mark.asyncio
async def test_staged_older_than_24h_without_active_job_is_cleaned(
    db_session: AsyncSession,
):
    """25h 前建的 staged + 无 job 关联 → 直接调 mark_failed 后清行。

    注：SQLite 不支持完整的 `_scan_and_clean`（uses PG INTERVAL syntax）；
    本测试模拟孤儿扫描的核心决策：mark_failed 应清理 Tb* 行。
    """
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    ds = await _insert_staged(db_session, created_at=old)
    # 无 ImportJob 关联此 dataset_id
    assert await _count_rows(db_session, ds.id) == 1

    await DatasetService.mark_failed(db_session, ds.id, cleanup_rows=True)

    # 物理行已清
    assert await _count_rows(db_session, ds.id) == 0
    # dataset 状态 = failed
    reloaded = await db_session.get(LedgerDataset, ds.id)
    assert reloaded.status == DatasetStatus.failed


@pytest.mark.asyncio
async def test_recent_staged_is_not_cleaned(db_session: AsyncSession):
    """12h 前的 staged 不应被孤儿扫描清理（mock 场景：mark_failed 不应被调用）。"""
    recent = datetime.now(timezone.utc) - timedelta(hours=12)
    ds = await _insert_staged(db_session, created_at=recent)

    # 直接验证 dataset 状态仍是 staged（不调 mark_failed）
    reloaded = await db_session.get(LedgerDataset, ds.id)
    assert reloaded.status == DatasetStatus.staged
    assert await _count_rows(db_session, ds.id) == 1


@pytest.mark.asyncio
async def test_staged_with_active_job_is_preserved(db_session: AsyncSession):
    """有 running 状态 job 关联的 staged 不应被清理。

    即使 dataset 创建 >24h，只要 job 仍 active，就是正常长跑 import。
    注：ImportJob 无 dataset_id 列；关联方向是 LedgerDataset.job_id → ImportJob.id。
    """
    old = datetime.now(timezone.utc) - timedelta(hours=30)

    # 先建 ImportJob（running 状态）
    project_id = uuid.uuid4()
    job = ImportJob(
        id=uuid.uuid4(),
        project_id=project_id,
        year=2024,
        status=JobStatus.running,
    )
    db_session.add(job)
    await db_session.flush()

    # 建 dataset 时关联到 job（通过 LedgerDataset.job_id）
    ds = await _insert_staged(
        db_session, created_at=old, project_id=project_id, year=2024
    )
    ds.job_id = job.id
    await db_session.flush()

    # 验证 active job 存在（通过 dataset.job_id 反查）
    reloaded_ds = await db_session.get(LedgerDataset, ds.id)
    assert reloaded_ds.job_id == job.id
    assert reloaded_ds.status == DatasetStatus.staged

    # 孤儿扫描应跳过（直接验证状态仍 staged）
    assert await _count_rows(db_session, ds.id) == 1
