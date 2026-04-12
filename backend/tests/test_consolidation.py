"""集团架构和组成部分审计师服务测试

Validates: Requirements 6.3, 6.5, 6.7
测试架构树构建、循环引用检测、指令锁定逻辑
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus
from app.models.core import Project
from app.models.consolidation_models import (
    Company,
    ComponentAuditor,
    ComponentInstruction,
    ComponentResult,
    InstructionStatus,
    EvaluationStatus,
    CompetenceRating,
    OpinionTypeEnum,
)
from app.models.consolidation_schemas import (
    CompanyCreate,
    ComponentAuditorCreate,
    ComponentAuditorUpdate,
    InstructionCreate,
    InstructionUpdate,
    ComponentResultCreate,
    InstructionStatus as SchemaInstructionStatus,
)
from app.services.group_structure_service import (
    GroupStructureService,
    _build_tree,
    _detect_circular_reference,
)
from app.services.component_auditor_service import ComponentAuditorService

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
        client_name="Test Client",
        status=ProjectStatus.created,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


# =============================================================================
# GroupStructureService - 架构树构建测试
# =============================================================================


class TestBuildTree:
    """测试 _build_tree 架构树构建逻辑"""

    def test_build_tree_flat_list(self):
        """从扁平列表构建基础树结构"""
        companies = [
            Company(
                id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                company_code="A",
                company_name="母公司A",
                parent_code=None,
                consol_level=0,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
            Company(
                id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                company_code="B",
                company_name="子公司B",
                parent_code="A",
                consol_level=1,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
        ]
        tree = _build_tree(companies)
        assert len(tree) == 1  # 只有一个根节点
        assert tree[0].company_code == "A"
        assert len(tree[0].children) == 1
        assert tree[0].children[0].company_code == "B"

    def test_build_tree_multiple_roots(self):
        """多个独立根节点（无父公司的公司）"""
        companies = [
            Company(
                id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                company_code="A",
                company_name="母公司A",
                parent_code=None,
                consol_level=0,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
            Company(
                id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                company_code="B",
                company_name="母公司B",
                parent_code=None,
                consol_level=0,
                ultimate_code="B",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
        ]
        tree = _build_tree(companies)
        assert len(tree) == 2
        codes = {node.company_code for node in tree}
        assert codes == {"A", "B"}

    def test_build_tree_deep_nesting(self):
        """多层嵌套树结构（爷爷 -> 爸 -> 子）"""
        companies = [
            Company(
                id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                company_code="ROOT",
                company_name="母公司",
                parent_code=None,
                consol_level=0,
                ultimate_code="ROOT",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
            Company(
                id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                company_code="L1",
                company_name="一级子公司",
                parent_code="ROOT",
                consol_level=1,
                ultimate_code="ROOT",
                ownership_type="direct",
                ownership_percentage=Decimal("80"),
                consolidation_method="full",
                is_deleted=False,
            ),
            Company(
                id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                company_code="L2",
                company_name="二级子公司",
                parent_code="L1",
                consol_level=2,
                ultimate_code="ROOT",
                ownership_type="direct",
                ownership_percentage=Decimal("60"),
                consolidation_method="full",
                is_deleted=False,
            ),
        ]
        tree = _build_tree(companies)
        assert len(tree) == 1
        assert tree[0].company_code == "ROOT"
        assert tree[0].children[0].company_code == "L1"
        assert tree[0].children[0].children[0].company_code == "L2"

    def test_build_tree_orphaned_nodes(self):
        """孤立节点（父公司不存在）作为根节点"""
        companies = [
            Company(
                id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                company_code="ORPHAN",
                company_name="孤立节点",
                parent_code="NONEXISTENT",
                consol_level=1,
                ultimate_code="ORPHAN",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
        ]
        tree = _build_tree(companies)
        assert len(tree) == 1
        assert tree[0].company_code == "ORPHAN"
        assert tree[0].children == []


# =============================================================================
# GroupStructureService - 循环引用检测测试
# =============================================================================


class TestCircularReferenceDetection:
    """测试 _detect_circular_reference 循环引用检测"""

    @pytest.mark.asyncio
    async def test_no_circular_reference(self, db_session: AsyncSession):
        """无循环引用时返回空列表"""
        project = await _create_test_project(db_session)
        companies = [
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="A",
                company_name="母公司A",
                parent_code=None,
                consol_level=0,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="B",
                company_name="子公司B",
                parent_code="A",
                consol_level=1,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="C",
                company_name="子公司C",
                parent_code="A",
                consol_level=1,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
        ]
        db_session.add_all(companies)
        await db_session.commit()
        errors = _detect_circular_reference(db_session, project.id)
        assert errors == []

    @pytest.mark.asyncio
    async def test_self_reference_cycle(self, db_session: AsyncSession):
        """A -> A 自身循环引用"""
        project = await _create_test_project(db_session)
        company = Company(
            id=uuid.uuid4(),
            project_id=project.id,
            company_code="A",
            company_name="母公司A",
            parent_code="A",  # 自身引用！
            consol_level=1,
            ultimate_code="A",
            ownership_type="direct",
            ownership_percentage=Decimal("100"),
            consolidation_method="full",
            is_deleted=False,
        )
        db_session.add(company)
        await db_session.commit()
        errors = _detect_circular_reference(db_session, project.id)
        assert len(errors) >= 1
        assert "循环引用" in errors[0] or "A" in errors[0]

    @pytest.mark.asyncio
    async def test_two_node_cycle(self, db_session: AsyncSession):
        """A -> B -> A 双向循环引用"""
        project = await _create_test_project(db_session)
        companies = [
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="A",
                company_name="母公司A",
                parent_code="B",
                consol_level=1,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="B",
                company_name="母公司B",
                parent_code="A",
                consol_level=1,
                ultimate_code="B",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
        ]
        db_session.add_all(companies)
        await db_session.commit()
        errors = _detect_circular_reference(db_session, project.id)
        assert len(errors) >= 1
        cycle_str = errors[0]
        assert "A" in cycle_str or "B" in cycle_str

    @pytest.mark.asyncio
    async def test_three_node_cycle(self, db_session: AsyncSession):
        """A -> B -> C -> A 三节点循环引用"""
        project = await _create_test_project(db_session)
        companies = [
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="A",
                company_name="A",
                parent_code="C",
                consol_level=1,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="B",
                company_name="B",
                parent_code="A",
                consol_level=2,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="C",
                company_name="C",
                parent_code="B",
                consol_level=3,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
        ]
        db_session.add_all(companies)
        await db_session.commit()
        errors = _detect_circular_reference(db_session, project.id)
        assert len(errors) >= 1
        cycle_str = errors[0]
        # Cycle should involve A, B, C
        assert "A" in cycle_str and "C" in cycle_str

    @pytest.mark.asyncio
    async def test_deleted_company_ignored(self, db_session: AsyncSession):
        """已删除公司不参与循环检测"""
        project = await _create_test_project(db_session)
        companies = [
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="A",
                company_name="母公司A",
                parent_code="B",
                consol_level=1,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=True,  # 已删除
            ),
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="B",
                company_name="母公司B",
                parent_code=None,
                consol_level=0,
                ultimate_code="B",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
        ]
        db_session.add_all(companies)
        await db_session.commit()
        errors = _detect_circular_reference(db_session, project.id)
        # 已删除的 A 不参与检测，不应产生循环引用
        assert errors == []

    @pytest.mark.asyncio
    async def test_independent_branches_no_cycle(self, db_session: AsyncSession):
        """独立分支无循环"""
        project = await _create_test_project(db_session)
        companies = [
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="A",
                company_name="A",
                parent_code=None,
                consol_level=0,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="B",
                company_name="B",
                parent_code="A",
                consol_level=1,
                ultimate_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="C",
                company_name="C",
                parent_code=None,
                consol_level=0,
                ultimate_code="C",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
            Company(
                id=uuid.uuid4(),
                project_id=project.id,
                company_code="D",
                company_name="D",
                parent_code="C",
                consol_level=1,
                ultimate_code="C",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
                is_deleted=False,
            ),
        ]
        db_session.add_all(companies)
        await db_session.commit()
        errors = _detect_circular_reference(db_session, project.id)
        assert errors == []


# =============================================================================
# GroupStructureService - 集成测试
# =============================================================================


class TestGroupStructureService:
    """测试 GroupStructureService 集成功能"""

    @pytest.mark.asyncio
    async def test_create_company_tree_building(self, db_session: AsyncSession):
        """创建公司后树结构正确构建"""
        project = await _create_test_project(db_session)
        service = GroupStructureService(db_session)

        # 创建根公司
        await service.create_company(
            project.id,
            CompanyCreate(
                company_code="PARENT",
                company_name="母公司",
                parent_code=None,
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
            ),
        )

        # 创建子公司
        await service.create_company(
            project.id,
            CompanyCreate(
                company_code="CHILD",
                company_name="子公司",
                parent_code="PARENT",
                ownership_type="direct",
                ownership_percentage=Decimal("80"),
                consolidation_method="full",
            ),
        )

        # 获取树
        tree = await service.get_company_tree(project.id)
        assert len(tree) == 1
        assert tree[0].company_code == "PARENT"
        assert len(tree[0].children) == 1
        assert tree[0].children[0].company_code == "CHILD"

    @pytest.mark.asyncio
    async def test_validate_structure_no_cycle(self, db_session: AsyncSession):
        """正常结构验证通过"""
        project = await _create_test_project(db_session)
        service = GroupStructureService(db_session)

        await service.create_company(
            project.id,
            CompanyCreate(
                company_code="A",
                company_name="A",
                parent_code=None,
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
            ),
        )
        await service.create_company(
            project.id,
            CompanyCreate(
                company_code="B",
                company_name="B",
                parent_code="A",
                ownership_type="direct",
                ownership_percentage=Decimal("100"),
                consolidation_method="full",
            ),
        )

        errors = await service.validate_structure(project.id)
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_structure_detects_cycle(self, db_session: AsyncSession):
        """循环引用被检测"""
        project = await _create_test_project(db_session)
        service = GroupStructureService(db_session)

        # 创建两个公司并制造循环
        company_a = Company(
            id=uuid.uuid4(),
            project_id=project.id,
            company_code="A",
            company_name="A",
            parent_code="B",
            consol_level=1,
            ultimate_code="A",
            ownership_type="direct",
            ownership_percentage=Decimal("100"),
            consolidation_method="full",
            is_deleted=False,
        )
        company_b = Company(
            id=uuid.uuid4(),
            project_id=project.id,
            company_code="B",
            company_name="B",
            parent_code="A",
            consol_level=2,
            ultimate_code="B",
            ownership_type="direct",
            ownership_percentage=Decimal("100"),
            consolidation_method="full",
            is_deleted=False,
        )
        db_session.add_all([company_a, company_b])
        await db_session.commit()

        errors = await service.validate_structure(project.id)
        assert len(errors) >= 1
        assert "循环引用" in errors[0]


# =============================================================================
# ComponentAuditorService - 指令锁定逻辑测试
# =============================================================================


class TestInstructionLockLogic:
    """测试审计指令的创建和锁定逻辑"""

    @pytest.mark.asyncio
    async def test_instruction_draft_can_update(self, db_session: AsyncSession):
        """草稿状态的指令可以更新"""
        project = await _create_test_project(db_session)
        service = ComponentAuditorService(db_session)

        auditor = await service.create_auditor(
            project.id,
            ComponentAuditorCreate(
                auditor_name="审计师A",
                auditor_code="A001",
                email="auditor@test.com",
                competence=CompetenceRating.good,
                evaluation_status=EvaluationStatus.qualified,
                evaluation_date=date(2024, 1, 1),
                evaluation_expiry=date(2025, 1, 1),
            ),
        )

        instruction = await service.create_instruction(
            project.id,
            InstructionCreate(
                component_auditor_id=auditor.id,
                instruction_type="初审",
                instruction_content="请完成初审工作",
                instruction_date=date(2024, 3, 1),
                due_date=date(2024, 3, 15),
            ),
        )

        # 草稿状态可以更新
        updated = await service.update_instruction(
            instruction.id,
            InstructionUpdate(instruction_content="更新后的内容"),
        )
        assert updated is not None
        assert updated.instruction_content == "更新后的内容"

    @pytest.mark.asyncio
    async def test_instruction_sent_cannot_update(self, db_session: AsyncSession):
        """已发送状态的指令不能更新（锁定）"""
        project = await _create_test_project(db_session)
        service = ComponentAuditorService(db_session)

        auditor = await service.create_auditor(
            project.id,
            ComponentAuditorCreate(
                auditor_name="审计师B",
                auditor_code="B001",
                email="auditor2@test.com",
                competence=CompetenceRating.good,
                evaluation_status=EvaluationStatus.qualified,
                evaluation_date=date(2024, 1, 1),
                evaluation_expiry=date(2025, 1, 1),
            ),
        )

        instruction = await service.create_instruction(
            project.id,
            InstructionCreate(
                component_auditor_id=auditor.id,
                instruction_type="终审",
                instruction_content="请完成终审",
                instruction_date=date(2024, 6, 1),
                due_date=date(2024, 6, 30),
                status=SchemaInstructionStatus.sent,  # 直接创建为已发送状态
            ),
        )

        # 已发送状态不能更新，应抛出异常
        with pytest.raises(ValueError, match="仅草稿状态可更新"):
            await service.update_instruction(
                instruction.id,
                InstructionUpdate(instruction_content="尝试更新"),
            )

    @pytest.mark.asyncio
    async def test_instruction_locked_after_send(self, db_session: AsyncSession):
        """发送指令后锁定"""
        project = await _create_test_project(db_session)
        service = ComponentAuditorService(db_session)

        auditor = await service.create_auditor(
            project.id,
            ComponentAuditorCreate(
                auditor_name="审计师C",
                auditor_code="C001",
                email="auditor3@test.com",
                competence=CompetenceRating.good,
                evaluation_status=EvaluationStatus.qualified,
                evaluation_date=date(2024, 1, 1),
                evaluation_expiry=date(2025, 1, 1),
            ),
        )

        instruction = await service.create_instruction(
            project.id,
            InstructionCreate(
                component_auditor_id=auditor.id,
                instruction_type="复核",
                instruction_content="请复核报告",
                instruction_date=date(2024, 7, 1),
                due_date=date(2024, 7, 20),
            ),
        )

        # 发送指令（锁定）
        sent_instruction = await service.send_instruction(instruction.id)
        assert sent_instruction.status == InstructionStatus.sent

        # 发送后尝试更新应被拒绝
        with pytest.raises(ValueError, match="仅草稿状态可更新"):
            await service.update_instruction(
                instruction.id,
                InstructionUpdate(instruction_content="锁定后尝试修改"),
            )

    @pytest.mark.asyncio
    async def test_instruction_accepted_cannot_update(self, db_session: AsyncSession):
        """已接收（accepted）状态的指令不能更新"""
        project = await _create_test_project(db_session)
        service = ComponentAuditorService(db_session)

        auditor = await service.create_auditor(
            project.id,
            ComponentAuditorCreate(
                auditor_name="审计师D",
                auditor_code="D001",
                email="auditor4@test.com",
                competence=CompetenceRating.good,
                evaluation_status=EvaluationStatus.qualified,
                evaluation_date=date(2024, 1, 1),
                evaluation_expiry=date(2025, 1, 1),
            ),
        )

        instruction = await service.create_instruction(
            project.id,
            InstructionCreate(
                component_auditor_id=auditor.id,
                instruction_type="审计",
                instruction_content="执行审计",
                instruction_date=date(2024, 8, 1),
                due_date=date(2024, 8, 15),
            ),
        )

        # 发送后接收
        await service.send_instruction(instruction.id)
        accepted = await service.accept_result(
            uuid.uuid4()  # dummy, this tests instruction lock not result flow
        )

        # 即使指令存在，状态非 draft 也不能更新
        # 先确保指令是非草稿状态
        from app.models.consolidation_models import ComponentInstruction
        db_session.query(ComponentInstruction).filter(
            ComponentInstruction.id == instruction.id
        ).update({"status": InstructionStatus.accepted})
        await db_session.commit()

        with pytest.raises(ValueError, match="仅草稿状态可更新"):
            await service.update_instruction(
                instruction.id,
                InstructionUpdate(instruction_content="已接收后尝试修改"),
            )

    @pytest.mark.asyncio
    async def test_auditor_belongs_to_project(self, db_session: AsyncSession):
        """审计师必须属于指定项目"""
        project = await _create_test_project(db_session)
        other_project = await _create_test_project(db_session)
        service = ComponentAuditorService(db_session)

        auditor = await service.create_auditor(
            project.id,
            ComponentAuditorCreate(
                auditor_name="审计师E",
                auditor_code="E001",
                email="auditor5@test.com",
                competence=CompetenceRating.good,
                evaluation_status=EvaluationStatus.qualified,
                evaluation_date=date(2024, 1, 1),
                evaluation_expiry=date(2025, 1, 1),
            ),
        )

        # 尝试用错误项目ID创建指令
        with pytest.raises(ValueError, match="不属于该项目"):
            await service.create_instruction(
                other_project.id,  # 错误的项目
                InstructionCreate(
                    component_auditor_id=auditor.id,
                    instruction_type="测试",
                    instruction_content="测试",
                    instruction_date=date(2024, 1, 1),
                    due_date=date(2024, 1, 15),
                ),
            )
