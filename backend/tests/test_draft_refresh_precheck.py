"""DraftRefreshService.precheck 四表库完整度前置校验测试.

Task 5.1（formula-management-library）：验证 precheck 复用 report_trace 数据完整度
前置校验口径——必需数据缺失进 blocking（阻断），次级来源缺失进 warnings（非阻断）。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import (
    AccountCategory,
    TbAuxBalance,
    TbBalance,
    TbLedger,
    TrialBalance,
)
from app.models.dataset_models import LedgerDataset
from app.services.draft_refresh_service import DraftRefreshService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

PROJECT_ID = uuid.uuid4()
YEAR = 2025

_TEST_TABLES = [
    TbBalance.__table__,
    TbLedger.__table__,
    TbAuxBalance.__table__,
    TrialBalance.__table__,
    LedgerDataset.__table__,
]


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().create_all(sync_conn, tables=_TEST_TABLES)
        )
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().drop_all(sync_conn, tables=_TEST_TABLES)
        )


def _tb_balance(**kw):
    base = dict(
        project_id=PROJECT_ID, year=YEAR, company_code="C1",
        account_code="1001", account_name="库存现金", closing_balance=Decimal("100"),
    )
    base.update(kw)
    return TbBalance(**base)


def _trial_balance(unadjusted=Decimal("100"), **kw):
    base = dict(
        project_id=PROJECT_ID, year=YEAR, company_code="C1",
        standard_account_code="1001", account_name="库存现金",
        account_category=AccountCategory.asset, unadjusted_amount=unadjusted,
    )
    base.update(kw)
    return TrialBalance(**base)


def _tb_ledger(**kw):
    from datetime import date
    base = dict(
        project_id=PROJECT_ID, year=YEAR, company_code="C1",
        voucher_date=date(YEAR, 1, 1), voucher_no="V1",
        account_code="6001", account_name="主营业务收入",
        credit_amount=Decimal("500"),
    )
    base.update(kw)
    return TbLedger(**base)


def _tb_aux(**kw):
    base = dict(
        project_id=PROJECT_ID, year=YEAR, company_code="C1",
        account_code="1122", account_name="应收账款",
        aux_type="customer", aux_code="K01", aux_name="客户甲",
        closing_balance=Decimal("300"),
    )
    base.update(kw)
    return TbAuxBalance(**base)


@pytest.mark.asyncio
async def test_precheck_full_data_no_blocking_no_warnings(db_session: AsyncSession):
    """四表齐全且有未审数 → 无 blocking、无 warnings、可刷新。"""
    db_session.add_all([_tb_balance(), _trial_balance(), _tb_ledger(), _tb_aux()])
    await db_session.commit()

    result = await DraftRefreshService().precheck(
        db_session, project_id=PROJECT_ID, year=YEAR
    )

    assert result.can_refresh is True
    assert result.blocking == []
    assert result.warnings == []


@pytest.mark.asyncio
async def test_precheck_missing_core_tables_blocks(db_session: AsyncSession):
    """tb_balance 与 trial_balance 均缺失 → 两条 blocking，不可刷新。"""
    # 仅有序时账，无核心余额源
    db_session.add(_tb_ledger())
    await db_session.commit()

    result = await DraftRefreshService().precheck(
        db_session, project_id=PROJECT_ID, year=YEAR
    )

    assert result.can_refresh is False
    blocking_tables = {i.table for i in result.blocking}
    assert blocking_tables == {"tb_balance", "trial_balance"}
    # 每条缺失项含表名 + 说明
    for item in result.blocking:
        assert item.label
        assert item.message


@pytest.mark.asyncio
async def test_precheck_missing_aux_and_ledger_is_warning(db_session: AsyncSession):
    """核心表齐全，缺 tb_ledger / tb_aux_balance → 非阻断 warnings，仍可刷新。"""
    db_session.add_all([_tb_balance(), _trial_balance()])
    await db_session.commit()

    result = await DraftRefreshService().precheck(
        db_session, project_id=PROJECT_ID, year=YEAR
    )

    assert result.can_refresh is True
    assert result.blocking == []
    warning_tables = {i.table for i in result.warnings}
    assert "tb_ledger" in warning_tables
    assert "tb_aux_balance" in warning_tables


@pytest.mark.asyncio
async def test_precheck_empty_unadjusted_is_warning(db_session: AsyncSession):
    """试算表有行但未审数全为 0 → 非阻断 warning（初稿可能为空）。"""
    db_session.add_all([
        _tb_balance(), _tb_ledger(), _tb_aux(),
        _trial_balance(unadjusted=Decimal("0")),
    ])
    await db_session.commit()

    result = await DraftRefreshService().precheck(
        db_session, project_id=PROJECT_ID, year=YEAR
    )

    assert result.can_refresh is True
    assert result.blocking == []
    assert any(
        i.table == "trial_balance" and "未审数" in i.message
        for i in result.warnings
    )


@pytest.mark.asyncio
async def test_precheck_result_to_dict_shape(db_session: AsyncSession):
    """to_dict 输出结构含 can_refresh / blocking / warnings，供 API 序列化。"""
    await db_session.commit()

    result = await DraftRefreshService().precheck(
        db_session, project_id=PROJECT_ID, year=YEAR
    )
    payload = result.to_dict()

    assert set(payload.keys()) == {"can_refresh", "blocking", "warnings"}
    assert payload["can_refresh"] is False  # 空库两核心表缺失
    assert isinstance(payload["blocking"], list)
    for entry in payload["blocking"]:
        assert set(entry.keys()) == {"table", "label", "message"}
