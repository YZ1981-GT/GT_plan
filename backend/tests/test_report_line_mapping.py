"""ReportLineMappingService 单元测试

Validates: Requirements 3.9, 3.10, 3.11, 3.12, 3.13, 3.14
"""

import io
import uuid

import pytest
import pytest_asyncio
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project
from app.models.audit_platform_models import (
    AccountChart,
    AccountMapping,
    AccountSource,
    MappingType,
    ReportLineMapping,
    ReportLineMappingType,
    ReportType,
)
from app.models.audit_platform_schemas import BasicInfoSchema

# SQLite JSONB compat
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


async def _create_test_project(db: AsyncSession) -> Project:
    """Create a test project."""
    from app.services import project_wizard_service as svc

    data = BasicInfoSchema(
        client_name="报表行次测试客户",
        audit_year=2024,
        project_type="annual",
        accounting_standard="enterprise",
    )
    return await svc.create_project(data, db)


async def _setup_standard_and_mappings(
    db: AsyncSession, project_id: uuid.UUID
) -> None:
    """Load standard accounts and create account mappings."""
    from app.services import account_chart_service as chart_svc

    await chart_svc.load_standard_template(project_id, "enterprise", db)

    # Import client accounts
    csv_content = (
        "科目编码,科目名称,借贷方向\n"
        "1001,库存现金,借\n"
        "1002,银行存款,借\n"
        "1122,应收账款,借\n"
        "2001,短期借款,贷\n"
        "5001,主营业务收入,贷\n"
        "5601,销售费用,借\n"
    )
    file = UploadFile(
        filename="client.csv",
        file=io.BytesIO(csv_content.encode("utf-8-sig")),
    )
    await chart_svc.import_client_chart(project_id, file, db)

    # Create account mappings
    from app.services import mapping_service

    from app.models.audit_platform_schemas import MappingInput

    for code in ["1001", "1002", "1122", "2001", "5001", "5601"]:
        m = MappingInput(
            original_account_code=code,
            standard_account_code=code,
            mapping_type=MappingType.auto_exact,
        )
        await mapping_service.save_mapping(project_id, m, db)


# ===================================================================
# ai_suggest_mappings (Task 7a.2)
# ===================================================================


class TestAiSuggestMappings:
    """Validates: Requirements 3.10"""

    @pytest.mark.asyncio
    async def test_generates_suggestions(self, db_session: AsyncSession):
        """AI suggest should generate mapping suggestions for mapped accounts."""
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, project.id)

        suggestions = await svc.ai_suggest_mappings(project.id, db_session)

        assert len(suggestions) > 0
        # Should have suggestions for balance sheet and income statement
        report_types = {s["report_type"] for s in suggestions}
        assert "balance_sheet" in report_types
        assert "income_statement" in report_types

    @pytest.mark.asyncio
    async def test_suggestions_have_required_fields(self, db_session: AsyncSession):
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, project.id)

        suggestions = await svc.ai_suggest_mappings(project.id, db_session)

        for s in suggestions:
            assert "standard_account_code" in s
            assert "report_type" in s
            assert "report_line_code" in s
            assert "report_line_name" in s
            assert "confidence" in s
            assert 0.0 <= s["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_no_duplicates_on_rerun(self, db_session: AsyncSession):
        """Running AI suggest twice should not create duplicate mappings."""
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, project.id)

        first = await svc.ai_suggest_mappings(project.id, db_session)
        second = await svc.ai_suggest_mappings(project.id, db_session)

        # Second run should return empty (all already exist)
        assert len(second) == 0
        # But first run should have created records
        assert len(first) > 0

    @pytest.mark.asyncio
    async def test_empty_when_no_mappings(self, db_session: AsyncSession):
        """No suggestions when no account mappings exist."""
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        # Don't set up any mappings or standard accounts
        suggestions = await svc.ai_suggest_mappings(project.id, db_session)
        assert suggestions == []

    @pytest.mark.asyncio
    async def test_saves_to_database(self, db_session: AsyncSession):
        """Suggestions should be persisted in report_line_mapping table."""
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, project.id)

        await svc.ai_suggest_mappings(project.id, db_session)

        # Verify records exist in DB
        db_mappings = await svc.get_mappings(project.id, db_session)
        assert len(db_mappings) > 0
        for m in db_mappings:
            assert m.mapping_type.value == "ai_suggested"
            assert m.is_confirmed is False


