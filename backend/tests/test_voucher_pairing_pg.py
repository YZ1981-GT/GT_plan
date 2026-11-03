"""多借多贷配对 × 真实账套（spec voucher-identity-writeback-and-audit-phase 任务 7，pg_only，只读）。

- 四川物流 FY-0012 经真实穿透服务：两笔银行付款配到应付职工薪酬、管理费用配到贷方应付职工薪酬（需求 3.8）；
- 四川物流整套账（2.2 万行、3,176 张凭证）逐张配对：配上的行对方金额合计 = 本行金额，指认到行的对方
  也把本行列为对方（第 6 步两条不变式在真实数据上从不违反），且有一对一、一对多、多对一各类结果。
"""

from __future__ import annotations

import uuid
from collections import Counter
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.audit_platform_models import TbLedger
from app.services.dataset_query import get_active_filter
from app.services.ledger_penetration_service import LedgerPenetrationService
from app.services.voucher_identity import annotate_lines, group_by_voucher_key
from app.services.voucher_pairing import pair_voucher

pytestmark = pytest.mark.pg_only

SICHUAN = uuid.UUID("f4b778ad-23b3-49ab-b3c8-ee62a5f82226")
YEAR = 2025
PAYROLL = "2211.01.99.04"


@pytest.fixture
async def pg():
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        pytest.skip("需要真实 PostgreSQL")
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            n = (await session.execute(sa.text("SELECT count(*) FROM tb_ledger WHERE project_id = :p AND year = :y "
                                               "AND NOT is_deleted"), {"p": SICHUAN, "y": YEAR})).scalar()
            if not n:
                pytest.skip("四川物流 2025 序时账不可用（数据依赖）")
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await engine.dispose()


async def test_fy0012_pairs_on_real_penetration(pg):
    rows = await LedgerPenetrationService(pg).get_voucher_entries(
        SICHUAN, YEAR, "0012", voucher_date="2025-01-20", voucher_type="FY")
    view = {}
    for r in rows:
        amount = r["debit_amount"] if r["side"] == "D" else r["credit_amount"]
        p = r["pairing"]
        view[(r["side"], r["account_code"], Decimal(str(amount)))] = (
            p["status"], p["basis"], sorted((c["account_code"], c["amount"]) for c in p["counterparts"]))
    assert view[("D", PAYROLL, Decimal("3680"))] == ("paired", "one_to_many", [("1002", "1680.00"), ("1002", "2000.00")])
    assert view[("C", "1002", Decimal("2000"))] == ("paired", "many_to_one", [(PAYROLL, "2000.00")])
    assert view[("C", "1002", Decimal("1680"))] == ("paired", "many_to_one", [(PAYROLL, "1680.00")])
    assert view[("D", "6602.01.99", Decimal("3680"))] == ("paired", "one_to_one", [(PAYROLL, "3680.00")])


async def test_whole_ledger_pairing_never_breaks_invariants(pg):
    tbl = TbLedger.__table__
    stmt = sa.select(
        tbl.c.id, tbl.c.year, tbl.c.company_code, tbl.c.voucher_date, tbl.c.voucher_type, tbl.c.voucher_no,
        tbl.c.account_code, tbl.c.account_name, tbl.c.debit_amount, tbl.c.credit_amount, tbl.c.summary,
    ).where(await get_active_filter(pg, tbl, SICHUAN, YEAR))
    rows = [dict(r) for r in (await pg.execute(stmt)).mappings()]
    status, basis, broken = Counter(), Counter(), []
    for vk, lines in group_by_voucher_key(rows, year=YEAR).items():
        annotate_lines(lines, year=YEAR)
        result = pair_voucher(lines)
        assert set(result) == {ln["line_fp"] for ln in lines}
        own = {ln["line_fp"]: Decimal(str(ln["debit_amount"] if ln["side"] == "D" else ln["credit_amount"] or 0))
               for ln in lines}
        for fp, p in result.items():
            status[p["status"]] += 1
            if p["status"] != "paired":
                continue
            basis[p["basis"]] += 1
            if sum(Decimal(c["amount"]) for c in p["counterparts"]) != own[fp]:
                broken.append(("金额合计", vk.to_str(), fp))
            for c in p["counterparts"]:
                if c["line_fp"] and fp not in {x["line_fp"] for x in result[c["line_fp"]]["counterparts"]}:
                    broken.append(("对方未回指", vk.to_str(), fp))
    assert broken == []
    assert sum(status.values()) == len(rows)
    assert status["paired"] > len(rows) * 0.6, status  # 2026-10-27 现算 18,692 / 22,716
    assert {"one_to_one", "single_side", "single_account", "one_to_many", "many_to_one"} <= set(basis), basis
