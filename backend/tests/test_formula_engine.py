"""取数公式引擎测试

Validates: Requirements 2.1-2.10
"""

import uuid
from decimal import Decimal

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import (
    AccountCategory,
    TbAuxBalance,
    TrialBalance,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.formula_engine import (
    AUXExecutor,
    FormulaEngine,
    FormulaError,
    PREVExecutor,
    SumTBExecutor,
    TBExecutor,
    WPExecutor,
)

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
    """Create test data: project + trial_balance + tb_aux_balance"""
    project = Project(
        id=FAKE_PROJECT_ID,
        name="公式引擎测试_2025",
        client_name="公式引擎测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    # Trial balance data
    tb_data = [
        ("1001", "库存现金", AccountCategory.asset, Decimal("50000"), Decimal("40000"),
         Decimal("0"), Decimal("0")),
        ("1002", "银行存款", AccountCategory.asset, Decimal("1000000"), Decimal("800000"),
         Decimal("5000"), Decimal("3000")),
        ("1003", "其他货币资金", AccountCategory.asset, Decimal("100000"), Decimal("80000"),
         Decimal("0"), Decimal("0")),
        ("6001", "主营业务收入", AccountCategory.revenue, Decimal("3000000"), Decimal("0"),
         Decimal("0"), Decimal("0")),
        ("6002", "其他业务收入", AccountCategory.revenue, Decimal("200000"), Decimal("0"),
         Decimal("0"), Decimal("0")),
    ]

    for code, name, cat, audited, opening, rje, aje in tb_data:
        db_session.add(TrialBalance(
            project_id=FAKE_PROJECT_ID,
            year=2025,
            company_code="001",
            standard_account_code=code,
            account_name=name,
            account_category=cat,
            unadjusted_amount=audited - rje - aje,
            audited_amount=audited,
            opening_balance=opening,
            rje_adjustment=rje,
            aje_adjustment=aje,
        ))

    # Prior year data for PREV testing
    db_session.add(TrialBalance(
        project_id=FAKE_PROJECT_ID,
        year=2024,
        company_code="001",
        standard_account_code="1001",
        account_name="库存现金",
        account_category=AccountCategory.asset,
        unadjusted_amount=Decimal("40000"),
        audited_amount=Decimal("40000"),
        opening_balance=Decimal("30000"),
        rje_adjustment=Decimal("0"),
        aje_adjustment=Decimal("0"),
    ))

    # Aux balance data
    db_session.add(TbAuxBalance(
        project_id=FAKE_PROJECT_ID,
        year=2025,
        company_code="001",
        account_code="1122",
        aux_type="客户",
        aux_code="C001",
        aux_name="客户A",
        opening_balance=Decimal("100000"),
        debit_amount=Decimal("50000"),
        credit_amount=Decimal("30000"),
        closing_balance=Decimal("120000"),
    ))

    await db_session.commit()
    return FAKE_PROJECT_ID


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# ===== TBExecutor Tests =====


@pytest.mark.asyncio
async def test_tb_executor_audited_amount(db_session, seeded_db):
    """TB() 取期末余额"""
    executor = TBExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"account_code": "1001", "column_name": "期末余额"},
    )
    assert result == Decimal("50000")


@pytest.mark.asyncio
async def test_tb_executor_opening_balance(db_session, seeded_db):
    """TB() 取年初余额"""
    executor = TBExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"account_code": "1001", "column_name": "年初余额"},
    )
    assert result == Decimal("40000")


@pytest.mark.asyncio
async def test_tb_executor_rje_adjustment(db_session, seeded_db):
    """TB() 取RJE调整"""
    executor = TBExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"account_code": "1002", "column_name": "RJE调整"},
    )
    assert result == Decimal("5000")


@pytest.mark.asyncio
async def test_tb_executor_aje_adjustment(db_session, seeded_db):
    """TB() 取AJE调整"""
    executor = TBExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"account_code": "1002", "column_name": "AJE调整"},
    )
    assert result == Decimal("3000")


