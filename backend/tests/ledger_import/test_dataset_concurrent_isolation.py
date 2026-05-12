"""F1 并发场景 / Sprint 11.5: 项目 A staged + 项目 B active 隔离

覆盖 `get_active_filter` 对跨项目并发场景的严格隔离：
1. 项目 A 有 staged dataset + 物理行；项目 B 有 active dataset + 物理行
   查询 B 只见 B 的 active 行；查询 A 不应返回 B 的行
2. 同一项目同一年度可以并存 staged + active（staged 不污染已 active 的视图）
3. A active V1 + B active V2（不同项目）互相隔离
4. 无 active 降级：project 无 active dataset 时 fallback 到 is_deleted=false
   过滤仍严格按 project_id 隔离

Fixture 模式：SQLite in-memory 复用 test_dataset_rollback_view_refactor.py 同款。
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
from app.models.dataset_models import DatasetStatus
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


async def _select_active_balance(
    db: AsyncSession, project_id: uuid.UUID, year: int,
) -> list[TbBalance]:
    cond = await get_active_filter(db, TbBalance.__table__, project_id, year)
    res = await db.execute(
        sa.select(TbBalance).where(cond).order_by(TbBalance.account_code)
    )
    return list(res.scalars().all())


async def _select_active_ledger(
    db: AsyncSession, project_id: uuid.UUID, year: int,
) -> list[TbLedger]:
    cond = await get_active_filter(db, TbLedger.__table__, project_id, year)
    res = await db.execute(
        sa.select(TbLedger).where(cond).order_by(TbLedger.account_code)
    )
    return list(res.scalars().all())


# ===========================================================================
# Case 1: A staged + B active 互不污染
# ===========================================================================


@pytest.mark.asyncio
async def test_project_a_staged_does_not_leak_into_b_active(
    db_session: AsyncSession,
):
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    year = 2024

    a_staged = await DatasetService.create_staged(
        db_session, project_id=project_a, year=year,
    )
    db_session.add_all([
        TbBalance(
            id=uuid.uuid4(),
            project_id=project_a, year=year, company_code="A01",
            account_code="1001", account_name="A-现金-staged",
            dataset_id=a_staged.id, is_deleted=False, currency_code="CNY",
        ),
        TbBalance(
            id=uuid.uuid4(),
            project_id=project_a, year=year, company_code="A01",
            account_code="1002", account_name="A-银行-staged",
            dataset_id=a_staged.id, is_deleted=False, currency_code="CNY",
        ),
    ])
    b_active = await DatasetService.create_staged(
        db_session, project_id=project_b, year=year,
    )
    await DatasetService.activate(db_session, b_active.id)
    db_session.add_all([
        TbBalance(
            id=uuid.uuid4(),
            project_id=project_b, year=year, company_code="B01",
            account_code="2001", account_name="B-应付-active",
            dataset_id=b_active.id, is_deleted=False, currency_code="CNY",
        ),
    ])
    await db_session.flush()

    b_rows = await _select_active_balance(db_session, project_b, year)
    assert len(b_rows) == 1
    assert b_rows[0].project_id == project_b
    assert b_rows[0].account_name == "B-应付-active"

    # 查询 A：当前 A 无 active dataset，fallback 到 project+is_deleted=false
    # 返回 A 的 staged 行（B' 架构允许看"当前进度"），但 **绝对** 不能返回 B 的行
    a_rows = await _select_active_balance(db_session, project_a, year)
    for r in a_rows:
        assert r.project_id == project_a
        assert not r.account_name.startswith("B-"), "A 查询不应返回 B 的数据"


# ===========================================================================
# Case 2: 同项目同年度 staged + active 并存（staged 不影响 active 视图）
# ===========================================================================


@pytest.mark.asyncio
async def test_same_project_staged_does_not_pollute_active_view(
    db_session: AsyncSession,
):
    project_id = uuid.uuid4()
    year = 2024

    # V1 active
    v1 = await DatasetService.create_staged(
        db_session, project_id=project_id, year=year,
    )
    await DatasetService.activate(db_session, v1.id)
    db_session.add(TbBalance(
        id=uuid.uuid4(),
        project_id=project_id, year=year, company_code="001",
        account_code="1001", account_name="V1-现金-active",
        dataset_id=v1.id, is_deleted=False, currency_code="CNY",
    ))

    # V2 staged（模拟第二次导入正在写入）
    v2 = await DatasetService.create_staged(
        db_session, project_id=project_id, year=year,
    )
    db_session.add(TbBalance(
        id=uuid.uuid4(),
        project_id=project_id, year=year, company_code="001",
        account_code="2001", account_name="V2-银行-staged",
        dataset_id=v2.id, is_deleted=False, currency_code="CNY",
    ))
    await db_session.flush()

    # 查询 active 视图 → 只见 V1
    rows = await _select_active_balance(db_session, project_id, year)
    assert len(rows) == 1
    assert rows[0].account_name == "V1-现金-active"
    assert rows[0].dataset_id == v1.id
    # V2 staged 的行存在于库但不可见
    all_rows_for_year = (
        await db_session.execute(
            sa.select(TbBalance).where(
                TbBalance.project_id == project_id,
                TbBalance.year == year,
            )
        )
    ).scalars().all()
    assert len(all_rows_for_year) == 2


# ===========================================================================
# Case 3: A active V1 + B active V2 （两项目各自 active）互不污染
# ===========================================================================


@pytest.mark.asyncio
async def test_two_actives_across_projects_do_not_leak(
    db_session: AsyncSession,
):
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    year = 2024

    a = await DatasetService.create_staged(
        db_session, project_id=project_a, year=year,
    )
    await DatasetService.activate(db_session, a.id)
    b = await DatasetService.create_staged(
        db_session, project_id=project_b, year=year,
    )
    await DatasetService.activate(db_session, b.id)

    db_session.add_all([
        TbLedger(
            id=uuid.uuid4(),
            project_id=project_a, year=year, company_code="A",
            voucher_date=date(year, 1, 1), voucher_no="A1",
            account_code="1001", dataset_id=a.id,
            is_deleted=False, currency_code="CNY",
        ),
        TbLedger(
            id=uuid.uuid4(),
            project_id=project_b, year=year, company_code="B",
            voucher_date=date(year, 1, 1), voucher_no="B1",
            account_code="1001", dataset_id=b.id,
            is_deleted=False, currency_code="CNY",
        ),
    ])
    await db_session.flush()

    a_rows = await _select_active_ledger(db_session, project_a, year)
    b_rows = await _select_active_ledger(db_session, project_b, year)
    assert len(a_rows) == 1 and a_rows[0].project_id == project_a
    assert len(b_rows) == 1 and b_rows[0].project_id == project_b
    assert a_rows[0].company_code == "A"
    assert b_rows[0].company_code == "B"


# ===========================================================================
# Case 4: 多年度 active 同时并存（F5 跨年度）
# ===========================================================================


@pytest.mark.asyncio
async def test_multi_year_actives_isolated(db_session: AsyncSession):
    project_id = uuid.uuid4()

    ds_2024 = await DatasetService.create_staged(
        db_session, project_id=project_id, year=2024,
    )
    await DatasetService.activate(db_session, ds_2024.id)
    ds_2025 = await DatasetService.create_staged(
        db_session, project_id=project_id, year=2025,
    )
    await DatasetService.activate(db_session, ds_2025.id)

    db_session.add_all([
        TbBalance(
            id=uuid.uuid4(),
            project_id=project_id, year=2024, company_code="001",
            account_code="1001", account_name="2024 年",
            dataset_id=ds_2024.id, is_deleted=False, currency_code="CNY",
        ),
        TbBalance(
            id=uuid.uuid4(),
            project_id=project_id, year=2025, company_code="001",
            account_code="1001", account_name="2025 年",
            dataset_id=ds_2025.id, is_deleted=False, currency_code="CNY",
        ),
    ])
    await db_session.flush()

    rows_2024 = await _select_active_balance(db_session, project_id, 2024)
    rows_2025 = await _select_active_balance(db_session, project_id, 2025)
    assert len(rows_2024) == 1 and rows_2024[0].account_name == "2024 年"
    assert len(rows_2025) == 1 and rows_2025[0].account_name == "2025 年"

    # 断言：2024/2025 各自 active dataset 都保留（mark_previous_superseded 不跨年）
    await db_session.refresh(ds_2024)
    await db_session.refresh(ds_2025)
    assert ds_2024.status == DatasetStatus.active
    assert ds_2025.status == DatasetStatus.active
