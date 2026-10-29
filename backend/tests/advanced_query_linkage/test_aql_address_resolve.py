"""模板溯源 address-resolve（advanced-query-linkage-closure 任务 32；ADR-AQL-17，R7.4，AQ-17）。

改造前：底稿 URI 无条件 ``SELECT … FROM wp_template_registry``，该表在共享库不存在 ⇒ 恒 500（评估 B10）；返回的页签名
``workpaper`` / ``report`` / ``note`` 模板库页面认不出（真实页签名 ``wp-template`` / ``report-config`` / ``note-template``）；
还返回模板页不支持的 ``highlight``；调整分录 / 试算类结果给出一条打开模板库的路由（那里没有它们的模板）。

现在：表存在且有记录时以表为准，否则用与指标树同一的 JSON 目录（wp_account_mapping + step_sheet_mapping）判定登记；
查表失败回滚到保存点（PG 上请求事务不停在 aborted），目录读取失败记 WARNING、按未登记返回；未登记 / 没有模板定义时
``registered=false``、空路由。请求经 httpx ASGI 真发到生产注册的 custom_query router（``authz_world.build_app``），
只替换 ``get_current_user`` 与 ``get_db``。
"""
from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.models.core import User
from app.routers import custom_query
from app.services.wp_template_registry import wp_template_registry_service
from tests.authz_world import build_app

URL = "/api/custom-query/address-resolve"
LIBRARY_VUE = Path(__file__).resolve().parents[3] / "audit-platform" / "frontend" / "src" / "views" / "TemplateLibraryMgmt.vue"


