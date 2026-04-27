"""Tests for Task 16: 大数据处理优化（穿透查询）

Validates: Requirements 15.1-15.5
"""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, ProjectUser
from app.models.audit_platform_models import TbBalance, TbLedger, TbAuxBalance, TbAuxLedger

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
    """Seed project + balance + ledger + aux data"""
    user = User(
        id=FAKE_USER_ID, username="tester", email="t@test.com",
        hashed_password="x", role="member",
    )
    db_session.add(user)

    project = Project(
        id=FAKE_PROJECT_ID, name="穿透查询测试", client_name="测试",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)

    db_session.add(ProjectUser(
        project_id=FAKE_PROJECT_ID, user_id=FAKE_USER_ID,
        role="auditor", permission_level="edit", is_deleted=False,
    ))

    # 科目余额
    for code, name, opening, debit, credit in [
        ("1001", "库存现金", 10000, 50000, 45000),
        ("1002", "银行存款", 500000, 2000000, 1800000),
        ("1122", "应收账款", 300000, 1000000, 900000),
    ]:
        db_session.add(TbBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            account_code=code, account_name=name,
            opening_balance=Decimal(str(opening)),
            debit_amount=Decimal(str(debit)),
            credit_amount=Decimal(str(credit)),
            closing_balance=Decimal(str(opening + debit - credit)),
        ))

    # 序时账（模拟多条凭证）
    for i in range(50):
        db_session.add(TbLedger(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            voucher_date=date(2025, 1, 1 + (i % 28)),
            voucher_no=f"记-{i+1:04d}",
            account_code="1002", account_name="银行存款",
            debit_amount=Decimal("40000") if i % 2 == 0 else Decimal("0"),
            credit_amount=Decimal("0") if i % 2 == 0 else Decimal("36000"),
            summary=f"测试凭证{i+1}",
        ))

    # 辅助余额
    for aux_code, aux_name, closing in [
        ("C001", "客户A", 150000), ("C002", "客户B", 100000), ("C003", "客户C", 50000),
    ]:
        db_session.add(TbAuxBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            account_code="1122", aux_type="客户", aux_code=aux_code, aux_name=aux_name,
            opening_balance=Decimal("100000"),
            debit_amount=Decimal("300000"),
            credit_amount=Decimal(str(300000 + 100000 - closing)),
            closing_balance=Decimal(str(closing)),
        ))

    # 辅助明细
    for i in range(20):
        db_session.add(TbAuxLedger(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            voucher_date=date(2025, 1, 1 + (i % 28)),
            voucher_no=f"记-{i+100:04d}",
            account_code="1122", aux_type="客户", aux_code="C001", aux_name="客户A",
            debit_amount=Decimal("15000") if i % 2 == 0 else Decimal("0"),
            credit_amount=Decimal("0") if i % 2 == 0 else Decimal("12000"),
            summary=f"辅助明细{i+1}",
        ))

    await db_session.commit()
    return {"project_id": FAKE_PROJECT_ID}


