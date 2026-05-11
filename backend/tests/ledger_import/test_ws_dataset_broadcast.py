"""Sprint 5.5: WebSocket 数据集广播流程测试

验证 DatasetService.activate / rollback 在同一事务中写入 event_outbox 记录，
确保后续 outbox_replay_worker 可以消费并广播给项目组成员。

测试策略：
- SQLite in-memory DB（复用邻居 fixture 模板）
- 不测真实 WebSocket 连接，只验证 outbox 记录正确写入
"""
from __future__ import annotations

import uuid
from datetime import date

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
from app.models.dataset_models import (
    DatasetStatus,
    ImportEventOutbox,
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


async def _seed_dataset(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    status: DatasetStatus = DatasetStatus.staged,
    previous_dataset_id: uuid.UUID | None = None,
) -> LedgerDataset:
    dataset = LedgerDataset(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        status=status,
        source_type="import",
        previous_dataset_id=previous_dataset_id,
    )
    db.add(dataset)
    await db.flush()
    # 插入少量数据行以满足 activate 需要
    for i in range(2):
        db.add(TbBalance(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            dataset_id=dataset.id,
            company_code="001",
            account_code=f"100{i}",
            account_name=f"acc-{i}",
            currency_code="CNY",
            is_deleted=False,
        ))
    for i in range(3):
        db.add(TbLedger(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            dataset_id=dataset.id,
            company_code="001",
            voucher_date=date(year, 1, 1),
            voucher_no=f"V{i:03d}",
            account_code=f"100{i % 2}",
            currency_code="CNY",
            is_deleted=False,
        ))
    await db.flush()
    return dataset


# ===========================================================================
# Case 1: activate 写入 outbox 事件
# ===========================================================================


@pytest.mark.asyncio
async def test_activate_creates_outbox_event(db_session: AsyncSession):
    """activate 应在 event_outbox 中插入 LEDGER_DATASET_ACTIVATED 事件。"""
    project_id = uuid.uuid4()
    year = 2024
    staged = await _seed_dataset(db_session, project_id=project_id, year=year)

    await DatasetService.activate(db_session, staged.id)

    result = await db_session.execute(
        sa.select(ImportEventOutbox).where(
            ImportEventOutbox.project_id == project_id,
        )
    )
    outbox_rows = result.scalars().all()
    assert len(outbox_rows) >= 1
    activated_events = [
        r for r in outbox_rows if "ACTIVATED" in r.event_type.upper()
    ]
    assert len(activated_events) == 1


# ===========================================================================
# Case 2: rollback 写入 outbox 事件
# ===========================================================================


@pytest.mark.asyncio
async def test_rollback_creates_outbox_event(db_session: AsyncSession):
    """rollback 应在 event_outbox 中插入 ROLLED_BACK 事件。"""
    project_id = uuid.uuid4()
    year = 2024

    # 先创建 V1 并激活
    v1 = await _seed_dataset(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, v1.id)

    # 创建 V2 并激活（V1 → superseded）
    v2 = await _seed_dataset(
        db_session, project_id=project_id, year=year,
        previous_dataset_id=v1.id,
    )
    await DatasetService.activate(db_session, v2.id)

    # 回滚 V2 → V1
    restored = await DatasetService.rollback(db_session, project_id, year)
    assert restored is not None

    result = await db_session.execute(
        sa.select(ImportEventOutbox).where(
            ImportEventOutbox.project_id == project_id,
        )
    )
    outbox_rows = result.scalars().all()
    rollback_events = [
        r for r in outbox_rows if "ROLLED_BACK" in r.event_type.upper()
    ]
    assert len(rollback_events) == 1


# ===========================================================================
# Case 3: outbox 事件包含 project_id
# ===========================================================================


@pytest.mark.asyncio
async def test_outbox_event_contains_project_id(db_session: AsyncSession):
    """outbox 事件的 project_id 字段应与操作的项目一致。"""
    project_id = uuid.uuid4()
    year = 2024
    staged = await _seed_dataset(db_session, project_id=project_id, year=year)

    await DatasetService.activate(db_session, staged.id)

    result = await db_session.execute(
        sa.select(ImportEventOutbox).where(
            ImportEventOutbox.project_id == project_id,
        )
    )
    outbox_row = result.scalars().first()
    assert outbox_row is not None
    assert outbox_row.project_id == project_id


# ===========================================================================
# Case 4: outbox 事件 payload 包含 dataset_id
# ===========================================================================


@pytest.mark.asyncio
async def test_outbox_event_payload_has_dataset_id(db_session: AsyncSession):
    """outbox 事件的 payload 应包含 dataset_id 信息。"""
    project_id = uuid.uuid4()
    year = 2024
    staged = await _seed_dataset(db_session, project_id=project_id, year=year)

    dataset = await DatasetService.activate(db_session, staged.id)

    outbox_id = getattr(dataset, "_activation_outbox_id", None)
    assert outbox_id is not None, "activate 应把 outbox id 挂到 dataset 上"

    result = await db_session.execute(
        sa.select(ImportEventOutbox).where(ImportEventOutbox.id == outbox_id)
    )
    outbox_row = result.scalar_one_or_none()
    assert outbox_row is not None
    assert outbox_row.payload is not None
    # payload 应包含 dataset_id（可能是 activated_dataset_id 或 dataset_id 键）
    payload_str = str(outbox_row.payload)
    assert str(dataset.id) in payload_str, (
        f"payload 应包含 dataset_id={dataset.id}"
    )


# ===========================================================================
# Case 5: rollback outbox payload 包含 rolled_back_dataset_id
# ===========================================================================


@pytest.mark.asyncio
async def test_rollback_outbox_payload_has_dataset_ids(db_session: AsyncSession):
    """rollback outbox 事件 payload 应包含 rolled_back 和 restored dataset_id。"""
    project_id = uuid.uuid4()
    year = 2024

    v1 = await _seed_dataset(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, v1.id)

    v2 = await _seed_dataset(
        db_session, project_id=project_id, year=year,
        previous_dataset_id=v1.id,
    )
    await DatasetService.activate(db_session, v2.id)

    restored = await DatasetService.rollback(db_session, project_id, year)
    assert restored is not None

    rollback_outbox_id = getattr(restored, "_rollback_outbox_id", None)
    assert rollback_outbox_id is not None

    result = await db_session.execute(
        sa.select(ImportEventOutbox).where(
            ImportEventOutbox.id == rollback_outbox_id
        )
    )
    outbox_row = result.scalar_one_or_none()
    assert outbox_row is not None
    assert outbox_row.payload is not None
    # 应包含 rolled_back_dataset_id 和 restored_dataset_id
    assert "rolled_back_dataset_id" in outbox_row.payload
    assert "restored_dataset_id" in outbox_row.payload
    assert outbox_row.payload["rolled_back_dataset_id"] == str(v2.id)
    assert outbox_row.payload["restored_dataset_id"] == str(v1.id)


# ===========================================================================
# Case 6: activate outbox 事件包含 year 字段
# ===========================================================================


@pytest.mark.asyncio
async def test_activate_outbox_contains_year(db_session: AsyncSession):
    """activate outbox 事件应包含 year 字段。"""
    project_id = uuid.uuid4()
    year = 2025
    staged = await _seed_dataset(db_session, project_id=project_id, year=year)

    await DatasetService.activate(db_session, staged.id)

    result = await db_session.execute(
        sa.select(ImportEventOutbox).where(
            ImportEventOutbox.project_id == project_id,
        )
    )
    outbox_row = result.scalars().first()
    assert outbox_row is not None
    assert outbox_row.year == year
