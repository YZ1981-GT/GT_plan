"""税审底稿接口（真发请求；spec tax-workpaper-data-fetch R6 / R7）。

只替换 ``get_current_user``（按请求切换身份）与 ``get_db``（SQLite 内存库），
鉴权（``require_project_access``）、service、计算模型、取数全部真实执行。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_models import (  # noqa: E402
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountMapping,
    AccountSource,
    TbBalance,
)
from app.models.base import Base, PermissionLevel  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, ProjectUserRole, User, UserRole  # noqa: E402
from app.models.tax_workpaper_models import TaxWorkpaperInput  # noqa: E402
from app.routers.tax_workpapers import router  # noqa: E402

P = uuid.UUID("00000000-0000-0000-0000-00000000a101")
EDITOR = uuid.UUID("00000000-0000-0000-0000-00000000a001")
READER = uuid.UUID("00000000-0000-0000-0000-00000000a002")
OUTSIDER = uuid.UUID("00000000-0000-0000-0000-00000000a003")
YEAR = 2025
URL = f"/api/projects/{P}/tax-workpapers"


class _Actor:
    def __init__(self, uid: uuid.UUID, role: UserRole = UserRole.auditor) -> None:
        self.id = uid
        self.role = role
        self.username = f"u-{uid.hex[-4:]}"
        self.is_active = True


ACTORS = {"editor": _Actor(EDITOR), "reader": _Actor(READER), "outsider": _Actor(OUTSIDER)}
_TABLES = [User.__table__, Project.__table__, ProjectUser.__table__, TbBalance.__table__,
           AccountMapping.__table__, AccountChart.__table__, TaxWorkpaperInput.__table__]


@pytest_asyncio.fixture
async def env() -> AsyncGenerator[dict, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add(Project(id=P, name="项目P", client_name="甲公司", project_type=ProjectType.annual,
                      status=ProjectStatus.execution, created_by=EDITOR))
        await s.flush()
        s.add(ProjectUser(project_id=P, user_id=EDITOR, role=ProjectUserRole.auditor, permission_level=PermissionLevel.edit))
        s.add(ProjectUser(project_id=P, user_id=READER, role=ProjectUserRole.auditor, permission_level=PermissionLevel.readonly))
        # 其他业务收入：出租固定资产收入 1,000 / 租金 200（「其中」明细；租金下再挂一个三级科目）
        for code, name, cr in (("6051", "其他业务收入", 1200), ("605101", "出租固定资产收入", 1000), ("605102", "租金", 200),
                               ("60510201", "某甲", 200)):
            s.add(TbBalance(project_id=P, year=YEAR, company_code="001", account_code=code, account_name=name,
                            credit_amount=cr, debit_amount=cr))
        s.add(AccountMapping(project_id=P, original_account_code="6051", standard_account_code="6051",
                             mapping_type="manual"))
        # 库存现金：有余额、税审底稿不取（底稿映射页「未进底稿」）
        s.add(TbBalance(project_id=P, year=YEAR, company_code="001", account_code="1001", account_name="库存现金",
                        closing_balance=100, closing_direction="debit"))
        # 主营业务成本没有明细：2-04 按「销售商品」等明细取数取不到（底稿映射页「规则指向、未取到」）
        s.add(TbBalance(project_id=P, year=YEAR, company_code="001", account_code="6401", account_name="主营业务成本",
                        debit_amount=500, credit_amount=500))
        s.add(AccountMapping(project_id=P, original_account_code="6401", standard_account_code="6401",
                             mapping_type="manual"))
        s.add(AccountChart(project_id=P, account_code="6051", account_name="其他业务收入",
                           direction=AccountDirection.credit, level=1, category=AccountCategory.revenue,
                           source=AccountSource.standard))
        await s.commit()

    current = {"actor": ACTORS["editor"]}
    app = FastAPI()
    app.include_router(router)

    async def _db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: current["actor"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"client": client, "as": lambda k: current.update(actor=ACTORS[k])}
    await engine.dispose()


def _values(body: dict) -> dict:
    return body["parts"][0]["values"]


@pytest.mark.asyncio
async def test_get_sheet_fetches_and_computes(env):
    r = await env["client"].get(f"{URL}/sheets/2-02", params={"year": YEAR})
    assert r.status_code == 200, r.text
    v = _values(r.json())
    assert v["D10"] == {"n": "1000"}            # 取数：出租固定资产收入贷方发生额
    assert v["C14"] == {"s": "租金"}             # 「其中」明细名称
    assert v["G10"] == {"n": "1000"}            # 公式 =D10+F10-E10
    assert v["C4"] == {"s": "甲公司"}            # 表头：被审核单位 = 客户名称
    cells = r.json()["parts"][0]["cells"]
    assert cells["D10"]["status"] == "auto" and "出租固定资产收入" in cells["D10"]["rule"]
    assert cells["D9"]["status"] == "manual"


@pytest.mark.asyncio
async def test_save_input_overrides_and_recomputes(env):
    c = env["client"]
    r = await c.put(f"{URL}/sheets/2-02", params={"year": YEAR},
                    json={"version": 0, "inputs": {"2-02": {"D10": 1500, "F10": 100}}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 1
    assert _values(body)["G10"] == {"n": "1600"}
    assert body["parts"][0]["cells"]["D10"]["origin"] == "input"
    assert body["parts"][0]["cells"]["D10"]["auto"] == {"n": "1000"}
    # 刷新读回
    again = await c.get(f"{URL}/sheets/2-02", params={"year": YEAR})
    assert _values(again.json())["D10"] == {"n": "1500"}


@pytest.mark.asyncio
async def test_stale_version_conflicts(env):
    c = env["client"]
    ok = await c.put(f"{URL}/sheets/2-02", params={"year": YEAR}, json={"version": 0, "inputs": {"2-02": {"F10": 1}}})
    assert ok.status_code == 200
    stale = await c.put(f"{URL}/sheets/2-02", params={"year": YEAR}, json={"version": 0, "inputs": {"2-02": {"F10": 2}}})
    assert stale.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("inputs, fragment", [
    ({"2-02": {"G10": 5}}, "公式格"),
    ({"2-02": {"Z999": 5}}, "范围"),
    ({"2-03": {"D8": 5}}, "不属于"),
    ({"2-02": {"F10": {"x": 1}}}, "数字、文字"),
])
async def test_invalid_inputs_rejected(env, inputs, fragment):
    r = await env["client"].put(f"{URL}/sheets/2-02", params={"year": YEAR}, json={"version": 0, "inputs": inputs})
    assert r.status_code == 422
    assert fragment in r.text


@pytest.mark.asyncio
async def test_params_default_and_save(env):
    c = env["client"]
    r = await c.get(f"{URL}/params", params={"year": YEAR})
    params = {p["ref"]: p for p in r.json()["params"]}
    assert params["B1"]["value"] == "甲公司" and params["B10"]["value"] == "2025年度"
    saved = await c.put(f"{URL}/params", params={"year": YEAR}, json={"version": 0, "values": {"B11": "张三"}})
    assert saved.status_code == 200
    sheet = await c.get(f"{URL}/sheets/2-02", params={"year": YEAR})
    assert _values(sheet.json())["F4"] == {"s": "张三"}   # 编制人
    bad = await c.put(f"{URL}/params", params={"year": YEAR}, json={"version": 1, "values": {"B99": "x"}})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_authorization(env):
    c = env["client"]
    env["as"]("reader")
    assert (await c.get(f"{URL}/sheets/2-02", params={"year": YEAR})).status_code == 200
    put = await c.put(f"{URL}/sheets/2-02", params={"year": YEAR}, json={"version": 0, "inputs": {}})
    assert put.status_code == 403
    assert (await c.put(f"{URL}/params", params={"year": YEAR}, json={"version": 0, "values": {}})).status_code == 403
    env["as"]("outsider")
    assert (await c.get(f"{URL}/sheets/2-02", params={"year": YEAR})).status_code == 403
    assert (await c.get(f"{URL}/params", params={"year": YEAR})).status_code == 403


@pytest.mark.asyncio
async def test_unknown_code_404(env):
    r = await env["client"].get(f"{URL}/sheets/9-99", params={"year": YEAR})
    assert r.status_code == 404


# ── 底稿映射页「科目 → 税审底稿」（spec citar-account-workpaper-map） ──
@pytest.mark.asyncio
async def test_account_map_lists_workpapers_via_parent_and_child(env):
    r = await env["client"].get(f"{URL}/account-map", params={"year": YEAR})
    assert r.status_code == 200, r.text
    body = r.json()
    rows = {a["code"]: a for a in body["accounts"]}
    assert list(rows) == ["1001", "6051", "605101", "605102", "60510201", "6401"]
    # 明细被 2-02 直接取数；上级 6051 因下级进入同一张底稿
    assert rows["605101"]["direct"] == ["2-02"] and rows["605101"]["workpapers"] == ["2-02"]
    assert rows["605102"]["direct"] == ["2-02"] and rows["605102"]["workpapers"] == ["2-02"]
    assert rows["6051"]["direct"] == [] and rows["6051"]["workpapers"] == ["2-02"]
    # 三级科目：「其中」明细取的是它的上级「租金」⇒ 经上级进入同一张底稿
    assert rows["60510201"]["direct"] == [] and rows["60510201"]["workpapers"] == ["2-02"]
    assert rows["605101"]["level"] == 2 and rows["605101"]["parent"] == "6051"
    # 标准科目：明细沿用上级的映射，名称取本项目标准科目表
    assert rows["605101"]["standard_code"] == "6051" and rows["605101"]["standard_name"] == "其他业务收入"
    assert rows["605101"]["credit"] == "1000"
    # 库存现金：有余额、税审底稿不取，标准科目未映射
    cash = rows["1001"]
    assert cash["workpapers"] == [] and cash["pending"] == [] and cash["has_activity"] is True
    assert cash["standard_code"] is None and cash["closing"] == "100"
    assert rows["605101"]["pending"] == []  # 已取到的底稿不重复列为「未取到」
    # 主营业务成本：规则指向 2-04 但没有明细可取 ⇒ 未取到 + 原因
    cost = rows["6401"]
    assert cost["workpapers"] == []
    assert [p["code"] for p in cost["pending"]] == ["2-04"]
    assert any("销售商品" in reason for reason in cost["pending"][0]["reasons"])
    assert body["notices"] == []


@pytest.mark.asyncio
async def test_account_map_authorization(env):
    c = env["client"]
    env["as"]("reader")
    assert (await c.get(f"{URL}/account-map", params={"year": YEAR})).status_code == 200
    env["as"]("outsider")
    assert (await c.get(f"{URL}/account-map", params={"year": YEAR})).status_code == 403


@pytest.mark.asyncio
async def test_account_map_ignores_rules_outside_workpaper_domain(env, monkeypatch):
    """申报表 / 审核说明上的取数规则不算「进入税审底稿」（底稿映射页只列税审底稿，点开的也是税审底稿页）。"""
    import copy
    import json

    from app.services import tax_workpaper_service as svc
    from app.services.tax_workbook import MODEL_PATH, TaxWorkbook

    model = copy.deepcopy(json.loads(MODEL_PATH.read_text(encoding="utf-8")))
    tax_return_code = model["groups"]["tax_return"][0]
    model["rules"].append({"sheet": model["codes"][tax_return_code][0], "ref": "ZZ999", "rule": "测试", "status": "auto",
                           "op": "amount", "path": ["其他业务收入", "出租固定资产收入"], "measure": "credit"})
    wb = TaxWorkbook(model)
    monkeypatch.setattr(svc, "load_workbook", lambda: wb)
    r = await env["client"].get(f"{URL}/account-map", params={"year": YEAR})
    rows = {a["code"]: a for a in r.json()["accounts"]}
    assert rows["605101"]["direct"] == ["2-02"], rows["605101"]


def test_rule_workpaper_codes_exist_in_frontend_index():
    """规则里出现的底稿编号必须都在前端底稿目录里（底稿映射页按目录显示表名、点开底稿）。"""
    import re
    from pathlib import Path

    from app.services.tax_workbook import load_workbook
    from app.services.tax_workpaper_service import WORKPAPER_DOMAIN, code_domain

    wb = load_workbook()
    sheet_code = {s: c for c, sheets in wb.codes.items() for s in sheets}
    rule_codes = {sheet_code[item["sheet"]] for item in wb.model["rules"]
                  if code_domain(wb, sheet_code[item["sheet"]]) == WORKPAPER_DOMAIN}
    index_ts = (Path(__file__).resolve().parents[2] / "audit-platform/frontend/src/views/tax-workpapers/taxWorkpaperIndex.ts")
    index_codes = set(re.findall(r"code: '([^']+)'", index_ts.read_text(encoding="utf-8")))
    assert len(rule_codes) >= 30  # 判据抽不到值时不空转
    assert rule_codes <= index_codes, sorted(rule_codes - index_codes)
