"""现金流量表工作底稿引擎测试

Validates: Requirements 3.1-3.12
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import (
    CashFlowCategory,
    CfsAdjustment,
    FinancialReport,
    FinancialReportType,
    ReportConfig,
)
from app.services.cfs_worksheet_engine import CFSWorksheetEngine
from app.services.report_config_service import ReportConfigService
from app.services.report_engine import ReportEngine

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
    """创建完整测试数据：项目 + 试算表 + 报表配置 + 生成报表"""
    # Project
    project = Project(
        id=FAKE_PROJECT_ID,
        name="CFS测试_2025",
        client_name="CFS测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    # Trial balance data
    tb_data = [
        # 现金类
        ("1001", "库存现金", AccountCategory.asset, Decimal("50000"), Decimal("40000")),
        ("1002", "银行存款", AccountCategory.asset, Decimal("1000000"), Decimal("800000")),
        ("1012", "其他货币资金", AccountCategory.asset, Decimal("100000"), Decimal("80000")),
        # 资产类
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
        ("4104", "未分配利润", AccountCategory.equity, Decimal("800000"), Decimal("500000")),
        # 收入/费用类
        ("6001", "主营业务收入", AccountCategory.revenue, Decimal("3000000"), Decimal("0")),
        ("6401", "主营业务成本", AccountCategory.expense, Decimal("2000000"), Decimal("0")),
        ("6403", "税金及附加", AccountCategory.expense, Decimal("50000"), Decimal("0")),
        ("6601", "销售费用", AccountCategory.expense, Decimal("100000"), Decimal("0")),
        ("6602", "管理费用", AccountCategory.expense, Decimal("200000"), Decimal("0")),
        ("6603", "财务费用", AccountCategory.expense, Decimal("30000"), Decimal("0")),
        ("6604", "研发费用", AccountCategory.expense, Decimal("50000"), Decimal("0")),
        ("6111", "投资收益", AccountCategory.revenue, Decimal("20000"), Decimal("0")),
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

    # Load seed report configs and generate reports (needed for indirect method)
    svc = ReportConfigService(db_session)
    await svc.load_seed_data()
    await db_session.flush()

    report_engine = ReportEngine(db_session)
    await report_engine.generate_all_reports(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    return FAKE_PROJECT_ID


# ===== 8.1 generate_worksheet 测试 =====


@pytest.mark.asyncio
async def test_generate_worksheet(db_session: AsyncSession, seeded_db):
    """工作底稿生成：包含所有科目的期初期末余额和变动额"""
    engine = CFSWorksheetEngine(db_session)
    result = await engine.generate_worksheet(FAKE_PROJECT_ID, 2025)

    assert result["project_id"] == str(FAKE_PROJECT_ID)
    assert result["year"] == 2025
    assert len(result["rows"]) > 0

    # Check a specific account
    cash_row = next(r for r in result["rows"] if r["account_code"] == "1001")
    assert Decimal(cash_row["opening_balance"]) == Decimal("40000")
    assert Decimal(cash_row["closing_balance"]) == Decimal("50000")
    assert Decimal(cash_row["period_change"]) == Decimal("10000")


@pytest.mark.asyncio
async def test_worksheet_period_change_calculation(db_session: AsyncSession, seeded_db):
    """变动额 = 期末 - 期初"""
    engine = CFSWorksheetEngine(db_session)
    result = await engine.generate_worksheet(FAKE_PROJECT_ID, 2025)

    for row in result["rows"]:
        opening = Decimal(row["opening_balance"])
        closing = Decimal(row["closing_balance"])
        change = Decimal(row["period_change"])
        assert change == closing - opening, f"Account {row['account_code']}: {change} != {closing} - {opening}"


# ===== 8.2 auto_generate_adjustments 测试 =====


@pytest.mark.asyncio
async def test_auto_generate_adjustments(db_session: AsyncSession, seeded_db):
    """自动生成常见调整项"""
    engine = CFSWorksheetEngine(db_session)
    created = await engine.auto_generate_adjustments(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    assert len(created) > 0

    # Should include depreciation (1602 change = 500000 - 400000 = 100000)
    depreciation = next(
        (a for a in created if a["description"] == "固定资产折旧"), None
    )
    assert depreciation is not None
    assert Decimal(depreciation["amount"]) == Decimal("100000")

    # Should include amortization (1702 change = 100000 - 80000 = 20000)
    amortization = next(
        (a for a in created if a["description"] == "无形资产摊销"), None
    )
    assert amortization is not None
    assert Decimal(amortization["amount"]) == Decimal("20000")


@pytest.mark.asyncio
async def test_auto_generate_idempotent(db_session: AsyncSession, seeded_db):
    """重复自动生成不会创建重复分录"""
    engine = CFSWorksheetEngine(db_session)
    created1 = await engine.auto_generate_adjustments(FAKE_PROJECT_ID, 2025)
    await db_session.flush()

    created2 = await engine.auto_generate_adjustments(FAKE_PROJECT_ID, 2025)
    await db_session.flush()

    # Second run should produce same count (old ones soft-deleted)
    assert len(created1) == len(created2)

    # Only the second batch should be active
    adjustments = await engine.list_adjustments(FAKE_PROJECT_ID, 2025)
    auto_count = sum(1 for a in adjustments if a.is_auto_generated)
    assert auto_count == len(created2)


# ===== 8.3 CFS Adjustment CRUD 测试 =====


@pytest.mark.asyncio
async def test_create_adjustment(db_session: AsyncSession, seeded_db):
    """创建 CFS 调整分录"""
    engine = CFSWorksheetEngine(db_session)
    adj = await engine.create_adjustment(
        project_id=FAKE_PROJECT_ID,
        year=2025,
        description="测试调整",
        debit_account="CF-002",
        credit_account="1122",
        amount=Decimal("50000"),
        cash_flow_category=CashFlowCategory.operating,
        cash_flow_line_item="销售商品、提供劳务收到的现金",
    )
    await db_session.commit()

    assert adj.id is not None
    assert adj.adjustment_no.startswith("CFS-")
    assert adj.amount == Decimal("50000")
    assert adj.cash_flow_category == CashFlowCategory.operating


@pytest.mark.asyncio
async def test_create_adjustment_negative_amount(db_session: AsyncSession, seeded_db):
    """金额必须大于零"""
    engine = CFSWorksheetEngine(db_session)
    with pytest.raises(ValueError, match="调整金额必须大于零"):
        await engine.create_adjustment(
            project_id=FAKE_PROJECT_ID,
            year=2025,
            description="负数测试",
            debit_account="CF-002",
            credit_account="1122",
            amount=Decimal("-100"),
        )


@pytest.mark.asyncio
async def test_update_adjustment(db_session: AsyncSession, seeded_db):
    """修改 CFS 调整分录"""
    engine = CFSWorksheetEngine(db_session)
    adj = await engine.create_adjustment(
        project_id=FAKE_PROJECT_ID,
        year=2025,
        description="原始描述",
        debit_account="CF-002",
        credit_account="1122",
        amount=Decimal("50000"),
    )
    await db_session.flush()

    updated = await engine.update_adjustment(
        adj.id,
        description="修改后描述",
        amount=Decimal("60000"),
    )
    assert updated.description == "修改后描述"
    assert updated.amount == Decimal("60000")


@pytest.mark.asyncio
async def test_delete_adjustment(db_session: AsyncSession, seeded_db):
    """软删除 CFS 调整分录"""
    engine = CFSWorksheetEngine(db_session)
    adj = await engine.create_adjustment(
        project_id=FAKE_PROJECT_ID,
        year=2025,
        description="待删除",
        debit_account="CF-002",
        credit_account="1122",
        amount=Decimal("50000"),
    )
    await db_session.flush()

    deleted = await engine.delete_adjustment(adj.id)
    assert deleted is True

    # Should not appear in list
    adjustments = await engine.list_adjustments(FAKE_PROJECT_ID, 2025)
    assert all(a.id != adj.id for a in adjustments)


@pytest.mark.asyncio
async def test_delete_nonexistent(db_session: AsyncSession, seeded_db):
    """删除不存在的分录返回 False"""
    engine = CFSWorksheetEngine(db_session)
    deleted = await engine.delete_adjustment(uuid.uuid4())
    assert deleted is False


@pytest.mark.asyncio
async def test_list_adjustments(db_session: AsyncSession, seeded_db):
    """列出所有调整分录"""
    engine = CFSWorksheetEngine(db_session)
    await engine.create_adjustment(
        project_id=FAKE_PROJECT_ID, year=2025,
        description="A", debit_account="CF-002", credit_account="1122",
        amount=Decimal("10000"),
    )
    await engine.create_adjustment(
        project_id=FAKE_PROJECT_ID, year=2025,
        description="B", debit_account="CF-006", credit_account="2202",
        amount=Decimal("20000"),
    )
    await db_session.flush()

    adjustments = await engine.list_adjustments(FAKE_PROJECT_ID, 2025)
    assert len(adjustments) == 2


# ===== 8.4 get_reconciliation_status 测试 =====


@pytest.mark.asyncio
async def test_reconciliation_no_adjustments(db_session: AsyncSession, seeded_db):
    """无调整分录时，有变动的科目未分配"""
    engine = CFSWorksheetEngine(db_session)
    result = await engine.get_reconciliation_status(FAKE_PROJECT_ID, 2025)

    assert result["all_balanced"] is False
    assert len(result["rows"]) > 0

    # 1001 has change 10000, no allocation
    cash_row = next(r for r in result["rows"] if r["account_code"] == "1001")
    assert Decimal(cash_row["period_change"]) == Decimal("10000")
    assert Decimal(cash_row["allocated_total"]) == Decimal("0")
    assert Decimal(cash_row["unallocated"]) == Decimal("10000")


@pytest.mark.asyncio
async def test_reconciliation_with_adjustments(db_session: AsyncSession, seeded_db):
    """有调整分录时，已分配额正确计算"""
    engine = CFSWorksheetEngine(db_session)
    await engine.create_adjustment(
        project_id=FAKE_PROJECT_ID, year=2025,
        description="应收账款收回",
        debit_account="CF-002",
        credit_account="1122",
        amount=Decimal("50000"),
        cash_flow_category=CashFlowCategory.operating,
    )
    await db_session.flush()

    result = await engine.get_reconciliation_status(FAKE_PROJECT_ID, 2025)

    # 1122 has change = 300000 - 250000 = 50000, allocated = 50000
    ar_row = next(r for r in result["rows"] if r["account_code"] == "1122")
    assert Decimal(ar_row["period_change"]) == Decimal("50000")
    assert Decimal(ar_row["allocated_total"]) == Decimal("50000")
    assert Decimal(ar_row["unallocated"]) == Decimal("0")


# ===== 8.5 generate_cfs_main_table 测试 =====


@pytest.mark.asyncio
async def test_cfs_main_table(db_session: AsyncSession, seeded_db):
    """现金流量表主表按类别汇总"""
    engine = CFSWorksheetEngine(db_session)
    await engine.create_adjustment(
        project_id=FAKE_PROJECT_ID, year=2025,
        description="销售收款",
        debit_account="CF-002",
        credit_account="1122",
        amount=Decimal("50000"),
        cash_flow_category=CashFlowCategory.operating,
        cash_flow_line_item="销售商品、提供劳务收到的现金",
    )
    await engine.create_adjustment(
        project_id=FAKE_PROJECT_ID, year=2025,
        description="购买设备",
        debit_account="1601",
        credit_account="CF-025",
        amount=Decimal("200000"),
        cash_flow_category=CashFlowCategory.investing,
        cash_flow_line_item="购建固定资产等支付的现金",
    )
    await db_session.flush()

    result = await engine.generate_cfs_main_table(FAKE_PROJECT_ID, 2025)

    assert "operating" in result["categories"]
    assert "investing" in result["categories"]
    assert Decimal(result["category_totals"]["operating"]) == Decimal("50000")
    assert Decimal(result["category_totals"]["investing"]) == Decimal("200000")


# ===== 8.6 generate_indirect_method 测试 =====


@pytest.mark.asyncio
async def test_indirect_method(db_session: AsyncSession, seeded_db):
    """间接法补充资料生成"""
    engine = CFSWorksheetEngine(db_session)
    result = await engine.generate_indirect_method(FAKE_PROJECT_ID, 2025)

    assert result["project_id"] == str(FAKE_PROJECT_ID)
    assert len(result["items"]) > 0

    # Net profit should be from IS-019
    net_profit_item = next(i for i in result["items"] if i["code"] == "CF-S03")
    assert Decimal(net_profit_item["amount"]) != Decimal("0")

    # Depreciation = 1602 change = 500000 - 400000 = 100000
    depreciation_item = next(i for i in result["items"] if i["code"] == "CF-S05")
    assert Decimal(depreciation_item["amount"]) == Decimal("100000")

    # Amortization = 1702 change = 100000 - 80000 = 20000
    amortization_item = next(i for i in result["items"] if i["code"] == "CF-S06")
    assert Decimal(amortization_item["amount"]) == Decimal("20000")


@pytest.mark.asyncio
async def test_indirect_method_working_capital(db_session: AsyncSession, seeded_db):
    """间接法营运资本变动计算"""
    engine = CFSWorksheetEngine(db_session)
    result = await engine.generate_indirect_method(FAKE_PROJECT_ID, 2025)

    # Inventory decrease = -(500000 - 400000) = -100000
    inventory_item = next(i for i in result["items"] if i["code"] == "CF-S12")
    assert Decimal(inventory_item["amount"]) == Decimal("-100000")

    # Operating receivables decrease = -(change in 1121+1122+1123+1221)
    # = -((50000-30000)+(300000-250000)+(80000-60000)+(40000-35000))
    # = -(20000+50000+20000+5000) = -95000
    receivables_item = next(i for i in result["items"] if i["code"] == "CF-S13")
    assert Decimal(receivables_item["amount"]) == Decimal("-95000")

    # Operating payables increase = change in 2201+2202+2203+2211+2221+2241
    # = (100000-80000)+(200000-150000)+(50000-40000)+(80000-60000)+(30000-25000)+(40000-30000)
    # = 20000+50000+10000+20000+5000+10000 = 115000
    payables_item = next(i for i in result["items"] if i["code"] == "CF-S14")
    assert Decimal(payables_item["amount"]) == Decimal("115000")


# ===== 8.7 verify_reconciliation 测试 =====


@pytest.mark.asyncio
async def test_verify_reconciliation(db_session: AsyncSession, seeded_db):
    """勾稽校验返回检查结果"""
    engine = CFSWorksheetEngine(db_session)
    result = await engine.verify_reconciliation(FAKE_PROJECT_ID, 2025)

    assert len(result["checks"]) == 2
    assert "间接法" in result["checks"][0]["check_name"]
    assert "现金净增加额" in result["checks"][1]["check_name"]


@pytest.mark.asyncio
async def test_cash_reconciliation_values(db_session: AsyncSession, seeded_db):
    """现金勾稽：期末现金-期初现金"""
    engine = CFSWorksheetEngine(db_session)
    result = await engine.verify_reconciliation(FAKE_PROJECT_ID, 2025)

    cash_check = result["checks"][1]
    # Opening cash = 40000 + 800000 + 80000 = 920000
    assert Decimal(cash_check["opening_cash"]) == Decimal("920000")
    # Closing cash = 50000 + 1000000 + 100000 = 1150000
    assert Decimal(cash_check["closing_cash"]) == Decimal("1150000")
    # Expected increase = 1150000 - 920000 = 230000
    assert Decimal(cash_check["expected_increase"]) == Decimal("230000")


# ===== 8.8 API 路由测试 =====


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    """创建测试 HTTP 客户端"""
    from app.core.database import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_generate_worksheet(client: AsyncClient):
    """POST /api/cfs-worksheet/generate"""
    resp = await client.post(
        "/api/cfs-worksheet/generate",
        json={"project_id": str(FAKE_PROJECT_ID), "year": 2025},
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert "rows" in result
    assert len(result["rows"]) > 0


@pytest.mark.asyncio
async def test_api_get_worksheet(client: AsyncClient):
    """GET /api/cfs-worksheet/{project_id}/{year}"""
    resp = await client.get(
        f"/api/cfs-worksheet/{FAKE_PROJECT_ID}/2025"
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert "rows" in result


@pytest.mark.asyncio
async def test_api_create_adjustment(client: AsyncClient):
    """POST /api/cfs-worksheet/adjustments"""
    resp = await client.post(
        f"/api/cfs-worksheet/adjustments?project_id={FAKE_PROJECT_ID}",
        json={
            "year": 2025,
            "description": "API测试调整",
            "debit_account": "CF-002",
            "credit_account": "1122",
            "amount": "50000",
            "cash_flow_category": "operating",
            "cash_flow_line_item": "销售商品、提供劳务收到的现金",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["amount"] == "50000" or float(result["amount"]) == 50000


@pytest.mark.asyncio
async def test_api_auto_generate(client: AsyncClient):
    """POST /api/cfs-worksheet/auto-generate"""
    resp = await client.post(
        "/api/cfs-worksheet/auto-generate",
        json={"project_id": str(FAKE_PROJECT_ID), "year": 2025},
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert "adjustments" in result
    assert len(result["adjustments"]) > 0


@pytest.mark.asyncio
async def test_api_reconciliation(client: AsyncClient):
    """GET /api/cfs-worksheet/{project_id}/{year}/reconciliation"""
    resp = await client.get(
        f"/api/cfs-worksheet/{FAKE_PROJECT_ID}/2025/reconciliation"
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert "rows" in result
    assert "all_balanced" in result


@pytest.mark.asyncio
async def test_api_indirect_method(client: AsyncClient):
    """GET /api/cfs-worksheet/{project_id}/{year}/indirect-method"""
    resp = await client.get(
        f"/api/cfs-worksheet/{FAKE_PROJECT_ID}/2025/indirect-method"
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert "items" in result
    assert "operating_cash_flow_indirect" in result


@pytest.mark.asyncio
async def test_api_verify(client: AsyncClient):
    """GET /api/cfs-worksheet/{project_id}/{year}/verify"""
    resp = await client.get(
        f"/api/cfs-worksheet/{FAKE_PROJECT_ID}/2025/verify"
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert "checks" in result
    assert len(result["checks"]) == 2


@pytest.mark.asyncio
async def test_api_main_table(client: AsyncClient):
    """GET /api/cfs-worksheet/{project_id}/{year}/main-table"""
    resp = await client.get(
        f"/api/cfs-worksheet/{FAKE_PROJECT_ID}/2025/main-table"
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert "categories" in result


@pytest.mark.asyncio
async def test_api_list_adjustments(client: AsyncClient):
    """GET /api/cfs-worksheet/{project_id}/{year}/adjustments"""
    # Create one first
    await client.post(
        f"/api/cfs-worksheet/adjustments?project_id={FAKE_PROJECT_ID}",
        json={
            "year": 2025,
            "description": "列表测试",
            "debit_account": "CF-002",
            "credit_account": "1122",
            "amount": "10000",
        },
    )

    resp = await client.get(
        f"/api/cfs-worksheet/{FAKE_PROJECT_ID}/2025/adjustments"
    )
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("data", data)
    assert isinstance(items, list)
    assert len(items) >= 1
