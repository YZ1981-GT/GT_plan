"""F1 / Sprint 11.2: `DatasetService.rollback` 视图重构单元测试

与 `integration/test_dataset_rollback_view_refactor.py` 的区别：
- 那份测试（集成）覆盖 rollback 后查询层仍能通过 `get_active_filter` 看到 V1 数据
- 本测试（单元）聚焦 `DatasetService.rollback` 的 **行为契约**：
    1. 元数据翻转：current active → rolled_back，previous → active
    2. Tb* 物理行 UPDATE 计数 = 0（B' 不动数据行）
    3. ActivationRecord 写入（action=rollback + 审计字段）
    4. DATASET_ROLLED_BACK 事件入 outbox（含 old_dataset_id / new_active_dataset_id）
    5. 无 previous 时返回 None 不抛异常
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
    ActivationRecord,
    ActivationType,
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


async def _seed_active_chain(
    db: AsyncSession, *, project_id: uuid.UUID, year: int,
) -> tuple[LedgerDataset, LedgerDataset]:
    """建两个 dataset 并按次序激活（V1 active → V2 active / V1 superseded）。

    为每个 dataset 写入 2 行 TbBalance + 2 行 TbLedger，is_deleted=false。
    """
    v1 = await DatasetService.create_staged(db, project_id=project_id, year=year)
    # 写入 V1 物理行
    for i in range(2):
        db.add(TbBalance(
            id=uuid.uuid4(), project_id=project_id, year=year,
            dataset_id=v1.id, company_code="001",
            account_code=f"100{i}", account_name=f"V1-{i}",
            currency_code="CNY", is_deleted=False,
        ))
        db.add(TbLedger(
            id=uuid.uuid4(), project_id=project_id, year=year,
            dataset_id=v1.id, company_code="001",
            voucher_date=date(year, 1, 1), voucher_no=f"V1-{i:03d}",
            account_code=f"100{i}", currency_code="CNY", is_deleted=False,
        ))
    await db.flush()
    await DatasetService.activate(db, v1.id, reason="V1 激活")
    await db.flush()

    v2 = await DatasetService.create_staged(db, project_id=project_id, year=year)
    for i in range(2):
        db.add(TbBalance(
            id=uuid.uuid4(), project_id=project_id, year=year,
            dataset_id=v2.id, company_code="001",
            account_code=f"200{i}", account_name=f"V2-{i}",
            currency_code="CNY", is_deleted=False,
        ))
        db.add(TbLedger(
            id=uuid.uuid4(), project_id=project_id, year=year,
            dataset_id=v2.id, company_code="001",
            voucher_date=date(year, 2, 1), voucher_no=f"V2-{i:03d}",
            account_code=f"200{i}", currency_code="CNY", is_deleted=False,
        ))
    await db.flush()
    await DatasetService.activate(db, v2.id, reason="V2 激活")
    await db.flush()
    await db.refresh(v1)
    await db.refresh(v2)
    return v1, v2


# ===========================================================================
# Case 1: rollback 语义 —— metadata 翻转 + 物理行不变
# ===========================================================================


@pytest.mark.asyncio
async def test_rollback_flips_metadata_without_updating_rows(
    db_session: AsyncSession,
):
    project_id = uuid.uuid4()
    year = 2024
    v1, v2 = await _seed_active_chain(
        db_session, project_id=project_id, year=year,
    )
    assert v1.status == DatasetStatus.superseded
    assert v2.status == DatasetStatus.active

    # 先记录每张表的物理行数（分 dataset）
    async def _counts(dataset_id: uuid.UUID) -> tuple[int, int]:
        bal = (
            await db_session.execute(
                sa.select(sa.func.count())
                .select_from(TbBalance)
                .where(TbBalance.dataset_id == dataset_id)
            )
        ).scalar_one()
        led = (
            await db_session.execute(
                sa.select(sa.func.count())
                .select_from(TbLedger)
                .where(TbLedger.dataset_id == dataset_id)
            )
        ).scalar_one()
        return int(bal), int(led)

    v1_before = await _counts(v1.id)
    v2_before = await _counts(v2.id)

    restored = await DatasetService.rollback(
        db_session, project_id, year,
        performed_by=None,
        reason="单元测试回滚",
        ip_address="10.0.0.3",
    )
    assert restored is not None
    assert restored.id == v1.id

    await db_session.refresh(v1)
    await db_session.refresh(v2)
    assert v1.status == DatasetStatus.active
    assert v2.status == DatasetStatus.rolled_back

    v1_after = await _counts(v1.id)
    v2_after = await _counts(v2.id)
    assert v1_before == v1_after, "rollback 不应改动 V1 物理行"
    assert v2_before == v2_after, "rollback 不应改动 V2 物理行"

    # is_deleted 仍为 false（无 UPDATE）
    async def _has_any_deleted(dataset_id: uuid.UUID) -> bool:
        for tbl_model in (TbBalance, TbLedger):
            res = await db_session.execute(
                sa.select(sa.func.count())
                .select_from(tbl_model)
                .where(
                    tbl_model.dataset_id == dataset_id,
                    tbl_model.is_deleted == sa.true(),
                )
            )
            if int(res.scalar_one()) > 0:
                return True
        return False

    assert not await _has_any_deleted(v1.id)
    assert not await _has_any_deleted(v2.id)


# ===========================================================================
# Case 2: ActivationRecord(action=rollback) + 审计字段
# ===========================================================================


@pytest.mark.asyncio
async def test_rollback_writes_activation_record(db_session: AsyncSession):
    project_id = uuid.uuid4()
    year = 2024
    actor = uuid.uuid4()

    v1, v2 = await _seed_active_chain(
        db_session, project_id=project_id, year=year,
    )
    await DatasetService.rollback(
        db_session, project_id, year,
        performed_by=actor,
        reason="复核发现数据异常",
        ip_address="10.0.0.9",
    )

    record = (
        await db_session.execute(
            sa.select(ActivationRecord)
            .where(
                ActivationRecord.action == ActivationType.rollback,
                ActivationRecord.dataset_id == v1.id,
            )
        )
    ).scalars().first()
    assert record is not None, "rollback 应创建 ActivationRecord(action=rollback)"
    assert record.previous_dataset_id == v2.id
    assert record.performed_by == actor
    assert record.reason == "复核发现数据异常"
    assert record.ip_address == "10.0.0.9"
    assert record.duration_ms is not None and record.duration_ms >= 0


# ===========================================================================
# Case 3: DATASET_ROLLED_BACK 事件入 outbox
# ===========================================================================


@pytest.mark.asyncio
async def test_rollback_enqueues_outbox_event(db_session: AsyncSession):
    from app.models.audit_platform_schemas import EventType

    project_id = uuid.uuid4()
    year = 2024
    v1, v2 = await _seed_active_chain(
        db_session, project_id=project_id, year=year,
    )
    restored = await DatasetService.rollback(
        db_session, project_id, year, reason="自动化测试",
    )
    assert restored is not None

    outbox_rows = (
        await db_session.execute(
            sa.select(ImportEventOutbox).where(
                ImportEventOutbox.project_id == project_id,
                ImportEventOutbox.event_type == EventType.LEDGER_DATASET_ROLLED_BACK,
            )
        )
    ).scalars().all()
    assert len(outbox_rows) >= 1
    row = outbox_rows[-1]
    payload = row.payload or {}
    assert payload.get("old_dataset_id") == str(v2.id)
    assert payload.get("new_active_dataset_id") == str(v1.id)
    # 兼容历史键
    assert payload.get("rolled_back_dataset_id") == str(v2.id)
    assert payload.get("restored_dataset_id") == str(v1.id)


# ===========================================================================
# Case 4: 首版无 previous → rollback 返回 None
# ===========================================================================


@pytest.mark.asyncio
async def test_rollback_returns_none_without_previous(db_session: AsyncSession):
    project_id = uuid.uuid4()
    year = 2024
    v1 = await DatasetService.create_staged(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, v1.id)
    await db_session.flush()

    restored = await DatasetService.rollback(db_session, project_id, year)
    assert restored is None

    await db_session.refresh(v1)
    assert v1.status == DatasetStatus.active


# ===========================================================================
# Case 5: 无 active dataset 时返回 None
# ===========================================================================


@pytest.mark.asyncio
async def test_rollback_no_active_returns_none(db_session: AsyncSession):
    project_id = uuid.uuid4()
    year = 2024
    # 不建任何 dataset
    restored = await DatasetService.rollback(db_session, project_id, year)
    assert restored is None
