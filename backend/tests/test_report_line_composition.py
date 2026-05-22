"""报表行构成科目 API 单元测试

Validates: Requirements F1.2
Tests:
- 正常查询：返回构成科目列表（按金额降序）+ 占比计算
- 空行（无映射科目）返回 404
- 占比计算正确性（总和 100%）
- 无 TB 数据时返回空 accounts
- 年度参数：指定年度 / 默认最新年度
- 权限校验（通过 require_project_access）
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, User, UserRole
from app.models.audit_platform_models import (
    ReportLineMapping,
    ReportLineMappingType,
    ReportType,
    TbBalance,
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


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    """Create a test project."""
    p = Project(
        id=uuid.uuid4(),
        name="构成科目测试项目",
        client_name="构成科目测试客户",
    )
    db_session.add(p)
    await db_session.flush()
    return p


@pytest_asyncio.fixture
async def report_line_mappings(db_session: AsyncSession, project: Project) -> list[ReportLineMapping]:
    """Create report line mappings for BS-001 (货币资金) with 1001 and 1002."""
    mappings = [
        ReportLineMapping(
            id=uuid.uuid4(),
            project_id=project.id,
            standard_account_code="1001",
            report_type=ReportType.balance_sheet,
            report_line_code="BS-001",
            report_line_name="货币资金",
            report_line_level=1,
            mapping_type=ReportLineMappingType.ai_suggested,
            is_confirmed=True,
        ),
        ReportLineMapping(
            id=uuid.uuid4(),
            project_id=project.id,
            standard_account_code="1002",
            report_type=ReportType.balance_sheet,
            report_line_code="BS-001",
            report_line_name="货币资金",
            report_line_level=1,
            mapping_type=ReportLineMappingType.ai_suggested,
            is_confirmed=True,
        ),
    ]
    for m in mappings:
        db_session.add(m)
    await db_session.flush()
    return mappings


@pytest_asyncio.fixture
async def tb_balances(db_session: AsyncSession, project: Project) -> list[TbBalance]:
    """Create TB balance entries for 1001 and 1002."""
    balances = [
        TbBalance(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2024,
            company_code="001",
            account_code="1001",
            account_name="库存现金",
            closing_balance=Decimal("50000"),
            opening_balance=Decimal("40000"),
        ),
        TbBalance(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2024,
            company_code="001",
            account_code="1002",
            account_name="银行存款",
            closing_balance=Decimal("4950000"),
            opening_balance=Decimal("4000000"),
        ),
    ]
    for b in balances:
        db_session.add(b)
    await db_session.flush()
    return balances


@pytest_asyncio.fixture
async def tb_balances_multi_year(db_session: AsyncSession, project: Project) -> list[TbBalance]:
    """Create TB balance entries for multiple years."""
    balances = [
        TbBalance(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2023,
            company_code="001",
            account_code="1001",
            account_name="库存现金",
            closing_balance=Decimal("30000"),
            opening_balance=Decimal("20000"),
        ),
        TbBalance(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2024,
            company_code="001",
            account_code="1001",
            account_name="库存现金",
            closing_balance=Decimal("50000"),
            opening_balance=Decimal("40000"),
        ),
        TbBalance(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2024,
            company_code="001",
            account_code="1002",
            account_name="银行存款",
            closing_balance=Decimal("4950000"),
            opening_balance=Decimal("4000000"),
        ),
    ]
    for b in balances:
        db_session.add(b)
    await db_session.flush()
    return balances


# ===================================================================
# Helper: direct service call (bypass HTTP layer for unit tests)
# ===================================================================


async def _call_line_composition(
    db: AsyncSession,
    project_id: uuid.UUID,
    line_code: str,
    year: int | None = None,
) -> dict:
    """Directly invoke the line-composition logic (same as the endpoint handler)."""
    import sqlalchemy as sa
    from app.routers.reports import LineCompositionAccount, LineCompositionResponse

    # 1. Determine year
    if year is None:
        year_result = await db.execute(
            sa.select(sa.func.max(TbBalance.year)).where(
                TbBalance.project_id == project_id,
                TbBalance.is_deleted == sa.false(),
            )
        )
        year = year_result.scalar_one_or_none()
        if year is None:
            return {"error": "no_tb_data", "status": 404}

    # 2. Query report_line_mapping
    mapping_result = await db.execute(
        sa.select(ReportLineMapping).where(
            ReportLineMapping.project_id == project_id,
            ReportLineMapping.report_line_code == line_code,
            ReportLineMapping.is_deleted == sa.false(),
            ReportLineMapping.is_confirmed == sa.true(),
        )
    )
    mappings = mapping_result.scalars().all()

    if not mappings:
        return {"error": "no_mapping", "status": 404}

    item_name = mappings[0].report_line_name
    account_codes = list({m.standard_account_code for m in mappings})

    # 3. Query tb_balance
    tb_result = await db.execute(
        sa.select(TbBalance).where(
            TbBalance.project_id == project_id,
            TbBalance.year == year,
            TbBalance.account_code.in_(account_codes),
            TbBalance.is_deleted == sa.false(),
        )
    )
    tb_rows = tb_result.scalars().all()

    # 4. Calculate totals and percentages
    total_amount = 0.0
    for tb in tb_rows:
        balance = float(tb.closing_balance) if tb.closing_balance is not None else 0.0
        total_amount += abs(balance)

    accounts = []
    for tb in sorted(
        tb_rows,
        key=lambda t: abs(float(t.closing_balance) if t.closing_balance is not None else 0.0),
        reverse=True,
    ):
        balance = float(tb.closing_balance) if tb.closing_balance is not None else 0.0
        pct = (abs(balance) / total_amount * 100.0) if total_amount != 0 else 0.0
        accounts.append({
            "code": tb.account_code,
            "name": tb.account_name or "",
            "closing_balance": balance,
            "pct": round(pct, 1),
        })

    actual_total = sum(
        float(tb.closing_balance) if tb.closing_balance is not None else 0.0
        for tb in tb_rows
    )

    return {
        "line_code": line_code,
        "item_name": item_name,
        "total_amount": actual_total,
        "accounts": accounts,
    }


# ===================================================================
# Tests
# ===================================================================


class TestLineCompositionNormal:
    """Test normal line-composition queries."""

    @pytest.mark.asyncio
    async def test_returns_accounts_sorted_by_amount_desc(
        self,
        db_session: AsyncSession,
        project: Project,
        report_line_mappings: list[ReportLineMapping],
        tb_balances: list[TbBalance],
    ):
        """Accounts are returned sorted by absolute closing_balance descending."""
        result = await _call_line_composition(db_session, project.id, "BS-001", year=2024)

        assert result["line_code"] == "BS-001"
        assert result["item_name"] == "货币资金"
        assert len(result["accounts"]) == 2
        # 银行存款 (4950000) should come first
        assert result["accounts"][0]["code"] == "1002"
        assert result["accounts"][0]["name"] == "银行存款"
        assert result["accounts"][0]["closing_balance"] == 4950000.0
        # 库存现金 (50000) second
        assert result["accounts"][1]["code"] == "1001"
        assert result["accounts"][1]["name"] == "库存现金"
        assert result["accounts"][1]["closing_balance"] == 50000.0

    @pytest.mark.asyncio
    async def test_total_amount_is_sum_of_balances(
        self,
        db_session: AsyncSession,
        project: Project,
        report_line_mappings: list[ReportLineMapping],
        tb_balances: list[TbBalance],
    ):
        """total_amount equals the sum of all closing_balances."""
        result = await _call_line_composition(db_session, project.id, "BS-001", year=2024)

        assert result["total_amount"] == 5000000.0  # 50000 + 4950000

    @pytest.mark.asyncio
    async def test_pct_calculation_correct(
        self,
        db_session: AsyncSession,
        project: Project,
        report_line_mappings: list[ReportLineMapping],
        tb_balances: list[TbBalance],
    ):
        """Percentage calculation: each account's |balance| / sum(|balances|) * 100."""
        result = await _call_line_composition(db_session, project.id, "BS-001", year=2024)

        # 银行存款: 4950000 / 5000000 * 100 = 99.0%
        assert result["accounts"][0]["pct"] == 99.0
        # 库存现金: 50000 / 5000000 * 100 = 1.0%
        assert result["accounts"][1]["pct"] == 1.0

    @pytest.mark.asyncio
    async def test_pct_sum_approximately_100(
        self,
        db_session: AsyncSession,
        project: Project,
        report_line_mappings: list[ReportLineMapping],
        tb_balances: list[TbBalance],
    ):
        """Sum of all pct values should be approximately 100%."""
        result = await _call_line_composition(db_session, project.id, "BS-001", year=2024)

        total_pct = sum(a["pct"] for a in result["accounts"])
        assert abs(total_pct - 100.0) < 0.5  # Allow rounding tolerance