# ===================================================================
# confirm_mapping / batch_confirm (Task 7a.3)
# ===================================================================


class TestConfirmMapping:
    """Validates: Requirements 3.11"""

    @pytest.mark.asyncio
    async def test_confirm_single(self, db_session: AsyncSession):
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, project.id)
        await svc.ai_suggest_mappings(project.id, db_session)

        all_mappings = await svc.get_mappings(project.id, db_session)
        assert len(all_mappings) > 0

        first = all_mappings[0]
        confirmed = await svc.confirm_mapping(project.id, first.id, db_session)
        assert confirmed.is_confirmed is True

    @pytest.mark.asyncio
    async def test_confirm_nonexistent_raises(self, db_session: AsyncSession):
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        fake_id = uuid.uuid4()

        with pytest.raises(Exception) as exc_info:
            await svc.confirm_mapping(project.id, fake_id, db_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_batch_confirm(self, db_session: AsyncSession):
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, project.id)
        await svc.ai_suggest_mappings(project.id, db_session)

        all_mappings = await svc.get_mappings(project.id, db_session)
        ids = [m.id for m in all_mappings]

        count = await svc.batch_confirm(project.id, ids, db_session)
        assert count == len(ids)

        # Verify all confirmed
        refreshed = await svc.get_mappings(project.id, db_session)
        for m in refreshed:
            assert m.is_confirmed is True

    @pytest.mark.asyncio
    async def test_batch_confirm_empty(self, db_session: AsyncSession):
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        count = await svc.batch_confirm(project.id, [], db_session)
        assert count == 0


# ===================================================================
# reference_copy (Task 7a.4)
# ===================================================================


class TestReferenceCopy:
    """Validates: Requirements 3.12, 3.13"""

    @pytest.mark.asyncio
    async def test_copy_from_source(self, db_session: AsyncSession):
        """Copy confirmed mappings from source project to target."""
        from app.services import report_line_mapping_service as svc

        # Create source project with confirmed mappings
        source = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, source.id)
        await svc.ai_suggest_mappings(source.id, db_session)

        source_mappings = await svc.get_mappings(source.id, db_session)
        ids = [m.id for m in source_mappings]
        await svc.batch_confirm(source.id, ids, db_session)

        # Create target project
        target = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, target.id)

        result = await svc.reference_copy(
            "报表行次测试客户", target.id, db_session
        )

        assert result.copied_count > 0

        # Verify copied mappings are reference_copied and unconfirmed
        target_mappings = await svc.get_mappings(target.id, db_session)
        for m in target_mappings:
            assert m.mapping_type.value == "reference_copied"
            assert m.is_confirmed is False

    @pytest.mark.asyncio
    async def test_copy_no_source(self, db_session: AsyncSession):
        """No source project → empty result."""
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        result = await svc.reference_copy("不存在的企业", project.id, db_session)
        assert result.copied_count == 0

    @pytest.mark.asyncio
    async def test_unmatched_accounts_reported(self, db_session: AsyncSession):
        """Accounts not in target should be reported as unmatched."""
        from app.services import report_line_mapping_service as svc

        # Source with extra account
        source = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, source.id)

        # Add an extra mapping for a code not in target
        extra = ReportLineMapping(
            project_id=source.id,
            standard_account_code="9999",
            report_type=ReportType.balance_sheet,
            report_line_code="BS999",
            report_line_name="特殊科目",
            report_line_level=1,
            mapping_type=ReportLineMappingType.ai_suggested,
            is_confirmed=True,
        )
        db_session.add(extra)
        await db_session.flush()
        await db_session.commit()

        # Target without 9999
        target = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, target.id)

        result = await svc.reference_copy(
            "报表行次测试客户", target.id, db_session
        )

        assert "9999" in result.unmatched_accounts


# ===================================================================
# inherit_from_prior_year (Task 7a.5)
# ===================================================================


