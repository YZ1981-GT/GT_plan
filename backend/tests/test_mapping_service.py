"""MappingService 单元测试

Validates: Requirements 3.1, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""

import io
import uuid
from decimal import Decimal

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
    TbBalance,
)
from app.models.audit_platform_schemas import (
    BasicInfoSchema,
    MappingInput,
    MappingSuggestion,
)

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
        client_name="映射测试客户",
        audit_year=2024,
        project_type="annual",
        accounting_standard="enterprise",
    )
    return await svc.create_project(data, db)


async def _load_standard_and_client(
    db: AsyncSession, project_id: uuid.UUID
) -> None:
    """Load standard template and import a small client chart."""
    from app.services import account_chart_service as svc

    # Load standard accounts
    await svc.load_standard_template(project_id, "enterprise", db)

    # Import client accounts via CSV
    csv_content = (
        "科目编码,科目名称,借贷方向\n"
        "1001,库存现金,借\n"
        "1002,银行存款,借\n"
        "1012,其他货币资金,借\n"
        "1101,交易性金融资产,借\n"
        "1122,应收账款,借\n"
        "2001,短期借款,贷\n"
        "5001,主营业务收入,贷\n"
        "9999,自定义科目,借\n"
    )
    file = UploadFile(
        filename="client.csv",
        file=io.BytesIO(csv_content.encode("utf-8-sig")),
    )
    await svc.import_client_chart(project_id, file, db)


# ===================================================================
# auto_suggest
# ===================================================================


class TestAutoSuggest:
    """Validates: Requirements 3.1"""

    @pytest.mark.asyncio
    async def test_prefix_match(self, db_session: AsyncSession):
        """Client code prefix matches standard code → confidence=1.0."""
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        await _load_standard_and_client(db_session, project.id)

        suggestions = await svc.auto_suggest(project.id, db_session)

        # 1001 should match standard 1001 by prefix
        s1001 = next(
            (s for s in suggestions if s.original_account_code == "1001"), None
        )
        assert s1001 is not None
        assert s1001.suggested_standard_code == "1001"
        assert s1001.confidence == 1.0
        assert s1001.match_method == "prefix"

    @pytest.mark.asyncio
    async def test_name_exact_match(self, db_session: AsyncSession):
        """Client name exactly matches standard name."""
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        await _load_standard_and_client(db_session, project.id)

        suggestions = await svc.auto_suggest(project.id, db_session)

        # All standard accounts with matching names should be found
        matched_codes = {s.original_account_code for s in suggestions}
        # 1001, 1002, etc. should all be matched (by prefix or name)
        assert "1001" in matched_codes
        assert "1002" in matched_codes

    @pytest.mark.asyncio
    async def test_unmatched_not_in_suggestions(self, db_session: AsyncSession):
        """Accounts that don't match should not appear in suggestions."""
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        await _load_standard_and_client(db_session, project.id)

        suggestions = await svc.auto_suggest(project.id, db_session)

        # 9999 "自定义科目" should not match any standard account
        s9999 = next(
            (s for s in suggestions if s.original_account_code == "9999"), None
        )
        assert s9999 is None

    @pytest.mark.asyncio
    async def test_empty_when_no_accounts(self, db_session: AsyncSession):
        """No suggestions when no client or standard accounts."""
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        suggestions = await svc.auto_suggest(project.id, db_session)
        assert suggestions == []

    @pytest.mark.asyncio
    async def test_suggestions_have_required_fields(self, db_session: AsyncSession):
        """Each suggestion has all required fields."""
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        await _load_standard_and_client(db_session, project.id)

        suggestions = await svc.auto_suggest(project.id, db_session)
        assert len(suggestions) > 0

        for s in suggestions:
            assert s.original_account_code
            assert s.suggested_standard_code
            assert s.match_method in ("prefix", "exact_name", "fuzzy_name")
            assert 0.0 <= s.confidence <= 1.0


