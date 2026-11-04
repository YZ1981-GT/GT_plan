"""科目余额表 / 序时账人工修改（spec citar-table-manual-edit R3~R5），真发请求：

只替换身份、库（SQLite）与 Redis（None）；鉴权、service、试算表重算全部真实执行。
余额表：1122 应收账款（上级，方向列存法）= 112201 甲 300 + 112202 乙 200；1002 银行存款（无方向列，借正贷负）。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal as D

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_models import (  # noqa: E402
    AccountCategory, AccountChart, AccountDirection, AccountMapping, AccountSource, MappingType, TbBalance, TbLedger,
    TrialBalance,
)
from app.models.base import Base, PermissionLevel  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, ProjectUserRole, UserRole  # noqa: E402
from app.models.ledger_edit_models import LedgerManualEdit  # noqa: E402
from app.routers.ledger_edits import router  # noqa: E402
from app.routers.ledger_penetration import router as penetration_router  # noqa: E402

P = uuid.UUID("00000000-0000-0000-0000-00000000d101")
EDITOR = uuid.UUID("00000000-0000-0000-0000-00000000d001")
READER = uuid.UUID("00000000-0000-0000-0000-00000000d002")
YEAR = 2025
URL = f"/api/projects/{P}/ledger"
Y = {"year": YEAR}
IDS = {code: uuid.uuid4() for code in ("1122", "112201", "112202", "1002")}
ENTRY = uuid.uuid4()


class _Actor:
    def __init__(self, uid: uuid.UUID) -> None:
        self.id = uid
        self.role = UserRole.auditor
        self.username = f"u-{uid.hex[-4:]}"
        self.is_active = True


@pytest_asyncio.fixture
async def env() -> AsyncGenerator[dict, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add(Project(id=P, name="余额修改_2025", client_name="甲公司", project_type=ProjectType.annual,
                      status=ProjectStatus.execution, created_by=EDITOR))
        await s.flush()
        s.add(ProjectUser(project_id=P, user_id=EDITOR, role=ProjectUserRole.auditor, permission_level=PermissionLevel.edit))
        s.add(ProjectUser(project_id=P, user_id=READER, role=ProjectUserRole.auditor, permission_level=PermissionLevel.readonly))
        common = dict(project_id=P, year=YEAR, company_code="001")
        s.add(TbBalance(id=IDS["1122"], account_code="1122", account_name="应收账款", opening_balance=D(400), opening_direction="debit",
                        debit_amount=D(150), credit_amount=D(50), closing_balance=D(500), closing_direction="debit", **common))
        s.add(TbBalance(id=IDS["112201"], account_code="112201", account_name="甲", opening_balance=D(250), opening_direction="debit",
                        debit_amount=D(100), credit_amount=D(50), closing_balance=D(300), closing_direction="debit", **common))
        s.add(TbBalance(id=IDS["112202"], account_code="112202", account_name="乙", opening_balance=D(150), opening_direction="debit",
                        debit_amount=D(50), credit_amount=D(0), closing_balance=D(200), closing_direction="debit", **common))
        s.add(TbBalance(id=IDS["1002"], account_code="1002", account_name="银行存款", opening_balance=D(100),
                        debit_amount=D(0), credit_amount=D(0), closing_balance=D(100), **common))
        for code in ("1122", "1002"):
            s.add(AccountMapping(project_id=P, original_account_code=code, standard_account_code=code,
                                 mapping_type=MappingType.auto_exact, created_by=EDITOR))
            s.add(AccountChart(project_id=P, account_code=code, account_name=code, direction=AccountDirection.debit, level=1,
                               category=AccountCategory.asset, source=AccountSource.standard))
        s.add(TbLedger(id=ENTRY, voucher_date=__import__("datetime").date(2025, 3, 5), voucher_no="记-1", account_code="112201",
                       account_name="甲", debit_amount=D(100), credit_amount=D(0), summary="销售", accounting_period=3, **common))
        await s.commit()

    current = {"actor": _Actor(EDITOR)}
    app = FastAPI()
    app.include_router(router)
    app.include_router(penetration_router)

    async def _db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: current["actor"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"c": client, "f": factory, "as": lambda uid: current.update(actor=_Actor(uid)),
               "use": lambda actor: current.update(actor=actor)}
    await engine.dispose()


async def _bal(f) -> dict[str, TbBalance]:
    async with f() as s:
        return {r.account_code: r for r in (await s.execute(sa.select(TbBalance))).scalars()}


async def _tb(f, code: str) -> TrialBalance:
    async with f() as s:
        return (await s.execute(sa.select(TrialBalance).where(TrialBalance.standard_account_code == code))).scalar_one()


@pytest.mark.asyncio
async def test_edit_leaf_syncs_parent_recalcs_tb_and_restores(env):
    c, f = env["c"], env["f"]
    r = await c.put(f"{URL}/balance-rows/{IDS['112201']}", params=Y,
                    json={"values": {"opening": 250, "debit": 160, "credit": 50, "closing": 360}, "reason": "补记"})
    assert r.status_code == 200, r.text
    bal = await _bal(f)
    assert bal["112201"].closing_balance == D(360) and bal["112201"].debit_amount == D(160)
    assert bal["1122"].closing_balance == D(560) and bal["1122"].debit_amount == D(210)  # 上级同步
    assert (await _tb(f, "1122")).unadjusted_amount == D(560)                            # 试算表按新值重算

    edits = (await c.get(f"{URL}/manual-edits", params={**Y, "table": "balance"})).json()
    assert [e["row_id"] for e in edits] == [str(IDS["112201"])]
    assert edits[0]["original"]["closing_balance"] == "300.00" and edits[0]["reason"] == "补记"
    async with f() as s:
        actions = sorted(e.action for e in (await s.execute(sa.select(LedgerManualEdit))).scalars())
    assert actions == ["cascade", "edit"]

    # 余额接口带 id，合成行之外都有
    rows = (await c.get(f"{URL}/balance", params=Y)).json()
    assert {row["account_code"]: row["id"] for row in rows}["112201"] == str(IDS["112201"])

    restored = await c.post(f"{URL}/balance/{IDS['112201']}/restore", params=Y)
    assert restored.status_code == 200, restored.text
    bal = await _bal(f)
    assert bal["112201"].closing_balance == D(300) and bal["1122"].closing_balance == D(500)
    assert bal["1122"].debit_amount == D(150)
    assert (await _tb(f, "1122")).unadjusted_amount == D(500)
    assert (await c.get(f"{URL}/manual-edits", params={**Y, "table": "balance"})).json() == []
    assert (await c.post(f"{URL}/balance/{IDS['1002']}/restore", params=Y)).status_code == 404


@pytest.mark.asyncio
async def test_direction_flip_and_signed_storage(env):
    c, f = env["c"], env["f"]
    # 方向列存法：期末改成贷方 20 ⇒ 存 20 + credit；上级按差额 −320 同步
    assert (await c.put(f"{URL}/balance-rows/{IDS['112201']}", params=Y, json={"values": {"closing": -20}})).status_code == 200
    bal = await _bal(f)
    assert (bal["112201"].closing_balance, bal["112201"].closing_direction) == (D(20), "credit")
    assert (bal["1122"].closing_balance, bal["1122"].closing_direction) == (D(180), "debit")
    # 无方向列存法：存借正贷负
    assert (await c.put(f"{URL}/balance-rows/{IDS['1002']}", params=Y, json={"values": {"closing": -5}})).status_code == 200
    bal = await _bal(f)
    assert bal["1002"].closing_balance == D(-5) and bal["1002"].closing_direction is None


@pytest.mark.asyncio
async def test_rejects_parent_row_bad_values_and_readonly(env):
    c = env["c"]
    parent = await c.put(f"{URL}/balance-rows/{IDS['1122']}", params=Y, json={"values": {"closing": 1}})
    assert parent.status_code == 422 and "末级" in parent.text
    for bad in ({"closing": "abc"}, {"name": "x"}, {"closing": True}):
        assert (await c.put(f"{URL}/balance-rows/{IDS['112202']}", params=Y, json={"values": bad})).status_code == 422, bad
    assert (await c.put(f"{URL}/balance-rows/{uuid.uuid4()}", params=Y, json={"values": {"closing": 1}})).status_code == 404
    env["as"](READER)
    assert (await c.put(f"{URL}/balance-rows/{IDS['112202']}", params=Y, json={"values": {"closing": 1}})).status_code == 403
    assert (await c.get(f"{URL}/manual-edits/summary", params=Y)).status_code == 200


@pytest.mark.asyncio
async def test_ledger_entry_edit_and_restore(env):
    c, f = env["c"], env["f"]
    r = await c.put(f"{URL}/entries/{ENTRY}", params=Y, json={"values": {
        "voucher_date": "2025-04-30", "voucher_no": "记-9", "summary": "销售（更正）", "account_code": "112202",
        "account_name": "乙", "debit_amount": 120, "credit_amount": None,
    }})
    assert r.status_code == 200, r.text
    async with f() as s:
        e = (await s.execute(sa.select(TbLedger))).scalar_one()
    assert (e.voucher_no, e.account_code, e.debit_amount, e.accounting_period) == ("记-9", "112202", D(120), 4)
    assert (await _bal(f))["112201"].closing_balance == D(300)  # 不回写余额表
    assert (await c.get(f"{URL}/manual-edits/summary", params=Y)).json() == {"balance": 0, "ledger": 1}
    for bad in ({"voucher_no": " "}, {"voucher_date": "2025-13-01"}, {"id": "x"}):
        assert (await c.put(f"{URL}/entries/{ENTRY}", params=Y, json={"values": bad})).status_code == 422, bad
    assert (await c.post(f"{URL}/ledger/{ENTRY}/restore", params=Y)).status_code == 200
    async with f() as s:
        e = (await s.execute(sa.select(TbLedger).execution_options(populate_existing=True))).scalar_one()
    assert (e.voucher_no, e.account_code, e.debit_amount, e.summary, e.accounting_period) == ("记-1", "112201", D(100), "销售", 3)
    assert e.voucher_date.isoformat() == "2025-03-05"
    assert (await c.get(f"{URL}/manual-edits/summary", params=Y)).json() == {"balance": 0, "ledger": 0}


@pytest.mark.asyncio
async def test_account_without_manual_edit_cannot_edit_or_restore(env):
    """账号未开通「允许修改」：余额表 / 序时账的修改与恢复都 403，数据不动；查看照常（spec citar-manual-edit-permission R2）。"""
    c, f = env["c"], env["f"]
    assert (await c.put(f"{URL}/entries/{ENTRY}", params=Y, json={"values": {"summary": "改过"}})).status_code == 200
    locked = _Actor(EDITOR)
    locked.allow_manual_edit = False
    env["use"](locked)
    r = await c.put(f"{URL}/balance-rows/{IDS['112201']}", params=Y, json={"values": {"closing": 1}})
    assert r.status_code == 403 and "允许修改" in r.text
    assert (await c.put(f"{URL}/entries/{ENTRY}", params=Y, json={"values": {"summary": "再改"}})).status_code == 403
    assert (await c.post(f"{URL}/ledger/{ENTRY}/restore", params=Y)).status_code == 403
    assert (await c.get(f"{URL}/manual-edits/summary", params=Y)).json() == {"balance": 0, "ledger": 1}
    assert (await _bal(f))["112201"].closing_balance == D(300)
    async with f() as s:
        e = (await s.execute(sa.select(TbLedger).execution_options(populate_existing=True))).scalar_one()
    assert e.summary == "改过"
