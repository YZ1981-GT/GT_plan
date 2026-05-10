"""F1 / Sprint 11.1: `DatasetService.activate` 视图重构单元测试

背景（B' 视图重构 / ADR-002）：
- 激活新数据集只改 ``ledger_datasets.status``（staged → active / 旧 active → superseded）
- **不再 UPDATE Tb* 物理行的 is_deleted 字段**（废弃了老 architecture 的批量行更新）
- 127s activate → <1s metadata 切换

本文件核心断言：
1. 旧 active → superseded，新 staged → active
2. 激活前后 Tb* 物理行 is_deleted **保持不变**（证明没有发生 UPDATE 风暴）
3. Idempotency：已 active 的 dataset 再 activate → 返回同一 dataset，状态不动、不新增
   ActivationRecord
4. ActivationRecord 正确写入并含审计字段（action/performed_by/reason/row_counts）
5. 激活事件进入 outbox（LEDGER_DATASET_ACTIVATED）
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
from app.models.audit_platform_models import TbAuxLedger, TbBalance, TbLedger
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


# ---------------------------------------------------------------------------
# 工具：插入 staged 四表行（B' 架构下 is_deleted=false）
# ---------------------------------------------------------------------------


async def _seed_dataset(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    status: DatasetStatus = DatasetStatus.staged,
    balance_rows: int = 3,
    ledger_rows: int = 5,
    aux_ledger_rows: int = 2,
) -> LedgerDataset:
    dataset = LedgerDataset(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        status=status,
        source_type="import",
    )
    db.add(dataset)
    await db.flush()
    for i in range(balance_rows):
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
    for i in range(ledger_rows):
        db.add(TbLedger(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            dataset_id=dataset.id,
            company_code="001",
            voucher_date=date(year, 1, 1),
            voucher_no=f"V{i:03d}",
            account_code=f"100{i % balance_rows}",
            currency_code="CNY",
            is_deleted=False,
        ))
    for i in range(aux_ledger_rows):
        db.add(TbAuxLedger(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            dataset_id=dataset.id,
            company_code="001",
            account_code=f"100{i}",
            aux_type="客户",
            aux_code=f"C{i}",
            currency_code="CNY",
            is_deleted=False,
        ))
    await db.flush()
    return dataset


async def _is_deleted_histogram(
    db: AsyncSession, dataset_id: uuid.UUID,
) -> dict[str, dict[bool, int]]:
    """返回 4 张表按 is_deleted 分桶的计数（用于证明激活不触碰物理行）。"""
    out: dict[str, dict[bool, int]] = {}
    for tbl in ("tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger"):
        t = sa.table(
            tbl,
            sa.column("dataset_id"),
            sa.column("is_deleted"),
        )
        res = await db.execute(
            sa.select(t.c.is_deleted, sa.func.count())
            .where(t.c.dataset_id == dataset_id)
            .group_by(t.c.is_deleted)
        )
        out[tbl] = {row[0]: int(row[1]) for row in res.all()}
    return out


# ===========================================================================
# Case 1: staged → active 切换 + 物理行 is_deleted 保持不变
# ===========================================================================


@pytest.mark.asyncio
async def test_activate_flips_metadata_not_physical_rows(db_session: AsyncSession):
    project_id = uuid.uuid4()
    year = 2024

    staged = await _seed_dataset(
        db_session, project_id=project_id, year=year,
        balance_rows=4, ledger_rows=6, aux_ledger_rows=2,
    )
    before_hist = await _is_deleted_histogram(db_session, staged.id)

    activated = await DatasetService.activate(
        db_session, staged.id,
        activated_by=None,
        reason="测试自动激活",
    )

    assert activated.status == DatasetStatus.active
    await db_session.refresh(staged)
    assert staged.status == DatasetStatus.active

    after_hist = await _is_deleted_histogram(db_session, staged.id)
    # B' 核心断言：激活前后每张表的 is_deleted 分布完全一致
    assert before_hist == after_hist, (
        "B' 架构下 activate 不应 UPDATE 任何 Tb* 物理行 is_deleted"
    )
    # 所有物理行都是 is_deleted=false
    for tbl, bucket in after_hist.items():
        assert bucket.get(True, 0) == 0, f"{tbl} 出现 is_deleted=true 行"


# ===========================================================================
# Case 2: 旧 active → superseded 切换（严格按 project+year 过滤）
# ===========================================================================


@pytest.mark.asyncio
async def test_activate_marks_previous_active_superseded(db_session: AsyncSession):
    project_id = uuid.uuid4()
    year = 2024

    v1 = await _seed_dataset(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, v1.id)

    # 其他年度 active dataset 不应受影响
    other_year_active = await _seed_dataset(
        db_session, project_id=project_id, year=2023,
    )
    await DatasetService.activate(db_session, other_year_active.id)

    v2 = await _seed_dataset(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, v2.id)

    await db_session.refresh(v1)
    await db_session.refresh(v2)
    await db_session.refresh(other_year_active)
    assert v1.status == DatasetStatus.superseded
    assert v2.status == DatasetStatus.active
    # year=2023 的 active dataset 不应被误标 superseded（F5 跨年度保护）
    assert other_year_active.status == DatasetStatus.active


# ===========================================================================
# Case 3: Idempotency — 重复 activate 同一 dataset 直接返回成功
# ===========================================================================


@pytest.mark.asyncio
async def test_activate_idempotent_for_active_dataset(db_session: AsyncSession):
    project_id = uuid.uuid4()
    year = 2024

    staged = await _seed_dataset(db_session, project_id=project_id, year=year)
    first = await DatasetService.activate(db_session, staged.id)
    assert first.status == DatasetStatus.active
    await db_session.flush()

    # 数一下初始 ActivationRecord
    count_before = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(ActivationRecord)
            .where(ActivationRecord.dataset_id == staged.id)
        )
    ).scalar_one()
    assert count_before >= 1

    # 再 activate 一次 → 同一 dataset，status 不变
    second = await DatasetService.activate(db_session, staged.id)
    assert second.id == first.id
    assert second.status == DatasetStatus.active

    # F29 幂等：不应产生新的 ActivationRecord
    count_after = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(ActivationRecord)
            .where(ActivationRecord.dataset_id == staged.id)
        )
    ).scalar_one()
    assert count_after == count_before, (
        "幂等 activate 不应新增 ActivationRecord（F29 / Sprint 10.39）"
    )


# ===========================================================================
# Case 4: ActivationRecord 审计字段完整性
# ===========================================================================


@pytest.mark.asyncio
async def test_activation_record_audit_fields(db_session: AsyncSession):
    project_id = uuid.uuid4()
    year = 2024
    actor = uuid.uuid4()

    staged = await _seed_dataset(
        db_session, project_id=project_id, year=year,
        balance_rows=3, ledger_rows=5, aux_ledger_rows=1,
    )
    record_summary = {
        "tb_balance": 3,
        "tb_ledger": 5,
        "tb_aux_balance": 0,
        "tb_aux_ledger": 1,
    }
    await DatasetService.activate(
        db_session, staged.id,
        activated_by=actor,
        record_summary=record_summary,
        ip_address="10.0.0.2",
        reason="用户点击激活",
    )

    record = (
        await db_session.execute(
            sa.select(ActivationRecord)
            .where(ActivationRecord.dataset_id == staged.id)
        )
    ).scalars().first()
    assert record is not None
    assert record.action == ActivationType.activate
    assert record.performed_by == actor
    assert record.ip_address == "10.0.0.2"
    assert record.reason == "用户点击激活"
    assert record.duration_ms is not None and record.duration_ms >= 0
    # after_row_counts 应反映实际写入数
    assert isinstance(record.after_row_counts, dict)
    assert record.after_row_counts.get("tb_balance") == 3
    assert record.after_row_counts.get("tb_ledger") == 5
    assert record.after_row_counts.get("tb_aux_ledger") == 1


# ===========================================================================
# Case 5: 激活事件通过 outbox 发布
# ===========================================================================


@pytest.mark.asyncio
async def test_activate_enqueues_outbox_event(db_session: AsyncSession):
    from app.models.audit_platform_schemas import EventType
    from app.models.dataset_models import ImportEventOutbox

    project_id = uuid.uuid4()
    year = 2024
    staged = await _seed_dataset(db_session, project_id=project_id, year=year)
    dataset = await DatasetService.activate(db_session, staged.id)

    outbox_id = getattr(dataset, "_activation_outbox_id", None)
    assert outbox_id is not None, "activate 应把 outbox id 挂到 dataset 上"

    outbox_row = (
        await db_session.execute(
            sa.select(ImportEventOutbox).where(ImportEventOutbox.id == outbox_id)
        )
    ).scalar_one_or_none()
    assert outbox_row is not None
    assert outbox_row.event_type == EventType.LEDGER_DATASET_ACTIVATED
    assert outbox_row.project_id == project_id
    assert outbox_row.year == year


# ===========================================================================
# Case 6: 非 staged 状态不允许激活
# ===========================================================================


@pytest.mark.asyncio
async def test_activate_non_staged_raises(db_session: AsyncSession):
    project_id = uuid.uuid4()
    year = 2024
    dataset = await _seed_dataset(
        db_session, project_id=project_id, year=year,
        status=DatasetStatus.superseded,
    )
    with pytest.raises(ValueError, match="not staged"):
        await DatasetService.activate(db_session, dataset.id)
