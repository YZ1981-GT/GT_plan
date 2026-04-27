"""ProjectWizardService 单元测试

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus
from app.models.core import Project
from app.models.audit_platform_schemas import (
    BasicInfoSchema,
    WizardStep,
)

# SQLite JSONB compat
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话（每次重建表）。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


def _make_basic_info(**overrides) -> BasicInfoSchema:
    """构造 BasicInfoSchema 测试数据。"""
    defaults = {
        "client_name": "测试客户",
        "audit_year": 2024,
        "project_type": "annual",
        "accounting_standard": "enterprise",
    }
    defaults.update(overrides)
    return BasicInfoSchema(**defaults)


async def _complete_confirmation_steps(project_id: uuid.UUID, db_session: AsyncSession) -> None:
    from app.services import project_wizard_service as svc

    await svc.update_step(
        project_id,
        WizardStep.account_import,
        {"file_name": "chart.xlsx", "imported_count": 100},
        db_session,
    )
    await svc.update_step(
        project_id,
        WizardStep.account_mapping,
        {"mapped_count": 10, "total_count": 10, "completion_rate": 100},
        db_session,
    )
    await svc.update_step(
        project_id,
        WizardStep.materiality,
        {"benchmark_type": "revenue"},
        db_session,
    )
    await svc.update_step(
        project_id,
        WizardStep.team_assignment,
        {"members": []},
        db_session,
    )


# ===================================================================
# create_project
# ===================================================================


class TestCreateProject:
    """Validates: Requirements 1.2, 1.3"""

    @pytest.mark.asyncio
    async def test_create_project_success(self, db_session: AsyncSession):
        from app.services import project_wizard_service as svc

        data = _make_basic_info()
        project = await svc.create_project(data, db_session)

        assert project.id is not None
        assert project.client_name == "测试客户"
        assert project.status == ProjectStatus.created
        assert project.wizard_state is not None
        # basic_info 步骤应已完成
        assert project.wizard_state["steps"]["basic_info"]["completed"] is True

    @pytest.mark.asyncio
    async def test_create_project_with_partner_and_manager(self, db_session: AsyncSession):
        from app.services import project_wizard_service as svc

        partner_id = uuid.uuid4()
        manager_id = uuid.uuid4()
        data = _make_basic_info(signing_partner_id=partner_id, manager_id=manager_id)
        project = await svc.create_project(data, db_session)

        assert project.partner_id == partner_id
        assert project.manager_id == manager_id

    @pytest.mark.asyncio
    async def test_create_project_name_format(self, db_session: AsyncSession):
        from app.services import project_wizard_service as svc

        data = _make_basic_info(client_name="ABC公司", audit_year=2025)
        project = await svc.create_project(data, db_session)

        assert project.name == "ABC公司_2025"


# ===================================================================
# get_wizard_state
# ===================================================================


class TestGetWizardState:
    """Validates: Requirements 1.4, 1.5"""

    @pytest.mark.asyncio
    async def test_get_wizard_state_after_create(self, db_session: AsyncSession):
        from app.services import project_wizard_service as svc

        data = _make_basic_info()
        project = await svc.create_project(data, db_session)
        state = await svc.get_wizard_state(project.id, db_session)

        assert state.project_id == project.id
        assert state.current_step == WizardStep.basic_info
        assert state.completed is False
        assert "basic_info" in state.steps

    @pytest.mark.asyncio
    async def test_get_wizard_state_not_found(self, db_session: AsyncSession):
        from app.services import project_wizard_service as svc

        with pytest.raises(Exception) as exc_info:
            await svc.get_wizard_state(uuid.uuid4(), db_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_preserves_step_data(self, db_session: AsyncSession):
        """断点续做：退出后重新进入恢复已保存步骤数据。"""
        from app.services import project_wizard_service as svc

        data = _make_basic_info()
        project = await svc.create_project(data, db_session)

        # 更新 account_import 步骤
        await svc.update_step(
            project.id,
            WizardStep.account_import,
            {"file_name": "chart.xlsx", "imported_count": 100},
            db_session,
        )

        # 模拟"退出后重新进入"：重新获取状态
        state = await svc.get_wizard_state(project.id, db_session)
        assert "account_import" in state.steps
        assert state.steps["account_import"].data["file_name"] == "chart.xlsx"
        assert state.steps["account_import"].data["imported_count"] == 100


# ===================================================================
# update_step
# ===================================================================


class TestUpdateStep:
    """Validates: Requirements 1.3, 1.4, 1.5, 1.8"""

    @pytest.mark.asyncio
    async def test_update_step_success(self, db_session: AsyncSession):
        from app.services import project_wizard_service as svc

        project = await svc.create_project(_make_basic_info(), db_session)
        state = await svc.update_step(
            project.id,
            WizardStep.account_import,
            {"file_name": "test.xlsx"},
            db_session,
        )

        assert "account_import" in state.steps
        assert state.steps["account_import"].completed is True
        assert state.current_step == WizardStep.account_import

    @pytest.mark.asyncio
    async def test_update_step_dependency_not_met(self, db_session: AsyncSession):
        """跳过前置步骤应报错。"""
        from app.services import project_wizard_service as svc

        project = await svc.create_project(_make_basic_info(), db_session)

        with pytest.raises(Exception) as exc_info:
            # account_mapping 依赖 account_import，但 account_import 未完成
            await svc.update_step(
                project.id,
                WizardStep.account_mapping,
                {"mappings": []},
                db_session,
            )
        assert exc_info.value.status_code == 400
        assert "account_import" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_update_step_overwrite_existing(self, db_session: AsyncSession):
        """修改已完成步骤的数据。"""
        from app.services import project_wizard_service as svc

        project = await svc.create_project(_make_basic_info(), db_session)

        # 第一次更新
        await svc.update_step(
            project.id,
            WizardStep.account_import,
            {"file_name": "old.xlsx"},
            db_session,
        )

        # 第二次更新（覆盖）
        state = await svc.update_step(
            project.id,
            WizardStep.account_import,
            {"file_name": "new.xlsx"},
            db_session,
        )

        assert state.steps["account_import"].data["file_name"] == "new.xlsx"

    @pytest.mark.asyncio
    async def test_update_step_after_confirm_rejected(self, db_session: AsyncSession):
        """项目已确认后不能修改向导步骤。"""
        from app.services import project_wizard_service as svc

        project = await svc.create_project(_make_basic_info(), db_session)

        # 手动将状态改为 planning（模拟已确认）
        project.status = ProjectStatus.planning
        await db_session.commit()

        with pytest.raises(Exception) as exc_info:
            await svc.update_step(
                project.id,
                WizardStep.account_import,
                {"file_name": "test.xlsx"},
                db_session,
            )
        assert exc_info.value.status_code == 400
        assert "已确认" in str(exc_info.value.detail)


# ===================================================================
# validate_step
# ===================================================================


class TestValidateStep:
    """Validates: Requirements 1.8"""

    @pytest.mark.asyncio
    async def test_validate_basic_info_valid(self, db_session: AsyncSession):
        from app.services import project_wizard_service as svc

        project = await svc.create_project(_make_basic_info(), db_session)
        result = await svc.validate_step(project.id, WizardStep.basic_info, db_session)

        assert result.valid is True
        assert len(result.messages) == 0

    @pytest.mark.asyncio
    async def test_validate_step_dependency_missing(self, db_session: AsyncSession):
        from app.services import project_wizard_service as svc

        project = await svc.create_project(_make_basic_info(), db_session)
        # 校验 account_mapping，但 account_import 未完成
        result = await svc.validate_step(
            project.id, WizardStep.account_mapping, db_session
        )

        assert result.valid is False
        assert any("account_import" in m.field for m in result.messages)

    @pytest.mark.asyncio
    async def test_validate_confirmation_all_steps_needed(self, db_session: AsyncSession):
        from app.services import project_wizard_service as svc

        project = await svc.create_project(_make_basic_info(), db_session)
        result = await svc.validate_step(
            project.id, WizardStep.confirmation, db_session
        )

        assert result.valid is False
        assert {m.field for m in result.messages} >= {
            "account_import",
            "account_mapping",
            "materiality",
            "team_assignment",
        }

    @pytest.mark.asyncio
    async def test_validate_confirmation_ready_after_required_steps(self, db_session: AsyncSession):
        from app.services import project_wizard_service as svc

        project = await svc.create_project(_make_basic_info(), db_session)
        await _complete_confirmation_steps(project.id, db_session)

        result = await svc.validate_step(
            project.id, WizardStep.confirmation, db_session
        )

        assert result.valid is True
        assert len(result.messages) == 0


# ===================================================================
# confirm_project
# ===================================================================


class TestConfirmProject:
    """Validates: Requirements 1.7"""

    @pytest.mark.asyncio
    async def test_confirm_project_success(self, db_session: AsyncSession):
        from app.services import project_wizard_service as svc

        project = await svc.create_project(_make_basic_info(), db_session)
        await _complete_confirmation_steps(project.id, db_session)

        confirmed = await svc.confirm_project(project.id, db_session)

        assert confirmed.status == ProjectStatus.planning
        state = svc._parse_wizard_state(confirmed)
        assert state.completed is True

    @pytest.mark.asyncio
    async def test_confirm_project_missing_required_steps(self, db_session: AsyncSession):
        from app.services import project_wizard_service as svc

        project = await svc.create_project(_make_basic_info(), db_session)

        with pytest.raises(Exception) as exc_info:
            await svc.confirm_project(project.id, db_session)
        assert exc_info.value.status_code == 400
        assert "account_import" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_confirm_project_missing_basic_info_step(self, db_session: AsyncSession):
        """缺少基本信息步骤时确认应失败。"""
        from app.services import project_wizard_service as svc

        project = await svc.create_project(_make_basic_info(), db_session)
        project.wizard_state = {**project.wizard_state, "steps": {}}
        await db_session.commit()

        with pytest.raises(Exception) as exc_info:
            await svc.confirm_project(project.id, db_session)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_project_already_planning(self, db_session: AsyncSession):
        """已经是 planning 状态的项目不能再次确认。"""
        from app.services import project_wizard_service as svc

        project = await svc.create_project(_make_basic_info(), db_session)
        project.status = ProjectStatus.planning
        await db_session.commit()

        with pytest.raises(Exception) as exc_info:
            await svc.confirm_project(project.id, db_session)
        assert exc_info.value.status_code == 400
        assert "planning" in str(exc_info.value.detail)
