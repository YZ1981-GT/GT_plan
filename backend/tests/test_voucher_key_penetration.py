"""凭证穿透与下钻按凭证键定位（spec voucher-identity-writeback-and-audit-phase 任务 4，需求 2.1）。

SQLite 真 ORM 行 + 端点级请求（httpx ASGI，覆盖内层 get_db / get_current_user，让真实鉴权判定跑）：
- 只给日期与号、同日同号两种凭证字 → 409 VOUCHER_KEY_AMBIGUOUS + 2 个候选，不合并分录；
- 带凭证字 → 只返回本凭证分录，每行带 voucher_key / side / line_fp；
- 只给号、跨日期 → 409 + 全部候选（按凭证键排序）；空凭证字匹配 NULL；
- 下钻 /drilldown/voucher/{no} 同口径，is_balanced 只对单张凭证计算。
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import TbLedger
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User
from app.services.drilldown_service import DrilldownService
from app.services.ledger_penetration_service import LedgerPenetrationService
from app.services.voucher_identity import (
    AMBIGUOUS_CANDIDATE_LIMIT,
    VoucherKey,
    VoucherKeyAmbiguous,
    fingerprint_lines,
    single_voucher_lines,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

REAL = json.loads((Path(__file__).parent / "fixtures" / "voucher_real_ledger_vectors.json").read_text(encoding="utf-8"))["vouchers"]
USER_ID, PROJECT_ID, YEAR = uuid.uuid4(), uuid.uuid4(), 2025
FY, ZZ = REAL["fy0003_same_day_same_no"], REAL["zz0003_same_day_same_no"]
COMPANY = FY[0]["company_code"]


def _amount(v):
    return Decimal(v) if v not in (None, "") else None


def _row(x: dict, **over) -> TbLedger:
    x = {**x, **over}
    return TbLedger(
        project_id=PROJECT_ID, year=YEAR, company_code=x["company_code"],
        voucher_date=date.fromisoformat(x["voucher_date"]), voucher_type=x["voucher_type"],
        voucher_no=x["voucher_no"], account_code=x["account_code"], account_name=x.get("account_name"),
        debit_amount=_amount(x["debit_amount"]), credit_amount=_amount(x["credit_amount"]), summary=x.get("summary"),
    )


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=USER_ID, username="vk", email="vk@test.com", hashed_password="x", role="member"))
        session.add(Project(id=PROJECT_ID, name="凭证键穿透测试", client_name="测试", project_type=ProjectType.annual,
                            status=ProjectStatus.execution, created_by=USER_ID))
        session.add(ProjectUser(project_id=PROJECT_ID, user_id=USER_ID, role="auditor", permission_level="edit",
                                is_deleted=False))
        session.add_all([_row(x) for x in FY + ZZ])
        # 同号别日（ZZ），以及凭证字为空的一张
        session.add_all([_row(x, voucher_date="2025-02-07") for x in ZZ[:2]])
        session.add_all([_row(x, voucher_no="0046", voucher_type=None) for x in FY])
        await session.commit()
        yield session
    await engine.dispose()


# ─── 服务层 ────────────────────────────────────────────────────────────────────


async def test_date_and_no_with_two_types_is_ambiguous(db):
    svc = LedgerPenetrationService(db)
    with pytest.raises(VoucherKeyAmbiguous) as ei:
        await svc.get_voucher_entries(PROJECT_ID, YEAR, "0003", voucher_date="2025-01-07")
    cands = ei.value.candidates
    assert [(c["voucher_date"], c["voucher_type"], c["line_count"]) for c in cands] == [
        ("2025-01-07", "FY", 2), ("2025-01-07", "ZZ", 3)]
    assert cands[0]["debit_total"] == "100000.00" and cands[1]["debit_total"] == "67401.16"
    assert all(c["company_code"] == COMPANY for c in cands)
    assert ei.value.status_code == 409
    assert ei.value.detail["error_code"] == "VOUCHER_KEY_AMBIGUOUS" and ei.value.detail["truncated"] is False


async def test_with_voucher_type_returns_only_that_voucher(db):
    svc = LedgerPenetrationService(db)
    rows = await svc.get_voucher_entries(PROJECT_ID, YEAR, "0003", voucher_date="2025-01-07", voucher_type="ZZ")
    assert len(rows) == 3
    vk = VoucherKey.of(year=YEAR, company_code=COMPANY, voucher_date="2025-01-07", voucher_type="ZZ", voucher_no="0003")
    assert {r["voucher_key"] for r in rows} == {vk.to_str()}
    assert [r["side"] for r in rows] == ["D", "C", "C"]
    assert [r["line_fp"] for r in rows] == fingerprint_lines(rows)
    assert len({r["line_fp"] for r in rows}) == 3
    assert all("extra_fields" in r for r in rows)


async def test_number_only_spanning_dates_lists_every_voucher(db):
    svc = LedgerPenetrationService(db)
    with pytest.raises(VoucherKeyAmbiguous) as ei:
        await svc.get_voucher_entries(PROJECT_ID, YEAR, "0003")
    assert [(c["voucher_date"], c["voucher_type"]) for c in ei.value.candidates] == [
        ("2025-01-07", "FY"), ("2025-01-07", "ZZ"), ("2025-02-07", "ZZ")]
    # 月份 + 凭证字能唯一定位
    rows = await svc.get_voucher_entries(PROJECT_ID, YEAR, "0003", month=2, voucher_type="ZZ")
    assert len(rows) == 2 and {r["voucher_date"] for r in rows} == {date(2025, 2, 7)}


async def test_empty_voucher_type_matches_null(db):
    svc = LedgerPenetrationService(db)
    rows = await svc.get_voucher_entries(PROJECT_ID, YEAR, "0046", voucher_type="")
    assert len(rows) == 2 and all(r["voucher_type"] is None for r in rows)
    assert await svc.get_voucher_entries(PROJECT_ID, YEAR, "0046", voucher_type="FY") == []
    assert len(await svc.get_voucher_entries(PROJECT_ID, YEAR, "0046")) == 2


async def test_drilldown_same_rules(db):
    svc = DrilldownService(db)
    with pytest.raises(VoucherKeyAmbiguous):
        await svc.get_voucher_detail(PROJECT_ID, YEAR, "0003", voucher_date="2025-01-07")
    got = await svc.get_voucher_detail(PROJECT_ID, YEAR, "0003", voucher_date="2025-01-07", voucher_type="FY")
    assert got["voucher_type"] == "FY" and got["is_balanced"] is True
    assert got["total_debit"] == Decimal("100000.00") and len(got["entries"]) == 2
    assert {e["side"] for e in got["entries"]} == {"D", "C"} and all(e["line_fp"] for e in got["entries"])
    assert got["voucher_key"] == VoucherKey.from_row(FY[0]).to_str()
    empty = await svc.get_voucher_detail(PROJECT_ID, YEAR, "9999")
    assert empty["entries"] == [] and empty["voucher_key"] is None


def test_candidate_list_is_capped():
    rows = [{"year": 2025, "company_code": "001", "voucher_date": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}",
             "voucher_type": "记", "voucher_no": "7", "debit_amount": "1", "credit_amount": None} for i in range(60)]
    with pytest.raises(VoucherKeyAmbiguous) as ei:
        single_voucher_lines(rows)
    assert len(ei.value.candidates) == AMBIGUOUS_CANDIDATE_LIMIT
    assert ei.value.detail["truncated"] is True and "60 张凭证" in ei.value.detail["message"]
    assert single_voucher_lines(rows[:1]) == rows[:1] and single_voucher_lines([]) == []


# ─── 端点级 ────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(db):
    import fakeredis.aioredis
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.deps import get_current_user
    from app.main import app

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    class _User:
        id = USER_ID

        class _Role:
            value = "member"

        role = _Role()

    async def _db():
        yield db

    async def _redis():
        yield fake_redis

    async def _user():
        return _User()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _redis
    app.dependency_overrides[get_current_user] = _user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("path", ["ledger/voucher/0003", "drilldown/voucher/0003"])
async def test_endpoint_409_then_200_with_voucher_type(client, path):
    url = f"/api/projects/{PROJECT_ID}/{path}"
    resp = await client.get(url, params={"year": YEAR, "voucher_date": "2025-01-07"})
    assert resp.status_code == 409
    body = resp.json()["message"]
    assert body["error_code"] == "VOUCHER_KEY_AMBIGUOUS"
    assert [c["voucher_type"] for c in body["candidates"]] == ["FY", "ZZ"]

    resp = await client.get(url, params={"year": YEAR, "voucher_date": "2025-01-07", "voucher_type": "FY"})
    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())
    lines = data if isinstance(data, list) else data["entries"]
    assert len(lines) == 2 and all(x["line_fp"] for x in lines)


async def test_endpoint_requires_project_membership(client, db):
    from app.deps import get_current_user
    from app.main import app

    class _Stranger:
        id = uuid.uuid4()

        class _Role:
            value = "member"

        role = _Role()

    async def _stranger():
        return _Stranger()

    app.dependency_overrides[get_current_user] = _stranger
    resp = await client.get(f"/api/projects/{PROJECT_ID}/ledger/voucher/0003",
                            params={"year": YEAR, "voucher_date": "2025-01-07", "voucher_type": "FY"})
    assert resp.status_code == 403
