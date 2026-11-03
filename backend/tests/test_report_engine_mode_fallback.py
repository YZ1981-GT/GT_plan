"""报表引擎 Tasks 1.4-1.7 测试

- Task 1.4: ReportEngine 未审/审定双模式
- Task 1.5: 公式 fallback 取数机制
- Task 1.6: 报表生成覆盖率统计
- Task 1.7: 公式调试模式

Validates: Requirements 18.1, 18.2, 18.3, 18.8, 20.1, 13.6, 18.9, 20.5, 20.6
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import (
    AccountCategory,
    TrialBalance,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import (
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


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """创建测试数据：项目 + 试算表（含未审数和审定数不同）+ 报表配置"""
    # Project
    project = Project(
        id=FAKE_PROJECT_ID,
        name="模式测试_2025",
        client_name="模式测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    # Trial balance data — 未审数和审定数不同
    tb_data = [
        # (code, name, category, audited, unadjusted, opening)
        ("1001", "库存现金", AccountCategory.asset, Decimal("50000"), Decimal("45000"), Decimal("40000")),
        ("1002", "银行存款", AccountCategory.asset, Decimal("1000000"), Decimal("900000"), Decimal("800000")),
        ("1012", "其他货币资金", AccountCategory.asset, Decimal("100000"), Decimal("90000"), Decimal("80000")),
        ("1122", "应收账款", AccountCategory.asset, Decimal("300000"), Decimal("280000"), Decimal("250000")),
        ("2001", "短期借款", AccountCategory.liability, Decimal("500000"), Decimal("500000"), Decimal("400000")),
        ("4001", "实收资本", AccountCategory.equity, Decimal("2000000"), Decimal("2000000"), Decimal("1800000")),
        # 科目有余额但公式可能算出 0（用于 fallback 测试）
        ("1101", "交易性金融资产", AccountCategory.asset, Decimal("200000"), Decimal("180000"), Decimal("150000")),
    ]
    for code, name, cat, audited, unadjusted, opening in tb_data:
        tb = TrialBalance(
            project_id=FAKE_PROJECT_ID,
            year=2025,
            company_code="default",
            standard_account_code=code,
            account_name=name,
            account_category=cat,
            audited_amount=audited,
            unadjusted_amount=unadjusted,
            opening_balance=opening,
        )
        db_session.add(tb)

    # Report config — 几行用于测试
    configs = [
        # 正常公式行
        ("BS-001", "货币资金", "TB('1001','期末余额')+TB('1002','期末余额')+TB('1012','期末余额')", 1, 0, False),
        # 引用不存在科目的公式（结果为 0，但 1101 有余额 → fallback）
        ("BS-002", "交易性金融资产", "TB('1101','期末余额')-TB('1101','期末余额')", 2, 0, False),
        # 合计行
        ("BS-003", "流动资产合计", "ROW('BS-001')+ROW('BS-002')", 3, 0, True),
        # 无公式行
        ("BS-004", "长期股权投资", None, 4, 1, False),
        # 应收账款
        ("BS-005", "应收账款", "TB('1122','期末余额')", 5, 0, False),
        # 故意写错的公式（测试容错）
        ("BS-006", "错误公式行", "INVALID_FUNC('xxx')", 6, 0, False),
    ]
    for row_code, row_name, formula, row_num, indent, is_total in configs:
        rc = ReportConfig(
            applicable_standard="soe_standalone",
            report_type=FinancialReportType.balance_sheet,
            row_code=row_code,
            row_name=row_name,
            formula=formula,
            row_number=row_num,
            indent_level=indent,
            is_total_row=is_total,
        )
        db_session.add(rc)

    await db_session.flush()
    return db_session


# ===========================================================================
# Task 1.4: 未审/审定双模式测试
# ===========================================================================


class TestReportModeSelection:
    """Task 1.4: ReportEngine 未审/审定双模式实现"""

    @pytest.mark.asyncio
    async def test_audited_mode_uses_audited_amount(self, seeded_db: AsyncSession):
        """审定模式使用 trial_balance.audited_amount"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
            mode="audited",
        )
        bs_rows = result.get("balance_sheet", [])
        # 货币资金 = 50000 + 1000000 + 100000 = 1150000 (audited)
        cash_row = next((r for r in bs_rows if r["row_code"] == "BS-001"), None)
        assert cash_row is not None
        assert Decimal(cash_row["current_period_amount"]) == Decimal("1150000")

    @pytest.mark.asyncio
    async def test_unadjusted_mode_uses_unadjusted_amount(self, seeded_db: AsyncSession):
        """未审模式使用 trial_balance.unadjusted_amount"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
            mode="unadjusted",
        )
        bs_rows = result.get("balance_sheet", [])
        # 货币资金 = 45000 + 900000 + 90000 = 1035000 (unadjusted)
        cash_row = next((r for r in bs_rows if r["row_code"] == "BS-001"), None)
        assert cash_row is not None
        assert Decimal(cash_row["current_period_amount"]) == Decimal("1035000")

    @pytest.mark.asyncio
    async def test_default_mode_is_audited(self, seeded_db: AsyncSession):
        """默认模式为 audited"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
        )
        bs_rows = result.get("balance_sheet", [])
        cash_row = next((r for r in bs_rows if r["row_code"] == "BS-001"), None)
        assert cash_row is not None
        # 默认应该用 audited_amount
        assert Decimal(cash_row["current_period_amount"]) == Decimal("1150000")

    @pytest.mark.asyncio
    async def test_mode_affects_all_rows(self, seeded_db: AsyncSession):
        """模式影响所有使用 TB 取数的行"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
            mode="unadjusted",
        )
        bs_rows = result.get("balance_sheet", [])
        # 应收账款 = 280000 (unadjusted)
        ar_row = next((r for r in bs_rows if r["row_code"] == "BS-005"), None)
        assert ar_row is not None
        assert Decimal(ar_row["current_period_amount"]) == Decimal("280000")


# ===========================================================================
# Task 1.5: 公式 fallback 取数机制
# ===========================================================================


class TestFormulaFallback:
    """Task 1.5 原「公式 fallback 取数」：spec formula-hub-integrity-closure（F10、需求 5，变异 #19）起取消。

    原实现在公式结果为 0 而试算表科目有余额时把首个科目余额换进去 ⇒ 合法的 0（如 BS-002 = 1101 − 1101）被写成
    200000。现行：按公式结果 0 写入、不替换，另出一条行告警请人核对公式。原三条断言钉的正是被修掉的替换行为。
    """

    @pytest.mark.asyncio
    async def test_zero_result_is_not_replaced_by_tb_balance(self, seeded_db: AsyncSession):
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
            mode="audited",
        )
        fa_row = next((r for r in result.get("balance_sheet", []) if r["row_code"] == "BS-002"), None)
        assert fa_row is not None
        assert Decimal(fa_row["current_period_amount"]) == Decimal("0")
        assert "fallback_applied" not in fa_row

    @pytest.mark.asyncio
    async def test_nonzero_result_has_no_balance_hint(self, seeded_db: AsyncSession):
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
            mode="audited",
        )
        cash_row = next((r for r in result.get("balance_sheet", []) if r["row_code"] == "BS-001"), None)
        assert cash_row is not None
        assert Decimal(cash_row["current_period_amount"]) == Decimal("1150000")
        warnings = result.get("coverage_stats", {}).get("by_type", {}).get("balance_sheet", {}).get("warnings", [])
        assert not [w for w in warnings if w["row_code"] == "BS-001" and "本级有余额" in w["message"]]

    @pytest.mark.asyncio
    async def test_zero_with_balance_marked_in_coverage_warnings(self, seeded_db: AsyncSession):
        """结果为 0 而科目有余额：在 coverage_stats 里给行告警（不替换值）。"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
            mode="audited",
        )
        warnings = result.get("coverage_stats", {}).get("by_type", {}).get("balance_sheet", {}).get("warnings", [])
        hints = [w for w in warnings if w["row_code"] == "BS-002" and w["type"] == "formula_warning"]
        assert len(hints) == 1, warnings
        assert "1101" in hints[0]["message"] and "不替换" in hints[0]["message"]


