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


# ═══════════════════════════════════════════════════════════════════════════
# Layer 2 / Sprint 8: 科目余额树形视图测试
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def seeded_tree_db(db_session: AsyncSession):
    """专用 fixture：复刻图中 1002 银行存款 汇总 307072.27 + 工行 + 邮储 结构。"""
    user = User(
        id=FAKE_USER_ID, username="tester", email="t@test.com",
        hashed_password="x", role="member",
    )
    db_session.add(user)

    project = Project(
        id=FAKE_PROJECT_ID, name="balance-tree test", client_name="c",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)

    db_session.add(ProjectUser(
        project_id=FAKE_PROJECT_ID, user_id=FAKE_USER_ID,
        role="auditor", permission_level="edit", is_deleted=False,
    ))

    # 1002 银行存款 汇总行
    db_session.add(TbBalance(
        project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
        account_code="1002", account_name="银行存款", level=1,
        opening_balance=Decimal("0"),
        debit_amount=Decimal("0"),
        credit_amount=Decimal("0"),
        closing_balance=Decimal("307072.27"),
    ))
    # 1122 应收账款 聚合行（无汇总仅明细场景，对应 converter 的 _aggregated_from_aux）
    db_session.add(TbBalance(
        project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
        account_code="1122", account_name="应收账款", level=1,
        opening_balance=Decimal("0"),
        closing_balance=Decimal("8000"),
        raw_extra={"_aggregated_from_aux": True, "_aux_row_count": 2},
    ))
    # 2202 纯汇总（无辅助）
    db_session.add(TbBalance(
        project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
        account_code="2202", account_name="应付账款", level=1,
        closing_balance=Decimal("-5000"),
    ))

    # 1002 的两条辅助余额（和 = 307072.27）
    for aux_code, aux_name, closing in [
        ("A001", "工商银行", Decimal("198431.65")),
        ("A002", "中国邮政储蓄银行", Decimal("108640.62")),
    ]:
        db_session.add(TbAuxBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            account_code="1002", aux_type="金融机构",
            aux_code=aux_code, aux_name=aux_name,
            closing_balance=closing,
        ))

    # 1122 的两条辅助余额（和 = 8000，和主表聚合值一致）
    for aux_code, aux_name, closing in [
        ("C001", "甲公司", Decimal("5000")),
        ("C002", "乙公司", Decimal("3000")),
    ]:
        db_session.add(TbAuxBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            account_code="1122", aux_type="客户",
            aux_code=aux_code, aux_name=aux_name,
            closing_balance=closing,
        ))

    await db_session.commit()
    return {"project_id": FAKE_PROJECT_ID}


@pytest_asyncio.fixture
async def tree_client(db_session: AsyncSession, seeded_tree_db):
    import fakeredis.aioredis
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.deps import get_current_user
    from app.main import app

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def override_get_db():
        yield db_session

    async def override_get_redis():
        yield fake_redis

    class _FakeUser:
        id = FAKE_USER_ID
        username = "tester"

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


