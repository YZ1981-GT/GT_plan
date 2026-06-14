"""A13 错报汇总金额一致性 PBT

Property: 随机生成 N 条 passed adjustments，
get_uncorrected_misstatements 返回的 total_debit/total_credit
等于所有 passed 行的 debit_amount/credit_amount 之和。

max_examples=5
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.audit_platform_models import Adjustment, AdjustmentType, Materiality
from app.models.base import Base, UserRole
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.services.misstatement_summary_service import MisstatementSummaryService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_TABLES = [
    User.__table__,
    Project.__table__,
    Adjustment.__table__,
    Materiality.__table__,
]

# Strategies
amount_st = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("999999.99"), places=2)
adj_type_st = st.sampled_from([AdjustmentType.aje, AdjustmentType.rje])


def _run_in_isolated_db(coro_factory):
    async def _runner():
        engine = create_async_engine(TEST_DB_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                return await coro_factory(session)
        finally:
            await engine.dispose()
    return asyncio.run(_runner())


@given(
    amounts=st.lists(
        st.tuples(amount_st, amount_st, adj_type_st),
        min_size=1,
        max_size=8,
    ),
)
@settings(max_examples=5, deadline=None)
def test_summary_totals_match_input(amounts):
    """Property: 汇总 total_debit/total_credit == SUM(passed debit/credit)"""

    async def _body(session: AsyncSession):
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()

        session.add(User(
            id=user_id, username=f"u_{user_id.hex[:6]}", email=f"{user_id.hex[:6]}@t.com",
            hashed_password="x", role=UserRole.manager,
        ))
        await session.flush()
        session.add(Project(
            id=project_id, name="PBT项目", client_name="PBT",
            project_type=ProjectType.annual, status=ProjectStatus.execution,
            created_by=user_id,
        ))
        await session.flush()

        expected_debit = Decimal("0")
        expected_credit = Decimal("0")

        for i, (debit, credit, adj_type) in enumerate(amounts):
            session.add(Adjustment(
                project_id=project_id,
                year=2025,
                company_code="91000000XXXXXXXXXX",
                adjustment_no=f"P-{i+1:03d}",
                adjustment_type=adj_type,
                account_code=f"{1001+i}",
                debit_amount=debit,
                credit_amount=credit,
                entry_group_id=uuid.uuid4(),
                review_status="passed",
                created_by=user_id,
            ))
            expected_debit += debit
            expected_credit += credit

        await session.flush()

        svc = MisstatementSummaryService(session)
        result = await svc.get_uncorrected_misstatements(project_id, 2025)

        assert result["total_debit"] == expected_debit
        assert result["total_credit"] == expected_credit
        assert result["count"] == len(amounts)

    _run_in_isolated_db(_body)


def test_empty_passed_returns_zero():
    """无 passed 记录时返回空列表和零合计"""

    async def _body(session: AsyncSession):
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()

        session.add(User(
            id=user_id, username="empty", email="e@t.com",
            hashed_password="x", role=UserRole.manager,
        ))
        await session.flush()
        session.add(Project(
            id=project_id, name="空项目", client_name="空",
            project_type=ProjectType.annual, status=ProjectStatus.execution,
            created_by=user_id,
        ))
        await session.flush()

        svc = MisstatementSummaryService(session)
        result = await svc.get_uncorrected_misstatements(project_id, 2025)

        assert result["prior"] == []
        assert result["current"] == []
        assert result["total_debit"] == Decimal("0")
        assert result["total_credit"] == Decimal("0")

    _run_in_isolated_db(_body)