# ===========================================================================
# Task 1.6: 报表生成覆盖率统计
# ===========================================================================


class TestCoverageStats:
    """Task 1.6: 报表生成覆盖率统计"""

    @pytest.mark.asyncio
    async def test_coverage_stats_present_in_result(self, seeded_db: AsyncSession):
        """generate_all_reports 返回值包含 coverage_stats"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
        )
        assert "coverage_stats" in result
        stats = result["coverage_stats"]
        assert "by_type" in stats
        assert "total_rows" in stats
        assert "rows_with_data" in stats
        assert "coverage_pct" in stats

    @pytest.mark.asyncio
    async def test_coverage_stats_per_report_type(self, seeded_db: AsyncSession):
        """覆盖率按报表类型分别统计"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
        )
        by_type = result["coverage_stats"]["by_type"]
        assert "balance_sheet" in by_type
        bs_stats = by_type["balance_sheet"]
        assert "total_rows" in bs_stats
        assert "rows_with_data" in bs_stats
        assert "coverage_pct" in bs_stats
        # 我们有 6 行配置
        assert bs_stats["total_rows"] == 6

    @pytest.mark.asyncio
    async def test_coverage_pct_calculation(self, seeded_db: AsyncSession):
        """覆盖率百分比计算正确"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
        )
        stats = result["coverage_stats"]
        # coverage_pct = rows_with_data / total_rows * 100
        expected_pct = round(stats["rows_with_data"] / max(stats["total_rows"], 1) * 100, 1)
        assert stats["coverage_pct"] == expected_pct

    @pytest.mark.asyncio
    async def test_rows_with_data_counts_nonzero_and_formula_rows(self, seeded_db: AsyncSession):
        """有数据行数统计：current_period_amount != 0 或有公式的行"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
        )
        bs_stats = result["coverage_stats"]["by_type"]["balance_sheet"]
        # BS-001: 1150000 (有数据) ✓
        # BS-002: 200000 (fallback, 有数据) ✓
        # BS-003: 1350000 (合计, 有数据) ✓
        # BS-004: 无公式, 0 (无数据) ✗
        # BS-005: 300000 (有数据) ✓
        # BS-006: 错误公式, 0 但有公式 ✓
        assert bs_stats["rows_with_data"] >= 4