class TestBalanceTreeEndpoint:
    """GET /api/projects/{pid}/ledger/balance-tree 返回主表+辅助两层嵌套。

    v2（2026-05-10）：children 按 aux_type 分组（第 2 层=维度组节点，
    第 3 层=具体 aux_code 明细行）；mismatch 按单一维度类型 vs 主表。
    """

    @pytest.mark.asyncio
    async def test_tree_structure(self, tree_client):
        resp = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR},
        )
        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)

        # 3 个主表行
        assert len(data["tree"]) == 3
        codes = [n["account_code"] for n in data["tree"]]
        assert set(codes) == {"1002", "1122", "2202"}

        # 1002 有 1 个维度组（金融机构），组内 2 条明细（工行+邮储）
        n1002 = next(n for n in data["tree"] if n["account_code"] == "1002")
        assert n1002["has_children"] is True
        assert len(n1002["children"]) == 1  # 1 个维度组
        assert n1002["aux_types"] == ["金融机构"]
        assert n1002["aux_rows_total"] == 2
        assert n1002["closing_balance"] == pytest.approx(307072.27)

        group = n1002["children"][0]
        assert group["_is_dimension_group"] is True
        assert group["aux_type"] == "金融机构"
        assert group["record_count"] == 2
        assert group["closing_balance"] == pytest.approx(307072.27)  # 维度组内求和
        aux_names = {c["aux_name"] for c in group["children"]}
        assert aux_names == {"工商银行", "中国邮政储蓄银行"}
        # 1002 不是聚合行
        assert n1002["aggregated_from_aux"] is False

    @pytest.mark.asyncio
    async def test_aggregated_flag_and_count(self, tree_client):
        resp = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR},
        )
        data = resp.json().get("data", resp.json())
        n1122 = next(n for n in data["tree"] if n["account_code"] == "1122")
        assert n1122["aggregated_from_aux"] is True
        assert n1122["aux_row_count"] == 2
        assert n1122["aux_rows_total"] == 2
        assert len(n1122["children"]) == 1  # 1 个"客户"维度组
        assert n1122["children"][0]["aux_type"] == "客户"
        assert n1122["children"][0]["record_count"] == 2

    @pytest.mark.asyncio
    async def test_pure_summary_has_no_children(self, tree_client):
        resp = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR},
        )
        data = resp.json().get("data", resp.json())
        n2202 = next(n for n in data["tree"] if n["account_code"] == "2202")
        assert n2202["has_children"] is False
        assert n2202["children"] == []
        assert n2202["aggregated_from_aux"] is False
        assert n2202["aux_types"] == []

    @pytest.mark.asyncio
    async def test_summary_counters(self, tree_client):
        resp = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR},
        )
        data = resp.json().get("data", resp.json())
        s = data["summary"]
        assert s["account_count"] == 3
        assert s["with_children_count"] == 2  # 1002 + 1122
        assert s["aggregated_count"] == 1  # 只有 1122
        assert s["aux_total_rows"] == 4  # 2 + 2（明细行总数，不是维度组数）
        # 维度组和 = 父，无 mismatch
        assert s["mismatches"] == []

    @pytest.mark.asyncio
    async def test_mismatch_detection(self, db_session, tree_client):
        # 人为制造一个不一致：往 1002 再加一条辅助但不补主表
        db_session.add(TbAuxBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            account_code="1002", aux_type="金融机构",
            aux_code="A003", aux_name="建设银行",
            closing_balance=Decimal("100.00"),  # 多出 100 元导致维度组 sum ≠ 父
        ))
        await db_session.commit()

        resp = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR},
        )
        data = resp.json().get("data", resp.json())
        mismatches = data["summary"]["mismatches"]
        # 新格式: 每条带 account_code + aux_type
        matches = [m for m in mismatches
                   if m["account_code"] == "1002" and m["aux_type"] == "金融机构"]
        assert len(matches) == 1
        assert matches[0]["record_count"] == 3  # 2 原有 + 1 新增
        assert matches[0]["dim_sum"] == pytest.approx(307172.27)
        assert matches[0]["parent_closing"] == pytest.approx(307072.27)
        assert matches[0]["diff"] == pytest.approx(100.00)

    @pytest.mark.asyncio
    async def test_multi_dimension_same_amount_no_mismatch(
        self, db_session, tree_client,
    ):
        """真实场景（YG36 1002）：一行多维度冗余存 N 条，按单一维度类型
        求和都等于主表，不应报 mismatch。

        例：
          金融机构:YG0001,工行;银行账户:3100...  closing=3948.93
          金融机构:YG0018,邮储;银行账户:951...   closing=100.00
        共 4 条 aux（2 金融机构 + 2 银行账户），平铺求和 = 父 × 2 错，
        按维度分组求和 = 父 ✓。
        """
        # 新建独立 account_code=1003 模拟真实 YG36 双维度
        db_session.add(TbBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            account_code="1003", account_name="现金-多维度测试", level=1,
            closing_balance=Decimal("4048.93"),
        ))
        # 金融机构维度 2 条
        for aux_code, aux_name, amt in [
            ("YG0001", "工行", Decimal("3948.93")),
            ("YG0018", "邮储", Decimal("100.00")),
        ]:
            db_session.add(TbAuxBalance(
                project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
                account_code="1003", aux_type="金融机构",
                aux_code=aux_code, aux_name=aux_name,
                closing_balance=amt,
            ))
        # 银行账户维度 2 条（同金额冗余）
        for aux_code, aux_name, amt in [
            (None, "3100035219100042014", Decimal("3948.93")),
            (None, "951004010002007700", Decimal("100.00")),
        ]:
            db_session.add(TbAuxBalance(
                project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
                account_code="1003", aux_type="银行账户",
                aux_code=aux_code, aux_name=aux_name,
                closing_balance=amt,
            ))
        await db_session.commit()

        resp = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR},
        )
        data = resp.json().get("data", resp.json())
        n1003 = next(n for n in data["tree"] if n["account_code"] == "1003")
        # 2 个维度组
        assert len(n1003["children"]) == 2
        assert set(n1003["aux_types"]) == {"金融机构", "银行账户"}
        assert n1003["aux_rows_total"] == 4
        # 每个维度组 sum = 父 closing（4048.93）
        for group in n1003["children"]:
            assert group["closing_balance"] == pytest.approx(4048.93)
            assert group["record_count"] == 2

        # summary 不应把 1003 标为 mismatch（按单一维度校验都过）
        mismatch_for_1003 = [m for m in data["summary"]["mismatches"]
                             if m["account_code"] == "1003"]
        assert mismatch_for_1003 == []


    # ── P3 分页测试 ──

    @pytest.mark.asyncio
    async def test_pagination_default(self, tree_client):
        """默认 page=1/size=100 返回 pagination 元信息。"""
        resp = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR},
        )
        data = resp.json().get("data", resp.json())
        assert "pagination" in data
        p = data["pagination"]
        assert p["page"] == 1
        assert p["page_size"] == 100
        assert p["total"] == 3  # 3 科目
        assert p["total_pages"] == 1

    @pytest.mark.asyncio
    async def test_pagination_page_size_2(self, tree_client):
        """page_size=2 → page1 返回 2 科目, page2 返回 1 科目。"""
        resp1 = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR, "page": 1, "page_size": 2},
        )
        data1 = resp1.json().get("data", resp1.json())
        assert len(data1["tree"]) == 2
        assert data1["pagination"]["page"] == 1
        assert data1["pagination"]["total"] == 3
        assert data1["pagination"]["total_pages"] == 2

        resp2 = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR, "page": 2, "page_size": 2},
        )
        data2 = resp2.json().get("data", resp2.json())
        assert len(data2["tree"]) == 1

    @pytest.mark.asyncio
    async def test_pagination_max_200(self, tree_client):
        """page_size 超过 200 应该 422（被 Query le=200 校验拒绝）。"""
        resp = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR, "page_size": 201},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_keyword_filter(self, tree_client):
        """keyword 过滤按 account_code/name 模糊匹配。"""
        resp = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR, "keyword": "1002"},
        )
        data = resp.json().get("data", resp.json())
        assert data["pagination"]["total"] == 1
        assert data["tree"][0]["account_code"] == "1002"

    @pytest.mark.asyncio
    async def test_only_with_children_filter(self, tree_client):
        """only_with_children=true 只返回有辅助的科目（1002 + 1122，不含 2202）。"""
        resp = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR, "only_with_children": "true"},
        )
        data = resp.json().get("data", resp.json())
        codes = {n["account_code"] for n in data["tree"]}
        assert codes == {"1002", "1122"}
        assert data["pagination"]["total"] == 2


    @pytest.mark.asyncio
    async def test_only_with_activity_loss_gain_coverage(
        self, db_session, tree_client,
    ):
        """only_with_activity 过滤：损益类（5/6）只看 debit/credit。

        真实场景：损益类科目期末结转到本年利润，opening/closing 为 NULL，
        但 debit/credit 当期有发生额，不应被"三字段都有金额"过滤掉。
        """
        # 添加 2 个损益类科目：一个有发生额，一个没有
        db_session.add(TbBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            account_code="6001", account_name="营业收入", level=1,
            # opening/closing 为 NULL（损益类结转特征）
            debit_amount=Decimal("37730554.10"),
            credit_amount=Decimal("37730554.10"),
        ))
        db_session.add(TbBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            account_code="6002", account_name="无活动损益",
            # 所有字段都 NULL 或 0
        ))
        # 添加 1 个资产类有活动的
        db_session.add(TbBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            account_code="1001", account_name="库存现金",
            opening_balance=Decimal("100"),
            closing_balance=Decimal("200"),
        ))
        # 添加 1 个资产类完全无活动的
        db_session.add(TbBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="001",
            account_code="1005", account_name="闲置科目",
        ))
        await db_session.commit()

        resp = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR, "only_with_activity": "true", "page_size": 200},
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        codes = {n["account_code"] for n in data["tree"]}

        # 6001 应该被包含（debit/credit 非零，虽然 opening/closing 为 NULL）
        assert "6001" in codes, "损益类 6001 有 debit/credit 应被 only_with_activity 包含"
        # 6002 应该被排除（所有字段 NULL）
        assert "6002" not in codes
        # 1001 资产类有 opening/closing 应被包含
        assert "1001" in codes
        # 1005 资产类全 NULL 应被排除
        assert "1005" not in codes
        # 原 1002/1122/2202 有 closing，也应被包含
        assert "1002" in codes
        assert "1122" in codes
        assert "2202" in codes  # 有 closing -5000


    # ── P1 多 company_code 合并账套专测 ──

    @pytest.mark.asyncio
    async def test_multi_company_isolation_and_merge(self, db_session, tree_client):
        """合并账套场景：不同 company_code 下相同 account_code 独立聚合。

        - 无 company_code 过滤时合并返回（父节点区分 company_code）
        - 传 company_code 只返回该公司数据
        - 两家子公司都有"金融机构:工行"辅助维度但不合并到一个节点
        """
        # 子公司 A001 的 6001 营业收入 + 客户维度
        db_session.add(TbBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="A001",
            account_code="6001", account_name="营业收入_A",
            debit_amount=Decimal("1000"),
            credit_amount=Decimal("1000"),
        ))
        db_session.add(TbAuxBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="A001",
            account_code="6001", aux_type="客户",
            aux_code="C01", aux_name="A 子公司客户",
            closing_balance=Decimal("1000"),
        ))
        # 子公司 B001 的 6001 营业收入 + 客户维度（account_code 相同）
        db_session.add(TbBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="B001",
            account_code="6001", account_name="营业收入_B",
            debit_amount=Decimal("2000"),
            credit_amount=Decimal("2000"),
        ))
        db_session.add(TbAuxBalance(
            project_id=FAKE_PROJECT_ID, year=YEAR, company_code="B001",
            account_code="6001", aux_type="客户",
            aux_code="C01", aux_name="B 子公司客户",
            closing_balance=Decimal("2000"),
        ))
        await db_session.commit()

        # 场景 1：不过滤公司 → 2 条 6001 独立主表行
        resp = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR, "keyword": "6001", "page_size": 50},
        )
        data = resp.json().get("data", resp.json())
        rows_6001 = [n for n in data["tree"] if n["account_code"] == "6001"]
        assert len(rows_6001) == 2, "2 家子公司的 6001 应独立存在于主表"
        companies = {n["company_code"] for n in rows_6001}
        assert companies == {"A001", "B001"}
        # 各自的 children 独立
        for row in rows_6001:
            assert len(row["children"]) == 1
            group = row["children"][0]
            assert group["aux_type"] == "客户"
            assert group["record_count"] == 1
            if row["company_code"] == "A001":
                assert group["closing_balance"] == pytest.approx(1000)
                assert group["children"][0]["aux_name"] == "A 子公司客户"
            else:
                assert group["closing_balance"] == pytest.approx(2000)
                assert group["children"][0]["aux_name"] == "B 子公司客户"

        # 场景 2：传 company_code=A001 → 只返 A001
        resp_a = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR, "company_code": "A001",
                    "keyword": "6001", "page_size": 50},
        )
        data_a = resp_a.json().get("data", resp_a.json())
        rows_a = [n for n in data_a["tree"] if n["account_code"] == "6001"]
        assert len(rows_a) == 1
        assert rows_a[0]["company_code"] == "A001"

        # 场景 3：only_with_children 在多公司合并下仍正确
        resp_c = await tree_client.get(
            f"/api/projects/{FAKE_PROJECT_ID}/ledger/balance-tree",
            params={"year": YEAR, "keyword": "6001",
                    "only_with_children": "true", "page_size": 50},
        )
        data_c = resp_c.json().get("data", resp_c.json())
        rows_c = [n for n in data_c["tree"] if n["account_code"] == "6001"]
        assert len(rows_c) == 2  # 两家都有辅助



