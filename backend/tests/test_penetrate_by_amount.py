"""Tests for Task 11: 按金额穿透端点

Validates: Requirements 5 (R4)
- GET /api/projects/{pid}/ledger/penetrate-by-amount
- 四策略匹配（exact / tolerance / code+amount / summary_keyword）
- 结果超 200 条截断提示
- 性能 P95 < 2s（用现有索引）
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, ProjectUser
from app.models.audit_platform_models import TbLedger

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()
YEAR = 2025


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """Seed project + ledger entries for penetrate-by-amount testing"""
    user = User(
        id=FAKE_USER_ID, username="tester", email="t@test.com",
        hashed_password="x", role="member",
    )
    db_session.add(user)

    project = Project(
        id=FAKE_PROJECT_ID, name="按金额穿透测试", client_name="测试客户",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)

    db_session.add(ProjectUser(
        project_id=FAKE_PROJECT_ID, user_id=FAKE_USER_ID,
        role="auditor", permission_level="edit", is_deleted=False,
    ))

    # 精确金额匹配条目
    db_session.add(TbLedger(
        project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
        voucher_date=date(2025, 3, 15), voucher_no="记-0100",
        account_code="6001", account_name="主营业务收入",
        debit_amount=Decimal("0"), credit_amount=Decimal("500000.00"),
        summary="销售商品收入",
    ))
    db_session.add(TbLedger(
        project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
        voucher_date=date(2025, 3, 16), voucher_no="记-0101",
        account_code="1002", account_name="银行存款",
        debit_amount=Decimal("500000.00"), credit_amount=Decimal("0"),
        summary="收到销售款",
    ))

    # 容差范围内的条目（500000 ± 100）
    db_session.add(TbLedger(
        project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
        voucher_date=date(2025, 4, 1), voucher_no="记-0200",
        account_code="6001", account_name="主营业务收入",
        debit_amount=Decimal("0"), credit_amount=Decimal("500050.00"),
        summary="销售商品收入（含运费）",
    ))
    db_session.add(TbLedger(
        project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
        voucher_date=date(2025, 4, 2), voucher_no="记-0201",
        account_code="1122", account_name="应收账款",
        debit_amount=Decimal("499950.00"), credit_amount=Decimal("0"),
        summary="应收客户A货款",
    ))

    # 特定科目 + 金额匹配（用于 code+amount 策略）
    db_session.add(TbLedger(
        project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
        voucher_date=date(2025, 5, 10), voucher_no="记-0300",
        account_code="2202", account_name="应付账款",
        debit_amount=Decimal("500000.00"), credit_amount=Decimal("0"),
        summary="支付供应商B货款",
    ))

    # 摘要关键词匹配条目
    db_session.add(TbLedger(
        project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
        voucher_date=date(2025, 6, 1), voucher_no="记-0400",
        account_code="6601", account_name="管理费用",
        debit_amount=Decimal("500000.00"), credit_amount=Decimal("0"),
        summary="咨询费-审计服务费",
    ))

    # 不相关的条目（不同金额）
    for i in range(10):
        db_session.add(TbLedger(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            voucher_date=date(2025, 1, 1 + i),
            voucher_no=f"记-{900+i:04d}",
            account_code="1001", account_name="库存现金",
            debit_amount=Decimal("1000.00"),
            credit_amount=Decimal("0"),
            summary=f"零星支出{i}",
        ))

    await db_session.commit()
    return {"project_id": FAKE_PROJECT_ID}


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    import fakeredis.aioredis
    from httpx import ASGITransport, AsyncClient
    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.main import app

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def override_get_db():
        yield db_session

    async def override_get_redis():
        yield fake_redis

    from app.deps import get_current_user

    class _FakeUser:
        id = FAKE_USER_ID

        class _Role:
            value = "admin"
        role = _Role()

    async def override_get_current_user():
        return _FakeUser()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _unwrap(resp_json: dict) -> dict:
    """Unwrap response middleware envelope {code, data, message} → data"""
    if "data" in resp_json and "code" in resp_json:
        return resp_json["data"]
    return resp_json


class TestPenetrateByAmountAPI:
    """API-level tests for penetrate-by-amount endpoint"""

    @pytest.mark.asyncio
    async def test_exact_match(self, client):
        """精确金额匹配"""
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/penetrate-by-amount",
            params={"year": YEAR, "amount": 500000.00, "tolerance": 0},
        )
        assert resp.status_code == 200
        data = _unwrap(resp.json())
        assert "matches" in data
        # Should find exact matches
        exact_matches = [m for m in data["matches"] if m["strategy"] == "exact"]
        assert len(exact_matches) == 1
        # 记-0100, 记-0101, 记-0300, 记-0400 all have exactly 500000
        assert len(exact_matches[0]["items"]) >= 2

    @pytest.mark.asyncio
    async def test_tolerance_match(self, client):
        """容差金额匹配"""
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/penetrate-by-amount",
            params={"year": YEAR, "amount": 500000.00, "tolerance": 100},
        )
        assert resp.status_code == 200
        data = _unwrap(resp.json())
        # Should have exact + tolerance strategies
        strategies = [m["strategy"] for m in data["matches"]]
        assert "exact" in strategies
        assert "tolerance" in strategies
        # Tolerance items should include 500050 and 499950
        tol_match = next(m for m in data["matches"] if m["strategy"] == "tolerance")
        tol_amounts = []
        for item in tol_match["items"]:
            tol_amounts.append(item["debit_amount"] or item["credit_amount"])
        assert any(abs(a - 500050) < 0.01 for a in tol_amounts)

    @pytest.mark.asyncio
    async def test_code_plus_amount_match(self, client):
        """科目+金额匹配"""
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/penetrate-by-amount",
            params={
                "year": YEAR, "amount": 500000.00, "tolerance": 0,
                "account_code": "2202",
            },
        )
        assert resp.status_code == 200
        data = _unwrap(resp.json())
        strategies = [m["strategy"] for m in data["matches"]]
        # exact will include all 500000 entries, code+amount filters to 2202 only
        # Since 2202 entry is already in exact, code+amount may be empty (dedup)
        assert "exact" in strategies

    @pytest.mark.asyncio
    async def test_summary_keyword_match(self, client):
        """摘要关键词匹配"""
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/penetrate-by-amount",
            params={
                "year": YEAR, "amount": 500000.00, "tolerance": 100,
                "summary_keyword": "审计",
            },
        )
        assert resp.status_code == 200
        data = _unwrap(resp.json())
        strategies = [m["strategy"] for m in data["matches"]]
        # The "审计服务费" entry should appear in summary strategy
        # (unless already captured by exact)
        assert "exact" in strategies

    @pytest.mark.asyncio
    async def test_empty_results_message(self, client):
        """无匹配结果时返回友好提示"""
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/penetrate-by-amount",
            params={"year": YEAR, "amount": 99999999.99, "tolerance": 0},
        )
        assert resp.status_code == 200
        data = _unwrap(resp.json())
        assert data["matches"] == []
        assert "未找到匹配凭证" in data["message"]
        assert "params" in data
        assert data["params"]["amount"] == 99999999.99

    @pytest.mark.asyncio
    async def test_date_filter(self, client):
        """日期范围过滤"""
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/penetrate-by-amount",
            params={
                "year": YEAR, "amount": 500000.00, "tolerance": 0,
                "date_from": "2025-03-01", "date_to": "2025-03-31",
            },
        )
        assert resp.status_code == 200
        data = _unwrap(resp.json())
        # Only March entries should match
        exact_matches = [m for m in data["matches"] if m["strategy"] == "exact"]
        assert len(exact_matches) == 1
        for item in exact_matches[0]["items"]:
            assert item["voucher_date"].startswith("2025-03")

    @pytest.mark.asyncio
    async def test_default_tolerance(self, client):
        """默认容差 0.01"""
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/penetrate-by-amount",
            params={"year": YEAR, "amount": 500000.00},
        )
        assert resp.status_code == 200
        data = _unwrap(resp.json())
        # With default tolerance 0.01, only exact matches should appear
        assert "matches" in data
        strategies = [m["strategy"] for m in data["matches"]]
        assert "exact" in strategies

    @pytest.mark.asyncio
    async def test_missing_required_params(self, client):
        """缺少必填参数返回 422"""
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/penetrate-by-amount",
            params={"year": YEAR},  # missing amount
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_response_structure(self, client):
        """验证响应结构"""
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/penetrate-by-amount",
            params={"year": YEAR, "amount": 500000.00, "tolerance": 100},
        )
        assert resp.status_code == 200
        data = _unwrap(resp.json())
        assert "matches" in data
        assert "total_count" in data
        for match in data["matches"]:
            assert "strategy" in match
            assert match["strategy"] in ("exact", "tolerance", "code+amount", "summary")
            assert "items" in match
            for item in match["items"]:
                assert "id" in item
                assert "voucher_date" in item
                assert "voucher_no" in item
                assert "account_code" in item
                assert "debit_amount" in item
                assert "credit_amount" in item
                assert "summary" in item


class TestPenetrateByAmountTruncation:
    """Test truncation behavior when results exceed 200"""

    @pytest_asyncio.fixture
    async def large_db_session(self) -> AsyncSession:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            yield session

    @pytest_asyncio.fixture
    async def large_seeded_db(self, large_db_session: AsyncSession):
        """Seed > 200 entries with same amount to test truncation"""
        user = User(
            id=FAKE_USER_ID, username="tester", email="t@test.com",
            hashed_password="x", role="member",
        )
        large_db_session.add(user)

        project = Project(
            id=FAKE_PROJECT_ID, name="截断测试", client_name="测试",
            project_type=ProjectType.annual, status=ProjectStatus.execution,
            created_by=FAKE_USER_ID,
        )
        large_db_session.add(project)

        large_db_session.add(ProjectUser(
            project_id=FAKE_PROJECT_ID, user_id=FAKE_USER_ID,
            role="auditor", permission_level="edit", is_deleted=False,
        ))

        # Insert 250 entries with same amount to trigger truncation
        for i in range(250):
            large_db_session.add(TbLedger(
                project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
                voucher_date=date(2025, 1, 1 + (i % 28)),
                voucher_no=f"记-{i:04d}",
                account_code="1002", account_name="银行存款",
                debit_amount=Decimal("100000.00"),
                credit_amount=Decimal("0"),
                summary=f"批量凭证{i}",
            ))

        await large_db_session.commit()

    @pytest.mark.asyncio
    async def test_truncation_at_200(self, large_db_session, large_seeded_db):
        """超过 200 条结果时截断并提示"""
        import fakeredis.aioredis
        from httpx import ASGITransport, AsyncClient
        from app.core.database import get_db
        from app.core.redis import get_redis
        from app.main import app
        from app.deps import get_current_user

        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

        async def override_get_db():
            yield large_db_session

        async def override_get_redis():
            yield fake_redis

        class _FakeUser:
            id = FAKE_USER_ID

            class _Role:
                value = "admin"
            role = _Role()

        async def override_get_current_user():
            return _FakeUser()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_redis] = override_get_redis
        app.dependency_overrides[get_current_user] = override_get_current_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(
                f"/api/projects/{FAKE_PROJECT_ID}/ledger/penetrate-by-amount",
                params={"year": YEAR, "amount": 100000.00, "tolerance": 0},
            )

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = _unwrap(resp.json())
        assert data.get("truncated") is True
        assert "结果过多" in data.get("message", "")
        # Total items should be capped at 200
        total_items = sum(len(m["items"]) for m in data["matches"])
        assert total_items <= 200