# ===========================================================================
# Task 1.7: 公式调试模式
# ===========================================================================


class TestDebugMode:
    """Task 1.7: 公式调试模式"""

    @pytest.mark.asyncio
    async def test_debug_false_no_debug_info(self, seeded_db: AsyncSession):
        """debug=False 时不返回 debug_info"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
            debug=False,
        )
        assert "debug_info" not in result

    @pytest.mark.asyncio
    async def test_debug_true_returns_debug_info(self, seeded_db: AsyncSession):
        """debug=True 时返回 debug_info"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
            debug=True,
        )
        assert "debug_info" in result
        debug_info = result["debug_info"]
        assert "balance_sheet" in debug_info

    @pytest.mark.asyncio
    async def test_debug_info_contains_formula_and_trace(self, seeded_db: AsyncSession):
        """调试信息包含公式文本、代入值、计算结果"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
            debug=True,
        )
        debug_rows = result["debug_info"]["balance_sheet"]
        # 找到 BS-001 的调试信息
        bs001_debug = next((d for d in debug_rows if d["row_code"] == "BS-001"), None)
        assert bs001_debug is not None
        assert bs001_debug["formula"] == "TB('1001','期末余额')+TB('1002','期末余额')+TB('1012','期末余额')"
        assert Decimal(bs001_debug["result"]) == Decimal("1150000")
        assert bs001_debug["substituted_expression"] is not None
        # 代入值应包含实际数字
        assert "50000" in bs001_debug["substituted_expression"]
        assert "1000000" in bs001_debug["substituted_expression"]

    @pytest.mark.asyncio
    async def test_debug_info_shows_zero_balance_hint(self, seeded_db: AsyncSession):
        """调试信息带「结果为 0 而科目有余额」告警（原 fallback_applied 标记随替换行为一并取消）"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
            debug=True,
        )
        debug_rows = result["debug_info"]["balance_sheet"]
        bs002_debug = next((d for d in debug_rows if d["row_code"] == "BS-002"), None)
        assert bs002_debug is not None
        assert "fallback_applied" not in bs002_debug
        assert bs002_debug["result"] == "0.00" or Decimal(bs002_debug["result"]) == 0
        assert any("本级有余额" in w for w in bs002_debug["warnings"]), bs002_debug["warnings"]

    @pytest.mark.asyncio
    async def test_formula_error_not_written_as_zero(self, seeded_db: AsyncSession):
        """公式执行失败：不抛异常、不写 0（新行金额为 NULL），失败原因进 failed_rows（spec formula-hub-integrity-closure
        F10 / 需求 5：原实现报错按 0 写入）"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
            debug=True,
        )
        error_row = next((r for r in result.get("balance_sheet", []) if r["row_code"] == "BS-006"), None)
        assert error_row is not None
        assert error_row["current_period_amount"] is None

    @pytest.mark.asyncio
    async def test_debug_info_error_field(self, seeded_db: AsyncSession):
        """调试信息中错误公式有 error 字段、result 为空（不以 0 冒充）"""
        engine = ReportEngine(seeded_db)
        result = await engine.generate_all_reports(
            FAKE_PROJECT_ID, 2025,
            applicable_standard="soe_standalone",
            debug=True,
        )
        debug_rows = result["debug_info"]["balance_sheet"]
        bs006_debug = next((d for d in debug_rows if d["row_code"] == "BS-006"), None)
        assert bs006_debug is not None
        assert bs006_debug["result"] is None
        assert bs006_debug["error"] and "INVALID_FUNC" in bs006_debug["error"], bs006_debug["error"]
