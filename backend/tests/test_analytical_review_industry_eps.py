"""分析性复核 — 同行业对比 + EPS-ROE 保存/读取 round-trip 测试

Validates: Requirements 4.1~4.5, 5.1~5.6
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
from app.models.workpaper_field_override_models import WorkpaperFieldOverride  # noqa: F401

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

PROJECT_ID = uuid.uuid4()
YEAR = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Task 8: 同行业对比分析 round-trip
# ---------------------------------------------------------------------------


class TestIndustryComparisonRoundTrip:
    """验证同行业对比分析数据保存后能正确读取。"""

    @pytest.mark.asyncio
    async def test_save_and_read_companies(self, db: AsyncSession):
        """保存可比公司名称/代码，读取一致。"""
        from app.services.analytical_review_service import (
            build_industry_comparison,
            save_industry_comparison,
        )

        payload = {
            "companies": [
                {"key": "A", "name": "贵州茅台", "stock_code": "600519"},
                {"key": "B", "name": "五粮液", "stock_code": "000858"},
                {"key": "C", "name": "洋河股份", "stock_code": "002304"},
                {"key": "D", "name": "泸州老窖", "stock_code": "000568"},
                {"key": "E", "name": "山西汾酒", "stock_code": "600809"},
            ],
            "financial_data": {},
            "comparison_table": {},
            "data_source_note": "Wind资讯",
        }
        await save_industry_comparison(db, PROJECT_ID, YEAR, payload)
        await db.flush()

        result = await build_industry_comparison(db, PROJECT_ID, "A1-14", YEAR)

        # 验证公司信息
        assert result["companies"][0]["name"] == "贵州茅台"
        assert result["companies"][0]["stock_code"] == "600519"
        assert result["companies"][4]["name"] == "山西汾酒"
        assert result["data_source_note"] == "Wind资讯"

    @pytest.mark.asyncio
    async def test_save_and_read_financial_data(self, db: AsyncSession):
        """保存主要财务数据指标值，读取一致。"""
        from app.services.analytical_review_service import (
            build_industry_comparison,
            save_industry_comparison,
        )

        payload = {
            "companies": [{"key": "A", "name": "测试A", "stock_code": "000001"}],
            "financial_data": {
                "total_assets": {
                    "2025": {"self": 1000000, "A": 2000000},
                    "2024": {"self": 900000, "A": 1800000},
                }
            },
            "comparison_table": {
                "roe": {
                    "2025": {"self": 15.5, "A": 18.2},
                }
            },
            "data_source_note": "",
        }
        await save_industry_comparison(db, PROJECT_ID, YEAR, payload)
        await db.flush()

        result = await build_industry_comparison(db, PROJECT_ID, "A1-14", YEAR)

        assert result["financial_data"]["total_assets"]["2025"]["self"] == 1000000
        assert result["financial_data"]["total_assets"]["2025"]["A"] == 2000000
        assert result["financial_data"]["total_assets"]["2024"]["self"] == 900000
        assert result["comparison_table"]["roe"]["2025"]["self"] == 15.5
        assert result["comparison_table"]["roe"]["2025"]["A"] == 18.2

    @pytest.mark.asyncio
    async def test_empty_read_returns_empty_structure(self, db: AsyncSession):
        """无保存数据时返回空结构。"""
        from app.services.analytical_review_service import build_industry_comparison

        result = await build_industry_comparison(db, PROJECT_ID, "A1-14", YEAR)

        assert len(result["companies"]) == 5
        assert result["companies"][0]["name"] == ""
        assert result["data_source_note"] == ""
        assert result["years"] == [2023, 2024, 2025]


# ---------------------------------------------------------------------------
# Task 9: EPS-ROE 计算 + round-trip
# ---------------------------------------------------------------------------


class TestEpsRoeCalculation:
    """验证 EPS-ROE 加权计算公式正确性（CAS 34）。"""

    def test_weighted_avg_shares_single_period(self):
        """单段期初股份 × 12个月 / 12 = 全额。"""
        from app.services.analytical_review_service import compute_weighted_avg_shares

        share_changes = [
            {"cum_shares": 100_000_000, "time_weight_months": 12},
        ]
        result = compute_weighted_avg_shares(share_changes)
        assert result == 100_000_000.0

    def test_weighted_avg_shares_multi_period(self):
        """多段加权：期初 1亿×6月 + 增发后 1.5亿×6月 = 1.25亿。"""
        from app.services.analytical_review_service import compute_weighted_avg_shares

        share_changes = [
            {"cum_shares": 100_000_000, "time_weight_months": 6},
            {"cum_shares": 150_000_000, "time_weight_months": 6},
        ]
        result = compute_weighted_avg_shares(share_changes)
        assert result == 125_000_000.0

    def test_weighted_avg_shares_empty(self):
        """空列表返回 0。"""
        from app.services.analytical_review_service import compute_weighted_avg_shares

        assert compute_weighted_avg_shares([]) == 0

    def test_compute_eps_roe_with_preferred_dividend(self):
        """优先股股利扣除后计算 EPS。"""
        from app.services.analytical_review_service import compute_eps_roe_values

        result = compute_eps_roe_values({
            "net_profit": 1000,
            "equity_end": 5000,
            "equity_begin": 4000,
            "weighted_avg_shares": 100,
            "preferred_dividend": 200,
            "convertible_bond_interest": 0,
            "dilution_extra_shares": 0,
        })
        # P = 1000 - 200 = 800
        # basic_eps = 800 / 100 = 8.0
        assert result["basic_eps"] == 8.0
        # roe_diluted = 800 / 5000 * 100 = 16.0
        assert result["roe_diluted"] == 16.0
        # roe_weighted = 800 / ((5000+4000)/2) * 100 = 17.7778
        assert result["roe_weighted"] == pytest.approx(17.7778, rel=1e-3)

    def test_diluted_eps_with_convertible_bonds(self):
        """稀释每股收益：分子加回可转债税后利息，分母加稀释股数。"""
        from app.services.analytical_review_service import compute_eps_roe_values

        result = compute_eps_roe_values({
            "net_profit": 1000,
            "equity_end": 5000,
            "equity_begin": 4000,
            "weighted_avg_shares": 100,
            "preferred_dividend": 0,
            "convertible_bond_interest": 50,  # 税后利息
            "dilution_extra_shares": 20,      # 稀释增加股数
        })
        # diluted_eps = (1000 + 50) / (100 + 20) = 1050 / 120 = 8.75
        assert result["diluted_eps"] == 8.75


class TestEpsRoeRoundTrip:
    """验证 EPS-ROE 参数保存后能正确读取并重算。"""

    @pytest.mark.asyncio
    async def test_save_and_recompute(self, db: AsyncSession):
        """保存股本变动参数后重新计算结果。"""
        from app.services.analytical_review_service import save_eps_roe

        payload = {
            "params": {
                "net_profit": 50_000_000,
                "equity_end": 200_000_000,
                "equity_begin": 180_000_000,
                "preferred_dividend": 0,
            },
            "share_changes": [
                {"id": "s0", "cum_shares": 100_000_000, "time_weight_months": 6},
                {"id": "s1", "cum_shares": 120_000_000, "time_weight_months": 6},
            ],
            "dilution_factors": {
                "convertible_bond_face_value": 0,
                "convertible_bond_rate": 0,
                "convertible_bond_shares": 0,
                "option_exercise_price": 0,
                "option_shares": 0,
            },
        }
        computed = await save_eps_roe(db, PROJECT_ID, YEAR, payload)
        await db.flush()

        # 加权平均股数 = 1亿×6/12 + 1.2亿×6/12 = 5千万 + 6千万 = 1.1亿
        # basic_eps = 5千万 / 1.1亿 = 0.4545
        assert computed["basic_eps"] == pytest.approx(0.4545, rel=1e-3)
        # roe_diluted = 5千万 / 2亿 * 100 = 25.0
        assert computed["roe_diluted"] == 25.0
        # roe_weighted = 5千万 / ((2亿+1.8亿)/2) * 100 = 5千万/1.9亿*100 = 26.3158
        assert computed["roe_weighted"] == pytest.approx(26.3158, rel=1e-3)

    @pytest.mark.asyncio
    async def test_save_read_persistence(self, db: AsyncSession):
        """保存后通过 build_eps_roe 读取验证持久化。"""
        from app.services.analytical_review_service import build_eps_roe, save_eps_roe

        payload = {
            "params": {
                "net_profit": 10_000_000,
                "equity_end": 80_000_000,
                "equity_begin": 70_000_000,
                "preferred_dividend": 500_000,
            },
            "share_changes": [
                {"id": "s0", "cum_shares": 50_000_000, "time_weight_months": 12},
            ],
            "dilution_factors": {
                "convertible_bond_face_value": 10_000_000,
                "convertible_bond_rate": 5,
                "convertible_bond_shares": 2_000_000,
                "option_exercise_price": 10,
                "option_shares": 500_000,
            },
        }
        await save_eps_roe(db, PROJECT_ID, YEAR, payload)
        await db.flush()

        # 通过 build_eps_roe 读取（模拟页面加载）
        result = await build_eps_roe(
            db, PROJECT_ID, "A1-14", YEAR,
            net_profit=None, equity_end=None, equity_begin=None, share_capital=None,
        )

        # 用户参数应覆盖自动取数
        assert result["inputs"]["net_profit"] == 10_000_000
        assert result["inputs"]["equity_end"] == 80_000_000
        assert result["inputs"]["preferred_dividend"] == 500_000
        assert result["dilution_factors"]["convertible_bond_face_value"] == 10_000_000
        assert result["dilution_factors"]["convertible_bond_rate"] == 5
        assert len(result["share_changes"]) == 1
        assert result["share_changes"][0]["cum_shares"] == 50_000_000
        # 计算结果存在
        assert result["computed"]["basic_eps"] is not None
        assert result["computed"]["diluted_eps"] is not None