@pytest.mark.asyncio
async def test_tb_executor_unadjusted(db_session, seeded_db):
    """TB() 取未审数"""
    executor = TBExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"account_code": "1002", "column_name": "未审数"},
    )
    # unadjusted = audited - rje - aje = 1000000 - 5000 - 3000 = 992000
    assert result == Decimal("992000")


@pytest.mark.asyncio
async def test_tb_executor_missing_account(db_session, seeded_db):
    """TB() 科目不存在返回 FormulaError"""
    executor = TBExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"account_code": "9999", "column_name": "期末余额"},
    )
    assert isinstance(result, FormulaError)
    assert "9999" in result.message


@pytest.mark.asyncio
async def test_tb_executor_invalid_column(db_session, seeded_db):
    """TB() 无效列名返回 FormulaError"""
    executor = TBExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"account_code": "1001", "column_name": "无效列"},
    )
    assert isinstance(result, FormulaError)
    assert "无效列" in result.message


# ===== WPExecutor Tests =====


@pytest.mark.asyncio
async def test_wp_executor_stub(db_session, seeded_db):
    """WP() MVP stub 返回 FormulaError"""
    executor = WPExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"wp_code": "E1-1", "cell_ref": "B5"},
    )
    assert isinstance(result, FormulaError)
    assert "暂不支持" in result.message


@pytest.mark.asyncio
async def test_wp_executor_missing_params(db_session, seeded_db):
    """WP() 缺少参数返回 FormulaError"""
    executor = WPExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"wp_code": "", "cell_ref": ""},
    )
    assert isinstance(result, FormulaError)


# ===== AUXExecutor Tests =====


@pytest.mark.asyncio
async def test_aux_executor_closing_balance(db_session, seeded_db):
    """AUX() 取辅助余额期末余额"""
    executor = AUXExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {
            "account_code": "1122",
            "aux_type": "客户",
            "aux_name": "客户A",
            "column_name": "期末余额",
        },
    )
    assert result == Decimal("120000")


@pytest.mark.asyncio
async def test_aux_executor_opening_balance(db_session, seeded_db):
    """AUX() 取辅助余额期初余额"""
    executor = AUXExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {
            "account_code": "1122",
            "aux_type": "客户",
            "aux_name": "客户A",
            "column_name": "期初余额",
        },
    )
    assert result == Decimal("100000")


@pytest.mark.asyncio
async def test_aux_executor_missing_record(db_session, seeded_db):
    """AUX() 记录不存在返回 FormulaError"""
    executor = AUXExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {
            "account_code": "1122",
            "aux_type": "客户",
            "aux_name": "不存在客户",
            "column_name": "期末余额",
        },
    )
    assert isinstance(result, FormulaError)


@pytest.mark.asyncio
async def test_aux_executor_invalid_column(db_session, seeded_db):
    """AUX() 无效列名返回 FormulaError"""
    executor = AUXExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {
            "account_code": "1122",
            "aux_type": "客户",
            "aux_name": "客户A",
            "column_name": "无效列",
        },
    )
    assert isinstance(result, FormulaError)


# ===== SumTBExecutor Tests =====


@pytest.mark.asyncio
async def test_sum_tb_executor(db_session, seeded_db):
    """SUM_TB() 范围汇总"""
    executor = SumTBExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"account_range": "1001~1003", "column_name": "期末余额"},
    )
    # 1001=50000 + 1002=1000000 + 1003=100000 = 1150000
    assert result == Decimal("1150000")


@pytest.mark.asyncio
async def test_sum_tb_executor_single_account(db_session, seeded_db):
    """SUM_TB() 范围内只有一个科目"""
    executor = SumTBExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"account_range": "6001~6001", "column_name": "期末余额"},
    )
    assert result == Decimal("3000000")


@pytest.mark.asyncio
async def test_sum_tb_executor_revenue_range(db_session, seeded_db):
    """SUM_TB() 收入科目范围"""
    executor = SumTBExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"account_range": "6001~6099", "column_name": "期末余额"},
    )
    # 6001=3000000 + 6002=200000 = 3200000
    assert result == Decimal("3200000")