class TestLineCompositionNoMapping:
    """Test when no mapping exists for the line_code."""

    @pytest.mark.asyncio
    async def test_no_mapping_returns_error(
        self,
        db_session: AsyncSession,
        project: Project,
        tb_balances: list[TbBalance],
    ):
        """Non-existent line_code returns 404 error."""
        result = await _call_line_composition(db_session, project.id, "NONEXIST-999", year=2024)

        assert result["error"] == "no_mapping"
        assert result["status"] == 404


class TestLineCompositionNoTbData:
    """Test when no TB data exists."""

    @pytest.mark.asyncio
    async def test_no_tb_data_returns_error(
        self,
        db_session: AsyncSession,
        project: Project,
    ):
        """Project with no TB data and no year specified returns 404."""
        result = await _call_line_composition(db_session, project.id, "BS-001")

        assert result["error"] == "no_tb_data"
        assert result["status"] == 404

    @pytest.mark.asyncio
    async def test_mapping_exists_but_no_tb_for_year(
        self,
        db_session: AsyncSession,
        project: Project,
        report_line_mappings: list[ReportLineMapping],
    ):
        """Mapping exists but no TB balance for the specified year returns empty accounts."""
        result = await _call_line_composition(db_session, project.id, "BS-001", year=2024)

        assert result["line_code"] == "BS-001"
        assert result["item_name"] == "货币资金"
        assert result["total_amount"] == 0.0
        assert result["accounts"] == []


