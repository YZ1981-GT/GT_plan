"""合并范围服务测试

Validates: Requirements 6.1, 6.2
"""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project
from app.models.consolidation_models import ConsolScope, ScopeChangeType, InclusionReason
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
    from app.models.base import ProjectStatus
    project = Project(
        id=uuid.uuid4(),
        name="Test Project",
        client_name="Test Client",
        status=ProjectStatus.created
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


class TestConsolScopeService:
    """合并范围服务测试"""

    @pytest.mark.asyncio
    async def test_create_scope_item(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = ConsolScopeCreate(
            project_id=project.id,
            year=2024,
            company_code="001",
            is_included=True,
            inclusion_reason=InclusionReason.direct_control,
        )
        result = svc.create_scope_item(db_session, project.id, data)
        assert result.company_code == "001"
        assert result.year == 2024
        assert result.is_included is True
        assert result.inclusion_reason == InclusionReason.direct_control

    @pytest.mark.asyncio
    async def test_get_scope_list(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = ConsolScopeCreate(
            project_id=project.id, year=2024, company_code="001",
            is_included=True, inclusion_reason=InclusionReason.direct_control,
        )
        svc.create_scope_item(db_session, project.id, data)
        scopes = svc.get_scope_list(db_session, project.id, 2024)
        assert len(scopes) == 1

    @pytest.mark.asyncio
    async def test_get_scope_list_filter_by_year(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        # Create for 2024
        svc.create_scope_item(db_session, project.id, ConsolScopeCreate(
            project_id=project.id, year=2024, company_code="001",
            is_included=True, inclusion_reason=InclusionReason.direct_control,
        ))
        # Create for 2023
        svc.create_scope_item(db_session, project.id, ConsolScopeCreate(
            project_id=project.id, year=2023, company_code="002",
            is_included=True, inclusion_reason=InclusionReason.direct_control,
        ))
        scopes = svc.get_scope_list(db_session, project.id, 2024)
        assert len(scopes) == 1
        assert scopes[0].company_code == "001"

    @pytest.mark.asyncio
    async def test_update_scope_item(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = ConsolScopeCreate(
            project_id=project.id, year=2024, company_code="001",
            is_included=True, inclusion_reason=InclusionReason.direct_control,
        )
        scope = svc.create_scope_item(db_session, project.id, data)
        update_data = ConsolScopeUpdate(
            is_included=False,
            exclusion_reason="已出售",
            scope_change_type=ScopeChangeType.disposed,
        )
        updated = svc.update_scope_item(db_session, scope.id, project.id, update_data)
        assert updated.is_included is False
        assert updated.exclusion_reason == "已出售"
        assert updated.scope_change_type == ScopeChangeType.exclusion

    @pytest.mark.asyncio
    async def test_delete_scope_item(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = ConsolScopeCreate(
            project_id=project.id, year=2024, company_code="001",
            is_included=True, inclusion_reason=InclusionReason.direct_control,
        )
        scope = svc.create_scope_item(db_session, project.id, data)
        result = svc.delete_scope_item(db_session, scope.id, project.id)
        assert result.is_deleted is True

    @pytest.mark.asyncio
    async def test_batch_create_scope_items(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        batch = ConsolScopeBatchUpdate(
            scope_items=[
                ConsolScopeCreate(
                    project_id=project.id, year=2024, company_code="001",
                    is_included=True, inclusion_reason=InclusionReason.direct_control,
                ),
                ConsolScopeCreate(
                    project_id=project.id, year=2024, company_code="002",
                    is_included=True, inclusion_reason=InclusionReason.direct_control,
                ),
            ]
        )
        results = svc.batch_create_scope_items(db_session, project.id, batch)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_scope_summary(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        svc.create_scope_item(db_session, project.id, ConsolScopeCreate(
            project_id=project.id, year=2024, company_code="001",
            is_included=True, inclusion_reason=InclusionReason.direct_control,
        ))
        svc.create_scope_item(db_session, project.id, ConsolScopeCreate(
            project_id=project.id, year=2024, company_code="002",
            is_included=True, inclusion_reason=InclusionReason.direct_control,
        ))
        summary = svc.get_scope_summary(db_session, project.id, 2024)
        assert summary.total_companies == 2
        assert summary.included_companies == 2
        assert summary.excluded_companies == 0
        assert summary.scope_changes == 0

    @pytest.mark.asyncio
    async def test_scope_change_detection(self, db_session: AsyncSession):
        """测试范围变更检测"""
        project = await _create_test_project(db_session)
        # 新增公司
        svc.create_scope_item(db_session, project.id, ConsolScopeCreate(
            project_id=project.id, year=2024, company_code="003",
            is_included=True, inclusion_reason=InclusionReason.subsidiary,
            scope_change_type=ScopeChangeType.new_inclusion,
        ))
        # 排除公司
        svc.create_scope_item(db_session, project.id, ConsolScopeCreate(
            project_id=project.id, year=2024, company_code="004",
            is_included=False, exclusion_reason="已处置",
            scope_change_type=ScopeChangeType.exclusion,
        ))
        summary = svc.get_scope_summary(db_session, project.id, 2024)
        assert summary.scope_changes == 2
