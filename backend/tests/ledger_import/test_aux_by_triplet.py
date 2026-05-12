"""S6-20: 三元组穿透查询测试（get_aux_by_triplet）。

覆盖场景：
- 科目+维度类型+编码三元组精确定位
- aux_code=None 返回该维度类型下所有
- 余额多行（不同 aux_code）求和
- 明细账分页
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.dialects.postgresql import JSONB

# SQLite 不支持 JSONB，用 JSON 替代
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.models.audit_platform_models import TbAuxBalance, TbAuxLedger
from app.models.base import Base
# 触发模型注册
from app.models import audit_platform_models  # noqa: F401
from app.services.ledger_penetration_service import LedgerPenetrationService

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s


PID = uuid.uuid4()
YEAR = 2025


async def _seed_aux_balance(
    session: AsyncSession, *, account_code: str, aux_type: str,
    aux_code: str, aux_name: str, opening: Decimal, closing: Decimal,
) -> None:
    session.add(TbAuxBalance(
        id=uuid.uuid4(),
        project_id=PID,
        year=YEAR,
        company_code="default",
        account_code=account_code,
        account_name=f"科目{account_code}",
        aux_type=aux_type,
        aux_code=aux_code,
        aux_name=aux_name,
        opening_balance=opening,
        debit_amount=Decimal(0),
        credit_amount=Decimal(0),
        closing_balance=closing,
    ))


async def _seed_aux_ledger(
    session: AsyncSession, *, account_code: str, aux_type: str,
    aux_code: str, aux_name: str, voucher_no: str,
    voucher_date: date = date(2025, 1, 15),
    debit: Decimal = Decimal(0),
) -> None:
    session.add(TbAuxLedger(
        id=uuid.uuid4(),
        project_id=PID,
        year=YEAR,
        company_code="default",
        account_code=account_code,
        account_name=f"科目{account_code}",
        aux_type=aux_type,
        aux_code=aux_code,
        aux_name=aux_name,
        voucher_date=voucher_date,
        voucher_no=voucher_no,
        debit_amount=debit,
        credit_amount=Decimal(0),
    ))


@pytest.mark.asyncio
async def test_triplet_exact_match(db_session: AsyncSession):
    """三元组精确查询：科目 6001.14.02 + 客户 + 041108"""
    # 科目 6001.14.02 下有两个客户（041108 和 008063）
    await _seed_aux_balance(
        db_session, account_code="6001.14.02", aux_type="客户",
        aux_code="041108", aux_name="重庆医药和平物流",
        opening=Decimal("100.00"), closing=Decimal("200.00"),
    )
    await _seed_aux_balance(
        db_session, account_code="6001.14.02", aux_type="客户",
        aux_code="008063", aux_name="重庆医药四川医药",
        opening=Decimal("500.00"), closing=Decimal("600.00"),
    )
    # 明细账 2 行（都属于 041108）
    await _seed_aux_ledger(
        db_session, account_code="6001.14.02", aux_type="客户",
        aux_code="041108", aux_name="重庆医药和平物流",
        voucher_no="记-001", debit=Decimal("50.00"),
    )
    await _seed_aux_ledger(
        db_session, account_code="6001.14.02", aux_type="客户",
        aux_code="041108", aux_name="重庆医药和平物流",
        voucher_no="记-002", debit=Decimal("50.00"),
    )
    await db_session.commit()

    svc = LedgerPenetrationService(db_session)
    result = await svc.get_aux_by_triplet(
        PID, YEAR, "6001.14.02", "客户", "041108",
    )

    assert result["account"]["account_code"] == "6001.14.02"
    assert result["aux"]["aux_type"] == "客户"
    assert result["aux"]["aux_code"] == "041108"
    assert result["aux"]["aux_name"] == "重庆医药和平物流"
    assert result["balance"]["opening_balance"] == Decimal("100.00")
    assert result["balance"]["closing_balance"] == Decimal("200.00")
    assert result["balance"]["aux_code_count"] == 1
    assert result["ledger"]["total"] == 2
    assert len(result["ledger"]["items"]) == 2


@pytest.mark.asyncio
async def test_triplet_no_aux_code_returns_all(db_session: AsyncSession):
    """aux_code=None 返回该 (account_code, aux_type) 下所有维度聚合。"""
    for code, name, opening, closing in [
        ("041108", "客户A", Decimal("100"), Decimal("200")),
        ("008063", "客户B", Decimal("500"), Decimal("600")),
    ]:
        await _seed_aux_balance(
            db_session, account_code="6001.14.02", aux_type="客户",
            aux_code=code, aux_name=name,
            opening=opening, closing=closing,
        )
    await db_session.commit()

    svc = LedgerPenetrationService(db_session)
    result = await svc.get_aux_by_triplet(
        PID, YEAR, "6001.14.02", "客户", aux_code=None,
    )

    assert result["balance"]["aux_code_count"] == 2
    # 聚合金额 = 100 + 500 = 600 期初
    assert result["balance"]["opening_balance"] == Decimal("600")
    assert result["balance"]["closing_balance"] == Decimal("800")
    # 单客户 aux_name 不赋值（多行）
    assert result["aux"]["aux_name"] is None


@pytest.mark.asyncio
async def test_triplet_disambiguates_crossref(db_session: AsyncSession):
    """真实场景：'税率' 同时出现在客户/项目下，三元组精确定位到客户下的税率。"""
    # 科目 6001 下的客户 041108 也有"税率"维度
    await _seed_aux_balance(
        db_session, account_code="6001", aux_type="客户",
        aux_code="041108", aux_name="客户A",
        opening=Decimal("100"), closing=Decimal("200"),
    )
    # 同科目下的"税率"维度
    await _seed_aux_balance(
        db_session, account_code="6001", aux_type="税率",
        aux_code="9", aux_name="9%",
        opening=Decimal("10"), closing=Decimal("20"),
    )
    await db_session.commit()

    svc = LedgerPenetrationService(db_session)
    # 只查客户维度
    result_cust = await svc.get_aux_by_triplet(PID, YEAR, "6001", "客户")
    assert result_cust["balance"]["closing_balance"] == Decimal("200")
    # 只查税率维度
    result_rate = await svc.get_aux_by_triplet(PID, YEAR, "6001", "税率")
    assert result_rate["balance"]["closing_balance"] == Decimal("20")


@pytest.mark.asyncio
async def test_triplet_empty_result(db_session: AsyncSession):
    """不存在的三元组 → balance 空 dict，ledger 0 行。"""
    svc = LedgerPenetrationService(db_session)
    result = await svc.get_aux_by_triplet(
        PID, YEAR, "9999", "客户", "XXX",
    )
    assert result["balance"] == {}
    assert result["ledger"]["total"] == 0
    assert result["ledger"]["items"] == []
