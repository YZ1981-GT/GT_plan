"""Sprint 10 Task 10.11: 跨年度同项目双 active 集成测试。

F5 验收：
- 项目 P 的 2024 与 2025 可并存各自的 active dataset
- activate 2025 不应误把 2024 标 superseded（mark_previous_superseded 按 year 过滤）
- get_active_filter 按 (project_id, year) 分别返回对应 dataset
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


@pytest.mark.asyncio
async def test_two_years_can_coexist_as_active(db_session: AsyncSession):
    """两个年度各自激活一个 dataset，互不影响。"""
    project_id = uuid.uuid4()

    # ---- 2024 创建 staged + activate ----
    ds2024 = await DatasetService.create_staged(db_session, project_id=project_id, year=2024)
    await DatasetService.activate(db_session, ds2024.id)
    await db_session.flush()

    # 写入 2024 数据
    db_session.add(
        TbBalance(
            id=uuid.uuid4(), project_id=project_id, year=2024,
            dataset_id=ds2024.id, company_code="default", account_code="2024-01",
            currency_code="CNY", is_deleted=False,
        )
    )

    # ---- 2025 创建 staged + activate ----
    ds2025 = await DatasetService.create_staged(db_session, project_id=project_id, year=2025)
    await DatasetService.activate(db_session, ds2025.id)
    await db_session.flush()

    # 写入 2025 数据
    db_session.add(
        TbBalance(
            id=uuid.uuid4(), project_id=project_id, year=2025,
            dataset_id=ds2025.id, company_code="default", account_code="2025-01",
            currency_code="CNY", is_deleted=False,
        )
    )
    await db_session.flush()

    # 验证：2024 仍是 active（不应被 2025 的 activate 误标 superseded）
    ds2024_reloaded = await db_session.get(LedgerDataset, ds2024.id)
    ds2025_reloaded = await db_session.get(LedgerDataset, ds2025.id)
    assert ds2024_reloaded.status == DatasetStatus.active
    assert ds2025_reloaded.status == DatasetStatus.active

    # 业务查询分别返回对应 dataset 的行
    filter_2024 = await get_active_filter(
        db_session, TbBalance.__table__, project_id, 2024
    )
    rows_2024 = (
        await db_session.execute(sa.select(TbBalance).where(filter_2024))
    ).scalars().all()
    assert len(rows_2024) == 1
    assert rows_2024[0].account_code == "2024-01"

    filter_2025 = await get_active_filter(
        db_session, TbBalance.__table__, project_id, 2025
    )
    rows_2025 = (
        await db_session.execute(sa.select(TbBalance).where(filter_2025))
    ).scalars().all()
    assert len(rows_2025) == 1
    assert rows_2025[0].account_code == "2025-01"


@pytest.mark.asyncio
async def test_activate_within_year_supersedes_same_year_only(
    db_session: AsyncSession,
):
    """同 year 内二次 activate 应该把 v1 标 superseded；但不应影响其他年度的 active。"""
    project_id = uuid.uuid4()

    # 2024 v1 → activate
    v1_2024 = await DatasetService.create_staged(db_session, project_id=project_id, year=2024)
    await DatasetService.activate(db_session, v1_2024.id)
    await db_session.flush()

    # 2025 v1 → activate
    v1_2025 = await DatasetService.create_staged(db_session, project_id=project_id, year=2025)
    await DatasetService.activate(db_session, v1_2025.id)
    await db_session.flush()

    # 2024 v2 → activate（v1_2024 应 superseded，v1_2025 不受影响）
    v2_2024 = await DatasetService.create_staged(db_session, project_id=project_id, year=2024)
    v2_2024.previous_dataset_id = v1_2024.id
    await DatasetService.activate(db_session, v2_2024.id)
    await db_session.flush()

    reloaded = {
        ds.id: ds for ds in (
            await db_session.execute(
                sa.select(LedgerDataset).where(
                    LedgerDataset.project_id == project_id
                )
            )
        ).scalars().all()
    }
    assert reloaded[v1_2024.id].status == DatasetStatus.superseded
    assert reloaded[v2_2024.id].status == DatasetStatus.active
    # 2025 的 active 不应被跨年影响
    assert reloaded[v1_2025.id].status == DatasetStatus.active



# ===========================================================================
# F29 / Sprint 10.39: 幂等 activate
# ===========================================================================


@pytest.mark.asyncio
async def test_activate_is_idempotent_on_already_active(
    db_session: AsyncSession,
):
    """已是 active 的 dataset 再次调 activate 应直接返回成功（幂等）。

    用例：resume_from_checkpoint 重跑 activate 阶段，不应因 "not staged" 失败。
    """
    project_id = uuid.uuid4()

    ds = await DatasetService.create_staged(
        db_session, project_id=project_id, year=2024
    )
    await DatasetService.activate(db_session, ds.id)
    await db_session.flush()

    # 二次调用应幂等返回，不抛异常
    result = await DatasetService.activate(db_session, ds.id)
    assert result.id == ds.id
    assert result.status == DatasetStatus.active