# ═══════════════════════════════════════════════════════════════════════════
# UX v3: cancel 端点清理 artifact（P2-4.2）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cancel_job_marks_artifact_consumed(db_session, tree_client):
    """cancel 端点应同时把 ImportJob.artifact_id 关联的 artifact 标为 consumed。

    防止用户反复 cancel 同文件导致 token 累加存储（P2-4.2 回归防护）。
    """
    from app.models.dataset_models import (
        ImportJob, ImportArtifact, JobStatus, ArtifactStatus,
    )

    # 1. 建 artifact（status=active）
    artifact_id = uuid.uuid4()
    artifact = ImportArtifact(
        id=artifact_id,
        project_id=FAKE_PROJECT_ID,
        upload_token="test-token-cancel-" + uuid.uuid4().hex[:8],
        status=ArtifactStatus.active,
        storage_uri="local:///tmp/test",
        file_manifest=[],
        file_count=0,
        total_size_bytes=0,
    )
    db_session.add(artifact)

    # 2. 建关联 artifact 的 job（status=running 可 cancel）
    job_id = uuid.uuid4()
    job = ImportJob(
        id=job_id,
        project_id=FAKE_PROJECT_ID,
        artifact_id=artifact_id,
        year=YEAR,
        status=JobStatus.running,
        progress_pct=50,
        progress_message="进行中",
    )
    db_session.add(job)
    await db_session.commit()

    # 3. 调 cancel 端点
    resp = await tree_client.post(
        f"/api/projects/{FAKE_PROJECT_ID}/ledger-import/jobs/{job_id}/cancel",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json().get("data", resp.json())
    # 实际端点在 ledger_datasets.cancel_import_job（先注册拦截），返回含 status/message
    assert body.get("status") == "canceled" or body.get("message") == "作业已取消"

    # 4. 验证 job 已 canceled
    await db_session.refresh(job)
    assert job.status == JobStatus.canceled

    # 5. 验证 artifact 已 consumed（P2-4.2 核心断言）
    await db_session.refresh(artifact)
    assert artifact.status == ArtifactStatus.consumed, \
        f"artifact 应被标为 consumed，实际 {artifact.status}"


@pytest.mark.asyncio
async def test_cancel_job_without_artifact_still_works(db_session, tree_client):
    """job.artifact_id=NULL 的场景下 cancel 不应报错（早期 job 可能无 artifact）。"""
    from app.models.dataset_models import ImportJob, JobStatus

    job_id = uuid.uuid4()
    job = ImportJob(
        id=job_id,
        project_id=FAKE_PROJECT_ID,
        artifact_id=None,  # 无 artifact
        year=YEAR,
        status=JobStatus.running,
        progress_pct=10,
    )
    db_session.add(job)
    await db_session.commit()

    resp = await tree_client.post(
        f"/api/projects/{FAKE_PROJECT_ID}/ledger-import/jobs/{job_id}/cancel",
    )
    assert resp.status_code == 200
    await db_session.refresh(job)
    assert job.status == JobStatus.canceled



# ═══════════════════════════════════════════════════════════════════════════
# P1-Q1: ImportJob 乐观锁（version 列）测试
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cancel_with_expected_version_matches(db_session, tree_client):
    """expected_version 匹配当前版本 → 允许 cancel + version 自增。"""
    from app.models.dataset_models import ImportJob, JobStatus

    job_id = uuid.uuid4()
    job = ImportJob(
        id=job_id, project_id=FAKE_PROJECT_ID, year=YEAR,
        status=JobStatus.running, progress_pct=30, version=5,
    )
    db_session.add(job)
    await db_session.commit()

    resp = await tree_client.post(
        f"/api/projects/{FAKE_PROJECT_ID}/ledger-import/jobs/{job_id}/cancel",
        params={"expected_version": 5},
    )
    assert resp.status_code == 200, resp.text
    await db_session.refresh(job)
    assert job.status == JobStatus.canceled
    # version 自增
    assert job.version == 6


@pytest.mark.asyncio
async def test_cancel_with_wrong_version_returns_409(db_session, tree_client):
    """expected_version 不匹配 → 返回 409。"""
    from app.models.dataset_models import ImportJob, JobStatus

    job_id = uuid.uuid4()
    job = ImportJob(
        id=job_id, project_id=FAKE_PROJECT_ID, year=YEAR,
        status=JobStatus.running, progress_pct=30, version=7,
    )
    db_session.add(job)
    await db_session.commit()

    resp = await tree_client.post(
        f"/api/projects/{FAKE_PROJECT_ID}/ledger-import/jobs/{job_id}/cancel",
        params={"expected_version": 3},  # 错误
    )
    assert resp.status_code == 409
    # job 应保持 running 状态未改变
    await db_session.refresh(job)
    assert job.status == JobStatus.running
    assert job.version == 7


@pytest.mark.asyncio
async def test_cancel_without_expected_version_backward_compat(db_session, tree_client):
    """不传 expected_version 保持向后兼容。"""
    from app.models.dataset_models import ImportJob, JobStatus

    job_id = uuid.uuid4()
    job = ImportJob(
        id=job_id, project_id=FAKE_PROJECT_ID, year=YEAR,
        status=JobStatus.running, progress_pct=30, version=10,
    )
    db_session.add(job)
    await db_session.commit()

    resp = await tree_client.post(
        f"/api/projects/{FAKE_PROJECT_ID}/ledger-import/jobs/{job_id}/cancel",
    )
    assert resp.status_code == 200
    await db_session.refresh(job)
    assert job.status == JobStatus.canceled
    assert job.version == 11  # 仍会自增（由 cancel 端点主动加）
