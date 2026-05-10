"""F1 / Sprint 11.6: rollback 完整流程集成测试

覆盖"两次导入 + 回滚"的核心业务流（对齐 requirements §4.2）：

1. V1：create_staged → 写入物理行 → activate → 通过 get_active_filter 能看到 V1 数据
2. V2：create_staged → 写入物理行 → activate → 查询只返回 V2 数据（V1 = superseded）
3. rollback：当前 active=V2 → rolled_back，previous=V1 → active
4. 回滚后查询：get_active_filter 返回 V1 数据（审计员能继续在老版本上工作）
5. Tb* 物理行数量全过程不变（既不 UPDATE 也不 DELETE）
6. ActivationRecord 留痕：1 × activate V1、1 × activate V2、1 × rollback
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
)
from app.services.dataset_query import get_active_filter
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


async def _write_import_batch(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    dataset_id: uuid.UUID,
    tag: str,
    balance_count: int = 3,
    ledger_count: int = 5,
) -> None:
    """模拟一次 pipeline 写入：生成 tag 标记的 N 行 TbBalance + TbLedger。"""
    for i in range(balance_count):
        db.add(TbBalance(
            id=uuid.uuid4(),
            project_id=project_id, year=year, dataset_id=dataset_id,
            company_code="001",
            account_code=f"B{i:03d}",
            account_name=f"{tag}-balance-{i}",
            currency_code="CNY",
            is_deleted=False,
        ))
    for i in range(ledger_count):
        db.add(TbLedger(
            id=uuid.uuid4(),
            project_id=project_id, year=year, dataset_id=dataset_id,
            company_code="001",
            voucher_date=date(year, 1, 1),
            voucher_no=f"{tag}-V{i:03d}",
            account_code=f"L{i:03d}",
            currency_code="CNY",
            is_deleted=False,
        ))
    await db.flush()


async def _count_physical_rows(db: AsyncSession, project_id: uuid.UUID, year: int) -> tuple[int, int]:
    """返回 (tb_balance 总数, tb_ledger 总数)（不按 dataset_id 过滤）。"""
    bal = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(TbBalance)
            .where(
                TbBalance.project_id == project_id,
                TbBalance.year == year,
            )
        )
    ).scalar_one()
    led = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(TbLedger)
            .where(
                TbLedger.project_id == project_id,
                TbLedger.year == year,
            )
        )
    ).scalar_one()
    return int(bal), int(led)


async def _active_balance_names(db: AsyncSession, project_id: uuid.UUID, year: int) -> list[str]:
    cond = await get_active_filter(db, TbBalance.__table__, project_id, year)
    res = await db.execute(
        sa.select(TbBalance.account_name).where(cond).order_by(TbBalance.account_code)
    )
    return [r[0] for r in res.all()]


# ===========================================================================
# 主流程测试
# ===========================================================================


@pytest.mark.asyncio
async def test_import_activate_reimport_activate_then_rollback(
    db_session: AsyncSession,
):
    project_id = uuid.uuid4()
    year = 2024

    # ---- 第一次导入 V1 ----
    v1 = await DatasetService.create_staged(
        db_session, project_id=project_id, year=year,
    )
    await _write_import_batch(
        db_session, project_id=project_id, year=year,
        dataset_id=v1.id, tag="V1", balance_count=3, ledger_count=5,
    )
    await DatasetService.activate(db_session, v1.id, reason="V1 导入完成")
    await db_session.flush()

    # 激活后：查询应返回 V1
    names_after_v1 = await _active_balance_names(db_session, project_id, year)
    assert len(names_after_v1) == 3
    assert all(n.startswith("V1-") for n in names_after_v1)

    bal_total_v1, led_total_v1 = await _count_physical_rows(db_session, project_id, year)
    assert bal_total_v1 == 3
    assert led_total_v1 == 5

    # ---- 第二次导入 V2 ----
    v2 = await DatasetService.create_staged(
        db_session, project_id=project_id, year=year,
    )
    await _write_import_batch(
        db_session, project_id=project_id, year=year,
        dataset_id=v2.id, tag="V2", balance_count=4, ledger_count=6,
    )
    await DatasetService.activate(db_session, v2.id, reason="V2 导入完成")
    await db_session.flush()

    # V1 自动降级 superseded，V2 active
    await db_session.refresh(v1)
    await db_session.refresh(v2)
    assert v1.status == DatasetStatus.superseded
    assert v2.status == DatasetStatus.active

    # 激活 V2 后：查询只返回 V2
    names_after_v2 = await _active_balance_names(db_session, project_id, year)
    assert len(names_after_v2) == 4
    assert all(n.startswith("V2-") for n in names_after_v2)

    # 物理行累加（V1 3+5 + V2 4+6）
    bal_total_v2, led_total_v2 = await _count_physical_rows(db_session, project_id, year)
    assert bal_total_v2 == 3 + 4
    assert led_total_v2 == 5 + 6

    # ---- rollback 到 V1 ----
    restored = await DatasetService.rollback(
        db_session, project_id, year,
        reason="V2 数据发现问题，回滚到 V1",
    )
    assert restored is not None
    assert restored.id == v1.id

    await db_session.refresh(v1)
    await db_session.refresh(v2)
    assert v1.status == DatasetStatus.active
    assert v2.status == DatasetStatus.rolled_back

    # rollback 后查询：回到 V1 数据
    names_after_rollback = await _active_balance_names(db_session, project_id, year)
    assert len(names_after_rollback) == 3
    assert all(n.startswith("V1-") for n in names_after_rollback)

    # 物理行数量仍然 = 3+4 和 5+6（既不 UPDATE 也不 DELETE）
    bal_total_final, led_total_final = await _count_physical_rows(db_session, project_id, year)
    assert bal_total_final == 7
    assert led_total_final == 11

    # 所有物理行 is_deleted=false
    bal_deleted = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(TbBalance)
            .where(
                TbBalance.project_id == project_id,
                TbBalance.year == year,
                TbBalance.is_deleted == sa.true(),
            )
        )
    ).scalar_one()
    assert bal_deleted == 0, "B' 架构下全流程不应产生 is_deleted=true 行"

    # ---- ActivationRecord 3 条留痕 ----
    records = (
        await db_session.execute(
            sa.select(ActivationRecord)
            .where(ActivationRecord.project_id == project_id)
            .order_by(ActivationRecord.performed_at)
        )
    ).scalars().all()
    actions = [r.action for r in records]
    assert actions.count(ActivationType.activate) == 2
    assert actions.count(ActivationType.rollback) == 1


@pytest.mark.asyncio
async def test_rollback_then_reactivate_creates_chain(db_session: AsyncSession):
    """Rollback 后重新 activate V2 应重新覆盖 V1（链式语义）。"""
    project_id = uuid.uuid4()
    year = 2024

    v1 = await DatasetService.create_staged(
        db_session, project_id=project_id, year=year,
    )
    await _write_import_batch(
        db_session, project_id=project_id, year=year,
        dataset_id=v1.id, tag="V1",
    )
    await DatasetService.activate(db_session, v1.id)
    await db_session.flush()

    v2 = await DatasetService.create_staged(
        db_session, project_id=project_id, year=year,
    )
    await _write_import_batch(
        db_session, project_id=project_id, year=year,
        dataset_id=v2.id, tag="V2",
    )
    await DatasetService.activate(db_session, v2.id)
    await db_session.flush()

    await DatasetService.rollback(db_session, project_id, year)
    await db_session.flush()

    # rollback 后再次 activate 一个新 dataset V3（模拟"发现 V1 也有问题，重新导入 V3"）
    v3 = await DatasetService.create_staged(
        db_session, project_id=project_id, year=year,
    )
    await _write_import_batch(
        db_session, project_id=project_id, year=year,
        dataset_id=v3.id, tag="V3", balance_count=2, ledger_count=3,
    )
    await DatasetService.activate(db_session, v3.id, reason="V3 新导入")
    await db_session.flush()

    await db_session.refresh(v1)
    await db_session.refresh(v2)
    await db_session.refresh(v3)
    assert v1.status == DatasetStatus.superseded
    assert v2.status == DatasetStatus.rolled_back
    assert v3.status == DatasetStatus.active

    names = await _active_balance_names(db_session, project_id, year)
    assert all(n.startswith("V3-") for n in names)