class TestLedgerPenetrationService:

    @pytest.mark.asyncio
    async def test_balance_summary(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.get_balance_summary(FAKE_PROJECT_ID, YEAR)
        assert len(result) == 3
        codes = [r["account_code"] for r in result]
        assert "1001" in codes
        assert "1002" in codes

    @pytest.mark.asyncio
    async def test_balance_summary_filter(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.get_balance_summary(FAKE_PROJECT_ID, YEAR, account_code="1002")
        assert len(result) == 1
        assert result[0]["account_code"] == "1002"

    @pytest.mark.asyncio
    async def test_ledger_entries(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.get_ledger_entries(FAKE_PROJECT_ID, YEAR, "1002")
        assert result["total"] == 50
        assert len(result["items"]) <= 100

    @pytest.mark.asyncio
    async def test_ledger_entries_pagination(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        p1 = await svc.get_ledger_entries(FAKE_PROJECT_ID, YEAR, "1002", page=1, page_size=10)
        p2 = await svc.get_ledger_entries(FAKE_PROJECT_ID, YEAR, "1002", page=2, page_size=10)
        assert len(p1["items"]) == 10
        assert len(p2["items"]) == 10
        assert p1["items"][0]["voucher_no"] != p2["items"][0]["voucher_no"]

    @pytest.mark.asyncio
    async def test_ledger_entries_date_filter(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.get_ledger_entries(
            FAKE_PROJECT_ID, YEAR, "1002", date_from="2025-01-01", date_to="2025-01-05",
        )
        assert result["total"] > 0
        for item in result["items"]:
            assert item["voucher_date"] <= date(2025, 1, 5)

    @pytest.mark.asyncio
    async def test_voucher_entries(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.get_voucher_entries(FAKE_PROJECT_ID, YEAR, "记-0001")
        assert len(result) >= 1
        assert result[0]["voucher_no"] == "记-0001"

    @pytest.mark.asyncio
    async def test_aux_balance(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.get_aux_balance(FAKE_PROJECT_ID, YEAR, "1122")
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_aux_ledger_entries(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.get_aux_ledger_entries(
            FAKE_PROJECT_ID, YEAR, "1122", aux_type="客户", aux_code="C001",
        )
        assert result["total"] == 20

    @pytest.mark.asyncio
    async def test_penetrate_all(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.penetrate(FAKE_PROJECT_ID, YEAR, account_code="1002")
        assert "total" in result
        assert "ledger" in result
        assert "aux_balance" in result

    @pytest.mark.asyncio
    async def test_penetrate_total_only(self, db_session, seeded_db):
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session)
        result = await svc.penetrate(FAKE_PROJECT_ID, YEAR, drill_level="total")
        assert "total" in result
        assert "ledger" not in result

    @pytest.mark.asyncio
    async def test_cache_and_invalidate(self, db_session, seeded_db):
        import fakeredis.aioredis
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session, fake_redis)

        # First call: cache miss
        r1 = await svc.penetrate_cached(FAKE_PROJECT_ID, YEAR, drill_level="total")
        assert "total" in r1

        # Second call: cache hit (same result)
        r2 = await svc.penetrate_cached(FAKE_PROJECT_ID, YEAR, drill_level="total")
        assert r2 == r1

        # Invalidate
        cleared = await svc.invalidate_cache(FAKE_PROJECT_ID, YEAR)
        assert cleared >= 1

    @pytest.mark.asyncio
    async def test_cache_degradation(self, db_session, seeded_db):
        """Redis不可用时降级到直接查询"""
        from app.services.ledger_penetration_service import LedgerPenetrationService
        svc = LedgerPenetrationService(db_session, redis=None)
        result = await svc.penetrate_cached(FAKE_PROJECT_ID, YEAR, drill_level="total")
        assert "total" in result

    @pytest.mark.asyncio
    async def test_legacy_upload_endpoint_returns_gone(self):
        from fastapi import HTTPException
        from app.routers.ledger_penetration import upload_data

        with pytest.raises(HTTPException, match="旧 /ledger/upload 导入入口已废弃") as exc:
            await upload_data(
                project_id=uuid.uuid4(),
                year=2025,
                file=AsyncMock(),
                db=AsyncMock(),
                current_user=AsyncMock(),
            )

        assert exc.value.status_code == 410

    @pytest.mark.asyncio
    async def test_legacy_upload_multi_endpoint_returns_gone(self):
        from fastapi import HTTPException
        from app.routers.ledger_penetration import upload_multi_files

        with pytest.raises(HTTPException, match="旧 /ledger/upload-multi 导入入口已废弃") as exc:
            await upload_multi_files(
                project_id=uuid.uuid4(),
                year=2025,
                files=[],
                db=AsyncMock(),
                current_user=AsyncMock(),
            )

        assert exc.value.status_code == 410


# ── API 测试 ──

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
            value = "member"
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


class TestLedgerPenetrationAPI:

    @pytest.mark.asyncio
    async def test_penetrate_api(self, client):
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/penetrate",
            params={"year": YEAR, "account_code": "1002"},
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert "total" in data

    @pytest.mark.asyncio
    async def test_balance_api(self, client):
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance",
            params={"year": YEAR},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_entries_api(self, client):
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/entries/1002",
            params={"year": YEAR, "page": 1, "page_size": 10},
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["total"] == 50
        assert len(data["items"]) == 10

    @pytest.mark.asyncio
    async def test_voucher_api(self, client):
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/voucher/记-0001",
            params={"year": YEAR},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_aux_balance_api(self, client):
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/aux-balance/1122",
            params={"year": YEAR},
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_aux_entries_api(self, client):
        resp = await client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/aux-entries/1122",
            params={"year": YEAR, "aux_type": "客户", "aux_code": "C001"},
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["total"] == 20

    @pytest.mark.asyncio
    async def test_clear_cache_api(self, client):
        resp = await client.delete(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/cache",
            params={"year": YEAR},
        )
        assert resp.status_code == 200
