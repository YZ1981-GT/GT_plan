"""外币折算服务测试

Validates: Requirements 6.6
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project
from app.models.consolidation_models import ForexTranslation
from app.models.consolidation_schemas import ForexRates
from app.services import forex_service as svc

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


class TestForexService:
    """外币折算逻辑测试"""

    @pytest.mark.asyncio
    async def test_translate_amount_with_rate(self):
        """汇率折算"""
        result = svc.translate_amount(Decimal("1000"), Decimal("7.2"), "bs")
        assert result == Decimal("7200")

    @pytest.mark.asyncio
    async def test_translate_amount_no_rate(self):
        """无汇率返回原值"""
        result = svc.translate_amount(Decimal("1000"), None, "bs")
        assert result == Decimal("1000")

    @pytest.mark.asyncio
    async def test_translate_amount_zero_rate(self):
        """零汇率返回原值"""
        result = svc.translate_amount(Decimal("1000"), Decimal("0"), "bs")
        assert result == Decimal("1000")

    @pytest.mark.asyncio
    async def test_create_forex_record(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        rates = ForexRates(
            bs_rate=Decimal("7.2"),
            pl_rate=Decimal("7.15"),
            avg_rate=Decimal("7.18"),
            equity_rate=Decimal("7.0"),
        )
        result = svc.create_or_update_forex(db_session, project.id, 2024, "002", rates)
        assert result.company_code == "002"
        assert result.bs_rate == Decimal("7.2")

    @pytest.mark.asyncio
    async def test_get_forex_list(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        rates = ForexRates(
            bs_rate=Decimal("7.2"),
            pl_rate=Decimal("7.15"),
            avg_rate=Decimal("7.18"),
        )
        svc.create_or_update_forex(db_session, project.id, 2024, "002", rates)
        forex_list = svc.get_forex_list(db_session, project.id, 2024)
        assert len(forex_list) == 1
        assert forex_list[0].company_code == "002"

    @pytest.mark.asyncio
    async def test_delete_forex(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        rates = ForexRates(bs_rate=Decimal("7.2"), pl_rate=Decimal("7.15"))
        forex = svc.create_or_update_forex(db_session, project.id, 2024, "002", rates)
        result = svc.delete_forex(db_session, forex.id, project.id)
        assert result is True
        forex_list = svc.get_forex_list(db_session, project.id, 2024)
        assert len(forex_list) == 0
