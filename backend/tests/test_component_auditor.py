"""组成部分审计师服务测试

Validates: Requirements 6.7
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project
from app.models.consolidation_models import (
    ComponentAuditor,
    ComponentInstruction,
    ComponentResult,
    InstructionStatus,
    EvaluationStatusEnum,
)
from app.models.consolidation_schemas import (
    ComponentAuditorCreate,
    ComponentAuditorUpdate,
    InstructionCreate,
    InstructionUpdate,
    ResultCreate,
    ResultUpdate,
)
from app.services import component_auditor_service as svc

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


class TestComponentAuditorService:
    """组成部分审计师 CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_auditor(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = ComponentAuditorCreate(
            auditor_code="CA001",
            auditor_name="审计师A",
            email="auditor@example.com",
            department="审计部",
        )
        result = svc.create_auditor(db_session, project.id, data)
        assert result.auditor_code == "CA001"
        assert result.auditor_name == "审计师A"

    @pytest.mark.asyncio
    async def test_get_auditors(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = ComponentAuditorCreate(
            auditor_code="CA001",
            auditor_name="审计师A",
            department="审计部",
        )
        svc.create_auditor(db_session, project.id, data)
        auditors = svc.get_auditors(db_session, project.id)
        assert len(auditors) == 1

    @pytest.mark.asyncio
    async def test_update_auditor(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = ComponentAuditorCreate(
            auditor_code="CA001",
            auditor_name="审计师A",
            department="审计部",
        )
        auditor = svc.create_auditor(db_session, project.id, data)
        update_data = ComponentAuditorUpdate(auditor_name="审计师B")
        updated = svc.update_auditor(db_session, auditor.id, project.id, update_data)
        assert updated.auditor_name == "审计师B"

    @pytest.mark.asyncio
    async def test_delete_auditor(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        data = ComponentAuditorCreate(
            auditor_code="CA001",
            auditor_name="审计师A",
            department="审计部",
        )
        auditor = svc.create_auditor(db_session, project.id, data)
        result = svc.delete_auditor(db_session, auditor.id, project.id)
        assert result is True


class TestComponentInstructionService:
    """审计指令 CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_instruction(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        auditor_data = ComponentAuditorCreate(
            auditor_code="CA001",
            auditor_name="审计师A",
            department="审计部",
        )
        auditor = svc.create_auditor(db_session, project.id, auditor_data)
        
        inst_data = InstructionCreate(
            instruction_title="检查应收账款",
            instruction_content="核对期末余额",
            instruction_type="field_review",
            due_date="2024-12-31",
        )
        result = svc.create_instruction(db_session, auditor.id, project.id, inst_data)
        assert result.instruction_title == "检查应收账款"
        assert result.instruction_status == InstructionStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_instructions_by_auditor(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        auditor_data = ComponentAuditorCreate(
            auditor_code="CA001",
            auditor_name="审计师A",
            department="审计部",
        )
        auditor = svc.create_auditor(db_session, project.id, auditor_data)
        
        inst_data = InstructionCreate(
            instruction_title="检查存货",
            instruction_content="盘点期末存货",
        )
        svc.create_instruction(db_session, auditor.id, project.id, inst_data)
        
        instructions = svc.get_instructions(db_session, project.id, auditor.id)
        assert len(instructions) == 1

    @pytest.mark.asyncio
    async def test_update_instruction(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        auditor_data = ComponentAuditorCreate(
            auditor_code="CA001",
            auditor_name="审计师A",
            department="审计部",
        )
        auditor = svc.create_auditor(db_session, project.id, auditor_data)
        
        inst_data = InstructionCreate(
            instruction_title="检查固定资产",
        )
        instruction = svc.create_instruction(db_session, auditor.id, project.id, inst_data)
        update_data = InstructionUpdate(instruction_title="检查固定资产(更新)")
        updated = svc.update_instruction(db_session, instruction.id, project.id, update_data)
        assert updated.instruction_title == "检查固定资产(更新)"


class TestComponentResultService:
    """审计结果 CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_result(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        auditor_data = ComponentAuditorCreate(
            auditor_code="CA001",
            auditor_name="审计师A",
            department="审计部",
        )
        auditor = svc.create_auditor(db_session, project.id, auditor_data)
        
        result_data = ResultCreate(
            company_code="002",
            company_name="子公司A",
            evaluation_status=EvaluationStatusEnum.QUALIFIED,
            findings="无重大问题",
        )
        result = svc.create_result(db_session, auditor.id, project.id, result_data)
        assert result.company_code == "002"
        assert result.evaluation_status == EvaluationStatusEnum.QUALIFIED

    @pytest.mark.asyncio
    async def test_update_result(self, db_session: AsyncSession):
        project = await _create_test_project(db_session)
        auditor_data = ComponentAuditorCreate(
            auditor_code="CA001",
            auditor_name="审计师A",
            department="审计部",
        )
        auditor = svc.create_auditor(db_session, project.id, auditor_data)
        
        result_data = ResultCreate(
            company_code="002",
            company_name="子公司A",
            evaluation_status=EvaluationStatusEnum.QUALIFIED,
        )
        result = svc.create_result(db_session, auditor.id, project.id, result_data)
        update_data = ResultUpdate(evaluation_status=EvaluationStatusEnum.UNQUALIFIED)
        updated = svc.update_result(db_session, result.id, project.id, update_data)
        assert updated.evaluation_status == EvaluationStatusEnum.UNQUALIFIED
