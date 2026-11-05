"""单体财务报表单元格来源（spec citar-cell-source-hover R5.6，design §7）。

复用 ``test_tax_assurance_api`` 的夹具（企业会计制度格式、七个标准科目）。判据：线性格构成之和 = 页面同一份报表的格值；
取数行拆到标准科目、合计行拆到引用行（链接本页格子）、手工值带自动值；接口项目只读鉴权。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.cell_source.fs import fs_sources
from app.services.tax_assurance.financial_statements import save_values
from tests.test_tax_assurance_api import EDITOR, P, YEAR, env  # noqa: F401  （夹具）

SRC = f"/api/projects/{P}/cell-sources/financial-statements"


def _sum(s):
    return sum((Decimal(i["amount"]) * Decimal(i["sign"]) for i in s["items"] if i["amount"] is not None), Decimal(0))


@pytest.fixture
def with_sources(env):  # noqa: F811
    from app.routers.cell_sources import router as src_router

    env["client"]._transport.app.include_router(src_router)
    return env


@pytest.mark.asyncio
async def test_every_linear_cell_reconciles(with_sources):
    async with with_sources["db"]() as s:
        res = await fs_sources(s, P, YEAR)
    assert res["format"] == "enterprise_system"
    linear = {k: v for k, v in res["cells"].items() if v["linear"]}
    assert len(linear) >= 20
    for k, v in linear.items():
        assert v["diff"] is None and _sum(v) == Decimal(v["value"] or 0), (k, v)


@pytest.mark.asyncio
async def test_account_and_total_rows(with_sources):
    async with with_sources["db"]() as s:
        cells = (await fs_sources(s, P, YEAR))["cells"]
    cash = cells["balance_sheet:7:current"]
    assert cash["kind"] == "import" and cash["value"] == "500"
    assert [(i["label"].split()[0], i["amount"]) for i in cash["items"]] == [("1002", "500")]
    assert cash["items"][0]["link"] == {"page": "trial_balance", "code": "1002"}
    assert cells["balance_sheet:7:prior"]["value"] == "400"  # 期初
    total = cells["balance_sheet:47:current"]
    assert total["title"].startswith("合计：")
    assert all(i["link"]["page"] == "statement" and i["link"]["sheet"] == "balance_sheet" for i in total["items"])
    # 贷方报表：借正贷负乘 −1
    payable = next(v for k, v in cells.items() if k.startswith("balance_sheet_liabilities:") and k.endswith(":current")
                   and any(i["label"].startswith("2202") for i in v["items"]))
    assert payable["value"] == "200" and payable["items"][0]["sign"] == "-1"


@pytest.mark.asyncio
async def test_manual_value_keeps_auto(with_sources):
    async with with_sources["db"]() as s:
        await save_values(s, P, YEAR, 0, {"balance_sheet": {"7": {"current": 650}}}, EDITOR)
        await s.commit()
        cells = (await fs_sources(s, P, YEAR))["cells"]
    cash = cells["balance_sheet:7:current"]
    assert cash["kind"] == "manual" and cash["manual"]["value"] == "650" and cash["manual"]["auto"] == "500"
    assert cash["value"] == "500" and _sum(cash) == Decimal(500)
    # 合计行按手工值合计（页面同一口径）
    total = cells["balance_sheet:47:current"]
    assert total["diff"] is None and _sum(total) == Decimal(total["value"])


@pytest.mark.asyncio
@pytest.mark.parametrize("who,status", [("editor", 200), ("reader", 200), ("outsider", 403)])
async def test_endpoint_requires_project_access(with_sources, who, status):
    with_sources["as"](who)
    r = await with_sources["client"].get(SRC, params={"year": YEAR})
    assert r.status_code == status, r.text
