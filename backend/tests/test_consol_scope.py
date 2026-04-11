"""合并范围服务测试

Validates: Requirements 6.1, 6.2
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project
from app.models.consolidation_models import ConsolScope, ScopeCompanyType
from app.models.consolidation_schemas import ConsolScopeCreate, ConsolScopeUpdate, ConsolScopeBatchUpdate
from app.services import consol_scope_service as svc

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
    project = Project(
        id=uuid.uuid4(),
        name="Test Project",
        status="active",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


class TestConsolScopeService:
    """合并范围 CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_scope_item(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = ConsolScopeCreate(
            company_code="001",
            company_name="母公司",
            company_type=ScopeCompanyType.PARENT,
            ownership_ratio=Decimal("100"),
            year=2024,
        )
        result = svc.create_scope_item(db_session, project.id, data)
        assert result.company_code == "001"
        assert result.company_name == "母公司"
        assert result.ownership_ratio == Decimal("100")

    @pytest.mark.asyncio
    async def test_get_scope_list(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = ConsolScopeCreate(
            company_code="001",
            company_name="母公司",
            company_type=ScopeCompanyType.PARENT,
            ownership_ratio=Decimal("100"),
            year=2024,
        )
        svc.create_scope_item(db_session, project.id, data)
        scopes = svc.get_scope_list(db_session, project.id, 2024)
        assert len(scopes) == 1
        assert scopes[0].company_code == "001"

    @pytest.mark.asyncio
    async def test_update_scope_item(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = ConsolScopeCreate(
            company_code="001",
            company_name="母公司",
            company_type=ScopeCompanyType.PARENT,
            ownership_ratio=Decimal("100"),
            year=2024,
        )
        created = svc.create_scope_item(db_session, project.id, data)
        update_data = ConsolScopeUpdate(company_name="母公司(更新)")
        updated = svc.update_scope_item(db_session, created.id, project.id, update_data)
        assert updated is not None
        assert updated.company_name == "母公司(更新)"

    @pytest.mark.asyncio
    async def test_delete_scope_item(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = ConsolScopeCreate(
            company_code="001",
            company_name="母公司",
            company_type=ScopeCompanyType.PARENT,
            ownership_ratio=Decimal("100"),
            year=2024,
        )
        created = svc.create_scope_item(db_session, project.id, data)
        result = svc.delete_scope_item(db_session, created.id, project.id)
        assert result is True
        scopes = svc.get_scope_list(db_session, project.id, 2024)
        assert len(scopes) == 0

    @pytest.mark.asyncio
    async def test_get_scope_summary(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        # Add parent
        svc.create_scope_item(db_session, project.id, ConsolScopeCreate(
            company_code="001", company_name="母公司",
            company_type=ScopeCompanyType.PARENT, ownership_ratio=Decimal("100"), year=2024
        ))
        # Add subsidiary
        svc.create_scope_item(db_session, project.id, ConsolScopeCreate(
            company_code="002", company_name="子公司A",
            company_type=ScopeCompanyType.SUBSIDIARY, ownership_ratio=Decimal("75"), year=2024
        ))
        summary = svc.get_scope_summary(db_session, project.id, 2024)
        assert summary.total_companies == 2
        assert summary.parent_count == 1
        assert summary.subsidiary_count == 1
