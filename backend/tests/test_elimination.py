"""抵消分录服务测试

Validates: Requirements 6.3
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project
from app.models.consolidation_models import EliminationEntry, EliminationEntryType, ReviewStatusEnum
from app.models.consolidation_schemas import EliminationCreate, EliminationEntryLine, EliminationEntryUpdate
from app.services import elimination_service as svc

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest.fixture
async def db_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()


async def _create_test_project(db: AsyncSession) -> Project:
    project = Project(id=uuid.uuid4(), name="Test Project", status="active")
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


class TestEliminationService:
    """抵消分录 CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_elimination_entry(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = EliminationCreate(
            entry_type=EliminationEntryType.INVESTMENT_ELIMINATION,
            year=2024,
            description="投资收益抵消",
            lines=[
                EliminationEntryLine(account_code="6111", account_name="投资收益", debit_amount=Decimal("100"), credit_amount=Decimal("0")),
                EliminationEntryLine(account_code="1511", account_name="长期股权投资", debit_amount=Decimal("0"), credit_amount=Decimal("100")),
            ],
        )
        entry = svc.create_elimination(db_session, project.id, data)
        assert entry.entry_no.startswith("IE-")
        assert entry.entry_type == EliminationEntryType.INVESTMENT_ELIMINATION
        assert len(entry.lines) == 2

    @pytest.mark.asyncio
    async def test_get_entries_by_year(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = EliminationCreate(
            entry_type=EliminationEntryType.INTERCOMPANY_ELIMINATION,
            year=2024,
            description="内部交易抵消",
            lines=[
                EliminationEntryLine(account_code="1122", account_name="应收账款", debit_amount=Decimal("50"), credit_amount=Decimal("0")),
                EliminationEntryLine(account_code="6001", account_name="主营业务收入", debit_amount=Decimal("0"), credit_amount=Decimal("50")),
            ],
        )
        svc.create_elimination(db_session, project.id, data)
        entries = svc.get_entries(db_session, project.id, 2024)
        assert len(entries) == 1

    @pytest.mark.asyncio
    async def test_update_elimination(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = EliminationCreate(
            entry_type=EliminationEntryType.UNREALIZED_PROFIT,
            year=2024,
            description="未实现利润",
            lines=[
                EliminationEntryLine(account_code="1301", account_name="存货", debit_amount=Decimal("20"), credit_amount=Decimal("0")),
            ],
        )
        entry = svc.create_elimination(db_session, project.id, data)
        update_data = EliminationEntryUpdate(description="更新：期末未实现利润")
        updated = svc.update_elimination(db_session, entry.id, project.id, update_data)
        assert updated.description == "更新：期末未实现利润"

    @pytest.mark.asyncio
    async def test_review_workflow(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = EliminationCreate(
            entry_type=EliminationEntryType.AR_AP_ELIMINATION,
            year=2024,
            description="应收应付抵消",
            lines=[
                EliminationEntryLine(account_code="1122", account_name="应收账款", debit_amount=Decimal("80"), credit_amount=Decimal("0")),
                EliminationEntryLine(account_code="2202", account_name="应付账款", debit_amount=Decimal("0"), credit_amount=Decimal("80")),
            ],
        )
        entry = svc.create_elimination(db_session, project.id, data)
        # Submit for review
        submitted = svc.submit_for_review(db_session, entry.id, project.id)
        assert submitted.review_status == ReviewStatusEnum.PENDING_REVIEW

    @pytest.mark.asyncio
    async def test_get_summary_by_type(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = EliminationCreate(
            entry_type=EliminationEntryType.INVESTMENT_ELIMINATION,
            year=2024,
            description="投资收益抵消",
            lines=[
                EliminationEntryLine(account_code="6111", debit_amount=Decimal("100"), credit_amount=Decimal("0")),
                EliminationEntryLine(account_code="1511", debit_amount=Decimal("0"), credit_amount=Decimal("100")),
            ],
        )
        svc.create_elimination(db_session, project.id, data)
        summaries = svc.get_summary(db_session, project.id, 2024)
        assert len(summaries) == 1
        assert summaries[0].count == 1
        assert summaries[0].total_debit == Decimal("100")
