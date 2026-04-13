"""Tests for Task 12: T型账户法

Validates: Requirements 10.1-10.6
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.t_account_models import TAccount, TAccountEntry, T_ACCOUNT_TEMPLATES

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
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    project = Project(
        id=FAKE_PROJECT_ID, name="T型账户测试", client_name="测试",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.commit()
    return {"project_id": FAKE_PROJECT_ID}


class TestTAccountService:

    @pytest.mark.asyncio
    async def test_create_t_account(self, db_session, seeded_db):
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        result = await svc.create_t_account(db_session, FAKE_PROJECT_ID, {
            "account_code": "1601", "account_name": "固定资产清理",
            "account_type": "asset", "opening_balance": 0,
        })
        await db_session.commit()
        assert result["account_code"] == "1601"
        assert result["opening_balance"] == 0
        assert result["net_change"] == 0

    @pytest.mark.asyncio
    async def test_add_debit_entry(self, db_session, seeded_db):
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        acc = await svc.create_t_account(db_session, FAKE_PROJECT_ID, {
            "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        })
        await db_session.flush()
        entry = await svc.add_entry(db_session, uuid.UUID(acc["id"]), {
            "entry_type": "debit", "amount": 100000, "description": "原值转入",
        })
        assert entry["entry_type"] == "debit"
        assert entry["amount"] == 100000

    @pytest.mark.asyncio
    async def test_add_credit_entry(self, db_session, seeded_db):
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        acc = await svc.create_t_account(db_session, FAKE_PROJECT_ID, {
            "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        })
        await db_session.flush()
        entry = await svc.add_entry(db_session, uuid.UUID(acc["id"]), {
            "entry_type": "credit", "amount": 60000, "description": "累计折旧转入",
        })
        assert entry["entry_type"] == "credit"

    @pytest.mark.asyncio
    async def test_invalid_entry_type(self, db_session, seeded_db):
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        acc = await svc.create_t_account(db_session, FAKE_PROJECT_ID, {
            "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        })
        await db_session.flush()
        with pytest.raises(ValueError, match="entry_type"):
            await svc.add_entry(db_session, uuid.UUID(acc["id"]), {
                "entry_type": "invalid", "amount": 100,
            })

    @pytest.mark.asyncio
    async def test_zero_amount(self, db_session, seeded_db):
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        acc = await svc.create_t_account(db_session, FAKE_PROJECT_ID, {
            "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        })
        await db_session.flush()
        with pytest.raises(ValueError, match="金额"):
            await svc.add_entry(db_session, uuid.UUID(acc["id"]), {
                "entry_type": "debit", "amount": 0,
            })

    @pytest.mark.asyncio
    async def test_calculate_net_change_asset(self, db_session, seeded_db):
        """资产类：净变动 = 借方 - 贷方"""
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        acc = await svc.create_t_account(db_session, FAKE_PROJECT_ID, {
            "account_code": "1601", "account_name": "固定资产清理",
            "account_type": "asset", "opening_balance": 0,
        })
        await db_session.flush()
        aid = uuid.UUID(acc["id"])
        await svc.add_entry(db_session, aid, {"entry_type": "debit", "amount": 100000, "description": "原值"})
        await svc.add_entry(db_session, aid, {"entry_type": "credit", "amount": 60000, "description": "折旧"})
        await svc.add_entry(db_session, aid, {"entry_type": "credit", "amount": 50000, "description": "处置收入"})
        await db_session.flush()

        result = await svc.calculate_net_change(db_session, aid)
        assert result["debit_total"] == 100000
        assert result["credit_total"] == 110000
        assert result["net_change"] == -10000  # 100000 - 110000
        assert result["closing_balance"] == -10000  # 0 + (-10000)

    @pytest.mark.asyncio
    async def test_calculate_net_change_liability(self, db_session, seeded_db):
        """负债类：净变动 = 贷方 - 借方"""
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        acc = await svc.create_t_account(db_session, FAKE_PROJECT_ID, {
            "account_code": "2201", "account_name": "应付账款",
            "account_type": "liability", "opening_balance": 500000,
        })
        await db_session.flush()
        aid = uuid.UUID(acc["id"])
        await svc.add_entry(db_session, aid, {"entry_type": "debit", "amount": 200000, "description": "偿还"})
        await svc.add_entry(db_session, aid, {"entry_type": "credit", "amount": 300000, "description": "新增"})
        await db_session.flush()

        result = await svc.calculate_net_change(db_session, aid)
        assert result["net_change"] == 100000  # 300000 - 200000
        assert result["closing_balance"] == 600000  # 500000 + 100000

    @pytest.mark.asyncio
    async def test_reconcile_match(self, db_session, seeded_db):
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        acc = await svc.create_t_account(db_session, FAKE_PROJECT_ID, {
            "account_code": "1601", "account_name": "固定资产清理",
            "account_type": "asset", "opening_balance": 0,
        })
        await db_session.flush()
        aid = uuid.UUID(acc["id"])
        await svc.add_entry(db_session, aid, {"entry_type": "debit", "amount": 50000})
        await db_session.flush()

        result = await svc.reconcile_with_balance_sheet(
            db_session, aid, Decimal("0"), Decimal("50000"),
        )
        assert result["is_reconciled"] is True

    @pytest.mark.asyncio
    async def test_reconcile_mismatch(self, db_session, seeded_db):
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        acc = await svc.create_t_account(db_session, FAKE_PROJECT_ID, {
            "account_code": "1601", "account_name": "固定资产清理",
            "account_type": "asset", "opening_balance": 0,
        })
        await db_session.flush()
        aid = uuid.UUID(acc["id"])
        await svc.add_entry(db_session, aid, {"entry_type": "debit", "amount": 50000})
        await db_session.flush()

        result = await svc.reconcile_with_balance_sheet(
            db_session, aid, Decimal("0"), Decimal("60000"),
        )
        assert result["is_reconciled"] is False
        assert result["difference"] == 10000

    @pytest.mark.asyncio
    async def test_integrate_to_cfs(self, db_session, seeded_db):
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        acc = await svc.create_t_account(db_session, FAKE_PROJECT_ID, {
            "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        })
        await db_session.flush()
        aid = uuid.UUID(acc["id"])
        await svc.add_entry(db_session, aid, {"entry_type": "debit", "amount": 100000, "description": "原值转入"})
        await svc.add_entry(db_session, aid, {"entry_type": "credit", "amount": 80000, "description": "处置收入"})
        await db_session.flush()

        result = await svc.integrate_to_cfs(db_session, aid)
        assert len(result["cfs_adjustment_items"]) == 2
        assert result["net_change"] == 20000

    @pytest.mark.asyncio
    async def test_list_t_accounts(self, db_session, seeded_db):
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        await svc.create_t_account(db_session, FAKE_PROJECT_ID, {
            "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        })
        await svc.create_t_account(db_session, FAKE_PROJECT_ID, {
            "account_code": "2201", "account_name": "应付账款", "account_type": "liability",
        })
        await db_session.commit()
        items = await svc.list_t_accounts(db_session, FAKE_PROJECT_ID)
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_get_not_found(self, db_session, seeded_db):
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        result = await svc.get_t_account(db_session, uuid.uuid4())
        assert result is None

    def test_templates(self):
        from app.services.t_account_service import TAccountService
        svc = TAccountService()
        templates = svc.get_templates()
        assert len(templates) == len(T_ACCOUNT_TEMPLATES)
        assert templates[0]["name"] == "固定资产处置"


# ── API 测试 ──

@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    import fakeredis.aioredis
    from httpx import ASGITransport, AsyncClient
    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.main import app

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_db] = lambda: db_session  # simplified
    app.dependency_overrides[get_redis] = lambda: fake_redis

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


class TestTAccountAPI:

    @pytest.mark.asyncio
    async def test_create_api(self, client):
        resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts", json={
            "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        })
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["account_code"] == "1601"

    @pytest.mark.asyncio
    async def test_list_api(self, client):
        await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts", json={
            "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        })
        resp = await client.get(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_add_entry_api(self, client):
        create_resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts", json={
            "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        })
        tid = create_resp.json().get("data", create_resp.json())["id"]

        resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts/{tid}/entries", json={
            "entry_type": "debit", "amount": 100000, "description": "原值转入",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_calculate_api(self, client):
        create_resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts", json={
            "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        })
        tid = create_resp.json().get("data", create_resp.json())["id"]
        await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts/{tid}/entries", json={
            "entry_type": "debit", "amount": 50000,
        })

        resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts/{tid}/calculate")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["debit_total"] == 50000

    @pytest.mark.asyncio
    async def test_reconcile_api(self, client):
        create_resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts", json={
            "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        })
        tid = create_resp.json().get("data", create_resp.json())["id"]
        await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts/{tid}/entries", json={
            "entry_type": "debit", "amount": 50000,
        })

        resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts/{tid}/reconcile", json={
            "bs_opening": 0, "bs_closing": 50000,
        })
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["is_reconciled"] is True

    @pytest.mark.asyncio
    async def test_integrate_api(self, client):
        create_resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts", json={
            "account_code": "1601", "account_name": "固定资产清理", "account_type": "asset",
        })
        tid = create_resp.json().get("data", create_resp.json())["id"]
        await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts/{tid}/entries", json={
            "entry_type": "debit", "amount": 100000, "description": "原值",
        })

        resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts/{tid}/integrate")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data["cfs_adjustment_items"]) == 1

    @pytest.mark.asyncio
    async def test_templates_api(self, client):
        resp = await client.get("/api/t-account-templates")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data) >= 5

    @pytest.mark.asyncio
    async def test_get_not_found_api(self, client):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/projects/{FAKE_PROJECT_ID}/t-accounts/{fake_id}")
        assert resp.status_code == 404
