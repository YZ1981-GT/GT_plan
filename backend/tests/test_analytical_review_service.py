"""分析性复核服务单元测试 — 计算逻辑验证

Validates: Requirements 1.1, 1.2, 1.3, 2.3
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import Materiality
from app.models.report_models import FinancialReport, FinancialReportType, ReportConfig
from app.models.workpaper_field_override_models import WorkpaperFieldOverride  # noqa: F401
from app.services.analytical_review_service import (
    classify_change,
    compute_change,
    compute_eps_roe_values,
    compute_weight_pct,
    compute_weighted_avg_shares,
    get_analytical_review_data,
    get_audit_explanation_for_row,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# 纯函数单元测试（无需 DB）
# ---------------------------------------------------------------------------


class TestComputeChange:
    """变动额/变动%计算"""

    def test_normal_increase(self):
        change, pct = compute_change(Decimal("1200000"), Decimal("1000000"))
        assert change == Decimal("200000")
        assert pct == Decimal("20")

    def test_normal_decrease(self):
        change, pct = compute_change(Decimal("800000"), Decimal("1000000"))
        assert change == Decimal("-200000")
        assert pct == Decimal("-20")

    def test_prior_zero_returns_none_pct(self):
        change, pct = compute_change(Decimal("500000"), Decimal("0"))
        assert change == Decimal("500000")
        assert pct is None

    def test_both_zero(self):
        change, pct = compute_change(Decimal("0"), Decimal("0"))
        assert change == Decimal("0")
        assert pct is None

    def test_none_values_treated_as_zero(self):
        change, pct = compute_change(None, Decimal("100"))
        assert change == Decimal("-100")
        assert pct == Decimal("-100")

    def test_prior_negative(self):
        """上年为负数时 pct = change / |prior| * 100"""
        change, pct = compute_change(Decimal("-50"), Decimal("-100"))
        assert change == Decimal("50")
        # 50 / abs(-100) * 100 = 50%
        assert pct == Decimal("50")


class TestClassifyChange:
    """变动状况分类判定"""

    def test_significant_by_pct(self):
        """变动% > 20% → significant"""
        assert classify_change(Decimal("25"), Decimal("100"), Decimal("10000")) == "significant"

    def test_significant_by_materiality(self):
        """变动额 > 重要性 → significant（即使 pct 低）"""
        assert classify_change(Decimal("5"), Decimal("60000"), Decimal("50000")) == "significant"

    def test_attention_by_pct(self):
        """10% < 变动% <= 20% → attention"""
        assert classify_change(Decimal("15"), Decimal("100"), Decimal("10000")) == "attention"

    def test_normal(self):
        """变动% <= 10% 且 变动额 <= 重要性 → normal"""
        assert classify_change(Decimal("5"), Decimal("100"), Decimal("10000")) == "normal"

    def test_none_pct_with_low_amount(self):
        """pct 为 None 且变动额 <= 重要性 → normal"""
        assert classify_change(None, Decimal("100"), Decimal("10000")) == "normal"

    def test_none_pct_with_high_amount(self):
        """pct 为 None 但变动额 > 重要性 → significant"""
        assert classify_change(None, Decimal("60000"), Decimal("50000")) == "significant"

    def test_negative_pct_significant(self):
        """负向变动也用绝对值判定"""
        assert classify_change(Decimal("-25"), Decimal("-200"), Decimal("10000")) == "significant"

    def test_zero_materiality(self):
        """重要性为 0 时，任何非零变动额都是 significant"""
        assert classify_change(Decimal("5"), Decimal("1"), Decimal("0")) == "significant"


class TestComputeWeightPct:
    """纵向比重%计算"""

    def test_normal(self):
        result = compute_weight_pct(Decimal("200000"), Decimal("1000000"))
        assert result == Decimal("20")

    def test_total_zero(self):
        assert compute_weight_pct(Decimal("100"), Decimal("0")) is None

    def test_total_none(self):
        assert compute_weight_pct(Decimal("100"), None) is None

    def test_amount_none(self):
        result = compute_weight_pct(None, Decimal("1000"))
        assert result == Decimal("0")

    def test_negative_total(self):
        """合计为负时用绝对值"""
        result = compute_weight_pct(Decimal("200"), Decimal("-1000"))
        assert result == Decimal("20")


# ---------------------------------------------------------------------------
# 预留接口测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_explanation_returns_none(db_session: AsyncSession):
    """预留接口当前返回 None"""
    pid = uuid.uuid4()
    result = await get_audit_explanation_for_row(db_session, pid, 2025, "BS-001")
    assert result is None


# ---------------------------------------------------------------------------
# 集成测试（使用 SQLite 内存库）
# ---------------------------------------------------------------------------

PROJECT_ID = uuid.uuid4()
YEAR = 2025
APPLICABLE_STANDARD = "soe_standalone"


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """创建测试数据：report_config + financial_report + materiality"""

    # 1. 创建 report_config 行（BS 简化为 3 行）
    bs_rows = [
        {"row_code": "BS-001", "row_name": "货币资金", "row_number": 1, "indent_level": 1, "is_total_row": False},
        {"row_code": "BS-002", "row_name": "应收账款", "row_number": 2, "indent_level": 1, "is_total_row": False},
        {"row_code": "BS-039", "row_name": "资产合计", "row_number": 39, "indent_level": 0, "is_total_row": True},
    ]
    is_rows = [
        {"row_code": "IS-001", "row_name": "营业收入", "row_number": 1, "indent_level": 0, "is_total_row": False},
        {"row_code": "IS-002", "row_name": "营业成本", "row_number": 2, "indent_level": 0, "is_total_row": False},
    ]

    for r in bs_rows + is_rows:
        report_type = FinancialReportType.balance_sheet if r["row_code"].startswith("BS") else FinancialReportType.income_statement
        db_session.add(ReportConfig(
            report_type=report_type,
            row_number=r["row_number"],
            row_code=r["row_code"],
            row_name=r["row_name"],
            indent_level=r["indent_level"],
            is_total_row=r["is_total_row"],
            applicable_standard=APPLICABLE_STANDARD,
        ))

    # 2. 创建 financial_report 数据（本年）
    bs_current = [
        ("BS-001", "货币资金", Decimal("1200000")),
        ("BS-002", "应收账款", Decimal("800000")),
        ("BS-039", "资产合计", Decimal("2000000")),
    ]
    bs_prior = [
        ("BS-001", "货币资金", Decimal("1000000")),
        ("BS-002", "应收账款", Decimal("1000000")),
        ("BS-039", "资产合计", Decimal("2000000")),
    ]
    is_current = [
        ("IS-001", "营业收入", Decimal("5000000")),
        ("IS-002", "营业成本", Decimal("3500000")),
    ]
    is_prior = [
        ("IS-001", "营业收入", Decimal("4000000")),
        ("IS-002", "营业成本", Decimal("3000000")),
    ]

    for code, name, amt in bs_current:
        db_session.add(FinancialReport(
            project_id=PROJECT_ID, year=YEAR,
            report_type=FinancialReportType.balance_sheet,
            row_code=code, row_name=name,
            current_period_amount=amt,
        ))
    for code, name, amt in bs_prior:
        db_session.add(FinancialReport(
            project_id=PROJECT_ID, year=YEAR - 1,
            report_type=FinancialReportType.balance_sheet,
            row_code=code, row_name=name,
            current_period_amount=amt,
        ))
    for code, name, amt in is_current:
        db_session.add(FinancialReport(
            project_id=PROJECT_ID, year=YEAR,
            report_type=FinancialReportType.income_statement,
            row_code=code, row_name=name,
            current_period_amount=amt,
        ))
    for code, name, amt in is_prior:
        db_session.add(FinancialReport(
            project_id=PROJECT_ID, year=YEAR - 1,
            report_type=FinancialReportType.income_statement,
            row_code=code, row_name=name,
            current_period_amount=amt,
        ))

    # 3. 创建重要性水平
    db_session.add(Materiality(
        project_id=PROJECT_ID,
        year=YEAR,
        benchmark_type="total_assets",
        benchmark_amount=Decimal("2000000"),
        overall_percentage=Decimal("5"),
        overall_materiality=Decimal("100000"),
        performance_ratio=Decimal("75"),
        performance_materiality=Decimal("75000"),
        trivial_ratio=Decimal("5"),
        trivial_threshold=Decimal("5000"),
    ))

    await db_session.flush()
    return db_session


@pytest.mark.asyncio
async def test_get_analytical_review_data_structure(seeded_db: AsyncSession):
    """验证返回数据结构完整性"""
    result = await get_analytical_review_data(
        seeded_db, PROJECT_ID, YEAR, "A1-13", "standalone"
    )

    assert result["wp_code"] == "A1-13"
    assert result["scope"] == "standalone"
    assert result["year"] == YEAR
    assert result["materiality"] == 100000.0

    sheets = result["sheets"]
    assert "bs_horizontal" in sheets
    assert "bs_vertical" in sheets
    assert "is_horizontal" in sheets
    assert "is_vertical" in sheets
    # ratio_analysis 现在由比率分析引擎计算填充
    assert sheets["ratio_analysis"] is not None
    assert sheets["ratio_analysis"]["title"] == "已审报表财务比率分析"
    assert sheets["ratio_analysis"]["index"] == "A1-13-5"
    assert len(sheets["ratio_analysis"]["categories"]) == 6
    assert sheets["industry_comparison"] is None
    assert sheets["eps_roe"] is None


@pytest.mark.asyncio
async def test_bs_horizontal_calculation(seeded_db: AsyncSession):
    """验证 BS 横向趋势分析计算"""
    result = await get_analytical_review_data(
        seeded_db, PROJECT_ID, YEAR, "A1-13", "standalone"
    )
    bs_h = result["sheets"]["bs_horizontal"]

    assert bs_h["title"] == "已审资产负债表（母公司）横向趋势分析"
    assert bs_h["index"] == "A1-13-1"

    rows = bs_h["rows"]
    assert len(rows) == 3

    # 货币资金：1000000 → 1200000, +200000, +20%, significant (==20% threshold checked via >)
    cash = rows[0]
    assert cash["row_code"] == "BS-001"
    assert cash["prior"] == 1000000.0
    assert cash["current"] == 1200000.0
    assert cash["change"] == 200000.0
    assert cash["change_pct"] == 20.0
    # 200000 > 100000 (materiality) → significant
    assert cash["status"] == "significant"

    # 应收账款：1000000 → 800000, -200000, -20%
    ar = rows[1]
    assert ar["change"] == -200000.0
    assert ar["change_pct"] == -20.0
    # abs(200000) > 100000 → significant
    assert ar["status"] == "significant"


@pytest.mark.asyncio
async def test_bs_vertical_calculation(seeded_db: AsyncSession):
    """验证 BS 纵向结构分析计算"""
    result = await get_analytical_review_data(
        seeded_db, PROJECT_ID, YEAR, "A1-13", "standalone"
    )
    bs_v = result["sheets"]["bs_vertical"]

    rows = bs_v["rows"]
    # 货币资金 本年比重: 1200000 / 2000000 * 100 = 60%
    cash = rows[0]
    assert cash["current_weight_pct"] == 60.0
    # 货币资金 上年比重: 1000000 / 2000000 * 100 = 50%
    assert cash["prior_weight_pct"] == 50.0
    # 比重变动: 60 - 50 = 10%
    assert cash["weight_change_pct"] == 10.0


@pytest.mark.asyncio
async def test_is_horizontal_calculation(seeded_db: AsyncSession):
    """验证 IS 横向趋势分析计算"""
    result = await get_analytical_review_data(
        seeded_db, PROJECT_ID, YEAR, "A1-13", "standalone"
    )
    is_h = result["sheets"]["is_horizontal"]

    rows = is_h["rows"]
    assert len(rows) == 2

    # 营业收入：4000000 → 5000000, +1000000, +25%
    revenue = rows[0]
    assert revenue["change"] == 1000000.0
    assert revenue["change_pct"] == 25.0
    assert revenue["status"] == "significant"

    # 营业成本：3000000 → 3500000, +500000, +16.67%
    cost = rows[1]
    assert cost["change"] == 500000.0
    assert round(cost["change_pct"], 2) == 16.67
    # 500000 > 100000 (materiality) → significant
    assert cost["status"] == "significant"


@pytest.mark.asyncio
async def test_is_vertical_calculation(seeded_db: AsyncSession):
    """验证 IS 纵向结构分析（以营业收入为基数）"""
    result = await get_analytical_review_data(
        seeded_db, PROJECT_ID, YEAR, "A1-13", "standalone"
    )
    is_v = result["sheets"]["is_vertical"]

    rows = is_v["rows"]
    # 营业收入自身比重 = 5000000 / 5000000 * 100 = 100%
    revenue = rows[0]
    assert revenue["current_weight_pct"] == 100.0

    # 营业成本比重 = 3500000 / 5000000 * 100 = 70%
    cost = rows[1]
    assert cost["current_weight_pct"] == 70.0
    # 上年: 3000000 / 4000000 * 100 = 75%
    assert cost["prior_weight_pct"] == 75.0


@pytest.mark.asyncio
async def test_consolidated_scope(seeded_db: AsyncSession):
    """验证合并范围标题"""
    result = await get_analytical_review_data(
        seeded_db, PROJECT_ID, YEAR, "A1-14", "consolidated"
    )
    # 没有 soe_consolidated 的 report_config 数据，rows 为空但结构正确
    assert result["wp_code"] == "A1-14"
    assert result["scope"] == "consolidated"
    bs_h = result["sheets"]["bs_horizontal"]
    assert "合并" in bs_h["title"]


@pytest.mark.asyncio
async def test_no_materiality_defaults_to_zero(db_session: AsyncSession):
    """无重要性水平记录时 materiality 默认 0"""
    pid = uuid.uuid4()
    # 没有 materiality 记录
    result = await get_analytical_review_data(
        db_session, pid, 2025, "A1-13", "standalone"
    )
    assert result["materiality"] == 0.0


def test_build_industry_comparison_structure():
    """build_industry_comparison is now async; test the structure via sync helpers."""
    # Test that the metric constants are properly defined
    from app.services.analytical_review_service import (
        _INDUSTRY_FINANCIAL_METRICS,
        _INDUSTRY_COMPARISON_METRICS,
        _COMPANY_LABELS,
    )
    assert len(_INDUSTRY_FINANCIAL_METRICS) == 7
    assert len(_INDUSTRY_COMPARISON_METRICS) == 5
    assert "self" in _COMPANY_LABELS
    assert len(_COMPANY_LABELS) == 6  # self + A~E


def test_compute_eps_roe_values():
    result = compute_eps_roe_values({
        "net_profit": 1000,
        "equity_end": 5000,
        "equity_begin": 4000,
        "weighted_avg_shares": 100,
        "preferred_dividend": 0,
        "convertible_bond_interest": 0,
        "dilution_extra_shares": 10,
    })
    assert result["roe_diluted"] == 20.0
    assert result["roe_weighted"] == pytest.approx(22.2222, rel=1e-3)
    assert result["basic_eps"] == 10.0
    # diluted_eps = 1000 / (100 + 10) = 9.0909
    assert result["diluted_eps"] == pytest.approx(9.0909, rel=1e-3)


@pytest.mark.asyncio
async def test_build_eps_roe_prefills_inputs(seeded_db: AsyncSession):
    """build_eps_roe is now async; test basic structure."""
    from app.services.analytical_review_service import build_eps_roe as build_eps_roe_fn

    data = await build_eps_roe_fn(
        seeded_db,
        PROJECT_ID,
        "A1-14",
        YEAR,
        net_profit=100.0,
        equity_end=500.0,
        equity_begin=400.0,
        share_capital=50.0,
    )
    assert data["index"] == "A1-14-7"
    assert data["inputs"]["net_profit"] == 100.0
    assert data["computed"]["basic_eps"] is not None


@pytest.mark.asyncio
async def test_a1_13_has_no_listed_sheets(seeded_db: AsyncSession):
    result = await get_analytical_review_data(
        seeded_db, PROJECT_ID, YEAR, "A1-13", "standalone"
    )
    assert result["is_listed"] is False
    assert result["sheets"]["industry_comparison"] is None
    assert result["sheets"]["eps_roe"] is None
