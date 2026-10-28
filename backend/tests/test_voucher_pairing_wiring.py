"""配对结果接入抽凭补全、凭证穿透与下钻（spec voucher-identity-writeback-and-audit-phase 任务 7，需求 3.7）。

SQLite 真 ORM 行（四川物流 FY-0012 + 同日同号的 ZZ-0003）：

- 抽凭补全 enrich_voucher_context：每条样本带 ``pairing``，旧字段对方科目按配对结果给（管理费用
  对贷方应付职工薪酬，不再是「多科目」）；源数据已带对方科目的不改；
- 凭证穿透端点（挂凭回拉走同一端点）与下钻服务返回与 pair_voucher 逐条相同的配对结果。
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import TbLedger
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User
from app.services.drilldown_service import DrilldownService
from app.services.ledger_sampling_service import _ledger_row_to_item, enrich_voucher_context
from app.services.voucher_identity import annotate_lines
from app.services.voucher_pairing import pair_voucher

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

REAL = json.loads((Path(__file__).parent / "fixtures" / "voucher_real_ledger_vectors.json")
                  .read_text(encoding="utf-8"))["vouchers"]
FY12, ZZ03 = REAL["fy0012_many_to_many"], REAL["zz0003_same_day_same_no"]
USER, PROJECT, YEAR = uuid.uuid4(), uuid.uuid4(), 2025
PAYROLL = "2211.01.99.04"


def _amount(v):
    return Decimal(v) if v not in (None, "") else None


def _row(x: dict, **over) -> TbLedger:
    x = {**x, **over}
    return TbLedger(
        id=uuid.uuid4(), project_id=PROJECT, year=YEAR, company_code=x["company_code"],
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
        session.add(User(id=USER, username="pair", email="pair@test.com", hashed_password="x", role="member"))
        session.add(Project(id=PROJECT, name="配对接入测试", client_name="测试", project_type=ProjectType.annual,
                            status=ProjectStatus.execution, created_by=USER))
        session.add(ProjectUser(project_id=PROJECT, user_id=USER, role="auditor", permission_level="edit",
                                is_deleted=False))
        session.add_all([_row(x) for x in FY12])
        # 同日同号别凭证字：配对按凭证键取整张凭证，不能把它并进 FY-0012
        session.add_all([_row(x, voucher_date="2025-01-20", voucher_no="0012") for x in ZZ03])
        await session.commit()
        yield session
    await engine.dispose()


async def _fy12_items(db) -> list[dict]:
    rows = (await db.execute(sa.select(TbLedger).where(TbLedger.voucher_type == "FY")
                             .order_by(TbLedger.account_code, TbLedger.credit_amount))).scalars().all()
    return [_ledger_row_to_item(r) for r in rows]


def _expected() -> dict:
    """pair_voucher 直接算出的 FY-0012 配对结果：(借贷栏, 科目, 金额) → 结果。"""
    rows = annotate_lines([dict(x) for x in FY12])
    result = pair_voucher(rows)
    return {(r["side"], r["account_code"], Decimal(r["debit_amount"] or r["credit_amount"])): result[r["line_fp"]]
            for r in rows}


def _key(item: dict) -> tuple:
    amount = item["debit_amount"] if item["side"] == "D" else item["credit_amount"]
    return item["side"], item["account_code"], Decimal(str(amount))


async def test_enrich_attaches_pairing_and_derives_counterpart_from_it(db):
    items = await _fy12_items(db)
    await enrich_voucher_context(db, PROJECT, YEAR, items)
    expected = _expected()
    assert len(items) == 5
    for it in items:
        assert it["pairing"] == expected[_key(it)], it["account_code"]
        assert len(it["voucher_entries"]) == 5, "按凭证键取整张凭证，同日同号的 ZZ 不并进来"
    by_key = {_key(it): it for it in items}
    assert by_key[("D", "6602.01.99", Decimal("3680"))]["counterpart_account"] == PAYROLL  # 以前是「多科目」
    assert by_key[("D", PAYROLL, Decimal("3680"))]["counterpart_account"] == "1002"
    assert by_key[("C", "1002", Decimal("2000"))]["counterpart_account"] == PAYROLL
    assert by_key[("C", PAYROLL, Decimal("3680"))]["counterpart_account_name"] == "管理费用_职工薪酬_其他"


async def test_enrich_omits_whole_voucher_for_large_vouchers(db):
    """超过配对上限的大凭证：样本不带整张分录（同一凭证抽中几笔就会重复几份），只留对侧汇总与行数。"""
    from app.services.voucher_pairing import LINE_LIMIT

    big = [dict(FY12[0], voucher_type="DA", voucher_no="9001", account_code="1002", debit_amount="1",
                credit_amount=None) for _ in range(LINE_LIMIT)]
    # 对侧两个科目：只有一个对方科目时按科目整体配上（single_account），不是 large
    big += [dict(FY12[0], voucher_type="DA", voucher_no="9001", account_code=code,
                 debit_amount=None, credit_amount=str(LINE_LIMIT // 2)) for code in ("2202", "2203")]
    db.add_all([_row(x) for x in big])
    await db.flush()
    rows = (await db.execute(sa.select(TbLedger).where(TbLedger.voucher_type == "DA")
                             .order_by(TbLedger.account_code).limit(2))).scalars().all()
    items = [_ledger_row_to_item(r) for r in rows]
    small = await _fy12_items(db)
    await enrich_voucher_context(db, PROJECT, YEAR, items + small)
    for it in items:
        assert it["voucher_entries"] == [] and it["voucher_entries_omitted"] is True
        assert it["voucher_line_count"] == LINE_LIMIT + 2
        assert it["pairing"]["status"] == "large" and it["pairing"]["counterpart_summary"]
        assert it["line_fp"]
    assert all(len(it["voucher_entries"]) == 5 and "voucher_entries_omitted" not in it for it in small)


async def test_enrich_keeps_counterpart_given_by_source(db):
    items = await _fy12_items(db)
    items[0]["counterpart_account"] = "源数据对方科目"
    await enrich_voucher_context(db, PROJECT, YEAR, items)
    assert items[0]["counterpart_account"] == "源数据对方科目"
    assert items[0]["pairing"]["status"] == "paired"


async def test_penetration_endpoint_returns_same_pairing(db):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import ledger_penetration

    app = FastAPI()
    app.include_router(ledger_penetration.router)

    class _User:
        id = USER

        class role:  # noqa: N801
            value = "member"

    async def _db():
        yield db

    async def _user():
        return _User()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/projects/{PROJECT}/ledger/voucher/0012",
                           params={"year": YEAR, "voucher_date": "2025-01-20", "voucher_type": "FY"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["data"] if isinstance(body, dict) and "data" in body else body
    expected = _expected()
    assert len(rows) == 5
    for r in rows:
        assert r["pairing"] == expected[_key(r)]


async def test_drilldown_voucher_detail_returns_same_pairing(db):
    detail = await DrilldownService(db).get_voucher_detail(
        PROJECT, YEAR, "0012", voucher_date="2025-01-20", voucher_type="FY")
    expected = _expected()
    assert len(detail["entries"]) == 5
    for e in detail["entries"]:
        side = e["side"]
        amount = e["debit_amount"] if side == "D" else e["credit_amount"]
        assert e["pairing"] == expected[(side, e["account_code"], amount)]
