"""商誉计算服务测试

Validates: Requirements 6.4
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project
from app.models.consolidation_models import GoodwillCalc
from app.models.consolidation_schemas import GoodwillInput
from app.services import goodwill_service as svc

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


class TestGoodwillService:
    """商誉计算逻辑测试"""

    @pytest.mark.asyncio
    async def test_calculate_positive_goodwill(self):
        """正商誉计算"""
        goodwill, is_neg, treatment = svc.calculate_goodwill(
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("80"),
        )
        assert goodwill == Decimal("360")
        assert is_neg is False
        assert treatment is None

    @pytest.mark.asyncio
    async def test_calculate_negative_goodwill(self):
        """负商誉计算"""
        goodwill, is_neg, treatment = svc.calculate_goodwill(
            acquisition_cost=Decimal("500"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("80"),
        )
        assert goodwill == Decimal("-140")
        assert is_neg is True

    @pytest.mark.asyncio
    async def test_calculate_with_none_inputs(self):
        """空值输入"""
        goodwill, is_neg, treatment = svc.calculate_goodwill(
            acquisition_cost=None,
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("80"),
        )
        assert goodwill is None

    @pytest.mark.asyncio
    async def test_create_goodwill_record(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            company_code="002",
            company_name="子公司A",
            acquisition_date="2024-01-01",
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("80"),
        )
        result = svc.create_goodwill(db_session, project.id, 2024, input_data)
        assert result.company_code == "002"
        assert result.goodwill_amount == Decimal("360")
        assert result.is_negative_goodwill is False

    @pytest.mark.asyncio
    async def test_record_impairment(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            company_code="002",
            company_name="子公司A",
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("80"),
        )
        goodwill = svc.create_goodwill(db_session, project.id, 2024, input_data)
        result = svc.record_impairment(db_session, goodwill.id, project.id, Decimal("50"))
        assert result.current_year_impairment == Decimal("50")
        assert result.accumulated_impairment == Decimal("50")

    @pytest.mark.asyncio
    async def test_delete_goodwill(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            company_code="002",
            company_name="子公司A",
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("80"),
        )
        goodwill = svc.create_goodwill(db_session, project.id, 2024, input_data)
        result = svc.delete_goodwill(db_session, goodwill.id, project.id)
        assert result is True
