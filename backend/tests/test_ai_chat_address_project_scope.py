"""AI 对话的地址查找按项目的审计年度与附注口径取（spec formula-fetch-followup-defect-closure R4.4）。

原状：``mcp_tools._search_address_ids`` 与 ``address_mention._load_address_entry`` 向地址目录传写死的年度 0 与 ``soe`` ⇒
试算表域按 ``year == 0`` 查不到任何科目（``build_trial_balance_entries`` 按年度过滤）、上市口径项目拿到国企附注地址；
``_load_address_entry`` 另外只看排序后的前 500 条（报表域在前、就占满了）⇒ 试算表 / 附注 / 底稿 / 辅助余额的地址一律找不到。
MCP 工具上下文的年度只读 ``audit_year``，未填（只有审计期末）时同样按 0 取数。
"""
from __future__ import annotations

import time
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.services import address_registry as svc
from app.services.ai_chat import address_mention, mcp_tools
from app.services.ai_chat.mcp_token import McpTokenPayload
from tests.authz_world import sqlite_world


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


async def _project(world, *, audit_year=None, period_end=None, template_type=None, nested=True):
    project = await world.project(project_id=uuid.uuid4())
    project.audit_year = audit_year
    project.audit_period_end = period_end
    if template_type is not None:
        data = {"template_type": template_type}
        project.wizard_state = {"steps": {"basic_info": {"data": data}}} if nested else {"basic_info": {"data": data}}
    await world.db.flush()
    return project


@pytest.mark.parametrize(("audit_year", "period_end", "template_type", "nested", "expected"), [
    (2024, date(2025, 12, 31), "listed", True, (2024, "listed")),   # audit_year 优先于审计期末
    (None, date(2025, 12, 31), "listed", False, (2025, "listed")),  # 未填 audit_year 回退审计期末年份；旧版 basic_info 位置
    (2025, None, "custom", True, (2025, "soe")),                    # 自定义模板按 soe（与前端 normalizeTemplateType 同口径）
    (None, None, None, True, (0, "soe")),                           # 都没有：年度 0（不猜今年）、口径 soe
])
async def test_project_address_scope(world, audit_year, period_end, template_type, nested, expected):
    project = await _project(world, audit_year=audit_year, period_end=period_end,
                             template_type=template_type, nested=nested)
    assert await address_mention.project_address_scope(world.db, project.id) == expected


def _entries(domain: str, n: int) -> list[svc.AddressEntry]:
    return [svc.AddressEntry(uri=f"{domain}://{i}#期末", domain=domain, source=str(i), path="", cell="期末",
                             label=f"{domain} 条目{i}", formula_ref=f"X('{domain}{i}')") for i in range(n)]


@pytest.fixture
def domains(monkeypatch: pytest.MonkeyPatch):
    """地址目录的域构建换成合成条目（报表域 600 条排在前面），记下每次取域的（年度, 口径）。"""
    calls: list[tuple[int, str, str]] = []
    tb = svc.AddressEntry(uri="tb://1001#期末余额", domain="tb", source="1001", path="", cell="期末余额",
                          label="试算表 > 1001 库存现金 > 期末余额", formula_ref="TB('1001','期末余额')", account_code="1001")

    async def fake_get_domain(self, db, project_id, year, template_type, domain):
        calls.append((year, template_type, domain))
        return {"report": _entries("report", 600), "tb": [tb]}.get(domain, [])

    monkeypatch.setattr(svc.AddressRegistryService, "_get_domain", fake_get_domain)
    if "_get_domain" in vars(svc.address_registry):
        monkeypatch.delattr(svc.address_registry, "_get_domain")
    return calls


async def test_load_address_entry_uses_project_scope_and_sees_every_domain(world, domains):
    project = await _project(world, audit_year=2024, template_type="listed")
    got = await address_mention._load_address_entry(world.db, "TB('1001','期末余额')", project.id)
    assert got is not None and got["account_code"] == "1001", "排在 600 条报表地址之后的试算表地址也要找得到"
    assert domains and {(y, t) for y, t, _ in domains} == {(2024, "listed")}


async def test_mcp_address_search_uses_project_scope(world, domains):
    project = await _project(world, audit_year=None, period_end=date(2025, 12, 31), template_type="listed")
    ctx = SimpleNamespace(db=world.db, project_id=project.id)
    got = await mcp_tools._search_address_ids(ctx, "1001", "tb", 10)
    assert got == ["TB('1001','期末余额')"]
    assert domains == [(2025, "listed", "tb")]


async def test_tool_context_year_falls_back_to_period_end(world):
    """工具上下文的年度与地址目录同一真源：未填 audit_year 时取审计期末年份（原先为 None ⇒ 试算表 / 附注工具按年度 0 取数）。"""
    project = await _project(world, audit_year=None, period_end=date(2025, 12, 31))
    user = await world.user()
    now = time.time()
    token = McpTokenPayload(token_id="t", user_id=user.id, project_id=project.id, run_id=uuid.uuid4(), role="auditor",
                            cycle_scope=frozenset(), mask_policy="none", issued_at=now, expires_at=now + 60)
    ctx = await mcp_tools.build_tool_context(db=world.db, token_payload=token, host_decision=None, resolver=None)
    assert ctx.year == 2025 and ctx.principal is user
