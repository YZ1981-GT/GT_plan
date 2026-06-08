"""data_quality_service._check_debit_credit_balance v2 目标态守护测试（真实 PG）。

Task 4.2 / 需求 6.1、6.3：确认 `_check_debit_credit_balance` 在 v2
（category_natural_positive）约定下，借方类合计 = 贷方类合计（差额 ≤ 容差）逻辑成立。

Task 4.5 / 需求 6.1、6.2、6.5、8.2：集成测试验证一套完整平衡的 v2 账套在
**分录级**（借方类合计=贷方类合计）+ **报表级**（资产合计=负债+权益合计）
两级校验下均通过；不平衡账套两级均阻断。报表级覆盖 data_quality
`_check_report_balance`（financial_report 按 row_name 匹配合计行）与
`consistency_gate.check_tb_balance`/`check_bs_balance`（trial_balance 类别汇总 +
financial_report is_total_row 合计行）两条入口。

校验口径（需求 6.1、6.2）：
- 分录级：借方类 = 资产(asset) + 费用(expense)（含成本，_infer_category 归 expense）；
  贷方类 = 负债(liability) + 权益(equity) + 收入(revenue）；差额 ≤ BALANCE_TOLERANCE（±1 元）。
- 报表级：资产合计 = 负债合计 + 所有者权益合计；差额 ≤ BALANCE_TOLERANCE。

设计原则（需求 6.3）：下游 data_quality / consistency_gate 已按类别分方向，是新约定的
**目标态**，入库层向其对齐，不反向改下游。本测试守护该目标态行为。

直接 seed v2 自然正数的 trial_balance（资产/费用借方正、负债/权益/收入贷方正）+
financial_report 合计行，不依赖入库/生成链路，专注校验平衡逻辑自身。

需真实 PG（与 test_trial_balance_sign_passthrough.py 同款 fixture），PG 不可达则 skip。

Validates: Requirements 6.1, 6.2, 6.3, 6.5, 8.2
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.report_models import FinancialReport, FinancialReportType
from app.services.consistency_gate import ConsistencyGate
from app.services.data_quality_service import DataQualityService

_TEST_PROJECT_ID = uuid.UUID("519c0de0-0000-4000-8000-00000000d401")
_TEST_YEAR = 2096
_COMPANY = "001"
_IS_PG = settings.DATABASE_URL.startswith("postgresql")


@pytest_asyncio.fixture
async def pg_factory():
    """真实 PG session factory + 测试项目 seed + 收尾清理。"""
    if not _IS_PG:
        pytest.skip("need PostgreSQL (debit/credit balance integration test)")

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")

    factory = async_sessionmaker(engine, expire_on_commit=False)

    from app.models.core import Project, ProjectStatus, ProjectType, User

    async def _cleanup():
        async with factory() as db:
            await db.execute(
                sa.delete(TrialBalance).where(TrialBalance.project_id == _TEST_PROJECT_ID)
            )
            await db.execute(
                sa.delete(FinancialReport).where(
                    FinancialReport.project_id == _TEST_PROJECT_ID
                )
            )
            await db.commit()

    await _cleanup()

    async with factory() as db:
        user = (
            await db.execute(
                sa.select(User).where(User.username == "_dq_balance_user")
            )
        ).scalar_one_or_none()
        if user:
            uid = user.id
        else:
            uid = uuid.uuid4()
            db.add(
                User(
                    id=uid,
                    username="_dq_balance_user",
                    email="dqbalance@test.com",
                    hashed_password="x",
                    role="admin",
                )
            )
            await db.flush()
        if not (
            await db.execute(
                sa.select(Project).where(Project.id == _TEST_PROJECT_ID)
            )
        ).scalar_one_or_none():
            db.add(
                Project(
                    id=_TEST_PROJECT_ID,
                    name="dq-balance-test",
                    client_name="X",
                    project_type=ProjectType.annual,
                    status=ProjectStatus.execution,
                    created_by=uid,
                )
            )
        await db.commit()

    yield factory
    await _cleanup()
    await engine.dispose()


def _tb(code: str, name: str, category: AccountCategory, amount: Decimal) -> TrialBalance:
    """构造一条 v2 自然正数的 trial_balance 行。"""
    return TrialBalance(
        project_id=_TEST_PROJECT_ID,
        year=_TEST_YEAR,
        company_code=_COMPANY,
        standard_account_code=code,
        account_name=name,
        account_category=category,
        unadjusted_amount=amount,
        audited_amount=amount,
    )


async def _seed(factory, rows: list[TrialBalance]) -> None:
    async with factory() as db:
        # 每个用例独立：先清空再 seed，避免跨用例累积
        await db.execute(
            sa.delete(TrialBalance).where(TrialBalance.project_id == _TEST_PROJECT_ID)
        )
        db.add_all(rows)
        await db.commit()


def _fr(
    row_code: str,
    row_name: str,
    amount: Decimal,
    *,
    is_total_row: bool = False,
) -> FinancialReport:
    """构造一条 balance_sheet 财务报表行（v2，金额自然正数）。"""
    return FinancialReport(
        project_id=_TEST_PROJECT_ID,
        year=_TEST_YEAR,
        report_type=FinancialReportType.balance_sheet,
        row_code=row_code,
        row_name=row_name,
        current_period_amount=amount,
        is_total_row=is_total_row,
    )


async def _seed_with_report(
    factory,
    tb_rows: list[TrialBalance],
    report_rows: list[FinancialReport],
) -> None:
    """同时 seed trial_balance + financial_report（每用例独立，先清后插）。"""
    async with factory() as db:
        await db.execute(
            sa.delete(TrialBalance).where(TrialBalance.project_id == _TEST_PROJECT_ID)
        )
        await db.execute(
            sa.delete(FinancialReport).where(
                FinancialReport.project_id == _TEST_PROJECT_ID
            )
        )
        db.add_all(tb_rows)
        db.add_all(report_rows)
        await db.commit()


@pytest.mark.asyncio
async def test_balanced_v2_passes(pg_factory):
    """v2 平衡账套：借方类合计 = 贷方类合计 → passed。

    借方类：资产 1001=12000 + 1122=50000 + 费用 6601=8000 = 70000
    贷方类：负债 2202=8000 + 权益 4001=30000 + 收入 6001=32000 = 70000
    差额 0 ≤ 容差 → passed。

    Validates: Requirements 6.1, 6.3
    """
    factory = pg_factory
    await _seed(factory, [
        _tb("1001", "库存现金", AccountCategory.asset, Decimal("12000")),
        _tb("1122", "应收账款", AccountCategory.asset, Decimal("50000")),
        _tb("6601", "管理费用", AccountCategory.expense, Decimal("8000")),
        _tb("2202", "应付账款", AccountCategory.liability, Decimal("8000")),
        _tb("4001", "实收资本", AccountCategory.equity, Decimal("30000")),
        _tb("6001", "主营业务收入", AccountCategory.revenue, Decimal("32000")),
    ])

    async with factory() as db:
        svc = DataQualityService(db)
        result = await svc._check_debit_credit_balance(_TEST_PROJECT_ID, _TEST_YEAR)

    assert result["status"] == "passed", result
    assert Decimal(result["details"]["debit_total"]) == Decimal("70000")
    assert Decimal(result["details"]["credit_total"]) == Decimal("70000")
    assert Decimal(result["details"]["difference"]) == Decimal("0")


@pytest.mark.asyncio
async def test_balanced_within_tolerance_passes(pg_factory):
    """差额在 ±1 元容差内（分/角舍入）→ 仍判 passed。

    借方类 70000.50，贷方类 70000.00，差额 0.50 ≤ 1 → passed。

    Validates: Requirements 6.1, 6.3
    """
    factory = pg_factory
    await _seed(factory, [
        _tb("1001", "库存现金", AccountCategory.asset, Decimal("70000.50")),
        _tb("2202", "应付账款", AccountCategory.liability, Decimal("70000.00")),
    ])

    async with factory() as db:
        svc = DataQualityService(db)
        result = await svc._check_debit_credit_balance(_TEST_PROJECT_ID, _TEST_YEAR)

    assert result["status"] == "passed", result
    assert Decimal(result["details"]["difference"]) == Decimal("0.50")


@pytest.mark.asyncio
async def test_unbalanced_v2_blocks(pg_factory):
    """v2 不平衡账套：借方类 ≠ 贷方类（超容差）→ blocking。

    借方类 60000，贷方类 70000，差额 10000 > 容差 → blocking。

    Validates: Requirements 6.1, 6.3
    """
    factory = pg_factory
    await _seed(factory, [
        _tb("1001", "库存现金", AccountCategory.asset, Decimal("60000")),
        _tb("2202", "应付账款", AccountCategory.liability, Decimal("70000")),
    ])

    async with factory() as db:
        svc = DataQualityService(db)
        result = await svc._check_debit_credit_balance(_TEST_PROJECT_ID, _TEST_YEAR)

    assert result["status"] == "blocking", result
    assert Decimal(result["details"]["difference"]) == Decimal("10000")


@pytest.mark.asyncio
async def test_credit_classes_summed_as_positive(pg_factory):
    """v2 关键：负债/权益/收入贷方类金额为正数时被正确归入贷方类合计（不取反）。

    确认下游不再有"贷方类取负/取绝对值"的旧约定残留——三类贷方科目各存正数，
    合计 = 三者之和（10000+20000+30000=60000），与等额借方类资产平衡。

    Validates: Requirements 6.1, 6.3
    """
    factory = pg_factory
    await _seed(factory, [
        _tb("1001", "库存现金", AccountCategory.asset, Decimal("60000")),
        _tb("2202", "应付账款", AccountCategory.liability, Decimal("10000")),
        _tb("4001", "实收资本", AccountCategory.equity, Decimal("20000")),
        _tb("6001", "主营业务收入", AccountCategory.revenue, Decimal("30000")),
    ])

    async with factory() as db:
        svc = DataQualityService(db)
        result = await svc._check_debit_credit_balance(_TEST_PROJECT_ID, _TEST_YEAR)

    assert result["status"] == "passed", result
    assert Decimal(result["details"]["credit_total"]) == Decimal("60000")
    assert Decimal(result["details"]["debit_total"]) == Decimal("60000")


@pytest.mark.asyncio
async def test_no_data_returns_warning(pg_factory):
    """无 trial_balance 数据：聚合 SUM 返回 0/0 → 差额 0 → passed（不报假阳性 blocking）。

    注：SQL 用 COALESCE(SUM(...),0)，空表也返回一行 (0,0)，故判 passed 而非 warning。

    Validates: Requirements 6.1
    """
    factory = pg_factory
    await _seed(factory, [])

    async with factory() as db:
        svc = DataQualityService(db)
        result = await svc._check_debit_credit_balance(_TEST_PROJECT_ID, _TEST_YEAR)

    assert result["status"] == "passed", result
    assert Decimal(result["details"]["difference"]) == Decimal("0")


# ---------------------------------------------------------------------------
# Task 4.5：平衡账套两级校验集成测试（分录级 + 报表级）
#
# 端到端验证"一套完整平衡的 v2 账套在分录级与报表级校验下均通过"。
# 账套设计（净利润 0，使 BS 在未结转损益下仍平衡）：
#   资产：1001 库存现金 100000 + 1122 应收账款 200000 = 300000
#   费用：6601 管理费用 40000
#   负债：2202 应付账款 120000
#   权益：4001 实收资本 180000
#   收入：6001 主营业务收入 40000
#   分录级：借方类(资产300000+费用40000)=340000 == 贷方类(负债120000+权益180000+收入40000)=340000 ✓
#   报表级：资产合计300000 == 负债和所有者权益合计(120000+180000)=300000 ✓
# ---------------------------------------------------------------------------

# 平衡账套的 trial_balance 行（复用于多个用例）
_BALANCED_TB = [
    ("1001", "库存现金", AccountCategory.asset, Decimal("100000")),
    ("1122", "应收账款", AccountCategory.asset, Decimal("200000")),
    ("6601", "管理费用", AccountCategory.expense, Decimal("40000")),
    ("2202", "应付账款", AccountCategory.liability, Decimal("120000")),
    ("4001", "实收资本", AccountCategory.equity, Decimal("180000")),
    ("6001", "主营业务收入", AccountCategory.revenue, Decimal("40000")),
]

# 平衡账套的 financial_report 合计行（资产合计 = 负债和所有者权益合计）
_BALANCED_REPORT = [
    ("BS-ASSET-TOTAL", "资产合计", Decimal("300000")),
    ("BS-LIAB-EQUITY-TOTAL", "负债和所有者权益合计", Decimal("300000")),
]


@pytest.mark.asyncio
async def test_balanced_account_passes_both_levels(pg_factory):
    """v2 平衡账套：分录级 + 报表级（data_quality）两级校验均通过。

    一次 run_checks 同时跑 debit_credit_balance（分录级）与 report_balance（报表级），
    断言二者 status 均为 passed，差额均 ≤ 容差。这是 Task 4.5 端到端核心断言。

    Validates: Requirements 6.1, 6.2, 6.5, 8.2
    """
    factory = pg_factory
    await _seed_with_report(
        factory,
        [_tb(c, n, cat, amt) for c, n, cat, amt in _BALANCED_TB],
        [_fr(rc, rn, amt, is_total_row=True) for rc, rn, amt in _BALANCED_REPORT],
    )

    async with factory() as db:
        svc = DataQualityService(db)
        report = await svc.run_checks(
            _TEST_PROJECT_ID,
            _TEST_YEAR,
            checks="debit_credit_balance,report_balance",
        )

    entry = report["results"]["debit_credit_balance"]
    rpt = report["results"]["report_balance"]

    # 分录级：借方类合计 = 贷方类合计
    assert entry["status"] == "passed", entry
    assert Decimal(entry["details"]["debit_total"]) == Decimal("340000")
    assert Decimal(entry["details"]["credit_total"]) == Decimal("340000")
    assert Decimal(entry["details"]["difference"]) <= Decimal("1")

    # 报表级：资产合计 = 负债和所有者权益合计
    assert rpt["status"] == "passed", rpt
    assert Decimal(rpt["details"]["asset_total"]) == Decimal("300000")
    assert Decimal(rpt["details"]["liability_equity_total"]) == Decimal("300000")
    assert Decimal(rpt["details"]["difference"]) <= Decimal("1")

    # 套件汇总：两项均通过，无 blocking
    assert report["summary"]["blocking"] == 0, report["summary"]


@pytest.mark.asyncio
async def test_balanced_account_passes_consistency_gate(pg_factory):
    """v2 平衡账套：consistency_gate 试算平衡 + 报表平衡两级校验均通过。

    覆盖第二条校验入口（consistency_gate）：
    - check_tb_balance：trial_balance 按类别汇总，资产 = 负债 + 权益。
    - check_bs_balance：financial_report is_total_row 合计行，资产合计 = 负债和权益合计。

    Validates: Requirements 6.1, 6.2, 6.5, 8.2
    """
    factory = pg_factory
    await _seed_with_report(
        factory,
        [_tb(c, n, cat, amt) for c, n, cat, amt in _BALANCED_TB],
        [_fr(rc, rn, amt, is_total_row=True) for rc, rn, amt in _BALANCED_REPORT],
    )

    async with factory() as db:
        gate = ConsistencyGate(db)
        tb_check = await gate.check_tb_balance(_TEST_PROJECT_ID, _TEST_YEAR)
        bs_check = await gate.check_bs_balance(_TEST_PROJECT_ID, _TEST_YEAR)

    # 试算平衡（分录/科目级）：资产300000 = 负债120000 + 权益180000
    assert tb_check.passed, tb_check.details
    # 报表平衡：资产合计300000 = 负债和所有者权益合计300000
    assert bs_check.passed, bs_check.details


@pytest.mark.asyncio
async def test_unbalanced_account_blocks_both_levels(pg_factory):
    """不平衡账套：分录级与报表级校验均阻断（超容差）。

    构造一套两级都不平衡的账套：
    - 分录级：借方类(资产300000)=300000，贷方类(负债120000+权益130000)=250000，差额50000。
    - 报表级：资产合计300000，负债和所有者权益合计250000，差额50000。
    断言 data_quality 两项均 blocking。

    Validates: Requirements 6.1, 6.2, 8.2
    """
    factory = pg_factory
    await _seed_with_report(
        factory,
        [
            _tb("1001", "库存现金", AccountCategory.asset, Decimal("100000")),
            _tb("1122", "应收账款", AccountCategory.asset, Decimal("200000")),
            _tb("2202", "应付账款", AccountCategory.liability, Decimal("120000")),
            _tb("4001", "实收资本", AccountCategory.equity, Decimal("130000")),
        ],
        [
            _fr("BS-ASSET-TOTAL", "资产合计", Decimal("300000"), is_total_row=True),
            _fr(
                "BS-LIAB-EQUITY-TOTAL",
                "负债和所有者权益合计",
                Decimal("250000"),
                is_total_row=True,
            ),
        ],
    )

    async with factory() as db:
        svc = DataQualityService(db)
        report = await svc.run_checks(
            _TEST_PROJECT_ID,
            _TEST_YEAR,
            checks="debit_credit_balance,report_balance",
        )

    entry = report["results"]["debit_credit_balance"]
    rpt = report["results"]["report_balance"]

    assert entry["status"] == "blocking", entry
    assert Decimal(entry["details"]["difference"]) == Decimal("50000")

    assert rpt["status"] == "blocking", rpt
    assert Decimal(rpt["details"]["difference"]) == Decimal("50000")

    assert report["summary"]["blocking"] == 2, report["summary"]