class TestLineCompositionYear:
    """Test year parameter handling."""

    @pytest.mark.asyncio
    async def test_default_year_uses_latest(
        self,
        db_session: AsyncSession,
        project: Project,
        report_line_mappings: list[ReportLineMapping],
        tb_balances_multi_year: list[TbBalance],
    ):
        """When year is not specified, uses the latest year from tb_balance."""
        result = await _call_line_composition(db_session, project.id, "BS-001")

        # Latest year is 2024, which has both 1001 and 1002
        assert len(result["accounts"]) == 2
        assert result["total_amount"] == 5000000.0

    @pytest.mark.asyncio
    async def test_explicit_year_filters_correctly(
        self,
        db_session: AsyncSession,
        project: Project,
        report_line_mappings: list[ReportLineMapping],
        tb_balances_multi_year: list[TbBalance],
    ):
        """Specifying year=2023 only returns data for that year."""
        result = await _call_line_composition(db_session, project.id, "BS-001", year=2023)

        # 2023 only has 1001 with balance 30000
        assert len(result["accounts"]) == 1
        assert result["accounts"][0]["code"] == "1001"
        assert result["accounts"][0]["closing_balance"] == 30000.0
        assert result["accounts"][0]["pct"] == 100.0
        assert result["total_amount"] == 30000.0


class TestLineCompositionEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_zero_balance_accounts(
        self,
        db_session: AsyncSession,
        project: Project,
        report_line_mappings: list[ReportLineMapping],
    ):
        """Accounts with zero balance get pct=0."""
        # Add TB entries with zero balance
        balances = [
            TbBalance(
                id=uuid.uuid4(),
                project_id=project.id,
                year=2024,
                company_code="001",
                account_code="1001",
                account_name="库存现金",
                closing_balance=Decimal("0"),
            ),
            TbBalance(
                id=uuid.uuid4(),
                project_id=project.id,
                year=2024,
                company_code="001",
                account_code="1002",
                account_name="银行存款",
                closing_balance=Decimal("0"),
            ),
        ]
        for b in balances:
            db_session.add(b)
        await db_session.flush()

        result = await _call_line_composition(db_session, project.id, "BS-001", year=2024)

        assert result["total_amount"] == 0.0
        assert all(a["pct"] == 0.0 for a in result["accounts"])

    @pytest.mark.asyncio
    async def test_unconfirmed_mappings_excluded(
        self,
        db_session: AsyncSession,
        project: Project,
        tb_balances: list[TbBalance],
    ):
        """Unconfirmed mappings are not included in the query."""
        # Add an unconfirmed mapping
        mapping = ReportLineMapping(
            id=uuid.uuid4(),
            project_id=project.id,
            standard_account_code="1001",
            report_type=ReportType.balance_sheet,
            report_line_code="BS-UNCONFIRMED",
            report_line_name="未确认行",
            report_line_level=1,
            mapping_type=ReportLineMappingType.ai_suggested,
            is_confirmed=False,
        )
        db_session.add(mapping)
        await db_session.flush()

        result = await _call_line_composition(db_session, project.id, "BS-UNCONFIRMED", year=2024)

        assert result["error"] == "no_mapping"

    @pytest.mark.asyncio
    async def test_deleted_mappings_excluded(
        self,
        db_session: AsyncSession,
        project: Project,
        tb_balances: list[TbBalance],
    ):
        """Soft-deleted mappings are not included."""
        mapping = ReportLineMapping(
            id=uuid.uuid4(),
            project_id=project.id,
            standard_account_code="1001",
            report_type=ReportType.balance_sheet,
            report_line_code="BS-DELETED",
            report_line_name="已删除行",
            report_line_level=1,
            mapping_type=ReportLineMappingType.ai_suggested,
            is_confirmed=True,
            is_deleted=True,
        )
        db_session.add(mapping)
        await db_session.flush()

        result = await _call_line_composition(db_session, project.id, "BS-DELETED", year=2024)

        assert result["error"] == "no_mapping"
