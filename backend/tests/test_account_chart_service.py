"""AccountChartService 单元测试

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

import io
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import UploadFile
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus
from app.models.core import Project
from app.models.audit_platform_models import AccountChart, AccountSource
from app.models.audit_platform_schemas import BasicInfoSchema, WizardStep

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
    """Create a test project for use in tests."""
    from app.services import project_wizard_service as svc

    data = BasicInfoSchema(
        client_name="测试客户",
        audit_year=2024,
        project_type="annual",
        accounting_standard="enterprise",
    )
    return await svc.create_project(data, db)


def _make_csv_upload(content: str, filename: str = "chart.csv") -> UploadFile:
    """Create a mock UploadFile from CSV string."""
    file_bytes = content.encode("utf-8-sig")
    return UploadFile(
        filename=filename,
        file=io.BytesIO(file_bytes),
    )


# ===================================================================
# load_standard_template
# ===================================================================


class TestLoadStandardTemplate:
    """Validates: Requirements 2.1, 2.2"""

    @pytest.mark.asyncio
    async def test_load_enterprise_standard(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        accounts = await svc.load_standard_template(
            project.id, "enterprise", db_session
        )

        assert len(accounts) > 0
        # Check first account
        first = accounts[0]
        assert first.account_code == "1001"
        assert first.account_name == "库存现金"
        assert first.source.value == "standard"

    @pytest.mark.asyncio
    async def test_load_standard_has_all_categories(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        accounts = await svc.load_standard_template(
            project.id, "enterprise", db_session
        )

        categories = {a.category.value for a in accounts}
        assert "asset" in categories
        assert "liability" in categories
        assert "equity" in categories
        assert "revenue" in categories
        assert "expense" in categories

    @pytest.mark.asyncio
    async def test_load_standard_has_second_level(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        accounts = await svc.load_standard_template(
            project.id, "enterprise", db_session
        )

        level2 = [a for a in accounts if a.level == 2]
        assert len(level2) > 0
        # Second-level accounts should have parent_code
        for a in level2:
            assert a.parent_code is not None

    @pytest.mark.asyncio
    async def test_load_standard_duplicate_is_incremental(self, db_session: AsyncSession):
        """Duplicate load should succeed (incremental: skip existing, insert new only)."""
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        first = await svc.load_standard_template(project.id, "enterprise", db_session)
        second = await svc.load_standard_template(project.id, "enterprise", db_session)
        # Second load returns all accounts (existing + any new), no exception
        assert len(second) >= len(first)

    @pytest.mark.asyncio
    async def test_load_unsupported_standard(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)

        with pytest.raises(Exception) as exc_info:
            await svc.load_standard_template(project.id, "unknown", db_session)
        assert exc_info.value.status_code == 400


# ===================================================================
# import_client_chart
# ===================================================================


class TestImportClientChart:
    """Validates: Requirements 2.3, 2.4, 2.5"""

    @pytest.mark.asyncio
    async def test_import_csv_success(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        csv_content = "科目编码,科目名称,借贷方向,父科目编码\n1001,库存现金,借,\n100101,人民币现金,借,1001\n1002,银行存款,借,"
        file = _make_csv_upload(csv_content)

        result = await svc.import_client_chart(project.id, file, db_session)

        assert result.total_imported == 3
        assert "asset" in result.by_category
        assert result.by_category["asset"] == 3

    @pytest.mark.asyncio
    async def test_import_csv_english_columns(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        csv_content = "account_code,account_name,direction,parent_code\n2001,短期借款,credit,\n2201,应付票据,credit,"
        file = _make_csv_upload(csv_content)

        result = await svc.import_client_chart(project.id, file, db_session)

        assert result.total_imported == 2
        assert "liability" in result.by_category

    @pytest.mark.asyncio
    async def test_import_missing_required_columns(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        csv_content = "名称,方向\n库存现金,借"
        file = _make_csv_upload(csv_content)

        with pytest.raises(Exception) as exc_info:
            await svc.import_client_chart(project.id, file, db_session)
        assert exc_info.value.status_code == 400
        assert "必填列" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_import_empty_rows_skipped(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        csv_content = "科目编码,科目名称\n1001,库存现金\n,,\n1002,银行存款"
        file = _make_csv_upload(csv_content)

        result = await svc.import_client_chart(project.id, file, db_session)

        assert result.total_imported == 2
        # Empty rows are silently skipped, not counted as errors
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_import_unsupported_format(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        file = UploadFile(
            filename="chart.txt",
            file=io.BytesIO(b"some text"),
        )

        with pytest.raises(Exception) as exc_info:
            await svc.import_client_chart(project.id, file, db_session)
        assert exc_info.value.status_code == 400
        assert "不支持" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_import_xls_rejected(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        file = UploadFile(
            filename="chart.xls",
            file=io.BytesIO(b"legacy excel content"),
        )

        with pytest.raises(Exception) as exc_info:
            await svc.import_client_chart(project.id, file, db_session)
        assert exc_info.value.status_code == 400
        assert ".xls" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_import_xlsx_with_legacy_auto_import_disabled(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "科目表"
        sheet.append(["科目编码", "科目名称", "借贷方向"])
        sheet.append(["1001", "库存现金", "借"])
        stream = io.BytesIO()
        workbook.save(stream)
        file = UploadFile(filename="chart.xlsx", file=io.BytesIO(stream.getvalue()))

        with pytest.raises(Exception) as exc_info:
            await svc.import_client_chart(project.id, file, db_session, skip_auto_import=False)

        assert exc_info.value.status_code == 410
        assert "旧 account_chart 自动联动四表导入已废弃" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_auto_import_data_sheets_requires_internal_flag(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)

        with pytest.raises(Exception) as exc_info:
            await svc._auto_import_data_sheets(
                project.id,
                b"fake-xlsx-content",
                year=2024,
                db=db_session,
            )

        assert exc_info.value.status_code == 410
        assert "_auto_import_data_sheets 已废弃且仅限内部兼容调用" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_import_direction_inference(self, db_session: AsyncSession):
        """When direction is not provided, infer from account code."""
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        csv_content = "科目编码,科目名称\n1001,库存现金\n2001,短期借款\n5001,主营业务收入"
        file = _make_csv_upload(csv_content)

        result = await svc.import_client_chart(project.id, file, db_session)
        assert result.total_imported == 3


# ===================================================================
# preview_file
# ===================================================================


class TestPreviewFile:
    @pytest.mark.asyncio
    async def test_preview_csv_samples_first_20_rows(self):
        from app.services import account_chart_service as svc

        csv_rows = ["科目编码,科目名称"]
        for i in range(30):
            csv_rows.append(f"100{i:02d},科目{i}")
        file = _make_csv_upload("\n".join(csv_rows), filename="preview.csv")

        result = await svc.preview_file(file)

        assert result["active_sheet"] == 0
        assert len(result["sheets"]) == 1
        assert result["sheets"][0]["total_rows"] == 30
        assert len(result["sheets"][0]["rows"]) == 20
        assert result["sheets"][0]["rows"][0]["科目编码"] == "10000"


# ===================================================================
# get_client_chart_tree
# ===================================================================


class TestGetClientChartTree:
    """Validates: Requirements 2.6"""

    @pytest.mark.asyncio
    async def test_tree_structure(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        csv_content = "科目编码,科目名称,借贷方向,父科目编码\n1001,库存现金,借,\n100101,人民币现金,借,1001\n2001,短期借款,贷,"
        file = _make_csv_upload(csv_content)
        await svc.import_client_chart(project.id, file, db_session)

        tree = await svc.get_client_chart_tree(project.id, db_session)

        assert "asset" in tree
        assert "liability" in tree
        # Asset tree should have 库存现金 as root with 人民币现金 as child
        asset_roots = tree["asset"]
        assert len(asset_roots) == 1
        assert asset_roots[0].account_code == "1001"
        assert len(asset_roots[0].children) == 1
        assert asset_roots[0].children[0].account_code == "100101"

    @pytest.mark.asyncio
    async def test_empty_tree(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        tree = await svc.get_client_chart_tree(project.id, db_session)

        assert tree == {}


# ===================================================================
# get_standard_chart
# ===================================================================


class TestGetStandardChart:
    """Validates: Requirements 2.2"""

    @pytest.mark.asyncio
    async def test_get_after_load(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        await svc.load_standard_template(project.id, "enterprise", db_session)

        accounts = await svc.get_standard_chart(project.id, db_session)
        assert len(accounts) > 0
        # Should be sorted by account_code
        codes = [a.account_code for a in accounts]
        assert codes == sorted(codes)

    @pytest.mark.asyncio
    async def test_get_empty(self, db_session: AsyncSession):
        from app.services import account_chart_service as svc

        project = await _create_test_project(db_session)
        accounts = await svc.get_standard_chart(project.id, db_session)
        assert accounts == []