# ===================================================================
# save_mapping
# ===================================================================


class TestSaveMapping:
    """Validates: Requirements 3.3, 3.4"""

    @pytest.mark.asyncio
    async def test_save_new_mapping(self, db_session: AsyncSession):
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        mapping = MappingInput(
            original_account_code="1001",
            original_account_name="库存现金",
            standard_account_code="1001",
            mapping_type=MappingType.manual,
        )
        record = await svc.save_mapping(project.id, mapping, db_session)

        assert record.original_account_code == "1001"
        assert record.standard_account_code == "1001"
        assert record.mapping_type == MappingType.manual

    @pytest.mark.asyncio
    async def test_update_existing_mapping(self, db_session: AsyncSession):
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        m1 = MappingInput(
            original_account_code="1001",
            original_account_name="库存现金",
            standard_account_code="1001",
        )
        await svc.save_mapping(project.id, m1, db_session)

        # Update to different standard code
        m2 = MappingInput(
            original_account_code="1001",
            original_account_name="库存现金",
            standard_account_code="1002",
        )
        record = await svc.save_mapping(project.id, m2, db_session)
        assert record.standard_account_code == "1002"

    @pytest.mark.asyncio
    async def test_many_to_one_mapping(self, db_session: AsyncSession):
        """Multiple client accounts can map to one standard account."""
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)

        # Map two client accounts to the same standard account
        for code in ["100101", "100102"]:
            m = MappingInput(
                original_account_code=code,
                original_account_name=f"现金-{code}",
                standard_account_code="1001",
            )
            await svc.save_mapping(project.id, m, db_session)

        mappings = await svc.get_mappings(project.id, db_session)
        std_codes = [m.standard_account_code for m in mappings]
        assert std_codes.count("1001") == 2


# ===================================================================
# batch_confirm
# ===================================================================


class TestBatchConfirm:
    """Validates: Requirements 3.5"""

    @pytest.mark.asyncio
    async def test_batch_confirm_returns_rate(self, db_session: AsyncSession):
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        await _load_standard_and_client(db_session, project.id)

        mappings = [
            MappingInput(
                original_account_code="1001",
                original_account_name="库存现金",
                standard_account_code="1001",
                mapping_type=MappingType.auto_exact,
            ),
            MappingInput(
                original_account_code="1002",
                original_account_name="银行存款",
                standard_account_code="1002",
                mapping_type=MappingType.auto_exact,
            ),
        ]
        result = await svc.batch_confirm(project.id, mappings, db_session)

        assert result.confirmed_count == 2
        assert result.total_count == 8  # 8 client accounts imported
        assert result.completion_rate == 25.0  # 2/8 * 100


# ===================================================================
# get_completion_rate
# ===================================================================


