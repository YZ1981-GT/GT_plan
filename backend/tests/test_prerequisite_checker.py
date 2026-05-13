"""PrerequisiteChecker 单元测试

覆盖 4 个操作的前置条件检查：
- recalc: account_mapping 存在且 rate >= 50%
- generate_reports: trial_balance > 0 行
- generate_workpapers: template_set 已选择
- generate_notes: financial_report > 0 行

使用 SQLite in-memory fixture。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401
import app.models.phase15_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401

from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.audit_platform_models import (  # noqa: E402
    AccountCategory,
    AccountMapping,
    MappingType,
    TbBalance,
    TrialBalance,
)
from app.models.report_models import FinancialReport, FinancialReportType  # noqa: E402
from app.services.prerequisite_checker import PrerequisiteChecker  # noqa: E402


YEAR = 2025
FAKE_PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def project(db_session: AsyncSession):
    user = User(
        id=uuid.uuid4(),
        username="admin",
        email="admin@test.com",
        hashed_password="x" * 60,
        role=UserRole.admin,
    )
    db_session.add(user)

    proj = Project(
        id=FAKE_PROJECT_ID,
        name="测试项目",
        client_name="测试客户",
        status=ProjectStatus.execution,
        wizard_state={},
    )
    db_session.add(proj)
    await db_session.flush()
    return proj


class TestRecalcPrerequisites:
    """recalc 前置条件：account_mapping 存在且 rate >= 50%"""

    @pytest.mark.asyncio
    async def test_no_tb_balance_data(self, db_session, project):
        """无余额表数据时返回导入提示"""
        checker = PrerequisiteChecker()
        result = await checker.check(db_session, FAKE_PROJECT_ID, YEAR, "recalc")
        assert result["ok"] is False
        assert "导入账套数据" in result["message"]
        assert result["prerequisite_action"] == "import_ledger"

    @pytest.mark.asyncio
    async def test_no_mapping(self, db_session, project):
        """有余额表但无映射时返回映射提示"""
        # 添加余额表数据
        for i in range(10):
            db_session.add(TbBalance(
                id=uuid.uuid4(),
                project_id=FAKE_PROJECT_ID,
                year=YEAR,
                company_code="default",
                account_code=f"100{i}",
                account_name=f"科目{i}",
            ))
        await db_session.flush()

        checker = PrerequisiteChecker()
        result = await checker.check(db_session, FAKE_PROJECT_ID, YEAR, "recalc")
        assert result["ok"] is False
        assert "映射率 0%" in result["message"]
        assert result["prerequisite_action"] == "auto_match"

    @pytest.mark.asyncio
    async def test_low_mapping_rate(self, db_session, project):
        """映射率 < 50% 时返回映射提示"""
        # 添加 10 个科目
        for i in range(10):
            db_session.add(TbBalance(
                id=uuid.uuid4(),
                project_id=FAKE_PROJECT_ID,
                year=YEAR,
                company_code="default",
                account_code=f"100{i}",
                account_name=f"科目{i}",
            ))
        # 只映射 3 个（30%）
        for i in range(3):
            db_session.add(AccountMapping(
                id=uuid.uuid4(),
                project_id=FAKE_PROJECT_ID,
                original_account_code=f"100{i}",
                standard_account_code=f"100{i}",
                mapping_type=MappingType.auto_exact,
            ))
        await db_session.flush()

        checker = PrerequisiteChecker()
        result = await checker.check(db_session, FAKE_PROJECT_ID, YEAR, "recalc")
        assert result["ok"] is False
        assert "30.0%" in result["message"]
        assert result["prerequisite_action"] == "auto_match"

    @pytest.mark.asyncio
    async def test_sufficient_mapping_rate(self, db_session, project):
        """映射率 >= 50% 时通过"""
        # 添加 10 个科目
        for i in range(10):
            db_session.add(TbBalance(
                id=uuid.uuid4(),
                project_id=FAKE_PROJECT_ID,
                year=YEAR,
                company_code="default",
                account_code=f"100{i}",
                account_name=f"科目{i}",
            ))
        # 映射 6 个（60%）
        for i in range(6):
            db_session.add(AccountMapping(
                id=uuid.uuid4(),
                project_id=FAKE_PROJECT_ID,
                original_account_code=f"100{i}",
                standard_account_code=f"100{i}",
                mapping_type=MappingType.auto_exact,
            ))
        await db_session.flush()

        checker = PrerequisiteChecker()
        result = await checker.check(db_session, FAKE_PROJECT_ID, YEAR, "recalc")
        assert result["ok"] is True


class TestReportPrerequisites:
    """generate_reports 前置条件：trial_balance > 0 行"""

    @pytest.mark.asyncio
    async def test_no_trial_balance(self, db_session, project):
        """无试算表数据时返回重算提示"""
        checker = PrerequisiteChecker()
        result = await checker.check(db_session, FAKE_PROJECT_ID, YEAR, "generate_reports")
        assert result["ok"] is False
        assert "试算表重算" in result["message"]
        assert result["prerequisite_action"] == "recalc"

    @pytest.mark.asyncio
    async def test_has_trial_balance(self, db_session, project):
        """有试算表数据时通过"""
        db_session.add(TrialBalance(
            id=uuid.uuid4(),
            project_id=FAKE_PROJECT_ID,
            year=YEAR,
            company_code="default",
            standard_account_code="1001",
            account_name="货币资金",
            account_category=AccountCategory.asset,
            unadjusted_amount=Decimal("100000.00"),
            audited_amount=Decimal("100000.00"),
        ))
        await db_session.flush()

        checker = PrerequisiteChecker()
        result = await checker.check(db_session, FAKE_PROJECT_ID, YEAR, "generate_reports")
        assert result["ok"] is True


class TestWorkpaperPrerequisites:
    """generate_workpapers 前置条件：template_set 已选择"""

    @pytest.mark.asyncio
    async def test_no_template_set(self, db_session, project):
        """未选择模板集时返回提示"""
        checker = PrerequisiteChecker()
        result = await checker.check(db_session, FAKE_PROJECT_ID, YEAR, "generate_workpapers")
        assert result["ok"] is False
        assert "底稿模板集" in result["message"]
        assert result["prerequisite_action"] == "select_template"

    @pytest.mark.asyncio
    async def test_has_template_set(self, db_session, project):
        """已选择模板集时通过"""
        project.wizard_state = {
            "template_set": {
                "template_set_id": str(uuid.uuid4()),
                "template_set_name": "标准底稿模板",
            }
        }
        await db_session.flush()

        checker = PrerequisiteChecker()
        result = await checker.check(db_session, FAKE_PROJECT_ID, YEAR, "generate_workpapers")
        assert result["ok"] is True


class TestNotesPrerequisites:
    """generate_notes 前置条件：financial_report > 0 行"""

    @pytest.mark.asyncio
    async def test_no_financial_report(self, db_session, project):
        """无报表数据时返回提示"""
        checker = PrerequisiteChecker()
        result = await checker.check(db_session, FAKE_PROJECT_ID, YEAR, "generate_notes")
        assert result["ok"] is False
        assert "生成财务报表" in result["message"]
        assert result["prerequisite_action"] == "generate_reports"

    @pytest.mark.asyncio
    async def test_has_financial_report(self, db_session, project):
        """有报表数据时通过"""
        db_session.add(FinancialReport(
            id=uuid.uuid4(),
            project_id=FAKE_PROJECT_ID,
            year=YEAR,
            report_type=FinancialReportType.balance_sheet,
            row_code="BS-001",
            row_name="流动资产：",
            current_period_amount=Decimal("0"),
            generated_at=datetime.now(timezone.utc),
        ))
        await db_session.flush()

        checker = PrerequisiteChecker()
        result = await checker.check(db_session, FAKE_PROJECT_ID, YEAR, "generate_notes")
        assert result["ok"] is True


class TestUnknownAction:
    """未知操作应返回 ok=True"""

    @pytest.mark.asyncio
    async def test_unknown_action_passes(self, db_session, project):
        checker = PrerequisiteChecker()
        result = await checker.check(db_session, FAKE_PROJECT_ID, YEAR, "unknown_action")
        assert result["ok"] is True
        assert result["prerequisite_action"] is None
