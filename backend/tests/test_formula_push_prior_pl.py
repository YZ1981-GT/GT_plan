"""损益类附注上期发生额取上年试算表（spec disclosure-note-template-word-realignment Task 34/35）。

2026-10-31 真库：推送原来把损益类附注的「上期发生额」取成本年试算表年初余额 —— 损益类科目年初恒为 0，和平药房_2025
八、65 销售费用等 8 节上期全被推成 0.00（报表上期 242,169,736.06 来自上年项目）。现在与报表上期 / PREV 同一查找口径
（``prior_year_context.resolve_prior_source``）取上年试算表审定数；取不到不出值、写明原因。真 SQLite + 真 ORM。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base
from app.models.core import Project
from app.services.formula_push.sources import load_prior_pl


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[Project.__table__, TrialBalance.__table__]))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


def _project(company: str | None, year: int, **kw) -> Project:
    return Project(id=uuid.uuid4(), name=f"甲_{year}", client_name="甲", company_code=company, audit_year=year,
                   report_scope="standalone", **kw)


def _tb(project: Project, year: int, code: str, audited: str, opening: str = "0") -> TrialBalance:
    return TrialBalance(id=uuid.uuid4(), project_id=project.id, year=year, company_code="001",
                        standard_account_code=code, account_name=code, account_category=AccountCategory.expense,
                        audited_amount=Decimal(audited), opening_balance=Decimal(opening))


@pytest.mark.asyncio
async def test_prior_period_comes_from_prior_year_project_trial_balance(db: AsyncSession) -> None:
    prior, cur = _project("C1", 2024), _project("C1", 2025)
    db.add_all([prior, cur, _tb(prior, 2024, "6601", "242169736.06"), _tb(prior, 2024, "660101", "1.00"),
                _tb(cur, 2025, "6601", "133145053.19")])
    await db.commit()
    snap = await load_prior_pl(db, cur.id, 2025, ("6601", "1122"))
    assert snap is not None and snap.tb_data is not None and snap.reason == ""
    assert snap.tb_data["6601"]["本期发生额"] == Decimal("242169737.06")  # 与试算表取数同口径：前缀含子级
    assert "1122" not in snap.tb_data  # 只取损益类


@pytest.mark.asyncio
async def test_same_project_prior_year_trial_balance_wins(db: AsyncSession) -> None:
    cur = _project("C1", 2025)
    db.add_all([cur, _tb(cur, 2024, "6601", "7"), _tb(cur, 2025, "6601", "9")])
    await db.commit()
    snap = await load_prior_pl(db, cur.id, 2025, ("6601",))
    assert snap.tb_data["6601"]["本期发生额"] == Decimal("7")


@pytest.mark.asyncio
async def test_no_prior_data_gives_reason_not_zero(db: AsyncSession) -> None:
    cur = _project("C1", 2025)
    db.add_all([cur, _tb(cur, 2025, "6601", "9")])
    await db.commit()
    snap = await load_prior_pl(db, cur.id, 2025, ("6601",))
    assert snap.tb_data is None and "没有上年项目" in snap.reason
    # 上年项目存在但没有试算表
    db.add(_project("C1", 2024))
    await db.commit()
    snap = await load_prior_pl(db, cur.id, 2025, ("6601",))
    assert snap.tb_data is None and "2024 年试算表" in snap.reason


@pytest.mark.asyncio
async def test_balance_sheet_only_bindings_skip_prior_lookup(db: AsyncSession) -> None:
    cur = _project("C1", 2025)
    db.add(cur)
    await db.commit()
    assert await load_prior_pl(db, cur.id, 2025, ("1122", "2241")) is None