@pytest.mark.asyncio
async def test_sum_tb_executor_empty_range(db_session, seeded_db):
    """SUM_TB() 范围内无科目返回 0"""
    executor = SumTBExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"account_range": "9001~9099", "column_name": "期末余额"},
    )
    assert result == Decimal("0")


@pytest.mark.asyncio
async def test_sum_tb_executor_invalid_range(db_session, seeded_db):
    """SUM_TB() 无效范围格式返回 FormulaError"""
    executor = SumTBExecutor()
    result = await executor.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        {"account_range": "1001", "column_name": "期末余额"},
    )
    assert isinstance(result, FormulaError)


# ===== FormulaEngine Tests =====


@pytest.mark.asyncio
async def test_engine_execute_tb(db_session, seeded_db, fake_redis):
    """FormulaEngine.execute TB"""
    engine = FormulaEngine(redis_client=fake_redis)
    result = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "TB", {"account_code": "1001", "column_name": "期末余额"},
    )
    assert result["value"] == 50000.0
    assert result["cached"] is False
    assert result["error"] is None


@pytest.mark.asyncio
async def test_engine_execute_caching(db_session, seeded_db, fake_redis):
    """FormulaEngine caching: second call returns cached=True"""
    engine = FormulaEngine(redis_client=fake_redis)

    r1 = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "TB", {"account_code": "1001", "column_name": "期末余额"},
    )
    assert r1["cached"] is False

    r2 = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "TB", {"account_code": "1001", "column_name": "期末余额"},
    )
    assert r2["cached"] is True
    assert r2["value"] == r1["value"]


@pytest.mark.asyncio
async def test_engine_invalidate_cache(db_session, seeded_db, fake_redis):
    """FormulaEngine.invalidate_cache clears cached entries"""
    engine = FormulaEngine(redis_client=fake_redis)

    await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "TB", {"account_code": "1001", "column_name": "期末余额"},
    )

    deleted = await engine.invalidate_cache(FAKE_PROJECT_ID, 2025)
    assert deleted >= 1

    r = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "TB", {"account_code": "1001", "column_name": "期末余额"},
    )
    assert r["cached"] is False


@pytest.mark.asyncio
async def test_engine_execute_without_redis(db_session, seeded_db):
    """FormulaEngine works without Redis"""
    engine = FormulaEngine(redis_client=None)
    result = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "TB", {"account_code": "1001", "column_name": "期末余额"},
    )
    assert result["value"] == 50000.0
    assert result["cached"] is False


@pytest.mark.asyncio
async def test_engine_execute_unknown_type(db_session, seeded_db):
    """FormulaEngine unknown formula type returns error"""
    engine = FormulaEngine(redis_client=None)
    result = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "UNKNOWN", {},
    )
    assert result["error"] is not None
    assert "未知公式类型" in result["error"]


@pytest.mark.asyncio
async def test_engine_execute_prev(db_session, seeded_db):
    """FormulaEngine PREV: year-1 data"""
    engine = FormulaEngine(redis_client=None)
    result = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "PREV", {
            "inner_type": "TB",
            "inner_params": {"account_code": "1001", "column_name": "期末余额"},
        },
    )
    # 2024 data: audited_amount=40000
    assert result["value"] == 40000.0
    assert result["error"] is None


@pytest.mark.asyncio
async def test_engine_execute_prev_no_data(db_session, seeded_db):
    """FormulaEngine PREV: year-1 no data returns error"""
    engine = FormulaEngine(redis_client=None)
    result = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "PREV", {
            "inner_type": "TB",
            "inner_params": {"account_code": "9999", "column_name": "期末余额"},
        },
    )
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_engine_execute_sum_tb(db_session, seeded_db):
    """FormulaEngine SUM_TB"""
    engine = FormulaEngine(redis_client=None)
    result = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "SUM_TB", {"account_range": "1001~1003", "column_name": "期末余额"},
    )
    assert result["value"] == 1150000.0


