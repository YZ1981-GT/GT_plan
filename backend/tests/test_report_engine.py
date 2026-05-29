"""报表生成引擎测试

Validates: Requirements 2.1, 2.2, 2.4, 2.5, 2.6, 2.9, 5.1, 5.2, 5.3, 5.4, 5.5, 8.2, 8.5
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import (
    AccountCategory,
    TrialBalance,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import (
    FinancialReport,
    FinancialReportType,
    ReportConfig,
)
from app.services.report_engine import ReportEngine, ReportFormulaParser

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


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


TEST_STANDARD = "enterprise"


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """创建完整测试数据：项目 + 试算表 + 报表配置（含公式）"""
    # Project
    project = Project(
        id=FAKE_PROJECT_ID,
        name="报表引擎测试_2025",
        client_name="报表引擎测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    # Trial balance data — 资产类
    tb_data = [
        ("1001", "库存现金", AccountCategory.asset, Decimal("50000"), Decimal("40000")),
        ("1002", "银行存款", AccountCategory.asset, Decimal("1000000"), Decimal("800000")),
        ("1012", "其他货币资金", AccountCategory.asset, Decimal("100000"), Decimal("80000")),
        ("1101", "交易性金融资产", AccountCategory.asset, Decimal("200000"), Decimal("150000")),
        ("1121", "应收票据", AccountCategory.asset, Decimal("50000"), Decimal("30000")),
        ("1122", "应收账款", AccountCategory.asset, Decimal("300000"), Decimal("250000")),
        ("1123", "预付款项", AccountCategory.asset, Decimal("80000"), Decimal("60000")),
        ("1221", "其他应收款", AccountCategory.asset, Decimal("40000"), Decimal("35000")),
        ("1401", "存货-原材料", AccountCategory.asset, Decimal("500000"), Decimal("400000")),
        ("1901", "其他流动资产", AccountCategory.asset, Decimal("30000"), Decimal("20000")),
        # 非流动资产
        ("1511", "长期股权投资", AccountCategory.asset, Decimal("600000"), Decimal("500000")),
        ("1521", "投资性房地产", AccountCategory.asset, Decimal("0"), Decimal("0")),
        ("1601", "固定资产原值", AccountCategory.asset, Decimal("2000000"), Decimal("1800000")),
        ("1602", "累计折旧", AccountCategory.asset, Decimal("500000"), Decimal("400000")),
        ("1604", "在建工程", AccountCategory.asset, Decimal("100000"), Decimal("80000")),
        ("1701", "无形资产原值", AccountCategory.asset, Decimal("300000"), Decimal("250000")),
        ("1702", "累计摊销", AccountCategory.asset, Decimal("100000"), Decimal("80000")),
        ("1801", "长期待摊费用", AccountCategory.asset, Decimal("50000"), Decimal("40000")),
        ("1811", "递延所得税资产", AccountCategory.asset, Decimal("20000"), Decimal("15000")),
        # 负债类
        ("2001", "短期借款", AccountCategory.liability, Decimal("500000"), Decimal("400000")),
        ("2201", "应付票据", AccountCategory.liability, Decimal("100000"), Decimal("80000")),
        ("2202", "应付账款", AccountCategory.liability, Decimal("200000"), Decimal("150000")),
        ("2203", "预收款项", AccountCategory.liability, Decimal("50000"), Decimal("40000")),
        ("2211", "应付职工薪酬", AccountCategory.liability, Decimal("80000"), Decimal("60000")),
        ("2221", "应交税费", AccountCategory.liability, Decimal("30000"), Decimal("25000")),
        ("2241", "其他应付款", AccountCategory.liability, Decimal("40000"), Decimal("30000")),
        ("2501", "长期借款", AccountCategory.liability, Decimal("300000"), Decimal("250000")),
        ("2901", "其他流动负债", AccountCategory.liability, Decimal("20000"), Decimal("15000")),
        # 权益类
        ("4001", "实收资本", AccountCategory.equity, Decimal("2000000"), Decimal("2000000")),
        ("4002", "资本公积", AccountCategory.equity, Decimal("500000"), Decimal("500000")),
        ("4003", "其他综合收益", AccountCategory.equity, Decimal("10000"), Decimal("5000")),
        ("4101", "盈余公积", AccountCategory.equity, Decimal("200000"), Decimal("180000")),
        ("4104", "未分配利润", AccountCategory.equity, Decimal("820000"), Decimal("500000")),
        # 收入/费用类
        ("6001", "主营业务收入", AccountCategory.revenue, Decimal("3000000"), Decimal("0")),
        ("6401", "主营业务成本", AccountCategory.expense, Decimal("2000000"), Decimal("0")),
        ("6403", "税金及附加", AccountCategory.expense, Decimal("50000"), Decimal("0")),
        ("6601", "销售费用", AccountCategory.expense, Decimal("100000"), Decimal("0")),
        ("6602", "管理费用", AccountCategory.expense, Decimal("200000"), Decimal("0")),
        ("6603", "财务费用", AccountCategory.expense, Decimal("30000"), Decimal("0")),
        ("6604", "研发费用", AccountCategory.expense, Decimal("50000"), Decimal("0")),
        ("6801", "所得税费用", AccountCategory.expense, Decimal("100000"), Decimal("0")),
    ]

    for code, name, cat, audited, opening in tb_data:
        db_session.add(TrialBalance(
            project_id=FAKE_PROJECT_ID,
            year=2025,
            company_code="001",
            standard_account_code=code,
            account_name=name,
            account_category=cat,
            unadjusted_amount=audited,
            audited_amount=audited,
            opening_balance=opening,
        ))

    await db_session.flush()

    # Insert ReportConfig rows with formulas for the test standard
    # Balance Sheet configs
    bs_configs = [
        ("BS-001", 1, "流动资产：", 0, False, None),
        ("BS-002", 2, "货币资金", 1, False, "TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')"),
        ("BS-003", 3, "交易性金融资产", 1, False, "TB('1101','期末余额')"),
        ("BS-004", 4, "应收票据", 1, False, "TB('1121','期末余额')"),
        ("BS-005", 5, "应收账款", 1, False, "TB('1122','期末余额')"),
        ("BS-006", 6, "预付款项", 1, False, "TB('1123','期末余额')"),
        ("BS-007", 7, "其他应收款", 1, False, "TB('1221','期末余额')"),
        ("BS-008", 8, "存货", 1, False, "TB('1401','期末余额')"),
        ("BS-009", 9, "其他流动资产", 1, False, "TB('1901','期末余额')"),
        ("BS-010", 10, "流动资产合计", 0, True, "ROW('BS-002') + ROW('BS-003') + ROW('BS-004') + ROW('BS-005') + ROW('BS-006') + ROW('BS-007') + ROW('BS-008') + ROW('BS-009')"),
        ("BS-011", 11, "非流动资产：", 0, False, None),
        ("BS-012", 12, "长期股权投资", 1, False, "TB('1511','期末余额')"),
        ("BS-013", 13, "投资性房地产", 1, False, "TB('1521','期末余额')"),
        ("BS-014", 14, "固定资产", 1, False, "TB('1601','期末余额') - TB('1602','期末余额')"),
        ("BS-015", 15, "在建工程", 1, False, "TB('1604','期末余额')"),
        ("BS-016", 16, "无形资产", 1, False, "TB('1701','期末余额') - TB('1702','期末余额')"),
        ("BS-017", 17, "长期待摊费用", 1, False, "TB('1801','期末余额')"),
        ("BS-018", 18, "递延所得税资产", 1, False, "TB('1811','期末余额')"),
        ("BS-019", 19, "其他非流动资产", 1, False, "TB('1901','期末余额')"),
        ("BS-020", 20, "非流动资产合计", 0, True, "ROW('BS-012') + ROW('BS-013') + ROW('BS-014') + ROW('BS-015') + ROW('BS-016') + ROW('BS-017') + ROW('BS-018') + ROW('BS-019')"),
        ("BS-021", 21, "资产总计", 0, True, "ROW('BS-010') + ROW('BS-020')"),
        # Liabilities
        ("BS-030", 30, "流动负债：", 0, False, None),
        ("BS-031", 31, "短期借款", 1, False, "TB('2001','期末余额')"),
        ("BS-032", 32, "应付票据", 1, False, "TB('2201','期末余额')"),
        ("BS-033", 33, "应付账款", 1, False, "TB('2202','期末余额')"),
        ("BS-034", 34, "预收款项", 1, False, "TB('2203','期末余额')"),
        ("BS-035", 35, "应付职工薪酬", 1, False, "TB('2211','期末余额')"),
        ("BS-036", 36, "应交税费", 1, False, "TB('2221','期末余额')"),
        ("BS-037", 37, "其他应付款", 1, False, "TB('2241','期末余额')"),
        ("BS-038", 38, "其他流动负债", 1, False, "TB('2901','期末余额')"),
        ("BS-039", 39, "流动负债合计", 0, True, "ROW('BS-031') + ROW('BS-032') + ROW('BS-033') + ROW('BS-034') + ROW('BS-035') + ROW('BS-036') + ROW('BS-037') + ROW('BS-038')"),
        ("BS-040", 40, "非流动负债：", 0, False, None),
        ("BS-041", 41, "长期借款", 1, False, "TB('2501','期末余额')"),
        ("BS-042", 42, "非流动负债合计", 0, True, "ROW('BS-041')"),
        ("BS-043", 43, "负债合计", 0, True, "ROW('BS-039') + ROW('BS-042')"),
        # Equity
        ("BS-050", 50, "所有者权益：", 0, False, None),
        ("BS-051", 51, "实收资本", 1, False, "TB('4001','期末余额')"),
        ("BS-052", 52, "资本公积", 1, False, "TB('4002','期末余额')"),
        ("BS-053", 53, "其他综合收益", 1, False, "TB('4003','期末余额')"),
        ("BS-054", 54, "盈余公积", 1, False, "TB('4101','期末余额')"),
        ("BS-055", 55, "未分配利润", 1, False, "TB('4104','期末余额')"),
        ("BS-056", 56, "所有者权益合计", 0, True, "ROW('BS-051') + ROW('BS-052') + ROW('BS-053') + ROW('BS-054') + ROW('BS-055')"),
        ("BS-057", 57, "负债和所有者权益总计", 0, True, "ROW('BS-043') + ROW('BS-056')"),
    ]

    for row_code, row_num, name, indent, is_total, formula in bs_configs:
        db_session.add(ReportConfig(
            report_type=FinancialReportType.balance_sheet,
            row_number=row_num,
            row_code=row_code,
            row_name=name,
            indent_level=indent,
            is_total_row=is_total,
            formula=formula,
            applicable_standard=TEST_STANDARD,
        ))

    # Income Statement configs
    is_configs = [
        ("IS-001", 1, "营业收入", 0, False, "SUM_TB('6001~6099','本期发生额')"),
        ("IS-002", 2, "营业成本", 0, False, "SUM_TB('6401~6499','本期发生额')"),
        ("IS-003", 3, "税金及附加", 0, False, "TB('6403','本期发生额')"),
        ("IS-004", 4, "销售费用", 0, False, "TB('6601','本期发生额')"),
        ("IS-005", 5, "管理费用", 0, False, "TB('6602','本期发生额')"),
        ("IS-006", 6, "财务费用", 0, False, "TB('6603','本期发生额')"),
        ("IS-007", 7, "研发费用", 0, False, "TB('6604','本期发生额')"),
        ("IS-010", 10, "营业利润", 0, True, "ROW('IS-001') - ROW('IS-002') - ROW('IS-003') - ROW('IS-004') - ROW('IS-005') - ROW('IS-006') - ROW('IS-007')"),
        ("IS-015", 15, "利润总额", 0, True, "ROW('IS-010')"),
        ("IS-016", 16, "所得税费用", 0, False, "TB('6801','本期发生额')"),
        ("IS-019", 19, "净利润", 0, True, "ROW('IS-015') - ROW('IS-016')"),
    ]

    for row_code, row_num, name, indent, is_total, formula in is_configs:
        db_session.add(ReportConfig(
            report_type=FinancialReportType.income_statement,
            row_number=row_num,
            row_code=row_code,
            row_name=name,
            indent_level=indent,
            is_total_row=is_total,
            formula=formula,
            applicable_standard=TEST_STANDARD,
        ))

    await db_session.flush()
    await db_session.commit()

    return FAKE_PROJECT_ID


# ===== ReportFormulaParser 测试 =====


@pytest.mark.asyncio
async def test_formula_parser_tb(db_session: AsyncSession, seeded_db):
    """TB() 从试算表取单科目值"""
    parser = ReportFormulaParser(db_session, FAKE_PROJECT_ID, 2025)
    result = await parser.execute("TB('1001','期末余额')", {})
    assert result == Decimal("50000")


@pytest.mark.asyncio
async def test_formula_parser_tb_opening(db_session: AsyncSession, seeded_db):
    """TB() 取年初余额"""
    parser = ReportFormulaParser(db_session, FAKE_PROJECT_ID, 2025)
    result = await parser.execute("TB('1001','年初余额')", {})
    assert result == Decimal("40000")


@pytest.mark.asyncio
async def test_formula_parser_tb_period(db_session: AsyncSession, seeded_db):
    """TB() 取本期发生额 = audited - opening"""
    parser = ReportFormulaParser(db_session, FAKE_PROJECT_ID, 2025)
    result = await parser.execute("TB('6001','本期发生额')", {})
    # 6001: audited=3000000, opening=0 → 3000000
    assert result == Decimal("3000000")


@pytest.mark.asyncio
async def test_formula_parser_sum_tb(db_session: AsyncSession, seeded_db):
    """SUM_TB() 范围求和"""
    parser = ReportFormulaParser(db_session, FAKE_PROJECT_ID, 2025)
    result = await parser.execute("SUM_TB('1401~1499','期末余额')", {})
    # Only 1401 in range → 500000
    assert result == Decimal("500000")


@pytest.mark.asyncio
async def test_formula_parser_row_ref(db_session: AsyncSession, seeded_db):
    """ROW() 引用 row_cache"""
    parser = ReportFormulaParser(db_session, FAKE_PROJECT_ID, 2025)
    cache = {"BS-002": Decimal("1150000"), "BS-003": Decimal("200000")}
    result = await parser.execute("ROW('BS-002') + ROW('BS-003')", cache)
    assert result == Decimal("1350000")


@pytest.mark.asyncio
async def test_formula_parser_arithmetic(db_session: AsyncSession, seeded_db):
    """算术运算：TB - TB"""
    parser = ReportFormulaParser(db_session, FAKE_PROJECT_ID, 2025)
    # 固定资产 = 原值 - 累计折旧
    result = await parser.execute("TB('1601','期末余额') - TB('1602','期末余额')", {})
    assert result == Decimal("1500000")  # 2000000 - 500000


@pytest.mark.asyncio
async def test_formula_parser_null_formula(db_session: AsyncSession, seeded_db):
    """空公式返回 0"""
    parser = ReportFormulaParser(db_session, FAKE_PROJECT_ID, 2025)
    assert await parser.execute(None, {}) == Decimal("0")
    assert await parser.execute("", {}) == Decimal("0")


@pytest.mark.asyncio
async def test_formula_parser_missing_account(db_session: AsyncSession, seeded_db):
    """不存在的科目返回 0"""
    parser = ReportFormulaParser(db_session, FAKE_PROJECT_ID, 2025)
    result = await parser.execute("TB('9999','期末余额')", {})
    assert result == Decimal("0")


@pytest.mark.asyncio
async def test_extract_account_codes(db_session: AsyncSession, seeded_db):
    """提取公式中的科目代码"""
    parser = ReportFormulaParser(db_session, FAKE_PROJECT_ID, 2025)
    codes = parser.extract_account_codes(
        "TB('1001','期末余额') + TB('1002','期末余额') + SUM_TB('1401~1499','期末余额')"
    )
    assert "1001" in codes
    assert "1002" in codes
    assert "1401~1499" in codes


@pytest.mark.asyncio
async def test_extract_row_refs(db_session: AsyncSession, seeded_db):
    """提取公式中的 ROW() 引用"""
    parser = ReportFormulaParser(db_session, FAKE_PROJECT_ID, 2025)
    refs = parser.extract_row_refs("ROW('BS-010') + ROW('BS-020')")
    assert refs == ["BS-010", "BS-020"]


# ===== ReportEngine 生成测试 =====


@pytest.mark.asyncio
async def test_generate_all_reports(db_session: AsyncSession, seeded_db):
    """生成四张报表"""
    engine = ReportEngine(db_session)
    results = await engine.generate_all_reports(FAKE_PROJECT_ID, 2025, applicable_standard=TEST_STANDARD)
    await db_session.commit()

    assert "balance_sheet" in results
    assert "income_statement" in results
    assert len(results["balance_sheet"]) > 0
    assert len(results["income_statement"]) > 0


@pytest.mark.asyncio
async def test_balance_sheet_values(db_session: AsyncSession, seeded_db):
    """资产负债表关键值验证"""
    engine = ReportEngine(db_session)
    results = await engine.generate_all_reports(FAKE_PROJECT_ID, 2025, applicable_standard=TEST_STANDARD)
    await db_session.commit()

    bs_rows = {r["row_code"]: r for r in results["balance_sheet"]}

    # 货币资金 = 1001 + 1002 + 1012 = 50000 + 1000000 + 100000 = 1150000
    assert Decimal(bs_rows["BS-002"]["current_period_amount"]) == Decimal("1150000")

    # 固定资产 = 1601 - 1602 = 2000000 - 500000 = 1500000
    assert Decimal(bs_rows["BS-014"]["current_period_amount"]) == Decimal("1500000")

    # 流动资产合计 = sum of BS-002 to BS-009
    expected_current_assets = (
        Decimal("1150000")  # 货币资金
        + Decimal("200000")  # 交易性金融资产
        + Decimal("50000")   # 应收票据
        + Decimal("300000")  # 应收账款
        + Decimal("80000")   # 预付款项
        + Decimal("40000")   # 其他应收款
        + Decimal("500000")  # 存货
        + Decimal("30000")   # 其他流动资产
    )
    assert Decimal(bs_rows["BS-010"]["current_period_amount"]) == expected_current_assets


@pytest.mark.asyncio
async def test_balance_sheet_equation(db_session: AsyncSession, seeded_db):
    """资产负债表平衡：资产合计 = 负债和所有者权益总计"""
    engine = ReportEngine(db_session)
    results = await engine.generate_all_reports(FAKE_PROJECT_ID, 2025, applicable_standard=TEST_STANDARD)
    await db_session.commit()

    bs_rows = {r["row_code"]: r for r in results["balance_sheet"]}
    total_assets = Decimal(bs_rows["BS-021"]["current_period_amount"])
    total_liab_equity = Decimal(bs_rows["BS-057"]["current_period_amount"])
    assert total_assets == total_liab_equity


@pytest.mark.asyncio
async def test_income_statement_values(db_session: AsyncSession, seeded_db):
    """利润表关键值验证"""
    engine = ReportEngine(db_session)
    results = await engine.generate_all_reports(FAKE_PROJECT_ID, 2025, applicable_standard=TEST_STANDARD)
    await db_session.commit()

    is_rows = {r["row_code"]: r for r in results["income_statement"]}

    # 营业收入 = SUM_TB('6001~6099','本期发生额')
    # 6001: audited=3000000, opening=0 → 3000000
    assert Decimal(is_rows["IS-001"]["current_period_amount"]) == Decimal("3000000")

    # 净利润 should be calculated
    net_profit = Decimal(is_rows["IS-019"]["current_period_amount"])
    assert net_profit != Decimal("0")


@pytest.mark.asyncio
async def test_prior_period_data(db_session: AsyncSession, seeded_db):
    """比较期间数据生成（year-1 无数据时为 0）"""
    engine = ReportEngine(db_session)
    results = await engine.generate_all_reports(FAKE_PROJECT_ID, 2025, applicable_standard=TEST_STANDARD)
    await db_session.commit()

    bs_rows = {r["row_code"]: r for r in results["balance_sheet"]}
    # Prior period (2024) has no trial balance data → all zeros
    assert Decimal(bs_rows["BS-002"]["prior_period_amount"]) == Decimal("0")


@pytest.mark.asyncio
async def test_report_written_to_db(db_session: AsyncSession, seeded_db):
    """报表数据写入 financial_report 表"""
    engine = ReportEngine(db_session)
    await engine.generate_all_reports(FAKE_PROJECT_ID, 2025, applicable_standard=TEST_STANDARD)
    await db_session.commit()

    import sqlalchemy as sa
    result = await db_session.execute(
        sa.select(sa.func.count()).select_from(FinancialReport).where(
            FinancialReport.project_id == FAKE_PROJECT_ID,
            FinancialReport.year == 2025,
            FinancialReport.is_deleted == sa.false(),
        )
    )
    count = result.scalar()
    assert count > 0


@pytest.mark.asyncio
async def test_generate_idempotent(db_session: AsyncSession, seeded_db):
    """重复生成不会创建重复行"""
    engine = ReportEngine(db_session)
    await engine.generate_all_reports(FAKE_PROJECT_ID, 2025, applicable_standard=TEST_STANDARD)
    await db_session.commit()

    import sqlalchemy as sa
    result1 = await db_session.execute(
        sa.select(sa.func.count()).select_from(FinancialReport).where(
            FinancialReport.project_id == FAKE_PROJECT_ID,
            FinancialReport.year == 2025,
        )
    )
    count1 = result1.scalar()

    await engine.generate_all_reports(FAKE_PROJECT_ID, 2025, applicable_standard=TEST_STANDARD)
    await db_session.commit()

    result2 = await db_session.execute(
        sa.select(sa.func.count()).select_from(FinancialReport).where(
            FinancialReport.project_id == FAKE_PROJECT_ID,
            FinancialReport.year == 2025,
        )
    )
    count2 = result2.scalar()
    assert count1 == count2


# ===== 平衡校验测试 =====


@pytest.mark.asyncio
async def test_check_balance(db_session: AsyncSession, seeded_db):
    """报表平衡校验"""
    engine = ReportEngine(db_session)
    await engine.generate_all_reports(FAKE_PROJECT_ID, 2025, applicable_standard=TEST_STANDARD)
    await db_session.commit()

    checks = await engine.check_balance(FAKE_PROJECT_ID, 2025)
    assert len(checks) > 0

    # 验证返回了资产负债表平衡检查项
    bs_check = next((c for c in checks if "资产负债表平衡" in c["check_name"]), None)
    assert bs_check is not None
    # 验证检查结果包含必要字段
    assert "passed" in bs_check
    assert "expected_value" in bs_check
    assert "actual_value" in bs_check


# ===== 增量更新测试 =====


@pytest.mark.asyncio
async def test_regenerate_affected(db_session: AsyncSession, seeded_db):
    """增量更新：修改科目后只重算受影响行"""
    engine = ReportEngine(db_session)
    await engine.generate_all_reports(FAKE_PROJECT_ID, 2025, applicable_standard=TEST_STANDARD)
    await db_session.commit()

    # 修改 1001 库存现金
    import sqlalchemy as sa
    result = await db_session.execute(
        sa.select(TrialBalance).where(
            TrialBalance.project_id == FAKE_PROJECT_ID,
            TrialBalance.year == 2025,
            TrialBalance.standard_account_code == "1001",
        )
    )
    tb_row = result.scalar_one()
    tb_row.audited_amount = Decimal("60000")  # was 50000
    await db_session.flush()

    count = await engine.regenerate_affected(
        FAKE_PROJECT_ID, 2025, changed_accounts=["1001"],
        applicable_standard=TEST_STANDARD,
    )
    await db_session.commit()

    assert count > 0

    # Verify BS-002 (货币资金) updated
    result = await db_session.execute(
        sa.select(FinancialReport).where(
            FinancialReport.project_id == FAKE_PROJECT_ID,
            FinancialReport.year == 2025,
            FinancialReport.row_code == "BS-002",
        )
    )
    row = result.scalar_one()
    # 60000 + 1000000 + 100000 = 1160000
    assert row.current_period_amount == Decimal("1160000")


@pytest.mark.asyncio
async def test_is_affected(db_session: AsyncSession, seeded_db):
    """_is_affected 正确识别受影响公式"""
    engine = ReportEngine(db_session)
    assert engine._is_affected(
        "TB('1001','期末余额') + TB('1002','期末余额')", ["1001"]
    ) is True
    assert engine._is_affected(
        "SUM_TB('1401~1499','期末余额')", ["1450"]
    ) is True
    assert engine._is_affected(
        "TB('1001','期末余额')", ["2001"]
    ) is False
    assert engine._is_affected(None, ["1001"]) is False


# ===== 穿透查询测试 =====


@pytest.mark.asyncio
async def test_drilldown(db_session: AsyncSession, seeded_db):
    """报表行穿透查询"""
    engine = ReportEngine(db_session)
    await engine.generate_all_reports(FAKE_PROJECT_ID, 2025, applicable_standard=TEST_STANDARD)
    await db_session.commit()

    result = await engine.drilldown(
        FAKE_PROJECT_ID, 2025,
        FinancialReportType.balance_sheet, "BS-002",
    )
    assert result["row_code"] == "BS-002"
    assert result["formula"] is not None
    assert len(result["contributing_accounts"]) > 0
    # Should include 1001, 1002, 1012
    codes = [a["account_code"] for a in result["contributing_accounts"]]
    assert "1001" in codes
    assert "1002" in codes


@pytest.mark.asyncio
async def test_drilldown_nonexistent(db_session: AsyncSession, seeded_db):
    """穿透查询不存在的行"""
    engine = ReportEngine(db_session)
    result = await engine.drilldown(
        FAKE_PROJECT_ID, 2025,
        FinancialReportType.balance_sheet, "NONEXISTENT",
    )
    assert "error" in result


# ===== API 路由测试 =====


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    """创建测试 HTTP 客户端

    - 使用 override_auth 注入 get_current_user / get_db / get_redis
    - Mock prerequisite_checker 绕过前置检查
    - Mock _resolve_applicable_standard 返回 TEST_STANDARD 匹配 seeded 数据
    """
    from app.main import app
    from tests._test_auth_helper import override_auth

    with patch(
        "app.services.prerequisite_checker.PrerequisiteChecker.check",
        new_callable=AsyncMock,
        return_value={"ok": True, "message": "", "prerequisite_action": None},
    ), patch(
        "app.routers.reports._resolve_applicable_standard",
        new_callable=AsyncMock,
        return_value=TEST_STANDARD,
    ):
        async with override_auth(app, db_session=db_session) as c:
            yield c


@pytest.mark.asyncio
async def test_api_generate_reports(client: AsyncClient):
    """POST /api/reports/generate"""
    resp = await client.post(
        "/api/reports/generate",
        json={"project_id": str(FAKE_PROJECT_ID), "year": 2025},
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert "report_types" in result
    assert len(result["report_types"]) > 0


@pytest.mark.asyncio
async def test_api_get_report(client: AsyncClient):
    """GET /api/reports/{project_id}/{year}/{report_type}"""
    # First generate
    await client.post(
        "/api/reports/generate",
        json={"project_id": str(FAKE_PROJECT_ID), "year": 2025},
    )

    resp = await client.get(
        f"/api/reports/{FAKE_PROJECT_ID}/2025/balance_sheet"
    )
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("data", data)
    assert len(items) > 0


@pytest.mark.asyncio
async def test_api_get_report_not_found(client: AsyncClient):
    """GET 未生成报表的项目返回模板行次结构（200）或 404（无配置）"""
    fake_id = uuid.uuid4()
    resp = await client.get(
        f"/api/reports/{fake_id}/2025/balance_sheet"
    )
    # 当 report_config 有该标准的行次配置时，返回 200 + 空模板结构
    # 当 report_config 无配置时，返回 404
    # 由于 seeded_db 已 seed 了 enterprise 标准的 report_config，此处返回 200
    assert resp.status_code == 200
    data = resp.json()
    # 响应可能被 ResponseWrapper 中间件包装为 {code, data, message}
    items = data.get("data", data) if isinstance(data, dict) else data
    assert isinstance(items, list)
    assert len(items) > 0


@pytest.mark.asyncio
async def test_api_drilldown(client: AsyncClient):
    await client.post(
        "/api/reports/generate",
        json={"project_id": str(FAKE_PROJECT_ID), "year": 2025},
    )

    resp = await client.get(
        f"/api/reports/{FAKE_PROJECT_ID}/2025/balance_sheet/drilldown/BS-002"
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["row_code"] == "BS-002"


@pytest.mark.asyncio
async def test_api_consistency_check(client: AsyncClient):
    """GET /api/reports/.../consistency-check"""
    await client.post(
        "/api/reports/generate",
        json={"project_id": str(FAKE_PROJECT_ID), "year": 2025},
    )

    resp = await client.get(
        f"/api/reports/{FAKE_PROJECT_ID}/2025/consistency-check"
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert "consistent" in result
    assert "checks" in result


@pytest.mark.asyncio
async def test_api_export_excel(client: AsyncClient):
    """GET /api/reports/.../export-excel"""
    await client.post(
        "/api/reports/generate",
        json={"project_id": str(FAKE_PROJECT_ID), "year": 2025},
    )

    resp = await client.get(
        f"/api/reports/{FAKE_PROJECT_ID}/2025/balance_sheet/export-excel"
    )
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers.get("content-type", "")
