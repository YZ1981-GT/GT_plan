"""地址库一次最多取 50000 条、如实回报总数与截断（spec formula-fetch-and-wp-generation-defect-closure R3）。

原状：前端整库加载传 ``limit=5000``，后端 ``Query(100)`` 无上限校验、``total`` 是截断后的条数 ⇒ 真实项目里排在后面的
附注 / 底稿 / 辅助余额域整段被截掉，选择器里是空的，而且看不出被截过。
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.deps import get_current_user
from app.routers import address_registry as router_module
from app.services import address_registry as svc

_REPO = Path(__file__).resolve().parents[2]
_STORE_TS = _REPO / "audit-platform" / "frontend" / "src" / "stores" / "addressRegistry.ts"
_EDIT_DIALOG = _REPO / "audit-platform" / "frontend" / "src" / "components" / "formula" / "FormulaEditDialog.vue"

#: 每个域的合成条目数（顺序即不按域过滤时的返回顺序）
_COUNTS = {"report": 3, "tb": 2, "note": 4, "wp": 0, "aux": 1}

#: 搜索端点按项目只读权限放行（R4.1）：项目须为 UUID；本文件只测载荷，门禁走真实 assert_project_permission 的管理员分支
_PID = "5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e01"
_ADMIN = SimpleNamespace(id=uuid.uuid4(), role=SimpleNamespace(value="admin"))


class _NoDbSession:
    """业务层已换成合成条目、不读库；门禁设置 RLS 上下文时按 SQLite 方言跳过（不需要真实会话）。"""

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))


def _isolate_singleton(monkeypatch) -> None:
    """别的用例若在单例实例上留下过 ``_get_domain`` 实例属性（monkeypatch 撤销实例级替换时会写回原方法），
    会挡住本文件的类级替换 ⇒ 本用例期间先拿掉它（用例结束由 monkeypatch 还原）。"""
    if "_get_domain" in vars(svc.address_registry):
        monkeypatch.delattr(svc.address_registry, "_get_domain")


def _entries(domain: str, n: int) -> list[svc.AddressEntry]:
    return [
        svc.AddressEntry(uri=f"{domain}://s/p#{i}", domain=domain, source="s", path="p", cell=str(i),
                         label=f"{domain} 条目{i}", formula_ref=f"X('{domain}{i}')")
        for i in range(n)
    ]


@pytest.fixture
def client(monkeypatch):
    calls: list[str] = []

    async def fake_get_domain(self, db, project_id, year, template_type, domain):
        calls.append(domain)
        return _entries(domain, _COUNTS[domain])

    monkeypatch.setattr(svc.AddressRegistryService, "_get_domain", fake_get_domain)
    _isolate_singleton(monkeypatch)
    app = FastAPI()
    app.include_router(router_module.router)

    async def _db():
        yield _NoDbSession()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: _ADMIN
    with TestClient(app) as c:
        c.calls = calls
        yield c


def _get(client, **params):
    return client.get("/api/address-registry", params={"project_id": _PID, "year": 2025, **params})


def test_limit_upper_bound_is_50000():
    assert svc.ADDRESS_REGISTRY_MAX_LIMIT == 50_000


@pytest.mark.parametrize("limit", [0, 50_001, 1_000_000])
def test_limit_out_of_range_is_422_not_silently_clamped(client, limit):
    assert _get(client, limit=limit).status_code == 422


def test_full_load_at_the_upper_bound_returns_everything(client):
    body = _get(client, limit=50_000).json()
    assert body["total"] == body["returned"] == sum(_COUNTS.values())
    assert body["truncated"] is False and body["truncated_domains"] == []


def test_truncation_reports_true_total_and_cut_domains(client):
    """不按域过滤时按 report → tb → note → wp → aux 返回；limit=4 截掉 tb 的 1 条与 note / aux 全部。"""
    body = _get(client, limit=4).json()
    assert body["total"] == 10 and body["returned"] == 4 and len(body["items"]) == 4
    assert body["truncated"] is True
    assert body["truncated_domains"] == ["tb", "note", "aux"]
    assert [i["domain"] for i in body["items"]] == ["report", "report", "report", "tb"]


def test_single_domain_truncation(client):
    body = _get(client, domain="note", limit=2).json()
    assert (body["total"], body["returned"], body["truncated"], body["truncated_domains"]) == (4, 2, True, ["note"])
    assert client.calls == ["note"]  # 按域加载只物化该域


def test_total_counts_keyword_matches_only(client):
    body = _get(client, keyword="条目3", limit=100).json()
    assert body["total"] == 1 and body["returned"] == 1 and body["truncated"] is False


@pytest.mark.asyncio
async def test_search_keeps_slicing_for_other_callers(monkeypatch):
    """AI 对话 / 提及等其他调用方仍用 search(limit)：行为不变（只返回前 limit 条）。"""
    async def fake_get_domain(self, db, project_id, year, template_type, domain):
        return _entries(domain, _COUNTS[domain])

    monkeypatch.setattr(svc.AddressRegistryService, "_get_domain", fake_get_domain)
    _isolate_singleton(monkeypatch)
    got = await svc.address_registry.search(None, "p1", 2025, "", "", "soe", 4)
    assert len(got) == 4
    matched = await svc.address_registry.match(None, "p1", 2025, "", "", "soe")
    assert len(matched) == 10
    matched.clear()  # 返回的是副本，清空不影响下一次
    assert len(await svc.address_registry.match(None, "p1", 2025, "", "", "soe")) == 10


def test_frontend_full_load_limit_matches_backend_upper_bound():
    """前端整库加载上限与后端上限同一个数；公式编辑弹窗的底稿域直调也用同一常量（不再各写各的 5000）。"""
    store = _STORE_TS.read_text(encoding="utf-8")
    m = re.search(r"export const ADDRESS_REGISTRY_FULL_LOAD_LIMIT\s*=\s*([\d_]+)", store)
    assert m, "stores/addressRegistry.ts 缺 ADDRESS_REGISTRY_FULL_LOAD_LIMIT"
    assert int(m.group(1).replace("_", "")) == svc.ADDRESS_REGISTRY_MAX_LIMIT
    assert "limit: ADDRESS_REGISTRY_FULL_LOAD_LIMIT" in store
    dialog = _EDIT_DIALOG.read_text(encoding="utf-8")
    assert "limit: ADDRESS_REGISTRY_FULL_LOAD_LIMIT" in dialog
    for src, name in ((store, "store"), (dialog, "FormulaEditDialog")):
        assert not re.search(r"limit:\s*5000\b", src), f"{name} 仍写死 limit: 5000"
