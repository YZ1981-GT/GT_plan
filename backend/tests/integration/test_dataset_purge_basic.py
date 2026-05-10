"""Sprint 10 Task 10.5: purge_old_datasets 基础逻辑集成测试。

不含 F53 retention_class 扩展，只验证纯 keep_count 保留策略：
- 同 (project_id, year) 下保留最近 N 个 superseded，其余物理 DELETE
- active / staged / rolled_back / failed 永不被 purge 动
- ActivationRecord 关联行同步删除
- Tb* 物理行按 dataset_id 清理
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# SQLite 兼容适配
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.audit_platform_models import TbBalance
from app.models.dataset_models import (
    ActivationRecord,
    ActivationType,
    DatasetStatus,
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


async def _insert_dataset(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    status: DatasetStatus,
    created_at: datetime,
) -> LedgerDataset:
    ds = LedgerDataset(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        status=status,
        created_at=created_at,
    )
    db.add(ds)
    await db.flush()
    # 添加一条占位 TbBalance 行，便于验证 cleanup
    db.add(
        TbBalance(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            dataset_id=ds.id,
            company_code="default",
            account_code="1001",
            currency_code="CNY",
            is_deleted=False,
        )
    )
    # 添加一条 ActivationRecord
    db.add(
        ActivationRecord(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            dataset_id=ds.id,
            action=ActivationType.activate,
        )
    )
    await db.flush()
    return ds


async def _count_datasets(
    db: AsyncSession, project_id: uuid.UUID, year: int, status: DatasetStatus
) -> int:
    result = await db.execute(
        sa.select(sa.func.count())
        .select_from(LedgerDataset)
        .where(
            LedgerDataset.project_id == project_id,
            LedgerDataset.year == year,
            LedgerDataset.status == status,
        )
    )
    return int(result.scalar_one())


async def _count_tb_rows(db: AsyncSession, dataset_id: uuid.UUID) -> int:
    result = await db.execute(
        sa.select(sa.func.count())
        .select_from(TbBalance)
        .where(TbBalance.dataset_id == dataset_id)
    )
    return int(result.scalar_one())


async def _count_activation_records(
    db: AsyncSession, dataset_id: uuid.UUID
) -> int:
    result = await db.execute(
        sa.select(sa.func.count())
        .select_from(ActivationRecord)
        .where(ActivationRecord.dataset_id == dataset_id)
    )
    return int(result.scalar_one())


# ===========================================================================
# 基础保留策略
# ===========================================================================
@pytest.mark.asyncio
async def test_purge_keeps_latest_n_superseded(db_session: AsyncSession):
    """N=3: 创建 5 个 superseded，purge 后只剩最近 3 个。"""
    project_id = uuid.uuid4()
    year = 2024
    base = datetime.now(timezone.utc) - timedelta(days=30)
    old_ids = []
    latest_ids = []
    for i in range(5):
        ds = await _insert_dataset(
            db_session,
            project_id=project_id,
            year=year,
            status=DatasetStatus.superseded,
            created_at=base + timedelta(days=i),
        )
        if i < 2:
            old_ids.append(ds.id)
        else:
            latest_ids.append(ds.id)

    result = await DatasetService.purge_old_datasets(
        db_session, project_id, keep_count=3
    )

    assert result["datasets_deleted"] == 2
    # 剩余 superseded 数 = 3
    remaining = await _count_datasets(
        db_session, project_id, year, DatasetStatus.superseded
    )
    assert remaining == 3
    # 被删除的 dataset 的 TbBalance 行数 = 0
    for old_id in old_ids:
        assert await _count_tb_rows(db_session, old_id) == 0
        assert await _count_activation_records(db_session, old_id) == 0
    # 保留的 dataset 行数/记录不变
    for keep_id in latest_ids:
        assert await _count_tb_rows(db_session, keep_id) == 1
        assert await _count_activation_records(db_session, keep_id) == 1


@pytest.mark.asyncio
async def test_purge_never_touches_active_or_staged(db_session: AsyncSession):
    """active / staged / rolled_back 状态应永不被 purge 删除。"""
    project_id = uuid.uuid4()
    year = 2024
    now = datetime.now(timezone.utc)

    active = await _insert_dataset(
        db_session, project_id=project_id, year=year,
        status=DatasetStatus.active, created_at=now,
    )
    staged = await _insert_dataset(
        db_session, project_id=project_id, year=year,
        status=DatasetStatus.staged, created_at=now - timedelta(hours=1),
    )
    rb = await _insert_dataset(
        db_session, project_id=project_id, year=year,
        status=DatasetStatus.rolled_back, created_at=now - timedelta(days=5),
    )
    # 10 个老 superseded，保留 1 个
    for i in range(10):
        await _insert_dataset(
            db_session, project_id=project_id, year=year,
            status=DatasetStatus.superseded,
            created_at=now - timedelta(days=30 + i),
        )

    await DatasetService.purge_old_datasets(
        db_session, project_id, keep_count=1
    )

    # active/staged/rolled_back 存活
    for ds in (active, staged, rb):
        assert await _count_tb_rows(db_session, ds.id) == 1
    # superseded 仅剩 1
    assert (
        await _count_datasets(db_session, project_id, year, DatasetStatus.superseded)
        == 1
    )


@pytest.mark.asyncio
async def test_purge_respects_year_scope(db_session: AsyncSession):
    """同 project 跨年度：2024/2025 各 5 个 superseded；只 purge 2024 保留 2。"""
    project_id = uuid.uuid4()
    base = datetime.now(timezone.utc) - timedelta(days=30)
    for yr in (2024, 2025):
        for i in range(5):
            await _insert_dataset(
                db_session, project_id=project_id, year=yr,
                status=DatasetStatus.superseded,
                created_at=base + timedelta(days=i),
            )

    result = await DatasetService.purge_old_datasets(
        db_session, project_id, year=2024, keep_count=2
    )

    assert result["datasets_deleted"] == 3
    assert (
        await _count_datasets(db_session, project_id, 2024, DatasetStatus.superseded)
        == 2
    )
    # 2025 未动
    assert (
        await _count_datasets(db_session, project_id, 2025, DatasetStatus.superseded)
        == 5
    )


@pytest.mark.asyncio
async def test_purge_keep_count_zero_deletes_all(db_session: AsyncSession):
    """keep_count=0 时，所有 superseded 都被删除。"""
    project_id = uuid.uuid4()
    year = 2024
    for i in range(3):
        await _insert_dataset(
            db_session, project_id=project_id, year=year,
            status=DatasetStatus.superseded,
            created_at=datetime.now(timezone.utc) - timedelta(days=i + 1),
        )

    result = await DatasetService.purge_old_datasets(
        db_session, project_id, keep_count=0
    )

    assert result["datasets_deleted"] == 3
    assert (
        await _count_datasets(db_session, project_id, year, DatasetStatus.superseded)
        == 0
    )


@pytest.mark.asyncio
async def test_purge_all_projects_walks_every_project(db_session: AsyncSession):
    """purge_all_projects 应扫描所有有 superseded 的项目。"""
    pid_a = uuid.uuid4()
    pid_b = uuid.uuid4()
    base = datetime.now(timezone.utc) - timedelta(days=20)
    for pid in (pid_a, pid_b):
        for i in range(4):
            await _insert_dataset(
                db_session, project_id=pid, year=2024,
                status=DatasetStatus.superseded,
                created_at=base + timedelta(days=i),
            )

    summary = await DatasetService.purge_all_projects(db_session, keep_count=2)

    assert summary["projects_processed"] == 2
    assert summary["datasets_deleted"] == 4  # 2 per project
    for pid in (pid_a, pid_b):
        assert (
            await _count_datasets(db_session, pid, 2024, DatasetStatus.superseded)
            == 2
        )
