"""公式求值正则容忍参数间空白（spec deliverable-trio-generation-accuracy，2026-10-16 真实库实测）。

库内 soe_standalone 资产减值准备表 10 行、现金流量表补充资料 15 行、权益变动表 2 行写成
``TB('1231', '期末余额')``（逗号后带空格）。AST 内核接受这种写法，但 report_engine 的 L2 预载
只认无空格正则 ⇒ 该 token 没被预载 ⇒ 内核按空 tb_data **静默求 0**（重药安徽坏账准备 2,896 万
在减值表里导出为 0）。这里钉住：有无空格求值结果相同。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.core import Project
from app.services.formula_grammar import ROW_PATTERN, SUM_ROW_PATTERN, SUM_TB_PATTERN, TB_PATTERN
from app.services.report_engine import ReportFormulaParser

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


@pytest.mark.parametrize(
    ("pattern", "text", "groups"),
    [
        (TB_PATTERN, "TB('1231', '期末余额')", ("1231", "期末余额")),
        (TB_PATTERN, "TB( '1231' , '期末余额' )", ("1231", "期末余额")),
        (TB_PATTERN, "TB('1231','期末余额')", ("1231", "期末余额")),
        (SUM_TB_PATTERN, "SUM_TB('1401~1499', '期末余额')", ("1401~1499", "期末余额")),
        (ROW_PATTERN, "ROW( 'BS-002' )", ("BS-002",)),
        (SUM_ROW_PATTERN, "SUM_ROW('IS-041', 'IS-043')", ("IS-041", "IS-043")),
    ],
)
def test_patterns_tolerate_whitespace(pattern, text, groups):
    m = pattern.search(text)
    assert m is not None and m.groups() == groups


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: MetaData().create_all(c, tables=[Project.__table__, TrialBalance.__table__]))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_spaced_tb_formula_evaluates_same_as_compact(db):
    pid = uuid.uuid4()
    db.add(Project(id=pid, name="空白公式_2025", client_name="空白公式"))
    for code, closing, opening in (("1231", 0, 0), ("1231-01", 100, 40), ("1231-02", 50, 10)):
        db.add(TrialBalance(
            project_id=pid, year=2025, company_code="001", standard_account_code=code,
            account_name="坏账准备", account_category=AccountCategory.asset,
            unadjusted_amount=Decimal(closing), audited_amount=Decimal(closing), opening_balance=Decimal(opening),
        ))
    await db.flush()

    parser = ReportFormulaParser(db, pid, 2025)
    assert await parser.execute("TB('1231', '期末余额')", {}) == Decimal("150")
    assert await parser.execute("TB('1231','期末余额')", {}) == Decimal("150")
    assert await parser.execute("TB('1231-02', '期末余额') * -1", {}) == Decimal("-50")

    opening = ReportFormulaParser(db, pid, 2025)
    opening._use_opening = True
    assert await opening.execute("TB('1231', '期末余额')", {}) == Decimal("50")
