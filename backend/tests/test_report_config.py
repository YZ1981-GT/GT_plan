"""报表格式配置测试 — 种子数据加载、克隆、API 路由

Validates: Requirements 1.1, 1.2, 1.5
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.report_models import FinancialReportType, ReportConfig

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
    """创建基础测试数据：用户和项目"""
    user = User(
        id=FAKE_USER_ID,
        username="test_config_user",
        email="config@example.com",
        hashed_password="hashed",
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.flush()

    project = Project(
        id=FAKE_PROJECT_ID,
        name="配置测试项目",
        client_name="配置测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.commit()
    return FAKE_PROJECT_ID


# ===== 种子数据加载测试 =====


@pytest.mark.asyncio
async def test_load_seed_data(db_session: AsyncSession):
    """加载种子数据到 report_config 表"""
    from app.services.report_config_service import ReportConfigService

    svc = ReportConfigService(db_session)
    count = await svc.load_seed_data()
    await db_session.commit()

    assert count > 0

    # 验证四种报表类型都有数据
    result = await db_session.execute(
        select(ReportConfig.report_type)
        .where(ReportConfig.is_deleted == False)  # noqa: E712
        .group_by(ReportConfig.report_type)
    )
    types = {r[0] for r in result.fetchall()}
    assert FinancialReportType.balance_sheet in types
    assert FinancialReportType.income_statement in types
    assert FinancialReportType.cash_flow_statement in types
    assert FinancialReportType.equity_statement in types


@pytest.mark.asyncio
async def test_load_seed_data_idempotent(db_session: AsyncSession):
    """重复加载种子数据不会重复插入"""
    from app.services.report_config_service import ReportConfigService

    svc = ReportConfigService(db_session)
    count1 = await svc.load_seed_data()
    await db_session.commit()

    count2 = await svc.load_seed_data()
    await db_session.commit()

    assert count1 > 0
    assert count2 == 0


@pytest.mark.asyncio
async def test_seed_balance_sheet_rows(db_session: AsyncSession):
    """资产负债表种子数据包含关键行次"""
    from app.services.report_config_service import ReportConfigService

    svc = ReportConfigService(db_session)
    await svc.load_seed_data()
    await db_session.commit()

    rows = await svc.list_configs(
        report_type=FinancialReportType.balance_sheet,
    )
    row_names = {r.row_name for r in rows}

    # 关键行次
    assert "货币资金" in row_names
    assert "应收账款" in row_names
    assert "存货" in row_names
    assert "固定资产" in row_names
    assert "流动资产合计" in row_names
    assert "非流动资产合计" in row_names
    assert "资产合计" in row_names
    assert "流动负债合计" in row_names
    assert "负债合计" in row_names
    assert "所有者权益合计" in row_names
    assert "负债和所有者权益总计" in row_names


@pytest.mark.asyncio
async def test_seed_income_statement_rows(db_session: AsyncSession):
    """利润表种子数据包含关键行次"""
    from app.services.report_config_service import ReportConfigService

    svc = ReportConfigService(db_session)
    await svc.load_seed_data()
    await db_session.commit()

    rows = await svc.list_configs(
        report_type=FinancialReportType.income_statement,
    )
    row_names = {r.row_name for r in rows}

    assert "一、营业收入" in row_names or any("营业收入" in n for n in row_names)
    assert any("营业成本" in n for n in row_names)
    assert any("营业利润" in n for n in row_names)
    assert any("利润总额" in n for n in row_names)
    assert any("净利润" in n for n in row_names)


@pytest.mark.asyncio
async def test_seed_cash_flow_rows(db_session: AsyncSession):
    """现金流量表种子数据包含三大类 + 补充资料"""
    from app.services.report_config_service import ReportConfigService

    svc = ReportConfigService(db_session)
    await svc.load_seed_data()
    await db_session.commit()

    rows = await svc.list_configs(
        report_type=FinancialReportType.cash_flow_statement,
    )
    row_names = {r.row_name for r in rows}

    assert any("经营活动" in n for n in row_names)
    assert any("投资活动" in n for n in row_names)
    assert any("筹资活动" in n for n in row_names)
    assert any("补充资料" in n for n in row_names)
    assert any("现金及现金等价物净增加额" in n for n in row_names)


@pytest.mark.asyncio
async def test_seed_equity_statement_rows(db_session: AsyncSession):
    """所有者权益变动表种子数据包含关键行次"""
    from app.services.report_config_service import ReportConfigService

    svc = ReportConfigService(db_session)
    await svc.load_seed_data()
    await db_session.commit()

    rows = await svc.list_configs(
        report_type=FinancialReportType.equity_statement,
    )
    row_names = {r.row_name for r in rows}

    assert any("实收资本" in n for n in row_names)
    assert any("资本公积" in n for n in row_names)
    assert any("盈余公积" in n for n in row_names)
    assert any("未分配利润" in n for n in row_names)
    assert any("所有者权益合计" in n for n in row_names)


# ===== 公式语法验证 =====


@pytest.mark.asyncio
async def test_formula_syntax_valid(db_session: AsyncSession):
    """验证种子数据中的公式语法正确"""
    import re
    from app.services.report_config_service import ReportConfigService

    svc = ReportConfigService(db_session)
    await svc.load_seed_data()
    await db_session.commit()

    rows = await svc.list_configs()

    # 合法的公式模式（SUM_TB 必须在 TB 之前匹配）
    sum_tb_pattern = re.compile(r"SUM_TB\('[^']+','[^']+'\)")
    tb_pattern = re.compile(r"TB\('[^']+','[^']+'\)")
    row_pattern = re.compile(r"ROW\('[^']+'\)")

    for row in rows:
        if row.formula is None:
            continue
        formula = row.formula
        # 移除所有合法 token 后应只剩空白和运算符（先匹配 SUM_TB 再匹配 TB）
        cleaned = sum_tb_pattern.sub("", formula)
        cleaned = tb_pattern.sub("", cleaned)
        cleaned = row_pattern.sub("", cleaned)
        cleaned = cleaned.replace("+", "").replace("-", "").replace("*", "").replace("/", "").strip()
        assert cleaned == "", (
            f"行 {row.row_code} 公式含非法字符: '{cleaned}' (原公式: {formula})"
        )


# ===== 克隆功能测试 =====


@pytest.mark.asyncio
async def test_clone_report_config(db_session: AsyncSession, seeded_db):
    """克隆标准配置到项目"""
    from app.services.report_config_service import ReportConfigService

    pid = seeded_db
    svc = ReportConfigService(db_session)
    await svc.load_seed_data()
    await db_session.commit()

    count = await svc.clone_report_config(pid)
    await db_session.commit()

    assert count > 0

    # 验证项目级配置存在
    project_rows = await svc.list_configs(
        applicable_standard=f"project:{pid}",
    )
    assert len(project_rows) == count


@pytest.mark.asyncio
async def test_clone_duplicate_raises(db_session: AsyncSession, seeded_db):
    """重复克隆应报错"""
    from app.services.report_config_service import ReportConfigService

    pid = seeded_db
    svc = ReportConfigService(db_session)
    await svc.load_seed_data()
    await db_session.commit()

    await svc.clone_report_config(pid)
    await db_session.commit()

    with pytest.raises(ValueError, match="已存在克隆配置"):
        await svc.clone_report_config(pid)


# ===== 修改配置测试 =====


@pytest.mark.asyncio
async def test_update_config(db_session: AsyncSession):
    """修改配置行"""
    from app.services.report_config_service import ReportConfigService

    svc = ReportConfigService(db_session)
    await svc.load_seed_data()
    await db_session.commit()

    rows = await svc.list_configs(
        report_type=FinancialReportType.balance_sheet,
    )
    first = rows[0]

    updated = await svc.update_config(first.id, {"row_name": "测试修改"})
    await db_session.commit()

    assert updated.row_name == "测试修改"


@pytest.mark.asyncio
async def test_update_nonexistent_raises(db_session: AsyncSession):
    """修改不存在的配置行应报错"""
    from app.services.report_config_service import ReportConfigService

    svc = ReportConfigService(db_session)
    with pytest.raises(ValueError, match="不存在"):
        await svc.update_config(uuid.uuid4(), {"row_name": "test"})


# ===== API 路由测试 =====


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    """创建测试 HTTP 客户端"""
    from app.core.database import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # 加载种子数据
    from app.services.report_config_service import ReportConfigService
    svc = ReportConfigService(db_session)
    await svc.load_seed_data()
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_list_configs(client: AsyncClient):
    """GET /api/report-config 返回配置列表"""
    resp = await client.get("/api/report-config")
    assert resp.status_code == 200
    data = resp.json()
    # ResponseWrapperMiddleware wraps in {"code", "data", "message"}
    items = data.get("data", data)
    assert len(items) > 0


@pytest.mark.asyncio
async def test_api_list_by_type(client: AsyncClient):
    """GET /api/report-config?report_type=balance_sheet 按类型筛选"""
    resp = await client.get(
        "/api/report-config",
        params={"report_type": "balance_sheet"},
    )
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("data", data)
    assert len(items) > 0
    for item in items:
        assert item["report_type"] == "balance_sheet"


@pytest.mark.asyncio
async def test_api_get_config_detail(client: AsyncClient):
    """GET /api/report-config/{id} 获取详情"""
    # 先获取列表
    resp = await client.get(
        "/api/report-config",
        params={"report_type": "balance_sheet"},
    )
    data = resp.json()
    items = data.get("data", data)
    config_id = items[0]["id"]

    # 获取详情
    resp2 = await client.get(f"/api/report-config/{config_id}")
    assert resp2.status_code == 200
    detail = resp2.json()
    detail_data = detail.get("data", detail)
    assert detail_data["id"] == config_id


@pytest.mark.asyncio
async def test_api_clone(client: AsyncClient):
    """POST /api/report-config/clone 克隆配置"""
    resp = await client.post(
        "/api/report-config/clone",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "applicable_standard": "enterprise",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["count"] > 0


@pytest.mark.asyncio
async def test_api_clone_duplicate(client: AsyncClient):
    """POST /api/report-config/clone 重复克隆返回 400"""
    await client.post(
        "/api/report-config/clone",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "applicable_standard": "enterprise",
        },
    )
    resp = await client.post(
        "/api/report-config/clone",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "applicable_standard": "enterprise",
        },
    )
    assert resp.status_code == 400
