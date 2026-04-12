"""少数股东权益服务测试

Validates: Requirements 6.5
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project
from app.models.consolidation_models import MinorityInterest
from app.models.consolidation_schemas import MinorityInterestInput
from app.services import minority_interest_service as svc

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


class TestMinorityInterestService:
    """少数股东权益计算测试"""

    @pytest.mark.asyncio
    async def test_calculate_mi_result(self):
        """少数股东损益计算"""
        result = svc.calculate_minority_result(
            subsidiary_net_assets=Decimal("1000"),
            minority_share_ratio=Decimal("25"),
            subsidiary_net_profit=Decimal("200"),
        )
        assert result.minority_equity == Decimal("250")
        assert result.minority_profit == Decimal("50")

    @pytest.mark.asyncio
    async def test_calculate_with_none_inputs(self):
        """空值输入"""
        result = svc.calculate_minority_result(
            subsidiary_net_assets=None,
            minority_share_ratio=Decimal("25"),
            subsidiary_net_profit=Decimal("200"),
        )
        assert result.minority_equity is None

    @pytest.mark.asyncio
    async def test_create_or_update_mi(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        input_data = MinorityInterestInput(
            company_code="002",
            company_name="子公司A",
            opening_equity=Decimal("800"),
            current_net_profit=Decimal("200"),
            net_assets=Decimal("1000"),
            minority_share_ratio=Decimal("25"),
        )
        result = svc.create_or_update_mi(db_session, project.id, 2024, input_data)
        assert result.company_code == "002"
        assert result.minority_share_ratio == Decimal("25")

    @pytest.mark.asyncio
    async def test_get_mi_list(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        input_data = MinorityInterestInput(
            company_code="002",
            company_name="子公司A",
            opening_equity=Decimal("800"),
            current_net_profit=Decimal("200"),
            net_assets=Decimal("1000"),
            minority_share_ratio=Decimal("25"),
        )
        svc.create_or_update_mi(db_session, project.id, 2024, input_data)
        mi_list = svc.get_mi_list(db_session, project.id, 2024)
        assert len(mi_list) == 1
        assert mi_list[0].company_code == "002"

    @pytest.mark.asyncio
    async def test_delete_mi(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        input_data = MinorityInterestInput(
            company_code="002",
            company_name="子公司A",
            opening_equity=Decimal("800"),
            current_net_profit=Decimal("200"),
            net_assets=Decimal("1000"),
            minority_share_ratio=Decimal("25"),
        )
        mi = svc.create_or_update_mi(db_session, project.id, 2024, input_data)
        result = svc.delete_mi(db_session, mi.id, project.id)
        assert result is True
        mi_list = svc.get_mi_list(db_session, project.id, 2024)
        assert len(mi_list) == 0