@pytest_asyncio.fixture
async def sqlite_client() -> AsyncIterator[AsyncClient]:
    """SQLite 内存库：没有 information_schema ⇒ 表存在判定本身失败，走 JSON 目录（与表不存在同一路径）。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    api = build_app(custom_query.router)
    user = User(id=uuid.uuid4(), username="aql-b11", email="aql-b11@test.invalid", hashed_password="x",
                role=UserRole.auditor, is_active=True)

    async def _db():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    async def _user() -> User:
        return user

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    try:
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://aql-b11") as http:
            yield http
    finally:
        await engine.dispose()


async def _resolve(http: AsyncClient, uri: str) -> dict:
    response = await http.get(URL, params={"uri": uri})
    assert response.status_code == 200, response.text[:600]
    return response.json()


def _json_catalog_name(code: str) -> str | None:
    """金标准：直接读两份 JSON（不经被测函数）。"""
    import json

    data = Path(custom_query.__file__).resolve().parents[2] / "data"
    step = json.loads((data / "step_sheet_mapping.json").read_text(encoding="utf-8")).get("mappings", {})
    if code in step:
        return step[code].get("wp_name") or code
    acc = json.loads((data / "wp_account_mapping.json").read_text(encoding="utf-8"))
    rows = acc.get("mappings", acc) if isinstance(acc, dict) else acc
    hit = next((m for m in rows if m.get("wp_code") == code), None)
    return (hit.get("wp_name") or hit.get("account_name") or code) if hit else None


@pytest.mark.parametrize("code", ["A1", "E1", "D2", "E1-2", "D2-1"])
async def test_workpaper_registered_by_json_catalog_when_table_missing(sqlite_client: AsyncClient, code: str) -> None:
    """表不存在：按 JSON 目录判定登记，返回模板库「底稿模板」页签与编码；不 500、不带 highlight。"""
    expected = _json_catalog_name(code)
    assert expected, f"夹具前提：{code} 在 JSON 目录里"
    body = await _resolve(sqlite_client, f"workpaper:{code}|审定表|B7")
    assert body["registered"] is True
    assert body["template_name"] == expected
    assert (body["route_path"], body["route_query"]) == ("/template-library", {"tab": "wp-template", "wp_code": code})
    assert (body["sheet_name"], body["cell_ref"]) == ("审定表", "B7")


async def test_unregistered_workpaper_gives_no_route(sqlite_client: AsyncClient) -> None:
    body = await _resolve(sqlite_client, "workpaper:ZZ9")
    assert _json_catalog_name("ZZ9") is None
    assert (body["registered"], body["template_name"], body["route_path"], body["route_query"]) == (False, None, "", {})


@pytest.mark.parametrize(("uri", "tab", "key", "value"), [
    ("report:balance_sheet", "report-config", "report_type", "balance_sheet"),
    ("note:八、1", "note-template", "section_id", "八、1"),
])
async def test_report_and_note_open_their_library_tabs(sqlite_client: AsyncClient, uri: str, tab: str, key: str,
                                                       value: str) -> None:
    body = await _resolve(sqlite_client, uri + "|C5:C10")
    assert body["registered"] is True
    assert (body["route_path"], body["route_query"]) == ("/template-library", {"tab": tab, key: value})


@pytest.mark.parametrize("uri", ["adj:adj_aje", "tb:tb_detail", "tb:ledger_entries"])
async def test_adjustment_and_trial_balance_results_have_no_template(sqlite_client: AsyncClient, uri: str) -> None:
    """调整分录 / 试算与四表类结果没有模板定义：registered=false、空路由（前端提示「该类结果没有模板定义」）。"""
    body = await _resolve(sqlite_client, uri)
    assert (body["registered"], body["route_path"], body["route_query"]) == (False, "", {})


async def test_unknown_uri_is_400_in_chinese(sqlite_client: AsyncClient) -> None:
    response = await sqlite_client.get(URL, params={"uri": "tb_detail"})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_code"] == "INVALID_SOURCE_URI" and "无法识别" in detail["message"]


async def test_registry_table_decides_when_it_has_rows(sqlite_client: AsyncClient, monkeypatch) -> None:
    """表存在且有记录：以表为准（与指标树同一口径）——表里有的取表里的名称，表里没有的不再看 JSON。"""
    async def _exists(db) -> bool:
        return True

    async def _tree(db) -> list[dict]:
        return [{"wp_code": "Q9", "wp_name": "【测试】登记表模板"}]

    monkeypatch.setattr(wp_template_registry_service, "table_exists", _exists)
    monkeypatch.setattr(wp_template_registry_service, "load_tree", _tree)
    assert (await _resolve(sqlite_client, "workpaper:Q9"))["template_name"] == "【测试】登记表模板"
    assert (await _resolve(sqlite_client, "workpaper:A1"))["registered"] is False


async def test_empty_registry_table_falls_back_to_json(sqlite_client: AsyncClient, monkeypatch) -> None:
    async def _exists(db) -> bool:
        return True

    async def _tree(db) -> list[dict]:
        return []

    monkeypatch.setattr(wp_template_registry_service, "table_exists", _exists)
    monkeypatch.setattr(wp_template_registry_service, "load_tree", _tree)
    assert (await _resolve(sqlite_client, "workpaper:A1"))["template_name"] == _json_catalog_name("A1")


async def test_catalog_read_failure_logs_warning_and_reports_unregistered(sqlite_client: AsyncClient, monkeypatch,
                                                                         caplog) -> None:
    def _broken() -> dict:
        raise OSError("磁盘读取失败（测试注入）")

    monkeypatch.setattr(custom_query, "_load_step_sheet_mapping", _broken)
    with caplog.at_level(logging.WARNING, logger=custom_query.logger.name):
        body = await _resolve(sqlite_client, "workpaper:A1")
    assert (body["registered"], body["route_path"]) == (False, "")
    assert any("底稿模板目录读取失败" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)


def test_library_tab_names_exist_on_the_template_library_page() -> None:
    """后端返回的页签名都是模板库页面真有的页签（原先 workpaper / report / note 页面认不出）。"""
    names = set(re.findall(r'<el-tab-pane\s+name="([^"]+)"', LIBRARY_VUE.read_text(encoding="utf-8")))
    assert {"wp-template", "report-config", "note-template"} <= names
    assert set(custom_query._TEMPLATE_LIBRARY_TABS.values()) <= names


# ── 真库：共享库没有 wp_template_registry 表 ─────────────────────────────────────────────


@pytest.mark.pg_only
async def test_pg_table_missing_resolves_by_json_catalog(business) -> None:
    exists = (await business.session.execute(text(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'wp_template_registry'"))).scalar()
    assert exists == 0, "前提：共享库没有 wp_template_registry 表（评估 B10 的 500 即因此）"
    for code in ("A1", "E1"):
        response = await business.http.get(URL, params={"uri": f"workpaper:{code}"})
        assert response.status_code == 200, response.text[:600]
        body = response.json()
        assert (body["registered"], body["template_name"]) == (True, _json_catalog_name(code))
        assert body["route_query"] == {"tab": "wp-template", "wp_code": code}


@pytest.mark.pg_only
async def test_pg_registry_failure_rolls_back_to_savepoint(business, monkeypatch) -> None:
    """查表失败：回滚到保存点、改用 JSON 目录，同一请求会话之后照常可用（原先异常不回滚即让事务停在 aborted）。"""
    async def _exists(db) -> bool:
        return True

    async def _tree(db) -> list[dict]:
        await db.execute(text("SELECT wp_code FROM aql_b11_no_such_table"))
        return []

    monkeypatch.setattr(wp_template_registry_service, "table_exists", _exists)
    monkeypatch.setattr(wp_template_registry_service, "load_tree", _tree)
    response = await business.http.get(URL, params={"uri": "workpaper:A1"})
    assert response.status_code == 200, response.text[:600]
    assert response.json()["template_name"] == _json_catalog_name("A1")
    assert (await business.session.execute(text("SELECT 1"))).scalar() == 1