@pytest.mark.asyncio
async def test_engine_execute_aux(db_session, seeded_db):
    """FormulaEngine AUX"""
    engine = FormulaEngine(redis_client=None)
    result = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "AUX", {
            "account_code": "1122",
            "aux_type": "客户",
            "aux_name": "客户A",
            "column_name": "期末余额",
        },
    )
    assert result["value"] == 120000.0


@pytest.mark.asyncio
async def test_engine_execute_wp_stub(db_session, seeded_db):
    """FormulaEngine WP stub returns error"""
    engine = FormulaEngine(redis_client=None)
    result = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "WP", {"wp_code": "E1-1", "cell_ref": "B5"},
    )
    assert result["error"] is not None
    assert "暂不支持" in result["error"]


@pytest.mark.asyncio
async def test_engine_batch_execute(db_session, seeded_db):
    """FormulaEngine.batch_execute"""
    engine = FormulaEngine(redis_client=None)
    formulas = [
        {"formula_type": "TB", "params": {"account_code": "1001", "column_name": "期末余额"}},
        {"formula_type": "TB", "params": {"account_code": "1002", "column_name": "期末余额"}},
        {"formula_type": "SUM_TB", "params": {"account_range": "6001~6099", "column_name": "期末余额"}},
    ]
    results = await engine.batch_execute(db_session, FAKE_PROJECT_ID, 2025, formulas)
    assert len(results) == 3
    assert results[0]["value"] == 50000.0
    assert results[1]["value"] == 1000000.0
    assert results[2]["value"] == 3200000.0


@pytest.mark.asyncio
async def test_engine_deterministic(db_session, seeded_db):
    """FormulaEngine deterministic: same formula → same result"""
    engine = FormulaEngine(redis_client=None)
    r1 = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "TB", {"account_code": "1001", "column_name": "期末余额"},
    )
    r2 = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "TB", {"account_code": "1001", "column_name": "期末余额"},
    )
    assert r1["value"] == r2["value"]


@pytest.mark.asyncio
async def test_engine_error_returns_formula_error(db_session, seeded_db):
    """FormulaEngine error handling: returns error string, not exception"""
    engine = FormulaEngine(redis_client=None)
    result = await engine.execute(
        db_session, FAKE_PROJECT_ID, 2025,
        "TB", {"account_code": "9999", "column_name": "期末余额"},
    )
    assert result["value"] is None
    assert result["error"] is not None
    assert "FORMULA_ERROR" not in result["error"]  # message, not code
    assert "9999" in result["error"]


# ===== API Route Tests =====


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    """Create test HTTP client"""
    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.main import app

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def override_get_db():
        yield db_session

    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_execute_formula(client: AsyncClient):
    """POST /api/formula/execute"""
    resp = await client.post(
        "/api/formula/execute",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "formula_type": "TB",
            "params": {"account_code": "1001", "column_name": "期末余额"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["value"] == 50000.0
    assert result["error"] is None


@pytest.mark.asyncio
async def test_api_execute_formula_error(client: AsyncClient):
    """POST /api/formula/execute with invalid account"""
    resp = await client.post(
        "/api/formula/execute",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "formula_type": "TB",
            "params": {"account_code": "9999", "column_name": "期末余额"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_api_batch_execute(client: AsyncClient):
    """POST /api/formula/batch-execute"""
    resp = await client.post(
        "/api/formula/batch-execute",
        json=[
            {
                "project_id": str(FAKE_PROJECT_ID),
                "year": 2025,
                "formula_type": "TB",
                "params": {"account_code": "1001", "column_name": "期末余额"},
            },
            {
                "project_id": str(FAKE_PROJECT_ID),
                "year": 2025,
                "formula_type": "SUM_TB",
                "params": {"account_range": "1001~1003", "column_name": "期末余额"},
            },
        ],
    )
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("data", data)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_api_batch_execute_empty(client: AsyncClient):
    """POST /api/formula/batch-execute with empty list"""
    resp = await client.post(
        "/api/formula/batch-execute",
        json=[],
    )
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("data", data)
    assert results == []