class TestInheritFromPriorYear:
    """Validates: Requirements 3.14"""

    @pytest.mark.asyncio
    async def test_inherit_confirmed_mappings(self, db_session: AsyncSession):
        from app.services import report_line_mapping_service as svc

        # Prior year project
        prior = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, prior.id)
        await svc.ai_suggest_mappings(prior.id, db_session)

        prior_mappings = await svc.get_mappings(prior.id, db_session)
        ids = [m.id for m in prior_mappings]
        await svc.batch_confirm(prior.id, ids, db_session)

        # Current year project
        current = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, current.id)

        result = await svc.inherit_from_prior_year(prior.id, current.id, db_session)

        assert result.copied_count > 0

        current_mappings = await svc.get_mappings(current.id, db_session)
        for m in current_mappings:
            assert m.mapping_type.value == "reference_copied"
            assert m.is_confirmed is False

    @pytest.mark.asyncio
    async def test_inherit_empty_prior(self, db_session: AsyncSession):
        from app.services import report_line_mapping_service as svc

        prior = await _create_test_project(db_session)
        current = await _create_test_project(db_session)

        result = await svc.inherit_from_prior_year(prior.id, current.id, db_session)
        assert result.copied_count == 0

    @pytest.mark.asyncio
    async def test_inherit_skips_unconfirmed(self, db_session: AsyncSession):
        """Only confirmed mappings should be inherited."""
        from app.services import report_line_mapping_service as svc

        prior = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, prior.id)
        await svc.ai_suggest_mappings(prior.id, db_session)
        # Don't confirm — all are unconfirmed

        current = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, current.id)

        result = await svc.inherit_from_prior_year(prior.id, current.id, db_session)
        assert result.copied_count == 0


# ===================================================================
# get_mappings (列表查询)
# ===================================================================


class TestGetMappings:
    """Validates: Requirements 3.9"""

    @pytest.mark.asyncio
    async def test_filter_by_report_type(self, db_session: AsyncSession):
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, project.id)
        await svc.ai_suggest_mappings(project.id, db_session)

        bs_mappings = await svc.get_mappings(
            project.id, db_session, report_type="balance_sheet"
        )
        is_mappings = await svc.get_mappings(
            project.id, db_session, report_type="income_statement"
        )

        for m in bs_mappings:
            assert m.report_type.value == "balance_sheet"
        for m in is_mappings:
            assert m.report_type.value == "income_statement"

    @pytest.mark.asyncio
    async def test_empty_project(self, db_session: AsyncSession):
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        mappings = await svc.get_mappings(project.id, db_session)
        assert mappings == []


# ===================================================================
# get_report_lines (供调整分录下拉)
# ===================================================================


class TestGetReportLines:
    @pytest.mark.asyncio
    async def test_returns_confirmed_lines(self, db_session: AsyncSession):
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, project.id)
        await svc.ai_suggest_mappings(project.id, db_session)

        # Before confirming — should be empty
        lines = await svc.get_report_lines(project.id, db_session)
        assert len(lines) == 0

        # Confirm all
        all_mappings = await svc.get_mappings(project.id, db_session)
        ids = [m.id for m in all_mappings]
        await svc.batch_confirm(project.id, ids, db_session)

        # After confirming — should have lines
        lines = await svc.get_report_lines(project.id, db_session)
        assert len(lines) > 0

    @pytest.mark.asyncio
    async def test_deduplicates_lines(self, db_session: AsyncSession):
        """Multiple accounts mapping to same report line should be deduplicated."""
        from app.services import report_line_mapping_service as svc

        project = await _create_test_project(db_session)
        await _setup_standard_and_mappings(db_session, project.id)
        await svc.ai_suggest_mappings(project.id, db_session)

        all_mappings = await svc.get_mappings(project.id, db_session)
        ids = [m.id for m in all_mappings]
        await svc.batch_confirm(project.id, ids, db_session)

        lines = await svc.get_report_lines(project.id, db_session)
        line_codes = [l.report_line_code for l in lines]
        # No duplicates
        assert len(line_codes) == len(set(line_codes))