class TestGetCompletionRate:
    """Validates: Requirements 3.5, 3.6"""

    @pytest.mark.asyncio
    async def test_zero_when_no_mappings(self, db_session: AsyncSession):
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        await _load_standard_and_client(db_session, project.id)

        rate = await svc.get_completion_rate(project.id, db_session)
        assert rate.mapped_count == 0
        assert rate.total_count == 8
        assert rate.completion_rate == 0.0

    @pytest.mark.asyncio
    async def test_rate_after_mapping(self, db_session: AsyncSession):
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        await _load_standard_and_client(db_session, project.id)

        # Map 4 of 8 accounts
        for code in ["1001", "1002", "1012", "1101"]:
            m = MappingInput(
                original_account_code=code,
                standard_account_code=code,
            )
            await svc.save_mapping(project.id, m, db_session)

        rate = await svc.get_completion_rate(project.id, db_session)
        assert rate.mapped_count == 4
        assert rate.completion_rate == 50.0

    @pytest.mark.asyncio
    async def test_unmapped_with_balance(self, db_session: AsyncSession):
        """Unmapped accounts with non-zero balances are reported."""
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        await _load_standard_and_client(db_session, project.id)

        # Add a balance record for unmapped account 9999
        balance = TbBalance(
            project_id=project.id,
            year=2024,
            company_code="default",
            account_code="9999",
            account_name="自定义科目",
            closing_balance=Decimal("10000.00"),
        )
        db_session.add(balance)
        await db_session.flush()
        await db_session.commit()

        rate = await svc.get_completion_rate(project.id, db_session)
        assert len(rate.unmapped_with_balance) >= 1
        codes = [item["account_code"] for item in rate.unmapped_with_balance]
        assert "9999" in codes

    @pytest.mark.asyncio
    async def test_no_unmapped_with_balance_when_all_mapped(
        self, db_session: AsyncSession
    ):
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        await _load_standard_and_client(db_session, project.id)

        # Map all 8 accounts
        for code in ["1001", "1002", "1012", "1101", "1122", "2001", "5001", "9999"]:
            m = MappingInput(
                original_account_code=code,
                standard_account_code="1001",  # doesn't matter which
            )
            await svc.save_mapping(project.id, m, db_session)

        rate = await svc.get_completion_rate(project.id, db_session)
        assert rate.completion_rate == 100.0
        assert rate.unmapped_with_balance == []


# ===================================================================
# update_mapping
# ===================================================================


class TestUpdateMapping:
    """Validates: Requirements 3.7"""

    @pytest.mark.asyncio
    async def test_update_mapping_success(self, db_session: AsyncSession):
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        m = MappingInput(
            original_account_code="1001",
            original_account_name="库存现金",
            standard_account_code="1001",
        )
        record = await svc.save_mapping(project.id, m, db_session)

        updated = await svc.update_mapping(
            project.id, record.id, "1002", db_session
        )
        assert updated.standard_account_code == "1002"
        assert updated.mapping_type == MappingType.manual

    @pytest.mark.asyncio
    async def test_update_nonexistent_mapping(self, db_session: AsyncSession):
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        fake_id = uuid.uuid4()

        with pytest.raises(Exception) as exc_info:
            await svc.update_mapping(project.id, fake_id, "1001", db_session)
        assert exc_info.value.status_code == 404


# ===================================================================
# get_mappings
# ===================================================================


class TestGetMappings:
    """Validates: Requirements 3.8"""

    @pytest.mark.asyncio
    async def test_get_mappings_ordered(self, db_session: AsyncSession):
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)

        for code in ["2001", "1001", "1002"]:
            m = MappingInput(
                original_account_code=code,
                standard_account_code=code,
            )
            await svc.save_mapping(project.id, m, db_session)

        mappings = await svc.get_mappings(project.id, db_session)
        codes = [m.original_account_code for m in mappings]
        assert codes == sorted(codes)

    @pytest.mark.asyncio
    async def test_get_mappings_empty(self, db_session: AsyncSession):
        from app.services import mapping_service as svc

        project = await _create_test_project(db_session)
        mappings = await svc.get_mappings(project.id, db_session)
        assert mappings == []


# ===================================================================
# Fuzzy matching helpers
# ===================================================================


class TestFuzzyHelpers:
    """Test the similarity helper functions."""

    def test_jaccard_identical(self):
        from app.services.mapping_service import _jaccard_similarity

        assert _jaccard_similarity("库存现金", "库存现金") == 1.0

    def test_jaccard_different(self):
        from app.services.mapping_service import _jaccard_similarity

        score = _jaccard_similarity("库存现金", "银行存款")
        assert score < 0.5

    def test_sequence_similar(self):
        from app.services.mapping_service import _sequence_similarity

        score = _sequence_similarity("应收账款", "应收票据")
        assert 0.0 < score < 1.0

    def test_fuzzy_score_threshold(self):
        from app.services.mapping_service import _fuzzy_score

        # Very similar names should exceed threshold
        score = _fuzzy_score("其他应收款", "其他应收款项")
        assert score > 0.7
